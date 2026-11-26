"""Generate the source package for PolicyEngine/chronicle#446, household spending by income decile.

Run from the repository root:

    uv run python scripts/build_uk_446_packages.py

``--check`` compares the generated YAML with the committed file instead of writing.

``ons-family-spending-workbook1-fye2025`` reads ONS's Family Spending workbook 1 (detailed
expenditure and trends), the financial year ending 2025 edition released on 11 June 2026, from
the Living Costs and Food Survey. The issue names workbook 2, but workbook 2 carries only
gross and unequivalised disposable income deciles; the equivalised decile table it asks for is
workbook 1's Table 3.1E, which prints both equivalisation versions side by side, and the same
workbook's Table A6 gives the gross income deciles the issue asks for if they come at no extra
cost. The package is written from its pinned artifact, read with Chronicle's own parser, so
every row number, column and guard cell below is one the package parser sees.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import re
import sys
from pathlib import Path

from openpyxl.utils import column_index_from_string

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_uk_408_packages import (  # noqa: E402
    PACKAGES,
    grid_of,
    manifest_file,
    metadata,
    render,
    write,
)
from chronicle.sources.cells import source_cells_from_xlsx  # noqa: E402

DIRECTORY = "ons/family_spending_workbook1_fye2025"
PACKAGE_ID = "ons-family-spending-workbook1-fye2025"
PREFIX = "ons.family_spending_fye2025"
EXTRACTED_AT = "2026-11-26"
SOURCE_PAGE = (
    "https://www.ons.gov.uk/peoplepopulationandcommunity/personalandhouseholdfinances/"
    "expenditure/datasets/familyspendingworkbook1detailedexpenditureandtrends"
)
SHEETS = ("3.1E", "A6")

COMMODITY = "expenditure_group"
DECILE = "income_decile_group"
RANKING = "income_decile_basis"
SCALE = "equivalence_scale"

EXPENDITURE = "ons.family_spending.mean_weekly_household_expenditure"
WEIGHTED = "ons.family_spending.weighted_households"
SAMPLE = "ons.family_spending.households_in_sample"

UNIT_CELL_TEXT = "Average weekly household expenditure (£)"
WEIGHTED_ROW_TEXT = "Weighted number of households (thousands)"
SAMPLE_ROW_TEXT = "Total number of households in sample"
SUPPRESSED = ".."

# value id, code as the parser reads it (None where the code cell holds the label), label.
COMMODITIES = (
    ("coicop_01", 1, "Food & non-alcoholic drinks"),
    ("coicop_02", 2, "Alcoholic drink, tobacco & narcotics"),
    ("coicop_03", 3, "Clothing & footwear"),
    ("coicop_04", 4, "Housing (net), fuel & power"),
    ("coicop_05", 5, "Household goods & services"),
    ("coicop_06", 6, "Health"),
    ("coicop_07", 7, "Transport"),
    ("coicop_08", 8, "Communication"),
    ("coicop_09", 9, "Recreation & culture"),
    ("coicop_10", 10, "Education"),
    ("coicop_11", 11, "Restaurants & hotels"),
    ("coicop_12", 12, "Miscellaneous goods & services"),
    ("coicop_01_to_12", "1-12", "All expenditure groups"),
    ("other_expenditure_items", 13, "Other expenditure items"),
    ("total_expenditure", None, "Total expenditure"),
)
DECILES = (
    ("decile_1", "Lowest ten per cent", "Lowest"),
    ("decile_2", "Second decile group", "Second"),
    ("decile_3", "Third decile group", "Third"),
    ("decile_4", "Fourth decile group", "Fourth"),
    ("decile_5", "Fifth decile group", "Fifth"),
    ("decile_6", "Sixth decile group", "Sixth"),
    ("decile_7", "Seventh decile group", "Seventh"),
    ("decile_8", "Eighth decile group", "Eighth"),
    ("decile_9", "Ninth decile group", "Ninth"),
    ("decile_10", "Highest ten per cent", "Highest"),
)
RANKINGS = {
    "equivalised_disposable_income": "Equivalised disposable income",
    "gross_income": "Gross income",
}
SCALES = {
    "updated_oecd_modified_2_adult_reference": (
        "Updated OECD-modified scale, 2-adult reference"
    ),
    "oecd_modified_1_adult_reference": "OECD-modified scale, 1-adult reference",
}


@dataclass(frozen=True)
class Block:
    """One decile table block: a sheet's label columns, its decile columns and its title."""

    key: str
    sheet: str
    table: str
    code_column: str
    label_column: str
    decile_columns: tuple[str, ...]
    all_column: str
    header_row: int
    title_guards: tuple[tuple[str, int, str, str], ...]
    ranking: str
    scale: str | None
    ranking_note: str


EQUIVALISATION_NOTE = (
    "Households are ranked by their equivalised disposable income. Table 3.1E's note 1: "
    "from FYE 2025 onwards ONS equivalises with the modified OECD scale based on a "
    "two-person reference household, replacing the previous single-person reference "
    "household, and for FYE 2025 it publishes tables using both methods side by side."
)
BLOCKS = (
    Block(
        key="table_3_1e.updated_oecd_modified_2_adult_reference",
        sheet="3.1E",
        table="Table 3.1E (updated OECD-modified scale, 2-adult reference)",
        code_column="A",
        label_column="B",
        decile_columns=tuple("EFGHIJKLMN"),
        all_column="O",
        header_row=8,
        title_guards=(
            (
                "A",
                2,
                "Detailed household expenditure by equivalised disposable income decile "
                "group (Updated OECD-modified scale,",
                "table title",
            ),
            ("A", 3, "2-adult reference1)", "equivalence scale reference household"),
            ("A", 4, "UK, financial year ending 2025", "coverage and period"),
        ),
        ranking="equivalised_disposable_income",
        scale="updated_oecd_modified_2_adult_reference",
        ranking_note=EQUIVALISATION_NOTE
        + " This block uses the updated OECD-modified scale (2-adult reference).",
    ),
    Block(
        key="table_3_1e.oecd_modified_1_adult_reference",
        sheet="3.1E",
        table="Table 3.1E (OECD-modified scale, 1-adult reference)",
        code_column="R",
        label_column="S",
        decile_columns=("V", "W", "X", "Y", "Z", "AA", "AB", "AC", "AD", "AE"),
        all_column="AF",
        header_row=8,
        title_guards=(
            (
                "R",
                2,
                "Detailed household expenditure by equivalised disposable income decile "
                "group (OECD-modified scale, ",
                "table title",
            ),
            ("R", 3, "1-adult reference1)", "equivalence scale reference household"),
            ("R", 4, "UK, financial year ending 2025", "coverage and period"),
        ),
        ranking="equivalised_disposable_income",
        scale="oecd_modified_1_adult_reference",
        ranking_note=EQUIVALISATION_NOTE
        + " This block uses the OECD-modified scale with a 1-adult reference household, "
        "the method used before FYE 2025.",
    ),
    Block(
        key="table_a6.gross_income",
        sheet="A6",
        table="Table A6",
        code_column="A",
        label_column="B",
        decile_columns=tuple("EFGHIJKLMN"),
        all_column="O",
        header_row=6,
        title_guards=(
            (
                "A",
                2,
                "Detailed household expenditure by gross income decile group",
                "table title",
            ),
            ("A", 3, "UK, financial year ending 2025", "coverage and period"),
        ),
        ranking="gross_income",
        scale=None,
        ranking_note="Households are ranked by their gross (not equivalised) income.",
    ),
)
# The all-household column is the same in each block, so it is read once, from the block
# that carries ONS's method from FYE 2025.
ALL_HOUSEHOLDS_BLOCK = BLOCKS[0]

COMMON_NOTES = (
    "ONS Family Spending workbook 1 (detailed expenditure and trends), financial year ending "
    "2025 edition, released 11 June 2026, from the Living Costs and Food Survey of UK private "
    "households. Background notes: figures are means over all households in the group, not "
    "only those reporting the expenditure; ONS suppresses ('..') figures based on fewer than "
    "10 reporting households, and such cells carry no fact; individual figures are rounded "
    "independently, so components need not add to the totals shown."
)
EXPENDITURE_NOTES = (
    "Average weekly household expenditure (£), FYE 2025 prices as published. The commodity "
    "groups are the publisher's COICOP divisions 1 to 12, their total ('1-12 All "
    "expenditure groups'), '13 Other expenditure items' and total expenditure (1-12 plus "
    "13). Housing (net) excludes mortgage interest payments, council tax and Northern "
    "Ireland rates (mortgage interest is in category 13), and total expenditure includes "
    "net rather than gross rent (the table's notes)."
)
WEIGHTED_NOTES = (
    "Weighted number of households (thousands), as printed above the expenditure table; "
    "value_scale 1000 stores households."
)
SAMPLE_NOTES = (
    "Total number of households in the Living Costs and Food Survey sample, unweighted, "
    "as printed above the expenditure table (ONS prints it to the nearest ten)."
)

HEADER = """
ONS Family Spending workbook 1: detailed expenditure and trends, the financial year ending
2025 edition (released 11 June 2026, next release to be announced), from the Living Costs
and Food Survey, for PolicyEngine/chronicle#446. Microcosm reads these as the official
reference of the LCFS stage's frame-against-donor decile receipt
(PolicyEngine/microcosm#1717).

Ported: mean weekly household expenditure by commodity group (COICOP divisions 1 to 12,
their total, other expenditure items and total expenditure), with each decile's weighted
households and households in the sample, by equivalised disposable income decile group in
both versions Table 3.1E prints side by side (the updated OECD-modified scale with a 2-adult
reference household, ONS's method from FYE 2025, and the OECD-modified scale with a 1-adult
reference household used before), and by gross income decile group (Table A6). The
all-household column is identical in the three blocks and is read once, from Table 3.1E's
updated-scale block, without decile filters.

Suppressed cells ('..', fewer than 10 reporting households) carry no fact: Education in
every decile of every block, and Health in every gross income decile. The source cells keep
the marker. No selected cell carries another marker.

Not ported: the detailed items below each division, the income boundaries, means and
medians of the groups, the per-person totals, Table 3.1 (unequivalised disposable income
deciles), the percentage tables (3.2, 3.2E), the quintile tables (3.1E5, 3.2E5) and the
other tables, none of which the issue asks for. Workbook 2, the file the issue names, has
no equivalised decile table for all households (only Tables A4 and A7, by gross and
unequivalised disposable income).

Written by scripts/build_uk_446_packages.py.
"""


def grid() -> dict[tuple[str, int, str], object]:
    filename, path = manifest_file(DIRECTORY)
    cells = source_cells_from_xlsx(
        path.read_bytes(), metadata(filename), sheets=SHEETS, coerce_numeric_text=True
    )
    return grid_of(cells)


def _clean(text: object) -> str:
    """A label cell without its footnote marker ('Housing (net)2, fuel & power')."""
    return re.sub(r"(?<=\))[0-9¹²³]", "", str(text)).strip()


def commodity_rows(cells: dict, block: Block) -> dict[str, tuple[int, object]]:
    """value id -> (row number, the code or label cell the row guard checks)."""
    found: dict[str, tuple[int, object]] = {}
    rows = sorted({row for (sheet, row, _) in cells if sheet == block.sheet})
    for value_id, code, label in COMMODITIES:
        matches = []
        for row in rows:
            code_cell = cells.get((block.sheet, row, block.code_column))
            label_cell = cells.get((block.sheet, row, block.label_column))
            if code is None:
                if str(code_cell).strip() == label and label_cell is None:
                    matches.append((row, code_cell))
            elif code_cell == code and _clean(label_cell) == label:
                matches.append((row, label_cell))
        if len(matches) != 1:
            raise ValueError(
                f"{block.sheet} {block.code_column}: {label!r} rows {matches}"
            )
        found[value_id] = matches[0]
    return found


def count_row(cells: dict, block: Block, text: str) -> int:
    rows = [
        row
        for (sheet, row, column), value in cells.items()
        if sheet == block.sheet and column == block.code_column and value == text
    ]
    if len(rows) != 1:
        raise ValueError(f"{block.sheet} {block.code_column}: {text!r} rows {rows}")
    return rows[0]


def unit_cell(cells: dict, block: Block, first_commodity_row: int) -> tuple[str, int]:
    """The block's 'Average weekly household expenditure (£)' cell above its first division."""
    low = column_index_from_string(block.code_column)
    high = column_index_from_string(block.all_column)
    hits = sorted(
        (row, column)
        for (sheet, row, column), value in cells.items()
        if sheet == block.sheet
        and value == UNIT_CELL_TEXT
        and row < first_commodity_row
        and low <= column_index_from_string(column) <= high
    )
    if len(hits) != 1:
        raise ValueError(f"{block.sheet} {block.code_column}: unit cells {hits}")
    row, column = hits[0]
    return column, row


def period_fields() -> dict:
    return {
        "period_type": "fiscal_year",
        "period": 2024,
        "period_coverage": {
            "start_date": "2024-04-01",
            "end_date": "2025-03-31",
            "basis": "fiscal",
            "source_period_label": "financial year ending 2025",
            "notes": (
                "Financial year ending March 2025 (FYE 2025); period.value stores the "
                "opening year."
            ),
        },
        "geography_id": "K02000001",
        "geography_level": "country",
        "geography_name": "United Kingdom",
        "geography_vintage": "current",
        "entity": "household",
        "entity_role": "private_household",
        "domain": "household_consumption_expenditure",
    }


def record_set_head(record_set_id: str, sheet: str, groupby: str) -> dict:
    return {
        "record_set_id": record_set_id,
        "provenance_class": "survey_aggregate",
        "survey_instrument": "Living Costs and Food Survey",
        "assertion": "observation",
        "record_set_spec_id": f"{record_set_id}.v1",
        "source_record_id_prefix": record_set_id,
        "sheet_name": sheet,
        **period_fields(),
        "groupby_dimension": groupby,
    }


def constraint(variable: str, value: str, label: str) -> dict:
    return {"variable": variable, "operator": "==", "value": value, "label": label}


def shared(block: Block, decile: str | None) -> tuple[dict, list[dict]]:
    filters: dict[str, str] = {}
    constraints: list[dict] = []
    if decile is not None:
        filters[DECILE] = decile
        constraints.append(constraint(DECILE, decile, "Income decile group"))
    filters[RANKING] = block.ranking
    constraints.append(
        constraint(RANKING, block.ranking, "Income that ranks the deciles")
    )
    if block.scale is not None:
        filters[SCALE] = block.scale
        constraints.append(constraint(SCALE, block.scale, "Equivalence scale"))
    return filters, constraints


def title_guards(block: Block) -> list[dict]:
    return [
        {"column": column, "row": row, "expected_value": value, "label": label}
        for column, row, value, label in block.title_guards
    ]


def measure(
    *,
    measure_id: str,
    label: str,
    column: str,
    source_column_id: str,
    header_row: int,
    header: str,
    concept: str,
    notes: str,
    unit: str,
    aggregation: str,
    value_scale: int | None = None,
) -> dict:
    payload = {
        "measure_id": measure_id,
        "label": label,
        "ordinal": 0,
        "column": column,
        "source_column_id": source_column_id,
        "expected_column_header_row": header_row,
        "expected_column_header": header,
        "concept": concept,
        "source_concept": concept,
        "concept_relation": "source_label",
        "concept_authority": "ons",
        "concept_evidence_url": SOURCE_PAGE,
        "concept_evidence_notes": notes,
        "unit": unit,
        "aggregation": aggregation,
    }
    if value_scale is not None:
        payload["value_scale"] = value_scale
    payload["expected_cell_type"] = "number"
    return payload


def column_label(cells: dict, block: Block, column: str) -> str:
    words = [
        cells.get((block.sheet, block.header_row + offset, column))
        for offset in range(3)
    ]
    return " ".join(str(word) for word in words if word is not None).replace("- ", "")


def expenditure_record_set(
    cells: dict,
    block: Block,
    record_set_id: str,
    column: str,
    header: str,
    group_label: str,
    decile: str | None,
) -> dict:
    rows_by_id = commodity_rows(cells, block)
    first_row = min(row for row, _ in rows_by_id.values())
    unit_column, unit_row_number = unit_cell(cells, block, first_row)
    rows = []
    for ordinal, (value_id, code, label) in enumerate(COMMODITIES):
        row_number, header_cell = rows_by_id[value_id]
        value = cells.get((block.sheet, row_number, column))
        if value == SUPPRESSED:
            continue
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise ValueError(
                f"{block.sheet}!{column}{row_number}: unexpected cell {value!r}"
            )
        row = {
            "value_id": value_id,
            "label": label,
            "ordinal": ordinal,
            "row_number": row_number,
            "expected_row_header_column": (
                block.code_column if code is None else block.label_column
            ),
            "expected_row_header": header_cell,
            "table_record_kind": "detail",
            "filters": {COMMODITY: value_id},
            "constraints": [constraint(COMMODITY, value_id, "Commodity or service")],
        }
        guards = []
        if code is not None:
            guards.append(
                {
                    "column": block.code_column,
                    "row": row_number,
                    "expected_value": code,
                    "label": "commodity code",
                }
            )
        if not rows:
            guards += title_guards(block)
            guards.append(
                {
                    "column": unit_column,
                    "row": unit_row_number,
                    "expected_value": UNIT_CELL_TEXT,
                    "label": "measure and unit",
                }
            )
        if guards:
            row["guard_cells"] = guards
        rows.append(row)
    payload = record_set_head(record_set_id, block.sheet, COMMODITY)
    if decile is not None:
        filters, constraints = shared(block, decile)
        payload["shared_filters"] = filters
        payload["shared_constraints"] = constraints
    payload["rows"] = rows
    ranking = (
        f", {RANKINGS[block.ranking].lower()} decile groups"
        + (f" ({SCALES[block.scale]})" if block.scale else "")
        if decile is not None
        else ""
    )
    payload["measures"] = [
        measure(
            measure_id="mean_weekly_household_expenditure",
            label=f"Average weekly household expenditure, {group_label}{ranking}, FYE 2025",
            column=column,
            source_column_id=group_label.lower().replace(" ", "_"),
            header_row=block.header_row,
            header=header,
            concept=EXPENDITURE,
            notes=" ".join(
                part
                for part in (
                    f"{block.table}, column '{group_label}'.",
                    block.ranking_note if decile is not None else "",
                    EXPENDITURE_NOTES,
                    COMMON_NOTES,
                )
                if part
            ),
            unit="gbp_per_week",
            aggregation="mean",
        )
    ]
    return payload


def count_record_set(
    cells: dict,
    block: Block,
    record_set_id: str,
    column: str,
    header: str,
    group_label: str,
    decile: str | None,
    kind: str,
) -> dict:
    text, concept, notes, value_scale, measure_label = {
        "weighted_households": (
            WEIGHTED_ROW_TEXT,
            WEIGHTED,
            WEIGHTED_NOTES,
            1000,
            "Weighted number of households",
        ),
        "households_in_sample": (
            SAMPLE_ROW_TEXT,
            SAMPLE,
            SAMPLE_NOTES,
            None,
            "Total number of households in sample",
        ),
    }[kind]
    row_number = count_row(cells, block, text)
    value = cells.get((block.sheet, row_number, column))
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(
            f"{block.sheet}!{column}{row_number}: unexpected cell {value!r}"
        )
    row = {
        "value_id": decile or "all_households",
        "label": group_label,
        "ordinal": 0,
        "row_number": row_number,
        "expected_row_header_column": block.code_column,
        "expected_row_header": text,
        "table_record_kind": "detail" if decile else "total",
    }
    if decile is not None:
        row["filters"] = {DECILE: decile}
        row["constraints"] = [constraint(DECILE, decile, "Income decile group")]
    row["guard_cells"] = title_guards(block)
    payload = record_set_head(record_set_id, block.sheet, DECILE)
    if decile is not None:
        filters, constraints = shared(block, None)
        payload["shared_filters"] = filters
        payload["shared_constraints"] = constraints
    payload["rows"] = [row]
    ranking = (
        f", {RANKINGS[block.ranking].lower()} decile groups"
        + (f" ({SCALES[block.scale]})" if block.scale else "")
        if decile is not None
        else ""
    )
    payload["measures"] = [
        measure(
            measure_id=kind,
            label=f"{measure_label}, {group_label}{ranking}, FYE 2025",
            column=column,
            source_column_id=group_label.lower().replace(" ", "_"),
            header_row=block.header_row,
            header=header,
            concept=concept,
            notes=" ".join(
                part
                for part in (
                    f"{block.table}, column '{group_label}'.",
                    block.ranking_note if decile is not None else "",
                    notes,
                    COMMON_NOTES,
                )
                if part
            ),
            unit="count",
            aggregation="sum",
            value_scale=value_scale,
        )
    ]
    return payload


def build() -> str:
    cells = grid()
    record_sets = []
    for block in BLOCKS:
        for (decile, label, header), column in zip(
            DECILES, block.decile_columns, strict=True
        ):
            if column_label(cells, block, column) != label:
                raise ValueError(
                    f"{block.sheet}!{column}{block.header_row}: "
                    f"{column_label(cells, block, column)!r} is not {label!r}"
                )
            stem = f"{PREFIX}.{block.key}.{decile}"
            record_sets.append(
                expenditure_record_set(
                    cells, block, f"{stem}.expenditure", column, header, label, decile
                )
            )
            for kind in ("weighted_households", "households_in_sample"):
                record_sets.append(
                    count_record_set(
                        cells,
                        block,
                        f"{stem}.{kind}",
                        column,
                        header,
                        label,
                        decile,
                        kind,
                    )
                )
    block = ALL_HOUSEHOLDS_BLOCK
    label = column_label(cells, block, block.all_column)
    if label != "All households":
        raise ValueError(f"{block.sheet}!{block.all_column}: {label!r}")
    stem = f"{PREFIX}.all_households"
    record_sets.append(
        expenditure_record_set(
            cells, block, f"{stem}.expenditure", block.all_column, "All", label, None
        )
    )
    for kind in ("weighted_households", "households_in_sample"):
        record_sets.append(
            count_record_set(
                cells,
                block,
                f"{stem}.{kind}",
                block.all_column,
                "All",
                label,
                None,
                kind,
            )
        )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": (
            "ONS Family Spending, FYE 2025 edition: mean weekly household expenditure by "
            "commodity group, with weighted households and sample sizes, by equivalised "
            "disposable income decile (both equivalence scales) and gross income decile, UK"
        ),
        "dimension_labels": {
            COMMODITY: "Commodity or service",
            DECILE: "Income decile group",
            RANKING: "Income that ranks the deciles",
            SCALE: "Equivalence scale",
        },
        "dimension_value_labels": {
            DECILE: {decile: label for decile, label, _ in DECILES},
            RANKING: dict(RANKINGS),
            SCALE: dict(SCALES),
        },
        "artifact": {
            "source_name": "ons",
            "source_table": (
                "Family spending workbook 1: detailed expenditure and trends, financial year "
                "ending 2025, Tables 3.1E and A6"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "family_spending_fye2025_release_2026_06_11",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": (
                "xlsx used-range cell parse of Tables 3.1E and A6, figures stored as text "
                "read as numbers"
            ),
            "parser": "xlsx_numeric_text_used_range",
            "artifact_year": 2025,
            "sheets": list(SHEETS),
        },
        "record_sets": record_sets,
    }
    return render(HEADER, payload)


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
    for directory, builder in BUILDERS.items():
        text = builder()
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
