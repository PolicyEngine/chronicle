"""Item 4 of PolicyEngine/chronicle#408: council tax collected by billing authority.

MHCLG's Tables 6a and 9a for England, and the per-authority rows of the pinned Welsh
collection workbooks and of SLGFS 2024-25.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
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
BLOCK_MARKER = "# Record sets below: scripts/build_uk_408_packages.py (PolicyEngine/chronicle#408).\n"
TABLE_5 = "mhclg-council-tax-collection-england-2025-26"
TABLE_6A = "mhclg-council-tax-collection-by-authority-2025-26"
TABLE_9A = "mhclg-council-tax-qrc4-2025-26"
# package id -> (artifact year, record sets, facts)
NEW_PACKAGES = {
    TABLE_6A: (2026, 4, 1208),
    TABLE_9A: (2026, 10, 5757),
}
EXTENDED_PACKAGES = {
    "welshgov-council-tax-collection-2024-25": (2025, 2, 161),
    "welshgov-council-tax-collection-2025-26": (2026, 2, 161),
    "scotgov-slgfs-council-tax-2024-25": (2026, 16, 167),
}
SHA256 = {
    TABLE_6A: (
        "0822434ac17b5699bb6ecc09e59f737f62fa11feb1e120935c7390b0dc4a4b85",
        104767,
    ),
    TABLE_9A: (
        "3937351a67bd12418301f97f504a5357566ecf3b6d375076119f1addb44d3d90",
        216962,
    ),
}
ENGLAND = "E92000001"
CLASSES = (
    "london_boroughs",
    "inner_london_boroughs",
    "outer_london_boroughs",
    "metropolitan_districts",
    "unitary_authorities",
    "shire_districts",
)
# Table 6a's ported columns by (measure, fiscal year).
TABLE_6A_COLUMNS = {
    ("net_collectable_debit", 2024): "F",
    ("amount_collected_in_year", 2024): "G",
    ("net_collectable_debit", 2025): "I",
    ("amount_collected_in_year", 2025): "J",
}
# Table 9a: ported QRC4 lines by column (lines 9 to 12 by quarter). Line 1 (F)
# restates Table 6a's 2025-26 column; the other columns left out are the lines the
# QRC4 form defines as arithmetic over other lines.
QRC4_PORTED = {
    "G": "prepayments_received_in_previous_years",
    "H": "in_year_receipts_net_of_refunds",
    "K": "receipts_of_previous_years_taxes",
    "L": "receipts_of_following_year_taxes",
    "R": "arrears_brought_forward",
    "S": "net_adjustments_to_arrears",
    "U": "arrears_collected_relating_to_earlier_years",
    "V": "arrears_collected_relating_to_previous_year",
    "W": "arrears_written_off_relating_to_earlier_years",
    "X": "arrears_written_off_relating_to_previous_year",
    "Z": "arrears_outstanding_relating_to_earlier_years",
    "AA": "arrears_outstanding_relating_to_previous_year",
    "AB": "amount_uncollected_in_year",
    "AC": "in_year_written_off",
    "AF": "court_and_administration_costs_in_arrears",
}
QRC4_QUARTERS = {"N": "2025-Q2", "O": "2025-Q3", "P": "2025-Q4", "Q": "2026-Q1"}
DEBIT = "mhclg.council_tax.net_collectable_debit"
COLLECTED = "mhclg.council_tax.amount_collected_in_year"


def _year(package_id: str) -> int:
    return {**NEW_PACKAGES, **EXTENDED_PACKAGES, TABLE_5: (2026,)}[package_id][0]


def _facts(package_id: str) -> list:
    return load_source_package(package_id).build_facts(_year(package_id))


def _index(package_id: str) -> dict[tuple, float]:
    """Facts by (concept, period value, geography id, authority class filter)."""
    found = {}
    for fact in _facts(package_id):
        key = (
            fact.measure.concept,
            fact.period.value,
            fact.geography.id,
            fact.filters.get("billing_authority_class"),
        )
        assert key not in found, key
        found[key] = fact.value
    return found


def _column(index: int) -> str:
    letters = ""
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _ods_table(directory: str, sheet: str, header: int) -> pd.DataFrame:
    """A worksheet read by pandas, with spreadsheet column letters as column names."""
    manifest = yaml.safe_load((DATA / directory / "manifest.yaml").read_text())
    (entry,) = manifest["files"].values()
    frame = pd.read_excel(
        DATA / directory / entry["filename"],
        engine="odf",
        sheet_name=sheet,
        header=header,
    )
    frame.columns = [_column(number) for number in range(1, len(frame.columns) + 1)]
    return frame


def _table_6a() -> pd.DataFrame:
    return _ods_table(
        "mhclg/council_tax_collection_by_authority_2025_26", "Table_6a_-_council_tax", 2
    )


def _table_9a() -> pd.DataFrame:
    return _ods_table("mhclg/council_tax_qrc4_2025_26", "Table_9a_-_Council_Tax", 3)


def _row_key(row) -> tuple[str, str | None]:
    """(geography id, class filter) of a Table 6a or 9a row."""
    if row["B"] == "E-ENG":
        return ENGLAND, None
    if row["C"] == "[z]":
        return ENGLAND, row["A"].removeprefix("of which: ").lower().replace(" ", "_")
    return row["C"], None


@pytest.mark.parametrize("package_id", sorted(NEW_PACKAGES))
def test_new_packages_validate_register_and_carry_no_anchors(package_id):
    year, record_sets, count = NEW_PACKAGES[package_id]
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
    assert max(Counter(build_semantic_fact_key(fact) for fact in built).values()) == 1


@pytest.mark.parametrize("package_id", sorted(EXTENDED_PACKAGES))
def test_extended_packages_validate_with_their_authority_rows(package_id):
    year, record_sets, count = EXTENDED_PACKAGES[package_id]
    package_dir = ROOT / "packages" / SOURCE_PACKAGE_ALIASES[package_id]
    report = validate_source_package(package_dir, year=year)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["record_set_count"] == record_sets
    text = (package_dir / "source_package.yaml").read_text(encoding="utf-8")
    (prefix, block) = text.split(BLOCK_MARKER)
    assert prefix.endswith("\n") and block.startswith("- record_set_id: ")
    assert "wave-3" not in prefix
    assert not any(
        isinstance(token, (yaml.AnchorToken, yaml.AliasToken))
        for token in yaml.scan(block)
    )
    built = _facts(package_id)
    assert len(built) == count
    assert validate_facts(built).valid
    assert max(Counter(build_semantic_fact_key(fact) for fact in built).values()) == 1


def test_no_fact_is_carried_by_two_packages():
    """Rows one table restates from another are asserted equal, not ported twice."""
    owners = defaultdict(set)
    for package_id in (*NEW_PACKAGES, *EXTENDED_PACKAGES, TABLE_5):
        for fact in _facts(package_id):
            owners[build_semantic_fact_key(fact)].add(package_id)
    assert max(len(found) for found in owners.values()) == 1


@pytest.mark.parametrize("package_id", sorted({**NEW_PACKAGES, **EXTENDED_PACKAGES}))
def test_facts_meet_the_consumer_contract(package_id):
    assert validate_consumer_fact_contract(_facts(package_id)).valid


@pytest.mark.parametrize("package_id", sorted(NEW_PACKAGES))
def test_manifests_pin_bytes_and_licence(package_id):
    data_dir = DATA / SOURCE_PACKAGE_ALIASES[package_id]
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["package_id"] == package_id
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-04"
    (entry,) = manifest["files"].values()
    content = (data_dir / entry["filename"]).read_bytes()
    assert (hashlib.sha256(content).hexdigest(), len(content)) == SHA256[package_id]
    assert (entry["sha256"], entry["size_bytes"]) == SHA256[package_id]


@pytest.mark.parametrize("package_id", sorted(NEW_PACKAGES))
def test_new_artifacts_are_in_r2(package_id):
    data_dir = DATA / SOURCE_PACKAGE_ALIASES[package_id]
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text(encoding="utf-8"))
    (entry,) = manifest["files"].values()
    assert entry["storage"]["r2"]["uri"].endswith(
        f"/{package_id}/2026/{entry['sha256']}/{entry['filename']}"
    )


def test_table_6a_facts_are_the_cells():
    facts = _index(TABLE_6A)
    expected = {}
    for _, row in _table_6a().iterrows():
        geography, kind = _row_key(row)
        if (geography, kind) == (ENGLAND, None):
            continue  # Table 5's England figures; see the next test
        for (measure, year), column in TABLE_6A_COLUMNS.items():
            key = (f"mhclg.council_tax.{measure}", year, geography, kind)
            expected[key] = row[column] * 1000
    assert facts == pytest.approx(expected)
    # 296 billing authorities and the six classes; the rate columns H and K are not
    # ported.
    geographies = {key[2] for key in facts if key[2] != ENGLAND}
    assert len(geographies) == 296
    assert {key[3] for key in facts} == {None, *CLASSES}
    assert {"E08000016", "E08000019"} <= geographies


def test_table_6a_england_row_restates_table_5():
    """chronicle#408: Table 6a's England row equals the pinned Table 5, so it is not
    ported again."""
    table = _table_6a()
    (england,) = [row for _, row in table.iterrows() if row["B"] == "E-ENG"]
    assert (england["F"], england["I"]) == (42_014_522, 44_981_384)
    table_5 = {
        (fact.measure.concept, fact.period.value): fact.value
        for fact in _facts(TABLE_5)
        if fact.geography.id == ENGLAND
    }
    for (measure, year), column in TABLE_6A_COLUMNS.items():
        concept = f"mhclg.council_tax.{measure}"
        assert england[column] * 1000 == pytest.approx(table_5[(concept, year)])
    facts = _index(TABLE_6A)
    assert not [key for key in facts if key[2:] == (ENGLAND, None)]


def test_table_9a_facts_are_the_cells():
    facts = _index(TABLE_9A)
    expected = {}
    for _, row in _table_9a().iterrows():
        geography, kind = _row_key(row)
        for column, measure in QRC4_PORTED.items():
            expected[(f"mhclg.council_tax.{measure}", 2025, geography, kind)] = (
                row[column] * 1000
            )
        for column, quarter in QRC4_QUARTERS.items():
            key = (
                "mhclg.council_tax.receipts_collected_in_quarter",
                quarter,
                geography,
                kind,
            )
            expected[key] = row[column] * 1000
    assert facts == pytest.approx(expected)
    geographies = {key[2] for key in facts if key[2] != ENGLAND}
    assert len(geographies) == 296
    assert {"E08000038", "E08000039"} <= geographies
    assert not {"E08000016", "E08000019"} & geographies
    assert not [key for key in facts if key[0] == DEBIT]


def test_table_9a_line_1_restates_table_6a_2025_26_for_every_row():
    """chronicle#408: QRC4 line 1 equals Table 6a's 2025-26 net collectable debit (and
    line 4 its amount collected) row by row, so line 1 is not ported again."""
    table_6a = {row["A"]: row for _, row in _table_6a().iterrows()}
    table_9a = _table_9a()
    assert set(table_9a["A"]) == set(table_6a)
    facts = _index(TABLE_6A)
    for _, row in table_9a.iterrows():
        restated = table_6a[row["A"]]
        assert (row["F"], row["I"]) == (restated["I"], restated["J"])
        geography, kind = _row_key(restated)
        if (geography, kind) != (ENGLAND, None):
            assert facts[(DEBIT, 2025, geography, kind)] == row["F"] * 1000
    (england,) = [row for _, row in table_9a.iterrows() if row["B"] == "E-ENG"]
    assert england["F"] == 44_981_384


def test_qrc4_lines_left_out_are_the_forms_arithmetic_over_ported_lines():
    table = _table_9a()
    for _, row in table.iterrows():
        assert row["I"] == row["G"] + row["H"]  # 4 = 2 + 3
        assert row["J"] == pytest.approx(100 * row["I"] / row["F"], abs=1e-5)  # 5
        assert row["M"] == row["H"] + row["K"] + row["L"]  # 8 = 3 + 6 + 7
        assert row["M"] == row["N"] + row["O"] + row["P"] + row["Q"]  # and 9 to 12
        assert row["T"] == row["R"] + row["S"]  # 15 = 13 + 14
        assert row["Y"] == row["T"] - row["U"] - row["V"] - row["W"] - row["X"]  # 20
        assert row["Y"] == row["Z"] + row["AA"]  # 20 = 20a + 20b
        assert row["AD"] == row["AB"] - row["AC"]  # 23 = 21 - 22
        assert row["AE"] == row["Y"] + row["AD"]  # 24 = 20 + 23
    # Line 21 adds costs the return does not print, so it is ported.
    assert (table["AB"] != table["F"] - table["I"]).sum() > 0


def _england_totals(package_id: str) -> dict[tuple, float]:
    """England's figure for each (concept, period) a table's authorities carry."""
    if package_id == TABLE_6A:
        return {
            (fact.measure.concept, fact.period.value): fact.value
            for fact in _facts(TABLE_5)
            if fact.period.value in {2024, 2025}
        }
    return {
        (concept, period): value
        for (concept, period, geography, kind), value in _index(package_id).items()
        if geography == ENGLAND and kind is None
    }


@pytest.mark.parametrize("package_id", [TABLE_6A, TABLE_9A])
def test_authorities_and_classes_add_up_to_england(package_id):
    totals = defaultdict(float)
    classes = defaultdict(dict)
    for (concept, period, geography, kind), value in _index(package_id).items():
        if geography != ENGLAND:
            totals[(concept, period)] += value
        elif kind is not None:
            classes[(concept, period)][kind] = value
    england = _england_totals(package_id)
    assert set(totals) == set(england) == set(classes)
    for key, value in england.items():
        assert totals[key] == pytest.approx(value, abs=1e-6)
        found = classes[key]
        assert found["london_boroughs"] == pytest.approx(
            found["inner_london_boroughs"] + found["outer_london_boroughs"]
        )
        assert value == pytest.approx(
            found["london_boroughs"]
            + found["metropolitan_districts"]
            + found["unitary_authorities"]
            + found["shire_districts"]
        )


@pytest.mark.parametrize(
    ("package_id", "total_id", "count"),
    [
        ("welshgov-council-tax-collection-2024-25", "W92000004", 22),
        ("welshgov-council-tax-collection-2025-26", "W92000004", 22),
        ("scotgov-slgfs-council-tax-2024-25", "S92000003", 32),
    ],
)
def test_authorities_sum_to_the_nation(package_id, total_id, count):
    sums, authorities, nation = defaultdict(float), defaultdict(set), {}
    for fact in _facts(package_id):
        key = (
            fact.measure.concept,
            fact.period.value,
            tuple(sorted(fact.filters.items())),
        )
        if fact.geography.level == "local_authority":
            sums[key] += fact.value
            authorities[key].add(fact.geography.id)
        elif fact.geography.id == total_id:
            nation[key] = fact.value
    assert sums
    for key, value in sums.items():
        assert len(authorities[key]) == count
        assert value == pytest.approx(nation[key], abs=1e-3)


def test_welsh_and_scottish_authority_rows_are_the_cells():
    for package_id, directory, sheet, first, last in (
        (
            "welshgov-council-tax-collection-2024-25",
            "welshgov/council_tax_collection_2024_25",
            "Table2",
            5,
            26,
        ),
        (
            "welshgov-council-tax-collection-2025-26",
            "welshgov/council_tax_collection_2025_26",
            "Table2",
            5,
            26,
        ),
        (
            "scotgov-slgfs-council-tax-2024-25",
            "scotgov/slgfs_council_tax_2024_25",
            "Table 2.8",
            7,
            38,
        ),
        (
            "scotgov-slgfs-council-tax-2024-25",
            "scotgov/slgfs_council_tax_2024_25",
            "Table 2.11",
            7,
            38,
        ),
    ):
        manifest = yaml.safe_load((DATA / directory / "manifest.yaml").read_text())
        (entry,) = manifest["files"].values()
        workbook = load_workbook(DATA / directory / entry["filename"], data_only=True)
        cells = workbook[sheet]
        specs = {
            record_set["record_set_id"]: record_set
            for record_set in yaml.safe_load(
                (
                    ROOT
                    / "packages"
                    / SOURCE_PACKAGE_ALIASES[package_id]
                    / "source_package.yaml"
                ).read_text()
            )["record_sets"]
        }
        checked = 0
        for fact in _facts(package_id):
            if fact.geography.level != "local_authority":
                continue
            record_set = specs[fact.source_record_id.rsplit(".", 2)[0]]
            if record_set["sheet_name"] != sheet:
                continue
            (row,) = [
                spec
                for spec in record_set["rows"]
                if spec["geography_id"] == fact.geography.id
            ]
            (measure,) = [
                spec
                for spec in record_set["measures"]
                if spec["concept"] == fact.measure.concept
            ]
            assert first <= row["row_number"] <= last
            cell = cells[f"{measure['column']}{row['row_number']}"].value
            assert fact.value == pytest.approx(cell * 1000)
            checked += 1
        columns = {"Table2": 7, "Table 2.8": 1, "Table 2.11": 2}[sheet]
        assert checked == (last - first + 1) * columns
