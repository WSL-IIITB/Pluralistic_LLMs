# Audit: how well is the 'child marriage & girls' exits' finding supported?

Run `python3 docs/district-research/audits/audit_marriage.py` (needs network; reads `public/data/districts-research.json`).

## Summary

| Test | Districts (of 30) |
|---|---|
| Any reason about marriage (what the headline counts) | 23 |
| ... with at least moderate evidence | 18 |
| ... with strong evidence | 6 |
| ... where a cited page names the district AND ties marriage to leaving school (strict text test) | 10 |

Numbers in these reasons: 60 of 65 checkable figures appear on a cited page; 5 do not (Gadag '17', Chitradurga '15', Mysuru '170', Bengaluru Rural '66' and '12').

## Per district

| District | Reasons (evidence) | Page ties marriage to leaving school? |
|---|---|---|
| Bagalkote | thin, moderate | yes |
| Belagavi | moderate, thin | yes |
| Bengaluru Rural | moderate, thin, thin | yes |
| Bengaluru Urban | moderate | yes |
| Bidar | moderate | no: counts / cases only |
| Chikkaballapur | thin, thin | yes |
| Chitradurga | strong, moderate, moderate | no: counts / cases only |
| Davanagere | moderate, thin | yes |
| Dharwad | moderate | no: counts / cases only |
| Gadag | thin, thin | no: counts / cases only |
| Hassan | strong, moderate, thin | no: counts / cases only |
| Haveri | moderate | no: counts / cases only |
| Kalaburagi | strong, thin | yes |
| Kodagu | thin, thin, thin | no: counts / cases only |
| Kolar | thin, moderate | yes |
| Koppal | moderate, strong | yes |
| Mandya | strong, moderate | no: counts / cases only |
| Mysuru | strong, moderate, moderate | no: counts / cases only |
| Raichur | thin | no: counts / cases only |
| Ramanagara | moderate, thin | no: counts / cases only |
| Shivamogga | moderate, moderate | yes |
| Vijayapura | moderate, moderate | no: counts / cases only |
| Yadgir | thin | no: counts / cases only |

## Reading it

- A district is counted in the headline if it has *any* marriage-related reason, whatever its evidence level.
- Many reasons are counts of child-marriage cases or enforcement actions (for example Mandya 172 cases, Ramanagara 44, Dharwad 28). The step 'so girls left school' is the researcher's inference, not something the page states.
- Some reasons rest on one case: Raichur (one POCSO case), Gadag (two marriages detected), Kodagu (three individual cases), Belagavi (one girl).
- Treat this as 'child marriage is documented as a concern in many districts', not as 'child marriage is the dominant cause of dropout'.

Caveat: the strict test is a text heuristic (marriage and a school-leaving phrase within about 260 characters, on a page that names the district). It can miss pages whose text did not load, and it cannot judge whether the page's claim is true.
