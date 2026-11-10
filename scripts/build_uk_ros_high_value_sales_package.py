"""Generate Registers of Scotland's residential sales over £1 million for chronicle#420.

Run from the repository root:

    uv run python scripts/build_uk_ros_high_value_sales_package.py

``--check`` compares the generated YAML with the committed file instead of writing. The
package is written from the pinned workbook, read with Chronicle's own parser, so every
row number, column and guard cell below is one the package parser sees. The publisher's
text is asserted cell by cell, so a run against different bytes fails rather than
drifting. Nothing is downloaded and no value is computed.

Item 13 of PolicyEngine/chronicle#420, asked in PolicyEngine/chronicle#435 for
Microcosm's next data PR, for extending Microcosm's home-value step to Scotland
(PolicyEngine/uk-scottish-budget-2027-28#5; PolicyEngine/microcosm#1112): RoS's
Property Market Report 2025-26 data tables 9 and 10, the volume and value of residential
sales of more than £1 million by local authority, each financial year from 2023-24. RoS
publishes no split above £2 million. The RoS site answers scripted requests with HTTP
403, so María downloaded the workbook in a browser on 10 November 2026; the manifest
keeps the link the browser recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import textwrap
from pathlib import Path

import yaml
from openpyxl.utils import get_column_letter

from chronicle.sources.cells import SourceArtifactMetadata, source_cells_from_xlsx

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-11-10"
ISSUE = "PolicyEngine/chronicle#420"
SCRIPT = "scripts/build_uk_ros_high_value_sales_package.py"
PACKAGE_ID = "ros-property-market-report-2025-26"
DIRECTORY = "ros/property_market_report_2025_26"
PAGE = "https://www.ros.gov.uk/data-and-statistics/property-market-statistics/property-market-report"
YEARS = (2023, 2024, 2025)  # #420: each financial year from 2023-24
HEADER_ROW = 6


class Flow(dict):
    """A small mapping written on one line, as the occupation packages write guards."""


class PackageDumper(yaml.SafeDumper):
    """Plain YAML with no anchors, so every record set reads on its own."""

    def ignore_aliases(self, data: object) -> bool:
        return True


PackageDumper.add_representer(
    Flow,
    lambda dumper, data: dumper.represent_mapping(
        "tag:yaml.org,2002:map", data, flow_style=True
    ),
)


def render(header: str, payload: dict) -> str:
    """The header's paragraphs, rewrapped as comment lines, then the package."""
    lines: list[str] = []
    for paragraph in textwrap.dedent(header).strip().split("\n\n"):
        if lines:
            lines.append("")
        lines += textwrap.wrap(
            " ".join(paragraph.split()),
            width=88,
            break_long_words=False,
            break_on_hyphens=False,
        )
    comment = "".join(f"# {line}".rstrip() + "\n" for line in lines)
    return comment + yaml.dump(
        payload, Dumper=PackageDumper, sort_keys=False, allow_unicode=True, width=100
    )


def pinned(directory: str) -> tuple[dict, bytes]:
    """The manifest's one file entry and its bytes, checked against the pinned digest."""
    manifest = yaml.safe_load((DATA / directory / "manifest.yaml").read_text())
    (entry,) = manifest["files"].values()
    content = (DATA / directory / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"], directory
    assert len(content) == entry["size_bytes"], directory
    return entry, content


def grid_of(content: bytes, filename: str) -> dict[tuple[str, int, str], object]:
    metadata = SourceArtifactMetadata(
        source_name="",
        source_table="",
        source_file=filename,
        url=None,
        vintage="",
        sha256="",
        size_bytes=0,
        extracted_at="",
        extraction_method="",
    )
    grid: dict[tuple[str, int, str], object] = {}
    for cell in source_cells_from_xlsx(content, metadata):
        if cell.raw_value in (None, ""):
            continue
        grid[
            (cell.sheet_name, cell.row_number, get_column_letter(cell.column_number))
        ] = cell.raw_value
    return grid


def squeeze(text: object) -> str:
    return " ".join(str(text).replace("\xad", "").split())


def guard(column: str, value: object, label: str) -> Flow:
    return Flow(column=column, expected_value=value, label=label)


def year_label(year: int) -> str:
    return f"{year}-{(year + 1) % 100:02d}"


# The Metadata sheet's text the package relies on, by row.
METADATA = {
    9: "Property Market Report 2025-26",
    18: "The data in this publication is extracted from Registers of Scotland's Land "
    "Register.",
    21: "This is an official statistics publication for Scotland.",
    23: "Only true market residential sales are included in these figures. For example, "
    "sales of a share of a residential property which may occur when one of the joint owners "
    "of a shared property buys out the share of the other owner are excluded as they might "
    "not reflect the true market value and could therefore have an impact on the house price "
    "statistics. Non-residential sales where the sale price is a token amount or is a "
    "non-monetary amount are also not included.",
    39: "You may use or reuse this information (not including logos) free of charge in any "
    "format or medium, under the Open Government Licence. If you use or publish this data, "
    "please acknowledge the data as Crown copyright and Registers of Scotland as the source, "
    "and add the following attribution statement:",
    40: "Contains Registers of Scotland data © Crown copyright and database right 2026. This "
    "data is licensed under the Open Government Licence v3.0.",
}
TABLES = (
    {
        "sheet": "9",
        "title": "Table 9 - Volume of residential property sales more than £1 million, by "
        "local authority, 2003-04 to 2025-26",
        "measure_id": "residential_property_sales",
        "label": "Volume of residential property sales more than £1 million",
        "concept": "ros.residential_property_sales",
        "unit": "count",
        "scale": None,
    },
    {
        "sheet": "10",
        "title": "Table 10 - Value of residential property sales more than £1 million "
        "(£million), by local authority, 2003-04 to 2025-26",
        "measure_id": "residential_property_sales_value",
        "label": "Value of residential property sales more than £1 million",
        "concept": "ros.residential_property_sales_value",
        "unit": "gbp",
        "scale": 1000000,
    },
)


def register_names() -> dict[str, str]:
    register = json.loads(
        (ROOT / "chronicle/geography/uk_canonical_names.json").read_text()
    )
    names = {
        code: name for code, name in register["names"].items() if code.startswith("S12")
    }
    assert len(names) == 32, len(names)
    return names


def table_rows(grid: dict, sheet: str) -> list[tuple[int, str, str]]:
    """(row, printed name, code) for each council area, then Scotland."""
    rows = []
    row = HEADER_ROW + 1
    while (sheet, row, "C") in grid:
        rows.append((row, grid[(sheet, row, "B")], grid[(sheet, row, "C")]))
        row += 1
    assert rows[-1][1:] == ("Scotland", "S92000003"), (sheet, rows[-1])
    return rows


def year_columns(grid: dict, sheet: str) -> dict[int, str]:
    assert grid[(sheet, HEADER_ROW, "B")] == "Local authority"
    assert grid[(sheet, HEADER_ROW, "C")] == "Local authority code"
    headers = {
        value: column
        for (name, row, column), value in grid.items()
        if name == sheet and row == HEADER_ROW and column not in ("B", "C")
    }
    assert "2025-26" in headers and max(headers, key=lambda h: headers[h]) == "2025-26"
    return {year: headers[year_label(year)] for year in YEARS}


def build() -> str:
    entry, content = pinned(DIRECTORY)
    grid = grid_of(content, entry["filename"])
    for row, text in METADATA.items():
        assert squeeze(grid[("Metadata", row, "B")]) == squeeze(text), row
    updated = grid[("Metadata", 14, "C")]
    assert grid[("Metadata", 14, "B")] == "Last updated"
    assert updated == "2026-06-09T00:00:00", (
        updated
    )  # the parser writes dates as ISO text
    names = register_names()
    values: dict[tuple[str, int, str], float] = {}
    layouts = {}
    for table in TABLES:
        sheet = table["sheet"]
        assert grid[(sheet, 5, "B")] == table["title"], sheet
        columns = year_columns(grid, sheet)
        rows = table_rows(grid, sheet)
        for _, printed, code in rows[:-1]:
            assert names[code] == printed, (sheet, code, printed)
        for year, column in columns.items():
            for row, _, code in rows:
                value = grid[(sheet, row, column)]
                assert isinstance(value, (int, float)) and value >= 0, (
                    sheet,
                    row,
                    value,
                )
                values[(sheet, year, code)] = value
        layouts[sheet] = (columns, rows)
    orders = {tuple(code for _, _, code in rows) for _, rows in layouts.values()}
    assert len(orders) == 1, "tables 9 and 10 list the same areas in one order"
    (order,) = orders
    absent = sorted(set(names) - set(order))
    assert len(order) - 1 + len(absent) == 32
    # Parity: the councils add to Scotland, and Table 9's Scotland row is Table 8's
    # band J (over £1,000,000) row.
    band_row = next(
        row
        for (name, row, column), value in grid.items()
        if name == "8" and column == "B" and value == "J - over £1,000,000"
    )
    band_columns = {
        value: column
        for (name, row, column), value in grid.items()
        if name == "8" and row == HEADER_ROW and column != "B"
    }
    for year in YEARS:
        councils = [code for code in order if code.startswith("S12")]
        volume = sum(values[("9", year, code)] for code in councils)
        assert volume == values[("9", year, "S92000003")], year
        value = sum(values[("10", year, code)] for code in councils)
        assert math.isclose(value, values[("10", year, "S92000003")], abs_tol=1e-6), (
            year
        )
        band = grid[("8", band_row, band_columns[year_label(year)])]
        assert band == values[("9", year, "S92000003")], (year, band)
    record_sets = []
    for table in TABLES:
        sheet = table["sheet"]
        columns, rows = layouts[sheet]
        for year in YEARS:
            record_set_id = f"ros.pmr_2025_26.{table['measure_id']}_over_1m.fy{year}"
            entries = []
            for ordinal, (row, printed, code) in enumerate(rows):
                scotland = code == "S92000003"
                area = {
                    "value_id": code.lower(),
                    "label": printed,
                    "ordinal": ordinal,
                    "row_number": row,
                    "expected_row_header_column": "B",
                    "expected_row_header": printed,
                    "geography_id": code,
                    "geography_level": "country" if scotland else "local_authority",
                    "geography_name": printed,
                    "geography_vintage": "current" if scotland else "ca_2019",
                    "table_record_kind": "total" if scotland else "detail",
                    "guard_cells": [guard("C", code, "local authority code")],
                }
                if ordinal == 0:
                    area["guard_cells"].append(
                        Flow(
                            column="B",
                            row=5,
                            expected_value=table["title"],
                            label="table title",
                        )
                    )
                entries.append(area)
            measure = {
                "measure_id": table["measure_id"],
                "label": table["label"],
                "ordinal": 0,
                "column": columns[year],
                "source_column_id": year_label(year),
                "expected_column_header_row": HEADER_ROW,
                "expected_column_header": year_label(year),
                "concept": table["concept"],
                "source_concept": table["concept"],
                "concept_relation": "source_label",
                "concept_authority": "ros",
                "concept_evidence_url": PAGE,
                "concept_evidence_notes": (
                    f"Property Market Report 2025-26 data tables, {table['title']}, column "
                    f"'{year_label(year)}'. {METADATA[23]} {METADATA[18]}"
                ),
                "unit": table["unit"],
                "aggregation": "sum",
                "expected_cell_type": "number",
            }
            if table["scale"]:
                measure["value_scale"] = table["scale"]
            record_sets.append(
                {
                    "record_set_id": record_set_id,
                    "provenance_class": "administrative",
                    "assertion": "observation",
                    "record_set_spec_id": f"ros.pmr.{table['measure_id']}_over_1m.v1",
                    "source_record_id_prefix": record_set_id,
                    "sheet_name": sheet,
                    "period_type": "fiscal_year",
                    "period": year,
                    "period_coverage": {
                        "start_date": f"{year}-04-01",
                        "end_date": f"{year + 1}-03-31",
                        "basis": "fiscal",
                        "source_period_label": year_label(year),
                        "notes": "Sales in the financial year, a flow of transactions, not "
                        "the stock of homes worth more than £1 million; period.value stores "
                        "the opening year.",
                    },
                    "geography_id": "S92000003",
                    "geography_level": "country",
                    "geography_name": "Scotland",
                    "geography_vintage": "current",
                    "entity": "dwelling",
                    "entity_role": "residential_property_sale",
                    "domain": "residential_property_transactions",
                    "groupby_dimension": "geography",
                    "shared_filters": {"house_price_band": "over_1m"},
                    "shared_constraints": [
                        Flow(
                            variable="house_price_band",
                            operator="==",
                            value="over_1m",
                            label="House price band",
                        ),
                        Flow(
                            variable="sale_price",
                            operator=">",
                            value=1000000,
                            unit="gbp",
                            label="Sale price",
                        ),
                    ],
                    "rows": entries,
                    "measures": [measure],
                }
            )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": "Registers of Scotland Property Market Report 2025-26: residential sales of "
        "more than £1 million by local authority, volume and value, 2023-24 to 2025-26",
        "dimension_labels": {
            "geography": "Geography",
            "house_price_band": "House price band",
        },
        "dimension_value_labels": {
            "house_price_band": {"over_1m": "More than £1 million"},
        },
        "artifact": {
            "source_name": "ros",
            "source_table": "Property Market Report 2025-26 data tables 9 and 10",
            "resource_package": "db",
            "resource_directory": f"data/{DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "property_market_report_2025_26_2026_06_09",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": f"xlsx used-range cell parse ({entry['filename']})",
            "parser": "xlsx_used_range",
            "sheets": ["9", "10"],
            "sheet_name": "9",
            "artifact_year": 2026,
        },
        "record_sets": record_sets,
    }
    facts = sum(len(rs["rows"]) * len(rs["measures"]) for rs in record_sets)
    totals = {year: values[("9", year, "S92000003")] for year in YEARS}
    absent_sorted = sorted(names[code] for code in absent)
    absent_names = ", ".join(absent_sorted[:-1]) + " or " + absent_sorted[-1]
    header = f"""
    Registers of Scotland, Property Market Report 2025-26 data tables (last updated 9 June
    2026, {PAGE}), tables 9 and 10, for {ISSUE} item 13
    (PolicyEngine/uk-scottish-budget-2027-28#5; PolicyEngine/microcosm#1112), asked in
    PolicyEngine/chronicle#435. Written
    by {SCRIPT} from the pinned workbook. The RoS site answers scripted requests with HTTP
    403; María downloaded the workbook in a browser on 10 November 2026, and the manifest
    keeps the link it recorded.

    Ported: the volume (table 9) and value (table 10, '£million', scaled to pounds) of
    residential property sales of more than £1 million, for Scotland and each local
    authority the tables list, in each financial year 2023-24, 2024-25 and 2025-26.
    Scotland's volumes are {totals[2023]}, {totals[2024]} and {totals[2025]}. The price
    band is the filter house_price_band over_1m with the constraint sale_price >
    £1,000,000, on concepts ros.residential_property_sales and
    ros.residential_property_sales_value. These are sales, a flow over the year, not the
    stock of homes worth more than £1 million; 'Only true market residential sales are
    included' (Metadata sheet).

    The tables list 27 of the 32 council areas, with the publisher's own codes; they print
    no row for {absent_names}. The 27 add to Scotland in every ported year (the
    generator asserts it), so those five had no such sales in these years. Table 9's
    Scotland row equals table 8's band 'J - over £1,000,000' in every ported year.

    Not ported: the years before 2023-24, not asked in {ISSUE}; table 11's top postal
    districts; and the rest of the report. RoS publishes no split above £2 million, which
    {ISSUE} also asks for: that needs an ad hoc table from RoS. {facts} facts.
    """
    return render(header, payload)


BUILDERS = {DIRECTORY: build}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the generated YAML with the committed file instead of writing.",
    )
    args = parser.parse_args()
    stale = []
    for directory, build_package in BUILDERS.items():
        text = build_package()
        path = PACKAGES / directory / "source_package.yaml"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(directory)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    for directory in stale:
        print(f"stale: packages/{directory}/source_package.yaml")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
