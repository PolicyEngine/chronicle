"""Independent publisher-row fidelity for 2023 Census weekly household rent."""

from __future__ import annotations

import csv
import hashlib
import os
import shutil
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

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
from chronicle.sources import build_source_cell_key, validate_source_cells
from chronicle.sources.rows import build_source_row_key, validate_source_rows
from chronicle.sources.specs import resolve_source_record
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIRECTORY = REPO_ROOT / "db/data/stats_nz/census_2023_place_summaries"
FAMILY_DIRECTORY = Path("stats_nz/census_2023_weekly_rent")
BAND_DIMENSION = "nz_census_2023.weekly_rent_source_label"
MEDIAN_DIMENSION = "nz_census_2023.weekly_rent_statistic"

# Literal publisher identities, independently audited against all 18 unchanged
# exports. These expectations are never assembled from package YAML.
PLACES = (
    (
        "NZ",
        "New Zealand",
        "6b35e4339ab98bd85dcfa0d297f9bf2c88403327dfe70430513cb7c10b26d89b",
    ),
    (
        "01",
        "Northland Region",
        "7eb81d38c4b3837c21d056ac772b91b4397ee4c1b26146a665deb373d847520f",
    ),
    (
        "02",
        "Auckland Region",
        "8146e6612b8a0434f021b02f096cd0befaa450fdab0f5c09325201586ae001bc",
    ),
    (
        "03",
        "Waikato Region",
        "d4f378940be75e0a138282bd55368b232e4eacb5ea347184f1b4b7abd2deb694",
    ),
    (
        "04",
        "Bay of Plenty Region",
        "fc75a24d8538450f98c8a4485a6c7816fb3b5d697ea363ad55b6ca88bcfde739",
    ),
    (
        "05",
        "Gisborne Region",
        "82f57517ccd7a22f953dc6ea5137d5e8f70248f762674a85bd33e0f8cf34285c",
    ),
    (
        "06",
        "Hawke's Bay Region",
        "ecd9485974efcc936ebacc452647b2597e6f37cf6386d328c88587fba66dcc46",
    ),
    (
        "07",
        "Taranaki Region",
        "96ff9f1943d9200a3096b965bc510e1b369016128388ac43a202504d99fa986f",
    ),
    (
        "08",
        "Manawatū-Whanganui Region",
        "c693e64b4194d507647b5ba35af4675df9fb44af64de40fd1ce399a37af396b5",
    ),
    (
        "09",
        "Wellington Region",
        "38cc255b43303a31f45cdfbf2ba8c4b9c8e367eaaf50e76c1388d3085cc08900",
    ),
    (
        "12",
        "West Coast Region",
        "42148ea27b7a7906b963b4ee29552f7826c5149c6ecd62459099f80ecc20e4ae",
    ),
    (
        "13",
        "Canterbury Region",
        "a4d8c4b9eaff633904419ed95dccc4e1bf5f64fd964020af06a006b269c9e8af",
    ),
    (
        "14",
        "Otago Region",
        "3491f761dd689c4a2cce52ebe950e9af97ad184e99b589a53bb9b40685c2b1e8",
    ),
    (
        "15",
        "Southland Region",
        "68fb9522adc00d9d195a8dd77c51d781f69d9a292ac8db3f6e6931064165cc78",
    ),
    (
        "16",
        "Tasman Region",
        "d06b59112aac85f051665fcdc99d470508c8bfa7223e103bcd79fbd7d3155c1a",
    ),
    (
        "17",
        "Nelson Region",
        "26a51a71c1ad40df12f04c58a164d029f41d565c32a201424e1edb8cf2e32341",
    ),
    (
        "18",
        "Marlborough Region",
        "92533df51e133c0c47bf24e0a28f2ee68aecaf737f65ec8d9e5d5bf72f697b44",
    ),
    (
        "99",
        "Area Outside Region",
        "6ee21b3170d89e29fb7ea3ee3986c9ff14860e99be1b230e64432a6c024c9369",
    ),
)
PLACE_BY_CODE = {place[0]: place for place in PLACES}

# Record set, value ID, section, variable label/code/category, physical CSV line,
# value type, unit, aggregation and published value label. The table median on
# line 1763 is pinned, so its identical quick-stat row on line 13 cannot replace it.
PUBLISHED_ROWS = (
    (
        "weekly_rent",
        "1",
        "Weekly rent paid by households",
        "Weekly rent paid by household",
        "1",
        "Under $200",
        1766,
        "Count",
        "count",
        "sum",
        "",
    ),
    (
        "weekly_rent",
        "2",
        "Weekly rent paid by households",
        "Weekly rent paid by household",
        "2",
        "$200 - $299",
        1767,
        "Count",
        "count",
        "sum",
        "",
    ),
    (
        "weekly_rent",
        "3",
        "Weekly rent paid by households",
        "Weekly rent paid by household",
        "3",
        "$300 - $399",
        1768,
        "Count",
        "count",
        "sum",
        "",
    ),
    (
        "weekly_rent",
        "4",
        "Weekly rent paid by households",
        "Weekly rent paid by household",
        "4",
        "$400 - $499",
        1769,
        "Count",
        "count",
        "sum",
        "",
    ),
    (
        "weekly_rent",
        "5",
        "Weekly rent paid by households",
        "Weekly rent paid by household",
        "5",
        "$500 - $599",
        1770,
        "Count",
        "count",
        "sum",
        "",
    ),
    (
        "weekly_rent",
        "6",
        "Weekly rent paid by households",
        "Weekly rent paid by household",
        "6",
        "$600 - $699",
        1771,
        "Count",
        "count",
        "sum",
        "",
    ),
    (
        "weekly_rent",
        "7",
        "Weekly rent paid by households",
        "Weekly rent paid by household",
        "7",
        "$700 - $799",
        1772,
        "Count",
        "count",
        "sum",
        "",
    ),
    (
        "weekly_rent",
        "8",
        "Weekly rent paid by households",
        "Weekly rent paid by household",
        "8",
        "$800 and over",
        1773,
        "Count",
        "count",
        "sum",
        "",
    ),
    (
        "median_weekly_rent",
        "median",
        "Median weekly rent paid by households",
        "",
        "",
        "",
        1763,
        "Median",
        "nzd_per_week",
        "median",
        "dollars",
    ),
)

HEADERS = (
    "section_title",
    "section_type",
    "classification_label",
    "code",
    "descriptor",
    "period",
    "duration",
    "variable1_label",
    "variable1_code",
    "variable1_descriptor",
    "variable2_label",
    "variable2_code",
    "variable2_descriptor",
    "value_type_description",
    "value",
    "value_label",
    "decimals",
    "confidentiality_indicator",
    "confidentiality_label",
    "final_indicator",
    "final_label",
    "last_updated_at_source",
)
GUARD_COLUMNS = tuple("ABCDEFGHIJKLMN") + tuple("PQRSTU")
GUARD_FIELDS = tuple(HEADERS[ord(column) - ord("A")] for column in GUARD_COLUMNS)
STATUS_FIELDS = (
    "confidentiality_indicator",
    "confidentiality_label",
    "final_indicator",
    "final_label",
)


def _suffix(code):
    return "nz" if code == "NZ" else f"rc_{code}"


def _alias(code):
    root = "stats-nz-census-2023-weekly-rent"
    return root if code == "NZ" else f"{root}-rc-{code}"


def _directory(code):
    return FAMILY_DIRECTORY if code == "NZ" else FAMILY_DIRECTORY / f"rc_{code}"


def _filename(code):
    return (
        "place-summaries-nz.csv" if code == "NZ" else f"place-summaries-rc-{code}.csv"
    )


def _record_id(code, row):
    measure = "count" if row[7] == "Count" else "median"
    return f"stats_nz.census_2023.{_suffix(code)}.{row[0]}.{row[1]}.{measure}"


def _label(row):
    return row[5] if row[7] == "Count" else row[2]


def _concept(row):
    return (
        "stats_nz.census_2023.household_count"
        if row[7] == "Count"
        else "stats_nz.census_2023.median_weekly_rent"
    )


def _text(value):
    return "" if value is None else str(value)


def _expected_selection(code, row):
    return dict(
        zip(
            GUARD_FIELDS,
            (
                row[2],
                "",
                "New Zealand" if code == "NZ" else "Regional council",
                "NZ" if code == "NZ" else str(int(code)),
                PLACE_BY_CODE[code][1],
                "2023",
                "Census",
                row[3],
                row[4],
                row[5],
                "",
                "",
                "",
                row[7],
                row[10],
                "0",
                "",
                "",
                "",
                "",
            ),
            strict=True,
        )
    )


def _expected_map(code):
    return {
        _record_id(code, row): (
            "NZ" if code == "NZ" else str(int(code)),
            row[2],
            "",
            row[3],
            row[4],
            row[5],
            "2023",
            "Census",
            row[7],
            row[10],
            row[6],
            PLACE_BY_CODE[code][2],
            f"place_summaries_{_suffix(code)}_weekly_rent",
            "O",
            row[8],
            1,
            row[9],
            "household",
            "Auckland" if code == "02" else PLACE_BY_CODE[code][1],
            _label(row),
            _concept(row),
        )
        for row in PUBLISHED_ROWS
    }


EXPECTED_OBSERVATIONS = {
    (code, record_id): identity
    for code, *_ in PLACES
    for record_id, identity in _expected_map(code).items()
}


@lru_cache
def _package(code):
    # An explicit scratch-only override supports external red mutation runs.
    scratch_root = os.environ.get("CHRONICLE_NZ_CENSUS_WEEKLY_RENT_TEST_ROOT")
    if scratch_root:
        candidate = Path(scratch_root) / _directory(code) / "source_package.yaml"
        if candidate.is_file():
            return load_source_package(candidate)
    return load_source_package(_alias(code))


@lru_cache
def _rows(code):
    return _package(code).build_source_rows(2023)


@lru_cache
def _cells(code):
    return _package(code).build_source_cells(2023, source_rows=_rows(code))


@lru_cache
def _specs(code):
    return _package(code).build_source_record_specs(2023)


@lru_cache
def _facts(code):
    return _package(code).build_facts(2023, cells=_cells(code), source_rows=_rows(code))


@lru_cache
def _publisher_rows(code):
    with (DATA_DIRECTORY / _filename(code)).open(
        newline="", encoding="utf-8-sig"
    ) as source:
        return dict(enumerate(csv.DictReader(source), start=2))


def _guard_index(spec):
    selector = spec.selector
    guards = {guard.address: guard.expected_value for guard in selector.guard_cells}
    for address, expected in (
        (selector.expected_row_header_address, selector.expected_row_header),
        (selector.expected_column_header_address, selector.expected_column_header),
    ):
        if address is not None:
            if address in guards:
                assert guards[address] == expected
            guards[address] = expected
    assert not selector.range_label_guards
    return guards


def _assert_publisher_map(code, package=None):
    if package is None:
        rows, cells, specs = _rows(code), _cells(code), _specs(code)
    else:
        rows = package.build_source_rows(2023)
        cells = package.build_source_cells(2023, source_rows=rows)
        specs = package.build_source_record_specs(2023)
    cell_index = {(cell.sheet_name, cell.address): cell for cell in cells}
    row_index = {build_source_row_key(row): row for row in rows}
    actual = {}
    for spec in specs:
        cell = cell_index[spec.selector.sheet_name, spec.selector.address]
        row = row_index[cell.source_row_key]
        values = row.values
        actual[spec.source_record_id] = (
            _text(values["code"]),
            values["section_title"],
            _text(values["section_type"]),
            _text(values["variable1_label"]),
            _text(values["variable1_code"]),
            _text(values["variable1_descriptor"]),
            _text(values["period"]),
            values["duration"],
            values["value_type_description"],
            _text(values["value_label"]),
            row.row_number,
            row.artifact.sha256,
            spec.selector.sheet_name,
            spec.selector.address.rstrip("0123456789"),
            spec.unit,
            spec.value_scale,
            spec.aggregation,
            spec.entity,
            spec.geography_name,
            spec.layout.groupby_value_label,
            spec.concept,
        )
    expected = _expected_map(code)
    assert len(specs) == len(actual) == len(expected) == 9
    assert set(actual) == set(expected)
    for record_id, identity in expected.items():
        assert actual[record_id] == identity, (
            f"{record_id}: selected {actual[record_id]!r}; expected {identity!r}"
        )


@pytest.mark.parametrize("code", [place[0] for place in PLACES])
def test_weekly_rent_package_validation_and_independent_publisher_map(code):
    assert SOURCE_PACKAGE_ALIASES[_alias(code)] == _directory(code)
    assert _package(code).package_id == _alias(code)
    _assert_publisher_map(code)
    report = validate_source_package(_package(code).package_path, year=2023)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["source_record_count"] == 9


@pytest.mark.parametrize("code", [place[0] for place in PLACES])
def test_weekly_rent_preserves_complete_publisher_bytes_and_r2_identity(code):
    path = DATA_DIRECTORY / _filename(code)
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == PLACE_BY_CODE[code][2]
    assert len(content.splitlines(keepends=True)) == 2031
    assert all(line.endswith(b"\r\n") for line in content.splitlines(keepends=True))
    assert tuple(_publisher_rows(code)[2]) == HEADERS
    manifest_name = "manifest-nz.yaml" if code == "NZ" else f"manifest-rc-{code}.yaml"
    manifest = yaml.safe_load((DATA_DIRECTORY / manifest_name).read_text())
    receipt = manifest["files"][2023]
    assert receipt["sha256"] == PLACE_BY_CODE[code][2]
    assert receipt["filename"] == _filename(code)
    assert receipt["size_bytes"] == len(content)
    assert _package(code).artifact.manifest == manifest_name
    assert (
        _package(code).artifact.resource_directory
        == "data/stats_nz/census_2023_place_summaries"
    )
    assert {fact.source.url for fact in _facts(code)} == {receipt["source_url"]}
    assert {fact.source.raw_r2_uri for fact in _facts(code)} == {
        receipt["storage"]["r2"]["uri"]
    }


@pytest.mark.parametrize("code", [place[0] for place in PLACES])
def test_weekly_rent_every_fact_has_one_unscaled_publisher_row_and_status_lineage(code):
    rows, cells, facts = _rows(code), _cells(code), _facts(code)
    assert _package(code).artifact.parser == "delimited_text_full_rows"
    assert len(rows) == 2030
    assert len(cells) == 220
    assert len(facts) == 9
    assert validate_source_rows(rows).valid
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert {fact.provenance_class for fact in facts} == {"census"}
    assert {fact.assertion for fact in facts} == {"observation"}
    cell_index = {(cell.sheet_name, cell.address): cell for cell in cells}
    row_index = {build_source_row_key(row): row for row in rows}
    specs = {spec.source_record_id: spec for spec in _specs(code)}
    for fact in facts:
        spec = specs[fact.source_record_id]
        selector = spec.selector
        cell = cell_index[selector.sheet_name, selector.address]
        row = row_index[cell.source_row_key]
        assert selector.end_address is None
        assert spec.divisor_selector is None
        assert spec.round_to is None
        assert spec.value_scale == 1
        assert fact.aggregation.denominator is None
        assert fact.measure.concept_relation == "source_label"
        assert Decimal(str(fact.value)) == Decimal(str(row.values["value"]))
        assert Decimal(str(fact.value)) == Decimal(
            _publisher_rows(code)[row.row_number]["value"]
        )
        assert fact.source_row_keys == (cell.source_row_key,)
        assert build_source_cell_key(cell) in fact.source_cell_keys
        for address in _guard_index(spec):
            assert (
                build_source_cell_key(cell_index[selector.sheet_name, address])
                in fact.source_cell_keys
            )
        assert all(row.values[field] is None for field in STATUS_FIELDS)
        assert str(row.values["period"]) == "2023"
        assert "Māori" not in row.values["section_title"]
        if row.values["value_type_description"] == "Count":
            assert fact.measure.unit == "count"
            assert fact.aggregation.method == "sum"
            assert fact.layout.groupby_value_label == row.values["variable1_descriptor"]
        else:
            assert row.values["value_type_description"] == "Median"
            assert row.row_number == 1763
            assert fact.measure.unit == "nzd_per_week"
            assert fact.aggregation.method == "median"
            assert (
                fact.layout.groupby_value_label
                == "Median weekly rent paid by households"
            )


def test_weekly_rent_all_162_observations_and_labels_are_independent():
    assert len(EXPECTED_OBSERVATIONS) == 162
    facts = []
    for code, *_ in PLACES:
        _assert_publisher_map(code)
        assert _dimension_label_reports(
            _alias(code), consumer_fact_rows(_facts(code))
        ) == ([], [])
        facts.extend(_facts(code))
    assert len(facts) == 162
    assert Counter(fact.entity.name for fact in facts) == {"household": 162}
    assert Counter(fact.geography.id for fact in facts) == {
        "NZ" if code == "NZ" else code: 9 for code, *_ in PLACES
    }
    assert Counter(fact.measure.unit for fact in facts) == {
        "count": 144,
        "nzd_per_week": 18,
    }
    coverage = build_bundle_coverage(consumer_fact_rows(facts))
    assert not coverage["duplicates"]["aggregate_fact_keys"]
    assert not coverage["duplicates"]["semantic_fact_keys"]


@pytest.mark.parametrize("code", [place[0] for place in PLACES])
def test_weekly_rent_every_selection_and_nonblank_guard_matches_literals(code):
    specs = {spec.source_record_id: spec for spec in _specs(code)}
    assert tuple(
        {field: str(value) for field, value in criteria.items()}
        for criteria in _package(code).artifact.selected_rows
    ) == tuple(_expected_selection(code, row) for row in PUBLISHED_ROWS)
    for virtual_row, row in enumerate(PUBLISHED_ROWS, start=2):
        spec = specs[_record_id(code, row)]
        expected = {
            f"{column}{virtual_row}": value
            for column, field in zip(GUARD_COLUMNS, GUARD_FIELDS, strict=True)
            if (value := _expected_selection(code, row)[field]) != ""
        } | {"O1": "value"}
        assert {
            address: str(value) for address, value in _guard_index(spec).items()
        } == expected
        assert spec.selector.expected_row_header_address == (
            f"J{virtual_row}" if row[7] == "Count" else f"A{virtual_row}"
        )


@pytest.mark.parametrize("guard_field", GUARD_FIELDS)
def test_weekly_rent_each_selection_guard_refuses_changed_or_flagged_source_row(
    guard_field,
):
    checked = 0
    physical_rows = {row[6] for row in PUBLISHED_ROWS}
    for code, *_ in PLACES:
        selected = [row for row in _rows(code) if row.row_number in physical_rows]
        assert len(selected) == 9
        for target in selected:
            changed = [
                replace(
                    row, values={**row.values, guard_field: "CONFIDENTIAL_OR_CHANGED"}
                )
                if row is target
                else row
                for row in selected
            ]
            with pytest.raises(ValueError, match="matched 0 rows"):
                _package(code).build_source_cells(2023, source_rows=changed)
            checked += 1
    assert checked == 162


@pytest.mark.parametrize(
    "guard_column", ("A", "C", "D", "E", "F", "G", "H", "I", "J", "N", "P", "Q", "O1")
)
def test_weekly_rent_nonblank_cell_guards_refuse_changed_cells(guard_column):
    checked = 0
    for code, *_ in PLACES:
        cell_index = {(cell.sheet_name, cell.address): cell for cell in _cells(code)}
        for spec in _specs(code):
            virtual_row = spec.selector.address.lstrip("O")
            address = "O1" if guard_column == "O1" else f"{guard_column}{virtual_row}"
            if address not in _guard_index(spec):
                continue  # The median has blank H/I/J; bands have blank P.
            coordinate = spec.selector.sheet_name, address
            changed = dict(cell_index)
            changed[coordinate] = replace(
                cell_index[coordinate],
                raw_value="CHANGED",
                cell_type="text",
                display_value="CHANGED",
            )
            with pytest.raises(ValueError, match="expected"):
                resolve_source_record(list(changed.values()), spec)
            checked += 1
    assert checked == (
        144 if guard_column in "HIJ" else 18 if guard_column == "P" else 162
    )


@pytest.mark.parametrize("code", [place[0] for place in PLACES])
def test_weekly_rent_source_dimensions_labels_period_and_geographies(code):
    facts = _facts(code)
    row_index = {build_source_row_key(row): row for row in _rows(code)}
    assert [
        (fact.source_record_id, fact.value)
        for fact in _package(code).build_facts(
            2025,
            cells=_cells(code),
            source_rows=_rows(code),
        )
    ] == [(fact.source_record_id, fact.value) for fact in facts]
    for fact in facts:
        row = row_index[fact.source_row_keys[0]]
        band = row.values["value_type_description"] == "Count"
        dimension = BAND_DIMENSION if band else MEDIAN_DIMENSION
        assert fact.layout.groupby_dimension == dimension
        assert fact.dimension_labels[dimension] == (
            "Weekly rent paid by household"
            if band
            else "Published weekly rent statistic"
        )
        assert (
            fact.dimension_value_labels[dimension][str(fact.layout.groupby_value_id)]
            == fact.layout.groupby_value_label
        )
        expected_filters = {dimension: row.values["variable1_code"]} if band else {}
        assert fact.filters == expected_filters
        assert {
            constraint.variable: constraint.value for constraint in fact.constraints
        } == expected_filters
        assert all(constraint.operator == "==" for constraint in fact.constraints)
        assert (fact.period.type, fact.period.value) == ("calendar_year", 2023)
        assert (fact.period_coverage.start_date, fact.period_coverage.end_date) == (
            "2023-03-07",
            "2023-03-07",
        )
        assert fact.geography.id == ("NZ" if code == "NZ" else code)
        assert fact.geography.level == ("country" if code == "NZ" else "region")
        assert fact.geography.name == (
            "Auckland" if code == "02" else PLACE_BY_CODE[code][1]
        )
        assert fact.geography.vintage == ("current" if code == "NZ" else "unstated")


def test_weekly_rent_sheet_identity_does_not_collide_with_shared_families():
    for code, *_ in PLACES:
        rent_cells = {build_source_cell_key(cell) for cell in _cells(code)}
        rent_rows = {build_source_row_key(row) for row in _rows(code)}
        for family in ("households-by-region", "family-type"):
            alias = f"stats-nz-census-2023-{family}"
            if code != "NZ":
                alias += f"-rc-{code}"
            other = load_source_package(alias)
            other_rows = other.build_source_rows(2023)
            other_cells = other.build_source_cells(2023, source_rows=other_rows)
            assert rent_cells.isdisjoint(
                build_source_cell_key(cell) for cell in other_cells
            )
            assert rent_rows.isdisjoint(build_source_row_key(row) for row in other_rows)
            assert {row.artifact.sha256 for row in other_rows} == {
                PLACE_BY_CODE[code][2]
            }


@pytest.mark.parametrize("code", [place[0] for place in PLACES])
def test_weekly_rent_identical_median_rows_are_distinguished_by_identity(code):
    publisher = _publisher_rows(code)
    assert publisher[13]["section_type"] == "Quick stats"
    assert publisher[1763]["section_type"] == ""
    assert publisher[13]["value"] == publisher[1763]["value"]
    median = next(fact for fact in _facts(code) if fact.measure.unit == "nzd_per_week")
    assert median.value == Decimal(publisher[1763]["value"])
    assert (
        len([fact for fact in _facts(code) if fact.measure.unit == "nzd_per_week"]) == 1
    )


@pytest.fixture
def mutated_weekly_rent_package():
    def mutate(kind):
        package = _package("02")
        selections = deepcopy(package.artifact.selected_rows)
        record_sets = package.record_sets
        artifact_overrides = {}
        if kind == "percent-instead-of-count":
            selections[0].update(
                value_type_description="Percent", value_label="percent", decimals=1
            )
        elif kind == "2018-instead-of-2023":
            # Rent bands are published only for 2023; the independently
            # published 2018 median on physical line 1762 is the historical
            # substitute that exercises an actual publisher row.
            selections[8].update(period=2018)
        elif kind == "northland-file-for-auckland":
            artifact_overrides["manifest"] = "manifest-rc-01.yaml"
            for selection in selections:
                selection.update(code=1, descriptor="Northland Region")
        elif kind == "maori-instead-of-total-population":
            selections[0].update(
                section_title="Weekly rent paid by households for the Māori ethnic group"
            )
        elif kind == "quick-stat-instead-of-table-median":
            selections[8].update(section_type="Quick stats")
        elif kind == "band-relabelled-as-neighbour":
            payload = deepcopy(record_sets[0].payload)
            payload["rows"][0]["label"] = "$200 - $299"
            record_sets = (replace(record_sets[0], payload=payload), *record_sets[1:])
        else:
            raise AssertionError(kind)
        artifact = replace(
            package.artifact, selected_rows=selections, **artifact_overrides
        )
        return replace(package, artifact=artifact, record_sets=record_sets)

    return mutate


@pytest.mark.parametrize(
    "kind",
    (
        "percent-instead-of-count",
        "2018-instead-of-2023",
        "northland-file-for-auckland",
        "maori-instead-of-total-population",
        "quick-stat-instead-of-table-median",
        "band-relabelled-as-neighbour",
    ),
)
def test_weekly_rent_independent_map_rejects_six_mutants(
    mutated_weekly_rent_package, kind
):
    with pytest.raises(AssertionError, match="selected"):
        _assert_publisher_map("02", mutated_weekly_rent_package(kind))


@pytest.mark.parametrize(
    ("code", "value_id", "expected"),
    (
        ("NZ", "1", 89439),
        ("NZ", "2", 53325),
        ("NZ", "3", 80247),
        ("NZ", "4", 101067),
        ("NZ", "5", 99042),
        ("NZ", "6", 68544),
        ("NZ", "7", 32286),
        ("NZ", "8", 35712),
        ("NZ", "median", 450),
        ("02", "1", 28113),
        ("02", "2", 9909),
        ("02", "3", 16734),
        ("02", "4", 28827),
        ("02", "5", 42645),
        ("02", "6", 37143),
        ("02", "7", 19629),
        ("02", "8", 22899),
        ("02", "median", 540),
    ),
)
def test_weekly_rent_exact_publisher_cells(code, value_id, expected):
    published = next(row for row in PUBLISHED_ROWS if row[1] == value_id)
    fact = next(
        fact
        for fact in _facts(code)
        if fact.source_record_id == _record_id(code, published)
    )
    assert Decimal(_publisher_rows(code)[published[6]]["value"]) == expected
    assert fact.value == expected
    assert fact.layout.groupby_value_label == _label(published)


@pytest.mark.parametrize("code", [place[0] for place in PLACES])
def test_weekly_rent_all_member_source_suites_validate_contract_and_preservation(
    tmp_path, code
):
    output = tmp_path / _alias(code)
    try:
        report = build_source_suite(_package(code).package_path, output, year=2023)
        assert report.valid, report.to_dict()
        assert report.source_rows.row_count == 2030
        assert report.facts.fact_count == report.consumer_facts.fact_count == 9
        assert report.source_records.lineage_coverage == 1
        assert report.agent_acceptance.valid
        assert all(report.agent_acceptance.checks.values())
    finally:
        # Only one small single-source suite is retained at a time.
        shutil.rmtree(output, ignore_errors=True)
