#!/usr/bin/env python3
"""Author the HMRC benefits in kind statistics, July 2026 package.

For PolicyEngine/uk-autumn-budget-dashboard-2026#316. Writes
``hmrc-benefits-in-kind-july-2026`` from the bytes its manifest pins under
``db/data``: Tables 1, 2A, 2C, 3A, 3B and 4 of HMRC's ``2026_Tables_1_to_4.ods``.
Nothing is downloaded and no value is computed.

Every selector is located by matching the publisher's text in Chronicle's own parse of
the file, and every match is asserted, so a re-run against different bytes fails
rather than drifting. The publisher's markers ('<0.5', '<2.5', '[note 3]') are asserted
cell by cell and emit no fact.

Usage::

    uv run python packages/hmrc/benefits_in_kind_july_2026/build_package.py
    uv run python packages/hmrc/benefits_in_kind_july_2026/build_package.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import yaml

from chronicle.sources.cells import SourceArtifactMetadata, source_cells_from_ods

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[2]

RELEASE_URL = (
    "https://www.gov.uk/government/statistics/benefits-in-kind-statistics-july-2026"
)
PACKAGE_ID = "hmrc-benefits-in-kind-july-2026"
DATA_DIR = "hmrc/benefits_in_kind_july_2026"
FILE = "2026_Tables_1_to_4.ods"
SHA256 = "a0ee56173ad12b784c3b986652f904c1229e165f5b27454b44ac9144cd98c678"
PREFIX = "hmrc.benefits_in_kind_july_2026"
SOURCE_TABLE = (
    "Benefits in kind statistics: July 2026, Tables 1 to 4: company car benefit and "
    "company car fuel benefit"
)
SHEETS = (
    "Contents",
    "Notes",
    "1_car_and_car_fuel_benefit",
    "2A_CO2_recipients",
    "2B_CO2_percentages",
    "2C_fuel_type_recipients",
    "2D_fuel_type_percentages",
    "2E_average_CO2",
    "3A_car_recipients_income",
    "3B_fuel_recipients_income",
    "4_car_region",
)

UK = {
    "geography_id": "K02000001",
    "geography_level": "country",
    "geography_name": "United Kingdom",
    "geography_vintage": "current",
}
DOMAIN = "company_car_benefits"
ENTITY_ROLE = "benefit_in_kind_recipient"
YEARS = tuple(range(2011, 2025))
YEAR_COLUMNS = dict(zip(YEARS, "BCDEFGHIJKLMNO"))
PROVISIONAL_YEAR = 2024
NEW_CO2_BANDS_FROM = 2020
# Zero-emission cars carried a zero-rate charge from April 2010 to April 2015 (note 3).
ZERO_RATE_YEARS = range(2011, 2015)

RECIPIENTS = "hmrc.benefit_in_kind_recipients"
TAXABLE_VALUE = "hmrc.benefit_in_kind_taxable_value"
MEAN_TAXABLE_VALUE = "hmrc.benefit_in_kind_mean_taxable_value"
INCOME_TAX = "hmrc.benefit_in_kind_income_tax_liability"
NIC = "hmrc.benefit_in_kind_class_1a_nic_liability"
MEAN_CO2 = "hmrc.company_car_mean_co2_emissions"
CO2_UNIT = "g_co2_per_km"

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


def pinned_bytes() -> tuple[Path, bytes]:
    path = REPO_ROOT / "db/data" / DATA_DIR / FILE
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    assert digest == SHA256, f"{path} has SHA-256 {digest}, expected {SHA256}"
    return path, content


def ods_sheets() -> dict[str, dict[tuple[int, str], object]]:
    """Map sheet -> (row, column letter) -> raw value, from Chronicle's own parse."""
    path, content = pinned_bytes()
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
    assert tuple(order) == SHEETS, order
    return sheets


def expect(grid: dict, row: int, column: str, value: object) -> None:
    assert grid.get((row, column)) == value, (
        row,
        column,
        grid.get((row, column)),
        value,
    )


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def text(grid: dict, row: int, column: str = "A") -> str:
    value = grid.get((row, column))
    assert isinstance(value, str), (row, column, value)
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


def guard(column: str, row: int, value: object, label: str) -> dict:
    return {"column": column, "row": row, "expected_value": value, "label": label}


def coverage_tax_year(opening: int, label: str, notes: str) -> dict:
    return {
        "start_date": f"{opening}-04-06",
        "end_date": f"{opening + 1}-04-05",
        "basis": "tax",
        "source_period_label": label,
        "notes": notes,
    }


def row_entry(
    *,
    value_id: str,
    label: str,
    ordinal: int,
    row_number: int,
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
        "expected_row_header_column": "A",
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


def measure_entry(
    *,
    measure_id: str,
    label: str,
    column: str,
    header_row: int,
    header: object,
    concept: str,
    unit: str,
    value_scale: int,
    notes: str,
    aggregation: str = "sum",
) -> dict:
    return {
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
        "concept_authority": "hmrc",
        "concept_evidence_url": RELEASE_URL,
        "concept_evidence_notes": notes,
        "unit": unit,
        "aggregation": aggregation,
        "value_scale": value_scale,
        "expected_cell_type": "number",
    }


def record_set(
    *,
    record_set_id: str,
    sheet: str,
    period: int,
    coverage: dict,
    provenance: str,
    groupby: str,
    rows: list[dict],
    measure: dict,
    shared: tuple[dict, list[dict]] | None = None,
    survey_instrument: str | None = None,
) -> dict:
    payload: dict = {
        "record_set_id": record_set_id,
        "provenance_class": provenance,
    }
    if survey_instrument is not None:
        payload["survey_instrument"] = survey_instrument
    payload |= {
        "assertion": "observation",
        "record_set_spec_id": f"{record_set_id}.v1",
        "source_record_id_prefix": record_set_id,
        "sheet_name": sheet,
        "period_type": "tax_year",
        "period": period,
        "period_coverage": coverage,
    }
    payload.update(UK)
    payload.update(
        {
            "entity": "person",
            "entity_role": ENTITY_ROLE,
            "domain": DOMAIN,
            "groupby_dimension": groupby,
        }
    )
    if shared is not None:
        filters, constraints = shared
        payload["shared_filters"] = filters
        if constraints:
            payload["shared_constraints"] = constraints
    payload["rows"] = rows
    payload["measures"] = [measure]
    return payload


# ------------------------------------------------- publisher vocabularies

BENEFIT_TYPES = {
    "car": "Company car benefit",
    "fuel": "Car fuel benefit",
    "all": "Car and fuel benefit",
}
BENEFIT_TYPE_LABEL = "Company car benefit type"


def benefit_type(value: str) -> tuple[dict, list[dict]]:
    return category("company_car_benefit_type", value, BENEFIT_TYPE_LABEL)


# Table 1: (measure id, label, concept, unit, scale, provenance, row headers for the car,
# fuel and car-and-fuel rows). The two average rows follow, car and fuel only.
TABLE_1 = (
    (
        "recipients",
        "Recipients",
        RECIPIENTS,
        "count",
        1000,
        "administrative",
        (
            "Car benefit recipients (thousands)",
            "Fuel benefit recipients (thousands)",
            "Car and fuel benefit recipients (thousands) [note 2]",
        ),
    ),
    (
        "taxable_value",
        "Taxable value",
        TAXABLE_VALUE,
        "gbp",
        1000000,
        "administrative",
        (
            "Car benefit total taxable value (£millions)",
            "Fuel benefit total taxable value (£millions)",
            "Car and fuel benefit total taxable value (£millions)",
        ),
    ),
    (
        "income_tax_liability",
        "Income Tax liability",
        INCOME_TAX,
        "gbp",
        1000000,
        "model_output",
        (
            "Car benefit total Income Tax liability (£millions)",
            "Fuel benefit total Income Tax liability (£millions)",
            "Car and car fuel benefit total Income Tax liability (£millions)",
        ),
    ),
    (
        "class_1a_nic_liability",
        "Class 1A NIC liability",
        NIC,
        "gbp",
        1000000,
        "model_output",
        (
            "Car benefit total NIC liability (£millions)",
            "Fuel benefit total NIC liability (£millions)",
            "Car and fuel benefit total NIC liability (£millions)",
        ),
    ),
)
TABLE_1_AVERAGES = (
    "Car benefit average taxable value (£)",
    "Fuel benefit average taxable value (£)",
)

CO2_BANDS_TO_2019 = (
    "Zero",
    "1 - 50",
    "51 - 75",
    "76 - 94",
    "95 - 104",
    "105 - 114",
    "115 - 124",
    "125 - 134",
    "135 - 144",
    "145 - 154",
    "155 - 164",
    "165 - 174",
    "175 g/km and over",
)
CO2_BANDS_FROM_2020 = (
    "Zero",
    "1 - 50",
    "51 - 54",
    "55 - 59",
    "60 - 64",
    "65 - 69",
    "70 - 74",
    "75 - 79",
    "80 - 84",
    "85 - 89",
    "90 - 94",
    "95 - 104",
    "105 - 114",
    "115 - 124",
    "125 - 134",
    "135 - 144",
    "145 - 154",
    "155 - 164",
    "165- 169",
    "170 g/km and over",
)
# Rows 4 to 27 of Table 2A, in sheet order, and its Total row.
CO2_SHEET_ROWS = (
    "Zero",
    "1 - 50",
    "51 - 75",
    "51 - 54",
    "55 - 59",
    "60 - 64",
    "65 - 69",
    "70 - 74",
    "76 - 94",
    "75 - 79",
    "80 - 84",
    "85 - 89",
    "90 - 94",
    "95 - 104",
    "105 - 114",
    "115 - 124",
    "125 - 134",
    "135 - 144",
    "145 - 154",
    "155 - 164",
    "165 - 174",
    "165- 169",
    "170 g/km and over",
    "175 g/km and over",
)

FUEL_TYPES = (
    (
        "diesel_including_hybrids",
        "Diesel (including hybrids)",
        "Diesel (including hybrids)",
    ),
    (
        "petrol_including_hybrids",
        "Petrol (including hybrids)",
        "Petrol (including hybrids)",
    ),
    ("fully_electric", "Fully Electric", "Fully electric"),
)

INCOME_RANGES_3A = (
    "£0 to £8,499",
    "£8,500 to £14,999",
    "£15,000 to £19,999",
    "£20,000 to £29,999",
    "£30,000 to £39,999",
    "£40,000 to £49,999",
    "£50,000 to £74,999",
    "£75,000 to £99,999",
    "£100,000 to £149,999",
    "£150,000 to £199,999",
    "£200,000 and over",
)
INCOME_RANGES_3B = (
    "£0 to £29,999",
    "£30,000 to £39,999",
    "£40,000 to £49,999",
    "£50,000 to £74,999",
    "£75,000 to £99,999",
    "£100,000 to £149,999",
    "£150,000 to £199,999",
    "£200,000 and over",
)

# Table 4's rows: publisher label -> geography. HMRC prints Northern Ireland, Scotland
# and Wales beside the English regions, and an 'Unknown' row.
REGIONS = (
    ("North East", "E12000001", "region"),
    ("North West", "E12000002", "region"),
    ("Yorkshire and The Humber", "E12000003", "region"),
    ("East Midlands", "E12000004", "region"),
    ("West Midlands", "E12000005", "region"),
    ("East of England", "E12000006", "region"),
    ("London", "E12000007", "region"),
    ("South East", "E12000008", "region"),
    ("South West", "E12000009", "region"),
    ("Northern Ireland", "N92000002", "country"),
    ("Scotland", "S92000003", "country"),
    ("Wales", "W92000004", "country"),
    ("Unknown", "hmrc:recipient_region_unknown", "statistical_scope"),
)

# Every cell HMRC fills with a marker instead of a number, in the six ported sheets.
MARKER_MEANINGS = {
    "<0.5": "fewer than 500 recipients, under half the table's unit of a thousand",
    "<2.5": "fewer than 2,500 recipients, under half the rounding base of 5 thousand",
    "[note 3]": "not available, as note 3 excludes zero-emission cars before April 2015",
}
EXPECTED_MARKERS = {
    "2A_CO2_recipients": {
        **{f"{column}4": "[note 3]" for column in "BCDE"},
        **{f"{column}5": "<0.5" for column in "BCD"},
        **{f"{column}6": "<0.5" for column in "BCF"},
    },
    "2C_fuel_type_recipients": {
        **{f"{column}7": "[note 3]" for column in "BCDE"},
        **{f"{column}7": "<2.5" for column in "FGHI"},
    },
    "3B_fuel_recipients_income": {"B7": "<2.5", "B8": "<2.5", "B13": "<2.5"},
}

# ------------------------------------------------------------ the notes


def year_label(opening: int) -> str:
    return f"{opening} to {opening + 1}"


def band_from_label(label: str) -> tuple[int, int | None]:
    """'Zero' -> (0, 0); '51 - 54' and '165- 169' -> (51, 54) and (165, 169);
    '170 g/km and over' -> (170, None)."""
    if label == "Zero":
        return 0, 0
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", label)
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        assert low < high, label
        return low, high
    match = re.fullmatch(r"(\d+) g/km and over", label)
    assert match, label
    return int(match.group(1)), None


def co2_value_id(low: int, high: int | None) -> str:
    if high == 0:
        return "co2_0"
    return f"co2_{low}_plus" if high is None else f"co2_{low}_to_{high}"


def co2_value_label(low: int, high: int | None) -> str:
    if high == 0:
        return "0 g/km"
    return f"{low} g/km and over" if high is None else f"{low} to {high} g/km"


def income_band(label: str) -> tuple[int, int | None]:
    """'£8,500 to £14,999' -> (8500, 14999); '£200,000 and over' -> (200000, None)."""
    match = re.fullmatch(r"£([\d,]+) to £([\d,]+)", label)
    if match:
        low, high = (int(part.replace(",", "")) for part in match.groups())
        assert low < high, label
        return low, high
    match = re.fullmatch(r"£([\d,]+) and over", label)
    assert match, label
    return int(match.group(1).replace(",", "")), None


def income_value_id(low: int, high: int | None) -> str:
    return f"income_{low}_plus" if high is None else f"income_{low}_to_{high}"


def assert_tiles(bands: list[tuple[int, int | None]]) -> None:
    """Each band starts one above the last one's top, and only the last is open."""
    for (_, previous_high), (low, _) in zip(bands, bands[1:]):
        assert previous_high is not None and low == previous_high + 1, bands
    assert bands[-1][1] is None, bands


def quote(sentence: str) -> str:
    return f"'{sentence}'"


SOURCES = (
    "HMRC compiles these from employers' P11D returns and, from 2017 to 2018, the company "
    "cars employers payroll and report through Real Time Information (RTI), counting a "
    "car reported both ways once (background quality report, section 3.5)."
)
LIABILITY_METHOD = (
    "HMRC estimates the liability for each Survey of Personal Incomes (SPI) case "
    "matched to the P11D and RTI records as the difference between the liabilities "
    "with and without the benefit, which 'effectively considers the benefit in kind as "
    "the final marginal element of income'; it grosses the cases up, divides by the "
    "grossed benefit to get an average rate per pound of benefit, and applies that "
    "rate to the whole taxable value (background quality report, section 3.5)."
)
PROJECTED_LIABILITIES = (
    "HMRC bases this year's Income Tax and NIC figures on projections of the Survey "
    "of Personal Incomes (commentary, section 1): the latest SPI is 'projected forward "
    "one year to help produce the provisional tax liability estimates that appear in "
    "Table 1' (background quality report, section 3.5)."
)
APPORTIONED = (
    "A recipient with more than one company car in the year is apportioned between "
    "the cars by the time each was held, so the rows add to recipients, not cars "
    "(background quality report, section 3.5)."
)
SURVEY_INSTRUMENT = (
    "Survey of Personal Incomes matched to employers' P11D and Real Time Information "
    "company car records"
)
SAMPLE_GROSSING = (
    "HMRC estimates this table from the Survey of Personal Incomes cases matched to the "
    "P11D and RTI records: it grosses them up with standard SPI grossing factors, then "
    "applies a further adjustment factor so that the total taxable value equals the "
    "figure from the full data, and the same factor scales the recipients (background "
    "quality report, section 3.5)."
)
AVERAGES_AS_PRINTED = (
    "The printed averages do not all equal the quotient of the printed, rounded "
    "taxable value and recipients, so they are ported as published, not derived."
)


def year_notes(opening: int, *, extra: str = "") -> str:
    """Caveats that belong to the reference year, recorded on period_coverage."""
    parts = []
    if opening in ZERO_RATE_YEARS:
        parts.append(
            "Cars emitting 0 g/km are not in these statistics for this year: from April "
            "2010 to April 2015 they carried a zero-rate charge (note 3), and HMRC "
            "includes electric cars only from 2015 to 2016 (commentary, section 6)."
        )
    if opening <= 2015:
        parts.append(
            "Before April 2016 a few employers payrolled benefits informally; their P11Ds "
            "were not processed electronically and are not in these statistics "
            "(commentary, section 8.1)."
        )
    else:
        detail = {
            2016: (
                "In 2016 to 2017 payrolled cars could not be reported through RTI, so "
                "every voluntarily payrolled car is missing."
            ),
            2017: (
                "In 2017 to 2018 reporting payrolled cars through RTI was voluntary, so "
                "the payrolled cars employers chose not to report are missing."
            ),
        }.get(
            opening,
            "From April 2018 payrolled cars must be reported through RTI, but HMRC "
            "finds compliance incomplete.",
        )
        parts.append(
            "From April 2016 employers could payroll company cars instead of reporting "
            f"them on a P11D. {detail} HMRC expects company car recipients to be "
            "under-reported in every year since April 2016 (commentary, section 8)."
        )
    if opening == PROVISIONAL_YEAR:
        parts.append(
            "HMRC marks 2024 to 2025 provisional (note 1): its figures come from an "
            "initial extract of the Expenses and Benefits data and may be revised."
        )
    if extra:
        parts.append(extra)
    return " ".join(parts)


def marker_sentence(markers: list[tuple[str, str]]) -> str:
    """'<0.5' for '1 - 50' and '51 - 75' ... -> one sentence, or '' when none."""
    if not markers:
        return ""
    by_marker: dict[str, list[str]] = {}
    for row_label, marker in markers:
        by_marker.setdefault(marker, []).append(quote(row_label))
    clauses = [
        f"'{marker}' ({MARKER_MEANINGS[marker]}) for {listed(rows)}"
        for marker, rows in by_marker.items()
    ]
    return (
        "HMRC prints " + "; ".join(clauses) + ": those cells emit no fact, not a zero."
    )


def listed(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def guarded_sentence(guarded: list[tuple[str, str]], measure_label: str) -> str:
    """Rows whose recipients carry a marker but whose measure is a number."""
    if not guarded:
        return ""
    (marker,) = {marker for _, marker in guarded}
    rows = listed([quote(label) for label, _ in guarded])
    return (
        f"HMRC prints '{marker}' ({MARKER_MEANINGS[marker]}) for the recipients of "
        f"{rows}: their {measure_label.lower()} cells are ported, each with the "
        "marker as a guard cell, and their recipients emit no fact."
    )


# ----------------------------------------------------------------- tables


def check_markers(sheets: dict) -> None:
    for sheet, expected in EXPECTED_MARKERS.items():
        found = {
            f"{column}{row}": value
            for (row, column), value in sheets[sheet].items()
            if value in MARKER_MEANINGS
        }
        assert found == expected, (sheet, found)


def check_notes(grid: dict) -> dict[int, str]:
    expect(grid, 1, "A", "Note")
    expect(grid, 1, "B", "Description")
    notes = {}
    for number in (1, 2, 3):
        expect(grid, number + 1, "A", number)
        notes[number] = text(grid, number + 1, "B")
    assert notes[1].startswith(
        "All figures given for tax year 2024 to 2025 are based on an initial extract"
    ), notes[1]
    assert notes[2].startswith(
        "All recipients of company car fuel benefit must also be in receipt"
    ), notes[2]
    assert notes[3].startswith(
        "Between April 2010 and April 2015 there was a zero-rate charge"
    ), notes[3]
    expect(grid, 5, "A", "End of worksheet")
    return notes


def year_headers(grid: dict, header_row: int) -> dict[int, str]:
    headers = {}
    for opening, column in YEAR_COLUMNS.items():
        expected = year_label(opening) + (
            " [note 1]" if opening == PROVISIONAL_YEAR else ""
        )
        expect(grid, header_row, column, expected)
        headers[opening] = expected
    assert (header_row, "P") not in grid
    return headers


def table_1(grid: dict, notes: dict[int, str]) -> tuple[list[dict], dict]:
    sheet = "1_car_and_car_fuel_benefit"
    title = "Table 1: Company car benefit and company car fuel benefit (time series)"
    expect(grid, 1, "A", title)
    incomplete = text(grid, 3)
    assert incomplete.startswith("The data in this table are not fully complete."), (
        incomplete
    )
    rounding = "Numbers and amounts are rounded to the nearest 10"
    expect(grid, 4, "A", rounding)
    expect(grid, 5, "A", "Tax Year")
    headers = year_headers(grid, 5)
    row = 6
    record_sets = []
    ported: dict = {}
    for measure_id, label, concept, unit, scale, provenance, row_headers in TABLE_1:
        first = row
        for offset, header in enumerate(row_headers):
            expect(grid, first + offset, "A", header)
        row += len(row_headers)
        if measure_id == "recipients":
            unit_text = (
                "recipients are in thousands, so the rounding is to the nearest 10,000. "
                "The car and fuel row counts people receiving either benefit, and it "
                "prints the same as the car row in every year; note 2: "
                + quote(notes[2])
            )
            method = "Individuals reported as receiving the benefit. " + SOURCES
        elif measure_id == "taxable_value":
            unit_text = (
                "amounts are in GBP million, so the rounding is to the nearest GBP 10 "
                "million. A car's taxable value is its list price with accessories times "
                "the appropriate percentage for its CO2 emissions, and car fuel benefit "
                "is the car fuel benefit multiplier times the same percentage (background "
                "quality report, section 2.4). The car and fuel row is their sum."
            )
            method = "The taxable value of the benefits reported. " + SOURCES
        else:
            unit_text = (
                "amounts are in GBP million, so the rounding is to the nearest GBP 10 "
                "million. The car and fuel row is their sum."
            )
            method = LIABILITY_METHOD
            if measure_id == "class_1a_nic_liability":
                method = (
                    "Class 1A National Insurance contributions, which employers pay on "
                    "the benefits; employees pay no NICs on car or car fuel benefit "
                    "(background quality report, section 2.4). " + method
                )
        for opening in YEARS:
            column = YEAR_COLUMNS[opening]
            for offset in range(3):
                assert is_number(grid.get((first + offset, column))), (
                    first + offset,
                    column,
                )
            measure_notes = (
                f"Table 1, {label}, {headers[opening]}. {method} "
                + quote(incomplete)
                + " "
                + quote(rounding)
                + ": "
                + unit_text
            )
            extra = ""
            if provenance == "model_output" and opening == PROVISIONAL_YEAR:
                extra = PROJECTED_LIABILITIES
            rows = []
            for ordinal, value_id in enumerate(("car", "fuel", "all")):
                filters, constraints = benefit_type(value_id)
                rows.append(
                    row_entry(
                        value_id=value_id,
                        label=BENEFIT_TYPES[value_id],
                        ordinal=ordinal,
                        row_number=first + ordinal,
                        header=row_headers[ordinal],
                        kind="total" if value_id == "all" else "detail",
                        filters=filters,
                        constraints=constraints,
                        guards=[
                            guard("A", 1, title, "Table title"),
                            guard("A", 4, rounding, "Rounding"),
                        ],
                    )
                )
                ported[(measure_id, value_id, opening)] = grid[
                    (first + ordinal, column)
                ]
            record_sets.append(
                record_set(
                    record_set_id=f"{PREFIX}.table1.{measure_id}.ty{opening}",
                    sheet=sheet,
                    period=opening,
                    coverage=coverage_tax_year(
                        opening, headers[opening], year_notes(opening, extra=extra)
                    ),
                    provenance=provenance,
                    groupby="company_car_benefit_type",
                    rows=rows,
                    measure=measure_entry(
                        measure_id=measure_id,
                        label=label,
                        column=column,
                        header_row=5,
                        header=headers[opening],
                        concept=concept,
                        unit=unit,
                        value_scale=scale,
                        notes=measure_notes,
                    ),
                )
            )
    average_row = row
    for offset, header in enumerate(TABLE_1_AVERAGES):
        expect(grid, average_row + offset, "A", header)
    expect(grid, average_row + len(TABLE_1_AVERAGES), "A", "End of worksheet")
    for opening in YEARS:
        column = YEAR_COLUMNS[opening]
        rows = []
        for ordinal, value_id in enumerate(("car", "fuel")):
            value = grid.get((average_row + ordinal, column))
            assert is_number(value), (average_row + ordinal, column)
            filters, constraints = benefit_type(value_id)
            rows.append(
                row_entry(
                    value_id=value_id,
                    label=BENEFIT_TYPES[value_id],
                    ordinal=ordinal,
                    row_number=average_row + ordinal,
                    header=TABLE_1_AVERAGES[ordinal],
                    kind="detail",
                    filters=filters,
                    constraints=constraints,
                    guards=[
                        guard("A", 1, title, "Table title"),
                        guard("A", 4, rounding, "Rounding"),
                    ],
                )
            )
            ported[("average_taxable_value", value_id, opening)] = value
        record_sets.append(
            record_set(
                record_set_id=f"{PREFIX}.table1.average_taxable_value.ty{opening}",
                sheet=sheet,
                period=opening,
                coverage=coverage_tax_year(
                    opening, headers[opening], year_notes(opening)
                ),
                provenance="administrative",
                groupby="company_car_benefit_type",
                rows=rows,
                measure=measure_entry(
                    measure_id="average_taxable_value",
                    label="Average taxable value",
                    column=column,
                    header_row=5,
                    header=headers[opening],
                    concept=MEAN_TAXABLE_VALUE,
                    unit="gbp",
                    value_scale=1,
                    notes=(
                        f"Table 1, Average taxable value, {headers[opening]}: HMRC's "
                        "average taxable value per recipient of each benefit, in GBP. "
                        f"{SOURCES} {quote(incomplete)} {quote(rounding)}: the averages "
                        f"are rounded to the nearest GBP 10. {AVERAGES_AS_PRINTED}"
                    ),
                    aggregation="mean",
                ),
            )
        )
    assert len(record_sets) == 5 * len(YEARS)
    return record_sets, ported


def table_2a(grid: dict, table_1_cells: dict) -> list[dict]:
    sheet = "2A_CO2_recipients"
    title = (
        "Table 2A: Company car benefit recipients as reported to HMRC by vehicle CO2 "
        "emission (time series)"
    )
    expect(grid, 1, "A", title)
    units = (
        "Recipients of company car benefit (thousands) from tax year 2011 to 2012 to "
        "tax year 2024 to 2025"
    )
    expect(grid, 2, "A", units)
    expect(grid, 3, "A", "CO2 emission band")
    headers = year_headers(grid, 3)
    rows_by_label = {}
    for offset, label in enumerate(CO2_SHEET_ROWS):
        expect(grid, 4 + offset, "A", label)
        rows_by_label[label] = 4 + offset
    total_row = 4 + len(CO2_SHEET_ROWS)
    expect(grid, total_row, "A", "Total")
    expect(grid, total_row + 1, "A", "End of worksheet")
    for scheme in (CO2_BANDS_TO_2019, CO2_BANDS_FROM_2020):
        assert_tiles([band_from_label(label) for label in scheme])
    record_sets = []
    for opening in YEARS:
        column = YEAR_COLUMNS[opening]
        scheme = (
            CO2_BANDS_FROM_2020 if opening >= NEW_CO2_BANDS_FROM else CO2_BANDS_TO_2019
        )
        filled = [
            label for label in CO2_SHEET_ROWS if (rows_by_label[label], column) in grid
        ]
        # Each year prints exactly one scheme's bands, in sheet order.
        assert filled == [label for label in CO2_SHEET_ROWS if label in scheme], (
            opening,
            filled,
        )
        # The Total row restates Table 1's car benefit recipients: ported from Table 1.
        assert (
            grid[(total_row, column)] == table_1_cells[("recipients", "car", opening)]
        )
        rows = []
        markers = []
        for label in scheme:
            row = rows_by_label[label]
            value = grid[(row, column)]
            if not is_number(value):
                assert value in MARKER_MEANINGS, (row, column, value)
                markers.append((label, value))
                continue
            low, high = band_from_label(label)
            value_id = co2_value_id(low, high)
            filters, constraints = category(
                "company_car_co2_band", value_id, "Company car CO2 emission band"
            )
            variable = "company_car_co2_emissions"
            if high == 0:
                constraints.append(
                    constraint(variable, "==", 0, "CO2 emissions", CO2_UNIT)
                )
            else:
                if low == 1:
                    constraints.append(
                        constraint(
                            variable, ">", 0, "CO2 emissions lower bound", CO2_UNIT
                        )
                    )
                else:
                    constraints.append(
                        constraint(
                            variable, ">=", low, "CO2 emissions lower bound", CO2_UNIT
                        )
                    )
                if high is not None:
                    constraints.append(
                        constraint(
                            variable,
                            "<",
                            high + 1,
                            "CO2 emissions upper bound",
                            CO2_UNIT,
                        )
                    )
            rows.append(
                row_entry(
                    value_id=value_id,
                    label=co2_value_label(low, high),
                    ordinal=len(rows),
                    row_number=row,
                    header=label,
                    kind="detail",
                    filters=filters,
                    constraints=constraints,
                    guards=[
                        guard("A", 1, title, "Table title"),
                        guard("A", 2, units, "Units"),
                    ],
                )
            )
        scheme_text = (
            "the bands printed from 2020 to 2021: five-gram bands from 51 to 94 g/km, "
            "and 165 to 169 and 170 g/km and over above 164"
            if opening >= NEW_CO2_BANDS_FROM
            else "the bands printed to 2019 to 2020: 51 to 75 and 76 to 94 g/km below "
            "95, and 165 to 174 and 175 g/km and over above 164"
        )
        notes = " ".join(
            part
            for part in (
                f"Table 2A, recipients of company car benefit by the CO2 emissions of the "
                f"car, {headers[opening]}, in thousands. {SOURCES} {APPORTIONED} Missing "
                "or implausible CO2 figures are imputed where other data allow, typically "
                "for under 2% of car benefits (section 3.5). From April 2020 the CO2 "
                "figures are WLTP measurements; before, they are NEDC figures, WLTP "
                "results converted back to NEDC equivalents from September 2018 "
                f"(background quality report, section 2.4). This year uses {scheme_text}. "
                "The sheet gives no rounding rule; its band cells are whole thousands. "
                "Its 'Total' row restates Table 1's car benefit recipients and is ported "
                "from Table 1.",
                marker_sentence(markers),
            )
            if part
        )
        record_sets.append(
            record_set(
                record_set_id=f"{PREFIX}.table2a.recipients.ty{opening}",
                sheet=sheet,
                period=opening,
                coverage=coverage_tax_year(
                    opening, headers[opening], year_notes(opening)
                ),
                provenance="administrative",
                groupby="company_car_co2_band",
                rows=rows,
                measure=measure_entry(
                    measure_id="recipients",
                    label="Recipients",
                    column=column,
                    header_row=3,
                    header=headers[opening],
                    concept=RECIPIENTS,
                    unit="count",
                    value_scale=1000,
                    notes=notes,
                ),
                shared=benefit_type("car"),
            )
        )
    return record_sets


def table_2c(grid: dict, table_1_cells: dict) -> list[dict]:
    sheet = "2C_fuel_type_recipients"
    title = (
        "Table 2C: Company car benefit recipients as reported to HMRC by vehicle fuel "
        "type (time series)"
    )
    expect(grid, 1, "A", title)
    expect(
        grid,
        2,
        "A",
        "Recipients of company car benefit (thousands) from tax year 2011 to 2012 to "
        "tax year 2024 to 2025",
    )
    rounding = "Numbers are rounded to the nearest 5"
    expect(grid, 3, "A", rounding)
    expect(grid, 4, "A", "Type of fuel")
    headers = year_headers(grid, 4)
    for offset, (_, header, _) in enumerate(FUEL_TYPES):
        expect(grid, 5 + offset, "A", header)
    total_row = 5 + len(FUEL_TYPES)
    expect(grid, total_row, "A", "Total")
    expect(grid, total_row + 1, "A", "End of worksheet")
    record_sets = []
    for opening in YEARS:
        column = YEAR_COLUMNS[opening]
        assert (
            grid[(total_row, column)] == table_1_cells[("recipients", "car", opening)]
        )
        rows = []
        markers = []
        for offset, (value_id, header, label) in enumerate(FUEL_TYPES):
            value = grid[(5 + offset, column)]
            if not is_number(value):
                assert value in MARKER_MEANINGS, (5 + offset, column, value)
                markers.append((header, value))
                continue
            filters, constraints = category(
                "company_car_fuel_type", value_id, "Company car fuel type"
            )
            rows.append(
                row_entry(
                    value_id=value_id,
                    label=label,
                    ordinal=len(rows),
                    row_number=5 + offset,
                    header=header,
                    kind="detail",
                    filters=filters,
                    constraints=constraints,
                    guards=[
                        guard("A", 1, title, "Table title"),
                        guard("A", 3, rounding, "Rounding"),
                    ],
                )
            )
        notes = " ".join(
            part
            for part in (
                f"Table 2C, recipients of company car benefit by the fuel type of the car, "
                f"{headers[opening]}, in thousands: {quote(rounding)}, so to the nearest "
                f"5,000. {SOURCES} {APPORTIONED} Missing or implausible fuel types are "
                "imputed where other data allow (section 3.5). HMRC classes a diesel car "
                "meeting the Euro IV or RDE2 standard as diesel even where no diesel "
                "supplement applies (background quality report, section 2.4). The rows "
                "are HMRC's own: 'Diesel (including hybrids)', 'Petrol (including "
                "hybrids)' and 'Fully Electric'. Its 'Total' row restates Table 1's car "
                "benefit recipients and is ported from Table 1.",
                marker_sentence(markers),
            )
            if part
        )
        record_sets.append(
            record_set(
                record_set_id=f"{PREFIX}.table2c.recipients.ty{opening}",
                sheet=sheet,
                period=opening,
                coverage=coverage_tax_year(
                    opening, headers[opening], year_notes(opening)
                ),
                provenance="administrative",
                groupby="company_car_fuel_type",
                rows=rows,
                measure=measure_entry(
                    measure_id="recipients",
                    label="Recipients",
                    column=column,
                    header_row=4,
                    header=headers[opening],
                    concept=RECIPIENTS,
                    unit="count",
                    value_scale=1000,
                    notes=notes,
                ),
                shared=benefit_type("car"),
            )
        )
    return record_sets


def table_2e(grid: dict) -> list[dict]:
    sheet = "2E_average_CO2"
    title = (
        "Table 2E: Average CO2 emissions of company cars as reported to HMRC (time "
        "series)"
    )
    expect(grid, 1, "A", title)
    units = (
        "Average CO2 emissions of company cars (in g/km) from tax year 2010 to 2011 to "
        "2024 to 2025"
    )
    expect(grid, 2, "A", units)
    expect(grid, 3, "A", "Tax Year")
    headers = year_headers(grid, 3)
    row_header = "Average CO2 emissions (g/km)"
    expect(grid, 4, "A", row_header)
    expect(grid, 5, "A", "End of worksheet")
    record_sets = []
    for opening in YEARS:
        column = YEAR_COLUMNS[opening]
        assert is_number(grid.get((4, column))), (4, column)
        filters, constraints = benefit_type("car")
        rows = [
            row_entry(
                value_id="car",
                label=BENEFIT_TYPES["car"],
                ordinal=0,
                row_number=4,
                header=row_header,
                kind="detail",
                filters=filters,
                constraints=constraints,
                guards=[
                    guard("A", 1, title, "Table title"),
                    guard("A", 2, units, "Units"),
                ],
            )
        ]
        notes = (
            "Table 2E, average CO2 emissions of company cars as reported to HMRC, "
            f"{headers[opening]}, in g/km. The background quality report gives the "
            "unit of Table 2E's averages as a company car benefit (section 2.5). "
            f"{SOURCES} Missing or implausible CO2 figures are imputed where other data "
            "allow, typically for under 2% of car benefits (section 3.5). From April "
            "2020 the CO2 figures are WLTP measurements; before, they are NEDC figures, "
            "WLTP results converted back to NEDC equivalents from September 2018 "
            "(background quality report, section 2.4). Electric cars are in the average "
            "from 2015 to 2016 (commentary, sections 2 and 6). The sheet gives no "
            "rounding rule; its cells are whole g/km. Its subtitle reads 'from tax year "
            "2010 to 2011', but its first column is 2011 to 2012."
        )
        record_sets.append(
            record_set(
                record_set_id=f"{PREFIX}.table2e.average_co2_emissions.ty{opening}",
                sheet=sheet,
                period=opening,
                coverage=coverage_tax_year(
                    opening, headers[opening], year_notes(opening)
                ),
                provenance="administrative",
                groupby="company_car_benefit_type",
                rows=rows,
                measure=measure_entry(
                    measure_id="average_co2_emissions",
                    label="Average CO2 emissions",
                    column=column,
                    header_row=3,
                    header=headers[opening],
                    concept=MEAN_CO2,
                    unit=CO2_UNIT,
                    value_scale=1,
                    notes=notes,
                    aggregation="mean",
                ),
            )
        )
    return record_sets


TABLE_3_4_MEASURES = (
    (
        "recipients",
        "Recipients",
        "B",
        "Recipients (thousands)",
        RECIPIENTS,
        "count",
        1000,
        "sum",
    ),
    (
        "taxable_value",
        "Taxable value",
        "C",
        "Taxable value (£millions)",
        TAXABLE_VALUE,
        "gbp",
        1000000,
        "sum",
    ),
    (
        "average_taxable_value",
        "Average taxable value",
        "D",
        "Average value (£)",
        MEAN_TAXABLE_VALUE,
        "gbp",
        1,
        "mean",
    ),
)


def tables_3_and_4(
    grid: dict,
    *,
    table: str,
    sheet: str,
    title: str,
    benefit: str,
    rounding: str,
    first_column_header: str,
    row_specs: list[tuple[str, str, str, dict, list[dict], dict | None]],
    table_1_cells: dict,
    groupby: str,
    describe: str,
    all_average_equals_table_1: bool,
) -> list[dict]:
    """Tables 3A, 3B and 4: one record set per measure, 2024 to 2025 only.

    ``row_specs`` holds (publisher label, value id, label, filters, constraints,
    geography) for each row above 'All'."""
    expect(grid, 1, "A", title)
    period_text = "Tax year 2024 to 2025 [note 1]"
    expect(grid, 2, "A", period_text)
    grossed = text(grid, 3)
    assert grossed.startswith(
        "The figures in this table are grossed up from the sample which contains income information."
    ), grossed
    assert grossed.endswith(
        "the total number of recipients will not necessarily match the figure in Table 1."
    ), grossed
    incomplete = text(grid, 4)
    assert incomplete.startswith("The data in this table are not fully complete."), (
        incomplete
    )
    expect(grid, 5, "A", rounding)
    expect(grid, 6, "A", first_column_header)
    for _, _, column, header, *_ in TABLE_3_4_MEASURES:
        expect(grid, 6, column, header)
    assert (6, "E") not in grid
    for offset, spec in enumerate(row_specs):
        expect(grid, 7 + offset, "A", spec[0])
    all_row = 7 + len(row_specs)
    expect(grid, all_row, "A", "All")
    expect(grid, all_row + 1, "A", "End of worksheet")
    # The 'All' row is HMRC's grossed total, which need not match Table 1. Its
    # recipients and taxable value print the same as Table 1's 2024 to 2025 cells, which
    # are ported, and its average matches Table 1's only where the argument says so.
    for measure_id, column in (("recipients", "B"), ("taxable_value", "C")):
        assert (
            grid[(all_row, column)]
            == table_1_cells[(measure_id, benefit, PROVISIONAL_YEAR)]
        ), (table, measure_id)
    table_1_average = table_1_cells[
        ("average_taxable_value", benefit, PROVISIONAL_YEAR)
    ]
    assert (grid[(all_row, "D")] == table_1_average) == all_average_equals_table_1, (
        table,
        grid[(all_row, "D")],
        table_1_average,
    )
    record_sets = []
    for (
        measure_id,
        label,
        column,
        header,
        concept,
        unit,
        scale,
        aggregation,
    ) in TABLE_3_4_MEASURES:
        rows = []
        markers = []
        guarded = []
        for offset, (
            publisher,
            value_id,
            row_label,
            filters,
            constraints,
            geography,
        ) in enumerate(row_specs):
            row = 7 + offset
            value = grid[(row, column)]
            guards = [
                guard("A", 1, title, "Table title"),
                guard("A", 2, period_text, "Tax year"),
                guard("A", 5, rounding, "Rounding"),
            ]
            if not is_number(value):
                assert value in MARKER_MEANINGS, (row, column, value)
                markers.append((publisher, value))
                continue
            recipients = grid[(row, "B")]
            if measure_id != "recipients" and not is_number(recipients):
                guarded.append((publisher, recipients))
                guards.append(
                    guard(
                        "B",
                        row,
                        recipients,
                        f"Recipients printed '{recipients}' ("
                        + MARKER_MEANINGS[recipients]
                        + "): no recipients fact",
                    )
                )
            rows.append(
                row_entry(
                    value_id=value_id,
                    label=row_label,
                    ordinal=len(rows),
                    row_number=row,
                    header=publisher,
                    kind="detail",
                    filters=filters,
                    constraints=constraints,
                    geography=geography,
                    guards=guards,
                )
            )
        if measure_id == "average_taxable_value":
            measure_text = (
                "HMRC's average taxable value per recipient, in GBP, rounded as the "
                f"sheet states. {AVERAGES_AS_PRINTED} Its 'All' row is not ported: "
                "it would share the key of Table 1's 2024 to 2025 average"
                + (
                    ", and prints the same value."
                    if all_average_equals_table_1
                    else ", and prints a different value, so HMRC's grossed recipients "
                    "for this table differ from Table 1's before rounding."
                )
            )
        else:
            measure_text = (
                "Its 'All' row prints the same value as Table 1's 2024 to 2025 cell, "
                "which is ported, so it is not ported again."
            )
        notes = " ".join(
            part
            for part in (
                f"Table {table}, {period_text}, {header}: {describe} "
                + quote(grossed)
                + " "
                + SAMPLE_GROSSING
                + " "
                + quote(incomplete)
                + " "
                + quote(rounding)
                + ". "
                + measure_text,
                marker_sentence(markers),
                guarded_sentence(guarded, label),
            )
            if part
        )
        record_sets.append(
            record_set(
                record_set_id=f"{PREFIX}.table{table.lower()}.{measure_id}.ty{PROVISIONAL_YEAR}",
                sheet=sheet,
                period=PROVISIONAL_YEAR,
                coverage=coverage_tax_year(
                    PROVISIONAL_YEAR,
                    period_text,
                    year_notes(PROVISIONAL_YEAR),
                ),
                provenance="survey_aggregate",
                survey_instrument=SURVEY_INSTRUMENT,
                groupby=groupby,
                rows=rows,
                measure=measure_entry(
                    measure_id=measure_id,
                    label=label,
                    column=column,
                    header_row=6,
                    header=header,
                    concept=concept,
                    unit=unit,
                    value_scale=scale,
                    notes=notes,
                    aggregation=aggregation,
                ),
                shared=benefit_type(benefit),
            )
        )
    return record_sets


INCOME_DEFINITION = (
    "Total income is 'inclusive of the benefit amount' and 'comprises all incomes "
    "assessable for Income Tax' (background quality report, section 2.4)."
)


def income_row_specs(labels: tuple[str, ...]) -> list[tuple]:
    bands = [income_band(label) for label in labels]
    assert bands[0][0] == 0
    assert_tiles(bands)
    specs = []
    for label, (low, high) in zip(labels, bands):
        value_id = income_value_id(low, high)
        filters, constraints = category(
            "benefit_in_kind_income_band", value_id, "Range of total income"
        )
        if low > 0:
            constraints.append(
                constraint("total_income", ">=", low, "Total income lower bound", "gbp")
            )
        if high is not None:
            constraints.append(
                constraint(
                    "total_income", "<", high + 1, "Total income upper bound", "gbp"
                )
            )
        specs.append((label, value_id, label, filters, constraints, None))
    return specs


def region_row_specs() -> list[tuple]:
    specs = []
    for label, geography_id, level in REGIONS:
        geography = {
            "geography_id": geography_id,
            "geography_level": level,
            "geography_name": label,
            "geography_vintage": "current",
        }
        value_id = geography_id.removeprefix("hmrc:")
        specs.append((label, value_id, label, {}, [], geography))
    return specs


def table_3a(grid: dict, table_1_cells: dict) -> list[dict]:
    return tables_3_and_4(
        grid,
        table="3A",
        sheet="3A_car_recipients_income",
        title="Table 3A: Income breakdown of recipients of company cars",
        benefit="car",
        rounding=(
            "Numbers and amounts less than 10 are rounded to the nearest 5; those "
            "greater than 10 are rounded to the nearest 10"
        ),
        first_column_header="Income Range",
        row_specs=income_row_specs(INCOME_RANGES_3A),
        table_1_cells=table_1_cells,
        groupby="benefit_in_kind_income_band",
        describe=(
            "company car benefit by range of total income of the recipient. "
            + INCOME_DEFINITION
        ),
        all_average_equals_table_1=True,
    )


def table_3b(grid: dict, table_1_cells: dict) -> list[dict]:
    record_sets = tables_3_and_4(
        grid,
        table="3B",
        sheet="3B_fuel_recipients_income",
        title="Table 3B: Income breakdown of recipients of employer-provided car fuel",
        benefit="fuel",
        rounding=(
            "Numbers and amounts less than 10 are rounded to the nearest 5; those "
            "greater than 10 are rounded to the nearest 10"
        ),
        first_column_header="Income Range",
        row_specs=income_row_specs(INCOME_RANGES_3B),
        table_1_cells=table_1_cells,
        groupby="benefit_in_kind_income_band",
        describe=(
            "car fuel benefit by range of total income of the recipient, in bands HMRC "
            "groups more coarsely than Table 3A's. " + INCOME_DEFINITION
        ),
        all_average_equals_table_1=True,
    )
    assert "Some income bands have been grouped" in text(grid, 4)
    return record_sets


def table_4(grid: dict, table_1_cells: dict) -> list[dict]:
    return tables_3_and_4(
        grid,
        table="4",
        sheet="4_car_region",
        title="Table 4: Regional breakdown of recipients of company cars",
        benefit="car",
        rounding="Numbers are rounded to the nearest 5 and amounts to the nearest 10",
        first_column_header="Region",
        row_specs=region_row_specs(),
        table_1_cells=table_1_cells,
        groupby="geography",
        describe=(
            "company car benefit by region of the recipient, with Northern Ireland, "
            "Scotland and Wales beside the English regions and an 'Unknown' row."
        ),
        all_average_equals_table_1=False,
    )


# ------------------------------------------------------------- package

HEADER = """\
# HMRC Benefits in kind statistics: July 2026 (published 15 July 2026), the Tables 1 to 4
# workbook, for PolicyEngine/uk-autumn-budget-dashboard-2026#316: Budget 2026 raises
# company car tax by one percentage point in every band from 2030-31, policyengine-uk
# 2.165.0 (PolicyEngine/policyengine-uk#2750) models the company car and car fuel
# benefits, and Microcosm vendors these facts to fill and measure its company car inputs.
# Written by build_package.py in this directory from the pinned workbook; edit that, not
# this.
#
# Ported: Table 1 (car and car fuel benefit recipients, taxable value, average taxable
# value, and Income Tax and NIC liabilities, 2011-12 to 2024-25), Table 2A (car benefit
# recipients by CO2 emission band, 2011-12 to 2024-25), Table 2C (car benefit recipients
# by fuel type, 2011-12 to 2024-25), Table 2E (average CO2 emissions of company cars,
# 2011-12 to 2024-25), Tables 3A and 3B (car and car fuel benefit recipients, taxable
# value and average taxable value by range of total income, 2024-25) and Table 4 (car
# benefit recipients, taxable value and average taxable value by region, 2024-25). Not
# ported: Tables 2B and 2D, which restate Tables 2A and 2C as percentages of each year's
# total to the whole percent ('<0.5%' below half a percent), so the ported counts are the
# finer series; the 'All' rows of Tables 3A, 3B and 4 (below); and Table 5 (all Class 1A
# benefits, a separate workbook).
#
# The averages are ported as published, not derived: HMRC's printed averages do not all
# equal the quotient of the printed, rounded cells. Table 1's 2024-25 car benefit average
# is GBP 3,330, where GBP 3,070 million over 920 thousand recipients gives GBP 3,337.
#
# Table 2A's CO2 bands changed in 2020-21 with the appropriate-percentage bands. To
# 2019-20 it prints 51-75, 76-94, 165-174 and 175 g/km and over; from 2020-21, five-gram
# bands from 51-54 to 90-94, and 165-169 and 170 g/km and over. Both schemes share zero,
# 1-50 and the ten-gram bands from 95-104 to 155-164. Each year carries the bands it
# prints, asserted to be exactly one scheme, and each band carries company_car_co2_emissions
# bounds, so bands of the two schemes never share a key.
#
# Publisher markers emit no fact, never a zero: '<0.5' (Table 2A, fewer than 500
# recipients), '<2.5' (Tables 2C and 3B, fewer than 2,500) and '[note 3]' (Tables 2A and
# 2C: cars emitting 0 g/km, excluded while they carried a zero-rate charge, 2011-12 to
# 2014-15). The notes of each affected measure name its marked cells, and Table 3B's three
# bands whose recipients are '<2.5' keep their taxable value and average with the marker
# as a guard cell. Rounding is each sheet's own and each measure's notes quote it: Table 1
# to the nearest 10 (10,000 recipients, GBP 10 million, GBP 10 for the averages), Table 2A
# whole thousands and Table 2E whole g/km with no stated rule, Table 2C to the nearest 5
# thousand, Tables 3A and 3B to the nearest 5 below 10 and the nearest 10 above, and Table
# 4 recipients to the nearest 5 thousand and amounts to the nearest 10.
#
# Recipients, taxable values and averages in Table 1, and Tables 2A, 2C and 2E, come from
# employers' P11D returns and, from 2017-18, the company cars they payroll and report
# through Real Time Information: administrative. HMRC estimates the Income Tax and NIC
# liabilities by matching the Survey of Personal Incomes to those records and comparing
# liabilities with and without the benefit, and for 2024-25 projects the latest SPI
# forward a year to do so: model_output. Tables 3A, 3B and 4 are grossed up from that
# matched sample with SPI grossing factors and scaled to the full data's taxable value:
# survey_aggregate, with the matched SPI as survey instrument, as hmrc-isa-statistics-2026
# classes its SPI-matched tables. NICs are the employers' Class 1A contributions. 2024-25
# is provisional (note 1), and HMRC warns that payrolled cars have been under-reported
# since April 2016; both caveats ride on each record set's period_coverage notes, as does
# the exclusion of zero-emission cars before 2015-16. The notes cite the release's
# commentary,
# https://www.gov.uk/government/statistics/benefits-in-kind-statistics-july-2026/benefit-in-kind-statistics-commentary-july-2026,
# and HMRC's background quality report for these statistics,
# https://www.gov.uk/government/statistics/benefits-in-kind-statistics-june-2023/benefit-in-kind-statistics-background-quality-report.
#
# Totals printed more than once are ported once, and build_package.py asserts every copy
# equal: the Total rows of Tables 2A and 2C restate Table 1's car benefit recipients in
# every year. The 'All' rows of Tables 3A, 3B and 4 are HMRC's grossed totals, which HMRC
# says need not match Table 1. Their recipients and taxable value print the same as Table
# 1's 2024-25 car or fuel cells, so they are not ported again. Their averages are not
# ported either, since each would share the key of Table 1's 2024-25 average: Tables 3A
# and 3B print Table 1's average, but Table 4 prints GBP 3,350 against Table 1's GBP
# 3,330, so its grossed recipients differ from Table 1's before rounding.
#
"""


class PackageDumper(yaml.SafeDumper):
    """Plain YAML with no anchors, so every record set reads on its own."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def render(payload: dict) -> str:
    return HEADER + yaml.dump(
        payload, Dumper=PackageDumper, sort_keys=False, allow_unicode=True, width=100
    )


def value_labels() -> dict:
    co2 = {}
    for scheme in (CO2_BANDS_TO_2019, CO2_BANDS_FROM_2020):
        for label in scheme:
            low, high = band_from_label(label)
            co2[co2_value_id(low, high)] = co2_value_label(low, high)
    income = {}
    for labels in (INCOME_RANGES_3A, INCOME_RANGES_3B):
        for label in labels:
            income[income_value_id(*income_band(label))] = label
    return {
        "company_car_benefit_type": dict(BENEFIT_TYPES),
        "company_car_co2_band": dict(
            sorted(co2.items(), key=lambda item: band_sort(item[0]))
        ),
        "company_car_fuel_type": {value_id: label for value_id, _, label in FUEL_TYPES},
        "benefit_in_kind_income_band": dict(
            sorted(income.items(), key=lambda item: band_sort(item[0]))
        ),
    }


def band_sort(value_id: str) -> tuple[int, int]:
    numbers = [int(part) for part in re.findall(r"\d+", value_id)]
    return numbers[0], numbers[1] if len(numbers) > 1 else 10**9


def package() -> str:
    sheets = ods_sheets()
    check_markers(sheets)
    notes = check_notes(sheets["Notes"])
    table_1_sets, table_1_cells = table_1(sheets["1_car_and_car_fuel_benefit"], notes)
    record_sets = (
        table_1_sets
        + table_2a(sheets["2A_CO2_recipients"], table_1_cells)
        + table_2c(sheets["2C_fuel_type_recipients"], table_1_cells)
        + table_2e(sheets["2E_average_CO2"])
        + table_3a(sheets["3A_car_recipients_income"], table_1_cells)
        + table_3b(sheets["3B_fuel_recipients_income"], table_1_cells)
        + table_4(sheets["4_car_region"], table_1_cells)
    )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": (
            "HMRC Benefits in kind statistics, July 2026: company car and car fuel "
            "benefit recipients, taxable value, average taxable value and Income Tax and "
            "NIC liabilities (Table 1), car benefit recipients by CO2 emission band and "
            "fuel type and average CO2 emissions (Tables 2A, 2C and 2E), and 2024-25 "
            "recipients, taxable value and average taxable value by range of total income "
            "and region (Tables 3A, 3B and 4)"
        ),
        "dimension_labels": {
            "company_car_benefit_type": BENEFIT_TYPE_LABEL,
            "company_car_co2_band": "Company car CO2 emission band",
            "company_car_fuel_type": "Company car fuel type",
            "benefit_in_kind_income_band": "Range of total income",
            "geography": "Geography",
        },
        "dimension_value_labels": value_labels(),
        "artifact": {
            "source_name": "hmrc",
            "source_table": SOURCE_TABLE,
            "resource_package": "db",
            "resource_directory": f"data/{DATA_DIR}",
            "manifest": "manifest.yaml",
            "vintage": "benefits_in_kind_statistics_july_2026",
            "extracted_at": "2026-10-30",
            "extraction_method": "ODS whole-workbook used-range parse with numeric-text coercion",
            "parser": "ods_numeric_text_used_range",
            "artifact_year": 2026,
        },
        "record_sets": record_sets,
    }
    return render(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the generated YAML with the committed file instead of writing.",
    )
    args = parser.parse_args()
    path = PACKAGE_DIR / "source_package.yaml"
    text_out = package()
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != text_out:
            print(
                f"Stale generated package: {path.relative_to(REPO_ROOT)}",
                file=sys.stderr,
            )
            return 1
        return 0
    path.write_text(text_out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
