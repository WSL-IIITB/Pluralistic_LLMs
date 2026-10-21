# TASK: Why is each district's dominant factor dominant? (8 Karnataka districts)

You are running as Gemini Deep Research. Do NOT ask me to confirm or edit the research plan -- treat the plan as
approved and start researching immediately. Put the complete deliverable in the final report text itself (not in a
linked document, canvas or table-only summary).

## 1. Context (pre-answered -- do NOT ask me questions)
- Topic (fixed): **secondary-school dropout in Karnataka -- Classes 8-10 / SSLC**, i.e. why students leave or stop attending.
- Geography: ONLY the 8 districts in section 3, each treated separately.
- I have two official-statistics files (UIDAI / NITI Aayog based) that name, for every district, the factor statistically most associated with its secondary dropout rate:
  - `method: state` -- the same factor ranks first for the whole state (here: household sanitation), paired with this district's own figure.
  - `method: district` -- a factor chosen for this district (for example, share of schools with English as the medium of instruction, or schools with a protected well).
- Do NOT reinterpret the numeric values; I could not verify what they measure. Do not present them as findings.
- Prefer 2022-2026 evidence; say the year of anything older. Search in English AND Kannada (Prajavani, Vijay Karnataka, Udayavani, Kannada Prabha, Samyukta Karnataka, TV9 Kannada, district editions of The Hindu / Deccan Herald / Times of India), plus official data (Samagra Shiksha Karnataka, DSERT, KSEAB, UDISE+, district statistical handbooks, High Court / Commission for Protection of Child Rights orders) and NGO or academic research (Pratham ASER, Azim Premji Foundation, CRY, UNICEF, peer-reviewed papers).

## 2. The question to answer, for EVERY factor row of EVERY district
> I found that this factor is the dominant factor for school dropouts in this district. Can you say why and provide some proof for it?

Answer it honestly. The factor was selected by a statistical method, not by field research, so it may or may not be backed by evidence you can find. "Not supported" and "no evidence" are perfectly good answers -- an invented explanation is the worst answer.

For each factor row give:
1. A **verdict**:
   - `supported` -- at least one source about THIS district (or a sub-area of it) links the factor to students leaving school.
   - `partly` -- no direct local link, but local conditions (district data, news) fit a mechanism that credible research documents elsewhere.
   - `not-supported` -- local evidence points the other way (e.g. the problem the factor describes is absent or already fixed here).
   - `no-evidence` -- you looked and found nothing useful either way.
2. **why** (<= 80 words): the reasoning, in plain language, for why this factor would drive dropout in this district -- or why you could not establish it.
3. **mechanism** (<= 40 words): the causal route in general terms (e.g. "no school toilets -> girls stay home once menstruating -> irregular attendance -> exit"). Mark it as general, not local.
4. **proof**: 0-5 items. Each has `scope` = `district` (a source about this district) or `general` (research or data from elsewhere that documents the mechanism), a paraphrased `claim` (<= 40 words), `sources` (ids), and optionally a `quote` of at most 12 consecutive words. NEVER present a `general` item as local proof; never put a statewide or national number under `scope: district`.

## 3. The 8 districts (project data -- background only, never cite it as a source)
### 29-571 | Tumakuru | regionId "bayaluseeme"
- Casefile secondary dropout rate: 19.4%
- Sub-area in the data files: Tumakuru Madhugiri -- dropout 27.3%
- Factor row [method: state] area "Tumakuru": factor "% Population Living in Households with Improved Sanitation" (value 3.58)
- Factor row [method: state] area "Tumakuru Madhugiri": factor "% Population Living in Households with Improved Sanitation" (value 5.03)
- Factor row [method: district] area "Tumakuru": factor "% Schools with instruction medium 1 (English)" (value 0.2)
- Factor row [method: district] area "Tumakuru Madhugiri": factor "% Schools with instruction medium 1 (English)" (value 0.32)

### 29-567 | Davanagere | regionId "bayaluseeme"
- Casefile secondary dropout rate: 11.8%
- Factor row [method: state] area "Davanagere": factor "% Population Living in Households with Improved Sanitation" (value 2.17)
- Factor row [method: district] area "Davanagere": factor "% Schools with instruction medium 1 (English)" (value 0.07)

### 29-566 | Chitradurga | regionId "bayaluseeme"
- Casefile secondary dropout rate: 24.3%
- Factor row [method: state] area "Chitradurga": factor "% Population Living in Households with Improved Sanitation" (value 4.48)
- Factor row [method: district] area "Chitradurga": factor "% Schools with instruction medium 1 (English)" (value 0.29)

### 29-575 | Dakshina Kannada | regionId "karavali"
- Casefile secondary dropout rate: 1.2%
- Factor row [method: state] area "Dakshina Kannada": factor "% Population Living in Households with Improved Sanitation" (value 0.22)
- Factor row [method: district] area "Dakshina Kannada": factor "% Schools with instruction medium 1 (English)" (value 0.01)

### 29-569 | Udupi | regionId "karavali"
- Casefile secondary dropout rate: 1.4%
- Factor row [method: state] area "Udupi": factor "% Population Living in Households with Improved Sanitation" (value 0.26)
- Factor row [method: district] area "Udupi": factor "% Schools with instruction medium 1 (English)" (value 0.01)

### 29-563 | Uttara Kannada | regionId "karavali"
- Casefile secondary dropout rate: 12.5%
- Sub-area in the data files: Uttara Kannada Sirsi -- dropout 17.2%
- Factor row [method: state] area "Uttara Kannada": factor "% Population Living in Households with Improved Sanitation" (value 2.3)
- Factor row [method: state] area "Uttara Kannada Sirsi": factor "% Population Living in Households with Improved Sanitation" (value 3.17)
- Factor row [method: district] area "Uttara Kannada": factor "% Schools with instruction medium 1 (English)" (value 0.14)
- Factor row [method: district] area "Uttara Kannada Sirsi": factor "% Schools with instruction medium 1 (English)" (value 0.35)

### 29-568 | Shivamogga | regionId "malnad"
- Casefile secondary dropout rate: 12.9%
- Factor row [method: state] area "Shivamogga": factor "% Population Living in Households with Improved Sanitation" (value 2.38)
- Factor row [method: district] area "Shivamogga": factor "% Schools with instruction medium 1 (English)" (value 0.13)

### 29-570 | Chikkamagaluru | regionId "malnad"
- Casefile secondary dropout rate: 19.6%
- Factor row [method: state] area "Chikkamangaluru": factor "% Population Living in Households with Improved Sanitation" (value 3.61)
- Factor row [method: district] area "Chikkamangaluru": factor "% Schools with instruction medium 1 (English)" (value 0.2)

## 4. Hard rules -- accuracy over volume
- Every claim, number, date and quote must come from a page you actually opened. NEVER invent or guess a URL, outlet, date, headline, quote or figure.
- Every `url` must be the canonical, directly openable page on the publisher's own domain. No search-engine, aggregator or redirect links (google.com/url, vertexaisearch.cloud.google.com/grounding-api-redirect, news.google.com, bing.com). If you cannot resolve a source to its real URL, drop it.
- A source supports a district only if it names that district (or a taluk or town in it). Do not borrow evidence from a neighbouring district.
- If you cannot find proof, say so in `why`, give verdict `no-evidence` or `partly`, and keep `proof` short or empty. Do not pad.
- Paraphrase. No markdown inside JSON string values. Dates as YYYY-MM-DD, YYYY-MM or YYYY ("" if unknown).
- Where a district has sub-area rows (e.g. "Belagavi Chikkodi"), they belong to that district: name the sub-area in `why`.

## 5. Output format -- follow exactly (I parse it by machine)
Output ONLY the district blocks, one per district in the order of section 3, with no introduction, summary table, commentary or markdown code fences. Each block is a sentinel line, one valid JSON object, and a closing sentinel line:

=== DISTRICT <districtId> | <District name> | BEGIN ===
{ ...JSON object... }
=== DISTRICT <districtId> | <District name> | END ===

JSON object:
{
  "districtId": "29-577",
  "name": "Mysuru",
  "regionId": "old-mysuru",
  "researchedOn": "<today, YYYY-MM-DD>",
  "dominantFactorWhy": [
    { "factor": "factor name exactly as supplied in section 3", "method": "state | district", "area": "area name exactly as supplied",
      "verdict": "supported | partly | not-supported | no-evidence",
      "why": "<= 80 words", "mechanism": "<= 40 words, general",
      "proof": [ { "scope": "district | general", "claim": "<= 40 words", "quote": "<= 12 words or empty", "sources": [1] } ] }
  ],
  "sources": [
    { "id": 1, "url": "https://...", "title": "...", "outlet": "...", "date": "2025-06-12", "type": "news | government | ngo | research | data" }
  ],
  "gaps": "<= 50 words: what you looked for but could not find"
}

One `dominantFactorWhy` entry per factor row in section 3 (normally two per district). `sources[].id` are 1-based and every number in a `sources` array must exist.

If you reach an output-length limit mid-way, stop cleanly after a completed END line and I will reply "continue" -- then resume with the next district, repeating nothing.
