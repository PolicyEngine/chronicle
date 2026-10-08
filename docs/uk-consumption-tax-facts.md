# UK consumption-tax source facts

Chronicle preserves ONS household final consumption expenditure and DESNZ road
transport fuel use for consumption diagnostics. Consumers choose survey bridges,
VAT treatment, conversions and calibration rows. These packages supply publisher
observations with source-cell lineage.

## ONS Consumer Trends

`ons-consumer-trends-current-price-2026` reuses the preserved `cpnsa.xlsx` with
SHA-256 `109e53de0c09d30327ae2053a0487cee159fe44135884707c9000c252438143c`.
It retains the September 2026 vintage and every existing energy and road-fuel
source-record identifier. The extension selects 0CN, every column of 01CN–12CN,
and annual TOURCN observations. Selectors guard the period, COICOP header and
ONS CDID identifier.

The declarations cover 5,164 facts: 166 columns in 31 annual/quarterly periods,
plus three tourism columns in six years. Annual periods run from 2020 to 2025;
quarterly periods run from 2020-Q1 to 2026-Q1.

| Selection | Publisher coverage |
| --- | --- |
| `source_sheet=0CN`, `coicop=NAT0` | National household consumption: UK residents |
| `source_sheet=0CN`, `coicop=0` | Domestic consumption on UK territory, including non-residents |
| `source_sheet=0CN`, `coicop=01` through `12` | The twelve domestic divisions |
| `source_sheet=01CN` through `12CN` | Every published division, group and class column, including rentals, narcotics, education, insurance and FISIM |
| `source_sheet=0CN`, `coicop=TOUR` | Annual and quarterly net tourism adjustments |
| `source_sheet=TOURCN`, `coicop=TOUR1` | Annual foreign-tourist expenditure in the UK, with the publisher's negative sign |
| `source_sheet=TOURCN`, `coicop=TOUR2` | Annual UK-tourist expenditure abroad |
| `source_sheet=TOURCN`, `coicop=TOUR` | Annual net tourism adjustments |

Use `source_sheet` when selecting divisions or net tourism: the workbook repeats
these series on its overview and detailed sheets. Chronicle preserves both
publisher locations. `consumption_concept` distinguishes `domestic`, `national`
and `national_adjustment`; `tourism_flow` identifies the tourism direction.

ONS publishes current prices, without seasonal adjustment, in £ million.
Numeric facts retain the package's `gbp` representation through a scale of
1,000,000. Every fact carries `published_unit=gbp_million`, `price_basis` and
`seasonal_adjustment`. Cells containing `[x]` in 04.4.4, 04.5.5 and 09.6 retain
that string and `publication_status=not_available`. Consumers must handle these
markers before monetary calculations. Chronicle supplies no zero replacement.

## DESNZ road transport fuel consumption

`desnz-road-transport-fuel-consumption-2024` preserves the [25 June 2026
workbook](https://www.gov.uk/government/statistics/uk-road-transport-fuel-consumption-at-regional-and-local-authority-level-2005-to-2024)
with SHA-256
`1b6d8596659ed9e4e6cb946b904f967a48d9eda175709c7f0b3801f87d0fc39f`.
Its manifest uses artifact year 2026; every fact retains its calendar reference
year from 2005 to 2024. Geography boundaries follow the workbook's December 2025
note. Selectors guard the geography, vehicle/fuel column and year/unit heading.

The declarations cover 3,200 observations: twenty years, sixteen published
country/region totals and ten vehicle/fuel columns. The columns include petrol
and diesel cars, motorcycles, buses and coaches, petrol and diesel LGVs, diesel
and natural-gas HGVs, LPG LGVs and all vehicles. Filters expose `vehicle_type`
and `fuel`; values stay in `ktoe` (thousand tonnes of oil equivalent). The
`institutional_sector` entity with role `road_transport` covers all road users.

The geography set includes the UK, GB, England, Wales, Scotland and Northern
Ireland, eight English regions, Inner London and Outer London. The publisher
prints Inner and Outer London separately. Chronicle adds no combined London
total. It selects each country's published total once; the England summary row
uses the country code E92000001. Local-authority figures remain in the preserved
workbook and source cells, outside emitted facts.

The accompanying [methodology](https://www.gov.uk/government/statistics/uk-road-transport-fuel-consumption-at-regional-and-local-authority-level-2005-to-2024/sub-national-road-transport-fuel-consumption-statistics-methodology-summary-2005-2024-web-accessible)
distinguishes the spatial mapping from the national emissions inventory. It
normalises the inventory to DUKES fuel sales after adjustments for off-road use
and Crown Dependencies; spatial mapping does not apply that normalisation.
The package records `estimate_basis=spatial_estimates_without_dukes_normalisation`
and `national_inventory_basis=normalised_to_adjusted_dukes_fuel_sales`, including
on the workbook's UK and GB totals. These totals retain the workbook's spatial
basis. The methodology page and its acquisition manifest are preserved under
`db/data/desnz/road_transport_fuel_consumption_2024/methodology/`.

`population_scope=vehicles_travelling_in_area` records area-based activity.
`electric_vehicle_treatment=excluded` records the removal of electric-vehicle
kilometres. Petrol and diesel facts carry
`biofuel_treatment=includes_blended_biofuels`, following workbook Note 6.
The workbook and methodology publish no ktoe-to-litres or ktoe-to-tonnes
conversion factors. Consumers supply those factors separately.

## Authoring and verification

`scripts/build_uk_consumption_tax_packages.py` regenerates the declarative
packages from the preserved workbooks. It builds no facts and runs no tests.
YAML templates share repeated category definitions across periods.

Regression coverage lives in `tests/test_source_uk_consumption_tax_facts.py`;
the existing transport/energy tests retain their original series checks and
account for the wider feed. Chronicle requires source-package/build-suite
validation and source-fidelity and boundary reviews before merge.
