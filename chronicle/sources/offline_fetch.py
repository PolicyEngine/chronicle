"""Validation for deterministic offline source-artifact fetch manifests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from ipaddress import ip_address
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, NoReturn
from urllib.parse import urlsplit

from chronicle.epoch import SCHEMA_IDS, schema_id

OFFLINE_FETCH_MANIFEST_SCHEMA_VERSION = schema_id("offline_fetch_manifest")

_LOWERCASE_SHA256 = re.compile(r"[0-9a-f]{64}")
_MISSING = object()
_MANIFEST_FIELDS = frozenset(
    {"schema_version", "generated_for", "artifacts", "final_validation"}
)
_ARTIFACT_FIELDS = frozenset(
    {
        "package_id",
        "url",
        "expected_filename",
        "destination_path",
        "manifest_path",
        "manifest_year",
        "discovery_note",
        "post_download_steps",
        "expected_sha256",
        "source_package_path",
        # Existing v1 extensions used by FETCH-MANIFEST.json.
        "r2",
        "replaces_synthetic_fixture",
        "already_archived",
        "archive_member",
        "note_new_vintage_sha256",
    }
)
_R2_FIELDS = frozenset(
    {"provider", "bucket", "key", "uri", "key_template", "uri_template"}
)


class OfflineFetchManifestError(ValueError):
    """Raised when an offline fetch manifest violates its deterministic contract."""


@dataclass(frozen=True)
class OfflineFetchR2Location:
    """A validated R2 location or content-addressed location template."""

    provider: str
    bucket: str
    key: str | None
    uri: str | None
    key_template: str | None
    uri_template: str | None


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
    r2: OfflineFetchR2Location | None = None
    replaces_synthetic_fixture: bool | None = None
    already_archived: bool | None = None
    archive_member: str | None = None
    note_new_vintage_sha256: str | None = None


@dataclass(frozen=True)
class OfflineFetchManifest:
    """A validated offline publisher-artifact fetch handoff."""

    schema_version: str
    generated_for: str
    artifacts: tuple[OfflineFetchArtifact, ...]
    final_validation: tuple[str, ...] = ()


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
    """Validate a parsed offline-fetch manifest from either accepted epoch."""

    if not isinstance(payload, Mapping):
        _fail(source, "$", "must be a JSON object")
    _reject_unknown_fields(payload, _MANIFEST_FIELDS, source=source, location="$")

    schema_version = _required_string(payload, "schema_version", source=source)
    offline_fetch_schema = SCHEMA_IDS["offline_fetch_manifest"]
    if schema_version not in offline_fetch_schema.accepted:
        _fail(
            source,
            "schema_version",
            f"must be {offline_fetch_schema.ledger!r} or "
            f"{offline_fetch_schema.chronicle!r}",
        )

    generated_for = _required_string(payload, "generated_for", source=source)
    raw_artifacts = payload.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        _fail(source, "artifacts", "must be a nonempty list")
    final_validation = _optional_string_list(
        payload,
        "final_validation",
        source=source,
        parent=None,
    )

    artifacts: list[OfflineFetchArtifact] = []
    seen_destinations: dict[str, int] = {}
    seen_manifest_paths: dict[str, int] = {}
    for index, raw_artifact in enumerate(raw_artifacts):
        location = f"artifacts[{index}]"
        if not isinstance(raw_artifact, Mapping):
            _fail(source, location, "must be a JSON object")
        _reject_unknown_fields(
            raw_artifact,
            _ARTIFACT_FIELDS,
            source=source,
            location=location,
        )

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
        if PurePosixPath(destination_path).name != expected_filename:
            _fail(
                source,
                f"{location}.destination_path",
                "must end with expected_filename",
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
        if (
            PurePosixPath(manifest_path).parent
            != PurePosixPath(destination_path).parent
        ):
            _fail(
                source,
                f"{location}.manifest_path",
                "must be beside destination_path",
            )
        if destination_path == manifest_path:
            _fail(
                source,
                f"{location}.destination_path",
                "must not overwrite manifest_path",
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
            "expected_sha256",
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

        r2 = _optional_r2(raw_artifact, source=source, parent=location)
        replaces_synthetic_fixture = _optional_bool(
            raw_artifact,
            "replaces_synthetic_fixture",
            source=source,
            parent=location,
        )
        already_archived = _optional_bool(
            raw_artifact,
            "already_archived",
            source=source,
            parent=location,
        )
        archive_member = _optional_basename(
            raw_artifact,
            "archive_member",
            source=source,
            parent=location,
        )
        note_new_vintage_sha256 = _optional_sha256(
            raw_artifact,
            "note_new_vintage_sha256",
            source=source,
            parent=location,
        )

        prior_index = seen_destinations.get(destination_path)
        if prior_index is not None:
            _fail(
                source,
                location,
                (f"duplicates destination_path from artifacts[{prior_index}]"),
            )
        prior_manifest_index = seen_manifest_paths.get(destination_path)
        if prior_manifest_index is not None:
            _fail(
                source,
                f"{location}.destination_path",
                (
                    "must not overwrite manifest_path from "
                    f"artifacts[{prior_manifest_index}]"
                ),
            )
        prior_destination_index = seen_destinations.get(manifest_path)
        if prior_destination_index is not None:
            _fail(
                source,
                f"{location}.manifest_path",
                (
                    "must not identify destination_path from "
                    f"artifacts[{prior_destination_index}]"
                ),
            )
        seen_destinations[destination_path] = index
        seen_manifest_paths.setdefault(manifest_path, index)

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
                r2=r2,
                replaces_synthetic_fixture=replaces_synthetic_fixture,
                already_archived=already_archived,
                archive_member=archive_member,
                note_new_vintage_sha256=note_new_vintage_sha256,
            )
        )

    return OfflineFetchManifest(
        schema_version=schema_version,
        generated_for=generated_for,
        artifacts=tuple(artifacts),
        final_validation=final_validation,
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
    if _has_control_characters(url):
        _fail(source, f"{parent}.url", "must not contain control characters")
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError as exc:
        _fail(source, f"{parent}.url", f"must be a valid HTTPS URL: {exc}")
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not parsed.hostname
        or any(character.isspace() for character in url)
    ):
        _fail(source, f"{parent}.url", "must be an HTTPS URL with a host")
    if parsed.username is not None or parsed.password is not None:
        _fail(source, f"{parent}.url", "must not contain user information")

    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        _fail(source, f"{parent}.url", "must use a public publisher host")
    try:
        address = ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            _fail(source, f"{parent}.url", "must use a public IP address")
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
    if _has_control_characters(filename):
        _fail(
            source,
            f"{parent}.expected_filename",
            "must not contain control characters",
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
    if _has_control_characters(value):
        _fail(source, location, "must not contain control characters")
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
    parent: str | None,
) -> tuple[str, ...]:
    value = payload.get(field, _MISSING)
    location = f"{parent}.{field}" if parent else field
    if not isinstance(value, list) or not value:
        _fail(source, location, "must be a nonempty list")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            _fail(source, f"{location}[{index}]", "must be a nonempty string")
    return tuple(value)


def _optional_sha256(
    payload: Mapping[str, Any],
    field: str,
    *,
    source: str,
    parent: str,
) -> str | None:
    if field not in payload:
        return None
    value = payload[field]
    location = f"{parent}.{field}"
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


def _optional_string_list(
    payload: Mapping[str, Any],
    field: str,
    *,
    source: str,
    parent: str | None,
) -> tuple[str, ...]:
    if field not in payload:
        return ()
    return _nonempty_string_list(
        payload,
        field,
        source=source,
        parent=parent,
    )


def _optional_bool(
    payload: Mapping[str, Any],
    field: str,
    *,
    source: str,
    parent: str,
) -> bool | None:
    if field not in payload:
        return None
    value = payload[field]
    if type(value) is not bool:
        _fail(source, f"{parent}.{field}", "must be a boolean")
    return value


def _optional_basename(
    payload: Mapping[str, Any],
    field: str,
    *,
    source: str,
    parent: str,
) -> str | None:
    if field not in payload:
        return None
    value = _required_string(payload, field, source=source, parent=parent)
    if (
        _has_control_characters(value)
        or "/" in value
        or "\\" in value
        or value in {".", ".."}
        or PurePosixPath(value).name != value
    ):
        _fail(source, f"{parent}.{field}", "must be a safe basename")
    return value


def _optional_r2(
    payload: Mapping[str, Any],
    *,
    source: str,
    parent: str,
) -> OfflineFetchR2Location | None:
    if "r2" not in payload:
        return None
    value = payload["r2"]
    location = f"{parent}.r2"
    if not isinstance(value, Mapping):
        _fail(source, location, "must be a JSON object")
    _reject_unknown_fields(value, _R2_FIELDS, source=source, location=location)

    provider = _required_string(value, "provider", source=source, parent=location)
    if provider != "r2":
        _fail(source, f"{location}.provider", "must be 'r2'")
    bucket = _required_string(value, "bucket", source=source, parent=location)
    key = _optional_string(value, "key", source=source, parent=location, required=False)
    uri = _optional_string(value, "uri", source=source, parent=location, required=False)
    key_template = _optional_string(
        value,
        "key_template",
        source=source,
        parent=location,
        required=False,
    )
    uri_template = _optional_string(
        value,
        "uri_template",
        source=source,
        parent=location,
        required=False,
    )

    if (key is None) != (uri is None):
        _fail(source, location, "must provide key and uri together")
    if (key_template is None) != (uri_template is None):
        _fail(source, location, "must provide key_template and uri_template together")
    if key is None and key_template is None:
        _fail(source, location, "must provide a location or location template")
    for field_name, item in (
        ("bucket", bucket),
        ("key", key),
        ("uri", uri),
        ("key_template", key_template),
        ("uri_template", uri_template),
    ):
        if item is not None and _has_control_characters(item):
            _fail(
                source,
                f"{location}.{field_name}",
                "must not contain control characters",
            )

    return OfflineFetchR2Location(
        provider=provider,
        bucket=bucket,
        key=key,
        uri=uri,
        key_template=key_template,
        uri_template=uri_template,
    )


def _reject_unknown_fields(
    payload: Mapping[Any, Any],
    allowed: frozenset[str],
    *,
    source: str,
    location: str,
) -> None:
    unknown = sorted(repr(field) for field in payload if field not in allowed)
    if unknown:
        _fail(source, location, "contains unknown fields: " + ", ".join(unknown))


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _fail(source: str, location: str, message: str) -> NoReturn:
    raise OfflineFetchManifestError(f"{source}: {location} {message}")
