# Stats NZ household net worth, year ended June 2024

This package preserves Stats NZ's **Household net worth statistics: Year ended
June 2024**, published 26 September 2025, from the unchanged staged XLSX. It
emits 1,413 directly published estimates from the Household Economic Survey
(HES) for July 2023–June 2024. Chronicle represents that span as
`fiscal_year: 2023`, with `survey_reference` coverage from `2023-07-01` to
`2024-06-30` and the publisher's `Year ended June 2024` label. The artifact year
is pinned to 2024; other requested build years return these same observations.

The source supports the distribution work requested in
[microcosm#592](https://github.com/PolicyEngine/microcosm/issues/592).
B11's donor liquid-asset mapping belongs to Microcosm. This package records
only the publisher's assets, liabilities and net worth; it computes no cash
or liquid-asset measure. Added for microcosm#592; outside #176's 15.

## Coverage and units

| Worksheets | Published estimates | Numeric facts |
|---|---|---:|
| Table1.01 | Every asset/liability type, trust and crypto memorandum item; median, mean, total and household count | 120 |
| Table2.01–Table2.04 | Every asset/liability row × each net-worth quintile and All quintiles; median, mean, total and household count | 360 |
| Table3.01–Table3.04 | Every asset/liability row × each income quintile and All quintiles; median, mean, total and household count | 360 |
| Table5.01 | Every household characteristic and published Total; median, mean, total and household count | 100 |
| Table7.01–Table7.04 | Every asset/liability row × each individual age group and Total; median, mean, total and people count | 473 |

Only the first, 2024 block emits facts. The complete original **39-sheet
workbook bytes** remain in `db/data/stats_nz/household_net_worth_2024/`.
The parser preserves the whole used ranges of Contents and the 14 scoped
worksheets, including historical blocks, unused columns, footnotes and symbols.
The XLSX expresses every requested cut, so neither the staged CSV nor its
code dictionary is copied or consumed. No fact is duplicated from another file.

Values stay exactly in the publisher's **$000s** (`NZD_thousands`), household
**000s** (`household_thousands`) and people **000s** (`person_thousands`). No
scaling or further rounding occurs. Median and mean use the corresponding
Chronicle aggregation; separately published totals/counts use `sum` as their
measure type but select one cell, never a range or an arithmetic calculation.
Medians are cut-points. Quintile boundaries and counts are publisher groupings,
not constructed percentiles or sums of quintiles. Every dimension and value
has a label. Publisher spelling and footnote markers remain; trailing spaces
remain verbatim in source cells and layout row labels, while Chronicle trims
the outer whitespace of display dimension labels.
Region entries in Table5.01 remain labelled household-characteristic cuts of
the national HES table, without a constructed regional geography mapping.

`published_section` follows the workbook's bounded groups, including their
published subgroup totals. In Table1.01, bold A9 “Assets” is the parent header;
bold A18 “Shares and other equity” starts the subgroup, which ends at bold B23
“Total shares and other equity”. B24 “Mutual funds and other investment funds”,
B25 “Pension funds”, B26 “Other household financial assets” and bold B27
“Household financial assets” return to the Assets parent, ending before bold
A28 “Total household assets”. They carry the Assets section and A9 lineage
guard, rather than the shares-and-equity section. No numeric value changes.

The independent grouping regression checks every section's exact member rows
in facts and exported consumer `universe_constraints`. The audited boundaries
below exclude header rows and separately published A-column overall totals:

| Worksheets | Section headers and selected member rows (2024 block) |
|---|---|
| Table1.01 | Assets A9: 10–17, 24–27; Shares and other equity A18: 19–23; Liabilities A29: 30–34; Trust memorandum items A37: 38–41; Crypto memorandum items A42: 43 |
| Table2.01, Table2.02, Table2.04; Table3.01, Table3.02, Table3.04 | Assets A9: 10–17; Liabilities A19: 20–24 |
| Table2.03, Table3.03 | Assets A8: 9–16; Liabilities A18: 19–23 |
| Table5.01 | Household size(4)(5) A9: 10–14; Household composition A15: 16–24; Tenure of household(10) A25: 26–30; Region A31: 32–36 |
| Table7.01, Table7.02, Table7.04 | Assets A10/A28: 11–18, 29–36; Liabilities A20/A38: 21–24, 39–42 |
| Table7.03 | Assets A9/A27: 10–17, 28–35; Liabilities A19/A37: 20–23, 38–41 |

Tables2/3 apply the six literal quintile column headers to all selected asset,
liability and overall-total rows. Tables7 apply the eight literal age group
headers across two blocks of four columns, each with its own asset and
liability sections. Suppressed `S` cells remain excluded from all section
memberships. Independent workbook-coordinate
checks enumerate every numeric estimate in the Median, Mean, Total and count
columns of all 14 current blocks, requiring exactly one selection per cell.

## Population and evidence

Population notes are verbatim fact dimensions, concept evidence and guarded
source-cell lineage. The distinctions are material:

- **Table1.01**: “For each asset and liability type, the population for this
  table is those households that have a non-zero value.” Asset means and
  medians therefore describe holders. Its net-worth median at C36 is **529**.
- **Tables2/3 .01 and .02**: all households, with publisher-assumed zero
  for households not recording a particular asset/liability. The .04 count
  tables explicitly describe non-zero holders. The .03 total tables have no
  population note; no population note is inferred for them.
- **Table5.01**: means and medians include households with zero net worth;
  counts describe non-zero holders. Its national Total median at C37 is
  **525**, also independently published at Tables2.01/3.01 M25. These remain
  separate source facts, without reconciling them with Table1.01's 529.
- **Tables7 .01 and .02**: all people aged 15+, including publisher-assumed
  zero values. The .04 counts describe non-zero holders. The .03 totals have
  no population note. Individual figures are read from individual tables,
  never converted from household estimates.

Each selector checks the publisher title, reference block, estimate/group
header, unit, row/section labels, population note where present, and all
footnotes/symbol definitions. Explicit guards attach these text cells to fact
lineage. Seven suppressed estimate cells remain source text, with no numeric
fact: Table7.01 C12/C22/K40/K41, Table7.02 C22, Table7.03 C21 and Table7.04 C22.
Their exact `S` symbols and suppression definitions are preserved and guarded.
The workbook's `...` (not applicable) and `R` (revised) symbols also remain
verbatim source cells, including in unselected historical/error columns.

The active declarative `AggregateFact`, record specs and consumer contract
have **no sampling-error field**. The legacy `SourceFact.margin_of_error` field
is a separate ingestion path and does not represent relative sampling errors
in percent. Relative sampling errors are therefore omitted from emitted facts
and preserved as source cells. Percentage-change columns and their sampling
errors are also omitted from facts and preserved in source cells. No error or
suppression is replaced with zero.

## Artifact and licence

The manifest is copied from the hub receipt: SHA-256
`2fb942322e5131824a15007e7b0742c4f8220822c7e8f9adee83bae154913f9e`,
386,546 bytes, fetched `2026-10-10T08:31:08Z`. Its immutable
`raw/nz/stats_nz/household_net_worth_2024/2024/...` key is built with
`chronicle.artifacts.build_r2_key`. The hub published the object with
`chronicle publish-raw` and verified it by streaming it back (SHA-256
matches) on 2026-10-10.

Licence: **CC BY 4.0**, attribution **Stats NZ**, per the hub's 10 October 2026
verification of <https://www.stats.govt.nz/about-us/copyright/>.

## Targeted validation

```sh
python -m policyengine_chronicle.cli validate-package stats-nz-household-net-worth-2024 --year 2024
python -m policyengine_chronicle.cli build-suite stats-nz-household-net-worth-2024 --year 2024 --out .hub-scratch/net-worth-suite --replace
python -m pytest tests/test_chronicle_nz_household_net_worth.py -p no:cacheprovider --basetemp=.hub-scratch/pytest -o tmp_path_retention_policy=failed
```

Source-package changes require the Chronicle `ledger-source-fidelity` and
`ledger-boundary` reviews before merge. Consumers own selection, alignment and
measurement; this package performs no aging, imputation or reconciliation.
