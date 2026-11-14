"""Registers of Scotland's sales over £1 million for PolicyEngine/chronicle#420 item 13.

Checks the package scripts/build_uk_ros_high_value_sales_package.py writes from RoS's
Property Market Report 2025-26 data tables 9 and 10. Values are re-read from the pinned
workbook with openpyxl, and each fact's cell is found from the fact's own measure,
financial year and local authority code, not from the package's coordinates.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
import runpy
from collections import defaultdict
from pathlib import Path

import openpyxl
import pytest
import yaml

from chronicle.artifacts import R2_COUNTRY_PUBLISHERS
from chronicle.bundle import UK_BUNDLE_SOURCE_PREFIXES, UK_BUNDLE_SOURCES
from chronicle.consumer_contract import (
    build_semantic_fact_key,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.geography_names import canonical_geography_name
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "ros-property-market-report-2025-26"
DIRECTORY = "ros/property_market_report_2025_26"
DATA = ROOT / "db/data" / DIRECTORY
SHEETS = {
    "ros.residential_property_sales": ("9", 1),
    "ros.residential_property_sales_value": ("10", 1_000_000),
}
YEARS = {2023: "2023-24", 2024: "2024-25", 2025: "2025-26"}


@pytest.fixture(scope="module")
def built():
    package = load_source_package(PACKAGE_ID)
    return package, package.build_facts(2026)


@pytest.fixture(scope="module")
def workbook():
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text())
    ((_, entry),) = manifest["files"].items()
    content = (DATA / entry["filename"]).read_bytes()
    return openpyxl.load_workbook(io.BytesIO(content), data_only=True)


def test_package_validates_registers_and_carries_no_anchors(built):
    package, facts = built
    report = validate_source_package(package.package_path, year=2026)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["source_record_count"] == len(facts) == 168
    assert SOURCE_PACKAGE_ALIASES[PACKAGE_ID] == Path(DIRECTORY)
    assert PACKAGE_ID in UK_BUNDLE_SOURCES
    # A new UK publisher: in the UK bundle's prefixes and under raw/uk in R2.
    assert "ros" in UK_BUNDLE_SOURCE_PREFIXES
    assert "ros" in R2_COUNTRY_PUBLISHERS["uk"]
    text = (package.package_path / "source_package.yaml").read_text(encoding="utf-8")
    assert not re.search(r"(:|^\s*-)\s+[&*][A-Za-z_][\w-]*\s*$", text, re.M)
    assert validate_facts(facts).valid
    assert len({build_semantic_fact_key(fact) for fact in facts}) == 168
    assert len(package.build_facts(2023)) == 168


def test_generator_reproduces_the_committed_package():
    generator = runpy.run_path(
        str(ROOT / "scripts/build_uk_ros_high_value_sales_package.py")
    )
    ((directory, build),) = generator["BUILDERS"].items()
    committed = ROOT / "packages" / directory / "source_package.yaml"
    assert build() == committed.read_text(encoding="utf-8")


def test_manifest_pins_bytes_licence_and_the_r2_key():
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["source_id"] == "ros"
    assert manifest["package_id"] == PACKAGE_ID
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["attribution"].startswith(
        "Contains Registers of Scotland data © Crown copyright and database right 2026."
    )
    ((year, entry),) = manifest["files"].items()
    content = (DATA / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    assert entry["source_url"] == (
        "https://www.ros.gov.uk/__data/assets/excel_doc/0007/336445/"
        "Online-data-tables-Property-Market-Report-2025-2026.xlsx"
    )
    key = f"raw/uk/ros/{PACKAGE_ID}/{year}/{entry['sha256']}/{entry['filename']}"
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }


def test_consumer_contract_is_valid(built):
    _, facts = built
    report = validate_consumer_fact_contract(facts)
    assert report.valid, report.errors[:3]
    assert all(fact.source.raw_r2_uri for fact in facts)


def test_facts_are_the_published_cells(built, workbook):
    _, facts = built
    for fact in facts:
        sheet, scale = SHEETS[fact.measure.concept]
        worksheet = workbook[sheet]
        label = YEARS[int(fact.period.value)]
        (column,) = [cell.column for cell in worksheet[6] if cell.value == label]
        (row,) = [
            cells[0].row
            for cells in worksheet.iter_rows(min_row=7, max_row=40)
            if cells[2].value == fact.geography.id
        ]
        published = worksheet.cell(row, column).value
        assert math.isclose(fact.value, published * scale, abs_tol=0.5), (
            fact.source_record_id
        )
        assert worksheet.cell(row, 2).value == canonical_geography_name(
            fact.geography.id
        )


def test_councils_add_to_scotland_and_match_band_j(built, workbook):
    _, facts = built
    sums: dict[tuple, float] = defaultdict(float)
    scotland: dict[tuple, float] = {}
    councils = set()
    for fact in facts:
        key = (fact.measure.concept, int(fact.period.value))
        if fact.geography.id == "S92000003":
            scotland[key] = fact.value
        else:
            councils.add(fact.geography.id)
            sums[key] += fact.value
    assert len(councils) == 27  # the tables print no row for the other five
    for key, total in scotland.items():
        assert math.isclose(sums[key], total, abs_tol=1.0), key
    band_sheet = workbook["8"]
    headers = {cell.value: cell.column for cell in band_sheet[6] if cell.value}
    (band_row,) = [
        cells[0].row
        for cells in band_sheet.iter_rows(min_row=7, max_row=20)
        if cells[1].value == "J - over £1,000,000"
    ]
    for year, label in YEARS.items():
        band = band_sheet.cell(band_row, headers[label]).value
        assert band == scotland[("ros.residential_property_sales", year)]


def test_sales_are_flows_with_the_price_band(built):
    _, facts = built
    assert {int(fact.period.value) for fact in facts} == set(YEARS)
    for fact in facts:
        assert fact.period.type == "fiscal_year"
        assert fact.period_coverage.basis == "fiscal"
        assert "not the stock" in fact.period_coverage.notes
        assert fact.filters == {"house_price_band": "over_1m"}
        assert fact.provenance_class == "administrative"
        assert fact.entity.name == "dwelling"
        assert fact.entity.role == "residential_property_sale"
        assert fact.domain == "residential_property_transactions"
        assert (
            "Only true market residential sales" in fact.measure.concept_evidence_notes
        )
        expected_unit = (
            "count"
            if fact.measure.concept == "ros.residential_property_sales"
            else "gbp"
        )
        assert fact.measure.unit == expected_unit
