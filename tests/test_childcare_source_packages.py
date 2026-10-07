"""Regression tests for the childcare source packages requested in issue 219."""

from __future__ import annotations

from pathlib import Path

import yaml

from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import load_source_package, validate_source_package
from chronicle.sources.cells import validate_source_cells
from chronicle.suite import build_source_suite


REPO_ROOT = Path(__file__).parents[1]
DFE_CONCEPT_BY_MEASURE_ID = {
    "registered_children_count": "dfe.funded_childcare_registered_children_total",
    "registered_children_nursery_count": (
        "dfe.funded_childcare_registered_children_nursery"
    ),
    "registered_children_reception_count": (
        "dfe.funded_childcare_registered_children_reception"
    ),
    "eligible_children_count": "dfe.funded_childcare_eligible_children_total",
    "eligible_children_nursery_count": (
        "dfe.funded_childcare_eligible_children_nursery"
    ),
    "eligible_children_universal_credit_count": (
        "dfe.funded_childcare_eligible_children_universal_credit"
    ),
    "eligible_children_legacy_benefit_count": (
        "dfe.funded_childcare_eligible_children_legacy_benefit"
    ),
    "registered_eligible_children_percent": (
        "dfe.funded_childcare_eligible_children_registered_percentage_total"
    ),
    "registered_eligible_children_nursery_percent": (
        "dfe.funded_childcare_eligible_children_registered_percentage_nursery"
    ),
    "all_children_count": "dfe.funded_childcare_estimated_all_children",
    "registered_all_children_percent": (
        "dfe.funded_childcare_all_children_registered_percentage"
    ),
}


def _fact_by_dimensions(facts, *, concept, period, measure_id=None, **dimensions):
    matches = [
        fact
        for fact in facts
        if fact.measure.concept == concept
        and fact.period.value == period
        and (measure_id is None or fact.layout.measure_id == measure_id)
        and all(fact.filters.get(key) == value for key, value in dimensions.items())
    ]
    assert len(matches) == 1
    return matches[0]


def test_hmrc_tax_free_childcare_package_preserves_activity_series():
    package = load_source_package("hmrc-tax-free-childcare-march-2026")
    report = validate_source_package(package.package_path, year=2026)
    cells = package.build_source_cells(2026)
    facts = package.build_facts(2026, cells=cells)

    assert report.valid
    assert report.counts == {
        "record_set_count": 126,
        "row_count": 126,
        "measure_count": 126,
        "source_record_count": 126,
        "source_region_count": 126,
    }
    assert len(cells) == 37_963
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid

    annual_used = {
        fact.period.value: fact.value
        for fact in facts
        if fact.measure.concept == "hmrc.tfc_children_with_used_accounts_annual_unique"
    }
    annual_top_up = {
        fact.period.value: fact.value
        for fact in facts
        if fact.measure.concept == "hmrc.tfc_government_top_up"
    }
    monthly_used = {
        fact.period.value: fact.value
        for fact in facts
        if fact.measure.concept == "hmrc.tfc_children_with_used_accounts_monthly"
    }
    monthly_used_facts = [
        fact
        for fact in facts
        if fact.measure.concept == "hmrc.tfc_children_with_used_accounts_monthly"
    ]

    assert len(annual_used) == len(annual_top_up) == 9
    assert annual_used[2024] == 1_085_020
    assert annual_top_up[2024] == 632_200_000
    assert len(monthly_used) == 108
    assert monthly_used["2017-04"] == 925
    assert monthly_used["2024-04"] == 664_215
    assert monthly_used["2025-04"] == 699_155
    assert monthly_used["2026-03"] == 744_315
    regimes = {
        regime: sum(
            fact.filters["definition_regime"] == regime for fact in monthly_used_facts
        )
        for regime in {
            "used_account_in_period",
            "payment_and_open_at_reference_date",
        }
    }
    assert regimes == {
        "used_account_in_period": 96,
        "payment_and_open_at_reference_date": 12,
    }
    assert (
        next(
            fact for fact in monthly_used_facts if fact.period.value == "2025-03"
        ).filters["definition_regime"]
        == "used_account_in_period"
    )
    assert (
        next(
            fact for fact in monthly_used_facts if fact.period.value == "2025-04"
        ).filters["definition_regime"]
        == "payment_and_open_at_reference_date"
    )
    assert all(
        any(
            constraint.variable == "definition_regime"
            and constraint.operator == "=="
            and constraint.value == fact.filters["definition_regime"]
            for constraint in fact.constraints
        )
        for fact in monthly_used_facts
    )

    assert all(
        fact.entity.name == "person"
        for fact in facts
        if fact.measure.concept != "hmrc.tfc_government_top_up"
    )
    assert all(
        fact.entity.name == "government"
        for fact in facts
        if fact.measure.concept == "hmrc.tfc_government_top_up"
    )
    assert all(fact.geography.id == "K02000001" for fact in facts)
    assert all(fact.provenance_class == "administrative" for fact in facts)
    assert all(fact.source_cell_keys for fact in facts)
    assert not any("share" in fact.measure.concept for fact in facts)
    assert len(consumer_fact_rows(facts)) == len(facts)


def test_dfe_funded_childcare_package_preserves_atomic_child_headlines(tmp_path):
    package = load_source_package("dfe-funded-early-education-childcare-2026")
    report = validate_source_package(package.package_path, year=2026)
    rows = package.build_source_rows(2026)
    cells = package.build_source_cells(2026, source_rows=rows)
    facts = package.build_facts(2026, cells=cells, source_rows=rows)
    declared_columns = [
        (record_set, row, measure)
        for record_set in package.build_source_record_set_specs(2026)
        for row in record_set.rows
        for measure in record_set.measures
    ]

    assert report.valid
    assert len(rows) == 224
    assert len(cells) == 6_075
    assert len(facts) == 770
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid

    working_2025_ages_3_4 = _fact_by_dimensions(
        facts,
        concept="dfe.funded_childcare_registered_children_total",
        period="2025-01",
        measure_id="registered_children_count",
        entitlement_type="Working parents",
        age="3 to 4 years",
    )
    working_2025_age_2 = _fact_by_dimensions(
        facts,
        concept="dfe.funded_childcare_registered_children_total",
        period="2025-01",
        measure_id="registered_children_count",
        entitlement_type="Working parents",
        age="2 years",
    )
    universal_nursery_2024 = _fact_by_dimensions(
        facts,
        concept="dfe.funded_childcare_registered_children_nursery",
        period="2024-01",
        measure_id="registered_children_nursery_count",
        entitlement_type="Universal",
        age="Total",
    )
    working_2024_ages_3_4 = _fact_by_dimensions(
        facts,
        concept="dfe.funded_childcare_registered_children_total",
        period="2024-01",
        measure_id="registered_children_count",
        entitlement_type="Working parents",
        age="3 to 4 years",
    )
    early_learning_2024_age_2 = _fact_by_dimensions(
        facts,
        concept="dfe.funded_childcare_registered_children_total",
        period="2024-01",
        measure_id="registered_children_count",
        entitlement_type="Early learning for 2-year-olds",
        age="2 years",
    )
    eligible_2024_age_2 = _fact_by_dimensions(
        facts,
        concept="dfe.funded_childcare_eligible_children_total",
        period="2024-01",
        measure_id="eligible_children_count",
        entitlement_type="Early learning for 2-year-olds",
        age="2 years",
    )
    registered_share_2024_age_2 = _fact_by_dimensions(
        facts,
        concept=("dfe.funded_childcare_eligible_children_registered_percentage_total"),
        period="2024-01",
        measure_id="registered_eligible_children_percent",
        entitlement_type="Early learning for 2-year-olds",
        age="2 years",
    )

    assert working_2025_ages_3_4.value == 379_029
    assert working_2025_age_2.value == 242_453
    assert universal_nursery_2024.value == 778_327
    assert working_2024_ages_3_4.value == 361_790
    assert early_learning_2024_age_2.value == 115_852
    assert eligible_2024_age_2.value == 154_957
    assert registered_share_2024_age_2.value == 74.763967

    assert all(fact.period.type == "month" for fact in facts)
    assert all(fact.geography.id == "E92000001" for fact in facts)
    assert all(fact.entity.name == "person" for fact in facts)
    assert all(fact.source_row_keys for fact in facts)
    assert all(fact.source.vintage == "release_2026_api_dataset_v1_0" for fact in facts)
    assert all(
        "third-week-of-January" in fact.measure.concept_evidence_notes for fact in facts
    )
    assert all(fact.layout.measure_id in DFE_CONCEPT_BY_MEASURE_ID for fact in facts)
    assert all(
        fact.measure.concept == DFE_CONCEPT_BY_MEASURE_ID[fact.layout.measure_id]
        for fact in facts
    )
    assert len(set(DFE_CONCEPT_BY_MEASURE_ID.values())) == len(
        DFE_CONCEPT_BY_MEASURE_ID
    )
    assert len(declared_columns) == len(facts)
    assert all(measure.source_column_dimensions for _, _, measure in declared_columns)
    assert all(
        all(
            {
                **record_set.shared_filters,
                **row.filters,
                **measure.filters,
            }.get(dimension)
            == value
            for dimension, value in measure.source_column_dimensions.items()
        )
        for record_set, row, measure in declared_columns
    )
    assert working_2025_ages_3_4.filters["registration_basis"] == "registered_children"
    assert working_2025_ages_3_4.filters["provision"] == "all"
    assert universal_nursery_2024.filters["provision"] == "nursery"
    assert eligible_2024_age_2.filters["registration_basis"] == "eligible_children"
    consumer_rows = consumer_fact_rows(facts)
    assert len({row["semantic_fact_key"] for row in consumer_rows}) == len(
        consumer_rows
    )
    assert not any(fact.value in {621_482, 416_537} for fact in facts)
    assert len(consumer_rows) == len(facts)

    suite = build_source_suite(
        "dfe-funded-early-education-childcare-2026",
        tmp_path / "dfe-suite",
        year=2026,
    )
    assert suite.valid
    assert not suite.agent_acceptance.errors


def test_childcare_manifests_pin_content_addressed_raw_artifacts():
    cases = (
        (
            "hmrc/tax_free_childcare_march_2026",
            "c2a8e82a7d1e6c85cbe119ffe0a51e692fac3e5014a37f845484dee710e7a29d",
            321_791,
        ),
        (
            "dfe/funded_early_education_childcare_2026",
            "cefdb06593016446d215433cf31f80649b8ce18f89e454a5ad7931b0ab32d72d",
            33_467,
        ),
    )

    for relative_path, sha256, size_bytes in cases:
        manifest = yaml.safe_load(
            (REPO_ROOT / "db" / "data" / relative_path / "manifest.yaml").read_text()
        )
        file_spec = manifest["files"][2026]
        assert file_spec["sha256"] == sha256
        assert file_spec["size_bytes"] == size_bytes
        assert file_spec["storage"]["r2"]["bucket"] == "ledger-raw"
        assert sha256 in file_spec["storage"]["r2"]["key"]
        assert file_spec["storage"]["r2"]["uri"].startswith("r2://ledger-raw/raw/")
