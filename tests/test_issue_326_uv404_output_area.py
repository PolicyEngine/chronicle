"""Regression tests for chronicle#326: Scotland's Census 2022 UV404 by 2022 output area.

The public UV404 output-area CSV (UK Data Service copy, byte-identical to the member of
NRS's output-area ZIP) carries all occupied households and the published 'Private
rented: Total' for each of 46,363 output areas. Its '-' cells emit no fact. Values are
the publisher's as fetched on 2026-10-15.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

import pytest
import yaml

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.core import validate_facts
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package

PACKAGE = "nrs-census2022-uv404-tenure-output-area"
DATA = (
    Path(__file__).resolve().parents[1]
    / "db/data/nrs/census2022_uv404_tenure_output_area"
)
SHA256 = "d6abb0ee1a8f21e17160a517088b1ca62ddcb728a35bf5ecbf82c7f400b6378f"


@pytest.fixture(scope="module")
def facts():
    return load_source_package(PACKAGE).build_facts(2022)


def test_artifact_is_the_issue_pinned_csv():
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text())
    (entry,) = manifest["files"].values()
    assert entry["sha256"] == SHA256
    assert entry["source_url"].endswith(
        "Census_2022_UV404_Household_tenure_Households_oa.csv"
    )
    content = (DATA / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == SHA256


def test_counts_markers_and_published_totals(facts):
    assert PACKAGE in SOURCE_PACKAGE_ALIASES and PACKAGE in UK_BUNDLE_SOURCES
    assert validate_facts(facts).valid
    by_tenure = Counter(f.filters["household_tenure"] for f in facts)
    # 4,910 output areas print '-' for 'Private rented: Total'; none for all households.
    assert by_tenure == {
        "All occupied households": 46_363,
        "Private rented: Total": 41_453,
    }
    totals = {
        tenure: sum(f.value for f in facts if f.filters["household_tenure"] == tenure)
        for tenure in by_tenure
    }
    assert totals == {
        "All occupied households": 2_508_542,
        "Private rented: Total": 322_903,
    }
    first = next(
        f
        for f in facts
        if f.geography.id == "S00135307"
        and f.filters["household_tenure"] == "Private rented: Total"
    )
    assert first.value == 12


def test_output_area_geography_and_census_date(facts):
    assert {f.geography.level for f in facts} == {"statistical_scope"}
    assert {f.geography.vintage for f in facts} == {"oa_2022"}
    # NRS names output areas by code only.
    assert all(f.geography.name == f.geography.id for f in facts)
    assert all(f.geography.id.startswith("S00") for f in facts)
    assert {f.period.value for f in facts} == {2022}
    assert {f.period_coverage.start_date for f in facts} == {"2022-03-20"}
    assert {f.measure.concept for f in facts} == {"nrs.census2022_households"}


def test_private_rented_total_is_the_published_cell_not_a_sum(facts):
    package = load_source_package(PACKAGE)
    columns = {
        record_set.payload["measures"][0]["column"]
        for record_set in package.record_sets
        if record_set.payload["record_set_id"].endswith("private_rented_total")
    }
    assert columns == {"I"}
    rows = package.artifact.build_source_rows(2022)
    marked = [row for row in rows if row.values.get("Private rented: Total") == "-"]
    assert len(marked) == 4910
    ported = {
        f.geography.id
        for f in facts
        if f.filters["household_tenure"] == "Private rented: Total"
    }
    assert not ported & {row.values[""] for row in marked}
