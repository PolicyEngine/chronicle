"""Tests for deterministic offline artifact-fetch handoffs."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from chronicle.sources.offline_fetch import (
    OFFLINE_FETCH_MANIFEST_SCHEMA_VERSION,
    OfflineFetchManifestError,
    load_offline_fetch_manifest,
    validate_offline_fetch_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _artifact() -> dict[str, object]:
    return {
        "package_id": "statbel-fiscal-income-2023",
        "url": "https://statbel.fgov.be/open-data/fiscal-income-2023.csv",
        "expected_filename": "fiscal-income-2023.csv",
        "destination_path": (
            "db/data/statbel/fiscal_income_2023/fiscal-income-2023.csv"
        ),
        "manifest_path": "db/data/statbel/fiscal_income_2023/manifest.yaml",
        "manifest_year": 2023,
        "discovery_note": "Resolve through the Statbel machine-readable catalog.",
        "source_package_path": (
            "packages/statbel/fiscal_income_2023/source_package.yaml"
        ),
        "post_download_steps": [
            "Compute and record the publisher artifact SHA-256.",
            "Run the package validator.",
        ],
    }


def _manifest() -> dict[str, object]:
    return {
        "schema_version": OFFLINE_FETCH_MANIFEST_SCHEMA_VERSION,
        "generated_for": "Open Belgian aggregate source packages",
        "artifacts": [_artifact()],
    }


def test_load_accepts_an_omitted_unknown_sha256(tmp_path):
    path = tmp_path / "FETCH-MANIFEST-BE.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")

    manifest = load_offline_fetch_manifest(path, require_discovery_notes=True)

    assert manifest.schema_version == OFFLINE_FETCH_MANIFEST_SCHEMA_VERSION
    assert manifest.generated_for == "Open Belgian aggregate source packages"
    assert len(manifest.artifacts) == 1
    assert manifest.artifacts[0].expected_sha256 is None
    assert manifest.artifacts[0].manifest_year == 2023
    assert manifest.artifacts[0].post_download_steps == (
        "Compute and record the publisher artifact SHA-256.",
        "Run the package validator.",
    )


def test_existing_v1_fetch_manifest_remains_valid():
    manifest = load_offline_fetch_manifest(REPO_ROOT / "FETCH-MANIFEST.json")

    assert len(manifest.artifacts) == 3
    assert manifest.artifacts[-1].manifest_path.endswith(
        "manifest_fy2025_monthly_source_package.yaml"
    )


def test_discovery_notes_are_optional_by_default_but_can_be_required():
    payload = _manifest()
    del payload["artifacts"][0]["discovery_note"]

    manifest = validate_offline_fetch_manifest(payload)

    assert manifest.artifacts[0].discovery_note is None
    with pytest.raises(OfflineFetchManifestError, match="discovery_note"):
        validate_offline_fetch_manifest(payload, require_discovery_notes=True)


@pytest.mark.parametrize(
    "sha256",
    [
        "pending",
        "0" * 64,
        "A" * 64,
    ],
)
def test_rejects_unpinned_sha256_sentinels_and_nonlowercase_hashes(sha256):
    payload = _manifest()
    payload["artifacts"][0]["expected_sha256"] = sha256

    with pytest.raises(OfflineFetchManifestError, match="expected_sha256"):
        validate_offline_fetch_manifest(payload)


def test_accepts_a_lowercase_nonzero_sha256():
    payload = _manifest()
    payload["artifacts"][0]["expected_sha256"] = "a1" * 32

    manifest = validate_offline_fetch_manifest(payload)

    assert manifest.artifacts[0].expected_sha256 == "a1" * 32


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("destination_path", "/tmp/publisher.csv"),
        ("destination_path", "db/data/statbel/../publisher.csv"),
        ("manifest_path", "/db/data/statbel/manifest.yaml"),
        ("manifest_path", "db/data/statbel/../../manifest.yaml"),
        ("source_package_path", "/packages/statbel/source_package.yaml"),
        (
            "source_package_path",
            "packages/statbel/../source_package.yaml",
        ),
    ],
)
def test_rejects_absolute_and_traversing_repository_paths(field, value):
    payload = _manifest()
    payload["artifacts"][0][field] = value

    with pytest.raises(OfflineFetchManifestError, match=field):
        validate_offline_fetch_manifest(payload)


def test_rejects_duplicate_package_destination_pairs():
    payload = _manifest()
    payload["artifacts"].append(deepcopy(payload["artifacts"][0]))

    with pytest.raises(OfflineFetchManifestError, match="duplicates package_id"):
        validate_offline_fetch_manifest(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "http://statbel.fgov.be/data.csv"),
        ("expected_filename", "nested/data.csv"),
        ("destination_path", "packages/statbel/data.csv"),
        ("manifest_path", "db/data/statbel/artifact.json"),
        ("manifest_year", True),
        ("post_download_steps", []),
        ("source_package_path", "db/data/statbel/source_package.yaml"),
    ],
)
def test_rejects_malformed_required_artifact_fields(field, value):
    payload = _manifest()
    payload["artifacts"][0][field] = value

    with pytest.raises(OfflineFetchManifestError, match=field):
        validate_offline_fetch_manifest(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "ledger.offline_fetch_manifest.v2"),
        ("generated_for", ""),
        ("artifacts", []),
    ],
)
def test_rejects_malformed_manifest_fields(field, value):
    payload = _manifest()
    payload[field] = value

    with pytest.raises(OfflineFetchManifestError, match=field):
        validate_offline_fetch_manifest(payload)
