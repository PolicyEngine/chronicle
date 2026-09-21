"""The publisher's geography name on consumer facts (chronicle#266).

Microcosm's calibration hierarchy labels a target's geography tier from the
Chronicle fact it selects and falls back to its own catalog only for
identifiers it already knows, so a fact below country level that states no name
cannot be placed. Chronicle has always held the name the publisher gives an
area; ``chronicle.consumer_fact.v3`` exports it. These tests pin that it rides
on the row, never on a key, and that ``build-bundle`` refuses an unnamed
sub-national geography.

Chronicle's canonical name register (chronicle#281) answers first for the
identifiers it carries, so the cases below that turn on a source naming an area
badly or not at all use identifiers outside it - output-area-level codes, and
the US areas whose publishers truncate their names. What the register answers
for is pinned in ``test_chronicle_geography_names``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from chronicle import bundle
from chronicle.bundle import (
    _cross_package_geography_name_warnings,
    _geography_name_errors,
)
from chronicle.consumer_contract import consumer_fact_row
from chronicle.core import (
    AggregateFact,
    Aggregation,
    EntityDimension,
    GeographyDimension,
    Measure,
    PeriodDimension,
    SourceProvenance,
    SourceRecordLayout,
)
from policyengine_chronicle.consumer import (
    build_consumer_artifact,
    load_consumer_artifact,
)
from policyengine_chronicle.schema import validate_consumer_fact_row

SHA = "ef" * 32
_KEY_FIELDS = (
    "aggregate_fact_key",
    "semantic_fact_key",
    "legacy_fact_key",
    "source_release_key",
    "source_series_key",
    "observed_measure_key",
    "dimension_set_key",
    "universe_constraint_set_key",
)


def _fact(*, name=None, level="constituency", geography_id="E14001101"):
    return AggregateFact(
        value=1200,
        period=PeriodDimension(type="month", value="2025-05"),
        geography=GeographyDimension(
            level=level,
            id=geography_id,
            vintage="pcon_2024",
            name=name,
        ),
        entity=EntityDimension(name="household"),
        measure=Measure(concept="dwp.uc_households", unit="count"),
        aggregation=Aggregation(method="sum"),
        provenance_class="administrative",
        source=SourceProvenance(
            source_name="dwp",
            source_table="Households on Universal Credit",
            source_file="uc.json",
            url="https://stat-xplore.dwp.gov.uk/webapi/rest/v1/table",
            vintage="stat_xplore_may_2025",
            extracted_at="2026-08-12",
            extraction_method="test",
            source_sha256=SHA,
            source_size_bytes=10,
            raw_r2_bucket="ledger-raw",
            raw_r2_key=f"raw/uk/dwp/uc/{SHA}/uc.json",
            raw_r2_uri=f"r2://ledger-raw/raw/uk/dwp/uc/{SHA}/uc.json",
        ),
        domain="universal_credit",
        source_record_id=f"dwp.uc.{geography_id.lower()}.households",
        source_cell_keys=("ledger.source_cell.v1:" + "a" * 24,),
        layout=SourceRecordLayout(
            record_set_id="dwp.uc.month2025_05",
            record_set_spec_id="dwp.uc.by_constituency.v1",
            measure_id="households",
            groupby_dimension="geography",
            groupby_value_id=geography_id.lower(),
            groupby_value_label="Bishop Auckland",
            groupby_dimension_label="Geography",
        ),
        dimension_labels={"geography": "Geography"},
        dimension_value_labels={"geography": {geography_id.lower(): "Bishop Auckland"}},
    )


def _copy_package(tmp_path, relative_dir, *, transform):
    source = Path(__file__).parents[1] / "packages" / relative_dir
    target = tmp_path / source.name
    shutil.copytree(source, target)
    package_yaml = target / "source_package.yaml"
    package_yaml.write_text(transform(package_yaml.read_text()))
    return target


def _without_geography_names(text):
    return "\n".join(
        line
        for line in text.split("\n")
        if not line.strip().startswith("geography_name:")
    )


def test_the_row_names_the_geography_its_publisher_names():
    row = consumer_fact_row(_fact(name="Bishop Auckland"))

    assert row["geography"] == {
        "id": "E14001101",
        "level": "constituency",
        "name": "Bishop Auckland",
        "vintage": "pcon_2024",
    }
    validate_consumer_fact_row(row, 1, "named.jsonl")


@pytest.mark.parametrize("name", [None, "", "   "])
def test_a_geography_the_source_does_not_name_exports_no_name(name):
    row = consumer_fact_row(_fact(name=name, level="msoa", geography_id="E02000001"))

    assert "name" not in row["geography"]
    validate_consumer_fact_row(row, 1, "unnamed.jsonl")


def test_the_geography_name_moves_no_key_and_nothing_else_on_the_row():
    plain = consumer_fact_row(_fact(level="msoa", geography_id="E02000001"))
    named = consumer_fact_row(
        _fact(name="Darlington 001", level="msoa", geography_id="E02000001")
    )

    for field_name in (*_KEY_FIELDS, "value", "dimensions", "period", "entity"):
        assert named[field_name] == plain[field_name]
    assert {key: value for key, value in named.items() if plain.get(key) != value} == {
        "geography": {**plain["geography"], "name": "Darlington 001"}
    }


def test_an_artifact_of_named_rows_loads(tmp_path):
    facts_path = tmp_path / "consumer_facts.jsonl"
    rows = [
        consumer_fact_row(_fact(name="Bishop Auckland")),
        consumer_fact_row(
            _fact(name="Blaydon and Consett", geography_id="E14001106"),
        ),
    ]
    facts_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )
    out_dir = tmp_path / "artifact"

    build_consumer_artifact(out_dir, facts_path=facts_path)
    artifact = load_consumer_artifact(out_dir)

    assert [row["geography"]["name"] for row in artifact.rows] == [
        "Bishop Auckland",
        "Blaydon and Consett",
    ]


def test_a_v2_row_may_not_carry_a_geography_name():
    row = {**consumer_fact_row(_fact(name="Bishop Auckland"))}
    row["schema_version"] = "chronicle.consumer_fact.v2"

    with pytest.raises(ValueError, match="geography"):
        validate_consumer_fact_row(row, 1, "v2.jsonl")


def test_unnamed_areas_are_reported_once_each_and_country_rows_are_not():
    rows = [
        consumer_fact_row(_fact(level="msoa", geography_id="E02000001")),
        consumer_fact_row(_fact(level="msoa", geography_id="E02000001")),
        consumer_fact_row(_fact(level="msoa", geography_id="E02000002")),
        consumer_fact_row(_fact(level="country", geography_id="K03000001")),
        consumer_fact_row(_fact(name="Bishop Auckland")),
    ]

    errors = _geography_name_errors("dwp-uc-households-by-constituency-may-2025", rows)

    assert [error.key for error in errors] == [
        "msoa:E02000001",
        "msoa:E02000002",
    ]
    assert {error.code for error in errors} == {"missing_geography_name"}
    assert "2 fact(s)" in errors[0].message


def test_build_bundle_reports_a_package_that_names_no_area(tmp_path):
    package_dir = _copy_package(
        tmp_path,
        "hhs_acf/tanf_caseload_2024",
        transform=_without_geography_names,
    )

    report = bundle.build_bundle(
        tmp_path / "bundle", year=2024, sources=[str(package_dir)]
    )

    assert not report.valid
    assert {issue.code for issue in report.errors} == {"missing_geography_name"}
    assert "state:0400000US01" in {issue.key for issue in report.errors}


def test_packages_that_name_one_area_two_ways_are_a_warning():
    warnings = _cross_package_geography_name_warnings(
        {
            ("county", "0500000US02013"): {
                "Aleutians East Borou": ["soi-county-2022"],
                "Aleutians East Borough": ["census-pep-county-population-2024"],
            },
            ("region", "E12000007"): {"London": ["dft-bus0415-fares-index-2026"]},
        }
    )

    assert [(warning.code, warning.key) for warning in warnings] == [
        ("conflicting_geography_name_across_packages", "county:0500000US02013")
    ]
    assert "'Aleutians East Borou' in ['soi-county-2022']" in warnings[0].message


def test_build_bundle_warns_when_two_packages_name_an_area_differently(tmp_path):
    package_dir = _copy_package(
        tmp_path,
        "hhs_acf/tanf_caseload_2024",
        transform=lambda text: text.replace(
            "geography_name: Alabama", "geography_name: Alabama (truncated)", 1
        ),
    )
    original_dir = (
        Path(__file__).parents[1] / "packages" / "hhs_acf/tanf_financial_2024"
    )

    report = bundle.build_bundle(
        tmp_path / "bundle",
        year=2024,
        sources=[str(package_dir), str(original_dir)],
    )

    names = [
        warning
        for warning in report.warnings
        if warning.code == "conflicting_geography_name_across_packages"
    ]
    assert report.valid
    assert [warning.key for warning in names] == ["state:0400000US01"]


def test_one_package_naming_an_area_twice_is_an_error():
    rows = [
        consumer_fact_row(
            _fact(name="Darlington 001", level="msoa", geography_id="E02000001")
        ),
        consumer_fact_row(
            _fact(name="Darlington  001", level="msoa", geography_id="E02000001")
        ),
        consumer_fact_row(
            _fact(name="Darlington 002", level="msoa", geography_id="E02000002")
        ),
    ]

    errors = _geography_name_errors("dwp-uc-households-by-constituency-may-2025", rows)

    assert [(error.code, error.key) for error in errors] == [
        ("conflicting_geography_name", "msoa:E02000001")
    ]
    assert "one source states one name for an area" in errors[0].message
