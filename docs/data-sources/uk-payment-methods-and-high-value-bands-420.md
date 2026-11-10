# Payment methods and Bands I and J for chronicle#420 items 12 and 13

[chronicle#420](https://github.com/PolicyEngine/chronicle/issues/420) items 12 and 13 come in
with chronicle#435's package PR. Microcosm's next data PR (PolicyEngine/microcosm#1095) needs
them as well as #435's own items.
- **Item 12** gives DESNZ's domestic customers by payment method and region, for a Direct
  Debit, standard credit and prepayment draw in Microcosm
  (PolicyEngine/uk-energy-price-cap-jan-2027#4).
- **Item 13** gives the Scottish Government's estimates for the proposed council tax Bands I
  and J, for extending Microcosm's home-value step to Scotland
  (PolicyEngine/uk-scottish-budget-2027-28#5; PolicyEngine/microcosm#1112).

Four packages add 1,823 facts, all official aggregates under the Open Government Licence v3.0
with no microdata. `scripts/build_uk_qep_payment_method_packages.py` and
`scripts/build_uk_scottish_high_value_bands_package.py` write them from the pinned bytes,
asserting the publishers' text, and `--check` compares the output with the committed YAML.
`tests/test_source_uk_qep_payment_methods.py` and
`tests/test_source_uk_scottish_high_value_bands.py` re-read the pinned files. All four files
are committed and in R2 (`chronicle publish-raw`, read back by `chronicle verify-raw`).

## Sources

| Package | File | Publisher, date | sha256 |
|---|---|---|---|
| `desnz-qep-electricity-payment-methods-2026` | `table_242.xlsx` | DESNZ, Quarterly Energy Prices table 2.4.2, updated 29 September 2026 | `a2eb03e7…` |
| `desnz-qep-time-of-use-electricity-payment-methods-2026` | `table_243.xlsx` | DESNZ, Quarterly Energy Prices table 2.4.3, updated 29 September 2026 | `2fb7aa20…` |
| `desnz-qep-gas-payment-methods-2026` | `table_252.xlsx` | DESNZ, Quarterly Energy Prices table 2.5.2, updated 29 September 2026 | `ea59d0bc…` |
| `scotgov-council-tax-high-value-bands-consultation-2026` | `consultation-council-tax-high-value-property-bands-mansion-tax.pdf` | Scottish Government, [Council Tax High-Value Property Bands (Mansion Tax): consultation](https://www.gov.scot/publications/consultation-council-tax-high-value-property-bands-mansion-tax/), 6 July 2026 | `024fb42d…` |

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
- **Provenance.** Both are `model_output`. The paper calls its rates "illustrative", and the
  figures' source reads "Illustrative Scottish Government estimates based on Records of
  Scotland data, CTAXBASE statistics and analysis by the Institute for Fiscal Studies".

The charts print their data labels series by series: the low estimates for Band I and Band J,
then the high ones. The generator and tests read them in that order and check it against the
paper's own text:
- each band's high estimate exceeds its low;
- Band I exceeds Band J;
- the property ranges bracket "approximately 15,000 properties in total";
- the revenue ranges sum to "between £12 million and £16 million per year".

The HTML page's alt text gives the same ranges, rounded.

**Not here:** Registers of Scotland's residential sales over £1 million and £2 million, item 13's
other part. The RoS property market report page
(https://www.ros.gov.uk/data-and-statistics/property-market-statistics/property-market-report)
refused the download (HTTP 403).
