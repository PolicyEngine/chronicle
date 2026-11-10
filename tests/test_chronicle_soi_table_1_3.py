"""IRS SOI Publication 1304 Table 1.3: returns, AGI and the child credit by filing status."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from chronicle.consumer_contract import validate_consumer_fact_contract
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources.cells import build_source_cell_key, validate_source_cells
from chronicle.sources.rows import validate_source_rows
from chronicle.yaml_io import safe_load as safe_load_yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "soi-table-1-3"
SHA256 = "aa9a706537a533f69c9a30c5837e99f5fdaeb5b45f5781740062a233c6b1d315"
STATUSES = (
    "all",
    "married_filing_jointly_surviving_spouse",
    "married_filing_separately",
    "head_of_household",
    "single",
)
#: TY2023 cells as published in 23in13ms.xls (rows 8 and 70, columns B to K);
#: dollar amounts are the table's thousands.
PUBLISHED = {
    ("filing_status_returns", "return_count"): (
        (160_602_107, 54_568_939, 4_139_858, 21_604_491, 80_288_820),
        "B",
        8,
    ),
    ("filing_status_agi", "adjusted_gross_income"): (
        (15_286_017_359, 9_542_425_944, 366_797_808, 1_156_241_023, 4_220_552_585),
        "C",
        8,
    ),
    ("filing_status_ctc_returns", "ctc_claims"): (
        (38_949_527, 21_526_250, 739_342, 14_827_347, 1_856_588),
        "B",
        70,
    ),
    ("filing_status_ctc_amount", "ctc_amount"): (
        (84_418_366, 58_813_439, 1_527_331, 22_060_826, 2_016_769),
        "C",
        70,
    ),
}
COLUMN_OFFSETS = {status: 2 * index for index, status in enumerate(STATUSES)}
#: Row 3 heads each filing status's pair of columns; row 5 heads each column.
STATUS_HEADERS = {
    "all": "All\nreturns",
    "married_filing_jointly_surviving_spouse": (
        "Returns of married persons filing jointly\nand returns of surviving spouses"
    ),
    "married_filing_separately": "Returns of married\npersons filing separately",
    "head_of_household": "Returns of heads\nof households",
    "single": "Returns of\nsingle persons",
}
MEASURE_HEADERS = {
    "return_count": "Number of\nreturns",
    "adjusted_gross_income": "Amount",
    "ctc_claims": "Number of\nreturns",
    "ctc_amount": "Amount",
}


def _record_id(record_set: str, status: str, measure: str) -> str:
    return f"irs_soi.ty2023.table_1_3.{record_set}.{status}.{measure}"


def _column(first: str, status: str) -> str:
    return chr(ord(first) + COLUMN_OFFSETS[status])


@pytest.fixture(scope="module")
def built():
    package = load_source_package(PACKAGE_ID)
    rows = package.build_source_rows(2023)
    cells = package.build_source_cells(2023, source_rows=rows)
    facts = package.build_facts(2023, source_rows=rows, cells=cells)
    return package, rows, cells, facts


def test_alias_and_pinned_publisher_bytes():
    assert SOURCE_PACKAGE_ALIASES[PACKAGE_ID] == Path("irs_soi/table_1_3")
    data_dir = ROOT / "db/data/irs_soi/table_1_3"
    manifest = safe_load_yaml((data_dir / "manifest.yaml").read_text())
    assert manifest["package_id"] == PACKAGE_ID
    artifact = manifest["files"][2023]
    content = (data_dir / artifact["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == artifact["sha256"] == SHA256
    assert len(content) == artifact["size_bytes"]
    assert artifact["source_url"] == "https://www.irs.gov/pub/irs-soi/23in13ms.xls"
    assert artifact["storage"]["r2"]["key"] == (
        f"raw/irs_soi/{PACKAGE_ID}/2023/{SHA256}/23in13ms.xls"
    )


def test_package_validates_and_counts_its_records():
    report = validate_source_package(PACKAGE_ID, year=2023)
    assert report.valid, report.errors
    assert report.counts == {
        "measure_count": 4,
        "record_set_count": 4,
        "row_count": 20,
        "source_record_count": 20,
        "source_region_count": 4,
    }


def test_every_fact_is_the_published_cell_for_its_filing_status(built):
    _package, rows, cells, facts = built
    assert validate_source_rows(rows).valid
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    contract = validate_consumer_fact_contract(facts)
    assert contract.valid, contract.errors
    by_id = {fact.source_record_id: fact for fact in facts}
    cells_by_key = {build_source_cell_key(cell): cell for cell in cells}
    expected_ids = set()
    for (record_set, measure), (values, first_column, row) in PUBLISHED.items():
        for status, value in zip(STATUSES, values, strict=True):
            record_id = _record_id(record_set, status, measure)
            expected_ids.add(record_id)
            fact = by_id[record_id]
            scale = 1_000 if fact.measure.unit == "usd" else 1
            assert fact.value == value * scale
            assert fact.filters == {"filing_status": status, "income_range": "all"}
            assert fact.layout.measure_id == measure
            assert fact.layout.groupby_dimension == "filing_status"
            assert fact.layout.groupby_value_id == status
            assert fact.period.type == "tax_year"
            assert fact.period.value == 2023
            assert fact.geography.id == "0100000US"
            assert fact.entity.name == "tax_unit"
            assert fact.provenance_class == "administrative"
            assert fact.source.source_sha256 == SHA256
            # Each fact cites its value cell and the two headers that label it:
            # its column's header in row 5 and its filing status's in row 3.
            column = _column(first_column, status)
            status_column = _column("B", status)
            cited = {
                cells_by_key[key].address: cells_by_key[key].raw_value
                for key in fact.source_cell_keys
            }
            assert len(cited) == len(fact.source_cell_keys) == 3
            assert cited == {
                f"{column}{row}": value,
                f"{column}5": MEASURE_HEADERS[measure],
                f"{status_column}3": STATUS_HEADERS[status],
            }
            constraints = {
                (item.variable, item.operator, item.value) for item in fact.constraints
            }
            assert (("filing_status", "==", status) in constraints) == (status != "all")
    assert set(by_id) == expected_ids


def test_filing_statuses_add_to_all_returns_within_rounding(built):
    _package, _rows, _cells, facts = built
    by_id = {fact.source_record_id: fact for fact in facts}
    for (record_set, measure), (values, _column_letter, _row) in PUBLISHED.items():
        scale = 1_000 if measure.endswith(("amount", "income")) else 1
        total = by_id[_record_id(record_set, "all", measure)].value
        detail = sum(
            by_id[_record_id(record_set, status, measure)].value
            for status in STATUSES[1:]
        )
        # SOI notes that detail may not add to totals because of rounding;
        # in TY2023 no total misses its statuses by more than one published unit.
        assert abs(total - detail) <= scale


def test_all_returns_match_table_1_2():
    table_1_2 = {
        fact.source_record_id: fact.value
        for fact in load_source_package("soi-table-1-2").build_facts(2023)
    }
    table_1_3 = {
        fact.source_record_id: fact.value
        for fact in load_source_package(PACKAGE_ID).build_facts(2023)
    }
    for measure, record_set in (
        ("return_count", "filing_status_returns"),
        ("adjusted_gross_income", "filing_status_agi"),
    ):
        assert (
            table_1_3[_record_id(record_set, "all", measure)]
            == (table_1_2[f"irs_soi.ty2023.table_1_2.all_returns.all.{measure}"])
        )


def test_other_years_have_no_artifact():
    package = load_source_package(PACKAGE_ID)
    for year in (2022, 2024):
        with pytest.raises(ValueError, match=f"No source artifact for year {year}"):
            package.build_facts(year)
