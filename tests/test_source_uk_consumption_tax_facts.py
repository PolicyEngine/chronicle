"""Publisher coverage and semantics for PolicyEngine/chronicle#322."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from chronicle.bundle import UK_BUNDLE_SOURCES, build_bundle
from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.dimension_labels import dimension_label_issues
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package
from chronicle.sources.cells import build_source_cell_key, validate_source_cells

ONS = "ons-consumer-trends-current-price-2026"
ROAD_FUEL = "desnz-road-transport-fuel-consumption-2024"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ons_data():
    package = load_source_package(ONS)
    cells = package.build_source_cells(2026)
    return cells, package.build_facts(2026, cells=cells)


@pytest.fixture(scope="module")
def road_fuel_data():
    package = load_source_package(ROAD_FUEL)
    cells = package.build_source_cells(2026)
    return cells, package.build_facts(2026, cells=cells)


def test_road_fuel_is_registered_in_the_uk_bundle():
    assert ROAD_FUEL in SOURCE_PACKAGE_ALIASES
    assert ROAD_FUEL in UK_BUNDLE_SOURCES


@pytest.mark.parametrize(
    ("fixture", "lineage_count"), [("ons_data", 3), ("road_fuel_data", 4)]
)
def test_consumption_facts_preserve_lineage_and_consumer_contract(
    request, fixture, lineage_count
):
    cells, facts = request.getfixturevalue(fixture)
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    keys = {build_source_cell_key(cell) for cell in cells}
    assert all(set(fact.source_cell_keys) <= keys for fact in facts)
    # Value cells and publisher classification guards all remain in lineage.
    assert all(len(fact.source_cell_keys) == lineage_count for fact in facts)
    assert {fact.assertion for fact in facts} == {"observation"}


def test_ons_uses_the_existing_preserved_vintage(ons_data):
    path = ROOT / "db/data/ons/consumer_trends_current_price_2026/cpnsa.xlsx"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "109e53de0c09d30327ae2053a0487cee159fe44135884707c9000c252438143c"
    )
    # 166 columns across 0CN and 01CN-12CN, in 31 periods, plus three
    # annual TOURCN series in six years. Published [x] cells remain facts.
    assert len(ons_data[1]) == 166 * 31 + 3 * 6
    assert {fact.source.vintage for fact in ons_data[1]} == {
        "2026_06_30_release_2026_q1"
    }
    assert {fact.source.extracted_at for fact in ons_data[1]} == {"2026-09-09"}


def test_ons_coicop_identifiers_and_constraints_are_strings(ons_data):
    for fact in ons_data[1]:
        assert isinstance(fact.filters["coicop"], str)
        coicop_constraints = [
            constraint
            for constraint in fact.constraints
            if constraint.variable == "coicop"
        ]
        assert coicop_constraints
        assert all(
            isinstance(constraint.value, str)
            and constraint.value == fact.filters["coicop"]
            for constraint in coicop_constraints
        )


def test_ons_entity_roles_match_consumption_concepts_across_all_series(ons_data):
    roles = {}
    for fact in ons_data[1]:
        roles.setdefault(fact.filters["consumption_concept"], set()).add(
            fact.entity.role
        )
    assert roles == {
        "domestic": {"households_on_uk_territory"},
        "national": {"resident_households"},
        "national_adjustment": {"household_tourism_adjustment"},
    }


def test_ons_divisions_and_vat_bridge_classes_cover_every_period(ons_data):
    facts = ons_data[1]
    required = {
        "02.3",
        "04.1",
        "04.2",
        "04.2.1",
        "04.2.2",
        "04.3",
        "04.4",
        "06.1",
        "06.2",
        "06.3",
        "07.1",
        "07.2.1",
        "07.2.3",
        "07.3",
        "10",
        "11.1",
        "11.2",
        "12.5",
        "12.6",
        "12.6.1",
    }
    periods = {
        *(("calendar_year", year) for year in range(2020, 2026)),
        *(
            ("quarter", f"{year}-Q{quarter}")
            for year in range(2020, 2026)
            for quarter in range(1, 5)
        ),
        ("quarter", "2026-Q1"),
    }
    for coicop in required:
        assert {
            (fact.period.type, fact.period.value)
            for fact in facts
            if fact.filters["coicop"] == coicop
        } == periods
    overview = [fact for fact in facts if fact.filters["source_sheet"] == "0CN"]
    assert {fact.filters["coicop"] for fact in overview} == {
        "NAT0",
        "TOUR",
        "0",
        *(f"{division:02}" for division in range(1, 13)),
    }
    for code in {"NAT0", "TOUR", "0", *(f"{i:02}" for i in range(1, 13))}:
        assert len([fact for fact in overview if fact.filters["coicop"] == code]) == 31


def test_ons_national_domestic_and_signed_tourism_are_distinct(ons_data):
    annual = {
        (fact.filters["source_sheet"], fact.filters["coicop"]): fact
        for fact in ons_data[1]
        if fact.period.type == "calendar_year" and fact.period.value == 2024
    }
    # 0CN B36 and D36; TOURCN C36 and D36, £ million as published.
    assert annual["0CN", "NAT0"].value == 1_699_387_000_000
    assert annual["0CN", "NAT0"].filters["consumption_concept"] == "national"
    assert annual["0CN", "0"].value == 1_685_220_000_000
    assert annual["0CN", "0"].filters["consumption_concept"] == "domestic"
    assert annual["TOURCN", "TOUR1"].value == -64_709_000_000
    assert annual["TOURCN", "TOUR1"].filters["tourism_flow"] == (
        "non_residents_spending_in_uk"
    )
    assert annual["TOURCN", "TOUR2"].value == 78_876_000_000
    assert annual["TOURCN", "TOUR2"].filters["tourism_flow"] == (
        "residents_spending_abroad"
    )
    tourism = [fact for fact in ons_data[1] if fact.filters["source_sheet"] == "TOURCN"]
    assert {fact.period.type for fact in tourism} == {"calendar_year"}
    assert all(fact.filters["price_basis"] == "current_prices" for fact in ons_data[1])
    assert all(
        fact.filters["seasonal_adjustment"] == "not_seasonally_adjusted"
        for fact in ons_data[1]
    )
    assert all(fact.filters["published_unit"] == "gbp_million" for fact in ons_data[1])


def test_ons_unavailable_cells_keep_published_markers_and_addresses(ons_data):
    cells, facts = ons_data
    by_key = {build_source_cell_key(cell): cell for cell in cells}
    marked = [fact for fact in facts if fact.value == "[x]"]
    assert len(marked) == 3 * 31
    assert {fact.filters["coicop"] for fact in marked} == {"04.4.4", "04.5.5", "09.6"}
    assert all(fact.filters["publication_status"] == "not_available" for fact in marked)
    for fact in marked:
        value_cells = [
            by_key[key]
            for key in fact.source_cell_keys
            if by_key[key].raw_value == "[x]"
        ]
        assert len(value_cells) == 1
        if fact.period.type == "calendar_year" and fact.period.value == 2024:
            assert (
                value_cells[0].address
                == {
                    "04.4.4": "P36",
                    "04.5.5": "V36",
                    "09.6": "AB36",
                }[fact.filters["coicop"]]
            )


def test_ons_legacy_energy_fact_identity_and_value_are_preserved(ons_data):
    facts = {fact.source_record_id: fact for fact in ons_data[1]}
    fact = facts["ons.consumer_trends.04cn.cy2020.coicop_04_5.expenditure"]
    assert fact.value == 31_805_000_000
    assert (
        fact.measure.concept == "ons.household_expenditure.electricity_gas_other_fuels"
    )


def test_road_fuel_covers_all_years_published_totals_and_vehicle_fuel_pairs(
    road_fuel_data,
):
    facts = road_fuel_data[1]
    assert {fact.period.type for fact in facts} == {"calendar_year"}
    assert {fact.period.value for fact in facts} == set(range(2005, 2025))
    assert {fact.measure.unit for fact in facts} == {"ktoe"}
    expected_pairs = {
        ("cars", "petrol"),
        ("cars", "diesel"),
        ("motorcycles", "petrol"),
        ("buses_and_coaches", "diesel"),
        ("lgv", "petrol"),
        ("lgv", "diesel"),
        ("hgv", "diesel"),
        ("hgv", "natural_gas"),
        ("lgv", "lpg"),
        ("all_vehicles", "all_fuels"),
    }
    assert {
        (fact.filters["vehicle_type"], fact.filters["fuel"]) for fact in facts
    } == expected_pairs
    # Fifteen coded country/region totals, plus the publisher's England row.
    assert len(facts) == 20 * 16 * len(expected_pairs)
    for year in range(2005, 2025):
        yearly = [fact for fact in facts if fact.period.value == year]
        assert {fact.geography.id for fact in yearly} >= {
            "K02000001",
            "K03000001",
            "E92000001",
        }
        assert len({fact.geography.id for fact in yearly}) == 16
        assert {fact.geography.level for fact in yearly} == {"country", "region"}
        assert all(
            fact.period_coverage.start_date == f"{year}-01-01" for fact in yearly
        )
        assert all(fact.period_coverage.end_date == f"{year}-12-31" for fact in yearly)


def test_road_fuel_retains_publisher_car_values_without_litre_conversion(
    road_fuel_data,
):
    cells, facts = road_fuel_data
    by_key = {build_source_cell_key(cell): cell for cell in cells}
    uk_cars = {
        fact.filters["fuel"]: fact
        for fact in facts
        if fact.period.value == 2024
        and fact.geography.id == "K02000001"
        and fact.filters["vehicle_type"] == "cars"
    }
    # 2024 sheet O384 and K384, not HMRC clearances × an OBR cars share.
    assert uk_cars["petrol"].value == pytest.approx(14605.695206681678)
    assert uk_cars["diesel"].value == pytest.approx(9571.883358666924)
    for fuel, column in [("petrol", "O"), ("diesel", "K")]:
        lineage = {
            by_key[key].address: by_key[key] for key in uk_cars[fuel].source_cell_keys
        }
        assert set(lineage) == {f"{column}384", f"{column}4", "C384", "A1"}
        assert lineage[f"{column}384"].raw_value == uk_cars[fuel].value


def test_road_fuel_distinguishes_london_subregions_from_english_regions(road_fuel_data):
    facts = [fact for fact in road_fuel_data[1] if fact.period.value == 2024]
    regions = {
        fact.geography.id
        for fact in facts
        if fact.filters["geography_kind"] == "english_region"
    }
    london = {
        fact.geography.id
        for fact in facts
        if fact.filters["geography_kind"] == "london_subregion"
    }
    assert len(regions) == 8
    assert all(code.startswith("E12") for code in regions)
    assert london == {"E13000001", "E13000002"}
    assert all(
        fact.geography.level == "region"
        for fact in facts
        if fact.geography.id in regions | london
    )


@pytest.mark.parametrize(
    "relative_path", ["manifest.yaml", "methodology/manifest.yaml"]
)
def test_road_fuel_raw_artifacts_have_content_addressed_r2_provenance(relative_path):
    path = ROOT / "db/data/desnz/road_transport_fuel_consumption_2024" / relative_path
    artifact = yaml.safe_load(path.read_text())["files"][2026]
    storage = artifact["storage"]["r2"]
    assert storage["provider"] == "r2"
    assert storage["bucket"] == "ledger-raw"
    assert storage["key"].startswith("raw/uk/desnz/")
    assert storage["key"].endswith(f"/{artifact['sha256']}/{artifact['filename']}")
    assert storage["uri"] == f"r2://ledger-raw/{storage['key']}"


def test_road_fuel_exposes_travel_scope_and_methodology(road_fuel_data):
    facts = road_fuel_data[1]
    assert all(
        fact.filters["population_scope"] == "vehicles_travelling_in_area"
        for fact in facts
    )
    assert all(
        fact.filters["electric_vehicle_treatment"] == "excluded" for fact in facts
    )
    assert all(
        fact.filters["estimate_basis"]
        == "spatial_estimates_without_dukes_normalisation"
        for fact in facts
    )
    assert all(
        fact.filters["national_inventory_basis"]
        == "normalised_to_adjusted_dukes_fuel_sales"
        for fact in facts
    )
    assert all(
        fact.filters["biofuel_treatment"] == "includes_blended_biofuels"
        for fact in facts
        if fact.filters["fuel"] in {"petrol", "diesel", "all_fuels"}
    )
    assert {fact.entity.name for fact in facts} == {"institutional_sector"}
    assert {fact.entity.role for fact in facts} == {"road_transport"}
    # The tables and accompanying methodology publish no factors converting
    # ktoe into litres or tonnes: consumers must supply those separately.
    assert not any("conversion_factor" in fact.measure.concept for fact in facts)


@pytest.mark.parametrize("fixture", ["ons_data", "road_fuel_data"])
def test_consumption_facts_have_complete_bundle_dimension_labels(request, fixture):
    _, facts = request.getfixturevalue(fixture)
    issues = dimension_label_issues(consumer_fact_rows(facts))
    # The ONS overview and detailed sheets sometimes word the same division
    # differently. Keep that publisher wording as a warning, as bundles do.
    errors = [
        issue for issue in issues if issue.code != "conflicting_groupby_value_label"
    ]
    assert not errors, [issue.to_dict() for issue in errors]


def test_consumption_sources_build_a_valid_merged_bundle(tmp_path):
    report = build_bundle(tmp_path / "consumption", year=2023, sources=[ONS, ROAD_FUEL])
    assert report.valid, report.to_dict()["errors"]
    assert report.coverage["fact_count"] == 8364
    assert len(report.source_packages) == 2
    assert report.coverage["counts"]["by_source"] == {"ons": 5164, "desnz": 3200}
    assert len(report.coverage["counts"]["by_geography"]) == 16
    assert len(report.coverage["counts"]["by_period"]) == 46
    assert not report.coverage["duplicates"]["aggregate_fact_keys"]
