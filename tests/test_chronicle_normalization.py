"""Tests for Chronicle structural normalization helpers."""

import pytest

from db.schema import DataSource, Jurisdiction
from chronicle.normalization import (
    SourceFact,
    apply_share,
    convert_units,
    format_derivation,
)


def test_convert_units_records_derivation():
    fact = SourceFact(
        name="snap_households",
        value=22_323,
        period=2023,
        unit="thousands",
        source=DataSource.USDA_SNAP,
        jurisdiction=Jurisdiction.US,
    )

    converted = convert_units(fact, 1000, "count")

    assert converted.value == 22_323_000
    assert converted.unit == "count"
    assert converted.derivation[0].operation == "convert_units"
    assert converted.derivation[0].parameters["factor"] == 1000


def test_apply_share_preserves_provenance():
    total = SourceFact(
        name="aca_marketplace_enrollment",
        value=21_446_150,
        period=2024,
        unit="count",
        source="cms-aca",
        jurisdiction="us",
        source_table="Marketplace OEP Report",
    )

    silver = apply_share(total, 0.54, name="silver_marketplace_enrollment")

    assert silver.name == "silver_marketplace_enrollment"
    assert silver.value == pytest.approx(11_580_921)
    assert silver.period == 2024
    assert silver.source == "cms-aca"
    assert silver.jurisdiction == "us"
    assert silver.source_table == "Marketplace OEP Report"
    assert silver.derivation[-1].operation == "apply_share"
    assert silver.derivation[-1].parameters["total_fact"] == (
        "aca_marketplace_enrollment"
    )


def test_format_derivation_lists_steps_in_order():
    fact = SourceFact(
        name="snap_households",
        value=22_323,
        period=2023,
        unit="thousands",
        source=DataSource.USDA_SNAP,
        jurisdiction=Jurisdiction.US,
    )

    converted = convert_units(fact, 1000, "count")
    shared = apply_share(converted, 0.5, name="half_snap_households")

    formatted = format_derivation(shared.derivation)

    assert formatted.startswith("convert_units(factor=1000")
    assert "; apply_share(share=0.5" in formatted
    assert format_derivation(()) == ""
