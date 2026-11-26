"""Historic Table 2 state rows for Schedule 1 line 1 and Schedule A lines 7, 8a, 14.

``soi-historic-table-2-state-broad-2022`` reads eight more columns of
``22in55cmcsv.csv``. The TY2022 documentation guide (``22incmdocguide.doc``,
extract in ``tests/data/irs_soi_doc_guides``) defines them:

- ``N00700``/``A00700``: "state and local income tax refunds", Schedule 1
  line 1, which the 2022 form words "Taxable refunds, credits, or offsets of
  state and local income taxes";
- ``N18300``/``A18300``: "taxes paid", Schedule A line 7 ("Add lines 5e and 6");
- ``N19300``/``A19300``: "mortgage interest paid", Schedule A line 8a;
- ``N19700``/``A19700``: "Total charitable contributions", Schedule A line 14.

``test_chronicle_soi_doc_guide_columns`` pins each measure id to its guide
definition. This module checks the facts themselves against the published
cells, against the file's own US row, and against Publication 1304 Table 2.1.
"""

from __future__ import annotations

import csv
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from chronicle.source_package import load_source_package

REPO_ROOT = Path(__file__).resolve().parents[1]
HT2_DIR = REPO_ROOT / "db" / "data" / "irs_soi" / "historic_table_2"
PACKAGE_ID = "soi-historic-table-2-state-broad-2022"
RECORD_PREFIX = "irs_soi.ty2022.historic_table_2.state_broad."

# measure_id -> IRS variable. Amount columns are published in thousands.
NEW_MEASURES = {
    "taxable_state_local_income_tax_refunds_returns": "N00700",
    "taxable_state_local_income_tax_refunds_amount": "A00700",
    "taxes_paid_deduction_returns": "N18300",
    "taxes_paid_deduction_amount": "A18300",
    "mortgage_interest_paid_returns": "N19300",
    "mortgage_interest_paid_amount": "A19300",
    "charitable_returns": "N19700",
    "charitable_amount": "A19700",
}
# Historic Table 2 publishes these rows besides the 50 states and DC.
NON_STATE_ROWS = frozenset({"US", "OA", "PR"})


@cache
def _csv_all_returns_rows(filename: str) -> dict[str, dict[str, str]]:
    """Each geography's AGI_STUB 0 row, parsed with the csv module alone."""
    with (HT2_DIR / filename).open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    return {row["STATE"]: row for row in rows if row["AGI_STUB"] == "0"}


def _cell(row: dict[str, str], variable: str) -> int:
    return int(row[variable].replace(",", ""))


def _scale(variable: str) -> int:
    return 1000 if variable.startswith("A") else 1


@cache
def _facts() -> dict[str, Any]:
    package = load_source_package(PACKAGE_ID)
    return {fact.source_record_id: fact for fact in package.build_facts(2023)}


def _state_fact(state: str, measure_id: str) -> Any:
    return _facts()[f"{RECORD_PREFIX}{state.lower()}.all.{measure_id}"]


def test_every_new_fact_is_its_published_cell():
    """Exhaustive over all 51 states and eight columns: 408 facts."""
    rows = _csv_all_returns_rows("22in55cmcsv.csv")
    states = sorted(set(rows) - NON_STATE_ROWS)

    assert len(states) == 51
    for state in states:
        for measure_id, variable in NEW_MEASURES.items():
            fact = _state_fact(state, measure_id)
            where = f"{state}:{measure_id}"
            assert fact.value == _cell(rows[state], variable) * _scale(variable), where
            assert fact.layout.source_column_id == variable, where
            assert fact.period.value == 2022, where
            assert fact.measure.unit == (
                "usd" if variable.startswith("A") else "count"
            ), where


def test_states_other_areas_and_puerto_rico_add_to_the_us_row():
    """Accounting identity of the published file, checked through the facts.

    Amounts add exactly. Return counts are each rounded to the nearest ten, so
    53 rounded cells can miss the US cell by at most 5 x 53.
    """
    rows = _csv_all_returns_rows("22in55cmcsv.csv")
    states = sorted(set(rows) - NON_STATE_ROWS)

    for measure_id, variable in NEW_MEASURES.items():
        scale = _scale(variable)
        total = sum(_state_fact(state, measure_id).value for state in states)
        total += (_cell(rows["OA"], variable) + _cell(rows["PR"], variable)) * scale
        us = _cell(rows["US"], variable) * scale
        if variable.startswith("A"):
            assert total == us, measure_id
        else:
            assert abs(total - us) <= 5 * 53, measure_id


def test_state_sums_track_table_2_1_lines_8a_and_14():
    """Differential check against the national publication's same lines.

    Table 2.1 (Publication 1304) tabulates itemized returns from the SOI
    sample; Historic Table 2 tabulates the state files. The 51 state rows come
    to 0.989-1.000 of Table 2.1's TY2022 line 8a and line 14 totals. A column
    one place over would not: the line 8b and 13 neighbours are 2% and 0.3% of
    these totals.
    """
    table_2_1 = load_source_package("soi-table-2-1")
    national = {
        fact.source_record_id.rsplit(".", 1)[1]: fact.value
        for fact in table_2_1.build_facts(2022)
        if fact.source_record_id.startswith(
            "irs_soi.ty2022.table_2_1.itemized_all_returns.all."
        )
    }
    rows = _csv_all_returns_rows("22in55cmcsv.csv")
    states = sorted(set(rows) - NON_STATE_ROWS)
    ratios = {
        measure_id: sum(_state_fact(state, measure_id).value for state in states)
        / national[measure_id]
        for measure_id in (
            "mortgage_interest_paid_returns",
            "mortgage_interest_paid_amount",
            "charitable_returns",
            "charitable_amount",
        )
    }

    assert ratios == pytest.approx(
        {
            "mortgage_interest_paid_returns": 1.0003,
            "mortgage_interest_paid_amount": 0.9959,
            "charitable_returns": 0.9918,
            "charitable_amount": 0.9887,
        },
        abs=0.0001,
    )


def test_ty2023_file_carries_the_same_variables_in_the_same_columns():
    """A TY2023 twin of this package can read these columns unchanged.

    ``23in55cmcsv.csv`` inserts two columns at DP, after every column read
    here, and ``23incmdocguide.doc`` defines the eight variables in the same
    words as the TY2022 guide.
    """
    package = load_source_package(PACKAGE_ID)
    columns = {
        measure["measure_id"]: measure["column"]
        for record_set in package.record_sets
        for measure in record_set.payload["measures"]
        if measure["measure_id"] in NEW_MEASURES
    }
    with (HT2_DIR / "23in55cmcsv.csv").open(newline="", encoding="utf-8-sig") as file:
        header = next(csv.reader(file))

    def index(letters: str) -> int:
        value = 0
        for letter in letters:
            value = value * 26 + ord(letter) - ord("A") + 1
        return value - 1

    assert {
        measure_id: header[index(column)] for measure_id, column in columns.items()
    } == NEW_MEASURES
