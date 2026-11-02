"""Period coverage on the Eurostat FX and FPB outlook facts in the BE suite.

Microcosm resolves the 2024 USD/EUR annual average and FPB outlook rows only
when a fact's ``period_coverage`` carries both endpoints. Coverage is
provenance, never identity: these tests also pin every fact's keys and value to
their digest at 2c7e8357, before either package declared coverage.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import Counter
from decimal import Decimal
from functools import lru_cache

import pytest

from chronicle.consumer_contract import (
    build_aggregate_fact_key,
    build_semantic_fact_key,
    consumer_fact_rows,
)
from chronicle.core import PeriodCoverage, build_fact_key, validate_facts
from chronicle.source_package import load_source_package

EUROSTAT_FX = "eurostat-ert-bil-eur-a-usd"
FPB_OUTLOOK = "fpb-economic-outlook-2026-2031-june-2026"
ALIASES = (EUROSTAT_FX, FPB_OUTLOOK)
# The BE suite builds at the default year, 2023; both packages pin artifact
# year 2026. Neither declares anything by year, so both years build alike.
BUILD_YEARS = (2023, 2026)
# sha256 of the sorted [source_record_id, aggregate_fact_key, semantic_fact_key,
# legacy_fact_key, value] rows, computed at 2c7e8357 with no period_coverage.
KEY_DIGESTS = {
    EUROSTAT_FX: "747005719cca792770b4b7fa19831be5faf5311de52dc3edee235889229d5c73",
    FPB_OUTLOOK: "3ba96f0eca16666d5ab6b62eefe7f9057f89aef5077f8e9572a5ff659b732b4b",
}
FPB_OBSERVED_YEARS = range(2022, 2026)
FPB_PROJECTED_YEARS = range(2026, 2032)
# Microcosm's factor-operand validation accepts exactly these coverage fields.
CONSUMER_COVERAGE_FIELDS = {
    "start_date",
    "end_date",
    "basis",
    "source_period_label",
    "notes",
}


@lru_cache
def _facts(alias: str, year: int) -> tuple:
    package = load_source_package(alias)
    cells = package.build_source_cells(year)
    return tuple(package.build_facts(year, cells=list(cells)))


@pytest.mark.parametrize("year", BUILD_YEARS)
@pytest.mark.parametrize("alias", ALIASES)
def test_every_fact_covers_exactly_its_calendar_year(alias, year):
    facts = _facts(alias, year)

    assert len(facts) == {EUROSTAT_FX: 55, FPB_OUTLOOK: 1000}[alias]
    for fact in facts:
        coverage = fact.period_coverage
        assert coverage is not None, fact.source_record_id
        assert fact.period.type == "calendar_year"
        assert coverage.start_date == f"{fact.period.value}-01-01"
        assert coverage.end_date == f"{fact.period.value}-12-31"
        assert coverage.source_period_label == str(fact.period.value)
        assert coverage.accounting_basis is None
        assert str(fact.period.value) in coverage.notes
    assert validate_facts(facts).valid


@pytest.mark.parametrize("alias", ALIASES)
def test_consumer_rows_expose_both_coverage_endpoints(alias):
    for row in consumer_fact_rows(_facts(alias, 2023)):
        coverage = row["period_coverage"]
        assert set(coverage) == CONSUMER_COVERAGE_FIELDS
        assert coverage["start_date"] <= coverage["end_date"]


def test_eurostat_exchange_rates_are_calendar_year_annual_averages():
    facts = _facts(EUROSTAT_FX, 2026)

    assert Counter(fact.period_coverage.basis for fact in facts) == {"calendar": 55}
    assert {fact.assertion for fact in facts} == {"observation"}
    for fact in facts:
        assert (fact.filters["freq"], fact.filters["statinfo"]) == ("A", "AVG")
        assert "statinfo=AVG 'Average'" in fact.period_coverage.notes
    # The operand Microcosm-BE money normalization reads.
    usd_2024 = next(fact for fact in facts if fact.period.value == 2024)
    assert Decimal(str(usd_2024.value)) == Decimal("1.0824")
    assert dataclasses.replace(usd_2024.period_coverage, notes=None) == (
        PeriodCoverage(
            start_date="2024-01-01",
            end_date="2024-12-31",
            basis="calendar",
            source_period_label="2024",
        )
    )


def test_fpb_basis_follows_the_observation_projection_split():
    facts = _facts(FPB_OUTLOOK, 2026)

    assert Counter(
        (fact.period.value, fact.assertion, fact.period_coverage.basis)
        for fact in facts
    ) == {
        **{(year, "observation", "calendar"): 100 for year in FPB_OBSERVED_YEARS},
        **{
            (year, "source_projection", "projection_horizon"): 100
            for year in FPB_PROJECTED_YEARS
        },
    }
    for fact in facts:
        assert "2026-2031 projection period" in fact.period_coverage.notes


@pytest.mark.parametrize("year", BUILD_YEARS)
@pytest.mark.parametrize("alias", ALIASES)
def test_period_coverage_moved_no_fact_key_or_value(alias, year):
    identity = sorted(
        [
            row["lineage"]["source_record_id"],
            row["aggregate_fact_key"],
            row["semantic_fact_key"],
            row["legacy_fact_key"],
            row["value"],
        ]
        for row in consumer_fact_rows(_facts(alias, year))
    )
    canonical = json.dumps(identity, separators=(",", ":")).encode()

    assert hashlib.sha256(canonical).hexdigest() == KEY_DIGESTS[alias]


@pytest.mark.parametrize("alias", ALIASES)
def test_fact_keys_ignore_any_period_coverage(alias):
    variants = (
        None,
        PeriodCoverage(),
        PeriodCoverage(
            start_date="1900-01-01",
            end_date="2100-12-31",
            basis="fiscal",
            source_period_label="other",
            accounting_basis="cash",
            notes="other",
        ),
    )
    for fact in _facts(alias, 2026):
        keys = (
            build_aggregate_fact_key(fact),
            build_semantic_fact_key(fact),
            build_fact_key(fact),
        )
        for coverage in variants:
            other = dataclasses.replace(fact, period_coverage=coverage)
            assert (
                build_aggregate_fact_key(other),
                build_semantic_fact_key(other),
                build_fact_key(other),
            ) == keys
