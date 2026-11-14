# Payment methods, Bands I and J and £1 million sales for chronicle#420 items 12 and 13

[chronicle#420](https://github.com/PolicyEngine/chronicle/issues/420) items 12 and 13 come in
with chronicle#435's package PR. Microcosm's next data PR (PolicyEngine/microcosm#1095) needs
them as well as #435's own items.
- **Item 12** gives DESNZ's domestic customers by payment method and region, for a Direct
  Debit, standard credit and prepayment draw in Microcosm
  (PolicyEngine/uk-energy-price-cap-jan-2027#4).
- **Item 13** gives the Scottish Government's estimates for the proposed council tax Bands I
  and J, and Registers of Scotland's sales over £1 million, for extending Microcosm's
  home-value step to Scotland (PolicyEngine/uk-scottish-budget-2027-28#5;
  PolicyEngine/microcosm#1112).

Five packages add 1,991 facts, all official aggregates under the Open Government Licence v3.0
with no microdata.
- **Generators:** `scripts/build_uk_qep_payment_method_packages.py`,
  `scripts/build_uk_scottish_high_value_bands_package.py` and
  `scripts/build_uk_ros_high_value_sales_package.py` write them from the pinned bytes,
  asserting the publishers' text. `--check` compares the output with the committed YAML.
- **Tests:** `tests/test_source_uk_qep_payment_methods.py`,
  `tests/test_source_uk_scottish_high_value_bands.py` and
  `tests/test_source_uk_ros_high_value_sales.py` re-read the pinned files.
- **Files:** all five are committed and in R2 (`chronicle publish-raw`, read back by
  `chronicle verify-raw`).

## Sources

| Package | File | Publisher, date | sha256 |
|---|---|---|---|
| `desnz-qep-electricity-payment-methods-2026` | `table_242.xlsx` | DESNZ, Quarterly Energy Prices table 2.4.2, updated 29 September 2026 | `a2eb03e7…` |
| `desnz-qep-time-of-use-electricity-payment-methods-2026` | `table_243.xlsx` | DESNZ, Quarterly Energy Prices table 2.4.3, updated 29 September 2026 | `2fb7aa20…` |
| `desnz-qep-gas-payment-methods-2026` | `table_252.xlsx` | DESNZ, Quarterly Energy Prices table 2.5.2, updated 29 September 2026 | `ea59d0bc…` |
| `scotgov-council-tax-high-value-bands-consultation-2026` | `consultation-council-tax-high-value-property-bands-mansion-tax.pdf` | Scottish Government, [Council Tax High-Value Property Bands (Mansion Tax): consultation](https://www.gov.scot/publications/consultation-council-tax-high-value-property-bands-mansion-tax/), 6 July 2026 | `024fb42d…` |
| `ros-property-market-report-2025-26` | `Online-data-tables-Property-Market-Report-2025-2026.xlsx` | Registers of Scotland, [Property Market Report 2025-26](https://www.ros.gov.uk/data-and-statistics/property-market-statistics/property-market-report) data tables, last updated 9 June 2026 | `7eef18d3…` |

The RoS site answers scripted requests with HTTP 403, so the workbook was downloaded in a
browser on 10 November 2026. The manifest keeps the link the browser recorded.

The QEP tables are on gov.uk's
[quarterly domestic energy price statistics](https://www.gov.uk/government/statistical-data-sets/quarterly-domestic-energy-price-statistics)
page. The next update is due 17 December 2026.

## Item 12: payment methods by region

Each table gives the percentage of domestic customers paying by standard credit, Direct
Debit and prepayment, by region:
- **Table 2.4.2:** standard electricity, "customers on standard electricity tariffs only".
- **Table 2.4.3:** "Economy 7 and other time of use electricity tariffs".
- **Table 2.5.2:** gas.

The packages port every quarter from April–June 2024 to April–June 2026, and the annual
sheets for 2024 and 2025.
- Payment method is the `payment_method` filter (`standard_credit`, `direct_debit`,
  `prepayment`) on concepts `desnz.qep.domestic_electricity_payment_method_share` and
  `desnz.qep.domestic_gas_payment_method_share`.
- Fuel and metering arrangement are shared filters. Table 2.4.3 is metering arrangement
  `economy_7_and_time_of_use`, which keeps it apart from table 2.4.2's `standard`.

Read them this way:
- **Shares, not counts.** Each region's three shares are the publisher's rounded percentages
  and add to 100 within 2 points. The tables give no customer numbers.
- **Regions.** The rows are the 14 former Public Electricity Supplier distribution areas, under
  the `desnz:qep:pes` ids the QEP unit cost packages use. Gas uses them too, "for consistency
  with the electricity tables". The electricity tables add England and Wales, Scotland, Great
  Britain, Northern Ireland and the United Kingdom; the gas table stops at Great Britain. The
  United Kingdom (Great Britain for gas) is the total row. England and Wales, Scotland and
  Great Britain are subtotals.
- **Survey.** "Data on gas and electricity tariffs is received directly from a sample of energy
  companies … via a quarterly survey", and "data is uplifted to Ofgem's total customer
  numbers" (methodology sheet).
- **Annual figures.** Table 2.4.3's annual figures "are averages of the rounded quarterly
  figures", and table 2.5.2 calls its sheet an "annual average".
- **Not ported:**
  - earlier periods;
  - the fixed and online tariff sheets;
  - tables 2.4.1 and 2.5.1, which split customers by supplier type, not payment method.

## Item 13: Bands I and J

The consultation's Figures 2 and 3 (page 9 of the paper) give the published low and high
estimates for Scotland.

| Band | Properties, 1 April 2026 values | Additional revenue per year (2026-27 Band D charges) |
|---|---|---|
| I: more than £1 million and up to £2 million | 12,680 to 16,740 | £9.13m to £12.05m |
| J: more than £2 million | 760 to 1,070 | £2.74m to £3.85m |

How the facts are typed:
- **Filters.** Band is `council_tax_band` (`I`, `J`), and the bound is `statistic`
  (`low_estimate`, `high_estimate`).
- **Properties** are `month` 2026-04 (the valuation date), entity `dwelling`, assertion
  `observation`.
- **Revenue** is `fiscal_year` 2026 (2026-27), entity `government`, assertion
  `source_projection`, as the OBR's council tax surcharge costing is. It is scaled from the
  chart's "£ millions" to pounds.
- **What the revenue is measured against.** The paper prices the bands "compared to the
  average Band H charge": Band I properties "would pay around £720 more per year than the
  Band H", and Band J properties "around £3,600 more per year". Each revenue figure is its
  property estimate times that increase, so it applies the full increase over the average
  Band H charge to every estimated property. A score that charges each property the
  increase over its own current band measures something else. The revenue facts' notes
  quote the paper's sentence.
- **Provenance.** Both are `model_output`. The paper calls its rates "illustrative", and the
  figures' source reads "Illustrative Scottish Government estimates based on Records of
  Scotland data, CTAXBASE statistics and analysis by the Institute for Fiscal Studies".

The charts print their data labels series by series: the low estimates for Band I and Band J,
then the high ones. The generator and tests read them in that order and check it against the
paper's own text:
- each band's high estimate exceeds its low;
- Band I exceeds Band J;
- the property ranges bracket "approximately 15,000 properties in total";
- the revenue ranges sum to "between £12 million and £16 million per year";
- each revenue figure is its property estimate times £720 (Band I) or £3,600 (Band J), to
  the £0.01m the chart prints.

The HTML page's alt text gives the same ranges, rounded.

### Item 13: sales over £1 million

`ros-property-market-report-2025-26` (168 facts) ports Registers of Scotland's Property Market
Report 2025-26 tables 9 and 10. They give the volume and value (in "£million", scaled to
pounds) of residential property sales of more than £1 million, for Scotland and each local
authority the tables list, in 2023-24, 2024-25 and 2025-26. Scotland had 403, 391 and 392
such sales.
- **Filter:** the band is `house_price_band` `over_1m`, with the constraint `sale_price` above
  £1,000,000.
- **Concepts:** `ros.residential_property_sales` and `ros.residential_property_sales_value`.
- **Entity:** `dwelling` with role `residential_property_sale` in
  `residential_property_transactions`, as ONS's house price statistics for small areas are.
- **New publisher:** `ros` is new to Chronicle. It joins the UK bundle's source prefixes, and
  its raw files go under `raw/uk/ros` in R2.

Read them this way:
- **Flows, not the stock.** These are sales over each financial year, not the number of homes
  worth more than £1 million. "Only true market residential sales are included" (metadata
  sheet), so share buy-outs and token or non-monetary sales are out.
- **Five council areas have no row.** The tables list 27 of the 32 council areas, with RoS's own
  codes. They print no row for Na h-Eileanan Siar, North Lanarkshire, Orkney Islands, Shetland
  Islands or West Dunbartonshire. The 27 add to Scotland in every ported year, so those five
  had no such sales; Chronicle stores no zero rows for them.
- **RoS price band J cross-check.** Table 9's Scotland row equals table 8's price band
  "J - over £1,000,000" in every ported year. This J is RoS's own price band letter, not
  the proposed council tax Band J above £2 million.
- **Nothing over £2 million.** RoS publishes no split above £2 million, which #420 also asks
  for; that needs an ad hoc table from RoS. The years before 2023-24 and table 11's top postal
  districts are not ported.
