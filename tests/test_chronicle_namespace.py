"""Tests for the Chronicle namespace."""

from chronicle.client import get_supabase_client
from chronicle.normalization import convert_units
from chronicle.targets import (
    Target,
    TargetType,
    query_targets,
)
from db.schema import Target as DbTarget
from db.supabase_client import (
    TARGETS_SCHEMA,
    query_targets as db_query_targets,
)


def test_chronicle_targets_reexport_schema_objects():
    assert Target is DbTarget
    assert TargetType.COUNT.value == "count"


def test_chronicle_targets_reexport_client_helpers():
    assert query_targets is db_query_targets


def test_chronicle_client_reexports_supabase_client():
    assert callable(get_supabase_client)


def test_chronicle_supabase_schema_boundaries_are_defaulted():
    assert TARGETS_SCHEMA == "targets"


def test_chronicle_normalization_exports_helpers():
    assert callable(convert_units)
