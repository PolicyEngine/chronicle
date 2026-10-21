"""Chronicle-owned labels for fact dimensions and dimension values.

Microcosm's calibration hierarchy (microcosm#855) names every dimension and
dimension value a target inherits from the Chronicle facts it selects, and it
takes those names only from Chronicle (chronicle#261). Every fact therefore
carries ``dimension_labels`` (dimension id to label) and
``dimension_value_labels`` (dimension id to value id to label) covering its
``filters`` and, when it has one, its ``layout.groupby_dimension``, whose label
is also stamped on ``layout.groupby_dimension_label``.

Labels resolve per package; the first source that has one wins.

Dimension ids:

1. the package's ``dimension_labels`` declaration;
2. the publisher's field label, for a Stat-Xplore field the parser read;
3. the label on the package's ``==`` constraints for that filter, when they
   agree on one label that is not the identifier itself.

Dimension values:

1. the package's ``dimension_value_labels`` declaration;
2. the fact's publisher row label (``layout.groupby_value_label``) when the
   dimension is the record set's groupby axis (the same id, or the same leaf
   name source-filter canonicalization matches on) and the value is the row's
   value id;
3. the publisher's text in the matching column of the fact's source row, when
   the row-semantic acceptance matches the filter to it (for ``all``, the
   publisher's aggregate item, such as Stat-Xplore's ``Total``);
4. a number or an ISO date, which labels itself.

Everything else must be declared. :func:`dimension_label_issues` checks rows
the way Microcosm reads them and reports what is missing or labelled two ways.
A value labelled two ways is a bundle error unless it is a reviewed publisher
wording in :data:`REVIEWED_VALUE_LABEL_VARIANTS` (chronicle#376).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from chronicle.consumer_contract import _concept_leaf
from chronicle.core import AggregateFact, SourceRecordLayout
from chronicle.epoch import Epoch, canonicalize_key
from chronicle.sources.rows import SourceRow, build_source_row_key

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# One dimension value id carries one label (chronicle#376). Microcosm copies a
# fact's labels into every target it compiles, and a release whose targets
# label one value two ways cannot be shown as one value. ``build-bundle``
# therefore refuses a value labelled two ways, whether by two packages or by
# the groupby rows of one package, unless every label it carries is listed
# here for that value; those it reports as warnings.
#
# Each entry is publisher wording that a review kept as published before the
# rule. A new package takes the label the other packages give a value, even
# where its own table words it differently, and its guards check the
# publisher's text. An entry leaves this register once its packages agree:
# the merged-bundle test requires every entry to still warn.
REVIEWED_VALUE_LABEL_VARIANTS: Mapping[tuple[str, str], frozenset[str]] = (
    MappingProxyType(
        {
            # chronicle#265: Census Bureau tables word ages differently.
            ("age", "85_plus"): frozenset({"Age 85 and over", "Age 85 plus"}),
            ("age", "age_20"): frozenset({"Age 20", "Female 20 years"}),
            ("age", "age_21"): frozenset({"Age 21", "Female 21 years"}),
            # chronicle#302: ASHE writes '30 to 39' where NTS0601 writes
            # 'Age 30 to 39'.
            ("age_band", "30 to 39"): frozenset({"30 to 39", "Age 30 to 39"}),
            ("age_band", "40 to 49"): frozenset({"40 to 49", "Age 40 to 49"}),
            # chronicle#313: SLC Table 7C(ii) spells one footnote two ways
            # (B75 and B111).
            (
                "early_year_award_line",
                "new_returning_total_returning_31_33_35",
            ): frozenset(
                {"Total returning [31[[33][35]", "Total returning [31][33][35]"}
            ),
            # chronicle#265: Groeipakket counts each supplement per child and
            # per family.
            ("groeipakket.component", "pleegzorgtoeslag"): frozenset(
                {
                    "Foster care supplement child caseload",
                    "Foster care supplement family caseload",
                }
            ),
            ("groeipakket.component", "sociale_toeslag"): frozenset(
                {
                    "Social supplement child caseload",
                    "Social supplement family caseload",
                }
            ),
            ("groeipakket.component", "wezentoeslag"): frozenset(
                {
                    "Orphan supplement child caseload",
                    "Orphan supplement family caseload",
                }
            ),
            ("groeipakket.component", "zorgtoeslag"): frozenset(
                {
                    "Care supplement child caseload",
                    "Care supplement family caseload",
                }
            ),
            # chronicle#265: two ONS tables number the same footnote
            # differently.
            ("household_type", "couple_3_plus_children_households"): frozenset(
                {
                    "3 or more dependent children [note 3]",
                    "3 or more dependent children [note 5]",
                }
            ),
            ("ons.household_type", "couple_3_plus_children_households"): frozenset(
                {
                    "3 or more dependent children [note 3]",
                    "3 or more dependent children [note 5]",
                }
            ),
            # chronicle#265: each Belgian package names its own country total.
            ("measure", "country_total"): frozenset(
                {
                    "Belgium PIT federal and local tax before withholding",
                    "Complete unemployment benefit recipients",
                    "Household disposable income gross",
                    "Worker-borne personal social security contributions",
                }
            ),
            # chronicle#265: Eurostat's paid-direction and received-direction
            # cells of one national-accounts item.
            ("na_item", "belgium_household_disposable_income_gross"): frozenset(
                {
                    "Disposable income, gross (B.6G), paid-direction cell",
                    "Disposable income, gross (B.6G), received-direction cell",
                }
            ),
            ("na_item", "belgium_household_mixed_income_gross"): frozenset(
                {
                    "Mixed income, gross (B.3G), paid-direction cell",
                    "Mixed income, gross (B.3G), received-direction cell",
                }
            ),
            ("na_item", "belgium_household_operating_surplus_gross"): frozenset(
                {
                    "Operating surplus, gross (B.2G), paid-direction cell",
                    "Operating surplus, gross (B.2G), received-direction cell",
                }
            ),
            # chronicle#322: the ONS Consumer Trends overview and detailed
            # worksheets name six divisions differently.
            ("ons.coicop", "coicop_01"): frozenset(
                {"Food and drink", "Food and non-alcoholic beverages"}
            ),
            ("ons.coicop", "coicop_02"): frozenset(
                {
                    "Alcohol, tobacco and narcotics",
                    "Alcoholic beverages and tobacco [note 1]",
                }
            ),
            ("ons.coicop", "coicop_04"): frozenset(
                {"Housing", "Housing, water, electricity, gas and other fuel"}
            ),
            ("ons.coicop", "coicop_05"): frozenset(
                {
                    "Furnishing, household equipment and routine HH maintenance",
                    "Furnishings, household equipment and routine maintenance "
                    "of the house",
                }
            ),
            ("ons.coicop", "coicop_11"): frozenset(
                {"Restaurant and hotels", "Restaurants and hotels"}
            ),
            ("ons.coicop", "coicop_12"): frozenset(
                {"Miscellaneous", "Miscellaneous goods and services"}
            ),
            # chronicle#211: Stats NZ heads its oldest band '65+' where
            # Statbel's rows write '65_plus'.
            ("person.age_band", "65_plus"): frozenset({"65+", "65_plus"}),
            # chronicle#313 and #343: DESNZ, ONS house-price and ONS rent
            # tables word property types differently.
            ("property_type", "detached"): frozenset(
                {"Detached", "Detached houses", "detached"}
            ),
            ("property_type", "semi_detached"): frozenset(
                {"Semi detached", "Semi-detached houses"}
            ),
            ("property_type", "terraced"): frozenset(
                {"Terraced", "Terraced houses", "terraced"}
            ),
            # chronicle#265: Eurostat publishes a decile's income threshold and
            # its income share under one income-quantile code.
            ("quant_inc", "d1"): frozenset(
                {"First income decile cut-point", "First income decile share"}
            ),
            ("quant_inc", "d2"): frozenset(
                {"Second income decile cut-point", "Second income decile share"}
            ),
            ("quant_inc", "d3"): frozenset(
                {"Third income decile cut-point", "Third income decile share"}
            ),
            ("quant_inc", "d4"): frozenset(
                {"Fourth income decile cut-point", "Fourth income decile share"}
            ),
            ("quant_inc", "d5"): frozenset(
                {"Fifth income decile cut-point", "Fifth income decile share"}
            ),
            ("quant_inc", "d6"): frozenset(
                {"Sixth income decile cut-point", "Sixth income decile share"}
            ),
            ("quant_inc", "d7"): frozenset(
                {"Seventh income decile cut-point", "Seventh income decile share"}
            ),
            ("quant_inc", "d8"): frozenset(
                {"Eighth income decile cut-point", "Eighth income decile share"}
            ),
            ("quant_inc", "d9"): frozenset(
                {"Ninth income decile cut-point", "Ninth income decile share"}
            ),
            # chronicle#265: the UK statistics offices and HMRC write 'Female'
            # or 'Females'; ACS B01001's rows write 'female'.
            ("sex", "female"): frozenset({"Female", "Females", "female"}),
            ("sex", "male"): frozenset({"Male", "Males"}),
            # chronicle#265: IRS SOI's total rows: 'All returns' in Historic
            # Table 2 and Table 1.1, 'All returns, total' in Tables 1.2, 1.4,
            # 2.1 and 4.3.
            ("us:statutes/26/62#adjusted_gross_income", "all"): frozenset(
                {"All returns", "All returns, total"}
            ),
        }
    )
)


def is_reviewed_value_label_variant(
    dimension_id: str,
    value_id: str | None,
    labels: Iterable[str],
) -> bool:
    """Whether every label of one value is a reviewed wording of it.

    A value labelled two ways is accepted only when its id is in
    :data:`REVIEWED_VALUE_LABEL_VARIANTS` and each label is listed for it, so a
    third wording of a reviewed value is refused like any other (chronicle#376).
    """
    if value_id is None:
        return False
    reviewed = REVIEWED_VALUE_LABEL_VARIANTS.get((dimension_id, value_id))
    return reviewed is not None and set(labels) <= reviewed


def dimension_value_id(value: Any) -> str:
    """Return the ``dimension_value_labels`` key of one dimension value.

    Booleans are lower-cased, lists and mappings JSON-serialized with sorted
    keys and no spaces, and anything else is written as ``str()`` of its JSON
    value: the form Microcosm's calibration hierarchy looks labels up by.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, dict | list | tuple):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def label_facts(
    facts: Iterable[AggregateFact],
    *,
    dimension_labels: Mapping[str, str] | None = None,
    dimension_value_labels: Mapping[str, Mapping[str, str]] | None = None,
    field_labels: Mapping[str, str] | None = None,
    source_rows: Iterable[SourceRow] = (),
) -> list[AggregateFact]:
    """Return one package's facts carrying the labels it declares or evidences.

    ``dimension_labels`` and ``dimension_value_labels`` are the package's
    declarations, ``field_labels`` the publisher's labels for parsed source-row
    columns, and ``source_rows`` the parsed rows the facts' lineage points at.
    A dimension or value no source labels is left unlabelled for
    :func:`dimension_label_issues` to report.
    """
    facts = list(facts)
    declared = dict(dimension_labels or {})
    declared_values = {
        dimension_id: dict(value_labels)
        for dimension_id, value_labels in (dimension_value_labels or {}).items()
    }
    publisher_field_labels = dict(field_labels or {})
    constraint_labels = _constraint_labels(facts)
    rows_by_key = {
        build_source_row_key(row, epoch=Epoch.LEDGER): row for row in source_rows
    }

    labelled = []
    for fact in facts:
        dimensions = _fact_dimensions(fact)
        layout = fact.layout
        groupby = layout.groupby_dimension if layout else None
        labels: dict[str, str] = {}
        for dimension_id in (*dimensions, *([groupby] if groupby else [])):
            label = (
                declared.get(dimension_id)
                or publisher_field_labels.get(dimension_id)
                or constraint_labels.get(dimension_id)
            )
            if label:
                labels[dimension_id] = label

        rows = [
            rows_by_key[key]
            for key in (
                canonicalize_key("source_row", key) for key in fact.source_row_keys
            )
            if key in rows_by_key
        ]
        value_labels: dict[str, dict[str, str]] = defaultdict(dict)
        for dimension_id, value in dimensions.items():
            value_id = dimension_value_id(value)
            label = (
                declared_values.get(dimension_id, {}).get(value_id)
                or _groupby_row_label(layout, dimension_id, value_id)
                or _source_row_label(rows, dimension_id, value)
                or _self_label(value)
            )
            if label:
                value_labels[dimension_id][value_id] = label
        if (
            groupby
            and groupby not in dimensions
            and layout.groupby_value_id is not None
        ):
            value_id = dimension_value_id(layout.groupby_value_id)
            label = declared_values.get(groupby, {}).get(value_id) or (
                _groupby_row_label(layout, groupby, value_id)
            )
            if label:
                value_labels[groupby][value_id] = label

        labelled.append(
            replace(
                fact,
                dimension_labels=labels,
                dimension_value_labels=dict(value_labels),
                layout=(
                    replace(layout, groupby_dimension_label=labels.get(groupby))
                    if layout
                    else layout
                ),
            )
        )
    return labelled


def unused_label_declarations(
    facts: Iterable[AggregateFact],
    *,
    dimension_labels: Mapping[str, str] | None = None,
    dimension_value_labels: Mapping[str, Mapping[str, str]] | None = None,
) -> list[str]:
    """Return the declarations no fact of the package uses, as dotted paths."""
    used_dimensions: set[str] = set()
    used_values: set[tuple[str, str]] = set()
    for fact in facts:
        for dimension_id, value in _fact_dimensions(fact).items():
            used_dimensions.add(dimension_id)
            used_values.add((dimension_id, dimension_value_id(value)))
        layout = fact.layout
        if layout and layout.groupby_dimension:
            used_dimensions.add(layout.groupby_dimension)
            if layout.groupby_value_id is not None:
                used_values.add(
                    (
                        layout.groupby_dimension,
                        dimension_value_id(layout.groupby_value_id),
                    )
                )
    unused = [
        f"dimension_labels.{dimension_id}"
        for dimension_id in (dimension_labels or {})
        if dimension_id not in used_dimensions
    ]
    unused.extend(
        f"dimension_value_labels.{dimension_id}.{value_id}"
        for dimension_id, value_labels in (dimension_value_labels or {}).items()
        for value_id in value_labels
        if (dimension_id, value_id) not in used_values
    )
    return unused


@dataclass(frozen=True)
class DimensionLabelIssue:
    """A dimension or value that is unlabelled, or labelled two ways."""

    code: str
    dimension_id: str
    value_id: str | None = None
    labels: tuple[str, ...] = ()
    fact_count: int = 0
    example_fact_key: str | None = None

    @property
    def message(self) -> str:
        target = f"dimension {self.dimension_id!r}"
        if self.value_id is not None:
            target = f"{target} value {self.value_id!r}"
        if self.code == "conflicting_groupby_value_label":
            return (
                f"{target} carries publisher row labels that differ across "
                f"facts: {list(self.labels)!r}; a consumer selecting facts "
                "from more than one of those rows sees conflicting labels."
            )
        if self.code.startswith("conflicting"):
            return f"{target} carries more than one label: {list(self.labels)!r}."
        return (
            f"{target} has no Chronicle label on {self.fact_count} fact(s); "
            "declare it in the package's dimension_labels or "
            "dimension_value_labels."
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable issue."""
        payload = {
            key: value
            for key, value in asdict(self).items()
            if value not in (None, (), [], 0)
        }
        if self.labels:
            payload["labels"] = list(self.labels)
        payload["message"] = self.message
        return payload


def dimension_label_issues(
    rows: Iterable[Mapping[str, Any]],
) -> list[DimensionLabelIssue]:
    """Check consumer-fact rows the way Microcosm's calibration hierarchy reads them.

    Each row's dimensions (its ``dimensions`` plus ``layout.groupby_dimension``
    folded in at ``layout.groupby_value_id`` when absent) each need exactly one
    non-empty label, read from ``dimension_labels`` or, for the groupby
    dimension, ``layout.groupby_dimension_label``; each value likewise, from
    ``dimension_value_labels`` or, for the groupby value,
    ``layout.groupby_value_label``. Across *rows*, every dimension id and every
    value must carry a single label. Values that only ever appear as a groupby
    value, whose publisher row labels differ across rows, are reported
    separately as ``conflicting_groupby_value_label``: that text is the
    publisher's, kept as published — including the row value of a groupby axis
    that is also a filter, whose own value the row names and the filter does
    not. Issues are aggregated per dimension or value, with a fact count and an
    example fact key.
    """
    missing: dict[tuple[str, str, str | None], list[Any]] = {}
    row_conflicts: dict[tuple[str, str | None], set[str]] = defaultdict(set)
    dimension_labels_seen: dict[str, set[str]] = defaultdict(set)
    value_labels_seen: dict[tuple[str, str], set[str]] = defaultdict(set)
    plain_values: set[tuple[str, str]] = set()

    for row in rows:
        fact_key = row.get("aggregate_fact_key")
        layout = row.get("layout") or {}
        groupby = str(layout.get("groupby_dimension") or "").strip()
        raw_groupby_value_id = layout.get("groupby_value_id")
        groupby_value_id = (
            dimension_value_id(raw_groupby_value_id).strip()
            if raw_groupby_value_id is not None
            else ""
        )
        dimensions = {
            str(key): value for key, value in (row.get("dimensions") or {}).items()
        }
        if groupby and groupby_value_id:
            dimensions.setdefault(groupby, groupby_value_id)
        row_dimension_labels = row.get("dimension_labels") or {}
        row_value_labels = row.get("dimension_value_labels") or {}

        for dimension_id, value in dimensions.items():
            labels = _nonempty_labels(
                row_dimension_labels.get(dimension_id),
                (
                    layout.get("groupby_dimension_label")
                    if dimension_id == groupby
                    else None
                ),
            )
            if not labels:
                _count(
                    missing, ("missing_dimension_label", dimension_id, None), fact_key
                )
            elif len(labels) > 1:
                row_conflicts[(dimension_id, None)].update(labels)
            else:
                dimension_labels_seen[dimension_id].update(labels)

            value_id = dimension_value_id(value)
            groupby_value = dimension_id == groupby and value_id == groupby_value_id
            if not groupby_value:
                plain_values.add((dimension_id, value_id))
            value_labels = _nonempty_labels(
                (row_value_labels.get(dimension_id) or {}).get(value_id),
                layout.get("groupby_value_label") if groupby_value else None,
            )
            if not value_labels:
                _count(
                    missing,
                    ("missing_dimension_value_label", dimension_id, value_id),
                    fact_key,
                )
            elif len(value_labels) > 1:
                row_conflicts[(dimension_id, value_id)].update(value_labels)
            else:
                value_labels_seen[(dimension_id, value_id)].update(value_labels)

        # When the groupby axis is also a filter but its row value differs from
        # the filter's, the row's own value never reaches the loop above. Its
        # publisher label is still a label of that axis, and a package that
        # names one row value two ways across its record sets drifts the way
        # ``conflicting_groupby_value_label`` reports (chronicle#265).
        if groupby and groupby_value_id:
            folded = dimension_value_id(dimensions.get(groupby, ""))
            if folded != groupby_value_id:
                row_label = _nonempty_labels(layout.get("groupby_value_label"))
                if row_label:
                    value_labels_seen[(groupby, groupby_value_id)].update(row_label)

    issues = [
        DimensionLabelIssue(
            code=code,
            dimension_id=dimension_id,
            value_id=value_id,
            fact_count=count,
            example_fact_key=example,
        )
        for (code, dimension_id, value_id), (count, example) in missing.items()
    ]
    for (dimension_id, value_id), labels in row_conflicts.items():
        issues.append(
            DimensionLabelIssue(
                code=(
                    "conflicting_dimension_label"
                    if value_id is None
                    else "conflicting_dimension_value_label"
                ),
                dimension_id=dimension_id,
                value_id=value_id,
                labels=tuple(sorted(labels)),
            )
        )
    for dimension_id, labels in dimension_labels_seen.items():
        if len(labels) > 1 and (dimension_id, None) not in row_conflicts:
            issues.append(
                DimensionLabelIssue(
                    code="conflicting_dimension_label",
                    dimension_id=dimension_id,
                    labels=tuple(sorted(labels)),
                )
            )
    for (dimension_id, value_id), labels in value_labels_seen.items():
        if len(labels) > 1 and (dimension_id, value_id) not in row_conflicts:
            issues.append(
                DimensionLabelIssue(
                    code=(
                        "conflicting_dimension_value_label"
                        if (dimension_id, value_id) in plain_values
                        else "conflicting_groupby_value_label"
                    ),
                    dimension_id=dimension_id,
                    value_id=value_id,
                    labels=tuple(sorted(labels)),
                )
            )
    return sorted(
        issues,
        key=lambda issue: (issue.code, issue.dimension_id, issue.value_id or ""),
    )


def dimension_labels_by_id(rows: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    """Return the labels each dimension id carries across consumer-fact rows."""
    found: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for dimension_id, label in (row.get("dimension_labels") or {}).items():
            found[str(dimension_id)].update(_nonempty_labels(label))
        layout = row.get("layout") or {}
        groupby = str(layout.get("groupby_dimension") or "").strip()
        if groupby:
            found[groupby].update(
                _nonempty_labels(layout.get("groupby_dimension_label"))
            )
    return {dimension_id: labels for dimension_id, labels in found.items() if labels}


def _fact_dimensions(fact: AggregateFact) -> dict[str, Any]:
    return {key: value for key, value in fact.filters.items() if value is not None}


def _constraint_labels(facts: list[AggregateFact]) -> dict[str, str]:
    """Return the one label a package's ``==`` constraints give each filter."""
    found: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        for constraint in fact.constraints:
            if constraint.operator != "==" or constraint.variable not in fact.filters:
                continue
            label = (constraint.label or "").strip()
            if label and label not in {
                constraint.variable,
                _concept_leaf(constraint.variable),
            }:
                found[constraint.variable].add(label)
    return {
        variable: next(iter(labels))
        for variable, labels in found.items()
        if len(labels) == 1
    }


def _groupby_row_label(
    layout: SourceRecordLayout | None,
    dimension_id: str,
    value_id: str,
) -> str | None:
    if layout is None or not layout.groupby_dimension:
        return None
    if layout.groupby_value_id is None:
        return None
    if dimension_value_id(layout.groupby_value_id) != value_id:
        return None
    groupby = layout.groupby_dimension
    if dimension_id != groupby and _concept_leaf(dimension_id) != _concept_leaf(
        groupby
    ):
        return None
    return (layout.groupby_value_label or "").strip() or None


def _source_row_label(
    rows: list[SourceRow],
    dimension_id: str,
    value: Any,
) -> str | None:
    if not rows:
        return None
    # Imported here: chronicle.suite imports chronicle.source_package, which
    # labels its facts through this module.
    from chronicle.suite import _filter_value_matches_source_value, _source_row_value

    matched = []
    for row in rows:
        found, source_value = _source_row_value(row, dimension_id)
        if found:
            matched.append(source_value)
    if not matched or any(source_value is None for source_value in matched):
        return None
    texts = {str(source_value).strip() for source_value in matched}
    if len(texts) != 1 or "" in texts:
        return None
    if value != "all" and not all(
        _filter_value_matches_source_value(dimension_id, value, source_value)
        for source_value in matched
    ):
        return None
    return texts.pop()


def _self_label(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return dimension_value_id(value)
    if isinstance(value, str) and _ISO_DATE.fullmatch(value):
        return value
    return None


def _nonempty_labels(*candidates: Any) -> set[str]:
    return {
        str(candidate).strip()
        for candidate in candidates
        if candidate is not None and str(candidate).strip()
    }


def _count(
    counts: dict[tuple[str, str, str | None], list[Any]],
    key: tuple[str, str, str | None],
    fact_key: Any,
) -> None:
    entry = counts.setdefault(key, [0, fact_key])
    entry[0] += 1


__all__ = [
    "REVIEWED_VALUE_LABEL_VARIANTS",
    "DimensionLabelIssue",
    "dimension_label_issues",
    "dimension_labels_by_id",
    "dimension_value_id",
    "is_reviewed_value_label_variant",
    "label_facts",
    "unused_label_declarations",
]
