You are running as Deep Research. The clarification step is finished: every question you could ask is already answered below. Do not ask me anything and do not propose a plan and wait. Your first action is to start researching; your only output is the final report.

PRE-ANSWERED CLARIFICATIONS
- Scope: only the districts listed in Section C, in Karnataka, India.
- Purpose: a factual knowledge base about the region, to be read by an AI model. Not an essay, not advice, not a summary for a human reader.
- Time frame: latest available data; today is {{AS_OF}}; history only where a topic asks for it.
- Languages and sources: English and Kannada (search in both); the source rules are in Section F.
- Length and depth: the word targets in Section G; when unsure, be more specific rather than longer.
- Format: the exact skeleton in Section G, nothing before or after it.
- Anything else unclear: use your best judgment and record it under REPORT SECTION 0.

FORMAT CONTRACT (overrides your default report style)
1. The first line of your reply is exactly: BEGIN REPORT
2. No title, executive summary, introduction, conclusion, key takeaways, recommendations or closing offer.
3. Use the headings in the Section G skeleton character for character.
4. Profiles are plain prose paragraphs: no bullets, no tables, no bold, no italics, no emojis, no links.
5. Citations are plain-text markers such as [S1][S2]; never your built-in link or chip citations; never markdown link syntax anywhere.
6. Each Sources line ends with the full plain-text URL of a page you actually opened, without tracking parameters.
7. A Profile contains no comment about your research; every gap goes in Annex E only.
8. The last line of your reply is exactly the END OF REPORT line from the Section G skeleton.

# DEEP RESEARCH BRIEF: Regional persona dossier for {{REGION_NAME}}, Karnataka ({{RUN_LABEL}})

## A. How to work

- RUN SCOPE. This run is {{RUN_LABEL}} for {{REGION_NAME}}. Write ONLY: {{PASS_SCOPE}}. Everything else in this brief belongs to another run; do not write, summarise or mention it.
- Do NOT ask me clarifying questions. Where something is ambiguous, choose the most defensible reading, record the assumption in REPORT SECTION 0, and carry on.
- Research each topic separately and in depth. Do not write from general knowledge when a verifiable source exists, and do not stop at the first page of search results. Look for district-level and taluk-level specifics, not only state-level averages.
- Deliver ONE final report covering only RUN SCOPE, in exactly the structure of Section G. Never merge topics, drop a topic or thin out later topics to save space, and never pad: each Profile is as long as its evidence supports, near its word target.
- If you are running out of space, finish the topic you are writing and go straight to the final line. Never compress the remaining topics to make them fit.
- Data you cannot open (dashboards such as UDISE+, scanned or paywalled documents): use the nearest published figure in this order: the same figure quoted in a tier 1-3 report or news story; a division-level or state-level figure; an earlier year. Label its level and year inside the sentence and add one line to Annex E. Do not spend more than a few searches on any single metric, and do not let one missing metric delay the rest of the report.
- Treat today as {{AS_OF}}. "Current" means as of that date. For every time-sensitive fact (schemes, renamings, political events, projects, disasters, statistics) state the year.

## B. Why this exists

An AI model will answer public-policy questions (for example, the reasons for secondary-school dropout in Karnataka) speaking as a resident of {{REGION_NAME}}. Your dossier is the ONLY knowledge it will have about the region: what you leave out it will not know, and what you get wrong it will state confidently. Write what a thoughtful lifelong resident knows, cares about, complains about and is proud of, and what such a person says outsiders get wrong.

Prefer: specific over generic (named places, taluks, institutions, schemes, crops, communities, disputes, dates, numbers); sourced over impressionistic; balanced (problems and internal disagreements as well as pride); regional over statewide (a statewide fact gets one clause; spend the words on how this region differs from the other five).

## C. The region (fixed - do not change this list)

Region: {{REGION_NAME}}
Districts ({{DISTRICT_COUNT}}), exactly these: {{DISTRICT_LIST}}

Rules:
- Use these districts in their current administrative form. Analyse them and only them.
- I have divided Karnataka into six regions. {{REGION_NAME}} is one of them; the other five are: {{PEER_REGIONS}}. Other regions appear in your report only for contrast, for shared rivers or corridors, or for migration flows.
- If a popular or official definition of this region includes districts I have not listed, or omits some of mine, do NOT change my list. Add one short note in REPORT SECTION 0 and keep all analysis on my districts. Where a sub-area of one of my districts is culturally or ecologically part of a different region (for example a hill taluk in a coastal district), cover it and flag it as such.
- In headings, tables and prose use the district names exactly as I list them. If a district has since been officially renamed or reorganised, give the newer official name once in parentheses and keep analysing the same territory. Search under old and new spellings (for example Mysuru/Mysore, Kalaburagi/Gulbarga, Chikkamagaluru/Chikmagalur).
- Where a district has been split or newly created, say so, and where statistics were published only for the parent district, use them and label them ("figure is for undivided X"). Ranks out of the districts are out of 31 for post-2021 sources and out of 30 for older ones.

## D. Region-specific brief

D.1, D.2 and D.4-D.6 apply to your whole run. In D.3 each bold key is a topic key: cover every item under a key that is in RUN SCOPE, under that key, as the highest priority for that topic, and ignore the keys outside RUN SCOPE.

{{REGION_BRIEF}}

## E. Topics

The full dossier has 18 topics, in the order below; this run covers only the topic keys named in RUN SCOPE, in this order. Topic keys and labels are fixed.

Ownership rule. Each fact appears in exactly ONE topic, its owner. Another topic may mention it in at most one clause without repeating the figure. Owners: Census 2011 SC/ST, religion and mother-tongue counts and migration stock: demographics. Caste and community structure, reservation categories, marriage customs: society_communities. Language varieties and language politics (no mother-tongue counts): language. Assembly and Lok Sabha results, MLAs, MPs, reservation agitations: politics_elections. MGNREGA days and wages, PDS, pensions, Jal Jeevan Mission, delivery of the guarantees: welfare_public_services. Shakti's transport impact: transport. Electoral reception of the guarantees: politics_elections. Unemployment, PLFS and MSMEs: economy. Seasonal and distress migration, child labour, occupational wages: labour_migration. Child marriage, teenage pregnancy, ICDS/anganwadi functioning, gender norms: women_children_youth; nutrition outcomes: health. Droughts, floods, groundwater, water disputes, mining and energy installations: environment_water_land (economy keeps only their jobs and revenue; governance keeps only inter-state boundary disputes; agriculture keeps only their effect on crops, income and debt). Farmers' unions: agriculture; their electoral role: politics_elections. Origins of identity movements: history_identity; their electoral role: politics_elections; attitudes to them: worldview_voice. Religious controversies: religion_belief only. Festival dates and places: culture; religious meaning: religion_belief.

Priority rule. The "Must cover" lists are checklists, not quotas. Within the word target, cover items in this order: (1) anything the region brief in Section D assigns to this topic key; (2) the items marked Priority (P) below, which must take at least 60 percent of the Profile's words together with the local causes, constraints and responses connected to them; (3) whatever differs most from the other five regions; (4) district-level facts and numbers, giving every district in my list at least one mention; (5) the remaining list items, one clause each. If space runs out, drop from the bottom of that order, never from the top. A fact earns space only if it could change how a resident explains a public problem.

{{TOPIC_BLOCKS}}

## F. Research method and source standards

Source hierarchy (use in this order; cite only what you actually opened):
1. Official and primary: Census of India 2011 (district census handbooks, primary census abstract), NFHS-5 (2019-21) district fact sheets, UDISE+, Karnataka's own SATS (Student Achievement Tracking System) records, Karnataka Human Development Report, Karnataka Economic Survey and Directorate of Economics and Statistics publications, Department of School Education and Literacy, Department of Agriculture and Horticulture, Karnataka State Disaster Management Authority, NITI Aayog reports, PLFS, NCRB, Election Commission of India results, Karnataka Legislature documents, government orders, budget documents, CAG reports, court judgments, gazetteers.
2. Academic and research-institution work: peer-reviewed journals, EPW, ISEC Bengaluru, IDS, Azim Premji University, IISc, CSDS-Lokniti, IFMR, World Bank and UN agency studies, field ethnographies.
3. Quality journalism: The Hindu, Deccan Herald, The Indian Express, Times of India, Mint, Scroll, The News Minute, and Kannada and regional press (Prajavani, Vijaya Karnataka, Vijayavani, Udayavani, Samyukta Karnataka, Kannada Prabha and local dailies).
4. NGO, foundation and community reports (Azim Premji Foundation, Akshara Foundation, Pratham/ASER, Sikshana, SKDRDP and similar).
5. Wikipedia and travel sites: open them for orientation only; they NEVER appear in a Sources list. YouTube videos, content farms, AI-written aggregator pages, and unsourced social-media posts are not used at all.

Never cite: YouTube or any video, Quora, Reddit, Facebook, Instagram, X/Twitter, Medium or personal blogs, travel, tourism, homestay, hotel or booking pages, business directories, exam-preparation or coaching sites, content farms, AI-generated aggregator pages, or anything without a named publisher and a date. At least half of the sources in each topic must be tier 1 or tier 2. Several outlets repeating one press release or one report count as one source.

Reference vintages, identical for all six regions: population, religion, language, SC/ST and literacy: Census 2011 (still the latest published population census). Health, marriage age and nutrition: NFHS-5 (2019-21) district fact sheets; add NFHS-6 only as a labelled comparison if its district fact sheets are published by {{AS_OF}}. School data: the latest published UDISE+ release, using the same release for every district and naming its year. SSLC and PUC: the five most recent annual results published by {{AS_OF}}, naming the years. Elections: the 2023 Assembly election and the 2024 Lok Sabha election. District GDP: the latest Directorate of Economics and Statistics edition, naming its year. State each vintage you actually used in REPORT SECTION 0; if a required vintage could not be obtained, say so there and in Annex E.

Standards:
- Citation mechanics (these override your default behaviour): do not use your built-in inline citation links, chips or bracket codes anywhere in the report. Cite only with plain-text markers placed before the sentence's full stop, for example "... in 2021 [S3]." Several sources are written adjacent: [S3][S5]; never [S3, S5], [S3-S5] or S3. Never use markdown link syntax [text](url), and never put a domain name in brackets or parentheses. URLs appear only in Sources lines, as plain text. REPORT SECTION 1 and the annexes carry no [S#] markers, except the cell markers Annex A specifies.
- Because the [S#] markers are deleted before the text is used, EVERY number must also name its source and year in words inside the sentence (for example "NFHS-5 (2019-21) records ...", "UDISE+ 2023-24 shows ...").
- Comparators: for every headline indicator give (i) the value by district, or the range with the highest and lowest districts named if the pattern is clearer that way, (ii) the Karnataka value for the same year and source, and (iii) where the source publishes it, the district rank. Example: "Raichur has the highest Class 9-10 dropout rate of the 31 districts (x percent) against the state figure of y percent (UDISE+ <year>)." Never call a district high, low, better or worse without a number and a comparator.
- Put in a Profile only claims that a tier 1-3 source states explicitly. A claim that rests only on a tier 4 source, or on a source you could not open, stays OUT of the Profile and goes to Annex E as "UNVERIFIED [topic_key]: <claim> | <source>".
- If sources conflict, state both figures neutrally in the Profile with their sources and years (for example "Census 2011 records X [S2]; NFHS-5 (2019-21) reports Y [S3]"). Put your view of which is more reliable in Annex E.
- Prefer the latest data and give its year. If district-level data do not exist, give the nearest available level in the Profile, labelled by level and year (for example "Karnataka-wide, 2021: ..."), and log the missing figure in Annex E. NEVER fabricate, interpolate or round to a plausible number, and never invent quotes, events, place names or people.
- Search in Kannada as well as English (use Kannada-script and transliterated search terms). A large share of regional detail exists only in Kannada-language reporting and government documents.
- In Profiles use Roman transliteration only for Kannada, Tulu, Konkani, Urdu and other local words, glossed at first use. Other scripts appear only in Annex D and in your own search terms.

## G. Output format (strict, so it can be converted mechanically to structured data)

The first line of your reply is exactly BEGIN REPORT. Then use this skeleton, keeping only the parts named in RUN SCOPE, with the heading lines character for character (same capitalisation, one space either side of the pipe, no numbering, no emoji, flush-left):

```
{{SKELETON}}
```

The example values under the first topic (Example Title, example.org) show layout only; never reuse them. Every topic has both "### Profile" and "### Sources", even if the Sources list is short.

REPORT SECTION 0: short bullets: assumptions, boundary notes, the data vintages you used, and anything ambiguous you resolved.
{{SECTION1_SPEC}}Sources lines: one line per source, in the form "- [S1] Title | Publisher | Year | URL". Number sources in order of first citation within the topic; every [S#] used in the Profile has a line and every line is cited at least once; a source used in several topics is listed again in each of them. URL is plain text beginning https://, the exact page or document you opened (not a homepage, not a search-results or redirect link, not a shortened link), with no tracking parameters (delete ?utm_source=chatgpt.com and anything like it). Title is the page or document title in full, with any "|" replaced by "-" and any double quote removed. Year is four digits, or n.d. if the document shows no date. Publisher is the organisation, not the domain. Aim for at least 6 (Part A) or 4 (Part B) sources per topic, but list ONLY pages or documents you actually opened in this run. If fewer real sources exist, list fewer and add "SOURCES SHORT [topic_key]: n listed" to Annex E. Never construct a URL from memory or from a URL pattern; a shorter list of real URLs is better than a full list with one invented URL.

{{ANNEX_SPEC}}

Profile rules:
- Length is a target, not a range: the word target given for each topic in Section E, plus or minus 10 percent. If you have more material, keep the most decision-relevant and drop the rest; if you have less, do not pad.
- Paragraph scaffold. Every Profile has this paragraph structure and no other, one blank line between paragraphs, no labels: P1 SIGNATURE (60-100 words, self-contained, begins with the region name): the 3-5 facts about this topic that most distinguish this region from the rest of Karnataka and would most change how a resident explains a public problem, each with number, year and place. P2 DRIVERS AND PROBLEMS: region-specific constraints, failures, disputes and their local causes, with named places. P3 SYSTEM AND INDICATORS: how the sector or institution is organised here, with district figures and the state comparator. P4 ASSETS AND RESPONSES: what works, local institutions, and what residents, officials, NGOs or studies say should be done, attributed; end with one or two sentences on how residents, local institutions or documented local movements frame the main problem in this topic and what they demand, attributed to a source (omit these sentences if no source documents such a framing). P5 (optional) DISTINCTIVE LOCAL DETAIL. Education may use up to 7 paragraphs. Order paragraphs by decreasing importance so that no paragraph depends on a later one and the Profile can be cut at any paragraph boundary. Do not repeat the signature text later.
- Plain prose only: no bullet lists, no tables, no bold, no italics, no headings, no links, no emoji. District figures go INTO the prose, grouped by pattern, in sentence form, for example: "Class 9-10 dropout is highest in <District> (a percent) and <District> (b percent) and lowest in <District> (c percent), against a Karnataka figure of d percent (UDISE+ <year>)."
- Cover districts by exception: state the region-wide pattern first, then name only the districts that depart from it, at most three per sentence; do not give each district its own sentence. Every district must appear at least once in every Part A Profile. In Part B Profiles name districts wherever the topic differs by district.
- Quantitative facts (a number with its year and source name counts as one): Part A Profiles 14-22; Part B Profiles 6-12; culture, history_identity, language and religion_belief 4-8.
- Every Profile contains both region-specific constraints or failures and working assets, schemes or sources of pride, each between 30 and 70 percent of its sentences. Use neutral verbs and describe outcomes with numbers, not adjectives. Avoid promotional words such as magnificent, pristine, vibrant, lush, breathtaking, rich tapestry, rich heritage.
- Write neutral, third-person prose: present tense for current conditions, past tense for historical events, and always the year for time-sensitive facts.
- A Profile never contains any of these (any capitalisation): "source document", "the sources", "provided sources", "this report", "this dossier", "my research", "could not find", "was not found", "no information", "no data", "not available", "not covered", "coverage is limited", "limited data", "beyond the scope", "further research", "unverified", "n/a", "Annex", "Section", or the words I, we, my, our. State an absence only as a fact about the region ("Kodagu has no railway line"), never as a gap in your knowledge.

The last line of your reply, with nothing after it, is exactly: END OF REPORT | {{RUN_LABEL}} | TOPICS DELIVERED: <comma-separated topic keys, in order>

## H. Guardrails

- Describe communities by what credible data and sources show and by how communities describe themselves. Never assert innate or essential traits of a caste, religion, tribe or gender. Use attributed phrasing ("surveys report ...", "residents commonly say ...").
- Show internal diversity: rural versus urban, coast versus hills, rich versus poor, men versus women, dominant versus marginalised communities. The region is not monolithic.
- On politically or religiously contested matters, present the main competing positions and who holds them, with sources, and take no side.
- Never name a private individual: anyone who does not hold a public office or a publicly documented public role (a student, farmer, victim, complainant or accused person in a news story counts as private). Public figures (elected representatives, officials, writers, artists, athletes, seers, heads of organisations) may be named only in their public role.
- No invented statistics, quotes, events or people. When unsure, leave it out and record it in Annex E.

## I. Final check (apply while writing; do not print this list)

Before each topic: is the heading exact? After each topic: does every [S#] have a Sources line and every Sources line a [S#]; is the Profile free of bullets and research-limit phrases; are my districts named? Before the last line: is every topic in RUN SCOPE present, in order; does any Sources list contain Wikipedia, a travel site, YouTube, a content farm or an aggregator page? Finally re-read the FORMAT CONTRACT: your reply must start with BEGIN REPORT and end with the END OF REPORT line.
