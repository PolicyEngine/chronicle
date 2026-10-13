# Stats NZ territorial-authority population, 30 June 2025

This package emits **67 publisher-backed estimated resident population (ERP)
counts**, one for each territorial authority in Table 2 of the unchanged
[29 October 2025 subnational population release workbook](https://www.stats.govt.nz/information-releases/subnational-population-estimates-at-30-june-2025/).
Each fact reads one column-E source cell, headed `2025 P`, with scale 1.
No population is computed from other cells.

| Source selection | Geography | Facts |
|---|---|---:|
| Table 2!E8:E11 and E33:E95, where column A names the territorial authority | TA 2025 | 67 |

The complete Table 2 used range is preserved as source cells, including
unselected values and footnotes. The workbook and its existing manifest are
shared with [the regional population package](../subnational_population_estimates_2025/README.md)
and are unchanged.

## Reference period and source semantics

- Reference date: **30 June 2025**, represented as `calendar_year: 2025` with
  equal start/end coverage dates `2025-06-30`. These are point-in-time counts,
  rather than annual averages.
- Publication vintage: **29 October 2025**. All admitted figures are
  **provisional**, retained in the source period label and concept evidence.
  The pinned source remains this vintage if the publisher later revises it.
- Population: all ages and all sexes, estimated resident population using the
  2023 census base, including adjustments for census under/overcount,
  residents temporarily overseas on census night, and subsequent births,
  deaths and net migration. No age-band or sex-specific fact is emitted.
- Provenance: `provenance_class: census` and `assertion: observation`, as in
  the regional package. A provisional historical ERP is still a publisher
  observation; these fields do not assert that its value is final.
- Concept: `stats_nz.estimated_resident_population`, with `source_label`
  relation and Stats NZ source evidence. No canonical equivalence or
  downstream population calibration is claimed.
- Geography boundaries: **1 January 2025**, recorded as
  `geography_level: local_authority`, `geography_id: nz-ta-NNN` with a
  three-digit TA code, and `geography_vintage: ta_2025`. This is the geography
  convention used by the MBIE tenancy-bond rent facts.

The separately pinned [Stats NZ TA 2025 classification](../../../db/data/stats_nz/territorial_authority_2025_codes/manifest.yaml)
contains 68 code/name/ASCII-name entries. Workbook headers match its
`TA2025_V1_00_NAME_ASCII` values after removing macrons and case-folding;
row order never assigns a code. Every admitted code is used once.
Code `999`, Area Outside Territorial Authority, has no workbook row and is
excluded. Each `geography_name` is the publisher's `TA2025_V1_00_NAME`, while
the value `label` is the exact workbook row text. For example, `nz-ta-002`
has geography name `Whangarei District` and value label `Whangārei district`.
The `geography` dimension label is Chronicle's existing `Geography` wording.
The classification names `nz-ta-018` and `nz-ta-027` “Ōtorohanga District”
and “Ōpōtiki District”; MBIE's package uses “Otorohanga District” and
“Opotiki District”. The merged bundle therefore adds two geography-name
warnings while preserving each publisher's spelling.

Each selected row has an exact column-A row-header guard and a `2025 P`
column-header guard. Guards also cover A3 `Territorial authority and Auckland
local board areas`, A4 `At 30 June 2023–2025`, A5 `Territorial authority and
Auckland local board area(2)`, A100 `2. Boundaries at 1 January 2025.`, and
A105 `P provisional`. Macron differences are not normalized in these guards.

## Preserved but not emitted

- The **21 Auckland local-board rows** at 12–32, named in column B with blank
  column A. Local boards require a geography level the current Chronicle
  contract does not provide; the NZ hub owns a separate G8-d2b follow-up.
- The **2023 and 2024 P columns**, and the **change and percent columns**.
- The **New Zealand(3) row** at 96. Table 2!E96 publishes 5,324,700; the
  existing regional package already emits that number from Table 1!D25.

Footnote 3 explains that the national population includes inlets, islands,
ships and oil rigs outside territorial authority areas. Values remain as the
publisher rounded them. Neither an authority sum nor an Auckland local-board
sum is emitted; published authority counts are not reconciled with the national
row. No residual, share, aging, interpolation, imputation, target activation,
or computed population enters Chronicle.

## Artifacts and bounded validation

[NZ population source notes](../../../docs/pe-nz-population-source-notes.md)
record the workbook and classification checksums and sizes. The workbook is
already published and verified. The NZ hub published the TA classification to
its declared `raw/nz/stats_nz/...` key on 13 October 2026 and verified the
remote object by SHA-256 against the manifest.

The package-specific tests build an independent expected map from the workbook
and classification, compare every admitted cell, check ten exact sample cells,
and exclude local boards, code `999`, and the national row. The existing
regional package retains its 85 facts. Source-package and consumer-contract
validation plus a one-source build are required; independent source-fidelity
and boundary judges must review the candidate before landing.
