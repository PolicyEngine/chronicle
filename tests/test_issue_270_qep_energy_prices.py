"""Regression coverage for the QEP portion of issue 270."""

from __future__ import annotations

from pathlib import Path

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


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
QEP_PACKAGES = {
    "desnz-qep-electricity-annual-bills-2026": (
        REPOSITORY_ROOT / "packages/desnz/qep_electricity_annual_bills_2026",
        72,
    ),
    "desnz-qep-electricity-unit-fixed-costs-2026": (
        REPOSITORY_ROOT / "packages/desnz/qep_electricity_unit_fixed_costs_2026",
        768,
    ),
    "desnz-qep-gas-annual-bills-2026": (
        REPOSITORY_ROOT / "packages/desnz/qep_gas_annual_bills_2026",
        72,
    ),
    "desnz-qep-gas-unit-fixed-costs-2026": (
        REPOSITORY_ROOT / "packages/desnz/qep_gas_unit_fixed_costs_2026",
        720,
    ),
}


def _facts(package_id: str):
    package_path, _ = QEP_PACKAGES[package_id]
    return load_source_package(package_path).build_facts(2026)


def test_qep_packages_are_registered_in_the_uk_bundle():
    package_ids = set(QEP_PACKAGES)

    assert package_ids <= set(SOURCE_PACKAGE_ALIASES)
    assert package_ids <= set(UK_BUNDLE_SOURCES)


@pytest.mark.parametrize(
    ("package_id", "package_path", "expected_fact_count"),
    [
        (package_id, package_path, expected_fact_count)
        for package_id, (package_path, expected_fact_count) in QEP_PACKAGES.items()
    ],
)
def test_qep_packages_preserve_source_cells_and_build_valid_facts(
    package_id: str,
    package_path: Path,
    expected_fact_count: int,
):
    package = load_source_package(package_path)
    report = validate_source_package(package_path, year=2026)
    cells = package.build_source_cells(2026)
    facts = package.build_facts(2026, cells=cells)

    assert package.package_id == package_id
    assert report.valid, report.to_dict()
    assert cells
    assert len(facts) == expected_fact_count
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert all(fact.source.raw_r2_uri for fact in facts)


@pytest.mark.parametrize("package_id", QEP_PACKAGES)
def test_qep_facts_use_only_the_published_annual_grains(package_id: str):
    facts = _facts(package_id)

    # QEP publishes these values for calendar and financial years. It does not
    # publish quarterly bill, unit-cost, or fixed-cost observations.
    assert {fact.period.type for fact in facts} == {
        "calendar_year",
        "fiscal_year",
    }
    assert {fact.period.value for fact in facts} == {2023, 2024, 2025}
    assert all(fact.period_coverage is not None for fact in facts)
    assert all(fact.period_coverage.start_date for fact in facts)
    assert all(fact.period_coverage.end_date for fact in facts)


def test_qep_annual_bill_filters_preserve_tariff_and_consumption_basis():
    electricity = _facts("desnz-qep-electricity-annual-bills-2026")
    gas = _facts("desnz-qep-gas-annual-bills-2026")

    for facts, consumption in ((electricity, 3_400), (gas, 11_200)):
        assert {fact.filters["payment_method"] for fact in facts} == {
            "standard_credit",
            "direct_debit",
            "prepayment",
            "all",
        }
        assert {fact.filters["tariff_type"] for fact in facts} == {
            "fixed",
            "variable",
            "all",
        }
        assert {fact.filters["benchmark_consumption_kwh"] for fact in facts} == {
            consumption
        }
        assert {fact.filters["vat_treatment"] for fact in facts} == {"including_vat"}
        assert {fact.measure.unit for fact in facts} == {"gbp_per_year"}
        assert {fact.aggregation.method for fact in facts} == {"mean"}


def test_qep_regional_costs_cover_every_publisher_price_scope():
    electricity = _facts("desnz-qep-electricity-unit-fixed-costs-2026")
    gas = _facts("desnz-qep-gas-unit-fixed-costs-2026")

    assert len({fact.geography.id for fact in electricity}) == 16
    assert len({fact.geography.id for fact in gas}) == 15
    assert "N92000002" in {fact.geography.id for fact in electricity}
    assert "N92000002" not in {fact.geography.id for fact in gas}
    assert "K02000001" in {fact.geography.id for fact in electricity}
    assert "K02000001" in {fact.geography.id for fact in gas}

    for facts in (electricity, gas):
        assert {fact.filters["payment_method"] for fact in facts} == {
            "standard_credit",
            "direct_debit",
            "prepayment",
            "all",
        }
        assert {fact.filters["price_component"] for fact in facts} == {
            "variable_unit_cost",
            "fixed_cost",
        }
        assert {fact.measure.unit for fact in facts} == {
            "gbp_per_kwh",
            "gbp_per_year",
        }


def test_qep_cost_components_do_not_embed_a_bill_consumption_assumption():
    facts = [
        *_facts("desnz-qep-electricity-unit-fixed-costs-2026"),
        *_facts("desnz-qep-gas-unit-fixed-costs-2026"),
    ]

    # DESNZ publishes unit and fixed costs independently of consumption. The
    # annual-bill packages carry the publisher's benchmark assumptions.
    assert all("benchmark_consumption_kwh" not in fact.filters for fact in facts)


def test_qep_published_cost_components_reconstruct_the_published_annual_bills():
    electricity_bills = _facts("desnz-qep-electricity-annual-bills-2026")
    electricity_costs = _facts("desnz-qep-electricity-unit-fixed-costs-2026")
    gas_bills = _facts("desnz-qep-gas-annual-bills-2026")
    gas_costs = _facts("desnz-qep-gas-unit-fixed-costs-2026")

    for bills, costs, consumption in (
        (electricity_bills, electricity_costs, 3_400),
        (gas_bills, gas_costs, 11_200),
    ):
        bill = next(
            fact
            for fact in bills
            if fact.period.type == "calendar_year"
            and fact.period.value == 2025
            and fact.filters["payment_method"] == "direct_debit"
            and fact.filters["tariff_type"] == "all"
        )
        components = {
            fact.filters["price_component"]: fact.value
            for fact in costs
            if fact.period.type == "calendar_year"
            and fact.period.value == 2025
            and fact.geography.id == "K02000001"
            and fact.filters["payment_method"] == "direct_debit"
        }

        reconstructed_bill = (
            components["variable_unit_cost"] * consumption + components["fixed_cost"]
        )
        assert reconstructed_bill == pytest.approx(bill.value)


def test_qep_packages_preserve_representative_publisher_values():
    expected = {
        "desnz-qep-electricity-annual-bills-2026": (
            "desnz.qep.table_2_2_1.cy2025.united_kingdom.direct_debit_variable_bill",
            1093.0524856031825,
        ),
        "desnz-qep-electricity-unit-fixed-costs-2026": (
            "desnz.qep.table_2_2_4.cy2025.london.direct_debit_variable_unit_cost",
            0.25501437131401583,
        ),
        "desnz-qep-gas-annual-bills-2026": (
            "desnz.qep.table_2_3_1.cy2025.united_kingdom.direct_debit_all_bill",
            823.353444031362,
        ),
        "desnz-qep-gas-unit-fixed-costs-2026": (
            "desnz.qep.table_2_3_4.fy2025.united_kingdom.overall_fixed_cost",
            118.34765518517737,
        ),
    }

    for package_id, (source_record_id, expected_value) in expected.items():
        facts = {fact.source_record_id: fact for fact in _facts(package_id)}
        assert facts[source_record_id].value == pytest.approx(expected_value)
