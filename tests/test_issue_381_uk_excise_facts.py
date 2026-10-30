"""Regression tests for the chronicle#381 excise facts behind PolicyEngine/microcosm#1359.

- OBR EFO March 2026 receipts: sheet 3.8's alcohol, tobacco, and betting and gaming
  duties and vaping tax (cash basis); sheet 3.10's betting and gaming duties by duty
  (accrued); sheet 3.11's tobacco clearances; sheet 3.12's alcohol clearances and
  accrued alcohol receipts; sheet 3.2's three gambling lines.
- HMRC Alcohol Bulletin and Tobacco Bulletin tables of 28 August 2026.
- HMRC UK Betting and Gaming Statistics tables of 30 September 2026.
- Gambling Commission Industry Statistics, annual report of 17 September 2026.
- ONS Consumer Trends, the 30 September 2026 release, which supersedes the 30 June one.

Values are the publishers' as fetched on 2026-10-23.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import pytest

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import (
    build_semantic_fact_key,
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.dimension_labels import dimension_label_issues
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package
from chronicle.sources.cells import (
    SourceArtifactMetadata,
    build_source_cell_key,
    source_cells_from_xlsx,
)

RECEIPTS = "obr-efo-receipts-march-2026"
ALCOHOL = "hmrc-alcohol-bulletin-july-2026"
TOBACCO = "hmrc-tobacco-bulletin-july-2026"
BETTING = "hmrc-betting-gaming-statistics-july-2026"
GAMBLING = "gambling-commission-industry-statistics-fy2025-26"
TRENDS_JUNE = "ons-consumer-trends-current-price-2026"
TRENDS_JUNE_ARTIFACT = Path("db/data/ons/consumer_trends_current_price_2026/cpnsa.xlsx")
TRENDS_SEPTEMBER = "ons-consumer-trends-current-price-september-2026"
NEW_PACKAGES = {
    ALCOHOL: 288,
    TOBACCO: 710,
    BETTING: 376,
    GAMBLING: 1435,
    TRENDS_SEPTEMBER: 5164,
}
OBR_PREFIX = "obr.efo_2026_03.receipts."


@pytest.fixture(scope="module")
def facts():
    return {
        alias: load_source_package(alias).build_facts(2026) for alias in NEW_PACKAGES
    }


@pytest.fixture(scope="module")
def receipts():
    package = load_source_package(RECEIPTS)
    cells = package.build_source_cells(2026)
    return cells, package.build_facts(2026, cells=cells)


def one(facts, **expected):
    """The one fact whose attributes and dimensions match ``expected``."""
    matches = [
        fact
        for fact in facts
        if all(
            (
                fact.measure.concept
                if key == "concept"
                else fact.period.value
                if key == "period"
                else fact.period.type
                if key == "period_type"
                else fact.filters.get(key)
            )
            == value
            for key, value in expected.items()
        )
    ]
    assert len(matches) == 1, (expected, len(matches))
    return matches[0]


@pytest.mark.parametrize("alias", sorted(NEW_PACKAGES))
def test_packages_are_registered_valid_and_labelled(alias, facts):
    assert alias in SOURCE_PACKAGE_ALIASES
    assert alias in UK_BUNDLE_SOURCES
    built = facts[alias]
    assert len(built) == NEW_PACKAGES[alias]
    assert validate_facts(built).valid
    assert validate_consumer_fact_contract(built).valid
    assert all(fact.source_cell_keys for fact in built)
    assert all(fact.period_coverage is not None for fact in built)
    issues = dimension_label_issues(consumer_fact_rows(built))
    # The ONS overview and detailed sheets word some divisions differently; the
    # package keeps the publisher's text.
    errors = [i for i in issues if i.code != "conflicting_groupby_value_label"]
    assert not errors, [issue.to_dict() for issue in errors]
    # One set of dimension values names one cell.
    keys = Counter(build_semantic_fact_key(fact) for fact in built)
    assert max(keys.values()) == 1


def test_obr_excise_lines(receipts):
    _cells, built = receipts
    new = [f for f in built if f.period_coverage is not None]
    assert len(built) == 280 and len(new) == 182
    lines = Counter(f.layout.record_set_id.split(".")[3] for f in new)
    assert lines == {
        **{
            line: 7
            for line in (
                "tobacco_duties",
                "spirits_duties",
                "wine_duties",
                "beer_and_cider_duties",
                "betting_and_gaming_duties",
                "vaping_tax",
                "cigarette_clearances",
                "non_cigarette_tobacco_clearances",
                "hand_rolled_tobacco_clearances",
                "other_tobacco_products_clearances",
                "beer_and_cider_clearances",
                "wine_clearances",
                "spirits_clearances",
                "beer_and_cider_duties_accrued",
                "wine_duties_accrued",
                "spirits_duties_accrued",
                "camelot_payments_to_national_lottery_distribution_fund",
                "horserace_betting_levy",
                "statutory_gaming_levy",
            )
        },
        **{
            line: 6
            for line in (
                "betting_and_gaming_duties_accrued",
                "remote_gaming_duty",
                "lottery_duty",
                "general_betting_duty",
                "machine_games_duty",
                "gaming_duty",
                "bingo_duty",
                "pool_betting_duty",
            )
        },
        # chronicle#395: the 2024-25 outturn only; October 2026 carries the later years.
        "vehicle_excise_duties": 1,
    }

    def line(name, year):
        (fact,) = [
            f for f in new if f.layout.record_set_id == f"{OBR_PREFIX}{name}.fy{year}"
        ]
        return fact

    # Units: clearances in base units, the published unit kept as a dimension.
    beer = line("beer_and_cider_clearances", 2024)
    assert beer.measure.unit == "litre_of_pure_alcohol"
    assert beer.value == pytest.approx(2168.2921615793966e5)
    assert beer.filters == {"published_unit": "thousand_hectolitres_of_alcohol"}
    assert line("cigarette_clearances", 2024).measure.unit == "stick"
    assert line("cigarette_clearances", 2024).value == pytest.approx(
        13578.199084269218e6
    )
    assert line("hand_rolled_tobacco_clearances", 2024).measure.unit == "kilogram"
    # One concept per duty; the accounting basis keeps cash and accrued apart.
    cash = line("beer_and_cider_duties", 2024)
    accrued = line("beer_and_cider_duties_accrued", 2024)
    assert (
        cash.measure.concept == accrued.measure.concept == "obr.beer_and_cider_duties"
    )
    assert (cash.value, accrued.value) == (3741000000, 3746000000)
    assert cash.filters == {"accounting_basis": "cash"}
    assert accrued.filters == {"accounting_basis": "accrual"}
    assert cash.period_coverage.accounting_basis == "cash"
    assert accrued.period_coverage.accounting_basis == "accrual"
    assert cash.period_coverage.start_date == "2024-04-01"
    assert line("tobacco_duties", 2024).value == 7927000000
    assert line("vaping_tax", 2025).value == 0
    assert line("statutory_gaming_levy", 2024).period_coverage.accounting_basis is None
    # Outturn 2024-25 is observed; sheet 3.10 starts at 2025-26 and is all forecast.
    assert line("tobacco_duties", 2024).assertion == "observation"
    assert line("tobacco_duties", 2025).assertion == "source_projection"
    sheet_3_10 = [
        f
        for f in new
        if f.period_coverage.source_period_label
        and lines[f.layout.record_set_id.split(".")[3]] == 6
    ]
    assert len(sheet_3_10) == 48
    assert {f.assertion for f in sheet_3_10} == {"source_projection"}
    for year in range(2024, 2031):
        assert line("non_cigarette_tobacco_clearances", year).value == pytest.approx(
            line("hand_rolled_tobacco_clearances", year).value
            + line("other_tobacco_products_clearances", year).value
        )


def test_obr_sheet_3_10_is_accrued(receipts):
    cells, built = receipts
    sheet_3_1 = {
        cell.address: cell.raw_value for cell in cells if cell.sheet_name == "3.1"
    }
    assert sheet_3_1["B7"] == "Betting and gaming taxes"
    assert sheet_3_1["B17"] == "Note: All taxes are on an accrued basis."
    duties = (
        "remote_gaming_duty",
        "lottery_duty",
        "general_betting_duty",
        "machine_games_duty",
        "gaming_duty",
        "bingo_duty",
        "pool_betting_duty",
    )
    by_id = {f.layout.record_set_id: f for f in built}
    for offset, year in enumerate(range(2025, 2031)):
        total = by_id[f"{OBR_PREFIX}betting_and_gaming_duties_accrued.fy{year}"]
        cash = by_id[f"{OBR_PREFIX}betting_and_gaming_duties.fy{year}"]
        assert total.value == pytest.approx(sheet_3_1["DEFGHI"[offset] + "7"] * 1e9)
        assert total.value != pytest.approx(cash.value)
        assert total.filters == {"accounting_basis": "accrual"}
        assert sum(
            by_id[f"{OBR_PREFIX}{duty}.fy{year}"].value for duty in duties
        ) == pytest.approx(total.value)


def test_alcohol_bulletin_clearances_by_product_and_breakdown(facts):
    built = facts[ALCOHOL]
    clearances = [f for f in built if f.measure.concept == "hmrc.alcohol_clearances"]
    assert {f.measure.unit for f in clearances} == {"litre_of_pure_alcohol"}
    totals = {
        product: one(
            clearances,
            period_type="fiscal_year",
            period=2024,
            alcohol_product=product,
            abv_band="all",
            duty_relief="all",
            duty_point="all",
        ).value
        for product in ("beer", "cider", "wine", "other_fermented_products", "spirits")
    }
    assert totals == pytest.approx(
        {
            "beer": 185277635.28381,
            "cider": 30347471.2870859,
            "wine": 152027012.448098,
            "other_fermented_products": 11971792.324352,
            "spirits": 132049510.767922,
        }
    )
    # Each breakdown partitions its product's total, every table and year.
    groups = defaultdict(float)
    for fact in clearances:
        for breakdown in ("abv_band", "duty_relief", "duty_point"):
            others = {"abv_band", "duty_relief", "duty_point"} - {breakdown}
            if fact.filters[breakdown] != "all" and all(
                fact.filters[name] == "all" for name in others
            ):
                key = (
                    fact.period.type,
                    fact.period.value,
                    fact.filters["alcohol_product"],
                    breakdown,
                )
                groups[key] += fact.value
    assert groups
    for (period_type, year, product, _breakdown), value in groups.items():
        total = one(
            clearances,
            period_type=period_type,
            period=year,
            alcohol_product=product,
            abv_band="all",
            duty_relief="all",
            duty_point="all",
        )
        assert value == pytest.approx(total.value, rel=1e-9)
    # Draught relief is published for beer and cider only.
    draught = {
        f.filters["alcohol_product"]
        for f in clearances
        if f.filters["duty_relief"] == "draught_relief_only"
    }
    assert draught == {"beer", "cider"}
    # The new regime's clearances start in August 2023; receipts cover the year.
    first = one(
        clearances,
        period_type="fiscal_year",
        period=2023,
        alcohol_product="beer",
        abv_band="all",
        duty_relief="all",
        duty_point="all",
    )
    assert first.period_coverage.start_date == "2023-08-01"
    receipts = [f for f in built if f.measure.concept == "hmrc.alcohol_duty_receipts"]
    total = one(receipts, period_type="fiscal_year", period=2023, alcohol_product="all")
    assert total.period_coverage.start_date == "2023-04-01"
    assert total.period_coverage.accounting_basis == "cash"
    assert (
        one(
            receipts, period_type="fiscal_year", period=2024, alcohol_product="all"
        ).value
        == 12615000000
    )
    assert {f.filters["alcohol_product"] for f in receipts} == {
        "beer",
        "cider",
        "wine_and_other_fermented_products",
        "spirits",
        "all",
    }
    production = [f for f in built if f.measure.concept == "hmrc.uk_beer_production"]
    assert {f.measure.unit for f in production} == {"litre", "litre_of_pure_alcohol"}


def test_tobacco_bulletin_clearances_and_receipts(facts):
    built = facts[TOBACCO]
    clearances = [f for f in built if f.measure.concept == "hmrc.tobacco_clearances"]
    cigarettes = one(
        clearances, period_type="fiscal_year", period=2024, tobacco_product="cigarettes"
    )
    assert cigarettes.measure.unit == "stick"
    assert cigarettes.value == pytest.approx(13577910633.7114)
    cigars = one(
        clearances, period_type="fiscal_year", period=2024, tobacco_product="cigars"
    )
    assert cigars.measure.unit == "kilogram"
    assert cigars.value == pytest.approx(395122.98372549296)
    by_period = defaultdict(dict)
    for fact in clearances:
        by_period[fact.period.type, fact.period.value][
            fact.filters["tobacco_product"]
        ] = fact.value
    assert len(by_period) == 36 + 35
    for products in by_period.values():
        assert products["non_cigarette_tobacco"] == pytest.approx(
            products["cigars"] + products["hand_rolling_tobacco"] + products["other"],
            rel=1e-6,
        )
    receipts = [f for f in built if f.measure.concept == "hmrc.tobacco_duty_receipts"]
    assert {f.period_coverage.accounting_basis for f in receipts} == {"cash"}
    assert one(
        receipts, period_type="fiscal_year", period=2024, tobacco_product="all"
    ).value == pytest.approx(7926528869.28)


def test_betting_and_gaming_receipts_and_mgd_liabilities(facts):
    built = facts[BETTING]
    receipts = [
        f for f in built if f.measure.concept == "hmrc.betting_and_gaming_duty_receipts"
    ]
    year = {
        f.filters["gambling_duty"]: f.value for f in receipts if f.period.value == 2024
    }
    assert year == {
        "general_betting_duty": 713858000,
        "pool_betting_duty": 8125000,
        "betting_total": 721983000,
        "gaming_duty": 165397000,
        "remote_gaming_duty": 1162539000,
        "bingo_duty": 25233000,
        "machine_games_duty": 609245000,
        "lottery_duty": 931887000,
        "all": 3616284000,
    }
    assert (
        year["betting_total"]
        == year["general_betting_duty"] + year["pool_betting_duty"]
    )
    assert year["all"] == sum(
        value for duty, value in year.items() if duty not in ("all", "betting_total")
    )
    # '[No Data]' cells emit no fact: Remote Gaming Duty starts in 2015-16.
    remote = sorted(
        f.period.value
        for f in receipts
        if f.filters["gambling_duty"] == "remote_gaming_duty"
    )
    assert remote[0] == 2015
    liabilities = [
        f for f in built if f.measure.concept == "hmrc.machine_games_duty_liabilities"
    ]
    revised = one(liabilities, period=2024, mgd_rate="all")
    assert revised.value == 612266000
    assert revised.period_coverage.source_period_label == "2024 to 2025 [revised]"
    assert revised.period_coverage.accounting_basis is None


def test_gambling_commission_ggy_and_lotteries(facts):
    built = facts[GAMBLING]
    # Great Britain, as the publication describes itself, the lottery included.
    assert {f.geography.id for f in built} == {"K03000001"}
    lottery = [
        f for f in built if f.filters.get("gambling_sector") == "national_lottery"
    ]
    assert len(lottery) == 160
    ggy = [
        f
        for f in built
        if f.measure.concept == "gambling_commission.gross_gambling_yield"
    ]

    def sector(name, year=2024, **dims):
        values = {"gambling_activity": "all", "betting_event": "all", **dims}
        return one(ggy, period=year, gambling_sector=name, **values).value

    sectors = (
        "arcades_non_remote",
        "betting_non_remote",
        "bingo_non_remote",
        "casino_non_remote",
        "betting_remote",
        "bingo_remote",
        "casino_remote",
    )
    assert sector("all") == pytest.approx(16727.655237e6)
    assert sector("all_excluding_lotteries") == pytest.approx(
        sum(sector(name) for name in sectors), rel=1e-9
    )
    assert sector("all") == pytest.approx(
        sector("all_excluding_lotteries")
        + sector("lotteries")
        + sector("national_lottery"),
        rel=1e-9,
    )
    # Remote betting splits two ways: by type and by event.
    by_type = sum(
        f.value
        for f in ggy
        if f.period.value == 2024
        and f.filters["gambling_sector"] == "betting_remote"
        and f.filters["gambling_activity"] != "all"
    )
    by_event = sum(
        f.value
        for f in ggy
        if f.period.value == 2024
        and f.filters["gambling_sector"] == "betting_remote"
        and f.filters["betting_event"] != "all"
    )
    assert by_type == pytest.approx(sector("betting_remote"), rel=1e-6)
    assert by_event == pytest.approx(sector("betting_remote"), rel=1e-6)
    sales = [
        f for f in built if f.measure.concept == "gambling_commission.lottery_sales"
    ]
    total = one(
        sales, period=2024, gambling_sector="national_lottery", sales_channel="all"
    )
    parts = sum(
        f.value
        for f in sales
        if f.period.value == 2024
        and f.filters["gambling_sector"] == "national_lottery"
        and f.filters["sales_channel"] != "all"
    )
    assert parts == pytest.approx(total.value, rel=1e-9)
    # Provisional and revised years keep the publisher's marker.
    labels = {
        f.period.value: f.period_coverage.source_period_label
        for f in ggy
        if f.layout.record_set_id.endswith(".sheet_1.fy" + str(f.period.value))
    }
    assert labels[2024] == "Apr 2024 - Mar 2025R"
    assert labels[2025] == "Apr 2025 - Mar 2026P"
    # Machine categories change on 1 July 2024: B1 to B4 before, B after.
    machines = [
        f
        for f in built
        if f.measure.concept
        == "gambling_commission.gaming_machine_gross_gambling_yield"
    ]
    categories = defaultdict(set)
    for fact in machines:
        categories[fact.period.value].add(fact.filters["machine_category"])
    assert "b1" in categories[2023] and "b" not in categories[2023]
    assert "b" in categories[2024] and "b1" not in categories[2024]


def test_consumer_trends_september_edition_supersedes_june(facts):
    september = facts[TRENDS_SEPTEMBER]
    root = Path(__file__).resolve().parents[1]
    # The 30 June edition is retired: no package, no export; its bytes stay.
    assert TRENDS_JUNE not in SOURCE_PACKAGE_ALIASES
    assert TRENDS_JUNE not in UK_BUNDLE_SOURCES
    assert (root / TRENDS_JUNE_ARTIFACT.parent / "manifest.yaml").is_file()
    assert {f.source.vintage for f in september} == {"2026_09_30_release_2026_q2"}
    # The June record sets: their spec ids, under new record-set ids.
    assert {f.layout.record_set_spec_id.split(".")[1] for f in september} == {
        "consumer_trends"
    }
    assert {f.layout.record_set_id.split(".")[1] for f in september} == {
        "consumer_trends_2026_09"
    }

    june_cells = {
        (cell.sheet_name, cell.address): cell.raw_value
        for cell in source_cells_from_xlsx(
            (root / TRENDS_JUNE_ARTIFACT).read_bytes(),
            SourceArtifactMetadata(
                source_name="ons",
                source_table="x",
                source_file="cpnsa.xlsx",
                url=None,
                vintage="x",
                sha256="0",
                size_bytes=0,
                extracted_at="x",
                extraction_method="x",
            ),
        )
    }
    package = load_source_package(TRENDS_SEPTEMBER)
    cells = package.build_source_cells(2026)
    by_key = {build_source_cell_key(cell): cell for cell in cells}

    # The revisions chronicle#381 cites, calendar 2024, GBP million: the same cell
    # in each release.
    for code, sheet, before, after in (
        ("02.1", "02CN", 28097, 27058),
        ("02.2", "02CN", 19989, 17102),
        ("09.4.3", "09CN", 11093, 12828),
        ("07.2.2", "07CN", 37025, 35460),
    ):
        fact = one(
            september,
            period_type="calendar_year",
            period=2024,
            coicop=code,
            source_sheet=sheet,
        )
        assert fact.value == after * 1_000_000
        (value_cell,) = [
            by_key[key]
            for key in fact.source_cell_keys
            if by_key[key].row_number == 36 and isinstance(by_key[key].raw_value, int)
        ]
        assert june_cells[sheet, value_cell.address] == before
    # ONS relabelled the national total's code NAT0 to NAT; the series is the same.
    national = [f for f in september if f.filters.get("coicop") == "NAT0"]
    assert national and {f.filters["cdid"] for f in national} == {"ABPB"}


def test_gambling_commission_leaves_out_zeros_that_are_not_measurements(facts):
    built = facts[GAMBLING]
    turnover = [f for f in built if f.measure.concept == "gambling_commission.turnover"]
    # Turnover the Commission reports as zero in every year: none is emitted.
    for sector, activity in (
        ("bingo_non_remote", "gaming_machines"),
        ("casino_remote", "poker_peer_to_peer"),
        ("betting_remote", "betting_exchange"),
    ):
        assert not [
            f
            for f in turnover
            if f.filters["gambling_sector"] == sector
            and f.filters["gambling_activity"] == activity
        ]
    # Their GGY is published, and kept.
    ggy = [
        f
        for f in built
        if f.measure.concept == "gambling_commission.gross_gambling_yield"
    ]
    assert (
        one(
            ggy,
            period=2024,
            gambling_sector="bingo_non_remote",
            gambling_activity="gaming_machines",
            betting_event="all",
        ).value
        > 0
    )
    # Betting-shop machine turnover is '-' in every year but 2024-25 and 2025-26,
    # whose zeros sit over quarters that are all '-': none is emitted, and the
    # machines' GGY is.
    assert not [
        f
        for f in turnover
        if f.filters["gambling_activity"] == "off_course_gaming_machines"
    ]
    assert (
        one(
            ggy,
            period=2025,
            gambling_sector="betting_non_remote",
            gambling_activity="off_course_gaming_machines",
            betting_event="all",
        ).value
        > 0
    )
    # 2008-09's National Lottery sales carry no channel split.
    sales = [
        f for f in built if f.measure.concept == "gambling_commission.lottery_sales"
    ]
    first = [
        f
        for f in sales
        if f.period.value == 2008 and f.filters["gambling_sector"] == "national_lottery"
    ]
    assert {f.filters["sales_channel"] for f in first} == {"all"}


def test_gambling_commission_notes_the_remote_regime_and_lottery_geography(facts):
    built = facts[GAMBLING]
    notes = {
        f.period.value: f.period_coverage.notes or ""
        for f in built
        if ".sheet_1.fy" in f.layout.record_set_id
    }
    for year in range(2008, 2014):
        assert "before the November 2014 legislation" in notes[year]
    assert "span the November 2014 legislation" in notes[2014]
    assert "November 2014" not in notes[2015]
    total = one(
        [f for f in built if ".sheet_1.fy" in f.layout.record_set_id],
        period=2024,
        gambling_sector="all",
    )
    assert total.geography.id == "K03000001"
    assert "includes the National Lottery" in total.measure.concept_evidence_notes


def test_gambling_commission_lottery_keeps_the_publication_geography(facts):
    # The workbook describes Great Britain, and the lottery's facts say so, along
    # with the Commission's UK-wide remit over the National Lottery.
    cells = load_source_package(GAMBLING).build_source_cells(2026)
    (preface,) = [c for c in cells if (c.sheet_name, c.address) == ("0", "B40")]
    assert "the gambling industry in Great Britain" in preface.raw_value
    for fact in facts[GAMBLING]:
        assert fact.geography.id == "K03000001"
        notes = fact.measure.concept_evidence_notes
        if fact.filters.get("gambling_sector") == "national_lottery":
            assert "Geography: Great Britain, as the workbook's preface" in notes
            assert "regulates the National Lottery across the United Kingdom" in notes
            assert "/about-us/guide/what-we-regulate" in notes
            assert "whether it includes Northern Ireland" in notes


def test_tobacco_part_years_start_with_the_monthly_tables(facts):
    built = facts[TOBACCO]
    starts = {
        (
            f.layout.record_set_id.split(".")[2],
            f.period.type,
            f.period.value,
        ): f.period_coverage.start_date
        for f in built
    }
    assert starts["clearances", "fiscal_year", 1990] == "1991-01-01"
    assert starts["receipts", "fiscal_year", 1990] == "1991-02-01"
    assert starts["receipts", "calendar_year", 1991] == "1991-02-01"
    assert starts["clearances", "calendar_year", 1991] == "1991-01-01"
    assert starts["clearances", "fiscal_year", 1991] == "1991-04-01"
    narrowed = {
        key
        for key, start in starts.items()
        if start not in (f"{key[2]}-04-01", f"{key[2]}-01-01")
    }
    assert narrowed == {
        ("clearances", "fiscal_year", 1990),
        ("receipts", "fiscal_year", 1990),
        ("receipts", "calendar_year", 1991),
    }


def test_beer_production_carries_the_imputation_note(facts):
    built = facts[ALCOHOL]
    noted = {
        (f.period.type, f.period.value)
        for f in built
        if f.measure.concept == "hmrc.uk_beer_production"
        and "partly on imputed data" in (f.period_coverage.notes or "")
    }
    assert noted == {
        ("fiscal_year", 2024),
        ("calendar_year", 2024),
        ("calendar_year", 2025),
    }
