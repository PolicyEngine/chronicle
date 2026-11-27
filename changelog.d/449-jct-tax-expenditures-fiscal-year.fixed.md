Type `jct-tax-expenditures-2024` as fiscal year 2024 (chronicle#121 item 4).
The package reads the 2024 column of JCX-48-24 Table 1, "Estimates of Federal
Tax Expenditures for Fiscal Years 2024-2028", but typed it as calendar year
2024. Its eleven facts now carry period `fiscal_year:2024`, and the record set
id and source record id prefix change from `jct.tax_expenditures.cy2024` to
`jct.tax_expenditures.fy2024` (for example
`jct.tax_expenditures.fy2024.salt_deduction.revenue_loss`). The values, record
set spec, rows, concepts and measures do not change. Consumers that pin the
old ids or period (Microcosm's US fiscal target references and Chronicle feed
scope) update them. The default bundle at 2023 still skips the package.
