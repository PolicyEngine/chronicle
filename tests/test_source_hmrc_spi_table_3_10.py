"""SPI 2023-24 Table 3.10 in hmrc-spi-income-bands-2023-24 (PolicyEngine/microcosm#1418)."""

from __future__ import annotations

from chronicle.source_package import load_source_package


def test_table_3_10_employment_income_keeps_its_own_source_concept():
    """Table 3.10's employment income adds other miscellaneous income to Table 3.6's,
    so it keeps a source concept of its own, mapped to Table 3.6's as a broad match."""
    facts = [
        fact
        for fact in load_source_package("hmrc-spi-income-bands-2023-24").build_facts(
            2026
        )
        if fact.layout.record_set_id.startswith("hmrc.spi_2324.table_3_10")
        and fact.layout.measure_id in ("employment_count", "employment_amount")
    ]
    assert len(facts) == 32
    for fact in facts:
        kind = fact.layout.measure_id.removeprefix("employment_")
        assert fact.measure.concept == f"hmrc.spi_employment_income_{kind}"
        assert (
            fact.measure.source_concept
            == f"hmrc.spi_table_3_10_employment_income_{kind}"
        )
        assert fact.measure.concept_relation == "broad_match"
        notes = fact.measure.concept_evidence_notes
        assert "other miscellaneous income (note 4)" in notes
        assert "contribution-based Employment and Support Allowance" in notes
