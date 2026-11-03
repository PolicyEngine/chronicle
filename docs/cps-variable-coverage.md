# CPS ASEC Variable Coverage for Microsimulation

This document summarizes the coverage of CPS ASEC variables for US tax/benefit microsimulation, identifying gaps and their impact on key policy calculations.

## Overview

The Current Population Survey Annual Social and Economic Supplement (CPS ASEC) provides:
- ~170,000 person records annually
- Income data for 15+ sources
- Census-imputed tax calculations
- SPM (Supplemental Poverty Measure) resources

**Key Limitation**: CPS is designed for income and poverty measurement, not tax simulation. Several important tax concepts are missing or underreported.

## Income Variables

### Fully Covered

| CPS Variable | Statute Mapping | IRC Section | Coverage Quality |
|--------------|-----------------|-------------|------------------|
| WSAL_VAL | Wages and salaries | 61(a)(1) | Good |
| SEMP_VAL | Self-employment income | 1402(a) | Good |
| FRSE_VAL | Farm self-employment | 1402(a) | Good |
| INT_VAL | Interest income | 61(a)(4) | Moderate (underreported) |
| DIV_VAL | Dividend income | 61(a)(7) | Moderate (underreported) |
| SS_VAL | Social Security | 86 | Good |
| UC_VAL | Unemployment compensation | 85 | Good |
| SSI_VAL | SSI (non-taxable) | N/A | Good |

### Partially Covered

| CPS Variable | Statute Mapping | IRC Section | Gap Impact |
|--------------|-----------------|-------------|------------|
| CAP_VAL | Capital gains | 1(h) | **Critical** - Severely underreported |
| PNSN_VAL | Pension distributions | 402 | Moderate - Taxable portion unclear |
| ANN_VAL | Annuity income | 72 | Moderate - Exclusion ratio unknown |
| RNT_VAL | Rental income | 469 | Moderate - Net vs gross unclear |

### Missing Variables

| Tax Concept | IRC Section | Impact on Microsim |
|-------------|-------------|-------------------|
| Qualified dividends | 1(h)(11) | High - Affects tax rate calculation |
| IRA distributions | 408 | Medium - Mixed with pension |
| 401(k) contributions | 401(k) | Medium - Reduces taxable income |
| HSA contributions | 223 | Low - Affects AGI |
| Royalty income | 469 | Low - Small population |
| Gambling income | 165(d) | Low - Underreported |

## Capital Gains Gap Analysis

Capital gains represent the largest data quality issue for tax microsimulation:

| Metric | CPS ASEC | IRS SOI 2021 | Gap |
|--------|----------|--------------|-----|
| Total capital gains | ~$50B | ~$1.2T | **96% underreported** |
| Returns with gains | ~2M | ~21M | 90% underreported |
| Top 1% share | Unknown | ~70% | Cannot estimate |

**Impact**:
- Understates income for top brackets
- Biases EITC eligibility (investment income test)
- Affects preferential rate calculations

**Mitigation**: Use IRS Public Use File (PUF) or statistical matching to augment CPS with capital gains data.

## Tax Credit Coverage

### EITC (IRC 32)

| Component | CPS Coverage | Notes |
|-----------|--------------|-------|
| Earned income | Full | WSAL_VAL + SEMP_VAL + FRSE_VAL |
| Investment income test | Partial | CAP_VAL + INT_VAL + DIV_VAL underreported |
| Qualifying children | Derived | Must compute from A_FAMREL, A_AGE, PARENT |
| Filing status | Imputed | Census tax model |

**Validation Target**: IRS SOI shows ~$64B EITC claimed (2021)
**CPS SPM_EITC**: Check alignment with IRS aggregate

### Child Tax Credit (IRC 24)

| Component | CPS Coverage | Notes |
|-----------|--------------|-------|
| Qualifying child count | Derived | Age < 17, relationship, residency |
| CTC amount | Imputed | CTC_CRD variable |
| ACTC amount | Imputed | ACTC_CRD variable |
| Phase-out | Imputed | Based on AGI |

**Validation Target**: IRS SOI shows ~$120B CTC/ACTC claimed (2021)

## Recommended Workflow

### 1. Download and Cache CPS
```bash
python micro/us/census/download_cps.py --year 2024
```

### 2. Convert to PolicyEngine Format
```bash
python scripts/cps_to_policyengine.py --year 2024 --summary
```

### 3. Run Microsimulation
```bash
# In policyengine-us repository
python -m policyengine_us.microsim --input policyengine_input_2024.parquet
```

## Data Quality Recommendations

### High Priority Gaps

1. **Capital Gains**: Augment with PUF statistical match or IRS-based imputations
2. **Investment Income**: Apply SOI-based adjustment factors
3. **Tax Unit Formation**: Validate against filing status distribution

### Medium Priority Gaps

1. **Pension Taxation**: Develop model for taxable portion
2. **Itemized Deductions**: Missing SALT, mortgage interest, charitable
3. **AMT Liability**: Cannot compute from CPS

### Monitoring Metrics

Track these divergence metrics:

| Metric | Acceptable Range | Action if Exceeded |
|--------|------------------|-------------------|
| Total returns | +/- 5% of SOI | Check weight calibration |
| AGI by bracket | +/- 10% | Check income transformations |
| EITC claims | +/- 10% | Check qualifying child derivation |
| EITC amount | +/- 15% | Check earned income calculation |

## Variable YAML Schema

Each CPS variable mapping follows this schema:

```yaml
variable: VARIABLE_NAME
source: cps-asec
entity: person | tax_unit | spm_unit | household
period: year
dtype: money | rate | boolean | category | count

documentation:
  url: "https://www2.census.gov/programs-surveys/cps/techdocs/cpsmar24.pdf"
  section: "Section Name"

concept: descriptive_name
definition: "What this variable measures"

maps_to:
  - jurisdiction: us
    statute: "26 USC section"
    variable: policyengine_variable_name
    coverage: full | partial
    notes: "Mapping notes"

gaps:
  - component: what_is_missing
    impact: high | medium | low
    notes: "Impact description"
```

## File Inventory

### Variable Mappings (71 files)

```
micro/us/census/cps-asec/
├── index.yaml           # Master variable index
├── WSAL_VAL.yaml        # Wages
├── SEMP_VAL.yaml        # Self-employment
├── INT_VAL.yaml         # Interest
├── DIV_VAL.yaml         # Dividends
├── CAP_VAL.yaml         # Capital gains
├── SS_VAL.yaml          # Social Security
├── PNSN_VAL.yaml        # Pensions
├── UC_VAL.yaml          # Unemployment
├── EIT_CRED.yaml        # EITC
├── CTC_CRD.yaml         # CTC
├── AGI.yaml             # Adjusted gross income
└── ... (60+ more)
```

### Conversion Scripts

```
scripts/
└── cps_to_policyengine.py      # Main conversion script

micro/us/
└── census/download_cps.py  # CPS downloader
```
