Check every measure id, row id and IRS column code the US legacy ETL cleanup
doc names next to a replacement package against that package's declarations.
Fix the SSI row the check flags: the SSA supplement declares `ssi_payments` as
a row, with `payment_amount` as its measure, and neither the Table 7.B1 package
nor the monthly statistics package declares it. The check reads the doc's
tables with markdown-it-py, a new dev dependency.
