"""Tests for Belgium's strict geography-vintage contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from chronicle.jurisdictions.be import (
    GeographyVintageDeclaration,
    GeographyVintageMismatchError,
    GeographyVintageMissingError,
    NISCodeCrosswalk,
    NISCrosswalkLookupError,
    compile_geography_keys,
)
from chronicle.source_package import load_source_package


REPO_ROOT = Path(__file__).resolve().parents[1]
CROSSWALK_PATH = (
    REPO_ROOT
    / "db"
    / "data"
    / "statbel"
    / "nis_2025_commune_crosswalk"
    / "statbel_nis_2025_commune_crosswalk.csv"
)


def test_nis_crosswalk_loads_publisher_rows_and_merged_codes():
    crosswalk = NISCodeCrosswalk.from_csv(CROSSWALK_PATH)

    assert len(crosswalk.rows) == 581
    assert {
        row.source_nis
        for row in crosswalk.rows
        if row.target_nis == "82039" and row.relationship == "merged"
    } == {"82003", "82005"}
    assert crosswalk.translate(
        "11007",
        source_vintage="nis_2019_2024",
        target_vintage="nis_2025",
    ).target_nis == "11002"


def test_nis_translation_plan_preserves_many_to_one_identity_rows():
    crosswalk = NISCodeCrosswalk.from_csv(CROSSWALK_PATH)

    plan = crosswalk.translation_plan(
        ["11056", "46003", "46013"],
        source_vintage="nis_2019_2024",
        target_vintage="nis_2025",
    )

    assert [row.source_nis for row in plan] == ["11056", "46003", "46013"]
    assert [row.target_nis for row in plan] == ["46030", "46030", "46030"]


def test_nis_translation_fails_when_crosswalk_has_no_declared_row():
    crosswalk = NISCodeCrosswalk.from_csv(CROSSWALK_PATH)

    with pytest.raises(NISCrosswalkLookupError, match="No NIS crosswalk row"):
        crosswalk.translate(
            "99999",
            source_vintage="nis_2019_2024",
            target_vintage="nis_2025",
        )


def test_commune_facts_compile_only_for_the_declared_vintage():
    facts = load_source_package(
        "statbel-fiscal-income-2023-nis-2025"
    ).build_facts(2023)

    keys = compile_geography_keys(
        facts,
        GeographyVintageDeclaration(level="commune", vintage="nis_2025"),
    )

    assert len(keys) == 565
    assert {key.vintage for key in keys} == {"nis_2025"}
    assert {key.geography_id for key in keys} >= {"11002", "46030", "82039"}


def test_compile_rejects_vintage_mismatch_instead_of_partial_join():
    rows = [
        {"geography": {"level": "commune", "id": "11001", "vintage": "nis_2025"}},
        {
            "geography": {
                "level": "commune",
                "id": "11002",
                "vintage": "nis_2019_2024",
            }
        },
    ]

    with pytest.raises(
        GeographyVintageMismatchError,
        match="nis_2019_2024.*11002",
    ):
        compile_geography_keys(
            rows,
            GeographyVintageDeclaration(level="commune", vintage="nis_2025"),
        )


def test_compile_rejects_missing_vintage_and_mixed_levels():
    declaration = GeographyVintageDeclaration(level="commune", vintage="nis_2025")

    with pytest.raises(GeographyVintageMissingError, match="11001"):
        compile_geography_keys(
            [{"level": "commune", "id": "11001"}],
            declaration,
        )
    with pytest.raises(GeographyVintageMismatchError, match="nuts1.*BE1"):
        compile_geography_keys(
            [{"level": "nuts1", "id": "BE1", "vintage": "NUTS_2024"}],
            declaration,
        )
