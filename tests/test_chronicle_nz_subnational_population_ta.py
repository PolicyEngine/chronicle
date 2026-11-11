"""Independent publisher-cell gates for the 30 June 2025 TA population facts."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import unicodedata

import openpyxl
import pytest
import yaml

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
from chronicle.sources.specs import (
    build_cells_by_sheet_address,
    resolve_source_record,
)


ALIAS = "stats-nz-subnational-population-ta-2025"
REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = REPO_ROOT / "packages/stats_nz/subnational_population_ta_2025"
DATA_ROOT = REPO_ROOT / "db/data/stats_nz"
WORKBOOK_PATH = (
    DATA_ROOT
    / "subnational_population_estimates_2025"
    / "subnational-population-estimates-at-30-june-2025-provisional.xlsx"
)
CLASSIFICATION_PATH = (
    DATA_ROOT
    / "territorial_authority_2025_codes"
    / "territorial-authority-2025-codes.json"
)
WORKBOOK_SHA256 = "001e8a896cfb50f5ed17836dc815b235e3bcca55ee91c9869a2afaeb054b50a6"
CLASSIFICATION_SHA256 = (
    "db033184db1f64bd4c53b0cf070cac3303815f20c9cc428e11389b91033dc225"
)
SHEET = "Table 2"
SHARED_GUARDS = {
    "A3": "Territorial authority and Auckland local board areas",
    "A4": "At 30 June 2023–2025",
    "A5": "Territorial authority and Auckland local board area(2)",
    "E6": "2025 P",
    "A100": "2. Boundaries at 1 January 2025.",
    "A105": "P provisional",
}
SAMPLES = (
    (8, "Far North district", "001", 73_700),
    (9, "Whangārei district", "002", 100_600),
    (11, "Auckland", "076", 1_816_000),
    (37, "Hamilton city", "016", 192_100),
    (42, "Taupō district", "021", 42_700),
    (68, "Wellington city", "047", 210_800),
    (81, "Christchurch city", "060", 419_200),
    (87, "Chatham Islands territory", "067", 620),
    (90, "Queenstown-Lakes district", "070", 53_800),
    (95, "Invercargill city", "075", 58_000),
)


def _ascii_name(value):
    return "".join(
        character
        for character in unicodedata.normalize("NFD", value)
        if not unicodedata.combining(character)
    ).casefold()


@lru_cache
def _publisher_evidence():
    """Read expected codes, labels and values without consulting package YAML."""
    classification = json.loads(CLASSIFICATION_PATH.read_bytes())
    assert not classification.get("exceededTransferLimit", False)
    attributes = [feature["attributes"] for feature in classification["features"]]
    assert len(attributes) == 68
    by_code = {item["TA2025_V1_00"]: item for item in attributes}
    by_name = {item["TA2025_V1_00_NAME_ASCII"].casefold(): item for item in attributes}
    assert len(by_code) == len(by_name) == 68
    assert "999" in by_code

    workbook = openpyxl.load_workbook(WORKBOOK_PATH, data_only=True)
    try:
        sheet = workbook[SHEET]
        values = {cell.coordinate: cell.value for row in sheet for cell in row}
        expected = {}
        local_boards = {}
        for row_number in range(8, 96):
            label = sheet[f"A{row_number}"].value
            if label is None:
                local_boards[row_number] = sheet[f"B{row_number}"].value
                continue
            # Match the publisher's name, not its position in the classification.
            item = by_name[_ascii_name(label)]
            geography_id = f"nz-ta-{item['TA2025_V1_00']}"
            assert geography_id not in expected
            expected[geography_id] = {
                "row": row_number,
                "label": label,
                "name": item["TA2025_V1_00_NAME"],
                "value": sheet[f"E{row_number}"].value,
            }
        assert len(expected) == 67
        assert set(expected) == {f"nz-ta-{code}" for code in by_code if code != "999"}
        assert set(local_boards) == set(range(12, 33))
        assert all("local board area" in label for label in local_boards.values())
        return expected, local_boards, values
    finally:
        workbook.close()


# Coordinates come from publisher evidence, so deleting YAML guards cannot
# silently delete their regression cases.
EXPECTED_GUARDS = {
    **SHARED_GUARDS,
    **{f"A{item['row']}": item["label"] for item in _publisher_evidence()[0].values()},
}


@pytest.fixture(scope="module")
def population():
    package = load_source_package(PACKAGE_PATH)
    cells = package.build_source_cells(2025)
    facts = package.build_facts(2025, cells=cells)
    return package, cells, facts


def _facts_by_id(facts):
    result = {fact.geography.id: fact for fact in facts}
    assert len(result) == len(facts) == 67
    return result


def _guard_index(specs):
    guards = {}
    for spec in specs:
        selector = spec.selector
        assert selector.sheet_name == SHEET
        assert not selector.range_label_guards
        entries = (
            (selector.expected_row_header_address, selector.expected_row_header),
            (selector.expected_column_header_address, selector.expected_column_header),
            *((guard.address, guard.expected_value) for guard in selector.guard_cells),
        )
        for address, expected in entries:
            if address is None:
                continue
            if address in guards:
                assert guards[address][1] == expected
            else:
                guards[address] = (spec, expected)
    return guards


@pytest.mark.parametrize(
    ("path", "expected_sha", "expected_size"),
    (
        (WORKBOOK_PATH, WORKBOOK_SHA256, 97_990),
        (CLASSIFICATION_PATH, CLASSIFICATION_SHA256, 14_315),
    ),
    ids=("workbook", "classification"),
)
def test_publisher_bytes_and_manifests_remain_pinned(path, expected_sha, expected_size):
    content = path.read_bytes()
    manifest = yaml.safe_load((path.parent / "manifest.yaml").read_text())
    entry = manifest["files"][2025]
    assert hashlib.sha256(content).hexdigest() == entry["sha256"] == expected_sha
    assert len(content) == entry["size_bytes"] == expected_size
    assert entry["filename"] == path.name
    assert entry["storage"]["r2"]["uri"].startswith(
        f"r2://ledger-raw/raw/nz/stats_nz/{path.parent.name}/2025/{expected_sha}/"
    )


def test_package_validates_and_preserves_the_complete_table_2(population):
    package, cells, facts = population
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == Path(
        "stats_nz/subnational_population_ta_2025"
    )
    assert load_source_package(ALIAS).package_path == package.package_path
    report = validate_source_package(PACKAGE_PATH, year=2025)
    assert report.valid
    assert not report.warnings
    assert report.counts["source_record_count"] == len(facts) == 67
    assert package.artifact.sheets == (SHEET,)
    assert len(cells) == 106 * 21 == 2_226
    assert {cell.sheet_name for cell in cells} == {SHEET}
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid


def test_every_ta_fact_matches_independent_publisher_mapping(population):
    package, cells, facts = population
    expected, _boards, _values = _publisher_evidence()
    actual = _facts_by_id(facts)
    assert actual.keys() == expected.keys()
    cells_by_key = {build_source_cell_key(cell): cell for cell in cells}
    specs_by_record = {
        spec.source_record_id: spec for spec in package.build_source_record_specs(2025)
    }
    selected_keys = set()
    for geography_id, item in expected.items():
        fact = actual[geography_id]
        spec = specs_by_record[fact.source_record_id]
        assert fact.value == item["value"]
        assert type(fact.value) is int
        assert fact.geography.level == "local_authority"
        assert fact.geography.name == item["name"]
        assert fact.geography.vintage == "ta_2025"
        assert fact.layout.groupby_value_label == item["label"]
        assert fact.layout.groupby_value_id == geography_id
        assert fact.dimension_labels["geography"] == "Geography"
        assert fact.dimension_value_labels["geography"][geography_id] == item["label"]
        assert fact.layout.groupby_dimension_label == "Geography"
        assert spec.selector.sheet_name == SHEET
        assert spec.selector.address == f"E{item['row']}"
        assert spec.selector.expected_row_header_address == f"A{item['row']}"
        assert spec.selector.expected_row_header == item["label"]
        assert spec.selector.expected_column_header_address == "E6"
        assert spec.selector.expected_column_header == "2025 P"
        assert spec.selector.end_address is None
        assert spec.selector.expected_cell_type == "number"
        assert spec.value_scale == 1
        assert spec.divisor_selector is None
        assert spec.round_to is None
        value_cell, *context = [cells_by_key[key] for key in fact.source_cell_keys]
        assert (value_cell.sheet_name, value_cell.address) == (SHEET, f"E{item['row']}")
        assert value_cell.raw_value == fact.value
        assert all(type(cell.raw_value) is str for cell in context)
        selected_keys.add(fact.source_cell_keys[0])
        assert fact.source.source_sha256 == WORKBOOK_SHA256
        assert fact.measure.unit == "count"
        assert fact.aggregation.method == "sum"
    assert len(selected_keys) == 67


@pytest.mark.parametrize(
    ("row_number", "label", "code", "value"),
    SAMPLES,
    ids=[f"E{row}-{code}" for row, _label, code, _value in SAMPLES],
)
def test_ten_published_sample_cells(population, row_number, label, code, value):
    _package, cells, facts = population
    expected, _boards, values = _publisher_evidence()
    geography_id = f"nz-ta-{code}"
    fact = _facts_by_id(facts)[geography_id]
    cells_by_key = {build_source_cell_key(cell): cell for cell in cells}
    assert values[f"A{row_number}"] == label
    assert values[f"E{row_number}"] == expected[geography_id]["value"] == value
    assert fact.value == value
    assert fact.layout.groupby_value_label == label
    assert cells_by_key[fact.source_cell_keys[0]].address == f"E{row_number}"


def test_excludes_local_boards_outside_area_and_national_row(population):
    package, cells, facts = population
    expected, boards, values = _publisher_evidence()
    specs = package.build_source_record_specs(2025)
    selected = {spec.selector.address for spec in specs}
    assert selected == {f"E{item['row']}" for item in expected.values()}
    assert not selected & {f"E{row}" for row in boards}
    assert "E96" not in selected
    assert values["A96"] == "New Zealand(3)"
    assert values["E96"] == 5_324_700
    assert {fact.geography.id for fact in facts}.isdisjoint({"NZ", "999", "nz-ta-999"})
    assert not {fact.layout.groupby_value_label for fact in facts} & set(
        boards.values()
    )
    # All excluded rows, years and change columns remain in parsed source cells.
    addresses = {cell.address for cell in cells}
    assert {f"E{row}" for row in boards} | {"E96", "C8", "D8", "F8", "G8"} <= addresses


def test_auckland_reads_published_total_cell_without_local_board_arithmetic(population):
    _package, cells, facts = population
    cells_by_key = {build_source_cell_key(cell): cell for cell in cells}
    auckland = _facts_by_id(facts)["nz-ta-076"]
    assert auckland.value == 1_816_000
    assert cells_by_key[auckland.source_cell_keys[0]].address == "E11"
    assert not {cells_by_key[key].address for key in auckland.source_cell_keys} & {
        f"E{row}" for row in range(12, 33)
    }


def test_period_population_and_provisional_status_are_source_backed(population):
    _package, cells, facts = population
    cell_index = {build_source_cell_key(cell): cell for cell in cells}
    rows = consumer_fact_rows(facts)
    assert validate_consumer_fact_contract(facts).valid
    assert len({row["aggregate_fact_key"] for row in rows}) == 67
    assert len({row["semantic_fact_key"] for row in rows}) == 67
    for fact, row in zip(facts, rows, strict=True):
        assert fact.period.type == "calendar_year"
        assert fact.period.value == 2025
        coverage = fact.period_coverage
        assert coverage.start_date == coverage.end_date == "2025-06-30"
        assert coverage.basis == "calendar"
        assert coverage.source_period_label == "At 30 June 2025 (provisional)"
        assert fact.assertion == "observation"
        assert fact.provenance_class == "census"
        assert fact.entity.name == "person"
        assert fact.entity.role == "resident_population"
        assert not fact.filters
        assert not fact.constraints
        assert fact.measure.concept == "stats_nz.estimated_resident_population"
        assert fact.source.vintage == "stats_nz_subnational_population_2025_10_29"
        assert "Table 2" in fact.source.source_table
        assert (
            row["geography"]["name"]
            == _publisher_evidence()[0][fact.geography.id]["name"]
        )
        assert row["concept_alignment"]["relation"] == "source_label"
        notes = row["concept_alignment"]["evidence_notes"]
        assert "provisional" in notes.lower()
        assert "1 January 2025" in notes
        assert "2023 census" in notes
        lineage_addresses = {cell_index[key].address for key in fact.source_cell_keys}
        assert SHARED_GUARDS.keys() <= lineage_addresses


@pytest.mark.parametrize("build_year", (2023, 2025, 2026))
def test_requested_build_year_cannot_change_publisher_reference_period(
    population, build_year
):
    package, cells, facts = population
    assert package.artifact.artifact_year == 2025
    assert package.build_facts(build_year, cells=cells) == facts


def test_every_required_guard_is_declared_and_literal(population):
    package, _cells, _facts = population
    guards = _guard_index(package.build_source_record_specs(2025))
    assert len(EXPECTED_GUARDS) == 73
    assert EXPECTED_GUARDS.keys() <= guards.keys()
    for address, expected in EXPECTED_GUARDS.items():
        assert guards[address][1] == expected
        assert _publisher_evidence()[2][address] == expected


@pytest.mark.parametrize("address", sorted(EXPECTED_GUARDS))
def test_each_guard_rejects_mutated_source_cell(population, address):
    package, cells, _facts = population
    guards = _guard_index(package.build_source_record_specs(2025))
    assert address in guards
    spec, expected = guards[address]
    cell_index = build_cells_by_sheet_address(cells)
    assert cell_index[(SHEET, address)].raw_value == expected
    resolve_source_record(cells, spec, cells_by_sheet_address=cell_index)
    changed_index = {
        **cell_index,
        (SHEET, address): replace(
            cell_index[(SHEET, address)], raw_value="unexpected publisher layout"
        ),
    }
    with pytest.raises(ValueError, match="expected"):
        resolve_source_record(cells, spec, cells_by_sheet_address=changed_index)
