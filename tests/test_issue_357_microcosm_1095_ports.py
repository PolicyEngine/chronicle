"""Regression tests for the chronicle#357 facts behind Microcosm's microcosm#1095 ports.

- HMRC Annual Stamp Tax Statistics 2024 to 2025 (the corrected tables of 11 March
  2026), Tables 6b, 8a and 8b for 2023-24 and 2024-25.
- OBR EFO March 2026 receipts, sheet 3.7: the EFO's only SDLT breakdown, by property
  type and rate. The EFO publishes no split by type of buyer (item 2).
- OBR EFO March 2026 expenditure, table 4.9: each DWP line stamped with the geography
  DWP's own tables give it, and the Northern Ireland rows ported (item 4).
- DWP Households Below Average Income, FYE 2025 release: medians and relative low
  income before and after housing costs, FYE 1995 to FYE 2025, and the FYE 2025 95%
  confidence intervals from the release's data-table ZIP (item 5).
- DWP Move to Universal Credit, households sent a migration notice by combination of
  legacy benefits and move status, cumulative from July 2022 to June 2026, from
  Stat-Xplore (item 3).

Values are the publishers' as fetched on 2026-10-15.
"""

from __future__ import annotations

from collections import Counter

import pytest

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import validate_consumer_fact_contract
from chronicle.core import validate_facts
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package

STAMPS = "hmrc-stamp-tax-statistics-2024-25"
HBAI = "dwp-hbai-summary-fye2025"
HBAI_CI = "dwp-hbai-uncertainty-fye2025"
RECEIPTS = "obr-efo-receipts-march-2026"
EXPENDITURE = "obr-efo-expenditure-march-2026"
MTUC = "dwp-mtuc-households-legacy-benefit-move-status-july-2022-june-2026"
NEW_PACKAGES = {
    STAMPS: (2025, 352),
    HBAI: (2025, 124),
    HBAI_CI: (2025, 8),
    MTUC: (2026, 80),
}

UK, GB, EW, NI = "K02000001", "K03000001", "K04000001", "N92000002"


@pytest.fixture(scope="module")
def facts():
    return {
        alias: load_source_package(alias).build_facts(year)
        for alias, (year, _count) in NEW_PACKAGES.items()
    }


@pytest.mark.parametrize("alias", sorted(NEW_PACKAGES))
def test_packages_are_registered_valid_and_complete(alias, facts):
    assert alias in SOURCE_PACKAGE_ALIASES
    assert alias in UK_BUNDLE_SOURCES
    built = facts[alias]
    assert len(built) == NEW_PACKAGES[alias][1]
    assert validate_facts(built).valid
    assert validate_consumer_fact_contract(built).valid
    assert all(fact.source_cell_keys for fact in built)


def _stamp(facts, table, year, measure, band=None, buyer=None):
    matches = [
        fact
        for fact in facts[STAMPS]
        if fact.layout.record_set_id.split(".")[2] == f"table_{table}"
        and fact.period.value == year
        and fact.layout.measure_id == measure
        and fact.filters.get("sdlt_price_band") == band
        and fact.filters.get("sdlt_buyer_type") == buyer
    ]
    assert len(matches) == 1, (table, year, measure, band, buyer, len(matches))
    return matches[0]


def test_stamp_tables_8a_and_8b_buyer_types(facts):
    # Table 8a 2024-25, all price bands: other buyers' residential SDLT.
    assert (
        _stamp(facts, "8a", 2024, "transactions", buyer="other_buyers").value == 124_500
    )
    assert (
        _stamp(facts, "8a", 2024, "property_value", buyer="other_buyers").value
        == 44_690e6
    )
    assert _stamp(facts, "8a", 2024, "receipts", buyer="other_buyers").value == 1_230e6
    assert _stamp(facts, "8a", 2024, "receipts", buyer="individuals").value == 9_145e6
    assert _stamp(facts, "8a", 2024, "receipts").value == 10_380e6
    assert _stamp(facts, "8a", 2023, "receipts").value == 8_570e6
    # Table 8b 2024-25: non-residential SDLT, other buyers and all buyers.
    assert _stamp(facts, "8b", 2024, "receipts", buyer="other_buyers").value == 3_260e6
    assert _stamp(facts, "8b", 2024, "receipts").value == 3_505e6
    # The corporate flat-rate row sits outside the price bands and has no individuals.
    corporate = "corporate_bodies_flat_rate"
    assert (
        _stamp(
            facts, "8a", 2024, "transactions", band=corporate, buyer="other_buyers"
        ).value
        == 100
    )
    assert not [
        fact
        for fact in facts[STAMPS]
        if fact.filters.get("sdlt_price_band") == corporate
        and fact.filters.get("sdlt_buyer_type") == "individuals"
    ]
    assert not [
        fact
        for fact in facts[STAMPS]
        if fact.filters.get("sdlt_price_band") == corporate
        and fact.filters.get("sdlt_property_type") == "non_residential"
    ]


def test_stamp_table_6b_keeps_the_surcharge_gross(facts):
    hrad = [
        f
        for f in facts[STAMPS]
        if f.filters.get("sdlt_higher_rates") == "additional_dwellings"
    ]
    assert Counter(f.layout.measure_id for f in hrad) == {
        "hrad_transactions": 22,
        "hrad_property_value": 22,
        "hrad_receipts_gross": 22,
        "hrad_surcharge_element_gross": 22,
    }
    assert _stamp(facts, "6b", 2024, "hrad_transactions").value == 211_700
    assert _stamp(facts, "6b", 2024, "hrad_surcharge_element_gross").value == 2_790e6
    assert (
        _stamp(facts, "6b", 2024, "hrad_receipts_gross", band="over_gbp_10m").value
        == 385e6
    )
    # The corrected column (I) and the other percentages are not ported.
    assert not [f for f in facts[STAMPS] if "proportion" in f.layout.measure_id]


def test_stamp_facts_state_coverage_threshold_and_edition(facts):
    stamps = facts[STAMPS]
    assert {f.geography.id for f in stamps} == {"hmrc:england_and_northern_ireland"}
    assert {f.geography.level for f in stamps} == {"statistical_scope"}
    assert {f.geography.name for f in stamps} == {"England and Northern Ireland"}
    assert {f.period.type for f in stamps} == {"fiscal_year"}
    assert {f.period.value for f in stamps} == {2023, 2024}
    assert {f.source.vintage for f in stamps} == {
        "annual_stamp_tax_statistics_2024_25_corrected_2026_03_11"
    }
    for fact in stamps:
        threshold = [
            c for c in fact.constraints if c.variable == "sdlt_chargeable_consideration"
        ]
        assert (
            len(threshold) == 1
            and threshold[0].operator == ">="
            and threshold[0].value == 40000
        )


def test_obr_sheet_3_7_property_type_lines():
    facts = load_source_package(RECEIPTS).build_facts(2025)
    lines = {
        fact.layout.record_set_id.split(".")[3]
        for fact in facts
        if fact.layout.record_set_id.startswith("obr.efo_2026_03.receipts.sdlt_")
    }
    assert lines == {
        "sdlt_residential",
        "sdlt_residential_main_rates",
        "sdlt_residential_higher_rates_additional_dwellings",
        "sdlt_residential_non_uk_resident_surcharge",
        "sdlt_non_residential",
    }

    def value(line, year):
        (fact,) = [
            f
            for f in facts
            if f.layout.record_set_id == f"obr.efo_2026_03.receipts.{line}.fy{year}"
        ]
        return fact.value

    # chronicle#397: only the 2024-25 outturn, which the October 2026 EFO does not
    # print, stays in the March package.
    assert {
        fact.period.value
        for fact in facts
        if fact.layout.record_set_id.startswith("obr.efo_2026_03.receipts.sdlt")
    } == {2024}
    # Outturn 2024-25 equals HMRC's all-buyer totals (Tables 8a and 8b).
    assert value("sdlt_residential", 2024) == pytest.approx(10.38e9)
    assert value("sdlt_non_residential", 2024) == pytest.approx(3.505e9)
    # The two property types make up sheet 3.8's SDLT line.
    assert value("sdlt_residential", 2024) + value(
        "sdlt_non_residential", 2024
    ) == pytest.approx(value("sdlt", 2024), rel=1e-9)


EXPENDITURE_STAMPS = {
    "housing_benefit": GB,
    "dla_and_pip": EW,
    "incapacity_benefits": GB,
    "attendance_allowance": EW,
    "pension_credit": GB,
    "carers_allowance": EW,
    "statutory_maternity_pay": GB,
    "winter_fuel_payment": EW,
    "universal_credit_in_cap": GB,
    "child_benefit": UK,
    "state_pension": GB,
    "jobseekers_allowance": GB,
    "universal_credit_outside_cap": GB,
    "ni_social_security_in_welfare_cap": NI,
    "ni_social_security_outside_welfare_cap": NI,
}


def test_obr_table_4_9_lines_carry_dwp_geography():
    facts = load_source_package(EXPENDITURE).build_facts(2025)
    table = [
        f for f in facts if f.layout.record_set_id.split(".")[3] in EXPENDITURE_STAMPS
    ]
    # chronicle#397: 2024-25 only; the October 2026 EFO carries the later years.
    assert len(table) == len(EXPENDITURE_STAMPS)
    for fact in table:
        line = fact.layout.record_set_id.split(".")[3]
        assert fact.geography.id == EXPENDITURE_STAMPS[line], (line, fact.geography.id)
        assert fact.geography.level == "country"
    names = {f.geography.id: f.geography.name for f in table}
    assert names == {
        UK: "United Kingdom",
        GB: "Great Britain",
        EW: "England and Wales",
        NI: "Northern Ireland",
    }
    # The Northern Ireland rows are new; the restamp changes no value.
    by_line = {
        (f.layout.record_set_id.split(".")[3], f.period.value): f.value for f in table
    }
    assert by_line[("ni_social_security_in_welfare_cap", 2024)] == pytest.approx(
        5_709_140_000
    )
    assert by_line[("ni_social_security_outside_welfare_cap", 2024)] == pytest.approx(
        3_999_748_000
    )
    assert by_line[("carers_allowance", 2024)] == pytest.approx(4_239_907_876.11)
    # Table 4.1 and 4.19 lines keep the United Kingdom.
    others = [
        f
        for f in facts
        if f.layout.record_set_id.split(".")[3] not in EXPENDITURE_STAMPS
    ]
    assert {f.geography.id for f in others} == {UK}


def test_hbai_series_coverage_price_basis_and_values(facts):
    summary = facts[HBAI]
    assert Counter(f.layout.measure_id for f in summary) == {
        "median_equivalised_household_income": 62,
        "relative_low_income_share": 62,
    }
    years = {f.period.value for f in summary}
    assert years == set(range(1994, 2025))
    # Great Britain before 2002/03, the United Kingdom from it (HBAI Notes).
    assert {f.geography.id for f in summary if f.period.value < 2002} == {GB}
    assert {f.geography.id for f in summary if f.period.value >= 2002} == {UK}
    medians = [
        f
        for f in summary
        if f.layout.measure_id == "median_equivalised_household_income"
    ]
    assert {f.filters["price_basis"] for f in medians} == {"average_2024_25_prices"}
    assert {f.measure.unit for f in medians} == {"gbp_per_week"}
    assert {f.source.vintage for f in summary} == {"hbai_fye2025_release_2026_03_26"}

    def latest(measure, basis):
        (fact,) = [
            f
            for f in summary
            if f.period.value == 2024
            and f.layout.measure_id == measure
            and f.filters["housing_costs"] == basis
        ]
        return fact.value

    assert latest(
        "median_equivalised_household_income", "before_housing_costs"
    ) == pytest.approx(719.481, abs=1e-3)
    assert latest(
        "median_equivalised_household_income", "after_housing_costs"
    ) == pytest.approx(623.144, abs=1e-3)
    assert latest("relative_low_income_share", "before_housing_costs") == pytest.approx(
        15.912, abs=1e-3
    )
    assert latest("relative_low_income_share", "after_housing_costs") == pytest.approx(
        19.641, abs=1e-3
    )


def test_hbai_confidence_intervals_bracket_the_estimates(facts):
    summary = {
        (f.layout.measure_id, f.filters["housing_costs"]): f.value
        for f in facts[HBAI]
        if f.period.value == 2024
    }
    bounds = {}
    for fact in facts[HBAI_CI]:
        assert fact.period.value == 2024 and fact.geography.id == UK
        measure = fact.layout.measure_id.rsplit("_ci_95_", 1)[0]
        bounds.setdefault((measure, fact.filters["housing_costs"]), {})[
            fact.filters["statistic"]
        ] = fact.value
    assert set(bounds) == set(summary)
    for key, interval in bounds.items():
        assert (
            interval["ci_95_lower_bound"] < summary[key] < interval["ci_95_upper_bound"]
        )
    assert bounds[("median_equivalised_household_income", "before_housing_costs")] == {
        "ci_95_lower_bound": pytest.approx(703.567, abs=1e-3),
        "ci_95_upper_bound": pytest.approx(735.576, abs=1e-3),
    }


def test_hbai_intervals_come_from_the_zip_member():
    package = load_source_package(HBAI_CI)
    assert package.artifact.parser == "zip_ods_used_range"
    assert package.artifact.archive_member == "uncertainty-hbai-2024-25-tables.ods"
    cells = package.artifact.build_source_cells(2025)
    sources = {cell.artifact.source_file for cell in cells}
    assert sources == {"hbai-data_tables-2025.zip!uncertainty-hbai-2024-25-tables.ods"}


def test_move_to_uc_households_by_legacy_benefit_and_move_status(facts):
    """Item 3: DWP's cumulative table, the one policyengine-uk-data#534 draws rates from."""
    built = facts[MTUC]
    cells = {(f.filters["legacy_benefit"], f.filters["move_status"]): f for f in built}
    assert len(cells) == len(built)
    claimed, closed = "Claimed UC", "Did not claim UC - Legacy benefit closed"
    # DWP's all-households row, Stat-Xplore extract of 15 October 2026.
    assert {
        status: cells[("all", status)].value
        for status in (claimed, closed, "In Progress", "all")
    } == {claimed: 1_580_761, closed: 241_662, "In Progress": 538, "all": 1_822_966}
    assert cells[("Housing Benefit only", claimed)].value == 30_900
    assert cells[("Housing Benefit only", closed)].value == 10_121
    assert cells[("Working Tax Credit only", claimed)].value == 53_993
    assert cells[("Working Tax Credit only", closed)].value == 51_805
    rate = cells[("all", claimed)].value / (
        cells[("all", claimed)].value + cells[("all", closed)].value
    )
    assert rate == pytest.approx(0.867, abs=5e-4)

    # 19 combinations by 3 statuses, and DWP's own totals beside them. A published
    # zero is kept; a series zero in every cell is not ported.
    assert Counter(f.layout.table_record_kind for f in built) == {
        "detail": 57,
        "total": 23,
    }
    assert cells[("Child Tax Credit only", "In Progress")].value == 0
    assert not {"Legacy non-customer", "Unknown/Missing"} & {
        value for key in cells for value in key
    }
    for fact in built:
        assert (fact.geography.id, fact.geography.name) == (GB, "Great Britain")
        assert (fact.entity.name, fact.provenance_class) == (
            "household",
            "administrative",
        )
        assert (fact.period.type, fact.period.value) == ("month", "2026-06")
        assert (fact.period_coverage.start_date, fact.period_coverage.end_date) == (
            "2022-07-01",
            "2026-06-30",
        )
        assert fact.source.vintage == "stat_xplore_extracted_2026_10_15"
        assert fact.measure.concept == "dwp.mtuc_households_sent_migration_notice"
        assert fact.measure.concept_evidence_notes.startswith(
            "Official statistics in development."
        )
