# HMRC annual savings statistics 2026 for PolicyEngine/microcosm#1415

[PolicyEngine/microcosm#1415](https://github.com/PolicyEngine/microcosm/issues/1415)
imputes yearly ISA subscriptions per adult by type, so that ISA-limit reforms and the
Lifetime ISA bonus stop scoring zero on Microcosm. These packages give it HMRC's published
ISA statistics and the one published fact that crosses age with amount. Everything here is
a published aggregate; no microdata is involved.
`packages/hmrc/isa_statistics_2026/build_package.py` regenerates all three packages from the
pinned bytes (`--check` compares instead of writing).

## Sources

All three were published by HMRC on GOV.UK under the Open Government Licence v3.0, and all
are committed and stored in R2.

| Package | File | Bytes | sha256 |
|---|---|---|---|
| `hmrc-isa-statistics-2026` | `Individual_Savings_Account_Tables_2026.ods` ("Individual Savings Account (ISA) tables: September 2026", published 16 September 2026) | 60,311 | `a0eaf908…10e3b` |
| `hmrc-lisa-statistics-2026` | `Lifetime_ISA_Tables_2026.ods` ("Lifetime Individual Savings Account (LISA) tables: September 2026") | 17,089 | `bba1520b…02231` |
| `hmrc-cash-isa-limit-reduction-2026` | the HTML of "Cash Individual Savings Account (ISA) limit reduction: tax information and impact note" (17 September 2026) | 103,157 | `3a27fd60…c6212` |

The two workbooks are on the
[release page](https://www.gov.uk/government/statistics/annual-savings-statistics-2026),
which also has the commentary and the methodology note. Budget 2026 (28 October 2026)
announced that the GBP 12,000 cash limit the impact note describes will not go ahead, so the
page may change; the package pins the bytes fetched on 28 October 2026.

## `hmrc-isa-statistics-2026`: 3,397 facts

Record-set ids start `hmrc.isa_statistics_2026.`.

**What it carries, by table:**
- **Table 9.4** (`table9_4.accounts.ty<year>`, `table9_4.amounts.ty<year>`, tax years 2008
  to 2024).
  - What it counts: Adult ISA accounts subscribed to in the year (`hmrc.isa_accounts_subscribed`, thousands)
    and amounts subscribed (`hmrc.isa_amount_subscribed`, GBP million).
  - `isa_component` values: `cash`, `stocks_and_shares`, `innovative_finance`, `lifetime`,
    `stocks_and_shares_insurance` and `all`.
  - Administrative totals from ISA managers' returns. They count accounts, not individuals.
  - Products that did not exist in a year carry no fact for it. Innovative Finance ISAs start
    in 2016-17 and Lifetime ISAs in 2017-18.
  - HMRC marks 2024-25 as provisional.
- **Table 9.6** (`table9_6.ty<year>`, 2011 to 2024).
  - What it counts: the market value of Adult ISA funds (`hmrc.isa_market_value`, GBP million) at the end
    of each tax year.
  - Dimensions: `isa_component` and `isa_asset_type`. The stocks-and-shares component's
    lines include `cash_on_deposit`.
  - HMRC's note says Lifetime ISA market values are inside the cash and stocks-and-shares
    totals.
- **Table 9.7** (`table9_7.ty2023.<type>.subscribers` and `.holders`).
  - What it counts: individuals subscribing (`hmrc.isa_subscribers`) and holding (`hmrc.isa_holders`) in
    2023-24.
  - Rows are 11 `isa_income_band`s plus all ranges, with `total_income` bounds.
  - Columns are 11 `isa_subscription_band`s plus all subscriptions. The bands have an edge
    at GBP 12,000 and an exact GBP 20,000 band.
  - For holders there are two columns: no further subscription, and all holders.
  - It is split into four `isa_type` blocks: `all`, `cash_only`, `stocks_and_shares_only`
    and `cash_and_stocks_and_shares`. In the `all` and `cash_and_stocks_and_shares` blocks,
    the band is the combined amount subscribed.
- **Table 9.8** (`table9_8.ty2023.<sex>.subscribers` and `.holders`): the same counts by 21
  `age_band`s and sex, with types as columns.
- **Table 9.9** (`table9_9.ty2023.subscribers` and `.holders`): the same counts by English
  region and country. HMRC's overseas and unknown row is the statistical scope
  `hmrc:overseas_and_unknown`.
- **Tables 9.10, 9.11 and 9.12**: individuals holding ISAs at the end of 2023-24.
  - Breakdowns: by income and type (9.10), by age and sex (9.11), and by region (9.12).
  - Columns are 12 `isa_market_value_band`s, with each breakdown's total and HMRC's average
    market value per holder (`hmrc.isa_mean_market_value_per_holder`).
  - Table 9.12's share of adults aged 18 or over (`hmrc.isa_holders_share_of_adults`) is
    its own `model_output` record set, since it rests on ONS population estimates.

**Provenance.**
- Tables 9.4 and 9.6 are `administrative`.
- Tables 9.7 to 9.12 are `survey_aggregate`. HMRC estimates them from a sample of
  individuals' accounts matched to the Survey of Personal Incomes, calibrated to the
  totals in Tables 9.4 and 9.6. Income, age, sex and region come from the Survey of
  Personal Incomes.

**Caveats.** They are kept in the facts' notes.
- **People under "(thousands)" headings.** The column headings of Tables 9.7 to 9.12 say
  "(thousands)", but the cells count individuals. Only that reading matches HMRC's
  commentary (13.05 million subscribers and 23.0 million holders in 2023-24), so those
  measures carry `value_scale: 1`. The heading text stays as each measure's header guard.
- **Coverage.** Tables 9.7 to 9.12 exclude Innovative Finance ISA holders. Their notes do
  not say how Lifetime ISAs are classed. Help to Buy ISAs are inside cash.
- **Amounts.** Table 9.7 has no amounts, and its bands are not reconciled here with Table
  9.4's amounts subscribed.
- **Totals in more than one table.** The same subscriber and holder totals appear in
  several tables (9.7 with 9.8 and 9.9, and with 9.10 to 9.12). They agree, and they
  account for this package's 145 semantic duplicate keys.
- **Not ported:**
  - Table 9.4's average subscription per account, a quotient of ported cells;
  - the Junior ISA rows of Tables 9.4 and 9.6.

## `hmrc-lisa-statistics-2026`: 40 facts

Table 1a's yearly Lifetime ISA withdrawals, 2018-19 to 2025-26
(`hmrc.lisa_statistics_2026.table1a.ty<year>`):
- individuals withdrawing for a house purchase, and the value withdrawn;
- individuals making unauthorised withdrawals, and the value withdrawn;
- the withdrawal charges.

The concepts are `hmrc.lisa_withdrawers`, `hmrc.lisa_withdrawal_value` and
`hmrc.lisa_withdrawal_charges`, by `lisa_withdrawal_reason`. HMRC rounds the numbers of
individuals to the nearest 50. The 2025-26 house-purchase count is 99,750.

The workbook has no subscriptions, holdings or bonus. Lifetime ISA accounts and amounts
subscribed are Table 9.4's `lifetime` rows, and the government's bonus is published in
neither file. Not ported: Table 1b, the same flows by month, and Table 1a's two average
columns.

## `hmrc-cash-isa-limit-reduction-2026`: 2 facts

One sentence of the impact note: "In 2022 to 2023, 78% of cash ISA subscribers aged under
65 subscribed less than £12,000 to a cash ISA and 22% subscribed over £12,000."

- **Record set:** `hmrc.cash_isa_limit_reduction_2026.cash_subscribers_under_65.ty2022`,
  concept `hmrc.cash_isa_subscribers_share` (unit `percent`, aggregation `share`), by
  `cash_isa_subscription_band`.
- **Provenance:** the note names no data source, so the shares are `model_output`.
- **What the sentence leaves open:** where a subscription of exactly GBP 12,000 falls, and
  whether someone who also paid into a stocks-and-shares ISA is counted on the cash amount
  alone.
- **Not ported:** the page's other "22%", the flat-rate charge on interest on cash held in
  non-cash ISAs, because it is a rate, not this share.

## For Microcosm

Re-pin the UK feed to the merge commit first; the vendor tool refuses a feed that does not
match the pin. Then select:
- **Subscriber cells:** record sets `hmrc.isa_statistics_2026.table9_7.ty2023.*`,
  `table9_8.ty2023.*` and `table9_9.ty2023.*`.
- **Growth and composition:** `table9_4.{accounts,amounts}.ty2023` and `.ty2024`.
- **Independent checks:** holders and market values from `table9_6.ty2024` and
  `table9_10` to `table9_12`, the impact note's record set, and Lifetime ISA Table 1a.

Bounds are first-class constraints, so a consumer reads band edges from them rather than
from value ids. Values are already people or pounds, so nothing should be multiplied by
1,000. Aligning the 2023-24 cells with a build year, and choosing between Table 9.7's bands
and Table 9.4's amounts, are the consumer's decisions.
