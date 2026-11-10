"""Publisher-cell fidelity for IRD's 2025 taxable-income release (2024 tax year)."""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
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
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources import build_source_cell_key, validate_source_cells
from chronicle.sources.specs import (
    build_cells_by_sheet_address,
    resolve_source_record,
)
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
ALIAS = "ird-taxable-income-distribution-2025"
DIRECTORY = Path("ird/taxable_income_distribution_2025")
FILENAME = "taxable-income-distribution-of-individuals-2025.xlsx"
SHA256 = "fc7bf7ecdb27a08219cac1ad0cb06cc6bc8de0aae03d605c6ef8d42a15d4b592"
SOURCE_URL = (
    "https://www.ird.govt.nz/-/media/project/ir/home/documents/about-us/"
    "tax-statistics---current/revenue-and-refunds/tax-on-taxable-income/"
    f"tax-on-taxable-income/{FILENAME}"
)
INCOME_SHEET = "Income tables 2001-24"
AGE_SHEET = "Age by income band distribution"
RECORD_PREFIX = "ird_taxable_income_distribution.ty2024"
INCOME_ROWS = (*range(8, 245), 246)
AGE_MARGINAL_ROWS = (*range(289, 304), 305)
AGE_INCOME_ROWS = tuple(range(6, 190))
AGE_COLUMNS = tuple("BCDEFGHIJKLMNOP")

# Pin the coordinates independently of the package. Removing a guard must fail
# collection-independent coverage and its mutation regression, rather than
# silently removing that regression from a package-derived parameter list.
EXPECTED_GUARDS = tuple(
    sorted(
        {
            *((INCOME_SHEET, f"BE{row}") for row in INCOME_ROWS),
            *((INCOME_SHEET, f"BE{row}") for row in AGE_MARGINAL_ROWS),
            *((AGE_SHEET, f"A{row}") for row in AGE_INCOME_ROWS),
            *(
                (INCOME_SHEET, f"{column}{row}")
                for row in (5, 286)
                for column in ("BU", "BV", "BW")
            ),
            *((AGE_SHEET, f"{column}4") for column in AGE_COLUMNS),
            *(
                (INCOME_SHEET, address)
                for address in ("A2", "BE5", "BE6", "BU4", "BE282", "BE286", "BU285")
            ),
            *((AGE_SHEET, address) for address in ("A1", "A4", "A5", "B3")),
        }
    )
)


@lru_cache
def _package():
    # The lane's red demonstration points to a scratch-only mutated YAML;
    # ordinary tests always exercise the registered package alias.
    return load_source_package(
        os.environ.get("CHRONICLE_NZ_TAXABLE_TEST_PACKAGE", ALIAS)
    )


@lru_cache
def _cells():
    return _package().build_source_cells(2024)


@lru_cache
def _cell_index():
    return build_cells_by_sheet_address(_cells())


@lru_cache
def _specs():
    return _package().build_source_record_specs(2024)


@lru_cache
def _records():
    return _package().build_source_records(2024, cells=_cells())


@lru_cache
def _facts():
    return _package().build_facts(2024, cells=_cells())


@lru_cache
def _facts_by_id():
    return {fact.source_record_id: fact for fact in _facts()}


def _fact(record_set, row, measure):
    return _facts_by_id()[f"{RECORD_PREFIX}.{record_set}.row_{row}.{measure}"]


@lru_cache
def _guard_index():
    guards = {}
    for spec in _specs():
        selector = spec.selector
        entries = (
            (
                selector.expected_row_header_address,
                selector.expected_row_header,
                "row header",
            ),
            (
                selector.expected_column_header_address,
                selector.expected_column_header,
                "column header",
            ),
            *(
                (guard.address, guard.expected_value, guard.label)
                for guard in selector.guard_cells
            ),
        )
        assert not selector.range_label_guards
        for address, expected, label in entries:
            if address is None:
                continue
            coordinate = (selector.sheet_name, address)
            if coordinate in guards:
                assert guards[coordinate][1] == expected
            else:
                guards[coordinate] = (spec, expected, label)
    return guards


def test_taxable_income_alias_and_package_validation():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == DIRECTORY
    assert _package().package_id == ALIAS
    report = validate_source_package(ALIAS, year=2024)
    assert report.valid
    assert not report.warnings
    assert report.counts == {
        "record_set_count": 3,
        "row_count": 438,
        "measure_count": 21,
        "source_record_count": 3522,
        "source_region_count": 3,
    }


def test_taxable_income_publisher_artifact_and_receipt_are_pinned():
    data_dir = REPO_ROOT / "db" / "data" / DIRECTORY
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text())
    artifact = manifest["files"][2024]
    path = data_dir / FILENAME
    assert manifest["source_id"] == "ird"
    assert manifest["package_id"] == ALIAS
    assert artifact["filename"] == FILENAME
    assert artifact["source_url"] == SOURCE_URL
    assert artifact["sha256"] == SHA256
    assert artifact["fetched_at"] == "2026-10-07T19:23:14Z"
    assert artifact["size_bytes"] == path.stat().st_size == 294_932
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SHA256

    key = build_r2_key(
        source_id="ird",
        package_id=ALIAS,
        year=2024,
        sha256=SHA256,
        filename=FILENAME,
    )
    assert key == f"raw/nz/ird/{ALIAS}/2024/{SHA256}/{FILENAME}"
    storage = artifact["storage"]["r2"]
    assert storage == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }
    assert {fact.source.raw_r2_uri for fact in _facts()} == {storage["uri"]}


def test_taxable_income_preserves_both_complete_data_worksheet_ranges():
    cells = _cells()
    assert len(cells) == 32_261
    assert Counter(cell.sheet_name for cell in cells) == {
        INCOME_SHEET: 329 * 79,
        AGE_SHEET: 190 * 33,
    }
    assert validate_source_cells(cells).valid
    facts = _facts()
    assert len(facts) == 3522
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert {fact.entity.name for fact in facts} == {"person"}
    assert {fact.provenance_class for fact in facts} == {"administrative"}
    assert {fact.assertion for fact in facts} == {"observation"}
    assert {fact.source.source_name for fact in facts} == {"ird"}
    assert {fact.source.source_sha256 for fact in facts} == {SHA256}
    assert {fact.source.source_size_bytes for fact in facts} == {294_932}
    assert {fact.source.url for fact in facts} == {SOURCE_URL}


def test_taxable_income_every_value_is_a_single_publisher_cell_with_unit_scaling():
    cell_keys = {build_source_cell_key(cell) for cell in _cells()}
    records = {record.source_record_id: record for record in _records()}
    assert Counter(fact.layout.record_set_id for fact in _facts()) == {
        f"{RECORD_PREFIX}.income_bands": 238 * 3,
        f"{RECORD_PREFIX}.age_marginals": 16 * 3,
        f"{RECORD_PREFIX}.age_by_income_band": 184 * 15,
    }
    for fact in _facts():
        spec = records[fact.source_record_id].spec
        selector = spec.selector
        assert selector.end_address is None
        assert spec.divisor_selector is None
        assert spec.round_to is None
        assert spec.value_scale == (1 if fact.measure.unit == "count" else 1_000_000)
        assert fact.measure.unit in {"count", "nzd"}
        assert fact.measure.concept_relation == "source_label"
        assert fact.aggregation.method == "sum"
        assert fact.aggregation.denominator is None
        raw = _cell_index()[(selector.sheet_name, selector.address)].raw_value
        expected = Decimal(str(raw)) * Decimal(str(spec.value_scale))
        if fact.measure.unit == "count":
            assert Decimal(str(fact.value)) == expected
        else:
            # The parser retains publisher numeric cells as binary floats;
            # the tolerance is below one tenth of a cent after NZD scaling.
            assert fact.value == pytest.approx(float(expected), abs=0.0001, rel=0)
        assert fact.source_cell_keys
        assert set(fact.source_cell_keys) <= cell_keys
        assert (
            build_source_cell_key(
                _cell_index()[(selector.sheet_name, selector.address)]
            )
            in fact.source_cell_keys
        )


def test_taxable_income_tax_year_is_the_workbooks_ending_year():
    assert _cell_index()[(INCOME_SHEET, "BU4")].raw_value == 2024
    assert _cell_index()[(INCOME_SHEET, "BU285")].raw_value == 2024
    assert "2024" in _cell_index()[(AGE_SHEET, "A1")].raw_value
    for fact in _facts():
        assert (fact.period.type, fact.period.value) == ("tax_year", 2024)
        assert (fact.geography.level, fact.geography.id, fact.geography.name) == (
            "country",
            "NZ",
            "New Zealand",
        )
        coverage = fact.period_coverage
        assert coverage.basis == "tax"
        assert coverage.start_date == "2023-04-01"
        assert coverage.end_date == "2024-03-31"
        assert "2024" in coverage.source_period_label
        assert "2025" not in coverage.source_period_label
    assert {
        (fact.period.type, fact.period.value)
        for fact in _package().build_facts(2023, cells=_cells())
    } == {("tax_year", 2024)}


def test_taxable_income_all_dimensions_and_values_have_labels():
    assert _dimension_label_reports(ALIAS, consumer_fact_rows(_facts())) == ([], [])
    expected_groupbys = {
        "income_bands": "ird_taxable_income_distribution.income_band_row",
        "age_marginals": "ird_taxable_income_distribution.age_band_row",
        "age_by_income_band": "ird_taxable_income_distribution.age_income_band_row",
    }
    for fact in _facts():
        record_set = fact.layout.record_set_id.rsplit(".", 1)[1]
        assert fact.layout.groupby_dimension == expected_groupbys[record_set]
        assert fact.layout.groupby_dimension_label
        assert fact.dimension_value_labels[fact.layout.groupby_dimension] == {
            fact.layout.groupby_value_id: fact.layout.groupby_value_label,
        }
        for dimension, value in fact.filters.items():
            assert fact.dimension_labels[dimension]
            assert fact.dimension_value_labels[dimension][str(value)] == str(value)


@pytest.mark.parametrize(
    ("record_set", "row", "measure", "sheet", "address", "value"),
    [
        ("income_bands", 246, "individuals", INCOME_SHEET, "BU246", 4_693_920),
        ("income_bands", 244, "individuals", INCOME_SHEET, "BU244", 2690),
        (
            "income_bands",
            244,
            "taxable_income_nzd",
            INCOME_SHEET,
            "BV244",
            5_150_970_000,
        ),
        (
            "income_bands",
            244,
            "tax_on_taxable_income_nzd",
            INCOME_SHEET,
            "BW244",
            1_955_439_551,
        ),
        ("income_bands", 8, "individuals", INCOME_SHEET, "BU8", 54_800),
        ("income_bands", 9, "individuals", INCOME_SHEET, "BU9", 331_010),
        (
            "income_bands",
            8,
            "tax_on_taxable_income_nzd",
            INCOME_SHEET,
            "BW8",
            -63_153.65,
        ),
        ("age_marginals", 303, "individuals", INCOME_SHEET, "BU303", 4990),
        ("age_by_income_band", 7, "individuals_age_c", AGE_SHEET, "C7", 140_490),
        ("age_by_income_band", 6, "individuals_age_b", AGE_SHEET, "B6", 290),
        ("age_by_income_band", 188, "individuals_age_b", AGE_SHEET, "B188", 340),
        ("age_by_income_band", 188, "individuals_age_p", AGE_SHEET, "P188", 4130),
    ],
)
def test_taxable_income_exact_publisher_cell_anchors(
    record_set,
    row,
    measure,
    sheet,
    address,
    value,
):
    fact = _fact(record_set, row, measure)
    record = next(
        record
        for record in _records()
        if record.source_record_id == fact.source_record_id
    )
    assert (record.spec.selector.sheet_name, record.spec.selector.address) == (
        sheet,
        address,
    )
    assert fact.value == pytest.approx(value, abs=0.0001, rel=0)


def test_taxable_income_preserves_low_income_unknown_age_and_open_bands():
    assert (
        _fact("income_bands", 8, "individuals").filters[
            "taxable_income_band_source_label"
        ]
        == "nil"
    )
    assert (
        _fact("income_bands", 9, "individuals").filters[
            "taxable_income_band_source_label"
        ]
        == "$0.01    -   $100"
    )
    top = _fact("income_bands", 244, "individuals")
    assert top.filters["taxable_income_band_source_label"] == "Over $1,000,000"
    age_top = _fact("age_by_income_band", 188, "individuals_age_p")
    assert age_top.filters["taxable_income_band_source_label"] == "Over $180,000"
    assert (
        _fact("age_marginals", 303, "individuals").filters["age_band_source_label"]
        == "Unknown"
    )
    assert (
        _fact("age_by_income_band", 6, "individuals_age_b").filters[
            "age_band_source_label"
        ]
        == "Unknown"
    )
    for fact in _facts():
        assert all(constraint.operator == "==" for constraint in fact.constraints)
        assert {
            constraint.variable: constraint.value for constraint in fact.constraints
        } == fact.filters
        assert set(fact.filters) <= {
            "taxable_income_band_source_label",
            "age_band_source_label",
        }


def test_taxable_income_separately_published_totals_are_separate_cell_facts():
    total_rows = {"income_bands": 246, "age_marginals": 305, "age_by_income_band": 189}
    for fact in _facts():
        table = fact.layout.record_set_id.rsplit(".", 1)[1]
        assert fact.layout.table_record_kind == (
            "total"
            if fact.layout.groupby_value_id == f"row_{total_rows[table]}"
            else "detail"
        )
    income = _fact("income_bands", 246, "taxable_income_nzd")
    age = _fact("age_marginals", 305, "taxable_income_nzd")
    assert income.value == 267_988_860_000
    assert age.value == pytest.approx(267_988_900_000, abs=0.0001, rel=0)
    assert income.value != age.value
    income_tax = _fact("income_bands", 246, "tax_on_taxable_income_nzd")
    age_tax = _fact("age_marginals", 305, "tax_on_taxable_income_nzd")
    assert income_tax.value == pytest.approx(60_676_797_696.91001, abs=0.0001, rel=0)
    assert age_tax.value == 60_676_900_000
    assert income_tax.value != age_tax.value
    # The publisher's separate age panels need not agree.
    assert _fact("age_marginals", 291, "individuals").value == 350_820
    assert _fact("age_by_income_band", 189, "individuals_age_e").value == 350_890
    assert _fact("age_marginals", 303, "individuals").value == 4990
    assert _fact("age_by_income_band", 189, "individuals_age_b").value == 5050


def test_taxable_income_bundle_coverage_delta_has_no_duplicate_keys():
    coverage = build_bundle_coverage(consumer_fact_rows(_facts()))
    assert coverage["fact_count"] == 3522
    assert coverage["counts"]["by_source"] == {"ird": 3522}
    assert coverage["counts"]["by_period"] == {"tax_year:2024": 3522}
    assert coverage["counts"]["by_geography"] == {"country:NZ": 3522}
    assert coverage["counts"]["by_entity"] == {"person": 3522}
    assert list(coverage["counts"]["by_source_table"].values()) == [3522]
    assert coverage["duplicates"] == {
        "aggregate_fact_keys": [],
        "semantic_fact_keys": [],
    }


def test_taxable_income_every_required_guard_is_declared():
    assert len(EXPECTED_GUARDS) == 470
    assert set(_guard_index()) == set(EXPECTED_GUARDS)


@pytest.mark.parametrize(
    ("sheet", "address"),
    EXPECTED_GUARDS,
    ids=[f"{sheet}:{address}" for sheet, address in EXPECTED_GUARDS],
)
def test_taxable_income_each_guard_rejects_mutated_publisher_cell(sheet, address):
    coordinate = (sheet, address)
    assert coordinate in _guard_index(), f"Missing publisher guard: {sheet}!{address}"
    spec, expected, label = _guard_index()[coordinate]
    resolve_source_record(_cells(), spec, cells_by_sheet_address=_cell_index())
    assert _cell_index()[coordinate].raw_value == expected
    changed_index = {
        **_cell_index(),
        coordinate: replace(
            _cell_index()[coordinate], raw_value="unexpected publisher layout"
        ),
    }
    with pytest.raises(ValueError, match=re.escape(label)):
        resolve_source_record(_cells(), spec, cells_by_sheet_address=changed_index)


def test_taxable_income_build_suite_passes_source_acceptance_gates(tmp_path):
    report = build_source_suite(ALIAS, tmp_path / "suite", year=2024)
    assert report.valid
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
    assert not report.agent_acceptance.errors
    assert report.source_cells.cell_count == 32_261
    assert report.source_records.resolved_count == 3522
    assert report.source_records.lineage_coverage == 1
    assert report.consumer_facts.fact_count == 3522
    assert report.agent_acceptance.counts["raw_artifact_count"] == 1
    assert report.agent_acceptance.counts["raw_r2_link_count"] == 1
