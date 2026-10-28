"""
Builds the district source library for secondary-school dropout in Karnataka (sources only, not yet on the site).

    python3 build_library.py            # curate + verify every URL -> sources.json, COVERAGE.md

Every URL below appeared in a web-search result (found_via says which query/tier). Nothing is written from
memory. `note` is what the search snippet said the page contains: it is NOT confirmed from the page unless
`check.reads_dropout` is true. The verification pass fetches each URL and records whether it opens, whether
it mentions dropouts / out-of-school children, and (district-scoped sources) whether it names the district.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from build_converted import ALIASES  # noqa: E402
from build_prompts import NAMES  # noqa: E402

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
ALL = "all"
D = {n.split(" (")[0]: i for i, n in NAMES.items()}  # "Belagavi" -> "29-555"


def d(*names: str) -> list[str]:
    return [D[n] for n in names]


# (url, title, publisher, year, kind, scope, districts, tier, note)
S = [
    # ---- Tier 1: statewide official data and reports -------------------------------------------------
    ("https://saiindia.gov.in/uploads/download_audit_report/2024/Report-No.-6,-2024,-Karnataka-06a2bcfb2a0b281.70901985.pdf",
     "CAG Report No. 6 of 2024, Karnataka (school education)", "Comptroller & Auditor General", "2024", "official-report", "statewide", ALL, 1,
     "Has a section on out-of-school children and, per the snippet, an appendix (2.2) with district-wise dropout rate for 2021-22."),
    ("https://www.deccanherald.com/india/karnataka/34000-children-out-of-school-in-karnataka-6000-in-bbmp-limits-1046869.html",
     "34,000 children out of school in Karnataka, 6,000 in BBMP limits", "Deccan Herald", "2021", "news", "statewide", d("Bidar", "Udupi", "Bengaluru Urban"), 1,
     "Samagra Shikshana Karnataka door-to-door survey: 34,411 out of school; Bidar 2,609 (highest after BBMP), Udupi 172 (lowest); reasons health, finances, family."),
    ("https://deccanherald.com/opinion/editorial/rise-school-drop-outs-worrying-717277.html",
     "Rise in school drop-outs worrying (editorial)", "Deccan Herald", "2019", "news", "statewide", d("Ballari", "Vijayapura", "Kalaburagi", "Yadgir"), 1,
     "State survey counted 70,116 out-of-school children in 2018-19 (14,000 the year before; age cover widened); migration and disinterest cited; district counts include Ballari 5,132 and Vijayapura 4,417."),
    ("https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fat-222-school-dropout-rate-in-karnataka-much-above-natl-avg-3592712",
     "At 22.2%, school dropout rate in Karnataka much above national average", "Deccan Herald", "2025", "news", "statewide", ALL, 1,
     "Samagra Shiksha 2025-26 review: Karnataka secondary dropout 22.2% (2023-24) vs 14.1% national; Ministry asked high-burden states to run door-to-door surveys."),
    ("https://www.thenewsminute.com/karnataka/karnataka-records-high-dropout-rate-in-secondary-schools-udise-data",
     "Karnataka records high dropout rate in secondary schools: UDISE data", "The News Minute", "2025", "news", "statewide", ALL, 1,
     "UDISE+ 2023-24: Karnataka secondary dropout 22.09% vs 14.1% national."),
    ("https://educationforallinindia.com/progress-in-retention-amid-persistent-challenges-analysis-based-on-udise-2025-26/",
     "Progress in retention amid persistent challenges (UDISE+ 2025-26)", "Education For All in India", "2026", "analysis", "statewide", ALL, 1,
     "State-wise retention/dropout analysis of UDISE+ 2025-26."),
    ("https://educationforallinindia.com/state-wise-analysis-of-sdg-4-education-indicators-in-india-2024-25-by-aruncmehta/",
     "State-wise analysis of SDG 4 education indicators in India (2024-25)", "Education For All in India", "2025", "analysis", "statewide", ALL, 1,
     "UDISE+ 2024-25 state table; Karnataka secondary dropout shown as 18.3% (column headers unclear in snippet)."),
    ("https://educationforallinindia.com/?p=14274",
     "Number of dropped-out children based on UDISE+ 2022-23 and 2023-24 data", "Education For All in India", "2024", "analysis", "statewide", ALL, 1,
     "State-wise counts of dropped-out children from UDISE+."),
    ("https://educationforallinindia.com/wp-content/uploads/2023/08/out-of-school-children-UDISEPlus-2021-22-ArunCMehta.pdf",
     "Out-of-school children, UDISE+ 2021-22", "Education For All in India", "2023", "analysis", "statewide", ALL, 1,
     "UDISE+ based out-of-school children estimates by state."),
    ("https://www.deccanherald.com/india/govt-hails-fall-in-girls-dropout-rates-raises-concern-for-boys-3841967",
     "Govt hails fall in girls' dropout rates, raises concern for boys", "Deccan Herald", "2026", "news", "statewide", ALL, 1,
     "UDISE+ 2025-26: girls' secondary dropout down from 19.6% (2023-24); boys' rate a concern."),
    ("https://www.deccanherald.com/india/karnataka/more-teachers-lower-enrolment-how-karnataka-schools-fared-in-udise-2025-26-data-4066244",
     "More teachers, lower enrolment: how Karnataka schools fared in UDISE+ 2025-26", "Deccan Herald", "2026", "news", "statewide", ALL, 1,
     "UDISE+ 2025-26 Karnataka summary: secondary dropout 18.1% (highest among states, per snippet), GER figures."),
    ("https://www.drishtiias.com/state-pcs-current-affairs/karnataka-records-highest-dropout-rate-among-boys-at-secondary-level/print_manually",
     "Karnataka records highest dropout rate among boys at secondary level", "Drishti IAS", "2026", "aggregator", "statewide", ALL, 1,
     "Summary of UDISE+ 2025-26: boys' secondary dropout 18.1%, overall 14.3% (figures conflict with other outlets; check original)."),
    ("https://eparlib.sansad.in/bitstream/123456789/2988252/1/AU969_BxOT3C.pdf",
     "Lok Sabha answer AU969 (school dropouts)", "Parliament of India", "2025", "parliament", "statewide", ALL, 1,
     "State-wise dropout data in a parliamentary answer (content not read)."),
    ("https://eparlib.sansad.in/bitstream/123456789/2988976/1/AU176_2TtAMH.pdf",
     "Lok Sabha answer AU176 (out-of-school children survey, PRABANDH)", "Parliament of India", "2025", "parliament", "statewide", ALL, 1,
     "States asked to run annual household surveys to identify out-of-school children; tracked on PRABANDH."),
    ("https://eparlib.sansad.in/bitstream/123456789/2989089/1/AU101_9ISW0K.pdf",
     "Lok Sabha answer AU101 (out-of-school children)", "Parliament of India", "2025", "parliament", "statewide", ALL, 1,
     "Parliamentary answer on out-of-school children/dropouts (content not read)."),
    ("https://img.asercentre.org/docs/ASER%202022%20report%20pdfs/District%20estimates/karnataka.pdf",
     "ASER 2022 Karnataka district estimates", "ASER Centre (Pratham)", "2022", "survey-data", "statewide", ALL, 1,
     "District-wise rural estimates incl. share of 6-14 not enrolled and school type, for Karnataka districts."),
    ("https://asercentre.org/wp-content/uploads/2022/12/Karnataka_District-Estimates.pdf",
     "ASER Karnataka district estimates (latest edition)", "ASER Centre (Pratham)", "2024", "survey-data", "statewide", ALL, 1,
     "District-wise rural enrolment estimates; e.g. Bagalkot shows 0.5% of 6-14 not in school (column reading unconfirmed)."),
    ("https://asercentre.org/wp-content/uploads/2022/12/ASER-2024-All-India-ppt-Jan-27-11am.pdf",
     "ASER 2024 all-India release", "ASER Centre (Pratham)", "2025", "survey-data", "statewide", ALL, 1,
     "National context: 15-16-year-olds out of school fell from 16.6% (2014) to 7.9% (2024); girls remain above 10%."),
    ("https://dhsprogram.com/pubs/pdf/FR374/FR374_Karnataka.pdf",
     "NFHS-5 Karnataka state report (2019-21)", "IIPS / DHS Program", "2021", "survey-data", "statewide", ALL, 1,
     "Fieldwork in all 30 districts; state tables on schooling, child marriage and adolescent girls."),
    ("https://www.data.gov.in/catalog/national-family-health-survey-5-nfhs-5-india-districts-factsheet-data-provisional",
     "NFHS-5 India districts factsheet data (provisional)", "Open Government Data (data.gov.in)", "2021", "data-portal", "statewide", ALL, 1,
     "Bulk district factsheet data; filter to Karnataka for female schooling and child-marriage indicators."),
    ("https://www.data.gov.in/resource/india-districts-factsheets-national-family-health-survey-nfhs-5-2019-2021",
     "India districts factsheets, NFHS-5 2019-2021", "Open Government Data (data.gov.in)", "2021", "data-portal", "statewide", ALL, 1,
     "District factsheet resource (xls/zip)."),
    ("https://www.indiastatdistricts.com/karnataka/all-districts/education/dropoutratesofgeneralcategoriesstudents",
     "Dropout rates (general category) by stage, all Karnataka districts, 2021-22", "IndiaStat Districts", "2022", "aggregator", "statewide", ALL, 1,
     "All-district table of dropout rates by stage (secondary compilation of UDISE+); figures not read."),
    ("https://www.deccanherald.com/india/karnataka/high-dropouts-dog-kasturba-girls-schools-880174.html",
     "High dropouts dog Kasturba girls' schools", "Deccan Herald", "", "news", "statewide", d("Ballari"), 1,
     "Karnataka Child Rights Commission member from Ballari on classes only up to 8 and hostels in a different location causing girls to drop out."),
    ("https://www.deccanherald.com/india/karnataka/education-rights-adalat-made-mandatory-2067930",
     "Education Rights Adalat made mandatory", "Deccan Herald", "", "news", "statewide", d("Ballari", "Chikkamagaluru", "Bengaluru Urban", "Mysuru"), 1,
     "KSCPCR chair's district tally of children leaving school (undated): Ballari 2,018, Bengaluru South 1,468, Mysuru 1,002, Chikkamagaluru 102."),
    ("https://www.deccanherald.com/india/karnataka/bengaluru/highest-number-school-dropouts-bangalore-2174993",
     "Highest number of school dropouts in Bangalore (district comparison)", "Deccan Herald", "", "news", "statewide", d("Bengaluru Urban", "Kalaburagi", "Yadgir"), 1,
     "Names Bengaluru Urban, Kalaburagi and Yadgir as districts with the most dropouts (date unclear)."),
    ("https://www.deccanherald.com/india/karnataka/activists-contest-claim-over-dip-2110371",
     "Activists contest claim over dip (out-of-school figures)", "Deccan Herald", "", "news", "statewide", d("Kalaburagi", "Yadgir"), 1,
     "Activists dispute official out-of-school counts; Yadgir figures disputed (SSA 11,197 vs NGO pilot of 900 in eight villages)."),
    ("https://www.deccanherald.com/india/karnataka/82k-children-quit-schools-701638.html",
     "82k children quit schools", "Deccan Herald", "2018", "news", "statewide", ALL, 1,
     "Education department recorded 82,713 dropouts in a year; school-level survey ordered via Grama Sabha and SATS."),
    ("https://www.deccanherald.com/india/karnataka/bengaluru/cs-orders-survey-to-find-school-dropouts-744631.html",
     "CS orders survey to find school dropouts", "Deccan Herald", "2019", "news", "statewide", ALL, 1,
     "Chief Secretary order for a dropout survey; mentions SATS 60-day absence rule (per other results)."),
    # ---- Tier 2: research, NGO and programme evidence ------------------------------------------------
    ("https://strive.lshtm.ac.uk/resources/correlates-school-dropout-and-absenteeism-among-adolescent-girls-marginalized-community",
     "Correlates of school dropout and absenteeism among adolescent girls from a marginalized community in north Karnataka", "LSHTM STRIVE (Prakash et al., J. Adolescence 2017)", "2017", "research", "regional", d("Bagalkote", "Vijayapura"), 2,
     "Survey of 2,275 SC/ST girls: 8.7% dropped out; poverty, work migration, child marriage and school environment linked to dropout (Bagalkot and Vijayapura)."),
    ("https://researchonline.lshtm.ac.uk/id/eprint/4523800",
     "Prakash et al. 2017 (LSHTM repository record)", "LSHTM Research Online", "2017", "research", "regional", d("Bagalkote", "Vijayapura"), 2,
     "Repository record for the north Karnataka adolescent girls dropout study."),
    ("https://strive.lshtm.ac.uk/system/files/attachments/Evidence brief - Samata intervention to increase secondary school completion.pdf",
     "Evidence brief: Samata intervention to increase secondary school completion", "LSHTM STRIVE", "2020", "research", "regional", d("Bagalkote", "Vijayapura"), 2,
     "SC/ST girls in north Karnataka: highest dropout risk in the state (11% vs 5.8% statewide, grades 8-9); trial found no overall effect."),
    ("https://www.joghr.org/article/12345-assessing-the-effect-of-the-samata-intervention-on-factors-hypothesised-to-be-on-the-pathway-to-child-marriage-and-school-drop-out-results-from-a-clu",
     "Assessing the effect of the Samata intervention on child marriage and school drop-out pathways", "Journal of Global Health Reports (Beattie et al.)", "2020", "research", "regional", d("Bagalkote", "Vijayapura"), 2,
     "Cluster-randomised trial in two districts by KHPT; mixed results."),
    ("https://cdn.clinicaltrials.gov/large-docs/41/NCT01996241/Prot_001.pdf",
     "Samata trial protocol (Bagalkot and Vijayapura)", "ClinicalTrials.gov / KHPT-LSHTM", "2014", "research", "regional", d("Bagalkote", "Vijayapura"), 2,
     "Background cites SSA data: 17% (Vijayapura) and 12% (Bagalkot) of girls lost between 7th and 8th standard in 2010-11."),
    ("https://strive.lshtm.ac.uk/sites/strive.lshtm.ac.uk/files/SAMATA Samachara  May 2016.pdf",
     "SAMATA Samachara newsletter, May 2016", "KHPT / LSHTM STRIVE", "2016", "ngo", "district", d("Vijayapura"), 2,
     "Vijayapura Deputy Commissioner: dropout down marginally, high in summer when families migrate for work."),
    ("https://www.ngji.in/index.php/ngji/article/view/355",
     "Out of school / dropout children in Dharwad district, Karnataka: a geographical study", "National Geographical Journal of India (Saviramath & Dadugoudar)", "2022", "research", "district", d("Dharwad"), 2,
     "Field survey plus secondary data on dropout in Dharwad district; causes and measures (findings not read)."),
    ("https://newskarnataka.com/education/150-kids-still-out-of-school-in-dharwad-ahead-of-new-academic-year/09052025/",
     "150 kids still out of school in Dharwad ahead of new academic year", "News Karnataka", "2025", "news", "district", d("Dharwad"), 3,
     "Joint survey: about 150 children not enrolled; Navalgund 53, Kundgol 36; many from migrant farm families."),
    ("https://newskarnataka.com/karnataka/gadag/gadags-heartfelt-mission-bringing-dropouts-back-to-school-one-child-at-a-time/09062025/",
     "Gadag's heartfelt mission: bringing dropouts back to school one child at a time", "News Karnataka", "2025", "news", "district", d("Gadag"), 3,
     "'Come, come to school' drive: survey of farms and worksites; 14 in Gadag town, 11 in Ron and 8 in rural Gadag returned."),
    ("https://www.siasat.com/karnataka-police-go-beyond-policing-return-200-school-dropouts-3517781/amp/",
     "Karnataka police go beyond policing, return 200 school dropouts", "Siasat", "2025", "news", "district", d("Shivamogga"), 3,
     "Shivamogga police 'Back to School' drive: 946 identified dropouts, Bhadravathi highest, 200+ returned."),
    ("https://www.deccanherald.com/content/392724/udupi-district-boasts-lowest-number.html",
     "Udupi district boasts lowest number (of out-of-school children)", "Deccan Herald", "2014", "news", "district", d("Udupi"), 3,
     "2013-14 survey: Udupi 1,008 out-of-school children, third lowest in the state."),
    ("https://www.deccanherald.com/india/karnataka/142-govt-schools-shut-in-u-k-over-17-years-4006584",
     "142 govt schools shut in Uttara Kannada over 17 years", "Deccan Herald", "2026", "news", "district", d("Uttara Kannada"), 3,
     "School closures and zero enrolment (access/supply context for dropout)."),
    ("https://deccanherald.com/india/karnataka/35-govt-schools-in-uttara-kannada-record-zero-admissions-this-academic-year-4082304",
     "35 govt schools in Uttara Kannada record zero admissions this academic year", "Deccan Herald", "2026", "news", "district", d("Uttara Kannada"), 3,
     "Zero-admission schools in Uttara Kannada and Sirsi educational districts."),
    ("https://www.deccanherald.com/content/403089/2151-school-dropouts-mandya-district.html",
     "2,151 school dropouts in Mandya district", "Deccan Herald", "2014", "news", "district", d("Mandya"), 3,
     "2013-14 DPI survey: 2,151 dropouts aged 6-14 (1,297 boys, 854 girls); Srirangapatna 443; parental illiteracy, poverty, migration, sibling care."),
    ("https://www.deccanherald.com/state/districts/mysuru-has-over-2600-school-drop-outs-428768.html",
     "Mysuru has over 2,600 school drop-outs", "Deccan Herald", "2014", "news", "district", d("Mysuru"), 3,
     "December 2013 survey (counts in the coverage vary: 5,512 identified, 2,855 re-enrolled); about 60% girls."),
    ("https://www.downtoearth.org.in/news/governance/bleak-future-ahead-covid-19-pushes-karnataka-s-first-generation-adivasi-learners-off-schools-78637",
     "Bleak future ahead: COVID-19 pushes Karnataka's first-generation Adivasi learners off schools", "Down To Earth", "2020", "news", "district", d("Chamarajanagara", "Mysuru"), 2,
     "Jenu Kuruba and tribal children in Chamarajanagar and Mysuru; ashram schools inside the tiger reserve; meals lost during closures."),
    ("https://antrocom.net/archives/2012/volume-8-number-2/an-investigative-study-on-school-drop-outs-in-tribal-settings-a-case-of-three-selected-tribes-in-south-karnataka/",
     "An investigative study on school drop-outs in tribal settings: three tribes in South Karnataka", "ANTROCOM Online Journal of Anthropology", "2012", "research", "district", d("Chamarajanagara"), 2,
     "Soliga, Jenu Kuruba and Betta Kuruba dropouts in Chamarajanagar district (findings not read)."),
    ("https://antrocom.net/archives/2021/volume-17-number-1/status-and-problems-of-jenukuruba-tribal-students-in-mysuru-district-of-karnataka/",
     "Status and problems of Jenukuruba tribal students in Mysuru district", "ANTROCOM Online Journal of Anthropology", "2021", "research", "district", d("Mysuru"), 2,
     "Jenu Kuruba students in Mysuru district; culturally linked education overlooked (findings not read)."),
    ("https://patrika.com/en/education-news/100-out-of-228-dropout-children-return-to-school-19106540",
     "100 out of 228 dropout children return to school", "Patrika", "2024", "news", "district", d("Chamarajanagara"), 3,
     "Chamarajanagar education survey: dropouts concentrated in Hanur taluk; poverty and parents sending children to fields."),
    ("https://www.deccanherald.com/content/495086/number-school-dropouts-falls-single.html",
     "Number of school dropouts falls to single digits", "Deccan Herald", "", "news", "district", d("Dakshina Kannada"), 3,
     "Dakshina Kannada dropout decline (details not read)."),
    ("https://www.deccanherald.com/india/karnataka/sharp-decline-school-dropouts-dk-2251961",
     "Sharp decline in school dropouts in DK", "Deccan Herald", "", "news", "district", d("Dakshina Kannada"), 3,
     "Dakshina Kannada dropout count fell from 7,800 (2001-02) to 132 (2012-13), credited to SSA drives."),
    ("https://www.deccanherald.com/india/karnataka/stark-decline-school-dropouts-dk-2422554",
     "Stark decline in school dropouts in DK", "Deccan Herald", "", "news", "district", d("Dakshina Kannada"), 3,
     "Dakshina Kannada dropout decline (details not read)."),
    ("https://newskarnataka.com/mangaluru/90-schools-in-dakshina-kannada-record-zero-admissions-in-five-years/29082025/",
     "90 schools in Dakshina Kannada record zero admissions in five years", "News Karnataka", "2025", "news", "district", d("Dakshina Kannada"), 3,
     "Zero-admission schools; aided schools converting to English/CBSE (enrolment context)."),
    ("https://www.ijfmr.com/research-paper.php?id=1809",
     "Economic analysis of primary school dropouts in Kodagu district", "International Journal for Multidisciplinary Research", "2023", "research", "district", d("Kodagu"), 2,
     "Socio-economic factors behind primary dropouts in Kodagu (primary level, not secondary)."),
    ("https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fkalaburagi-tops-state-in-school-absenteeism-782699.html",
     "Kalaburagi tops state in school absenteeism", "Deccan Herald", "2019", "news", "district", d("Kalaburagi"), 3,
     "1,648 children absent seven days running (highest in state); migration and ill health cited."),
    ("https://azimpremjifoundation.org/field-update",
     "Azim Premji Foundation field updates (lists 'Who drops out of school: dropout study of Yadgir')", "Azim Premji Foundation", "", "ngo", "district", d("Yadgir"), 2,
     "Foundation lists a Yadgir dropout study under Karnataka; report itself not found."),
    ("https://clpr.org.in/?p=7693",
     "CLPR: Karnataka High Court out-of-school children case", "Centre for Law and Policy Research", "2021", "ngo", "statewide", ALL, 2,
     "Karnataka HC suo motu case on out-of-school children; household survey ordered (rural survey began December 2020)."),
    ("https://dspace.sduaher.ac.in/jspui/handle/123456789/4635",
     "Thesis: irregularity and dropout among children at Anganwadi centres in Kolar district", "SDUAHER dspace (G M Nagaraja)", "2014", "research", "district", d("Kolar"), 2,
     "Anganwadi-level dropout in Kolar (early childhood, not secondary)."),
    ("https://www.isec.ac.in/wp-content/uploads/2025/10/WP-595-Manasi-and-Chennamma-Kambara-et-al1-Final.pdf",
     "ISEC Working Paper 595: educational disparities among children of informal migrant workers in Bengaluru", "Institute for Social and Economic Change", "2025", "research", "district", d("Bengaluru Urban"), 2,
     "656 migrant workers in construction, garment and domestic work: children's schooling."),
    ("https://www.deccanherald.com/city/life-in-bengaluru/makeshift-schools-for-kids-of-construction-workers-759392.html",
     "Makeshift schools for kids of construction workers", "Deccan Herald", "2019", "news", "district", d("Bengaluru Urban"), 3,
     "Tent schools after High Court suo motu petition; 415 dropouts found in Bengaluru survey, 193 readmitted."),
    ("https://www.deccanherald.com/india/karnataka/mcc-begins-h2h-mobile-app-survey-on-school-dropouts-941373.html",
     "MCC begins house-to-house mobile app survey on school dropouts", "Deccan Herald", "2021", "news", "district", d("Mysuru"), 3,
     "Mysuru City Corporation app-based survey of children aged 6-14."),
    ("https://sussex.figshare.com/articles/report/Distress_Seasonal_Migration_and_its_Impact_on_Children_s_Education/23313065",
     "Distress seasonal migration and its impact on children's education", "University of Sussex / CREATE", "", "research", "national", ALL, 2,
     "National study; 40-60 lakh children in distress seasonal migration (brick kilns, sugarcane harvesting)."),
    ("https://pmc.ncbi.nlm.nih.gov/articles/PMC9980764",
     "Determinants of school dropouts among adolescents: evidence from a longitudinal study in India", "PMC / Population Council", "2022", "research", "national", ALL, 2,
     "Cites north Karnataka findings on poverty, girls' work migration, bullying; national longitudinal evidence."),
    ("https://www.gov.uk/research-for-development-outputs/diverging-pathways-when-and-why-children-discontinue-education-in-india",
     "Diverging pathways: when and why children discontinue education in India", "Young Lives / UK R4D", "", "research", "national", ALL, 2,
     "Pulled-out / pushed-out / opted-out framework; pull factors above 60% (Andhra Pradesh and Telangana)."),
    # ---- Tier 2b: girls, marriage, labour, tribal / devadasi -----------------------------------------
    ("https://www.deccanherald.com/india/karnataka/700-child-marriages-in-a-year-cm-siddaramaiah-pulls-up-officials-3565338",
     "700 child marriages in a year: CM pulls up officials", "Deccan Herald", "2025", "news", "statewide", ALL, 2,
     "Child marriage cases 418 (2021-22) to 719 (2023-24) per the department; district counts appear in related reports."),
    ("https://thesouthfirst.com/health/karnataka-has-teen-pregnancy-problem-more-than-28500-underage-girls-reported-pregnant-in-11-months",
     "Karnataka has a teen pregnancy problem: 28,500 underage girls reported pregnant in 11 months", "The South First", "2024", "news", "statewide", ALL, 2,
     "Adolescent pregnancy counts (a schooling-exit pathway for girls)."),
    ("https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fpoverty-school-closure-push-up-child-marriages-in-karnataka-997144.html",
     "Poverty, school closure push up child marriages in Karnataka", "Deccan Herald", "2021", "news", "statewide", ALL, 2,
     "Links COVID school closures and poverty to child marriage."),
    ("https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fintl-day-against-child-labour-3-kids-rescued-from-child-labour-every-2-days-since-2021-in-karnataka-3581896",
     "3 kids rescued from child labour every 2 days since 2021 in Karnataka", "Deccan Herald", "2025", "news", "statewide", ALL, 2,
     "2,589 children rescued 2021 to April 2025; 781 in 2024."),
    ("https://deccanherald.com/india/karnataka/32-child-workers-rescued-last-year-and-11-this-year-in-mysuru-district-3065768",
     "32 child workers rescued last year and 11 this year in Mysuru district", "Deccan Herald", "2024", "news", "district", d("Mysuru"), 3,
     "Labour department raids in Mysuru, April 2023 to May 2024."),
    ("https://www.deccanchronicle.com/southern-states/karnataka/800-child-labourers-rescued-in-karnataka-during-a-special-ongoing-drive-1987042",
     "800 child labourers rescued in Karnataka during special drive", "Deccan Chronicle", "", "news", "statewide", d("Bengaluru Urban", "Mysuru", "Dharwad", "Kalaburagi", "Bengaluru Rural"), 3,
     "One-day statewide drive; district-wise rescue counts (date unclear)."),
    ("https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fchildren-of-ex-devadasis-need-not-write-fathers-name-karnataka-government-1169995.html",
     "Children of ex-Devadasis need not write father's name: Karnataka government", "Deccan Herald", "2022", "news", "statewide", d("Koppal", "Ballari", "Belagavi", "Vijayapura"), 2,
     "Mandatory father's name in admission forms cited as a driver of high dropout among Devadasi children."),
    ("https://www.terredeshommes.nl/en/projects/children-empowerment-for-getting-out-of-the-devadasi-system",
     "Children empowerment for getting out of the Devadasi system", "Terre des Hommes Netherlands", "", "ngo", "regional", d("Belagavi", "Koppal", "Ballari", "Vijayapura"), 2,
     "GOOD project in five north Karnataka districts, 51 villages."),
    # ---- SSLC results as a (non-dropout) outcome signal ---------------------------------------------
    ("https://www.theweek.in/wire-updates/national/2025/05/02/mes16-ka-sslc-results.html",
     "Karnataka Class 10 results 2025: pass percentage", "The Week (PTI)", "2025", "news", "statewide", d("Kalaburagi", "Vijayapura", "Yadgir"), 3,
     "SSLC 2025 district pass percentages at the bottom (Kalaburagi 42.43, Vijayapura 49.58, Yadgir 51.6). Pass rate is not a dropout rate."),
    ("https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fkarnataka-sslc-results-improve-by-8-percentage-points-to-6234-22-students-get-625625-2-3521589",
     "Karnataka SSLC results improve by 8 percentage points to 62.34%", "Deccan Herald", "2025", "news", "statewide", ALL, 3,
     "SSLC 2025 results; Yadgir 33rd from bottom per DH; sources disagree on last district. Not a dropout rate."),
    ("https://www.deccanherald.com/india/karnataka/govt-comes-up-with-29-point-norms-to-tackle-poor-sslc-results-3625364",
     "Govt comes up with 29-point norms to tackle poor SSLC results", "Deccan Herald", "2025", "news", "statewide", ALL, 3,
     "Policy response to poor SSLC results (exam-linked exits)."),
    # ---- added after checking leads from the two unsourced thin-district reports (pages fetched; numbers found on page) ----
    ("https://etvbharat.com/en/!state/authorities-foil-25-child-marriages-in-april-may-in-karnataka-davanagere-enn24070806000",
     "Authorities foil 25 child marriages in April-May in Karnataka's Davanagere", "ETV Bharat", "2024", "news", "district", d("Davanagere"), 3,
     "Verified on page: 25 of 26 reported child marriages stopped in April-May 2024; 194 prevented in 2023; counts by taluk. Marriage-stopping counts, not a dropout statistic."),
    ("https://newskarnataka.com/davanagere/preventing-child-marriages-in-davanagere-karnataka-a-success-story/09072024/",
     "Preventing child marriages in Davanagere: a success story", "News Karnataka", "2024", "news", "district", d("Davanagere"), 3,
     "Verified on page: 25 of 26 child marriages prevented in April-May 2024; children report cases through a toll-free number."),
    ("https://newskarnataka.com/karnataka/bengaluru/karnataka-police-rescue-800-child-labourers-in-statewide-operation/14092026/",
     "Karnataka police rescue 800 child labourers in statewide operation", "News Karnataka", "2026", "news", "district", d("Tumakuru"), 3,
     "Verified on page: Tumakuru 660 premises inspected, 33 children rescued (statewide drive, 16,951 premises, about 800 rescued)."),
    ("https://www.siasat.com/800-child-labourers-rescued-in-statewide-police-crackdown-3541250/",
     "800 child labourers rescued in statewide police crackdown", "Siasat", "2026", "news", "statewide", d("Tumakuru", "Bengaluru Urban"), 3,
     "Statewide drive; Tumakuru 33 rescued (the 660-premises figure was not on this page, it is on the News Karnataka one)."),
    ("https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fkscpcr-asks-school-education-department-to-submit-report-on-closure-of-schools-in-karnataka-3801344",
     "KSCPCR asks School Education Department to submit report on closure of schools in Karnataka", "Deccan Herald", "2026", "news", "statewide", ALL, 2,
     "Child-rights commission suo motu complaint on proposed merger/closure of low-enrolment schools into Karnataka Public Schools; distance and access concerns. Not specific to Ramanagara."),
    ("https://www.thesouthfirst.com/karnataka/officials-activists-worry-about-girls-as-details-of-murugha-matha-sexual-assault-case-emerge/",
     "Officials, activists worry about girls as details of Murugha Matha sexual assault case emerge", "The South First", "2022", "news", "district", d("Chitradurga"), 3,
     "Girls from the Murugha Matha hostel moved to Morarji Desai residential schools and CWCs (counts in coverage range from about 80 to 106; not 38)."),
    ("https://english.udayavani.com/article/raichur-27-child-labourers-rescued/913557",
     "Raichur: 27 child labourers rescued", "Udayavani", "2020", "news", "district", d("Raichur"), 3,
     "Search snippet only (page would not open here): nine vehicles stopped, 27 children rescued and returned to parents."),
]

INDIASTAT = json.load(open(os.path.join(HERE, "indiastat_urls.json"))) if os.path.exists(os.path.join(HERE, "indiastat_urls.json")) else {}

KW_DROP = re.compile(r"drop[- ]?out|out[- ]of[- ]school|dropped out|discontinu", re.I)


def fetch(url: str) -> tuple[int, str, str]:
    """-> (status, content_type, text). Retries once without TLS verification (flagged) for gov sites with bad certs."""
    for verify in (True, False):
        ctx = ssl.create_default_context() if verify else ssl._create_unverified_context()  # noqa: S323
        try:
            req = urllib.request.Request(urllib.parse.quote(url, safe=":/?&=%#,.-_~@+"), headers={"User-Agent": UA, "Accept-Language": "en"})
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                body = r.read(1_500_000)
                ct = r.headers.get("content-type", "")
                note = "" if verify else "tls-unverified"
                return r.status, ct + (" " + note if note else ""), body.decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            return e.code, "", ""
        except ssl.SSLError:
            continue
        except Exception as e:  # noqa: BLE001
            if verify and "CERTIFICATE" in str(e).upper():
                continue
            return 0, "", ""
    return 0, "", ""


def aliases(did: str) -> list[str]:
    base = NAMES[did].split(" (")[0]
    for k, v in ALIASES.items():
        if k.split(" (")[0] == base:
            return v
    return [base.lower()]


def check(entry: dict) -> dict:
    st, ct, body = fetch(entry["url"])
    out = {"status": st, "content_type": ct.strip()}
    if st != 200:
        out["state"] = "unreachable" if st == 0 else f"http {st}"
        return out
    if "pdf" in ct.lower() or body[:5] == "%PDF-":
        out["state"] = "opens (pdf, text not checked)"
        return out
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I))).lower()
    out["reads_dropout"] = bool(KW_DROP.search(text))
    ds = entry["districts"]
    if entry["scope"] == "district" and ds != ALL:
        out["names_district"] = all(any(a in text for a in aliases(x)) for x in ds)
    out["state"] = "verified" if out["reads_dropout"] and out.get("names_district", True) else "opens, relevance not confirmed"
    return out


def main() -> None:
    entries = []
    for i, (url, title, pub, year, kind, scope, dists, tier, note) in enumerate(S, start=1):
        entries.append({"id": f"L{i:03d}", "url": url, "title": title, "publisher": pub, "year": year, "kind": kind, "scope": scope,
                        "districts": dists, "tier": tier, "note": note, "found_via": "web search (this session)"})
    n = len(entries)
    for did, url in sorted(INDIASTAT.items()):
        n += 1
        entries.append({"id": f"L{n:03d}", "url": url, "title": f"IndiaStat district dropout table: {NAMES[did].split(' (')[0]}", "publisher": "IndiaStat Districts",
                        "year": "2013-2022", "kind": "aggregator", "scope": "district", "districts": [did], "tier": 1,
                        "note": "Dropout rates by stage and category, 2013-14 to 2021-22 (UDISE-based compilation). Table values not read.",
                        "found_via": "web search + URL pattern probe"})
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        for e, c in zip(entries, pool.map(check, entries)):
            e["check"] = c
    stamp = datetime.date.today().isoformat()
    with open(os.path.join(HERE, "sources.json"), "w", encoding="utf-8") as f:
        json.dump({"builtOn": stamp, "count": len(entries), "sources": entries}, f, indent=1, ensure_ascii=False)
    # ---- coverage matrix ----
    kinds = ["official-report", "survey-data", "data-portal", "parliament", "aggregator", "analysis", "research", "ngo", "news"]
    L = [f"# Source library: coverage by district ({stamp})", "",
         f"{len(entries)} sources. Sources found by web search and URL probes; verified = opens, mentions dropouts, and (district sources) names the district.", ""]
    st = {}
    for e in entries:
        st[e["check"]["state"]] = st.get(e["check"]["state"], 0) + 1
    L += ["Verification: " + "; ".join(f"{k}: {v}" for k, v in sorted(st.items())), "",
          "| District | District-scoped sources | Statewide sources naming it | Kinds present |", "|---|---|---|---|"]
    for did, nm in sorted(NAMES.items()):
        own = [e for e in entries if e["scope"] == "district" and did in e["districts"]]
        named = [e for e in entries if e["scope"] != "district" and e["districts"] != ALL and did in e["districts"]]
        ks = sorted({e["kind"] for e in own + named})
        L.append(f"| {nm} | {len(own)} | {len(named)} | {', '.join(ks) or 'none'} |")
    L += ["", "Statewide sources apply to every district: " + str(sum(1 for e in entries if e["districts"] == ALL)), ""]
    with open(os.path.join(HERE, "COVERAGE.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"{len(entries)} sources; verification: {st}")


if __name__ == "__main__":
    main()
