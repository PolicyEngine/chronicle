"""Generate ACS 2024 1-year household-type packages from pinned publisher API bytes.

Run ``python -m chronicle.sources.census_acs1_household_type [--check]``. It
declares every estimate and margin-of-error cell of B11001 (household type,
including living alone) and B11003 (family type by presence and age of own
children under 18) for the United States, and for each state, DC and Puerto
Rico, from the Census Bureau's API responses as fetched. It never fetches,
sums, imputes, reconciles, or aligns values to a consumer year.

Both tables name household types with the ``household_type`` values the ACS
5-year county package uses for B11001 (``all``, ``family``, ``nonfamily``), so
a consumer reads one vocabulary across them. B11003's universe is families,
one per family household, so its total is ``household_type`` ``family`` and its
family types are the B11001 family-household types.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from openpyxl.utils import get_column_letter
import yaml

from chronicle.dimension_labels import canonical_value_label
from chronicle.epoch import schema_id
from chronicle.yaml_io import safe_load

ROOT = Path(__file__).resolve().parents[2]
YEAR = 2024
TABLES = ("B11001", "B11003")
GEOGRAPHIES = ("national", "state")
GENERATED_BY = "python -m chronicle.sources.census_acs1_household_type"
#: The 50 states, DC and Puerto Rico, as the ACS 1-year state endpoint returns them.
STATE_ROW_COUNT = 52
DISTRICT_OF_COLUMBIA_FIPS = "11"
PUERTO_RICO_FIPS = "72"

TABLE_METADATA = {
    "B11001": (
        "Household type (including living alone)",
        "household",
        "household_type",
        "household_count",
    ),
    "B11003": (
        "Family type by presence and age of own children under 18 years",
        "household",
        "family_type",
        "family_count",
    ),
}

#: Each ``household_type`` value with the wording the ACS 5-year county
#: package gives it, where that package emits it, and Census's otherwise.
HOUSEHOLD_TYPE_LABELS = {
    "all": "Total",
    "family": "Family households",
    "married_couple_family": "Married-couple family",
    "other_family": "Other family",
    "male_householder_no_spouse": "Male householder, no spouse present",
    "female_householder_no_spouse": "Female householder, no spouse present",
    "nonfamily": "Nonfamily households",
    "householder_living_alone": "Householder living alone",
    "householder_not_living_alone": "Householder not living alone",
}
OWN_CHILDREN_LABELS = {
    "all": "All families",
    "with_own_children_under_18": "With own children of the householder under 18 years",
    "own_children_under_6_only": "Under 6 years only",
    "own_children_under_6_and_6_to_17": "Under 6 years and 6 to 17 years",
    "own_children_6_to_17_only": "6 to 17 years only",
    "no_own_children_under_18": "No own children of the householder under 18 years",
}
DIMENSION_LABELS = {
    "household_type": "Household type",
    "own_children": "Own children of the householder under 18",
}

#: B11001 cells in publisher order: (variable index, household_type).
B11001_CELLS = (
    (1, "all"),
    (2, "family"),
    (3, "married_couple_family"),
    (4, "other_family"),
    (5, "male_householder_no_spouse"),
    (6, "female_householder_no_spouse"),
    (7, "nonfamily"),
    (8, "householder_living_alone"),
    (9, "householder_not_living_alone"),
)
#: B11003 cells in publisher order: (variable index, household_type, own_children).
B11003_CELLS = (
    (1, "family", "all"),
    (2, "married_couple_family", "all"),
    (3, "married_couple_family", "with_own_children_under_18"),
    (4, "married_couple_family", "own_children_under_6_only"),
    (5, "married_couple_family", "own_children_under_6_and_6_to_17"),
    (6, "married_couple_family", "own_children_6_to_17_only"),
    (7, "married_couple_family", "no_own_children_under_18"),
    (8, "other_family", "all"),
    (9, "male_householder_no_spouse", "all"),
    (10, "male_householder_no_spouse", "with_own_children_under_18"),
    (11, "male_householder_no_spouse", "own_children_under_6_only"),
    (12, "male_householder_no_spouse", "own_children_under_6_and_6_to_17"),
    (13, "male_householder_no_spouse", "own_children_6_to_17_only"),
    (14, "male_householder_no_spouse", "no_own_children_under_18"),
    (15, "female_householder_no_spouse", "all"),
    (16, "female_householder_no_spouse", "with_own_children_under_18"),
    (17, "female_householder_no_spouse", "own_children_under_6_only"),
    (18, "female_householder_no_spouse", "own_children_under_6_and_6_to_17"),
    (19, "female_householder_no_spouse", "own_children_6_to_17_only"),
    (20, "female_householder_no_spouse", "no_own_children_under_18"),
)


def cells(table: str) -> list[tuple[int, dict[str, str], str]]:
    """Each publisher cell's variable index, category filters and label."""
    if table == "B11001":
        return [
            (index, {"household_type": value}, HOUSEHOLD_TYPE_LABELS[value])
            for index, value in B11001_CELLS
        ]
    if table == "B11003":
        result = []
        for index, household_type, own_children in B11003_CELLS:
            label = HOUSEHOLD_TYPE_LABELS[household_type]
            if own_children != "all":
                label = f"{label}: {OWN_CHILDREN_LABELS[own_children]}"
            result.append(
                (
                    index,
                    {"household_type": household_type, "own_children": own_children},
                    label,
                )
            )
        return result
    raise ValueError(f"Unsupported ACS household table: {table}")


def _measure(
    table: str,
    index: int,
    categories: dict[str, str],
    label: str,
    suffix: str,
    columns: dict[str, str],
) -> dict[str, Any]:
    title, _entity, _domain, concept = TABLE_METADATA[table]
    variable = f"{table}_{index:03d}{suffix}"
    is_moe = suffix == "M"
    statistic = "margin_of_error" if is_moe else "estimate"
    filters: dict[str, str] = {"statistic": statistic, **categories}
    constraints = [
        {
            "variable": "statistic",
            "operator": "==",
            "value": statistic,
            "label": "Statistic",
        }
    ]
    for dimension, value in categories.items():
        if value != "all":
            constraints.append(
                {
                    "variable": dimension,
                    "operator": "==",
                    "value": value,
                    "label": DIMENSION_LABELS[dimension],
                }
            )
    return {
        "measure_id": variable,
        "label": f"{label}: {'Margin of error' if is_moe else 'Estimate'}",
        "ordinal": (index - 1) * 2 + int(is_moe),
        "column": columns[variable],
        "source_column_id": variable,
        # In a wide publisher table the categories belong to the guarded
        # variable column, rather than to the geography row.
        "source_column_dimensions": dict(filters),
        "expected_column_header_row": 1,
        "expected_column_header": variable,
        "concept": f"census_acs.{concept}{'_margin_of_error' if is_moe else ''}",
        "source_concept": f"{title}: {label} ({statistic})",
        "concept_relation": "source_label",
        "concept_evidence_url": (
            f"https://api.census.gov/data/{YEAR}/acs/acs1/groups/{table}.html"
        ),
        "concept_evidence_notes": (
            "Publisher margin of error at the ACS 90% confidence level. "
            "Each MOE selects one publisher cell with scale 1; "
            "MOEs must not be added across categories or geographies."
            if is_moe
            else "Publisher estimate, without period alignment or adjustment."
        ),
        "unit": "count",
        "aggregation": "sum",
        "expected_cell_type": "number",
        "filters": filters,
        "constraints": constraints,
    }


def directory(table: str, geography: str) -> str:
    """The package's directory name under db/data/census and packages/census."""
    return f"acs1_{table.lower()}_{geography}_{YEAR}"


def package_id(table: str, geography: str) -> str:
    """The package's stable id."""
    return f"census-acs1-{table.lower()}-{geography}-{YEAR}"


def _geography_key(geography: str) -> str:
    return "us" if geography == "national" else "state"


def _expected_geo_id(geography: str, source: dict[str, Any]) -> str:
    if geography == "national":
        return "0100000US"
    return f"0400000US{source['state']}"


def build_package(table: str, geography: str, root: Path = ROOT) -> dict[str, Any]:
    """Declare every numeric E/M cell of one table at one geography level."""
    if table not in TABLES:
        raise ValueError(f"Unsupported ACS household table: {table}")
    if geography not in GEOGRAPHIES:
        raise ValueError(f"Unsupported ACS geography: {geography}")
    data_dir = root / "db/data/census" / directory(table, geography)
    manifest = safe_load((data_dir / "manifest.yaml").read_text())
    artifact = manifest["files"][YEAR]
    content = (data_dir / artifact["filename"]).read_bytes()
    if hashlib.sha256(content).hexdigest() != artifact["sha256"]:
        raise ValueError(f"Publisher SHA-256 mismatch for {table} {geography}")
    if len(content) != artifact["size_bytes"]:
        raise ValueError(f"Publisher size mismatch for {table} {geography}")
    raw_table = json.loads(content)
    raw_header = raw_table[0]
    # get=NAME,group(...) repeats NAME. The row parser keeps its first column
    # position and the last identical value; guard that equivalence explicitly.
    header = list(dict.fromkeys(raw_header))
    columns = {name: get_column_letter(i) for i, name in enumerate(header, start=1)}
    table_cells = cells(table)
    variables = [
        f"{table}_{index:03d}{suffix}"
        for index, _, _ in table_cells
        for suffix in ("E", "M")
    ]
    required = {"GEO_ID", "NAME", _geography_key(geography)}
    required.update(variables)
    required.update(variable + "A" for variable in variables)
    missing = required - set(header)
    if missing:
        raise ValueError(f"Missing source columns in {table}: {sorted(missing)}")
    measures = [
        _measure(table, index, categories, label, suffix, columns)
        for index, categories, label in table_cells
        for suffix in ("E", "M")
    ]

    source_rows = []
    for raw_row in raw_table[1:]:
        if len(raw_row) != len(raw_header):
            raise ValueError(f"Ragged source row in {table}")
        source = dict(zip(raw_header, raw_row, strict=True))
        if any(
            source[name] != value
            for name, value in zip(raw_header, raw_row, strict=True)
        ):
            raise ValueError(f"Conflicting duplicate source columns in {table}")
        if source["GEO_ID"] != _expected_geo_id(geography, source):
            raise ValueError(
                f"GEO_ID does not match its geography in {table}: {source['GEO_ID']}"
            )
        source_rows.append(source)
    source_rows.sort(key=lambda row: row["GEO_ID"])
    geo_ids = [row["GEO_ID"] for row in source_rows]
    if len(geo_ids) != len(set(geo_ids)):
        raise ValueError(f"Duplicate geography rows in {table} {geography}")
    if geography == "national" and geo_ids != ["0100000US"]:
        raise ValueError(f"Expected one United States row in {table}")
    if geography == "state" and (
        len(geo_ids) != STATE_ROW_COUNT
        or f"0400000US{DISTRICT_OF_COLUMBIA_FIPS}" not in geo_ids
        or f"0400000US{PUERTO_RICO_FIPS}" not in geo_ids
    ):
        raise ValueError(
            f"Expected {STATE_ROW_COUNT} state rows (50 states, DC and Puerto Rico) "
            f"in {table}"
        )

    rows = []
    level = "country" if geography == "national" else "state"
    for ordinal, source in enumerate(source_rows):
        for variable in variables:
            raw = source[variable]
            annotation = source[variable + "A"]
            # These tables publish every cell for the nation and the states.
            # A future vintage's suppression code or annotation must be added
            # here on purpose, so an unknown encoding fails closed.
            if raw is None or int(raw) < 0 or annotation is not None:
                raise ValueError(
                    f"Unknown suppression in {table} {source['GEO_ID']}: "
                    f"{variable}={raw!r} annotation={annotation!r}"
                )
        rows.append(
            {
                "value_id": "us" if geography == "national" else source["state"],
                "label": source["NAME"],
                "ordinal": ordinal,
                "row_number": ordinal + 2,
                "geography_id": source["GEO_ID"],
                "geography_level": level,
                "geography_name": source["NAME"],
                "geography_vintage": str(YEAR),
                "expected_row_header_column": columns["NAME"],
                "expected_row_header": source["NAME"],
                "guard_cells": [
                    {
                        "column": columns["GEO_ID"],
                        "expected_value": source["GEO_ID"],
                        "label": "GEO_ID",
                    }
                ],
                "table_record_kind": "total",
            }
        )

    title, entity, domain, _concept = TABLE_METADATA[table]
    groupby = "census_acs.nation" if geography == "national" else "census_acs.state"
    record_set_id = f"census_acs.acs1_{YEAR}.{table.lower()}.{geography}"
    record_set = {
        "record_set_id": record_set_id,
        "provenance_class": "survey_aggregate",
        "survey_instrument": "ACS 1-year",
        "record_set_spec_id": f"census_acs.acs1.{table.lower()}.{geography}.v1",
        "source_record_id_prefix": record_set_id,
        "sheet_name": "api_response",
        "period_type": "calendar_year",
        "period": YEAR,
        "period_coverage": {
            "start_date": f"{YEAR}-01-01",
            "end_date": f"{YEAR}-12-31",
            "basis": "survey_reference",
            "source_period_label": f"{YEAR} ACS 1-year",
            "notes": f"Single-year estimate from interviews throughout {YEAR}. "
            "Household and family type describe the household at the interview; "
            "Puerto Rico's estimate is separate from the United States total.",
        },
        "geography_id": "0100000US",
        "geography_level": "country",
        "geography_name": "United States",
        "geography_vintage": str(YEAR),
        "entity": entity,
        "domain": domain,
        "groupby_dimension": groupby,
        "rows": rows,
        "measures": measures,
    }
    dimensions = {
        groupby: "Nation" if geography == "national" else "State",
        "statistic": "Statistic",
    }
    values: dict[str, dict[str, str]] = {
        "statistic": {"estimate": "Estimate", "margin_of_error": "Margin of error"}
    }
    category_labels = {
        "household_type": HOUSEHOLD_TYPE_LABELS,
        "own_children": OWN_CHILDREN_LABELS,
    }
    for _index, categories, _label in table_cells:
        for dimension, value in categories.items():
            dimensions[dimension] = DIMENSION_LABELS[dimension]
            # A value Chronicle's label register lists is declared with the
            # register's label (chronicle#376); Census's own text stays in the
            # measure labels and the source cells.
            values.setdefault(dimension, {})[value] = (
                canonical_value_label(dimension, value)
                or category_labels[dimension][value]
            )
    scope = (
        "the United States row"
        if geography == "national"
        else "all 52 rows (50 states, DC and Puerto Rico)"
    )
    return {
        "schema_version": schema_id("source_package"),
        "package_id": package_id(table, geography),
        "label": f"Census ACS {YEAR} 1-year {geography} {table}: {title}",
        "generated_by": GENERATED_BY,
        "dimension_labels": dimensions,
        "dimension_value_labels": values,
        "source_geography_count": len(source_rows),
        "artifact": {
            "source_name": "census_acs",
            "source_table": f"ACS {YEAR} 1-year {table}: {title}",
            "resource_package": "db",
            "resource_directory": f"data/census/{directory(table, geography)}",
            "manifest": "manifest.yaml",
            "vintage": f"acs_1_year_{YEAR}",
            "extracted_at": "2026-11-08",
            "extraction_method": "Full publisher JSON row parse with guarded E/M source "
            f"cells; {scope} retained; the generator fails on any suppression code "
            "or annotation instead of emitting it",
            "parser": "json_table_full_rows",
            "sheet_name": "api_response",
            "selected_rows": [{"GEO_ID": row["GEO_ID"]} for row in source_rows],
        },
        "record_sets": [record_set],
    }


def render_package(table: str, geography: str, root: Path = ROOT) -> str:
    """Render the deterministic declarative package with explicit YAML."""

    class Dumper(yaml.SafeDumper):
        def ignore_aliases(self, data):
            return True

    return f"# Generated by {GENERATED_BY}.\n" + yaml.dump(
        build_package(table, geography, root),
        Dumper=Dumper,
        sort_keys=False,
        width=88,
        allow_unicode=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--table", choices=TABLES, action="append")
    parser.add_argument("--geography", choices=GEOGRAPHIES, action="append")
    args = parser.parse_args()
    stale = []
    for table in args.table or TABLES:
        for geography in args.geography or GEOGRAPHIES:
            output = (
                ROOT
                / "packages/census"
                / directory(table, geography)
                / "source_package.yaml"
            )
            rendered = render_package(table, geography)
            if args.check:
                if not output.exists() or output.read_text() != rendered:
                    stale.append(str(output.relative_to(ROOT)))
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"{table} {geography}: {'checked' if args.check else 'generated'}")
    if stale:
        parser.exit(1, f"Stale generated packages: {', '.join(stale)}\n")


if __name__ == "__main__":
    main()
