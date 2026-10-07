"""Publisher-fidelity tests for New Zealand Chronicle source packages."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import replace
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

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

REPO_ROOT = Path(__file__).resolve().parents[1]
WFF_ALIAS = "ird-working-for-families-statistics-sept-2025"
WFF_DIRECTORY = Path("ird/working_for_families_statistics_sept_2025")
WFF_FILENAME = "working-for-families-statistics---sept-2025.xlsx"
WFF_SHA256 = "95ae66f4d44f3f47ea3daa006328b22f061a163cf7e31b487342cde649390833"
WFF_R2_KEY = f"raw/nz/ird/{WFF_ALIAS}/2024/{WFF_SHA256}/{WFF_FILENAME}"
WFF_SOURCE_URL = (
    "https://www.ird.govt.nz/-/media/project/ir/home/documents/about-us/"
    "tax-statistics---current/social-policy/wff-stats/"
    f"{WFF_FILENAME}?modified=20251111195236"
)
DATA_SHEET = "Working for families data"
INCOME_SHEET = "Working for families income"
RECORD_PREFIX = "ird_wff_statistics.ty2024"


@lru_cache
def _package():
    return load_source_package(WFF_ALIAS)


@lru_cache
def _cells():
    return _package().build_source_cells(2024)


@lru_cache
def _facts():
    return _package().build_facts(2024, cells=_cells())


@lru_cache
def _records():
    return _package().build_source_records(2024, cells=_cells())


def _fact(record_set, row, measure):
    record_id = f"{RECORD_PREFIX}.{record_set}.{row}.{measure}"
    return next(fact for fact in _facts() if fact.source_record_id == record_id)


def test_wff_alias_and_package_shape():
    assert SOURCE_PACKAGE_ALIASES[WFF_ALIAS] == WFF_DIRECTORY
    assert _package().package_id == WFF_ALIAS
    report = validate_source_package(WFF_ALIAS, year=2024)
    assert report.valid
    assert not report.warnings
    assert report.counts == {
        "record_set_count": 5,
        "row_count": 43,
        "measure_count": 26,
        "source_record_count": 330,
        "source_region_count": 5,
    }


def test_wff_official_artifact_is_pinned():
    data_dir = REPO_ROOT / "db" / "data" / WFF_DIRECTORY
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text())
    artifact = manifest["files"][2024]
    path = data_dir / WFF_FILENAME

    assert manifest["source_id"] == "ird"
    assert manifest["package_id"] == WFF_ALIAS
    assert artifact["filename"] == WFF_FILENAME
    assert artifact["source_url"] == WFF_SOURCE_URL
    assert artifact["sha256"] == WFF_SHA256
    assert hashlib.sha256(path.read_bytes()).hexdigest() == WFF_SHA256
    assert path.stat().st_size == artifact["size_bytes"] == 71_211


def test_wff_r2_provenance_and_consumer_contract():
    data_dir = REPO_ROOT / "db" / "data" / WFF_DIRECTORY
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text())
    storage = manifest["files"][2024]["storage"]["r2"]
    assert storage == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": WFF_R2_KEY,
        "uri": f"r2://ledger-raw/{WFF_R2_KEY}",
    }
    assert {fact.source.raw_r2_uri for fact in _facts()} == {storage["uri"]}
    assert validate_consumer_fact_contract(_facts()).valid


def test_wff_labels_every_dimension_and_value_for_the_bundle():
    # build-bundle refuses a package that leaves a dimension or value without a
    # Chronicle label (chronicle#261, #265).
    assert _dimension_label_reports(WFF_ALIAS, consumer_fact_rows(_facts())) == (
        [],
        [],
    )
    total = _fact("recipient_families", "all", "wff_recipient_families")
    assert total.dimension_labels["wff_credit_component"] == (
        "Working for Families credit type"
    )
    assert total.dimension_value_labels["wff_credit_component"] == {
        "any": "Any Working for Families credit"
    }
    assert total.dimension_value_labels["wff_entitlement_status"] == {
        "nonzero": "Non-zero entitlement"
    }
    unknown = _fact("income_distribution", "income_unknown", "ftc_recipient_families")
    assert unknown.dimension_value_labels["family_scheme_income_band_source_label"] == {
        "Unknown**": "Unknown**"
    }
    assert unknown.dimension_value_labels["wff_credit_component"] == {
        "ftc": "Family Tax Credit"
    }


def test_wff_build_suite_passes_all_source_acceptance_gates(tmp_path):
    report = build_source_suite(WFF_ALIAS, tmp_path / "suite", year=2024)
    assert report.valid
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
    assert not report.agent_acceptance.errors
    assert report.source_records.resolved_count == 330
    assert report.source_records.lineage_coverage == 1
    assert report.source_cells.cell_count == 4910
    assert report.consumer_facts.fact_count == 330
    assert report.agent_acceptance.counts["raw_artifact_count"] == 1
    assert report.agent_acceptance.counts["raw_r2_link_count"] == 1


def test_wff_bundle_coverage_delta_has_no_duplicate_keys():
    coverage = build_bundle_coverage(consumer_fact_rows(_facts()))
    assert coverage["fact_count"] == 330
    assert coverage["counts"]["by_source"] == {"ird": 330}
    assert coverage["counts"]["by_period"] == {"tax_year:2024": 330}
    assert coverage["counts"]["by_geography"] == {"country:NZ": 330}
    assert coverage["counts"]["by_entity"] == {"family": 329, "person": 1}
    assert coverage["counts"]["by_source_table"] == {
        "ird:Working for Families statistics - September 2025": 330
    }
    assert coverage["duplicates"] == {
        "aggregate_fact_keys": [],
        "semantic_fact_keys": [],
    }


def test_wff_source_cells_and_fact_lineage_are_complete():
    cells = _cells()
    facts = _facts()
    assert len(cells) == 4910
    assert {cell.sheet_name for cell in cells} == {DATA_SHEET, INCOME_SHEET}
    assert validate_source_cells(cells).valid
    assert len(facts) == 330
    assert validate_facts(facts).valid
    assert Counter(fact.entity.name for fact in facts) == {
        "family": 329,
        "person": 1,
    }
    assert {fact.provenance_class for fact in facts} == {"administrative"}
    assert {fact.assertion for fact in facts} == {"observation"}
    assert {fact.source.source_name for fact in facts} == {"ird"}
    assert {fact.source.source_sha256 for fact in facts} == {WFF_SHA256}
    assert {fact.source.url for fact in facts} == {WFF_SOURCE_URL}
    assert {fact.measure.unit for fact in facts} == {"count", "nzd"}
    assert {fact.measure.concept_relation for fact in facts} == {"source_label"}
    cell_keys = {build_source_cell_key(cell) for cell in cells}
    assert all(fact.source_cell_keys for fact in facts)
    assert all(set(fact.source_cell_keys) <= cell_keys for fact in facts)

    # Every emitted value is one publisher cell with a declared unit scale;
    # there is no interpolation, inferred residual, ratio, or reconciliation.
    cells_by_address = {(cell.sheet_name, cell.address): cell for cell in cells}
    records_by_id = {record.source_record_id: record for record in _records()}
    for fact in facts:
        record = records_by_id[fact.source_record_id]
        selector = record.spec.selector
        assert selector.end_address is None
        assert record.spec.divisor_selector is None
        raw_value = cells_by_address[(selector.sheet_name, selector.address)].raw_value
        assert Decimal(str(fact.value)) == (
            Decimal(str(raw_value)) * Decimal(str(record.spec.value_scale))
        )


def test_wff_nz_tax_year_and_country_are_explicit():
    for fact in _facts():
        assert (fact.period.type, fact.period.value) == ("tax_year", 2024)
        assert (fact.geography.level, fact.geography.id) == ("country", "NZ")
        coverage = fact.period_coverage
        assert coverage.start_date == "2023-04-01"
        assert coverage.end_date == "2024-03-31"
        assert coverage.basis == "tax"
        assert coverage.source_period_label == "2024 Tax Year / 2023-24 Tax Year"
        assert coverage.accounting_basis is None
        assert "not an estimate of all eligible families" in coverage.notes

    # A generic bundle's requested year must not relabel the fixed source year.
    assert {
        (fact.period.type, fact.period.value)
        for fact in _package().build_facts(2023, cells=_cells())
    } == {("tax_year", 2024)}


@pytest.mark.parametrize(
    ("component", "families", "entitlement"),
    [
        ("ftc", 252_500, 2_273_000_000),
        ("mftc", 2_600, 12_000_000),
        ("iwtc", 150_500, 437_000_000),
        ("bstc", 137_200, 320_000_000),
        ("wff", 328_400, 3_043_000_000),
    ],
)
def test_wff_national_credit_counts_and_entitlements(component, families, entitlement):
    count = _fact("recipient_families", "all", f"{component}_recipient_families")
    amount = _fact("aggregate_entitlements", "all", f"{component}_entitlement_nzd")
    assert count.value == families
    assert amount.value == entitlement
    assert count.filters["wff_entitlement_status"] == "nonzero"
    assert count.entity.role == amount.entity.role == "wff_entitled_family"
    assert count.filters["wff_credit_component"] == (
        "any" if component == "wff" else component
    )


def test_wff_supported_children_and_family_sizes_remain_distinct():
    child_total = _fact("supported_children", "all", "wff_supported_children")
    assert child_total.value == 656_500
    assert child_total.entity.name == "person"
    counts = (136_600, 107_800, 50_900, 20_700, 7_700, 2_800, 1_100)
    for child_count, expected in enumerate(counts, start=1):
        suffix = (
            "1_child"
            if child_count == 1
            else "7_plus_children"
            if child_count == 7
            else f"{child_count}_children"
        )
        fact = _fact(
            "recipient_families_by_child_count", "all", f"wff_families_{suffix}"
        )
        assert fact.value == expected
        assert fact.entity.name == "family"
        constraint = next(
            c for c in fact.constraints if c.variable == "supported_child_count"
        )
        assert constraint.value == child_count
        assert constraint.unit == "children"
        assert constraint.operator == (">=" if child_count == 7 else "==")
    # Preserve distinct published counts; do not force one table to match another.
    assert (
        sum(counts)
        != _fact("recipient_families", "all", "wff_recipient_families").value
    )


def test_wff_complete_published_income_table_preserves_source_labels():
    facts = [
        fact
        for fact in _facts()
        if fact.layout.record_set_id == f"{RECORD_PREFIX}.income_distribution"
    ]
    assert len(facts) == 39 * 8
    assert Counter(fact.layout.measure_id for fact in facts) == {
        f"{component}_{measure}": 39
        for component in ("wff", "ftc", "iwtc", "bstc")
        for measure in ("entitlement_nzd", "recipient_families")
    }
    expected_labels = {*range(5_000, 180_001, 5_000), "180,000+", "Unknown**", "All"}
    assert {
        fact.filters["family_scheme_income_band_source_label"] for fact in facts
    } == expected_labels
    for fact in facts:
        constraints = [
            constraint
            for constraint in fact.constraints
            if constraint.variable == "family_scheme_income_band_source_label"
        ]
        assert len(constraints) == 1
        assert constraints[0].operator == "=="
        assert (
            constraints[0].value
            == fact.filters["family_scheme_income_band_source_label"]
        )
        assert "numeric labels are not recoded" in fact.measure.concept_evidence_notes
        assert fact.layout.table_record_kind == (
            "total" if fact.layout.groupby_value_id == "all_income_bands" else "detail"
        )


def test_wff_income_definition_preserves_publisher_qualifications():
    facts = [
        fact
        for fact in _facts()
        if fact.layout.record_set_id == f"{RECORD_PREFIX}.income_distribution"
    ]
    checklist = (REPO_ROOT / "docs" / "pe-nz-source-checklist.md").read_text()
    for notes in [checklist, *(fact.measure.concept_evidence_notes for fact in facts)]:
        normalized = " ".join(notes.lower().split())
        assert "entitlement-time-weighted" in normalized
        assert "work and income" in normalized
        assert "individual tax-return income" in normalized
        assert "excludes partner income" in normalized


@pytest.mark.parametrize(
    ("row", "counts", "amounts"),
    [
        (
            "income_label_5000",
            (2690, 2650, 810, 940),
            (20_780_000, 16_750_000, 2_330_000, 1_700_000),
        ),
        (
            "income_label_180000_plus",
            (16150, 210, 180, 15960),
            (18_370_000, 340_000, 190_000, 17_840_000),
        ),
        (
            "income_unknown",
            (3390, 2630, 1930, 1340),
            (28_020_000, 20_790_000, 4_450_000, 2_700_000),
        ),
        (
            "all_income_bands",
            (328400, 252500, 150500, 137200),
            (3_043_000_000, 2_273_000_000, 437_000_000, 320_000_000),
        ),
    ],
)
def test_wff_income_table_exact_anchor_rows(row, counts, amounts):
    for component, count, amount in zip(
        ("wff", "ftc", "iwtc", "bstc"), counts, amounts
    ):
        assert (
            _fact("income_distribution", row, f"{component}_recipient_families").value
            == count
        )
        assert (
            _fact("income_distribution", row, f"{component}_entitlement_nzd").value
            == amount
        )


def test_wff_income_rounding_adjustments_are_not_population_facts():
    cells = {cell.address: cell for cell in _cells() if cell.sheet_name == INCOME_SHEET}
    assert cells["AO50"].raw_value == "Rounding adjustment"
    assert cells["AO53"].raw_value == (
        "** Income is unknown for families that have not filed a Working for Families return."
    )
    for column, adjustment in zip(
        ("AP", "AQ", "AR", "AS", "AT", "AU", "AV", "AW"),
        (-0.43, 0.82, 0.43, -0.2, 50, 100, 180, 50),
    ):
        assert cells[f"{column}50"].raw_value == pytest.approx(adjustment)
        detail = sum(cells[f"{column}{row}"].raw_value for row in range(12, 50))
        # IRD reports detail minus total, not an additive population row.
        assert detail - cells[f"{column}50"].raw_value == pytest.approx(
            cells[f"{column}51"].raw_value
        )
    assert all(
        record.spec.selector.sheet_name != INCOME_SHEET
        or not record.spec.selector.address.endswith("50")
        for record in _records()
    )


@pytest.mark.parametrize(
    ("sheet", "address", "message"),
    [
        (DATA_SHEET, "A27", "row header"),
        (DATA_SHEET, "B92", "column header"),
        (INCOME_SHEET, "AO10", "income table tax-year label"),
        (INCOME_SHEET, "AO52", "income table population footnote"),
    ],
)
def test_wff_header_guards_reject_drift(sheet, address, message):
    changed_cells = [
        replace(cell, raw_value="unexpected publisher layout")
        if (cell.sheet_name, cell.address) == (sheet, address)
        else cell
        for cell in _cells()
    ]
    with pytest.raises(ValueError, match=message):
        _package().build_facts(2024, cells=changed_cells)
