# TASK: District-by-district research on secondary-school dropout in Karnataka (15 districts)

You are running as ChatGPT Deep Research. I have pre-answered every clarifying question below -- do NOT ask me
questions and do NOT propose a plan for approval; start researching immediately.

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
### 29-572 | Bengaluru Urban | regionId "old-mysuru"
- Casefile dropout rate: reported only for sub-areas (below)
- Sub-area in the data files: Bengaluru U North -- dropout 7.3%
- Sub-area in the data files: Bengaluru U South -- dropout 12.5%
- UIDAI/NITI row [method: state] area "Bengaluru U North": factor "% Population Living in Households with Improved Sanitation" (value 1.35)
- UIDAI/NITI row [method: state] area "Bengaluru U South": factor "% Population Living in Households with Improved Sanitation" (value 2.3)
- UIDAI/NITI row [method: district] area "Bengaluru U North": factor "% Schools with Functional Protected Well" (value 0.02)
- UIDAI/NITI row [method: district] area "Bengaluru U South": factor "% Schools with Functional Protected Well" (value 0.05)
- Existing coverage from a previous shallow pass: moderate (6 sources, 5 news items)

### 29-583 | Bengaluru Rural | regionId "old-mysuru"
- Casefile secondary dropout rate (LKI-SSM): 14.8%
- UIDAI/NITI row [method: state] area "Bengaluru Rural": factor "% Population Living in Households with Improved Sanitation" (value 2.73)
- UIDAI/NITI row [method: district] area "Bengaluru Rural": factor "% Schools with instruction medium 1 (English)" (value 0.1)
- Existing coverage from a previous shallow pass: thin (3 sources, 3 news items)

### 29-584 | Ramanagara | regionId "old-mysuru"
- Casefile secondary dropout rate (LKI-SSM): 24.7%
- UIDAI/NITI row [method: state] area "Ramanagara": factor "% Population Living in Households with Improved Sanitation" (value 4.55)
- UIDAI/NITI row [method: district] area "Ramanagara": factor "% Schools with instruction medium 1 (English)" (value 0.19)
- Existing coverage from a previous shallow pass: thin (5 sources, 4 news items)

### 29-573 | Mandya | regionId "old-mysuru"
- Casefile secondary dropout rate (LKI-SSM): 20.7%
- UIDAI/NITI row [method: state] area "Mandya": factor "% Population Living in Households with Improved Sanitation" (value 3.81)
- UIDAI/NITI row [method: district] area "Mandya": factor "% Schools with instruction medium 1 (English)" (value 0.22)
- Existing coverage from a previous shallow pass: thin (4 sources, 4 news items)

### 29-577 | Mysuru | regionId "old-mysuru"
- Casefile secondary dropout rate (LKI-SSM): 11.5%
- UIDAI/NITI row [method: state] area "Mysuru": factor "% Population Living in Households with Improved Sanitation" (value 2.12)
- UIDAI/NITI row [method: district] area "Mysuru": factor "% Schools with Functional Protected Well" (value 0.07)
- Existing coverage from a previous shallow pass: moderate (7 sources, 7 news items)

### 29-578 | Chamarajanagara | regionId "old-mysuru"
- Casefile secondary dropout rate (LKI-SSM): 23.2%
- UIDAI/NITI row [method: state] area "Chamarajanagara": factor "% Population Living in Households with Improved Sanitation" (value 4.28)
- UIDAI/NITI row [method: district] area "Chamarajanagara": factor "% Schools with instruction medium 1 (English)" (value 0.25)
- Existing coverage from a previous shallow pass: moderate (5 sources, 5 news items)

### 29-582 | Chikkaballapur | regionId "bayaluseeme"
- Casefile secondary dropout rate (LKI-SSM): 15.8%
- UIDAI/NITI row [method: state] area "Chikkaballapura": factor "% Population Living in Households with Improved Sanitation" (value 2.91)
- UIDAI/NITI row [method: district] area "Chikkaballapura": factor "% Schools with instruction medium 1 (English)" (value 0.16)
- Existing coverage from a previous shallow pass: thin (4 sources, 3 news items)

### 29-581 | Kolar | regionId "bayaluseeme"
- Casefile secondary dropout rate (LKI-SSM): 22.1%
- UIDAI/NITI row [method: state] area "Kolar": factor "% Population Living in Households with Improved Sanitation" (value 4.07)
- UIDAI/NITI row [method: district] area "Kolar": factor "% Schools with instruction medium 1 (English)" (value 0.16)
- Existing coverage from a previous shallow pass: thin (4 sources, 3 news items)

### 29-571 | Tumakuru | regionId "bayaluseeme"
- Casefile secondary dropout rate (LKI-SSM): 19.4%
- Sub-area in the data files: Tumakuru Madhugiri -- dropout 27.3%
- UIDAI/NITI row [method: state] area "Tumakuru": factor "% Population Living in Households with Improved Sanitation" (value 3.58)
- UIDAI/NITI row [method: state] area "Tumakuru Madhugiri": factor "% Population Living in Households with Improved Sanitation" (value 5.03)
- UIDAI/NITI row [method: district] area "Tumakuru": factor "% Schools with instruction medium 1 (English)" (value 0.2)
- UIDAI/NITI row [method: district] area "Tumakuru Madhugiri": factor "% Schools with instruction medium 1 (English)" (value 0.32)
- Existing coverage from a previous shallow pass: thin (5 sources, 3 news items)

### 29-567 | Davanagere | regionId "bayaluseeme"
- Casefile secondary dropout rate (LKI-SSM): 11.8%
- UIDAI/NITI row [method: state] area "Davanagere": factor "% Population Living in Households with Improved Sanitation" (value 2.17)
- UIDAI/NITI row [method: district] area "Davanagere": factor "% Schools with instruction medium 1 (English)" (value 0.07)
- Existing coverage from a previous shallow pass: thin (5 sources, 3 news items)

### 29-566 | Chitradurga | regionId "bayaluseeme"
- Casefile secondary dropout rate (LKI-SSM): 24.3%
- UIDAI/NITI row [method: state] area "Chitradurga": factor "% Population Living in Households with Improved Sanitation" (value 4.48)
- UIDAI/NITI row [method: district] area "Chitradurga": factor "% Schools with instruction medium 1 (English)" (value 0.29)
- Existing coverage from a previous shallow pass: thin (6 sources, 5 news items)

### 29-568 | Shivamogga | regionId "malnad"
- Casefile secondary dropout rate (LKI-SSM): 12.9%
- UIDAI/NITI row [method: state] area "Shivamogga": factor "% Population Living in Households with Improved Sanitation" (value 2.38)
- UIDAI/NITI row [method: district] area "Shivamogga": factor "% Schools with instruction medium 1 (English)" (value 0.13)
- Existing coverage from a previous shallow pass: moderate (4 sources, 4 news items)

### 29-570 | Chikkamagaluru | regionId "malnad"
- Casefile secondary dropout rate (LKI-SSM): 19.6%
- UIDAI/NITI row [method: state] area "Chikkamangaluru": factor "% Population Living in Households with Improved Sanitation" (value 3.61)
- UIDAI/NITI row [method: district] area "Chikkamangaluru": factor "% Schools with instruction medium 1 (English)" (value 0.2)
- Existing coverage from a previous shallow pass: thin (3 sources, 3 news items)

### 29-576 | Kodagu | regionId "malnad"
- Casefile secondary dropout rate (LKI-SSM): 14.2%
- UIDAI/NITI row [method: state] area "Kodagu": factor "% Population Living in Households with Improved Sanitation" (value 2.62)
- UIDAI/NITI row [method: district] area "Kodagu": factor "% Schools with instruction medium 1 (English)" (value 0.08)
- Existing coverage from a previous shallow pass: thin (5 sources, 5 news items)

### 29-574 | Hassan | regionId "malnad"
- Casefile secondary dropout rate (LKI-SSM): 15.8%
- UIDAI/NITI row [method: state] area "Hassan": factor "% Population Living in Households with Improved Sanitation" (value 2.91)
- UIDAI/NITI row [method: district] area "Hassan": factor "% Schools with instruction medium 1 (English)" (value 0.16)
- Existing coverage from a previous shallow pass: thin (3 sources, 3 news items)

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
