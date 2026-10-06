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
