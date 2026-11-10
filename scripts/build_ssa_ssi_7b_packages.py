"""Write the source packages for SSA Supplement 2025 Tables 7.B3 and 7.B7.

Run from the repository root:

    uv run python scripts/build_ssa_ssi_7b_packages.py

``--check`` compares the generated YAML with the committed files instead of writing.
Both packages read SSA's section 7.B workbook (``7b.xlsx``), the file the Table 7.B1
package pins, through that package's manifest. ``TABLE_7B3``, ``TABLE_7B7`` and
``PACKAGES`` set each measure's column and each sheet's body, heading and
column-group rows. The script reads each area's row number and label, each column
heading, the title and each guard value from the workbook's own cells, and the
geography fields from the 7.B1 package's rows, so the three tables name each area
the same way. It downloads nothing and computes no value.

- ``ssa-ssi-table-7b3-2024`` (period month 2024-12): December 2024 recipients of
  federal SSI and of federally administered state supplementation, with their average
  monthly payments, by state or area.
- ``ssa-ssi-table-7b7-2024`` (calendar year 2024): federal SSI and federally
  administered state supplementation payments by state or area, which the workbook
  gives in thousands of dollars. Its Total column repeats Table 7.B1's payment totals
  cell for cell, and the 7.B1 package already emits those totals for every row but the
  Northern Mariana Islands'.

Like the 7.B1 package, both emit All areas, the 50 states and DC. They parse the
Northern Mariana Islands row as source cells and emit no fact for it. A cell SSA marks
". . ." (not applicable) yields no fact. Table 7.B3's All-areas state supplementation
cells carry footnote a in their text ("a 1,327,153": the count includes recipients not
assigned to a state), so they stay source cells only.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

import openpyxl
import yaml

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "db/data/ssa/ssi_table_7b1_2024"
XLSX_SHA256 = "6363d2efb1e9f76a672ef380ad41e6a2426ebe63c86a31d5dd78534a3aa31bd6"
B1_PACKAGE = ROOT / "packages/ssa/ssi_table_7b1_2024/source_package.yaml"
PAGE = "https://www.ssa.gov/policy/docs/statcomps/supplement/2025/7b.html"
OUTLYING_AREA = "Northern Mariana Islands"

COMMON = {
    "geography_id": "0100000US",
    "geography_level": "country",
    "geography_name": "United States",
    "geography_vintage": "current",
    "entity": "person",
    "entity_role": "ssi_recipient",
    "domain": "social_security_and_ssi_payments",
}
CALENDAR_2024 = {
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "basis": "calendar",
    "source_period_label": "calendar year 2024",
    "notes": "Payments during calendar year 2024.",
}

# (record set token, column, measure, source column id, measure label, concept,
#  source concept, unit, aggregation, value scale, evidence note)
TABLE_7B3 = [
    (
        "ssi_federal_payment_recipients",
        "D",
        "recipient_count",
        "federal_ssi_recipient_count",
        "Federal SSI recipients",
        "ssa.ssi_federal_payment_recipient_count",
        "ssa_supplement.table_7b3.federal_ssi_recipient_count",
        "count",
        "sum",
        None,
        "Table 7.B3 reports recipients of a federal SSI payment in December 2024 by "
        "state or area.",
    ),
    (
        "ssi_federal_average_monthly_payment",
        "E",
        "average_monthly_payment",
        "federal_ssi_average_monthly_payment",
        "Federal SSI average monthly payment",
        "ssa.ssi_federal_average_monthly_payment",
        "ssa_supplement.table_7b3.federal_ssi_average_monthly_payment",
        "usd",
        "mean",
        None,
        "Table 7.B3 reports the average federal SSI payment in December 2024, in "
        "dollars, by state or area.",
    ),
    (
        "ssi_state_supplementation_recipients",
        "F",
        "recipient_count",
        "state_supplementation_recipient_count",
        "Federally administered state supplementation recipients",
        "ssa.ssi_federally_administered_state_supplementation_recipient_count",
        "ssa_supplement.table_7b3.state_supplementation_recipient_count",
        "count",
        "sum",
        None,
        "Table 7.B3 reports recipients of a federally administered state "
        "supplementary payment in December 2024 for the states whose supplement SSA "
        "administers.",
    ),
    (
        "ssi_state_supplementation_average_monthly_payment",
        "G",
        "average_monthly_payment",
        "state_supplementation_average_monthly_payment",
        "Federally administered state supplementation average monthly payment",
        "ssa.ssi_federally_administered_state_supplementation_average_monthly_payment",
        "ssa_supplement.table_7b3.state_supplementation_average_monthly_payment",
        "usd",
        "mean",
        None,
        "Table 7.B3 reports the average federally administered state supplementary "
        "payment in December 2024, in dollars, for the states whose supplement SSA "
        "administers.",
    ),
]
TABLE_7B7 = [
    (
        "ssi_federal_payments",
        "E",
        "payment_amount",
        "federal_ssi_payment_thousands",
        "Federal SSI payments",
        "ssa.ssi_federal_payment_amount",
        "ssa_supplement.table_7b7.federal_ssi_payment_amount",
        "usd",
        "sum",
        1000,
        "Table 7.B7 reports calendar-year 2024 federal SSI payments by state or area "
        "in thousands of dollars.",
    ),
    (
        "ssi_state_supplementation_payments",
        "F",
        "payment_amount",
        "state_supplementation_payment_thousands",
        "Federally administered state supplementation payments",
        "ssa.ssi_federally_administered_state_supplementation_payment_amount",
        "ssa_supplement.table_7b7.state_supplementation_payment_amount",
        "usd",
        "sum",
        1000,
        "Table 7.B7 reports calendar-year 2024 federally administered state "
        "supplementation payments by state or area in thousands of dollars.",
    ),
]
PACKAGES = {
    "7.B3": {
        "path": ROOT / "packages/ssa/ssi_table_7b3_2024/source_package.yaml",
        "package_id": "ssa-ssi-table-7b3-2024",
        "label": (
            "SSA Annual Statistical Supplement 2025 Table 7.B3 SSI recipients and "
            "average monthly payment by type of payment"
        ),
        "body": (5, 58),
        "header_row": 4,
        "spanner_row": 3,
        "measures": TABLE_7B3,
        "period": {"period_type": "month", "period": "2024-12"},
    },
    "7.B7": {
        "path": ROOT / "packages/ssa/ssi_table_7b7_2024/source_package.yaml",
        "package_id": "ssa-ssi-table-7b7-2024",
        "label": (
            "SSA Annual Statistical Supplement 2025 Table 7.B7 SSI payment amounts by "
            "type of payment"
        ),
        "body": (4, 57),
        "header_row": 3,
        "spanner_row": None,
        "measures": TABLE_7B7,
        "period": {
            "period_type": "calendar_year",
            "period": 2024,
            "period_coverage": CALENDAR_2024,
        },
    },
}


def dump(data) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100000)


def slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def b1_geographies() -> dict[str, dict]:
    """Area label -> geography fields, from the 7.B1 package's rows."""
    spec = yaml.safe_load(B1_PACKAGE.read_text(encoding="utf-8"))
    fields = ("geography_id", "geography_level", "geography_name", "geography_vintage")
    found: dict[str, dict] = {}
    for record_set in spec["record_sets"]:
        for row in record_set["rows"]:
            geography = {key: row[key] for key in fields}
            assert found.setdefault(row["expected_row_header"], geography) == geography
    assert len(found) == 52, len(found)
    return found


def area_rows(sheet, first: int, last: int) -> dict[str, tuple[int, str]]:
    """Area label -> (row, label column) for the table body; All areas included."""
    found: dict[str, tuple[int, str]] = {}
    for row in range(first, last + 1):
        for column in "ABC":
            value = sheet[f"{column}{row}"].value
            if isinstance(value, str) and value.strip() and value != "Outlying area":
                assert value not in found, value
                found[value] = (row, column)
                break
    return found


def build_package(
    sheet,
    *,
    table: str,
    package_id: str,
    label: str,
    body: tuple[int, int],
    header_row: int,
    spanner_row: int | None,
    measures: list,
    period: dict,
) -> dict:
    title = sheet["A2"].value
    assert isinstance(title, str) and title.startswith(f"Table {table}—"), title
    geographies = b1_geographies()
    areas = area_rows(sheet, *body)
    assert set(areas) == set(geographies) | {OUTLYING_AREA}, set(areas) ^ set(
        geographies
    )
    token_prefix = "month2024_12" if period["period_type"] == "month" else "cy2024"
    record_sets = []
    for (
        token,
        column,
        measure_id,
        source_column_id,
        measure_label,
        concept,
        source_concept,
        unit,
        aggregation,
        scale,
        note,
    ) in measures:
        heading = sheet[f"{column}{header_row}"].value
        assert isinstance(heading, str) and heading, (table, column, heading)
        spanner = None
        if spanner_row is not None:
            # The group heading sits in the left cell of its two-column merge.
            spanner_column = (
                column
                if sheet[f"{column}{spanner_row}"].value
                else chr(ord(column) - 1)
            )
            spanner = (spanner_column, sheet[f"{spanner_column}{spanner_row}"].value)
            assert isinstance(spanner[1], str) and spanner[1], (table, column, spanner)
        rows = []
        for label_text, (row, label_column) in areas.items():
            if label_text == OUTLYING_AREA:
                continue
            if not is_number(sheet[f"{column}{row}"].value):
                continue
            is_total = label_text == "All areas"
            guards = []
            if spanner is not None:
                guards.append(
                    {
                        "column": spanner[0],
                        "row": spanner_row,
                        "expected_value": spanner[1],
                        "label": f"Table {table} column group",
                    }
                )
            if is_total:
                guards.append(
                    {
                        "column": "A",
                        "row": 2,
                        "expected_value": title,
                        "label": f"Table {table} title",
                    }
                )
            entry = {
                "value_id": slug(label_text),
                "label": label_text,
                "ordinal": len(rows),
                "row_number": row,
                "column": column,
                **geographies[label_text],
                "filters": {},
                "constraints": [],
                "expected_row_header_column": label_column,
                "expected_row_header": label_text,
                "expected_column_header_row": header_row,
                "expected_column_header": heading,
            }
            if guards:
                entry["guard_cells"] = guards
            entry["table_record_kind"] = "total" if is_total else "detail"
            rows.append(entry)
        measure = {
            "measure_id": measure_id,
            "label": measure_label,
            "ordinal": 0,
            "column": column,
            "source_column_id": source_column_id,
            "concept": concept,
            "source_concept": source_concept,
            "concept_relation": "exact",
            "concept_authority": "ledger-us",
            "concept_evidence_url": PAGE,
            "concept_evidence_notes": f"SSA Annual Statistical Supplement 2025 {note}",
            "unit": unit,
            "aggregation": aggregation,
        }
        if scale is not None:
            measure["value_scale"] = scale
        measure["expected_cell_type"] = "number"
        record_sets.append(
            {
                "sheet_name": table,
                **period,
                **COMMON,
                "rows": rows,
                "record_set_id": f"ssa_supplement.{token_prefix}.{token}.by_area",
                "provenance_class": "administrative",
                "record_set_spec_id": f"ssa_supplement.{token}.by_area.v1",
                "source_record_id_prefix": (
                    f"ssa_supplement.{token_prefix}.{token}.by_area"
                ),
                "measures": [measure],
                "groupby_dimension": "geography",
            }
        )
    return {
        "schema_version": "ledger.source_package.v1",
        "package_id": package_id,
        "label": label,
        "dimension_labels": {"geography": "Geography"},
        "artifact": {
            "source_name": "ssa",
            "source_table": f"SSA Annual Statistical Supplement 2025 Table {table}",
            "resource_package": "db",
            "resource_directory": "data/ssa/ssi_table_7b1_2024",
            "manifest": "manifest.yaml",
            "vintage": "annual_statistical_supplement_2025",
            "extracted_at": "2026-11-10",
            "extraction_method": (
                f"xlsx_used_range parse of sheet {table} of SSA's Annual Statistical "
                "Supplement 2025 section 7.B workbook (7b.xlsx), the file package "
                "ssa-ssi-table-7b1-2024 pins"
                + (
                    "; the measures scale its payment cells, which hold thousands "
                    "of dollars, by 1,000"
                    if table == "7.B7"
                    else ""
                )
            ),
            "parser": "xlsx_used_range",
            "artifact_year": 2024,
            "sheet_name": table,
            "sheets": [table],
        },
        "record_sets": record_sets,
    }


def build_packages() -> dict[Path, str]:
    """Committed package path -> the YAML text this script writes there."""
    workbook = RESOURCES / "7b.xlsx"
    assert hashlib.sha256(workbook.read_bytes()).hexdigest() == XLSX_SHA256
    book = openpyxl.load_workbook(workbook, read_only=False, data_only=True)
    return {
        config["path"]: dump(
            build_package(
                book[table],
                table=table,
                **{key: value for key, value in config.items() if key != "path"},
            )
        )
        for table, config in PACKAGES.items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the generated YAML with the committed files instead of writing",
    )
    args = parser.parse_args(argv)
    stale = []
    for path, text in build_packages().items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(path.relative_to(ROOT))
    for path in stale:
        print(f"stale: {path.relative_to(ROOT)}", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
