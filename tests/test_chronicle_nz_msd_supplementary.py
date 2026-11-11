"""Direct-cell fidelity for MSD's June 2026 Work and Income regions."""

import hashlib
from dataclasses import replace
from decimal import Decimal
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
from chronicle.source_package import load_source_package, validate_source_package
from chronicle.sources import build_source_cell_key, validate_source_cells
from chronicle.suite import build_source_suite

ROOT = Path(__file__).resolve().parents[1]
ALIAS = "msd-benefit-fact-sheets-supplementary-june-2026"
DIRECTORY = Path("msd/benefit_fact_sheets_supplementary_june_2026")
FILENAME = "quarterly-benefit-fact-sheets-w-i-supplementary-tables-june-2026.xlsx"
SHA256 = "40551e97ff2c33c2c2a81795fcb70d02b3002b96bfda0ffd9acf8e549f640c9a"
SOURCE_URL = (
    "https://www.msd.govt.nz/documents/about-msd-and-our-work/publications-resources/statistics/benefit/2026/"
    + FILENAME
)
REGIONS = {
    "Auckland": ("auckland", (36528, 48138, 124107)),
    "BOP": ("bay-of-plenty", (11040, 18021, 34764)),
    "Canterbury": ("canterbury", (8505, 27153, 34254)),
    "Central": ("central", (6426, 13686, 19443)),
    "East Coast": ("east-coast", (5097, 11187, 18036)),
    "Nelson": ("nelson", (3384, 10566, 12465)),
    "Northland": ("northland", (6036, 10440, 18123)),
    "Southern": ("southern", (5733, 18714, 19950)),
    "Taranaki": ("taranaki", (5844, 13914, 18504)),
    "Waikato": ("waikato", (9594, 16962, 31371)),
    "Wellington": ("wellington", (7431, 14883, 26292)),
    "Other regions": ("other-regions", (630, 2526, 6003)),
}
ASSISTANCE = (
    "special_benefit_or_temporary_additional_support",
    "disability_allowance",
    "accommodation_supplement",
)


@lru_cache
def _package():
    return load_source_package(ALIAS)


@lru_cache
def _cells():
    return _package().build_source_cells(2026)


@lru_cache
def _facts():
    return _package().build_facts(2026, cells=_cells())


def test_regional_package_and_publisher_bytes_are_pinned():
    report = validate_source_package(ALIAS, year=2026)
    assert report.valid and not report.warnings
    assert report.counts == {
        "record_set_count": 12,
        "row_count": 36,
        "measure_count": 12,
        "source_record_count": 36,
        "source_region_count": 12,
    }
    directory = ROOT / "db/data" / DIRECTORY
    artifact = yaml.safe_load((directory / "manifest.yaml").read_text())["files"][2026]
    assert artifact["source_url"] == SOURCE_URL
    assert (
        artifact["sha256"]
        == hashlib.sha256((directory / FILENAME).read_bytes()).hexdigest()
        == SHA256
    )
    assert artifact["size_bytes"] == (directory / FILENAME).stat().st_size == 143509
    assert artifact["fetched_at"] == "2026-10-07T19:22:20Z"
    key = build_r2_key(
        source_id="msd",
        package_id=ALIAS,
        year=2026,
        sha256=SHA256,
        filename=FILENAME,
        package_path=ROOT / "packages" / DIRECTORY,
    )
    assert key.startswith("raw/nz/msd/")
    assert artifact["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": "r2://ledger-raw/" + key,
    }
    assert {f.source.raw_r2_uri for f in _facts()} == {"r2://ledger-raw/" + key}


@pytest.mark.parametrize("sheet", REGIONS)
def test_each_published_region_assistance_count_is_one_exact_cell(sheet):
    slug, values = REGIONS[sheet]
    cells = {(c.sheet_name, c.address): c for c in _cells()}
    records = {
        r.source_record_id: r
        for r in _package().build_source_records(2026, cells=_cells())
    }
    for row, assistance, value in zip((7, 8, 9), ASSISTANCE, values):
        fact = next(
            f
            for f in _facts()
            if f.source_record_id
            == f"msd.supplementary.jun2026.{slug}.{assistance}.recipients"
        )
        record = records[fact.source_record_id]
        assert cells[(sheet, f"W{row}")].raw_value == fact.value == value
        assert record.spec.selector.address == f"W{row}"
        assert record.spec.selector.end_address is None
        assert record.spec.divisor_selector is None
        assert record.spec.value_scale == 1
        assert Decimal(str(fact.value)) == Decimal(
            str(cells[(sheet, f"W{row}")].raw_value)
        )
        assert fact.geography.id == "nz-wi-" + slug
        assert fact.geography.level == "statistical_scope"
        assert fact.geography.vintage == "msd_wi_region"
        assert fact.filters["msd_supplementary_assistance_type"] == assistance


def test_quarter_end_period_all_ages_and_no_national_reconstruction():
    for fact in _facts():
        assert (fact.period.type, fact.period.value) == ("month", "2026-06")
        assert fact.period_coverage.source_period_label == "Jun-26"
        assert (
            fact.period_coverage.start_date
            == fact.period_coverage.end_date
            == "2026-06-30"
        )
        assert fact.entity.name == "person"
        assert fact.provenance_class == "administrative"
        assert fact.assertion == "observation"
        assert fact.aggregation.method == "sum"
        assert fact.measure.unit == "count"
        assert fact.source.source_sha256 == SHA256
        assert fact.source.url == SOURCE_URL
        assert "does not split AS recipients" in fact.measure.concept_evidence_notes
    assert {f.geography.id for f in _facts()} == {
        "nz-wi-" + slug for slug, _ in REGIONS.values()
    }
    assert len(_facts()) == 36
    assert {
        (f.period.type, f.period.value)
        for f in _package().build_facts(2023, cells=_cells())
    } == {("month", "2026-06")}
    notes = {
        (c.address): c.raw_value
        for c in _cells()
        if c.sheet_name == "Contents and notes"
    }
    assert notes["B31"] == "• Supplementary and hardship assistance data are all ages."
    assert (
        notes["B34"]
        == "• People may be receiving more than one type of Supplementary Assistance."
    )
    assert '"Other regions" refers to offices managed by national units' in notes["C24"]


def test_complete_source_cells_contract_labels_and_coverage():
    cells, facts = _cells(), _facts()
    assert len(cells) == 18615
    assert {c.sheet_name for c in cells} == {"Contents and notes", *REGIONS}
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert _dimension_label_reports(ALIAS, consumer_fact_rows(facts)) == ([], [])
    keys = {build_source_cell_key(c) for c in cells}
    assert all(f.source_cell_keys and set(f.source_cell_keys) <= keys for f in facts)
    coverage = build_bundle_coverage(consumer_fact_rows(facts))
    assert coverage["counts"]["by_geography"] == {
        "statistical_scope:nz-wi-" + slug: 3 for slug, _ in REGIONS.values()
    }
    assert coverage["counts"]["by_entity"] == {"person": 36}
    assert coverage["counts"]["by_period"] == {"month:2026-06": 36}
    assert coverage["duplicates"] == {
        "aggregate_fact_keys": [],
        "semantic_fact_keys": [],
    }


def test_regional_build_suite_passes_acceptance(tmp_path):
    report = build_source_suite(ALIAS, tmp_path / "suite", year=2023)
    assert report.valid
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
    assert report.consumer_facts.fact_count == 36
    assert report.source_cells.cell_count == 18615
    assert report.source_records.lineage_coverage == 1
    assert report.agent_acceptance.counts["raw_artifact_count"] == 1
    assert report.agent_acceptance.counts["raw_r2_link_count"] == 1


@pytest.mark.parametrize("sheet", REGIONS)
@pytest.mark.parametrize("address", ("B2", "B4", "B6", "W6", "B7", "B8", "B9"))
def test_every_regional_guard_rejects_mutated_source(sheet, address):
    changed = [
        replace(c, raw_value="mutated publisher layout")
        if (c.sheet_name, c.address) == (sheet, address)
        else c
        for c in _cells()
    ]
    with pytest.raises(ValueError):
        _package().build_facts(2026, cells=changed)


@pytest.mark.parametrize("sheet", REGIONS)
def test_numeric_guard_rejects_mutated_source(sheet):
    changed = [
        replace(c, cell_type="text", raw_value="S")
        if (c.sheet_name, c.address) == (sheet, "W9")
        else c
        for c in _cells()
    ]
    with pytest.raises(ValueError, match="cell type"):
        _package().build_facts(2026, cells=changed)
