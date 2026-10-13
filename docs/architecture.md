# Arch Data Architecture

## Overview

Arch is PolicyEngine's source-data foundation for social simulation. It captures
source publications, preserves provenance, and represents published values as
structured, queryable facts. Microplex consumes Arch facts to produce final
calibrated simulation inputs.

This document describes the full data pipeline from source publications to
Microplex target sets and calibrated output. Arch is global at the schema,
validation, and build-harness layer. Jurisdiction source packages such as
`arch-us` and `arch-uk` emit records into that shared contract.

## Repository Boundaries

| Layer | Owns | Does not own |
|-------|------|--------------|
| Arch | Source artifacts, provenance, aggregate facts, constraints, microdata ingestion | Source reconciliation, aging, imputation, active target selection |
| Microplex Targets | Source selection, reconciliation, aging, imputation, active target sets | Source artifact storage and provenance |
| Microplex | Entity model, weights, calibration interfaces, calibrated output | Source ETL and source provenance |
| Jurisdiction source packages | Source-specific parsers and specs that emit Arch records | Forked fact or constraint schemas |
| Jurisdiction simulation packages | Model-specific adapters, variable mappings, target recipes | Source facts |
| PolicyEngine | Policy-facing workflows and analysis tools | Source ETL or calibrated microdata generation |

## Storage Layers

### Object Storage

Source files are immutable and versioned.

```text
sources/
  irs/soi/2023/table_1_2.xlsx          # IRS SOI individual returns
  census/acs/2023/pums_hh.csv          # ACS PUMS households
  census/cps/2024/asec_raw.zip         # CPS ASEC microdata
  bls/cpi/2024/monthly.csv             # CPI monthly series
  usda/snap/2023/qc_data.xlsx          # SNAP QC data
```

### Supabase Schemas

| Schema | Purpose | Example Tables |
|--------|---------|----------------|
| `arch` | Source metadata and lineage | sources, files, content, fetch_log |
| `indices` | Source time series | series, values (CPI, wage growth) |
| `microdata` | Intermediate microdata | cps_asec, acs_pums, synthetic |
| `microplex` | Final calibrated data | households, persons, tax_units |

## Python Namespaces

New code should use the `arch` namespace:

```python
from arch.sources import SourceFile, SourceReference, query_sources
from arch.facts import SourceFact
from arch.microdata import query_cps_asec
from arch.normalization import convert_units
```

The `db` package holds the local source-artifact store and the Supabase client
behind the public `arch` namespace. The legacy `targets` / `strata` /
`stratum_constraints` tables and their loaders were retired (see the README).

Jurisdiction source packages should use short import namespaces and published
distribution names with a PolicyEngine prefix:

```text
repo: PolicyEngine/arch-us
distribution: policyengine-arch-us
import: arch_us
```

They should depend on `policyengine-arch-data` and emit shared `arch` objects
rather than redefining source rows/cells, source-row values, aggregate facts,
aggregate constraints, stable keys, or DB tables.

## Data Flow

```text
source publications
(files, manifests,
 parsed-as-published cells)
      |
      v
arch.sources
(source lineage references)
      |
      v
arch.facts
(structured source claims)
      |
      +------------------------+
      v                        v
arch.normalization        microdata.*
(units, scales,           (typed source
 IDs, source-published     microdata)
 arithmetic)
      |                        |
      v                        |
arch.aggregate_facts          |
(published aggregate          |
 facts)                       |
      |                        |
      +-----------+------------+
                  v
        Microplex Targets
   (selected, reconciled,
    aged active target sets)
                  |
                  v
             microplex.*
          (final calibrated
              microdata)
```

## Source Facts And Microplex Targets

Source ETL should separate Arch aggregate facts from Microplex target composition:

1. Load or parse source publications into source lineage and published cells.
2. Materialize source-backed facts in Arch.
3. Apply representation-only normalization such as unit scale conversion or
   source-published total/share arithmetic.
4. Keep the fact queryable with source and derivation metadata.
5. Let Microplex select, reconcile, age, and activate calibration target sets.

Arch source facts can align source-published concepts to canonical vocabulary
terms. When a legal concept is available from Axiom, Arch should use the Axiom
term as the canonical concept key and keep the publisher's column/series concept
as `source_concept`. For example, SOI adjusted gross income is represented as:

```text
canonical concept: us:statutes/26/62#adjusted_gross_income
source concept:    irs_soi.adjusted_gross_income
relation:          exact
authority:         arch-us
```

This alignment is evidence-bearing metadata, not an Arch dependency on Axiom
runtime behavior. Nonlegal empirical inputs can use shared Arch/common concepts
and later align to Axiom or Microplex where appropriate.

The `arch.normalization` package owns low-assumption representation helpers:

```python
from arch.facts import SourceFact
from arch.normalization import convert_units
from db.schema import DataSource, Jurisdiction

snap_households = SourceFact(
    name="snap_households",
    value=22_323,
    period=2023,
    unit="thousands",
    source=DataSource.USDA_SNAP,
    jurisdiction=Jurisdiction.US,
)

normalized = convert_units(snap_households, 1000, "count")
```

Projection facts from official sources such as CBO, OBR, and ONS can be loaded
as source facts directly. PolicyEngine-owned inflation, aging, projection, or
cross-source reconciliation assumptions belong in Microplex Targets, not Arch.

### Downstream Adapter Aliases

Arch variables should describe source-backed facts, not downstream simulator
variables. If a Microplex or PolicyEngine target cell names the same empirical
quantity differently, the alias belongs in the downstream adapter.

For example, IRS SOI publishes nonnegative income tax liability aggregates.
Arch should preserve that as an SOI liability fact, while a Microplex adapter
may use it to satisfy a model target named `income_tax_positive`. Arch should
not create a duplicate source fact solely to match the model variable name.

This rule also applies in reverse: if a Microplex target cell is really a
survey input, imputed model feature, or source-selection decision rather than a
publisher aggregate, the cell should stay out of Arch until a primary source
fact and its provenance are identified.

## Calibration Pipeline

### 1. Source facts (from the consumer bundle)

`arch build-bundle` writes the source-backed facts to `consumer_facts.jsonl`.
Arch has no separate target table; target selection starts from those facts.

### 2. Variable Mapping

Arch fact concepts are source-linked or canonical vocabulary IDs. They should not
depend on a simulator implementation. Microplex jurisdiction packages map those
target IDs to model variables and entities.

### 3. Target Composition

Microplex Targets owns composition from source-backed inputs to active target
sets:

```python
target_set = microplex.targets.compose(
    inputs=arch_facts,
    target_year=2024,
    reconciliation="scale_states_to_national",
    aging="apply_published_growth_factor",
)
```

Every source choice, reconciliation rule, aging method, and activation rule is
declared and versioned in Microplex, not Arch.

### 4. Hierarchical Constraint Building

Since all weights are at the household level, person-level targets must be
aggregated:

```python
# What we want: count of people aged 18-64 in California
# What we compute: for each household, count matching persons

build_hierarchical_constraint_matrix(
    hh_df=households,      # 18,825 rows
    person_df=persons,     # 48,292 rows
    targets=targets,       # Microplex active target set
)

# Returns: Constraint objects with indicators at household level
# indicator[i] = count of matching persons in household i
```

The key insight: since all persons in a household share the household weight:

```text
sum over HH(hh_weight * count_matching_in_hh) = total_matching_persons
```

### 5. IPF Calibration

Iterative Proportional Fitting adjusts household weights to match all targets:

```python
for iteration in range(max_iter):
    for constraint in constraints:
        current = sum(hh_weight * constraint.indicator)
        ratio = constraint.target_value / current
        hh_weight *= clip(ratio, 0.9, 1.1)

    hh_weight = clip(hh_weight, min_weight, max_weight)
```

### 6. Output (`microplex.*` schema)

```sql
-- microplex.households: Calibrated household weights
SELECT household_id, state_fips, weight, ...
FROM microplex.households;
-- 18,825 rows

-- microplex.persons: Linked to households
SELECT person_id, household_id, age, employment_income, ...
FROM microplex.persons;
-- 48,292 rows
```

## Entity Hierarchy

```text
Household (weight lives here)
├── Tax Unit 1
│   ├── Person A (head)
│   └── Person B (spouse)
└── Tax Unit 2
    └── Person C (dependent filing separately)
```

- Weights are always at household level.
- Person-level targets aggregate count/sum per household.
- Tax-unit-level targets aggregate count/sum per household.
- Household-level targets use a direct indicator.

## Schema Details

### arch.* (Source Lineage)

```sql
arch.sources        -- institution, dataset, url, update_frequency
arch.files          -- r2_key, checksum, source_id, fetched_at
arch.content        -- parsed-as-published text/tables
arch.fetch_log      -- change detection, version history
```

### indices.* (Source Time Series)

```sql
indices.series      -- series_id, name, source, frequency
indices.values      -- series_id, date, value
```

Microplex recipes can reference these source series when they choose an
indexing rule:

```yaml
indexing_rule eitc_inflation:
  series: indices/bls_chained_cpi_u
  base_year: 2015
  rounding: 10
```

### microdata.* (Intermediate)

```sql
microdata.cps_asec       -- processed CPS (cleaned, typed)
microdata.acs_pums       -- processed ACS
microdata.synthetic      -- generated synthetic records
```

### microplex.* (Final Output)

```sql
microplex.households     -- calibrated household records with weights
microplex.persons        -- person records linked to households
microplex.tax_units      -- tax unit records (future)
```
