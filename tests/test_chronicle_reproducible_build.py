"""Identical inputs must give byte-identical Chronicle build artifacts.

A rebuilt suite can only be checked against a published one by hash when
``ledger.db``, and the ``datapackage.json`` and ``ro-crate-metadata.json``
sidecars that hash it, are pure functions of their inputs.
"""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime, timedelta
from functools import cache
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile

from hypothesis import given, settings, strategies as st
import pytest

from chronicle.bundle import build_bundle
from chronicle.database import (
    _MAX_SOURCE_DATE_EPOCH,
    SOURCE_DATE_EPOCH_ENV,
    build_created_at,
    build_chronicle_db,
)
from chronicle.jurisdictions.us.soi import (
    build_soi_table_1_1_facts,
    build_soi_table_1_1_source_cells,
)
from chronicle.sources.cells import build_source_cell_key
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "packages" / "irs_soi" / "table_1_1"
EPOCHS = st.integers(min_value=0, max_value=_MAX_SOURCE_DATE_EPOCH)


@cache
def _soi_facts():
    return tuple(build_soi_table_1_1_facts(2023))


@cache
def _soi_cells():
    return tuple(build_soi_table_1_1_source_cells(2023))


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _created_at(db_path: Path) -> str:
    with closing(sqlite3.connect(db_path)) as connection:
        return connection.execute("SELECT created_at FROM ledger_builds").fetchone()[0]


def _build_suite_in_new_process(output_dir: Path, *, hash_seed: str) -> None:
    environment = {
        key: value for key, value in os.environ.items() if key != SOURCE_DATE_EPOCH_ENV
    }
    environment["PYTHONHASHSEED"] = hash_seed
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "policyengine_chronicle.cli",
            "build-suite",
            str(PACKAGE_DIR),
            "--year",
            "2023",
            "--out",
            str(output_dir),
            "--replace",
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr


def test_build_suite_rebuild_in_a_new_process_is_byte_identical(tmp_path):
    # One output path for both builds: reports embed absolute output paths.
    # Separate processes with different hash seeds stand in for a rebuild
    # checked against a published suite.
    output_dir = tmp_path / "suite"

    _build_suite_in_new_process(output_dir, hash_seed="1")
    published = _file_hashes(output_dir)
    _build_suite_in_new_process(output_dir, hash_seed="2")
    rebuilt = _file_hashes(output_dir)

    assert {"ledger.db", "datapackage.json", "ro-crate-metadata.json"} <= set(published)
    assert rebuilt == published


def test_ledger_db_created_at_defaults_to_unix_epoch(tmp_path, monkeypatch):
    monkeypatch.delenv(SOURCE_DATE_EPOCH_ENV, raising=False)
    db_path = tmp_path / "ledger.db"

    build_chronicle_db(list(_soi_facts()), db_path, source_cells=list(_soi_cells()))

    assert _created_at(db_path) == "1970-01-01T00:00:00+00:00"


def test_ledger_db_created_at_follows_source_date_epoch(tmp_path, monkeypatch):
    monkeypatch.setenv(SOURCE_DATE_EPOCH_ENV, "1767225600")

    build_chronicle_db([], tmp_path / "env.db")
    build_chronicle_db([], tmp_path / "explicit.db", source_date_epoch=1798761600)

    assert _created_at(tmp_path / "env.db") == "2026-01-01T00:00:00+00:00"
    assert _created_at(tmp_path / "explicit.db") == "2027-01-01T00:00:00+00:00"


@pytest.mark.parametrize(
    "raw",
    ["", " 1", "1 ", "+1", "-1", "007", "1.5", "1e9", "0x10", "\u0663", "253402300800"],
)
def test_malformed_source_date_epoch_is_refused_before_touching_db(
    tmp_path, monkeypatch, raw
):
    monkeypatch.delenv(SOURCE_DATE_EPOCH_ENV, raising=False)
    db_path = tmp_path / "ledger.db"
    build_chronicle_db([], db_path)
    published = db_path.read_bytes()
    monkeypatch.setenv(SOURCE_DATE_EPOCH_ENV, raw)

    with pytest.raises(ValueError, match=SOURCE_DATE_EPOCH_ENV):
        build_chronicle_db([], db_path, replace=True)

    assert db_path.read_bytes() == published


@pytest.mark.parametrize("value", [-1, _MAX_SOURCE_DATE_EPOCH + 1, True, 1.0, "1"])
def test_malformed_explicit_source_date_epoch_is_refused(tmp_path, value):
    db_path = tmp_path / "ledger.db"

    with pytest.raises(ValueError, match="source_date_epoch"):
        build_chronicle_db([], db_path, source_date_epoch=value)

    assert not db_path.exists()


@pytest.mark.parametrize("build", ["suite", "bundle"])
def test_malformed_source_date_epoch_leaves_published_output_in_place(
    tmp_path, monkeypatch, build
):
    output_dir = tmp_path / "published"
    output_dir.mkdir()
    (output_dir / "ledger.db").write_bytes(b"published")
    monkeypatch.setenv(SOURCE_DATE_EPOCH_ENV, "yesterday")

    with pytest.raises(ValueError, match=SOURCE_DATE_EPOCH_ENV):
        if build == "suite":
            build_source_suite(PACKAGE_DIR, output_dir, year=2023, replace=True)
        else:
            build_bundle(output_dir, year=2023, sources=[PACKAGE_DIR], replace=True)

    assert _file_hashes(output_dir) == {
        "ledger.db": hashlib.sha256(b"published").hexdigest()
    }


@pytest.mark.parametrize(
    ("epoch", "expected"),
    [
        (0, "1970-01-01T00:00:00+00:00"),
        (1767225600, "2026-01-01T00:00:00+00:00"),
        (_MAX_SOURCE_DATE_EPOCH, "9999-12-31T23:59:59+00:00"),
    ],
)
def test_created_at_formats_known_epochs(epoch, expected):
    assert build_created_at(epoch, {}) == expected


@pytest.mark.skipif(
    sys.platform == "win32", reason="fromtimestamp stops near year 3000 on Windows"
)
@given(epoch=EPOCHS)
def test_created_at_matches_the_platform_timestamp_conversion(epoch):
    assert build_created_at(epoch, {}) == (
        datetime.fromtimestamp(epoch, tz=UTC).isoformat()
    )


@given(epoch=EPOCHS)
def test_created_at_round_trips_to_its_epoch_in_utc(epoch):
    created_at = build_created_at(epoch, {})
    parsed = datetime.fromisoformat(created_at)

    assert parsed.utcoffset() == timedelta(0)
    assert int(parsed.timestamp()) == epoch
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", created_at)


@given(epoch=EPOCHS)
def test_environment_and_explicit_epoch_agree(epoch):
    from_environment = build_created_at(None, {SOURCE_DATE_EPOCH_ENV: str(epoch)})

    assert from_environment == build_created_at(epoch, {})
    # An explicit value wins over the environment.
    assert build_created_at(epoch, {SOURCE_DATE_EPOCH_ENV: "0"}) == from_environment


@given(earlier=EPOCHS, later=EPOCHS)
def test_created_at_sorts_in_epoch_order(earlier, later):
    earlier, later = sorted((earlier, later))

    assert build_created_at(earlier, {}) <= build_created_at(later, {})


@given(
    raw=st.one_of(
        st.from_regex(r"[0-9]{1,13}", fullmatch=True),
        st.text(max_size=16),
    )
)
def test_only_date_format_epochs_in_range_are_accepted(raw):
    # ``date +%s`` output: ASCII digits, no leading zero unless the value is 0.
    accepted = (
        raw.isascii()
        and raw.isdigit()
        and (raw == "0" or not raw.startswith("0"))
        and int(raw) <= _MAX_SOURCE_DATE_EPOCH
    )
    environ = {SOURCE_DATE_EPOCH_ENV: raw}

    if accepted:
        assert build_created_at(None, environ) == build_created_at(int(raw), {})
    else:
        with pytest.raises(ValueError, match=SOURCE_DATE_EPOCH_ENV):
            build_created_at(None, environ)


def _indexes(items):
    return st.sets(st.integers(min_value=0, max_value=len(items) - 1), max_size=8)


@settings(max_examples=25, deadline=None)
@given(data=st.data(), epoch=EPOCHS, other_epoch=EPOCHS)
def test_ledger_db_bytes_are_a_function_of_inputs(data, epoch, other_epoch):
    fact_indexes = data.draw(_indexes(_soi_facts()), label="fact_indexes")
    extra_cell_indexes = data.draw(_indexes(_soi_cells()), label="extra_cell_indexes")
    facts = [_soi_facts()[index] for index in sorted(fact_indexes)]
    lineage = {key for fact in facts for key in fact.source_cell_keys}
    cells = [
        cell
        for index, cell in enumerate(_soi_cells())
        if index in extra_cell_indexes or build_source_cell_key(cell) in lineage
    ]

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        reports = [
            build_chronicle_db(
                facts,
                root / name,
                source_cells=cells,
                source_date_epoch=build_epoch,
            )
            for name, build_epoch in (
                ("first/ledger.db", epoch),
                ("second/ledger.db", epoch),
                ("other-epoch/ledger.db", other_epoch),
            )
        ]
        first, second, other = (
            (root / name).read_bytes()
            for name in ("first/ledger.db", "second/ledger.db", "other-epoch/ledger.db")
        )

    # Same inputs at different paths: same bytes.
    assert first == second
    # The build time is metadata, never identity.
    assert reports[0].build_id == reports[1].build_id == reports[2].build_id
    assert (first == other) == (epoch == other_epoch)
