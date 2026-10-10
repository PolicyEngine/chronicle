"""Publisher-cell fidelity for IRD's August 2026 wage and salary release."""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from dataclasses import replace
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

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
ALIAS = "ird-wage-salary-distribution-2026"
DIRECTORY = Path("ird/wage_salary_distribution_2026")
FILENAME = "wage-and-salary-distributions-for-individuals.xlsx"
SHA256 = "d0526b2092f9fa2bec44e11984c0ef17fda788a742c1c7054d416f6a0cd9e750"
SOURCE_URL = (
    "https://www.ird.govt.nz/-/media/project/ir/home/documents/about-us/"
    "tax-statistics---current/revenue-and-refunds/wage-and-salary/"
    f"wage-and-salary-statistics/{FILENAME}"
)
SOURCE_PAGE = (
    "https://www.ird.govt.nz/about-us/tax-statistics/revenue-refunds/"
    "wage-salary-distributions/wage-and-salary-statistics-datasets"
)
SHEET = "Tables - wage and salary"
RECORD_PREFIX = "ird_wage_salary_distribution.ty2026"
BAND_ROWS = tuple(range(7, 243))
DECILE_ROWS = tuple(range(255, 265))
PERCENTILE_ROWS = tuple(range(270, 280))

# Coordinates are independent of YAML: removing a guard cannot remove its
# regression case. All 236 bands and every selected quantile row are guarded.
EXPECTED_GUARDS = tuple(
    (SHEET, address)
    for address in sorted(
        {
            *(f"AM{row}" for row in BAND_ROWS),
            *(f"AM{row}" for row in DECILE_ROWS),
            *(f"AM{row}" for row in PERCENTILE_ROWS),
            "A1",
            "AM3",
            "AM4",
            "BB3",
            "BC2",
            "BB4",
            "BC4",
            "AM252",
            "BB251",
            "BB252",
            "BC252",
            "AM267",
            "BB266",
            "BB267",
            "BC267",
            "AM280",
            "AM281",
        }
    )
)


@lru_cache
def _package():
    # Scratch YAML is used only for the lane's explicit red demonstrations.
    return load_source_package(os.environ.get("CHRONICLE_NZ_WAGE_TEST_PACKAGE", ALIAS))


@lru_cache
def _cells():
    return _package().build_source_cells(2026)


@lru_cache
def _cell_index():
    return build_cells_by_sheet_address(_cells())


@lru_cache
def _specs():
    return _package().build_source_record_specs(2026)


@lru_cache
def _records():
    return _package().build_source_records(2026, cells=_cells())


@lru_cache
def _facts():
    return _package().build_facts(2026, cells=_cells())


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


def test_wage_salary_alias_and_package_validation():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == DIRECTORY
    assert _package().package_id == ALIAS
    report = validate_source_package(ALIAS, year=2026)
    assert report.valid
    assert not report.warnings
    assert report.counts == {
        "record_set_count": 5,
        "row_count": 274,
        "measure_count": 6,
        "source_record_count": 510,
        "source_region_count": 5,
    }


def test_wage_salary_publisher_artifact_and_receipt_are_pinned():
    data_dir = REPO_ROOT / "db" / "data" / DIRECTORY
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text())
    artifact = manifest["files"][2026]
    path = data_dir / FILENAME
    assert manifest["source_id"] == "ird"
    assert manifest["package_id"] == ALIAS
    assert manifest["license"] == "CC BY 4.0"
    assert artifact["filename"] == FILENAME
    assert artifact["source_url"] == SOURCE_URL
    assert manifest["source_page"] == SOURCE_PAGE
    assert artifact["sha256"] == SHA256
    assert artifact["fetched_at"] == "2026-10-10T08:31:07Z"
    assert artifact["size_bytes"] == path.stat().st_size == 198_542
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SHA256

    key = build_r2_key(
        source_id="ird",
        package_id=ALIAS,
        year=2026,
        sha256=SHA256,
        filename=FILENAME,
    )
    assert key == f"raw/nz/ird/{ALIAS}/2026/{SHA256}/{FILENAME}"
    storage = artifact["storage"]["r2"]
    assert storage == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }
    assert {fact.source.raw_r2_uri for fact in _facts()} == {storage["uri"]}


def test_wage_salary_preserves_all_four_complete_worksheet_ranges():
    cells = _cells()
    assert len(cells) == 20_631
    assert Counter(cell.sheet_name for cell in cells) == {
        "Explanatory Notes": 28 * 17,
        "Graphs - wage and salary": 1,
        SHEET: 282 * 57,
        "Graph data": 204 * 20,
    }
    assert validate_source_cells(cells).valid
    facts = _facts()
    assert len(facts) == 510
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert {fact.entity.name for fact in facts} == {"person"}
    assert {fact.provenance_class for fact in facts} == {"administrative"}
    assert {fact.assertion for fact in facts} == {"observation"}
    assert {fact.source.source_name for fact in facts} == {"ird"}
    assert {fact.source.source_sha256 for fact in facts} == {SHA256}
    assert {fact.source.source_size_bytes for fact in facts} == {198_542}
    assert {fact.source.url for fact in facts} == {SOURCE_URL}


def test_wage_salary_every_value_has_single_cell_lineage_and_exact_unit_scaling():
    cell_keys = {build_source_cell_key(cell) for cell in _cells()}
    records = {record.source_record_id: record for record in _records()}
    assert Counter(fact.layout.record_set_id for fact in _facts()) == {
        f"{RECORD_PREFIX}.income_bands": 236 * 2,
        f"{RECORD_PREFIX}.decile_boundaries": 9,
        f"{RECORD_PREFIX}.decile_income": 10,
        f"{RECORD_PREFIX}.percentile_boundaries": 9,
        f"{RECORD_PREFIX}.percentile_income": 10,
    }
    for fact in _facts():
        spec = records[fact.source_record_id].spec
        selector = spec.selector
        assert selector.end_address is None
        assert spec.divisor_selector is None
        assert spec.round_to is None
        income = fact.source_record_id.endswith(".wage_salary_income_nzd")
        assert spec.value_scale == (1_000_000 if income else 1)
        assert fact.measure.unit == ("count" if spec.unit == "count" else "nzd")
        assert fact.measure.concept_relation == "source_label"
        assert fact.aggregation.denominator is None
        raw = _cell_index()[(selector.sheet_name, selector.address)].raw_value
        decimal_product = Decimal(str(raw)) * Decimal(str(spec.value_scale))
        # Chronicle converts decimal-integral products to integers; every
        # non-integral cached numeric value keeps the native scaled float.
        expected = (
            int(decimal_product)
            if decimal_product == decimal_product.to_integral_value()
            else raw * spec.value_scale
        )
        assert fact.value == expected
        assert set(fact.source_cell_keys) <= cell_keys
        assert (
            build_source_cell_key(
                _cell_index()[(selector.sheet_name, selector.address)]
            )
            in fact.source_cell_keys
        )
        for address in (selector.expected_column_header_address,):
            assert address is not None
            assert (
                build_source_cell_key(_cell_index()[(selector.sheet_name, address)])
                in fact.source_cell_keys
            )
        for guard in selector.guard_cells:
            assert (
                build_source_cell_key(
                    _cell_index()[(selector.sheet_name, guard.address)]
                )
                in fact.source_cell_keys
            )


def test_wage_salary_tax_year_is_the_workbooks_ending_year():
    assert _cell_index()[(SHEET, "BB3")].raw_value == 2026
    assert _cell_index()[(SHEET, "BB251")].raw_value == 2026
    assert _cell_index()[(SHEET, "BB266")].raw_value == 2026
    assert _cell_index()[(SHEET, "BC2")].raw_value == "New"
    for fact in _facts():
        assert (fact.period.type, fact.period.value) == ("tax_year", 2026)
        assert (fact.geography.level, fact.geography.id, fact.geography.name) == (
            "country",
            "NZ",
            "New Zealand",
        )
        coverage = fact.period_coverage
        assert coverage.basis == "tax"
        assert coverage.start_date == "2025-04-01"
        assert coverage.end_date == "2026-03-31"
        assert "2026" in coverage.source_period_label
    assert {
        (fact.period.type, fact.period.value)
        for fact in _package().build_facts(2025, cells=_cells())
    } == {("tax_year", 2026)}


def test_wage_salary_all_dimensions_and_values_have_labels():
    assert _dimension_label_reports(ALIAS, consumer_fact_rows(_facts())) == ([], [])
    expected_labels = {
        "ird_wage_salary_distribution.income_band_row": "Published wage and salary income band",
        "ird_wage_salary_distribution.decile_row": "Published wage and salary decile",
        "ird_wage_salary_distribution.percentile_row": "Published wage and salary percentile",
        "wage_salary_band_source_label": "Published wage and salary income band",
        "wage_salary_decile": "Published wage and salary decile",
        "wage_salary_percentile": "Published wage and salary percentile",
    }
    assert _package().dimension_labels == expected_labels
    expected_groupbys = {
        "income_bands": "ird_wage_salary_distribution.income_band_row",
        "decile_boundaries": "ird_wage_salary_distribution.decile_row",
        "decile_income": "ird_wage_salary_distribution.decile_row",
        "percentile_boundaries": "ird_wage_salary_distribution.percentile_row",
        "percentile_income": "ird_wage_salary_distribution.percentile_row",
    }
    for fact in _facts():
        record_set = fact.layout.record_set_id.rsplit(".", 1)[1]
        assert fact.layout.groupby_dimension == expected_groupbys[record_set]
        assert fact.layout.groupby_dimension_label
        assert fact.dimension_value_labels[fact.layout.groupby_dimension] == {
            fact.layout.groupby_value_id: fact.layout.groupby_value_label,
        }
        for dimension, value in fact.filters.items():
            assert fact.dimension_labels[dimension] == expected_labels[dimension]
            assert _package().dimension_value_labels[dimension][str(value)] == str(
                value
            )
            assert fact.dimension_value_labels[dimension][str(value)] == str(value)


@pytest.mark.parametrize(
    ("record_set", "row", "measure", "address", "raw_value", "scale"),
    [
        ("income_bands", 242, "individuals", "BB242", 2_840_300, 1),
        (
            "income_bands",
            242,
            "wage_salary_income_nzd",
            "BC242",
            199691.51608914993,
            1_000_000,
        ),
        ("income_bands", 241, "individuals", "BB241", 980, 1),
        ("income_bands", 7, "individuals", "BB7", 81_400, 1),
        ("decile_boundaries", 255, "upper_boundary_nzd", "BB255", 6880.24, 1),
        (
            "decile_income",
            255,
            "wage_salary_income_nzd",
            "BC255",
            768.2012857799999,
            1_000_000,
        ),
        (
            "percentile_boundaries",
            278,
            "upper_boundary_nzd",
            "BB278",
            289185.87,
            1,
        ),
        (
            "percentile_income",
            279,
            "wage_salary_income_nzd",
            "BC279",
            13137.484879959999,
            1_000_000,
        ),
    ],
)
def test_wage_salary_exact_publisher_cell_anchors(
    record_set, row, measure, address, raw_value, scale
):
    fact = _fact(record_set, row, measure)
    record = next(
        record
        for record in _records()
        if record.source_record_id == fact.source_record_id
    )
    assert (record.spec.selector.sheet_name, record.spec.selector.address) == (
        SHEET,
        address,
    )
    assert _cell_index()[(SHEET, address)].raw_value == raw_value
    assert record.spec.value_scale == scale
    assert fact.value == raw_value * scale


def test_wage_salary_quantile_boundaries_are_cut_points_and_top_boundaries_absent():
    for record_set, rows, dimension, source_values in (
        ("decile_boundaries", range(255, 264), "wage_salary_decile", range(1, 10)),
        (
            "percentile_boundaries",
            range(270, 279),
            "wage_salary_percentile",
            range(91, 100),
        ),
    ):
        for row, source_value in zip(rows, source_values, strict=True):
            fact = _fact(record_set, row, "upper_boundary_nzd")
            assert fact.measure.unit == "nzd"
            assert fact.aggregation.method == "quantile"
            assert fact.filters == {dimension: source_value}
    for record_set, row, dimension, source_value in (
        ("decile", 264, "wage_salary_decile", 10),
        ("percentile", 279, "wage_salary_percentile", 100),
    ):
        assert _cell_index()[(SHEET, f"BB{row}")].raw_value is None
        assert (
            f"{RECORD_PREFIX}.{record_set}_boundaries.row_{row}.upper_boundary_nzd"
            not in _facts_by_id()
        )
        income = _fact(f"{record_set}_income", row, "wage_salary_income_nzd")
        assert income.filters == {dimension: source_value}
        assert income.aggregation.method == "sum"


def test_wage_salary_source_labels_stay_categorical_and_open_ended():
    assert _fact("income_bands", 7, "individuals").filters == {
        "wage_salary_band_source_label": "$1      -   $1,000"
    }
    assert _fact("income_bands", 241, "individuals").filters == {
        "wage_salary_band_source_label": "Over $1 million"
    }
    for fact in _facts():
        record_set = fact.layout.record_set_id.rsplit(".", 1)[1]
        dimension = (
            "wage_salary_band_source_label"
            if record_set == "income_bands"
            else "wage_salary_decile"
            if record_set.startswith("decile")
            else "wage_salary_percentile"
        )
        row = int(fact.layout.groupby_value_id.removeprefix("row_"))
        assert fact.filters == {dimension: _cell_index()[(SHEET, f"AM{row}")].raw_value}
        assert all(constraint.operator == "==" for constraint in fact.constraints)
        assert {
            constraint.variable: constraint.value for constraint in fact.constraints
        } == fact.filters
        assert set(fact.filters) <= {
            "wage_salary_band_source_label",
            "wage_salary_decile",
            "wage_salary_percentile",
        }


def test_wage_salary_separately_published_totals_are_separate_cell_facts():
    for fact in _facts():
        total = (
            fact.layout.record_set_id == f"{RECORD_PREFIX}.income_bands"
            and fact.layout.groupby_value_id == "row_242"
        )
        assert fact.layout.table_record_kind == ("total" if total else "detail")
        assert fact.aggregation.method == (
            "quantile" if ".upper_boundary_nzd" in fact.source_record_id else "sum"
        )
    for measure, address in (
        ("individuals", "BB242"),
        ("wage_salary_income_nzd", "BC242"),
    ):
        total = _fact("income_bands", 242, measure)
        record = next(
            record
            for record in _records()
            if record.source_record_id == total.source_record_id
        )
        assert record.spec.selector.address == address
        assert record.spec.selector.end_address is None
        assert total.filters == {"wage_salary_band_source_label": "Total"}


def test_wage_salary_preserves_revision_flags_and_drawing_note_without_reconciliation():
    assert {
        (column, _cell_index()[(SHEET, f"{column}2")].raw_value)
        for column in ("AW", "AY", "BA")
    } == {("AW", "R"), ("AY", "R"), ("BA", "R")}
    assert {
        _cell_index()[(SHEET, address)].raw_value for address in ("AV3", "AX3", "AZ3")
    } == {2023, 2024, 2025}
    path = REPO_ROOT / "db" / "data" / DIRECTORY / FILENAME
    with ZipFile(path) as archive:
        drawing = ElementTree.fromstring(archive.read("xl/drawings/drawing1.xml"))
    note = "".join(
        node.text or "" for node in drawing.iter() if node.tag.endswith("}t")
    )
    for phrase in (
        "gross earnings received from any employer",
        "New Zealand Superannuation",
        "Taxable welfare benefits",
        "Student allowances",
        "Earnings-related ACC payments",
        "Shareholder-employee salaries",
        "children with PAYE earnings",
        "From the 2016 March year onwards the data is based on data from the full population.",
        "17 August 2026",
        "Data for the 2022 to 2025 tax years has been revised",
    ):
        assert phrase in note
    assert {fact.period.value for fact in _facts()} == {2026}


def test_wage_salary_footnotes_are_preserved_in_income_and_boundary_lineage():
    expected = {
        "AM280": "* Each decile contains the wage and salary earning population divided by 10",
        "AM281": (
            "** Each percentile for the top 10% of wage and salary earners contains "
            "the wage and salary earning population divided by 100"
        ),
    }
    for address, value in expected.items():
        assert _cell_index()[(SHEET, address)].raw_value == value
    for fact in _facts():
        record_set = fact.layout.record_set_id.rsplit(".", 1)[1]
        if record_set.startswith("decile"):
            address = "AM280"
        elif record_set.startswith("percentile"):
            address = "AM281"
        else:
            continue
        assert (
            build_source_cell_key(_cell_index()[(SHEET, address)])
            in fact.source_cell_keys
        )


def test_wage_salary_bundle_coverage_delta_has_no_duplicate_keys():
    coverage = build_bundle_coverage(consumer_fact_rows(_facts()))
    assert coverage["fact_count"] == 510
    assert coverage["counts"]["by_source"] == {"ird": 510}
    assert coverage["counts"]["by_period"] == {"tax_year:2026": 510}
    assert coverage["counts"]["by_geography"] == {"country:NZ": 510}
    assert coverage["counts"]["by_entity"] == {"person": 510}
    assert list(coverage["counts"]["by_source_table"].values()) == [510]
    assert coverage["duplicates"] == {
        "aggregate_fact_keys": [],
        "semantic_fact_keys": [],
    }


def test_wage_salary_every_required_guard_is_declared():
    assert len(EXPECTED_GUARDS) == 273
    assert set(_guard_index()) == set(EXPECTED_GUARDS)


@pytest.mark.parametrize(
    ("sheet", "address"),
    EXPECTED_GUARDS,
    ids=[f"{sheet}:{address}" for sheet, address in EXPECTED_GUARDS],
)
def test_wage_salary_each_guard_rejects_mutated_publisher_cell(sheet, address):
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


def test_wage_salary_build_suite_passes_source_acceptance_gates(tmp_path):
    report = build_source_suite(ALIAS, tmp_path / "suite", year=2026)
    assert report.valid
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
    assert not report.agent_acceptance.errors
    assert report.source_cells.cell_count == 20_631
    assert report.source_records.resolved_count == 510
    assert report.source_records.lineage_coverage == 1
    assert report.consumer_facts.fact_count == 510
    assert report.agent_acceptance.counts["raw_artifact_count"] == 1
    assert report.agent_acceptance.counts["raw_r2_link_count"] == 1
