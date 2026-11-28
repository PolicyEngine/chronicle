Add `jct-tax-expenditures-2025`, the edition after `jct-tax-expenditures-2024`
(chronicle#449): 13 fiscal year 2025 individual income tax revenue-loss
estimates from Table 1 of JCX-45-25, "Estimates of Federal Tax Expenditures for
Fiscal Years 2025-2029" (December 3, 2025), typed `fiscal_year` 2025. It
declares its predecessor's concept, measure, unit, labels, filters and
constraints for the ten lines the two share. JCT prints the charitable
deduction on three lines (education, health, and other than education and
health); the new package reads each line as its own row
(`charitable_deduction_education`, `charitable_deduction_health`,
`charitable_deduction_other_than_education_and_health`) and stores no sum,
while the 2024 package's `charitable_deduction` row is the sum of the three. A
consumer that wants the total adds the three facts. JCX-45-25 reflects
legislation enacted by August 31, 2025 (Table 1, footnote 1), so levels move
from the 2024 edition: the state and local tax deduction goes from USD 21.7
billion (FY2024) to USD 49.1 billion (FY2025). The publisher PDF is registered
raw-only, and a test checks each value of the CSV extract against the PDF's
text. Like its predecessor, the package has no artifact for 2023, so the
default bundle at 2023 skips it. The register gains the ten shared values'
labels.
