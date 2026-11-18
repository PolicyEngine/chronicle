"""DWP's young people and work review packages for PolicyEngine/chronicle#442.

Checks the packages scripts/build_uk_young_people_work_review_packages.py writes from
the interim report's analytical annex data tables (Table 28) and the final report's
data tables (Tables 2 and 3). The workbooks are re-read here with a small ODS reader of
the test's own, not the package parser, and each fact is matched to its cell.
"""

from __future__ import annotations

import hashlib
import re
import runpy
import zipfile
from pathlib import Path
from xml.etree import ElementTree

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
INTERIM = "dwp-young-people-pip-lcwra-projections-2026"
FINAL = "dwp-welfare-state-to-working-state-tables-2026"
DIRECTORIES = {
    INTERIM: "dwp/young_people_pip_lcwra_projections_2026",
    FINAL: "dwp/welfare_state_to_working_state_tables_2026",
}
FACT_COUNTS = {INTERIM: 88, FINAL: 29}
CASELOAD = "dwp.benefit_caseload_count"
EXPENDITURE = "dwp.benefit_expenditure_amount"
COST = "dwp.recommended_policy_package_annual_cost"
NEET_RATE = "dwp.neet_rate_projection"
ODS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}


def read_sheet(package_id: str, sheet: str) -> dict[tuple[int, int], object]:
    """{(row, column): value} of one sheet, numbers from office:value, else the text."""
    manifest = yaml.safe_load(
        (ROOT / "db/data" / DIRECTORIES[package_id] / "manifest.yaml").read_text()
    )
    ((_, entry),) = manifest["files"].items()
    path = ROOT / "db/data" / DIRECTORIES[package_id] / entry["filename"]
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("content.xml"))
    table_key = f"{{{ODS['table']}}}"
    office_key = f"{{{ODS['office']}}}"
    for table in root.iter(f"{table_key}table"):
        if table.get(f"{table_key}name") != sheet:
            continue
        cells: dict[tuple[int, int], object] = {}
        row_number = 0
        cell_tags = (f"{table_key}table-cell", f"{table_key}covered-table-cell")
        for row in table.iter(f"{table_key}table-row"):
            values: dict[int, object] = {}
            column = 0
            for cell in row:
                if cell.tag not in cell_tags:
                    continue
                repeat = int(cell.get(f"{table_key}number-columns-repeated", "1"))
                if cell.get(f"{office_key}value-type") == "float":
                    value: object = float(cell.get(f"{office_key}value"))
                else:
                    value = "".join(cell.itertext()).strip() or None
                for _ in range(min(repeat, 64)):
                    column += 1
                    if value is not None:
                        values[column] = value
            repeat_rows = int(row.get(f"{table_key}number-rows-repeated", "1"))
            for offset in range(1, (min(repeat_rows, 64) if values else 1) + 1):
                for column, value in values.items():
                    cells[(row_number + offset, column)] = value
            row_number += repeat_rows
        return cells
    raise KeyError(sheet)


@pytest.fixture(scope="module")
def built():
    return {
        package_id: load_source_package(package_id).build_facts(2026)
        for package_id in DIRECTORIES
    }


def by_measure(facts, concept: str, dimension: str) -> dict[tuple[str, int], float]:
    return {
        (fact.filters[dimension], int(fact.period.value)): fact.value
        for fact in facts
        if fact.measure.concept == concept
    }


@pytest.mark.parametrize("package_id", sorted(DIRECTORIES))
def test_package_validates_registers_and_carries_no_anchors(package_id, built):
    package = load_source_package(package_id)
    facts = built[package_id]
    report = validate_source_package(package.package_path, year=2026)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["source_record_count"] == len(facts) == FACT_COUNTS[package_id]
    assert SOURCE_PACKAGE_ALIASES[package_id] == Path(DIRECTORIES[package_id])
    assert package_id in UK_BUNDLE_SOURCES
    text = (package.package_path / "source_package.yaml").read_text(encoding="utf-8")
    assert not re.search(r"(:|^\s*-)\s+[&*][A-Za-z_][\w-]*\s*$", text, re.M)
    assert validate_facts(facts).valid
    assert len({build_semantic_fact_key(fact) for fact in facts}) == len(facts)
    assert len(package.build_facts(2023)) == len(facts)


def test_generator_reproduces_the_committed_packages():
    generator = runpy.run_path(
        str(ROOT / "scripts/build_uk_young_people_work_review_packages.py")
    )
    assert set(generator["BUILDERS"]) == set(DIRECTORIES.values())
    for directory, build in generator["BUILDERS"].items():
        committed = ROOT / "packages" / directory / "source_package.yaml"
        assert build() == committed.read_text(encoding="utf-8"), directory


@pytest.mark.parametrize("package_id", sorted(DIRECTORIES))
def test_manifest_pins_bytes_licence_and_the_r2_key(package_id):
    data = ROOT / "db/data" / DIRECTORIES[package_id]
    manifest = yaml.safe_load((data / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["source_id"] == "dwp"
    assert manifest["package_id"] == package_id
    assert manifest["license"] == "Open Government Licence v3.0"
    assert (
        "This publication is licensed under the terms of the Open Government Licence v3.0"
        in manifest["license_evidence"]
    )
    ((year, entry),) = manifest["files"].items()
    content = (data / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    assert entry["source_url"].startswith("https://assets.publishing.service.gov.uk/")
    key = f"raw/uk/dwp/{package_id}/{year}/{entry['sha256']}/{entry['filename']}"
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }


@pytest.mark.parametrize("package_id", sorted(DIRECTORIES))
def test_consumer_contract_is_valid(package_id, built):
    facts = built[package_id]
    report = validate_consumer_fact_contract(facts)
    assert report.valid, report.errors[:3]
    assert all(fact.source.raw_r2_uri for fact in facts)


# ------------------------------------------------------------ Table 28 (interim)

T28_ROWS = {  # (benefit, concept): the table's row
    ("uc_health_lcwra", CASELOAD): 7,
    ("uc_health_lcwra", EXPENDITURE): 8,
    ("personal_independence_payment", CASELOAD): 9,
    ("personal_independence_payment", EXPENDITURE): 10,
}


def test_table_28_facts_are_the_cells(built):
    cells = read_sheet(INTERIM, "Table_28")
    assert cells[(2, 1)] == (
        "Table 28: PIP and UCH-LCWRA caseload and expenditure projections, aged 16-24"
    )
    years = {cells[(6, column)]: column for column in range(3, 25)}
    assert list(years) == [f"{y}-{str(y + 1)[2:]}" for y in range(2019, 2041)]
    facts = built[INTERIM]
    for (benefit, concept), row in T28_ROWS.items():
        scale = 1 if concept == CASELOAD else 1_000_000
        values = by_measure(facts, concept, "health_and_disability_benefit")
        for label, column in years.items():
            year = int(label[:4])
            assert values[(benefit, year)] == cells[(row, column)] * scale, (
                benefit,
                concept,
                year,
            )
    assert len(facts) == 4 * 22


def test_table_28_splits_history_from_projections_and_carries_its_semantics(built):
    facts = built[INTERIM]
    for fact in facts:
        year = int(fact.period.value)
        assert fact.period.type == "fiscal_year"
        assert (fact.period_coverage.start_date, fact.period_coverage.end_date) == (
            f"{year}-04-01",
            f"{year + 1}-03-31",
        )
        if year >= 2026:  # 'Period: 2026-27 to 2040-41'
            assert (fact.provenance_class, fact.assertion) == (
                "model_output",
                "source_projection",
            )
        else:
            assert (fact.provenance_class, fact.assertion) == (
                "administrative",
                "observation",
            )
        assert fact.geography.id == "K04000001"  # 'Population: England and Wales'
        assert fact.filters["age_band"] == "16_to_24"
        assert set(fact.filters) == {"age_band", "health_and_disability_benefit"}
        notes = fact.measure.concept_evidence_notes
        assert "should be treated as an indication only" in notes
        if fact.measure.concept == CASELOAD:
            assert (fact.entity.name, fact.measure.unit) == ("person", "count")
            assert "claimants in receipt of the 'limited capability to work'" in notes
        else:
            assert fact.measure.concept == EXPENDITURE
            assert (fact.entity.name, fact.measure.unit) == ("government", "gbp")
            assert "Neither the table nor the annex names a price basis" in notes
    assert sum(1 for fact in facts if int(fact.period.value) < 2026) == 4 * 7


def test_table_28_matches_the_annex_findings(built):
    facts = built[INTERIM]
    caseload = by_measure(facts, CASELOAD, "health_and_disability_benefit")
    spending = by_measure(facts, EXPENDITURE, "health_and_disability_benefit")
    pip = "personal_independence_payment"
    # 'rose from approximately £1.3 billion in the financial year ending 2020 to around
    # £3.3 billion in the financial year ending 2025'
    assert (spending[(pip, 2019)], spending[(pip, 2024)]) == (1.3e9, 3.3e9)
    # 'up to 877,000 and £9.2 billion respectively' (financial year ending 2041)
    assert (caseload[(pip, 2040)], spending[(pip, 2040)]) == (877_000, 9.2e9)
    # 'The LCWRA caseload is projected to rise to 229,000 ... fall to £750 million'
    assert caseload[("uc_health_lcwra", 2040)] == 229_000
    assert spending[("uc_health_lcwra", 2040)] == 750e6


# -------------------------------------------------- Tables 2 and 3 (final report)

T2_EXPECTED = {  # policy area: (row, geography, concept relation)
    "opportunity_and_support_guarantees": (10, "K03000001", "source_label"),
    "health": (11, "E92000001", "source_label"),
    "education": (12, "E92000001", "source_label"),
    "youth_hiring_incentives": (13, "K03000001", "approximate"),
    "welfare_savings": (14, "K02000001", "source_label"),
    "fiscal_offsets": (15, "K02000001", "approximate"),
    "total_net_cost": (16, "K02000001", "approximate"),
}


def test_table_2_facts_are_the_cells_with_each_areas_coverage(built):
    cells = read_sheet(FINAL, "2")
    assert cells[(6, 1)] == (
        "Table 2: Annual cost and saving per policy area in 2036/37, £m, 2026/27 prices"
    )
    assert (cells[(9, 1)], cells[(9, 2)]) == ("Local system reform", "[low]")
    facts = [fact for fact in built[FINAL] if fact.measure.concept == COST]
    assert {fact.filters["policy_area"] for fact in facts} == set(T2_EXPECTED)
    for fact in facts:
        row, geography, relation = T2_EXPECTED[fact.filters["policy_area"]]
        assert fact.value == cells[(row, 2)] * 1_000_000
        assert fact.geography.id == geography
        assert fact.measure.concept_relation == relation
        assert (fact.period.type, int(fact.period.value)) == ("fiscal_year", 2036)
        assert fact.filters["price_basis"] == "2026_27_prices"
        assert (fact.provenance_class, fact.assertion) == (
            "model_output",
            "source_projection",
        )
        assert "should not be regarded as official government analysis" in (
            fact.measure.concept_evidence_notes
        )
    values = {fact.filters["policy_area"]: fact.value for fact in facts}
    total = values.pop("total_net_cost")
    # 'The net cost value is the sum of the gross costs, direct welfare savings from
    # proposed reforms and fiscal offsets'; local system reform rounds to zero.
    assert sum(values.values()) == total == -200e6


def test_table_3_facts_are_the_cells(built):
    cells = read_sheet(FINAL, "3")
    assert (
        cells[(6, 1)]
        == "Table 3: Total NEET rate impact profile, UK, 2026/27 to 2036/27"
    )
    years = {cells[(8, column)]: column for column in range(2, 13)}
    assert list(years) == [f"{y}/{str(y + 1)[2:]}" for y in range(2026, 2037)]
    facts = [fact for fact in built[FINAL] if fact.measure.concept == NEET_RATE]
    rates = by_measure(facts, NEET_RATE, "neet_rate_projection")
    for scenario, row in (("baseline", 9), ("with_report_recommendations", 10)):
        for label, column in years.items():
            assert rates[(scenario, int(label[:4]))] == cells[(row, column)]
    assert len(facts) == 22
    for fact in facts:
        assert fact.geography.id == "K02000001"
        assert (fact.entity.name, fact.measure.unit) == ("person", "percent")
        assert fact.filters["age_band"] == "16_to_24"
    assert rates[("baseline", 2026)] == rates[("with_report_recommendations", 2026)]
    for year in range(2027, 2037):
        assert rates[("with_report_recommendations", year)] < rates[("baseline", year)]
    # 'a NEET rate of around 6.8%' in 2036 (analytical annex, section 2)
    assert round(rates[("with_report_recommendations", 2036)], 1) == 6.8
