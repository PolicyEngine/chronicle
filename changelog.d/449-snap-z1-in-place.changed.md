Two US packages now read the newer edition of their publisher file in place
(chronicle#449). Each keeps its package id, record sets, rows, labels and
filters. `usda-snap-fy69-to-current` reads `FY24.xlsx` of
`snap-zip-fy69tocurrent-11.zip`, USDA's fiscal year 2024 figures as of
11/13/2026, in place of the same member of the `-6` zip (vintage
`fiscal_year_2024_revised_2026_11_13`). The two members have the same labels
and cell positions, but 65 of the package's 216 facts change value, in 27
geographies. The national average monthly households go from 22,200,091.5833
to 22,209,610.0833, the persons from 41,690,237.75 to 41,709,123.0833, the
average monthly benefit per person from USD 187.5886 to USD 186.7615, and the
benefits from USD 93,847,365,890 to USD 93,475,887,992. The facts keep their
record ids and semantic keys; their aggregate, legacy and release keys change
with the file.
`federal-reserve-z1-household-net-worth` reads table S1M.b of the Z.1 release
of 2026-06-11 in place of table B.101 of the release of 2026-03-19 (source
table `Z.1 S1M.b Households and nonprofit organizations`, vintage
`z1_2026_06_11`). Net worth is still line 40, series FL152090005, and the
sector footnote is the same. The 2023 net worth of households and nonprofit
organizations goes from USD 156,080.7 billion to USD 156,278.8 billion. The
package does not read the releases from 2026-09-11, which change the sector's
coverage. The fact keeps its record id and semantic key. Because the source
table's name changes, its source series, observed measure, release, aggregate
and legacy keys change. The S1M.b unit, billions of dollars, comes from the
release PDF, which is registered raw-only with the B.101 page it replaces.
