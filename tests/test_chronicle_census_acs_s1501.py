"""Census ACS 2024 1-year S1501 educational attainment by state.

The package reads the data.census.gov table API response for S1501 (all states,
the District of Columbia and Puerto Rico) and emits the Total estimates for the
two population universes the table splits attainment by: 18 to 24 years (four
categories) and 25 years and over (seven categories, with associate's and
bachelor's degrees separate). PolicyEngine/chronicle#310.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chronicle.consumer_contract import validate_consumer_fact_contract
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources.cells import SourceArtifactMetadata, validate_source_cells
from chronicle.sources.rows import (
    S1501_ATTAINMENT_COLUMNS,
    source_rows_from_census_acs_s1501_attainment_json,
    validate_source_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ALIAS = "census-acs-s1501-state-attainment-2024"
ARTIFACT = REPO_ROOT / "db/data/census/acs_s1501_state_2024/acs_S1501_state_2024.json"
SHA256 = "84fff08c9d2793a90f2326eb68ae8ba4d5e18957899fc8cdda015d26520f73a4"
VARIABLES = [
    variable for variable, _age, _attainment, _label in S1501_ATTAINMENT_COLUMNS
]


def _artifact() -> SourceArtifactMetadata:
    return SourceArtifactMetadata(
        source_name="census_acs",
        source_table="test",
        source_file="test.json",
        url="https://example.test/test",
        vintage="test",
        sha256="abc123",
        size_bytes=10,
        extracted_at="2026-10-12",
        extraction_method="test",
    )


def _table() -> list[list[str]]:
    header = ["NAME", "S1501_C01_006M", *reversed(VARIABLES), "GEO_ID"]
    values = {variable: str(1000 + index) for index, variable in enumerate(VARIABLES)}
    row = ["Alabama", "9", *(values[v] for v in reversed(VARIABLES)), "0400000US01"]
    return [header, row]


def _published() -> dict[tuple[str, str], int]:
    table = json.loads(ARTIFACT.read_text(encoding="utf-8"))["response"]["data"]
    header = table[0]
    return {
        (row[header.index("GEO_ID")], variable): int(row[header.index(variable)])
        for row in table[1:]
        for variable in VARIABLES
    }


@pytest.mark.parametrize("wrap", [False, True])
def test_parser_reads_both_census_api_shapes(wrap):
    table = _table()
    payload = {"response": {"data": table, "tableName": "S1501"}} if wrap else table

    rows = source_rows_from_census_acs_s1501_attainment_json(
        json.dumps(payload).encode(), _artifact(), sheet_name="api_response"
    )

    assert validate_source_rows(rows).valid
    assert len(rows) == len(VARIABLES) == 13
    assert [row.values["source_column_id"] for row in rows] == VARIABLES
    assert rows[0].values == {
        "GEO_ID": "0400000US01",
        "NAME": "Alabama",
        "age": "Aged 18 to 24",
        "educational_attainment": "all",
        "source_column_id": "S1501_C01_001E",
        "source_concept": (
            "Estimate!!Total!!AGE BY EDUCATIONAL ATTAINMENT!!Population 18 to 24 years"
        ),
        "value": 1000,
        "source_table_row_number": 2,
    }
    associates = rows[VARIABLES.index("S1501_C01_011E")].values
    assert associates["age"] == "Aged 25 and over"
    assert associates["educational_attainment"] == "associates_degree"
    assert associates["source_concept"].endswith("!!Associate's degree")
    assert associates["value"] == 1010


def test_parser_refuses_a_table_without_an_attainment_column():
    header, row = _table()
    index = header.index("S1501_C01_012E")
    del header[index], row[index]

    with pytest.raises(ValueError, match="S1501_C01_012E"):
        source_rows_from_census_acs_s1501_attainment_json(
            json.dumps([header, row]).encode(), _artifact(), sheet_name="api_response"
        )


def test_parser_refuses_an_unknown_payload():
    with pytest.raises(ValueError, match="array of arrays"):
        source_rows_from_census_acs_s1501_attainment_json(
            json.dumps({"data": []}).encode(), _artifact(), sheet_name="api_response"
        )


def test_alias_validates_with_pinned_counts():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == Path("census/acs_s1501_state_2024")
    report = validate_source_package(ALIAS, year=2024)

    assert report.valid, report.errors
    assert report.counts == {
        "record_set_count": 104,
        "row_count": 676,
        "measure_count": 104,
        "source_record_count": 676,
        "source_region_count": 104,
    }


def test_every_fact_is_the_published_estimate():
    package = load_source_package(ALIAS)
    rows = package.build_source_rows(2024)
    cells = package.build_source_cells(2024, source_rows=rows)
    facts = package.build_facts(2024, cells=cells, source_rows=rows)
    published = _published()

    assert validate_source_rows(rows).valid
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert len(facts) == len(published) == 52 * 13
    variable_by_cell = {
        ("18_to_24" if age == "Aged 18 to 24" else "25_plus", attainment): variable
        for variable, age, attainment, _label in S1501_ATTAINMENT_COLUMNS
    }
    seen = set()
    for fact in facts:
        assert len(fact.source_row_keys) == 1
        universe = fact.layout.record_set_id.split(".")[3].removeprefix(
            "state_attainment_"
        )
        variable = variable_by_cell[(universe, fact.layout.groupby_value_id)]
        key = (fact.geography.id, variable)
        assert fact.value == published[key]
        seen.add(key)
        assert fact.period.value == 2024
        assert fact.geography.level == "state"
        assert fact.provenance_class == "survey_aggregate"
        assert fact.survey_instrument == "ACS 1-year"
        assert fact.source.source_sha256 == SHA256
        assert fact.source.raw_r2_uri == (
            f"r2://ledger-raw/raw/census_acs/{ALIAS}/2024/{SHA256}/"
            "acs_S1501_state_2024.json"
        )
    assert seen == set(published)


def test_universes_and_attainment_constraints():
    facts = {
        fact.source_record_id: fact
        for fact in load_source_package(ALIAS).build_facts(2024)
    }
    prefix = "census_acs.acs1_2024.s1501.state_attainment"

    def constraints(record_id: str) -> set:
        return {(c.variable, c.operator, c.value) for c in facts[record_id].constraints}

    associates = f"{prefix}_25_plus.01.associates_degree.population"
    bachelors = f"{prefix}_25_plus.01.bachelors_degree.population"
    assert facts[associates].value == 343_468
    assert facts[bachelors].value == 637_543
    assert constraints(associates) == {
        ("age", ">=", 25),
        ("educational_attainment", "==", "associates_degree"),
    }
    assert constraints(f"{prefix}_25_plus.01.all.population") == {("age", ">=", 25)}
    assert facts[f"{prefix}_25_plus.01.all.population"].value == 3_540_061
    young = f"{prefix}_18_to_24.01.some_college_or_associates_degree.population"
    assert constraints(young) == {
        ("age", ">=", 18),
        ("age", "<", 25),
        ("educational_attainment", "==", "some_college_or_associates_degree"),
    }
    assert (
        facts[f"{prefix}_25_plus.72.graduate_or_professional_degree.population"].value
        == 214_691
    )


def test_published_categories_add_to_each_universe_total():
    """The detail rows partition each universe in this release."""
    facts = load_source_package(ALIAS).build_facts(2024)
    totals: dict[str, int] = {}
    parts: dict[str, int] = {}
    for fact in facts:
        record_set = fact.layout.record_set_id
        if fact.layout.table_record_kind == "total":
            totals[record_set] = fact.value
        else:
            parts[record_set] = parts.get(record_set, 0) + fact.value

    assert len(totals) == 104
    assert totals == parts


def test_other_years_have_no_artifact():
    with pytest.raises(ValueError, match="No source artifact for year 2025"):
        load_source_package(ALIAS).build_facts(2025)
