# MBIE tenancy bond rents by territorial authority

Publisher: Ministry of Business, Innovation and Employment / Tenancy Services.
Licence: CC BY 3.0 NZ, as supplied in the hub's source brief; the CSV itself
does not contain licence text. Attribution accompanies the package.

The immutable staged CSV was fetched on 7 October 2026. Its latest published
month is April 2026. This package pins all published location rows in the
12-month window May 2025–April 2026, rather than selecting a moving latest month
at build time. The file gives no revision status, so “latest” does not assert
that these observations are final. The existing full-row CSV parser preserves
all 26,646 source rows, including the trailing empty row, and selects 810 rows
for 8,921 source cells and 5,670 directly published facts.

The seven emitted measures are lodged, active and closed bond counts, median
rent, geometric mean rent, and upper/lower quartile rent. Counts describe bond
records, not a computed number of households or distinct dwellings; the
schema's `dwelling` entity uses the explicit `rental_bond_record` role.
Rent values remain in NZD per week at scale 1. The file's own “Log Std Dev
Weekly Rent” header supplies its weekly rent context. Quartiles are currency
cut-points with percentile constraints 25 and 75, never shares. The publisher's
geometric mean uses `aggregation: mean` with `concept_relation: approximate`;
it is not an arithmetic mean calculated by Chronicle. Log standard deviation
remains preserved in source rows/cells because the current aggregation
vocabulary cannot faithfully express a standard deviation.

The CSV supplies **no column definitions establishing whether rents describe
newly lodged bonds or active stock**. Both bond populations have separate count
columns; those headers do not identify the population behind the rent columns.
The rent population remains unspecified in every rent measure's evidence
notes. The file also supplies no bedrooms, dwelling types, or arithmetic mean.
Those requested dimensions and measure cannot be emitted from these bytes.
The hub would need to stage the publisher's definitions and the relevant
disaggregated artifact before those items can be added. The source entry point
for those follow-ups is
[Tenancy Services rental bond data](https://www.tenancy.govt.nz/about-tenancy-services/data-and-statistics/rental-bond-data/).

The window contains 66 positive published location IDs, assigned
`local_authority` / `ta_2025` under the NZ checklist ruling. IDs use the
country-prefixed form `nz-ta-001`, preserving the numeric publisher ID in a
labelled constraint. No authoritative `ta_2025` register is staged, so an
independent official ID/name comparison remains open. No Chatham Islands row
appears in this file; that is a source absence, not a reconstructed zero.
Publisher `ALL` is retained as country `NZ`; `NA` remains a separate
`statistical_scope:nz-mbie-location-na`, without allocating it to TAs.

Within the window, Kaikoura has no row in August/October 2025 or March 2026;
Westland has no December 2025 row; Waimate has no January/March 2026 row.
The file does not explain these omissions. Chronicle preserves them without
imputation, suppression assumptions, reconciliation, or a crosswalk.

The manifest records the receipt URL, hash, size and fetch timestamp and a key
computed with Chronicle's `build_r2_key`. Its R2 metadata declares the intended
immutable destination; upload and round-trip verification are pending with
the hub and have not been represented as completed here. Stats NZ household
net worth is outside this staged package.
