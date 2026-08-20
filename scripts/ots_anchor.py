#!/usr/bin/env python3
"""Anchor witnessed release manifests in Bitcoin via OpenTimestamps.

Each release manifest under ``releases/manifests/<stem>.json`` is already
witnessed by two RFC 3161 authorities and a pinned producer signature over its
exact bytes. This tool adds an operator-independent witness: an OpenTimestamps
proof over those same exact bytes, committed as ``ots/<stem>.json.ots``.
Because manifest ``state.jsonlSha256`` covers the full journal bytes and
``previousManifestSha256`` chains every earlier manifest, a Bitcoin
attestation over one manifest bounds the existence time of the whole journal
state it commits to.

Proofs live in the top-level ``ots/`` directory, never under ``releases/``:
the append gate keeps ``releases/`` closed to anything but exact release
bundles, and OpenTimestamps upgrades rewrite proof files in place, which the
release-history immutability check would reject.

Subcommands:

- ``run``: stamp any manifest that lacks a proof, then try to upgrade pending
  proofs to complete Bitcoin attestations. Idempotent; safe on a schedule.
- ``verify``: check every proof against its manifest's current bytes and
  report attestation status. Exits nonzero on digest mismatch or a manifest
  with no proof.
- ``status``: list proofs and whether each is pending or Bitcoin-complete.

Requires the ``ots`` CLI (PyPI ``opentimestamps-client``); stamping and
upgrading contact public calendar servers, verification of a complete proof
against Bitcoin needs a local node or the printed manual block check.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST_DIR = pathlib.Path("releases/manifests")
OTS_DIR = pathlib.Path("ots")
MANIFEST_NAME_RE = re.compile(r"^(\d{4})-([0-9a-f]{16})\.json$")
SUBPROCESS_TIMEOUT = 300

# Stable output substrings observed from opentimestamps-client 0.7.2.
_MISMATCH_TEXT = "File does not match original"
_PENDING_TEXT = "Pending confirmation in Bitcoin blockchain"
_MANUAL_TEXT = "To verify manually, check that Bitcoin block"
_NO_NODE_TEXT = "Could not connect to Bitcoin node"
_UPGRADE_PENDING_TEXT = "Timestamp not complete"
_BITCOIN_ATTESTATION_TEXT = "BitcoinBlockHeaderAttestation"
_PENDING_ATTESTATION_TEXT = "PendingAttestation"


class AnchorError(RuntimeError):
    """A condition that must stop the anchoring run."""


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def discover_manifests(root: pathlib.Path) -> list[pathlib.Path]:
    directory = root / MANIFEST_DIR
    if not directory.is_dir():
        raise AnchorError(f"manifest directory missing: {directory}")
    manifests = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and MANIFEST_NAME_RE.match(path.name)
    )
    if not manifests:
        raise AnchorError(f"no release manifests found in {directory}")
    return manifests


def check_manifest_name_digest(manifest: pathlib.Path) -> str:
    """Refuse to anchor bytes that contradict the manifest's own filename."""

    match = MANIFEST_NAME_RE.match(manifest.name)
    if match is None:  # discover_manifests already filtered on the pattern
        raise AnchorError(f"unexpected manifest filename: {manifest.name}")
    digest = sha256_file(manifest)
    if digest[:16] != match.group(2):
        raise AnchorError(
            f"manifest {manifest.name} bytes hash to {digest[:16]}..., "
            "which contradicts the filename; refusing to anchor"
        )
    return digest


def proof_path(root: pathlib.Path, manifest: pathlib.Path) -> pathlib.Path:
    return root / OTS_DIR / f"{manifest.name}.ots"


def _run_ots(
    ots_bin: list[str], arguments: list[str], *, timeout: int = SUBPROCESS_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    command = [*ots_bin, *arguments]
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AnchorError(
            f"ots binary not found ({command[0]!r}); install "
            "opentimestamps-client or pass --ots-bin"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AnchorError(f"ots timed out: {' '.join(command)}") from exc


def stamp_manifest(
    root: pathlib.Path, manifest: pathlib.Path, ots_bin: list[str]
) -> pathlib.Path:
    """Stamp a temporary copy so nothing is ever written under releases/."""

    destination = proof_path(root, manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ots-anchor-") as name:
        working_copy = pathlib.Path(name) / manifest.name
        shutil.copyfile(manifest, working_copy)
        completed = _run_ots(ots_bin, ["stamp", str(working_copy)])
        produced = working_copy.with_name(working_copy.name + ".ots")
        if completed.returncode != 0 or not produced.is_file():
            raise AnchorError(
                f"ots stamp failed for {manifest.name}: "
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
        shutil.move(str(produced), destination)
    return destination


def proof_is_complete(proof: pathlib.Path, ots_bin: list[str]) -> bool:
    """True when the local proof file carries a Bitcoin attestation.

    ``ots info`` reads only the proof file, no network. An upgraded proof can
    still list leftover ``PendingAttestation`` entries from calendars that
    have not answered; one Bitcoin block attestation is what matters, and a
    complete proof is left untouched so its committed bytes stay stable.
    """

    completed = _run_ots(ots_bin, ["info", str(proof)])
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise AnchorError(f"ots info failed for {proof.name}: {output.strip()}")
    if _BITCOIN_ATTESTATION_TEXT in output:
        return True
    if _PENDING_ATTESTATION_TEXT in output:
        return False
    raise AnchorError(
        f"proof {proof.name} lists neither a Bitcoin nor a pending "
        "attestation; refusing to guess"
    )


def upgrade_proof(proof: pathlib.Path, ots_bin: list[str]) -> None:
    """Try to fold a Bitcoin attestation into a pending proof.

    Only called on proofs classified as pending. A still-pending calendar
    answer is normal; anything else nonzero is a real failure. The client
    leaves a ``.bak`` beside an upgraded proof; git history already keeps
    the pending version, so the backup is removed.
    """

    completed = _run_ots(ots_bin, ["upgrade", str(proof)])
    output = completed.stdout + completed.stderr
    backup = proof.with_name(proof.name + ".bak")
    if backup.is_file():
        backup.unlink()
    if completed.returncode == 0:
        return
    if _UPGRADE_PENDING_TEXT in output or _PENDING_TEXT in output:
        return
    raise AnchorError(f"ots upgrade failed for {proof.name}: {output.strip()}")


def classify_proof(
    manifest: pathlib.Path, proof: pathlib.Path, ots_bin: list[str]
) -> str:
    """Classify a proof against the manifest's current bytes.

    Returns one of ``"bitcoin"`` (complete attestation, verified or reported
    for manual block check), ``"pending"`` (bound to these bytes, calendar
    attestation not yet in Bitcoin), or ``"mismatch"``.
    """

    completed = _run_ots(
        ots_bin, ["--no-bitcoin", "verify", "-f", str(manifest), str(proof)]
    )
    output = completed.stdout + completed.stderr
    if _MISMATCH_TEXT in output:
        return "mismatch"
    if completed.returncode == 0 or _MANUAL_TEXT in output:
        return "bitcoin"
    if _PENDING_TEXT in output:
        return "pending"
    if _NO_NODE_TEXT in output:
        return "bitcoin"
    raise AnchorError(
        f"unrecognized ots verify outcome for {proof.name}: {output.strip()}"
    )


def command_run(root: pathlib.Path, ots_bin: list[str]) -> int:
    manifests = discover_manifests(root)
    stamped: list[str] = []
    upgraded: list[str] = []
    pending: list[str] = []
    for manifest in manifests:
        check_manifest_name_digest(manifest)
        proof = proof_path(root, manifest)
        if not proof.is_file():
            stamp_manifest(root, manifest, ots_bin)
            stamped.append(manifest.name)
            pending.append(manifest.name)
            continue
        if proof_is_complete(proof, ots_bin):
            continue
        upgrade_proof(proof, ots_bin)
        if proof_is_complete(proof, ots_bin):
            upgraded.append(manifest.name)
        else:
            pending.append(manifest.name)
    print(
        f"ots anchor run: {len(manifests)} manifests, "
        f"stamped {len(stamped)}, upgraded {len(upgraded)}, "
        f"still pending {len(pending)}"
    )
    for name in stamped:
        print(f"  stamped {name}")
    for name in upgraded:
        print(f"  upgraded {name}")
    return 0


def command_verify(
    root: pathlib.Path, ots_bin: list[str], *, require_bitcoin: bool
) -> int:
    manifests = discover_manifests(root)
    failures: list[str] = []
    pending_count = 0
    bitcoin_count = 0
    for manifest in manifests:
        check_manifest_name_digest(manifest)
        proof = proof_path(root, manifest)
        if not proof.is_file():
            failures.append(f"{manifest.name}: no OpenTimestamps proof")
            continue
        state = classify_proof(manifest, proof, ots_bin)
        if state == "mismatch":
            failures.append(f"{manifest.name}: proof does not match manifest bytes")
        elif state == "pending":
            pending_count += 1
            if require_bitcoin:
                failures.append(f"{manifest.name}: attestation not yet in Bitcoin")
        else:
            bitcoin_count += 1
    print(
        f"ots anchor verify: {len(manifests)} manifests, "
        f"{bitcoin_count} with Bitcoin attestations, {pending_count} pending"
    )
    for failure in failures:
        print(f"  FAIL {failure}", file=sys.stderr)
    if failures:
        return 1
    print("every release manifest has an OpenTimestamps proof bound to its exact bytes")
    return 0


def command_status(root: pathlib.Path, ots_bin: list[str]) -> int:
    manifests = discover_manifests(root)
    for manifest in manifests:
        proof = proof_path(root, manifest)
        if not proof.is_file():
            print(f"{manifest.name}: unanchored")
            continue
        state = classify_proof(manifest, proof, ots_bin)
        label = {
            "bitcoin": "bitcoin attestation",
            "pending": "pending calendar attestation",
            "mismatch": "MISMATCH",
        }[state]
        print(f"{manifest.name}: {label}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="anchor witnessed release manifests via OpenTimestamps"
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root",
        type=pathlib.Path,
        default=ROOT,
        help=argparse.SUPPRESS,
    )
    common.add_argument(
        "--ots-bin",
        default="ots",
        help="ots invocation, shell-split (default: %(default)s)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "run", parents=[common], help="stamp missing proofs, upgrade pending"
    )
    verify_parser = subparsers.add_parser(
        "verify",
        parents=[common],
        help="check every proof against current manifest bytes",
    )
    verify_parser.add_argument(
        "--require-bitcoin",
        action="store_true",
        help="fail while any attestation is still pending",
    )
    subparsers.add_parser(
        "status", parents=[common], help="list proofs and their state"
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    ots_bin = shlex.split(args.ots_bin)
    try:
        if args.command == "run":
            return command_run(root, ots_bin)
        if args.command == "verify":
            return command_verify(root, ots_bin, require_bitcoin=args.require_bitcoin)
        return command_status(root, ots_bin)
    except AnchorError as exc:
        print(f"ots anchor failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
