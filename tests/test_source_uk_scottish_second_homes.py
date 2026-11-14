"""Scotland's second homes and empty dwellings for PolicyEngine/chronicle#435 item 1.

Checks the package scripts/build_uk_scottish_second_homes_package.py writes from the
Scottish Government's "Second homes and empty properties in September 2025" web table.
Values are re-read from the pinned workbook with openpyxl, and each fact's cell is found
from the fact's own class, September and area, not from the package's coordinates.
"""

from __future__ import annotations

import hashlib
import io
import re
import runpy
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
from chronicle.geography_names import canonical_geography_name
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "scotgov-second-homes-empty-properties-2025"
DATA = ROOT / "db/data/scotgov/second_homes_empty_properties_2025"
FACTS = 396  # 6 tables x 2 Septembers x (Scotland + 32 council areas)

# Each class's worksheet, by the package's concept.
SHEETS = {
    "scotgov.council_tax.second_homes_and_empty_properties": "Second Homes Empty Properties",
    "scotgov.council_tax.second_homes": "Second Homes",
    "scotgov.council_tax.empty_properties": "Empty Properties (6 months +)",
    "scotgov.council_tax.long_term_empty_properties": "Long Term Empty 12 Months",
    "scotgov.council_tax.long_term_empty_properties_discount_below_10_percent_or_increase": (
        "Long Term Empty Discount"
    ),
    "scotgov.council_tax.unoccupied_exemptions": "Unoccupied Exemptions",
}
SECOND, EMPTY, LTE, LTE_DISCOUNT, TOTAL, UNOCCUPIED = (
    "scotgov.council_tax.second_homes",
    "scotgov.council_tax.empty_properties",
    "scotgov.council_tax.long_term_empty_properties",
    "scotgov.council_tax.long_term_empty_properties_discount_below_10_percent_or_increase",
    "scotgov.council_tax.second_homes_and_empty_properties",
    "scotgov.council_tax.unoccupied_exemptions",
)
# The web table's own spellings of four council areas.
SPELLINGS = {
    "Argyll & Bute": "Argyll and Bute",
    "Dumfries & Galloway": "Dumfries and Galloway",
    "Edinburgh, City of": "City of Edinburgh",
    "Glasgow": "Glasgow City",
    "Perth & Kinross": "Perth and Kinross",
}


@pytest.fixture(scope="module")
def built():
    package = load_source_package(PACKAGE_ID)
    return package, package.build_facts(2025)


@pytest.fixture(scope="module")
def workbook():
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text())
    ((_, entry),) = manifest["files"].items()
    content = (DATA / entry["filename"]).read_bytes()
    return openpyxl.load_workbook(io.BytesIO(content), data_only=True)


def _squeeze(text: object) -> str:
    return " ".join(str(text).split())


def _by_class(facts) -> dict[tuple[str, str, str], int]:
    """{(concept, period, geography id): value}."""
    values = {}
    for fact in facts:
        key = (fact.measure.concept, fact.period.value, fact.geography.id)
        assert key not in values, key
        values[key] = fact.value
    return values


# ---------------------------------------------------------------- registration


def test_package_validates_registers_and_carries_no_anchors(built):
    package, facts = built
    report = validate_source_package(package.package_path, year=2025)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["source_record_count"] == len(facts) == FACTS
    assert SOURCE_PACKAGE_ALIASES[PACKAGE_ID] == Path(
        "scotgov/second_homes_empty_properties_2025"
    )
    assert PACKAGE_ID in UK_BUNDLE_SOURCES
    text = (package.package_path / "source_package.yaml").read_text(encoding="utf-8")
    assert not re.search(r"(:|^\s*-)\s+[&*][A-Za-z_][\w-]*\s*$", text, re.M)
    assert validate_facts(facts).valid
    keys = Counter(build_semantic_fact_key(fact) for fact in facts)
    assert max(keys.values()) == 1
    assert len(package.build_facts(2023)) == FACTS


def test_generator_reproduces_the_committed_package():
    generator = runpy.run_path(
        str(ROOT / "scripts/build_uk_scottish_second_homes_package.py")
    )
    ((directory, build),) = generator["BUILDERS"].items()
    committed = ROOT / "packages" / directory / "source_package.yaml"
    assert build() == committed.read_text(encoding="utf-8")


def test_manifest_pins_bytes_licence_and_the_r2_key():
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["source_id"] == "scotgov"
    assert manifest["package_id"] == PACKAGE_ID
    assert manifest["publisher"].startswith("Scottish Government")
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-10"
    ((year, entry),) = manifest["files"].items()
    assert year == 2025
    content = (DATA / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    assert entry["source_url"].startswith(
        "https://www.gov.scot/binaries/content/documents/govscot/publications/statistics/"
        "2025/12/second-homes-and-empty-properties-in-september-2025/"
    )
    # `chronicle publish-raw` uploaded the bytes and wrote storage.r2, and
    # `chronicle verify-raw` read the object back.
    key = f"raw/uk/scotgov/{PACKAGE_ID}/{year}/{entry['sha256']}/{entry['filename']}"
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


# ---------------------------------------------------------------- published cells


def _register_name(printed: object) -> str:
    """The register's name for an area as the web table prints it."""
    name = _squeeze(printed)
    if name.lower() == "scotland":
        return "Scotland"
    return SPELLINGS.get(name, name)


def test_facts_are_the_published_cells(built, workbook):
    _, facts = built
    found = Counter()
    for fact in facts:
        worksheet = workbook[SHEETS[fact.measure.concept]]
        year = fact.period.value.removesuffix("-09")
        assert fact.period.value == f"{year}-09"
        (column,) = [
            cell.column
            for cell in worksheet[4]
            if cell.value is not None and _squeeze(cell.value) == year
        ]
        name = canonical_geography_name(fact.geography.id)
        (row,) = [
            cells[0].row
            for cells in worksheet.iter_rows(min_row=5, max_row=37)
            if _register_name(cells[0].value) == name
        ]
        assert worksheet.cell(row, column).value == fact.value, fact.source_record_id
        found[fact.measure.concept] += 1
    assert found == {concept: 66 for concept in SHEETS}


def test_council_areas_add_to_scotland_but_for_one_misprinted_cell(built):
    _, facts = built
    sums: dict[tuple[str, str], int] = defaultdict(int)
    scotland: dict[tuple[str, str], int] = {}
    for fact in facts:
        key = (fact.measure.concept, fact.period.value)
        if fact.geography.id == "S92000003":
            assert fact.layout.table_record_kind == "total"
            scotland[key] = fact.value
        else:
            assert fact.geography.level == "local_authority"
            assert fact.geography.id.startswith("S12")
            sums[key] += fact.value
    assert len(scotland) == len(sums) == 12
    gaps = {
        key: sums[key] - scotland[key] for key in scotland if sums[key] != scotland[key]
    }
    # The Scotland row of the long-term empty discount table at September 2025 transposes
    # two digits: the councils add to the figure the edition's empty homes page gives.
    assert gaps == {(LTE_DISCOUNT, "2025-09"): 630}


def test_classes_add_to_the_total_and_nest(built):
    _, facts = built
    values = _by_class(facts)
    areas = {geography for (_, _, geography) in values}
    assert len(areas) == 33
    for period in ("2024-09", "2025-09"):
        for area in areas:
            second, empty, total = (
                values[(concept, period, area)] for concept in (SECOND, EMPTY, TOTAL)
            )
            assert second + empty == total, (period, area)
            assert values[(LTE, period, area)] <= empty, (period, area)
            assert values[(LTE_DISCOUNT, period, area)] <= values[(LTE, period, area)]


# ---------------------------------------------------------------- semantics


def test_septembers_roles_and_caveats_travel_with_the_facts(built):
    _, facts = built
    assert {fact.period.value for fact in facts} == {"2024-09", "2025-09"}
    for fact in facts:
        assert fact.period.type == "month"
        year = fact.period.value[:4]
        assert fact.period_coverage.source_period_label == f"September {year}"
        assert "'Data presented for September each year'" in fact.period_coverage.notes
        assert ("Note 13:" in fact.period_coverage.notes) == (year == "2024")
        assert fact.provenance_class == "administrative"
        assert fact.domain == "council_tax_stock"
        assert fact.entity.name == "dwelling"
        expected_role = (
            "exempt_dwelling"
            if fact.measure.concept == UNOCCUPIED
            else "chargeable_dwelling"
        )
        assert fact.entity.role == expected_role
        assert fact.measure.concept_authority == "scotgov"
        assert fact.measure.unit == "count"
        assert fact.filters == {}
        notes = fact.measure.concept_evidence_notes
        assert notes.startswith(
            "Second homes and empty properties in September 2025, web table, sheet "
        )
        if fact.measure.concept in (EMPTY, LTE, TOTAL):
            assert "will therefore be overstated in such instances" in notes  # note 10
            assert "(South Ayrshire)" in notes  # note 11
        if fact.measure.concept in (SECOND, TOTAL):
            assert "furnished and lived in for at least 25 days" in notes
            assert "up to 100% council tax premium" in notes  # note 14
        if fact.measure.concept in (LTE, LTE_DISCOUNT):
            assert "From 1st April 2013" in notes  # note 2
        assert "Note 1: 'Trends over time" in notes


def test_one_name_per_area_and_the_register_codes(built):
    _, facts = built
    names = defaultdict(set)
    for fact in facts:
        names[fact.geography.id].add(fact.geography.name)
        assert canonical_geography_name(fact.geography.id) is not None
    assert all(len(spellings) == 1 for spellings in names.values()), names
    assert names["S92000003"] == {"Scotland"}
    assert names["S12000036"] == {"Edinburgh, City of"}
    assert names["S12000049"] == {"Glasgow City"}
    assert sum(code.startswith("S12") for code in names) == 32
