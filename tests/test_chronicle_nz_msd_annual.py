"""Publisher-cell fidelity for MSD's FY2024/25 benefit expense actuals."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

from chronicle.artifacts import build_r2_key
from chronicle.bundle import _dimension_label_reports, build_bundle_coverage
from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources import build_source_cell_key, validate_source_cells
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
ALIAS = "msd-annual-report-benefit-expenses-2025"
DIRECTORY = Path("msd/annual_report_benefit_expenses_2025")
PACKAGE = REPO_ROOT / "packages" / DIRECTORY
DATA = REPO_ROOT / "db" / "data" / DIRECTORY
FILENAME = "msd-annual-report-2025.pdf"
SHA256 = "991a524e9cc6de7de1b75f07122aa0d5452a4d5303433bdbfccc316a481fa3c6"
SOURCE_URL = (
    "https://www.msd.govt.nz/documents/about-msd-and-our-work/"
    "publications-resources/corporate/annual-report/2025/" + FILENAME
)

# Page 182, extracted lines 19–29: the second numeric column is Actual 2025,
# not Actual 2024. Values are in the publisher's $000 units.
ACTUALS = [
    (4963, "Accommodation Assistance", 2_232_026),
    (4965, "Disability Assistance", 491_784),
    (4967, "Hardship Assistance", 754_599),
    (4969, "Jobseeker Support and Emergency Benefit", 4_640_562),
    (4971, "New Zealand Superannuation", 23_191_199),
    (4973, "Orphan's/Unsupported Child's Benefit", 402_311),
    (4975, "Sole Parent Support", 2_255_092),
    (4977, "Student Allowances", 573_646),
    (4979, "Supported Living Payment", 2_668_450),
    (4981, "Other Benefits or Related Expenses", 1_057_867),
    (4983, "Total Benefits or Related Expenses", 38_267_536),
]


@lru_cache
def _package():
    return load_source_package(PACKAGE)


@lru_cache
def _cells():
    return _package().build_source_cells(2025)


@lru_cache
def _facts():
    return _package().build_facts(2025, cells=_cells())


@lru_cache
def _records():
    return _package().build_source_records(2025, cells=_cells())


def test_msd_annual_package_validation_and_alias():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == DIRECTORY
    assert _package().package_id == ALIAS
    report = validate_source_package(PACKAGE, year=2025)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts == {
        "record_set_count": 1,
        "row_count": 11,
        "measure_count": 1,
        "source_record_count": 11,
        "source_region_count": 1,
    }


def test_msd_annual_original_pdf_and_receipt_provenance():
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text())
    artifact = manifest["files"][2025]
    assert manifest["source_id"] == "msd"
    assert manifest["package_id"] == ALIAS
    assert artifact["filename"] == FILENAME
    assert artifact["source_url"] == SOURCE_URL
    assert artifact["fetched_at"] == "2026-10-07T19:22:33Z"
    assert artifact["sha256"] == SHA256
    assert hashlib.sha256((DATA / FILENAME).read_bytes()).hexdigest() == SHA256
    assert (DATA / FILENAME).stat().st_size == artifact["size_bytes"] == 2_214_729
    key = build_r2_key(
        source_id="msd",
        package_id=ALIAS,
        year=2025,
        sha256=SHA256,
        filename=FILENAME,
        package_path=PACKAGE,
    )
    assert key == f"raw/nz/msd/{ALIAS}/2025/{SHA256}/{FILENAME}"
    assert artifact["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }
    for fact in _facts():
        assert fact.source.source_sha256 == SHA256
        assert fact.source.source_size_bytes == 2_214_729
        assert fact.source.url == SOURCE_URL
        assert fact.source.raw_r2_uri == f"r2://ledger-raw/{key}"


@pytest.mark.parametrize("row,component,raw", ACTUALS)
def test_msd_annual_exact_published_actual_cells(row, component, raw):
    cells = {cell.address: cell for cell in _cells()}
    assert cells[f"A{row}"].raw_value == 182
    assert cells[f"B{row}"].raw_value == 19 + (row - 4963) // 2
    assert component in cells[f"C{row}"].raw_value
    assert cells[f"D{row}"].raw_value == f"{raw:,}"
    assert cells[f"E{row}"].raw_value == raw
    fact = next(
        fact
        for fact in _facts()
        if fact.filters["benefit_expense_component"] == component
    )
    assert fact.value == raw * 1000
    assert fact.measure.unit == "nzd"
    assert build_source_cell_key(cells[f"E{row}"]) in fact.source_cell_keys
    assert fact.layout.table_record_kind == ("total" if row == 4983 else "detail")


def test_msd_annual_published_total_is_not_computed():
    record = next(
        record for record in _records() if record.spec.selector.address == "E4983"
    )
    assert record.spec.selector.end_address is None
    assert record.spec.divisor_selector is None
    assert record.spec.value_scale == 1000
    assert len(_facts()) == 11
    assert {fact.filters["benefit_expense_component"] for fact in _facts()} == {
        component for _, component, _ in ACTUALS
    }
    assert all("average" not in fact.measure.concept for fact in _facts())


def test_msd_annual_full_document_cells_and_publisher_lineage():
    cells = _cells()
    facts = _facts()
    assert len(cells) == 35_136
    assert {cell.sheet_name for cell in cells} == {"document_numbers"}
    assert {cell.raw_value for cell in cells if cell.column_number == 1} == {
        "page_number",
        *range(1, 210),
    }
    # The publisher's 210th page has no extractable text. The full-document
    # numeric parser visits it but has no text number to turn into a cell.
    document = PdfReader(DATA / FILENAME)
    assert len(document.pages) == 210
    assert document.pages[-1].extract_text() == ""
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert {fact.provenance_class for fact in facts} == {"administrative"}
    assert {fact.assertion for fact in facts} == {"observation"}
    cell_keys = {build_source_cell_key(cell) for cell in cells}
    assert all(fact.source_cell_keys for fact in facts)
    assert all(set(fact.source_cell_keys) <= cell_keys for fact in facts)
    by_address = {cell.address: cell for cell in cells}
    records = {record.source_record_id: record for record in _records()}
    for fact in facts:
        record = records[fact.source_record_id]
        assert record.spec.selector.end_address is None
        assert record.spec.divisor_selector is None
        raw = by_address[record.spec.selector.address].raw_value
        assert Decimal(str(fact.value)) == Decimal(str(raw)) * 1000


def test_msd_annual_fiscal_period_and_scope_are_explicit():
    for fact in _facts():
        assert (fact.period.type, fact.period.value) == ("fiscal_year", 2024)
        assert (fact.geography.level, fact.geography.id) == ("country", "NZ")
        assert fact.geography.name == "New Zealand"
        assert fact.entity.name == "government"
        coverage = fact.period_coverage
        assert coverage.basis == "fiscal"
        assert coverage.source_period_label == "2025"
        assert coverage.start_date == "2024-07-01"
        assert coverage.end_date == "2025-06-30"
    fact = next(
        fact
        for fact in _facts()
        if fact.filters["benefit_expense_component"] == "Accommodation Assistance"
    )
    assert fact.measure.source_concept == "msd.benefits_or_related_expenses"
    assert "does not define which payments it includes" in (
        fact.measure.concept_evidence_notes
    )
    assert "No AS-only scope is asserted" in fact.measure.concept_evidence_notes


def test_msd_annual_labels_and_single_source_coverage():
    rows = consumer_fact_rows(_facts())
    assert _dimension_label_reports(ALIAS, rows) == ([], [])
    for fact in _facts():
        component = fact.filters["benefit_expense_component"]
        assert fact.dimension_value_labels["benefit_expense_component"] == {
            component: component
        }
        assert fact.layout.groupby_dimension_label == "Benefit expense component"
    coverage = build_bundle_coverage(rows)
    assert coverage["fact_count"] == 11
    assert coverage["counts"]["by_source"] == {"msd": 11}
    assert coverage["counts"]["by_geography"] == {"country:NZ": 11}
    assert coverage["counts"]["by_period"] == {"fiscal_year:2024": 11}
    assert coverage["counts"]["by_entity"] == {"government": 11}
    assert coverage["duplicates"] == {
        "aggregate_fact_keys": [],
        "semantic_fact_keys": [],
    }


def test_msd_annual_build_suite_acceptance(tmp_path):
    report = build_source_suite(PACKAGE, tmp_path / "annual-suite", year=2025)
    assert report.valid, report.to_dict()
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
    assert report.source_records.resolved_count == 11
    assert report.source_records.lineage_coverage == 1
    assert report.source_cells.cell_count == 35_136
    assert report.consumer_facts.fact_count == 11
    assert report.agent_acceptance.counts["raw_artifact_count"] == 1
    assert report.agent_acceptance.counts["raw_r2_link_count"] == 1


# Every authored guard address and every row/column header has its own drift
# regression. Mutations affect parsed source cells, leaving original PDF bytes
# unchanged. Shared guards appear once here, though used by every expense row.
GUARD_ADDRESSES = [
    ("C3", "report fiscal-year end date"),
    ("C4959", "expense table actual-year columns"),
    ("D4959", "selected Actual 2025 column"),
    ("F4959", "expense table actual-year and units context"),
    ("E1", "column header"),
    *[
        (f"{column}{row}", message)
        for row, _, _ in ACTUALS
        for column, message in (
            ("A", "PDF page number"),
            ("B", "PDF extracted line number"),
            ("C", "row header"),
            ("D", "source Actual 2025 number text"),
        )
    ],
]


@pytest.mark.parametrize("address,message", GUARD_ADDRESSES)
def test_msd_annual_every_guard_rejects_source_drift(address, message):
    changed = [
        replace(cell, raw_value="unexpected publisher layout")
        if cell.address == address
        else cell
        for cell in _cells()
    ]
    with pytest.raises(ValueError, match=message):
        _package().build_facts(2025, cells=changed)


def test_msd_annual_selected_value_rejects_non_numeric_type():
    changed = [
        replace(cell, cell_type="text") if cell.address == "E4963" else cell
        for cell in _cells()
    ]
    with pytest.raises(ValueError, match="type"):
        _package().build_facts(2025, cells=changed)
