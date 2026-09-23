"""
Static subreddit -> district lookup table (the "city_subreddit" resolution
method in ../schema.py's ResolutionMethod). This is the cheapest, highest-
confidence signal the district resolver has: if a post came from r/mumbai,
it is almost certainly about Mumbai district, no NER/LLM required.

Self-contained by design: the (district_id, state_code) pairs below were
cross-referenced by hand against app/data/district_gazetteer.json (keyed by
lowercase district/state name -> [{"districtId", "stateCode", ...}]) at the
time this file was written, and are copied here as plain literals so this
module has zero import-time dependency on that JSON file (or on any other
in-progress module). If the gazetteer's ids ever change, re-cross-reference
and update the literals below.

Three tiers of entry:
  - City/region subreddits with an unambiguous single district
    -> confidence "high", district_id set.
  - Whole-state subreddits (e.g. r/kerala covers 14 districts) -> district_id
    is intentionally None (no single district to pick), state_code is set,
    confidence "medium". The resolver should treat this as a state-level hit
    -- i.e. exactly the "state_fallback" ResolutionMethod / isStateFallback
    case in schema.py, not a failed lookup.
  - Pan-India subreddits (r/india, r/IndiaSpeaks, r/indianews) -> both
    district_id and state_code are None, confidence "low". This is an
    explicit non-geolocating entry: the *key exists* in the map (so callers
    can tell "we recognized this subreddit and it doesn't geolocate" apart
    from "we've never heard of this subreddit"), but resolution must fall
    through to the next stage (place NER / script / LLM geolocation).
"""

from __future__ import annotations

SubredditEntry = dict[str, "str | None"]

SUBREDDIT_DISTRICT_MAP: dict[str, SubredditEntry] = {
    # ── Pan-India (explicitly non-geolocating) ─────────────────────────────
    "india": {"district_id": None, "state_code": None, "confidence": "low"},
    "indiaspeaks": {"district_id": None, "state_code": None, "confidence": "low"},
    "indianews": {"district_id": None, "state_code": None, "confidence": "low"},

    # ── Metro / large city subreddits (high confidence, single district) ──
    "mumbai": {"district_id": "27-519", "state_code": "27", "confidence": "high"},
    "delhi": {"district_id": "07-delhi", "state_code": "07", "confidence": "high"},
    "gurgaon": {"district_id": "06-086", "state_code": "06", "confidence": "high"},
    "gurugram": {"district_id": "06-086", "state_code": "06", "confidence": "high"},
    "noida": {"district_id": "09-141", "state_code": "09", "confidence": "high"},
    "faridabad": {"district_id": "06-088", "state_code": "06", "confidence": "high"},
    "bangalore": {"district_id": "29-572", "state_code": "29", "confidence": "high"},
    "bengaluru": {"district_id": "29-572", "state_code": "29", "confidence": "high"},
    "chennai": {"district_id": "33-603", "state_code": "33", "confidence": "high"},
    "kolkata": {"district_id": "19-342", "state_code": "19", "confidence": "high"},
    "pune": {"district_id": "27-521", "state_code": "27", "confidence": "high"},
    "hyderabad": {"district_id": "36-536", "state_code": "36", "confidence": "high"},
    "ahmedabad": {"district_id": "24-474", "state_code": "24", "confidence": "high"},

    # ── Mid-size city subreddits ────────────────────────────────────────────
    "lucknow": {"district_id": "09-157", "state_code": "09", "confidence": "high"},
    "nagpur": {"district_id": "27-505", "state_code": "27", "confidence": "high"},
    "chandigarh": {"district_id": "04-055", "state_code": "04", "confidence": "high"},
    "bhopal": {"district_id": "23-444", "state_code": "23", "confidence": "high"},
    "jaipur": {"district_id": "08-110", "state_code": "08", "confidence": "high"},
    "indore": {"district_id": "23-439", "state_code": "23", "confidence": "high"},
    "surat": {"district_id": "24-492", "state_code": "24", "confidence": "high"},
    "kanpur": {"district_id": "09-164", "state_code": "09", "confidence": "high"},
    "coimbatore": {"district_id": "33-632", "state_code": "33", "confidence": "high"},
    "kochi": {"district_id": "32-595", "state_code": "32", "confidence": "high"},
    "vizag": {"district_id": "37-544", "state_code": "37", "confidence": "high"},
    "visakhapatnam": {"district_id": "37-544", "state_code": "37", "confidence": "high"},
    "patna": {"district_id": "10-230", "state_code": "10", "confidence": "high"},
    "guwahati": {"district_id": "18-322", "state_code": "18", "confidence": "high"},
    "bhubaneswar": {"district_id": "21-386", "state_code": "21", "confidence": "high"},
    "nashik": {"district_id": "27-516", "state_code": "27", "confidence": "high"},
    "varanasi": {"district_id": "09-197", "state_code": "09", "confidence": "high"},
    "amritsar": {"district_id": "03-049", "state_code": "03", "confidence": "high"},
    "ludhiana": {"district_id": "03-041", "state_code": "03", "confidence": "high"},
    "jodhpur": {"district_id": "08-113", "state_code": "08", "confidence": "high"},
    "udaipur": {"district_id": "08-130", "state_code": "08", "confidence": "high"},
    "vadodara": {"district_id": "24-486", "state_code": "24", "confidence": "high"},
    "rajkot": {"district_id": "24-476", "state_code": "24", "confidence": "high"},
    "ranchi": {"district_id": "20-364", "state_code": "20", "confidence": "high"},
    "raipur": {"district_id": "22-410", "state_code": "22", "confidence": "high"},
    "shimla": {"district_id": "02-033", "state_code": "02", "confidence": "high"},
    "dehradun": {"district_id": "05-060", "state_code": "05", "confidence": "high"},
    "jammu": {"district_id": "01-021", "state_code": "01", "confidence": "high"},
    "srinagar": {"district_id": "01-010", "state_code": "01", "confidence": "high"},
    "thiruvananthapuram": {"district_id": "32-601", "state_code": "32", "confidence": "high"},
    "trivandrum": {"district_id": "32-601", "state_code": "32", "confidence": "high"},
    "mysuru": {"district_id": "29-577", "state_code": "29", "confidence": "high"},
    "mysore": {"district_id": "29-577", "state_code": "29", "confidence": "high"},
    "madurai": {"district_id": "33-623", "state_code": "33", "confidence": "high"},
    "puducherry": {"district_id": "34-635", "state_code": "34", "confidence": "high"},
    "pondicherry": {"district_id": "34-635", "state_code": "34", "confidence": "high"},
    "goa": {"district_id": None, "state_code": "30", "confidence": "medium"},

    # ── Whole-state subreddits (no single district -> state_fallback) ─────
    "kerala": {"district_id": None, "state_code": "32", "confidence": "medium"},
    "tamilnadu": {"district_id": None, "state_code": "33", "confidence": "medium"},
    "punjab": {"district_id": None, "state_code": "03", "confidence": "medium"},
    "rajasthan": {"district_id": None, "state_code": "08", "confidence": "medium"},
    "gujarat": {"district_id": None, "state_code": "24", "confidence": "medium"},
    "westbengal": {"district_id": None, "state_code": "19", "confidence": "medium"},
    "karnataka": {"district_id": None, "state_code": "29", "confidence": "medium"},
    "maharashtra": {"district_id": None, "state_code": "27", "confidence": "medium"},
    "uttarpradesh": {"district_id": None, "state_code": "09", "confidence": "medium"},
    "bihar": {"district_id": None, "state_code": "10", "confidence": "medium"},
    "odisha": {"district_id": None, "state_code": "21", "confidence": "medium"},
    "assam": {"district_id": None, "state_code": "18", "confidence": "medium"},
    "jharkhand": {"district_id": None, "state_code": "20", "confidence": "medium"},
    "chhattisgarh": {"district_id": None, "state_code": "22", "confidence": "medium"},
    "uttarakhand": {"district_id": None, "state_code": "05", "confidence": "medium"},
    "himachalpradesh": {"district_id": None, "state_code": "02", "confidence": "medium"},
    "madhyapradesh": {"district_id": None, "state_code": "23", "confidence": "medium"},
    "haryana": {"district_id": None, "state_code": "06", "confidence": "medium"},
    "telangana": {"district_id": None, "state_code": "36", "confidence": "medium"},
    "andhrapradesh": {"district_id": None, "state_code": "37", "confidence": "medium"},
    "manipur": {"district_id": None, "state_code": "14", "confidence": "medium"},
    "meghalaya": {"district_id": None, "state_code": "17", "confidence": "medium"},
    "nagaland": {"district_id": None, "state_code": "13", "confidence": "medium"},
    "mizoram": {"district_id": None, "state_code": "15", "confidence": "medium"},
    "tripura": {"district_id": None, "state_code": "16", "confidence": "medium"},
    "sikkim": {"district_id": None, "state_code": "11", "confidence": "medium"},
    "arunachalpradesh": {"district_id": None, "state_code": "12", "confidence": "medium"},
}


def _state_names_from_gazetteer(gazetteer: dict) -> dict[str, str]:
    """state_code -> state_name, derived from the district gazetteer (used by
    the Data View's router)."""
    names: dict[str, str] = {}
    for candidates in gazetteer.values():
        for cand in candidates:
            code = cand.get("stateCode")
            name = cand.get("stateName")
            if code and name and code not in names:
                names[code] = name
    return names


def lookup_subreddit(name: str) -> SubredditEntry | None:
    """
    Normalize a subreddit reference (case-insensitive, optional "r/" prefix,
    optional leading/trailing slashes/whitespace) and look it up.

    Returns None if the subreddit is simply unknown to this map (caller
    should fall through to the next resolution stage). Returns a dict with
    district_id=None if the subreddit IS known but is a whole-state or
    pan-India community that doesn't geolocate to a single district --
    callers should distinguish these two cases (see module docstring).
    """
    if not name:
        return None
    normalized = name.strip().strip("/")
    if normalized.lower().startswith("r/"):
        normalized = normalized[2:]
    normalized = normalized.strip().lower()
    return SUBREDDIT_DISTRICT_MAP.get(normalized)
