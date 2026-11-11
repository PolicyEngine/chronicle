"""Author the chronicle#357 item 3 package: Move to UC households by legacy benefit.

Reads the Stat-Xplore response the manifest pins under ``db/data`` (database
``MtUC_Households``, households sent a managed migration notice, by 'Legacy
Benefit' and 'Move Status', each with DWP's own total, over every notice month)
and writes ``dwp-mtuc-households-legacy-benefit-move-status-july-2022-june-2026``,
nothing downloaded and no fact built.

The table is cumulative because DWP's background information advises taking a
statistic from the tabulation that carries it rather than summing finer cells,
each of which carries its own random error. A legacy-benefit row or move-status
column that is zero in every cell is not ported; any other published zero is.

usage: build_dwp_mtuc_households_package.py
"""

from __future__ import annotations

import copy
import json
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
NAME = "mtuc_households_legacy_benefit_move_status_july_2022_june_2026"
PACKAGE_ID = "dwp-" + NAME.replace("_", "-")
EXTRACTED_AT = "2026-10-15"
LEGACY_FIELD = "str:field:MtUC_Households:V_F_MtUC_Households:Legacy_Ben_Code"
STATUS_FIELD = "str:field:MtUC_Households:V_F_MtUC_Households:Claim_Status_Code"
MEASURE_LABEL = "Move to UC - Households"
RECORD_SET_ID = "dwp.statx.mtuc_households.legacy_benefit_move_status.2026-06"
BACKGROUND_URL = (
    "https://www.gov.uk/government/publications/"
    "move-to-universal-credit-statistics-background-information/"
    "move-to-universal-credit-statistics-background-information"
)
# Columns of the unpivoted rows: measure, value, then label and URI per field.
COLUMNS = {
    "measure": "A",
    "value": "B",
    "legacy": "C",
    "legacy_uri": "D",
    "status": "E",
    "status_uri": "F",
}
PERIOD = {
    "period_type": "month",
    "period": "2026-06",
    "period_coverage": {
        "start_date": "2022-07-01",
        "end_date": "2026-06-30",
        "basis": "calendar",
        "source_period_label": "Month Migration Notice Sent: Jul-22 to Jun-26",
        "notes": (
            "Cumulative: households sent a migration notice in any month from July 2022 "
            "to June 2026, the notice months Stat-Xplore held at extraction on 15 "
            "October 2026; period.value is the latest notice month. Each household "
            "is counted once, in the move status it held at DWP's extract, which DWP "
            "takes about a month before each release. It is the release DWP "
            "summarises in its Universal Credit quarterly statistics of 18 August 2026 "
            "(1.8 million households sent a notice to end June 2026, 87% claimed)."
        ),
    },
}

HEADER = """\
# DWP Stat-Xplore 'Households invited to Move to Universal Credit' (official statistics in
# development): households sent a managed migration notice, by combination of legacy
# benefits and move status, cumulative over the notice months July 2022 to June 2026,
# extracted 15 October 2026, for PolicyEngine/chronicle#357 item 3
# (PolicyEngine/microcosm#1095). policyengine-uk-data#534 draws its claim rates from this
# table ('MtUC Households 3').
#
# Move status, as DWP's background information defines it:
# - Claimed UC: a UC claim dated no earlier than the notice (or flagged in the Move to UC
#   system as made through managed migration) and made within one month after the deadline
#   or any extension, so a claim after the legacy award closed, inside that month, counts.
# - Did not claim UC - Legacy benefit closed: no such claim, and the legacy award ended.
# - In Progress: no claim yet, and the deadline (or extension) has not passed.
# Statuses are as at DWP's extract, so a later release can move a household from 'did not
# claim' to 'claimed', and DWP removes households later found out of scope; each release
# supersedes the last. From August 2026 DWP summarises the series inside its Universal Credit
# quarterly statistics (18 August 2026: 1.8 million households sent a notice to end June 2026,
# 87% claimed), with the tables on Stat-Xplore only. Stat-Xplore serves only the current
# release, so the package names the extraction date; later extracts land beside it.
#
# Coverage: the areas of Great Britain where notices were sent. Stat-Xplore adds random
# error to every cell, so parts need not sum to DWP's totals; the totals are DWP's own
# (total: true) and sit in the .total record set.
{skipped}"""


def guard(column: str, row: int, value: str, label: str) -> dict:
    return {"column": column, "row": row, "expected_value": value, "label": label}


def build() -> int:
    path = ROOT / "db/data/dwp" / NAME / f"{NAME}.json"
    data = json.loads(path.read_bytes().decode("utf-8"))
    assert [field["uri"] for field in data["fields"]] == [LEGACY_FIELD, STATUS_FIELD]
    assert [m["label"] for m in data["measures"]] == [MEASURE_LABEL]
    legacy_items, status_items = (field["items"] for field in data["fields"])
    assert legacy_items[-1]["labels"] == ["Total"] and "uris" not in legacy_items[-1]
    assert status_items[-1]["labels"] == ["Total"] and "uris" not in status_items[-1]
    values = next(iter(data["cubes"].values()))["values"]

    legacy_zero = [
        i
        for i in range(len(legacy_items) - 1)
        if not any(values[i][j] for j in range(len(status_items)))
    ]
    status_zero = [
        j
        for j in range(len(status_items) - 1)
        if not any(values[i][j] for i in range(len(legacy_items)))
    ]
    skipped = " and ".join(
        [f"the '{legacy_items[i]['labels'][0]}' row" for i in legacy_zero]
        + [f"the '{status_items[j]['labels'][0]}' status" for j in status_zero]
    )

    detail_rows, total_rows = [], []
    for i, legacy in enumerate(legacy_items):
        if i in legacy_zero:
            continue
        legacy_label = legacy["labels"][0]
        legacy_total = legacy_label == "Total"
        for j, status in enumerate(status_items):
            if j in status_zero:
                continue
            status_label = status["labels"][0]
            status_total = status_label == "Total"
            row = 2 + i * len(status_items) + j  # virtual table: header on row 1
            guards = [
                guard(COLUMNS["measure"], row, MEASURE_LABEL, "measure"),
                guard(COLUMNS["legacy"], row, legacy_label, "Legacy Benefit"),
                guard(COLUMNS["status"], row, status_label, "Move Status"),
            ]
            if not legacy_total:
                guards.append(
                    guard(
                        COLUMNS["legacy_uri"],
                        row,
                        legacy["uris"][0],
                        "Legacy Benefit URI",
                    )
                )
            if not status_total:
                guards.append(
                    guard(
                        COLUMNS["status_uri"], row, status["uris"][0], "Move Status URI"
                    )
                )
            filters = {
                "legacy_benefit": "all" if legacy_total else legacy_label,
                "move_status": "all" if status_total else status_label,
            }
            constraints = [
                {"variable": variable, "operator": "==", "value": value, "label": label}
                for variable, value, label, totalled in (
                    (
                        "legacy_benefit",
                        legacy_label,
                        "Legacy Benefit",
                        legacy_total,
                    ),
                    ("move_status", status_label, "Move Status", status_total),
                )
                if not totalled
            ]
            value_id = "__".join(
                "".join(ch if ch.isalnum() else "_" for ch in text.lower()).strip("_")
                for text in (
                    "all_households" if legacy_total else legacy_label,
                    "all_statuses" if status_total else status_label,
                )
            )
            record = {
                "value_id": value_id,
                "label": (
                    ("All households" if legacy_total else legacy_label)
                    + ", "
                    + ("all move statuses" if status_total else status_label)
                ),
                "row_number": row,
                "expected_row_header_column": (
                    COLUMNS["status"] if status_total else COLUMNS["status_uri"]
                ),
                "expected_row_header": "Total" if status_total else status["uris"][0],
                "table_record_kind": "total"
                if legacy_total or status_total
                else "detail",
                "filters": filters,
                "constraints": constraints,
                "guard_cells": guards,
            }
            (total_rows if legacy_total or status_total else detail_rows).append(record)

    measure = {
        "measure_id": "households_sent_migration_notice",
        "label": "Households sent a Move to UC migration notice",
        "ordinal": 0,
        "column": COLUMNS["value"],
        "source_column_id": "value",
        "expected_column_header_row": 1,
        "expected_column_header": "value",
        "concept": "dwp.mtuc_households_sent_migration_notice",
        "source_concept": "dwp.mtuc_households_sent_migration_notice",
        "concept_relation": "source_label",
        "concept_authority": "dwp",
        "concept_evidence_url": BACKGROUND_URL,
        "concept_evidence_notes": (
            "Official statistics in development. DWP Move to UC statistics (Stat-Xplore "
            "'Households invited to Move to Universal Credit', extracted 15 October 2026): "
            "households sent a managed migration notice from July 2022 to June 2026, "
            "Great Britain, by the legacy benefits the household received and its move "
            "status at DWP's extract. Claimed UC: a claim made within one month after the "
            "deadline or any extension, including after the legacy award closed. Did not "
            "claim: no such claim, legacy award ended. In Progress: deadline not yet "
            "passed. Each release supersedes the last; cells carry Stat-Xplore's random "
            "error."
        ),
        "unit": "count",
        "aggregation": "sum",
        "expected_cell_type": "number",
    }

    def record_set(suffix: str, rows: list[dict]) -> dict:
        record_set_id = RECORD_SET_ID + suffix
        for ordinal, row in enumerate(rows):
            row["ordinal"] = ordinal
        return {
            "record_set_id": record_set_id,
            "provenance_class": "administrative",
            "record_set_spec_id": f"{record_set_id}.v1",
            "source_record_id_prefix": record_set_id,
            "sheet_name": "api_response",
            **copy.deepcopy(PERIOD),
            "geography_id": "K03000001",
            "geography_level": "country",
            "geography_name": "Great Britain",
            "geography_vintage": "current",
            "entity": "household",
            "entity_role": "migration_notice_household",
            "domain": "universal_credit",
            "groupby_dimension": "dwp.mtuc_legacy_benefit_move_status",
            "rows": [
                {
                    key: row[key]
                    for key in (
                        "value_id",
                        "label",
                        "ordinal",
                        "row_number",
                        "expected_row_header_column",
                        "expected_row_header",
                        "table_record_kind",
                        "filters",
                        "constraints",
                        "guard_cells",
                    )
                }
                for row in rows
            ],
            "measures": [dict(measure)],
        }

    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": (
            "DWP Stat-Xplore: households sent a Move to UC migration notice by legacy "
            "benefit combination and move status, Great Britain, notices July 2022 to "
            "June 2026"
        ),
        "dimension_labels": {
            "dwp.mtuc_legacy_benefit_move_status": "Legacy benefit combination by move status",
            "legacy_benefit": "Legacy Benefit",
            "move_status": "Move Status",
        },
        "artifact": {
            "source_name": "dwp",
            "source_table": (
                "Households invited to Move to Universal Credit by Legacy Benefit and "
                "Move Status, notices July 2022 to June 2026"
            ),
            "resource_package": "db",
            "resource_directory": f"data/dwp/{NAME}",
            "manifest": "manifest.yaml",
            "vintage": f"stat_xplore_extracted_{EXTRACTED_AT.replace('-', '_')}",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": (
                "Stat-Xplore Open Data API table response parsed and unpivoted to one row "
                "per cube cell; database str:database:MtUC_Households; measure "
                "str:count:MtUC_Households:V_F_MtUC_Households; fields in response order: "
                f"{LEGACY_FIELD}; {STATUS_FIELD}; value sets C_MtUC_Legacy_Benefit_Claimed, "
                "C_MtUC_Claim_Status; recode total: true on both; the notice-month field is "
                "not requested, so each cell covers every notice month"
            ),
            "parser": "statxplore_table_json_rows",
            "sheet_name": "api_response",
            "artifact_year": 2026,
        },
        "record_sets": [record_set("", detail_rows), record_set(".total", total_rows)],
    }
    out = ROOT / "packages/dwp" / NAME / "source_package.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    note = (
        textwrap.fill(
            f"Not ported, zero in every cell: {skipped}.",
            width=92,
            initial_indent="# ",
            subsequent_indent="# ",
        )
        + "\n"
        if skipped
        else ""
    )
    out.write_text(
        HEADER.format(skipped=note)
        + yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return len(detail_rows) + len(total_rows)


if __name__ == "__main__":
    print(PACKAGE_ID, build())
