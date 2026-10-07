"""Tests for deterministic offline artifact-fetch handoffs."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from chronicle.epoch import SCHEMA_IDS
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
    assert manifest.final_validation
    assert manifest.artifacts[0].r2 is not None
    assert manifest.artifacts[0].r2.bucket == "ledger-raw"
    assert manifest.artifacts[0].replaces_synthetic_fixture is True
    assert manifest.artifacts[-1].already_archived is True
    assert manifest.artifacts[-1].archive_member == "FY25.xlsx"
    assert manifest.artifacts[-1].manifest_path.endswith(
        "manifest_fy2025_monthly_source_package.yaml"
    )


def test_accepts_chronicle_epoch_and_keeps_ledger_emit_default():
    schema_pair = SCHEMA_IDS["offline_fetch_manifest"]
    payload = _manifest()
    payload["schema_version"] = schema_pair.chronicle

    manifest = validate_offline_fetch_manifest(payload)

    assert manifest.schema_version == schema_pair.chronicle
    assert OFFLINE_FETCH_MANIFEST_SCHEMA_VERSION == schema_pair.ledger


def test_rejects_unknown_schema_and_names_both_epochs():
    schema_pair = SCHEMA_IDS["offline_fetch_manifest"]
    payload = _manifest()
    payload["schema_version"] = "future.offline_fetch_manifest.v9"

    with pytest.raises(OfflineFetchManifestError) as error:
        validate_offline_fetch_manifest(payload)

    message = str(error.value)
    assert schema_pair.ledger in message
    assert schema_pair.chronicle in message


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


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@example.com/data.csv",
        "https://localhost/data.csv",
        "https://publisher.localhost/data.csv",
        "https://127.0.0.1/data.csv",
        "https://10.0.0.1/data.csv",
        "https://[::1]/data.csv",
    ],
)
def test_rejects_userinfo_and_nonpublic_fetch_hosts(url):
    payload = _manifest()
    payload["artifacts"][0]["url"] = url

    with pytest.raises(OfflineFetchManifestError, match="url"):
        validate_offline_fetch_manifest(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expected_filename", "publisher\x00.csv"),
        (
            "destination_path",
            "db/data/statbel/fiscal_income_2023/publisher\n.csv",
        ),
        (
            "manifest_path",
            "db/data/statbel/fiscal_income_2023/manifest\x7f.yaml",
        ),
        (
            "source_package_path",
            "packages/statbel/fiscal_income_2023\x00/source_package.yaml",
        ),
    ],
)
def test_rejects_control_characters_in_filenames_and_paths(field, value):
    payload = _manifest()
    payload["artifacts"][0][field] = value

    with pytest.raises(OfflineFetchManifestError, match=field):
        validate_offline_fetch_manifest(payload)


def test_rejects_unknown_manifest_and_artifact_fields():
    payload = _manifest()
    payload["expected_sha25"] = "typo"

    with pytest.raises(OfflineFetchManifestError, match="expected_sha25"):
        validate_offline_fetch_manifest(payload)

    payload = _manifest()
    payload["artifacts"][0]["expected_sha25"] = "typo"

    with pytest.raises(OfflineFetchManifestError, match="expected_sha25"):
        validate_offline_fetch_manifest(payload)


def test_rejects_duplicate_destinations():
    payload = _manifest()
    payload["artifacts"].append(deepcopy(payload["artifacts"][0]))

    with pytest.raises(OfflineFetchManifestError, match="duplicates destination_path"):
        validate_offline_fetch_manifest(payload)

    payload = _manifest()
    duplicate = deepcopy(payload["artifacts"][0])
    duplicate["package_id"] = "another-package"
    payload["artifacts"].append(duplicate)

    with pytest.raises(OfflineFetchManifestError, match="duplicates destination_path"):
        validate_offline_fetch_manifest(payload)


def test_rejects_destination_filename_and_manifest_directory_mismatches():
    payload = _manifest()
    payload["artifacts"][0]["destination_path"] = (
        "db/data/statbel/fiscal_income_2023/not-the-expected-file.csv"
    )

    with pytest.raises(OfflineFetchManifestError, match="expected_filename"):
        validate_offline_fetch_manifest(payload)

    payload = _manifest()
    payload["artifacts"][0]["manifest_path"] = (
        "db/data/statbel/another_package/manifest.yaml"
    )

    with pytest.raises(OfflineFetchManifestError, match="beside destination_path"):
        validate_offline_fetch_manifest(payload)


def test_rejects_destination_paths_that_can_overwrite_manifests():
    payload = _manifest()
    artifact = payload["artifacts"][0]
    artifact["expected_filename"] = "manifest.yaml"
    artifact["destination_path"] = artifact["manifest_path"]

    with pytest.raises(OfflineFetchManifestError, match="overwrite manifest_path"):
        validate_offline_fetch_manifest(payload)

    payload = _manifest()
    first = payload["artifacts"][0]
    second = deepcopy(first)
    second["package_id"] = "another-package"
    second["expected_filename"] = "manifest.yaml"
    second["destination_path"] = first["manifest_path"]
    second["manifest_path"] = "db/data/statbel/fiscal_income_2023/another-manifest.yaml"
    payload["artifacts"].append(second)

    with pytest.raises(
        OfflineFetchManifestError,
        match="overwrite manifest_path from artifacts\\[0\\]",
    ):
        validate_offline_fetch_manifest(payload)

    payload["artifacts"].reverse()
    with pytest.raises(
        OfflineFetchManifestError,
        match="identify destination_path from artifacts\\[0\\]",
    ):
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
