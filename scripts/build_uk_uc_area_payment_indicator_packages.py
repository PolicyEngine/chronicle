"""Author the chronicle#339 packages: UC households by area and Payment Indicator.

Reads the three Stat-Xplore responses the manifests pin under ``db/data`` (one per
series, months from January 2025 to the latest loaded, dimensions month, Payment
Indicator, [number of children,] area) and writes, nothing downloaded and no fact
built:

- ``dwp-uc-households-by-constituency-payment-indicator-...``
- ``dwp-uc-households-by-local-authority-payment-indicator-...``
- ``dwp-uc-households-by-constituency-children-payment-indicator-...``

They re-extract the all-claims series of 7 October 2026 with Payment Indicator as a
dimension, Yes and No, whose sum is the all-claims count. Every month, indicator
[and child band] is one record set whose rows are a contiguous block of areas, so
each row is written once and referenced by alias in the other record sets, and the
block's first and last rows guard its month, indicator and child band.

usage: build_uk_uc_area_payment_indicator_packages.py SUFFIX EXTRACTED_AT
  SUFFIX: the package id suffix naming the months, e.g. january-2025-may-2026
  EXTRACTED_AT: the extraction date, YYYY-MM-DD
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

SERIES = {
    # key: (directory stem, geography field uri, level, vintage, children?)
    "constituency": (
        "uc_households_by_constituency_payment_indicator",
        "str:valueset:UC_Households:V_F_UC_HOUSEHOLDS:PCON24:V_C_MASTERGEOG21_PARLC24_TO_REGION",
        "constituency",
        "pcon_2024",
        False,
    ),
    "local_authority": (
        "uc_households_by_local_authority_payment_indicator",
        "str:valueset:UC_Households:V_F_UC_HOUSEHOLDS:WARD_CODE:V_C_MASTERGEOG21_LA_TO_REGION",
        "local_authority",
        "lad_2023",
        False,
    ),
    "constituency_children": (
        "uc_households_by_constituency_children_payment_indicator",
        "str:valueset:UC_Households:V_F_UC_HOUSEHOLDS:PCON24:V_C_MASTERGEOG21_PARLC24_TO_REGION",
        "constituency",
        "pcon_2024",
        True,
    ),
}
DATE_FIELD = "str:field:UC_Households:F_UC_HH_DATE:DATE_NAME"
PAYMENT_FIELD = "str:field:UC_Households:V_F_UC_HOUSEHOLDS:HCPAYMENT"
CHILDREN_FIELD = "str:field:UC_Households:V_F_UC_HOUSEHOLDS:NUMBER_OF_CHILDREN"
PAYMENT = {"No": "no", "Yes": "yes"}
# The pre-April-2019 marker carries no households in these months and emits no fact.
CHILDREN_SKIPPED = "Not available prior to April 2019"
MONTHS = {
    name: number
    for number, name in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}


def yaml_scalar(value: object) -> str:
    """Write a scalar, list or mapping in YAML flow style (JSON strings are YAML)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {yaml_scalar(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(yaml_scalar(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text.lower()).strip("_")


def build(key: str, suffix: str, extracted_at: str) -> int:
    stem, geography_uri, level, vintage, by_children = SERIES[key]
    directory = f"dwp/{stem}_{suffix.replace('-', '_')}"
    package_id = "dwp-" + stem.replace("_", "-") + f"-{suffix}"
    path = ROOT / "db/data" / directory / f"{stem}_{suffix.replace('-', '_')}.json"
    data = json.loads(path.read_bytes().decode("utf-8"))
    fields = data["fields"]
    uris = [field["uri"] for field in fields]
    expected = (
        [DATE_FIELD, PAYMENT_FIELD]
        + ([CHILDREN_FIELD] if by_children else [])
        + [geography_uri]
    )
    assert uris == expected, uris
    # Columns of the unpivoted rows: measure, value, then label and uri per field.
    columns = ["measure", "value"]
    for field in fields:
        key_name = field["label"]
        columns += [key_name, key_name + "_uri"]
    letter = {name: column_letter(i) for i, name in enumerate(columns)}
    month_items = fields[0]["items"]
    payment_items = fields[1]["items"]
    assert [item["labels"][0] for item in payment_items] == ["No", "Yes"]
    child_items = fields[2]["items"] if by_children else [None]
    geo_items = fields[-1]["items"]
    areas = [
        (item["uris"][0].rsplit(":", 1)[1], item["labels"][0]) for item in geo_items
    ]
    assert areas[-1] == ("ZZXXXXXXX", "Unknown"), areas[-1]
    block = len(geo_items)
    month_col = letter[fields[0]["label"]]
    payment_col = letter[fields[1]["label"]]
    child_col = letter[fields[2]["label"]] if by_children else None
    geo_header_col = letter[fields[-1]["label"] + "_uri"]

    templates: dict[str, dict] = {}
    record_sets = []
    record_rows: list[list] = []
    row_number = 2  # virtual table: header on row 1
    for month in month_items:
        month_label = month["labels"][0]
        name, year = month_label.split()
        period = f"{year}-{MONTHS[name]:02d}"
        for payment in payment_items:
            payment_label = payment["labels"][0]
            for child in child_items:
                child_label = child["labels"][0] if child else None
                first_row = row_number
                last_row = row_number + block - 1
                row_number += block
                if child_label == CHILDREN_SKIPPED:
                    continue
                rows = []
                for offset, (code, name_) in enumerate(areas[:-1]):
                    if code not in templates:
                        templates[code] = {
                            "value_id": code.lower(),
                            "label": name_,
                            "ordinal": offset,
                            "row_number": first_row + offset,
                            "expected_row_header_column": geo_header_col,
                            "expected_row_header": (
                                geography_uri.replace("str:valueset:", "str:value:")
                                + f":{code}"
                            ),
                            "geography_id": code,
                            "geography_level": level,
                            "geography_name": name_,
                            "geography_vintage": vintage,
                            "table_record_kind": "detail",
                        }
                    rows.append([code, first_row + offset, None])
                guards = [
                    {
                        "column": month_col,
                        "row": first_row,
                        "expected_value": month_label,
                        "label": "month",
                    },
                    {
                        "column": month_col,
                        "row": last_row,
                        "expected_value": month_label,
                        "label": "month",
                    },
                    {
                        "column": payment_col,
                        "row": first_row,
                        "expected_value": payment_label,
                        "label": "Payment Indicator",
                    },
                    {
                        "column": payment_col,
                        "row": last_row,
                        "expected_value": payment_label,
                        "label": "Payment Indicator",
                    },
                ]
                if child_label:
                    guards += [
                        {
                            "column": child_col,
                            "row": first_row,
                            "expected_value": child_label,
                            "label": "Number of Children",
                        },
                        {
                            "column": child_col,
                            "row": last_row,
                            "expected_value": child_label,
                            "label": "Number of Children",
                        },
                    ]
                # The block's first row carries the guards for both ends of the
                # block; its last row is the 'Unknown' area, which emits no fact.
                rows[0][2] = guards
                shared_filters = {"payment_indicator": payment_label}
                shared_constraints = [
                    {
                        "variable": "payment_indicator",
                        "operator": "==",
                        "value": payment_label,
                        "label": "Payment Indicator",
                    }
                ]
                record_set_id = (
                    f"dwp.statx.{stem}.{period}.payment_{PAYMENT[payment_label]}"
                    + (f".children_{slug(child_label)}" if child_label else "")
                )
                if child_label:
                    shared_filters = {
                        "number_of_children": child_label,
                        **shared_filters,
                    }
                    shared_constraints.insert(
                        0,
                        {
                            "variable": "number_of_children",
                            "operator": "==",
                            "value": child_label,
                            "label": "Number of Children",
                        },
                    )
                record_sets.append(
                    {
                        "record_set_id": record_set_id,
                        "provenance_class": "administrative",
                        "record_set_spec_id": f"{record_set_id}.v1",
                        "source_record_id_prefix": record_set_id,
                        "sheet_name": "api_response",
                        "period_type": "month",
                        "period": period,
                        "geography_id": "K03000001",
                        "geography_level": "country",
                        "geography_name": "Great Britain",
                        "geography_vintage": "current",
                        "entity": "household",
                        "entity_role": "uc_household",
                        "domain": "universal_credit",
                        "groupby_dimension": "dwp.uc_number_of_children"
                        if by_children
                        else "geography",
                        "shared_filters": shared_filters,
                        "shared_constraints": shared_constraints,
                        "measures": [
                            {
                                "measure_id": (
                                    "universal_credit_households_by_children"
                                    if by_children
                                    else "universal_credit_households"
                                ),
                                "label": "Households on Universal Credit",
                                "ordinal": 0,
                                "column": "B",
                                "source_column_id": "value",
                                "concept": "dwp.uc_households",
                                "source_concept": "dwp.uc_households",
                                "concept_relation": "source_label",
                                "concept_authority": "dwp",
                                "concept_evidence_url": "https://stat-xplore.dwp.gov.uk/",
                                "concept_evidence_notes": (
                                    f"Publisher Households on Universal Credit cube with Payment "
                                    f"Indicator, extracted {extracted_at}. Payment Indicator 'Yes' is a "
                                    "household with a calculated award paid in the month, 'No' a nil "
                                    "award; their sum is the all-claims count. Statistical disclosure "
                                    "control may prevent additivity."
                                ),
                                "unit": "count",
                                "aggregation": "sum",
                                "expected_cell_type": "number",
                                "expected_column_header_row": 1,
                                "expected_column_header": "value",
                            }
                        ],
                    }
                )
                record_rows.append(rows)
    assert row_number - 2 == len(month_items) * 2 * len(child_items) * block
    months = [m["labels"][0] for m in month_items]
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": package_id,
        "label": (
            "DWP Stat-Xplore UC households by "
            + (
                "constituency and number of children"
                if by_children
                else level.replace("_", " ")
            )
            + f" and Payment Indicator, {months[0]} to {months[-1]}"
        ),
        "dimension_labels": (
            {
                "number_of_children": "Number of Children",
                "dwp.uc_number_of_children": "Number of Children",
                "payment_indicator": "Payment Indicator",
            }
            if by_children
            else {"geography": "Geography", "payment_indicator": "Payment Indicator"}
        ),
        "artifact": {
            "source_name": "dwp",
            "source_table": (
                "DWP Stat-Xplore UC households by "
                + (
                    "constituency, number of children"
                    if by_children
                    else level.replace("_", " ")
                )
                + f" and Payment Indicator, {months[0]} to {months[-1]}"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{directory}",
            "manifest": "manifest.yaml",
            "vintage": f"stat_xplore_extracted_{extracted_at.replace('-', '_')}",
            "extracted_at": extracted_at,
            "extraction_method": (
                "Stat-Xplore Open Data API table response parsed and unpivoted to one row per "
                "cube cell; dimensions month, Payment Indicator, "
                + ("number of children, " if by_children else "")
                + "area; recodes total: false"
            ),
            "parser": "statxplore_table_json_rows",
            "artifact_year": 2025,
            "sheet_name": "api_response",
        },
    }
    out_dir = ROOT / "packages" / directory
    out_dir.mkdir(parents=True, exist_ok=True)
    header = HEADER.format(
        series=(
            "constituency and number of children"
            if by_children
            else level.replace("_", " ")
        ),
        extracted_at=extracted_at,
        first=months[0],
        last=months[-1],
    )
    header += textwrap.fill(
        "The query echoes inside the preserved response. "
        + (
            "The geography and child recodes are the October query's, and the "
            "'Unknown' area (ZZXXXXXXX) and the pre-April-2019 child marker emit no "
            "facts."
            if by_children
            else "The geography recode is the October query's, and the 'Unknown' "
            "area (ZZXXXXXXX) emits no facts."
        )
        + " Each cell is as published: DWP perturbs cells at source, so independently "
        "queried cubes and margins need not reconcile.",
        width=92,
        initial_indent="# ",
        subsequent_indent="# ",
    )
    header += "\n"
    head = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100)
    lines = [header + head + "record_sets:\n"]
    defined: set[str] = set()
    for record_set, rows in zip(record_sets, record_rows):
        block = yaml.safe_dump(
            [record_set], sort_keys=False, allow_unicode=True, width=100
        )
        lines.append(block)
        lines.append("  rows:\n")
        for code, number, guards in rows:
            anchor = "a_" + code.lower()
            if anchor not in defined:
                row = dict(templates[code], row_number=number)
                if guards:
                    row["guard_cells"] = guards
                lines.append(f"  - &{anchor} {yaml_scalar(row)}\n")
                defined.add(anchor)
                continue
            # Only the first area's anchor carries guards, and the first area opens
            # every block, so every alias of it overrides them.
            extra = {"row_number": number}
            if guards:
                extra["guard_cells"] = guards
            body = ", ".join(f"{k}: {yaml_scalar(v)}" for k, v in extra.items())
            lines.append(f"  - {{<<: *{anchor}, {body}}}\n")
    (out_dir / "source_package.yaml").write_text("".join(lines), encoding="utf-8")
    return sum(len(rows) for rows in record_rows)


HEADER = """\
# DWP Stat-Xplore 'Households on Universal Credit' by {series} and Payment Indicator,
# {first} to {last}, extracted {extracted_at}, for PolicyEngine/chronicle#339
# (microcosm#1198). It re-extracts the all-claims series of 7 October 2026 with Payment
# Indicator as a dimension: 'Yes' counts households with a calculated award paid in the
# month, 'No' those with a nil award, and their sum is the all-claims count the retired
# package carried (within disclosure control). DWP's 'household' is the UC unit of
# assessment.
"""


if __name__ == "__main__":
    suffix, extracted_at = sys.argv[1], sys.argv[2]
    for key in SERIES:
        print(key, build(key, suffix, extracted_at))
