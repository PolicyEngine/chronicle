"""Regression coverage for issue 270 Census central-heating facts."""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path

import pytest
import yaml

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import validate_consumer_fact_contract
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources.cells import build_source_cell_key, validate_source_cells
from chronicle.sources.rows import build_source_row_key, validate_source_rows


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

ONS_CATEGORIES = {
    "does_not_apply": "Does not apply",
    "no_central_heating": "No central heating",
    "mains_gas_only": "Mains gas only",
    "tank_or_bottled_gas_only": "Tank or bottled gas only",
    "electric_only": "Electric only",
    "oil_only": "Oil only",
    "wood_only": "Wood only",
    "solid_fuel_only": "Solid fuel only",
    "renewable_energy_only": "Renewable energy only",
    "district_or_communal_heat_networks_only": (
        "District or communal heat networks only"
    ),
    "other_central_heating_only": "Other central heating only",
    "two_or_more_types_excluding_renewable": (
        "Two or more types of central heating (not including renewable energy)"
    ),
    "two_or_more_types_including_renewable": (
        "Two or more types of central heating (including renewable energy)"
    ),
}

NRS_CATEGORIES = {
    "all_occupied_households": "All occupied households",
    "no_central_heating": "No central heating",
    "gas_central_heating_total": "Gas central heating: Total",
    "mains_gas": "Gas central heating: Mains gas",
    "other_gas": (
        "Gas central heating: Other gas (including liquid petroleum gas and biogas)"
    ),
    "electric": "Electric (including storage heaters) central heating",
    "oil": "Oil central heating",
    "solid_fuel": "Solid Fuel (excluding wood)",
    "wood_or_biomass": (
        "Wood or Biomass (including logs, pellets, chippings) central heating"
    ),
    "other_renewable": (
        "Other renewable energy source (including electric and air heat pump systems)"
    ),
    "district_or_communal_heat": "District or communal heat system",
    "other_central_heating": "Other central heating",
    "two_or_more_types": "Two or more types of central heating",
}

CENSUS_PACKAGES = {
    "ons-census2021-ts046-central-heating-ltla": {
        "path": Path("packages/ons/census2021_ts046_central_heating_ltla"),
        "data_path": Path("db/data/ons/census2021_ts046_central_heating_ltla"),
        "year": 2021,
        "fact_count": 4_303,
        "geography_count": 331,
        "geography_prefix": ("E", "W"),
        "geography_vintage": "census_2021_ltla",
        "date": "2021-03-21",
        "source_id": "ons",
        "filename": "ons-ts046-version-4.csv",
        "source_url": (
            "https://download.ons.gov.uk/downloads/datasets/TS046/editions/2021/"
            "versions/4.csv"
        ),
        "sha256": ("572c007288266f73b09f640be87feef2d641413a8a749f90cb2b64294dc62354"),
        "size_bytes": 237_221,
        "categories": ONS_CATEGORIES,
    },
    "nrs-census2022-uv407-central-heating-council-area": {
        "path": Path("packages/nrs/census2022_uv407_central_heating_council_area"),
        "data_path": Path("db/data/nrs/census2022_uv407_central_heating_council_area"),
        "year": 2022,
        "fact_count": 416,
        "geography_count": 32,
        "geography_prefix": ("S",),
        "geography_vintage": "ca_2019",
        "date": "2022-03-20",
        "source_id": "nrs",
        "filename": "nrs-uv407-central-heating-local-authority.csv",
        "source_url": (
            "https://ukds-ckan.s3.eu-west-1.amazonaws.com/2022/NRS/UV407/"
            "Census_2022_UV407_Central_heating_Local_authority.csv"
        ),
        "sha256": ("e878c7d3628f6bf2094e313bc19d4bee0a8c9bbe8d4e6ca4162ba32eda1bda8d"),
        "size_bytes": 32_748,
        "categories": NRS_CATEGORIES,
    },
}


@pytest.fixture(scope="module", params=sorted(CENSUS_PACKAGES))
def census_package(request):
    alias = request.param
    config = CENSUS_PACKAGES[alias]
    package = load_source_package(alias)
    source_rows = package.build_source_rows(config["year"])
    cells = package.build_source_cells(config["year"], source_rows=source_rows)
    facts = package.build_facts(
        config["year"],
        cells=cells,
        source_rows=source_rows,
    )
    return alias, config, package, source_rows, cells, facts


def test_census_heating_packages_are_registered_for_the_uk_bundle():
    aliases = set(CENSUS_PACKAGES)

    assert aliases <= set(SOURCE_PACKAGE_ALIASES)
    assert aliases <= set(UK_BUNDLE_SOURCES)


@pytest.mark.parametrize("alias", sorted(CENSUS_PACKAGES))
def test_census_heating_raw_artifacts_match_their_manifests(alias):
    config = CENSUS_PACKAGES[alias]
    directory = REPOSITORY_ROOT / config["data_path"]
    manifest = yaml.safe_load((directory / "manifest.yaml").read_text())
    artifact = manifest["files"][config["year"]]
    payload = directory.joinpath(config["filename"]).read_bytes()

    assert manifest["source_id"] == config["source_id"]
    assert manifest["package_id"] == alias
    assert artifact["filename"] == config["filename"]
    assert artifact["source_url"] == config["source_url"]
    assert artifact["sha256"] == config["sha256"]
    assert artifact["size_bytes"] == config["size_bytes"]
    assert len(payload) == config["size_bytes"]
    assert hashlib.sha256(payload).hexdigest() == config["sha256"]

    expected_key = (
        f"raw/uk/{config['source_id']}/{alias}/{config['year']}/"
        f"{config['sha256']}/{config['filename']}"
    )
    assert artifact["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": expected_key,
        "uri": f"r2://ledger-raw/{expected_key}",
    }


def test_census_heating_packages_build_valid_fully_lineaged_facts(census_package):
    _, config, package, source_rows, cells, facts = census_package
    report = validate_source_package(package.package_path, year=config["year"])
    source_cell_keys = {build_source_cell_key(cell) for cell in cells}
    source_row_keys = {build_source_row_key(row) for row in source_rows}

    assert report.valid, report.to_dict()
    assert len(facts) == config["fact_count"]
    assert validate_source_rows(source_rows).valid
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert all(fact.source_record_id for fact in facts)
    assert all(fact.source_cell_keys for fact in facts)
    assert all(fact.source_row_keys for fact in facts)
    assert all(set(fact.source_cell_keys) <= source_cell_keys for fact in facts)
    assert all(set(fact.source_row_keys) <= source_row_keys for fact in facts)
    assert {fact.source.source_sha256 for fact in facts} == {config["sha256"]}
    assert {fact.source.source_size_bytes for fact in facts} == {config["size_bytes"]}
    assert all(fact.source.raw_r2_uri for fact in facts)


def test_census_heating_categories_are_preserved_in_source_rows(census_package):
    _, config, package, _, _, facts = census_package
    expected_categories = set(config["categories"])
    record_sets = package.build_source_record_set_specs(config["year"])

    assert package.dimension_value_labels["heating_type"] == config["categories"]
    assert {fact.filters["heating_type"] for fact in facts} == expected_categories
    assert {
        record_set.shared_filters["heating_type"] for record_set in record_sets
    } == (expected_categories)
    for record_set in record_sets:
        category = record_set.shared_filters["heating_type"]
        assert {
            row.source_row_dimensions["heating_type"] for row in record_set.rows
        } == {category}


def test_census_heating_facts_cover_each_publisher_geography(census_package):
    _, config, _, _, _, facts = census_package
    expected_categories = set(config["categories"])
    geography_ids = {fact.geography.id for fact in facts}

    assert len(geography_ids) == config["geography_count"]
    assert all(
        geography_id.startswith(config["geography_prefix"])
        for geography_id in geography_ids
    )
    assert {fact.geography.level for fact in facts} == {"local_authority"}
    assert {fact.geography.vintage for fact in facts} == {config["geography_vintage"]}
    assert Counter(fact.filters["heating_type"] for fact in facts) == {
        category: config["geography_count"] for category in expected_categories
    }


def test_census_heating_facts_use_the_exact_census_day(census_package):
    _, config, _, _, _, facts = census_package

    assert {fact.period.type for fact in facts} == {"calendar_year"}
    assert {fact.period.value for fact in facts} == {config["year"]}
    assert {fact.period_coverage.start_date for fact in facts} == {config["date"]}
    assert {fact.period_coverage.end_date for fact in facts} == {config["date"]}
    assert {fact.period_coverage.basis for fact in facts} == {"survey_reference"}
    assert all(
        "Census day" in fact.period_coverage.source_period_label for fact in facts
    )


def test_census_heating_preserves_representative_publisher_values():
    ons = {
        fact.source_record_id: fact
        for fact in load_source_package(
            "ons-census2021-ts046-central-heating-ltla"
        ).build_facts(2021)
    }
    nrs = {
        fact.source_record_id: fact
        for fact in load_source_package(
            "nrs-census2022-uv407-central-heating-council-area"
        ).build_facts(2022)
    }

    assert (
        ons["ons.census2021.ts046.mains_gas_only.e06000001.households"].value == 33_664
    )
    assert (
        nrs["nrs.census2022.uv407.all_occupied_households.s12000005.households"].value
        == 24_072
    )
    assert (
        nrs["nrs.census2022.uv407.gas_central_heating_total.s12000005.households"].value
        == 20_746
    )
    assert nrs["nrs.census2022.uv407.mains_gas.s12000005.households"].value == 20_488
    assert nrs["nrs.census2022.uv407.other_gas.s12000005.households"].value == 255


def test_census_heating_does_not_fabricate_connection_shares(census_package):
    _, _, _, _, _, facts = census_package

    assert {fact.measure.unit for fact in facts} == {"count"}
    assert {fact.aggregation.method for fact in facts} == {"sum"}
    assert all(set(fact.filters) == {"heating_type"} for fact in facts)
    assert all(
        not any(
            token in fact.measure.concept.lower()
            for token in ("share", "percent", "percentage", "connection_rate")
        )
        for fact in facts
    )
