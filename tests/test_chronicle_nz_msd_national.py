"""Publisher fidelity for MSD's June 2026 national benefit workbook."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

from chronicle.artifacts import build_r2_key
from chronicle.bundle import _dimension_label_reports, build_bundle_coverage
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
from chronicle.sources import build_source_cell_key, validate_source_cells
from chronicle.suite import build_source_suite

ROOT = Path(__file__).resolve().parents[1]
ALIAS = "msd-benefit-fact-sheets-national-june-2026"
DIRECTORY = Path("msd/benefit_fact_sheets_national_june_2026")
FILENAME = "quarterly-benefit-fact-sheets-national-benefit-tables-june-2026.xlsx"
SHA256 = "90cd8e7c8ff210ca9334eb035dfef3a39abdefe10365e5f7a6ccbd4291248f74"
SOURCE_URL = (
    "https://www.msd.govt.nz/documents/about-msd-and-our-work/"
    "publications-resources/statistics/benefit/2026/" + FILENAME
)
SOURCE_TABLE = "Quarterly Benefit Fact Sheets - National Benefit Tables, June 2026"


@lru_cache
def _package():
    return load_source_package(ROOT / "packages" / DIRECTORY)


@lru_cache
def _cells():
    return _package().build_source_cells(2026)


@lru_cache
def _facts():
    return _package().build_facts(2026, cells=_cells())


@lru_cache
def _records():
    return _package().build_source_records(2026, cells=_cells())


def test_national_alias_and_package_validation():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == DIRECTORY
    report = validate_source_package(ROOT / "packages" / DIRECTORY, year=2026)
    assert report.valid
    assert not report.warnings
    assert report.counts == {
        "record_set_count": 8,
        "row_count": 25,
        "measure_count": 17,
        "source_record_count": 46,
        "source_region_count": 8,
    }


def test_national_receipt_and_immutable_r2_artifact():
    data_dir = ROOT / "db/data" / DIRECTORY
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text())
    entry = manifest["files"][2026]
    content = (data_dir / FILENAME).read_bytes()
    assert manifest["source_id"] == "msd"
    assert manifest["package_id"] == ALIAS
    assert entry["filename"] == FILENAME
    assert entry["source_url"] == SOURCE_URL
    assert entry["sha256"] == hashlib.sha256(content).hexdigest() == SHA256
    assert entry["size_bytes"] == len(content) == 96_100
    assert entry["fetched_at"] == "2026-10-07T19:22:18Z"
    key = build_r2_key(
        source_id="msd",
        package_id=ALIAS,
        year=2026,
        sha256=SHA256,
        filename=FILENAME,
        package_path=ROOT / "packages" / DIRECTORY,
    )
    assert key == f"raw/nz/msd/{ALIAS}/2026/{SHA256}/{FILENAME}"
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }
    assert {f.source.raw_r2_uri for f in _facts()} == {f"r2://ledger-raw/{key}"}


def test_national_entire_workbook_is_preserved_and_facts_are_direct_cells():
    cells = _cells()
    assert len(cells) == 6_052
    assert {c.sheet_name for c in cells} == {
        "Contents and notes",
        "Summary table-current",
        "Summary table - last 5 years",
        "Main benefits - last 5 years",
        "JS - last 5 years",
        "SPS - last 5 years",
        "SLP - last 5 years",
        "Other - last 5 years",
        "Supplementary - last 5 years",
    }
    assert validate_source_cells(cells).valid
    assert len(_facts()) == 46
    assert validate_facts(_facts()).valid
    assert validate_consumer_fact_contract(_facts()).valid
    by_address = {(c.sheet_name, c.address): c for c in cells}
    cell_keys = {build_source_cell_key(c) for c in cells}
    by_record = {r.source_record_id: r for r in _records()}
    for fact in _facts():
        record = by_record[fact.source_record_id]
        selector = record.spec.selector
        assert selector.end_address is None
        assert record.spec.divisor_selector is None
        assert record.spec.value_scale == 1
        assert (
            fact.value == by_address[(selector.sheet_name, selector.address)].raw_value
        )
        assert fact.source_cell_keys
        assert set(fact.source_cell_keys) <= cell_keys
        assert fact.provenance_class == "administrative"
        assert fact.assertion == "observation"
        assert fact.entity.name == "person"
        assert fact.measure.unit == "count"
        assert fact.measure.concept_authority == "msd"
        assert fact.measure.concept_relation == "source_label"
        assert fact.source.source_sha256 == SHA256
        assert fact.source.url == SOURCE_URL


def test_national_every_dimension_and_value_is_labelled():
    assert _dimension_label_reports(ALIAS, consumer_fact_rows(_facts())) == ([], [])
    for fact in _facts():
        assert fact.layout.groupby_dimension_label
        for dimension, value in fact.filters.items():
            assert fact.dimension_labels[dimension]
            assert fact.dimension_value_labels[dimension][str(value)]


def test_national_publisher_period_and_age_status_are_explicit():
    for fact in _facts():
        assert (fact.period.type, fact.period.value) == ("month", "2026-06")
        assert (fact.geography.level, fact.geography.id) == ("country", "NZ")
        assert fact.period_coverage.source_period_label == "Jun-26"
        assert fact.period_coverage.basis == "calendar"
        assert (
            fact.period_coverage.start_date
            == fact.period_coverage.end_date
            == "2026-06-30"
        )
        assert "randomly rounded to base 3" in fact.period_coverage.notes
    notes = next(
        c
        for c in _cells()
        if (c.sheet_name, c.address) == ("Contents and notes", "C17")
    )
    assert notes.raw_value == (
        "Working-age people are aged 18-64 years. This definition reflects the minimum age "
        "of eligibility for most main benefits and the age of qualification for New Zealand Superannuation."
    )
    assert {f.filters.get("msd_main_benefit_age_status") for f in _facts()} == {
        "working_age",
        "non_working_age",
        None,
    }
    # A different bundle build year does not relabel the fixed published quarter.
    assert {
        (f.period.type, f.period.value)
        for f in _package().build_facts(2025, cells=_cells())
    } == {("month", "2026-06")}


def test_national_source_na_age_cells_remain_source_evidence():
    selected = {
        (r.spec.selector.sheet_name, r.spec.selector.address) for r in _records()
    }
    for address in ("J13", "J14", "J15"):
        cell = next(
            c
            for c in _cells()
            if (c.sheet_name, c.address) == ("Summary table-current", address)
        )
        assert cell.raw_value == "N/A"
        assert (cell.sheet_name, cell.address) not in selected
    age_facts = [
        f for f in _facts() if "msd_main_benefit_age_group_source_label" in f.filters
    ]
    assert len(age_facts) == 21
    assert {
        f.filters["msd_main_benefit_age_group_source_label"] for f in age_facts
    } == {
        "18-24 years",
        "25-39 years",
        "40-54 years",
        "55-64 years",
    }


def test_national_accommodation_supplement_exact_publisher_cell():
    fact = next(
        f
        for f in _facts()
        if f.filters.get("msd_supplementary_assistance_type")
        == "accommodation_supplement"
    )
    record = next(r for r in _records() if r.source_record_id == fact.source_record_id)
    assert fact.value == 363_309
    assert (record.spec.selector.sheet_name, record.spec.selector.address) == (
        "Supplementary - last 5 years",
        "W7",
    )
    assert fact.measure.concept == "msd.supplementary_assistance_recipients"
    combined = next(
        f
        for f in _facts()
        if f.filters.get("msd_supplementary_assistance_type")
        == "special_benefit_or_temporary_additional_support"
    )
    assert combined.value == 106_251
    assert combined.dimension_value_labels["msd_supplementary_assistance_type"] == {
        "special_benefit_or_temporary_additional_support": "Special Benefit (SPB) or Temporary Additional Support (TAS)",
    }


def test_national_single_source_coverage():
    coverage = build_bundle_coverage(consumer_fact_rows(_facts()))
    assert coverage["fact_count"] == 46
    assert coverage["counts"]["by_source"] == {"msd": 46}
    assert coverage["counts"]["by_source_table"] == {f"msd:{SOURCE_TABLE}": 46}
    assert coverage["counts"]["by_period"] == {"month:2026-06": 46}
    assert coverage["counts"]["by_entity"] == {"person": 46}
    assert coverage["counts"]["by_geography"] == {"country:NZ": 46}
    assert coverage["duplicates"] == {
        "aggregate_fact_keys": [],
        "semantic_fact_keys": [],
    }


def test_national_build_suite_all_acceptance_checks(tmp_path):
    report = build_source_suite(
        ROOT / "packages" / DIRECTORY, tmp_path / "suite", year=2026
    )
    assert report.valid
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
    assert not report.agent_acceptance.errors
    assert report.source_records.resolved_count == 46
    assert report.source_records.lineage_coverage == 1
    assert report.source_cells.cell_count == 6_052
    assert report.consumer_facts.fact_count == 46
    assert report.agent_acceptance.counts["raw_artifact_count"] == 1
    assert report.agent_acceptance.counts["raw_r2_link_count"] == 1


# Fixed publisher cells: keeping these parameters independent of YAML also
# catches an accidentally removed guard.
@pytest.mark.parametrize(
    ("record_id", "sheet", "address", "published_value"),
    [
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.18-24 years.jobseeker_support_recipients",
            "Summary table-current",
            "D12",
            48045,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.18-24 years.sole_parent_support_recipients",
            "Summary table-current",
            "F12",
            9327,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.18-24 years.supported_living_payment_recipients",
            "Summary table-current",
            "H12",
            9420,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.18-24 years.other_main_benefits_recipients",
            "Summary table-current",
            "L12",
            477,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.18-24 years.all_main_benefits_recipients",
            "Summary table-current",
            "N12",
            68598,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.25-39 years.jobseeker_support_recipients",
            "Summary table-current",
            "D13",
            68376,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.25-39 years.sole_parent_support_recipients",
            "Summary table-current",
            "F13",
            52398,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.25-39 years.supported_living_payment_recipients",
            "Summary table-current",
            "H13",
            24138,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.25-39 years.other_main_benefits_recipients",
            "Summary table-current",
            "L13",
            1317,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.25-39 years.all_main_benefits_recipients",
            "Summary table-current",
            "N13",
            146223,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.40-54 years.jobseeker_support_recipients",
            "Summary table-current",
            "D14",
            57399,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.40-54 years.sole_parent_support_recipients",
            "Summary table-current",
            "F14",
            18522,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.40-54 years.supported_living_payment_recipients",
            "Summary table-current",
            "H14",
            32838,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.40-54 years.other_main_benefits_recipients",
            "Summary table-current",
            "L14",
            834,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.40-54 years.all_main_benefits_recipients",
            "Summary table-current",
            "N14",
            109593,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.55-64 years.jobseeker_support_recipients",
            "Summary table-current",
            "D15",
            44661,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.55-64 years.sole_parent_support_recipients",
            "Summary table-current",
            "F15",
            1011,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.55-64 years.supported_living_payment_recipients",
            "Summary table-current",
            "H15",
            43107,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.55-64 years.other_main_benefits_recipients",
            "Summary table-current",
            "L15",
            501,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_by_benefit_and_age.55-64 years.all_main_benefits_recipients",
            "Summary table-current",
            "N15",
            89277,
        ),
        (
            "msd_benefit_statistics.month2026_06.youth_payment_working_age_by_age.18-24 years.youth_payment_and_young_parent_payment_recipients",
            "Summary table-current",
            "J12",
            1329,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_benefit_totals.working_age.jobseeker_support_recipients",
            "Summary table-current",
            "D24",
            218481,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_benefit_totals.working_age.sole_parent_support_recipients",
            "Summary table-current",
            "F24",
            81255,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_benefit_totals.working_age.supported_living_payment_recipients",
            "Summary table-current",
            "H24",
            109500,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_benefit_totals.working_age.youth_payment_and_young_parent_payment_recipients",
            "Summary table-current",
            "J24",
            1329,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_benefit_totals.working_age.other_main_benefits_recipients",
            "Summary table-current",
            "L24",
            3126,
        ),
        (
            "msd_benefit_statistics.month2026_06.working_age_benefit_totals.working_age.all_main_benefits_recipients",
            "Summary table-current",
            "N24",
            413691,
        ),
        (
            "msd_benefit_statistics.month2026_06.jobseeker_support_subgroups.jobseeker_support_work_ready.recipients",
            "JS - last 5 years",
            "X5",
            120300,
        ),
        (
            "msd_benefit_statistics.month2026_06.jobseeker_support_subgroups.jobseeker_support_health_condition_or_disability.recipients",
            "JS - last 5 years",
            "X6",
            98181,
        ),
        (
            "msd_benefit_statistics.month2026_06.supported_living_payment_subgroups.supported_living_payment_caring.recipients",
            "SLP - last 5 years",
            "X5",
            11400,
        ),
        (
            "msd_benefit_statistics.month2026_06.supported_living_payment_subgroups.supported_living_payment_health_condition_or_disability.recipients",
            "SLP - last 5 years",
            "X6",
            98097,
        ),
        (
            "msd_benefit_statistics.month2026_06.other_working_age_benefits.emergency_benefit.recipients",
            "Other - last 5 years",
            "W5",
            2136,
        ),
        (
            "msd_benefit_statistics.month2026_06.other_working_age_benefits.emergency_maintenance_allowance.recipients",
            "Other - last 5 years",
            "W6",
            924,
        ),
        (
            "msd_benefit_statistics.month2026_06.other_working_age_benefits.jobseeker_support_student_hardship.recipients",
            "Other - last 5 years",
            "W7",
            66,
        ),
        (
            "msd_benefit_statistics.month2026_06.non_working_age_benefits.jobseeker_support.recipients",
            "Other - last 5 years",
            "W16",
            576,
        ),
        (
            "msd_benefit_statistics.month2026_06.non_working_age_benefits.sole_parent_support.recipients",
            "Other - last 5 years",
            "W17",
            9,
        ),
        (
            "msd_benefit_statistics.month2026_06.non_working_age_benefits.supported_living_payment.recipients",
            "Other - last 5 years",
            "W18",
            3576,
        ),
        (
            "msd_benefit_statistics.month2026_06.non_working_age_benefits.emergency_benefit.recipients",
            "Other - last 5 years",
            "W19",
            3309,
        ),
        (
            "msd_benefit_statistics.month2026_06.non_working_age_benefits.emergency_maintenance_allowance.recipients",
            "Other - last 5 years",
            "W20",
            3,
        ),
        (
            "msd_benefit_statistics.month2026_06.non_working_age_benefits.jobseeker_support_student_hardship.recipients",
            "Other - last 5 years",
            "W21",
            0,
        ),
        (
            "msd_benefit_statistics.month2026_06.non_working_age_benefits.widows_benefit_overseas.recipients",
            "Other - last 5 years",
            "W22",
            3,
        ),
        (
            "msd_benefit_statistics.month2026_06.non_working_age_benefits.youth_payment_and_young_parent_payment.recipients",
            "Other - last 5 years",
            "W23",
            1293,
        ),
        (
            "msd_benefit_statistics.month2026_06.non_working_age_benefits.all_main_benefits.recipients",
            "Other - last 5 years",
            "W24",
            8766,
        ),
        (
            "msd_benefit_statistics.month2026_06.national_supplementary_assistance.special_benefit_or_temporary_additional_support.recipients",
            "Supplementary - last 5 years",
            "W5",
            106251,
        ),
        (
            "msd_benefit_statistics.month2026_06.national_supplementary_assistance.disability_allowance.recipients",
            "Supplementary - last 5 years",
            "W6",
            206190,
        ),
        (
            "msd_benefit_statistics.month2026_06.national_supplementary_assistance.accommodation_supplement.recipients",
            "Supplementary - last 5 years",
            "W7",
            363309,
        ),
    ],
)
def test_national_exact_publisher_cells(record_id, sheet, address, published_value):
    fact = next(f for f in _facts() if f.source_record_id == record_id)
    record = next(r for r in _records() if r.source_record_id == record_id)
    assert fact.value == published_value
    assert (record.spec.selector.sheet_name, record.spec.selector.address) == (
        sheet,
        address,
    )
    cell = next(c for c in _cells() if (c.sheet_name, c.address) == (sheet, address))
    assert cell.raw_value == published_value


@pytest.mark.parametrize(
    ("sheet", "address", "message"),
    [
        ("JS - last 5 years", "B2", "table title"),
        ("JS - last 5 years", "B5", "benefit-subgroup axis"),
        ("JS - last 5 years", "C5", "row header"),
        ("JS - last 5 years", "C6", "row header"),
        ("JS - last 5 years", "X4", "column header"),
        ("Other - last 5 years", "B13", "table title"),
        ("Other - last 5 years", "B15", "benefit axis"),
        ("Other - last 5 years", "B16", "row header"),
        ("Other - last 5 years", "B17", "row header"),
        ("Other - last 5 years", "B18", "row header"),
        ("Other - last 5 years", "B19", "row header"),
        ("Other - last 5 years", "B2", "table title"),
        ("Other - last 5 years", "B20", "row header"),
        ("Other - last 5 years", "B21", "row header"),
        ("Other - last 5 years", "B22", "row header"),
        ("Other - last 5 years", "B23", "row header"),
        ("Other - last 5 years", "B24", "row header"),
        ("Other - last 5 years", "B4", "benefit axis"),
        ("Other - last 5 years", "B5", "row header"),
        ("Other - last 5 years", "B6", "row header"),
        ("Other - last 5 years", "B7", "row header"),
        ("Other - last 5 years", "W15", "column header"),
        ("Other - last 5 years", "W4", "column header"),
        ("SLP - last 5 years", "B2", "table title"),
        ("SLP - last 5 years", "B5", "benefit-subgroup axis"),
        ("SLP - last 5 years", "C5", "row header"),
        ("SLP - last 5 years", "C6", "row header"),
        ("SLP - last 5 years", "X4", "column header"),
        ("Summary table-current", "B12", "age-group axis"),
        ("Summary table-current", "B2", "table title"),
        ("Summary table-current", "B24", "row header"),
        ("Summary table-current", "C12", "row header"),
        ("Summary table-current", "C13", "row header"),
        ("Summary table-current", "C14", "row header"),
        ("Summary table-current", "C15", "row header"),
        ("Summary table-current", "D4", "publisher quarter label"),
        ("Summary table-current", "D5", "column header"),
        ("Summary table-current", "D6", "recipient count column"),
        ("Summary table-current", "F5", "column header"),
        ("Summary table-current", "F6", "recipient count column"),
        ("Summary table-current", "H5", "column header"),
        ("Summary table-current", "H6", "recipient count column"),
        ("Summary table-current", "J13", "non-applicable Youth Payment age cell"),
        ("Summary table-current", "J14", "non-applicable Youth Payment age cell"),
        ("Summary table-current", "J15", "non-applicable Youth Payment age cell"),
        ("Summary table-current", "J5", "column header"),
        ("Summary table-current", "J6", "recipient count column"),
        ("Summary table-current", "L5", "column header"),
        ("Summary table-current", "L6", "recipient count column"),
        ("Summary table-current", "N5", "column header"),
        ("Summary table-current", "N6", "recipient count column"),
        ("Supplementary - last 5 years", "B2", "table title"),
        ("Supplementary - last 5 years", "B4", "supplementary-assistance axis"),
        ("Supplementary - last 5 years", "B5", "row header"),
        ("Supplementary - last 5 years", "B6", "row header"),
        ("Supplementary - last 5 years", "B7", "row header"),
        ("Supplementary - last 5 years", "W4", "column header"),
    ],
)
def test_national_each_source_guard_rejects_mutation(sheet, address, message):
    changed = [
        replace(c, raw_value="unexpected publisher layout")
        if (c.sheet_name, c.address) == (sheet, address)
        else c
        for c in _cells()
    ]
    with pytest.raises(ValueError, match=message):
        _package().build_facts(2026, cells=changed)


@pytest.mark.parametrize(
    ("sheet", "address"),
    [
        ("Summary table-current", "D12"),
        ("Summary table-current", "J12"),
        ("Summary table-current", "D24"),
        ("JS - last 5 years", "X5"),
        ("SLP - last 5 years", "X5"),
        ("Other - last 5 years", "W5"),
        ("Other - last 5 years", "W16"),
        ("Supplementary - last 5 years", "W5"),
    ],
)
def test_national_selected_value_types_reject_mutation(sheet, address):
    changed = [
        replace(c, raw_value="S", cell_type="string", display_value="S")
        if (c.sheet_name, c.address) == (sheet, address)
        else c
        for c in _cells()
    ]
    with pytest.raises(ValueError, match="expected cell type"):
        _package().build_facts(2026, cells=changed)
