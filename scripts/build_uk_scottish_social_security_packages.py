"""Generate the Social Security Scotland caseload packages for PolicyEngine/chronicle#420.

Run from the repository root:

    uv run python scripts/build_uk_scottish_social_security_packages.py

``--check`` compares the generated YAML with the committed files instead of writing.
Every package is written from its pinned workbook, read with Chronicle's own parser,
so every row number, column and guard cell below is one the package parser sees. The
publisher's text is asserted cell by cell, so a run against different bytes fails
rather than drifting. Nothing is downloaded and no value is computed.

Item 7 of the issue (PolicyEngine/uk-scottish-budget-2027-28#6; PolicyEngine/uk-pip-review-2026#1),
from Social Security Scotland's official statistics, the latest edition of each:

- ``scotgov-adp-caseload-july-2026``: Adult Disability Payment to 31 July 2026, the
  caseload by award type, Daily Living and Mobility award level and both levels crossed,
  by type of client (new applicants, case transfers from DWP), each month from April 2024,
  and at 31 July 2026 by age band and by council area.
- ``scotgov-carer-support-payment-caseload-june-2026``: Carer Support Payment to 30 June
  2026, the caseload in payment and with underlying entitlement by type of client each
  month from April 2024, and at 30 June 2026 by age band and by council area.
- ``scotgov-child-disability-payment-caseload-june-2026``: Child Disability Payment to 30
  June 2026, the caseload by type of client each month from April 2024.
- ``scotgov-padp-caseload-july-2026``: Pension Age Disability Payment to 31 July 2026, the
  caseload by type of client each month from its launch in October 2024.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import textwrap
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml
from openpyxl.utils import get_column_letter

from chronicle.sources.cells import SourceArtifactMetadata, source_cells_from_xlsx

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-11-06"
ISSUE = "PolicyEngine/chronicle#420"
CONSUMERS = (
    "PolicyEngine/uk-scottish-budget-2027-28#6 and PolicyEngine/uk-pip-review-2026#1"
)
SCRIPT = "scripts/build_uk_scottish_social_security_packages.py"
SITE = "https://www.socialsecurity.gov.scot/publications/"
FIRST_MONTH = date(2024, 4, 1)  # #420: each published date from April 2024


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


def constraint(variable: str, value: object, label: str) -> Flow:
    return Flow(variable=variable, operator="==", value=value, label=label)


def bound(operator: str, value: int, label: str) -> Flow:
    return Flow(
        variable="age", operator=operator, value=value, unit="years", label=label
    )


def guard(column: str, row: int, value: object, label: str) -> Flow:
    return Flow(column=column, row=row, expected_value=value, label=label)


def squeeze(text: object) -> str:
    return " ".join(str(text).replace("\xa0", " ").split())


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


SCOTLAND = {
    "geography_id": "S92000003",
    "geography_level": "country",
    "geography_name": "Scotland",
    "geography_vintage": "current",
}

# Labels for every dimension and value the packages use. A package declares the ones
# its facts use; the values two packages emit go in
# chronicle/dimension_values/canonical_labels.json. Age bands take the register's
# 'Age 16 to 17' wording, as the chronicle#420 young people packages do.
DIMENSION_LABELS = {
    "scotgov.adp_month": "ADP caseload month",
    "scotgov.carer_support_payment_month": "Carer Support Payment caseload month",
    "scotgov.child_disability_payment_month": "Child Disability Payment caseload month",
    "scotgov.padp_month": "Pension Age Disability Payment caseload month",
    "geography": "Geography",
    "age_band": "Age band",
    "case_route": "Type of client",
    "adp_award_components": "ADP award components",
    "adp_daily_living_award_level": "ADP Daily Living award level",
    "adp_mobility_award_level": "ADP Mobility award level",
    "carer_support_payment_status": "Carer Support Payment status",
}
AGE_BANDS = {
    # value id: (words, lower bound, upper bound)
    "16_to_18": ("16 to 18", 16, 19),
    "19_to_24": ("19 to 24", 19, 25),
    "25_to_34": ("25 to 34", 25, 35),
    "35_to_44": ("35 to 44", 35, 45),
    "45_to_54": ("45 to 54", 45, 55),
    "55_to_64": ("55 to 64", 55, 65),
    "under_18": ("under 18", None, 18),
    "18_to_24": ("18 to 24", 18, 25),
    "25_to_29": ("25 to 29", 25, 30),
    "30_to_34": ("30 to 34", 30, 35),
    "35_to_39": ("35 to 39", 35, 40),
    "40_to_44": ("40 to 44", 40, 45),
    "45_to_49": ("45 to 49", 45, 50),
    "50_to_54": ("50 to 54", 50, 55),
    "55_to_59": ("55 to 59", 55, 60),
    "60_to_64": ("60 to 64", 60, 65),
    "65_and_over": ("65 and over", 65, None),
}
VALUE_LABELS = {
    "age_band": {band: f"Age {words}" for band, (words, _, _) in AGE_BANDS.items()},
    "case_route": {
        "all": "All clients",
        "new_applicant": "New applicants",
        "case_transfer": "Case transfers",
    },
    "adp_award_components": {
        "daily_living_only": "Daily Living award only",
        "mobility_only": "Mobility award only",
        "both": "Both Daily Living and Mobility awards",
    },
    "adp_daily_living_award_level": {
        "enhanced": "Enhanced",
        "standard": "Standard",
        "transitional": "Transitional",
        "not_awarded": "Not awarded",
    },
    "adp_mobility_award_level": {
        "enhanced": "Enhanced",
        "standard": "Standard",
        "not_awarded": "Not awarded",
    },
    "carer_support_payment_status": {
        "in_payment": "In payment",
        "underlying_entitlement": "Underlying entitlement",
    },
}


def declarations(record_sets: list[dict]) -> tuple[dict, dict]:
    """The dimension and value labels the record sets' facts use."""
    used: dict[str, set[str]] = {}
    for record_set in record_sets:
        used.setdefault(record_set["groupby_dimension"], set())
        filters = [record_set.get("shared_filters", {})]
        filters += [row.get("filters", {}) for row in record_set["rows"]]
        filters += [measure.get("filters", {}) for measure in record_set["measures"]]
        for mapping in filters:
            for key, value in mapping.items():
                used.setdefault(key, set()).add(str(value))
    dimension_labels = {
        key: DIMENSION_LABELS[key] for key in DIMENSION_LABELS if key in used
    }
    value_labels = {
        key: {
            value: label
            for value, label in VALUE_LABELS[key].items()
            if value in used[key]
        }
        for key in VALUE_LABELS
        if used.get(key)
    }
    return dimension_labels, value_labels


def category(variable: str, value: str) -> tuple[dict, list[Flow]]:
    """A publisher category as a filter and, unless it is 'all', a constraint."""
    if value == "all":
        return {variable: value}, []
    return {variable: value}, [constraint(variable, value, DIMENSION_LABELS[variable])]


def age_semantics(band: str) -> tuple[Flow, list[Flow]]:
    words, lower, upper = AGE_BANDS[band]
    filters, constraints = category("age_band", band)
    if lower is not None:
        constraints.append(bound(">=", lower, "Age lower bound"))
    if upper is not None:
        constraints.append(bound("<", upper, "Age upper bound"))
    return Flow(filters), constraints


MONTH_NUMBERS = {
    name: number
    for number, name in enumerate(
        "January February March April May June July August September October November "
        "December".split(),
        start=1,
    )
}
MONTH_NUMBERS.update({name[:3]: number for name, number in list(MONTH_NUMBERS.items())})


def month_of(label: object) -> date | None:
    if not isinstance(label, str):
        return None
    match = re.fullmatch(r"([A-Z][a-z]+) (\d{4})", label.strip())
    if not match or match.group(1) not in MONTH_NUMBERS:
        return None
    return date(int(match.group(2)), MONTH_NUMBERS[match.group(1)], 1)


def month_end(month: date) -> date:
    following = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return date.fromordinal(following.toordinal() - 1)


def point_in_time(month: date, label: str, notes: str) -> dict:
    last = month_end(month).isoformat()
    return {
        "start_date": last,
        "end_date": last,
        "basis": "calendar",
        "source_period_label": label,
        "notes": notes,
    }


def measure_spec(
    measure_id: str,
    label: str,
    column: str,
    header_row: int,
    header: str,
    *,
    concept: str,
    evidence_url: str,
    notes: str,
    filters: Flow | None = None,
    constraints: list[Flow] | None = None,
) -> dict:
    measure = {
        "measure_id": measure_id,
        "label": label,
        "ordinal": 0,
        "column": column,
        "source_column_id": measure_id,
        "expected_column_header_row": header_row,
        "expected_column_header": header,
        "concept": concept,
        "source_concept": concept,
        "concept_relation": "source_label",
        "concept_authority": "social_security_scotland",
        "concept_evidence_url": evidence_url,
        "concept_evidence_notes": notes,
        "unit": "count",
        "aggregation": "sum",
        "expected_cell_type": "number",
    }
    if filters:
        measure["filters"] = filters
    if constraints:
        measure["constraints"] = constraints
    return measure


def numbered(measures: list[dict]) -> list[dict]:
    return [{**measure, "ordinal": ordinal} for ordinal, measure in enumerate(measures)]


def fact_count(payload: dict) -> int:
    return sum(len(rs["rows"]) * len(rs["measures"]) for rs in payload["record_sets"])


def package_payload(
    *, package_id: str, label: str, record_sets: list[dict], artifact: dict
) -> dict:
    dimension_labels, value_labels = declarations(record_sets)
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": package_id,
        "label": label,
        "dimension_labels": dimension_labels,
    }
    if value_labels:
        payload["dimension_value_labels"] = value_labels
    payload["artifact"] = artifact
    payload["record_sets"] = record_sets
    return payload


# ---------------------------------------------------------------- council areas

# Chronicle's register names every Scottish council area; Social Security Scotland
# writes one of them its own way.
COUNCIL_ALIASES = {"Edinburgh, City of": "City of Edinburgh"}


def council_codes() -> dict[str, str]:
    register = json.loads(
        (ROOT / "chronicle/geography/uk_canonical_names.json").read_text()
    )
    names = {
        code: name for code, name in register["names"].items() if code.startswith("S12")
    }
    assert len(names) == 32, len(names)
    by_name = {name: code for code, name in names.items()}
    assert len(by_name) == 32
    return by_name


def council_rows(grid: dict, sheet: str, first_row: int, value_column: str):
    """(row, printed name, code) for the 32 councils, then the 'Other' and Total rows."""
    by_name = council_codes()
    seen: dict[str, int] = {}
    rows = []
    other = None
    row = first_row
    while (sheet, row, "A") in grid:
        text = grid[(sheet, row, "A")]
        if isinstance(text, str) and text.startswith("[note"):
            break
        if text == "Other":
            other = row
        elif text != "Total":
            name = COUNCIL_ALIASES.get(text, text)
            code = by_name[name]
            assert code not in seen, (sheet, text)
            seen[code] = row
            rows.append((row, text, code))
        row += 1
    assert len(rows) == 32 and other is not None, (sheet, len(rows), other)
    return rows, other


# ---------------------------------------------------------------- long monthly tables


@dataclass(frozen=True)
class MonthlyTable:
    sheet: str
    title: str  # the start of the title cell
    header_row: int
    routes: tuple[tuple[str, str], ...]  # (printed type of client, case_route value)
    month_header: str
    caseload_header: str
    # (measure id, printed header, filters) for every ported column but the caseload
    columns: tuple[tuple[str, str, dict], ...]
    port_caseload: bool = True
    # (measure id, a sentence its notes add): what a column holds beyond its header
    column_notes: tuple[tuple[str, str], ...] = ()


def monthly_blocks(grid: dict, table: MonthlyTable):
    """{route: [(row, month, label)]} for the months from April 2024, in order."""
    sheet = table.sheet
    assert grid[(sheet, table.header_row, "A")] == "Type of client"
    assert squeeze(grid[(sheet, table.header_row, "B")]) == table.month_header
    blocks: dict[str, list[tuple[int, date, str]]] = {}
    order: list[str] = []
    row = table.header_row + 1
    while True:
        route = grid.get((sheet, row, "A"))
        if not isinstance(route, str) or route.startswith("[note"):
            break
        label = grid[(sheet, row, "B")]
        month = month_of(label)
        assert month is not None, (sheet, row, label)
        if route not in blocks:
            order.append(route)
            blocks[route] = []
        blocks[route].append((row, month, label))
        row += 1
    assert order == [printed for printed, _ in table.routes], (sheet, order)
    months = None
    ported = {}
    for route in order:
        rows = blocks[route]
        for (_, before, _), (_, after, _) in zip(rows, rows[1:]):
            assert month_end(before).toordinal() + 1 == after.toordinal(), (
                sheet,
                route,
            )
        series = [month for _, month, _ in rows]
        assert months is None or series == months, sheet
        months = series
        ported[route] = [item for item in rows if item[1] >= FIRST_MONTH]
    return ported


def header_columns(grid: dict, sheet: str, header_row: int) -> dict[str, str]:
    columns = {}
    column = 1
    while (sheet, header_row, get_column_letter(column)) in grid:
        text = squeeze(grid[(sheet, header_row, get_column_letter(column))])
        assert text not in columns, (sheet, text)
        columns[text] = get_column_letter(column)
        column += 1
    return columns


@dataclass
class Tally:
    suppressed: int = 0
    gaps: dict | None = None

    def gap(
        self, name: str, parts: list, whole, *, limit: int = 15, shortfall: float = 0.0
    ) -> None:
        """Record the parts' gap to the whole, and assert it is within the rounding.

        Each published cell is rounded to the nearest 5, so a few parts miss their
        whole by 5 or 10. ``shortfall`` also allows the parts to fall short by up to that
        share of the whole, for cases the publisher could not assign to a part.
        """
        if self.gaps is None:
            self.gaps = {}
        if whole is None or any(part is None for part in parts):
            self.gaps.setdefault(f"{name} (skipped: a [c] cell)", 0)
            self.gaps[f"{name} (skipped: a [c] cell)"] += 1
            return
        difference = sum(parts) - whole
        self.gaps[name] = max(self.gaps.get(name, 0), abs(difference))
        assert difference <= limit, (name, parts, whole)
        assert -difference <= limit + shortfall * whole, (name, parts, whole)


def cell_value(grid: dict, key: tuple, tally: Tally) -> int | None:
    value = grid.get(key)
    if value == "[c]":
        tally.suppressed += 1
        return None
    assert is_number(value), (key, value)
    return value


def monthly_record_sets(
    grid: dict,
    table: MonthlyTable,
    *,
    package_slug: str,
    groupby: str,
    concept: str,
    role: str,
    page: str,
    benefit: str,
    caseload_note: str,
    tally: Tally,
) -> tuple[list[dict], dict]:
    """One record set per type of client and month: its row, and its ported columns."""
    sheet = table.sheet
    title = grid[(sheet, 1, "A")]
    assert squeeze(title).startswith(table.title), (sheet, title)
    columns = header_columns(grid, sheet, table.header_row)
    assert squeeze(table.caseload_header) in columns, (sheet, table.caseload_header)
    ported = monthly_blocks(grid, table)
    values: dict[tuple[str, date], dict[str, int | None]] = {}
    record_sets = []
    route_values = dict(table.routes)
    for printed_route, rows in ported.items():
        route = route_values[printed_route]
        for row, month, label in rows:
            cells = {
                "caseload": cell_value(
                    grid, (sheet, row, columns[squeeze(table.caseload_header)]), tally
                )
            }
            measures = []
            if table.port_caseload and cells["caseload"] is not None:
                measures.append(
                    measure_spec(
                        "caseload",
                        f"{benefit} caseload",
                        columns[squeeze(table.caseload_header)],
                        table.header_row,
                        grid[
                            (
                                sheet,
                                table.header_row,
                                columns[squeeze(table.caseload_header)],
                            )
                        ],
                        concept=concept,
                        evidence_url=page,
                        notes=(
                            f"{benefit} statistics, sheet '{sheet}', column "
                            f"{columns[squeeze(table.caseload_header)]} "
                            f"('{squeeze(table.caseload_header)}'): {caseload_note}"
                        ),
                    )
                )
            for measure_id, header, filters in table.columns:
                column = columns[squeeze(header)]
                value = cell_value(grid, (sheet, row, column), tally)
                cells[measure_id] = value
                if value is None:
                    continue
                more_filters, more_constraints = {}, []
                for variable, item in filters.items():
                    f, c = category(variable, item)
                    more_filters.update(f)
                    more_constraints += c
                measures.append(
                    measure_spec(
                        measure_id,
                        f"{benefit}: {squeeze(header)}",
                        column,
                        table.header_row,
                        grid[(sheet, table.header_row, column)],
                        concept=concept,
                        evidence_url=page,
                        notes=(
                            f"{benefit} statistics, sheet '{sheet}', column {column} "
                            f"('{squeeze(header)}'), people in receipt on the last day of "
                            "the month."
                            + (
                                f" {dict(table.column_notes)[measure_id]}"
                                if measure_id in dict(table.column_notes)
                                else ""
                            )
                        ),
                        filters=Flow(more_filters),
                        constraints=more_constraints,
                    )
                )
            values[(route, month)] = cells
            if not measures:
                continue
            filters, constraints = category("case_route", route)
            record_set_id = (
                f"scotgov.{package_slug}.{sheet_id(sheet)}.{route}.{month:%Y_%m}"
            )
            guards = [
                guard("A", 1, title, "table title"),
                guard("A", row, printed_route, "type of client"),
            ]
            record_sets.append(
                {
                    "record_set_id": record_set_id,
                    "provenance_class": "administrative",
                    "assertion": "observation",
                    "record_set_spec_id": f"{record_set_id}.v1",
                    "source_record_id_prefix": record_set_id,
                    "sheet_name": sheet,
                    "period_type": "month",
                    "period": f"{month:%Y-%m}",
                    "period_coverage": point_in_time(month, label, caseload_note),
                    **SCOTLAND,
                    "entity": "person",
                    "entity_role": role,
                    "domain": "social_security",
                    "groupby_dimension": groupby,
                    "shared_filters": filters,
                    "shared_constraints": constraints,
                    "rows": [
                        {
                            "value_id": f"{month:%Y_%m}",
                            "label": label,
                            "ordinal": 0,
                            "row_number": row,
                            "expected_row_header_column": "B",
                            "expected_row_header": label,
                            # All clients is the type-of-client breakdown's total.
                            "table_record_kind": "total"
                            if route == "all"
                            else "detail",
                            "guard_cells": guards,
                        }
                    ],
                    "measures": numbered(measures),
                }
            )
    return record_sets, values


def sheet_id(sheet: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", sheet.lower()).strip("_")


def check_routes(values: dict, tally: Tally, name: str) -> None:
    """New applicants plus case transfers make all clients, for every ported column."""
    months = sorted({month for _, month in values})
    for month in months:
        whole = values[("all", month)]
        for key in whole:
            tally.gap(
                f"{name}: routes add to all clients",
                [
                    values[("new_applicant", month)][key],
                    values[("case_transfer", month)][key],
                ],
                whole[key],
            )


def snapshot_record_set(
    *,
    record_set_id: str,
    sheet: str,
    rows: list[dict],
    month: date,
    label: str,
    notes: str,
    groupby: str,
    role: str,
    measure: dict,
    geography: dict | None = None,
) -> dict:
    return {
        "record_set_id": record_set_id,
        "provenance_class": "administrative",
        "assertion": "observation",
        "record_set_spec_id": f"{record_set_id}.v1",
        "source_record_id_prefix": record_set_id,
        "sheet_name": sheet,
        "period_type": "month",
        "period": f"{month:%Y-%m}",
        "period_coverage": point_in_time(month, label, notes),
        **(geography or SCOTLAND),
        "entity": "person",
        "entity_role": role,
        "domain": "social_security",
        "groupby_dimension": groupby,
        "rows": rows,
        "measures": [measure],
    }


def age_table(
    grid: dict,
    *,
    sheet: str,
    title_start: str,
    header: tuple[str, str],
    bands: tuple[tuple[str, str], ...],
    tally: Tally,
    name: str,
) -> tuple[list[dict], int, str]:
    """Rows for each printed age band; asserts the bands add to the printed total."""
    title = grid[(sheet, 1, "A")]
    assert squeeze(title).startswith(title_start), (sheet, title)
    assert grid[(sheet, 6, "A")] == header[0] and grid[(sheet, 6, "B")] == header[1]
    assert grid[(sheet, 7, "A")] == "Total"
    total = grid[(sheet, 7, "B")]
    rows, parts = [], []
    for offset, (printed, band) in enumerate(bands):
        row = 8 + offset
        assert grid[(sheet, row, "A")] == printed, (sheet, row)
        value = cell_value(grid, (sheet, row, "B"), tally)
        parts.append(value)
        if value is None:
            continue
        filters, constraints = age_semantics(band)
        rows.append(
            {
                "value_id": band,
                "label": VALUE_LABELS["age_band"][band],
                "ordinal": offset,
                "row_number": row,
                "expected_row_header_column": "A",
                "expected_row_header": printed,
                "table_record_kind": "detail",
                "filters": filters,
                "constraints": constraints,
            }
        )
    assert str(grid[(sheet, 8 + len(bands), "A")]).startswith("[note"), sheet
    rows[0]["guard_cells"] = [guard("A", 1, title, "table title")]
    tally.gap(f"{name}: age bands add to the total", parts, total)
    return rows, total, title


def council_table(
    grid: dict,
    *,
    sheet: str,
    title_start: str,
    header: tuple[str, str],
    tally: Tally,
    name: str,
) -> tuple[list[dict], int, str, int]:
    title = grid[(sheet, 1, "A")]
    assert squeeze(title).startswith(title_start), (sheet, title)
    assert (
        squeeze(grid[(sheet, 6, "A")]) == header[0]
        and squeeze(grid[(sheet, 6, "B")]) == header[1]
    )
    assert grid[(sheet, 7, "A")] == "Total"
    total = grid[(sheet, 7, "B")]
    councils, other_row = council_rows(grid, sheet, 8, "B")
    rows, parts = [], []
    for ordinal, (row, printed, code) in enumerate(councils):
        value = cell_value(grid, (sheet, row, "B"), tally)
        parts.append(value)
        if value is None:
            continue
        rows.append(
            {
                "value_id": code.lower(),
                "label": printed,
                "ordinal": ordinal,
                "row_number": row,
                "expected_row_header_column": "A",
                "expected_row_header": printed,
                "geography_id": code,
                "geography_level": "local_authority",
                "geography_name": printed,
                "geography_vintage": "ca_2019",
                "table_record_kind": "detail",
            }
        )
    other = grid[(sheet, other_row, "B")]
    rows[0]["guard_cells"] = [guard("A", 1, title, "table title")]
    tally.gap(f"{name}: councils and 'Other' add to the total", parts + [other], total)
    return rows, total, title, other


def snapshot_measure(
    *, sheet: str, header: str, concept: str, page: str, benefit: str, what: str
) -> dict:
    return measure_spec(
        "caseload",
        f"{benefit} caseload",
        "B",
        6,
        header,
        concept=concept,
        evidence_url=page,
        notes=f"{benefit} statistics, sheet '{sheet}', column B ('{header}'): {what}",
    )


def format_gaps(tally: Tally) -> str:
    parts = []
    for name, gap in sorted(tally.gaps.items()):
        if "skipped" in name:
            parts.append(f"{name}: {gap}")
        else:
            parts.append(f"{name}: at most {gap:,}")
    return "; ".join(parts)


def artifact(directory: str, entry: dict, source_table: str, vintage: str) -> dict:
    return {
        "source_name": "scotgov",
        "source_table": source_table,
        "resource_package": "db",
        "resource_directory": f"data/{directory}",
        "manifest": "manifest.yaml",
        "vintage": vintage,
        "extracted_at": EXTRACTED_AT,
        "extraction_method": f"xlsx used-range cell parse ({entry['filename']})",
        "parser": "xlsx_used_range",
        "artifact_year": 2026,
    }


ROUNDING = "'Figures are rounded for disclosure control and may not sum due to rounding' (note 1)"


# ---------------------------------------------------------------- Adult Disability Payment

ADP_DIRECTORY = "scotgov/adp_statistics_july_2026"
ADP_PAGE = SITE + "2026/09/adult-disability-payment-statistics-to-31-july-2026"
ADP_ROUTES = (
    ("All", "all"),
    ("New Applicant", "new_applicant"),
    ("Case Transfer", "case_transfer"),
)
ADP_CASELOAD_NOTE = (
    "'The caseload presented in the ADP tables is based on a true point-in-time on the last "
    "day of each month to calculate the caseload of that month' (note 51); 'The caseload "
    "measure counts an individual only once' (note 32)."
)
# Tables 16 and 17 cite note 62 ('not included in this table'), but their 'Number not
# awarded' is the caseload less the assigned levels: it includes the cases note 70 says
# could not be assigned to an award level, so Table 16's is Table 15's Mobility-only count
# plus Table 15's shortfall, and Table 17's the Daily Living-only count plus the same
# shortfall. build_adp asserts both; note 62 holds for Table 18.
ADP_NOT_AWARDED_NOTE = (
    "Its 'Number not awarded' is the caseload less the assigned levels, so it includes "
    "the cases that 'could not be assigned to a Daily Living or Mobility award level' "
    "(note 70): it is Table 15's {other} count plus Table 15's shortfall, within the "
    "rounding, not Table 15's {other} count alone. Note 62's 'not included in this "
    "table' holds for Table 18, not for this column."
)


ADP_TABLES = (
    MonthlyTable(
        "T15 Caseload by award type",
        "Table 15: Caseload for Adult Disability Payment by award type",
        6,
        ADP_ROUTES,
        "Month",
        "Caseload",
        (
            (
                "daily_living_only",
                "Number in receipt of Daily Living Award only",
                {"adp_award_components": "daily_living_only"},
            ),
            (
                "mobility_only",
                "Number in receipt of Mobility award only",
                {"adp_award_components": "mobility_only"},
            ),
            (
                "both",
                "Number in receipt of both Daily Living and Mobility award",
                {"adp_award_components": "both"},
            ),
        ),
    ),
    MonthlyTable(
        "T16 Caseload by DL award",
        "Table 16: Caseload for Adult Disability Payment by Daily Living award level",
        6,
        ADP_ROUTES,
        "Month",
        "Caseload",
        (
            (
                "daily_living_enhanced",
                "Number on Enhanced Daily Living",
                {"adp_daily_living_award_level": "enhanced"},
            ),
            (
                "daily_living_standard",
                "Number on Standard Daily Living",
                {"adp_daily_living_award_level": "standard"},
            ),
            (
                "daily_living_transitional",
                "Number on transitional Daily Living",
                {"adp_daily_living_award_level": "transitional"},
            ),
            (
                "daily_living_not_awarded",
                "Number not awarded",
                {"adp_daily_living_award_level": "not_awarded"},
            ),
        ),
        port_caseload=False,
        column_notes=(
            (
                "daily_living_not_awarded",
                ADP_NOT_AWARDED_NOTE.format(other="Mobility only"),
            ),
        ),
    ),
    MonthlyTable(
        "T17 Caseload by mob award",
        "Table 17: Caseload for Adult Disability Payment by Mobility award level",
        6,
        ADP_ROUTES,
        "Month",
        "Caseload",
        (
            (
                "mobility_enhanced",
                "Number on Enhanced Mobility",
                {"adp_mobility_award_level": "enhanced"},
            ),
            (
                "mobility_standard",
                "Number on Standard Mobility",
                {"adp_mobility_award_level": "standard"},
            ),
            (
                "mobility_not_awarded",
                "Number not awarded",
                {"adp_mobility_award_level": "not_awarded"},
            ),
        ),
        port_caseload=False,
        column_notes=(
            (
                "mobility_not_awarded",
                ADP_NOT_AWARDED_NOTE.format(other="Daily Living only"),
            ),
        ),
    ),
    MonthlyTable(
        "T18 Caseload by award level",
        "Table 18: Caseload for Adult Disability Payment by Daily Living and Mobility award levels",
        6,
        ADP_ROUTES,
        "Month",
        "Caseload",
        tuple(
            (
                f"mobility_{mobility}__daily_living_{living}",
                f"Mobility {mobility_text} - Daily Living {living_text}",
                {
                    "adp_mobility_award_level": mobility,
                    "adp_daily_living_award_level": living,
                },
            )
            for mobility, mobility_text in (
                ("enhanced", "Enhanced"),
                ("standard", "Standard"),
                ("not_awarded", "Not Awarded"),
            )
            for living, living_text in (
                ("enhanced", "Enhanced"),
                ("standard", "Standard"),
                ("transitional", "Transitional"),
                ("not_awarded", "Not Awarded"),
            )
            if (mobility, living) != ("not_awarded", "not_awarded")
        ),
        port_caseload=False,
    ),
)
ADP_AGE_BANDS = (
    ("16-18", "16_to_18"),
    ("19-24", "19_to_24"),
    ("25-34", "25_to_34"),
    ("35-44", "35_to_44"),
    ("45-54", "45_to_54"),
    ("55-64", "55_to_64"),
    ("65 and older", "65_and_over"),
)
ADP_NOTE_QUOTES = (
    "Figures are rounded for disclosure control and may not sum due to rounding.",
    "[c] indicates that figures are suppressed for disclosure control.",
    "The caseload measure counts an individual only once.",
    "The caseload presented in the ADP tables is based on a true point-in-time on the last "
    "day of each month to calculate the caseload of that month.",
    "A case transfer is a DWP client who has had their award transferred over to Adult "
    "Disability Payment.",
    "The transitional low rate WADLA is a transitional rate for clients transferred from "
    "Working Age Disability Living Allowance to Adult Disability Payment",
    "A small number of cases could not be assigned to a daily living award level and are "
    "not included in this table, therefore totals may not sum.",
    "The age that is used in this table is based on the age the person would be on the last "
    "day of the specific caseload period.",
)


def build_adp() -> str:
    entry, content = pinned(ADP_DIRECTORY)
    grid = grid_of(source_cells_from_xlsx(content, metadata(entry["filename"])))
    notes = squeeze(" ".join(str(v) for (s, _, _), v in grid.items() if s == "Notes"))
    for quote in ADP_NOTE_QUOTES:
        assert squeeze(quote) in notes, quote
    assert (
        grid[("Contents", 1, "A")]
        == "Adult Disability Payment from 21 March 2022 to 31 July 2026"
    )
    tally = Tally()
    record_sets = []
    tables = {}
    for table in ADP_TABLES:
        sets, values = monthly_record_sets(
            grid,
            table,
            package_slug="adp_july_2026",
            groupby="scotgov.adp_month",
            concept="scotgov.adp_caseload",
            role="adp_client",
            page=ADP_PAGE,
            benefit="Adult Disability Payment",
            caseload_note=ADP_CASELOAD_NOTE,
            tally=tally,
        )
        record_sets += sets
        tables[table.sheet] = values
        check_routes(values, tally, table.sheet)
    t15 = tables["T15 Caseload by award type"]
    for sheet, values in tables.items():
        for key, cells in values.items():
            # Every table's caseload column is T15's; it is ported once, from T15.
            assert cells["caseload"] == t15[key]["caseload"], (sheet, key)
            parts = [value for name, value in cells.items() if name != "caseload"]
            # Note 70: 'A small number of cases could not be assigned to a Daily Living or
            # Mobility award level', so Tables 15 and 18 fall short of the caseload.
            unassigned = 0.01 if sheet.startswith(("T15", "T18")) else 0.0
            tally.gap(
                f"{sheet}: levels add to the caseload",
                parts,
                cells["caseload"],
                shortfall=unassigned,
            )
    # Tables 16 and 17's 'not awarded' include the unassigned cases (ADP_NOT_AWARDED_NOTE).
    for key, cells in t15.items():
        unassigned = cells["caseload"] - sum(
            cells[part] for part in ("daily_living_only", "mobility_only", "both")
        )
        tally.gap(
            "T16's not awarded is T15's Mobility only plus T15's shortfall",
            [cells["mobility_only"], unassigned],
            tables["T16 Caseload by DL award"][key]["daily_living_not_awarded"],
        )
        tally.gap(
            "T17's not awarded is T15's Daily Living only plus T15's shortfall",
            [cells["daily_living_only"], unassigned],
            tables["T17 Caseload by mob award"][key]["mobility_not_awarded"],
        )
    for key, cells in tables["T18 Caseload by award level"].items():
        living = tables["T16 Caseload by DL award"][key]
        mobility = tables["T17 Caseload by mob award"][key]
        for level in ("enhanced", "standard", "transitional"):
            tally.gap(
                "T18's Daily Living margins against T16",
                [
                    cells[f"mobility_{m}__daily_living_{level}"]
                    for m in ("enhanced", "standard", "not_awarded")
                ],
                living[f"daily_living_{level}"],
            )
        for level in ("enhanced", "standard"):
            tally.gap(
                "T18's Mobility margins against T17",
                [
                    cells[f"mobility_{level}__daily_living_{d}"]
                    for d in ("enhanced", "standard", "transitional", "not_awarded")
                ],
                mobility[f"mobility_{level}"],
            )
    latest = max(month for _, month in t15)
    assert latest == date(2026, 7, 1)
    mobility_only_latest = t15[("all", latest)]["mobility_only"]
    not_awarded_latest = tables["T16 Caseload by DL award"][("all", latest)][
        "daily_living_not_awarded"
    ]
    latest_caseload = t15[("all", latest)]["caseload"]
    # Table 19: by age at 31 July 2026; its total is T15's, ported once.
    age_rows, age_total, _ = age_table(
        grid,
        sheet="T19 Caseload by age",
        title_start="Table 19: Caseload for Adult Disability Payment by age at 31 July 2026",
        header=("Age band", "Caseload"),
        bands=ADP_AGE_BANDS,
        tally=tally,
        name="T19",
    )
    assert age_total == latest_caseload, (age_total, latest_caseload)
    record_sets.append(
        snapshot_record_set(
            record_set_id="scotgov.adp_july_2026.t19_caseload_by_age.2026_07",
            sheet="T19 Caseload by age",
            rows=age_rows,
            month=latest,
            label="31 July 2026",
            notes=(
                f"{ADP_CASELOAD_NOTE} 'The age that is used in this table is based on the age "
                "the person would be on the last day of the specific caseload period' (note 33)."
            ),
            groupby="age_band",
            role="adp_client",
            measure=snapshot_measure(
                sheet="T19 Caseload by age",
                header="Caseload",
                concept="scotgov.adp_caseload",
                page=ADP_PAGE,
                benefit="Adult Disability Payment",
                what="people in receipt on 31 July 2026 by age band.",
            ),
        )
    )
    # Table 25: by council area at 31 July 2026; 'Other' (no council) emits no fact.
    council_rows_, council_total, _, other = council_table(
        grid,
        sheet="T25 Caseload by LA",
        title_start="Table 25: Caseload for Adult Disability Payment by Local Authority area at 31 July 2026",
        header=("Local Authority", "Caseload"),
        tally=tally,
        name="T25",
    )
    assert council_total == latest_caseload
    record_sets.append(
        snapshot_record_set(
            record_set_id="scotgov.adp_july_2026.t25_caseload_by_council.2026_07",
            sheet="T25 Caseload by LA",
            rows=council_rows_,
            month=latest,
            label="31 July 2026",
            notes=ADP_CASELOAD_NOTE,
            groupby="geography",
            role="adp_client",
            measure=snapshot_measure(
                sheet="T25 Caseload by LA",
                header="Caseload",
                concept="scotgov.adp_caseload",
                page=ADP_PAGE,
                benefit="Adult Disability Payment",
                what="people in receipt on 31 July 2026 by council area.",
            ),
            geography=SCOTLAND,
        )
    )
    payload = package_payload(
        package_id="scotgov-adp-caseload-july-2026",
        label=(
            "Social Security Scotland: Adult Disability Payment caseload by award type and level "
            "and type of client, April 2024 to July 2026, and by age and council area at 31 July "
            "2026"
        ),
        record_sets=record_sets,
        artifact=artifact(
            ADP_DIRECTORY,
            entry,
            "Adult Disability Payment statistics to 31 July 2026, Tables 15 to 19 and 25",
            "adp_statistics_2026_09_15",
        ),
    )
    header = f"""
    Social Security Scotland, 'Adult Disability Payment statistics to 31 July 2026'
    (published 15 September 2026, {ADP_PAGE}), the caseload tables, for {ISSUE} item 7
    ({CONSUMERS}). Written by {SCRIPT} from the pinned workbook. Statistics producer:
    Social Security Scotland, an executive agency of the Scottish Government, so the
    source id is scotgov.

    Ported, each month from April 2024 to July 2026 and for all clients, new applicants
    and case transfers ('A case transfer is a DWP client who has had their award
    transferred over to Adult Disability Payment', note 47): Table 15's caseload and its
    numbers with a Daily Living award only, a Mobility award only and both; Table 16's
    numbers on enhanced, standard and transitional Daily Living and not awarded it ('The
    transitional low rate WADLA is a transitional rate for clients transferred from Working
    Age Disability Living Allowance to Adult Disability Payment'); Table 17's on enhanced
    and standard Mobility and not awarded it; and Table 18's eleven combinations of the two
    levels. And at 31 July 2026: Table 19's caseload by age band ('The age that is used in
    this table is based on the age the person would be on the last day of the specific
    caseload period', note 33) and Table 25's by council area. All as concept
    scotgov.adp_caseload, people, at Scotland or the council's code.

    Each table prints the caseload again; the generator asserts every one equal to Table
    15's and ports it once, from Table 15, and Tables 19 and 25's totals are Table 15's
    July 2026 caseload. Not ported: the percentage columns (each row's counts over its
    caseload), Table 15's Accessible Vehicles and Equipment counts, March 2022 to March 2024,
    and Table 25's 'Other' row (postcodes that match no council), which has no code but
    counts in the total.

    Semantics as published: {ADP_CASELOAD_NOTE} {ROUNDING}; '[c] indicates that figures are
    suppressed for disclosure control' (note 11), and a [c] cell emits no fact ({tally.suppressed}
    in the ported rows). Tables 16, 17 and 18 cite note 62: 'A small number of cases could
    not be assigned to a daily living award level and are not included in this table,
    therefore totals may not sum'. That holds for Table 18, which falls short of the
    caseload as Table 15 does (note 70). Tables 16 and 17 add up: their 'Number not
    awarded' is the caseload less the assigned levels, so it includes the unassigned cases.
    Table 16's is Table 15's Mobility-only count plus Table 15's shortfall, and Table 17's
    the Daily Living-only count plus the same shortfall, within the rounding in every
    month and type of client. So adp_daily_living_award_level not_awarded is not 'ADP
    clients with Mobility only' ({not_awarded_latest:,} against Table 15's
    {mobility_only_latest:,} for all clients at July 2026), and it rises faster than that
    count as the shortfall grows; the generator
    asserts both identities, and those two columns' notes say so.
    Note 84: a change of analytical software raised the award levels in Tables 15 to 18 'with
    around 1-2% more enhanced Daily Living awards, 1% more enhanced Mobility awards, and 1-2%
    more clients awarded both Daily Living and Mobility components', so earlier editions'
    levels are not comparable.

    Parity, asserted by the generator: routes, levels, ages and councils add to their
    totals within the rounding to the nearest 5, except that Tables 15 and 18 fall short of
    the caseload by the cases that 'could not be assigned to a Daily Living or Mobility award
    level' (note 70): 280 people for all clients in April 2024, rising to 2,520 (0.5 per
    cent) in July 2026. Largest gaps: {format_gaps(tally)}. {fact_count(payload)} facts.
    """
    return render(header, payload)


# ---------------------------------------------------------------- Carer Support Payment

CSP_DIRECTORY = "scotgov/carer_support_payment_statistics_june_2026"
CSP_PAGE = (
    SITE
    + "2026/08/carer-support-payment-statistics-and-carers-allowance-supplement-statistics-to-30-june-2026"
)
CSP_CASELOAD_NOTE = (
    "'The caseload presented in the Carer Support Payment caseload table is based on a true "
    "point-in-time on the last day of each month to calculate the caseload of that month' "
    "(note 14); 'The caseload measure counts an individual only once' (note 13)."
)
CSP_TABLE = MonthlyTable(
    "Table 9 Caseload",
    "Table 9: Carer Support Payment - Caseload by month",
    6,
    (
        ("All", "all"),
        ("New application", "new_applicant"),
        ("Case transfer", "case_transfer"),
    ),
    "Month",
    "Total Caseload",
    (
        ("in_payment", "In Payment", {"carer_support_payment_status": "in_payment"}),
        (
            "underlying_entitlement",
            "Underlying entitlement",
            {"carer_support_payment_status": "underlying_entitlement"},
        ),
    ),
)
CSP_AGE_BANDS = (
    ("Under 18", "under_18"),
    ("18-24", "18_to_24"),
    ("25-29", "25_to_29"),
    ("30-34", "30_to_34"),
    ("35-39", "35_to_39"),
    ("40-44", "40_to_44"),
    ("45-49", "45_to_49"),
    ("50-54", "50_to_54"),
    ("55-59", "55_to_59"),
    ("60-64", "60_to_64"),
    ("65 and over", "65_and_over"),
)
CSP_NOTE_QUOTES = (
    "From 20 November 2023, Carer Support Payment opened for new applications in the pilot "
    "areas of Dundee City, Na h-Eileanan Siar and Perth and Kinross. On 24 June 2024, Carer "
    "Support Payment launched in the three further pilot local authority areas of Angus, "
    "North Lanarkshire and South Lanarkshire. Carer Support Payment was rolled out to seven "
    "additional areas from August, and was made available nationally from 4 November 2024.",
    "Figures are rounded for disclosure control and may not sum due to rounding.",
    "The caseload measure counts an individual only once.",
    "Underlying entitlement or In payment for the caseload calculation is based on the "
    "status of an individual as on the last day of each month.",
    "This is a derived statistic calculated based on identifying all cases who are in "
    "receipt of, or have been approved for, a payment in the caseload period, even if they "
    "have not been paid yet.",
)


def build_csp() -> str:
    entry, content = pinned(CSP_DIRECTORY)
    grid = grid_of(source_cells_from_xlsx(content, metadata(entry["filename"])))
    notes = squeeze(" ".join(str(v) for (s, _, _), v in grid.items() if s == "Notes"))
    for quote in CSP_NOTE_QUOTES:
        assert squeeze(quote) in notes, quote
    assert grid[("Contents", 1, "A")] == "Carer Support Payment as at 30 June 2026"
    tally = Tally()
    record_sets, values = monthly_record_sets(
        grid,
        CSP_TABLE,
        package_slug="carer_support_payment_june_2026",
        groupby="scotgov.carer_support_payment_month",
        concept="scotgov.carer_support_payment_caseload",
        role="carer",
        page=CSP_PAGE,
        benefit="Carer Support Payment",
        caseload_note=CSP_CASELOAD_NOTE,
        tally=tally,
    )
    check_routes(values, tally, "Table 9")
    for key, cells in values.items():
        tally.gap(
            "Table 9: in payment and underlying entitlement add to the caseload",
            [cells["in_payment"], cells["underlying_entitlement"]],
            cells["caseload"],
        )
    latest = max(month for _, month in values)
    assert latest == date(2026, 6, 1)
    latest_caseload = values[("all", latest)]["caseload"]
    age_rows, age_total, _ = age_table(
        grid,
        sheet="Table 11 Caseload by age",
        title_start="Table 11: Carer Support Payment - Caseload at 30 June 2026 by age",
        header=("Client age group", "Total Caseload"),
        bands=CSP_AGE_BANDS,
        tally=tally,
        name="Table 11",
    )
    assert age_total == latest_caseload
    record_sets.append(
        snapshot_record_set(
            record_set_id="scotgov.carer_support_payment_june_2026.table_11_caseload_by_age.2026_06",
            sheet="Table 11 Caseload by age",
            rows=age_rows,
            month=latest,
            label="30 June 2026",
            notes=CSP_CASELOAD_NOTE,
            groupby="age_band",
            role="carer",
            measure=snapshot_measure(
                sheet="Table 11 Caseload by age",
                header="Total Caseload",
                concept="scotgov.carer_support_payment_caseload",
                page=CSP_PAGE,
                benefit="Carer Support Payment",
                what="carers in receipt on 30 June 2026 by age group.",
            ),
        )
    )
    council_rows_, council_total, _, _ = council_table(
        grid,
        sheet="Table 10 Caseload by LA",
        title_start="Table 10: Carer Support Payment - Caseload at 30 June 2026 by local authority",
        header=("Local authority", "Total Caseload"),
        tally=tally,
        name="Table 10",
    )
    assert council_total == latest_caseload
    record_sets.append(
        snapshot_record_set(
            record_set_id="scotgov.carer_support_payment_june_2026.table_10_caseload_by_council.2026_06",
            sheet="Table 10 Caseload by LA",
            rows=council_rows_,
            month=latest,
            label="30 June 2026",
            notes=CSP_CASELOAD_NOTE,
            groupby="geography",
            role="carer",
            measure=snapshot_measure(
                sheet="Table 10 Caseload by LA",
                header="Total Caseload",
                concept="scotgov.carer_support_payment_caseload",
                page=CSP_PAGE,
                benefit="Carer Support Payment",
                what="carers in receipt on 30 June 2026 by council area.",
            ),
        )
    )
    payload = package_payload(
        package_id="scotgov-carer-support-payment-caseload-june-2026",
        label=(
            "Social Security Scotland: Carer Support Payment caseload in payment and with "
            "underlying entitlement by type of client, April 2024 to June 2026, and by age and "
            "council area at 30 June 2026"
        ),
        record_sets=record_sets,
        artifact=artifact(
            CSP_DIRECTORY,
            entry,
            "Carer Support Payment statistics to 30 June 2026, Tables 9 to 11",
            "carer_support_payment_statistics_2026_08_11",
        ),
    )
    header = f"""
    Social Security Scotland, 'Carer Support Payment statistics and Carer's Allowance
    Supplement statistics to 30 June 2026' (published 11 August 2026, {CSP_PAGE}), the
    caseload tables, for {ISSUE} item 7 ({CONSUMERS}). Written by {SCRIPT} from the pinned
    workbook. Statistics producer: Social Security Scotland, an executive agency of the
    Scottish Government, so the source id is scotgov.

    Ported: Table 9's total caseload and its carers in payment and with underlying
    entitlement ('Underlying entitlement or In payment for the caseload calculation is based
    on the status of an individual as on the last day of each month', note 15), each month
    from April 2024 to June 2026, for all clients, new applications and case transfers; and
    at 30 June 2026, Table 11's caseload by age group and Table
    10's by council area. All as concept scotgov.carer_support_payment_caseload, carers, at
    Scotland or the council's code. Tables 10 and 11's totals are Table 9's June 2026
    caseload, ported once. Not ported: the percentage columns, November 2023 to March 2024
    (the pilot's first months), and Table 10's 'Other' row, which has no council code.

    Coverage grew over the ported months, as note 2 dates it: 'From 20 November 2023, Carer
    Support Payment opened for new applications in the pilot areas of Dundee City, Na
    h-Eileanan Siar and Perth and Kinross. On 24 June 2024, Carer Support Payment launched in
    the three further pilot local authority areas of Angus, North Lanarkshire and South
    Lanarkshire. Carer Support Payment was rolled out to seven additional areas from August,
    and was made available nationally from 4 November 2024.' So the months before November
    2024 count the pilot areas only, though they sit at Scotland's code, and November 2024's
    rise is the national launch, mostly case transfers.

    Semantics as published: {CSP_CASELOAD_NOTE} 'This is a derived statistic calculated based
    on identifying all cases who are in receipt of, or have been approved for, a payment in
    the caseload period, even if they have not been paid yet' (note 16). {ROUNDING}; a cell
    marked [c], suppressed for disclosure control, emits no fact ({tally.suppressed} in the
    ported rows).

    Parity, asserted by the generator within the rounding to the nearest 5; largest gaps:
    {format_gaps(tally)}. {fact_count(payload)} facts.
    """
    return render(header, payload)


# ---------------------------------------------------------------- Child Disability Payment

CDP_DIRECTORY = "scotgov/child_disability_payment_statistics_june_2026"
CDP_PAGE = SITE + "2026/08/child-disability-payment-statistics-to-30-june-2026"
CDP_CASELOAD_NOTE = (
    "'The caseload is based on a true point-in-time on the last day of each month to "
    "calculate the caseload of that month' (note 3); 'The total number of children in receipt "
    "measure counts an individual only once and can include children receiving care or "
    "mobility awards only or both' (note 4)."
)
CDP_TABLE = MonthlyTable(
    "T14 Caseload by award type",
    "Table 14: Caseload for Child Disability Payment by award type",
    6,
    (
        ("All", "all"),
        ("New Applicants", "new_applicant"),
        ("Case Transfers", "case_transfer"),
    ),
    "Month [note 3] [note 4] [note 5]",
    "Total number of children in receipt [note 4] [note 6]",
    (),
)


def build_cdp() -> str:
    entry, content = pinned(CDP_DIRECTORY)
    grid = grid_of(source_cells_from_xlsx(content, metadata(entry["filename"])))
    assert (
        grid[("Contents", 1, "A")]
        == "Child Disability Payment from 26 July 2021 to 30 June 2026"
    )
    sheet_notes = squeeze(
        " ".join(str(v) for (s, _, _), v in grid.items() if s == CDP_TABLE.sheet)
    )
    for quote in (
        "The caseload is based on a true point-in-time on the last day of each month to "
        "calculate the caseload of that month.",
        "The total number of children in receipt measure counts an individual only once and "
        "can include children receiving care or mobility awards only or both.",
        "Figures are rounded for disclosure control and may not sum due to rounding.",
    ):
        assert squeeze(quote) in sheet_notes, quote
    tally = Tally()
    record_sets, values = monthly_record_sets(
        grid,
        CDP_TABLE,
        package_slug="child_disability_payment_june_2026",
        groupby="scotgov.child_disability_payment_month",
        concept="scotgov.child_disability_payment_caseload",
        role="child",
        page=CDP_PAGE,
        benefit="Child Disability Payment",
        caseload_note=CDP_CASELOAD_NOTE,
        tally=tally,
    )
    check_routes(values, tally, "Table 14")
    assert max(month for _, month in values) == date(2026, 6, 1)
    payload = package_payload(
        package_id="scotgov-child-disability-payment-caseload-june-2026",
        label=(
            "Social Security Scotland: Child Disability Payment caseload by type of client, "
            "April 2024 to June 2026"
        ),
        record_sets=record_sets,
        artifact=artifact(
            CDP_DIRECTORY,
            entry,
            "Child Disability Payment statistics to 30 June 2026, Table 14",
            "child_disability_payment_statistics_2026_08_18",
        ),
    )
    header = f"""
    Social Security Scotland, 'Child Disability Payment statistics to 30 June 2026'
    (published 18 August 2026, {CDP_PAGE}), Table 14's caseload totals, for {ISSUE} item 7
    ({CONSUMERS}), which asks for the Child Disability Payment total. Written by {SCRIPT}
    from the pinned workbook. Statistics producer: Social Security Scotland, an executive
    agency of the Scottish Government, so the source id is scotgov.

    Ported: the total number of children in receipt, each month from April 2024 to June
    2026, for all clients, new applicants and case transfers, as concept
    scotgov.child_disability_payment_caseload at Scotland. Not ported: the table's award
    type columns and percentages, its months before April 2024, and the workbook's other
    caseload tables (care and mobility levels, age by single year and month, condition,
    council area), which #420 does not ask for.

    Semantics as published: {CDP_CASELOAD_NOTE} 'This is a derived statistic calculated based
    on identifying all cases who are in receipt of, or have been approved for, a payment in
    the caseload period, even if they have not been paid yet' (note 2). {ROUNDING}.

    Parity, asserted by the generator within the rounding to the nearest 5; largest gaps:
    {format_gaps(tally)}. {fact_count(payload)} facts.
    """
    return render(header, payload)


# ---------------------------------------------------------------- Pension Age Disability Payment

PADP_DIRECTORY = "scotgov/padp_statistics_july_2026"
PADP_PAGE = (
    SITE
    + "2026/09/pension-age-disability-payment-and-scottish-adult-disability-living-allowance-statistics-to-31-july-2026"
)
PADP_CASELOAD_NOTE = (
    "Pension Age Disability Payment caseload in the month; the workbook does not state the "
    "caseload's basis, which Social Security Scotland's other caseload tables give as a true "
    "point-in-time on the last day of the month."
)
PADP_TABLE = MonthlyTable(
    "T13 Caseload by award level",
    "Pension Age Disability Payment - Table 13: Caseload by month and award level",
    6,
    (
        ("All", "all"),
        ("New applicants", "new_applicant"),
        ("Case transfers", "case_transfer"),
    ),
    "Month",
    "Caseload",
    (),
)
PADP_NOTE_QUOTES = (
    "Figures are rounded for disclosure control and may not sum due to rounding.",
    "From 21 October 2024, Pension Age Disability Payment opened for new applications in the "
    "pilot areas of Argyll and Bute, Highland, Aberdeen City, Orkney Islands and Shetland "
    "Islands.",
    "As part of ongoing quality assurance work, we have identified two issues affecting "
    "caseload figures for case transfers.",
)


def build_padp() -> str:
    entry, content = pinned(PADP_DIRECTORY)
    grid = grid_of(source_cells_from_xlsx(content, metadata(entry["filename"])))
    notes = squeeze(" ".join(str(v) for (s, _, _), v in grid.items() if s == "Notes"))
    for quote in PADP_NOTE_QUOTES:
        assert squeeze(quote) in notes, quote
    assert (
        grid[("Contents", 1, "A")]
        == "Pension Age Disability Payment statistics to 31 July 2026"
    )
    tally = Tally()
    record_sets, values = monthly_record_sets(
        grid,
        PADP_TABLE,
        package_slug="padp_july_2026",
        groupby="scotgov.padp_month",
        concept="scotgov.padp_caseload",
        role="padp_client",
        page=PADP_PAGE,
        benefit="Pension Age Disability Payment",
        caseload_note=PADP_CASELOAD_NOTE,
        tally=tally,
    )
    check_routes(values, tally, "Table 13")
    months = sorted({month for _, month in values})
    assert months[0] == date(2024, 10, 1) and months[-1] == date(2026, 7, 1)
    payload = package_payload(
        package_id="scotgov-padp-caseload-july-2026",
        label=(
            "Social Security Scotland: Pension Age Disability Payment caseload by type of "
            "client, October 2024 to July 2026"
        ),
        record_sets=record_sets,
        artifact=artifact(
            PADP_DIRECTORY,
            entry,
            "Pension Age Disability Payment statistics to 31 July 2026, Table 13",
            "padp_statistics_2026_09_15",
        ),
    )
    header = f"""
    Social Security Scotland, 'Pension Age Disability Payment and Scottish Adult Disability
    Living Allowance statistics to 31 July 2026' (published 15 September 2026, {PADP_PAGE}),
    the Pension Age Disability Payment workbook's Table 13 caseload totals, for {ISSUE} item
    7 ({CONSUMERS}), which asks for the Pension Age Disability Payment total. Written by
    {SCRIPT} from the pinned workbook. Statistics producer: Social Security Scotland, an
    executive agency of the Scottish Government, so the source id is scotgov.

    Ported: the caseload each month from October 2024, when Pension Age Disability Payment
    opened ('From 21 October 2024, Pension Age Disability Payment opened for new
    applications in the pilot areas of Argyll and Bute, Highland, Aberdeen City, Orkney
    Islands and Shetland Islands', note 2; national from 22 April 2025), to July 2026, for
    all clients, new applicants and case transfers, as concept scotgov.padp_caseload at
    Scotland. Case transfers print 0 before they began;
    those published zeros are ported. Not ported: the higher and lower award levels and
    percentages, and the workbook's other caseload tables (age, condition, council area at
    31 July 2026), which #420 does not ask for.

    Semantics as published: {ROUNDING}. Note 37: 'As part of ongoing quality assurance work,
    we have identified two issues affecting caseload figures for case transfers. Some
    clients who had left the caseload, but then later received a backdated payment were
    still being counted on the caseload for the intervening months. Some clients who are
    missing an entitlement start date were not being counted on the caseload. Both issues
    have now been resolved.' The workbook's notes do not define the caseload's date basis.

    Parity, asserted by the generator within the rounding to the nearest 5; largest gaps:
    {format_gaps(tally)}. {fact_count(payload)} facts.
    """
    return render(header, payload)


# ---------------------------------------------------------------- the packages

BUILDERS = {
    "scotgov/adp_caseload_july_2026": build_adp,
    "scotgov/carer_support_payment_caseload_june_2026": build_csp,
    "scotgov/child_disability_payment_caseload_june_2026": build_cdp,
    "scotgov/padp_caseload_july_2026": build_padp,
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
