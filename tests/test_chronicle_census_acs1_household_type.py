"""Publisher-backed ACS 2024 1-year household tables: nation, states and districts.

B11001 (household type) and B11003 (family type) for the nation and the states,
and B11001 and B19001 (household income) for the 119th Congress districts too
(chronicle#447).
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
from chronicle.sources import census_acs1_household_type as generator
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
PACKAGES = tuple(
    (table, geography)
    for table in generator.TABLES
    for geography in generator.TABLE_GEOGRAPHIES[table]
)
SHA256 = {
    ("B11001", "national"): (
        "0b42533e29ff8e68ce33bb1a5c53566fac6cc5de247f47dde303c0b834a96116"
    ),
    ("B11001", "state"): (
        "7fe1626e4974495c4a21670fd2c08319914676bb613fa3289d203c5d826466ae"
    ),
    ("B11003", "national"): (
        "25e981752fabf1515a58d1cb9914df1d61b12827d6ac66d171d440fa06ae58cf"
    ),
    ("B11003", "state"): (
        "8b73454674d25d07daac44f75e5478e1612ef31e9334a4bd5d2e84b9e421ed40"
    ),
    ("B11001", "district"): (
        "126295f7a684f4da67ae2381fd177861598b45376e85577917f0ae236d6a6d36"
    ),
    ("B19001", "national"): (
        "a25ad30d2cc3000c83d30142320a187883e5c0d87dd9ebbabec16b6f2f79b358"
    ),
    ("B19001", "state"): (
        "4a4a73c4f9f798678e0cb6a444850604ddb20aace82f5d5ac163635b68c58d8e"
    ),
    ("B19001", "district"): (
        "eea9d2a6e8b77f979da35c137f8d10835d9779a559637ba087f3188579722ddc"
    ),
}
CELL_COUNTS = {"B11001": 9, "B11003": 20, "B19001": 17}
#: The district endpoint returns the 435 districts, DC's and Puerto Rico's.
GEOGRAPHY_COUNTS = {"national": 1, "state": 52, "district": 437}
GEOGRAPHY_LEVELS = {
    "national": "country",
    "state": "state",
    "district": "congressional_district",
}
#: Published national estimates, read off data.census.gov's B11001 and B11003.
NATIONAL_ESTIMATES = {
    "B11001_001E": 132_737_146,
    "B11001_002E": 84_966_539,
    "B11001_003E": 61_980_084,
    "B11001_007E": 47_770_607,
    "B11003_001E": 84_966_539,
    "B11003_003E": 22_978_636,
    # B19001's universe is households too, so its total is B11001's.
    "B19001_001E": 132_737_146,
}
#: Each published total and the cells that partition it.
PARTITIONS = {
    "B11001": {1: (2, 7), 2: (3, 4), 4: (5, 6), 7: (8, 9)},
    "B11003": {
        1: (2, 8),
        2: (3, 7),
        3: (4, 5, 6),
        8: (9, 15),
        9: (10, 14),
        10: (11, 12, 13),
        15: (16, 20),
        16: (17, 18, 19),
    },
    "B19001": {1: tuple(range(2, 18))},
}
#: B11003 family types that B11001 also counts, as (B11003 cell, B11001 cell).
CROSS_TABLE = ((1, 2), (2, 3), (8, 4), (9, 5), (15, 6))


def _api_geography(geography: str) -> str:
    """The geography part of the data file's name."""
    return {"national": "us", "state": "state", "district": "district"}[geography]


def _api_clause(geography: str) -> str:
    return {
        "national": "us:1",
        "state": "state:*",
        "district": "congressional%20district:*&in=state:*",
    }[geography]


def _data_directory(table: str, geography: str) -> Path:
    return ROOT / "db/data/census" / generator.directory(table, geography)


def _filename(table: str, geography: str) -> str:
    return f"acs1_2024_{table}_{_api_geography(geography)}.json"


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
    return value


def _estimates(table: str, geography: str) -> dict[tuple[str, int], int]:
    return {
        (row["GEO_ID"], index): int(row[f"{table}_{index:03d}E"])
        for row in _publisher_rows(table, geography)
        for index in range(1, CELL_COUNTS[table] + 1)
    }


@dataclass
class HouseholdPackage:
    table: str
    geography: str
    package: SourcePackage
    rows: list[SourceRow]
    cells: list[SourceCell]
    facts: list[AggregateFact]


@pytest.fixture(scope="module", params=PACKAGES, ids=lambda item: "-".join(item))
def household_package(request) -> HouseholdPackage:
    table, geography = request.param
    package = load_source_package(generator.package_id(table, geography))
    rows = package.build_source_rows(2024)
    cells = package.build_source_cells(2024, source_rows=rows)
    facts = package.build_facts(2024, source_rows=rows, cells=cells)
    return HouseholdPackage(table, geography, package, rows, cells, facts)


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
    assert url == (
        "https://api.census.gov/data/2024/acs/acs1"
        f"?get=NAME,group({table})&for={_api_clause(geography)}"
    )
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


def test_source_rows_and_cells_preserve_publisher_values(household_package):
    bundle = household_package
    publisher = _publisher_rows(bundle.table, bundle.geography)
    assert len(bundle.rows) == len(publisher) == GEOGRAPHY_COUNTS[bundle.geography]
    assert validate_source_rows(bundle.rows).valid
    assert validate_source_cells(bundle.cells).valid
    by_key = {}
    publisher_by_geo = {row["GEO_ID"]: row for row in publisher}
    for parsed in bundle.rows:
        raw = publisher_by_geo[parsed.values["GEO_ID"]]
        assert parsed.values == {name: _scalar(value) for name, value in raw.items()}
        assert parsed.artifact.sha256 == SHA256[bundle.table, bundle.geography]
        by_key[build_source_row_key(parsed)] = parsed
    columns = list(bundle.rows[0].values)
    assert len(bundle.cells) == (len(publisher) + 1) * len(columns)
    for cell in bundle.cells:
        column = columns[cell.column_number - 1]
        if cell.row_number == 1:
            assert cell.raw_value == column
        else:
            source_row = by_key[cell.source_row_key]
            assert cell.raw_value == source_row.values[column]


def test_source_package_and_consumer_contracts_validate(household_package):
    bundle = household_package
    package_id = generator.package_id(bundle.table, bundle.geography)
    report = validate_source_package(package_id, year=2024)
    assert report.valid, report.errors
    expected = 2 * CELL_COUNTS[bundle.table] * GEOGRAPHY_COUNTS[bundle.geography]
    assert report.counts["source_record_count"] == expected
    assert validate_facts(bundle.facts).valid
    contract_report = validate_consumer_fact_contract(bundle.facts)
    assert contract_report.valid, contract_report.errors


def test_agent_acceptance_checks_source_semantics(household_package):
    bundle = household_package
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


def test_every_fact_is_the_exact_publisher_cell_with_its_categories(
    household_package,
):
    bundle = household_package
    publisher = {
        row["GEO_ID"]: row for row in _publisher_rows(bundle.table, bundle.geography)
    }
    categories = {
        index: filters for index, filters, _label in generator.cells(bundle.table)
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
        row = publisher[fact.geography.id]
        assert fact.value == int(row[variable]) >= 0
        assert fact.geography.name == row["NAME"]
        assert fact.geography.level == GEOGRAPHY_LEVELS[bundle.geography]
        assert len(fact.source_row_keys) == 1
        source_row = rows_by_key[fact.source_row_keys[0]]
        assert source_row.values["GEO_ID"] == fact.geography.id
        value_cell = cells_by_key[fact.source_cell_keys[0]]
        assert value_cell.source_row_key == fact.source_row_keys[0]
        assert value_cell.raw_value == fact.value
        assert list(source_row.values)[value_cell.column_number - 1] == variable
        # The fact cites three cells and nothing else: its value, its column's
        # header (the variable name, row 1) and its row's GEO_ID.
        geo_id_column = list(source_row.values).index("GEO_ID") + 1
        assert len(fact.source_cell_keys) == 3
        assert {
            (cell.row_number, cell.column_number, cell.raw_value)
            for cell in (cells_by_key[key] for key in fact.source_cell_keys)
        } == {
            (value_cell.row_number, value_cell.column_number, fact.value),
            (1, value_cell.column_number, variable),
            (value_cell.row_number, geo_id_column, fact.geography.id),
        }
        assert fact.source.source_sha256 == SHA256[bundle.table, bundle.geography]
        assert fact.source.vintage == "acs_1_year_2024"
        index = int(variable[len(bundle.table) + 1 : -1])
        is_moe = variable.endswith("M")
        statistic = "margin_of_error" if is_moe else "estimate"
        assert fact.filters == {"statistic": statistic, **categories[index]}
        constraints = {
            (item.variable, item.operator, item.value) for item in fact.constraints
        }
        assert ("statistic", "==", statistic) in constraints
        for dimension, value in categories[index].items():
            if dimension == "income_range":
                # Brackets are bounds on household income, as in the ACS
                # 5-year county package, not an equality on the value id.
                assert (dimension, "==", value) not in constraints
                continue
            assert ((dimension, "==", value) in constraints) == (value != "all")
        assert fact.measure.concept.endswith("_margin_of_error") == is_moe
        if is_moe:
            assert "90%" in fact.measure.concept_evidence_notes
        assert fact.aggregation.method == "sum"
        assert fact.provenance_class == "survey_aggregate"
        assert fact.survey_instrument == "ACS 1-year"
        assert fact.assertion == "observation"
        assert fact.period.type == "calendar_year"
        assert fact.period.value == 2024
        assert fact.period_coverage.start_date == "2024-01-01"
        assert fact.period_coverage.end_date == "2024-12-31"
        assert fact.period_coverage.basis == "survey_reference"
    assert seen == {
        (geo_id, f"{bundle.table}_{index:03d}{suffix}")
        for geo_id in publisher
        for index in range(1, CELL_COUNTS[bundle.table] + 1)
        for suffix in "EM"
    }


def test_other_years_cannot_relabel_the_publisher_period(household_package):
    for year in (2023, 2025):
        with pytest.raises(ValueError, match=f"No source artifact for year {year}"):
            household_package.package.build_facts(year)


@pytest.mark.parametrize("table,geography", PACKAGES)
def test_published_partitions_hold_in_every_geography(table, geography):
    estimates = _estimates(table, geography)
    geo_ids = {geo_id for geo_id, _index in estimates}
    assert len(geo_ids) == GEOGRAPHY_COUNTS[geography]
    for geo_id in geo_ids:
        for total, parts in PARTITIONS[table].items():
            assert estimates[geo_id, total] == sum(
                estimates[geo_id, part] for part in parts
            )


@pytest.mark.parametrize("geography", ("national", "state"))
def test_b11003_family_types_are_b11001_family_households(geography):
    families = _estimates("B11003", geography)
    households = _estimates("B11001", geography)
    for geo_id in {geo_id for geo_id, _index in families}:
        for family_cell, household_cell in CROSS_TABLE:
            assert families[geo_id, family_cell] == households[geo_id, household_cell]


@pytest.mark.parametrize("table", ("B11001", "B11003", "B19001"))
def test_national_estimates_equal_the_states_and_dc(table):
    national = _estimates(table, "national")
    states = _estimates(table, "state")
    state_ids = {geo_id for geo_id, _index in states}
    assert "0400000US72" in state_ids
    for index in range(1, CELL_COUNTS[table] + 1):
        assert national["0100000US", index] == sum(
            states[geo_id, index] for geo_id in state_ids if geo_id != "0400000US72"
        )


def test_national_estimates_match_the_published_figures():
    for variable, expected in NATIONAL_ESTIMATES.items():
        table = variable[:6]
        (row,) = _publisher_rows(table, "national")
        assert int(row[variable]) == expected


def test_both_tables_share_the_county_package_household_types():
    county = safe_load_yaml(
        (
            ROOT / "packages/census/acs5_b11001_county_2024/source_package.yaml"
        ).read_text()
    )
    county_labels = county["dimension_value_labels"]["household_type"]
    for table, geography in PACKAGES:
        if table == "B19001":
            continue
        payload = generator.build_package(table, geography, root=ROOT)
        labels = payload["dimension_value_labels"]["household_type"]
        for value, label in labels.items():
            assert county_labels.get(value, label) == label


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
    data_dir = tmp_path / "db/data/census" / generator.directory("B11001", "state")
    data_dir.mkdir(parents=True)
    content = _data_directory("B11001", "state") / _filename("B11001", "state")
    (data_dir / _filename("B11001", "state")).write_bytes(content.read_bytes() + b" ")
    (data_dir / "manifest.yaml").write_text(
        (_data_directory("B11001", "state") / "manifest.yaml").read_text()
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        generator.build_package("B11001", "state", root=tmp_path)


@pytest.mark.parametrize("table,geography", PACKAGES)
def test_generator_refuses_a_suppression_code(tmp_path, table, geography):
    def mutate(payload):
        payload[1][payload[0].index(f"{table}_003M")] = "-555555555"

    root = _mutated_root(tmp_path, table, geography, mutate)
    with pytest.raises(ValueError, match="Unknown suppression"):
        generator.build_package(table, geography, root=root)


def test_generator_refuses_an_annotation(tmp_path):
    def mutate(payload):
        payload[1][payload[0].index("B11003_017EA")] = "*****"

    root = _mutated_root(tmp_path, "B11003", "state", mutate)
    with pytest.raises(ValueError, match="Unknown suppression"):
        generator.build_package("B11003", "state", root=root)


def test_generator_refuses_a_missing_required_variable(tmp_path):
    def mutate(payload):
        column = payload[0].index("B11003_020M")
        for row in payload:
            del row[column]

    root = _mutated_root(tmp_path, "B11003", "national", mutate)
    with pytest.raises(ValueError, match="B11003_020M"):
        generator.build_package("B11003", "national", root=root)


def test_generator_refuses_geography_disagreement(tmp_path):
    def mutate(payload):
        payload[1][payload[0].index("GEO_ID")] = "0400000US99"

    root = _mutated_root(tmp_path, "B11001", "state", mutate)
    with pytest.raises(ValueError, match="GEO_ID"):
        generator.build_package("B11001", "state", root=root)


@pytest.mark.parametrize("state", ("01", "11", "72"))
def test_generator_refuses_a_missing_state_dc_or_puerto_rico(tmp_path, state):
    def mutate(payload):
        state_column = payload[0].index("state")
        row = next(row for row in payload[1:] if row[state_column] == state)
        payload.remove(row)

    root = _mutated_root(tmp_path, "B11001", "state", mutate)
    with pytest.raises(ValueError, match="52 state rows"):
        generator.build_package("B11001", "state", root=root)


def test_state_row_fips_are_the_50_states_dc_and_puerto_rico():
    assert len(generator.STATE_FIPS) == 50
    assert generator.STATE_ROW_COUNT == 52
    assert generator.STATE_ROW_FIPS == generator.STATE_FIPS | {"11", "72"}
    for table in generator.TABLES:
        payload = _raw_table(table, "state")
        state_column = payload[0].index("state")
        assert {row[state_column] for row in payload[1:]} == generator.STATE_ROW_FIPS


@pytest.mark.parametrize("table", generator.TABLES)
def test_generator_refuses_a_state_swapped_for_an_unknown_code(tmp_path, table):
    # 52 rows with consistent GEO_IDs, but Alabama's row now carries FIPS 99.
    def mutate(payload):
        state_column = payload[0].index("state")
        geo_column = payload[0].index("GEO_ID")
        row = next(row for row in payload[1:] if row[state_column] == "01")
        row[state_column] = "99"
        row[geo_column] = "0400000US99"

    root = _mutated_root(tmp_path, table, "state", mutate)
    with pytest.raises(ValueError, match=r"52 state rows.*missing \['0400000US01'\]"):
        generator.build_package(table, "state", root=root)


def test_generator_refuses_a_second_national_row(tmp_path):
    def mutate(payload):
        payload.append(list(payload[1]))

    root = _mutated_root(tmp_path, "B11001", "national", mutate)
    with pytest.raises(ValueError, match="Duplicate geography rows"):
        generator.build_package("B11001", "national", root=root)


def test_generator_refuses_conflicting_duplicate_names(tmp_path):
    def mutate(payload):
        columns = [index for index, name in enumerate(payload[0]) if name == "NAME"]
        assert len(columns) == 2
        payload[1][columns[-1]] = "Conflicting state name"

    root = _mutated_root(tmp_path, "B11001", "state", mutate)
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        generator.build_package("B11001", "state", root=root)


@pytest.mark.parametrize("table", ("B11001", "B19001"))
def test_district_estimates_add_up_to_their_state(table):
    """The district rows of a state add up exactly to its state row.

    ACS tabulates every geography from the same weighted records, so no
    rounding gap appears: all 52 states (with DC and Puerto Rico, one
    district each) and every cell agree exactly in the 2024 1-year files.
    """
    states = _estimates(table, "state")
    sums: dict[tuple[str, int], int] = {}
    for (geo_id, index), value in _estimates(table, "district").items():
        key = (f"0400000US{geo_id.removeprefix('5001900US')[:2]}", index)
        sums[key] = sums.get(key, 0) + value
    assert sums == states


def test_district_rows_are_the_s0101_district_package_rows():
    s0101 = json.loads(
        (
            ROOT / "db/data/census/acs_s0101_district_2024/acs_S0101_district_2024.json"
        ).read_text(encoding="utf-8")
    )
    geo_column = s0101[0].index("GEO_ID")
    s0101_ids = {row[geo_column] for row in s0101[1:]}
    assert len(s0101_ids) == generator.DISTRICT_ROW_COUNT
    for table in ("B11001", "B19001"):
        assert {row["GEO_ID"] for row in _publisher_rows(table, "district")} == (
            s0101_ids
        )


@pytest.mark.parametrize("geography", ("national", "state", "district"))
def test_b19001_households_are_b11001_households(geography):
    income = {row["GEO_ID"]: row for row in _publisher_rows("B19001", geography)}
    households = {row["GEO_ID"]: row for row in _publisher_rows("B11001", geography)}
    assert income.keys() == households.keys()
    for geo_id, row in income.items():
        for suffix in "EM":
            assert (
                row[f"B19001_001{suffix}"] == households[geo_id][f"B11001_001{suffix}"]
            )


def test_b19001_brackets_are_the_county_package_brackets():
    county = safe_load_yaml(
        (
            ROOT / "packages/census/acs5_b19001_county_2024/source_package.yaml"
        ).read_text()
    )
    county_measures = {
        measure["measure_id"]: measure
        for record_set in county["record_sets"]
        for measure in record_set["measures"]
    }
    for geography in generator.TABLE_GEOGRAPHIES["B19001"]:
        payload = generator.build_package("B19001", geography, root=ROOT)
        assert payload["income_brackets"] == county["income_brackets"]
        assert (
            payload["dimension_value_labels"]["income_range"]
            == (county["dimension_value_labels"]["income_range"])
        )
        for measure in payload["record_sets"][0]["measures"]:
            twin = county_measures[measure["measure_id"]]
            for field in ("filters", "constraints", "source_column_dimensions"):
                assert measure[field] == twin[field], (geography, measure["measure_id"])


def _drop_district(payload, state, district):
    state_column = payload[0].index("state")
    district_column = payload[0].index("congressional district")
    row = next(
        row
        for row in payload[1:]
        if row[state_column] == state and row[district_column] == district
    )
    payload.remove(row)


def test_generator_refuses_a_missing_district(tmp_path):
    root = _mutated_root(
        tmp_path,
        "B19001",
        "district",
        lambda payload: _drop_district(payload, "06", "52"),
    )
    with pytest.raises(ValueError, match="437 congressional district rows"):
        generator.build_package("B19001", "district", root=root)


def test_generator_refuses_a_gap_in_a_states_district_codes(tmp_path):
    # 437 rows with consistent GEO_IDs, but California's district 52 is now 53.
    def mutate(payload):
        state_column = payload[0].index("state")
        district_column = payload[0].index("congressional district")
        geo_column = payload[0].index("GEO_ID")
        row = next(
            row
            for row in payload[1:]
            if row[state_column] == "06" and row[district_column] == "52"
        )
        row[district_column] = "53"
        row[geo_column] = "5001900US0653"

    root = _mutated_root(tmp_path, "B11001", "district", mutate)
    with pytest.raises(ValueError, match="Unexpected district codes for state 06"):
        generator.build_package("B11001", "district", root=root)


def test_generator_refuses_a_district_table_for_b11003():
    with pytest.raises(ValueError, match="Unsupported ACS geography for B11003"):
        generator.build_package("B11003", "district", root=ROOT)
