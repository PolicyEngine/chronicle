"""Canonical Arch aggregate facts and validation.

This module is intentionally independent of Microplex. It defines source-backed
aggregate facts, deterministic fact keys, human-readable labels, and
schema-level validation for Arch fact sets.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

Scalar = str | int | float | bool | None

ALLOWED_PERIOD_TYPES = {
    "calendar_year",
    "tax_year",
    "fiscal_year",
    "month",
    # Sub-monthly and quarterly publisher prints recorded by the Thesis
    # resolver (e.g. DOL UI weekly claims, BEA quarterly GDP).
    "quarter",
    "week_ending",
}
ALLOWED_GEOGRAPHY_LEVELS = {
    "country",
    "region",
    "state",
    "county",
    "congressional_district",
    "state_legislative_district_upper",
    "state_legislative_district_lower",
    "parliamentary_constituency",
    "local_authority",
    "metro_area",
    "zip_code",
    "statistical_scope",
}
ALLOWED_ENTITIES = {
    "person",
    "household",
    "tax_unit",
    "family",
    "benefit_unit",
    "return",
    "pension_plan",
    "government",
    "dwelling",
    "institutional_sector",
    # Macro publisher prints (GDP growth, industrial production, price
    # indexes) describe the whole economy, not a person-level population.
    "economy",
}
ALLOWED_AGGREGATIONS = {
    "count",
    "sum",
    "mean",
    "median",
    "rate",
    "ratio",
    "share",
    # A published series value taken as printed (policy rates, index
    # levels, claims counts) — the publisher's own aggregate, not ours.
    "level",
}
ALLOWED_CONSTRAINT_OPERATORS = {"==", "!=", ">", ">=", "<", "<=", "in"}
ALLOWED_CONCEPT_RELATIONS = {
    "exact",
    "broad_match",
    "narrow_match",
    "approximate",
    "source_label",
}
FACT_KEY_PREFIX = "arch.fact.v1"


@dataclass(frozen=True)
class PeriodDimension:
    """Fact period identity."""

    type: str
    value: int | str


@dataclass(frozen=True)
class GeographyDimension:
    """Fact geography identity.

    ``name`` is human-readable metadata and is excluded from stable keys.
    """

    level: str
    id: str
    vintage: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class EntityDimension:
    """Unit/entity measured by the fact."""

    name: str
    role: str | None = None


@dataclass(frozen=True)
class Measure:
    """Simulator-neutral fact measure."""

    concept: str
    unit: str
    source_concept: str | None = None
    concept_relation: str | None = None
    concept_authority: str | None = None
    concept_evidence_url: str | None = None
    concept_evidence_notes: str | None = None
    legal_vintage: str | None = None


@dataclass(frozen=True)
class Aggregation:
    """How source observations are aggregated into the fact value."""

    method: str
    count_entity: str | None = None
    denominator: str | None = None


@dataclass(frozen=True)
class SourceProvenance:
    """Source identity and extraction provenance for a fact."""

    source_name: str | None
    source_table: str | None = None
    source_file: str | None = None
    url: str | None = None
    vintage: str | None = None
    extracted_at: str | None = None
    extraction_method: str | None = None
    method_notes: str | None = None
    source_sha256: str | None = None
    source_size_bytes: int | None = None
    raw_r2_bucket: str | None = None
    raw_r2_key: str | None = None
    raw_r2_uri: str | None = None
    # The pair a row stored in base units was recorded as, such as 7.716 in
    # millions for a value of 7716000 in count. A row in a unit with no scale
    # word holds neither.
    recorded_value: float | None = None
    recorded_unit: str | None = None


def drop_absent_recorded_pair(source: dict[str, Any]) -> None:
    """Remove the recorded pair keys a source mapping does not hold.

    Serialized facts and build hashes read a row with no pair exactly as they
    did before ``SourceProvenance`` held one.
    """

    for key in ("recorded_value", "recorded_unit"):
        if source[key] is None:
            del source[key]


@dataclass(frozen=True)
class AggregateConstraint:
    """One semantic filter that scopes an aggregate fact."""

    variable: str
    operator: str
    value: Scalar
    unit: str | None = None
    role: str = "filter"
    label: str | None = None


@dataclass(frozen=True)
class SourceRecordLayout:
    """Non-semantic layout metadata for rebuilding source tables.

    These fields help humans and tools reconstitute compact source tables from
    atomic facts. They are intentionally excluded from stable fact keys.
    """

    record_set_id: str | None = None
    record_set_spec_id: str | None = None
    record_set_spec_hash: str | None = None
    groupby_dimension: str | None = None
    groupby_value_id: str | None = None
    groupby_value_label: str | None = None
    groupby_ordinal: int | None = None
    measure_id: str | None = None
    measure_label: str | None = None
    measure_ordinal: int | None = None
    source_row_id: str | None = None
    source_column_id: str | None = None
    table_record_kind: str | None = None
    parent_record_set_id: str | None = None
    total_record_id: str | None = None


@dataclass(frozen=True)
class AggregateFact:
    """Canonical Arch published aggregate fact."""

    value: int | float | str | Decimal
    period: PeriodDimension
    geography: GeographyDimension
    entity: EntityDimension
    measure: Measure
    aggregation: Aggregation
    source: SourceProvenance
    filters: dict[str, Scalar] = field(default_factory=dict)
    domain: str = "all"
    label: str | None = None
    source_record_id: str | None = None
    source_cell_keys: tuple[str, ...] = ()
    source_row_keys: tuple[str, ...] = ()
    constraints: tuple[AggregateConstraint, ...] = ()
    layout: SourceRecordLayout | None = None


@dataclass(frozen=True)
class ValidationIssue:
    """One fact validation issue."""

    code: str
    message: str
    field: str | None = None
    fact_key: str | None = None
    fact_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable issue."""
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}


@dataclass(frozen=True)
class ValidationReport:
    """Validation and QA summary for a fact set."""

    fact_count: int
    counts: dict[str, dict[str, int]]
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...] = ()

    @property
    def valid(self) -> bool:
        """Whether the fact set has no validation errors."""
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report."""
        return {
            "valid": self.valid,
            "fact_count": self.fact_count,
            "counts": self.counts,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }


def build_fact_key(fact: AggregateFact) -> str:
    """Build a stable key from fact schema fields, not human labels."""
    payload = _canonical_key_payload(fact)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{FACT_KEY_PREFIX}:{digest}"


def build_label(fact: AggregateFact) -> str:
    """Build a human-readable label from fact metadata."""
    concept = _humanize(fact.measure.concept)
    aggregation = _humanize(fact.aggregation.method)
    entity = _humanize(fact.entity.name)
    period = f"{fact.period.value} {_humanize(fact.period.type)}"
    geography = fact.geography.name or fact.geography.id
    source = _source_label(fact.source)

    label = f"{geography} {period} {aggregation} {concept} for {entity}"
    if fact.filters:
        label = f"{label} ({_format_filters(fact.filters)})"
    if source:
        label = f"{label} [{source}]"
    return label


def build_aggregate_constraints(
    fact: AggregateFact,
) -> tuple[AggregateConstraint, ...]:
    """Build first-class aggregate constraints from fact metadata.

    Source loaders can provide explicit constraints. For the current fixture
    slice, older fact records carry SOI bracket boundaries in ``filters``;
    this function lifts those into queryable semantic constraints.
    """
    if fact.constraints:
        return fact.constraints

    constraints: list[AggregateConstraint] = []
    filing_status = fact.filters.get("filing_status")
    if filing_status not in (None, "all"):
        constraints.append(
            AggregateConstraint(
                variable="irs_soi.filing_status",
                operator="==",
                value=filing_status,
                label="Filing status",
            )
        )

    lower = fact.filters.get("agi_lower_usd")
    if lower is not None:
        constraints.append(
            AggregateConstraint(
                variable="irs_soi.adjusted_gross_income",
                operator=">=",
                value=lower,
                unit="usd",
                label="Adjusted gross income lower bound",
            )
        )

    upper = fact.filters.get("agi_upper_usd")
    if upper is not None:
        constraints.append(
            AggregateConstraint(
                variable="irs_soi.adjusted_gross_income",
                operator="<",
                value=upper,
                unit="usd",
                label="Adjusted gross income upper bound",
            )
        )

    handled_filters = {
        "agi_lower_usd",
        "agi_upper_usd",
        "filing_status",
        "income_range",
    }
    child_count = fact.filters.get("eitc_child_count")
    if child_count not in (None, "all"):
        if child_count == "3plus":
            constraints.append(
                AggregateConstraint(
                    variable="us.tax.earned_income_credit_qualifying_children",
                    operator=">=",
                    value=3,
                    unit="count",
                    label="EITC qualifying children",
                )
            )
        else:
            constraints.append(
                AggregateConstraint(
                    variable="us.tax.earned_income_credit_qualifying_children",
                    operator="==",
                    value=child_count,
                    unit="count",
                    label="EITC qualifying children",
                )
            )
        handled_filters.add("eitc_child_count")

    for key, value in sorted(fact.filters.items()):
        if key in handled_filters or value in (None, "all"):
            continue
        constraints.append(
            AggregateConstraint(
                variable=key,
                operator="==",
                value=value,
                label=_humanize(key),
            )
        )

    return tuple(constraints)


def validate_fact(fact: AggregateFact) -> tuple[ValidationIssue, ...]:
    """Validate one aggregate fact."""
    errors: list[ValidationIssue] = []

    _require_nonempty(errors, fact.measure.concept, "measure.concept")
    _require_nonempty(errors, fact.measure.unit, "measure.unit")
    _validate_measure_concept_alignment(errors, fact.measure)
    _require_nonempty(errors, fact.domain, "domain")

    if fact.period.type not in ALLOWED_PERIOD_TYPES:
        errors.append(
            _issue(
                "malformed_period",
                f"Unsupported period type: {fact.period.type!r}",
                "period.type",
            )
        )
    if isinstance(fact.period.value, str) and not fact.period.value.strip():
        errors.append(
            _issue("missing_period", "Period value is required", "period.value")
        )

    if fact.geography.level not in ALLOWED_GEOGRAPHY_LEVELS:
        errors.append(
            _issue(
                "malformed_geography",
                f"Unsupported geography level: {fact.geography.level!r}",
                "geography.level",
            )
        )
    _require_nonempty(errors, fact.geography.id, "geography.id")

    if fact.entity.name not in ALLOWED_ENTITIES:
        errors.append(
            _issue(
                "malformed_entity",
                f"Unsupported entity: {fact.entity.name!r}",
                "entity.name",
            )
        )

    if fact.aggregation.method not in ALLOWED_AGGREGATIONS:
        errors.append(
            _issue(
                "malformed_aggregation",
                f"Unsupported aggregation method: {fact.aggregation.method!r}",
                "aggregation.method",
            )
        )
    if (
        fact.aggregation.count_entity is not None
        and fact.aggregation.count_entity not in ALLOWED_ENTITIES
    ):
        errors.append(
            _issue(
                "malformed_aggregation",
                "Unsupported aggregation count entity: "
                f"{fact.aggregation.count_entity!r}",
                "aggregation.count_entity",
            )
        )

    _validate_value(errors, fact.value)
    _validate_filters(errors, fact.filters)
    _validate_constraints(errors, fact.constraints)
    _validate_provenance(errors, fact.source)

    return tuple(errors)


def validate_facts(facts: list[AggregateFact]) -> ValidationReport:
    """Validate a fact set and return QA counts plus issues."""
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    key_indices: dict[str, list[int]] = {}

    for index, fact in enumerate(facts):
        key = build_fact_key(fact)
        key_indices.setdefault(key, []).append(index)
        for issue in validate_fact(fact):
            errors.append(
                ValidationIssue(
                    code=issue.code,
                    message=issue.message,
                    field=issue.field,
                    fact_key=key,
                    fact_index=index,
                )
            )
        if not fact.label:
            warnings.append(
                ValidationIssue(
                    code="missing_label",
                    message="Fact has no human-readable label metadata",
                    field="label",
                    fact_key=key,
                    fact_index=index,
                )
            )

    for key, indices in key_indices.items():
        if len(indices) > 1:
            errors.append(
                ValidationIssue(
                    code="duplicate_key",
                    message=f"Duplicate fact key appears at indices {indices}",
                    fact_key=key,
                    fact_index=indices[0],
                )
            )

    return ValidationReport(
        fact_count=len(facts),
        counts=fact_counts(facts),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def fact_counts(facts: list[AggregateFact]) -> dict[str, dict[str, int]]:
    """Count facts across the main QA dimensions."""
    return {
        "by_source": _counter_dict(
            fact.source.source_name or "missing" for fact in facts
        ),
        "by_geography": _counter_dict(
            f"{fact.geography.level}:{fact.geography.id}" for fact in facts
        ),
        "by_entity": _counter_dict(fact.entity.name for fact in facts),
        "by_period": _counter_dict(
            f"{fact.period.type}:{fact.period.value}" for fact in facts
        ),
        "missing_labels": {"count": sum(1 for fact in facts if not fact.label)},
        "missing_provenance": {
            "count": sum(1 for fact in facts if _has_missing_provenance(fact))
        },
        "missing_lineage": {
            "count": sum(
                1
                for fact in facts
                if not fact.source_cell_keys and not fact.source_row_keys
            )
        },
    }


def _canonical_key_payload(fact: AggregateFact) -> dict[str, Any]:
    payload = {
        "period": asdict(fact.period),
        "geography": {
            "level": fact.geography.level,
            "id": fact.geography.id,
            "vintage": fact.geography.vintage,
        },
        "entity": asdict(fact.entity),
        "measure": asdict(fact.measure),
        "aggregation": asdict(fact.aggregation),
        "domain": fact.domain,
        "filters": {
            key: fact.filters[key]
            for key in sorted(fact.filters)
            if fact.filters[key] is not None
        },
        "source": {
            "source_name": fact.source.source_name,
            "source_table": fact.source.source_table,
            "source_file": fact.source.source_file,
            "vintage": fact.source.vintage,
        },
    }
    if fact.constraints:
        payload["constraints"] = [asdict(constraint) for constraint in fact.constraints]
    return payload


def _validate_value(errors: list[ValidationIssue], value: Any) -> None:
    if isinstance(value, Decimal):
        return
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        errors.append(_issue("malformed_value", "Fact value must be scalar", "value"))
        return
    if isinstance(value, str) and not value.strip():
        errors.append(_issue("missing_value", "Fact value is required", "value"))


def _validate_filters(
    errors: list[ValidationIssue],
    filters: dict[str, Scalar],
) -> None:
    for key, value in filters.items():
        if not key.strip():
            errors.append(
                _issue("malformed_filter", "Filter keys must be nonempty", "filters")
            )
        if isinstance(value, Decimal):
            continue
        if isinstance(value, list | dict | tuple | set):
            errors.append(
                _issue(
                    "malformed_filter",
                    f"Filter {key!r} has non-scalar value",
                    f"filters.{key}",
                )
            )


def _validate_measure_concept_alignment(
    errors: list[ValidationIssue],
    measure: Measure,
) -> None:
    relation = measure.concept_relation
    if relation is not None and relation not in ALLOWED_CONCEPT_RELATIONS:
        errors.append(
            _issue(
                "malformed_concept_relation",
                f"Unsupported concept relation: {relation!r}",
                "measure.concept_relation",
            )
        )
    if measure.source_concept is not None and not measure.source_concept.strip():
        errors.append(
            _issue(
                "missing_field",
                "Source concept must be nonempty when provided",
                "measure.source_concept",
            )
        )
    if measure.source_concept and relation is None:
        errors.append(
            _issue(
                "missing_field",
                "Concept relation is required when source_concept is provided",
                "measure.concept_relation",
            )
        )


def _validate_constraints(
    errors: list[ValidationIssue],
    constraints: tuple[AggregateConstraint, ...],
) -> None:
    for index, constraint in enumerate(constraints):
        if not constraint.variable.strip():
            errors.append(
                _issue(
                    "malformed_constraint",
                    "Constraint variable must be nonempty",
                    f"constraints.{index}.variable",
                )
            )
        if constraint.operator not in ALLOWED_CONSTRAINT_OPERATORS:
            errors.append(
                _issue(
                    "malformed_constraint",
                    f"Unsupported constraint operator: {constraint.operator!r}",
                    f"constraints.{index}.operator",
                )
            )
        value = constraint.value
        if isinstance(value, Decimal):
            continue
        if isinstance(value, list | dict | tuple | set):
            errors.append(
                _issue(
                    "malformed_constraint",
                    f"Constraint {constraint.variable!r} has non-scalar value",
                    f"constraints.{index}.value",
                )
            )


def _validate_provenance(
    errors: list[ValidationIssue],
    source: SourceProvenance,
) -> None:
    _require_nonempty(errors, source.source_name, "source.source_name")
    if not (source.source_table or source.source_file):
        errors.append(
            _issue(
                "missing_provenance",
                "Source provenance must include source_table or source_file",
                "source.source_table",
            )
        )
    _require_nonempty(errors, source.vintage, "source.vintage")
    _require_nonempty(errors, source.extracted_at, "source.extracted_at")
    _require_nonempty(errors, source.extraction_method, "source.extraction_method")


def _has_missing_provenance(fact: AggregateFact) -> bool:
    return any(
        issue.field is not None
        and issue.field.startswith("source.")
        and issue.code in {"missing_field", "missing_provenance"}
        for issue in validate_fact(fact)
    )


def _require_nonempty(
    errors: list[ValidationIssue],
    value: str | None,
    field_name: str,
) -> None:
    if value is None or not str(value).strip():
        errors.append(
            _issue(
                "missing_field",
                f"Required field is missing: {field_name}",
                field_name,
            )
        )


def _issue(code: str, message: str, field_name: str) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, field=field_name)


def _counter_dict(values: Any) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _humanize(value: object) -> str:
    text = str(value)
    text = re.sub(r"[_\-.]+", " ", text)
    return " ".join(text.split())


def _format_filters(filters: dict[str, Scalar]) -> str:
    return ", ".join(
        f"{_humanize(key)}={_humanize(value)}"
        for key, value in sorted(filters.items())
        if value is not None
    )


def _source_label(source: SourceProvenance) -> str:
    parts = [part for part in (source.source_name, source.source_table) if part]
    if source.source_file and source.source_file not in parts:
        parts.append(source.source_file)
    if source.vintage:
        parts.append(str(source.vintage))
    return " ".join(parts)
