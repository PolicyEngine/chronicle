"""Publisher-period regressions for the additions to chronicle#313."""

from dataclasses import replace
from functools import cache

import pytest

from chronicle.bundle import _dimension_label_reports
from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import PeriodCoverage, PeriodDimension
from chronicle.source_package import load_source_package
from chronicle.suite import _period_matches_source_row, build_source_suite


@pytest.fixture(scope="module")
def facts_for():
    @cache
    def build(alias):
        package = load_source_package(alias)
        return package.build_facts(package.artifact.artifact_year)

    return build


@pytest.mark.parametrize(
    "alias,year,count",
    [
        ("ons-mye-2025-uk", 2025, 4416),
        ("ons-mye-2024-uk-revised-2026", 2025, 16),
        ("lps-housing-stock-lgd-2026", 2026, 72),
        ("slc-student-loan-repayments-england-2026", 2026, 8),
        ("slc-student-support-england-2025-provisional-2025-26", 2025, 136),
        ("ons-public-sector-employment-june-2026", 2026, 24),
        ("ons-national-balance-sheet-land-preliminary-2026", 2026, 3),
        ("dfi-ni-public-transport-statistics-2025-26", 2026, 14),
        ("isc-annual-census-2025", 2025, 1),
        ("isc-annual-census-2026", 2026, 1),
        ("welshgov-dwelling-stock-by-tenure-2025", 2025, 150),
        ("scotgov-dwelling-stock-by-tenure-2024", 2024, 192),
    ],
)
def test_latest_comment_inputs_have_valid_source_cells_and_contracts(
    tmp_path, facts_for, alias, year, count
):
    """Check guards, raw-fact boundary, contracts and DB lineage end to end."""
    contract = validate_consumer_fact_contract(facts_for(alias))
    assert contract.valid, contract.to_dict()
    report = build_source_suite(alias, tmp_path / alias, year=year)
    assert report.agent_acceptance.valid, report.agent_acceptance.to_dict()
    assert report.valid, report.to_dict()
    assert report.consumer_facts.fact_count == count
    assert report.facts.fact_count == count
    assert report.source_records.lineaged_count == count


def test_mid2025_higher_geographies_and_sexes_keep_the_revised_vintage(facts_for):
    facts = facts_for("ons-mye-2025-uk")
    assert len({f.geography.id for f in facts}) == 16
    assert {f.period.value for f in facts} == {2025}
    assert {f.filters.get("sex") for f in facts} == {None, "female", "male"}
    assert len({f.filters.get("age") for f in facts}) == 92
    # MYE2 - Persons!D9 and MYE3!D9, 1 October 2026 publisher edition.
    total = next(f for f in facts if f.geography.id == "K02000001" and not f.filters)
    assert total.value == 69_483_939
    assert total.period_coverage.end_date == "2025-06-30"
    revised = facts_for("ons-mye-2024-uk-revised-2026")
    uk = next(f for f in revised if f.geography.id == "K02000001")
    assert uk.value == 69_256_274
    assert uk.period.value == 2024
    assert uk.period_coverage.end_date == "2024-06-30"
    assert uk.source.vintage != "mid_2024"


def test_lps_roll_forward_inputs_are_six_published_april_snapshots(facts_for):
    facts = facts_for("lps-housing-stock-lgd-2026")
    assert len(facts) == 12 * 6
    assert {f.period.value for f in facts} == set(range(2021, 2027))
    assert all(f.entity.name == "dwelling" for f in facts)
    assert all(f.period_coverage.end_date == f"{f.period.value}-04-01" for f in facts)


def test_slc_repayments_are_posted_fiscal_year_flows(facts_for):
    facts = facts_for("slc-student-loan-repayments-england-2026")
    assert len(facts) == 8  # Seven plan columns plus the publisher's HE total.
    assert {f.period.type for f in facts} == {"fiscal_year"}
    assert {f.period.value for f in facts} == {2025}
    assert all(f.period_coverage.end_date == "2026-03-31" for f in facts)
    assert all(f.measure.unit == "gbp" for f in facts)
    # Footnote 24 labels Tables 4A/4B provisional, not Table 1A repayments.
    assert all("publication_status" not in f.filters for f in facts)


def test_slc_provisional_support_keeps_early_year_basis_and_different_totals(facts_for):
    facts = facts_for("slc-student-support-england-2025-provisional-2025-26")
    assert {f.period.type for f in facts} == {"academic_year"}
    assert {f.period.value for f in facts} == {2025}
    assert all(f.period_coverage.end_date == "2025-10-31" for f in facts)
    assert all(f.provenance_class == "administrative" for f in facts)
    assert all(f.filters["publication_status"] == "provisional" for f in facts)
    counts = {
        f.filters["early_year_award_line"]: f.value
        for f in facts
        if f.measure.unit == "count"
    }
    # Table 7C(i)!R24 versus 7C(ii)!M40. The latter excludes postgraduate DSA.
    assert counts["summary_grand_total_10_33_35"] == pytest.approx(1_185_010)
    assert counts["new_returning_grand_total_10_31_33_35"] == pytest.approx(1_185_022)
    averages = [f for f in facts if f.aggregation.method == "mean"]
    assert averages
    assert all(f.measure.unit == "gbp" for f in averages)


def test_slc_returning_support_keeps_both_publisher_footnote_spellings(facts_for):
    alias = "slc-student-support-england-2025-provisional-2025-26"
    facts = facts_for(alias)
    axis = "early_year_award_line"
    line = "new_returning_total_returning_31_33_35"
    returning = {f.aggregation.method: f for f in facts if f.filters[axis] == line}
    # Table 7C(ii)!B75 and B111 contain different literal footnote spellings.
    labels = {
        "sum": "Total returning [31][33][35]",
        "mean": "Total returning [31[[33][35]",
    }
    assert set(returning) == set(labels)
    for method, label in labels.items():
        fact = returning[method]
        assert fact.layout.groupby_value_label == label
        assert fact.dimension_value_labels[axis][line] == label

    errors, warnings = _dimension_label_reports(alias, consumer_fact_rows(facts))
    assert not errors, [error.to_dict() for error in errors]
    assert [(warning.code, warning.key) for warning in warnings] == [
        ("conflicting_groupby_value_label", f"{axis}={line}")
    ]


def test_public_sector_employment_keeps_four_published_quarters(facts_for):
    facts = facts_for("ons-public-sector-employment-june-2026")
    assert {f.period.value for f in facts} == {
        "2025-03",
        "2025-06",
        "2025-09",
        "2025-12",
    }
    assert len({f.measure.concept for f in facts}) == 6
    assert all(f.measure.unit == "count" for f in facts)
    assert all("seasonally adjusted" in f.measure.concept_evidence_notes for f in facts)
    civil = [f for f in facts if f.measure.concept == "ons.pse_headcount_civil_service"]
    assert all(
        "excludes Northern Ireland" in f.measure.concept_evidence_notes for f in civil
    )


def test_preliminary_land_is_a_publisher_sector_stock(facts_for):
    facts = facts_for("ons-national-balance-sheet-land-preliminary-2026")
    # End-2025 land AN.211, Tables 2/3/11!47; GBP million scaled to GBP.
    assert {f.entity.role: f.value for f in facts} == {
        "total_economy": 6_872_455_000_000,
        "households": 4_485_171_000_000,
        "non_financial_corporations": 2_063_534_000_000,
    }
    assert all(f.filters["publication_status"] == "preliminary" for f in facts)
    assert all(f.period_coverage.end_date == "2025-12-31" for f in facts)


def test_ni_bus_receipts_keep_rounded_source_values(facts_for):
    facts = facts_for("dfi-ni-public-transport-statistics-2025-26")
    latest = {f.filters["service"]: f for f in facts if f.period.value == 2025}
    # Journeys!H119/H120 are receipts in GBP million, not passenger journeys.
    assert latest["ulsterbus"].value == 103_500_000
    assert latest["metro_glider"].value == 49_000_000
    assert all(f.period.type == "fiscal_year" for f in facts)
    assert all(f.measure.unit == "gbp" for f in facts)
    assert all(f.period_coverage.end_date == "2026-03-31" for f in latest.values())


@pytest.mark.parametrize("year,total", [(2025, 545_640), (2026, 526_611)])
def test_isc_pupil_total_keeps_january_and_membership_scope(facts_for, year, total):
    (fact,) = facts_for(f"isc-annual-census-{year}")
    assert fact.value == total  # Publisher PDF executive summary.
    assert fact.period.value == f"{year}-01"
    census_day = "2025-01-16" if year == 2025 else "2026-01-15"
    assert fact.period_coverage.start_date == census_day
    assert fact.period_coverage.end_date == census_day
    assert fact.filters["school_membership"] == "isc"
    # PDF extraction supplies page/text/number cell lineage, rather than CSV rows.
    assert len(fact.source_cell_keys) == 4
    assert fact.source_record_id


def test_welsh_tenure_stocks_preserve_provisional_and_absent_rows(facts_for):
    facts = facts_for("welshgov-dwelling-stock-by-tenure-2025")
    wales = {f.filters["Tenure"]: f for f in facts if f.geography.id == "W92000004"}
    assert wales["All tenures"].value == 1_487_200
    assert wales["Owner occupied"].value == 1_061_000
    assert wales["Privately rented"].value == 184_900
    assert wales["Owner occupied"].filters["publication_status"] == "provisional"
    assert wales["Privately rented"].filters["publication_status"] == "provisional"
    local_authority = [f for f in facts if f.filters["Tenure"] == "Local Authority"]
    assert len(local_authority) == 12  # Wales and 11 LAs have source rows.
    assert not any(f.geography.id == "W06000003" for f in local_authority)  # Conwy.
    assert all(f.period_coverage.end_date == "2025-03-31" for f in facts)
    assert all(f.entity.name == "dwelling" for f in facts)


@pytest.mark.parametrize("source_date", ["31/03/2025", "2025-03-31"])
def test_source_snapshot_date_requires_the_recorded_day(facts_for, source_date):
    fact = facts_for("welshgov-dwelling-stock-by-tenure-2025")[0]
    assert _period_matches_source_row(fact, source_date)


@pytest.mark.parametrize(
    "source_date,period,coverage",
    [
        ("31/02/2025", PeriodDimension("calendar_year", 2025), "point"),
        ("30/03/2025", PeriodDimension("calendar_year", 2025), "point"),
        ("31/03/2024", PeriodDimension("calendar_year", 2025), "point"),
        ("2025-02-31", PeriodDimension("calendar_year", 2025), "point"),
        ("31/03/2025", PeriodDimension("calendar_year", 2024), "point"),
        ("31/03/2025", PeriodDimension("fiscal_year", 2025), "point"),
        ("31/03/2025", PeriodDimension("month", "2025-03"), "point"),
        ("31/03/2025", PeriodDimension("calendar_year", 2025), "span"),
        ("31/03/2025", PeriodDimension("calendar_year", 2025), None),
    ],
)
def test_source_snapshot_date_rejects_inexact_period_evidence(
    facts_for, source_date, period, coverage
):
    fact = facts_for("welshgov-dwelling-stock-by-tenure-2025")[0]
    if coverage == "point":
        period_coverage = fact.period_coverage
    elif coverage == "span":
        period_coverage = PeriodCoverage("2025-01-01", "2025-12-31", "calendar")
    else:
        period_coverage = None
    fact = replace(fact, period=period, period_coverage=period_coverage)
    assert not _period_matches_source_row(fact, source_date)


def test_scottish_tenure_stocks_keep_2024_and_source_fractions(facts_for):
    facts = facts_for("scotgov-dwelling-stock-by-tenure-2024")
    national = {
        f.filters["dwelling_stock_tenure"]: f
        for f in facts
        if f.geography.id == "S92000003"
    }
    assert national["all_dwellings"].value == 2_731_099
    assert any(f.value != int(f.value) for f in facts)
    assert all(f.period.value == 2024 for f in facts)
    assert all(f.period_coverage.end_date == "2024-03-31" for f in facts)
    assert all(f.entity.name == "dwelling" for f in facts)
    # Six non-applicable LA ownership cells are absent, rather than numeric zero.
    assert (
        sum(
            f.filters["dwelling_stock_tenure"]
            == "local_authorities_new_towns_scottish_homes"
            for f in facts
        )
        == 27
    )
