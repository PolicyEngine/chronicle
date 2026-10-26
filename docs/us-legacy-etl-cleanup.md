# US legacy ETL cleanup

Chronicle's rule is that every fact value traces to a publisher
(`AGENTS.md`). The legacy loaders in `db/etl_*.py` predate the source-package
architecture and write rows into the SQLite `targets` table through
`chronicle load <source>`. `docs/adr-chronicle-fact-identity-v2.md` ("Legacy
Migration") treats those rows as compatibility inputs, not production facts.
This page records the audit of the 14 US loaders and what happened to each
series, in the same form as the UK "Legacy ETL cleanup" table in
`docs/pe-uk-source-checklist.md` (chronicle#135).

| Loader | Outcome | Why |
|---|---|---|
| `db/etl_soi.py` | retired with the table | Parsed the IRS Table 1.1 and 1.4 workbooks committed under `db/data/irs_soi/` and checked each against its manifest sha256. Its values were publisher-backed, but they only fed the legacy `targets` table, which nothing read. The `soi-table-1-1` and `soi-table-1-4` packages publish the same cells as facts. |
| `db/etl_snap.py` | retired with the table | Copied facts from the `usda-snap-fy69-to-current` source package (chronicle#81) into the legacy `targets` table. The package itself still publishes them. |
| `db/etl_soi_state.py`, `db/etl_soi_credits.py`, `db/etl_soi_deductions.py`, `db/etl_soi_income_sources.py` | retired | Invented values presented as IRS figures (below). |
| `db/etl_aca_enrollment.py`, `db/etl_bls.py`, `db/etl_cbo.py`, `db/etl_census.py`, `db/etl_cps.py`, `db/etl_medicaid.py`, `db/etl_ssa.py`, `db/etl_ssi.py` | retired | Hand-typed values with landing-page URLs and no artifact; each module mixes transcribed, rounded, computed and invented numbers (below). |

Until the legacy targets table was retired, a boundary test ran `chronicle load
all` and required every row it wrote to reproduce its own publisher cell (with
27 mutation cases). With the table gone, boundary tests
(`tests/test_chronicle_boundaries.py`) check instead that none of the 14 modules
ships or imports, that no `db/etl_*.py` loader remains, that the CLI rejects
`chronicle load`, `stats` and `query`, and that `chronicle init` creates only the
source-artifact tables.

## Consumers

No current reader outside Chronicle was found in the default branches
searched. Inside Chronicle the loaders were reached only through `db/cli.py` (`chronicle load <source>`, and `load all`,
which CI's surface job ran until the targets table was retired), the re-exports in `chronicle/targets/loaders.py`
and `chronicle/jurisdictions/us/__init__.py`, and their own tests. The legacy
`targets` table is not part of the source-package bundle, the consumer-fact
export or the hosted mirror (`chronicle/mirror.py` exports only the
source-package tables), so no Microcosm pin carried these values. A search of
the main branch of every local PolicyEngine, Axiom and CosilicoAI clone, and a
GitHub code search of those organizations, found no other current reader of
the loaders, `chronicle.targets.loaders` or `chronicle.jurisdictions.us`. A
wider audit of the whole legacy `targets` path, which also shallow-cloned every
repository in those organizations, found three historical readers, all now in
archived repositories: microplex-us's Arch SQLite target provider, which read
the whole table until it was deleted on 2026-06-08; microplex's calibration
script, which read the older `microplex` Supabase schema; and cosilico-microdata, whose `targets_db.py` imported
`db.schema` and whose integration tests called `load_soi_targets` and
`load_snap_targets`. Which of the retired
rows they consumed is not verified.

## Retired: invented IRS SOI state values

Four loaders presented invented numbers as IRS Statistics of Income figures,
with IRS source URLs on every row. Their own comments said so, and the values
do not match the IRS files for the years they claim. On main,
`chronicle load all` wrote 5,326 rows from them: 3,366 from `soi-state`, 306
from `soi-credits`, 1,144 from `soi-income-sources` and 510 from
`soi-deductions`.

| Module | What its comments said | Rows it wrote |
|---|---|---|
| `db/etl_soi_state.py` | "Representative data for all 50 states + DC (2021 tax year)"; the AGI-band rows came from `_generate_agi_bracket_data`, "Generate synthetic AGI bracket distribution based on state totals ... approximate distribution patterns" | state returns, AGI and tax liability for 2020 and 2021, and the same three split into 10 AGI bands with one fixed share vector for every state |
| `db/etl_soi_credits.py` | "Values scaled by state population and poverty rates"; the national by-children blocks: "Representative 2021 data (national distribution)" | state EITC, CTC and ACTC claims and amounts for 2021. Its national EITC, CTC and ACTC by-children loaders (`load_*_by_children_targets`) were called only from its own tests. |
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
that have a matching IRS column, 6 are within 0.5% of the IRS figure. Three
series named no IRS line, so they are compared with the nearest column and
marked as proxies below.

| Legacy series (2021, 51 geographies) | IRS column | Within 0.5% | Median error | Example, legacy vs IRS |
|---|---|---|---|---|
| state AGI | `A00100` | 0 | 14.6% | NY $1,456.8B vs $1,068.8B |
| state tax liability | `A10300` total tax liability, proxy (also 0 within 0.5% against `A06500` and `A05800`) | 0 | 50.6% | WA $29.9B vs $74.3B |
| state EITC claims | `N59660` | 0 | 18.4% | FL 1,876,000 vs 2,688,720 |
| state CTC amount | `A07225` | 0 | 770.9% | ID $465M vs $40.8M |
| state ACTC amount | `A11070` | 0 | 75.6% | NJ $597M vs $2,817.6M |
| state SALT amount | `A18300` total taxes paid, proxy | 0 | 69.5% | TN $2,475M vs $1,076M |
| state mortgage interest amount | `A19300` interest paid, proxy | 0 | 24.6% | CA $12.3B vs $34.7B |
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
| `db/etl_soi_deductions.py` `mortgage_interest_claims`, `mortgage_interest_amount` (state) | state: `soi-congressional-district-2022` `interest_paid_deduction_*` (`N19300`/`A19300`, state rows for all 51 geographies; chronicle#345 relabels the column as Schedule A line 8a home mortgage interest); national: `soi-table-2-1` `mortgage_interest_paid_*` | None for 2022. |
| `db/etl_soi_deductions.py` `charitable_claims`, `charitable_amount` (state) | state: `soi-congressional-district-2022` `charitable_*` (`N19700`/`A19700`, state rows for all 51 geographies); national: `soi-table-2-1` `charitable_*` | None for 2022. |
| `db/etl_soi_deductions.py` `medical_claims`, `medical_amount` (state) | `soi-historic-table-2-state-broad-2022` `medical_dental_expense_*` | None for 2022. |
| `db/etl_soi_deductions.py` `qbi_claims`, `qbi_amount` (state) | `soi-congressional-district-2022` `qualified_business_income_deduction_*` (`N04475`/`A04475`, state rows for all 51 geographies); `soi-historic-table-2-state-broad-2022` `qbi_claims`, `qbi_amount` | None for 2022. The broad package's `qbi_*` read `N03270`/`A03270` on main; chronicle#345 repins them to `N04475`/`A04475`. |
| `db/etl_soi_income_sources.py` taxable and tax-exempt interest, ordinary and qualified dividends, Schedule C, partnership and S corporation, rental and royalty (national and state) | national: `soi-historic-table-2` (US row); state: `soi-historic-table-2-state-broad-2022` `taxable_interest_*`, `tax_exempt_interest_*`, `ordinary_dividends_*`, `qualified_dividends_*`, `schedule_c_income_*`, `partnership_scorp_income_*`, `rental_royalty_income_*` | None for 2022. |
| `db/etl_soi_income_sources.py` `short_term_capital_gains_*`, `long_term_capital_gains_*` | `soi-historic-table-2`, `soi-historic-table-2-state-broad-2022` and `soi-table-1-4` publish net capital gain (`net_capital_gains_*`) only | Gap: no packaged table splits gains into short and long term. |
| `db/etl_soi_income_sources.py` `state_local_refunds_*` | — | Gap: HT2 publishes `N00700`/`A00700`, but no package selects it. |
| `db/etl_soi_income_sources.py` `alimony_received_*` | national: `soi-table-1-4` `alimony_received_*` | Gap at state grain: no package carries state alimony. |

## Retired: hand-typed values from other publishers

These eight loaders cite a publisher landing page on every row but read no
artifact. Checked against the publishers' own tables, each mixes transcribed
numbers with rounded, computed and invented ones.

| Module | Rows on main | Evidence |
|---|---|---|
| `db/etl_aca_enrollment.py` | 223 (OEP 2023-2025) | State plan selections match the CMS state-level OEP files Chronicle packages for 10 of 51 states in 2024 and in 2025, and the misses include digit runs (2024: WY 24,567 vs 42,293, AL 235,678 vs 386,195; 2025: AL 268,857 vs 477,838, TN 398,765 vs 642,867). Metal-level enrollment is computed by Chronicle as a two-digit share times total enrollment (`apply_share`), and national APTC recipients are written as "~92% of enrollees". |
| `db/etl_census.py` | 120 (2021-2023) | The 18 national age groups are rounded to thousands except 85+, which carries the last three digits of the total population in every year (4,938,895 against 334,914,895) and in 2023 makes the groups sum exactly to it. State household counts are digit runs (CA 14,234,000, FL 8,765,000, NY 7,654,000). |
| `db/etl_medicaid.py` | 93 (2021-2025) | In 2025, after the five largest states, the state totals descend in digit runs ( IL 2,987,000, OH 2,654,000, MI 2,456,000, NJ 1,987,000, AZ 1,876,000, WA 1,765,000, MA 1,654,000, VA 1,543,000). National child and adult enrollment are written as "48% of total" and "52% of total". |
| `db/etl_ssa.py` | 30 (2021-2023) | The 2023 SSI rows disagree with SSA's Annual Statistical Supplement 2024 Table 7.A1 for December 2023 (aged 1,100,000 vs 1,160,789; blind 67,000 vs 63,886) and with `db/etl_ssi.py` for the same month (7,400,000 vs 7,425,331 recipients). The 2022 total benefits are $1,234,000,000,000. In each year the four beneficiary categories sum exactly to the total beneficiaries, while their benefits fall $78B to $130B short of total benefits. |
| `db/etl_ssi.py` | 133 (2021-2023) | The December 2023 total of 7,425,331 recipients matches Table 7.A1, but the category counts do not (aged 1,160,608 vs 1,160,789; disabled 6,199,817 vs 6,200,656). Federal payments are labelled "# Approximately"; state payments are rounded to $50 million. |
| `db/etl_bls.py` | 18 (2021-2023) | Levels are rounded to 100,000 and miss BLS's annual averages by up to 2%: 2023 labor force 167,300,000 against 167,116,417, unemployed 6,200,000 against 6,079,917, and an unemployment rate of 3.7 against 3.6 (BLS API series LNU01000000, LNU03000000 and LNU04000000, mean of 12 months). Median weekly earnings were not checked. |
| `db/etl_cps.py` | 63 (9 months, 2023-2025) | 8 of 27 monthly rates match BLS's seasonally adjusted series as published today. January 2023 unemployment is 3.9 against 3.5 (LNS14000000); September 2025 labor force is 168,600,000 against 171,261,000 (LNS11000000). |
| `db/etl_cbo.py` | 110 (2024-2034) | Labelled CBO's February 2024 Budget and Economic Outlook, whose summary puts the fiscal 2024 deficit at $1.6 trillion, outlays at 23.1% of GDP and 2024 real growth at 1.5%. The module has $1,882B, 23.9% and 2.0%. |

### Where the publisher's values live

| ETL series | Chronicle package and measures | Gap |
|---|---|---|
| `db/etl_aca_enrollment.py` state and national plan selections, APTC recipients, average APTC | `cms-aca-oep-state-level` (2024 OEP), `cms-aca-oep-state-level-2022`, `cms-aca-oep-state-level-2025`: `marketplace_enrollment`, `aptc_recipients`, `average_monthly_aptc` by state; effectuated enrollment in `cms-aca-effectuated-enrollment-2022` and `kff-marketplace-effectuated-enrollment` | The OEP packages publish state rows only, so national totals are a gap, and the 2023 OEP file is not packaged. |
| `db/etl_aca_enrollment.py` average gross and net premium, CSR recipients | full-year effectuated enrollment, not open enrollment: `cms-aca-effectuated-enrollment-2022` `average_total_premium`, `average_premium_after_aptc`, `csr_enrollment` | Gap for the 2023-2025 open-enrollment periods. |
| `db/etl_aca_enrollment.py` new enrollees, metal-level shares and enrollment | — | Gap: no package carries these. Metal-level enrollment computed from a share would not be a Chronicle fact in any case. |
| `db/etl_census.py` national and state population, age groups | `census-pep-2024-national-age-sex`, `census-pep-2024-state-age-sex`, `census-pep-county-population-2024`, `census-population-projections-2023`; ACS age bands in `census-acs-s0101-national-age-2024`, `census-acs-s0101-state-age-2024`, `census-acs-s0101-congressional-district-age-2024` | The PEP packages publish 2024 in the module's 18 five-year bands plus the total (19 national and 969 state facts); 2021-2023 are not packaged. |
| `db/etl_census.py` household counts | `census-acs-s2201-congressional-district-snap-2024` (district households) | Gap: no national or state household-count package. |
| `db/etl_medicaid.py` total, Medicaid and CHIP enrollment by state | `cms-medicaid-chip-monthly-enrollment-december-2024`, `cms-medicaid-chip-monthly-enrollment-dataset` (December 2025) | Earlier months and the August reference month are not packaged. |
| `db/etl_medicaid.py` child and adult enrollment | `cms-medicaid-chip-monthly-enrollment-december-2024`, `cms-medicaid-chip-monthly-enrollment-dataset`: `medicaid_chip_child_enrollment`, `total_adult_medicaid_enrollment` by state | Earlier months are not packaged. |
| `db/etl_medicaid.py` aged, disabled and expansion enrollment | — | Gap: no package carries these eligibility groups. |
| `db/etl_ssa.py` OASDI beneficiaries, benefits and average benefits by type | `ssa-annual-statistical-supplement-2025` (calendar 2024 payments by program) | Gap: beneficiary counts and average benefits, and years before 2024. |
| `db/etl_ssa.py` and `db/etl_ssi.py` SSI recipients and payments, national and by state | `ssa-ssi-table-7b1-2024` (recipients and payments by state and category), `ssa-ssi-monthly-statistics-2024-12`, `ssa-annual-statistical-supplement-2025` `ssi_payments` | Years before 2024 are not packaged. |
| `db/etl_ssi.py` federal payment and state supplementation amounts | — | Gap: `ssa-ssi-monthly-statistics-2024-12` carries federal-payment recipients by age, not amounts. |
| `db/etl_ssa.py` and `db/etl_ssi.py` `ssi_avg_monthly_payment` | — | Gap: no package carries average SSI payments. |
| `db/etl_bls.py` and `db/etl_cps.py` labor force, employment, unemployment and their rates; median weekly earnings | — | Gap: no BLS package. |
| `db/etl_cbo.py` GDP, revenue, outlays, deficit, debt, unemployment, CPI, 10-year rate, real growth, labor force | `cbo-individual-income-tax-receipts-2026-02`, `cbo-revenue-projections-income-by-source-2026-02` (February 2026 revenue projections) | Gap for every series the module wrote: the named packages carry historical individual income tax receipts and projected income components, not total revenue or any other series here, and no February 2024 vintage is packaged. |

The 12 modules, their tests, their `chronicle load` sources and their
re-exports are deleted. `db/etl_census.py`'s `load_congressional_district_targets`
took caller-supplied values and was called only from
`tests/test_congressional_districts.py`. That test file's last check pinned the
legacy `GeographicLevel` enum and went with it when the table was retired.
`DataSource` members stay: `SourceFact` and `SourceReference` still accept them.

## Retired: the legacy targets table

After the 12 loaders went, `etl_soi.py` and `etl_snap.py` were the only writers
of the SQLite `targets` / `strata` / `stratum_constraints` tables, and no live
consumer read those tables. The follow-on to chronicle#348 retired the whole path:

- `db/schema.py`'s `Target`, `Stratum` and `StratumConstraint` tables and the
  `TargetType` and `GeographicLevel` enums. `chronicle init` now creates only
  the source-artifact tables, which `load-source-files` and `source-stats` use.
- `chronicle load`, `chronicle stats` and `chronicle query` (`db/cli.py`).
- `db/etl_soi.py` and `db/etl_snap.py`, with their tests. The two AGI-bracket
  tables that `chronicle/jurisdictions/us/soi.py` imported from `etl_soi.py`
  now live in `soi.py`.
- `db/supabase_client.py`'s `query_targets`, `query_strata`,
  `insert_targets_batch` and `TARGETS_SCHEMA`.
- `chronicle/targets/loaders.py`, `chronicle/targets/client.py` and the legacy
  names re-exported by `chronicle.targets` and `policyengine_chronicle.targets`.
  Both modules keep the US poverty/nonfiler target source coverage
  (`chronicle/targets/us_poverty.py`).
- `chronicle.normalization`'s `as_target`, `target_kwargs` and
  `TargetBlueprint`, which built rows for the table. The lineage helpers
  (`convert_units`, `scale_value`, `apply_share`, `format_derivation`) stay, in
  `chronicle/normalization/transforms.py`.
- `scripts/export_to_json.py`, which wrote `targets_summary.json` from the table.

What the audit checked before deleting:

- **Chronicle itself.** No module under `chronicle/` reads the three tables.
  `chronicle/database.py` and `chronicle/mirror.py` work on their own ledger
  tables. The bundle, the consumer-fact export and the hosted mirror never
  carried the table.
- **Other repositories.** No current reader or writer (see Consumers above for
  the search and the three historical readers, all in archived repositories).
  Microcosm and chronicle.institute call `chronicle build-bundle` /
  `ledger build-bundle`, which this change does not touch.
- **Supabase.** Chronicle's configured project has no `targets` schema, so
  `query_targets` and `query_strata` failed with PostgREST `PGRST106 Invalid
  schema: targets`. The older copy of the three tables lives in that project's
  `microplex` schema. It was loaded in December 2025, has not been modified
  since 2026-01-02, and its last observed index read was on 2026-05-30.
  Apart from the audit's own probes, no request touched it in the 90 days of
  retained edge logs. This change leaves that hosted data alone.
- **Websites.** `targets_summary.json` was written for a CosilicoAI/cosilico.ai
  calibration page that was deleted on 2026-02-23. The script's
  `../policyengine.org` default path came from a later rename. No
  `PolicyEngine/policyengine.org` repository exists, policyengine.org returns
  404 for the file, and policyengine-app-v2 never read it.
- **Packaging.** Chronicle has never been published on PyPI under any of its
  names, and no repository installs it as a dependency.

The `codex/thesis-ledger-facts` branch carries its own frozen copy of the
legacy loaders, and its "Arch checks" job runs `arch load all`. Retiring the
path on `main` does not change that branch; chronicle#352 retires that copy.
