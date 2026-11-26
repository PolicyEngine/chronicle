"""Source packages for PolicyEngine/chronicle#408 item 3: VOA Council Tax stock of
properties 2026.

Tables CTSOP1.0 to CTSOP4.0 of the summary workbook become three packages; the three
small-area zips (CTSOP1.1, 3.1 and 4.1) are raw-only registrations, pinned and never
parsed into facts. Counts are the publisher's as fetched on 2026-11-04.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from functools import cache
import hashlib
from pathlib import Path
import re
import subprocess
from xml.etree import ElementTree
import zipfile

from openpyxl.utils import column_index_from_string, get_column_letter
import pytest
import yaml

from chronicle.artifacts import (
    build_r2_key,
    inventory_source_artifacts,
    publish_source_artifacts,
)
from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import (
    build_semantic_fact_key,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "db/data"
SUMMARY = "voa/council_tax_bands_2026"
WORKBOOK = DATA / SUMMARY / "2026_CT_SoP_Summary_Tables.ods"
SUMMARY_SHA256 = "9e9be6944fb8c23a8cdb9491527ebf545072b8f38e8575308d84e595246029d9"
# package id -> (record sets, facts)
PACKAGES = {
    "voa-council-tax-bands-2026": (8, 8_566),
    "voa-council-tax-property-types-2026": (1_120, 120_493),
    "voa-council-tax-build-periods-2026": (1_173, 93_529),
}
# Each package's sheets and the columns that hold counts.
SHEETS = {
    "voa-council-tax-bands-2026": {"CTSOP1_0": ("E", "N"), "CTSOP2_0": ("E", "N")},
    "voa-council-tax-property-types-2026": {"CTSOP3_0": ("F", "AW")},
    "voa-council-tax-build-periods-2026": {"CTSOP4_0": ("F", "AJ")},
}
KINDS = {"ENGWAL", "NATL", "REGL", "CTYMET", "LAUA", "PCON", "UNMD"}
PAGE = "https://www.gov.uk/government/statistics/council-tax-stock-of-properties-2026"
ASSETS = "https://assets.publishing.service.gov.uk/media"
# directory, package id, filename, publisher URL, sha256, bytes, CSV member.
RAW_ZIPS = (
    (
        "voa/ctsop1_1_lsoa_2026",
        "voa-ctsop1-1-lsoa-2026",
        "CTSOP_1_1.zip",
        f"{ASSETS}/6ab25147a9c3d267bcccecc1/CTSOP_1_1.zip",
        "a59b842ae151513aef295b5f9bfe61f99dbfe4fd1e3054010a2c6fb14c6628ae",
        4_311_882,
        "CTSOP_1_1/CTSOP1_1_2026_03_31.csv",
    ),
    (
        "voa/ctsop3_1_lsoa_2026",
        "voa-ctsop3-1-lsoa-2026",
        "CTSOP_3_1__1_.zip",
        f"{ASSETS}/6ab2566afe72ed1e2b02ee4c/CTSOP_3_1__1_.zip",
        "9822bd314c2939a49d230d218257f1ed0fed36f962f64ce4e20f926aa768ac65",
        95_521_582,
        "CTSOP_3_1/CTSOP3_1_2026_03_31.csv",
    ),
    (
        "voa/ctsop4_1_lsoa_2026",
        "voa-ctsop4-1-lsoa-2026",
        "CTSOP_4_1.zip",
        f"{ASSETS}/6aa93b422f29b388848184b8/CTSOP_4_1.zip",
        "5cd6580757035e36d66f76ea9fe7456e064af6f97e558df7393a427f2ba35d05",
        73_430_283,
        "CTSOP_4_1/CTSOP4_1_2026_03_31.csv",
    ),
)
_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


def _cell_value(cell: ElementTree.Element) -> object:
    if cell.get(f"{_OFFICE}value-type") == "float":
        number = float(cell.get(f"{_OFFICE}value"))
        return int(number) if number.is_integer() else number
    text = "\n".join("".join(p.itertext()) for p in cell.iter(f"{_TEXT}p"))
    return text or None


@cache
def _workbook() -> dict[str, dict[tuple[int, str], object]]:
    """Every sheet's cells, read from content.xml without Chronicle's ODS parser."""
    root = ElementTree.fromstring(zipfile.ZipFile(WORKBOOK).read("content.xml"))
    sheets = {}
    for table in root.iter(f"{_TABLE}table"):
        cells: dict[tuple[int, str], object] = {}
        row_number = 0
        for row in table.iter(f"{_TABLE}table-row"):
            repeat = int(row.get(f"{_TABLE}number-rows-repeated", "1"))
            entries, column = [], 0
            for cell in row:
                if cell.tag not in {
                    f"{_TABLE}table-cell",
                    f"{_TABLE}covered-table-cell",
                }:
                    continue
                span = int(cell.get(f"{_TABLE}number-columns-repeated", "1"))
                value = _cell_value(cell)
                if value is not None:
                    entries += [(column + offset, value) for offset in range(span)]
                column += span
            for offset in range(repeat if entries else 0):
                for index, value in entries:
                    cells[(row_number + offset + 1, get_column_letter(index + 1))] = (
                        value
                    )
            row_number += repeat
        sheets[table.get(f"{_TABLE}name")] = cells
    return sheets


def _rows(sheet: str) -> list[int]:
    cells = _workbook()[sheet]
    return sorted(
        row
        for (row, column), value in cells.items()
        if column == "A" and value in KINDS
    )


def _row_of(sheet: str, code: str, band: str | None = None) -> int:
    cells = _workbook()[sheet]
    (row,) = [
        row
        for row in _rows(sheet)
        if cells[(row, "C")] == code and (band is None or cells[(row, "E")] == band)
    ]
    return row


def _columns(first: str, last: str) -> list[str]:
    return [
        get_column_letter(index)
        for index in range(
            column_index_from_string(first), column_index_from_string(last) + 1
        )
    ]


@cache
def _facts(package_id: str) -> dict[str, object]:
    return {
        fact.source_record_id: fact
        for fact in load_source_package(package_id).build_facts(2026)
    }


@cache
def _payload(package_id: str) -> dict:
    path = (
        ROOT / "packages" / SOURCE_PACKAGE_ALIASES[package_id] / "source_package.yaml"
    )
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    return yaml.load(path.read_text(encoding="utf-8"), Loader=loader)


def _manifest(directory: str) -> dict:
    return yaml.safe_load(
        (DATA / directory / "manifest.yaml").read_text(encoding="utf-8")
    )


def _expected_r2(source_id, package_id, year, sha256, filename, directory) -> dict:
    key = build_r2_key(
        source_id=source_id,
        package_id=package_id,
        year=year,
        sha256=sha256,
        filename=filename,
        package_path=DATA / directory,
    )
    assert key == f"raw/uk/{source_id}/{package_id}/{year}/{sha256}/{filename}"
    return {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_packages_validate_register_and_carry_no_anchors(package_id):
    record_sets, count = PACKAGES[package_id]
    package_dir = ROOT / "packages" / SOURCE_PACKAGE_ALIASES[package_id]
    report = validate_source_package(package_dir, year=2026)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["record_set_count"] == record_sets
    assert package_id in UK_BUNDLE_SOURCES
    text = (package_dir / "source_package.yaml").read_text(encoding="utf-8")
    assert not re.search(r"[&*]id\d{3}\b", text)
    built = list(_facts(package_id).values())
    assert len(built) == count
    assert validate_facts(built).valid
    assert validate_consumer_fact_contract(built).valid
    assert max(Counter(build_semantic_fact_key(fact) for fact in built).values()) == 1


def test_summary_manifest_pins_bytes_licence_and_r2():
    manifest = _manifest(SUMMARY)
    assert manifest["package_id"] == "voa-council-tax-bands-2026"
    assert manifest["source_page"] == PAGE
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-04"
    (entry,) = manifest["files"].values()
    content = WORKBOOK.read_bytes()
    assert entry["filename"] == WORKBOOK.name
    assert hashlib.sha256(content).hexdigest() == entry["sha256"] == SUMMARY_SHA256
    assert len(content) == entry["size_bytes"] == 1_391_108
    assert entry["storage"]["r2"] == _expected_r2(
        "voa",
        "voa-council-tax-bands-2026",
        2026,
        SUMMARY_SHA256,
        WORKBOOK.name,
        SUMMARY,
    )
    # The two other packages read the same artifact.
    for package_id in PACKAGES:
        assert (
            _payload(package_id)["artifact"]["resource_directory"] == f"data/{SUMMARY}"
        )


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_facts_are_the_workbook_cells(package_id):
    """Every fact is its cell, and every printed count of a ported row is a fact."""
    workbook = _workbook()
    facts = _facts(package_id)
    covered = set()
    for record_set in _payload(package_id)["record_sets"]:
        sheet = record_set["sheet_name"]
        prefix = record_set["source_record_id_prefix"]
        for row in record_set["rows"]:
            assert (
                workbook[sheet][(row["row_number"], "C")] == row["expected_row_header"]
            )
            for spec in record_set["measures"]:
                fact = facts[f"{prefix}.{row['value_id']}.{spec['measure_id']}"]
                assert (
                    fact.value == workbook[sheet][(row["row_number"], spec["column"])]
                )
                covered.add((sheet, row["row_number"], spec["column"]))
    assert len(covered) == len(facts)
    printed, markers = set(), Counter()
    for sheet, (first, last) in SHEETS[package_id].items():
        rows = _rows(sheet)
        if sheet == "CTSOP2_0":
            rows = [row for row in rows if workbook[sheet][(row, "A")] != "ENGWAL"]
        for row in rows:
            for column in _columns(first, last):
                value = workbook[sheet][(row, column)]
                if isinstance(value, int):
                    printed.add((sheet, row, column))
                else:
                    markers[value] += 1
    assert covered == printed
    assert set(markers) <= {"[z]", "[c]"}


def test_bands_geographies_and_constituency_matching():
    facts = list(_facts("voa-council-tax-bands-2026").values())
    levels = defaultdict(set)
    for fact in facts:
        levels[(fact.geography.level, fact.geography.vintage)].add(fact.geography.id)
    assert {key: len(ids) for key, ids in levels.items()} == {
        ("country", "gss_2025"): 3,
        # The nine regions, and Inner and Outer London.
        ("region", "gss_2025"): 11,
        ("county", "gss_2025"): 27,
        ("local_authority", "lad_2025"): 318,
        ("constituency", "pcon_2024"): 575,
    }
    ids = set().union(*levels.values())
    assert {"E08000038", "E08000039"} <= ids
    assert not {"E08000016", "E08000019"} & ids
    # CTSOP2.0's country and regional rows count matched properties only.
    matches = Counter(
        (
            fact.source_record_id.split(".")[2],
            fact.geography.level,
            fact.filters.get("geography_match"),
        )
        for fact in facts
    )
    assert {key for key in matches if key[0] == "ctsop1_0"} == {
        ("ctsop1_0", level, None)
        for level in ("country", "region", "county", "local_authority")
    }
    assert {key for key in matches if key[0] == "ctsop2_0"} == {
        ("ctsop2_0", "country", "matched"),
        ("ctsop2_0", "region", "matched"),
        ("ctsop2_0", "constituency", None),
        ("ctsop2_0", "country", "unmatched"),
    }
    names = {fact.geography.id: fact.geography.name for fact in facts}
    assert names["W06000023"] == "Powys / Powys"
    assert names["K04000001"] == "England and Wales"


def test_england_and_wales_band_a_and_its_markers():
    facts = _facts("voa-council-tax-bands-2026")
    (england_and_wales,) = [
        fact
        for fact in facts.values()
        if fact.geography.id == "K04000001"
        and fact.measure.concept == "voa.ct_stock_band_a"
        and not fact.filters
    ]
    assert england_and_wales.value == 6_339_720
    assert england_and_wales.period.value == "2026-03"
    assert england_and_wales.period_coverage.end_date == "2026-03-31"
    # England has no band I: its '[z]' cell is no fact; Wales's band I is.
    band_i = {
        fact.geography.id
        for fact in facts.values()
        if fact.measure.concept == "voa.ct_stock_band_i"
        and fact.source_record_id.startswith("voa.ctsop2026.ctsop1_0")
    }
    assert "E92000001" not in band_i and "W92000004" in band_i and len(band_i) == 24


def test_band_cells_sum_to_all_properties_within_rounding():
    """Each count is rounded to the nearest 10, so nine bands and their total can differ
    by up to 5 times ten cells."""
    workbook = _workbook()
    largest = {}
    for sheet in ("CTSOP1_0", "CTSOP2_0"):
        cells = workbook[sheet]
        gaps = []
        for row in _rows(sheet):
            bands = [cells[(row, column)] for column in "EFGHIJKLM"]
            if "[c]" in bands:
                continue
            total = sum(value for value in bands if isinstance(value, int))
            gaps.append(abs(total - cells[(row, "N")]))
        largest[sheet] = max(gaps)
    assert largest == {"CTSOP1_0": 30, "CTSOP2_0": 20}


def test_countries_and_unmatched_reconcile_with_england_and_wales():
    cells = _workbook()
    one, two = cells["CTSOP1_0"], cells["CTSOP2_0"]

    def value(sheet: str, code: str, column: str) -> int:
        found = cells[sheet][(_row_of(sheet, code), column)]
        return found if isinstance(found, int) else 0

    for column in "EFGHIJKLMN":
        england, wales, both = (
            value("CTSOP1_0", code, column)
            for code in ("E92000001", "W92000004", "K04000001")
        )
        assert abs(england + wales - both) <= 15
        matched = sum(
            value("CTSOP2_0", code, column)
            for code in ("E92000001", "W92000004", "Unmatched [note 15]")
        )
        assert abs(matched - value("CTSOP2_0", "K04000001", column)) <= 20
        # The two sheets print one England and Wales row.
        assert both == value("CTSOP2_0", "K04000001", column)
    # CTSOP1.0 counts by billing authority, CTSOP2.0 by matched postcode: the country
    # rows differ by the unmatched properties.
    gap = sum(
        one[(_row_of("CTSOP1_0", code), "N")] - two[(_row_of("CTSOP2_0", code), "N")]
        for code in ("E92000001", "W92000004")
    )
    assert (gap, two[(_row_of("CTSOP2_0", "Unmatched [note 15]"), "N")]) == (
        9_640,
        9_630,
    )


@pytest.mark.parametrize(
    ("sheet", "total_column"), (("CTSOP3_0", "AW"), ("CTSOP4_0", "AJ"))
)
def test_crossed_tables_restate_ctsop1_and_add_up(sheet, total_column):
    """Each band row's All column is CTSOP1.0's count for that band and area; the
    columns and band rows add up within the publisher's rounding."""
    cells = _workbook()[sheet]
    one = _workbook()["CTSOP1_0"]
    band_column = dict(zip("ABCDEFGHI", "EFGHIJKLM"))
    by_area = defaultdict(dict)
    for row in _rows(sheet):
        code, band = cells[(row, "C")], cells[(row, "E")]
        by_area[code][band] = row
        expected = one[
            (_row_of("CTSOP1_0", code), "N" if band == "All" else band_column[band])
        ]
        assert cells[(row, total_column)] == expected, (code, band)
    assert len(by_area) == 359
    columns = _columns("F", total_column)
    headers = {column: cells[(5, column)] for column in columns}
    type_totals = [
        column
        for column, header in headers.items()
        if sheet == "CTSOP3_0"
        and isinstance(header, str)
        and header.endswith(("Bungalow", "Maisonette", "House"))
    ]
    leaves = [
        column for column in columns if column not in {*type_totals, total_column}
    ]
    for row in _rows(sheet):
        values = [cells[(row, column)] for column in leaves]
        if all(isinstance(value, int) for value in values):
            assert abs(sum(values) - cells[(row, total_column)]) <= 5 * (
                len(leaves) + 1
            )
        for total in type_totals:
            parts = [
                column
                for column in leaves
                if str(headers[column]).startswith(f"{headers[total]}:")
            ]
            values = [cells[(row, column)] for column in [*parts, total]]
            if all(isinstance(value, int) for value in values):
                assert abs(sum(values[:-1]) - values[-1]) <= 5 * len(values)
    for code, bands in by_area.items():
        for column in columns:
            values = [cells[(bands[band], column)] for band in bands if band != "All"]
            if all(
                isinstance(value, int)
                for value in [*values, cells[(bands["All"], column)]]
            ):
                assert abs(sum(values) - cells[(bands["All"], column)]) <= 5 * (
                    len(values) + 1
                )


def test_crossed_tables_filters():
    property_types = _facts("voa-council-tax-property-types-2026")
    fact = property_types[
        "voa.ctsop2026.ctsop3_0.band_a.bungalow_1_to_3_bedrooms.full.k04000001.bungalow_1_bedroom"
    ]
    assert fact.filters == {
        "council_tax_band": "A",
        "voa_property_type": "bungalow",
        "voa_bedrooms": "1_bedroom",
    }
    assert (
        fact.value
        == _workbook()["CTSOP3_0"][(_row_of("CTSOP3_0", "K04000001", "A"), "F")]
    )
    totals = [
        fact
        for fact in property_types.values()
        if fact.source_record_id.endswith(".all_properties")
        and fact.geography.id == "K04000001"
    ]
    assert {fact.filters.get("council_tax_band") for fact in totals} == {
        None,
        *"ABCDEFGHI",
    }
    assert all(set(fact.filters) <= {"council_tax_band"} for fact in totals)
    build_periods = _facts("voa-council-tax-build-periods-2026")
    periods = Counter(
        fact.filters.get("voa_build_period") for fact in build_periods.values()
    )
    assert periods["year_2026"] and periods["pre_1900"] and periods["unknown"]
    assert all(isinstance(value, str) for value in periods if value is not None)


@pytest.mark.parametrize(
    (
        "directory",
        "package_id",
        "filename",
        "source_url",
        "sha256",
        "size_bytes",
        "member",
    ),
    RAW_ZIPS,
)
def test_raw_only_registration(
    directory, package_id, filename, source_url, sha256, size_bytes, member
):
    """Each small-area zip is pinned, held in R2 only, and never parsed into facts."""
    manifest = _manifest(directory)
    entry = manifest["files"][2026]
    assert manifest["source_id"] == "voa"
    assert manifest["package_id"] == package_id
    assert manifest["registration_kind"] == "raw_only"
    assert manifest["license"] == "Open Government Licence v3.0"
    assert member in manifest["provenance_notes"]
    assert entry["filename"] == filename
    assert entry["source_url"] == source_url
    assert entry["sha256"] == sha256
    assert entry["size_bytes"] == size_bytes
    assert entry["storage"]["local"] is False
    assert entry["storage"]["r2"] == _expected_r2(
        "voa", package_id, 2026, sha256, filename, directory
    )
    assert package_id not in SOURCE_PACKAGE_ALIASES
    assert package_id not in UK_BUNDLE_SOURCES
    assert not (ROOT / "packages" / directory / "source_package.yaml").exists()
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", f"db/data/{directory}/{filename}"], cwd=ROOT
    )
    assert ignored.returncode == 0
    local = DATA / directory / filename
    if local.exists():
        assert hashlib.sha256(local.read_bytes()).hexdigest() == sha256
        assert member in zipfile.ZipFile(local).namelist()


def test_raw_only_manifests_stay_valid_without_their_bytes(tmp_path):
    for directory, *_ in RAW_ZIPS:
        target = tmp_path / "db" / "data" / directory
        target.mkdir(parents=True)
        (target / "manifest.yaml").write_bytes(
            (DATA / directory / "manifest.yaml").read_bytes()
        )
    inventory = inventory_source_artifacts(tmp_path / "db" / "data")
    published = publish_source_artifacts(
        tmp_path / "db" / "data", wrangler_command="false"
    )
    assert inventory.valid
    assert inventory.counts["missing_count"] == 0
    assert inventory.counts["r2_only_count"] == 3
    assert published.valid
    assert published.counts["skipped_count"] == 3
    assert published.counts["uploaded_count"] == 0
