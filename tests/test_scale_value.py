"""Unit coverage for the shared measure value scaler.

The scaler decides integrality in decimal so publisher lexemes that scale to
whole numbers come out as exact ints, while every non-integral product keeps
the binary result bit-for-bit (existing fact values must not shift).
"""

import pytest

from chronicle.sources.specs import _scale_value


def test_integral_decimal_product_is_exact_int():
    # The spr_exp_func regression: binary multiplication alone emits
    # 16448060000.000002 for this publisher lexeme.
    assert _scale_value(16448.06, 1_000_000) == 16_448_060_000
    assert isinstance(_scale_value(16448.06, 1_000_000), int)


def test_integral_float_product_is_int():
    assert _scale_value(2.5, 2) == 5
    assert isinstance(_scale_value(2.5, 2), int)


def test_int_inputs_stay_int():
    assert _scale_value(5, 1000) == 5000
    assert isinstance(_scale_value(5, 1000), int)


def test_non_integral_product_preserves_binary_result_bit_for_bit():
    # Non-integral results must be the pre-existing binary product. These
    # pairs are chosen because binary multiplication and the rejected
    # all-Decimal implementation (float(Decimal(str(v)) * Decimal(str(s))))
    # land on DIFFERENT adjacent doubles, so this test fails under a
    # full-Decimal scaler; the expected reprs are the binary products.
    cases = {
        (247322.9728, 1000): "247322972.79999998",  # all-Decimal: ...72.8
        (944577.8457, 1000): "944577845.6999999",  # all-Decimal: ...45.7
        (288204.28227, 1000): "288204282.27000004",  # all-Decimal: ...82.27
        (322810.9418, 1000): "322810941.79999995",  # all-Decimal: ...41.8
    }
    for (value, scale), expected_repr in cases.items():
        assert repr(value * scale) == expected_repr
        assert repr(_scale_value(value, scale)) == expected_repr


def test_string_passthrough_only_at_scale_one():
    assert _scale_value("suppressed", 1) == "suppressed"
    with pytest.raises(ValueError, match="Cannot scale"):
        _scale_value("suppressed", 1000)


def test_bool_and_none_are_rejected():
    with pytest.raises(ValueError, match="Cannot scale"):
        _scale_value(True, 1)
    with pytest.raises(ValueError, match="Cannot scale"):
        _scale_value(None, 1)


def test_scaler_corrections_pin_previously_dusty_package_values():
    # The complete set of existing facts whose serialized values change under
    # decimal integrality (verified by a full five-package diff against the
    # pre-change tree): four integral publisher values that binary
    # multiplication had emitted with float dust (e.g. a recipient headcount
    # of 1028438.0000000001). Everything else is bit-identical.
    from chronicle.source_package import load_source_package

    expected = {
        (
            "slc-student-support-england-2025",
            2025,
            "slc.support_2025.table_3a.recipients.ay2017.grand_total.recipients",
        ): 1_028_438,
        (
            "slc-student-support-england-2025",
            2025,
            "slc.support_2025.table_4c.recipients.ay2018"
            ".adult_dependants_grant.recipients",
        ): 16_336,
        (
            "welshgov-council-tax-levels-2026-27",
            2026,
            "welshgov.ct_levels_2026_27.budget.authority"
            ".fy2026.w06000005.council_tax_income",
        ): 131_972_547,
        (
            "scotgov-scottish-budget-social-security-assistance-2026",
            2026,
            "scotgov.budget_2026_27.table_5_08.fy2025"
            ".carer_support_payment.amount",
        ): 520_700_000,
    }

    facts_by_alias = {}
    for alias, year, record_id in expected:
        if alias not in facts_by_alias:
            package = load_source_package(alias)
            rows = package.build_source_rows(year)
            cells = package.build_source_cells(year, source_rows=rows)
            facts = package.build_facts(year, cells=cells, source_rows=rows)
            facts_by_alias[alias] = {
                fact.source_record_id: fact for fact in facts
            }
        fact = facts_by_alias[alias][record_id]
        assert fact.value == expected[(alias, year, record_id)]
        assert isinstance(fact.value, int)


def test_non_integral_package_values_keep_their_binary_doubles():
    # Discriminating fact-level pins: for each of these, the rejected
    # all-Decimal scaler emits a DIFFERENT adjacent double (shown in the
    # comment), verified by building all five packages under both
    # implementations and diffing every serialized value. The pinned reprs
    # are the pre-existing binary products, unchanged from main.
    from chronicle.source_package import load_source_package

    expected = {
        # chronicle#397 left the March 2026 EFO packages with 2024-25 (and a few
        # 2025-26 lines) only: state pension FY2030-31 and income tax FY2025-26 went
        # with the years the October 2026 packages publish.
        ("obr-efo-expenditure-march-2026", 2026): {
            # all-Decimal: 2938385000.0
            "obr.efo_2026_03.expenditure.council_tax_scotland"
            ".fy2024.council_tax_scotland.amount": "2938385000.0000005",
        },
        ("obr-efo-receipts-march-2026", 2026): {
            # all-Decimal: 47375027967.77022
            "obr.efo_2026_03.receipts.ni_employee"
            ".fy2024.ni_employee.amount": "47375027967.770226",
            # all-Decimal: 115446805221.42703
            "obr.efo_2026_03.receipts.ni_employer"
            ".fy2024.ni_employer.amount": "115446805221.42705",
        },
        ("slc-student-support-england-2025", 2025): {
            # all-Decimal: 1117591.0 — the upstream lexeme is genuinely
            # non-integral, so the scaler must NOT round it to a clean count.
            "slc.support_2025.table_3a.recipients"
            ".ay2020.grand_total.recipients": "1117591.0000000002",
            # all-Decimal: 168349636.59000003
            "slc.support_2025.table_4c.amount"
            ".ay2023.parents_learning_allowance.amount_awarded": "168349636.59",
        },
        ("welshgov-council-tax-levels-2026-27", 2026): {
            # all-Decimal: 708199216.3799999
            "welshgov.ct_levels_2026_27.budget.authority"
            ".fy2026.w06000016.budget_requirement": "708199216.38",
        },
    }

    for (alias, year), pins in expected.items():
        package = load_source_package(alias)
        rows = package.build_source_rows(year)
        cells = package.build_source_cells(year, source_rows=rows)
        facts = package.build_facts(year, cells=cells, source_rows=rows)
        facts_by_id = {fact.source_record_id: fact for fact in facts}
        for record_id, value_repr in pins.items():
            assert repr(facts_by_id[record_id].value) == value_repr
