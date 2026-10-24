"""Extract each published municipal rate; normalize representation only."""

from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from collections import Counter
from io import StringIO
from pathlib import Path

import yaml
from pypdf import PdfReader

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[2]
DATA_DIR = REPO_ROOT / "db/data/spf_finances/municipal_tax_rate_ay2026"
RAW_PATH = DATA_DIR / "municipal-tax-rate-2026.pdf"
RAW_SHA256 = "051211d85f05367002c31ad1879b294af50b8c14119d2127451bc976bd5e1606"
CATALOG_PATH = (
    REPO_ROOT
    / "db/data/statbel/population_structure_commune_2025"
    / "statbel_population_structure_commune_2025.csv"
)
CSV_PATH = DATA_DIR / "spf_finances_municipal_tax_rate_ay2026.csv"
AUDIT_PATH = PACKAGE_DIR / "commune_mapping_audit.csv"
PACKAGE_ID = "spf-finances-municipal-tax-rate-ay2026"
SOURCE_NAME = "spf_finances_municipal_tax_rate"
SOURCE_TABLE = "Municipal tax rates (%) for tax assessment year 2026"
SOURCE_URL = (
    "https://fin.belgium.be/sites/default/files/media/documents/"
    "municipal-tax-rate-2026.pdf"
)
ALTERNATE_URL = SOURCE_URL.replace("fin.belgium.be", "finances.belgium.be")
PERIOD_LABEL = "for tax assessment year 2026"
# Belgian packages key tax_year by income year and carry the assessment year
# as a constraint (statbel/fiscal_income_distribution_2023, spf_finances/pit_2023).
INCOME_YEAR = 2025
ASSESSMENT_YEAR = 2026
HEADERS = (
    "value_id",
    "period",
    "geography_id",
    "geography_level",
    "geography_name",
    "geography_vintage",
    "publisher_commune",
    "value",
    "source_page",
    "source_column_block",
    "source_line_start",
    "source_line_end",
    "source_rate_line",
    "source_rate_text",
    "source_sha256",
    "source_url",
    "match_tier",
    "income_year",
    "assessment_year",
)
AUDIT_HEADERS = HEADERS + ("source_municipality_nl", "source_municipality_fr")


def _normalized_name(label: str) -> str:
    decomposed = unicodedata.normalize("NFKD", label.casefold())
    return "".join(
        char
        for char in decomposed
        if not unicodedata.combining(char) and char not in "-'’‐‑– "
    )


def load_communes() -> dict[str, dict[str, str]]:
    """Use only the committed Statbel catalogue, including German NL aliases."""
    with CATALOG_PATH.open(encoding="utf-8", newline="") as stream:
        records = list(csv.DictReader(stream))
    catalog = {}
    for row in records:
        code = row["geography_id"]
        if row["value_id"] != f"nis_{code}_total":
            continue
        if code in catalog or row["geography_vintage"] != "nis_2025":
            raise ValueError(f"Duplicate or unexpected Statbel commune: {code}")
        catalog[code] = row
    if len(catalog) != 565:
        raise ValueError("Expected all 565 Statbel NIS 2025 communes")
    return catalog


def match_commune(label: str, catalog: dict) -> tuple[str, str]:
    """Exact NL/FR first, then the declared orthographic normalization only."""
    for tier, normalize in (
        ("exact_statbel", lambda value: value),
        ("orthographic_normalization", _normalized_name),
    ):
        candidates = {
            code
            for code, row in catalog.items()
            if any(
                normalize(label) == normalize(row[field])
                for field in ("source_municipality_nl", "source_municipality_fr")
            )
        }
        if len(candidates) > 1:
            raise ValueError(f"Ambiguous commune {label!r}: {sorted(candidates)}")
        if candidates:
            return candidates.pop(), tier
    raise ValueError(f"Unresolved commune: {label!r}")


def parse_pdf(path: Path = RAW_PATH) -> list[dict]:
    """Read all three blocks per page and retain physical pypdf text lines.

    Line numbers are 1-based in page.extract_text().splitlines(), counting blank
    lines. Blocks are the repeated CITY OR MUNICIPALITY / Rate (%) columns,
    numbered left to right (1..3). Wrapped names are joined before matching.
    """
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != RAW_SHA256 or len(content) != 182097:
        raise ValueError("Captured SPF Finances PDF checksum or size mismatch")
    reader = PdfReader(path)
    if len(reader.pages) != 5:
        raise ValueError("Expected five PDF pages")
    rows = []
    headings = []
    for page_number, page in enumerate(reader.pages, start=1):
        block = 0
        pending = []
        for line_number, line in enumerate(page.extract_text().splitlines(), start=1):
            text = line.strip()
            if not text or text == f"{page_number} / 5":
                continue
            if page_number == 1 and text in ("Municipal tax rates (%)", PERIOD_LABEL):
                headings.append(text)
                continue
            if text == "CITY OR MUNICIPALITY Rate (%)":
                if pending:
                    raise ValueError("Unfinished row at PDF block boundary")
                block += 1
                continue
            if not 1 <= block <= 3:
                raise ValueError(f"Unexpected PDF text before a block: {text!r}")
            pending.append((line_number, text))
            match = re.fullmatch(r"(?:(.+?)\s+)?(\d+,\d)", text)
            if match is None:
                if any(char.isdigit() for char in text):
                    raise ValueError(f"Unrecognized numeric PDF line: {text!r}")
                continue
            pieces = [value for _, value in pending[:-1]]
            if match[1]:
                pieces.append(match[1])
            label = ""
            for piece in pieces:
                label += ("" if not label or label.endswith("-") else " ") + piece
            if not label:
                raise ValueError("PDF rate without a municipality")
            rate_text = match[2]
            rows.append(
                {
                    "publisher_commune": label,
                    "value": rate_text.replace(",", "."),
                    "source_page": page_number,
                    "source_column_block": block,
                    "source_line_start": pending[0][0],
                    "source_line_end": line_number,
                    "source_rate_line": line_number,
                    "source_rate_text": rate_text,
                }
            )
            pending = []
        if pending or block != 3:
            raise ValueError(f"Incomplete PDF page {page_number}")
    if headings != ["Municipal tax rates (%)", PERIOD_LABEL]:
        raise ValueError("Publisher assessment-year heading changed")
    if len(rows) != 565:
        raise ValueError(f"Expected 565 published rate cells, got {len(rows)}")
    return rows


def assemble_rows(source_rows=None, catalog=None) -> list[dict]:
    """Require a bijection: exactly one published cell for every NIS commune."""
    source_rows = parse_pdf() if source_rows is None else source_rows
    catalog = load_communes() if catalog is None else catalog
    result = []
    seen_labels = set()
    seen_codes = set()
    for source in source_rows:
        label = source["publisher_commune"]
        code, tier = match_commune(label, catalog)
        if label in seen_labels or code in seen_codes:
            raise ValueError(f"Non-bijective commune mapping: {label!r} -> {code}")
        seen_labels.add(label)
        seen_codes.add(code)
        result.append(
            {
                "value_id": f"nis_{code}",
                "period": INCOME_YEAR,
                "geography_id": code,
                "geography_level": "commune",
                "geography_name": catalog[code]["geography_name"],
                "geography_vintage": "nis_2025",
                **source,
                "source_sha256": RAW_SHA256,
                "source_url": SOURCE_URL,
                "match_tier": tier,
                "income_year": INCOME_YEAR,
                "assessment_year": ASSESSMENT_YEAR,
            }
        )
    if seen_codes != set(catalog) or len(result) != 565:
        raise ValueError(
            f"Incomplete commune mapping; absent: {sorted(set(catalog) - seen_codes)}"
        )
    return result


class _NoAliasesDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _yaml_bytes(payload: dict) -> bytes:
    return yaml.dump(
        payload,
        Dumper=_NoAliasesDumper,
        sort_keys=False,
        allow_unicode=True,
        width=100,
    ).encode("utf-8")


def _csv_bytes(rows: list[dict], headers: tuple) -> bytes:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _storage(filename: str, sha: str, entry: str | int) -> dict:
    key = f"raw/belgium/{PACKAGE_ID}/{entry}/{sha}/{filename}"
    return {
        "r2": {
            "provider": "r2",
            "bucket": "ledger-raw",
            "key": key,
            "uri": f"r2://ledger-raw/{key}",
        }
    }


def _package_payload(rows: list[dict]) -> dict:
    prefix = "spf_finances.municipal_pit_surcharge.income_year2025.by_commune_nis2025"
    selected = []
    for row_number, row in enumerate(rows, start=2):
        selected.append(
            {
                "value_id": row["geography_id"],
                "label": row["geography_name"],
                "ordinal": len(selected),
                "row_number": row_number,
                "expected_row_header_column": "A",
                "expected_row_header": row["value_id"],
                "source_row_id": row["publisher_commune"],
                **{
                    key: row[key]
                    for key in (
                        "geography_id",
                        "geography_level",
                        "geography_name",
                        "geography_vintage",
                    )
                },
                "table_record_kind": "total",
                "filters": {"publisher_commune": row["publisher_commune"]},
                "constraints": [
                    {
                        "variable": "publisher_commune",
                        "operator": "==",
                        "value": row["publisher_commune"],
                        "label": "Publisher municipality",
                    }
                ],
                "guard_cells": [
                    {
                        "column": column,
                        "row": "start",
                        "expected_value": row[field],
                        "label": field,
                    }
                    for column, field in (
                        ("C", "geography_id"),
                        ("G", "publisher_commune"),
                        ("I", "source_page"),
                        ("J", "source_column_block"),
                        ("K", "source_line_start"),
                        ("L", "source_line_end"),
                        ("M", "source_rate_line"),
                    )
                ],
            }
        )
    return {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": (
            "SPF Finances municipal PIT surcharge rates, income year 2025 "
            "(tax assessment year 2026)"
        ),
        "dimension_labels": {
            "geography": "Geography",
            "publisher_commune": "Publisher municipality",
        },
        "artifact": {
            "source_name": SOURCE_NAME,
            "source_table": SOURCE_TABLE,
            "resource_package": "db",
            "resource_directory": "data/spf_finances/municipal_tax_rate_ay2026",
            "manifest": "manifest.yaml",
            "vintage": "municipal_tax_rate_ay2026_20260317",
            "extracted_at": "2026-10-23",
            "extraction_method": (
                "Deterministic full five-page PDF extraction; one printed rate per row; "
                "decimal comma representation only; page/block/physical text lines retained"
            ),
            "parser": "delimited_text_full_rows",
            "artifact_year": INCOME_YEAR,
            "sheet_name": CSV_PATH.stem,
        },
        "record_sets": [
            {
                "record_set_id": prefix,
                "provenance_class": "administrative",
                "record_set_spec_id": f"{prefix}.v1",
                "source_record_id_prefix": prefix,
                "sheet_name": CSV_PATH.stem,
                "period_type": "tax_year",
                "period": INCOME_YEAR,
                "period_coverage": {
                    "basis": "tax",
                    "source_period_label": PERIOD_LABEL,
                    "notes": (
                        "Publisher assessment year 2026 taxes income of 2025. As in the other "
                        "Belgian tax packages, the tax_year period is the income year and the "
                        "printed assessment year is kept as a constraint and in this label. "
                        "Income of policy year 2026 would require assessment-year 2027 rates, "
                        "which are absent from this artifact."
                    ),
                },
                "geography_id": "BE",
                "geography_level": "country",
                "geography_name": "Belgium",
                "geography_vintage": "current",
                "entity": "government",
                "domain": "personal_income_tax",
                "groupby_dimension": "geography",
                "shared_constraints": [
                    {
                        "variable": "income_year",
                        "operator": "==",
                        "value": INCOME_YEAR,
                        "label": "Publisher income year",
                    },
                    {
                        "variable": "assessment_year",
                        "operator": "==",
                        "value": ASSESSMENT_YEAR,
                        "label": "Publisher assessment year",
                    },
                ],
                "rows": selected,
                "measures": [
                    {
                        "measure_id": "municipal_pit_surcharge_rate",
                        "label": "Rate (%)",
                        "ordinal": 0,
                        "column": "H",
                        "source_column_id": "value",
                        "expected_column_header_row": 1,
                        "expected_column_header": "value",
                        "concept": "municipal_pit_surcharge_rate",
                        "source_concept": "spf_finances.municipal_pit_surcharge_rate",
                        "concept_relation": "source_label",
                        "concept_authority": "spf_finances",
                        "concept_evidence_url": SOURCE_URL,
                        "concept_evidence_notes": (
                            "Publisher heading Municipal tax rates (%) for tax assessment year 2026 "
                            "and repeated CITY OR MUNICIPALITY / Rate (%) columns. "
                            "Direct administrative rate in percent; no averaging or scaling."
                        ),
                        "legal_vintage": "income_year_2025_assessment_year_2026",
                        "unit": "percent",
                        "aggregation": "rate",
                        "expected_cell_type": "number",
                    }
                ],
            }
        ],
    }


def render_outputs() -> dict[Path, bytes]:
    rows = assemble_rows()
    content = _csv_bytes(rows, HEADERS)
    catalog = load_communes()
    audit = [
        {
            **row,
            **{
                key: catalog[row["geography_id"]][key]
                for key in (
                    "source_municipality_nl",
                    "source_municipality_fr",
                )
            },
        }
        for row in rows
    ]
    entries = {}
    for entry, filename, data in (
        (INCOME_YEAR, CSV_PATH.name, content),
        ("source_capture", RAW_PATH.name, RAW_PATH.read_bytes()),
    ):
        sha = hashlib.sha256(data).hexdigest()
        entries[entry] = {
            "filename": filename,
            "source_url": SOURCE_URL,
            "source_urls": [SOURCE_URL, ALTERNATE_URL],
            "source_table": SOURCE_TABLE,
            "sha256": sha,
            "size_bytes": len(data),
            "retrieved_at": "2026-10-23",
            "storage": _storage(filename, sha, entry),
            "notes": (
                "Verbatim publisher PDF, created 2026-03-17; title Municipal tax rate | FPS Finance. "
                if entry == "source_capture"
                else "Representation-only extract of all 565 PDF cells; exact page/block/text-line locators. "
            )
            + (
                "Downloaded by HTTP GET from fin.belgium.be; the same path on "
                "finances.belgium.be is recorded but was not fetched. "
                "Uploaded to R2 ledger-raw and verified by SHA-256 readback on 2026-10-24."
            ),
        }
    manifest = {
        "source_id": "belgium",
        "package_id": PACKAGE_ID,
        "source_name": "SPF Finances municipal PIT surcharge rates AY2026",
        "publisher": "FPS Finance / SPF Finances / FOD Financiën",
        "source_page": SOURCE_URL,
        "files": entries,
    }
    return {
        CSV_PATH: content,
        AUDIT_PATH: _csv_bytes(audit, AUDIT_HEADERS),
        DATA_DIR / "manifest.yaml": _yaml_bytes(manifest),
        PACKAGE_DIR / "source_package.yaml": _yaml_bytes(_package_payload(rows)),
    }


def main() -> None:
    outputs = render_outputs()
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    with CSV_PATH.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    print(
        f"{len(rows)} published cells; mapping tiers: "
        f"{dict(Counter(row['match_tier'] for row in rows))}"
    )


if __name__ == "__main__":
    main()
