#!/usr/bin/env python3
"""Transcribe printed article figures; never calculate new observations.

The input is a sanitized browser transcription, not publisher response bytes.
Its immutable hash and per-figure sentence/table locators preserve that limit.
Run from any directory to regenerate the curated CSV, manifest and package YAML.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[2]
DATA_DIR = REPO_ROOT / "db/data/ostbelgien/kindergeld_2025"
PACKAGE_ID = "ostbelgien-kindergeld-2025"
CAPTURE_NAME = "kindergeld-in-ostbelgien.article.html"
CSV_NAME = "ostbelgien_kindergeld_2025.csv"
CAPTURE_SHA256 = "c570d9b5cef3bb100c4caf1ca8db528376d6f7b3176968d3d259bb947d2801c5"
SOURCE_URL = (
    "https://ostbelgienstatistik.be/desktopdefault.aspx/tabid-3748/6766_read-39090/"
)
SOURCE_TABLE = "Kindergeld in Ostbelgien, Aktualisierung vom 31.03.2026"
SCOPE_ID = "ostbelgien:deutschsprachige_gemeinschaft"
# The article's own name for the area (harness: publisher geography wording).
SCOPE_NAME = "Deutschsprachige Gemeinschaft"
COMMUNES = {
    "63001": "Amel",
    "63012": "Büllingen",
    "63013": "Bütgenbach",
    "63023": "Eupen",
    "63040": "Kelmis",
    "63048": "Lontzen",
    "63061": "Raeren",
    "63067": "Sankt Vith",
    "63087": "Burg-Reuland",
}
DIMENSIONS = {
    "ostbelgien.population": "Kindergeld: veröffentlichte Zähleinheit",
    "ostbelgien.amount_type": "Kindergeld: Betragssystem",
    "ostbelgien.age_group": "Altersgruppe",
    "ostbelgien.supplement": "Zuschlag",
    "ostbelgien.premium": "Prämie",
    "ostbelgien.expenditure_component": "Ausgaben Familienleistungen",
}
HEADERS = [
    "value_id",
    "table",
    "row_label",
    *DIMENSIONS,
    "value_raw",
    "value",
    "unit",
    "reference_basis",
    "source_period_label",
    "source_locator",
    "table_record_kind",
    "entity",
    "entity_role",
]
AGE_TABLE = "Verteilung des Kindergelds nach Altersgruppen"
SUPPLEMENT_TABLE = "Verteilung des Kindergelds nach Zuschlag"
EXPENDITURE_TABLE = "Ausgaben Familienleistungen im Jahr 2025"
CASELOAD_TABLE = "Text: Kindergeld und Empfänger"
PREMIUM_TABLE = "Text: Geburts- und Adoptionsprämie"


class Element:
    def __init__(self, tag: str):
        self.tag = tag
        self.parts: list[str | Element] = []

    def text(self) -> str:
        return " ".join(
            "".join(
                p.text() if isinstance(p, Element) else p for p in self.parts
            ).split()
        )

    def descendants(self, tag: str):
        for part in self.parts:
            if isinstance(part, Element):
                if part.tag == tag:
                    yield part
                yield from part.descendants(tag)


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Element(tag)
        self.stack[-1].parts.append(node)
        if tag not in {"br", "hr", "img", "input", "meta", "link", "wbr"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if len(self.stack) > 1 and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_data(self, data):
        self.stack[-1].parts.append(data)


def parse_number(raw: str) -> str:
    """Normalize German number notation; preserve published precision."""
    text = raw.replace("%", "").replace(" ", "").replace(".", "")
    return str(Decimal(text.replace(",", ".")))


def extract_rows(path: Path) -> list[dict]:
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != CAPTURE_SHA256:
        raise ValueError("Article evidence transcription checksum mismatch")
    parser = ArticleParser()
    parser.feed(content.decode("utf-8"))
    paragraphs = [p.text() for p in parser.root.descendants("p")]
    rows = []

    def paragraph(fragment):
        matches = [p for p in paragraphs if fragment in p]
        if len(matches) != 1:
            raise ValueError(f"Expected one evidence paragraph: {fragment}")
        return matches[0]

    def add(
        value_id,
        table,
        label,
        raw,
        unit,
        basis,
        period_label,
        locator,
        axis,
        category,
        population,
        entity="person",
        role="benefit_recipient",
        total=False,
    ):
        row = dict.fromkeys(HEADERS, "")
        row.update(
            {
                "value_id": value_id,
                "table": table,
                "row_label": label,
                "value_raw": raw,
                "value": parse_number(raw),
                "unit": unit,
                "reference_basis": basis,
                "source_period_label": period_label,
                "source_locator": locator,
                "table_record_kind": "total" if total else "detail",
                "entity": entity,
                "entity_role": role,
                "ostbelgien.population": population,
                axis: category,
            }
        )
        rows.append(row)

    def narrative(value_id, pattern, evidence, population, amount, unit="count"):
        match = re.search(pattern, evidence)
        if not match:
            raise ValueError(f"Sentence selector failed: {value_id}")
        add(
            value_id,
            CASELOAD_TABLE,
            f"{population}: {amount}",
            match[1],
            unit,
            "december_2025",
            "Dezember 2025",
            evidence,
            "ostbelgien.amount_type",
            amount,
            population,
            total=amount == "Insgesamt",
        )

    headline = paragraph("Insgesamt wurde im Dezember 2025")
    recipients = paragraph("verteilen sich auf")
    transition = paragraph("Übergangsregelung geschaffen")
    narrative("children_total", r"für ([\d.]+) Kinder", headline, "Kinder", "Insgesamt")
    narrative(
        "recipients_total",
        r"auf ([\d.]+) Empfänger",
        recipients,
        "Empfänger",
        "Insgesamt",
    )
    for value_id, pattern, population, amount, unit in (
        (
            "children_protected",
            r"erhielten ([\d.]+) Kinder",
            "Kinder",
            "festgehaltener Betrag",
            "count",
        ),
        ("children_new", r"und ([\d.]+) Kinder", "Kinder", "neuer Betrag", "count"),
        (
            "recipients_protected",
            r"erhielten ([\d.]+) \(",
            "Empfänger",
            "festgehaltener Betrag",
            "count",
        ),
        (
            "recipients_new",
            r"und ([\d.]+) Empfänger",
            "Empfänger",
            "neuer Betrag",
            "count",
        ),
        (
            "children_protected_share",
            r"Kinder, d.h. ([\d,]+ %)",
            "Kinder",
            "festgehaltener Betrag",
            "percent",
        ),
        (
            "children_new_share",
            r"Kinder, d.h. ([\d,]+ %), einen neuen",
            "Kinder",
            "neuer Betrag",
            "percent",
        ),
        (
            "recipients_protected_share",
            r"139 \(([\d,]+ %)\)",
            "Empfänger",
            "festgehaltener Betrag",
            "percent",
        ),
        (
            "recipients_new_share",
            r"Empfänger \(([\d,]+ %)\)",
            "Empfänger",
            "neuer Betrag",
            "percent",
        ),
    ):
        narrative(value_id, pattern, transition, population, amount, unit)

    # Ignore empty layout tables, and retain every printed row of the three data tables.
    tables = [t for t in parser.root.descendants("table") if list(t.descendants("tr"))]
    if len(tables) != 3:
        raise ValueError("Expected exactly three populated article tables")
    definitions = (
        (
            AGE_TABLE,
            "ostbelgien.age_group",
            "publisher_year_2025_ambiguous",
            "Kinder",
            [
                ("age_0_17", "0-17 Jahre"),
                ("age_18_24", "18-24 Jahre"),
                ("age_25_plus", "25 Jahre und älter"),
                ("age_total", "Total"),
            ],
        ),
        (
            SUPPLEMENT_TABLE,
            "ostbelgien.supplement",
            "end_2025",
            "Kinder",
            [
                ("supplement_social", "Sozialzuschlag"),
                ("supplement_large_family", "Zuschlag für kinderreiche Familien"),
                ("supplement_disability", "Zuschlag für Kinder mit Beeinträchtigung"),
                ("supplement_half_orphan", "Halbwaisenzuschlag"),
                ("supplement_full_orphan", "Vollwaisenzuschlag"),
            ],
        ),
        (
            EXPENDITURE_TABLE,
            "ostbelgien.expenditure_component",
            "calendar_year_2025",
            "Ausgaben",
            [
                ("expenditure_basic", "Basiskindergeld"),
                ("expenditure_disability", "Zuschlag Beeinträchtigung"),
                ("expenditure_social", "Sozialzuschlag"),
                ("expenditure_annual", "Jahreszuschlag"),
                ("expenditure_large_family", "Zuschlag für kinderreiche Familien"),
                ("expenditure_half_orphan", "Halbwaisenzuschlag"),
                ("expenditure_full_orphan", "Vollwaisenzuschlag"),
                ("expenditure_new_total", "Kindergeld neuer Betrag"),
                ("expenditure_protected", "Kindergeld festgehaltener Betrag"),
                ("expenditure_birth", "Geburtsprämie"),
                ("expenditure_adoption", "Adoptionsprämie"),
                ("expenditure_premiums_total", "Prämien"),
                ("expenditure_other", "Sonstiges (Korrekturen, Verträge etc.)"),
                ("expenditure_total", "Total Familienleistungen"),
            ],
        ),
    )
    for table, (title, axis, basis, population, labels) in zip(tables, definitions):
        cells = [
            [
                p.text()
                for p in tr.parts
                if isinstance(p, Element) and p.tag in {"td", "th"}
            ]
            for tr in table.descendants("tr")
        ]
        if cells[0] != ["", "2025"] or [c[0] for c in cells[1:]] != [
            label for _, label in labels
        ]:
            raise ValueError(f"Published table labels changed: {title}")
        for (value_id, label), (_, raw) in zip(labels, cells[1:]):
            expenditure = title == EXPENDITURE_TABLE
            add(
                value_id,
                title,
                label,
                raw,
                "eur" if expenditure else "count",
                basis,
                "2025",
                f'Tabelle "{title}"; Zeile "{label}"; Spalte "2025"',
                axis,
                label,
                population,
                entity="government" if expenditure else "person",
                role="payer" if expenditure else "benefit_recipient",
                total=label
                in {
                    "Total",
                    "Kindergeld neuer Betrag",
                    "Prämien",
                    "Total Familienleistungen",
                },
            )

    premium = paragraph("2025 wurde die Geburtsprämie")
    match = re.search(
        r"Geburtsprämie ([\d.]+) und die Adoptionsprämie (einmal) ausgezahlt", premium
    )
    if not match:
        raise ValueError("Premium payment sentence changed")
    for value_id, label, raw in (
        ("birth_premium_payments", "Geburtsprämie", match[1]),
        ("adoption_premium_payments", "Adoptionsprämie", match[2]),
    ):
        add(
            value_id,
            PREMIUM_TABLE,
            label,
            "1" if raw == "einmal" else raw,
            "count",
            "calendar_year_2025",
            "2025",
            premium,
            "ostbelgien.premium",
            label,
            "Prämienauszahlungen",
            entity="benefit_unit",
            role="premium_payment",
        )
        rows[-1]["value_raw"] = raw  # Preserve the publisher's word for one occurrence.
    return rows


class LiteralDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def dump(path: Path, payload: dict) -> None:
    path.write_text(
        yaml.dump(
            payload,
            Dumper=LiteralDumper,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        ),
        encoding="utf-8",
    )


def constraint(key, value):
    return {"variable": key, "operator": "==", "value": value, "label": DIMENSIONS[key]}


def package_spec(rows: list[dict]) -> dict:
    tables = {
        CASELOAD_TABLE: "caseload",
        AGE_TABLE: "age",
        SUPPLEMENT_TABLE: "supplements",
        PREMIUM_TABLE: "premiums",
        EXPENDITURE_TABLE: "expenditure",
    }
    grouped = defaultdict(list)
    for row_number, row in enumerate(rows, start=2):
        grouped[
            (
                row["table"],
                row["entity"],
                row["ostbelgien.population"],
                row["unit"],
                row["reference_basis"],
            )
        ].append((row_number, row))
    sets = []
    for (table, entity, population, unit, basis), members in grouped.items():
        first = members[0][1]
        axis = next(
            key for key in DIMENSIONS if key != "ostbelgien.population" and first[key]
        )
        stem = f"ostbelgien.kindergeld.cy2025.{tables[table]}"
        metric = {"percent": "published_share_percent", "eur": "expenditure_eur"}.get(
            unit, "count"
        )
        subgroup = {
            "Kinder": "children",
            "Empfänger": "recipients",
            "Ausgaben": "spending",
            "Prämienauszahlungen": "payments",
        }[population]
        snapshot = basis in {"december_2025", "end_2025"}
        notes = (
            "Published December/end-December stock; represented at 31 December, not an annual flow."
            if snapshot
            else "Publisher's calendar-year 2025 payments or expenditure."
        )
        if table == AGE_TABLE:
            notes = (
                'Publisher column label "2025"; prose says "die 2025 Kindergeld von der '
                'Deutschsprachigen Gemeinschaft erhalten haben". Full-year dates represent that '
                "label only. Total equals the December stock, but the article does not establish "
                "whether these are annual unique recipients or a December age distribution."
            )
        if table == SUPPLEMENT_TABLE:
            notes += " A child may receive two supplements; rows overlap and no total is published."
        record_set = {
            "record_set_id": f"{stem}.{subgroup}.{metric}",
            "provenance_class": "administrative",
            "assertion": "observation",
            "record_set_spec_id": stem + ".v1",
            "source_record_id_prefix": stem,
            "sheet_name": "ostbelgien_kindergeld_2025",
            "period_type": "calendar_year",
            "period": 2025,
            "period_coverage": {
                "start_date": "2025-12-31" if snapshot else "2025-01-01",
                "end_date": "2025-12-31",
                "basis": "calendar",
                "source_period_label": first["source_period_label"],
                "notes": notes,
            },
            "geography_id": SCOPE_ID,
            "geography_level": "statistical_scope",
            "geography_name": SCOPE_NAME,
            "geography_vintage": "nis_2025",
            "entity": entity,
            "entity_role": first["entity_role"],
            "domain": "child_benefit",
            "groupby_dimension": axis,
            "shared_filters": {"ostbelgien.population": population},
            "shared_constraints": [constraint("ostbelgien.population", population)],
            "rows": [],
        }
        for ordinal, (number, row) in enumerate(members):
            record_set["rows"].append(
                {
                    "value_id": row["value_id"],
                    "label": row[axis],
                    "ordinal": ordinal,
                    "row_number": number,
                    "expected_row_header_column": "A",
                    "expected_row_header": row["value_id"],
                    "guard_cells": [
                        {
                            "column": chr(65 + HEADERS.index(col)),
                            "row": "start",
                            "expected_value": row[col],
                            "label": col,
                        }
                        for col in (
                            "table",
                            "row_label",
                            axis,
                            "unit",
                            "reference_basis",
                            "source_locator",
                        )
                    ],
                    "table_record_kind": row["table_record_kind"],
                    "filters": {axis: row[axis]},
                    "constraints": [constraint(axis, row[axis])],
                }
            )
        concept = f"ostbelgien.kindergeld.{subgroup}.{metric}"
        record_set["measures"] = [
            {
                "measure_id": metric,
                "label": f"{population}: {metric}",
                "ordinal": 0,
                "column": chr(65 + HEADERS.index("value")),
                "source_column_id": "value",
                "expected_column_header_row": 1,
                "expected_column_header": "value",
                "concept": concept,
                "source_concept": concept,
                "concept_relation": "source_label",
                "concept_authority": "publisher",
                "concept_evidence_url": SOURCE_URL,
                "concept_evidence_notes": (
                    "Direct publisher figure in the hashed sanitized browser article transcription; "
                    "the CSV preserves the exact sentence or table/row/column locator and raw lexeme. "
                    "Published shares remain percentage values as printed, not recalculated ratios. "
                    "Empfänger are payees, not an asserted household count. Premium counts are "
                    "payment occurrences, not unique children. See README for scope and definitions."
                ),
                "unit": unit,
                "aggregation": "share" if unit == "percent" else "sum",
                "expected_cell_type": "number",
            }
        ]
        sets.append(record_set)
    return {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": "Ostbelgien Kindergeld 2025: caseload, premiums and expenditure",
        "artifact": {
            "source_name": "ostbelgien_kindergeld",
            "source_table": SOURCE_TABLE,
            "resource_package": "db",
            "resource_directory": "data/ostbelgien/kindergeld_2025",
            "manifest": "manifest.yaml",
            "vintage": "aktualisierung_2026_03_31",
            "extracted_at": "2026-10-24",
            "extraction_method": "Curated CSV from checksum-pinned sanitized browser article transcription; build_package.py",
            "parser": "delimited_text_full_rows",
            "artifact_year": 2025,
            "sheet_name": "ostbelgien_kindergeld_2025",
        },
        "dimension_labels": DIMENSIONS,
        "dimension_value_labels": {
            key: {value: value for value in sorted({r[key] for r in rows if r[key]})}
            for key in DIMENSIONS
        },
        "record_sets": sets,
    }


def generate(data_dir: Path = DATA_DIR, package_dir: Path = PACKAGE_DIR) -> None:
    rows = extract_rows(data_dir / CAPTURE_NAME)
    csv_path = data_dir / CSV_NAME
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    files = {}
    for key, path in ((2025, csv_path), ("source_capture", data_dir / CAPTURE_NAME)):
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        r2_key = f"raw/belgium/{PACKAGE_ID}/{key}/{sha}/{path.name}"
        files[key] = {
            "filename": path.name,
            "source_url": SOURCE_URL,
            "source_table": SOURCE_TABLE,
            "sha256": sha,
            "size_bytes": path.stat().st_size,
            "retrieved_at": "2026-10-24",
            "artifact_kind": "curated_extract"
            if key == 2025
            else "sanitized_browser_transcription",
            "storage": {
                "r2": {
                    "provider": "r2",
                    "bucket": "ledger-raw",
                    "key": r2_key,
                    "uri": f"r2://ledger-raw/{r2_key}",
                }
            },
            "notes": "Uploaded to R2 ledger-raw and verified by SHA-256 readback on 2026-10-24. "
            + (
                "One published figure per row; not publisher bytes. Derived only by German number-format "
                "normalization and einmal=1. Repeated prose headlines are not duplicated; the age-table "
                "total is a separate printed cell. Four publisher percentages retained verbatim."
                if key == 2025
                else "Browser capture 2026-10-24 ~01:10Z (Claude desktop built-in browser). Article outerHTML "
                "with script/style elements, class/style/id/data-* attributes and comments stripped; "
                "whitespace collapsed. Original capture header retained. A transcription for evidence, "
                "not the publisher's byte stream; plain clients receive a Cloudflare challenge."
            ),
        }
    dump(
        data_dir / "manifest.yaml",
        {
            "source_id": "belgium",
            "package_id": PACKAGE_ID,
            "source_name": SOURCE_TABLE,
            "publisher": "Ministerium der Deutschsprachigen Gemeinschaft Belgiens, Fachbereich Familienleistungen",
            "source_page": SOURCE_URL,
            "reuse_status": "no licence stated; figures cited with attribution",
            "reuse_reference": "https://ostbelgienstatistik.be/desktopdefault.aspx/tabid-2399/",
            "geography_scope": {
                "id": SCOPE_ID,
                "name": SCOPE_NAME,
                "level": "statistical_scope",
                "vintage": "nis_2025",
                "definition": "Belgian German-speaking Community: territory of these nine communes in Liège province; not a NUTS region.",
                "membership_source": "db/data/statbel/population_structure_commune_2025/statbel_population_structure_commune_2025.csv",
                "communes": [
                    {"nis_2025": code, "geography_name": name}
                    for code, name in COMMUNES.items()
                ],
            },
            "status": "semantic_candidate",
            "files": files,
        },
    )
    dump(package_dir / "source_package.yaml", package_spec(rows))
    print(
        f"Extracted {len(rows)} published figures from the pinned article transcription"
    )


if __name__ == "__main__":
    generate()
