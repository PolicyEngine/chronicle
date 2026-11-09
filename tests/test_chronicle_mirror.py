"""Tests for per-table JSONL exports of Chronicle DB artifacts."""

from __future__ import annotations

import json

from chronicle.harness import main as harness_main
from chronicle.mirror import LEDGER_MIRROR_TABLES, export_chronicle_db_tables
from chronicle.database import build_chronicle_db
from chronicle.jurisdictions.us.soi import (
    build_soi_table_1_1_source_cells,
    build_soi_table_1_1_facts,
)


def test_export_chronicle_db_tables_writes_jsonl_and_manifest(tmp_path):
    db_path = tmp_path / "ledger.db"
    output_dir = tmp_path / "mirror"
    build_chronicle_db(
        build_soi_table_1_1_facts(2023),
        db_path,
        source_cells=build_soi_table_1_1_source_cells(2023),
    )

    report = export_chronicle_db_tables(db_path, output_dir)
    manifest = json.loads((output_dir / "manifest.json").read_text())

    assert report.table_count == len(LEDGER_MIRROR_TABLES)
    assert manifest["table_count"] == len(LEDGER_MIRROR_TABLES)
    assert {table["table"] for table in manifest["tables"]} == set(LEDGER_MIRROR_TABLES)
    assert (output_dir / "source_cells.jsonl").exists()
    assert (output_dir / "aggregate_facts.jsonl").exists()
    assert (output_dir / "build_artifacts.jsonl").exists()

    first_cell = json.loads(
        (output_dir / "source_cells.jsonl").read_text().splitlines()[0]
    )
    first_artifact = json.loads(
        (output_dir / "source_artifacts.jsonl").read_text().splitlines()[0]
    )
    first_fact = json.loads(
        (output_dir / "aggregate_facts.jsonl").read_text().splitlines()[0]
    )

    assert first_cell["artifact_sha256"]
    assert "raw_r2_key" in first_artifact
    assert "raw_value_json" in first_cell
    assert isinstance(first_fact["filters_json"], dict)


def test_export_chronicle_db_tables_orders_rows_deterministically(tmp_path):
    db_path = tmp_path / "ledger.db"
    first_output_dir = tmp_path / "mirror-first"
    second_output_dir = tmp_path / "mirror-second"
    build_chronicle_db(
        build_soi_table_1_1_facts(2023),
        db_path,
        source_cells=build_soi_table_1_1_source_cells(2023),
    )

    first_report = export_chronicle_db_tables(db_path, first_output_dir)
    second_report = export_chronicle_db_tables(db_path, second_output_dir)

    first_hashes = {table.table: table.sha256 for table in first_report.tables}
    second_hashes = {table.table: table.sha256 for table in second_report.tables}

    assert first_hashes == second_hashes


def test_export_db_tables_cli_emits_manifest_summary(tmp_path, capsys):
    db_path = tmp_path / "ledger.db"
    output_dir = tmp_path / "mirror"
    build_chronicle_db(
        build_soi_table_1_1_facts(2023),
        db_path,
        source_cells=build_soi_table_1_1_source_cells(2023),
    )

    exit_code = harness_main(
        [
            "export-db-tables",
            "--db",
            str(db_path),
            "--out",
            str(output_dir),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["output_dir"] == str(output_dir)
    assert payload["table_count"] == len(LEDGER_MIRROR_TABLES)
    assert payload["row_count"] > 0
    assert (output_dir / "manifest.json").exists()


def test_export_covers_every_table_the_db_build_writes(tmp_path):
    """The JSONL export is the only bulk relational path out of a DB artifact."""
    import sqlite3
    from contextlib import closing

    db_path = tmp_path / "ledger.db"
    build_chronicle_db(
        build_soi_table_1_1_facts(2023),
        db_path,
        source_cells=build_soi_table_1_1_source_cells(2023),
    )
    with closing(sqlite3.connect(db_path)) as connection:
        tables = {
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    assert tables == set(LEDGER_MIRROR_TABLES)
