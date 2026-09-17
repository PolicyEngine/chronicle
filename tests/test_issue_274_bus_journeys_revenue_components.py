"""Regression coverage for the published bus inputs requested in issue 274."""

from __future__ import annotations

import pytest

from chronicle.bundle import UK_BUNDLE_SOURCES, build_bundle
from chronicle.consumer_contract import validate_consumer_fact_contract
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources.cells import validate_source_cells


ISSUE_274_ARTIFACT_YEARS = {
    "dfi-ni-bus-concessionary-journeys-2024-25": 2025,
    "dft-bus01-passenger-journeys-2025": 2025,
    "dft-bus05i-revenue-support-2025": 2025,
    "dft-nts0303-mode-trips-2025": 2025,
    "dft-nts0601-age-mode-trips-2025": 2025,
}

EXPECTED_FACT_COUNTS = {
    "dfi-ni-bus-concessionary-journeys-2024-25": 6,
    "dft-bus01-passenger-journeys-2025": 804,
    "dft-bus05i-revenue-support-2025": 78,
    "dft-nts0303-mode-trips-2025": 9,
    "dft-nts0601-age-mode-trips-2025": 81,
}

REPRESENTATIVE_PUBLISHER_FACTS = {
    "dfi-ni-bus-concessionary-journeys-2024-25": (
        "dfi_ni.public_transport.figure_6.fy2024."
        "full_fare_concession.passenger_journeys",
        8_960_000,
    ),
    "dft-bus01-passenger-journeys-2025": (
        "dft.bus01.bus01c.total_concessionary.fy2025.england.passenger_journeys",
        1_016_631_373.68352,
    ),
    "dft-bus05i-revenue-support-2025": (
        "dft.bus05i.bus05ai.gross_operating_revenue.fy2025.england."
        "total_estimated_operating_revenue",
        6_616_074_977.27538,
    ),
    "dft-nts0303-mode-trips-2025": (
        "dft.nts0303a.mode_trips.cy2025.cy2025.other_local_bus_trips_per_person",
        27.7152103800693,
    ),
    "dft-nts0601-age-mode-trips-2025": (
        "dft.nts0601a.mode_trips_by_age.cy2025.age_70_and_over."
        "other_local_bus_trips_per_person",
        36.2889056732402,
    ),
}

BUS01_URBAN_RURAL_GEOGRAPHIES = {
    "dft:other_predominantly_urban_areas",
    "dft:urban_with_significant_rural",
    "dft:largely_or_mainly_rural",
}

BUS01_GEOGRAPHIES = {
    "E92000001",
    "dft:english_non_metropolitan_areas",
    "dft:english_metropolitan_areas",
    "E12000007",
    "dft:england_outside_london",
    "E12000001",
    "E12000002",
    "E12000003",
    "E12000004",
    "E12000005",
    "E12000006",
    "E12000008",
    "E12000009",
} | BUS01_URBAN_RURAL_GEOGRAPHIES

NTS_TRIP_CONCEPTS = {
    "dft.bus_in_london_trips_per_person",
    "dft.other_local_bus_trips_per_person",
    "dft.all_modes_trips_per_person",
}

NTS0601_AGE_BANDS = {
    "0 to 16",
    "17 to 20",
    "21 to 29",
    "30 to 39",
    "40 to 49",
    "50 to 59",
    "60 to 69",
    "70 and over",
    "All Ages",
}


def _facts(alias):
    return load_source_package(alias).build_facts(ISSUE_274_ARTIFACT_YEARS[alias])


def test_issue_274_packages_are_registered_and_bundled():
    assert set(ISSUE_274_ARTIFACT_YEARS) <= set(SOURCE_PACKAGE_ALIASES)
    assert set(ISSUE_274_ARTIFACT_YEARS) <= set(UK_BUNDLE_SOURCES)


def test_issue_274_packages_pass_bundle_acceptance(tmp_path):
    report = build_bundle(
        tmp_path / "issue-274-bundle",
        year=2025,
        sources=tuple(ISSUE_274_ARTIFACT_YEARS),
    )

    assert report.valid, report.to_dict()
    assert not report.errors


@pytest.mark.parametrize(
    ("alias", "year"),
    sorted(ISSUE_274_ARTIFACT_YEARS.items()),
)
def test_issue_274_packages_build_valid_consumer_facts(alias, year):
    package = load_source_package(alias)
    report = validate_source_package(package.package_path, year=year)
    cells = package.build_source_cells(year)
    facts = package.build_facts(year, cells=cells)

    assert report.valid, report.to_dict()
    assert cells
    assert len(facts) == EXPECTED_FACT_COUNTS[alias]
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid


@pytest.mark.parametrize(
    ("alias", "expected"),
    sorted(REPRESENTATIVE_PUBLISHER_FACTS.items()),
)
def test_issue_274_packages_preserve_representative_publisher_values(alias, expected):
    source_record_id, expected_value = expected
    facts = {fact.source_record_id: fact for fact in _facts(alias)}

    assert facts[source_record_id].value == pytest.approx(expected_value)


def test_issue_274_facts_declare_exact_period_coverage():
    for alias in ISSUE_274_ARTIFACT_YEARS:
        facts = _facts(alias)

        assert all(fact.period_coverage is not None for fact in facts)
        assert all(fact.period_coverage.start_date for fact in facts)
        assert all(fact.period_coverage.end_date for fact in facts)
        assert all(fact.period_coverage.basis for fact in facts)


def test_bus01_carries_total_and_published_concessionary_journey_series():
    facts = _facts("dft-bus01-passenger-journeys-2025")
    all_journeys = [fact for fact in facts if "journey_category" not in fact.filters]
    elderly_disabled = [
        fact
        for fact in facts
        if fact.filters.get("journey_category") == "elderly_disabled_concessionary"
    ]
    total_concessionary = [
        fact
        for fact in facts
        if fact.filters.get("journey_category") == "total_concessionary"
    ]

    assert {fact.measure.concept for fact in facts} == {
        "dft.local_bus_passenger_journeys"
    }
    assert {fact.geography.id for fact in facts} == BUS01_GEOGRAPHIES
    assert len(all_journeys) == 21 * 16
    assert len(elderly_disabled) == 18 * 13
    assert len(total_concessionary) == 18 * 13
    assert {fact.period.value for fact in all_journeys} == set(range(2005, 2026))
    assert {fact.period.value for fact in elderly_disabled} == set(range(2008, 2026))
    assert {fact.period.value for fact in total_concessionary} == set(range(2008, 2026))
    assert {fact.period.type for fact in facts} == {"fiscal_year"}
    assert {
        constraint.label
        for fact in elderly_disabled + total_concessionary
        for constraint in fact.constraints
        if constraint.variable == "journey_category"
    } == {"Journey Category"}

    latest = [fact for fact in facts if fact.period.value == 2025]
    assert {fact.period_coverage.start_date for fact in latest} == {"2024-04-01"}
    assert {fact.period_coverage.end_date for fact in latest} == {"2025-03-31"}


def test_bus01_carries_published_urban_rural_totals_without_inventing_splits():
    facts = _facts("dft-bus01-passenger-journeys-2025")
    urban_rural = [
        fact for fact in facts if fact.geography.id in BUS01_URBAN_RURAL_GEOGRAPHIES
    ]

    assert len(urban_rural) == 3 * 21
    assert {fact.period.value for fact in urban_rural} == set(range(2005, 2026))
    assert all("journey_category" not in fact.filters for fact in urban_rural)
    assert {
        geography_id: sum(fact.geography.id == geography_id for fact in urban_rural)
        for geography_id in BUS01_URBAN_RURAL_GEOGRAPHIES
    } == {geography_id: 21 for geography_id in BUS01_URBAN_RURAL_GEOGRAPHIES}

    latest_values = {
        fact.geography.id: fact.value
        for fact in urban_rural
        if fact.period.value == 2025
    }
    assert latest_values == pytest.approx(
        {
            "dft:other_predominantly_urban_areas": 543_030_275.74153,
            "dft:urban_with_significant_rural": 294_497_821.00725996,
            "dft:largely_or_mainly_rural": 236_387_358.09336,
        }
    )


def test_bus05_carries_each_published_support_component_and_gross_revenue():
    facts = _facts("dft-bus05i-revenue-support-2025")
    support_concepts = {
        "dft.local_bus_net_public_transport_support",
        "dft.local_bus_concessionary_travel_reimbursement",
        "dft.local_bus_bus_service_operators_grant",
    }
    support = [fact for fact in facts if fact.measure.concept in support_concepts]
    gross_revenue = [
        fact
        for fact in facts
        if fact.measure.concept == "dft.local_bus_total_estimated_operating_revenue"
    ]

    assert len(support) == 3 * 5 * 3
    assert {fact.measure.concept for fact in support} == support_concepts
    assert {fact.period.value for fact in support} == {2023, 2024, 2025}
    assert {fact.geography.id for fact in support} == {
        "E92000001",
        "E12000007",
        "dft:england_outside_london",
        "dft:english_metropolitan_areas",
        "dft:english_non_metropolitan_areas",
    }
    assert len(gross_revenue) == 3 * 3
    assert {fact.geography.id for fact in gross_revenue} == {
        "E92000001",
        "E12000007",
        "dft:england_outside_london",
    }


def test_nts0303_and_nts0601_cover_requested_years_modes_and_ages():
    all_ages = _facts("dft-nts0303-mode-trips-2025")
    by_age = _facts("dft-nts0601-age-mode-trips-2025")

    assert {fact.period.value for fact in all_ages} == {2023, 2024, 2025}
    assert {fact.period.value for fact in by_age} == {2023, 2024, 2025}
    assert {fact.measure.concept for fact in all_ages} == NTS_TRIP_CONCEPTS
    assert {fact.measure.concept for fact in by_age} == NTS_TRIP_CONCEPTS
    assert {tuple(fact.filters.items()) for fact in all_ages} == {()}
    assert {fact.filters["age_band"] for fact in by_age} == NTS0601_AGE_BANDS
    assert {fact.filters["sex"] for fact in by_age} == {"All people"}
    assert {fact.geography.id for fact in all_ages + by_age} == {"E92000001"}
    assert {
        constraint.label
        for fact in by_age
        for constraint in fact.constraints
        if constraint.variable == "age_band"
    } == {"Age band"}


def test_nts0601_all_ages_rows_match_the_published_nts0303_totals():
    nts0303 = {
        (fact.period.value, fact.measure.concept): fact.value
        for fact in _facts("dft-nts0303-mode-trips-2025")
    }
    nts0601 = {
        (fact.period.value, fact.measure.concept): fact.value
        for fact in _facts("dft-nts0601-age-mode-trips-2025")
        if fact.filters["age_band"] == "All Ages"
    }

    assert nts0601 == nts0303


def test_dfi_carries_published_full_fare_concession_journeys_without_a_remainder():
    facts = _facts("dfi-ni-bus-concessionary-journeys-2024-25")
    concession = [
        fact
        for fact in facts
        if fact.measure.concept
        == "dfi_ni.translink_bus.full_fare_concession_passenger_journeys"
    ]

    assert len(concession) == 6
    assert {fact.period.value for fact in concession} == set(range(2019, 2025))
    assert {fact.geography.id for fact in concession} == {"N92000002"}
    assert {tuple(sorted(fact.filters.items())) for fact in concession} == {
        (("transport_mode", "bus"), ("travel_status", "full_fare_concession"))
    }

    concepts = {fact.measure.concept for fact in facts}
    assert all("fare_paying" not in concept for concept in concepts)


def test_issue_274_packages_do_not_publish_requested_downstream_calculations():
    concepts = {
        fact.measure.concept
        for alias in ISSUE_274_ARTIFACT_YEARS
        for fact in _facts(alias)
    }

    assert all("fare_paying" not in concept for concept in concepts)
    assert all("revenue_per_journey" not in concept for concept in concepts)
    assert all("journey_share" not in concept for concept in concepts)
