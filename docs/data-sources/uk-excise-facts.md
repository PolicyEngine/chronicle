# UK excise facts for chronicle#381

[chronicle#381](https://github.com/PolicyEngine/chronicle/issues/381) asks for the facts
behind PolicyEngine/microcosm#1359, which gives households alcohol and tobacco quantities
levelled to published clearances, checks them against duty receipts, and later maps
gambling stakes to the gambling duties. Everything here is a published aggregate; no
UKDS-licensed microdata is involved. Values are the publishers' as fetched on 23 October
2026, except the OBR workbook, archived on 6 August 2026 and not re-downloaded.
`scripts/build_uk_excise_packages.py` regenerates the OBR, HMRC and Gambling Commission
packages from the pinned bytes. The Consumer Trends package cannot be built from scratch;
see section 2.

## Summary

| request | Chronicle | facts |
|---|---|---:|
| #381.1 OBR EFO March 2026 excise lines | sheets 3.8, 3.10, 3.11, 3.12 and 3.2 added to `obr-efo-receipts-march-2026` | +181 |
| #381.2 ONS Consumer Trends, 30 September 2026 release | `ons-consumer-trends-current-price-september-2026`, which supersedes the 30 June package | 5,164 |
| #381.3 Gambling Commission GGY by sector | `gambling-commission-industry-statistics-fy2025-26` | 1,435 |
| #381.4 HMRC betting and gaming receipts by duty | `hmrc-betting-gaming-statistics-july-2026` | 376 |
| addendum: HMRC Alcohol Bulletin | `hmrc-alcohol-bulletin-july-2026` | 288 |
| addendum: HMRC Tobacco Bulletin | `hmrc-tobacco-bulletin-july-2026` | 710 |
| addendum: on/off-trade split of pure alcohol | none archivable (see below) | 0 |

Each fact's `source_record_id` is `{record_set_id}.{row value}.{measure_id}`.

## 1. OBR EFO March 2026 receipts: the excise lines

The archived `efo_receipts.xlsx` (sha256 `f65b6cb7…`); no new download. Record sets are
`obr.efo_2026_03.receipts.<line>.fy<opening year>`, one concept per line (`obr.<line>`),
in the package's existing shape. Unlike the earlier lines, these carry `period_coverage`.

- **Sheet 3.8** (cash basis, as its title and note state), rows 27 to 30, 36 and 48:
  tobacco, spirits, wine, and beer and cider duties, betting and gaming duties and vaping
  tax, 2024-25 (outturn) to 2030-31. Vaping tax is zero before it starts.
- **Sheet 3.10**, rows 6 and 8 to 14: betting and gaming duties and the seven duties they
  break into, 2025-26 to 2030-31, all forecast. The sheet states no basis. Its total equals
  sheet 3.1's "Betting and gaming taxes" (row 7), which sheet 3.1's note puts on an accrued
  basis, in every year, and differs from sheet 3.8's cash line, so its lines are stamped
  accrual. Bingo duty's near-zero values after its abolition are kept.
- **Sheet 3.11**, rows 5, 6, 8 and 9: cigarette clearances, stored in sticks (published in
  millions), and non-cigarette clearances with hand-rolled and other tobacco, stored in
  kilograms (published in thousands).
- **Sheet 3.12**: rows 5 to 7, alcohol clearances by group (beer and cider, wine, spirits),
  stored in litres of pure alcohol (published in thousands of hectolitres of alcohol), and
  rows 16 to 18, the same groups' receipts on the accrued basis the table's note states.
  Wine includes other fermented products such as fruit ciders; spirits include spirit-based
  ready-to-drinks (the footnotes, kept in the notes).
- **Sheet 3.2**, rows 10, 11 and 28: Camelot payments to the National Lottery Distribution
  Fund, the horserace betting levy and the statutory gaming levy. The sheet states no
  basis, and these lines carry none.

A duty's cash and accrued lines share a concept (`obr.beer_and_cider_duties`, say) and
differ in the `accounting_basis` dimension (`cash`, `accrual`), mirrored in
`period_coverage.accounting_basis`; the accrued lines' row ids end `_accrued`. Clearance
facts carry `published_unit` (`million_sticks`, `thousand_kilograms`,
`thousand_hectolitres_of_alcohol`) beside the stored unit (`stick`, `kilogram`,
`litre_of_pure_alcohol`). Entities: clearances are `institutional_sector` with roles
`tobacco_market` and `alcohol_market`; receipts keep the package's `person` /
`resident_population` / `public_sector_finances`.

## 2. ONS Consumer Trends: the 30 September 2026 release

`cpnsa.xlsx` from the dataset's current URL (514.2 KB, 526,549 bytes, sha256
`982307e5…`), release of 30 September 2026 covering April to June 2026. The package carries
the record sets of `ons-consumer-trends-current-price-2026` (the 30 June release, acquired
9 September) against the new workbook: the same `record_set_spec_id` values,
`record_set_id` and `source_record_id_prefix` under `ons.consumer_trends_2026_09`, vintage
`2026_09_30_release_2026_q2`, and a `source_table` naming the release.
`scripts/build_uk_consumption_tax_packages.py` regenerates its expanded record sets from
the workbook. It refreshes the headers, CDID guards and shared dimensions of the seven
series that predate chronicle#322 (04.5, 04.5.1 to 04.5.4, 07.2.2 and 07.3.2), but those
series' 217 record sets are kept by hand in the YAML. They were carried over from the June
package by renaming their ids, so the script needs the YAML and cannot build the package
from the bytes alone.

It supersedes the June package, retired as 02d43ae9 retires superseded editions: the
package and its alias are gone, and its workbook and manifest stay in
`db/data/ons/consumer_trends_current_price_2026/`. #381 asked to keep the June vintage
addressable; exporting one edition instead avoids 5,164 duplicate semantic keys, and a
consumer that re-pins takes the September values.

- Every emitted period (2020 to 2025, 2020 Q1 to 2026 Q1) sits on the row it held in June.
  2026 Q2 stays in the preserved workbook and source cells.
- ONS relabelled the national total's COICOP header from `NAT0` to `NAT`; its series (CDID
  ABPB) is unchanged. The guard reads `NAT` and the `coicop` dimension keeps `NAT0`.
- Selectors by concept, COICOP, source sheet and period match as they did; selectors by the
  June `record_set_id` prefix (`ons.consumer_trends.`) or `source_table` match nothing.
- ONS revised every period. Calendar 2024, £ million: 02.1 28,097 to 27,058; 02.2 19,989
  to 17,102; 09.4.3 11,093 to 12,828; 07.2.2 37,025 to 35,460 (the four #381 cites);
  04.5.1 electricity 26,099 to 28,129; 04.5.2 gas 14,642 to 18,298.

## 3. Gambling Commission industry statistics

"Industry Statistics – Annual report – Financial year April 2025 to March 2026 – Official
statistics" (published 17 September 2026), 440,955 bytes, sha256 `a6ea23b5…`. GBP
million, financial years from 2008-09 (sheets 1, 4 and 6 to 9 and 11) or 2015-16 (the
remote detail of sheets 10 to 10b). The Commission marks the latest year provisional (`P`)
and revisions `R`; the marker stays in `source_period_label`. A new publisher,
`gambling_commission`, routed under `raw/uk/`.

- **Geography: Great Britain, but the National Lottery is stamped United Kingdom on
  Chronicle's reading, from an unarchived page.**
  - What the workbook says: its preface (sheet 0, cell B40) describes "the gambling
    industry in Great Britain". It never names the United Kingdom or Northern Ireland,
    and it prints the National Lottery as one total, with no country split.
  - What Chronicle stamps: Great Britain (`K03000001`) for every fact except the
    National Lottery's own tables, sheet 1's column M (its own record sets) and sheet 11.
    Those 160 facts are stamped United Kingdom (`K02000001`).
  - Why: the Commission's
    [What we regulate](https://www.gamblingcommission.gov.uk/about-us/guide/what-we-regulate)
    page lists "The National Lottery across the United Kingdom" among what it regulates,
    and licenses the other sectors for Great Britain. The page was last updated
    5 May 2026 and read on 23 October 2026.
  - The limit: Chronicle does not archive that page, so no preserved byte backs the UK
    stamp. The values are the workbook's either way; only the geography is a reading.
    Each lottery fact's notes say this, and the generator asserts that the preface
    still reads Great Britain.
  - For consumers: a Great Britain filter returns no lottery facts. Sheet 1's overall
    total includes the lottery and stays Great Britain, with a note, so within the
    Commission's facts the lottery line and the total sit under different geographies.
- **Remote gambling before November 2014.** Sheet 1's remote lines follow the regime before
  the November 2014 legislation until 2013-14, where they equal sheet 12, and 2014-15 adds
  sheet 12's April to October 2014 to sheet 10's November 2014 to March 2015. Those years'
  `period_coverage` notes say so; the generator asserts both identities.

- Concepts: `gambling_commission.gross_gambling_yield` and `gambling_commission.turnover`,
  with `gambling_sector`, `gambling_activity` and `betting_event`;
  `gambling_commission.gaming_machine_gross_gambling_yield`, with `gambling_venue` and
  `machine_category`; `gambling_commission.lottery_sales` with `gambling_sector` and
  `sales_channel`; `gambling_commission.lottery_sales_distribution` with `gambling_sector`
  and `sales_use`. Every fact carries each dimension of its family, `all` at the margins.
- Sheet 1: GGY by sector, with and without the National Lottery and lotteries.
- Sheets 6 to 8: non-remote betting (over the counter, machines, on course, pool), bingo
  and casino (games, machines), turnover and GGY.
- Sheet 10: remote turnover by sector and remote GGY in total. Sheet 10a: remote casino
  by game, including slots. Sheet 10b: remote betting by type (betting, exchange, pool)
  and by event (football, horses and eight more, with unallocated revenue share).
- Sheet 4: gaming machine GGY by venue and by category: B1 to B4, C, D and aggregated
  categories to March 2024; B, C and D from April 2024, after the category B changes of
  1 July 2024.
- Sheets 9 and 11: lotteries and the National Lottery, sales by channel and their
  distribution (good causes, prizes, expenses; for the National Lottery also lottery duty,
  retailers' commission, and costs and operator profit).
- Left out:
  - totals that restate a line already emitted. Sheets 6 to 8's GGY totals restate sheet
    1's sector lines, differing by at most £0.01m (sheet 6 in 2024-25, sheet 7 in 2011-12
    and 2022-23, sheet 8 in 2011-12), so in those years an activity split can miss its
    `all` margin by that much. Sheet 10's sector GGY and the totals of sheets 10a to 10c
    restate sheets 1 and 10 exactly. Sheet 4's by-category total (column I) restates
    column B, differing by at most £0.012m, in 2010-11 to 2013-14;
  - percentage changes; machine, premises and account counts; funds held in customer
    accounts; the External Lottery Manager columns;
  - quarterly rows, and the November 2014 to March 2015 part year;
  - sheets 5, 6a to 6d, 7a, 7b, 8a and 8b (finer splits #381 does not ask for), sheet 10c
    (it restates sheets 1 and 10) and sheet 12 (remote gambling before November 2014);
  - `-` cells, and published zeros that stand for no measurement: turnover the
    Commission reports as zero in every year (bingo machines, peer-to-peer poker, betting
    exchanges), betting-shop machine turnover for 2024-25 and 2025-26 (zeros over
    quarters that are all `-`), and the National Lottery's 2008-09 sales channels (zeros
    against a positive total). That is 44 cells; each rule is asserted against the bytes.

## 4. HMRC UK Betting and Gaming Statistics

`2026_Jul_Bet_and_Gam_Tab.ods` (published 30 September 2026), 85,224 bytes, sha256
`3979df37…`. Accredited official statistics, United Kingdom.

- Table 1a: receipts of each duty (General Betting, Pool Betting, Gaming, Remote Gaming,
  Amusement Machine Licence, Bingo, Machine Games, Lottery), their betting total and the
  total, financial years 1986-87 to 2025-26, GBP thousand:
  `hmrc.betting_and_gaming_duty_receipts` with `gambling_duty`. HMRC builds them from
  banking data, payments falling due the month after each accounting period, so they carry
  the cash accounting basis. The 2024-25 total matches OBR sheet 3.8's cash line.
- Table 2a: Machine Games Duty liabilities by rate band and in total, 2013-14 to 2025-26:
  `hmrc.machine_games_duty_liabilities` with `mgd_rate`. Liabilities declared on returns,
  refreshed from April 2018, not receipts. Its total-receipts column repeats Table 1a.
- `[No Data]` (a duty not in force) and `[Disclosive]` cells emit no fact. `[revised]`
  stays in `source_period_label`.

## 5. HMRC Alcohol Bulletin

"Alcohol Bulletin tables (May 2026 to July 2026)", `Alcohol_Tables_Jul26.ods` (published
28 August 2026), 60,468 bytes, sha256 `e01eba25…`. Accredited official statistics, United
Kingdom. Each product sheet's financial-year table (1a to 5a) and calendar-year table (1b
to 5b), for 2023 to 2025.

- `hmrc.alcohol_clearances`, in litres of pure alcohol, for beer, cider, wine, other
  fermented products and spirits, with `abv_band`, `duty_relief` and `duty_point`. Each
  clearance fact carries all three, `all` at the margins; each breakdown partitions the
  total. Draught relief is published for beer and cider (alone and with small producer
  relief); other fermented products combine draught and small producer relief; wine and
  spirits have no relief split.
- The bulletin publishes clearances in litres of alcohol only (since February 2024; before,
  hectolitres). No clearance volume in litres of product exists, so strengths cannot be
  derived from clearances. `hmrc.uk_beer_production` (litres and litres of alcohol) and
  `hmrc.uk_potable_spirits_production` are UK production, not clearances. The Beer
  sheet calls November 2024 to March 2025 production partly imputed: the 2024-25,
  calendar 2024 and calendar 2025 production facts carry that note.
- Clearances cover the regime introduced in August 2023 only, so the 2023 to 2024 and
  calendar 2023 clearance facts start on 1 August 2023 (`period_coverage`); receipts and
  production cover whole years.
- `hmrc.alcohol_duty_receipts` by product (beer, cider, spirits, wine with other fermented
  products) and in total, cash basis, GBP million. HMRC flags wine, other fermented
  products and cider receipts from April 2023 as under further assurance.

## 6. HMRC Tobacco Bulletin

"Tobacco Bulletin tables July 2026", `Tobacco_Tab_Jul_26.ods` (published 28 August 2026),
110,472 bytes, sha256 `41154c1d…`. Accredited official statistics, United Kingdom.

- `hmrc.tobacco_clearances` with `tobacco_product`: cigarettes in sticks (published in
  millions); cigars, hand-rolling tobacco, other and the non-cigarette total in kilograms
  (published in thousands). Financial years 1990-91 to 2025-26 (Table 2a) and calendar
  years 1991 to 2025 (Table 2b).
- The monthly tables start in January 1991, and the receipts mark January 1991 `[X]`, so
  three record sets are part years. The 1990 to 1991 clearances cover January to March
  1991, and the 1990 to 1991 and calendar 1991 receipts start in February 1991. Their
  `period_coverage` starts there, with a note; their lineage gains the monthly table's
  first-month label and, for receipts, its `[X]` cell. The generator asserts that each
  annual figure equals its published months.
- `hmrc.tobacco_duty_receipts` by the same products and overall, cash basis, GBP million
  (Tables 1a and 1b).
- Tobacco for heating has no column: both sheets' notes include its receipts in "Other".
  The clearances sheet's note repeats the receipts sheet's text ("Values are in £
  millions"); the column headers give the units. OBR sheet 3.11's "Other tobacco
  products" corresponds to HMRC's cigars plus other.

## Licences

Each new manifest records its licence, attribution and evidence (`license`,
`license_url`, `attribution`, `license_evidence`, `license_verified_at`), checked on
23 October 2026.

- HMRC's three workbooks and ONS's `cpnsa.xlsx`: the Open Government Licence v3.0, which
  their GOV.UK and ONS pages state for all content not otherwise marked. The Alcohol
  Bulletin's cover adds that it is Crown copyright and may be used if the source is made
  clear.
- The Gambling Commission's workbook: the Open Government Licence v3.0, on the strength of
  data.gov.uk's listing of the Commission's Industry Statistics series, whose entry names
  the November 2024 edition. Neither the workbook nor its publication page states a
  licence, and the Commission's website terms require prior approval to copy material
  unless otherwise stated.
- The OBR workbook was archived before this change, and its manifest is unchanged.

## On-trade and off-trade split: not archived

Public Health Scotland's MESAS sales series now sits in the Alcohol Consumption and Harms
Dashboard (release of 30 June 2026; official statistics). It covers Scotland, and England
and Wales, each alone, in calendar years 2017 to 2025 (England and Wales to 2024), by trade
sector and drink type. It is not archived: the figures download only through the
dashboard's per-session buttons (no fixed file), the dashboard says "Copyright for these
data remain with the data providers" (NielsenIQ and Circana), and there is no Great
Britain or UK total.
