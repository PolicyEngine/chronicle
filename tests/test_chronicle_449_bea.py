"""BEA new-vintage packages (chronicle#449).

``bea-nipa-total-wages-salaries-2026-11-25`` reads ``NipaDataA.txt`` as BEA
served it after its 2026-11-25 release, the next edition of
``bea-nipa-total-wages-salaries`` (the 2026-04-30 file). Series A034RC differs
from the earlier file for 2021 to 2025, the years BEA's 2026-09-30 annual
update revised, so the 2023 and 2024 cells moved and the 2018 cell did not.

``bea-regional-state-personal-income-components-2026-09-30`` reads
``SAINC.zip`` from BEA's 2026-09-30 release, which carries the annual update of
state personal income, the next edition of
``bea-regional-state-personal-income-components-2024`` (the 2026-04-09 file).
The SAINC5N member keeps its name, header, line codes, descriptions and units.

Each new package is its predecessor's YAML with the package id, label,
vintage, extraction date and raw directory changed, and a release segment in
its record set ids and record id prefixes. No row or column position moved.
The expected values and file lines are read from the publisher files with
``csv`` and ``zipfile``, not through Chronicle's parsers.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
import yaml

from chronicle.consumer_contract import (
    build_aggregate_fact_key,
    build_semantic_fact_key,
    build_source_series_key,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package
from chronicle.sources.cells import validate_source_cells
from chronicle.sources.rows import build_source_row_key
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"
DATA = REPO_ROOT / "db" / "data" / "bea"

NIPA = "bea-nipa-total-wages-salaries-2026-11-25"
REGIONAL = "bea-regional-state-personal-income-components-2026-09-30"
PREDECESSOR = {
    NIPA: "bea-nipa-total-wages-salaries",
    REGIONAL: "bea-regional-state-personal-income-components-2024",
}
# The record id segment each new edition adds after the source namespace.
RELEASE_SEGMENT = {
    NIPA: ("bea_nipa.", "bea_nipa.release_2026_11_25."),
    REGIONAL: ("bea_regional.", "bea_regional.release_2026_09_30."),
}
VINTAGE = {
    NIPA: "bea_nipa_annual_release_2026_11_25",
    REGIONAL: "bea_regional_state_personal_income_2026_09_30",
}
# package -> (raw directory, file name, sha256, size, URL, source page, table)
ARTIFACT = {
    NIPA: (
        DATA / "nipa_total_wages_salaries_2026_11_25",
        "NipaDataA.txt",
        "ee5f1db60c96fa17784a6efe7c728f57a993187318b2989bea2fd296fd7f5b3c",
        12_094_214,
        "https://apps.bea.gov/national/Release/TXT/NipaDataA.txt",
        "https://www.bea.gov/open-data",
        "NIPA Annual Data Flat File",
    ),
    REGIONAL: (
        DATA / "regional_personal_income_state_2026_09_30",
        "SAINC.zip",
        "cb28a9a200c71b48e283c4e4e6ef1b18524cb6c1edc31d7b768862c766ff770f",
        17_620_171,
        "https://apps.bea.gov/regional/zip/SAINC.zip",
        "https://apps.bea.gov/regional/downloadzip.htm",
        "Annual Personal Income by State",
    ),
}
NIPA_FILE = ARTIFACT[NIPA][0] / ARTIFACT[NIPA][1]
SAINC_ZIP = ARTIFACT[REGIONAL][0] / ARTIFACT[REGIONAL][1]
OLD_NIPA_FILE = DATA / "nipa_total_wages_salaries" / "NipaDataA.txt"
OLD_SAINC_ZIP = DATA / "regional_personal_income_state" / "SAINC.zip"
SAINC5N_MEMBER = "SAINC5N__ALL_AREAS_1998_2025.csv"
NIPA_PERIODS = (2018, 2023, 2024)
# SAINC5N line code of each regional record set.
LINE_CODE = {
    "state_personal_income": 10,
    "state_contributions_for_government_social_insurance": 36,
    "state_residence_adjustment": 42,
    "state_dividends_interest_rent": 46,
    "state_personal_current_transfer_receipts": 47,
    "state_wages_salaries": 50,
    "state_supplements_to_wages_salaries": 60,
    "state_proprietors_income": 70,
}
PUBLISHED = {
    # Spot values from the publisher files, as printed: millions of dollars in
    # NipaDataA.txt, thousands of dollars in SAINC5N.
    "bea_nipa.release_2026_11_25.cy2018.total_wages_salaries.a034rc."
    "wages_salaries_amount": 8_899_824 * 1_000_000,
    "bea_nipa.release_2026_11_25.cy2023.total_wages_salaries.a034rc."
    "wages_salaries_amount": 11_735_097 * 1_000_000,
    "bea_nipa.release_2026_11_25.cy2024.total_wages_salaries.a034rc."
    "wages_salaries_amount": 12_410_601 * 1_000_000,
    "bea_regional.release_2026_09_30.cy2023.state_personal_income.us.amount": (
        23_637_147_000 * 1000
    ),
}


def _build(package_id: str, year: int):
    package = load_source_package(package_id)
    rows = package.build_source_rows(year)
    cells = package.build_source_cells(year, source_rows=rows)
    records = package.build_source_records(year, cells=cells, source_rows=rows)
    facts = package.build_facts(year, cells=cells, source_rows=rows)
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    return rows, records, facts


@pytest.fixture(scope="module")
def built():
    """Each new package built at 2023, the default bundle's year."""
    out = {}
    for package_id in (NIPA, REGIONAL):
        rows, records, facts = _build(package_id, 2023)
        assert validate_consumer_fact_contract(facts).valid
        out[package_id] = {
            "facts": facts,
            "records": {record.source_record_id: record for record in records},
            "line_by_row_key": {
                build_source_row_key(row): row.row_number for row in rows
            },
        }
    return out


def _csv_rows(text: str) -> list[list[str]]:
    # Neither file has a quoted line break, so list index + 1 is the file line.
    return list(csv.reader(io.StringIO(text)))


def _nipa_rows(path: Path) -> list[list[str]]:
    return _csv_rows(path.read_bytes().decode("utf-8-sig"))


def _nipa_series(path: Path, series: str) -> dict[int, tuple[int, str]]:
    """Period -> (file line, Value) for one series code."""
    found: dict[int, tuple[int, str]] = {}
    for line, row in enumerate(_nipa_rows(path), start=1):
        if line > 1 and row[0] == series:
            assert int(row[1]) not in found, row
            found[int(row[1])] = (line, row[2])
    return found


def _sainc5n(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        return _csv_rows(archive.read(SAINC5N_MEMBER).decode("utf-8-sig"))


def _sainc5n_by_area_and_line(path: Path) -> dict[tuple[str, int], dict[str, str]]:
    """(GeoName, LineCode) -> the row's cells, plus its file line under "_line"."""
    rows = _sainc5n(path)
    header = rows[0]
    found: dict[tuple[str, int], dict[str, str]] = {}
    for line, row in enumerate(rows[1:], start=2):
        if len(row) != len(header) or row[3] != "SAINC5N":
            continue  # the closing note lines
        record = dict(zip(header, row, strict=True))
        record["_line"] = str(line)
        key = (record["GeoName"], int(record["LineCode"]))
        assert key not in found, key
        found[key] = record
    return found


def _constraint(fact, variable: str):
    (value,) = [c.value for c in fact.constraints if c.variable == variable]
    return value


def _file_line(built_package: dict, fact) -> int:
    (row_key,) = fact.source_row_keys
    return built_package["line_by_row_key"][row_key]


@pytest.mark.parametrize("package_id", [NIPA, REGIONAL])
def test_manifest_registers_the_publisher_file(package_id):
    directory, filename, sha256, size, url, source_page, table = ARTIFACT[package_id]
    manifest = yaml.safe_load((directory / "manifest.yaml").read_text())
    entry = manifest["files"][2024]
    payload = (directory / filename).read_bytes()

    assert hashlib.sha256(payload).hexdigest() == sha256
    assert len(payload) == size
    assert manifest["source_id"] == "bea"
    assert manifest["package_id"] == package_id
    assert manifest["source_page"] == source_page
    assert manifest["table"] == table
    assert entry["filename"] == filename
    assert entry["source_url"] == url
    assert entry["sha256"] == sha256
    assert entry["size_bytes"] == size
    key = f"raw/bea/{package_id}/2024/{sha256}/{filename}"
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }


def test_nipa_facts_are_their_publisher_cells(built):
    _, filename, sha256, _, url, _, _ = ARTIFACT[NIPA]
    published = _nipa_series(NIPA_FILE, "A034RC")
    facts = {fact.period.value: fact for fact in built[NIPA]["facts"]}

    assert len(built[NIPA]["facts"]) == 3
    assert sorted(facts) == list(NIPA_PERIODS)
    for virtual_row, period in enumerate(NIPA_PERIODS, start=2):
        fact = facts[period]
        line, value = published[period]
        assert _file_line(built[NIPA], fact) == line
        # Column C (Value) of the selected row; C1 is its header, B its period.
        assert built[NIPA]["records"][fact.source_record_id].source_cell_addresses == (
            f"C{virtual_row}",
            "C1",
            f"B{virtual_row}",
        )
        # NipaDataA.txt prints millions of dollars with thousands separators.
        assert fact.value == int(value.replace(",", "")) * 1_000_000
        assert fact.value == PUBLISHED[fact.source_record_id]
        assert fact.source_record_id == (
            f"bea_nipa.release_2026_11_25.cy{period}.total_wages_salaries."
            "a034rc.wages_salaries_amount"
        )
        assert fact.period.type == "calendar_year"
        assert fact.geography.id == "0100000US"
        assert _constraint(fact, "bea_nipa.series_code") == "A034RC"
        assert fact.measure.concept == "bea_nipa.wages_and_salaries"
        assert fact.measure.unit == "usd"
        assert fact.source.vintage == VINTAGE[NIPA]
        assert fact.source.source_sha256 == sha256
        assert fact.source.source_file == filename
        assert fact.source.url == url


def test_regional_facts_are_their_publisher_cells(built):
    _, filename, sha256, _, url, _, _ = ARTIFACT[REGIONAL]
    published = _sainc5n_by_area_and_line(SAINC_ZIP)
    seen = set()

    assert len(built[REGIONAL]["facts"]) == 416
    for fact in built[REGIONAL]["facts"]:
        record_set = fact.layout.record_set_id.rsplit(".", 1)[1]
        area = _constraint(fact, "bea_regional.geo_name")
        line_code = _constraint(fact, "bea_regional.line_code")
        assert _constraint(fact, "bea_regional.table_name") == "SAINC5N"
        assert line_code == LINE_CODE[record_set]
        row = published[(area, line_code)]
        assert _file_line(built[REGIONAL], fact) == int(row["_line"])
        # AH is the 2023 column of SAINC5N__ALL_AREAS_1998_2025.csv.
        value_cell, header_cell, *_ = built[REGIONAL]["records"][
            fact.source_record_id
        ].source_cell_addresses
        assert value_cell.startswith("AH") and value_cell[2:].isdigit()
        assert header_cell == "AH1"
        assert row["Unit"] == "Thousands of dollars"
        assert fact.value == int(row["2023"]) * 1000
        fips = row["GeoFIPS"].strip().strip('"')
        expected_area = "0100000US" if fips == "00000" else f"0400000US{fips[:2]}"
        assert fact.geography.id == expected_area
        assert fact.geography.name == area
        assert fact.period.type == "calendar_year"
        assert fact.period.value == 2023
        assert fact.source.vintage == VINTAGE[REGIONAL]
        assert fact.source.source_sha256 == sha256
        assert fact.source.source_file == filename
        assert fact.source.url == url
        if fact.source_record_id in PUBLISHED:
            assert fact.value == PUBLISHED[fact.source_record_id]
        seen.add((area, line_code))
    assert len(seen) == 416 == 52 * len(LINE_CODE)


def test_every_published_spot_value_belongs_to_a_package(built):
    ids = {
        fact.source_record_id for package in built.values() for fact in package["facts"]
    }
    assert set(PUBLISHED) <= ids


def test_nipa_package_reads_the_same_three_cells_at_every_year(built):
    """The NIPA package names its periods literally, so each build year reads
    the same three cells and labels them the same way."""
    expected = sorted(
        (f.source_record_id, f.value, f.period.value) for f in built[NIPA]["facts"]
    )
    for year in (2018, 2024):
        _, _, other = _build(NIPA, year)
        assert sorted((f.source_record_id, f.value, f.period.value) for f in other) == (
            expected
        )


@pytest.mark.parametrize("year", [2009, 2024, 2025])
def test_regional_package_reads_the_requested_year(year):
    published = _sainc5n_by_area_and_line(SAINC_ZIP)
    _, _, facts = _build(REGIONAL, year)

    assert len(facts) == 416
    assert {fact.period.value for fact in facts} == {year}
    assert {fact.source.vintage for fact in facts} == {VINTAGE[REGIONAL]}
    for fact in facts:
        row = published[
            (
                _constraint(fact, "bea_regional.geo_name"),
                _constraint(fact, "bea_regional.line_code"),
            )
        ]
        assert fact.value == int(row[str(year)]) * 1000


@pytest.mark.parametrize("year", [1997, 2026])
def test_regional_package_has_no_year_outside_the_file(year):
    with pytest.raises(ValueError, match=f"No source artifact for year {year}"):
        load_source_package(REGIONAL).build_facts(year)


def test_the_regional_file_is_the_2026_09_30_release():
    assert _sainc5n(SAINC_ZIP)[-2:] == [
        ["Last updated: September 30, 2026-- revised statistics for 2009-2025."],
        ["U.S. Bureau of Economic Analysis"],
    ]
    assert _sainc5n(OLD_SAINC_ZIP)[-2] == [
        "Last updated: April 9, 2026-- new statistics for 2025; revised statistics "
        "for 2020-2024."
    ]


def test_the_cells_keep_their_meaning_between_editions():
    """Differential across the two editions of each file: the header, and for
    every row the package selects its labels, codes and unit, are unchanged."""
    old_nipa, new_nipa = _nipa_rows(OLD_NIPA_FILE), _nipa_rows(NIPA_FILE)
    assert new_nipa[0] == old_nipa[0] == ["%SeriesCode", "Period", "Value"]
    old_series = {p: v for p, (_, v) in _nipa_series(OLD_NIPA_FILE, "A034RC").items()}
    new_series = {p: v for p, (_, v) in _nipa_series(NIPA_FILE, "A034RC").items()}
    assert set(old_series) == set(new_series) == set(range(1929, 2026))
    # The edition differs for 2021 to 2025 and leaves earlier years alone.
    revised = {year for year in new_series if new_series[year] != old_series[year]}
    assert revised == {2021, 2022, 2023, 2024, 2025}

    old_rows, new_rows = _sainc5n(OLD_SAINC_ZIP), _sainc5n(SAINC_ZIP)
    assert new_rows[0] == old_rows[0]
    assert new_rows[0][:8] == [
        "GeoFIPS",
        "GeoName",
        "Region",
        "TableName",
        "LineCode",
        "IndustryClassification",
        "Description",
        "Unit",
    ]
    assert new_rows[0][8:] == [str(year) for year in range(1998, 2026)]
    old_index = _sainc5n_by_area_and_line(OLD_SAINC_ZIP)
    new_index = _sainc5n_by_area_and_line(SAINC_ZIP)
    selected_rows = load_source_package(REGIONAL).artifact.selected_rows
    assert len(selected_rows) == 416
    for selected in selected_rows:
        key = (selected["GeoName"], int(selected["LineCode"]))
        for field in (
            "GeoFIPS",
            "Region",
            "TableName",
            "LineCode",
            "IndustryClassification",
            "Description",
            "Unit",
        ):
            assert new_index[key][field] == old_index[key][field], (key, field)
    with (
        zipfile.ZipFile(OLD_SAINC_ZIP) as old_zip,
        zipfile.ZipFile(SAINC_ZIP) as new_zip,
    ):
        assert new_zip.read("SAINC5N__definition.xml") == old_zip.read(
            "SAINC5N__definition.xml"
        )
        old_notes = old_zip.read("SAINC5N__Footnotes.html").decode().splitlines()
        new_notes = new_zip.read("SAINC5N__Footnotes.html").decode().splitlines()
    changed = [
        (old, new) for old, new in zip(old_notes, new_notes, strict=True) if old != new
    ]
    assert len(changed) == 1
    assert "Last updated: September 30, 2026" in changed[0][1]


def _declarations(package_id: str) -> dict:
    path = PACKAGES_ROOT / SOURCE_PACKAGE_ALIASES[package_id] / "source_package.yaml"
    return yaml.safe_load(path.read_text())


@pytest.mark.parametrize("package_id", [NIPA, REGIONAL])
def test_new_packages_mirror_their_predecessors(package_id):
    """Differential: apart from the package id, label, vintage, extraction
    date, raw directory and the release segment of the record ids, the
    declarations equal the predecessor's."""
    new = _declarations(package_id)
    old = _declarations(PREDECESSOR[package_id])
    namespace, released = RELEASE_SEGMENT[package_id]

    assert new.pop("package_id") == package_id
    assert old.pop("package_id") == PREDECESSOR[package_id]
    new.pop("label")
    old.pop("label")
    assert new["artifact"].pop("vintage") == VINTAGE[package_id]
    old["artifact"].pop("vintage")
    assert new["artifact"].pop("extracted_at") == "2026-11-26"
    old["artifact"].pop("extracted_at")
    assert new["artifact"].pop("resource_directory") == (
        f"data/bea/{ARTIFACT[package_id][0].name}"
    )
    old["artifact"].pop("resource_directory")
    for record_set in old["record_sets"]:
        for key in ("record_set_id", "source_record_id_prefix"):
            assert record_set[key].startswith(namespace)
            record_set[key] = record_set[key].replace(namespace, released, 1)
    assert json.loads(json.dumps(new)) == json.loads(json.dumps(old))


@pytest.mark.parametrize("package_id", [NIPA, REGIONAL])
def test_new_editions_share_their_predecessors_semantic_keys(built, package_id):
    """The two editions form one source series: each 2023-build fact has its
    predecessor's semantic key and source series key, and its own aggregate
    key, because the vintage and file differ."""
    _, _, old_facts = _build(PREDECESSOR[package_id], 2023)
    namespace, released = RELEASE_SEGMENT[package_id]
    old_by_id = {
        fact.source_record_id.replace(namespace, released, 1): fact
        for fact in old_facts
    }
    new_by_id = {fact.source_record_id: fact for fact in built[package_id]["facts"]}

    assert set(new_by_id) == set(old_by_id)
    for record_id, fact in new_by_id.items():
        old = old_by_id[record_id]
        assert build_semantic_fact_key(fact) == build_semantic_fact_key(old)
        assert build_source_series_key(fact) == build_source_series_key(old)
        assert build_aggregate_fact_key(fact) != build_aggregate_fact_key(old)


# The NIPA suite writes all 561,888 rows of NipaDataA.txt, about a minute; the
# default bundle test builds it at 2023 with every other package.
@pytest.mark.parametrize("package_id", [REGIONAL])
def test_source_suite_passes_agent_acceptance(package_id, tmp_path):
    suite = build_source_suite(package_id, tmp_path / package_id, year=2023)

    assert suite.valid
    assert suite.agent_acceptance.valid
    assert suite.agent_acceptance.counts["row_semantic_error_count"] == 0
