"""CMS full-year 2025 effectuated enrollment from the annual dataset (chronicle#449).

``cms-aca-annual-effectuated-enrollment-2025`` reads the 2025 state rows of the
CMS data.cms.gov CSV "Health Insurance Exchanges Annual Effectuated Enrollment"
(version 2025-01-01). CMS no longer updates the "Early Snapshot and Full Year
Average" reports that ``cms-aca-effectuated-enrollment-2022`` reads. The CSV
holds the reports' "Full Year" tables for coverage years 2016 to 2025, with the
same eight columns and definitions, so the package declares the 2022 package's
concepts, measures, units, rows and record set, and reads only the 2025 rows.

The tests read the CSV with the standard library and the 2022 workbook with
openpyxl directly, so the values they check do not depend on Chronicle's cell
parsers.
"""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

import openpyxl
import pytest
import yaml
from openpyxl.utils import column_index_from_string

from chronicle.consumer_contract import build_semantic_fact_key
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources.cells import validate_source_cells
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "db" / "data"
PACKAGES_ROOT = REPO_ROOT / "packages"

PACKAGE = "cms-aca-annual-effectuated-enrollment-2025"
PREDECESSOR = "cms-aca-effectuated-enrollment-2022"
KFF = "kff-marketplace-effectuated-enrollment"
CSV_PATH = (
    DATA / "cms_aca/annual_effectuated_enrollment_2025"
    "/health_insurance_exchanges_annual_effectuated_enrollment_data_asof_20260421.csv"
)
CSV_SHA256 = "cbeee9acdfc1cafa543b4c33889836906d788386f3b1ede638ec5df2c204f716"
CSV_SIZE = 39_885
CSV_URL = (
    "https://data.cms.gov/sites/default/files/2026-05/"
    "2836bf59-0829-49b6-8439-f4132a79c2ce/"
    "Health%20Insurance%20Exchanges%20Annual%20Effectuated%20Enrollment"
    "%20Data_asof_20260421.csv"
)
WORKBOOK_2022 = (
    DATA / "cms_aca/effectuated_enrollment_2022/full-year-effectuated-enrollment.xlsx"
)
SHEET = "health_insurance_exchanges_annual_effectuated_enrollment"
HEADER = [
    "State",
    "Year",
    "Platform",
    "Effectuated_Enr",
    "APTC_Enr",
    "Pct_APTC_Enr",
    "CSR_Enr",
    "Pct_CSR_Enr",
    "Avg_Prm",
    "Avg_APTC",
    "Avg_Prm_Aft_APTC",
]
# measure_id -> (CSV column, CSV variable); the 2022 package reads the same
# measures from columns C to J of the workbook's "Full Year 2022" sheet.
MEASURES = {
    "total_enrollment": ("D", "Effectuated_Enr"),
    "aptc_enrollment": ("E", "APTC_Enr"),
    "share_with_aptc": ("F", "Pct_APTC_Enr"),
    "csr_enrollment": ("G", "CSR_Enr"),
    "share_with_csr": ("H", "Pct_CSR_Enr"),
    "average_total_premium": ("I", "Avg_Prm"),
    "average_monthly_aptc": ("J", "Avg_APTC"),
    "average_premium_after_aptc": ("K", "Avg_Prm_Aft_APTC"),
}
# Census state FIPS codes (50 states and DC), independent of the packages.
FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56",
}  # fmt: skip


def _package_yaml(package_id: str) -> dict:
    path = PACKAGES_ROOT / SOURCE_PACKAGE_ALIASES[package_id] / "source_package.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _build(package_id: str, year: int):
    package = load_source_package(package_id)
    rows = package.build_source_rows(year)
    cells = package.build_source_cells(year, source_rows=rows)
    facts = package.build_facts(year, cells=cells, source_rows=rows)
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    return facts


@pytest.fixture(scope="module")
def built():
    return {PACKAGE: _build(PACKAGE, 2025), PREDECESSOR: _build(PREDECESSOR, 2022)}


def _csv_lines() -> list[list[str]]:
    text = CSV_PATH.read_bytes().decode("utf-8")
    return list(csv.reader(io.StringIO(text)))


def _rows_for(year: str) -> dict[str, list[str]]:
    """The year's 51 state rows by state code; the Total rows are left out."""
    return {
        line[0]: line
        for line in _csv_lines()[1:]
        if line[1] == year and line[0] != "Total"
    }


def _diff_paths(old, new, path: tuple = ()) -> set[tuple]:
    if isinstance(old, dict) and isinstance(new, dict):
        paths = {path + (key,) for key in old.keys() ^ new.keys()}
        for key in old.keys() & new.keys():
            paths |= _diff_paths(old[key], new[key], path + (key,))
        return paths
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        paths = set()
        for index, (old_item, new_item) in enumerate(zip(old, new, strict=True)):
            paths |= _diff_paths(old_item, new_item, path + (index,))
        return paths
    return set() if old == new else {path}


def test_manifest_registers_the_publisher_file():
    manifest = yaml.safe_load((CSV_PATH.parent / "manifest.yaml").read_text())
    (year,) = manifest["files"]
    entry = manifest["files"][2025]

    assert year == 2025
    assert manifest["package_id"] == PACKAGE
    assert hashlib.sha256(CSV_PATH.read_bytes()).hexdigest() == CSV_SHA256
    assert entry["filename"] == CSV_PATH.name
    assert entry["publisher_filename"] == (
        "Health Insurance Exchanges Annual Effectuated Enrollment Data_asof_20260421.csv"
    )
    assert entry["source_url"] == CSV_URL
    assert entry["sha256"] == CSV_SHA256
    assert entry["size_bytes"] == CSV_SIZE == CSV_PATH.stat().st_size
    assert entry["storage"]["r2"]["key"] == (
        f"raw/cms_aca/{PACKAGE}/2025/{CSV_SHA256}/{CSV_PATH.name}"
    )


def test_csv_holds_ten_years_of_total_and_state_rows():
    """Each coverage year from 2016 to 2025 has the three platform Total rows
    and then the 50 states and DC, in the 2022 package's row order."""
    header, *lines = _csv_lines()
    states = [
        row["expected_row_header"]
        for row in _package_yaml(PACKAGE)["record_sets"][0]["rows"]
    ]

    assert header == HEADER
    assert len(lines) == 540
    assert sorted(states) == sorted(FIPS)
    for index, year in enumerate(range(2016, 2026)):
        block = lines[index * 54 : (index + 1) * 54]
        assert {line[1] for line in block} == {str(year)}
        assert [(line[0], line[2]) for line in block[:3]] == [
            ("Total", "All"),
            ("Total", "HealthCare.gov"),
            ("Total", "SBE"),
        ]
        assert [line[0] for line in block[3:]] == states
    # The 2025 state rows are file lines 491 to 541 (line 1 is the header).
    assert [line[0] for line in _csv_lines()[490:541]] == states


def test_facts_are_their_publisher_cells(built):
    header = HEADER
    states = _rows_for("2025")
    assert sorted(states) == sorted(FIPS)

    seen = set()
    for fact in built[PACKAGE]:
        state = fact.layout.groupby_value_id.upper()
        _column, variable = MEASURES[fact.layout.measure_id]
        assert fact.layout.source_column_id == variable
        assert fact.value == float(states[state][header.index(variable)]), (
            fact.source_record_id
        )
        assert fact.source_record_id == (
            f"cms_aca.effectuated_enrollment.2025.state_marketplace.{state.lower()}."
            f"{fact.layout.measure_id}"
        )
        assert fact.geography.level == "state"
        assert fact.geography.id == f"0400000US{FIPS[state]}"
        assert len(fact.source_row_keys) == 1
        assert fact.period.type == "calendar_year"
        assert fact.period.value == 2025
        assert fact.source.vintage == "calendar_year_2025"
        assert fact.source.source_sha256 == CSV_SHA256
        assert fact.source.source_file == CSV_PATH.name
        seen.add((state, variable))
    assert len(built[PACKAGE]) == 408
    assert seen == {
        (state, variable) for state in FIPS for _column, variable in MEASURES.values()
    }


def test_cells_are_the_2025_state_rows_only():
    package = load_source_package(PACKAGE)
    cells = package.build_source_cells(2025)
    data_cells = [cell for cell in cells if cell.row_number > 1]

    assert [cell.raw_value for cell in cells if cell.row_number == 1] == HEADER
    assert len(data_cells) == 51 * len(HEADER)
    assert {cell.raw_value for cell in data_cells if cell.column_number == 2} == {2025}
    assert {cell.note for cell in data_cells} == {
        f"source_line_number={line}" for line in range(491, 542)
    }


def test_measure_columns_and_rows_head_their_cells():
    lines = _csv_lines()
    package = _package_yaml(PACKAGE)
    (record_set,) = package["record_sets"]

    columns = {}
    for measure in record_set["measures"]:
        variable = measure["source_column_id"]
        assert lines[0][column_index_from_string(measure["column"]) - 1] == variable
        assert measure["expected_column_header_row"] == 1
        assert measure["expected_column_header"] == variable
        assert measure["source_concept"] == f"cms_aca.{variable}"
        columns[measure["measure_id"]] = (measure["column"], variable)
    assert columns == MEASURES
    assert [row["row_number"] for row in record_set["rows"]] == list(range(2, 53))
    assert package["artifact"]["selected_rows"] == [
        {"State": row["expected_row_header"], "Year": "{year}"}
        for row in record_set["rows"]
    ]
    for row in record_set["rows"]:
        assert row["expected_row_header_column"] == "A"
        assert row["expected_row_header"] == row["value_id"].upper()


def test_package_file_equals_the_2022_package_apart_from_the_artifact():
    """Concepts, units, aggregations, labels, rows, geographies, record ids and
    the record set spec stay those of the 2022 package. Only the edition's ids
    and the positions in the new file change."""
    new, old = _package_yaml(PACKAGE), _package_yaml(PREDECESSOR)
    changes = {
        ("package_id",): PACKAGE,
        ("label",): (
            "CMS Marketplace full-year 2025 effectuated enrollment and financial "
            "assistance"
        ),
        ("artifact", "source_table"): (
            "Health Insurance Exchanges Annual Effectuated Enrollment : 2025-01-01"
        ),
        ("artifact", "resource_directory"): (
            "data/cms_aca/annual_effectuated_enrollment_2025"
        ),
        ("artifact", "extracted_at"): "2026-11-27",
        ("artifact", "extraction_method"): (
            "CSV full-row parse with source-row cells selected by State and Year"
        ),
        ("artifact", "parser"): "delimited_text_full_rows",
        ("artifact", "sheet_name"): SHEET,
        ("artifact", "selected_rows"): new["artifact"]["selected_rows"],
        ("record_sets", 0, "sheet_name"): SHEET,
    }
    for index, row in enumerate(old["record_sets"][0]["rows"]):
        # The workbook's state rows 6 to 56 are the selected cell rows 2 to 52.
        changes[("record_sets", 0, "rows", index, "row_number")] = row["row_number"] - 4
    for index, measure in enumerate(old["record_sets"][0]["measures"]):
        column, variable = MEASURES[measure["measure_id"]]
        path = ("record_sets", 0, "measures", index)
        changes[(*path, "column")] = column
        changes[(*path, "source_column_id")] = variable
        changes[(*path, "expected_column_header_row")] = 1
        changes[(*path, "expected_column_header")] = variable
        changes[(*path, "source_concept")] = f"cms_aca.{variable}"

    assert _diff_paths(old, new) == set(changes)
    for path, value in changes.items():
        node = new
        for key in path:
            node = node[key]
        assert node == value, path


def _definition(fact) -> tuple:
    layout = fact.layout
    return (
        fact.measure.concept,
        fact.measure.unit,
        fact.measure.concept_relation,
        fact.measure.concept_authority,
        fact.aggregation,
        fact.entity,
        fact.geography,
        fact.filters,
        fact.constraints,
        fact.domain,
        fact.provenance_class,
        fact.assertion,
        fact.period.type,
        fact.dimension_labels,
        fact.dimension_value_labels,
        layout.record_set_spec_id,
        layout.groupby_dimension,
        layout.groupby_value_id,
        layout.groupby_value_label,
        layout.groupby_ordinal,
        layout.measure_id,
        layout.measure_label,
        layout.measure_ordinal,
        layout.table_record_kind,
    )


def test_facts_keep_the_2022_packages_definitions(built):
    old = {
        fact.source_record_id.replace(".2022.", ".2025."): fact
        for fact in built[PREDECESSOR]
    }
    new = {fact.source_record_id: fact for fact in built[PACKAGE]}

    assert set(new) == set(old)
    for record_id, fact in new.items():
        assert _definition(fact) == _definition(old[record_id]), record_id
        assert (fact.period.value, old[record_id].period.value) == (2025, 2022)


def test_csv_repeats_the_2022_report_full_year_table():
    """The CSV's 2022 state rows are the 2022 package's cells: the annual
    dataset continues the report series."""
    workbook = openpyxl.load_workbook(WORKBOOK_2022, read_only=True, data_only=True)
    sheet = workbook["Full Year 2022"]
    report = {
        row[0]: row[2:10]
        for row in sheet.iter_rows(min_row=6, max_row=56, values_only=True)
    }
    workbook.close()
    rows = _rows_for("2022")

    assert sorted(report) == sorted(rows) == sorted(FIPS)
    for state, values in report.items():
        assert [float(text) for text in rows[state][3:]] == list(values), state


def test_state_rows_add_up_to_the_total_row_the_package_leaves_out(built):
    """The package reads states only, like the 2022 package. CMS's Total row for
    all platforms equals the sum of the 51 state rows."""
    total = next(line for line in _csv_lines() if line[:3] == ["Total", "2025", "All"])
    for measure_id, column in (
        ("total_enrollment", "Effectuated_Enr"),
        ("aptc_enrollment", "APTC_Enr"),
        ("csr_enrollment", "CSR_Enr"),
    ):
        values = [
            fact.value
            for fact in built[PACKAGE]
            if fact.layout.measure_id == measure_id
        ]
        assert len(values) == 51
        assert sum(values) == int(total[HEADER.index(column)]), measure_id
    assert int(total[HEADER.index("Effectuated_Enr")]) == 22_085_132
    assert all(fact.geography.level == "state" for fact in built[PACKAGE])


def test_no_fact_shares_a_semantic_key_with_a_related_package(built):
    """The same concepts at another period (the 2022 package, KFF's 2024 values)
    or another population (OEP plan selections) give different fact keys."""
    new_keys = {build_semantic_fact_key(fact) for fact in built[PACKAGE]}
    others = {
        PREDECESSOR: built[PREDECESSOR],
        KFF: _build(KFF, 2024),
        "cms-aca-oep-state-level-2022": _build("cms-aca-oep-state-level-2022", 2022),
        "cms-aca-oep-state-level": _build("cms-aca-oep-state-level", 2024),
        "cms-aca-oep-state-level-2025": _build("cms-aca-oep-state-level-2025", 2025),
        "cms-aca-oep-state-level-2026": _build("cms-aca-oep-state-level-2026", 2026),
    }

    assert len(new_keys) == 408
    for package_id, facts in others.items():
        assert not new_keys & {build_semantic_fact_key(fact) for fact in facts}, (
            package_id
        )


@pytest.mark.parametrize("year", [2022, 2023, 2024])
def test_other_build_years_have_no_artifact(year):
    """Only the 2025 file is registered, so no build year relabels the CSV's
    rows for the 2022 package's year or KFF's 2024, and the 2023 bundle skips
    the package."""
    with pytest.raises(ValueError, match=f"No source artifact for year {year}"):
        load_source_package(PACKAGE).build_source_rows(year)


def test_validate_source_package_reports_counts():
    report = validate_source_package(PACKAGE, year=2025)

    assert report.valid
    assert report.counts == {
        "record_set_count": 1,
        "row_count": 51,
        "measure_count": 8,
        "source_record_count": 408,
        "source_region_count": 1,
    }


def test_source_suite_passes_agent_acceptance(tmp_path):
    suite = build_source_suite(PACKAGE, tmp_path / PACKAGE, year=2025)

    assert suite.agent_acceptance.valid
    assert suite.agent_acceptance.counts["row_semantic_error_count"] == 0
