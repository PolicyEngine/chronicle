"""Generate county ACS 2020–2024 packages from pinned publisher API bytes.

Run ``python -m chronicle.sources.census_acs5_county [--check]``. This only
declares guarded source cells, publisher categories and reference periods. It
never fetches, sums, imputes, reconciles, or aligns values to a consumer year.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
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
TABLES = ("B01003", "B11001", "B19001", "B19013", "B19025", "B19051", "B19061")
GENERATED_BY = "python -m chronicle.sources.census_acs5_county"

# None denotes an unbounded endpoint. Household income can be negative, so
# Census's first bracket has no finite lower bound. Upper bounds are exclusive.
INCOME_BRACKETS = (
    (None, 10_000),
    (10_000, 15_000),
    (15_000, 20_000),
    (20_000, 25_000),
    (25_000, 30_000),
    (30_000, 35_000),
    (35_000, 40_000),
    (40_000, 45_000),
    (45_000, 50_000),
    (50_000, 60_000),
    (60_000, 75_000),
    (75_000, 100_000),
    (100_000, 125_000),
    (125_000, 150_000),
    (150_000, 200_000),
    (200_000, None),
)

TABLE_METADATA = {
    "B01003": ("Total population", "person", "population", "person_count", "count"),
    "B11001": (
        "Household type (including living alone)",
        "household",
        "household_type",
        "household_count",
        "count",
    ),
    "B19001": (
        "Household income in the past 12 months (in 2024 inflation-adjusted dollars)",
        "household",
        "household_income",
        "household_count",
        "count",
    ),
    "B19013": (
        "Median household income in the past 12 months (in 2024 inflation-adjusted dollars)",
        "household",
        "household_income",
        "median_household_income",
        "USD",
    ),
    "B19025": (
        "Aggregate household income in the past 12 months (in 2024 inflation-adjusted dollars)",
        "household",
        "household_income",
        "aggregate_household_income",
        "USD",
    ),
    "B19051": (
        "Earnings in the past 12 months for households",
        "household",
        "household_earnings",
        "household_count",
        "count",
    ),
    "B19061": (
        "Aggregate earnings in the past 12 months (in 2024 inflation-adjusted dollars) for households",
        "household",
        "household_earnings",
        "aggregate_household_earnings",
        "USD",
    ),
}

# Publisher code/annotation pairs seen in this vintage. Unknown negative
# encodings fail closed. These are preserved as source cells, never numbers.
SENTINELS = {
    ("B01003_001M", -555555555): "*****",
    ("B19013_001E", -666666666): "-",
    ("B19013_001M", -222222222): "**",
}


def _categories(table: str) -> list[tuple[int, str, str]]:
    if table == "B11001":
        return [
            (1, "all", "Total"),
            (2, "family", "Family households"),
            (7, "nonfamily", "Nonfamily households"),
        ]
    if table == "B19051":
        return [
            (1, "all", "Total"),
            (2, "with_earnings", "With earnings"),
            (3, "without_earnings", "No earnings"),
        ]
    if table == "B19001":
        categories = [(1, "all", "Total")]
        for index, (lower, upper) in enumerate(INCOME_BRACKETS, start=2):
            if lower is None:
                value_id, label = "under_10000", "Less than $10,000"
            elif upper is None:
                value_id, label = "200000_plus", "$200,000 or more"
            else:
                value_id = f"{lower}_to_{upper - 1}"
                label = f"${lower:,} to ${upper - 1:,}"
            categories.append((index, value_id, label))
        return categories
    return [(1, "all", "Total")]


def _measure(
    table: str,
    index: int,
    category: str,
    label: str,
    suffix: str,
    columns: dict[str, str],
) -> dict[str, Any]:
    title, _entity, _domain, concept, unit = TABLE_METADATA[table]
    variable = f"{table}_{index:03d}{suffix}"
    is_moe = suffix == "M"
    statistic = "margin_of_error" if is_moe else "estimate"
    filters: dict[str, str] = {"statistic": statistic}
    constraints = [
        {
            "variable": "statistic",
            "operator": "==",
            "value": statistic,
            "label": "Statistic",
        }
    ]
    dimension = {
        "B11001": "household_type",
        "B19001": "income_range",
        "B19051": "earnings_status",
    }.get(table)
    if dimension:
        filters[dimension] = category
        if category != "all" and dimension != "income_range":
            constraints.append(
                {
                    "variable": dimension,
                    "operator": "==",
                    "value": category,
                    "label": {
                        "household_type": "Household type",
                        "earnings_status": "Earnings status",
                    }[dimension],
                }
            )
    if table == "B19001" and index != 1:
        lower, upper = INCOME_BRACKETS[index - 2]
        for operator, bound in ((">=", lower), ("<", upper)):
            if bound is not None:
                constraints.append(
                    {
                        "variable": "household_income",
                        "operator": operator,
                        "value": bound,
                        "unit": "USD",
                        "label": "Household income in 2024 dollars",
                    }
                )
    # In a wide publisher table these categories and endpoints belong to the
    # guarded variable column, rather than to the county row.
    column_dimensions: dict[str, Any] = dict(filters)
    for constraint in constraints:
        if constraint["variable"] == "household_income":
            bound = "lower_bound" if constraint["operator"] == ">=" else "upper_bound"
            column_dimensions[f"household_income_{bound}"] = constraint["value"]
    return {
        "measure_id": variable,
        "label": f"{label}: {'Margin of error' if is_moe else 'Estimate'}",
        "ordinal": (index - 1) * 2 + int(is_moe),
        "column": columns[variable],
        "source_column_id": variable,
        "source_column_dimensions": column_dimensions,
        "expected_column_header_row": 1,
        "expected_column_header": variable,
        "concept": f"census_acs.{concept}{'_margin_of_error' if is_moe else ''}",
        "source_concept": f"{title}: {label} ({statistic})",
        "concept_relation": "source_label",
        "concept_evidence_url": f"https://api.census.gov/data/2024/acs/acs5/groups/{table}.html",
        "concept_evidence_notes": (
            "Publisher margin of error at the ACS 90% confidence level. "
            "Each MOE selects one publisher cell with scale 1; "
            "MOEs must not be added across categories or counties."
            if is_moe
            else "Publisher estimate, without period alignment or adjustment."
        ),
        "unit": unit,
        "aggregation": "median" if table == "B19013" else "sum",
        "expected_cell_type": "number",
        "filters": filters,
        "constraints": constraints,
    }


def build_package(table: str, root: Path = ROOT) -> dict[str, Any]:
    """Declare numeric E/M cells; retain unavailable values in raw lineage only."""
    if table not in TABLES:
        raise ValueError(f"Unsupported ACS county table: {table}")
    directory = f"acs5_{table.lower()}_county_2024"
    data_dir = root / "db/data/census" / directory
    manifest = safe_load((data_dir / "manifest.yaml").read_text())
    artifact = manifest["files"][2024]
    content = (data_dir / artifact["filename"]).read_bytes()
    if hashlib.sha256(content).hexdigest() != artifact["sha256"]:
        raise ValueError(f"Publisher SHA-256 mismatch for {table}")
    if len(content) != artifact["size_bytes"]:
        raise ValueError(f"Publisher size mismatch for {table}")
    raw_table = json.loads(content)
    raw_header = raw_table[0]
    # get=NAME,group(...) repeats NAME. The row parser keeps its first column
    # position and the last identical value; guard that equivalence explicitly.
    header = list(dict.fromkeys(raw_header))
    columns = {name: get_column_letter(i) for i, name in enumerate(header, start=1)}
    variables = [
        f"{table}_{index:03d}{suffix}"
        for index, category, label in _categories(table)
        for suffix in ("E", "M")
    ]
    required = {"GEO_ID", "NAME", "state", "county"}
    required.update(variables)
    required.update(variable + "A" for variable in variables)
    missing = required - set(header)
    if missing:
        raise ValueError(f"Missing source columns in {table}: {sorted(missing)}")
    measures = [
        _measure(table, index, category, label, suffix, columns)
        for index, category, label in _categories(table)
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
        geo_id = f"0500000US{source['state']}{source['county']}"
        if source["GEO_ID"] != geo_id:
            raise ValueError(f"GEO_ID does not match county FIPS in {table}: {source}")
        source_rows.append(source)
    source_rows.sort(key=lambda row: row["GEO_ID"])
    geo_ids = [row["GEO_ID"] for row in source_rows]
    pr_count = sum(row["state"] == "72" for row in source_rows)
    if (
        len(geo_ids) != len(set(geo_ids))
        or len(geo_ids) - pr_count != 3144
        or pr_count != 78
    ):
        raise ValueError(
            "Expected 3,222 unique county rows (3,144 non-PR counties and "
            f"78 Puerto Rico municipios) in {table}"
        )
    if {geo for geo in geo_ids if geo.startswith("0500000US09")} != {
        f"0500000US09{code}" for code in range(110, 200, 10)
    }:
        raise ValueError(f"Expected nine Connecticut planning regions in {table}")

    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    unavailable = []
    for ordinal, source in enumerate(source_rows):
        available = []
        for measure in measures:
            variable = measure["source_column_id"]
            value = int(source[variable])
            annotation = source[variable + "A"]
            if value < 0:
                if (variable, value) not in SENTINELS or annotation != SENTINELS[
                    (variable, value)
                ]:
                    raise ValueError(
                        f"Unknown negative encoding in {table}: {variable}={value}"
                    )
                unavailable.append(
                    {
                        "geography_id": source["GEO_ID"],
                        "geography_name": source["NAME"],
                        "source_column_id": variable,
                        "publisher_code": value,
                        "annotation": annotation,
                    }
                )
            elif annotation is not None:
                raise ValueError(f"Unexpected annotation for {variable}: {annotation}")
            else:
                available.append(variable)
        groups[tuple(available)].append(
            {
                "value_id": source["GEO_ID"].removeprefix("0500000US"),
                "label": source["NAME"],
                "ordinal": ordinal,
                "row_number": ordinal + 2,
                "geography_id": source["GEO_ID"],
                "geography_level": "county",
                "geography_name": source["NAME"],
                "geography_vintage": "2024",
                "expected_row_header_column": columns["NAME"],
                "expected_row_header": source["NAME"],
                "guard_cells": [
                    {
                        "column": columns["GEO_ID"],
                        "expected_value": source["GEO_ID"],
                        "label": "County GEO_ID",
                    }
                ],
                "table_record_kind": "total",
            }
        )

    title, entity, domain, _concept, _unit = TABLE_METADATA[table]
    record_sets = []
    for group, (available, rows) in enumerate(sorted(groups.items())):
        if not available:
            continue  # Suppressed row remains in source rows/cells and metadata.
        record_set_id = (
            f"census_acs.acs5_2020_2024.{table.lower()}.county.group_{group}"
        )
        record_sets.append(
            {
                "record_set_id": record_set_id,
                "provenance_class": "survey_aggregate",
                "survey_instrument": "ACS 5-year",
                "record_set_spec_id": f"census_acs.acs5.{table.lower()}.county.v1",
                "source_record_id_prefix": record_set_id,
                "sheet_name": "api_response",
                "period_type": "calendar_year",
                "period": 2024,
                "period_coverage": {
                    "start_date": "2020-01-01",
                    "end_date": "2024-12-31",
                    "basis": "survey_reference",
                    "source_period_label": "2020–2024 ACS 5-year",
                    "notes": "Pooled five-year estimate, not a single-year 2024 observation. "
                    "Income and earnings refer to the past 12 months at interview; "
                    "published monetary values are in 2024 inflation-adjusted dollars.",
                },
                "geography_id": "0100000US",
                "geography_level": "country",
                "geography_name": "United States",
                "geography_vintage": "2024",
                "entity": entity,
                "domain": domain,
                "groupby_dimension": "census_acs.county",
                "rows": rows,
                "measures": [
                    measure
                    for measure in measures
                    if measure["source_column_id"] in available
                ],
            }
        )
    dimensions = {"census_acs.county": "County", "statistic": "Statistic"}
    values = {
        "statistic": {"estimate": "Estimate", "margin_of_error": "Margin of error"}
    }
    category_dimension = {
        "B11001": "household_type",
        "B19001": "income_range",
        "B19051": "earnings_status",
    }.get(table)
    if category_dimension:
        dimensions[category_dimension] = {
            "B11001": "Household type",
            "B19001": "Income range",
            "B19051": "Earnings status",
        }[table]
        # A value Chronicle's label register lists is declared with the
        # register's label (chronicle#376): B19001's "Total" is income_range
        # all, which the IRS SOI packages call "All income ranges". Census's
        # own text stays in the measure labels and the source cells.
        values[category_dimension] = {
            category: canonical_value_label(category_dimension, category) or label
            for _, category, label in _categories(table)
        }
    payload = {
        "schema_version": schema_id("source_package"),
        "package_id": f"census-acs5-{table.lower()}-county-2024",
        "label": f"Census ACS 2020–2024 5-year county {table}: {title}",
        "generated_by": GENERATED_BY,
        "dimension_labels": dimensions,
        "dimension_value_labels": values,
        "source_county_count": len(source_rows),
        "unavailable_cells": unavailable,
        "artifact": {
            "source_name": "census_acs",
            "source_table": f"ACS 2020–2024 5-year {table}: {title}",
            "resource_package": "db",
            "resource_directory": f"data/census/{directory}",
            "manifest": "manifest.yaml",
            "vintage": "acs_5_year_2020_2024",
            "extracted_at": "2026-10-24",
            "extraction_method": "Full publisher JSON row parse with guarded county E/M source cells; "
            "all 3,222 county rows retained, including 78 Puerto Rico municipios; "
            "sentinel codes and annotations retained in raw rows and unavailable_cells, "
            "never emitted as numeric facts",
            "parser": "json_table_full_rows",
            "sheet_name": "api_response",
            "selected_rows": [{"GEO_ID": row["GEO_ID"]} for row in source_rows],
        },
        "record_sets": record_sets,
    }
    if table == "B19001":
        payload["income_brackets"] = [
            {
                "variable_id": f"B19001_{index:03d}E",
                "lower_bound": lower,
                "upper_bound": upper,
                "lower_inclusive": lower is not None,
                "upper_inclusive": False,
                "unit": "USD",
                "dollar_year": 2024,
            }
            for index, (lower, upper) in enumerate(INCOME_BRACKETS, start=2)
        ]
    return payload


def render_package(table: str, root: Path = ROOT) -> str:
    """Render the deterministic declarative package with explicit YAML."""

    class Dumper(yaml.SafeDumper):
        def ignore_aliases(self, data):
            return True

    return f"# Generated by {GENERATED_BY}.\n" + yaml.dump(
        build_package(table, root),
        Dumper=Dumper,
        sort_keys=False,
        width=88,
        allow_unicode=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--table", choices=TABLES, action="append")
    args = parser.parse_args()
    stale = []
    for table in args.table or TABLES:
        output = (
            ROOT
            / "packages/census"
            / f"acs5_{table.lower()}_county_2024/source_package.yaml"
        )
        rendered = render_package(table)
        if args.check:
            if not output.exists() or output.read_text() != rendered:
                stale.append(str(output.relative_to(ROOT)))
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"{table}: {'checked' if args.check else 'generated'}")
    if stale:
        parser.exit(1, f"Stale generated packages: {', '.join(stale)}\n")


if __name__ == "__main__":
    main()
