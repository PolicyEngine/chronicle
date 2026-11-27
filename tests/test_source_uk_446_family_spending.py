"""Source package for PolicyEngine/chronicle#446: household spending by income decile.

ONS's Family Spending workbook 1, the financial year ending 2025 edition (released 11 June
2026), from the Living Costs and Food Survey: mean weekly household expenditure by commodity
group, with each decile's weighted households and households in the sample, by equivalised
disposable income decile in both equivalisation versions (Table 3.1E) and by gross income
decile (Table A6). Expected values are read from the pinned workbook here with openpyxl,
independently of Chronicle's parser, except for a few published figures written in so that a
re-pin that moves one of them fails.
"""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import runpy

from openpyxl import load_workbook
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
PACKAGE_ID = "ons-family-spending-workbook1-fye2025"
YEAR = 2025
SHA256 = "af8d4a4464c0cc0a49195495a6e665667234379ac08293037a69e065d8931076"
SIZE = 558943
EXPENDITURE = "ons.family_spending.mean_weekly_household_expenditure"
WEIGHTED = "ons.family_spending.weighted_households"
SAMPLE = "ons.family_spending.households_in_sample"
UPDATED = "updated_oecd_modified_2_adult_reference"
ONE_ADULT = "oecd_modified_1_adult_reference"
EQUIVALISED = "equivalised_disposable_income"
GROSS = "gross_income"
GROUPS = (
    *(f"coicop_{division:02}" for division in range(1, 13)),
    "coicop_01_to_12",
    "other_expenditure_items",
    "total_expenditure",
)
DECILES = tuple(f"decile_{decile}" for decile in range(1, 11))
# (ranking, scale) -> (sheet, decile columns, all-household column)
BLOCKS = {
    (EQUIVALISED, UPDATED): ("3.1E", tuple("EFGHIJKLMN"), "O"),
    (EQUIVALISED, ONE_ADULT): (
        "3.1E",
        ("V", "W", "X", "Y", "Z", "AA", "AB", "AC", "AD", "AE"),
        "AF",
    ),
    (GROSS, None): ("A6", tuple("EFGHIJKLMN"), "O"),
}
# sheet -> expenditure group -> row; and the two count rows.
ROWS = {
    "3.1E": dict(
        zip(
            GROUPS,
            (28, 105, 118, 138, 180, 200, 209, 229, 262, 302, 309, 347, 372, 375, 389),
            strict=True,
        )
    ),
    "A6": dict(
        zip(
            GROUPS,
            (27, 93, 106, 124, 164, 184, 193, 213, 245, 285, 292, 328, 353, 356, 370),
            strict=True,
        )
    ),
}
COUNT_ROWS = {"3.1E": (17, 18), "A6": (16, 17)}


def _facts():
    return load_source_package(PACKAGE_ID).build_facts(YEAR)


def _package() -> dict:
    path = (
        ROOT / "packages" / SOURCE_PACKAGE_ALIASES[PACKAGE_ID] / "source_package.yaml"
    )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _artifact_dir() -> Path:
    return ROOT / "db" / _package()["artifact"]["resource_directory"]


def _manifest() -> dict:
    return yaml.safe_load(
        (_artifact_dir() / "manifest.yaml").read_text(encoding="utf-8")
    )


def _workbook():
    ((_, entry),) = _manifest()["files"].items()
    return load_workbook(_artifact_dir() / entry["filename"], data_only=True)


def _number(text: object) -> float | None:
    """The workbook prints its figures as text; '..' marks a suppressed cell."""
    if text == "..":
        return None
    return float(str(text).replace(",", ""))


def _by_key(facts) -> dict:
    keyed = {}
    for fact in facts:
        key = (fact.measure.concept, tuple(sorted(fact.filters.items())))
        assert key not in keyed, key
        keyed[key] = fact
    return keyed


def _key(concept: str, **filters: str) -> tuple:
    return (concept, tuple(sorted(filters.items())))


def _block_filters(ranking: str, scale: str | None, decile: str) -> dict:
    filters = {"income_decile_group": decile, "income_decile_basis": ranking}
    if scale is not None:
        filters["equivalence_scale"] = scale
    return filters


def test_package_validates_registers_and_builds_unique_facts():
    package_dir = ROOT / "packages" / SOURCE_PACKAGE_ALIASES[PACKAGE_ID]
    report = validate_source_package(package_dir, year=YEAR)
    assert report.valid, report
    assert PACKAGE_ID in UK_BUNDLE_SOURCES
    built = _facts()
    assert len(built) == 487
    assert validate_facts(built).valid
    contract = validate_consumer_fact_contract(built)
    assert contract.valid, contract.to_dict()
    assert max(Counter(build_semantic_fact_key(fact) for fact in built).values()) == 1
    assert {fact.provenance_class for fact in built} == {"survey_aggregate"}
    assert {fact.survey_instrument for fact in built} == {
        "Living Costs and Food Survey"
    }
    assert {(fact.period.type, fact.period.value) for fact in built} == {
        ("fiscal_year", 2024)
    }
    assert {(fact.geography.id, fact.geography.name) for fact in built} == {
        ("K02000001", "United Kingdom")
    }
    assert {(fact.entity.name, fact.entity.role) for fact in built} == {
        ("household", "private_household")
    }
    assert Counter(fact.measure.concept for fact in built) == {
        EXPENDITURE: 425,
        WEIGHTED: 31,
        SAMPLE: 31,
    }


def test_package_builds_the_same_facts_at_the_bundle_year():
    package = load_source_package(PACKAGE_ID)
    assert [
        (fact.source_record_id, fact.value) for fact in package.build_facts(2023)
    ] == [(fact.source_record_id, fact.value) for fact in package.build_facts(YEAR)]


def test_generator_reproduces_the_committed_package():
    generator = runpy.run_path(str(ROOT / "scripts/build_uk_446_packages.py"))
    for directory, build in generator["BUILDERS"].items():
        path = ROOT / "packages" / directory / "source_package.yaml"
        assert build() == path.read_text(encoding="utf-8"), directory


def test_manifest_pins_bytes_licence_and_r2():
    manifest = _manifest()
    assert manifest["package_id"] == PACKAGE_ID
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-26"
    ((year, entry),) = manifest["files"].items()
    assert year == YEAR
    content = (_artifact_dir() / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"] == SHA256
    assert len(content) == entry["size_bytes"] == SIZE
    assert entry["storage"]["r2"]["uri"].endswith(
        f"/{PACKAGE_ID}/{year}/{SHA256}/{entry['filename']}"
    )


@pytest.mark.parametrize("ranking,scale", sorted(BLOCKS, key=str))
def test_decile_facts_are_the_workbook_cells(ranking, scale):
    sheet, columns, _ = BLOCKS[(ranking, scale)]
    worksheet = _workbook()[sheet]
    facts = _by_key(_facts())
    for decile, column in zip(DECILES, columns, strict=True):
        filters = _block_filters(ranking, scale, decile)
        for group, row in ROWS[sheet].items():
            published = _number(worksheet[f"{column}{row}"].value)
            key = _key(EXPENDITURE, expenditure_group=group, **filters)
            if published is None:
                assert key not in facts, key
            else:
                assert facts[key].value == pytest.approx(published), key
        weighted_row, sample_row = COUNT_ROWS[sheet]
        weighted = _number(worksheet[f"{column}{weighted_row}"].value)
        sample = _number(worksheet[f"{column}{sample_row}"].value)
        assert facts[_key(WEIGHTED, **filters)].value == weighted * 1000
        assert facts[_key(SAMPLE, **filters)].value == sample


def test_all_household_facts_are_read_once_and_match_every_block():
    workbook = _workbook()
    facts = _by_key(_facts())
    for group in GROUPS:
        (fact,) = [
            fact
            for key, fact in facts.items()
            if key[0] == EXPENDITURE and dict(key[1]) == {"expenditure_group": group}
        ]
        for sheet, _, column in BLOCKS.values():
            published = _number(workbook[sheet][f"{column}{ROWS[sheet][group]}"].value)
            assert fact.value == pytest.approx(published), (sheet, group)
    assert facts[_key(WEIGHTED)].value == 28_710_000
    assert facts[_key(SAMPLE)].value == 5_000


def test_suppressed_cells_carry_no_fact():
    built = _facts()
    decile_groups = Counter(
        (fact.filters["income_decile_basis"], fact.filters["expenditure_group"])
        for fact in built
        if fact.measure.concept == EXPENDITURE and "income_decile_group" in fact.filters
    )
    assert ("equivalised_disposable_income", "coicop_10") not in decile_groups
    assert ("gross_income", "coicop_10") not in decile_groups
    assert ("gross_income", "coicop_06") not in decile_groups
    assert decile_groups[("equivalised_disposable_income", "coicop_06")] == 20
    assert decile_groups[("gross_income", "coicop_01")] == 10


def test_totals_add_up_within_rounding():
    keyed = _by_key(_facts())
    columns = [()]
    for ranking, scale in BLOCKS:
        for decile in DECILES:
            columns.append(
                tuple(sorted(_block_filters(ranking, scale, decile).items()))
            )
    for column in columns:

        def value(group: str) -> float:
            return keyed[
                (
                    EXPENDITURE,
                    tuple(sorted({**dict(column), "expenditure_group": group}.items())),
                )
            ].value

        assert value("coicop_01_to_12") + value(
            "other_expenditure_items"
        ) == pytest.approx(value("total_expenditure"), abs=0.1 + 1e-9), column
    divisions = sum(
        keyed[_key(EXPENDITURE, expenditure_group=f"coicop_{division:02}")].value
        for division in range(1, 13)
    )
    assert divisions == pytest.approx(
        keyed[_key(EXPENDITURE, expenditure_group="coicop_01_to_12")].value, abs=0.6
    )


@pytest.mark.parametrize("ranking,scale", sorted(BLOCKS, key=str))
def test_deciles_add_up_to_all_households_within_rounding(ranking, scale):
    keyed = _by_key(_facts())
    for concept, total, tolerance in (
        (WEIGHTED, 28_710_000, 50_000),
        (SAMPLE, 5_000, 50),
    ):
        deciles = sum(
            keyed[_key(concept, **_block_filters(ranking, scale, decile))].value
            for decile in DECILES
        )
        assert abs(deciles - total) <= tolerance, (concept, deciles)


def test_the_published_figures_are_pinned():
    keyed = _by_key(_facts())
    updated = _block_filters(EQUIVALISED, UPDATED, "decile_1")
    assert (
        keyed[_key(EXPENDITURE, expenditure_group="total_expenditure")].value == 676.6
    )
    assert keyed[_key(EXPENDITURE, expenditure_group="coicop_01")].value == 73.7
    assert (
        keyed[_key(EXPENDITURE, expenditure_group="total_expenditure", **updated)].value
        == 377.1
    )
    assert (
        keyed[
            _key(
                EXPENDITURE,
                expenditure_group="total_expenditure",
                **_block_filters(EQUIVALISED, UPDATED, "decile_10"),
            )
        ].value
        == 1243.2
    )
    assert (
        keyed[
            _key(
                EXPENDITURE,
                expenditure_group="total_expenditure",
                **_block_filters(EQUIVALISED, ONE_ADULT, "decile_1"),
            )
        ].value
        == 380.1
    )
    assert (
        keyed[
            _key(
                EXPENDITURE,
                expenditure_group="total_expenditure",
                **_block_filters(GROSS, None, "decile_1"),
            )
        ].value
        == 291.3
    )
    assert keyed[_key(SAMPLE, **updated)].value == 500


def test_every_fact_states_its_ranking_and_scale():
    for fact in _facts():
        filters = fact.filters
        if "income_decile_group" not in filters:
            assert "income_decile_basis" not in filters
            assert "equivalence_scale" not in filters
        elif filters["income_decile_basis"] == EQUIVALISED:
            assert filters["equivalence_scale"] in {UPDATED, ONE_ADULT}
        else:
            assert filters["income_decile_basis"] == GROSS
            assert "equivalence_scale" not in filters
