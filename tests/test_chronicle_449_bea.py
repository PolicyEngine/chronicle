"""BEA new-vintage packages (chronicle#449).

Four packages read ``NipaDataA.txt`` as BEA served it after its 2026-11-25
release, the next editions of the four packages that read the 2026-04-30 file:
``bea-nipa-total-wages-salaries-2026-11-25``,
``bea-nipa-personal-income-components-2026-11-25``,
``bea-nipa-personal-income-disposition-2026-11-25`` and
``bea-nipa-pension-contributions-2026-11-25``. Against the earlier file, every
series they read keeps its years, and its values change only for 2021 to
2025, the years BEA's 2026-09-30 annual update revised.

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
COMPONENTS = "bea-nipa-personal-income-components-2026-11-25"
DISPOSITION = "bea-nipa-personal-income-disposition-2026-11-25"
PENSION = "bea-nipa-pension-contributions-2026-11-25"
REGIONAL = "bea-regional-state-personal-income-components-2026-09-30"
NIPA_FILE_PACKAGES = (NIPA, COMPONENTS, DISPOSITION, PENSION)
NEW_PACKAGES = (*NIPA_FILE_PACKAGES, REGIONAL)
PREDECESSOR = {
    NIPA: "bea-nipa-total-wages-salaries",
    COMPONENTS: "bea-nipa-personal-income-components",
    DISPOSITION: "bea-nipa-personal-income-disposition",
    PENSION: "bea-nipa-pension-contributions",
    REGIONAL: "bea-regional-state-personal-income-components-2024",
}
# The record id segment each new edition adds after the source namespace.
NIPA_SEGMENT = ("bea_nipa.", "bea_nipa.release_2026_11_25.")
RELEASE_SEGMENT = {
    **dict.fromkeys(NIPA_FILE_PACKAGES, NIPA_SEGMENT),
    REGIONAL: ("bea_regional.", "bea_regional.release_2026_09_30."),
}
VINTAGE = {
    **dict.fromkeys(NIPA_FILE_PACKAGES, "bea_nipa_annual_release_2026_11_25"),
    REGIONAL: "bea_regional_state_personal_income_2026_09_30",
}
# manifest owner -> (raw directory, file name, sha256, size, URL, source page,
# table). The four NIPA packages share the first package's directory, as their
# predecessors share theirs.
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
ARTIFACT_OF = {**dict.fromkeys(NIPA_FILE_PACKAGES, NIPA), REGIONAL: REGIONAL}
NIPA_FILE = ARTIFACT[NIPA][0] / ARTIFACT[NIPA][1]
SAINC_ZIP = ARTIFACT[REGIONAL][0] / ARTIFACT[REGIONAL][1]
OLD_NIPA_FILE = DATA / "nipa_total_wages_salaries" / "NipaDataA.txt"
OLD_SAINC_ZIP = DATA / "regional_personal_income_state" / "SAINC.zip"
SAINC5N_MEMBER = "SAINC5N__ALL_AREAS_1998_2025.csv"
# The NIPA series each package selects, in declaration order.
NIPA_SERIES = {
    NIPA: ("A034RC",),
    COMPONENTS: (
        "A041RC",
        "A048RC",
        "A064RC",
        "B703RC",
        "A038RC",
        "B040RC",
        "B039RC",
        "B042RC",
        "A045RC",
        "A063RC",
        "W823RC",
        "W824RC",
        "W729RC",
        "W825RC",
        "W826RC",
        "W827RC",
        "B931RC",
        "A577RC",
    ),
    DISPOSITION: ("A065RC", "W055RC", "A067RC", "A068RC", "A071RC", "A072RC"),
    PENSION: ("W351RC", "Y351RC"),
}
# Total wages and salaries names its three years; the others read the year
# they are built for.
WAGES_PERIODS = (2018, 2023, 2024)
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
    # Spot values from the publisher files, as printed: millions of dollars
    # (and one percentage) in NipaDataA.txt, thousands of dollars in SAINC5N.
    "bea_nipa.release_2026_11_25.cy2018.total_wages_salaries.a034rc."
    "wages_salaries_amount": 8_899_824 * 1_000_000,
    "bea_nipa.release_2026_11_25.cy2023.total_wages_salaries.a034rc."
    "wages_salaries_amount": 11_735_097 * 1_000_000,
    "bea_nipa.release_2026_11_25.cy2024.total_wages_salaries.a034rc."
    "wages_salaries_amount": 12_410_601 * 1_000_000,
    "bea_nipa.release_2026_11_25.cy2023.personal_interest_income.a064rc.amount": (
        2_079_352 * 1_000_000
    ),
    "bea_nipa.release_2026_11_25.cy2023.personal_income.a065rc.amount": (
        23_642_338 * 1_000_000
    ),
    "bea_nipa.release_2026_11_25.cy2023.personal_saving_rate.a072rc.rate": 6.1,
    "bea_nipa.release_2026_11_25.cy2023.defined_contribution_employer_contributions."
    "w351rc.employer_contributions": 269_697 * 1_000_000,
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


def _built(package_id: str, year: int) -> dict:
    rows, records, facts = _build(package_id, year)
    return {
        "facts": facts,
        "records": {record.source_record_id: record for record in records},
        "line_by_row_key": {build_source_row_key(row): row.row_number for row in rows},
    }


@pytest.fixture(scope="module")
def built():
    """Each new package built at 2023, the default bundle's year."""
    out = {package_id: _built(package_id, 2023) for package_id in NEW_PACKAGES}
    for package in out.values():
        assert validate_consumer_fact_contract(package["facts"]).valid
    return out


def _csv_rows(text: str) -> list[list[str]]:
    # Neither file has a quoted line break, so list index + 1 is the file line.
    return list(csv.reader(io.StringIO(text)))


def _nipa_rows(path: Path) -> list[list[str]]:
    return _csv_rows(path.read_bytes().decode("utf-8-sig"))


def _nipa_cells(path: Path) -> dict[tuple[str, int], tuple[int, str]]:
    """(series code, year) -> (file line, Value) for the series the packages read."""
    wanted = {code for codes in NIPA_SERIES.values() for code in codes}
    found: dict[tuple[str, int], tuple[int, str]] = {}
    for line, row in enumerate(_nipa_rows(path), start=1):
        if line == 1 or row[0] not in wanted:
            continue
        key = (row[0], int(row[1]))
        assert key not in found, row
        found[key] = (line, row[2])
    return found


@pytest.fixture(scope="module")
def nipa_cells():
    return {"new": _nipa_cells(NIPA_FILE), "old": _nipa_cells(OLD_NIPA_FILE)}


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


def _nipa_value(printed: str, unit: str):
    # NipaDataA.txt prints dollar series in millions with thousands
    # separators, and the saving rate as a percentage.
    if unit == "percent":
        return float(printed)
    assert unit == "usd"
    return int(printed.replace(",", "")) * 1_000_000


def _selected(package_id: str, year: int) -> list[tuple[str, int]]:
    """The (series, year) cells a build selects, in their virtual-row order."""
    if package_id == NIPA:
        return [("A034RC", period) for period in WAGES_PERIODS]
    return [(series, year) for series in NIPA_SERIES[package_id]]


def _assert_nipa_facts(package_id: str, built_package: dict, cells: dict, year: int):
    selected = _selected(package_id, year)
    facts = {
        (_constraint(fact, "bea_nipa.series_code"), fact.period.value): fact
        for fact in built_package["facts"]
    }
    assert len(built_package["facts"]) == len(selected)
    assert sorted(facts) == sorted(selected)
    _, filename, sha256, _, url, _, _ = ARTIFACT[NIPA]
    for virtual_row, key in enumerate(selected, start=2):
        fact = facts[key]
        line, printed = cells[key]
        assert _file_line(built_package, fact) == line
        addresses = built_package["records"][
            fact.source_record_id
        ].source_cell_addresses
        # Column C (Value) of the selected row; B is its year, C1 the header.
        assert addresses[0] == f"C{virtual_row}"
        assert f"B{virtual_row}" in addresses
        assert fact.value == _nipa_value(printed, fact.measure.unit)
        assert fact.source_record_id.startswith(
            f"bea_nipa.release_2026_11_25.cy{key[1]}."
        )
        assert fact.period.type == "calendar_year"
        assert fact.geography.id == "0100000US"
        assert fact.source.vintage == VINTAGE[package_id]
        assert fact.source.source_sha256 == sha256
        assert fact.source.source_file == filename
        assert fact.source.url == url
        if fact.source_record_id in PUBLISHED:
            assert fact.value == PUBLISHED[fact.source_record_id]


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


@pytest.mark.parametrize("package_id", NIPA_FILE_PACKAGES)
def test_nipa_package_reads_the_shared_2026_11_25_file(package_id):
    artifact = load_source_package(package_id).artifact
    predecessor = load_source_package(PREDECESSOR[package_id]).artifact

    assert (
        artifact.resource_directory == "data/bea/nipa_total_wages_salaries_2026_11_25"
    )
    assert predecessor.resource_directory == "data/bea/nipa_total_wages_salaries"
    assert artifact.manifest == predecessor.manifest == "manifest.yaml"
    assert artifact.artifact_year == predecessor.artifact_year == 2024


@pytest.mark.parametrize("package_id", NIPA_FILE_PACKAGES)
def test_nipa_facts_are_their_publisher_cells(built, nipa_cells, package_id):
    _assert_nipa_facts(package_id, built[package_id], nipa_cells["new"], 2023)


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


def test_fact_counts_and_periods_at_the_bundle_year(built):
    counts = {package_id: len(built[package_id]["facts"]) for package_id in built}
    periods = {
        package_id: sorted({fact.period.value for fact in built[package_id]["facts"]})
        for package_id in built
    }

    assert counts == {
        NIPA: 3,
        COMPONENTS: 18,
        DISPOSITION: 6,
        PENSION: 2,
        REGIONAL: 416,
    }
    assert periods == {
        NIPA: [2018, 2023, 2024],
        COMPONENTS: [2023],
        DISPOSITION: [2023],
        PENSION: [2023],
        REGIONAL: [2023],
    }


def test_wages_package_reads_the_same_three_cells_at_every_year(built):
    """Total wages and salaries names its periods literally, so each build year
    reads the same three cells and labels them the same way."""
    expected = sorted(
        (f.source_record_id, f.value, f.period.value) for f in built[NIPA]["facts"]
    )
    for year in (2018, 2024):
        _, _, other = _build(NIPA, year)
        assert sorted((f.source_record_id, f.value, f.period.value) for f in other) == (
            expected
        )


@pytest.mark.parametrize("year", [2024, 2025])
@pytest.mark.parametrize("package_id", [COMPONENTS, DISPOSITION, PENSION])
def test_year_selecting_nipa_packages_read_the_requested_year(
    nipa_cells, package_id, year
):
    _assert_nipa_facts(package_id, _built(package_id, year), nipa_cells["new"], year)


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


def test_every_nipa_series_keeps_its_years_and_changes_only_2021_to_2025(
    nipa_cells,
):
    """Differential across the two NipaDataA.txt editions for every series the
    four packages read: no year is dropped, and only 2021 to 2025 change. The
    defined contribution series gain 2025."""
    assert (
        _nipa_rows(NIPA_FILE)[0]
        == _nipa_rows(OLD_NIPA_FILE)[0]
        == [
            "%SeriesCode",
            "Period",
            "Value",
        ]
    )
    old, new = nipa_cells["old"], nipa_cells["new"]
    added = {}
    for series in {code for codes in NIPA_SERIES.values() for code in codes}:
        old_years = {year for code, year in old if code == series}
        new_years = {year for code, year in new if code == series}
        assert old_years <= new_years, series
        added[series] = new_years - old_years
        revised = {
            year
            for year in old_years
            if old[(series, year)][1] != new[(series, year)][1]
        }
        assert revised <= set(range(2021, 2026)), (series, revised)
    assert {series: years for series, years in added.items() if years} == {
        "W351RC": {2025},
        "Y351RC": {2025},
    }
    # The edition moves the 2023 and 2024 wages and salaries and keeps 2018.
    assert new[("A034RC", 2018)][1] == old[("A034RC", 2018)][1]
    assert new[("A034RC", 2023)][1] != old[("A034RC", 2023)][1]
    assert new[("A034RC", 2024)][1] != old[("A034RC", 2024)][1]


def test_the_sainc5n_cells_keep_their_meaning_between_editions():
    """Differential across the two SAINC.zip editions: the header, and for
    every row the package selects its labels, codes and unit, are unchanged."""
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


@pytest.mark.parametrize("package_id", NEW_PACKAGES)
def test_new_packages_mirror_their_predecessors(package_id):
    """Differential: apart from the package id, label, vintage, extraction
    date, raw directory and the release segment of the record ids, the
    declarations equal the predecessor's."""
    new = _declarations(package_id)
    old = _declarations(PREDECESSOR[package_id])
    namespace, released = RELEASE_SEGMENT[package_id]

    assert new.pop("package_id") == package_id
    assert old.pop("package_id") == PREDECESSOR[package_id]
    # The label names the release; the regional predecessor's named a year.
    release = "2026-09-30" if package_id == REGIONAL else "2026-11-25"
    old_label = old.pop("label").replace("BEA Regional 2024 ", "BEA Regional ")
    assert new.pop("label") == f"{old_label}, {release} release"
    assert new["artifact"].pop("vintage") == VINTAGE[package_id]
    old["artifact"].pop("vintage")
    assert new["artifact"].pop("extracted_at") == "2026-11-26"
    old["artifact"].pop("extracted_at")
    assert new["artifact"].pop("resource_directory") == (
        f"data/bea/{ARTIFACT[ARTIFACT_OF[package_id]][0].name}"
    )
    old["artifact"].pop("resource_directory")
    for record_set in old["record_sets"]:
        for key in ("record_set_id", "source_record_id_prefix"):
            assert record_set[key].startswith(namespace)
            record_set[key] = record_set[key].replace(namespace, released, 1)
    assert json.loads(json.dumps(new)) == json.loads(json.dumps(old))


@pytest.mark.parametrize("package_id", NEW_PACKAGES)
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


# A NIPA suite writes all 561,888 rows of NipaDataA.txt, about a minute each;
# the default bundle test builds the four at 2023 with every other package.
@pytest.mark.parametrize("package_id", [REGIONAL])
def test_source_suite_passes_agent_acceptance(package_id, tmp_path):
    suite = build_source_suite(package_id, tmp_path / package_id, year=2023)

    assert suite.valid
    assert suite.agent_acceptance.valid
    assert suite.agent_acceptance.counts["row_semantic_error_count"] == 0
