# Source library: secondary-school dropout in Karnataka (sources only)

Collected top-down so the dashboard can later be compared against official data. **Nothing here is on the site yet.**

- `sources.json` — every source: url, title, publisher, year, kind, scope, districts, tier, note, and a `check` block.
- `COVERAGE.md` — sources per district and kind, with verification counts.
- `build_library.py` — curates the list and re-verifies every URL (`python3 build_library.py`).
- `indiastat_urls.json` — the per-district IndiaStat dropout-table URLs that resolved (29 of 30; Bengaluru Urban did not).

Tiers: **1** statewide official/data (UDISE+ analyses, ASER district estimates, NFHS-5, CAG audit, parliament answers, IndiaStat tables),
**2** research / NGO / programme evidence (Samata trial, tribal and migrant-children studies, child marriage and labour data),
**3** district news and official drives.

`note` is what the search snippet said the page holds; it is not confirmed from the page. `check.state`:
`verified` (opens, mentions dropouts, names the district where it is district-scoped), `opens, relevance not confirmed`,
`opens (pdf, text not checked)`, `http 403` / `unreachable` (the host blocks automated requests; open by hand).

## Best sources for a numeric comparison with our data
- ASER district estimates for Karnataka (2022 and latest): rural enrolment by district.
- NFHS-5 district factsheet data (data.gov.in): female schooling and child-marriage indicators by district. The per-district PDFs on the IIPS site could not be reached; use the data.gov.in file.
- CAG Report 6 of 2024 (Karnataka): district-wise dropout rate 2021-22 (host unreachable from here; open by hand).
- IndiaStat per-district dropout tables 2013-14 to 2021-22 (a compilation of UDISE data; values not read).

## Known gaps
- No district-specific narrative source was found beyond what the dashboard already holds for Haveri, Raichur, Chitradurga, Davanagere, Tumakuru, Hassan, Chikkaballapur, Ramanagara. Next step there: a deep-research round, or Kannada-language local news.
- Official 2024-25 district-wise out-of-school counts (Samagra Shiksha / PRABANDH) and UDISE+ district report cards were not found; those portals are dynamic or block automated access.
- Karnataka Human Development Report district tables and the Samagra Shiksha PAB minutes for Karnataka were not located.
- Several statewide secondary-dropout figures conflict (22.09%, 22.2%, 18.3%, 18.1%, 14.3%): different years, classes or measures. Check the original UDISE+ report before quoting one.
