# UK high-value housing sources (chronicle#343)

[#343](https://github.com/PolicyEngine/chronicle/issues/343) asks for the published
sources Microcosm needs to say where high-value homes are, for its local targets
(the high value council tax surcharge, stamp duty and capital gains on property).
Chronicle carries two kinds of thing for it:

- **Fact packages**, for publisher tables that Chronicle parses into facts:
  - `obr-hvcts-costing-april-2026`: the OBR costing note's Tables 1.1, 1.2 and
    1.5 and three parameters stated in its text (63 facts, source projections).
  - `ons-hpssa-pcon24-year-ending-march-2026`: ONS sales counts and median price
    paid by 2024 constituency and property type, for the years ending March 2023
    to 2026 (22,940 facts).
- **Raw-only registrations**, for releases that Chronicle pins and archives but
  does not parse:
  - `hmlr-price-paid-data-yearly-august-2026` (the 32 yearly files, 1995 to
    2026) and `hmlr-price-paid-data-monthly-update-august-2026` (the change file):
    HM Land Registry Price Paid Data, August 2026 release;
  - `hmlr-uk-hpi-full-file-july-2026`: the UK House Price Index full file;
  - `ons-nspl-august-2026`: the National Statistics Postcode Lookup.

  These follow the #269 registrations, such as `ons-oa21-pcon-jul2024-lookup`:
  each has a manifest with publisher URL, sha256, size, retrieval time and
  vintage, and an R2 copy. None has a `source_package.yaml`, an alias or a bundle
  entry. A consumer references one by `{source_id, package_id, year, sha256,
  filename}`.

## Why raw-only

- **Price Paid Data is record-level.** Each row is one registered transfer, and
  the price is HM Land Registry's assertion. Its 31.6 million rows are not
  Chronicle facts, and every aggregate the issue needs (latest sale per
  property, category A only, uprated, above a threshold, by area) is a
  computation, which belongs to Microcosm.
- **The UK HPI is the uprating input, not a target.** Microcosm needs each local
  authority's monthly index by property type from January 1995. That is about two
  million published cells, out of proportion to a bundle of about a million
  facts, and Microcosm reads them as a lookup.
- **The NSPL is a postcode lookup.** It is the same kind of artifact as the
  output-area lookups #269 registered.

## Storage

| registration | file | bytes | in git |
|---|---|---|---|
| `hmlr-price-paid-data-yearly-august-2026` | `pp-1995.csv` to `pp-2026.csv` | 5,525,539,417 in 32 files | no |
| `hmlr-price-paid-data-monthly-update-august-2026` | `pp-monthly-update-new-version.csv` | 15,840,574 | no |
| `hmlr-uk-hpi-full-file-july-2026` | `UK-HPI-full-file-2026-07.csv` | 35,012,747 | no |
| `ons-nspl-august-2026` | `NSPL_AUG_2026.zip` | 185,109,467 | no |

These are the first Chronicle registrations whose bytes are archived in R2 and
never committed:

- Price Paid Data carries Royal Mail and Ordnance Survey address data. HM Land
  Registry licenses that data only for personal or non-commercial use and for
  residential property price information services, and Chronicle is a public
  repository.
- The NSPL zip is above GitHub's 100 MB file limit.
- Each monthly UK HPI full file revises the last. Nothing in Chronicle parses
  it, so committing every vintage would add 35 MB of history a month for no
  build.

Each of their file entries says so with `storage.local: false`:

- `inventory-artifacts` and `publish-raw` accept such an entry with no local
  copy, so both stay valid over `db/data` on a fresh clone;
- they still check the bytes when a local copy is present, and `publish-raw`
  uploads from it;
- `verify-raw` checks the R2 object against the pin;
- an entry marked R2-only with no `storage.r2` location is an error.

`.gitignore` keeps the local copies out of commits.

Price Paid is registered as HM Land Registry's yearly files, not its single
`pp-complete.csv` (5,525,539,417 bytes). `publish-raw` uploads through
`wrangler r2 object put`, which refuses files above 300 MiB; the largest yearly
file (`pp-2002.csv`) is 239,344,429 bytes. The 32 yearly files of a release hold
exactly the complete file's rows, split by year of transfer. For this release,
order-independent row digests by year agree between the two (31,610,742 rows).

## HM Land Registry Price Paid Data

- **Release:** August 2026 data, published 29 September 2026 (objects last
  modified 28 September 2026). HM Land Registry updates the data on the 20th
  working day of each month; the September 2026 release is due at the end of
  October 2026.
- **Files:**
  - `pp-YYYY.csv`, 1995 to 2026: every standard (A) and additional (B)
    transaction with a date of transfer in that calendar year, as at the
    release, with the release's amendments and deletions applied. Together they
    are HM Land Registry's single file. The manifest keys each file by its year.
  - `pp-monthly-update-new-version.csv` is the release's change file: the
    month's new transactions and the additions, changes and deletions it makes
    to earlier releases.
- **Versioning:** each monthly release revises every yearly file, so a release is
  a new pair of registrations under its own directories (for example
  `price_paid_data_yearly_september_2026`). A consumer pins one release by the
  sha256 of each file. Chronicle does not apply a change file to a snapshot;
  choosing a release is the consumer's job.
- **Licence:** Open Government Licence v3.0 with HM Land Registry's statement,
  "Contains HM Land Registry data © Crown copyright and database right 2021.
  This data is licensed under the Open Government Licence v3.0." The address
  fields (postcode, PAON, SAON, street, locality, town/city, district, county)
  carry the Royal Mail and Ordnance Survey terms above.

### Field contract

CSV, comma-separated, every field double-quoted, no header row, 16 fields in
HM Land Registry's order ([About the Price Paid Data](https://www.gov.uk/guidance/about-the-price-paid-data)):

| # | field | format and codes |
|---|---|---|
| 1 | transaction unique identifier | `{` 36 hexadecimal digits and hyphens `}`; a category change deletes the old identifier and adds a new one |
| 2 | price | whole pounds, the sale price stated on the transfer deed |
| 3 | date of transfer | `YYYY-MM-DD 00:00`, completion date on the deed |
| 4 | postcode | as at the transaction; later reallocations are not applied |
| 5 | property type | `D` detached, `S` semi-detached, `T` terraced (includes end-of-terrace), `F` flat/maisonette, `O` other |
| 6 | old/new | `Y` newly built, `N` established building |
| 7 | duration | `F` freehold, `L` leasehold (leases of 7 years or less are not recorded); `U` also occurs |
| 8 | PAON | primary addressable object name |
| 9 | SAON | secondary addressable object name (flat or unit) |
| 10 | street | |
| 11 | locality | |
| 12 | town/city | |
| 13 | district | |
| 14 | county | |
| 15 | PPD category type | `A` standard price paid (single residential property sold for value, from January 1995); `B` additional price paid (repossessions, buy-to-lets identified by a mortgage, transfers to non-private individuals, and property type `O`; identified from October 2013, though 1,873 transfers dated before 2013 also carry `B` in this release) |
| 16 | record status | `A` addition, `C` change, `D` deletion; meaningful in the monthly file |

Excluded by HM Land Registry: sales not lodged for registration, sales not for
value (gifts, right-to-buy discounts, transfers on divorce, court orders and the
other cases its guidance lists), and sales whose price includes VAT.

### Parity

- **Rows by year of transfer.** HM Land Registry publishes no row counts for a
  release, so the release itself is the reference. Each yearly file's rows equal
  the complete file's rows for that year (order-independent row digests by year
  agree), and every row has 16 fields:

| year | rows | of which category B |
|---|---:|---:|
| 1995 | 797,158 | 11 |
| 1996 | 965,427 | 8 |
| 1997 | 1,094,673 | 13 |
| 1998 | 1,050,706 | 14 |
| 1999 | 1,195,090 | 16 |
| 2000 | 1,129,596 | 36 |
| 2001 | 1,246,054 | 31 |
| 2002 | 1,351,982 | 30 |
| 2003 | 1,235,660 | 41 |
| 2004 | 1,232,193 | 60 |
| 2005 | 1,061,836 | 97 |
| 2006 | 1,326,330 | 108 |
| 2007 | 1,272,507 | 159 |
| 2008 | 649,722 | 185 |
| 2009 | 625,377 | 163 |
| 2010 | 663,358 | 185 |
| 2011 | 661,265 | 282 |
| 2012 | 668,982 | 434 |
| 2013 | 811,189 | 19,527 |
| 2014 | 985,204 | 65,836 |
| 2015 | 1,011,782 | 92,825 |
| 2016 | 1,046,656 | 124,031 |
| 2017 | 1,067,647 | 160,761 |
| 2018 | 1,037,666 | 162,102 |
| 2019 | 1,012,236 | 169,217 |
| 2020 | 897,978 | 144,590 |
| 2021 | 1,281,983 | 195,049 |
| 2022 | 1,077,205 | 167,264 |
| 2023 | 861,502 | 153,187 |
| 2024 | 931,453 | 167,548 |
| 2025 | 974,087 | 164,626 |
| 2026 | 386,238 | 55,113 |
| **all** | **31,610,742** | **1,843,549** |

  Every row of a yearly or complete file has record status `A`; `C` and `D` occur
  only in the monthly file. Duration `U` occurs on 525 rows.
- **`pp-2024.csv`** has 931,453 rows in this release (763,905 category A and
  167,548 category B), not the 881,757 the issue quotes from
  [PolicyEngine/uk-mansion-tax](https://github.com/PolicyEngine/uk-mansion-tax).
  That figure matches neither the file nor its category A rows.
- **Against the ONS constituency workbook.** ONS computes the workbook from Price
  Paid. Category A sales of detached, semi-detached, terraced and flat
  properties in this release, by year of transfer, against the sum of the
  workbook's 575 seats:

| year ending March | Price Paid, this release | ONS, sum of 575 seats | difference |
|---|---:|---:|---:|
| 2023 | 873,130 | 872,848 | +282 (0.03%) |
| 2024 | 692,752 | 692,252 | +500 (0.07%) |
| 2025 | 855,338 | 853,195 | +2,143 (0.25%) |
| 2026 | 707,700 | 659,366 | +48,334 (7.33%) |

  The gap grows towards the latest year. That fits the lag between sale and
  registration (HM Land Registry: typically two weeks to two months, sometimes
  longer), since this release is later than ONS's extract.

## UK House Price Index full file

- **Release:** July 2026, published 16 September 2026 on the
  [data downloads page](https://www.gov.uk/government/statistical-data-sets/uk-house-price-index-data-downloads-july-2026).
  Each release revises earlier months, so a consumer pins it by sha256.
- **Layout:** one row per area and month, 151,920 rows, with a 54-column header
  row. `Date` is `dd/mm/yyyy`, `RegionName` and `AreaCode` (GSS) identify the
  area. Country and region series start in April 1968, and the 317 England and
  Wales local authorities (E06, E07, E08, E09, W06) each run 379 months from
  January 1995 to July 2026.
- **Measures:** `AveragePrice`, `Index` (January 2023 = 100), `IndexSA`,
  `AveragePriceSA`, `SalesVolume`, and for each breakdown its `Price`, `Index`,
  `1m%Change` and `12m%Change`:
  - property type: `Detached`, `SemiDetached`, `Terraced`, `Flat`;
  - funding: `Cash`, `Mortgage` (with sales volumes);
  - buyer: `FTB`, `FOO`;
  - build: `New`, `Old` (with sales volumes).

  The sales-volume columns are blank before 1995 and for the latest months while
  registrations complete. The Isles of Scilly (`E06000053`) have no series.
- **Licence:** Open Government Licence v3.0. The UK HPI is produced by HM Land
  Registry with the Office for National Statistics, Registers of Scotland and
  Land and Property Services Northern Ireland. HM Land Registry's
  [About the UK House Price Index](https://www.gov.uk/government/publications/about-the-uk-house-price-index/about-the-uk-house-price-index)
  prescribes the attribution for any use or publication of the data: "Contains
  HM Land Registry data © Crown copyright and database right 2020. This data is
  licensed under the Open Government Licence v3.0."

## National Statistics Postcode Lookup

- **Release:** August 2026, from the
  [ONS Open Geography Portal](https://geoportal.statistics.gov.uk/datasets/9d8364ebae8b4439aa66cda440e54fc8).
  Postcodes are as at the third Friday of the month before release.
- **Layout:** `Data/NSPL_AUG_2026_UK.csv`, 2,729,090 current and terminated UK
  postcodes, with 35 fields in a header row. The same rows are split by postcode
  area under `Data/multi_csv`, and the user guide and code lists sit alongside.
- **Fields #343 uses:**
  - `pcds`: postcode, single space;
  - `dointr` and `doterm`: introduction and termination, `yyyymm`; `doterm` is
    blank for a live postcode. Terminated postcodes are kept, so old sales still
    place.
  - `oa21cd`, `lsoa21cd`, `msoa21cd`: 2021 Census output area, LSOA and MSOA;
  - `lad26cd`: local authority;
  - `pcon24cd`: Westminster constituency, July 2024 boundaries;
  - `ctry26cd` and `usrtypind` (0 small user, 1 large user).

  Every geography is assigned best-fit from the postcode's 2021 output area.
  For all 2,413,799 England and Wales postcodes, live and terminated, the
  `oa21cd` join to `ons-oa21-pcon-jul2024-lookup` gives the same constituency as
  `pcon24cd`.
- **Licence:** Open Government Licence v3.0, with the attributions the user
  guide requires: OS data and Royal Mail data, Crown copyright and database
  right; Source: Office for National Statistics. Commercial use of the Northern
  Ireland (`BT`) postcodes needs a separate Land and Property Services licence.

## OBR costing of the high value council tax surcharge

- **Release:** supplementary forecast information release 'Costing of high value
  council tax surcharge', dated 2 April 2026 (PDF created the same day), linked
  from the
  [November 2025 Economic and fiscal outlook page](https://obr.uk/efo/economic-and-fiscal-outlook-november-2025/).
  Fetched 12 October 2026, sha256 `dfc64839…`, 126,847 bytes, committed.
- **Facts:** `obr-hvcts-costing-april-2026`, 63 source projections for England.
  These are Tables 1.1 and 1.2 (properties in scope by band, static and
  post-behaviour, 2028-29 to 2030-31), Table 1.5 (the costing, 2026-27 to
  2030-31) and three parameters in paragraph 1.13.
- **Licence:** the OBR's
  [copyright page](https://obr.uk/copyright/) allows use and re-use of its
  material, logos excepted, under the Open Government Licence. The costing is
  the government's (HMRC's), certified by the OBR.

## ONS house price statistics for small areas by parliamentary constituency

- **Release:** edition year ending March 2026, released 17 September 2026, from
  the
  [dataset page](https://www.ons.gov.uk/peoplepopulationandcommunity/housing/datasets/parliamentaryconstituencyhousepricestatisticsforsmallareas).
  Fetched 12 October 2026, sha256 `e5a1d593…`, 5,935,546 bytes, committed. ONS
  updates the dataset twice a year; the next edition is due in March 2027.
- **Facts:** `ons-hpssa-pcon24-year-ending-march-2026`, 22,940 sales counts and
  median prices, for 575 July 2024 constituencies by property type and the four
  years ending March 2023 to 2026.
- **Licence:** Open Government Licence v3.0. The cover sheet says the statistics
  are adapted from HM Land Registry data licensed under the Open Government
  Licence v3.0, and asks users to credit "Source: Office for National
  Statistics".

## What stays in Microcosm

As #343 sets out, these steps belong to Microcosm, and none of their values
becomes a Chronicle fact:

- de-duplicating Price Paid to each property's latest sale;
- dropping category B and record-status deletions;
- uprating each sale by the UK HPI to a valuation date. The Isles of Scilly
  have no UK HPI series, so a postcode, `lad26cd`, HPI join drops their 113
  postcodes (94 live) unless Microcosm falls back, for example to Cornwall
  (`E06000052`) or the South West;
- the owner-occupier adjustment (census tenure and the OBR's 40 per cent
  non-owner-occupied share);
- counting homes above thresholds by local authority and constituency;
- binding the counts as targets with tolerances.
