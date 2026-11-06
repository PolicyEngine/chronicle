"""Export a deterministic Chronicle DB artifact to per-table JSONL files."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_MIRROR_TABLES = (
    "ledger_builds",
    "build_artifacts",
    "source_artifacts",
    "source_columns",
    "source_rows",
    "source_row_values",
    "source_cells",
    "source_records",
    "concept_alignments",
    "aggregate_facts",
    "aggregate_constraints",
    "fact_source_cells",
    "fact_source_rows",
)
LEDGER_MIRROR_PRIMARY_KEYS = {
    "ledger_builds": "build_id",
    "build_artifacts": "build_artifact_key",
    "source_artifacts": "artifact_sha256",
    "source_columns": "source_column_key",
    "source_rows": "source_row_key",
    "source_row_values": "source_row_value_key",
    "source_cells": "source_cell_key",
    "source_records": "source_record_id",
    "concept_alignments": (
        "source_concept,canonical_concept,relation,legal_vintage,"
        "period_type,period_value"
    ),
    "aggregate_facts": "fact_key",
    "aggregate_constraints": "fact_key,ordinal",
    "fact_source_cells": "fact_key,source_cell_key",
    "fact_source_rows": "fact_key,source_row_key",
}
JSON_COLUMNS = {
    "raw_value_json",
    "values_json",
    "value_json",
    "filters_json",
}


@dataclass(frozen=True)
class ChronicleTableExport:
    """One exported relational table."""

    table: str
    path: str
    row_count: int
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable export record."""
        return asdict(self)


@dataclass(frozen=True)
class ChronicleMirrorExportReport:
    """Report for a per-table JSONL export of a local Chronicle DB artifact."""

    db_path: str
    output_dir: str
    exported_at: str
    build_ids: tuple[str, ...]
    tables: tuple[ChronicleTableExport, ...]

    @property
    def table_count(self) -> int:
        """Number of exported tables."""
        return len(self.tables)

    @property
    def row_count(self) -> int:
        """Total exported row count."""
        return sum(table.row_count for table in self.tables)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable export report."""
        return {
            "db_path": self.db_path,
            "output_dir": self.output_dir,
            "exported_at": self.exported_at,
            "build_ids": list(self.build_ids),
            "table_count": self.table_count,
            "row_count": self.row_count,
            "tables": [table.to_dict() for table in self.tables],
        }


def export_chronicle_db_tables(
    db_path: str | Path,
    output_dir: str | Path,
    *,
    replace: bool = False,
) -> ChronicleMirrorExportReport:
    """Export Chronicle SQLite tables to deterministic per-table JSONL files."""
    db = Path(db_path)
    if not db.exists():
        raise FileNotFoundError(f"Chronicle DB not found: {db}")

    output = Path(output_dir)
    _prepare_output_dir(output, replace=replace)

    exports: list[ChronicleTableExport] = []
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.row_factory = sqlite3.Row
        build_ids = tuple(
            row["build_id"]
            for row in connection.execute(
                "SELECT build_id FROM ledger_builds ORDER BY build_id"
            ).fetchall()
        )
        for table in LEDGER_MIRROR_TABLES:
            exports.append(_export_table(connection, output, table))

    report = ChronicleMirrorExportReport(
        db_path=str(db),
        output_dir=str(output),
        exported_at=datetime.now(timezone.utc).isoformat(),
        build_ids=build_ids,
        tables=tuple(exports),
    )
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report


def _export_table(
    connection: sqlite3.Connection,
    output_dir: Path,
    table: str,
) -> ChronicleTableExport:
    path = output_dir / f"{table}.jsonl"
    row_count = 0
    with path.open("w", encoding="utf-8") as file:
        rows = connection.execute(
            f"SELECT * FROM {table} ORDER BY {LEDGER_MIRROR_PRIMARY_KEYS[table]}"
        ).fetchall()
        for row in rows:
            payload = {key: _export_value(key, row[key]) for key in row.keys()}
            file.write(json.dumps(payload, sort_keys=True))
            file.write("\n")
            row_count += 1

    return ChronicleTableExport(
        table=table,
        path=str(path),
        row_count=row_count,
        size_bytes=path.stat().st_size,
        sha256=_sha256(path),
    )


def _export_value(column: str, value: Any) -> Any:
    if column in JSON_COLUMNS and isinstance(value, str):
        return json.loads(value)
    return value


def _prepare_output_dir(output_path: Path, *, replace: bool) -> None:
    if output_path.exists() and any(output_path.iterdir()):
        if not replace:
            raise FileExistsError(
                f"Mirror export output directory is not empty: {output_path}"
            )
        if output_path.resolve() in {Path("/").resolve(), Path.home().resolve()}:
            raise ValueError(
                f"Refusing to replace unsafe output directory: {output_path}"
            )
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True, exist_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
