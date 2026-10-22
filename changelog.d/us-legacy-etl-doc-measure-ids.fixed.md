Check every measure id, row id and IRS column code the US legacy ETL cleanup
doc names next to a replacement package against that package's declarations,
and fix the two the check found: the congressional district file's line 8a
measures are `mortgage_interest_paid_*` since chronicle#345, and `ssi_payments`
is a row of the SSA supplement's `payment_amount`, not a measure of the SSI
Table 7.B1 or monthly statistics packages.
