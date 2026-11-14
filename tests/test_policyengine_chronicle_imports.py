import importlib

import pytest

from policyengine_chronicle import (
    AggregateFact,
    Aggregation,
    EntityDimension,
    GeographyDimension,
    Measure,
    PeriodDimension,
    SourceProvenance,
    build_fact_key,
    validate_fact,
)
import policyengine_chronicle.normalization as chronicle_normalization
from policyengine_chronicle.cli import main as chronicle_main
from policyengine_chronicle.targets.us_poverty import hard_target_package_aliases


def test__given_chronicle_import_path__then_it_reexports_chronicle_fact_schema() -> (
    None
):
    # Given
    fact = AggregateFact(
        value=1,
        period=PeriodDimension(type="calendar_year", value=2024),
        geography=GeographyDimension(level="country", id="0100000US"),
        entity=EntityDimension(name="person"),
        measure=Measure(concept="test.people", unit="count"),
        aggregation=Aggregation(method="sum"),
        provenance_class="administrative",
        source=SourceProvenance(
            source_name="test",
            source_table="Fixture",
            vintage="2024",
            extracted_at="2026-06-14",
            extraction_method="unit test",
        ),
    )

    # When
    issues = validate_fact(fact)
    key = build_fact_key(fact)

    # Then
    assert not issues
    assert key.startswith("ledger.fact.v1:")


def test__given_chronicle_facts_import_path__then_it_reexports_chronicle_facts() -> (
    None
):
    # When
    from chronicle.facts import AggregateFact as ChronicleCoreAggregateFact
    from policyengine_chronicle.facts import AggregateFact as ChronicleAggregateFact

    # Then
    assert ChronicleAggregateFact is ChronicleCoreAggregateFact


def test__given_chronicle_target_import_path__then_it_reexports_target_contracts() -> (
    None
):
    # When
    aliases = hard_target_package_aliases()

    # Then
    assert "soi-table-1-1" in aliases
    assert "ssa-ssi-table-7b1-2024" in aliases


def test__given_public_chronicle_namespaces__then_core_helpers_are_importable() -> None:
    from policyengine_chronicle.normalization import convert_units
    from policyengine_chronicle.sources import SourceFile

    assert SourceFile is not None
    assert convert_units is not None


def test__given_retired_profile_namespace__then_it_is_not_importable() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("policyengine_chronicle.target_profiles")


def test__given_public_chronicle_normalization__then_target_construction_is_gone() -> (
    None
):
    with pytest.raises(AttributeError):
        getattr(chronicle_normalization, "as_target")
    with pytest.raises(AttributeError):
        getattr(chronicle_normalization, "target_kwargs")
    with pytest.raises(AttributeError):
        getattr(chronicle_normalization, "TargetBlueprint")


def test__given_chronicle_help__then_cli_does_not_eager_load_legacy_clients(
    monkeypatch,
    capsys,
) -> None:
    # Given
    monkeypatch.setattr("sys.argv", ["chronicle", "--help"])

    # When
    chronicle_main()

    # Then
    output = capsys.readouterr().out
    assert "Usage: chronicle <command> [options]" in output
    assert "validate-facts" in output
    assert "  load\n" not in output
    assert "  stats\n" not in output
