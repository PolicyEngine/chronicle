# UK facts for chronicle#395

[chronicle#395](https://github.com/PolicyEngine/chronicle/issues/395) asks for the facts
that rows of Microcosm's next policyengine-uk bump wait on
([PolicyEngine/microcosm#1095](https://github.com/PolicyEngine/microcosm/issues/1095)):
Northern Ireland's domestic rates bill, Wales's bus fare yield, the Childcare Offer for
Wales take-up and, in two comments, the OBR's vehicle excise duty (VED) line with its split
by payer, and bottled gas's share of household spending on gas. Everything here is a
published aggregate; no microdata is involved.

`scripts/build_uk_395_packages.py` regenerates the thirteen new packages from the pinned
bytes. The OBR's VED line is written into the March 2026 receipts package by
`scripts/build_uk_excise_packages.py` and carried to October by
`scripts/build_obr_efo_october_2026.py`.

## Sources

All are committed and stored in R2, under the Open Government Licence v3.0.

| Package | File | Publisher, date | sha256 |
|---|---|---|---|
| `lps-domestic-rates-paid-2026` | `domestic-rates-collected-by-district-council.csv` | Land & Property Services on OpenDataNI, resources updated 8 May 2026 | `b8d7d649…` |
| `lps-lone-pensioner-allowance-ye-2024` | `lps-lpa-ye-2024.XLSX` | Land & Property Services, Lone Pensioner Allowance statistics to year end 2024, 29 May 2024 | `f2ea22b1…` |
| `lps-disabled-persons-allowance-ye-2024` | `lps-dpa-ye-2024.XLSX` | Land & Property Services, Disabled Person's Allowance statistics to year end 2024, 29 May 2024 | `41b5aaa7…` |
| `ons-crpsf-ni-domestic-rates-fye2025` | `crpsffye2025totalpublicsectorcurrentreceipts.xlsx` | ONS, country and regional public sector finances, 26 May 2026 | `9dbadf3d…` |
| `dft-bus01-wales-journeys-2025` | the `bus01.ods` that `dft-bus01-passenger-journeys-2025` pins | DfT, revised 24 March 2026 | (shared) |
| `welshgov-childcare-offer-report-2023-24` | `report-of-the-childcare-offer-for-wales-from-september-2023-to-august-2024.pdf` | Welsh Government, 15 October 2025 | `3b2b8632…` |
| `ons-pusf-vehicle-duty-households-october-2026` | `cddz.csv` | ONS time series CDDZ (PUSF), 21 October 2026 | `57e479c9…` |
| `ons-pusf-vehicle-duty-businesses-october-2026` | `eked.csv` | ONS time series EKED (PUSF), 21 October 2026 | `711a959b…` |
| `ons-mm23-cpi-weight-gas-october-2026` | `cjxb.csv` | ONS time series CJXB (MM23), 21 October 2026 | `fa253369…` |
| `ons-mm23-cpi-weight-natural-gas-october-2026` | `l89x.csv` | ONS time series L89X (MM23), 21 October 2026 | `c1022e5c…` |
| `ons-mm23-cpi-weight-liquefied-hydrocarbons-october-2026` | `l89y.csv` | ONS time series L89Y (MM23), 21 October 2026 | `9f381055…` |
| `ons-mm23-cpi-index-natural-gas-october-2026` | `l7e9.csv` | ONS time series L7E9 (MM23), 21 October 2026 | `1187e870…` |
| `ons-mm23-cpi-index-liquefied-hydrocarbons-october-2026` | `l7ea.csv` | ONS time series L7EA (MM23), 21 October 2026 | `9682ce4d…` |

OpenDataNI's record for the LPS dataset sets its licence to "not specified". nidirect's
[Open data](https://www.nidirect.gov.uk/articles/open-data) page states that all data
published on the OpenDataNI portal falls under the Open Government Licence; the manifest
quotes both under `license_evidence`.

## 1. Northern Ireland domestic rates

The issue asks for the whole domestic bill (the regional and the district rate together)
net of reliefs, for 2024-25 and 2025-26, with reliefs as separate facts where a source
gives them. No published table gives the amount levied on domestic property. Two give
domestic receipts, and both are ported:

- **`lps-domestic-rates-paid-2026`** (144 facts). LPS's domestic rates paid against
  ratepayer accounts as at 31 March of each rating year, and the number of domestic
  occupancies that made a payment within the year, for the 11 district councils and
  Northern Ireland, rating years 2020-21 to 2025-26.
  - Concepts: `lps.domestic_rates_paid` (GBP) and
    `lps.domestic_occupancies_with_rates_payment` (count).
  - Record sets `lps.domestic_rates_paid_2026.fy<opening year>`: a rating year is a
    fiscal-year period, April to March.
  - Councils carry their LGD 2014 codes (`N09000001` to `N09000011`); the total row is
    `N92000002`.
  - What "paid" means, from the dataset's notes: the amount paid against the year's
    accounts by 31 March, including accounts with a balance left. Its totals are "not
    adjusted for receipts at year end which have been paid by ratepayers, but not yet
    allocated to a particular rate account". The CSV publishes no relief separately, and
    does not say whether credits such as rate rebate count as payments.
  - 2024-25: GBP 889,543,160 from 817,423 occupancies; 2025-26: GBP 947,888,579. The
    councils' counts sum to Northern Ireland's; their amounts sum to within GBP 2 of it,
    as published.
- **`ons-crpsf-ni-domestic-rates-fye2025`** (52 facts). The 'Northern Ireland' worksheet's
  'Northern Ireland Regional Domestic Rates' (row 51) and 'Northern Ireland District
  Domestic Rates' (row 52), GBP million, financial years 1999 to 2000 through 2024 to
  2025.
  - Concepts: `ons.northern_ireland_regional_domestic_rates` and
    `ons.northern_ireland_district_domestic_rates`, each its own fact; the package adds no
    total.
  - 2024-25: GBP 498 million regional and GBP 441 million district. The rows equal the
    'United Kingdom' worksheet's in every year.

**How the two relate.**
- They are different measures, and neither package derives anything from the other.
- LPS's figure is the amount paid against the rating year's accounts by 31 March, so
  arrears are left out. Reliefs applied to a bill reduce what is due. The dataset does
  not say whether credits such as rate rebate count as payments.
- The ONS workbook does not state whether its rows are accrued or cash, or gross or net of
  reliefs and rebates.
- Together, the ONS rows for 2024-25 (GBP 498 million and GBP 441 million) exceed LPS's
  GBP 889.5 million paid.

**Reliefs.** Two domestic reliefs are published with their own statistics, and both are
ported:

- **`lps-lone-pensioner-allowance-ye-2024`** (420 facts). Lone Pensioner Allowance, a 20%
  rates reduction for ratepayers aged 70 or over who live alone.
  - Owner occupiers with a current award at 31 March 2010 to 2024 (nil awards included),
    and the net amount payable to them over each financial year, by council and for
    Northern Ireland (Tables 1.1 and 1.2).
  - Northern Ireland's net amounts for private renters, NIHE and housing association
    tenants and all tenures (Table 1.5): GBP 9,241,619 in 2023-24.
  - Every amount shares `lps.lone_pensioner_allowance_net_amount` and carries its tenure
    as `lpa_tenure`.
- **`lps-disabled-persons-allowance-ye-2024`** (360 facts). Disabled Person's Allowance,
  a 25% reduction for a property adapted for a disabled resident: properties with a
  current award and the net amount awarded over each financial year, by council and for
  Northern Ireland (Tables 1.1 and 1.2). GBP 4,687,743 in 2023-24.
- Counts are stamped by the calendar year of the 31 March they are current on, and
  amounts by the financial year's opening year.
- Both editions end at 2023-24, and no 2024-25 edition is published yet. Tables that
  restate the ported rows (LPA 1.3 and 1.4, DPA 1.3) are not ported again; the build
  asserts each copy equal.

Rate rebate, and the housing benefit rate relief it replaces, have no published series
by year. LPS's Trust Statement (the Rate Levy Accruals Account) lists reliefs by type, but
its rate revenue is not split between domestic and non-domestic property, and the latest
edition found is for 2022-23 (laid in November 2023). It is not ported. So the sources
give the reliefs above, not the whole bill net of reliefs.

## 2. Wales: local bus journeys, and no published fare receipts

**`dft-bus01-wales-journeys-2025`** (57 facts) reads the BUS01 workbook that the England
package pins, for the Wales columns that package leaves out of its scope:

- BUS01a passenger journeys on local bus services (column R), years ending March 2005 to
  2025;
- BUS01c concessionary passenger journeys (column P), years ending March 2008 to 2025, for
  both Type values: 'Elderly/Disabled journeys' and 'Total concessionary journeys' (which
  includes youth schemes).

The record sets mirror the England package's: concept `dft.local_bus_passenger_journeys`,
`journey_category` filters, and the year ending March stamped by its closing year. In the
year ending March 2025, Wales had 71.7 million local bus journeys, of which 32.3 million
were concessionary. The package derives no fare-paying count.

`welshgov-bus-statistics-2024-25` carries the same journeys, as the Welsh Government
publishes them rounded, under its own concept (`welshgov.bus.passenger_journeys`) and
stamped by opening year. This package's `fiscal_year` 2025 is that package's
`fiscal_year` 2024 (2024-25), and likewise a year back. Join the two on their coverage
dates, not their period values.

**Passenger fare receipts for Wales are not published.**

- DfT publishes receipts by revenue type for England only (BUS05ai).
- For Wales, BUS04ai gives total operating revenue. Its note 1 says that includes Bus
  Service Operators Grant, concessionary fare reimbursement, contracts, other public
  transport support and passenger fare receipts.
- The Welsh Government's public service vehicles release says the operator survey collects
  passenger receipts but does not present them, and StatsWales's road topic has no
  receipts table.

Chronicle therefore carries no fares-paid fact for Wales. Any residual of operating revenue
less published support would be a consumer derivation.

## 3. The Childcare Offer for Wales

**`welshgov-childcare-offer-report-2023-24`** (3 facts) carries Table 4 of the report for
September 2023 to August 2024:

- children in Offer-funded childcare, 21,283: the Offer's monitoring information, so
  `administrative`;
- the estimated eligible population under current eligibility criteria, 36,600:
  "Welsh Government analysis of the ONS Annual Population Survey 2023", Table 4's source
  line says, so `model_output`. It rests on calendar-2023 survey data, while the fact is
  stamped for the 2023-24 Offer year;
- the estimated take-up rate, 58%, also `model_output`.

The Offer year runs September to August. The facts are `academic_year` 2023 with those
dates and no fiscal or calendar basis. No later report has been published yet.

## 4. Vehicle excise duty (comment of 29 October)

**The OBR's line, in both vintages.**

- `obr-efo-receipts-march-2026` gains sheet 3.8 row 52, 'Vehicle excise duties', on the
  cash basis the sheet states, for its 2024-25 outturn only (GBP 8.205 billion): record
  set `obr.efo_2026_03.receipts.vehicle_excise_duties.fy2024`, concept
  `obr.vehicle_excise_duties`.
  - October's tables start at 2025-26, so the calendar-2025 window's 2024-25 part comes
    from March.
  - Of two vintages' numbers for one line and year, Chronicle keeps the later. March's
    forecasts for 2025-26 to 2030-31 are therefore not ported: October publishes those
    years, 2025-26 as outturn. `OBR_OUTTURN_ONLY_LINES` in the build script records this.
  - The other March lines' overlap with October predates this rule; chronicle#397 tracks
    it.
- The October package already carried the line as a table-scoped row
  (`obr.cash_receipts.vehicle_excise_duties`). With VED a March line, the October build
  carries it under the March line id and concept instead
  (`obr.efo_2026_10.receipts.vehicle_excise_duties.fy<year>`, 2025-26 to 2031-32), with
  the same cells, values and assertions. The two vintages share no key.

**The split by payer.** The national accounts record VED paid by households and by
businesses under different tax categories, and ONS publishes both:

- `ons-pusf-vehicle-duty-households-october-2026`: CDDZ, 'Current receipts: Other taxes:
  Vehicle duty paid by households', concept `ons.vehicle_duty_paid_by_households`;
- `ons-pusf-vehicle-duty-businesses-october-2026`: EKED, 'Current receipts: Taxes on
  production: Vehicle duty paid by businesses', concept
  `ons.vehicle_duty_paid_by_businesses`.

Each carries calendar years 2018 to 2025 (GBP million). In 2025, households paid GBP 5,535
million and businesses GBP 3,501 million. The series' quarters and months are not ported,
and no total is derived. The series' metadata state no accounting basis, while the OBR's
line is on a cash basis: use the split for the shares of households and businesses, not
as levels against the OBR line.

## 5. Bottled gas's share of household spending on gas (comment of 29 October)

**The weights.** ONS's CPI weights for COICOP 04.5.2 Gas (CJXB) and its two classes,
04.5.2.1 Natural gas and town gas (L89X) and 04.5.2.2 Liquefied hydrocarbons (L89Y), for
weight years 2024 to 2026, in parts per thousand.

- CJXB's metadata states that unit. L89X's and L89Y's leave it blank, but the two equal
  CJXB in each of these years; the tests assert it.
- ONS bases the weights for year Y on household spending in year Y-2, price-updated to
  January of Y. Undoing that update is Microcosm's arithmetic.
- The 2027 weights are due with ONS's early-2027 weights update.

**The indices.** L7E9 and L7EA, the two classes' indices (2015=100): the annual figures
for 2023 to 2025, which are the averages of the twelve months, and the January values
for 2023 to 2026.

## A parser change

LPS prints amounts as text such as '£51,877,954'. The delimited-text parser already read
'$' amounts as numbers; it now strips '£' the same way, in `chronicle/sources/rows.py` and
`chronicle/sources/cells.py`. Before the change, no artifact that reaches that function
held a '£' followed by a digit. DWP's Stat-Xplore band labels such as '£200' are parsed by
their own parser and are unchanged.
