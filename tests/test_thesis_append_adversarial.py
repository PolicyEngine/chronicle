"""Adversarial verification of the Thesis observation append gate.

These tests exercise counterexamples from the 2026-07-10 ledger review. The
cases that pinned open findings 3, 6, and 13 are now real assertions that the
hardened gate rejects the attack. The remaining strict-xfail tests document
boundaries that are deliberately out of scope for this pass (provenance-format
validation, the no-base-ref full-file mode, and per-commit history walking);
each fails loudly if it ever starts passing.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import os
import subprocess
import sys
from pathlib import Path

import pytest

from arch.core import (
    AggregateFact,
    Aggregation,
    EntityDimension,
    GeographyDimension,
    Measure,
    PeriodDimension,
    SourceProvenance,
    validate_facts,
)

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "ledger" / "official_observations.jsonl"
PREFIX_PATH = ROOT / "ledger" / "immutable_prefix.json"

sys.path.insert(0, str(ROOT / "scripts"))

from check_thesis_facts_append import (  # noqa: E402
    AppendError,
    check_rows,
    effective_current_rows,
    expected_assertion_version_id,
)


def _read_lines() -> list[str]:
    return [
        line
        for line in LEDGER_PATH.read_text(encoding="utf-8").split("\n")
        if line.strip()
    ]


def _json_line(row: dict) -> str:
    return json.dumps(row, separators=(",", ":"))


def _to_aggregate_fact(row: dict) -> AggregateFact:
    return AggregateFact(
        value=row["value"],
        period=PeriodDimension(**row["period"]),
        geography=GeographyDimension(**row["geography"]),
        entity=EntityDimension(**row["entity"]),
        measure=Measure(**row["measure"]),
        aggregation=Aggregation(**row["aggregation"]),
        source=SourceProvenance(**row["source"]),
        filters=row.get("filters", {}),
        domain=row.get("domain", "all"),
        label=row.get("label"),
        source_record_id=row.get("source_record_id"),
        source_cell_keys=tuple(row.get("source_cell_keys", ())),
        source_row_keys=tuple(row.get("source_row_keys", ())),
    )


def _appended_row(
    original: dict,
    *,
    value_delta: float = 0,
    source_record_id: str | None = None,
) -> dict:
    row = copy.deepcopy(original)
    row["value"] += value_delta
    if source_record_id is not None:
        row["source_record_id"] = source_record_id
    row.update(
        {
            "retrievedAt": "2026-07-11T00:00:00Z",
            "sourceVintage": "2026-07-11",
            "ledgerRepoSha": "a" * 40,
            "responseArchive": {
                "sha256": "b" * 64,
                "contentEncoding": "gzip",
            },
        }
    )
    row.pop("targetContentHash", None)
    row.pop("sourceBindingProjection", None)
    row["assertionVersion"] = {
        "id": expected_assertion_version_id(row),
        "supersedes": None,
    }
    return row


def _write_checker_fixture(path: Path, ledger_text: str, manifest: dict) -> None:
    ledger_dir = path / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    (ledger_dir / "official_observations.jsonl").write_text(
        ledger_text, encoding="utf-8"
    )
    (ledger_dir / "immutable_prefix.json").write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
    )
    scripts_dir = path / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    for name in (
        "check_thesis_facts_append.py",
        "canonical_json.py",
        "verify_release_chain.py",
    ):
        (scripts_dir / name).write_text(
            (ROOT / "scripts" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def _commit_candidate(path: Path) -> str:
    """Commit whatever the fixture has just written and name that commit.

    The installed receipt package judges the named commit's objects, so a
    fixture that mutated a working tree has not yet stated the candidate.
    Committing is how the fixture states its candidate. An empty commit is
    allowed because some fixtures change nothing and the question -- does this
    commit pass -- is still a real one.
    """

    _git(path, "add", "-A")
    _git(path, "commit", "-q", "--allow-empty", "-m", "candidate")
    return _git(path, "rev-parse", "HEAD")


def _run_checker(
    path: Path, base_ref: str | None = None
) -> subprocess.CompletedProcess:
    commit = _commit_candidate(path)
    command = [
        sys.executable,
        str(path / "scripts/check_thesis_facts_append.py"),
        "--commit",
        commit,
    ]
    if base_ref is not None:
        command.extend(["--base-ref", base_ref])
    completed = subprocess.run(command, cwd=path, capture_output=True, text=True)
    _assert_verdict_subject(completed, path, commit, base_ref=base_ref)
    return completed


def _assert_verdict_subject(
    completed: subprocess.CompletedProcess,
    path: Path,
    commit: str,
    *,
    base_ref: str | None = None,
) -> None:
    """The second line names the candidate pair, and the base pair when a base was given."""

    if completed.returncode == 0:
        tree = _git(path, "rev-parse", f"{commit}^{{tree}}")
        subject = f"candidate commit {commit} tree {tree}"
        if base_ref is not None:
            base = _git(path, "rev-parse", base_ref)
            subject += (
                f" base commit {base} tree {_git(path, 'rev-parse', base + '^{tree}')}"
            )
        assert completed.stdout.splitlines()[1:] == [subject]
    else:
        assert "candidate commit " not in completed.stdout


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=path, capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


def _init_fixture_repo(path: Path) -> str:
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Append Gate Test")
    _git(path, "config", "user.email", "append-gate@example.invalid")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "base")
    return _git(path, "rev-parse", "HEAD")


def _rehash_manifest(lines: list[str]) -> dict:
    manifest = json.loads(PREFIX_PATH.read_text(encoding="utf-8"))
    count = int(manifest["prefixLineCount"])
    manifest["lineSha256s"] = [
        hashlib.sha256(line.encode("utf-8")).hexdigest() for line in lines[:count]
    ]
    manifest["prefixSha256"] = hashlib.sha256(
        ("\n".join(lines[:count]) + "\n").encode("utf-8")
    ).hexdigest()
    return manifest


def _extend_manifest_to_all_lines(lines: list[str]) -> dict:
    manifest = json.loads(PREFIX_PATH.read_text(encoding="utf-8"))
    manifest["prefixLineCount"] = len(lines)
    manifest["lineSha256s"] = [
        hashlib.sha256(line.encode("utf-8")).hexdigest() for line in lines
    ]
    manifest["prefixSha256"] = hashlib.sha256(
        ("\n".join(lines) + "\n").encode("utf-8")
    ).hexdigest()
    return manifest


def _initialize_surface_fixture(path: Path) -> tuple[list[str], str]:
    lines = _read_lines()
    manifest = json.loads(PREFIX_PATH.read_text(encoding="utf-8"))
    _write_checker_fixture(path, "\n".join(lines) + "\n", manifest)
    return lines, _init_fixture_repo(path)


def _append_surface_fixture_row(path: Path, lines: list[str], identity: str) -> None:
    row = _appended_row(
        json.loads(lines[-1]),
        value_delta=1,
        source_record_id=identity,
    )
    (path / "ledger" / "official_observations.jsonl").write_text(
        "\n".join([*lines, _json_line(row)]) + "\n",
        encoding="utf-8",
    )


def _add_untracked_gate_anchor(path: Path) -> Path:
    anchor = path / "releases" / "anchors" / "test-producer.pub"
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text("test public key only\n", encoding="utf-8")
    return anchor


def test_two_class_data_only_proposal_passes(tmp_path):
    lines, base = _initialize_surface_fixture(tmp_path)
    _append_surface_fixture_row(
        tmp_path,
        lines,
        "verification.surface.data-only",
    )

    completed = _run_checker(tmp_path, base)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "+1 appended vs base" in completed.stdout


def test_two_class_gate_only_proposal_passes(tmp_path):
    _lines, base = _initialize_surface_fixture(tmp_path)
    _add_untracked_gate_anchor(tmp_path)

    completed = _run_checker(tmp_path, base)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "gate-only proposal" in completed.stdout
    assert "DATA_SURFACE unchanged" in completed.stdout
    assert "releases/anchors/test-producer.pub" in completed.stdout


def test_two_class_mixed_proposal_is_rejected_before_data_checks(tmp_path):
    lines, base = _initialize_surface_fixture(tmp_path)
    _append_surface_fixture_row(
        tmp_path,
        lines,
        "verification.surface.mixed",
    )
    _add_untracked_gate_anchor(tmp_path)

    completed = _run_checker(tmp_path, base)

    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert (
        "mixed data/gate proposal is forbidden: DATA_SURFACE changes="
        "['ledger/official_observations.jsonl']; GATE_SURFACE changes="
        "['releases/anchors/test-producer.pub']; split them into separate "
        "pull requests"
    ) in completed.stderr


@pytest.mark.parametrize(
    "dependency",
    ["canonical_json.py", "verify_release_chain.py"],
)
def test_base_gate_uses_base_script_and_dependency_imports(
    tmp_path,
    dependency: str,
):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _lines, base = _initialize_surface_fixture(candidate)

    base_gate = tmp_path / "base-gate"
    subprocess.run(
        ["git", "clone", "--no-checkout", str(candidate), str(base_gate)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(base_gate),
            "fetch",
            "--no-tags",
            "--depth",
            "1",
            "origin",
            base,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(base_gate), "checkout", "--detach", base],
        check=True,
        capture_output=True,
        text=True,
    )

    candidate_gate_marker = tmp_path / "candidate-gate-executed"
    candidate_dependency_marker = tmp_path / "candidate-dependency-imported"
    (candidate / "scripts" / "check_thesis_facts_append.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(candidate_gate_marker)!r}).write_text('executed')\n"
        "raise SystemExit(97)\n",
        encoding="utf-8",
    )
    (candidate / "scripts" / dependency).write_text(
        "from pathlib import Path\n"
        f"Path({str(candidate_dependency_marker)!r}).write_text('imported')\n"
        "raise RuntimeError('candidate dependency imported')\n",
        encoding="utf-8",
    )

    candidate_commit = _commit_candidate(candidate)

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(base_gate / "scripts")
    environment["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            str(base_gate / "scripts" / "check_thesis_facts_append.py"),
            "--root",
            str(candidate),
            "--commit",
            candidate_commit,
            "--base-ref",
            base,
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "gate-only proposal" in completed.stdout
    _assert_verdict_subject(completed, candidate, candidate_commit, base_ref=base)
    assert not candidate_gate_marker.exists()
    assert not candidate_dependency_marker.exists()


def test_workflow_has_a_base_owned_trusted_pr_gate():
    workflow = (ROOT / ".github" / "workflows" / "thesis-facts-append.yml").read_text(
        encoding="utf-8"
    )

    # A pull_request workflow is loaded from the candidate merge ref, so its
    # detached base-script step can itself be replaced. Once installed on the
    # default branch, the base-owned target event is not candidate-controlled;
    # it fetches the merge ref as inert data and executes only base modules.
    for required in (
        "\n  pull_request_target:\n",
        "permissions:\n  contents: read\n",
        "trusted-base-append-gate:",
        "name: Trusted base append gate",
        '[[ "$BASE_SHA" =~ ^[0-9a-f]{40,64}$ ]]',
        '[[ "$MERGE_SHA" =~ ^[0-9a-f]{40,64}$ ]]',
        '[[ "$PR_NUMBER" =~ ^[0-9]+$ ]]',
        '"+refs/pull/${PR_NUMBER}/merge:refs/remotes/origin/pr-merge"',
        'PYTHONPATH="$base_gate/scripts"',
        # The base gate provisions the BASE commit's own hash-locked env and
        # runs with it — dropping either line would let a shimmed base gate
        # ModuleNotFoundError or resolve deps the PR could influence.
        'uv sync --locked --no-dev --project "$base_gate"',
        'uv run --locked --no-dev --project "$base_gate"',
        'python "$base_gate/scripts/check_thesis_facts_append.py"',
        '--root "$candidate"',
        '--base-ref "$BASE_SHA"',
        # The commit under judgement is named on the command line in all three
        # invocations. Dropping any of them would leave the gate judging
        # whichever HEAD the clone at --root happened to name. The package's
        # object reader binds its verdict to this explicit commit and tree.
        '--commit "$MERGE_SHA"',
        '--commit "$workspace_sha"',
        '--commit "$GITHUB_SHA"',
        "fetch-depth: 0",
    ):
        assert required in workflow

    # And the pull_request job's id is read from the workspace and shape-checked
    # before it is passed, the same way the other two are.
    assert 'workspace_sha="$(git -C "$GITHUB_WORKSPACE" rev-parse HEAD)"' in workflow
    assert '[[ "$workspace_sha" =~ ^[0-9a-f]{40,64}$ ]]' in workflow

    # Both base-gate jobs ask the base gate what it accepts before invoking it,
    # because the base gate on any pull request opened before --commit merged
    # does not accept it and the one after requires it. The question goes to
    # base-owned code about its own interface. The fallback is never silent, so
    # a run that took it says so in its own log; requiring the notice here is
    # what stops the fallback being quietly widened into the ordinary path.
    assert workflow.count('base_gate_help="$(') == 2
    assert workflow.count('case "$base_gate_help" in') == 2
    assert workflow.count("*--commit*)") == 2
    assert workflow.count('echo "note: the base gate at') == 2
    # Shell `case` takes the first matching arm, so the order of the arms is
    # part of the contract: the `--commit` arm must come before the fallback
    # in each block, and the `--commit` invocation must sit inside its arm
    # (peer review of #241, round 1).
    for block in workflow.split('case "$base_gate_help" in')[1:]:
        body = block.split("esac", 1)[0]
        commit_arm = body.index("*--commit*)")
        fallback = re.search(r"^\s*\*\)\s*$", body, re.M)
        assert fallback is not None
        fallback_arm = fallback.start()
        assert commit_arm < fallback_arm
        assert '--commit "$' in body[commit_arm:fallback_arm]
        assert '--commit "$' not in body[fallback_arm:]


def test_duplicate_identity_without_supersedes_is_rejected():
    lines = _read_lines()
    duplicate = _appended_row(json.loads(lines[-1]), value_delta=1)

    with pytest.raises(AppendError, match="without superseding"):
        check_rows([*lines, _json_line(duplicate)], len(lines))


def test_mismatched_av2_id_is_rejected():
    lines = _read_lines()
    row = _appended_row(
        json.loads(lines[-1]),
        source_record_id="verification.unique.mismatched_av2",
    )
    row["assertionVersion"]["id"] = "av2:" + "0" * 64

    with pytest.raises(AppendError, match="does not match its content"):
        check_rows([*lines, _json_line(row)], len(lines))


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        ("measure.source_concept", "DIFFERENT_PUBLISHER_SERIES"),
        ("measure.concept_relation", "approximate"),
        ("measure.concept_authority", "different_authority"),
        ("measure.legal_vintage", "different_legal_vintage"),
        ("source.source_file", "different_release.csv"),
        ("source.source_sha256", "d" * 64),
        ("source_cell_keys", ["different:publisher:cell"]),
        ("source_row_keys", ["different:publisher:row"]),
    ],
)
def test_av2_binds_material_concept_and_source_lineage(path: str, replacement: object):
    # Review finding 6: av1 projected only measure concept/unit and four source
    # fields, so these material changes collided. The av2 projection binds the
    # complete concept mapping, exact source file/digest, and row/cell lineage.
    original = json.loads(_read_lines()[-1])
    changed = copy.deepcopy(original)
    if "." in path:
        parent, key = path.split(".", maxsplit=1)
        changed[parent][key] = replacement
    else:
        changed[path] = replacement

    assert expected_assertion_version_id(changed) != (
        expected_assertion_version_id(original)
    )


def test_av2_binds_the_archived_response_digest():
    # av1 could reuse an id across different archived response bytes; av2 binds
    # responseArchive.sha256 so re-fetched bytes are a distinct assertion.
    original = json.loads(_read_lines()[-1])
    changed = copy.deepcopy(original)
    changed["responseArchive"] = {**changed["responseArchive"], "sha256": "e" * 64}

    assert expected_assertion_version_id(changed) != (
        expected_assertion_version_id(original)
    )


def test_inconsistent_supersedes_chain_is_rejected():
    lines = _read_lines()
    original = json.loads(lines[-1])
    original_id = expected_assertion_version_id(original)
    first_correction = _appended_row(original, value_delta=1)
    first_correction["assertionVersion"]["supersedes"] = original_id
    second_correction = _appended_row(original, value_delta=2)
    second_correction["assertionVersion"]["supersedes"] = original_id

    with pytest.raises(AppendError, match="but the active version"):
        check_rows(
            [*lines, _json_line(first_correction), _json_line(second_correction)],
            len(lines),
        )


def test_pre_versioning_row_is_addressable_by_recomputed_av2_id():
    lines = _read_lines()
    original = json.loads(lines[-1])
    correction = _appended_row(original, value_delta=1)
    correction["assertionVersion"]["supersedes"] = expected_assertion_version_id(
        original
    )

    check_rows([*lines, _json_line(correction)], len(lines))


def test_full_ci_fact_validation_accepts_an_explicit_correction():
    # Review finding 6: the append gate accepts an explicit correction, but the
    # required aggregate-fact validation used to reject it as a duplicate key.
    # Validating the supersede-aware effective current view resolves the
    # documented correction path.
    rows = [json.loads(line) for line in _read_lines()]
    original = rows[-1]
    correction = _appended_row(original, value_delta=1)
    correction["assertionVersion"]["supersedes"] = expected_assertion_version_id(
        original
    )

    # The append gate itself accepts exactly the advertised correction shape.
    lines = [_json_line(row) for row in rows]
    check_rows([*lines, _json_line(correction)], len(lines))

    # The subsequently required aggregate-fact validation now runs on the
    # supersede-aware current view, which drops the superseded original.
    current = effective_current_rows([*rows, correction])
    report = validate_facts([_to_aggregate_fact(row) for row in current])
    assert report.valid, report.to_dict()
    # The correction replaces the original one for one. Compare with the
    # ledger's own current view, not its row count: once the ledger holds a
    # real correction (Thesis's six first-print corrections, 2026-10-19), the
    # current view is already shorter than the file.
    assert len(current) == len(effective_current_rows(rows))
    assert original not in current
    assert correction in current


def test_correction_chain_cannot_restore_a_superseded_legacy_value():
    # Review finding 6: an A->B->A chain must not resurrect a superseded value.
    # Restoring A means re-asserting A's exact content, which recomputes A's
    # effective id — reserved when A was first seen — so the restore is rejected.
    lines = _read_lines()
    original = json.loads(lines[-1])
    original_id = expected_assertion_version_id(original)
    first_correction = _appended_row(original, value_delta=1)
    first_correction["assertionVersion"]["supersedes"] = original_id
    restore = copy.deepcopy(original)
    restore["assertionVersion"] = {
        "id": expected_assertion_version_id(restore),
        "supersedes": first_correction["assertionVersion"]["id"],
    }
    assert restore["assertionVersion"]["id"] == original_id

    with pytest.raises(AppendError, match="restates assertion version"):
        check_rows(
            [*lines, _json_line(first_correction), _json_line(restore)],
            len(lines),
        )


def test_provenance_correction_gets_a_distinct_av2_id_and_supersedes():
    # Review finding 6: under av1 a provenance-only correction (changed lineage,
    # re-archived bytes) collided with the original id and could be reissued.
    # av2 binds lineage, so the correction is a DISTINCT assertion that merges
    # cleanly as an explicit supersede rather than reusing the legacy id.
    lines = _read_lines()
    original = json.loads(lines[-1])
    original_id = expected_assertion_version_id(original)
    correction = copy.deepcopy(original)
    correction["source_cell_keys"] = ["different:publisher:cell"]
    correction["assertionVersion"] = {
        "id": expected_assertion_version_id(correction),
        "supersedes": original_id,
    }

    assert correction["assertionVersion"]["id"] != original_id
    check_rows([*lines, _json_line(correction)], len(lines))


@pytest.mark.xfail(
    strict=True,
    reason=(
        "out of scope for this pass: provenance fields are checked for presence "
        "and binding, not for retrievedAt/sha/git-sha string formats"
    ),
)
@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("retrievedAt", "not-a-timestamp"),
        ("ledgerRepoSha", "not-a-git-sha"),
        ("responseArchive.sha256", "not-a-sha256"),
    ],
)
def test_appended_provenance_requires_valid_integrity_metadata(
    field: str, invalid_value: str
):
    lines = _read_lines()
    row = _appended_row(
        json.loads(lines[-1]),
        source_record_id=f"verification.unique.invalid.{field}",
    )
    if field == "responseArchive.sha256":
        row["responseArchive"]["sha256"] = invalid_value
    else:
        row[field] = invalid_value
    row["assertionVersion"]["id"] = expected_assertion_version_id(row)

    with pytest.raises(AppendError):
        check_rows([*lines, _json_line(row)], len(lines))


def test_joint_manifest_and_file_rewrite_is_rejected_against_git_base(tmp_path):
    # A coordinated rewrite of a frozen row plus a rehashed manifest is rejected
    # end-to-end: the base-anchored manifest check catches the co-edited
    # manifest before the append-only line diff even runs.
    lines = _read_lines()
    original_text = "\n".join(lines) + "\n"
    original_manifest = json.loads(PREFIX_PATH.read_text(encoding="utf-8"))
    _write_checker_fixture(tmp_path, original_text, original_manifest)
    base = _init_fixture_repo(tmp_path)

    rewritten = json.loads(lines[0])
    rewritten["value"] += 1
    lines[0] = _json_line(rewritten)
    manifest = _rehash_manifest(lines)
    _write_checker_fixture(tmp_path, "\n".join(lines) + "\n", manifest)

    completed = _run_checker(tmp_path, base)

    assert completed.returncode == 1
    assert "immutable prefix manifest" in completed.stderr


def test_manifest_extension_cannot_grandfather_an_unbound_append(tmp_path):
    # Review finding 3: a PR extends the co-editable prefix manifest over its own
    # append so the unbound row counts as "prefix" and every post-cutover binding
    # is skipped. Base-anchoring the manifest and using the BASE prefix count for
    # the binding boundary both reject it.
    lines = _read_lines()
    original_text = "\n".join(lines) + "\n"
    original_manifest = json.loads(PREFIX_PATH.read_text(encoding="utf-8"))
    _write_checker_fixture(tmp_path, original_text, original_manifest)
    base = _init_fixture_repo(tmp_path)

    row = copy.deepcopy(json.loads(lines[-1]))
    row["source_record_id"] = "verification.unbound.grandfathered_append"
    row["observed_at"] = "2099-02-01"
    row["period"] = {"type": "month", "value": "2099-01"}
    for field in (
        "retrievedAt",
        "sourceVintage",
        "ledgerRepoSha",
        "responseArchive",
        "targetContentHash",
        "sourceBindingProjection",
        "assertionVersion",
    ):
        row.pop(field, None)
    lines.append(_json_line(row))
    manifest = _extend_manifest_to_all_lines(lines)
    _write_checker_fixture(tmp_path, "\n".join(lines) + "\n", manifest)

    # This counterexample also survives the separately required aggregate-fact
    # validation: the new period gives it a unique semantic fact key.
    facts = [_to_aggregate_fact(json.loads(line)) for line in lines]
    assert validate_facts(facts).valid

    completed = _run_checker(tmp_path, base)

    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "immutable prefix manifest" in completed.stderr


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        # Truthiness accepted "" as absent: hash "" with the projection key
        # removed used to pass the pairing check entirely.
        ("empty_hash_no_projection", "must carry"),
        # Both falsy-but-present: "" paired with {} skipped every check.
        ("empty_hash_empty_projection", "not a SHA-256 hex digest"),
        # A present non-dict projection crashed instead of refusing.
        ("valid_hash_string_projection", "non-empty object"),
    ],
)
def test_binding_pair_presence_and_shape_are_enforced(
    tmp_path, mutation, expected_error
):
    # Found during the package extraction review: bool(row.get(...)) treated
    # falsy-but-present binding values as absent, silently waiving the
    # contract binding for a row that claims to grade a registered target.
    lines = _read_lines()
    original_text = "\n".join(lines) + "\n"
    original_manifest = json.loads(PREFIX_PATH.read_text(encoding="utf-8"))
    _write_checker_fixture(tmp_path, original_text, original_manifest)
    base = _init_fixture_repo(tmp_path)

    row = copy.deepcopy(json.loads(lines[-1]))
    row["source_record_id"] = "verification.binding.truthiness_waiver"
    row["observed_at"] = "2099-03-01"
    row["period"] = {"type": "month", "value": "2099-02"}
    if mutation == "empty_hash_no_projection":
        row["targetContentHash"] = ""
        row.pop("sourceBindingProjection", None)
    elif mutation == "empty_hash_empty_projection":
        row["targetContentHash"] = ""
        row["sourceBindingProjection"] = {}
    else:
        # The base row may legitimately carry no binding pair, so pin a
        # format-valid hash to isolate the projection-shape refusal.
        row["targetContentHash"] = "a" * 64
        row["sourceBindingProjection"] = "bound"
    sys.path.insert(0, str(Path("scripts").resolve()))
    import check_thesis_facts_append as gate_module

    row["assertionVersion"] = {
        "id": gate_module.expected_assertion_version_id(row),
        "supersedes": None,
    }
    lines.append(_json_line(row))
    _write_checker_fixture(tmp_path, "\n".join(lines) + "\n", original_manifest)

    completed = _run_checker(tmp_path, base)

    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert expected_error in completed.stderr


@pytest.mark.xfail(
    strict=True,
    reason=(
        "by design: the full-file (no base-ref) mode trusts the co-editable "
        "manifest, so a joint manifest/file rewrite is only anchored on the PR "
        "path (--base-ref) or by an external witness"
    ),
)
def test_full_file_check_alone_rejects_joint_manifest_and_file_rewrite(tmp_path):
    lines = _read_lines()
    rewritten = json.loads(lines[0])
    rewritten["value"] += 1
    lines[0] = _json_line(rewritten)
    manifest = _rehash_manifest(lines)
    _write_checker_fixture(tmp_path, "\n".join(lines) + "\n", manifest)
    _init_fixture_repo(tmp_path)

    completed = _run_checker(tmp_path)

    assert completed.returncode == 1, completed.stdout + completed.stderr


def test_prefix_byte_check_rejects_an_inserted_blank_line(tmp_path):
    # Review finding 13: _lines dropped blank lines, so a blank line inserted
    # into the frozen JSONL normalized away and passed even with --base-ref. The
    # byte guard rejects any blank/whitespace-only line in the covered region.
    lines = _read_lines()
    manifest = json.loads(PREFIX_PATH.read_text(encoding="utf-8"))
    original_text = "\n".join(lines) + "\n"
    _write_checker_fixture(tmp_path, original_text, manifest)
    base = _init_fixture_repo(tmp_path)
    text_with_blank_line = lines[0] + "\n\n" + "\n".join(lines[1:]) + "\n"
    _write_checker_fixture(tmp_path, text_with_blank_line, manifest)

    completed = _run_checker(tmp_path, base)

    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "blank or whitespace-only" in completed.stderr


@pytest.mark.xfail(
    strict=True,
    reason=(
        "out of scope for this pass: the checker compares only base and final "
        "trees, not every intermediate commit, so a rewrite-then-restore whose "
        "final tree equals the base passes"
    ),
)
def test_base_check_rejects_rewrite_then_restore_across_commits(tmp_path):
    lines = _read_lines()
    original_text = "\n".join(lines) + "\n"
    manifest = json.loads(PREFIX_PATH.read_text(encoding="utf-8"))
    _write_checker_fixture(tmp_path, original_text, manifest)
    base = _init_fixture_repo(tmp_path)

    rewritten = json.loads(lines[0])
    rewritten["value"] += 1
    rewritten_lines = [_json_line(rewritten), *lines[1:]]
    (tmp_path / "ledger" / "official_observations.jsonl").write_text(
        "\n".join(rewritten_lines) + "\n", encoding="utf-8"
    )
    _git(tmp_path, "add", "ledger/official_observations.jsonl")
    _git(tmp_path, "commit", "-qm", "rewrite frozen row")

    (tmp_path / "ledger" / "official_observations.jsonl").write_text(
        original_text, encoding="utf-8"
    )
    _git(tmp_path, "add", "ledger/official_observations.jsonl")
    _git(tmp_path, "commit", "-qm", "restore frozen row")

    completed = _run_checker(tmp_path, base)

    assert completed.returncode == 1, completed.stdout + completed.stderr
