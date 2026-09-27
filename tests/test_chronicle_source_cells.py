"""Tests for Chronicle source-cell preservation."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import openpyxl
import pytest

from chronicle.epoch import HASH_DOMAINS
from chronicle.harness import (
    build_fixture_source_cell_file,
    validate_fixture_source_cells,
)
from chronicle.jurisdictions.us.soi import (
    build_soi_table_1_1_source_cells,
    build_soi_table_1_1_source_record_specs,
)
from chronicle.sources.cells import (
    SourceArtifactMetadata,
    load_source_cells_jsonl,
    source_cells_from_delimited_text,
    source_cells_from_html_tables_and_text,
    source_cells_from_ods,
    source_cells_from_xlsx,
    validate_source_cells,
)
from chronicle.sources.rows import (
    SourceRow,
    source_cells_from_source_rows,
    source_rows_from_delimited_text,
)
from chronicle.sources.specs import (
    CellSelectorSpec,
    resolve_cell_selector,
    resolve_source_record,
)


def test_ods_numeric_text_mode_coerces_formatted_numbers_only():
    artifact = SourceArtifactMetadata(
        source_name="hmrc",
        source_table="test",
        source_file="test.ods",
        url="https://example.test/test.ods",
        vintage="test",
        sha256="abc123",
        size_bytes=10,
        extracted_at="2026-09-03",
        extraction_method="test",
    )
    content = BytesIO()
    with ZipFile(content, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "content.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body>
    <office:spreadsheet>
      <table:table table:name="Table_1">
        <table:table-row>
          <table:table-cell office:value-type="string"><text:p>119,258</text:p></table:table-cell>
          <table:table-cell office:value-type="string"><text:p>-12.5</text:p></table:table-cell>
          <table:table-cell office:value-type="string"><text:p>[Fewer than 1]</text:p></table:table-cell>
        </table:table-row>
      </table:table>
    </office:spreadsheet>
  </office:body>
</office:document-content>
""",
        )

    uncoerced = source_cells_from_ods(content.getvalue(), artifact)
    cells = source_cells_from_ods(
        content.getvalue(),
        artifact,
        coerce_numeric_text=True,
    )

    assert [cell.raw_value for cell in uncoerced] == [
        "119,258",
        "-12.5",
        "[Fewer than 1]",
    ]
    assert [cell.raw_value for cell in cells] == [119_258, -12.5, "[Fewer than 1]"]
    assert [cell.cell_type for cell in cells] == ["number", "number", "text"]


def test_build_soi_table_1_1_source_cells_preserves_workbook_used_range():
    cells = build_soi_table_1_1_source_cells(2023)
    report = validate_source_cells(cells)
    cells_by_address = {cell.address: cell for cell in cells}

    assert report.valid
    assert report.cell_count == 92 * 21
    assert report.counts["by_sheet"] == {"TBL11": 1932}
    assert report.counts["by_source"] == {"irs_soi": 1932}
    assert cells_by_address["A10"].raw_value == "All returns"
    assert cells_by_address["B10"].raw_value == 160_602_107
    assert cells_by_address["B10"].artifact.source_file == "23in11si.xls"


def test_build_source_cell_file_writes_jsonl(tmp_path):
    output = tmp_path / "soi-cells.jsonl"

    report = build_fixture_source_cell_file("soi-table-1-1", output, year=2023)
    cells = load_source_cells_jsonl(output)

    assert report.valid
    assert len(cells) == 1932
    assert cells[0].artifact.sha256


def test_fixture_source_cells_validate():
    report = validate_fixture_source_cells()

    assert report.valid
    assert report.cell_count == 1932
    assert report.counts["by_sheet"] == {"TBL11": 1932}


def test_source_cell_validation_accepts_both_row_epochs_and_rejects_unknown():
    cell = build_soi_table_1_1_source_cells(2023)[0]
    pair = HASH_DOMAINS["source_row"]

    for prefix in pair.accepted:
        accepted = replace(cell, source_row_key=f"{prefix}:same-payload")
        assert validate_source_cells([accepted]).valid

    report = validate_source_cells(
        [replace(cell, source_row_key="future.source_row.v9:same-payload")]
    )

    assert not report.valid
    error = report.errors[0]
    assert error.code == "malformed_source_row_key"
    assert pair.ledger in error.message
    assert pair.chronicle in error.message


def test_source_record_selector_guard_fails_on_changed_row_header():
    cells = build_soi_table_1_1_source_cells(2023)
    spec = build_soi_table_1_1_source_record_specs(2023)[0]
    bad_spec = replace(
        spec,
        selector=replace(spec.selector, expected_row_header="Not all returns"),
    )

    with pytest.raises(ValueError, match="expected row header"):
        resolve_source_record(cells, bad_spec)


def test_column_header_guard_matches_a_delimited_year_header_text():
    # Package YAML renders a digit-only string such as '2024' to the integer
    # 2024, while a delimited file's header row keeps the text '2024'. A guard
    # expecting 2024 matches that text, and nothing looser.
    artifact = SourceArtifactMetadata(
        source_name="bea",
        source_table="test",
        source_file="test.csv",
        url="https://example.test/test.csv",
        vintage="test",
        sha256="abc123",
        size_bytes=10,
        extracted_at="2026-09-25",
        extraction_method="test",
    )
    rows = source_rows_from_delimited_text(
        b"Item,2023,2024,02024,2024.0\nReturns,1,2,3,4\n",
        artifact,
        sheet_name="test",
    )
    cells = source_cells_from_source_rows(rows, selected_rows=())

    def selector(column: str, header):
        return CellSelectorSpec(
            selector_id=f"test.{column}",
            sheet_name="test",
            address=f"{column}2",
            expected_cell_type="number",
            expected_column_header_address=f"{column}1",
            expected_column_header=header,
        )

    assert resolve_cell_selector(cells, selector("C", 2024)).raw_value == 2
    assert resolve_cell_selector(cells, selector("C", "2024")).raw_value == 2
    for column, header in (("B", 2024), ("D", 2024), ("E", 2024), ("C", True)):
        with pytest.raises(ValueError, match="expected column header"):
            resolve_cell_selector(cells, selector(column, header))


def test_delimited_source_row_selection_requires_exact_match():
    artifact = SourceArtifactMetadata(
        source_name="bea",
        source_table="test",
        source_file="test.csv",
        url="https://example.test/test.csv",
        vintage="test",
        sha256="abc123",
        size_bytes=10,
        extracted_at="2026-05-06",
        extraction_method="test",
    )
    rows = [
        SourceRow(
            artifact=artifact,
            sheet_name="NipaDataA",
            row_number=2,
            values={"Period": 2021, "SeriesCode": "W351RC", "Value": 1},
        ),
        SourceRow(
            artifact=artifact,
            sheet_name="NipaDataA",
            row_number=3,
            values={"Period": 2022, "SeriesCode": "W351RC", "Value": 2},
        ),
    ]

    with pytest.raises(ValueError, match="matched 2 rows"):
        source_cells_from_source_rows(
            rows,
            selected_rows=({"SeriesCode": "W351RC"},),
        )

    with pytest.raises(ValueError, match="matched 0 rows"):
        source_cells_from_source_rows(
            rows,
            selected_rows=({"SeriesCode": "Y351RC", "Period": "2022"},),
        )


def test_delimited_text_selected_rows_preserves_requested_order_with_shared_keys():
    artifact = SourceArtifactMetadata(
        source_name="census_pep",
        source_table="test",
        source_file="test.csv",
        url="https://example.test/test.csv",
        vintage="test",
        sha256="abc123",
        size_bytes=10,
        extracted_at="2026-05-27",
        extraction_method="test",
    )
    content = b"STATE,RACE,AGE,VALUE\n06,1,0,10\n06,1,1,11\n06,2,0,20\n"

    cells = source_cells_from_delimited_text(
        content,
        artifact,
        sheet_name="test",
        selected_rows=(
            {"STATE": "06", "RACE": "2", "AGE": "0"},
            {"STATE": "06", "RACE": "1", "AGE": "0"},
        ),
    )
    values = {
        (cell.row_number, cell.column_number): cell.raw_value
        for cell in cells
        if cell.row_number > 1
    }

    assert values[(2, 4)] == 20
    assert values[(3, 4)] == 10


def test_delimited_text_parsers_preserve_underscore_identifiers():
    artifact = SourceArtifactMetadata(
        source_name="ons",
        source_table="test",
        source_file="test.csv",
        url="https://example.test/test.csv",
        vintage="test",
        sha256="abc123",
        size_bytes=10,
        extracted_at="2026-06-27",
        extraction_method="test",
    )
    content = b"band,value\n0_4,123\n10_19,456\n"

    rows = source_rows_from_delimited_text(
        content,
        artifact,
        sheet_name="test",
    )
    cells = source_cells_from_delimited_text(
        content,
        artifact,
        sheet_name="test",
    )

    assert [row.values["band"] for row in rows] == ["0_4", "10_19"]
    assert [
        cell.raw_value
        for cell in cells
        if cell.column_number == 1 and cell.row_number > 1
    ] == ["0_4", "10_19"]


def test_delimited_text_parsers_accept_cp1252_publisher_text():
    artifact = SourceArtifactMetadata(
        source_name="census_pep",
        source_table="test",
        source_file="test.csv",
        url="https://example.test/test.csv",
        vintage="test",
        sha256="abc123",
        size_bytes=10,
        extracted_at="2026-07-22",
        extraction_method="test",
    )
    content = "county,value\nDoña Ana County,123\n".encode("cp1252")

    rows = source_rows_from_delimited_text(content, artifact, sheet_name="test")
    cells = source_cells_from_delimited_text(content, artifact, sheet_name="test")

    assert rows[0].values["county"] == "Doña Ana County"
    assert next(cell for cell in cells if cell.address == "A2").raw_value == (
        "Doña Ana County"
    )


def test_html_tables_and_text_parser_preserves_tables_and_document_numbers():
    artifact = SourceArtifactMetadata(
        source_name="dwp",
        source_table="test html",
        source_file="test.html",
        url="https://example.test/test.html",
        vintage="test",
        sha256="abc123",
        size_bytes=10,
        extracted_at="2026-05-10",
        extraction_method="test",
    )
    html = b"""
    <html>
      <body>
        <p>There were 620,000 ESA cases and 180,000 income-related cases.</p>
        <table>
          <thead>
            <tr><th>Benefit</th><th>Cases</th></tr>
          </thead>
          <tbody>
            <tr><td>Employment and Support Allowance</td><td>999,000</td></tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    cells = source_cells_from_html_tables_and_text(html, artifact)
    cells_by_sheet_address = {(cell.sheet_name, cell.address): cell for cell in cells}

    assert validate_source_cells(cells).valid
    assert cells_by_sheet_address[("table_1", "A1")].raw_value == "Benefit"
    assert cells_by_sheet_address[("table_1", "B2")].raw_value == 999_000
    assert cells_by_sheet_address[("table_1", "B2")].display_value == "999,000"
    assert cells_by_sheet_address[("document_numbers", "D2")].raw_value == "620,000"
    assert cells_by_sheet_address[("document_numbers", "E2")].raw_value == 620_000
    assert cells_by_sheet_address[("document_numbers", "D3")].raw_value == "180,000"
    assert cells_by_sheet_address[("document_numbers", "E3")].raw_value == 180_000


def _two_sheet_workbook() -> bytes:
    workbook = openpyxl.Workbook()
    wanted = workbook.active
    wanted.title = "UKPC"
    wanted["A1"] = "code"
    wanted["B1"] = 42
    unwanted = workbook.create_sheet("Cover_sheet")
    unwanted["A1"] = "not selected by any record set"
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_source_cells_from_xlsx_restricts_the_parse_to_declared_sheets():
    artifact = SourceArtifactMetadata(
        source_name="nrs",
        source_table="test",
        source_file="test.xlsx",
        url="https://example.test/test.xlsx",
        vintage="test",
        sha256="abc123",
        size_bytes=10,
        extracted_at="2026-08-12",
        extraction_method="test",
    )
    content = _two_sheet_workbook()

    every_sheet = source_cells_from_xlsx(content, artifact)
    only_ukpc = source_cells_from_xlsx(content, artifact, sheets=("UKPC",))

    assert {cell.sheet_name for cell in every_sheet} == {"UKPC", "Cover_sheet"}
    assert {cell.sheet_name for cell in only_ukpc} == {"UKPC"}
    assert {(cell.address, cell.raw_value) for cell in only_ukpc} == {
        ("A1", "code"),
        ("B1", 42),
    }


def test_source_cells_from_xlsx_rejects_a_sheet_the_workbook_does_not_carry():
    artifact = SourceArtifactMetadata(
        source_name="nrs",
        source_table="test",
        source_file="test.xlsx",
        url="https://example.test/test.xlsx",
        vintage="test",
        sha256="abc123",
        size_bytes=10,
        extracted_at="2026-08-12",
        extraction_method="test",
    )

    with pytest.raises(ValueError, match="does not carry"):
        source_cells_from_xlsx(
            _two_sheet_workbook(),
            artifact,
            sheets=("UKPC", "Renamed_by_publisher"),
        )


def _test_artifact() -> SourceArtifactMetadata:
    return SourceArtifactMetadata(
        source_name="irs_soi",
        source_table="test",
        source_file="test.xlsx",
        url="https://example.test/test.xlsx",
        vintage="test",
        sha256="abc123",
        size_bytes=10,
        extracted_at="2026-09-27",
        extraction_method="test",
    )


def _workbook_bytes(data_extent: tuple[int, int], merged: list[str]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in range(1, data_extent[0] + 1):
        for column in range(1, data_extent[1] + 1):
            sheet.cell(row=row, column=column, value=row * 100 + column)
    for cell_range in merged:
        sheet.merge_cells(cell_range)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_source_cells_from_xlsx_ignores_a_row_merged_to_the_sheet_edge():
    """23in54us.xlsx (TY2023) merges its footnote row A179:XFD179. openpyxl
    fills all 16,384 columns with MergedCell placeholders, so the used range
    grew to ~70 million cells; the parse now stops at the file's own cells."""
    content = _workbook_bytes((4, 5), ["A6:XFD6"])

    cells = source_cells_from_xlsx(content, _test_artifact())

    assert {(cell.row_number, cell.column_number) for cell in cells} == {
        (row, column) for row in range(1, 7) for column in range(1, 6)
    }
    assert {cell.address: cell.raw_value for cell in cells}["C2"] == 203


def test_xlsx_used_range_bounds_equal_openpyxl_without_an_edge_merge():
    """Invariant: a sheet with no merged range reaching column XFD or the last
    row keeps openpyxl's (max_row, max_column), whether its merged ranges sit
    inside the data or run past it; with one, only its placeholders stop
    counting."""
    from chronicle.sources.cells import _xlsx_used_range_bounds

    layouts = [
        ((rows, columns), merged)
        for rows in (1, 3)
        for columns in (1, 4)
        for merged in (
            [],
            ["A1:B1"],
            [f"A{rows + 2}:F{rows + 2}"],
            [f"B{rows + 1}:B{rows + 4}"],
            ["C2:H9"],
        )
    ]
    for extent, merged in layouts:
        sheet = openpyxl.load_workbook(BytesIO(_workbook_bytes(extent, merged))).active
        assert _xlsx_used_range_bounds(sheet) == (sheet.max_row, sheet.max_column), (
            extent,
            merged,
        )

        edge = openpyxl.load_workbook(
            BytesIO(_workbook_bytes(extent, [*merged, "A20:XFD20"]))
        ).active
        assert edge.max_column == 16_384
        assert _xlsx_used_range_bounds(edge) == (
            max(sheet.max_row, 20),
            sheet.max_column,
        ), (extent, merged)


def test_xlsx_used_range_bounds_ignore_a_column_merged_to_the_last_row():
    """The row edge works like the column edge. A stub stands in for the
    sheet: openpyxl would materialise over a million MergedCells for a real
    A1:A1048576 merge."""
    from types import SimpleNamespace

    from openpyxl.cell.cell import MergedCell
    from openpyxl.worksheet.cell_range import CellRange

    from chronicle.sources.cells import _xlsx_used_range_bounds

    real = openpyxl.Workbook().active
    cells = {
        (row, column): real.cell(row=row, column=column)
        for row in (1, 2, 3)
        for column in (1, 2)
    }
    cells.update(
        {(row, 4): MergedCell(real, row=row, column=4) for row in range(5, 60)}
    )
    cells[(4, 4)] = real.cell(row=4, column=4)  # the merge's anchor
    sheet = SimpleNamespace(
        merged_cells=SimpleNamespace(ranges=[CellRange("D4:D1048576")]),
        _cells=cells,
        max_row=1_048_576,
        max_column=4,
    )

    assert _xlsx_used_range_bounds(sheet) == (4, 4)
