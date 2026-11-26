"""Independent row and cell fidelity for Stats NZ's 2023 Census place exports."""

from __future__ import annotations

import csv
import hashlib
import os
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

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
from chronicle.sources import build_source_cell_key, validate_source_cells
from chronicle.sources.rows import build_source_row_key, validate_source_rows
from chronicle.sources.specs import resolve_source_record
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIRECTORY = REPO_ROOT / "db/data/stats_nz/census_2023_place_summaries"
FAMILIES = ("households_by_region", "family_type")
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

# The identities below were audited from all 18 publisher CSVs. They are literal
# evidence independent of the package YAML, including physical source line numbers.
# The source publishes codes without leading zeroes; Chronicle's region IDs use two.
PLACES = (
    (
        "NZ",
        "New Zealand",
        "6b35e4339ab98bd85dcfa0d297f9bf2c88403327dfe70430513cb7c10b26d89b",
        394086,
        "2026-10-10T20:12:00Z",
        "place-summaries-new-zealand-20261011-080638.csv",
    ),
    (
        "01",
        "Northland Region",
        "7eb81d38c4b3837c21d056ac772b91b4397ee4c1b26146a665deb373d847520f",
        410926,
        "2026-10-10T20:12:01Z",
        "place-summaries-northland-region-20261011-091200.csv",
    ),
    (
        "02",
        "Auckland Region",
        "8146e6612b8a0434f021b02f096cd0befaa450fdab0f5c09325201586ae001bc",
        409747,
        "2026-10-10T20:12:01Z",
        "place-summaries-auckland-region-20261011-091008.csv",
    ),
    (
        "03",
        "Waikato Region",
        "d4f378940be75e0a138282bd55368b232e4eacb5ea347184f1b4b7abd2deb694",
        407261,
        "2026-10-10T20:12:02Z",
        "place-summaries-waikato-region-20261011-091201.csv",
    ),
    (
        "04",
        "Bay of Plenty Region",
        "fc75a24d8538450f98c8a4485a6c7816fb3b5d697ea363ad55b6ca88bcfde739",
        419296,
        "2026-10-10T20:12:02Z",
        "place-summaries-bay-of-plenty-region-20261011-091202.csv",
    ),
    (
        "05",
        "Gisborne Region",
        "82f57517ccd7a22f953dc6ea5137d5e8f70248f762674a85bd33e0f8cf34285c",
        408338,
        "2026-10-10T20:12:03Z",
        "place-summaries-gisborne-region-20261011-091203.csv",
    ),
    (
        "06",
        "Hawke's Bay Region",
        "ecd9485974efcc936ebacc452647b2597e6f37cf6386d328c88587fba66dcc46",
        414894,
        "2026-10-10T20:12:04Z",
        "place-summaries-hawke's-bay-region-20261011-091204.csv",
    ),
    (
        "07",
        "Taranaki Region",
        "96ff9f1943d9200a3096b965bc510e1b369016128388ac43a202504d99fa986f",
        408612,
        "2026-10-10T20:12:04Z",
        "place-summaries-taranaki-region-20261011-091204.csv",
    ),
    (
        "08",
        "Manawatū-Whanganui Region",
        "c693e64b4194d507647b5ba35af4675df9fb44af64de40fd1ce399a37af396b5",
        431319,
        "2026-10-10T20:12:05Z",
        "place-summaries-manawatu-whanganui-region-20261011-072623.csv",
    ),
    (
        "09",
        "Wellington Region",
        "38cc255b43303a31f45cdfbf2ba8c4b9c8e367eaaf50e76c1388d3085cc08900",
        413326,
        "2026-10-10T20:12:06Z",
        "place-summaries-wellington-region-20261011-091205.csv",
    ),
    (
        "12",
        "West Coast Region",
        "42148ea27b7a7906b963b4ee29552f7826c5149c6ecd62459099f80ecc20e4ae",
        414035,
        "2026-10-10T20:12:09Z",
        "place-summaries-west-coast-region-20261011-091208.csv",
    ),
    (
        "13",
        "Canterbury Region",
        "a4d8c4b9eaff633904419ed95dccc4e1bf5f64fd964020af06a006b269c9e8af",
        415340,
        "2026-10-10T20:12:10Z",
        "place-summaries-canterbury-region-20261011-091209.csv",
    ),
    (
        "14",
        "Otago Region",
        "3491f761dd689c4a2cce52ebe950e9af97ad184e99b589a53bb9b40685c2b1e8",
        404747,
        "2026-10-10T20:12:10Z",
        "place-summaries-otago-region-20261011-091210.csv",
    ),
    (
        "15",
        "Southland Region",
        "68fb9522adc00d9d195a8dd77c51d781f69d9a292ac8db3f6e6931064165cc78",
        412514,
        "2026-10-10T20:12:11Z",
        "place-summaries-southland-region-20261011-091211.csv",
    ),
    (
        "16",
        "Tasman Region",
        "d06b59112aac85f051665fcdc99d470508c8bfa7223e103bcd79fbd7d3155c1a",
        406093,
        "2026-10-10T20:12:06Z",
        "place-summaries-tasman-region-20261011-091206.csv",
    ),
    (
        "17",
        "Nelson Region",
        "26a51a71c1ad40df12f04c58a164d029f41d565c32a201424e1edb8cf2e32341",
        406118,
        "2026-10-10T20:12:07Z",
        "place-summaries-nelson-region-20261011-091207.csv",
    ),
    (
        "18",
        "Marlborough Region",
        "92533df51e133c0c47bf24e0a28f2ee68aecaf737f65ec8d9e5d5bf72f697b44",
        416244,
        "2026-10-10T20:12:08Z",
        "place-summaries-marlborough-region-20261011-091207.csv",
    ),
    (
        "99",
        "Area Outside Region",
        "6ee21b3170d89e29fb7ea3ee3986c9ff14860e99be1b230e64432a6c024c9369",
        417115,
        "2026-10-10T20:12:12Z",
        "place-summaries-area-outside-region-20261011-091211.csv",
    ),
)
PLACE_BY_CODE = {place[0]: place for place in PLACES}

# family, record set, value ID, section, variable label, publisher category code,
# exact publisher category text, physical CSV row. No selector is read to build it.
PUBLISHED_ROWS = (
    (
        "households_by_region",
        "households",
        "households",
        "Number of families and households",
        "Families or households",
        "H",
        "Households",
        1655,
    ),
    (
        "households_by_region",
        "tenure",
        "1",
        "Tenure of household",
        "Tenure of household",
        "1",
        "Owned",
        1733,
    ),
    (
        "households_by_region",
        "tenure",
        "2",
        "Tenure of household",
        "Tenure of household",
        "2",
        "Not owned",
        1736,
    ),
    (
        "households_by_region",
        "tenure",
        "3",
        "Tenure of household",
        "Tenure of household",
        "3",
        "In family trust",
        1739,
    ),
    (
        "households_by_region",
        "household_size",
        "1",
        "Number of usual residents in household",
        "Number of usual residents in household",
        "1",
        "One usual resident",
        1693,
    ),
    (
        "households_by_region",
        "household_size",
        "2",
        "Number of usual residents in household",
        "Number of usual residents in household",
        "2",
        "Two usual residents",
        1694,
    ),
    (
        "households_by_region",
        "household_size",
        "3",
        "Number of usual residents in household",
        "Number of usual residents in household",
        "3",
        "Three usual residents",
        1695,
    ),
    (
        "households_by_region",
        "household_size",
        "4",
        "Number of usual residents in household",
        "Number of usual residents in household",
        "4",
        "Four usual residents",
        1696,
    ),
    (
        "households_by_region",
        "household_size",
        "5",
        "Number of usual residents in household",
        "Number of usual residents in household",
        "5",
        "Five usual residents",
        1697,
    ),
    (
        "households_by_region",
        "household_size",
        "6",
        "Number of usual residents in household",
        "Number of usual residents in household",
        "6",
        "Six usual residents",
        1698,
    ),
    (
        "households_by_region",
        "household_size",
        "7",
        "Number of usual residents in household",
        "Number of usual residents in household",
        "7",
        "Seven usual residents",
        1699,
    ),
    (
        "households_by_region",
        "household_size",
        "8",
        "Number of usual residents in household",
        "Number of usual residents in household",
        "8",
        "Eight or more usual residents",
        1700,
    ),
    (
        "family_type",
        "families",
        "families",
        "Number of families and households",
        "Families or households",
        "F",
        "Families",
        1652,
    ),
    (
        "family_type",
        "family_type",
        "1",
        "Family type",
        "Family type",
        "1",
        "Couple Without Children",
        1662,
    ),
    (
        "family_type",
        "family_type",
        "2",
        "Family type",
        "Family type",
        "2",
        "Couple With Child(ren)",
        1665,
    ),
    (
        "family_type",
        "family_type",
        "3",
        "Family type",
        "Family type",
        "3",
        "One Parent With Child(ren)",
        1668,
    ),
)


def _place_suffix(code):
    return "nz" if code == "NZ" else f"rc_{code}"


def _filename(code):
    return (
        "place-summaries-nz.csv" if code == "NZ" else f"place-summaries-rc-{code}.csv"
    )


def _alias(family, code):
    root = f"stats-nz-census-2023-{family.replace('_', '-')}"
    return root if code == "NZ" else f"{root}-rc-{code}"


def _directory(family, code):
    root = Path(f"stats_nz/census_2023_{family}")
    return root if code == "NZ" else root / f"rc_{code}"


def _record_id(code, published_row):
    return f"stats_nz.census_2023.{_place_suffix(code)}.{published_row[1]}.{published_row[2]}.count"


def _expected_map(family, code):
    name, sha256 = PLACE_BY_CODE[code][1:3]
    geography_name = "Auckland" if code == "02" else name
    publisher_code = "NZ" if code == "NZ" else str(int(code))
    return {
        _record_id(code, row): (
            publisher_code,
            row[3],
            row[4],
            row[5],
            row[6],
            "2023",
            "Count",
            row[7],
            sha256,
            f"place_summaries_{_place_suffix(code)}_{'households' if family == 'households_by_region' else 'families'}",
            "O",
            "count",
            1,
            "sum",
            "household" if family == "households_by_region" else "family",
            geography_name,
        )
        for row in PUBLISHED_ROWS
        if row[0] == family
    }


EXPECTED_OBSERVATIONS = {
    (family, code, record_id): identity
    for family in FAMILIES
    for code, *_ in PLACES
    for record_id, identity in _expected_map(family, code).items()
}

# All 20 source identity/status columns and the value header must be guarded.
# Empty fields matter: introducing a confidentiality or not-available flag must fail.
GUARD_COLUMNS = (
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "I",
    "J",
    "K",
    "L",
    "M",
    "N",
    "P",
    "Q",
    "R",
    "S",
    "T",
    "U",
)
NONBLANK_GUARD_COLUMNS = ("A", "C", "D", "E", "F", "G", "H", "I", "J", "N", "Q")
GUARD_FIELDS = tuple(HEADERS[ord(column) - ord("A")] for column in GUARD_COLUMNS)
EXPECTED_DIMENSIONS = {
    "households": "nz_census_2023.total_kind",
    "families": "nz_census_2023.total_kind",
    "tenure": "nz_census_2023.household_tenure_source_label",
    "household_size": "nz_census_2023.household_size_source_label",
    "family_type": "nz_census_2023.family_type_source_label",
}


@lru_cache
def _package(family, code):
    # The override is for explicit red demonstrations on scratch YAML only.
    scratch_root = os.environ.get("CHRONICLE_NZ_CENSUS_TEST_ROOT")
    if scratch_root:
        candidate = (
            Path(scratch_root) / _directory(family, code) / "source_package.yaml"
        )
        if candidate.is_file():
            return load_source_package(candidate)
    return load_source_package(_alias(family, code))


@lru_cache
def _rows(family, code):
    return _package(family, code).build_source_rows(2023)


@lru_cache
def _cells(family, code):
    return _package(family, code).build_source_cells(
        2023, source_rows=_rows(family, code)
    )


@lru_cache
def _specs(family, code):
    return _package(family, code).build_source_record_specs(2023)


@lru_cache
def _facts(family, code):
    return _package(family, code).build_facts(
        2023, cells=_cells(family, code), source_rows=_rows(family, code)
    )


@lru_cache
def _publisher_rows(code):
    with (DATA_DIRECTORY / _filename(code)).open(
        newline="", encoding="utf-8-sig"
    ) as source:
        return dict(enumerate(csv.DictReader(source), start=2))


def _assert_publisher_map(family, code, package=None):
    if package is None:
        specs, cells, rows = (
            _specs(family, code),
            _cells(family, code),
            _rows(family, code),
        )
    else:
        rows = package.build_source_rows(2023)
        cells = package.build_source_cells(2023, source_rows=rows)
        specs = package.build_source_record_specs(2023)
    cell_index = {(cell.sheet_name, cell.address): cell for cell in cells}
    row_index = {build_source_row_key(row): row for row in rows}
    actual = {}
    for spec in specs:
        cell = cell_index[(spec.selector.sheet_name, spec.selector.address)]
        row = row_index[cell.source_row_key]
        values = row.values
        actual[spec.source_record_id] = (
            str(values["code"]),
            values["section_title"],
            values["variable1_label"],
            str(values["variable1_code"]),
            values["variable1_descriptor"],
            str(values["period"]),
            values["value_type_description"],
            row.row_number,
            row.artifact.sha256,
            spec.selector.sheet_name,
            spec.selector.address.rstrip("0123456789"),
            spec.unit,
            spec.value_scale,
            spec.aggregation,
            spec.entity,
            spec.geography_name,
        )
    expected = _expected_map(family, code)
    assert len(specs) == len(actual) == len(expected)
    assert set(actual) == set(expected)
    for record_id, identity in expected.items():
        assert actual[record_id] == identity, (
            f"{record_id}: selected {actual[record_id]!r}; expected {identity!r}"
        )


def _expected_guards(code, published_row, virtual_row):
    publisher_code = "NZ" if code == "NZ" else int(code)
    values = (
        published_row[3],
        None,
        "New Zealand" if code == "NZ" else "Regional council",
        publisher_code,
        PLACE_BY_CODE[code][1],
        2023,
        "Census",
        published_row[4],
        int(published_row[5]) if published_row[5].isdigit() else published_row[5],
        published_row[6],
        None,
        None,
        None,
        "Count",
        None,
        0,
        None,
        None,
        None,
        None,
    )
    return {
        f"{column}{virtual_row}": value
        for column, value in zip(GUARD_COLUMNS, values, strict=True)
    } | {"O1": "value"}


def _expected_selection(code, published_row):
    guards = _expected_guards(code, published_row, 2)
    return {
        field: "" if guards[f"{column}2"] is None else str(guards[f"{column}2"])
        for column, field in zip(GUARD_COLUMNS, GUARD_FIELDS, strict=True)
    }


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


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("code", [place[0] for place in PLACES])
def test_census_package_validation_and_independent_publisher_map(family, code):
    assert SOURCE_PACKAGE_ALIASES[_alias(family, code)] == _directory(family, code)
    assert _package(family, code).package_id == _alias(family, code)
    report = validate_source_package(_package(family, code).package_path, year=2023)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["source_record_count"] == (
        12 if family == "households_by_region" else 4
    )
    _assert_publisher_map(family, code)


@pytest.mark.parametrize("place", PLACES, ids=[place[0] for place in PLACES])
def test_census_artifact_receipts_complete_bytes_and_shared_r2_identity(place):
    code, _, sha256, size, fetched_at, disposition_filename = place
    path = DATA_DIRECTORY / _filename(code)
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == sha256
    assert path.stat().st_size == size
    lines = content.splitlines(keepends=True)
    assert len(lines) == 2031
    assert all(line.endswith(b"\r\n") for line in lines)
    assert (
        "*.csv binary" in (DATA_DIRECTORY / ".gitattributes").read_text().splitlines()
    )
    assert len(_publisher_rows(code)) == 2030
    assert tuple(_publisher_rows(code)[2]) == HEADERS
    manifest_name = "manifest-nz.yaml" if code == "NZ" else f"manifest-rc-{code}.yaml"
    manifest = yaml.safe_load((DATA_DIRECTORY / manifest_name).read_text())
    artifact = manifest["files"][2023]
    assert manifest["source_id"] == "stats_nz"
    assert manifest["package_id"] == "census_2023_place_summaries"
    assert manifest["license"] == "CC BY 4.0"
    url = (
        "https://tools.summaries.stats.govt.nz/api/export-csv/newzealand/NZ/"
        if code == "NZ"
        else f"https://tools.summaries.stats.govt.nz/api/export-csv/rkTah6u2O2VYyP4Y/{int(code)}/"
    )
    assert artifact["filename"] == _filename(code)
    assert artifact["source_url"] == url
    assert artifact["sha256"] == sha256
    assert artifact["size_bytes"] == size
    assert artifact["fetched_at"] == fetched_at
    assert artifact["content_disposition_filename"] == disposition_filename
    key = build_r2_key(
        source_id="stats_nz",
        package_id=manifest["package_id"],
        year=2023,
        sha256=sha256,
        filename=_filename(code),
        package_path=DATA_DIRECTORY,
    )
    assert (
        key
        == f"raw/nz/stats_nz/census_2023_place_summaries/2023/{sha256}/{_filename(code)}"
    )
    assert artifact["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }
    for family in FAMILIES:
        package = _package(family, code)
        assert (
            package.artifact.resource_directory
            == "data/stats_nz/census_2023_place_summaries"
        )
        assert package.artifact.manifest == manifest_name
        assert {fact.source.url for fact in _facts(family, code)} == {url}
        assert {fact.source.raw_r2_uri for fact in _facts(family, code)} == {
            f"r2://ledger-raw/{key}"
        }


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("code", [place[0] for place in PLACES])
def test_census_every_fact_is_one_unscaled_count_with_full_row_and_flag_lineage(
    family, code
):
    package, rows, cells, facts = (
        _package(family, code),
        _rows(family, code),
        _cells(family, code),
        _facts(family, code),
    )
    assert package.artifact.parser == "delimited_text_full_rows"
    assert len(rows) == 2030
    assert validate_source_rows(rows).valid
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert len(cells) == (len(facts) + 1) * 22
    assert {fact.provenance_class for fact in facts} == {"census"}
    assert {fact.assertion for fact in facts} == {"observation"}
    assert {fact.source.source_name for fact in facts} == {"stats_nz"}
    assert len({fact.source_record_id for fact in facts}) == len(facts)
    cell_index = {(cell.sheet_name, cell.address): cell for cell in cells}
    row_index = {build_source_row_key(row): row for row in rows}
    specs = {spec.source_record_id: spec for spec in _specs(family, code)}
    for fact in facts:
        spec = specs[fact.source_record_id]
        selector = spec.selector
        cell = cell_index[selector.sheet_name, selector.address]
        source_row = row_index[cell.source_row_key]
        assert selector.end_address is None
        assert spec.divisor_selector is None
        assert spec.round_to is None
        assert spec.value_scale == 1
        assert fact.measure.unit == "count"
        assert fact.aggregation.method == "sum"
        assert fact.aggregation.denominator is None
        assert fact.measure.concept_relation == "source_label"
        assert Decimal(str(fact.value)) == Decimal(str(source_row.values["value"]))
        assert Decimal(str(fact.value)) == Decimal(
            str(_publisher_rows(code)[source_row.row_number]["value"])
        )
        assert fact.source_row_keys == (cell.source_row_key,)
        assert build_source_cell_key(cell) in fact.source_cell_keys
        for address in _guard_index(spec):
            assert (
                build_source_cell_key(cell_index[selector.sheet_name, address])
                in fact.source_cell_keys
            )
        assert all(
            source_row.values[flag] is None
            for flag in (
                "confidentiality_indicator",
                "confidentiality_label",
                "final_indicator",
                "final_label",
            )
        )
        assert source_row.values["value_label"] is None
        assert (
            str(source_row.values["period"]),
            source_row.values["value_type_description"],
        ) == ("2023", "Count")
        assert (
            fact.layout.groupby_value_label == source_row.values["variable1_descriptor"]
        )


def test_census_all_288_expected_observations_and_labels_are_independent():
    assert len(EXPECTED_OBSERVATIONS) == 288
    all_facts = []
    for family in FAMILIES:
        for code, *_ in PLACES:
            facts = _facts(family, code)
            assert _dimension_label_reports(
                _alias(family, code), consumer_fact_rows(facts)
            ) == ([], [])
            all_facts.extend(facts)
    assert len(all_facts) == 288
    assert Counter(fact.entity.name for fact in all_facts) == {
        "household": 216,
        "family": 72,
    }
    assert Counter(fact.geography.id for fact in all_facts) == {
        ("NZ" if code == "NZ" else code): 16 for code, *_ in PLACES
    }
    coverage = build_bundle_coverage(consumer_fact_rows(all_facts))
    assert not coverage["duplicates"]["aggregate_fact_keys"]
    assert not coverage["duplicates"]["semantic_fact_keys"]


def test_census_shared_artifacts_keep_family_cell_and_row_identities_distinct():
    for code, *_ in PLACES:
        household_cells = {
            build_source_cell_key(cell) for cell in _cells("households_by_region", code)
        }
        family_cells = {
            build_source_cell_key(cell) for cell in _cells("family_type", code)
        }
        assert household_cells.isdisjoint(family_cells)
        household_rows = {
            build_source_row_key(row) for row in _rows("households_by_region", code)
        }
        family_rows = {build_source_row_key(row) for row in _rows("family_type", code)}
        assert household_rows.isdisjoint(family_rows)
        assert (
            {row.artifact.sha256 for row in _rows("households_by_region", code)}
            == {row.artifact.sha256 for row in _rows("family_type", code)}
            == {PLACE_BY_CODE[code][2]}
        )


def test_census_dimensions_preserve_categories_in_consumer_compatible_variables():
    for family in FAMILIES:
        for code, *_ in PLACES:
            row_index = {build_source_row_key(row): row for row in _rows(family, code)}
            for fact in _facts(family, code):
                kind = fact.layout.record_set_id.rsplit(".", 1)[-1]
                dimension = EXPECTED_DIMENSIONS[kind]
                assert fact.layout.groupby_dimension == dimension
                row = row_index[fact.source_row_keys[0]]
                expected_filters = (
                    {}
                    if kind in {"households", "families"}
                    else {dimension: row.values["variable1_code"]}
                )
                assert fact.filters == expected_filters
                assert {
                    constraint.variable: constraint.value
                    for constraint in fact.constraints
                } == expected_filters
                assert all(
                    constraint.operator == "==" for constraint in fact.constraints
                )
                assert not any(
                    constraint.variable.startswith("stats_nz.")
                    for constraint in fact.constraints
                )
                assert (
                    fact.dimension_value_labels[dimension][
                        str(fact.layout.groupby_value_id)
                    ]
                    == row.values["variable1_descriptor"]
                )


@pytest.mark.parametrize(
    ("family", "kind"),
    (
        ("households_by_region", "tenure"),
        ("households_by_region", "household_size"),
        ("family_type", "family_type"),
    ),
)
def test_census_consumer_contract_rejects_publisher_namespace_constraints(family, kind):
    original = next(
        fact
        for fact in _facts(family, "NZ")
        if fact.layout.record_set_id.endswith(f".{kind}")
    )
    changed = replace(
        original,
        constraints=tuple(
            replace(constraint, variable=f"stats_nz.census_2023.{kind}")
            for constraint in original.constraints
        ),
    )
    report = validate_consumer_fact_contract([changed])
    assert not report.valid
    assert any(
        error.code == "source_specific_constraint_variable" for error in report.errors
    )


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("code", [place[0] for place in PLACES])
def test_census_every_guard_is_declared_from_independent_literals(family, code):
    published = [row for row in PUBLISHED_ROWS if row[0] == family]
    by_id = {spec.source_record_id: spec for spec in _specs(family, code)}
    for virtual_row, row in enumerate(published, start=2):
        spec = by_id[_record_id(code, row)]
        expected = _expected_guards(code, row, virtual_row)
        assert _guard_index(spec) == {
            address: value for address, value in expected.items() if value is not None
        }
    assert tuple(
        {field: str(value) for field, value in criteria.items()}
        for criteria in _package(family, code).artifact.selected_rows
    ) == tuple(_expected_selection(code, row) for row in published)


@pytest.mark.parametrize("guard_column", (*NONBLANK_GUARD_COLUMNS, "O1"))
def test_census_each_guard_rejects_mutated_source_cell(guard_column):
    # Iterate every fact for this independently declared guard, so deleting a
    # YAML guard cannot delete its regression. No tracked publisher bytes change.
    checked = 0
    for family in FAMILIES:
        for code, *_ in PLACES:
            cell_index = {
                (cell.sheet_name, cell.address): cell for cell in _cells(family, code)
            }
            published = [row for row in PUBLISHED_ROWS if row[0] == family]
            by_id = {spec.source_record_id: spec for spec in _specs(family, code)}
            for virtual_row, row in enumerate(published, start=2):
                spec = by_id[_record_id(code, row)]
                address = (
                    "O1" if guard_column == "O1" else f"{guard_column}{virtual_row}"
                )
                coordinate = spec.selector.sheet_name, address
                assert address in _guard_index(spec)
                original = cell_index[coordinate]
                mutated = dict(cell_index)
                mutated[coordinate] = replace(
                    original,
                    raw_value="CONFIDENTIAL_OR_CHANGED",
                    cell_type="text",
                    display_value="CONFIDENTIAL_OR_CHANGED",
                )
                with pytest.raises(ValueError, match="expected"):
                    resolve_source_record(list(mutated.values()), spec)
                checked += 1
    assert checked == 288


@pytest.mark.parametrize("guard_field", GUARD_FIELDS)
def test_census_each_selection_guard_rejects_mutated_source_row(guard_field):
    checked = 0
    for family in FAMILIES:
        for code, *_ in PLACES:
            published = [row for row in PUBLISHED_ROWS if row[0] == family]
            selected_numbers = {row[7] for row in published}
            selected = [
                row for row in _rows(family, code) if row.row_number in selected_numbers
            ]
            assert len(selected) == len(published)
            for target in selected:
                # A selected-only in-memory source-row subset keeps the guard
                # checks small; complete 2,030-row preservation is tested above.
                changed = [
                    replace(
                        row,
                        values={**row.values, guard_field: "CONFIDENTIAL_OR_CHANGED"},
                    )
                    if row is target
                    else row
                    for row in selected
                ]
                with pytest.raises(ValueError, match="matched 0 rows"):
                    _package(family, code).build_source_cells(2023, source_rows=changed)
                checked += 1
    assert checked == 288


@pytest.fixture
def mutated_census_package():
    def mutate(overrides=None, other_manifest=None):
        package = _package("households_by_region", "02")
        selections = deepcopy(package.artifact.selected_rows)
        if overrides:
            # The independent selection order pins Owned to virtual row 3.
            selections[1].update(overrides)
            if overrides.get("value_type_description") == "Percent":
                selections[1].update(value_label="percent", decimals=1)
        if other_manifest:
            for criteria in selections:
                criteria.update(code=1, descriptor="Northland Region")
        artifact = replace(
            package.artifact,
            selected_rows=selections,
            **({"manifest": other_manifest} if other_manifest else {}),
        )
        return replace(package, artifact=artifact)

    return mutate


@pytest.mark.parametrize(
    ("overrides", "manifest"),
    [
        pytest.param(
            {"value_type_description": "Percent"}, None, id="percent-instead-of-count"
        ),
        pytest.param({"period": 2018}, None, id="2018-instead-of-2023"),
        pytest.param(None, "manifest-rc-01.yaml", id="northland-file-for-auckland"),
        pytest.param(
            {"section_title": "Tenure of household for the Māori ethnic group"},
            None,
            id="maori-instead-of-total-population",
        ),
    ],
)
def test_census_independent_map_rejects_mutated_yaml_selection(
    mutated_census_package, overrides, manifest
):
    mutant = mutated_census_package(overrides, manifest)
    with pytest.raises(AssertionError, match="selected"):
        _assert_publisher_map("households_by_region", "02", mutant)


@pytest.mark.parametrize(
    ("code", "section", "category", "expected"),
    [
        ("NZ", "Number of families and households", "Households", 1780527),
        ("NZ", "Number of families and households", "Families", 1294503),
        ("NZ", "Tenure of household", "Owned", 978105),
        ("NZ", "Tenure of household", "Not owned", 604884),
        ("NZ", "Tenure of household", "In family trust", 197112),
        ("NZ", "Family type", "Couple Without Children", 537486),
        ("NZ", "Family type", "Couple With Child(ren)", 543483),
        ("NZ", "Family type", "One Parent With Child(ren)", 213534),
        ("02", "Number of families and households", "Households", 539490),
        ("02", "Number of families and households", "Families", 426684),
        ("02", "Tenure of household", "Owned", 259299),
        ("02", "Tenure of household", "Not owned", 218220),
        ("02", "Tenure of household", "In family trust", 61839),
        ("02", "Family type", "One Parent With Child(ren)", 73689),
        ("02", "Number of usual residents in household", "One usual resident", 95991),
    ],
)
def test_census_exact_publisher_cells(code, section, category, expected):
    published = next(
        row for row in PUBLISHED_ROWS if row[3] == section and row[6] == category
    )
    fact = next(
        fact
        for fact in _facts(published[0], code)
        if fact.source_record_id == _record_id(code, published)
    )
    assert Decimal(_publisher_rows(code)[published[7]]["value"]) == expected
    assert fact.value == expected
    assert fact.layout.groupby_value_label == category


def test_census_reference_night_geographies_and_independent_totals_are_preserved():
    for family in FAMILIES:
        for code, name, *_ in PLACES:
            package, cells, rows = (
                _package(family, code),
                _cells(family, code),
                _rows(family, code),
            )
            facts = _facts(family, code)
            assert [
                (fact.source_record_id, fact.value)
                for fact in package.build_facts(2025, cells=cells, source_rows=rows)
            ] == [(fact.source_record_id, fact.value) for fact in facts]
            for fact in facts:
                assert (fact.period.type, fact.period.value) == ("calendar_year", 2023)
                assert (
                    fact.period_coverage.start_date,
                    fact.period_coverage.end_date,
                ) == ("2023-03-07", "2023-03-07")
                assert fact.geography.name == ("Auckland" if code == "02" else name)
                assert fact.geography.id == ("NZ" if code == "NZ" else code)
                assert fact.geography.level == ("country" if code == "NZ" else "region")
                assert fact.geography.vintage == (
                    "current" if code == "NZ" else "unstated"
                )
    national = {
        fact.layout.groupby_value_label: fact
        for fact in _facts("households_by_region", "NZ")
    }
    assert (
        sum(
            national[label].value for label in ("Owned", "Not owned", "In family trust")
        )
        == 1780101
    )
    assert national["Households"].value == 1780527
    assert national["Households"].value != 1780101
    household_row = next(row for row in PUBLISHED_ROWS if row[6] == "Households")
    assert (
        _expected_map("households_by_region", "NZ")[_record_id("NZ", household_row)][7]
        == 1655
    )


@pytest.mark.parametrize("family", FAMILIES)
def test_census_source_suite_validates_consumer_contract_and_preservation(
    tmp_path, family
):
    code = "NZ"
    report = build_source_suite(
        _package(family, code).package_path, tmp_path / _alias(family, code), year=2023
    )
    assert report.valid, report.to_dict()
    assert report.source_rows.row_count == 2030
    assert report.facts.fact_count == (12 if family == "households_by_region" else 4)
    assert report.consumer_facts.fact_count == report.facts.fact_count
    assert report.source_records.lineage_coverage == 1
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
