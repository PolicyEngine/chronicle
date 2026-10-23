#!/usr/bin/env python3
"""Select printed cells from FPD's immutable January 2025 amount-band tables.

The tables are PDF Form XObjects. Reading their Tm/TJ operators directly avoids
pypdf's layout/visitor coordinate loss. No OCR, calculations or inferred zeros
enter the extract. Printed sums are checked, never emitted as new observations.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
import csv
from dataclasses import dataclass
from decimal import Decimal
import hashlib
from pathlib import Path
import re
import sys

from pypdf import PdfReader
from pypdf.generic import ContentStream
import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT))
from chronicle.epoch import schema_id  # noqa: E402

DATA_DIR = REPO_ROOT / "db/data/sfpd/pension_amount_bands_2025"
PACKAGE_ID = "sfpd-pension-amount-bands-2025"
PDF_NAME = "nl_statistiek_2025.pdf"
CSV_NAME = "pension_amount_bands_2025.csv"
PDF_SHA256 = "198baf61f9277755059367c811664a71917aab6fe5d2b7e2c7e2c96e9baa8c64"
SOURCE_URL = "https://www.sfpd.fgov.be/media/Stat/Jaarlijks/nl_statistiek_2025.pdf"
LANDING_URL = (
    "https://www.sfpd.fgov.be/nl/kenniscentrum/statistieken/statistieken-werknemers"
)
SOURCE_TABLE = "Jaarlijkse statistiek 2025, sections 1.2, 6.2 and 9"
SEXES = ("Mannen en vrouwen", "Mannen", "Vrouwen")
CAREERS = (
    "Alle loopbanen",
    "Zuiver of gemengde loopbaan werknemer",
    "Zuivere of gemengde loopbaan zelfstandige",
    "Zuivere loopbaan werknemer",
    "Gemengde loopbaan werknemer en zelfstandige",
    "Gemengde loopbaan werknemer en ambtenaar",
    "Gemengde loopbaan werknemer, zelfstandige en ambtenaar",
    "Zuivere loopbaan zelfstandige",
    "Gemengde loopbaan zelfstandige en ambtenaar",
)
CATEGORIES = (
    "Totaal",
    "Gehuwd: Rust gezinsbedrag",
    "Gehuwd: Rust bedrag alleenstaande",
    "Niet gehuwd: Rust bedrag alleenstaande",
    "Niet gehuwd: Rust en overleving",
    "Niet gehuwd: Overleving en overgangsuitkering",
)
ELIGIBILITIES = (
    "Totaal",
    "Die in aanmerking komen voor de toekenning van het basisbedrag",
    "Die in aanmerking komen voor de toekenning van het verhoogd basisbedrag",
    "Niet verdeelde gevallen",
)
DIMENSIONS = {
    "sfpd.population": "FPD published beneficiary population",
    "sfpd.career": "Loopbaan",
    "sfpd.sex": "Geslacht",
    "sfpd.pension_category": "Pensioencategorie en burgerlijke staat",
    "sfpd.igo_eligibility": "IGO toekenning",
    "sfpd.age_group": "Leeftijdsgroep",
    "sfpd.monthly_amount_band": "Schijf van maandbedrag (EUR)",
}
HEADERS = [
    "row_id",
    "section",
    "table",
    "pdf_page",
    "printed_page",
    "pdf_form",
    "pdf_panel",
    "pdf_row",
    "recipients_column",
    "expenditure_column",
    "recipients_position",
    "expenditure_position",
    *DIMENSIONS,
    "sfpd.monthly_amount_lower_bound",
    "sfpd.monthly_amount_upper_bound",
    "recipients",
    "monthly_expenditure_eur",
    "recipients_raw",
    "expenditure_raw",
]
NUMBER = re.compile(r"\d+(?:\.\d{3})*(?:,\d{2})?\Z")
BAND = re.compile(r"([\d.,]+) (?:-|tot) ([\d.,]+)\Z|([\d.,]+) en (?:>|meer)\Z")


@dataclass(frozen=True)
class Token:
    x: float
    y: float
    text: str


def number(text: str) -> str:
    """Normalize only Dutch thousands/decimal punctuation; no rescaling."""
    if not NUMBER.fullmatch(text):
        raise ValueError(f"Not a published numeric lexeme: {text!r}")
    return text.replace(".", "").replace(",", ".")


def form_tokens(reader: PdfReader, page_number: int) -> tuple[str, list[Token]]:
    objects = reader.pages[page_number - 1]["/Resources"]["/XObject"]
    forms = [
        (name, obj.get_object())
        for name, obj in objects.items()
        if obj.get_object().get("/Subtype") == "/Form"
    ]
    if len(forms) != 1:
        raise ValueError(f"Expected one table form on PDF page {page_number}")
    name, form = forms[0]
    tokens = []
    x = y = 0.0
    for args, operator in ContentStream(form, reader).operations:
        if operator == b"Tm":
            if list(args[:4]) != [1, 0, 0, 1]:
                raise ValueError("Unexpected table text transform")
            x, y = map(float, args[-2:])
        elif operator in (b"TJ", b"Tj"):
            fragments = args[0] if operator == b"TJ" else args
            text = "".join(str(v) for v in fragments if isinstance(v, str)).strip()
            if text:
                tokens.append(Token(x, y, text))
        elif operator in (b"Td", b"TD", b"T*", b"'", b'"'):
            raise ValueError(f"Unsupported table text positioning: {operator!r}")
    return str(name), tokens


def _bounds(label: str) -> tuple[str, str]:
    if label == "Totaal":
        return "", ""
    if label == "minder dan 125,00":
        return "", "125.00"
    if label == "2.000,00 en meer":
        return "2000.00", ""
    match = BAND.fullmatch(label)
    if not match:
        raise ValueError(f"Unexpected amount band {label!r}")
    lower, upper, open_lower = match.groups()
    return number(lower or open_lower), number(upper) if upper else ""


def _base(page: int, form: str, section: str, table: str, sex: str) -> dict:
    row = dict.fromkeys(HEADERS, "")
    row.update(
        pdf_page=str(page),
        printed_page=str(page - 10),
        pdf_form=form,
        section=section,
        table=table,
    )
    row["sfpd.sex"] = sex
    return row


def _value(row: dict, count: Token | None, expense: Token | None, column: int) -> None:
    if count is not None:
        row["recipients"] = number(count.text)
        row["recipients_raw"] = count.text
        row["recipients_position"] = f"{count.x:g},{count.y:g}"
        row["recipients_column"] = str(column)
    if expense is not None:
        row["monthly_expenditure_eur"] = number(expense.text)
        row["expenditure_raw"] = expense.text
        row["expenditure_position"] = f"{expense.x:g},{expense.y:g}"
        row["expenditure_column"] = str(column + 1)
    lower, upper = _bounds(row["sfpd.monthly_amount_band"])
    row["sfpd.monthly_amount_lower_bound"] = lower
    row["sfpd.monthly_amount_upper_bound"] = upper


def _band_table(
    reader: PdfReader, page: int, career_index: int | None, sex_index: int
) -> list[dict]:
    form, tokens = form_tokens(reader, page)
    pension = career_index is not None
    section = "1.2" if pension else "6.2"
    table = f"1.2.{career_index + 1}" if pension else "6.2"
    # Column boundaries are local Form coordinates, not page coordinates.
    edges = (
        [76.6, 125, 205, 250, 328, 375, 448]
        if pension
        else [77, 123, 179, 225, 282, 326, 384, 430, 477]
    )
    labels = sorted(
        (
            t
            for t in tokens
            if t.x < 77 and (t.text == "Totaal" or BAND.fullmatch(t.text))
        ),
        key=lambda t: -t.y,
    )
    expected = 54 if pension else 62
    if len(labels) != expected:
        raise ValueError(f"PDF p{page}: {len(labels)} band rows, expected {expected}")
    rows = []
    matched = set()
    for label_index, label in enumerate(labels):
        panel = label_index // 27 if pension else 0
        row_index = label_index % 27 if pension else label_index
        if (row_index == 0) != (label.text == "Totaal"):
            raise ValueError(f"Unexpected total location on p{page}")
        values = {}
        for token in tokens:
            if token.x < 77 or abs(token.y - label.y) > 2:
                continue
            if not NUMBER.fullmatch(token.text):
                continue
            col = bisect.bisect_right(edges, token.x) - 1
            if col < 0 or col >= len(edges) - 1 or col in values:
                raise ValueError(f"Ambiguous cell p{page} {token}")
            values[col] = token
            matched.add(token)
        for category in range((len(edges) - 1) // 2):
            count, expense = values.get(category * 2), values.get(category * 2 + 1)
            if count is None and expense is None:
                continue  # A blank publisher cell does not assert a zero.
            row = _base(page, form, section, table, SEXES[sex_index])
            row.update(pdf_panel=str(panel + 1), pdf_row=str(row_index + 1))
            row["sfpd.monthly_amount_band"] = label.text
            if pension:
                row["sfpd.population"] = (
                    "Pensioengerechtigden (werknemers en zelfstandigen)"
                )
                row["sfpd.career"] = CAREERS[career_index]
                row["sfpd.pension_category"] = CATEGORIES[panel * 3 + category]
            else:
                row["sfpd.population"] = "Inkomensgarantie voor ouderen (IGO)"
                row["sfpd.igo_eligibility"] = ELIGIBILITIES[category]
            _value(row, count, expense, category * 2 + 2)
            row["row_id"] = (
                f"p{page}.panel{panel + 1}.row{row_index + 1}.category{category + 1}"
            )
            rows.append(row)
    numeric = {t for t in tokens if t.x >= 77 and NUMBER.fullmatch(t.text)}
    if matched != numeric:
        raise ValueError(
            f"Unselected numeric table cells on p{page}: {numeric - matched}"
        )
    return rows


def _age_table(reader: PdfReader, page: int, sex_index: int) -> list[dict]:
    form, tokens = form_tokens(reader, page)
    age_labels = sorted(
        (t for t in tokens if t.x < 80 and (t.text == "Totaal" or "jaar" in t.text)),
        key=lambda t: -t.y,
    )
    if len(age_labels) != 57:
        raise ValueError(
            f"p{page}: expected 3 panels of 19 age rows, got {len(age_labels)}"
        )
    # Read the three-line column headers, including the open-ended bands.
    panels = []
    for edges, header_y in (
        ([82, 156, 202, 247, 294, 342, 395], 683.22),
        ([82, 126, 171, 216, 261, 307, 355, 395], 442.97),
        ([79, 126, 171, 216, 261, 307], 202.72),
    ):
        bands = []
        for left, right in zip(edges, edges[1:]):
            parts = sorted(
                (
                    t
                    for t in tokens
                    if left <= t.x < right and header_y - 0.1 <= t.y <= header_y + 23
                ),
                key=lambda t: (-t.y, t.x),
            )
            label = " ".join(t.text for t in parts)
            if label == "Totaal aantal gerechtigden":
                label = "Totaal"
            _bounds(label)  # Fail if any header is missing or ambiguous.
            bands.append(label)
        panels.append((edges, bands))
    rows = []
    matched = set()
    for label_index, label in enumerate(age_labels):
        panel, row_index = divmod(label_index, 19)
        edges, bands = panels[panel]
        if (row_index == 0) != (label.text == "Totaal"):
            raise ValueError(f"Unexpected age total p{page}")
        for token in tokens:
            if (
                token.x < 80
                or abs(token.y - label.y) > 2
                or not NUMBER.fullmatch(token.text)
                or "," in token.text
            ):
                continue
            col = bisect.bisect_right(edges, token.x) - 1
            if col < 0 or col >= len(bands):
                raise ValueError(f"Unexpected age table column p{page}: {token}")
            row = _base(page, form, "9", "9", SEXES[sex_index])
            row.update(pdf_panel=str(panel + 1), pdf_row=str(row_index + 1))
            row["sfpd.population"] = (
                "FPD-uitkeringsgerechtigden (werknemers en zelfstandigen)"
            )
            row["sfpd.age_group"] = label.text
            row["sfpd.monthly_amount_band"] = bands[col]
            _value(row, token, None, col + 2)
            row["row_id"] = (
                f"p{page}.panel{panel + 1}.row{row_index + 1}.column{col + 2}"
            )
            rows.append(row)
            matched.add(token)
    numeric = {
        t
        for t in tokens
        if t.x >= 80
        and NUMBER.fullmatch(t.text)
        and "," not in t.text
        and any(abs(t.y - label.y) <= 2 for label in age_labels)
    }
    if matched != numeric:
        raise ValueError(f"Unselected age table cells p{page}: {numeric - matched}")
    return sorted(
        rows,
        key=lambda r: (
            int(r["pdf_panel"]),
            int(r["pdf_row"]),
            int(r["recipients_column"]),
        ),
    )


def check_totals(rows: list[dict]) -> list[dict]:
    """Compare extracted detail with existing printed totals (Decimal exact)."""
    groups = defaultdict(list)
    for row in rows:
        axis = "sfpd.age_group" if row["section"] == "9" else "sfpd.monthly_amount_band"
        group = (
            row["pdf_page"],
            row["sfpd.pension_category"],
            row["sfpd.igo_eligibility"],
            row["sfpd.monthly_amount_band"] if axis == "sfpd.age_group" else "",
        )
        groups[(axis, group)].append(row)
    checks = []
    for (axis, group), members in groups.items():
        totals = [r for r in members if r[axis] == "Totaal"]
        if len(totals) != 1:
            raise ValueError(f"Expected a printed total for {group}")
        for metric in ("recipients", "monthly_expenditure_eur"):
            if not totals[0][metric]:
                continue
            actual = sum(
                (
                    Decimal(r[metric])
                    for r in members
                    if r[axis] != "Totaal" and r[metric]
                ),
                Decimal(0),
            )
            expected = Decimal(totals[0][metric])
            if actual != expected:
                raise ValueError(
                    f"Printed total mismatch {group} {metric}: {actual} != {expected}"
                )
            checks.append(
                {
                    "pdf_page": group[0],
                    "metric": metric,
                    "printed_total": str(expected),
                    "detail_sum": str(actual),
                }
            )
    return checks


def extract_rows(pdf_path: Path) -> list[dict]:
    if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != PDF_SHA256:
        raise ValueError("Raw PDF checksum mismatch")
    reader = PdfReader(pdf_path)
    if len(reader.pages) != 244:
        raise ValueError("Unexpected PDF page count")
    rows = []
    for career_index, start in enumerate((58, 62, 65, 68, 71, 74, 77, 80, 83)):
        for sex_index in range(3):
            rows.extend(_band_table(reader, start + sex_index, career_index, sex_index))
    for sex_index in range(3):
        rows.extend(_band_table(reader, 227 + sex_index, None, sex_index))
        rows.extend(_age_table(reader, 240 + sex_index, sex_index))
    check_totals(rows)
    return rows


class LiteralDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _dump(path: Path, value: dict) -> None:
    path.write_text(
        yaml.dump(
            value, Dumper=LiteralDumper, sort_keys=False, allow_unicode=True, width=100
        ),
        encoding="utf-8",
    )


def _constraint(variable: str, value: str, operator: str = "==") -> dict:
    return {
        "variable": variable,
        "operator": operator,
        "value": value,
        "label": DIMENSIONS.get(variable, "Published monthly amount boundary (EUR)"),
    }


def package_spec(rows: list[dict]) -> dict:
    groups = defaultdict(list)
    for csv_row, row in enumerate(rows, start=2):
        key = (
            row["table"],
            row["sfpd.sex"],
            row["sfpd.pension_category"],
            row["sfpd.igo_eligibility"],
            row["sfpd.age_group"],
            bool(row["recipients"]),
            bool(row["monthly_expenditure_eur"]),
        )
        groups[key].append((csv_row, row))
    record_sets = []
    for group_index, members in enumerate(groups.values()):
        first = members[0][1]
        shared = {
            key: first[key]
            for key in DIMENSIONS
            if key != "sfpd.monthly_amount_band" and first[key]
        }
        identifier = f"sfpd.amount_bands.jan2025.group{group_index + 1}"
        spec = {
            "record_set_id": identifier,
            "provenance_class": "administrative",
            "assertion": "observation",
            "record_set_spec_id": identifier + ".v1",
            "source_record_id_prefix": identifier,
            "sheet_name": "amount_bands",
            "period_type": "month",
            "period": "2025-01",
            "period_coverage": {
                "start_date": "2025-01-01",
                "end_date": "2025-01-31",
                "basis": "calendar",
                "source_period_label": "januari 2025",
                "notes": "Beneficiary stock at 1 January 2025, not a monthly average; gross monthly amounts payable for January. FPD employees/self-employed database; public-sector pension amounts excluded. Includes beneficiaries residing abroad. See package README.",
            },
            "geography_id": "BE",
            "geography_level": "country",
            "geography_name": "Belgium",
            "geography_vintage": "current",
            "entity": "person",
            "entity_role": "benefit_recipient",
            "domain": "pensions" if first["section"] == "1.2" else "social_security",
            "groupby_dimension": "sfpd.monthly_amount_band",
            "shared_filters": dict(shared),
            "shared_constraints": [_constraint(k, v) for k, v in shared.items()],
            "rows": [],
            "measures": [],
        }
        for ordinal, (csv_row, row) in enumerate(members):
            band = row["sfpd.monthly_amount_band"]
            constraints = [_constraint("sfpd.monthly_amount_band", band)]
            # Bounds are interpreted labels, never observations or rescaled values.
            for suffix, operator in (("lower_bound", ">="), ("upper_bound", "<=")):
                value = row[f"sfpd.monthly_amount_{suffix}"]
                if value:
                    op = "<" if band == "minder dan 125,00" else operator
                    constraints.append(
                        {
                            "variable": "sfpd.monthly_amount",
                            "operator": op,
                            "value": float(value),
                            "unit": "eur",
                            "label": "Published monthly amount boundary (EUR)",
                        }
                    )
            spec["rows"].append(
                {
                    "value_id": row["row_id"],
                    "label": band,
                    "ordinal": ordinal,
                    "row_number": csv_row,
                    "expected_row_header_column": "A",
                    "expected_row_header": row["row_id"],
                    "guard_cells": [
                        {
                            "column": "S",
                            "row": "start",
                            "expected_value": band,
                            "label": "Exact published monthly amount band",
                        }
                    ],
                    "table_record_kind": "total" if band == "Totaal" else "detail",
                    "filters": {"sfpd.monthly_amount_band": band},
                    "constraints": constraints,
                }
            )
        population = {"1.2": "pension", "6.2": "igo", "9": "all_benefits"}[
            first["section"]
        ]
        for ordinal, (metric, unit, label) in enumerate(
            (
                ("recipients", "count", "Aantal gerechtigden"),
                ("monthly_expenditure_eur", "eur", "Maandelijkse uitgave (EUR)"),
            )
        ):
            if not first[metric]:
                continue
            column = chr(65 + HEADERS.index(metric))
            # The two metric columns occur before Excel Z in this fixed schema.
            spec["measures"].append(
                {
                    "measure_id": metric,
                    "label": label,
                    "ordinal": ordinal,
                    "column": column,
                    "source_column_id": metric,
                    "expected_column_header_row": 1,
                    "expected_column_header": metric,
                    "concept": f"sfpd_{population}_{metric}",
                    "source_concept": f"sfpd.{population}.{metric}",
                    "concept_relation": "exact",
                    "concept_authority": "publisher",
                    "concept_evidence_url": SOURCE_URL,
                    "concept_evidence_notes": "Direct published cell; population, amount bands, January reference and gross payment basis are documented in PDF printed pp1–5,47,216–217,229 and package README. Career selects the beneficiary's career, not a scheme-only expenditure component.",
                    "unit": unit,
                    "aggregation": "sum",
                    "expected_cell_type": "number",
                }
            )
        record_sets.append(spec)
    return {
        "schema_version": schema_id("source_package"),
        "package_id": PACKAGE_ID,
        "label": "FPD January 2025 pension and benefit monthly amount-band distributions",
        "artifact": {
            "source_name": "sfpd_pension_amount_bands",
            "source_table": SOURCE_TABLE,
            "resource_package": "db",
            "resource_directory": "data/sfpd/pension_amount_bands_2025",
            "manifest": "manifest.yaml",
            "vintage": "jaarlijkse_statistiek_2025",
            "extracted_at": "2026-10-23",
            "extraction_method": "Deterministic PDF Form Tm/TJ cell extraction; build_package.py; no derived facts",
            "parser": "delimited_text_full_rows",
            "artifact_year": 2025,
            "sheet_name": "amount_bands",
        },
        "dimension_labels": DIMENSIONS,
        "dimension_value_labels": {
            key: {v: v for v in sorted({row[key] for row in rows if row[key]})}
            for key in DIMENSIONS
        },
        "record_sets": record_sets,
    }


def generate(data_dir: Path = DATA_DIR, package_dir: Path = PACKAGE_DIR) -> None:
    rows = extract_rows(data_dir / PDF_NAME)
    csv_path = data_dir / CSV_NAME
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    files = {}
    for key, path in ((2025, csv_path), ("source_capture", data_dir / PDF_NAME)):
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        r2_key = f"raw/belgium/{PACKAGE_ID}/{key}/{sha}/{path.name}"
        files[key] = {
            "filename": path.name,
            "source_url": SOURCE_URL,
            "sha256": sha,
            "size_bytes": path.stat().st_size,
            "retrieved_at": "2026-10-23",
            "source_table": SOURCE_TABLE,
            "storage": {
                "r2": {
                    "provider": "r2",
                    "bucket": "ledger-raw",
                    "key": r2_key,
                    "uri": f"r2://ledger-raw/{r2_key}",
                }
            },
            "notes": "R2 location declared only; upload after lane review. "
            + (
                "Deterministic cell transcription from source_capture; no derived observations."
                if key == 2025
                else "Immutable publisher PDF; 244 pages, permissions encrypted; empty user password."
            ),
        }
    _dump(
        data_dir / "manifest.yaml",
        {
            "source_id": "belgium",
            "package_id": PACKAGE_ID,
            "source_name": "FPD Jaarlijkse statistiek 2025 amount-band distributions",
            "publisher": "Federale Pensioendienst (FPD/SFPD)",
            "source_page": LANDING_URL,
            "files": files,
        },
    )
    package_dir.mkdir(parents=True, exist_ok=True)
    _dump(package_dir / "source_package.yaml", package_spec(rows))
    print(
        f"Extracted {len(rows)} rows, {sum(bool(r[m]) for r in rows for m in ('recipients', 'monthly_expenditure_eur'))} printed numeric cells; {len(check_totals(rows))} exact printed-total checks"
    )


if __name__ == "__main__":
    generate()
