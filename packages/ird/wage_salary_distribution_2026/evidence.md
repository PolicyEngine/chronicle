# Publisher evidence: IRD wage and salary distributions, 2026 release

This package represents the publisher's latest March tax year, 2026: 1 April
2025 to 31 March 2026. It retains the complete downloaded workbook unchanged.
It selects only the 2026 published band, decile and top-percentile cells; the
historical and revised columns remain source bytes and preserved source cells.

## Artifact and receipt

- Publisher: Inland Revenue Department (IRD), New Zealand.
- [Dataset page](https://www.ird.govt.nz/about-us/tax-statistics/revenue-refunds/wage-salary-distributions/wage-and-salary-statistics-datasets).
- [Stable workbook URL](https://www.ird.govt.nz/-/media/project/ir/home/documents/about-us/tax-statistics---current/revenue-and-refunds/wage-and-salary/wage-and-salary-statistics/wage-and-salary-distributions-for-individuals.xlsx).
- Receipt: HTTP 200; fetched at `2026-10-10T08:31:07Z`; 198,542 bytes;
  SHA-256 `d0526b2092f9fa2bec44e11984c0ef17fda788a742c1c7054d416f6a0cd9e750`.
- The receipt's source and final URLs are the same stable workbook URL. The hub
  reports that the dataset-page link adds `?modified=20260825224541`, matching
  the HTTP Last-Modified value `Tue, 25 Aug 2026 22:45:41 GMT`. These HTTP header
  and page-link observations were supplied by the hub, rather than re-fetched
  by this offline lane.
- Licence: `CC BY 4.0`, based on the hub's 2026-10-10 verification of
  [IRD's Crown copyright conditions](https://www.ird.govt.nz/about-this-site/conditions-of-use/copyright).
- The manifest's R2 storage key is built with Chronicle's `build_r2_key`.
  The hub published the object with `chronicle publish-raw` and verified it
  by streaming it back (SHA-256 matches) on 2026-10-10.

The heading in `xl/drawings/drawing1.xml` is “Wage and salary distributions for
individuals ”, with a trailing space. The workbook's extraction note states
17 August 2026. No workbook title containing “Aug 2026” was found in its XML
text or document properties.

## Publisher definitions and population

The explanatory notes are drawing text, rather than worksheet cell values.
The following paragraphs are transcribed from `xl/drawings/drawing1.xml`,
joining text runs within each paragraph:

> Wage and salary income includes any gross earnings received from any employer where pay as you earn (PAYE) was deducted or the income was otherwise reported by employers through the PAYE system, e.g. salary and wages, income received in the form of shares and share options and Paid Parental Leave. Not included in these statistics are:

> - New Zealand Superannuation
> - Taxable welfare benefits
> - Student allowances
> - Earnings-related ACC payments, and
> - Shareholder-employee salaries (since there was no PAYE deducted).

> All data is published on a March year basis.

> The tables and graphs include individuals with part-time or part-year PAYE incomes and also include children with PAYE earnings. Individuals who did not receive any wage or salary income (as defined above) are not included in the tables and graphs. Entities other than natural persons are also excluded.

> The data up to the 2015 March year was based on a random sample of individuals scaled up to population estimates. The sample was 2% of wage and salary earners, and 10% of IR3 filers (with wages or salaries).

> From the 2016 March year onwards the data is based on data from the full population.

> Tabulated data on wage and salary distributions of individuals from the 2006 to 2026 March years is included in the accompanying tables and graphs.

> Data was extracted from Inland Revenue systems on 17 August 2026. Data for the 2022 to 2025 tax years has been revised, and there may be some differences to numbers previously published.

The selected 2026 facts use administrative provenance and refer to individuals
with wage or salary income under this publisher definition. They do not merge
with the separate IRD taxable-income distribution package.

## Workbook layout and revision metadata

`Tables - wage and salary!A1` states
`individuals with wage or salary income:  Year ended 31 March`. Row 3 gives
ending years. The band panels are A–Q (2001–2008), R–AL (2009–2018) and AM–BC
(2019–2026); their row-4 labels are respectively `bands to $150,000`,
`bands to $200,000` and `bands to $300,000`.

The 2026 band columns are BB for `Number of individuals` and BC for
`Wage/salary income ($M)`, with `BB3 = 2026` and `BC2 = New`. Row 2 contains
the verbatim revision markers `AW2 = R`, `AY2 = R`, `BA2 = R`, and `BC2 = New`.
The paired year cells are `AV3 = 2023`, `AX3 = 2024`, `AZ3 = 2025`, and
`BB3 = 2026`. These markers and the drawing sentence naming “2022 to 2025”
are retained as separate publisher assertions, without reconciliation. No
2023–2025 revised-column facts are constructed.

Chronicle's XLSX parser uses non-read-only openpyxl workbooks and retains every
used-range cell of each selected sheet, including blanks. That code path
materializes these worksheet ranges: Explanatory Notes 28×17, Graphs - wage
and salary 1×1, Tables - wage and salary 282×57, and Graph data 204×20, or
20,631 cells across the complete workbook. The sheet XML's stale declared
dimension `A1:BE1261` is not the non-read-only parser's materialized range.

## Selected publisher cells

The band selection is every row 7–242 inclusive: 235 published band rows and
the separately published `Total` row. Each count and amount reads its own
single cached cell. `Total` remains a separate publisher fact, without summing
the preceding rows.

| Cell | Publisher label or meaning | Cached value |
| --- | --- | --- |
| AM7 / BB7 | `$1      -   $1,000` / individuals | 81400 |
| AM241 / BB241 | `Over $1 million` / individuals | 980 |
| AM242 / BB242 | `Total` / individuals | 2840300 |
| BC242 | Total wage/salary income, $M | 199691.51608914993 |
| AM255 / BB255 | Decile 1 / wage/salary at upper boundary, dollars | 1 / 6880.24 |
| BC255 | Decile 1 wage/salary income, $M | 768.2012857799999 |
| AM264 / BB264 | Decile 10 / upper boundary | 10 / blank |
| BC264 | Decile 10 wage/salary income, $M | 57917.73481663 |
| AM278 / BB278 | Percentile 99 / wage/salary at upper boundary, dollars | 99 / 289185.87 |
| AM279 / BB279 | Percentile 100 / upper boundary | 100 / blank |
| BC279 | Percentile 100 wage/salary income, $M | 13137.484879959999 |

The cached values above are those returned by Chronicle's XLSX parser.
The unchanged source XML retains the complete numeric representation,
including `BC255`'s numeric text `768.20128577999992`, which openpyxl reads
as the binary float shown above. Amount facts use the publisher's `$M` value
with scale 1,000,000 to NZD; neither source cells nor amount facts are rounded.
Upper-boundary cells are already dollars and use scale 1.

Decile rows are 255–264, headed by `AM252 = Decile`, `BB251 = 2026`,
`BB252 = Wage/salary at upper boundary ($)` and
`BC252 = Wage/salary income ($M)`. Top-percentile rows are 270–279, headed
by `AM267 = Top 10%`, `BB266 = 2026`, and the same measure labels at BB267
and BC267. Their row labels are the published integers 1–10 and 91–100.

`BB264` and `BB279` are explicitly empty XML cells with no numeric value.
No upper boundary is invented for either decile 10 or percentile 100. Their
published income amounts remain facts. Upper boundaries are cut-points,
not income or population shares, and the open-ended wage band remains its
original categorical label.

The footnotes are preserved verbatim from worksheet cells:

> AM280: * Each decile contains the wage and salary earning population divided by 10

> AM281: ** Each percentile for the top 10% of wage and salary earners contains the wage and salary earning population divided by 100

The selected cells therefore support 472 band facts, 19 decile facts and 19
top-percentile facts, for 510 facts. This count follows the publisher's
nonblank numeric cells and includes no derived means, shares, interval
bounds, revised-year facts, period alignment or reconciliation.
