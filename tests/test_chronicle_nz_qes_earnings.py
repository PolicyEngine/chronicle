"""Literal publisher-cell and layout gates for Stats NZ's QES weekly earnings."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import replace
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import re

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
from chronicle.sources.specs import (
    build_cells_by_sheet_address,
    resolve_source_record,
)
from chronicle.suite import build_source_suite

ROOT = Path(__file__).resolve().parents[1]
SHEET = "Table 7"
ALIASES = {
    2025: "stats-nz-qes-average-weekly-earnings-june-2025",
    2026: "stats-nz-qes-average-weekly-earnings-june-2026",
}
DIRECTORIES = {
    year: Path(f"stats_nz/qes_average_weekly_earnings_june_{year}") for year in ALIASES
}
ARTIFACTS = {
    2025: (
        "25053dcbd343320cad72e2896475eaebaf5f5bb0b5965ca788506ca15efcea30",
        135_784,
    ),
    2026: (
        "1af2e7e37f1c108a2656842cf1f519c903e1a982bcdc03ee02d0ad888ebc3a97",
        124_556,
    ),
}

# Audited from the two publisher workbooks independently of package YAML.
# A vintage, quarter, series, address and literal value identify each fact.
EXPECTED_CELLS = (
    (2025, "2023-Q2", "QEMQ.SBSZ9A", "P13", 1502.27),
    (2025, "2023-Q2", "QEMQ.SBSZ9Z", "T13", 1530.82),
    (2025, "2023-Q3", "QEMQ.SBSZ9A", "P14", 1528.92),
    (2025, "2023-Q3", "QEMQ.SBSZ9Z", "T14", 1557.93),
    (2025, "2023-Q4", "QEMQ.SBSZ9A", "P15", 1556.16),
    (2025, "2023-Q4", "QEMQ.SBSZ9Z", "T15", 1587.94),
    (2025, "2024-Q1", "QEMQ.SBSZ9A", "P16", 1563.54),
    (2025, "2024-Q1", "QEMQ.SBSZ9Z", "T16", 1593),
    (2026, "2024-Q2", "QEMQ.SBSZ9A", "P13", 1586.32),
    (2026, "2024-Q2", "QEMQ.SBSZ9Z", "T13", 1612.27),
    (2026, "2024-Q3", "QEMQ.SBSZ9A", "P14", 1595.11),
    (2026, "2024-Q3", "QEMQ.SBSZ9Z", "T14", 1620.53),
    (2026, "2024-Q4", "QEMQ.SBSZ9A", "P15", 1622.73),
    (2026, "2024-Q4", "QEMQ.SBSZ9Z", "T15", 1651.31),
    (2026, "2025-Q1", "QEMQ.SBSZ9A", "P16", 1637.2),
    (2026, "2025-Q1", "QEMQ.SBSZ9Z", "T16", 1665.72),
    (2026, "2025-Q2", "QEMQ.SBSZ9A", "P17", 1652.72),
    (2026, "2025-Q2", "QEMQ.SBSZ9Z", "T17", 1678.9),
    (2026, "2025-Q3", "QEMQ.SBSZ9A", "P18", 1661.12),
    (2026, "2025-Q3", "QEMQ.SBSZ9Z", "T18", 1687.51),
    (2026, "2025-Q4", "QEMQ.SBSZ9A", "P19", 1681.06),
    (2026, "2025-Q4", "QEMQ.SBSZ9Z", "T19", 1712.05),
    (2026, "2026-Q1", "QEMQ.SBSZ9A", "P20", 1685.39),
    (2026, "2026-Q1", "QEMQ.SBSZ9Z", "T20", 1715.66),
    (2026, "2026-Q2", "QEMQ.SBSZ9A", "P21", 1700.68),
    (2026, "2026-Q2", "QEMQ.SBSZ9Z", "T21", 1729.95),
)
EXPECTED_COVERAGE = {
    "2023-Q2": ("2023-04-01", "2023-06-30"),
    "2023-Q3": ("2023-07-01", "2023-09-30"),
    "2023-Q4": ("2023-10-01", "2023-12-31"),
    "2024-Q1": ("2024-01-01", "2024-03-31"),
    "2024-Q2": ("2024-04-01", "2024-06-30"),
    "2024-Q3": ("2024-07-01", "2024-09-30"),
    "2024-Q4": ("2024-10-01", "2024-12-31"),
    "2025-Q1": ("2025-01-01", "2025-03-31"),
    "2025-Q2": ("2025-04-01", "2025-06-30"),
    "2025-Q3": ("2025-07-01", "2025-09-30"),
    "2025-Q4": ("2025-10-01", "2025-12-31"),
    "2026-Q1": ("2026-01-01", "2026-03-31"),
    "2026-Q2": ("2026-04-01", "2026-06-30"),
}
FOOTNOTE = (
    "Average weekly earnings are calculated by dividing earnings by the number of FTEs."
)
COMMON_GUARDS = {
    "A1": "Table 7",
    "A3": "Average weekly earnings for FTEs(1)",
    "A4": "By sector",
    "A8": "Series ref: QEMQ",
    "A10": "($)",
    "A12": "Quarter",
    "P6": "Total",
    "P7": "Ordinary time",
    "T7": "Total",
    "P8": "SBSZ9A",
    "T8": "SBSZ9Z",
    "B49": FOOTNOTE,
}
# Coordinates and values are independent of YAML: dropping a guard does not
# remove its mutation regression case.
EXPECTED_GUARDS = {
    2025: {
        **COMMON_GUARDS,
        "A13": "2023",
        "A16": "2024",
        "C13": "Jun",
        "C14": "Sep",
        "C15": "Dec",
        "C16": "Mar",
    },
    2026: {
        **COMMON_GUARDS,
        "A13": "2024",
        "A16": "2025",
        "A20": "2026",
        "C13": "Jun",
        "C14": "Sep",
        "C15": "Dec",
        "C16": "Mar",
        "C17": "Jun",
        "C18": "Sep",
        "C19": "Dec",
        "C20": "Mar",
        "C21": "Jun",
    },
}
GUARD_CASES = tuple(
    (year, address) for year, guards in EXPECTED_GUARDS.items() for address in guards
)


@lru_cache
def _package(year):
    return load_source_package(
        os.environ.get(f"CHRONICLE_NZ_QES_{year}_TEST_PACKAGE", ALIASES[year])
    )


@lru_cache
def _cells(year):
    return _package(year).build_source_cells(year)


@lru_cache
def _cell_index(year):
    return build_cells_by_sheet_address(_cells(year))


@lru_cache
def _specs(year):
    return _package(year).build_source_record_specs(year)


@lru_cache
def _facts(year):
    return _package(year).build_facts(year, cells=_cells(year))


def _assert_expected_publisher_map(year, specs):
    expected = {
        (period, series): (SHEET, address)
        for vintage, period, series, address, _value in EXPECTED_CELLS
        if vintage == year
    }
    actual = {
        (spec.period, spec.filters["earnings_series_reference"]): (
            spec.selector.sheet_name,
            spec.selector.address,
        )
        for spec in specs
    }
    assert len(specs) == len(actual) == len(expected), "publisher cell count drift"
    assert actual == expected, (
        f"selected publisher cells {actual!r}; expected {expected!r}"
    )


@lru_cache
def _guard_index(year):
    guards = {}
    for spec in _specs(year):
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
                (item.address, item.expected_value, item.label)
                for item in selector.guard_cells
            ),
        )
        assert selector.sheet_name == SHEET
        assert not selector.range_label_guards
        for address, expected, label in entries:
            if address is None:
                continue
            if address in guards:
                assert guards[address][1] == expected
            else:
                guards[address] = (spec, expected, label)
    return guards


@pytest.mark.parametrize("year", ALIASES)
def test_qes_alias_and_package_validation(year):
    assert SOURCE_PACKAGE_ALIASES[ALIASES[year]] == DIRECTORIES[year]
    report = validate_source_package(ALIASES[year], year=year)
    assert report.valid, report.to_dict()
    assert not report.warnings
    count = 8 if year == 2025 else 18
    assert report.counts["source_record_count"] == count
    assert report.counts["record_set_count"] == (4 if year == 2025 else 9)


@pytest.mark.parametrize("year", ALIASES)
def test_qes_publisher_bytes_and_country_storage_are_pinned(year):
    directory = ROOT / "db/data" / DIRECTORIES[year]
    manifest = yaml.safe_load((directory / "manifest.yaml").read_text())
    entry = manifest["files"][year]
    filename = f"quarterly-employment-survey-june-{year}-quarter.xlsx"
    content = (directory / filename).read_bytes()
    sha256, size = ARTIFACTS[year]
    source_url = (
        "https://www.stats.govt.nz/assets/Uploads/Labour-market-statistics/"
        f"Labour-market-statistics-June-{year}-quarter/Download-data/{filename}"
    )
    assert hashlib.sha256(content).hexdigest() == entry["sha256"] == sha256
    assert len(content) == entry["size_bytes"] == size
    assert manifest["license"]["url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert manifest["license"]["evidence_url"] == (
        "https://www.stats.govt.nz/about-us/copyright/"
    )
    assert entry["filename"] == filename
    assert entry["source_url"] == source_url
    assert entry["fetched_at"] == "2026-10-22T07:57:28Z"
    key = build_r2_key(
        source_id="stats_nz",
        package_id=DIRECTORIES[year].name,
        year=year,
        sha256=sha256,
        filename=filename,
    )
    assert key.startswith(f"raw/nz/stats_nz/{DIRECTORIES[year].name}/{year}/{sha256}/")
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }
    assert {fact.source.raw_r2_uri for fact in _facts(year)} == {
        entry["storage"]["r2"]["uri"]
    }


@pytest.mark.parametrize("year", ALIASES)
def test_qes_preserves_all_worksheets_and_nonemitted_blocks(year):
    cells = _cells(year)
    sizes = {
        "Contents": 41 * 9,
        "Table 1": 54 * 9,
        "Table 2": 54 * 9,
        "Table 3": (75 if year == 2025 else 74) * 13,
        "Table 4": 53 * 9,
        "Table 5": 53 * 9,
        "Table 6": 55 * 21,
        "Table 7": 51 * 21,
        "Table 8": 51 * 21,
        "Table 9": 51 * 21,
        "Table 10": (79 if year == 2025 else 78) * 29,
        "Table 11": (79 if year == 2025 else 78) * 29,
        "Table 12": (80 if year == 2025 else 79) * 29,
        "Table 13": (80 if year == 2025 else 79) * 29,
        "Table 14": 31 * 9,
        "Table 15": 32 * 9,
    }
    assert Counter(cell.sheet_name for cell in cells) == sizes
    assert validate_source_cells(cells).valid
    assert _cell_index(year)[(SHEET, "R8")].raw_value == "SBSZ9B"
    assert _cell_index(year)[(SHEET, "D6")].raw_value == "Public sector"
    assert _cell_index(year)[(SHEET, "J6")].raw_value == "Private sector"
    assert _cell_index(year)[(SHEET, "A23")].raw_value == (
        "Percentage change from the same quarter of previous year"
    )
    assert _cell_index(year)[(SHEET, "A36")].raw_value == (
        "Percentage change from previous quarter"
    )


@pytest.mark.parametrize("year", ALIASES)
def test_qes_every_published_value_matches_literal_cell_map(year):
    _assert_expected_publisher_map(year, _specs(year))
    facts = {
        (fact.period.value, fact.filters["earnings_series_reference"]): fact
        for fact in _facts(year)
    }
    expected = [entry for entry in EXPECTED_CELLS if entry[0] == year]
    assert len(facts) == len(_facts(year)) == len(expected)
    for _vintage, period, series, address, value in expected:
        fact = facts[(period, series)]
        cell = _cell_index(year)[(SHEET, address)]
        assert cell.raw_value == fact.value == value
        assert build_source_cell_key(cell) == fact.source_cell_keys[0]


@pytest.mark.parametrize("year", ALIASES)
def test_qes_one_published_cell_per_fact_without_arithmetic(year):
    for fact, spec in zip(_facts(year), _specs(year), strict=True):
        assert spec.value_scale == 1
        assert spec.divisor_selector is None
        assert spec.round_to is None
        assert spec.selector.end_address is None
        assert spec.selector.expected_cell_type == "number"
        assert spec.selector.address.startswith(("P", "T"))
        assert 13 <= int(spec.selector.address[1:]) <= (16 if year == 2025 else 21)
        assert fact.measure.unit == "nzd_per_week"
        assert fact.aggregation.method == "mean"
        assert fact.aggregation.denominator is None
        assert fact.source.source_sha256 == ARTIFACTS[year][0]
        assert fact.source_record_id == spec.source_record_id
        assert fact.layout.source_column_id in {"SBSZ9A", "SBSZ9Z"}
        assert build_source_cell_key(_cell_index(year)[(SHEET, "B49")]) in (
            fact.source_cell_keys
        )


@pytest.mark.parametrize("year", ALIASES)
def test_qes_periods_and_publisher_observation_scope(year):
    facts = _facts(year)
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    for fact in facts:
        assert fact.period.type == "quarter"
        coverage = fact.period_coverage
        assert (coverage.start_date, coverage.end_date) == EXPECTED_COVERAGE[
            fact.period.value
        ]
        assert coverage.basis == "calendar"
        assert (fact.geography.level, fact.geography.id, fact.geography.name) == (
            "country",
            "NZ",
            "New Zealand",
        )
        assert (fact.entity.name, fact.entity.role) == (
            "person",
            "full_time_equivalent_employee",
        )
        assert fact.provenance_class == "survey_aggregate"
        assert fact.survey_instrument == "Quarterly Employment Survey (QES)"
        assert fact.assertion == "observation"
        notes = coverage.notes
        assert "20th" in notes and "middle month" in notes
        assert "pay week" in notes.lower()
    assert _package(year).build_facts(2031, cells=_cells(year)) == facts


@pytest.mark.parametrize("year", ALIASES)
def test_qes_every_dimension_and_value_has_a_label(year):
    facts = _facts(year)
    assert _dimension_label_reports(ALIASES[year], consumer_fact_rows(facts)) == (
        [],
        [],
    )
    for fact in facts:
        ordinary = fact.filters["earnings_series_reference"] == "QEMQ.SBSZ9A"
        assert fact.filters == {
            "earnings_denominator": "fte",
            "seasonal_adjustment": "actual",
            "earnings_sector": "all_sectors",
            "earnings_series_reference": "QEMQ.SBSZ9A" if ordinary else "QEMQ.SBSZ9Z",
            "earnings_component": "ordinary_time" if ordinary else "total",
        }
        assert fact.layout.groupby_dimension == "earnings_sector"
        assert fact.layout.groupby_value_label == "All sectors"
        for dimension, value in fact.filters.items():
            assert fact.dimension_labels[dimension]
            assert fact.dimension_value_labels[dimension][str(value)]
        label = fact.layout.measure_label
        assert fact.filters["earnings_series_reference"] in label
        assert "FTE" in label
        assert "actual" in label.lower()
        assert "not seasonally adjusted" in label.lower()
        assert ("ordinary" if ordinary else "total") in label.lower()


def test_qes_shared_quarters_agree_and_each_quarter_is_emitted_once():
    # Five identical shared quarters are evidence about these publisher
    # vintages; no values are reconciled, averaged or computed from them.
    for earlier_row, later_row in ((17, 13), (18, 14), (19, 15), (20, 16), (21, 17)):
        for column in ("P", "T"):
            assert _cell_index(2025)[(SHEET, f"{column}{earlier_row}")].raw_value == (
                _cell_index(2026)[(SHEET, f"{column}{later_row}")].raw_value
            )
    facts = [*_facts(2025), *_facts(2026)]
    assert len(facts) == 26
    assert (
        len(
            {
                (fact.period.value, fact.filters["earnings_series_reference"])
                for fact in facts
            }
        )
        == 26
    )
    assert Counter(fact.period.value for fact in facts) == {
        period: 2 for period in EXPECTED_COVERAGE
    }
    coverage = build_bundle_coverage(consumer_fact_rows(facts))
    assert coverage["fact_count"] == 26
    assert coverage["counts"]["by_geography"] == {"country:NZ": 26}
    assert not coverage["duplicates"]["aggregate_fact_keys"]
    assert not coverage["duplicates"]["semantic_fact_keys"]


@pytest.mark.parametrize("year", ALIASES)
def test_qes_every_required_guard_is_declared(year):
    # The workbook stores year anchors as strings; Chronicle's YAML compiler
    # normalizes numeric-looking guard values to integers before comparison.
    assert {
        address: str(item[1]) for address, item in _guard_index(year).items()
    } == EXPECTED_GUARDS[year]


@pytest.mark.parametrize(("year", "address"), GUARD_CASES)
def test_qes_each_guard_rejects_mutated_publisher_cell(year, address):
    assert address in _guard_index(year), f"Missing publisher guard: {SHEET}!{address}"
    spec, expected, label = _guard_index(year)[address]
    coordinate = (SHEET, address)
    assert _cell_index(year)[coordinate].raw_value == EXPECTED_GUARDS[year][address]
    assert str(expected) == EXPECTED_GUARDS[year][address]
    resolve_source_record(_cells(year), spec, cells_by_sheet_address=_cell_index(year))
    changed_index = {
        **_cell_index(year),
        coordinate: replace(
            _cell_index(year)[coordinate], raw_value="unexpected publisher layout"
        ),
    }
    with pytest.raises(ValueError, match=re.escape(label)):
        resolve_source_record(_cells(year), spec, cells_by_sheet_address=changed_index)


@pytest.mark.parametrize("year", ALIASES)
def test_qes_column_shift_yaml_mutant_is_rejected(year):
    package = _package(year)
    changed_sets = []
    for declared in package.record_sets:
        payload = deepcopy(declared.payload)
        for measure in payload["measures"]:
            if measure["column"] == "P":
                measure.update(column="R", expected_column_header="SBSZ9B")
        changed_sets.append(replace(declared, payload=payload))
    changed = replace(package, record_sets=tuple(changed_sets))
    with pytest.raises(AssertionError, match="selected publisher cells"):
        _assert_expected_publisher_map(year, changed.build_source_record_specs(year))


def test_qes_duplicate_quarter_from_earlier_vintage_yaml_mutant_is_rejected():
    package = _package(2025)
    previous = package.record_sets[-1]
    payload = deepcopy(previous.payload)
    payload.update(
        record_set_id="stats_nz.qes.awe.2024q2",
        source_record_id_prefix="stats_nz.qes.awe.2024q2",
        period="2024-Q2",
    )
    payload["rows"][0].update(row_number=17, expected_row_header="Jun")
    extra_quarter = replace(previous, payload=payload)
    changed = replace(package, record_sets=(*package.record_sets, extra_quarter))
    with pytest.raises(AssertionError, match="publisher cell count drift"):
        _assert_expected_publisher_map(2025, changed.build_source_record_specs(2025))


@pytest.mark.parametrize("year", ALIASES)
def test_qes_build_suite_passes_source_acceptance(year, tmp_path):
    report = build_source_suite(ALIASES[year], tmp_path / "suite", year=year)
    assert report.valid
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
    assert report.source_records.resolved_count == (8 if year == 2025 else 18)
    assert report.source_records.lineage_coverage == 1
    assert not report.agent_acceptance.errors
