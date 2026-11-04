# UK land value inputs for chronicle#408

[chronicle#408](https://github.com/PolicyEngine/chronicle/issues/408) asks for the published
inputs that Microcosm needs for the UK land value tax analysis
([PolicyEngine/uk-land-value-tax](https://github.com/PolicyEngine/uk-land-value-tax)):

- land values by local authority, whose method is prototyped in
  [PolicyEngine/uk-lvt-paper#14](https://github.com/PolicyEngine/uk-lvt-paper/pull/14) and
  [PolicyEngine/uk-lvt-paper#16](https://github.com/PolicyEngine/uk-lvt-paper/pull/16);
- the council tax each authority charges;
- stamp duty purchases by buyer.

Chronicle registers the inputs, and Microcosm builds the targets from them. Every source here
is a published table or file, and no value in this PR is computed by PolicyEngine.

`scripts/build_uk_408_packages.py` regenerates the new packages from the pinned bytes, and
`--check` compares instead of writing.

## Barnsley's and Sheffield's codes

ONS replaced Barnsley's E08000016 and Sheffield's E08000019 with E08000038 and E08000039 in
2025, after a boundary change. Every package keeps the codes its table prints, so packages from
the same period disagree:

| Package | Barnsley | Sheffield |
| --- | --- | --- |
| `mhclg-land-value-estimates-2023` | E08000016 | E08000019 |
| `mhclg-council-tax-collection-by-authority-2025-26` (Table 6a) | E08000016 | E08000019 |
| `mhclg-council-tax-qrc4-2025-26` (Table 9a) | E08000038 | E08000039 |
| `voa-council-tax-bands-2026`, `-property-types-2026`, `-build-periods-2026` | E08000038 | E08000039 |
| `mhclg-epc-d3-domestic-2026-q3`, to 2025 Q4 | E08000016 | E08000019 |
| `mhclg-epc-d3-domestic-2026-q3`, from 2025 Q4 (2025 Q4 has both) | E08000038 | E08000039 |
| `mhclg-live-table-126-dwelling-density-2026` | E08000016 | E08000019 |
| `mhclg-council-tax-levels-england-2026-27` (on main) | E08000038 | E08000039 |

A consumer that joins these packages on `geography_id` must map one pair of codes to the other.
Otherwise it drops both authorities.

- Tables 6a and 9a give their authority rows `mhclg.billing_authority` values made from the
  printed code. Each of these two authorities therefore has a different value in each table.
- Chronicle's geography name register, built from ONS's December 2024 lookups, carries the old
  codes but not the new ones.

## 1. MHCLG land value estimates for policy appraisal 2023

**`mhclg-land-value-estimates-2023`** (10,101 facts) holds all eight data sheets of MHCLG's
[workbook](https://www.gov.uk/government/publications/land-value-estimates-for-policy-appraisal-2023):

- **Publication:** published 16 March 2026; valuation date 1 October 2023; England.
- **File:** `Land_value_estimates_for_policy_appraisal_2023.xlsx`, 175,902 bytes, sha256
  `ca626b7e…8705`. This is the copy PolicyEngine/uk-lvt-paper#14 pins.
- **Period:** every fact is stamped `month` 2023-10, with a one-day coverage of 1 October 2023.
- **What the values are:** MHCLG's modelled values of a hypothetical serviced 1 hectare
  development site with planning permission, for economic appraisal.
  - The guidelines say "these land values do not represent the market value of land".
  - They also say the values are not directly comparable with the 2019 edition or earlier
    ones.
  - Every record set is therefore `provenance_class: model_output`.
  - Each value is in GBP per hectare (`unit: gbp_per_hectare`), with `aggregation: mean`. The
    guidelines call the outputs "reasonable averages in the context of this exercise".

### Residential

The two residential sheets cover 295 council areas: every English authority except the Isles
of Scilly.

- **Site density.** `mhclg.residential_site_density`, in dwellings per hectare, is given
  under the low, "Medium" (central) and high scenarios (filter `site_density_scenario`).
  - The second sheet prints the same densities, so they are ported once.
  - A test asserts the two sheets agree.
- **Values.** Under each density there are values at the 25th, 40th, 50th, 60th and 75th
  percentiles of new-build house price per square metre (filter `new_build_price_percentile`,
  `p25` to `p75`).
  - The sheet heads these columns with the bare numbers (25, 40, "50 (Median)", 60, 75), so
    the package declares labels that name them ("25th percentile", ..., "50th percentile
    (median)").
  - Every other filter value takes the sheets' own heading: "Low", "Medium" and "High", or
    the office or retail type the row prints.
- **Two concepts:**
  - `mhclg.residential_land_value_before_floor`, from sheet `Residential`.
  - `mhclg.residential_land_value_floor_adjusted`, from sheet `Residential (adj for floor)`.
    It applies MHCLG's minimum "floor value", which is designed to "give a credible lower
    bound result" in land value uplift calculations.
- **Unreported cells.** `Residential` prints `-` where the residual is negative ("Negative
  values are not reported").
  - Those 35 cells, in 14 authorities, emit no fact.
  - As in the VOA's 2025 CTSOP1.1 package, the rows that print every value share a `full`
    record set, and each other pattern gets a `subset_<n>` record set.
- **Codes.** Councils carry the codes printed, which were current at the valuation date.
  - Barnsley and Sheffield are E08000016 and E08000019.
  - ONS replaced those codes with E08000038 and E08000039 in 2025, after a boundary change.
  - Mapping the old codes to the new ones is the consumer's translation.

**Parity checks** (the issue's):

- Both sheets have 295 authority rows.
- No printed value falls as the percentile rises, under any density, on either sheet.
- One case does not strictly rise. On the floor-adjusted sheet, Cumberland's median and 60th
  percentile values are equal (GBP 460,000 per hectare) under all three densities, because
  the floor binds.
- Every floor-adjusted value is at least the estimate before the floor, wherever the latter
  is printed.

### Non-residential

These are the VOA's valuations of selected locations, procured by MHCLG. Entity `firm`, with
the site type as `entity_role`.

- **Industrial** (`mhclg.industrial_land_value`):
  - the 109 built-up areas: the seven major commercial centres and 102 others;
  - the ten London locations.
- **Office** (`mhclg.office_land_value`):
  - the major commercial centres by `office_accommodation_type` (`primary`, `secondary`,
    `tertiary`);
  - the other built-up areas for "the most prevalent office type for location";
  - London on the city central appraisal.
- **Retail** (`mhclg.retail_land_value`):
  - the major commercial centres by `retail_location_type` (`urban`, `suburban`);
  - the other built-up areas and London on city or town centre assumptions.
- **Distribution** (`mhclg.distribution_land_value`): the nine English regions.
- **Agriculture** (`mhclg.agricultural_land_value`): the nine regions by
  `agricultural_land_grade`.
  - "Low" is Agricultural Land Classification grades 4 and 5.
  - "Medium" is grades 3a and 3b.
  - "High" is grades 1 and 2.
- **Car Park** (`mhclg.car_park_land_value`): 109 locations named by postcode district and
  town, such as `AL3 - St Albans`.

Office and Retail print `-` for negative values, and those cells emit no fact. That leaves 48
office values and 89 retail values.

**Geographies:**

- Built-up areas use `statistical_scope` with ONS Built-up Areas 2022 codes
  (`geography_vintage: bua_2022`). These are E63 codes, plus Chester's cross-border
  K08000001.
- London locations have no published code. They are identified as
  `mhclg-lve-2023-london:<name>`.
- Car parks are identified as `postcode-district:<district>`.

## 2. Market Value Survey 2024 (English Housing Survey): annex tables

There are three packages, one per annex workbook of MHCLG's
[Market Value Survey 2024](https://www.gov.uk/government/publications/market-value-survey-2024),
published 14 April 2026:

- `mhclg-market-value-survey-2024-chapter-1`: 3,984 facts.
- `mhclg-market-value-survey-2024-chapter-3`: 274 facts.
- `mhclg-market-value-survey-2024-chapter-4`: 200 facts.

**Survey and period**

- The VOA valued the dwellings in the EHS 2022-23 and 2023-24 physical surveys as at 1 July
  2024. The tables print the 2015 survey, as at 1 October 2015, alongside.
- Each fact's period is its valuation date (`month` 2024-07 or 2015-10), not the survey year.
- Every record set is `provenance_class: survey_aggregate`, with the survey instrument set as
  in `mhclg-ehs-weekly-housing-costs-2023-24`.

**Tables ported**

- **Chapter 1:** AT1.1 to AT1.7, in both the A ("all dwellings") and B ("excluding London")
  versions where both exist. The B tables use the geography `mhclg:england_excluding_london`.
- **Chapter 3:** AT3.3, AT3.5 and AT3.6.
- **Chapter 4:** AT4.1 to AT4.6.
- **Not asked for:** Chapter 2, and AT3.1, AT3.2 and AT3.4.

**Values**

- Values are in GBP thousands as printed (`value_scale: 1000`, `unit: gbp`).
- The sample sizes printed beside the means are a measure of their own.
- Cells the tables suppress (`u`) or mark unavailable (`[x]`) emit no fact.

**Not ported**

- AT1.1's percentage-change block, which is arithmetic over the printed means.
- AT1.2's 100% total row.
- The chapter 4 rows that restate chapter 1's: AT4.1's £1m to £2m and £2m-or-more rows, and
  AT4.2's rest-of-England rows for those bands, together with both tables' sample sizes.
  - The generator and the tests read both workbooks and assert that the two agree.
  - One sample size differs: AT4.1 prints its 2024 all-dwellings base with two digits
    transposed against AT1.1A's. That cell is not ported, and a test records the difference.

**Filter values**

- Where two tables word the same tenure or value band differently, the filter takes one value
  (for example `gbp_2m_or_more` for "£2,000,000 or more", "£2m or more" and "£2m plus").
- The printed wording stays in each row's label and guard.
- The package headers list each such mapping.
- Every filter value carries a label, chosen in this order:
  - the row's wording, where the package prints the value as a row;
  - otherwise the column header as printed;
  - otherwise the title of the block that sets it (AT1.7's "House or bungalow" and "Flat",
    AT4.5's two home values).
- Chronicle's label register (chronicle#376) gives a value that several packages emit one
  label:
  - "Yes" and "No", the wording most packages use, where chapter 1's sample-size rows print
    "Dependent Children - Yes" and the like;
  - for the two value bands chapters 1 and 4 word differently, chapter 1's "£1,000,000 to
    £2,000,000" and "£2,000,000 or more". This choice is proposed for the maintainer's
    review.

This document quotes no figure from the survey.

## 3. VOA Council Tax: stock of properties 2026

The [2026 release](https://www.gov.uk/government/statistics/council-tax-stock-of-properties-2026):

- Published 24 September 2026, with counts at 31 March 2026, for England and Wales.
- GOV.UK now names HM Revenue & Customs as the publisher, the statistics being "produced by the
  Valuation Office". The source id stays `voa`.
- The summary workbook is `2026_CT_SoP_Summary_Tables.ods`: 1,391,108 bytes, sha256
  `9e9be694…29d9`, the copy PolicyEngine/uk-lvt-paper#14 pins.
- Its counts are rounded to the nearest 10. `[z]` marks band I outside Wales and `[c]` a
  suppressed count of 1 to 4; neither emits a fact.

**`voa-council-tax-bands-2026`** (8,566 facts): CTSOP1.0 and CTSOP2.0 at every geography the
sheets print.

- **Geographies:**
  - England and Wales, the two countries and the 9 regions;
  - 29 counties and metropolitan counties, with Inner and Outer London;
  - 318 billing authorities;
  - 575 constituencies;
  - the unmatched row.
- **Concepts and period:** the 2025 packages' concepts (`voa.ct_stock_band_a` to `_i`, and
  `voa.ct_stock_all_properties`), with `period` `month` 2026-03.
- **Two bases.** CTSOP2.0's country and region rows count the properties matched to a
  constituency by postcode, so they carry `geography_match: matched`. CTSOP1.0's rows carry no
  such filter.
- **Repeated row.** CTSOP2.0's England and Wales row equals CTSOP1.0's and is asserted rather
  than ported twice.

**`voa-council-tax-property-types-2026`** (120,493 facts) and
**`voa-council-tax-build-periods-2026`** (93,529 facts) carry the remaining two tables:

- **What they hold:** CTSOP3.0 (band by property type and bedrooms) and CTSOP4.0 (band by
  build period), at every geography, from the same workbook.
- **Concepts:** each has its own (`voa.ct_stock_by_property_type`, `voa.ct_stock_by_build_period`),
  so their "All" rows and columns are ported without repeating CTSOP1.0's facts.
- **Filter values:** build periods take values such as `year_2009`, because a digit-only string
  would become an integer.

**Codes:**

- Barnsley and Sheffield are E08000038 and E08000039, the codes ONS gave them in 2025.
- Inner and Outer London (E13) are typed as regions, as DESNZ's packages type them.

**Raw only.** The three small-area zips are registered `raw_only`, kept in R2 only and
git-ignored:

- **Registrations:** `voa-ctsop1-1-lsoa-2026` (CTSOP1.1, 4,311,882 bytes),
  `voa-ctsop3-1-lsoa-2026` (CTSOP3.1, 95,521,582 bytes) and `voa-ctsop4-1-lsoa-2026` (CTSOP4.1,
  73,430,283 bytes).
- **Member name.** The 2026 CTSOP1.1 member is `CTSOP_1_1/CTSOP1_1_2026_03_31.csv`; 2025's was
  `CTSOP1.1/…`. Microcosm's band-mix builder reads the member by name.
- **Different counts.** The zips assign properties to areas by postcode, so their authority
  rows differ from the summary sheets' billing-authority counts.

**Parity**

- **Bands against the all-properties column:** band cells sum to "All properties" within
  rounding, with the largest gap 30 on CTSOP1.0 and 20 on CTSOP2.0.
- **England and Wales:** England plus Wales is within ±10 of England and Wales in every column.
- **Crossed tables:** CTSOP3.0's and CTSOP4.0's "All" columns equal CTSOP1.0 in all 3,255 rows.
  Their other cells sum to the "All" column within rounding (up to 80 and 70).
- **CTSOP1.0 against CTSOP2.0:** CTSOP1.0 counts 8,260 more properties for England and 1,380
  more for Wales. Together that is 9,640, against the unmatched row's 9,630.
- **For information:** England's total went from 25,746,570 in 2025 to 25,936,540 in 2026 on
  CTSOP2.0's basis.

## 4. Council tax collected by billing authority

England needed new files. The Welsh and Scottish rows come from workbooks Chronicle already
pins.

### England

Two new packages come from MHCLG's release
[Collection rates for council tax and non-domestic rates in England, 2025 to 2026](https://www.gov.uk/government/statistics/collection-rates-for-council-tax-and-non-domestic-rates-in-england-2025-to-2026).

**`mhclg-council-tax-collection-by-authority-2025-26`** (1,208 facts) is Table 6a:

- Net collectable debit and amount collected, for 2024-25 and 2025-26.
- Rows: the six authority classes and 296 billing authorities, with Table 5's concepts.
- Rate columns H and K are left out, because the workbook's `Table_6` sheet defines them as
  Line 4 / Line 1 × 100.
- England's row is not ported. It restates Table 5 (`mhclg-council-tax-collection-england-2025-26`),
  and a test asserts the two agree.

**`mhclg-council-tax-qrc4-2025-26`** (5,757 facts) is Table 9a, each authority's QRC4 return
for 2025-26:

- **Annual lines,** stamped `fiscal_year` 2025: 2, 3, 6, 7, 13, 14, 16 to 19, 20a, 20b, 21, 22
  and 25.
- **Quarterly lines** 9 to 12, for 2025-Q2 to 2026-Q1.
- **Left out because the QRC4 form defines them as arithmetic over other lines:** 4, 5, 8, 15,
  20, 23 and 24. Line 21 stays, because its formula adds costs, which the return does not
  print.
- **Line 1, the estimated net collectable debit,** is not ported. It restates Table 6a's
  2025-26 figure for every row, and a test asserts it.
- **Codes:** Table 9a prints Barnsley and Sheffield as E08000038 and E08000039, while Table 6a,
  in the same release, prints E08000016 and E08000019. Both are kept as printed.
- **Line 7's year:** the QRC4 form describes line 7 as receipts of 2025-26 council taxes, but
  Table 9a's heading says 2026-27. The package follows the heading.

### Wales

The 22 authority rows of Table 2 now join the "Total Wales" row in both pinned workbooks.
`welshgov-council-tax-collection-2024-25` and `welshgov-council-tax-collection-2025-26` each
have 161 facts.

### Scotland

`scotgov-slgfs-council-tax-2024-25` now has 167 facts:

- It adds the 32 council rows of SLGFS 2024-25 Tables 2.8 (council tax income after CTR) and
  2.11 (CTR).
- The figures are income after CTR (LFR A0), not a net collectable debit.
- 2024-25 is the latest year until the next SLGFS.

### Parity (all exact)

- **Table 6a against Table 5.** England's figures in Table 6a equal Table 5's:
  - net collectable debit: GBP 42,014,522 thousand in 2024-25 and 44,981,384 thousand in
    2025-26;
  - amount collected: GBP 40,281,988 thousand and 43,002,543 thousand.
- **Table 9a against Table 6a.** Table 9a's line 1 equals Table 6a's 2025-26 debit for England
  and for every authority.
- **Authorities and classes.** The authorities sum to England, and the classes add up, for
  every measure.
- **Wales.** The Welsh authorities sum to "Total Wales" for all seven measures in both years.
- **Scotland.** The Scottish councils sum to Scotland: GBP 2,996,849 thousand of income,
  351,000 thousand of CTR funding and 389,010 thousand of reduction in liability.
- **QRC4 arithmetic.** Every QRC4 formula holds for all 303 rows.

These rows give Microcosm council tax by authority for all three nations, which unblocks
`local_council_tax_net`.

## 5. HMRC Annual Stamp Tax Statistics 2024-25: more tables

`hmrc-stamp-tax-statistics-2024-25` grows from 352 to 1,487 facts.

- **Same artifact.** The new rows come from the same file (`Annual_Stamps_2024_25_correction.ods`,
  sha256 `ee391638…b7b5`), written by `scripts/build_uk_1095_port_packages.py`.
- **Parser.** It is now `ods_numeric_text_used_range`, because Table 5a's 2023-24 sheet stores
  some numbers as text. The 352 existing facts keep their keys and values.
- **Both years.** Tables 7, 3a, 5a, 9a and 9d come for 2023-24 and 2024-25, and Table 2e
  quarterly.

**New facts by table:**

- Table 7: 203.
- Table 3a: 204.
- Table 5a: 423.
- Table 9a: 120.
- Table 9d: 77.
- Table 2e: 108 (27 quarters × 4 measures).

**Not ported:**

- Cells that restate ported facts: Table 7's and 9d's "All ages", 5a's "All price bands", and
  3a's all-countries residential and non-residential cells. Each is asserted equal to the fact
  it restates.
- The percentage columns, as with Table 6b. This includes 9a's and 2e's FTBR claims as a share
  of residential transactions, which divide published counts and are printed as text.

**What the tables mean:**

- **Table 7's rounding.** Its note says transactions are rounded to the nearest 100, but the
  cells print unrounded counts, some below 50, although the note says `[X]` marks fewer than 50.
  They are stored as printed, with the note.
- **Table 5a's misprint.** The 2024-25 sheet says "2023-24" in its heading and its contents
  entry, but its own note says 2024-25 and its totals equal Table 8a's 2024-25 receipts. It is
  stamped 2024-25.
- **Table 5a includes corporate flat-rate purchases.** Its price bands include corporate bodies
  paying the flat rate, which Table 8a reports on its own row.
  - Above £500,000, 5a's all-countries bands exceed 8a's by exactly the corporate row's £405m of
    property value in 2024-25.
  - So 5a's facts carry `sdlt_corporate_flat_rate: included_in_price_bands`.
- **Table 2e.** It is quarterly and, despite its title, not split by price band.
  - Recent quarters print fractional claims.
  - Its note says the series starts in 2017 Q2, but the data start in 2017 Q4.
- **Relief thresholds.** The 2024-25 relief counts were made under the thresholds in force from
  23 September 2022 to 31 March 2025: a £425,000 nil-rate threshold and a £625,000 maximum price.

**Parity, 2024-25** (all pass, and 2023-24 agrees too):

- **Table 3a against Tables 8a and 8b.** Residential and non-residential receipts are £10,380m
  and £3,505m, equal to 8a and 8b.
- **Table 5a against Table 3a.** 5a's all-countries, all-bands receipts equal 3a's residential
  receipts.
- **Table 7 against Table 8a.** Table 7's 925,140 transactions are within rounding of 8a's
  925,100.
- **Table 9a against Tables 9d and 2e.** 9a's 155,400 claims equal 9d's total. 2e's quarters
  from 2024 Q2 to 2025 Q1 sum to 155,368.45.

## 6. UCL's house price per square metre: not in this PR

ReShare 856542's two bundles are 3,214,161,126 and 4,426,805,029 bytes. Each holds stored
nested zips, the linked file `tranall_link_02122023.zip` alone being 3.2 GB. `publish-raw`
uploads through `wrangler r2 object put`, which refuses objects over 300 MiB. Item 6 therefore
waits for a separate change to how Chronicle stores large raw files, which
[chronicle#409](https://github.com/PolicyEngine/chronicle/issues/409) asks for a ruling on.

## 7. Floor area and dwelling density by authority

### EPC live table D3

**`mhclg-epc-d3-domestic-2026-q3`** (75,051 facts) is EPC live table D3:

- Published 29 October 2026, with data to 30 September 2026.
- File: `D3-_Domestic_Properties.ods`, 4,506,479 bytes, sha256 `834b564e…a062be`.

**What it holds**

- Three measures: lodgements, total floor area (`square_metres`) and habitable rooms.
- England and Wales, England and Wales separately: every quarter from 2008-Q4 to 2026-Q3, and
  calendar years 2009 to 2025.
- Each region and each local authority: every quarter.
- The register's "Unknown" area rows, ported once as `mhclg-epc-d3:england-area-unknown`. The
  regional and authority sheets print the same rows.

**Not ported**

- The `(Total)` rows, which span all periods. Tests assert they equal the sum of the quarters.
- The energy and carbon columns, which the issue does not ask for.
- Tables NB3 and EB3.

**Semantics**

- D3 counts certificates lodged, not dwellings.
- A dwelling with several certificates counts each time.
- Homes never sold, let or built since 2008 are absent.

**Codes**

- Barnsley and Sheffield print under E08000016 and E08000019 up to 2025 Q4, and under E08000038
  and E08000039 from 2025 Q4, so 2025 Q4 has both. Every code is kept as printed, with its own
  vintage.
- D3_by_LA's first column is headed "Region" but holds the authority name.

**Parity**

- England plus Wales equals England and Wales exactly, except floor area: 1 m² short in 2009
  and in 2009 Q2.
- Regions plus "Unknown" equal England, except floor area in 10 quarters, by at most 2 m².
- English authorities plus "Unknown" equal England, except floor area in 13 quarters, by at most
  11 m².
- Welsh authorities equal Wales, except floor area in 11 quarters, by at most 3 m².
- Every floor-area gap falls in 2012 Q1 or earlier. Lodgements and rooms match exactly
  throughout.
- Each year equals the sum of its quarters.

### Live Table 126

**`mhclg-live-table-126-dwelling-density-2026`** (5,406 facts) is Live Table 126:

- Published 21 May 2026.
- File: `LiveTable126.ods`, 90,471 bytes, the copy PolicyEngine/uk-lvt-paper#14 pins.
- The GOV.UK page's update of 25 June 2026 covered tables 116, 119, 612 and 615, not 126.

**What it holds**

- Dwellings per hectare at 31 March, 2011 to 2025, for England, the regions, the counties and
  the local authorities.
- Provenance class `model_output`, as for the other dwelling stock packages.

**Markers and duplicates**

- `[x]` cells emit no fact. `[p]` (provisional) and `[r]` (revised) stay in the measure
  headers and labels.
- The `[p]` years, 2022 to 2025, also carry `publication_status == provisional`, as
  `welshgov-dwelling-stock-by-tenure-2025` does. A consumer can filter on it. `[r]` (2024)
  has no filter of its own.
- Four codes print twice:
  - Cumberland, Westmorland and Furness, and North Yorkshire repeat identical rows.
  - Suffolk's first row lacks its 2023 value.
  - Each is ported once, and tests assert that the pairs agree.
- Tyne and Wear prints as E11000004, with values to 2022.

## 8. ONS land by sector

### The other sectors' land

Both balance sheet packages now port land (AN.211) for every sector their workbooks print. The
new sectors are E43E, E43J, E43K, E43Z, E447, E44C, E44D, E44O and E44Q, beside the E44R, E44N
and E43B already ported.

- `ons-national-balance-sheet-land-2025` grows from 90 to 360 facts: 12 sectors, 1995 to 2024.
- `ons-national-balance-sheet-land-preliminary-2026` grows from 3 to 12 facts, for end-2025. Its
  artifact now names the sector sheets it reads.

Every sector identity holds exactly, in every year:

- E44D = E44N + E44O.
- E43Z = E447 + E44C.
- E44Q = E43Z + E43E.
- E43B = E43E + E43J.
- E44R = E43B + E43K + E43Z + E44D.

So the whole economy less households and non-financial corporations is E43K + E43Z + E44O, a
published figure rather than a residual. It is £454,887m in 2024, and £323,750m at end-2025 in
the preliminary edition.

### ONS's 2022 series

**`ons-land-underlying-buildings-2022`** (108 facts) is Figure 1 of ONS's "Improving estimates of
land underlying other buildings and structures in the national balance sheet, UK" (27 June
2022).

**What it holds**

- Four series: total non-produced assets, land underlying dwellings, land underlying other
  buildings and structures, and other non-produced assets.
- Years 1995 to 2021, in GBP trillion to one decimal place (`value_scale: 1e12`).
- Provenance class `model_output`.

**Caveats**

- It is a 2022 vintage, from before later balance sheet revisions.
- The CSV prints the total as a fourth series, which the issue does not list.
- The components miss the total by at most GBP 0.1tn, in 11 of the 27 years. ONS notes that
  they "may not always add to the total because of rounding".
- The manifest pins ONS's generator URL. Three fetches about 40 minutes apart returned identical
  bytes.

## 9. Tax Policy Associates' model: raw only

**`tpa-lvt-model-2026`** (`db/data/tpa/lvt_model_2026`) is a `raw_only` registration: three
files pinned at commit `fef94f9e7a36ada25a9c29f1f6827759a12eed07` (10 September 2026), the
repository's latest on 4 November 2026.

- **The files:**
  - `preprocessing/config.py` holds the rebuild cost per square metre by property type
    (`BASE_COST_PER_M2`) and the regional factors (`REGION_FACTOR`).
  - `webapp/cells.json` holds the model's estimates by local authority.
  - `LICENSE` is the MIT licence.
- **No facts.** These are a third party's modelling assumptions and model output, not a
  publisher's statistics, so no facts are built from them. No provenance class could be read
  as official.
- **Storage.** The files are kept in R2 only and git-ignored. `config.py` is Python source,
  which this repository's lint would otherwise read as its own code. Their manifest keys are
  labels (`preprocessing_config`, `webapp_cells`, `licence`), not years.
