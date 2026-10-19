"""
Measure how much text the self-hosted Gemma can actually use in one prompt.

    cd backend && .venv/bin/python ../scripts/probe_gemma_context.py

Uses the backend's own configured Gemma client (backend/.env) -- the address is never printed.
For each size (4k..64k tokens) it hides a made-up fact at the start, middle and end of varied filler
text and asks for it back. "Usable context" = the largest size where recall is >= 95% and the first
token arrives in under ~15 s. Stops at the first failing size. Result -> docs/chat/gemma_probe.json.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.config import get_settings  # noqa: E402
from app.connectors.llm import RemoteGemmaLLMClient  # noqa: E402

SIZES = [4_000, 8_000, 16_000, 32_000, 64_000]
POSITIONS = ["start", "middle", "end"]
TTFT_LIMIT_S = 15.0
WORDS = (
    "school district village family harvest monsoon teacher student road bus fee exam result class "
    "migration labour cotton sugarcane coffee estate harbour fishing weaving market cooperative panchayat "
    "hostel scholarship attendance register survey report officer collector committee programme"
).split()


def filler(rng: random.Random, n_chars: int) -> str:
    out, size = [], 0
    while size < n_chars:
        s = " ".join(rng.choice(WORDS) for _ in range(rng.randint(8, 16))).capitalize() + ". "
        out.append(s)
        size += len(s)
    return "".join(out)


async def ask(client, model: str, prompt: str, timeout: float) -> tuple[str, float, int | None]:
    t0 = time.monotonic()
    stream = await client.chat.completions.create(
        model=model, temperature=0, max_tokens=24, stream=True, timeout=timeout,
        stream_options={"include_usage": True},
        messages=[{"role": "user", "content": prompt}],
    )
    ttft, text, usage = None, "", None
    async for chunk in stream:
        if chunk.usage:
            usage = chunk.usage.prompt_tokens
        if chunk.choices and chunk.choices[0].delta.content:
            if ttft is None:
                ttft = time.monotonic() - t0
            text += chunk.choices[0].delta.content
    return text, ttft if ttft is not None else time.monotonic() - t0, usage


async def main() -> None:
    llm = RemoteGemmaLLMClient(get_settings())
    client, model = llm.client, llm._model
    base = str(client.base_url).rstrip("/")
    clean = lambda s: str(s).replace(base, "<endpoint>")  # noqa: E731
    result: dict = {"model": model, "trials": [], "usable_context_tokens": None}

    try:  # many OpenAI-compatible servers report max_model_len on /v1/models
        models = await client.models.list()
        for m in models.data:
            extra = getattr(m, "model_extra", None) or {}
            print(f"server model: {m.id}  max_model_len: {extra.get('max_model_len', 'not reported')}")
            result["reported_max_model_len"] = extra.get("max_model_len")
    except Exception as exc:  # noqa: BLE001
        print("could not list models:", type(exc).__name__, clean(exc)[:120])

    # calibrate characters-per-token with a small prompt
    rng = random.Random(7)
    probe_text = filler(rng, 6_000)
    _, _, tok = await ask(client, model, probe_text + "\nSay OK.", 60)
    chars_per_token = (len(probe_text) + 9) / tok if tok else 4.0
    print(f"calibration: {chars_per_token:.2f} characters per token\n")

    usable = None
    for size in SIZES:
        recalls, ttfts, failed, actual = 0, [], False, None
        for pos in POSITIONS:
            code = f"{rng.choice(['MANGO', 'CEDAR', 'LOTUS', 'OPAL'])}-{rng.randint(1000, 9999)}"
            needle = f"IMPORTANT FACT: the secret code for district Zeta-9 is {code}. "
            body = filler(rng, int(size * chars_per_token))
            cut = {"start": 0, "middle": len(body) // 2, "end": len(body)}[pos]
            prompt = body[:cut] + needle + body[cut:] + "\n\nQuestion: what is the secret code for district Zeta-9? Reply with the code only."
            try:
                text, ttft, used = await ask(client, model, prompt, 240)
                ok = code in text
                recalls += ok
                ttfts.append(ttft)
                actual = used or actual
                print(f"{size:>6} tok  needle@{pos:<6} recall={'yes' if ok else 'NO '}  first token {ttft:5.1f}s  (prompt_tokens={used})")
                result["trials"].append({"size": size, "pos": pos, "ok": ok, "ttft_s": round(ttft, 2), "prompt_tokens": used})
            except Exception as exc:  # noqa: BLE001 -- overflow etc.
                failed = True
                msg = clean(exc)[:200]
                print(f"{size:>6} tok  needle@{pos:<6} ERROR {type(exc).__name__}: {msg}")
                result["trials"].append({"size": size, "pos": pos, "error": msg})
                break
        recall = recalls / len(POSITIONS)
        slow = bool(ttfts) and max(ttfts) > TTFT_LIMIT_S
        if failed or recall < 0.95 or slow:
            print(f"-> stopping at {size}: {'error' if failed else f'recall {recall:.0%}'}{', slow' if slow else ''}\n")
            break
        usable = actual or size
        print(f"-> {size} OK (recall {recall:.0%}, worst first token {max(ttfts):.1f}s)\n")

    result["usable_context_tokens"] = usable
    os.makedirs(os.path.join(ROOT, "docs/chat"), exist_ok=True)
    out = os.path.join(ROOT, "docs/chat/gemma_probe.json")
    json.dump(result, open(out, "w"), indent=2)
    print(f"USABLE CONTEXT (measured): {usable} tokens  -> {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
