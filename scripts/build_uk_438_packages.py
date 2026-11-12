"""Generate the source packages for PolicyEngine/chronicle#438, the dwellings inputs.

Run from the repository root:

    uv run python scripts/build_uk_438_packages.py

``--check`` compares the generated YAML with the committed files instead of writing.
Each package is written from its pinned artifact, read with Chronicle's own parsers, so
every row number, column and guard cell below is one the package parser sees.

- ``ons-national-balance-sheet-dwellings-2025`` and
  ``ons-national-balance-sheet-dwellings-preliminary-2026``: dwellings (AN.111) for the
  twelve institutional sectors, read from the two balance sheet workbooks that the land
  packages pin (item 1). No new file.
- ``ons-capital-stocks-dwellings-2025`` and
  ``ons-capital-stocks-dwellings-preliminary-2026``: the gross and net capital stock of
  dwellings at current prices, from ONS's capital stocks releases of 27 November 2025 and
  10 June 2026 (item 2).
- ``ons-census2021-ts054-tenure-msoa``: Census 2021 TS054 households by tenure for the
  7,264 MSOAs of England and Wales, in the categories and spec ids of
  ``ons-census2021-ts054-tenure-lad`` (item 3).

The helpers come from scripts/build_uk_408_packages.py, which writes the land packages.
"""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_uk_408_packages import (  # noqa: E402
    PACKAGES,
    grid_of,
    manifest_file,
    metadata,
    nbs_year_rows,
    render,
    write,
    xlsx_grid,
)

from chronicle.sources.cells import source_cells_from_xlsx  # noqa: E402
from chronicle.sources.rows import (  # noqa: E402
    source_cells_from_source_rows,
    source_rows_from_delimited_text,
)

EXTRACTED_AT = "2026-11-12"
ISSUE = "PolicyEngine/chronicle#438"
# The label the preliminary land package declares, and Chronicle's register lists.
PRELIMINARY_LABELS = {"publication_status": {"preliminary": "Preliminary"}}


# --------------------------------------------- 1. Dwellings by institutional sector


@dataclass(frozen=True)
class BalanceSheet:
    package_id: str
    directory: str
    data_directory: str
    url: str
    source_table: str
    vintage: str
    artifact_year: int
    years: range
    prefix: str
    preliminary: bool


NBS_EDITIONS = (
    BalanceSheet(
        package_id="ons-national-balance-sheet-dwellings-2025",
        directory="ons/national_balance_sheet_dwellings_2025",
        data_directory="ons/national_balance_sheet_land_2025",
        url=(
            "https://www.ons.gov.uk/economy/nationalaccounts/uksectoraccounts/datasets/"
            "thenationalbalancesheetestimates"
        ),
        source_table=(
            "The UK national balance sheet estimates, 2025 edition (reference tables), "
            "Tables 2 to 13"
        ),
        vintage="nbs_2025",
        artifact_year=2024,
        years=range(1995, 2025),
        prefix="ons.nbs2025",
        preliminary=False,
    ),
    BalanceSheet(
        package_id="ons-national-balance-sheet-dwellings-preliminary-2026",
        directory="ons/national_balance_sheet_dwellings_preliminary_2026",
        data_directory="ons/national_balance_sheet_land_preliminary_2026",
        url=(
            "https://www.ons.gov.uk/economy/nationalaccounts/uksectoraccounts/datasets/"
            "preliminaryuknationalbalancesheetestimates"
        ),
        source_table=(
            "Preliminary UK national balance sheet estimates, 10 June 2026, Tables 2 to 13"
        ),
        vintage="preliminary_nbs_2026_06_10",
        artifact_year=2026,
        years=range(2025, 2026),
        prefix="ons.preliminary_nbs2026",
        preliminary=True,
    ),
)
# (dwellings CDID, sheet, entity role, concept suffix, label, the sheet's title as printed)
NBS_SECTORS = (
    (
        "E46Y",
        "Table 2",
        "total_economy",
        "total",
        "United Kingdom total",
        "National balance sheet: by asset, current prices1 (£million at end year)",
    ),
    (
        "E46D",
        "Table 3",
        "non_financial_corporations",
        "nfc",
        "Non-financial corporations",
        "Non-financial corporations, current prices (£million at end year) ",
    ),
    (
        "E46E",
        "Table 4",
        "public_non_financial_corporations",
        "public_nfc",
        "Public non-financial corporations",
        "Public non-financial corporations, current prices (£million at end year)",
    ),
    (
        "E46F",
        "Table 5",
        "private_non_financial_corporations",
        "private_nfc",
        "Private non-financial corporations",
        "Private non-financial corporations, current prices (£million at end year)",
    ),
    (
        "E46G",
        "Table 6",
        "financial_corporations",
        "financial_corporations",
        "Financial corporations",
        "Financial corporations, current prices (£million at end year)",
    ),
    (
        "E46I",
        "Table 7",
        "general_government",
        "general_government",
        "General government",
        "General government, current prices (£million at end year)1",
    ),
    (
        "E46K",
        "Table 8",
        "central_government",
        "central_government",
        "Central government",
        "Central government, current prices (£million at end year)1",
    ),
    (
        "E46L",
        "Table 9",
        "local_government",
        "local_government",
        "Local government",
        "Local government, current prices (£million at end year)1",
    ),
    (
        "E46M",
        "Table 10",
        "households_and_npish",
        "households_and_npish",
        "Households and NPISH",
        "Households and non-profit institutions serving households (NPISH), current "
        "prices (£million at end year)",
    ),
    (
        "E46V",
        "Table 11",
        "households",
        "households",
        "Households sector",
        "Households, current prices (£million at end year)",
    ),
    (
        "E46W",
        "Table 12",
        "non_profit_institutions_serving_households",
        "npish",
        "Non-profit institutions serving households",
        "Non-profit institutions serving households (NPISH), current prices (£million "
        "at end year)",
    ),
    (
        "E46X",
        "Table 13",
        "public_sector",
        "public_sector",
        "Public sector",
        "Public sector, current prices (£million at end year)1,2",
    ),
)
NBS_SHEETS = tuple(sheet for _, sheet, *_ in NBS_SECTORS)
NBS_LAND_NOTE = "Excludes the value of the land underneath the assets."
NBS_PUBLIC_SECTOR_NOTE = (
    "Public sector is general government plus public non-financial corporations."
)
NBS_CAPITAL_STOCKS_NOTE = (
    "is unavailable for the central and local government sectors (S.1311 + S.1313) "
    "from the capital stocks dataset."
)
NBS_HEADER = """
ONS, {title}: dwellings (AN.111) at current prices, GBP million (value_scale 1e6), at
{span}, for the twelve institutional sectors the reference tables print, each from its
own table: the whole economy (Table 2, E46Y); non-financial corporations (Table 3, E46D),
public (Table 4, E46E) and private (Table 5, E46F); financial corporations (Table 6,
E46G); general government (Table 7, E46I), central (Table 8, E46K) and local (Table 9,
E46L); households and NPISH (Table 10, E46M), households (Table 11, E46V) and NPISH
(Table 12, E46W); and the public sector (Table 13, E46X).{status}

The workbook is the one {land} pins, and this package reads each table's Dwellings
column (B) for the years that package reads Land. Every table's notes say that its
produced assets exclude the value of the land underneath them, and Table 2's note 1
traces the asset breakdown to ONS's capital stocks dataset, so the rows are modelled
estimates (model_output), as the land rows are. Financial corporations (E46G) and local
government (E46L) print 0 in every year, and the zeros are kept as printed.

The sectors overlap as ONS's sector tree does (E46D = E46E + E46F, E46I = E46K + E46L,
E46M = E46V + E46W, E46X = E46I + E46E, E46Y = E46D + E46G + E46I + E46M), so no total
is derived. Written by scripts/build_uk_438_packages.py for {issue} item 1.
"""


def nbs_dwellings_column(grid: dict, sheet: str, cdid: str) -> str:
    """The Dwellings column, found by its CDID and checked against its two headers."""
    (column,) = [
        column
        for (name, row, column), value in grid.items()
        if name == sheet and row == 8 and value == cdid
    ]
    assert re.fullmatch(r"Dwellings\d", grid[(sheet, 6, column)]), (sheet, column)
    assert grid[(sheet, 7, column)].strip() == "AN.111", (sheet, column)
    return column


def nbs_notes(grid: dict, sheet: str) -> list[str]:
    """The table's notes, the text cells of column B below its 'Notes' heading."""
    (start,) = [
        row
        for (name, row, column), value in grid.items()
        if name == sheet and column == "A" and value == "Notes"
    ]
    return [
        value.strip()
        for (name, row, column), value in sorted(
            grid.items(), key=lambda item: item[0][1]
        )
        if name == sheet and column == "B" and row > start and isinstance(value, str)
    ]


def nbs_record_set(
    edition: BalanceSheet, sector: tuple, year: int, row: int, column: str, notes: str
) -> dict:
    cdid, sheet, role, suffix, label, _title = sector
    record_set_id = f"{edition.prefix}.dwellings.{role}.cy{year}"
    record = {
        "record_set_id": record_set_id,
        "provenance_class": "model_output",
        "record_set_spec_id": f"{record_set_id}.v1",
        "source_record_id_prefix": record_set_id,
        "sheet_name": sheet,
        "period_type": "calendar_year",
        "period": year,
        "geography_id": "K02000001",
        "geography_level": "country",
        "geography_name": "United Kingdom",
        "geography_vintage": "current",
        "entity": "institutional_sector",
        "entity_role": role,
        "domain": "national_balance_sheet",
        "groupby_dimension": "ons.nbs_asset_category",
        "rows": [
            {
                "value_id": f"cy{year}",
                "label": str(year),
                "ordinal": 0,
                "row_number": row,
                "expected_row_header_column": "A",
                "expected_row_header": year,
                "table_record_kind": "total",
            }
        ],
        "measures": [
            {
                "measure_id": "dwellings_value",
                "label": f"{label} dwellings, end of {year}",
                "ordinal": 0,
                "column": column,
                "source_column_id": "dwellings_value",
                "expected_column_header_row": 8,
                "expected_column_header": cdid,
                "concept": f"ons.nbs_dwellings_value_{suffix}",
                "source_concept": f"ons.{cdid.lower()}",
                "concept_relation": "source_label",
                "concept_authority": "ons",
                "concept_evidence_url": edition.url,
                "concept_evidence_notes": notes,
                "unit": "gbp",
                "aggregation": "sum",
                "value_scale": 1000000,
                "expected_cell_type": "number",
            }
        ],
    }
    if edition.preliminary:
        record["period_coverage"] = {
            "start_date": f"{year}-12-31",
            "end_date": f"{year}-12-31",
            "basis": "calendar",
            "source_period_label": f"End of {year}",
            "notes": "Preliminary current-price balance-sheet stock, not an annual flow.",
        }
        record["shared_filters"] = {"publication_status": "preliminary"}
        record["shared_constraints"] = [
            {
                "variable": "publication_status",
                "operator": "==",
                "value": "preliminary",
                "label": "Publication status",
            }
        ]
    return record


def build_nbs(edition: BalanceSheet) -> str:
    grid = xlsx_grid(edition.data_directory, NBS_SHEETS)
    record_sets = []
    for sector in NBS_SECTORS:
        cdid, sheet, _role, _suffix, _label, title = sector
        assert grid[(sheet, 1, "B")] == title, (sheet, grid[(sheet, 1, "B")])
        column = nbs_dwellings_column(grid, sheet, cdid)
        notes = nbs_notes(grid, sheet)
        assert NBS_LAND_NOTE in notes, sheet
        years = nbs_year_rows(grid, sheet)
        for year in edition.years:
            row = years[year]
            assert isinstance(grid[(sheet, row, column)], int), (sheet, year)
            if edition.preliminary:
                text = (
                    "Preliminary estimates released 10 June 2026; dwellings AN.111, "
                    f"current-price GBP million at end of {year}, {sheet} "
                    f"({title.split(',')[0]}), series {cdid}."
                )
            else:
                text = (
                    f"The UK national balance sheet estimates, 2025 edition, {sheet} "
                    f"({title.split(',')[0]}), Dwellings (AN.111) series {cdid}, GBP "
                    "million at current prices, end-of-year position."
                )
            text += f" The table's notes: '{NBS_LAND_NOTE}'"
            if cdid == "E46Y":
                assert any(note.endswith(NBS_CAPITAL_STOCKS_NOTE) for note in notes)
                text += (
                    " Its note 1 traces the asset breakdown to ONS's capital stocks "
                    "dataset."
                )
            if cdid == "E46X":
                assert NBS_PUBLIC_SECTOR_NOTE in notes
                text += f" Table 13 note 1: '{NBS_PUBLIC_SECTOR_NOTE}'"
            record_sets.append(nbs_record_set(edition, sector, year, row, column, text))
    first, last = edition.years[0], edition.years[-1]
    if edition.preliminary:
        title = (
            "Preliminary UK national balance sheet estimates (released 10 June 2026)"
        )
        span = f"end-{last}"
        status = " Every fact carries publication_status preliminary."
        land = "ons-national-balance-sheet-land-preliminary-2026"
        label = (
            "ONS preliminary national balance sheet: dwellings (AN.111) by institutional "
            f"sector, end-{last}"
        )
    else:
        title = (
            "The UK national balance sheet estimates, 2025 edition (released 18 "
            "December 2025)"
        )
        span = f"the end of each year from {first} to {last}"
        status = ""
        land = "ons-national-balance-sheet-land-2025"
        label = (
            "ONS national balance sheet 2025: dwellings (AN.111) by institutional sector, "
            f"{first}-{last}"
        )
    dimension_labels = {"ons.nbs_asset_category": "Balance sheet year"}
    if edition.preliminary:
        dimension_labels["publication_status"] = "Publication status"
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": edition.package_id,
        "label": label,
        "dimension_labels": dimension_labels,
        "artifact": {
            "source_name": "ons",
            "source_table": edition.source_table,
            "resource_package": "db",
            "resource_directory": f"data/{edition.data_directory}",
            "manifest": "manifest.yaml",
            "vintage": edition.vintage,
            "extracted_at": EXTRACTED_AT,
            "extraction_method": "xlsx used-range cell parse of the sector tables",
            "parser": "xlsx_used_range",
            "artifact_year": edition.artifact_year,
            "sheets": list(NBS_SHEETS),
        },
        "record_sets": record_sets,
    }
    if edition.preliminary:
        payload["dimension_value_labels"] = PRELIMINARY_LABELS
    header = NBS_HEADER.format(
        title=title, span=span, status=status, land=land, issue=ISSUE
    )
    return render(header, payload)


# ------------------------------------------- 2. ONS capital stocks of dwellings


@dataclass(frozen=True)
class CapitalStocks:
    package_id: str
    directory: str
    url: str
    released: str
    source_table: str
    vintage: str
    artifact_year: int
    parser: str
    years: range
    prefix: str
    preliminary: bool
    sheet_titles: dict[str, str]


CS_EDITIONS = (
    CapitalStocks(
        package_id="ons-capital-stocks-dwellings-2025",
        directory="ons/capital_stocks_dwellings_2025",
        url=(
            "https://www.ons.gov.uk/economy/nationalaccounts/uksectoraccounts/datasets/"
            "capitalstocksconsumptionoffixedcapital"
        ),
        released="27 November 2025",
        source_table=(
            "Capital stocks and fixed capital consumption, 27 November 2025, Tables "
            "1.1.1 and 2.1.1"
        ),
        vintage="capital_stocks_2025_11_27",
        artifact_year=2024,
        parser="xlsx_numeric_text_used_range",
        years=range(1995, 2025),
        prefix="ons.capital_stocks2025",
        preliminary=False,
        sheet_titles={
            "1.1.1": "1.1.1 Gross capital stock: by asset and sector, current prices",
            "2.1.1": "2.1.1 Net capital stock: by asset and sector, current prices",
        },
    ),
    CapitalStocks(
        package_id="ons-capital-stocks-dwellings-preliminary-2026",
        directory="ons/capital_stocks_dwellings_preliminary_2026",
        url=(
            "https://www.ons.gov.uk/economy/nationalaccounts/uksectoraccounts/datasets/"
            "preliminarycapitalstocksandfixedcapitalconsumption"
        ),
        released="10 June 2026",
        source_table=(
            "Preliminary capital stocks and fixed capital consumption, 10 June 2026, "
            "Tables 1.1.1 and 2.1.1"
        ),
        vintage="preliminary_capital_stocks_2026_06_10",
        artifact_year=2026,
        parser="xlsx_used_range",
        years=range(2025, 2026),
        prefix="ons.preliminary_capital_stocks2026",
        preliminary=True,
        sheet_titles={
            "1.1.1": "1.1.1 Gross capital stock: by asset, current prices",
            "2.1.1": "2.1.1 Net capital stock: by asset, current prices",
        },
    ),
)
# (row header as printed, entity role, concept suffix, label, gross CDID, net CDID)
CS_ROWS = (
    (
        "Total non-financial corporations1",
        "non_financial_corporations",
        "nfc",
        "Non-financial corporations",
        "MIM8",
        "MKV5",
    ),
    (
        "Financial corporations",
        "financial_corporations",
        "financial_corporations",
        "Financial corporations",
        "J5LD",
        "J5LF",
    ),
    (
        "Central government",
        "central_government",
        "central_government",
        "Central government",
        "MJS8",
        "MJS9",
    ),
    (
        "General government",
        "general_government",
        "general_government",
        "General government",
        "MQ2L",
        "MQ2T",
    ),
    ("Households", "households", "households", "Households", "MJY2", "MJY3"),
    (
        "NPISH2",
        "non_profit_institutions_serving_households",
        "npish",
        "Non-profit institutions serving households",
        "J5LL",
        "J5LN",
    ),
    (
        "Total households & NPISH2",
        "households_and_npish",
        "households_and_npish",
        "Households and NPISH",
        "MK2R",
        "MK2S",
    ),
    (
        "Total dwellings (excluding land)",
        "total_economy",
        "total",
        "United Kingdom total",
        "MJF7",
        "MJF8",
    ),
)
# sheet -> (measure kind, its name in the notes, ONS's definition as the bulletin gives it)
CS_MEASURES = {
    "1.1.1": (
        "gross",
        "gross capital stock",
        "ONS's bulletin of 27 November 2025 defines the gross capital stock as the value "
        "of all fixed assets still in use at a point in time.",
    ),
    "2.1.1": (
        "net",
        "net capital stock",
        "ONS's bulletin of 27 November 2025 defines the net capital stock as the gross "
        "stock less the consumption of fixed capital accrued up to that point.",
    ),
}
CS_NFC_NOTE = (
    "1 An asset breakdown of non financial corporations into public and private sector "
    "corporations is not available in this release."
)
CS_ROUNDING_NOTE = (
    "2. Differences between totals and the sum of constituent parts are due to rounding "
    "or because chained volume measures are not additive before the reference year."
)
CS_HEADER = """
ONS, {title} (released {released}): the gross and net capital stock of dwellings at
current prices, GBP billion (value_scale 1e9), {span}, {coverage}, from Tables 1.1.1
(gross) and 2.1.1 (net). The tables print dwellings excluding land.{sectors}{status}

The workbook states no estimation method, service lives or depreciation profile. Its
notes say only that differences between totals and the sum of their parts are due to
rounding (the tables print whole billions), that chained volume measures are referenced
to 2023, and that 'z' marks data not collected.{nfc} ONS's bulletin of 27 November 2025
defines the gross stock as the value of all fixed assets still in use at a point in
time, and the net stock as the gross stock less the consumption of fixed capital accrued
up to that point. The stocks are modelled estimates (model_output).

Written by scripts/build_uk_438_packages.py for {issue} item 2.
"""


def cs_grid(edition: CapitalStocks) -> dict[tuple[str, int, str], object]:
    """Index the tables' cells as the package's own parser reads them.

    The Contents sheet is read too, for its notes; the package parses only the tables.
    """
    filename, path = manifest_file(edition.directory)
    cells = source_cells_from_xlsx(
        path.read_bytes(),
        metadata(filename),
        sheets=("Contents", *CS_MEASURES),
        coerce_numeric_text=edition.parser == "xlsx_numeric_text_used_range",
    )
    return grid_of(cells)


def cs_rows(grid: dict, sheet: str, edition: CapitalStocks) -> dict[str, int]:
    """Each dwellings row's number, found by its printed header in column A."""
    headers = {
        value: row
        for (name, row, column), value in grid.items()
        if name == sheet and column == "A" and isinstance(value, str)
    }
    total = "Total dwellings (excluding land)"
    if edition.preliminary:
        return {total: headers[total]}
    block = headers["Dwellings (excluding land):"]
    rows = {}
    for header, *_ in CS_ROWS:
        (row,) = [
            row
            for (name, row, column), value in grid.items()
            if name == sheet
            and column == "A"
            and value == header
            and block < row <= block + 9
        ]
        rows[header] = row
    return rows


def cs_year_columns(grid: dict, sheet: str) -> dict[int, str]:
    columns = {
        value: column
        for (name, row, column), value in grid.items()
        if name == sheet and row == 2 and isinstance(value, int)
    }
    assert grid[(sheet, 2, "B")] == "CDID", sheet
    return columns


def cs_record_set(
    edition: CapitalStocks,
    sheet: str,
    spec: tuple,
    row: int,
    year: int,
    column: str,
) -> dict:
    header, role, suffix, label, gross_cdid, net_cdid = spec
    measure_kind, measure_name, definition = CS_MEASURES[sheet]
    cdid = gross_cdid if measure_kind == "gross" else net_cdid
    record_set_id = f"{edition.prefix}.dwellings.{measure_kind}.{role}.cy{year}"
    title = edition.sheet_titles[sheet]
    notes = (
        f"{edition.source_table.split(', Tables')[0]}, Table {title}, GBP billion: "
        f"dwellings (excluding land), {header.rstrip('0123456789')}, series {cdid}. "
        f"{definition}"
    )
    if role == "non_financial_corporations":
        notes += (
            " The table's note 1: the release gives no asset breakdown of non-financial "
            "corporations into public and private corporations."
        )
    record = {
        "record_set_id": record_set_id,
        "provenance_class": "model_output",
        "record_set_spec_id": f"{record_set_id}.v1",
        "source_record_id_prefix": record_set_id,
        "sheet_name": sheet,
        "period_type": "calendar_year",
        "period": year,
        "geography_id": "K02000001",
        "geography_level": "country",
        "geography_name": "United Kingdom",
        "geography_vintage": "current",
        "entity": "institutional_sector",
        "entity_role": role,
        "domain": "capital_stocks",
        "groupby_dimension": "ons.capital_stock_sector",
        "rows": [
            {
                "value_id": role,
                "label": header.rstrip("0123456789"),
                "ordinal": 0,
                "row_number": row,
                "expected_row_header_column": "A",
                "expected_row_header": header,
                "table_record_kind": "total",
                "guard_cells": [
                    {
                        "column": "B",
                        "row": row,
                        "expected_value": cdid,
                        "label": "ONS series ID",
                    }
                ],
            }
        ],
        "measures": [
            {
                "measure_id": f"{measure_kind}_capital_stock",
                "label": f"{label} {measure_name} of dwellings, {year}",
                "ordinal": 0,
                "column": column,
                "source_column_id": f"cy{year}",
                "expected_column_header_row": 2,
                "expected_column_header": year,
                "concept": f"ons.{measure_kind}_capital_stock_dwellings_{suffix}",
                "source_concept": f"ons.{cdid.lower()}",
                "concept_relation": "source_label",
                "concept_authority": "ons",
                "concept_evidence_url": edition.url,
                "concept_evidence_notes": notes,
                "unit": "gbp",
                "aggregation": "sum",
                "value_scale": 1000000000,
                "expected_cell_type": "number",
            }
        ],
    }
    if edition.preliminary:
        record["shared_filters"] = {"publication_status": "preliminary"}
        record["shared_constraints"] = [
            {
                "variable": "publication_status",
                "operator": "==",
                "value": "preliminary",
                "label": "Publication status",
            }
        ]
    return record


def build_capital_stocks(edition: CapitalStocks) -> str:
    grid = cs_grid(edition)
    specs = CS_ROWS if not edition.preliminary else CS_ROWS[-1:]
    record_sets = []
    for sheet, title in edition.sheet_titles.items():
        assert grid[(sheet, 1, "A")] == title, (sheet, grid[(sheet, 1, "A")])
        assert "£ billion" in {
            value
            for (name, row, _), value in grid.items()
            if name == sheet and row == 1
        }, sheet
        rows = cs_rows(grid, sheet, edition)
        columns = cs_year_columns(grid, sheet)
        assert set(edition.years) <= set(columns), sheet
        assert max(columns) == edition.years[-1], sheet
        measure_kind = CS_MEASURES[sheet][0]
        for spec in specs:
            header, *_rest, gross_cdid, net_cdid = spec
            row = rows[header]
            cdid = gross_cdid if measure_kind == "gross" else net_cdid
            assert grid[(sheet, row, "B")] == cdid, (sheet, header)
            for year in edition.years:
                column = columns[year]
                assert isinstance(grid[(sheet, row, column)], int), (sheet, row, year)
                record_sets.append(
                    cs_record_set(edition, sheet, spec, row, year, column)
                )
    notes = {
        value.strip()
        for (name, _row, _column), value in grid.items()
        if isinstance(value, str)
    }
    assert CS_ROUNDING_NOTE in notes
    first, last = edition.years[0], edition.years[-1]
    if edition.preliminary:
        title = "Preliminary capital stocks and fixed capital consumption"
        coverage = "for the whole economy"
        span = f"{last}"
        sectors = (
            " This edition prints dwellings for the whole economy only: its sector "
            "tables (1.3.1, 2.3.1) cover all assets together."
        )
        status = " Every fact carries publication_status preliminary."
        nfc = ""
        label = (
            "ONS preliminary capital stocks: gross and net capital stock of dwellings, "
            f"current prices, {last}"
        )
    else:
        assert CS_NFC_NOTE in notes
        title = "Capital stocks and fixed capital consumption"
        coverage = "for the whole economy and each sector the tables print"
        span = f"{first}-{last}"
        sectors = (
            " The sectors are non-financial corporations (MIM8 gross, MKV5 net),"
            " financial corporations (J5LD, J5LF), central government (MJS8, MJS9),"
            " general government (MQ2L, MQ2T), households (MJY2, MJY3), NPISH (J5LL,"
            " J5LN), households and NPISH (MK2R, MK2S) and the total (MJF7, MJF8). The"
            " tables print no row for local government's dwellings, and general"
            " government equals central government in every year."
        )
        status = ""
        nfc = (
            " Note 1 on the sector rows says the release gives no asset breakdown of "
            "non-financial corporations into public and private corporations."
        )
        label = (
            "ONS capital stocks 2025: gross and net capital stock of dwellings by "
            f"institutional sector, current prices, {first}-{last}"
        )
    dimension_labels = {"ons.capital_stock_sector": "Institutional sector"}
    if edition.preliminary:
        dimension_labels["publication_status"] = "Publication status"
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": edition.package_id,
        "label": label,
        "dimension_labels": dimension_labels,
        "artifact": {
            "source_name": "ons",
            "source_table": edition.source_table,
            "resource_package": "db",
            "resource_directory": f"data/{edition.directory}",
            "manifest": "manifest.yaml",
            "vintage": edition.vintage,
            "extracted_at": EXTRACTED_AT,
            "extraction_method": (
                "xlsx used-range cell parse of Tables 1.1.1 and 2.1.1, figures stored as "
                "text read as numbers"
                if edition.parser == "xlsx_numeric_text_used_range"
                else "xlsx used-range cell parse of Tables 1.1.1 and 2.1.1"
            ),
            "parser": edition.parser,
            "artifact_year": edition.artifact_year,
            "sheets": list(CS_MEASURES),
        },
        "record_sets": record_sets,
    }
    if edition.preliminary:
        payload["dimension_value_labels"] = PRELIMINARY_LABELS
    header = CS_HEADER.format(
        title=title,
        released=edition.released,
        coverage=coverage,
        span=span,
        sectors=sectors,
        status=status,
        nfc=nfc,
        issue=ISSUE,
    )
    return render(header, payload)


# --------------------------------------------- 3. Census 2021 TS054 tenure by MSOA

TS054_LAD_DIRECTORY = "ons/census2021_ts054_tenure_lad"
TS054_DIRECTORY = "ons/census2021_ts054_tenure_msoa"
TS054_MEMBER = "census2021-ts054-msoa.csv"
TS054_PREFIX = "Tenure of household: "
TS054_LAD_PREFIX = "ons.census2021.ts054.lad."
TS054_URL = "https://www.nomisweb.co.uk/datasets/c2021ts054"
TS054_HOUSEHOLDS_NOTE = (
    "Households, not dwellings: ONS's metadata says tenure is not available for "
    "household spaces with no usual residents."
)
TS054_SDC_NOTE = (
    "Census 2021's disclosure control (targeted record swapping and cell key "
    "perturbation) can make counts differ slightly between tables, so an "
    "authority's MSOAs need not sum to its local authority row."
)
TS054_SOCIAL_NOTE = (
    "ONS's quality statement for the variable: people misreport their landlord between "
    "'Council or local authority' and 'Housing association', so the two social rented "
    "categories should be added together."
)
TS054_HEADER = """
Census 2021 table TS054 (tenure of household) for the 7,264 middle layer super output
areas of England and Wales on 2021 boundaries (6,856 in England, 408 in Wales), at Census
Day, 21 March 2021, hence calendar_year 2021: the table ons-census2021-ts054-tenure-lad
ports for local authorities, at a finer geography ({issue} item 3).

Artifact: Nomis's bulk download for TS054 (census2021-ts054.zip), whose member
census2021-ts054-msoa.csv has one row per MSOA and one column per category. The Nomis API
query the local authority package pins, at geography TYPE152 instead of TYPE424, returns
at most 25,000 rows to an unregistered user: 2,778 of the 7,264 MSOAs. Fetched in three
pages on 12 November 2026, its 65,376 rows equal the member's cells.

Ported, as for the local authority package: the eight detail categories and the
all-households total, under the same uk.local_geography.tenure.<bucket>.v1 spec ids and
c2021_tenure_9_name filters, so a target summing a bucket gets the same publisher facts at
either geography. The eight details sum to the total in every MSOA. The four roll-up
columns (Owned, Shared ownership, Social rented and Private rented) are sums of ported
details and stay in the source rows.

Semantics: households, not dwellings. ONS's quality statement for the variable says the
two social rented categories should be added together, because people misreport their
landlord between them. Census 2021's disclosure control (targeted record swapping and
cell key perturbation) can make counts differ slightly between tables, so an authority's
MSOAs need not sum to its local authority row.

Rows: the eight detail record sets share one list of MSOA rows, written once and
referenced by alias; the total record set has its own, marked total. Each row is guarded
by its MSOA code in column C.
"""


class AliasingDumper(yaml.SafeDumper):
    """YAML that writes a list shared by several record sets once, with an anchor."""


def ts054_categories() -> list[tuple[str, str, str, str]]:
    """(slug, spec id, category, row kind) per record set of the local authority package."""
    path = PACKAGES / TS054_LAD_DIRECTORY / "source_package.yaml"
    package = yaml.safe_load(path.read_text(encoding="utf-8"))
    categories = []
    for record_set in package["record_sets"]:
        record_set_id = record_set["record_set_id"]
        assert record_set_id.startswith(TS054_LAD_PREFIX), record_set_id
        (category,) = record_set["shared_filters"].values()
        kinds = {row["table_record_kind"] for row in record_set["rows"]}
        (kind,) = kinds
        categories.append(
            (
                record_set_id[len(TS054_LAD_PREFIX) :],
                record_set["record_set_spec_id"],
                category,
                kind,
            )
        )
    assert len(categories) == 9 and categories[0][3] == "total"
    return categories


def ts054_grid() -> dict[tuple[int, str], object]:
    """The MSOA member's cells, as the package's zip_delimited_text_full_rows parse sees them."""
    filename, path = manifest_file(TS054_DIRECTORY)
    with zipfile.ZipFile(path) as archive:
        content = archive.read(TS054_MEMBER)
    rows = source_rows_from_delimited_text(
        content, metadata(filename), sheet_name=TS054_MEMBER
    )
    cells = source_cells_from_source_rows(rows, selected_rows=())
    return {
        (row, column): value for (_sheet, row, column), value in grid_of(cells).items()
    }


def ts054_rows(grid: dict, kind: str) -> list[dict]:
    """One row per MSOA, in the member's order, guarded by its code in column C."""
    assert grid[(1, "C")] == "geography code" and grid[(1, "B")] == "geography"
    rows = []
    numbers = sorted({row for row, _ in grid if row > 1})
    assert numbers == list(range(2, 2 + 7264)), (numbers[0], numbers[-1])
    for ordinal, number in enumerate(numbers):
        code, name = grid[(number, "C")], grid[(number, "B")]
        assert grid[(number, "A")] == 2021, (number, grid[(number, "A")])
        assert re.fullmatch(r"[EW]02\d{6}", code), code
        rows.append(
            {
                "value_id": code.lower(),
                "label": name,
                "ordinal": ordinal,
                "row_number": number,
                "expected_row_header_column": "C",
                "expected_row_header": code,
                "geography_id": code,
                "geography_level": "msoa",
                "geography_name": name,
                "geography_vintage": "msoa_2021",
                "table_record_kind": kind,
            }
        )
    return rows


def build_ts054_msoa() -> str:
    grid = ts054_grid()
    columns = {
        value[len(TS054_PREFIX) :]: column
        for (row, column), value in grid.items()
        if row == 1 and isinstance(value, str) and value.startswith(TS054_PREFIX)
    }
    shared_rows = {kind: ts054_rows(grid, kind) for kind in ("total", "detail")}
    record_sets = []
    for slug, spec_id, category, kind in ts054_categories():
        column = columns[category]
        header = TS054_PREFIX + category
        assert grid[(1, column)] == header
        notes = f"{TS054_HOUSEHOLDS_NOTE} {TS054_SDC_NOTE}"
        if category.startswith("Social rented: "):
            notes += f" {TS054_SOCIAL_NOTE}"
        record_set_id = f"ons.census2021.ts054.msoa.{slug}"
        record_sets.append(
            {
                "record_set_id": record_set_id,
                "provenance_class": "census",
                "record_set_spec_id": spec_id,
                "source_record_id_prefix": record_set_id,
                "sheet_name": TS054_MEMBER,
                "period_type": "calendar_year",
                "period": 2021,
                "geography_id": "K04000001",
                "geography_level": "country",
                "geography_name": "England and Wales",
                "geography_vintage": "gss_2023",
                "entity": "household",
                "entity_role": "occupied_household",
                "domain": "housing_tenure",
                "groupby_dimension": "ons.census2021_msoa",
                "shared_filters": {"c2021_tenure_9_name": category},
                "shared_constraints": [
                    {
                        "variable": "c2021_tenure_9_name",
                        "operator": "==",
                        "value": category,
                        "label": "publisher tenure category",
                    }
                ],
                "measures": [
                    {
                        "measure_id": "households",
                        "label": "Occupied households",
                        "ordinal": 0,
                        "column": column,
                        "source_column_id": header,
                        "source_column_dimensions": {"c2021_tenure_9_name": category},
                        "concept": "ons.census2021_households",
                        "concept_evidence_url": TS054_URL,
                        "concept_evidence_notes": notes,
                        "unit": "count",
                        "aggregation": "sum",
                        "expected_cell_type": "number",
                        "expected_column_header_row": 1,
                        "expected_column_header": header,
                    }
                ],
                "rows": shared_rows[kind],
            }
        )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "ons-census2021-ts054-tenure-msoa",
        "label": (
            "Census 2021 TS054: households by tenure, middle layer super output areas of "
            "England and Wales"
        ),
        "dimension_labels": {"ons.census2021_msoa": "Middle layer super output area"},
        "artifact": {
            "source_name": "ons",
            "source_table": (
                "Census 2021 TS054 tenure of household, middle layer super output areas "
                "(2021), England and Wales"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{TS054_DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "census_2021",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": (
                "zip archive CSV member full-row parse, one source row per MSOA"
            ),
            "parser": "zip_delimited_text_full_rows",
            "archive_member": TS054_MEMBER,
            "sheet_name": TS054_MEMBER,
            "artifact_year": 2021,
        },
        "record_sets": record_sets,
    }
    lines: list[str] = []
    for paragraph in (
        textwrap.dedent(TS054_HEADER.format(issue=ISSUE)).strip().split("\n\n")
    ):
        if lines:
            lines.append("")
        lines += textwrap.wrap(
            " ".join(paragraph.split()), width=88, break_on_hyphens=False
        )
    comment = "".join(f"# {line}".rstrip() + "\n" for line in lines)
    return comment + yaml.dump(
        payload,
        Dumper=AliasingDumper,
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )


BUILDERS = {
    **{
        edition.directory: (lambda edition=edition: build_nbs(edition))
        for edition in NBS_EDITIONS
    },
    **{
        edition.directory: (lambda edition=edition: build_capital_stocks(edition))
        for edition in CS_EDITIONS
    },
    TS054_DIRECTORY: build_ts054_msoa,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the generated YAML with the committed files instead of writing.",
    )
    args = parser.parse_args()
    stale = []
    for directory, build in BUILDERS.items():
        text = build()
        path = PACKAGES / directory / "source_package.yaml"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(directory)
        else:
            write(directory, text)
    for directory in stale:
        print(f"stale: packages/{directory}/source_package.yaml")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
