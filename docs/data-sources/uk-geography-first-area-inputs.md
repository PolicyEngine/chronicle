# UK area inputs for the geography-first spine (chronicle#412)

[#412](https://github.com/PolicyEngine/chronicle/issues/412) asks for the published area
inputs that PolicyEngine/microcosm#931 needs to move area assignment to the start of the UK
spine. Each household clone draws an output area within its FRS region, conditioned on two
things the FRS records about the real address: the deprivation decile (`IMDE`, `IMDW`,
`IMDS`, `IMDN`) and the dwelling's council tax band. The household's council tax then
follows the authority it is assigned to.

Every item is a **raw-only registration**, as for the atomic supports of
[#269](https://github.com/PolicyEngine/chronicle/issues/269):

- each manifest pins the publisher URL, sha256, size and fetch time;
- each file has an R2 copy in `ledger-raw`;
- none has a `source_package.yaml`, an alias or a bundle entry;
- no facts are emitted, so the consumer bundle does not change.

A consumer references one by `{source_id, package_id, year, sha256, filename}`.
Microcosm builds its area supports from these bytes.

## Registrations

| item | registration | file | bytes | in git |
|---|---|---|---|---|
| 1 | `mhclg-english-indices-of-deprivation-2019-file-1` | `File_1_-_IMD2019_Index_of_Multiple_Deprivation.xlsx` | 1,433,347 | yes |
| 1 | `mhclg-english-indices-of-deprivation-2025-file-1` | `File_1_IoD2025_Index_of_Multiple_Deprivation.xlsx` | 1,469,027 | yes |
| 1 | `welshgov-wimd-2019-ranks-by-small-area` | `welsh-index-multiple-deprivation-2019-index-and-domain-ranks-by-small-area.ods` | 232,940 | yes |
| 1 | `welshgov-wimd-2025-ranks-by-small-area` | `wimd-2025-index-and-domain-ranks-by-small-area.ods` | 242,742 | yes |
| 1 | `scotgov-simd-2020v2-ranks` | `SIMD_2020v2_ranks.xlsx` | 513,811 | yes |
| 1 | `scotgov-simd-2020v2-data-zone-lookup` | `SIMD_2020v2_datazone_lookup_updated_2025.xlsx` | 1,339,239 | yes |
| 1 | `nisra-nimdm-2017-soa-results` | `NIMDM17_SOAresults.xls` | 1,772,032 | yes |
| 1 | `nisra-nimdm-2017-sa-results` | `NIMDM17_SA_for_publication.xls` | 1,797,632 | yes |
| 1 | `ons-lsoa11-lsoa21-lad22-exact-fit-lookup-v3` | `ew_lsoa11_lsoa21_lad22_exact_fit_v3.csv` | 3,030,656 | yes |
| 1, 3 | `ons-nspl-may-2026` | `NSPL_MAY_2026.zip` | 187,209,017 | no |
| 2 | `mhclg-council-tax-levels-england-2024-25-table-1` to `-table-9` | the nine 2024-25 table files | 532,733 in 9 files | yes |
| 2 | `welshgov-council-tax-levels-2024-25` | `council-tax-levels-april-2024-march-2025-482.pdf` | 417,849 | yes |
| 2 | `welshgov-band-d-council-tax-composition-1993-94-to-2026-27` | `statswales_band_d_council_tax_composition_by_billing_authority.csv` | 590,478 | yes |
| 3 | `ons-oac2011-clusters-and-names-v3` | `2011oacclustersandnamescsvv3.zip` | 1,527,645 | yes |
| 3 | `ons-oa11-oa21-lad22-exact-fit-lookup-v3` | `ew_oa11_oa21_lad22_exact_fit_v3.csv` | 9,835,499 | no |

The two files not in git are R2-only (`storage.local: false`, git-ignored), as in #343 and
#356:

- the NSPL zip is above GitHub's 100 MB limit;
- the OA lookup is above the 9 MB line #356 drew for raw-only files that no build parses.

`tests/test_issue_412_uk_area_inputs.py` pins every registration. It also reads the
committed bytes to check the counts quoted below.

## 1. Deprivation by small area

### Indices

| nation | index | areas | registration | deciles |
|---|---|---|---|---|
| England | IoD 2019 (26 September 2019) | 32,844 LSOAs, 2011 | `mhclg-english-indices-of-deprivation-2019-file-1` | in the file |
| England | IoD 2025 (30 October 2025) | 33,755 LSOAs, 2021 | `mhclg-english-indices-of-deprivation-2025-file-1` | in the file |
| Wales | WIMD 2019 | 1,909 LSOAs, 2011 | `welshgov-wimd-2019-ranks-by-small-area` | in the file |
| Wales | WIMD 2025 (27 November 2025) | 1,917 LSOAs, 2021 | `welshgov-wimd-2025-ranks-by-small-area` | in the file |
| Scotland | SIMD 2020v2 | 6,976 data zones, 2011 | `scotgov-simd-2020v2-ranks` and `scotgov-simd-2020v2-data-zone-lookup` | lookup only |
| Northern Ireland | NIMDM 2017 | 890 SOAs (2001), 4,537 Small Areas (2011) | `nisra-nimdm-2017-soa-results` and `nisra-nimdm-2017-sa-results` | none |

Notes by index:

- **England.** Each File 1 gives the IMD rank, the decile and the local authority district
  (2019 or 2024 boundaries).
  - IoD 2019 prints 26 pairs of LSOAs that share a rank, with the next rank skipped. IoD
    2025 has no ties.
  - MHCLG re-issued the IoD 2025 LSOA files in November 2025 with no change to the data,
    after ONS corrected the district of LSOA E01027305. The registered file carries the
    correction (West Northamptonshire, E06000062).
- **Wales.** Each WIMD file gives the overall rank and the eight domain ranks. A second
  sheet gives each LSOA's rank, decile, quintile and quartile; WIMD 2025 adds a deprivation
  group.
- **Scotland.** The ranks file gives the overall rank and seven domain ranks but no deciles.
  The data zone lookup (the file updated in 2025) gives the same ranks with vigintile,
  decile and quintile, plus the 2016 urban rural class and higher geographies.
- **Northern Ireland.** NISRA publishes the Multiple Deprivation Measure as ranks, at SOA
  and at Small Area level. It publishes no deciles, so a decile is the consumer's banding
  of the rank.

### Crosswalks

- **England and Wales.** `ons-lsoa11-lsoa21-lad22-exact-fit-lookup-v3` is the ONS exact-fit
  lookup, version 3. It has 35,796 pairs covering 34,753 LSOAs of 2011 and 35,672 of 2021.
  Its change indicator `CHGIND` counts:
  - `U`, unchanged: 33,647;
  - `S`, split: 1,900;
  - `M`, merged: 239;
  - `X`, irregular: 10.
- **Scotland: nothing new is needed.** The NRS Census 2022 index registered under #269
  (`nrs-census2022-index`) already links the 2022 output areas to SIMD.
  - Its `Census_2022_Index/OA_TO_HIGHER_AREAS.csv` gives each of the 46,363 output areas a
    2011 data zone (`DZ2011`) and that zone's rank (`SIMD2020`). NRS assigns both best fit,
    by output area centroid.
  - `SIMD2020` equals the SIMD 2020v2 rank for every output area.
  - Four 2011 data zones receive no 2022 output area.
  - No published lookup from 2011 to 2022 data zones was found.
- **Northern Ireland: no lookup is published.** NISRA's geography lookups go from Small
  Areas and SOAs to other 2011-era geographies, and its Data Zone 2021 lookups (v3) go from
  Data Zones upwards; nothing links the two. The May 2026 NSPL is the bridge (next section).

### The NSPL check

The issue asks which index and vintage the IMD column of `ons-nspl-august-2026` carries.

**August 2026 edition (`imd25ind`).** The user guide's News section says the 2011-based IMD
"has been updated to 2021-based (IMD25) for England and Wales; Scotland and Northern Ireland
are not yet available." Checked against the bytes:

- England: every postcode (2,272,272) carries the IoD 2025 rank of its 2021 LSOA.
- Wales: every postcode (141,527) carries the WIMD 2025 rank of its 2021 LSOA.
- Scotland and Northern Ireland: every postcode carries 0.
- Annex B still prints the 2019 ranges for the field (1 to 32,844 and 1 to 1,909). The data
  run to 33,755 and 1,917, and section 29 of the guide names the 2025 files.

**May 2026 edition (`imd20ind`), registered here as `ons-nspl-may-2026`.** This is the last
edition carrying the 2019-vintage indices:

- England: IoD 2019, ranks 1 to 32,844.
- Wales: WIMD 2019, ranks 1 to 1,909.
- Scotland: SIMD 2020v2, ranks 1 to 6,976.
- Northern Ireland: NIMDM 2017, ranks 1 to 890 (SOAs).

Its Documents folder has the four IMD lookups (EN and WA as at 12_19, SC as at 12_20, NI as
at 12_17). Each equals the registered publisher file on every area: 32,844, 1,909, 6,976
and 890.

Each postcode in this edition also carries `oa21cd`: the 2021 output area in England and
Wales, the 2022 output area in Scotland and the 2021 Data Zone in Northern Ireland. So it
links the 2019-vintage ranks to the small areas Microcosm assigns, in all four nations.
Postcodes in one small area can carry different ranks. The areas with more than one rank
among their postcodes are:

| nation | areas with more than one rank | areas with postcodes |
|---|---|---|
| England | 507 | 178,582 OAs |
| Wales | 28 | 10,274 OAs |
| Scotland | 3,335 | 46,282 OAs |
| Northern Ireland | 2,011 | 3,780 Data Zones |

How to weight such areas is Microcosm's choice.

**What this means for Microcosm.** The vintage question stays with DWP.

- If the FRS 2024-25 deciles use IoD 2019, WIMD 2019, SIMD 2020v2 and NIMDM 2017, the May
  2026 NSPL is the postcode-level crosswalk.
- If England and Wales use IoD 2025 and WIMD 2025, the August 2026 NSPL is the crosswalk
  for those two nations.

Either way the NSPL carries ranks only. Deciles come from the index files, and for Northern
Ireland from banding the NIMDM ranks.

## 2. Council tax Band D, 2024-25

### England

The 2024-25 release publishes Tables 1 to 9 as nine ODS files, not one workbook. Each is
registered on its own, as `mhclg-council-tax-levels-england-2024-25-table-1` to `-table-9`.
The release page's current file is registered in each case: the revised Tables 1, 5 and 9
(May 2024) and the revised Table 7.

The release numbers its tables differently from the 2025-26 workbook
(`mhclg-council-tax-levels-england-summary-2025-26`). **The table Microcosm reads is Table 8
here, not Table 9.**

| 2024-25 release | content | 2025-26 workbook |
|---|---|---|
| Table 1 (revised) | England summary, 2020-21 to 2024-25 | Table 1 |
| Table 2 | average Band D by class of authority | Table 2 |
| Table 3 | England average Band D, 2010-11 to 2024-25 | Table 3 |
| none | use of the referendum principles flexibility | Table 4 |
| Table 4 | adult social care precept | Table 5 |
| Table 5 (revised) | parish precept | Table 6 |
| Table 6 | area Band D by area of authority | Table 7 |
| Table 7 (revised), 7a to 7f | Band D by individual authority | Tables 8a to 8f |
| **Table 8** | **area council tax for a dwelling occupied by two adults, Bands A to H, each billing authority** | **Table 9** |
| Table 9 (revised) | local authority level data: requirement, taxbase and chargeable dwellings | a separate Table 10 release |

Table 8 covers the 296 billing authorities, with E code and ONS code. Its figures include
adult social care and parish precepts (note a), and note b states the band ratios.

Table 9's workbook has ten data sheets and also carries 272 empty sheets named after
external file references.

### Wales

- `welshgov-council-tax-levels-2024-25` is the 2024-25 release itself (SFR 20/2024, 21
  March 2024). It is published as a PDF only. Its Table 1 gives each authority's average
  band D with the county council, community council and police elements, rounded to the
  pound.
- `welshgov-band-d-council-tax-composition-1993-94-to-2026-27` is the StatsWales dataset
  "Composition of average band D council tax by billing authority", as one CSV export. It
  gives the same elements unrounded, from 1993-94 to 2026-27.
  - Checked: the release's Table 1 equals the export's 2024-25 values rounded to the pound,
    for all 22 authorities and the Wales average. This holds for the band D total and each
    of the three elements.
  - The API regenerates the export, so the registration pins one fetch's bytes.
- Not registered: the April 2025 to March 2026 release. Its Table 2 gives the overall
  2024-25 band D, but not its elements, and the StatsWales export carries the same values.

### Scotland

No action: `scotgov-band-d-council-tax-rates-2026-27` already covers 2024-25.

## 3. Output Area Classification

- `ons-oac2011-clusters-and-names-v3`: the ONS 2011 OAC, version 3 (3 July 2023). It gives
  the supergroup (8), group (26) and subgroup (76) for each of the 232,296 UK output areas
  of 2011:
  - 171,372 in England;
  - 10,036 in Wales;
  - 46,351 in Scotland;
  - 4,537 Small Areas in Northern Ireland.
- `ons-oa11-oa21-lad22-exact-fit-lookup-v3`: the ONS output area lookup from 2011 to 2021,
  version 3. It has 189,567 pairs covering 181,408 output areas of 2011 and 188,880 of 2021.
  Its change indicator `CHNGIND` counts:
  - `U`: 175,469;
  - `S`: 12,654;
  - `M`: 1,040;
  - `X`: 403;
  - one row coded with a lower-case `x`, as published (2011 output area E00079804).
- **The 2021 OAC is not registered.**
  - ONS does not host it. Its page points to the Geographic Data Service (GeoDS), which
    developed the 2021/22 UK classification with ONS and publishes it under the Open
    Government Licence. GeoDS downloads need a sign-in.
  - The August 2026 NSPL already carries it: `oac21ind` holds each postcode's 2021/22
    subgroup, and every output area's postcodes share one code.
  - That gives a class for 178,582 of England's 178,605 output areas, 10,274 of Wales's
    10,275, 46,282 of Scotland's 46,363 and all 3,780 Northern Ireland Data Zones. The
    other areas contain no postcode.
  - The May 2026 NSPL's `oac11ind` gives the 2011 OAC of each postcode against the same
    2021 small areas.

## Licences

Every file is published under the Open Government Licence (v3.0 where the publisher states
a version).

- The NSPL user guide requires the OS and Royal Mail attributions.
- It also requires a separate Land and Property Services licence for commercial use of the
  Northern Ireland (BT) postcodes.

## Disclosure

Every registered file is a published area lookup or an area aggregate. Nothing here is
derived from survey records.
