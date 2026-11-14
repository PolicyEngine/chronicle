"""Federal Student Aid (FSA) Data Center federal student loan portfolio packages.

Six packages read the six portfolio workbooks FSA published on studentaid.gov
(fetched 12 October 2026; the files carry Last-Modified 8 October 2026). Each
emits the published levels of the FY2026 quarters in its file: dollars
outstanding ($ billions) and recipient or borrower counts (millions, or
thousands for the location table), scaled to dollars and persons. The tests pin
headline values, compare every fact against an independent ``xlrd`` read of
its cell, and check the quirks the packages keep as published: the location
table's "Other" and "Not Reported" rows, the repayment-plan NA markers, and the
recipient versus borrower counts (PolicyEngine/chronicle#310).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import xlrd
import yaml

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

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_YEAR = 2026

PACKAGES = {
    "ed-fsa-portfolio-summary-fy2026-q3": (
        "ed_fsa/portfolio_summary_fy2026_q3",
        "PortfolioSummary.xls",
        "11606d4b93ceea969fcae0f790f3a4e1c2999b62050559ce89bdc269810a62ee",
        {"record_set_count": 9, "row_count": 24, "source_record_count": 24},
    ),
    "ed-fsa-portfolio-by-location-fy2026-q2": (
        "ed_fsa/portfolio_by_location_fy2026_q2",
        "Portfolio-by-Location.xls",
        "d9e8608a82fa1e130c6a80bc5870d25d6f47c626ed200bd33b8f45a43e262dba",
        {"record_set_count": 1, "row_count": 54, "source_record_count": 108},
    ),
    "ed-fsa-portfolio-by-age-fy2026-q2": (
        "ed_fsa/portfolio_by_age_fy2026_q2",
        "Portfolio-by-Age.xls",
        "c2027d277bb88e31c5a8c0f8fc6d81422f45d60e0306f79e63a0c25c7286e2ef",
        {"record_set_count": 4, "row_count": 24, "source_record_count": 24},
    ),
    "ed-fsa-portfolio-by-debt-size-fy2026-q2": (
        "ed_fsa/portfolio_by_debt_size_fy2026_q2",
        "Portfolio-by-Debt-Size.xls",
        "881bd8bbd257da5f5b906b0f0923cf246de6e3d28ee35e8be1cd23d841e88a4d",
        {"record_set_count": 4, "row_count": 36, "source_record_count": 36},
    ),
    "ed-fsa-portfolio-by-loan-type-fy2026-q3": (
        "ed_fsa/portfolio_by_loan_type_fy2026_q3",
        "PortfoliobyLoanType.xls",
        "e64e9d2945dfe703d42d383a7f65fbd4b044d134565ea77a0bd194f366becd33",
        {"record_set_count": 12, "row_count": 42, "source_record_count": 42},
    ),
    "ed-fsa-dl-portfolio-by-repayment-plan-fy2026-q3": (
        "ed_fsa/dl_portfolio_by_repayment_plan_fy2026_q3",
        "DLPortfoliobyRepaymentPlan.xls",
        "5cea1958115574270c825ccc34dd656658d58bff6e439a21fb1f3aafe7bf3ca0",
        {"record_set_count": 36, "row_count": 227, "source_record_count": 227},
    ),
}
FACT_TOTAL = 461
MONTH_END = {"2025-12": "2025-12-31", "2026-03": "2026-03-31", "2026-06": "2026-06-30"}


def _facts(alias: str) -> dict:
    package = load_source_package(alias)
    return {fact.source_record_id: fact for fact in package.build_facts(BUILD_YEAR)}


def _cell(book: xlrd.Book, sheet: str, address: str):
    column = "".join(ch for ch in address if ch.isalpha())
    row = int("".join(ch for ch in address if ch.isdigit()))
    index = 0
    for ch in column:
        index = index * 26 + ord(ch) - 64
    return book.sheet_by_name(sheet).cell(row - 1, index - 1)


@pytest.mark.parametrize("alias", sorted(PACKAGES))
def test_alias_validates_with_pinned_counts(alias):
    path, _filename, _sha256, counts = PACKAGES[alias]
    assert SOURCE_PACKAGE_ALIASES[alias] == Path(path)

    report = validate_source_package(alias, year=BUILD_YEAR)

    assert report.valid, report.errors
    assert {key: report.counts[key] for key in counts} == counts


@pytest.mark.parametrize("alias", sorted(PACKAGES))
def test_every_fact_is_its_published_cell_times_the_declared_scale(alias):
    """Source-cell preservation against an independent read of the workbook."""
    path, filename, sha256, counts = PACKAGES[alias]
    package = load_source_package(alias)
    cells = package.build_source_cells(BUILD_YEAR)
    records = package.build_source_records(BUILD_YEAR, cells=cells)
    facts = {fact.source_record_id: fact for fact in package.build_facts(BUILD_YEAR)}
    book = xlrd.open_workbook(str(REPO_ROOT / "db" / "data" / path / filename))
    specs = {
        spec.source_record_id: spec
        for spec in package.build_source_record_specs(BUILD_YEAR)
    }

    assert validate_source_cells(cells).valid
    assert validate_facts(list(facts.values())).valid
    # The whole workbook is parsed, every sheet and every used cell.
    assert len(cells) == sum(sheet.nrows * sheet.ncols for sheet in book.sheets())
    assert len(facts) == len(records) == counts["source_record_count"]
    for record_id, fact in facts.items():
        spec = specs[record_id]
        cell = _cell(book, spec.selector.sheet_name, spec.selector.address)
        assert cell.ctype == xlrd.XL_CELL_NUMBER, record_id
        expected = Decimal(repr(cell.value)) * Decimal(spec.value_scale)
        assert expected == expected.to_integral_value(), record_id
        assert fact.value == int(expected), record_id
        assert isinstance(fact.value, int)
        assert fact.source.source_sha256 == sha256
        assert fact.source.source_file == filename
        assert fact.source.url == (
            "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/"
            + filename
        )
        assert fact.source.raw_r2_uri == (
            f"r2://ledger-raw/raw/ed_fsa/{alias}/{BUILD_YEAR}/{sha256}/{filename}"
        )
        assert fact.provenance_class == "administrative"
        assert fact.assertion == "observation"
        assert fact.period.type == "month"
        assert fact.period_coverage.start_date == MONTH_END[fact.period.value]
        assert fact.period_coverage.end_date == MONTH_END[fact.period.value]
        assert fact.domain == "federal_student_loans"
        assert fact.entity.name == "person"
        # Constraints use source-neutral variables (the consumer contract
        # rejects variables in the ed_fsa namespace).
        assert not any(item.variable.startswith("ed_fsa") for item in fact.constraints)
        if fact.layout.table_record_kind != "total":
            assert fact.constraints, record_id


def test_portfolio_summary_latest_quarter_matches_the_published_totals():
    facts = _facts("ed-fsa-portfolio-summary-fy2026-q3")
    prefix = "ed_fsa.portfolio_summary.fy2026_q3"

    total = facts[f"{prefix}.dollars_outstanding.all.dollars_outstanding"]
    assert total.value == 1_724_500_000_000
    assert total.period.value == "2026-06"
    assert total.period_coverage.source_period_label == "Federal Fiscal Year 2026 Q3"
    assert total.constraints == ()
    assert (
        facts[f"{prefix}.unduplicated_recipients.all.unduplicated_recipients"].value
        == 42_300_000
    )
    assert (
        facts[f"{prefix}.dollars_outstanding.direct_loans.dollars_outstanding"].value
        == 1_564_800_000_000
    )
    assert facts[f"{prefix}.recipients.ffel.recipients"].value == 6_400_000
    # Chronicle stores the printed Total cell, not a sum. In this release the
    # parts happen to add to it exactly (footnote 1 warns they need not).
    parts = sum(
        facts[f"{prefix}.dollars_outstanding.{program}.dollars_outstanding"].value
        for program in ("direct_loans", "ffel", "perkins")
    )
    assert parts == 1_724_500_000_000
    assert {fact.entity.role for fact in facts.values()} == {
        "federal_student_loan_recipient"
    }
    assert {fact.period.value for fact in facts.values()} == {
        "2025-12",
        "2026-03",
        "2026-06",
    }


def test_location_keeps_other_and_not_reported_as_statistical_scopes():
    facts = _facts("ed-fsa-portfolio-by-location-fy2026-q2")
    prefix = "ed_fsa.portfolio_by_location.2026_03_31"

    assert len(facts) == 108
    assert {fact.period.value for fact in facts.values()} == {"2026-03"}
    not_reported = facts[f"{prefix}.not_reported.dollars_outstanding"]
    assert not_reported.value == 52_200_000_000
    assert not_reported.geography.id == "ed_fsa:location_not_reported"
    assert not_reported.geography.level == "statistical_scope"
    assert not_reported.geography.name == "Not Reported"
    assert facts[f"{prefix}.not_reported.borrowers"].value == 1_953_300
    other = facts[f"{prefix}.other.borrowers"]
    assert other.value == 96_500
    assert other.geography.id == "ed_fsa:location_other"
    california = facts[f"{prefix}.ca.dollars_outstanding"]
    assert california.value == 156_700_000_000
    assert california.geography.id == "0400000US06"
    assert facts[f"{prefix}.ca.borrowers"].value == 3_919_500
    assert facts[f"{prefix}.pr.dollars_outstanding"].geography.id == "0400000US72"
    states = {
        fact.geography.id for fact in facts.values() if fact.geography.level == "state"
    }
    assert len(states) == 52  # 50 states, DC and Puerto Rico
    assert {fact.entity.role for fact in facts.values()} == {
        "federal_student_loan_borrower"
    }
    assert facts[
        f"{prefix}.ca.dollars_outstanding"
    ].period_coverage.source_period_label == ("Data as of Mar. 31, 2026")


def test_age_bands_carry_age_bounds_and_not_reported_has_none():
    facts = _facts("ed-fsa-portfolio-by-age-fy2026-q2")
    prefix = "ed_fsa.portfolio_by_age.fy2026_q2"

    def bounds(value_id: str, measure: str) -> set:
        fact = facts[f"{prefix}.{measure}.{value_id}.{measure}"]
        return {(c.variable, c.operator, c.value) for c in fact.constraints}

    assert bounds("age_24_and_younger", "borrowers") == {("age", "<", 25)}
    assert bounds("age_25_to_34", "dollars_outstanding") == {
        ("age", ">=", 25),
        ("age", "<", 35),
    }
    assert bounds("age_62_and_older", "borrowers") == {("age", ">=", 62)}
    assert bounds("age_not_reported", "borrowers") == {
        ("age_reporting_status", "==", "not_reported")
    }
    assert (
        facts[f"{prefix}.dollars_outstanding.age_35_to_49.dollars_outstanding"].value
        == 685_100_000_000
    )
    assert facts[f"{prefix}.borrowers.age_25_to_34.borrowers"].value == 14_000_000


def test_debt_size_bands_follow_the_definitions_sheet_bounds():
    facts = _facts("ed-fsa-portfolio-by-debt-size-fy2026-q2")
    prefix = "ed_fsa.portfolio_by_debt_size.fy2026_q2"
    lowest = facts[f"{prefix}.borrowers.debt_less_than_5k.borrowers"]
    highest = facts[f"{prefix}.dollars_outstanding.debt_200k_plus.dollars_outstanding"]
    middle = facts[f"{prefix}.borrowers.debt_80k_to_100k.borrowers"]

    assert lowest.value == 6_900_000
    assert {(c.variable, c.operator, c.value) for c in lowest.constraints} == {
        ("federal_student_loan_balance", "<", 5_000)
    }
    assert highest.value == 355_800_000_000
    assert {(c.variable, c.operator, c.value) for c in highest.constraints} == {
        ("federal_student_loan_balance", ">=", 200_000)
    }
    assert {(c.variable, c.operator, c.value) for c in middle.constraints} == {
        ("federal_student_loan_balance", ">=", 80_000),
        ("federal_student_loan_balance", "<", 100_000),
    }


def test_loan_type_keeps_stafford_combined_unique_count_apart():
    facts = _facts("ed-fsa-portfolio-by-loan-type-fy2026-q3")
    prefix = "ed_fsa.portfolio_by_loan_type.fy2026_q3"

    assert (
        facts[f"{prefix}.dollars_outstanding.parent_plus.dollars_outstanding"].value
        == 115_000_000_000
    )
    assert facts[f"{prefix}.recipients.parent_plus.recipients"].value == 3_500_000
    unique = facts[
        f"{prefix}.stafford_combined_unique_recipients.stafford_combined."
        "stafford_combined_unique_recipients"
    ]
    assert unique.value == 34_800_000
    assert unique.measure.concept == "ed_fsa.unduplicated_recipient_count"
    assert unique.layout.table_record_kind == "subtotal"
    assert {(c.variable, c.value) for c in unique.constraints} == {
        ("federal_student_loan_type_group", "stafford")
    }
    # Loan-level recipient counts are not a partition of persons.
    loan_level = facts[f"{prefix}.recipients.stafford_subsidized.recipients"]
    assert loan_level.measure.concept == "ed_fsa.recipient_count"
    assert "counted multiple times" in loan_level.measure.concept_evidence_notes


def test_repayment_plan_na_markers_emit_no_fact_and_are_guarded():
    package = load_source_package("ed-fsa-dl-portfolio-by-repayment-plan-fy2026-q3")
    facts = {fact.source_record_id: fact for fact in package.build_facts(BUILD_YEAR)}
    records = {
        record.source_record_id: record
        for record in package.build_source_records(BUILD_YEAR)
    }

    for quarter in ("q1", "q2", "q3"):
        dl = f"ed_fsa.dl_by_repayment_plan.fy2026_{quarter}"
        assert f"{dl}.recipients.other.recipients" not in facts
        assert f"{dl}.dollars_outstanding.other.dollars_outstanding" in facts
        ffel = f"ed_fsa.ed_held_ffel_by_repayment_plan.fy2026_{quarter}"
        assert f"{ffel}.recipients.other.recipients" not in facts
    # The federally managed "Other" recipients cell reads NA** in Q1 and 0.09
    # (millions) in Q2 and Q3.
    fed = "ed_fsa.federally_managed_by_repayment_plan"
    assert f"{fed}.fy2026_q1.recipients.other.recipients" not in facts
    assert facts[f"{fed}.fy2026_q3.recipients.other.recipients"].value == 90_000
    # The marker cell is lineage of the matching dollars fact.
    dollars_other = records[
        "ed_fsa.dl_by_repayment_plan.fy2026_q3.dollars_outstanding.other."
        "dollars_outstanding"
    ]
    assert "V60" in dollars_other.source_cell_addresses


def test_repayment_plan_latest_quarter_has_no_rap_and_keeps_portfolios_apart():
    facts = _facts("ed-fsa-dl-portfolio-by-repayment-plan-fy2026-q3")
    q3 = [fact for fact in facts.values() if fact.period.value == "2026-06"]

    plans = {
        constraint.value
        for fact in q3
        for constraint in fact.constraints
        if constraint.variable == "federal_student_loan_repayment_plan"
    }
    assert "save" in plans
    assert not any("rap" in plan or "assistance" in plan for plan in plans)
    portfolios = {
        constraint.value
        for fact in facts.values()
        for constraint in fact.constraints
        if constraint.variable == "federal_student_loan_portfolio"
    }
    assert portfolios == {"direct_loan", "ed_held_ffel", "federally_managed"}
    assert all(
        ("federal_student_loan_status_group", "repayment_deferment_forbearance")
        in {(c.variable, c.value) for c in fact.constraints}
        for fact in facts.values()
    )
    save = facts[
        "ed_fsa.dl_by_repayment_plan.fy2026_q3.dollars_outstanding.save."
        "dollars_outstanding"
    ]
    assert save.value == 354_300_000_000
    assert (
        facts["ed_fsa.dl_by_repayment_plan.fy2026_q3.recipients.save.recipients"].value
        == 6_520_000
    )


def test_consumer_rows_validate_and_keys_are_unique():
    facts = [
        fact
        for alias in sorted(PACKAGES)
        for fact in load_source_package(alias).build_facts(BUILD_YEAR)
    ]

    assert len(facts) == FACT_TOTAL
    assert validate_consumer_fact_contract(facts).valid
    rows = consumer_fact_rows(facts)
    assert len({row["aggregate_fact_key"] for row in rows}) == FACT_TOTAL
    assert len({row["semantic_fact_key"] for row in rows}) == FACT_TOTAL
    assert {row["source"]["source_name"] for row in rows} == {"ed_fsa"}


@pytest.mark.parametrize("alias", sorted(PACKAGES))
def test_other_years_have_no_artifact(alias):
    package = load_source_package(alias)

    with pytest.raises(ValueError, match="No source artifact for year 2025"):
        package.build_facts(2025)


def test_a_guard_on_the_location_data_date_binds(tmp_path):
    source = (
        REPO_ROOT / "packages" / PACKAGES["ed-fsa-portfolio-by-location-fy2026-q2"][0]
    )
    payload = yaml.safe_load((source / "source_package.yaml").read_text("utf-8"))
    for guard in payload["record_sets"][0]["rows"][0]["guard_cells"]:
        if guard.get("row") == 4:
            guard["expected_value"] = "Data as of Dec. 31, 2025"
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    (package_dir / "source_package.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Data as of Dec. 31, 2025"):
        load_source_package(package_dir).build_facts(BUILD_YEAR)


def test_a_selector_moved_to_the_previous_quarter_is_refused(tmp_path):
    source = REPO_ROOT / "packages" / PACKAGES["ed-fsa-portfolio-summary-fy2026-q3"][0]
    payload = yaml.safe_load((source / "source_package.yaml").read_text("utf-8"))
    latest = [
        record_set
        for record_set in payload["record_sets"]
        if record_set["record_set_id"].startswith("ed_fsa.portfolio_summary.fy2026_q3")
    ]
    latest[0]["rows"][0]["row_number"] = 66
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    (package_dir / "source_package.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="expected row header 'Q3', got 'Q2'"):
        load_source_package(package_dir).build_facts(BUILD_YEAR)
