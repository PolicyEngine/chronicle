# Stats NZ 2023 Census households by regional council

This package family emits 216 published household counts from Stats NZ's
[Place summaries tool](https://tools.summaries.stats.govt.nz/): 12 counts for
New Zealand, each of the 16 regional councils, and the separately published
`Area Outside Region` (code `99`). It reads the household total, three tenure
categories and eight household-size categories. The companion
[family-type package family](../census_2023_family_type/README.md) emits the
four family counts for each of the same 18 places. Together they emit 288
facts, each taken from one CSV row.

The requested package IDs `stats_nz/census_2023_households_by_region` and
`stats_nz/census_2023_family_type` remain the two family roots. Each root YAML
describes New Zealand, and its `rc_XX/source_package.yaml` children describe
one regional-council entry each. Chronicle's `SourceArtifactSpec` selects one
manifest per declarative package, so these 36 package members preserve the
per-place artifact boundary without changing the package harness. Both
families reference the same 18 files and per-place manifests in
`db/data/stats_nz/census_2023_place_summaries/`; the bytes are committed once.
CSV source cells use Chronicle's virtual sheet names
`place_summaries_<place>_households` and `place_summaries_<place>_families`.
These are not publisher worksheets. The distinct names prevent cell-key
collisions between the two families' different compact selected-row orders.

## Scope and source semantics

The selections require `period = 2023`, `duration = Census`, and
`value_type_description = Count` in these sections:

| Section | Published categories | Facts per place |
| --- | --- | ---: |
| Number of families and households | Households | 1 |
| Tenure of household | Owned; Not owned; In family trust | 3 |
| Number of usual residents in household | One usual resident through Eight or more usual residents | 8 |

The product publishes household size, measured by usual residents. It does
not publish the requested household-composition breakdown or a social-renting
split. `Not owned` remains exactly that publisher category; no social-renting
count is inferred. The complete CSV files retain percentages, 2013 and 2018
rows, Māori-ethnic-group sections and all other sections, which emit no facts
in these package families. No rent or income section is admitted.

New Zealand is read from its own national file. Its `Households` row is
1,780,527; its three tenure rows are 978,105, 604,884 and 197,112, which total
1,780,101. These independent published values are retained without
reconciliation. Neither national totals nor household totals are constructed
by summing regions, tenure categories or size categories.

The reference period is the 2023 Census. Coverage records census night,
7 March 2023, as directed by the hub; the staged CSVs themselves state only
`2023` and `Census`. Their regional-council boundary vintage is not stated.
The regional codes follow the population package's `region` convention,
including the separate `region:99` geography for `Area Outside Region`.
An independently pinned REGC 2025 register confirms that code/name pairing;
it does not establish a 2025 boundary vintage for these census facts.

The staged CSVs contain no rounding-method note, so this ingestion makes no
claim about random rounding. Every selected row has empty
`confidentiality_indicator`, `confidentiality_label`, `final_indicator` and
`final_label` fields. The complete fields remain source-row lineage, and
the `selected_rows` criteria require empty status fields, refusing a flagged
confidential or unavailable row even when its value field contains numeric
text. Category labels retain the publisher's spelling and capitalisation.
Auckland's `geography_name` is "Auckland", following the population package's
name convention; its guarded source-row descriptor retains the CSV's
"Auckland Region". Layout value labels describe the published categories.

See the shared [publisher evidence](evidence.md) for exact rows, checked cells,
receipt metadata and remaining publication steps. All values remain the
publisher's counts, with scale 1 and census provenance. No aging, imputation,
shares, reconciliation or consumer target bindings are constructed.

## Bounded validation

The targeted regression file is
`tests/test_chronicle_nz_census_households.py`. It independently lists
the expected places, categories and row identities and tests package mutants
for percentage, historical-year, wrong-region and Māori-section substitutions.
The test file runs `validate-package` for all 36 members and the source
`build-suite` for the two national roots; CI's bundle job builds every
member's suite.
Raw R2 keys come from Chronicle's key builder. The hub published the 18
objects with `chronicle publish-raw` and verified each by streaming it back
(SHA-256 matches) on 2026-10-10.
The required source-fidelity and boundary judge reviews remain merge gates.
