"""Tests for the Chronicle namespace."""

import importlib

import pytest

import chronicle
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


@pytest.mark.parametrize("name", chronicle.__all__)
def test_every_name_in_chronicle_all_imports_as_a_submodule(name):
    # `from chronicle import *` raises on a name with no module behind it,
    # such as the retired "client".
    module = importlib.import_module(f"chronicle.{name}")

    assert module.__name__ == f"chronicle.{name}"
