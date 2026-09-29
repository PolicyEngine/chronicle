"""Regression tests for the chronicle#302 UK pension packages.

State Pension and Pension Credit caseloads and amounts (Stat-Xplore, February 2023 to
March 2026), Northern Ireland (DfC, May 2026 edition), workplace pensions (DWP savings
trends; ONS ASHE summary and tables P1 to P12), salary sacrifice (OBR costing, HMRC policy
paper, HMRC Tables 6.1/6.2), Winter Fuel Payment (Stat-Xplore and the official statistics,
winters 2023 to 2024 through 2025 to 2026; HMRC's charge note), Attendance Allowance
(Stat-Xplore) and the DWP Spring 2026 forecast tables to 2030-31. Values are the
publishers' as fetched on 2026-09-29.
"""

from __future__ import annotations

import json

import pytest

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import validate_consumer_fact_contract
from chronicle.core import validate_facts
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package
from chronicle.sources.cells import SourceArtifactMetadata
from chronicle.sources.rows import source_rows_from_statxplore_table
from chronicle.suite import _statxplore_age_range

WINDOW = "february-2023-march-2026"
SP_AGE = f"dwp-state-pension-age-gender-type-{WINDOW}"
SP_REGION = f"dwp-state-pension-region-type-gender-{WINDOW}"
SP_CATEGORY = f"dwp-state-pension-category-protected-payment-{WINDOW}"
SP_AMOUNT = f"dwp-state-pension-amount-band-type-{WINDOW}"
PC_TYPE = f"dwp-pension-credit-type-partner-age-{WINDOW}"
PC_REGION = f"dwp-pension-credit-region-type-partner-age-{WINDOW}"
PC_GENDER = f"dwp-pension-credit-gender-type-{WINDOW}"
PC_AMOUNT = f"dwp-pension-credit-amount-band-type-{WINDOW}"
AA = f"dwp-attendance-allowance-entitled-country-award-age-gender-{WINDOW}"
NI_SP = "dfc-ni-state-pension-statistics-may-2026"
NI_PC = "dfc-ni-pension-credit-statistics-may-2026"
SAVINGS = "dwp-workplace-pension-savings-trends-2009-to-2025"
ONS_SUMMARY = "ons-employee-workplace-pensions-summary-2024"
OBR = "obr-salary-sacrifice-costing-february-2026"
HMRC_PAPER = "hmrc-salary-sacrifice-reform-2029-headcounts"
HMRC_RELIEF_2023 = "hmrc-pension-contribution-relief-2023-24"
HMRC_RELIEF_2024 = "hmrc-salary-sacrifice-relief-2024-25"
WFP_CHARGE = "hmrc-winter-fuel-payment-charge-2025"
WFP_STATX_2023 = "dwp-winter-fuel-payment-recipients-winter-2023-24"
WFP_STATX = "dwp-winter-fuel-payment-recipients-winters-2024-25-2025-26"
WFP_ODS = "dwp-winter-fuel-payment-statistics-winter-{}"
FORECAST = "dwp-benefit-expenditure-caseload-spring-2026"

ASHE_GROUPS = ("age", "industry", "occupation", "business-size")
ASHE_MEMBERSHIP = {
    group: f"ons-ashe-pension-membership-by-{group}-earnings-2024"
    for group in ASHE_GROUPS
}
ASHE_BANDS = {
    (payer, group, basis): (
        f"ons-ashe-{payer}-contribution-bands-by-{group}-2024-{basis}"
    )
    for payer in ("employee", "employer")
    for group in ASHE_GROUPS
    for basis in ("full-pay", "qualifying-earnings")
}

# Every package #302 adds or extends, with its fact count.
FACT_COUNTS = {
    SP_AGE: 4879,
    SP_REGION: 2798,
    SP_CATEGORY: 598,
    SP_AMOUNT: 429,
    PC_TYPE: 2194,
    PC_REGION: 22966,
    PC_GENDER: 312,
    PC_AMOUNT: 468,
    AA: 2678,
    NI_SP: 275,
    NI_PC: 236,
    SAVINGS: 936,
    ONS_SUMMARY: 80,
    ASHE_MEMBERSHIP["age"]: 765,
    ASHE_MEMBERSHIP["industry"]: 1490,
    ASHE_MEMBERSHIP["occupation"]: 737,
    ASHE_MEMBERSHIP["business-size"]: 454,
    ASHE_BANDS["employee", "age", "full-pay"]: 723,
    ASHE_BANDS["employee", "age", "qualifying-earnings"]: 606,
    ASHE_BANDS["employee", "industry", "full-pay"]: 1451,
    ASHE_BANDS["employee", "industry", "qualifying-earnings"]: 1232,
    ASHE_BANDS["employee", "occupation", "full-pay"]: 718,
    ASHE_BANDS["employee", "occupation", "qualifying-earnings"]: 620,
    ASHE_BANDS["employee", "business-size", "full-pay"]: 433,
    ASHE_BANDS["employee", "business-size", "qualifying-earnings"]: 378,
    ASHE_BANDS["employer", "age", "full-pay"]: 613,
    ASHE_BANDS["employer", "age", "qualifying-earnings"]: 642,
    ASHE_BANDS["employer", "industry", "full-pay"]: 1208,
    ASHE_BANDS["employer", "industry", "qualifying-earnings"]: 1287,
    ASHE_BANDS["employer", "occupation", "full-pay"]: 606,
    ASHE_BANDS["employer", "occupation", "qualifying-earnings"]: 654,
    ASHE_BANDS["employer", "business-size", "full-pay"]: 355,
    ASHE_BANDS["employer", "business-size", "qualifying-earnings"]: 383,
    OBR: 36,
    HMRC_PAPER: 6,
    HMRC_RELIEF_2023: 85,
    HMRC_RELIEF_2024: 85,
    WFP_CHARGE: 5,
    WFP_STATX_2023: 288,
    WFP_STATX: 348,
    WFP_ODS.format("2023-24"): 192,
    WFP_ODS.format("2024-25"): 154,
    WFP_ODS.format("2025-26"): 66,
    FORECAST: 2674,
}
EXTENDED = {FORECAST, HMRC_PAPER, HMRC_RELIEF_2024}


@pytest.fixture(scope="module")
def built():
    cache = {}

    def facts(alias):
        if alias not in cache:
            cache[alias] = load_source_package(alias).build_facts(2026)
        return cache[alias]

    return facts


def _value(
    facts,
    *,
    period,
    measure_id=None,
    geography=None,
    concept=None,
    exact=False,
    **filters,
):
    # exact=True matches only facts whose filters are exactly the given ones.
    matches = [
        fact
        for fact in facts
        if fact.period.value == period
        and (measure_id is None or fact.layout.measure_id == measure_id)
        and (geography is None or fact.geography.id == geography)
        and (concept is None or fact.measure.concept == concept)
        and all(fact.filters.get(key) == value for key, value in filters.items())
        and (not exact or dict(fact.filters) == filters)
    ]
    assert len(matches) == 1, (period, measure_id, geography, filters, len(matches))
    return matches[0].value


def _period_start(fact):
    value = fact.period.value
    return int(value[:4]) if isinstance(value, str) else int(value)


def test_issue_302_packages_are_registered():
    assert set(FACT_COUNTS) <= set(SOURCE_PACKAGE_ALIASES)
    assert set(FACT_COUNTS) <= set(UK_BUNDLE_SOURCES)
    # The region-by-type cut is superseded by the region, type, partner and age cross.
    assert f"dwp-pension-credit-region-type-{WINDOW}" not in SOURCE_PACKAGE_ALIASES


@pytest.mark.parametrize("alias", sorted(FACT_COUNTS))
def test_issue_302_package_builds_valid_facts_from_2023(alias, built):
    facts = built(alias)

    assert len(facts) == FACT_COUNTS[alias]
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    if alias not in EXTENDED:
        # Every period is 2023 or later: the window runs from 2023 to the latest published.
        assert min(_period_start(fact) for fact in facts) >= 2023


def test_state_pension_march_2026_great_britain_residents(built):
    facts = built(SP_AGE)
    march = dict(period="2026-03", age_bands_and_single_year="all", gender="all")

    # Residents only: 13,307,794 cases in all, of which 1,093,218 live abroad and 7,278
    # have no known address (the three items sum to 5 more: Stat-Xplore perturbs each cell).
    assert (
        _value(facts, measure_id="total_recipients", category_of_pension="all", **march)
        == 12_207_303
    )
    assert (
        _value(
            facts,
            measure_id="total_recipients",
            category_of_pension="Pre-2016 State Pension",
            **march,
        )
        == 7_084_158
    )
    assert (
        _value(
            facts,
            measure_id="total_recipients",
            category_of_pension="New State Pension",
            **march,
        )
        == 5_123_141
    )
    assert _value(
        facts, measure_id="total_mean_weekly_amount", category_of_pension="all", **march
    ) == pytest.approx(221.42, abs=0.005)
    for age, recipients in ((66, 712_988), (67, 710_010), (68, 691_366)):
        assert (
            _value(
                facts,
                period="2026-03",
                measure_id="total_recipients",
                age_bands_and_single_year=age,
                gender="all",
                category_of_pension="all",
            )
            == recipients
        )
    months = {fact.period.value for fact in facts}
    assert min(months) == "2023-02" and max(months) == "2026-03" and len(months) == 13
    assert all(fact.geography.id == "K03000001" for fact in facts)


def test_state_pension_single_year_ages_carry_age_bounds(built):
    fact = next(
        fact
        for fact in built(SP_AGE)
        if fact.filters["age_bands_and_single_year"] == 71
    )
    bounds = {
        (c.variable, c.operator, c.value)
        for c in fact.constraints
        if c.variable == "age"
    }

    assert bounds == {("age", ">=", 71), ("age", "<", 72)}


def test_pension_credit_march_2026_by_type_and_region(built):
    gb = built(PC_TYPE)
    margins = dict(period="2026-03", measure_id="total_claims", partner_indicator="all")

    assert (
        _value(
            gb, type_of_pension_credit="all", age_bands_and_single_year="all", **margins
        )
        == 1_380_846
    )
    assert (
        _value(
            gb,
            type_of_pension_credit="Guarantee Credit only",
            age_bands_and_single_year="all",
            **margins,
        )
        == 832_322
    )
    assert (
        _value(
            gb,
            type_of_pension_credit="Savings Credit only",
            age_bands_and_single_year="all",
            **margins,
        )
        == 150_288
    )
    assert (
        _value(
            gb,
            type_of_pension_credit="Both Guarantee and Savings Credit",
            age_bands_and_single_year="all",
            **margins,
        )
        == 398_237
    )
    assert all(fact.entity.name == "benefit_unit" for fact in gb)

    regional = [
        fact
        for fact in built(PC_REGION)
        if fact.period.value == "2026-03"
        and fact.layout.measure_id == "total_claims"
        and fact.filters["type_of_pension_credit"] == "all"
        and fact.filters["partner_indicator"] == "all"
        and fact.filters["age_bands_and_single_year"] == "all"
    ]
    assert len(regional) == 11
    assert {fact.geography.id for fact in regional} >= {
        "E12000001",
        "W92000004",
        "S92000003",
    }
    assert next(f.value for f in regional if f.geography.id == "E12000001") == 75_173
    # Stat-Xplore perturbs each cell independently, so the regions sum to within a few
    # claims of the Great Britain cell rather than exactly.
    assert abs(sum(fact.value for fact in regional) - 1_380_846) <= 25


def test_northern_ireland_may_2026(built):
    sp = built(NI_SP)
    pc = built(NI_PC)

    # The rolling series' May 2026 point; the age table restates its total.
    may = dict(period="2026-05", exact=True)
    assert _value(sp, measure_id="claimants_all", **may) == 335_540
    assert (
        _value(
            sp,
            measure_id="claimants_new_state_pension",
            category_of_pension="New State Pension",
            **may,
        )
        == 152_970
    )
    assert _value(sp, measure_id="average_weekly_payment_all", **may) == 227.39
    assert _value(pc, measure_id="claimants_all", **may) == 60_030
    assert _value(pc, measure_id="beneficiaries_all", **may) == 68_900
    assert _value(pc, measure_id="average_weekly_payment_all", **may) == 92.88
    assert _value(sp, measure_id="claimants_all", age_band="all", **may) == 335_540
    assert min(fact.period.value for fact in sp + pc) == "2023-02"
    assert all(fact.geography.id == "N92000002" for fact in sp + pc)


def test_workplace_pension_savings_trends_2025(built):
    facts = built(SAVINGS)
    eligible = dict(eligibility="eligible", sector="all", exact=True)
    saved = dict(
        measure_id="annual_saving", saver_population="eligible_savers", sector="all"
    )

    assert _value(
        facts, period=2025, measure_id="participation_rate", **eligible
    ) == pytest.approx(0.90)
    assert (
        _value(facts, period=2025, measure_id="participating_employees", **eligible)
        == 22_610_000
    )
    assert (
        _value(
            facts,
            period=2025,
            measure_id="participating_employees",
            eligibility="all",
            sector="all",
            exact=True,
        )
        == 24_207_000
    )
    for component, amount in (
        ("all", 166.1e9),
        ("employee_contributions", 44.2e9),
        ("employer_contributions", 101.6e9),
        ("tax_relief", 20.3e9),
    ):
        assert _value(
            facts, period=2025, saving_component=component, **saved
        ) == pytest.approx(amount)
    # Every year is restated in 2025 earnings terms, and the concept says so.
    assert _value(facts, period=2023, saving_component="all", **saved) == pytest.approx(
        152.0e9
    )
    assert {fact.period.value for fact in facts} == {2023, 2024, 2025}
    assert all(fact.provenance_class == "survey_aggregate" for fact in facts)


def test_ons_ashe_tables_p1_to_p12(built):
    industry = built(ASHE_MEMBERSHIP["industry"])
    education_db = dict(
        period=2024,
        sic2007_summary_category="all",
        sector="all",
        weekly_earnings_band="all",
        pension_type="defined_benefit",
    )

    assert (
        _value(
            industry,
            measure_id="share_defined_benefit",
            sic2007_section="P",
            **education_db,
        )
        == 73.1
    )
    assert (
        _value(
            industry,
            measure_id="jobs_defined_benefit",
            sic2007_section="P",
            **education_db,
        )
        == 2_901_000
    )
    assert {fact.filters["sic2007_section"] for fact in industry} == set(
        "ABCDEFGHIJKLMNOPQRS"
    ) | {"all"}
    assert {fact.filters["sic2007_summary_category"] for fact in industry} == {
        "all",
        "index_of_production",
        "service_industries",
    }
    assert {
        fact.filters["soc2020_major_group"]
        for fact in built(ASHE_MEMBERSHIP["occupation"])
    } == set(range(1, 10))

    employer = built(ASHE_BANDS["employer", "industry", "full-pay"])
    public = dict(
        period=2024,
        sic2007_section="all",
        sic2007_summary_category="all",
        sector="Public",
        pension_type="all",
        contribution_basis="full_pay",
    )
    assert (
        _value(
            employer,
            measure_id="share_20_and_over",
            employer_contribution_rate_band="20% and over",
            **public,
        )
        == 44.7
    )
    # The employer 0 per cent band is suppressed or [w] in every row of P9 to P12.
    assert "0%" not in {
        fact.filters["employer_contribution_rate_band"] for fact in employer
    }

    # The all-employees rows of P2 to P4 and P6 to P8, P10 to P12 restate P1, P5 and P9
    # cell for cell and are not ported twice.
    group_keys = {
        "sic2007_section",
        "sic2007_summary_category",
        "sector",
        "soc2020_major_group",
        "business_size_band",
    }
    for alias in [*ASHE_MEMBERSHIP.values(), *ASHE_BANDS.values()]:
        if "-by-age-" in alias:
            continue
        assert not [
            fact
            for fact in built(alias)
            if all(
                value == "all"
                for key, value in fact.filters.items()
                if key in group_keys
            )
        ], alias
    assert all(
        fact.entity.name == "person" and fact.entity.role == "employee_job"
        for fact in built(ASHE_MEMBERSHIP["business-size"])
    )


def test_salary_sacrifice_costing_paper_and_relief(built):
    obr = built(OBR)
    for route, first, last in (
        ("salary_sacrifice", 12.9e9, 15.1e9),
        ("bonus_sacrifice", 13.0e9, 14.2e9),
    ):
        for year, amount in ((2027, first), (2030, last)):
            assert _value(
                obr,
                period=year,
                concept="obr.salary_sacrifice_costing.tax_base",
                sacrifice_route=route,
                contribution_portion="above_2000_annual_threshold",
            ) == pytest.approx(amount)
    assert all(fact.assertion == "source_projection" for fact in obr)

    paper = {
        (f.measure.concept, f.period.type, f.period.value): f for f in built(HMRC_PAPER)
    }
    employers = paper["hmrc.salary_sacrifice_pension_employers", "calendar_year", 2025]
    assert employers.value == 290_000 and employers.entity.name == "firm"
    forgone_2023 = paper["hmrc.salary_sacrifice_forgone_nics", "tax_year", 2023]
    forgone_2030 = paper["hmrc.salary_sacrifice_forgone_nics", "tax_year", 2030]
    assert (forgone_2023.value, forgone_2023.assertion) == (5.8e9, "observation")
    assert (forgone_2030.value, forgone_2030.assertion) == (8.0e9, "source_projection")

    relief_2023 = built(HMRC_RELIEF_2023)
    nics = dict(
        period=2023,
        concept="hmrc.pension_contribution_nics_relief",
        contribution_type="Salary sacrificed contributions",
        sector_scheme="all",
        scheme_type="all",
        tax_rate="all",
    )
    # The lost SPP Review's NI-relief pair (GBP 1.2bn / 2.9bn) is Table 6.2's 2023-24 row.
    assert (
        _value(relief_2023, nics_relief_class="Class 1 Primary (employee)", **nics)
        == 1.2e9
    )
    assert (
        _value(relief_2023, nics_relief_class="Class 1 Secondary (employer)", **nics)
        == 2.9e9
    )

    relief_2024 = built(HMRC_RELIEF_2024)
    income_tax = dict(
        period=2024,
        concept="hmrc.pension_contribution_income_tax_relief",
        sector_scheme="all",
        scheme_type="all",
        tax_rate="all",
    )
    assert (
        _value(
            relief_2024,
            contribution_type="Individual contributions to net pay arrangements",
            **income_tax,
        )
        == 7.0e9
    )
    assert (
        _value(
            relief_2024,
            contribution_type="Individual contributions to relief at source schemes",
            **income_tax,
        )
        == 5.9e9
    )


def test_winter_fuel_payment_winter_2025_26(built):
    ods = built(WFP_ODS.format("2025-26"))

    england_and_wales = dict(period=2025, geography="K04000001", exact=True)
    assert _value(ods, measure_id="recipients", **england_and_wales) == 10_872_496
    assert _value(ods, measure_id="beneficiaries", **england_and_wales) == 11_003_237

    statx = built(WFP_STATX)
    totals = {
        fact.geography.id: fact.value
        for fact in statx
        if fact.period.value == 2025
        and fact.layout.measure_id == "total_recipients"
        and all(value == "all" for value in fact.filters.values())
    }
    assert totals == {"E92000001": 10_221_936, "W92000004": 644_326}
    assert {fact.period.value for fact in built(WFP_STATX_2023)} == {2023}

    charge = {fact.filters["charge_recovery_group"]: fact for fact in built(WFP_CHARGE)}
    assert {group: fact.value for group, fact in charge.items()} == {
        "all": 2_200_000,
        "paye_only": 1_300_000,
        "self_assessment": 900_000,
        "self_assessment_with_paye": 800_000,
        "self_employed": 100_000,
    }
    assert all(fact.assertion == "source_projection" for fact in charge.values())


def test_attendance_allowance_by_country(built):
    facts = built(AA)

    def country_totals(month):
        return {
            fact.geography.id: fact.value
            for fact in facts
            if fact.period.value == month
            and all(value == "all" for value in fact.filters.values())
        }

    assert country_totals("2025-08") == {
        "E92000001": 1_611_266,
        "W92000004": 125_031,
        "S92000003": 92_380,
    }
    # Scottish cases fall as they transfer to Pension Age Disability Payment.
    assert country_totals("2026-03")["S92000003"] == 579


def test_dwp_forecast_tables_run_to_2030_31(built):
    facts = built(FORECAST)
    caseload = dict(concept="dwp.benefit_caseload_count")

    assert (
        _value(
            facts,
            period=2025,
            benefit_forecast_line="caseloads_by_benefit__winter_fuel_payments",
            **caseload,
        )
        == 10_891_000
    )
    assert (
        _value(
            facts,
            period=2024,
            benefit_forecast_line="caseloads_by_benefit__winter_fuel_payments",
            **caseload,
        )
        == 1_268_000
    )
    assert (
        _value(
            facts,
            period=2024,
            benefit_forecast_line="caseloads_by_benefit__attendance_allowance",
            **caseload,
        )
        == 1_645_000
    )
    assert (
        _value(
            facts,
            period=2030,
            benefit_forecast_line="caseloads_by_benefit__pension_credit",
            **caseload,
        )
        == 1_133_000
    )
    assert (
        _value(
            facts,
            period=2030,
            benefit_forecast_line="state_pension__total_state_pension_caseload",
            **caseload,
        )
        == 13_697_000
    )
    assert _value(
        facts,
        period=2030,
        concept="dwp.benefit_expenditure_amount",
        benefit_forecast_line="state_pension__total",
    ) == pytest.approx(180.7e9, rel=1e-3)
    assert {fact.period.value for fact in facts} == set(range(2023, 2031))

    # The Notes tab: Scottish cases leave a benefit's lines when executive competence
    # moves to the Scottish Government, so those lines cover England and Wales from then.
    def geography(line, year):
        # a line may carry both an expenditure and a caseload fact in a year
        (geography_id,) = {
            f.geography.id
            for f in facts
            if f.filters["benefit_forecast_line"] == line and f.period.value == year
        }
        return geography_id

    wfp = "caseloads_by_benefit__winter_fuel_payments"
    assert geography(wfp, 2023) == "K03000001"
    assert geography(wfp, 2024) == "K04000001"
    for line in (
        "caseloads_by_benefit__attendance_allowance",
        "caseloads_by_benefit__carer_s_allowance",
        "disability_benefits__personal_independence_payment__in_payment",
    ):
        assert geography(line, 2023) == "K04000001"
    # Lines that mix moved and unmoved benefits, and those paid abroad, keep the frame.
    for line in (
        "caseloads_by_benefit__industrial_injuries_benefits",
        "disability_benefits__total",
        "disability_benefits__disability_living_allowance__outside_uk",
        "caseloads_by_benefit__pension_credit",
    ):
        assert geography(line, 2030) == "K03000001"


def _statxplore_response():
    field = "str:field:SP_New:V_F_SP_CASELOAD_New:SEX"
    return {
        "measures": [
            {
                "uri": "str:count:SP_New:V_F_SP_CASELOAD_New",
                "label": "State Pension Caseload",
            },
            {
                "uri": "str:statfn:SP_New:V_F_SP_CASELOAD_New:CAWKLYAMT:MEAN",
                "label": "Mean of Weekly Amount",
            },
        ],
        "fields": [
            {
                "uri": field,
                "label": "Gender",
                "items": [
                    {"labels": ["Female"], "uris": [f"{field}:C_SP_CCSEX:2"]},
                    {"labels": ["Male"], "uris": [f"{field}:C_SP_CCSEX:1"]},
                ],
            }
        ],
        "cubes": {
            "str:count:SP_New:V_F_SP_CASELOAD_New": {"values": [7, 5]},
            "str:statfn:SP_New:V_F_SP_CASELOAD_New:CAWKLYAMT:MEAN": {
                "values": [210.5, 230.25]
            },
        },
    }


def test_statxplore_parser_unpivots_every_measure_cube():
    content = json.dumps(_statxplore_response()).encode("utf-8")
    artifact = SourceArtifactMetadata(
        source_name="dwp",
        source_table="State Pension caseload",
        source_file="sp.json",
        url=None,
        vintage="test",
        sha256="0" * 64,
        size_bytes=len(content),
        extracted_at="2026-09-29",
        extraction_method="Stat-Xplore table response",
    )

    rows = source_rows_from_statxplore_table(content, artifact, sheet_name="statx")

    assert [
        (
            row.row_number,
            row.values["measure"],
            row.values["gender"],
            row.values["value"],
        )
        for row in rows
    ] == [
        (1, "State Pension Caseload", "Female", 7),
        (2, "State Pension Caseload", "Male", 5),
        (3, "Mean of Weekly Amount", "Female", 210.5),
        (4, "Mean of Weekly Amount", "Male", 230.25),
    ]


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("66", (66, 67)),
        ("65-69", (65, 70)),
        ("65 - 69", (65, 70)),
        ("65–69", (65, 70)),
        ("90 and over", (90, None)),
        ("Under 65", (0, 65)),
        ("Unknown", None),
        ("all", None),
    ],
)
def test_statxplore_age_labels_give_age_bounds(label, expected):
    assert _statxplore_age_range(label) == expected
