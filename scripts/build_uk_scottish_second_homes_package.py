"""Generate Scotland's second homes and empty dwellings package for PolicyEngine/chronicle#435.

Run from the repository root:

    uv run python scripts/build_uk_scottish_second_homes_package.py

``--check`` compares the generated YAML with the committed file instead of writing. The
package is written from the pinned workbook, read with Chronicle's own parser, so every
row number, column and guard cell below is one the package parser sees. The publisher's
text is asserted cell by cell, so a run against different bytes fails rather than
drifting. Nothing is downloaded and no value is computed.

Item 1 of the issue, for Microcosm's Scottish council tax level (PolicyEngine/microcosm#1095):
the Scottish Government's "Second homes and empty properties in September 2025" (published
16 December 2025), from the councils' council tax base (CTAXBASE) returns. All six tables
of its web table, for Scotland and its 32 council areas, at September 2024 and September
2025: second homes, empty properties (empty for more than 6 months and liable for council
tax), long-term empty properties (12 months or more), the long-term empty properties with a
discount below 10% or an increase, dwellings with an unoccupied exemption, and second homes
plus empty properties.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import textwrap
from dataclasses import dataclass
from pathlib import Path

import yaml
from openpyxl.utils import get_column_letter

from chronicle.sources.cells import SourceArtifactMetadata, source_cells_from_xlsx

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-11-10"
ISSUE = "PolicyEngine/chronicle#435"
SCRIPT = "scripts/build_uk_scottish_second_homes_package.py"
PACKAGE_ID = "scotgov-second-homes-empty-properties-2025"
PACKAGE_DIRECTORY = "scotgov/second_homes_empty_properties_2025"
DATA_DIRECTORY = "scotgov/second_homes_empty_properties_2025"
PAGE = "https://www.gov.scot/publications/second-homes-and-empty-properties-in-september-2025/"
TITLE = "Second homes and empty properties in September 2025"
YEARS = (
    2024,
    2025,
)  # #435: September 2024, and September 2025 where the tables carry it
HEADER_ROW = 4
SCOTLAND_ROW = 5  # the 32 council areas follow, rows 6 to 37


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


def metadata(filename: str) -> SourceArtifactMetadata:
    return SourceArtifactMetadata(
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


def pinned(directory: str) -> tuple[dict, bytes]:
    """The manifest's one file entry and its bytes, checked against the pinned digest."""
    manifest = yaml.safe_load((DATA / directory / "manifest.yaml").read_text())
    (entry,) = manifest["files"].values()
    content = (DATA / directory / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"], directory
    assert len(content) == entry["size_bytes"], directory
    return entry, content


def grid_of(cells) -> dict[tuple[str, int, str], object]:
    grid: dict[tuple[str, int, str], object] = {}
    for cell in cells:
        if cell.raw_value in (None, ""):
            continue
        grid[
            (cell.sheet_name, cell.row_number, get_column_letter(cell.column_number))
        ] = cell.raw_value
    return grid


def write(directory: str, text: str) -> None:
    path = PACKAGES / directory / "source_package.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def guard(column: str, row: int, value: object, label: str) -> Flow:
    return Flow(column=column, row=row, expected_value=value, label=label)


def squeeze(text: object) -> str:
    return " ".join(str(text).replace("\xa0", " ").split())


def is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------- the publisher's text

# The cover sheet's definitions, quoted in each measure's evidence notes.
SECOND_HOMES = (
    "Second homes: homes which are furnished and lived in for at least 25 days in a "
    "12-month period but not as someone’s main residence."
)
EMPTY = (
    "Empty Properties: properties which have been empty for more than 6 months and are "
    "liable for council tax. Of which, there are long term empty properties (empty for "
    "more than 12 months)."
)
UNOCCUPIED = (
    "Unoccupied Exemptions: the total number of dwellings exempt from Council Tax due to "
    "being unoccupied. Examples being housing awaiting demolition or a new build waiting to "
    "be occupied (please refer to the Council Tax (Exempt Dwellings) (Scotland) Order 1997 "
    "for more information)."
)
COVER = {
    5: "Information on empty properties and second homes is collected each year from local "
    "authorities through the council tax base (CTAXBASE) data collection.",
    7: "Data presented for September each year for:",
    8: SECOND_HOMES,
    9: EMPTY,
    10: UNOCCUPIED,
    16: "Last update: December 2025",
    18: "Latest data available: 2025",
}

# The notes sheet's notes on these classes in 2024 and 2025, quoted as published. Notes 3
# to 9 concern earlier years only.
NOTES = {
    1: "Trends over time for all these statistics should be interpreted with some caution, "
    "given that increases and decreases can be caused in part by reclassification exercises "
    "which local authorities carry out from time to time, or issues with management "
    "information systems, rather than being real changes in the numbers of properties.",
    2: "From 1st April 2013 local authorities gained the discretionary power to remove the "
    "empty properties discount or set a council tax increase of 100% on certain properties "
    "which have been empty for one year or more. This, along with associated improvements in "
    "the data held by local authorities, has led to the reclassification of a number of "
    "properties and has had a significant bearing on the year-on-year changes in the figures.",
    10: "In September 2024 the guidance for empty properties data collection was "
    "strengthened to ensure that councils excluded properties empty less than 6 months from "
    "their data return (in CTAXBASE 8b). It was discovered that prior to 2024 some councils "
    "had included these in their return to the Scottish Government. Empty homes (properties "
    "empty for more than 6 months) will therefore be overstated in such instances; however, "
    "we are not able to quantify the impact of their inclusion on published statistics "
    "before 2024. The decrease of 6% in empty homes between 2023 and 2024, is likely to be "
    "associated with a programme of work to clarify that empty homes should only be recorded "
    "at 6 months or over. This decrease was driven by the City of Edinburgh, where data from "
    "2024 is now provided for empty homes 6 months or over (decrease of 57%, -4,107).",
    11: "Following the strengthening of guidance described in note 10, there was one "
    "authority (South Ayrshire) who reported they have a very small number of properties "
    "empty less than 6 months included in the total for empty properties.",
    12: "Caution should be taken when interpreting the North Lanarkshire change between 2023 "
    "and 2024 as it seems likely, rather than an increase in empty homes this year, that "
    "their previous returns have under reported empty homes.",
    13: "As a result of a cyber attack on Na h-Eileanan Siar in November 2023 the council was "
    "still working through a large backlog of changes to accounts and properties at the time "
    "of the 2024 data collection. For this reason, the figures are not as up to date as they "
    "would normally be.",
    14: "Powers enabling Councils in Scotland to apply either, a 50% Council Tax discount, the "
    "standard rate, or an up to 100% council tax premium (double the rate) on second homes "
    "came into force in April 2024. 30 local authorities have introduced the premium in some "
    "form as of September 2024.",
}


def quoted(numbers: tuple[int, ...]) -> str:
    return " ".join(f"Note {number}: '{NOTES[number]}'" for number in numbers)


@dataclass(frozen=True)
class Table:
    sheet: str
    title: str  # cell A1
    contents: str  # the contents sheet's description of the worksheet
    measure_id: str
    label: str
    role: str
    definition: str
    notes: tuple[int, ...]


TABLES = (
    Table(
        "Second Homes Empty Properties",
        "Total Second Homes and  Empty Properties",
        "Total Second Homes and Long Term Empty Properties",
        "second_homes_and_empty_properties",
        "Second homes and empty properties",
        "chargeable_dwelling",
        "The worksheet's total of second homes and empty properties. The contents sheet "
        "describes it as 'Total Second Homes and Long Term Empty Properties'; in every cell "
        "it is the Second Homes table plus the Empty Properties (6 months +) table, which "
        "the generator asserts. " + SECOND_HOMES + " " + EMPTY,
        (1, 10, 11, 14),
    ),
    Table(
        "Second Homes",
        "Second Homes",
        "Second Homes",
        "second_homes",
        "Second homes",
        "chargeable_dwelling",
        SECOND_HOMES,
        (1, 14),
    ),
    Table(
        "Empty Properties (6 months +)",
        "Empty Properties (6 months +)",
        "Empty properties (6 months +)",
        "empty_properties",
        "Empty properties (empty for more than 6 months, liable for council tax)",
        "chargeable_dwelling",
        EMPTY,
        (1, 10, 11, 12),
    ),
    Table(
        "Long Term Empty 12 Months",
        "Long Term Empty Properties: 12 months or more",
        "Long Term Empty Properties: 12 months or more",
        "long_term_empty_properties",
        "Long-term empty properties (empty for 12 months or more)",
        "chargeable_dwelling",
        EMPTY,
        (1, 2, 10, 11),
    ),
    Table(
        "Long Term Empty Discount",
        "Long Term Empty Properties: 12 months or more and where a discount below 10% or an "
        "increase has been applied",
        "Long Term Empty Properties: 12 months or more and where a discount below 10% or an "
        "increase has been applied",
        "long_term_empty_properties_discount_below_10_percent_or_increase",
        "Long-term empty properties with a discount below 10% or an increase",
        "chargeable_dwelling",
        "Long-term empty properties (12 months or more) where a council tax discount below "
        "10% or an increase has been applied. " + EMPTY,
        (1, 2),
    ),
    Table(
        "Unoccupied Exemptions",
        "Number of dwellings receiving an exemption from council tax due to being an "
        "unoccupied exemption",
        "Unoccupied Exemptions",
        "unoccupied_exemptions",
        "Dwellings with an unoccupied exemption from council tax",
        "exempt_dwelling",
        UNOCCUPIED,
        (1,),
    ),
)
SHEETS = {table.sheet: table for table in TABLES}
SECOND, EMPTY_6M, LTE, LTE_DISCOUNT, TOTAL = (
    "Second Homes",
    "Empty Properties (6 months +)",
    "Long Term Empty 12 Months",
    "Long Term Empty Discount",
    "Second Homes Empty Properties",
)

# The one published Scotland cell its 32 council rows do not add to: the empty homes page
# of the same edition gives "25,703 properties (79%) received either a discount of less
# than 10% or a Council Tax premium", the councils' sum, where the web table prints
# 25,073. Ported as printed; the generator fails if a corrected file is pinned.
MISPRINT = {(LTE_DISCOUNT, 2025): (25073, 25703)}

SCOTLAND = {
    "geography_id": "S92000003",
    "geography_level": "country",
    "geography_name": "Scotland",
    "geography_vintage": "current",
}

# Chronicle's register names every council area; the web table spells some its own way.
COUNCIL_ALIASES = {
    "Argyll & Bute": "Argyll and Bute",
    "Dumfries & Galloway": "Dumfries and Galloway",
    "Edinburgh, City of": "City of Edinburgh",
    "Glasgow": "Glasgow City",
    "Perth & Kinross": "Perth and Kinross",
}


def register_names() -> dict[str, str]:
    """The register's name for each Scottish council area code."""
    register = json.loads(
        (ROOT / "chronicle/geography/uk_canonical_names.json").read_text()
    )
    names = {
        code: name for code, name in register["names"].items() if code.startswith("S12")
    }
    assert len(names) == 32 and len(set(names.values())) == 32, len(names)
    return names


# ---------------------------------------------------------------- reading the workbook


def check_text(grid: dict) -> None:
    """Assert the cover, notes and contents sheets' text the package relies on."""
    for row, text in COVER.items():
        assert squeeze(grid[("COVER SHEET", row, "A")]) == squeeze(text), row
    for number, text in NOTES.items():
        row = number + 4
        assert grid[("NOTES", row, "A")] == number, (row, number)
        assert squeeze(grid[("NOTES", row, "B")]) == squeeze(text), number
    contents = {
        squeeze(grid[("CONTENTS", row, "A")]): squeeze(grid[("CONTENTS", row, "C")])
        for row in range(10, 16)
    }
    assert contents == {table.sheet: table.contents for table in TABLES}, contents


def year_columns(grid: dict, sheet: str) -> dict[int, str]:
    """{year: column} from the header row; the published years end at 2025."""
    assert grid[(sheet, HEADER_ROW, "A")] == "Local Authority", sheet
    columns = {}
    for (name, row, column), value in grid.items():
        if name == sheet and row == HEADER_ROW and column != "A":
            assert isinstance(value, str) and value.isdigit(), (sheet, column, value)
            columns[int(value)] = column
    assert max(columns) == YEARS[-1], (sheet, max(columns))
    return {year: columns[year] for year in YEARS}


def area_rows(
    grid: dict, sheet: str, names: dict[str, str]
) -> list[tuple[int, str, str]]:
    """(row, printed name, code) for Scotland, then the 32 council areas in order."""
    codes = {name: code for code, name in names.items()}
    printed = grid[(sheet, SCOTLAND_ROW, "A")]
    assert squeeze(printed).lower() == "scotland", (sheet, printed)
    rows = [(SCOTLAND_ROW, printed, SCOTLAND["geography_id"])]
    for row in range(SCOTLAND_ROW + 1, SCOTLAND_ROW + 33):
        printed = grid[(sheet, row, "A")]
        name = squeeze(printed)
        rows.append((row, printed, codes[COUNCIL_ALIASES.get(name, name)]))
    assert (sheet, SCOTLAND_ROW + 33, "A") not in grid, sheet
    assert len({code for _, _, code in rows}) == 33, sheet
    return rows


def check_parity(values: dict) -> dict[str, int]:
    """Assert the publisher's own identities on the ported cells.

    ``values`` maps (sheet, year, code) to the published count. The 32 councils add to
    Scotland in every table but one misprinted cell; second homes plus empty properties
    is the total; long-term empty is within empty, and those with a discount below 10%
    or an increase are within long-term empty.
    """
    codes = sorted({code for (_, _, code) in values})
    councils = [code for code in codes if code.startswith("S12")]
    checks = {"council sums": 0, "class identities": 0}
    for table in TABLES:
        for year in YEARS:
            scotland = values[(table.sheet, year, SCOTLAND["geography_id"])]
            total = sum(values[(table.sheet, year, code)] for code in councils)
            if (table.sheet, year) in MISPRINT:
                assert (scotland, total) == MISPRINT[(table.sheet, year)], (
                    scotland,
                    total,
                )
            else:
                assert scotland == total, (table.sheet, year, scotland, total)
            checks["council sums"] += 1
    for year in YEARS:
        for code in codes:
            second, empty, total = (
                values[(sheet, year, code)] for sheet in (SECOND, EMPTY_6M, TOTAL)
            )
            assert second + empty == total, (year, code)
            assert values[(LTE, year, code)] <= empty, (year, code)
            assert values[(LTE_DISCOUNT, year, code)] <= values[(LTE, year, code)], (
                year,
                code,
            )
            checks["class identities"] += 1
    return checks


# ---------------------------------------------------------------- the package


def rows_of(table: Table, areas, names: dict[str, str], geography_names: dict) -> list:
    rows = []
    for ordinal, (row, printed, code) in enumerate(areas):
        if code == SCOTLAND["geography_id"]:
            entry = {
                "value_id": code.lower(),
                "label": "Scotland",
                "ordinal": ordinal,
                "row_number": row,
                "expected_row_header_column": "A",
                "expected_row_header": printed,
                **SCOTLAND,
                "table_record_kind": "total",
                "guard_cells": [
                    guard("A", 1, table.title, "table title"),
                    guard("A", HEADER_ROW, "Local Authority", "row header label"),
                ],
            }
        else:
            entry = {
                "value_id": code.lower(),
                "label": names[code],
                "ordinal": ordinal,
                "row_number": row,
                "expected_row_header_column": "A",
                "expected_row_header": printed,
                "geography_id": code,
                "geography_level": "local_authority",
                "geography_name": geography_names[code],
                "geography_vintage": "ca_2019",
                "table_record_kind": "detail",
            }
        rows.append(entry)
    return rows


def record_set(table: Table, year: int, column: str, rows: list) -> dict:
    record_set_id = (
        f"scotgov.second_homes_empty_properties_2025.{table.measure_id}.y{year}"
    )
    period_notes = (
        f"'Data presented for September each year' (cover sheet): the councils' council "
        f"tax base (CTAXBASE) returns at September {year}, read from the {TITLE} edition."
    )
    if year == 2024:
        period_notes += " " + quoted((13,))
    return {
        "record_set_id": record_set_id,
        "provenance_class": "administrative",
        "assertion": "observation",
        "record_set_spec_id": (
            "uk.local_geography.council_tax.scotland_second_homes_empty_properties."
            f"{table.measure_id}.v1"
        ),
        "source_record_id_prefix": record_set_id,
        "sheet_name": table.sheet,
        "period_type": "month",
        "period": f"{year}-09",
        "period_coverage": {
            "basis": "calendar",
            "source_period_label": f"September {year}",
            "notes": period_notes,
        },
        **SCOTLAND,
        "entity": "dwelling",
        "entity_role": table.role,
        "domain": "council_tax_stock",
        "groupby_dimension": "geography",
        "measures": [
            {
                "measure_id": table.measure_id,
                "label": table.label,
                "ordinal": 0,
                "column": column,
                "source_column_id": table.measure_id,
                "expected_column_header_row": HEADER_ROW,
                "expected_column_header": str(year),
                "concept": f"scotgov.council_tax.{table.measure_id}",
                "source_concept": f"scotgov.council_tax.{table.measure_id}",
                "concept_relation": "source_label",
                "concept_authority": "scotgov",
                "concept_evidence_url": PAGE,
                "concept_evidence_notes": (
                    f"{TITLE}, web table, sheet '{table.sheet}' ('{squeeze(table.title)}'), "
                    f"column {column} ('{year}'). {table.definition} "
                    + quoted(table.notes)
                ),
                "unit": "count",
                "aggregation": "sum",
                "expected_cell_type": "number",
            }
        ],
        "rows": rows,
    }


def build() -> str:
    entry, content = pinned(DATA_DIRECTORY)
    grid = grid_of(source_cells_from_xlsx(content, metadata(entry["filename"])))
    check_text(grid)
    names = register_names()
    values: dict[tuple[str, int, str], int] = {}
    areas_by_sheet = {}
    for table in TABLES:
        assert squeeze(grid[(table.sheet, 1, "A")]) == squeeze(table.title), table.sheet
        assert grid[(table.sheet, 1, "A")] == table.title, table.sheet
        columns = year_columns(grid, table.sheet)
        areas = area_rows(grid, table.sheet, names)
        areas_by_sheet[table.sheet] = (columns, areas)
        for year, column in columns.items():
            for row, _, code in areas:
                value = grid[(table.sheet, row, column)]
                assert is_count(value) and value >= 0, (table.sheet, row, column, value)
                values[(table.sheet, year, code)] = value
    orders = {
        tuple(code for _, _, code in areas) for _, areas in areas_by_sheet.values()
    }
    assert len(orders) == 1, "the six tables list the areas in one order"
    # One name per area: the first table's spelling, whitespace squeezed.
    geography_names = {
        code: squeeze(printed)
        for _, printed, code in areas_by_sheet[TABLES[0].sheet][1]
        if code != SCOTLAND["geography_id"]
    }
    checks = check_parity(values)
    record_sets = []
    for table in TABLES:
        columns, areas = areas_by_sheet[table.sheet]
        rows = rows_of(table, areas, names, geography_names)
        for year in YEARS:
            record_sets.append(record_set(table, year, columns[year], rows))
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": (
            "Scottish Government Second Homes and Empty Properties, September 2025 edition: "
            "second homes, empty and long-term empty properties and unoccupied exemptions "
            "by council area, September 2024 and 2025"
        ),
        "dimension_labels": {"geography": "Geography"},
        "artifact": {
            "source_name": "scotgov",
            "source_table": f"{TITLE}: web table",
            "resource_package": "db",
            "resource_directory": f"data/{DATA_DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "second_homes_empty_properties_2025_12_16",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": f"xlsx used-range cell parse ({entry['filename']})",
            "parser": "xlsx_used_range",
            "sheets": [table.sheet for table in TABLES],
            "sheet_name": TABLES[0].sheet,
            "artifact_year": 2025,
        },
        "record_sets": record_sets,
    }
    facts = sum(len(rs["rows"]) * len(rs["measures"]) for rs in record_sets)
    scotland = {
        (sheet, year): values[(sheet, year, SCOTLAND["geography_id"])]
        for sheet in (SECOND, EMPTY_6M, LTE)
        for year in YEARS
    }
    header = f"""
    Scottish Government, '{TITLE}' (published 16 December 2025, {PAGE}), the web table's
    six tables, for {ISSUE} item 1 (Microcosm's Scottish council tax level,
    PolicyEngine/microcosm#1095). Written by {SCRIPT} from the pinned workbook. The
    councils' council tax base (CTAXBASE) returns give the counts; 'Data presented for
    September each year' (cover sheet), so each year is month YYYY-09, as the CTAXBASE
    chargeable dwellings packages stamp their September counts.

    Ported, for Scotland and its 32 council areas at September 2024 and September 2025:
    second homes; empty properties, empty for more than 6 months and liable for council
    tax; long-term empty properties, 12 months or more; the long-term empty properties
    where a discount below 10% or an increase has been applied; dwellings with an
    unoccupied exemption from council tax; and the worksheet of second homes plus empty
    properties. Each class is its own concept, scotgov.council_tax.<measure id>, with the
    cover sheet's definition and the notes on it quoted in the evidence notes. Second homes
    and empty properties are chargeable dwellings (entity role chargeable_dwelling, as
    MHCLG's Council Taxbase lines 11 to 17); unoccupied exemptions are exempt_dwelling.
    The September 2024 edition's web table (published 17 December 2024, sha256 8c796fb0…)
    prints the same cells for every year to 2024: this edition revises none of them.

    Not ported: the years before 2024 (from 1996, 2005, 2013 or 2014), not asked in
    {ISSUE}, some of which notes 3 to 9 qualify. Nothing in the edition splits the counts by council tax band or
    by premium or discount rate beyond the long-term empty table, and CTAXBASE's published
    tables give chargeable dwellings by band only (the scotgov-council-tax-bands packages),
    with no Band D equivalents by class.

    Geography: Scotland and the register's S12 codes. The web table spells some areas its
    own way ('Edinburgh, City of', 'Glasgow' on two sheets, '&' for 'and', 'SCOTLAND' and
    trailing spaces on some sheets); each row guard carries its sheet's exact text, and
    each area's geography name is its first sheet's spelling.

    Caveats, quoted in the evidence notes: trends 'should be interpreted with some caution'
    (note 1); empty homes before 2024 'will therefore be overstated' where councils
    included properties empty less than 6 months (note 10), and South Ayrshire still
    includes 'a very small number' of them (note 11); Na h-Eileanan Siar's 2024 figures
    'are not as up to date as they would normally be' (note 13); and the second homes
    premium powers from April 2024 (note 14).

    Parity, asserted by the generator: in every table and year the 32 councils add to
    Scotland ({checks["council sums"]} checks) except one misprinted cell, the long-term
    empty properties with a discount below 10% or an increase at September 2025, where
    the Scotland row prints 25,073 and the councils add to 25,703, the figure the
    edition's empty homes page gives; it is ported as printed. In every area and year
    ({checks["class identities"]} checks) second homes plus empty properties is the
    total, long-term empty is within empty, and the discount or increase subset is
    within long-term empty. Scotland: second homes
    {scotland[(SECOND, 2024)]:,} and {scotland[(SECOND, 2025)]:,}, empty properties
    {scotland[(EMPTY_6M, 2024)]:,} and {scotland[(EMPTY_6M, 2025)]:,}, long-term empty
    {scotland[(LTE, 2024)]:,} and {scotland[(LTE, 2025)]:,} (2024 and 2025). {facts}
    facts.
    """
    return render(header, payload)


BUILDERS = {PACKAGE_DIRECTORY: build}


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
            write(directory, text)
    for directory in stale:
        print(f"stale: packages/{directory}/source_package.yaml")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
