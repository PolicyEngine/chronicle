"""Tests for the Chronicle namespace."""

from chronicle.client import get_supabase_client
from chronicle.normalization import convert_units
from chronicle.targets import TargetSourceCoverage, coverage_entries
from chronicle.targets.us_poverty import (
    TargetSourceCoverage as UsPovertyTargetSourceCoverage,
)
from db.supabase_client import LEDGER_SCHEMA


def test_chronicle_targets_reexports_source_coverage_helpers():
    assert TargetSourceCoverage is UsPovertyTargetSourceCoverage
    assert callable(coverage_entries)


def test_chronicle_client_reexports_supabase_client():
    assert callable(get_supabase_client)


def test_chronicle_supabase_schema_boundaries_are_defaulted():
    assert LEDGER_SCHEMA == "ledger"


def test_chronicle_normalization_exports_helpers():
    assert callable(convert_units)
