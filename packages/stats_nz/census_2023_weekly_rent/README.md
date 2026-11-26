# Stats NZ 2023 Census weekly rent by regional council

This package family emits 162 published facts from Stats NZ's
[Place summaries tool](https://tools.summaries.stats.govt.nz/): eight household
rent-band counts and one published median for New Zealand, each of the 16
regional councils, and the separately published `Area Outside Region`
(code `99`). Every fact reads one CSV row. No rent-band total is emitted.

The national root is `stats_nz/census_2023_weekly_rent`, with alias
`stats-nz-census-2023-weekly-rent`; its 17 `rc_XX/source_package.yaml` children
use aliases ending in `-rc-XX`. They reference the same 18 unchanged files
and per-place manifests as the
[household](../census_2023_households_by_region/README.md) and
[family-type](../census_2023_family_type/README.md) families in
`db/data/stats_nz/census_2023_place_summaries/`. No CSV or manifest is copied,
renamed, rewritten, or added. Their binary Git attributes preserve the exact
publisher CRLF bytes.

## Scope and source semantics

Each selection requires `period = 2023`, `duration = Census`, the place's
published code and descriptor, and the exact section and row identity:

| Section | Published categories | Value type | Facts per place |
| --- | --- | --- | ---: |
| Weekly rent paid by households | Under $200; $200 - $299; $300 - $399; $400 - $499; $500 - $599; $600 - $699; $700 - $799; $800 and over | Count | 8 |
| Median weekly rent paid by households | The table row with empty `section_type` | Median | 1 |

Band facts use a household count measure, unit `count`, and scale 1. The
median has its own `median` measure, unit `nzd_per_week`, scale 1, and
`aggregation: median`. It reads the published value rather than deriving a
median, mean, or band midpoint. The median section appears twice in every
file: the `Quick stats` row on physical CSV line 13 and the table row on
line 1763. The package selects only line 1763 by its row identity, including
empty `section_type`. Selecting the table occurrence follows the existing
families' treatment of duplicated quick statistics and keeps its table-row
provenance next to the rent bands. Equal values do not make the two row
identities interchangeable.

The population definition is **not stated in the product**: the committed
CSVs contain no note establishing whether these rows cover rented occupied
private dwellings with a stated rent. That qualification is therefore not
asserted. The dollar basis is weekly rent in New Zealand dollars at the
census date, as specified by the hub. The CSV supports the weekly basis in
the section title and labels the median `dollars`; it does not spell out the
currency name or a separate dollar-basis note.

The reference date is census night, **7 March 2023**, as specified by the
hub and recorded in coverage. The files themselves state `2023` and
`Census`, without printing the exact night. The regional boundary vintage
is unstated. Geography keys follow the existing Census families, including
`region:99` for `Area Outside Region`; it is never assigned to another
region. Auckland's consumer geography name is `Auckland`, while its source
row retains the exact descriptor `Auckland Region`.

New Zealand rows come from the national file. They are never reconstructed
from regional values, and the eight bands are never summed into another
fact. Published band labels retain their exact spelling and spacing,
including `$200 - $299`. Every emitted dimension and dimension value carries
a label. The complete source files retain `Percent` rows, 2013 and 2018
periods, sections `for the Māori ethnic group`, the duplicate quick-stat
median, and unrelated sections; none emits a fact in this family.

All 162 selected rows have empty `confidentiality_indicator`,
`confidentiality_label`, `final_indicator`, and `final_label`. Those fields
travel in the full source-row lineage. Selection requires them to be empty,
so a flagged row cannot become a numeric fact even if its value contains
numeric text. No rounding-method note is stated in the files, and blank
status fields are not treated as a declaration of revision-final status.

The parser preserves each complete 2,030-row CSV as source rows, then builds
compact selected cells under the Chronicle virtual sheet
`place_summaries_<nz|rc_XX>_weekly_rent`. These names are not publisher
worksheets. Their family suffix avoids cell-key collisions with the
household and family packages' different selected-row orders. Each selected
cell retains its original physical line number and source-row key.

See [publisher evidence](evidence.md) for exact cells and the already
published raw objects. No aging, interpolation, shares, reconciliation,
imputation, or consumer target construction is performed.

## Bounded validation

The targeted regression file is
`tests/test_chronicle_nz_census_weekly_rent.py`. It declares the expected
place, section, category and row identities independently of package YAML,
checks the exact New Zealand and Auckland cells, and rejects percentage,
historical-year, wrong-region, Māori-section, duplicate-median and adjacent
band-label substitutions. Package validation and single-source suites cover
all 18 members. Full bundle construction remains a CI check.

The shared raw objects were published and verified by the hub on
2026-10-10; this offline lane checked local hashes and sizes against all 18
existing manifests without network access. Licence: `CC BY 4.0`, with
attribution to Stats NZ. The required `ledger-source-fidelity` and
`ledger-boundary` judge reviews remain merge gates.
