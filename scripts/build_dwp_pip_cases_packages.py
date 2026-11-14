"""Generate the PIP cases with entitlement packages for PolicyEngine/chronicle#420 item 6.

Run from the repository root:

    uv run python scripts/build_dwp_pip_cases_packages.py

``--check`` compares the generated YAML with the committed files instead of writing.
Each package is written from its pinned Stat-Xplore response (database PIP_Monthly_new,
'PIP Cases with Entitlement from 2019', extracted 6 November 2026), read with Chronicle's
own parser, so every row number below is the virtual row the package parser builds. The
publisher's field labels and item labels are asserted, so a run against different bytes
fails rather than drifting. Nothing is downloaded and no value is computed.

- ``dwp-pip-cases-country-award-age-*``: cases by country of residence (England, Wales,
  Scotland), daily living award, mobility award and age band, each quarter-end month from
  January 2024 to July 2026;
- ``dwp-pip-cases-country-end-of-life-rules-award-*``: the same countries and months by
  End of Life Rules indicator (normal rules or SREL) and the two awards;
- ``dwp-pip-cases-country-disability-award-*``: the same countries and months by main
  disabling condition (disability category) and the two awards;
- ``dwp-pip-cases-region-award-*``: the nine English regions by the two awards;
- ``dwp-pip-cases-by-constituency-july-2026`` and ``dwp-pip-cases-by-local-authority-
  july-2026``: all cases at July 2026 by Westminster constituency and by local authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

import yaml

from chronicle.sources.cells import SourceArtifactMetadata
from chronicle.sources.rows import source_rows_from_statxplore_table
from chronicle.suite import _statxplore_age_range

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-11-06"
VINTAGE = "stat_xplore_2026_11_06"
ISSUE = "PolicyEngine/chronicle#420"
SCRIPT = "scripts/build_dwp_pip_cases_packages.py"

DATABASE = "str:database:PIP_Monthly_new"
DATABASE_LABEL = "PIP Cases with Entitlement from 2019"
MEASURE = "str:count:PIP_Monthly_new:V_F_PIP_MONTHLY"
MEASURE_LABEL = "PIP Cases with Entitlement from 2019"
FIELD = "str:field:PIP_Monthly_new:V_F_PIP_MONTHLY"
MONTH_FIELD = "str:field:PIP_Monthly_new:F_PIP_DATE:DATE2"
COUNTRY_FIELD = f"{FIELD}:COA_CODE"
DL_FIELD = f"{FIELD}:DL_AWARD_TYPE"
MOB_FIELD = f"{FIELD}:MOB_AWARD_TYPE"
AGE_FIELD = f"{FIELD}:SINGLE_AGE"
DISABILITY_FIELD = f"{FIELD}:DISABILITY_CODE"
RULES_FIELD = f"{FIELD}:TERMINALLY_ILL_RULES_IND"
CONSTITUENCY_VALUESET = "str:valueset:PIP_Monthly_new:V_F_PIP_MONTHLY:PCON24:V_C_MASTERGEOG21_PARLC24_TO_REGION"
LOCAL_AUTHORITY_VALUESET = "str:valueset:PIP_Monthly_new:V_F_PIP_MONTHLY:WARD_CODE:V_C_MASTERGEOG21_LA_TO_REGION"
METADATA_URL = "https://stat-xplore.dwp.gov.uk/webapi/metadata/PIP_Monthly_new/PIP_Monthly_new.html"
USER_GUIDE = (
    "https://www.gov.uk/government/publications/personal-independence-payment-data-on-"
    "stat-xplore-user-guide/personal-independence-payment-data-on-stat-xplore-user-guide"
)
RELEASE = (
    "https://www.gov.uk/government/statistics/personal-independence-payment-statistics-"
    "to-july-2026/personal-independence-payment-statistics-to-july-2026"
)
# The quarter-end months DWP refreshes (31 January, 30 April, 31 July, 31 October), from
# January 2024 to July 2026, the latest the release of 15 September 2026 carries.
MONTHS = (
    ("Jan-24", "2024-01"),
    ("Apr-24", "2024-04"),
    ("Jul-24", "2024-07"),
    ("Oct-24", "2024-10"),
    ("Jan-25", "2025-01"),
    ("Apr-25", "2025-04"),
    ("Jul-25", "2025-07"),
    ("Oct-25", "2025-10"),
    ("Jan-26", "2026-01"),
    ("Apr-26", "2026-04"),
    ("Jul-26", "2026-07"),
)
NOT_AREAS = {"XXZZZZZZZ": "Abroad", "ZZXXXXXXX": "Unknown"}


@dataclass(frozen=True)
class Category:
    """One categorical Stat-Xplore field: its publisher labels and Chronicle's value ids."""

    field_uri: str
    field_label: str
    key: str  # the parser's column key, which the facts' filters use
    values: tuple[tuple[str, str], ...]  # (publisher label, value-id part)
    total: str | None  # value-id part of the field's Total item, if requested
    total_label: str | None  # row-label wording of that Total
    age: bool = False


DAILY_LIVING = Category(
    DL_FIELD,
    "Daily Living Award Status",
    "daily_living_award_status",
    (
        ("Daily Living - Enhanced", "dl_enhanced"),
        ("Daily Living - Standard", "dl_standard"),
        ("Daily Living - Nil", "dl_nil"),
        ("Unknown or missing", "dl_unknown"),
    ),
    "dl_all",
    "all daily living awards",
)
MOBILITY = Category(
    MOB_FIELD,
    "Mobility Award Status",
    "mobility_award_status",
    (
        ("Mobility Award - Enhanced", "mob_enhanced"),
        ("Mobility Award - Standard", "mob_standard"),
        ("Mobility Award - Nil", "mob_nil"),
        ("Unknown or missing", "mob_unknown"),
    ),
    "mob_all",
    "all mobility awards",
)
AGE = Category(
    AGE_FIELD,
    "Age (bands and single year)",
    "age_bands_and_single_year",
    tuple(
        (label, "age_" + label.replace("-", "_").replace(" ", "_"))
        for label in (
            "16-19",
            "20-24",
            "25-29",
            "30-34",
            "35-39",
            "40-44",
            "45-49",
            "50-54",
            "55-59",
            "60-64",
            "65-69",
            "70-74",
            "75-79",
            "80-84",
            "85-89",
            "90 and over",
        )
    )
    + (("Unknown or missing", "age_unknown"),),
    "age_all",
    "all ages",
    age=True,
)
RULES = Category(
    RULES_FIELD,
    "End of Life Rules Indicator",
    "end_of_life_rules_indicator",
    (
        ("Normal Rules", "normal_rules"),
        ("SREL", "srel"),
        ("Missing or Unknown", "rules_unknown"),
    ),
    None,
    None,
)
DISABILITY = Category(
    DISABILITY_FIELD,
    "Disability",
    "disability",
    tuple(
        (label, "dis_" + slug)
        for label, slug in (
            ("Haematological Disease", "haematological"),
            ("Infectious disease", "infectious"),
            ("Malignant disease", "malignant"),
            ("Metabolic disease", "metabolic"),
            ("Psychiatric disorders", "psychiatric"),
            ("Neurological disease", "neurological"),
            ("Visual disease", "visual"),
            ("Hearing disorders", "hearing"),
            ("Cardiovascular disease", "cardiovascular"),
            ("Gastrointestinal disease", "gastrointestinal"),
            (
                "Diseases of the liver, gallbladder, biliary tract",
                "liver_gallbladder_biliary",
            ),
            ("Skin disease", "skin"),
            ("Musculoskeletal disease (general)", "musculoskeletal_general"),
            ("Musculoskeletal disease (regional)", "musculoskeletal_regional"),
            ("Autoimmune disease (connective tissue disorders)", "autoimmune"),
            ("Genitourinary disease", "genitourinary"),
            ("Endocrine disease", "endocrine"),
            ("Respiratory disease", "respiratory"),
            ("Multisystem and extremes of age", "multisystem_extremes_of_age"),
            ("Diseases of the immune system", "immune_system"),
            ("Unknown or missing", "unknown"),
            ("Disability not recorded - Assessment not completed", "not_recorded"),
        )
    ),
    None,
    None,
)
# Value-set codes of each requested item, in request order (the response echoes them).
VALUE_CODES = {
    DL_FIELD: ("1", "2", "3", "99"),
    MOB_FIELD: ("1", "2", "3", "99"),
    AGE_FIELD: tuple(str(code) for code in range(1, 16)) + ("999", "99999"),
    RULES_FIELD: ("2", "1", "99"),
    DISABILITY_FIELD: tuple(str(code) for code in range(1, 21)) + ("99", "9999"),
}
VALUE_SETS = {
    DL_FIELD: "C_PIP_DL_AWARD_TYPE",
    MOB_FIELD: "C_PIP_MOB_AWARD_TYPE",
    AGE_FIELD: "C_PIP_AGE_BAND",
    RULES_FIELD: "C_PIP_TERM_ILL_IND",
    DISABILITY_FIELD: "C_PIP_DIS_CAT",
}

COUNTRIES = (
    ("E92000001", "England"),
    ("W92000004", "Wales"),
    ("S92000003", "Scotland"),
)
REGIONS = (
    ("E12000001", "North East"),
    ("E12000002", "North West"),
    ("E12000003", "Yorkshire and The Humber"),
    ("E12000004", "East Midlands"),
    ("E12000005", "West Midlands"),
    ("E12000006", "East of England"),
    ("E12000007", "London"),
    ("E12000008", "South East"),
    ("E12000009", "South West"),
)
GEOGRAPHY_FIELD_LABEL = "National - Regional - LA - OAs"


@dataclass(frozen=True)
class Cube:
    stem: str
    title: str  # the package label's cross, e.g. 'country, award and age band'
    geography_valueset: str  # V_C_2021_COUNTRY or V_C_MASTERGEOG21_REGION_TO_COUNTRY
    geography_level: str
    areas: tuple[tuple[str, str], ...]
    categories: tuple[Category, ...]
    groupby: str
    groupby_label: str
    record_set_slug: str

    @property
    def window(self) -> str:
        return "january_2024_july_2026"

    @property
    def directory(self) -> str:
        return f"dwp/{self.stem}_{self.window}"

    @property
    def package_id(self) -> str:
        return "dwp-" + f"{self.stem}_{self.window}".replace("_", "-")

    @property
    def filename(self) -> str:
        return f"{self.stem}_{self.window}.json"


CUBES = (
    Cube(
        "pip_cases_country_award_age",
        "country, daily living award, mobility award and age band",
        "V_C_2021_COUNTRY",
        "country",
        COUNTRIES,
        (DAILY_LIVING, MOBILITY, AGE),
        "dwp.pip_country_award_age",
        "Country by daily living award by mobility award by age band",
        "country_award_age",
    ),
    Cube(
        "pip_cases_country_end_of_life_rules_award",
        "country, End of Life Rules indicator, daily living award and mobility award",
        "V_C_2021_COUNTRY",
        "country",
        COUNTRIES,
        (RULES, DAILY_LIVING, MOBILITY),
        "dwp.pip_country_end_of_life_rules_award",
        "Country by End of Life Rules indicator by daily living award by mobility award",
        "country_end_of_life_rules_award",
    ),
    Cube(
        "pip_cases_country_disability_award",
        "country, disability category, daily living award and mobility award",
        "V_C_2021_COUNTRY",
        "country",
        COUNTRIES,
        (DISABILITY, DAILY_LIVING, MOBILITY),
        "dwp.pip_country_disability_award",
        "Country by disability category by daily living award by mobility award",
        "country_disability_award",
    ),
    Cube(
        "pip_cases_region_award",
        "English region, daily living award and mobility award",
        "V_C_MASTERGEOG21_REGION_TO_COUNTRY",
        "region",
        REGIONS,
        (DAILY_LIVING, MOBILITY),
        "dwp.pip_region_award",
        "English region by daily living award by mobility award",
        "region_award",
    ),
)


@dataclass(frozen=True)
class AreaCube:
    stem: str
    valueset: str
    field_label: str
    level: str
    vintage: str
    noun: str  # 'Westminster parliamentary constituency'
    count: int  # areas, Abroad and Unknown excluded

    @property
    def directory(self) -> str:
        return f"dwp/{self.stem}"

    @property
    def package_id(self) -> str:
        return "dwp-" + self.stem.replace("_", "-")

    @property
    def filename(self) -> str:
        return f"{self.stem}.json"


AREA_CUBES = (
    AreaCube(
        "pip_cases_by_constituency_july_2026",
        CONSTITUENCY_VALUESET,
        "Westminster Parliamentary Constituency",
        "constituency",
        "pcon_2024",
        "Westminster parliamentary constituency (2024 boundaries)",
        632,
    ),
    AreaCube(
        "pip_cases_by_local_authority_july_2026",
        LOCAL_AUTHORITY_VALUESET,
        "National - Regional - LA - Ward",
        "local_authority",
        "lad_2023",
        "local authority",
        350,
    ),
)


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


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


def wrap(header: str) -> str:
    """The header's paragraphs, rewrapped as comment lines (breaking only at spaces)."""
    lines: list[str] = []
    for paragraph in textwrap.dedent(header).strip().split("\n\n"):
        if lines:
            lines.append("")
        lines += textwrap.wrap(
            " ".join(paragraph.split()),
            width=88,
            break_long_words=False,
            break_on_hyphens=False,
        )
    return "".join(f"# {line}".rstrip() + "\n" for line in lines)


def pinned(directory: str, filename: str) -> bytes:
    """The response bytes, checked against the manifest's digest and size."""
    manifest = yaml.safe_load((DATA / directory / "manifest.yaml").read_text())
    (entry,) = manifest["files"].values()
    assert entry["filename"] == filename, (directory, entry["filename"])
    content = (DATA / directory / filename).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"], directory
    assert len(content) == entry["size_bytes"], directory
    return content


def parsed(content: bytes, filename: str) -> tuple[dict, list]:
    """The response and its rows, as the package's statxplore_table_json_rows parser reads them."""
    artifact = SourceArtifactMetadata(
        source_name="dwp",
        source_table="",
        source_file=filename,
        url=None,
        vintage=VINTAGE,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        extracted_at=EXTRACTED_AT,
        extraction_method="",
    )
    rows = source_rows_from_statxplore_table(
        content, artifact, sheet_name="api_response"
    )
    return json.loads(content.decode("utf-8")), rows


def check_response(data: dict) -> None:
    assert data["database"]["uri"] == DATABASE, data["database"]
    assert data["database"]["label"] == DATABASE_LABEL, data["database"]
    assert [m["uri"] for m in data["measures"]] == [MEASURE]
    assert [m["label"] for m in data["measures"]] == [MEASURE_LABEL]
    assert list(data["cubes"]) == [MEASURE]


def check_items(
    field: dict, expected_uris: list[str], expected_labels: list[str], total: bool
):
    items = field["items"]
    if total:
        assert items[-1] == {"type": "Total", "labels": ["Total"]}, items[-1]
        items = items[:-1]
    assert [item["type"] for item in items] == ["RecodeItem"] * len(items)
    assert [item["uris"] for item in items] == [[uri] for uri in expected_uris], field[
        "uri"
    ]
    assert [item["labels"] for item in items] == [[label] for label in expected_labels]


def value_uri(field_uri: str, valueset: str, code: str) -> str:
    return field_uri.replace("str:field:", "str:value:") + f":{valueset}:{code}"


MEASURE_SPEC = {
    "measure_id": "cases_with_entitlement",
    "label": "PIP cases with entitlement",
    "ordinal": 0,
    "column": "B",
    "source_column_id": "value",
    "expected_column_header_row": 1,
    "expected_column_header": "value",
    "concept": "dwp.pip_cases_with_entitlement",
    "source_concept": "dwp.pip_cases_with_entitlement",
    "concept_relation": "source_label",
    "concept_authority": "dwp",
    "concept_evidence_url": METADATA_URL,
    "concept_evidence_notes": (
        "DWP Personal Independence Payment cases with entitlement (Stat-Xplore "
        "PIP_Monthly_new, 'PIP Cases with Entitlement from 2019'): claims entitled to PIP "
        "at the reference month, in payment or not ('payment may be suspended, for example "
        "if they are in hospital'), counted from the date of the decision; claims "
        "administered by DWP, unrounded administrative data with Stat-Xplore disclosure "
        "control."
    ),
    "unit": "count",
    "aggregation": "sum",
    "expected_cell_type": "number",
}


def record_set_head(record_set_id: str, period: str, groupby: str) -> dict:
    return {
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
        "entity": "person",
        "entity_role": "claimant",
        "domain": "social_security",
        "groupby_dimension": groupby,
        "assertion": "observation",
        "measures": [MEASURE_SPEC],
    }


def dump_record_set(record_set: dict) -> str:
    return yaml.safe_dump([record_set], sort_keys=False, allow_unicode=True, width=100)


def build_cube(cube: Cube) -> tuple[str, dict]:
    content = pinned(cube.directory, cube.filename)
    data, rows = parsed(content, cube.filename)
    check_response(data)
    fields = data["fields"]
    assert [field["uri"] for field in fields] == [
        MONTH_FIELD,
        COUNTRY_FIELD,
        *(category.field_uri for category in cube.categories),
    ]
    assert fields[1]["label"] == GEOGRAPHY_FIELD_LABEL
    check_items(
        fields[0],
        [
            f"str:value:PIP_Monthly_new:F_PIP_DATE:DATE2:C_PIP_DATE:{period.replace('-', '')}"
            for _, period in MONTHS
        ],
        [label for label, _ in MONTHS],
        total=False,
    )
    check_items(
        fields[1],
        [
            value_uri(COUNTRY_FIELD, cube.geography_valueset, code)
            for code, _ in cube.areas
        ],
        [name for _, name in cube.areas],
        total=False,
    )
    for field, category in zip(fields[2:], cube.categories):
        assert field["label"] == category.field_label, field["label"]
        check_items(
            field,
            [
                value_uri(category.field_uri, VALUE_SETS[category.field_uri], code)
                for code in VALUE_CODES[category.field_uri]
            ],
            [label for label, _ in category.values],
            total=category.total is not None,
        )
    # Columns: A measure, B value, then a label and a URI column per field.
    keys = ["month", "national_regional_la_oas", *(c.key for c in cube.categories)]
    label_column = {key: column_letter(2 + 2 * index) for index, key in enumerate(keys)}
    uri_column = {key: column_letter(3 + 2 * index) for index, key in enumerate(keys)}
    assert list(rows[0].values) == [
        "measure",
        "value",
        *(name for key in keys for name in (key, f"{key}_uri")),
    ]
    axes = [
        [(label, None) for label, _ in MONTHS],
        list(cube.areas),
        *(
            [
                *category.values,
                *((("Total", category.total),) if category.total else ()),
            ]
            for category in cube.categories
        ),
    ]
    sizes = [len(axis) for axis in axes]
    assert len(rows) == eval_product(sizes)
    # Each cell's virtual row is its parser row number plus one (header on row 1).
    by_month: dict[str, list[tuple[tuple, int, object]]] = {}
    for row in rows:
        values = row.values
        month = values["month"]
        series = (values["national_regional_la_oas_uri"].rsplit(":", 1)[1],) + tuple(
            values[category.key] for category in cube.categories
        )
        by_month.setdefault(month, []).append(
            (series, row.row_number + 1, values["value"])
        )
    assert list(by_month) == [label for label, _ in MONTHS]
    series_values: dict[tuple, list] = {}
    for month, cells in by_month.items():
        for series, _, value in cells:
            assert isinstance(value, int) and not isinstance(value, bool), (
                month,
                series,
            )
            series_values.setdefault(series, []).append(value)
    # A series zero in every month is not ported; a published zero inside a kept series is.
    dropped = {series for series, values in series_values.items() if not any(values)}
    kept_zeros = sum(
        1
        for series, values in series_values.items()
        if series not in dropped
        for value in values
        if value == 0
    )

    names = dict(cube.areas)
    total_parts = {c.key: (c.total, c.total_label) for c in cube.categories}
    part_of = {c.key: dict(c.values) for c in cube.categories}

    def row_spec(series: tuple) -> tuple[dict, list]:
        code, *labels = series
        value_parts = [code.lower()]
        label_parts = [names[code]]
        filters: dict[str, object] = {}
        constraints: list[dict] = []
        totals = []
        for category, label in zip(cube.categories, labels):
            if label == "Total":
                part, wording = total_parts[category.key]
                value_parts.append(part)
                label_parts.append(wording)
                filters[category.key] = "all"
                totals.append(category.key)
                continue
            value_parts.append(part_of[category.key][label])
            label_parts.append(label)
            filters[category.key] = label
            constraints.append(
                {
                    "variable": category.key,
                    "operator": "==",
                    "value": label,
                    "label": category.field_label,
                }
            )
            if category.age:
                bounds = _statxplore_age_range(label)
                if bounds is not None:
                    lower, upper = bounds
                    constraints.append(
                        {
                            "variable": "age",
                            "operator": ">=",
                            "value": lower,
                            "unit": "years",
                            "label": "Age lower bound",
                        }
                    )
                    if upper is not None:
                        constraints.append(
                            {
                                "variable": "age",
                                "operator": "<",
                                "value": upper,
                                "unit": "years",
                                "label": "Age upper bound",
                            }
                        )
        last = cube.categories[-1]
        if labels[-1] == "Total":
            header_column, header = label_column[last.key], "Total"
        else:
            code_of = dict(
                zip((label for label, _ in last.values), VALUE_CODES[last.field_uri])
            )
            header_column = uri_column[last.key]
            header = value_uri(
                last.field_uri, VALUE_SETS[last.field_uri], code_of[labels[-1]]
            )
        spec = {
            "value_id": "__".join(value_parts),
            "label": ", ".join(label_parts),
            "ordinal": None,
            "row_number": None,
            "expected_row_header_column": header_column,
            "expected_row_header": header,
            "geography_id": code,
            "geography_level": cube.geography_level,
            "geography_name": names[code],
            "geography_vintage": "current",
            "table_record_kind": "total" if totals else "detail",
            "filters": filters,
            "constraints": constraints,
        }
        return spec, labels

    def guards(series: tuple, labels: list, month: str, row_number: int) -> list[dict]:
        code = series[0]
        out = [
            {
                "column": "A",
                "row": row_number,
                "expected_value": MEASURE_LABEL,
                "label": "measure",
            },
            {
                "column": label_column["month"],
                "row": row_number,
                "expected_value": month,
                "label": "month",
            },
            {
                "column": uri_column["national_regional_la_oas"],
                "row": row_number,
                "expected_value": value_uri(
                    COUNTRY_FIELD, cube.geography_valueset, code
                ),
                "label": "geography value URI",
            },
        ]
        for category, label in zip(cube.categories, labels):
            name = category.field_label.lower()
            if label == "Total":
                out.append(
                    {
                        "column": label_column[category.key],
                        "row": row_number,
                        "expected_value": "Total",
                        "label": f"{name} total",
                    }
                )
                continue
            code_of = dict(
                zip(
                    (lab for lab, _ in category.values), VALUE_CODES[category.field_uri]
                )
            )
            out.append(
                {
                    "column": uri_column[category.key],
                    "row": row_number,
                    "expected_value": value_uri(
                        category.field_uri,
                        VALUE_SETS[category.field_uri],
                        code_of[label],
                    ),
                    "label": f"{name} value URI",
                }
            )
        return out

    lines: list[str] = []
    defined: set[str] = set()
    record_sets = []
    facts = 0
    for month, period in MONTHS:
        kind_rows: dict[str, list] = {"detail": [], "total": []}
        for series, row_number, _value in by_month[month]:
            if series in dropped:
                continue
            spec, labels = row_spec(series)
            kind_rows[spec["table_record_kind"]].append(
                (series, spec, labels, row_number)
            )
        for kind, kind_list in kind_rows.items():
            if not kind_list:
                continue
            record_set_id = (
                f"dwp.statx.pip_cases.{cube.record_set_slug}.month{period.replace('-', '_')}"
                + (".total" if kind == "total" else "")
            )
            head = record_set_head(record_set_id, period, cube.groupby)
            record_sets.append(head)
            lines.append(dump_record_set(head))
            lines.append("  rows:\n")
            for ordinal, (series, spec, labels, row_number) in enumerate(kind_list):
                anchor = "r__" + spec["value_id"]
                guard_cells = guards(series, labels, month, row_number)
                if anchor not in defined:
                    row = dict(
                        spec,
                        ordinal=ordinal,
                        row_number=row_number,
                        guard_cells=guard_cells,
                    )
                    lines.append(f"  - &{anchor} {yaml_scalar(row)}\n")
                    defined.add(anchor)
                else:
                    extra = {
                        "ordinal": ordinal,
                        "row_number": row_number,
                        "guard_cells": guard_cells,
                    }
                    body = ", ".join(f"{k}: {yaml_scalar(v)}" for k, v in extra.items())
                    lines.append(f"  - {{<<: *{anchor}, {body}}}\n")
                facts += 1
    stats = {
        "series": len(series_values),
        "dropped": len(dropped),
        "kept_zeros": kept_zeros,
        "facts": facts,
        "cells": len(rows),
    }
    return "".join(lines), stats


def eval_product(sizes: list[int]) -> int:
    total = 1
    for size in sizes:
        total *= size
    return total


def cube_header(cube: Cube, stats: dict) -> str:
    totals = [c for c in cube.categories if c.total]
    total_names = ", ".join(c.field_label for c in totals)
    geography = (
        "country of residence (England, Wales, Scotland; the V_C_2021_COUNTRY value set of "
        "the residence-based geography field)"
        if cube.geography_level == "country"
        else "the nine English regions of residence (V_C_MASTERGEOG21_REGION_TO_COUNTRY); "
        "Wales and England are in dwp-pip-cases-country-award-age-january-2024-july-2026"
    )
    extra = {
        "pip_cases_country_award_age": (
            "Age is the band value set C_PIP_AGE_BAND (16-19, five-year bands to 85-89, 90 "
            "and over, Unknown or missing), 'recorded in years as at the caseload date'; each "
            "band keeps its label as the filter and states numeric age bounds as constraints."
        ),
        "pip_cases_country_end_of_life_rules_award": (
            "SREL is the Special Rules for End of Life ('for people making a claim to PIP "
            "because they are approaching the end of their life due to a progressive "
            "disease'; from 3 April 2023 'death can reasonably be expected within 12 months', "
            "6 months before). The indicator requests no total, so the all-rules margin is "
            "dwp-pip-cases-country-award-age-january-2024-july-2026's and no fact is stated "
            "twice; 'Missing or Unknown' is zero in every month here."
        ),
        "pip_cases_country_disability_award": (
            "Disability is the main disabling condition recorded at the assessment, by DWP's "
            "data standard of 13 February 2023 (category value set C_PIP_DIS_CAT; the "
            "subgroups and conditions are not ported). Annotation X: from June 2024 Chronic "
            "Fatigue Syndrome moved from Musculoskeletal disease (general) to Neurological "
            "disease, back to April 2013. The category requests no total, so the all-"
            "conditions margin is dwp-pip-cases-country-award-age-january-2024-july-2026's."
        ),
        "pip_cases_region_award": (
            "The regions add to England's total in each month within disclosure control; "
            "tests/test_source_uk_pip_cases.py checks it."
        ),
    }[cube.stem]
    return f"""
    DWP Personal Independence Payment cases with entitlement (Stat-Xplore PIP_Monthly_new,
    'PIP Cases with Entitlement from 2019') by {cube.title}, the quarter-end months from
    January 2024 to July 2026, extracted {EXTRACTED_AT}, for {ISSUE} item 6. Written by
    {SCRIPT} from the pinned response; edit that, not this.

    Cases with entitlement: 'Claimants generally receive payment during the period for
    which they have entitlement, although there are times when payment may be suspended,
    for example if they are in hospital', and claims 'will not appear in the "cases with
    entitlement" statistics until the date of the decision' (PIP statistics to July 2026,
    {RELEASE}). DWP refreshes the series quarterly, with data 'up to and including the last
    day in the quarter (31 January, 30 April, 31 July, 31 October)' ({USER_GUIDE}); each
    month here is that point-in-time caseload, so period_type is month.

    Geography is {geography}. The request avoids the field's Devolution value set, which
    codes 'DWP Ownership' (England, Wales and abroad) as K03000001, Great Britain's code;
    cases abroad and of unknown residence have no GSS code and are not requested. Scotland:
    PIP is devolved and replaced by Adult Disability Payment, and 'Social Security Scotland
    completed the case transfer process for those who were in receipt of PIP in Scotland by
    the end of June 2025' (annotation II). The Scotland rows are the residual claims DWP
    still administers there, falling from 218,589 in January 2024 to 919 in July 2026; from
    July 2025 they 'may relate to cases where a person moves to Scotland from England or
    Wales while in receipt of PIP', with a run-on of up to 13 weeks from November 2025
    (annotation III). So the Scotland rows are not Scotland's disability caseload.

    {extra}

    The two awards are the daily living and mobility components ('standard rate if they
    score between 8 and 11 points', 'enhanced rate if their scores add up to 12 points or
    more'; Nil is no award of that component), each with DWP's 'Unknown or missing' band.
    Annotation XI: 'For a very small proportion of the caseload (0.2%), the combination of
    award rates (daily living and mobility) is reported as nil-nil', a claim under review.
    {total_names} request total: true; those rows sit in .total record sets with the filter
    'all', and every other field is total: false.

    Stat-Xplore data 'are unrounded' (the user guide), and 'Statistical disclosure control
    is applied to Stat-Xplore tables ... Totals may not sum due to the disclosure control
    applied': 'all cells may be slightly adjusted to prevent any identifiable data being
    exposed' (Stat-Xplore's Data Confidentiality note). So the categories and their Total
    need not add exactly; tests/test_source_uk_pip_cases.py checks they add within it. Of {stats["series"]}
    series, {stats["dropped"]} are zero in every month and are not ported. The {stats["facts"]}
    facts are every other cell ({stats["kept_zeros"]} of them published zeros inside a kept
    series).
    """


def build_cube_package(cube: Cube) -> str:
    body, stats = build_cube(cube)
    months = f"{MONTHS[0][0]} (January 2024) through {MONTHS[-1][0]} (July 2026)"
    totals = [c for c in cube.categories if c.total]
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": cube.package_id,
        "label": (
            f"DWP Stat-Xplore: PIP cases with entitlement by {cube.title}, January 2024 to "
            "July 2026"
        ),
        "dimension_labels": {cube.groupby: cube.groupby_label},
        "artifact": {
            "source_name": "dwp",
            "source_table": (
                f"PIP cases with entitlement by {cube.title}, January 2024 to July 2026"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{cube.directory}",
            "manifest": "manifest.yaml",
            "vintage": VINTAGE,
            "extracted_at": EXTRACTED_AT,
            "extraction_method": (
                "Stat-Xplore Open Data API table response parsed and unpivoted to one row per "
                f"cube cell; database {DATABASE}; measure {MEASURE}; fields in response "
                f"order: {MONTH_FIELD}; {COUNTRY_FIELD}; "
                + "; ".join(c.field_uri for c in cube.categories)
                + "; value sets: C_PIP_DATE, "
                + cube.geography_valueset
                + ", "
                + ", ".join(VALUE_SETS[c.field_uri] for c in cube.categories)
                + f"; reference months {months}, the quarter-end months; recode total: true "
                + "on "
                + ", ".join(c.field_uri.rsplit(":", 1)[1] for c in totals)
                + ", total: false on every other field."
            ),
            "parser": "statxplore_table_json_rows",
            "sheet_name": "api_response",
            "artifact_year": 2026,
        },
    }
    header = wrap(cube_header(cube, stats))
    head = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100)
    return header + head + "record_sets:\n" + body


def build_area_package(area: AreaCube) -> str:
    content = pinned(area.directory, area.filename)
    data, rows = parsed(content, area.filename)
    check_response(data)
    fields = data["fields"]
    assert [field["uri"] for field in fields] == [MONTH_FIELD, area.valueset]
    assert fields[1]["label"] == area.field_label
    check_items(
        fields[0],
        ["str:value:PIP_Monthly_new:F_PIP_DATE:DATE2:C_PIP_DATE:202607"],
        ["Jul-26"],
        total=False,
    )
    items = fields[1]["items"]
    assert all(item["type"] == "RecodeItem" for item in items)
    prefix = area.valueset.replace("str:valueset:", "str:value:") + ":"
    assert all(item["uris"][0].startswith(prefix) for item in items)
    codes = [item["uris"][0].rsplit(":", 1)[1] for item in items]
    assert {
        code: item["labels"][0] for code, item in zip(codes, items) if code in NOT_AREAS
    } == NOT_AREAS
    assert codes[-2:] == ["XXZZZZZZZ", "ZZXXXXXXX"], codes[-2:]
    assert len(codes) == area.count + 2 and len(set(codes)) == len(codes)
    # The parser names a field's columns after its label (snake case).
    key = re.sub(r"[^a-z0-9]+", "_", area.field_label.lower()).strip("_")
    assert list(rows[0].values) == [
        "measure",
        "value",
        "month",
        "month_uri",
        key,
        f"{key}_uri",
    ]
    assert len(rows) == len(items)
    record_set_id = f"dwp.statx.pip_cases.{area.level}.month2026_07"
    head = record_set_head(record_set_id, "2026-07", "geography")
    lines = [dump_record_set(head), "  rows:\n"]
    facts = 0
    for ordinal, row in enumerate(
        row
        for row in rows
        if row.values[f"{key}_uri"].rsplit(":", 1)[1] not in NOT_AREAS
    ):
        values = row.values
        code = values[f"{key}_uri"].rsplit(":", 1)[1]
        assert values["month"] == "Jul-26"
        assert isinstance(values["value"], int) and values["value"] > 0, code
        row_number = row.row_number + 1
        spec = {
            "value_id": code.lower(),
            "label": values[key],
            "ordinal": ordinal,
            "row_number": row_number,
            "expected_row_header_column": "F",
            "expected_row_header": values[f"{key}_uri"],
            "geography_id": code,
            "geography_level": area.level,
            "geography_name": values[key],
            "geography_vintage": area.vintage,
            "table_record_kind": "detail",
            "guard_cells": [
                {
                    "column": "A",
                    "row": row_number,
                    "expected_value": MEASURE_LABEL,
                    "label": "measure",
                },
                {
                    "column": "C",
                    "row": row_number,
                    "expected_value": "Jul-26",
                    "label": "month",
                },
            ],
        }
        lines.append(f"  - {yaml_scalar(spec)}\n")
        facts += 1
    assert facts == area.count
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": area.package_id,
        "label": f"DWP Stat-Xplore: PIP cases with entitlement by {area.noun}, July 2026",
        "dimension_labels": {"geography": "Geography"},
        "artifact": {
            "source_name": "dwp",
            "source_table": f"PIP cases with entitlement by {area.noun}, July 2026",
            "resource_package": "db",
            "resource_directory": f"data/{area.directory}",
            "manifest": "manifest.yaml",
            "vintage": VINTAGE,
            "extracted_at": EXTRACTED_AT,
            "extraction_method": (
                "Stat-Xplore Open Data API table response parsed and unpivoted to one row per "
                f"cube cell; database {DATABASE}; measure {MEASURE}; fields in response "
                f"order: {MONTH_FIELD}; {area.valueset} (every value of the value set); "
                "reference month Jul-26 (July 2026); no recode totals."
            ),
            "parser": "statxplore_table_json_rows",
            "sheet_name": "api_response",
            "artifact_year": 2026,
        },
    }
    header = wrap(
        f"""
        DWP Personal Independence Payment cases with entitlement (Stat-Xplore
        PIP_Monthly_new, 'PIP Cases with Entitlement from 2019') by {area.noun} of
        residence at July 2026, the latest month of the release of 15 September 2026,
        extracted {EXTRACTED_AT}, for {ISSUE} item 6. Written by {SCRIPT} from the pinned
        response; edit that, not this.

        Every value of the value set {area.valueset.rsplit(":", 1)[1]} is requested: the
        {area.count} areas of Great Britain, as the UC area packages read them
        ({area.vintage}), plus 'Abroad' (XXZZZZZZZ) and 'Unknown' (ZZXXXXXXX), which have no
        GSS code and emit no facts. 'Geographies are based on the claimants latest recorded
        address' (annotation V). Scottish areas hold only the residual claims DWP still
        administers there after the move to Adult Disability Payment (annotations II and
        III; see dwp-pip-cases-country-award-age-january-2024-july-2026), so they are not
        Scotland's disability caseload.

        Cases with entitlement are claims entitled to PIP at the month, in payment or not,
        counted from the date of the decision. Stat-Xplore data 'are unrounded', with
        disclosure control applied, so the areas need not add exactly to the country
        totals; tests/test_source_uk_pip_cases.py checks they add within it. {area.count}
        facts.
        """
    )
    head_text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100)
    return header + head_text + "record_sets:\n" + "".join(lines)


BUILDERS = {
    **{cube.directory: (lambda cube=cube: build_cube_package(cube)) for cube in CUBES},
    **{
        area.directory: (lambda area=area: build_area_package(area))
        for area in AREA_CUBES
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the generated YAML with the committed files instead of writing.",
    )
    args = parser.parse_args()
    stale = []
    for directory, build in BUILDERS.items():
        text = build()
        path = PACKAGES / directory / "source_package.yaml"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(directory)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    for directory in stale:
        print(f"stale: packages/{directory}/source_package.yaml")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
