"""Row-grain source concepts on the FPB June 2026 outlook annex.

Each annex row is its own publisher series. A table-wide source concept
(``…t07.published_cell``) gave every row of a table one observed concept, so a
consumer that reads the source concept as series identity, as Microcosm's
roll-forward check does, took total population and working-age population for
one series. Each fact now names its table and row. That moves the aggregate
and legacy keys, which hash the observed concept, and leaves the semantic key
and the value alone.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from functools import lru_cache

import pytest
import yaml

from chronicle.consumer_contract import consumer_fact_rows
from chronicle.source_package import load_source_package

FPB_OUTLOOK = "fpb-economic-outlook-2026-2031-june-2026"
PREFIX = "fpb.economic_outlook_2026_2031"
BUILD_YEARS = (2023, 2026)
ANNEX_YEARS = list(range(2022, 2032))
TABLE_ROWS = {"t01": 4, "t06": 3, "t07": 10, "t11": 21, "t17": 7, "t24": 55}
# sha256 of the sorted [source_record_id, semantic_fact_key, value] rows. The
# same digest holds at 2c7e8357, before the row-grain concepts.
SEMANTIC_DIGEST = "a60a849390016a2da1ed6ca512e9107b571bf0be7dabd8ad33ec9d34d0d0dabb"
# sha256 of the sorted [source_record_id, aggregate_fact_key, legacy_fact_key]
# rows under the row-grain concepts.
ROW_KEY_DIGEST = "dc0d8c714a477024dcbadd17c647bb5d39b3b9d149595928175ae9501423585e"


@lru_cache
def _facts(year: int) -> tuple:
    package = load_source_package(FPB_OUTLOOK)
    cells = package.build_source_cells(year)
    return tuple(package.build_facts(year, cells=list(cells)))


@lru_cache
def _table_of_record_set() -> dict[str, str]:
    package = load_source_package(FPB_OUTLOOK)
    with (package.package_path / "source_package.yaml").open(encoding="utf-8") as f:
        record_sets = yaml.safe_load(f)["record_sets"]
    return {rs["record_set_id"]: rs["sheet_name"].lower() for rs in record_sets}


def _digest(rows: list[list]) -> str:
    canonical = json.dumps(sorted(rows), separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


@pytest.mark.parametrize("year", BUILD_YEARS)
def test_every_fact_names_its_table_and_row(year):
    tables = _table_of_record_set()
    for fact in _facts(year):
        layout = fact.layout
        assert layout.groupby_value_id == layout.source_row_id
        assert fact.measure.source_concept == (
            f"{PREFIX}.{tables[layout.record_set_id]}.{layout.groupby_value_id}"
        )
        assert fact.measure.concept_relation == "source_label"


@pytest.mark.parametrize("year", BUILD_YEARS)
def test_each_row_is_one_series_across_the_annex_years(year):
    series = defaultdict(list)
    for fact in _facts(year):
        series[fact.measure.source_concept].append(fact)

    assert Counter(concept.split(".")[2] for concept in series) == TABLE_ROWS
    for concept, facts in series.items():
        assert sorted(fact.period.value for fact in facts) == ANNEX_YEARS, concept
        assert len({fact.layout.record_set_spec_id for fact in facts}) == 1
        assert len({fact.measure.concept for fact in facts}) == 1
        assert len({fact.measure.unit for fact in facts}) == 1
    # One row per spec, so no two rows share a source concept.
    specs = {fact.layout.record_set_spec_id for fact in _facts(year)}
    assert len(specs) == len(series) == sum(TABLE_ROWS.values())


def test_population_rows_are_separate_series():
    concepts = {
        fact.layout.groupby_value_id: fact.measure.source_concept
        for fact in _facts(2026)
        if fact.period.value == 2025
    }

    assert concepts["total_population"] == f"{PREFIX}.t07.total_population"
    assert concepts["working_age_population"] == f"{PREFIX}.t07.working_age_population"


@pytest.mark.parametrize("year", BUILD_YEARS)
def test_row_concepts_move_no_semantic_key_or_value(year):
    rows = consumer_fact_rows(list(_facts(year)))

    assert (
        _digest(
            [
                [
                    row["lineage"]["source_record_id"],
                    row["semantic_fact_key"],
                    row["value"],
                ]
                for row in rows
            ]
        )
        == SEMANTIC_DIGEST
    )


@pytest.mark.parametrize("year", BUILD_YEARS)
def test_row_concepts_pin_aggregate_and_legacy_keys(year):
    rows = consumer_fact_rows(list(_facts(year)))

    assert len({row["aggregate_fact_key"] for row in rows}) == len(rows)
    assert (
        _digest(
            [
                [
                    row["lineage"]["source_record_id"],
                    row["aggregate_fact_key"],
                    row["legacy_fact_key"],
                ]
                for row in rows
            ]
        )
        == ROW_KEY_DIGEST
    )
