# State-Level Calibration Targets

This directory contains state-level calibration targets for use with the PolicyEngine microsimulation system. Targets are used to calibrate (reweight) microdata samples to match official administrative statistics.

## Data Files

| File | Source | Description |
|------|--------|-------------|
| `state_income_distribution.parquet` | IRS SOI | AGI distribution by state and income bracket |
| `state_tax_credits.parquet` | IRS SOI | EITC and CTC claims by state |
| `state_unemployment.parquet` | DOL | Unemployment insurance statistics by state |
| `state_demographics.parquet` | Census ACS | Population demographics by state |

## Building Targets

Run the build script to generate/update all target files:

```bash
cd arch-data
python data/targets/build_state_targets.py
```

## Usage with microplex Reweighter

```python
from microplex import Reweighter
from data.targets.build_state_targets import load_state_targets, convert_to_reweighter_targets

# Load targets for specific states and years
income_targets = load_state_targets(
    "income_distribution",
    states=["CA", "TX", "NY"],
    years=[2023],
)

# Convert to reweighter format
targets = convert_to_reweighter_targets(
    income_targets,
    target_col="target_returns",
    category_col="state_code",
    microdata_col="state",
)

# Apply to microdata
reweighter = Reweighter(sparsity="l1")
weighted_data = reweighter.fit_transform(microdata, targets)
```

## Data Schema

### state_income_distribution.parquet

| Column | Type | Description |
|--------|------|-------------|
| state_code | string | Two-letter state abbreviation |
| state_fips | string | Two-digit FIPS code |
| state_name | string | Full state name |
| year | int | Tax year |
| agi_bracket | string | AGI bracket label (e.g., "50k_to_75k") |
| agi_bracket_min | float | Lower bound of bracket |
| agi_bracket_max | float | Upper bound of bracket (None for top) |
| target_returns | int | Number of tax returns |
| target_agi | int | Total AGI in dollars |
| target_tax_liability | int | Total federal income tax |

### state_tax_credits.parquet

| Column | Type | Description |
|--------|------|-------------|
| state_code | string | Two-letter state abbreviation |
| state_fips | string | Two-digit FIPS code |
| state_name | string | Full state name |
| year | int | Tax year |
| eitc_claims | int | Number of EITC claims |
| eitc_amount | int | Total EITC dollars |
| ctc_claims | int | Number of CTC claims |
| ctc_amount | int | Total CTC dollars |

### state_unemployment.parquet

| Column | Type | Description |
|--------|------|-------------|
| state_code | string | Two-letter state abbreviation |
| state_fips | string | Two-digit FIPS code |
| state_name | string | Full state name |
| year | int | Year |
| labor_force | int | Total labor force |
| unemployed | int | Number unemployed |
| unemployment_rate | float | Unemployment rate (0-1) |
| initial_claims | int | Initial UI claims |
| continued_claims | int | Continued UI claims |
| avg_weekly_benefit | int | Average weekly benefit |
| benefits_paid | int | Total benefits paid |

### state_demographics.parquet

| Column | Type | Description |
|--------|------|-------------|
| state_code | string | Two-letter state abbreviation |
| state_fips | string | Two-digit FIPS code |
| state_name | string | Full state name |
| year | int | Year |
| total_population | int | Total state population |
| population_under_18 | int | Population under 18 |
| population_18_64 | int | Population 18-64 |
| population_65_plus | int | Population 65+ |
| total_households | int | Total households |
| married_households | int | Married-couple households |
| single_parent_households | int | Single-parent households |
| median_household_income | int | Median household income |
| poverty_rate | float | Poverty rate (0-1) |

## Data Sources

### IRS Statistics of Income (SOI)

- **URL**: https://www.irs.gov/statistics/soi-tax-stats-historic-table-2
- **Coverage**: 2020-2023
- **Update frequency**: Annual (typically ~18 months lag)
- **Notes**: State totals and AGI bracket distributions. Some values are estimated from national patterns.

### Department of Labor (DOL)

- **URL**: https://oui.doleta.gov/unemploy/claims.asp
- **Coverage**: 2020-2023
- **Update frequency**: Weekly (initial claims), Monthly (benefits)
- **Notes**: Includes initial claims, continued claims, and benefit amounts.

### Census American Community Survey (ACS)

- **URL**: https://api.census.gov/data/2022/acs/acs5
- **Coverage**: 2020-2023
- **Update frequency**: Annual
- **Notes**: 5-year ACS estimates. Includes demographics and economic characteristics.

## Loading targets

The in-repo `calibration/` package that once consumed these files was retired
with the legacy target store. The parquet outputs stand alone as inputs for
downstream Microplex calibration:

```python
from data.targets.build_state_targets import load_state_targets

targets = load_state_targets("income_distribution", years=[2023])
```

## Extending Targets

To add new target sources:

1. Add a `build_state_<source>()` function to `build_state_targets.py`
2. Update `build_all_state_targets()` to include the new source
3. Document the schema in this README
4. Run the build script to generate the parquet file
