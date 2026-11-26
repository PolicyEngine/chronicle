"""Read-only raw artifact verification against a binary-emitting fake Wrangler."""

from __future__ import annotations

import base64
import hashlib
import json
import random
import shlex
import sys
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pytest
import yaml

from chronicle.artifacts import build_r2_key, verify_raw_artifacts
from chronicle.cli import main as cli_main
from chronicle.harness import main as harness_main
from policyengine_chronicle.cli import main as public_cli_main


class FakeWrangler:
    """Use an executable fixture, like the existing publish-raw tests."""

    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.config = directory / "remote.json"
        self.log = directory / "commands.jsonl"
        driver = directory / "driver.py"
        driver.write_text(
            "import base64, json, pathlib, sys\n"
            "config_path, log_path = map(pathlib.Path, sys.argv[1:3])\n"
            "args = sys.argv[3:]\n"
            "with log_path.open('a') as log:\n"
            "    log.write(json.dumps(args) + '\\n')\n"
            "if len(args) != 6 or args[:3] != ['r2', 'object', 'get'] "
            "or args[4:] != ['--remote', '--pipe']:\n"
            "    sys.stderr.write('Unsupported command')\n"
            "    sys.exit(2)\n"
            "config = json.loads(config_path.read_text())\n"
            "location = args[3]\n"
            "if location in config['errors']:\n"
            "    sys.stderr.write(config['errors'][location])\n"
            "    sys.exit(1)\n"
            "if location not in config['objects']:\n"
            "    sys.stderr.write('NoSuchKey: specified key does not exist')\n"
            "    sys.exit(1)\n"
            "sys.stderr.write(config.get('diagnostics', ''))\n"
            "sys.stderr.flush()\n"
            "payload = base64.b64decode(config['objects'][location])\n"
            "for offset in range(0, len(payload), 65536):\n"
            "    sys.stdout.buffer.write(payload[offset:offset + 65536])\n",
            encoding="utf-8",
        )
        executable = directory / "wrangler"
        executable.write_text(
            "#!/bin/sh\nexec "
            + " ".join(
                shlex.quote(str(value))
                for value in (sys.executable, driver, self.config, self.log)
            )
            + ' "$@"\n',
            encoding="utf-8",
        )
        executable.chmod(0o755)
        self.command = str(executable)
        self.set_remote({})

    def set_remote(self, objects: dict[str, bytes], errors=None, *, diagnostics=""):
        self.config.write_text(
            json.dumps(
                {
                    "objects": {
                        key: base64.b64encode(value).decode("ascii")
                        for key, value in objects.items()
                    },
                    "errors": errors or {},
                    "diagnostics": diagnostics,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    @property
    def commands(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]


def _add_artifact(
    root,
    payload=b"official NZ source bytes",
    *,
    source_id="ird",
    package_id="ird-wff",
    year=2024,
    filename="wff.xlsx",
    manifest_filename="manifest.yaml",
    prefix=None,
    bucket="ledger-raw",
    local=True,
):
    directory = root / source_id / package_id
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / manifest_filename
    manifest = (
        yaml.safe_load(manifest_path.read_text())
        if manifest_path.exists()
        else {"source_id": source_id, "package_id": package_id, "files": {}}
    )
    digest = hashlib.sha256(payload).hexdigest()
    key = build_r2_key(
        source_id=source_id,
        package_id=package_id,
        year=year,
        sha256=digest,
        filename=filename,
        prefix=prefix,
        package_path=manifest_path,
    )
    manifest["files"][year] = {
        "filename": filename,
        "sha256": digest,
        "size_bytes": len(payload),
        "storage": {"r2": {"provider": "r2", "bucket": bucket, "key": key}},
    }
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    if local:
        (directory / filename).write_bytes(payload)
    return manifest_path, key


def _edit_artifact(manifest_path, edit, year=2024):
    manifest = yaml.safe_load(manifest_path.read_text())
    edit(manifest["files"][year])
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))


def _snapshot(root):
    return {
        str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
        for path in sorted(root.rglob("*"))
    }


def _verify(root, fake, **options):
    return verify_raw_artifacts(root, wrangler_command=fake.command, **options)


def test_verify_raw_streams_binary_and_reports_pinned_measurements(tmp_path):
    root = tmp_path / "db" / "data"
    payload = bytes(range(256)) * 8192 + b"\x00\xff\xfe"
    manifest_path, key = _add_artifact(root, payload)
    fake = FakeWrangler(tmp_path / "fake")
    fake.set_remote({f"ledger-raw/{key}": payload}, diagnostics="D" * 131072)
    before = _snapshot(root)

    report = _verify(root, fake)

    assert report.valid
    assert report.counts["manifest_count"] == 1
    assert report.counts["artifact_count"] == 1
    assert report.counts["r2_link_count"] == 1
    assert report.counts["verified_count"] == 1
    assert report.counts["failed_count"] == 0
    entry = report.entries[0]
    assert entry.status == "verified"
    assert entry.manifest_path == str(manifest_path)
    assert entry.source_id == "ird"
    assert entry.package_id == "ird-wff"
    assert entry.year == "2024"
    assert entry.filename == "wff.xlsx"
    assert entry.canonical_key == key
    assert entry.r2_location.key == key
    assert entry.r2_location.bucket == "ledger-raw"
    assert entry.sha256_expected == hashlib.sha256(payload).hexdigest()
    assert entry.sha256_remote == entry.sha256_expected == entry.sha256_local
    assert entry.size_bytes_remote == entry.size_bytes_expected == len(payload)
    assert entry.size_bytes_local == len(payload)
    assert entry.fetch.ok
    assert entry.fetch.stdout == ""
    assert entry.fetch.stderr == "D" * 65536
    assert entry.errors == report.errors == ()
    assert fake.commands == [
        ["r2", "object", "get", f"ledger-raw/{key}", "--remote", "--pipe"]
    ]
    assert _snapshot(root) == before
    with pytest.raises(FrozenInstanceError):
        report.root = "changed"
    with pytest.raises(FrozenInstanceError):
        entry.status = "changed"


def test_verify_raw_allows_absent_local_file(tmp_path):
    root = tmp_path / "db" / "data"
    payload = b"remote-only artifact"
    _, key = _add_artifact(root, payload, local=False)
    fake = FakeWrangler(tmp_path / "fake")
    fake.set_remote({f"ledger-raw/{key}": payload})
    before = _snapshot(root)

    report = _verify(root, fake)

    assert report.valid
    assert report.entries[0].status == "verified"
    assert report.entries[0].sha256_local is None
    assert report.entries[0].size_bytes_local is None
    assert _snapshot(root) == before


@pytest.mark.parametrize(
    "status",
    [
        "key_mismatch",
        "digest_mismatch",
        "size_mismatch",
        "missing_remote",
        "no_r2_location",
        "fetch_error",
        "invalid_manifest",
    ],
)
def test_verify_raw_failure_statuses_are_read_only(tmp_path, status):
    root = tmp_path / "db" / "data"
    payload = b"original official payload"
    manifest_path, key = _add_artifact(root, payload)
    fake = FakeWrangler(tmp_path / "fake")
    objects = {f"ledger-raw/{key}": payload}
    errors = {}
    if status == "key_mismatch":
        _edit_artifact(
            manifest_path,
            lambda entry: entry["storage"]["r2"].update(
                key=key.replace("raw/nz/", "raw/")
            ),
        )
    elif status == "digest_mismatch":
        objects[f"ledger-raw/{key}"] = b"X" + payload[1:]
    elif status == "size_mismatch":
        objects[f"ledger-raw/{key}"] = payload[:-1]
    elif status == "missing_remote":
        objects = {}
    elif status == "no_r2_location":
        _edit_artifact(manifest_path, lambda entry: entry.pop("storage"))
    elif status == "fetch_error":
        errors[f"ledger-raw/{key}"] = "Authentication failed"
    elif status == "invalid_manifest":
        _edit_artifact(manifest_path, lambda entry: entry.update(size_bytes=True))
    fake.set_remote(objects, errors)
    before = _snapshot(root)

    report = _verify(root, fake)

    assert not report.valid
    assert report.entries[0].status == status
    assert report.counts["verified_count"] == 0
    assert report.counts["failed_count"] == 1
    assert report.counts[f"{status}_count"] == 1
    assert _snapshot(root) == before
    assert all(command[:3] == ["r2", "object", "get"] for command in fake.commands)
    assert not any("put" in command or "delete" in command for command in fake.commands)
    if status in {"key_mismatch", "no_r2_location", "invalid_manifest"}:
        assert fake.commands == []
        assert report.entries[0].fetch is None


@pytest.mark.parametrize("status", ["digest_mismatch", "size_mismatch"])
def test_verify_raw_compares_present_local_file(tmp_path, status):
    root = tmp_path / "db" / "data"
    payload = b"official source bytes"
    manifest_path, key = _add_artifact(root, payload)
    local = manifest_path.parent / "wff.xlsx"
    local.write_bytes(
        b"X" + payload[1:] if status == "digest_mismatch" else payload[:-1]
    )
    fake = FakeWrangler(tmp_path / "fake")
    fake.set_remote({f"ledger-raw/{key}": payload})

    report = _verify(root, fake)

    assert not report.valid
    assert report.entries[0].status == status
    assert report.entries[0].sha256_remote == hashlib.sha256(payload).hexdigest()
    assert (
        report.entries[0].sha256_local == hashlib.sha256(local.read_bytes()).hexdigest()
    )
    assert report.entries[0].size_bytes_local == local.stat().st_size


def test_verify_raw_rejects_malformed_entry_fields(tmp_path, capsys):
    root = tmp_path / "db" / "data"
    manifest_path, key = _add_artifact(root)
    original = manifest_path.read_bytes()
    fake = FakeWrangler(tmp_path / "fake")
    fake.set_remote({f"ledger-raw/{key}": b"official NZ source bytes"})
    changes = [
        lambda entry: entry.update(filename=None),
        lambda entry: entry.update(filename=123),
        lambda entry: entry.update(sha256="not-a-digest"),
        lambda entry: entry.update(sha256="x" * 64),
        lambda entry: entry.update(sha256=date(2024, 1, 1)),
        lambda entry: entry.update(sha256={"not", "a", "digest"}),
        lambda entry: entry.update(sha256=b"binary digest"),
        lambda entry: entry.pop("sha256"),
        lambda entry: entry.update(size_bytes=-1),
        lambda entry: entry.update(size_bytes="24"),
        lambda entry: entry.update(size_bytes=date(2024, 1, 1)),
        lambda entry: entry.update(size_bytes={1, 2}),
        lambda entry: entry.update(size_bytes=b"24"),
        lambda entry: entry.pop("size_bytes"),
        lambda entry: entry.update(storage={"r2": "bad"}),
        lambda entry: entry["storage"]["r2"].update(key=""),
        lambda entry: entry["storage"]["r2"].update(key=123),
        lambda entry: entry["storage"]["r2"].update(bucket=""),
        lambda entry: entry["storage"]["r2"].update(bucket=123),
    ]
    for change in changes:
        manifest_path.write_bytes(original)
        _edit_artifact(manifest_path, change)
        before = _snapshot(root)
        report = _verify(root, fake)
        assert not report.valid
        assert report.entries[0].status == "invalid_manifest"
        assert _snapshot(root) == before
        exit_code = harness_main(
            ["verify-raw", "--root", str(root), "--wrangler-command", fake.command]
        )
        payload = json.loads(capsys.readouterr().out)
        assert exit_code == 1
        assert payload["entries"][0]["status"] == "invalid_manifest"
        assert _snapshot(root) == before
    assert fake.commands == []


def test_verify_raw_missing_object_markers_and_other_errors(tmp_path):
    root = tmp_path / "db" / "data"
    _, key = _add_artifact(root)
    fake = FakeWrangler(tmp_path / "fake")
    for marker in (
        "NoSuchKey",
        "The specified key does not exist",
        "Object not found",
        "Object does not exist",
    ):
        fake.set_remote({}, {f"ledger-raw/{key}": marker})
        report = _verify(root, fake)
        assert not report.valid
        assert report.entries[0].status == "missing_remote"
    for marker in ("connection refused", "HTTP 404", "code: 10007"):
        fake.set_remote({}, {f"ledger-raw/{key}": marker})
        assert _verify(root, fake).entries[0].status == "fetch_error"


# Wrangler's stderr for an absent object, as the NZ hub observed it in a live
# read-back on 2026-10-10 (bytes reproduced here, not a retained log).
_REAL_WRANGLER_MISSING = (
    "\x1b[31m\u2718 \x1b[41;31m[\x1b[41;97mERROR\x1b[41;31m]\x1b[0m "
    "\x1b[1mThe specified key does not exist.\x1b[0m\n\n\n"
    '\U0001fab5  Logs were written to "/tmp/wrangler.log"\n'
)


@pytest.mark.parametrize(
    ("stderr", "status"),
    [
        (_REAL_WRANGLER_MISSING, "missing_remote"),
        # Colour codes inside the phrase itself.
        (
            "\x1b[31m\u2718 [ERROR]\x1b[0m The specified \x1b[1mkey\x1b[0m does "
            "\x1b[4mnot\x1b[0m exist.",
            "missing_remote",
        ),
        ("An error occurred (NoSuchKey) when calling GetObject", "missing_remote"),
        ("  Object   not found.  ", "missing_remote"),
        ("NoSuchKey: specified key does not exist", "missing_remote"),
        # A marker inside a longer identifier is not the marker.
        ("error: NoSuchKeyHandler could not start", "fetch_error"),
        ("error: nosuchkeys table is locked", "fetch_error"),
        # A marker merely mentioned on a line that reports no error.
        ("note: see the docs on NoSuchKey\nconnection reset by peer", "fetch_error"),
        ("warning: Object not found pages are cached for 60s", "fetch_error"),
        (
            "retrying; last reply said the specified key does not exist yet",
            "fetch_error",
        ),
        # Known limit: an error line that merely mentions a marker still counts.
        (
            "error: could not reach bucket; NoSuchKey handling disabled",
            "missing_remote",
        ),
    ],
)
def test_verify_raw_classifies_wrangler_diagnostics(tmp_path, stderr, status):
    root = tmp_path / "db" / "data"
    _, key = _add_artifact(root)
    fake = FakeWrangler(tmp_path / "fake")
    fake.set_remote({}, {f"ledger-raw/{key}": stderr})

    report = _verify(root, fake)

    assert not report.valid
    assert report.entries[0].status == status


def test_verify_raw_missing_marker_survives_colour_codes_at_any_position(tmp_path):
    root = tmp_path / "db" / "data"
    _, key = _add_artifact(root)
    fake = FakeWrangler(tmp_path / "fake")
    phrase = "[ERROR] The specified key does not exist."
    for position in range(len(phrase) + 1):
        coloured = phrase[:position] + "\x1b[1;31m" + phrase[position:] + "\x1b[0m"
        fake.set_remote({}, {f"ledger-raw/{key}": coloured})
        assert _verify(root, fake).entries[0].status == "missing_remote", position


def test_verify_raw_missing_executable_is_fetch_error(tmp_path):
    root = tmp_path / "db" / "data"
    _add_artifact(root)
    before = _snapshot(root)

    report = verify_raw_artifacts(
        root, wrangler_command=str(tmp_path / "absent-wrangler")
    )

    assert not report.valid
    assert report.entries[0].status == "fetch_error"
    assert _snapshot(root) == before


def test_verify_raw_incident_object_only_at_legacy_key_is_missing(tmp_path):
    root = tmp_path / "db" / "data"
    payload = b"official WFF workbook"
    _, key = _add_artifact(root, payload)
    legacy_key = key.replace("raw/nz/", "raw/")
    fake = FakeWrangler(tmp_path / "fake")
    fake.set_remote({f"ledger-raw/{legacy_key}": payload})

    report = _verify(root, fake)

    assert not report.valid
    assert report.entries[0].status == "missing_remote"
    assert report.entries[0].canonical_key == key
    assert fake.commands[0][3] == f"ledger-raw/{key}"


def test_verify_raw_incident_manifest_at_legacy_key_is_key_mismatch(tmp_path):
    root = tmp_path / "db" / "data"
    payload = b"official WFF workbook"
    manifest_path, key = _add_artifact(root, payload)
    legacy_key = key.replace("raw/nz/", "raw/")
    _edit_artifact(
        manifest_path, lambda entry: entry["storage"]["r2"].update(key=legacy_key)
    )
    fake = FakeWrangler(tmp_path / "fake")
    fake.set_remote({f"ledger-raw/{legacy_key}": payload})

    report = _verify(root, fake)

    assert not report.valid
    assert report.entries[0].status == "key_mismatch"
    assert report.entries[0].canonical_key == key
    assert report.entries[0].r2_location.key == legacy_key
    assert fake.commands == []


def test_verify_raw_report_is_deterministic_in_publish_scan_order(tmp_path):
    root = tmp_path / "db" / "data"
    fake = FakeWrangler(tmp_path / "fake")
    objects = {}
    for source_id, package_id, year in (
        ("ons", "ons-mye", "source_capture"),
        ("ird", "ird-wff", 2025),
        ("ird", "ird-wff", 2024),
    ):
        payload = str(year).encode()
        _, key = _add_artifact(
            root, payload, source_id=source_id, package_id=package_id, year=year
        )
        objects[f"ledger-raw/{key}"] = payload
    # The shared local filename reflects the final 2024 entry. Remove it so
    # both pinned years are valid remote-only artifacts.
    for path in root.rglob("wff.xlsx"):
        path.unlink()
    fake.set_remote(objects)

    first = _verify(root, fake)
    second = _verify(root, fake)

    assert first.valid and second.valid
    assert first.to_dict() == second.to_dict()
    assert [(entry.source_id, entry.year) for entry in first.entries] == [
        ("ird", "2025"),
        ("ird", "2024"),
        ("ons", "source_capture"),
    ]


def test_verify_raw_cli_accepts_publish_flags_and_bucket_fallback(tmp_path, capsys):
    root = tmp_path / "db" / "data"
    payload = b"custom CLI artifact"
    manifest_path, key = _add_artifact(
        root,
        payload,
        package_id="override-package",
        manifest_filename="artifacts.yaml",
        prefix="archive",
        bucket="declared-bucket",
    )
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest.pop("source_id")
    manifest.pop("package_id")
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    fake = FakeWrangler(tmp_path / "fake")
    fake.set_remote({f"declared-bucket/{key}": payload})
    argv = [
        "verify-raw",
        "--root",
        str(root),
        "--manifest",
        "artifacts.yaml",
        "--source-id",
        "ird",
        "--package-id",
        "override-package",
        "--r2-bucket",
        "fallback-bucket",
        "--r2-prefix",
        "archive",
        "--wrangler-command",
        fake.command,
    ]

    assert harness_main(argv) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    assert fake.commands[-1][3] == f"declared-bucket/{key}"
    _edit_artifact(manifest_path, lambda entry: entry["storage"]["r2"].pop("bucket"))
    fake.set_remote({f"fallback-bucket/{key}": payload})
    assert harness_main(argv) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    assert fake.commands[-1][3] == f"fallback-bucket/{key}"


@pytest.mark.parametrize("status", ["verified", "missing_remote", "no_r2_location"])
def test_verify_raw_cli_json_and_exit_status(tmp_path, capsys, status):
    root = tmp_path / "db" / "data"
    payload = b"CLI fixture"
    manifest_path, key = _add_artifact(root, payload)
    fake = FakeWrangler(tmp_path / "fake")
    if status == "verified":
        fake.set_remote({f"ledger-raw/{key}": payload})
    if status == "no_r2_location":
        _edit_artifact(manifest_path, lambda entry: entry.pop("storage"))

    exit_code = harness_main(
        ["verify-raw", "--root", str(root), "--wrangler-command", fake.command]
    )
    report = json.loads(capsys.readouterr().out)

    assert exit_code == (0 if status == "verified" else 1)
    assert report["valid"] is (status == "verified")
    assert report["root"] == str(root)
    assert report["counts"]["artifact_count"] == 1
    assert report["counts"]["failed_count"] == (0 if status == "verified" else 1)
    assert report["entries"][0]["status"] == status
    assert report["entries"][0]["canonical_key"] == (
        None if status == "no_r2_location" else key
    )
    assert isinstance(report["errors"], list)


@pytest.mark.parametrize(
    "entrypoint", [cli_main, public_cli_main], ids=["legacy", "public"]
)
def test_verify_raw_top_level_cli_dispatches(tmp_path, capsys, monkeypatch, entrypoint):
    root = tmp_path / "db" / "data"
    payload = b"dispatch fixture"
    _, key = _add_artifact(root, payload)
    fake = FakeWrangler(tmp_path / "fake")
    fake.set_remote({f"ledger-raw/{key}": payload})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "chronicle",
            "verify-raw",
            "--root",
            str(root),
            "--wrangler-command",
            fake.command,
        ],
    )

    with pytest.raises(SystemExit) as exc:
        entrypoint()

    assert exc.value.code == 0
    assert json.loads(capsys.readouterr().out)["entries"][0]["status"] == "verified"


def test_verify_raw_seeded_payload_property(tmp_path):
    # Hypothesis is absent from this repository's dependencies. Exercise the
    # property with seeded random bytes, including empty and multi-chunk data.
    rng = random.Random(332)
    root = tmp_path / "db" / "data"
    fake = FakeWrangler(tmp_path / "fake")
    lengths = (0, 1, 65536, 65537, 1_048_591) + tuple(
        rng.randrange(2, 65536) for _ in range(3)
    )
    for length in lengths:
        payload = rng.randbytes(length)
        manifest_path, key = _add_artifact(root, payload)
        original = manifest_path.read_bytes()
        canonical_location = f"ledger-raw/{key}"
        flipped = bytes([payload[0] ^ 1]) + payload[1:] if payload else b"\x01"
        cases = [
            ({canonical_location: payload}, "verified", key),
            (
                {canonical_location: flipped},
                "digest_mismatch" if payload else "size_mismatch",
                key,
            ),
            ({}, "missing_remote", key),
            (
                {f"ledger-raw/{key.replace('raw/nz/', 'raw/')}": payload},
                "key_mismatch",
                key.replace("raw/nz/", "raw/"),
            ),
        ]
        if payload:
            cases.append(({canonical_location: payload[:-1]}, "size_mismatch", key))
        for remote, expected_status, declared_key in cases:
            manifest_path.write_bytes(original)
            _edit_artifact(
                manifest_path,
                lambda entry, declared_key=declared_key: entry["storage"]["r2"].update(
                    key=declared_key
                ),
            )
            fake.set_remote(remote)
            before = _snapshot(root)
            report = _verify(root, fake)
            assert report.valid is (expected_status == "verified")
            assert report.entries[0].status == expected_status
            assert _snapshot(root) == before


def test_verify_raw_reports_invalid_roots_and_manifests(tmp_path):
    fake = FakeWrangler(tmp_path / "fake")
    absent = tmp_path / "absent"
    report = _verify(absent, fake)
    assert not report.valid
    assert report.errors
    assert not absent.exists()
    root = tmp_path / "db" / "data"
    root.mkdir(parents=True)
    empty = _verify(root, fake)
    assert empty.valid
    assert empty.entries == ()
    assert all(count == 0 for count in empty.counts.values())
    manifest_path = root / "manifest.yaml"
    for malformed in ("[", "- scalar manifest\n", "files: []\n", "files: {}\n"):
        manifest_path.write_text(malformed)
        before = _snapshot(root)
        report = _verify(root, fake)
        assert not report.valid
        assert report.errors
        assert _snapshot(root) == before
    assert fake.commands == []
