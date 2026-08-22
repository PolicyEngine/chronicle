"""Tests for TY2023 IRS SOI Publication 4801 Form 8960 facts."""

from __future__ import annotations

from chronicle.core import validate_facts
from chronicle.source_package import load_source_package, validate_source_package
from chronicle.sources.cells import validate_source_cells
from chronicle.sources.rows import validate_source_rows


EXPECTED_COUNTS = {
    "line_1": 8_200_131,
    "line_2": 6_877_553,
    "line_3": 176_061,
    "line_4a": 4_988_033,
    "line_4b": 4_038_235,
    "line_4c": 2_260_296,
    "line_5d": 6_432_002,
    "line_8": 8_976_709,
    "line_12": 8_211_516,
    "line_17": 8_104_840,
}

EXPECTED_AMOUNTS_USD = {
    "line_1": 209_033_554_000,
    "line_2": 349_823_646_000,
    "line_3": 6_970_315_000,
    "line_4a": 1_185_607_258_000,
    "line_4b": -1_076_350_273_000,
    "line_4c": 109_256_984_000,
    "line_5d": 556_322_852_000,
    "line_8": 1_222_447_069_000,
    "line_12": 1_197_238_417_000,
    "line_17": 39_330_017_000,
}


def _facts_by_line_and_measure():
    package = load_source_package("soi-form-8960-2023")
    source_rows = package.build_source_rows(2023)
    cells = package.build_source_cells(2023, source_rows=source_rows)
    facts = package.build_facts(2023, cells=cells, source_rows=source_rows)
    return (
        package,
        source_rows,
        cells,
        facts,
        {
            (fact.layout.record_set_id.rsplit(".", 1)[-1], fact.layout.measure_id): fact
            for fact in facts
        },
    )


def test_form_8960_package_emits_requested_counts_and_amounts():
    package, source_rows, cells, facts, facts_by_line_and_measure = (
        _facts_by_line_and_measure()
    )

    assert package.package_id == "soi-form-8960-2023"
    assert len(package.record_sets) == 10
    assert len(source_rows) == 10
    assert len(facts) == 20
    assert validate_source_rows(source_rows).valid
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid

    for line, expected_count in EXPECTED_COUNTS.items():
        count = facts_by_line_and_measure[(line, "return_count")]
        amount = facts_by_line_and_measure[(line, "amount")]
        assert count.value == expected_count
        assert count.measure.unit == "count"
        assert count.measure.concept == f"irs_soi.form_8960.{line}.return_count"
        assert amount.value == EXPECTED_AMOUNTS_USD[line]
        assert amount.measure.unit == "usd"
        assert amount.measure.concept == f"irs_soi.form_8960.{line}"

    assert {fact.provenance_class for fact in facts} == {"administrative"}
    assert {fact.source.url for fact in facts} == {
        "https://www.irs.gov/pub/irs-pdf/p4801.pdf"
    }
    assert {fact.source.vintage for fact in facts} == {"tax_year_2023_rev_6_2026"}
    assert {fact.source.source_sha256 for fact in facts} == {
        "a831947133806455b971560102bf6d7710865ece481616844bead7c9b81958fd"
    }
    assert all(fact.source.raw_r2_uri for fact in facts)


def test_form_8960_line_4_arithmetic_is_consistent_to_published_unit():
    _, _, _, _, facts_by_line_and_measure = _facts_by_line_and_measure()
    line_4a = facts_by_line_and_measure[("line_4a", "amount")].value
    line_4b = facts_by_line_and_measure[("line_4b", "amount")].value
    line_4c = facts_by_line_and_measure[("line_4c", "amount")].value

    # Publication 4801 displays independently estimated amounts in $000. The
    # reported components therefore leave exactly one published unit of
    # rounding residual; changing any fact to force equality would break
    # publisher fidelity.
    residual = line_4a + line_4b - line_4c
    assert residual == 1_000
    assert abs(residual) <= 1_000


def test_form_8960_source_package_validates():
    report = validate_source_package("soi-form-8960-2023", year=2023)

    assert report.valid
    assert report.counts == {
        "measure_count": 20,
        "record_set_count": 10,
        "row_count": 10,
        "source_record_count": 20,
        "source_region_count": 10,
    }
