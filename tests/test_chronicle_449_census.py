"""Census packages for the next editions of four US feed packages (chronicle#449).

- ``census-b01001-female-age-2024`` and ``census-b01001-female-age-2025`` read
  the 2024 and 2025 ACS 1-year API responses for B01001's nine female age
  bands from 15 to 44 (``B01001_030E`` to ``B01001_038E``) in the 50 states,
  DC and Puerto Rico, as ``census-b01001-female-age-2023`` reads the 2023
  response. The three responses have one header and the same 52 state rows in
  the same order, so no row or column moves.
- ``census-pep-2025-national-age-sex`` reads Vintage 2025
  ``nc-est2025-agesex-res.csv``: ``POPESTIMATE2025`` is column I, where
  Vintage 2024's ``POPESTIMATE2024`` is column H. The SEX and AGE rows are
  Vintage 2024's, in the same order.
- ``census-pep-2025-state-age-sex`` reads Vintage 2025
  ``sc-est2025-alldata6.csv``, the file ``census-pep-2025-state-age-bands``
  pins: ``POPESTIMATE2025`` is column P, where Vintage 2024's
  ``POPESTIMATE2024`` is column O, in Vintage 2024's eighteen five-year groups.
- ``census-stc-individual-income-tax`` builds its manifest's FY2025 flat file
  at 2025.

The expected values are read from the publisher files with ``json`` and
``csv``, apart from Chronicle's parsers.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path

import pytest

from chronicle.artifacts import build_r2_key
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources.cells import validate_source_cells
from chronicle.yaml_io import safe_load as safe_load_yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = REPO_ROOT / "packages" / "census"
DATA = REPO_ROOT / "db" / "data" / "census"

# The API's B01001 variable for each age value: "Estimate!!Total:!!Female:!!15
# to 17 years" to "...!!40 to 44 years", the same labels in 2023, 2024 and 2025.
B01001_VARIABLES = {
    "age_15_to_17": "B01001_030E",
    "age_18_to_19": "B01001_031E",
    "age_20": "B01001_032E",
    "age_21": "B01001_033E",
    "age_22_to_24": "B01001_034E",
    "age_25_to_29": "B01001_035E",
    "age_30_to_34": "B01001_036E",
    "age_35_to_39": "B01001_037E",
    "age_40_to_44": "B01001_038E",
}
# The 50 states, DC (11) and Puerto Rico (72), in the responses' row order.
STATE_FIPS = (
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12", "13", "15", "16",
    "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29",
    "30", "31", "32", "33", "34", "35", "36", "37", "38", "39", "40", "41", "42",
    "44", "45", "46", "47", "48", "49", "50", "51", "53", "54", "55", "56", "72",
)  # fmt: skip
B01001 = {
    "census-b01001-female-age-2024": 2024,
    "census-b01001-female-age-2025": 2025,
}
# Vintage 2024's eighteen five-year groups; AGE 85 in the state file and AGE
# 85 to 100 in the national file hold everyone 85 and over.
PEP_GROUPS = {
    **{f"{age}_to_{age + 4}": (age, age + 4) for age in range(0, 85, 5)},
    "85_plus": (85, None),
}
# (manifest, file key, source id, package id the R2 key names) of each raw file
# this change registers.
RAW_FILES = (
    (
        DATA / "b01001_female_15_44_2024" / "manifest.yaml",
        2024,
        "census_acs",
        "census-b01001-female-age-2024",
    ),
    (
        DATA / "b01001_female_15_44_2025" / "manifest.yaml",
        2025,
        "census_acs",
        "census-b01001-female-age-2025",
    ),
    (
        DATA / "pep_2025_national_age_sex" / "manifest.yaml",
        2025,
        "census_pep",
        "census-pep-2025-national-age-sex",
    ),
    (
        DATA / "stc_individual_income_tax" / "manifest.yaml",
        2025,
        "census_stc",
        "census-stc-individual-income-tax",
    ),
)


def _build(package_id: str, year: int):
    package = load_source_package(package_id)
    rows = package.build_source_rows(year)
    cells = package.build_source_cells(year, source_rows=rows)
    facts = package.build_facts(year, cells=cells, source_rows=rows)
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    return facts


def _package_yaml(directory: str) -> dict:
    path = PACKAGES / directory / "source_package.yaml"
    return safe_load_yaml(path.read_text(encoding="utf-8"))


def _manifest(path: Path) -> dict:
    return safe_load_yaml(path.read_text(encoding="utf-8"))


def _age_bounds(fact) -> dict[str, int]:
    return {
        constraint.operator: int(constraint.value)
        for constraint in fact.constraints
        if constraint.variable == "age"
    }


def _assert_provenance(facts, manifest_path: Path, year: int) -> None:
    entry = _manifest(manifest_path)["files"][year]
    assert {fact.source.source_file for fact in facts} == {entry["filename"]}
    assert {fact.source.url for fact in facts} == {entry["source_url"]}
    assert {fact.source.source_sha256 for fact in facts} == {entry["sha256"]}
    assert {fact.source.raw_r2_uri for fact in facts} == {entry["storage"]["r2"]["uri"]}


def test_new_packages_are_registered_next_to_their_predecessors():
    assert SOURCE_PACKAGE_ALIASES["census-b01001-female-age-2024"] == Path(
        "census/b01001_female_15_44_2024"
    )
    assert SOURCE_PACKAGE_ALIASES["census-b01001-female-age-2025"] == Path(
        "census/b01001_female_15_44_2025"
    )
    assert SOURCE_PACKAGE_ALIASES["census-pep-2025-national-age-sex"] == Path(
        "census/pep_2025_national_age_sex"
    )
    assert SOURCE_PACKAGE_ALIASES["census-pep-2025-state-age-sex"] == Path(
        "census/pep_2025_state_age_sex"
    )
    aliases = list(SOURCE_PACKAGE_ALIASES)
    for predecessor, successors in (
        (
            "census-b01001-female-age-2023",
            ("census-b01001-female-age-2024", "census-b01001-female-age-2025"),
        ),
        ("census-pep-2024-national-age-sex", ("census-pep-2025-national-age-sex",)),
        ("census-pep-2024-state-age-sex", ("census-pep-2025-state-age-sex",)),
    ):
        start = aliases.index(predecessor)
        assert aliases[start + 1 : start + 1 + len(successors)] == list(successors)


@pytest.mark.parametrize(
    ("manifest_path", "year", "source_id", "package_id"), RAW_FILES
)
def test_manifest_entries_pin_the_saved_publisher_bytes(
    manifest_path: Path, year: int, source_id: str, package_id: str
):
    manifest = _manifest(manifest_path)
    entry = manifest["files"][year]
    content = (manifest_path.parent / entry["filename"]).read_bytes()

    assert (manifest["source_id"], manifest["package_id"]) == (source_id, package_id)
    assert entry["sha256"] == hashlib.sha256(content).hexdigest()
    assert entry["size_bytes"] == len(content)
    # The Census API request carried a key; no manifest records one.
    assert "key=" not in entry["source_url"]
    key = build_r2_key(
        source_id=source_id,
        package_id=package_id,
        year=year,
        sha256=entry["sha256"],
        filename=entry["filename"],
        package_path=manifest_path.parent,
    )
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }


@pytest.mark.parametrize("package_id", sorted(B01001))
def test_b01001_query_is_the_2023_query_for_the_new_year(package_id: str):
    year = B01001[package_id]
    old = _manifest(DATA / "b01001_female_15_44_2023" / "manifest.yaml")
    new = _manifest(DATA / f"b01001_female_15_44_{year}" / "manifest.yaml")

    assert new["files"][year]["source_url"] == old["files"][2023]["source_url"].replace(
        "/data/2023/", f"/data/{year}/"
    )
    assert new["source_page"] == old["source_page"].replace("/2023/", f"/{year}/")
    assert new["table"] == old["table"] == "B01001 Sex by Age"


@pytest.mark.parametrize("package_id", sorted(B01001))
def test_b01001_facts_equal_the_api_response_cells(package_id: str):
    year = B01001[package_id]
    raw_dir = DATA / f"b01001_female_15_44_{year}"
    with (raw_dir / f"census_b01001_female_15_44_{year}.json").open(
        encoding="utf-8"
    ) as stream:
        table = json.load(stream)
    header, body = table[0], table[1:]
    assert header == [*B01001_VARIABLES.values(), "state"]
    assert tuple(row[-1] for row in body) == STATE_FIPS
    cells = {row[-1]: dict(zip(header, row, strict=True)) for row in body}

    facts = _build(package_id, year)

    assert len(facts) == 468
    assert {(fact.period.type, fact.period.value) for fact in facts} == {
        ("calendar_year", year)
    }
    assert {fact.source.vintage for fact in facts} == {f"acs_1_year_{year}"}
    _assert_provenance(facts, raw_dir / "manifest.yaml", year)
    seen = set()
    for fact in facts:
        prefix, state, value_id, measure = fact.source_record_id.rsplit(".", 3)
        assert prefix == f"census_acs.acs1_{year}.b01001.female_age"
        assert measure == "female_population"
        assert fact.geography.id == f"0400000US{state}"
        assert fact.filters == {"sex": "female"}
        assert fact.value == int(cells[state][B01001_VARIABLES[value_id]])
        seen.add((state, value_id))
    assert seen == {
        (state, value) for state in STATE_FIPS for value in B01001_VARIABLES
    }


@pytest.mark.parametrize("package_id", sorted(B01001))
def test_b01001_package_has_no_2023_artifact(package_id: str):
    # The default bundle builds at 2023, so it skips this package.
    report = validate_source_package(package_id, year=2023)

    assert not report.valid
    assert [error.code for error in report.errors] == ["source_artifact_unavailable"]


def test_b01001_packages_equal_the_2023_package_but_for_the_edition():
    old = _package_yaml("b01001_female_15_44_2023")
    # The record set ids, prefixes, period and vintage are year templates.
    assert old["artifact"]["vintage"] == "acs_1_year_{year}"
    assert {record_set["period"] for record_set in old["record_sets"]} == {"{year}"}
    for year in sorted(B01001.values()):
        expected = copy.deepcopy(old)
        expected["package_id"] = f"census-b01001-female-age-{year}"
        expected["label"] = (
            f"Census ACS {year} B01001 state female population by age band"
        )
        expected["artifact"].update(
            source_table=(
                f"ACS {year} 1-year detailed table B01001 female age bands by state"
            ),
            resource_directory=f"data/census/b01001_female_15_44_{year}",
            extracted_at="2026-11-26",
        )

        assert _package_yaml(f"b01001_female_15_44_{year}") == expected


def _pep_national_cells(column: str) -> dict[int, int]:
    path = DATA / "pep_2025_national_age_sex" / "nc-est2025-agesex-res.csv"
    by_age = {}
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        # Columns A to H are Vintage 2024's; POPESTIMATE2025 is column I.
        assert reader.fieldnames == [
            "SEX",
            "AGE",
            "ESTIMATESBASE2020",
            *(f"POPESTIMATE{year}" for year in range(2020, 2026)),
        ]
        for row in reader:
            if row["SEX"] == "0":
                by_age[int(row["AGE"])] = int(row[column])
    # Single years 0 to 100 (100 and over) and the all-ages row, 999.
    assert sorted(by_age) == [*range(101), 999]
    return by_age


@pytest.mark.parametrize("build_year", [2025, 2023])
def test_pep_national_2025_facts_equal_the_csv_cells(build_year: int):
    by_age = _pep_national_cells("POPESTIMATE2025")

    # artifact_year pins the Vintage 2025 file, so the 2023 default bundle
    # builds the same July 1, 2025 facts.
    facts = _build("census-pep-2025-national-age-sex", build_year)

    assert len(facts) == 19
    assert {(fact.period.type, fact.period.value) for fact in facts} == {
        ("calendar_year", 2025)
    }
    assert {fact.source.vintage for fact in facts} == {"census_pep_vintage_2025"}
    assert {fact.geography.id for fact in facts} == {"0100000US"}
    _assert_provenance(
        facts, DATA / "pep_2025_national_age_sex" / "manifest.yaml", 2025
    )
    values = {}
    for fact in facts:
        prefix, value_id, measure = fact.source_record_id.rsplit(".", 2)
        assert prefix == "census_pep.cy2025.national_resident_population_age"
        assert measure == "population"
        values[value_id] = fact.value
        if value_id == "all":
            assert not _age_bounds(fact)
            assert fact.value == by_age[999]
            continue
        first, last = PEP_GROUPS[value_id]
        if last is None:
            assert _age_bounds(fact) == {">=": first}
            assert fact.value == sum(by_age[age] for age in range(first, 101))
        else:
            assert _age_bounds(fact) == {">=": first, "<": last + 1}
            assert fact.value == sum(by_age[age] for age in range(first, last + 1))
    assert set(values) == {"all", *PEP_GROUPS}


def test_pep_national_2025_equals_vintage_2024_but_for_the_edition():
    old = _package_yaml("pep_2024_national_age_sex")
    expected = copy.deepcopy(old)
    expected["package_id"] = "census-pep-2025-national-age-sex"
    expected["label"] = "Census PEP Vintage 2025 national resident population by age"
    expected["artifact"].update(
        resource_directory="data/census/pep_2025_national_age_sex",
        manifest="manifest.yaml",
        vintage="census_pep_vintage_2025",
        extracted_at="2026-11-26",
        sheet_name="nc-est2025-agesex-res",
        artifact_year=2025,
    )
    (record_set,) = expected["record_sets"]
    record_set.update(
        record_set_id="census_pep.cy2025.national_resident_population_age",
        source_record_id_prefix="census_pep.cy2025.national_resident_population_age",
        sheet_name="nc-est2025-agesex-res",
        period=2025,
    )
    (measure,) = record_set["measures"]
    assert (measure["column"], measure["expected_column_header"]) == (
        "H",
        "POPESTIMATE2024",
    )
    measure.update(column="I", expected_column_header="POPESTIMATE2025")

    assert _package_yaml("pep_2025_national_age_sex") == expected


def _pep_state_cells(column: str) -> dict[str, list[int]]:
    # Each state's both-sexes, all-origins rows summed over the six race groups,
    # by single year of age (85 is 85 and over).
    path = DATA / "pep_2025_age_sex" / "sc-est2025-alldata6.csv"
    by_age: dict[str, list[int]] = {}
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        # Columns A to O are Vintage 2024's; POPESTIMATE2025 is column P.
        assert reader.fieldnames == [
            "SUMLEV",
            "REGION",
            "DIVISION",
            "STATE",
            "NAME",
            "SEX",
            "ORIGIN",
            "RACE",
            "AGE",
            "ESTIMATESBASE2020",
            *(f"POPESTIMATE{year}" for year in range(2020, 2026)),
        ]
        for row in reader:
            if (row["SUMLEV"], row["SEX"], row["ORIGIN"]) != ("040", "0", "0"):
                continue
            ages = by_age.setdefault(f"{int(row['STATE']):02d}", [0] * 86)
            ages[int(row["AGE"])] += int(row[column])
    assert len(by_age) == 51
    return by_age


@pytest.mark.parametrize("build_year", [2025, 2023])
def test_pep_state_2025_facts_equal_the_csv_cells(build_year: int):
    by_age = _pep_state_cells("POPESTIMATE2025")

    facts = _build("census-pep-2025-state-age-sex", build_year)

    assert len(facts) == 918
    assert {(fact.period.type, fact.period.value) for fact in facts} == {
        ("calendar_year", 2025)
    }
    assert {fact.source.vintage for fact in facts} == {"census_pep_vintage_2025"}
    assert {fact.geography.vintage for fact in facts} == {"2025"}
    _assert_provenance(
        facts, DATA / "pep_2025_age_sex" / "manifest_state_source_package.yaml", 2025
    )
    seen = set()
    for fact in facts:
        prefix, state, value_id, measure = fact.source_record_id.rsplit(".", 3)
        assert prefix == "census_pep.v2025.cy2025.state_resident_population"
        assert measure == "population"
        assert fact.geography.id == f"0400000US{state}"
        first, last = PEP_GROUPS[value_id]
        if last is None:
            assert _age_bounds(fact) == {">=": first}
            assert fact.value == by_age[state][85]
        else:
            assert _age_bounds(fact) == {">=": first, "<": last + 1}
            assert fact.value == sum(by_age[state][first : last + 1])
        seen.add((state, value_id))
    # Like Vintage 2024's package, no state total (chronicle#397).
    assert seen == {(state, value_id) for state in by_age for value_id in PEP_GROUPS}


def test_pep_state_2025_equals_vintage_2024_but_for_the_edition():
    old = _package_yaml("pep_2024_state_age_sex")
    expected = copy.deepcopy(old)
    expected["package_id"] = "census-pep-2025-state-age-sex"
    expected["label"] = "Census PEP Vintage 2025 state resident population by age"
    expected["artifact"].update(
        resource_directory="data/census/pep_2025_age_sex",
        vintage="census_pep_vintage_2025",
        # The date census-pep-2025-state-age-bands gives the same file.
        extracted_at="2026-11-05",
        sheet_name="sc-est2025-alldata6",
        artifact_year=2025,
    )
    for record_set in expected["record_sets"]:
        state = record_set["record_set_id"].rsplit(".", 1)[1]
        record_set_id = f"census_pep.v2025.cy2025.state_resident_population.{state}"
        record_set.update(
            record_set_id=record_set_id,
            source_record_id_prefix=record_set_id,
            sheet_name="sc-est2025-alldata6",
            period=2025,
            geography_vintage="2025",
        )
        (measure,) = record_set["measures"]
        assert (measure["column"], measure["source_column_id"]) == (
            "O",
            "POPESTIMATE2024",
        )
        measure.update(
            column="P",
            source_column_id="POPESTIMATE2025",
            expected_column_header="POPESTIMATE2025",
            source_concept="census_pep.POPESTIMATE2025",
        )

    assert _package_yaml("pep_2025_state_age_sex") == expected
    # The same artifact and manifest as census-pep-2025-state-age-bands.
    bands = _package_yaml("pep_2025_state_age_bands")["artifact"]
    new = _package_yaml("pep_2025_state_age_sex")["artifact"]
    assert (new["resource_directory"], new["manifest"]) == (
        bands["resource_directory"],
        bands["manifest"],
    )


def test_pep_vintages_publish_each_line_and_year_once():
    # Of two vintages' numbers for a line and year Chronicle keeps the later
    # (chronicle#397). Vintage 2024's packages and Vintage 2025's age bands
    # are for 2024; the two new packages are for 2025.
    periods = {
        directory: {
            record_set["period"]
            for record_set in _package_yaml(directory)["record_sets"]
        }
        for directory in (
            "pep_2024_national_age_sex",
            "pep_2024_state_age_sex",
            "pep_2025_state_age_bands",
            "pep_2025_national_age_sex",
            "pep_2025_state_age_sex",
        )
    }

    assert periods == {
        "pep_2024_national_age_sex": {2024},
        "pep_2024_state_age_sex": {2024},
        "pep_2025_state_age_bands": {2024},
        "pep_2025_national_age_sex": {2025},
        "pep_2025_state_age_sex": {2025},
    }


def test_stc_fy2025_facts_equal_the_flat_file_t40_cells():
    report = validate_source_package("census-stc-individual-income-tax", year=2025)
    path = DATA / "stc_individual_income_tax" / "FY2025-Flat-File.txt"
    with path.open(newline="", encoding="utf-8") as stream:
        table = list(csv.reader(stream))
    header = table[0]
    t40_rows = [row for row in table[1:] if row[0] == "T40"]
    # The FY2024 file's layout: the same header and item rows, T40 on line 21.
    with (DATA / "stc_individual_income_tax" / "FY2024-Flat-File.txt").open(
        newline="", encoding="utf-8"
    ) as stream:
        fy2024 = list(csv.reader(stream))
    assert header == fy2024[0]
    assert [row[0] for row in table] == [row[0] for row in fy2024]
    assert len(t40_rows) == 1 and table.index(t40_rows[0]) == 20
    cells = dict(zip(header, t40_rows[0], strict=True))
    published = {code for code in header[1:] if cells[code] != "X"}
    # The file prints X, not a number, for six states, as in FY2024; DC (DC)
    # has a number.
    assert set(header[1:]) - published == {"AK", "FL", "NV", "SD", "TX", "WY"}
    assert "DC" in published

    facts = _build("census-stc-individual-income-tax", 2025)

    assert report.valid
    assert len(facts) == 46
    assert {(fact.period.type, fact.period.value) for fact in facts} == {
        ("fiscal_year", 2025)
    }
    assert {fact.source.vintage for fact in facts} == {"fiscal_year_2025"}
    _assert_provenance(
        facts, DATA / "stc_individual_income_tax" / "manifest.yaml", 2025
    )
    seen = set()
    for fact in facts:
        prefix, code, row, measure = fact.source_record_id.rsplit(".", 3)
        assert prefix == "census_stc.fy2025.individual_income_tax_collections"
        assert (row, measure) == ("t40", "collections")
        # The file reports thousands of dollars (value_scale 1000).
        assert fact.value == int(cells[code.upper()]) * 1000
        seen.add(code.upper())
    assert seen == published


def test_stc_fy2025_builds_the_fy2024_record_sets():
    def shape(year: int) -> set[tuple]:
        return {
            (
                fact.source_record_id.replace(f".fy{year}.", ".fy."),
                fact.geography.id,
                fact.measure,
                fact.entity,
                fact.constraints,
                fact.source.source_table.replace(f"FY{year} ", "FY "),
            )
            for fact in _build("census-stc-individual-income-tax", year)
        }

    assert shape(2025) == shape(2024)


def test_stc_manifest_lists_fy2025_like_fy2024():
    manifest = _manifest(DATA / "stc_individual_income_tax" / "manifest.yaml")
    fy2024, fy2025 = manifest["files"][2024], manifest["files"][2025]

    assert sorted(manifest["files"]) == [2023, 2024, 2025]
    assert set(fy2025) == set(fy2024) | {"fetched_at", "notes"}
    assert fy2025["filename"] == "FY2025-Flat-File.txt"
    assert fy2025["source_url"] == fy2024["source_url"].replace("2024", "2025")
    assert fy2025["source_table"] == fy2024["source_table"].replace("2024", "2025")
    assert fy2025["year"] == 2025
