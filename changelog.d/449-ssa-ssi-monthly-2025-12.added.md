Add `ssa-ssi-monthly-statistics-2025-12`, the December 2025 edition of the SSA
SSI Monthly Statistics Table 1 package (chronicle#449). It reads the "Total
with— Federal payment" row by age group, four facts for December 2025: all
ages 7,264,734, under 18 1,015,006, 18 to 64 3,820,243 and 65 or older
2,429,485. As `ssa-ssi-monthly-statistics-2024-12` does, it reads a CSV
extracted from the published HTML page, and the verbatim page capture sits
beside the CSV. ssa.gov refuses automated downloads, so the maintainer saved
the page from a browser on 2026-11-27. The December 2025 table keeps the rows,
columns and footnotes of the December 2024 table. The package declares its
predecessor's measures, concepts, units, labels, rows, filters, constraints
and record set spec. The label register lists the four age values the two
editions now share (`all_ages`, `under_18`, `age_18_to_64`,
`age_65_or_older`), each with its one wording.
