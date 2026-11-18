"""The IRS's early-filing returns are four distinct, source-backed snapshots."""

from hashlib import sha256

import openpyxl
import pytest

from chronicle.consumer_contract import consumer_fact_rows
from chronicle.core import validate_facts
from chronicle.source_package import load_source_package
from chronicle.sources.cells import validate_source_cells


@pytest.mark.parametrize(
    ("year", "week", "cutoff", "digest"),
    [
        (
            2024,
            21,
            "2025-05-22",
            "4a20b0c67e9296c2c401b43deb7bcc4f7fa54925266f43d72e379687e2d57051",
        ),
        (
            2024,
            30,
            "2025-07-24",
            "59bcc4f111cd7ef51bd3a5c36442d0d6c87f5f269399154bb0a0a20e4cc49387",
        ),
        (
            2025,
            21,
            "2026-05-28",
            "c2bb465f6c12eaa5d1eb8cfb9132b8c14b5619655d5e9c5810fb45b5d763312c",
        ),
        (
            2025,
            30,
            "2026-07-30",
            "c36eda3e737c0b9b77e0c46f53e134158b4e1584fdb7d9968d8a82bf0416035c",
        ),
    ],
)
def test_published_cells_and_partial_return_universe(year, week, cutoff, digest):
    package = load_source_package(f"soi-filing-season-week{week}-{year}")
    filename = f"{year - 1999}inweek{week}.xlsx"
    root = package.package_path.parents[2]
    path = root / "db" / package.artifact.resource_directory / filename
    assert sha256(path.read_bytes()).hexdigest() == digest
    workbook = openpyxl.load_workbook(path, data_only=True)
    sheet = workbook["Filing Season"]

    cells = package.build_source_cells(year)
    assert validate_source_cells(cells).valid
    facts = package.build_facts(year, cells=cells)
    assert validate_facts(facts).valid
    rows = consumer_fact_rows(facts)
    assert len({r["aggregate_fact_key"] for r in rows}) == len(rows) == 116 * 17

    # The entire rectangle is published in the same order in all four files.
    # Read the money/count captions independently of Chronicle's selectors.
    for record_index, row in enumerate(rows):
        sheet_row, column_offset = divmod(record_index, 17)
        sheet_row += 11
        column = column_offset + 2
        heading = sheet.cell(sheet_row, 1).value.strip()
        is_dollars = (
            heading == "Adjusted gross income"
            or heading == "Amount"
            or heading.endswith(": Amount")
        )
        scale = 1000 if is_dollars else 1
        assert row["value"] == sheet.cell(sheet_row, column).value * scale
        assert row["observed_measure"]["unit"] == ("usd" if is_dollars else "count")
        assert row["source"]["url"] == f"https://www.irs.gov/pub/irs-soi/{filename}"
        assert digest in row["source"]["raw_r2_uri"]
        assert row["period"] == {"type": "tax_year", "value": year}
        assert row["dimensions"]["filing_season_week"] == week
        assert row["dimensions"]["processing_cutoff"] == cutoff
        assert "initially processed" in row["period_coverage"]["notes"]
        assert row["period_coverage"]["basis"] == "tax"
        assert bool(row["lineage"]["source_cell_keys"])
        assert (row["dimensions"]["income_range"] == "all") == (column == 2)
        assert (row["layout"]["table_record_kind"] == "total") == (column == 2)

    # Pin the comparison's central series; SALT is an amount-only row.
    national = {
        r["observed_measure"]["source_measure_id"]: r
        for r in rows
        if r["dimensions"]["income_range"] == "all"
    }
    for measure, number in {
        "return_count": 11,
        "standard_deduction_returns": 54,
        "standard_deduction_amount": 55,
        "total_itemized_deductions_returns": 60,
        "total_itemized_deductions_amount": 61,
        "limited_state_local_taxes_amount": 64,
        "charitable_amount": 70,
    }.items():
        expected = sheet.cell(number, 2).value
        if measure.endswith("_amount"):
            expected *= 1000
        assert national[measure]["value"] == expected
    assert "limited_state_local_taxes_returns" not in national
    if (year, week) == (2025, 30):
        assert national["return_count"]["value"] == 147_524_776
        assert national["total_itemized_deductions_returns"]["value"] == 16_223_991
    workbook.close()
