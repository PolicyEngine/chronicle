# US Poverty and Nonfiler Source-Target Coverage

This document records the Chronicle-side source coverage contract for US poverty and
nonfiler calibration work. Chronicle stores source-backed facts and target inputs.
Microcosm owns the active calibration profile, source reconciliation, aging, and
model variable mapping.

The related machine-readable contract lives in
`chronicle.targets.us_poverty.US_POVERTY_NONFILER_TARGET_COVERAGE`.

## Main Answer

Yes, many of the targets discussed for ECPS/Microcosm are already in Chronicle:

- BEA NIPA full-population income, transfer, tax, and pension aggregates.
- IRS SOI filer income, deduction, credit, wage, and state/district facts.
- USDA SNAP participation and benefits.
- HHS ACF TANF and LIHEAP administrative data.
- SSA Social Security and SSI totals.
- CMS Medicaid, CHIP, ACA, Medicare, and National Health Expenditure data.
- Census PEP/ACS demographic controls and state individual income tax
  collections.

The missing piece was not another legacy `policyengine-us-data` comparison. It
was an explicit coverage gate that tells consumers which Chronicle source families
are hard target inputs, which are validation-only diagnostics, and which source
packages are still missing for SPM-specific components.

## Hard Target Inputs

These source families are appropriate Chronicle inputs for Microcosm target
composition. Microcosm may still decide how to reconcile, age, activate, or map
them to model variables.

| Family | Source scope | Chronicle aliases |
|---|---|---|
| Population by age, sex, state, and congressional district | Census PEP and ACS demographics | `census-pep-2024-national-age-sex`, `census-pep-2024-state-age-sex`, `census-acs-s0101-national-age-2024`, `census-acs-s0101-state-age-2024`, `census-acs-s0101-congressional-district-age-2024` |
| NIPA personal income, transfers, taxes, and pensions | BEA NIPA full-population aggregates | `bea-nipa-total-wages-salaries`, `bea-nipa-personal-income-components`, `bea-nipa-personal-income-disposition`, `bea-nipa-pension-contributions` |
| SOI filer income, taxes, deductions, and credits | IRS SOI administrative totals | `soi-table-1-1`, `soi-table-1-2`, `soi-table-1-4`, `soi-table-2-1`, `soi-table-2-5`, `soi-table-2-5-eitc-agi-children-2023`, `soi-table-4-3`, `soi-state-2022`, `soi-historic-table-2`, `soi-historic-table-2-state-agi-2022`, `soi-historic-table-2-state-agi-2023`, `soi-historic-table-2-state-broad-2022`, `soi-historic-table-2-state-eitc-2022`, `soi-w2-statistics-2020` |
| Social Security and SSI | SSA administrative totals | `ssa-annual-statistical-supplement-2025`, `ssa-ssi-table-7b1-2024` |
| SNAP | USDA FNS administrative totals | `usda-snap-fy69-to-current` |
| TANF | HHS ACF caseload and financial totals | `hhs-acf-tanf-caseload-2024`, `hhs-acf-tanf-financial-2024` |
| LIHEAP | HHS ACF LIHEAP profiles | `hhs-acf-liheap-fy2023-national-profile`, `hhs-acf-liheap-fy2024-national-profile` |
| Health programs | CMS administrative enrollment and spending totals | `cms-medicaid-chip-monthly-enrollment-dataset`, `cms-medicaid-chip-monthly-enrollment-december-2024`, `cms-nhe-historical-service-source`, `cms-aca-oep-state-level`, `cms-aca-oep-state-level-2022`, `cms-aca-oep-state-level-2025`, `cms-aca-effectuated-enrollment-2022`, `cms-medicare-trustees-report-2025-part-b-premium-income` |
| State individual income taxes | Census state tax collections | `census-stc-individual-income-tax` |

BEA NIPA is especially important for nonfilers because it is a
full-population macro control, not an SOI-only filer target. It currently gives
Chronicle coverage for wages, proprietors' income, rental income, interest,
dividends, UI, Social Security, SSI, SNAP, Medicare, Medicaid, TANF, personal
taxes, disposable personal income, and pension contributions.

## Validation Only

These sources are useful diagnostics, but they should not be hard targets for
fixing CPS/Microcosm poverty resources:

| Family | Why validation-only |
|---|---|
| Census CPS ASEC SPM poverty, resources, and thresholds | This is the result we are trying to diagnose. Hard-targeting it would mask model/data errors. |
| Distributional national accounts | Useful for reasonableness checks, but partly informed by survey distribution assumptions and not an independent SPM target. |
| ACS poverty and income distributions | Independent of CPS sampling, but still survey-based and not the SPM resource definition. |
| ACS S2201 SNAP congressional district estimates | Useful for local validation or allocation, not a national administrative hard target. |
| CBO income and revenue projections | Useful for forecast/aging checks, not contemporaneous calibration. |
| Federal Reserve household balance sheet | Useful for wealth/capital-income reasonableness, not an SPM resource target. |

## Source Gaps

These are the current poverty/SPM-specific gaps to add as source packages:

| Gap | Candidate source | Why it matters |
|---|---|---|
| Housing assistance and subsidy controls | HUD Picture of Subsidized Households; HUD assisted-housing unit or expenditure tables | SPM adds capped housing subsidy resources. |
| WIC participation and benefits | USDA FNS WIC program data | SPM adds WIC resources. |
| School lunch and breakfast benefits | USDA FNS National School Lunch and School Breakfast program data | SPM adds school meal resources. |
| Child support received and paid | HHS OCSE annual report tables | Small in the SPM gap, but should be modeled and chronicled for completeness. |
| Workers' compensation benefits | DOL, NASI, or state workers' compensation totals | BEA broad transfers are not a clean program-specific workers' comp target. |
| MOOP, work expenses, and childcare expense validation | MEPS, BLS Consumer Expenditure, AHS, or childcare expenditure sources | These are SPM deductions. They should guide validation/imputation rather than be blind hard targets. |

## ECPS Gate Interpretation

The old ECPS-style gate was a source-backed target coverage gate: every active
source-backed target family needed a chronicled source family, with reviewed
exclusions for survey/model-only variables. That idea belongs here in Chronicle as
source coverage, while Microcosm owns the active target profile.

The important distinction is:

- NIPA, SOI, SSA, USDA, HHS ACF, CMS, and Census population/tax collections are
  source-backed candidate inputs.
- CPS SPM and DINA-style distributional outputs are validation diagnostics.
- HUD housing, WIC, school meals, OCSE child support, workers comp, and
  MOOP/work/childcare validation still need explicit source packages.
