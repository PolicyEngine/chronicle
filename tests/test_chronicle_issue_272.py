"""Regression coverage for HMRC CGT Tables 7, 8, and 9 (issue #272)."""

from __future__ import annotations

import pytest

from chronicle.bundle import UK_BUNDLE_SOURCES
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


ISSUE_272_PACKAGES = {
    "hmrc-cgt-asset-type-2026": 171,
    "hmrc-cgt-residential-property-2026": 268,
    "hmrc-cgt-carried-interest-2026": 68,
}

ISSUE_272_SOURCE_CELL_COUNTS = {
    "hmrc-cgt-asset-type-2026": 964,
    "hmrc-cgt-residential-property-2026": 1_121,
    "hmrc-cgt-carried-interest-2026": 278,
}

ISSUE_272_ARTIFACTS = {
    "hmrc-cgt-asset-type-2026": (
        "a27ad79c3c67178e8b808c0561201dd6585b472d7919c0043fdc44142460b2bd",
        11_181,
    ),
    "hmrc-cgt-residential-property-2026": (
        "fefe621cab478ca14b06aaeabe0ac2db95a4912b1b40ac029fbbd5ea3fa34952",
        11_240,
    ),
    "hmrc-cgt-carried-interest-2026": (
        "403b04573a4ba942624ee078152aaeb8ce009d80c48e38cbc62d58749fec4ddb",
        6_536,
    ),
}


def _facts(alias: str):
    return load_source_package(alias).build_facts(2026)


def test_issue_272_packages_are_registered():
    assert set(ISSUE_272_PACKAGES) <= set(SOURCE_PACKAGE_ALIASES)
    assert set(ISSUE_272_PACKAGES) <= set(UK_BUNDLE_SOURCES)


@pytest.mark.parametrize(
    ("alias", "expected_fact_count"),
    sorted(ISSUE_272_PACKAGES.items()),
)
def test_issue_272_packages_build_valid_source_backed_facts(
    alias: str,
    expected_fact_count: int,
):
    package = load_source_package(alias)
    report = validate_source_package(package.package_path, year=2026)
    cells = package.build_source_cells(2026)
    facts = package.build_facts(2026, cells=cells)

    assert report.valid, report.to_dict()
    assert len(cells) == ISSUE_272_SOURCE_CELL_COUNTS[alias]
    assert len(facts) == expected_fact_count
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert {fact.source.source_name for fact in facts} == {"hmrc"}
    expected_sha256, expected_size = ISSUE_272_ARTIFACTS[alias]
    assert {fact.source.source_sha256 for fact in facts} == {expected_sha256}
    assert {fact.source.source_size_bytes for fact in facts} == {expected_size}
    assert {fact.assertion for fact in facts} == {"observation"}
    assert all(fact.source_cell_keys for fact in facts)


def test_table_7_emits_only_source_measures_and_keeps_unknown_periods():
    facts = _facts("hmrc-cgt-asset-type-2026")

    assert {fact.period.type for fact in facts} == {"tax_year"}
    assert {fact.period.value for fact in facts} == {2023}
    assert {fact.provenance_class for fact in facts} == {"survey_aggregate"}
    assert len({fact.survey_instrument for fact in facts}) == 1
    assert None not in {fact.survey_instrument for fact in facts}
    assert {fact.measure.unit for fact in facts} == {"count", "gbp"}
    assert {fact.measure.concept for fact in facts} == {
        "hmrc.cgt_disposals",
        "hmrc.cgt_disposal_proceeds",
        "hmrc.cgt_gains",
    }
    assert any(fact.filters.get("cgt_holding_period") == "unknown" for fact in facts)
    assert not any("percentage" in fact.measure.concept for fact in facts)

    residential_unknown_gains = next(
        fact
        for fact in facts
        if fact.measure.concept == "hmrc.cgt_gains"
        and fact.filters
        == {
            "cgt_asset_category": "non_financial",
            "cgt_asset_type": "residential_land_buildings",
            "cgt_holding_period": "unknown",
        }
    )
    assert residential_unknown_gains.value == 2_067_000_000


def test_table_8_keeps_channels_taxpayer_types_and_tax_month_coverage():
    package = load_source_package("hmrc-cgt-residential-property-2026")
    facts = package.build_facts(2026)
    cells = package.build_source_cells(2026)

    assert {fact.provenance_class for fact in facts} == {"administrative"}
    assert {fact.filters.get("channel") for fact in facts} >= {
        "uk_property_service",
        "self_assessment_only",
        "self_assessment_component",
        "total",
    }
    assert {
        fact.measure.concept
        for fact in facts
        if fact.filters.get("channel") == "self_assessment_only"
    } == {"hmrc.cgt_residential_property_taxpayers"}
    assert {
        fact.measure.concept
        for fact in facts
        if fact.filters.get("channel") == "self_assessment_component"
    } == {
        "hmrc.cgt_residential_property_disposals",
        "hmrc.cgt_residential_property_gains",
        "hmrc.cgt_residential_property_tax",
    }
    assert {fact.filters.get("taxpayer_type") for fact in facts} >= {
        "individuals",
        "trusts",
    }
    october_2024 = [fact for fact in facts if fact.period.value == "2024-10"]
    assert len(october_2024) == 5
    assert {fact.period.type for fact in october_2024} == {"month"}
    assert {
        (fact.period_coverage.start_date, fact.period_coverage.end_date)
        for fact in october_2024
    } == {("2024-10-06", "2024-11-05")}
    october_2024_gains = next(
        fact
        for fact in october_2024
        if fact.measure.concept == "hmrc.cgt_residential_property_gains"
    )
    assert october_2024_gains.value == 1_932_000_000
    assert not any(fact.period.value == 2022 for fact in facts)
    assert not any(fact.value == "[Unavailable]" for fact in facts)
    unavailable = next(
        cell
        for cell in cells
        if cell.sheet_name == "Table_8a" and cell.address == "M15"
    )
    assert unavailable.raw_value == "[Unavailable]"


def test_table_9_preserves_carry_shapes_without_inventing_sub_million_tax():
    package = load_source_package("hmrc-cgt-carried-interest-2026")
    facts = package.build_facts(2026)
    cells = package.build_source_cells(2026)

    assert {fact.provenance_class for fact in facts} == {"administrative"}
    assert {fact.period.value for fact in facts} == {2023, 2024}
    assert {fact.filters.get("sex") for fact in facts} >= {"female", "male"}
    assert any("cgt_carried_interest_gain_band" in fact.filters for fact in facts)
    assert any("age_band" in fact.filters for fact in facts)
    assert not any(fact.value == "[Less than 1]" for fact in facts)

    table_9a = [
        fact
        for fact in facts
        if fact.layout.record_set_id and ".table9a." in fact.layout.record_set_id
    ]
    assert len(table_9a) == 18
    assert {fact.layout.groupby_dimension for fact in table_9a} == {
        "hmrc.cgt_carried_interest_year"
    }
    assert {fact.layout.groupby_dimension_label for fact in table_9a} == {
        "Year of disposal"
    }
    assert {
        (
            fact.period.value,
            fact.layout.groupby_value_id,
            fact.layout.groupby_value_label,
        )
        for fact in table_9a
    } == {
        (2023, "ty2023", "Year of disposal 2023 to 2024"),
        (2024, "ty2024", "Year of disposal 2024 to 2025"),
    }

    sub_million_tax = next(
        cell for cell in cells if cell.sheet_name == "Table_9b" and cell.address == "D7"
    )
    assert sub_million_tax.raw_value == "[Less than 1]"

    total_2024 = [
        fact
        for fact in facts
        if fact.period.value == 2024
        and not fact.filters
        and fact.layout.table_record_kind == "total"
    ]
    assert {fact.value for fact in total_2024} >= {
        3_890,
        5_388_000_000,
        1_448_000_000,
    }


@pytest.mark.parametrize(
    ("alias", "expected_duplicate_semantic_keys"),
    [
        ("hmrc-cgt-asset-type-2026", 18),
        ("hmrc-cgt-residential-property-2026", 15),
        ("hmrc-cgt-carried-interest-2026", 3),
    ],
)
def test_issue_272_repeated_publisher_margins_agree(
    alias: str,
    expected_duplicate_semantic_keys: int,
):
    rows_by_semantic_key = {}
    for row in consumer_fact_rows(_facts(alias)):
        rows_by_semantic_key.setdefault(row["semantic_fact_key"], []).append(row)
    duplicates = [rows for rows in rows_by_semantic_key.values() if len(rows) > 1]

    assert len(duplicates) == expected_duplicate_semantic_keys
    assert all(len({row["value"] for row in rows}) == 1 for rows in duplicates)
