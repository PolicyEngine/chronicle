# Stats NZ subnational population, 30 June 2025 — partial

This package emits 85 publisher-backed population counts: the 16 regional
council areas and the separately published New Zealand total, each for all ages
and the four source age bands. It does **not** complete the five-year-age × sex ×
region surface requested by [issue #176](https://github.com/PolicyEngine/chronicle/issues/176).

The [29 October 2025 release](https://www.stats.govt.nz/information-releases/subnational-population-estimates-at-30-june-2025/)
and its unchanged XLSX provide these cells:

| Source sheet | Exact selection | Facts |
|---|---|---:|
| Table 1 | D7:D22 and D25, headed `2025 P` | 17 |
| Table 3 | Columns D:G, rows 10, 13, 16, 19, 22, 25, 28, 31, 34, 37, 40, 43, 46, 49, 52, 55, 64 | 68 |

Table 3's columns are 0–14, 15–39, 40–64, and 65+. All selected counts include
all sexes; no sex-specific counts appear in these worksheets. Both source
worksheets are parsed over their complete used ranges (2,265 cells), including
unselected years and explanatory footnotes. The package does not ingest
territorial authority/local board tables, island subtotals, percentages, median
ages, or population-change components.

## Reference period and population definition

- Reference date: **30 June 2025**, expressed as `calendar_year: 2025` plus
  equal start/end coverage dates `2025-06-30`. These are point-in-time counts,
  not annual average populations.
- Publication vintage: **29 October 2025**; all selected figures are
  **provisional**. The source artifact remains pinned even if Stats NZ later
  revises its historical estimates.
- Population: estimated resident population (ERP), based on the 2023 census
  usually resident population and adjusted for net census under/overcount,
  residents temporarily overseas on census night, and subsequent births,
  deaths, and net migration. This is not the unadjusted census-night count.
- Geography: regional boundaries at **1 January 2025**, with REGC codes stored
  as strings and `geography_vintage: regc_2025`. The separately pinned official
  [REGC 2025 attributes](https://services2.arcgis.com/vKb0s8tBIA3bdocZ/arcgis/rest/services/Regional_Council_2025/FeatureServer)
  supply the codes and names. The classification names code `02` “Auckland”;
  the population workbook labels the same region “Auckland region”.
- National scope: Table 1!D25 publishes **5,324,700**, including areas outside
  regions, such as Chatham Islands territory. The package reads the published
  national cells directly. It neither sums the 16 regions nor constructs a
  code-`99` outside-region residual. Published rounding also prevents exact
  reconciliation from being assumed.
- Provenance: `census` for a census-controlled ERP estimate, and
  `assertion: observation` for the historical reference date. “Observation”
  does not mean final or error-free; the source's provisional status remains
  explicit in the period and concept evidence.
- Concept relation: `source_label`, with Stats NZ evidence. No Axiom canonical
  equivalence, population calibration, uprating, interpolation, or target
  activation is claimed.

Every numeric value is a single selected source cell with scale 1. Row labels,
age headers, reference years, the boundary footnote, and the provisional-status
footnote have guards. The tests compare every admitted value against the
publisher workbook and every regional code/name against the independent
publisher classification.

Dimension labels follow the bundle's one-label-per-id rule. `geography` is
"Geography" and `person.age_band` is "Age band", the labels the other packages
that emit those ids already use. These two labels are Chronicle's wording. The
band values carry the publisher's headers `0–14`, `15–39`, `40–64` and `65+`
(Table 3!D6:G6). Statbel writes its band as `65_plus`, so the merged bundle
warns that the two packages word that value differently.

## Artifacts and remaining access gaps

See [NZ population source notes](../../../docs/pe-nz-population-source-notes.md)
for the three pinned checksums, raw storage, the detailed S7 API access failure,
and S8's missing single-year-age artifact. The wave-1 checklist deliberately
keeps the package-completion checkbox unchecked.

## Reproduce the bounded checks

```sh
uv run chronicle validate-package stats-nz-subnational-population-estimates-2025 --year 2025
uv run chronicle build-suite stats-nz-subnational-population-estimates-2025 --year 2025 --out /tmp/chronicle-nz-population-suite
uv run pytest -q tests/test_chronicle_nz_population.py tests/test_chronicle_artifacts.py tests/test_source_package_alias_drift.py
```

Source and consumer checks pass for this partial package. The concept-alignment
warning records that no Axiom CLI metadata validation ran; the source-label
mapping is not a certified canonical alignment. Independent source-fidelity
and boundary judges must review this candidate before landing.
