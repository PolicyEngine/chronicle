`hhs-acf-tanf-caseload-2024` now reads ACF's "FY2024 15 Months TANF Caseload"
workbook (`fy2024-15months-tanf-caseload.xlsx`, sheets dated 2025-06-10) in
place of the fiscal year 2024 workbook dated 2025-01-30, which ACF took off its
page (chronicle#449). The package keeps its id, record sets, rows, row labels
and measures, and still reads the fiscal year 2024 averages (October 2023 to
September 2024); the new workbook also holds calendar year 2024 averages, which
the package does not read. ACF revised fiscal year 2024 between the two
workbooks, so 13 of the package's 58 facts change value: the seven national
averages and the total families of Colorado, Maryland, North Carolina, Rhode
Island, Tennessee and Vermont. The national average monthly families go from
841,208.67 to 839,119.17 and the recipients from 2,060,968.25 to 2,054,214.75;
Maryland's families go from 12,918.5 to 10,308.17. The facts keep their record
ids, record set spec ids and semantic keys. On all 58 facts these change with
the file: the aggregate, legacy and release keys; the fact label, which names
the file; the record set spec hash and the source cell keys, because the cells
moved; and the source fields (file name, sha256, size, R2 key, extraction date
and URL, which is now the workbook's own address). Rhode Island's total
families go from a whole number (3,391) to 3,447.5, so that fact's value type
goes from integer to number. The earlier workbook stays in R2 and is registered
raw-only.
