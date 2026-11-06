# UK Scottish Budget facts for chronicle#420

[chronicle#420](https://github.com/PolicyEngine/chronicle/issues/420) asks for the published
facts that four UK events need. This page covers its Scottish batch, for the Scottish Budget
2027-28 ([PolicyEngine/uk-scottish-budget-2027-28](https://github.com/PolicyEngine/uk-scottish-budget-2027-28)):
item 7, Social Security Scotland's caseloads, and item 8, HMRC's Scottish income tax outturn
statistics for 2024 to 2025. Both are official statistics of aggregates under the Open
Government Licence v3.0; no microdata is read or stored.

Five packages add 3,966 facts. `scripts/build_uk_scottish_social_security_packages.py` and
`scripts/build_uk_scottish_income_tax_package.py` write them from the pinned bytes, asserting
the publishers' text; `--check` compares the output with the committed YAML, and
`tests/test_source_uk_scottish_social_security.py` and
`tests/test_source_uk_scottish_income_tax.py` re-read the pinned files. All five files are
committed and in R2 (`chronicle publish-raw`, read back by `chronicle verify-raw`).

## Sources

| Packages | File | Publisher, date | sha256 |
|---|---|---|---|
| `scotgov-adp-caseload-july-2026` | `adult_disability_payment_to_31_july_2026_tables.xlsx` | Social Security Scotland, ADP statistics to 31 July 2026, 15 September 2026 | `89be0f9d…` |
| `scotgov-carer-support-payment-caseload-june-2026` | `carer_support_payment_and_carers_allowance_supplement_june_2026_tables.xlsx` | Social Security Scotland, Carer Support Payment statistics to 30 June 2026, 11 August 2026 | `1cebfef7…` |
| `scotgov-child-disability-payment-caseload-june-2026` | `child_disability_payment_statistics_to_30_june_2026.xlsx` | Social Security Scotland, CDP statistics to 30 June 2026, 18 August 2026 | `7cde9d47…` |
| `scotgov-padp-caseload-july-2026` | `pension_age_disability_payment_to_31_july_2026_tables.xlsx` | Social Security Scotland, PADP statistics to 31 July 2026, 15 September 2026 | `9ab67f8e…` |
| `hmrc-scottish-income-tax-outturn-2024-25` | `Scottish_Income_Tax_Outturn_Statistics_2024-2025.ods` | HMRC, Scottish Income Tax Outturn Statistics: 2024 to 2025, 9 July 2026 | `d085b365…` |

The Social Security Scotland files are renamed without spaces; each manifest keeps the
publisher's file name as `publisher_filename`.

## 7. Social Security Scotland caseloads

`scripts/build_uk_scottish_social_security_packages.py` writes four packages from Social Security Scotland's latest official statistics, each an xlsx pinned under `db/data/scotgov/` (Open Government Licence v3.0; the source id is `scotgov` because Social Security Scotland is an executive agency of the Scottish Government, and `scotgov` is already in the UK bundle and R2 prefix lists). `tests/test_source_uk_scottish_social_security.py` re-reads the workbooks and finds each fact's cell from its own dimensions.

- **Adult Disability Payment to 31 July 2026** (`scotgov-adp-caseload-july-2026`, 1,885 facts; published 15 September 2026). Each month from April 2024 to July 2026, for all clients, new applicants and case transfers ("a DWP client who has had their award transferred over to Adult Disability Payment", note 47): Table 15's caseload and award types (Daily Living only, Mobility only, both), Table 16's Daily Living levels (enhanced, standard, transitional, not awarded), Table 17's Mobility levels (enhanced, standard, not awarded) and Table 18's eleven combinations. At 31 July 2026: Table 19 by age band and Table 25 by council area.
- **Carer Support Payment to 30 June 2026** (`scotgov-carer-support-payment-caseload-june-2026`, 282; published 11 August 2026). Table 9's caseload, in payment and with underlying entitlement, each month from April 2024, by type of client; at 30 June 2026, Table 11 by age group and Table 10 by council area.
- **Child Disability Payment to 30 June 2026** (`scotgov-child-disability-payment-caseload-june-2026`, 81; published 18 August 2026): Table 14's total children in receipt, each month from April 2024, by type of client.
- **Pension Age Disability Payment to 31 July 2026** (`scotgov-padp-caseload-july-2026`, 66; published 15 September 2026): Table 13's caseload each month from its launch in October 2024, by type of client.

Read them this way:

- **Point in time.** "The caseload presented in the ADP tables is based on a true point-in-time on the last day of each month" (note 51; the CSP and CDP tables say the same). The PADP workbook states no basis. Each fact's period is the month, with its last day as the coverage date.
- **Rounding and suppression.** "Figures are rounded for disclosure control and may not sum due to rounding"; a `[c]` cell is suppressed and emits no fact (2 in ADP, 4 in CSP).
- **Ported once.** Every ADP table repeats Table 15's caseload, and the age and council tables print a total: each is asserted equal and ported once. The "Other" council row (postcodes matching no council) has no code and is not ported; ADP's July 2026 councils add to 1,420 less than Scotland.
- **Unassigned award levels.** ADP Tables 15 and 18 fall short of the caseload by the cases that "could not be assigned to a Daily Living or Mobility award level" (note 70): 280 in April 2024, rising to 2,520 (0.5%) in July 2026. Tables 16 and 17 add to the caseload within 10.
- **Not comparable with earlier editions.** Note 84: a software change raised the award levels in Tables 15 to 18 by about 1-2%.
- **Not ported.** Percentages, ADP's Accessible Vehicles and Equipment counts, months before April 2024, and the CDP and PADP award-level, age and council tables (#420 asks for their totals only). Each edition prints age and council only at its own date, so those are the latest date only.

## 8. HMRC Scottish Income Tax Outturn Statistics, 2024 to 2025

`hmrc-scottish-income-tax-outturn-2024-25` holds all four statistical tables of HMRC's release of 9 July 2026: 1,652 facts. `scripts/build_uk_scottish_income_tax_package.py` writes it from the pinned ODS (`Scottish_Income_Tax_Outturn_Statistics_2024-2025.ods`, sha256 `d085b365…`), and `tests/test_source_uk_scottish_income_tax.py` re-reads the workbook with odfpy.

- **Tables.**
  - Table 1 is the NSND Income Tax outturn by component, 2016-17 to 2024-25 (245 facts). The components are the SA and PAYE established liabilities, the estimated further liability, the adjustment for uncollectable amounts, Relief at Source, Gift Aid and the final revenue.
  - Table 2 has the taxpayers by highest marginal rate, and the NSND Income Tax in each tax band by taxpayer marginal rate (736).
  - Table 3 is the outturn by collection method, with the PAYE and SA shares (190).
  - Table 4 is the indicative in-year Income Tax withheld in RTI, by month, 2016-17 to 2025-26 (481). It is not NSND Income Tax: it includes savings, non-Income Tax charges and overpayments.
- **Concepts.** Each table has its own concept: `hmrc.nsnd_income_tax_outturn`, `hmrc.nsnd_income_taxpayers`, `hmrc.nsnd_income_tax_by_band`, `hmrc.nsnd_income_tax_by_collection_method` and its share, and `hmrc.rti_income_tax_withheld`. The "Scottish share of UK" rows take `_scottish_share_of_uk` concepts, stored as fractions. Chronicle doesn't reconcile the three tables' totals. The tests assert that Table 2's all-bands, all-taxpayers cell and Table 3's final revenue equal Table 1's.
- **Geography.**
  - Scottish taxpayers sit at S92000003 and Welsh taxpayers at W92000004. Both mean taxpayer status, set by residence over the whole tax year, not address.
  - The rest of the UK is `hmrc:england_wales_and_northern_ireland` to 2018-19 and on 2019-20's pre-Welsh tax devolution basis. It is `hmrc:england_and_northern_ireland` after that. These are the stamp tax package's scopes.
  - 2019-20 carries `welsh_tax_devolution_basis`.
- **Marginal rates.** `marginal_rate` reuses HMRC's existing values: basic, higher, additional and all ("All rates"). Column J, "Additional/Top rate taxpayers", is `top` for Scotland from 2018-19, `additional` for the rest of the UK, and `additional_or_top` for the UK.
- **A publisher error, ported as published.** The UK's 2024-25 all-bands, all-taxpayers cell is £275,357.1 million. That is £1,254.7 million below its own parts, which is the starter band left out. The generator pins the gap.
- **Quality.** HMRC: "Over 95% of the final outturn figure comes from established Income Tax liabilities". The 2024-25 Scottish revenue is £18,635 million from 3,036,400 taxpayers, the release's "£18.6 billion".
