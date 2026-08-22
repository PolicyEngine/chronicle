# Final report: chronicle#179 passive pass-through anchors

## Result

Implemented and validated the TY2023 passive pass-through administrative
anchors requested in chronicle#179. The work adds 20 Form 8960 facts and
extends the existing Publication 1304 Table 1.4 record set with 160 partnership
and S corporation facts, for 180 net-new TY2023 facts. Every affected record set
and fact has `provenance_class: administrative`.

No network access, fetch, push, or pull request was used.

## Record sets and fact counts

Form 8960 package ID: `soi-form-8960-2023`.

Each Form 8960 record set has one all-filers row and two facts: a return count
and a USD amount. The ten record sets therefore emit 20 facts:

- `irs_soi.ty2023.form_8960.line_1`
- `irs_soi.ty2023.form_8960.line_2`
- `irs_soi.ty2023.form_8960.line_3`
- `irs_soi.ty2023.form_8960.line_4a`
- `irs_soi.ty2023.form_8960.line_4b`
- `irs_soi.ty2023.form_8960.line_4c`
- `irs_soi.ty2023.form_8960.line_5d`
- `irs_soi.ty2023.form_8960.line_8`
- `irs_soi.ty2023.form_8960.line_12`
- `irs_soi.ty2023.form_8960.line_17`

Publication 1304 package ID: `soi-table-1-4`.

- Existing record set extended: `irs_soi.ty2023.table_1_4`.
- TY2023 total: 20 AGI rows × 37 measures = 740 facts.
- Net-new partnership and S corporation slice: 20 rows × 8 measures = 160
  facts.
- Complete Schedule E entity slice, including the four existing estate/trust
  measures: 20 rows × 12 measures = 240 facts.
- TY2020 remains at its original 29 measures and 580 facts because that
  publication combines partnership and S corporation values. The new separate
  measures are source-accurately scoped to TY2021–TY2023.

Amounts are normalized from published thousands of dollars to `unit: usd`
with `value_scale: 1000`; return counts use `unit: count`. Table 1.4 net-loss
amounts remain the publisher's positive magnitudes.

## Source identity and scope notes

Form 8960 is pinned to:

- URL: `https://www.irs.gov/pub/irs-pdf/p4801.pdf`
- Vintage: `tax_year_2023_rev_6_2026`
- Publication identity: Publication 4801 (Rev. 6-2026), pages 214–215
- Curated source artifact SHA-256:
  `a831947133806455b971560102bf6d7710865ece481616844bead7c9b81958fd`
- Supervisor-verified extract SHA-256:
  `1cafe8a381e83c5365b6a2ef54695ac6b4beca369eb61338169e24f2581ef080`
- Full Publication 4801 transcript SHA-256:
  `0c157394542a0b3e2cbfe361d6ac4c744568c6476bada9d7a7647470b54a9364`

Table 1.4 is pinned to:

- URL: `https://www.irs.gov/pub/irs-soi/23in14ar.xls`
- SHA-256:
  `b6c1f87fbb5533417e195f6938538e5de09b6a0825a6a54346bf9363a18d96af`
- Size: 115,712 bytes

The source-package description and manifest document the identified data
boundary: IRS SOI entity-side partnership tables 23pa01, 23pa04, 23pa06,
23pa10, and 23pa23 provide no passive/nonpassive split by industry, while Table
1.4 provides entity income and loss without a passive split. Form 8960 line 4
is therefore the sole administrative anchor for the passive pass-through NIIT
base.

## Form 8960 line 4 reconciliation

The publisher's displayed amounts in thousands do not satisfy literal equality:

- Line 4a: `$1,185,607,258,000`
- Line 4b: `-$1,076,350,273,000`
- Their sum: `$109,256,985,000`
- Published line 4c: `$109,256,984,000`
- Residual: `$1,000`, exactly one published reporting unit

The ingestion preserves all publisher values. The unit-level consistency test
asserts the exact `$1,000` residual and reconciliation within one reporting
unit; forcing exact equality would falsify one of the supplied source values.

## Microcosm concept IDs

The primary passive-plus-rental NIIT base is:

- `irs_soi.form_8960.line_4c`

Its associated line 4 inputs and counts are:

- `irs_soi.form_8960.line_4a`
- `irs_soi.form_8960.line_4a.return_count`
- `irs_soi.form_8960.line_4b`
- `irs_soi.form_8960.line_4b.return_count`
- `irs_soi.form_8960.line_4c.return_count`

The other Form 8960 concepts are:

- `irs_soi.form_8960.line_1`
- `irs_soi.form_8960.line_1.return_count`
- `irs_soi.form_8960.line_2`
- `irs_soi.form_8960.line_2.return_count`
- `irs_soi.form_8960.line_3`
- `irs_soi.form_8960.line_3.return_count`
- `irs_soi.form_8960.line_5d`
- `irs_soi.form_8960.line_5d.return_count`
- `irs_soi.form_8960.line_8`
- `irs_soi.form_8960.line_8.return_count`
- `irs_soi.form_8960.line_12`
- `irs_soi.form_8960.line_12.return_count`
- `irs_soi.form_8960.line_17`
- `irs_soi.form_8960.line_17.return_count`

The Table 1.4 entity concepts are:

- `irs_soi.partnership_net_income`
- `irs_soi.returns_with_partnership_net_income`
- `irs_soi.partnership_net_loss`
- `irs_soi.returns_with_partnership_net_loss`
- `irs_soi.s_corporation_net_income`
- `irs_soi.returns_with_s_corporation_net_income`
- `irs_soi.s_corporation_net_loss`
- `irs_soi.returns_with_s_corporation_net_loss`
- `irs_soi.estate_and_trust_net_income`
- `irs_soi.returns_with_estate_and_trust_net_income`
- `irs_soi.estate_and_trust_net_loss`
- `irs_soi.returns_with_estate_and_trust_net_loss`

## Validation results

- `ruff check chronicle policyengine_chronicle db scripts tests`: passed.
- Governance, boundary, facts-only, consumer-contract, alias-drift, and Form
  8960 focused tests: 67 passed.
- Full `pytest -q`: 650 passed, 1 skipped, 0 failed in 27m22s. The skip and 14
  dependency warnings are pre-existing/non-blocking.
- `validate-package soi-form-8960-2023 --year 2023`: valid; 10 record sets, 20
  measures, 20 source records, 10 regions.
- `build-suite soi-form-8960-2023 --year 2023`: valid; 20 facts and consumer
  facts, 66 source cells, 10 source rows, 10 regions, lineage coverage 1.0, no
  acceptance errors.
- `validate-package soi-table-1-4 --year 2023`: valid; 1 record set, 37
  measures, 20 rows, 740 source records, 1 region.
- `build-suite soi-table-1-4 --year 2023`: valid; 740 facts and consumer facts,
  8,109 source cells, 1 region, lineage coverage 1.0, no acceptance errors.
- Direct Table 1.4 fact builds for TY2020–TY2023: valid; 580, 740, 740, and 740
  facts respectively.
- Canonical merged-bundle test: passed; 145,402 facts across 121 included source
  packages, including 33,957 IRS SOI facts.

The repository has no Makefile. All checks used its Python harness and pytest
suite through the existing offline virtual environment.

## Changelog

The functional change fragment is `changelog.d/179.added.md`, following the
parent PolicyEngine repository convention. `CHANGELOG.md` was not edited
manually.
