"""DESNZ's domestic payment methods by region for PolicyEngine/chronicle#420 item 12.

Checks the packages scripts/build_uk_qep_payment_method_packages.py writes from
Quarterly Energy Prices tables 2.4.2 (standard electricity), 2.4.3 (Economy 7 and other
time of use electricity) and 2.5.2 (gas). Values are re-read from the pinned workbooks
with openpyxl, and each fact's cell is found from the fact's own period, region and
payment method, not from the package's coordinates.
"""

from __future__ import annotations

import hashlib
import io
import re
import runpy
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
import pytest
import yaml

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import (
    build_semantic_fact_key,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "db/data"

PACKAGES = {
    # package id: (directory, table, metering arrangement, facts)
    "desnz-qep-electricity-payment-methods-2026": (
        "desnz/qep_electricity_payment_methods_2026",
        "2.4.2",
        "standard",
        627,
    ),
    "desnz-qep-time-of-use-electricity-payment-methods-2026": (
        "desnz/qep_time_of_use_electricity_payment_methods_2026",
        "2.4.3",
        "economy_7_and_time_of_use",
        627,
    ),
    "desnz-qep-gas-payment-methods-2026": (
        "desnz/qep_gas_payment_methods_2026",
        "2.5.2",
        None,
        561,
    ),
}
HEADINGS = {
    "standard_credit": "Credit (%)",
    "direct_debit": "Direct Debit (%)",
    "prepayment": "Prepayment (%)",
}
QUARTERS = {1: "Jan – Mar", 2: "Apr – Jun", 3: "Jul – Sep", 4: "Oct – Dec"}
# How the tables print the nations and unions Chronicle codes.
AREA_LABELS = {
    "K04000001": {"England & Wales"},
    "S92000003": {"Scotland"},
    "K03000001": {"Great Britain"},
    "N92000002": {"Northern Ireland"},
    "K02000001": {"United Kingdom", "UK"},
}
# #420: each published quarter from April 2024; the tables run to June 2026.
QUARTER_PERIODS = {
    "2024-Q2",
    "2024-Q3",
    "2024-Q4",
    "2025-Q1",
    "2025-Q2",
    "2025-Q3",
    "2025-Q4",
    "2026-Q1",
    "2026-Q2",
}


@pytest.fixture(scope="module")
def built():
    packages = {}
    for package_id in PACKAGES:
        package = load_source_package(package_id)
        packages[package_id] = (package, package.build_facts(2026))
    return packages


def _workbook(directory: str):
    manifest = yaml.safe_load((DATA / directory / "manifest.yaml").read_text())
    ((_, entry),) = manifest["files"].items()
    content = (DATA / directory / entry["filename"]).read_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # the workbooks' charts
        return openpyxl.load_workbook(io.BytesIO(content), data_only=True)


def _squeeze(text: object) -> str:
    return " ".join(str(text).split())


def _published(worksheet) -> dict[tuple, dict[str, object]]:
    """{(year, quarter or None, region label): {heading: value}} for one sheet."""
    header = next(
        row[0].row
        for row in worksheet.iter_rows(max_col=1)
        if _squeeze(row[0].value) == "Year"
    )
    headings = {
        _squeeze(cell.value): cell.column
        for cell in worksheet[header]
        if cell.value is not None
    }
    quarterly = "Quarter" in headings
    values = {}
    for row in worksheet.iter_rows(min_row=header + 1):
        if row[0].value in (None, ""):
            break
        year = int(str(row[0].value).strip())
        if quarterly:
            key = (year, row[1].value, row[2].value)
        else:
            key = (year, None, row[1].value)
        values[key] = {
            heading: worksheet.cell(row[0].row, column).value
            for heading, column in headings.items()
            if heading in HEADINGS.values()
        }
    return values


def _region_labels(fact) -> set[str]:
    if fact.geography.id.startswith("desnz:qep:pes:"):
        return {fact.geography.name}
    return AREA_LABELS[fact.geography.id]


# ---------------------------------------------------------------- registration


def test_packages_validate_register_and_carry_no_anchors(built):
    for package_id, (package, facts) in built.items():
        directory, _, _, count = PACKAGES[package_id]
        report = validate_source_package(package.package_path, year=2026)
        assert report.valid, report.to_dict()
        assert not report.warnings
        assert report.counts["source_record_count"] == len(facts) == count
        assert SOURCE_PACKAGE_ALIASES[package_id] == Path(directory)
        assert package_id in UK_BUNDLE_SOURCES
        text = (package.package_path / "source_package.yaml").read_text(
            encoding="utf-8"
        )
        assert not re.search(r"(:|^\s*-)\s+[&*][A-Za-z_][\w-]*\s*$", text, re.M)
        assert validate_facts(facts).valid
        keys = Counter(build_semantic_fact_key(fact) for fact in facts)
        assert max(keys.values()) == 1, package_id
        assert len(package.build_facts(2023)) == count
    every = Counter(
        build_semantic_fact_key(fact) for _, facts in built.values() for fact in facts
    )
    assert (
        max(every.values()) == 1
    )  # the metering arrangement keeps 2.4.2 and 2.4.3 apart


def test_generator_reproduces_the_committed_packages():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        generator = runpy.run_path(
            str(ROOT / "scripts/build_uk_qep_payment_method_packages.py")
        )
        builders = generator["BUILDERS"]
        assert sorted(builders) == sorted(row[0] for row in PACKAGES.values())
        for directory, build in builders.items():
            committed = ROOT / "packages" / directory / "source_package.yaml"
            assert build() == committed.read_text(encoding="utf-8"), directory


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_manifests_pin_bytes_licence_and_the_r2_key(package_id):
    directory = PACKAGES[package_id][0]
    path = DATA / directory / "manifest.yaml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert manifest["source_id"] == "desnz"
    assert manifest["package_id"] == package_id
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-10"
    ((year, entry),) = manifest["files"].items()
    content = (path.parent / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    assert entry["source_url"].startswith(
        "https://assets.publishing.service.gov.uk/media/"
    )
    key = f"raw/uk/desnz/{package_id}/{year}/{entry['sha256']}/{entry['filename']}"
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }


def test_consumer_contract_is_valid(built):
    for package_id, (_, facts) in built.items():
        report = validate_consumer_fact_contract(facts)
        assert report.valid, (package_id, report.errors[:3])
        assert all(fact.source.raw_r2_uri for fact in facts), package_id


# ---------------------------------------------------------------- published cells


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_facts_are_the_published_cells(built, package_id):
    directory, table, _, count = PACKAGES[package_id]
    workbook = _workbook(directory)
    quarterly = _published(workbook[table])
    annual = _published(workbook[f"{table} (Annual)"])
    _, facts = built[package_id]
    for fact in facts:
        heading = HEADINGS[fact.filters["payment_method"]]
        if fact.period.type == "quarter":
            year, quarter = fact.period.value.split("-Q")
            keys = [
                (int(year), QUARTERS[int(quarter)], label)
                for label in _region_labels(fact)
            ]
            sheet = quarterly
        else:
            assert fact.period.type == "calendar_year"
            keys = [
                (int(fact.period.value), None, label) for label in _region_labels(fact)
            ]
            sheet = annual
        (key,) = [key for key in keys if key in sheet]
        assert sheet[key][heading] == fact.value, fact.source_record_id
    assert len(facts) == count


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_each_regions_shares_add_to_100_within_rounding(built, package_id):
    _, facts = built[package_id]
    totals: dict[tuple, int] = defaultdict(int)
    methods: dict[tuple, set] = defaultdict(set)
    for fact in facts:
        key = (fact.period.type, fact.period.value, fact.geography.id)
        totals[key] += fact.value
        methods[key].add(fact.filters["payment_method"])
    assert all(found == set(HEADINGS) for found in methods.values())
    assert all(abs(total - 100) <= 2 for total in totals.values()), totals


# ---------------------------------------------------------------- semantics


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_periods_regions_and_filters(built, package_id):
    _, _, metering, _ = PACKAGES[package_id]
    _, facts = built[package_id]
    periods = {(fact.period.type, str(fact.period.value)) for fact in facts}
    assert periods == {("quarter", value) for value in QUARTER_PERIODS} | {
        ("calendar_year", "2024"),
        ("calendar_year", "2025"),
    }
    areas = {fact.geography.id for fact in facts}
    pes = {area for area in areas if area.startswith("desnz:qep:pes:")}
    assert len(pes) == 14
    nations = areas - pes
    if package_id == "desnz-qep-gas-payment-methods-2026":
        assert nations == {"K04000001", "S92000003", "K03000001"}
    else:
        assert nations == {
            "K04000001",
            "S92000003",
            "K03000001",
            "N92000002",
            "K02000001",
        }
    fuel = "gas" if metering is None else "electricity"
    for fact in facts:
        expected = {"fuel": fuel, "payment_method": fact.filters["payment_method"]}
        if metering:
            expected["metering_arrangement"] = metering
        assert fact.filters == expected
        assert fact.measure.unit == "percent"
        assert fact.aggregation.method == "share"
        assert fact.provenance_class == "survey_aggregate"
        assert fact.entity.name == "household"
        assert fact.entity.role == "domestic_energy_customer"
        assert fact.domain == "domestic_energy_prices"
        assert "uplifted to Ofgem's total customer numbers" in (
            fact.measure.concept_evidence_notes
        )
        if fact.period.type == "quarter":
            assert fact.period_coverage.basis == "calendar"
    time_of_use = built["desnz-qep-time-of-use-electricity-payment-methods-2026"][1]
    annual = [fact for fact in time_of_use if fact.period.type == "calendar_year"]
    assert all(
        "averages of the rounded quarterly figures" in fact.period_coverage.notes
        for fact in annual
    )
