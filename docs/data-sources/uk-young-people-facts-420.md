# UK young people and work facts for chronicle#420

[chronicle#420](https://github.com/PolicyEngine/chronicle/issues/420) asks for the published
facts that four UK events need. This page covers its young people batch, for the final
report of the independent review of young people and work
([PolicyEngine/uk-young-people-work-review](https://github.com/PolicyEngine/uk-young-people-work-review)):
items 1 (ONS NEET), 2 (LFS table A06), 3 (people on Universal Credit by age and
conditionality regime), 4 (PAYE RTI by age and ASHE Table 6) and 9 (HMRC's employer NICs
reliefs for young employees). Every source is a published aggregate under the Open
Government Licence v3.0; no survey microdata is read or stored, and the values are the
publishers' own cells with the publishers' suppression.

Eighteen packages add 33,641 facts. `scripts/build_uk_young_people_packages.py` writes
seventeen of them and `scripts/build_dwp_uc_people_age_conditionality_package.py` the UC
cube, each from its pinned bytes, asserting the publisher's text cell by cell; `--check`
compares the output with the committed YAML. `tests/test_source_uk_young_people_facts.py`
and `tests/test_source_uk_uc_people_age_conditionality.py` re-read the pinned files and
find each fact's cell from its own dimensions.

## Sources

| Packages | File | Publisher, date | sha256 |
|---|---|---|---|
| `ons-neet-august-2026` | `notineducationemploymentortrainingaj26.xlsx` | ONS, NEET Table 1, 27 August 2026 | `e01e0a08…` |
| `ons-a06-sa-october-2026` | `a06saoct2026.xls` | ONS, LFS table A06 SA, 20 October 2026 | `39f3c4b3…` |
| `ons-a06-nsa-october-2026` | `a06nsaoct2026.xls` | ONS, LFS table A06 NSA, 20 October 2026 | `e3518e44…` |
| `ons-paye-rti-age-nsa-october-2026` | `rtinsaoct2026.xlsx` | ONS and HMRC, PAYE RTI non-seasonally adjusted, 20 October 2026 | `f67a0b41…` |
| `ons-ashe-table6-{weekly,annual}-pay-gross[-cv]-2024-revised` | `ashetable62024revised.zip` | ONS, ASHE Table 6, 2024 revised, 23 October 2025 | `cd3c982b…` |
| `ons-ashe-table6-{weekly,annual}-pay-gross[-cv]-2025-revised` | `ashetable62025revised.zip` | ONS, ASHE Table 6, 2025 revised, 22 October 2026 | `2ccc3b37…` |
| `ons-ashe-table6-{weekly,annual}-pay-gross[-cv]-2026-provisional` | `ashetable62026provisional.zip` | ONS, ASHE Table 6, 2026 provisional, 22 October 2026 | `106405c4…` |
| `hmrc-employer-nics-age-reliefs-january-2026` | `tax_relief_statistics_january_2026.ods` | HMRC, Tax relief statistics (January 2026), 22 January 2026 | `fa94a61f…` |
| `dwp-uc-people-country-age-conditionality-regime-april-2024-may-2026` | `people_on_uc_by_country_age_conditionality_regime_april_2024_may_2026.json` | DWP Stat-Xplore, UC_Monthly, extracted 6 November 2026 | `13f53626…` |

All nine files are committed and in R2: `chronicle publish-raw` wrote each manifest's
`storage.r2` block, and `chronicle verify-raw` read every object back.

Rules for reading these facts:

- **Select by concept.** Levels, shares and rates have their own concepts
  (`ons.lfs_people`, `ons.lfs_neet_people`, `ons.lfs_neet_rate`,
  `ons.lfs_employment_rate` and so on), and an ASHE CV takes its estimate's concept with
  the suffix `_coefficient_of_variation`.
- **Ages by bound.** Every age band carries `age_band` and its `age` bounds as
  constraints, so bands from different tables (NEET's 18-20, A06's 18-21, ASHE's 18-21,
  RTI's 18-24) can be told apart by their bounds. The labels follow the register's
  "Age 16 to 17" wording.
- **One adjustment at a time.** NEET and A06 carry `seasonal_adjustment`
  (seasonally adjusted, not seasonally adjusted); PAYE RTI here is not seasonally
  adjusted only.

## 1. ONS NEET (NEET Table 1, August 2026)

- **Ported:** every quarter from April to June 2024 to April to June 2026, from all nine
  data sheets: people, men and women at 16-24, 16-17 and 18-24, seasonally adjusted and
  not, and the not seasonally adjusted sheets for people aged 18-20, 21-22 and 23-24.
  Each age group's five cells: NEET (all, unemployed, economically inactive), the
  population of the age group and the NEET share of it. 945 facts.
- **Definition:** anyone in any education or training, part-time study included, is not
  NEET; ONS's glossary is quoted in the package header.
- **Status:** official statistics in development until 11 August 2026, official
  statistics since; the August 2026 edition says so. LFS quality notes (the 2024 to 2025
  data collection changes, the January to March 2019 reweighting, the seasonal adjustment
  review marked `[r]`) are quoted in the header and the period notes.
- **Cells:** the sheets say "thousands", which is the display format; the cells hold
  people, so no scale applies.
- **A publisher inconsistency, ported as published.** The "Women - NSA" sheet's 18-24
  population is below the "Women - SA" sheet's, A06 NSA's and its own 16-24 minus 16-17
  in every ported quarter, by 5,141 to 18,933 people, and its 18-24 NEET share is computed
  on it. The generator pins each quarter's gap.
- **Next edition:** 26 November 2026 (July to September 2026).

## 2. LFS table A06, SA and NSA (October 2026)

- **Ported:** people, men and women aged 16 to 17, 18 to 24 and 16 to 24 by full-time
  education (all, in, not in) and economic activity (all, employed, unemployed,
  economically inactive), as levels and as the employment, unemployment and inactivity
  rates. The NSA edition also splits 18-24 into 18-21 and 22-24; its 18_24 sheets
  repeat the 18-24 group, which is asserted equal and ported once. SA 1,701 facts, NSA
  2,831.
- **Periods:** A06 publishes rolling three-month periods every month, and Chronicle has
  period types for the calendar quarters only, as chronicle#407 found for Nomis's
  rolling years. The packages port January to March, April to June, July to September
  and October to December from April to June 2024 to April to June 2026, both editions.
  The latest window, June to August 2026, has no period type and is not ported; July to
  September 2026 comes in the 17 November edition.
- **#420's spec** asked for the NSA periods covering April 2024 to March 2025 and the SA
  latest. Both editions carry every calendar quarter of the window, so those cuts are
  selections of these facts.
- **Not NEET:** footnote 1, "Not in full-time education includes people in part-time
  education and/or some form of training", so NEET cannot be derived from A06.
- **Rates:** footnote 3's denominators: all people for employment and inactivity, the
  economically active for unemployment.
- **Suppression:** four NSA cells are "*" (unemployed 22 to 24 year olds in full-time
  education: men in October to December 2025, women in April to June 2024, level and
  rate) and emit no fact. ONS shades estimates based on small samples; Chronicle reads no
  shading.

## 3. People on Universal Credit by country, age and conditionality regime

- **Ported:** DWP's Stat-Xplore cube People on Universal Credit (UC_Monthly), April 2024
  to May 2026 (the latest month; DWP has released quarterly since 12 May 2026), by
  residence-based country (England, Wales, Scotland and DWP's Great Britain total), age
  and conditionality regime. 16,510 facts.
- **People, not households:** everyone with an open claim on the count date; both
  partners of a joint claim are counted.
- **Ages:** single years from 16 to 24, then DWP's bands from 25-29 to 65-70, "Over 70"
  and "Unknown/Missing". DWP says "Over 70" holds people aged 71 to 90 and counts people
  over 90 as unknown. "Over 70" carries its lower bound only, `age >= 71`, as the
  Attendance Allowance cube's "90 and over" carries `age >= 90`; "Unknown/Missing"
  carries none.
- **Regimes:** the six regimes plus "Unknown or missing regime", so the regimes add to
  each age's total. DWP's wording for "No work requirements" is "Health or caring
  responsibility prevents claimant from working or preparing for work"; its examples are
  full-time education, State Pension age, a child under 1 and no prospect of work. It
  does not name LCWRA; "Preparing for work" holds people with limited capability for
  work.
- **Great Britain** includes unknown residence (3,205 in April 2024, 9,991 in May 2026)
  and equals the employment indicator cube's total in all 26 months.
- **Disclosure control:** Stat-Xplore perturbs each cell; regimes add to each age's
  total within 18 people and ages to the all-ages total within 26.

## 4a. PAYE Real Time Information by age (October 2026)

- **Ported:** Tables 28 to 31 of the non-seasonally adjusted reference table, UK:
  payrolled employees and median pay from April 2024 to September 2026, mean and
  aggregate pay to August 2026. 826 facts.
- **Ages:** the published bands, 0 to 17, 18 to 24, 25 to 34, 35 to 49, 50 to 64, 65 and
  over, and the UK. No single years and no split at 21 are published, so #420's single
  years at 16 to 24 are not available from this table.
- **Semantics:** age at the time of payment; each employee counted once, as "an average
  of employee counts in each day of the month"; PAYE pay only, so no self-employment or
  pensions; pay is gross. Accredited official statistics.
- **Revisions:** September 2026 is an early estimate, "more likely to be subject to more
  significant revisions"; its period notes say so.
- **Parity:** the bands add to the UK within one employee and £2 of aggregate pay.

## 4b. ASHE Table 6, earnings by age group

- **Ported:** Tables 6.1a (gross weekly pay) and 6.7a (gross annual pay) with their CVs
  (6.1b, 6.7b), 2024 revised, 2025 revised and 2026 provisional: the number of jobs, the
  median, the mean and ten percentiles, for all employee jobs and each sex by
  working-pattern sheet, by age group (16-17, 18-21, 22-29, 30-39, 40-49, 50-59, 60+).
  12 packages, 10,806 facts.
- **Semantics:** employee jobs, not people, in the April pay period (annual pay for the
  tax year ending 5 April); employees on adult rates, except that "Figures for 16 to 17
  year olds include employees not on adult rates of pay" (footnote b), which the 16-17
  rows' own record sets carry. Cells ONS suppresses ("x", CV over 20%) emit no fact.
- **Table 2:** every sheet's "All employees" row is ASHE Table 2's (chronicle#407) cell
  for cell, in all three editions, so the two tables' total facts share semantic keys
  (1,404, reported by the bundle as semantic duplicates). So Table 6's 2024 revised
  edition carries the revised data, which ONS's correction of 3 November 2025 put into
  Table 2's 2024 revised table.

## 9. HMRC tax relief statistics: employer NICs reliefs (January 2026)

- **Ported:** the two reliefs' cost (Table 2, £ million) for 2020-21 to 2025-26 and their
  claimants (Table 5) for 2020-21 to 2024-25. 22 facts.
- **Semantics:** a zero rate of Class 1 secondary NICs for employees under 21 up to the
  upper secondary threshold, and for apprentices under 25 up to the apprentice upper
  secondary threshold; "The under 25 apprentice employer NICs relief takes precedence
  over the under 21 employer NICs relief", so the costs do not overlap. 2025-26 is HMRC's
  first forecast year (`assertion: source_projection`). The claimants are employers
  ("we report the number of employers claiming the relief"), so the facts' entity is
  `firm`.
- **Parity:** the publication page's section 3.28 prints the same under-21 series, which
  the generator asserts.
