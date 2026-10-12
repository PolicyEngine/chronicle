# US legacy ETL cleanup

Chronicle's rule is that every fact value traces to a publisher
(`AGENTS.md`). The legacy loaders in `db/etl_*.py` predate the source-package
architecture: they write hand-typed numbers into the SQLite `targets` table
through `chronicle load <source>`. `docs/adr-chronicle-fact-identity-v2.md`
("Legacy Migration") treats those rows as compatibility inputs, not production
facts. This page records the audit of the US loaders and what happened to each
series, in the same form as the UK "Legacy ETL cleanup" table in
`docs/pe-uk-source-checklist.md` (chronicle#135).

## Retired: invented IRS SOI state values

Four loaders presented invented numbers as IRS Statistics of Income figures,
with IRS source URLs on every row. Their own comments said so, and the values
do not match the IRS files for the years they claim.

| Module | What its comments said | Rows it wrote |
|---|---|---|
| `db/etl_soi_state.py` | "Representative data for all 50 states + DC (2021 tax year)"; the AGI-band rows came from `_generate_agi_bracket_data`, "Generate synthetic AGI bracket distribution based on state totals ... approximate distribution patterns" | state returns, AGI and tax liability for 2020 and 2021, and the same three split into 10 AGI bands with one fixed share vector for every state |
| `db/etl_soi_credits.py` | "Values scaled by state population and poverty rates"; the national by-children blocks: "Representative 2021 data (national distribution)" | state EITC, CTC and ACTC claims and amounts for 2021; national EITC, CTC and ACTC by number of children for 2021 |
| `db/etl_soi_deductions.py` | "Representative data by state, scaled by population and income levels" | state SALT, mortgage interest, charitable, medical and QBI claims and amounts for 2021 |
| `db/etl_soi_income_sources.py` | state block: "representative 2021 data scaled by state population and income levels"; national block: "Values are from 2021 tax year" | national and state returns and amounts for 11 income sources, 2021 |

### Evidence

**Fixed amounts per claim.** In `SOI_DEDUCTIONS_DATA`, every state's medical
amount is exactly $6,000 per claim and every state's QBI amount exactly $7,000
per claim (51 of 51 geographies each); charitable is $2,000 and mortgage
interest $8,000 per claim in 50 of 51. In `SOI_CREDITS_DATA`, 34 of 51 ACTC
amounts are exactly $1,500 per claim.

**Digit runs.** `SOI_STATE_DATA` gives Alabama 2,234,567 returns and
$134,567,000,000 of AGI and Arizona 3,456,789 returns and $234,567,000,000. The
national income-source block gives 54,876,543 taxable-interest returns,
8,765,432 tax-exempt-interest returns, $876,543,000,000 of long-term capital
gains, and 12,345,678 for both short-term-gain and rental returns.

**Same-year comparison with the IRS files.** Historic Table 2 for tax years
2020 and 2021 (`https://www.irs.gov/pub/irs-soi/20in55cmcsv.csv`, sha256
`01da5c0e510685d19fe47fe1c960f217d20208f31f66c7dbd2892feba7d2ace2`, and
`https://www.irs.gov/pub/irs-soi/21in55cmcsv.csv`, sha256
`eb12920d565b773d895e84cb4188119f13ffd664c04579ed6e7ccc7d298a0a2d`) publishes
the same state rows for the same years. Of the 1,581 state values for 2021
that have a column of the same meaning, 6 are within 0.5% of the IRS figure.

| Legacy series (2021, 51 geographies) | IRS column | Within 0.5% | Median error | Example, legacy vs IRS |
|---|---|---|---|---|
| state AGI | `A00100` | 0 | 14.6% | NY $1,456.8B vs $1,068.8B |
| state tax liability | `A10300` (also 0 against `A06500` and `A05800`) | 0 | 50.6% | WA $29.9B vs $74.3B |
| state EITC claims | `N59660` | 0 | 18.4% | FL 1,876,000 vs 2,688,720 |
| state CTC amount | `A07225` | 0 | 770.9% | ID $465M vs $40.8M |
| state ACTC amount | `A11070` | 0 | 75.6% | NJ $597M vs $2,817.6M |
| state SALT amount | `A18300` | 0 | 69.5% | TN $2,475M vs $1,076M |
| state mortgage interest amount | `A19300` | 0 | 24.6% | CA $12.3B vs $34.7B |
| state charitable amount | `A19700` | 0 | 72.5% | AR $486M vs $5,292M |
| state QBI amount | `A04475` | 0 | 63.9% | FL $4.58B vs $17.66B |
| state taxable interest amount | `A00300` | 0 | 252.0% | DE $1,543M vs $199.5M |
| state refunds amount | `A00700` | 0 | 853.5% | TX $1,654M vs $32.1M |

For 2020 the state module's AGI and tax liability match 0 of 51 states. The
national block is off by factors of 2.7 (taxable interest amount) and 8.5
(state and local refunds amount) against the HT2 US row. The national EITC
by-children rows (7M, 8M, 6M and 4M claims) sum to 25 million claims; the IRS
counted 32,067,810. The retired tests pinned the invented levels: for example
`tests/test_etl_soi_credits.py` asserted `20_000_000 < all_eitc_claims <
30_000_000`, a range that excludes the published value.

### Consumers

Nothing outside Chronicle read these rows. Inside Chronicle the loaders were
reached only through `db/cli.py` (`chronicle load soi-state | soi-credits |
soi-income-sources | soi-deductions`, and `load all`, which CI's surface job
runs), the re-exports in `chronicle/targets/loaders.py` and
`chronicle/jurisdictions/us/__init__.py`, and their own tests. The legacy
`targets` table is not part of the source-package bundle, the consumer-fact
export or the hosted mirror (`chronicle/mirror.py` exports only the
source-package tables), so no Microcosm pin carried these values.

### Where the publisher's values live

| ETL series | Chronicle package and measures | Gap |
|---|---|---|
| `db/etl_soi_state.py` `tax_unit_count`, `adjusted_gross_income` (state) | `soi-historic-table-2-state-broad-2022` `return_count`, `adjusted_gross_income`; `soi-historic-table-2-state-agi-2023` | Tax years 2020 and 2021 are not packaged. |
| `db/etl_soi_state.py` `income_tax_liability` (state) | `soi-historic-table-2-state-broad-2022` `income_tax_liability_*` (`A06500`), `income_tax_before_credits_*` (`A05800`) | The legacy rows named no IRS line, so neither measure is a like-for-like replacement. |
| `db/etl_soi_state.py` AGI-band rows | `soi-historic-table-2-state-agi-2022` and `soi-historic-table-2-state-agi-2023` (state × AGI band returns and AGI) | No packaged state × AGI-band tax liability. |
| `db/etl_soi_credits.py` `eitc_claims`, `eitc_amount` (state) | `soi-historic-table-2-state-eitc-2022` `eitc_claims`, `eitc_amount` | None for 2022. |
| `db/etl_soi_credits.py` `ctc_claims`, `ctc_amount`, `actc_claims`, `actc_amount` (state) | `soi-historic-table-2-state-broad-2022` `ctc_*` (`N07225`/`A07225`), `actc_*` (`N11070`/`A11070`) | None for 2022. |
| `db/etl_soi_credits.py` EITC by number of children (national) | `soi-table-2-5-eitc-agi-children-2022`, `soi-table-2-5-eitc-agi-children-2023`; by state: `soi-historic-table-2-state-eitc-2022` `eitc_no_children_*` through `eitc_three_or_more_children_*` | None. |
| `db/etl_soi_credits.py` CTC and ACTC by number of children (national) | — | Gap: no packaged IRS table publishes CTC or ACTC by number of qualifying children. |
| `db/etl_soi_deductions.py` `salt_claims`, `salt_amount` (state) | `soi-historic-table-2-state-broad-2022` `limited_state_local_taxes_*`, `real_estate_taxes_*` | The legacy "SALT" named no IRS line; HT2's total-taxes-paid column (`N18300`/`A18300`) is not packaged at state grain. |
| `db/etl_soi_deductions.py` `mortgage_interest_claims`, `mortgage_interest_amount` (state) | national: `soi-table-2-1` `mortgage_interest_paid_*`; district: `soi-congressional-district-2022` | Gap at state grain: HT2 publishes `N19300`/`A19300`, but no package selects it for states. |
| `db/etl_soi_deductions.py` `charitable_claims`, `charitable_amount` (state) | national: `soi-table-2-1` `charitable_*`; district: `soi-congressional-district-2022` `charitable_*` | Gap at state grain: HT2 publishes `N19700`/`A19700`, but no package selects it for states. |
| `db/etl_soi_deductions.py` `medical_claims`, `medical_amount` (state) | `soi-historic-table-2-state-broad-2022` `medical_dental_expense_*` | None for 2022. |
| `db/etl_soi_deductions.py` `qbi_claims`, `qbi_amount` (state) | `soi-historic-table-2-state-broad-2022` `qbi_claims`, `qbi_amount` | None for 2022. On main these read `N03270`/`A03270`; chronicle#345 repins them to the QBI deduction columns `N04475`/`A04475`. |
| `db/etl_soi_income_sources.py` taxable and tax-exempt interest, ordinary and qualified dividends, Schedule C, partnership and S corporation, rental and royalty (national and state) | national: `soi-historic-table-2` (US row); state: `soi-historic-table-2-state-broad-2022` `taxable_interest_*`, `tax_exempt_interest_*`, `ordinary_dividends_*`, `qualified_dividends_*`, `schedule_c_income_*`, `partnership_scorp_income_*`, `rental_royalty_income_*` | None for 2022. |
| `db/etl_soi_income_sources.py` `short_term_capital_gains_*`, `long_term_capital_gains_*` | `soi-historic-table-2`, `soi-historic-table-2-state-broad-2022` and `soi-table-1-4` publish net capital gain (`net_capital_gains_*`) only | Gap: no packaged table splits gains into short and long term. |
| `db/etl_soi_income_sources.py` `state_local_refunds_*` | — | Gap: HT2 publishes `N00700`/`A00700`, but no package selects it. |
| `db/etl_soi_income_sources.py` `alimony_received_*` | national: `soi-table-1-4` `alimony_received_*` | Gap at state grain: no package carries state alimony. |

The modules, their tests, the four `chronicle load` sources and the loader
re-exports are deleted. `DataSource.IRS_SOI` stays: `db/etl_soi.py` still
writes it and existing databases carry the string.
