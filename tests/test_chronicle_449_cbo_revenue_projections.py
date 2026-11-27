"""``cbo-revenue-projections-income-by-source-2026-02`` against CBO's own
workbook (chronicle#449).

The package reads a CSV extract, made when cbo.gov refused automated requests.
CBO reposted the workbook on 2026-02-26. The repost is now registered raw-only
beside the package, and these tests read its sheet "3.Individual Income Tax
Details" with openpyxl: every value in the CSV equals its workbook cell, so the
repost changed none of the package's facts.
"""

from __future__ import annotations

import csv
import hashlib
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest
import yaml

from chronicle.core import validate_facts
from chronicle.source_package import load_source_package

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "db" / "data" / "cbo"
PACKAGE = "cbo-revenue-projections-income-by-source-2026-02"
CSV_PATH = (
    DATA
    / "revenue_projections_income_by_source_2026_02"
    / "cbo_revenue_projections_income_by_source_2026_02.csv"
)
RAW_ONLY = DATA / "revenue_projections_income_by_source_2026_02_raw_only"
WORKBOOK = RAW_ONLY / "51138-2026-02-Revenue.xlsx"
WORKBOOK_SHA256 = "8f5bf6db9b40b4d997ea3932a340515f92b08e035f69e5e603e15791f3ce258c"
WORKBOOK_SIZE = 916_083
SHEET = "3.Individual Income Tax Details"
YEARS = range(2023, 2037)

# CSV row -> the workbook's row label in column A, as CBO prints it (with its
# footnote letter), stripped of trailing spaces.
WORKBOOK_ROWS = {
    "adjusted_gross_income": "Adjusted gross income",
    "wages_and_salaries": "Salaries and wages",
    "taxable_interest_and_ordinary_dividends_excluding_qualified_dividends": (
        "Taxable interest and ordinary dividends (excludes qualified dividends)"
    ),
    "qualified_dividend_income": "Qualified dividends",
    "net_capital_gain": "Capital gain or lossa",
    "net_business_income": (
        "Net business income (all income and loss reported on Schedules C, E, and F)b"
    ),
}


@pytest.fixture(scope="module")
def sheet():
    return openpyxl.load_workbook(WORKBOOK, data_only=True)[SHEET]


def _year_columns(sheet) -> dict[int, int]:
    """Columns by the calendar year in row 9."""
    assert sheet["A9"].value == "Calendar year"
    return {
        int(cell.value): cell.column
        for cell in sheet[9]
        if isinstance(cell.value, (int, float))
    }


def _row(sheet, label: str) -> int:
    rows = [
        row
        for row in range(10, sheet.max_row + 1)
        if isinstance(sheet.cell(row, 1).value, str)
        and sheet.cell(row, 1).value.strip() == label
    ]
    assert len(rows) == 1, label
    return rows[0]


def _usd(cell_value) -> Decimal:
    """A workbook cell in billions of dollars, as dollars."""
    return (Decimal(repr(cell_value)) * Decimal(10) ** 9).quantize(Decimal("1e8"))


def test_the_reposted_workbook_is_registered_raw_only():
    manifest = yaml.safe_load((RAW_ONLY / "manifest.yaml").read_text())
    entry = manifest["files"]["workbook"]

    assert manifest["package_id"] == PACKAGE
    assert manifest["registration_kind"] == "raw_only"
    assert list(manifest["files"]) == ["workbook"]
    assert hashlib.sha256(WORKBOOK.read_bytes()).hexdigest() == WORKBOOK_SHA256
    assert entry["filename"] == WORKBOOK.name
    assert entry["sha256"] == WORKBOOK_SHA256
    assert entry["size_bytes"] == WORKBOOK_SIZE == WORKBOOK.stat().st_size
    assert entry["storage"]["r2"]["key"] == (
        f"raw/cbo/{PACKAGE}/workbook/{WORKBOOK_SHA256}/{WORKBOOK.name}"
    )
    assert entry["storage"]["r2"]["uri"] == (
        f"r2://ledger-raw/{entry['storage']['r2']['key']}"
    )


def test_the_workbook_is_the_repost_of_the_february_2026_baseline():
    book = openpyxl.load_workbook(WORKBOOK, data_only=True)
    contents = [cell.value for cell in book["Contents"]["A"] if cell.value]
    sheet = book[SHEET]

    assert any("reposted on February 26, 2026" in str(line) for line in contents)
    assert any("Tables 7a and 7b" in str(line) for line in contents)
    assert sheet["A5"].value == (
        "3. Detailed Individual Income Tax Projections in CBO's February 2026 Baseline"
    )
    assert sheet["A6"].value == "Billions of dollars"
    assert sheet["B8"].value.strip() == "Actual"
    assert sheet["D8"].value == "Projected"
    assert sorted(_year_columns(sheet)) == list(range(2022, 2037))


def test_every_csv_value_equals_its_workbook_cell(sheet):
    with CSV_PATH.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    columns = _year_columns(sheet)

    assert [row["source_concept_id"] for row in rows] == list(WORKBOOK_ROWS)
    compared = 0
    for row in rows:
        workbook_row = _row(sheet, WORKBOOK_ROWS[row["source_concept_id"]])
        for year in YEARS:
            cell = sheet.cell(workbook_row, columns[year]).value
            assert Decimal(row[f"year_{year}"]) == _usd(cell), (
                row["source_concept_id"],
                year,
            )
            compared += 1
    assert compared == 84


def test_adjusted_gross_income_row_is_total_income_less_adjustments(sheet):
    """Check on the row's meaning: the workbook's "Adjusted gross income" is
    its "Total income" less its "Subtract statutory adjustments", so the
    package's AGI row is the row CBO calls AGI. CBO prints one decimal, so the
    printed rows agree to within 0.2 (2036: 26,787.8 against 26,787.6)."""
    columns = _year_columns(sheet)
    agi = _row(sheet, "Adjusted gross income")
    total = _row(sheet, "Total income")
    adjustments = _row(sheet, "Subtract statutory adjustments")
    for year in YEARS:
        column = columns[year]
        assert sheet.cell(agi, column).value == pytest.approx(
            sheet.cell(total, column).value - sheet.cell(adjustments, column).value,
            abs=0.25,
        )


@pytest.mark.parametrize("year", [2023, 2024, 2025, 2026])
def test_facts_equal_the_workbook_cells(sheet, year):
    package = load_source_package(PACKAGE)
    facts = package.build_facts(year)
    columns = _year_columns(sheet)

    assert validate_facts(facts).valid
    assert len(facts) == 6
    for fact in facts:
        row_id = fact.source_record_id.rsplit(".", 2)[1]
        cell = sheet.cell(_row(sheet, WORKBOOK_ROWS[row_id]), columns[year]).value

        assert Decimal(repr(fact.value)) == _usd(cell), fact.source_record_id
        assert (fact.period.type, str(fact.period.value)) == ("tax_year", str(year))
