"""Source-only regression gates for the partial 30 June 2025 NZ population package."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, replace
import hashlib
import html
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys

import openpyxl
import pytest
import yaml

from chronicle.bundle import (
    _cross_package_dimension_label_errors,
    _dimension_label_reports,
    build_bundle,
    build_bundle_coverage,
)
from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.dimension_labels import dimension_labels_by_id
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources.cells import build_source_cell_key, validate_source_cells

ALIAS = "stats-nz-subnational-population-estimates-2025"
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "db" / "data" / "stats_nz"
WORKBOOK_SHA256 = "001e8a896cfb50f5ed17836dc815b235e3bcca55ee91c9869a2afaeb054b50a6"
REGC_SHA256 = "e5d53fa6abf742121d123bff970c77658a16e8c9b405b83d1a978cc22920d660"
NATIONAL_PAGE_SHA256 = (
    "b2d2751800857895b1498d87df6f03ac3511ec8c7a9b17cc3150c8ab56533053"
)
# Order and rows are from Tables 1 and 3 of the pinned publisher workbook.
REGIONS = (
    ("01", 7, 10),
    ("02", 8, 13),
    ("03", 9, 16),
    ("04", 10, 19),
    ("05", 11, 22),
    ("06", 12, 25),
    ("07", 13, 28),
    ("08", 14, 31),
    ("09", 15, 34),
    ("16", 16, 37),
    ("17", 17, 40),
    ("18", 18, 43),
    ("12", 19, 46),
    ("13", 20, 49),
    ("14", 21, 52),
    ("15", 22, 55),
    ("NZ", 25, 64),
)
# These are the source's four broad bands, not five-year-age target bands.
AGE_BANDS = {
    "0_14": ("D", 0, 15),
    "15_39": ("E", 15, 40),
    "40_64": ("F", 40, 65),
    "65_plus": ("G", 65, None),
}
# Each band's value cells: Table 1 holds all ages, Table 3 the broad bands.
BAND_COLUMNS = {
    "all": ("Table 1", "D"),
    **{band: ("Table 3", column) for band, (column, *_) in AGE_BANDS.items()},
}
NATIONAL_ROWS = {"Table 1": 25, "Table 3": 64}
BOUNDARY_FOOTNOTES = {"Table 1": "A29", "Table 3": "A68"}
# Other packages that emit this package's person.age_band dimension.
STATBEL_POPULATION_ALIASES = (
    "statbel-population-structure-2025",
    "statbel-population-structure-2026",
)


def _artifact(package_name):
    directory = DATA_ROOT / package_name
    manifest = yaml.safe_load((directory / "manifest.yaml").read_text())
    entry = manifest["files"][2025]
    return (directory / entry["filename"]).read_bytes(), entry


def _build_digests(cells, facts):
    """Return the SHA-256 of each serialized build output: cells, facts, rows."""

    def digest(lines):
        return hashlib.sha256("\n".join(lines).encode()).hexdigest()

    def dumped(item):
        return json.dumps(asdict(item), sort_keys=True, default=str)

    return {
        "source_cells": digest(dumped(cell) for cell in cells),
        "facts": digest(dumped(fact) for fact in facts),
        "consumer_rows": digest(
            json.dumps(row, sort_keys=True) for row in consumer_fact_rows(facts)
        ),
    }


_REBUILD_SCRIPT = f"""
import json
from chronicle.source_package import load_source_package
from tests.test_chronicle_nz_population import _build_digests
package = load_source_package({ALIAS!r})
cells = package.build_source_cells(2025)
print(json.dumps(_build_digests(cells, package.build_facts(2025, cells=cells))))
"""


@pytest.fixture(scope="module")
def population():
    package = load_source_package(ALIAS)
    cells = package.build_source_cells(2025)
    facts = package.build_facts(2025, cells=cells)
    return package, cells, facts


@pytest.fixture(scope="module")
def workbook():
    content, _ = _artifact("subnational_population_estimates_2025")
    book = openpyxl.load_workbook(BytesIO(content), data_only=True)
    yield book
    book.close()


@pytest.mark.parametrize(
    ("package_name", "expected_sha", "expected_size"),
    [
        ("subnational_population_estimates_2025", WORKBOOK_SHA256, 97990),
        ("regional_council_2025_codes", REGC_SHA256, 3381),
        ("national_population_estimates_2025", NATIONAL_PAGE_SHA256, 61286),
    ],
)
def test_publisher_artifact_bytes_and_country_storage_are_pinned(
    package_name, expected_sha, expected_size
):
    content, entry = _artifact(package_name)
    assert hashlib.sha256(content).hexdigest() == entry["sha256"] == expected_sha
    assert len(content) == entry["size_bytes"] == expected_size
    assert entry["storage"]["r2"]["uri"].startswith(
        f"r2://ledger-raw/raw/nz/stats_nz/{package_name}/2025/{expected_sha}/"
    )


def test_partial_package_counts_and_whole_sheet_preservation(population):
    package, cells, facts = population
    report = validate_source_package(ALIAS, year=2025)
    assert report.valid
    assert not report.warnings
    assert report.counts["record_set_count"] == 5
    assert report.counts["source_record_count"] == len(facts) == 85
    assert "partial" in package.label.lower()
    assert package.artifact.sheets == ("Table 1", "Table 3")
    # Full used ranges, including unused years and source footnotes: 35x9 + 75x26.
    assert len(cells) == 2265
    assert Counter(cell.sheet_name for cell in cells) == {
        "Table 1": 315,
        "Table 3": 1950,
    }
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid


def test_every_fact_equals_one_published_cell_with_no_scaling(population, workbook):
    package, cells, facts = population
    actual = {
        (fact.geography.id, fact.filters.get("person.age_band", "all")): fact
        for fact in facts
    }
    cell_keys = {build_source_cell_key(cell) for cell in cells}
    assert len(actual) == 85
    for geography_id, total_row, broad_age_row in REGIONS:
        assert (
            actual[(geography_id, "all")].value
            == workbook["Table 1"][f"D{total_row}"].value
        )
        for age_band, (column, _lower, _upper) in AGE_BANDS.items():
            assert (
                actual[(geography_id, age_band)].value
                == workbook["Table 3"][f"{column}{broad_age_row}"].value
            )
    for fact, spec in zip(facts, package.build_source_record_specs(2025), strict=True):
        assert spec.value_scale == 1
        assert spec.divisor_selector is None
        assert spec.round_to is None
        assert spec.selector.end_address is None
        assert fact.source_record_id == spec.source_record_id
        assert fact.source_cell_keys
        assert set(fact.source_cell_keys) <= cell_keys
        assert fact.source.source_sha256 == WORKBOOK_SHA256
        assert fact.aggregation.method == "sum"
        assert fact.measure.unit == "count"
        assert type(fact.value) is int


def test_regc_codes_and_names_match_official_2025_classification(population):
    _package, _cells, facts = population
    content, _ = _artifact("regional_council_2025_codes")
    classification = json.loads(content)
    assert not classification.get("exceededTransferLimit", False)
    codes = {
        row["attributes"]["REGC2025_V1_00"]: row["attributes"]["REGC2025_V1_00_NAME"]
        for row in classification["features"]
    }
    assert len(codes) == 17  # Sixteen regions plus publisher code 99 (outside region).
    regional_facts = [fact for fact in facts if fact.geography.level == "region"]
    assert {fact.geography.id for fact in regional_facts} == codes.keys() - {"99"}
    assert len(regional_facts) == 80
    assert all(fact.geography.vintage == "regc_2025" for fact in regional_facts)
    assert all(
        fact.geography.name == codes[fact.geography.id] for fact in regional_facts
    )
    assert (
        codes["02"] == "Auckland"
    )  # Workbook calls the same region "Auckland region".


def test_national_total_is_published_not_reconciled_from_regions(population, workbook):
    _package, _cells, facts = population
    totals = {fact.geography.id: fact for fact in facts if not fact.filters}
    # Table 1 footnote 3 includes areas outside a region (for example Chatham).
    assert totals["NZ"].value == workbook["Table 1"]["D25"].value == 5_324_700
    assert totals["NZ"].value != sum(
        fact.value for code, fact in totals.items() if code != "NZ"
    )
    assert "99" not in totals  # Do not construct an outside-region residual.
    assert totals["NZ"].geography.level == "country"
    assert totals["NZ"].source_record_id.endswith(".all_ages.nz.population")


def test_each_fact_reads_its_own_cell_and_regions_never_feed_the_nation(
    population,
):
    package, cells, facts = population
    cells_by_key = {build_source_cell_key(cell): cell for cell in cells}
    specs = package.build_source_record_specs(2025)
    value_cells = {}
    for fact, spec in zip(facts, specs, strict=True):
        # The first lineage key is the one value cell; the rest are its column
        # header and guard cells, all of them text.
        value_cell, *context_cells = (
            cells_by_key[key] for key in fact.source_cell_keys
        )
        assert (value_cell.sheet_name, value_cell.address) == (
            spec.selector.sheet_name,
            spec.selector.address,
        )
        assert value_cell.raw_value == fact.value
        assert all(type(cell.raw_value) is str for cell in context_cells)
        value_cells[fact.source_record_id] = fact.source_cell_keys[0]
    assert len(set(value_cells.values())) == len(facts) == 85

    for band, (sheet, column) in BAND_COLUMNS.items():
        band_facts = [
            fact for fact in facts if fact.filters.get("person.age_band", "all") == band
        ]
        regional = [fact for fact in band_facts if fact.geography.level == "region"]
        (national,) = [fact for fact in band_facts if fact.geography.id == "NZ"]
        assert len(regional) == 16
        assert len({fact.geography.id for fact in regional}) == 16
        # The nation is its own fact, read from its own published cell.
        national_cell = cells_by_key[national.source_cell_keys[0]]
        assert (national_cell.sheet_name, national_cell.address) == (
            sheet,
            f"{column}{NATIONAL_ROWS[sheet]}",
        )
        regional_value_keys = {fact.source_cell_keys[0] for fact in regional}
        assert not set(national.source_cell_keys) & regional_value_keys


def test_every_row_records_reference_date_and_regc_2025_boundaries(population):
    _package, cells, facts = population
    footnotes = {
        build_source_cell_key(cell)
        for cell in cells
        if BOUNDARY_FOOTNOTES.get(cell.sheet_name) == cell.address
    }
    assert {
        cell.raw_value
        for cell in cells
        if BOUNDARY_FOOTNOTES.get(cell.sheet_name) == cell.address
    } == {"2. Boundaries at 1 January 2025."}
    assert len(footnotes) == 2
    rows = consumer_fact_rows(facts)
    assert len(rows) == 85
    for row in rows:
        coverage = row["period_coverage"]
        assert coverage["start_date"] == coverage["end_date"] == "2025-06-30"
        assert row["period"] == {"type": "calendar_year", "value": 2025}
        # Each row's lineage carries its table's boundary footnote.
        assert len(footnotes & set(row["lineage"]["source_cell_keys"])) == 1
        notes = row["concept_alignment"]["evidence_notes"]
        assert "1 January 2025 boundaries" in notes
        geography = row["geography"]
        if geography["level"] == "region":
            assert geography["vintage"] == "regc_2025"
        else:
            # New Zealand is the country, not a REGC 2025 area; its boundary is
            # the footnote in its lineage.
            assert (geography["level"], geography["id"], geography["vintage"]) == (
                "country",
                "NZ",
                "current",
            )


def test_rebuilding_the_package_is_byte_identical(population):
    # Rebuild in fresh interpreters with different hash seeds, so that set or
    # dict ordering cannot make a build differ from the in-process one.
    _package, cells, facts = population
    expected = _build_digests(cells, facts)
    for seed in ("1", "2"):
        completed = subprocess.run(
            [sys.executable, "-c", _REBUILD_SCRIPT],
            capture_output=True,
            check=True,
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed},
            text=True,
        )
        assert json.loads(completed.stdout.splitlines()[-1]) == expected


def test_age_universes_are_only_published_broad_bands_and_all_sexes(population):
    _package, _cells, facts = population
    assert {fact.filters.get("person.age_band", "all") for fact in facts} == {
        "all",
        *AGE_BANDS,
    }
    for fact in facts:
        assert "person.sex" not in fact.filters
        assert not any(
            constraint.variable == "person.sex" for constraint in fact.constraints
        )
        assert fact.entity.name == "person"
        assert fact.entity.role == "resident_population"
        if not fact.filters:
            assert not fact.constraints
            continue
        _column, lower, upper = AGE_BANDS[fact.filters["person.age_band"]]
        age_constraints = {
            (item.operator, item.value, item.unit)
            for item in fact.constraints
            if item.variable == "person.age"
        }
        expected = {(">=", lower, "years")}
        if upper is not None:
            expected.add(("<", upper, "years"))
        assert age_constraints == expected


@pytest.mark.parametrize("requested_year", [2023, 2025, 2026])
def test_requested_build_year_cannot_uprate_or_relabel_pinned_vintage(
    population, requested_year
):
    package, cells, original = population
    facts = package.build_facts(requested_year, cells=cells)
    assert facts == original
    assert package.artifact.artifact_year == 2025
    for fact in facts:
        assert fact.period.type == "calendar_year"
        assert fact.period.value == 2025
        assert fact.period_coverage.start_date == "2025-06-30"
        assert fact.period_coverage.end_date == "2025-06-30"
        assert fact.period_coverage.basis == "calendar"
        assert (
            fact.period_coverage.source_period_label == "At 30 June 2025 (provisional)"
        )
        assert fact.source.vintage == "stats_nz_subnational_population_2025_10_29"
        assert fact.assertion == "observation"
        assert fact.provenance_class == "census"


@pytest.mark.parametrize(
    ("sheet", "address", "replacement"),
    [
        ("Table 1", "D6", "2026 P"),
        ("Table 1", "A7", "Auckland region"),
        ("Table 1", "A4", "Year ended 30 June 2023–2025"),
        ("Table 1", "A29", "2. Boundaries at 1 January 2026."),
        ("Table 1", "A34", "F final"),
        ("Table 3", "C13", "2024 P"),
        ("Table 3", "A13", "Northland region"),
        ("Table 3", "E6", "15–64"),
        ("Table 3", "G6", "60+"),
        ("Table 3", "A68", "2. Boundaries at 1 January 2026."),
        ("Table 3", "A74", "F final"),
    ],
)
def test_source_semantic_drift_fails_closed(population, sheet, address, replacement):
    package, cells, _facts = population
    mutated = [
        replace(cell, raw_value=replacement, display_value=replacement)
        if (cell.sheet_name, cell.address) == (sheet, address)
        else cell
        for cell in cells
    ]
    with pytest.raises(ValueError, match="expected"):
        package.build_facts(2025, cells=mutated)


def test_consumer_rows_preserve_source_only_scope_and_lineage(population):
    _package, _cells, facts = population
    rows = consumer_fact_rows(facts)
    assert validate_consumer_fact_contract(facts).valid
    assert len({row["aggregate_fact_key"] for row in rows}) == 85
    assert len({row["semantic_fact_key"] for row in rows}) == 85
    for row in rows:
        assert row["concept_alignment"]["relation"] == "source_label"
        notes = row["concept_alignment"]["evidence_notes"]
        assert "not five-year or single-year ages" in notes
        assert "there is no sex-specific split" in notes
        assert "outside regions" in notes
        assert row["source"]["raw_r2_key"].startswith("raw/nz/stats_nz/")
        assert row["lineage"]["source_cell_keys"]
        assert row["lineage"]["source_record_id"]
        assert (
            not {"target", "solver", "calibration", "uprating_factor", "weight"}
            & row.keys()
        )


def test_national_landing_page_is_evidence_not_an_age_table_package():
    content, _ = _artifact("national_population_estimates_2025")
    page = html.unescape(content.decode()).replace("\\/", "/")
    assert "single-year of age" in page
    assert "Infoshare" in page
    assert "2025-08-19 10:45:00" in page
    assert "DocumentBlock" not in page
    assert "stats-nz-national-population-estimates-2025" not in SOURCE_PACKAGE_ALIASES
    assert not (
        REPO_ROOT
        / "packages/stats_nz/national_population_estimates_2025/source_package.yaml"
    ).exists()


def test_explicit_single_package_bundle_passes_all_source_gates(tmp_path):
    report = build_bundle(tmp_path / "bundle", sources=[ALIAS], year=2025)
    assert report.valid
    rows = [
        json.loads(line)
        for line in (tmp_path / "bundle/consumer_facts.jsonl").read_text().splitlines()
    ]
    coverage = build_bundle_coverage(rows)
    assert coverage["fact_count"] == 85
    assert coverage["counts"]["by_source"] == {"stats_nz": 85}
    assert coverage["counts"]["by_period"] == {"calendar_year:2025": 85}
    assert coverage["counts"]["by_geography"]["country:NZ"] == 5
    assert len(coverage["counts"]["by_geography"]) == 17
    assert not coverage["duplicates"]["aggregate_fact_keys"]
    assert not coverage["duplicates"]["semantic_fact_keys"]


def test_every_dimension_and_value_carries_one_bundle_label(population, workbook):
    # build-bundle refuses a package that leaves a dimension or value without a
    # Chronicle label (chronicle#261, #265).
    _package, _cells, facts = population
    assert _dimension_label_reports(ALIAS, consumer_fact_rows(facts)) == ([], [])
    for fact in facts:
        assert fact.dimension_labels["geography"] == "Geography"
        assert fact.layout.groupby_dimension_label == "Geography"
        band = fact.filters.get("person.age_band")
        if band is None:
            assert "person.age_band" not in fact.dimension_labels
            continue
        column = AGE_BANDS[band][0]
        assert fact.dimension_labels["person.age_band"] == "Age band"
        # The value label is the publisher's own column header, Table 3!D6:G6.
        assert fact.dimension_value_labels["person.age_band"] == {
            band: workbook["Table 3"][f"{column}6"].value
        }


def test_person_age_band_keeps_the_label_statbel_gives_it():
    # One dimension id carries one label across the bundle (chronicle#265), and
    # Statbel's population-structure packages are the other packages on main
    # that emit person.age_band. The default-bundle test covers `geography`.
    labels = {}
    for alias in (ALIAS, *STATBEL_POPULATION_ALIASES):
        package = load_source_package(alias)
        rows = consumer_fact_rows(package.build_facts(package.artifact.artifact_year))
        for dimension_id, found in dimension_labels_by_id(rows).items():
            for label in found:
                labels.setdefault(dimension_id, {}).setdefault(label, []).append(alias)
    assert labels["person.age_band"] == {
        "Age band": [ALIAS, *STATBEL_POPULATION_ALIASES]
    }
    assert _cross_package_dimension_label_errors(labels) == []
