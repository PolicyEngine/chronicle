"""Regression coverage for the bounded NEED and ONS work in issue 270."""

from __future__ import annotations

from pathlib import Path

import pytest

from chronicle.consumer_contract import validate_consumer_fact_contract
from chronicle.core import validate_facts
from chronicle.source_package import load_source_package, validate_source_package
from chronicle.sources.cells import build_source_cell_key, validate_source_cells


NEED_2024_PACKAGES = {
    Path("packages/desnz/need_england_wales_2024"): 144,
    Path("packages/desnz/need_scotland_2024"): 84,
}

ONS_PACKAGE = Path("packages/ons/consumer_trends_current_price_2026")

ONS_ENERGY_COICOPS = {
    "04.5",
    "04.5.1",
    "04.5.2",
    "04.5.3",
    "04.5.4",
}


@pytest.mark.parametrize(
    ("package_path", "expected_count"),
    sorted(NEED_2024_PACKAGES.items(), key=lambda item: str(item[0])),
)
def test_need_2024_packages_build_valid_consumer_facts(package_path, expected_count):
    package = load_source_package(package_path)
    report = validate_source_package(package_path, year=2024)
    cells = package.build_source_cells(2024)
    facts = package.build_facts(2024, cells=cells)

    assert report.valid, report.to_dict()
    assert cells
    assert len(facts) == expected_count
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid


@pytest.mark.parametrize(
    ("new_path", "old_path"),
    (
        (
            Path("packages/desnz/need_england_wales_2024"),
            Path("packages/desnz/need_england_wales_2023"),
        ),
        (
            Path("packages/desnz/need_scotland_2024"),
            Path("packages/desnz/need_scotland_2023"),
        ),
    ),
)
def test_need_2024_preserves_the_2023_headline_table_scope(new_path, old_path):
    new_facts = load_source_package(new_path).build_facts(2024)
    old_facts = load_source_package(old_path).build_facts(2023)

    def scope(fact):
        return (
            fact.measure.concept,
            fact.measure.unit,
            fact.aggregation.method,
            fact.layout.groupby_dimension,
            fact.layout.groupby_value_id,
            tuple(sorted(fact.filters.items())),
        )

    assert {scope(fact) for fact in new_facts} == {scope(fact) for fact in old_facts}
    assert {fact.period.value for fact in new_facts} == {2024}


@pytest.mark.parametrize(
    ("package_path", "source_record_id", "expected_value"),
    (
        (
            Path("packages/desnz/need_england_wales_2024"),
            "desnz.need_2024.table_5.property_type.detached.detached.mean_consumption",
            15_295.81350122108,
        ),
        (
            Path("packages/desnz/need_scotland_2024"),
            "desnz.need_2024.table_3.property_type.detached.detached.mean_consumption",
            16_615.4520685985,
        ),
    ),
)
def test_need_2024_preserves_representative_publisher_values(
    package_path, source_record_id, expected_value
):
    facts = {
        fact.source_record_id: fact
        for fact in load_source_package(package_path).build_facts(2024)
    }

    assert facts[source_record_id].value == pytest.approx(expected_value)


def test_ons_consumer_trends_adds_each_energy_subclass_for_every_period():
    facts = load_source_package(ONS_PACKAGE).build_facts(2026)
    energy = [fact for fact in facts if ".04cn" in fact.layout.record_set_id]
    expected_annual_periods = set(range(2020, 2026))
    expected_quarterly_periods = {
        *(
            f"{year}-Q{quarter}"
            for year in range(2020, 2026)
            for quarter in range(1, 5)
        ),
        "2026-Q1",
    }

    assert len(facts) == 217
    assert {fact.filters["coicop"] for fact in energy} == ONS_ENERGY_COICOPS
    assert {fact.period.type for fact in energy} == {"calendar_year", "quarter"}
    for coicop in ONS_ENERGY_COICOPS:
        coicop_facts = [fact for fact in energy if fact.filters["coicop"] == coicop]
        assert len(coicop_facts) == 31
        assert {
            fact.period.value
            for fact in coicop_facts
            if fact.period.type == "calendar_year"
        } == expected_annual_periods
        assert {
            fact.period.value for fact in coicop_facts if fact.period.type == "quarter"
        } == expected_quarterly_periods


def test_ons_energy_subclasses_preserve_publisher_cells_and_concepts():
    package = load_source_package(ONS_PACKAGE)
    cells = package.build_source_cells(2026)
    cells_by_key = {build_source_cell_key(cell): cell for cell in cells}
    facts = package.build_facts(2026, cells=cells)
    annual_2024 = {
        fact.filters["coicop"]: fact
        for fact in facts
        if ".04cn" in fact.layout.record_set_id
        and fact.period.type == "calendar_year"
        and fact.period.value == 2024
    }

    expected = {
        "04.5.1": ("ons.household_expenditure.electricity", "R", 26_099_000_000),
        "04.5.2": ("ons.household_expenditure.gas", "S", 14_642_000_000),
        "04.5.3": ("ons.household_expenditure.liquid_fuels", "T", 1_195_000_000),
        "04.5.4": ("ons.household_expenditure.solid_fuels", "U", 352_000_000),
    }
    for coicop, (concept, column, value) in expected.items():
        fact = annual_2024[coicop]
        assert fact.measure.concept == concept
        assert {cells_by_key[key].address for key in fact.source_cell_keys} == {
            f"{column}36"
        }
        assert fact.measure.unit == "gbp"
        assert fact.aggregation.method == "sum"
        assert fact.value == value
