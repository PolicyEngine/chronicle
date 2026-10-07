"""Council-tax nation-level billed/collectable totals and CTR cost packages.

Nine UK source packages carry the publisher amounts the policyengine-uk-data#448
council-tax diagnosis compared the model against: Scottish Government council
tax collection statistics (CTRR, two vintages), the SLGFS 2024-25 council-tax
tables (CTR funding and reduction in liability, income after CTR, potential
yield by band, average bill before and after CTR), Welsh Government council
tax collection rates (two vintages) and Council Tax Reduction Scheme annual
reports (total value of awards, two vintages), and MHCLG's England council tax
levels summary and collection-rates tables. Every oracle below is the publisher's
stored cell times the declared value_scale; the comparators quoted in the
diagnosis are the rounded display values of the same cells.
"""

from __future__ import annotations

import pytest

from chronicle.source_package import load_source_package


def _facts(alias: str, year: int):
    package = load_source_package(alias)
    rows = package.build_source_rows(year)
    cells = package.build_source_cells(year, source_rows=rows)
    return package.build_facts(year, cells=cells, source_rows=rows)


def _value(facts, concept: str, period, filters: dict | None = None):
    matches = [
        fact
        for fact in facts
        if fact.measure.concept == concept
        and fact.period.value == period
        and (filters is None or fact.filters == filters)
    ]
    assert len(matches) == 1, (concept, period, filters, len(matches))
    return matches[0].value


def _assert_shape(facts, *, geography_id: str, period_type: str):
    assert {fact.geography.id for fact in facts} == {geography_id}
    assert {fact.geography.level for fact in facts} == {"country"}
    assert {fact.period.type for fact in facts} == {period_type}
    assert {fact.assertion for fact in facts} == {"observation"}
    assert {fact.provenance_class for fact in facts} == {"administrative"}
    assert all(fact.source.raw_r2_uri for fact in facts)
    assert all(fact.source_cell_keys for fact in facts)


def test_scotgov_council_tax_collection_2025_26_figure_1_scotland_rows():
    facts = _facts("scotgov-council-tax-collection-2025-26", 2026)
    # 27 billing years (1999-00 to 2025-26) x 4 published columns.
    assert len(facts) == 108
    _assert_shape(facts, geography_id="S92000003", period_type="fiscal_year")
    assert {fact.period.value for fact in facts} == set(range(1999, 2026))
    assert {fact.entity.name for fact in facts} == {"government"}
    assert {fact.entity.role for fact in facts} == {"billing_authority"}

    # Headline 2025-26 row: GBP 3.389bn billed net of CTR, GBP 3.227bn received
    # by 31 March 2026 (the publisher displays 3,388,884 / 3,226,613 thousand).
    billed = _value(facts, "scotgov.council_tax.net_amount_billed", 2025)
    received = _value(facts, "scotgov.council_tax.amount_received", 2025)
    uncollected = _value(facts, "scotgov.council_tax.amount_uncollected", 2025)
    share = _value(facts, "scotgov.council_tax.percentage_received", 2025)
    assert repr(billed) == "3388883606.00916"
    assert repr(received) == "3226613159.306509"
    assert repr(uncollected) == "162270446.7026512"
    assert repr(share) == "0.9521168427222129"
    assert billed - received == pytest.approx(uncollected, abs=1e-3)
    assert received / billed == pytest.approx(share, abs=1e-12)

    # This vintage restates 2024-25 as at 31 March 2026.
    assert repr(_value(facts, "scotgov.council_tax.net_amount_billed", 2024)) == (
        "3072918966.350784"
    )
    assert repr(_value(facts, "scotgov.council_tax.net_amount_billed", 1999)) == (
        "1242900980.5556805"
    )
    units = {fact.measure.concept: fact.measure.unit for fact in facts}
    assert units == {
        "scotgov.council_tax.net_amount_billed": "gbp",
        "scotgov.council_tax.amount_received": "gbp",
        "scotgov.council_tax.amount_uncollected": "gbp",
        "scotgov.council_tax.percentage_received": "share",
    }
    shares = [
        fact.value
        for fact in facts
        if fact.measure.concept == "scotgov.council_tax.percentage_received"
    ]
    assert all(0.9 < value < 1.0 for value in shares)


def test_scotgov_council_tax_collection_2024_25_is_the_in_year_vintage():
    facts = _facts("scotgov-council-tax-collection-2024-25", 2025)
    # 26 billing years (1999-00 to 2024-25) x 4 published columns.
    assert len(facts) == 104
    _assert_shape(facts, geography_id="S92000003", period_type="fiscal_year")
    assert {fact.period.value for fact in facts} == set(range(1999, 2025))

    # Provisional in-year 2024-25 figures as at 31 March 2025: GBP 3.077bn
    # billed, GBP 2.938bn received, 95.5 per cent.
    assert repr(_value(facts, "scotgov.council_tax.net_amount_billed", 2024)) == (
        "3076769837.571812"
    )
    assert repr(_value(facts, "scotgov.council_tax.amount_received", 2024)) == (
        "2938384738.902261"
    )
    assert repr(_value(facts, "scotgov.council_tax.percentage_received", 2024)) == (
        "0.9550226029325727"
    )
    assert repr(_value(facts, "scotgov.council_tax.net_amount_billed", 1999)) == (
        "1243499648.216659"
    )


def test_scotgov_council_tax_collection_vintages_differ_by_source_table():
    later = _facts("scotgov-council-tax-collection-2025-26", 2026)
    earlier = _facts("scotgov-council-tax-collection-2024-25", 2025)
    later_2024 = _value(later, "scotgov.council_tax.net_amount_billed", 2024)
    earlier_2024 = _value(earlier, "scotgov.council_tax.net_amount_billed", 2024)
    # Same billing year, restated in the later vintage: both publisher facts
    # are carried and a consumer distinguishes them by source_table.
    assert later_2024 != earlier_2024
    assert {fact.source.source_table for fact in later} != {
        fact.source.source_table for fact in earlier
    }


def test_scotgov_slgfs_2024_25_council_tax_tables():
    facts = _facts("scotgov-slgfs-council-tax-2024-25", 2026)
    # Table 2.11 (2) + Table 2.8 (1) + Table 2.6 (4) + Chart 2.7 (6 x 9)
    # + Table 2.10 (5 x 2).
    assert len(facts) == 71
    _assert_shape(facts, geography_id="S92000003", period_type="fiscal_year")

    # Table 2.11, Scotland row: CTR reduction in liability GBP 389,010
    # thousand (the GBP 389m comparator) and CTR funding GBP 351,000 thousand,
    # whose cell the publisher stores as 350999.99999999977.
    reduction = _value(
        facts, "scotgov.council_tax_reduction.reduction_in_liability", 2024
    )
    funding = _value(
        facts, "scotgov.council_tax_reduction.funding_from_scottish_government", 2024
    )
    assert reduction == 389_010_000
    assert isinstance(reduction, int)
    assert repr(funding) == "350999999.99999976"
    # Table 2.8, Scotland row: council tax income after CTR; Table 2.6 carries
    # the same measure for the four earlier years (GBP millions).
    assert _value(facts, "scotgov.council_tax.income_after_ctr", 2024) == (
        2_996_849_000
    )
    assert {
        fact.period.value: fact.value
        for fact in facts
        if fact.measure.concept == "scotgov.council_tax.income_after_ctr"
    } == {
        2020: 2_581_475_000,
        2021: 2_640_123_000,
        2022: 2_766_633_000,
        2023: 2_930_953_000,
        2024: 2_996_849_000,
    }

    # Chart 2.7: CTR total GBP 390.3m and its Band A share; the gross
    # potential row equals the five components for every band column.
    ctr_total = _value(
        facts,
        "scotgov.council_tax_potential_yield.total",
        2024,
        {"potential_yield_component": "council_tax_reduction"},
    )
    ctr_band_a = _value(
        facts,
        "scotgov.council_tax_potential_yield.band_a",
        2024,
        {"council_tax_band": "A", "potential_yield_component": "council_tax_reduction"},
    )
    assert repr(ctr_total) == "390302659.96999997"
    assert repr(ctr_band_a) == "129880248.40302114"
    components = (
        "council_tax_billed_estimate",
        "council_tax_reduction",
        "single_person_discount",
        "exempt_dwellings",
        "other_discounts",
    )
    for band in "ABCDEFGH":
        concept = f"scotgov.council_tax_potential_yield.band_{band.lower()}"
        gross = _value(
            facts,
            concept,
            2024,
            {"council_tax_band": band, "potential_yield_component": "gross_potential_council_tax"},
        )
        parts = sum(
            _value(
                facts,
                concept,
                2024,
                {"council_tax_band": band, "potential_yield_component": component},
            )
            for component in components
        )
        assert gross == pytest.approx(parts, rel=1e-9)
    gross_total = _value(
        facts,
        "scotgov.council_tax_potential_yield.total",
        2024,
        {"potential_yield_component": "gross_potential_council_tax"},
    )
    assert repr(gross_total) == "3959173987.2489443"
    chart_rows = [
        fact
        for fact in facts
        if fact.measure.concept.startswith("scotgov.council_tax_potential_yield.")
    ]
    assert len(chart_rows) == 54
    assert all(fact.constraints for fact in chart_rows)

    # Table 2.10: average bill per dwelling before and after CTR, GBP, mean.
    before = _value(facts, "scotgov.council_tax.average_bill_per_dwelling_before_ctr", 2024)
    after_2020 = _value(
        facts, "scotgov.council_tax.average_bill_per_dwelling_after_ctr", 2020
    )
    assert repr(before) == "1309.7148402647151"
    assert repr(after_2020) == "1053.1156962400614"
    averages = [
        fact
        for fact in facts
        if fact.measure.concept.startswith("scotgov.council_tax.average_bill_per_dwelling")
    ]
    assert len(averages) == 10
    assert {fact.aggregation.method for fact in averages} == {"mean"}
    assert {fact.entity.name for fact in averages} == {"dwelling"}
    assert {fact.period.value for fact in averages} == set(range(2020, 2025))


def test_scotgov_band_measure_ids_distinguish_stock_from_potential_yield():
    stock = _facts("scotgov-council-tax-bands-2025", 2025)
    potential_yield = _facts("scotgov-slgfs-council-tax-2024-25", 2026)

    stock_ids = {
        fact.layout.measure_id
        for fact in stock
        if fact.measure.concept.startswith("scotgov.chargeable_dwellings_")
    }
    potential_yield_ids = {
        fact.layout.measure_id
        for fact in potential_yield
        if fact.measure.concept.startswith("scotgov.council_tax_potential_yield.")
    }

    assert stock_ids == {
        "band_a",
        "band_b",
        "band_c",
        "band_d",
        "band_e",
        "band_f",
        "band_g",
        "band_h",
        "total",
    }
    assert potential_yield_ids == {
        "potential_yield_band_a",
        "potential_yield_band_b",
        "potential_yield_band_c",
        "potential_yield_band_d",
        "potential_yield_band_e",
        "potential_yield_band_f",
        "potential_yield_band_g",
        "potential_yield_band_h",
        "potential_yield_total",
    }
    assert stock_ids.isdisjoint(potential_yield_ids)


@pytest.mark.parametrize(
    ("alias", "year", "period", "debit", "collected", "extra_concept", "extra"),
    [
        (
            "welshgov-council-tax-collection-2025-26",
            2026,
            2025,
            2_523_751_000,
            2_403_994_830,
            "welshgov.council_tax.arrears_brought_forward",
            263_375_000,
        ),
        (
            "welshgov-council-tax-collection-2024-25",
            2025,
            2024,
            2_331_585_000,
            2_228_016_000,
            "welshgov.council_tax.prior_year_debits_credits",
            -4_650_000,
        ),
    ],
)
def test_welshgov_council_tax_collection_total_wales_row(
    alias, year, period, debit, collected, extra_concept, extra
):
    facts = _facts(alias, year)
    # Seven publisher columns of the Total Wales row; the five formula-labelled
    # columns (5, 8, 10, 11, 12) are not ported.
    assert len(facts) == 7
    _assert_shape(facts, geography_id="W92000004", period_type="fiscal_year")
    assert {fact.period.value for fact in facts} == {period}
    assert {fact.entity.role for fact in facts} == {"billing_authority"}
    assert {fact.measure.unit for fact in facts} == {"gbp"}
    assert _value(facts, "welshgov.council_tax.net_collectable_debit", period) == debit
    assert (
        _value(facts, "welshgov.council_tax.amount_collected_in_year", period)
        == collected
    )
    assert _value(facts, extra_concept, period) == extra
    assert {fact.measure.concept for fact in facts} == {
        "welshgov.council_tax.arrears_brought_forward",
        "welshgov.council_tax.prior_year_debits_credits",
        "welshgov.council_tax.arrears_collected",
        "welshgov.council_tax.arrears_written_off",
        "welshgov.council_tax.net_collectable_debit",
        "welshgov.council_tax.amount_collected_in_year",
        "welshgov.council_tax.in_year_written_off",
    }


@pytest.mark.parametrize(
    ("alias", "year", "values"),
    [
        (
            "welshgov-ctrs-annual-report-2025-26",
            2026,
            {2024: 322_938_000, 2025: 347_393_000},
        ),
        (
            "welshgov-ctrs-annual-report-2024-25",
            2025,
            {2023: 301_121_000, 2024: 322_938_000},
        ),
    ],
)
def test_welshgov_ctrs_annual_report_total_value_of_awards(alias, year, values):
    facts = _facts(alias, year)
    # Table 2 'Total value of CTRS awards in Wales', Wales row, two fiscal
    # years, read from the publisher PDF through the pdf_text_numbers parser.
    assert len(facts) == 2
    _assert_shape(facts, geography_id="W92000004", period_type="fiscal_year")
    assert {fact.measure.concept for fact in facts} == {
        "welshgov.council_tax_reduction.total_value_of_awards"
    }
    assert {fact.period.value: fact.value for fact in facts} == values
    assert all(isinstance(fact.value, int) for fact in facts)
    assert {fact.entity.role for fact in facts} == {"billing_authority"}
    assert {fact.measure.unit for fact in facts} == {"gbp"}
    assert {fact.domain for fact in facts} == {"council_tax_reduction"}


def test_mhclg_council_tax_levels_england_summary_2025_26_table_1():
    facts = _facts("mhclg-council-tax-levels-england-summary-2025-26", 2026)
    # Six publisher lines x five fiscal years (2021-22 to 2025-26).
    assert len(facts) == 30
    _assert_shape(facts, geography_id="E92000001", period_type="fiscal_year")
    assert {fact.period.value for fact in facts} == set(range(2021, 2026))

    # The GBP 44.1bn council tax requirement, the 19.3m Band D taxbase and the
    # GBP 2,280.21 average Band D quoted in the 2025-26 release.
    assert _value(facts, "mhclg.council_tax.requirement", 2025) == 44_118_104_184
    assert (
        _value(facts, "mhclg.council_tax.requirement_excluding_parish_precepts", 2025)
        == 43_259_506_797
    )
    assert _value(facts, "mhclg.council_tax.parish_precepts", 2025) == 858_597_387
    assert (
        _value(facts, "mhclg.council_tax.taxbase_band_d_equivalents", 2025)
        == 19_348_236
    )
    assert _value(facts, "mhclg.council_tax.average_band_d", 2025) == 2280.21
    assert (
        _value(facts, "mhclg.council_tax.average_band_d_excluding_parish_precepts", 2025)
        == 2235.84
    )
    assert _value(facts, "mhclg.council_tax.requirement", 2021) == 34_436_646_428

    by_concept = {}
    for fact in facts:
        by_concept.setdefault(
            fact.measure.concept,
            (fact.entity.name, fact.measure.unit, fact.aggregation.method),
        )
    assert by_concept == {
        "mhclg.council_tax.requirement_excluding_parish_precepts": ("government", "gbp", "sum"),
        "mhclg.council_tax.parish_precepts": ("government", "gbp", "sum"),
        "mhclg.council_tax.requirement": ("government", "gbp", "sum"),
        "mhclg.council_tax.taxbase_band_d_equivalents": ("dwelling", "count", "sum"),
        "mhclg.council_tax.average_band_d_excluding_parish_precepts": ("dwelling", "gbp", "mean"),
        "mhclg.council_tax.average_band_d": ("dwelling", "gbp", "mean"),
    }


def test_mhclg_council_tax_collection_england_2025_26_table_5():
    facts = _facts("mhclg-council-tax-collection-england-2025-26", 2026)
    # Two council tax amount rows x five fiscal years; the percentage-change
    # rows and the non-domestic rates rows are not ported.
    assert len(facts) == 10
    _assert_shape(facts, geography_id="E92000001", period_type="fiscal_year")
    assert {fact.period.value for fact in facts} == set(range(2021, 2026))
    assert {fact.measure.unit for fact in facts} == {"gbp"}
    assert _value(facts, "mhclg.council_tax.net_collectable_debit", 2025) == (
        44_981_384_000
    )
    assert _value(facts, "mhclg.council_tax.amount_collected_in_year", 2025) == (
        43_002_543_000
    )
    assert _value(facts, "mhclg.council_tax.net_collectable_debit", 2021) == (
        35_341_498_000
    )
