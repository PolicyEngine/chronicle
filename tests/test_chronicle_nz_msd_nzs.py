"""Publisher-fidelity tests for MSD's June 2026 NZS/VP fact sheet."""

from __future__ import annotations

import hashlib
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

from chronicle.artifacts import build_r2_key
from chronicle.bundle import _dimension_label_reports, build_bundle_coverage
from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import load_source_package, validate_source_package
from chronicle.sources import build_source_cell_key, validate_source_cells
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = Path("msd/nzs_vp_fact_sheet_june_2026")
PACKAGE_PATH = REPO_ROOT / "packages" / DIRECTORY
PACKAGE_ID = "msd-nzs-vp-fact-sheet-june-2026"
FILENAME = "quarterly-benefit-fact-sheets-nzs-and-vp-tables-june-2026.xlsx"
SHA256 = "18561d76dab98e24593a619733f01f9ba6e6dd2b5de16357bd7d79066f33c6de"
SOURCE_URL = (
    "https://www.msd.govt.nz/documents/about-msd-and-our-work/"
    "publications-resources/statistics/benefit/2026/" + FILENAME
)
SHEET = "Summary - latest qtr"
PREFIX = "msd_nzs_vp.june2026"
SPEC = yaml.safe_load((PACKAGE_PATH / "source_package.yaml").read_text())


@lru_cache
def _package():
    return load_source_package(PACKAGE_PATH)


@lru_cache
def _cells():
    return _package().build_source_cells(2026)


@lru_cache
def _facts():
    return _package().build_facts(2026, cells=_cells())


@lru_cache
def _records():
    return _package().build_source_records(2026, cells=_cells())


def _fact(category, row, benefit):
    return next(
        fact
        for fact in _facts()
        if fact.source_record_id == f"{PREFIX}.{category}.{row}.{benefit}_recipients"
    )


def _guard_addresses():
    """Exercise each authored guard/header cell, including every row label."""
    addresses = set()
    for record_set in SPEC["record_sets"]:
        for row in record_set["rows"]:
            addresses.add(f"{row['expected_row_header_column']}{row['row_number']}")
            addresses.update(
                f"{guard['column']}{guard['row']}" for guard in row["guard_cells"]
            )
        addresses.update(
            f"{measure['column']}{measure['expected_column_header_row']}"
            for measure in record_set["measures"]
        )
    return sorted(addresses)


TYPE_GUARD_ADDRESSES = [
    f"{measure['column']}{record_set['rows'][0]['row_number']}"
    for record_set in SPEC["record_sets"]
    for measure in record_set["measures"]
]


def test_nzs_package_validation_and_immutable_artifact():
    report = validate_source_package(PACKAGE_PATH, year=2026)
    assert report.valid
    assert not report.warnings
    assert report.counts == {
        "record_set_count": 6,
        "row_count": 23,
        "measure_count": 12,
        "source_record_count": 46,
        "source_region_count": 6,
    }
    data_dir = REPO_ROOT / "db" / "data" / DIRECTORY
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text())
    artifact = manifest["files"][2026]
    raw = data_dir / FILENAME
    assert manifest["source_id"] == "msd"
    assert manifest["package_id"] == PACKAGE_ID
    assert artifact["source_url"] == SOURCE_URL
    assert artifact["sha256"] == hashlib.sha256(raw.read_bytes()).hexdigest() == SHA256
    assert artifact["size_bytes"] == raw.stat().st_size == 81_322
    assert artifact["fetched_at"] == "2026-10-07T19:22:22Z"
    key = build_r2_key(
        source_id="msd",
        package_id=PACKAGE_ID,
        year=2026,
        sha256=SHA256,
        filename=FILENAME,
        package_path=PACKAGE_PATH,
    )
    assert key.startswith("raw/nz/msd/")
    assert artifact["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }
    assert {fact.source.raw_r2_uri for fact in _facts()} == {f"r2://ledger-raw/{key}"}


def test_nzs_whole_workbook_source_cells_and_direct_cell_lineage():
    assert Counter(cell.sheet_name for cell in _cells()) == {
        "Contents and notes": 124,
        SHEET: 203,
        "Benefit type - over time": 161,
        "Recipient chars - over time": 1320,
        "TA Breakdown - over time": 1015,
        "Overseas Pension - latest qtr": 152,
    }
    assert len(_cells()) == 2975
    assert validate_source_cells(_cells()).valid
    assert len(_facts()) == 46
    assert validate_facts(_facts()).valid
    assert validate_consumer_fact_contract(_facts()).valid
    assert {fact.entity.name for fact in _facts()} == {"person"}
    assert {fact.provenance_class for fact in _facts()} == {"administrative"}
    assert {fact.assertion for fact in _facts()} == {"observation"}
    assert {fact.measure.unit for fact in _facts()} == {"count"}
    assert {fact.measure.concept_relation for fact in _facts()} == {"source_label"}
    assert {fact.source.source_sha256 for fact in _facts()} == {SHA256}
    cells = {(cell.sheet_name, cell.address): cell for cell in _cells()}
    keys = {build_source_cell_key(cell) for cell in _cells()}
    records = {record.source_record_id: record for record in _records()}
    for fact in _facts():
        record = records[fact.source_record_id]
        selector = record.spec.selector
        assert selector.sheet_name == SHEET
        assert selector.address[0] in {"D", "F"}
        assert selector.end_address is None
        assert record.spec.divisor_selector is None
        assert record.spec.value_scale == 1
        assert cells[SHEET, selector.address].formula is None
        assert Decimal(str(fact.value)) == Decimal(
            str(cells[SHEET, selector.address].raw_value)
        )
        assert fact.source_cell_keys and set(fact.source_cell_keys) <= keys


def test_nzs_quarter_end_month_and_publisher_period_are_pinned():
    for fact in _facts():
        assert (fact.period.type, fact.period.value) == ("month", "2026-06")
        assert (fact.geography.level, fact.geography.id, fact.geography.name) == (
            "country",
            "NZ",
            "New Zealand",
        )
        assert fact.period_coverage.source_period_label == "Jun-26"
        assert fact.period_coverage.basis == "calendar"
        assert (
            fact.period_coverage.start_date
            == fact.period_coverage.end_date
            == "2026-06-30"
        )
        assert "not a quarterly average or flow" in fact.period_coverage.notes
    # A requested bundle year cannot relabel the pinned June 2026 publisher period.
    assert {
        (fact.period.type, fact.period.value)
        for fact in _package().build_facts(2023, cells=_cells())
    } == {("month", "2026-06")}


@pytest.mark.parametrize(
    ("category", "row", "nzs", "vp", "address"),
    [
        ("recipient_total", "all", 974001, 4674, 29),
        ("additional_support", "as", 47727, 168, 7),
        ("additional_support", "da", 117132, 723, 8),
        ("additional_support", "tas_special_benefit", 13101, 9, 9),
        ("gender", "male", 456150, 2925, 10),
        ("gender", "female", 517776, 1749, 11),
        ("gender", "gender_diverse", 81, 0, 12),
        ("age_group", "under_60", 720, 6, 13),
        ("age_group", "60_64", 6213, 15, 14),
        ("age_group", "65_69", 275655, 588, 15),
        ("age_group", "70_74", 244431, 525, 16),
        ("age_group", "75_79", 207561, 1095, 17),
        ("age_group", "80_84", 130641, 1038, 18),
        ("age_group", "85_89", 73521, 744, 19),
        ("age_group", "90_plus", 35265, 663, 20),
        ("ethnic_group", "european", 710739, 3390, 21),
        ("ethnic_group", "maori", 68148, 639, 22),
        ("ethnic_group", "pacific_peoples", 30426, 45, 23),
        ("ethnic_group", "asian", 68157, 33, 24),
        ("ethnic_group", "melaa", 6306, 3, 25),
        ("ethnic_group", "other_ethnicity", 25866, 42, 26),
        ("ethnicity_reporting_status", "recorded", 871674, 4017, 27),
        ("ethnicity_reporting_status", "not_specified", 102327, 657, 28),
    ],
)
def test_nzs_every_emitted_summary_count_is_an_exact_publisher_cell(
    category, row, nzs, vp, address
):
    for benefit, column, expected in (("nzs", "D", nzs), ("vp", "F", vp)):
        fact = _fact(category, row, benefit)
        assert fact.value == expected
        record = next(
            record
            for record in _records()
            if record.source_record_id == fact.source_record_id
        )
        assert record.spec.selector.address == f"{column}{address}"
        assert fact.filters["msd_nzs_vp.benefit_type"] == benefit


def test_nzs_labels_every_dimension_value_and_keeps_total_response_semantics():
    assert _dimension_label_reports(PACKAGE_ID, consumer_fact_rows(_facts())) == (
        [],
        [],
    )
    for fact in _facts():
        for dimension, value in fact.filters.items():
            assert fact.dimension_labels[dimension]
            assert fact.dimension_value_labels[dimension][str(value)]
        assert fact.layout.groupby_dimension_label
    assert _fact("age_group", "under_60", "nzs").dimension_value_labels[
        "msd_nzs_vp.age_group"
    ] == {"under_60": "Under 60 years"}
    assert _fact(
        "additional_support", "tas_special_benefit", "nzs"
    ).dimension_value_labels["msd_nzs_vp.additional_support"] == {
        "tas_special_benefit": "Temporary Additional Support/Special Benefit"
    }
    for benefit in ("nzs", "vp"):
        fact = _fact("ethnic_group", "maori", benefit)
        assert (
            "Total response ethnicity means people can appear more than once"
            in fact.measure.concept_evidence_notes
        )
        assert "randomly rounded to base 3" in fact.measure.concept_evidence_notes
    # AS counts in this package refer only to NZS/VP recipients; they are not
    # the national all-status AS recipients or an AS-by-W&I-region status split.
    assert (
        _fact("additional_support", "as", "nzs").filters["msd_nzs_vp.benefit_type"]
        == "nzs"
    )
    assert (
        _fact("additional_support", "as", "vp").filters["msd_nzs_vp.benefit_type"]
        == "vp"
    )


@pytest.mark.parametrize("field", ["dimension_labels", "dimension_value_labels"])
def test_nzs_missing_dimension_or_value_labels_are_rejected_by_bundle_guard(field):
    rows = deepcopy(consumer_fact_rows(_facts()))
    for row in rows:
        row[field].pop("msd_nzs_vp.benefit_type")
    errors, _ = _dimension_label_reports(PACKAGE_ID, rows)
    assert errors
    assert {error.code for error in errors} == {
        "missing_dimension_label"
        if field == "dimension_labels"
        else "missing_dimension_value_label"
    }


@pytest.mark.parametrize("address", _guard_addresses())
def test_nzs_every_guard_and_header_rejects_mutated_publisher_cell(address):
    changed = [
        replace(cell, raw_value="unexpected publisher layout")
        if (cell.sheet_name, cell.address) == (SHEET, address)
        else cell
        for cell in _cells()
    ]
    with pytest.raises(ValueError, match="expected|header|guard"):
        _package().build_facts(2026, cells=changed)


@pytest.mark.parametrize("address", TYPE_GUARD_ADDRESSES)
def test_nzs_each_record_set_and_benefit_rejects_non_numeric_value(address):
    changed = [
        replace(cell, raw_value="S", cell_type="text")
        if (cell.sheet_name, cell.address) == (SHEET, address)
        else cell
        for cell in _cells()
    ]
    with pytest.raises(ValueError, match="expected cell type"):
        _package().build_facts(2026, cells=changed)


def test_nzs_single_source_bundle_coverage_has_no_duplicate_keys():
    coverage = build_bundle_coverage(consumer_fact_rows(_facts()))
    assert coverage["fact_count"] == 46
    assert coverage["counts"]["by_source"] == {"msd": 46}
    assert coverage["counts"]["by_period"] == {"month:2026-06": 46}
    assert coverage["counts"]["by_geography"] == {"country:NZ": 46}
    assert coverage["counts"]["by_entity"] == {"person": 46}
    assert coverage["counts"]["by_source_table"] == {
        "msd:New Zealand Superannuation and Veteran's Pension - June 2026": 46
    }
    assert coverage["duplicates"] == {
        "aggregate_fact_keys": [],
        "semantic_fact_keys": [],
    }


def test_nzs_build_suite_passes_source_acceptance(tmp_path):
    report = build_source_suite(PACKAGE_PATH, tmp_path / "suite", year=2026)
    assert report.valid
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
    assert report.source_cells.cell_count == 2975
    assert report.source_records.resolved_count == 46
    assert report.source_records.lineage_coverage == 1
    assert report.consumer_facts.fact_count == 46
    assert report.agent_acceptance.counts["raw_artifact_count"] == 1
    assert report.agent_acceptance.counts["raw_r2_link_count"] == 1
