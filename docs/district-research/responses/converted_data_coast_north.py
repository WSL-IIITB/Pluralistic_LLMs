"""
Authoring data for the Gemini half of the deep-research round (set-coast-north.md):
Dakshina Kannada, Udupi, Uttara Kannada, Belagavi, Vijayapura, Bagalkote, Dharwad,
Gadag, Haveri, Kalaburagi, Bidar, Yadgir, Raichur, Koppal, Ballari (+Vijayanagara).

Numbers in the cite lists are the report's own citation numbers (see
set-coast-north.sources.json). build_converted.py turns this into schema JSON and
then OPENS EVERY CITED PAGE to confirm each figure and that the page names the
district -- anything that fails is dropped and logged. Judgement calls made while
reading the report are noted in `notes`.
"""

SET = "set-coast-north"

# (districtId, name, regionId) -> content. reasons: (factor, category, detail, cites, evidence)
# facts: (label, value, cites). heads: (cite, takeaway). resp: (text, cites)
# checks: (method, verdict, note, cites)
DISTRICTS = [
    dict(
        id="29-575", name="Dakshina Kannada", region="karavali",
        headline="Top-ranked SSLC district, but seasonal labour migration is the documented reason children are out of school.",
        summary="Dakshina Kannada has the state's best SSLC results, backed by slow-learner coaching, yet district surveys have pointed to parents' seasonal migration for work as the leading cause of out-of-school children, and SSA coordinators work with Childline to trace them. Even in this high-performing district hundreds of enrolled candidates skip SSLC papers each year. No source gives Class 8-10 dropout counts, and none explains the district's very low casefile dropout rate.",
        reasons=[
            ("Parents' seasonal labour migration", "migration", "Surveys identified migrating labour families as the leading reason children are out of school; SSA coordinators work with the child welfare body and Childline to trace and re-enrol them.", [4, 5], "moderate"),
            ("Skipping SSLC papers", "other", "Hundreds of enrolled students are absent from SSLC language papers each year (329 on day one in 2024; 233 missed third-language papers in 2026).", [6, 7], "thin"),
            ("Intensive Class 10 retention drive", "governance", "Teachers are trained to coach slow learners and keep every Class 10 student on track, which fits the 98.40% pass rate and first state rank in 2026.", [1, 2, 3], "moderate"),
        ],
        facts=[
            ("SSLC pass rate, 2026", "98.40% (state rank 1)", [1]),
            ("Children out of school because of migration (survey)", "132", [4]),
            ("Absent on first SSLC language paper, 2024", "329", [6]),
            ("Absent for third-language SSLC paper, 2026", "233", [7]),
        ],
        heads=[(1, "Dakshina Kannada tops the state in SSLC 2026 with 98.40%, Udupi second."), (4, "Migration of labour families put 132 children out of school in the district."), (3, "Officials urged that no Class 10 student be left out."), (6, "First-day SSLC absentee numbers in Dakshina Kannada and Udupi.")],
        resp=[("SSA coordinators work with the Child Welfare Commission and Childline to trace migrant children, and teachers coach slow learners through Class 10.", [3, 4])],
        checks=[("state", "no-evidence", "No local source links household sanitation to dropout.", []),
                ("district", "unclear", "English-medium schools post strong SSLC results here, but no source links medium of instruction to retention or dropout.", [8])],
        gaps="No Class 8-10 dropout counts or recent out-of-school survey; the migration survey is several years old; nothing explains the very low casefile dropout rate.",
    ),
    dict(
        id="29-569", name="Udupi", region="karavali",
        headline="Near-perfect SSLC results; documented exits are mostly students absent from board papers.",
        summary="Udupi shares Dakshina Kannada's profile: 98.18% SSLC pass in 2026 (second in the state) after intensive slow-learner coaching. The only dropout-like signal in the sources is students who sit the whole secondary cycle and then skip board papers, 62 in language papers in 2026 and 122 in science papers in an earlier cycle. Early-secondary dropout is rarely reported.",
        reasons=[
            ("Skipping SSLC board papers", "other", "Students from several blocks failed to appear for language papers in 2026 and for science papers in an earlier cycle, a late exit that official pass rates hide.", [7, 10], "thin"),
            ("Intensive slow-learner coaching", "governance", "Teachers are told to isolate weaker students and drill them with question banks after preparatory exams, which keeps Class 10 candidates in the system.", [9, 8], "moderate"),
        ],
        facts=[
            ("SSLC pass rate, 2026", "98.18% (state rank 2)", [9]),
            ("Students who failed SSLC, 2026", "244", [9]),
            ("Absent for SSLC language papers, 2026", "62", [7]),
            ("Schools with 100% SSLC pass", "51", [8]),
        ],
        heads=[(9, "Focused preparatory strategy helps Dakshina Kannada and Udupi record top SSLC performance."), (10, "Over 42,000 students attend the SSLC exam in Dakshina Kannada and Udupi.")],
        resp=[("Education officials mandate slow-learner coaching and question-bank drills after the preparatory exam.", [9])],
        checks=[("state", "unclear", "Every government school here had toilets in 2023 High Court data; the factor is household sanitation, which no source links to dropout locally.", [19]),
                ("district", "no-evidence", "English-medium schooling is common here, but no source links it to retention or dropout.", [])],
        gaps="No Class 8-10 dropout counts; most sources are SSLC-result coverage; the district's very low casefile dropout rate is unexplained.",
    ),
    dict(
        id="29-563", name="Uttara Kannada", region="karavali",
        headline="Forest-belt poverty and thin staffing, with only old out-of-school counts for the Sirsi area.",
        summary="Uttara Kannada has few documented exits: a 2014 state survey found only 686 out-of-school children in Uttara Kannada (the fewest in the state) and 1,066 in the Sirsi educational district, and COVID-era fears kept some Sirsi parents from sending children to SSLC papers. A 2023 High Court report found every government school in the district had toilets. Claims about Siddi girls and guest teachers in the deep-research report could not be tied to their cited pages and were dropped.",
        reasons=[
            ("Few out-of-school children (2014)", "other", "The state's 2014 survey found Uttara Kannada had the fewest out-of-school children in Karnataka, with the Sirsi educational district higher.", [17], "moderate"),
            ("COVID-era exam avoidance in Sirsi", "health", "During the pandemic some Sirsi parents withheld children from SSLC maths and English papers over health fears.", [14], "thin"),
        ],
        facts=[
            ("Out-of-school children, Uttara Kannada (SSA survey, 2014)", "686", [17]),
            ("Out-of-school children, Sirsi educational district (SSA survey, 2014)", "1,066", [17]),
        ],
        heads=[(14, "Students in Karnataka write SSLC in the face of adversity, including Sirsi parents' pandemic fears."), (15, "Government-school students from Sirsi score near-perfect in SSLC 2024.")],
        resp=[],
        checks=[("state", "unclear", "A 2023 High Court report found every government school here had toilets, yet the casefile rate is high; the factor is household sanitation, which the report does not measure.", [19]),
                ("district", "no-evidence", "No data linking instruction medium to local dropout.", [])],
        gaps="No recent dropout or SSLC figures; Sirsi evidence is the 2014 count and one COVID item; the high casefile rate is unexplained. Siddi-girls and guest-teacher claims were dropped (cited pages do not support them).",
    ),
    dict(
        id="29-555", name="Belagavi", region="kitturu-karnataka",
        headline="Child marriage and sugarcane-economy pressure sit behind adolescent exits, even as results stay strong.",
        summary="Belagavi coverage centres on child marriage, with a minor married twice and the Akka Pade task force stopping marriages, and on child-labour rescues from local businesses. Sugarcane price disputes are reported as background to household stress, though no source links them to dropout. The division records a 95.71% SSLC pass rate in 2026. Belagavi Chikkodi was not researched separately.",
        reasons=[
            ("Child marriage of adolescent girls", "gender", "A 15-year-old was married off twice before the legal age, and the Akka Pade task force has intercepted marriages and sent girls to child protection committees.", [20, 21], "moderate"),
            ("Child labour in local businesses", "economic", "Authorities rescued five school-age children from a bakery, one of several raids on commercial establishments.", [24], "thin"),
            ("Sugarcane-economy household stress", "economic", "Prolonged farmer protests over cane prices signal income instability in agricultural households, though the sources do not tie it to dropout directly.", [22, 23], "thin"),
        ],
        facts=[
            ("Belagavi division SSLC pass rate, 2026", "95.71%", [25]),
            ("Children rescued from a bakery", "5", [24]),
        ],
        heads=[(21, "Akka Pade prevents a child marriage in Belagavi district."), (20, "Police register a case as a minor girl is married off twice in Belagavi district."), (24, "Five children rescued from a bakery in Belagavi."), (25, "Belagavi division tops Karnataka in SSLC with 95.71%.")],
        resp=[("The Akka Pade women's task force intercepts child marriages and hands minors to District Child Protection Committees.", [21])],
        checks=[("state", "no-evidence", "No local data links sanitation to dropout.", []), ("district", "no-evidence", "No local data links English-medium instruction to dropout.", [])],
        gaps="No district dropout, out-of-school or Class 8-10 retention figures; the SSLC figure is for the whole division; Chikkodi sub-area not covered.",
    ),
    dict(
        id="29-557", name="Vijayapura", region="kitturu-karnataka",
        headline="Mass weddings used to marry school-age girls, plus teachers pulled off duty, shape a weak secondary system.",
        summary="Vijayapura sources describe families using mass weddings to marry school-age daughters, prompting a rule that organisers give 21 days' notice so officials can check brides' ages. Teachers have protested being diverted to census work after SSLC, and the district has had poor SSLC performance that drew warnings to education officials. Many students are children of daily-wage farm labourers.",
        reasons=[
            ("Child marriage through mass weddings", "gender", "Poor families use mass wedding ceremonies to marry school-age daughters, so the district required organisers to give 21 days' notice for age verification.", [27], "moderate"),
            ("Agricultural wage-labour poverty", "economic", "Many students are children of daily-wage farm labourers, which is reported to push them towards work.", [26], "thin"),
            ("Census duty clashing with teaching", "governance", "High-school teachers complained that census work clashes with the academic calendar; the Deputy Commissioner exempted Vijayapura's high-school teachers.", [28], "thin"),
            ("Weak SSLC performance", "governance", "A poor SSLC result led the in-charge minister to threaten action against education officials and send teams to learn from coastal districts.", [29], "thin"),
        ],
        facts=[
            ("Advance notice required for mass weddings", "21 days", [27]),
            ("Candidates who tampered with SSLC marks cards for postal jobs", "42", [30]),
        ],
        heads=[(27, "Permission needed 21 days in advance for mass weddings in Vijayapura."), (28, "High-school teachers say the academic calendar clashes with census work."), (29, "DDPI taken to task for Vijayapura's dismal SSLC performance.")],
        resp=[("The district administration requires 21 days' notice for mass weddings so brides' ages can be verified.", [27])],
        checks=[("state", "no-evidence", "No evidence links sanitation to dropout here.", []), ("district", "no-evidence", "No evidence links instruction medium to dropout here.", [])],
        gaps="No dropout, out-of-school or SSLC pass-rate figures retrieved for recent years; sources are mostly 2015-2016 and one 2023 fraud case.",
    ),
    dict(
        id="29-556", name="Bagalkote", region="kitturu-karnataka",
        headline="Child marriage and a 2022 hijab-related exam boycott are the documented exits for girls.",
        summary="Bagalkote reporting links girls' school exit to child marriage, with the state offering gram panchayats a Rs 50,000 reward for preventing it, and records a student skipping SSLC in 2022 rather than remove a hijab. Farm-labour pressure on teenagers is asserted but thinly sourced.",
        reasons=[
            ("Child marriage of girls", "gender", "A child development project officer's mentoring reaches over 600 early-married girls in Bagalkot villages, a measure of how common early marriage is.", [31], "thin"),
            ("Hijab-related exam boycott", "social-norms", "A Bagalkot student refused to remove her hijab and skipped an SSLC paper during the 2022 dress-code row.", [32], "moderate"),
        ],
        facts=[
            ("Statewide: reward per gram panchayat that prevents child marriage", "Rs 50,000", [18]),
        ],
        heads=[(32, "Bagalkot student refuses to remove hijab, skips SSLC exam."), (33, "Class 10 results: a Bagalkot girl tops SSLC in Karnataka."), (18, "State announces Rs 50,000 reward to gram panchayats that prevent child marriages.")],
        resp=[("The state pays Rs 50,000 to gram panchayats that prevent child marriages and runs Children's Gram Sabhas.", [18])],
        checks=[("state", "no-evidence", "No local reporting links sanitation to dropout.", []), ("district", "no-evidence", "No local data links English-medium instruction to dropout.", [])],
        gaps="No dropout, out-of-school, SSLC pass-rate or migration data for the district was retrieved; child-marriage figures are thin.",
    ),
    dict(
        id="29-562", name="Dharwad", region="kitturu-karnataka",
        headline="A rural Dharwad study ties dropout to hardship and migration; child marriage is also being stopped.",
        summary="A study of rural Dharwad attributes high upper-primary and early-secondary dropout to disinterest, economic hardship and families migrating for wage work. The district's SSLC rank rose while its pass percentage fell, which The Hindu reported but did not link to dropout. Authorities prevented 28 child marriages in 2024-25 and launched Mission Vidyakashi to improve SSLC and PU results.",
        reasons=[
            ("Hardship, disinterest and migration", "economic", "A study of Dharwad's rural areas found dropouts driven by student disinterest, economic hardship and families moving for wage labour.", [37], "moderate"),
            ("Child marriage of girls", "gender", "Officials stopped 28 child marriages in 2024-25, evidence of ongoing pressure to marry girls out of school.", [39], "moderate"),
            ("Rank up, pass rate down", "governance", "Dharwad moved up the SSLC ranking while its pass percentage fell; the report reads this as weaker students leaving, which the sources do not confirm.", [35, 36], "thin"),
        ],
        facts=[
            ("Child marriages prevented, 2024-25", "28", [39]),
            ("SSLC state rank, 2023", "24th (up from 26th)", [36]),
        ],
        heads=[(39, "28 child marriages prevented in Dharwad district during 2024-25."), (35, "Dharwad goes up in SSLC ranking but down in pass percentage."), (38, "Mission Vidyakashi launched to improve Dharwad's SSLC and PU performance.")],
        resp=[("Mission Vidyakashi aims to improve teaching methods and SSLC and PU results.", [38])],
        checks=[("state", "no-evidence", "Sanitation is not identified as a dropout driver in local sources.", []), ("district", "no-evidence", "No data links instruction medium to local dropout.", [])],
        gaps="The dropout study is from 2019; no recent district dropout or out-of-school counts.",
    ),
    dict(
        id="29-561", name="Gadag", region="kitturu-karnataka",
        headline="Bonded shepherding of boys and mass weddings are the documented exits; the 2022 hijab row disrupted SSLC.",
        summary="Gadag sources cover two brothers from a Gadag village pulled out of school to work as bonded shepherds for five years (freed in 2013), two child marriages detected among mass weddings in 2016-17, a slide to 34th in the SSLC ranking with a 66.74% pass rate in 2015, and the suspension of seven teachers and invigilators in the 2022 hijab row. Evidence is dated and mostly single cases.",
        reasons=[
            ("Bonded shepherding of boys", "economic", "Two brothers, now 12 and 10, from a Gadag village were forced out of school five years earlier to work as bonded shepherds after their parents borrowed money; they were freed in 2013.", [41], "thin"),
            ("Child marriage at mass weddings", "gender", "Officials detected two child marriages among mass weddings in Gadag in 2016-17 and said this may not be the full extent.", [42], "thin"),
            ("Hijab row at SSLC", "social-norms", "Seven teachers and chief invigilators were suspended in 2022 for letting students write SSLC in hijab, alienating some minority students.", [43], "thin"),
        ],
        facts=[
            ("SSLC pass rate and state rank, 2015", "66.74% (34th)", [40]),
            ("Registered SSLC candidates, 2015", "15,095", [44]),
            ("Teachers and invigilators suspended in the hijab row", "7", [43]),
        ],
        heads=[(40, "Gadag slides from 13th to 34th place in SSLC results."), (41, "Goodbye to 5 long years as shepherd boys."), (43, "Seven teachers suspended for letting students write SSLC in hijab.")],
        resp=[],
        checks=[("state", "no-evidence", "No local reporting links sanitation to dropout.", []), ("district", "no-evidence", "No local data links English-medium instruction to dropout.", [])],
        gaps="Sources are mostly 2013-2017 and 2022; no recent dropout, out-of-school or SSLC figures.",
    ),
    dict(
        id="29-564", name="Haveri", region="kitturu-karnataka",
        headline="Private schools withholding hall tickets over fee arrears turn Class 10 students into exam dropouts.",
        summary="In Haveri, 30 students of one high school were denied SSLC hall tickets in 2021 even though they said they had paid fees, and the minister allowed them the supplementary exam; in 2024 one student sat a mock exam outside the Deputy Commissioner's office in protest. Student unions oppose plans to close or merge government schools, and the state women's commission chair flagged child marriage and teenage pregnancy in the district.",
        reasons=[
            ("Hall tickets withheld by a school", "governance", "30 students of one Haveri high school were not given SSLC hall tickets despite paying fees and had to take the supplementary exam.", [45], "moderate"),
            ("School closure and merger fears", "school-infrastructure", "Student unions argue that closing or merging government schools will cut secondary access for the poorest rural students.", [48], "thin"),
            ("Child marriage and teenage pregnancy", "gender", "The women's commission chair flagged the district for child marriage and teenage pregnancy, which end schooling for girls.", [49], "moderate"),
        ],
        facts=[("Students of one Haveri high school denied hall tickets, 2021", "30", [45])],
        heads=[(47, "SSLC student writes a mock exam in protest in front of the Deputy Commissioner's office in Haveri."), (45, "In a tussle between school managements and parents, many miss the SSLC exam."), (48, "SFI members urge the government to drop its plan to close schools.")],
        resp=[("PU courses are being added to three residential schools in the district.", [50])],
        checks=[("state", "no-evidence", "Sanitation is not cited as a dropout driver locally.", []), ("district", "no-evidence", "No evidence links instruction medium to dropout.", [])],
        gaps="No dropout or out-of-school counts or SSLC pass rates for the district.",
    ),
    dict(
        id="29-579", name="Kalaburagi", region="kalyana-karnataka",
        headline="Out-of-school counts differ 50-fold between departments, and child marriage is widespread.",
        summary="A rural-development survey found 11,137 out-of-school children in Kalaburagi while the education department reported 225, so the true scale is unclear. Authorities stopped 128 child marriages in a year and logged 43 more cases in four months, and parents were booked for marrying 15-year-old daughters. Child labour in ragpicking and scrap shops is reported, and the district ranked last in SSLC 2026.",
        reasons=[
            ("Child marriage of adolescent girls", "gender", "Officials prevented 128 child marriages in one year and logged 43 more cases in four months; parents were booked for marrying ailing 15-year-olds.", [52, 53, 54], "strong"),
            ("Departments disagree on dropout counts", "governance", "A rural-development survey counted 11,137 out-of-school children against 225 reported by the education department, hiding the real scale.", [51], "strong"),
        ],
        facts=[
            ("Out-of-school children: rural-development survey vs education department", "11,137 vs 225", [51]),
            ("Child marriages prevented in one year", "128", [52]),
            ("SSLC pass rate, 2026 (lowest in the state)", "85.06%", [1]),
        ],
        heads=[(51, "Different surveys on out-of-school children in Kalaburagi reveal contrasting figures."), (52, "Campaign prevents 128 child marriages in Kalaburagi in one year."), (54, "Four booked for child marriage in Kalaburagi.")],
        resp=[("A campaign and task force stepped up child-marriage prevention, with officials told to file FIRs swiftly.", [52, 53])],
        checks=[("state", "no-evidence", "Poverty, child marriage and data gaps dominate local reporting; sanitation is not linked to dropout.", []), ("district", "no-evidence", "No evidence links instruction medium to dropout.", [])],
        gaps="Out-of-school survey figures are contested and undated here; no Class 8-10 dropout rate.",
    ),
    dict(
        id="29-558", name="Bidar", region="kalyana-karnataka",
        headline="Festival-linked child marriages and very weak historic SSLC results; NGOs run 'academic ICU' bridge classes.",
        summary="Bidar sees child marriages cluster around festivals such as Akshaya Tritiya, prompting special task forces. SSLC outcomes have been historically poor, at one point only 27% passed, and Rotary Clubs have set up 'academic ICU' courses to help out-of-school children clear SSLC before they age out at 16. The district's out-of-school tracking figures are contested.",
        reasons=[
            ("Festival-linked child marriage", "gender", "Child marriages spike around festivals such as Akshaya Tritiya, so officials form special teams to stop parents withdrawing daughters from Class 8-9.", [55], "moderate"),
            ("Very poor SSLC outcomes", "governance", "A Hindu report on the district's results recorded only about 27% passing at one point, a pipeline that pushes failing students out.", [56], "thin"),
            ("Enrolled children working in scrap shops", "economic", "An official said some enrolled Bidar students worked in a nearby scrap shop and had to be rescued.", [51], "thin"),
        ],
        facts=[("Historic SSLC pass rate cited", "27%", [56]), ("Out-of-school children tracked (2025, contested)", "26", [51])],
        heads=[(55, "Ahead of Akshaya Tritiya, Bidar steps up vigil with special teams to prevent child marriages."), (57, "Rotary Clubs to set up an Academic ICU for out-of-school children in Bidar.")],
        resp=[("Rotary Clubs are running 'Academic ICU' bridge courses to help out-of-school children clear SSLC.", [57])],
        checks=[("state", "no-evidence", "No evidence links sanitation to dropout.", []), ("district", "no-evidence", "No evidence links instruction medium to dropout.", [])],
        gaps="No reliable out-of-school or dropout counts; the 27% pass figure is old.",
    ),
    dict(
        id="29-580", name="Yadgir", region="kalyana-karnataka",
        headline="Distress migration pulls 14-18-year-olds out of school; the Deputy Commissioner drives dropouts back herself.",
        summary="Yadgir's sources describe mass distress migration of labourer families to cities such as Bengaluru, a survey finding 1,747 out-of-school children aged 14-18, and a 2019 count of 1,547 children absent for more than three weeks, the highest in the state at the time. The administration uses NIOS and 'Mitra' programmes to bring older adolescents back, and an Azim Premji action-research study points to economic constraints at the transition into secondary school.",
        reasons=[
            ("Distress migration of labour families", "migration", "Families unable to live off arid land migrate to cities for construction and wage work, taking children out of school.", [58, 59], "moderate"),
            ("Chronic absenteeism", "other", "In 2019 Yadgir had the state's highest number of children missing school for over three consecutive weeks.", [60], "moderate"),
            ("Economic bottleneck at the move to secondary school", "economic", "Azim Premji Foundation research found deep-rooted economic constraints blocking the transition into secondary school.", [62], "moderate"),
        ],
        facts=[("Out-of-school children aged 14-18 (survey)", "1,747", [59]), ("Children absent more than three weeks, 2019", "1,547", [60])],
        heads=[(59, "1,747 out-of-school children in Yadgir to be brought back through NIOS and Mitra."), (61, "Yadgir Deputy Commissioner takes dropouts back to school in her vehicle."), (60, "SSA writes to the welfare panel about out-of-school children.")],
        resp=[("The administration uses NIOS and 'Mitra' programmes to mainstream older out-of-school adolescents; the Deputy Commissioner personally returns dropouts to class.", [59, 61])],
        checks=[("state", "no-evidence", "No direct evidence links sanitation to dropout.", []), ("district", "no-evidence", "No evidence links instruction medium to dropout.", [])],
        gaps="No district SSLC pass rates; the migration source is older.",
    ),
    dict(
        id="29-559", name="Raichur", region="kalyana-karnataka",
        headline="Cotton fields pull children out of class: 1,290 child labourers rescued in one year.",
        summary="Raichur's agricultural economy, especially Bt cotton, creates demand for child labour; the Labour Department rescued 1,290 children from cotton fields in a year and a judge warned against farm child labour. A child-marriage and POCSO case was reported. Older surveys counted over 12,000 out-of-school children while the education department later reported none, prompting the child-rights commission to demand a resurvey.",
        reasons=[
            ("Cotton-field child labour", "economic", "Labour rescues removed 1,290 children from cotton fields in a year, and a judge warned that farm child labour is destroying children's futures.", [63, 64], "strong"),
            ("Under-reported out-of-school children", "governance", "An older survey counted 12,128 out-of-school children while the education department reported zero absentees, drawing a commission demand for a resurvey.", [17, 66], "moderate"),
            ("Child marriage and sexual violence", "gender", "Ten people were booked under POCSO for a child marriage and assault of a minor.", [65], "thin"),
        ],
        facts=[("Child labourers rescued from cotton fields in a year", "1,290", [63]), ("Out-of-school children, older survey", "12,128", [17])],
        heads=[(63, "1,290 child labourers rescued in Raichur this year."), (64, "Judge warns against employing children in agricultural work."), (66, "KSCPCR urges a resurvey of out-of-school children in two districts.")],
        resp=[("The Karnataka child rights commission asked the education department to resurvey out-of-school children in the district.", [66])],
        checks=[("state", "no-evidence", "Labour demand overshadows any sanitation link in local reporting.", []), ("district", "no-evidence", "No evidence links instruction medium to dropout.", [])],
        gaps="Rescue figure and survey are several years old; no recent dropout rate or SSLC rank.",
    ),
    dict(
        id="29-560", name="Koppal", region="kalyana-karnataka",
        headline="The Devadasi system and forged age records for child marriage end girls' schooling.",
        summary="Koppal's reporting centres on the outlawed Devadasi system, with a 2022 survey counting about 3,600 Devadasis in the district, and on families using forged school age certificates to marry minors at mass weddings. A regional report counts over 14,000 children in agricultural work across the Hyderabad-Karnataka belt, though not by district.",
        reasons=[
            ("Dedication of girls as Devadasis", "social-norms", "Poor families, often in medical debt, still dedicate adolescent daughters to temple deities, ending their schooling.", [67, 68, 69], "moderate"),
            ("Forged age records for child marriage", "gender", "Authorities found fabricated school age certificates used to marry minor girls at mass weddings.", [70], "moderate"),
            ("Agricultural child labour (regional)", "economic", "A regional report found more than a third of child labour in the Hyderabad-Karnataka belt is in agriculture; the figure is not broken down by district.", [71], "thin"),
        ],
        facts=[("Devadasi women in the district (2022 survey)", "3,600", [69]), ("Statewide region: children in agricultural child labour (Hyderabad-Karnataka)", "14,122", [71])],
        heads=[(70, "Documents certifying a Koppal girl's age for marriage were fabricated."), (69, "22-year-old forced into the Devadasi system rescued in Koppal."), (68, "Parents held for pushing a daughter into the Devadasi system.")],
        resp=[],
        checks=[("state", "no-evidence", "Severe socio-cultural exploitation overshadows sanitation in local reporting.", []), ("district", "no-evidence", "No evidence links instruction medium to dropout.", [])],
        gaps="No dropout counts or SSLC figures; the labour statistic is regional, not district-level.",
    ),
    dict(
        id="29-565", name="Ballari (incl. Vijayanagara)", region="kalyana-karnataka",
        headline="A tracking drive found 259 out-of-school children but brought back only 38.",
        summary="In a drive reported in January 2025, officials identified 259 out-of-school children in Ballari but brought only 38 back to school. The deep-research report's claims about mining, poverty and mass weddings rested on a social-media post and a statewide article that does not name Ballari, so they are not used here.",
        reasons=[
            ("Low reintegration of out-of-school children", "governance", "A tracking drive identified 259 out-of-school children but managed to bring only 38 back to class.", [51], "moderate"),
            ("Mass weddings used to marry girls", "gender", "Mass wedding ceremonies are described as a gateway for marrying school-age girls while evading age checks.", [42], "thin"),
        ],
        facts=[("Out-of-school children identified", "259", [51]), ("Children reintegrated into school", "38", [51])],
        heads=[(51, "Different surveys on out-of-school children in Kalyana Karnataka reveal contrasting figures."), (42, "Mass weddings, a gateway for child marriages.")],
        resp=[],
        checks=[("state", "no-evidence", "No source cites sanitation as a dropout driver here.", []), ("district", "no-evidence", "No evidence links instruction medium to dropout.", [])],
        gaps="Mining-belt, poverty and mass-wedding claims were dropped (social-media post; statewide article); no SSLC or migration data. Vijayanagara not separately covered.",
    ),
]
