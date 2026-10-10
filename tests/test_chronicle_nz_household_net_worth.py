"""Stats NZ household net worth: published cells, populations, and drift guards."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path

import openpyxl
import pytest
import yaml

from chronicle.artifacts import build_r2_key
from chronicle.bundle import _dimension_label_reports, build_bundle_coverage
from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources.cells import build_source_cell_key, validate_source_cells
from chronicle.sources.specs import build_cells_by_sheet_address, resolve_source_record
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
ALIAS = "stats-nz-household-net-worth-2024"
DIRECTORY = Path("stats_nz/household_net_worth_2024")
FILENAME = "household-net-worth-statistics-year-ended-june-2024.xlsx"
SHA256 = "2fb942322e5131824a15007e7b0742c4f8220822c7e8f9adee83bae154913f9e"
DATA_DIR = REPO_ROOT / "db/data" / DIRECTORY
SOURCE_URL = (
    "https://www.stats.govt.nz/assets/Uploads/Household-net-worth-statistics/"
    "Household-net-worth-statistics-Year-ended-June-2024/Download-data/" + FILENAME
)
PREFIX = "stats_nz_household_net_worth."
# Pinned independently of the YAML: used range, first 2024 row, last 2024 row,
# first footer row, and the publisher's estimate columns.
SHEET_PLANS = {
    "Table1.01": (167, 8, 43, 155, "CGKO"),
    "Table2.01": (97, 6, 25, 86, "CEGIKM"),
    "Table2.02": (97, 6, 25, 86, "CEGIKM"),
    "Table2.03": (96, 5, 24, 85, "CEGIKM"),
    "Table2.04": (97, 6, 25, 86, "CEGIKM"),
    "Table3.01": (97, 6, 25, 86, "CEGIKM"),
    "Table3.02": (97, 6, 25, 86, "CEGIKM"),
    "Table3.03": (96, 5, 24, 85, "CEGIKM"),
    "Table3.04": (97, 6, 25, 86, "CEGIKM"),
    "Table5.01": (142, 8, 37, 128, "CGKO"),
    "Table7.01": (166, 8, 44, 156, "CGKO"),
    "Table7.02": (166, 8, 44, 156, "CGKO"),
    "Table7.03": (165, 7, 43, 155, "CGKO"),
    "Table7.04": (166, 8, 44, 156, "CGKO"),
}
SUPPRESSED = {
    ("Table7.01", "C12"),
    ("Table7.01", "C22"),
    ("Table7.01", "K40"),
    ("Table7.01", "K41"),
    ("Table7.02", "C22"),
    ("Table7.03", "C21"),
    ("Table7.04", "C22"),
}
# Workbook structure, independent of record_sets: bold A-column headings begin
# sections; B-column subtotals close nested groups; A-column totals are separate.
# In Table1.01 B23 closes A18's shares group, so B24:B27 return to A9's Assets.
PUBLISHED_SECTION_ROWS = {
    "Table1.01": {
        "Assets": (*range(10, 18), *range(24, 28)),
        "Shares and other equity": tuple(range(19, 24)),
        "Liabilities": tuple(range(30, 35)),
        "Trust memorandum items": tuple(range(38, 42)),
        "Crypto memorandum items": (43,),
    },
    "Table2.01": {"Assets": tuple(range(10, 18)), "Liabilities": tuple(range(20, 25))},
    "Table2.02": {"Assets": tuple(range(10, 18)), "Liabilities": tuple(range(20, 25))},
    "Table2.03": {"Assets": tuple(range(9, 17)), "Liabilities": tuple(range(19, 24))},
    "Table2.04": {"Assets": tuple(range(10, 18)), "Liabilities": tuple(range(20, 25))},
    "Table3.01": {"Assets": tuple(range(10, 18)), "Liabilities": tuple(range(20, 25))},
    "Table3.02": {"Assets": tuple(range(10, 18)), "Liabilities": tuple(range(20, 25))},
    "Table3.03": {"Assets": tuple(range(9, 17)), "Liabilities": tuple(range(19, 24))},
    "Table3.04": {"Assets": tuple(range(10, 18)), "Liabilities": tuple(range(20, 25))},
    "Table5.01": {
        "Household size(4)(5)": tuple(range(10, 15)),
        "Household composition": tuple(range(16, 25)),
        "Tenure of household(10)": tuple(range(26, 31)),
        "Region": tuple(range(32, 37)),
    },
    "Table7.01": {
        "Assets": (*range(11, 19), *range(29, 37)),
        "Liabilities": (*range(21, 25), *range(39, 43)),
    },
    "Table7.02": {
        "Assets": (*range(11, 19), *range(29, 37)),
        "Liabilities": (*range(21, 25), *range(39, 43)),
    },
    "Table7.03": {
        "Assets": (*range(10, 18), *range(28, 36)),
        "Liabilities": (*range(20, 24), *range(38, 42)),
    },
    "Table7.04": {
        "Assets": (*range(11, 19), *range(29, 37)),
        "Liabilities": (*range(21, 25), *range(39, 43)),
    },
}
# Every numeric estimate within these column/block boundaries inherits its
# published column header. Suppressed cells are absent from the numeric oracle.
QUINTILE_COLUMN_GROUPS = {
    "Table2": (
        "net_worth_quintile",
        {
            "C": "Quintile 1 (under $52,577)",
            "E": "Quintile 2 ($52,577 to $307,007)",
            "G": "Quintile 3 ($307,008 to $780,499)",
            "I": "Quintile 4 ($780,500 to $1,450,999)",
            "K": "Quintile 5 ($1,451,000 and over)",
            "M": "All quintiles",
        },
    ),
    "Table3": (
        "income_quintile",
        {
            "C": "Quintile 1 (under $46,962)",
            "E": "Quintile 2 ($46,962 to $83,295)",
            "G": "Quintile 3 ($83,296 to $132,579)",
            "I": "Quintile 4 ($132,580 to $197,538)",
            "K": "Quintile 5 ($197,539 and over)",
            "M": "All quintiles",
        },
    ),
}
INDIVIDUAL_AGE_COLUMN_BLOCKS = (
    {"C": "15-24", "G": "25-34", "K": "35-44", "O": "45-54"},
    {"C": "55-64", "G": "65-74", "K": "75+", "O": "Total"},
)
GROUPING_DIMENSIONS = {
    PREFIX + name
    for name in (
        "published_section",
        "net_worth_quintile",
        "income_quintile",
        "individual_age_group",
    )
}


@lru_cache
def _workbook():
    return openpyxl.load_workbook(DATA_DIR / FILENAME, data_only=True)


@lru_cache
def _package():
    # A scratch-only YAML can be supplied for the lane's red demonstrations.
    return load_source_package(
        os.environ.get("CHRONICLE_NZ_NET_WORTH_TEST_PACKAGE", ALIAS)
    )


@lru_cache
def _cells():
    return _package().build_source_cells(2024)


@lru_cache
def _cell_index():
    return build_cells_by_sheet_address(_cells())


@lru_cache
def _specs():
    return _package().build_source_record_specs(2024)


@lru_cache
def _facts():
    return _package().build_facts(2024, cells=_cells())


@lru_cache
def _facts_by_cell():
    return {
        (spec.selector.sheet_name, spec.selector.address): fact
        for spec, fact in zip(_specs(), _facts(), strict=True)
    }


def _published_estimates():
    estimates = {}
    for sheet, (_last, first, final, _footer, columns) in SHEET_PLANS.items():
        for row in range(first, final + 1):
            for column in columns:
                cell = _workbook()[sheet][f"{column}{row}"]
                if type(cell.value) in (int, float):
                    estimates[(sheet, cell.coordinate)] = cell.value
    return estimates


def _expected_grouping_memberships():
    """Enumerate publisher memberships without consulting package selectors."""
    assert set(PUBLISHED_SECTION_ROWS) == set(SHEET_PLANS)
    memberships = Counter()
    for sheet, address in _published_estimates():
        column, row_number = re.fullmatch(r"([A-Z]+)([0-9]+)", address).groups()
        row = int(row_number)
        for section, member_rows in PUBLISHED_SECTION_ROWS[sheet].items():
            if row in member_rows:
                memberships[
                    (sheet, address, PREFIX + "published_section", section)
                ] += 1
        for table, (dimension, column_groups) in QUINTILE_COLUMN_GROUPS.items():
            if sheet.startswith(table):
                memberships[
                    (sheet, address, PREFIX + dimension, column_groups[column])
                ] += 1
        if sheet.startswith("Table7"):
            # Table7.03 starts one row earlier; its second age header is row26.
            second_header = 26 if sheet == "Table7.03" else 27
            age = INDIVIDUAL_AGE_COLUMN_BLOCKS[row > second_header][column]
            memberships[(sheet, address, PREFIX + "individual_age_group", age)] += 1
    return memberships


def _expected_guards():
    """Independent publisher-coordinate contract; deleting YAML guards stays red."""
    guards = set(SUPPRESSED)
    for sheet, (last, first, final, footer, columns) in SHEET_PLANS.items():
        book = _workbook()[sheet]
        guards.update((sheet, f"A{row}") for row in range(1, 5))
        if isinstance(book["A5"].value, str) and "population" in book["A5"].value:
            guards.add((sheet, "A5"))
        guards.add((sheet, f"A{first}"))
        guards.update((sheet, f"A{row}") for row in range(footer, last + 1))
        # Labels and parent sections in the year block, excluding the unselected
        # generic axis descriptor. These include labels for suppressed rows.
        for row in range(first + 1, final + 1):
            for column in "AB":
                cell = book[f"{column}{row}"]
                if isinstance(cell.value, str) and not cell.value.startswith(
                    "Asset or liability type"
                ):
                    guards.add((sheet, cell.coordinate))
        if sheet in ("Table1.01", "Table5.01"):
            guards.update(
                (sheet, f"{column}{row}") for column in columns for row in (6, 7)
            )
        elif sheet.startswith(("Table2", "Table3")):
            guards.update(
                (sheet, f"{column}{row}")
                for column in columns
                for row in (first + 1, first + 2)
            )
        else:
            unit_row = 6 if sheet == "Table7.03" else 7
            guards.update(
                (sheet, f"{column}{row}")
                for column in columns
                for row in (unit_row, first + 1, first + 19)
            )
    return tuple(sorted(guards))


EXPECTED_GUARDS = _expected_guards()


def _guard_index(specs):
    guards = {}
    for spec in specs:
        selector = spec.selector
        entries = (
            (
                selector.expected_row_header_address,
                selector.expected_row_header,
                "row header",
            ),
            (
                selector.expected_column_header_address,
                selector.expected_column_header,
                "column header",
            ),
            *(
                (guard.address, guard.expected_value, guard.label)
                for guard in selector.guard_cells
            ),
        )
        assert not selector.range_label_guards
        for address, expected, label in entries:
            if address is not None:
                coordinate = (selector.sheet_name, address)
                if coordinate in guards:
                    assert guards[coordinate][1] == expected
                else:
                    guards[coordinate] = (spec, expected, label)
    return guards


@lru_cache
def _guards():
    return _guard_index(_specs())


def _expected_measure(sheet, address):
    column = re.match(r"[A-Z]+", address).group()
    if sheet in ("Table1.01", "Table5.01"):
        return (
            "household_thousands" if column == "O" else "NZD_thousands",
            {"C": "median", "G": "mean", "K": "sum", "O": "sum"}[column],
        )
    suffix = sheet.rsplit(".", 1)[1]
    unit = (
        ("person_thousands" if sheet.startswith("Table7") else "household_thousands")
        if suffix == "04"
        else "NZD_thousands"
    )
    return unit, {"01": "median", "02": "mean", "03": "sum", "04": "sum"}[suffix]


def _assert_frozen_package(package):
    """Fail on model arithmetic, period alignment, or missing publisher labels."""
    assert package.artifact.artifact_year == 2024
    specs = package.build_source_record_specs(2024)
    selected = [(spec.selector.sheet_name, spec.selector.address) for spec in specs]
    assert len(selected) == len(set(selected)) == 1413
    assert set(selected) == set(_published_estimates())
    assert set(_guard_index(specs)) == set(EXPECTED_GUARDS)
    assert set(package.dimension_labels) == {
        PREFIX + name
        for name in (
            "asset_or_liability_type",
            "household_characteristic",
            "published_section",
            "population_note",
            "net_worth_quintile",
            "income_quintile",
            "individual_age_group",
        )
    }
    assert all(package.dimension_labels.values())
    for spec in specs:
        selector = spec.selector
        assert spec.value_scale == 1
        assert spec.divisor_selector is None
        assert spec.round_to is None
        assert selector.end_address is None
        assert (spec.period_type, spec.period) == ("fiscal_year", 2023)
        assert (spec.unit, spec.aggregation) == _expected_measure(
            selector.sheet_name, selector.address
        )
        assert spec.provenance_class == "survey_aggregate"
        assert spec.survey_instrument == "Household Economic Survey"
        assert spec.assertion == "observation"
        coverage = spec.period_coverage
        assert (coverage.start_date, coverage.end_date, coverage.basis) == (
            "2023-07-01",
            "2024-06-30",
            "survey_reference",
        )
        population = _workbook()[selector.sheet_name]["A5"].value
        if isinstance(population, str) and "population" in population:
            assert spec.filters[PREFIX + "population_note"] == population
        assert all(constraint.operator == "==" for constraint in spec.constraints)


def test_household_net_worth_alias_and_validate_package():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == DIRECTORY
    assert _package().package_id == ALIAS
    report = validate_source_package(ALIAS, year=2024)
    assert report.valid
    assert not report.warnings
    assert report.counts["record_set_count"] == 82
    assert report.counts["source_record_count"] == 1413


def test_household_net_worth_artifact_receipt_storage_and_licence_are_pinned():
    manifest = yaml.safe_load((DATA_DIR / "manifest.yaml").read_text())
    entry = manifest["files"][2024]
    content = (DATA_DIR / FILENAME).read_bytes()
    assert manifest["source_id"] == "stats_nz"
    assert manifest["license"] == "CC BY 4.0"
    assert manifest["attribution"] == "Stats NZ"
    assert entry["source_url"] == SOURCE_URL
    assert entry["fetched_at"] == "2026-10-10T08:31:08Z"
    assert entry["sha256"] == hashlib.sha256(content).hexdigest() == SHA256
    assert entry["size_bytes"] == len(content) == 386_546
    assert len(_workbook().sheetnames) == 39
    key = build_r2_key(
        source_id="stats_nz",
        package_id="household_net_worth_2024",
        year=2024,
        sha256=SHA256,
        filename=FILENAME,
    )
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }
    assert {fact.source.raw_r2_uri for fact in _facts()} == {f"r2://ledger-raw/{key}"}
    assert {path.name for path in DATA_DIR.iterdir()} == {"manifest.yaml", FILENAME}


def test_household_net_worth_preserves_contents_and_complete_scoped_sheets():
    assert _package().artifact.sheets == ("Contents", *SHEET_PLANS)
    assert len(_cells()) == 31_534
    assert Counter(cell.sheet_name for cell in _cells()) == {
        "Contents": 53 * 2,
        **{sheet: last * 18 for sheet, (last, *_) in SHEET_PLANS.items()},
    }
    assert validate_source_cells(_cells()).valid
    assert validate_facts(_facts()).valid
    assert validate_consumer_fact_contract(_facts()).valid
    assert {fact.source.source_sha256 for fact in _facts()} == {SHA256}
    assert {fact.source.source_size_bytes for fact in _facts()} == {386_546}
    assert {fact.source.url for fact in _facts()} == {SOURCE_URL}
    # Preserve all used cells, including unused years, errors, and symbols.
    for cell in _cells():
        assert cell.raw_value == _workbook()[cell.sheet_name][cell.address].value


def test_household_net_worth_frozen_publisher_boundaries():
    _assert_frozen_package(_package())


def test_household_net_worth_every_fact_is_one_unscaled_published_estimate():
    expected = _published_estimates()
    assert len(expected) == len(_facts()) == 1413
    assert set(_facts_by_cell()) == set(expected)
    cells_by_key = {build_source_cell_key(cell): cell for cell in _cells()}
    for spec, fact in zip(_specs(), _facts(), strict=True):
        coordinate = (spec.selector.sheet_name, spec.selector.address)
        assert fact.source_record_id == spec.source_record_id
        assert fact.value == expected[coordinate]
        assert fact.measure.unit == spec.unit
        assert fact.aggregation.method == spec.aggregation
        assert fact.aggregation.denominator is None
        value_cell = cells_by_key[fact.source_cell_keys[0]]
        assert (value_cell.sheet_name, value_cell.address) == coordinate
        assert value_cell.raw_value == fact.value
        # The row header needs an explicit guard because core selector lineage
        # does not automatically include expected_row_header_address.
        label_cell = _cell_index()[
            (spec.selector.sheet_name, spec.selector.expected_row_header_address)
        ]
        assert build_source_cell_key(label_cell) in fact.source_cell_keys
        assert set(fact.source_cell_keys) <= cells_by_key.keys()


@pytest.mark.parametrize(
    ("sheet", "address", "value"),
    [
        ("Table1.01", "C10", 765),
        ("Table1.01", "G10", 884),
        ("Table1.01", "K10", 926_540_131),
        ("Table1.01", "O10", 1049),
        ("Table5.01", "C10", 334),
        ("Table5.01", "G10", 678),
        ("Table5.01", "O10", 461),
        ("Table2.01", "C25", 11),
        ("Table2.04", "C25", 390),
        ("Table3.01", "C25", 344),
        ("Table3.04", "C25", 394),
        ("Table7.01", "C26", 4),
        ("Table7.04", "C11", 10),
        ("Table1.01", "C36", 529),
        ("Table2.01", "M25", 525),
        ("Table5.01", "C37", 525),
    ],
)
def test_household_net_worth_exact_publisher_cells(sheet, address, value):
    assert _workbook()[sheet][address].value == value
    assert _facts_by_cell()[(sheet, address)].value == value


def test_household_net_worth_population_notes_distinguish_holders_and_all_households():
    holders = _facts_by_cell()[("Table1.01", "C36")]
    all_households = _facts_by_cell()[("Table5.01", "C37")]
    assert holders.value == 529
    assert all_households.value == 525
    assert "non-zero value" in holders.filters[PREFIX + "population_note"]
    assert (
        "including those with zero net worth"
        in all_households.filters[PREFIX + "population_note"]
    )
    for spec, fact in zip(_specs(), _facts(), strict=True):
        note = _workbook()[spec.selector.sheet_name]["A5"].value
        if isinstance(note, str) and "population" in note:
            assert fact.filters[PREFIX + "population_note"] == note
            assert note in fact.measure.concept_evidence_notes
            assert (
                build_source_cell_key(_cell_index()[(spec.selector.sheet_name, "A5")])
                in fact.source_cell_keys
            )


def test_household_net_worth_quintiles_and_age_groups_remain_publisher_groupings():
    for name, header in (
        ("net_worth_quintile", "Table2.01"),
        ("income_quintile", "Table3.01"),
    ):
        dimension = PREFIX + name
        labels = {_workbook()[header][f"{column}7"].value for column in "CEGIKM"}
        assert {
            fact.filters[dimension] for fact in _facts() if dimension in fact.filters
        } == labels
        assert _package().dimension_value_labels[dimension] == {
            label: label for label in labels
        }
    age_dimension = PREFIX + "individual_age_group"
    assert {
        fact.filters[age_dimension]
        for fact in _facts()
        if age_dimension in fact.filters
    } == {
        "15-24",
        "25-34",
        "35-44",
        "45-54",
        "55-64",
        "65-74",
        "75+",
        "Total",
    }
    for fact in _facts():
        assert all(constraint.operator == "==" for constraint in fact.constraints)
        assert fact.entity.name == (
            "person" if age_dimension in fact.filters else "household"
        )
        assert fact.geography.id == "NZ"
        if fact.aggregation.method == "median":
            assert (
                "Published medians are cut-points"
                in fact.measure.concept_evidence_notes
            )


def test_household_net_worth_grouping_dimensions_follow_publisher_boundaries():
    expected = _expected_grouping_memberships()
    dimensions = Counter()
    constraints = Counter()
    for spec, fact in zip(_specs(), _facts(), strict=True):
        coordinate = (spec.selector.sheet_name, spec.selector.address)
        dimensions.update(
            (*coordinate, dimension, value)
            for dimension, value in fact.filters.items()
            if dimension in GROUPING_DIMENSIONS
        )
        for constraint in fact.constraints:
            if constraint.variable in GROUPING_DIMENSIONS:
                assert constraint.operator == "=="
                constraints[(*coordinate, constraint.variable, constraint.value)] += 1
    assert dimensions == expected
    assert constraints == expected


def test_household_net_worth_consumer_grouping_constraints_follow_publisher_boundaries():
    expected = _expected_grouping_memberships()
    coordinates = {
        spec.source_record_id: (spec.selector.sheet_name, spec.selector.address)
        for spec in _specs()
    }
    actual = Counter()
    for row in consumer_fact_rows(_facts()):
        coordinate = coordinates[row["lineage"]["source_record_id"]]
        for constraint in row["universe_constraints"]["constraints"]:
            if constraint["variable"] in GROUPING_DIMENSIONS:
                assert constraint["operator"] == "=="
                actual[(*coordinate, constraint["variable"], constraint["value"])] += 1
    assert actual == expected


def test_household_net_worth_suppression_is_raw_evidence_and_never_an_estimate():
    assert len(SUPPRESSED) == 7
    for coordinate in SUPPRESSED:
        assert _cell_index()[coordinate].raw_value == "S"
        assert coordinate not in _facts_by_cell()
        assert coordinate in _guards()
    for sheet in ("Table7.01", "Table7.02", "Table7.03", "Table7.04"):
        symbols = [
            cell.raw_value
            for cell in _cells()
            if cell.sheet_name == sheet
            and isinstance(cell.raw_value, str)
            and cell.raw_value.startswith("S     suppressed.")
        ]
        assert len(symbols) == 1
        assert "confidentiality reasons" in symbols[0]
    assert _cell_index()[("Table1.01", "E43")].raw_value == "..."
    assert ("Table1.01", "E43") not in _facts_by_cell()


def test_household_net_worth_every_publisher_note_is_verbatim_in_fact_lineage():
    for spec, fact in zip(_specs(), _facts(), strict=True):
        sheet = spec.selector.sheet_name
        last, _first, _final, footer, _columns = SHEET_PLANS[sheet]
        for row in range(footer, last + 1):
            cell = _cell_index()[(sheet, f"A{row}")]
            assert build_source_cell_key(cell) in fact.source_cell_keys
            assert cell.raw_value in fact.measure.concept_evidence_notes


@pytest.mark.parametrize("requested_year", [2023, 2024, 2025])
def test_household_net_worth_requested_year_cannot_change_reference_period(
    requested_year,
):
    facts = _package().build_facts(requested_year, cells=_cells())
    assert facts == _facts()
    for fact in facts:
        assert (fact.period.type, fact.period.value) == ("fiscal_year", 2023)
        coverage = fact.period_coverage
        assert (coverage.start_date, coverage.end_date, coverage.basis) == (
            "2023-07-01",
            "2024-06-30",
            "survey_reference",
        )
        assert coverage.source_period_label == "Year ended June 2024"
        assert fact.provenance_class == "survey_aggregate"
        assert fact.survey_instrument == "Household Economic Survey"
        assert fact.assertion == "observation"


def test_household_net_worth_dimensions_values_and_consumer_contract_have_labels():
    rows = consumer_fact_rows(_facts())
    assert _dimension_label_reports(ALIAS, rows) == ([], [])
    for fact in _facts():
        assert fact.layout.groupby_dimension_label
        assert (
            fact.dimension_value_labels[fact.layout.groupby_dimension][
                fact.layout.groupby_value_id
            ]
            == fact.layout.groupby_value_label.strip()
        )
        for dimension, value in fact.filters.items():
            assert fact.dimension_labels[dimension]
            assert fact.dimension_value_labels[dimension][str(value)]
    for row in rows:
        assert row["concept_alignment"]["relation"] == "source_label"
        assert row["lineage"]["source_cell_keys"]
        assert (
            not {"target", "solver", "calibration", "uprating_factor", "weight"}
            & row.keys()
        )


def test_household_net_worth_single_package_coverage_has_no_duplicate_keys():
    coverage = build_bundle_coverage(consumer_fact_rows(_facts()))
    assert coverage["fact_count"] == 1413
    assert coverage["counts"]["by_source"] == {"stats_nz": 1413}
    assert coverage["counts"]["by_geography"] == {"country:NZ": 1413}
    assert coverage["counts"]["by_entity"] == {"household": 940, "person": 473}
    assert coverage["counts"]["by_period"] == {"fiscal_year:2023": 1413}
    assert coverage["duplicates"] == {
        "aggregate_fact_keys": [],
        "semantic_fact_keys": [],
    }


def test_household_net_worth_every_required_guard_is_declared():
    assert len(EXPECTED_GUARDS) == 752
    assert set(_guards()) == set(EXPECTED_GUARDS)


@pytest.mark.parametrize(
    ("sheet", "address"),
    EXPECTED_GUARDS,
    ids=[f"{sheet}:{address}" for sheet, address in EXPECTED_GUARDS],
)
def test_household_net_worth_each_guard_rejects_mutated_publisher_cell(sheet, address):
    coordinate = (sheet, address)
    assert coordinate in _guards(), f"Missing publisher guard: {sheet}!{address}"
    spec, expected, label = _guards()[coordinate]
    resolve_source_record(_cells(), spec, cells_by_sheet_address=_cell_index())
    assert _cell_index()[coordinate].raw_value == expected
    changed_index = {
        **_cell_index(),
        coordinate: replace(
            _cell_index()[coordinate], raw_value="unexpected publisher layout"
        ),
    }
    with pytest.raises(ValueError, match=re.escape(label)):
        resolve_source_record(_cells(), spec, cells_by_sheet_address=changed_index)


@pytest.mark.parametrize(
    "mutation",
    [
        "scale",
        "divisor",
        "range",
        "rounding",
        "period",
        "labels",
        "population",
        "median",
    ],
)
def test_household_net_worth_mutated_yaml_cannot_cross_publisher_boundaries(
    tmp_path, mutation
):
    payload = yaml.safe_load(
        (REPO_ROOT / "packages" / DIRECTORY / "source_package.yaml").read_text()
    )
    first = payload["record_sets"][0]
    if mutation == "scale":
        first["measures"][0]["value_scale"] = 1000
    elif mutation == "divisor":
        first["measures"][0]["divisor_column"] = "G"
    elif mutation == "range":
        first["rows"][0]["row_end_number"] = 11
    elif mutation == "rounding":
        first["measures"][0]["round_to"] = 100
    elif mutation == "period":
        first["period"] = 2024
    elif mutation == "labels":
        del payload["dimension_labels"][PREFIX + "published_section"]
    elif mutation == "population":
        first["shared_filters"][PREFIX + "population_note"] = "All households"
    elif mutation == "median":
        first["measures"][0]["aggregation"] = "sum"
    path = tmp_path / "source_package.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    mutated = load_source_package(path)
    with pytest.raises(AssertionError):
        _assert_frozen_package(mutated)


def _build_digests(cells, facts):
    def digest(items):
        return hashlib.sha256("\n".join(items).encode()).hexdigest()

    return {
        "source_cells": digest(
            json.dumps(asdict(cell), sort_keys=True, default=str) for cell in cells
        ),
        "facts": digest(
            json.dumps(asdict(fact), sort_keys=True, default=str) for fact in facts
        ),
        "consumer_rows": digest(
            json.dumps(row, sort_keys=True) for row in consumer_fact_rows(facts)
        ),
    }


def test_household_net_worth_rebuild_is_deterministic_across_hash_seeds():
    expected = _build_digests(_cells(), _facts())
    script = f"""
import json
from chronicle.source_package import load_source_package
from tests.test_chronicle_nz_household_net_worth import _build_digests
package = load_source_package({ALIAS!r})
cells = package.build_source_cells(2024)
print(json.dumps(_build_digests(cells, package.build_facts(2024, cells=cells))))
"""
    for seed in ("1", "2"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        assert json.loads(result.stdout.splitlines()[-1]) == expected


def test_household_net_worth_build_suite_passes_all_source_acceptance_gates(tmp_path):
    report = build_source_suite(ALIAS, tmp_path / "suite", year=2024)
    assert report.valid
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
    assert not report.agent_acceptance.errors
    assert report.source_cells.cell_count == 31_534
    assert report.source_records.resolved_count == 1413
    assert report.source_records.lineage_coverage == 1
    assert report.consumer_facts.fact_count == 1413
    assert report.agent_acceptance.counts["raw_artifact_count"] == 1
    assert report.agent_acceptance.counts["raw_r2_link_count"] == 1
