Add three IRS SOI packages for tax year 2023, the next editions of their
TY2022 twins (chronicle#449, chronicle#117): `soi-state-2023`, the four US
totals of the state-data file `23in54us.xlsx` (returns, AGI, and returns and
amount of the EITC with three or more qualifying children), and
`soi-ira-traditional-contributions-2023` and `soi-ira-roth-contributions-2023`,
the all-taxpayers row of IRA Tables 5 and 6 (`23in05ira.xlsx`,
`23in06ira.xlsx`). The xlsx cell reader no longer lets the placeholders of a
merged range that runs to the worksheet edge widen a sheet's used range:
`23in54us.xlsx` merges its footnote row across the whole sheet (`A179:XFD179`),
which made openpyxl report 16,384 columns. No other committed workbook, and
no R2-only workbook the default bundle reads, has such a range.
