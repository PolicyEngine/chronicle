"""IRS SOI Historic Table 2 TY2023 state AGI-band package.

The package emits, for 50 states and DC, one fact per published cell of
``23in55cmcsv.csv``: return count (N1) and AGI (A00100) for each of the ten
AGI stubs, with stub 9 ($500k-$1M) and stub 10 ($1M+) as separate facts.
These tests read the publisher CSV directly with the standard library, so the
values they check do not depend on Chronicle's own row parser.
"""

from __future__ import annotations

import csv
import hashlib
import math
from pathlib import Path

import pytest

from chronicle.core import validate_facts
from chronicle.source_package import load_source_package
from chronicle.sources.cells import validate_source_cells
from chronicle.sources.rows import validate_source_rows
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "db" / "data" / "irs_soi" / "historic_table_2"
CSV_2023 = RAW_DIR / "23in55cmcsv.csv"
CSV_SHA256 = "d1f7c8901fcefb2c46f5dd14f22715b7c8513794ce7b9ea6a6a947f1c548668f"
PACKAGE_ID = "soi-historic-table-2-state-agi-2023"
PACKAGE_2022_ID = "soi-historic-table-2-state-agi-2022"
AGI = "us:statutes/26/62#adjusted_gross_income"

# AGI stub -> (value id, lower bound, upper bound), from the SOI documentation
# for the Historic Table 2 state files.
STUBS = {
    1: ("under_1", -math.inf, 1),
    2: ("1_to_10k", 1, 10_000),
    3: ("10k_to_25k", 10_000, 25_000),
    4: ("25k_to_50k", 25_000, 50_000),
    5: ("50k_to_75k", 50_000, 75_000),
    6: ("75k_to_100k", 75_000, 100_000),
    7: ("100k_to_200k", 100_000, 200_000),
    8: ("200k_to_500k", 200_000, 500_000),
    9: ("500k_to_1m", 500_000, 1_000_000),
    10: ("1m_plus", 1_000_000, math.inf),
}
STUB_BY_VALUE_ID = {value_id: stub for stub, (value_id, _, _) in STUBS.items()}
MEASURE_COLUMNS = {"return_count": ("N1", 1), "adjusted_gross_income": ("A00100", 1000)}
NON_STATE_ROWS = {"US", "OA", "PR"}


def _publisher_cells() -> dict[tuple[str, int], dict[str, int]]:
    with CSV_2023.open(newline="", encoding="utf-8-sig") as handle:
        return {
            (row["STATE"], int(row["AGI_STUB"])): {
                column: int(row[column].replace(",", "")) for column in ("N1", "A00100")
            }
            for row in csv.DictReader(handle)
        }


@pytest.fixture(scope="module")
def facts():
    package = load_source_package(PACKAGE_ID)
    rows = package.build_source_rows(2023)
    cells = package.build_source_cells(2023, source_rows=rows)
    built = package.build_facts(2023, cells=cells, source_rows=rows)
    assert validate_source_rows(rows).valid
    assert validate_source_cells(cells).valid
    assert validate_facts(built).valid
    return built


def _parts(fact) -> tuple[str, str, str]:
    """(state code, band value id, measure id) from the source record id."""
    prefix = "irs_soi.ty2023.historic_table_2.state_agi."
    assert fact.source_record_id.startswith(prefix)
    state, band, measure = fact.source_record_id[len(prefix) :].split(".")
    return state.upper(), band, measure


def _bounds(fact) -> tuple[float, float]:
    lower, upper = -math.inf, math.inf
    for constraint in fact.constraints:
        assert constraint.variable == AGI
        if constraint.operator == ">=":
            lower = constraint.value
        elif constraint.operator == "<":
            upper = constraint.value
        else:  # pragma: no cover - a new operator is a packaging error
            raise AssertionError(constraint.operator)
    return lower, upper


def test_raw_artifact_is_the_registered_publisher_file():
    assert hashlib.sha256(CSV_2023.read_bytes()).hexdigest() == CSV_SHA256
    assert CSV_2023.stat().st_size == 757_078


def test_state_agi_2023_package_builds_split_top_bands(facts, tmp_path):
    by_id = {fact.source_record_id: fact for fact in facts}
    prefix = "irs_soi.ty2023.historic_table_2.state_agi"

    assert len(facts) == 1_020
    assert by_id[f"{prefix}.co.1m_plus.adjusted_gross_income"].value == (47_266_883_000)
    assert by_id[f"{prefix}.co.1m_plus.return_count"].value == 15_610
    assert by_id[f"{prefix}.co.500k_to_1m.adjusted_gross_income"].value == (
        25_370_899_000
    )
    assert by_id[f"{prefix}.co.500k_to_1m.return_count"].value == 38_030
    assert by_id[f"{prefix}.ca.1m_plus.return_count"].value == 132_720
    assert by_id[f"{prefix}.ca.1m_plus.adjusted_gross_income"].value == (
        400_221_114_000
    )
    co_top = by_id[f"{prefix}.co.1m_plus.adjusted_gross_income"]
    assert co_top.geography.id == "0400000US08"
    assert co_top.filters == {"filing_status": "all", "income_range": "1m_plus"}
    assert co_top.layout.source_column_id == "A00100"
    assert _bounds(co_top) == (1_000_000, math.inf)
    assert _bounds(by_id[f"{prefix}.co.500k_to_1m.return_count"]) == (
        500_000,
        1_000_000,
    )

    suite = build_source_suite(PACKAGE_ID, tmp_path / PACKAGE_ID, year=2023)
    assert suite.agent_acceptance.valid
    assert suite.agent_acceptance.counts["row_semantic_error_count"] == 0


def test_every_fact_carries_the_literal_2023_vintage(facts):
    text = (
        REPO_ROOT
        / "packages"
        / "irs_soi"
        / "historic_table_2_state_agi_2023"
        / "source_package.yaml"
    ).read_text()

    assert "{year}" not in text
    for fact in facts:
        assert fact.period.type == "tax_year"
        assert fact.period.value == 2023
        assert fact.source.source_sha256 == CSV_SHA256
        assert fact.source.vintage == "tax_year_2023"


@pytest.mark.parametrize("build_year", [2022, 2024])
def test_building_at_another_year_does_not_relabel_the_2023_file(facts, build_year):
    """The artifact is pinned: any build year yields the same TY2023 facts."""
    package = load_source_package(PACKAGE_ID)
    rows = package.build_source_rows(build_year)
    cells = package.build_source_cells(build_year, source_rows=rows)
    other = package.build_facts(build_year, cells=cells, source_rows=rows)

    def summary(items):
        return sorted(
            (fact.source_record_id, fact.value, fact.period.value) for fact in items
        )

    assert summary(other) == summary(facts)


def test_each_fact_is_exactly_one_publisher_cell(facts):
    """Invariant: value == the named CSV cell x value_scale, one row per fact."""
    publisher = _publisher_cells()
    for fact in facts:
        state, band, measure = _parts(fact)
        column, scale = MEASURE_COLUMNS[measure]
        assert len(fact.source_row_keys) == 1, fact.source_record_id
        assert fact.value == publisher[(state, STUB_BY_VALUE_ID[band])][column] * scale


def test_bands_partition_the_agi_line_in_every_state(facts):
    """Invariant: per state and measure the ten bands are ordered, contiguous
    and non-overlapping, and cover (-inf, inf)."""
    by_cell: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for fact in facts:
        state, _, measure = _parts(fact)
        by_cell.setdefault((state, measure), []).append(_bounds(fact))

    assert len(by_cell) == 51 * 2
    for key, intervals in by_cell.items():
        intervals.sort()
        assert intervals[0][0] == -math.inf, key
        assert intervals[-1][1] == math.inf, key
        for (_, upper), (lower, _) in zip(intervals, intervals[1:], strict=False):
            assert upper == lower, key
        assert intervals == [(STUBS[stub][1], STUBS[stub][2]) for stub in sorted(STUBS)]


def test_bands_add_up_to_the_publishers_state_total(facts):
    """Invariant: AGI bands sum exactly to the published stub-0 total; counts,
    rounded to tens by the publisher, sum to it within the rounding of eleven
    cells."""
    publisher = _publisher_cells()
    totals: dict[tuple[str, str], int] = {}
    for fact in facts:
        state, _, measure = _parts(fact)
        totals[(state, measure)] = totals.get((state, measure), 0) + fact.value

    states = {state for state, _ in publisher} - NON_STATE_ROWS
    assert len(states) == 51
    for state in states:
        assert totals[(state, "adjusted_gross_income")] == (
            publisher[(state, 0)]["A00100"] * 1000
        )
        count_gap = totals[(state, "return_count")] - publisher[(state, 0)]["N1"]
        assert abs(count_gap) <= 55, state
    for fact in facts:
        if _parts(fact)[2] == "return_count":
            assert fact.value % 10 == 0, fact.source_record_id


def test_2023_ids_parallel_the_2022_package_except_the_split_top_band(facts):
    """Consumers match vintages on the id with the tax year removed; only the
    top band differs, where 2022 publishes one summed row."""
    package_2022 = load_source_package(PACKAGE_2022_ID)
    rows = package_2022.build_source_rows(2022)
    cells = package_2022.build_source_cells(2022, source_rows=rows)
    ids_2022 = {
        fact.source_record_id.replace(".ty2022.", ".tyYYYY.")
        for fact in package_2022.build_facts(2022, cells=cells, source_rows=rows)
        if fact.source_record_id.rsplit(".", 1)[1] in MEASURE_COLUMNS
    }
    ids_2023 = {
        fact.source_record_id.replace(".ty2023.", ".tyYYYY.").replace(
            ".500k_to_1m.", ".500k_plus."
        )
        for fact in facts
        if ".1m_plus." not in fact.source_record_id
    }

    assert ids_2023 == ids_2022
    assert len(ids_2022) == 51 * 9 * 2
