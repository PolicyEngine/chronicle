#!/usr/bin/env python3
"""Generate selectors for every published USD annual Euro/ECU exchange rate.

The immutable JSON-stat response is read directly by Chronicle's full-row parser.
This generator writes metadata and selectors only; it never transforms values.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[2]
DATA_DIR = REPO_ROOT / "db/data/eurostat/ert_bil_eur_a_usd"
FILENAME = "ert_bil_eur_a_USD.json"
PACKAGE_ID = "eurostat-ert-bil-eur-a-usd"
SHA256 = "3c96ca57c15266d07e1976d90ba806a5bb90ab46a503b6311df3aaa9f5ba66c7"
SOURCE_PAGE = (
    "https://ec.europa.eu/eurostat/databrowser/view/ert_bil_eur_a/default/table?lang=en"
)
SOURCE_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
    "ert_bil_eur_a?currency=USD&statinfo=AVG&format=JSON&lang=EN"
)
SOURCE_TABLE = (
    "Eurostat ert_bil_eur_a Euro/ECU exchange rates - annual data, USD average"
)
NOTES = (
    "Published annual average in US dollars per one euro/ECU: source unit NAC "
    "(National currency), currency USD, statinfo AVG. Eurostat publishes the "
    "modern euro series from ECB reference rates; the historical Euro/ECU series "
    "before euro introduction is retained as published. Values are neither "
    "inverted nor rescaled. Each selector reads one published value, not a "
    "Chronicle-computed annual mean. The currency-market statistical scope and "
    "institutional_sector entity are harness representations of a market rate; "
    "the source has no geography or institutional-sector dimension."
)


class _NoAliasesDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _dump(payload: dict) -> str:
    return yaml.dump(
        payload,
        Dumper=_NoAliasesDumper,
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )


def generate() -> dict[Path, str]:
    """Return deterministic manifest and package text from the pinned capture."""
    content = (DATA_DIR / FILENAME).read_bytes()
    if len(content) != 4488 or hashlib.sha256(content).hexdigest() != SHA256:
        raise ValueError("Source capture does not match the immutable size/SHA-256 pin")
    data = json.loads(content)
    if data["id"] != ["freq", "statinfo", "unit", "currency", "time"]:
        raise ValueError("Unexpected JSON-stat dimension order")
    if data["size"] != [1, 1, 1, 1, 55]:
        raise ValueError("Unexpected JSON-stat cube shape")
    fixed = {"freq": "A", "statinfo": "AVG", "unit": "NAC", "currency": "USD"}
    for dimension, code in fixed.items():
        if data["dimension"][dimension]["category"]["index"] != {code: 0}:
            raise ValueError(f"Unexpected {dimension} category")
    year_positions = sorted(
        data["dimension"]["time"]["category"]["index"].items(),
        key=lambda item: item[1],
    )
    record_sets = []
    for year, source_index in year_positions:
        if data["value"].get(str(source_index)) is None:
            raise ValueError(f"Missing published value for {year}")
        family = f"eurostat.ert_bil_eur_a.cy{year}.usd_average"
        coordinates = {**fixed, "time": year}
        record_sets.append(
            {
                "record_set_id": family,
                "provenance_class": "administrative",
                "assertion": "observation",
                "record_set_spec_id": "eurostat.ert_bil_eur_a.usd_average.v1",
                "source_record_id_prefix": family,
                "sheet_name": "ert_bil_eur_a",
                "period_type": "calendar_year",
                "period": int(year),
                "geography_id": "eurostat:ert_bil_eur_a:USD",
                "geography_level": "statistical_scope",
                "geography_name": "Euro/ECU exchange rate against the US dollar",
                "geography_vintage": "not_applicable",
                "entity": "institutional_sector",
                "entity_role": "currency_market",
                "domain": "exchange_rates",
                "groupby_dimension": "currency",
                "shared_filters": coordinates,
                "shared_constraints": [
                    {
                        "variable": dimension,
                        "operator": "==",
                        "value": code,
                        "label": data["dimension"][dimension]["label"],
                    }
                    for dimension, code in coordinates.items()
                ],
                "rows": [
                    {
                        "value_id": "USD",
                        "label": "US dollar",
                        "ordinal": 0,
                        "row_number": source_index + 2,
                        "expected_row_header_column": "D",
                        "expected_row_header": "USD",
                        "guard_cells": [
                            {
                                "column": column,
                                "expected_value": coordinates[dimension],
                                "label": f"Eurostat {dimension} dimension",
                            }
                            for column, dimension in zip(
                                ("A", "B", "C", "D", "E"),
                                ("freq", "statinfo", "unit", "currency", "time"),
                                strict=True,
                            )
                        ],
                    }
                ],
                "measures": [
                    {
                        "measure_id": "annual_average_exchange_rate",
                        "label": "Annual average US dollars per euro/ECU",
                        "ordinal": 0,
                        "column": "F",
                        "source_column_id": "value",
                        "expected_column_header_row": 1,
                        "expected_column_header": "value",
                        "concept": (
                            "eurostat.ert_bil_eur_a.annual_average_exchange_rate"
                        ),
                        "source_concept": "eurostat.ert_bil_eur_a.value",
                        "concept_relation": "source_label",
                        "concept_authority": "eurostat",
                        "concept_evidence_url": SOURCE_PAGE,
                        "concept_evidence_notes": (
                            f"{NOTES} Exact JSON locator: value['{source_index}']; "
                            f"dimensions freq=A, statinfo=AVG, unit=NAC, "
                            f"currency=USD, time={year}; parsed sheet ert_bil_eur_a, "
                            f"row {source_index + 2}, column F."
                        ),
                        "unit": "usd_per_eur",
                        "aggregation": "mean",
                        "value_scale": 1,
                        "expected_cell_type": "number",
                    }
                ],
            }
        )
    package = {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": "Eurostat annual average USD per EUR/ECU exchange rates, 1971-2025",
        "dimension_labels": {
            dimension: data["dimension"][dimension]["label"] for dimension in data["id"]
        },
        "dimension_value_labels": {
            dimension: data["dimension"][dimension]["category"]["label"]
            for dimension in data["id"]
        },
        "artifact": {
            "source_name": "eurostat",
            "source_table": SOURCE_TABLE,
            "resource_package": "db",
            "resource_directory": "data/eurostat/ert_bil_eur_a_usd",
            "manifest": "manifest.yaml",
            "vintage": "eurostat_ert_bil_eur_a_usd_updated_2026_07_08",
            "extracted_at": "2026-10-23",
            "extraction_method": (
                "Eurostat dissemination API JSON-stat 2.0 full-cube row parse; "
                "one selector per populated value, preserving source_index and "
                "all five source dimensions without transforming values"
            ),
            "parser": "json_stat_2_full_rows",
            "artifact_year": 2026,
            "sheet_name": "ert_bil_eur_a",
        },
        "record_sets": record_sets,
    }
    key = f"raw/eurostat/{PACKAGE_ID}/2026/{SHA256}/{FILENAME}"
    manifest = {
        "source_id": "eurostat",
        "package_id": PACKAGE_ID,
        "dataset": "ert_bil_eur_a",
        "source_name": "Eurostat ert_bil_eur_a annual USD exchange rates",
        "publisher": "Eurostat",
        "source_page": SOURCE_PAGE,
        "files": {
            2026: {
                "filename": FILENAME,
                "source_url": SOURCE_URL,
                "source_table": SOURCE_TABLE,
                "sha256": SHA256,
                "size_bytes": len(content),
                "retrieved_at": "2026-10-23",
                "updated": data["updated"],
                "license": "CC BY 4.0; Eurostat source acknowledgement required",
                "storage": {
                    "r2": {
                        "provider": "r2",
                        "bucket": "ledger-raw",
                        "key": key,
                        "uri": f"r2://ledger-raw/{key}",
                    }
                },
                "notes": (
                    "Verbatim publisher JSON-stat response, registered from the staged "
                    "capture using chronicle fetch-artifact. R2 location is declared "
                    "only; upload is pending Belgium session review. Reuse under "
                    "Eurostat's CC BY 4.0 policy with source acknowledgement. "
                    "Different bytes at the mutable API URL require a new vintage. "
                    + NOTES
                ),
            }
        },
    }
    header = "# Generated by packages/eurostat/ert_bil_eur_a_usd/build_package.py.\n"
    return {
        DATA_DIR / "manifest.yaml": header + _dump(manifest),
        PACKAGE_DIR / "source_package.yaml": header + _dump(package),
    }


def main() -> None:
    for path, text in generate().items():
        path.write_text(text, encoding="utf-8")
    print("Generated manifest and selectors for 55 published annual exchange rates.")


if __name__ == "__main__":
    main()
