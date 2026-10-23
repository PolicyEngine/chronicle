#!/usr/bin/env python3
"""Reproduce commune population facts from the captured Statbel 2025 release.

Only sum publisher MS_POPULATION cells over nationality, marital status and
single-year ages. The source already uses NIS 2025 municipality codes. Source
line numbers (header is line 1, population is column U) are retained for every
aggregate. No geographic translation or period alignment is performed.
"""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from io import StringIO, TextIOWrapper
from pathlib import Path
from zipfile import ZipFile

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[2]
DATA_ROOT = REPO_ROOT / "db/data/statbel"
DATA_DIR = DATA_ROOT / "population_structure_commune_2025"
CSV_FILENAME = "statbel_population_structure_commune_2025.csv"
CSV_PATH = DATA_DIR / CSV_FILENAME
MANIFEST_PATH = DATA_DIR / "manifest.yaml"
SOURCE_PACKAGE_PATH = PACKAGE_DIR / "source_package.yaml"
RAW_PATH = DATA_ROOT / "population_structure_nuts1_2025/TF_SOC_POP_STRUCT_2025.zip"
RAW_MANIFEST = RAW_PATH.parent / "manifest.yaml"
CROSSWALK_PATH = (
    DATA_ROOT / "nis_2025_commune_crosswalk/statbel_nis_2025_commune_crosswalk.csv"
)
FISCAL_PATH = (
    DATA_ROOT
    / "fiscal_income_commune_2023_nis_2025"
    / "statbel_fiscal_income_commune_2023_nis_2025.csv"
)
NUTS1_PATH = RAW_PATH.parent / "statbel_population_structure_nuts1_2025.csv"
PACKAGE_ID = "statbel-population-structure-commune-2025"
MEMBER = "TF_SOC_POP_STRUCT_2025.txt"
RAW_SHA256 = "33910ea36437e39cfffd82ad82c759a2a8d1f2ab7662d45ce71c8ec9f336716c"
EXTRACTED_AT = "2026-10-23"
LANDING_PAGE = "https://data.gov.be/en/datasets/nodeid5468"
SOURCE_TABLE = (
    "Population by place of residence, nationality, marital status, age and sex, "
    "2025, NIS 2025 communes"
)
REGIONS = {"04000": "BE1", "02000": "BE2", "03000": "BE3"}
SEXES = {"M": "male", "F": "female"}
AGE_BANDS = (("0_17", 0, 18), ("18_64", 18, 65), ("65_plus", 65, None))
CATEGORIES = ("total",) + tuple(
    f"{sex}_{band}" for sex in SEXES.values() for band, *_ in AGE_BANDS
)
HEADERS = (
    "value_id",
    "period",
    "geography_id",
    "geography_level",
    "geography_name",
    "geography_vintage",
    "person.sex",
    "person.age_band",
    "age",
    "value",
    "nuts1_id",
    "source_member",
    "source_rows",
    "source_url",
    "source_sha256",
    "source_municipality_nl",
    "source_municipality_fr",
    "source_region_code",
)


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


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _source_url() -> str:
    return yaml.safe_load(RAW_MANIFEST.read_text())["files"]["source_capture"][
        "source_url"
    ]


def _line_ranges(numbers: list[int]) -> str:
    """Losslessly encode ascending publisher line numbers as inclusive ranges."""
    parts = []
    start = end = numbers[0]
    for number in numbers[1:]:
        if number == end + 1:
            end = number
        else:
            parts.append(str(start) if start == end else f"{start}-{end}")
            start = end = number
    parts.append(str(start) if start == end else f"{start}-{end}")
    return ";".join(parts)


def aggregate_rows() -> list[dict[str, str | int]]:
    """Stream the pinned ZIP and return the seven published-count sums per commune."""
    if hashlib.sha256(RAW_PATH.read_bytes()).hexdigest() != RAW_SHA256:
        raise ValueError("Captured Statbel ZIP checksum mismatch")
    crosswalk = _csv_rows(CROSSWALK_PATH)
    names = {
        row["geography_id"]: row["geography_name"] for row in _csv_rows(FISCAL_PATH)
    }
    targets = {row["target_nis"] for row in crosswalk}
    if len(targets) != 565 or targets != set(names):
        raise ValueError("NIS 2025 commune catalogs disagree")

    counts: dict[tuple[str, str], int] = defaultdict(int)
    lines: dict[tuple[str, str], list[int]] = defaultdict(list)
    geography: dict[str, tuple[str, str, str]] = {}
    with ZipFile(RAW_PATH) as archive:
        if archive.namelist() != [MEMBER]:
            raise ValueError("Expected the single captured population text member")
        with (
            archive.open(MEMBER) as raw,
            TextIOWrapper(raw, encoding="utf-8-sig") as stream,
        ):
            reader = csv.DictReader(stream, delimiter="|")
            if reader.fieldnames[-1] != "MS_POPULATION":
                raise ValueError("Publisher population column changed")
            for line, row in enumerate(reader, start=2):
                code = row["CD_REFNIS"]
                sex = SEXES[row["CD_SEX"]]
                age = int(row["CD_AGE"])
                population = int(row["MS_POPULATION"])
                if not 0 <= age <= 100 or population < 0:
                    raise ValueError(
                        f"Unexpected publisher age or count on line {line}"
                    )
                band = "0_17" if age < 18 else "18_64" if age < 65 else "65_plus"
                meta = (row["TX_DESCR_NL"], row["TX_DESCR_FR"], row["CD_RGN_REFNIS"])
                if geography.setdefault(code, meta) != meta:
                    raise ValueError(f"Publisher geography varies within {code}")
                for category in ("total", f"{sex}_{band}"):
                    counts[code, category] += population
                    lines[code, category].append(line)

    if set(geography) != targets:
        raise ValueError("ZIP commune codes are not exactly the NIS 2025 catalog")
    source_url = _source_url()
    rows = []
    regional = defaultdict(int)
    for code in sorted(geography):
        nl, fr, region_code = geography[code]
        nuts1 = REGIONS[region_code]
        for category in CATEGORIES:
            if category == "total":
                sex, band, age_label = "", "", "All ages"
            else:
                sex, band = category.split("_", 1)
                age_label = {
                    "0_17": "Aged 0 to 17",
                    "18_64": "Aged 18 to 64",
                    "65_plus": "Aged 65 and over",
                }[band]
                regional[nuts1, sex, band] += counts[code, category]
            if not lines[code, category]:
                raise ValueError(f"Publisher category missing: {code} {category}")
            rows.append(
                dict(
                    zip(
                        HEADERS,
                        (
                            f"nis_{code}_{category}",
                            2025,
                            code,
                            "commune",
                            names[code],
                            "nis_2025",
                            sex,
                            band,
                            age_label,
                            counts[code, category],
                            nuts1,
                            MEMBER,
                            _line_ranges(lines[code, category]),
                            source_url,
                            RAW_SHA256,
                            nl,
                            fr,
                            region_code,
                        ),
                        strict=True,
                    )
                )
            )
    expected = {
        (row["geography_id"], row["person.sex"], row["person.age_band"]): int(
            row["value"]
        )
        for row in _csv_rows(NUTS1_PATH)
    }
    if dict(regional) != expected:
        raise ValueError(
            "Commune sums do not exactly reproduce all 18 NUTS1 observations"
        )
    return rows


def _package_payload(rows: list[dict]) -> dict:
    record_sets = []
    for category in CATEGORIES:
        prefix = (
            f"statbel.population_structure.cy2025.people.by_commune_nis2025.{category}"
        )
        record_set = {
            "record_set_id": prefix,
            "provenance_class": "census",
            "record_set_spec_id": f"statbel.population_structure.people.by_commune_nis2025.{category}.v1",
            "source_record_id_prefix": prefix,
            "sheet_name": CSV_PATH.stem,
            "period_type": "calendar_year",
            "period": 2025,
            "period_coverage": {
                "start_date": "2025-01-01",
                "end_date": "2025-01-01",
                "basis": "calendar",
                "source_period_label": "Population on 1 January 2025",
            },
            "geography_id": "BE",
            "geography_level": "country",
            "geography_name": "Belgium",
            "geography_vintage": "current",
            "entity": "person",
            "domain": "resident_population",
            "groupby_dimension": "geography",
        }
        if category != "total":
            sex, band = category.split("_", 1)
            _, lower, upper = next(item for item in AGE_BANDS if item[0] == band)
            record_set["shared_filters"] = {"person.sex": sex, "person.age_band": band}
            record_set["shared_constraints"] = [
                {
                    "variable": "person.sex",
                    "operator": "==",
                    "value": sex,
                    "label": "Sex",
                },
                {
                    "variable": "person.age_band",
                    "operator": "==",
                    "value": band,
                    "label": "Age band",
                },
                {
                    "variable": "person.age",
                    "operator": ">=",
                    "value": lower,
                    "unit": "years",
                    "label": "Age lower bound",
                },
            ]
            if upper is not None:
                record_set["shared_constraints"].append(
                    {
                        "variable": "person.age",
                        "operator": "<",
                        "value": upper,
                        "unit": "years",
                        "label": "Age upper bound",
                    }
                )
        selected = []
        for row_number, row in enumerate(rows, start=2):
            if row["value_id"] != f"nis_{row['geography_id']}_{category}":
                continue
            selected.append(
                {
                    "value_id": row["geography_id"],
                    "label": row["geography_name"],
                    "ordinal": len(selected),
                    "row_number": row_number,
                    "expected_row_header_column": "A",
                    "expected_row_header": row["value_id"],
                    "geography_id": row["geography_id"],
                    "geography_level": "commune",
                    "geography_name": row["geography_name"],
                    "geography_vintage": "nis_2025",
                    "table_record_kind": "total" if category == "total" else "detail",
                    "guard_cells": [
                        {
                            "column": column,
                            "row": "start",
                            "expected_value": row[field],
                            "label": field,
                        }
                        for column, field in (
                            ("C", "geography_id"),
                            ("G", "person.sex"),
                            ("H", "person.age_band"),
                            ("I", "age"),
                        )
                        if row[field] != ""
                    ],
                }
            )
        record_set["rows"] = selected
        record_set["measures"] = [
            {
                "measure_id": "people",
                "label": "Resident population",
                "ordinal": 0,
                "column": "J",
                "source_column_id": "value",
                "expected_column_header_row": 1,
                "expected_column_header": "value",
                "concept": "people",
                "source_concept": "statbel.population_structure.population",
                "concept_relation": "exact",
                "concept_authority": "ledger-be",
                "concept_evidence_url": LANDING_PAGE,
                "concept_evidence_notes": "Statbel resident population on 1 January 2025 by municipality, age and sex.",
                "unit": "count",
                "aggregation": "sum",
                "expected_cell_type": "number",
            }
        ]
        record_sets.append(record_set)
    return {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": "Statbel population on 1 January 2025 by NIS 2025 commune, sex and age band",
        "dimension_labels": {
            "geography": "Geography",
            "person.sex": "Sex",
            "person.age_band": "Age band",
        },
        "artifact": {
            "source_name": "statbel_population_structure",
            "source_table": SOURCE_TABLE,
            "resource_package": "db",
            "resource_directory": "data/statbel/population_structure_commune_2025",
            "manifest": "manifest.yaml",
            "vintage": "statbel_population_structure_2025",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": "Deterministic sums of captured Statbel MS_POPULATION cells; source member and inclusive line ranges retained per row; already NIS 2025 codes; no crosswalk aggregation",
            "parser": "delimited_text_full_rows",
            "artifact_year": 2025,
            "sheet_name": CSV_PATH.stem,
        },
        "record_sets": record_sets,
    }


def render_outputs() -> dict[Path, bytes]:
    """Return reproducible package files without mutating the workspace."""
    rows = aggregate_rows()
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, HEADERS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    content = stream.getvalue().encode("utf-8")
    sha = hashlib.sha256(content).hexdigest()
    key = f"raw/belgium/{PACKAGE_ID}/2025/{sha}/{CSV_FILENAME}"
    capture = yaml.safe_load(RAW_MANIFEST.read_text())["files"]["source_capture"]
    capture["filename"] = f"../population_structure_nuts1_2025/{RAW_PATH.name}"
    capture["manifest"] = "../population_structure_nuts1_2025/manifest.yaml"
    capture["manifest_entry"] = "source_capture"
    capture["notes"] = (
        "Same captured publisher ZIP as the NUTS1 package, referenced in place; no duplicate bytes or upload."
    )
    manifest = {
        "source_id": "belgium",
        "package_id": PACKAGE_ID,
        "source_name": "Statbel commune population structure 2025",
        "publisher": "Statbel",
        "source_page": LANDING_PAGE,
        "files": {
            2025: {
                "filename": CSV_FILENAME,
                "source_url": _source_url(),
                "source_table": SOURCE_TABLE,
                "sha256": sha,
                "size_bytes": len(content),
                "storage": {
                    "r2": {
                        "provider": "r2",
                        "bucket": "ledger-raw",
                        "key": key,
                        "uri": f"r2://ledger-raw/{key}",
                    }
                },
                "source_urls": [LANDING_PAGE, _source_url()],
                "notes": (
                    "Deterministic aggregation of the sole TF_SOC_POP_STRUCT_2025.txt member of the captured ZIP. "
                    "Sum integer MS_POPULATION (column U) over nationality and marital status, and over ages 0-17, 18-64, 65+ by sex; "
                    "also retain each commune's all-age/all-sex total. Reference date: 1 January 2025. "
                    "All 565 publisher CD_REFNIS codes exactly equal the crosswalk target_nis set; the ZIP already uses NIS 2025, so no code translation or merger aggregation is applied. "
                    "Names follow the fiscal commune package; original Dutch/French publisher names are retained. "
                    "source_rows are inclusive text line ranges separated by semicolons (header line 1), pointing to column U in source_member; source_sha256 pins the ZIP. "
                    "All 18 NUTS1 x sex x age-band sums exactly match the existing NUTS1 extract: zero differences. "
                    "Regional totals: BE1 1255795, BE2 6864766, BE3 3704990; national total 11825551. "
                    "R2 location declared for session upload; this lane does not upload raw artifacts."
                ),
            },
        },
        "source_capture_reference": capture,
    }
    return {
        CSV_PATH: content,
        MANIFEST_PATH: _yaml_bytes(manifest),
        SOURCE_PACKAGE_PATH: _yaml_bytes(_package_payload(rows)),
    }


def main() -> None:
    for path, content in render_outputs().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(f"Wrote {path.relative_to(REPO_ROOT)} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
