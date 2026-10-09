# MBIE tenancy bond rents by territorial authority

Publisher: Ministry of Business, Innovation and Employment / Tenancy Services.
Licence: CC BY 3.0 NZ, as supplied in the hub's source brief; the CSV itself
does not contain licence text. Attribution accompanies the package.

This package pins `detailed-monthly-tla-tenancy-september.csv`, the file MBIE
published on 9 September 2026 (server Last-Modified 9 September 2026 23:18 GMT,
10 September in New Zealand; the landing page says the data were last updated
10 September 2026). The hub fetched it on 8 October 2026. It covers February
1993 to July 2026 and replaces the 23 June 2026 file
`detailed-monthly-tla-tenancy-v2.csv` (data to April 2026) that this package
first pinned; MBIE's landing page now links only the September file.

MBIE describes the rental bond data as provisional and subject to revision:
its landing page says that, while bond data migrate to a new bond management
system, the data may be incomplete or revised, and that users should always
use the latest file. The values here are the September file's as published; a
later MBIE file may revise them. Comparing the overlapping August 2025–April
2026 rows, 1,511 of 4,242 measure cells differ between the June and September
files.

The package pins all published location rows in the latest 12 months of the
file, August 2025–July 2026, rather than selecting a moving latest month at
build time. The file is UTF-8 with a byte-order mark, unquoted headers without
spaces (`TimeFrame`, `location_id`, `location`, `LodgedBonds`, ...), months
written `d/mm/yyyy` (`1/07/2026`), the newest month first, no thousands
separators and CRLF line endings. The existing full-row CSV parser decodes it
as `utf-8-sig`, so the BOM does not reach the first header, and keeps
`TimeFrame` as the publisher's text. It preserves all 26,850 source rows and
selects 809 rows by `TimeFrame` and `location_id`, for 8,910 source cells and
5,663 directly published facts. Facts keep the dimension names `Time Frame`
and `Location Id`; Chronicle's row-semantics check matches them to the
publisher's `TimeFrame` and `location_id` columns by normalised name. The
`Time Frame` value is the publisher's month text, and each fact's period is
the calendar month with explicit start and end dates.

The seven emitted measures are lodged, active and closed bond counts, median
rent, geometric mean rent, and upper/lower quartile rent. Counts describe bond
records, not a computed number of households or distinct dwellings; the
schema's `dwelling` entity uses the explicit `rental_bond_record` role.
Rent values remain in NZD per week at scale 1. The file's own
`LogStdDevWeeklyRent` header supplies its weekly rent context. Quartiles are
currency cut-points with percentile constraints 25 and 75, never shares. The
publisher's geometric mean uses `aggregation: mean` with
`concept_relation: approximate`; it is not an arithmetic mean calculated by
Chronicle. Log standard deviation remains preserved in source rows/cells
because the current aggregation vocabulary cannot faithfully express a
standard deviation.

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

Method notes from that landing page: MBIE applies fixed random rounding to
base 3 and suppresses results when there are fewer than 5 bonds for any given
selection. All 2,427 bond-count cells in the pinned window are multiples of 3.
Chronicle keeps the published, rounded values and does not reconcile the ALL
row with the sum of the location rows.

The window contains 66 positive published location IDs, assigned
`local_authority` / `ta_2025` under the NZ checklist ruling. IDs use the
country-prefixed form `nz-ta-001`, preserving the numeric publisher ID in a
labelled constraint. No authoritative `ta_2025` register is staged, so an
independent official ID/name comparison remains a follow-up. No Chatham
Islands row appears in this file; that is a source absence, not a
reconstructed zero. Publisher `ALL` is retained as country `NZ`; `NA` remains
a separate `statistical_scope:nz-mbie-location-na`, without allocating it to
TAs.

Within the window, Kaikoura has no row in August/October 2025 or March/June
2026; Westland has no December 2025 row; Waimate has no January/March 2026 row.
The file does not explain these omissions. The landing page's suppression rule
may account for them, but the file does not say so, and Chronicle preserves
them without imputation, suppression assumptions, reconciliation, or a
crosswalk.

The manifest records the receipt URL, hash, size and fetch timestamp and a key
computed with Chronicle's `build_r2_key`. The hub publishes the September CSV
to that immutable `raw/nz/mbie/...` key and verifies the object by SHA-256
before merge. Stats NZ household net worth is outside this staged package.
