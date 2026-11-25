"""Publisher-backed ACS 2024 1-year check tables: B19013 and S1701 (chronicle#447).

Median household income (B19013) and poverty status (S1701) for the states, DC
and Puerto Rico, and for the 119th Congress districts, DC's delegate district
and Puerto Rico's resident commissioner district. Microcosm reads them as
checks of its district build (PolicyEngine/microcosm#1673).
"""

from __future__ import annotations

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
from chronicle.sources import census_acs1_check_tables as generator
from chronicle.sources.cells import (
    SourceCell,
    build_source_cell_key,
    validate_source_cells,
)
from chronicle.sources.rows import (
    SourceRow,
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
PACKAGES = tuple(
    (table, geography)
    for table in generator.TABLES
    for geography in generator.GEOGRAPHIES
)
SHA256 = {
    ("B19013", "state"): (
        "8e285c2cc594cd16e5a64dca4f49e3dc2a21f43ed33e8fd66abf1956c1a87384"
    ),
    ("B19013", "district"): (
        "424b8411b6829c1706328e19ab3bf2d5e4944cd3c00fec7f2e0c10c78aac4273"
    ),
    ("S1701", "state"): (
        "952d1d327d07f7a367fc7ef419179415ed71072367321b7757fdb3c9b452f1e0"
    ),
    ("S1701", "district"): (
        "11df1a14dd3f4029b3a9d685fe211d26296ea4eb9c06e435f62ce134e5c2c247"
    ),
}
CELL_COUNTS = {"B19013": 1, "S1701": 8}
GEOGRAPHY_COUNTS = {"state": 52, "district": 437}
API_CLAUSES = {
    "state": "state:*",
    "district": "congressional%20district:*&in=state:*",
}
S1701_STEMS = [stem for stem, _, _, _ in generator.cells("S1701")]


def _data_directory(table: str, geography: str) -> Path:
    return ROOT / "db/data/census" / generator.directory(table, geography)


def _filename(table: str, geography: str) -> str:
    return f"acs1_2024_{table}_{geography}.json"


def _raw_table(table: str, geography: str) -> list[list[Any]]:
    path = _data_directory(table, geography) / _filename(table, geography)
    return json.loads(path.read_text(encoding="utf-8"))


def _publisher_rows(table: str, geography: str) -> list[dict[str, Any]]:
    header, *rows = _raw_table(table, geography)
    return [dict(zip(header, row, strict=True)) for row in rows]


def _scalar(value: Any) -> Any:
    """Account for the established JSON table parser's numeric normalization."""
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return value
        return int(number) if number.is_integer() else number
    return value


@dataclass
class CheckPackage:
    table: str
    geography: str
    package: SourcePackage
    rows: list[SourceRow]
    cells: list[SourceCell]
    facts: list[AggregateFact]


@pytest.fixture(scope="module", params=PACKAGES, ids=lambda item: "-".join(item))
def check_package(request) -> CheckPackage:
    table, geography = request.param
    package = load_source_package(generator.package_id(table, geography))
    rows = package.build_source_rows(2024)
    cells = package.build_source_cells(2024, source_rows=rows)
    facts = package.build_facts(2024, source_rows=rows, cells=cells)
    return CheckPackage(table, geography, package, rows, cells, facts)


@pytest.mark.parametrize("table,geography", PACKAGES)
def test_pinned_bytes_manifests_and_deterministic_generation(table, geography):
    package_id = generator.package_id(table, geography)
    assert SOURCE_PACKAGE_ALIASES[package_id] == Path(
        f"census/{generator.directory(table, geography)}"
    )
    data_dir = _data_directory(table, geography)
    manifest = safe_load_yaml((data_dir / "manifest.yaml").read_text())
    assert manifest["package_id"] == package_id
    assert manifest["reference_period"] == "2024"
    artifact = manifest["files"][2024]
    assert artifact["filename"] == _filename(table, geography)
    content = (data_dir / artifact["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == artifact["sha256"]
    assert artifact["sha256"] == SHA256[table, geography]
    assert len(content) == artifact["size_bytes"]
    url = artifact["source_url"]
    if table.startswith("S"):
        expected = (
            "https://api.census.gov/data/2024/acs/acs1/subject"
            f"?get=group({table})&for={API_CLAUSES[geography]}"
        )
    else:
        expected = (
            "https://api.census.gov/data/2024/acs/acs1"
            f"?get=NAME,group({table})&for={API_CLAUSES[geography]}"
        )
    assert url == expected
    assert "key" not in parse_qs(urlparse(url).query)
    key = artifact["storage"]["r2"]["key"]
    assert key == (
        f"raw/census_acs/{package_id}/2024/{artifact['sha256']}/{artifact['filename']}"
    )
    checked_in = (
        ROOT / "packages/census" / generator.directory(table, geography)
    ) / "source_package.yaml"
    assert generator.render_package(table, geography, root=ROOT) == (
        checked_in.read_text()
    )


def test_source_rows_and_cells_preserve_publisher_values(check_package):
    bundle = check_package
    publisher = _publisher_rows(bundle.table, bundle.geography)
    assert len(bundle.rows) == len(publisher) == GEOGRAPHY_COUNTS[bundle.geography]
    assert validate_source_rows(bundle.rows).valid
    assert validate_source_cells(bundle.cells).valid
    publisher_by_geo = {row["GEO_ID"]: row for row in publisher}
    for parsed in bundle.rows:
        raw = publisher_by_geo[parsed.values["GEO_ID"]]
        assert parsed.values == {name: _scalar(value) for name, value in raw.items()}
        assert parsed.artifact.sha256 == SHA256[bundle.table, bundle.geography]
    columns = list(bundle.rows[0].values)
    assert len(bundle.cells) == (len(publisher) + 1) * len(columns)


def test_source_package_and_consumer_contracts_validate(check_package):
    bundle = check_package
    package_id = generator.package_id(bundle.table, bundle.geography)
    report = validate_source_package(package_id, year=2024)
    assert report.valid, report.errors
    expected = 2 * CELL_COUNTS[bundle.table] * GEOGRAPHY_COUNTS[bundle.geography]
    assert report.counts["source_record_count"] == expected
    assert len(bundle.facts) == expected
    assert validate_facts(bundle.facts).valid
    contract_report = validate_consumer_fact_contract(bundle.facts)
    assert contract_report.valid, contract_report.errors


def test_agent_acceptance_checks_source_semantics(check_package):
    bundle = check_package
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


def test_every_fact_is_the_exact_publisher_cell_with_its_categories(check_package):
    bundle = check_package
    publisher = {
        row["GEO_ID"]: row for row in _publisher_rows(bundle.table, bundle.geography)
    }
    declared = {
        stem: (categories, bounds)
        for stem, categories, _label, bounds in generator.cells(bundle.table)
    }
    cells_by_key = {build_source_cell_key(cell): cell for cell in bundle.cells}
    seen = set()
    for fact in bundle.facts:
        variable = fact.layout.source_column_id
        assert fact.layout.measure_id == variable
        key = (fact.geography.id, variable)
        assert key not in seen
        seen.add(key)
        row = publisher[fact.geography.id]
        assert fact.value == _scalar(row[variable]) >= 0
        assert fact.geography.name == row["NAME"]
        assert fact.geography.level == generator.GEOGRAPHY_LEVELS[bundle.geography]
        value_cell = cells_by_key[fact.source_cell_keys[0]]
        assert value_cell.raw_value == fact.value
        assert fact.source.source_sha256 == SHA256[bundle.table, bundle.geography]
        categories, (lower, upper) = declared[variable[:-1]]
        is_moe = variable.endswith("M")
        statistic = "margin_of_error" if is_moe else "estimate"
        assert fact.filters == {"statistic": statistic, **categories}
        constraints = {
            (item.variable, item.operator, item.value) for item in fact.constraints
        }
        expected = {("statistic", "==", statistic)}
        for dimension, value in categories.items():
            if value != "all":
                expected.add((dimension, "==", value))
        if lower is not None:
            expected.add(("age", ">=", lower))
        if upper is not None:
            expected.add(("age", "<", upper))
        assert constraints == expected
        assert fact.measure.concept.endswith("_margin_of_error") == is_moe
        if bundle.table == "B19013":
            assert fact.measure.concept.startswith("census_acs.median_household_income")
            assert fact.aggregation.method == "median"
        else:
            assert fact.measure.concept.startswith(
                "census_acs.poverty_universe_person_count"
            )
            assert fact.aggregation.method == "sum"
        assert fact.provenance_class == "survey_aggregate"
        assert fact.survey_instrument == "ACS 1-year"
        assert fact.period.type == "calendar_year"
        assert fact.period.value == 2024
    assert seen == {
        (geo_id, f"{stem}{suffix}")
        for geo_id in publisher
        for stem in declared
        for suffix in "EM"
    }


def test_other_years_cannot_relabel_the_publisher_period(check_package):
    for year in (2023, 2025):
        with pytest.raises(ValueError, match=f"No source artifact for year {year}"):
            check_package.package.build_facts(year)


@pytest.mark.parametrize("geography", generator.GEOGRAPHIES)
def test_s1701_age_bands_partition_all_ages(geography):
    for row in _publisher_rows("S1701", geography):
        for column in ("C01", "C02"):
            assert int(row[f"S1701_{column}_001E"]) == sum(
                int(row[f"S1701_{column}_{age}E"]) for age in ("002", "006", "010")
            )


def test_s1701_districts_add_up_to_their_state():
    """ACS tabulates every geography from the same weighted records."""
    states = {row["state"]: row for row in _publisher_rows("S1701", "state")}
    sums: dict[tuple[str, str], int] = {}
    for row in _publisher_rows("S1701", "district"):
        for stem in S1701_STEMS:
            key = (row["state"], stem)
            sums[key] = sums.get(key, 0) + int(row[f"{stem}E"])
    assert {key[0] for key in sums} == generator.STATE_ROW_FIPS
    for (state, stem), total in sums.items():
        assert total == int(states[state][f"{stem}E"]), (state, stem)


def test_b19013_state_medians_lie_within_their_districts():
    """A state's households are its districts' households, so its median lies
    between its districts' lowest and highest median."""
    by_state: dict[str, list[int]] = {}
    for row in _publisher_rows("B19013", "district"):
        by_state.setdefault(row["state"], []).append(int(row["B19013_001E"]))
    for row in _publisher_rows("B19013", "state"):
        medians = by_state[row["state"]]
        assert min(medians) <= int(row["B19013_001E"]) <= max(medians), row["state"]


def test_district_rows_are_the_s0101_district_package_rows():
    s0101 = json.loads(
        (
            ROOT / "db/data/census/acs_s0101_district_2024/acs_S0101_district_2024.json"
        ).read_text(encoding="utf-8")
    )
    geo_column = s0101[0].index("GEO_ID")
    s0101_ids = {row[geo_column] for row in s0101[1:]}
    for table in generator.TABLES:
        assert {row["GEO_ID"] for row in _publisher_rows(table, "district")} == (
            s0101_ids
        )


def test_b19013_measures_are_the_county_package_b19013_measures():
    county = safe_load_yaml(
        (
            ROOT / "packages/census/acs5_b19013_county_2024/source_package.yaml"
        ).read_text()
    )
    twins = {
        measure["measure_id"]: measure
        for record_set in county["record_sets"]
        for measure in record_set["measures"]
    }
    for geography in generator.GEOGRAPHIES:
        payload = generator.build_package("B19013", geography, root=ROOT)
        for measure in payload["record_sets"][0]["measures"]:
            twin = twins[measure["measure_id"]]
            for field in (
                "label",
                "concept",
                "unit",
                "aggregation",
                "filters",
                "constraints",
            ):
                assert measure[field] == twin[field], (geography, field)


def _mutated_root(tmp_path: Path, table: str, geography: str, mutate) -> Path:
    data_dir = tmp_path / "db/data/census" / generator.directory(table, geography)
    data_dir.mkdir(parents=True)
    payload = _raw_table(table, geography)
    mutate(payload)
    content = json.dumps(payload).encode()
    (data_dir / _filename(table, geography)).write_bytes(content)
    manifest = safe_load_yaml(
        (_data_directory(table, geography) / "manifest.yaml").read_text()
    )
    manifest["files"][2024].update(
        sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content)
    )
    (data_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    return tmp_path


def test_generator_refuses_changed_bytes(tmp_path):
    data_dir = tmp_path / "db/data/census" / generator.directory("B19013", "state")
    data_dir.mkdir(parents=True)
    content = _data_directory("B19013", "state") / _filename("B19013", "state")
    (data_dir / _filename("B19013", "state")).write_bytes(content.read_bytes() + b" ")
    (data_dir / "manifest.yaml").write_text(
        (_data_directory("B19013", "state") / "manifest.yaml").read_text()
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        generator.build_package("B19013", "state", root=tmp_path)


@pytest.mark.parametrize("table,geography", PACKAGES)
def test_generator_refuses_a_code_in_a_declared_cell(tmp_path, table, geography):
    stem = generator.cells(table)[-1][0]

    def mutate(payload):
        payload[1][payload[0].index(f"{stem}E")] = "-666666666"
        payload[1][payload[0].index(f"{stem}EA")] = "-"

    root = _mutated_root(tmp_path, table, geography, mutate)
    with pytest.raises(ValueError, match="Unknown suppression"):
        generator.build_package(table, geography, root=root)


def test_s1701_codes_in_undeclared_cells_are_kept_as_source_cells():
    """S1701 publishes (X), N and too-few-cases codes in cells no fact reads."""
    rows = _publisher_rows("S1701", "district")
    declared = {f"{stem}{suffix}" for stem in S1701_STEMS for suffix in "EM"}
    codes = {
        name
        for row in rows
        for name, value in row.items()
        if name.endswith("EA") and value is not None
    }
    assert codes
    assert not {name[:-1] for name in codes} & declared


def test_generator_refuses_a_missing_district(tmp_path):
    def mutate(payload):
        state_column = payload[0].index("state")
        district_column = payload[0].index("congressional district")
        row = next(
            row
            for row in payload[1:]
            if row[state_column] == "06" and row[district_column] == "52"
        )
        payload.remove(row)

    root = _mutated_root(tmp_path, "S1701", "district", mutate)
    with pytest.raises(ValueError, match="437 congressional district rows"):
        generator.build_package("S1701", "district", root=root)


@pytest.mark.parametrize("state", ("01", "11", "72"))
def test_generator_refuses_a_missing_state_dc_or_puerto_rico(tmp_path, state):
    def mutate(payload):
        state_column = payload[0].index("state")
        row = next(row for row in payload[1:] if row[state_column] == state)
        payload.remove(row)

    root = _mutated_root(tmp_path, "B19013", "state", mutate)
    with pytest.raises(ValueError, match="52 state rows"):
        generator.build_package("B19013", "state", root=root)
