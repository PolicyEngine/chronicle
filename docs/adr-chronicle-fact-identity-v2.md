# ADR: Chronicle Fact Identity v2

Status: proposed after external ChatGPT Pro review on 2026-05-09

Implementation note: this ADR describes the Chronicle identity model now used by
the `consumer_fact.v1` schema and generated `chronicle.*` key prefixes.

## Decision

Chronicle v2 uses layered identities instead of one overloaded target key:

1. `source_record_key`
   Identifies an immutable publisher record, row, section, cell group, or
   synthetic legacy record within an immutable source release.

2. `aggregate_fact_key`
   Identifies one source-specific aggregate observation from an immutable source
   release.

3. `semantic_fact_key`
   Identifies the source-agnostic statistic represented by that observation.
   This is the bridge for downstream reconciliation and Microcosm target
   selection, but it is not the primary Chronicle source fact key.

4. `concept_alignment_key`
   Identifies a versioned assertion that a source-observed measure maps to a
   canonical concept.

Lineage, labels, evidence notes, layout coordinates, parser versions, build
timestamps, hosted mirror locations, and downstream adapter aliases are not
aggregate fact identity.

## Rationale

Chronicle is a source-data registry and build harness, not the Microcosm target
activation layer. Its primary stable key should answer: "which publisher
observation, from which immutable source release, asserts this aggregate?"

The current key includes the full `Measure` object, including evidence notes and
authority fields. That creates key churn when reviewers improve concept evidence
without changing the source observation. It also risks using row, cell, or table
layout details as fact identity when those should instead be lineage and audit
metadata.

The v2 split keeps source facts stable while still giving Microcosm a clean
semantic handle for source selection, aging, reconciliation, and activation.

## Canonicalization

All v2 keys are deterministic hashes over canonical JSON with explicit
namespaces, for example `chronicle:aggregate_fact:v2`.

Canonical JSON rules:

- sorted object keys;
- sorted dimension, filter, and constraint arrays;
- no null/default fields;
- normalized dates;
- normalized units and scales;
- normalized geography IDs and boundary vintages;
- explicit schema-version namespace.

## Source Identity

`source_release_key` identifies an immutable publisher release:

```text
H("chronicle:source_release:v2", {
  publisher_id,
  source_dataset_id,
  release_id_or_vintage,
  release_revision
})
```

If a publisher changes bytes under the same apparent vintage, Chronicle creates a
new release revision. The same `source_release_key` must never point to
different source content.

`source_artifact_key` identifies a logical artifact in that release:

```text
H("chronicle:source_artifact:v2", {
  source_release_key,
  artifact_id
})
```

Artifact paths, filenames, mirror URIs, and publisher URLs are lookup and audit
metadata. They do not define aggregate fact identity.

## Source Record Identity

`source_record_key` identifies a native or synthetic source record inside a
source release:

```text
H("chronicle:source_record:v2", {
  source_release_key,
  source_frame_key,
  record_kind,
  native_record_key
})
```

`native_record_key` should use the best stable key available:

1. publisher primary key, code, row ID, table ID, or record ID;
2. canonical semantic row key from source columns;
3. coordinate fallback, marked `lineage_stability = "coordinate"`;
4. synthetic legacy key, marked `lineage_stability = "synthetic"`.

Row numbers, sheet ranges, XPath selectors, and cell addresses are locators.
They only become source-record identity when no stronger native key exists.

## Observed Measures And Concept Alignment

Split the current `Measure` object into an observed source measure plus a
separate concept alignment.

`observed_measure_key`:

```text
H("chronicle:observed_measure:v2", {
  source_dataset_key,
  source_measure_id,
  unit_id,
  quantity_kind,
  scale,
  measurement_basis_key
})
```

`concept_alignment_key` is a versioned assertion with:

- `observed_measure_key`;
- `canonical_concept_id`;
- `canonical_measure_key`;
- relation, such as `exact`, `narrower`, `broader`, or `overlaps`;
- authority;
- evidence URL and notes;
- legal vintage and validity window;
- status, such as `proposed`, `reviewed`, `active`, or `rejected`.

Concept evidence, relation text, authority, and alignment status do not affect
`aggregate_fact_key`. Changing the active canonical alignment may change
`semantic_fact_key`, but the source observation remains the same.

If legal vintage materially changes the observed statistic, represent it as a
measurement basis, dimension, or universe constraint. Otherwise keep it in the
concept alignment scope.

## Aggregate Fact Identity

`aggregate_fact_key` identifies a source-specific observation:

```text
H("chronicle:aggregate_fact:v2", {
  source_release_key,
  source_series_key,
  observed_measure_key,
  aggregation_key,
  period_key,
  geography_key,
  entity_key,
  dimension_set_key,
  universe_constraint_set_key
})
```

Include in key material:

- source release;
- source reporting series;
- observed source measure;
- aggregation;
- period;
- geography, including authority and boundary vintage when relevant;
- entity/unit of analysis;
- dimensions;
- universe constraints that define the statistic.

Exclude from key material:

- `source_record_key`;
- `source_row_keys`;
- `source_cell_keys`;
- artifact file path, URL, mirror path, or local path;
- sheet, table layout, row number, column number, or cell address;
- labels and descriptions;
- notes and source display formatting;
- evidence URL and evidence notes;
- parser version and package commit;
- build timestamp;
- value;
- Microcosm target names, source-selection status, simulator aliases, aging,
  reconciliation, and activation state.

If two rows in the same source release produce the same `aggregate_fact_key`
with different values, Chronicle should fail validation. That usually means a missing
dimension, missing methodology/status field, or duplicate source data. Do not
patch the collision by adding `source_record_key` to aggregate identity.

## Semantic Fact Identity

`semantic_fact_key` is the source-agnostic reconciliation handle:

```text
H("chronicle:semantic_fact:v2", {
  canonical_measure_key_or_observed_measure_key,
  aggregation_key,
  period_key,
  geography_key,
  entity_key,
  dimension_set_key,
  universe_constraint_set_key
})
```

Multiple source-specific facts may share a semantic key. That is expected and
belongs to downstream source selection and reconciliation.

## Lineage

Store lineage outside aggregate identity:

```text
AggregateFactLineage {
  aggregate_fact_key,
  role,                 # value | numerator | denominator | period | geography | measure | filter | constraint
  source_record_key,
  source_cell_key,
  source_field_key,
  derivation_expr
}
```

`source_cell_key` is:

```text
H("chronicle:source_cell:v2", {
  source_record_key,
  source_field_key
})
```

Lineage answers "where did this value come from?" It does not answer "what
aggregate fact is this?"

## Values And Hashes

Values are payload, not identity. Store separate hashes:

- `value_hash`: normalized value, value status, uncertainty, and unit payload;
- `lineage_hash`: sorted lineage references and derivation expressions;
- `content_hash`: aggregate key plus value and lineage hashes;
- `build_hash`: source package commit, parser versions, artifact content hashes,
  dependency lock, and build environment.

Parser bug fixes against the same immutable artifact should keep identity stable
and change content/build hashes. If a source release's bytes change, create a
new release revision.

## Constraints

Split constraints into:

- `universe_constraint_set_key`: semantic population/statistic constraints that
  affect identity, such as age range, recipient status, income condition,
  fiscal-year basis, nominal/real basis, or inflation index.
- validation and quality rules: nonnegative checks, total-equals-components
  checks, tolerance checks, confidence interval requirements, and completeness
  checks. These do not affect identity.

The broad `domain` field should normally be metadata. If domain is hiding real
meaning, encode that meaning as source namespace, measure basis, dimension, or
universe constraint.

## Legacy Migration

> **Superseded (2026-10).** The synthetic-legacy migration below was never
> implemented. The legacy target rows were retired instead of migrated: no live
> consumer read them, and most of their values did not trace to publisher bytes. See
> `docs/us-legacy-etl-cleanup.md`. No Chronicle code emits `synthetic_legacy`
> records or `L0_SYNTHETIC` facts.

Legacy direct target rows are compatibility inputs, not production Chronicle facts.

Migration path:

1. Create one source package per legacy loader or legacy target table.
2. Create a synthetic source dataset and release, for example
   `legacy:<loader_name>`.
3. Materialize each legacy target row as a `SourceRecord` with
   `record_kind = "synthetic_legacy"` and
   `lineage_stability = "synthetic"`.
4. Materialize synthetic cells for the value and, where possible, period,
   geography, measure, and dimensions.
5. Compile through the same source-package pathway into `AggregateFact`.
6. Preserve `legacy_fact_key`, loader name, legacy table, and legacy variable.
7. Mark these facts as non-production until real publisher artifacts and
   source-cell lineage replace them.
8. Retire the synthetic package when a real source package reproduces the
   legacy outputs within tolerance.

## Production Lineage Levels

Use explicit lineage quality levels:

- `L0_SYNTHETIC`: legacy or hand-entered compatibility rows, not production.
- `L1_ARTIFACT_ONLY`: publisher release and artifact hash exist, but weak or
  missing record/cell lineage. Draft only.
- `L2_VALUE_CELL_LINEAGE`: immutable release, artifact hash, source record,
  value cell or deterministic derivation, semantic coordinates, hashes, and
  build run. Minimum production level for agent-authored facts.
- `L3_FULL_CELL_LINEAGE`: cell or field lineage for value, measure, period,
  geography, dimensions, filters, and constraints, plus reviewed concept
  evidence and reproducible build manifest.

Agents should not populate production Chronicle facts at scale below `L2`.

## Migration From Current Implementation

1. Add v2 tables and columns alongside current `fact_key` output.
2. Replace raw source fields in fact identity with `source_dataset_key`,
   `source_release_key`, `source_artifact_key`, `source_frame_key`, and
   `source_series_key`. Only release and series affect aggregate identity.
3. Split `Measure` into `ObservedMeasure` and `ConceptAlignment`.
4. Add `aggregate_fact_key`, `semantic_fact_key`, `observed_measure_key`, and
   `active_alignment_key`.
5. Normalize filters and constraints into `dimension_set_key` and
   `universe_constraint_set_key`.
6. Move row and cell references into `AggregateFactLineage`.
7. Add compatibility views for existing downstream consumers.
8. Convert legacy loaders into synthetic source packages, then replace them
   package by package with real publisher lineage.

## Validation Invariants

Builds should fail when:

- a production fact lacks `source_release_key`;
- a production fact lacks value lineage at `L2` or better;
- the same `source_release_key` points to different artifact content;
- the same `aggregate_fact_key` has two values in one build;
- a duplicate key is resolved by adding source-row or source-cell identity
  instead of adding the missing semantic dimension;
- source geography lacks required boundary vintage;
- unit, scale, aggregation, or universe constraints are ambiguous.

## Tests To Add

- Label edits do not change `aggregate_fact_key`.
- Evidence URL or note edits do not change `aggregate_fact_key`.
- Parser version and package commit changes do not change `aggregate_fact_key`.
- Row reorder does not change `source_record_key` when a native row key exists.
- Coordinate-only lineage is marked low stability.
- Source release byte changes force a new release revision.
- Unit, scale, aggregation, geography vintage, and universe-constraint changes
  change aggregate identity.
- Constraint order is canonicalized.
- Duplicate aggregate keys with different values fail validation.
- Concept alignment evidence changes do not change `aggregate_fact_key`.
- Active canonical concept changes may change `semantic_fact_key`.
- Synthetic legacy facts remain non-production until backed by real source
  artifacts and source-cell lineage.
