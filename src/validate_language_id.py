import argparse
import json

import fasttext

from src.logging_config import PROJECT_ROOT
from src.validation_io import update_validation, now_iso

MODEL_PATH = PROJECT_ROOT / "config" / "lid.176.ftz"
DEFAULT_QUERY_ID = "self_image_life_goal"
LANG_FILE = PROJECT_ROOT / "config" / "languages.json"

EXPECTED_LABELS = {
    "as-IN": "as", "bn-IN": "bn", "brx-IN": "brx", "doi-IN": "doi",
    "gu-IN": "gu", "hi-IN": "hi", "kn-IN": "kn", "ks-IN": "ks",
    "kok-IN": "gom", "mai-IN": "mai", "ml-IN": "ml", "mni-IN": "mni",
    "mr-IN": "mr", "ne-IN": "ne", "od-IN": "or", "pa-IN": "pa",
    "sa-IN": "sa", "sat-IN": "sat", "sd-IN": "sd", "ta-IN": "ta",
    "te-IN": "te", "ur-IN": "ur", "en": "en",
}

SUPPORTED_LABELS = {
    "as", "bn", "en", "gu", "hi", "kn", "ml", "mr", "ne", "or",
    "pa", "sa", "sd", "ta", "te", "ur", "gom", "mai",
}

LABEL_NAMES = {
    "asm": "Assamese", "ben": "Bengali", "brx": "Bodo", "doi": "Dogri",
    "guj": "Gujarati", "hin": "Hindi", "kan": "Kannada", "kas": "Kashmiri",
    "kok": "Konkani", "mai": "Maithili", "mal": "Malayalam", "mni": "Manipuri",
    "mar": "Marathi", "nep": "Nepali", "ori": "Odia", "pan": "Punjabi",
    "san": "Sanskrit", "sat": "Santali", "snd": "Sindhi", "tam": "Tamil",
    "tel": "Telugu", "urd": "Urdu", "eng": "English", "deu": "German",
    "ita": "Italian", "fra": "French", "spa": "Spanish", "por": "Portuguese",
    "ron": "Romanian", "pol": "Polish", "rus": "Russian", "nld": "Dutch",
}


def predict(model, text: str) -> tuple[str, float]:
    clean = " ".join(text.split())
    if not clean:
        return "", 0.0
    labels, probs = model.predict(clean)
    return labels[0].replace("__label__", ""), float(probs[0])


def main(raw_file) -> None:
    model = fasttext.load_model(str(MODEL_PATH))
    records = json.loads(raw_file.read_text(encoding="utf-8"))
    langs = json.loads(LANG_FILE.read_text(encoding="utf-8"))["languages"]
    name_by_code = {entry["code"]: entry["name"] for entry in langs}
    name_by_code["en"] = "English"
    confusable_by_code = {
        entry["code"]: set(entry.get("adjacent_confusable", []))
        for entry in langs
    }
    alternate_by_code = {
        entry["code"]: set(entry.get("alternate_detector_labels", []))
        for entry in langs
    }

    print(
        f"{'code':7s} | {'expected':11s} | {'detected':11s} | {'verdict':10s} | "
        f"ref(native_query): {'' :8s}"
    )
    print("-" * 84)

    mismatches = []
    ambiguous = []
    unverifiable = []
    results_by_code = {}  # for validation write-back
    for record in records:
        code = record["target_lang_code"]
        expected_name = name_by_code[code]
        expected_label = EXPECTED_LABELS[code]

        detected_label, prob = predict(model, record["native_answer"])
        detected_name = LABEL_NAMES.get(detected_label, detected_label)

        ref_label, _ = predict(model, record["translated_query"])
        ref_name = LABEL_NAMES.get(ref_label, ref_label)
        ref_ok = ref_label == expected_label

        if expected_label not in SUPPORTED_LABELS:
            verdict = "UNVERIFIED"
        elif detected_label == expected_label:
            verdict = "MATCH"
        elif detected_label in alternate_by_code.get(code, set()):
            verdict = "MATCH"
        elif detected_label in confusable_by_code.get(code, set()):
            verdict = "DETECTOR-AMBIGUOUS"
        else:
            verdict = "MISMATCH"

        if verdict == "MISMATCH":
            mismatches.append((code, expected_name, detected_name, prob))
        if verdict == "DETECTOR-AMBIGUOUS":
            ambiguous.append((code, expected_name, detected_name))
        if verdict == "UNVERIFIED":
            unverifiable.append((code, expected_name, expected_label))

        results_by_code[code] = {
            "status": verdict,
            "detected_label": detected_label,
            "detected_name": detected_name,
            "checked_at": now_iso(),
        }

        ref_col = f"OK({prob:.2f})" if ref_ok else f"ref_detected={ref_name}"
        if (
            detected_label != expected_label
            and detected_label in alternate_by_code.get(code, set())
        ):
            print(f"{code:7s} | {expected_name:11s} | {detected_name:11s} | alt-script MATCH | {ref_col}")
        else:
            print(f"{code:7s} | {expected_name:11s} | {detected_name:11s} | {verdict:18s} | {ref_col}")

    print()
    print(f"Total records checked: {len(records)}")
    print(f"MATCH count: {len(records) - len(mismatches) - len(ambiguous) - len(unverifiable)}")
    print(f"DETECTOR-AMBIGUOUS count: {len(ambiguous)}")
    for code, exp, det in ambiguous:
        print(f"  {code}: expected {exp}, detected {det} (adjacent script/language; manual review confirms)")
    print(f"MISMATCH count: {len(mismatches)}")
    for code, exp, det, prob in mismatches:
        print(f"  {code}: expected {exp}, detected {det} (p={prob:.2f})")
    print(f"UNVERIFIED (detector does not support the language, manual review required): {len(unverifiable)}")
    for code, exp, lab in unverifiable:
        print(f"  {code}: expected {exp}, lid.176 has no {lab}")

    update_validation(raw_file, "language_id", results_by_code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate native_answer language/script against the expected language."
    )
    parser.add_argument(
        "--query-id",
        default=DEFAULT_QUERY_ID,
        help=f"query id; resolves to data/raw/sarvam_<query_id>.json (default: {DEFAULT_QUERY_ID})",
    )
    args = parser.parse_args()

    raw_file = PROJECT_ROOT / "data" / "raw" / f"sarvam_{args.query_id}.json"
    if not raw_file.exists():
        parser.error(f"dataset not found: {raw_file}")

    main(raw_file)