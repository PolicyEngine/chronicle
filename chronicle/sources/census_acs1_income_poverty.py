"""Generate ACS 2024 1-year check-table packages from pinned publisher API bytes.

Run ``python -m chronicle.sources.census_acs1_check_tables [--check]``. It
declares the estimate and margin-of-error cells of B19013 (median household
income) and of S1701 (poverty status: the population for whom poverty status
is determined and the population below the poverty level, for all ages, under
18, 18 to 64 and 65 and over) for each state, DC and Puerto Rico, and for each
congressional district of the 119th Congress, DC's delegate district and Puerto
Rico's resident commissioner district (chronicle#447). Microcosm reads them as
checks of its district build (PolicyEngine/microcosm#1673). It never fetches,
sums, imputes, reconciles, or aligns values to a consumer year.

B19013 takes the concept, unit and aggregation of the ACS 5-year county
package's B19013. S1701's universe is the population for whom poverty status is
determined, not the resident population, so its counts carry their own concept;
poverty status and the age band are filters, and the age bounds constraints.
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
TABLES = ("B19013", "S1701")
GEOGRAPHIES = ("state", "district")
GENERATED_BY = "python -m chronicle.sources.census_acs1_check_tables"
DISTRICT_OF_COLUMBIA_FIPS = "11"
PUERTO_RICO_FIPS = "72"
#: The 50 states' FIPS codes.
STATE_FIPS = frozenset(
    (
        "01", "02", "04", "05", "06", "08", "09", "10", "12", "13",
        "15", "16", "17", "18", "19", "20", "21", "22", "23", "24",
        "25", "26", "27", "28", "29", "30", "31", "32", "33", "34",
        "35", "36", "37", "38", "39", "40", "41", "42", "44", "45",
        "46", "47", "48", "49", "50", "51", "53", "54", "55", "56",
    )
)  # fmt: skip
#: The state rows the ACS 1-year endpoints return: 50 states, DC, Puerto Rico.
STATE_ROW_FIPS = STATE_FIPS | {DISTRICT_OF_COLUMBIA_FIPS, PUERTO_RICO_FIPS}
STATE_ROW_COUNT = len(STATE_ROW_FIPS)
#: The 435 districts of the 119th Congress, DC's delegate district and Puerto
#: Rico's resident commissioner district (code 98 for both).
DISTRICT_ROW_COUNT = 437
NON_VOTING_DISTRICT = "98"
AT_LARGE_DISTRICT = "00"
DISTRICT_VINTAGE = "119th_congress"
GEOGRAPHY_KEYS = {"state": "state", "district": "congressional district"}
GEOGRAPHY_DIMENSIONS = {
    "state": ("census_acs.state", "State"),
    "district": ("census_acs.congressional_district", "Congressional district"),
}
GEOGRAPHY_WORDING = {"state": "state", "district": "congressional district"}
GEOGRAPHY_LEVELS = {"state": "state", "district": "congressional_district"}

#: table -> (title, entity, domain, API dataset path, API groups page)
TABLE_METADATA = {
    "B19013": (
        "Median household income in the past 12 months (in 2024 inflation-adjusted "
        "dollars)",
        "household",
        "household_income",
        "acs/acs1",
        f"https://api.census.gov/data/{YEAR}/acs/acs1/groups/B19013.html",
    ),
    "S1701": (
        "Poverty status in the past 12 months",
        "person",
        "poverty_status",
        "acs/acs1/subject",
        f"https://api.census.gov/data/{YEAR}/acs/acs1/subject/groups/S1701.html",
    ),
}
TABLE_PERIOD_NOTES = {
    "B19013": "Household income refers to the past 12 months at the interview, "
    "in 2024 inflation-adjusted dollars",
    "S1701": "Poverty status compares the past 12 months' family or personal "
    "income at the interview with the official poverty thresholds",
}

#: S1701 poverty status values: C01 counts the universe, C02 its part below the
#: poverty level.
POVERTY_STATUS_COLUMNS = {"C01": "all", "C02": "below_poverty_level"}
POVERTY_STATUS_LABELS = {
    "all": "Population for whom poverty status is determined",
    "below_poverty_level": "Below poverty level",
}
#: S1701 rows: (row, age_band value, Census label, lower age, upper age).
S1701_AGE_ROWS = (
    ("001", "all", "All ages", None, None),
    ("002", "under_18", "Under 18 years", 0, 18),
    ("006", "18_to_64", "18 to 64 years", 18, 65),
    ("010", "65_and_over", "65 years and over", 65, None),
)
AGE_BAND_LABELS = {
    "all": "All ages",
    "under_18": "Age under 18",
    "18_to_64": "Age 18 to 64",
    "65_and_over": "Age 65 and over",
}
DIMENSION_LABELS = {"poverty_status": "Poverty status", "age_band": "Age band"}


def cells(table: str) -> list[tuple[str, dict[str, str], str, tuple[Any, Any]]]:
    """Each declared cell's variable stem, category filters, label and age bounds."""
    if table == "B19013":
        return [("B19013_001", {}, "Total", (None, None))]
    if table == "S1701":
        result = []
        for column, status in POVERTY_STATUS_COLUMNS.items():
            for row, age_band, age_label, lower, upper in S1701_AGE_ROWS:
                label = POVERTY_STATUS_LABELS[status]
                if age_band != "all":
                    label = f"{label}: {age_label}"
                result.append(
                    (
                        f"S1701_{column}_{row}",
                        {"poverty_status": status, "age_band": age_band},
                        label,
                        (lower, upper),
                    )
                )
        return result
    raise ValueError(f"Unsupported ACS check table: {table}")


def _measure(
    table: str,
    ordinal: int,
    stem: str,
    categories: dict[str, str],
    label: str,
    bounds: tuple[Any, Any],
    suffix: str,
    columns: dict[str, str],
) -> dict[str, Any]:
    title, _entity, _domain, _path, groups_page = TABLE_METADATA[table]
    variable = f"{stem}{suffix}"
    is_moe = suffix == "M"
    statistic = "margin_of_error" if is_moe else "estimate"
    filters: dict[str, str] = {"statistic": statistic, **categories}
    constraints: list[dict[str, Any]] = [
        {
            "variable": "statistic",
            "operator": "==",
            "value": statistic,
            "label": "Statistic",
        }
    ]
    # In a wide publisher table the categories and age endpoints belong to
    # the guarded variable column, rather than to the geography row.
    column_dimensions: dict[str, Any] = dict(filters)
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
    lower, upper = bounds
    for operator, bound, name, bound_label in (
        (">=", lower, "lower", "Age lower bound"),
        ("<", upper, "upper", "Age upper bound"),
    ):
        if bound is not None:
            constraints.append(
                {
                    "variable": "age",
                    "operator": operator,
                    "value": bound,
                    "unit": "years",
                    "label": bound_label,
                }
            )
            column_dimensions[f"age_{name}_bound"] = bound
    if table == "B19013":
        concept, unit, aggregation = (
            "census_acs.median_household_income",
            "USD",
            "median",
        )
    else:
        concept, unit, aggregation = (
            "census_acs.poverty_universe_person_count",
            "count",
            "sum",
        )
    return {
        "measure_id": variable,
        "label": f"{label}: {'Margin of error' if is_moe else 'Estimate'}",
        "ordinal": ordinal * 2 + int(is_moe),
        "column": columns[variable],
        "source_column_id": variable,
        "source_column_dimensions": column_dimensions,
        "expected_column_header_row": 1,
        "expected_column_header": variable,
        "concept": f"{concept}{'_margin_of_error' if is_moe else ''}",
        "source_concept": f"{title}: {label} ({statistic})",
        "concept_relation": "source_label",
        "concept_evidence_url": groups_page,
        "concept_evidence_notes": (
            "Publisher margin of error at the ACS 90% confidence level. "
            "Each MOE selects one publisher cell with scale 1; "
            "MOEs must not be added across categories or geographies."
            if is_moe
            else "Publisher estimate, without period alignment or adjustment."
        ),
        "unit": unit,
        "aggregation": aggregation,
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


def _expected_geo_id(geography: str, source: dict[str, Any]) -> str:
    if geography == "district":
        return f"5001900US{source['state']}{source['congressional district']}"
    return f"0400000US{source['state']}"


def _check_rows(table: str, geography: str, source_rows: list[dict[str, Any]]) -> None:
    """The state rows are 52; the district rows the 119th Congress plan, once each.

    Each of the 50 states has one at-large district row (code 00) or districts
    numbered 01 to n without a gap; DC and Puerto Rico have code 98.
    """
    geo_ids = [row["GEO_ID"] for row in source_rows]
    if len(geo_ids) != len(set(geo_ids)):
        raise ValueError(f"Duplicate geography rows in {table} {geography}")
    if geography == "state":
        expected = {f"0400000US{fips}" for fips in STATE_ROW_FIPS}
        if set(geo_ids) != expected:
            raise ValueError(
                f"Expected {STATE_ROW_COUNT} state rows (50 states, DC and Puerto "
                f"Rico) in {table}; missing {sorted(expected - set(geo_ids))}, "
                f"unexpected {sorted(set(geo_ids) - expected)}"
            )
        return
    if len(source_rows) != DISTRICT_ROW_COUNT:
        raise ValueError(
            f"Expected {DISTRICT_ROW_COUNT} congressional district rows (435 "
            f"districts, DC and Puerto Rico) in {table}; got {len(source_rows)}"
        )
    codes: dict[str, list[str]] = {}
    for source in source_rows:
        codes.setdefault(source["state"], []).append(source["congressional district"])
    if set(codes) != STATE_ROW_FIPS:
        raise ValueError(
            f"District rows of {table} do not cover the 50 states, DC and Puerto "
            f"Rico once each: missing {sorted(STATE_ROW_FIPS - set(codes))}, "
            f"unexpected {sorted(set(codes) - STATE_ROW_FIPS)}"
        )
    for state, state_codes in codes.items():
        state_codes = sorted(state_codes)
        if state in (DISTRICT_OF_COLUMBIA_FIPS, PUERTO_RICO_FIPS):
            expected_codes = [NON_VOTING_DISTRICT]
        elif state_codes == [AT_LARGE_DISTRICT]:
            expected_codes = [AT_LARGE_DISTRICT]
        else:
            expected_codes = [
                f"{number:02d}" for number in range(1, len(state_codes) + 1)
            ]
        if state_codes != expected_codes:
            raise ValueError(
                f"Unexpected district codes for state {state} in {table}: {state_codes}"
            )


def build_package(table: str, geography: str, root: Path = ROOT) -> dict[str, Any]:
    """Declare the selected numeric E/M cells of one table at one geography."""
    if table not in TABLES:
        raise ValueError(f"Unsupported ACS check table: {table}")
    if geography not in GEOGRAPHIES:
        raise ValueError(f"Unsupported ACS geography for {table}: {geography}")
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
    variables = [f"{stem}{suffix}" for stem, _, _, _ in table_cells for suffix in "EM"]
    required = {"GEO_ID", "NAME", GEOGRAPHY_KEYS[geography], "state"}
    required.update(variables)
    required.update(variable + "A" for variable in variables)
    missing = required - set(header)
    if missing:
        raise ValueError(f"Missing source columns in {table}: {sorted(missing)}")
    measures = [
        _measure(table, ordinal, stem, categories, label, bounds, suffix, columns)
        for ordinal, (stem, categories, label, bounds) in enumerate(table_cells)
        for suffix in "EM"
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
    _check_rows(table, geography, source_rows)

    rows = []
    for ordinal, source in enumerate(source_rows):
        for variable in variables:
            raw = source[variable]
            annotation = source[variable + "A"]
            # The declared cells are published for every state and district.
            # S1701's other cells carry ACS codes (N, (X), -, **); a code in a
            # declared cell must be handled on purpose, so it fails closed.
            if raw is None or float(raw) < 0 or annotation is not None:
                raise ValueError(
                    f"Unknown suppression in {table} {source['GEO_ID']}: "
                    f"{variable}={raw!r} annotation={annotation!r}"
                )
        rows.append(
            {
                "value_id": source["state"]
                + (source["congressional district"] if geography == "district" else ""),
                "label": source["NAME"],
                "ordinal": ordinal,
                "row_number": ordinal + 2,
                "geography_id": source["GEO_ID"],
                "geography_level": GEOGRAPHY_LEVELS[geography],
                "geography_name": source["NAME"],
                "geography_vintage": (
                    DISTRICT_VINTAGE if geography == "district" else str(YEAR)
                ),
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

    title, entity, domain, _api_path, _groups_page = TABLE_METADATA[table]
    groupby, groupby_label = GEOGRAPHY_DIMENSIONS[geography]
    record_set_id = f"census_acs.acs1_{YEAR}.{table.lower()}.{geography}"
    period_notes = (
        f"Single-year estimate from interviews throughout {YEAR}. "
        f"{TABLE_PERIOD_NOTES[table]}; "
        "Puerto Rico's estimate is separate from the United States total."
    )
    if geography == "district":
        period_notes += (
            f" Districts are those of the 119th Congress, as {YEAR} ACS tabulates."
        )
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
            "notes": period_notes,
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
    dimensions = {groupby: groupby_label, "statistic": "Statistic"}
    values: dict[str, dict[str, str]] = {
        "statistic": {"estimate": "Estimate", "margin_of_error": "Margin of error"}
    }
    category_labels = {
        "poverty_status": POVERTY_STATUS_LABELS,
        "age_band": AGE_BAND_LABELS,
    }
    for _stem, categories, _label, _bounds in table_cells:
        for dimension, value in categories.items():
            dimensions[dimension] = DIMENSION_LABELS[dimension]
            # A value Chronicle's label register lists is declared with the
            # register's label (chronicle#376); Census's own text stays in the
            # measure labels and the source cells.
            values.setdefault(dimension, {})[value] = (
                canonical_value_label(dimension, value)
                or category_labels[dimension][value]
            )
    scope = {
        "state": "all 52 rows (50 states, DC and Puerto Rico)",
        "district": f"all {DISTRICT_ROW_COUNT} rows (the 435 districts of the 119th "
        "Congress, DC's delegate district and Puerto Rico's resident commissioner "
        "district)",
    }[geography]
    subject = table.startswith("S")
    return {
        "schema_version": schema_id("source_package"),
        "package_id": package_id(table, geography),
        "label": f"Census ACS {YEAR} 1-year {GEOGRAPHY_WORDING[geography]} {table}: "
        f"{title}",
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
            # The day the publisher bytes were fetched, from the manifest.
            "extracted_at": str(artifact["fetched_at"]),
            "extraction_method": "Full publisher JSON row parse with guarded E/M source "
            f"cells; {scope} retained; "
            + (
                f"{len(variables)} of the {'subject' if subject else 'detailed'} "
                "table's cells declared; "
                if subject
                else ""
            )
            + "the generator fails on any suppression code or annotation in a "
            "declared cell instead of emitting it",
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
