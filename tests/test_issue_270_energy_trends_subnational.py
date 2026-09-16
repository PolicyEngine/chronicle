"""Regression coverage for issue 270 Energy Trends and subnational facts."""

from __future__ import annotations

import re

import pytest

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import validate_consumer_fact_contract
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources.cells import validate_source_cells


PACKAGES = {
    "desnz-energy-trends-domestic-gas-2026": 21,
    "desnz-energy-trends-domestic-electricity-2026": 22,
    "desnz-subnational-electricity-consumption-2024": 1464,
    "desnz-subnational-gas-consumption-2024": 1452,
}


def _facts(alias: str):
    return load_source_package(alias).build_facts(2026)


def test_issue_270_energy_packages_are_registered_for_the_uk_bundle():
    assert set(PACKAGES) <= set(SOURCE_PACKAGE_ALIASES)
    assert set(PACKAGES) <= set(UK_BUNDLE_SOURCES)


@pytest.mark.parametrize(("alias", "fact_count"), sorted(PACKAGES.items()))
def test_issue_270_energy_packages_preserve_valid_source_cells(alias, fact_count):
    package = load_source_package(alias)
    report = validate_source_package(package.package_path, year=2026)
    cells = package.build_source_cells(2026)
    facts = package.build_facts(2026, cells=cells)

    assert report.valid, report.to_dict()
    assert len(facts) == fact_count
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid


def test_energy_trends_has_every_published_period_from_2022():
    gas = _facts("desnz-energy-trends-domestic-gas-2026")
    electricity = _facts("desnz-energy-trends-domestic-electricity-2026")

    expected_annual = {2022, 2023, 2024, 2025}
    expected_gas_quarters = {
        f"{year}-Q{quarter}"
        for year in range(2022, 2027)
        for quarter in range(1, 5)
        if (year, quarter) <= (2026, 1)
    }
    expected_electricity_quarters = expected_gas_quarters | {"2026-Q2"}

    assert {
        fact.period.value for fact in gas if fact.period.type == "calendar_year"
    } == (expected_annual)
    assert {fact.period.value for fact in gas if fact.period.type == "quarter"} == (
        expected_gas_quarters
    )
    assert {
        fact.period.value for fact in electricity if fact.period.type == "calendar_year"
    } == expected_annual
    assert {
        fact.period.value for fact in electricity if fact.period.type == "quarter"
    } == expected_electricity_quarters
    assert {fact.filters["temperature_adjustment"] for fact in gas + electricity} == {
        "actual_temperature"
    }


def test_energy_trends_preserves_representative_publisher_values():
    gas = {fact.source_record_id: fact for fact in _facts(PACKAGE_GAS)}
    electricity = {fact.source_record_id: fact for fact in _facts(PACKAGE_ELECTRICITY)}

    assert gas[
        "desnz.energy_trends.4_1.domestic.2022.domestic_consumption.consumption"
    ].value == pytest.approx(273_585_930_000)
    assert gas[
        "desnz.energy_trends.4_1.domestic.2026_q1.domestic_consumption.consumption"
    ].value == pytest.approx(113_987_700_000)
    assert electricity[
        "desnz.energy_trends.5_5.domestic.2022.domestic_consumption.consumption"
    ].value == pytest.approx(93_887_800_000)
    assert electricity[
        "desnz.energy_trends.5_5.domestic.2026_q2.domestic_consumption.consumption"
    ].value == pytest.approx(21_221_400_000)


def test_energy_trends_uses_one_fuel_neutral_series_label():
    facts = [
        *_facts(PACKAGE_GAS),
        *_facts(PACKAGE_ELECTRICITY),
    ]

    assert {
        fact.layout.groupby_value_label
        for fact in facts
        if fact.layout.groupby_value_id == "domestic_consumption"
    } == {"Domestic consumption"}


def test_latest_energy_trends_quarters_keep_provisional_status_in_notes():
    gas = {fact.source_record_id: fact for fact in _facts(PACKAGE_GAS)}
    electricity = {fact.source_record_id: fact for fact in _facts(PACKAGE_ELECTRICITY)}

    latest = (
        gas[
            "desnz.energy_trends.4_1.domestic.2026_q1.domestic_consumption.consumption"
        ],
        electricity[
            "desnz.energy_trends.5_5.domestic.2026_q2.domestic_consumption.consumption"
        ],
    )
    assert all("provisional" in fact.period_coverage.notes.lower() for fact in latest)


PACKAGE_GAS = "desnz-energy-trends-domestic-gas-2026"
PACKAGE_ELECTRICITY = "desnz-energy-trends-domestic-electricity-2026"
PACKAGE_SUBNATIONAL_ELECTRICITY = "desnz-subnational-electricity-consumption-2024"
PACKAGE_SUBNATIONAL_GAS = "desnz-subnational-gas-consumption-2024"


@pytest.mark.parametrize(
    ("alias", "expected_fact_count", "expected_geography_count"),
    [
        (PACKAGE_SUBNATIONAL_ELECTRICITY, 732, 366),
        (PACKAGE_SUBNATIONAL_GAS, 726, 363),
    ],
)
def test_subnational_packages_cover_the_published_geographies(
    alias, expected_fact_count, expected_geography_count
):
    facts = _facts(alias)
    facts_2024 = [fact for fact in facts if fact.period.value == 2024]

    assert len(facts_2024) == expected_fact_count
    assert len({fact.geography.id for fact in facts_2024}) == expected_geography_count
    assert all(re.fullmatch(r"[A-Z][0-9]{8}", fact.geography.id) for fact in facts_2024)
    assert {fact.geography.level for fact in facts_2024} == {
        "country",
        "region",
        "local_authority",
        "statistical_scope",
    }
    assert {fact.filters["metric"] for fact in facts_2024} == {
        "meter_count",
        "consumption",
    }


def test_subnational_packages_keep_units_reference_periods_and_weather_basis():
    electricity = _facts(PACKAGE_SUBNATIONAL_ELECTRICITY)
    gas = _facts(PACKAGE_SUBNATIONAL_GAS)

    assert {fact.measure.unit for fact in electricity + gas} == {"count", "kwh"}
    assert {fact.filters["temperature_adjustment"] for fact in electricity} == {
        "as_reported"
    }
    assert {fact.filters["temperature_adjustment"] for fact in gas} == {
        "weather_corrected"
    }
    electricity_2024 = next(
        fact
        for fact in electricity
        if fact.period.value == 2024 and fact.geography.id == "K03000001"
    )
    gas_reference_facts = [
        fact
        for fact in gas
        if fact.geography.id == "K03000001" and fact.filters["metric"] == "meter_count"
    ]
    assert electricity_2024.period_coverage.start_date == "2024-02-01"
    assert electricity_2024.period_coverage.end_date == "2025-01-31"
    assert {fact.period.type for fact in gas_reference_facts} == {"calendar_year"}
    assert {fact.period_coverage.basis for fact in gas_reference_facts} == {
        "survey_reference"
    }
    assert all(fact.period_coverage.start_date is None for fact in gas_reference_facts)
    assert all(fact.period_coverage.end_date is None for fact in gas_reference_facts)
    assert {
        fact.period_coverage.source_period_label for fact in gas_reference_facts
    } == {
        "2023 (mid-May 2023 to mid-May 2024)",
        "2024 (mid-May 2024 to mid-May 2025)",
    }
    assert all(
        "not exact dates" in fact.period_coverage.notes
        and "calendar_year identity" in fact.period_coverage.notes
        for fact in gas_reference_facts
    )


def test_subnational_gas_omits_blank_and_zero_non_gas_island_rows():
    facts = _facts(PACKAGE_SUBNATIONAL_GAS)
    excluded_geographies = {"E06000053", "S12000023", "S12000027"}

    assert not [
        fact
        for fact in facts
        if fact.geography.id in excluded_geographies
        and fact.period.value in {2023, 2024}
    ]
    assert all(fact.value != 0 for fact in facts)


def test_subnational_packages_preserve_representative_great_britain_values():
    electricity = {
        fact.source_record_id: fact for fact in _facts(PACKAGE_SUBNATIONAL_ELECTRICITY)
    }
    gas = {fact.source_record_id: fact for fact in _facts(PACKAGE_SUBNATIONAL_GAS)}

    assert electricity[
        "desnz.subnational.electricity.cy2024.k03000001.domestic_meter_count"
    ].value == pytest.approx(29_344_362)
    assert electricity[
        "desnz.subnational.electricity.cy2024.k03000001.domestic_consumption"
    ].value == pytest.approx(97_503_554_566.10884)
    assert gas[
        "desnz.subnational.gas.cy2024.k03000001.domestic_meter_count"
    ].value == pytest.approx(24_702_708)
    assert gas[
        "desnz.subnational.gas.cy2024.k03000001.domestic_consumption"
    ].value == pytest.approx(280_605_464_567.4601)


def test_subnational_gas_meter_counts_are_not_derived_connection_shares():
    gas_meter_facts = [
        fact
        for fact in _facts(PACKAGE_SUBNATIONAL_GAS)
        if fact.filters["metric"] == "meter_count"
    ]

    assert {fact.measure.concept for fact in gas_meter_facts} == {
        "desnz.subnational.domestic_gas_meter_count"
    }
    assert all(fact.aggregation.method == "sum" for fact in gas_meter_facts)
    assert all("share" not in fact.measure.concept for fact in gas_meter_facts)
