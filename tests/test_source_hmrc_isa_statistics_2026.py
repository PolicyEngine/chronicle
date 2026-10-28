"""HMRC annual savings statistics, September 2026 (PolicyEngine/microcosm#1415).

Checks the three packages build_package.py writes: the ISA tables (9.4, 9.6 and 9.7
to 9.12), Lifetime ISA Table 1a and the cash ISA limit impact note. Values are re-read
from the workbooks with pandas, located by the publisher's labels rather than by the
packages' coordinates.
"""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import runpy

import pandas as pd
import pytest
import yaml

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import validate_consumer_fact_contract
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)

ROOT = Path(__file__).resolve().parents[1]
ISA = ROOT / "packages/hmrc/isa_statistics_2026"
LISA = ROOT / "packages/hmrc/lisa_statistics_2026"
NOTE = ROOT / "packages/hmrc/cash_isa_limit_reduction_2026"
ISA_ODS = ROOT / "db/data/hmrc/isa_statistics_2026/Individual_Savings_Account_Tables_2026.ods"
LISA_ODS = ROOT / "db/data/hmrc/lisa_statistics_2026/Lifetime_ISA_Tables_2026.ods"
PREFIX = "hmrc.isa_statistics_2026"
TYPES = ("cash_only", "stocks_and_shares_only", "cash_and_stocks_and_shares")


def _facts(package_dir: Path) -> dict[str, object]:
    package = load_source_package(package_dir)
    return {fact.source_record_id: fact for fact in package.build_facts(2026)}


@pytest.fixture(scope="module")
def isa_facts():
    return _facts(ISA)


@pytest.fixture(scope="module")
def isa_sheets():
    return pd.read_excel(ISA_ODS, sheet_name=None, header=None, engine="odf")


def _value(facts: dict, record_set: str, row: str, measure: str) -> float:
    return facts[f"{PREFIX}.{record_set}.{row}.{measure}"].value


@pytest.mark.parametrize(
    ("package_dir", "package_id", "record_sets", "facts"),
    [
        (ISA, "hmrc-isa-statistics-2026", 73, 3397),
        (LISA, "hmrc-lisa-statistics-2026", 8, 40),
        (NOTE, "hmrc-cash-isa-limit-reduction-2026", 1, 2),
    ],
)
def test_packages_validate_register_and_carry_no_anchors(
    package_dir, package_id, record_sets, facts
):
    report = validate_source_package(package_dir, year=2026)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["record_set_count"] == record_sets
    assert report.counts["source_record_count"] == facts
    assert SOURCE_PACKAGE_ALIASES[package_id] == package_dir.relative_to(ROOT / "packages")
    assert package_id in UK_BUNDLE_SOURCES
    text = (package_dir / "source_package.yaml").read_text(encoding="utf-8")
    assert not any(
        isinstance(token, (yaml.AnchorToken, yaml.AliasToken)) for token in yaml.scan(text)
    )
    built = list(_facts(package_dir).values())
    assert validate_facts(built).valid
    assert validate_consumer_fact_contract(built).valid


def test_generator_reproduces_the_committed_packages():
    generator = runpy.run_path(str(ISA / "build_package.py"))
    for package_dir, build in (
        (ISA, "isa_package"),
        (LISA, "lisa_package"),
        (NOTE, "note_package"),
    ):
        assert generator[build]() == (package_dir / "source_package.yaml").read_text(
            encoding="utf-8"
        )


@pytest.mark.parametrize("package_dir", [ISA, LISA, NOTE])
def test_manifests_pin_bytes_licence_and_r2(package_dir):
    data_dir = ROOT / "db/data/hmrc" / package_dir.name
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-10-28"
    entry = manifest["files"][2026]
    content = (data_dir / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    assert entry["storage"]["r2"]["uri"] == (
        f"r2://ledger-raw/raw/uk/hmrc/{manifest['package_id']}/2026/"
        f"{entry['sha256']}/{entry['filename']}"
    )


def test_provenance_and_units_by_table(isa_facts):
    # Table 9.4: four lines a year to 2015-16, five in 2016-17 (Innovative Finance ISAs
    # begin) and six from 2017-18 (Lifetime ISAs begin). Table 9.6: 19 lines a year,
    # less the exchange-traded shares line before 2013-14 and the three Innovative
    # Finance lines before 2016-17.
    by_table = Counter()
    for record_id, fact in isa_facts.items():
        table = record_id.split(".")[2]
        by_table[(table, fact.provenance_class, fact.measure.concept)] += 1
        if fact.provenance_class == "survey_aggregate":
            assert "Survey of Personal Incomes" in fact.survey_instrument
        else:
            assert fact.survey_instrument is None
    assert by_table == {
        ("table9_4", "administrative", "hmrc.isa_accounts_subscribed"): 85,
        ("table9_4", "administrative", "hmrc.isa_amount_subscribed"): 85,
        ("table9_6", "administrative", "hmrc.isa_market_value"): 249,
        ("table9_7", "survey_aggregate", "hmrc.isa_subscribers"): 576,
        ("table9_7", "survey_aggregate", "hmrc.isa_holders"): 96,
        ("table9_8", "survey_aggregate", "hmrc.isa_subscribers"): 264,
        ("table9_8", "survey_aggregate", "hmrc.isa_holders"): 132,
        ("table9_9", "survey_aggregate", "hmrc.isa_subscribers"): 60,
        ("table9_9", "survey_aggregate", "hmrc.isa_holders"): 30,
        ("table9_10", "survey_aggregate", "hmrc.isa_holders"): 624,
        ("table9_10", "survey_aggregate", "hmrc.isa_mean_market_value_per_holder"): 48,
        ("table9_11", "survey_aggregate", "hmrc.isa_holders"): 858,
        ("table9_11", "survey_aggregate", "hmrc.isa_mean_market_value_per_holder"): 66,
        ("table9_12", "survey_aggregate", "hmrc.isa_holders"): 195,
        ("table9_12", "survey_aggregate", "hmrc.isa_mean_market_value_per_holder"): 15,
        ("table9_12", "model_output", "hmrc.isa_holders_share_of_adults"): 14,
    }
    # Tables 9.7 to 9.12 count people under '(thousands)' headings: unscaled.
    assert _value(isa_facts, "table9_7.ty2023.all.subscribers", "all", "all_subscriptions") == 13054561
    assert _value(isa_facts, "table9_7.ty2023.all.holders", "all", "all_holders") == 23025972
    # Table 9.4 is in thousands of accounts and GBP million.
    assert _value(isa_facts, "table9_4.accounts.ty2023", "cash", "accounts") == 9939000
    assert _value(isa_facts, "table9_4.amounts.ty2024", "lifetime", "amounts") == 2818000000


def _money_id(prefix: str, label: str) -> str:
    """'£0-£12,570' -> income_0_to_12570, '£150,001 or more' -> income_150001_plus,
    '£20,000' -> subscription_20000_to_20000, read from the publisher's label."""
    text = label.replace("(thousands)", "").replace("\n", " ").strip()
    if text.endswith(" or more"):
        low = int(text.removesuffix(" or more").lstrip("£").replace(",", ""))
        return f"{prefix}_{low}_plus"
    parts = [int(part.lstrip("£").replace(",", "")) for part in text.split("-")]
    low, high = (parts[0], parts[0]) if len(parts) == 1 else parts
    return f"{prefix}_{low}_to_{high}"


def test_table_9_7_matches_the_workbook_by_label(isa_facts, isa_sheets):
    sheet = isa_sheets["9_7_ISA_subs_by_income"]
    titles = {
        "all": "Range of Income of All ISA Subscribers (maximum combined subscription £20,000)",
        "cash_only": "Range of Income of Cash ISA Subscribers Only",
        "stocks_and_shares_only": "Range of Income of Stocks & Shares ISA Subscribers Only",
        "cash_and_stocks_and_shares": "Range of Income of Cash and Stocks & Shares ISA Subscribers",
    }
    labels = sheet.iloc[:, 0].astype(str).str.strip()
    checked = 0
    for isa_type, title in titles.items():
        (start,) = labels.index[labels == title]
        headers = [str(h) for h in sheet.iloc[start, 1:15]]
        record_set = f"table9_7.ty2023.{isa_type}"
        for offset in range(1, 13):
            label = labels[start + offset]
            row = "all" if label == "All ranges" else _money_id("income", label)
            for column, header in enumerate(headers, start=1):
                if header.startswith("All Subscriptions"):
                    key = (f"{record_set}.subscribers", "all_subscriptions")
                elif header.startswith("No Further Subscription"):
                    key = (f"{record_set}.holders", "no_further_subscription")
                elif header.startswith("All ISA Holders"):
                    key = (f"{record_set}.holders", "all_holders")
                else:
                    key = (f"{record_set}.subscribers", _money_id("subscription", header))
                assert _value(isa_facts, key[0], row, key[1]) == sheet.iloc[start + offset, column]
                checked += 1
    assert checked == 4 * 12 * 14 == sum(
        1 for record_id in isa_facts if record_id.startswith(f"{PREFIX}.table9_7.")
    )


def test_table_9_7_blocks_and_holders_add_up(isa_facts):
    for row in [
        "income_0_to_12570",
        "income_40001_to_50270",
        "income_150001_plus",
        "all",
    ]:
        measures = [
            fact.source_record_id.rsplit(".", 1)[1]
            for fact in isa_facts.values()
            if fact.source_record_id.startswith(f"{PREFIX}.table9_7.ty2023.all.subscribers.{row}.")
        ]
        assert len(measures) == 12
        for measure in measures:
            whole = _value(isa_facts, "table9_7.ty2023.all.subscribers", row, measure)
            parts = sum(
                _value(isa_facts, f"table9_7.ty2023.{t}.subscribers", row, measure)
                for t in TYPES
            )
            assert abs(whole - parts) <= 2, (row, measure, whole, parts)
        for isa_type in ("all", *TYPES):
            record_set = f"table9_7.ty2023.{isa_type}"
            subscribed = _value(isa_facts, f"{record_set}.subscribers", row, "all_subscriptions")
            held = _value(isa_facts, f"{record_set}.holders", row, "all_holders")
            idle = _value(isa_facts, f"{record_set}.holders", row, "no_further_subscription")
            assert abs(subscribed + idle - held) <= 2, (isa_type, row)
    # The four blocks partition the 13.05 million subscribers, 28.8% at GBP 20,000.
    total = _value(isa_facts, "table9_7.ty2023.all.subscribers", "all", "all_subscriptions")
    full = _value(isa_facts, "table9_7.ty2023.all.subscribers", "all", "subscription_20000_to_20000")
    assert round(full / total, 3) == 0.288


def test_tables_9_8_and_9_9_restate_table_9_7(isa_facts):
    for isa_type in TYPES:
        expected = _value(isa_facts, f"table9_7.ty2023.{isa_type}.subscribers", "all", "all_subscriptions")
        persons = _value(isa_facts, "table9_8.ty2023.all.subscribers", "all", f"{isa_type}_subscribers")
        male = _value(isa_facts, "table9_8.ty2023.male.subscribers", "all", f"{isa_type}_subscribers")
        female = _value(isa_facts, "table9_8.ty2023.female.subscribers", "all", f"{isa_type}_subscribers")
        uk = _value(isa_facts, "table9_9.ty2023.subscribers", "K02000001", f"{isa_type}_subscribers")
        assert persons == expected == uk
        assert abs(male + female - persons) <= 2
    holders = _value(isa_facts, "table9_7.ty2023.all.holders", "all", "all_holders")
    assert _value(isa_facts, "table9_8.ty2023.all.holders", "all", "all_holders") == holders
    assert _value(isa_facts, "table9_9.ty2023.holders", "K02000001", "all_holders") == holders
    for table in ("table9_10.ty2023.all", "table9_11.ty2023.all", "table9_12.ty2023"):
        row = "K02000001" if table.startswith("table9_12") else "all"
        assert _value(isa_facts, table, row, "all_holders") == holders
    regions = sum(
        _value(isa_facts, "table9_9.ty2023.subscribers", f"E1200000{i}", "all_subscribers")
        for i in range(1, 10)
    )
    england = _value(isa_facts, "table9_9.ty2023.subscribers", "E92000001", "all_subscribers")
    assert abs(regions - england) <= 9
    countries = england + sum(
        _value(isa_facts, "table9_9.ty2023.subscribers", code, "all_subscribers")
        for code in ("W92000004", "S92000003", "N92000002", "overseas_and_unknown")
    )
    uk = _value(isa_facts, "table9_9.ty2023.subscribers", "K02000001", "all_subscribers")
    assert abs(countries - uk) <= 5


def test_age_bands_cover_the_published_rows(isa_facts):
    persons = [
        fact
        for fact in isa_facts.values()
        if fact.source_record_id.startswith(f"{PREFIX}.table9_8.ty2023.all.subscribers.")
        and fact.source_record_id.endswith(".all_subscribers")
    ]
    assert len(persons) == 22
    bands = sum(fact.value for fact in persons if fact.filters["age_band"] != "all")
    total = next(fact.value for fact in persons if fact.filters["age_band"] == "all")
    assert abs(bands - total) <= 21
    under_24 = next(fact for fact in persons if fact.filters["age_band"] == "age_under_24")
    assert [(c.variable, c.operator, c.value) for c in under_24.constraints if c.variable == "age"] == [
        ("age", "<", 24)
    ]


def test_table_9_4_components_sum_and_match_the_workbook(isa_facts, isa_sheets):
    sheet = isa_sheets["9_4_ISA_subscriptions"]
    labels = sheet.iloc[:, 0].astype(str).str.strip()
    for section, heading, scale in (
        ("accounts", "Number of accounts subscribed in current year (thousands)", 1000),
        ("amounts", "Amounts subscribed (£ million)", 1000000),
    ):
        start = labels.index[labels == heading][0]
        years = [str(y).strip() for y in sheet.iloc[start, 1:18]]
        assert years[15] == "2023 to 2024" and years[16].startswith("2024 to 2025")
        for column, opening in ((16, 2023), (17, 2024)):
            record_set = f"table9_4.{section}.ty{opening}"
            for row_label, component in (
                ("Cash ISA", "cash"),
                ("Stock and Shares ISA", "stocks_and_shares"),
                ("Lifetime ISA", "lifetime"),
                ("Total", "all"),
            ):
                row = labels.index[(labels == row_label) & (labels.index > start)][0]
                assert _value(isa_facts, record_set, component, section) == (
                    sheet.iloc[row, column] * scale
                )
            parts = sum(
                _value(isa_facts, record_set, component, section)
                for component in ("cash", "stocks_and_shares", "innovative_finance", "lifetime")
            )
            assert abs(parts - _value(isa_facts, record_set, "all", section)) <= 2 * scale
    # Products launched later carry no fact before they existed.
    assert f"{PREFIX}.table9_4.accounts.ty2016.lifetime.accounts" not in isa_facts
    assert f"{PREFIX}.table9_4.accounts.ty2017.lifetime.accounts" in isa_facts
    assert f"{PREFIX}.table9_4.accounts.ty2015.innovative_finance.accounts" not in isa_facts


def test_table_9_6_lines_sum_to_their_components(isa_facts):
    record_set = "table9_6.ty2024"
    rows = Counter()
    for record_id, fact in isa_facts.items():
        if record_id.startswith(f"{PREFIX}.{record_set}."):
            rows[(fact.filters["isa_component"], fact.filters["isa_asset_type"])] = fact.value
    for component in ("stocks_and_shares", "cash", "innovative_finance"):
        lines = sum(v for (c, a), v in rows.items() if c == component and a != "all")
        assert abs(lines - rows[(component, "all")]) <= 2e6, component
    adult = sum(rows[(c, "all")] for c in ("stocks_and_shares", "cash", "innovative_finance"))
    assert abs(adult - rows[("all", "all")]) <= 2e6
    assert rows[("stocks_and_shares", "cash_on_deposit")] == 22398e6


def test_lifetime_isa_table_1a():
    facts = _facts(LISA)
    assert len(facts) == 40
    latest = {
        record_id.rsplit(".", 1)[1]: fact.value
        for record_id, fact in facts.items()
        if ".table1a.ty2025." in record_id
    }
    assert latest == {
        "house_purchase_withdrawers": 99750,
        "house_purchase_withdrawal_value": 1536484000,
        "unauthorised_withdrawers": 154100,
        "unauthorised_withdrawal_value": 475944000,
        "withdrawal_charges": 118985000,
    }
    sheet = pd.read_excel(LISA_ODS, sheet_name="Lifetime_ISA_sheet", header=None, engine="odf")
    labels = sheet.iloc[:, 0].astype(str)
    row = labels.index[labels == "2018 to 2019"][0]
    assert facts["hmrc.lisa_statistics_2026.table1a.ty2018.tax_year_2018.house_purchase_withdrawers"].value == sheet.iloc[row, 1]


def test_impact_note_shares():
    facts = _facts(NOTE)
    shares = {fact.filters["cash_isa_subscription_band"]: fact for fact in facts.values()}
    assert shares["under_12000"].value + shares["over_12000"].value == 100
    assert shares["over_12000"].value == 22
    for fact in shares.values():
        assert fact.provenance_class == "model_output"
        assert fact.period.value == 2022
        assert ("age", "<", 65) in {(c.variable, c.operator, c.value) for c in fact.constraints}
