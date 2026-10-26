#!/usr/bin/env python3
"""Build the six ed_fsa source packages from the pinned FSA portfolio workbooks.

Every guard, header and label string is read from the workbook itself, so the
YAML cannot drift from the publisher bytes. The script selects publisher cells
and declares their units; it does not aggregate, reconcile, age or impute.

To refresh for a new FSA quarter, fetch the new workbooks into new
``db/data/ed_fsa/<package>`` directories, update the package names, row numbers
and quarter labels below, and rerun ``python packages/ed_fsa/build_packages.py``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import xlrd
import yaml

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "db" / "data" / "ed_fsa"
PACKAGES = ROOT / "packages" / "ed_fsa"
EVIDENCE_URL = "https://studentaid.gov/data-center/student/portfolio"

QUARTER_END = {
    "Q1": ("2025-12", "2025-12-31"),
    "Q2": ("2026-03", "2026-03-31"),
    "Q3": ("2026-06", "2026-06-30"),
}
QUARTER_NOTE = (
    "FSA labels the run by federal fiscal year and quarter (each federal fiscal "
    "year begins October 1; Q1 ends 12/31, Q2 ends 3/31, Q3 ends 6/30, Q4 ends "
    "9/30). The value is the outstanding level at the end of the quarter, not a "
    "flow over it."
)


class Workbook:
    def __init__(self, path: Path):
        self.book = xlrd.open_workbook(str(path))

    def raw(self, sheet: str, address: str):
        column = "".join(ch for ch in address if ch.isalpha())
        row = int("".join(ch for ch in address if ch.isdigit()))
        col_index = 0
        for ch in column:
            col_index = col_index * 26 + (ord(ch) - 64)
        cell = self.book.sheet_by_name(sheet).cell(row - 1, col_index - 1)
        if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
            return None
        if cell.ctype == xlrd.XL_CELL_NUMBER:
            value = float(cell.value)
            return int(value) if value.is_integer() else value
        return str(cell.value)

    def numeric(self, sheet: str, address: str) -> bool:
        value = self.raw(sheet, address)
        return isinstance(value, int | float) and not isinstance(value, bool)


def guard(book: Workbook, sheet: str, column: str, row: int, label: str) -> dict:
    value = book.raw(sheet, f"{column}{row}")
    if value is None:
        raise ValueError(f"Guard {sheet}!{column}{row} is empty")
    return {"column": column, "row": row, "expected_value": value, "label": label}


def next_col(column: str) -> str:
    return chr(ord(column) + 1)


@dataclass
class Category:
    value_id: str
    label: str
    column: str  # dollars column; count column is the next one
    constraints: list[dict] = field(default_factory=list)
    kind: str = "detail"
    heading_label: str = "publisher category heading"


@dataclass
class Measure:
    measure_id: str
    label: str
    concept: str
    unit: str
    value_scale: int
    source_concept: str
    notes: str
    offset: int  # 0 = dollars column, 1 = count column


def constraint(variable, operator, value, label, unit=None):
    out = {"variable": variable, "operator": operator, "value": value}
    if unit:
        out["unit"] = unit
    out["label"] = label
    return out


def eq(variable, value, label):
    return constraint(variable, "==", value, label)


def bounds(variable, lower, upper, label, unit):
    out = []
    if lower is not None:
        out.append(constraint(variable, ">=", lower, f"{label} lower bound", unit))
    if upper is not None:
        out.append(constraint(variable, "<", upper, f"{label} upper bound", unit))
    return out


def coverage(quarter: str) -> dict:
    month, end = QUARTER_END[quarter]
    return {
        "start_date": end,
        "end_date": end,
        "basis": "calendar",
        "source_period_label": f"Federal Fiscal Year 2026 {quarter}",
        "notes": QUARTER_NOTE,
    }


def wide_record_sets(
    *,
    book: Workbook,
    sheet: str,
    table_id: str,
    periods: list[tuple[int, str]],
    fy_row: int | None,
    category_row: int,
    measure_row: int,
    categories: list[Category],
    measures: list[Measure],
    common_guards: list[dict],
    groupby: str,
    entity_role: str,
    shared_constraints: list[dict],
    na_label: str = "recipients cell published as a marker, not a number",
) -> list[dict]:
    record_sets = []
    for row_number, quarter in periods:
        assert book.raw(sheet, f"B{row_number}") == quarter, (sheet, row_number)
        period_fy_row = fy_row if fy_row is not None else row_number
        assert book.raw(sheet, f"A{period_fy_row}") == 2026, (sheet, period_fy_row)
        fy_guard = {
            "column": "A",
            "row": period_fy_row,
            "expected_value": 2026,
            "label": "federal fiscal year",
        }
        if period_fy_row == row_number:
            fy_guard = {
                "column": "A",
                "expected_value": 2026,
                "label": "federal fiscal year",
            }
        month, _end = QUARTER_END[quarter]
        for measure in measures:
            rows = []
            na_guards: dict[str, list[dict]] = {}
            # A count cell FSA publishes as a marker (NA**, NA***) yields no
            # fact; guard the marker on the same category's dollars row.
            for category in categories:
                column = next_col(category.column)
                assert book.numeric(sheet, f"{category.column}{row_number}"), (
                    sheet,
                    category.column,
                    row_number,
                )
                if not book.numeric(sheet, f"{column}{row_number}"):
                    na_guards.setdefault(category.value_id, []).append(
                        {
                            "column": column,
                            "expected_value": book.raw(sheet, f"{column}{row_number}"),
                            "label": na_label,
                        }
                    )
            for ordinal, category in enumerate(categories):
                column = (
                    category.column
                    if measure.offset == 0
                    else next_col(category.column)
                )
                address = f"{column}{row_number}"
                if not book.numeric(sheet, address):
                    continue
                guards = [
                    guard(
                        book,
                        sheet,
                        category.column,
                        category_row,
                        category.heading_label,
                    ),
                    copy.deepcopy(fy_guard),
                ]
                if measure.offset == 0:
                    for g in na_guards.get(category.value_id, []):
                        if g["column"] != column:
                            guards.append(copy.deepcopy(g))
                guards.extend(copy.deepcopy(common_guards))
                row = {
                    "value_id": category.value_id,
                    "label": category.label,
                    "ordinal": ordinal,
                    "row_number": row_number,
                    "column": column,
                    "source_column_id": f"{category.value_id}.{measure.measure_id}",
                    "expected_row_header_column": "B",
                    "expected_row_header": quarter,
                    "expected_column_header_row": measure_row,
                    "expected_column_header": book.raw(sheet, f"{column}{measure_row}"),
                    "table_record_kind": category.kind,
                    "guard_cells": guards,
                }
                if category.constraints:
                    row["constraints"] = copy.deepcopy(category.constraints)
                rows.append(row)
            if not rows:
                continue
            record_set_id = (
                f"ed_fsa.{table_id}.fy2026_{quarter.lower()}.{measure.measure_id}"
            )
            record_set = {
                "record_set_id": record_set_id,
                "provenance_class": "administrative",
                "assertion": "observation",
                "record_set_spec_id": f"ed_fsa.{table_id}.{measure.measure_id}.v1",
                "source_record_id_prefix": record_set_id,
                "sheet_name": sheet,
                "period_type": "month",
                "period": month,
                "period_coverage": coverage(quarter),
                "geography_id": "0100000US",
                "geography_level": "country",
                "geography_name": "United States",
                "geography_vintage": "current",
                "entity": "person",
                "entity_role": entity_role,
                "domain": "federal_student_loans",
                "groupby_dimension": groupby,
            }
            if shared_constraints:
                record_set["shared_constraints"] = copy.deepcopy(shared_constraints)
            record_set["rows"] = rows
            record_set["measures"] = [
                {
                    "measure_id": measure.measure_id,
                    "label": measure.label,
                    "ordinal": 0,
                    "column": rows[0]["column"],
                    "source_column_id": measure.measure_id,
                    "concept": measure.concept,
                    "source_concept": measure.source_concept,
                    "concept_relation": "source_label",
                    "concept_authority": "ed_fsa",
                    "concept_evidence_url": EVIDENCE_URL,
                    "concept_evidence_notes": measure.notes,
                    "unit": measure.unit,
                    "aggregation": "sum",
                    "value_scale": measure.value_scale,
                    "expected_cell_type": "number",
                }
            ]
            record_sets.append(record_set)
    return record_sets


def artifact(table: str, vintage: str, resource_directory: str) -> dict:
    return {
        "source_name": "ed_fsa",
        "source_table": table,
        "resource_package": "db",
        "resource_directory": f"data/ed_fsa/{resource_directory}",
        "manifest": "manifest.yaml",
        "vintage": vintage,
        "extracted_at": "2026-10-12",
        "extraction_method": "XLS whole-workbook used-range cell parse",
        "parser": "xls_used_range",
    }


class Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def str_presenter(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


Dumper.add_representer(str, str_presenter)


def write_package(directory: str, header: str, payload: dict) -> int:
    path = PACKAGES / directory / "source_package.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.dump(
        payload, Dumper=Dumper, sort_keys=False, width=88, allow_unicode=True
    )
    generated = "# Generated by packages/ed_fsa/build_packages.py from the pinned workbook.\n#\n"
    path.write_text(generated + header + body, encoding="utf-8", newline="\n")
    facts = sum(len(rs["rows"]) * len(rs["measures"]) for rs in payload["record_sets"])
    print(
        f"{path.relative_to(ROOT).as_posix()}: {len(payload['record_sets'])} record "
        f"sets, {facts} facts"
    )
    return facts


def comment(text: str) -> str:
    return "".join(f"# {line}".rstrip() + "\n" for line in text.strip().splitlines())


STATE_FIPS = {
    "Alabama": "01",
    "Alaska": "02",
    "Arizona": "04",
    "Arkansas": "05",
    "California": "06",
    "Colorado": "08",
    "Connecticut": "09",
    "Delaware": "10",
    "District of Columbia": "11",
    "Florida": "12",
    "Georgia": "13",
    "Hawaii": "15",
    "Idaho": "16",
    "Illinois": "17",
    "Indiana": "18",
    "Iowa": "19",
    "Kansas": "20",
    "Kentucky": "21",
    "Louisiana": "22",
    "Maine": "23",
    "Maryland": "24",
    "Massachusetts": "25",
    "Michigan": "26",
    "Minnesota": "27",
    "Mississippi": "28",
    "Missouri": "29",
    "Montana": "30",
    "Nebraska": "31",
    "Nevada": "32",
    "New Hampshire": "33",
    "New Jersey": "34",
    "New Mexico": "35",
    "New York": "36",
    "North Carolina": "37",
    "North Dakota": "38",
    "Ohio": "39",
    "Oklahoma": "40",
    "Oregon": "41",
    "Pennsylvania": "42",
    "Puerto Rico": "72",
    "Rhode Island": "44",
    "South Carolina": "45",
    "South Dakota": "46",
    "Tennessee": "47",
    "Texas": "48",
    "Utah": "49",
    "Vermont": "50",
    "Virginia": "51",
    "Washington": "53",
    "West Virginia": "54",
    "Wisconsin": "55",
    "Wyoming": "56",
}
STATE_ABBR = {
    "Alabama": "al",
    "Alaska": "ak",
    "Arizona": "az",
    "Arkansas": "ar",
    "California": "ca",
    "Colorado": "co",
    "Connecticut": "ct",
    "Delaware": "de",
    "District of Columbia": "dc",
    "Florida": "fl",
    "Georgia": "ga",
    "Hawaii": "hi",
    "Idaho": "id",
    "Illinois": "il",
    "Indiana": "in",
    "Iowa": "ia",
    "Kansas": "ks",
    "Kentucky": "ky",
    "Louisiana": "la",
    "Maine": "me",
    "Maryland": "md",
    "Massachusetts": "ma",
    "Michigan": "mi",
    "Minnesota": "mn",
    "Mississippi": "ms",
    "Missouri": "mo",
    "Montana": "mt",
    "Nebraska": "ne",
    "Nevada": "nv",
    "New Hampshire": "nh",
    "New Jersey": "nj",
    "New Mexico": "nm",
    "New York": "ny",
    "North Carolina": "nc",
    "North Dakota": "nd",
    "Ohio": "oh",
    "Oklahoma": "ok",
    "Oregon": "or",
    "Pennsylvania": "pa",
    "Puerto Rico": "pr",
    "Rhode Island": "ri",
    "South Carolina": "sc",
    "South Dakota": "sd",
    "Tennessee": "tn",
    "Texas": "tx",
    "Utah": "ut",
    "Vermont": "vt",
    "Virginia": "va",
    "Washington": "wa",
    "West Virginia": "wv",
    "Wisconsin": "wi",
    "Wyoming": "wy",
}

LOCATION_HEADER = """
FSA Data Center, Federal Student Loan Portfolio: Portfolio-by-Location.xls,
balances and borrowers by borrower location, data as of Mar. 31, 2026 (federal
fiscal year 2026 Q2; the workbook publishes this one date only).

Included: all 54 published rows: the 50 states, the District of Columbia,
Puerto Rico, "Other" and "Not Reported". Balance in $ billions; borrowers in
thousands. The sheet has no total row, and Chronicle does not compute one.

Kept as published:
- "Not Reported" ($52.2 billion; 1,953.3 thousand borrowers) holds FFEL and
  Perkins loans whose commercial lenders are not required to report a current
  address. It is a statistical-scope row, not a geography, and is not
  allocated to states.
- "Other" is a borrower location the servicer reported outside the states and
  territories listed (also a statistical-scope row).
- Counts are borrowers (for parent PLUS, the parent), not recipients; balances
  exclude interest on school-held Perkins loans.
"""


def build_location() -> None:
    d = "portfolio_by_location_fy2026_q2"
    book = Workbook(DATA / d / "Portfolio-by-Location.xls")
    s = "PortfoliobyBorrowerLocation"
    defs = "Definitions"
    assert book.raw(s, "A4") == "Data as of Mar. 31, 2026"
    common = [
        guard(book, s, "A", 1, "table title"),
        guard(book, s, "A", 2, "balance definition"),
        guard(book, s, "A", 3, "data source"),
        guard(book, s, "A", 4, "data date"),
        guard(book, s, "A", 6, "location column heading"),
        guard(book, s, "A", 62, "Not Reported footnote"),
    ]
    universe = f"{book.raw(defs, 'A7')} {book.raw(defs, 'A8')} {book.raw(defs, 'A4')}"
    rows = []
    for ordinal, row_number in enumerate(range(7, 61)):
        name = book.raw(s, f"A{row_number}")
        if name in STATE_FIPS:
            geo = {
                "geography_id": f"0400000US{STATE_FIPS[name]}",
                "geography_level": "state",
            }
            value_id = STATE_ABBR[name]
        elif name == "Other":
            geo = {
                "geography_id": "ed_fsa:location_other",
                "geography_level": "statistical_scope",
            }
            value_id = "other"
        elif name == "Not Reported":
            geo = {
                "geography_id": "ed_fsa:location_not_reported",
                "geography_level": "statistical_scope",
            }
            value_id = "not_reported"
        else:
            raise ValueError(name)
        rows.append(
            {
                "value_id": value_id,
                "label": name,
                "ordinal": ordinal,
                "row_number": row_number,
                "expected_row_header_column": "A",
                "expected_row_header": name,
                **geo,
                "geography_name": name,
                "geography_vintage": "current",
                "table_record_kind": "total",
                "guard_cells": copy.deepcopy(common),
            }
        )
    assert len(rows) == 54 and book.raw(s, "A61") is None

    def measure(
        measure_id,
        label,
        ordinal,
        column,
        source_column_id,
        concept,
        source_concept,
        notes,
        unit,
        scale,
    ):
        return {
            "measure_id": measure_id,
            "label": label,
            "ordinal": ordinal,
            "column": column,
            "source_column_id": source_column_id,
            "expected_column_header_row": 6,
            "expected_column_header": book.raw(s, f"{column}6"),
            "concept": concept,
            "source_concept": source_concept,
            "concept_relation": "source_label",
            "concept_authority": "ed_fsa",
            "concept_evidence_url": EVIDENCE_URL,
            "concept_evidence_notes": notes,
            "unit": unit,
            "aggregation": "sum",
            "value_scale": scale,
            "expected_cell_type": "number",
        }

    record_set_id = "ed_fsa.portfolio_by_location.2026_03_31"
    record_sets = [
        {
            "record_set_id": record_set_id,
            "provenance_class": "administrative",
            "assertion": "observation",
            "record_set_spec_id": "ed_fsa.portfolio_by_location.v1",
            "source_record_id_prefix": record_set_id,
            "sheet_name": s,
            "period_type": "month",
            "period": "2026-03",
            "period_coverage": {
                "start_date": "2026-03-31",
                "end_date": "2026-03-31",
                "basis": "calendar",
                "source_period_label": book.raw(s, "A4"),
                "notes": (
                    "Outstanding level on the data date the sheet states (federal "
                    "fiscal year 2026, end of Q2), not a flow. " + book.raw(defs, "A4")
                ),
            },
            "geography_id": "0100000US",
            "geography_level": "country",
            "geography_name": "United States",
            "geography_vintage": "current",
            "entity": "person",
            "entity_role": "federal_student_loan_borrower",
            "domain": "federal_student_loans",
            "groupby_dimension": "ed_fsa.borrower_location",
            "rows": rows,
            "measures": [
                measure(
                    "dollars_outstanding",
                    "Dollars outstanding",
                    0,
                    "B",
                    "balance",
                    "ed_fsa.dollars_outstanding",
                    "Balance (in billions)",
                    f"{book.raw(defs, 'B12')} {universe}",
                    "usd",
                    1_000_000_000,
                ),
                measure(
                    "borrowers",
                    "Borrowers",
                    1,
                    "C",
                    "borrowers",
                    "ed_fsa.borrower_count",
                    "Borrowers (in thousands)",
                    f"{book.raw(defs, 'B13')} {book.raw(defs, 'B14').strip()} "
                    f"{book.raw(defs, 'B15')} {universe}",
                    "count",
                    1_000,
                ),
            ],
        }
    ]
    write_package(
        d,
        comment(LOCATION_HEADER),
        {
            "schema_version": "ledger.source_package.v1",
            "package_id": "ed-fsa-portfolio-by-location-fy2026-q2",
            "label": "FSA federal student loan portfolio by borrower location, March 31, 2026",
            "dimension_labels": {"ed_fsa.borrower_location": "Borrower location"},
            "artifact": artifact(
                "FSA Federal Student Loan Portfolio by Borrower Location",
                "fsa_portfolio_by_location_2026_03_31",
                d,
            ),
            "record_sets": record_sets,
        },
    )


def main() -> None:
    # ------------------------------------------------------------------ summary
    d = "portfolio_summary_fy2026_q3"
    book = Workbook(DATA / d / "PortfolioSummary.xls")
    s = "PortfolioSummary"
    common = [
        guard(book, s, "A", 1, "table title"),
        guard(book, s, "A", 2, "balance definition"),
        guard(book, s, "A", 3, "data source"),
        guard(book, s, "A", 6, "fiscal-year column heading"),
        guard(book, s, "A", 69, "notes heading after the last published quarter"),
        guard(book, s, "A", 71, "quarter-end definition"),
    ]
    dollars_notes = (
        f"{book.raw(s, 'A2')}. "
        f'Note 1: "{book.raw(s, "A70")}" Note 2: "{book.raw(s, "A71")}"'
    )
    recipient_notes = f'Note 3: "{book.raw(s, "A72")}"'
    programs = [
        Category(
            "direct_loans",
            "Direct Loans",
            "C",
            [
                eq(
                    "federal_student_loan_program",
                    "direct_loans",
                    "Federal student loan program",
                )
            ],
            heading_label="publisher loan program heading",
        ),
        Category(
            "ffel",
            "Federal Family Education Loans (FFEL)",
            "E",
            [
                eq(
                    "federal_student_loan_program",
                    "ffel",
                    "Federal student loan program",
                )
            ],
            heading_label="publisher loan program heading",
        ),
        Category(
            "perkins",
            "Perkins Loans",
            "G",
            [
                eq(
                    "federal_student_loan_program",
                    "perkins",
                    "Federal student loan program",
                )
            ],
            heading_label="publisher loan program heading",
        ),
    ]
    total = Category(
        "all", "Total", "I", kind="total", heading_label="publisher total heading"
    )
    periods = [(65, "Q1"), (66, "Q2"), (67, "Q3")]
    dollars = Measure(
        "dollars_outstanding",
        "Dollars outstanding",
        "ed_fsa.dollars_outstanding",
        "usd",
        1_000_000_000,
        "Dollars Outstanding (in billions)",
        dollars_notes,
        0,
    )
    recipients = Measure(
        "recipients",
        "Recipients",
        "ed_fsa.recipient_count",
        "count",
        1_000_000,
        "Recipients (in millions)",
        recipient_notes,
        1,
    )
    unduplicated = Measure(
        "unduplicated_recipients",
        "Unduplicated recipients",
        "ed_fsa.unduplicated_recipient_count",
        "count",
        1_000_000,
        "Unduplicated Recipients (in millions)",
        recipient_notes
        + " The Total column counts each recipient once across loan programs.",
        1,
    )
    kwargs = dict(
        book=book,
        sheet=s,
        table_id="portfolio_summary",
        periods=periods,
        fy_row=65,
        category_row=5,
        measure_row=6,
        common_guards=common,
        groupby="ed_fsa.loan_program",
        entity_role="federal_student_loan_recipient",
        shared_constraints=[],
    )
    record_sets = []
    # Interleave per period: dollars (programs + total), recipients, unduplicated.
    for period in periods:
        k = dict(kwargs, periods=[period])
        record_sets += wide_record_sets(
            **k, categories=programs + [total], measures=[dollars]
        )
        record_sets += wide_record_sets(**k, categories=programs, measures=[recipients])
        record_sets += wide_record_sets(
            **k, categories=[total], measures=[unduplicated]
        )
    header = comment(
        """
Federal Student Aid (FSA) Data Center, Federal Student Loan Portfolio:
PortfolioSummary.xls, the federal student loan portfolio by loan program.

Included: the three FY2026 quarterly runs (Q1 ends Dec 31, 2025; Q2 ends Mar 31,
2026; Q3 ends Jun 30, 2026, the latest published), for Direct Loans, FFEL,
Perkins and the Total column: dollars outstanding ($ billions) and recipients
(millions; the Total column is "Unduplicated Recipients").
Excluded: FY2007 to FY2025 rows. They remain in the parsed source cells.

Chronicle stores the published levels: no aging, no reconciliation across FSA
tables, and the Total is not recomputed from its parts (footnote 1: totals may
not equal the sum due to rounding and data-run timing). FSA counts recipients
(the student who benefits; for parent PLUS the child, not the parent borrower).
Each fact's period is the quarter-end month, with the FSA fiscal quarter label
in period_coverage.
"""
    )
    write_package(
        d,
        header,
        {
            "schema_version": "ledger.source_package.v1",
            "package_id": "ed-fsa-portfolio-summary-fy2026-q3",
            "label": "FSA federal student loan portfolio summary, FY2026 Q1 to Q3",
            "dimension_labels": {"ed_fsa.loan_program": "Loan program"},
            "artifact": artifact(
                "FSA Federal Student Aid Portfolio Summary",
                "fsa_portfolio_summary_fy2026_q3",
                d,
            ),
            "record_sets": record_sets,
        },
    )

    # -------------------------------------------------------------- location
    build_location()

    # ------------------------------------------------------------- loan type
    d = "portfolio_by_loan_type_fy2026_q3"
    book = Workbook(DATA / d / "PortfoliobyLoanType.xls")
    s = "PortfoliobyLoanType"
    common = [
        guard(book, s, "A", 1, "table title"),
        guard(book, s, "A", 2, "balance definition"),
        guard(book, s, "A", 3, "data source"),
        guard(book, s, "A", 7, "fiscal-year column heading"),
        guard(book, s, "A", 59, "notes heading after the last published quarter"),
        guard(book, s, "A", 61, "quarter-end definition"),
    ]
    dollars_notes = f'{book.raw(s, "A2")}. Note 1: "{book.raw(s, "A60")}" Note 2: "{book.raw(s, "A61")}"'
    recipient_notes = (
        f'Note 3: "{book.raw(s, "A62")}" Note 4: "{book.raw(s, "A63").strip()}"'
    )

    def lt(value):
        return [eq("federal_student_loan_type", value, "Federal student loan type")]

    types = [
        Category(
            "stafford_subsidized",
            "Stafford Subsidized",
            "C",
            lt("stafford_subsidized"),
            heading_label="publisher loan type heading",
        ),
        Category(
            "stafford_unsubsidized",
            "Stafford Unsubsidized",
            "E",
            lt("stafford_unsubsidized"),
            heading_label="publisher loan type heading",
        ),
        Category(
            "grad_plus",
            "Grad PLUS",
            "I",
            lt("grad_plus"),
            heading_label="publisher loan type heading",
        ),
        Category(
            "parent_plus",
            "Parent PLUS",
            "K",
            lt("parent_plus"),
            heading_label="publisher loan type heading",
        ),
        Category(
            "perkins",
            "Perkins",
            "M",
            lt("perkins"),
            heading_label="publisher loan type heading",
        ),
        Category(
            "consolidation",
            "Consolidation",
            "O",
            lt("consolidation"),
            heading_label="publisher loan type heading",
        ),
    ]
    stafford = Category(
        "stafford_combined",
        "Stafford (Combined)",
        "G",
        [
            eq(
                "federal_student_loan_type_group",
                "stafford",
                "Federal student loan type group",
            )
        ],
        kind="subtotal",
        heading_label="publisher loan type heading",
    )
    periods = [(55, "Q1"), (56, "Q2"), (57, "Q3")]
    dollars = Measure(
        "dollars_outstanding",
        "Dollars outstanding",
        "ed_fsa.dollars_outstanding",
        "usd",
        1_000_000_000,
        "Dollars Outstanding (in billions)",
        dollars_notes,
        0,
    )
    recipients = Measure(
        "recipients",
        "Recipients",
        "ed_fsa.recipient_count",
        "count",
        1_000_000,
        "Recipients (in millions)",
        recipient_notes,
        1,
    )
    stafford_dollars = Measure(
        "stafford_combined_dollars_outstanding",
        "Stafford (Combined) dollars outstanding",
        "ed_fsa.dollars_outstanding",
        "usd",
        1_000_000_000,
        "Stafford (Combined) Dollars Outstanding (in billions)",
        dollars_notes,
        0,
    )
    stafford_unique = Measure(
        "stafford_combined_unique_recipients",
        "Stafford (Combined) unique recipients",
        "ed_fsa.unduplicated_recipient_count",
        "count",
        1_000_000,
        "Stafford (Combined) Unique Recipients (in millions)",
        recipient_notes,
        1,
    )
    kwargs = dict(
        book=book,
        sheet=s,
        table_id="portfolio_by_loan_type",
        fy_row=None,
        category_row=6,
        measure_row=7,
        common_guards=common,
        groupby="ed_fsa.loan_type",
        entity_role="federal_student_loan_recipient",
        shared_constraints=[],
    )
    record_sets = []
    for period in periods:
        k = dict(kwargs, periods=[period])
        record_sets += wide_record_sets(**k, categories=types, measures=[dollars])
        record_sets += wide_record_sets(**k, categories=types, measures=[recipients])
        record_sets += wide_record_sets(
            **k, categories=[stafford], measures=[stafford_dollars]
        )
        record_sets += wide_record_sets(
            **k, categories=[stafford], measures=[stafford_unique]
        )
    header = comment(
        """
FSA Data Center, Federal Student Loan Portfolio: PortfoliobyLoanType.xls.

Included: the three FY2026 quarterly runs (Q1 to Q3; Q3 ends Jun 30, 2026, the
latest published) for Stafford Subsidized, Stafford Unsubsidized, Grad PLUS,
Parent PLUS, Perkins and Consolidation (dollars outstanding in $ billions,
recipients in millions), and Stafford (Combined) in its own record sets because
its count is a unique Stafford recipient count, not a loan-level count.
Excluded: FY2014 Q2 to FY2025 Q4 rows. They remain in the parsed source cells.

FSA counts recipients at the loan level, so a person can be counted under more
than one loan type (note 4). No aging, no reconciliation to the Portfolio
Summary (note 1: totals may differ across portfolio reports).
"""
    )
    write_package(
        d,
        header,
        {
            "schema_version": "ledger.source_package.v1",
            "package_id": "ed-fsa-portfolio-by-loan-type-fy2026-q3",
            "label": "FSA federal student loan portfolio by loan type, FY2026 Q1 to Q3",
            "dimension_labels": {"ed_fsa.loan_type": "Loan type"},
            "artifact": artifact(
                "FSA Portfolio by Loan Type", "fsa_portfolio_by_loan_type_fy2026_q3", d
            ),
            "record_sets": record_sets,
        },
    )

    # ------------------------------------------------------------------- age
    d = "portfolio_by_age_fy2026_q2"
    book = Workbook(DATA / d / "Portfolio-by-Age.xls")
    s = "Portfolio by Age"
    common = [
        guard(book, s, "A", 1, "table title"),
        guard(book, s, "A", 2, "balance definition"),
        guard(book, s, "A", 3, "data source"),
        guard(book, s, "A", 6, "fiscal-year column heading"),
        guard(book, s, "A", 44, "notes heading after the last published quarter"),
    ]
    defs = "Definitions"
    universe = (
        f"{book.raw(defs, 'A8')} {book.raw(defs, 'A9')} {book.raw(defs, 'A4')} "
        f'Note: "{book.raw(s, "A45").strip()}"'
    )
    dollars_notes = f"{book.raw(defs, 'B19')} {universe}"
    borrower_notes = f"{book.raw(defs, 'B20')} {universe}"

    def age(lo, hi):
        return bounds("age", lo, hi, "Age", "years")

    bands = [
        Category(
            "age_24_and_younger",
            "24 and Younger",
            "C",
            age(None, 25),
            heading_label="publisher age band heading",
        ),
        Category(
            "age_25_to_34",
            "25 to 34",
            "E",
            age(25, 35),
            heading_label="publisher age band heading",
        ),
        Category(
            "age_35_to_49",
            "35 to 49",
            "G",
            age(35, 50),
            heading_label="publisher age band heading",
        ),
        Category(
            "age_50_to_61",
            "50 to 61",
            "I",
            age(50, 62),
            heading_label="publisher age band heading",
        ),
        Category(
            "age_62_and_older",
            "62 and Older",
            "K",
            age(62, None),
            heading_label="publisher age band heading",
        ),
        Category(
            "age_not_reported",
            "Not Reported",
            "M",
            [eq("age_reporting_status", "not_reported", "Age reporting status")],
            heading_label="publisher age band heading",
        ),
    ]
    periods = [(42, "Q1"), (43, "Q2")]
    dollars = Measure(
        "dollars_outstanding",
        "Dollars outstanding",
        "ed_fsa.dollars_outstanding",
        "usd",
        1_000_000_000,
        "Dollars Outstanding (in billions)",
        dollars_notes,
        0,
    )
    borrowers = Measure(
        "borrowers",
        "Borrowers",
        "ed_fsa.borrower_count",
        "count",
        1_000_000,
        "Borrowers (in millions)",
        borrower_notes,
        1,
    )
    record_sets = []
    for period in periods:
        k = dict(
            book=book,
            sheet=s,
            table_id="portfolio_by_age",
            periods=[period],
            fy_row=None,
            category_row=5,
            measure_row=6,
            common_guards=common,
            groupby="ed_fsa.borrower_age_band",
            entity_role="federal_student_loan_borrower",
            shared_constraints=[],
            categories=bands,
        )
        record_sets += wide_record_sets(**k, measures=[dollars])
        record_sets += wide_record_sets(**k, measures=[borrowers])
    header = comment(
        """
FSA Data Center, Federal Student Loan Portfolio: Portfolio-by-Age.xls,
balances and borrowers by borrower age at the end of the quarter.

Included: the FY2026 Q1 and Q2 runs (Q2 ends Mar 31, 2026, the latest
published) for all six published columns: 24 and Younger, 25 to 34, 35 to 49,
50 to 61, 62 and Older, and Not Reported. Dollars outstanding in $ billions;
borrowers in millions. Excluded: FY2017 Q2 to FY2025 Q4 rows, which remain in
the parsed source cells.

The table counts borrowers (for parent PLUS, the parent), not recipients, and
covers Direct Loan, FFEL and Perkins borrowers in an open loan status. The
Definitions sheet describes bands "Younger than 18" and "19 to 24" that the
table does not publish; the table's first band is "24 and Younger", so it has
no lower age bound here. Not Reported carries no age bound.
"""
    )
    write_package(
        d,
        header,
        {
            "schema_version": "ledger.source_package.v1",
            "package_id": "ed-fsa-portfolio-by-age-fy2026-q2",
            "label": "FSA federal student loan portfolio by borrower age, FY2026 Q1 and Q2",
            "dimension_labels": {"ed_fsa.borrower_age_band": "Borrower age"},
            "artifact": artifact(
                "FSA Federal Student Loan Portfolio by Borrower Age",
                "fsa_portfolio_by_age_fy2026_q2",
                d,
            ),
            "record_sets": record_sets,
        },
    )

    # ------------------------------------------------------------- debt size
    d = "portfolio_by_debt_size_fy2026_q2"
    book = Workbook(DATA / d / "Portfolio-by-Debt-Size.xls")
    s = "Portfolio by Debt Size"
    common = [
        guard(book, s, "A", 1, "table title"),
        guard(book, s, "A", 2, "balance definition"),
        guard(book, s, "A", 3, "data source"),
        guard(book, s, "A", 6, "fiscal-year column heading"),
        guard(book, s, "A", 44, "notes heading after the last published quarter"),
    ]
    universe = (
        f"{book.raw(defs, 'A8')} {book.raw(defs, 'A9')} {book.raw(defs, 'A4')} "
        f'Note: "{book.raw(s, "A45").strip()}"'
    )
    dollars_notes = f"{book.raw(defs, 'B21')} {universe}"
    borrower_notes = f"{book.raw(defs, 'B22')} {universe}"

    def bal(lo, hi):
        return bounds(
            "federal_student_loan_balance",
            lo,
            hi,
            "Federal student loan balance",
            "usd",
        )

    bands = [
        Category("debt_less_than_5k", "Less than 5K", "C", bal(None, 5_000)),
        Category("debt_5k_to_10k", "5K to 10K", "E", bal(5_000, 10_000)),
        Category("debt_10k_to_20k", "10K to 20K", "G", bal(10_000, 20_000)),
        Category("debt_20k_to_40k", "20K to 40K", "I", bal(20_000, 40_000)),
        Category("debt_40k_to_60k", "40K to 60K", "K", bal(40_000, 60_000)),
        Category("debt_60k_to_80k", "60K to 80K", "M", bal(60_000, 80_000)),
        Category("debt_80k_to_100k", "80K to 100K", "O", bal(80_000, 100_000)),
        Category("debt_100k_to_200k", "100K to 200K", "Q", bal(100_000, 200_000)),
        Category("debt_200k_plus", "200K+", "S", bal(200_000, None)),
    ]
    for band in bands:
        band.heading_label = "publisher debt-size band heading"
    periods = [(42, "Q1"), (43, "Q2")]
    dollars = Measure(
        "dollars_outstanding",
        "Dollars outstanding",
        "ed_fsa.dollars_outstanding",
        "usd",
        1_000_000_000,
        "Dollars Outstanding (in billions)",
        dollars_notes,
        0,
    )
    borrowers = Measure(
        "borrowers",
        "Borrowers",
        "ed_fsa.borrower_count",
        "count",
        1_000_000,
        "Borrowers (in millions)",
        borrower_notes,
        1,
    )
    record_sets = []
    for period in periods:
        k = dict(
            book=book,
            sheet=s,
            table_id="portfolio_by_debt_size",
            periods=[period],
            fy_row=None,
            category_row=5,
            measure_row=6,
            common_guards=common,
            groupby="ed_fsa.borrower_debt_size",
            entity_role="federal_student_loan_borrower",
            shared_constraints=[],
            categories=bands,
        )
        record_sets += wide_record_sets(**k, measures=[dollars])
        record_sets += wide_record_sets(**k, measures=[borrowers])
    header = comment(
        """
FSA Data Center, Federal Student Loan Portfolio: Portfolio-by-Debt-Size.xls,
balances and borrowers by the borrower's total federal student loan balance.

Included: the FY2026 Q1 and Q2 runs (Q2 ends Mar 31, 2026, the latest
published) for the nine published bands, Less than 5K to 200K+. Dollars
outstanding in $ billions; borrowers in millions. Band bounds follow the
Definitions sheet ("$5,000 or more and less than $10,000"). Excluded: FY2017
Q2 to FY2025 Q4 rows, which remain in the parsed source cells.

The table counts borrowers (for parent PLUS, the parent). The table heads two
bands "80K-100K" and "100K to 200K" where the Definitions sheet writes
"80K to 100K" and "100K-200K"; guards keep the table's spelling and the row
labels use the "to" form for both.
"""
    )
    write_package(
        d,
        header,
        {
            "schema_version": "ledger.source_package.v1",
            "package_id": "ed-fsa-portfolio-by-debt-size-fy2026-q2",
            "label": "FSA federal student loan portfolio by borrower debt size, FY2026 Q1 and Q2",
            "dimension_labels": {"ed_fsa.borrower_debt_size": "Borrower debt size"},
            "artifact": artifact(
                "FSA Federal Student Loan Portfolio by Borrower Debt Size",
                "fsa_portfolio_by_debt_size_fy2026_q2",
                d,
            ),
            "record_sets": record_sets,
        },
    )

    # -------------------------------------------------------- repayment plan
    d = "dl_portfolio_by_repayment_plan_fy2026_q3"
    book = Workbook(DATA / d / "DLPortfoliobyRepaymentPlan.xls")
    universe_note = f'"{book.raw(defs, "A7")}" "{book.raw(defs, "A4")}"'
    recipient_note = f'"{book.raw(defs, "A8")}" {book.raw(defs, "B23")}'
    status = eq(
        "federal_student_loan_status_group",
        "repayment_deferment_forbearance",
        "Federal student loan status group",
    )

    def plan(value_id, label, column):
        return Category(
            value_id,
            label,
            column,
            [
                eq(
                    "federal_student_loan_repayment_plan",
                    value_id,
                    "Federal student loan repayment plan",
                )
            ],
            heading_label="publisher repayment plan heading",
        )

    def pfh(value_id, label, column, plan_id, hardship):
        return Category(
            value_id,
            label,
            column,
            [
                eq(
                    "federal_student_loan_repayment_plan",
                    plan_id,
                    "Federal student loan repayment plan",
                ),
                eq(
                    "federal_student_loan_partial_financial_hardship",
                    hardship,
                    "Partial financial hardship",
                ),
            ],
            heading_label="publisher repayment plan heading",
        )

    level = [
        plan("level_10_years_or_less", "Level: 10 years or less", "C"),
        plan("level_over_10_years", "Level: over 10 years", "E"),
        plan("graduated_10_years_or_less", "Graduated: 10 years or less", "G"),
        plan("graduated_over_10_years", "Graduated: over 10 years", "I"),
    ]
    sheets = [
        (
            "DLPortfoliobyRepaymentPlan",
            "dl_by_repayment_plan",
            "direct_loan",
            [(58, "Q1"), (59, "Q2"), (60, "Q3")],
            58,
            62,
            level
            + [
                plan("income_contingent", "Income-Contingent", "K"),
                plan("income_based", "Income-Based", "M"),
                plan("pay_as_you_earn", "Pay As You Earn", "O"),
                plan("save", "SAVE", "Q"),
                plan("alternative", "Alternative", "S"),
                plan("other", "Other", "U"),
            ],
            "ed_fsa.repayment_plan",
        ),
        (
            "DL-IDRbyPFH",
            "dl_idr_by_partial_financial_hardship",
            "direct_loan",
            [(50, "Q1"), (51, "Q2"), (52, "Q3")],
            50,
            None,
            [
                pfh(
                    "income_based_with_pfh",
                    "Income-Based Repayment with Partial Financial Hardship",
                    "C",
                    "income_based",
                    "with_partial_financial_hardship",
                ),
                pfh(
                    "income_based_without_pfh",
                    "Income-Based Repayment without Partial Financial Hardship",
                    "E",
                    "income_based",
                    "without_partial_financial_hardship",
                ),
                pfh(
                    "pay_as_you_earn_with_pfh",
                    "Pay As You Earn with Partial Financial Hardship",
                    "G",
                    "pay_as_you_earn",
                    "with_partial_financial_hardship",
                ),
                pfh(
                    "pay_as_you_earn_without_pfh",
                    "Pay As You Earn without Partial Financial Hardship",
                    "I",
                    "pay_as_you_earn",
                    "without_partial_financial_hardship",
                ),
            ],
            "ed_fsa.repayment_plan_hardship",
        ),
        (
            "ED-HeldFFELbyRepaymentPlan",
            "ed_held_ffel_by_repayment_plan",
            "ed_held_ffel",
            [(48, "Q1"), (49, "Q2"), (50, "Q3")],
            48,
            52,
            level
            + [
                plan("income_sensitive", "Income-Sensitive", "K"),
                plan("income_based", "Income-Based", "M"),
                plan("alternative", "Alternative", "O"),
                plan("other", "Other", "Q"),
            ],
            "ed_fsa.repayment_plan",
        ),
        (
            "ED-HeldFFEL-IDRbyPFH",
            "ed_held_ffel_idr_by_partial_financial_hardship",
            "ed_held_ffel",
            [(48, "Q1"), (49, "Q2"), (50, "Q3")],
            48,
            None,
            [
                pfh(
                    "income_based_with_pfh",
                    "Income-Based Repayment with Partial Financial Hardship",
                    "C",
                    "income_based",
                    "with_partial_financial_hardship",
                ),
                pfh(
                    "income_based_without_pfh",
                    "Income-Based Repayment without Partial Financial Hardship",
                    "E",
                    "income_based",
                    "without_partial_financial_hardship",
                ),
            ],
            "ed_fsa.repayment_plan_hardship",
        ),
        (
            "FedManagedPortbyRepaymentPlan",
            "federally_managed_by_repayment_plan",
            "federally_managed",
            [(45, "Q1"), (46, "Q2"), (47, "Q3")],
            45,
            49,
            level
            + [
                plan("income_contingent", "Income-Contingent", "K"),
                plan("income_sensitive", "Income-Sensitive", "M"),
                plan("income_based", "Income-Based", "O"),
                plan("pay_as_you_earn", "Pay As You Earn", "Q"),
                plan("save", "SAVE", "S"),
                plan("alternative", "Alternative", "U"),
                plan("other", "Other", "W"),
            ],
            "ed_fsa.repayment_plan",
        ),
        (
            "FedManaged-IDRbyPFH",
            "federally_managed_idr_by_partial_financial_hardship",
            "federally_managed",
            [(45, "Q1"), (46, "Q2"), (47, "Q3")],
            45,
            None,
            [
                pfh(
                    "income_based_with_pfh",
                    "Income-Based Repayment with Partial Financial Hardship",
                    "C",
                    "income_based",
                    "with_partial_financial_hardship",
                ),
                pfh(
                    "income_based_without_pfh",
                    "Income-Based Repayment without Partial Financial Hardship",
                    "E",
                    "income_based",
                    "without_partial_financial_hardship",
                ),
                pfh(
                    "pay_as_you_earn_with_pfh",
                    "Pay As You Earn with Partial Financial Hardship",
                    "G",
                    "pay_as_you_earn",
                    "with_partial_financial_hardship",
                ),
                pfh(
                    "pay_as_you_earn_without_pfh",
                    "Pay As You Earn without Partial Financial Hardship",
                    "I",
                    "pay_as_you_earn",
                    "without_partial_financial_hardship",
                ),
            ],
            "ed_fsa.repayment_plan_hardship",
        ),
    ]
    portfolio_labels = {
        "direct_loan": "Federal student loan portfolio",
        "ed_held_ffel": "Federal student loan portfolio",
        "federally_managed": "Federal student loan portfolio",
    }
    record_sets = []
    for (
        sheet,
        table_id,
        portfolio,
        periods,
        fy_row,
        notes_row,
        categories,
        groupby,
    ) in sheets:
        common = [
            guard(book, sheet, "A", 1, "table title"),
            guard(book, sheet, "A", 2, "portfolio and loan-status universe"),
            guard(book, sheet, "A", 3, "data source"),
            guard(book, sheet, "A", 7, "fiscal-year column heading"),
        ]
        if notes_row:
            common.append(
                guard(
                    book,
                    sheet,
                    "A",
                    notes_row,
                    "notes heading after the last published quarter",
                )
            )
        dollars_notes = (
            f"{book.raw(sheet, 'A2')}. {book.raw(defs, 'B22')} {universe_note}"
        )
        recipient_notes = f"{book.raw(sheet, 'A2')}. {recipient_note} {universe_note}"
        dollars = Measure(
            "dollars_outstanding",
            "Dollars outstanding",
            "ed_fsa.dollars_outstanding",
            "usd",
            1_000_000_000,
            "Dollars Outstanding (in billions)",
            dollars_notes,
            0,
        )
        recipients = Measure(
            "recipients",
            "Recipients",
            "ed_fsa.recipient_count",
            "count",
            1_000_000,
            "Recipients (in millions)",
            recipient_notes,
            1,
        )
        shared = [
            eq(
                "federal_student_loan_portfolio", portfolio, portfolio_labels[portfolio]
            ),
            copy.deepcopy(status),
        ]
        for period in periods:
            k = dict(
                book=book,
                sheet=sheet,
                table_id=table_id,
                periods=[period],
                fy_row=fy_row,
                category_row=6,
                measure_row=7,
                common_guards=common,
                groupby=groupby,
                entity_role="federal_student_loan_recipient",
                shared_constraints=shared,
                categories=categories,
            )
            record_sets += wide_record_sets(**k, measures=[dollars])
            record_sets += wide_record_sets(**k, measures=[recipients])
    header = comment(
        """
FSA Data Center, Federal Student Loan Portfolio: DLPortfoliobyRepaymentPlan.xls,
balances and recipients by repayment plan for loans in repayment, deferment and
forbearance (default, in-school and grace are excluded).

Included: the FY2026 Q1 to Q3 runs (Q3 ends Jun 30, 2026, the latest
published) of all six data sheets: Direct Loans by plan, Direct Loan IBR and
PAYE by partial financial hardship, ED-held FFEL by plan, ED-held FFEL IBR by
partial financial hardship, the federally managed portfolio (Direct Loans plus
ED-held FFEL) by plan, and its IBR and PAYE by partial financial hardship.
Dollars outstanding in $ billions; recipients in millions. Excluded: earlier
quarters (from FY2013 Q3), which remain in the parsed source cells.

Kept as published:
- Recipient counts are loan-level, so a recipient can be counted under more
  than one plan or status.
- The latest quarter ends Jun 30, 2026, before RAP launched on Jul 1, 2026, so
  no sheet has a RAP column.
- Direct Loan "Other" recipients read "NA***" and ED-held FFEL "Other"
  recipients read "NA**" in every FY2026 quarter, as does the federally managed
  "Other" recipients cell for Q1 (Q2 and Q3 publish 0.09). The workbook does
  not define the asterisks. No fact is emitted for these cells; a guard on the
  matching dollars row records the marker.
- The three portfolios overlap: the federally managed sheet covers Direct
  Loans and ED-held FFEL together.
"""
    )
    write_package(
        d,
        header,
        {
            "schema_version": "ledger.source_package.v1",
            "package_id": "ed-fsa-dl-portfolio-by-repayment-plan-fy2026-q3",
            "label": "FSA federal student loan portfolio by repayment plan, FY2026 Q1 to Q3",
            "dimension_labels": {
                "ed_fsa.repayment_plan": "Repayment plan",
                "ed_fsa.repayment_plan_hardship": "Repayment plan and partial financial hardship",
            },
            "artifact": artifact(
                "FSA Direct Loan Portfolio by Repayment Plan",
                "fsa_dl_portfolio_by_repayment_plan_fy2026_q3",
                d,
            ),
            "record_sets": record_sets,
        },
    )


if __name__ == "__main__":
    main()
