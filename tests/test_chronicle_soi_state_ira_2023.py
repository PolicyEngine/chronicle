"""IRS SOI TY2023 state-data US totals and IRA Tables 5/6.

``soi-state-2023`` reads the United States workbook of the TY2023 state data
(``23in54us.xlsx``); ``soi-ira-traditional-contributions-2023`` and
``soi-ira-roth-contributions-2023`` read IRA Tables 5 and 6 of the June 2026
IRA study (``23in05ira.xlsx``, ``23in06ira.xlsx``). Each mirrors its TY2022
twin with literal TY2023 labels. The workbooks' layouts moved, and the
packages move with them:

- 23in54us.xlsx: the geography label moved from A8 to B3, the "All returns"
  header from row 3 to row 4, and the EITC block two rows down.
- The IRA tables use an "Estimates" sheet with "All taxpayers" on row 7.

The expected values are read with openpyxl directly, not through Chronicle's
cell parser.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import openpyxl
import pytest
import yaml

from chronicle.core import validate_facts
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package
from chronicle.sources.cells import validate_source_cells
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "db" / "data" / "irs_soi"
PACKAGES_ROOT = REPO_ROOT / "packages"

# package -> (TY2022 twin, manifest, workbook, sha256, size, sheet,
#             {source_record_id suffix: (cell, scale)})
PACKAGES = {
    "soi-state-2023": (
        "soi-state-2022",
        DATA / "state_2023" / "manifest.yaml",
        DATA / "state_2023" / "23in54us.xlsx",
        "4bc45f2586fb924c1e0e7818773096bdcf71223b6407120ca058efaed728607a",
        265_549,
        "Sheet1",
        {
            "state_2023.us.return_count.all_returns.return_count": ("B9", 1),
            "state_2023.us.adjusted_gross_income.all_returns.amount": ("B26", 1000),
            (
                "state_2023.us.eitc_three_or_more_children_returns."
                "three_or_more_qualifying_children.return_count"
            ): ("B146", 1),
            (
                "state_2023.us.eitc_three_or_more_children_amount."
                "three_or_more_qualifying_children.amount"
            ): ("B147", 1000),
        },
    ),
    "soi-ira-traditional-contributions-2023": (
        "soi-ira-traditional-contributions-2022",
        DATA / "ira_contributions" / "manifest_traditional_2023_source_package.yaml",
        DATA / "ira_contributions" / "23in05ira.xlsx",
        "17b02670eeb35dab5d3f8be6a26333d527993f8b22933fa77bb3a06f3c8ad143",
        11_345,
        "Estimates",
        {
            "traditional_ira_contributions.all_taxpayers.all_taxpayers.taxpayer_count": (
                "B7",
                1,
            ),
            "traditional_ira_contributions.all_taxpayers.all_taxpayers.amount": (
                "C7",
                1000,
            ),
        },
    ),
    "soi-ira-roth-contributions-2023": (
        "soi-ira-roth-contributions-2022",
        DATA / "ira_contributions" / "manifest_roth_2023_source_package.yaml",
        DATA / "ira_contributions" / "23in06ira.xlsx",
        "b526e4d4163172ed9992d16375cbf601b1c8b4d5bcf66f86e038c0e91c420418",
        11_380,
        "Estimates",
        {
            "roth_ira_contributions.all_taxpayers.all_taxpayers.taxpayer_count": (
                "B7",
                1,
            ),
            "roth_ira_contributions.all_taxpayers.all_taxpayers.amount": ("C7", 1000),
        },
    ),
}
PUBLISHED = {
    # Spot values from the publisher files, as printed.
    "irs_soi.ty2023.state_2023.us.return_count.all_returns.return_count": 159_949_000,
    "irs_soi.ty2023.traditional_ira_contributions.all_taxpayers.all_taxpayers."
    "taxpayer_count": 5_873_053,
    "irs_soi.ty2023.roth_ira_contributions.all_taxpayers.all_taxpayers."
    "taxpayer_count": 9_488_414,
}


def _build(package_id: str, year: int):
    package = load_source_package(package_id)
    rows = package.build_source_rows(year)
    cells = package.build_source_cells(year, source_rows=rows)
    return cells, package.build_facts(year, cells=cells, source_rows=rows)


@pytest.fixture(scope="module")
def built():
    facts_by_package = {}
    for package_id in PACKAGES:
        cells, facts = _build(package_id, 2023)
        assert validate_source_cells(cells).valid
        assert validate_facts(facts).valid
        facts_by_package[package_id] = facts
    return facts_by_package


def _cell(workbook: Path, sheet: str, address: str):
    book = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    try:
        return book[sheet][address].value
    finally:
        book.close()


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_manifest_registers_the_publisher_file(package_id):
    _, manifest_path, workbook, sha256, size, _, _ = PACKAGES[package_id]
    entry = yaml.safe_load(manifest_path.read_text())["files"][2023]

    assert hashlib.sha256(workbook.read_bytes()).hexdigest() == sha256
    assert entry["filename"] == workbook.name
    assert entry["source_url"] == f"https://www.irs.gov/pub/irs-soi/{workbook.name}"
    assert entry["sha256"] == sha256
    assert entry["size_bytes"] == size == workbook.stat().st_size
    assert entry["storage"]["r2"]["key"].endswith(f"/2023/{sha256}/{workbook.name}")


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_each_fact_is_its_publisher_cell(built, package_id):
    _, _, workbook, sha256, _, sheet, expected = PACKAGES[package_id]
    facts = {fact.source_record_id: fact for fact in built[package_id]}

    assert set(facts) == {f"irs_soi.ty2023.{suffix}" for suffix in expected}
    for suffix, (address, scale) in expected.items():
        fact = facts[f"irs_soi.ty2023.{suffix}"]
        assert fact.value == _cell(workbook, sheet, address) * scale, suffix
        assert fact.period.type == "tax_year"
        assert fact.period.value == 2023
        assert fact.source.source_sha256 == sha256
        assert fact.source.vintage == "tax_year_2023"
        assert fact.geography.id == "0100000US"
        if fact.measure.legal_vintage is not None:
            assert fact.measure.legal_vintage == "tax_year_2023"
    for record_id, value in PUBLISHED.items():
        if record_id in facts:
            assert facts[record_id].value == value


def test_state_totals_equal_the_historic_table_2_us_row(built):
    """Differential across two publisher files: the TY2023 United States
    workbook and the TY2023 Historic Table 2 CSV (US, AGI stub 0) report the
    same totals."""
    csv_path = DATA / "historic_table_2" / "23in55cmcsv.csv"
    if not csv_path.exists():
        pytest.skip("23in55cmcsv.csv arrives with chronicle#291")
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        us = next(
            row
            for row in csv.DictReader(handle)
            if row["STATE"] == "US" and row["AGI_STUB"] == "0"
        )
    by_measure = {
        fact.source_record_id.split(".")[4]: fact.value
        for fact in built["soi-state-2023"]
    }
    variables = {
        "return_count": ("N1", 1),
        "adjusted_gross_income": ("A00100", 1000),
        "eitc_three_or_more_children_returns": ("N59664", 1),
        "eitc_three_or_more_children_amount": ("A59664", 1000),
    }
    for measure, (variable, scale) in variables.items():
        assert by_measure[measure] == int(us[variable].replace(",", "")) * scale


@pytest.mark.parametrize("build_year", [2022, 2024])
def test_building_at_another_year_does_not_relabel_the_2023_files(built, build_year):
    for package_id in PACKAGES:
        _, other = _build(package_id, build_year)
        assert sorted((f.source_record_id, f.value, f.period.value) for f in other) == (
            sorted(
                (f.source_record_id, f.value, f.period.value) for f in built[package_id]
            )
        )


def _declarations(package_id: str) -> dict:
    path = PACKAGES_ROOT / SOURCE_PACKAGE_ALIASES[package_id] / "source_package.yaml"
    return yaml.safe_load(path.read_text())


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_packages_mirror_their_2022_twins(package_id):
    """Differential: apart from year labels, file locations and the cell
    positions the TY2023 layout moved, the declarations equal TY2022's."""
    text = (
        PACKAGES_ROOT / SOURCE_PACKAGE_ALIASES[package_id] / "source_package.yaml"
    ).read_text()
    assert "{year}" not in text

    def normalised(spec: dict) -> dict:
        spec = json.loads(json.dumps(spec))
        for key in ("package_id", "label"):
            spec.pop(key)
        for key in (
            "vintage",
            "extracted_at",
            "artifact_year",
            "manifest",
            "resource_directory",
        ):
            spec["artifact"].pop(key, None)
        for record_set in spec["record_sets"]:
            for key in (
                "record_set_id",
                "source_record_id_prefix",
                "period",
                "sheet_name",
            ):
                record_set.pop(key)
            for row in record_set["rows"]:
                row.pop("row_number")
                for guard in row.get("guard_cells", ()):
                    guard.pop("row", None)
                    guard.pop("column", None)
            for measure in record_set["measures"]:
                for key in (
                    "legal_vintage",
                    "expected_column_header_row",
                    "expected_column_header",
                ):
                    measure.pop(key, None)
        return spec

    twin = PACKAGES[package_id][0]
    assert normalised(_declarations(package_id)) == normalised(_declarations(twin))


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_source_suite_passes_agent_acceptance(package_id, tmp_path):
    suite = build_source_suite(package_id, tmp_path / package_id, year=2023)

    assert suite.agent_acceptance.valid
    assert suite.agent_acceptance.counts["row_semantic_error_count"] == 0
