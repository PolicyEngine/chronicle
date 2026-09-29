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
  37/38, "Sales of capital assets reported on Form 1040, Schedule D: Taxable
  net gain", which counts only Schedule D returns with a gain. For TY2022 the
  two counts are 30,465,850 and 12,915,122 returns. Historic Table 2's US count
  equals Table 1.4's capital-gain-distribution, taxable-net-gain and
  taxable-net-loss returns combined to within 0.25% in every year TY2020–TY2023.
- The congressional-district ids read as a gain-only amount. IRC section
  1222(11) and the Publication 1304 Explanation of Terms both use "net capital
  gain" for a positive amount only.
- The ids name the Form 1040 line rather than repeat the IRS phrase "net
  capital gain (less loss)". Publication 1304 Table A uses that phrase for
  Schedule D gain and loss returns without the distribution-only returns
  (TY2022: 26,480,998), so the phrase alone does not identify the population.

**Semantic keys.** Historic Table 2 and the congressional-district file now
share one concept for the same IRS variable, as they already did for 19 of the
31 IRS columns they share. Their TY2022 state and US rows therefore share
semantic keys, which adds 104 semantic-duplicate keys to the default bundle (51
states and the US, returns and amount). The values differ: the IRS guide for the
congressional-district file says its state totals "may not be comparable to
State totals published elsewhere by SOI because of disclosure protection
procedures or the exclusion of returns that did not match based on the ZIP
code." The Historic Table 2 and Table 1.4 rows no longer share a semantic key.

**Unchanged.** Table 1.4 keeps `irs_soi.returns_with_taxable_net_capital_gains`
/ `irs_soi.taxable_net_capital_gains`.

**Pinned by** `tests/test_chronicle_soi_capital_gain_concepts.py`: every
`irs_soi` package that reads `N01000`/`A01000` (any vintage) must declare the
new concept, only Table 1.4 may declare the Schedule D gain concept, the retired
ids may not reappear, and the consumer selector (`source_measure_id`) and
published values are unchanged.
