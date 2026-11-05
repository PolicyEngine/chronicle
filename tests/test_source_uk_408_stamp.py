"""HMRC stamp tax facts for PolicyEngine/chronicle#408 item 5.

HMRC Annual Stamp Tax Statistics 2024 to 2025 (the corrected tables of 11 March 2026):
Tables 7, 3a, 5a, 9a and 9d for 2023-24 and 2024-25, and the quarterly Table 2e, added
to hmrc-stamp-tax-statistics-2024-25 beside chronicle#357's Tables 6b, 8a and 8b. Every
new fact is checked against the workbook read independently (pandas' ODF reader), and
each of the issue's parity checks is asserted.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import runpy

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
PACKAGE_ID = "hmrc-stamp-tax-statistics-2024-25"
PACKAGE_DIR = ROOT / "packages/hmrc/stamp_tax_statistics_2024_25"
ODS = (
    ROOT
    / "db/data/hmrc/stamp_tax_statistics_2024_25/Annual_Stamps_2024_25_correction.ods"
)
SCOPE = "hmrc:england_and_northern_ireland"
# (table, financial year's opening year, or "quarters") -> facts
NEW_FACTS = {
    ("table_7", 2024): 105,
    ("table_7", 2023): 98,
    ("table_3a", 2024): 102,
    ("table_3a", 2023): 102,
    ("table_5a", 2024): 207,
    ("table_5a", 2023): 216,
    ("table_9a", 2024): 60,
    ("table_9a", 2023): 60,
    ("table_9d", 2024): 40,
    ("table_9d", 2023): 37,
    ("table_2e", "quarters"): 108,
}
CHRONICLE_357_FACTS = 352


@pytest.fixture(scope="module")
def facts():
    return load_source_package(PACKAGE_ID).build_facts(2025)


@pytest.fixture(scope="module")
def new_facts(facts):
    return [f for f in facts if (_table(f), _year(f)) in NEW_FACTS]


@pytest.fixture(scope="module")
def workbook():
    return pd.read_excel(ODS, engine="odf", sheet_name=None, header=None)


@pytest.fixture(scope="module")
def package():
    return yaml.safe_load(
        (PACKAGE_DIR / "source_package.yaml").read_text(encoding="utf-8")
    )


def _table(fact) -> str:
    return fact.layout.record_set_id.split(".")[2]


def _year(fact) -> int | str:
    return fact.period.value if fact.period.type == "fiscal_year" else "quarters"


def _sheet(fact) -> str:
    table = _table(fact).removeprefix("table_")
    if table == "2e":
        return "Table_2e"
    year = fact.period.value
    return f"Table_{table}_({year}-{(year + 1) % 100:02d})"


def _cell(workbook, sheet: str, row: int, column: str):
    """The workbook's cell, with numbers stored as text read as numbers."""
    index = 0
    for letter in column:
        index = index * 26 + ord(letter) - 64
    value = workbook[sheet].iat[row - 1, index - 1]
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value)
    return value


def _fact(facts, table, year, measure_id, geography=SCOPE, **filters):
    """The one fact with exactly these filters (residential unless told otherwise)."""
    filters.setdefault("sdlt_property_type", "residential")
    filters = {key: value for key, value in filters.items() if value is not None}
    matches = [
        f
        for f in facts
        if _table(f) == table
        and _year(f) == year
        and f.layout.measure_id == measure_id
        and f.geography.id == geography
        and {k: v for k, v in f.filters.items() if k != "sdlt_corporate_flat_rate"}
        == filters
    ]
    assert len(matches) == 1, (
        table,
        year,
        measure_id,
        geography,
        filters,
        len(matches),
    )
    return matches[0]


def test_package_validates_registers_and_carries_no_anchors(facts):
    report = validate_source_package(PACKAGE_DIR, year=2025)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["record_set_count"] == 72
    assert PACKAGE_ID in SOURCE_PACKAGE_ALIASES
    assert PACKAGE_ID in UK_BUNDLE_SOURCES
    text = (PACKAGE_DIR / "source_package.yaml").read_text(encoding="utf-8")
    assert not any(
        isinstance(token, (yaml.AnchorToken, yaml.AliasToken))
        for token in yaml.scan(text)
    )
    assert len(facts) == CHRONICLE_357_FACTS + sum(NEW_FACTS.values())
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    assert max(Counter(build_semantic_fact_key(f) for f in facts).values()) == 1


def test_new_tables_add_the_pinned_facts(new_facts):
    assert Counter((_table(f), _year(f)) for f in new_facts) == NEW_FACTS


def test_generator_reproduces_the_committed_package(tmp_path):
    generator = runpy.run_path(str(ROOT / "scripts/build_uk_1095_port_packages.py"))
    build = generator["build_stamps"]
    build.__globals__["STAMPS_PACKAGE"] = tmp_path
    build()
    assert (tmp_path / "source_package.yaml").read_text(encoding="utf-8") == (
        PACKAGE_DIR / "source_package.yaml"
    ).read_text(encoding="utf-8")


def test_every_new_fact_is_its_workbook_cell(new_facts, workbook, package):
    rows, columns = {}, {}
    for record_set in package["record_sets"]:
        for row in record_set["rows"]:
            rows[(record_set["record_set_id"], row["value_id"])] = row["row_number"]
        for measure in record_set["measures"]:
            columns[(record_set["record_set_id"], measure["measure_id"])] = (
                measure["column"],
                measure.get("value_scale", 1),
            )
    for fact in new_facts:
        record_set_id = fact.layout.record_set_id
        row = rows[(record_set_id, fact.layout.source_row_id)]
        column, scale = columns[(record_set_id, fact.layout.measure_id)]
        printed = _cell(workbook, _sheet(fact), row, column)
        assert isinstance(printed, (int, float)), (fact.source_record_id, printed)
        assert fact.value == pytest.approx(printed * scale, rel=1e-12), (
            fact.source_record_id,
            printed,
        )


def test_restating_and_percentage_columns_are_not_ported(new_facts, package):
    headers = {
        (record_set["record_set_id"], measure["measure_id"]): str(
            measure["expected_column_header"]
        )
        for record_set in package["record_sets"]
        for measure in record_set["measures"]
    }
    ported = {headers[(f.layout.record_set_id, f.layout.measure_id)] for f in new_facts}
    assert not [header for header in ported if "%" in header or "percentage" in header]
    # Table 7's and 9d's 'All ages' restate 8a's individuals and 9a's claims; Table
    # 5a's 'All price bands' restates 3a's residential columns.
    assert not [
        header
        for header in ported
        if header.startswith(("All ages", "All price bands"))
    ]
    # Table 3a's All countries row is ported only for all property types: its
    # residential and non-residential cells restate Tables 8a and 8b.
    assert {
        f.filters.get("sdlt_property_type")
        for f in new_facts
        if _table(f) == "table_3a" and f.geography.id == SCOPE
    } == {None}


def test_parity_3a_receipts_are_8a_and_8b_receipts(facts, workbook):
    # 2024-25: residential GBP 10,380m and non-residential GBP 3,505m.
    sheet = "Table_3a_(2024-25)"
    assert _cell(workbook, sheet, 7, "E") == 10_380
    assert _cell(workbook, sheet, 7, "H") == 3_505
    assert _fact(facts, "table_8a", 2024, "receipts").value == 10_380e6
    assert (
        _fact(
            facts, "table_8b", 2024, "receipts", sdlt_property_type="non_residential"
        ).value
        == 3_505e6
    )
    total = _fact(facts, "table_3a", 2024, "receipts", sdlt_property_type=None)
    assert total.value == 13_885e6 == 10_380e6 + 3_505e6
    # England and Northern Ireland make up 'All countries' (to the rounding).
    for measure_id, tolerance in (
        ("transactions", 100),
        ("property_value", 10e6),
        ("receipts", 10e6),
    ):
        parts = sum(
            _fact(
                facts, "table_3a", 2024, measure_id, area, sdlt_property_type=None
            ).value
            for area in ("E92000001", "N92000002")
        )
        whole = _fact(
            facts, "table_3a", 2024, measure_id, sdlt_property_type=None
        ).value
        assert abs(whole - parts) <= tolerance, (measure_id, whole, parts)


def test_parity_5a_all_bands_receipts_are_3a_residential_receipts(facts, workbook):
    sheet = "Table_5a_(2024-25)"
    assert _cell(workbook, sheet, 9, "W") == _cell(
        workbook, "Table_3a_(2024-25)", 7, "E"
    )
    england = _fact(facts, "table_3a", 2024, "receipts", "E92000001")
    assert england.value == _cell(workbook, sheet, 10, "W") * 1e6
    # Each area's ported bands add up to its 'All price bands' receipts, to rounding.
    for area_row in range(9, 21):
        bands = [_cell(workbook, sheet, area_row, column) for column in "EHKNQT"]
        printed = sum(value for value in bands if isinstance(value, (int, float)))
        assert abs(printed - _cell(workbook, sheet, area_row, "W")) <= 20, area_row


def test_parity_table_7_is_8a_individuals_within_rounding(facts, workbook):
    assert _cell(workbook, "Table_7_(2024-25)", 9, "Q") == 925_140
    individuals = _fact(
        facts, "table_8a", 2024, "transactions", sdlt_buyer_type="individuals"
    )
    assert individuals.value == 925_100
    ages = [
        f
        for f in facts
        if _table(f) == "table_7"
        and f.period.value == 2024
        and "sdlt_price_band" not in f.filters
    ]
    assert len(ages) == 15
    assert sum(f.value for f in ages) == 925_140
    assert abs(925_140 - individuals.value) <= 50


def test_parity_ftbr_claims_9a_9d_and_2e(facts, workbook):
    claims = _fact(facts, "table_9a", 2024, "ftbr_claims")
    assert claims.value == 155_400
    assert _cell(workbook, "Table_9d_(2024-25)", 10, "Q") == 155_400
    # 9d's ported age bands for all claims; 'Over 79' is [X], under 50.
    by_age = [
        f
        for f in facts
        if _table(f) == "table_9d"
        and f.period.value == 2024
        and "sdlt_ftbr_liability" not in f.filters
    ]
    assert len(by_age) == 14
    assert abs(sum(f.value for f in by_age) - 155_400) <= 14 * 50 + 50
    quarters = [
        f
        for f in facts
        if _table(f) == "table_2e"
        and f.layout.measure_id == "ftbr_claims"
        and f.period.value in {"2024-Q2", "2024-Q3", "2024-Q4", "2025-Q1"}
    ]
    assert len(quarters) == 4
    assert sum(f.value for f in quarters) == pytest.approx(155_368.45, abs=0.01)
    assert abs(sum(f.value for f in quarters) - 155_400) <= 50


def test_table_5a_is_2024_25_despite_its_title(facts, workbook):
    sheet = "Table_5a_(2024-25)"
    assert str(_cell(workbook, sheet, 1, "A")).startswith("Table 5a 2023-24:")
    assert str(_cell(workbook, sheet, 3, "A")).endswith("region for 2024-25.")
    contents = workbook["Contents"]
    (entry,) = contents.loc[contents[0] == "Table_5a_(2024-25)", 1]
    assert entry.startswith("2023-24:")
    # Its totals are Table 8a's 2024-25 totals.
    assert [_cell(workbook, sheet, 9, c) for c in "UVW"] == [
        _cell(workbook, "Table_8a_(2024-25)", 8, c) for c in "HIJ"
    ]
    stamped = {
        f.period.value
        for f in facts
        if _table(f) == "table_5a"
        and f.layout.record_set_id.endswith(("fy2024", "fy2024.subset_1"))
    }
    assert stamped == {2024}
    assert all(
        "2024-25" in f.measure.concept_evidence_notes
        for f in facts
        if _table(f) == "table_5a" and f.period.value == 2024
    )


def test_table_5a_bands_include_the_corporate_flat_rate(facts):
    """Above GBP 500,000 the all-countries bands exceed Table 8a's by 8a's corporate
    flat-rate row, which 8a keeps out of its bands: by exactly its GBP 405m of
    property value in 2024-25."""
    excess = sum(
        _fact(facts, "table_5a", 2024, "property_value", sdlt_price_band=band).value
        - _fact(facts, "table_8a", 2024, "property_value", sdlt_price_band=band).value
        for band in (
            "gbp_500k_to_1m",
            "gbp_1m_to_1_5m",
            "gbp_1_5m_to_2m",
            "over_gbp_2m",
        )
    )
    corporate = _fact(
        facts,
        "table_8a",
        2024,
        "property_value",
        sdlt_price_band="corporate_bodies_flat_rate",
    )
    assert excess == corporate.value == 405e6
    assert {
        f.filters["sdlt_corporate_flat_rate"] for f in facts if _table(f) == "table_5a"
    } == {"included_in_price_bands"}


def test_table_7_stores_2024_25_counts_as_printed(facts, workbook):
    assert _cell(workbook, "Table_7_(2024-25)", 5, "A").startswith(
        "Transactions are rounded to the nearest 100."
    )
    youngest_top_band = _fact(
        facts,
        "table_7",
        2024,
        "transactions_age_0_to_19",
        sdlt_buyer_type="individuals",
        sdlt_price_band="over_gbp_2m",
        sdlt_purchaser_age_band="age_0_to_19",
    )
    assert youngest_top_band.value == _cell(workbook, "Table_7_(2024-25)", 15, "B") == 5
    # 2023-24 rounds to the nearest 100 and marks small cells [X], which emit no fact.
    assert _cell(workbook, "Table_7_(2023-24)", 13, "B") == "[X]"
    assert not [
        f
        for f in facts
        if _table(f) == "table_7"
        and f.period.value == 2023
        and f.filters.get("sdlt_price_band") == "gbp_1m_to_1_5m"
        and f.filters.get("sdlt_purchaser_age_band") == "age_0_to_19"
    ]


def test_table_2e_quarters_coverage_and_thresholds(facts):
    table_2e = [f for f in facts if _table(f) == "table_2e"]
    quarters = sorted({f.period.value for f in table_2e})
    assert (quarters[0], quarters[-1], len(quarters)) == ("2017-Q4", "2025-Q1", 27)
    assert not {"2020-Q4", "2021-Q1", "2021-Q2"} & set(quarters)
    before_ltt = {f.geography.id for f in table_2e if f.period.value < "2018-Q2"}
    assert before_ltt == {"hmrc:england_wales_and_northern_ireland"}
    assert {f.geography.id for f in table_2e if f.period.value >= "2018-Q2"} == {SCOPE}
    claims = {
        f.period.value: f for f in table_2e if f.layout.measure_id == "ftbr_claims"
    }
    assert claims["2024-Q2"].value == pytest.approx(31_146.2618121061)
    assert claims["2024-Q1"].value == 25_100
    notes = {
        quarter: fact.measure.concept_evidence_notes for quarter, fact in claims.items()
    }
    assert "£300,000 and maximum price £500,000, in force" in notes["2019-Q1"]
    assert "from 23 September 2022" in notes["2022-Q3"]
    assert "£425,000 and maximum price £625,000" in notes["2024-Q4"]


def test_ftbr_liability_splits_the_claims(facts):
    for year in (2023, 2024):
        claims = _fact(facts, "table_9a", year, "ftbr_claims").value
        exempt = _fact(
            facts, "table_9a", year, "ftbr_claims_exempt", sdlt_ftbr_liability="exempt"
        ).value
        liable = _fact(
            facts, "table_9a", year, "ftbr_claims_liable", sdlt_ftbr_liability="liable"
        ).value
        assert abs(exempt + liable - claims) <= 100
        notes = _fact(facts, "table_9a", year, "ftbr_claims").measure
        assert "from 23 September 2022 to 31 March 2025" in notes.concept_evidence_notes
    assert {
        f.measure.concept
        for f in facts
        if _table(f) in {"table_9a", "table_9d", "table_2e"}
    } == {
        "hmrc.sdlt.ftbr_amount_relieved",
        "hmrc.sdlt.ftbr_claims",
        "hmrc.sdlt.ftbr_average_amount_relieved",
    }


def test_every_fact_keeps_the_gbp_40000_universe(facts):
    for fact in facts:
        threshold = [
            c for c in fact.constraints if c.variable == "sdlt_chargeable_consideration"
        ]
        assert len(threshold) == 1 and threshold[0].value == 40000
