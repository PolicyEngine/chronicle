# UK dwellings by sector, ONS's capital stocks of dwellings and tenure by MSOA (chronicle#438)

[chronicle#438](https://github.com/PolicyEngine/chronicle/issues/438) follows
[chronicle#408](https://github.com/PolicyEngine/chronicle/issues/408), whose item 8 ported land
by sector from the same balance sheet workbooks. It asks for three inputs to Microcosm's stock
table of homes ([PolicyEngine/microcosm#1524](https://github.com/PolicyEngine/microcosm/issues/1524))
and its base ledger ([PolicyEngine/microcosm#1521](https://github.com/PolicyEngine/microcosm/issues/1521),
workstream 2):

1. Dwellings (AN.111) by institutional sector, from the two balance sheet workbooks Chronicle
   already pins.
2. ONS's gross and net capital stock of dwellings, from its capital stocks releases.
3. Census 2021 TS054 households by tenure for every MSOA in England and Wales.

Five packages add 66,230 facts, all OGL v3.0: 854 `model_output` facts for items 1 and 2, and
65,376 `census` facts for item 3. Three new files are pinned, and one parser is added for
workbooks that store their figures as text. Solving the cost level, the England and Wales
split, the depreciation profile, the scaling of each authority's social rented homes across its
MSOAs and the base ledger stay Microcosm's work, and none of their values become Chronicle
facts.

## 1. Dwellings by sector, from the two pinned balance sheets

**Packages**

- `ons-national-balance-sheet-dwellings-2025`: 360 facts, the 12 sectors at the end of each year
  from 1995 to 2024.
- `ons-national-balance-sheet-dwellings-preliminary-2026`: 12 facts, the 12 sectors at end-2025,
  each with `publication_status: preliminary`.

**No new file.** Each package reads the workbook its land package pins, through that package's
manifest: `nbsreferencetables2025.xlsx` (sha256 `8bec0fbb…3a79`) and
`preliminarynbs2026referencetables.xlsx` (`fdf04918…ab90`). It reads column B, Dwellings, of
Tables 2 to 13, for the years the land package reads Land. The dwellings rows are sibling
packages rather than new record sets in the land packages, for two reasons:

- the land packages stay byte for byte as they were;
- each package id says what it holds.

DfT's BUS01 Wales package reads its sibling's workbook in the same way.

**The series**, read from row 8 of each table, as the issue lists them:

| Table | Sector | Dwellings | Land (ported by #408) |
|---|---|---|---|
| 2 | Whole economy | E46Y | E44R |
| 3 | Non-financial corporations | E46D | E43B |
| 4 | Public non-financial corporations | E46E | E43E |
| 5 | Private non-financial corporations | E46F | E43J |
| 6 | Financial corporations | E46G | E43K |
| 7 | General government | E46I | E43Z |
| 8 | Central government | E46K | E447 |
| 9 | Local government | E46L | E44C |
| 10 | Households and NPISH | E46M | E44D |
| 11 | Households | E46V | E44N |
| 12 | NPISH | E46W | E44O |
| 13 | Public sector | E46X | E44Q |

**Semantics**

- GBP million at current prices, end-of-year positions (`value_scale: 1e6`).
- Every table's notes include "Excludes the value of the land underneath the assets." Table 3
  marks its Dwellings header with note 2, which is about the costs of ownership transfer; its
  land note is note 1.
- Table 2's note 1 traces the asset breakdown to ONS's capital stocks dataset. So the rows are
  modelled estimates, `model_output`, as the land rows are.
- Financial corporations (E46G) and local government (E46L) print 0 in every year from 1995, not
  only recently. The zeros are kept as printed.

**Parity.** Every sector identity holds exactly, in every year of both editions:

- E46Y = E46D + E46G + E46I + E46M.
- E46D = E46E + E46F.
- E46I = E46K + E46L.
- E46M = E46V + E46W.
- E46X = E46I + E46E.

So the issue's checks hold:

- **End-2024 (2025 edition):**
  - E46Y £2,525,540m = E46D 554,744 + E46G 0 + E46I 8,105 + E46M 1,962,691;
  - E46D 554,744 = E46E 129,699 + E46F 425,045;
  - E46M 1,962,691 = E46V 1,960,671 + E46W 2,020.
- **End-2025 (preliminary edition):** E46Y £2,637,111m = E46D 592,560 + E46G 0 + E46I 7,615 +
  E46M 2,036,936.

## 2. ONS capital stocks: gross and net stock of dwellings

**Packages**

- `ons-capital-stocks-dwellings-2025`: 480 facts.
  - From ONS's "Capital stocks and fixed capital consumption", released 27 November 2025:
    `capitalstockstables2025.xlsx`, 535,814 bytes, sha256 `71a995c3…0de7`.
  - Tables 1.1.1 (gross) and 2.1.1 (net), by asset and sector at current prices.
  - The eight rows of each table's dwellings block, 1995 to 2024.
- `ons-capital-stocks-dwellings-preliminary-2026`: 2 facts.
  - From "Preliminary capital stocks and fixed capital consumption", released 10 June 2026:
    `preliminarycapitalstocktable2026.xlsx`, 172,136 bytes, sha256 `e88090cf…8f18`.
  - Tables 1.1.1 and 2.1.1, by asset at current prices.
  - The whole economy's dwellings for 2025, with `publication_status: preliminary`.

**The gross stock is printed for dwellings**, in both editions, beside the net stock: MJF7
(gross) and MJF8 (net) for the whole economy, and in the 2025 edition for each sector.

**The 2025 edition's rows**

| Row as printed | Entity role | Gross | Net |
|---|---|---|---|
| Total non-financial corporations | `non_financial_corporations` | MIM8 | MKV5 |
| Financial corporations | `financial_corporations` | J5LD | J5LF |
| Central government | `central_government` | MJS8 | MJS9 |
| General government | `general_government` | MQ2L | MQ2T |
| Households | `households` | MJY2 | MJY3 |
| NPISH | `non_profit_institutions_serving_households` | J5LL | J5LN |
| Total households & NPISH | `households_and_npish` | MK2R | MK2S |
| Total dwellings (excluding land) | `total_economy` | MJF7 | MJF8 |

- The tables print no local government row for dwellings, and general government equals central
  government in every year.
- Note 1 on the sector rows: the release gives no asset breakdown of non-financial corporations
  into public and private corporations.

**The preliminary edition prints dwellings for the whole economy only.** Its sector tables (1.3.1
and 2.3.1) cover all assets together, so it has no dwellings by sector to port. At 172.1 kB, the
file is about a third of the size of the earlier preliminary editions ONS lists.

**Semantics**

- GBP billion, printed as whole numbers (`value_scale: 1e9`). The workbooks note that totals and
  their parts differ because of rounding. The 2025 edition's total misses the sum of its sectors
  by up to £1bn, and households and NPISH miss their two parts by up to £1bn.
- The workbooks state no estimation method, service lives or depreciation profile. Their other
  notes say that chained volume measures are referenced to 2023 and that "z" marks data not
  collected.
- ONS's bulletin of 27 November 2025 defines the gross capital stock as the value of all fixed
  assets still in use at a point in time. It defines the net stock as the gross stock less the
  consumption of fixed capital accrued up to that point. Each fact's notes carry the definition
  for its measure.
- The tables label each column by year and do not say at what point in the year a stock is
  measured. So the facts carry the year as printed, with no end-of-year coverage.
- The stocks are modelled estimates, `model_output`.

**Figures stored as text.** The 2025 workbook stores most of its figures, and its year headers,
as text: "977" rather than 977.

- A new parser, `xlsx_numeric_text_used_range`, reads a text cell that holds only a number as
  that number, as `ods_numeric_text_used_range` does for ODS files. Other text stays text.
- The preliminary workbook stores numbers, so its package uses `xlsx_used_range`.

**Parity check**

- **The 2025 edition against the 2025 balance sheet.**
  - The net stock agrees with the balance sheet's dwellings to within £0.5bn, the rounding of a
    whole billion. That holds for each of the eight sectors, in every year from 1995 to 2024.
  - At end-2024, the whole economy's net stock (MJF8) is £2,526bn, against E46Y's £2,525,540m.
- **The two preliminary editions.**
  - For 2025, the net stock (£2,631bn) is £6.1bn below the preliminary balance sheet's E46Y
    (£2,637,111m), although both were released on 10 June 2026.
  - For 2024, which neither preliminary package ports, they differ the other way: £2,567bn
    against £2,543,326m.
  - As the issue asks, these differences are reported here, not tested.

**Storage.** Both workbooks are committed, and the private `ledger-raw` bucket holds them under
`raw/uk/ons/<package id>/<year>/<sha256>/`. ONS's pages state that all content is available
under the Open Government Licence v3.0, except where otherwise stated (checked 12 November
2026).

## 3. Census 2021 TS054 tenure by MSOA

**Package.** `ons-census2021-ts054-tenure-msoa`: 65,376 facts. It covers the 7,264 middle
layer super output areas of England and Wales on 2021 boundaries (6,856 in England, 408 in
Wales), at Census Day, 21 March 2021 (`calendar_year` 2021, as for the local authority
package).

**Ported as the local authority package ports it.** `ons-census2021-ts054-tenure-lad` sets the
pattern:

- the eight detail categories and the all-households total;
- the same `uk.local_geography.tenure.<bucket>.v1` spec ids and `c2021_tenure_9_name` filters,
  so a target summing a bucket gets the same publisher facts at either geography;
- concept `ons.census2021_households`, entity `household`, provenance class `census`;
- geography level `msoa`, vintage `msoa_2021`, with the names the MSOA income package uses.

**The artifact is Nomis's bulk download, not the API query.**

- The issue asks for the local authority package's Nomis API query at geography `TYPE152` in
  place of `TYPE424`. For a user without a Nomis key, the API returns at most 25,000 rows,
  and this query has 65,376. Its first response stops partway through an MSOA, at 2,778 of
  the 7,264.
- Nomis's bulk download for TS054, `census2021-ts054.zip` (4,074,446 bytes, sha256
  `aa073110…04c2`), is listed on its Census 2021 bulk page. Its member
  `census2021-ts054-msoa.csv` has one row per MSOA and one column per category.
- Fetched in three pages on 12 November 2026 for comparison, the API's 65,376 rows equal the
  member's cells, names included.
- The member's metadata file is version 2 of TS054, issued on 6 January 2023. ONS lists later
  versions of 30 January and 28 March 2023, and the API's current rows match this file.
- The package parses the member with `zip_delimited_text_full_rows`. The four roll-up columns
  (Owned, Shared ownership, Social rented and Private rented) are sums of ported details. They
  stay in the source rows.
- The eight detail record sets share one list of MSOA rows. It is written once in the package
  file and referenced by alias, which keeps the file at 4.5 MB rather than about 20 MB.

**Semantics**

- Households, not dwellings. ONS's metadata says tenure is not available for household spaces
  with no usual residents.
- ONS's quality statement for the variable: people misreport their landlord between "Council
  or local authority" and "Housing association", so the two social rented categories should be
  added together. The social rented facts carry that note.
- Census 2021's disclosure control, targeted record swapping and cell key perturbation, can make
  counts differ slightly between tables. Every fact carries that note too.
- The eight details sum to the total in every MSOA. 1,575 cells are 0, kept as printed.

**Parity with the local authority rows**

The check maps each MSOA to its authority through the MSOA income workbook's 2021 authority
codes, merging the 17 districts that became Cumberland, Westmorland and Furness, North
Yorkshire and Somerset in April 2023. As the issue asks, the differences are reported here,
not tested.

- Of the 2,862 authority cells (318 authorities by nine categories), 722 equal the sum of their
  MSOAs.
- The rest differ by at most 26 households. The largest differences are in authorities' totals
  of over 90,000 households.
- The England and Wales total differs by 120 households: 24,783,284 summed over MSOAs, against
  24,783,164 over authorities.
- For the two social rented categories, an authority's MSOAs miss its row by at most 16 households
  ("rents from council or local authority") and 14 ("other social rented").

**Storage.** The zip is committed, and the private `ledger-raw` bucket holds it under
`raw/uk/ons/ons-census2021-ts054-tenure-msoa/2021/<sha256>/`. ONS's page for TS054 states that
all content is available under the Open Government Licence v3.0, except where otherwise stated
(checked 12 November 2026).

## Not in this change

- The chained volume measures, consumption of fixed capital, and the other assets the two
  capital stocks workbooks print.
- TS054's other geographies in the bulk zip (output areas, LSOAs, regions and countries).
- ONS's perpetual inventory method input files, which the bulletin links as a separate dataset,
  last released on 29 November 2024.
- The 2026 annual balance sheet, expected in December 2026, and the next capital stocks edition,
  as new vintages. #408 already lists the balance sheet.
