# Check of the two thin-district reports (research1, research2)

Files: `responses/thin-research1-unsourced.txt`, `responses/thin-research2-unsourced.txt` (copies of the deep-research output).

**Neither report contains a single URL**, and neither follows the JSON block format, so nothing in them can be ingested or page-verified as written.
They were treated as leads. The factor values they quote (sanitation, English-medium) do match our data. Everything else was unsourced.

## Claims I tried to confirm (web search, then fetched the page and looked for the numbers)

| District | Claim (which report) | Result |
|---|---|---|
| Davanagere | 25 of 26 child marriages stopped Apr-May 2024; 194 prevented the year before (R2) | **Confirmed** on two pages (ETV Bharat, News Karnataka). The 194 is for 2023. These count marriages stopped; they are not dropout figures. |
| Tumakuru | 33 child labourers rescued from 660 premises (R2) | **Confirmed** (News Karnataka, statewide police drive; "660" appears only there). |
| Ramanagara | School mergers into Karnataka Public Schools; child-rights commission suo motu (R2) | **Partly.** The commission's suo motu complaint on closures/mergers is confirmed (Deccan Herald). Nothing found on Ramanagara specifically, the 6 km distance, or "87 of 97 weddings stopped". |
| Chitradurga | 38 girls moved out of a mutt hostel to Morarji schools (R2) | **Not supported.** The Murugha Matha case is real, but coverage gives about 80 to 106 girls, not 38. |
| Raichur | Hybrid cotton seed child labour; vehicles stopped, children rescued (both) | **Partly.** A 2020 raid (27 children, nine vehicles) exists in a search snippet (page did not open); general cottonseed child-labour sources exist. The Rs 50-70 wage, granite mines "1 in 10", and "4,256 rescued" were not found. |
| Haveri | 42 teenage pregnancies in 2025-26 (R2) | **Not found.** A Deccan Herald report instead gives 58 pregnancies among 129 POCSO cases in Haveri (2024-25); a different measure. |
| Hassan | Teenage boys leaving school for Mumbai bakery work (R2) | **Not found.** |
| Chikkaballapur | 1,242 of 1,528 villages declared child-marriage free (R2) | **Not found.** Only a January 2025 report of a 15-year-old forced into marriage turned up. |

Not checked (no time or no search path): Chitradurga Ganga Kalyana "30% less migration", Davanagere 1,447 dropouts and the Dalit-student assault, Hassan 1,819 out-of-school (older survey), Tumakuru school-roof collapses and hostel poisoning, Chikkaballapur POCSO "eight times" and Bhagyalakshmi analysis, Ramanagara sericulture child labour and dyslexia dropouts, SSLC ranks and pass rates.

## The two reports contradict each other
- **Haveri:** R1 says infrastructure shortage and farm labour drive dropout; R2 says underage marriage and teenage pregnancy. Neither is sourced.
- **Chikkaballapur:** R1 says distance, unsafe transport and high POCSO incidence; R2 says a successful turnaround with most villages child-marriage free.
- **Raichur SSLC:** R1 says "lowest in state" and also gives 85.06% for 2026 and 52.05% for 2025; R2 says 52.05% (2025), 32nd of 35.
- **Verdicts:** R1 labels most factor rows "no evidence" and Davanagere "unclear"; R2 says "no evidence" throughout.

## What this means
- Keep the confirmed items as sources (added to `source-library/sources.json`): Davanagere (2), Tumakuru, KSCPCR closures, Murugha Matha, Raichur raid (snippet only).
- Do not put the unconfirmed figures on the dashboard or in the chat.
- To use the rest, ask the researcher for the **source URL behind each claim** (the sentinel JSON format with a `sources` list), or run the claims through `ingest_why.py`-style page verification once URLs exist.
