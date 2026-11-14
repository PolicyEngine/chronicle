"""Tests for the Chronicle namespace."""

from chronicle.normalization import convert_units
from chronicle.targets import TargetSourceCoverage, coverage_entries
from chronicle.targets.us_poverty import (
    TargetSourceCoverage as UsPovertyTargetSourceCoverage,
)


def test_chronicle_targets_reexports_source_coverage_helpers():
    assert TargetSourceCoverage is UsPovertyTargetSourceCoverage
    assert callable(coverage_entries)


def test_chronicle_normalization_exports_helpers():
    assert callable(convert_units)
