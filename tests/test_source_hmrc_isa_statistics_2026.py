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
        (ISA, "hmrc-isa-statistics-2026", 73, 3230),
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
    # Finance lines before 2016-17. Tables 9.7 to 9.12 less the 167 restated cells:
    # Tables 9.7 to 9.9's 'All ISA Holders' columns (48, 66 and 15), and the
    # all-sexes, all-ages and United Kingdom rows of Tables 9.8, 9.9 (5 each, after
    # that column), 9.11 and 9.12 (14 each).
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
        ("table9_7", "survey_aggregate", "hmrc.isa_holders"): 48,
        ("table9_8", "survey_aggregate", "hmrc.isa_subscribers"): 260,
        ("table9_8", "survey_aggregate", "hmrc.isa_holders"): 65,
        ("table9_9", "survey_aggregate", "hmrc.isa_subscribers"): 56,
        ("table9_9", "survey_aggregate", "hmrc.isa_holders"): 14,
        ("table9_10", "survey_aggregate", "hmrc.isa_holders"): 624,
        ("table9_10", "survey_aggregate", "hmrc.isa_mean_market_value_per_holder"): 48,
        ("table9_11", "survey_aggregate", "hmrc.isa_holders"): 845,
        ("table9_11", "survey_aggregate", "hmrc.isa_mean_market_value_per_holder"): 65,
        ("table9_12", "survey_aggregate", "hmrc.isa_holders"): 182,
        ("table9_12", "survey_aggregate", "hmrc.isa_mean_market_value_per_holder"): 14,
        ("table9_12", "model_output", "hmrc.isa_holders_share_of_adults"): 14,
    }
    # Tables 9.7 to 9.12 count people under '(thousands)' headings: unscaled.
    assert _value(isa_facts, "table9_7.ty2023.all.subscribers", "all", "all_subscriptions") == 13054561
    assert _value(isa_facts, "table9_10.ty2023.all", "all", "all_holders") == 23025972
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
                    # Restates Table 9.10's 'Total' column, which is ported.
                    key = (f"table9_10.ty2023.{isa_type}", "all_holders")
                else:
                    key = (f"{record_set}.subscribers", _money_id("subscription", header))
                assert _value(isa_facts, key[0], row, key[1]) == sheet.iloc[start + offset, column]
                checked += 1
    assert checked == 4 * 12 * 14 == 4 * 12 + sum(
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
            held = _value(isa_facts, f"table9_10.ty2023.{isa_type}", row, "all_holders")
            idle = _value(isa_facts, f"{record_set}.holders", row, "no_further_subscription")
            assert abs(subscribed + idle - held) <= 2, (isa_type, row)
    # The four blocks partition the 13.05 million subscribers, 28.8% at GBP 20,000.
    total = _value(isa_facts, "table9_7.ty2023.all.subscribers", "all", "all_subscriptions")
    full = _value(isa_facts, "table9_7.ty2023.all.subscribers", "all", "subscription_20000_to_20000")
    assert round(full / total, 3) == 0.288


def _row(sheet: pd.DataFrame, label: str, column: int = 0) -> int:
    labels = sheet.iloc[:, column].astype(str).str.strip()
    (row,) = labels.index[labels == label]
    return row


def _column(sheet: pd.DataFrame, header_row: int, text: str) -> int:
    (column,) = [i for i, h in enumerate(sheet.iloc[header_row]) if str(h).startswith(text)]
    return column


def test_restated_cells_are_ported_once(isa_facts, isa_sheets):
    """Tables 9.7 to 9.12 print some totals more than once. Each is one fact, and the
    workbook's other copies, found by label, equal it."""
    keys = Counter(build_semantic_fact_key(fact) for fact in isa_facts.values())
    assert max(keys.values()) == 1
    t98 = isa_sheets["9_8_ISA_subs_by_age_sex"]
    t99 = isa_sheets["9_9_ISA_subs_by_country_region"]
    t911 = isa_sheets["9_11ISA_market_value_by_age_sex"]
    t912 = isa_sheets["9_12ISA_market_values_by_region"]
    # Table 9.8's all-sexes 'Total' row and Table 9.9's United Kingdom row restate
    # Table 9.7's 'All ranges' rows and Table 9.10's holders.
    national = [
        *(
            _value(isa_facts, f"table9_7.ty2023.{t}.subscribers", "all", "all_subscriptions")
            for t in (*TYPES, "all")
        ),
        _value(isa_facts, "table9_7.ty2023.all.holders", "all", "no_further_subscription"),
        _value(isa_facts, "table9_10.ty2023.all", "all", "all_holders"),
    ]
    assert list(t98.iloc[_row(t98, "Total"), 1:7]) == national
    assert list(t99.iloc[_row(t99, "United Kingdom", 1), 2:8]) == national
    # Table 9.11's all-sexes 'Total' row and Table 9.12's United Kingdom row restate
    # Table 9.10's 'All ranges' row for all ISA types.
    for sheet, header_row, row in (
        (t911, _row(t911, "Market Value"), _row(t911, "Total")),
        (t912, _row(t912, "Area Code"), _row(t912, "United Kingdom", 1)),
    ):
        checked = 0
        for column, header in enumerate(sheet.iloc[header_row].astype(str)):
            if header.startswith("£"):
                measure = _money_id("market_value", header)
            elif header.startswith("Total"):
                measure = "all_holders"
            elif header.startswith("Average"):
                measure = "average_market_value"
            else:
                continue
            ported = _value(isa_facts, "table9_10.ty2023.all", "all", measure)
            assert sheet.iloc[row, column] == ported, header
            checked += 1
        assert checked == 14
    # Tables 9.8 and 9.9's 'All ISA Holders' columns restate Tables 9.11 and 9.12's
    # 'Total' columns row for row (Table 9.7's is checked by label above).
    for left, left_header, right, right_header, label_column, count in (
        (t98, "Type of ISA", t911, "Market Value", 0, 3 * 22),
        (t99, "Area Code", t912, "Area Code", 1, 15),
    ):
        start = _row(left, left_header)
        held = _column(left, start, "All ISA Holders")
        total = _column(right, _row(right, right_header), "Total")
        rows = [
            (row, _row(right, label.strip(), label_column))
            for row, label in left.iloc[start + 1 :, label_column].astype(str).items()
            if pd.notna(left.iloc[row, held])
        ]
        assert len(rows) == count
        assert all(left.iloc[a, held] == right.iloc[b, total] for a, b in rows)
    # The copies carry no fact; Table 9.12's United Kingdom share of adults stays.
    for record_id in (
        "table9_7.ty2023.cash_only.holders.all.all_holders",
        "table9_8.ty2023.male.holders.age_under_24.all_holders",
        "table9_8.ty2023.all.subscribers.all.all_subscribers",
        "table9_8.ty2023.all.holders.all.no_further_subscription",
        "table9_9.ty2023.subscribers.K02000001.cash_only_subscribers",
        "table9_9.ty2023.holders.E12000001.all_holders",
        "table9_11.ty2023.all.all.market_value_1_to_2499",
        "table9_12.ty2023.K02000001.average_market_value",
    ):
        assert f"{PREFIX}.{record_id}" not in isa_facts, record_id
    assert f"{PREFIX}.table9_12.ty2023.share_of_adults.K02000001.share_of_adults" in isa_facts


def test_tables_9_8_and_9_9_add_up_to_table_9_7(isa_facts):
    for isa_type in TYPES:
        persons = _value(isa_facts, f"table9_7.ty2023.{isa_type}.subscribers", "all", "all_subscriptions")
        male = _value(isa_facts, "table9_8.ty2023.male.subscribers", "all", f"{isa_type}_subscribers")
        female = _value(isa_facts, "table9_8.ty2023.female.subscribers", "all", f"{isa_type}_subscribers")
        assert abs(male + female - persons) <= 2
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
    uk = _value(isa_facts, "table9_7.ty2023.all.subscribers", "all", "all_subscriptions")
    assert abs(countries - uk) <= 5


def test_age_bands_cover_the_published_rows(isa_facts):
    persons = [
        fact
        for fact in isa_facts.values()
        if fact.source_record_id.startswith(f"{PREFIX}.table9_8.ty2023.all.subscribers.")
        and fact.source_record_id.endswith(".all_subscribers")
    ]
    # The all-ages row restates Table 9.7's total, which is ported from Table 9.7.
    assert len(persons) == 21
    bands = sum(fact.value for fact in persons)
    total = _value(isa_facts, "table9_7.ty2023.all.subscribers", "all", "all_subscriptions")
    assert abs(bands - total) <= 21
    under_24 = next(fact for fact in persons if fact.filters["age_band"] == "age_under_24")
    assert [(c.variable, c.operator, c.value) for c in under_24.constraints if c.variable == "age"] == [
        ("age", "<", 24)
    ]


def test_the_docs_arithmetic_on_tables_9_4_and_9_7(isa_facts):
    """The two caveats the docs page states from the cells (not stored as facts)."""

    def subscribers(isa_type: str, measure: str = "all_subscriptions") -> float:
        return _value(isa_facts, f"table9_7.ty2023.{isa_type}.subscribers", "all", measure)

    def at_floors(isa_type: str) -> float:
        """Subscribers in each band times the band's floor ('subscription_2001_to_4000')."""
        prefix = f"{PREFIX}.table9_7.ty2023.{isa_type}.subscribers.all.subscription_"
        bands = {
            int(record_id.removeprefix(prefix).split("_")[0]): fact.value
            for record_id, fact in isa_facts.items()
            if record_id.startswith(prefix)
        }
        assert len(bands) == 11
        return sum(floor * count for floor, count in bands.items())

    accounts = {
        component: _value(isa_facts, "table9_4.accounts.ty2023", component, "accounts")
        for component in ("cash", "stocks_and_shares", "lifetime")
    }
    amounts = {
        component: _value(isa_facts, "table9_4.amounts.ty2023", component, "amounts")
        for component in ("cash", "stocks_and_shares", "all")
    }
    # Table 9.7's bands at their floors against Table 9.4's amounts subscribed.
    assert round(at_floors("all") / 1e9, 1) == 114.3
    assert round(at_floors("cash_only") / 1e9, 1) == 78.1
    assert (amounts["cash"], amounts["stocks_and_shares"]) == (69498e6, 31070e6)
    assert at_floors("cash_only") > amounts["cash"]
    assert at_floors("all") > amounts["all"] == 102995e6
    # Lifetime ISAs: the cash and stocks and shares people match Table 9.4's accounts.
    cash, shares, both = (subscribers(t) for t in TYPES)
    assert cash + shares + both == subscribers("all") == 13054561
    assert round(cash + both, -3) == accounts["cash"] == 9939000
    assert round(shares + both, -3) == accounts["stocks_and_shares"] == 4091000
    assert accounts["lifetime"] == 964000


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


HELP_TO_BUY = (
    "'Help to Buy: ISAs are included within these statistics under cash subscriptions "
    "and market values, but the information is not separated out.'"
)


def test_notes_roles_and_universes(isa_facts):
    """Help to Buy ISAs are inside cash (methodology section 3.4) from 2015-16, when the
    scheme opened; Table 9.4 counts accounts; each '(thousands)' note cites the
    commentary's count for its measure; Table 9.12's share is of adults."""
    by_concept = Counter()
    for record_id, fact in isa_facts.items():
        table = record_id.split(".")[2]
        concept = fact.measure.concept
        notes = fact.measure.concept_evidence_notes
        by_concept[(concept, fact.entity.role)] += 1
        if table in ("table9_4", "table9_6"):
            assert (HELP_TO_BUY in notes) == (fact.period.value >= 2015), record_id
        else:
            assert HELP_TO_BUY in notes, record_id
        assert "13.05 million" not in notes
        if concept == "hmrc.isa_subscribers":
            assert "15 million Adult ISA accounts subscribed to and 23 million" in notes
        elif concept == "hmrc.isa_holders":
            assert "gives 23 million Adult ISA holders in 2023 to 2024" in notes
            assert "individuals subscribing" not in notes
        elif concept == "hmrc.isa_mean_market_value_per_holder":
            assert "'(thousands)'" not in notes
        elif concept == "hmrc.isa_holders_share_of_adults":
            ages = [(c.variable, c.operator, c.value) for c in fact.constraints if c.variable == "age"]
            assert ages == [("age", ">=", 18)]
    assert by_concept == {
        ("hmrc.isa_accounts_subscribed", "isa_account"): 85,
        ("hmrc.isa_amount_subscribed", "isa_account"): 85,
        ("hmrc.isa_market_value", "isa_holder"): 249,
        ("hmrc.isa_subscribers", "isa_subscriber"): 892,
        ("hmrc.isa_holders", "isa_holder"): 1778,
        ("hmrc.isa_mean_market_value_per_holder", "isa_holder"): 127,
        ("hmrc.isa_holders_share_of_adults", "isa_holder"): 14,
    }


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
    for band, fact in shares.items():
        assert fact.provenance_class == "model_output"
        assert fact.period.value == 2022
        # The sentence places no subscription of exactly GBP 12,000, so each row
        # carries its band and no amount bound.
        assert {(c.variable, c.operator, c.value) for c in fact.constraints} == {
            ("isa_type", "==", "cash"),
            ("age", "<", 65),
            ("cash_isa_subscription_band", "==", band),
        }
