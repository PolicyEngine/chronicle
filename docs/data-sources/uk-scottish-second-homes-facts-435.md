# Scotland's second homes and empty dwellings for chronicle#435

[chronicle#435](https://github.com/PolicyEngine/chronicle/issues/435) asks for two sets of UK
facts for Microcosm's next data PR (PolicyEngine/microcosm#1095). This page covers item 1:
Scotland's second homes and empty dwellings by council area. Microcosm levels Scotland's
council tax bills to the liability of every chargeable dwelling, and these counts let it take
out the dwellings no survey household lives in. Item 2, the November 2026 edition of ONS's NEET
release, follows that release.

One package adds 396 facts. `scripts/build_uk_scottish_second_homes_package.py` writes it from
the pinned bytes, asserting the publisher's text, and `--check` compares the output with the
committed YAML. `tests/test_source_uk_scottish_second_homes.py` re-reads the pinned workbook. The
statistics are official aggregates under the Open Government Licence v3.0; no microdata is read
or stored. The workbook is committed and in R2 (`chronicle publish-raw`, read back by
`chronicle verify-raw`).

## Source

| Package | File | Publisher, date | sha256 |
|---|---|---|---|
| `scotgov-second-homes-empty-properties-2025` | `Empty_properties_and_second_homes_September_2025_Web_Table.xlsx` | Scottish Government, [Second homes and empty properties in September 2025](https://www.gov.scot/publications/second-homes-and-empty-properties-in-september-2025/), web table, 16 December 2025 | `082d5dc7…` |

The file is renamed without spaces; the manifest keeps the publisher's file name as
`publisher_filename`. The councils' council tax base (CTAXBASE) returns give the counts.

## What is ported

All six tables of the web table, for Scotland and its 32 council areas, at September 2024 and
September 2025. Each class is its own concept, and each fact quotes the cover sheet's
definition and the workbook notes on its class in `concept_evidence_notes`.

- **Second homes** (`scotgov.council_tax.second_homes`): "homes which are furnished and lived in
  for at least 25 days in a 12-month period but not as someone's main residence".
- **Empty properties** (`scotgov.council_tax.empty_properties`): "properties which have been empty
  for more than 6 months and are liable for council tax".
- **Long-term empty properties** (`scotgov.council_tax.long_term_empty_properties`): empty for
  12 months or more, a subset of empty properties.
- **Long-term empty properties with a discount below 10% or an increase**
  (`scotgov.council_tax.long_term_empty_properties_discount_below_10_percent_or_increase`), a
  subset of long-term empty properties.
- **Unoccupied exemptions** (`scotgov.council_tax.unoccupied_exemptions`): "the total number of
  dwellings exempt from Council Tax due to being unoccupied", for example housing awaiting
  demolition or a new build waiting to be occupied.
- **Second homes and empty properties** (`scotgov.council_tax.second_homes_and_empty_properties`):
  the worksheet's total. The contents sheet calls it "Total Second Homes and Long Term Empty
  Properties", but in every cell it is second homes plus empty properties (6 months or more).

Each year is month `YYYY-09` ("Data presented for September each year"), the month the
`scotgov-council-tax-bands-2024` and `-2025` packages give CTAXBASE's chargeable dwellings.
Second homes and empty properties are liable for council tax, so they are entity role
`chargeable_dwelling`, as MHCLG's Council Taxbase lines 11 to 17 are for England. Unoccupied
exemptions are `exempt_dwelling`. Areas carry the register's codes (Scotland `S92000003`, the
councils `S12…`). The web table spells some areas its own way ('Edinburgh, City of', 'Glasgow'
on two sheets, '&' for 'and', 'SCOTLAND', trailing spaces). Each row guard keeps its sheet's
exact text, and each area's geography name is its first sheet's spelling.

## Read them this way

- **Counts, not liability.** The edition gives dwellings, not Band D equivalents. CTAXBASE's
  published tables give chargeable dwellings by band only, with no class split, so a share of
  the liability by class cannot be taken from published figures. Premiums can double a second
  or empty home's bill. Since April 2024, councils can apply "a 50% Council Tax discount, the
  standard rate, or an up to 100% council tax premium (double the rate) on second homes", and
  30 had introduced the premium in some form by September 2024 (note 14). From April 2013 they
  could remove the discount on long-term empty properties or set an increase (note 2).
  Councils' policies are on the
  [council tax datasets page](https://www.gov.scot/publications/council-tax-datasets/)
  ("Second homes and long term empty policies and discounts"), not ported here.
- **Empty homes may be overstated.** The guidance on empty properties was strengthened in
  September 2024 so that councils left out properties empty less than 6 months. Before that,
  some councils included them, so "Empty homes (properties empty for more than 6 months) will
  therefore be overstated in such instances" (note 10, and the methodology page, both "prior to
  2024"; the edition's empty homes page says "prior to 2025"). South Ayrshire still includes "a
  very small number" of them (note 11).
- **Na h-Eileanan Siar, 2024.** After a cyber attack, its 2024 figures "are not as up to date as
  they would normally be" (note 13). The 2024 record sets quote this note.
- **Trends.** "Trends over time for all these statistics should be interpreted with some
  caution", as councils' reclassifications and systems move the counts (note 1).
- **Not counted here.** Properties empty for 6 months or less, which are liable for council tax,
  and any split by council tax band or by discount or premium rate beyond the long-term empty
  table.
- **One misprinted cell.** The Scotland row of the long-term empty table with a discount below
  10% or an increase prints 25,073 at September 2025. Its 32 councils add to 25,703, the figure
  the edition's empty homes page gives ("25,703 properties (79%) received either a discount of
  less than 10% or a Council Tax premium"). Both are ported as printed, and the generator fails
  if a corrected file is pinned.

## Parity

- In every table and year, the 32 councils add to Scotland, except the misprinted cell above.
- In every area and year, second homes plus empty properties is the total. Long-term empty is
  within empty, and the discount-or-increase subset is within long-term empty.
- The September 2024 edition's web table (17 December 2024, sha256 `8c796fb0…`) prints the
  same cells for every year to 2024: this edition revises none of them.
- The edition's key points give each change from 2024, and the packaged cells reproduce them:
  second homes −679 (21,606 to 20,927), empty properties +915 (43,538 to 44,453), long-term
  empty +741 (31,596 to 32,337) and unoccupied exemptions −2,790 (47,779 to 44,989).

## Not ported

- The years before 2024 (from 1996, 2005, 2013 or 2014, by table), which chronicle#435 does
  not ask for, and some of which notes 3 to 9 qualify.
- The "Charts and Tables" workbook. Its Table 1 repeats the September 2025 counts with a
  dwellings estimate and rates per 10,000 dwellings, and its charts repeat Scotland's series.
- The September 2024 edition, whose cells this edition repeats unrevised.
