"""Tests for the congressional district geographic level."""

from db.schema import GeographicLevel


def test_geographic_level_enum_exists():
    """GeographicLevel enum should include congressional_district."""
    assert GeographicLevel.CONGRESSIONAL_DISTRICT == "congressional_district"
    assert GeographicLevel.STATE == "state"
    assert GeographicLevel.NATIONAL == "national"
