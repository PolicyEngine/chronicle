"""``hhs-acf-tanf-caseload-2024`` reads ACF's later fiscal year 2024 workbook
in place (chronicle#449).

ACF replaced the fiscal year 2024 workbook on its page with the "FY2024 15
Months TANF Caseload" workbook (``fy2024-15months-tanf-caseload.xlsx``, sheets
dated 2025-06-10). It covers October 2023 to December 2024 and revises fiscal
year 2024: the package keeps its id, record set ids, spec ids, labels, rows and
measures, and reads the newer file. The FYCY2024 sheets now hold the fiscal
year block in columns B:E (families) and B:D (recipients) with the states in
column A, one row lower than before because row 4 holds the date, beside a
calendar year 2024 block that the package does not read.

The expected values are read from the workbook directly with openpyxl, not
through Chronicle's parsers.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import openpyxl
import pytest
import yaml

from chronicle.core import validate_facts
from chronicle.source_package import load_source_package
from chronicle.sources.cells import validate_source_cells

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "db" / "data" / "hhs_acf"
PACKAGE = "hhs-acf-tanf-caseload-2024"
XLSX = DATA / "tanf_caseload_2024" / "fy2024-15months-tanf-caseload.xlsx"
SHA256 = "e7f7b4df5f94c1925b865a576fb4ecf62cfe572ccdad854231f0d1559c96b973"
SIZE = 265_521
URL = (
    "https://acf.gov/sites/default/files/documents/ofa/"
    "fy2024-15months-tanf-caseload.xlsx"
)
# The workbook the package read before: in R2 only, registered raw-only.
OLD_SHA256 = "6a9c86ad056ac256d409b48c23731d158d6e94d6dae6b5bd888c42a6021db27c"
OLD_SIZE = 220_896

# Measure -> (FYCY2024 sheet, its header in the fiscal-year block, the monthly
# table whose October-September counts the block averages).
MEASURES = {
    "total_families": ("FYCY2024-Families", "Total\nFamilies", "TotalFam"),
    "two_parent_families": (
        "FYCY2024-Families",
        "Two\nParent\nFamilies",
        "Two-parent",
    ),
    "one_parent_families": (
        "FYCY2024-Families",
        "One \nParent \nFamilies",
        "One-parent",
    ),
    "no_parent_families": (
        "FYCY2024-Families",
        "No \nParent \nFamilies",
        "Zero-parent",
    ),
    "total_recipients": ("FYCY2024-Recipients", "Total \nRecipients", "TotalRecipent"),
    "adult_recipients": ("FYCY2024-Recipients", "Adults", "Adults"),
    "child_recipients": ("FYCY2024-Recipients", "Children", "Children"),
}
TITLES = {
    "FYCY2024-Families": "AVERAGE MONTHLY NUMBER OF FAMILIES: Oct. 2023 - Dec. 2024",
    "FYCY2024-Recipients": (
        "AVERAGE MONTHLY NUMBER OF RECIPIENTS, ADULTS, AND CHILDREN: "
        "Oct. 2023 - Dec. 2024"
    ),
}
FISCAL_YEAR_BLOCK = "Fiscal Year 2024 (October - September)"
CALENDAR_YEAR_BLOCK = "Calendar Year 2024 (January - December)"
FISCAL_YEAR_NOTE = "Fiscal year average is based on data Oct. 2023 through Sep. 2024"
FISCAL_YEAR_MONTHS = ("Oct-23", "Nov-23", "Dec-23") + tuple(
    f"{month}-24"
    for month in ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep")
)

# The 13 facts whose value ACF revised, as the 15-month workbook prints them.
# In comments: the value in the workbook dated 2025-01-30.
PREFIX = "hhs_acf_tanf.fy2024.average_monthly_"
REVISED = {
    PREFIX + "families.us.us_total.total_families": 839_119.1666666666,  # 841,208.67
    PREFIX
    + "families.us.us_total.two_parent_families": 56_504.916666666664,  # 56,430.92
    PREFIX
    + "families.us.us_total.one_parent_families": 436_503.6666666667,  # 438,444.92
    PREFIX
    + "families.us.us_total.no_parent_families": 346_110.5833333333,  # 346,332.83
    PREFIX + "recipients.us.us_total.total_recipients": 2_054_214.75,  # 2,060,968.25
    PREFIX + "recipients.us.us_total.adult_recipients": 557_885.5,  # 560,124.5
    PREFIX + "recipients.us.us_total.child_recipients": 1_496_329.25,  # 1,500,843.75
    PREFIX + "families.state.co.total_families": 12_759.75,  # 12,456.08
    PREFIX + "families.state.md.total_families": 10_308.166666666666,  # 12,918.5
    PREFIX + "families.state.nc.total_families": 7_285.833333333333,  # 7,116.17
    PREFIX + "families.state.ri.total_families": 3_447.5,  # 3,391
    PREFIX + "families.state.tn.total_families": 12_109.416666666666,  # 12,117.25
    PREFIX + "families.state.vt.total_families": 1_653.6666666666667,  # 1,654.83
}


@pytest.fixture(scope="module")
def built():
    package = load_source_package(PACKAGE)
    cells = package.build_source_cells(2024)
    facts = package.build_facts(2024, cells=cells)
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    return cells, facts


@pytest.fixture(scope="module")
def book():
    return openpyxl.load_workbook(XLSX, data_only=True)


def _place(fact) -> str:
    """The workbook's row label for a fact's geography."""
    return "U.S. Totals" if fact.geography.id == "0100000US" else fact.geography.name


def _row(sheet, place: str, first_row: int) -> int:
    rows = [
        row
        for row in range(first_row, sheet.max_row + 1)
        if sheet.cell(row, 1).value == place
    ]
    assert len(rows) == 1, (sheet.title, place)
    return rows[0]


def _block_columns(sheet, heading: str) -> dict[str, int]:
    """A block's columns by their row-6 header, found from the block's row-5
    heading rather than from the package."""
    starts = [cell.column for cell in sheet[5] if cell.value == heading]
    assert len(starts) == 1, (sheet.title, heading)
    columns = {}
    column = starts[0]
    while sheet.cell(6, column).value not in (None, "State"):
        columns[sheet.cell(6, column).value] = column
        column += 1
    return columns


def test_manifest_registers_the_15_month_workbook_in_place():
    manifest = yaml.safe_load((XLSX.parent / "manifest.yaml").read_text())
    entry = manifest["files"][2024]

    assert manifest["package_id"] == PACKAGE
    assert manifest["source_page"] == "https://acf.gov/ofa/data/tanf-caseload-data-2024"
    assert list(manifest["files"]) == [2024]
    assert hashlib.sha256(XLSX.read_bytes()).hexdigest() == SHA256
    assert entry["filename"] == XLSX.name
    assert entry["source_url"] == URL
    assert entry["sha256"] == SHA256
    assert entry["size_bytes"] == SIZE == XLSX.stat().st_size
    assert entry["storage"]["r2"]["key"] == (
        f"raw/hhs_acf_tanf/{PACKAGE}/2024/{SHA256}/{XLSX.name}"
    )
    assert entry["storage"]["r2"]["uri"] == (
        f"r2://ledger-raw/{entry['storage']['r2']['key']}"
    )
    assert "downloaded it in a browser on 2026-11-27" in manifest["notes"]
    assert "AWS WAF challenge" in manifest["notes"]
    assert OLD_SHA256 in manifest["notes"]
    # No second file stays beside the one the package reads.
    assert sorted(path.name for path in XLSX.parent.iterdir()) == [
        XLSX.name,
        "manifest.yaml",
    ]


def test_the_earlier_workbook_is_registered_raw_only():
    manifest = yaml.safe_load(
        (DATA / "tanf_caseload_2024_raw_only" / "manifest.yaml").read_text()
    )
    entry = manifest["files"][2024]

    assert manifest["registration_kind"] == "raw_only"
    assert manifest["package_id"] == PACKAGE
    assert entry["filename"] == "tanf_caseload_2024.xlsx"
    assert entry["sha256"] == OLD_SHA256
    assert entry["size_bytes"] == OLD_SIZE
    assert entry["storage"]["local"] is False
    assert entry["storage"]["r2"]["key"] == (
        f"raw/hhs_acf_tanf/{PACKAGE}/2024/{OLD_SHA256}/tanf_caseload_2024.xlsx"
    )
    assert not (DATA / "tanf_caseload_2024_raw_only" / entry["filename"]).exists()


def test_fact_count_period_ids_and_source(built):
    cells, facts = built

    assert len(facts) == 58
    assert {(fact.period.type, fact.period.value) for fact in facts} == {
        ("fiscal_year", 2024)
    }
    assert {fact.source.source_file for fact in facts} == {XLSX.name}
    assert {fact.source.source_sha256 for fact in facts} == {SHA256}
    assert {fact.source.url for fact in facts} == {URL}
    assert {fact.source.vintage for fact in facts} == {"fiscal_year_2024"}
    # The ids the package had before the change: 4 + 3 national, 51 state.
    record_sets = {fact.source_record_id.rsplit(".", 2)[0] for fact in facts}
    assert record_sets == {
        PREFIX + "families.us",
        PREFIX + "families.state",
        PREFIX + "recipients.us",
    }
    states = [fact for fact in facts if fact.geography.level == "state"]
    assert len(states) == len({fact.geography.id for fact in states}) == 51


def test_facts_are_their_fiscal_year_cells(built, book):
    """Each fact is the cell of its state's row (found by name) under its
    header in the "Fiscal Year 2024 (October - September)" block."""
    _, facts = built
    for sheet_name, title in TITLES.items():
        sheet = book[sheet_name]
        notes = [sheet.cell(row, 1).value for row in range(62, sheet.max_row + 1)]
        assert sheet["A3"].value == title
        assert sheet["A4"].value.strftime("%Y-%m-%d") == "2025-06-10"
        assert sheet["A6"].value == "State"
        assert FISCAL_YEAR_NOTE in notes

    for fact in facts:
        measure_id = fact.source_record_id.rsplit(".", 1)[1]
        sheet_name, header, _ = MEASURES[measure_id]
        sheet = book[sheet_name]
        row = _row(sheet, _place(fact), first_row=7)
        column = _block_columns(sheet, FISCAL_YEAR_BLOCK)[header]

        assert fact.value == sheet.cell(row, column).value, fact.source_record_id


def test_fiscal_year_cells_average_october_to_september(built, book):
    """Check on the cells' meaning, not a fact: each fiscal-year cell is the
    mean of its row's twelve monthly counts, October 2023 to September 2024,
    in the workbook's monthly table. The monthly tables run on to December
    2024, which only the calendar-year block uses."""
    _, facts = built
    for fact in facts:
        measure_id = fact.source_record_id.rsplit(".", 1)[1]
        table = book[MEASURES[measure_id][2]]
        months = {
            cell.value: cell.column
            for cell in table[4]
            if isinstance(cell.value, str) and cell.value[-3:] in ("-23", "-24")
        }
        assert len(months) == 15
        assert set(FISCAL_YEAR_MONTHS) <= set(months)
        row = _row(table, _place(fact), first_row=5)
        counts = [table.cell(row, months[month]).value for month in FISCAL_YEAR_MONTHS]

        assert fact.value == pytest.approx(sum(counts) / 12, rel=1e-12)


def test_no_fact_reads_the_calendar_year_block(built, book):
    """The calendar-year block repeats the headers. Where the two blocks
    differ, the fact equals the fiscal-year cell, not the calendar-year one."""
    _, facts = built
    differing = 0
    for fact in facts:
        measure_id = fact.source_record_id.rsplit(".", 1)[1]
        sheet_name, header, _ = MEASURES[measure_id]
        sheet = book[sheet_name]
        row = _row(sheet, _place(fact), first_row=7)
        calendar = sheet.cell(row, _block_columns(sheet, CALENDAR_YEAR_BLOCK)[header])
        if calendar.value != fact.value:
            differing += 1

    assert differing >= 50


def test_revised_values(built):
    _, facts = built
    by_id = {fact.source_record_id: fact for fact in facts}

    for source_record_id, value in REVISED.items():
        assert by_id[source_record_id].value == pytest.approx(value, rel=1e-12)
    # A state that ACF did not revise keeps its value.
    assert by_id[PREFIX + "families.state.ca.total_families"].value == 290_247.75
