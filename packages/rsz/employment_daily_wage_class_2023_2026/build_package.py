#!/usr/bin/env python3
"""Select RSZ publisher cells; normalize display representation, never aggregate facts."""

from __future__ import annotations

from collections import defaultdict
import calendar
import csv
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parents[2]
sys.path.insert(0, str(ROOT))
from chronicle.epoch import schema_id  # noqa: E402

PACKAGE_ID = "rsz-employment-daily-wage-class-2023-2026"
DATA = ROOT / "db/data/rsz/employment_daily_wage_class_2023_2026"
CSV_NAME = "employment_daily_wage_class.csv"
CAPTURED_AT = "2026-10-24T01:05:27Z"
# T7 prints "Man-homme"/"Vrouw-femme" through 2025Q3 and T17 always prints the
# capitalized forms; one value per sex keeps a series whole. Locators keep the print.
SEX_VALUES = {"man-homme": "Man-Homme", "vrouw-femme": "Vrouw-Femme"}
LANDING = "https://www.rsz.be/stats/arbeidsmarktanalyse-gedetailleerde-kwartaalgegevens"
OLD = "rsz-arbeidsmarktanalyse-per-kwartaal-2023-2024.xlsx"
NEW = "rsz-arbeidsmarktanalyse-per-kwartaal-2024-2026.xlsx"
BASE = "https://www.rsz.be/file/6103c41969844d308979992d7f84d51e59927e1e/"
CAPTURES = {
    OLD: (
        "7338f7aafb61e6469b53b917fb07b3d2017f17b8a457fb025ebc78bac355cce6",
        BASE
        + "e99a2c6552443e5bcb6d91bbf13bd59186d0318d/analyse-du-marche-du-travail-trimestrielle-arbeidsmarktanalyse-per-kwartaal-2023-2024.xlsx",
    ),
    NEW: (
        "35e43c50ba0f31038d6e46965404b9d828855a77151828795738ff048f646bec",
        BASE
        + "3317e5e3f67597073d8a13e89ec258298ba42e48/analyse-du-marche-du-travail-trimestrielle-arbeidsmarktanalyse-per-kwartaal-2024-2026.xlsx",
    ),
    "rsz-gedetailleerde-kwartaalgegevens.html": (
        "aaf7d6a870f40d8942f9fca7f9d022c26a6fe12a7e9feec8a515db064984bae8",
        LANDING,
    ),
    "rsz-gemeenschappelijke-criteria.html": (
        "b1f9df57fcd06e5091ed34d642ddb91a4c79b3d86f1d50cbaf68fc3e41b54c91",
        "https://www.rsz.be/gemeenschappelijke-criteria",
    ),
    "rsz-gemeenschappelijke-variabelen.html": (
        "e008e4a37f1686b8ce8c5bd22b575e3953b76dbfb701e7490f2ce6ec099f0428",
        "https://www.rsz.be/gemeenschappelijke-variabelen",
    ),
    "rsz-open-data-data-governance-act.html": (
        "956cb55a26adbdca779ed153a8cb8290bb2dea3e2b643380cc485fc5d554ab6e",
        "https://www.rsz.be/open-data-data-governance-act",
    ),
}
DIMENSIONS = {
    "rsz.daily_wage_class": "Dagloonklasse / Classe salaire journalier (EUR/day)",
    "rsz.age_class": "Leeftijdsklasse / Tranche d'âge",
    "rsz.sex": "Geslacht / Sexe",
    "rsz.worker_status": "Statuut / Statut",
    "rsz.nace2025_activity": "Hoofdactiviteit van de werkgever / Activité principal de l'employeur (NACE 2025)",
}
HEADERS = [
    "row_id",
    "quarter",
    *DIMENSIONS,
    "jobs",
    "employed_workers",
    "fte",
    "source_locator",
]
METRICS = [
    ("jobs", "Arbeidsplaatsen / Postes de travail", "count", "person"),
    (
        "employed_workers",
        "Tewerkgestelde werknemers / Travailleurs occupés",
        "count",
        "person",
    ),
    ("fte", "VTE / ETP", "fte", "person"),
]


class LiteralDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


class CompactRow(dict):
    """Keep complete descriptive labels without repeated block indentation."""


LiteralDumper.add_representer(
    CompactRow,
    lambda dumper, value: dumper.represent_mapping(
        "tag:yaml.org,2002:map", value, flow_style=True
    ),
)


def yaml_text(value):
    return yaml.dump(
        value, Dumper=LiteralDumper, sort_keys=False, allow_unicode=True, width=4096
    )


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(source: Path):
    """Copy only pinned bytes from the supplied read-only source directory."""
    DATA.mkdir(parents=True, exist_ok=True)
    for name, (sha, _) in CAPTURES.items():
        path = source / name
        if digest(path) != sha:
            raise ValueError(f"Capture checksum mismatch: {name}")
        shutil.copyfile(path, DATA / name)
    for name in ("CAPTURED_AT.txt", "SHA256SUMS.txt"):
        shutil.copyfile(source / name, DATA / name)


def displayed(cell):
    """Use the positive numeric format section; literal zero dashes remain zero."""
    if isinstance(cell.value, bool) or not isinstance(cell.value, (int, float)):
        raise ValueError(f"Non-numeric {cell.coordinate}: {cell.value!r}")
    fmt = cell.number_format.split(";")[0]
    fmt = re.sub(r'"[^"]*"|_.|\*.', "", fmt)
    match = re.search(r"[0#][0#,]*(?:\.([0#]+))?", fmt)
    if not match:
        raise ValueError(f"Unsupported display format {cell.number_format!r}")
    places = len(match.group(1) or "")
    return format(
        Decimal(str(cell.value)).quantize(
            Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP
        ),
        "f",
    )


def extract():
    rows = []
    value_labels = defaultdict(dict)
    variants = defaultdict(set)
    for name in (OLD, NEW):
        if digest(DATA / name) != CAPTURES[name][0]:
            raise ValueError(f"Workbook checksum mismatch: {name}")
        values = load_workbook(DATA / name, read_only=True, data_only=True)
        formulas = load_workbook(DATA / name, read_only=True, data_only=False)
        try:
            for sheet in ("T17",) if name == OLD else ("T17", "T7"):
                width, start, first_measure = (
                    (7, 2, 4) if sheet == "T17" else (10, 3, 7)
                )
                data_rows = values[sheet].iter_rows(min_row=start, max_col=width)
                formula_rows = formulas[sheet].iter_rows(min_row=start, max_col=width)
                for cells, expressions in zip(data_rows, formula_rows):
                    quarter = cells[0].value
                    if quarter is None:
                        continue
                    if str(quarter).startswith("Totaal"):
                        if not all(
                            c.data_type == "f" and c.value.startswith("=SUBTOTAL(")
                            for c in expressions[first_measure:]
                        ):
                            raise ValueError(
                                f"Typed total requires review: {name} {sheet} {cells[0].row}"
                            )
                        continue
                    if not isinstance(quarter, int):
                        raise ValueError(f"Unknown quarter {quarter!r}")
                    if name == OLD and quarter // 10 != 2023:
                        continue
                    dims = {}
                    if sheet == "T17":
                        wage, age, sex = (c.value for c in cells[1:4])
                        dims["rsz.age_class"] = str(age)
                    else:
                        status, sex, activity, nl, fr, wage = (
                            c.value for c in cells[1:7]
                        )
                        dims["rsz.worker_status"] = status
                        dims["rsz.nace2025_activity"] = activity
                        variants[activity].add((nl, fr))
                        value_labels["rsz.nace2025_activity"].setdefault(
                            activity, f"{nl} / {fr}"
                        )
                    dims["rsz.daily_wage_class"] = (
                        "Onbekend-Inconnu"
                        if wage.lower() == "onbekend-inconnu"
                        else wage
                    )
                    if sex.casefold() not in SEX_VALUES:
                        raise ValueError(f"Unexpected sex label {sex!r} in {sheet}")
                    dims["rsz.sex"] = SEX_VALUES[sex.casefold()]
                    for key, value in dims.items():
                        value_labels[key].setdefault(value, value)
                    native = [sheet, quarter, sorted(dims.items())]
                    row_id = hashlib.sha256(
                        json.dumps(native, ensure_ascii=False).encode()
                    ).hexdigest()[:24]
                    locator = {
                        "workbook": name,
                        "sheet": sheet,
                        "row": cells[0].row,
                        "printed_dimensions": {
                            c.coordinate: c.value for c in cells[:first_measure]
                        },
                        "cells": {
                            metric[0]: {
                                "cell": c.coordinate,
                                "cached_value": str(c.value),
                                "number_format": c.number_format,
                            }
                            for metric, c in zip(METRICS, cells[first_measure:])
                        },
                    }
                    row = dict.fromkeys(HEADERS, "")
                    row.update(
                        {
                            "row_id": row_id,
                            "quarter": f"{quarter // 10}Q{quarter % 10}",
                            **dims,
                        }
                    )
                    row.update(
                        {
                            metric[0]: displayed(c)
                            for metric, c in zip(METRICS, cells[first_measure:])
                        }
                    )
                    row["source_locator"] = json.dumps(
                        locator, ensure_ascii=False, separators=(",", ":")
                    )
                    rows.append(row)
        finally:
            values.close()
            formulas.close()
    if len({r["row_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate semantic source row")
    return (
        rows,
        dict(value_labels),
        {
            k: [list(x) for x in sorted(v)]
            for k, v in sorted(variants.items())
            if len(v) > 1
        },
    )


def constraint(key, value):
    return {"variable": key, "operator": "==", "value": value}


def package_spec(rows, value_labels):
    groups = defaultdict(list)
    for line, row in enumerate(rows, 2):
        locator = json.loads(row["source_locator"])
        group = (
            locator["sheet"],
            row["quarter"],
            row["rsz.daily_wage_class"],
            row["rsz.sex"],
            row["rsz.worker_status"],
        )
        groups[group].append((line, row))
    records = []
    for group, members in groups.items():
        sheet, quarter, wage, sex, status = group
        axis = "rsz.age_class" if sheet == "T17" else "rsz.nace2025_activity"
        shared = {"rsz.daily_wage_class": wage, "rsz.sex": sex}
        if status:
            shared["rsz.worker_status"] = status
        native = hashlib.sha256(
            json.dumps(group, ensure_ascii=False).encode()
        ).hexdigest()[:16]
        prefix = f"rsz.{sheet.lower()}.{quarter}.{native}"
        yaml_rows = [
            CompactRow(
                {
                    "value_id": r[axis],
                    "label": value_labels[axis][r[axis]],
                    "ordinal": ordinal,
                    "row_number": line,
                    "expected_row_header_column": "A",
                    "expected_row_header": r["row_id"],
                    "filters": {axis: r[axis]},
                    "constraints": [constraint(axis, r[axis])],
                }
            )
            for ordinal, (line, r) in enumerate(members)
        ]
        year, q = int(quarter[:4]), int(quarter[-1])
        month = q * 3
        end = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
        for metric, label, unit, entity in METRICS:
            full_quarter = metric == "fte"
            records.append(
                {
                    "record_set_id": prefix + "." + metric,
                    "record_set_spec_id": f"rsz.{sheet.lower()}.daily_wage_class.v1",
                    "source_record_id_prefix": prefix,
                    "provenance_class": "administrative",
                    "assertion": "observation",
                    "sheet_name": "employment_daily_wage_class",
                    "period_type": "quarter",
                    "period": quarter[:4] + "-" + quarter[4:],
                    "period_coverage": {
                        "start_date": f"{year}-{month - 2:02d}-01"
                        if full_quarter
                        else end,
                        "end_date": end,
                        "basis": "calendar",
                        "source_period_label": str(year * 10 + q),
                        "notes": (
                            "Quarter work volume (VTE / ETP)."
                            if full_quarter
                            else "Quarter-end stock, on the last day of the quarter."
                        )
                        + " RSZ-registered employment includes inbound cross-border workers; excludes posted workers and self-employed. "
                        + (
                            "T7: 2024 retropolated by publisher to NACE 2025."
                            if sheet == "T7"
                            else "T17: 2023 from archive, 2024 onward from newer workbook."
                        ),
                    },
                    "geography_id": "BE",
                    "geography_level": "country",
                    "geography_name": "Belgium",
                    "geography_vintage": "current",
                    "entity": entity,
                    "entity_role": {
                        "jobs": "employee_job",
                        "employed_workers": "employee",
                        "fte": "full_time_equivalent_employee",
                    }[metric],
                    "domain": "employment",
                    "groupby_dimension": axis,
                    "shared_filters": shared,
                    "shared_constraints": [constraint(k, v) for k, v in shared.items()],
                    "rows": yaml_rows,
                    "measures": [
                        {
                            "measure_id": metric,
                            "label": label,
                            "ordinal": 0,
                            "column": get_column_letter(HEADERS.index(metric) + 1),
                            "source_column_id": metric,
                            "expected_column_header_row": 1,
                            "expected_column_header": metric,
                            "concept": "rsz." + metric,
                            "source_concept": "rsz." + metric,
                            "concept_relation": "source_label",
                            "concept_authority": "RSZ/ONSS, Directie Statistiek",
                            "concept_evidence_url": "https://www.rsz.be/gemeenschappelijke-variabelen",
                            "concept_evidence_notes": "One published workbook cell at its displayed precision; exact workbook, sheet, cell, cached value and number format in source_locator. No aggregation, scaling or alignment.",
                            "unit": unit,
                            "aggregation": "sum",
                            "expected_cell_type": "number",
                        }
                    ],
                }
            )
    return {
        "schema_version": schema_id("source_package"),
        "package_id": PACKAGE_ID,
        "label": "RSZ/ONSS employment by daily wage class, T17 2023Q1–2026Q1 and T7 2024Q1–2026Q1",
        "dimension_labels": DIMENSIONS,
        "dimension_value_labels": value_labels,
        "artifact": {
            "source_name": "rsz_employment_daily_wage_class",
            "source_table": "RSZ T17 daily wage, age and sex; T7 NACE 2025, daily wage, sex and status",
            "resource_package": "db",
            "resource_directory": "data/rsz/employment_daily_wage_class_2023_2026",
            "manifest": "manifest.yaml",
            "vintage": "rsz_quarterly_updated_2026_08_26",
            "extracted_at": "2026-10-24",
            "extraction_method": "Deterministic representation-only workbook cell extract; all selected data cells, printed labels, cached values, number formats and exact workbook/sheet/cell locators preserved. Excel SUBTOTAL formulas excluded.",
            "parser": "delimited_text_full_rows",
            "artifact_year": 2026,
            "sheet_name": "employment_daily_wage_class",
        },
        "record_sets": records,
    }


def storage(name, sha):
    key = f"raw/belgium/{PACKAGE_ID}/2026/{sha}/{name}"
    return {
        "r2": {
            "provider": "r2",
            "bucket": "ledger-raw",
            "key": key,
            "uri": "r2://ledger-raw/" + key,
        }
    }


def main():
    if len(sys.argv) > 1:
        stage(Path(sys.argv[1]))
    rows, labels, variants = extract()
    with (DATA / CSV_NAME).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    spec = package_spec(rows, labels)
    (PACKAGE_DIR / "source_package.yaml").write_text(yaml_text(spec), encoding="utf-8")
    (PACKAGE_DIR / "nace_label_variants.json").write_text(
        json.dumps(variants, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    files = {}
    for key, name, url in [
        (2026, CSV_NAME, LANDING),
        *((name, name, url) for name, (_, url) in CAPTURES.items()),
    ]:
        path = DATA / name
        sha = digest(path)
        files[key] = {
            "filename": name,
            "source_url": url,
            "sha256": sha,
            "size_bytes": path.stat().st_size,
            "retrieved_at": CAPTURED_AT,
            "storage": storage(name, sha),
            "notes": "Uploaded to R2 ledger-raw and verified by SHA-256 readback on 2026-10-24. "
            + (
                "Representation-only cell extract; publisher captures below."
                if name == CSV_NAME
                else "Verbatim publisher source capture; checksum verified against supplied SHA256SUMS.txt."
            ),
        }
    manifest = {
        "source_id": "belgium",
        "package_id": PACKAGE_ID,
        "source_name": "RSZ/ONSS quarterly labour market analysis",
        "publisher": "Rijksdienst voor Sociale Zekerheid / Office national de sécurité sociale, Directie Statistiek",
        "source_page": LANDING,
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "Source: RSZ/ONSS, Directie Statistiek, Arbeidsmarktanalyse: gedetailleerde kwartaalgegevens, updated 26/08/2026; CC BY 4.0. Chronicle selected cells and normalized display representation and documented labels.",
        "files": files,
    }
    (DATA / "manifest.yaml").write_text(yaml_text(manifest), encoding="utf-8")
    print(
        json.dumps(
            {
                "rows": len(rows),
                "facts": len(rows) * 3,
                "T7_facts": sum(
                    json.loads(r["source_locator"])["sheet"] == "T7" for r in rows
                )
                * 3,
                "yaml_bytes": (PACKAGE_DIR / "source_package.yaml").stat().st_size,
                "record_sets": len(spec["record_sets"]),
            }
        )
    )


if __name__ == "__main__":
    main()
