"""OBR EFO Table 4.1 (March 2026) and 5.1 (October 2026) council tax block.

Row 19 'Total net council tax receipts' (concept obr.council_tax_total) equals
row 15 'Total council tax receipts' (England + Scotland + Wales) plus NI
domestic rates, the council tax accruals adjustment and, from 2028-29, the
high-value council tax surcharge. The decomposition rows let a consumer bind a
household council tax liability to the GB cash-receipts total instead of the
UK total that carries components with no household counterpart.

Since chronicle#397 the March package keeps only 2024-25, the year the October
package does not print; October carries 2025-26 to 2031-32.
"""

from __future__ import annotations

import pytest

from chronicle.source_package import load_source_package

RECEIPTS_GB = "obr.council_tax_receipts_england_scotland_wales"
ACCRUALS = "obr.council_tax_accruals_adjustment"
SURCHARGE = "obr.council_tax_high_value_surcharge"


def _by_concept_period(facts):
    table = {}
    for fact in facts:
        table[(fact.measure.concept, fact.period.value)] = fact
    return table


def _assert_decomposition(table, years):
    for year in years:
        nations = sum(
            table[(concept, year)].value
            for concept in (
                "obr.council_tax_england",
                "obr.council_tax_scotland",
                "obr.council_tax_wales",
            )
        )
        # Row 15 is the sum of the three nation rows.
        assert table[(RECEIPTS_GB, year)].value == pytest.approx(nations, rel=1e-9)
        # Row 19 is row 15 + NI domestic rates + accruals (+ surcharge from 2028-29).
        components = (
            table[(RECEIPTS_GB, year)].value
            + table[("obr.domestic_rates", year)].value
            + table[(ACCRUALS, year)].value
            + (table[(SURCHARGE, year)].value if (SURCHARGE, year) in table else 0)
        )
        assert table[("obr.council_tax_total", year)].value == pytest.approx(
            components, rel=1e-9
        )


def _years(table, concept):
    return {period for key, period in table if key == concept}


def test_obr_table_4_1_council_tax_decomposition_rows():
    facts = load_source_package("obr-efo-expenditure-march-2026").build_facts(2026)
    table = _by_concept_period(facts)

    assert _years(table, RECEIPTS_GB) == {2024}
    assert _years(table, ACCRUALS) == {2024}
    # The surcharge is forecast from 2028-29, so October alone carries it.
    assert _years(table, SURCHARGE) == set()
    # FY2024-25 outturn: GBP 46.389bn GB receipts, GBP 0.807bn accruals adjustment.
    assert table[(RECEIPTS_GB, 2024)].value == pytest.approx(46_389_308_000, abs=0.01)
    assert table[(ACCRUALS, 2024)].value == pytest.approx(806_635_170.18, abs=0.01)
    assert table[(RECEIPTS_GB, 2024)].assertion == "observation"
    assert table[(RECEIPTS_GB, 2024)].geography.id == "K02000001"
    _assert_decomposition(table, [2024])
    # chronicle#357 adds table 4.9's two Northern Ireland rows; chronicle#397 keeps
    # each of the 23 lines' 2024-25 outturn.
    assert len(facts) == 23


def test_obr_table_5_1_council_tax_decomposition_rows_in_october():
    table = _by_concept_period(
        load_source_package("obr-efo-expenditure-october-2026").build_facts(2026)
    )

    years = set(range(2025, 2032))
    assert _years(table, RECEIPTS_GB) == years
    assert _years(table, ACCRUALS) == years
    # The publisher prints the surcharge from 2028-29 only; blank cells emit no facts.
    assert _years(table, SURCHARGE) == {2028, 2029, 2030, 2031}
    assert table[(SURCHARGE, 2028)].value == 397_292_600
    assert table[(RECEIPTS_GB, 2025)].assertion == "observation"
    assert table[(RECEIPTS_GB, 2026)].assertion == "source_projection"
    _assert_decomposition(table, sorted(years))
