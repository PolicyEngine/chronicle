"""Tests for source-backed Chronicle SOI fact builders."""

from __future__ import annotations

from chronicle.core import validate_facts
from chronicle.jurisdictions.us.soi import (
    AXIOM_IRC_AGI_CONCEPT,
    IRS_SOI_AGI_SOURCE_CONCEPT,
    build_soi_table_1_1_source_cells,
    build_soi_table_1_1_source_region_specs,
    build_soi_table_1_1_source_record_set_spec,
    build_soi_table_1_1_source_record_specs,
    build_soi_table_1_1_facts,
    build_soi_table_1_4_source_region_specs,
    build_soi_table_1_4_facts,
    _legacy_soi_table_1_1_source_record_specs,
)
from chronicle.sources.cells import build_source_cell_key


def test_build_soi_table_1_1_facts_from_packaged_source():
    facts = build_soi_table_1_1_facts(2023)
    values_by_concept = {
        fact.measure.concept: fact.value
        for fact in facts
        if fact.filters["income_range"] == "all"
    }

    assert validate_facts(facts).valid
    assert len(facts) == 80
    assert values_by_concept == {
        "irs_soi.individual_income_tax_returns": 160_602_107,
        AXIOM_IRC_AGI_CONCEPT: 15_286_017_359_000,
        "irs_soi.total_income_tax": 2_147_909_818_000,
        "irs_soi.returns_with_income_tax_after_credits": 111_545_061,
    }
    assert {fact.source.url for fact in facts} == {
        "https://www.irs.gov/pub/irs-soi/23in11si.xls"
    }
    assert all(fact.label for fact in facts)
    assert all(fact.source_record_id for fact in facts)
    assert all(len(fact.source_cell_keys) == 1 for fact in facts)


def test_build_soi_table_1_1_facts_includes_agi_brackets():
    facts = build_soi_table_1_1_facts(2023)
    facts_by_concept_and_range = {
        (fact.measure.concept, fact.filters["income_range"]): fact for fact in facts
    }

    returns = facts_by_concept_and_range[
        ("irs_soi.individual_income_tax_returns", "100k_to_200k")
    ]
    agi = facts_by_concept_and_range[(AXIOM_IRC_AGI_CONCEPT, "100k_to_200k")]
    tax = facts_by_concept_and_range[("irs_soi.total_income_tax", "100k_to_200k")]
    positive_tax_returns = facts_by_concept_and_range[
        ("irs_soi.returns_with_income_tax_after_credits", "100k_to_200k")
    ]

    assert returns.value == 27_602_755
    assert agi.value == 3_818_295_141_000
    assert tax.value == 409_532_689_000
    assert positive_tax_returns.value == 27_208_705
    assert returns.filters["agi_lower_usd"] == 100_000
    assert returns.filters["agi_upper_usd"] == 200_000
    assert returns.constraints[0].variable == AXIOM_IRC_AGI_CONCEPT
    assert agi.measure.source_concept == IRS_SOI_AGI_SOURCE_CONCEPT
    assert agi.measure.concept_relation == "exact"
    assert agi.layout is not None
    assert agi.layout.record_set_id == "irs_soi.ty2023.table_1_1"
    assert agi.layout.groupby_dimension == AXIOM_IRC_AGI_CONCEPT
    assert agi.layout.groupby_value_id == "100k_to_200k"
    assert agi.layout.measure_id == "adjusted_gross_income"


def test_soi_facts_carry_source_cell_lineage():
    facts = build_soi_table_1_1_facts(2023)
    fact = next(
        fact
        for fact in facts
        if fact.measure.concept == AXIOM_IRC_AGI_CONCEPT
        and fact.filters["income_range"] == "all"
    )
    source_cell = next(
        cell for cell in build_soi_table_1_1_source_cells(2023) if cell.address == "D10"
    )

    assert fact.source_record_id == "irs_soi.ty2023.table_1_1.all.adjusted_gross_income"
    assert fact.source_cell_keys == (build_source_cell_key(source_cell),)


def test_soi_record_set_spec_compiles_to_legacy_atomic_specs():
    record_set = build_soi_table_1_1_source_record_set_spec(2023)
    compiled = build_soi_table_1_1_source_record_specs(2023)
    legacy = _legacy_soi_table_1_1_source_record_specs(2023)

    assert len(record_set.rows) == 20
    assert len(record_set.measures) == 4
    assert len(compiled) == 80
    assert [
        (spec.source_record_id, spec.selector.address, spec.concept)
        for spec in compiled
    ] == [
        (spec.source_record_id, spec.selector.address, spec.concept) for spec in legacy
    ]
    assert compiled[0].layout is not None
    assert compiled[0].layout.record_set_spec_hash


def test_soi_source_region_spec_covers_selected_record_set():
    regions = build_soi_table_1_1_source_region_specs(2023)

    assert len(regions) == 1
    assert regions[0].region_id == "irs_soi.ty2023.table_1_1.selected_region"
    assert regions[0].record_set_id == "irs_soi.ty2023.table_1_1"
    assert regions[0].sheet_name == "TBL11"
    assert regions[0].top_row == 10
    assert regions[0].bottom_row == 29
    assert regions[0].left_column == 1
    assert regions[0].right_column == 17


def test_build_soi_table_1_4_wage_facts_from_packaged_source():
    facts = build_soi_table_1_4_facts(2023)
    facts_by_concept_and_range = {
        (fact.measure.concept, fact.filters["income_range"]): fact for fact in facts
    }

    assert validate_facts(facts).valid
    assert len(facts) == 740
    assert (
        facts_by_concept_and_range[("irs_soi.returns_with_total_wages", "all")].value
        == 128_591_050
    )
    all_wages = facts_by_concept_and_range[("us:statutes/26/62#input.wages", "all")]
    assert all_wages.value == 10_204_095_705_000
    assert all_wages.measure.source_concept == "irs_soi.total_wages"
    assert all_wages.measure.concept_relation == "broad_match"
    assert (
        facts_by_concept_and_range[
            ("irs_soi.returns_with_total_wages", "100k_to_200k")
        ].value
        == 23_193_910
    )
    assert (
        facts_by_concept_and_range[
            ("us:statutes/26/62#input.wages", "100k_to_200k")
        ].value
        == 2_774_550_975_000
    )
    assert (
        facts_by_concept_and_range[("irs_soi.taxable_net_capital_gains", "all")].value
        == 966_168_014_000
    )
    assert (
        facts_by_concept_and_range[("irs_soi.taxable_pension_income", "all")].value
        == 932_130_236_000
    )
    assert (
        facts_by_concept_and_range[
            ("irs_soi.taxable_social_security_benefits", "all")
        ].value
        == 527_072_873_000
    )
    assert (
        facts_by_concept_and_range[("irs_soi.alimony_received", "all")].value
        == 6_686_429_000
    )
    assert (
        facts_by_concept_and_range[("irs_soi.alimony_paid", "all")].value
        == 7_497_135_000
    )
    assert {fact.source.url for fact in facts} == {
        "https://www.irs.gov/pub/irs-soi/23in14ar.xls"
    }
    assert all(fact.layout for fact in facts)


def test_soi_table_1_4_source_region_spec_covers_wage_record_set():
    regions = build_soi_table_1_4_source_region_specs(2023)

    assert len(regions) == 1
    assert regions[0].region_id == "irs_soi.ty2023.table_1_4.selected_region"
    assert regions[0].record_set_id == "irs_soi.ty2023.table_1_4"
    assert regions[0].sheet_name == "TBL14"
    assert regions[0].top_row == 9
    assert regions[0].bottom_row == 28
    assert regions[0].left_column == 1
    assert regions[0].right_column == 123
