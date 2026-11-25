## Parameters
- Assign Bucket Priority  [[Bucket Priority  (copy)_1213591364235264]] = 0.5 (real); range: [] members: ['0.', '0.25', '0.5', '0.75', '1.']
- Choose a Bucket for Intervention [[Choose a Bucket  (copy)_1192426827382784]] = "Infrastructure / Facilities" (string); range: [] members: ['"Digital / ICT"', '"Infrastructure / Facilities"', '"Monitoring and Compliance"', '"Pedagogy"', '"Socio Economic"', '"Teachers Profile"', '"Select a Bucket"']
- Digital / ICT [[Human Resources (copy)_1067667345227776]] = 0.5 (real); range: [] members: ['0.', '0.25', '0.5', '0.75', '1.']
- Teachers Profile [[Infrastructure (copy)_0743577051181062]] = 0.5 (real); range: [] members: ['0.', '0.25', '0.5', '0.75', '1.']
- Reset Trigger [[Parameter 10]] = 1 (integer); range: [] members: ['0', '1']
- Socio Economic [[Parameter 1]] = 0.25 (real); range: [] members: ['0.', '0.25', '0.5', '0.75', '1.']
- Reduce Children under 5 years who are stunted [[Parameter 2]] = 0.20000000000000001 (real); range: [('0.05', '1.0', '0.05')] members: []
- Enter Budget [[Parameter 3]] = 100000000. (real); range: [('100000.0', '1000000000.0', '1.0')] members: []
- Choose a Bucket  [[Parameter 4]] = "Socio Economic" (string); range: [] members: ['"Digital / ICT"', '"Infrastructure / Facilities"', '"Monitoring and Compliance"', '"Pedagogy"', '"Socio Economic"', '"Teachers Profile"', '"Select a Bucket"']
- Show [[Parameter 5]] = "All" (string); range: [] members: ['"All"', '"Top 5"']
- Top N Factors [[Parameter 6]] = 5 (integer); range: [('1', '5', None)] members: []
- Factor Threshold [[Parameter 7]] = 5 (integer); range: [] members: []
- District Selected Parameter [[Parameter 8]] = "Yes" (string); range: [] members: ['"Yes"', '"No"']
- Priority mode [[Parameter 9]] = "Custom Priority" (string); range: [] members: ['"Equal Allocation"', '"Custom Priority"']
- Monitoring & Compliance [[Pedagogy (copy)_1067667345616897]] = 0.5 (real); range: [] members: ['0.', '0.25', '0.5', '0.75', '1.']
- Infrastructure / Facilities [[Socio Cultural (copy)_0743577050935300]] = 0.5 (real); range: [] members: ['0.', '0.25', '0.5', '0.75', '1.']
- Bucket Priority  [[Socio Economic (copy)_0399441990914048]] = 0.5 (real); range: [] members: ['0.', '0.25', '0.5', '0.75', '1.']
- Socio Cultural [[Socio Economic (copy)_0743577050828803]] = 0. (real); range: [] members: ['0.', '0.25', '0.5', '0.75', '1.']

### Calculation1  ([Calculation_0009074246770689])
"Reset Allocation"

### State for ranking   ([Calculation_0138296631574528])
//State for ranking 
[State]

### District selection   ([Calculation_0206159173345280])
IF COUNT([District]) = 0 THEN
    "Please select a district"
ELSE
    ""
END

### Low Factor Flag  ([Calculation_0283466526920705])
IF { FIXED [District],[State] : COUNTD([Factor Name]) } < [Parameters].[Factor Threshold] THEN "Low"
ELSE "OK"
END

### Caution msg  ([Calculation_0283466527346690])
IF 
COUNTD(
    IF [Low Factor Flag] = "Low" THEN [State] END
) > 0
THEN 
"⚠ The Selected State has Low factors"
END

### Current dropout rate of district  ([Calculation_0289753671049216])
{ FIXED [State],[District] :
    AVG(
        IF TRIM([Factor Name]) = "Children under 5 years who are stunted (height-for-age) (%) (ind_068)" THEN
            FLOAT([Field Value])
        END
    )
}

### Current state dropout rate  ([Calculation_0289753672859649])
{ FIXED [State] :
    AVG(
        IF TRIM([Factor Name]) = "Children under 5 years who are stunted (height-for-age) (%) (ind_068)" THEN
            FLOAT([Field Value])
        END
    )
}

### Target dropout rate   ([Calculation_0289753673134082])
{ FIXED [State] :
    AVG(
        IF TRIM([Factor Name]) = "Children under 5 years who are stunted (height-for-age) (%) (ind_068)" THEN
            FLOAT([Field Value])
        END
    )
}
*
(1 - [Parameters].[Reduce Children under 5 years who are stunted])

### Target dropout rate of a district  ([Calculation_0289753673334787])
{ FIXED [State],[District] :
    AVG(
        IF TRIM([Factor Name]) = "Children under 5 years who are stunted (height-for-age) (%) (ind_068)" THEN
            FLOAT([Field Value])
        END
    )
}
*
(1 - [Parameters].[Reduce Children under 5 years who are stunted])

### Calculated weight   ([Calculation_0399441991806980])
IF { FIXED :
        MAX(
            IF [Selected Bucket Set]
            THEN 1
            ELSE 0
            END
        )
    } = 0

THEN

    1
    /
    { FIXED [State], [District] : COUNTD([Bucket]) }

ELSE

    IF [Selected Bucket Set] THEN
        [Parameters].[Bucket Priority ]

    ELSE

        (1 - [Parameters].[Bucket Priority ]) 
        /
        (
            { FIXED [State], [District] : COUNTD([Bucket]) } - 1
        )

    END

END

### Bucket Priority value   ([Calculation_0606152648802304])
//Bucket Priority value 
[Calculated weight ]/1*100

### Prescribed   ([Calculation_0743577052131336])
IF [Factor Name] = "Dropout Rate" THEN
    [Field Value]

ELSEIF ABS([M Value]) < 0.00001 THEN
    [Field Value]

ELSE
    MIN(
        100,
        MAX(
            0,
            [Field Value] +

            (
                ([Calculated weight ] / [Bucket Factor Count])

                *
                (
                    (
                        { FIXED [State], [District] :
                            MAX(
                                IF [Factor Name] = "Children under 5 years who are stunted (height-for-age) (%) (ind_068)"
                                THEN [Field Value]
                                END
                            )
                        }
                        * (1 - [Parameters].[Reduce Children under 5 years who are stunted])
                        -
                        { FIXED [State], [District] :
                            MAX(
                                IF [Factor Name] = "Children under 5 years who are stunted (height-for-age) (%) (ind_068)"
                                THEN [Field Value]
                                END
                            )
                        }
                    )
                    / [M Value]
                )
            )
        )
    )
END

### Change  ([Calculation_0743577055944713])
//Change
IF ABS([Field Value]) < 0.000001 THEN
        NULL
    ELSE
        ABS(
            ([Prescribed ] - [Field Value])
            / [Field Value] 
        )
    END

### Total intervention of a state   ([Calculation_0743577056460810])
//Total intervention of a state 
{ FIXED [State] :
    AVG([change 2])
}

### Intervention  ([Calculation_0743577056677899])
//Intervention
[Total intervention of a state ]*[Confidence value]

### Intervention Index  ([Calculation_0743577057722380])
//Intervention Index
[Intervention]
/
{ FIXED :
    SUM([Intervention])
}

### Bucket Clean  ([Calculation_0762838675275777])
IF TRIM([Bucket]) = "Infrastructure" 
OR TRIM([Bucket]) = "Infrastructure/Facilities" THEN
    "Infrastructure/Facilities"
ELSE
    TRIM([Bucket])
END

### Ci  ([Calculation_1053639695585280])
// Ci
IF [Factor Name] = "Dropout rate"
   OR ISNULL([M Value])
   OR ISNULL([Prescribed ])
THEN
    NULL
ELSE
    ABS(
        ([Prescribed ] - [Field Value])
        / [Field Value]
    )
END

### Proportion num  ([Calculation_1053639713054721])
//Proportion numerator 
IF ISNULL([Ci])
   OR ISNULL([M Value])
   OR [M Value] = 0
THEN
    NULL
ELSE
    ABS(
        ([Ci] / [M Value])
        * [Calculated weight ]/[Bucket Factor Count]
    )
END

### Proportion denom  ([Calculation_1053639718154245])
//Proportion denom
{ FIXED [State] :
    SUM([Proportion num])
}

### Budget share for each factor   ([Calculation_1053639719772168])
//Budget share for each factor 
IF ISNULL([Proportion denom])
   OR [Proportion denom] = 0
THEN
    NULL
ELSE
    (
        [Proportion num]
        /
        [Proportion denom]
    )
    * [Parameters].[Enter Budget]
END

### Factor Budget Share %  ([Calculation_1053639721816073])
//Factor Budget Share %
IF ISNULL([Parameters].[Enter Budget]) OR [Parameters].[Enter Budget] = 0 THEN
    NULL
ELSE
    ([Budget share for each factor ] / [Parameters].[Enter Budget]) * 100
END

### Bucket's budget  ([Calculation_1053639723401226])
{ FIXED [State], [Bucket] :
    SUM([Budget share for each factor ])
}

### bucket share   ([Calculation_1053639723839499])
//bucket share 
IF ISNULL([Parameters].[Enter Budget]) OR [Parameters].[Enter Budget] = 0 THEN
    NULL
ELSE
    ([Bucket's budget] / [Parameters].[Enter Budget]) * 100
END

### Intervention Bucket Weight  ([Calculation_1213591366713345])
IF { FIXED :
        MAX(
            IF [Selected Intervention Bucket Set]
            THEN 1
            ELSE 0
            END
        )
    } = 0

THEN

    1
    /
    { FIXED [State], [District] : COUNTD([Bucket]) }

ELSE

    IF [Selected Intervention Bucket Set] THEN

        [Parameters].[Assign Bucket Priority ]

    ELSE

        (1 - [Parameters].[Assign Bucket Priority ])

        /
        (
            { FIXED [State], [District] : COUNTD([Bucket]) } - 1
        )

    END

END

### change 2  ([Calculation_1213591372693508])
//Change 2
IF ABS([Field Value]) < 0.000001 THEN
        NULL
    ELSE
        ABS(
            ([Prescribed  for intervention] - [Field Value])
            / [Field Value] 
        )
    END

### Confidence value  ([Calculation_1273267480760320])
//Confidence value
{ FIXED [State] :
    AVG(
        IF [Factor Name] = "Children under 5 years who are stunted (height-for-age) (%) (ind_068)"
        THEN [Confidence Level]
        END
    )
}

### Bucket Factor Count  ([Calculation_1581964621225984])
//Bucket Factor Count
{ FIXED [State], [District], [Bucket] :

    COUNTD(
        IF [Factor Name] <> "Dropout Rate"
        THEN [Factor Name]
        END
    )

}

### Prescribed  for intervention  ([Prescribed  (copy)_1213591372492803])
IF [Factor Name] = "Dropout Rate" THEN
    [Field Value]

ELSEIF ABS([M Value]) < 0.00001 THEN
    [Field Value]

ELSE
    MIN(
        100,
        MAX(
            0,
            [Field Value] +

            (
                ([Intervention Bucket Weight] / [Bucket Factor Count])

                *
                (
                    (
                        { FIXED [State], [District] :
                            MAX(
                                IF [Factor Name] = "Dropout Rate"
                                THEN [Field Value]
                                END
                            )
                        }
                        * (1 - [Parameters].[Reduce Children under 5 years who are stunted])
                        -
                        { FIXED [State], [District] :
                            MAX(
                                IF [Factor Name] = "Dropout Rate"
                                THEN [Field Value]
                                END
                            )
                        }
                    )
                    / [M Value]
                )
            )
        )
    )
END

### Assign Bucket Priority   ([Bucket Priority  (copy)_1213591364235264])
0.5

### Reduce Children under 5 years who are stunted  ([Parameter 2])
0.20000000000000001

### Enter Budget  ([Parameter 3])
100000000.

### Factor Threshold  ([Parameter 7])
5

### Bucket Priority   ([Socio Economic (copy)_0399441990914048])
0.5

