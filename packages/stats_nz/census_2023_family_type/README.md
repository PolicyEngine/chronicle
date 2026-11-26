# Stats NZ 2023 Census families by regional council

This package family emits 72 published family counts: four counts for
New Zealand, each of the 16 regional councils, and `Area Outside Region`
(publisher code `99`). Every fact reads one row from the place's unchanged
Stats NZ Place summaries CSV.

| Section | Published categories | Facts per place |
| --- | --- | ---: |
| Number of families and households | Families | 1 |
| Family type | Couple Without Children; Couple With Child(ren); One Parent With Child(ren) | 3 |

All selections are 2023 `Count` rows with `duration = Census`. The New Zealand
family total is 1,294,503; the three separately published family-type counts
are 537,486, 543,483 and 213,534. These values remain independent publisher
rows. National values read the national file rather than a sum of regions.
Labels, including `Couple Without Children`, retain their exact published
capitalisation.

The national root and its 17 `rc_XX` members share the 18 source files with
the [household package family](../census_2023_households_by_region/README.md),
which explains the per-place package layout, source exclusions, census-night
reference date, unstated boundary vintage, absent rounding-method evidence,
and the household-composition and social-renting gaps. No shared artifact
bytes are committed twice. `Area Outside Region` remains its own geography
and is never folded into a council.

The complete source files preserve percentage and historical rows,
Māori-ethnic-group sections and unrelated sections without emitting them.
Confidentiality and final-status fields remain lineage; a confidential or
unavailable row cannot become a numeric fact. No reconciliation, inferred
categories, period alignment, imputation or target construction is performed.

See the shared [publisher evidence](../census_2023_households_by_region/evidence.md).
The licence is `CC BY 4.0`, with attribution to Stats NZ. The hub published the
18 raw files to R2 and verified each by SHA-256 on 2026-10-10.
