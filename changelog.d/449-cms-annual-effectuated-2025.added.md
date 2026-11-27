Add CMS full-year 2025 Marketplace effectuated enrollment (chronicle#449).
`cms-aca-annual-effectuated-enrollment-2025` reads the 2025 state rows of the
CMS data.cms.gov dataset "Health Insurance Exchanges Annual Effectuated
Enrollment" (version 2025-01-01, CSV as of 2026-04-21): average monthly
effectuated enrollment, APTC and CSR enrollment and shares, and average
premiums and APTC for the 50 states and DC, 408 facts for 2025. CMS no longer
updates the Early Snapshot and Full Year Average reports that
`cms-aca-effectuated-enrollment-2022` reads; the CSV holds the same Full Year
tables for 2016 to 2025, with the same definitions. The package declares the
concepts, measures, units, rows and record set of
`cms-aca-effectuated-enrollment-2022` and reads only the 2025 rows, so no
other package gives the same quantity for the same year. The label register
lists the 51 `cms_aca.state` values the two packages now share.
