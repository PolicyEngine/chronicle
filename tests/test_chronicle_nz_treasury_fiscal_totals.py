"""Publisher-fidelity tests for Treasury's AN24-01 fiscal totals."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

from chronicle.artifacts import build_r2_key
from chronicle.bundle import (
    _dimension_label_reports,
    build_bundle,
    build_bundle_coverage,
)
from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    ArtifactYearRestampError,
    load_source_package,
    validate_source_package,
)
from chronicle.sources.cells import build_source_cell_key, validate_source_cells
from chronicle.sources.rows import build_source_row_key, validate_source_rows
from chronicle.suite import build_source_suite, validate_source_record_specs

REPO_ROOT = Path(__file__).resolve().parents[1]
ALIAS = "treasury-an24-01-fiscal-totals"
DIRECTORY = Path("treasury/an24_01_fiscal_totals")
PACKAGE_PATH = REPO_ROOT / "packages" / DIRECTORY
DATA_PATH = REPO_ROOT / "db" / "data" / DIRECTORY
COMMIT = "6e840d54b67bb7f34c63b9d34897e234317445c3"
RAW_BASE = (
    "https://raw.githubusercontent.com/Treasury-Analytics-and-Insights/"
    f"analytical-note-24-01-effects-of-taxes-and-benefits/{COMMIT}"
)
SOURCE_URL = f"{RAW_BASE}/data/fiscal_totals.csv"
CSV_SHA256 = "beeff2ddd166229ce2e1650b06a75af7e0cc9ed59c3652c2844ea210d51f8dfa"
LICENSE_SHA256 = "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499"
TABLE = "AN24-01 fiscal totals, TY2019"
SHEET = "fiscal_totals"
QUANTITY_DIMENSION = "treasury.an24_01.quantity"
PUBLISHED_ROWS = (
    ("acc_earners_levy", "ACC earners' levy", 1_710_000_000),
    ("accommodation_supplement", "Accommodation Supplement", 1_531_000_000),
    ("alcohol_excise", "Alcohol excise", 545_008_000),
    ("best_start_tax_credit", "Best Start tax credit", 48_610_000),
    ("early_childhood_education", "Early childhood education", 1_883_000_000),
    ("family_tax_credit", "Family tax credit", 2_007_807_000),
    ("gst", "GST", 15_602_120_000),
    ("health", "Health", 17_990_750_000),
    ("income_related_rent_subsidy", "Income-Related Rent Subsidy", 953_000_000),
    ("in_work_tax_credit", "In-work tax credit", 588_486_000),
    ("jobseeker_support", "Jobseeker Support", 1_815_138_000),
    ("minimum_family_tax_credit", "Minimum family tax credit", 13_403_000),
    ("nz_super_and_vets", "NZ Super and Vets", 14_502_222_000),
    ("paid_parental_leave", "Paid parental leave", 348_750_000),
    ("pbff_model_budget_total", "PBFF model budget total", 10_590_775_000),
    ("personal_income_tax", "Personal income tax", 38_350_500_000),
    ("petrol_excise", "Petrol excise", 765_222_000),
    ("primary_education", "Primary education", 3_883_734_000),
    ("secondary_education", "Secondary education", 2_817_016_000),
    ("sole_parent_support", "Sole Parent Support", 1_115_119_000),
    ("student_allowance", "Student allowance", 564_948_000),
    ("student_loan", "Student loan", 571_050_000),
    ("supported_living_payment", "Supported Living Payment", 1_552_524_000),
    ("tertiary_education", "Tertiary education", 3_161_000_000),
    ("tobacco_excise", "Tobacco excise", 369_853_000),
    ("winter_energy_payment", "Winter Energy Payment", 441_347_000),
    ("youth_young_parent_payment", "Youth/Young Parent Payment", 52_812_000),
)
GUARD_CASES = (
    ("A1", "publisher quantity header"),
    ("B1", "column header"),
    ("C1", "publisher derivation header"),
    *((f"A{row}", "row header") for row in range(2, 29)),
    *((f"C{row}", "verbatim publisher derivation") for row in range(2, 29)),
)


@lru_cache
def _package():
    return load_source_package(ALIAS)


@lru_cache
def _rows():
    return _package().build_source_rows(2019)


@lru_cache
def _cells():
    return _package().build_source_cells(2019, source_rows=_rows())


@lru_cache
def _records():
    return _package().build_source_records(2019, cells=_cells())


@lru_cache
def _facts():
    return _package().build_facts(2019, cells=_cells(), source_rows=_rows())


def _fact(slug):
    return next(f for f in _facts() if f.measure.concept == f"treasury.an24_01.{slug}")


def _mutated_package(tmp_path, mutate):
    payload = yaml.safe_load((PACKAGE_PATH / "source_package.yaml").read_text())
    mutate(payload)
    (tmp_path / "source_package.yaml").write_text(yaml.safe_dump(payload))
    return tmp_path


def test_treasury_alias_and_package_validation():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == DIRECTORY
    assert _package().package_id == ALIAS
    assert _package().artifact.parser == "delimited_text_full_rows"
    assert _package().artifact.artifact_year == 2019
    report = validate_source_package(ALIAS, year=2019)
    assert report.valid
    assert not report.warnings
    assert report.counts == {
        "record_set_count": 27,
        "row_count": 27,
        "measure_count": 27,
        "source_record_count": 27,
        "source_region_count": 27,
    }


@pytest.mark.parametrize(
    ("entry", "filename", "url", "sha256", "size", "fetched_at"),
    [
        (
            2019,
            "fiscal_totals.csv",
            SOURCE_URL,
            CSV_SHA256,
            8_134,
            "2026-10-07T19:25:22Z",
        ),
        (
            "license",
            "LICENSE",
            f"{RAW_BASE}/LICENSE",
            LICENSE_SHA256,
            7_048,
            "2026-10-07T19:24:41Z",
        ),
    ],
)
def test_treasury_artifact_and_license_match_publisher_receipts(
    entry, filename, url, sha256, size, fetched_at
):
    manifest = yaml.safe_load((DATA_PATH / "manifest.yaml").read_text())
    artifact = manifest["files"][entry]
    content = (DATA_PATH / filename).read_bytes()
    assert manifest["source_id"] == "treasury"
    assert manifest["package_id"] == ALIAS
    assert manifest["publisher_commit"] == COMMIT
    assert manifest["license"] == "CC0-1.0"
    assert artifact["filename"] == filename
    assert artifact["source_url"] == url
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest() == sha256
    assert artifact["size_bytes"] == len(content) == size
    assert artifact["fetched_at"] == fetched_at
    key = build_r2_key(
        source_id="treasury",
        package_id=ALIAS,
        year=entry,
        sha256=sha256,
        filename=filename,
        prefix="raw/nz",
    )
    assert artifact["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }


def test_treasury_full_rows_and_cells_preserve_all_published_values_and_notes():
    with (DATA_PATH / "fiscal_totals.csv").open(newline="") as source:
        reader = csv.DictReader(source)
        assert reader.fieldnames == ["Quantity", "TY2019", "Notes"]
        published = list(reader)
    assert len(published) == len(_rows()) == 27
    assert validate_source_rows(_rows()).valid
    assert len(_cells()) == 28 * 3
    assert validate_source_cells(_cells()).valid
    cells = {cell.address: cell for cell in _cells()}
    assert set(cells) == {f"{col}{row}" for col in "ABC" for row in range(1, 29)}
    assert {cell.sheet_name for cell in _cells()} == {SHEET}
    assert [cells[f"{col}1"].raw_value for col in "ABC"] == [
        "Quantity",
        "TY2019",
        "Notes",
    ]
    for row_number, (raw, parsed, (_, quantity, amount)) in enumerate(
        zip(published, _rows(), PUBLISHED_ROWS, strict=True), start=2
    ):
        assert raw["Quantity"] == quantity
        assert int(raw["TY2019"]) == amount
        assert parsed.row_number == row_number
        assert parsed.values == {
            "Quantity": quantity,
            "TY2019": amount,
            "Notes": raw["Notes"],
        }
        assert cells[f"A{row_number}"].raw_value == quantity
        assert cells[f"B{row_number}"].raw_value == amount
        assert cells[f"C{row_number}"].raw_value == raw["Notes"]


def test_treasury_facts_are_direct_publisher_cells_with_verbatim_notes_lineage():
    assert len(_facts()) == len(_records()) == 27
    assert validate_facts(_facts()).valid
    assert validate_consumer_fact_contract(_facts()).valid
    cells = {build_source_cell_key(cell): cell for cell in _cells()}
    records = {record.spec.concept: record for record in _records()}
    rows = {row.row_number: row for row in _rows()}
    for row_number, (slug, quantity, amount) in enumerate(PUBLISHED_ROWS, start=2):
        fact = _fact(slug)
        record = records[fact.measure.concept]
        assert fact.value == amount == rows[row_number].values["TY2019"]
        assert fact.source.source_name == "treasury"
        assert fact.source.source_table == TABLE
        assert fact.source.url == SOURCE_URL
        assert fact.source.source_sha256 == CSV_SHA256
        assert (
            fact.source.raw_r2_uri
            == f"r2://ledger-raw/raw/nz/treasury/{ALIAS}/2019/{CSV_SHA256}/fiscal_totals.csv"
        )
        assert fact.assertion == "observation"
        assert fact.provenance_class == "model_output"
        assert fact.survey_instrument is None
        assert fact.entity.name == "government"
        assert fact.measure.unit == "nzd"
        assert fact.aggregation.method == "sum"
        assert (
            fact.measure.source_concept
            == fact.measure.concept
            == f"treasury.an24_01.{slug}"
        )
        assert fact.measure.concept_relation == "source_label"
        assert fact.measure.concept_authority == "treasury"
        assert fact.measure.concept_evidence_url == SOURCE_URL
        assert fact.measure.concept_evidence_notes == rows[row_number].values["Notes"]
        assert record.spec.selector.address == f"B{row_number}"
        assert record.spec.selector.end_address is None
        assert record.spec.divisor_selector is None
        assert record.spec.round_to is None
        assert record.spec.value_scale == 1
        assert not fact.filters
        assert not fact.constraints
        assert fact.source_row_keys == (build_source_row_key(rows[row_number]),)
        lineage = {
            cells[key].address: cells[key].raw_value for key in fact.source_cell_keys
        }
        assert lineage[f"B{row_number}"] == amount
        assert lineage[f"C{row_number}"] == fact.measure.concept_evidence_notes
        assert lineage["A1"] == "Quantity"
        assert lineage["B1"] == "TY2019"
        assert lineage["C1"] == "Notes"
        assert fact.layout.groupby_value_label == quantity


@pytest.mark.parametrize(
    ("slug", "address", "amount", "notes"),
    [
        (
            "accommodation_supplement",
            "B3",
            1_531_000_000,
            "Weighted average of Accommodation Assistance actuals for fiscal years 2018 (weight 1/4) and 2019 (weight 3/4). Source: https://www.treasury.govt.nz/publications/efu/budget-economic-and-fiscal-update-2022 (fiscal year 2018; file befu22-data-expensetables.xlsx) and CFISnet - the Crown's Financial and Information System (fiscal year 2019).",
        ),
        (
            "pbff_model_budget_total",
            "B16",
            10_590_775_000,
            "Total PBFF model service budget in fiscal year 2019. Source: 2019 Population Based Funding Formula model - Ministry of Health.",
        ),
        (
            "winter_energy_payment",
            "B27",
            441_347_000,
            "Winter Energy Payment actual in fiscal year 2019. Source: CFISnet - the Crown's Financial and Information System.",
        ),
    ],
)
def test_treasury_exact_published_anchor_cells(slug, address, amount, notes):
    fact = _fact(slug)
    record = next(
        record
        for record in _records()
        if record.source_record_id == fact.source_record_id
    )
    assert record.spec.selector.address == address
    assert fact.value == amount
    assert fact.measure.concept_evidence_notes == notes


def test_treasury_tax_year_country_and_labels_are_explicit():
    assert _dimension_label_reports(ALIAS, consumer_fact_rows(_facts())) == ([], [])
    for slug, quantity, _ in PUBLISHED_ROWS:
        fact = _fact(slug)
        assert (fact.period.type, fact.period.value) == ("tax_year", 2019)
        assert (fact.geography.level, fact.geography.id, fact.geography.name) == (
            "country",
            "NZ",
            "New Zealand",
        )
        assert fact.period_coverage.basis == "tax"
        assert fact.period_coverage.source_period_label == "TY2019"
        assert fact.period_coverage.start_date == "2018-04-01"
        assert fact.period_coverage.end_date == "2019-03-31"
        assert (
            "PBFF model budget total and Winter Energy Payment"
            in fact.period_coverage.notes
        )
        assert "neither recomputes nor aligns" in fact.period_coverage.notes
        assert fact.layout.groupby_dimension == QUANTITY_DIMENSION
        assert fact.dimension_labels[QUANTITY_DIMENSION] == "Quantity"
        assert fact.dimension_value_labels[QUANTITY_DIMENSION] == {slug: quantity}


@pytest.mark.parametrize("year", [2018, 2020, 2023, 2026])
def test_treasury_off_year_build_preserves_published_period_and_facts(year):
    report = validate_source_package(ALIAS, year=year)
    assert report.valid
    assert [asdict(fact) for fact in _package().build_facts(year)] == [
        asdict(fact) for fact in _facts()
    ]


@pytest.mark.parametrize(
    ("address", "message"), GUARD_CASES, ids=[case[0] for case in GUARD_CASES]
)
def test_treasury_all_label_notes_and_header_guards_reject_source_drift(
    address, message
):
    changed = [
        replace(cell, raw_value="unexpected publisher content")
        if cell.address == address
        else cell
        for cell in _cells()
    ]
    report = validate_source_record_specs(
        _package().build_source_record_specs(2019), changed
    )
    assert not report.valid
    assert report.resolved_count == (0 if address in {"A1", "B1", "C1"} else 26)
    assert all(
        error.code == "source_record_resolution_failed" for error in report.errors
    )
    assert any(message in error.message for error in report.errors)
    with pytest.raises(ValueError, match=message):
        _package().build_facts(2019, cells=changed, source_rows=_rows())


@pytest.mark.parametrize("row", range(2, 29))
def test_treasury_every_amount_requires_a_numeric_source_cell(row):
    changed = [
        replace(cell, raw_value="suppressed", cell_type="text")
        if cell.address == f"B{row}"
        else cell
        for cell in _cells()
    ]
    report = validate_source_record_specs(
        _package().build_source_record_specs(2019), changed
    )
    assert not report.valid
    assert report.resolved_count == 26
    with pytest.raises(ValueError, match="expected cell type"):
        _package().build_facts(2019, cells=changed, source_rows=_rows())


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"provenance_class": None}, "provenance_class"),
        ({"provenance_class": "computed"}, "must be one of"),
        ({"provenance_class": "survey_aggregate"}, "survey_instrument"),
        ({"survey_instrument": "HES"}, "forbidden"),
        ({"assertion": "policyengine_computed"}, "PolicyEngine-computed"),
        ({"assertion": "forecast"}, "PolicyEngine-computed"),
    ],
)
def test_treasury_invalid_provenance_or_computed_assertions_fail_validation(
    tmp_path, mutation, message
):
    path = _mutated_package(
        tmp_path, lambda payload: payload["record_sets"][0].update(mutation)
    )
    report = validate_source_package(path, year=2019)
    assert not report.valid
    assert any(message in error.message for error in report.errors)


def test_treasury_a_year_template_cannot_restamp_published_ty2019(tmp_path):
    path = _mutated_package(
        tmp_path, lambda payload: payload["record_sets"][0].update(period="{year}")
    )
    report = validate_source_package(path, year=2023)
    assert not report.valid
    assert any(error.code == "artifact_year_restamp" for error in report.errors)
    with pytest.raises(ArtifactYearRestampError, match="pins artifact_year 2019"):
        load_source_package(path).build_facts(2023)


def test_treasury_build_suite_passes_source_acceptance(tmp_path):
    report = build_source_suite(ALIAS, tmp_path / "suite", year=2019)
    assert report.valid
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
    assert not report.agent_acceptance.errors
    assert report.source_rows.row_count == 27
    assert report.source_cells.cell_count == 84
    assert report.source_records.resolved_count == 27
    assert report.source_records.lineage_coverage == 1
    assert report.consumer_facts.fact_count == 27
    assert report.agent_acceptance.counts["raw_artifact_count"] == 1
    assert report.agent_acceptance.counts["raw_r2_link_count"] == 1


def test_treasury_single_source_bundle_has_expected_delta(tmp_path):
    # Keep this explicit single-source build small; the full bundle runs in CI.
    report = build_bundle(tmp_path / "bundle", year=2023, sources=[ALIAS])
    assert report.valid
    assert len(report.source_packages) == 1
    assert not report.skipped_sources
    coverage = report.coverage
    assert coverage == build_bundle_coverage(consumer_fact_rows(_facts()))
    assert coverage["fact_count"] == 27
    assert coverage["counts"]["by_source"] == {"treasury": 27}
    assert coverage["counts"]["by_source_table"] == {f"treasury:{TABLE}": 27}
    assert coverage["counts"]["by_period"] == {"tax_year:2019": 27}
    assert coverage["counts"]["by_geography"] == {"country:NZ": 27}
    assert coverage["counts"]["by_entity"] == {"government": 27}
    assert coverage["duplicates"] == {
        "aggregate_fact_keys": [],
        "semantic_fact_keys": [],
    }
