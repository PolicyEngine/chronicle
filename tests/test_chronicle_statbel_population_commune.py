"""Source-only checks for Statbel's 1 January 2025 commune population."""

from __future__ import annotations

import csv
import hashlib
import runpy
from collections import Counter, defaultdict
from dataclasses import replace
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile

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
from chronicle.sources.cells import build_source_cell_key, validate_source_cells

REPO_ROOT = Path(__file__).resolve().parents[1]
ALIAS = "statbel-population-structure-commune-2025"
PACKAGE_DIR = REPO_ROOT / "packages/statbel/population_structure_commune_2025"
DATA_DIR = REPO_ROOT / "db/data/statbel/population_structure_commune_2025"
CSV_PATH = DATA_DIR / "statbel_population_structure_commune_2025.csv"
NUTS1_DATA_DIR = REPO_ROOT / "db/data/statbel/population_structure_nuts1_2025"
RAW_PATH = NUTS1_DATA_DIR / "TF_SOC_POP_STRUCT_2025.zip"
MEMBER = "TF_SOC_POP_STRUCT_2025.txt"
RAW_SHA256 = "33910ea36437e39cfffd82ad82c759a2a8d1f2ab7662d45ce71c8ec9f336716c"
CURATED_SHA256 = "c2e08240e4b6820e81bbb7b8f3ec001605583bd6dbb43cf6871c0c65189ba1d6"
AGE_BOUNDS = {"0_17": (0, 18), "18_64": (18, 65), "65_plus": (65, None)}


def _csv_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _expanded_source_rows(value):
    """Interpret the CSV's physical TXT line references independently."""
    result = []
    for part in value.split(";"):
        endpoints = [int(endpoint) for endpoint in part.split("-")]
        assert len(endpoints) in {1, 2}
        assert endpoints[0] >= 2  # The publisher's header is physical line 1.
        if len(endpoints) == 1:
            result.append(endpoints[0])
        else:
            assert endpoints[1] > endpoints[0]
            result.extend(range(endpoints[0], endpoints[1] + 1))
    return result


@pytest.fixture(scope="module")
def curated_rows():
    return _csv_rows(CSV_PATH)


@pytest.fixture(scope="module")
def population():
    package = load_source_package(ALIAS)
    source_rows = package.build_source_rows(2025)
    cells = package.build_source_cells(2025, source_rows=source_rows)
    facts = package.build_facts(2025, source_rows=source_rows, cells=cells)
    return package, cells, facts


@pytest.fixture(scope="module")
def publisher_audit():
    """Audit every publisher row without importing the package generator."""
    values = Counter()
    line_numbers = defaultdict(list)
    region_by_code = {}
    with ZipFile(RAW_PATH) as archive:
        assert archive.namelist() == [MEMBER]
        with archive.open(MEMBER) as member:
            records = csv.DictReader(
                TextIOWrapper(member, encoding="utf-8-sig"), delimiter="|"
            )
            for line_number, record in enumerate(records, start=2):
                code = record["CD_REFNIS"]
                age = int(record["CD_AGE"])
                sex = {"M": "male", "F": "female"}[record["CD_SEX"]]
                band = "0_17" if age < 18 else "18_64" if age < 65 else "65_plus"
                count = int(record["MS_POPULATION"])
                region = {"04000": "BE1", "02000": "BE2", "03000": "BE3"}[
                    record["CD_RGN_REFNIS"]
                ]
                assert region_by_code.setdefault(code, region) == region
                for key in ((code, "", ""), (code, sex, band)):
                    values[key] += count
                    line_numbers[key].append(line_number)
    return values, line_numbers, region_by_code


def test_alias_and_package_validation_preserve_the_complete_commune_table():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == Path(
        "statbel/population_structure_commune_2025"
    )
    report = validate_source_package(ALIAS, year=2025)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["record_set_count"] == 7
    assert report.counts["row_count"] == report.counts["source_record_count"] == 3955
    source = (PACKAGE_DIR / "source_package.yaml").read_text()
    payload = yaml.safe_load(source)
    assert payload["schema_version"] == "ledger.source_package.v1"
    assert all(
        record_set["provenance_class"] == "census"
        for record_set in payload["record_sets"]
    )
    assert (
        sum(line.strip() == "provenance_class: census" for line in source.splitlines())
        == 7
    )
    assert not any(
        isinstance(token, (yaml.AliasToken, yaml.AnchorToken))
        for token in yaml.scan(source)
    )


def test_artifact_hashes_and_declared_storage_reuse_the_captured_zip():
    manifest = yaml.safe_load((DATA_DIR / "manifest.yaml").read_text())
    assert manifest["source_id"] == "belgium"
    assert manifest["package_id"] == ALIAS
    entry = manifest["files"][2025]
    content = CSV_PATH.read_bytes()
    assert entry["filename"] == CSV_PATH.name
    assert hashlib.sha256(content).hexdigest() == entry["sha256"] == CURATED_SHA256
    assert len(content) == entry["size_bytes"] == 4_519_597
    expected_key = f"raw/belgium/{ALIAS}/2025/{entry['sha256']}/{CSV_PATH.name}"
    assert entry["storage"]["r2"]["key"] == expected_key
    assert entry["storage"]["r2"]["uri"] == f"r2://ledger-raw/{expected_key}"
    assert set(manifest["files"]) == {2025}
    capture = manifest["source_capture_reference"]
    assert (DATA_DIR / capture["manifest"]).resolve() == (
        NUTS1_DATA_DIR / "manifest.yaml"
    ).resolve()
    assert capture["manifest_entry"] == "source_capture"
    assert (DATA_DIR / capture["filename"]).resolve() == RAW_PATH.resolve()
    assert (
        capture["sha256"]
        == hashlib.sha256(RAW_PATH.read_bytes()).hexdigest()
        == RAW_SHA256
    )
    assert capture["size_bytes"] == RAW_PATH.stat().st_size
    existing = yaml.safe_load((NUTS1_DATA_DIR / "manifest.yaml").read_text())
    assert (
        capture["storage"]["r2"] == existing["files"]["source_capture"]["storage"]["r2"]
    )


def test_each_curated_value_and_line_reference_matches_publisher_rows(
    curated_rows, publisher_audit
):
    values, source_lines, region_by_code = publisher_audit
    actual_keys = set()
    source_url = yaml.safe_load((NUTS1_DATA_DIR / "manifest.yaml").read_text())[
        "files"
    ]["source_capture"]["source_url"]
    for row in curated_rows:
        key = (row["geography_id"], row["person.sex"], row["person.age_band"])
        assert key not in actual_keys
        actual_keys.add(key)
        assert int(row["value"]) == values[key]
        assert _expanded_source_rows(row["source_rows"]) == source_lines[key]
        assert row["nuts1_id"] == region_by_code[row["geography_id"]]
        assert row["source_member"] == MEMBER
        assert row["source_sha256"] == RAW_SHA256
        assert row["source_url"] == source_url
    assert actual_keys == set(values)
    assert len(actual_keys) == 3955


def test_publisher_codes_are_already_nis_2025_and_names_follow_statbel_conventions(
    curated_rows, publisher_audit
):
    _, _, region_by_code = publisher_audit
    crosswalk = _csv_rows(
        REPO_ROOT
        / "db/data/statbel/nis_2025_commune_crosswalk/statbel_nis_2025_commune_crosswalk.csv"
    )
    fiscal = _csv_rows(
        REPO_ROOT
        / "db/data/statbel/fiscal_income_commune_2023_nis_2025/statbel_fiscal_income_commune_2023_nis_2025.csv"
    )
    target_codes = {row["target_nis"] for row in crosswalk}
    source_codes = {row["source_nis"] for row in crosswalk}
    names = {row["geography_id"]: row["geography_name"] for row in fiscal}
    actual_codes = {row["geography_id"] for row in curated_rows}
    assert len(source_codes) == 581
    assert len(actual_codes) == 565
    assert actual_codes == set(region_by_code) == target_codes == set(names)
    assert "11007" not in actual_codes  # Borsbeek is already included in Antwerpen.
    assert {
        "82039",
        "46030",
    } <= actual_codes  # Bastogne and Beveren-Kruibeke-Zwijndrecht.
    assert Counter(row["geography_id"] for row in curated_rows) == {
        code: 7 for code in actual_codes
    }
    for row in curated_rows:
        assert row["geography_name"] == names[row["geography_id"]]
        assert row["geography_vintage"] == "nis_2025"
        assert row["geography_level"] == "commune"
        assert row["period"] == "2025"


def test_commune_components_and_every_nuts1_age_sex_fact_reconcile_exactly(
    curated_rows,
):
    totals = Counter()
    components = Counter()
    by_nuts1 = Counter()
    for row in curated_rows:
        value = int(row["value"])
        if row["person.sex"]:
            components[row["geography_id"]] += value
            by_nuts1[(row["nuts1_id"], row["person.sex"], row["person.age_band"])] += (
                value
            )
        else:
            assert row["person.age_band"] == ""
            assert row["age"] == "All ages"
            totals[row["geography_id"]] += value
    nuts1 = load_source_package("statbel-population-structure-2025").build_facts(2025)
    expected = {
        (
            fact.geography.id,
            fact.filters["person.sex"],
            fact.filters["person.age_band"],
        ): fact.value
        for fact in nuts1
    }
    assert totals == components
    assert dict(by_nuts1) == expected
    assert sum(totals.values()) == sum(expected.values()) == 11_825_551


def test_facts_preserve_count_semantics_constraints_and_cell_lineage(
    population, curated_rows
):
    package, cells, facts = population
    assert len(facts) == 3955
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    cell_keys = {build_source_cell_key(cell) for cell in cells}
    by_key = {
        (row["geography_id"], row["person.sex"], row["person.age_band"]): row
        for row in curated_rows
    }
    for fact in facts:
        key = (
            fact.geography.id,
            fact.filters.get("person.sex", ""),
            fact.filters.get("person.age_band", ""),
        )
        assert fact.value == int(by_key[key]["value"])
        assert type(fact.value) is int
        assert fact.entity.name == "person"
        assert fact.measure.concept == "people"
        assert fact.measure.unit == "count"
        assert fact.aggregation.method == "sum"
        assert fact.provenance_class == "census"
        assert fact.assertion == "observation"
        assert (fact.period.type, fact.period.value) == ("calendar_year", 2025)
        assert fact.period_coverage is not None
        assert (
            fact.period_coverage.start_date
            == fact.period_coverage.end_date
            == "2025-01-01"
        )
        assert fact.period_coverage.basis == "calendar"
        assert (
            fact.period_coverage.source_period_label == "Population on 1 January 2025"
        )
        assert fact.geography.level == "commune"
        assert fact.geography.vintage == "nis_2025"
        assert fact.source_record_id
        assert fact.source_row_keys
        assert fact.source_cell_keys
        assert set(fact.source_cell_keys) <= cell_keys
        constraints = {
            (constraint.variable, constraint.operator, constraint.value)
            for constraint in fact.constraints
        }
        if key[1]:
            lower, upper = AGE_BOUNDS[key[2]]
            assert ("person.sex", "==", key[1]) in constraints
            assert ("person.age_band", "==", key[2]) in constraints
            assert ("person.age", ">=", lower) in constraints
            assert {
                (variable, operator, value)
                for variable, operator, value in constraints
                if variable == "person.age" and operator == "<"
            } == (set() if upper is None else {("person.age", "<", upper)})
        else:
            assert not fact.filters
            assert not fact.constraints
            assert fact.layout.table_record_kind == "total"
    assert package.artifact.artifact_year == 2025


def test_consumer_identity_labels_and_source_only_contract(population):
    _, _, facts = population
    rows = consumer_fact_rows(facts)
    assert len({row["aggregate_fact_key"] for row in rows}) == 3955
    assert len({row["semantic_fact_key"] for row in rows}) == 3955
    assert _dimension_label_reports(ALIAS, rows) == ([], [])
    for row in rows:
        assert row["lineage"]["source_record_id"]
        assert row["lineage"]["source_cell_keys"]
        assert row["source"]["raw_r2_key"].startswith(f"raw/belgium/{ALIAS}/2025/")
        assert (
            not {"target", "solver", "calibration", "uprating_factor", "weight"}
            & row.keys()
        )


def test_source_only_coverage_matches_measured_bundle_contribution(population):
    # The package-only suite measured these contributions at build year 2025;
    # the immutable observations retain their 1 January 2025 reference date.
    _, _, facts = population
    coverage = build_bundle_coverage(consumer_fact_rows(facts))
    assert coverage["fact_count"] == 3955
    assert coverage["counts"]["by_source"] == {"statbel_population_structure": 3955}
    assert coverage["counts"]["by_source_table"] == {
        "statbel_population_structure:Population by place of residence, nationality, "
        "marital status, age and sex, 2025, NIS 2025 communes": 3955
    }
    assert coverage["counts"]["by_period"] == {"calendar_year:2025": 3955}
    assert coverage["counts"]["by_entity"] == {"person": 3955}
    assert len(coverage["counts"]["by_geography"]) == 565
    assert set(coverage["counts"]["by_geography"].values()) == {7}
    assert coverage["counts"]["by_geography"]["commune:11002"] == 7
    assert not coverage["duplicates"]["aggregate_fact_keys"]
    assert not coverage["duplicates"]["semantic_fact_keys"]


def test_curated_and_package_generation_reproduces_committed_bytes():
    generator = runpy.run_path(str(PACKAGE_DIR / "build_package.py"))
    outputs = generator["render_outputs"]()
    assert CSV_PATH in outputs
    assert DATA_DIR / "manifest.yaml" in outputs
    assert PACKAGE_DIR / "source_package.yaml" in outputs
    assert len(outputs) == 3
    for path, expected in outputs.items():
        assert path.read_bytes() == expected, path.relative_to(REPO_ROOT)


def test_geography_guard_rejects_semantic_drift(population):
    package, cells, _ = population
    changed = [
        replace(cell, raw_value="99999", display_value="99999")
        if cell.address == "C2"
        else cell
        for cell in cells
    ]
    with pytest.raises(ValueError, match="expected"):
        package.build_facts(2025, cells=changed)
