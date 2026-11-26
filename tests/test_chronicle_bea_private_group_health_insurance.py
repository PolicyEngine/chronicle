"""BEA NIPA Table 7.8 line 17: employer contributions for private group health insurance.

The package reads series B4923C from the Section 7 workbook BEA published with
its 2026 annual update (30 September 2026). The tests pin each published value,
the guards that tie the selected cell to line 17, the row against BEA's own
flat file, and the coverage statement the facts carry: BEA's estimates include
contributions for retired employees, so the series is not an active-employee
amount (consumer context: PolicyEngine/microcosm#454).
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    artifact_year_restamp_issues,
    load_source_package,
)
from chronicle.sources.cells import validate_source_cells
from policyengine_chronicle.schema import validate_consumer_fact_row

REPO_ROOT = Path(__file__).resolve().parents[1]
ALIAS = "bea-nipa-private-group-health-insurance"
PACKAGE_DIR = REPO_ROOT / "packages" / "bea" / "nipa_private_group_health_insurance"
WORKBOOK_SHA256 = "de1c34e37da9b8b8d765efc0611cc653102373fe522fe9218c7689067b29b7fd"
# Table 7.8 line 17, millions of dollars, and the column each year sits in.
PUBLISHED_MILLIONS = {2023: 923_195, 2024: 977_034, 2025: 1_027_929}
YEAR_COLUMN = {2023: "CA", 2024: "CB", 2025: "CC"}
LINE_17_ROW = 26
HEADER_ROW = 8
# The annual flat file the other bea_nipa packages pin carries the same series
# at an earlier vintage (its manifest records the fetch on 11 May 2026).
FLAT_FILE = (
    REPO_ROOT / "db" / "data" / "bea" / "nipa_total_wages_salaries" / "NipaDataA.txt"
)


def _record_id(year: int) -> str:
    return f"bea_nipa.cy{year}.private_group_health_insurance.b4923c.amount"


def _column_letters(number: int) -> str:
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _variant(tmp_path: Path, edit) -> Path:
    """Copy the package with ``edit`` applied; it still reads the pinned workbook."""
    payload = yaml.safe_load((PACKAGE_DIR / "source_package.yaml").read_text())
    edit(payload)
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    (package_dir / "source_package.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )
    return package_dir


def _row(payload: dict) -> dict:
    return payload["record_sets"][0]["rows"][0]


def _measure(payload: dict) -> dict:
    return payload["record_sets"][0]["measures"][0]


def test_alias_resolves_to_the_package():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == Path(
        "bea/nipa_private_group_health_insurance"
    )
    package = load_source_package(ALIAS)
    assert package.package_id == ALIAS
    assert package.artifact.artifact_year == 2025
    assert package.artifact.sheets == ("T70800-A",)


@pytest.mark.parametrize("year", sorted(PUBLISHED_MILLIONS))
def test_each_published_year_is_the_table_7_8_line_17_cell(year):
    package = load_source_package(ALIAS)
    cells = package.build_source_cells(year)
    records = package.build_source_records(year, cells=cells)
    facts = package.build_facts(year, cells=cells)

    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    # Only the Table 7.8 annual sheet is parsed: 43 rows by 81 columns, sparse.
    assert {cell.sheet_name for cell in cells} == {"T70800-A"}
    assert len(cells) == 3_483
    assert len(facts) == 1
    (fact,) = facts
    (record,) = records

    assert fact.source_record_id == _record_id(year)
    assert fact.value == PUBLISHED_MILLIONS[year] * 1_000_000
    assert isinstance(fact.value, int)
    # The value cell first, then its column header, then the eleven guard cells.
    assert record.source_cell_addresses[:2] == (
        f"{YEAR_COLUMN[year]}{LINE_17_ROW}",
        f"{YEAR_COLUMN[year]}{HEADER_ROW}",
    )
    assert set(record.source_cell_addresses[2:]) == {
        "A1",
        "A2",
        "A5",
        "A8",
        f"A{LINE_17_ROW}",
        f"B{LINE_17_ROW}",
        f"C{LINE_17_ROW}",
        "B21",
        "C21",
        "C11",
        "A43",
    }

    assert fact.period.type == "calendar_year"
    assert fact.period.value == year
    assert fact.geography.id == "0100000US"
    assert fact.geography.level == "country"
    assert fact.entity.name == "person"
    assert fact.entity.role == "employee"
    assert fact.provenance_class == "model_output"
    assert fact.measure.unit == "usd"
    assert fact.measure.concept == "bea_nipa.private_group_health_insurance"
    assert fact.measure.source_concept == (
        "bea_nipa.b4923c_private_group_health_insurance"
    )
    assert fact.measure.concept_relation == "source_label"
    assert fact.measure.concept_authority == "bea"
    assert fact.measure.concept_evidence_url == (
        "https://www.bea.gov/sites/default/files/methodologies/SPI-Methodology.pdf"
    )
    assert fact.filters == {"bea_nipa.series_code": "B4923C"}
    assert [
        (item.variable, item.operator, item.value) for item in fact.constraints
    ] == [("bea_nipa.series_code", "==", "B4923C")]
    assert fact.dimension_labels == {"bea_nipa.series_code": "BEA NIPA series code"}
    assert fact.dimension_value_labels == {
        "bea_nipa.series_code": {"B4923C": "Private group health insurance"}
    }

    assert fact.source.source_name == "bea"
    assert fact.source.source_table == (
        "NIPA Table 7.8. Supplements to Wages and Salaries by Type"
    )
    assert fact.source.source_file == "Section7All_xls.xlsx"
    assert fact.source.url == (
        "https://apps.bea.gov/national/Release/XLS/Survey/Section7All_xls.xlsx"
    )
    assert fact.source.source_sha256 == WORKBOOK_SHA256
    assert fact.source.source_size_bytes == 944_273
    assert fact.source.vintage == "bea_nipa_annual_update_2026_09_30"
    assert fact.source.raw_r2_uri == (
        "r2://ledger-raw/raw/bea/bea-nipa-private-group-health-insurance/2025/"
        f"{WORKBOOK_SHA256}/Section7All_xls.xlsx"
    )


def test_the_declared_series_label_is_the_guarded_line_17_stub():
    package = load_source_package(ALIAS)
    cells = {cell.address: cell for cell in package.build_source_cells(2024)}

    stub = cells[f"B{LINE_17_ROW}"].raw_value
    assert stub == "  Private group health insurance\\3\\"
    declared = package.build_facts(2024)[0].dimension_value_labels[
        "bea_nipa.series_code"
    ]["B4923C"]
    assert stub.strip().removesuffix("\\3\\") == declared
    assert cells[f"C{LINE_17_ROW}"].raw_value == "B4923C"
    assert str(cells[f"A{LINE_17_ROW}"].raw_value) == "17"
    assert cells["A2"].raw_value == "[Millions of dollars]"
    assert cells["A5"].raw_value == "Data published September 30, 2026"


def test_consumer_rows_carry_the_value_the_workbook_digest_and_the_labels():
    package = load_source_package(ALIAS)
    facts = [package.build_facts(year)[0] for year in sorted(PUBLISHED_MILLIONS)]

    assert validate_consumer_fact_contract(facts).valid
    rows = consumer_fact_rows(facts)
    for index, (year, row) in enumerate(zip(sorted(PUBLISHED_MILLIONS), rows), 1):
        validate_consumer_fact_row(row, index, PACKAGE_DIR)
        assert row["value"] == PUBLISHED_MILLIONS[year] * 1_000_000
        assert row["value_type"] == "integer"
        assert row["assertion"] == "observation"
        assert row["period"] == {"type": "calendar_year", "value": year}
        assert row["lineage"]["source_record_id"] == _record_id(year)
        assert row["layout"]["record_set_id"] == (
            f"bea_nipa.cy{year}.private_group_health_insurance"
        )
        assert row["dimensions"] == {"bea_nipa.series_code": "B4923C"}
        assert row["source"]["source_sha256"] == WORKBOOK_SHA256
        assert row["concept_alignment"]["authority"] == "bea"
        assert row["concept_alignment"]["relation"] == "source_label"
        # The exported note carries BEA's two coverage quotations and the
        # scope inference Chronicle draws from them, marked as its own.
        notes = row["concept_alignment"]["evidence_notes"]
        assert (
            '"health insurance purchased by employers for their active and '
            'retired employees"'
        ) in notes
        assert '"active and retired federal civilian employees"' in notes
        assert "Chronicle's reading" in notes
        assert "not an active-employee amount" in notes
        assert row["concept_alignment"]["evidence_url"].endswith(
            "/methodologies/SPI-Methodology.pdf"
        )
    # Three years of one series: one record-set spec, three distinct facts.
    assert {row["layout"]["record_set_spec_id"] for row in rows} == {
        "bea_nipa.private_group_health_insurance.v1"
    }
    assert len({row["aggregate_fact_key"] for row in rows}) == 3
    assert len({row["semantic_fact_key"] for row in rows}) == 3
    # Deterministic: a second build writes the same rows.
    again = consumer_fact_rows(
        [package.build_facts(year)[0] for year in sorted(PUBLISHED_MILLIONS)]
    )
    assert again == rows


@pytest.mark.parametrize("year", [2022, 2026])
def test_a_year_without_a_declared_column_is_refused_not_restamped(year):
    package = load_source_package(ALIAS)

    with pytest.raises(ValueError, match=f"No source artifact for year {year}"):
        package.build_facts(year)


@pytest.mark.parametrize("year", [2022, 2023, 2024, 2026])
def test_no_build_year_restamps_the_artifact_year_cell(year):
    assert artifact_year_restamp_issues(load_source_package(ALIAS), year) == []


@pytest.mark.parametrize(
    ("label", "edit", "message"),
    [
        (
            "line 18 (life insurance)",
            lambda payload: _row(payload).update(row_number=27),
            "expected row header 'B4923C', got 'A2211C'",
        ),
        (
            "line 16 (publicly administered funds)",
            lambda payload: _row(payload).update(row_number=25),
            "expected row header 'B4923C', got 'Y390RC'",
        ),
        (
            "the 2023 column under the 2024 label",
            lambda payload: _measure(payload)["column_by_year"].update({2024: "CA"}),
            "expected column header 2024, got '2023'",
        ),
    ],
)
def test_a_selector_that_leaves_line_17_or_its_year_is_refused(
    tmp_path, label, edit, message
):
    package = load_source_package(_variant(tmp_path, edit))

    with pytest.raises(ValueError) as raised:
        package.build_facts(2024)
    assert message in str(raised.value), label


@pytest.mark.parametrize(
    ("column", "row"),
    [
        ("A", 1),
        ("A", 2),
        ("A", 5),
        ("A", 8),
        ("A", "start"),
        ("B", "start"),
        ("C", "start"),
        ("C", 21),
        ("B", 21),
        ("C", 11),
        ("A", 43),
    ],
)
def test_every_guard_cell_binds(tmp_path, column, row):
    """Each guard is checked against the bytes: a wrong expectation refuses."""

    def edit(payload: dict) -> None:
        guards = _row(payload)["guard_cells"]
        (guard,) = [g for g in guards if g["column"] == column and g["row"] == row]
        guard["expected_value"] = "not what BEA published"

    package = load_source_package(_variant(tmp_path, edit))

    with pytest.raises(ValueError, match="not what BEA published"):
        package.build_facts(2024)


def test_the_guards_cover_the_table_identity():
    payload = yaml.safe_load((PACKAGE_DIR / "source_package.yaml").read_text())
    guards = {
        (guard["column"], guard["row"]): guard["expected_value"]
        for guard in deepcopy(_row(payload)["guard_cells"])
    }

    assert guards[("A", 1)] == "Table 7.8. Supplements to Wages and Salaries by Type"
    assert guards[("A", 2)] == "[Millions of dollars]"
    assert guards[("A", 5)] == "Data published September 30, 2026"
    assert guards[("A", "start")] == 17
    assert guards[("B", "start")] == "  Private group health insurance\\3\\"
    assert guards[("C", "start")] == "B4923C"
    assert _row(payload)["expected_row_header"] == "B4923C"
    assert _measure(payload)["value_scale"] == 1_000_000
    assert _measure(payload)["column_by_year"] == YEAR_COLUMN
    assert _measure(payload)["expected_column_header_by_year"] == {
        year: year for year in YEAR_COLUMN
    }


def test_the_row_matches_the_earlier_pinned_flat_file_except_at_2024_and_2025():
    """Differential: two BEA publications of series B4923C.

    The Section 7 workbook (data published 30 September 2026) and the annual
    flat file the other ``bea_nipa`` packages pin (fetched 11 May 2026) carry
    the same series. They agree for every year from 1948 to 2023. For 2024 the
    flat file has $1,002.920 billion and the workbook $977.034 billion, and
    only the workbook has 2025.
    """
    package = load_source_package(ALIAS)
    cells = {cell.address: cell for cell in package.build_source_cells(2025)}
    workbook = {}
    for number in range(4, 82):
        column = _column_letters(number)
        year = int(cells[f"{column}{HEADER_ROW}"].raw_value)
        workbook[year] = cells[f"{column}{LINE_17_ROW}"].raw_value
    assert sorted(workbook) == list(range(1948, 2026))
    assert {year: workbook[year] for year in PUBLISHED_MILLIONS} == PUBLISHED_MILLIONS

    flat_file = {}
    for line in FLAT_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("B4923C,"):
            _code, year, value = line.split(",", 2)
            flat_file[int(year)] = int(value.strip('"').replace(",", ""))
    assert sorted(flat_file) == list(range(1948, 2025))

    differing = {
        year: (flat_file.get(year), workbook[year])
        for year in workbook
        if flat_file.get(year) != workbook[year]
    }
    assert differing == {2024: (1_002_920, 977_034), 2025: (None, 1_027_929)}
