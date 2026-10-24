"""Publisher-backed 2020–2024 ACS 5-year detailed tables for US counties."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

from chronicle.concepts import validate_concept_alignments
from chronicle.consumer_contract import validate_consumer_fact_contract
from chronicle.core import AggregateFact, validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    SourcePackage,
    load_source_package,
    validate_source_package,
)
from chronicle.sources import census_acs5_county
from chronicle.sources.cells import (
    SourceCell,
    build_source_cell_key,
    validate_source_cells,
)
from chronicle.sources.rows import (
    SourceRow,
    build_source_row_key,
    validate_source_rows,
)
from chronicle.sources.specs import (
    compile_source_record_set_specs,
    source_regions_from_record_set_spec,
)
from chronicle.suite import (
    build_agent_acceptance_report,
    validate_source_record_specs,
    validate_source_regions,
)
from chronicle.yaml_io import safe_load as safe_load_yaml

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("B01003", "B11001", "B19001", "B19013", "B19025", "B19051", "B19061")
COUNTY_COUNT = 3_144
CT_REGIONS = {f"0500000US09{code}" for code in range(110, 191, 10)}
SHA256 = {
    "B01003": "c83ef6e45601455855312f2e26ea755cd43a7c65ee58662e4cb4fad122a70bf2",
    "B11001": "a0c2f64ad5f7172cded551364fc15d6bc37bbbc75ac135f7be00c8622d31d01a",
    "B19001": "731d54b9443455987e088c4e65c848034c99ef19fb20aef60b87dc481450b3c2",
    "B19013": "c574579d1f648472db366ea4726630c15f8d295ff9294e7dc9156b461d7e83a1",
    "B19025": "8def9b6a5684a4b499d3ed0e23737358882ea4ad5627a06f7db5a63114bf7589",
    "B19051": "919b6abbf7e46452761a04b1051a3e6bf085808b2d251a554d10f82940c4f5d3",
    "B19061": "d3948e8118f7a5c5bbd82d2802591bb6edf184e012e227b478d71edd860f59f4",
}
FACT_COUNTS = {
    "B01003": 3_274,
    "B11001": 18_864,
    "B19001": 106_896,
    "B19013": 6_286,
    "B19025": 6_288,
    "B19051": 18_864,
    "B19061": 6_288,
}
INCOME_BOUNDS = (
    (None, 10_000),
    (10_000, 15_000),
    (15_000, 20_000),
    (20_000, 25_000),
    (25_000, 30_000),
    (30_000, 35_000),
    (35_000, 40_000),
    (40_000, 45_000),
    (45_000, 50_000),
    (50_000, 60_000),
    (60_000, 75_000),
    (75_000, 100_000),
    (100_000, 125_000),
    (125_000, 150_000),
    (150_000, 200_000),
    (200_000, None),
)


def _package_id(table: str) -> str:
    return f"census-acs5-{table.lower()}-county-2024"


def _directory(table: str) -> Path:
    return Path(f"census/acs5_{table.lower()}_county_2024")


def _data_directory(table: str) -> Path:
    return ROOT / "db/data" / _directory(table)


def _raw_table(table: str) -> list[list[Any]]:
    path = _data_directory(table) / f"acs5_2024_{table}_county.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _publisher_rows(table: str) -> list[dict[str, Any]]:
    header, *rows = _raw_table(table)
    return [dict(zip(header, row, strict=True)) for row in rows]


def _scalar(value: Any) -> Any:
    """Account for the established JSON table parser's numeric normalization."""
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return value


def _variables(table: str) -> list[str]:
    indices = {
        "B11001": (1, 2, 7),
        "B19001": range(1, 18),
        "B19051": (1, 2, 3),
    }.get(table, (1,))
    return [f"{table}_{index:03}{suffix}" for index in indices for suffix in "EM"]


@dataclass
class CountyPackage:
    table: str
    package: SourcePackage
    rows: list[SourceRow]
    cells: list[SourceCell]
    facts: list[AggregateFact]


@pytest.fixture(scope="module", params=TABLES)
def county_package(request) -> CountyPackage:
    table = request.param
    package = load_source_package(_package_id(table))
    rows = package.build_source_rows(2024)
    cells = package.build_source_cells(2024, source_rows=rows)
    facts = package.build_facts(2024, source_rows=rows, cells=cells)
    return CountyPackage(table, package, rows, cells, facts)


@pytest.mark.parametrize("table", TABLES)
def test_pinned_bytes_manifests_and_deterministic_generation(table):
    assert SOURCE_PACKAGE_ALIASES[_package_id(table)] == _directory(table)
    data_dir = _data_directory(table)
    manifest = safe_load_yaml((data_dir / "manifest.yaml").read_text())
    artifact = manifest["files"][2024]
    content = (data_dir / artifact["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == artifact["sha256"] == SHA256[table]
    assert len(content) == artifact["size_bytes"]
    assert manifest["reference_period"] == "2020–2024"
    url = artifact["source_url"]
    assert url == (
        f"https://api.census.gov/data/2024/acs/acs5?get=NAME,group({table})&for=county:*"
    )
    assert "key" not in parse_qs(urlparse(url).query)
    fetch_manifest = json.loads((ROOT / "FETCH-MANIFEST.json").read_text())
    entries = [
        entry
        for entry in fetch_manifest["artifacts"]
        if entry["package_id"] == _package_id(table)
    ]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["expected_sha256"] == SHA256[table]
    assert entry["destination_path"] == str(
        Path("db/data") / _directory(table) / artifact["filename"]
    )
    assert entry["url"] == url
    checked_in = ROOT / "packages" / _directory(table) / "source_package.yaml"
    assert census_acs5_county.render_package(table, root=ROOT) == checked_in.read_text()


def test_source_rows_and_cells_preserve_publisher_values(county_package):
    bundle = county_package
    publisher = _publisher_rows(bundle.table)
    assert len(bundle.rows) == len(publisher) == 3_222
    assert validate_source_rows(bundle.rows).valid
    assert validate_source_cells(bundle.cells).valid
    by_key = {}
    for parsed, raw in zip(bundle.rows, publisher, strict=True):
        assert parsed.values == {name: _scalar(value) for name, value in raw.items()}
        assert parsed.artifact.sha256 == SHA256[bundle.table]
        by_key[build_source_row_key(parsed)] = parsed
    county_ids = {row["GEO_ID"] for row in publisher if row["state"] != "72"}
    assert len(county_ids) == COUNTY_COUNT
    assert {geoid for geoid in county_ids if geoid.startswith("0500000US09")} == (
        CT_REGIONS
    )
    assert all(
        "Planning Region" in row["NAME"] for row in publisher if row["state"] == "09"
    )
    columns = list(bundle.rows[0].values)
    # Source cells select 50-state/DC rows while full source rows also retain PR.
    assert len(bundle.cells) == (COUNTY_COUNT + 1) * len(columns)
    for cell in bundle.cells:
        column = columns[cell.column_number - 1]
        if cell.row_number == 1:
            assert cell.raw_value == column
        else:
            source_row = by_key[cell.source_row_key]
            assert source_row.values["GEO_ID"] in county_ids
            assert cell.raw_value == source_row.values[column]


def test_source_package_and_consumer_contracts_validate(county_package):
    bundle = county_package
    report = validate_source_package(_package_id(bundle.table), year=2024)
    assert report.valid, report.errors
    assert report.counts["source_record_count"] == FACT_COUNTS[bundle.table]
    assert validate_facts(bundle.facts).valid
    contract_report = validate_consumer_fact_contract(bundle.facts)
    assert contract_report.valid, contract_report.errors


def test_agent_acceptance_checks_source_semantics(county_package):
    bundle = county_package
    record_sets = bundle.package.build_source_record_set_specs(2024)
    record_specs = [
        spec
        for record_set in record_sets
        for spec in compile_source_record_set_specs(record_set)
    ]
    regions = [
        region
        for record_set in record_sets
        for region in source_regions_from_record_set_spec(record_set)
    ]
    source_column_dimensions = {
        f"{record_set.source_record_id_prefix}.{row.value_id}.{measure.measure_id}": (
            dict(measure.source_column_dimensions)
        )
        for record_set in record_sets
        for row in record_set.rows
        for measure in record_set.measures
        if measure.source_column_dimensions
    }
    region_report = validate_source_regions(regions, bundle.cells)
    record_report = validate_source_record_specs(record_specs, bundle.cells)
    concept_report = validate_concept_alignments(bundle.facts)
    assert region_report.valid, region_report.errors
    assert record_report.valid, record_report.errors
    assert concept_report.valid, concept_report.errors
    report = build_agent_acceptance_report(
        bundle.facts,
        bundle.rows,
        bundle.cells,
        source_rows=validate_source_rows(bundle.rows),
        source_cells=validate_source_cells(bundle.cells),
        source_regions=region_report,
        source_records=record_report,
        fact_report=validate_facts(bundle.facts),
        concept_alignments=concept_report,
        source_column_dimensions_by_record_id=source_column_dimensions,
    )
    assert report.valid, report.errors


def test_every_numeric_fact_is_the_exact_publisher_cell(county_package):
    bundle = county_package
    variables = _variables(bundle.table)
    publisher = {
        row["GEO_ID"]: row
        for row in _publisher_rows(bundle.table)
        if row["state"] != "72"
    }
    expected = {
        (geoid, variable): int(row[variable])
        for geoid, row in publisher.items()
        for variable in variables
        if row[variable] is not None and int(row[variable]) >= 0
    }
    cells_by_key = {build_source_cell_key(cell): cell for cell in bundle.cells}
    rows_by_key = {build_source_row_key(row): row for row in bundle.rows}
    seen = set()
    for fact in bundle.facts:
        variable = fact.layout.source_column_id
        assert fact.layout.measure_id == variable
        key = (fact.geography.id, variable)
        assert key not in seen
        seen.add(key)
        assert fact.value == expected[key]
        assert fact.value >= 0
        assert fact.geography.level == "county"
        assert fact.geography.name == publisher[fact.geography.id]["NAME"]
        assert len(fact.source_row_keys) == 1
        source_row = rows_by_key[fact.source_row_keys[0]]
        assert source_row.values["GEO_ID"] == fact.geography.id
        assert source_row.values[variable] == fact.value
        value_cell = cells_by_key[fact.source_cell_keys[0]]
        assert value_cell.source_row_key == fact.source_row_keys[0]
        assert value_cell.raw_value == fact.value
        assert list(source_row.values)[value_cell.column_number - 1] == variable
        assert fact.source.source_sha256 == SHA256[bundle.table]
        assert fact.source.source_size_bytes == source_row.artifact.size_bytes
        assert fact.source.raw_r2_uri == source_row.artifact.raw_r2_uri
        assert fact.source.vintage == "acs_5_year_2020_2024"
        is_moe = variable.endswith("M")
        statistic = "margin_of_error" if is_moe else "estimate"
        assert fact.filters["statistic"] == statistic
        assert ("statistic", "==", statistic) in {
            (item.variable, item.operator, item.value) for item in fact.constraints
        }
        assert fact.measure.concept.endswith("_margin_of_error") == is_moe
        if is_moe:
            assert "90%" in fact.measure.concept_evidence_notes
        assert fact.aggregation.method == (
            "median" if bundle.table == "B19013" and not is_moe else "sum"
        )
        assert fact.provenance_class == "survey_aggregate"
        assert fact.survey_instrument == "ACS 5-year"
        assert fact.assertion == "observation"
        assert fact.period.type == "calendar_year"
        assert fact.period.value == 2024
        assert fact.period_coverage.start_date == "2020-01-01"
        assert fact.period_coverage.end_date == "2024-12-31"
        assert fact.period_coverage.basis == "survey_reference"
    assert seen == set(expected)
    assert len(bundle.facts) == FACT_COUNTS[bundle.table]
    counties = {fact.geography.id for fact in bundle.facts}
    assert len(counties) == (3_143 if bundle.table == "B19013" else COUNTY_COUNT)
    assert {
        geoid for geoid in counties if geoid.startswith("0500000US09")
    } == CT_REGIONS
    assert not any(geoid.startswith("0500000US72") for geoid in counties)


def test_other_years_cannot_relabel_the_publisher_period(county_package):
    for year in (2023, 2026):
        with pytest.raises(ValueError, match=f"No source artifact for year {year}"):
            county_package.package.build_facts(year)


def test_estimate_partition_identities_and_publisher_suppression(county_package):
    bundle = county_package
    values = {
        (fact.geography.id, fact.layout.source_column_id): fact.value
        for fact in bundle.facts
    }
    counties = {geoid for geoid, _variable in values}
    if bundle.table == "B19001":
        for geoid in counties:
            assert values[geoid, "B19001_001E"] == sum(
                values[geoid, f"B19001_{index:03}E"] for index in range(2, 18)
            )
    elif bundle.table in {"B19051", "B11001"}:
        detail = (2, 3) if bundle.table == "B19051" else (2, 7)
        for geoid in counties:
            assert values[geoid, f"{bundle.table}_001E"] == sum(
                values[geoid, f"{bundle.table}_{index:03}E"] for index in detail
            )
    elif bundle.table == "B01003":
        rows = [row for row in bundle.rows if row.values["state"] != 72]
        assert Counter(row.values["B01003_001MA"] for row in rows) == {
            "*****": 3_014,
            None: 130,
        }
        assert sum(row.values["B01003_001M"] == -555_555_555 for row in rows) == 3_014
        assert sum(variable.endswith("M") for _geoid, variable in values) == 130
    elif bundle.table == "B19013":
        row = next(
            row for row in bundle.rows if row.values["GEO_ID"] == "0500000US35011"
        )
        assert row.values["NAME"] == "De Baca County, New Mexico"
        assert row.values["B19013_001E"] == -666_666_666
        assert row.values["B19013_001EA"] == "-"
        assert row.values["B19013_001M"] == -222_222_222
        assert row.values["B19013_001MA"] == "**"
        assert not any(geoid == "0500000US35011" for geoid, _variable in values)


def test_income_bracket_metadata_and_constraints(county_package):
    if county_package.table != "B19001":
        return
    payload = census_acs5_county.build_package("B19001", root=ROOT)
    brackets = payload["income_brackets"]
    assert len(brackets) == len(INCOME_BOUNDS) == 16
    for index, (metadata, bounds) in enumerate(
        zip(brackets, INCOME_BOUNDS, strict=True), start=2
    ):
        assert metadata["variable_id"] == f"B19001_{index:03}E"
        assert (metadata["lower_bound"], metadata["upper_bound"]) == bounds
        assert metadata["lower_inclusive"] == (bounds[0] is not None)
        assert metadata["upper_inclusive"] is False
        assert metadata["unit"] == "USD"
        assert metadata["dollar_year"] == 2024
    by_variable = {}
    for fact in county_package.facts:
        by_variable.setdefault(fact.layout.source_column_id, fact)
    for index, (lower, upper) in enumerate(INCOME_BOUNDS, start=2):
        expected = set()
        if lower is not None:
            expected.add(("household_income", ">=", lower, "USD"))
        if upper is not None:
            expected.add(("household_income", "<", upper, "USD"))
        for suffix in "EM":
            fact = by_variable[f"B19001_{index:03}{suffix}"]
            constraints = {
                (item.variable, item.operator, item.value, item.unit)
                for item in fact.constraints
                if item.variable == "household_income"
            }
            assert constraints == expected
            assert fact.filters["income_range"] != "all"
    for suffix in "EM":
        total = by_variable[f"B19001_001{suffix}"]
        assert total.filters["income_range"] == "all"
        assert not any(
            item.variable == "household_income" for item in total.constraints
        )


def _mutated_root(tmp_path: Path, table: str, mutate) -> Path:
    data_dir = tmp_path / "db/data" / _directory(table)
    data_dir.mkdir(parents=True)
    payload = _raw_table(table)
    mutate(payload)
    content = json.dumps(payload).encode()
    (data_dir / f"acs5_2024_{table}_county.json").write_bytes(content)
    manifest = safe_load_yaml((_data_directory(table) / "manifest.yaml").read_text())
    manifest["files"][2024].update(
        sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content)
    )
    (data_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    return tmp_path


def test_generator_refuses_unknown_negative_encoding(tmp_path):
    def mutate(payload):
        payload[1][payload[0].index("B19025_001E")] = "-12345"

    root = _mutated_root(tmp_path, "B19025", mutate)
    with pytest.raises(ValueError):
        census_acs5_county.build_package("B19025", root=root)


def test_generator_refuses_a_missing_required_variable(tmp_path):
    def mutate(payload):
        column = payload[0].index("B19051_003M")
        for row in payload:
            del row[column]

    root = _mutated_root(tmp_path, "B19051", mutate)
    with pytest.raises(ValueError, match="B19051_003M"):
        census_acs5_county.build_package("B19051", root=root)


def test_generator_refuses_geography_disagreement(tmp_path):
    def mutate(payload):
        payload[1][payload[0].index("GEO_ID")] = "0500000US99999"

    root = _mutated_root(tmp_path, "B19025", mutate)
    with pytest.raises(ValueError):
        census_acs5_county.build_package("B19025", root=root)


def test_generator_refuses_conflicting_duplicate_names(tmp_path):
    def mutate(payload):
        columns = [index for index, name in enumerate(payload[0]) if name == "NAME"]
        assert len(columns) == 2
        payload[1][columns[-1]] = "Conflicting county name"

    root = _mutated_root(tmp_path, "B19025", mutate)
    with pytest.raises(ValueError):
        census_acs5_county.build_package("B19025", root=root)


def test_generator_refuses_mismatched_sentinel_annotation(tmp_path):
    def mutate(payload):
        column = payload[0].index("B01003_001M")
        row = next(row for row in payload[1:] if row[column] == "-555555555")
        row[payload[0].index("B01003_001MA")] = "Unexpected annotation"

    root = _mutated_root(tmp_path, "B01003", mutate)
    with pytest.raises(ValueError):
        census_acs5_county.build_package("B01003", root=root)
