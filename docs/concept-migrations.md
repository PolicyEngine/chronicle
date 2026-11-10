# Concept migrations

Consumer-facing source vocabulary is a compatibility contract
(see [architecture](architecture.md#source-facts-and-microcosm-targets)). A
deliberate concept rename is recorded here, with the regression test that pins
the affected consumer selector. Changing a concept changes each affected
consumer row's `observed_measure.source_concept`, `observed_measure_key`,
`aggregate_fact_key`, `semantic_fact_key`, `legacy_fact_key` and generated
`label`; a label change also moves `layout.measure_label`. `measure_id`,
`source_record_id`, values and lineage do not change.

## 2026-09-27: IRS SOI Form 1040 line 7 capital gain or (loss)

| Packages | Columns | Old concept | New concept |
|---|---|---|---|
| `soi-historic-table-2`, `soi-historic-table-2-state-broad-2022` | `N01000` | `irs_soi.returns_with_taxable_net_capital_gains` | `irs_soi.returns_with_form_1040_capital_gain_or_loss` |
| same | `A01000` | `irs_soi.taxable_net_capital_gains` | `irs_soi.form_1040_capital_gain_or_loss` |
| `soi-congressional-district-2022` | `N01000` | `irs_soi.returns_with_net_capital_gains` | `irs_soi.returns_with_form_1040_capital_gain_or_loss` |
| same | `A01000` | `irs_soi.net_capital_gains` | `irs_soi.form_1040_capital_gain_or_loss` |

Labels become the IRS wording, "Returns with net capital gain (less loss)" and
"Net capital gain (less loss)". `measure_id` stays `net_capital_gains_returns` /
`net_capital_gains_amount`.

**Why.** The IRS documentation guides for Historic Table 2 (TY2020–TY2023) and
for the TY2022 congressional-district, ZIP and county files define `N01000` as
"Number of returns with net capital gain (less loss)" and `A01000` as "Net
capital gain (less loss) amount", both from Form 1040 line 7, "Capital gain or
(loss)". That line holds a Schedule D gain, a Schedule D loss limited to $3,000
($1,500 married filing separately), or capital gain distributions reported
without a Schedule D.

- The Historic Table 2 packages had borrowed the concept of Table 1.4 columns
  37/38 (25/26 before TY2022), "Sales of capital assets reported on Form 1040, Schedule D: Taxable
  net gain", which counts only Schedule D returns with a gain. For TY2022 the
  two counts are 30,465,850 and 12,915,122 returns. Historic Table 2's US count
  equals Table 1.4's capital-gain-distribution, taxable-net-gain and
  taxable-net-loss returns combined to within 0.25% in every year TY2020–TY2023
  (the TY2022 identity is checked in CI against Chronicle's registered files).
- The congressional-district ids read as a gain-only amount. IRC section
  1222(11) and the Publication 1304 Explanation of Terms both use "net capital
  gain" for a positive amount only.
- The ids name the Form 1040 line rather than repeat the IRS phrase "net
  capital gain (less loss)". Publication 1304 Table A uses that phrase for
  Schedule D gain and loss returns without the distribution-only returns
  (TY2022: 26,480,998), so the phrase alone does not identify the population.

**Semantic keys.** Historic Table 2 and the congressional-district file now
share one concept for the same IRS variable. Before this change that held for 26
of the 38 IRS variables the national package shares with the
congressional-district file (24 of 36 for the state package); the capital-gains
pair was 2 of the same 12 exceptions in both. Their TY2022 state and US rows therefore share semantic
keys, which adds 104 semantic-duplicate keys to the default bundle (51 states
and the US, returns and amount). The values differ: the IRS guide for the
congressional-district file says its state totals "may not be comparable to
State totals published elsewhere by SOI because of disclosure protection
procedures or the exclusion of returns that did not match based on the ZIP
code." Historic Table 2 and Table 1.4 capital-gain rows for the same year can
no longer share a semantic key. In the default bundle they did not collide,
because Historic Table 2 builds at TY2022 and Table 1.4 at TY2023, but a TY2022
build of both did.

**Unchanged.** Table 1.4 keeps `irs_soi.returns_with_taxable_net_capital_gains`
/ `irs_soi.taxable_net_capital_gains`. `measure_id` stays
`net_capital_gains_returns` / `net_capital_gains_amount` in all four packages
because Microcosm selects on it, so one `measure_id` still names two different
measures; chronicle#307 tracks giving them distinct ids together with the
Microcosm selector change, and the 10 other IRS columns that Historic Table 2
and the congressional-district file still label with different concepts.

**Pinned by** `tests/test_chronicle_soi_capital_gain_concepts.py`: every
`irs_soi` measure (any vintage) that names `N01000`/`A01000` in its
`source_column_id` or `expected_column_header` guard must declare the new
concept, only Table 1.4 may declare the Schedule D gain concept, the retired
ids may not reappear, and the consumer selector (`source_measure_id`) and
published values are unchanged.

## 2026-10-12: IRS SOI geographic-file columns follow their documentation guides

Four IRS SOI mappings read a column that the file's documentation guide defines
as a different item. Extracts of the guides are in
`tests/data/irs_soi_doc_guides/`, each with its irs.gov URL and sha256.

### Column corrections

Measure ids, concepts and labels stay. Values, `layout.source_column_id` and
the cell lineage change.

| Packages | Measure ids | Old columns | New columns | TY2022 US, old → new |
|---|---|---|---|---|
| `soi-congressional-district-2022` | `limited_state_local_taxes_returns` / `_amount` | `N18425`/`A18425`, "State and local income taxes" (Schedule A line 5a) | `N18460`/`A18460`, "Limited state and local taxes" (line 5e) | 10,842,580 → 14,777,040 returns; $250.4B → $121.2B |
| same | `premium_tax_credit_returns` / `_amount` | `N85530`/`A85530`, "Additional Medicare tax" (Form 8959 line 24) | `N85770`/`A85770`, "Total premium tax credit" | 6,848,330 → 7,713,000 returns; $14.2B → $53.1B |
| `soi-historic-table-2`, `soi-historic-table-2-state-broad-2022` | `qbi_claims` / `qbi_amount` | `N03270`/`A03270`, "Self-employment health insurance deduction" (Schedule 1 line 17) | `N04475`/`A04475`, "Qualified business income deduction" (Form 1040 line 13) | 3,711,990 → 25,430,690 returns; $31.3B → $215.7B |

Historic Table 2 already read `N18460` and `N85770` for the same measure ids.
The TY2022 guides print the premium tax credit's form as "8926"; the TY2023
Historic Table 2 guide prints 8962 for the same variables.

### Schedule A line 8a relabel

| Packages | Columns | Old measure id / concept | New measure id / concept |
|---|---|---|---|
| `soi-congressional-district-2022` | `N19300` | `interest_paid_deduction_returns` / `irs_soi.returns_with_interest_paid_deduction` | `mortgage_interest_paid_returns` / `irs_soi.returns_with_home_mortgage_interest_paid_to_financial_institutions` |
| same | `A19300` | `interest_paid_deduction_amount` / `irs_soi.interest_paid_deduction` | `mortgage_interest_paid_amount` / `irs_soi.home_mortgage_interest_paid_to_financial_institutions` |

Labels become Table 2.1's: "Returns with home mortgage interest paid to
financial institutions" and "Home mortgage interest paid to financial
institutions amount". Unlike the 2026-09-27 rename, `measure_id` and
`source_record_id` move too, so the consumer selector moves.

**Why.** The guide defines `N19300`/`A19300` as mortgage interest paid,
Schedule A line 8a. `interest_paid_deduction_*` is Table 2.1's line 10 total,
and the 2022 Schedule A computes line 10 as lines 8a, 8b, 8c and 9 combined
(line 8d is reserved). No geographic file publishes line 10. For TY2022 the
district file's US `A19300` is $140.1B, 0.984 of Table 2.1's line 8a and 0.822
of its line 10 ($170.5B).

**Added.** The line 8b, 8c and 9 columns, with Table 2.1's ids, concepts and
labels: `home_mortgage_personal_seller_*` (`N19500`/`A19500`),
`deductible_points_*` (`N19530`/`A19530`) and `investment_interest_paid_*`
(`N19570`/`A19570`). The four amounts sum to line 10: $163.7B for the TY2022
US row, 0.960 of Table 2.1's. Return counts do not add, because one return can
report more than one line.

**Consumer effect.** Microcosm's SOI compiler (main, 2026-10-12) selects facts
by `measure_id` and skips ids it does not map. On its next Chronicle feed
re-pin:

- The district line 8a rows stop mapping to `interest_deduction`. Microcosm
  leaves `mortgage_interest_paid_*` unmapped on purpose, so those district
  targets drop, and its `state_cd` bridge entries for `interest_paid_deduction_*`
  stop matching. The 8b, 8c and 9 ids are unmapped too. How to use the
  district rows is Microcosm's decision; the line 8a rows keep
  `layout.source_column_id` `N19300`/`A19300`, so a selector keyed on the IRS
  column still finds them.
- The district SALT and PTC rows carry the corrected columns.
  microcosm#1224's register keyed on `N18425`/`A18425` and `N85530`/`A85530`
  stops matching them, and its pinned receipt test needs updating.
- Microcosm maps no Historic Table 2 `qbi_*` measure, so the QBI fix moves no
  Microcosm target.

**Pinned by** `tests/test_chronicle_soi_doc_guide_columns.py`. It maps every
`measure_id` declared by a package that reads an IRS-variable file (Historic
Table 2, congressional-district or county, any vintage) to one guide
definition. It then checks that every compiled cell selector reads the column
that definition names. Row-level column overrides and header guards count, as
the build reads them. Measure ids shared across packages must read one column.
The line 10 ids may not be read from a geographic file. Two differential checks
compare published values: the district US row against Historic Table 2's, and
the line 8a column and four-part sum against Table 2.1. A property check holds
every limited SALT row to the $10,000 line 5e cap, within publisher rounding.
