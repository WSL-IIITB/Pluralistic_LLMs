import json

import fasttext

from src.logging_config import PROJECT_ROOT

MODEL_PATH = PROJECT_ROOT / "config" / "lid.176.ftz"
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "sarvam_self_image_life_goal.json"
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
    "pa", "sa", "ta", "te", "ur", "gom", "mai",
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


def main() -> None:
    model = fasttext.load_model(str(MODEL_PATH))
    records = json.loads(RAW_FILE.read_text(encoding="utf-8"))
    langs = json.loads(LANG_FILE.read_text(encoding="utf-8"))["languages"]
    name_by_code = {entry["code"]: entry["name"] for entry in langs}
    name_by_code["en"] = "English"

    print(
        f"{'code':7s} | {'expected':11s} | {'detected':11s} | {'verdict':9s} | "
        f"ref(native_query): {'' :8s}"
    )
    print("-" * 78)

    mismatches = []
    unverifiable = []
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
        else:
            verdict = "MISMATCH"

        if verdict == "MISMATCH":
            mismatches.append((code, expected_name, detected_name, prob))
        if verdict == "UNVERIFIED":
            unverifiable.append((code, expected_name, expected_label))

        ref_col = f"OK({prob:.2f})" if ref_ok else f"ref_detected={ref_name}"
        print(f"{code:7s} | {expected_name:11s} | {detected_name:11s} | {verdict:10s} | {ref_col}")

    print()
    print(f"Total records checked: {len(records)}")
    print(f"MATCH count: {len(records) - len(mismatches) - len(unverifiable)}")
    print(f"MISMATCH count: {len(mismatches)}")
    for code, exp, det, prob in mismatches:
        print(f"  {code}: expected {exp}, detected {det} (p={prob:.2f})")
    print(f"UNVERIFIED (detector does not support the language, manual review required): {len(unverifiable)}")
    for code, exp, lab in unverifiable:
        print(f"  {code}: expected {exp}, lid.176 has no {lab}")


if __name__ == "__main__":
    main()