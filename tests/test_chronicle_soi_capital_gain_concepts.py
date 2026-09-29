"""IRS SOI capital-gain columns carry the concept their publisher documents.

Two different IRS capital-gain counts share the ``net_capital_gains_*``
measure ids:

- Historic Table 2 and the congressional-district file read ``N01000`` /
  ``A01000``. Every IRS documentation guide for those files (TY2020-TY2023)
  defines them as "Number of returns with net capital gain (less loss)" and
  "Net capital gain (less loss) amount", sourced from Form 1040 line 7,
  "Capital gain or (loss)". That line holds a Schedule D gain, a loss limited
  to $3,000 ($1,500 married filing separately), or capital gain distributions
  reported without a Schedule D.
- Table 1.4 columns 37/38 (TY2022-TY2023; 25/26 before) are "Sales of capital
  assets reported on Form 1040, Schedule D: Taxable net gain", a Schedule D
  gain-only count. For TY2022 it is 12,915,122 returns against Historic Table
  2's 30,465,850.

The concept ids keep those apart. ``measure_id`` stays shared because it is
the selector consumers key on; this module pins both properties so a cloned
vintage (for example a TY2023 package generated from its TY2022 twin) cannot
reintroduce the Table 1.4 concept on a line-7 column. See
``docs/concept-migrations.md`` for the rename record.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml

from chronicle.consumer_contract import consumer_fact_row
from chronicle.source_package import load_source_package

REPO_ROOT = Path(__file__).resolve().parents[1]
IRS_SOI_PACKAGES = REPO_ROOT / "packages" / "irs_soi"

LINE_7_RETURNS_CONCEPT = "irs_soi.returns_with_form_1040_capital_gain_or_loss"
LINE_7_AMOUNT_CONCEPT = "irs_soi.form_1040_capital_gain_or_loss"
LINE_7_DECLARATIONS = {
    "N01000": (
        "net_capital_gains_returns",
        "Returns with net capital gain (less loss)",
        LINE_7_RETURNS_CONCEPT,
    ),
    "A01000": (
        "net_capital_gains_amount",
        "Net capital gain (less loss)",
        LINE_7_AMOUNT_CONCEPT,
    ),
}
SCHEDULE_D_GAIN_CONCEPTS = frozenset(
    {
        "irs_soi.returns_with_taxable_net_capital_gains",
        "irs_soi.taxable_net_capital_gains",
    }
)
# Ids retired by the rename recorded in docs/concept-migrations.md. The
# congressional-district package used these for the same line-7 columns.
RETIRED_LINE_7_CONCEPTS = frozenset(
    {
        "irs_soi.returns_with_net_capital_gains",
        "irs_soi.net_capital_gains",
    }
)
# Packages on main that read the line-7 columns. Later vintages join
# automatically because the scan below keys on the IRS variable name.
KNOWN_LINE_7_PACKAGES = frozenset(
    {
        "historic_table_2",
        "historic_table_2_state_broad_2022",
        "congressional_district_2022",
    }
)


def _measures(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        if "measure_id" in node and "concept" in node:
            yield node
        for value in node.values():
            yield from _measures(value)
    elif isinstance(node, list):
        for value in node:
            yield from _measures(value)


def _irs_soi_measures() -> Iterator[tuple[str, dict[str, Any]]]:
    for path in sorted(IRS_SOI_PACKAGES.glob("*/source_package.yaml")):
        package = yaml.safe_load(path.read_text())
        for measure in _measures(package):
            yield path.parent.name, measure


def _line_7_variable(measure: dict[str, Any]) -> str | None:
    for key in ("source_column_id", "expected_column_header"):
        if measure.get(key) in LINE_7_DECLARATIONS:
            return measure[key]
    return None


def test_every_line_7_column_carries_the_line_7_concept():
    seen: set[str] = set()
    for package_dir, measure in _irs_soi_measures():
        variable = _line_7_variable(measure)
        if variable is None:
            continue
        seen.add(package_dir)
        measure_id, label, concept = LINE_7_DECLARATIONS[variable]
        where = f"{package_dir}:{measure['measure_id']}"
        assert measure["measure_id"] == measure_id, where
        assert measure["label"] == label, where
        assert measure["concept"] == concept, where
        # Both guards name the same IRS variable, so a column shift cannot
        # move the concept onto a neighbour.
        assert measure.get("source_column_id") == variable, where
        assert measure.get("expected_column_header") == variable, where

    assert KNOWN_LINE_7_PACKAGES <= seen


def test_schedule_d_gain_concepts_stay_on_table_1_4():
    declaring = {
        (package_dir, measure["measure_id"])
        for package_dir, measure in _irs_soi_measures()
        if measure["concept"] in SCHEDULE_D_GAIN_CONCEPTS
    }

    assert declaring == {
        ("table_1_4", "net_capital_gains_returns"),
        ("table_1_4", "net_capital_gains_amount"),
    }


def test_retired_line_7_concepts_are_not_declared():
    declaring = sorted(
        f"{package_dir}:{measure['measure_id']}"
        for package_dir, measure in _irs_soi_measures()
        if measure["concept"] in RETIRED_LINE_7_CONCEPTS
    )

    assert declaring == []


def _facts_by_record(package_id: str, year: int) -> dict[str, Any]:
    package = load_source_package(package_id)
    return {fact.source_record_id: fact for fact in package.build_facts(year)}


@pytest.fixture(scope="module")
def capital_gain_rows() -> dict[str, dict[str, Any]]:
    """Consumer rows for the US all-returns capital-gain facts, TY2022."""
    ht2 = _facts_by_record("soi-historic-table-2", 2022)
    cd = _facts_by_record("soi-congressional-district-2022", 2022)
    table_1_4 = _facts_by_record("soi-table-1-4", 2022)
    facts = {
        "ht2_returns": ht2[
            "irs_soi.ty2022.historic_table_2.us.all.net_capital_gains_returns"
        ],
        "ht2_amount": ht2[
            "irs_soi.ty2022.historic_table_2.us.all.net_capital_gains_amount"
        ],
        "cd_returns": cd[
            "irs_soi.ty2022.congressional_district_2022.all_returns.us."
            "net_capital_gains_returns"
        ],
        "cd_amount": cd[
            "irs_soi.ty2022.congressional_district_2022.all_returns.us."
            "net_capital_gains_amount"
        ],
        "t14_returns": table_1_4[
            "irs_soi.ty2022.table_1_4.all.net_capital_gains_returns"
        ],
        "t14_amount": table_1_4[
            "irs_soi.ty2022.table_1_4.all.net_capital_gains_amount"
        ],
    }
    return {name: consumer_fact_row(fact) for name, fact in facts.items()}


def test_consumer_selector_survives_the_concept_rename(capital_gain_rows):
    # Consumers select these facts by source_measure_id; the rename must not
    # move it, and the values stay the published cells.
    expected = {
        "ht2_returns": (
            "net_capital_gains_returns",
            LINE_7_RETURNS_CONCEPT,
            30_465_850,
        ),
        "ht2_amount": (
            "net_capital_gains_amount",
            LINE_7_AMOUNT_CONCEPT,
            1_251_675_034_000,
        ),
        "cd_returns": ("net_capital_gains_returns", LINE_7_RETURNS_CONCEPT, 29_845_710),
        "cd_amount": (
            "net_capital_gains_amount",
            LINE_7_AMOUNT_CONCEPT,
            1_157_234_600_000,
        ),
        "t14_returns": (
            "net_capital_gains_returns",
            "irs_soi.returns_with_taxable_net_capital_gains",
            12_915_122,
        ),
        "t14_amount": (
            "net_capital_gains_amount",
            "irs_soi.taxable_net_capital_gains",
            1_269_785_083_000,
        ),
    }

    for name, (measure_id, concept, value) in expected.items():
        row = capital_gain_rows[name]
        assert row["observed_measure"]["source_measure_id"] == measure_id, name
        assert row["observed_measure"]["source_concept"] == concept, name
        assert row["value"] == value, name


def _cells_by_address(package_id: str, year: int) -> dict[str, Any]:
    cells = load_source_package(package_id).build_source_cells(year)
    assert len({cell.sheet_name for cell in cells}) == 1
    return {cell.address: cell for cell in cells}


def test_publisher_cells_show_n01000_is_line_7_not_schedule_d_gain():
    """Differential check of the concept choice against the registered bytes.

    Form 1040 line 7 holds a Schedule D gain, a limited Schedule D loss, or
    capital gain distributions filed without a Schedule D. Table 1.4 reports
    those three groups in separate columns. Historic Table 2's N01000 (a
    population count rounded to tens) matches their sum, not the gain column.
    """
    ht2 = _cells_by_address("soi-historic-table-2", 2022)
    table_1_4 = _cells_by_address("soi-table-1-4", 2022)

    assert (ht2["A2"].raw_value, ht2["B2"].raw_value) == ("US", 0)
    assert ht2["AK1"].raw_value == "N01000"
    n01000 = ht2["AK2"].raw_value

    assert table_1_4["A9"].raw_value == "All returns, total"
    assert "Capital gain distributions" in table_1_4["AJ3"].raw_value
    assert "Schedule D" in table_1_4["AL3"].raw_value
    assert table_1_4["AL4"].raw_value == "Taxable\nnet gain"
    assert table_1_4["AN4"].raw_value == "Taxable\nnet loss"
    distributions_only = table_1_4["AJ9"].raw_value
    schedule_d_gain = table_1_4["AL9"].raw_value
    schedule_d_loss = table_1_4["AN9"].raw_value

    line_7_components = distributions_only + schedule_d_gain + schedule_d_loss
    assert (n01000, line_7_components) == (30_465_850, 30_461_045)
    assert abs(n01000 - line_7_components) / line_7_components < 0.0025
    assert n01000 / schedule_d_gain > 2.3


def test_line_7_and_schedule_d_gain_facts_are_different_semantic_facts(
    capital_gain_rows,
):
    rows = capital_gain_rows
    for kind in ("returns", "amount"):
        ht2, table_1_4 = rows[f"ht2_{kind}"], rows[f"t14_{kind}"]
        # Same period, geography, entity and measure id: only the concept
        # separates Form 1040 line 7 from Schedule D taxable net gain.
        assert ht2["period"] == table_1_4["period"]
        assert ht2["geography"]["id"] == table_1_4["geography"]["id"]
        assert ht2["semantic_fact_key"] != table_1_4["semantic_fact_key"]
