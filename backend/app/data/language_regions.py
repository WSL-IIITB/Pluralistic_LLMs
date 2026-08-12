"""
Dependency-free Indian-script detection heuristic (the "script_language"
resolution method in ../schema.py's ResolutionMethod). No langdetect/fasttext/
any external NLP package -- just Unicode codepoint-range checks against the
well-known Indic script blocks, each of which maps almost 1:1 to a state's
dominant regional language. This is deliberately a cheap, offline-only signal
that sits between the subreddit-name lookup (app/data/subreddit_map.py) and
full LLM geolocation in the resolver's fallback chain.

State codes below were cross-referenced by hand against
app/data/district_gazetteer.json (keyed by lowercase state name ->
[{"districtId", "stateCode", ...}]) at the time this file was written and are
copied here as plain literals, so this module has zero import-time dependency
on that JSON file (or any other in-progress module).

Coverage and known limitations:
  - Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Gurmukhi (Punjabi),
    and Odia scripts each map to one state with "medium" confidence -- script
    alone reliably identifies the *language*, and each of these languages has
    one clearly dominant state, so this is a solid (if soft) geo-signal.
  - Telugu script is used by both Andhra Pradesh and Telangana (post-2014
    bifurcation); we default to Andhra Pradesh (the larger Telugu-speaking
    population per the last census) but this is a coin-flip -- callers should
    treat it as no stronger than "medium" and let a later stage (place NER
    naming an actual city/district) override it.
  - Devanagari is used for Hindi *and* Marathi (and Nepali, Konkani, ...), so
    it cannot alone distinguish "Hindi-belt state" from "Maharashtra" -- we
    return (None, "low") rather than guess, explicitly falling through to the
    next resolution stage (place NER / LLM geolocation) instead of pretending
    to a confidence the signal doesn't have.
  - Plain Latin-script text (English, or romanized/transliterated Indian
    languages -- "kaise ho", "eppadi irukka") carries no script signal at
    all -- also (None, "low"), fall through to LLM geolocation.
  - Mixed-script text is resolved by whichever Indic script has the most
    codepoints in the input; ties fall through to (None, "low") since we
    can't confidently pick one.
"""

from __future__ import annotations

# ── Unicode block ranges for Indian scripts (inclusive, codepoint ints) ────
# Order matches the Unicode standard's own layout of the Indic blocks.
_SCRIPT_RANGES: dict[str, tuple[int, int]] = {
    "devanagari": (0x0900, 0x097F),
    "bengali": (0x0980, 0x09FF),
    "gurmukhi": (0x0A00, 0x0A7F),
    "gujarati": (0x0A80, 0x0AFF),
    "odia": (0x0B00, 0x0B7F),
    "tamil": (0x0B80, 0x0BFF),
    "telugu": (0x0C00, 0x0C7F),
    "kannada": (0x0C80, 0x0CFF),
    "malayalam": (0x0D00, 0x0D7F),
}

# Script -> (state_code, confidence). Devanagari is intentionally absent --
# it is handled as an explicit ambiguous case in detect_script_region().
_SCRIPT_STATE: dict[str, tuple[str, str]] = {
    "bengali": ("19", "medium"),  # West Bengal
    "gurmukhi": ("03", "medium"),  # Punjab
    "gujarati": ("24", "medium"),  # Gujarat
    "odia": ("21", "medium"),  # Odisha
    "tamil": ("33", "medium"),  # Tamil Nadu
    "telugu": ("37", "medium"),  # Andhra Pradesh (see module docstring caveat)
    "kannada": ("29", "medium"),  # Karnataka
    "malayalam": ("32", "medium"),  # Kerala
}


def _classify_char(ch: str) -> str | None:
    """Return the Indic script block name a single character falls in, or None."""
    codepoint = ord(ch)
    for script, (lo, hi) in _SCRIPT_RANGES.items():
        if lo <= codepoint <= hi:
            return script
    return None


def detect_script_region(text: str) -> tuple[str | None, str]:
    """
    Heuristically infer a dominant state from the Unicode scripts present in
    `text`, by counting codepoints per Indic script block and taking whichever
    script appears most.

    Returns (state_code_or_None, confidence):
      - (state_code, "medium") for an unambiguous single-state script
        (Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Gurmukhi, Odia).
      - (None, "low") if the dominant script is Devanagari (Hindi/Marathi/
        Nepali/Konkani all share it -- state ambiguous), if no Indic
        characters are present at all (plain Latin/English text), or if the
        top two scripts are tied (can't confidently pick one).
    """
    if not text:
        return (None, "low")

    counts: dict[str, int] = {}
    for ch in text:
        script = _classify_char(ch)
        if script is not None:
            counts[script] = counts.get(script, 0) + 1

    if not counts:
        # Plain Latin script (English, or romanized Indian-language text) --
        # no script signal at all; fall through to LLM geolocation.
        return (None, "low")

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    top_script, top_count = ranked[0]
    if len(ranked) > 1 and ranked[1][1] == top_count:
        # Tied dominant scripts (e.g. equal Tamil and Telugu snippets) --
        # not confident enough to pick one.
        return (None, "low")

    if top_script == "devanagari":
        # Hindi-belt vs Maharashtra (vs Nepali/Konkani) is genuinely
        # ambiguous from script alone -- explicitly fall through rather than
        # guess a state confidence doesn't support.
        return (None, "low")

    return _SCRIPT_STATE[top_script]
