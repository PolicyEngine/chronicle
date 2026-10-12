# Chronicle Storage Architecture

This note is the canonical storage plan for Chronicle while the source-package
harness stabilizes. The detailed agent workflow remains in
`docs/agent-source-package-harness.md`; this document only defines where each
class of Chronicle data belongs.

## Decision Summary

Chronicle stores data in two R2 buckets and one relational build artifact.

`ledger-raw` is the immutable source-byte archive. It stores exact publisher
artifacts as fetched: workbooks, CSVs, PDFs, ZIPs, HTML snapshots, and similar
government-statistics release files. Raw objects are
content-addressed by checksum and should never be overwritten in place.

`ledger-derived` is the reproducible artifact archive. It stores build outputs
that Chronicle can regenerate from raw bytes, package specs, parser code, and build
configuration. Examples include parsed-cell or parsed-row Parquet/JSONL files,
source record outputs, `ledger.db`, per-table JSONL exports, QA reports, Data
Package metadata, and RO-Crate metadata.

`ledger.db` is the queryable relational artifact for a build. It holds the rows
that applications, agents, and downstream systems search and join: source
artifacts, source rows/cells, source records, aggregate facts, aggregate
constraints, concept alignments, lineage edges, build metadata, and R2 location
columns. `build-suite` writes it, `publish-derived` can store it in
`ledger-derived`, and `export-db-tables` writes its tables to JSONL for loading
into other stores.

The deterministic local build remains the authority for source-backed facts.
There is no hosted relational mirror. The Supabase mirror was retired on
2026-10-12 because its default schema does not exist in the configured project
and nothing read the copy it once loaded; see
`docs/supabase-mirror-retirement.md`.

## Ownership Matrix

| Data class | Git/local package | `ledger-raw` R2 | `ledger-derived` R2 | SQLite `ledger.db` |
|------------|-------------------|---------------|-------------------|------------------|
| Source package specs | Authoritative YAML and parser code | No | Optional packaged snapshot | No |
| Raw publisher files | Tiny fixtures only | Authoritative bytes | No | Metadata plus R2 pointer |
| Source manifests | Authoritative checked metadata | No | Optional snapshot | Metadata loaded into tables |
| Parsed source rows/cells | Generated local output | No | Snapshot artifact | Queryable table |
| Source records/facts | Generated local output | No | Snapshot artifact | Queryable table |
| Aggregate constraints | Generated local output | No | Snapshot artifact | Queryable table |
| Build reports and QA | Generated local output | No | Snapshot artifact | Build summary rows |
| Per-table JSONL exports | Generated local output | No | Snapshot artifact | Export source |
| Microcosm active targets | No | No | No | No |

Microcosm active targets are adapter output outside Chronicle core.

## Object Key Conventions

New UK and New Zealand source artifacts use country-organized,
content-addressed keys:

```text
raw/{country}/{source_id}/{package_id}/{year}/{sha256}/{filename}
```

For example, an IRD artifact uses:

```text
raw/nz/ird/ird-working-for-families-statistics-sept-2025/2024/{sha256}/working-for-families-statistics---sept-2025.xlsx
```

The implemented country segments are `nz` and `uk`. US objects deliberately
retain the legacy shape `raw/{source_id}/...`; migrating those keys requires a
separate consumer audit. The fetch and raw-publish commands infer the country
from the package publisher directory. Raw publication refuses to replace a
manifest-recorded key that disagrees with the inferred country path.

New UK and New Zealand derived build artifacts use the same country segment
and build-scoped keys so different builds can coexist and be audited:

```text
derived/{country}/{source_id}/{package_id}/{year}/{build_id}/{artifact_name}
```

Examples:

```text
derived/uk/ons/ons-mye-2024-uk/2024/{build_id}/source_cells.jsonl
derived/nz/ird/ird-working-for-families-statistics-sept-2025/2024/{build_id}/ledger.db
```

Legacy US derived keys likewise remain `derived/{source_id}/...`.

Derived artifacts are reproducible and may be replaced by a new build, but a
specific `{build_id}` path should be immutable once published.

Raw publisher files tracked in Git must each remain below 100 MiB
(`100 * 1024 * 1024` bytes), GitHub's individual-file ceiling. Exact publisher
artifacts at or above that ceiling belong in `ledger-raw`; their checked
manifests retain the source URL, SHA-256, byte size, and R2 location so builds
can fetch and verify them without committing the bytes.

## Relational Artifact Contract

`ledger.db` is the lookup surface for Chronicle, not a place where agents invent
source facts. Every row comes from a deterministic build of checked source
packages.

The artifact exposes:

- source artifact identity: source name, table/file, URL, vintage, extraction
  date, extraction method, checksum, size, and raw R2 bucket/key/URI;
- source rows/cells and source records, including exact source-row and
  source-cell lineage;
- source columns and source-row values, so row-oriented artifacts are queryable
  by raw or normalized column names without JSON scans;
- aggregate facts and aggregate constraints with stable keys, dimensions,
  filters, units, aggregation semantics, labels, and source provenance;
- concept alignments, including source concept, canonical concept, relation,
  authority, legal vintage, and evidence;
- build metadata, validation status, and derived artifact R2 bucket/key/URI.

`source_artifacts` and `build_artifacts` carry R2 bucket, key, and URI columns
for raw and derived objects. A derived object's R2 location is known only after
`publish-derived` uploads it; `--build-artifacts-out` writes those rows.

## Build And Publish Flow

The intended flow is:

1. Register raw source artifacts with `uv run chronicle fetch-artifact`, which
   writes local bytes, records checksums in `manifest.yaml`, and can upload the
   exact bytes to `ledger-raw`. Existing manifest-declared artifacts can be
   checksum-validated, uploaded, and linked with `uv run chronicle publish-raw`.
   Production package specs may omit raw bytes from Git as long as the manifest
   keeps `source_url` and SHA-256 metadata; builds can fill
   `LEDGER_SOURCE_ARTIFACT_CACHE_DIR` by setting
   `LEDGER_SOURCE_ARTIFACT_FETCH=1`. The old `CHRONICLE_`-prefixed environment
   variables remain accepted only as migration fallbacks.
2. Validate and build a source package with `uv run chronicle validate-package` and
   `uv run chronicle build-suite`.
3. Produce local deterministic outputs: parsed rows/cells, source records,
   aggregate facts, `ledger.db`, QA reports, Data Package metadata, and RO-Crate
   metadata.
4. Optionally export `ledger.db` tables to JSONL with
   `uv run chronicle export-db-tables`.
5. Publish derived build outputs to `ledger-derived`:

   ```bash
   uv run chronicle publish-derived \
     --dir /tmp/chronicle-suite \
     --source-id irs_soi \
     --package-id soi-table-1-1 \
     --year 2023 \
     --build-artifacts-out /tmp/chronicle-build-artifacts.jsonl
   ```

There is no hosted load step. Readers can fetch a published `ledger.db` from
`ledger-derived` or build the consumer-fact export
(`uv run chronicle build-consumer-artifact`).

## Non-Goals

A hosted relational mirror, if one is ever reintroduced, should not store raw
binary artifacts. It should point to R2. The conditions for reintroducing one
are in `docs/supabase-mirror-retirement.md`.

Chronicle should not store raw survey or administrative microdata. It reflects
government statistics releases and the provenance needed to audit those
published facts.

R2 should not be the schema authority. It stores bytes and reproducible build
files, while Chronicle code and checked specs define semantics.

Chronicle should not own Microcosm source selection, aging, reconciliation,
activation profiles, or simulator-specific target mappings. Those belong in
Microcosm or thin downstream adapters.
