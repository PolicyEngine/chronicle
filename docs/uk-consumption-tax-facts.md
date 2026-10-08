# UK consumption-tax source facts

Chronicle preserves ONS household final consumption expenditure and DESNZ road
transport fuel use for consumption diagnostics. Consumers choose survey bridges,
VAT treatment, conversions and calibration rows. These packages supply publisher
observations with source-cell lineage.

## ONS Consumer Trends

`ons-consumer-trends-current-price-2026` reuses the preserved `cpnsa.xlsx` with
SHA-256 `109e53de0c09d30327ae2053a0487cee159fe44135884707c9000c252438143c`.
The workbook's cover sheet identifies the 30 June 2026 release, covering January
to March 2026. Chronicle acquired these bytes on 9 September 2026; that date is
`extracted_at`, not the publication vintage. Facts carry
`vintage=2026_06_30_release_2026_q1`. The publisher's current URL now serves a
later release; adding the 30 September 2026 release requires a separate vintage
and artifact, preserving this workbook's bytes and checksum.

The extension retains every existing energy and road-fuel source-record
identifier. It selects 0CN, every column of 01CN–12CN,
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
COICOP codes remain strings in filters and constraints, including `0`, `10`,
`11` and `12`. Domestic facts use entity role `households_on_uk_territory`;
national facts use `resident_households`. Signed tourism adjustments use
`household_tourism_adjustment` because their components concern both residents
and non-residents.

The seven existing series (04.5, 04.5.1–04.5.4, 07.2.2 and 07.3.2) keep their
specific `ons.household_expenditure.*` measure concepts. The added series use
`ons.household_final_consumption_expenditure`. To select the complete feed,
filter by COICOP, source sheet, period and consumption concept rather than only
the generic measure concept.

### Consumer migration

The 217 existing facts retain their source-record IDs and values, but their
aggregate and semantic fact keys change. Their domestic entity role changes
from `resident_households` to `households_on_uk_territory`; they gain
`price_basis`, `seasonal_adjustment`, `published_unit`, `source_sheet` and
`consumption_concept`; and their lineage includes the value, COICOP header and
CDID guard cells. The corrected publication vintage also changes provenance
and source-cell keys. Consumers must refresh pinned keys and role selectors.
Microcosm's `ons_household_expenditure_facts.json` vendors 42 annual rows affected
by this migration; see [microcosm#1113](https://github.com/PolicyEngine/microcosm/issues/1113).

ONS publishes current prices, without seasonal adjustment, in £ million.
Numeric facts retain the package's `gbp` representation through a scale of
1,000,000. Every fact carries `published_unit=gbp_million`, `price_basis` and
`seasonal_adjustment`. Cells containing `[x]` in 04.4.4, 04.5.5 and 09.6 retain
that string and `publication_status=not_available`. Consumers must handle these
markers before monetary calculations. Chronicle supplies no zero replacement.

Domestic 07.2.2 includes non-residents' fuel spending in the UK. TOURCN supplies
no COICOP-specific tourism split, so this feed alone cannot convert domestic
07.2.2 to the national consumption concept. A survey-based bridge needs a
separate source or consumer assumption for that adjustment.

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
total. Both London subdivisions use `geography_level=region` within the current
schema, so a level-only filter returns ten areas. `geography_kind` distinguishes
`english_region` (eight), `london_subregion` (two) and `country` (six).
It selects each country's published total once; the England summary row
uses the country code E92000001. Local-authority figures remain in the preserved
workbook and source cells, outside emitted facts.

The emitted columns also exclude the personal-transport and freight-transport
subtotals, the bioenergy "of which" column, and road-type breakdowns. Those
cells remain in the preserved workbook. Consumers splitting duty on blended
biofuel must select or source the bioenergy component separately.

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
kilometres. Petrol, diesel and all-vehicle/all-fuel facts carry
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
