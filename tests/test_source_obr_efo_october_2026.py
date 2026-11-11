"""OBR Economic and fiscal outlook, October 2026 (PolicyEngine/chronicle#393).

Checks the five packages scripts/build_obr_efo_october_2026.py writes. Values are
re-read from the workbooks with pandas and located by the publisher's labels, not by the
packages' coordinates.
"""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import re
import runpy

import pandas as pd
import pytest
import yaml

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import (
    build_semantic_fact_key,
    build_universe_constraint_set_key,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "db/data/obr"
KINDS = ("receipts", "expenditure", "economy", "aggregates", "policy")
OCTOBER = "obr.efo_2026_10"


def _facts(kind: str) -> dict[str, object]:
    package = load_source_package(f"obr-efo-{kind}-october-2026")
    return {fact.source_record_id: fact for fact in package.build_facts(2026)}


@pytest.fixture(scope="module")
def facts():
    return {kind: _facts(kind) for kind in KINDS}


def _sheet(kind: str, sheet: str) -> pd.DataFrame:
    path = DATA / f"efo_{kind}_october_2026" / f"efo_{kind}.xlsx"
    return pd.read_excel(path, sheet_name=sheet, header=None)


def _cell(frame: pd.DataFrame, label: str, year: str, *, label_column: int = 1) -> float:
    """The cell in the row whose label is `label`, under the header `year`."""
    labels = frame.iloc[:, label_column].astype(str)
    (row,) = labels.index[labels == label]
    header_row = max(
        r for r in frame.index[: row] if (frame.iloc[r].astype(str).str.strip() == year).any()
    )
    (column,) = [
        c for c in frame.columns if str(frame.iloc[header_row, c]).strip() == year
    ]
    return frame.iloc[row, column]


@pytest.mark.parametrize(
    ("kind", "record_sets", "count"),
    [
        ("receipts", 1551, 1551),
        ("expenditure", 165, 165),
        ("economy", 56, 56),
        ("aggregates", 25, 25),
        ("policy", 624, 2520),
    ],
)
def test_packages_validate_register_and_carry_no_anchors(kind, record_sets, count):
    package_dir = ROOT / "packages/obr" / f"efo_{kind}_october_2026"
    package_id = f"obr-efo-{kind}-october-2026"
    report = validate_source_package(package_dir, year=2026)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["record_set_count"] == record_sets
    assert report.counts["source_record_count"] == count
    assert SOURCE_PACKAGE_ALIASES[package_id] == package_dir.relative_to(ROOT / "packages")
    assert package_id in UK_BUNDLE_SOURCES
    text = (package_dir / "source_package.yaml").read_text(encoding="utf-8")
    assert not any(
        isinstance(token, (yaml.AnchorToken, yaml.AliasToken)) for token in yaml.scan(text)
    )
    built = list(_facts(kind).values())
    assert validate_facts(built).valid
    assert validate_consumer_fact_contract(built).valid
    keys = Counter(build_semantic_fact_key(fact) for fact in built)
    assert max(keys.values()) == 1


def test_generator_reproduces_the_committed_packages():
    generator = runpy.run_path(str(ROOT / "scripts/build_obr_efo_october_2026.py"))
    for kind, build in generator["BUILDERS"].items():
        path = ROOT / "packages/obr" / f"efo_{kind}_october_2026" / "source_package.yaml"
        assert build() == path.read_text(encoding="utf-8"), kind


@pytest.mark.parametrize("kind", KINDS)
def test_manifests_pin_bytes_licence_and_r2(kind):
    data_dir = DATA / f"efo_{kind}_october_2026"
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-10-29"
    assert manifest["source_page"] == (
        "https://obr.uk/efo/economic-and-fiscal-outlook-october-2026/"
    )
    entry = manifest["files"][2026]
    content = (data_dir / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    assert entry["storage"]["r2"]["uri"] == (
        f"r2://ledger-raw/raw/uk/obr/{manifest['package_id']}/2026/"
        f"{entry['sha256']}/{entry['filename']}"
    )


@pytest.mark.parametrize("kind", ("receipts", "expenditure", "economy", "aggregates"))
def test_every_march_line_keeps_its_line_id_and_concept(facts, kind):
    """The October package carries each March line under the same line id and
    concept; since chronicle#397 the years both vintages publish are October's only."""
    march = load_source_package(f"obr-efo-{kind}-march-2026").build_facts(2026)

    def lines(prefix: str, built) -> dict[str, set[str]]:
        found: dict[str, set[str]] = {}
        for fact in built:
            record_set = fact.layout.record_set_id
            if not record_set.startswith(prefix):
                continue
            line = re.sub(r"\.(fy|cy)\d{4}$", "", record_set.removeprefix(prefix))
            found.setdefault(line, set()).add(fact.measure.concept)
        return found

    march_lines = lines(f"obr.efo_2026_03.{kind}.", march)
    october_lines = lines(f"{OCTOBER}.{kind}.", facts[kind].values())
    for line, concepts in march_lines.items():
        assert october_lines.get(line) == concepts, line
    # chronicle#397: a line October prints in every year March had left the March
    # package; the build keeps its March record set, and October its id and concept.
    generator = runpy.run_path(str(ROOT / "scripts/build_obr_efo_october_2026.py"))
    for text, _before in generator["LINES_LEFT_IN_OCTOBER_ONLY"].get(kind, ()):
        (record_set,) = yaml.safe_load(text)
        line = re.sub(
            r"\.(fy|cy)\d{4}$",
            "",
            record_set["record_set_id"].removeprefix(f"obr.efo_2026_03.{kind}."),
        )
        assert line not in march_lines, line
        assert october_lines[line] == {record_set["measures"][0]["concept"]}, line


# chronicle#397: of two vintages' numbers for one line and year, Chronicle keeps the
# later. What the March 2026 packages keep, by line: every line's 2024-25 outturn
# (calendar 2024 for the economy), except the lines October starts in 2026-27, which
# keep their 2025-26 forecast. Sheet 3.10's total is not one of them: October prints
# its 2025-26 as table 4.1's 'Betting and gaming taxes'.
MARCH_KEEPS = {
    "receipts": (41, {2024: 34, 2025: 7}),
    "expenditure": (23, {2024: 23}),
    "economy": (6, {2024: 6}),
    "aggregates": (4, {2024: 1, 2025: 3}),
}


def _line_year(fact) -> tuple:
    """A fact's line and year, whatever its id; the assertion is left out, so a March
    forecast meets October's outturn for the same year."""
    return (
        fact.measure.concept,
        fact.measure.unit,
        fact.period.type,
        fact.period.value,
        fact.geography.level,
        fact.geography.id,
        fact.entity.name,
        fact.entity.role,
        build_universe_constraint_set_key(fact),
    )


@pytest.mark.parametrize("kind", ("receipts", "expenditure", "economy", "aggregates"))
def test_march_keeps_only_the_line_years_october_does_not_publish(facts, kind):
    march = load_source_package(f"obr-efo-{kind}-march-2026").build_facts(2026)
    october = {fact.layout.record_set_id for fact in facts[kind].values()}
    record_sets = {fact.layout.record_set_id for fact in march}
    assert not {
        record_set
        for record_set in record_sets
        if record_set.replace("obr.efo_2026_03.", f"{OCTOBER}.", 1) in october
    }
    # Nor under another id: October's table 4.1 prints sheet 3.10's 2025-26 total.
    october_line_years = {_line_year(fact) for fact in facts[kind].values()}
    assert not [
        fact.layout.record_set_id
        for fact in march
        if _line_year(fact) in october_line_years
    ]
    count, years = MARCH_KEEPS[kind]
    assert len(march) == len(record_sets) == count
    assert Counter(fact.period.value for fact in march) == years
    lines = Counter(
        re.sub(r"\.(fy|cy)\d{4}$", "", record_set) for record_set in record_sets
    )
    assert set(lines.values()) == {1}
    # The later years are October's now, each line under the same line id.
    assert {
        line.replace("obr.efo_2026_03.", f"{OCTOBER}.", 1) for line in lines
    } <= {re.sub(r"\.(fy|cy)\d{4}$", "", record_set) for record_set in october}
    if kind == "aggregates":
        forecasts = {
            fact.measure.concept for fact in march if fact.period.value == 2025
        }
        assert forecasts == {
            "obr.public_sector_current_receipts",
            "obr.total_managed_expenditure",
            "obr.public_sector_net_borrowing",
        }
        assert {fact.assertion for fact in march if fact.period.value == 2025} == {
            "source_projection"
        }


def test_outturn_and_forecast_follow_the_tables(facts):
    receipts = facts["receipts"]
    income_tax = {
        fact.period.value: fact
        for fact in receipts.values()
        if fact.layout.record_set_id.startswith(f"{OCTOBER}.receipts.income_tax.")
    }
    # 2025-26 is outturn in October (a forecast in March), and 2031-32 is new.
    assert sorted(income_tax) == list(range(2025, 2032))
    assert income_tax[2025].assertion == "observation"
    assert {income_tax[year].assertion for year in range(2026, 2032)} == {
        "source_projection"
    }
    assert income_tax[2025].value == pytest.approx(
        _cell(_sheet("receipts", "4.4"), "Income tax (gross of tax credits)", "2025-26") * 1e9
    )


def test_table_4_5_savings_income(facts):
    """PolicyEngine/microcosm#1418's savings path: growth rates as published."""
    frame = _sheet("receipts", "4.5")
    rows = {
        fact.period.value: fact
        for fact in facts["receipts"].values()
        if fact.layout.record_set_id.startswith(
            f"{OCTOBER}.receipts.self_employed_income_growth.savings_income."
        )
    }
    assert sorted(rows) == list(range(2024, 2032))
    for year, fact in rows.items():
        assert fact.measure.concept == "obr.self_employed_income_growth.savings_income"
        assert fact.layout.measure_id == "growth_rate"
        assert fact.measure.unit == "percent"
        assert fact.assertion == "source_projection"
        label = f"{year}-{(year + 1) % 100:02d}"
        assert fact.value == _cell(frame, "Savings income", label)
    # The path from 2023-24 to 2025-26 that Max cites (x1.358).
    assert round((1 + rows[2024].value / 100) * (1 + rows[2025].value / 100), 3) == 1.358


def test_northern_ireland_domestic_rates_in_both_places(facts):
    receipts = [
        fact
        for fact in facts["receipts"].values()
        if fact.layout.record_set_id.startswith(
            f"{OCTOBER}.receipts.other_taxes.northern_ireland_domestic_rates."
        )
    ]
    expenditure = [
        fact
        for fact in facts["expenditure"].values()
        if fact.layout.record_set_id.startswith(f"{OCTOBER}.expenditure.domestic_rates.")
    ]
    assert len(receipts) == len(expenditure) == 7
    by_year = {fact.period.value: fact.value for fact in expenditure}
    for fact in receipts:
        assert fact.layout.source_row_id  # each carries its own table and row
        assert fact.value != by_year[fact.period.value]
    assert {fact.measure.concept for fact in expenditure} == {"obr.domestic_rates"}
    assert _cell(_sheet("receipts", "4.2"), "Northern Ireland domestic rates", "2025-26") * 1e9 == (
        next(f.value for f in receipts if f.period.value == 2025)
    )


def test_restated_rows_and_tables_left_out(facts):
    record_sets = {fact.layout.record_set_id for fact in facts["receipts"].values()}
    # Table 4.7's total SDLT and ATED rows restate table 4.8's; tables 4.9 and 4.19
    # are left out (no unit; a mislabelled unit over thresholds).
    assert not any(".property_transaction_taxes.total_sdlt." in r for r in record_sets)
    assert not any(".property_transaction_taxes.annual_tax_on" in r for r in record_sets)
    path = ROOT / "packages/obr/efo_receipts_october_2026/source_package.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    sheets = Counter(record_set["sheet_name"] for record_set in payload["record_sets"])
    assert set(sheets) == {f"4.{n}" for n in range(1, 23)} - {"4.9", "4.19"}
    # Rows that restate another table's row are ported once (the build asserts the
    # copies equal): tables 4.22 and 4.21 against 4.20, 4.8 and 4.2, and table
    # 4.1's betting and gaming row against table 4.10 from 2026-27.
    for line in (
        "fiscally_neutral_receipts.contracts_for_difference",
        "fiscally_neutral_receipts.renewables_obligation",
        "fiscally_neutral_receipts.capacity_markets",
        "fiscally_neutral_receipts.green_gas_levy",
        "fiscally_neutral_receipts.warm_homes_discount",
        "fiscally_neutral_receipts.vat_refunds",
        "fiscally_neutral_receipts.extended_producer_responsibility",
        "fiscally_neutral_receipts.community_infrastructure_levy",
        "contracts_for_difference_drivers.c_d_e_f_forecast_gbp_million",
    ):
        assert not any(f".receipts.{line}." in r for r in record_sets), line
    betting = sorted(
        r for r in record_sets if ".other_hmrc_taxes.betting_and_gaming_taxes." in r
    )
    assert betting == [f"{OCTOBER}.receipts.other_hmrc_taxes.betting_and_gaming_taxes.fy2025"]
    # Table 4.22 prints '£ million' over GBP billion cells.
    total = next(
        fact.value
        for fact in facts["receipts"].values()
        if fact.layout.record_set_id
        == f"{OCTOBER}.receipts.fiscally_neutral_receipts.total_fiscally_neutral_receipts.fy2026"
    )
    assert total == pytest.approx(
        _cell(_sheet("receipts", "4.22"), "Total fiscally neutral receipts", "2026-27") * 1e9
    )


def test_cash_and_accrued_taxes_share_a_concept(facts):
    """Table 4.1 (accrued) and table 4.8 (cash) print the same taxes: each pair shares
    a concept and differs in accounting_basis, as chronicle#381's excise duties do."""
    by_concept: dict[str, dict[str, set]] = {}
    for fact in facts["receipts"].values():
        if fact.measure.concept_relation != "exact":
            continue
        basis = fact.filters["accounting_basis"]
        entry = by_concept.setdefault(fact.measure.concept, {})
        entry.setdefault(basis, set()).add(fact.measure.source_concept)
        label = fact.layout.groupby_value_label
        assert label.endswith("(accrued)" if basis == "accrual" else "(cash)"), label
    assert by_concept["obr.diverted_profits_tax"] == {
        "accrual": {"obr.other_hmrc_taxes.diverted_profits_tax"},
        "cash": {"obr.cash_receipts.diverted_profits_tax"},
    }
    assert len([c for c, bases in by_concept.items() if set(bases) == {"accrual", "cash"}]) == 8
    # Table 4.1's accrued vaping tax and 2025-26 betting and gaming join the March
    # lines' concepts, whose cash lines come from table 4.8.
    assert set(by_concept["obr.vaping_tax"]) == {"accrual"}
    assert set(by_concept["obr.betting_and_gaming_duties"]) == {"accrual"}
    tobacco = next(
        fact
        for fact in facts["receipts"].values()
        if fact.layout.record_set_id == f"{OCTOBER}.receipts.tobacco_duties.fy2025"
    )
    assert tobacco.layout.measure_label == "Tobacco duties, cash basis, FY2025-26"


def test_policy_measure_labels_are_trimmed():
    path = ROOT / "packages/obr/efo_policy_october_2026/source_package.yaml"
    labels = yaml.safe_load(path.read_text(encoding="utf-8"))["dimension_value_labels"]
    measures = labels["policy_measure"]
    assert len(measures) == 103
    assert all(label == label.strip() for label in measures.values())
    assert measures["measure_61"].startswith("Property Income:")


def test_sample_values_by_label(facts):
    expenditure = facts["expenditure"]
    state_pension = next(
        fact
        for fact in expenditure.values()
        if fact.layout.record_set_id == f"{OCTOBER}.expenditure.state_pension.fy2026"
    )
    assert state_pension.value == pytest.approx(
        _cell(_sheet("expenditure", "5.9"), "State pension", "2026-27") * 1e9
    )
    economy = facts["economy"]
    deposit = {
        fact.period.value: fact
        for fact in economy.values()
        if fact.layout.record_set_id.startswith(f"{OCTOBER}.economy.deposit_rate.")
    }
    frame = _sheet("economy", "1.9")
    (row,) = frame.index[frame.iloc[:, 1] == 2025]
    (column,) = [c for c in frame.columns if frame.iloc[2, c] == "Deposit rate"]
    assert deposit[2025].value == frame.iloc[row, column]
    assert deposit[2025].assertion == "observation"
    assert deposit[2026].assertion == "source_projection"
    policy = facts["policy"]
    first = next(
        fact
        for fact in policy.values()
        if fact.layout.record_set_id == f"{OCTOBER}.policy.measure_1.fy2026"
        and fact.layout.groupby_value_id == "total"
    )
    table = _sheet("policy", "1.1")
    (start,) = table.index[table.iloc[:, 2] == 1]
    total = next(r for r in table.index[start:] if table.iloc[r, 6] == "Total")
    assert table.iloc[6, 8] == "2026-27"
    assert first.value == pytest.approx(table.iloc[total, 8] * 1e6)
    assert first.measure.concept == "obr.policy_decision_costing"


def test_policy_measures_sum_to_their_totals(facts):
    rows: dict[tuple[str, int], dict[str, float]] = {}
    for fact in facts["policy"].values():
        record_set = fact.layout.record_set_id
        if ".policy.summary." in record_set:
            continue
        rows.setdefault((record_set, fact.period.value), {})[
            fact.layout.groupby_value_id
        ] = fact.value
    assert len({record_set.rsplit(".", 1)[0] for record_set, _ in rows}) == 103
    for key, values in rows.items():
        parts = sum(value for row, value in values.items() if row != "total")
        assert abs(parts - values["total"]) <= 1e6, key
