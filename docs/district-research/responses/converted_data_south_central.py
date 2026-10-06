"""
Authoring data for the ChatGPT half of the deep-research round (set-south-central.md):
Bengaluru Urban/Rural, Ramanagara, Mandya, Mysuru, Chamarajanagara, Chikkaballapur, Kolar,
Tumakuru, Davanagere, Chitradurga, Shivamogga, Chikkamagaluru, Kodagu, Hassan.

Cite numbers are the report's own (see set-south-central.sources.json). In the report's
tables the citation digits are glued to the values ("2,02810" = 2,028 + cite 10); they are
un-glued here and then re-checked against the cited pages by build_converted.py.

Judgement calls: SSLC 2025 pass rates for Kodagu, Hassan and Shivamogga (82.21 / 82.12 /
82.29) are omitted -- an earlier fetched source gave Kodagu 82.40, so these look conflated.
A 2016 "35-40% drop out between Classes 10 and 12" line is statewide, not Chikkaballapur's.
"""

SET = "set-south-central"

DISTRICTS = [
    dict(
        id="29-572", name="Bengaluru Urban", region="old-mysuru",
        headline="Migrant-labour families and school toilet gaps; thousands of dropouts counted across Bengaluru North and South.",
        summary="Bengaluru Urban's reported exits are tied to migration and weak tracking of children in a large, mobile population. A Bangalore Mirror report counted about 2,000 dropouts in Bengaluru South and 1,800 in Bengaluru North in 2023-24, and a 2023 High Court report found one government school in Bengaluru North and four in Bengaluru South without toilets. A statewide survey found most dropouts happen around ages 11 to 13, at the move into high school.",
        reasons=[
            ("Migration and an untracked child population", "migration", "A Bangalore Mirror report says migration fuels dropout in the state, and an officer said Bengaluru North's low out-of-school count (189) may reflect weak tracking in a garment-factory area.", [4, 10], "thin"),
            ("Schools without toilets", "school-infrastructure", "A 2023 High Court report found one government school in Bengaluru North and four in Bengaluru South without toilets.", [7], "thin"),
        ],
        facts=[
            ("Bengaluru South dropouts, 2023-24", "2,028", [10]),
            ("Bengaluru North dropouts, 2023-24", "1,824", [10]),
            ("Bengaluru South SSLC pass rate, 2025", "72.3%", [9]),
            ("Statewide: share of dropouts aged 11-13", "63%", [6]),
        ],
        heads=[(10, "Migration fuels school dropout crisis in Karnataka."), (7, "No drinking water in 87 government schools, no toilets in 464, says High Court."), (28, "Bengaluru Urban sees maximum dropouts in Karnataka, Udupi least.")],
        resp=[],
        checks=[("state", "unclear", "Government schools in the district lack toilets, but no source ties this to dropout locally.", [7]),
                ("district", "no-evidence", "No local investigation links the district-method factor to retention.", [5])],
        gaps="Dropout counts differ from an earlier Deccan Herald reading (2,682 South); casefile sub-areas North and South are not separated in most sources.",
    ),
    dict(
        id="29-583", name="Bengaluru Rural", region="old-mysuru",
        headline="Child labour near the metro and schools without water or toilets.",
        summary="Bengaluru Rural sits next to the metropolis, which creates demand for cheap adolescent labour; labour sweeps rescued 145 children over three years in a Times of India report. A High Court audit flagged five schools here without drinking water or toilets. Child-rights groups worry about post-COVID children who never returned to school.",
        reasons=[
            ("Child labour near the metro", "economic", "Proximity to Bengaluru draws adolescents into unorganised work; labour sweeps rescued 145 children over three years.", [11], "moderate"),
            ("Schools without toilets", "school-infrastructure", "A 2023 High Court report found five government schools in Bengaluru Rural without toilets.", [7], "thin"),
        ],
        facts=[
            ("Child labourers rescued over three years", "145", [11]),
            ("SSLC pass rate, 2025", "74.02%", [9]),
            ("Government schools without toilets (High Court data, 2023)", "5", [7], "manual"),
        ],
        heads=[(11, "Covid on the ebb, but child labour incidence still high in Karnataka.")],
        resp=[],
        checks=[("state", "unclear", "Schools here lack water and toilets, but no source links this to dropout.", [7]),
                ("district", "no-evidence", "No documented link between English-medium instruction and dropout locally.", [])],
        gaps="No district dropout counts; the child-labour figure comes from a statewide report.",
    ),
    dict(
        id="29-584", name="Ramanagara", region="old-mysuru",
        headline="Child marriage is the main documented exit: 44 cases in 2020-2023.",
        summary="Ramanagara is one of the southern districts with the most recorded child marriages, 44 between 2020 and 2023, and reporting also notes rising child labour. Tracking is reactive, based on rescues and interventions rather than bridge courses for slow learners.",
        reasons=[
            ("Child marriage of girls", "gender", "State child-welfare data records 44 child marriages in the district between 2020 and 2023, withdrawing girls from the SSLC pipeline.", [12], "moderate"),
            ("Rising child labour", "economic", "Reporting notes a rise in child-labour incidents that pull boys out of class.", [11], "thin"),
        ],
        facts=[("Child marriage cases, 2020-2023", "44", [12])],
        heads=[(12, "Mandya is the number one district in child marriages since 2020, with Ramanagara among the southern districts listed."), (13, "Bengaluru ranks low in the child protection index in Karnataka.")],
        resp=[],
        checks=[("state", "no-evidence", "No local investigation links sanitation to dropout.", []), ("district", "no-evidence", "Language of instruction is not cited as a barrier.", [])],
        gaps="No dropout, SSLC or out-of-school figures for the district.",
    ),
    dict(
        id="29-573", name="Mandya", region="old-mysuru",
        headline="Mandya recorded the state's most child marriages since 2020, despite strong SSLC results.",
        summary="Women and Child Welfare data show 172 child marriages in Mandya in 2020-2023, the highest in the state, with officials also citing single-parent households' financial strain as a driver of irregular attendance. The district's SSLC pass rate was 96.7% in 2023, which hides students who left earlier. Child marriages fell to 25 in January-October 2025 after intensive interventions.",
        reasons=[
            ("Child marriage of girls", "gender", "Mandya recorded 172 child marriages in 2020-2023, the most in the state, falling to 25 by late 2025 after enforcement.", [12, 15], "strong"),
            ("Single-parent households", "economic", "A legislative reply named single-parent households among the reasons for school dropout in Mandya and five other educational districts.", [14], "moderate"),
        ],
        facts=[
            ("Child marriage cases, 2020-2023", "172", [12]),
            ("Child marriage cases, January-October 2025", "25", [15]),
            ("SSLC pass rate, 2023", "96.7%", [9]),
        ],
        heads=[(12, "Mandya is number one in child marriages since 2020, data shows."), (15, "Drastic fall in child marriage numbers in the Old Mysuru region."), (14, "Poverty, migration and single parents among reasons for school dropout in Karnataka.")],
        resp=[("The District Child Protection Officer's interventions are reported to have cut child marriages to 25 in the first ten months of 2025.", [15])],
        checks=[("state", "no-evidence", "No local reports highlight sanitation as a dropout cause.", []), ("district", "no-evidence", "Language of instruction is not documented as a barrier.", [])],
        gaps="No dropout counts; the report's mention of female foeticide is not tied to schooling.",
    ),
    dict(
        id="29-577", name="Mysuru", region="old-mysuru",
        headline="Mysuru had the state's most child-marriage complaints in six months of 2024.",
        summary="Between April and September 2024 Mysuru received 105 child-marriage complaints, the most in the state, with 36 marriages carried out and 69 prevented. A legislative reply also named single-parent households among the reasons for dropout in Mysuru and five other educational districts.",
        reasons=[
            ("Child marriage of girls", "gender", "105 complaints in six months of 2024, 36 marriages carried out and 69 prevented, ending girls' schooling.", [16], "strong"),
            ("Single-parent households", "economic", "A legislative reply named single-parent households among the reasons for school dropout in Mysuru and five other educational districts.", [14], "moderate"),
        ],
        facts=[
            ("Child marriage complaints, April-September 2024", "105", [16]),
            ("Child marriage cases since 2020", "100", [12]),
            ("Child marriages carried out, April-September 2024", "36", [16]),
            ("Child marriages prevented, April-September 2024", "69", [16]),
        ],
        heads=[(16, "State announces a Rs 50,000 reward to gram panchayats that prevent child marriages."), (14, "Poverty, migration and single parents among reasons for school dropout in Karnataka.")],
        resp=[("The state offers Rs 50,000 to gram panchayats that prevent child marriage.", [16])],
        checks=[("state", "no-evidence", "Sanitation is not cited as a leading driver of high-school exits.", []), ("district", "no-evidence", "No evidence links the district-method factor to retention.", [])],
        gaps="The report's claim about residential schools for rescued child labourers cites a source that does not mention Mysuru and was dropped.",
    ),
    dict(
        id="29-578", name="Chamarajanagara", region="old-mysuru",
        headline="Tribal customs and seasonal migration are blamed for secondary exits; only three child marriages reported in 2025.",
        summary="A Times of India report on a legislative reply names Chamarajanagara as one of two tribal-dominated districts where social customs are blamed for school dropout. Reported child marriages were only three in the first ten months of 2025.",
        reasons=[
            ("Social customs in a tribal-dominated district", "social-norms", "In a legislative reply, social customs were blamed as one reason for dropout in two tribal-dominated districts, Chamarajanagara and Chitradurga.", [14], "moderate"),
        ],
        facts=[("Child marriages reported, January-October 2025", "3", [15], "manual")],
        heads=[(14, "Poverty, migration and single parents among reasons for school dropout in Karnataka."), (15, "Drastic fall in child marriage numbers in the Old Mysuru region.")],
        resp=[],
        checks=[("state", "no-evidence", "Sanitation is not listed among the causes of dropout here.", []), ("district", "no-evidence", "Medium of instruction is not documented as a barrier here.", [])],
        gaps="The main source is a statewide article; district-level dropout counts and SSLC results were not retrieved.",
    ),
    dict(
        id="29-582", name="Chikkaballapur", region="bayaluseeme",
        headline="Child marriage and abduction of adolescent girls; a statewide Class 10-12 dropout figure does not belong to this district.",
        summary="Chikkaballapur's documented exit in these sources is a 15-year-old pulled out of school and married (2016). The deep-research report's claim of a 35-40% post-SSLC dropout and a shortage of PU colleges here was a statewide statement from a 2016 budget article and is shown only as statewide context.",
        reasons=[
            ("Girl pulled out of school and married", "gender", "A 2016 report describes a 15-year-old from Chikkaballapur who was forcibly pulled out of school and married to a man from Andhra Pradesh.", [19], "thin"),
            ("SSLC malpractice", "governance", "Teachers were suspended for aiding SSLC malpractice and question papers circulated on WhatsApp, undermining the exam.", [21], "thin"),
        ],
        facts=[("Statewide: share of students who drop out between Classes 10 and 12 (2016, educationists)", "35-40%", [18])],
        heads=[(19, "Child brides born out of poverty and lack of security.")],
        resp=[],
        checks=[("state", "no-evidence", "No evidence links sanitation to dropout in this district.", []), ("district", "unclear", "Rural educators say rural students stay focused, but English medium is not cited as a cause of dropout.", [22])],
        gaps="No district dropout, out-of-school or SSLC pass-rate figures; the 35-40% figure is statewide and was not used as a district finding.",
    ),
    dict(
        id="29-581", name="Kolar", region="bayaluseeme",
        headline="A KGF government school with four teachers for 86 students failed all 38 SSLC candidates in 2024.",
        summary="At a 126-year-old government school in Kolar Gold Fields, all 38 SSLC candidates failed in 2025 because four teachers served 86 high-school students with no Science or Hindi teachers. A report of a man marrying his bride's minor sister points to child-marriage pressure on adolescent girls. A claim about bus-fare barriers could not be tied to Kolar and was dropped.",
        reasons=[
            ("Teacher shortage and mass failure", "school-infrastructure", "A KGF government school had four teachers for 86 high-school students and no Science or Hindi teachers; all 38 candidates failed SSLC in 2024.", [23], "strong"),
            ("Child marriage", "gender", "A report of a man marrying his bride's minor sister shows child-marriage pressure on adolescent girls in the district.", [25], "thin"),
        ],
        facts=[
            ("SSLC candidates who failed at the KGF school, 2024", "38", [23]),
            ("Teachers for 86 high-school students at the KGF school", "4", [23], "manual"),
        ],
        heads=[(23, "126-year-old forgotten school: all 38 SSLC students of a pioneer Karnataka school fail."), (25, "Man in Karnataka marries bride's minor sister too, held.")],
        resp=[],
        checks=[("state", "no-evidence", "Distance and transport, not sanitation, are the documented physical barriers.", []), ("district", "no-evidence", "Mass failure is attributed to missing subject teachers, not to English medium.", [23])],
        gaps="No district dropout or out-of-school counts retrieved; the bus-fare claim was dropped (cited article does not tie it to Kolar).",
    ),
    dict(
        id="29-571", name="Tumakuru", region="bayaluseeme",
        headline="Fee affordability and child exploitation cases; Madhugiri lost hundreds of students to unorganised labour.",
        summary="Tumakuru sources include an SSLC girl who attempted suicide because her family could not pay exam fees, a police case after 24 runaway children alleged forced labour and abuse at a madrasa, and an older report that Madhugiri taluk lost 436 students to unorganised work.",
        reasons=[
            ("Hall ticket withheld over school fees", "economic", "In 2021 a Tumakuru Class 10 girl who scored 95% in Class 9 was not issued an SSLC hall ticket because she could not pay the school's fee; she attempted suicide and later topped the supplementary exams.", [26], "thin"),
            ("Child labour exploitation", "economic", "Police registered cases after 24 runaway children alleged abuse and forced labour at a madrasa in Tumakuru Rural.", [27], "thin"),
            ("Madhugiri dropouts to unorganised labour", "economic", "A statewide dropout report listed Madhugiri with hundreds of students leaving to work in the unorganised sector.", [28], "moderate"),
        ],
        facts=[("Madhugiri dropouts (older statewide report)", "436", [28]), ("Children who alleged forced labour at a madrasa", "24", [27])],
        heads=[(27, "FIR against Tumakuru madrasa management after 24 runaway children allege abuse and forced labour."), (26, "Girl student who tried to end life scores highest in supplementary exams.")],
        resp=[],
        checks=[("state", "no-evidence", "Local reporting centres on finances and forced labour, not sanitation.", []), ("district", "no-evidence", "Language of instruction is not cited as a barrier locally.", [])],
        gaps="Sources are individual cases and an old count; no current dropout or SSLC district figures.",
    ),
    dict(
        id="29-567", name="Davanagere", region="bayaluseeme",
        headline="Selected for a UNICEF child-labour rehabilitation pilot; SSLC results have been volatile.",
        summary="Davanagere was chosen for a UNICEF pilot to rehabilitate child labourers, with hostels and schools built to bring them back into class, and the Chief Minister has warned teachers over results. Authorities also investigated a protocol breach at an SSLC evaluation centre.",
        reasons=[
            ("Child labour", "economic", "UNICEF picked the district for a child-labour rehabilitation project, building hostels and schools to reintegrate children.", [29], "moderate"),
            ("Volatile SSLC results", "governance", "The Chief Minister warned local teachers to improve results, and an SSLC evaluation-centre breach was probed.", [30, 31], "thin"),
        ],
        facts=[("UNICEF child-labour rehabilitation pilot", "District selected", [29])],
        heads=[(29, "Davanagere chosen for UNICEF project."), (31, "Assessment protocol breach spotted at SSLC evaluation centre in Davangere.")],
        resp=[("A UNICEF project funds hostels and schools to rehabilitate child labourers.", [29])],
        checks=[("state", "no-evidence", "No local investigation links sanitation to dropout.", []), ("district", "no-evidence", "No documentation links instruction medium to dropout.", [])],
        gaps="The UNICEF source is old; no current dropout counts retrieved.",
    ),
    dict(
        id="29-566", name="Chitradurga", region="bayaluseeme",
        headline="49 child marriages carried out in six months of 2024, driven by landless poverty.",
        summary="Chitradurga recorded 102 child-marriage complaints between April and September 2024; 49 marriages were carried out and 53 prevented. Police point to poverty among landless families, who use early marriage to ease household burdens.",
        reasons=[
            ("Child marriage of girls", "gender", "102 complaints in April-September 2024, of which 49 marriages were carried out, removing girls from school.", [16, 32], "strong"),
            ("Landless poverty", "economic", "Police say landless families treat child marriage as an economic coping mechanism.", [32], "moderate"),
            ("Social customs in a tribal-dominated district", "social-norms", "In a legislative reply, social customs were blamed as one reason for dropout in two tribal-dominated districts, Chitradurga and Chamarajanagara.", [14], "moderate"),
        ],
        facts=[
            ("Child marriage complaints, April-September 2024", "102", [16]),
            ("Child marriages carried out", "49", [16]),
            ("Child marriages prevented", "53", [16]),
        ],
        heads=[(16, "State announces a Rs 50,000 reward to gram panchayats that prevent child marriages."), (32, "Behind the silicone shine, 2,000 children forced into wedlock in Karnataka in three years.")],
        resp=[("Gram panchayats that prevent child marriage get a Rs 50,000 reward.", [16])],
        checks=[("state", "no-evidence", "Sanitation is not among the documented causes of dropout.", []), ("district", "no-evidence", "Medium of instruction is not a documented barrier.", [])],
        gaps="No school-level dropout or SSLC district figures retrieved.",
    ),
    dict(
        id="29-568", name="Shivamogga", region="malnad",
        headline="Hostel conditions for SC/ST students and child marriage drive exits; police now track dropouts.",
        summary="The state child-rights commission noted high dropout among SC/ST students in social-welfare hostels in Shivamogga, citing poor living conditions and food. Child marriage is a persistent threat, with 79 cases recorded in 2023-24, and police and the education department are working to trace dropped-out youth. The report's claim about schools forcing weak students to register as private candidates is about a Chikkamagaluru school and has been moved there.",
        reasons=[
            ("Hostel conditions for SC/ST students", "school-infrastructure", "The child-rights commission noted high dropout among marginalised students in welfare hostels, citing unlivable conditions and poor food.", [34], "moderate"),
            ("Child marriage", "gender", "79 child marriages were recorded in 2023-24, and officials avert several each year.", [35, 37], "moderate"),
        ],
        facts=[("Child marriages recorded, 2023-24", "79", [35])],
        heads=[(36, "Shivamogga Police join hands with the Education Department to bring dropouts back to school."), (34, "Meeting concerning safety of children in Shivamogga held.")],
        resp=[("Police and the education department are jointly tracing dropouts to bring them back to school.", [36])],
        checks=[("state", "no-evidence", "Hostel conditions are cited, not household sanitation.", []), ("district", "no-evidence", "No evidence links instruction medium to dropout.", [])],
        gaps="The district's SSLC pass rate is omitted because sources conflict; no dropout counts from these sources.",
    ),
    dict(
        id="29-570", name="Chikkamagaluru", region="malnad",
        headline="Migrant plantation families keep children out of school each pepper and coffee harvest.",
        summary="Each harvest season families migrate into Chikkamagaluru to work in coffee and pepper plantations, and children live in roadside tents minding younger siblings instead of attending school. A school in Begar made four regular students write SSLC as private candidates without parental consent, and parents threatened to withdraw daughters over the 2022 hijab ban.",
        reasons=[
            ("Seasonal plantation migration", "migration", "Hundreds of migrant families work the coffee and pepper harvest; their children miss school while living in makeshift tents.", [17], "strong"),
            ("Students registered as private candidates", "governance", "Karnataka Public School Begar allegedly registered four regular students as private candidates without parental consent, costing them internal marks.", [33], "moderate"),
            ("Hijab dispute", "social-norms", "Parents said they would withdraw daughters from high schools if headscarves were barred during the 2022 row.", [40], "thin"),
        ],
        facts=[("Students made to write SSLC as private candidates at one school", "4", [33], "manual"), ("Child marriages, January-October 2025", "19", [15]), ("Child marriage cases since 2020", "40", [12])],
        heads=[(17, "Come pepper harvest season, children of migrant workers in Karnataka miss school."), (33, "Karnataka Public School allegedly made four students write SSLC exams as private candidates in Chikkamagaluru."), (40, "Students and parents urge schools to allow girls with hijab in Chikkamagaluru.")],
        resp=[],
        checks=[("state", "no-evidence", "Migration and administrative malpractice, not sanitation, are the documented barriers.", []), ("district", "no-evidence", "Medium of instruction is not cited as a barrier.", [])],
        gaps="SSLC pass rate omitted because sources conflict; no dropout counts.",
    ),
    dict(
        id="29-576", name="Kodagu", region="malnad",
        headline="Even a girl who passed SSLC was engaged at 16 and later killed, showing marriage pressure after Class 10.",
        summary="Kodagu coverage includes a 16-year-old, the only student from her remote village school to pass SSLC, who was engaged immediately and later murdered. Child marriage cases stood at 10 in January-October 2025. The report's remark about elephant attacks on estate workers does not concern students and was not used.",
        reasons=[
            ("Marriage pressure after SSLC", "gender", "A 16-year-old who was the only student from her village school to pass SSLC was forced into an engagement and later murdered.", [42, 43], "thin"),
        ],
        facts=[("Child marriages, January-October 2025", "10", [15])],
        heads=[(42, "Kodagu student clears exam, gets engaged, killed."), (43, "Tip-off to police led to Kodagu minor girl's murder? Probe on.")],
        resp=[],
        checks=[("state", "no-evidence", "Physical safety and child marriage, not sanitation, are the reported barriers.", []), ("district", "no-evidence", "No evidence connects instruction medium to dropout.", [])],
        gaps="Single-case evidence only; SSLC pass rate omitted because sources conflict.",
    ),
    dict(
        id="29-574", name="Hassan", region="malnad",
        headline="Child marriages doubled in two years and put Hassan at the top of the state.",
        summary="Reporting says child marriages in Hassan doubled over two years, placing the district first in the state, with poverty and single-parent households behind withdrawals. A survey found 1,819 out-of-school children, concentrated in particular taluks, and police formed an all-women squad, Hasanamba Pade, to track dropouts and stop underage marriages.",
        reasons=[
            ("Child marriage doubling", "gender", "Child marriages in the district doubled over two years, the highest in the state at the time of the report.", [44, 45], "strong"),
            ("Girls taken in love-affair marriages", "gender", "Minor girls are reported to be taken and married under the guise of love affairs, complicating efforts to return them to class.", [45], "moderate"),
            ("Out-of-school children", "other", "A survey identified 1,819 out-of-school children, concentrated in specific taluks.", [46], "moderate"),
        ],
        facts=[("Out-of-school children identified in a survey", "1,819", [46])],
        heads=[(44, "Child marriages double in two years; Hassan on top."), (45, "Cases of child marriage worry officials in Hassan."), (46, "1,819 children out of school in Hassan district: survey."), (47, "73 school dropouts in Hassan this year.")],
        resp=[("Police formed an all-women squad, Hasanamba Pade, to track dropouts and prevent underage marriages.", [45])],
        checks=[("state", "no-evidence", "Child marriage and poverty, not sanitation, are the documented barriers.", []), ("district", "no-evidence", "Medium of instruction is not cited as a barrier.", [])],
        gaps="The out-of-school survey and child-marriage report are several years old; SSLC pass rate omitted because sources conflict.",
    ),
]
