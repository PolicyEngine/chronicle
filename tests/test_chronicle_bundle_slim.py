"""Slim bundles: ``build_bundle(keep_suite_intermediates=False)`` and ``--slim``.

A slim bundle deletes each source suite's ``SUITE_INTERMEDIATE_FILES`` once the
suite finishes. Invariants:

- with the build clock pinned, every file a slim bundle keeps is
  byte-identical to a full build's, and the slim bundle holds exactly the full
  build's files minus the intermediates plus ``reports/pruned_intermediates.json``
  (``ledger.db`` stores its build time, which the suite sidecars hash);
- pruning deletes only the intermediate files that exist as regular files, and
  is idempotent;
- the default keeps every intermediate and writes no pruning report.
"""

from __future__ import annotations

import gc
import hashlib
import itertools
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from chronicle.bundle import (
    PRUNED_INTERMEDIATES_REPORT,
    SUITE_INTERMEDIATE_FILES,
    _prune_suite_intermediates,
    build_bundle,
)
from chronicle.harness import build_bundle_dir
from chronicle.harness import main as harness_main

# Three explicit packages that build in seconds.
SMALL_SOURCES = (
    "soi-table-1-1",
    "cbo-revenue-projections-income-by-source-2026-02",
    "ssa-ssi-table-7b1-2024",
)
PRUNED_REPORT_PATH = f"reports/{PRUNED_INTERMEDIATES_REPORT}"
# Suite files a slim bundle keeps, a sample of each kind build_source_suite writes.
KEPT_SUITE_FILES = (
    "consumer_facts.jsonl",
    "source_regions.jsonl",
    "datapackage.json",
    "ro-crate-metadata.json",
    "reports/build_summary.json",
    "reports/database.json",
)


class _FrozenDatetime(datetime):
    """``ledger.db`` stores its build time; pin it so two builds match byte for byte."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 1, tzinfo=tz)


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_slim_bundle_matches_full_bundle_byte_for_byte(tmp_path, monkeypatch):
    monkeypatch.setattr("chronicle.database.datetime", _FrozenDatetime)
    # One output path for both builds: reports embed absolute output paths.
    output_dir = tmp_path / "bundle"

    full = build_bundle(output_dir, year=2023, sources=SMALL_SOURCES)
    full_files = _file_hashes(output_dir)
    full_sizes = {name: (output_dir / name).stat().st_size for name in full_files}
    slim = build_bundle(
        output_dir,
        year=2023,
        sources=SMALL_SOURCES,
        replace=True,
        keep_suite_intermediates=False,
    )
    slim_files = _file_hashes(output_dir)

    intermediates = {
        f"sources/{source}/{name}"
        for source in SMALL_SOURCES
        for name in SUITE_INTERMEDIATE_FILES
    }
    kept = full_files.keys() - intermediates
    assert full.valid
    assert slim.valid
    assert intermediates <= full_files.keys()
    assert PRUNED_REPORT_PATH not in full_files
    assert slim_files.keys() == kept | {PRUNED_REPORT_PATH}
    for name in (
        "consumer_facts.jsonl",
        "coverage.json",
        "source_packages.json",
        "reports/build_bundle.json",
    ):
        assert slim_files[name] == full_files[name], name
    assert {name: slim_files[name] for name in kept} == {
        name: full_files[name] for name in kept
    }
    assert slim.to_dict() == full.to_dict()

    pruned = json.loads((output_dir / PRUNED_REPORT_PATH).read_text())
    assert pruned == {
        "pruned_file_names": list(SUITE_INTERMEDIATE_FILES),
        "suite_count": len(SMALL_SOURCES),
        "file_count": len(intermediates),
        "bytes": sum(full_sizes[name] for name in intermediates),
        "suites": [
            {
                "source": source,
                "output_dir": str(output_dir / "sources" / source),
                "files": [
                    {"name": name, "bytes": full_sizes[f"sources/{source}/{name}"]}
                    for name in SUITE_INTERMEDIATE_FILES
                ],
            }
            for source in SMALL_SOURCES
        ],
    }


def test_slim_bundle_prunes_a_suite_that_fails_partway(tmp_path, monkeypatch):
    def failing_suite(source, output_dir, **kwargs):
        suite_dir = Path(output_dir)
        (suite_dir / "reports").mkdir(parents=True)
        for name in SUITE_INTERMEDIATE_FILES:
            (suite_dir / name).write_text("partial")
        (suite_dir / "reports" / "source_rows.json").write_text("{}")
        raise RuntimeError("parser failed")

    monkeypatch.setattr("chronicle.bundle.build_source_suite", failing_suite)
    output_dir = tmp_path / "bundle"

    report = build_bundle(
        output_dir,
        year=2023,
        sources=["soi-table-1-1"],
        keep_suite_intermediates=False,
    )

    suite_dir = output_dir / "sources" / "soi-table-1-1"
    assert [issue.code for issue in report.errors] == ["source_suite_build_failed"]
    assert sorted(_file_hashes(suite_dir)) == ["reports/source_rows.json"]
    pruned = json.loads((output_dir / PRUNED_REPORT_PATH).read_text())
    assert pruned["suites"] == [
        {
            "source": "soi-table-1-1",
            "output_dir": str(suite_dir),
            "files": [
                {"name": name, "bytes": len("partial")}
                for name in SUITE_INTERMEDIATE_FILES
            ],
        }
    ]


def test_slim_bundle_records_no_suite_that_wrote_nothing(tmp_path, monkeypatch):
    def empty_failure(source, output_dir, **kwargs):
        raise RuntimeError("no artifact")

    monkeypatch.setattr("chronicle.bundle.build_source_suite", empty_failure)
    output_dir = tmp_path / "bundle"

    build_bundle(
        output_dir,
        year=2023,
        sources=["soi-table-1-1"],
        keep_suite_intermediates=False,
    )

    pruned = json.loads((output_dir / PRUNED_REPORT_PATH).read_text())
    assert pruned["suites"] == []
    assert (pruned["suite_count"], pruned["file_count"], pruned["bytes"]) == (0, 0, 0)


def _open_sqlite_paths_under(root: Path) -> list[Path]:
    """Database files under ``root`` that some live connection still holds open."""
    held = []
    for obj in gc.get_objects():
        if not isinstance(obj, sqlite3.Connection):
            continue
        try:
            databases = obj.execute("PRAGMA database_list").fetchall()
        except sqlite3.ProgrammingError:
            continue  # closed, or owned by another thread
        for _, _, filename in databases:
            if filename and Path(filename).resolve().is_relative_to(root.resolve()):
                held.append(Path(filename))
    return held


def test_slim_bundle_leaves_no_pruned_ledger_db_open(tmp_path):
    """A deleted ledger.db frees its storage only once its connection closes.

    With the collector off, a connection left in a reference cycle stays open
    and keeps the unlinked file's blocks allocated for the whole bundle build.
    """
    output_dir = tmp_path / "bundle"
    probe_path = tmp_path / "probe.db"
    collector_was_enabled = gc.isenabled()
    gc.disable()
    try:
        build_bundle(
            output_dir,
            year=2023,
            sources=SMALL_SOURCES,
            keep_suite_intermediates=False,
        )
        held = _open_sqlite_paths_under(output_dir)
        # Positive control: the scan must see a connection left open, and stop
        # seeing it once it is closed, or an empty result proves nothing.
        probe = sqlite3.connect(probe_path)
        probe_open = _open_sqlite_paths_under(tmp_path)
        probe.close()
        probe_closed = _open_sqlite_paths_under(tmp_path)
    finally:
        if collector_was_enabled:
            gc.enable()

    assert held == []
    assert [path.resolve() for path in probe_open] == [probe_path.resolve()]
    assert probe_closed == []


def test_prune_suite_intermediates_exhaustively(tmp_path):
    """Each intermediate absent, a file or a directory, beside kept files or none.

    Kept files are never candidates for deletion, so they vary together.
    """
    intermediate_states = ("absent", "file", "directory")
    combinations = itertools.product(
        itertools.product(intermediate_states, repeat=len(SUITE_INTERMEDIATE_FILES)),
        (
            ("absent",) * len(KEPT_SUITE_FILES),
            ("file",) * len(KEPT_SUITE_FILES),
        ),
    )
    for case, (intermediate_case, kept_case) in enumerate(combinations):
        suite_dir = tmp_path / str(case)
        suite_dir.mkdir()
        expected: list[dict[str, object]] = []
        for index, (name, state) in enumerate(
            zip(SUITE_INTERMEDIATE_FILES, intermediate_case, strict=True)
        ):
            if state == "file":
                (suite_dir / name).write_bytes(b"x" * index)
                expected.append({"name": name, "bytes": index})
            elif state == "directory":
                (suite_dir / name).mkdir()
                (suite_dir / name / "inner").write_text(name)
        for name, state in zip(KEPT_SUITE_FILES, kept_case, strict=True):
            if state == "file":
                (suite_dir / name).parent.mkdir(parents=True, exist_ok=True)
                (suite_dir / name).write_text(f"{case}:{name}")
        before = _file_hashes(suite_dir)
        removed = {item["name"] for item in expected}

        assert _prune_suite_intermediates(suite_dir) == expected, case
        after = _file_hashes(suite_dir)
        assert after == {
            name: digest for name, digest in before.items() if name not in removed
        }, case
        assert _prune_suite_intermediates(suite_dir) == [], case
        assert _file_hashes(suite_dir) == after, case


def test_prune_suite_intermediates_ignores_a_missing_suite_dir(tmp_path):
    assert _prune_suite_intermediates(tmp_path / "never-built") == []


def test_build_bundle_dir_passes_keep_suite_intermediates(tmp_path, monkeypatch):
    captured = []

    def fake_build_bundle(output_dir, **kwargs):
        captured.append(kwargs["keep_suite_intermediates"])

    monkeypatch.setattr("chronicle.harness.build_bundle", fake_build_bundle)

    build_bundle_dir(tmp_path / "default", year=2023)
    build_bundle_dir(tmp_path / "slim", year=2023, keep_suite_intermediates=False)

    assert captured == [True, False]


def test_build_bundle_cli_slim_deletes_suite_intermediates(tmp_path, capsys):
    full_dir = tmp_path / "full"
    slim_dir = tmp_path / "slim"
    common = ["build-bundle", "--year", "2023", "--source", "soi-table-1-1"]

    full_status = harness_main([*common, "--out", str(full_dir)])
    full_payload = json.loads(capsys.readouterr().out)
    slim_status = harness_main([*common, "--out", str(slim_dir), "--slim"])
    slim_payload = json.loads(capsys.readouterr().out)

    assert (full_status, slim_status) == (0, 0)
    assert slim_payload["valid"]
    assert slim_payload["counts"] == full_payload["counts"]
    full_suite = full_dir / "sources" / "soi-table-1-1"
    slim_suite = slim_dir / "sources" / "soi-table-1-1"
    for name in SUITE_INTERMEDIATE_FILES:
        assert (full_suite / name).is_file()
        assert not (slim_suite / name).exists()
    assert (slim_suite / "consumer_facts.jsonl").read_bytes() == (
        full_suite / "consumer_facts.jsonl"
    ).read_bytes()
    assert not (full_dir / PRUNED_REPORT_PATH).exists()
    pruned = json.loads((slim_dir / PRUNED_REPORT_PATH).read_text())
    assert (pruned["suite_count"], pruned["file_count"]) == (
        1,
        len(SUITE_INTERMEDIATE_FILES),
    )
