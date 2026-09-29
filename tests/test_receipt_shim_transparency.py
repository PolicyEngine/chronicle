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

RELEASE_FILE_SUFFIXES = (
    ".json",
    ".producer.sig",
    ".freetsa.tsr",
    ".digicert.tsr",
)


def _release_manifests() -> list[pathlib.Path]:
    """Every canonical release manifest, in release-index order."""

    return sorted((ROOT / "releases" / "manifests").glob("[0-9]" * 4 + "-*.json"))


# The originals pin one DigiCert responder, the one that signed releases 0000
# to 0020. Later releases carry receipts from DigiCert's 2026 responder, which
# only the shim's pins admit (receipt 0.6.2's additional_signers;
# tests/test_production_tsa_pins.py covers that entry). On those releases the
# original refuses where the shim accepts, by design, so the differential
# replays the journal as it stood at the last release the originals can
# verify. That is the whole surface on which the pair is meant to agree, and
# it no longer moves when the journal grows.
ORACLE_HEAD_RELEASE_STEM = "0020-7f669f1e1364c5cc"


def _oracle_release_manifests() -> list[pathlib.Path]:
    """The release manifests the originals can verify, in release-index order."""

    manifests = _release_manifests()
    stems = [manifest.stem for manifest in manifests]
    assert ORACLE_HEAD_RELEASE_STEM in stems, stems
    return manifests[: stems.index(ORACLE_HEAD_RELEASE_STEM) + 1]


def _head_release() -> dict:
    return json.loads(_oracle_release_manifests()[-1].read_text(encoding="utf-8"))


# The numbers this differential replays are read from the committed release
# chain rather than transcribed into the test. Transcribed numbers went stale
# the first time the append lane ran. What the differential actually asserts --
# that the original and the shim emit the same bytes -- does not depend on the
# numbers at all; they only pin the text the pair is expected to agree on.
_HEAD_RELEASE = _head_release()
RELEASE_COUNT = len(_oracle_release_manifests())
NEW_RELEASE_STEM = _oracle_release_manifests()[-1].stem
FIRST_APPEND_RELEASE_STEM = _oracle_release_manifests()[1].stem
RELEASE_INDEX = int(_HEAD_RELEASE["releaseIndex"])
CANDIDATE_LINE_COUNT = int(_HEAD_RELEASE["state"]["lineCount"])
BASE_LINE_COUNT = int(_HEAD_RELEASE["append"]["previousLineCount"])
APPENDED_ROW_COUNT = int(_HEAD_RELEASE["append"]["appendedRowCount"])
PREFIX_LINE_COUNT = int(
    json.loads((ROOT / "ledger" / "immutable_prefix.json").read_text(encoding="utf-8"))[
        "prefixLineCount"
    ]
)
RELEASE_CHAIN_OK = re.compile(
    rb"release chain OK: "
    + str(RELEASE_COUNT).encode("ascii")
    + rb" releases, HEAD="
    + re.escape(NEW_RELEASE_STEM.encode("ascii"))
    + rb"\.json, digicert=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z, "
    + rb"freetsa=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\n"
)
APPEND_GATE_OK = (
    f"thesis-facts append check OK: {CANDIDATE_LINE_COUNT} rows, "
    f"immutable prefix {PREFIX_LINE_COUNT}, "
    f"+{APPENDED_ROW_COUNT} appended vs base, release {RELEASE_INDEX}\n"
).encode("utf-8")

Mutation = Callable[[pathlib.Path], None]


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", sorted(ORIGINAL_HASHES))
def test_original_oracle_fixtures_are_authenticated(name: str) -> None:
    assert _sha256(ORIGINAL_FIXTURES / name) == ORIGINAL_HASHES[name]


def _original_surface(name: str) -> frozenset[str]:
    """Read one surface literal from the authenticated original gate."""

    import ast

    module = ast.parse(
        (ORIGINAL_FIXTURES / "check_thesis_facts_append.py").read_text(encoding="utf-8")
    )
    for node in module.body:
        if (
            isinstance(node, ast.Assign)
            and [getattr(target, "id", None) for target in node.targets] == [name]
            and isinstance(node.value, ast.Call)
        ):
            return frozenset(ast.literal_eval(node.value.args[0]))
    raise AssertionError(f"{name} not found in the original gate")


def test_the_shim_gate_surface_deliberately_widens_the_originals() -> None:
    """The one place the pair is meant to disagree about classification.

    The originals' GATE_SURFACE predates scripts/receipt_pins.py, where the
    shim's trust pins now live, and never listed the uv inputs that provision
    the judge. The shim's surface covers every original entry and adds those,
    so a proposal that changes one of them is refused as mixed (with rows) or
    named as gate-only (alone), where the original judged it as plain data.
    No case in this file changes such a file, so the byte-identity asserted
    here is unaffected; tests/test_thesis_append_shim_isolation.py holds the
    shim to the wider surface.
    """

    from receipt.append_gate import _matches_surface

    from scripts.receipt_pins import APPEND_GATE_SPEC

    original_gate = _original_surface("GATE_SURFACE")
    shim_gate = APPEND_GATE_SPEC.gate_surface
    for entry in original_gate:
        if entry.endswith("/**"):
            assert entry in shim_gate, entry
        else:
            assert _matches_surface(entry, shim_gate), entry
    assert _original_surface("DATA_SURFACE") == APPEND_GATE_SPEC.data_surface
    for widened in ("scripts/receipt_pins.py", "pyproject.toml", "uv.lock"):
        assert not _matches_surface(widened, original_gate), widened
        assert _matches_surface(widened, shim_gate), widened


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
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=cwd,
        input=stdin,
        env=environment,
        capture_output=True,
        check=False,
    )


def _fixed_width_environment() -> dict[str, str]:
    """The caller's environment with argparse's wrapping width fixed at 80.

    ``argparse`` wraps help text to the terminal width, which it takes from
    ``COLUMNS`` when there is no terminal. Fixing it is what lets a help text be
    compared against a literal at all.
    """

    environment = os.environ.copy()
    environment["COLUMNS"] = "80"
    return environment


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


CANDIDATE_LINE = re.compile(
    rb"(?m)^candidate commit [0-9a-f]{40}(?:[0-9a-f]{24})? "
    rb"tree [0-9a-f]{40}(?:[0-9a-f]{24})?"
    rb"(?: base commit [0-9a-f]{40}(?:[0-9a-f]{24})? "
    rb"tree [0-9a-f]{40}(?:[0-9a-f]{24})?)?\n\Z"
)


def _split_candidate_line(stdout: bytes) -> tuple[bytes, bytes | None]:
    """Separate the shim's own last line from the gate's output.

    The shim prints one line the original never printed: the commit and tree
    the package judged, and the base pair when a base was supplied. Everything
    before it is the gate's own bytes, and those are what the differential
    compares.
    """

    match = CANDIDATE_LINE.search(stdout)
    if match is None:
        return stdout, None
    return stdout[: match.start()], match.group(0)


def _assert_gate_bytes_identical(
    original: subprocess.CompletedProcess[bytes],
    shim: subprocess.CompletedProcess[bytes],
    *,
    expected_code: int,
    candidate: str | None,
    tree: str | None,
    base: str | None = None,
    base_tree: str | None = None,
) -> None:
    """Compare the pair on the gate's bytes, and check the shim's extra line.

    The package reaches its verdict about the named commit's objects, and the
    shim prints one line the original never did: the candidate commit and
    tree, and the base pair when a base was supplied. That line is asserted
    against the object ids the fixture committed; the rest must be identical.
    """

    body, tail = _split_candidate_line(shim.stdout)
    if expected_code == 0:
        expected = f"candidate commit {candidate} tree {tree}"
        if base is not None:
            expected += f" base commit {base} tree {base_tree}"
        assert tail == f"{expected}\n".encode("utf-8")
    else:
        assert tail is None, shim.stdout
    assert original.returncode == expected_code
    assert shim.returncode == expected_code
    assert body == original.stdout
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


def _copy_custody_tree(destination: pathlib.Path) -> pathlib.Path:
    """Copy the custody state as it stood at the oracle's head release.

    The journal is append-only, so that state is the committed ledger cut to
    the head release's line count, with every later release's files removed.
    """

    root = destination / "root"
    shutil.copytree(ROOT / "ledger", root / "ledger")
    shutil.copytree(ROOT / "releases", root / "releases")
    oracle_stems = {manifest.stem for manifest in _oracle_release_manifests()}
    later_stems = {manifest.stem for manifest in _release_manifests()} - oracle_stems
    for path in (root / "releases" / "manifests").iterdir():
        if path.name.split(".", 1)[0] in later_stems:
            path.unlink()
    ledger = root / "ledger" / "official_observations.jsonl"
    rows = ledger.read_bytes().splitlines(keepends=True)
    assert len(rows) >= CANDIDATE_LINE_COUNT
    ledger.write_bytes(b"".join(rows[:CANDIDATE_LINE_COUNT]))
    return root


def test_full_release_chain_is_byte_identical(
    original_oracle: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    custody = _copy_custody_tree(tmp_path)
    arguments = ("--full", "--root", str(custody))
    original = _run_script(
        original_oracle / "scripts" / "verify_release_chain.py",
        *arguments,
    )
    shim = _run_script(SHIM_SCRIPTS / "verify_release_chain.py", *arguments)
    _assert_byte_identical(original, shim, expected_code=0)
    assert shim.stderr == b""
    # The two RFC 3161 receipt times are set by the timestamp authorities, so
    # they are matched by shape rather than transcribed; the release count and
    # the HEAD manifest name come from the committed chain.
    assert RELEASE_CHAIN_OK.fullmatch(shim.stdout), shim.stdout


def test_shim_verifies_the_live_release_chain() -> None:
    """The shim alone accepts the whole committed journal.

    Releases after the oracle's head are beyond what the originals can verify,
    so the live chain is the shim's to answer for, without a partner.
    """

    live = _release_manifests()
    shim = _run_script(
        SHIM_SCRIPTS / "verify_release_chain.py", "--full", "--root", str(ROOT)
    )
    assert shim.returncode == 0, shim.stderr
    assert shim.stderr == b""
    assert re.fullmatch(
        rb"release chain OK: "
        + str(len(live)).encode("ascii")
        + rb" releases, HEAD="
        + re.escape(live[-1].stem.encode("ascii"))
        + rb"\.json, digicert=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z, "
        + rb"freetsa=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\n",
        shim.stdout,
    ), shim.stdout


def _flip_middle_byte(path: pathlib.Path) -> None:
    payload = bytearray(path.read_bytes())
    payload[len(payload) // 2] ^= 0x01
    path.write_bytes(bytes(payload))


def _append_unwitnessed_row(root: pathlib.Path) -> None:
    ledger = root / "ledger" / "official_observations.jsonl"
    ledger.write_bytes(ledger.read_bytes() + b"{}\n")


def _corrupt_producer_signature(root: pathlib.Path) -> None:
    _flip_middle_byte(
        root / "releases" / "manifests" / f"{FIRST_APPEND_RELEASE_STEM}.producer.sig"
    )


def _corrupt_freetsa_receipt(root: pathlib.Path) -> None:
    _flip_middle_byte(
        root / "releases" / "manifests" / f"{FIRST_APPEND_RELEASE_STEM}.freetsa.tsr"
    )


@pytest.mark.parametrize(
    ("case", "mutation", "marker"),
    [
        (
            "unwitnessed-row",
            _append_unwitnessed_row,
            (
                f"HEAD release lineCount {CANDIDATE_LINE_COUNT} does not match "
                f"working-tree line count {CANDIDATE_LINE_COUNT + 1}"
            ).encode("utf-8"),
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


def _commit_candidate(root: pathlib.Path, message: str) -> str:
    """Commit whatever is in the working tree and name the commit.

    The shim judges a commit, so the fixture has to state its candidate as one.
    """

    _git(root, "add", "-A")
    _git(root, "commit", "--quiet", "--allow-empty", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _replay_latest_release(
    destination: pathlib.Path,
) -> tuple[pathlib.Path, str, str]:
    """Create the real prior-release base and commit the witnessed HEAD append.

    Returns the clone, the base commit, and the candidate commit. The candidate
    is a commit rather than a working-tree state because that is the only thing
    the shim will judge: the package reads the named commit's objects.
    """

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
    base = _commit_candidate(root, "release base")

    ledger.write_bytes(full_ledger)
    for suffix in RELEASE_FILE_SUFFIXES:
        shutil.copyfile(
            _release_file(ROOT, suffix),
            _release_file(root, suffix),
        )
    return root, base, _commit_candidate(root, "witnessed append")


def _plain_checkout(
    clone: pathlib.Path, oid: str, destination: pathlib.Path
) -> pathlib.Path:
    """Materialise one commit as a working tree for the original to judge.

    The original script judges whatever directory it is pointed at, so the fair
    comparison hands it a directory holding exactly the candidate commit --
    the same bytes the package reads from that commit's objects and
    materializes privately for its leaf verifier.
    """

    _git(clone, "worktree", "add", "--detach", str(destination), oid)
    return destination


def _tree_of(clone: pathlib.Path, oid: str) -> str:
    return _git(clone, "rev-parse", f"{oid}^{{tree}}")


def _run_append_pair(
    original_oracle: pathlib.Path,
    candidate: pathlib.Path,
    base: str,
    oid: str,
) -> tuple[subprocess.CompletedProcess[bytes], subprocess.CompletedProcess[bytes]]:
    plain = _plain_checkout(candidate, oid, candidate.parent / "original-checkout")
    original = _run_script(
        original_oracle / "scripts" / "check_thesis_facts_append.py",
        "--root",
        str(plain),
        "--base-ref",
        base,
        cwd=plain,
    )
    shim = _run_script(
        SHIM_SCRIPTS / "check_thesis_facts_append.py",
        "--root",
        str(candidate),
        "--base-ref",
        base,
        "--commit",
        oid,
        cwd=candidate,
    )
    return original, shim


# The original's own command-line surface, pinned so that a change to it is
# visible here rather than only in the fixture's digest. The shim's surface can
# no longer be identical: it takes a commit, and the commit is required.
ORIGINAL_APPEND_GATE_HELP = (
    b"usage: check_thesis_facts_append.py [-h] [--root ROOT] "
    b"[--base-ref BASE_REF]\n"
    b"\n"
    b"options:\n"
    b"  -h, --help           show this help message and exit\n"
    b"  --root ROOT          candidate worktree root (defaults to the "
    b"checker's\n"
    b"                       repository)\n"
    b"  --base-ref BASE_REF  enforce an append-only diff against this git "
    b"ref\n"
)


def test_original_append_gate_help_is_unchanged(
    original_oracle: pathlib.Path,
) -> None:
    original = _run_script(
        original_oracle / "scripts" / "check_thesis_facts_append.py",
        "--help",
        environment=_fixed_width_environment(),
    )
    assert original.returncode == 0
    assert original.stderr == b""
    assert original.stdout == ORIGINAL_APPEND_GATE_HELP


def test_shim_append_gate_help_requires_a_commit() -> None:
    shim = _run_script(
        SHIM_SCRIPTS / "check_thesis_facts_append.py",
        "--help",
        environment=_fixed_width_environment(),
    )
    assert shim.returncode == 0
    assert shim.stderr == b""
    assert b"--commit COMMIT" in shim.stdout
    # Required, so argparse spells it without brackets in the usage line.
    assert b"--commit COMMIT" in shim.stdout.split(b"\n\n", maxsplit=1)[0]
    assert b"[--commit" not in shim.stdout


def test_valid_base_ref_append_is_byte_identical(
    original_oracle: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    candidate, base, oid = _replay_latest_release(tmp_path)
    original, shim = _run_append_pair(original_oracle, candidate, base, oid)
    _assert_gate_bytes_identical(
        original,
        shim,
        expected_code=0,
        candidate=oid,
        tree=_tree_of(candidate, oid),
        base=base,
        base_tree=_tree_of(candidate, base),
    )
    assert shim.stderr == b""
    assert _split_candidate_line(shim.stdout)[0] == APPEND_GATE_OK


def _rewrite_historical_row(root: pathlib.Path) -> None:
    ledger = root / "ledger" / "official_observations.jsonl"
    rows = ledger.read_bytes().splitlines(keepends=True)
    rows[PREFIX_LINE_COUNT] = b" " + rows[PREFIX_LINE_COUNT]
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
            (f"change rewrites existing line {PREFIX_LINE_COUNT + 1}").encode("utf-8"),
        ),
        (
            "missing-assertion-version",
            _remove_appended_assertion_version,
            f"appended line {BASE_LINE_COUNT + 1}".encode("utf-8"),
        ),
        (
            "missing-release-manifest",
            _remove_new_release_manifest,
            (
                "release proposal must add exactly one manifest for index "
                f"{RELEASE_INDEX}"
            ).encode("utf-8"),
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
    candidate, base, _accepted = _replay_latest_release(tmp_path / case)
    mutation(candidate)
    # The corruption has to be committed: the package judges the named
    # commit's objects, so an uncommitted change is not part of the candidate
    # at all and would not be seen.
    oid = _commit_candidate(candidate, f"corrupt: {case}")
    original, shim = _run_append_pair(original_oracle, candidate, base, oid)
    _assert_gate_bytes_identical(
        original,
        shim,
        expected_code=1,
        candidate=None,
        tree=None,
    )
    assert shim.stdout == b""
    assert marker in _normalized_stderr(shim.stderr)
