# Publisher evidence: 2023 Census Place summaries

The two package families use Stats NZ's
[Place summaries tool](https://tools.summaries.stats.govt.nz/) export,
“Download data → Place summaries”. The offline lane verified the 18 staged
files against their supplied receipts: all SHA-256 digests and byte sizes
match, every response is HTTP 200, and every file has 2,030 data rows and
22 columns. Each file contains one place, with the same 16 selected 2023
`Count` row identities.

## Artifacts and download metadata

The original and final URLs, fetch times, sizes, checksums, and
`content_disposition_filename` are recorded in the per-place manifests under
`db/data/stats_nz/census_2023_place_summaries/`. The complete files are copied
without changing their bytes. Both package families reference these same
artifacts rather than committing a second copy.
The artifact directory's `.gitattributes` marks `*.csv binary` so Git preserves
the publisher's CRLF bytes when the hub commits them.
The CSV cell representation uses family-specific Chronicle virtual sheets,
`place_summaries_<place>_households` and `place_summaries_<place>_families`.
These names are not publisher worksheets; they distinguish the families'
different compact selected-row orders and prevent source-cell key collisions.

The national endpoint is
`https://tools.summaries.stats.govt.nz/api/export-csv/newzealand/NZ/`.
Regional endpoints use the opaque classification identifier and publisher
code from each receipt; no endpoint is reconstructed from a guessed
identifier. For example, the Northland receipt pins
`https://tools.summaries.stats.govt.nz/api/export-csv/rkTah6u2O2VYyP4Y/1/`.
Source pages retain the tool URL and each regional page, such as
[Auckland Region](https://tools.summaries.stats.govt.nz/places/RC/auckland-region).

| Local artifact | Publisher code | Bytes | Receipt Content-Disposition filename |
| --- | --- | ---: | --- |
| `place-summaries-nz.csv` | NZ | 394086 | `place-summaries-new-zealand-20261011-080638.csv` |
| `place-summaries-rc-01.csv` | 1 | 410926 | `place-summaries-northland-region-20261011-091200.csv` |
| `place-summaries-rc-02.csv` | 2 | 409747 | `place-summaries-auckland-region-20261011-091008.csv` |
| `place-summaries-rc-03.csv` | 3 | 407261 | `place-summaries-waikato-region-20261011-091201.csv` |
| `place-summaries-rc-04.csv` | 4 | 419296 | `place-summaries-bay-of-plenty-region-20261011-091202.csv` |
| `place-summaries-rc-05.csv` | 5 | 408338 | `place-summaries-gisborne-region-20261011-091203.csv` |
| `place-summaries-rc-06.csv` | 6 | 414894 | `place-summaries-hawke's-bay-region-20261011-091204.csv` |
| `place-summaries-rc-07.csv` | 7 | 408612 | `place-summaries-taranaki-region-20261011-091204.csv` |
| `place-summaries-rc-08.csv` | 8 | 431319 | `place-summaries-manawatu-whanganui-region-20261011-072623.csv` |
| `place-summaries-rc-09.csv` | 9 | 413326 | `place-summaries-wellington-region-20261011-091205.csv` |
| `place-summaries-rc-16.csv` | 16 | 406093 | `place-summaries-tasman-region-20261011-091206.csv` |
| `place-summaries-rc-17.csv` | 17 | 406118 | `place-summaries-nelson-region-20261011-091207.csv` |
| `place-summaries-rc-18.csv` | 18 | 416244 | `place-summaries-marlborough-region-20261011-091207.csv` |
| `place-summaries-rc-12.csv` | 12 | 414035 | `place-summaries-west-coast-region-20261011-091208.csv` |
| `place-summaries-rc-13.csv` | 13 | 415340 | `place-summaries-canterbury-region-20261011-091209.csv` |
| `place-summaries-rc-14.csv` | 14 | 404747 | `place-summaries-otago-region-20261011-091210.csv` |
| `place-summaries-rc-15.csv` | 15 | 412514 | `place-summaries-southland-region-20261011-091211.csv` |
| `place-summaries-rc-99.csv` | 99 | 417115 | `place-summaries-area-outside-region-20261011-091211.csv` |

The filename timestamp is download metadata, not a census reference date or
an asserted release date. The receipts show fetches on 10 October 2026 UTC.
The hub reports fetching Auckland twice and obtaining identical bytes and
the same SHA-256, despite the endpoint generating a timestamped filename.
Only one Auckland receipt/file is staged here; this lane verified that file's
receipt match and does not invent a second fetch record. The stable content
is pinned by hash, rather than by the generated filename timestamp.

Licence: `CC BY 4.0`, with attribution to Stats NZ. The hub verified Stats NZ's
[copyright page](https://www.stats.govt.nz/about-us/copyright/) on
10 October 2026 and supplied its default Creative Commons Attribution 4.0
International licence statement. This offline lane did not re-fetch the page.
Each R2 block uses Chronicle's `build_r2_key` for the immutable `raw/nz` key.
The manifests are named `manifest-<place>.yaml`, not `manifest.yaml`, so read
them back with `chronicle verify-raw --root
db/data/stats_nz/census_2023_place_summaries --manifest 'manifest-*.yaml'`.
The hub published the 18 objects with `chronicle publish-raw` and verified
each by streaming it back (SHA-256 matches) on 2026-10-10.

## Exact selected rows and values

The following are physical CSV line numbers, with the header on line 1.
Every line below is selected separately from each place's own file. Count
text has six fractional zeroes, with `decimals = 0`; values retain scale 1.
The section, category code and descriptor, place code and descriptor, period,
duration, value type and status fields remain source-row evidence.

| CSV line | Section | Category code | Exact published category | New Zealand | Auckland Region |
| ---: | --- | --- | --- | ---: | ---: |
| 1652 | Number of families and households | F | Families | 1294503 | 426684 |
| 1655 | Number of families and households | H | Households | 1780527 | 539490 |
| 1662 | Family type | 1 | Couple Without Children | 537486 | 151557 |
| 1665 | Family type | 2 | Couple With Child(ren) | 543483 | 201435 |
| 1668 | Family type | 3 | One Parent With Child(ren) | 213534 | 73689 |
| 1693 | Number of usual residents in household | 1 | One usual resident | 389685 | 95991 |
| 1694 | Number of usual residents in household | 2 | Two usual residents | 570507 | 150981 |
| 1695 | Number of usual residents in household | 3 | Three usual residents | 288159 | 97416 |
| 1696 | Number of usual residents in household | 4 | Four usual residents | 266046 | 95316 |
| 1697 | Number of usual residents in household | 5 | Five usual residents | 118113 | 43149 |
| 1698 | Number of usual residents in household | 6 | Six usual residents | 48381 | 20283 |
| 1699 | Number of usual residents in household | 7 | Seven usual residents | 19737 | 9213 |
| 1700 | Number of usual residents in household | 8 | Eight or more usual residents | 18174 | 9486 |
| 1733 | Tenure of household | 1 | Owned | 978105 | 259299 |
| 1736 | Tenure of household | 2 | Not owned | 604884 | 218220 |
| 1739 | Tenure of household | 3 | In family trust | 197112 | 61839 |

The New Zealand tenure rows total 1,780,101, differing from the independent
1,780,527 household row. This comparison illustrates why Chronicle reads
the published totals directly and never reconciles them. No sum is emitted
as a fact. The national files are not reconstructed from regional files,
and the `Area Outside Region` values are not assigned to another region.

## Reference period, geography and flags

All selected rows say `period = 2023` and `duration = Census`. Coverage
records 7 March 2023, the census-night date given by the hub's instruction;
the exact day is not printed in these CSV files. Boundary vintage is also
absent from the staged files and is recorded as unstated. The existing
`db/data/stats_nz/regional_council_2025_codes/regional-council-2025-codes.json`
register independently verifies regional codes, including `99`, without
assigning the register's boundary year to this product. Auckland's
`geography_name` is normalized to `Auckland` to match the population package's
name convention; the exact CSV descriptor `Auckland Region` remains guarded
and preserved in its full source row. Layout value labels retain the published
categories rather than geographic descriptors.

No staged file supplies a rounding-method note. Chronicle therefore makes
no random-rounding claim for this ingestion. All 288 selected rows have
empty `confidentiality_indicator`, `confidentiality_label`, `final_indicator`
and `final_label`; those blanks do not assert a final revision status. These
fields are kept in source-row lineage, with guards that reject a confidential
or unavailable numeric row through `selected_rows` criteria requiring empty
status fields. Other sections contain unavailable rows marked
`..` / `not available`; they remain full source rows, not numbers inferred
from blanks.

The CSV is preserved in full and its complete row set is parsed. Selected
cells alone are sufficient for the 16 facts per place; all other columns and
unselected rows retain their original bytes. Percentages, 2013 and 2018 rows,
Māori-ethnic-group sections and other sections are preserved but not emitted.
This product supplies household size and the three tenure categories, with
no household-composition or social-renting split. Those missing dimensions
remain missing; no `not stated` category, share, rent, income, rebased 2025
value or consumer target is created.
