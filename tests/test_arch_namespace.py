"""Tests for the Arch namespace."""

from arch.client import get_supabase_client
from arch.microdata import get_table_name, query_cps_asec
from arch.normalization import convert_units
from db.supabase_client import ARCH_SCHEMA, MICRODATA_SCHEMA


def test_arch_microdata_reexport_client_helpers():
    assert get_table_name("us", "census", "cps_asec", 2024, "person") == (
        "us_census_cps_asec_2024_person"
    )
    assert callable(query_cps_asec)


def test_arch_client_reexports_supabase_client():
    assert callable(get_supabase_client)


def test_arch_supabase_schema_boundaries_are_defaulted():
    assert ARCH_SCHEMA == "arch"
    assert MICRODATA_SCHEMA == "microdata"


def test_arch_normalization_exports_helpers():
    assert callable(convert_units)
