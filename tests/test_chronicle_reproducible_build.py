"""Identical inputs must give byte-identical Chronicle build artifacts.

A rebuilt suite can only be checked against a published one by hash when
``ledger.db``, and the ``datapackage.json`` and ``ro-crate-metadata.json``
sidecars that hash it, are pure functions of their inputs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import cache
import hashlib
from pathlib import Path
import re
import sqlite3
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

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "packages/irs_soi/table_1_1"
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
    with sqlite3.connect(db_path) as connection:
        return connection.execute("SELECT created_at FROM ledger_builds").fetchone()[0]


def test_build_source_suite_rebuild_is_byte_identical(tmp_path, monkeypatch):
    monkeypatch.delenv(SOURCE_DATE_EPOCH_ENV, raising=False)
    # One output path for both builds: reports embed absolute output paths.
    output_dir = tmp_path / "suite"

    build_source_suite(PACKAGE_DIR, output_dir, year=2023)
    first = _file_hashes(output_dir)
    build_source_suite(PACKAGE_DIR, output_dir, year=2023, replace=True)
    second = _file_hashes(output_dir)

    assert {"ledger.db", "datapackage.json", "ro-crate-metadata.json"} <= set(first)
    assert second == first


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
    ["", " 1", "1 ", "+1", "-1", "1.5", "1e9", "0x10", "\u0663", "253402300800"],
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


@given(raw=st.text(max_size=16))
def test_only_decimal_epochs_in_range_are_accepted(raw):
    accepted = (
        re.fullmatch(r"[0-9]{1,12}", raw) is not None
        and int(raw) <= _MAX_SOURCE_DATE_EPOCH
    )
    environ = {SOURCE_DATE_EPOCH_ENV: raw}

    if accepted:
        assert build_created_at(None, environ) == build_created_at(int(raw), {})
    else:
        with pytest.raises(ValueError, match=SOURCE_DATE_EPOCH_ENV):
            build_created_at(None, environ)


@settings(max_examples=25, deadline=None)
@given(
    fact_indexes=st.sets(st.integers(min_value=0, max_value=79), max_size=8),
    extra_cell_indexes=st.sets(st.integers(min_value=0, max_value=1931), max_size=8),
    epoch=EPOCHS,
    other_epoch=EPOCHS,
)
def test_ledger_db_bytes_are_a_function_of_inputs(
    fact_indexes, extra_cell_indexes, epoch, other_epoch
):
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
