"""Regression tests for the family and household composition packages
(chronicle#235 ONS Tables 1 and 3, #236 HMRC Child Benefit, #237 census
household composition)."""

from __future__ import annotations

import pytest

from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import load_source_package, validate_source_package


def _fact(
    facts, *, concept, period, geography_id="K02000001", record_set_id=None, **filters
):
    matches = [
        fact
        for fact in facts
        if fact.measure.concept == concept
        and fact.period.value == period
        and fact.geography.id == geography_id
        and (record_set_id is None or fact.layout.record_set_id == record_set_id)
        and all(fact.filters.get(key) == value for key, value in filters.items())
    ]
    assert len(matches) == 1, (concept, period, geography_id, filters, len(matches))
    return matches[0]


# --- chronicle#235: ONS Families and households 2025, Tables 1 and 3 ---


def test_ons_families_tables_1_and_3_carry_estimates_and_confidence_intervals():
    package = load_source_package("ons-families-households-2025")
    report = validate_source_package(package.package_path, year=2025)
    facts = package.build_facts(2025)
    families = [fact for fact in facts if fact.entity.name == "family"]

    assert report.valid
    assert report.counts["record_set_count"] == 40
    assert report.counts["source_record_count"] == 816
    assert len(facts) == 816
    assert len(families) == 720
    assert {fact.entity.role for fact in families} == {"resident_family"}
    assert {fact.period.value for fact in families} == set(range(2018, 2026))
    assert {fact.provenance_class for fact in families} == {"survey_aggregate"}
    assert {fact.survey_instrument for fact in families} == {"Labour Force Survey"}
    assert {fact.filters["statistic"] for fact in families} == {
        "estimate",
        "ci_95_half_width",
    }
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert len(consumer_fact_rows(facts)) == len(facts)

    lone_parent = _fact(
        facts,
        concept="ons.families_by_type",
        period=2025,
        family_type="lone_parent",
        children="dependent_children",
        statistic="estimate",
    )
    lone_parent_ci = _fact(
        facts,
        concept="ons.families_by_type",
        period=2025,
        family_type="lone_parent",
        children="dependent_children",
        statistic="ci_95_half_width",
    )
    assert lone_parent.value == 1_946_000
    assert lone_parent_ci.value == 88_000
    assert lone_parent.layout.table_record_kind == "detail"
    assert (
        _fact(
            facts,
            concept="ons.families_by_type",
            period=2024,
            family_type="lone_parent",
            children="dependent_children",
            statistic="estimate",
        ).value
        == 1_986_000
    )
    assert (
        _fact(
            facts,
            concept="ons.families_by_type",
            period=2025,
            family_type="all_families",
            children="dependent_children",
            statistic="estimate",
        ).value
        == 8_512_000
    )
    one_child = _fact(
        facts,
        concept="ons.families_with_dependent_children_by_number",
        period=2025,
        family_type="lone_parent",
        number_of_dependent_children="one",
        statistic="estimate",
    )
    assert one_child.value == 1_081_000
    assert (
        _fact(
            facts,
            concept="ons.families_with_dependent_children_by_number",
            period=2025,
            family_type="lone_parent",
            number_of_dependent_children="one",
            statistic="ci_95_half_width",
        ).value
        == 68_000
    )
    # Value cell plus the row and column header cells back every fact.
    assert len(lone_parent.source_cell_keys) == 3


def test_ons_families_households_household_tables_are_unchanged():
    facts = load_source_package("ons-families-households-2025").build_facts(2025)
    households = [fact for fact in facts if fact.entity.name == "household"]

    assert len(households) == 96
    assert {fact.measure.concept for fact in households} == {
        "ons.households_by_type",
        "ons.households_total",
        "ons.average_household_size",
    }


# --- chronicle#236: HMRC Child Benefit statistics, August 2025 ---


def test_hmrc_child_benefit_package_builds_headline_series_and_cross_sections():
    package = load_source_package("hmrc-child-benefit-august-2025")
    report = validate_source_package(package.package_path, year=2025)
    facts = package.build_facts(2025)

    assert report.valid
    assert report.counts["record_set_count"] == 205
    assert report.counts["source_record_count"] == 1166
    assert len(facts) == 1166
    assert {fact.entity.name for fact in facts} == {
        "family",
        "person",
        "government",
    }
    assert {fact.assertion for fact in facts} == {"observation"}
    assert {fact.geography.level for fact in facts} == {"country", "region"}
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert len(consumer_fact_rows(facts)) == len(facts)

    registered = _fact(
        facts, concept="hmrc.child_benefit_families_registered", period="2025-08"
    )
    in_payment = _fact(
        facts,
        concept="hmrc.child_benefit_families_in_payment",
        period="2025-08",
        record_set_id="hmrc.child_benefit.aug2025.families_in_payment.month2025_08",
    )
    assert registered.value == 7_552_330
    assert registered.entity.name == "family"
    assert registered.period.type == "month"
    assert in_payment.value == 6_867_695
    assert (
        _fact(
            facts, concept="hmrc.child_benefit_families_registered", period="2024-08"
        ).value
        == 7_619_265
    )
    assert (
        _fact(
            facts, concept="hmrc.child_benefit_children_registered", period="2025-08"
        ).value
        == 12_730_410
    )
    assert (
        _fact(
            facts,
            concept="hmrc.child_benefit_children_in_payment",
            period="2025-08",
            record_set_id="hmrc.child_benefit.aug2025.children_in_payment.month2025_08",
        ).value
        == 11_730_730
    )
    assert {
        fact.period.value
        for fact in facts
        if fact.measure.concept == "hmrc.child_benefit_families_in_payment"
        and fact.filters == {"payment_status": "in_payment"}
    } == {f"{year}-08" for year in range(2003, 2026)}


def test_hmrc_child_benefit_opt_outs_and_number_of_children():
    facts = load_source_package("hmrc-child-benefit-august-2025").build_facts(2025)

    opted_out = _fact(
        facts,
        concept="hmrc.child_benefit_families_opted_out",
        period="2025-08",
        claimant_sex="all",
    )
    assert opted_out.value == 684_635
    assert (
        _fact(
            facts,
            concept="hmrc.child_benefit_children_in_opted_out_families",
            period="2025-08",
            child_age_band="all",
        ).value
        == 999_680
    )
    by_children = {
        fact.filters["number_of_children"]: fact.value
        for fact in facts
        if fact.measure.concept == "hmrc.child_benefit_families_in_payment"
        and fact.period.value == "2025-08"
        and fact.geography.id == "K02000001"
        and fact.layout.record_set_id
        == "hmrc.child_benefit.aug2025.families_in_payment_by_number_of_children.month2025_08"
    }
    assert by_children == {
        "all": 6_867_695,
        "one": 3_356_385,
        "two": 2_524_055,
        "three": 725_315,
        "four": 191_920,
        "five_to_nine": 69_660,
        "ten_or_more": 370,
    }
    # The pre-2019 series carries the publisher's single 'Five or more' column.
    assert (
        _fact(
            facts,
            concept="hmrc.child_benefit_families_in_payment",
            period="2011-08",
            number_of_children="five_or_more",
        ).value
        == 85_340
    )
    scotland = _fact(
        facts,
        concept="hmrc.child_benefit_families_in_payment",
        period="2025-08",
        geography_id="S92000003",
        number_of_children="all",
    )
    assert scotland.value == 510_220
    assert scotland.geography.level == "country"
    assert (
        _fact(
            facts,
            concept="hmrc.child_benefit_families_in_payment",
            period="2025-08",
            geography_id="E12000007",
            number_of_children="all",
        ).geography.level
        == "region"
    )


def test_hmrc_child_benefit_take_up_and_hicbc_facts():
    facts = load_source_package("hmrc-child-benefit-august-2025").build_facts(2025)

    take_up_2022 = _fact(
        facts,
        concept="hmrc.child_benefit_claim_rate_of_eligible_children",
        period="2022-05",
        child_age="All ages",
    )
    assert take_up_2022.value == pytest.approx(88.6)
    assert take_up_2022.measure.unit == "percent"
    assert take_up_2022.provenance_class == "model_output"
    assert take_up_2022.entity.name == "person"
    assert _fact(
        facts,
        concept="hmrc.child_benefit_claim_rate_of_eligible_children",
        period="2025-05",
        child_age="All ages",
    ).value == pytest.approx(86.6)
    # Table 16 (tax-year series) and Table 17 (2023-24 by country and region)
    # both print the UK 2023-24 figures; select the series record sets.
    individuals = _fact(
        facts,
        concept="hmrc.hicbc_individuals_with_liability",
        period=2023,
        record_set_id="hmrc.child_benefit.aug2025.hicbc_individuals.ty2023",
    )
    revenue = _fact(
        facts,
        concept="hmrc.hicbc_tax_revenue",
        period=2023,
        record_set_id="hmrc.child_benefit.aug2025.hicbc_revenue.ty2023",
    )
    assert individuals.value == 436_560
    assert individuals.period.type == "tax_year"
    assert individuals.entity.name == "person"
    assert revenue.value == 593_336_825
    assert revenue.measure.unit == "gbp"
    assert revenue.entity.name == "government"


# --- chronicle#237: census household composition, country level ---


def test_census_household_composition_country_packages():
    expectations = {
        "ons-census2021-ts003-household-composition-country": (
            2021,
            66,
            "ons.census2021_household_composition",
        ),
        "nrs-census2022-uv113-household-composition-country": (
            2022,
            26,
            "nrs.census2022_household_composition",
        ),
        "nisra-census2021-household-composition-country": (
            2021,
            23,
            "nisra.census2021_household_composition",
        ),
    }
    for alias, (year, fact_count, concept) in expectations.items():
        package = load_source_package(alias)
        report = validate_source_package(package.package_path, year=year)
        facts = package.build_facts(year)

        assert report.valid, alias
        assert len(facts) == fact_count, alias
        assert {fact.measure.concept for fact in facts} == {concept}
        assert {fact.provenance_class for fact in facts} == {"census"}
        assert {fact.entity.name for fact in facts} == {"household"}
        assert {fact.period.value for fact in facts} == {year}
        assert all(fact.source_row_keys for fact in facts)
        assert validate_facts(facts).valid
        assert validate_consumer_fact_contract(facts).valid
        assert len(consumer_fact_rows(facts)) == len(facts)


def test_census_lone_parent_households_with_dependent_children_as_published():
    ew = load_source_package(
        "ons-census2021-ts003-household-composition-country"
    ).build_facts(2021)
    lone_parent = "Single family household: Lone parent family: With dependent children"
    assert {fact.geography.id for fact in ew} == {"K04000001", "E92000001", "W92000004"}
    assert (
        _fact(
            ew,
            concept="ons.census2021_household_composition",
            period=2021,
            geography_id="K04000001",
            c2021_hhcomp_15_name=lone_parent,
        ).value
        == 1_719_350
    )
    assert (
        _fact(
            ew,
            concept="ons.census2021_household_composition",
            period=2021,
            geography_id="E92000001",
            c2021_hhcomp_15_name=lone_parent,
        ).value
        == 1_617_076
    )
    assert (
        _fact(
            ew,
            concept="ons.census2021_household_composition",
            period=2021,
            geography_id="W92000004",
            c2021_hhcomp_15_name=lone_parent,
        ).value
        == 102_274
    )
    total = _fact(
        ew,
        concept="ons.census2021_household_composition",
        period=2021,
        geography_id="K04000001",
        c2021_hhcomp_15_name="Total: All households",
    )
    assert total.value == 24_783_199
    assert total.layout.table_record_kind == "total"
    assert (
        _fact(
            ew,
            concept="ons.census2021_household_composition",
            period=2021,
            geography_id="K04000001",
            c2021_hhcomp_15_name="Other household types: With dependent children",
        ).value
        == 656_418
    )

    scotland = load_source_package(
        "nrs-census2022-uv113-household-composition-country"
    ).build_facts(2022)
    assert (
        _fact(
            scotland,
            concept="nrs.census2022_household_composition",
            period=2022,
            geography_id="S92000003",
            household_composition="One family household: Lone parent family: One dependent child",
        ).value
        == 82_643
    )
    assert (
        _fact(
            scotland,
            concept="nrs.census2022_household_composition",
            period=2022,
            geography_id="S92000003",
            household_composition="One family household: Lone parent family: Two or more dependent children",
        ).value
        == 62_982
    )
    all_households = _fact(
        scotland,
        concept="nrs.census2022_household_composition",
        period=2022,
        geography_id="S92000003",
        household_composition="All households",
    )
    assert all_households.value == 2_509_269
    assert all_households.layout.table_record_kind == "total"

    ni = load_source_package(
        "nisra-census2021-household-composition-country"
    ).build_facts(2021)
    assert sum(fact.value for fact in ni) == 768_811
    assert (
        _fact(
            ni,
            concept="nisra.census2021_household_composition",
            period=2021,
            geography_id="N92000002",
            household_composition_label="Single family household: Lone parent family (female): One dependent child",
        ).value
        == 28_080
    )
    assert (
        _fact(
            ni,
            concept="nisra.census2021_household_composition",
            period=2021,
            geography_id="N92000002",
            household_composition_label="Single family household: Lone parent family (male): One dependent child",
        ).value
        == 2_906
    )
    assert {fact.layout.table_record_kind for fact in ni} == {"detail"}
