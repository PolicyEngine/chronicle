# Arch

Arch is PolicyEngine's source-data foundation for social simulation. It captures
source publications, preserves provenance, and represents published values as
structured, queryable facts.

Arch may normalize structure: parse files, type values, declare units and
scales, assign geography and period identifiers, and preserve lineage back to
source artifacts. Arch does not choose among sources, reconcile inconsistent
sources, age values, impute missing data, select active calibration targets, or
apply simulator-specific mappings.

Microplex consumes Arch facts to build simulation datasets and Microplex
Targets. Modeling choices live in Microplex, not Arch.

## Purpose

This repository provides:

- **Sources**: Source file references, retrieval metadata, manifests, checksums,
  and provenance.
- **Facts**: Source-backed claims represented with typed values, units,
  geography, period, source table, and lineage.
- **Normalization**: Low-assumption representation changes such as unit/scale
  conversion and source-published total/share arithmetic.
- **Target inputs**: Source-published aggregates, projections, rates, counts,
  and metadata that Microplex may use to compose calibration targets.
- **Microdata**: Survey and administrative microdata ingestion for CPS, PUF,
  FRS, and related datasets.
- **Jurisdiction loaders**: Source-specific ETL that emits the shared Arch
  schema.

Arch facts are not PolicyEngine's assertion that a source claim is ultimately true.
They are source-backed claims with provenance.

## Boundary

The load-bearing rule:

> Arch may re-express a published value, but may not choose among, reconcile,
> age, impute, or transform published values in ways that change their meaning.

| Layer | Owns | Examples |
|-------|------|----------|
| Arch Sources | Source artifacts and provenance | URLs, checksums, source files, parsed tables/cells |
| Arch Facts | Structured source claims | SOI cells, ACS estimates, CPI values, CBO-published projections |
| Arch Normalization | Representation changes | Unit scales, typed values, geography/date identifiers |
| Arch Target Inputs | Source facts shaped for calibration | SOI EITC totals, CBO baselines, source-published growth factors |
| Microplex Targets | Model-ready target sets | Source selection, reconciliation, aging, activation profiles |

The storage split is documented in
[`docs/storage-architecture.md`](docs/storage-architecture.md): `arch-raw`
stores immutable source bytes, `arch-derived` stores reproducible build
artifacts, and Supabase/Postgres hosts the queryable relational Arch registry
mirrored from accepted builds.

## Repository Model

Arch is global at the schema, validation, database, and build-harness layer.
Jurisdiction packages are modular source packages that emit the same Arch
objects.

```text
GitHub repositories:
  PolicyEngine/arch-data # Core schema, validation, harness, DB schema
  PolicyEngine/arch-us   # US source parsers/specs; emits Arch records
  PolicyEngine/arch-uk   # UK source parsers/specs; emits Arch records

Python distributions:
  policyengine-arch-data
  policyengine-arch-us
  policyengine-arch-uk

Python imports:
  arch
  arch_us
  arch_uk
```

The current `arch.jurisdictions.us` package is an in-repo prototype while the
core schema is still moving. Once the Arch contract stabilizes, US and UK
source packages should move to `arch-us` and `arch-uk`. They must not fork
`AggregateConstraint`, source-row/source-cell lineage, stable keys, validation, or the
relational DB schema.

## Structure

```text
arch/
├── arch/                    # Public Arch namespace
│   ├── sources/             # Source lineage helpers
│   ├── facts/               # Source-backed facts
│   ├── normalization/       # Low-assumption representation helpers
│   ├── targets/             # Target input schema, client, loaders
│   ├── microdata/           # Microdata registry, ingestion, queries
│   ├── jurisdictions/       # Temporary in-repo jurisdiction source prototypes
├── db/                      # SQLModel persistence and source loaders
│   ├── schema.py            # SQLModel: Target, Stratum, StratumConstraint
│   ├── supabase_client.py   # Supabase client helpers
│   └── etl_*.py             # Source-specific ETL pipelines
├── micro/                   # Microplex consumers of Arch records
├── calibration/             # Calibration target adapters and constraints
├── data/                    # Cached data files
└── docs/                    # Architecture and source documentation
```

New code should prefer `arch.sources`, `arch.facts`, `arch.normalization`,
`arch.targets`, and `arch.microdata`. Microplex-specific target composition
and calibration code belongs under `micro/`.

## Quick Start

### 1. Install

```bash
pip install policyengine-arch-data
# Or for development:
git clone https://github.com/PolicyEngine/arch-data arch
cd arch
pip install -e ".[dev]"
```

### 2. Initialize and Load Legacy Target Inputs

```bash
arch init
arch load soi --years 2021
arch stats
```

### 3. Validate Fixture Facts

The standalone Arch fact harness validates JSONL aggregate facts and emits a
JSON report with fact counts, QA counts, warnings, and validation errors:

```bash
uv run python -m arch.harness validate-facts --fixture
# Equivalent when the console script is installed:
uv run arch validate-facts --fixture
```

To build a tiny source-backed fixture from the packaged IRS SOI Table 1.1
workbook and validate it:

```bash
uv run arch build-fixture-facts soi-table-1-1 --year 2023 --output /tmp/arch-soi-facts.jsonl
uv run arch validate-facts --input /tmp/arch-soi-facts.jsonl
```

To preserve the whole used range of that workbook as source-cell records before
semantic fact construction:

```bash
uv run arch build-source-cells soi-table-1-1 --year 2023 --output /tmp/arch-soi-cells.jsonl
uv run arch validate-source-cells --input /tmp/arch-soi-cells.jsonl
```

Delimited source packages should preserve the whole file as row records before
selecting facts. For example, the BEA NIPA flat file pilot parses all source
rows, then emits two selected pension contribution facts:

```bash
uv run arch build-source-rows bea-nipa-pension-contributions --year 2022 --output /tmp/arch-bea-rows.jsonl
uv run arch validate-source-rows --input /tmp/arch-bea-rows.jsonl
```

ZIP archives with rectangular publisher files use the same row-first contract.
The CMS Marketplace OEP state-level package preserves the raw CMS ZIP, parses
its CSV member into source rows/cells, and emits state-level enrollment and
APTC facts:

```bash
uv run arch validate-package cms-aca-oep-state-level --year 2024
uv run arch build-suite cms-aca-oep-state-level --year 2024 --out /tmp/arch-cms-aca-oep-2024 --replace
```

To build a relational Arch DB artifact with aggregate facts, first-class
constraints, source-cell lineage, and source-row lineage when available:

```bash
uv run arch build-db --fixture --db /tmp/arch-fixture.db --replace
```

This writes queryable Arch-owned tables such as `source_rows`,
`source_columns`, `source_row_values`, `source_cells`, `aggregate_facts`,
`aggregate_constraints`, `concept_alignments`, `fact_source_cells`, and
`fact_source_rows`. The DB is a deterministic build artifact from source
manifests, parsers, and checked-in specs; hosted Postgres/Supabase should mirror
this schema rather than become the unreproducible origin of source-backed facts.

To run the source-package build suite agents should target, build the source
rows/cells, source-region spec, selector report, aggregate facts, DB artifact,
and JSON reports into one output directory:

```bash
uv run arch build-suite soi-table-1-1 --year 2023 --out /tmp/arch-suite --replace
```

The same command accepts a declarative package directory. This is the preferred
agent authoring surface:

```bash
uv run arch build-suite packages/irs_soi/table_1_1 --year 2023 --out /tmp/arch-suite --replace
```

The first UK source packages use the OBR March 2026 EFO receipts and
expenditure workbooks and emit 2025-26 fiscal-year aggregate facts:

```bash
uv run arch validate-package obr-efo-receipts --year 2025
uv run arch build-suite obr-efo-receipts --year 2025 --out /tmp/arch-obr-efo-receipts-2025 --replace
uv run arch validate-package obr-efo-expenditure --year 2025
uv run arch build-suite obr-efo-expenditure --year 2025 --out /tmp/arch-obr-efo-expenditure-2025 --replace
uv run arch validate-package slc-student-support-england-2025 --year 2025
uv run arch build-suite slc-student-support-england-2025 --year 2025 --out /tmp/arch-slc-student-support-england-2025 --replace
```

The first ZIP-backed PE migration package is CMS Marketplace OEP state-level
PUF:

```bash
uv run arch validate-package cms-aca-oep-state-level --year 2024
uv run arch build-suite cms-aca-oep-state-level --year 2024 --out /tmp/arch-cms-aca-oep-2024 --replace
```

This writes:

```text
<output-dir>/
  datapackage.json
  ro-crate-metadata.json
  source_rows.jsonl
  source_cells.jsonl
  source_regions.jsonl
  facts.jsonl
  consumer_facts.jsonl
  arch.db
  reports/
    source_rows.json
    source_cells.json
    source_regions.json
    selectors.json
    source_records.json
    facts.json
    consumer_facts.json
    concept_alignments.json
    database.json
    agent_acceptance.json
    build_summary.json
```

Agent-authored source packages should be judged by these reports. They should
add or update source manifests, parsers, selector specs, and source-record
specs; they should not hand-edit DB artifacts or core schemas.
The quick gate is `reports/agent_acceptance.json`, which checks raw R2 links,
full-document parsing, fact provenance, source-cell/source-row lineage,
expected first-class constraints, row-backed filter/constraint evidence,
concept alignment evidence, Axiom concept validation status, and stage-report
validity.

To build the downstream integration artifact Microplex should consume, merge
available source-package suites for a year into one bundle:

```bash
uv run arch build-bundle --year 2023 --out /tmp/arch-us-2023 --replace
```

This writes a root `consumer_facts.jsonl`, `source_packages.json`,
`coverage.json`, and `reports/build_bundle.json`. Source-specific suite outputs
remain nested under `sources/<source-package>/`. The bundle coverage report
includes counts by source, geography, entity, period, observed measure, and
concept plus duplicate `aggregate_fact_key` and `semantic_fact_key` diagnostics.
The row-level downstream contract is `consumer_facts.jsonl`; the other bundle
files are diagnostic reports for gating and review. Consumer-contract rows must
carry canonical constraints explicitly in `universe_constraints`; source-layout
`dimensions` are metadata and are not target constraints.

Builds without an Axiom CLI still pass when the source package is otherwise
valid, but `agent_acceptance.json` warns with
`concept_alignment_validation_skipped`. For strict agent review, require every
canonical concept to resolve through Axiom:

```bash
uv run arch build-suite packages/irs_soi/table_1_1 \
  --year 2023 \
  --out /tmp/arch-suite \
  --replace \
  --axiom-cli axiom \
  --axiom-root ../rules-us \
  --require-axiom-validation
```

For the faster authoring loop before running the full build suite, validate a
package directory directly:

```bash
uv run arch validate-package packages/irs_soi/table_1_1 --year 2023
```

To start a new package from the constrained YAML template:

```bash
uv run arch scaffold-package --source-id irs_soi --package-id soi-table-1-2 \
  --out packages/irs_soi/table_1_2 \
  --source-table "Publication 1304 Table 1.2" \
  --resource-directory data/irs_soi/table_1_2
```

Raw source artifacts should be content-addressed and checksum-locked before a
package spec depends on them. Tiny fixtures can stay in Git, but production raw
files should live in private Cloudflare R2 buckets, with `manifest.yaml` and the
hosted database carrying the queryable provenance:

```bash
# One-time after creating the PolicyEngine Cloudflare account and running
# `npx wrangler login`:
uv run arch bootstrap-r2 --raw-bucket arch-raw --derived-bucket arch-derived

# Fetch/register a source artifact, write db/data/.../manifest.yaml, and upload
# the exact bytes to R2 when Wrangler is authenticated:
uv run arch fetch-artifact \
  --url https://www.irs.gov/pub/irs-soi/23in12ms.xls \
  --source-id irs_soi \
  --package-id soi-table-1-2 \
  --year 2023 \
  --out-dir db/data/irs_soi/table_1_2 \
  --source-page https://www.irs.gov/statistics/soi-tax-stats-individual-income-tax-returns-complete-report-publication-1304-basic-tables-part-1 \
  --table "Publication 1304 Table 1.2" \
  --upload-r2

# Audit local manifests and checksums:
uv run arch inventory-artifacts --root db/data

# Upload all existing manifest-declared local artifacts to arch-raw and write
# storage.r2 metadata back into the manifests:
uv run arch publish-raw --root db/data
```

To coordinate broad PE source migration without jumping straight to semantic
target construction, generate an agent batch plan from the PE manifest:

```bash
uv run arch plan-pe-sources \
  --manifest docs/pe-us-source-manifest.csv \
  --out docs/pe-us-source-agent-plan.json \
  --markdown docs/pe-us-source-agent-plan.md
```

The plan marks existing source packages, primary-source lookup work,
fetch/register work, source-cell scaffolds, and repair items. Fetch hints
include `--upload-r2`; semantic target work still requires a package to pass
`build-suite`. Aggregators such as FRED stay in the migration plan only as
publisher-source lookup clues; they should not become canonical Arch source
artifacts or target provenance.

R2 owns the immutable bytes. Arch manifests and Supabase/Postgres mirrors own
metadata such as source URL, checksum, size, vintage, extraction date, and R2
key. Source-package parsers still read deterministic local/package resources,
so builds remain reproducible without making hosted storage the source of
schema truth.

The same build-suite path also supports the SOI Table 1.4 wage pilot:

```bash
uv run arch build-suite soi-table-1-4 --year 2023 --out /tmp/arch-suite-1-4 --replace
uv run arch build-suite packages/irs_soi/table_1_4 --year 2023 --out /tmp/arch-suite-1-4 --replace
```

To prepare the deterministic SQLite artifact for a hosted Supabase/Postgres
mirror, export each relational table to JSONL plus a manifest:

```bash
uv run arch export-db-tables --db /tmp/arch-suite/arch.db --out /tmp/arch-mirror --replace
```

To publish the deterministic build outputs to the `arch-derived` R2 bucket:

```bash
uv run arch publish-derived \
  --dir /tmp/arch-suite \
  --source-id irs_soi \
  --package-id soi-table-1-1 \
  --year 2023 \
  --build-artifacts-out /tmp/arch-build-artifacts.jsonl
```

The Supabase schema for this mirror lives at
`supabase/migrations/20260504_arch_bronze.sql`. Raw government spreadsheets are
mirrored as artifact metadata plus one row per parsed cell, not one tidy table
per sheet. Typed rectangular microdata can still use separate raw microdata
tables.

After the migration is applied and the `arch` schema is exposed through the
Supabase Data API, accepted mirror exports can be upserted with:

```bash
uv run arch load-supabase-mirror \
  --dir /tmp/arch-mirror \
  --build-artifacts /tmp/arch-build-artifacts.jsonl
```

Use `--dry-run` first to validate JSONL row counts and file coverage without
writing to Supabase.

Arch facts keep source concepts and canonical concepts separately. For example,
the SOI Table 1.1 adjusted gross income column is preserved as
`irs_soi.adjusted_gross_income`, while the canonical concept is
`us:statutes/26/62#adjusted_gross_income` with an `exact` alignment assertion.
The SOI Table 1.4 wage amount column is preserved as `irs_soi.total_wages`,
while the canonical concept is `us:statutes/26/62#input.wages` with a
`broad_match` assertion because Axiom currently treats wages as an inferred
input under IRC section 62 rather than an exact statutory term.
This lets Arch share vocabulary with Axiom legal terms without importing Axiom
runtime code.

To validate source-to-canonical concept alignments against an installed Axiom
concept CLI outside the full suite:

```bash
uv run arch validate-concept-alignments --input /tmp/arch-soi-facts.jsonl \
  --axiom-cli axiom \
  --axiom-root ../rules-us
```

The command emits JSON with the alignments checked, validation errors, and
warnings. If the Axiom CLI is omitted, Arch still reports alignment metadata and
warns that external concept validation was skipped. `build-suite` accepts the
same `--axiom-cli` and `--axiom-root` flags, plus
`--require-axiom-validation` when skipped concept checks should fail agent
acceptance.

### 4. Run Arch Explorer

Arch Explorer is a Next/Tailwind app that reads the fixture fact JSONL and
source-cell JSONL, then shows aggregate facts, source-cell lineage, and
consumer-contract fields:

```bash
cd explorer
npm install
npm run dev -- --port 3090
```

Then open `http://localhost:3090`.

By default, the workbench reads the current local suite outputs at
`/tmp/arch-us-2023-parity/sources/*` and
`/tmp/arch-soi-historic-table-2-2022`. To point it at another build, set:

```bash
ARCH_EXPLORER_DATA_DIRS=/tmp/arch-build-a,/tmp/arch-build-b npm run dev -- --port 3090
```

### 5. Query Target Inputs in Python

```python
from arch.targets import DataSource, Target, TargetType
from calibration.targets import get_targets

target_inputs = get_targets(
    jurisdiction="us",
    year=2021,
    sources=["irs-soi"],
)
```

### 6. Query Microdata

```python
from arch.microdata import query_cps_asec

persons = query_cps_asec(year=2024, table_type="person", limit=10_000)
```

## Target Input Schema

Target inputs use a three-table schema:

- **strata**: Population subgroups, such as California filers with AGI between
  $50k and $75k.
- **stratum_constraints**: Rules defining each stratum.
- **targets**: Source-published aggregate values linked to strata.

These are inputs to Microplex target composition. Microplex owns the active,
reconciled, aged target sets used for calibration.

## Arch Facts And Microplex Targets

Source facts should be structurally normalized before Microplex considers them
as calibration target candidates.
Normalization is about representation, not modeling: units, scales, typed
values, geography IDs, period IDs, and same-source arithmetic where the source
publishes the total/share relationship.

Inflation, aging, cross-source reconciliation, source selection, and target
activation belong in Microplex Targets unless the source itself publishes the
adjusted or projected series.

```python
from arch.facts import SourceFact
from arch.targets import DataSource, Jurisdiction, TargetType
from arch.normalization import as_target, convert_units

fact = SourceFact(
    name="snap_households",
    value=22_323,
    period=2023,
    unit="thousands",
    source=DataSource.USDA_SNAP,
    jurisdiction=Jurisdiction.US,
)

target_input = as_target(
    convert_units(fact, 1000, "count"),
    target_type=TargetType.COUNT,
    stratum_name="US SNAP Households",
)
```

## Current Coverage

### Microdata

| Source | Variables | Description |
|--------|-----------|-------------|
| US CPS ASEC | 78 | Census household survey |
| US IRS PUF | 33 | Tax return sample |
| UK FRS | 29 | DWP household survey |

### Aggregate Facts And Target Inputs

| Source | Coverage | Description |
|--------|----------|-------------|
| IRS SOI | National, state, AGI brackets | Tax return aggregates |
| Census | Demographics, poverty, districts | Population statistics |
| BLS | Labor market and price data | Employment and index series |
| CBO | Federal projections | Budget and economic projections |
| SSA/SSI | National and state programs | Social Security data |
| SNAP | State-level | Food assistance |
| CMS | Medicaid and ACA enrollment | Health coverage |
| HMRC/ONS/OBR | UK tax, population, projections | UK official statistics |

## Boundaries

- **Arch** owns source data, provenance, source facts, aggregate facts, and
  microdata ingestion.
- **Microplex Targets** owns source selection, reconciliation, aging, imputation,
  active target sets, and calibration profiles.
- **Microplex** owns simulation interfaces, entity modeling, weights, and
  calibration execution.
- **Jurisdiction source packages** such as `arch-us` and `arch-uk` own
  source-specific parsers and specs that emit shared Arch records.
- **Jurisdiction simulation packages** such as `microplex-us` own
  simulation-specific variable mappings and target recipes.
- **PolicyEngine** owns policy-facing tools and analysis workflows.

## Related Repositories

- [microplex](https://github.com/PolicyEngine/microplex) - Core microsimulation
  abstractions and calibration interfaces.
- [microplex-us](https://github.com/PolicyEngine/microplex-us) - US-specific
  simulation adapters and calibration profiles.

## Witnessed observation journal

The `codex/thesis-ledger-facts` branch carries an append-only, externally
witnessed observation ledger: every append lands with a chained release
manifest, dual RFC 3161 receipts, and an Ed25519 producer signature,
verified by a gate that runs from the base commit's hash-locked
environment. Verification machinery is consumed from the `receipt`
package with this repository's trust pins committed in
`scripts/receipt_pins.py`; see `releases/README.md` (immutable
post-genesis, like everything under `releases/`) for the schema, offline
verification procedure, and security limits.

Each release manifest is additionally anchored in Bitcoin through
OpenTimestamps: `ots/<stem>.json.ots` timestamps the manifest's exact
bytes, so the anteriority of the journal state it commits to does not
depend on trusting this repository's git history. A scheduled job stamps
new manifests and upgrades pending proofs daily. See `ots/README.md` for
what the proofs do and do not establish and the two-command verification
procedure.
