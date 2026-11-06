# UK PIP review facts for chronicle#420

[chronicle#420](https://github.com/PolicyEngine/chronicle/issues/420) asks for the published
facts that four UK events need. This page covers its PIP batch, for the final report of the
PIP review ([PolicyEngine/uk-pip-review-2026](https://github.com/PolicyEngine/uk-pip-review-2026)):
item 5, the points tables of DWP's Pathways to Work evidence pack, and item 6, DWP's
Stat-Xplore PIP cases with entitlement. Both are DWP publications of aggregates under the Open
Government Licence v3.0; no survey or administrative microdata is read or stored.

Seven packages add 23,947 facts. `scripts/build_dwp_pathways_evidence_pack_package.py` and
`scripts/build_dwp_pip_cases_packages.py` write them from the pinned bytes; `--check` compares
the output with the committed YAML, and `tests/test_source_uk_pathways_pip_points.py` and
`tests/test_source_uk_pip_cases.py` re-read the pinned files. All seven files are committed
and in R2 (`chronicle publish-raw`, read back by `chronicle verify-raw`).

## Sources

| Packages | File | Publisher, date | sha256 |
|---|---|---|---|
| `dwp-pathways-to-work-pip-points-january-2025` | `chapter_2_reforming_the_structure.ods` | DWP, Pathways to Work evidence pack chapter 2 data tables, revised 23 July 2025 | `4a6e864b…` |
| `dwp-pip-cases-country-award-age-january-2024-july-2026` | `pip_cases_country_award_age_january_2024_july_2026.json` | DWP Stat-Xplore, PIP_Monthly_new, extracted 6 November 2026 | `2358e4c1…` |
| `dwp-pip-cases-country-end-of-life-rules-award-january-2024-july-2026` | `pip_cases_country_end_of_life_rules_award_january_2024_july_2026.json` | the same | `b7823818…` |
| `dwp-pip-cases-country-disability-award-january-2024-july-2026` | `pip_cases_country_disability_award_january_2024_july_2026.json` | the same | `b2cb4730…` |
| `dwp-pip-cases-region-award-january-2024-july-2026` | `pip_cases_region_award_january_2024_july_2026.json` | the same | `4fd09fa2…` |
| `dwp-pip-cases-by-constituency-july-2026` | `pip_cases_by_constituency_july_2026.json` | the same | `7fb5d210…` |
| `dwp-pip-cases-by-local-authority-july-2026` | `pip_cases_by_local_authority_july_2026.json` | the same | `f991e805…` |

## 5. Pathways to Work evidence pack, chapter 2: PIP point scores

- **Package:** `dwp-pathways-to-work-pip-points-january-2025` (`packages/dwp/pathways_to_work_pip_points_january_2025`), 1,240 facts, written by `scripts/build_dwp_pathways_evidence_pack_package.py` from the chapter 2 data tables (`db/data/dwp/pathways_to_work_evidence_pack_chapter_2_2025/chapter_2_reforming_the_structure.ods`). The consultation page records updates to this ODS on 17 and 23 July 2025; the pinned file is the 23 July one (Last-Modified 2025-07-23T07:20:15Z).
- **Tables:** 2.9 and 2.10 (daily living and mobility points by age group), 2.11 and 2.12 (the same by primary health condition), 2.19 (the most points on any one daily living activity), 2.20 (by daily living award), 2.21 (by age), 2.22 (by condition), 2.27 (points on each daily living activity) and 2.28 (2.27 by condition: five groups and the rest). Not ported: Tables 2.25 and 2.26 (by local authority and constituency), 2.18, 2.23, 2.24 and the non-points tables.
- **Population, as DWP's notes state it:** the PIP caseload at end January 2025; working-age claimants only; normal rules only (special rules for end of life excluded); claimants under DWP policy ownership (England, Wales and abroad). Tables 2.19 to 2.22, 2.27 and 2.28 cover claimants awarded the daily living component. The facts carry these as filters and constraints worded as `dwp-pip-daily-living-foi-2025` words them, at geography K04000001 (England and Wales), the nearest GSS footprint; claimants abroad are included and have no code. Period: month 2025-01.
- **Tables 2.9 to 2.12 are the whole caseload, pension age included,** though DWP's note says "Data includes working age claimants only" on every table, so their facts carry no `pip_claimant_age_group`. Table 2.9's 60+ row holds 1,183,000 claimants and Table 2.10's 1,182,000, and the four tables' totals are 3,620,000 to 3,701,000. Stat-Xplore's caseload for England and Wales at January 2025 (`dwp-pip-cases-country-award-age-january-2024-july-2026`, all rules) is 503,287 aged 60 to 64, 1,196,452 aged 60 to 79 and 3,653,211 in all. So their 60+ rows run past State Pension age, and a reader that wants working age cannot take it from these tables. Tables 2.19 to 2.22, 2.27 and 2.28 do fit the working-age daily living caseload (Table 2.21's 60+ row is 569,000, and Table 2.19's total 2,891,000) and keep `working_age`. `tests/test_source_uk_pathways_pip_points.py` checks the comparison against the pinned cube.
- **Units:** shares are percentages as published (unit percent, aggregation share); the volume columns are counts in whole thousands. The share scoring 4 or more on one activity is the sum of Table 2.19's shares from 4 points up; Chronicle does not store that sum.
- **Not ported, as publisher errors (12 cells):**
  - Table 2.11's "All health conditions" row prints its bands in text order ('0-3', '10-11', … '4-7', '41+', '8-9') under numeric-order headings. Each misplaced cell equals, within 0.02 points, the volume-weighted average of the 20 condition rows for the band text order gives it. Only its '0-3' cell and its volume are ported.
  - Table 2.28's Arthritis "Activity 1 - Preparing food" 2-point cell repeats the Anxiety and Depression block's 79.83, and the row adds to 98.74. Weighted by Table 2.22's volumes, Table 2.28 reproduces Table 2.27 within 0.017 points in every other cell. At this one the gap is 0.121: Arthritis's weight (279,000 of 2,891,000) times the 1.26-point shortfall.
- **Parity, asserted on the published cells:**
  - Every distribution adds to 100 within 0.2 points. The exceptions are the two rows above and Table 2.9's whole percentages, whose rows add to 98 to 102, within the 94 to 106 that rounding twelve cells allows, except the 16–19 row.
  - **Table 2.9's 16–19 row adds to 92,** below what rounding can give: about 8 points of that distribution are missing from some band, and DWP does not say which. It is ported as published; a reader imputing points by age should not treat that row as a complete distribution.
  - Weighted by DWP's award volumes, Table 2.20 reproduces Table 2.19 within 0.008 points; by age (2.21) within 0.006; by condition (2.22) within 0.014.
  - Table 2.20's award volumes (1,608,000 enhanced, 1,283,000 standard) equal FOI2025/24990's counts.
- **Reprints and totals:**
  - Tables 2.20 to 2.22 open with Table 2.19's row reprinted. It is asserted equal and ported once.
  - The "All ages" and "All health conditions" rows describe the same caseload on bases DWP prints differently (3,627,000 and 3,701,000 for daily living; 3,620,000 and 3,691,000 for mobility). They share semantic keys (14 pairs), which the bundle reports as semantic duplicates.
- **Annex B of the Timms review interim report** (updated 15 July 2026) and its supplementary ODS files (8 July 2026) contain no points tables, so no newer edition exists.

## 6. PIP cases with entitlement (Stat-Xplore)

`scripts/build_dwp_pip_cases_packages.py` writes six packages from six pinned DWP
Stat-Xplore responses (database `PIP_Monthly_new`, "PIP Cases with Entitlement from
2019", extracted 6 November 2026; Open Government Licence per Stat-Xplore's terms). Each
month is the quarter-end caseload DWP refreshes (31 January, 30 April, 31 July,
31 October), January 2024 to July 2026:

- `dwp-pip-cases-country-award-age-january-2024-july-2026`: England, Wales and Scotland
  by daily living award, mobility award and age band (7,997 facts);
- `dwp-pip-cases-country-end-of-life-rules-award-january-2024-july-2026`: by End of Life
  Rules indicator (normal rules or SREL) and the two awards (1,078);
- `dwp-pip-cases-country-disability-award-january-2024-july-2026`: by disability category
  (the main disabling condition recorded at assessment) and the two awards (10,769);
- `dwp-pip-cases-region-award-january-2024-july-2026`: the nine English regions by the two
  awards (1,881);
- `dwp-pip-cases-by-constituency-july-2026` and `dwp-pip-cases-by-local-authority-july-2026`:
  all cases at July 2026 by Westminster constituency (632) and local authority (350).

Read them this way:

- **One margin, one package.** The awards and age request DWP's totals (filter `all`); the
  rules and disability fields do not, so the all-rules and all-conditions totals are the
  award-and-age package's and no fact is stated twice. Wales and England are country rows
  there; the region package holds the English regions only.
- **Scotland is residual.** Adult Disability Payment replaced PIP, and Social Security
  Scotland finished moving PIP cases by the end of June 2025. The Scotland rows (218,589 in
  January 2024, 919 in July 2026) are claims DWP still administers there, not Scotland's
  disability caseload.
- **Unrounded but adjusted.** Stat-Xplore cells are unrounded, with random disclosure
  adjustment, so parts and totals agree only within it. The tests check the awards and ages
  against their totals, the regions against England and the areas against the countries.
  A series zero in every month is not ported; cases abroad or of unknown residence have no
  GSS code and are not ported either (the release's 4.1 million for July 2026 adds them).

- **Not ported, against #420's list:** the 178 disability subgroups and 536 conditions (the
  packages carry the disability category); age by gender; cases abroad and of unknown
  residence. DWP's rounding applies to its bulletin, not to Stat-Xplore's unrounded,
  adjusted cells.
- **Parity:** awards add to their totals within 12 cases and ages within 26; the regions
  add to England within 12; at July 2026 the constituencies and local authorities add to
  the countries within 28. England plus Wales at July 2026 is 4,085,518; the release's
  "4.1 million" also counts cases abroad and of unknown residence.
