# TASK: District-by-district research on secondary-school dropout in Karnataka (15 districts)

You are running as Gemini Deep Research. Do NOT ask me to confirm or edit the research plan -- treat the plan as
approved and start researching immediately. Put the complete deliverable in the final report text itself (not in a
linked document, canvas or table-only summary).

## 1. Pre-answered clarifications
- Topic (fixed): **why students leave, or stop attending, secondary school -- Classes 8-10 / SSLC -- in each named district of Karnataka**, India. Also relevant: out-of-school and irregular-attendance children of that age, SSLC (Class 10) failure and exam-linked exits, and the transition from Class 8 to 9.
- Geography: ONLY the 15 districts listed in section 4. Treat each district separately. Do not substitute state-level or neighbouring-district evidence for a district; if you can only find state-level material, say so in `gaps` and mark coverage "thin".
- Time window: prioritise 2022-2026 reporting and data; use older material (2015-2021) only when it is the best district-specific evidence available, and say which year it is from.
- Languages: search in English AND Kannada (e.g. Prajavani, Vijay Karnataka, Vijayavani, Udayavani, Kannada Prabha, Samyukta Karnataka, Public TV, TV9 Kannada, Daijiworld, local district editions of The Hindu / Deccan Herald / Times of India). Kannada-language articles are valuable for the thinly covered districts -- read them and paraphrase in English.
- Source types wanted, in this priority: (1) district-specific news and investigations, (2) government / official data (Samagra Shiksha Karnataka, DSERT, KSEAB SSLC results, DDPI/BEO statements, UDISE+, District Statistical Handbooks, Karnataka State Commission for Protection of Child Rights, Labour Dept child-labour drives, Zilla Panchayat/DC orders and "out-of-school children survey" results), (3) NGO / research reports (Pratham ASER, CRY, Azim Premji Foundation, Child Rights Trust, KHPT, Mythri, Bachpan Bachao Andolan, UNICEF/UNESCO case studies, peer-reviewed papers).
- Output language: English. Output format: exactly as specified in section 6.

## 2. What to find, for EVERY district
1. The specific reasons students leave secondary school there, as documented: poverty and seasonal/labour migration (sugarcane cutting, tobacco/cotton/chilli/brick-kiln/construction work, plantation/estate work, fishing/harbour work, mining belt), child labour, child marriage and girls leaving after puberty, school distance / closed or merged schools / zero-enrolment schools, teacher vacancies, toilets and other infrastructure, language-of-instruction issues, SSLC failure and "slow learner" exits, safety of girls, post-COVID drop, Lambani/tanda and other community-specific access gaps, Devadasi-linked practices, disability, health.
2. Hard numbers with the year: out-of-school counts from the state's annual survey, dropout counts/rates, SSLC pass % and state rank (2024, 2025, 2026 if available), number of schools closed/merged, child marriages stopped, children rescued from labour, teacher-vacancy counts, enrolment/GER.
3. Recent district-specific news items (aim for 5-10 per district) with real, openable URLs.
4. What local authorities and NGOs are actually doing (tracking drives, bridge courses, residential schools, cash transfers, bicycle/bus schemes).
5. **Check the official UIDAI/NITI factors** supplied for each district in section 4 (see section 3): for each factor row, does local evidence support it, contradict it, or is there no evidence either way?

## 3. About the UIDAI / NITI Aayog "dominant factor" rows
For each district I am giving you rows from two official-statistics files that name the factor statistically most associated with that district's secondary-school dropout rate:
- `method: state` -- the SAME factor is the top-ranked factor for the whole state (here: sanitation), paired with this district's own figure for it.
- `method: district` -- a factor selected individually for the district (e.g. share of schools with English as medium of instruction, schools with a protected well).
Do NOT try to reinterpret the numeric values (I could not verify what the numbers measure) and do not present them as findings. Your job is only to test, using real-world evidence from the district, whether each named factor plausibly matters locally. Report one `officialFactorCheck` entry per supplied row with a verdict of `supports`, `contradicts`, `unclear` or `no-evidence`, a one-sentence note, and the source numbers behind it. A verdict of `no-evidence` is a perfectly good answer.
Where a district has sub-area rows (e.g. "Belagavi Chikkodi"), the sub-area is part of the same district: include it in that district's research and name it in the factor note.

## 4. The 15 districts (project data -- treat as background, never cite it as a source)
### 29-575 | Dakshina Kannada | regionId "karavali"
- Casefile secondary dropout rate (LKI-SSM): 1.2%
- UIDAI/NITI row [method: state] area "Dakshina Kannada": factor "% Population Living in Households with Improved Sanitation" (value 0.22)
- UIDAI/NITI row [method: district] area "Dakshina Kannada": factor "% Schools with instruction medium 1 (English)" (value 0.01)
- Existing coverage from a previous shallow pass: none yet

### 29-569 | Udupi | regionId "karavali"
- Casefile secondary dropout rate (LKI-SSM): 1.4%
- UIDAI/NITI row [method: state] area "Udupi": factor "% Population Living in Households with Improved Sanitation" (value 0.26)
- UIDAI/NITI row [method: district] area "Udupi": factor "% Schools with instruction medium 1 (English)" (value 0.01)
- Existing coverage from a previous shallow pass: thin (6 sources, 5 news items)

### 29-563 | Uttara Kannada | regionId "karavali"
- Casefile secondary dropout rate (LKI-SSM): 12.5%
- Sub-area in the data files: Uttara Kannada Sirsi -- dropout 17.2%
- UIDAI/NITI row [method: state] area "Uttara Kannada": factor "% Population Living in Households with Improved Sanitation" (value 2.3)
- UIDAI/NITI row [method: state] area "Uttara Kannada Sirsi": factor "% Population Living in Households with Improved Sanitation" (value 3.17)
- UIDAI/NITI row [method: district] area "Uttara Kannada": factor "% Schools with instruction medium 1 (English)" (value 0.14)
- UIDAI/NITI row [method: district] area "Uttara Kannada Sirsi": factor "% Schools with instruction medium 1 (English)" (value 0.35)
- Existing coverage from a previous shallow pass: thin (3 sources, 3 news items)

### 29-555 | Belagavi | regionId "kitturu-karnataka"
- Casefile secondary dropout rate (LKI-SSM): 22.2%
- Sub-area in the data files: Belagavi Chikkodi -- dropout 22.4%
- UIDAI/NITI row [method: state] area "Belagavi": factor "% Population Living in Households with Improved Sanitation" (value 4.09)
- UIDAI/NITI row [method: state] area "Belagavi Chikkodi": factor "% Population Living in Households with Improved Sanitation" (value 4.13)
- UIDAI/NITI row [method: district] area "Belagavi": factor "% Schools with instruction medium 1 (English)" (value 0.19)
- UIDAI/NITI row [method: district] area "Belagavi Chikkodi": factor "% Schools with instruction medium 1 (English)" (value 0.26)
- Existing coverage from a previous shallow pass: thin (5 sources, 4 news items)

### 29-557 | Vijayapura | regionId "kitturu-karnataka"
- Casefile secondary dropout rate (LKI-SSM): 21.8%
- UIDAI/NITI row [method: state] area "Vijayapura": factor "% Population Living in Households with Improved Sanitation" (value 4.02)
- UIDAI/NITI row [method: district] area "Vijayapura": factor "% Schools with instruction medium 1 (English)" (value 0.2)
- Existing coverage from a previous shallow pass: thin (2 sources, 2 news items)

### 29-556 | Bagalkote | regionId "kitturu-karnataka"
- Casefile secondary dropout rate (LKI-SSM): 16.3%
- UIDAI/NITI row [method: state] area "Bagalkot": factor "% Population Living in Households with Improved Sanitation" (value 3.0)
- UIDAI/NITI row [method: district] area "Bagalkot": factor "% Schools with instruction medium 1 (English)" (value 0.15)
- Existing coverage from a previous shallow pass: thin (2 sources, 2 news items)

### 29-562 | Dharwad | regionId "kitturu-karnataka"
- Casefile secondary dropout rate (LKI-SSM): 12.8%
- UIDAI/NITI row [method: state] area "Dharwad": factor "% Population Living in Households with Improved Sanitation" (value 2.36)
- UIDAI/NITI row [method: district] area "Dharwad": factor "% Schools with instruction medium 1 (English)" (value 0.07)
- Existing coverage from a previous shallow pass: moderate (4 sources, 3 news items)

### 29-561 | Gadag | regionId "kitturu-karnataka"
- Casefile secondary dropout rate (LKI-SSM): 20.7%
- UIDAI/NITI row [method: state] area "Gadag": factor "% Population Living in Households with Improved Sanitation" (value 3.81)
- UIDAI/NITI row [method: district] area "Gadag": factor "% Schools with instruction medium 1 (English)" (value 0.18)
- Existing coverage from a previous shallow pass: thin (2 sources, 0 news items)

### 29-564 | Haveri | regionId "kitturu-karnataka"
- Casefile secondary dropout rate (LKI-SSM): 24.3%
- UIDAI/NITI row [method: state] area "Haveri": factor "% Population Living in Households with Improved Sanitation" (value 4.48)
- UIDAI/NITI row [method: district] area "Haveri": factor "% Schools with instruction medium 1 (English)" (value 0.25)
- Existing coverage from a previous shallow pass: thin (2 sources, 1 news items)

### 29-579 | Kalaburagi | regionId "kalyana-karnataka"
- Casefile secondary dropout rate (LKI-SSM): 30.0%
- UIDAI/NITI row [method: state] area "Kalburgi": factor "% Population Living in Households with Improved Sanitation" (value 5.53)
- UIDAI/NITI row [method: district] area "Kalburgi": factor "% Schools with instruction medium 1 (English)" (value 0.21)
- Existing coverage from a previous shallow pass: moderate (6 sources, 5 news items)

### 29-558 | Bidar | regionId "kalyana-karnataka"
- Casefile secondary dropout rate (LKI-SSM): 29.2%
- UIDAI/NITI row [method: state] area "Bidar": factor "% Population Living in Households with Improved Sanitation" (value 5.38)
- UIDAI/NITI row [method: district] area "Bidar": factor "% Schools with instruction medium 1 (English)" (value 0.24)
- Existing coverage from a previous shallow pass: thin (4 sources, 2 news items)

### 29-580 | Yadgir | regionId "kalyana-karnataka"
- Casefile secondary dropout rate (LKI-SSM): 37.4%
- UIDAI/NITI row [method: state] area "Yadagiri": factor "% Population Living in Households with Improved Sanitation" (value 6.89)
- UIDAI/NITI row [method: district] area "Yadagiri": factor "% Schools with instruction medium 1 (English)" (value 0.32)
- Existing coverage from a previous shallow pass: moderate (6 sources, 6 news items)

### 29-559 | Raichur | regionId "kalyana-karnataka"
- Casefile secondary dropout rate (LKI-SSM): 29.5%
- UIDAI/NITI row [method: state] area "Raichur": factor "% Population Living in Households with Improved Sanitation" (value 5.44)
- UIDAI/NITI row [method: district] area "Raichur": factor "% Schools with instruction medium 1 (English)" (value 0.22)
- Existing coverage from a previous shallow pass: moderate (5 sources, 3 news items)

### 29-560 | Koppal | regionId "kalyana-karnataka"
- Casefile secondary dropout rate (LKI-SSM): 25.7%
- UIDAI/NITI row [method: state] area "Koppal": factor "% Population Living in Households with Improved Sanitation" (value 4.74)
- UIDAI/NITI row [method: district] area "Koppal": factor "% Schools with instruction medium 1 (English)" (value 0.24)
- Existing coverage from a previous shallow pass: moderate (8 sources, 5 news items)

### 29-565 | Ballari (and Vijayanagara) | regionId "kalyana-karnataka"
- Casefile secondary dropout rate (LKI-SSM): 24.3%
- Sub-area in the data files: Vijayanagara -- dropout 23.7%
- UIDAI/NITI row [method: state] area "Ballari": factor "% Population Living in Households with Improved Sanitation" (value 4.48)
- UIDAI/NITI row [method: state] area "Vijayanagara": factor "% Population Living in Households with Improved Sanitation" (value 4.37)
- UIDAI/NITI row [method: district] area "Ballari": factor "% Schools with instruction medium 1 (English)" (value 0.11)
- UIDAI/NITI row [method: district] area "Vijayanagara": factor "% Schools with instruction medium 1 (English)" (value 0.18)
- Existing coverage from a previous shallow pass: thin (7 sources, 6 news items)

## 5. Hard rules -- accuracy over volume
- Every claim, number, date and headline must be backed by a page you actually opened. NEVER invent or guess a URL, outlet, date, headline, quote or figure. Do not reconstruct a URL from memory.
- Every `url` must be the canonical, directly openable article/report URL on the publisher's own domain. Never output search-engine, news-aggregator or redirect links (e.g. google.com/url, vertexaisearch.cloud.google.com/grounding-api-redirect, news.google.com/rss, bing.com). If you cannot resolve a source to its real URL, drop that source.
- Be district-specific. A national or statewide statistic may appear only as context in `gaps` or a clearly labelled key fact; never as evidence for a district.
- If two sources disagree (e.g. different SSLC pass rates), report the one from the more authoritative source and note the conflict in `gaps`.
- Paraphrase. Quote at most 12 consecutive words from any source. No markdown formatting inside JSON string values.
- Dates as the source shows them: YYYY-MM-DD, or YYYY-MM, or YYYY; use "" only if truly unknown.
- Be honest about thin coverage: `coverage` is "rich" (several recent district-specific sources with numbers), "moderate", or "thin". Do not pad. Put what you looked for but could not find in `gaps`.
- "Existing coverage" in section 4 tells you what a previous, shallow pass already found. Go beyond it: new sources, newer data, Kannada-language sources, official documents.

## 6. Output format -- follow exactly (I will parse it by machine)
Output ONLY the district blocks below, one per district, in the order of section 4, with no introduction, no summary table, no commentary between blocks and no markdown code fences. Each block is a sentinel line, one valid JSON object, and a closing sentinel line:

=== DISTRICT <districtId> | <District name> | BEGIN ===
{ ...JSON object... }
=== DISTRICT <districtId> | <District name> | END ===

The JSON object for each district:
{
  "districtId": "29-577",
  "name": "Mysuru",
  "regionId": "old-mysuru",
  "researchedOn": "<today, YYYY-MM-DD>",
  "headline": "<= 25 words: the single best-evidenced takeaway for THIS district",
  "summary": "70-110 words synthesising why students leave or stop attending secondary school here, and how strong the evidence is",
  "reasons": [
    { "factor": "<= 6 words", "category": "economic | migration | school-infrastructure | social-norms | gender | health | governance | other",
      "detail": "<= 40 words, specific to this district, paraphrased", "sources": [1, 3], "evidence": "strong | moderate | thin" }
  ],
  "keyFacts": [ { "label": "<= 8 words incl. the year", "value": "figure exactly as the source states it", "sources": [2] } ],
  "headlines": [ { "title": "article title", "outlet": "The Hindu", "date": "2025-06-12", "url": "https://...", "takeaway": "<= 25 words" } ],
  "responses": [ { "text": "<= 30 words: a local programme or official action", "sources": [4] } ],
  "officialFactorCheck": [
    { "factor": "factor name exactly as supplied in section 4", "method": "state | district", "verdict": "supports | contradicts | unclear | no-evidence",
      "note": "<= 35 words", "sources": [2] }
  ],
  "sources": [
    { "id": 1, "url": "https://...", "title": "...", "outlet": "...", "date": "2025-06-12", "type": "news | government | ngo | research | data" }
  ],
  "coverage": "rich | moderate | thin",
  "gaps": "<= 50 words: what you looked for but could not find or verify"
}

Counts per district: reasons 4-6, keyFacts 4-8, headlines 5-10 (newest first; district-specific news only), responses 0-4, sources up to ~15. `sources[].id` are 1-based; every number in a `sources` array must exist; every `headlines[].url` must also appear in `sources`. Use `regionId` exactly as given in section 4.

If you reach an output-length limit mid-way, stop cleanly after a completed END line and I will reply "continue" -- then resume with the next district, repeating nothing.
