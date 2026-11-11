"""Regression tests for the chronicle#343 high-value housing sources.

Two fact packages: the OBR costing of the high value council tax surcharge (2 April
2026) and the ONS house price statistics by 2024 constituency (year ending March 2026
edition). Three raw-only registrations, which Chronicle pins and never parses into
facts: HM Land Registry Price Paid Data (August 2026 release, the 32 yearly files and the
monthly change file), the UK House Price Index full file (July 2026) and the National
Statistics Postcode Lookup (August 2026). Values are the publishers' as fetched on
2026-10-12.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from chronicle.artifacts import (
    build_r2_key,
    inventory_source_artifacts,
    publish_source_artifacts,
)
from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import validate_consumer_fact_contract
from chronicle.core import validate_facts
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPOSITORY_ROOT / "db" / "data"

OBR = "obr-hvcts-costing-april-2026"
HPSSA = "ons-hpssa-pcon24-year-ending-march-2026"
FACT_COUNTS = {OBR: 63, HPSSA: 22940}

ENGLAND = "E92000001"

PPD_HOST = "https://price-paid-data.publicdata.landregistry.gov.uk"
PPD_YEARLY = "hmlr/price_paid_data_yearly_august_2026"
PPD_YEARS = range(1995, 2027)
# Wrangler's `r2 object put`, which publish-raw drives, refuses files above 300 MiB.
WRANGLER_MAX_UPLOAD = 300 * 1024 * 1024

# directory, package id, year, filename, publisher URL, sha256, bytes, vintage.
# No raw byte is committed: Price Paid carries Royal Mail and OS address-data terms,
# the NSPL zip is above GitHub's file limit, and each monthly UK HPI full file
# revises the last. Every entry is marked storage.local: false and R2 holds it.
RAW_SOURCES = (
    (
        PPD_YEARLY,
        "hmlr-price-paid-data-yearly-august-2026",
        2024,
        "pp-2024.csv",
        f"{PPD_HOST}/pp-2024.csv",
        "afec0cff353cc4570cc02795b78dbd270b4e678b5a0a50bc3e082c883abb7707",
        162_424_209,
        "ppd_2026_08",
    ),
    (
        "hmlr/price_paid_data_monthly_update_august_2026",
        "hmlr-price-paid-data-monthly-update-august-2026",
        2026,
        "pp-monthly-update-new-version.csv",
        f"{PPD_HOST}/pp-monthly-update-new-version.csv",
        "5236cb389b294f3352027fb3d01bf6f6f367fb99658cbf9ba9ffeef3c3e07d43",
        15_840_574,
        "ppd_2026_08",
    ),
    (
        "hmlr/uk_hpi_full_file_july_2026",
        "hmlr-uk-hpi-full-file-july-2026",
        2026,
        "UK-HPI-full-file-2026-07.csv",
        "https://publicdata.landregistry.gov.uk/market-trend-data/"
        "house-price-index-data/UK-HPI-full-file-2026-07.csv",
        "654a541934ba7b393a741e23bc0c6fb668690f562feb8a7b4fff62d653fd6607",
        35_012_747,
        "uk_hpi_2026_07",
    ),
    (
        "ons/nspl_august_2026",
        "ons-nspl-august-2026",
        2026,
        "NSPL_AUG_2026.zip",
        "https://www.arcgis.com/sharing/rest/content/items/"
        "9d8364ebae8b4439aa66cda440e54fc8/data",
        "f5d86a518d360cad67f0304f25574d3ce619f242d9ea6385a120abab7c15b15c",
        185_109_467,
        "nspl_2026_08",
    ),
)

# HM Land Registry's column order (guidance 'About the Price Paid Data'); the files
# carry no header row.
PPD_FIELDS = (
    "transaction_unique_identifier",
    "price",
    "date_of_transfer",
    "postcode",
    "property_type",
    "old_new",
    "duration",
    "paon",
    "saon",
    "street",
    "locality",
    "town_city",
    "district",
    "county",
    "ppd_category_type",
    "record_status",
)


@pytest.fixture(scope="module")
def built():
    cache = {}

    def facts(alias):
        if alias not in cache:
            cache[alias] = load_source_package(alias).build_facts(2026)
        return cache[alias]

    return facts


def _by(facts, **wanted):
    matches = [
        fact
        for fact in facts
        if all(
            (
                fact.period.value
                if key == "period"
                else fact.geography.id
                if key == "geography"
                else fact.measure.concept
                if key == "concept"
                else fact.filters.get(key)
            )
            == value
            for key, value in wanted.items()
        )
    ]
    return matches


def _value(facts, **wanted):
    matches = _by(facts, **wanted)
    assert len(matches) == 1, (wanted, len(matches))
    return matches[0].value


def test_issue_343_fact_packages_are_registered():
    assert set(FACT_COUNTS) <= set(SOURCE_PACKAGE_ALIASES)
    assert set(FACT_COUNTS) <= set(UK_BUNDLE_SOURCES)


@pytest.mark.parametrize("alias", sorted(FACT_COUNTS))
def test_issue_343_package_builds_valid_facts(alias, built):
    facts = built(alias)

    assert len(facts) == FACT_COUNTS[alias]
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid


def test_obr_properties_in_scope_by_band(built):
    facts = built(OBR)
    assert all(fact.assertion == "source_projection" for fact in facts)
    assert all(fact.provenance_class == "model_output" for fact in facts)
    assert {fact.geography.id for fact in facts} == {ENGLAND}

    expected = {
        # Table 1.1 (static) and Table 1.2 (post-behaviour), thousands, 2028-29.
        "static": {
            "gbp_2m_to_2_5m": 71,
            "gbp_2_5m_to_3_5m": 54,
            "gbp_3_5m_to_5m": 25,
            "over_gbp_5m": 15,
            None: 165,
        },
        "post_behaviour": {
            "gbp_2m_to_2_5m": 66,
            "gbp_2_5m_to_3_5m": 53,
            "gbp_3_5m_to_5m": 24,
            "over_gbp_5m": 14,
            None: 156,
        },
    }
    concept = "obr.hvcts_costing.properties_in_scope"
    for basis, bands in expected.items():
        for band, thousands in bands.items():
            matches = [
                fact
                for fact in _by(
                    facts, period=2028, concept=concept, behaviour_basis=basis
                )
                if fact.filters.get("property_value_band") == band
            ]
            assert len(matches) == 1, (basis, band)
            assert matches[0].value == thousands * 1000
    # The later years as published.
    assert (
        _value(
            facts,
            period=2030,
            concept=concept,
            behaviour_basis="static",
            property_value_band="gbp_2m_to_2_5m",
        )
        == 72_000
    )
    totals = {
        (fact.filters["behaviour_basis"], fact.period.value): fact.value
        for fact in facts
        if fact.measure.concept == concept and "property_value_band" not in fact.filters
    }
    assert totals == {
        ("static", 2028): 165_000,
        ("static", 2029): 166_000,
        ("static", 2030): 167_000,
        ("post_behaviour", 2028): 156_000,
        ("post_behaviour", 2029): 157_000,
        ("post_behaviour", 2030): 158_000,
    }


def test_obr_costing_lines_add_up(built):
    facts = built(OBR)
    concept = "obr.hvcts_costing.psnb_impact"
    published = {
        "static_costing": (0, 0, -605, -620, -635),
        "behavioural_response": (120, 155, 205, 190, 200),
        "price_capitalisation_bunching_and_supply": (0, 0, 30, 30, 30),
        "compliance_appeals_and_support_scheme": (0, 0, 120, 125, 125),
        "other_tax_heads": (120, 155, 55, 35, 45),
        "post_behavioural_costing": (120, 155, -400, -430, -435),
    }
    for line, values in published.items():
        for year, value in zip(range(2026, 2031), values, strict=True):
            assert _value(facts, period=year, concept=concept, costing_line=line) == (
                value * 1_000_000
            )
    for year in range(2026, 2031):
        line = {
            fact.filters["costing_line"]: fact.value
            for fact in _by(facts, period=year, concept=concept)
        }
        assert (
            line["static_costing"] + line["behavioural_response"]
            == (line["post_behavioural_costing"])
        )
        assert line["behavioural_response"] == (
            line["price_capitalisation_bunching_and_supply"]
            + line["compliance_appeals_and_support_scheme"]
            + line["other_tax_heads"]
        )


def test_obr_stated_parameters(built):
    facts = built(OBR)
    assert _value(facts, concept="obr.hvcts_costing.non_owner_occupied_share") == 40
    assert _value(facts, concept="obr.hvcts_costing.non_uk_resident_owner_share") == 14
    (take_up,) = _by(facts, concept="obr.hvcts_costing.support_scheme_take_up")
    assert take_up.value == 75
    assert take_up.entity.name == "household"
    assert [
        (constraint.variable, constraint.operator, constraint.value)
        for constraint in take_up.constraints
    ] == [("household_net_income", "<", 30000)]
    for fact in facts:
        if fact.measure.unit == "percent":
            assert fact.period.value == 2028


def _registered_constituencies() -> set[str]:
    path = DATA_ROOT / "ons/oa21_pcon_jul2024_lookup/ew_oa21_pcon24_lookup.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["PCON25CD"] for row in csv.DictReader(handle)}


def test_hpssa_covers_every_2024_constituency_in_england_and_wales(built):
    facts = built(HPSSA)
    seats = {fact.geography.id for fact in facts}

    assert len(seats) == 575
    assert seats == _registered_constituencies()
    assert {fact.geography.vintage for fact in facts} == {"pcon_2024"}
    assert {fact.period.value for fact in facts} == {2022, 2023, 2024, 2025}
    assert {fact.period.type for fact in facts} == {"fiscal_year"}


def test_hpssa_values_and_partition(built):
    facts = built(HPSSA)
    sales = "ons.hpssa.residential_property_sales"
    median = "ons.hpssa.median_price_paid"

    # Aldershot, year ending March 1996 to 2026 are on the same row; spot the latest.
    aldershot = [fact for fact in facts if fact.geography.id == "E14001063"]
    assert len(aldershot) == 40

    # Every seat-year's four property types sum to its all-types count.
    by_seat_year: dict[tuple[str, int], dict[str | None, float]] = {}
    for fact in facts:
        if fact.measure.concept != sales:
            continue
        key = (fact.geography.id, fact.period.value)
        by_seat_year.setdefault(key, {})[fact.filters.get("property_type")] = fact.value
    assert len(by_seat_year) == 575 * 4
    for parts in by_seat_year.values():
        assert parts.pop(None) == sum(parts.values())

    totals = {}
    for (_, year), parts in by_seat_year.items():
        totals[year] = totals.get(year, 0) + sum(parts.values())
    assert totals == {2022: 872_848, 2023: 692_252, 2024: 853_195, 2025: 659_366}

    # Suppressed medians ([x], fewer than five sales) emit no fact.
    medians = [fact for fact in facts if fact.measure.concept == median]
    assert len(medians) == 575 * 4 * 5 - 60
    assert all(fact.measure.unit == "gbp" for fact in medians)


def _manifest(directory: str) -> dict:
    return yaml.safe_load((DATA_ROOT / directory / "manifest.yaml").read_text())


def _expected_r2(source_id, package_id, year, sha256, filename, directory) -> dict:
    key = build_r2_key(
        source_id=source_id,
        package_id=package_id,
        year=year,
        sha256=sha256,
        filename=filename,
        package_path=DATA_ROOT / directory,
    )
    assert key == f"raw/uk/{source_id}/{package_id}/{year}/{sha256}/{filename}"
    return {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }


def _tracked(directory: str) -> set[str]:
    return set(
        subprocess.run(
            ["git", "ls-files", f"db/data/{directory}"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    )


@pytest.mark.parametrize(
    (
        "directory",
        "package_id",
        "year",
        "filename",
        "source_url",
        "sha256",
        "size_bytes",
        "vintage",
    ),
    RAW_SOURCES,
)
def test_raw_only_registration(
    directory,
    package_id,
    year,
    filename,
    source_url,
    sha256,
    size_bytes,
    vintage,
):
    """Each raw release is pinned, held in R2 only, and never parsed into facts."""
    manifest = _manifest(directory)
    entry = manifest["files"][year]
    source_id = directory.split("/")[0]

    assert manifest["source_id"] == source_id
    assert manifest["package_id"] == package_id
    assert entry["filename"] == filename
    assert entry["source_url"] == source_url
    assert entry["sha256"] == sha256
    assert entry["size_bytes"] == size_bytes
    assert entry["vintage"] == vintage
    assert entry["storage"]["local"] is False
    assert entry["storage"]["r2"] == _expected_r2(
        source_id, package_id, year, sha256, filename, directory
    )

    tracked = _tracked(directory)
    if tracked:
        # Untracked in a source checkout before commit; exact once committed.
        assert tracked == {f"db/data/{directory}/manifest.yaml"}

    assert package_id not in SOURCE_PACKAGE_ALIASES
    assert package_id not in UK_BUNDLE_SOURCES
    assert not (
        REPOSITORY_ROOT / "packages" / directory / "source_package.yaml"
    ).exists()


def test_price_paid_yearly_files_cover_one_release():
    """The 32 yearly files of one release, each small enough for publish-raw."""
    manifest = _manifest(PPD_YEARLY)
    package_id = manifest["package_id"]

    assert sorted(manifest["files"]) == list(PPD_YEARS)
    for year, entry in manifest["files"].items():
        assert entry["filename"] == f"pp-{year}.csv"
        assert entry["source_url"] == f"{PPD_HOST}/pp-{year}.csv"
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        assert 0 < entry["size_bytes"] < WRANGLER_MAX_UPLOAD
        assert entry["vintage"] == "ppd_2026_08"
        assert entry["storage"]["local"] is False
        assert entry["storage"]["r2"] == _expected_r2(
            "hmlr", package_id, year, entry["sha256"], entry["filename"], PPD_YEARLY
        )
    assert len({entry["sha256"] for entry in manifest["files"].values()}) == 32


def _uncommitted_paths() -> list[Path]:
    paths = [
        DATA_ROOT / PPD_YEARLY / entry["filename"]
        for entry in _manifest(PPD_YEARLY)["files"].values()
    ]
    paths += [
        DATA_ROOT / directory / filename
        for directory, _, _, filename, *_ in RAW_SOURCES
        if directory != PPD_YEARLY
    ]
    return paths


def test_raw_only_manifests_stay_valid_without_their_bytes(tmp_path):
    """A fresh clone has no raw bytes; inventory and publish-raw must not fail."""
    directories = sorted({source[0] for source in RAW_SOURCES})
    for directory in directories:
        target = tmp_path / "db" / "data" / directory
        target.mkdir(parents=True)
        (target / "manifest.yaml").write_bytes(
            (DATA_ROOT / directory / "manifest.yaml").read_bytes()
        )

    inventory = inventory_source_artifacts(tmp_path / "db" / "data")
    published = publish_source_artifacts(
        tmp_path / "db" / "data", wrangler_command="false"
    )

    assert inventory.valid
    assert inventory.counts["missing_count"] == 0
    assert inventory.counts["r2_only_count"] == 35
    assert published.valid
    assert published.counts["skipped_count"] == 35
    assert published.counts["uploaded_count"] == 0


def test_uncommitted_raw_bytes_are_ignored_by_git():
    for path in _uncommitted_paths():
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(path.relative_to(REPOSITORY_ROOT))],
            cwd=REPOSITORY_ROOT,
        )
        assert ignored.returncode == 0, path


@pytest.mark.skipif(
    not os.environ.get("LEDGER_VERIFY_LARGE_RAW"),
    reason="hashes about 5.8 GB of local bytes; set LEDGER_VERIFY_LARGE_RAW=1",
)
def test_uncommitted_raw_bytes_match_their_pins_when_present():
    pins = {
        DATA_ROOT / PPD_YEARLY / entry["filename"]: (
            entry["sha256"],
            entry["size_bytes"],
        )
        for entry in _manifest(PPD_YEARLY)["files"].values()
    }
    for directory, _, year, filename, *_ in RAW_SOURCES:
        entry = _manifest(directory)["files"][year]
        pins[DATA_ROOT / directory / filename] = (entry["sha256"], entry["size_bytes"])
    checked = 0
    for path, (sha256, size_bytes) in pins.items():
        if not path.exists():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 24), b""):
                digest.update(chunk)
        assert path.stat().st_size == size_bytes, path
        assert digest.hexdigest() == sha256, path
        checked += 1
    if not checked:
        pytest.skip("no uncommitted raw bytes are present locally")


def test_price_paid_monthly_file_matches_the_field_contract():
    path = (
        DATA_ROOT
        / "hmlr/price_paid_data_monthly_update_august_2026"
        / "pp-monthly-update-new-version.csv"
    )
    if not path.exists():
        pytest.skip("Price Paid bytes are archived in R2, not committed")
    text = path.read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text)))

    assert rows, "empty monthly file"
    assert {len(row) for row in rows} == {len(PPD_FIELDS)}
    records = [dict(zip(PPD_FIELDS, row, strict=True)) for row in rows]
    assert all(
        re.fullmatch(r"\{[0-9A-F-]{36}\}", r["transaction_unique_identifier"])
        for r in records
    )
    assert all(r["price"].isdigit() for r in records)
    assert all(
        re.fullmatch(r"\d{4}-\d{2}-\d{2} 00:00", r["date_of_transfer"]) for r in records
    )
    assert {r["property_type"] for r in records} <= set("DSTFO")
    assert {r["old_new"] for r in records} <= set("YN")
    assert {r["duration"] for r in records} <= {"F", "L", "U"}
    assert {r["ppd_category_type"] for r in records} == {"A", "B"}
    assert {r["record_status"] for r in records} <= {"A", "C", "D"}


def test_uk_hpi_full_file_header():
    path = DATA_ROOT / "hmlr/uk_hpi_full_file_july_2026/UK-HPI-full-file-2026-07.csv"
    if not path.exists():
        pytest.skip("UK HPI bytes are archived in R2, not committed")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = list(reader)

    assert len(header) == 54
    assert header[:10] == [
        "Date",
        "RegionName",
        "AreaCode",
        "AveragePrice",
        "Index",
        "IndexSA",
        "1m%Change",
        "12m%Change",
        "AveragePriceSA",
        "SalesVolume",
    ]
    for prefix in ("Detached", "SemiDetached", "Terraced", "Flat"):
        assert f"{prefix}Price" in header
        assert f"{prefix}Index" in header
    assert len(rows) == 151_920
    england_jan_2023 = [
        row for row in rows if row[2] == "E92000001" and row[0] == "01/01/2023"
    ]
    assert [row[4] for row in england_jan_2023] == ["100"]
    la_codes = {
        row[2] for row in rows if row[2][:3] in {"E06", "E07", "E08", "E09", "W06"}
    }
    assert len(la_codes) == 317
    # The Isles of Scilly have no series; Microcosm's uprating join must fall back.
    assert "E06000053" not in la_codes
