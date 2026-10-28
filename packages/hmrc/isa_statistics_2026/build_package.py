#!/usr/bin/env python3
"""Author the HMRC annual savings statistics 2026 packages (PolicyEngine/microcosm#1415).

Writes three source packages from the bytes their manifests pin under ``db/data``.
Nothing is downloaded and no value is computed:

- ``hmrc-isa-statistics-2026``: ISA Tables 9.4, 9.6 and 9.7 to 9.12 (September 2026);
- ``hmrc-lisa-statistics-2026``: Lifetime ISA Table 1a, yearly withdrawals;
- ``hmrc-cash-isa-limit-reduction-2026``: the cash ISA limit impact note's shares of
  under-65 cash ISA subscribers either side of GBP 12,000 in 2022-23.

Every selector is located by matching the publisher's text in Chronicle's own parse of
the file, and every match is asserted, so a re-run against different bytes fails
rather than drifting.

Usage::

    uv run python packages/hmrc/isa_statistics_2026/build_package.py
    uv run python packages/hmrc/isa_statistics_2026/build_package.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import yaml

from chronicle.sources.cells import (
    SourceArtifactMetadata,
    source_cells_from_html_tables_and_text,
    source_cells_from_ods,
)

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[2]

RELEASE_URL = "https://www.gov.uk/government/statistics/annual-savings-statistics-2026"
METHODOLOGY_URL = (
    RELEASE_URL + "/annual-savings-statistics-background-and-methodology"
)
IMPACT_NOTE_URL = (
    "https://www.gov.uk/government/publications/"
    "reduction-in-the-cash-individual-savings-account-isa-limit/"
    "cash-individual-savings-account-isa-limit-reduction"
)

ISA_PACKAGE_ID = "hmrc-isa-statistics-2026"
ISA_DIR = "hmrc/isa_statistics_2026"
ISA_FILE = "Individual_Savings_Account_Tables_2026.ods"
ISA_SHA256 = "a0eaf90801fadc293c1187e8bcd66983b37a0fe81028d9a04b3e6dd71bd10e3b"
ISA_PREFIX = "hmrc.isa_statistics_2026"
ISA_SHEETS = (
    "Cover_Sheet",
    "Contents",
    "9_4_ISA_subscriptions",
    "9_6_ISA_market_values",
    "9_7_ISA_subs_by_income",
    "9_8_ISA_subs_by_age_sex",
    "9_9_ISA_subs_by_country_region",
    "9_10_ISA_market_values_income",
    "9_11ISA_market_value_by_age_sex",
    "9_12ISA_market_values_by_region",
)

LISA_PACKAGE_ID = "hmrc-lisa-statistics-2026"
LISA_DIR = "hmrc/lisa_statistics_2026"
LISA_FILE = "Lifetime_ISA_Tables_2026.ods"
LISA_SHA256 = "bba1520b58072a71ad90fd32992a3226ba3b54e806dc9330b132bb7136502231"
LISA_PREFIX = "hmrc.lisa_statistics_2026"
LISA_SHEETS = ("Cover_sheet", "Lifetime_ISA_sheet")

NOTE_PACKAGE_ID = "hmrc-cash-isa-limit-reduction-2026"
NOTE_DIR = "hmrc/cash_isa_limit_reduction_2026"
NOTE_FILE = "cash-individual-savings-account-isa-limit-reduction.html"
NOTE_SHA256 = "3a27fd6017afd85a1167e3acb3687d6312ea32c07f1101535f888279bd2c6212"
NOTE_PREFIX = "hmrc.cash_isa_limit_reduction_2026"

UK = {
    "geography_id": "K02000001",
    "geography_level": "country",
    "geography_name": "United Kingdom",
    "geography_vintage": "current",
}
DOMAIN = "individual_savings_accounts"
SURVEY = (
    "Survey of Personal Incomes matched to ISA managers' returns of individual "
    "accounts (ISACOMM100)"
)
THOUSANDS_HEADING = (
    "The column headings say '(thousands)', but the cells are counts of individuals: "
    "only that reading matches HMRC's commentary (13.05 million subscribers in "
    "2023 to 2024), so value_scale is 1."
)
TABLES_9_7_TO_9_12 = (
    "HMRC estimates Tables 9.7 to 9.12 from a sample of individuals' ISA accounts "
    "matched to the Survey of Personal Incomes and calibrated to the totals in "
    "Tables 9.4 and 9.6; income, age, sex and region come from the Survey of Personal "
    "Incomes. Innovative Finance ISA holders are not included."
)

# ---------------------------------------------------------------- parsing


def artifact_meta(path: Path) -> SourceArtifactMetadata:
    return SourceArtifactMetadata(
        source_name="hmrc",
        source_table=path.name,
        source_file=path.name,
        url=None,
        vintage="x",
        sha256="0",
        size_bytes=0,
        extracted_at="x",
        extraction_method="x",
    )


def pinned_bytes(directory: str, filename: str, sha256: str) -> tuple[Path, bytes]:
    path = REPO_ROOT / "db/data" / directory / filename
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    assert digest == sha256, f"{path} has SHA-256 {digest}, expected {sha256}"
    return path, content


def ods_sheets(
    directory: str, filename: str, sha256: str, expected_sheets: tuple[str, ...]
) -> dict[str, dict[tuple[int, str], object]]:
    """Map sheet -> (row, column letter) -> raw value, from Chronicle's own parse."""
    path, content = pinned_bytes(directory, filename, sha256)
    cells = source_cells_from_ods(
        content, artifact_meta(path), coerce_numeric_text=True
    )
    sheets: dict[str, dict[tuple[int, str], object]] = {}
    order: list[str] = []
    for cell in cells:
        if cell.sheet_name not in sheets:
            sheets[cell.sheet_name] = {}
            order.append(cell.sheet_name)
        if cell.raw_value in (None, ""):
            continue
        column = re.match(r"[A-Z]+", cell.address).group(0)
        sheets[cell.sheet_name][(cell.row_number, column)] = cell.raw_value
    assert tuple(order) == expected_sheets, order
    return sheets


def column_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def columns(first: str, count: int) -> list[str]:
    start = 0
    for char in first:
        start = start * 26 + ord(char) - 64
    return [column_letter(start + offset) for offset in range(count)]


def only_row(
    grid: dict, column: str, text: str, *, after: int = 0, before: int = 10**6
) -> int:
    rows = [
        row
        for (row, col), value in grid.items()
        if col == column and value == text and after < row < before
    ]
    assert len(rows) == 1, (column, text, after, before, rows)
    return rows[0]


def expect(grid: dict, row: int, column: str, value: object) -> None:
    assert grid.get((row, column)) == value, (row, column, grid.get((row, column)), value)


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def note_text(grid: dict, row: int) -> str:
    value = grid.get((row, "A"))
    assert isinstance(value, str), (row, value)
    return value


# ---------------------------------------------------------------- shapes


def constraint(
    variable: str, operator: str, value: object, label: str, unit: str | None = None
) -> dict:
    item = {"variable": variable, "operator": operator, "value": value}
    if unit is not None:
        item["unit"] = unit
    item["label"] = label
    return item


def category(variable: str, value: str, label: str) -> tuple[dict, list[dict]]:
    """A publisher category as a filter and, unless it is 'all', a constraint."""
    filters = {variable: value}
    constraints = [] if value == "all" else [constraint(variable, "==", value, label)]
    return filters, constraints


def money_band(label: str) -> tuple[int, int | None]:
    """'£1-£2,000' -> (1, 2000); '£20,000' -> (20000, 20000); '£150,001 or more' ->
    (150001, None)."""
    text = re.sub(r"\s*\(thousands\)$", "", label)
    match = re.fullmatch(r"£([\d,]+)-£([\d,]+)", text)
    if match:
        low, high = (int(part.replace(",", "")) for part in match.groups())
        assert low < high, label
        return low, high
    match = re.fullmatch(r"£([\d,]+) or more", text)
    if match:
        return int(match.group(1).replace(",", "")), None
    match = re.fullmatch(r"£([\d,]+)", text)
    assert match, label
    value = int(match.group(1).replace(",", ""))
    return value, value


def band_id(prefix: str, low: int, high: int | None) -> str:
    return f"{prefix}_{low}_plus" if high is None else f"{prefix}_{low}_to_{high}"


def coverage_tax_year(opening: int, label: str, notes: str | None = None) -> dict:
    coverage = {
        "start_date": f"{opening}-04-06",
        "end_date": f"{opening + 1}-04-05",
        "basis": "tax",
        "source_period_label": label,
    }
    if notes:
        coverage["notes"] = notes
    return coverage


def coverage_year_end(opening: int, label: str, notes: str | None = None) -> dict:
    """A stock dated at the end of the tax year (5 April)."""
    coverage = {
        "start_date": f"{opening + 1}-04-05",
        "end_date": f"{opening + 1}-04-05",
        "basis": "tax",
        "source_period_label": label,
    }
    if notes:
        coverage["notes"] = notes
    return coverage


def row_entry(
    *,
    value_id: str,
    label: str,
    ordinal: int,
    row_number: int,
    header_column: str,
    header: object,
    kind: str,
    filters: dict | None = None,
    constraints: list[dict] | None = None,
    geography: dict | None = None,
    guards: list[dict] | None = None,
) -> dict:
    entry: dict = {
        "value_id": value_id,
        "label": label,
        "ordinal": ordinal,
        "row_number": row_number,
        "expected_row_header_column": header_column,
        "expected_row_header": header,
    }
    if geography:
        entry.update(geography)
    entry["table_record_kind"] = kind
    if filters:
        entry["filters"] = filters
    if constraints:
        entry["constraints"] = constraints
    if guards:
        entry["guard_cells"] = guards
    return entry


def guard(column: str, row: int, value: object, label: str) -> dict:
    return {"column": column, "row": row, "expected_value": value, "label": label}


def measure_entry(
    *,
    measure_id: str,
    label: str,
    ordinal: int,
    column: str,
    header_row: int,
    header: object,
    concept: str,
    unit: str,
    value_scale: int | None,
    notes: str,
    evidence_url: str = RELEASE_URL,
    aggregation: str = "sum",
    filters: dict | None = None,
    constraints: list[dict] | None = None,
) -> dict:
    entry: dict = {
        "measure_id": measure_id,
        "label": label,
        "ordinal": ordinal,
        "column": column,
        "source_column_id": measure_id,
        "expected_column_header_row": header_row,
        "expected_column_header": header,
        "concept": concept,
        "source_concept": concept,
        "concept_relation": "source_label",
        "concept_authority": "hmrc",
        "concept_evidence_url": evidence_url,
        "concept_evidence_notes": notes,
        "unit": unit,
        "aggregation": aggregation,
    }
    if value_scale is not None:
        entry["value_scale"] = value_scale
    entry["expected_cell_type"] = "number"
    if filters:
        entry["filters"] = filters
    if constraints:
        entry["constraints"] = constraints
    return entry


def record_set(
    *,
    record_set_id: str,
    sheet: str,
    period: int,
    coverage: dict,
    provenance: str,
    entity_role: str,
    groupby: str,
    rows: list[dict],
    measures: list[dict],
    geography: dict = UK,
    shared: tuple[dict, list[dict]] | None = None,
    survey: str | None = None,
) -> dict:
    payload: dict = {"record_set_id": record_set_id, "provenance_class": provenance}
    if survey is not None:
        payload["survey_instrument"] = survey
    payload.update(
        {
            "assertion": "observation",
            "record_set_spec_id": f"{record_set_id}.v1",
            "source_record_id_prefix": record_set_id,
            "sheet_name": sheet,
            "period_type": "tax_year",
            "period": period,
            "period_coverage": coverage,
        }
    )
    payload.update(geography)
    payload.update(
        {
            "entity": "person",
            "entity_role": entity_role,
            "domain": DOMAIN,
            "groupby_dimension": groupby,
        }
    )
    if shared is not None:
        filters, constraints = shared
        if filters:
            payload["shared_filters"] = filters
        if constraints:
            payload["shared_constraints"] = constraints
    payload["rows"] = rows
    payload["measures"] = measures
    return payload


# ------------------------------------------------- publisher vocabularies

INCOME_LABELS = (
    "£0-£12,570",
    "£12,571-£20,000",
    "£20,001-£30,000",
    "£30,001-£40,000",
    "£40,001-£50,270",
    "£50,271-£60,000",
    "£60,001-£80,000",
    "£80,001-£100,000",
    "£100,001-£125,140",
    "£125,141-£150,000",
    "£150,001 or more",
)
SUBSCRIPTION_HEADERS = (
    "£1-£2,000 (thousands)",
    "£2,001-£4,000 (thousands)",
    "£4,001-£6,000 (thousands)",
    "£6,001-£8,000 (thousands)",
    "£8,001-£10,000 (thousands)",
    "£10,001-£12,000 (thousands)",
    "£12,001-£14,000 (thousands)",
    "£14,001-£16,000 (thousands)",
    "£16,001-£18,000 (thousands)",
    "£18,001-£19,999 (thousands)",
    "£20,000 (thousands)",
)
MARKET_VALUE_HEADERS = (
    "£1-£2,499 (thousands)",
    "£2,500-£4,999 (thousands)",
    "£5,000-£9,999 (thousands)",
    "£10,000-£14,999 (thousands)",
    "£15,000-£19,999 (thousands)",
    "£20,000-£24,999 (thousands)",
    "£25,000-£34,999 (thousands)",
    "£35,000-£49,999 (thousands)",
    "£50,000-£74,999 (thousands)",
    "£75,000-£99,999 (thousands)",
    "£100,000-£199,999 (thousands)",
    "£200,000 or more (thousands)",
)
ALL_SUBSCRIPTIONS = "All Subscriptions (thousands)"
NO_FURTHER = "No Further Subscription (thousands)"
ALL_HOLDERS = "All ISA Holders (thousands)"
TOTAL_HOLDERS = "Total (thousands)"
AVERAGE_VALUE = "Average ISA Market Value (£)"
SHARE_OF_ADULTS = "Percentage of All Adults (%)"

ISA_TYPES = {
    "all": "All Adult ISA types",
    "cash_only": "Cash ISA only",
    "stocks_and_shares_only": "Stocks and shares ISA only",
    "cash_and_stocks_and_shares": "Cash and stocks and shares ISAs",
}
SUBSCRIBER_BLOCKS_9_7 = (
    (
        "all",
        "Range of Income of All ISA Subscribers (maximum combined subscription £20,000)",
    ),
    ("cash_only", "Range of Income of Cash ISA Subscribers Only"),
    ("stocks_and_shares_only", "Range of Income of Stocks & Shares ISA Subscribers Only"),
    (
        "cash_and_stocks_and_shares",
        "Range of Income of Cash and Stocks & Shares ISA Subscribers",
    ),
)
HOLDER_BLOCKS_9_10 = (
    ("all", "Range of Income of All ISA Holders"),
    ("cash_only", "Range of Income of Cash ISA Holders Only"),
    ("stocks_and_shares_only", "Range of Income of Stocks & Shares ISA Holders Only"),
    ("cash_and_stocks_and_shares", "Range of Income of Cash and Stocks & Shares ISA Holders"),
)
TYPE_COLUMNS_9_8 = (
    ("cash_only", "Cash ISA (thousands)"),
    ("stocks_and_shares_only", "Stocks & Shares ISA (thousands)"),
    ("cash_and_stocks_and_shares", "Stocks & Shares and Cash ISA (thousands)"),
)
AGE_LABELS = (
    "Under 24",
    "24-26",
    "27-29",
    "30-32",
    "33-35",
    "36-38",
    "39-41",
    "42-44",
    "45-47",
    "48-50",
    "51-53",
    "54-56",
    "57-59",
    "60-62",
    "63-65",
    "66-68",
    "69-71",
    "72-74",
    "75-77",
    "78-80",
    "81 and over",
)
SEXES = (("male", "Male "), ("female", "Female "), ("all", ""))
REGIONS = (
    ("E12000001", "North East", "E12000001", "region"),
    ("E12000002", "North West and Merseyside", "E12000002", "region"),
    ("E12000003", "Yorkshire and the Humber", "E12000003", "region"),
    ("E12000004", "East Midlands", "E12000004", "region"),
    ("E12000005", "West Midlands", "E12000005", "region"),
    ("E12000006", "East of England", "E12000006", "region"),
    ("E12000007", "London", "E12000007", "region"),
    ("E12000008", "South East", "E12000008", "region"),
    ("E12000009", "South West", "E12000009", "region"),
    ("[no code]", "Total", "E92000001", "country"),
    ("W99999999", "Wales", "W92000004", "country"),
    ("S99999999", "Scotland", "S92000003", "country"),
    ("N99999999", "Northern Ireland", "N92000002", "country"),
    ("[no code]", "Overseas and Unknown", "hmrc:overseas_and_unknown", "statistical_scope"),
    ("K02000001", "United Kingdom", "K02000001", "country"),
)
GEOGRAPHY_NAMES = {
    "E92000001": "England",
    "W92000004": "Wales",
    "S92000003": "Scotland",
    "N92000002": "Northern Ireland",
    "hmrc:overseas_and_unknown": "Overseas and unknown",
    "K02000001": "United Kingdom",
}

# ------------------------------------------------------------ row builders


def income_rows(grid: dict, first_row: int, guards: list[dict]) -> list[dict]:
    rows = []
    previous_high: int | None = None
    for ordinal, label in enumerate(INCOME_LABELS):
        row = first_row + ordinal
        expect(grid, row, "A", label)
        low, high = money_band(label)
        value_id = band_id("income", low, high)
        filters, constraints = category("isa_income_band", value_id, "ISA income band")
        if previous_high is not None:
            constraints.append(
                constraint("total_income", ">", previous_high, "Total income lower bound", "gbp")
            )
        if high is not None:
            constraints.append(
                constraint("total_income", "<=", high, "Total income upper bound", "gbp")
            )
        previous_high = high
        rows.append(
            row_entry(
                value_id=value_id,
                label=f"Total income {label}",
                ordinal=ordinal,
                row_number=row,
                header_column="A",
                header=label,
                kind="detail",
                filters=filters,
                constraints=constraints,
                guards=guards,
            )
        )
    total_row = first_row + len(INCOME_LABELS)
    expect(grid, total_row, "A", "All ranges")
    rows.append(
        row_entry(
            value_id="all",
            label="All income ranges",
            ordinal=len(INCOME_LABELS),
            row_number=total_row,
            header_column="A",
            header="All ranges",
            kind="total",
            filters={"isa_income_band": "all"},
            guards=guards,
        )
    )
    return rows


def age_rows(grid: dict, first_row: int, prefix: str, guards: list[dict] | None) -> list[dict]:
    rows = []
    for ordinal, label in enumerate(AGE_LABELS):
        row = first_row + ordinal
        header = f"{prefix}{label}"
        expect(grid, row, "A", header)
        if label == "Under 24":
            value_id, bounds = "age_under_24", [("<", 24, "Age upper bound")]
            display = label
        elif label == "81 and over":
            value_id, bounds = "age_81_plus", [(">=", 81, "Age lower bound")]
            display = label
        else:
            low, high = (int(part) for part in label.split("-"))
            value_id = f"age_{low}_to_{high}"
            bounds = [(">=", low, "Age lower bound"), ("<=", high, "Age upper bound")]
            display = f"{low} to {high}"
        filters, constraints = category("age_band", value_id, "Age band")
        constraints.extend(
            constraint("age", operator, value, text, "years") for operator, value, text in bounds
        )
        rows.append(
            row_entry(
                value_id=value_id,
                label=display,
                ordinal=ordinal,
                row_number=row,
                header_column="A",
                header=header,
                kind="detail",
                filters=filters,
                constraints=constraints,
                guards=guards,
            )
        )
    total_row = first_row + len(AGE_LABELS)
    total_header = f"{prefix}Total"
    expect(grid, total_row, "A", total_header)
    rows.append(
        row_entry(
            value_id="all",
            label="All ages",
            ordinal=len(AGE_LABELS),
            row_number=total_row,
            header_column="A",
            header=total_header,
            kind="total",
            filters={"age_band": "all"},
            guards=guards,
        )
    )
    return rows


def region_rows(grid: dict, england_row: int, *, skip: tuple[str, ...] = ()) -> list[dict]:
    """Rows of Tables 9.9 and 9.12, from the row after the 'England' heading."""
    expect(grid, england_row, "A", "[no code]")
    expect(grid, england_row, "B", "England")
    rows = []
    ordinal = 0
    for offset, (code, name, geography_id, level) in enumerate(REGIONS, start=1):
        row = england_row + offset
        expect(grid, row, "A", code)
        expect(grid, row, "B", name)
        if geography_id in skip:
            continue
        guards = [guard("A", row, code, "Area code as published")]
        if geography_id == "E92000001":
            guards.append(guard("B", england_row, "England", "England section heading"))
        geography = {
            "geography_id": geography_id,
            "geography_level": level,
            "geography_name": GEOGRAPHY_NAMES.get(geography_id, name),
            "geography_vintage": "current",
        }
        kind = "total" if geography_id in ("E92000001", "K02000001") else "detail"
        rows.append(
            row_entry(
                value_id=geography_id.replace("hmrc:", ""),
                label=GEOGRAPHY_NAMES.get(geography_id, name),
                ordinal=ordinal,
                row_number=row,
                header_column="B",
                header=name,
                kind=kind,
                geography=geography,
                guards=guards,
            )
        )
        ordinal += 1
    expect(grid, england_row + len(REGIONS) + 1, "A", "End of worksheet")
    return rows


# --------------------------------------------------------- measure builders


def subscription_measures(header_row: int, first_column: str, notes: str) -> list[dict]:
    letters = columns(first_column, len(SUBSCRIPTION_HEADERS) + 1)
    measures = []
    previous_high = 0
    for ordinal, header in enumerate(SUBSCRIPTION_HEADERS):
        low, high = money_band(header)
        value_id = band_id("subscription", low, high)
        filters, constraints = category(
            "isa_subscription_band", value_id, "ISA subscription band"
        )
        if low == high:
            constraints.append(
                constraint("isa_subscription_amount", "==", low, "ISA subscription", "gbp")
            )
        else:
            constraints.append(
                constraint(
                    "isa_subscription_amount", ">", previous_high,
                    "ISA subscription lower bound", "gbp",
                )
            )
            next_low = money_band(SUBSCRIPTION_HEADERS[ordinal + 1])[0]
            operator, bound = ("<", next_low) if next_low == high + 1 and next_low == 20000 else ("<=", high)
            constraints.append(
                constraint(
                    "isa_subscription_amount", operator, bound,
                    "ISA subscription upper bound", "gbp",
                )
            )
        previous_high = high
        measures.append(
            measure_entry(
                measure_id=value_id,
                label=f"Individuals subscribing {header.removesuffix(' (thousands)')}",
                ordinal=ordinal,
                column=letters[ordinal],
                header_row=header_row,
                header=header,
                concept="hmrc.isa_subscribers",
                unit="count",
                value_scale=1,
                notes=notes,
                filters=filters,
                constraints=constraints,
            )
        )
    measures.append(
        measure_entry(
            measure_id="all_subscriptions",
            label="All individuals subscribing",
            ordinal=len(SUBSCRIPTION_HEADERS),
            column=letters[-1],
            header_row=header_row,
            header=ALL_SUBSCRIPTIONS,
            concept="hmrc.isa_subscribers",
            unit="count",
            value_scale=1,
            notes=notes,
            filters={"isa_subscription_band": "all"},
        )
    )
    return measures


def holder_status_measures(
    header_row: int, no_further_column: str, all_column: str, notes: str
) -> list[dict]:
    no_filters, no_constraints = category(
        "isa_subscription_band", "none", "ISA subscription band"
    )
    no_constraints.append(
        constraint("isa_subscription_amount", "==", 0, "No further subscription in the year", "gbp")
    )
    return [
        measure_entry(
            measure_id="no_further_subscription",
            label="ISA holders who made no further subscription in the year",
            ordinal=0,
            column=no_further_column,
            header_row=header_row,
            header=NO_FURTHER,
            concept="hmrc.isa_holders",
            unit="count",
            value_scale=1,
            notes=notes,
            filters=no_filters,
            constraints=no_constraints,
        ),
        measure_entry(
            measure_id="all_holders",
            label="All ISA holders",
            ordinal=1,
            column=all_column,
            header_row=header_row,
            header=ALL_HOLDERS,
            concept="hmrc.isa_holders",
            unit="count",
            value_scale=1,
            notes=notes,
            filters={"isa_subscription_band": "all"},
        ),
    ]


def market_value_measures(
    header_row: int, first_column: str, notes: str, average_notes: str
) -> list[dict]:
    letters = columns(first_column, len(MARKET_VALUE_HEADERS) + 2)
    measures = []
    for ordinal, header in enumerate(MARKET_VALUE_HEADERS):
        low, high = money_band(header)
        value_id = band_id("market_value", low, high)
        filters, constraints = category(
            "isa_market_value_band", value_id, "ISA market value band"
        )
        if ordinal == 0:
            constraints.append(
                constraint("isa_market_value", ">", 0, "ISA market value lower bound", "gbp")
            )
        else:
            constraints.append(
                constraint("isa_market_value", ">=", low, "ISA market value lower bound", "gbp")
            )
        if high is not None:
            constraints.append(
                constraint("isa_market_value", "<", high + 1, "ISA market value upper bound", "gbp")
            )
        measures.append(
            measure_entry(
                measure_id=value_id,
                label=f"ISA holders with market value {header.removesuffix(' (thousands)')}",
                ordinal=ordinal,
                column=letters[ordinal],
                header_row=header_row,
                header=header,
                concept="hmrc.isa_holders",
                unit="count",
                value_scale=1,
                notes=notes,
                filters=filters,
                constraints=constraints,
            )
        )
    measures.append(
        measure_entry(
            measure_id="all_holders",
            label="All ISA holders",
            ordinal=len(MARKET_VALUE_HEADERS),
            column=letters[-2],
            header_row=header_row,
            header=TOTAL_HOLDERS,
            concept="hmrc.isa_holders",
            unit="count",
            value_scale=1,
            notes=notes,
            filters={"isa_market_value_band": "all"},
        )
    )
    measures.append(
        measure_entry(
            measure_id="average_market_value",
            label="Average ISA market value per holder",
            ordinal=len(MARKET_VALUE_HEADERS) + 1,
            column=letters[-1],
            header_row=header_row,
            header=AVERAGE_VALUE,
            concept="hmrc.isa_mean_market_value_per_holder",
            unit="gbp",
            value_scale=1,
            notes=average_notes,
            aggregation="mean",
            filters={"isa_market_value_band": "all"},
        )
    )
    return measures


# ----------------------------------------------------------------- tables


def table_9_4(grid: dict) -> list[dict]:
    sheet = "9_4_ISA_subscriptions"
    expect(grid, 1, "A", "9.4: Individual Savings Accounts (ISAs)")
    units_note = note_text(grid, 5)
    assert units_note == "Numbers are in thousands, Amounts are in £ million and Averages are in £.", units_note
    returns_note = note_text(grid, 3)
    assert returns_note.startswith("The below tables shows the number of ISAs to which subscriptions"), returns_note
    limit_note = note_text(grid, 4)
    assert "which is not reported in these statistics" in limit_note, limit_note
    sections = (
        (
            "accounts",
            "Number of accounts subscribed in current year (thousands)",
            "hmrc.isa_accounts_subscribed",
            "count",
            1000,
            "Stocks and Shares Insurance Component",
        ),
        (
            "amounts",
            "Amounts subscribed (£ million)",
            "hmrc.isa_amount_subscribed",
            "gbp",
            1000000,
            "Stocks and shares insurance component",
        ),
    )
    components = (
        ("cash", "Cash ISA", "Cash ISA"),
        ("stocks_and_shares", "Stock and Shares ISA", "Stocks and shares ISA"),
        ("innovative_finance", "Innovative Finance ISA", "Innovative Finance ISA"),
        ("lifetime", "Lifetime ISA", "Lifetime ISA"),
        ("all", "Total", "All Adult ISAs"),
        ("stocks_and_shares_insurance", None, "Stocks and shares insurance component"),
    )
    year_columns = columns("B", 17)
    junior_row = only_row(grid, "A", "Junior ISAs (introduced from 1 November 2011)")
    record_sets = []
    for section, heading, concept, unit, scale, insurance_label in sections:
        header_row = only_row(grid, "A", heading, before=junior_row)
        for column_index, column in enumerate(year_columns):
            opening = 2008 + column_index
            year_label = grid[(header_row, column)]
            expected_label = f"{opening} to {opening + 1}" + (
                "[provisional]" if opening == 2024 else ""
            )
            assert re.sub(r"\s+$", "", str(year_label)) == expected_label, (year_label, expected_label)
            rows = []
            for ordinal, (component, label, readable) in enumerate(components):
                row = header_row + 1 + ordinal
                published = label if label is not None else insurance_label
                expect(grid, row, "A", published)
                value = grid.get((row, column))
                if not is_number(value):
                    assert value == "[not available]", (row, column, value)
                    continue
                filters, constraints = category("isa_component", component, "ISA component")
                rows.append(
                    row_entry(
                        value_id=component,
                        label=readable,
                        ordinal=len(rows),
                        row_number=row,
                        header_column="A",
                        header=published,
                        kind="total" if component == "all" else "detail",
                        filters=filters,
                        constraints=constraints,
                    )
                )
            notes = (
                f"Table 9.4, {heading}, {year_label}. Adult ISAs only (Junior ISAs are "
                "not ported). The counts are of accounts subscribed to in the year, not "
                "of individuals. " + units_note + " " + returns_note + " The Total row "
                "is the sum of the cash, stocks and shares, Innovative Finance and "
                "Lifetime ISA rows; the stocks and shares insurance component row is "
                "not added into it. " + limit_note
            )
            provisional = (
                "HMRC marks 2024 to 2025 as provisional." if opening == 2024 else None
            )
            record_sets.append(
                record_set(
                    record_set_id=f"{ISA_PREFIX}.table9_4.{section}.ty{opening}",
                    sheet=sheet,
                    period=opening,
                    coverage=coverage_tax_year(opening, str(year_label).strip(), provisional),
                    provenance="administrative",
                    entity_role="isa_subscriber",
                    groupby="isa_component",
                    rows=rows,
                    measures=[
                        measure_entry(
                            measure_id=section,
                            label=(
                                "Accounts subscribed to in the year"
                                if section == "accounts"
                                else "Amount subscribed in the year"
                            ),
                            ordinal=0,
                            column=column,
                            header_row=header_row,
                            header=year_label,
                            concept=concept,
                            unit=unit,
                            value_scale=scale,
                            notes=notes,
                        )
                    ],
                )
            )
    return record_sets


SHARES_TRADED = "Shares traded on a recognised stock exchange in the EEA & UK"
UCITS = (
    "Units/Shares in Undertaking for Collective Investment In Transferable Securities"
)
MARKET_VALUE_LINES = (
    ("Adult ISAs : Stocks & Shares Component", None),
    ("Shares", ("stocks_and_shares", "shares", "detail")),
    (SHARES_TRADED, ("stocks_and_shares", "shares_traded_on_a_recognised_exchange", "detail")),
    ("Securities", ("stocks_and_shares", "securities", "detail")),
    ("Gilts", ("stocks_and_shares", "gilts", "detail")),
    ("Unit Trusts", ("stocks_and_shares", "unit_trusts", "detail")),
    (
        "Shares in Open Ended Investment Companies (OEICs)",
        ("stocks_and_shares", "open_ended_investment_companies", "detail"),
    ),
    ("Corporate Bond Funds", ("stocks_and_shares", "corporate_bond_funds", "detail")),
    ("Investment Trusts", ("stocks_and_shares", "investment_trusts", "detail")),
    (UCITS, ("stocks_and_shares", "ucits", "detail")),
    ("Surrender value of policies", ("stocks_and_shares", "surrender_value_of_policies", "detail")),
    ("Cash on deposit", ("stocks_and_shares", "cash_on_deposit", "detail")),
    ("Total ISA and PEP Stocks & Shares Funds", ("stocks_and_shares", "all", "total")),
    ("Adult ISAs: Cash Component", None),
    ("Other Investment Products", ("cash", "other_investment_products", "detail")),
    ("Cash on deposit", ("cash", "cash_on_deposit", "detail")),
    ("Total ISA Cash Component (including TESSA)", ("cash", "all", "total")),
    ("Adult ISAs : Innovative Finance Component", None),
    (
        "Outstanding principal balance of Innovative Finance loans",
        ("innovative_finance", "innovative_finance_loans", "detail"),
    ),
    ("Cash on deposit", ("innovative_finance", "cash_on_deposit", "detail")),
    ("Total ISA Innovative Finance Component", ("innovative_finance", "all", "total")),
    ("Total Adult ISA and PEP Funds", ("all", "all", "total")),
)


def table_9_6(grid: dict) -> list[dict]:
    sheet = "9_6_ISA_market_values"
    expect(grid, 1, "A", "9.6: Individual Savings Accounts (ISAs)")
    lisa_note = note_text(grid, 8)
    assert lisa_note == (
        "Lifetime ISAs market values are included in the overall total market values "
        "for Cash ISAs and Stocks and Shares ISAs."
    ), lisa_note
    tessa_note = note_text(grid, 5)
    assert tessa_note.startswith("Market values of Unit Trusts"), tessa_note
    policy_note = note_text(grid, 4)
    assert policy_note.startswith("The surrender value of policies"), policy_note
    revision_note = note_text(grid, 9)
    assert revision_note.startswith("Total ISA and PEP Stocks & Shares Funds"), revision_note
    header_row = only_row(grid, "A", "Tax Year")
    year_columns = columns("B", 14)
    record_sets = []
    for column_index, column in enumerate(year_columns):
        opening = 2011 + column_index
        year_label = grid[(header_row, column)]
        assert year_label == f"{opening} to {opening + 1} (£ million)", year_label
        rows = []
        section_row = None
        for offset, (label, spec) in enumerate(MARKET_VALUE_LINES, start=1):
            row = header_row + offset
            expect(grid, row, "A", label)
            if spec is None:
                section_row = row
                continue
            component, asset, kind = spec
            value = grid.get((row, column))
            if not is_number(value):
                assert value == "[not available]", (row, column, value)
                continue
            filters, constraints = category("isa_component", component, "ISA component")
            asset_filters, asset_constraints = category("isa_asset_type", asset, "ISA asset type")
            filters.update(asset_filters)
            constraints.extend(asset_constraints)
            guards = None
            if component != "all":
                guards = [guard("A", section_row, grid[(section_row, "A")], "Component heading")]
            rows.append(
                row_entry(
                    value_id=f"{component}.{asset}",
                    label=f"{label} ({component.replace('_', ' ')} component)" if component != "all" else label,
                    ordinal=len(rows),
                    row_number=row,
                    header_column="A",
                    header=label,
                    kind=kind,
                    filters=filters,
                    constraints=constraints,
                    guards=guards,
                )
            )
        expect(grid, header_row + len(MARKET_VALUE_LINES) + 1, "A", "Junior ISAs")
        notes = (
            f"Table 9.6, market value of Adult ISA funds by type of qualifying investment, "
            f"{year_label}, as at the end of the tax year. " + note_text(grid, 3) + " "
            + policy_note + " " + tessa_note + " " + lisa_note + " " + revision_note
            + " Junior ISA lines are not ported."
        )
        record_sets.append(
            record_set(
                record_set_id=f"{ISA_PREFIX}.table9_6.ty{opening}",
                sheet=sheet,
                period=opening,
                coverage=coverage_year_end(
                    opening,
                    str(year_label),
                    f"Market values as at 5 April {opening + 1}, the end of the tax year.",
                ),
                provenance="administrative",
                entity_role="isa_holder",
                groupby="isa_asset_type",
                rows=rows,
                measures=[
                    measure_entry(
                        measure_id="market_value",
                        label="Market value of Adult ISA funds",
                        ordinal=0,
                        column=column,
                        header_row=header_row,
                        header=year_label,
                        concept="hmrc.isa_market_value",
                        unit="gbp",
                        value_scale=1000000,
                        notes=notes,
                    )
                ],
            )
        )
    return record_sets


def subscriber_notes(table: str, extra: str = "") -> str:
    return (
        f"Table {table}, individuals subscribing to Adult ISAs in the 2023 to 2024 tax "
        "year (6 April 2023 to 5 April 2024). " + THOUSANDS_HEADING + " "
        + TABLES_9_7_TO_9_12 + " HMRC does not say how Lifetime ISAs are classed in "
        "these tables." + (" " + extra if extra else "")
    )


HOLDER_NOTE = (
    "HMRC: no further subscription represents individuals holding possibly one or more "
    "ISA account (variously cash, stocks and shares, or a combination of both) but who "
    "did not make a further subscription during the 2023 to 2024 year. The total number "
    "of ISA holders is not reported by ISA managers; HMRC estimates it from average "
    "market values of ISAs for a sample of individuals combined with reported aggregate "
    "ISA market values (Table 9.6)."
)


def table_9_7(grid: dict) -> list[dict]:
    sheet = "9_7_ISA_subs_by_income"
    expect(grid, 1, "A", "9.7: Individual Savings Accounts (ISAs)")
    assert note_text(grid, 6) == "Innovative Finance ISA holders are not included in these tables."
    record_sets = []
    title_rows = []
    for isa_type, title in SUBSCRIBER_BLOCKS_9_7:
        title_row = only_row(grid, "A", title)
        title_rows.append(title_row)
        letters = columns("B", 14)
        for letter, header in zip(
            letters, SUBSCRIPTION_HEADERS + (ALL_SUBSCRIPTIONS, NO_FURTHER, ALL_HOLDERS)
        ):
            expect(grid, title_row, letter, header)
        guards = [guard("A", title_row, title, "Table 9.7 block title")]
        shared = category("isa_type", isa_type, "ISA type")
        both_note = (
            "In this block the subscription band is the combined amount subscribed "
            "across cash and stocks and shares ISAs."
            if isa_type in ("all", "cash_and_stocks_and_shares")
            else ""
        )
        record_sets.append(
            record_set(
                record_set_id=f"{ISA_PREFIX}.table9_7.ty2023.{isa_type}.subscribers",
                sheet=sheet,
                period=2023,
                coverage=coverage_tax_year(2023, "2023 to 2024 tax year"),
                provenance="survey_aggregate",
                survey=SURVEY,
                entity_role="isa_subscriber",
                groupby="isa_income_band",
                rows=income_rows(grid, title_row + 1, guards),
                measures=subscription_measures(
                    title_row, "B", subscriber_notes("9.7", both_note)
                ),
                shared=shared,
            )
        )
        record_sets.append(
            record_set(
                record_set_id=f"{ISA_PREFIX}.table9_7.ty2023.{isa_type}.holders",
                sheet=sheet,
                period=2023,
                coverage=coverage_year_end(2023, "2023 to 2024 tax year"),
                provenance="survey_aggregate",
                survey=SURVEY,
                entity_role="isa_holder",
                groupby="isa_income_band",
                rows=income_rows(grid, title_row + 1, guards),
                measures=holder_status_measures(
                    title_row, letters[12], letters[13],
                    subscriber_notes("9.7", HOLDER_NOTE),
                ),
                shared=shared,
            )
        )
    assert title_rows == sorted(title_rows), title_rows
    expect(grid, title_rows[-1] + len(INCOME_LABELS) + 2, "A", "End of worksheet")
    return record_sets


def table_9_8(grid: dict) -> list[dict]:
    sheet = "9_8_ISA_subs_by_age_sex"
    expect(grid, 1, "A", "9.8: Individual Savings Accounts (ISAs)")
    header_row = only_row(grid, "A", "Type of ISA")
    letters = columns("B", 6)
    headers = tuple(header for _, header in TYPE_COLUMNS_9_8) + (
        ALL_SUBSCRIPTIONS, NO_FURTHER, ALL_HOLDERS,
    )
    for letter, header in zip(letters, headers):
        expect(grid, header_row, letter, header)
    notes = subscriber_notes(
        "9.8",
        "HMRC does not say at what date age is measured. Before 6 April 2024, 16 and "
        "17 year olds could subscribe to adult cash ISAs, so the youngest band may "
        "include them.",
    )
    record_sets = []
    for block, (sex, prefix) in enumerate(SEXES):
        first_row = header_row + 1 + block * (len(AGE_LABELS) + 1)
        shared = category("sex", sex, "Sex")
        subscriber_measures = []
        for ordinal, (isa_type, header) in enumerate(TYPE_COLUMNS_9_8):
            filters, constraints = category("isa_type", isa_type, "ISA type")
            subscriber_measures.append(
                measure_entry(
                    measure_id=f"{isa_type}_subscribers",
                    label=f"Individuals subscribing: {ISA_TYPES[isa_type]}",
                    ordinal=ordinal,
                    column=letters[ordinal],
                    header_row=header_row,
                    header=header,
                    concept="hmrc.isa_subscribers",
                    unit="count",
                    value_scale=1,
                    notes=notes,
                    filters=filters,
                    constraints=constraints,
                )
            )
        subscriber_measures.append(
            measure_entry(
                measure_id="all_subscribers",
                label="All individuals subscribing",
                ordinal=3,
                column=letters[3],
                header_row=header_row,
                header=ALL_SUBSCRIPTIONS,
                concept="hmrc.isa_subscribers",
                unit="count",
                value_scale=1,
                notes=notes,
                filters={"isa_type": "all"},
            )
        )
        record_sets.append(
            record_set(
                record_set_id=f"{ISA_PREFIX}.table9_8.ty2023.{sex}.subscribers",
                sheet=sheet,
                period=2023,
                coverage=coverage_tax_year(2023, "2023 to 2024 tax year"),
                provenance="survey_aggregate",
                survey=SURVEY,
                entity_role="isa_subscriber",
                groupby="age_band",
                rows=age_rows(grid, first_row, prefix, None),
                measures=subscriber_measures,
                shared=shared,
            )
        )
        holder_measures = holder_status_measures(
            header_row, letters[4], letters[5],
            subscriber_notes("9.8", HOLDER_NOTE),
        )
        for item in holder_measures:
            item["filters"] = {"isa_type": "all", **item["filters"]}
        record_sets.append(
            record_set(
                record_set_id=f"{ISA_PREFIX}.table9_8.ty2023.{sex}.holders",
                sheet=sheet,
                period=2023,
                coverage=coverage_year_end(2023, "2023 to 2024 tax year"),
                provenance="survey_aggregate",
                survey=SURVEY,
                entity_role="isa_holder",
                groupby="age_band",
                rows=age_rows(grid, first_row, prefix, None),
                measures=holder_measures,
                shared=shared,
            )
        )
    end_row = header_row + 1 + len(SEXES) * (len(AGE_LABELS) + 1)
    expect(grid, end_row, "A", "End of worksheet")
    return record_sets


def table_9_9(grid: dict) -> list[dict]:
    sheet = "9_9_ISA_subs_by_country_region"
    expect(grid, 1, "A", "9.9: Individual Savings Accounts (ISAs)")
    header_row = only_row(grid, "A", "Area Code")
    expect(grid, header_row, "B", "Type of ISA")
    letters = columns("C", 6)
    headers = tuple(header for _, header in TYPE_COLUMNS_9_8) + (
        ALL_SUBSCRIPTIONS, NO_FURTHER, ALL_HOLDERS,
    )
    for letter, header in zip(letters, headers):
        expect(grid, header_row, letter, header)
    notes = subscriber_notes(
        "9.9",
        "Region and country come from the Survey of Personal Incomes. HMRC publishes "
        "the countries under the codes W99999999, S99999999 and N99999999 and leaves "
        "England's total and the overseas and unknown row without a code.",
    )
    subscriber_measures = []
    for ordinal, (isa_type, header) in enumerate(TYPE_COLUMNS_9_8):
        filters, constraints = category("isa_type", isa_type, "ISA type")
        subscriber_measures.append(
            measure_entry(
                measure_id=f"{isa_type}_subscribers",
                label=f"Individuals subscribing: {ISA_TYPES[isa_type]}",
                ordinal=ordinal,
                column=letters[ordinal],
                header_row=header_row,
                header=header,
                concept="hmrc.isa_subscribers",
                unit="count",
                value_scale=1,
                notes=notes,
                filters=filters,
                constraints=constraints,
            )
        )
    subscriber_measures.append(
        measure_entry(
            measure_id="all_subscribers",
            label="All individuals subscribing",
            ordinal=3,
            column=letters[3],
            header_row=header_row,
            header=ALL_SUBSCRIPTIONS,
            concept="hmrc.isa_subscribers",
            unit="count",
            value_scale=1,
            notes=notes,
            filters={"isa_type": "all"},
        )
    )
    holder_measures = holder_status_measures(
        header_row, letters[4], letters[5], subscriber_notes("9.9", HOLDER_NOTE)
    )
    for item in holder_measures:
        item["filters"] = {"isa_type": "all", **item["filters"]}
    england_row = header_row + 1
    return [
        record_set(
            record_set_id=f"{ISA_PREFIX}.table9_9.ty2023.subscribers",
            sheet=sheet,
            period=2023,
            coverage=coverage_tax_year(2023, "2023 to 2024 tax year"),
            provenance="survey_aggregate",
            survey=SURVEY,
            entity_role="isa_subscriber",
            groupby="geography",
            rows=region_rows(grid, england_row),
            measures=subscriber_measures,
        ),
        record_set(
            record_set_id=f"{ISA_PREFIX}.table9_9.ty2023.holders",
            sheet=sheet,
            period=2023,
            coverage=coverage_year_end(2023, "2023 to 2024 tax year"),
            provenance="survey_aggregate",
            survey=SURVEY,
            entity_role="isa_holder",
            groupby="geography",
            rows=region_rows(grid, england_row),
            measures=holder_measures,
        ),
    ]


def holder_notes(table: str, extra: str = "") -> str:
    return (
        f"Table {table}, individuals holding Adult ISAs as at the end of the 2023 to 2024 "
        "tax year, by market value. " + THOUSANDS_HEADING + " " + TABLES_9_7_TO_9_12
        + " The total number of ISA holders is not reported by ISA managers; HMRC "
        "estimates it from average market values of ISAs for a sample of individuals "
        "combined with reported aggregate ISA market values (Table 9.6)."
        + (" " + extra if extra else "")
    )


AVERAGE_NOTE = (
    "Average ISA market value per holder in GBP, as published (the market value total "
    "behind it is not published at this breakdown)."
)


def table_9_10(grid: dict) -> list[dict]:
    sheet = "9_10_ISA_market_values_income"
    expect(grid, 1, "A", "9.10: Individual Savings Accounts (ISAs)")
    record_sets = []
    title_rows = []
    letters = columns("B", 14)
    for isa_type, title in HOLDER_BLOCKS_9_10:
        title_row = only_row(grid, "A", title)
        title_rows.append(title_row)
        for letter, header in zip(letters, MARKET_VALUE_HEADERS + (TOTAL_HOLDERS, AVERAGE_VALUE)):
            expect(grid, title_row, letter, header)
        guards = [guard("A", title_row, title, "Table 9.10 block title")]
        record_sets.append(
            record_set(
                record_set_id=f"{ISA_PREFIX}.table9_10.ty2023.{isa_type}",
                sheet=sheet,
                period=2023,
                coverage=coverage_year_end(2023, "2023 to 2024 tax year"),
                provenance="survey_aggregate",
                survey=SURVEY,
                entity_role="isa_holder",
                groupby="isa_income_band",
                rows=income_rows(grid, title_row + 1, guards),
                measures=market_value_measures(
                    title_row, "B", holder_notes("9.10"), holder_notes("9.10", AVERAGE_NOTE)
                ),
                shared=category("isa_type", isa_type, "ISA type"),
            )
        )
    assert title_rows == sorted(title_rows), title_rows
    expect(grid, title_rows[-1] + len(INCOME_LABELS) + 2, "A", "End of worksheet")
    return record_sets


def table_9_11(grid: dict) -> list[dict]:
    sheet = "9_11ISA_market_value_by_age_sex"
    expect(grid, 1, "A", "9.11: Individual Savings Accounts")
    header_row = only_row(grid, "A", "Market Value")
    letters = columns("B", 14)
    for letter, header in zip(letters, MARKET_VALUE_HEADERS + (TOTAL_HOLDERS, AVERAGE_VALUE)):
        expect(grid, header_row, letter, header)
    record_sets = []
    for block, (sex, prefix) in enumerate(SEXES):
        first_row = header_row + 1 + block * (len(AGE_LABELS) + 1)
        record_sets.append(
            record_set(
                record_set_id=f"{ISA_PREFIX}.table9_11.ty2023.{sex}",
                sheet=sheet,
                period=2023,
                coverage=coverage_year_end(2023, "2023 to 2024 tax year"),
                provenance="survey_aggregate",
                survey=SURVEY,
                entity_role="isa_holder",
                groupby="age_band",
                rows=age_rows(grid, first_row, prefix, None),
                measures=market_value_measures(
                    header_row, "B",
                    holder_notes("9.11", "All Adult ISA types."),
                    holder_notes("9.11", AVERAGE_NOTE),
                ),
                shared=category("sex", sex, "Sex"),
            )
        )
    end_row = header_row + 1 + len(SEXES) * (len(AGE_LABELS) + 1)
    expect(grid, end_row, "A", "End of worksheet")
    return record_sets


def table_9_12(grid: dict) -> list[dict]:
    sheet = "9_12ISA_market_values_by_region"
    expect(grid, 1, "A", "9.12: Individual Savings Accounts (ISAs)")
    adults_note = note_text(grid, 6)
    assert adults_note == (
        "In column titles, percentage of adults refers to all individuals aged 18 or over."
    ), adults_note
    population_note = note_text(grid, 5)
    assert population_note.startswith("Population estimates are taken from the Office"), population_note
    header_row = only_row(grid, "A", "Area Code")
    expect(grid, header_row, "B", "Market Value")
    letters = columns("C", 15)
    headers = MARKET_VALUE_HEADERS + (TOTAL_HOLDERS, SHARE_OF_ADULTS, AVERAGE_VALUE)
    for letter, header in zip(letters, headers):
        expect(grid, header_row, letter, header)
    notes = holder_notes(
        "9.12",
        "All Adult ISA types. HMRC publishes the countries under the codes W99999999, "
        "S99999999 and N99999999 and leaves England's total and the overseas and "
        "unknown row without a code.",
    )
    england_row = header_row + 1
    measures = market_value_measures(
        header_row, "C", notes, holder_notes("9.12", AVERAGE_NOTE)
    )
    # Table 9.12 puts the share of adults between the total and the average.
    measures[-1]["column"] = letters[14]
    share_measure = measure_entry(
        measure_id="share_of_adults",
        label="ISA holders as a share of adults aged 18 or over",
        ordinal=0,
        column=letters[13],
        header_row=header_row,
        header=SHARE_OF_ADULTS,
        concept="hmrc.isa_holders_share_of_adults",
        unit="share",
        value_scale=1,
        notes=(
            "Table 9.12, ISA holders at the end of the 2023 to 2024 tax year as a share of "
            "all individuals aged 18 or over, stored as the published fraction. "
            + population_note + " " + adults_note
        ),
        aggregation="share",
        filters={"isa_type": "all"},
    )
    return [
        record_set(
            record_set_id=f"{ISA_PREFIX}.table9_12.ty2023",
            sheet=sheet,
            period=2023,
            coverage=coverage_year_end(2023, "2023 to 2024 tax year"),
            provenance="survey_aggregate",
            survey=SURVEY,
            entity_role="isa_holder",
            groupby="geography",
            rows=region_rows(grid, england_row),
            measures=measures,
            shared=category("isa_type", "all", "ISA type"),
        ),
        record_set(
            record_set_id=f"{ISA_PREFIX}.table9_12.ty2023.share_of_adults",
            sheet=sheet,
            period=2023,
            coverage=coverage_year_end(2023, "2023 to 2024 tax year"),
            provenance="model_output",
            entity_role="isa_holder",
            groupby="geography",
            rows=region_rows(grid, england_row, skip=("hmrc:overseas_and_unknown",)),
            measures=[share_measure],
        ),
    ]


# ------------------------------------------------------------- packages

ISA_HEADER = """\
# HMRC Annual savings statistics, September 2026: the Individual Savings Account (ISA)
# tables (published 16 September 2026), for PolicyEngine/microcosm#1415. Written by
# build_package.py in this directory from the pinned workbook; edit that, not this.
#
# Ported: Table 9.4 (Adult ISA accounts subscribed to and amounts subscribed, by
# component, 2008-09 to 2024-25), Table 9.6 (market value of Adult ISA funds by type of
# qualifying investment, 2011-12 to 2024-25), and Tables 9.7 to 9.12 (2023-24 estimates of
# individuals subscribing and holding, by income, age, sex, region, subscription band and
# market value). Not ported: Table 9.4's average subscription per account (a quotient of
# ported cells) and the Junior ISA rows of Tables 9.4 and 9.6.
#
# Tables 9.7 to 9.12 put '(thousands)' in their column headings, but the cells are counts
# of individuals: only that reading matches HMRC's commentary (13.05 million subscribers
# and 23.0 million holders in 2023-24), so those measures carry value_scale 1. Table 9.4
# counts accounts, not individuals, in thousands, with amounts in GBP million, as its
# own note says. HMRC estimates Tables 9.7 to 9.12 from a sample of individuals' accounts
# matched to the Survey of Personal Incomes and calibrated to the totals in Tables 9.4
# and 9.6. Table 9.6 says Lifetime ISA market values are inside the cash and stocks and
# shares totals; the notes to Tables 9.7 to 9.12 do not say how Lifetime ISAs are classed,
# and they exclude Innovative Finance ISA holders. In Table 9.7's 'all' and 'cash and
# stocks and shares' blocks the subscription band is the combined amount. Chronicle
# reconciles none of these tables with each other.
#
"""

LISA_HEADER = """\
# HMRC Annual savings statistics, September 2026: the Lifetime ISA tables (published
# 16 September 2026), for PolicyEngine/microcosm#1415. Written by
# packages/hmrc/isa_statistics_2026/build_package.py from the pinned workbook.
#
# The workbook has withdrawals only: Table 1a by tax year and Table 1b by tax month.
# Lifetime ISA accounts and amounts subscribed are in the ISA tables' Table 9.4
# (hmrc-isa-statistics-2026); the government bonus is published in neither. Ported: Table
# 1a's counts and values for 2018-19 to 2025-26. Not ported: Table 1b (the same flows by
# month) and Table 1a's two average columns (quotients of ported cells). HMRC rounds the
# numbers of individuals to the nearest 50.
#
"""

NOTE_HEADER = """\
# HMRC, Cash Individual Savings Account (ISA) limit reduction: tax information and impact
# note (published 17 September 2026), archived HTML on the html_tables_and_text
# document-numbers lane, for PolicyEngine/microcosm#1415. Written by
# packages/hmrc/isa_statistics_2026/build_package.py from the pinned page.
#
# One sentence, two facts: in 2022-23, 78% of cash ISA subscribers aged under 65
# subscribed less than GBP 12,000 to a cash ISA and 22% subscribed over GBP 12,000. The
# note names no data source, so the shares carry provenance_class model_output (a policy
# paper's estimate). The sentence does not place a subscription of exactly GBP 12,000,
# and does not say whether a subscriber who also paid into a stocks and shares ISA is
# counted on the cash amount alone. The page's other '22%' (the flat-rate charge on
# interest on cash held in non-cash ISAs) is a rate, not this share, and is not ported.
# Budget 2026 (28 October 2026) announced that the GBP 12,000 limit will not go ahead.
#
"""


class PackageDumper(yaml.SafeDumper):
    """Plain YAML with no anchors, so every record set reads on its own."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def render(header: str, payload: dict) -> str:
    return header + yaml.dump(
        payload, Dumper=PackageDumper, sort_keys=False, allow_unicode=True, width=100
    )


ISA_DIMENSION_LABELS = {
    "isa_type": "ISA type",
    "isa_income_band": "Total income band",
    "isa_subscription_band": "ISA subscription band",
    "isa_market_value_band": "ISA market value band",
    "isa_component": "ISA component",
    "isa_asset_type": "Type of qualifying investment",
    "age_band": "Age band",
    "sex": "Sex",
    "geography": "Geography",
}


def isa_value_labels() -> dict:
    income = {band_id("income", *money_band(label)): f"Total income {label}" for label in INCOME_LABELS}
    income["all"] = "All income ranges"
    subscription = {
        band_id("subscription", *money_band(header)): header.removesuffix(" (thousands)")
        for header in SUBSCRIPTION_HEADERS
    }
    subscription["all"] = "All subscriptions"
    subscription["none"] = "No further subscription"
    market_value = {
        band_id("market_value", *money_band(header)): header.removesuffix(" (thousands)")
        for header in MARKET_VALUE_HEADERS
    }
    market_value["all"] = "All market values"
    ages = {}
    for label in AGE_LABELS:
        if label == "Under 24":
            ages["age_under_24"] = "Under 24"
        elif label == "81 and over":
            ages["age_81_plus"] = "81 and over"
        else:
            low, high = label.split("-")
            ages[f"age_{low}_to_{high}"] = f"{low} to {high}"
    ages["all"] = "All ages"
    return {
        "isa_type": dict(ISA_TYPES),
        "isa_income_band": income,
        "isa_subscription_band": subscription,
        "isa_market_value_band": market_value,
        "isa_component": {
            "cash": "Cash ISA",
            "stocks_and_shares": "Stocks and shares ISA",
            "innovative_finance": "Innovative Finance ISA",
            "lifetime": "Lifetime ISA",
            "stocks_and_shares_insurance": "Stocks and shares insurance component",
            "all": "All Adult ISAs",
        },
        "isa_asset_type": {
            "shares": "Shares",
            "shares_traded_on_a_recognised_exchange": SHARES_TRADED,
            "securities": "Securities",
            "gilts": "Gilts",
            "unit_trusts": "Unit Trusts",
            "open_ended_investment_companies": "Shares in Open Ended Investment Companies (OEICs)",
            "corporate_bond_funds": "Corporate Bond Funds",
            "investment_trusts": "Investment Trusts",
            "ucits": UCITS,
            "surrender_value_of_policies": "Surrender value of policies",
            "cash_on_deposit": "Cash on deposit",
            "other_investment_products": "Other Investment Products",
            "innovative_finance_loans": "Outstanding principal balance of Innovative Finance loans",
            "all": "All qualifying investments",
        },
        "age_band": ages,
        "sex": {"male": "Male", "female": "Female", "all": "All"},
    }


def isa_package() -> str:
    sheets = ods_sheets(ISA_DIR, ISA_FILE, ISA_SHA256, ISA_SHEETS)
    record_sets = (
        table_9_4(sheets["9_4_ISA_subscriptions"])
        + table_9_6(sheets["9_6_ISA_market_values"])
        + table_9_7(sheets["9_7_ISA_subs_by_income"])
        + table_9_8(sheets["9_8_ISA_subs_by_age_sex"])
        + table_9_9(sheets["9_9_ISA_subs_by_country_region"])
        + table_9_10(sheets["9_10_ISA_market_values_income"])
        + table_9_11(sheets["9_11ISA_market_value_by_age_sex"])
        + table_9_12(sheets["9_12ISA_market_values_by_region"])
    )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": ISA_PACKAGE_ID,
        "label": (
            "HMRC Individual Savings Account statistics, September 2026: accounts, "
            "subscriptions and market values (Tables 9.4 and 9.6), and individuals "
            "subscribing and holding by income, age, sex, region, subscription and market "
            "value in 2023-24 (Tables 9.7 to 9.12)"
        ),
        "dimension_labels": ISA_DIMENSION_LABELS,
        "dimension_value_labels": isa_value_labels(),
        "artifact": {
            "source_name": "hmrc",
            "source_table": "Individual Savings Account (ISA) tables: September 2026",
            "resource_package": "db",
            "resource_directory": f"data/{ISA_DIR}",
            "manifest": "manifest.yaml",
            "vintage": "annual_savings_statistics_2026",
            "extracted_at": "2026-10-28",
            "extraction_method": "ODS whole-workbook used-range parse with numeric-text coercion",
            "parser": "ods_numeric_text_used_range",
            "artifact_year": 2026,
        },
        "record_sets": record_sets,
    }
    return render(ISA_HEADER, payload)


LISA_COLUMNS = (
    ("B", "Number of individuals withdrawing for a house purchase", "house_purchase_withdrawers",
     "hmrc.lisa_withdrawers", "count", "house_purchase"),
    ("C", "Total value of house purchase withdrawals, £", "house_purchase_withdrawal_value",
     "hmrc.lisa_withdrawal_value", "gbp", "house_purchase"),
    ("E", "Number of individuals making unauthorised withdrawals", "unauthorised_withdrawers",
     "hmrc.lisa_withdrawers", "count", "unauthorised"),
    ("F", "Total value of unauthorised withdrawals, £", "unauthorised_withdrawal_value",
     "hmrc.lisa_withdrawal_value", "gbp", "unauthorised"),
    ("G", "Total value of withdrawal charges, £", "withdrawal_charges",
     "hmrc.lisa_withdrawal_charges", "gbp", "unauthorised"),
)
LISA_AVERAGES = {
    "D": "Average value of a withdrawal for a house purchase, £",
    "H": "Average value of an unauthorised withdrawal, £",
}


def lisa_package() -> str:
    sheets = ods_sheets(LISA_DIR, LISA_FILE, LISA_SHA256, LISA_SHEETS)
    grid = sheets["Lifetime_ISA_sheet"]
    expect(grid, 1, "A", "Lifetime Individual Savings Accounts (LISAs) Tables 1a and 1b")
    notes_text = [note_text(grid, row) for row in range(2, 12)]
    assert notes_text[2].startswith("The figures for the number of individuals are rounded"), notes_text[2]
    title_row = only_row(grid, "A", "Table 1a: Yearly LISA withdrawals")
    header_row = title_row + 1
    expect(grid, header_row, "A", "Tax year")
    for column, header, *_ in LISA_COLUMNS:
        expect(grid, header_row, column, header)
    for column, header in LISA_AVERAGES.items():
        expect(grid, header_row, column, header)
    record_sets = []
    row = header_row + 1
    notes = (
        "Lifetime ISA Table 1a, yearly withdrawals. " + " ".join(notes_text[:3])
    )
    while grid.get((row, "A")) not in (None, "Table 1b: Monthly LISA withdrawals"):
        label = grid[(row, "A")]
        match = re.fullmatch(r"(\d{4}) to (\d{4})", str(label))
        assert match and int(match.group(2)) == int(match.group(1)) + 1, label
        opening = int(match.group(1))
        measures = []
        for ordinal, (column, header, measure_id, concept, unit, reason) in enumerate(LISA_COLUMNS):
            assert is_number(grid.get((row, column))), (row, column)
            filters, constraints = category("lisa_withdrawal_reason", reason, "Lifetime ISA withdrawal reason")
            measures.append(
                measure_entry(
                    measure_id=measure_id,
                    label=header.removesuffix(", £"),
                    ordinal=ordinal,
                    column=column,
                    header_row=header_row,
                    header=header,
                    concept=concept,
                    unit=unit,
                    value_scale=1,
                    notes=notes,
                    filters=filters,
                    constraints=constraints,
                )
            )
        record_sets.append(
            record_set(
                record_set_id=f"{LISA_PREFIX}.table1a.ty{opening}",
                sheet="Lifetime_ISA_sheet",
                period=opening,
                coverage=coverage_tax_year(opening, str(label)),
                provenance="administrative",
                entity_role="lisa_holder",
                groupby="hmrc.tax_year",
                rows=[
                    row_entry(
                        value_id=f"tax_year_{opening}",
                        label=f"Tax year {label}",
                        ordinal=0,
                        row_number=row,
                        header_column="A",
                        header=label,
                        kind="detail",
                        guards=[guard("A", title_row, "Table 1a: Yearly LISA withdrawals", "Table title")],
                    )
                ],
                measures=measures,
            )
        )
        row += 1
    assert len(record_sets) == 8, len(record_sets)
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": LISA_PACKAGE_ID,
        "label": (
            "HMRC Lifetime ISA statistics, September 2026: yearly withdrawals for house "
            "purchases and unauthorised withdrawals, 2018-19 to 2025-26 (Table 1a)"
        ),
        "dimension_labels": {
            "hmrc.tax_year": "Tax year",
            "lisa_withdrawal_reason": "Lifetime ISA withdrawal reason",
        },
        "dimension_value_labels": {
            "lisa_withdrawal_reason": {
                "house_purchase": "Withdrawal for a house purchase",
                "unauthorised": "Unauthorised withdrawal",
            }
        },
        "artifact": {
            "source_name": "hmrc",
            "source_table": "Lifetime Individual Savings Account (LISA) tables: September 2026",
            "resource_package": "db",
            "resource_directory": f"data/{LISA_DIR}",
            "manifest": "manifest.yaml",
            "vintage": "annual_savings_statistics_2026",
            "extracted_at": "2026-10-28",
            "extraction_method": "ODS whole-workbook used-range parse with numeric-text coercion",
            "parser": "ods_numeric_text_used_range",
            "artifact_year": 2026,
        },
        "record_sets": record_sets,
    }
    return render(LISA_HEADER, payload)


NOTE_SENTENCE = (
    "In 2022 to 2023, 78% of cash ISA subscribers aged under 65 subscribed less than "
    "£12,000 to a cash ISA and 22% subscribed over £12,000."
)


def note_package() -> str:
    path, content = pinned_bytes(NOTE_DIR, NOTE_FILE, NOTE_SHA256)
    cells = source_cells_from_html_tables_and_text(content, artifact_meta(path))
    rows: dict[int, dict[int, object]] = {}
    for cell in cells:
        if cell.sheet_name == "document_numbers":
            rows.setdefault(cell.row_number, {})[cell.column_number] = cell.raw_value
    assert rows[1] == {1: "element_index", 2: "element_type", 3: "text", 4: "number_text", 5: "numeric_value"}
    sentence_rows = [row for row, values in rows.items() if values.get(3) == NOTE_SENTENCE]
    assert len(sentence_rows) == 7, sentence_rows
    by_number = {rows[row][4]: row for row in sentence_rows}
    element_index = rows[sentence_rows[0]][1]
    assert {rows[row][1] for row in sentence_rows} == {element_index}
    shared_filters, shared_constraints = category("isa_type", "cash", "ISA subscribed to")
    shared_constraints.append(constraint("age", "<", 65, "Aged under 65", "years"))
    entries = []
    for ordinal, (number, value_id, label, operator) in enumerate(
        (
            ("78", "under_12000", "Less than GBP 12,000", "<"),
            ("22", "over_12000", "Over GBP 12,000", ">"),
        )
    ):
        row = by_number[number]
        assert rows[row][5] == int(number)
        filters, constraints = category("cash_isa_subscription_band", value_id, "Cash ISA subscription band")
        constraints.append(
            constraint("cash_isa_subscription_amount", operator, 12000, "Cash ISA subscription relative to GBP 12,000", "gbp")
        )
        entries.append(
            row_entry(
                value_id=value_id,
                label=label,
                ordinal=ordinal,
                row_number=row,
                header_column="D",
                header=number,
                kind="detail",
                filters=filters,
                constraints=constraints,
                guards=[
                    guard("A", row, element_index, "HTML element index"),
                    guard("C", row, NOTE_SENTENCE, "paragraph text"),
                ],
            )
        )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": NOTE_PACKAGE_ID,
        "label": (
            "HMRC cash ISA limit reduction impact note: shares of cash ISA subscribers aged "
            "under 65 either side of GBP 12,000, 2022-23"
        ),
        "dimension_labels": {
            "cash_isa_subscription_band": "Cash ISA subscription relative to GBP 12,000",
            "isa_type": "ISA type",
        },
        "dimension_value_labels": {
            "cash_isa_subscription_band": {
                "under_12000": "Less than GBP 12,000",
                "over_12000": "Over GBP 12,000",
            },
            "isa_type": {"cash": "Cash ISA"},
        },
        "artifact": {
            "source_name": "hmrc",
            "source_table": (
                "Cash Individual Savings Account (ISA) limit reduction: tax information and "
                "impact note"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{NOTE_DIR}",
            "manifest": "manifest.yaml",
            "vintage": "tiin_2026_09",
            "extracted_at": "2026-10-28",
            "extraction_method": "HTML table and document-text number parse of the archived impact note",
            "parser": "html_tables_and_text",
            "artifact_year": 2026,
        },
        "record_sets": [
            {
                "record_set_id": f"{NOTE_PREFIX}.cash_subscribers_under_65.ty2022",
                "provenance_class": "model_output",
                "assertion": "observation",
                "record_set_spec_id": f"{NOTE_PREFIX}.cash_subscribers_under_65.ty2022.v1",
                "source_record_id_prefix": f"{NOTE_PREFIX}.cash_subscribers_under_65.ty2022",
                "sheet_name": "document_numbers",
                "period_type": "tax_year",
                "period": 2022,
                "period_coverage": coverage_tax_year(2022, "2022 to 2023"),
                **UK,
                "entity": "person",
                "entity_role": "cash_isa_subscriber",
                "domain": DOMAIN,
                "groupby_dimension": "cash_isa_subscription_band",
                "shared_filters": shared_filters,
                "shared_constraints": shared_constraints,
                "rows": entries,
                "measures": [
                    measure_entry(
                        measure_id="share_of_cash_subscribers",
                        label="Share of cash ISA subscribers aged under 65",
                        ordinal=0,
                        column="E",
                        header_row=1,
                        header="numeric_value",
                        concept="hmrc.cash_isa_subscribers_share",
                        unit="percent",
                        value_scale=1,
                        notes=(
                            "HMRC impact note, impact on individuals: " + NOTE_SENTENCE
                            + " The note names no data source."
                        ),
                        evidence_url=IMPACT_NOTE_URL,
                        aggregation="share",
                    )
                ],
            }
        ],
    }
    return render(NOTE_HEADER, payload)


PACKAGES = (
    (ISA_DIR, isa_package),
    (LISA_DIR, lisa_package),
    (NOTE_DIR, note_package),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the generated YAML with the committed files instead of writing.",
    )
    args = parser.parse_args()
    stale = []
    for directory, build in PACKAGES:
        path = REPO_ROOT / "packages" / directory / "source_package.yaml"
        text = build()
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(str(path.relative_to(REPO_ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    if stale:
        print("Stale generated packages: " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
