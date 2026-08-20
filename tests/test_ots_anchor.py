"""Tests for scripts/ots_anchor.py.

The suite never contacts calendar servers or Bitcoin: a fake ``ots``
executable reproduces the observed opentimestamps-client 0.7.2 output
contract (stamp/upgrade/info/verify), and every invocation is logged so the
tests can assert which operations ran.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "scripts"))

import ots_anchor  # noqa: E402

FAKE_OTS = r"""
import hashlib
import json
import os
import pathlib
import sys

LOG = pathlib.Path(os.environ["FAKE_OTS_LOG"])


def log(entry):
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(entry + "\n")


def read_proof(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def write_proof(path, payload):
    pathlib.Path(path).write_text(json.dumps(payload), encoding="utf-8")


def main():
    arguments = [a for a in sys.argv[1:] if a != "--no-bitcoin"]
    command = arguments[0]
    log(command)
    if command == "stamp":
        target = pathlib.Path(arguments[1])
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        write_proof(
            str(target) + ".ots", {"digest": digest, "state": "pending"}
        )
        print("Submitting to remote calendar https://fake.calendar")
        return 0
    if command == "info":
        proof = read_proof(arguments[1])
        if proof["state"] == "bitcoin":
            print("verify BitcoinBlockHeaderAttestation(963213)")
        else:
            print("verify PendingAttestation('https://fake.calendar')")
        return 0
    if command == "upgrade":
        path = pathlib.Path(arguments[1])
        proof = read_proof(path)
        if os.environ.get("FAKE_OTS_UPGRADE") == "success":
            proof["state"] = "bitcoin"
            write_proof(path, proof)
            pathlib.Path(str(path) + ".bak").write_text(
                "backup", encoding="utf-8"
            )
            print("Success! Timestamp complete")
            return 0
        print("Failed! Timestamp not complete")
        return 1
    if command == "verify":
        target = pathlib.Path(arguments[arguments.index("-f") + 1])
        proof = read_proof(arguments[-1])
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != proof["digest"]:
            print("File does not match original!")
            return 1
        if proof["state"] == "bitcoin":
            print(
                "To verify manually, check that Bitcoin block 963213 "
                "has merkleroot aa"
            )
            return 1
        print("Pending confirmation in Bitcoin blockchain")
        return 1
    raise SystemExit(f"unexpected fake ots command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
"""


def make_manifest(directory: Path, index: int, payload: bytes) -> Path:
    digest = hashlib.sha256(payload).hexdigest()
    path = directory / f"{index:04d}-{digest[:16]}.json"
    path.write_bytes(payload)
    return path


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    manifest_dir = tmp_path / "releases" / "manifests"
    manifest_dir.mkdir(parents=True)
    manifests = [
        make_manifest(manifest_dir, 0, b'{"releaseIndex": 0}\n'),
        make_manifest(manifest_dir, 1, b'{"releaseIndex": 1}\n'),
    ]
    fake = tmp_path / "fake_ots.py"
    fake.write_text(FAKE_OTS, encoding="utf-8")
    log = tmp_path / "ots-invocations.log"
    log.touch()
    monkeypatch.setenv("FAKE_OTS_LOG", str(log))
    monkeypatch.setenv("FAKE_OTS_UPGRADE", "pending")
    ots_bin = f"{shlex.quote(sys.executable)} {shlex.quote(str(fake))}"
    return {
        "root": tmp_path,
        "manifest_dir": manifest_dir,
        "manifests": manifests,
        "ots_bin": ots_bin,
        "log": log,
    }


def run_cli(repo: dict, *arguments: str) -> int:
    return ots_anchor.main(
        [*arguments, "--root", str(repo["root"]), "--ots-bin", repo["ots_bin"]]
    )


def logged_commands(repo: dict) -> list[str]:
    return repo["log"].read_text(encoding="utf-8").split()


def test_run_stamps_every_manifest_into_ots_dir(repo: dict) -> None:
    assert run_cli(repo, "run") == 0
    proofs = sorted((repo["root"] / "ots").iterdir())
    assert [p.name for p in proofs] == [m.name + ".ots" for m in repo["manifests"]]
    for manifest, proof in zip(repo["manifests"], proofs):
        payload = json.loads(proof.read_text(encoding="utf-8"))
        assert payload["digest"] == hashlib.sha256(manifest.read_bytes()).hexdigest()


def test_run_never_writes_into_releases(repo: dict) -> None:
    before = sorted(p.name for p in repo["manifest_dir"].iterdir())
    assert run_cli(repo, "run") == 0
    after = sorted(p.name for p in repo["manifest_dir"].iterdir())
    assert before == after


def test_run_is_idempotent_and_upgrades_pending_proofs(
    repo: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_cli(repo, "run") == 0
    assert logged_commands(repo).count("stamp") == 2

    # Second run: calendars still pending — no new stamps, upgrade attempted.
    assert run_cli(repo, "run") == 0
    assert logged_commands(repo).count("stamp") == 2
    assert logged_commands(repo).count("upgrade") == 2

    # Third run: attestations land — proofs upgraded in place, .bak removed.
    monkeypatch.setenv("FAKE_OTS_UPGRADE", "success")
    assert run_cli(repo, "run") == 0
    for manifest in repo["manifests"]:
        proof = repo["root"] / "ots" / f"{manifest.name}.ots"
        assert json.loads(proof.read_text(encoding="utf-8"))["state"] == ("bitcoin")
        assert not proof.with_name(proof.name + ".bak").exists()

    # Fourth run: complete proofs are left untouched (no further upgrades).
    upgrades_before = logged_commands(repo).count("upgrade")
    assert run_cli(repo, "run") == 0
    assert logged_commands(repo).count("upgrade") == upgrades_before


def test_run_refuses_manifest_contradicting_its_filename(repo: dict) -> None:
    rogue = repo["manifest_dir"] / f"0002-{'0' * 16}.json"
    rogue.write_bytes(b'{"releaseIndex": 2}\n')
    assert run_cli(repo, "run") == 1


def test_verify_passes_with_pending_proofs_by_default(repo: dict) -> None:
    assert run_cli(repo, "run") == 0
    assert run_cli(repo, "verify") == 0
    assert run_cli(repo, "verify", "--require-bitcoin") == 1


def test_verify_fails_on_missing_proof(repo: dict) -> None:
    assert run_cli(repo, "run") == 0
    (repo["root"] / "ots" / f"{repo['manifests'][0].name}.ots").unlink()
    assert run_cli(repo, "verify") == 1


def test_verify_fails_when_proof_binds_different_bytes(repo: dict) -> None:
    assert run_cli(repo, "run") == 0
    proof = repo["root"] / "ots" / f"{repo['manifests'][1].name}.ots"
    payload = json.loads(proof.read_text(encoding="utf-8"))
    payload["digest"] = "ab" * 32
    proof.write_text(json.dumps(payload), encoding="utf-8")
    assert run_cli(repo, "verify") == 1


def test_status_reports_each_state(repo: dict, capsys) -> None:
    assert run_cli(repo, "status") == 0
    output = capsys.readouterr().out
    assert output.count("unanchored") == 2

    assert run_cli(repo, "run") == 0
    assert run_cli(repo, "status") == 0
    output = capsys.readouterr().out
    assert output.count("pending calendar attestation") == 2
