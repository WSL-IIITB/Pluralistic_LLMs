# Persona card schema (hand-distilled from backend/app/data/personas/*.json)

One file per region: `<region_id>.json` -> `{ "male": Card, "female": Card }`.
Everything must be GROUNDED in that persona's JSON (region_definition + topics[*].regional_profile).
Never invent facts, numbers, names or quotes. Numbers must appear in the source text.

Card = {
  "name": "Puttaswamy",                 // the persona's first name as written in region_definition; if the text never names them, use a short descriptor like "The Malpe fisherman's wife"
  "ageLabel": "44",                      // "44" or "Late 30s" (as the source states)
  "emoji": "🌾",                         // ONE emoji avatar that fits (👨‍🌾 👩‍🏭 🧕 👩‍🌾 🎣 ☕ ...)
  "role": "Sugarcane & paddy farmer",    // <= 6 words
  "place": "Malavalli taluk, Mandya",   // <= 6 words
  "community": "Vokkaliga",              // or "" if none stated
  "tagline": "...",                      // <= 16 words, third person, vivid but factual
  "household": [ { "who": "Wife Rathnamma", "emoji": "👩" }, ... ],   // 2-6 members as stated in the source
  "vitals": [ { "label": "Land", "value": "2.5 acres" }, ... ],       // 3-4 tiles, only figures stated in the source (land, income, schooling, kids, etc.)
  "dayInLife": [ { "when": "Before 5 am", "emoji": "🐄", "text": "..." }, ... ],  // 4-5 beats, each text <= 18 words, from the daily-life topic; `when` may be a season/time-of-day
  "topics": [                            // EXACTLY these 7 keys in this order:
    // daily_life_and_work, family_and_household, education_and_schooling, health_and_wellbeing,
    // community_and_belief, civic_life_and_government, worldview_and_concerns
    { "key": "daily_life_and_work", "label": "Daily Life & Work", "emoji": "⏰",
      "headline": "<= 12 words",
      "points": [ "<= 20 words", "<= 20 words", "<= 20 words" ],       // exactly 3, concrete
      "stat": { "value": "22%", "label": "<= 12 words, what the number is + year/source as stated" } }  // OPTIONAL: omit if no clean number
  ],
  "schoolPressures": [ { "emoji": "🚜", "label": "<= 3 words", "detail": "<= 20 words" } ],  // 3-4 items: what pulls/pushes THIS household's kids out of secondary school (from the education topic)
  "worries": [ "<= 4 words", ... ]       // 4-6 short chips from the worldview/concerns topic
}
Style: plain, warm, concrete. No markdown. No [S1]-style citation markers. Composite persona -- describe in third person, present tense.

## `factorEffects` (added for the "how the factors affect them" section)

```
"factorEffects": {
  "districtId": "29-573",                 // the district the persona lives in (place field)
  "pressures": [ "<= 35 words", ... ],    // EXACTLY one per schoolPressures item, same order: what that pressure does to THIS household's schooling
  "sanitation": "<= 30 words",            // "If ... lacks a proper toilet, ..." -- conditional, built only from facts on the card
  "district": "<= 40 words"               // the district-level factor (English-medium share, or protected wells in Bengaluru Urban/Mysuru),
                                          // anchored in the card's own pressures; says what the card shows instead
}
```
Rules: no new facts, numbers or places; never claim what research found (the UI shows the district's real research status from
`dominantFactorWhy`); write conditionally ("if ...") for the dominant factors, since the persona data does not measure them.


## `dataLens` (the persona's district through the NITI prescriptive model)

```
"dataLens": {
  "area": "Belagavi Chikkodi",            // the NITI workbook row the persona lives in (public/data/niti-prescriptive.json)
  "changes": [ { "factor": "<exact NITI factor name>", "effect": "<= 36 words" }, x3 ],  // the area's top three changes (feasible
                                          // ranking), same order: how that change would reach THIS household
  "lag": { "factor": "<exact NITI factor name>", "effect": "<= 36 words" }  // the factor where the area ranks lowest in Karnataka,
                                          // if not already in the top three
}
```
Rules: the numbers (values, ranks, dropout rates) are shown live from niti-prescriptive.json, so the lines carry none except facts
already on the card (ages). Any "lowest / leads / among the fewest" wording must match the area's rank among Karnataka's 35 rows.
Household facts come only from the card. Write conditionally where the card does not show the factor ("if her home lacked a
toilet..."). The UI labels these lines as an interpretation, not data.

## `intro` (the animated self-introduction)

```
"intro": {
  "backdrop": "fields" | "city" | "dry-plains" | "coast" | "hills-forest",
  "lines": [ { "scene": "hello|household|day|world|school|district|worries|outro",
               "text": "first-person caption, <= 25 words",
               "say": "optional spoken form (numbers and acronyms written out)",
               "show": [indices into household / dayInLife / schoolPressures / worries; for district, dataLens.changes],
               "topic": "topic key whose headline + stat the 'world' scene shows" } ]
}
```
Rules: scenes in that order; 130-215 words in all (about a minute); every fact from this card only, every number on the card;
no added greetings, language or culture beyond the card; the outro says it is a composite persona built from public data.
`python3 scripts/check_persona_intros.py` must pass.
