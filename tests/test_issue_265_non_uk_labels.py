"""Dimension labels are checked for every package, not just the UK suite (chronicle#265).

chronicle#261 gave every consumer fact Chronicle-owned dimension and value
labels but checked only the UK packages, so the US, Belgian and Eurostat
packages emitted whatever labels happened to resolve. Microcosm reads them the
same way whichever country published them — its US fiscal and Belgian target
references carry hierarchy seeds too — so ``build-bundle`` now holds every
package to the same rule, and one dimension id carries one label across the
whole bundle.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from chronicle import bundle
from chronicle.bundle import (
    UK_BUNDLE_SOURCES,
    _cross_package_dimension_label_errors,
    _cross_package_value_label_warnings,
    _dimension_label_reports,
    _value_labels,
)
from chronicle.source_package import SOURCE_PACKAGE_ALIASES

_PACKAGES = Path(__file__).parents[1] / "packages"


def _row(*, dimension_labels, groupby_label):
    layout = {
        "record_set_id": "jct.tax_expenditures.cy2024",
        "groupby_dimension": "jct.tax_expenditure",
        "groupby_value_id": "salt_deduction",
        "groupby_value_label": "State and local tax deduction",
    }
    if groupby_label is not None:
        layout["groupby_dimension_label"] = groupby_label
    return {
        "dimensions": {"tax_expenditure": "salt_deduction"},
        "dimension_labels": dict(dimension_labels),
        "dimension_value_labels": {
            "tax_expenditure": {"salt_deduction": "State and local tax deduction"}
        },
        "layout": layout,
    }


def _copy_package(tmp_path, relative_dir, *, transform):
    source = _PACKAGES / relative_dir
    target = tmp_path / source.name
    shutil.copytree(source, target)
    package_yaml = target / "source_package.yaml"
    package_yaml.write_text(transform(package_yaml.read_text()))
    return target


def _without_label_blocks(text):
    kept, skipping = [], False
    for line in text.split("\n"):
        if line.startswith(("dimension_labels:", "dimension_value_labels:")):
            skipping = True
            continue
        if skipping:
            if not line or line.startswith(" "):
                continue
            skipping = False
        kept.append(line)
    return "\n".join(kept)


def test_a_package_outside_the_uk_suite_is_checked_like_a_uk_one():
    unlabelled = _row(dimension_labels={}, groupby_label=None)
    labelled = _row(
        dimension_labels={
            "tax_expenditure": "Tax expenditure",
            "jct.tax_expenditure": "Tax expenditure",
        },
        groupby_label="Tax expenditure",
    )

    assert "jct-tax-expenditures-2024" not in UK_BUNDLE_SOURCES
    errors, warnings = _dimension_label_reports(
        "jct-tax-expenditures-2024", [unlabelled]
    )
    assert {error.code for error in errors} == {"missing_dimension_label"}
    assert {error.source for error in errors} == {"jct-tax-expenditures-2024"}
    assert warnings == []
    assert _dimension_label_reports("jct-tax-expenditures-2024", [labelled]) == ([], [])


def test_one_dimension_id_needs_one_label_across_the_whole_bundle():
    errors = _cross_package_dimension_label_errors(
        {
            "geo": {
                "Geopolitical entity (reporting)": ["eurostat-ilc-li02"],
                "Belgium": ["eurostat-nasa-10-nf-tr"],
            },
            "geography": {
                "Geography": ["statbel-fiscal-income-2023-nis-2025", "ons-a"]
            },
        }
    )

    assert [(error.code, error.key) for error in errors] == [
        ("conflicting_dimension_label_across_packages", "geo")
    ]
    assert "Packages label dimension 'geo' differently" in errors[0].message


def test_build_bundle_reports_an_unlabelled_non_uk_package(tmp_path):
    package_dir = _copy_package(
        tmp_path,
        "jct/tax_expenditures_2024",
        transform=_without_label_blocks,
    )

    report = bundle.build_bundle(
        tmp_path / "bundle", year=2024, sources=[str(package_dir)]
    )

    assert not report.valid
    assert {issue.code for issue in report.errors} == {"missing_dimension_label"}
    assert "jct.tax_expenditure" in {issue.key for issue in report.errors}


def test_the_packages_microcosm_targets_outside_the_uk_declare_their_labels():
    """The ids microcosm#855's US fiscal and Belgian references read."""
    declared = {}
    for alias, dimension_id in (
        ("jct-tax-expenditures-2024", "jct.tax_expenditure"),
        ("nbb-national-accounts-household-disposable-income-2024", "measure"),
        ("onem-rva-unemployment-2024", "measure"),
        ("onss-contributions-2024", "measure"),
        ("spf-finances-pit-2023", "measure"),
        ("statbel-population-structure-2025", "demographic_group"),
    ):
        package = _PACKAGES / SOURCE_PACKAGE_ALIASES[alias] / "source_package.yaml"
        labels = yaml.safe_load(package.read_text()).get("dimension_labels") or {}
        declared[alias] = labels.get(dimension_id)

    assert declared == {
        "jct-tax-expenditures-2024": "Tax expenditure",
        "nbb-national-accounts-household-disposable-income-2024": "Measure",
        "onem-rva-unemployment-2024": "Measure",
        "onss-contributions-2024": "Measure",
        "spf-finances-pit-2023": "Measure",
        "statbel-population-structure-2025": "Demographic group",
    }


def test_a_value_two_packages_word_differently_is_a_warning():
    warnings = _cross_package_value_label_warnings(
        {
            ("income_range", "under_1"): {
                "No adjusted gross income": ["soi-table-1-1"],
                "No adjusted gross income and deficit": [
                    "soi-filing-season-week47-2024-eitc-total"
                ],
            },
            ("filing_status", "all"): {"All filing statuses": ["soi-table-1-1"]},
        }
    )

    assert [(warning.code, warning.key) for warning in warnings] == [
        ("conflicting_value_label_across_packages", "income_range=under_1")
    ]
    assert "'No adjusted gross income' in ['soi-table-1-1']" in warnings[0].message


def test_an_area_name_is_left_to_the_geography_warning():
    """A value that is the row's own geography is the other warning's business."""
    row = {
        "geography": {"level": "constituency", "id": "E14001101"},
        "dimension_value_labels": {
            "geography": {"e14001101": "Bishop Auckland"},
            "tenure": {"social": "Social rented"},
        },
        "layout": {
            "groupby_dimension": "geography",
            "groupby_value_id": "e14001101",
            "groupby_value_label": "Bishop Auckland",
        },
    }

    assert _value_labels([row]) == {("tenure", "social"): {"Social rented"}}


def test_one_package_disagreeing_with_itself_is_left_to_its_own_report():
    """The package-level check owns single-source drift; this one would repeat it."""
    warnings = _cross_package_value_label_warnings(
        {
            ("groeipakket.component", "sociale_toeslag"): {
                "Social supplement child caseload": [
                    "opgroeien-groeipakket-caseload-2025"
                ],
                "Social supplement family caseload": [
                    "opgroeien-groeipakket-caseload-2025"
                ],
            }
        }
    )

    assert warnings == []
