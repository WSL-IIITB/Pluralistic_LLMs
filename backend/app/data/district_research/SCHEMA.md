# District research file schema

One file per Karnataka district: `<districtId>.json` (e.g. `29-577.json`). Topic is fixed:
**secondary-school dropout / out-of-school / irregular attendance (Classes 8-10, incl. SSLC)** in that district.

```json
{
  "districtId": "29-577",
  "name": "Mysuru",
  "regionId": "old-mysuru",
  "researchedOn": "2026-10-06",
  "headline": "<= 25 words: the single best-evidenced takeaway for THIS district",
  "summary": "60-100 words synthesising what the sources say about why students leave / stop attending secondary school here",
  "reasons": [
    {
      "factor": "<= 6 words",
      "category": "economic | migration | school-infrastructure | social-norms | gender | health | governance | other",
      "detail": "<= 40 words, specific to this district, paraphrased",
      "sources": [1, 3],
      "evidence": "strong | moderate | thin"
    }
  ],
  "keyFacts": [ { "label": "<= 8 words incl. year", "value": "figure as stated in the source", "sources": [2] } ],
  "headlines": [
    { "title": "article title", "outlet": "The Hindu", "date": "2024-06-12", "url": "https://...", "takeaway": "<= 25 words" }
  ],
  "responses": [ { "text": "<= 30 words: a local programme/official action", "sources": [4] } ],
  "sources": [
    { "id": 1, "url": "https://...", "title": "...", "outlet": "...", "date": "2024-06-12", "type": "news | government | ngo | research | data" }
  ],
  "officialFactorCheck": [
    {
      "factor": "factor name exactly as given in the UIDAI/NITI rows for this district",
      "method": "state | district",
      "verdict": "supports | contradicts | unclear | no-evidence",
      "note": "<= 35 words: what local evidence says about this factor in THIS district",
      "sources": [2]
    }
  ],
  "coverage": "rich | moderate | thin",
  "gaps": "<= 40 words: what you looked for but could not find"
}
```

`officialFactorCheck` is OPTIONAL (added for the ChatGPT/Gemini deep-research round): one entry per UIDAI/NITI factor row
supplied for the district. Counts: reasons 3-6, keyFacts 3-6, headlines 3-8 (district-specific media items, newest first), responses 0-4.
`sources[].id` are 1-based and every `sources` index in reasons/keyFacts/responses must exist. Every `headlines[].url`
must also appear in `sources`.
