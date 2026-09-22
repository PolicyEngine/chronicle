"""Tests for Chronicle's canonical UK geography-name register (chronicle#281).

The register answers with one name per identifier so a consumer target that
selects facts from two packages for one area sees one name. These tests pin
what it is made of - ONS lookup artifacts Chronicle already pins, at the
checksums the manifests record - and that the export uses it without losing the
publisher's own text.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from chronicle.consumer_contract import _geography_row_payload
from chronicle.core import (
    AggregateFact,
    Aggregation,
    EntityDimension,
    GeographyDimension,
    Measure,
    PeriodDimension,
    SourceProvenance,
)
from chronicle.geography_names import (
    REGISTER_PATH,
    canonical_geography_level,
    canonical_geography_name,
    register_size,
)

_REPO_ROOT = Path(__file__).parents[1]
_REGISTER = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))


def _fact(geography_id: str, name: str | None, level: str = "local_authority"):
    return AggregateFact(
        source_record_id="test.record",
        measure=Measure(concept="test.concept", unit="count"),
        value=1,
        aggregation=Aggregation(method="sum"),
        period=PeriodDimension(type="tax_year", value=2023),
        geography=GeographyDimension(level=level, id=geography_id, name=name),
        entity=EntityDimension(name="person"),
        domain="test",
        provenance_class="administrative",
        source=SourceProvenance(
            source_name="test",
            source_table="test",
            source_file="test.csv",
            url=None,
            vintage="v",
            extracted_at="2026-09-21",
            extraction_method="test",
        ),
    )


def test_register_covers_every_tier_the_uk_packages_publish():
    assert register_size() == len(_REGISTER["names"]) == 953
    levels = set(_REGISTER["levels"].values())
    assert levels == {"local_authority", "region", "country", "constituency"}
    assert all(name.strip() for name in _REGISTER["names"].values())


@pytest.mark.parametrize(
    ("geography_id", "canonical", "level"),
    [
        # HMRC appends " UA" to every English unitary; the register does not.
        ("E06000001", "Hartlepool", "local_authority"),
        # MHCLG drops ", City of" and HMRC keeps an older form; ONS has both.
        ("E06000010", "Kingston upon Hull, City of", "local_authority"),
        # Two ONS packages spell this region two ways (chronicle#281).
        ("E12000003", "Yorkshire and The Humber", "region"),
        # DWP carries the circumflex, HMRC and one ONS package do not.
        ("W07000112", "Ynys Môn", "constituency"),
        # HMRC capitalises the "super" that ONS and DWP leave lower case.
        ("E14001581", "Weston-super-Mare", "constituency"),
        # DESNZ writes "(inc unallocated)" on the country totals it publishes.
        ("K03000001", "Great Britain", "country"),
        ("S92000003", "Scotland", "country"),
    ],
)
def test_register_answers_the_identifiers_publishers_spell_differently(
    geography_id,
    canonical,
    level,
):
    assert canonical_geography_name(geography_id) == canonical
    assert canonical_geography_level(geography_id) == level


def test_an_identifier_the_register_does_not_carry_has_no_canonical_name():
    assert canonical_geography_name("E01000001") is None
    assert canonical_geography_name("") is None
    assert canonical_geography_name(None) is None


def test_every_register_source_is_a_pinned_artifact_at_the_manifest_checksum():
    # Not every manifest names a package (the Eurostat ones predate the field),
    # and glob order differs between filesystems, so index them first.
    directories = {}
    for path in sorted((_REPO_ROOT / "db" / "data").glob("*/*/manifest.yaml")):
        package_id = (yaml.safe_load(path.read_text()) or {}).get("package_id")
        if package_id:
            directories[package_id] = path.parent

    assert _REGISTER["sources"]
    for source in _REGISTER["sources"]:
        directory = directories[source["package_id"]]
        manifest = yaml.safe_load((directory / "manifest.yaml").read_text())
        entry = next(iter(manifest["files"].values()))
        assert entry["filename"] == source["filename"]
        assert entry["sha256"] == source["sha256"]
        content = (directory / source["filename"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == source["sha256"]


def test_export_names_a_known_area_from_the_register_and_keeps_publisher_text():
    payload = _geography_row_payload(_fact("E06000001", "Hartlepool UA"))

    assert payload["name"] == "Hartlepool"
    assert payload["publisher_name"] == "Hartlepool UA"


def test_export_omits_publisher_name_when_the_publisher_already_agrees():
    payload = _geography_row_payload(_fact("E06000001", "Hartlepool"))

    assert payload["name"] == "Hartlepool"
    assert "publisher_name" not in payload


def test_export_keeps_the_publisher_name_for_an_area_outside_the_register():
    payload = _geography_row_payload(_fact("E01000001", "Some Output Area", "msoa"))

    assert payload["name"] == "Some Output Area"
    assert "publisher_name" not in payload


def test_export_names_nothing_when_neither_the_register_nor_the_source_does():
    payload = _geography_row_payload(_fact("E01000001", None, "msoa"))

    assert "name" not in payload
    assert "publisher_name" not in payload


def test_a_wrong_level_on_a_known_identifier_still_gets_its_register_name():
    payload = _geography_row_payload(_fact("E12000003", "Yorkshire and the Humber"))

    assert payload["name"] == "Yorkshire and The Humber"
    assert payload["publisher_name"] == "Yorkshire and the Humber"
