"""Tests for the publication shell functions in .github/workflows/ots-anchor.yml."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ots-anchor.yml"
PUBLISH_STEP = "Anchor, verify, and publish proof-only changes"
COMMIT_SUBJECT = "Update OpenTimestamps anchors for release manifests"
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def publish_script() -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["anchor"]["steps"]
    (step,) = [step for step in steps if step.get("name") == PUBLISH_STEP]
    return step["run"]


def shell_function(script: str, name: str) -> str:
    match = re.search(
        rf"^{re.escape(name)}\(\) \{{\n.*?^\}}$", script, re.DOTALL | re.MULTILINE
    )
    assert match is not None, f"{name}() not found in the publish step"
    return match.group(0)


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def bot_checkout(tmp_path: Path) -> Path:
    """A repository shaped like the job's main checkout after anchoring."""

    repo = tmp_path / "main"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", BOT_NAME)
    git(repo, "config", "user.email", BOT_EMAIL)
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    (repo / "ots").mkdir()
    (repo / "ots" / "0000.json.ots").write_bytes(b"pending")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "baseline")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def commit_proofs(repo: Path) -> None:
    script = (
        "set -euo pipefail\n"
        + shell_function(publish_script(), "commit_proofs")
        + "\ncommit_proofs\n"
    )
    subprocess.run(
        ["bash", "-c", script],
        cwd=repo,
        env={**os.environ, "MAIN_BRANCH": "main"},
        check=True,
        capture_output=True,
        text=True,
    )


def test_publish_script_carries_no_coauthor_trailer() -> None:
    assert "Co-Authored-By" not in publish_script()


def test_commit_proofs_writes_a_plain_bot_commit(tmp_path: Path) -> None:
    repo = bot_checkout(tmp_path)
    (repo / "ots" / "0000.json.ots").write_bytes(b"upgraded")

    commit_proofs(repo)
    message = git(repo, "log", "-1", "--format=%B")
    assert message.strip() == COMMIT_SUBJECT
    assert "Co-Authored-By" not in message
    assert git(repo, "log", "-1", "--format=%an <%ae>").strip() == (
        f"{BOT_NAME} <{BOT_EMAIL}>"
    )

    # A retry amends the proof-only commit instead of stacking a second one.
    (repo / "ots" / "0001.json.ots").write_bytes(b"new")
    commit_proofs(repo)
    assert git(repo, "rev-list", "--count", "origin/main..HEAD").strip() == "1"
    assert git(repo, "log", "-1", "--format=%B").strip() == COMMIT_SUBJECT
    assert git(repo, "diff", "--name-only", "origin/main...HEAD").split() == [
        "ots/0000.json.ots",
        "ots/0001.json.ots",
    ]
