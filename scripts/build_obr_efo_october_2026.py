#!/usr/bin/env python3
"""Author the OBR EFO October 2026 packages (PolicyEngine/chronicle#393).

Writes five source packages from the bytes their manifests pin under ``db/data/obr``,
for the Economic and fiscal outlook the OBR published with the Budget on 28 October
2026. Nothing is downloaded and no value is computed:

- ``obr-efo-receipts-october-2026``: the March 2026 package's lines, and every other
  row of the receipts workbook's tables except 4.9 and 4.19 (see RECEIPTS_LEFT_OUT);
- ``obr-efo-expenditure-october-2026``, ``obr-efo-economy-october-2026`` and
  ``obr-efo-aggregates-october-2026``: the March 2026 packages' lines, plus the
  economy's deposit rate and household financial assets;
- ``obr-efo-policy-october-2026``: Table 1.1, the costing of each policy decision.

A March 2026 line keeps its line id, its display label and its concept under the
``obr.efo_2026_10`` prefix, so a consumer changes vintage by package. Its October table
is found by title (the chapters moved: receipts tables 3.x became 4.x and expenditure
4.x became 5.x) and its row by label, and every match is asserted, so a re-run against
different bytes fails rather than drifting.

Usage::

    uv run python scripts/build_obr_efo_october_2026.py
    uv run python scripts/build_obr_efo_october_2026.py --check
"""

from __future__ import annotations

import argparse
import copy
import math
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from chronicle.sources.cells import SourceArtifactMetadata, source_cells_from_xlsx

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages/obr"
DATA = ROOT / "db/data/obr"
OCTOBER = "obr.efo_2026_10"
MARCH = "obr.efo_2026_03"
EFO_PAGE = "https://obr.uk/efo/economic-and-fiscal-outlook-october-2026/"
FY = re.compile(r"^(\d{4})-(\d{2})$")
LINE_YEAR = re.compile(r"\.(fy|cy)\d{4}$")
UK = {
    "geography_id": "K02000001",
    "geography_level": "country",
    "geography_name": "United Kingdom",
    "geography_vintage": "current",
}
# A year column's band text, as the tables print it, and the assertion it gives.
BAND_ASSERTIONS = {
    "Outturn": "observation",
    "Estimated Outurn": "observation",
    "Estimate": "observation",
    "Forecast": "source_projection",
}
RECEIPTS = ("person", "resident_population", "public_sector_finances")


def download_url(kind: str) -> str:
    return (
        "https://obr.uk/download/october-2026-economic-and-fiscal-outlook-"
        f"detailed-forecast-tables-{kind}/"
    )


def fy_label(opening: int) -> str:
    return f"{opening}-{(opening + 1) % 100:02d}"


def column_number(letters: str) -> int:
    number = 0
    for char in letters:
        number = number * 26 + ord(char) - 64
    return number


def collapse(text: object) -> str:
    return " ".join(str(text).split())


def slug(label: str) -> str:
    """'Other HMRC taxes1' -> other_hmrc_taxes; a footnote digit after a word goes."""
    text = re.sub(r"(?<=[A-Za-z)])\d+$", "", collapse(label))
    text = text.replace("&", " and ").replace("£", " gbp ")
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# ---------------------------------------------------------------- workbooks


def load_grids(path: Path) -> dict[str, dict[tuple[int, str], object]]:
    """Sheet -> (row, column letters) -> raw value, from Chronicle's own xlsx parse."""
    meta = SourceArtifactMetadata(
        source_name="obr",
        source_table=path.name,
        source_file=path.name,
        url=None,
        vintage="x",
        sha256="0",
        size_bytes=0,
        extracted_at="x",
        extraction_method="x",
    )
    grids: dict[str, dict[tuple[int, str], object]] = {}
    for cell in source_cells_from_xlsx(path.read_bytes(), meta):
        if cell.raw_value in (None, ""):
            continue
        column = re.match(r"[A-Z]+", cell.address).group(0)
        grids.setdefault(cell.sheet_name, {})[(cell.row_number, column)] = cell.raw_value
    return grids


def october_workbook(kind: str) -> dict[str, dict]:
    directory = DATA / f"efo_{kind}_october_2026"
    manifest = yaml.safe_load((directory / "manifest.yaml").read_text(encoding="utf-8"))
    entry = manifest["files"][2026]
    path = directory / entry["filename"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == entry["sha256"], (path, digest)
    return load_grids(path)


def march_workbook(kind: str) -> dict[str, dict]:
    return load_grids(DATA / f"efo_{kind}_march_2026" / f"efo_{kind}.xlsx")


def title_key(title: object) -> str:
    """'4.8 Current receipts (on a cash basis)' -> 'Current receipts (on a cash basis)'."""
    return re.sub(r"^\s*\d+\.\d+[a-z]?\s*", "", collapse(title))


def sheet_title(grid: dict) -> str:
    title = grid.get((2, "B"))
    assert isinstance(title, str), title
    return title


def fiscal_columns(grid: dict, header_row: int) -> list[tuple[int, str]]:
    found = sorted(
        (column_number(column), column, value.strip())
        for (row, column), value in grid.items()
        if row == header_row and isinstance(value, str) and FY.match(value.strip())
    )
    columns = []
    for _, column, label in found:
        opening = int(label[:4])
        assert label == fy_label(opening), (header_row, column, label)
        columns.append((opening, column))
    years = [opening for opening, _ in columns]
    assert years and years == list(range(years[0], years[0] + len(years))), years
    return columns


def bands(grid: dict, band_row: int | None, columns: list[tuple[int, str]]) -> dict:
    """Each year column's band text ('Outturn', 'Forecast', ...); 'Forecast' if none."""
    if band_row is None:
        return {column: "Forecast" for _, column in columns}
    status = {}
    current = None
    for _, column in columns:
        text = grid.get((band_row, column))
        if isinstance(text, str):
            current = collapse(text)
        assert current in BAND_ASSERTIONS, (band_row, column, current)
        status[column] = current
    return status


def header_row_above(grid: dict, row: int) -> int:
    """The nearest fiscal-year header row above a data row."""
    candidates = [
        r
        for (r, column), value in grid.items()
        if r < row and isinstance(value, str) and FY.match(value.strip())
    ]
    assert candidates, row
    return max(candidates)


def band_row_for(grid: dict, header_row: int) -> int | None:
    row = header_row - 1
    texts = [
        collapse(value)
        for (r, _), value in grid.items()
        if r == row and isinstance(value, str)
    ]
    return row if texts and all(text in BAND_ASSERTIONS for text in texts) else None


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def fiscal_coverage(opening: int, basis: str | None = None) -> dict:
    coverage = {
        "start_date": f"{opening}-04-01",
        "end_date": f"{opening + 1}-03-31",
        "basis": "fiscal",
        "source_period_label": fy_label(opening),
    }
    if basis is not None:
        coverage["accounting_basis"] = basis
    return coverage


def record_ids(kind: str, line_id: str, prefix: str, year: int) -> dict:
    record_set_id = f"{OCTOBER}.{kind}.{line_id}.{prefix}{year}"
    return {
        "record_set_id": record_set_id,
        "record_set_spec_id": f"{record_set_id}.v1",
        "source_record_id_prefix": record_set_id,
    }


# ------------------------------------------------------------ March lines

# October labels that differ from March's for the same line.
RENAMED = {
    ("expenditure", "council_tax_england"): (
        "England council tax receipts",
        "England council tax receipts1",
    ),
    ("expenditure", "council_tax_total"): (
        "Total net council tax receipts1",
        "Total net council tax receipts2",
    ),
}

DWP_GB = (
    "Geography: a DWP line, as in the March 2026 package: DWP's benefit expenditure "
    "and caseload tables (Spring 2026, Notes 1 and 3; package "
    "dwp-benefit-expenditure-caseload-spring-2026) give these lines for Great Britain, "
    "or people resident overseas receiving United Kingdom benefits; Northern Ireland's "
    "social security is on rows of its own."
)


def devolved_out(benefit: str, date: str) -> str:
    return (
        "Geography: England and Wales, with people resident overseas, as in the March "
        "2026 package: DWP's tables (Spring 2026, Notes 3 and 4) leave Scottish "
        f"{benefit} cases out from {date}, when executive competence moved to the "
        "Scottish Government."
    )


ACCRUAL_4_10 = (
    "Table 4.10 states no basis; row 6 equals table 4.1's accrued 'Betting and gaming "
    "taxes' row (row 7) in every year table 4.10 covers, so the line is stamped accrual."
)
OF_WHICH_4_10 = "An 'of which' of row 6; the seven duties sum to it. " + ACCRUAL_4_10
SDLT = (
    "The EFO publishes no split of SDLT by type of buyer (chronicle#357 item 2); SDLT "
    "applies in England and Northern Ireland, and the line is stamped United Kingdom "
    "like the rest of this package's receipts."
)
WINE = "Footnote 1: includes other fermented products such as fruit ciders."
SPIRITS = "Footnote 2: includes spirit-based ‘ready-to-drinks’ such as alcopops."
MARCH_LINE_NOTES = {
    "receipts": {
        "tobacco_duties": "Cash basis (table title and note).",
        "spirits_duties": "Cash basis (table title and note).",
        "wine_duties": "Cash basis (table title and note).",
        "beer_and_cider_duties": "Cash basis (table title and note).",
        "betting_and_gaming_duties": "Cash basis (table title and note).",
        "vaping_tax": (
            "Cash basis (table title and note). The tax is zero in the years before it "
            "starts, as published."
        ),
        "betting_and_gaming_duties_accrued": (
            "Table 4.10 states no basis; this row equals table 4.1's accrued 'Betting "
            "and gaming taxes' row (row 7) in every year table 4.10 covers, not table "
            "4.8's cash row 36, so it is stamped accrual. Table 4.10 now starts in "
            "2026-27, its first forecast year."
        ),
        "remote_gaming_duty": OF_WHICH_4_10,
        "lottery_duty": OF_WHICH_4_10,
        "general_betting_duty": OF_WHICH_4_10,
        "machine_games_duty": OF_WHICH_4_10,
        "gaming_duty": OF_WHICH_4_10,
        "bingo_duty": OF_WHICH_4_10
        + " Bingo duty is abolished from 1 April 2026; the table's near-zero values are "
        "kept as published.",
        "pool_betting_duty": OF_WHICH_4_10,
        "cigarette_clearances": "Million sticks, as the row label states.",
        "non_cigarette_tobacco_clearances": (
            "Thousand kilograms, as the row label states; rows 8 and 9 sum to it."
        ),
        "hand_rolled_tobacco_clearances": (
            "An 'of which' of row 6 (\"Non-cigarette clearances ('000s kg)\"), in its "
            "unit; rows 8 and 9 sum to it."
        ),
        "other_tobacco_products_clearances": (
            "An 'of which' of row 6 (\"Non-cigarette clearances ('000s kg)\"), in its "
            "unit; rows 8 and 9 sum to it."
        ),
        "wine_clearances": WINE,
        "spirits_clearances": SPIRITS,
        "beer_and_cider_duties_accrued": "Accrued basis (the table's note).",
        "wine_duties_accrued": "Accrued basis (the table's note). " + WINE,
        "spirits_duties_accrued": "Accrued basis (the table's note). " + SPIRITS,
        "sdlt_residential": "SDLT on residential property, all buyers. " + SDLT,
        "sdlt_residential_main_rates": (
            "Residential SDLT at the main rates, an 'of which' of row 8. " + SDLT
        ),
        "sdlt_residential_higher_rates_additional_dwellings": (
            "Residential SDLT from the higher rates on additional dwellings, an 'of "
            "which' of row 8; it matches HMRC's net surcharge (Annual Stamp Tax "
            "Statistics Table 2f), not the gross surcharge element of Table 6b. " + SDLT
        ),
        "sdlt_residential_non_uk_resident_surcharge": (
            "Residential SDLT from the non-UK resident surcharge, an 'of which' of row "
            "8. " + SDLT
        ),
        "sdlt_non_residential": "SDLT on non-residential property, all buyers. " + SDLT,
    },
    "expenditure": {
        "council_tax_england": (
            "Footnote 1, new in October: outturn reflects the latest MHCLG pre-measures "
            "data and does not align with the public sector finances data used "
            "elsewhere in the forecast."
        ),
        "domestic_rates": (
            "The OBR also shows Northern Ireland domestic rates in receipts table 4.2, "
            "row 6 ('Northern Ireland domestic rates', package "
            "obr-efo-receipts-october-2026), with different values; both are carried as "
            "published, and the OBR calls neither one regional or district."
        ),
        "council_tax_total": (
            "Footnote 2: the table breaks down the council tax receipts line of Table "
            "A.5 of the October 2026 EFO."
        ),
        "housing_benefit": DWP_GB,
        "incapacity_benefits": DWP_GB
        + " The line includes Severe Disablement Allowance, which DWP gives for England "
        "and Wales only from 1 April 2020 (Notes 4).",
        "pension_credit": DWP_GB,
        "statutory_maternity_pay": DWP_GB,
        "universal_credit_in_cap": DWP_GB,
        "state_pension": DWP_GB,
        "jobseekers_allowance": DWP_GB,
        "universal_credit_outside_cap": DWP_GB,
        "dla_and_pip": devolved_out(
            "Disability Living Allowance and Personal Independence Payment",
            "1 April 2020",
        ),
        "attendance_allowance": devolved_out("Attendance Allowance", "1 April 2020"),
        "carers_allowance": devolved_out("Carer's Allowance", "3 September 2018"),
        "winter_fuel_payment": (
            "Geography: England and Wales, with people resident overseas, as in the "
            "March 2026 package: DWP's tables (Spring 2026, Notes 3 and 4) leave "
            "Scottish Winter Fuel Payment cases out from April 2024, when the payment "
            "was devolved."
        ),
        "ni_social_security_in_welfare_cap": (
            "Geography: Northern Ireland. The Northern Ireland Executive is responsible "
            "for social security expenditure on residents of Northern Ireland (DWP "
            "benefit expenditure and caseload tables, Spring 2026, Notes 3); the table "
            "gives it on its own rows beside the DWP lines."
        ),
        "ni_social_security_outside_welfare_cap": (
            "Geography: Northern Ireland. The Northern Ireland Executive is responsible "
            "for social security expenditure on residents of Northern Ireland (DWP "
            "benefit expenditure and caseload tables, Spring 2026, Notes 3); the table "
            "gives it on its own rows beside the DWP lines."
        ),
    },
}

ECONOMY_OUTTURN_NOTE = (
    "Calendar 2025 is stamped outturn and 2026 onwards forecast: the EFO's foreword says "
    "the current fiscal year, 2026-27, is presented as an OBR forecast because its "
    "outturn is incomplete, and the workbook marks no forecast start on the tables."
)


@dataclass
class MarchLine:
    line_id: str
    template: dict
    march_sheet: str
    march_row: int
    march_label: object
    header_column: str


def march_lines(kind: str) -> list[MarchLine]:
    path = PACKAGES / f"efo_{kind}_march_2026" / "source_package.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    lines: dict[str, MarchLine] = {}
    for record_set in payload["record_sets"]:
        line_id = LINE_YEAR.sub("", record_set["record_set_id"]).removeprefix(
            f"{MARCH}.{kind}."
        )
        if line_id in lines:
            continue
        (row,) = record_set["rows"]
        lines[line_id] = MarchLine(
            line_id=line_id,
            template=record_set,
            march_sheet=record_set["sheet_name"],
            march_row=row["row_number"],
            march_label=row["expected_row_header"],
            header_column=row.get("expected_row_header_column", "B"),
        )
    return list(lines.values())


def october_sheet_for(march_grid: dict, october_by_title: dict) -> str:
    key = title_key(sheet_title(march_grid))
    assert key in october_by_title, key
    return october_by_title[key]


def nearest_row(grid: dict, column: str, label: object, march_row: int) -> int:
    rows = sorted(
        (abs(row - march_row), row)
        for (row, col), value in grid.items()
        if col == column and value == label
    )
    assert rows, (column, label)
    assert len(rows) == 1 or rows[0][0] < rows[1][0], (column, label, rows)
    return rows[0][1]


def move_guards(row_entry: dict, october_grid: dict) -> None:
    """Re-point each guard cell (a title or a note) at the same text in October."""
    guards = []
    for guard in row_entry.get("guard_cells", []):
        if guard["row"] == 2 and guard["column"] == "B":
            text = sheet_title(october_grid)
            assert title_key(text) == title_key(guard["expected_value"]), (guard, text)
            guards.append({**guard, "expected_value": text})
            continue
        if title_key(guard["expected_value"]) != collapse(guard["expected_value"]):
            # A block title such as '3.12 Alcohol receipts forecasts'.
            wanted = title_key(guard["expected_value"])
            matches = [
                (row, value)
                for (row, column), value in october_grid.items()
                if column == guard["column"]
                and isinstance(value, str)
                and title_key(value) == wanted
            ]
        else:
            matches = [
                (row, value)
                for (row, column), value in october_grid.items()
                if column == guard["column"] and value == guard["expected_value"]
            ]
        assert len(matches) == 1, (guard, matches)
        row, value = matches[0]
        guards.append({**guard, "row": row, "expected_value": value})
    if guards:
        row_entry["guard_cells"] = guards


def base_note(sheet: str, row: int, label: object, unit_text: str) -> str:
    return (
        f"OBR EFO October 2026 detailed forecast tables, table {sheet}, row {row} "
        f"('{collapse(label)}'), {unit_text}."
    )


UNIT_TEXT = {
    ("gbp", 1000000000): "GBP billion",
    ("stick", 1000000): "million sticks",
    ("kilogram", 1000): "thousand kilograms",
    ("litre_of_pure_alcohol", 100000): "thousand hectolitres of alcohol",
    ("percent_of_gdp", None): "per cent of GDP",
}


def port_fiscal_line(kind: str, line: MarchLine, grid: dict, sheet: str) -> list[dict]:
    """One October record set per year column for a row-labelled March line."""
    march_label, october_label = RENAMED.get((kind, line.line_id), (None, None))
    if march_label is not None:
        assert line.march_label == march_label, (line.line_id, line.march_label)
    label = october_label or line.march_label
    row = nearest_row(grid, line.header_column, label, line.march_row)
    header_row = header_row_above(grid, row)
    columns = fiscal_columns(grid, header_row)
    band = bands(grid, band_row_for(grid, header_row), columns)
    measure_template = line.template["measures"][0]
    unit_text = UNIT_TEXT[(measure_template["unit"], measure_template.get("value_scale"))]
    notes = base_note(sheet, row, label, unit_text)
    extra = MARCH_LINE_NOTES.get(kind, {}).get(line.line_id)
    if extra:
        notes += " " + extra
    record_sets = []
    for opening, column in columns:
        value = grid.get((row, column))
        if value is None:
            continue
        assert is_number(value), (sheet, row, column, value)
        record_set = copy.deepcopy(line.template)
        record_set.update(record_ids(kind, line.line_id, "fy", opening))
        record_set["assertion"] = BAND_ASSERTIONS[band[column]]
        record_set["sheet_name"] = sheet
        record_set["period"] = opening
        if "period_coverage" in record_set:
            record_set["period_coverage"] = fiscal_coverage(
                opening, record_set["period_coverage"].get("accounting_basis")
            )
        (row_entry,) = record_set["rows"]
        row_entry["row_number"] = row
        row_entry["expected_row_header"] = label
        move_guards(row_entry, grid)
        (measure,) = record_set["measures"]
        display = row_entry["label"]
        basis = record_set.get("shared_filters", {}).get("accounting_basis")
        if basis is not None:
            display += ", accrued basis" if basis == "accrual" else ", cash basis"
        measure.update(
            {
                "label": f"{display}, FY{fy_label(opening)}",
                "column": column,
                "expected_column_header_row": header_row,
                "expected_column_header": fy_label(opening),
                "concept_evidence_url": download_url(kind),
                "concept_evidence_notes": notes,
            }
        )
        record_sets.append(record_set)
    assert record_sets, line.line_id
    return record_sets


def port_economy_line(line: MarchLine, march_grid: dict, grid: dict, sheet: str) -> list[dict]:
    """Economy tables run years down column B and variables across; the March line's
    column must carry the same header in October."""
    (measure_template,) = line.template["measures"]
    column = measure_template["column"]
    for header_row in (3, 4):
        assert march_grid.get((header_row, column)) == grid.get((header_row, column)), (
            sheet,
            column,
            header_row,
        )
    unit_text = {
        ("gbp", 1000000000): "GBP billion",
        ("count", 1000000): "millions of people",
        ("percent", None): "per cent",
    }[(measure_template["unit"], measure_template.get("value_scale"))]
    record_sets = []
    for year in range(2025, 2032):
        (row,) = [r for (r, col), value in grid.items() if col == "B" and value == year]
        value = grid.get((row, column))
        assert is_number(value), (sheet, row, column, value)
        record_set = copy.deepcopy(line.template)
        record_set.update(record_ids("economy", line.line_id, "cy", year))
        record_set["assertion"] = "observation" if year <= 2025 else "source_projection"
        record_set["sheet_name"] = sheet
        record_set["period"] = year
        (row_entry,) = record_set["rows"]
        row_entry["row_number"] = row
        row_entry["expected_row_header"] = year
        move_guards(row_entry, grid)
        (measure,) = record_set["measures"]
        measure.update(
            {
                "label": f"{row_entry['label']}, {year}",
                "concept_evidence_url": download_url("economy"),
                "concept_evidence_notes": (
                    f"OBR EFO October 2026 detailed forecast tables, table {sheet} "
                    f"('{title_key(sheet_title(grid))}'), column {column}, calendar-year "
                    f"row; {unit_text}. {ECONOMY_OUTTURN_NOTE}"
                ),
            }
        )
        record_sets.append(record_set)
    return record_sets


def port_march_package(kind: str, grids: dict) -> tuple[list[dict], set, list[str]]:
    """The March package's lines in October, the October cells they use, and the
    changes against March for the package notes."""
    march_grids = march_workbook(kind)
    by_title = {
        title_key(sheet_title(grid)): sheet
        for sheet, grid in grids.items()
        if isinstance(grid.get((2, "B")), str) and re.match(r"\s*\d", grid[(2, "B")])
    }
    record_sets: list[dict] = []
    used: set[tuple[str, int]] = set()
    changes: list[str] = []
    for line in march_lines(kind):
        march_grid = march_grids[line.march_sheet]
        sheet = october_sheet_for(march_grid, by_title)
        grid = grids[sheet]
        if kind == "economy":
            record_sets += port_economy_line(line, march_grid, grid, sheet)
            continue
        ported = port_fiscal_line(kind, line, grid, sheet)
        row = ported[0]["rows"][0]["row_number"]
        used.add((sheet, row))
        record_sets += ported
        if (kind, line.line_id) in RENAMED:
            march_label, october_label = RENAMED[(kind, line.line_id)]
            changes.append(
                f"{line.line_id}: row label '{march_label}' (March table "
                f"{line.march_sheet}) is now '{october_label}' (table {sheet})"
            )
    return record_sets, used, changes


# ------------------------------------------------- the rest of the receipts


@dataclass(frozen=True)
class RowUnit:
    unit: str
    scale: int | None
    unit_text: str
    measure_id: str
    aggregation: str


GBP_BN = RowUnit("gbp", 1000000000, "GBP billion", "amount", "sum")
GBP_M = RowUnit("gbp", 1000000, "GBP million", "amount", "sum")


@dataclass(frozen=True)
class Table:
    """A receipts table's rows beyond the March lines, as the table prints them."""

    sheet: str
    key: str
    unit_cell: tuple[int, str, str] | None
    unit: RowUnit | None
    entity: tuple[str, str, str]
    basis: str | None = None
    basis_guard: tuple[int, str, str] | None = None
    basis_before_row: int | None = None
    period: str = "fiscal_year"
    calendar_header_row: int | None = None
    note: str = ""
    left_out: dict = field(default_factory=dict)
    left_out_from_year: dict = field(default_factory=dict)
    row_units: dict = field(default_factory=dict)
    row_prefix: dict = field(default_factory=dict)
    calendar_rows: dict = field(default_factory=dict)


TAXPAYERS = ("person", "taxpayer", "public_sector_finances")
CASH_NOTE_4_8 = (
    "Note: All tax lines prior to accruals adjustments on tax line are on a cash basis "
    "rather than an accrued basis."
)
RECEIPTS_TABLES = (
    Table(
        "4.1",
        "other_hmrc_taxes",
        (3, "C", "£ billion"),
        GBP_BN,
        RECEIPTS,
        "accrual",
        (17, "B", "Note: All taxes are on an accrued basis."),
        left_out_from_year={
            7: (
                2026,
                "From 2026-27 the row restates table 4.10's accrued total (line "
                "betting_and_gaming_duties_accrued), so only 2025-26, which table 4.10 "
                "does not print, is kept.",
            ),
        },
    ),
    Table("4.2", "other_taxes", (3, "C", "£ billion"), GBP_BN, RECEIPTS),
    Table("4.3", "other_receipts", (3, "C", "£ billion"), GBP_BN, RECEIPTS),
    Table("4.4", "income_tax_and_nics", (3, "C", "£ billion"), GBP_BN, RECEIPTS),
    Table(
        "4.5",
        "self_employed_income_growth",
        (3, "C", "Percentage change on a year earlier"),
        RowUnit("percent", None, "percentage change on a year earlier", "growth_rate", "rate"),
        ("person", "self_assessment_taxpayer", "public_sector_finances"),
        note=(
            "Every column, 2024-25 included, sits under the table's 'Forecast' band, so "
            "every fact is a source_projection; the table starts in 2024-25."
        ),
    ),
    Table("4.6", "onshore_corporation_tax", (3, "C", "£ billion"), GBP_BN, RECEIPTS),
    Table(
        "4.7",
        "property_transaction_taxes",
        (3, "C", "£ billion"),
        GBP_BN,
        RECEIPTS,
        left_out={
            6: "'Total SDLT' restates table 4.8's 'Stamp duty land tax' line (row 24)",
            14: "'Annual tax on enveloped dwellings (ATED)' restates table 4.8's row 25",
        },
    ),
    Table("4.8", "cash_receipts", (3, "D", "£ billion"), GBP_BN, RECEIPTS, "cash",
          (66, "B", CASH_NOTE_4_8), basis_before_row=57),
    Table(
        "4.13",
        "inheritance_tax",
        None,
        None,
        ("person", "deceased_person", "public_sector_finances"),
        row_units={
            5: RowUnit("percent", None, "per cent", "share", "share"),
            6: RowUnit("count", 1000, "thousands of deaths", "count", "sum"),
            7: RowUnit("count", 1000, "thousands of deaths", "count", "sum"),
            8: RowUnit("gbp", 1000, "GBP thousand", "mean_amount", "mean"),
        },
        note="The table states each row's unit in its label.",
    ),
    Table(
        "4.14",
        "oil_and_gas_expenditure",
        (3, "C", "£ billion"),
        GBP_BN,
        ("institutional_sector", "oil_and_gas_industry", "public_sector_finances"),
        period="calendar_year",
        calendar_header_row=5,
    ),
    Table(
        "4.15",
        "vat_gap_and_standard_rated_share",
        (3, "C", "Per cent"),
        RowUnit("percent", None, "per cent", "share", "share"),
        RECEIPTS,
        calendar_rows={8: 7},
    ),
    Table("4.16", "corporation_tax_credits", (3, "C", "£ billion"), GBP_BN,
          ("firm", "corporation_tax_payer", "public_sector_finances")),
    Table(
        "4.17",
        "personal_tax_measures_yield",
        (3, "C", "£ billion"),
        GBP_BN,
        RECEIPTS,
        note=(
            "The table flags no outturn: every column, past years included, is the "
            "OBR's latest estimate of the measures' yield, so every fact is a "
            "source_projection."
        ),
    ),
    Table(
        "4.18",
        "threshold_freezes",
        (3, "C", "Million"),
        RowUnit("count", 1000000, "millions of taxpayers", "count", "sum"),
        TAXPAYERS,
        row_prefix={
            7: "taxpayers", 8: "taxpayers", 9: "taxpayers",
            11: "higher_rate_taxpayers", 12: "higher_rate_taxpayers",
            13: "higher_rate_taxpayers",
            15: "additional_rate_taxpayers", 16: "additional_rate_taxpayers",
            17: "additional_rate_taxpayers",
        },
    ),
    Table("4.20", "environmental_levies", (3, "C", "£ billion"), GBP_BN, RECEIPTS),
    Table(
        "4.21",
        "contracts_for_difference_drivers",
        None,
        None,
        ("institutional_sector", "electricity_generators", "public_sector_finances"),
        row_units={
            5: RowUnit("gbp_per_mwh", None, "GBP per MWh", "price", "mean"),
            6: RowUnit("gbp_per_mwh", None, "GBP per MWh", "price", "mean"),
            7: RowUnit("gbp_per_mwh", None, "GBP per MWh", "price", "mean"),
            8: RowUnit("kwh", 1000000000, "TWh", "generation", "sum"),
            9: GBP_M,
            10: GBP_M,
            11: GBP_M,
        },
        note="The table states each row's unit in its label.",
        left_out={
            11: (
                "'(c * d + e + f) Forecast (£ million)' restates table 4.20's 'Contracts "
                "for difference' line (row 7), in GBP million"
            ),
        },
    ),
    Table(
        "4.22",
        "fiscally_neutral_receipts",
        (3, "C", "£ million"),
        GBP_BN,
        RECEIPTS,
        note=(
            "The unit cell says '£ million', but the cells are GBP billion: 'VAT "
            "refunds' (row 17) equals table 4.8's 'VAT refunds' (row 55, £ billion) in "
            "every year this table covers, and 'Council tax' is about £54 billion; so "
            "value_scale is 1e9, with the cell kept as a guard."
        ),
        left_out={
            10: "'Contracts for difference' restates table 4.20's row 7",
            11: "'Renewables obligation' restates table 4.20's row 6",
            12: "'Capacity markets' restates table 4.20's 'Capacity market1' (row 8)",
            13: "'Green gas levy' restates table 4.20's row 9",
            14: "'Warm homes discount' restates table 4.20's 'Warm home discount' (row 10)",
            17: "'VAT refunds' restates table 4.8's row 55",
            18: (
                "'Extended producer responsibility' restates table 4.2's 'Extended "
                "producer responsibility Fees' (row 25)"
            ),
            19: "'Community infrastructure levy' restates table 4.2's row 13",
        },
    ),
)
# Taxes table 4.1 prints on an accrued basis and table 4.8 on a cash basis. Each pair
# shares one concept, with the basis as a constraint, as chronicle#381's excise duties
# do; the source concepts stay the tables' own. (sheet, row) -> (label, concept).
SHARED_TAX_CONCEPTS = {
    ("4.1", 6): ("Customs duties", "obr.customs_duties"),
    ("4.8", 37): ("Customs Duties", "obr.customs_duties"),
    ("4.1", 7): ("Betting and gaming taxes", "obr.betting_and_gaming_duties"),
    ("4.1", 8): ("Landfill tax", "obr.landfill_tax"),
    ("4.8", 34): ("Landfill tax", "obr.landfill_tax"),
    ("4.1", 9): ("Aggregates levy", "obr.aggregates_levy"),
    ("4.8", 35): ("Aggregates levy", "obr.aggregates_levy"),
    ("4.1", 10): ("Soft drink industry levy", "obr.soft_drinks_industry_levy"),
    ("4.8", 43): ("Soft drinks industry levy", "obr.soft_drinks_industry_levy"),
    ("4.1", 11): ("Diverted profits tax", "obr.diverted_profits_tax"),
    ("4.8", 41): ("Diverted profits tax", "obr.diverted_profits_tax"),
    ("4.1", 12): ("Plastic packaging tax", "obr.plastic_packaging_tax"),
    ("4.8", 44): ("Plastic Packaging tax ", "obr.plastic_packaging_tax"),
    ("4.1", 13): ("Residential property developer tax", "obr.residential_property_developer_tax"),
    ("4.8", 45): ("Residential property developer tax", "obr.residential_property_developer_tax"),
    ("4.1", 14): ("Carbon border adjustment mechanism", "obr.carbon_border_adjustment_mechanism"),
    ("4.8", 49): ("Carbon border adjustment mechanism", "obr.carbon_border_adjustment_mechanism"),
    ("4.1", 15): ("Vaping tax", "obr.vaping_tax"),
}
SHARED_TAX_NOTE = (
    "Tables 4.1 (accrued) and 4.8 (cash) both print this tax, so the two lines share "
    "this concept and differ in accounting_basis, as chronicle#381's excise duties do"
)
MARCH_LINE_PAIRS = {
    ("4.1", 7): "betting_and_gaming_duties",
    ("4.1", 15): "vaping_tax",
}
# Whole tables of the receipts workbook left out, and why.
RECEIPTS_LEFT_OUT = {
    "4.9": (
        "'APD forecast - projection of passenger numbers by band' states no unit for "
        "its passenger numbers"
    ),
    "4.19": (
        "'Counterfactual and actual personal tax thresholds' prints '£ billion' over "
        "thresholds in pounds (a personal allowance of 12,570) and flags no outturn; "
        "its actual thresholds are legislation and the others are counterfactuals"
    ),
}


def table_notes(grid: dict, first_row: int) -> tuple[list[str], dict[str, str]]:
    """A table's 'Note:' and 'Source:' lines and its numbered footnotes, below its rows."""
    notes, footnotes = [], {}
    for (row, column), value in sorted(grid.items()):
        if row < first_row or column != "B" or not isinstance(value, str):
            continue
        text = collapse(value)
        if text.startswith(("Note:", "Source:")):
            notes.append(text)
        match = re.match(r"^(\d+) (.+)$", text)
        if match:
            footnotes[match.group(1)] = match.group(2)
    return notes, footnotes


def footnote_for(label: str, footnotes: dict[str, str]) -> str:
    match = re.search(r"(?<=[A-Za-z)])(\d+)$", collapse(label))
    if not match or match.group(1) not in footnotes:
        return ""
    return f" Footnote {match.group(1)}: {footnotes[match.group(1)]}"


def check_restatements(grids: dict) -> None:
    """The rows left out restate rows kept; the evidence the notes cite holds."""
    cash, sdlt = grids["4.8"], grids["4.7"]
    for left_row, kept_row in ((6, 24), (14, 25)):
        for index in range(7):
            left = sdlt.get((left_row, "CDEFGHI"[index]))
            kept = cash.get((kept_row, "DEFGHIJ"[index]))
            assert is_number(left) and left == kept, (left_row, kept_row, left, kept)
    accrued, breakdown = grids["4.1"], grids["4.10"]
    assert breakdown[(5, "C")] == "2026-27" and accrued[(5, "D")] == "2026-27"
    assert accrued[(7, "B")] == "Betting and gaming taxes"
    for index in range(6):
        assert breakdown[(6, "CDEFGH"[index])] == accrued[(7, "DEFGHI"[index])], index
    neutral = grids["4.22"]
    assert neutral[(17, "B")] == "VAT refunds" and cash[(55, "B")] == "VAT refunds"
    for index in range(6):
        assert neutral[(17, "CDEFGH"[index])] == cash[(55, "EFGHIJ"[index])], index
    # Tables 4.22 and 4.21 restate tables 4.20 and 4.2 for 2026-27 to 2031-32.
    levies, other = grids["4.20"], grids["4.2"]
    drivers = grids["4.21"]
    assert neutral[(5, "C")] == drivers[(4, "C")] == "2026-27"
    assert levies[(5, "D")] == other[(5, "D")] == "2026-27"
    for left_row, kept, kept_row in (
        (10, levies, 7),
        (11, levies, 6),
        (12, levies, 8),
        (13, levies, 9),
        (14, levies, 10),
        (18, other, 25),
        (19, other, 13),
    ):
        for index in range(6):
            # Equal to the last binary digit or two: 4.22's CfD row differs by 1e-16.
            left = neutral.get((left_row, "CDEFGH"[index]))
            kept_value = kept[(kept_row, "DEFGHI"[index])]
            assert is_number(left) and math.isclose(left, kept_value, rel_tol=1e-12), (
                left_row,
                kept_row,
                index,
            )
    assert collapse(drivers[(11, "B")]) == "(c * d + e + f) Forecast (£ million)"
    assert levies[(7, "B")] == "Contracts for difference"
    for index in range(6):
        left = drivers[(11, "CDEFGH"[index])]
        assert math.isclose(left, levies[(7, "DEFGHI"[index])] * 1000, rel_tol=1e-9), index


def row_label(grid: dict, row: int) -> tuple[str, str] | None:
    """The row's label and its column: B, or C for the sub-rows of an 'of which'."""
    for column in ("B", "C"):
        value = grid.get((row, column))
        if isinstance(value, str) and value.strip():
            return column, value
    return None


def receipts_rows(table: Table, grid: dict, used_rows: set[int]) -> list[dict]:
    title = sheet_title(grid)
    if table.unit_cell is not None:
        row, column, text = table.unit_cell
        assert grid.get((row, column)) == text, (table.sheet, grid.get((row, column)))
    if table.basis_guard is not None:
        row, column, text = table.basis_guard
        assert grid.get((row, column)) == text, (table.sheet, grid.get((row, column)))
    if table.period == "calendar_year":
        header_row = table.calendar_header_row
        found = sorted(
            (column_number(c), c, v)
            for (r, c), v in grid.items()
            if r == header_row and is_number(v)
        )
        year_columns = [(int(value), column) for _, column, value in found]
        band = bands(grid, header_row - 1, year_columns)
    else:
        header_row = min(
            r for (r, c), v in grid.items() if isinstance(v, str) and FY.match(v.strip())
        )
        year_columns = fiscal_columns(grid, header_row)
        band = bands(grid, band_row_for(grid, header_row), year_columns)
    last_row = max(r for r, _ in grid)
    notes, footnotes = table_notes(grid, header_row + 1)
    record_sets = []
    parent = None
    for row in range(header_row + 1, last_row + 1):
        found = row_label(grid, row)
        if found is None:
            continue
        column, label = found
        if column == "B" and collapse(label).lower().startswith(("of which", "note:", "source:")):
            continue
        values = [(o, c, grid.get((row, c))) for o, c in year_columns]
        numbers = [v for _, _, v in values if is_number(v)]
        if not numbers:
            if column == "B" and not re.match(r"^\d+ ", collapse(label)):
                parent = label if row not in table.row_prefix else parent
            continue
        if column == "B":
            parent = label
        if row in used_rows or row in table.left_out:
            continue
        unit = table.row_units.get(row, table.unit)
        assert unit is not None, (table.sheet, row)
        key = slug(label)
        display = collapse(label)
        if column == "C":
            key = f"{slug(parent)}_{key}"
            display = f"{collapse(parent)}: {display}"
        if row in table.row_prefix:
            key = f"{table.row_prefix[row]}_{key}"
        line_id = f"{table.key}.{key}"
        concept = f"obr.{table.key}.{key}"
        canonical, relation = concept, "source_label"
        if (table.sheet, row) in SHARED_TAX_CONCEPTS:
            expected, canonical = SHARED_TAX_CONCEPTS[(table.sheet, row)]
            assert label == expected, (table.sheet, row, label)
            relation = "exact"
        basis = table.basis
        if table.basis_before_row is not None and row >= table.basis_before_row:
            basis = None
        if basis is not None:
            display += " (accrued)" if basis == "accrual" else " (cash)"
        if row in table.calendar_rows:
            calendar_header = table.calendar_rows[row]
            found_years = sorted(
                (column_number(c), c, v)
                for (r, c), v in grid.items()
                if r == calendar_header and is_number(v)
            )
            row_years = [(int(v), c) for _, c, v in found_years]
            assert [c for _, c in row_years] == [c for _, c in year_columns]
            period, prefix, row_header_row = "calendar_year", "cy", calendar_header
        elif table.period == "calendar_year":
            row_years, period, prefix, row_header_row = year_columns, "calendar_year", "cy", header_row
        else:
            row_years, period, prefix, row_header_row = year_columns, "fiscal_year", "fy", header_row
        note = base_note(table.sheet, row, label, unit.unit_text)
        if basis == "cash":
            note += " Cash basis (table title and note)."
        elif basis == "accrual":
            note += " Accrued basis (the table's note)."
        if column == "C":
            note += f" An 'of which' of '{collapse(parent)}'."
        note += footnote_for(label, footnotes)
        if relation == "exact":
            note += f" {SHARED_TAX_NOTE} ({canonical})."
            if (table.sheet, row) in MARCH_LINE_PAIRS:
                note += (
                    " Table 4.8's cash line is the March line "
                    f"{MARCH_LINE_PAIRS[(table.sheet, row)]}."
                )
        if row in table.left_out_from_year:
            note += " " + table.left_out_from_year[row][1]
        if table.note:
            note += " " + table.note
        for extra in notes:
            note += " " + extra
        guards = [{"column": "B", "row": 2, "expected_value": title, "label": "table title"}]
        if table.unit_cell is not None:
            r, c, text = table.unit_cell
            guards.append({"column": c, "row": r, "expected_value": text, "label": "unit cell"})
        if basis is not None and table.basis_guard is not None:
            r, c, text = table.basis_guard
            guards.append({"column": c, "row": r, "expected_value": text, "label": "basis note"})
        for (opening, year_column), (_, check_column) in zip(row_years, year_columns, strict=True):
            assert year_column == check_column
            value = grid.get((row, year_column))
            if value is None:
                continue
            assert is_number(value), (table.sheet, row, year_column, value)
            if row in table.left_out_from_year and opening >= table.left_out_from_year[row][0]:
                continue
            label_text = fy_label(opening) if prefix == "fy" else opening
            record_set = {
                **record_ids("receipts", line_id, prefix, opening),
                "provenance_class": "model_output",
                "assertion": BAND_ASSERTIONS[band[year_column]],
                "sheet_name": table.sheet,
                "period_type": period,
                "period": opening,
            }
            if prefix == "fy":
                record_set["period_coverage"] = fiscal_coverage(opening, basis)
            record_set.update(UK)
            entity, role, domain = table.entity
            record_set.update(
                {
                    "entity": entity,
                    "entity_role": role,
                    "domain": domain,
                    "groupby_dimension": "obr.efo_line",
                }
            )
            if basis is not None:
                record_set["shared_filters"] = {"accounting_basis": basis}
                record_set["shared_constraints"] = [
                    {
                        "variable": "accounting_basis",
                        "operator": "==",
                        "value": basis,
                        "label": "Accounting basis",
                    }
                ]
            record_set["rows"] = [
                {
                    "value_id": f"{table.key}_{key}",
                    "label": display,
                    "ordinal": 0,
                    "row_number": row,
                    "expected_row_header_column": column,
                    "expected_row_header": label,
                    "table_record_kind": "total",
                    "guard_cells": guards,
                }
            ]
            measure = {
                "measure_id": unit.measure_id,
                "label": f"{display}, " + (f"FY{label_text}" if prefix == "fy" else str(opening)),
                "ordinal": 0,
                "column": year_column,
                "source_column_id": unit.measure_id,
                "expected_column_header_row": row_header_row,
                "expected_column_header": label_text,
                "concept": canonical,
                "source_concept": concept,
                "concept_relation": relation,
                "concept_authority": "obr",
                "concept_evidence_url": download_url("receipts"),
                "concept_evidence_notes": note,
                "unit": unit.unit,
                "aggregation": unit.aggregation,
            }
            if unit.scale is not None:
                measure["value_scale"] = unit.scale
            measure["expected_cell_type"] = "number"
            record_set["measures"] = [measure]
            record_sets.append(record_set)
    return record_sets


# Receipts rows that need more than their table's notes.
RECEIPTS_ROW_NOTES = {
    ("4.2", 6): (
        "The OBR also shows Northern Ireland domestic rates in expenditure table 5.1, "
        "row 16 ('NI domestic rates', package obr-efo-expenditure-october-2026, line "
        "domestic_rates), with different values; both are carried as published, and "
        "the OBR calls neither one regional or district."
    ),
}


def receipts_package() -> tuple[list[dict], list[str]]:
    grids = october_workbook("receipts")
    check_restatements(grids)
    record_sets, used, changes = port_march_package("receipts", grids)
    covered = {table.sheet for table in RECEIPTS_TABLES} | set(RECEIPTS_LEFT_OUT)
    march_only = {"4.10", "4.11", "4.12"}
    tables = {sheet for sheet in grids if re.match(r"^4\.\d+$", sheet)}
    assert tables == covered | march_only, sorted(tables ^ (covered | march_only))
    for table in RECEIPTS_TABLES:
        rows = {row for sheet, row in used if sheet == table.sheet}
        for record_set in receipts_rows(table, grids[table.sheet], rows):
            row = record_set["rows"][0]["row_number"]
            extra = RECEIPTS_ROW_NOTES.get((table.sheet, row))
            if extra:
                record_set["measures"][0]["concept_evidence_notes"] += " " + extra
            record_sets.append(record_set)
    for sheet in march_only:
        grid = grids[sheet]
        rows = {row for s, row in used if s == sheet}
        numbered = {
            row
            for (row, column), value in grid.items()
            if is_number(value) and row_label(grid, row) is not None
            and not FY.match(str(grid.get((row, column))))
        }
        assert numbered == rows, (sheet, sorted(numbered - rows))
    return record_sets, changes


# ------------------------------------------------------- economy additions

ECONOMY_ADDITIONS = (
    # (line id, template line, table, column, header row, header text, concept, label,
    #  unit, value_scale, aggregation, note)
    (
        "deposit_rate",
        "bank_rate",
        "1.9",
        "F",
        3,
        "Deposit rate",
        "obr.deposit_rate",
        "Deposit rate, per cent",
        "percent",
        None,
        "rate",
        "per cent",
    ),
    (
        "household_financial_assets",
        "nominal_gdp_nsa",
        "1.11",
        "D",
        4,
        "Financial assets (£bn)",
        "obr.household_financial_assets",
        "Household financial assets, GBP billion",
        "gbp",
        1000000000,
        "sum",
        (
            "GBP billion, in the table's households block (row 3, 'Households'). The "
            "table defines the series as household financial assets (ONS Economic "
            "Accounts, identifier: NNML); it does not say whether a calendar-year row "
            "is the year-end or the average stock"
        ),
    ),
)


def economy_additions(grids: dict) -> list[dict]:
    templates = {line.line_id: line for line in march_lines("economy")}
    record_sets = []
    for (
        line_id, template_id, sheet, column, header_row, header, concept, label,
        unit, scale, aggregation, unit_text,
    ) in ECONOMY_ADDITIONS:
        grid = grids[sheet]
        assert grid.get((header_row, column)) == header, (sheet, column, grid.get((header_row, column)))
        if sheet == "1.11":
            assert grid.get((3, "C")) == "Households"
        template = templates[template_id].template
        for year in range(2025, 2032):
            (row,) = [r for (r, c), v in grid.items() if c == "B" and v == year]
            value = grid.get((row, column))
            assert is_number(value), (sheet, row, column, value)
            record_set = copy.deepcopy(template)
            record_set.update(record_ids("economy", line_id, "cy", year))
            record_set["assertion"] = "observation" if year <= 2025 else "source_projection"
            record_set["sheet_name"] = sheet
            record_set["period"] = year
            (row_entry,) = record_set["rows"]
            row_entry.update(
                {"value_id": line_id, "label": label, "row_number": row, "expected_row_header": year}
            )
            row_entry["guard_cells"] = [
                {"column": "B", "row": 2, "expected_value": sheet_title(grid), "label": "table title"},
                {"column": column, "row": header_row, "expected_value": header, "label": "column header"},
            ]
            measure = {
                "measure_id": line_id,
                "label": f"{label}, {year}",
                "ordinal": 0,
                "column": column,
                "source_column_id": line_id,
                "concept": concept,
                "source_concept": f"obr.efo_economy.{line_id}",
                "concept_relation": "source_label",
                "concept_authority": "obr",
                "concept_evidence_url": download_url("economy"),
                "concept_evidence_notes": (
                    f"OBR EFO October 2026 detailed forecast tables, table {sheet} "
                    f"('{title_key(sheet_title(grid))}'), column {column} ('{header}'), "
                    f"calendar-year row; {unit_text}. {ECONOMY_OUTTURN_NOTE}"
                ),
                "unit": unit,
                "aggregation": aggregation,
                "expected_cell_type": "number",
            }
            if scale is not None:
                measure["value_scale"] = scale
            record_set["measures"] = [measure]
            record_sets.append(record_set)
    return record_sets


# ------------------------------------------------------------------- policy

POLICY_TITLE = "Table 1.1: Breakdown of policy decisions since March 2026"
POLICY_NOTE = (
    "Note: This table uses the convention that a negative sign implies a loss to the "
    "Exchequer (and is therefore an increase in PSNB)."
)
POLICY_SECTIONS = {
    "Scorecard measures": "scorecard",
    "Fiscally neutral measures1": "fiscally_neutral",
    "Non-scorecard measures": "non_scorecard",
}
POLICY_ENTITY = ("government", "public_sector", "public_sector_finances")
POLICY_YEARS = "IJKLMN"


def policy_constraint(variable: str, value: str, label: str) -> dict:
    return {"variable": variable, "operator": "==", "value": value, "label": label}


def policy_package() -> tuple[list[dict], dict]:
    grid = october_workbook("policy")["1.1"]
    assert grid[(4, "C")] == POLICY_TITLE
    assert grid[(5, "I")] == "£ million" and grid[(6, "I")] == "Forecast"
    assert grid[(7, "G")] == "Head" and grid[(7, "H")] == "Category"
    columns = fiscal_columns(grid, 7)
    assert [c for _, c in columns] == list(POLICY_YEARS)
    notes, _ = table_notes({(r, "B"): v for (r, c), v in grid.items() if c == "C"}, 8)
    assert notes == [POLICY_NOTE], notes
    assert grid[(557, "C")] == "1 Includes measures with no net impact on borrowing."
    measures: list[dict] = []
    section = None
    current = None
    summary_start = None
    for row in range(8, 557):
        c_value, d_value = grid.get((row, "C")), grid.get((row, "D"))
        if c_value in POLICY_SECTIONS:
            section = POLICY_SECTIONS[c_value]
            continue
        if d_value in POLICY_SECTIONS:
            section = POLICY_SECTIONS[d_value]
            continue
        if d_value == "Total effects of receipts measures (£ millions)":
            summary_start = row
            break
        head, category = grid.get((row, "G")), grid.get((row, "H"))
        if isinstance(d_value, str) and head is not None:
            number = c_value if is_number(c_value) else None
            assert (number is not None) == (section == "scorecard"), (row, c_value)
            count = sum(1 for m in measures if m["section"] == section) + 1
            current = {
                "id": f"measure_{int(number)}" if number is not None else f"{section}_{count}",
                "number": int(number) if number is not None else None,
                "name": d_value,
                "section": section,
                "first_row": row,
                "rows": [],
            }
            measures.append(current)
        if head is None:
            assert all(grid.get((row, c)) is None for c in POLICY_YEARS), row
            continue
        assert current is not None, row
        for column in POLICY_YEARS:
            assert is_number(grid.get((row, column))), (row, column)
        current["rows"].append((row, head, category))
    assert summary_start == 490, summary_start
    assert [m["number"] for m in measures if m["section"] == "scorecard"] == list(range(1, 99))
    record_sets = []
    for measure in measures:
        keys = set()
        rows = []
        for row, head, category in measure["rows"]:
            if head == "Total":
                assert category is None, row
                key, kind, label, filters, constraints = "total", "total", "Total", {
                    "policy_head": "all",
                    "policy_category": "all",
                }, []
            else:
                key = f"{slug(head)}.{slug(category)}"
                kind, label = "detail", f"{head}: {category}"
                filters = {"policy_head": slug(head), "policy_category": slug(category)}
                constraints = [
                    policy_constraint("policy_head", slug(head), "Policy head"),
                    policy_constraint("policy_category", slug(category), "Policy category"),
                ]
            assert key not in keys, (measure["id"], key)
            keys.add(key)
            entry = {
                "value_id": key,
                "label": label,
                "ordinal": len(rows),
                "row_number": row,
                "expected_row_header_column": "G",
                "expected_row_header": head,
                "table_record_kind": kind,
                "filters": filters,
            }
            if constraints:
                entry["constraints"] = constraints
            entry["guard_cells"] = [
                {"column": "D", "row": measure["first_row"], "expected_value": measure["name"], "label": "measure"},
            ]
            if head != "Total":
                entry["guard_cells"].append(
                    {"column": "H", "row": row, "expected_value": category, "label": "category"}
                )
            rows.append(entry)
        assert rows[-1]["value_id"] == "total", measure["id"]
        number = f"measure {measure['number']} " if measure["number"] else ""
        notes = (
            f"OBR EFO October 2026 detailed forecast tables: policy, table 1.1 "
            f"('Breakdown of policy decisions since March 2026'), {number}('{measure['name']}'), "
            f"rows {measure['rows'][0][0]} to {measure['rows'][-1][0]}, GBP million. {POLICY_NOTE}"
        )
        if measure["section"] == "fiscally_neutral":
            notes += " Footnote 1 of 'Fiscally neutral measures': includes measures with no net impact on borrowing."
        if measure["section"] == "non_scorecard":
            notes += " Listed under 'Non-scorecard measures'."
        for opening, column in columns:
            record_set = {
                **record_ids("policy", measure["id"], "fy", opening),
                "provenance_class": "model_output",
                "assertion": "source_projection",
                "sheet_name": "1.1",
                "period_type": "fiscal_year",
                "period": opening,
                "period_coverage": fiscal_coverage(opening),
                **UK,
                "entity": POLICY_ENTITY[0],
                "entity_role": POLICY_ENTITY[1],
                "domain": POLICY_ENTITY[2],
                "groupby_dimension": "obr.policy_component",
                "shared_filters": {
                    "policy_section": measure["section"],
                    "policy_measure": measure["id"],
                },
                "shared_constraints": [
                    policy_constraint("policy_section", measure["section"], "Policy section"),
                    policy_constraint("policy_measure", measure["id"], "Policy measure"),
                ],
                "rows": copy.deepcopy(rows),
                "measures": [
                    {
                        "measure_id": "costing",
                        "label": f"Costing, FY{fy_label(opening)}",
                        "ordinal": 0,
                        "column": column,
                        "source_column_id": "costing",
                        "expected_column_header_row": 7,
                        "expected_column_header": fy_label(opening),
                        "concept": "obr.policy_decision_costing",
                        "source_concept": "obr.policy_decision_costing",
                        "concept_relation": "source_label",
                        "concept_authority": "obr",
                        "concept_evidence_url": download_url("policy"),
                        "concept_evidence_notes": notes,
                        "unit": "gbp",
                        "aggregation": "sum",
                        "value_scale": 1000000,
                        "expected_cell_type": "number",
                    }
                ],
            }
            record_sets.append(record_set)
    record_sets += policy_summary(grid, summary_start, columns)
    labels = {
        "policy_section": {
            "scorecard": "Scorecard measures",
            "fiscally_neutral": "Fiscally neutral measures",
            "non_scorecard": "Non-scorecard measures",
        },
        "policy_measure": {m["id"]: m["name"].strip() for m in measures},
    }
    return record_sets, labels


def policy_summary(grid: dict, start: int, columns: list[tuple[int, str]]) -> list[dict]:
    """Rows 490 to 555: the measures' effects by head and category, and the direct and
    indirect effects of the Government's decisions."""
    blocks = {
        "Total effects of receipts measures (£ millions)": "receipts_measures",
        "Total effects of expenditure measures (£ millions)": "expenditure_measures",
    }
    heads = {"Current DEL", "Current AME", "Capital DEL", "Capital AME"}
    rows, block, head = [], None, None
    for row in range(start, 556):
        label = grid.get((row, "D"))
        if label is None or label == "of which:":
            continue
        assert all(is_number(grid.get((row, c))) for c in POLICY_YEARS), (row, label)
        if label in blocks:
            block, head = blocks[label], None
            key = f"{block}.total"
        elif block == "receipts_measures" and row < 520:
            key = f"{block}.{slug(label)}"
        elif block == "expenditure_measures" and row < 549:
            if label in heads:
                head = slug(label)
                key = f"{block}.{head}"
            else:
                key = f"{block}.{head}.{slug(label)}"
        else:
            block = "government_decisions"
            key = f"{block}.{slug(label)}"
        rows.append((row, label, key))
    keys = [key for _, _, key in rows]
    assert len(keys) == len(set(keys)), keys
    record_sets = []
    for opening, column in columns:
        entries = []
        for ordinal, (row, label, key) in enumerate(rows):
            entries.append(
                {
                    "value_id": key,
                    "label": collapse(label),
                    "ordinal": ordinal,
                    "row_number": row,
                    "expected_row_header_column": "D",
                    "expected_row_header": label,
                    "table_record_kind": "detail",
                    "filters": {"policy_summary_line": key},
                    "constraints": [
                        policy_constraint("policy_summary_line", key, "Policy decisions summary line")
                    ],
                }
            )
        record_sets.append(
            {
                **record_ids("policy", "summary", "fy", opening),
                "provenance_class": "model_output",
                "assertion": "source_projection",
                "sheet_name": "1.1",
                "period_type": "fiscal_year",
                "period": opening,
                "period_coverage": fiscal_coverage(opening),
                **UK,
                "entity": POLICY_ENTITY[0],
                "entity_role": POLICY_ENTITY[1],
                "domain": POLICY_ENTITY[2],
                "groupby_dimension": "policy_summary_line",
                "rows": entries,
                "measures": [
                    {
                        "measure_id": "costing",
                        "label": f"Costing, FY{fy_label(opening)}",
                        "ordinal": 0,
                        "column": column,
                        "source_column_id": "costing",
                        "expected_column_header_row": 7,
                        "expected_column_header": fy_label(opening),
                        "concept": "obr.policy_decisions_effect",
                        "source_concept": "obr.policy_decisions_effect",
                        "concept_relation": "source_label",
                        "concept_authority": "obr",
                        "concept_evidence_url": download_url("policy"),
                        "concept_evidence_notes": (
                            "OBR EFO October 2026 detailed forecast tables: policy, table "
                            "1.1, rows 490 to 555: the effects of the policy decisions by "
                            "head and category, and the direct and indirect effects of the "
                            f"Government's decisions, GBP million. {POLICY_NOTE}"
                        ),
                        "unit": "gbp",
                        "aggregation": "sum",
                        "value_scale": 1000000,
                        "expected_cell_type": "number",
                    }
                ],
            }
        )
    return record_sets


# ------------------------------------------------------------ the packages


class PackageDumper(yaml.SafeDumper):
    """Plain YAML with no anchors, so every record set reads on its own."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def artifact(kind: str, source_table: str) -> dict:
    return {
        "source_name": "obr",
        "source_table": source_table,
        "resource_package": "db",
        "resource_directory": f"data/obr/efo_{kind}_october_2026",
        "manifest": "manifest.yaml",
        "vintage": "efo_october_2026",
        "extracted_at": "2026-10-29",
        "extraction_method": "xlsx whole-workbook used-range cell parse",
        "parser": "xlsx_used_range",
        "artifact_year": 2026,
    }


def header_lines(text: str) -> str:
    lines = []
    for paragraph in text.strip().split("\n\n"):
        words, line = paragraph.split(), "#"
        for word in words:
            if len(line) + 1 + len(word) > 88:
                lines.append(line)
                line = "#"
            line += " " + word
        lines.append(line)
        lines.append("#")
    return "\n".join(lines) + "\n"


COMMON_HEADER = """
OBR Economic and fiscal outlook, October 2026 (published with the Budget on 28 October
2026), for PolicyEngine/chronicle#393. Written by scripts/build_obr_efo_october_2026.py
from the pinned workbook; edit that, not this. Values are as the tables print them, with
value_scale for the stated unit. Fiscal-year periods store the opening year (2025-26 ->
2025). Each year column's assertion follows the band above it: 'Outturn' (and 'Estimate',
'Estimated Outurn') gives observation and 'Forecast' gives source_projection; a table
with no band is all forecast. In October, 2025-26 is outturn, where in March it was a
forecast, and 2031-32 is a new forecast year.
"""


def march_header(kind: str, changes: list[str]) -> str:
    text = COMMON_HEADER + f"""

The March 2026 package's lines (package obr-efo-{kind}-march-2026), under the
obr.efo_2026_10 prefix with their line ids, display labels and concepts, so a consumer
changes vintage by package. Each is found by its table's title and its row's label; the
row numbers and the October table number ride on each record set and its notes.
"""
    if changes:
        text += "\n\nRows October renames against March: " + "; ".join(changes) + "."
    else:
        text += "\n\nOctober drops, renames or splits none of the March package's rows."
    return text


RECEIPTS_HEADER = """

Receipts. The March 2026 package's 41 lines (receipts tables 3.x are now 4.x, with the
same titles and rows), then every other row of the workbook's tables, except tables 4.9
and 4.19 (RECEIPTS_LEFT_OUT in the build script: 4.9 states no unit for its passenger
numbers; 4.19 prints '£ billion' over thresholds in pounds and flags no outturn). A row
beyond the March lines takes the line id '<table key>.<row label>' and the concept
'obr.<table key>.<row label>', where the table key names the table (other_hmrc_taxes,
cash_receipts, self_employed_income_growth, ...); the sub-rows of table 4.8's 'of which'
blocks, printed in column C, prefix their parent. Table 4.5's 'Savings income' row is
obr.self_employed_income_growth.savings_income, a percentage change on a year earlier
from 2024-25, all under the table's 'Forecast' band. Rows that restate a row kept are
left out, as the March package left out sheet 3.7's total, and the build asserts each
copy equal (each table's left_out in the build script): table 4.7's 'Total SDLT' and
ATED rows (table 4.8 rows 24 and 25); table 4.22's VAT refunds, community
infrastructure levy, extended producer responsibility and five environmental levies
(tables 4.8, 4.2 and 4.20); table 4.21's '(c * d + e + f) Forecast' row (table 4.20's
contracts for difference); and, from 2026-27, table 4.1's 'Betting and gaming taxes'
(table 4.10's total). Tables 4.1 (accrued) and 4.8 (cash) print eight of the same
taxes: each pair shares one concept, with an exact relation, and differs in
accounting_basis (SHARED_TAX_CONCEPTS); table 4.1's vaping tax and 2025-26 betting and
gaming take the March lines' concepts. Table 4.22 prints '£ million' over GBP billion
cells (its VAT refunds equal table 4.8's in every year), so its rows carry value_scale
1e9. Table 4.10 now starts in 2026-27, its first forecast year. Northern Ireland
domestic rates are carried in both places the OBR shows them: this package's table 4.2
row 6, and expenditure table 5.1 row 16.
"""


def render(header: str, payload: dict) -> str:
    return header_lines(header) + yaml.dump(
        payload, Dumper=PackageDumper, sort_keys=False, allow_unicode=True, width=100
    )


def march_payload(kind: str) -> dict:
    path = PACKAGES / f"efo_{kind}_march_2026" / "source_package.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def package_payload(kind: str, record_sets: list[dict], **extra: object) -> dict:
    march = march_payload(kind)
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": f"obr-efo-{kind}-october-2026",
        "label": march["label"].replace("March 2026", "October 2026"),
        "dimension_labels": march.get("dimension_labels", {"obr.efo_line": "EFO table line"}),
    }
    if "dimension_value_labels" in march:
        payload["dimension_value_labels"] = march["dimension_value_labels"]
    payload.update(extra)
    payload["artifact"] = artifact(
        kind, march["artifact"]["source_table"].replace("March 2026", "October 2026")
    )
    payload["record_sets"] = record_sets
    return payload


def build_receipts() -> str:
    record_sets, changes = receipts_package()
    payload = package_payload("receipts", record_sets)
    payload["dimension_value_labels"].setdefault("accounting_basis", {})
    return render(march_header("receipts", changes) + RECEIPTS_HEADER, payload)


def build_expenditure() -> str:
    grids = october_workbook("expenditure")
    record_sets, _, changes = port_march_package("expenditure", grids)
    header = march_header("expenditure", changes) + """

Expenditure tables 4.x are now 5.x, with the same titles. Table 5.1 adds a footnote to
England's council tax receipts: outturn reflects the latest MHCLG pre-measures data and
does not align with the public sector finances data used elsewhere. Its 'NI domestic
rates' row is one of the two places the OBR shows Northern Ireland domestic rates; the
other is receipts table 4.2 row 6, in obr-efo-receipts-october-2026.
"""
    return render(header, package_payload("expenditure", record_sets))


def build_economy() -> str:
    grids = october_workbook("economy")
    record_sets, _, changes = port_march_package("economy", grids)
    record_sets += economy_additions(grids)
    header = march_header("economy", changes) + """

Economy. The March lines for calendar 2025 to 2031, plus two series
PolicyEngine/policyengine-uk#2638's interest projection reads: table 1.9's deposit rate
(obr.deposit_rate) and table 1.11's household financial assets
(obr.household_financial_assets, ONS NNML). Calendar 2025 is outturn and 2026 onwards
forecast; the tables mark no forecast start.
"""
    return render(header, package_payload("economy", record_sets))


def build_aggregates() -> str:
    grids = october_workbook("aggregates")
    record_sets, _, changes = port_march_package("aggregates", grids)
    header = march_header("aggregates", changes) + """

Aggregates. Tables 6.1, 6.2 and 6.5 print only forecast years, now 2026-27 to 2031-32;
table 6.13 has 2025-26 as outturn.
"""
    return render(header, package_payload("aggregates", record_sets))


def build_policy() -> str:
    record_sets, labels = policy_package()
    summary = {
        row["value_id"]: row["label"]
        for record_set in record_sets
        if record_set["groupby_dimension"] == "policy_summary_line"
        for row in record_set["rows"]
    }
    heads, categories = {}, {}
    for record_set in record_sets:
        for row in record_set["rows"]:
            filters = row.get("filters", {})
            if filters.get("policy_head", "all") != "all":
                head, category = row["label"].split(": ", 1)
                heads[filters["policy_head"]] = head
                categories[filters["policy_category"]] = category
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "obr-efo-policy-october-2026",
        "label": "OBR EFO October 2026 detailed forecast tables: policy",
        "dimension_labels": {
            "obr.policy_component": "Policy decision component",
            "policy_summary_line": "Policy decisions summary line",
            "policy_section": "Policy section",
            "policy_measure": "Policy measure",
            "policy_head": "Policy head",
            "policy_category": "Policy category",
        },
        "dimension_value_labels": {
            **labels,
            "policy_head": {"all": "All heads", **dict(sorted(heads.items()))},
            "policy_category": {"all": "All categories", **dict(sorted(categories.items()))},
            "policy_summary_line": summary,
        },
        "artifact": artifact("policy", "EFO October 2026 detailed forecast tables: policy"),
        "record_sets": record_sets,
    }
    header = COMMON_HEADER + """

Policy. Table 1.1, 'Breakdown of policy decisions since March 2026': each decision's
costing by head and category, and its total, for 2026-27 to 2031-32, all under the
table's 'Forecast' band, in GBP million. The 98 scorecard measures keep the OBR's
numbers (measure_1 ... measure_98); the three fiscally neutral and two non-scorecard
measures are numbered in table order. Rows 490 to 555, the effects by head and category
and the direct and indirect effects of the Government's decisions, are one record set
per year (line summary). A negative sign is a loss to the Exchequer, as the table's note
says.
"""
    return render(header, payload)


BUILDERS = {
    "receipts": build_receipts,
    "expenditure": build_expenditure,
    "economy": build_economy,
    "aggregates": build_aggregates,
    "policy": build_policy,
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
    for kind, build in BUILDERS.items():
        path = PACKAGES / f"efo_{kind}_october_2026" / "source_package.yaml"
        text = build()
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    if stale:
        print("Stale generated packages: " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
