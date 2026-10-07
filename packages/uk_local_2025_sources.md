# UK local sources for the 2025 calibration

Chronicle preserves the publisher artifacts requested in [issue 313](https://github.com/PolicyEngine/chronicle/issues/313). Consumers choose household controls, align periods and construct geography or rent distributions.

| Source family | Packages and coverage | Publisher semantics |
| --- | --- | --- |
| Scotland households | `nrs-households-dwellings-2025`, `nrs-households-data-zone-2025`, `nrs-dwellings-data-zone-2025` | Council and country private-household estimates: June 2024/2025. Council dwelling stock: September. Data-zone occupied dwellings: September; dwelling stock: December. The small-area occupied-dwelling table does not assert the adjusted private-household estimate. |
| Wales households | `welshgov-household-estimates-mid2024`, `welshgov-household-projections-2022-based` | Revised mid-2022/2023/2024 estimates and principal mid-2025 projection. Publisher decimals retained. The estimate selector excludes private-household population and average household size. |
| England households | `ons-household-projections-2022-based` | Table 406, all 349 areas, mid-2022 through mid-2047, 2022 boundaries; metropolitan counties remain counties. `source_projection` identifies each publisher projection. |
| NI housing stock | `lps-housing-stock-lgd-2026` | Eleven districts and NI country, 1 April 2025/2026. Domestic or mixed-rated dwelling stock. |
| GB survey households | `ons-household-totals-country-region-2015-2025` | Three countries and nine English regions, 2015–2025, April–June Labour Force Survey estimates. Counts scale the source's thousands to units. Each measure's evidence notes retain its CV code and 95% interval half-width; guarded source cells retain the original uncertainty values. The existing `ons-households-by-type-country-2025` package and its Scotland household-composition fact remain unchanged, including their source identities. |
| England/Wales census residents | `ons-census2021-rm120-{pcon24,lad}-residence{1,2}-sex{0,1,2}` | Household/communal residence, three sex categories, 24 age categories including total; Census day 21 March 2021. Constituencies use 2024 boundaries; the 318 LADs use 2023 boundaries. Twelve rectangular Nomis requests each stay below the anonymous 25,000-row limit. |
| Scottish census residents | `nrs-census2022-uv101a-ukpc24`, `nrs-census2022-uv101a-council-area` | Census day 20 March 2022, 20 age categories plus total, three sex categories, household/communal residence. Disclosure-controlled cells need not add to totals. Usual residents include students at term-time addresses. |
| NI communal residents | `nisra-census2021-ct0105-communal-residents-lgd`, `nisra-census2021-ms-f04-communal-residents-ward` | District age/sex counts retain the two positions in the establishment as separate dimensions. Ward MS-F04a retains counts by broad age/sex; MS-F04b percentages produce no count facts. Wards use `statistical_scope` and the 2014 boundary vintage. |
| UK population | `ons-lad-population-by-age-2025` | Mid-2025, 361 LADs including all eleven NI districts. Nomis retains all ages and the 19 published age groups. The full ONS UK age/sex workbook is also registered as a raw companion. |
| Devolved population | `nrs-mye-2025-council-area`, `nisra-mye-2025-lgd-single-year-age`, `nrs-pcon24-population-by-age-2024-revised-2026` | Mid-2025 council/district single-year ages; open 90+ band. The revised Scottish UKPC24 edition retains every mid-2011–2024 year as its own period, using the September 2026, 2022-data-zone vintage. NISRA's numeric age code 90 denotes 90 and over. |
| Universal Credit | `dwp-uc-households-by-{constituency,constituency-children,local-authority}-january-2025-may-2026` | January 2025–May 2026, monthly periods, extraction vintage 7 October 2026. Raw queries/responses preserve all publisher categories and disclosure control. Unknown geography and the pre-April-2019 unavailable child bucket do not produce area facts; the published unknown/missing child category remains distinct. |
| PIPR rents | `ons-pipr-rents-by-area-august-2026` | September 2026 edition; January 2025–August 2026 numeric monthly means for all dwellings, four bedroom categories and four property categories independently. Scottish geography comprises 18 BRMAs. NI's numeric all-dwelling means in this edition end June 2026. Unavailable cells produce no numeric facts. |
| Scottish rent statistics | `scotgov-private-sector-rents-2025` | BRMA means, medians and quartiles by five bedroom/room categories, collected October 2024–September 2025. The shared one-bedroom category measures a room. Scotland-wide quartiles/medians marked NA produce no facts. |

Every artifact manifest records its source URL, extraction timestamp, SHA-256, byte size and uploaded R2 location. Full-row parsers retain physical source-row coordinates in the lineage key and cell note; selectors address the compact virtual-cell table with its header on row 1.

## Raw geography and rent evidence

The following directories under `db/data/` have `registration_kind: raw_only` and no fact-package alias:

- `voa/brma_boundaries_2020`: original English GML ZIP, applicable May 2020.
- `welshgov/brma_boundaries_2012`: May 2012 Rent Officers Wales boundaries, Edinburgh DataShare deposit, including correspondence and OGL documentation.
- `scotgov/brma_boundaries_2009`: Scottish 2009 polygons revised July 2015.
- `scotgov/brma_postcode_lookup_2023`: Rent Service Scotland FOI postcode-to-BRMA lookup.
- `ons/lsoa2021_population_weighted_centroids_v4`: all 35,672 EW LSOA centroids from the ONS V4 feature-service download; publisher ONS/Ordnance Survey licence applies.
- `nrs/oa2022_population_weighted_centroids`: original NRS Census 2022 OA centroid ZIP.
- `voa/shadow_list_of_rents_april_2026`: original 502,239 weekly net rent records, October 2024–September 2025.
- `welshgov/shadow_list_of_rents_2023`: original ATISN 25142 workbook, October 2022–September 2023.
- `scotgov/brma_market_evidence_2016_2021`: original FOI 2016–2021 letting workbook, including postcode, BRMA, payment frequency and net rent.
- `ons/mye_2025_uk`: full publisher UK mid-year age/sex workbook.

The rent lists retain payment frequency and source units. PIPR, rent-officer lists and Scottish rent statistics share an evidence base; their separate statistics do not establish independence. Chronicle constructs no OA-to-BRMA assignment, overlap, rent distribution or BRMA private-renter estimate.

## Pending source access

The Scottish Census 2022 ward tenure-by-bedroom joint table requires the original cached export pinned in Microcosm PR 1092 (SHA-256 `03d6157d34bd3df44e79ded1c03510954dee55e9e05d3c276b26ad463a565677`) or a guest table-builder download after accepting the publisher's terms. This table has no stable download URL. The change does not yet register or emit that export.

NRS also publishes [UV404 tenure alone at output-area level](https://statistics.ukdataservice.ac.uk/dataset/scotland-s-census-2022-uv404-tenure-households/resource/a9f38d0c-e8af-4e86-9ff1-a77f73cfcbde), with an OGL [CSV download](https://ukds-ckan.s3.eu-west-1.amazonaws.com/2022/NRS/UV404/Census_2022_UV404_Household_tenure_Households_oa.csv). Consumers can use those published private-tenure counts at OA level when they do not need the joint bedroom distribution.

Mid-2025 constituency estimates for England/Wales and Northern Ireland, and Scottish small-area mid-2025 estimates, are outside this change; the requested publisher releases were not yet available on 7 October 2026. The revised Scottish constituency facts retain their published mid-2024 endpoint.

## Validation

Run the source package at its `artifact_year`, rather than restamping a census or revised estimate to 2025:

```sh
uv run chronicle validate-package ons-lad-population-by-age-2025 --year 2025
uv run chronicle build-suite nrs-census2022-uv101a-ukpc24 --year 2022 --out /tmp/uv101a --replace
uv run pytest -q tests/test_chronicle_uk_local_2025.py
```

`build-suite` validates source rows/cells, selector guards, raw facts, consumer contracts and database lineage. Registry aliases include each fact package in the UK bundle; raw-only registrations remain artifact inputs.
