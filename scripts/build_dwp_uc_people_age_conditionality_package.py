"""Author the PolicyEngine/chronicle#420 item 3 package: People on Universal Credit by
country, age and conditionality regime.

Run from the repository root:

    uv run python scripts/build_dwp_uc_people_age_conditionality_package.py

``--check`` compares the generated YAML with the committed file instead of writing.
The package is written from the Stat-Xplore response its manifest pins under
``db/data``, read with Chronicle's own Stat-Xplore parser, so every row number and
column below is one the package parser sees. Nothing is downloaded and no value is
computed; the response's field items are asserted, so a run against a different
response fails rather than drifting.

The response is the raw ``/table`` answer (query echoed) for the People on Universal
Credit database (UC_Monthly): month, residence-based country, age (single years 16 to
24, then DWP's bands) and conditionality regime, with DWP's totals on country, age and
regime. Its rows unpivot month-major in field order, so each month is one block of
country x age x regime cells, and each (month, country) a block of age x regime cells.
Every month gives two record sets: the detail cells, and the cells where age, regime or
both are DWP's 'Total'. Each row is written once as an anchor and every later month
references it, overriding its row number and guards.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import textwrap
from pathlib import Path

import yaml

from chronicle.sources.rows import source_rows_from_statxplore_table

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = "dwp/uc_people_country_age_conditionality_regime_april_2024_may_2026"
FILENAME = "people_on_uc_by_country_age_conditionality_regime_april_2024_may_2026.json"
PACKAGE_ID = "dwp-uc-people-country-age-conditionality-regime-april-2024-may-2026"
EXTRACTED_AT = "2026-11-06"
ISSUE = "PolicyEngine/chronicle#420"
SCRIPT = "scripts/build_dwp_uc_people_age_conditionality_package.py"
GROUPBY = "dwp.uc_people_country_age_conditionality_regime"
METADATA = "https://stat-xplore.dwp.gov.uk/webapi/metadata/UC_Monthly"

DB = "UC_Monthly"
COUNT = f"str:count:{DB}:V_F_UC_CASELOAD_FULL"
DATE_FIELD = f"str:field:{DB}:F_UC_DATE:DATE_NAME"
GEO_FIELD = f"str:field:{DB}:V_F_UC_CASELOAD_FULL:COA_CODE"
AGE_FIELD = f"str:field:{DB}:V_F_UC_CASELOAD_FULL:AGE_CODE"
REGIME_FIELD = f"str:field:{DB}:V_F_UC_CASELOAD_FULL:CCCONDITIONALITY_REGIME"
MEASURE_LABEL = "People on Universal Credit"

# Country items in request order, then DWP's total, which is Great Britain: the count
# DWP publishes, including people whose residence is unknown ('Unknown', which emits
# no fact).
COUNTRY_VALUESET = (
    f"str:value:{DB}:V_F_UC_CASELOAD_FULL:COA_CODE:V_C_MASTERGEOG21_COUNTRY_TO_GB"
)
COUNTRIES = (
    ("E92000001", "England"),
    ("W92000004", "Wales"),
    ("S92000003", "Scotland"),
)
UNKNOWN_AREA = "ZZXXXXXXX"
GREAT_BRITAIN = ("K03000001", "Great Britain")

SINGLE_AGE = f"str:value:{DB}:V_F_UC_CASELOAD_FULL:AGE_CODE:C_UC_SINGLE_AGE"
AGE_BAND = f"str:value:{DB}:V_F_UC_CASELOAD_FULL:AGE_CODE:C_UC_AGE_BAND"
# Age items in request order: (value URI, label, (lower, upper or None) or None). DWP:
# 'The over 70 age group contains people aged 71 to 90 inclusive only. Over 90 years is
# classified as missing/unknown'. 'Over 70' takes the open top band's lower bound,
# age >= 71, which Chronicle's Stat-Xplore age reader gives for the label (as '90 and
# over' gives age >= 90); 'Unknown/Missing' carries none.
AGES = (
    *((f"{SINGLE_AGE}:{age}", str(age), (age, age + 1)) for age in range(16, 25)),
    *(
        (f"{AGE_BAND}:{code}", f"{low}-{high}", (low, high + 1))
        for code, low, high in (
            (3, 25, 29),
            (4, 30, 34),
            (5, 35, 39),
            (6, 40, 44),
            (7, 45, 49),
            (8, 50, 54),
            (9, 55, 59),
            (10, 60, 64),
            (11, 65, 70),
        )
    ),
    (f"{AGE_BAND}:999", "Over 70", (71, None)),
    (f"{AGE_BAND}:9999", "Unknown/Missing", None),
)
REGIME_VALUE = f"str:value:{DB}:V_F_UC_CASELOAD_FULL:CCCONDITIONALITY_REGIME:C_UC_CONDITIONALITY_REGIME"
REGIMES = (
    ("AA", "Searching for work"),
    ("AB", "Working - with requirements"),
    ("BC", "No work requirements"),
    ("BD", "Working - no requirements"),
    ("DF", "Planning for work"),
    ("CE", "Preparing for work"),
    ("ZZ", "Unknown or missing regime"),
    ("NA", "Not available prior to April 2015"),
)
TOTAL = "Total"
MONTHS = {
    name: number
    for number, name in enumerate(
        (
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
        ),
        start=1,
    )
}
# Columns of the unpivoted rows: measure, value, then a label and a URI per field.
COLUMN = {
    "measure": "A",
    "value": "B",
    "month": "C",
    "geography_uri": "F",
    "geography": "E",
    "age": "G",
    "age_uri": "H",
    "regime": "I",
    "regime_uri": "J",
}
AGE_KEY = "age_bands_and_single_year"
REGIME_KEY = "conditionality_regime"
AGE_LABEL = "Age (bands and single year)"
REGIME_LABEL = "Conditionality Regime"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def yaml_scalar(value: object) -> str:
    """A scalar, list or mapping in YAML flow style (JSON strings are YAML)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {yaml_scalar(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(yaml_scalar(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def pinned() -> tuple[dict, bytes]:
    """The manifest's one file entry and its bytes, checked against the pinned digest."""
    data_dir = ROOT / "db/data" / DIRECTORY
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text(encoding="utf-8"))
    (entry,) = manifest["files"].values()
    assert entry["filename"] == FILENAME
    content = (data_dir / FILENAME).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    return entry, content


def check_response(data: dict) -> list[str]:
    """Assert the response is the query this package describes; return its months."""
    assert data["database"]["uri"] == f"str:database:{DB}"
    assert [measure["uri"] for measure in data["measures"]] == [COUNT]
    assert data["measures"][0]["label"] == MEASURE_LABEL
    fields = data["fields"]
    assert [field["uri"] for field in fields] == [
        DATE_FIELD,
        GEO_FIELD,
        AGE_FIELD,
        REGIME_FIELD,
    ]
    assert [field["label"] for field in fields] == [
        "Month",
        "National - Regional - LA - OAs",
        AGE_LABEL,
        REGIME_LABEL,
    ]
    months = [item["labels"][0] for item in fields[0]["items"]]
    for item in fields[0]["items"]:
        name, year = item["labels"][0].split()
        assert item["uris"] == [
            f"str:value:{DB}:F_UC_DATE:DATE_NAME:C_UC_DATE:{year}{MONTHS[name]:02d}"
        ]
    geo = [(item["labels"][0], item.get("uris")) for item in fields[1]["items"]]
    assert geo == [
        *((name, [f"{COUNTRY_VALUESET}:{code}"]) for code, name in COUNTRIES),
        ("Unknown", [f"{COUNTRY_VALUESET}:{UNKNOWN_AREA}"]),
        (TOTAL, None),
    ], geo
    ages = [(item["labels"][0], item.get("uris")) for item in fields[2]["items"]]
    assert ages == [(label, [uri]) for uri, label, _ in AGES] + [(TOTAL, None)], ages
    regimes = [(item["labels"][0], item.get("uris")) for item in fields[3]["items"]]
    assert regimes == [
        (label, [f"{REGIME_VALUE}:{code}"]) for code, label in REGIMES
    ] + [(TOTAL, None)], regimes
    cube = data["cubes"][COUNT]["values"]
    assert len(cube) == len(months)
    for by_month in cube:
        assert len(by_month) == len(geo)
        for by_geo in by_month:
            assert len(by_geo) == len(ages)
            assert all(len(by_age) == len(regimes) for by_age in by_geo)
    return months


def period(month_label: str) -> str:
    name, year = month_label.split()
    return f"{year}-{MONTHS[name]:02d}"


def build() -> str:
    entry, content = pinned()
    data = json.loads(content.decode("utf-8"))
    months = check_response(data)
    rows = source_rows_from_statxplore_table(content, None, sheet_name="api_response")
    geo_items = [*COUNTRIES, (UNKNOWN_AREA, "Unknown"), GREAT_BRITAIN]
    age_items = [*AGES, (None, TOTAL, None)]
    regime_items = [*((code, label) for code, label in REGIMES), (None, TOTAL)]
    block = len(geo_items) * len(age_items) * len(regime_items)
    assert len(rows) == len(months) * block

    # The parser's row r is the package table's row r + 1 (row 1 holds the headers).
    def row_at(m: int, g: int, a: int, r: int):
        index = ((m * len(geo_items) + g) * len(age_items) + a) * len(regime_items) + r
        return rows[index], index + 2

    # A series is one (country, age, regime) cell across the months; one that is zero
    # in every month carries nothing and is not ported.
    zero_series = set()
    for g, (code, _) in enumerate(geo_items):
        if code == UNKNOWN_AREA:
            continue
        for a in range(len(age_items)):
            for r in range(len(regime_items)):
                values = [
                    row_at(m, g, a, r)[0].values["value"] for m in range(len(months))
                ]
                assert all(isinstance(v, int) and v >= 0 for v in values), values
                if not any(values):
                    zero_series.add((g, a, r))

    templates: dict[str, dict] = {}
    record_sets: list[tuple[dict, list[tuple[str, int, int, list[dict]]]]] = []
    ported_zero_cells = 0
    for m, month_label in enumerate(months):
        detail: list[tuple[str, int, list[dict]]] = []
        totals: list[tuple[str, int, list[dict]]] = []
        month_rows: list[tuple[int, list[dict]]] = []
        for g, (geo_code, geo_name) in enumerate(geo_items):
            if geo_code == UNKNOWN_AREA:
                continue
            geo_rows: list[tuple[int, list[dict]]] = []
            for a, (age_uri, age_label, bounds) in enumerate(age_items):
                for r, (regime_code, regime_label) in enumerate(regime_items):
                    if (g, a, r) in zero_series:
                        continue
                    row, number = row_at(m, g, a, r)
                    values = row.values
                    assert values["measure"] == MEASURE_LABEL
                    assert values["month"] == month_label
                    assert values["national_regional_la_oas"] == (
                        TOTAL if geo_code == GREAT_BRITAIN[0] else geo_name
                    )
                    assert values[AGE_KEY] == age_label
                    assert values[REGIME_KEY] == regime_label
                    if values["value"] == 0:
                        ported_zero_cells += 1
                    age_value = "all" if age_uri is None else age_label
                    regime_value = "all" if regime_code is None else regime_label
                    value_id = "__".join(
                        (
                            geo_code.lower(),
                            "age_all" if age_uri is None else slug(age_label),
                            "regime_all" if regime_code is None else slug(regime_label),
                        )
                    )
                    if value_id not in templates:
                        constraints = []
                        if age_uri is not None:
                            constraints.append(
                                {
                                    "variable": AGE_KEY,
                                    "operator": "==",
                                    "value": age_label,
                                    "label": AGE_LABEL,
                                }
                            )
                            if bounds is not None:
                                low, high = bounds
                                constraints.append(
                                    {
                                        "variable": "age",
                                        "operator": ">=",
                                        "value": low,
                                        "unit": "years",
                                        "label": "Age lower bound",
                                    }
                                )
                                if high is not None:
                                    constraints.append(
                                        {
                                            "variable": "age",
                                            "operator": "<",
                                            "value": high,
                                            "unit": "years",
                                            "label": "Age upper bound",
                                        }
                                    )
                        if regime_code is not None:
                            constraints.append(
                                {
                                    "variable": REGIME_KEY,
                                    "operator": "==",
                                    "value": regime_label,
                                    "label": REGIME_LABEL,
                                }
                            )
                        template = {
                            "value_id": value_id,
                            "label": ", ".join(
                                (
                                    geo_name,
                                    "all ages" if age_uri is None else age_label,
                                    "all regimes"
                                    if regime_code is None
                                    else regime_label,
                                )
                            ),
                            "expected_row_header_column": (
                                COLUMN["regime"]
                                if regime_code is None
                                else COLUMN["regime_uri"]
                            ),
                            "expected_row_header": (
                                TOTAL
                                if regime_code is None
                                else f"{REGIME_VALUE}:{regime_code}"
                            ),
                            "geography_id": geo_code,
                            "geography_level": "country",
                            "geography_name": geo_name,
                            "geography_vintage": "current",
                            "table_record_kind": (
                                "detail"
                                if age_uri is not None and regime_code is not None
                                else "total"
                            ),
                            "filters": {AGE_KEY: age_value, REGIME_KEY: regime_value},
                        }
                        if constraints:
                            template["constraints"] = constraints
                        templates[value_id] = template
                    # Every row guards its age; its expected row header checks its regime.
                    guards = [
                        (
                            {
                                "column": COLUMN["age"],
                                "row": number,
                                "expected_value": TOTAL,
                                "label": "age total",
                            }
                            if age_uri is None
                            else {
                                "column": COLUMN["age_uri"],
                                "row": number,
                                "expected_value": age_uri,
                                "label": "age value URI",
                            }
                        )
                    ]
                    target = (
                        detail
                        if templates[value_id]["table_record_kind"] == "detail"
                        else totals
                    )
                    target.append((value_id, number, guards))
                    geo_rows.append((number, guards))
                    month_rows.append((number, guards))
            # The (month, country) block's first and last ported rows guard its country.
            for number, guards in (geo_rows[0], geo_rows[-1]):
                guards.append(
                    {
                        "column": COLUMN["geography"],
                        "row": number,
                        "expected_value": TOTAL,
                        "label": "geography total (Great Britain)",
                    }
                    if geo_code == GREAT_BRITAIN[0]
                    else {
                        "column": COLUMN["geography_uri"],
                        "row": number,
                        "expected_value": f"{COUNTRY_VALUESET}:{geo_code}",
                        "label": "geography value URI",
                    }
                )
        # The month block's first and last ported rows guard the month and the measure.
        for number, guards in (month_rows[0], month_rows[-1]):
            guards += [
                {
                    "column": COLUMN["month"],
                    "row": number,
                    "expected_value": month_label,
                    "label": "month",
                },
                {
                    "column": COLUMN["measure"],
                    "row": number,
                    "expected_value": MEASURE_LABEL,
                    "label": "measure",
                },
            ]
        for kind, members in (("detail", detail), ("total", totals)):
            record_set_id = (
                f"dwp.statx.uc_people.country_age_conditionality_regime.month"
                f"{period(month_label).replace('-', '_')}"
                + (".total" if kind == "total" else "")
            )
            record_sets.append(
                (
                    {
                        "record_set_id": record_set_id,
                        "provenance_class": "administrative",
                        "record_set_spec_id": f"{record_set_id}.v1",
                        "source_record_id_prefix": record_set_id,
                        "sheet_name": "api_response",
                        "period_type": "month",
                        "period": period(month_label),
                        "geography_id": GREAT_BRITAIN[0],
                        "geography_level": "country",
                        "geography_name": GREAT_BRITAIN[1],
                        "geography_vintage": "current",
                        "entity": "person",
                        "entity_role": "universal_credit_claimant",
                        "domain": "universal_credit",
                        "groupby_dimension": GROUPBY,
                        "assertion": "observation",
                    },
                    members,
                )
            )

    facts = sum(len(members) for _, members in record_sets)
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": (
            "DWP Stat-Xplore: People on Universal Credit by country, age and "
            f"conditionality regime, {months[0]} to {months[-1]}"
        ),
        "dimension_labels": {GROUPBY: "Country by age by conditionality regime"},
        "artifact": {
            "source_name": "dwp",
            "source_table": (
                "People on Universal Credit by country, age (bands and single year) and "
                f"conditionality regime, {months[0]} to {months[-1]}"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": f"stat_xplore_{EXTRACTED_AT.replace('-', '_')}",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": (
                "Stat-Xplore Open Data API table response parsed and unpivoted to one "
                f"row per cube cell; database str:database:{DB}; measure {COUNT}; fields "
                f"in response order: {DATE_FIELD}; {GEO_FIELD}; {AGE_FIELD}; "
                f"{REGIME_FIELD}; value sets: C_UC_DATE, "
                "V_C_MASTERGEOG21_COUNTRY_TO_GB, C_UC_SINGLE_AGE (16 to 24), C_UC_AGE_BAND "
                "(25-29 to 65-70, Over 70, Unknown/Missing), C_UC_CONDITIONALITY_REGIME; "
                f"months {months[0]} through {months[-1]}, inclusive; recode total: true "
                "on COA_CODE, AGE_CODE and CCCONDITIONALITY_REGIME, total: false on "
                "DATE_NAME."
            ),
            "parser": "statxplore_table_json_rows",
            "sheet_name": "api_response",
            "artifact_year": 2026,
        },
    }
    measure = {
        "measure_id": "people",
        "label": MEASURE_LABEL,
        "ordinal": 0,
        "column": COLUMN["value"],
        "source_column_id": "value",
        "expected_column_header_row": 1,
        "expected_column_header": "value",
        "concept": "dwp.uc_people",
        "source_concept": "dwp.people_on_universal_credit",
        "concept_relation": "source_label",
        "concept_authority": "dwp",
        "concept_evidence_url": f"{METADATA}/Conditionality%20Regime.html",
        "concept_evidence_notes": (
            f"DWP People on Universal Credit (UC_Monthly) cube cells for {months[0]} to "
            f"{months[-1]} by residence-based country, age and conditionality regime "
            "preserve the publisher labels and value URIs. People are individual "
            "claimants on the count date, the second Thursday of the month; DWP assigns "
            "each person one of six conditionality regimes. Stat-Xplore applies "
            "statistical disclosure control, so parts need not add to totals."
        ),
        "unit": "count",
        "aggregation": "sum",
        "expected_cell_type": "number",
    }
    not_ported = len(zero_series) * len(months)
    unknown_area = len(months) * len(age_items) * len(regime_items)
    header = render_header(
        months, facts, not_ported, unknown_area, ported_zero_cells, len(zero_series)
    )
    head = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100)
    lines = [header, head, "record_sets:\n"]
    defined: set[str] = set()
    measure_block = yaml.safe_dump(
        {"measures": [measure]}, sort_keys=False, allow_unicode=True, width=100
    )
    measure_block = textwrap.indent(measure_block, "  ")
    for record_set, members in record_sets:
        lines.append(
            yaml.safe_dump([record_set], sort_keys=False, allow_unicode=True, width=100)
        )
        lines.append("  rows:\n")
        for ordinal, (value_id, number, guards) in enumerate(members):
            anchor = "r_" + value_id
            if anchor not in defined:
                row = {
                    "value_id": templates[value_id]["value_id"],
                    "label": templates[value_id]["label"],
                    "ordinal": ordinal,
                    "row_number": number,
                    **{
                        key: value
                        for key, value in templates[value_id].items()
                        if key not in ("value_id", "label")
                    },
                    "guard_cells": guards,
                }
                lines.append(f"  - &{anchor} {yaml_scalar(row)}\n")
                defined.add(anchor)
                continue
            extra = {"ordinal": ordinal, "row_number": number, "guard_cells": guards}
            body = ", ".join(f"{k}: {yaml_scalar(v)}" for k, v in extra.items())
            lines.append(f"  - {{<<: *{anchor}, {body}}}\n")
        lines.append(measure_block)
    return "".join(lines)


def render_header(
    months: list[str],
    facts: int,
    not_ported: int,
    unknown_area: int,
    ported_zero_cells: int,
    zero_series: int,
) -> str:
    paragraphs = [
        f"""DWP People on Universal Credit (Stat-Xplore UC_Monthly) by residence-based
        country, age and conditionality regime, every month from {months[0]} to
        {months[-1]}, for {ISSUE} item 3 (PolicyEngine/uk-young-people-work-review#3 and
        PolicyEngine/uk-young-people-work-review#7). Written by {SCRIPT} from the pinned
        response; edit that, not this. The latest month is that of DWP's quarterly
        release of 18 August 2026 ('Universal Credit quarterly statistics, 29 April 2013
        to 14 May 2026'); 202606 is rejected as an invalid value. Since 12 May 2026 DWP
        releases these statistics quarterly, in February, May, August and November, and
        has 'removed' provisional monthly estimates, so the next release adds June to
        August 2026. DWP marks April and May 2025 'rev': 'Figures marked "rev" have been
        revised. However, they have not been previously released on Stat-Xplore as the
        data was suspended.'""",
        """These count people, not households: 'The monthly number of People on
        Universal Credit includes all individuals who have an open claim on the count
        date for that month', the count date being 'the second Thursday of each month'
        (Stat-Xplore user guide; annotation I). Both partners of a joint claim are
        counted.""",
        """Conditionality regime is the person's: 'Each person will be assigned one of
        six conditionality regimes based on their assessed capability and
        circumstances. ... Different members of a household can be subject to the same
        or different requirements' (field metadata). DWP describes 'No work
        requirements' as 'Not expected to work at present. Health or caring
        responsibility prevents claimant from working or preparing for work. Examples of
        people in this regime include those in full time education, over state pension
        age, have a child under 1 years old and those with no prospect to work', and
        'Preparing for work' as 'Expected to start preparing for future even with
        limited capability for work at the present time or a child aged 2'. Besides the
        six regimes the field has 'Unknown or missing regime', which is ported, so the
        regimes add to each age's total, and 'Not available prior to April 2015', which
        is zero in every month and is not.""",
        """Ages are single years from 16 to 24 (value set C_UC_SINGLE_AGE) and DWP's bands
        above (C_UC_AGE_BAND): 25-29 to 60-64, 65-70, 'Over 70' and 'Unknown/Missing'.
        'Age is derived from the claimant's date of birth'; 'The over 70 age group
        contains people aged 71 to 90 inclusive only. Over 90 years is classified as
        missing/unknown for this measure' (field metadata). Each single year and band
        carries age bounds. 'Over 70' carries its lower bound only, age >= 71, as the
        open top band of a sibling cube does ('90 and over', age >= 90), so a reader
        selecting by age keeps it; DWP's upper limit of 90 is the note quoted here.
        'Unknown/Missing' carries none.""",
        """Geography is the residence-based field (National - Regional - LA - OAs),
        country value set, with DWP's total: that total is the Great Britain count DWP
        publishes, and it includes people whose residence is unknown ('Unknown',
        ZZXXXXXXX), which emits no fact. The three countries therefore add to less than
        Great Britain by about the unknown-residence count; the Great Britain totals are
        those of dwp-uc-people-employment-indicator-january-2023-may-2026.""",
        f"""'Statistical disclosure control has been applied with Stat-Xplore, which guards
        against the identification of an individual claimant' (dataset metadata): cells
        are perturbed, so parts and totals need not add exactly;
        tests/test_source_uk_uc_people_age_conditionality.py bounds the gaps. Of the
        response's cells, the {unknown_area} for the unknown-residence item and the
        {not_ported} in the {zero_series} series that are zero in every month are not
        ported. The {facts} facts are every other cell, {ported_zero_cells} of them
        published zeros inside a kept series.""",
    ]
    lines: list[str] = []
    for paragraph in paragraphs:
        if lines:
            lines.append("")
        lines += textwrap.wrap(
            " ".join(textwrap.dedent(paragraph).split()),
            width=88,
            break_long_words=False,
            break_on_hyphens=False,
        )
    return "".join(f"# {line}".rstrip() + "\n" for line in lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the generated YAML with the committed file instead of writing.",
    )
    args = parser.parse_args()
    text = build()
    path = ROOT / "packages" / DIRECTORY / "source_package.yaml"
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            print(f"stale: packages/{DIRECTORY}/source_package.yaml")
            return 1
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
