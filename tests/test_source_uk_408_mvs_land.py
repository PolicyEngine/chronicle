"""Source packages for PolicyEngine/chronicle#408 items 2 and 8.

The Market Value Survey 2024 annex tables, land by institutional sector in both pinned
national balance sheet workbooks, and ONS's 2022 series for land underlying dwellings and
other buildings and structures. The Market Value Survey's expected values are read from
the pinned workbooks here, never written into this file.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import io
from pathlib import Path

from openpyxl import load_workbook
import pandas as pd
import pytest
import yaml

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
# package id -> (artifact year, record sets, facts)
PACKAGES = {
    "mhclg-market-value-survey-2024-chapter-1": (2024, 194, 3984),
    "mhclg-market-value-survey-2024-chapter-3": (2024, 22, 274),
    "mhclg-market-value-survey-2024-chapter-4": (2024, 47, 200),
    "ons-land-underlying-buildings-2022": (2022, 27, 108),
    "ons-national-balance-sheet-land-2025": (2024, 360, 360),
    "ons-national-balance-sheet-land-preliminary-2026": (2026, 12, 12),
}
NEW_ARTIFACTS = {
    "mhclg-market-value-survey-2024-chapter-1": (
        "47b57f7680092a080c647024f8cf9232e9fb75439d99966ed1701f6edb290512",
        86895,
    ),
    "mhclg-market-value-survey-2024-chapter-3": (
        "2725e15842d6b28faa11835f40a142afe6a1b7e5a24f7c1d4f46de27b6db364b",
        37212,
    ),
    "mhclg-market-value-survey-2024-chapter-4": (
        "fc27131ea159145be7f6c61ae0a6b873ec4c2e63db06516dbb0c3689b2dd056f",
        15838,
    ),
    "ons-land-underlying-buildings-2022": (
        "1b99e4f94383d5aa39d4829454cfc12bc6f46dc58ad54c9bafcf9614cfc2fd0f",
        1275,
    ),
}
MVS = [package_id for package_id in PACKAGES if package_id.startswith("mhclg-market")]
# CDID -> (sheet, column, entity role)
SECTORS = {
    "E44R": ("Table 2", "V", "total_economy"),
    "E43B": ("Table 3", "V", "non_financial_corporations"),
    "E43E": ("Table 4", "V", "public_non_financial_corporations"),
    "E43J": ("Table 5", "V", "private_non_financial_corporations"),
    "E43K": ("Table 6", "T", "financial_corporations"),
    "E43Z": ("Table 7", "T", "general_government"),
    "E447": ("Table 8", "T", "central_government"),
    "E44C": ("Table 9", "S", "local_government"),
    "E44D": ("Table 10", "T", "households_and_npish"),
    "E44N": ("Table 11", "S", "households"),
    "E44O": ("Table 12", "T", "non_profit_institutions_serving_households"),
    "E44Q": ("Table 13", "V", "public_sector"),
}


def _facts(package_id: str) -> list:
    year = PACKAGES[package_id][0]
    return load_source_package(package_id).build_facts(year)


def _records(package_id: str) -> list:
    year = PACKAGES[package_id][0]
    return load_source_package(package_id).build_source_records(year)


def _manifest(package_id: str) -> dict:
    data_dir = DATA / SOURCE_PACKAGE_ALIASES[package_id]
    return yaml.safe_load((data_dir / "manifest.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_packages_validate_register_and_carry_no_anchors(package_id):
    year, record_sets, count = PACKAGES[package_id]
    package_dir = ROOT / "packages" / SOURCE_PACKAGE_ALIASES[package_id]
    report = validate_source_package(package_dir, year=year)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["record_set_count"] == record_sets
    assert package_id in UK_BUNDLE_SOURCES
    text = (package_dir / "source_package.yaml").read_text(encoding="utf-8")
    assert not any(
        isinstance(token, (yaml.AnchorToken, yaml.AliasToken))
        for token in yaml.scan(text)
    )
    built = _facts(package_id)
    assert len(built) == count
    assert validate_facts(built).valid
    contract = validate_consumer_fact_contract(built)
    assert contract.valid, contract.to_dict()
    assert max(Counter(build_semantic_fact_key(fact) for fact in built).values()) == 1


@pytest.mark.parametrize("package_id", sorted(NEW_ARTIFACTS))
def test_new_manifests_pin_bytes_and_licence(package_id):
    manifest = _manifest(package_id)
    assert manifest["package_id"] == package_id
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-04"
    (entry,) = manifest["files"].values()
    content = (
        DATA / SOURCE_PACKAGE_ALIASES[package_id] / entry["filename"]
    ).read_bytes()
    sha256, size = NEW_ARTIFACTS[package_id]
    assert hashlib.sha256(content).hexdigest() == entry["sha256"] == sha256
    assert len(content) == entry["size_bytes"] == size


def test_the_balance_sheet_blocks_only_add_to_the_packages():
    """The sector record sets follow the packages' own, which stay as they were."""
    marker = (
        "# Sector record sets below are written by scripts/build_uk_408_packages.py"
    )
    for package_id in (
        "ons-national-balance-sheet-land-2025",
        "ons-national-balance-sheet-land-preliminary-2026",
    ):
        path = (
            ROOT
            / "packages"
            / SOURCE_PACKAGE_ALIASES[package_id]
            / "source_package.yaml"
        )
        text = path.read_text(encoding="utf-8")
        assert text.count(marker) == 1
        payload = yaml.safe_load(text)
        roles = Counter(record["entity_role"] for record in payload["record_sets"])
        per_role = 1 if "preliminary" in package_id else 30
        assert roles == {role: per_role for _, _, role in SECTORS.values()}


def _workbook_series(package_id: str) -> dict[str, dict[int, int]]:
    (entry,) = _manifest(package_id)["files"].values()
    path = DATA / SOURCE_PACKAGE_ALIASES[package_id] / entry["filename"]
    workbook = load_workbook(path, data_only=True, read_only=True)
    series = {}
    for cdid, (sheet, column, _) in SECTORS.items():
        worksheet = workbook[sheet]
        assert worksheet[f"{column}8"].value == cdid
        assert worksheet[f"{column}7"].value == "AN.211"
        series[cdid] = {
            row[0].value: worksheet[f"{column}{row[0].row}"].value
            for row in worksheet.iter_rows(min_row=9, max_row=60, max_col=1)
            if isinstance(row[0].value, int) and row[0].value >= 1995
        }
    return series


@pytest.mark.parametrize(
    "package_id,years",
    [
        ("ons-national-balance-sheet-land-2025", range(1995, 2025)),
        ("ons-national-balance-sheet-land-preliminary-2026", range(2025, 2026)),
    ],
)
def test_sector_land_is_the_workbook_cells_and_adds_up(package_id, years):
    series = _workbook_series(package_id)
    by_role = {role: cdid for cdid, (_, _, role) in SECTORS.items()}
    facts = defaultdict(dict)
    for fact in _facts(package_id):
        facts[by_role[fact.entity.role]][fact.period.value] = fact.value
    for cdid in SECTORS:
        assert set(facts[cdid]) == set(years), cdid
        for year in years:
            assert facts[cdid][year] == series[cdid][year] * 1_000_000, (cdid, year)
    for year in years:
        land = {cdid: facts[cdid][year] for cdid in SECTORS}
        # ONS's sector tree: every identity holds exactly in both workbooks.
        assert land["E44D"] == land["E44N"] + land["E44O"]
        assert land["E43Z"] == land["E447"] + land["E44C"]
        assert land["E44Q"] == land["E43Z"] + land["E43E"]
        assert land["E43B"] == land["E43E"] + land["E43J"]
        assert land["E44R"] == land["E43B"] + land["E43K"] + land["E43Z"] + land["E44D"]


def test_land_article_2022_is_the_csv():
    package_id = "ons-land-underlying-buildings-2022"
    (entry,) = _manifest(package_id)["files"].values()
    text = (DATA / SOURCE_PACKAGE_ALIASES[package_id] / entry["filename"]).read_text(
        encoding="utf-8"
    )
    lines = list(csv.reader(io.StringIO(text)))
    assert [cell.strip() for cell in lines[4]] == ["Unit", "£ trillion"]
    assert lines[6] == [
        "Year",
        "Total non-produced assets",
        "Land underlying dwellings",
        "Land underlying other buildings and structures",
        "Other non-produced assets",
    ]
    published = {
        int(line[0]): [float(value) for value in line[1:]] for line in lines[7:]
    }
    assert sorted(published) == list(range(1995, 2022))
    concepts = [
        "ons.non_produced_assets_value",
        "ons.land_underlying_dwellings_value",
        "ons.land_underlying_other_buildings_and_structures_value",
        "ons.other_non_produced_assets_value",
    ]
    for fact in _facts(package_id):
        column = concepts.index(fact.measure.concept)
        assert fact.value == round(published[fact.period.value][column] * 1e12)
    for total, *parts in published.values():
        # 'The components of land may not always add to the total because of rounding.'
        assert abs(total - sum(parts)) <= 0.1 + 1e-9


def _ods_cells(package_id: str) -> dict[str, pd.DataFrame]:
    (entry,) = _manifest(package_id)["files"].values()
    path = DATA / SOURCE_PACKAGE_ALIASES[package_id] / entry["filename"]
    return pd.read_excel(path, sheet_name=None, header=None, engine="odf")


def _address(address: str) -> tuple[int, int]:
    letters = "".join(character for character in address if character.isalpha())
    number = int(address[len(letters) :])
    column = 0
    for character in letters:
        column = column * 26 + ord(character) - 64
    return number - 1, column - 1


@pytest.mark.parametrize("package_id", MVS)
def test_mvs_facts_are_the_workbook_cells(package_id):
    sheets = _ods_cells(package_id)
    records = _records(package_id)
    assert len(records) == PACKAGES[package_id][2]
    for record in records:
        selector = record.spec.selector
        row, column = _address(selector.address)
        printed = sheets[selector.sheet_name].iat[row, column]
        assert isinstance(printed, (int, float)), (
            selector.sheet_name,
            selector.address,
        )
        scale = record.spec.value_scale
        assert record.value == pytest.approx(printed * scale, rel=1e-12, abs=1e-9), (
            selector.sheet_name,
            selector.address,
        )


@pytest.mark.parametrize("package_id", MVS)
def test_mvs_sample_sizes_are_positive_integers(package_id):
    sizes = [
        fact.value
        for fact in _facts(package_id)
        if fact.measure.concept == "mhclg.mvs_sample_size"
    ]
    assert sizes
    assert all(isinstance(size, int) and size > 0 for size in sizes)


def _declared(package_id: str) -> dict[str, set]:
    """Each sheet's declared (block, period, row) and (block, period, measure) pairs."""
    path = (
        ROOT / "packages" / SOURCE_PACKAGE_ALIASES[package_id] / "source_package.yaml"
    )
    declared = defaultdict(set)
    for record in yaml.safe_load(path.read_text(encoding="utf-8"))["record_sets"]:
        parts = record["record_set_id"].split(".")
        block = ".".join(parts[3:-1])
        for row in record["rows"]:
            declared[record["sheet_name"]].add((block, "row", row["value_id"]))
        for measure in record["measures"]:
            declared[record["sheet_name"]].add(
                (block, "measure", measure["measure_id"])
            )
    return declared


def test_mvs_a_and_b_sheets_cover_the_same_categories():
    for package_id in MVS:
        declared = _declared(package_id)
        for sheet in declared:
            if (
                sheet.endswith("a")
                and f"{sheet[:-1]}b" in declared
                and sheet != "AT1_6a"
            ):
                assert declared[sheet] == declared[f"{sheet[:-1]}b"], sheet
    chapter_1 = _declared("mhclg-market-value-survey-2024-chapter-1")
    imd = {item for item in chapter_1["AT1_6a"] if item[0].startswith("imd_decile")}
    assert imd == chapter_1["AT1_6b"]


@pytest.mark.parametrize("package_id", MVS)
def test_mvs_complete_percentage_columns_sum_to_100(package_id):
    """A percentage column that prints every row of its block sums to 100.

    Annex Table 4.5's percentages are of the table's whole base, so its two blocks sum
    to 100 together. AT4.1's and AT4.2's rest-of-England columns port only the band that
    Chapter 1 does not print, so they are not whole distributions here.
    """
    columns = defaultdict(dict)
    rows = defaultdict(set)
    for fact in _facts(package_id):
        if not fact.measure.concept.endswith("_percentage"):
            continue
        # <record set family>.<full|subset_n>.<row>.<measure>
        *family, _subset, row, measure = fact.source_record_id.split(".")
        if family[2] == "at4_1" or family[-1] == "rest_of_england":
            continue
        if family[2] == "at4_5":
            family = family[:3] + family[4:]
            row = fact.source_record_id.split(".")[3] + "." + row
        columns[(tuple(family), measure)][row] = fact.value
        rows[tuple(family)].add(row)
    complete = {
        key: values for key, values in columns.items() if set(values) == rows[key[0]]
    }
    assert complete
    for key, values in complete.items():
        assert sum(values.values()) == pytest.approx(100, abs=0.5), key


TENURE_COLUMNS = tuple((column, column) for column in "CDEFGHJKLMNO")
REST_OF_ENGLAND = (("D", "H"), ("G", "O"))
# Chapter 4 rows that print Chapter 1's cells again: (sheet, row, Chapter 1 sheet, row,
# column pairs). They are asserted here, not ported.
CHAPTER_4_RESTATES = (
    ("AT4_1", 12, "AT1_2a", 19, TENURE_COLUMNS),
    ("AT4_1", 13, "AT1_2a", 20, TENURE_COLUMNS),
    ("AT4_1", 18, "AT1_2a", 32, TENURE_COLUMNS),
    ("AT4_1", 19, "AT1_2a", 33, TENURE_COLUMNS),
    ("AT4_1", 21, "AT1_1a", 15, TENURE_COLUMNS),
    ("AT4_2", 11, "AT1_2b", 19, REST_OF_ENGLAND),
    ("AT4_2", 12, "AT1_2b", 20, REST_OF_ENGLAND),
    ("AT4_2", 17, "AT1_2b", 32, REST_OF_ENGLAND),
    ("AT4_2", 18, "AT1_2b", 33, REST_OF_ENGLAND),
    ("AT4_2", 20, "AT1_1b", 15, REST_OF_ENGLAND),
    ("AT4_2", 20, "AT1_3", 28, (("C", "H"), ("F", "O"))),
)
# AT4.1 prints its 2024 all-dwellings base with two digits transposed against AT1.1A.
TRANSPOSED = {("AT4_1", 21, "O")}


def _cell(sheets: dict[str, pd.DataFrame], sheet: str, column: str, row: int):
    return sheets[sheet].iat[_address(f"{column}{row}")]


def test_chapter_4_rows_restating_chapter_1_are_asserted_not_ported():
    chapter_1 = _ods_cells("mhclg-market-value-survey-2024-chapter-1")
    chapter_4 = _ods_cells("mhclg-market-value-survey-2024-chapter-4")
    ported = {
        (record.spec.selector.sheet_name, record.spec.selector.address)
        for record in _records("mhclg-market-value-survey-2024-chapter-4")
    }
    compared = 0
    for sheet, row, other_sheet, other_row, columns in CHAPTER_4_RESTATES:
        for column, other_column in columns:
            assert (sheet, f"{column}{row}") not in ported
            mine = _cell(chapter_4, sheet, column, row)
            theirs = _cell(chapter_1, other_sheet, other_column, other_row)
            if (sheet, row, column) in TRANSPOSED:
                mine, theirs = int(mine), int(theirs)
                assert mine != theirs
                assert sorted(str(mine)) == sorted(str(theirs))
            elif isinstance(theirs, (int, float)):
                assert mine == pytest.approx(theirs, rel=1e-6), (sheet, row, column)
                compared += 1
    assert compared


def test_no_semantic_key_repeats_across_these_packages():
    packages = [*PACKAGES, "mhclg-ehs-weekly-housing-costs-2023-24"]
    keys = Counter()
    for package_id in packages:
        package = load_source_package(package_id)
        keys.update(
            build_semantic_fact_key(fact)
            for fact in package.build_facts(package.artifact.artifact_year)
        )
    assert max(keys.values()) == 1


def test_the_new_concepts_belong_to_these_packages_only():
    concepts = set()
    for package_id in PACKAGES:
        for fact in _facts(package_id):
            concepts.add(fact.measure.concept)
    existing = {
        "ons.nbs_land_value_total",
        "ons.nbs_land_value_households",
        "ons.nbs_land_value_nfc",
    }
    new = concepts - existing
    assert new
    ours = {
        ROOT / "packages" / SOURCE_PACKAGE_ALIASES[package_id]
        for package_id in PACKAGES
    }
    for path in sorted((ROOT / "packages").glob("*/*/source_package.yaml")):
        if path.parent in ours:
            continue
        text = path.read_text(encoding="utf-8")
        assert not any(f"concept: {concept}\n" in text for concept in new), path
