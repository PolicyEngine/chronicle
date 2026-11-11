# Publisher evidence: 2023 Census weekly rent

This family reads the 18 committed Stats NZ Place summaries CSVs already
used by the [household and family families](../census_2023_households_by_region/evidence.md).
This offline lane verified every file's SHA-256 and byte size against its
unchanged `manifest-<place>.yaml`; each file has 2,030 data rows, 22 columns,
and 2,031 CRLF line endings. No artifact or manifest was changed, copied,
renamed, or fetched. Receipt URLs, timestamps and the publisher's generated
download filenames remain in those manifests.

## Exact selected rows and values

These are physical CSV line numbers, with the header on line 1. All 18
files use these identities. Every selected row has `period = 2023`,
`duration = Census`, and empty `section_type`. Counts have
`variable1_label = Weekly rent paid by household`, the category code below,
and `value_type_description = Count`. All values have six fractional
zeroes and `decimals = 0`; their scale is 1. `value` is column O.

| CSV line | Section | Category code | Exact category / value type | New Zealand | Auckland Region |
| ---: | --- | --- | --- | ---: | ---: |
| 1766 | Weekly rent paid by households | 1 | Under $200 | 89439 | 28113 |
| 1767 | Weekly rent paid by households | 2 | $200 - $299 | 53325 | 9909 |
| 1768 | Weekly rent paid by households | 3 | $300 - $399 | 80247 | 16734 |
| 1769 | Weekly rent paid by households | 4 | $400 - $499 | 101067 | 28827 |
| 1770 | Weekly rent paid by households | 5 | $500 - $599 | 99042 | 42645 |
| 1771 | Weekly rent paid by households | 6 | $600 - $699 | 68544 | 37143 |
| 1772 | Weekly rent paid by households | 7 | $700 - $799 | 32286 | 19629 |
| 1773 | Weekly rent paid by households | 8 | $800 and over | 35712 | 22899 |
| 1763 | Median weekly rent paid by households | Empty | Median; dollars | 450 | 540 |

The median table row has empty `variable1_label`, `variable1_code`,
`variable1_descriptor`, and all three `variable2_*` fields, with
`value_type_description = Median` and `value_label = dollars`. Its
`last_updated_at_source` is `2024-09-02 10:17:01+00`. Physical line 13 is a
separate `Quick stats` occurrence of the same median, updated
`2024-08-14 15:03:09+00`, with equal values in all 18 files. Only the
table occurrence with empty `section_type` is selected, preserving its own
row identity as the existing families do for duplicated quick statistics.
The band rows have update timestamp `2024-09-16 09:50:00+00`.

The package's selected-row order is the eight bands, then the median;
its compact virtual rows are therefore 2 through 10. The virtual sheet is
`place_summaries_<nz|rc_XX>_weekly_rent`. The parser's selected-cell
representation retains each physical `source_line_number` and source-row
key. The sheet suffix distinguishes this family from the household and
family packages without asserting a publisher worksheet.

Exactly nine rows per place become facts: 144 household counts and 18
published medians. No sum of the bands, sum of regions, share, mean,
interpolation, or calculated median is emitted. New Zealand is read from
its own source file. The median uses its own measure with unit
`nzd_per_week` and `aggregation: median`.

## Population, period, geography and status

The rent population definition is **not stated in the product**. No staged
CSV note identifies a universe of rented occupied private dwellings with
stated rent, so this family does not assert that definition. The weekly
basis is in the section titles; the median's currency label is `dollars`.
The hub supplies the New Zealand-dollar basis at the census date and
census night, 7 March 2023. The CSV rows state only `2023` and `Census`,
without the exact day or a separate currency-basis explanation. Regional
boundary vintage and a rounding-method note are unstated.

Geography follows the existing Census families: the separately published
code `99` retains `region:99`, and Auckland's consumer geography name is
`Auckland` while its exact source descriptor is `Auckland Region`.

All 162 selected rows have empty `confidentiality_indicator`,
`confidentiality_label`, `final_indicator`, and `final_label`. These
fields are preserved in full source-row lineage, and selections require
them to be empty, refusing flagged numeric rows. Their blanks do not
assert final revision status. Complete source rows preserve percentages,
2013 and 2018 periods, Māori-ethnic-group sections, unrelated sections,
and the duplicate quick-stat median without emitting those rows.

## Existing published objects

The manifests already pin the following objects in `ledger-raw`. The
shared evidence records the hub's publication and streamed SHA-256
verification on 2026-10-10; this lane verified only the existing local
bytes and manifest metadata. The manifest table title mentions families
and households because the immutable artifacts are shared full-product
exports; the rent package identifies its own emitted source table.

| Place | Existing manifest | Existing R2 object |
| --- | --- | --- |
| New Zealand | [manifest-nz.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-nz.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/6b35e4339ab98bd85dcfa0d297f9bf2c88403327dfe70430513cb7c10b26d89b/place-summaries-nz.csv) |
| Northland | [manifest-rc-01.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-01.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/7eb81d38c4b3837c21d056ac772b91b4397ee4c1b26146a665deb373d847520f/place-summaries-rc-01.csv) |
| Auckland | [manifest-rc-02.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-02.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/8146e6612b8a0434f021b02f096cd0befaa450fdab0f5c09325201586ae001bc/place-summaries-rc-02.csv) |
| Waikato | [manifest-rc-03.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-03.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/d4f378940be75e0a138282bd55368b232e4eacb5ea347184f1b4b7abd2deb694/place-summaries-rc-03.csv) |
| Bay of Plenty | [manifest-rc-04.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-04.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/fc75a24d8538450f98c8a4485a6c7816fb3b5d697ea363ad55b6ca88bcfde739/place-summaries-rc-04.csv) |
| Gisborne | [manifest-rc-05.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-05.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/82f57517ccd7a22f953dc6ea5137d5e8f70248f762674a85bd33e0f8cf34285c/place-summaries-rc-05.csv) |
| Hawke's Bay | [manifest-rc-06.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-06.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/ecd9485974efcc936ebacc452647b2597e6f37cf6386d328c88587fba66dcc46/place-summaries-rc-06.csv) |
| Taranaki | [manifest-rc-07.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-07.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/96ff9f1943d9200a3096b965bc510e1b369016128388ac43a202504d99fa986f/place-summaries-rc-07.csv) |
| Manawatū-Whanganui | [manifest-rc-08.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-08.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/c693e64b4194d507647b5ba35af4675df9fb44af64de40fd1ce399a37af396b5/place-summaries-rc-08.csv) |
| Wellington | [manifest-rc-09.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-09.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/38cc255b43303a31f45cdfbf2ba8c4b9c8e367eaaf50e76c1388d3085cc08900/place-summaries-rc-09.csv) |
| West Coast | [manifest-rc-12.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-12.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/42148ea27b7a7906b963b4ee29552f7826c5149c6ecd62459099f80ecc20e4ae/place-summaries-rc-12.csv) |
| Canterbury | [manifest-rc-13.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-13.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/a4d8c4b9eaff633904419ed95dccc4e1bf5f64fd964020af06a006b269c9e8af/place-summaries-rc-13.csv) |
| Otago | [manifest-rc-14.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-14.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/3491f761dd689c4a2cce52ebe950e9af97ad184e99b589a53bb9b40685c2b1e8/place-summaries-rc-14.csv) |
| Southland | [manifest-rc-15.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-15.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/68fb9522adc00d9d195a8dd77c51d781f69d9a292ac8db3f6e6931064165cc78/place-summaries-rc-15.csv) |
| Tasman | [manifest-rc-16.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-16.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/d06b59112aac85f051665fcdc99d470508c8bfa7223e103bcd79fbd7d3155c1a/place-summaries-rc-16.csv) |
| Nelson | [manifest-rc-17.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-17.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/26a51a71c1ad40df12f04c58a164d029f41d565c32a201424e1edb8cf2e32341/place-summaries-rc-17.csv) |
| Marlborough | [manifest-rc-18.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-18.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/92533df51e133c0c47bf24e0a28f2ee68aecaf737f65ec8d9e5d5bf72f697b44/place-summaries-rc-18.csv) |
| Area Outside Region | [manifest-rc-99.yaml](../../../db/data/stats_nz/census_2023_place_summaries/manifest-rc-99.yaml) | [raw object](r2://ledger-raw/raw/nz/stats_nz/census_2023_place_summaries/2023/6ee21b3170d89e29fb7ea3ee3986c9ff14860e99be1b230e64432a6c024c9369/place-summaries-rc-99.csv) |

Licence is `CC BY 4.0`, with attribution to Stats NZ, as pinned by the
existing manifests and shared publisher evidence. Required source-fidelity
and boundary judge reviews remain merge gates; this note does not record
those reviews as executed.
