"""Tests for the relational Arch database artifact."""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace
import sqlite3

import pytest

from arch.artifacts import infer_build_id
from arch.core import build_aggregate_constraints
from arch.jurisdictions.us.soi import AXIOM_IRC_AGI_CONCEPT
from arch.database import build_arch_db
from arch.harness import build_arch_db_file
from arch.jurisdictions.us.soi import (
    build_soi_table_1_1_source_cells,
    build_soi_table_1_1_facts,
)
from arch.mirror import export_arch_db_tables


def test_build_aggregate_constraints_lifts_agi_filters():
    fact = next(
        fact
        for fact in build_soi_table_1_1_facts(2023)
        if fact.source_record_id
        == "irs_soi.ty2023.table_1_1.100k_to_200k.return_count"
    )

    constraints = build_aggregate_constraints(fact)

    assert [(item.variable, item.operator, item.value, item.unit) for item in constraints] == [
        (AXIOM_IRC_AGI_CONCEPT, ">=", 100_000, "usd"),
        (AXIOM_IRC_AGI_CONCEPT, "<", 200_000, "usd"),
    ]


def test_build_arch_db_writes_aggregate_fact_constraints_and_lineage(tmp_path):
    db_path = tmp_path / "arch-fixture.db"
    facts = build_soi_table_1_1_facts(2023)
    cells = build_soi_table_1_1_source_cells(2023)

    report = build_arch_db(facts, db_path, source_cells=cells)

    assert report.facts_count == 80
    assert report.source_records_count == 80
    assert report.source_cells_count == 1932
    assert report.source_artifacts_count == 1

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        artifact = connection.execute(
            """
            SELECT raw_r2_bucket, raw_r2_key, raw_r2_uri
            FROM source_artifacts
            WHERE artifact_sha256 = ?
            """,
            (cells[0].artifact.sha256,),
        ).fetchone()
        build_artifact_count = connection.execute(
            "SELECT COUNT(*) FROM build_artifacts"
        ).fetchone()[0]
        all_returns = connection.execute(
            """
            SELECT *
            FROM aggregate_facts
            WHERE source_record_id = ?
            """,
            ("irs_soi.ty2023.table_1_1.all.return_count",),
        ).fetchone()

        assert all_returns["measure_concept"] == "irs_soi.individual_income_tax_returns"
        assert all_returns["aggregation_method"] == "count"
        assert all_returns["entity_name"] == "tax_unit"
        assert all_returns["value_numeric"] == 160_602_107
        assert all_returns["domain"] == "all_individual_income_tax_returns"
        assert artifact["raw_r2_bucket"] == "arch-raw"
        assert artifact["raw_r2_key"].startswith(
            "raw/irs_soi/soi-table-1-1/2023/"
        )
        assert artifact["raw_r2_uri"].startswith("r2://arch-raw/")
        assert build_artifact_count == 0

        bracket = connection.execute(
            """
            SELECT fact_key
            FROM aggregate_facts
            WHERE source_record_id = ?
            """,
            ("irs_soi.ty2023.table_1_1.100k_to_200k.return_count",),
        ).fetchone()
        constraints = connection.execute(
            """
            SELECT variable, operator, value_numeric, unit
            FROM aggregate_constraints
            WHERE fact_key = ?
            ORDER BY ordinal
            """,
            (bracket["fact_key"],),
        ).fetchall()

        assert [tuple(row) for row in constraints] == [
            (AXIOM_IRC_AGI_CONCEPT, ">=", 100_000, "usd"),
            (AXIOM_IRC_AGI_CONCEPT, "<", 200_000, "usd"),
        ]

        agi_fact = connection.execute(
            """
            SELECT
                measure_concept,
                measure_source_concept,
                measure_concept_relation,
                layout_record_set_id,
                layout_groupby_value_id,
                layout_measure_id
            FROM aggregate_facts
            WHERE source_record_id = ?
            """,
            ("irs_soi.ty2023.table_1_1.all.adjusted_gross_income",),
        ).fetchone()
        alignment = connection.execute(
            """
            SELECT source_concept, canonical_concept, relation, authority
            FROM concept_alignments
            WHERE source_concept = ?
            """,
            ("irs_soi.adjusted_gross_income",),
        ).fetchone()

        assert tuple(agi_fact) == (
            AXIOM_IRC_AGI_CONCEPT,
            "irs_soi.adjusted_gross_income",
            "exact",
            "irs_soi.ty2023.table_1_1",
            "all",
            "adjusted_gross_income",
        )
        assert tuple(alignment) == (
            "irs_soi.adjusted_gross_income",
            AXIOM_IRC_AGI_CONCEPT,
            "exact",
            "arch-us",
        )

        lineage = connection.execute(
            """
            SELECT source_cells.address, source_cells.raw_value_numeric
            FROM aggregate_facts
            JOIN fact_source_cells
              ON fact_source_cells.fact_key = aggregate_facts.fact_key
            JOIN source_cells
              ON source_cells.source_cell_key = fact_source_cells.source_cell_key
            WHERE aggregate_facts.source_record_id = ?
            """,
            ("irs_soi.ty2023.table_1_1.all.return_count",),
        ).fetchone()

        assert tuple(lineage) == ("B10", 160_602_107)


def test_build_arch_db_build_id_changes_when_fact_payload_changes(tmp_path):
    cells = build_soi_table_1_1_source_cells(2023)
    facts = build_soi_table_1_1_facts(2023)
    changed_facts = [replace(facts[0], value=999), *facts[1:]]

    original = build_arch_db(
        facts,
        tmp_path / "original.db",
        source_cells=cells,
    )
    changed = build_arch_db(
        changed_facts,
        tmp_path / "changed.db",
        source_cells=cells,
    )

    assert original.build_id != changed.build_id


def test_build_arch_db_rejects_unresolved_source_cell_lineage(tmp_path):
    fact = replace(
        build_soi_table_1_1_facts(2023)[0],
        source_cell_keys=("arch.source_cell.v1:missing",),
    )

    with pytest.raises(sqlite3.IntegrityError):
        build_arch_db([fact], tmp_path / "bad-lineage.db")


def test_build_arch_db_file_uses_fixture_facts_and_cells(tmp_path):
    db_path = tmp_path / "arch-fixture.db"

    report = build_arch_db_file(db_path)

    assert report.facts_count == 80
    assert report.source_cells_count == 1932
    with sqlite3.connect(db_path) as connection:
        facts_count = connection.execute(
            "SELECT COUNT(*) FROM aggregate_facts"
        ).fetchone()[0]
        cells_count = connection.execute("SELECT COUNT(*) FROM source_cells").fetchone()[0]

    assert facts_count == 80
    assert cells_count == 1932


def _record_sqlite_connections(monkeypatch):
    opened = []
    connect = sqlite3.connect

    def record(*args, **kwargs):
        connection = connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", record)
    return opened


def _assert_closed(connections):
    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            connection.execute("SELECT 1")


def test_build_arch_db_closes_its_connection(tmp_path, monkeypatch):
    """The DB file must be released on return so callers can delete it."""
    opened = _record_sqlite_connections(monkeypatch)
    db_path = tmp_path / "arch.db"

    build_arch_db(
        build_soi_table_1_1_facts(2023),
        db_path,
        source_cells=build_soi_table_1_1_source_cells(2023),
    )

    _assert_closed(opened)
    with closing(sqlite3.connect(db_path)) as connection:
        builds = connection.execute("SELECT COUNT(*) FROM arch_builds").fetchone()
    assert builds == (1,)


def test_arch_db_readers_close_their_connections(tmp_path, monkeypatch):
    suite = tmp_path / "suite"
    report = build_arch_db(
        build_soi_table_1_1_facts(2023),
        suite / "arch.db",
        source_cells=build_soi_table_1_1_source_cells(2023),
    )
    opened = _record_sqlite_connections(monkeypatch)

    assert infer_build_id(suite) == report.build_id
    export_arch_db_tables(suite / "arch.db", tmp_path / "mirror")

    assert len(opened) == 2
    _assert_closed(opened)
