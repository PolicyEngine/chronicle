# IRS Statistics of Income (SOI) State-Level Data Sources

This document catalogs available IRS SOI data sources with state-level breakdowns for use in tax-benefit microsimulation calibration.

## Overview

The IRS Statistics of Income (SOI) Division provides comprehensive state-level tax data derived from individual income tax returns (Forms 1040). These datasets are essential for:

- Calibrating microsimulation models to match administrative totals
- Validating income distributions by state and AGI bracket
- Cross-checking survey data (CPS, ACS) against tax records

## Primary Data Sources

### 1. Historic Table 2: Individual Income and Tax Data by State and AGI Size

**URL**: https://www.irs.gov/statistics/soi-tax-stats-historic-table-2

**Description**: The cornerstone state-level SOI dataset, providing individual income and tax data classified by state and size of adjusted gross income.

#### Years Available

| Period | URL | Format |
|--------|-----|--------|
| 2020-2022 | [Main page](https://www.irs.gov/statistics/soi-tax-stats-historic-table-2) | CSV, XLSX |
| 2015-2019 | [2015-2019](https://www.irs.gov/statistics/soi-tax-stats-historic-table-2-2015-2019) | CSV, XLSX |
| 2010-2014 | [2010-2014](https://www.irs.gov/statistics/soi-tax-stats-historic-table-2-2010-2014) | CSV, XLSX |
| 2005-2009 | [2005-2009](https://www.irs.gov/statistics/soi-tax-stats-historic-table-2-2005-2009) | XLS |
| 2000-2004 | [2000-2004](https://www.irs.gov/statistics/soi-tax-stats-historic-table-2-2000-2004) | XLS |
| 1996-1999 | [1996-1999](https://www.irs.gov/statistics/soi-tax-stats-historic-table-2-1996-1999) | XLS (Excel 4) |

#### Variables

| Variable | Description | Unit |
|----------|-------------|------|
| `n_returns` | Number of returns filed | Count |
| `n_exemptions` | Number of personal exemptions (proxy for population) | Count |
| `agi` | Adjusted gross income | Dollars |
| `wages_salaries` | Wages and salaries | Dollars |
| `dividends` | Dividends before exclusion | Dollars |
| `interest` | Interest received | Dollars |
| `tax_liability` | Total income tax liability | Dollars |

#### AGI Size Brackets

The data is stratified by AGI brackets (varies slightly by year):

- Under $1
- $1 - $5,000
- $5,000 - $10,000
- $10,000 - $15,000
- $15,000 - $20,000
- $20,000 - $25,000
- $25,000 - $30,000
- $30,000 - $40,000
- $40,000 - $50,000
- $50,000 - $75,000
- $75,000 - $100,000
- $100,000 - $200,000
- $200,000 - $500,000
- $500,000 - $1,000,000
- $1,000,000 - $1,500,000
- $1,500,000 - $2,000,000
- $2,000,000 - $5,000,000
- $5,000,000 - $10,000,000
- $10,000,000 or more

#### Geographic Coverage

- All 50 states
- District of Columbia
- Puerto Rico
- Other areas (territories, APO/FPO)
- United States total

#### Documentation

Each tax year includes a documentation guide (DOC format) explaining variable definitions and methodology.

---

### 2. AGI Percentile Data by State

**URL**: https://www.irs.gov/statistics/soi-tax-stats-adjusted-gross-income-agi-percentile-data-by-state

**Description**: Income distribution data by cumulative AGI percentiles for each state.

#### Years Available

2006-2022 (CSV, XLSX formats)

#### Variables

**Table 1**: Number of Returns, Shares of AGI and Total Income Tax, AGI Floor on Percentiles, and Average Tax Rates

| Variable | Description |
|----------|-------------|
| `n_returns` | Number of returns |
| `share_agi` | Share of total AGI |
| `share_tax` | Share of total income tax |
| `agi_floor` | AGI floor for percentile |
| `avg_tax_rate` | Average tax rate |

**Table 2**: Number of Returns, Shares of AGI, and Sources of Income

| Variable | Description |
|----------|-------------|
| `wages_salaries` | Wages and salaries |
| `taxable_interest` | Taxable interest |
| `ordinary_dividends` | Ordinary dividends |
| `capital_gains` | Net capital gains |
| `business_income` | Business/professional income |
| `partnership_scorp` | Partnership and S-Corp income |

#### Percentile Breakdowns

Data provided by descending cumulative percentiles (e.g., top 1%, top 5%, top 10%, top 25%, top 50%).

#### Geographic Coverage

All 50 states + District of Columbia

#### Data Quality Note

Limited to returns with **positive AGI only**.

---

### 3. ZIP Code Data

**URL**: https://www.irs.gov/statistics/soi-tax-stats-individual-income-tax-statistics-zip-code-data-soi

**Description**: Granular geographic data by state and ZIP code.

#### Years Available

- 1998, 2001
- 2004-2022 (continuous)

#### Variables

| Variable | Description |
|----------|-------------|
| `n_returns` | Number of returns (proxy for households) |
| `n_exemptions` | Personal exemptions (proxy for population) |
| `agi` | Adjusted gross income |
| `wages_salaries` | Wages and salaries |
| `dividends` | Dividends before exclusion |
| `interest` | Interest received |

#### Format

State-level Excel spreadsheets compressed in ZIP format.

---

### 4. County Data

**URL**: https://www.irs.gov/statistics/soi-tax-stats-county-data

**Description**: County-level income and tax data with state totals.

#### Years Available

1989-2022

#### Variables

Same as ZIP Code data:
- Number of returns
- Personal exemptions
- Adjusted gross income
- Wages and salaries
- Dividends
- Interest

#### Format

- 2011-2022: Web-accessible pages
- 1989-2010: Compressed ZIP archives with state Excel files

---

### 5. State-to-State Migration Data

**URL**: https://www.irs.gov/statistics/soi-tax-stats-migration-data

**Description**: Year-over-year migration flows based on address changes on tax returns.

#### Years Available

Filing Year 2011 onward (most recent: 2021-2022)

#### Variables

| Variable | Description |
|----------|-------------|
| `n_returns` | Number of migrating returns |
| `n_exemptions` | Number of exemptions (persons) |
| `agi` | Total AGI of migrants |

#### Breakdowns

- By AGI size bracket
- By age of primary taxpayer
- Inflows and outflows separately

#### Geographic Levels

- State-to-state
- County-to-county

---

## Credit and Deduction Data by State

### EITC Statistics

**URL**: https://www.irs.gov/credits-deductions/individuals/earned-income-tax-credit/earned-income-tax-credit-statistics

**Years**: 1999-2022

**Variables**:
- Number of returns with EITC
- Total EITC amount

**Note**: State-level EITC breakdowns available through linked participation rate data.

**Data Quality**:
- Estimates based on samples
- Excludes amended returns and audit adjustments
- 2021-2022 data from EITC Fact Sheet (not SOI sample)

### Child Tax Credit / Additional Child Tax Credit

**URL**: https://www.irs.gov/statistics/soi-tax-stats-state-data-fy-2022

**State-level statistics include**:
- CTC claims by state
- ACTC claims by state
- Benefits gap estimates (underclaims)

**Key 2022 Statistics**:
- Maximum CTC: $2,000 per qualifying child
- Maximum ACTC: $1,500 per qualifying child
- ACTC total: $34 billion on 17.8 million returns

### State Data by Fiscal Year

**URLs**:
- [FY 2024](https://www.irs.gov/statistics/soi-tax-stats-state-data-fy-2024)
- [FY 2023](https://www.irs.gov/statistics/soi-tax-stats-state-data-fy-2023)
- [FY 2022](https://www.irs.gov/statistics/soi-tax-stats-state-data-fy-2022)

**Variables**:
- Returns filed
- Taxes collected
- Refunds issued

---

## Publication 1304: Individual Income Tax Returns Complete Report

**URL**: https://www.irs.gov/statistics/soi-tax-stats-individual-income-tax-returns-complete-report-publication-1304

**Description**: Comprehensive national-level data with detailed breakdowns (not state-specific but useful for validation).

### Available Tables

| Part | Content |
|------|---------|
| Basic Tables Part 1 | Returns filed and sources of income |
| Basic Tables Part 2 | Exemptions and itemized deductions |
| Basic Tables Part 3 | Tax computation and credits |
| Table A | Selected items in current and constant dollars |

### Years Available

1990-2023

### Format

Microsoft Excel files; complete report as PDF

---

## Historical Data Tables Summary

**URL**: https://www.irs.gov/statistics/soi-tax-stats-historical-data-tables

| Table | Description | State-Level |
|-------|-------------|-------------|
| Table 1 | Selected Income and Tax Items | No |
| Table 2 | Income/Tax by State and AGI Size | **Yes** |
| Table 3 | Returns, Income, Deductions by AGI Size | No |
| Table 7 | Standard and Itemized Deductions | No |
| Table 21c | Returns Filed by Type, State, Calendar Year | **Yes** |

---

## Data Quality Notes

### Sampling

- Data derived from samples of filed returns (before audit)
- Represents Forms 1040, 1040A, 1040EZ (historical), 1040-SR
- Electronic and paper returns included

### Suppression

- Small cells may be suppressed to prevent disclosure
- ZIP-level data particularly affected
- State totals generally complete

### Rounding

- Dollar amounts typically in thousands or millions
- Return counts may be rounded to nearest thousand
- Check documentation guide for specific year

### Timing

- Tax Year vs. Filing Year distinction important
- Most data released 18-24 months after tax year end
- Preliminary vs. final releases may differ

### Coverage

- Represents tax filers only (not total population)
- Non-filers excluded (significant for low-income analysis)
- Number of exemptions approximates but does not equal population

---

## Chronicle packages

Chronicle reads these tables as source packages under `packages/irs_soi/`,
which parse the IRS files with checksum-locked artifacts and source-cell
lineage. The state-grain packages are:

- `soi-historic-table-2-state-broad-2022`: returns, AGI, income sources,
  itemized deductions, tax and credits by state for tax year 2022
- `soi-historic-table-2-state-agi-2022` and `soi-historic-table-2-state-agi-2023`:
  returns and AGI by state and AGI band
- `soi-historic-table-2-state-eitc-2022`: EITC claims and amounts by state and
  number of qualifying children
- `soi-congressional-district-2022` and `soi-county-2022`: sub-state totals

The legacy `db/etl_soi_state.py`, `db/etl_soi_credits.py`,
`db/etl_soi_deductions.py` and `db/etl_soi_income_sources.py` loaders were
retired because they wrote invented values under IRS source URLs. See
[US legacy ETL cleanup](../us-legacy-etl-cleanup.md) for the evidence and for
where each of their series is now published.

---

## Implementation Notes

### CSV Parsing

Historic Table 2 CSV structure (2022):
```
STATE, STATE_NAME, AGI_STUB, N1, A00100, N02650, A02650, ...
```

Where:
- `STATE`: State FIPS code
- `AGI_STUB`: AGI bracket code (1-10+)
- `N1`: Number of returns
- `A00100`: AGI amount
- Field names follow Form 1040 line numbers

### Strata Design

Recommended hierarchy:
```
US All Filers
  -> US Filers AGI $50k-$75k
  -> CA All Filers
       -> CA Filers AGI $50k-$75k
```

Use `parent_id` for rollup validation.

### Validation

Cross-check against:
- Census ACS income estimates
- BEA personal income by state
- CPS ASEC weighted totals

---

## Related Resources

- [IRS Statistics Main Page](https://www.irs.gov/statistics)
- [SOI Tax Stats Overview](https://www.irs.gov/statistics/soi-tax-stats-statistics-of-income)
- [Individual Income Tax State Data Portal](https://www.irs.gov/statistics/soi-tax-stats-individual-income-tax-state-data)
- [NBER SOI ZIP Code Data Mirror](https://www.nber.org/research/data/individual-income-tax-statistics-zip-code-data-soi)

---

## Changelog

- 2024-12-22: Initial documentation created
- 2026-10-12: Replaced the ETL roadmap with the Chronicle package list; the legacy state SOI loaders were retired
