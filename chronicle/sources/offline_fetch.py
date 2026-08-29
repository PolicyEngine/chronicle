"""Validation for deterministic offline source-artifact fetch manifests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, NoReturn
from urllib.parse import urlsplit


OFFLINE_FETCH_MANIFEST_SCHEMA_VERSION = "ledger.offline_fetch_manifest.v1"

_LOWERCASE_SHA256 = re.compile(r"[0-9a-f]{64}")
_MISSING = object()


class OfflineFetchManifestError(ValueError):
    """Raised when an offline fetch manifest violates its deterministic contract."""


@dataclass(frozen=True)
class OfflineFetchArtifact:
    """One publisher artifact requested through an offline handoff."""

    package_id: str
    url: str
    expected_filename: str
    destination_path: str
    manifest_path: str
    manifest_year: int
    discovery_note: str | None
    post_download_steps: tuple[str, ...]
    expected_sha256: str | None = None
    source_package_path: str | None = None


@dataclass(frozen=True)
class OfflineFetchManifest:
    """A validated offline publisher-artifact fetch handoff."""

    schema_version: str
    generated_for: str
    artifacts: tuple[OfflineFetchArtifact, ...]


def load_offline_fetch_manifest(
    path: str | Path,
    *,
    require_discovery_notes: bool = False,
) -> OfflineFetchManifest:
    """Load and validate an offline fetch manifest from JSON."""

    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OfflineFetchManifestError(
            f"Could not read offline fetch manifest {manifest_path}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise OfflineFetchManifestError(
            f"Offline fetch manifest {manifest_path} is not valid JSON: {exc}"
        ) from exc

    return validate_offline_fetch_manifest(
        payload,
        source=str(manifest_path),
        require_discovery_notes=require_discovery_notes,
    )


def validate_offline_fetch_manifest(
    payload: object,
    *,
    source: str = "offline fetch manifest",
    require_discovery_notes: bool = False,
) -> OfflineFetchManifest:
    """Validate a parsed ``ledger.offline_fetch_manifest.v1`` mapping."""

    if not isinstance(payload, Mapping):
        _fail(source, "$", "must be a JSON object")

    schema_version = _required_string(payload, "schema_version", source=source)
    if schema_version != OFFLINE_FETCH_MANIFEST_SCHEMA_VERSION:
        _fail(
            source,
            "schema_version",
            f"must be {OFFLINE_FETCH_MANIFEST_SCHEMA_VERSION!r}",
        )

    generated_for = _required_string(payload, "generated_for", source=source)
    raw_artifacts = payload.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        _fail(source, "artifacts", "must be a nonempty list")

    artifacts: list[OfflineFetchArtifact] = []
    seen_package_destinations: dict[tuple[str, str], int] = {}
    for index, raw_artifact in enumerate(raw_artifacts):
        location = f"artifacts[{index}]"
        if not isinstance(raw_artifact, Mapping):
            _fail(source, location, "must be a JSON object")

        package_id = _required_string(
            raw_artifact,
            "package_id",
            source=source,
            parent=location,
        )
        url = _https_url(raw_artifact, source=source, parent=location)
        expected_filename = _expected_filename(
            raw_artifact,
            source=source,
            parent=location,
        )
        destination_path = _repo_path(
            raw_artifact,
            "destination_path",
            source=source,
            parent=location,
            required_prefix=("db", "data"),
        )
        manifest_path = _repo_path(
            raw_artifact,
            "manifest_path",
            source=source,
            parent=location,
            required_prefix=("db", "data"),
        )
        if not manifest_path.endswith(".yaml"):
            _fail(
                source,
                f"{location}.manifest_path",
                "must identify a YAML manifest",
            )
        manifest_year = raw_artifact.get("manifest_year", _MISSING)
        if type(manifest_year) is not int:
            _fail(
                source,
                f"{location}.manifest_year",
                "must be an integer",
            )

        discovery_note = _optional_string(
            raw_artifact,
            "discovery_note",
            source=source,
            parent=location,
            required=require_discovery_notes,
        )
        post_download_steps = _nonempty_string_list(
            raw_artifact,
            "post_download_steps",
            source=source,
            parent=location,
        )
        expected_sha256 = _optional_sha256(
            raw_artifact,
            source=source,
            parent=location,
        )

        source_package_path = None
        if "source_package_path" in raw_artifact:
            source_package_path = _repo_path(
                raw_artifact,
                "source_package_path",
                source=source,
                parent=location,
                required_prefix=("packages",),
                required_basename="source_package.yaml",
            )

        package_destination = (package_id, destination_path)
        prior_index = seen_package_destinations.get(package_destination)
        if prior_index is not None:
            _fail(
                source,
                location,
                (
                    "duplicates package_id and destination_path from "
                    f"artifacts[{prior_index}]"
                ),
            )
        seen_package_destinations[package_destination] = index

        artifacts.append(
            OfflineFetchArtifact(
                package_id=package_id,
                url=url,
                expected_filename=expected_filename,
                destination_path=destination_path,
                manifest_path=manifest_path,
                manifest_year=manifest_year,
                discovery_note=discovery_note,
                post_download_steps=post_download_steps,
                expected_sha256=expected_sha256,
                source_package_path=source_package_path,
            )
        )

    return OfflineFetchManifest(
        schema_version=schema_version,
        generated_for=generated_for,
        artifacts=tuple(artifacts),
    )


def _required_string(
    payload: Mapping[str, Any],
    field: str,
    *,
    source: str,
    parent: str | None = None,
) -> str:
    location = f"{parent}.{field}" if parent else field
    value = payload.get(field, _MISSING)
    if not isinstance(value, str) or not value.strip():
        _fail(source, location, "must be a nonempty string")
    return value


def _optional_string(
    payload: Mapping[str, Any],
    field: str,
    *,
    source: str,
    parent: str,
    required: bool,
) -> str | None:
    if field not in payload:
        if required:
            _fail(source, f"{parent}.{field}", "must be a nonempty string")
        return None
    return _required_string(payload, field, source=source, parent=parent)


def _https_url(
    payload: Mapping[str, Any],
    *,
    source: str,
    parent: str,
) -> str:
    url = _required_string(payload, "url", source=source, parent=parent)
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        _fail(source, f"{parent}.url", f"must be a valid HTTPS URL: {exc}")
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not parsed.hostname
        or any(character.isspace() for character in url)
    ):
        _fail(source, f"{parent}.url", "must be an HTTPS URL with a host")
    return url


def _expected_filename(
    payload: Mapping[str, Any],
    *,
    source: str,
    parent: str,
) -> str:
    filename = _required_string(
        payload,
        "expected_filename",
        source=source,
        parent=parent,
    )
    if (
        "/" in filename
        or "\\" in filename
        or filename in {".", ".."}
        or PurePosixPath(filename).name != filename
    ):
        _fail(source, f"{parent}.expected_filename", "must be a basename")
    return filename


def _repo_path(
    payload: Mapping[str, Any],
    field: str,
    *,
    source: str,
    parent: str,
    required_prefix: tuple[str, ...],
    required_basename: str | None = None,
) -> str:
    value = _required_string(payload, field, source=source, parent=parent)
    location = f"{parent}.{field}"
    if "\\" in value:
        _fail(source, location, "must use a relative POSIX repository path")

    raw_parts = value.split("/")
    path = PurePosixPath(value)
    if path.is_absolute():
        _fail(source, location, "must be relative")
    if any(part in {"", ".", ".."} for part in raw_parts):
        _fail(source, location, "must not contain empty or traversal segments")
    if path.parts[: len(required_prefix)] != required_prefix:
        required_root = "/".join(required_prefix)
        _fail(source, location, f"must be under {required_root}/")
    if len(path.parts) <= len(required_prefix):
        _fail(source, location, "must identify a file below the required root")
    if required_basename is not None and path.name != required_basename:
        _fail(source, location, f"must end with {required_basename}")
    return path.as_posix()


def _nonempty_string_list(
    payload: Mapping[str, Any],
    field: str,
    *,
    source: str,
    parent: str,
) -> tuple[str, ...]:
    value = payload.get(field, _MISSING)
    location = f"{parent}.{field}"
    if not isinstance(value, list) or not value:
        _fail(source, location, "must be a nonempty list")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            _fail(source, f"{location}[{index}]", "must be a nonempty string")
    return tuple(value)


def _optional_sha256(
    payload: Mapping[str, Any],
    *,
    source: str,
    parent: str,
) -> str | None:
    if "expected_sha256" not in payload:
        return None
    value = payload["expected_sha256"]
    location = f"{parent}.expected_sha256"
    if (
        not isinstance(value, str)
        or _LOWERCASE_SHA256.fullmatch(value) is None
        or value == "0" * 64
    ):
        _fail(
            source,
            location,
            "must be a nonzero lowercase 64-character hexadecimal SHA-256",
        )
    return value


def _fail(source: str, location: str, message: str) -> NoReturn:
    raise OfflineFetchManifestError(f"{source}: {location} {message}")
