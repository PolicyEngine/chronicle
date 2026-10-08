# June 2026 supplementary assistance evidence

The staged publisher workbook is
`quarterly-benefit-fact-sheets-w-i-supplementary-tables-june-2026.xlsx`.
Every worksheet is parsed; facts select the `Jun-26` column W, rows 7–9,
on each of its 12 region sheets.

Verbatim evidence in `Contents and notes`:

- B31: “• Supplementary and hardship assistance data are all ages.”
- B34: “• People may be receiving more than one type of Supplementary Assistance.”
- C24: “Work and Income has 11 geographical regions: Northland; Auckland;
  Waikato; Bay of Plenty; East Coast; Taranaki (King Country, Whanganui and
  Taranaki); Central; Wellington; Nelson (Marlborough, West Coast and Nelson);
  Canterbury; and Southern.  "Other regions" refers to offices managed by
  national units, for example, contact centres and processing centres and
  unspecified regions.”
- C21: “All information in this data file has been randomly rounded to base 3,
  data found here is rounded independently from other products produced by MSD.”
  (First sentence.)

The published row labels on every region sheet are “Special Benefit (SPB) or
Temporary Additional Support (TAS)”, “Disability Allowance (DA)”, and
“Accommodation Supplement (AS)”. The first is a combined payment category;
these bytes do not support a TAS-only count.

The workbook publishes assistance type by quarter for each region. Inspection
of all 13 worksheets found no AS recipient cut by main-benefit, NZS or
non-beneficiary status. It also has no national row. The separate national
workbook's `Supplementary - last 5 years!W7` publishes AS recipients as
363,309; that cell is emitted by `benefit_fact_sheets_national_june_2026`.
Regional counts are never summed into a national fact. The NZS/VP workbook
separately publishes AS counts within its pension-recipient universes; those
are not regional status cuts.
