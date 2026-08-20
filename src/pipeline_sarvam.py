import json
import logging
import os
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


class SarvamAPIError(Exception):
    pass


def get_api_key() -> str:
    key = os.environ.get(ENV_KEY_NAME)
    if key:
        return key
    if SECRETS_PATH.exists():
        return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))["api_subscription_key"]
    raise RuntimeError(f"API key not found: set env var {ENV_KEY_NAME} or create {SECRETS_PATH}")


def _post_json(endpoint: str, payload: dict, api_key: str) -> dict:
    url = f"{API_BASE}{endpoint}"
    headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=120)
    except requests.RequestException as exc:
        raise SarvamAPIError(f"request to {endpoint} failed: {exc}") from exc
    if response.status_code != 200:
        raise SarvamAPIError(
            f"request to {endpoint} failed with HTTP {response.status_code}: {response.text}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise SarvamAPIError(f"request to {endpoint} returned non-JSON body: {response.text}") from exc


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    api_key = get_api_key()
    payload = {
        "input": text,
        "source_language_code": source_lang,
        "target_language_code": target_lang,
        "model": TRANSLATE_MODEL,
    }
    data = _post_json("/translate", payload, api_key)
    translated = data.get("translated_text")
    if not isinstance(translated, str) or not translated:
        raise SarvamAPIError(
            f"translate failed ({source_lang} -> {target_lang}): "
            f"response missing translated_text: {data}"
        )
    return translated


def get_native_answer(query_text: str, lang_code: str) -> str:
    api_key = get_api_key()
    system_prompt = (
        "You are a helpful assistant. Answer the user's question entirely in the "
        f"language with code {lang_code}. Do not use English or any other language in your response."
    )
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
        raise SarvamAPIError(f"chat completion failed ({lang_code}): unexpected response shape: {data}") from exc
    if not isinstance(content, str) or not content:
        raise SarvamAPIError(f"chat completion failed ({lang_code}): empty or non-string content: {data}")
    return content


def run_single_query_pipeline(
    query_id: str,
    source_query_en: str,
    lang_codes: list[str],
    logger: logging.Logger | None = None,
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
            native_answer = get_native_answer(source_query_en, lang_code)
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
                model_used="sarvam",
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
            model_used="sarvam",
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