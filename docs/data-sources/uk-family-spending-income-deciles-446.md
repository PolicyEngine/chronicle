# UK household spending by income decile: ONS Family Spending, FYE 2025 (chronicle#446)

[chronicle#446](https://github.com/PolicyEngine/chronicle/issues/446) asks for ONS's published
table of household spending by income decile. Microcosm compares the spending it imputes from
the Living Costs and Food Survey (LCFS) with the donor survey by decile
([PolicyEngine/microcosm#1717](https://github.com/PolicyEngine/microcosm/issues/1717)), and
reads this table as that comparison's official reference. Chronicle keeps the preserved
workbook, its cells and the facts; the comparison and any arithmetic stay in Microcosm.

One package adds 487 `survey_aggregate` facts from the LCFS, under the Open Government Licence
v3.0, from one new file.

## Which workbook

ONS publishes Family Spending as two workbooks. The financial year ending (FYE) 2025 edition of
workbook 2 (expenditure by income) prints decile tables only by gross income (Table A4) and by
unequivalised disposable income (Table A7). Its equivalised tables (3.3E and 3.7E) are quintiles
of one-adult and two-adult non-retired households.

The equivalised decile table for all households is workbook 1's Table 3.1E (detailed
expenditure and trends). It prints both equivalisation versions side by side. Workbook 1's
Table A6 gives the same figures by gross income decile. So the package pins workbook 1.

## Package

- `ons-family-spending-workbook1-fye2025`: 487 facts.
  - From ONS's "Family spending workbook 1: detailed expenditure and trends", FYE 2025 edition,
    released 11 June 2026: `workbook1detailedexpenditureandtrends.xlsx`, 558,943 bytes, sha256
    `af8d4a44…1076`.
  - Table 3.1E, both blocks: households ranked by equivalised disposable income, with the
    updated OECD-modified scale (2-adult reference) and with the OECD-modified scale (1-adult
    reference).
  - Table A6: households ranked by gross income.
- `scripts/build_uk_446_packages.py` writes the package from the pinned workbook, read with
  Chronicle's own parser. `--check` compares the result with the committed file.

**Concepts**

| Concept | Unit | Facts |
|---|---|---|
| `ons.family_spending.mean_weekly_household_expenditure` | `gbp_per_week`, mean | 425 |
| `ons.family_spending.weighted_households` | `count` (printed in thousands, `value_scale: 1000`) | 31 |
| `ons.family_spending.households_in_sample` | `count` | 31 |

**Dimensions**

- `expenditure_group`: `coicop_01` to `coicop_12` (the COICOP divisions as ONS numbers them,
  under its labels, such as "Food & non-alcoholic drinks"), `coicop_01_to_12` ("All expenditure
  groups"), `other_expenditure_items` (category 13) and `total_expenditure`.
- `income_decile_group`: `decile_1` ("Lowest ten per cent") to `decile_10` ("Highest ten per
  cent").
- `income_decile_basis`: `equivalised_disposable_income` (Table 3.1E) or `gross_income` (Table
  A6).
- `equivalence_scale`, on equivalised facts only: `updated_oecd_modified_2_adult_reference` or
  `oecd_modified_1_adult_reference`.

**Facts by table**

| Table | Spending | Weighted households | Households in sample |
|---|---|---|---|
| 3.1E, updated OECD-modified scale (2-adult reference) | 140 | 10 | 10 |
| 3.1E, OECD-modified scale (1-adult reference) | 140 | 10 | 10 |
| A6, gross income | 130 | 10 | 10 |
| All households | 15 | 1 | 1 |

The all-household column is the same in the three blocks. The package reads it once, from Table
3.1E's updated-scale block, and those facts carry no decile, basis or scale.

## Semantics

- **Period.** `fiscal_year` 2024: FYE 2025, 1 April 2024 to 31 March 2025, labelled "financial
  year ending 2025" as printed.
- **Population.** UK private households (`household`, `private_household`, K02000001), from the
  LCFS (`survey_instrument: Living Costs and Food Survey`).
- **Means.** Each figure is a mean over all households in the group, not only those reporting
  the expenditure (Background notes). The figures are £ a week in FYE 2025 prices, as printed.
- **Ranking.**
  - Table 3.1E ranks households by equivalised disposable income. Its note 1: from FYE 2025, ONS
    equivalises with the modified OECD scale based on a two-person reference household. This
    replaces the single-person reference household, and FYE 2025 tables publish both methods
    side by side.
  - Table A6 ranks households by gross income, not equivalised.
- **Commodity groups.**
  - Category 4, "Housing (net), fuel & power", excludes mortgage interest payments, council tax
    and Northern Ireland rates. Mortgage interest is in category 13.
  - Total expenditure includes net rent rather than gross rent (the tables' notes).
  - Category 13, "Other expenditure items", is outside consumption. Total expenditure is
    categories 1 to 12 plus 13.
- **Counts.** Weighted households are printed in thousands. The households in the sample are
  unweighted and printed to the nearest ten.

## Markers and rounding

- **Suppressed cells.** ONS prints ".." where a figure rests on fewer than 10 reporting
  households, or where it does not recommend the figure for reliable analysis. Those cells carry
  no fact, and the preserved source cells keep the marker.
  - Education: every decile of every block.
  - Health: every gross income decile. Table 3.1E prints it in every decile.
- **Other markers.** The workbook also uses "[ ]" (fewer than 20 reporting households, use with
  caution), ":" (no reporting households) and "~" (above zero but rounds to zero). None of them
  occurs in the selected cells, and the generator refuses any cell that is neither a number nor
  "..".
- **Rounding.** ONS rounds each figure independently, so components need not add to the totals
  shown.

## Checks

The package's tests read the pinned workbook with openpyxl, independently of Chronicle's parser:

- Every fact equals its workbook cell, and every suppressed cell has no fact.
- The all-household figures are the same in all three blocks.
- For every column, categories 1 to 12 plus category 13 equal total expenditure to within
  £0.10. For all households, the twelve divisions add up to categories 1 to 12 to within £0.60.
- In each block, the deciles' weighted households add up to the all-household 28.71 million to
  within 50,000, and their sample sizes to 5,000 to within 50.
- Pinned published figures:
  - all households: total expenditure £676.60, food £73.70;
  - total expenditure, lowest decile: £377.10 (updated scale), £380.10 (1-adult reference) and
    £291.30 (gross income);
  - total expenditure, highest equivalised decile: £1,243.20 (updated scale).

**Storage.** The workbook is committed, and the private `ledger-raw` bucket holds it under
`raw/uk/ons/ons-family-spending-workbook1-fye2025/2025/<sha256>/`. ONS's pages state that all
content is available under the Open Government Licence v3.0, except where otherwise stated
(checked 26 November 2026).

## Not in this change

- The detailed items below each division.
- The groups' income boundaries, means and medians, and the per-person totals.
- Table 3.1 (unequivalised disposable income deciles), the percentage tables (3.2 and 3.2E), the
  quintile tables (3.1E5 and 3.2E5), and Tables A1 to A3 and 4.1 to 4.3.
- Workbook 2.
- Earlier editions, which ONS equivalised with the single-person reference household (Table
  3.1E's note 1).
