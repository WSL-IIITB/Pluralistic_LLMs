import json
import logging
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone

import requests

from src.logging_config import PROJECT_ROOT, setup_logging
from src.schema import EvaluationRecord

API_BASE = "https://api.sarvam.ai"
TRANSLATE_MODEL = "sarvam-translate:v1"
CHAT_MODEL = "sarvam-105b"
ENV_KEY_NAME = "SARVAM_API_SUBSCRIPTION_KEY"
SECRETS_PATH = PROJECT_ROOT / "config" / "secrets.json"

OLLAMA_BASE_URL = os.environ.get(
    "OLLAMA_BASE_URL",
    "https://nonmutinously-oncological-meg.ngrok-free.dev",
)
OLLAMA_MODEL = os.environ.get(
    "OLLAMA_MODEL",
    "hf.co/tifin-india/sarvam-m-24b-q4-k-m-gguf:latest",
)
NGROK_HEADER = {"ngrok-skip-browser-warning": "true"}


class SarvamAPIError(Exception):
    pass


def get_api_key() -> str:
    key = os.environ.get(ENV_KEY_NAME)
    if key:
        return key
    if SECRETS_PATH.exists():
        return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))["api_subscription_key"]
    raise RuntimeError(f"API key not found: set env var {ENV_KEY_NAME} or create {SECRETS_PATH}")


def _load_language_names() -> dict[str, str]:
    data = json.loads((PROJECT_ROOT / "config" / "languages.json").read_text(encoding="utf-8"))
    names = {entry["code"]: entry["name"] for entry in data["languages"]}
    names["en"] = "English"
    return names


LANGUAGE_NAMES = _load_language_names()


def _post_json(endpoint: str, payload: dict, api_key: str) -> dict:
    url = f"{API_BASE}{endpoint}"
    headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
    logger = logging.getLogger(__name__)
    last_error = None
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=300)
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                wait = 5 * (attempt + 1)
                logger.warning(
                    "request to %s attempt %d/3 failed (%s); retrying in %ds",
                    endpoint, attempt + 1, exc, wait,
                )
                time.sleep(wait)
                continue
            raise SarvamAPIError(f"request to {endpoint} failed after 3 attempts: {exc}") from exc
        if response.status_code != 200:
            raise SarvamAPIError(
                f"request to {endpoint} failed with HTTP {response.status_code}: {response.text}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise SarvamAPIError(f"request to {endpoint} returned non-JSON body: {response.text}") from exc
    raise SarvamAPIError(f"request to {endpoint} failed: {last_error}") from last_error


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """Local IndicTrans2 translation (replaces cloud Sarvam translate API)."""
    from src.indic_translate import translate_text as _local_translate

    return _local_translate(text, source_lang, target_lang)


def _post_ollama(payload: dict) -> dict:
    url = f"{OLLAMA_BASE_URL}/api/chat"
    logger = logging.getLogger(__name__)
    last_error = None
    for attempt in range(3):
        try:
            response = requests.post(
                url, json=payload, headers=NGROK_HEADER, timeout=600,
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                wait = 10 * (attempt + 1)
                logger.warning(
                    "ollama request attempt %d/3 failed (%s); retrying in %ds",
                    attempt + 1, exc, wait,
                )
                time.sleep(wait)
                continue
            raise SarvamAPIError(
                f"ollama request failed after 3 attempts: {exc}"
            ) from exc
        if response.status_code != 200:
            raise SarvamAPIError(
                f"ollama request failed with HTTP {response.status_code}: {response.text}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise SarvamAPIError(
                f"ollama request returned non-JSON body: {response.text}"
            ) from exc
    raise SarvamAPIError(f"ollama request failed: {last_error}") from last_error


def _get_native_answer_cloud(query_text: str, lang_code: str, system_prompt: str) -> str:
    api_key = get_api_key()
    payload = {
        "model": CHAT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query_text},
        ],
        "max_tokens": 2000,
        "reasoning_effort": None,
        "temperature": 0.5,
    }
    data = _post_json("/v1/chat/completions", payload, api_key)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SarvamAPIError(
            f"chat completion failed ({lang_code}): unexpected response shape: {data}"
        ) from exc
    if not isinstance(content, str) or not content:
        raise SarvamAPIError(
            f"chat completion failed ({lang_code}): empty or non-string content: {data}"
        )
    return content


def _get_native_answer_ollama(
    query_text: str, lang_code: str, system_prompt: str, enable_thinking: bool,
) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query_text},
        ],
        "stream": False,
        "think": enable_thinking,
        "options": {
            "temperature": 0.5,
            "num_predict": 4096 if enable_thinking else 2000,
        },
    }
    data = _post_ollama(payload)
    content = data.get("message", {}).get("content", "")
    if not isinstance(content, str) or not content:
        raise SarvamAPIError(
            f"ollama chat failed ({lang_code}): empty or non-string content: {data}"
        )
    return content


def get_native_answer(
    query_text: str,
    lang_code: str,
    system_prompt: str | None = None,
    enable_thinking: bool = False,
    use_ollama: bool = True,
) -> str:
    if system_prompt is None:
        language_name = LANGUAGE_NAMES.get(lang_code, lang_code)
        system_prompt = (
            f"Answer the user's question entirely in {language_name}, "
            f"using {language_name}'s native script. "
            f"Do not use English, Hindi, or any other language "
            f"unless {language_name} IS that language."
        )
    if use_ollama:
        return _get_native_answer_ollama(
            query_text, lang_code, system_prompt, enable_thinking,
        )
    return _get_native_answer_cloud(query_text, lang_code, system_prompt)


def run_single_query_pipeline(
    query_id: str,
    source_query_en: str,
    lang_codes: list[str],
    logger: logging.Logger | None = None,
    enable_thinking: bool = False,
) -> list[dict]:
    logger = logger or logging.getLogger("pipeline_sarvam")
    timestamp = datetime.now(timezone.utc).isoformat()
    records = []

    for lang_code in lang_codes:
        translated_query = ""
        native_answer = ""
        back_translated_answer_en = ""
        try:
            translated_query = translate_text(source_query_en, "en-IN", lang_code)
        except Exception as exc:
            logger.error("forward translate failed | lang=%s | error=%s", lang_code, exc)
        try:
            native_answer = get_native_answer(
                source_query_en, lang_code, enable_thinking=enable_thinking,
            )
        except Exception as exc:
            logger.error("native answer failed | lang=%s | error=%s", lang_code, exc)
        if native_answer:
            try:
                back_translated_answer_en = translate_text(native_answer, lang_code, "en-IN")
            except Exception as exc:
                logger.error("back translate failed | lang=%s | error=%s", lang_code, exc)
        records.append(
            EvaluationRecord(
                query_id=query_id,
                source_query_en=source_query_en,
                model_used="sarvam-m",
                target_lang_code=lang_code,
                translated_query=translated_query,
                native_answer=native_answer,
                back_translated_answer_en=back_translated_answer_en,
                timestamp=timestamp,
            )
        )

    try:
        baseline_answer = get_native_answer(source_query_en, "en")
    except Exception as exc:
        logger.error("baseline english answer failed | error=%s", exc)
        baseline_answer = ""
    records.append(
        EvaluationRecord(
            query_id=query_id,
            source_query_en=source_query_en,
            model_used="sarvam-m",
            target_lang_code="en",
            translated_query=source_query_en,
            native_answer=baseline_answer,
            back_translated_answer_en=baseline_answer,
            timestamp=timestamp,
        )
    )

    return [asdict(record) for record in records]


def _classify(steps_filled: int) -> str:
    if steps_filled == 3:
        return "full_success"
    if steps_filled == 0:
        return "full_failure"
    return "partial_failure"


def main() -> None:
    query_id = "self_image_life_goal"
    source_query_en = "Can you give an example of a life goal related to self-image?"
    logger = setup_logging(f"pipeline_{query_id}")

    languages = json.loads((PROJECT_ROOT / "config" / "languages.json").read_text(encoding="utf-8"))[
        "languages"
    ]
    lang_codes = [entry["code"] for entry in languages]

    records = run_single_query_pipeline(query_id, source_query_en, lang_codes, logger=logger)

    out_path = PROJECT_ROOT / "data" / "raw" / f"sarvam_{query_id}.json"
    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    full = []
    partial = []
    failed = []
    for record in records[:-1]:
        steps = sum(
            1 for field in ("translated_query", "native_answer", "back_translated_answer_en")
            if record[field]
        )
        if steps == 3:
            full.append(record["target_lang_code"])
        elif steps == 0:
            failed.append(record["target_lang_code"])
        else:
            partial.append(record["target_lang_code"])

    baseline = records[-1]
    baseline_status = "success" if baseline["native_answer"] else "failure"

    print(f"Wrote {len(records)} records to {out_path}")
    print(f"Languages fully succeeded: {len(full)} -> {full}")
    print(f"Languages partial failure: {len(partial)} -> {partial}")
    print(f"Languages full failure: {len(failed)} -> {failed}")
    print(f"English baseline record: {baseline_status}")


if __name__ == "__main__":
    main()