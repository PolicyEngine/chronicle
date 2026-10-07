"""Tests for scripts/ots_anchor.py.

The suite never contacts calendar servers or Bitcoin: a fake ``ots``
executable reproduces the opentimestamps-client 0.7.2 output contract
(stamp/upgrade/info/verify, as read from ``otsclient/cmds.py`` and observed
against the real client), and every invocation is logged so the tests can
assert which operations ran. Like the real client, the fake prints ``info``
output on stdout and every logged message on stderr.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "scripts"))

import ots_anchor  # noqa: E402

CALENDARS = (
    "https://btc.calendar.catallaxy.com",
    "https://finney.calendar.eternitywall.com",
    "https://alice.btc.calendar.opentimestamps.org",
    "https://bob.btc.calendar.opentimestamps.org",
)
BITCOIN_ATTESTATIONS = (
    (963242, "34ff137ec701d2ee72ac4f88a08ddee948932f6be2840a066198acfae077a24d"),
    (963243, "583d3abcc52c06fdffa5ba3d24177b6fb6f048f63733e2f79734897648827278"),
    (963253, "20f7fb6f9e04f098f4cdecb138618d62d4e302a22f1e144c1e3f16c7d97fb00e"),
    (963257, "376fd236cf6f231bb0453fcb5b109d3dfc2bebfac2455f3e723f0a79b6919f75"),
)


def pending_line(calendar: str) -> str:
    return f"Calendar {calendar}: Pending confirmation in Bitcoin blockchain\n"


def confirmed_line(calendar: str) -> str:
    return f"Got 1 attestation(s) from {calendar}\n"


def manual_check_lines(block: int, merkle_root: str) -> str:
    return (
        "Not checking Bitcoin attestation; Bitcoin disabled\n"
        f"To verify manually, check that Bitcoin block {block} "
        f"has merkleroot {merkle_root}\n"
    )


MISMATCH_VERIFY_OUTPUT = "File does not match original!\n"
PENDING_VERIFY_OUTPUT = "".join(pending_line(calendar) for calendar in CALENDARS)
COMPLETE_VERIFY_OUTPUT = "".join(
    manual_check_lines(block, root) for block, root in BITCOIN_ATTESTATIONS
)
# A locally pending proof whose calendars have all confirmed: the client's
# verify path upgrades in memory first, then reports each attestation.
RESOLVED_VERIFY_OUTPUT = (
    "".join(confirmed_line(calendar) for calendar in CALENDARS) + COMPLETE_VERIFY_OUTPUT
)
# The normal progression: some calendars confirmed, the rest still pending.
MIXED_VERIFY_OUTPUT = (
    confirmed_line(CALENDARS[0])
    + pending_line(CALENDARS[1])
    + confirmed_line(CALENDARS[2])
    + pending_line(CALENDARS[3])
    + "".join(
        manual_check_lines(block, root) for block, root in BITCOIN_ATTESTATIONS[:2]
    )
)
# Transient calendar failures are logged with the URLError reason text.
TRANSIENT_VERIFY_OUTPUT = (
    f"Calendar {CALENDARS[0]}: timed out\n"
    f"Calendar {CALENDARS[1]}: [Errno -3] Temporary failure in name resolution\n"
    + pending_line(CALENDARS[2])
    + pending_line(CALENDARS[3])
)
PENDING_INFO_TREE = "".join(
    f"    verify PendingAttestation('{calendar}')\n" for calendar in CALENDARS
)
COMPLETE_INFO_TREE = """\
    verify PendingAttestation('https://btc.calendar.catallaxy.com')
    verify BitcoinBlockHeaderAttestation(963257)
    verify PendingAttestation('https://bob.btc.calendar.opentimestamps.org')
    verify BitcoinBlockHeaderAttestation(963243)
    verify PendingAttestation('https://alice.btc.calendar.opentimestamps.org')
    verify BitcoinBlockHeaderAttestation(963242)
    verify PendingAttestation('https://finney.calendar.eternitywall.com')
    verify BitcoinBlockHeaderAttestation(963253)
"""


def info_output(digest: str, tree: str) -> str:
    return f"File sha256 hash: {digest}\nTimestamp:\n{tree}"


FAKE_OTS = r"""
import hashlib
import json
import os
import pathlib
import sys

LOG = pathlib.Path(os.environ["FAKE_OTS_LOG"])
CALENDARS = (
    "https://btc.calendar.catallaxy.com",
    "https://finney.calendar.eternitywall.com",
    "https://alice.btc.calendar.opentimestamps.org",
    "https://bob.btc.calendar.opentimestamps.org",
)
BITCOIN_ATTESTATIONS = (
    (
        963242,
        "34ff137ec701d2ee72ac4f88a08ddee948932f6be2840a066198acfae077a24d",
    ),
    (
        963243,
        "583d3abcc52c06fdffa5ba3d24177b6fb6f048f63733e2f79734897648827278",
    ),
    (
        963253,
        "20f7fb6f9e04f098f4cdecb138618d62d4e302a22f1e144c1e3f16c7d97fb00e",
    ),
    (
        963257,
        "376fd236cf6f231bb0453fcb5b109d3dfc2bebfac2455f3e723f0a79b6919f75",
    ),
)


def log_line(message):
    # otsclient/ots.py: logging.basicConfig(format="%(message)s") -> stderr.
    print(message, file=sys.stderr)


def calendar_pending(calendar):
    log_line(f"Calendar {calendar}: Pending confirmation in Bitcoin blockchain")


def calendar_confirmed(calendar):
    log_line(f"Got 1 attestation(s) from {calendar}")


def manual_check(block, merkle_root):
    log_line("Not checking Bitcoin attestation; Bitcoin disabled")
    log_line(
        f"To verify manually, check that Bitcoin block {block} "
        f"has merkleroot {merkle_root}"
    )


def verify_pending_proof(mode):
    # upgrade_timestamp() chatter first, then one report per attestation now
    # held in memory, exactly as verify_timestamp() in otsclient/cmds.py does.
    confirmed = 0
    if mode == "pending":
        for calendar in CALENDARS:
            calendar_pending(calendar)
    elif mode == "resolved":
        for calendar in CALENDARS:
            calendar_confirmed(calendar)
        confirmed = len(CALENDARS)
    elif mode == "mixed":
        calendar_confirmed(CALENDARS[0])
        calendar_pending(CALENDARS[1])
        calendar_confirmed(CALENDARS[2])
        calendar_pending(CALENDARS[3])
        confirmed = 2
    elif mode == "transient":
        log_line(f"Calendar {CALENDARS[0]}: timed out")
        log_line(
            f"Calendar {CALENDARS[1]}: "
            "[Errno -3] Temporary failure in name resolution"
        )
        calendar_pending(CALENDARS[2])
        calendar_pending(CALENDARS[3])
    else:
        raise SystemExit(f"unexpected FAKE_OTS_VERIFY_CALENDARS: {mode}")
    for block, merkle_root in BITCOIN_ATTESTATIONS[:confirmed]:
        manual_check(block, merkle_root)


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
        for calendar in CALENDARS:
            log_line(f"Submitting to remote calendar {calendar}")
        return 0
    if command == "info":
        proof = read_proof(arguments[1])
        spoof = os.environ.get("FAKE_OTS_INFO_SPOOF")
        print(f"File sha256 hash: {proof['digest']}")
        print("Timestamp:")
        if spoof == "hash-line":
            # A second full digest line must not be trusted over the first.
            print(f"File sha256 hash: {os.environ['FAKE_OTS_SPOOF_DIGEST']}")
        if proof["state"] == "bitcoin":
            print("    verify PendingAttestation('https://btc.calendar.catallaxy.com')")
            print("    verify BitcoinBlockHeaderAttestation(963257)")
            print(
                "    verify PendingAttestation("
                "'https://bob.btc.calendar.opentimestamps.org')"
            )
            print("    verify BitcoinBlockHeaderAttestation(963243)")
            print(
                "    verify PendingAttestation("
                "'https://alice.btc.calendar.opentimestamps.org')"
            )
            print("    verify BitcoinBlockHeaderAttestation(963242)")
            print(
                "    verify PendingAttestation("
                "'https://finney.calendar.eternitywall.com')"
            )
            print("    verify BitcoinBlockHeaderAttestation(963253)")
        elif spoof == "attestation":
            print(
                "verify PendingAttestation("
                "'https://fake/BitcoinBlockHeaderAttestation(1)')"
            )
        elif spoof == "hash-in-uri":
            print(
                "    verify PendingAttestation('https://fake/"
                f"File sha256 hash: {os.environ['FAKE_OTS_SPOOF_DIGEST']}')"
            )
        else:
            for calendar in CALENDARS:
                print(f"    verify PendingAttestation('{calendar}')")
        return 0
    if command == "upgrade":
        path = pathlib.Path(arguments[1])
        proof = read_proof(path)
        upgrade = os.environ.get("FAKE_OTS_UPGRADE")
        if upgrade == "success":
            proof["state"] = "bitcoin"
            write_proof(path, proof)
            pathlib.Path(str(path) + ".bak").write_text(
                "backup", encoding="utf-8"
            )
            for calendar in CALENDARS:
                calendar_confirmed(calendar)
            log_line("Success! Timestamp complete")
            return 0
        if upgrade == "broken":
            path.replace(pathlib.Path(str(path) + ".bak"))
            log_line("calendar response could not be serialized")
            return 2
        for calendar in CALENDARS:
            calendar_pending(calendar)
        log_line("Failed! Timestamp not complete")
        return 1
    if command == "verify":
        target = pathlib.Path(arguments[arguments.index("-f") + 1])
        proof = read_proof(arguments[-1])
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if (
            digest != proof["digest"]
            or os.environ.get("FAKE_OTS_VERIFY_FORCE_MISMATCH") == "yes"
        ):
            # otsclient/cmds.py verify_command: the digest check happens
            # before any calendar is consulted.
            log_line("File does not match original!")
            return 1
        abnormal_exit = os.environ.get("FAKE_OTS_VERIFY_EXIT")
        if abnormal_exit:
            log_line("Traceback (most recent call last):")
            log_line("RuntimeError: simulated client crash")
            return int(abnormal_exit)
        if proof["state"] == "bitcoin":
            for block, merkle_root in BITCOIN_ATTESTATIONS:
                manual_check(block, merkle_root)
            return 1
        verify_pending_proof(os.environ.get("FAKE_OTS_VERIFY_CALENDARS", "pending"))
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


def invoke_fake_ots(repo: dict, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*shlex.split(repo["ots_bin"]), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def proof_for(repo: dict, index: int) -> Path:
    return repo["root"] / "ots" / f"{repo['manifests'][index].name}.ots"


def rebind_proof(proof: Path, **changes: str) -> None:
    """Rewrite a fake proof so it binds other bytes or carries another state."""

    payload = json.loads(proof.read_text(encoding="utf-8"))
    payload.update(changes)
    proof.write_text(json.dumps(payload), encoding="utf-8")


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
        assert json.loads(proof.read_text(encoding="utf-8"))["state"] == "bitcoin"
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
    proof_for(repo, 0).unlink()
    assert run_cli(repo, "verify") == 1


def test_verify_fails_when_proof_binds_different_bytes(repo: dict) -> None:
    assert run_cli(repo, "run") == 0
    proof = proof_for(repo, 1)
    rebind_proof(proof, digest="ab" * 32)
    assert (
        ots_anchor.classify_proof(
            repo["manifests"][1], proof, shlex.split(repo["ots_bin"])
        )
        == "mismatch"
    )
    assert run_cli(repo, "verify") == 1


def test_fake_client_emits_the_real_mismatch_line(repo: dict) -> None:
    """opentimestamps-client 0.7.2 logs ``File does not match original!``."""

    assert run_cli(repo, "run") == 0
    proof = proof_for(repo, 1)
    verify = invoke_fake_ots(
        repo, "--no-bitcoin", "verify", "-f", str(repo["manifests"][0]), str(proof)
    )
    assert verify.returncode == 1
    assert verify.stdout == ""
    assert verify.stderr == MISMATCH_VERIFY_OUTPUT
    assert verify.stderr.strip() == ots_anchor._MISMATCH_LINE


def test_verify_enumerates_every_mismatch(repo: dict, capsys) -> None:
    assert run_cli(repo, "run") == 0
    for index in (0, 1):
        rebind_proof(proof_for(repo, index), digest="ab" * 32)
    capsys.readouterr()

    assert run_cli(repo, "verify") == 1
    captured = capsys.readouterr()
    failures = [line for line in captured.err.splitlines() if "FAIL" in line]
    assert failures == [
        f"  FAIL {manifest.name}: proof does not match manifest bytes"
        for manifest in repo["manifests"]
    ]
    assert "0 locally Bitcoin-complete, 0 pending locally" in captured.out


def test_verify_reports_tampered_manifest_without_aborting(repo: dict, capsys) -> None:
    assert run_cli(repo, "run") == 0
    repo["manifests"][0].write_bytes(b'{"releaseIndex": 0, "tampered": true}\n')
    capsys.readouterr()

    assert run_cli(repo, "verify") == 1
    captured = capsys.readouterr()
    failures = [line for line in captured.err.splitlines() if "FAIL" in line]
    assert failures == [
        f"  FAIL {repo['manifests'][0].name}: manifest bytes contradict its filename"
    ]
    assert "0 locally Bitcoin-complete, 1 pending locally" in captured.out


def test_status_prints_mismatch_for_tampered_manifest_and_proof(
    repo: dict, capsys
) -> None:
    assert run_cli(repo, "run") == 0
    repo["manifests"][0].write_bytes(b'{"releaseIndex": 0, "tampered": true}\n')
    rebind_proof(proof_for(repo, 1), digest="ab" * 32)
    capsys.readouterr()

    assert run_cli(repo, "status") == 0
    assert capsys.readouterr().out.splitlines() == [
        f"{repo['manifests'][0].name}: MISMATCH (manifest bytes contradict its filename)",
        f"{repo['manifests'][1].name}: MISMATCH (proof does not match manifest bytes)",
    ]


def test_status_reports_multi_calendar_pending_proofs(repo: dict, capsys) -> None:
    assert run_cli(repo, "status") == 0
    output = capsys.readouterr().out
    assert output.count("unanchored") == 2

    assert run_cli(repo, "run") == 0
    proof = proof_for(repo, 0)
    verify = invoke_fake_ots(
        repo,
        "--no-bitcoin",
        "verify",
        "-f",
        str(repo["manifests"][0]),
        str(proof),
    )
    assert verify.returncode == 1
    assert verify.stdout == ""
    assert verify.stderr == PENDING_VERIFY_OUTPUT
    info = invoke_fake_ots(repo, "info", str(proof))
    assert info.returncode == 0
    digest = hashlib.sha256(repo["manifests"][0].read_bytes()).hexdigest()
    assert info.stdout == info_output(digest, PENDING_INFO_TREE)
    assert info.stderr == ""
    upgrade = invoke_fake_ots(repo, "upgrade", str(proof))
    assert upgrade.returncode == 1
    assert upgrade.stderr == PENDING_VERIFY_OUTPUT + "Failed! Timestamp not complete\n"

    commands_before = len(logged_commands(repo))
    assert run_cli(repo, "status") == 0
    output = capsys.readouterr().out
    assert output.count("pending local proof") == 2
    assert logged_commands(repo)[commands_before:] == ["info", "verify"] * 2


def test_status_prefers_bitcoin_info_with_leftover_pending_attestations(
    repo: dict, capsys
) -> None:
    assert run_cli(repo, "run") == 0
    proof = proof_for(repo, 0)
    rebind_proof(proof, state="bitcoin")

    info = invoke_fake_ots(repo, "info", str(proof))
    assert info.returncode == 0
    digest = hashlib.sha256(repo["manifests"][0].read_bytes()).hexdigest()
    assert info.stdout == info_output(digest, COMPLETE_INFO_TREE)
    verify = invoke_fake_ots(
        repo,
        "--no-bitcoin",
        "verify",
        "-f",
        str(repo["manifests"][0]),
        str(proof),
    )
    assert verify.returncode == 1
    assert verify.stderr == COMPLETE_VERIFY_OUTPUT

    assert run_cli(repo, "status") == 0
    output = capsys.readouterr().out
    assert output.count("bitcoin attestation stored locally") == 1
    assert output.count("pending local proof") == 1


@pytest.mark.parametrize(
    ("calendars", "expected_output", "logged_marker"),
    [
        ("mixed", MIXED_VERIFY_OUTPUT, "Got 1 attestation(s) from"),
        ("transient", TRANSIENT_VERIFY_OUTPUT, "Temporary failure in name resolution"),
        ("resolved", RESOLVED_VERIFY_OUTPUT, "Got 1 attestation(s) from"),
    ],
    ids=["mixed", "transient", "resolved"],
)
def test_run_reaches_upgrade_despite_verify_calendar_chatter(
    repo: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
    calendars: str,
    expected_output: str,
    logged_marker: str,
) -> None:
    """Calendar progress and transient errors during verify never abort a run.

    The real client's verify path upgrades in memory first, so a locally
    pending proof whose calendars have confirmed prints ``Got N
    attestation(s) from ...`` lines, and a calendar timeout prints
    ``Calendar <url>: <error>``. Neither is a grammar the tool checks: the
    binding comes from ``ots info``, the chatter is logged, and the run goes
    on to ``upgrade_proof`` for every pending proof.
    """

    assert run_cli(repo, "run") == 0
    monkeypatch.setenv("FAKE_OTS_VERIFY_CALENDARS", calendars)
    proof = proof_for(repo, 0)
    verify = invoke_fake_ots(
        repo, "--no-bitcoin", "verify", "-f", str(repo["manifests"][0]), str(proof)
    )
    assert verify.returncode == 1
    assert verify.stderr == expected_output
    upgrades_before = logged_commands(repo).count("upgrade")
    capsys.readouterr()

    assert run_cli(repo, "run") == 0
    captured = capsys.readouterr()
    assert logged_commands(repo).count("upgrade") == upgrades_before + 2
    assert "still pending 2" in captured.out
    assert f"ots verify {proof.name}: exit status 1" in captured.err
    assert logged_marker in captured.err

    assert run_cli(repo, "status") == 0
    assert capsys.readouterr().out.count("pending local proof") == 2
    assert run_cli(repo, "verify") == 0


def test_verify_chatter_is_indented_in_the_log(
    repo: dict, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Echoed calendar text can never start a log line."""

    assert run_cli(repo, "run") == 0
    monkeypatch.setenv("FAKE_OTS_VERIFY_CALENDARS", "transient")
    capsys.readouterr()

    assert run_cli(repo, "status") == 0
    err_lines = capsys.readouterr().err.splitlines()
    echoed = [line for line in err_lines if "Calendar " in line]
    assert len(echoed) == 8
    assert all(line.startswith("  ") for line in echoed)


def test_classify_reports_mismatch_from_info_digest_without_calendar_traffic(
    repo: dict,
) -> None:
    assert run_cli(repo, "run") == 0
    proof = proof_for(repo, 1)
    rebind_proof(proof, digest="ab" * 32)
    commands_before = len(logged_commands(repo))

    assert (
        ots_anchor.classify_proof(
            repo["manifests"][1], proof, shlex.split(repo["ots_bin"])
        )
        == "mismatch"
    )
    assert logged_commands(repo)[commands_before:] == ["info"]


def test_classify_fails_closed_on_the_clients_mismatch_line(
    repo: dict, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Even when ``ots info`` agrees, the client's own mismatch line wins."""

    assert run_cli(repo, "run") == 0
    monkeypatch.setenv("FAKE_OTS_VERIFY_FORCE_MISMATCH", "yes")
    proof = proof_for(repo, 0)
    assert (
        ots_anchor.classify_proof(
            repo["manifests"][0], proof, shlex.split(repo["ots_bin"])
        )
        == "mismatch"
    )
    capsys.readouterr()
    assert run_cli(repo, "verify") == 1
    assert capsys.readouterr().err.count("FAIL") == 2
    assert run_cli(repo, "run") == 1


def test_classify_fails_closed_on_abnormal_verify_exit(
    repo: dict, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    assert run_cli(repo, "run") == 0
    monkeypatch.setenv("FAKE_OTS_VERIFY_EXIT", "2")
    capsys.readouterr()

    assert run_cli(repo, "status") == 1
    captured = capsys.readouterr()
    assert captured.out.count("ERROR (ots verify did not run to completion") == 2
    assert run_cli(repo, "verify") == 1
    assert run_cli(repo, "run") == 1


def test_inspect_proof_reads_digest_and_state(repo: dict) -> None:
    assert run_cli(repo, "run") == 0
    proof = proof_for(repo, 0)
    ots_bin = shlex.split(repo["ots_bin"])
    digest = hashlib.sha256(repo["manifests"][0].read_bytes()).hexdigest()
    assert ots_anchor.inspect_proof(proof, ots_bin) == ots_anchor.ProofInfo(
        digest=digest, state="pending"
    )
    rebind_proof(proof, state="bitcoin", digest=digest.upper())
    assert ots_anchor.inspect_proof(proof, ots_bin) == ots_anchor.ProofInfo(
        digest=digest, state="bitcoin"
    )


def test_inspect_proof_fails_closed_without_exactly_one_digest_line(
    repo: dict, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    assert run_cli(repo, "run") == 0
    proof = proof_for(repo, 0)
    rebind_proof(proof, digest="ab" * 32)
    digest = hashlib.sha256(repo["manifests"][0].read_bytes()).hexdigest()
    monkeypatch.setenv("FAKE_OTS_INFO_SPOOF", "hash-line")
    monkeypatch.setenv("FAKE_OTS_SPOOF_DIGEST", digest)

    with pytest.raises(ots_anchor.AnchorError, match="2 file hash lines"):
        ots_anchor.inspect_proof(proof, shlex.split(repo["ots_bin"]))
    capsys.readouterr()
    assert run_cli(repo, "status") == 1
    assert "ERROR (ots info for" in capsys.readouterr().out
    assert run_cli(repo, "run") == 1


def test_inspect_proof_ignores_digest_text_inside_attestation_lines(
    repo: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_cli(repo, "run") == 0
    proof = proof_for(repo, 0)
    rebind_proof(proof, digest="ab" * 32)
    digest = hashlib.sha256(repo["manifests"][0].read_bytes()).hexdigest()
    monkeypatch.setenv("FAKE_OTS_INFO_SPOOF", "hash-in-uri")
    monkeypatch.setenv("FAKE_OTS_SPOOF_DIGEST", digest)

    ots_bin = shlex.split(repo["ots_bin"])
    assert ots_anchor.inspect_proof(proof, ots_bin).digest == "ab" * 32
    assert ots_anchor.classify_proof(repo["manifests"][0], proof, ots_bin) == "mismatch"


def test_manifests_option_reads_external_checkout(repo: dict) -> None:
    external = repo["root"].parent / "journal" / "releases" / "manifests"
    external.mkdir(parents=True)
    manifest_names = [manifest.name for manifest in repo["manifests"]]
    for manifest in repo["manifests"]:
        manifest.replace(external / manifest.name)

    assert run_cli(repo, "run", "--manifests", str(external)) == 0
    assert sorted(proof.name for proof in (repo["root"] / "ots").iterdir()) == [
        f"{name}.ots" for name in manifest_names
    ]
    assert not list(external.glob("*.ots"))


def test_guard_accepts_only_ots_and_rejects_outside_changes(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=OTS test",
            "-c",
            "user.email=ots@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
        check=True,
    )
    (tmp_path / "ots").mkdir()
    (tmp_path / "ots" / "proof.ots").write_text("proof", encoding="utf-8")

    assert ots_anchor.main(["guard", "--root", str(tmp_path)]) == 0
    (tmp_path / "README.md").write_text("changed\n", encoding="utf-8")
    assert ots_anchor.main(["guard", "--root", str(tmp_path)]) == 1


def test_run_reverifies_bitcoin_complete_proof_binding(repo: dict) -> None:
    assert run_cli(repo, "run") == 0
    proof = proof_for(repo, 0)
    rebind_proof(proof, state="bitcoin", digest="ab" * 32)
    upgrades_before = logged_commands(repo).count("upgrade")

    assert run_cli(repo, "run") == 1
    assert logged_commands(repo).count("upgrade") == upgrades_before


def test_local_state_resists_calendar_output_spoofing(
    repo: dict, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    assert run_cli(repo, "run") == 0
    monkeypatch.setenv("FAKE_OTS_INFO_SPOOF", "attestation")
    monkeypatch.setenv("FAKE_OTS_VERIFY_CALENDARS", "resolved")

    assert run_cli(repo, "status") == 0
    assert capsys.readouterr().out.count("pending local proof") == 2
    assert run_cli(repo, "verify", "--require-bitcoin") == 1
    upgrades_before = logged_commands(repo).count("upgrade")
    assert run_cli(repo, "run") == 0
    assert logged_commands(repo).count("upgrade") == upgrades_before + 2


def test_failed_upgrade_restores_original_backup(
    repo: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_cli(repo, "run") == 0
    proof = proof_for(repo, 0)
    original = proof.read_bytes()
    monkeypatch.setenv("FAKE_OTS_UPGRADE", "broken")

    assert run_cli(repo, "run") == 1
    assert proof.read_bytes() == original
    assert not proof.with_name(proof.name + ".bak").exists()


def test_timed_out_upgrade_restores_original_backup(
    repo: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_cli(repo, "run") == 0
    proof = proof_for(repo, 0)
    original = proof.read_bytes()
    real_run_ots = ots_anchor._run_ots

    def time_out_after_backup(ots_bin, arguments, *, timeout=300):
        if arguments[0] == "upgrade":
            upgrade_target = Path(arguments[1])
            upgrade_target.replace(
                upgrade_target.with_name(upgrade_target.name + ".bak")
            )
            raise ots_anchor.AnchorError("ots timed out")
        return real_run_ots(ots_bin, arguments, timeout=timeout)

    monkeypatch.setattr(ots_anchor, "_run_ots", time_out_after_backup)
    assert run_cli(repo, "run") == 1
    assert proof.read_bytes() == original
    assert not proof.with_name(proof.name + ".bak").exists()


def test_run_rejects_symlinked_proof_directory(repo: dict) -> None:
    proof_directory = repo["root"] / "ots"
    proof_directory.symlink_to(repo["manifest_dir"], target_is_directory=True)

    assert run_cli(repo, "run") == 1
    assert not list(repo["manifest_dir"].glob("*.ots"))
