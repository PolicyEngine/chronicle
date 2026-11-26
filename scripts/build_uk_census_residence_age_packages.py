"""Author the chronicle#358 census residence-type-by-age packages.

Writes, from the bytes the manifests pin under ``db/data`` (nothing downloaded and
no fact built):

- eight ``ons-census2021-ur-{hh,ce}-age101-{sex,persons}-{ctry,rgn}`` packages:
  ONS Census 2021 usual residents in households (UR_HH) and in communal
  establishments (UR_CE) by single year of age (0 to 100 and over), by sex and
  for all persons, for England and Wales and the English regions, from the
  Census API's census-observations responses;
- six ``nisra-census2021-residence-type-age-{sex,persons}-{ni,lgd14,parlcon24}``
  packages: NISRA's flexible-table equivalent by single year of age;
- ``nrs-census2022-uv101a-scotland``: NRS UV101a at Scotland level, the finest
  residence-type-by-age table NRS publishes (top band 85 and over).

Selectors are located by matching publisher text in the parsed source rows, and
every match is asserted, so a re-run against different bytes fails rather than
drifting.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class PackageDumper(yaml.SafeDumper):
    """Emit plain YAML with no anchors, so every record set reads alone."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def write_package(directory: Path, payload: dict, comment: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "source_package.yaml").write_text(
        comment
        + yaml.dump(
            payload,
            Dumper=PackageDumper,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        ),
        encoding="utf-8",
    )


def constraint(variable: str, value: object, label: str) -> dict:
    return {"variable": variable, "operator": "==", "value": value, "label": label}


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def census_period(year: int, day: str, notes: str) -> dict:
    return {
        "period_type": "calendar_year",
        "period": year,
        "period_coverage": {
            "start_date": day,
            "end_date": day,
            "basis": "calendar",
            "source_period_label": f"Census {year}",
            "notes": notes,
        },
    }


# ---------------------------------------------------------------------------- ONS

ONS_API = "https://api.beta.ons.gov.uk/v1/population-types"
ONS_POPULATION_TYPES = {
    "UR_HH": "All usual residents in households",
    "UR_CE": "All usual residents in communal establishments",
}
ONS_AGE_NOTE = (
    "ONS's quality statement on the age variable: single-year estimates for ages 90 "
    "to 100 and over are less reliable than the 90 and over group as a whole, because "
    "estimation and adjustment at these ages was based on the 90+ range (Census 2021 "
    "dictionary, Age; resident_age_101a quality_statement_text in the API)."
)
ONS_SDC_NOTE = (
    "Cells are as published after targeted record swapping and cell key perturbation, "
    "so they need not add to totals or match other tables (ONS, Protecting personal "
    "data in Census 2021 results)."
)


def ons_rows(path: Path) -> tuple[list[str], list[dict], dict]:
    """Columns, rows and payload as the ons_census_observations_json_rows parser emits."""
    data = json.loads(path.read_bytes().decode("utf-8"))
    columns: list[str] | None = None
    rows = []
    for entry in data["observations"]:
        values = {"population_type": None}
        for dimension in entry["dimensions"]:
            values[dimension["dimension_id"]] = dimension["option"]
            values[f"{dimension['dimension_id']}_code"] = dimension["option_id"]
        values["observation"] = entry["observation"]
        if columns is None:
            columns = list(values)
        assert list(values) == columns
        rows.append(values)
    return columns, rows, data


def build_ons(population_type: str, area_type: str, by_sex: bool) -> None:
    kind = "sex" if by_sex else "persons"
    slug = population_type.lower().replace("_", "-")
    package_id = f"ons-census2021-{slug}-age101-{kind}-{area_type}"
    directory = f"ons/census2021_{population_type.lower()}_age101_{kind}_{area_type}"
    dims = "resident_age_101a,sex" if by_sex else "resident_age_101a"
    filename = f"census2021_{population_type.lower()}_{area_type}_{dims.replace(',', '_')}.json"
    path = ROOT / "db/data" / directory / filename
    columns, rows, data = ons_rows(path)
    href = data["links"]["self"]["href"]
    assert f"/population-types/{population_type}/census-observations" in href, href
    assert data["total_observations"] == len(rows) and data["blocked_areas"] == 0
    letters = {name: column_letter(i) for i, name in enumerate(columns)}
    area_code_column = letters[f"{area_type}_code"]
    age_code_column = letters["resident_age_101a_code"]
    value_column = letters["observation"]
    sex_code_column = letters.get("sex_code")
    areas = []
    for row in rows:
        code = row[f"{area_type}_code"]
        if (code, row[area_type]) not in areas:
            areas.append((code, row[area_type]))
    if area_type == "rgn":
        # Wales is in both area types with identical cells; it is ported once,
        # from the country response.
        assert ("W92000004", "Wales") in areas
        areas = [area for area in areas if area[0] != "W92000004"]
        assert len(areas) == 9 and all(code.startswith("E12") for code, _ in areas)
    else:
        assert areas == [("E92000001", "England"), ("W92000004", "Wales")], areas
    sexes = [("1", "Female"), ("2", "Male")] if by_sex else [(None, None)]
    record_sets = []
    for code, name in areas:
        for sex_code, sex_label in sexes:
            selected = []
            for index, row in enumerate(rows, start=2):
                if row[f"{area_type}_code"] != code:
                    continue
                if sex_code is not None and row["sex_code"] != sex_code:
                    continue
                selected.append((index, row))
            assert [r["resident_age_101a_code"] for _, r in selected] == [
                str(a) for a in range(101)
            ]
            level = "country" if area_type == "ctry" else "region"
            row_specs = []
            for ordinal, (row_number, row) in enumerate(selected):
                age_label = row["resident_age_101a"]
                guards = [
                    {
                        "column": area_code_column,
                        "row": row_number,
                        "expected_value": code,
                        "label": "area code",
                    }
                ]
                if sex_code is not None:
                    assert row["sex"] == sex_label
                    guards.append(
                        {
                            "column": sex_code_column,
                            "row": row_number,
                            "expected_value": int(sex_code),
                            "label": "sex option id",
                        }
                    )
                row_specs.append(
                    {
                        "value_id": f"age_{row['resident_age_101a_code']}",
                        "label": age_label,
                        "ordinal": ordinal,
                        "row_number": row_number,
                        "expected_row_header_column": age_code_column,
                        "expected_row_header": int(row["resident_age_101a_code"]),
                        "table_record_kind": "detail",
                        "filters": {"resident_age_101a": age_label},
                        "constraints": [
                            constraint(
                                "resident_age_101a", age_label, "Age (101 categories)"
                            )
                        ],
                        "guard_cells": guards,
                    }
                )
            shared_filters = {"population_type": population_type}
            shared_constraints = [
                constraint("population_type", population_type, "Population type")
            ]
            if sex_code is not None:
                shared_filters["sex"] = sex_label
                shared_constraints.append(constraint("sex", sex_label, "Sex"))
            record_set_id = (
                f"ons.census2021.{population_type.lower()}.age101.{code.lower()}"
                + (f".{sex_label.lower()}" if sex_label else ".all_persons")
            )
            record_sets.append(
                {
                    "record_set_id": record_set_id,
                    "provenance_class": "census",
                    "record_set_spec_id": f"{record_set_id}.v1",
                    "source_record_id_prefix": record_set_id,
                    "sheet_name": "observations",
                    **census_period(
                        2021,
                        "2021-03-21",
                        f"Census day 21 March 2021. {ONS_POPULATION_TYPES[population_type]}; "
                        "students at their term-time address.",
                    ),
                    "geography_id": code,
                    "geography_level": level,
                    "geography_name": name,
                    "geography_vintage": "current",
                    "entity": "person",
                    "entity_role": "usual_resident",
                    "domain": "population",
                    "groupby_dimension": "resident_age_101a",
                    "shared_filters": shared_filters,
                    "shared_constraints": shared_constraints,
                    "measures": [
                        {
                            "measure_id": "ons_census2021_residents",
                            "label": "Usual residents",
                            "ordinal": 0,
                            "column": value_column,
                            "source_column_id": "observation",
                            "expected_column_header_row": 1,
                            "expected_column_header": "observation",
                            "concept": "ons.census2021_residents",
                            "concept_evidence_url": f"{ONS_API}/{population_type}/census-observations",
                            "concept_evidence_notes": (
                                f"ONS Census 2021 API, population type {population_type} "
                                f"({ONS_POPULATION_TYPES[population_type]}), area type {area_type}, "
                                f"dimensions {dims}: each cell as published. {ONS_AGE_NOTE} "
                                f"{ONS_SDC_NOTE}"
                            ),
                            "unit": "count",
                            "aggregation": "sum",
                            "expected_cell_type": "number",
                        }
                    ],
                    "rows": row_specs,
                }
            )
    label_population = ONS_POPULATION_TYPES[population_type]
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": package_id,
        "label": (
            f"ONS Census 2021: {label_population.lower()} by single year of age"
            + (" and sex" if by_sex else " (all persons)")
            + (", England and Wales" if area_type == "ctry" else ", English regions")
        ),
        "dimension_labels": {
            "population_type": "Population type",
            "resident_age_101a": "Age (101 categories)",
            **({"sex": "Sex"} if by_sex else {}),
        },
        "dimension_value_labels": {
            "population_type": {population_type: label_population}
        },
        "artifact": {
            "source_name": "ons",
            "source_table": (
                f"ONS Census 2021 custom dataset: {population_type} by {dims.replace(',', ' by ')}, "
                f"{'countries' if area_type == 'ctry' else 'regions'}"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{directory}",
            "manifest": "manifest.yaml",
            "vintage": "census_2021_api_extracted_2026_10_15",
            "extracted_at": "2026-10-15",
            "extraction_method": (
                "ONS Census API census-observations JSON, one source row per published cell"
            ),
            "parser": "ons_census_observations_json_rows",
            "sheet_name": "observations",
            "artifact_year": 2021,
        },
        "record_sets": record_sets,
    }
    write_package(
        ROOT / "packages" / directory,
        payload,
        ons_header(population_type, area_type, by_sex),
    )


def ons_header(population_type: str, area_type: str, by_sex: bool) -> str:
    return f"""\
# ONS Census 2021 (census day 21 March 2021), from the Census API's "create a custom dataset"
# service: GET /v1/population-types/{population_type}/census-observations with area type
# {area_type} and dimensions resident_age_101a{",sex" if by_sex else ""}, for
# PolicyEngine/chronicle#358 item 1. Population type {population_type} is
# {ONS_POPULATION_TYPES[population_type].lower()}; with its counterpart it splits the usual
# residents of RM120 (ons.census2021_residents) by residence type, here by single year of age
# 0 to 99 and 'Aged 100 years and over', so 85-89 and 90 and over can be told apart.
#
# The response is preserved byte for byte (deterministic: two fetches agree) and parsed by
# ons_census_observations_json_rows, one row per published cell; the population type is read
# from the request URL the response echoes. Every cell is a fact as published: ONS applies
# targeted record swapping and cell key perturbation, so cells need not add to totals or to
# other tables' cells. {"Sex has no all-persons category; the all-persons cells are their own query and package." if by_sex else "These are the all-persons cells, a query of their own because the sex dimension has no total."}
# {"The rgn area type is the nine English regions plus Wales as a whole; Wales is ported once, from the ctry response, where its cells are identical." if area_type == "rgn" else "England and Wales are the two areas of the ctry area type."}
#
# ONS's quality statement on age: single-year estimates for 90 to 100 and over are less
# reliable than the 90+ group, because estimation and adjustment at those ages used the 90+
# range (the census dictionary's Age entry; the API's quality_statement_text). It does not say
# the single years were derived from a 90+ total.
"""


# -------------------------------------------------------------------------- NISRA

NISRA_GEOGRAPHIES = {
    "ni": (None, None, None),
    "lgd14": ("Local Government District 2014", "local_authority", "lgd_2014"),
    "parlcon24": ("Parliamentary Constituency 2024", "constituency", "pcon_2024"),
}


def build_nisra(geo: str, by_sex: bool) -> None:
    kind = "sex" if by_sex else "persons"
    package_id = f"nisra-census2021-residence-type-age-{kind}-{geo}"
    directory = f"nisra/census2021_residence_type_age_{kind}_{geo}"
    filename = f"census2021_residence_type_single_year_age_{kind}_{geo}.csv"
    path = ROOT / "db/data" / directory / filename
    reader = csv.reader(io.StringIO(path.read_bytes().decode("utf-8")))
    header = next(reader)
    data = list(reader)
    geo_label, level, vintage = NISRA_GEOGRAPHIES[geo]
    expected = (
        ([f"{geo_label} Code", f"{geo_label} Label"] if geo_label else [])
        + [
            "Residence Type Code",
            "Residence Type Label",
            "Age Code",
            "Age Label",
        ]
        + (["Sex Code", "Sex Label"] if by_sex else [])
        + ["Count"]
    )
    assert header == expected, header
    letters = {name: column_letter(i) for i, name in enumerate(header)}
    index = {name: i for i, name in enumerate(header)}
    residence_types = [
        ("1", "Person in a household"),
        ("2", "Person in a communal establishment"),
    ]
    sexes = [("1", "Female"), ("2", "Male")] if by_sex else [(None, None)]
    record_sets = []
    for residence_code, residence_label in residence_types:
        for sex_code, sex_label in sexes:
            rows = []
            for row_number, values in enumerate(data, start=2):
                if values[index["Residence Type Code"]] != residence_code:
                    continue
                if sex_code is not None and values[index["Sex Code"]] != sex_code:
                    continue
                assert values[index["Residence Type Label"]] == residence_label
                age_code, age_label = (
                    values[index["Age Code"]],
                    values[index["Age Label"]],
                )
                guards = [
                    {
                        "column": letters["Residence Type Code"],
                        "row": row_number,
                        "expected_value": int(residence_code),
                        "label": "residence type code",
                    },
                ]
                if sex_code is not None:
                    assert values[index["Sex Label"]] == sex_label
                    guards.append(
                        {
                            "column": letters["Sex Code"],
                            "row": row_number,
                            "expected_value": int(sex_code),
                            "label": "sex code",
                        }
                    )
                spec = {
                    "value_id": f"age_{age_code}",
                    "label": age_label,
                    "ordinal": len(rows),
                    "row_number": row_number,
                    "expected_row_header_column": letters["Age Code"],
                    "expected_row_header": int(age_code),
                    "table_record_kind": "detail",
                    "filters": {"Age Label": age_label},
                    "constraints": [constraint("Age Label", age_label, "Age")],
                    "guard_cells": guards,
                }
                if geo_label:
                    code = values[index[f"{geo_label} Code"]]
                    name = values[index[f"{geo_label} Label"]]
                    spec["value_id"] = f"{code.lower()}__age_{age_code}"
                    spec["geography_id"] = code
                    spec["geography_level"] = level
                    spec["geography_name"] = name
                    spec["geography_vintage"] = vintage
                    spec["guard_cells"].append(
                        {
                            "column": letters[f"{geo_label} Code"],
                            "row": row_number,
                            "expected_value": code,
                            "label": "area code",
                        }
                    )
                rows.append(spec)
            areas = 1 if not geo_label else (11 if geo == "lgd14" else 18)
            assert len(rows) == 101 * areas, (
                geo,
                kind,
                residence_code,
                sex_code,
                len(rows),
            )
            shared_filters = {"Residence Type Label": residence_label}
            shared_constraints = [
                constraint("Residence Type Label", residence_label, "Residence type")
            ]
            if sex_code is not None:
                shared_filters["Sex Label"] = sex_label
                shared_constraints.append(constraint("Sex Label", sex_label, "Sex"))
            residence_slug = (
                "household" if residence_code == "1" else "communal_establishment"
            )
            record_set_id = (
                f"nisra.census2021.residence_type_age.{geo}.{residence_slug}"
                + (f".{sex_label.lower()}" if sex_label else ".all_persons")
            )
            record_sets.append(
                {
                    "record_set_id": record_set_id,
                    "provenance_class": "census",
                    "record_set_spec_id": f"{record_set_id}.v1",
                    "source_record_id_prefix": record_set_id,
                    "sheet_name": filename,
                    **census_period(
                        2021,
                        "2021-03-21",
                        "Census day 21 March 2021; age on census day.",
                    ),
                    "geography_id": "N92000002",
                    "geography_level": "country",
                    "geography_name": "Northern Ireland",
                    "geography_vintage": "current",
                    "entity": "person",
                    "entity_role": "usual_resident",
                    "domain": "population",
                    "groupby_dimension": "Age Label",
                    "shared_filters": shared_filters,
                    "shared_constraints": shared_constraints,
                    "measures": [
                        {
                            "measure_id": "nisra_census2021_residents",
                            "label": "Usual residents",
                            "ordinal": 0,
                            "column": letters["Count"],
                            "source_column_id": "Count",
                            "expected_column_header_row": 1,
                            "expected_column_header": "Count",
                            "concept": "nisra.census2021_residents",
                            "concept_evidence_url": (
                                "https://build.nisra.gov.uk/en/standard/DT-0063"
                            ),
                            "concept_evidence_notes": (
                                "NISRA Census 2021 flexible table builder, dataset PEOPLE, "
                                "residence type by single year of age (AGE_SYOA, 0 to '100+ years')"
                                + (" by sex" if by_sex else "")
                                + ": DT-0063's variables with single years in place of its 19 "
                                "bands, as the request prefers. Communal establishment counts "
                                "include people sleeping rough. Cells as published after targeted "
                                "record swapping and cell key perturbation (cover sheet)."
                            ),
                            "unit": "count",
                            "aggregation": "sum",
                            "expected_cell_type": "number",
                        }
                    ],
                    "rows": rows,
                }
            )
    geography_text = {
        "ni": "Northern Ireland",
        "lgd14": "local government districts (2014)",
        "parlcon24": "Westminster parliamentary constituencies (2024)",
    }[geo]
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": package_id,
        "label": (
            "NISRA Census 2021: usual residents by residence type and single year of age"
            + (" and sex" if by_sex else " (all persons)")
            + f", {geography_text}"
        ),
        "dimension_labels": {
            "Age Label": "Age",
            "Residence Type Label": "Residence type",
            **({"Sex Label": "Sex"} if by_sex else {}),
        },
        "artifact": {
            "source_name": "nisra",
            "source_table": (
                "NISRA Census 2021 flexible table: residence type by single year of age"
                + (" by sex" if by_sex else "")
                + f", {geography_text}"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{directory}",
            "manifest": "manifest.yaml",
            "vintage": "census_2021_flexible_table_builder_extracted_2026_10_15",
            "extracted_at": "2026-10-15",
            "extraction_method": (
                "Flexible Table Builder CSV, delimited text full-row parse, one source row per cell"
            ),
            "parser": "delimited_text_full_rows",
            "sheet_name": filename,
            "artifact_year": 2021,
        },
        "record_sets": record_sets,
    }
    write_package(ROOT / "packages" / directory, payload, nisra_header(geo, by_sex))


def nisra_header(geo: str, by_sex: bool) -> str:
    where = {
        "ni": "Northern Ireland",
        "lgd14": "the 11 local government districts (2014 boundaries)",
        "parlcon24": (
            "the 18 Westminster constituencies (2024 boundaries), which the builder approximates "
            "by best-fit Data Zone 2021 aggregation"
        ),
    }[geo]
    return f"""\
# NISRA Census 2021 (census day 21 March 2021), for PolicyEngine/chronicle#358 item 3: usual
# residents by residence type (person in a household / in a communal establishment) and
# single year of age (0 to '100+ years'){" by sex" if by_sex else ", all persons"}, for {where}.
# DT-0063 'Residence Type by Age (19 Categories) by Sex' splits 85-89 from 90+, and the builder
# offers the same variables with single year of age (AGE_SYOA), which the request prefers: it
# also gives 15, 16-17 and 18-19. The extract is the builder's stable CSV (two downloads
# agree byte for byte); the builder publishes no totals{", and the all-persons cells are a query of their own" if by_sex else ""}.
# NISRA applies targeted record swapping and cell key perturbation, so cells need not add to
# totals across tables; communal establishment counts include people sleeping rough.
"""


# ---------------------------------------------------------------------------- NRS

NRS_DIR = "nrs/census2022_uv101a_scotland"
NRS_FILE = "census2022_uv101a_sex_and_age_residence_type_scotland.csv"


def build_nrs() -> None:
    path = ROOT / "db/data" / NRS_DIR / NRS_FILE
    lines = path.read_bytes().decode("utf-8").splitlines()
    assert (
        lines[10]
        == '"Counting","Country","Sex","Age","Residence Type Indicator","Count",'
    ), lines[10]
    reader = csv.reader(io.StringIO("\n".join(lines[11:])))
    data = []
    for values in reader:
        if len(values) >= 6 and values[0] == "Individuals":
            data.append(values)
        else:
            break
    assert len(data) == 189, len(data)
    letters = {
        "Counting": "A",
        "Country": "B",
        "Sex": "C",
        "Age": "D",
        "Residence Type Indicator": "E",
        "Count": "F",
    }
    record_sets = []
    for sex in ("All people", "Female", "Male"):
        for residence in (
            "All people",
            "Lives in a household",
            "Lives in a communal establishment",
        ):
            rows = []
            for offset, values in enumerate(data):
                if values[2] != sex or values[4] != residence:
                    continue
                assert values[1] == "Scotland"
                row_number = offset + 2
                age = values[3]
                rows.append(
                    {
                        "value_id": "age_"
                        + age.lower().replace(" - ", "_").replace(" ", "_"),
                        "label": age,
                        "ordinal": len(rows),
                        "row_number": row_number,
                        "expected_row_header_column": "D",
                        "expected_row_header": age,
                        "table_record_kind": "total" if age == "Total" else "detail",
                        "filters": {"Age": age},
                        "constraints": [constraint("Age", age, "Age")],
                        "guard_cells": [
                            {
                                "column": "B",
                                "row": row_number,
                                "expected_value": "Scotland",
                                "label": "Country",
                            },
                            {
                                "column": "C",
                                "row": row_number,
                                "expected_value": sex,
                                "label": "Sex",
                            },
                            {
                                "column": "E",
                                "row": row_number,
                                "expected_value": residence,
                                "label": "Residence Type Indicator",
                            },
                        ],
                    }
                )
            assert len(rows) == 21 and rows[-1]["label"] == "85 and over", rows[-1][
                "label"
            ]
            slug_sex = sex.lower().replace(" ", "_")
            slug_res = residence.lower().replace(" ", "_")
            record_set_id = f"nrs.census2022_uv101a_scotland.{slug_sex}.{slug_res}"
            record_sets.append(
                {
                    "record_set_id": record_set_id,
                    "provenance_class": "census",
                    "record_set_spec_id": f"{record_set_id}.v1",
                    "source_record_id_prefix": record_set_id,
                    "sheet_name": NRS_FILE,
                    **census_period(
                        2022,
                        "2022-03-20",
                        "Census day 20 March 2022. Usual residents; students at term-time address.",
                    ),
                    "geography_id": "S92000003",
                    "geography_level": "country",
                    "geography_name": "Scotland",
                    "geography_vintage": "current",
                    "entity": "person",
                    "entity_role": "usual_resident",
                    "domain": "population",
                    "groupby_dimension": "Age",
                    "shared_filters": {
                        "Sex": sex,
                        "Residence Type Indicator": residence,
                    },
                    "shared_constraints": [
                        constraint("Sex", sex, "Sex"),
                        constraint(
                            "Residence Type Indicator",
                            residence,
                            "Residence Type Indicator",
                        ),
                    ],
                    "measures": [
                        {
                            "measure_id": "nrs_census2022_residents",
                            "label": "Usual residents",
                            "ordinal": 0,
                            "column": letters["Count"],
                            "source_column_id": "Count",
                            "expected_column_header_row": 1,
                            "expected_column_header": "Count",
                            "concept": "nrs.census2022_residents",
                            "concept_evidence_notes": (
                                "Publisher disclosure-controlled counts: cells need not add to "
                                "totals. Census date 20 March 2022, students at term-time address."
                            ),
                            "unit": "count",
                            "aggregation": "sum",
                            "expected_cell_type": "number",
                        }
                    ],
                    "rows": rows,
                }
            )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "nrs-census2022-uv101a-scotland",
        "label": "NRS Scotland's Census 2022 UV101a residence type by sex by age: Scotland",
        "dimension_labels": {
            "Sex": "Sex",
            "Age": "Age",
            "Residence Type Indicator": "Residence Type Indicator",
        },
        "artifact": {
            "source_name": "nrs",
            "source_table": "NRS Scotland's Census 2022 UV101a residence type by sex by age: Scotland",
            "resource_package": "db",
            "resource_directory": f"data/{NRS_DIR}",
            "manifest": "manifest.yaml",
            "vintage": "census_2022_uv101a_2024_release",
            "extracted_at": "2026-10-15",
            "extraction_method": "Publisher artifact parsed without modifying values",
            "parser": "delimited_text_full_rows",
            "artifact_year": 2022,
            "sheet_name": NRS_FILE,
            "header_row": 11,
        },
        "record_sets": record_sets,
    }
    write_package(ROOT / "packages" / NRS_DIR, payload, NRS_HEADER)


NRS_HEADER = """\
# Scotland's Census 2022 UV101a (usual residents by sex, age and residence type) at Scotland
# level, for PolicyEngine/chronicle#358 item 2: the same SuperWEB2 export layout as the
# council-area and UK-constituency UV101a packages, from the UK Data Service mirror of NRS's
# outputs. Census day 20 March 2022.
#
# NRS publishes nothing finer than '85 and over' by residence type. UV101a (20 age bands) and
# UV101b (six bands) are the only published tables crossing residence type with age; UV102a
# (single year by sex) also stops at 85 and over, and UV103 (single year to 100 and over) has
# no sex or residence type. A residence-type split of 85-89 from 90 and over would need an
# export from NRS's flexible table builder, which requires accepting its user agreement and
# has not been made. This package therefore carries UV101a's 20 bands and totals, by sex and
# residence type, as published (cells are perturbed and need not add up).
"""


if __name__ == "__main__":
    for population_type in ("UR_HH", "UR_CE"):
        for area_type in ("ctry", "rgn"):
            for by_sex in (True, False):
                build_ons(population_type, area_type, by_sex)
    for geo in ("ni", "lgd14", "parlcon24"):
        for by_sex in (True, False):
            build_nisra(geo, by_sex)
    build_nrs()
