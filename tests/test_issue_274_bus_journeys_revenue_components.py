"""Regression coverage for the published bus inputs requested in issue 274."""

from __future__ import annotations

import pytest

from chronicle.bundle import UK_BUNDLE_SOURCES, build_bundle
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
    "dft-bus05i-revenue-support-2025": 102,
    "dft-nts0303-mode-trips-2025": 9,
    "dft-nts0601-age-mode-trips-2025": 81,
}

LEGACY_BUS05_FACT_KEYS = {
    "dft.bus05i.bus05ai.fare_receipts.fy2023.england.passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:a80c1fdac1658daddcb7e7ff",
        "ledger.semantic_fact.v2:00d8d9d2379db72608394280",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2023.england_outside_london."
    "passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:9328a861a0b4ed62357e19e2",
        "ledger.semantic_fact.v2:c863134e679b8ede3a502606",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2023.english_metropolitan_areas."
    "passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:d6efd4d0fa84bfb1ef2882d2",
        "ledger.semantic_fact.v2:555c41a2249e0060efcc49c4",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2023.english_non_metropolitan_areas."
    "passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:4175a90f074112d800ddb3df",
        "ledger.semantic_fact.v2:67ab51e28deee30aa40d9681",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2023.london.passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:dd2f3034c9cb6369e0f75eea",
        "ledger.semantic_fact.v2:f64077ddfaccc7560bdda1ac",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2024.england.passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:a042884c4d97209c3db1a40d",
        "ledger.semantic_fact.v2:4b913b97a0513b3bd606d077",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2024.england_outside_london."
    "passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:edba4d0a19a1c09ab1aaadfc",
        "ledger.semantic_fact.v2:0299e3715f9735dc7eff4d42",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2024.english_metropolitan_areas."
    "passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:66463024aed5e1ff4d738ffd",
        "ledger.semantic_fact.v2:9c5ea7202e38b7b1248be897",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2024.english_non_metropolitan_areas."
    "passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:bfb9b1b1c64d459bcbc39bd3",
        "ledger.semantic_fact.v2:3df10d6bf7c0029defce9cc4",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2024.london.passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:ebf1639656d41b2f42dcd9ad",
        "ledger.semantic_fact.v2:2a8ec7218e9f86856385450b",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2025.england.passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:2ece7c3d283b6de43b30389f",
        "ledger.semantic_fact.v2:9760cf3d8cd14de93b09968f",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2025.england_outside_london."
    "passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:465d300355c85e7c498397dd",
        "ledger.semantic_fact.v2:79496e0e39d6a38e3fa97c67",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2025.english_metropolitan_areas."
    "passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:98a9d82e78c19322b71b3ae0",
        "ledger.semantic_fact.v2:266e53fe8d7bceb31c51efec",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2025.english_non_metropolitan_areas."
    "passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:65aae4855ef3826563da85fd",
        "ledger.semantic_fact.v2:f17af3091a6632c961c1ead9",
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2025.london.passenger_fare_receipts": (
        "ledger.aggregate_fact.v2:33611c64d2048fe660501802",
        "ledger.semantic_fact.v2:8587d34e39717bcb3abf7e1b",
    ),
    "dft.bus05i.bus05bi.net_support.fy2023.england.total_estimated_net_support": (
        "ledger.aggregate_fact.v2:e89c824a7e7b414503746541",
        "ledger.semantic_fact.v2:e4cd5838d7b6607a9191c51f",
    ),
    "dft.bus05i.bus05bi.net_support.fy2023.england_outside_london."
    "total_estimated_net_support": (
        "ledger.aggregate_fact.v2:555920791138ab05c843c05d",
        "ledger.semantic_fact.v2:54a806e5080b33ea05fefa59",
    ),
    "dft.bus05i.bus05bi.net_support.fy2023.london.total_estimated_net_support": (
        "ledger.aggregate_fact.v2:eb637416cc203d3c477c00eb",
        "ledger.semantic_fact.v2:5ce675da4a86f56f4169328e",
    ),
    "dft.bus05i.bus05bi.net_support.fy2024.england.total_estimated_net_support": (
        "ledger.aggregate_fact.v2:1085667f2638aadc22f148df",
        "ledger.semantic_fact.v2:f14f4f17d7b674b74c18b3fb",
    ),
    "dft.bus05i.bus05bi.net_support.fy2024.england_outside_london."
    "total_estimated_net_support": (
        "ledger.aggregate_fact.v2:12efc43d192b68eb7c8bc4ee",
        "ledger.semantic_fact.v2:6482e359ce082e8fb83bb779",
    ),
    "dft.bus05i.bus05bi.net_support.fy2024.london.total_estimated_net_support": (
        "ledger.aggregate_fact.v2:cb4fb0903abe0119a044bbb3",
        "ledger.semantic_fact.v2:1371ba021ea12057a7917bc3",
    ),
    "dft.bus05i.bus05bi.net_support.fy2025.england.total_estimated_net_support": (
        "ledger.aggregate_fact.v2:a12dfcdc0662c8a5e48bf003",
        "ledger.semantic_fact.v2:d6c31dbfd7e23d0a705861ca",
    ),
    "dft.bus05i.bus05bi.net_support.fy2025.england_outside_london."
    "total_estimated_net_support": (
        "ledger.aggregate_fact.v2:7ab0c5007c9a6ad38aaa1468",
        "ledger.semantic_fact.v2:55f8ff103004096b2a950d9f",
    ),
    "dft.bus05i.bus05bi.net_support.fy2025.london.total_estimated_net_support": (
        "ledger.aggregate_fact.v2:d8e40cee2fc723b719ff4680",
        "ledger.semantic_fact.v2:a338ed4747a2538f660d0fff",
    ),
}

LEGACY_BUS05_SOURCE_RELEASE_KEY = "ledger.source_release.v2:21f7bbdcd26157d5d0b65bfb"

LEGACY_BUS05_SOURCE_SERIES_KEYS = {
    "dft.bus05i.bus05ai.fare_receipts.fy2023": (
        "ledger.source_series.v2:689f0930b7ad31dc92324238"
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2024": (
        "ledger.source_series.v2:648a78df7b7055e02caadbdb"
    ),
    "dft.bus05i.bus05ai.fare_receipts.fy2025": (
        "ledger.source_series.v2:dcd1cb4f226766f54fc13529"
    ),
    "dft.bus05i.bus05bi.net_support.fy2023": (
        "ledger.source_series.v2:1494efcfe52e4b386170d251"
    ),
    "dft.bus05i.bus05bi.net_support.fy2024": (
        "ledger.source_series.v2:e4e5a0c3a7bab20538ec93df"
    ),
    "dft.bus05i.bus05bi.net_support.fy2025": (
        "ledger.source_series.v2:2517821a79e8144ebd372c1c"
    ),
}

SURVIVING_BUS05_BSOG_FACT_KEYS = {
    "dft.bus05i.bus05bi.support_components.fy2023.england."
    "bus_service_operators_grant": (
        "ledger.aggregate_fact.v2:912897a280c8279d662e1e5f",
        "ledger.semantic_fact.v2:a4df9df1f725fa6f920e420e",
    ),
    "dft.bus05i.bus05bi.support_components.fy2023.england_outside_london."
    "bus_service_operators_grant": (
        "ledger.aggregate_fact.v2:5e0e0e3df357b26e40069e78",
        "ledger.semantic_fact.v2:e28d7f381e6fe3ece61c4c2e",
    ),
    "dft.bus05i.bus05bi.support_components.fy2023.english_metropolitan_areas."
    "bus_service_operators_grant": (
        "ledger.aggregate_fact.v2:41a523dec28b47dc039afdc7",
        "ledger.semantic_fact.v2:b77d762db9e016046e4ae3e7",
    ),
    "dft.bus05i.bus05bi.support_components.fy2023."
    "english_non_metropolitan_areas.bus_service_operators_grant": (
        "ledger.aggregate_fact.v2:c806498ebf28e5718ec5ef4e",
        "ledger.semantic_fact.v2:3acc382a60e700e63fbf4103",
    ),
    "dft.bus05i.bus05bi.support_components.fy2024.england."
    "bus_service_operators_grant": (
        "ledger.aggregate_fact.v2:61cb62f5a76864b9007701f7",
        "ledger.semantic_fact.v2:01ec07ef9ccf59cefcb0fcc4",
    ),
    "dft.bus05i.bus05bi.support_components.fy2024.england_outside_london."
    "bus_service_operators_grant": (
        "ledger.aggregate_fact.v2:60a3f4e2d46db42110b71fca",
        "ledger.semantic_fact.v2:0f273941b8978aeeaee754be",
    ),
    "dft.bus05i.bus05bi.support_components.fy2024.english_metropolitan_areas."
    "bus_service_operators_grant": (
        "ledger.aggregate_fact.v2:fadf51f7438fbd35dd7828cb",
        "ledger.semantic_fact.v2:64f3e9c5595695b7c457efc7",
    ),
    "dft.bus05i.bus05bi.support_components.fy2024."
    "english_non_metropolitan_areas.bus_service_operators_grant": (
        "ledger.aggregate_fact.v2:0f7655db6bdf56160bbaf68f",
        "ledger.semantic_fact.v2:5eaaf087e9c7fe48e0a597cd",
    ),
    "dft.bus05i.bus05bi.support_components.fy2025.england."
    "bus_service_operators_grant": (
        "ledger.aggregate_fact.v2:46b3743626f4382a99ecf5db",
        "ledger.semantic_fact.v2:679659a46c816a1d1c7908a1",
    ),
    "dft.bus05i.bus05bi.support_components.fy2025.england_outside_london."
    "bus_service_operators_grant": (
        "ledger.aggregate_fact.v2:ecad41cd51caeef445e1a2e1",
        "ledger.semantic_fact.v2:83fd63b303cd7774dc201600",
    ),
    "dft.bus05i.bus05bi.support_components.fy2025.english_metropolitan_areas."
    "bus_service_operators_grant": (
        "ledger.aggregate_fact.v2:520cf7eca036c9e0f531c30f",
        "ledger.semantic_fact.v2:d7560731eb61c6f61ce58d06",
    ),
    "dft.bus05i.bus05bi.support_components.fy2025."
    "english_non_metropolitan_areas.bus_service_operators_grant": (
        "ledger.aggregate_fact.v2:8f8ca87c0e29b6f85beddc12",
        "ledger.semantic_fact.v2:0948700e70bd9234e2e3c06e",
    ),
}

SURVIVING_BUS05_BSOG_SOURCE_SERIES_KEYS = {
    "dft.bus05i.bus05bi.support_components.fy2023": (
        "ledger.source_series.v2:e2457b8eb0639eed5d1d88a9"
    ),
    "dft.bus05i.bus05bi.support_components.fy2024": (
        "ledger.source_series.v2:1da78aed6e202be8ecdf57e9"
    ),
    "dft.bus05i.bus05bi.support_components.fy2025": (
        "ledger.source_series.v2:24be27d8aeb8ce457353b24a"
    ),
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
    dfi_alias = "dfi-ni-bus-concessionary-journeys-2024-25"
    nts_aliases = {
        "dft-nts0303-mode-trips-2025",
        "dft-nts0601-age-mode-trips-2025",
    }

    for alias in ISSUE_274_ARTIFACT_YEARS:
        for fact in _facts(alias):
            period_identity_prefix = "cy" if alias in nts_aliases else "fy"
            period_identity = fact.layout.record_set_id.rsplit(".", 1)[-1]
            assert period_identity[:2] == period_identity_prefix
            publisher_year = period_identity[2:]
            assert len(publisher_year) == 4 and publisher_year.isdecimal()
            year = int(publisher_year)
            assert fact.period.value == year, fact.source_record_id

            if alias == dfi_alias:
                expected = (
                    f"{year}-04-01",
                    f"{year + 1}-03-31",
                    "fiscal",
                    f"{year}-{str(year + 1)[-2:]}",
                )
            elif alias in nts_aliases:
                expected = (
                    f"{year}-01-01",
                    f"{year}-12-31",
                    "survey_reference",
                    str(year),
                )
            else:
                expected = (
                    f"{year - 1}-04-01",
                    f"{year}-03-31",
                    "fiscal",
                    f"Year ending March {year}",
                )

            coverage = fact.period_coverage
            assert coverage is not None
            assert (
                coverage.start_date,
                coverage.end_date,
                coverage.basis,
                coverage.source_period_label,
            ) == expected, fact.source_record_id


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
    alias = "dft-bus01-passenger-journeys-2025"
    package = load_source_package(alias)
    facts = _facts(alias)
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

    other_urban = [
        fact
        for fact in urban_rural
        if fact.geography.id == "dft:other_predominantly_urban_areas"
    ]
    assert {fact.geography.name for fact in other_urban} == {
        "Other predominantly urban areas"
    }
    assert all("[note 2]" not in fact.label for fact in other_urban)

    guarded_rows = [
        row
        for record_set in package.build_source_record_set_specs(2025)
        for row in record_set.rows
        if row.value_id == "other_predominantly_urban_areas"
    ]
    assert {row.label for row in guarded_rows} == {"Other predominantly urban areas"}
    assert {row.expected_column_header for row in guarded_rows} == {
        "Other predominantly urban areas [note 2]"
    }


def test_bus05_carries_each_published_support_component_and_gross_revenue():
    facts = _facts("dft-bus05i-revenue-support-2025")
    component_geographies = {
        "dft.local_bus_net_public_transport_support": {
            "E92000001",
            "E12000007",
            "dft:england_outside_london",
            "dft:english_metropolitan_areas",
            "dft:english_non_metropolitan_areas",
        },
        "dft.local_bus_concessionary_travel_reimbursement": {
            "E92000001",
            "E12000007",
            "dft:england_outside_london",
            "dft:english_metropolitan_areas",
            "dft:english_non_metropolitan_areas",
        },
        "dft.local_bus_gross_public_transport_support": {
            "E92000001",
            "E12000007",
            "dft:england_outside_london",
            "dft:english_metropolitan_areas",
            "dft:english_non_metropolitan_areas",
        },
        "dft.local_bus_bus_service_operators_grant": {
            "E92000001",
            "dft:england_outside_london",
            "dft:english_metropolitan_areas",
            "dft:english_non_metropolitan_areas",
        },
        "dft.local_bus_additional_funding_to_operators": {
            "E92000001",
            "dft:england_outside_london",
        },
        "dft.local_bus_fare_cap": {
            "E92000001",
            "dft:england_outside_london",
        },
    }
    support = [fact for fact in facts if fact.measure.concept in component_geographies]
    gross_revenue = [
        fact
        for fact in facts
        if fact.measure.concept == "dft.local_bus_total_estimated_operating_revenue"
    ]

    assert len(support) == 69
    assert {fact.measure.concept for fact in support} == set(component_geographies)
    assert {fact.period.value for fact in support} == {2023, 2024, 2025}
    assert {
        concept: {
            fact.geography.id for fact in support if fact.measure.concept == concept
        }
        for concept in component_geographies
    } == component_geographies
    assert {
        concept: sum(fact.measure.concept == concept for fact in support)
        for concept in component_geographies
    } == {
        concept: len(geographies) * 3
        for concept, geographies in component_geographies.items()
    }
    assert len(gross_revenue) == 3 * 3
    assert {fact.geography.id for fact in gross_revenue} == {
        "E92000001",
        "E12000007",
        "dft:england_outside_london",
    }

    latest_england = {
        fact.measure.concept: fact.value
        for fact in facts
        if fact.period.value == 2025 and fact.geography.id == "E92000001"
    }
    assert latest_england["dft.local_bus_gross_public_transport_support"] == (
        1_584_976_000
    )
    assert latest_england[
        "dft.local_bus_additional_funding_to_operators"
    ] == pytest.approx(84_539_980.19)
    assert latest_england["dft.local_bus_fare_cap"] == pytest.approx(515_693_216.6)


def test_bus05_published_components_reconcile_to_published_totals():
    facts = _facts("dft-bus05i-revenue-support-2025")
    values = {
        (fact.period.value, fact.geography.id, fact.measure.concept): fact.value
        for fact in facts
    }
    net_components = {
        "dft.local_bus_net_public_transport_support",
        "dft.local_bus_concessionary_travel_reimbursement",
        "dft.local_bus_bus_service_operators_grant",
        "dft.local_bus_additional_funding_to_operators",
        "dft.local_bus_fare_cap",
    }
    gross_components = {
        "dft.local_bus_passenger_fare_receipts",
        "dft.local_bus_gross_public_transport_support",
        "dft.local_bus_concessionary_travel_reimbursement",
        "dft.local_bus_bus_service_operators_grant",
        "dft.local_bus_additional_funding_to_operators",
        "dft.local_bus_fare_cap",
    }

    for fact in facts:
        if fact.measure.concept == "dft.local_bus_total_estimated_net_support":
            components = net_components
        elif fact.measure.concept == "dft.local_bus_total_estimated_operating_revenue":
            components = gross_components
        else:
            continue

        component_sum = sum(
            values.get((fact.period.value, fact.geography.id, concept), 0)
            for concept in components
        )
        assert component_sum == pytest.approx(fact.value), fact.source_record_id


def test_bus05_preserves_pre_issue_274_consumer_identity_keys():
    rows = consumer_fact_rows(_facts("dft-bus05i-revenue-support-2025"))
    legacy_rows = {
        row["lineage"]["source_record_id"]: row
        for row in rows
        if ".fare_receipts." in row["lineage"]["source_record_id"]
        or ".net_support." in row["lineage"]["source_record_id"]
    }

    assert set(legacy_rows) == set(LEGACY_BUS05_FACT_KEYS)
    for source_record_id, (
        aggregate_key,
        semantic_key,
    ) in LEGACY_BUS05_FACT_KEYS.items():
        row = legacy_rows[source_record_id]
        source_series_id = source_record_id.rsplit(".", 2)[0]
        assert (
            row["aggregate_fact_key"],
            row["semantic_fact_key"],
            row["source_release_key"],
            row["source_series_key"],
        ) == (
            aggregate_key,
            semantic_key,
            LEGACY_BUS05_SOURCE_RELEASE_KEY,
            LEGACY_BUS05_SOURCE_SERIES_KEYS[source_series_id],
        )


def test_bus05_preserves_surviving_bsog_consumer_identity_keys():
    rows = consumer_fact_rows(_facts("dft-bus05i-revenue-support-2025"))
    bsog_rows = {
        row["lineage"]["source_record_id"]: row
        for row in rows
        if row["observed_measure"]["source_concept"]
        == "dft.local_bus_bus_service_operators_grant"
    }

    assert set(bsog_rows) == set(SURVIVING_BUS05_BSOG_FACT_KEYS)
    for source_record_id, (
        aggregate_key,
        semantic_key,
    ) in SURVIVING_BUS05_BSOG_FACT_KEYS.items():
        row = bsog_rows[source_record_id]
        source_series_id = source_record_id.rsplit(".", 2)[0]
        assert (
            row["aggregate_fact_key"],
            row["semantic_fact_key"],
            row["source_release_key"],
            row["source_series_key"],
        ) == (
            aggregate_key,
            semantic_key,
            LEGACY_BUS05_SOURCE_RELEASE_KEY,
            SURVIVING_BUS05_BSOG_SOURCE_SERIES_KEYS[source_series_id],
        )


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
    alias = "dfi-ni-bus-concessionary-journeys-2024-25"
    package = load_source_package(alias)
    facts = _facts(alias)
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
    values = {fact.period.value: fact.value for fact in concession}
    assert values == {
        2019: 10_855_000,
        2020: 3_500_000,
        2021: 6_179_000,
        2022: 7_824_000,
        2023: 8_642_000,
        2024: 8_960_000,
    }
    assert all(type(value) is int for value in values.values())

    round_to_by_record_set = {
        record_set.record_set_id: record_set.measures[0].round_to
        for record_set in package.build_source_record_set_specs(2025)
    }
    assert round_to_by_record_set == {
        "dfi_ni.public_transport.figure_6.fy2019": None,
        "dfi_ni.public_transport.figure_6.fy2020": None,
        "dfi_ni.public_transport.figure_6.fy2021": 1,
        "dfi_ni.public_transport.figure_6.fy2022": None,
        "dfi_ni.public_transport.figure_6.fy2023": None,
        "dfi_ni.public_transport.figure_6.fy2024": None,
    }

    fy2021 = next(fact for fact in concession if fact.period.value == 2021)
    fy2021_row = consumer_fact_rows([fy2021])[0]
    assert (
        fy2021_row["lineage"]["source_record_id"],
        fy2021_row["legacy_fact_key"],
        fy2021_row["aggregate_fact_key"],
        fy2021_row["semantic_fact_key"],
        fy2021_row["source_release_key"],
        fy2021_row["source_series_key"],
    ) == (
        "dfi_ni.public_transport.figure_6.fy2021.full_fare_concession."
        "passenger_journeys",
        "ledger.fact.v1:a4cd7fd8346c485e9519518c",
        "ledger.aggregate_fact.v2:b957e464f7b52b76cd3d2aad",
        "ledger.semantic_fact.v2:953236ab76764c187a659764",
        "ledger.source_release.v2:d9a319cf282ce4cd26a6d9d7",
        "ledger.source_series.v2:4fa313f3861bf251df4377f9",
    )

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
