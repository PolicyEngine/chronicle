"""Byte-level differential tests for the receipt consumer shims."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from collections.abc import Callable

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SHIM_SCRIPTS = ROOT / "scripts"
ORIGINAL_FIXTURES = ROOT / "tests" / "fixtures" / "vidimus_shim_originals"
ORIGINAL_HASHES = {
    "canonical_json.py": (
        "562bf267b7686bce8cb71f3c13f34825c21cd4ef0aba1c0c46aff16962a6cadd"
    ),
    "check_thesis_facts_append.py": (
        "46727ab22186b8f150fc7dbee8222cee729a6ddb4ba8e8cbe4a3dda702cbc427"
    ),
    "verify_release_chain.py": (
        "7f73e6921ca40e41e556c8e37a634e2780e7e8eeb3ab203ecdb9b7bd4b15a844"
    ),
}
OPENSSL_QUEUE_ID = re.compile(rb"(?m)^[0-9A-Fa-f]{8,16}(?=:error:)")

BASE_LINE_COUNT = 190
CANDIDATE_LINE_COUNT = 191
NEW_RELEASE_STEM = "0014-bd12e9e3e79a5529"
RELEASE_FILE_SUFFIXES = (
    ".json",
    ".producer.sig",
    ".freetsa.tsr",
    ".digicert.tsr",
)

Mutation = Callable[[pathlib.Path], None]


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", sorted(ORIGINAL_HASHES))
def test_original_oracle_fixtures_are_authenticated(name: str) -> None:
    assert _sha256(ORIGINAL_FIXTURES / name) == ORIGINAL_HASHES[name]


@pytest.fixture(scope="session")
def original_oracle(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """Copy the authenticated original scripts into one executable tree."""

    oracle = tmp_path_factory.mktemp("receipt-original-oracle")
    scripts = oracle / "scripts"
    scripts.mkdir()
    for name, expected in ORIGINAL_HASHES.items():
        source = ORIGINAL_FIXTURES / name
        assert _sha256(source) == expected
        shutil.copyfile(source, scripts / name)
    shutil.copytree(
        ROOT / "releases" / "anchors",
        oracle / "releases" / "anchors",
    )
    return oracle


def _run_script(
    script: pathlib.Path,
    *arguments: str,
    cwd: pathlib.Path = ROOT,
    stdin: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        check=False,
    )


def _normalized_stderr(value: bytes) -> bytes:
    """Mask only OpenSSL 3's necessarily per-process error-queue prefix."""

    return OPENSSL_QUEUE_ID.sub(b"<openssl-err-id>", value)


def _assert_byte_identical(
    original: subprocess.CompletedProcess[bytes],
    shim: subprocess.CompletedProcess[bytes],
    *,
    expected_code: int,
) -> None:
    assert original.returncode == expected_code
    assert shim.returncode == expected_code
    assert shim.stdout == original.stdout
    assert _normalized_stderr(shim.stderr) == _normalized_stderr(original.stderr)


@pytest.mark.parametrize(
    ("arguments", "stdin", "expected_code"),
    [
        (
            (),
            b'{"\\ud83d\\ude00":1,"\\ue000":2,"fixed":1e-6,"scientific":1e21}\n',
            0,
        ),
        (
            ("--sha256",),
            b'{"\\ud83d\\ude00":1,"\\ue000":2,"fixed":1e-6,"scientific":1e21}\n',
            0,
        ),
        (("--help",), None, 0),
        (("--not-an-option",), None, 2),
    ],
)
def test_canonical_json_cli_is_byte_identical(
    original_oracle: pathlib.Path,
    arguments: tuple[str, ...],
    stdin: bytes | None,
    expected_code: int,
) -> None:
    original = _run_script(
        original_oracle / "scripts" / "canonical_json.py",
        *arguments,
        stdin=stdin,
    )
    shim = _run_script(
        SHIM_SCRIPTS / "canonical_json.py",
        *arguments,
        stdin=stdin,
    )
    _assert_byte_identical(original, shim, expected_code=expected_code)


def test_release_chain_cli_help_is_byte_identical(
    original_oracle: pathlib.Path,
) -> None:
    original = _run_script(
        original_oracle / "scripts" / "verify_release_chain.py",
        "--help",
    )
    shim = _run_script(SHIM_SCRIPTS / "verify_release_chain.py", "--help")
    _assert_byte_identical(original, shim, expected_code=0)


def test_live_full_release_chain_is_byte_identical(
    original_oracle: pathlib.Path,
) -> None:
    arguments = ("--full", "--root", str(ROOT))
    original = _run_script(
        original_oracle / "scripts" / "verify_release_chain.py",
        *arguments,
    )
    shim = _run_script(SHIM_SCRIPTS / "verify_release_chain.py", *arguments)
    _assert_byte_identical(original, shim, expected_code=0)
    assert shim.stderr == b""
    assert shim.stdout == (
        b"release chain OK: 15 releases, "
        b"HEAD=0014-bd12e9e3e79a5529.json, "
        b"digicert=2026-08-15T13:59:24Z, "
        b"freetsa=2026-08-15T13:59:24Z\n"
    )


def _copy_custody_tree(destination: pathlib.Path) -> pathlib.Path:
    root = destination / "root"
    shutil.copytree(ROOT / "ledger", root / "ledger")
    shutil.copytree(ROOT / "releases", root / "releases")
    return root


def _flip_middle_byte(path: pathlib.Path) -> None:
    payload = bytearray(path.read_bytes())
    payload[len(payload) // 2] ^= 0x01
    path.write_bytes(bytes(payload))


def _append_unwitnessed_row(root: pathlib.Path) -> None:
    ledger = root / "ledger" / "official_observations.jsonl"
    ledger.write_bytes(ledger.read_bytes() + b"{}\n")


def _corrupt_producer_signature(root: pathlib.Path) -> None:
    _flip_middle_byte(
        root
        / "releases"
        / "manifests"
        / "0001-916626696d034b80.producer.sig"
    )


def _corrupt_freetsa_receipt(root: pathlib.Path) -> None:
    _flip_middle_byte(
        root
        / "releases"
        / "manifests"
        / "0001-916626696d034b80.freetsa.tsr"
    )


@pytest.mark.parametrize(
    ("case", "mutation", "marker"),
    [
        (
            "unwitnessed-row",
            _append_unwitnessed_row,
            b"HEAD release lineCount 191 does not match working-tree line count 192",
        ),
        (
            "producer-signature",
            _corrupt_producer_signature,
            b"producer Ed25519 signature verification failed",
        ),
        (
            "freetsa-receipt",
            _corrupt_freetsa_receipt,
            b"cannot inspect RFC 3161 receipt",
        ),
    ],
)
def test_corrupt_release_chain_refusals_are_byte_identical(
    original_oracle: pathlib.Path,
    tmp_path: pathlib.Path,
    case: str,
    mutation: Mutation,
    marker: bytes,
) -> None:
    custody = _copy_custody_tree(tmp_path / case)
    mutation(custody)
    arguments = ("--full", "--root", str(custody))
    original = _run_script(
        original_oracle / "scripts" / "verify_release_chain.py",
        *arguments,
    )
    shim = _run_script(SHIM_SCRIPTS / "verify_release_chain.py", *arguments)
    _assert_byte_identical(original, shim, expected_code=1)
    assert shim.stdout == b""
    assert marker in _normalized_stderr(shim.stderr)


def _git(root: pathlib.Path, *arguments: str) -> str:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
    )
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _release_file(root: pathlib.Path, suffix: str) -> pathlib.Path:
    return root / "releases" / "manifests" / f"{NEW_RELEASE_STEM}{suffix}"


def _replay_latest_release(destination: pathlib.Path) -> tuple[pathlib.Path, str]:
    """Create the real prior-release base and restore the witnessed HEAD append."""

    root = _copy_custody_tree(destination)
    ledger = root / "ledger" / "official_observations.jsonl"
    full_ledger = ledger.read_bytes()
    rows = full_ledger.splitlines(keepends=True)
    assert len(rows) == CANDIDATE_LINE_COUNT
    assert all(row.endswith(b"\n") for row in rows)
    ledger.write_bytes(b"".join(rows[:BASE_LINE_COUNT]))
    for suffix in RELEASE_FILE_SUFFIXES:
        _release_file(root, suffix).unlink()

    _git(root, "init", "--quiet")
    _git(root, "config", "user.email", "shim-differential@example.invalid")
    _git(root, "config", "user.name", "Shim Differential")
    _git(root, "add", "-A")
    _git(root, "commit", "--quiet", "-m", "release 1 base")
    base = _git(root, "rev-parse", "HEAD")

    ledger.write_bytes(full_ledger)
    for suffix in RELEASE_FILE_SUFFIXES:
        shutil.copyfile(
            _release_file(ROOT, suffix),
            _release_file(root, suffix),
        )
    return root, base


def _run_append_pair(
    original_oracle: pathlib.Path,
    candidate: pathlib.Path,
    base: str,
) -> tuple[subprocess.CompletedProcess[bytes], subprocess.CompletedProcess[bytes]]:
    arguments = ("--root", str(candidate), "--base-ref", base)
    original = _run_script(
        original_oracle / "scripts" / "check_thesis_facts_append.py",
        *arguments,
        cwd=candidate,
    )
    shim = _run_script(
        SHIM_SCRIPTS / "check_thesis_facts_append.py",
        *arguments,
        cwd=candidate,
    )
    return original, shim


def test_append_gate_cli_help_is_byte_identical(
    original_oracle: pathlib.Path,
) -> None:
    original = _run_script(
        original_oracle / "scripts" / "check_thesis_facts_append.py",
        "--help",
    )
    shim = _run_script(SHIM_SCRIPTS / "check_thesis_facts_append.py", "--help")
    _assert_byte_identical(original, shim, expected_code=0)


def test_valid_base_ref_append_is_byte_identical(
    original_oracle: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    candidate, base = _replay_latest_release(tmp_path)
    original, shim = _run_append_pair(original_oracle, candidate, base)
    _assert_byte_identical(original, shim, expected_code=0)
    assert shim.stderr == b""
    assert shim.stdout == (
        b"thesis-facts append check OK: 191 rows, immutable prefix 128, "
        b"+1 appended vs base, release 14\n"
    )


def _rewrite_historical_row(root: pathlib.Path) -> None:
    ledger = root / "ledger" / "official_observations.jsonl"
    rows = ledger.read_bytes().splitlines(keepends=True)
    rows[128] = b" " + rows[128]
    ledger.write_bytes(b"".join(rows))


def _remove_appended_assertion_version(root: pathlib.Path) -> None:
    ledger = root / "ledger" / "official_observations.jsonl"
    rows = ledger.read_bytes().splitlines(keepends=True)
    row = json.loads(rows[BASE_LINE_COUNT])
    row.pop("assertionVersion")
    rows[BASE_LINE_COUNT] = (
        json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    ledger.write_bytes(b"".join(rows))


def _remove_new_release_manifest(root: pathlib.Path) -> None:
    _release_file(root, ".json").unlink()


@pytest.mark.parametrize(
    ("case", "mutation", "marker"),
    [
        (
            "historical-rewrite",
            _rewrite_historical_row,
            b"change rewrites existing line 129",
        ),
        (
            "missing-assertion-version",
            _remove_appended_assertion_version,
            b"appended line 191",
        ),
        (
            "missing-release-manifest",
            _remove_new_release_manifest,
            b"release proposal must add exactly one manifest for index 14",
        ),
    ],
)
def test_corrupt_base_ref_append_refusals_are_byte_identical(
    original_oracle: pathlib.Path,
    tmp_path: pathlib.Path,
    case: str,
    mutation: Mutation,
    marker: bytes,
) -> None:
    candidate, base = _replay_latest_release(tmp_path / case)
    mutation(candidate)
    original, shim = _run_append_pair(original_oracle, candidate, base)
    _assert_byte_identical(original, shim, expected_code=1)
    assert shim.stdout == b""
    assert marker in _normalized_stderr(shim.stderr)
