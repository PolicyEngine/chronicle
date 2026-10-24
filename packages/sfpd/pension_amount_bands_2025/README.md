# FPD/SFPD monthly amount-band distributions, January 2025

This package preserves the published numeric cells in sections 1.2, 6.2 and 9
of the Federale Pensioendienst (FPD/SFPD), *Jaarlijkse statistiek van de
uitkeringsgerechtigden 2025*. It preserves printed totals as observations and
does not create missing totals, zero-fill blank cells, rescale amounts or
reconcile overlapping populations.

The publisher artifact is `nl_statistiek_2025.pdf` (244 PDF pages,
5,546,459 bytes), SHA-256
`198baf61f9277755059367c811664a71917aab6fe5d2b7e2c7e2c96e9baa8c64`.
The source URL is
<https://www.sfpd.fgov.be/media/Stat/Jaarlijks/nl_statistiek_2025.pdf>, linked
from the publisher's employee statistics page:
<https://www.sfpd.fgov.be/nl/kenniscentrum/statistieken/statistieken-werknemers>.
Retrieval date: 2026-10-23. The document's title page identifies the situation
in January 2025; its dated publication note is 19 November 2025 (PDF page 3).
All page numbers below distinguish physical PDF pages from printed pages.

## Reference period and measured amounts

The reference date is **1 January 2025**, using the January 2025 payment
database. This is a stock of beneficiaries and the associated monthly amounts,
not an annual flow or a sum of twelve months. The chapter introductions make
the date explicit on PDF pages 25, 225 and 239 (printed pages 15, 215 and 229).

In the package, each recipient count has period coverage 1 January 2025 to
1 January 2025, the stock date. Each monthly-expenditure cell has coverage
1–31 January 2025, the month whose gross monthly amounts it reports. Coverage
is declared per record set, so each table group becomes one record set per
metric. The two sets share the group's spec ID and source-record-ID prefix, so
fact keys and source-record IDs match a combined set. Both keep the compact
period `month:2025-01`.

The introduction on PDF page 14 (printed page 4) defines all reported amounts
as **monthly gross amounts**. Actual cash payments may be reduced by income
tax withholding, health insurance contributions, solidarity contributions or
recoveries. The package records expenditure in EUR exactly as printed.
Presentation normalization of Dutch thousands separators and decimal commas
does not change the amount or its scale.

The introduction's observation limits on PDF page 13 (printed page 3) also
apply: newly entitled people whose first payment is delayed can be absent,
people temporarily outside the regular payment cycle can be absent, and recent
deaths can remain until the database is updated. These are payment-database
statistics rather than a complete entitlement register.

## Scheme and population boundaries

The website's employee statistics label does not make the entire document an
employee-only publication. PDF page 11 (printed page 1) identifies the database
as the employee **and self-employed** part of FPD, formerly RVP (*ex-RVP*).
Civil-servant-only statistics are published separately.

Section 1.2 covers recipients of employee and/or self-employed retirement,
survivor or transitional pension benefits. A recipient may also receive a
civil-servant pension, which determines the published career combination, but
**the civil-servant pension amount is excluded**. This distinction is explicit
on PDF pages 15, 19 and 25 (printed pages 5, 9 and 15). Pure civil-servant
careers are excluded. Unconditional self-employed pensions are excluded from
the first chapter's pension-recipient distributions (PDF page 25).
The first chapter limits amounts to its named retirement, survivor and
transitional benefits when recipients also receive other internal benefits
(PDF page 19). Its bands therefore do not describe total income including
IGO, annuities, heating allowances or other benefits paid to the same people.

The nine career tables are overlapping publisher selections, not components
to add together. In particular, "pure or mixed employee career" selects
recipients with employee pension rights, while the amounts include the
employee and self-employed portions of their pensions. The selection must not
be interpreted as expenditure on the employee scheme alone. The analogous
qualification applies to "pure or mixed self-employed career".

Section 6.2 covers **Inkomensgarantie voor ouderen (IGO)**, the means-tested
income guarantee for older people. It includes IGO recipients whether or not
they also receive a pension or another benefit (PDF page 225, printed page
215). Its amount bands and expenditure concern IGO, not the total pension
income of those recipients. Its eligibility categories are the basic amount,
increased basic amount, and unallocated cases, plus the printed total.

Section 9 covers **all ex-RVP FPD benefit recipients**, a broader population
than section 1.2. PDF page 239 (printed page 229) lists pension benefits,
IGO/guaranteed income, employee annuities, unconditional self-employed
pensions, disability allowances and transitional benefits. Civil-servant
pension rights can be recognized, but their paid amount is excluded. Despite
the title's reference to monthly expenditure in EUR, the numeric data cells
in these tables are **recipient counts only**; euro amounts label the bands.

These are unfiltered publisher totals, not a selection of Belgian residents.
Section 2 separately distinguishes beneficiaries residing in Belgium,
payments in Belgium and payments abroad (PDF page 105, printed page 95). For
example, its Belgium-resident pension-recipient subset is 2,217,045, while
section 1.2's all-career total is 2,449,233. A Belgian geography identifier
therefore describes the administering national benefit system here; it must
not be read as an assertion that every recipient resides in Belgium. The
package applies no residence filter that the selected tables do not print.

The unit is the publisher's *gerechtigde* (beneficiary), rather than a pension
award, employment spell or generic household. PDF page 14 says that a person
(or couple) with multiple benefits is counted once in the relevant
distribution and that amounts correspond to the included benefits. The
household-rate retirement category remains a beneficiary count; consumers
must not reinterpret it as a count of all people in recipient households.

## Selected tables and exact bands

| Section | Physical PDF pages | Printed pages | Dimensions and measures |
| --- | --- | --- | --- |
| 1.2.1, all careers | 58–60 | 48–50 | Three sex panels; six categories; count and monthly gross pension expenditure |
| 1.2.2, pure/mixed employee | 62–64 | 52–54 | Same |
| 1.2.3, pure/mixed self-employed | 65–67 | 55–57 | Same |
| 1.2.4, pure employee | 68–70 | 58–60 | Same |
| 1.2.5, employee + self-employed | 71–73 | 61–63 | Same |
| 1.2.6, employee + civil servant | 74–76 | 64–66 | Same |
| 1.2.7, employee + self-employed + civil servant | 77–79 | 67–69 | Same |
| 1.2.8, pure self-employed | 80–82 | 70–72 | Same |
| 1.2.9, self-employed + civil servant | 83–85 | 73–75 | Same |
| 6.2, IGO | 227–229 | 217–219 | Three sex panels; four eligibility categories; count and monthly gross IGO expenditure |
| 9, all FPD/ex-RVP benefits | 240–242 | 230–232 | Three sex panels; age group × monthly amount band; counts only |

Every three-page group orders sex as men and women, men, then women. PDF page
61 (printed page 51) is a chart, not another numeric table. The section 1.2
introduction is PDF page 57 (printed page 47).

Each section 1.2 table contains 26 bands plus the printed total. The first
band is `0,01 - 124,99`; subsequent bands have printed 125-EUR lower-bound
steps; the last closed band is `3.000,00 - 3.124,99`; the open upper band is
`3.125,00 en >`. The six categories are total; married retirement at household
rate; married retirement at single rate; unmarried retirement at single rate;
unmarried retirement plus survivor pension; and unmarried survivor pension or
transitional benefit. Visual inspection confirms that the lower table's
"Niet gehuwd" heading spans all three lower categories.

Section 6.2 contains 61 bands plus the printed total. Its first band is
`0,01 tot 24,99`, the last closed band is `1.475,00 tot 1.499,99`, and the
open upper band is `1.500,00 en meer`. **All three sex pages print
`1.225,00 tot 1.449,99` between the 1,200–1,224.99 and 1,250–1,274.99 rows.**
This is an apparent publisher boundary typo, but the package preserves the
printed label and boundaries rather than silently changing the upper bound
to 1,249.99. Consumers must handle the resulting overlap explicitly.

Section 9 contains 17 amount bands: `minder dan 125,00`, closed 125-EUR bands
from `125,00 tot 249,99` through `1.875,00 tot 1.999,99`, and `2.000 en meer`.
Unlike section 1.2, the first band does not print a 0.01-EUR lower bound. The
18 printed age labels are younger than 20, five-year groups from 20–24 through
95–99, and 100 and older. The younger-than-20 rows are blank. The first of
three horizontal panels also prints total recipients by age; all panels
print totals across ages. Blank cells remain absent observations.

## Extraction and independent checks

The PDF has permission-only owner-password encryption; pypdf with
`cryptography` reads it without a password. Plain pypdf `extract_text()`
scrambles the table order, and its `extraction_mode="layout"` omits embedded
table text. These failures affect all three selected sections. The generator
therefore reads the embedded form content streams and their positioned text
operators, reconstructing cells deterministically with exact page, table,
row and column locators. It does not depend on OCR or Poppler at runtime.

An independent audit used Poppler `pdftotext -bbox` and Decimal arithmetic,
with columns inferred from each panel's printed total row. It counted:

| Section | Published numeric cells | Printed column-total checks | Result |
| --- | ---: | ---: | --- |
| 1.2 | 7,980 | 324 | Exact matches, including expenditure cents |
| 6.2 | 1,354 | 24 | Exact matches, including expenditure cents |
| 9 | 905 | 54 | Exact matches |
| All selected sections | 10,239 | 402 | No mismatches |

These counts include the publisher's printed totals and exclude blanks.
Validation sums are checks only; they are not stored as new facts.
The audit also compared every CSV value and its physical PDF page, panel,
printed row and column to the independently reconstructed Poppler cells:
10,239 source cells versus 10,239 CSV cells, with no missing, extra or
different values.

PDF page 66 (printed page 56, section 1.2.3, men) has an additional
publisher layout anomaly in the unmarried survivor/transitional category:
the 2,875–2,999.99 row prints EUR 2,879.23 with no count, while the
3,000–3,124.99 row prints count 1 with no expenditure. Both Poppler extraction
and visual inspection of the rendered page confirm the displacement. Each
numeric cell remains attached to its printed row, and its blank partner is
not filled or moved. Both column totals still reconcile exactly, so a column
total check alone would not detect this anomaly.

For example, PDF page 58 prints 281,092 all-career recipients and EUR
13,150,977.27 in the 0.01–124.99 band; its open 3,125-and-over band prints
30,814 and EUR 104,516,662.46. PDF page 227 prints 118,262 IGO recipients and
EUR 85,039,735.46 in its total row. PDF page 240 prints 700,624 recipients
across all ages in the 2,000-and-over band.

The source has different printed overall totals in different places: its
introductory payment file contains 2,489,520 recipients (PDF page 15), whereas
section 9 explicitly states and prints 2,489,512 (PDF pages 239–240). Section
1.2 separately prints 2,449,233 pension recipients. The package retains each
selected table's published population and total; it does not reconcile the
eight-person discrepancy with the introduction.

## Reproduction

From the repository root, with the project's dependencies installed:

```sh
python packages/sfpd/pension_amount_bands_2025/build_package.py
chronicle validate-package sfpd-pension-amount-bands-2025 --year 2025
chronicle build-suite sfpd-pension-amount-bands-2025 --year 2025 --out /tmp/sfpd-amount-bands --replace
```

The generator verifies the raw PDF checksum before writing the normalized CSV,
manifest and package YAML. It never downloads or uploads artifacts. Every CSV
value has its original numeric lexeme, physical and printed page, table, panel,
row, column, Form name and local text coordinates. The focused fidelity tests
independently read the PDF's literal text operators rather than reusing the
generator's parser.
