"""Exercise scripts/ots_anchor.py against the real opentimestamps-client.

The fake client in test_ots_anchor.py encodes the client's output contract;
these tests check that contract against the client the workflow actually runs
(``uvx --from opentimestamps-client==0.7.2 ots``) without any network access:

- ``ots info`` only deserializes the proof and never contacts a calendar.
- ``ots --no-bitcoin verify`` of mismatching bytes stops at the digest check,
  before any calendar is consulted (otsclient/cmds.py, verify_command).
- The proofs built here carry either a Bitcoin block attestation, for which the
  client's upgrade loop never runs, or a pending attestation naming a calendar
  outside the client's default whitelist, which the client refuses to contact
  (``Ignoring attestation from calendar ...: Calendar not in whitelist``).

The client is tried offline first, then with uv's normal resolution, which
installs it on a CI runner. Set ``OTS_ANCHOR_TEST_OTS_BIN`` to use another
invocation. The module is skipped when no invocation works.
"""

from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "scripts"))

import ots_anchor  # noqa: E402

CLIENT_PIN = "opentimestamps-client==0.7.2"
DEFAULT_INVOCATIONS = (
    f"uvx --offline --from {CLIENT_PIN} ots",
    f"uvx --from {CLIENT_PIN} ots",
)
CLIENT_TIMEOUT = 300  # seconds; the first online invocation installs the client

# OpenTimestamps detached proof format (opentimestamps/core/timestamp.py,
# notary.py, serialize.py in opentimestamps 0.4.5): magic, version, file hash
# op tag, file digest, then the timestamp tree. The proofs built here attest
# the file digest directly, with no further operations.
HEADER_MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
MAJOR_VERSION = 1
OP_SHA256_TAG = b"\x08"
PENDING_ATTESTATION_TAG = bytes.fromhex("83dfe30d2ef90c8e")
BITCOIN_ATTESTATION_TAG = bytes.fromhex("0588960d73d71901")
UNLISTED_CALENDAR = "https://calendar.example.invalid"
BLOCK_HEIGHT = 963242
MISMATCH_LINE = "File does not match original!"


def varuint(value: int) -> bytes:
    if value == 0:
        return b"\x00"
    encoded = bytearray()
    while value:
        septet = value & 0x7F
        value >>= 7
        encoded.append(septet | 0x80 if value else septet)
    return bytes(encoded)


def varbytes(payload: bytes) -> bytes:
    return varuint(len(payload)) + payload


def pending_attestation(uri: str) -> bytes:
    return PENDING_ATTESTATION_TAG + varbytes(varbytes(uri.encode("ascii")))


def bitcoin_attestation(height: int) -> bytes:
    return BITCOIN_ATTESTATION_TAG + varbytes(varuint(height))


def build_proof(payload: bytes, *attestations: bytes) -> bytes:
    """Serialize a detached proof that attests ``payload``'s SHA-256 directly."""

    digest = hashlib.sha256(payload).digest()
    tree = b"".join(b"\xff\x00" + attestation for attestation in attestations[:-1])
    tree += b"\x00" + attestations[-1]
    return HEADER_MAGIC + varuint(MAJOR_VERSION) + OP_SHA256_TAG + digest + tree


def run_client(
    invocation: list[str], *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*invocation, *arguments],
        capture_output=True,
        text=True,
        timeout=CLIENT_TIMEOUT,
        check=False,
    )


@pytest.fixture(scope="module")
def real_ots_bin(tmp_path_factory: pytest.TempPathFactory) -> str:
    probe = tmp_path_factory.mktemp("probe") / "probe.ots"
    probe.write_bytes(build_proof(b"probe\n", pending_attestation(UNLISTED_CALENDAR)))
    override = os.environ.get("OTS_ANCHOR_TEST_OTS_BIN")
    invocations = (override,) if override else DEFAULT_INVOCATIONS
    for invocation in invocations:
        # --no-cache keeps the client from reading or writing ~/.cache/ots.
        candidate = f"{invocation} --no-cache"
        try:
            completed = run_client(shlex.split(candidate), "info", str(probe))
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode == 0 and "File sha256 hash:" in completed.stdout:
            return candidate
    pytest.skip(f"{CLIENT_PIN} is not runnable here")


def anchor_root(tmp_path: Path) -> tuple[Path, Path]:
    manifest_dir = tmp_path / "releases" / "manifests"
    manifest_dir.mkdir(parents=True)
    (tmp_path / "ots").mkdir()
    return tmp_path, manifest_dir


def make_manifest(directory: Path, index: int, payload: bytes) -> Path:
    digest = hashlib.sha256(payload).hexdigest()
    path = directory / f"{index:04d}-{digest[:16]}.json"
    path.write_bytes(payload)
    return path


def write_proof(root: Path, manifest: Path, proof_bytes: bytes) -> Path:
    proof = root / "ots" / f"{manifest.name}.ots"
    proof.write_bytes(proof_bytes)
    return proof


def run_cli(root: Path, ots_bin: str, *arguments: str) -> int:
    return ots_anchor.main([*arguments, "--root", str(root), "--ots-bin", ots_bin])


def test_committed_proofs_bind_the_digest_in_their_filenames(
    real_ots_bin: str,
) -> None:
    proofs = sorted((ROOT / "ots").glob("*.json.ots"))
    assert proofs
    for proof in proofs:
        stem_digest = proof.name.split("-", 1)[1][:16]
        info = ots_anchor.inspect_proof(proof, shlex.split(real_ots_bin))
        assert info.digest.startswith(stem_digest), proof.name
        assert info.state in {"bitcoin", "pending"}, proof.name


def test_synthetic_proofs_round_trip_through_ots_info(
    real_ots_bin: str, tmp_path: Path
) -> None:
    payload = b'{"releaseIndex": 0}\n'
    digest = hashlib.sha256(payload).hexdigest()
    ots_bin = shlex.split(real_ots_bin)

    pending = tmp_path / "pending.ots"
    pending.write_bytes(build_proof(payload, pending_attestation(UNLISTED_CALENDAR)))
    assert ots_anchor.inspect_proof(pending, ots_bin) == ots_anchor.ProofInfo(
        digest=digest, state="pending"
    )

    complete = tmp_path / "complete.ots"
    complete.write_bytes(
        build_proof(
            payload,
            bitcoin_attestation(BLOCK_HEIGHT),
            pending_attestation(UNLISTED_CALENDAR),
        )
    )
    assert ots_anchor.inspect_proof(complete, ots_bin) == ots_anchor.ProofInfo(
        digest=digest, state="bitcoin"
    )


def test_client_prints_exact_mismatch_line_and_nothing_else(
    real_ots_bin: str, tmp_path: Path
) -> None:
    root, manifest_dir = anchor_root(tmp_path)
    manifest = make_manifest(manifest_dir, 0, b'{"releaseIndex": 0}\n')
    proof = write_proof(
        root,
        manifest,
        build_proof(b"other bytes\n", pending_attestation(UNLISTED_CALENDAR)),
    )

    completed = run_client(
        shlex.split(real_ots_bin),
        "--no-bitcoin",
        "verify",
        "-f",
        str(manifest),
        str(proof),
    )
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == MISMATCH_LINE + "\n"
    assert ots_anchor._MISMATCH_LINE == MISMATCH_LINE
    assert (
        ots_anchor.verify_proof_binding(manifest, proof, shlex.split(real_ots_bin))
        is False
    )


def test_status_and_verify_enumerate_mismatches(
    real_ots_bin: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest_dir = anchor_root(tmp_path)
    good = make_manifest(manifest_dir, 0, b'{"releaseIndex": 0}\n')
    write_proof(
        root, good, build_proof(good.read_bytes(), bitcoin_attestation(BLOCK_HEIGHT))
    )
    swapped = make_manifest(manifest_dir, 1, b'{"releaseIndex": 1}\n')
    write_proof(
        root,
        swapped,
        build_proof(b'{"releaseIndex": 99}\n', pending_attestation(UNLISTED_CALENDAR)),
    )
    tampered = make_manifest(manifest_dir, 2, b'{"releaseIndex": 2}\n')
    write_proof(
        root,
        tampered,
        build_proof(tampered.read_bytes(), pending_attestation(UNLISTED_CALENDAR)),
    )
    tampered.write_bytes(b'{"releaseIndex": 2, "tampered": true}\n')

    assert run_cli(root, real_ots_bin, "status") == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        f"{good.name}: bitcoin attestation stored locally",
        f"{swapped.name}: MISMATCH (proof does not match manifest bytes)",
        f"{tampered.name}: MISMATCH (manifest bytes contradict its filename)",
    ]
    assert "  Not checking Bitcoin attestation; Bitcoin disabled" in captured.err
    assert (
        f"  To verify manually, check that Bitcoin block {BLOCK_HEIGHT} has merkleroot"
        in captured.err
    )

    assert run_cli(root, real_ots_bin, "verify") == 1
    captured = capsys.readouterr()
    failures = [line for line in captured.err.splitlines() if line.startswith("  FAIL")]
    assert failures == [
        f"  FAIL {swapped.name}: proof does not match manifest bytes",
        f"  FAIL {tampered.name}: manifest bytes contradict its filename",
    ]
    assert "3 manifests, 1 locally Bitcoin-complete, 0 pending locally" in captured.out


def test_run_reaches_upgrade_for_pending_proof(
    real_ots_bin: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest_dir = anchor_root(tmp_path)
    complete = make_manifest(manifest_dir, 0, b'{"releaseIndex": 0}\n')
    write_proof(
        root,
        complete,
        build_proof(complete.read_bytes(), bitcoin_attestation(BLOCK_HEIGHT)),
    )
    pending = make_manifest(manifest_dir, 1, b'{"releaseIndex": 1}\n')
    proof = write_proof(
        root,
        pending,
        build_proof(pending.read_bytes(), pending_attestation(UNLISTED_CALENDAR)),
    )
    original = proof.read_bytes()

    assert run_cli(root, real_ots_bin, "run") == 0
    captured = capsys.readouterr()
    assert "2 manifests, stamped 0, upgraded 0, still pending 1" in captured.out
    assert (
        f"  Ignoring attestation from calendar {UNLISTED_CALENDAR}: "
        "Calendar not in whitelist"
    ) in captured.err
    assert proof.read_bytes() == original
    assert not proof.with_name(proof.name + ".bak").exists()
    assert run_cli(root, real_ots_bin, "verify") == 0
    assert run_cli(root, real_ots_bin, "verify", "--require-bitcoin") == 1


def test_run_refuses_proof_bound_to_other_bytes(
    real_ots_bin: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest_dir = anchor_root(tmp_path)
    manifest = make_manifest(manifest_dir, 0, b'{"releaseIndex": 0}\n')
    proof = write_proof(
        root, manifest, build_proof(b"other bytes\n", bitcoin_attestation(BLOCK_HEIGHT))
    )
    original = proof.read_bytes()

    assert run_cli(root, real_ots_bin, "run") == 1
    assert "does not match manifest bytes; refusing to skip" in capsys.readouterr().err
    assert proof.read_bytes() == original
