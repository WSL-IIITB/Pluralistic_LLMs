from dataclasses import dataclass


@dataclass
class EvaluationRecord:
    query_id: str
    source_query_en: str
    model_used: str
    target_lang_code: str
    translated_query: str
    native_answer: str
    back_translated_answer_en: str
    timestamp: str
    notes: str = ""