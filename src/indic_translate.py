"""Local IndicTrans2 translation via transformers.

Replaces the cloud Sarvam translate API. Uses:
  - models/indictrans2/indictrans2-en-indic  (English -> Indic)
  - models/indictrans2/indictrans2-indic-en  (Indic -> English)
"""
import json
import logging
import time
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
from IndicTransToolkit import IndicProcessor

from src.logging_config import PROJECT_ROOT

MODEL_DIR = PROJECT_ROOT / "models" / "indictrans2"
EN_INDIC_DIR = MODEL_DIR / "indictrans2-en-indic"
INDIC_EN_DIR = MODEL_DIR / "indictrans2-indic-en"

# Sarvam language code -> IndicTrans2 FLORES target tag.
# For dual-script languages we pick the script that matches sarvam-m output.
SARVAM_TO_FLORES = {
    "as-IN": "asm_Beng",   # Assamese
    "bn-IN": "ben_Beng",   # Bengali
    "brx-IN": "brx_Deva",  # Bodo
    "doi-IN": "doi_Deva",  # Dogri
    "gu-IN": "guj_Gujr",   # Gujarati
    "hi-IN": "hin_Deva",   # Hindi
    "kn-IN": "kan_Knda",   # Kannada
    "ks-IN": "kas_Arab",   # Kashmiri (Perso-Arabic, matches sarvam-m)
    "kok-IN": "gom_Deva",  # Konkani
    "mai-IN": "mai_Deva",  # Maithili
    "ml-IN": "mal_Mlym",   # Malayalam
    "mni-IN": "mni_Beng",  # Manipuri (Bengali, matches sarvam-m)
    "mr-IN": "mar_Deva",   # Marathi
    "ne-IN": "npi_Deva",   # Nepali
    "od-IN": "ory_Orya",   # Odia
    "pa-IN": "pan_Guru",   # Punjabi
    "sa-IN": "san_Deva",   # Sanskrit
    "sat-IN": "sat_Olck",  # Santali
    "sd-IN": "snd_Arab",   # Sindhi (Perso-Arabic)
    "ta-IN": "tam_Taml",   # Tamil
    "te-IN": "tel_Telu",   # Telugu
    "ur-IN": "urd_Arab",   # Urdu
}

SRC_LANG = "eng_Latn"
EN_TAG = "eng_Latn"


def _flores_for(sarvam_code: str) -> str:
    tag = SARVAM_TO_FLORES.get(sarvam_code)
    if tag is None:
        raise ValueError(f"no FLORES mapping for Sarvam code: {sarvam_code}")
    return tag


class TranslationModels:
    """Lazily load one translation model at a time (each is ~1GB in RAM)."""

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None
        self._direction: str | None = None
        self._logger = logging.getLogger(__name__)
        self._processor = IndicProcessor(inference=True)

    @staticmethod
    def _load(directory: str):
        model = AutoModelForSeq2SeqLM.from_pretrained(
            directory, trust_remote_code=True, dtype="float32",
        )
        tokenizer = AutoTokenizer.from_pretrained(
            directory,
            trust_remote_code=True,
            src_vocab_fp=str(directory / "dict.SRC.json"),
            tgt_vocab_fp=str(directory / "dict.TGT.json"),
            src_spm_fp=str(directory / "model.SRC"),
            tgt_spm_fp=str(directory / "model.TGT"),
        )
        return model, tokenizer

    def _ensure(self, direction: str) -> None:
        if self._direction == direction:
            return
        directory = EN_INDIC_DIR if direction == "en-indic" else INDIC_EN_DIR
        self._logger.info("loading IndicTrans2 %s", direction)
        self._model, self._tokenizer = self._load(directory)
        self._direction = direction

    def translate_to_indic(self, text: str, sarvam_code: str) -> str:
        """English -> native Indic, in the target language's script."""
        tgt = _flores_for(sarvam_code)
        self._ensure("en-indic")
        # preprocess adds language tags and fills the placeholder queue that
        # postprocess_batch consumes; they must be called as a pair.
        batch = self._processor.preprocess_batch([text], src_lang=SRC_LANG, tgt_lang=tgt)
        self._tokenizer._switch_to_input_mode()
        tokenized = self._tokenizer(
            batch, padding="longest", truncation=True, max_length=256,
            return_tensors="pt",
        )
        generated = self._model.generate(
            **tokenized, num_beams=5, num_return_sequences=1, max_length=256,
            use_cache=False,
        )
        self._tokenizer._switch_to_target_mode()
        decoded = self._tokenizer.batch_decode(
            generated, skip_special_tokens=True, clean_up_tokenization_spaces=True,
        )
        # dist-200M emits Devanagari for non-Devanagari scripts;
        # postprocess converts to the target native script.
        decoded = self._processor.postprocess_batch(decoded, lang=tgt)
        return decoded[0]

    def translate_to_english(self, text: str, sarvam_code: str) -> str:
        """Native Indic -> English (back-translation)."""
        src = _flores_for(sarvam_code)
        self._ensure("indic-en")
        batch = self._processor.preprocess_batch([text], src_lang=src, tgt_lang=EN_TAG)
        self._tokenizer._switch_to_input_mode()
        tokenized = self._tokenizer(
            batch, padding="longest", truncation=True, max_length=256,
            return_tensors="pt",
        )
        generated = self._model.generate(
            **tokenized, num_beams=5, num_return_sequences=1, max_length=256,
            use_cache=False,
        )
        self._tokenizer._switch_to_target_mode()
        decoded = self._tokenizer.batch_decode(
            generated, skip_special_tokens=True, clean_up_tokenization_spaces=True,
        )
        decoded = self._processor.postprocess_batch(decoded, lang=EN_TAG)
        return decoded[0]


_MODELS = TranslationModels()


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """Translate via local IndicTrans2.

    source_lang/target_lang use Sarvam codes (e.g. 'en-IN', 'hi-IN').
    """
    t0 = time.time()
    if target_lang in ("en", "en-IN"):
        # Back-translation: target is English.
        result = _MODELS.translate_to_english(text, source_lang)
    else:
        # Forward translation: English -> native.
        result = _MODELS.translate_to_indic(text, target_lang)
    logging.getLogger(__name__).info(
        "translate %s->%s took %.1fs", source_lang, target_lang, time.time() - t0,
    )
    return result
