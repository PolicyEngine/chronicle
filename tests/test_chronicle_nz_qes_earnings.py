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
# Vintages are keyed by name: June 2026 and September 2026 share a year.
JUNE_2025 = "june_2025"
JUNE_2026 = "june_2026"
SEPTEMBER_2026 = "september_2026"
ALIASES = {
    JUNE_2025: "stats-nz-qes-average-weekly-earnings-june-2025",
    JUNE_2026: "stats-nz-qes-average-weekly-earnings-june-2026",
    SEPTEMBER_2026: "stats-nz-qes-average-weekly-earnings-september-2026",
}
DIRECTORIES = {
    vintage: Path(f"stats_nz/qes_average_weekly_earnings_{vintage}")
    for vintage in ALIASES
}
# The artifact year each manifest files its workbook under.
YEARS = {JUNE_2025: 2025, JUNE_2026: 2026, SEPTEMBER_2026: 2026}
MONTHS = {JUNE_2025: "June", JUNE_2026: "June", SEPTEMBER_2026: "September"}
FETCHED_AT = {
    JUNE_2025: "2026-10-22T07:57:28Z",
    JUNE_2026: "2026-10-22T07:57:28Z",
    SEPTEMBER_2026: "2026-11-03T21:46:14Z",
}
ARTIFACTS = {
    JUNE_2025: (
        "25053dcbd343320cad72e2896475eaebaf5f5bb0b5965ca788506ca15efcea30",
        135_784,
    ),
    JUNE_2026: (
        "1af2e7e37f1c108a2656842cf1f519c903e1a982bcdc03ee02d0ad888ebc3a97",
        124_556,
    ),
    SEPTEMBER_2026: (
        "d6fb9a947185551292dd6e81a527d994615ae15053b800a11e364ddb915626f3",
        119_004,
    ),
}
# Each vintage emits a contiguous Table 7 level block: (record sets, last row).
EMITTED = {JUNE_2025: (4, 16), JUNE_2026: (1, 13), SEPTEMBER_2026: (9, 21)}

# Audited from the three publisher workbooks independently of package YAML.
# A vintage, quarter, series, address and literal value identify each fact.
EXPECTED_CELLS = (
    (JUNE_2025, "2023-Q2", "QEMQ.SBSZ9A", "P13", 1502.27),
    (JUNE_2025, "2023-Q2", "QEMQ.SBSZ9Z", "T13", 1530.82),
    (JUNE_2025, "2023-Q3", "QEMQ.SBSZ9A", "P14", 1528.92),
    (JUNE_2025, "2023-Q3", "QEMQ.SBSZ9Z", "T14", 1557.93),
    (JUNE_2025, "2023-Q4", "QEMQ.SBSZ9A", "P15", 1556.16),
    (JUNE_2025, "2023-Q4", "QEMQ.SBSZ9Z", "T15", 1587.94),
    (JUNE_2025, "2024-Q1", "QEMQ.SBSZ9A", "P16", 1563.54),
    (JUNE_2025, "2024-Q1", "QEMQ.SBSZ9Z", "T16", 1593),
    (JUNE_2026, "2024-Q2", "QEMQ.SBSZ9A", "P13", 1586.32),
    (JUNE_2026, "2024-Q2", "QEMQ.SBSZ9Z", "T13", 1612.27),
    (SEPTEMBER_2026, "2024-Q3", "QEMQ.SBSZ9A", "P13", 1595.11),
    (SEPTEMBER_2026, "2024-Q3", "QEMQ.SBSZ9Z", "T13", 1620.53),
    (SEPTEMBER_2026, "2024-Q4", "QEMQ.SBSZ9A", "P14", 1622.73),
    (SEPTEMBER_2026, "2024-Q4", "QEMQ.SBSZ9Z", "T14", 1651.31),
    (SEPTEMBER_2026, "2025-Q1", "QEMQ.SBSZ9A", "P15", 1637.2),
    (SEPTEMBER_2026, "2025-Q1", "QEMQ.SBSZ9Z", "T15", 1665.72),
    (SEPTEMBER_2026, "2025-Q2", "QEMQ.SBSZ9A", "P16", 1652.72),
    (SEPTEMBER_2026, "2025-Q2", "QEMQ.SBSZ9Z", "T16", 1678.9),
    (SEPTEMBER_2026, "2025-Q3", "QEMQ.SBSZ9A", "P17", 1661.12),
    (SEPTEMBER_2026, "2025-Q3", "QEMQ.SBSZ9Z", "T17", 1687.51),
    (SEPTEMBER_2026, "2025-Q4", "QEMQ.SBSZ9A", "P18", 1681.06),
    (SEPTEMBER_2026, "2025-Q4", "QEMQ.SBSZ9Z", "T18", 1712.05),
    (SEPTEMBER_2026, "2026-Q1", "QEMQ.SBSZ9A", "P19", 1685.39),
    (SEPTEMBER_2026, "2026-Q1", "QEMQ.SBSZ9Z", "T19", 1715.66),
    (SEPTEMBER_2026, "2026-Q2", "QEMQ.SBSZ9A", "P20", 1700.68),
    (SEPTEMBER_2026, "2026-Q2", "QEMQ.SBSZ9Z", "T20", 1729.95),
    (SEPTEMBER_2026, "2026-Q3", "QEMQ.SBSZ9A", "P21", 1714.86),
    (SEPTEMBER_2026, "2026-Q3", "QEMQ.SBSZ9Z", "T21", 1743.23),
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
    "2026-Q3": ("2026-07-01", "2026-09-30"),
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
    JUNE_2025: {
        **COMMON_GUARDS,
        "A13": "2023",
        "A16": "2024",
        "C13": "Jun",
        "C14": "Sep",
        "C15": "Dec",
        "C16": "Mar",
    },
    JUNE_2026: {
        **COMMON_GUARDS,
        "A13": "2024",
        "C13": "Jun",
    },
    SEPTEMBER_2026: {
        **COMMON_GUARDS,
        "A13": "2024",
        "A15": "2025",
        "A19": "2026",
        "C13": "Sep",
        "C14": "Dec",
        "C15": "Mar",
        "C16": "Jun",
        "C17": "Sep",
        "C18": "Dec",
        "C19": "Mar",
        "C20": "Jun",
        "C21": "Sep",
    },
}
GUARD_CASES = tuple(
    (vintage, address)
    for vintage, guards in EXPECTED_GUARDS.items()
    for address in guards
)
# _guard_index unions guard addresses across record sets, so it can't see one
# record set drop a guard that another record set still declares, or that
# doubles as a row header (September's C13 is also 2024-Q3's). Each record set
# must declare exactly its vintage's anchors and its own year block's label.
VINTAGE_ANCHORS = {
    JUNE_2025: ("A13",),
    JUNE_2026: ("A13",),
    SEPTEMBER_2026: ("A13", "C13"),
}
YEAR_LABEL_ROWS = {
    vintage: tuple(
        sorted(
            int(address[1:])
            for address in guards
            if address[0] == "A" and int(address[1:]) >= 13
        )
    )
    for vintage, guards in EXPECTED_GUARDS.items()
}


@lru_cache
def _package(vintage):
    return load_source_package(
        os.environ.get(
            f"CHRONICLE_NZ_QES_{vintage.upper()}_TEST_PACKAGE", ALIASES[vintage]
        )
    )


@lru_cache
def _cells(vintage):
    return _package(vintage).build_source_cells(YEARS[vintage])


@lru_cache
def _cell_index(vintage):
    return build_cells_by_sheet_address(_cells(vintage))


@lru_cache
def _specs(vintage):
    return _package(vintage).build_source_record_specs(YEARS[vintage])


@lru_cache
def _facts(vintage):
    return _package(vintage).build_facts(YEARS[vintage], cells=_cells(vintage))


def _expected_count(vintage):
    return sum(1 for entry in EXPECTED_CELLS if entry[0] == vintage)


def _assert_expected_publisher_map(vintage, specs):
    expected = {
        (period, series): (SHEET, address)
        for owner, period, series, address, _value in EXPECTED_CELLS
        if owner == vintage
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
def _guard_index(vintage):
    guards = {}
    for spec in _specs(vintage):
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


@pytest.mark.parametrize("vintage", ALIASES)
def test_qes_alias_and_package_validation(vintage):
    assert SOURCE_PACKAGE_ALIASES[ALIASES[vintage]] == DIRECTORIES[vintage]
    report = validate_source_package(ALIASES[vintage], year=YEARS[vintage])
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["source_record_count"] == _expected_count(vintage)
    assert report.counts["record_set_count"] == EMITTED[vintage][0]


@pytest.mark.parametrize("vintage", ALIASES)
def test_qes_publisher_bytes_and_country_storage_are_pinned(vintage):
    year = YEARS[vintage]
    directory = ROOT / "db/data" / DIRECTORIES[vintage]
    manifest = yaml.safe_load((directory / "manifest.yaml").read_text())
    entry = manifest["files"][year]
    month = MONTHS[vintage]
    filename = f"quarterly-employment-survey-{month.lower()}-{year}-quarter.xlsx"
    content = (directory / filename).read_bytes()
    sha256, size = ARTIFACTS[vintage]
    source_url = (
        "https://www.stats.govt.nz/assets/Uploads/Labour-market-statistics/"
        f"Labour-market-statistics-{month}-{year}-quarter/Download-data/{filename}"
    )
    assert hashlib.sha256(content).hexdigest() == entry["sha256"] == sha256
    assert len(content) == entry["size_bytes"] == size
    assert manifest["license"]["url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert manifest["license"]["evidence_url"] == (
        "https://www.stats.govt.nz/about-us/copyright/"
    )
    assert entry["filename"] == filename
    assert entry["source_url"] == source_url
    assert entry["fetched_at"] == FETCHED_AT[vintage]
    key = build_r2_key(
        source_id="stats_nz",
        package_id=DIRECTORIES[vintage].name,
        year=year,
        sha256=sha256,
        filename=filename,
    )
    assert key.startswith(
        f"raw/nz/stats_nz/{DIRECTORIES[vintage].name}/{year}/{sha256}/"
    )
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }
    assert {fact.source.raw_r2_uri for fact in _facts(vintage)} == {
        entry["storage"]["r2"]["uri"]
    }


@pytest.mark.parametrize("vintage", ALIASES)
def test_qes_preserves_all_worksheets_and_nonemitted_blocks(vintage):
    cells = _cells(vintage)
    # Tables 3 and 10-13 lose one row per newer vintage; September 2026 also
    # publishes one fewer Table 15 row.
    shorter = {JUNE_2025: 0, JUNE_2026: 1, SEPTEMBER_2026: 2}[vintage]
    sizes = {
        "Contents": 41 * 9,
        "Table 1": 54 * 9,
        "Table 2": 54 * 9,
        "Table 3": (75 - shorter) * 13,
        "Table 4": 53 * 9,
        "Table 5": 53 * 9,
        "Table 6": 55 * 21,
        "Table 7": 51 * 21,
        "Table 8": 51 * 21,
        "Table 9": 51 * 21,
        "Table 10": (79 - shorter) * 29,
        "Table 11": (79 - shorter) * 29,
        "Table 12": (80 - shorter) * 29,
        "Table 13": (80 - shorter) * 29,
        "Table 14": 31 * 9,
        "Table 15": (31 if vintage == SEPTEMBER_2026 else 32) * 9,
    }
    assert Counter(cell.sheet_name for cell in cells) == sizes
    assert validate_source_cells(cells).valid
    assert _cell_index(vintage)[(SHEET, "R8")].raw_value == "SBSZ9B"
    assert _cell_index(vintage)[(SHEET, "D6")].raw_value == "Public sector"
    assert _cell_index(vintage)[(SHEET, "J6")].raw_value == "Private sector"
    assert _cell_index(vintage)[(SHEET, "A23")].raw_value == (
        "Percentage change from the same quarter of previous year"
    )
    assert _cell_index(vintage)[(SHEET, "A36")].raw_value == (
        "Percentage change from previous quarter"
    )


@pytest.mark.parametrize("vintage", ALIASES)
def test_qes_every_published_value_matches_literal_cell_map(vintage):
    _assert_expected_publisher_map(vintage, _specs(vintage))
    facts = {
        (fact.period.value, fact.filters["earnings_series_reference"]): fact
        for fact in _facts(vintage)
    }
    expected = [entry for entry in EXPECTED_CELLS if entry[0] == vintage]
    assert len(facts) == len(_facts(vintage)) == len(expected)
    for _vintage, period, series, address, value in expected:
        fact = facts[(period, series)]
        cell = _cell_index(vintage)[(SHEET, address)]
        assert cell.raw_value == fact.value == value
        assert build_source_cell_key(cell) == fact.source_cell_keys[0]


@pytest.mark.parametrize("vintage", ALIASES)
def test_qes_one_published_cell_per_fact_without_arithmetic(vintage):
    for fact, spec in zip(_facts(vintage), _specs(vintage), strict=True):
        assert spec.value_scale == 1
        assert spec.divisor_selector is None
        assert spec.round_to is None
        assert spec.selector.end_address is None
        assert spec.selector.expected_cell_type == "number"
        assert spec.selector.address.startswith(("P", "T"))
        assert 13 <= int(spec.selector.address[1:]) <= EMITTED[vintage][1]
        assert fact.measure.unit == "nzd_per_week"
        assert fact.aggregation.method == "mean"
        assert fact.aggregation.denominator is None
        assert fact.source.source_sha256 == ARTIFACTS[vintage][0]
        assert fact.source_record_id == spec.source_record_id
        assert fact.layout.source_column_id in {"SBSZ9A", "SBSZ9Z"}
        assert build_source_cell_key(_cell_index(vintage)[(SHEET, "B49")]) in (
            fact.source_cell_keys
        )


@pytest.mark.parametrize("vintage", ALIASES)
def test_qes_periods_and_publisher_observation_scope(vintage):
    facts = _facts(vintage)
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
    assert _package(vintage).build_facts(2031, cells=_cells(vintage)) == facts


@pytest.mark.parametrize("vintage", ALIASES)
def test_qes_every_record_set_states_its_own_provenance(vintage):
    # Each record set states its provenance in its own YAML mapping; a YAML
    # anchor or package-level default does not count.
    path = ROOT / "packages" / DIRECTORIES[vintage] / "source_package.yaml"
    text = path.read_text()
    assert not re.search(r"(^|\s)[&*][A-Za-z_]", text)
    payload = yaml.safe_load(text)
    assert len(payload["record_sets"]) == EMITTED[vintage][0]
    for record_set in payload["record_sets"]:
        assert record_set["provenance_class"] == "survey_aggregate"
        assert record_set["survey_instrument"] == "Quarterly Employment Survey (QES)"
        assert record_set["assertion"] == "observation"


@pytest.mark.parametrize("vintage", ALIASES)
def test_qes_every_dimension_and_value_has_a_label(vintage):
    facts = _facts(vintage)
    assert _dimension_label_reports(ALIASES[vintage], consumer_fact_rows(facts)) == (
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


# Shared quarters between consecutive vintages, as (older row, newer row).
# The newest vintage that publishes a quarter emits it; the older cells stay
# preserved and unemitted.
SHARED_ROWS = {
    # June 2025 rows 17-21 against June 2026 rows 13-17: June 2024-June 2025.
    (JUNE_2025, JUNE_2026): tuple((row, row - 4) for row in range(17, 22)),
    # June 2025 rows 18-21 against September 2026 rows 13-16: Sep 2024-Jun 2025.
    (JUNE_2025, SEPTEMBER_2026): tuple((row, row - 5) for row in range(18, 22)),
    # June 2026 rows 14-21 against September 2026 rows 13-20: Sep 2024-Jun 2026.
    (JUNE_2026, SEPTEMBER_2026): tuple((row, row - 1) for row in range(14, 22)),
}


def _quarter_label(vintage, row):
    """The published quarter of a Table 7 level row, read from the cells."""
    index = _cell_index(vintage)
    month = index[(SHEET, f"C{row}")].raw_value
    year = next(
        index[(SHEET, f"A{anchor}")].raw_value
        for anchor in range(row, 12, -1)
        if index[(SHEET, f"A{anchor}")].raw_value
    )
    return f"{month} {year}"


def test_qes_shared_quarters_agree_and_each_quarter_is_emitted_once():
    # Every shared quarter-series value is identical across the vintages that
    # publish it. This is evidence about the publisher's vintages; no value is
    # reconciled, averaged or computed from them.
    compared = Counter()
    for (older, newer), rows in SHARED_ROWS.items():
        for older_row, newer_row in rows:
            assert _quarter_label(older, older_row) == _quarter_label(newer, newer_row)
            for column in ("P", "T"):
                older_value = _cell_index(older)[(SHEET, f"{column}{older_row}")]
                newer_value = _cell_index(newer)[(SHEET, f"{column}{newer_row}")]
                assert older_value.raw_value == newer_value.raw_value
                compared[(older, newer)] += 1
    assert compared == {
        (JUNE_2025, JUNE_2026): 10,
        (JUNE_2025, SEPTEMBER_2026): 8,
        (JUNE_2026, SEPTEMBER_2026): 16,
    }
    facts = [fact for vintage in ALIASES for fact in _facts(vintage)]
    assert len(facts) == 28
    keys = Counter(
        (fact.period.value, fact.filters["earnings_series_reference"]) for fact in facts
    )
    assert set(keys.values()) == {1}
    assert len(keys) == 28
    assert Counter(fact.period.value for fact in facts) == {
        period: 2 for period in EXPECTED_COVERAGE
    }
    coverage = build_bundle_coverage(consumer_fact_rows(facts))
    assert coverage["fact_count"] == 28
    assert coverage["counts"]["by_geography"] == {"country:NZ": 28}
    assert not coverage["duplicates"]["aggregate_fact_keys"]
    assert not coverage["duplicates"]["semantic_fact_keys"]


@pytest.mark.parametrize("vintage", ALIASES)
def test_qes_every_required_guard_is_declared(vintage):
    # The workbook stores year anchors as strings; Chronicle's YAML compiler
    # normalizes numeric-looking guard values to integers before comparison.
    assert {
        address: str(item[1]) for address, item in _guard_index(vintage).items()
    } == EXPECTED_GUARDS[vintage]


@pytest.mark.parametrize("vintage", ALIASES)
def test_qes_each_record_set_declares_its_vintage_and_year_anchors(vintage):
    for spec in _specs(vintage):
        selector = spec.selector
        row = int(selector.expected_row_header_address[1:])
        year_row = max(r for r in YEAR_LABEL_ROWS[vintage] if r <= row)
        expected = {
            address: EXPECTED_GUARDS[vintage][address]
            for address in (*VINTAGE_ANCHORS[vintage], f"A{year_row}")
        }
        declared = {
            item.address: str(item.expected_value)
            for item in selector.guard_cells
            if item.address[0] in "AC" and int(item.address[1:]) >= 13
        }
        assert declared == expected, (
            f"{selector.expected_row_header_address}: declared {declared!r}"
        )


@pytest.mark.parametrize(("vintage", "address"), GUARD_CASES)
def test_qes_each_guard_rejects_mutated_publisher_cell(vintage, address):
    assert address in _guard_index(vintage), (
        f"Missing publisher guard: {SHEET}!{address}"
    )
    spec, expected, label = _guard_index(vintage)[address]
    coordinate = (SHEET, address)
    index = _cell_index(vintage)
    assert index[coordinate].raw_value == EXPECTED_GUARDS[vintage][address]
    assert str(expected) == EXPECTED_GUARDS[vintage][address]
    resolve_source_record(_cells(vintage), spec, cells_by_sheet_address=index)
    changed_index = {
        **index,
        coordinate: replace(index[coordinate], raw_value="unexpected publisher layout"),
    }
    with pytest.raises(ValueError, match=re.escape(label)):
        resolve_source_record(
            _cells(vintage), spec, cells_by_sheet_address=changed_index
        )


@pytest.mark.parametrize("vintage", ALIASES)
def test_qes_column_shift_yaml_mutant_is_rejected(vintage):
    package = _package(vintage)
    changed_sets = []
    for declared in package.record_sets:
        payload = deepcopy(declared.payload)
        for measure in payload["measures"]:
            if measure["column"] == "P":
                measure.update(column="R", expected_column_header="SBSZ9B")
        changed_sets.append(replace(declared, payload=payload))
    changed = replace(package, record_sets=tuple(changed_sets))
    with pytest.raises(AssertionError, match="selected publisher cells"):
        _assert_expected_publisher_map(
            vintage, changed.build_source_record_specs(YEARS[vintage])
        )


# An older vintage that re-emits a quarter the newer vintage owns: June 2025
# re-emitting June 2024 (row 17, owned by June 2026), and June 2026
# re-emitting June 2026 (row 21, owned by September 2026).
DUPLICATE_QUARTER_MUTANTS = (
    (JUNE_2025, "2024-Q2", 17, "Jun"),
    (JUNE_2026, "2026-Q2", 21, "Jun"),
)


@pytest.mark.parametrize(
    ("vintage", "period", "row", "header"), DUPLICATE_QUARTER_MUTANTS
)
def test_qes_duplicate_quarter_from_earlier_vintage_yaml_mutant_is_rejected(
    vintage, period, row, header
):
    package = _package(vintage)
    previous = package.record_sets[-1]
    payload = deepcopy(previous.payload)
    record_set_id = "stats_nz.qes.awe." + period.lower().replace("-", "")
    payload.update(
        record_set_id=record_set_id,
        record_set_spec_id=f"{record_set_id}.v1",
        source_record_id_prefix=record_set_id,
        period=period,
    )
    payload["rows"][0].update(row_number=row, expected_row_header=header)
    extra_quarter = replace(previous, payload=payload)
    changed = replace(package, record_sets=(*package.record_sets, extra_quarter))
    specs = changed.build_source_record_specs(YEARS[vintage])
    # The mutant resolves cleanly against the publisher workbook, so only the
    # literal ownership map stops it.
    for spec in specs:
        resolve_source_record(
            _cells(vintage), spec, cells_by_sheet_address=_cell_index(vintage)
        )
    with pytest.raises(AssertionError, match="publisher cell count drift"):
        _assert_expected_publisher_map(vintage, specs)


@pytest.mark.parametrize("vintage", ALIASES)
def test_qes_build_suite_passes_source_acceptance(vintage, tmp_path):
    report = build_source_suite(
        ALIASES[vintage], tmp_path / "suite", year=YEARS[vintage]
    )
    assert report.valid
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
    assert report.source_records.resolved_count == _expected_count(vintage)
    assert report.source_records.lineage_coverage == 1
    assert not report.agent_acceptance.errors
