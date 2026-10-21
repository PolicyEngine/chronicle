"""One dimension value carries one label (chronicle#376).

Microcosm copies every fact's dimension and value labels into the targets it
compiles, and the calibration-diagnostics dashboard refuses a release whose
targets label one value two ways. ``build-bundle`` reported a value that two
packages label differently only as a warning (chronicle#265), so IRS SOI's
filing-season week-47 package labelled ``under_1`` of the adjusted-gross-income
dimension "No adjusted gross income and deficit" while every other IRS SOI
package writes "No adjusted gross income", and US release
``populace-us-2024-0fb05b6-4b57d15a287c-20260930T150401Z`` carried both.

``build-bundle`` now refuses a value labelled two ways, inside one package or
across packages, unless every label is a publisher wording Chronicle has
reviewed and kept (``REVIEWED_VALUE_LABEL_VARIANTS``); those stay warnings.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from chronicle import bundle, dimension_labels
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package

ADJUSTED_GROSS_INCOME = "us:statutes/26/62#adjusted_gross_income"
WEEK47 = "soi-filing-season-week47-2024-eitc-total"
IRS_SOI_LABEL = "No adjusted gross income"
WEEK47_COLUMN_HEADER = "No adjusted gross\nincome and deficit"
_PACKAGES = Path(__file__).parents[1] / "packages"


def _groupby_row(*, value_label: str) -> dict:
    """A consumer row whose groupby value carries the given row label."""
    return {
        "aggregate_fact_key": f"ledger.aggregate_fact.v2:{value_label}",
        "dimensions": {"income_range": "under_1"},
        "dimension_labels": {
            "income_range": "Income range",
            ADJUSTED_GROSS_INCOME: "Adjusted gross income",
        },
        "dimension_value_labels": {
            "income_range": {"under_1": IRS_SOI_LABEL},
            ADJUSTED_GROSS_INCOME: {"under_1": value_label},
        },
        "layout": {
            "groupby_dimension": ADJUSTED_GROSS_INCOME,
            "groupby_dimension_label": "Adjusted gross income",
            "groupby_value_id": "under_1",
            "groupby_value_label": value_label,
        },
    }


def test_the_week47_band_below_one_dollar_takes_the_irs_soi_label():
    package = load_source_package(WEEK47)
    facts = package.build_facts(2024, cells=package.build_source_cells(2024))
    below_one_dollar = [
        fact
        for fact in facts
        if fact.layout.groupby_dimension == ADJUSTED_GROSS_INCOME
        and fact.layout.groupby_value_id == "under_1"
    ]

    assert sorted(fact.source_record_id for fact in below_one_dollar) == [
        "irs_soi.ty2024.filing_season_week47.eitc_by_agi.under_1."
        "total_earned_income_credit_amount",
        "irs_soi.ty2024.filing_season_week47.eitc_by_agi.under_1."
        "total_earned_income_credit_returns",
    ]
    for fact in below_one_dollar:
        assert fact.layout.groupby_value_label == IRS_SOI_LABEL
        assert fact.dimension_value_labels[ADJUSTED_GROSS_INCOME] == {
            "under_1": IRS_SOI_LABEL
        }
        assert fact.dimension_value_labels["income_range"] == {"under_1": IRS_SOI_LABEL}
        # The band itself is unchanged: adjusted gross income below $1.
        assert [
            (constraint.variable, constraint.operator, constraint.value)
            for constraint in fact.constraints
        ] == [(ADJUSTED_GROSS_INCOME, "<", 1)]


def test_the_week47_column_guard_keeps_the_irs_wording():
    """The label follows the other IRS SOI packages; the guard still reads the IRS."""
    package_yaml = _PACKAGES / SOURCE_PACKAGE_ALIASES[WEEK47] / "source_package.yaml"
    package = yaml.safe_load(package_yaml.read_text())
    rows = [
        row
        for record_set in package["record_sets"]
        if record_set["groupby_dimension"] == ADJUSTED_GROSS_INCOME
        for row in record_set["rows"]
        if row["value_id"] == "under_1"
    ]

    assert [(row["label"], row["expected_column_header"]) for row in rows] == [
        (IRS_SOI_LABEL, WEEK47_COLUMN_HEADER),
        (IRS_SOI_LABEL, WEEK47_COLUMN_HEADER),
    ]


def test_irs_soi_packages_label_the_band_below_one_dollar_one_way(tmp_path):
    report = bundle.build_bundle(
        tmp_path / "bundle",
        year=2023,
        sources=[
            WEEK47,
            "soi-historic-table-2",
            "soi-table-2-5-eitc-agi-children-2023",
        ],
    )

    assert report.valid, [issue.to_dict() for issue in report.errors]
    assert [
        issue.to_dict()
        for issue in (*report.errors, *report.warnings)
        if issue.key == f"{ADJUSTED_GROSS_INCOME}=under_1"
    ] == []


def test_a_value_two_packages_label_differently_is_refused():
    labels_by_value = {
        (ADJUSTED_GROSS_INCOME, "under_1"): {
            IRS_SOI_LABEL: ["soi-table-1-4"],
            "No adjusted gross income and deficit": [WEEK47],
        },
        ("filing_status", "all"): {"All filing statuses": ["soi-table-1-1"]},
    }

    errors = bundle._cross_package_value_label_errors(labels_by_value)

    assert [(error.code, error.key) for error in errors] == [
        (
            "conflicting_value_label_across_packages",
            f"{ADJUSTED_GROSS_INCOME}=under_1",
        )
    ]
    assert f"'No adjusted gross income and deficit' in ['{WEEK47}']" in (
        errors[0].message
    )
    assert bundle._cross_package_value_label_warnings(labels_by_value) == []


def test_a_reviewed_publisher_wording_across_packages_stays_a_warning():
    labels_by_value = {
        ("property_type", "semi_detached"): {
            "Semi-detached houses": ["ons-hpssa-pcon24-year-ending-march-2026"],
            "Semi detached": ["desnz-need-england-wales-2024"],
        }
    }

    assert bundle._cross_package_value_label_errors(labels_by_value) == []
    assert [
        (warning.code, warning.key)
        for warning in bundle._cross_package_value_label_warnings(labels_by_value)
    ] == [("conflicting_value_label_across_packages", "property_type=semi_detached")]


def test_a_new_wording_of_a_reviewed_value_is_refused():
    labels_by_value = {
        ("property_type", "semi_detached"): {
            "Semi-detached houses": ["ons-hpssa-pcon24-year-ending-march-2026"],
            "Semi detached": ["desnz-need-england-wales-2024"],
            "Semi-detached": ["a-new-package"],
        }
    }

    errors = bundle._cross_package_value_label_errors(labels_by_value)

    assert [error.key for error in errors] == ["property_type=semi_detached"]
    assert bundle._cross_package_value_label_warnings(labels_by_value) == []


def test_one_package_labelling_a_groupby_value_two_ways_is_refused():
    errors, warnings = bundle._dimension_label_reports(
        WEEK47,
        [
            _groupby_row(value_label=IRS_SOI_LABEL),
            _groupby_row(value_label="No adjusted gross income and deficit"),
        ],
    )

    assert [(error.code, error.key) for error in errors] == [
        ("conflicting_groupby_value_label", f"{ADJUSTED_GROSS_INCOME}=under_1")
    ]
    assert errors[0].source == WEEK47
    assert warnings == []


def test_a_reviewed_publisher_wording_inside_one_package_stays_a_warning():
    """SLC prints two footnote spellings for one row (Table 7C(ii)!B75, B111)."""
    axis = "early_year_award_line"
    axis_label = "Early-in-year support line"
    returning_total_id = "new_returning_total_returning_31_33_35"
    rows = [
        {
            "aggregate_fact_key": f"ledger.aggregate_fact.v2:{value_label}",
            "dimensions": {axis: returning_total_id},
            "dimension_labels": {axis: axis_label},
            "dimension_value_labels": {axis: {returning_total_id: value_label}},
            "layout": {
                "groupby_dimension": axis,
                "groupby_dimension_label": axis_label,
                "groupby_value_id": returning_total_id,
                "groupby_value_label": value_label,
            },
        }
        for value_label in (
            "Total returning [31][33][35]",
            "Total returning [31[[33][35]",
        )
    ]

    errors, warnings = bundle._dimension_label_reports(
        "slc-student-support-england-2025-provisional-2025-26", rows
    )

    assert errors == []
    assert [(warning.code, warning.key) for warning in warnings] == [
        ("conflicting_groupby_value_label", f"{axis}={returning_total_id}")
    ]


def test_every_reviewed_variant_names_two_or_more_labels():
    register = dimension_labels.REVIEWED_VALUE_LABEL_VARIANTS

    assert register
    for (dimension_id, value_id), labels in register.items():
        assert dimension_id.strip() == dimension_id and dimension_id
        assert value_id.strip() == value_id and value_id
        assert len(labels) >= 2, (dimension_id, value_id)
        assert all(label.strip() == label and label for label in labels)
    assert (ADJUSTED_GROSS_INCOME, "under_1") not in register
