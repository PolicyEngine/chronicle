The two IRS SOI congressional district packages
(`soi-congressional-district-2022` and `soi-congressional-district-2023`) no
longer give a fact for a state total or the United States total of the district
file where another package gives the same quantity for the tax year
(chronicle#449). The IRS guide says that state totals within the congressional
data may not be comparable to the state totals SOI publishes elsewhere, and
points to Historic Table 2 for complete state totals. 4,616 TY2022 facts and
4,462 TY2023 facts go. Most had the semantic key of a Historic Table 2,
Publication 1304 or state-data fact of the same tax year (3,569 and 3,466),
with a different value in most pairs. Others (1,030 and 979) read an IRS column
that a Historic Table 2 package of the same tax year also reads at the same
level, under another concept id or domain. The last 17 of each year are United
States totals with the same tax-form line in Publication 1304, which uses
another domain or concept id: ten Schedule A items in Table 2.1, the EITC
returns and amount for no, one and two qualifying children in Table 2.5, and
the self-employed retirement plans deduction in Table 1.4. The other totals
stay until a package with the complete total exists (1,836 state and 30
national facts for TY2022; 1,938 state and 30 national facts for TY2023). They
move to the new record sets `...all_returns_state_totals`,
`...all_returns_us_total` and, for TY2023, `...agi_500k_plus_state_totals`
(record set spec ids `...all_returns_state_totals.v1`,
`...all_returns_us_total.v1` and `...agi_class_state_totals.v1`); they keep
their source record ids, semantic keys and values, and their aggregate and
source series keys change with the record set. The jurisdictions with one
district (eight in TY2022, seven in TY2023) have only one row in the file. That
row is now a congressional district fact (value id `<state>_00`, GEOID `<state
FIPS>00`, and `98` for the District of Columbia's delegate district), so each
package holds all 436 districts: 1,000 new district facts for TY2022 and 868
for TY2023. Where such a jurisdiction keeps a state total, the state fact and
the district fact read the same cell (288 cells in TY2022, 266 in TY2023). The
TY2022 state totals of the $500,000-or-more class go because
`soi-historic-table-2-state-agi-2022` has a row for that class, which adds
Historic Table 2's two top classes; the TY2023 package has no such row, so the
TY2023 totals of that class stay. The district facts that existed before keep
their ids, keys and values; their record set spec hash changes, because the
record sets lost rows, and the kept totals also change their record set id and
record set spec id. Fourteen of the removed United States totals of each year
have their only twin in a Publication 1304 package that builds one tax year at
a time (`soi-table-1-2`, `soi-table-1-4` and `soi-table-2-1`): the standard
deduction amount, the self-employed health insurance deduction amount and
returns, the self-employed retirement plans deduction amount and the ten
Schedule A items. Their TY2022 values are in a build for 2022 and not in a
bundle built for 2023, and their TY2023 values are not in a bundle built for
2022. The six EITC totals have their twin at each build year, because the Table
2.5 packages are pinned to their tax year. A consumer that scaled the districts
of a state to the district file's own state row must use the Historic Table 2
state row instead.
