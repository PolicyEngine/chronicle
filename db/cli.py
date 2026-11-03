"""CLI for Arch's local source-artifact database."""

import argparse
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from .schema import (
    DEFAULT_DB_PATH,
    SourceArtifact,
    SourceRow,
    SourceTable,
    init_db,
    get_engine,
)


def cmd_init(args):
    """Initialize the database."""
    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    init_db(db_path)
    print(f"Initialized database at {db_path}")


def cmd_load_source_files(args):
    """Load full source files into the source artifact tables."""
    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    engine = init_db(db_path)

    if args.inventory != "pe":
        raise ValueError(f"Unsupported source-file inventory: {args.inventory}")

    from .pe_source_inventory import pe_source_specs
    from .source_files import ingest_source_artifacts, prune_source_artifacts

    include_us = args.jurisdiction in {"all", "us"}
    include_uk = args.jurisdiction in {"all", "uk"}
    specs = pe_source_specs(
        pe_us_root=Path(args.pe_us_root),
        pe_uk_root=Path(args.pe_uk_root),
        include_us=include_us,
        include_uk=include_uk,
    )
    if args.limit:
        specs = specs[: args.limit]

    with Session(engine) as session:
        results = ingest_source_artifacts(session, specs)
        removed = 0 if args.limit else prune_source_artifacts(session, specs)

    print(f"Loaded {len(results)} source artifacts into {db_path}")
    if removed:
        print(f"Pruned {removed} stale source artifacts")
    print(f"Parsed tables: {sum(result.table_count for result in results):,}")
    print(f"Parsed rows: {sum(result.row_count for result in results):,}")


def cmd_source_stats(args):
    """Show source artifact statistics."""
    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    engine = get_engine(db_path)
    with Session(engine) as session:
        artifact_count = session.exec(select(func.count(SourceArtifact.id))).one()
        table_count = session.exec(select(func.count(SourceTable.id))).one()
        row_count = session.exec(select(func.count(SourceRow.id))).one()
        by_pipeline = session.exec(
            select(
                SourceArtifact.origin_project,
                SourceArtifact.pipeline,
                func.count(SourceArtifact.id),
            )
            .group_by(SourceArtifact.origin_project, SourceArtifact.pipeline)
            .order_by(SourceArtifact.origin_project, SourceArtifact.pipeline)
        ).all()
        by_source = session.exec(
            select(SourceArtifact.source_id, func.count(SourceArtifact.id))
            .group_by(SourceArtifact.source_id)
            .order_by(SourceArtifact.source_id)
        ).all()

    print(f"Database: {db_path}")
    print(f"Source artifacts: {artifact_count:,}")
    print(f"Source tables: {table_count:,}")
    print(f"Source rows: {row_count:,}")
    print("Pipelines:")
    for origin_project, pipeline, count in by_pipeline:
        print(f"  {origin_project}/{pipeline}: {count:,}")
    print("Sources:")
    for source_id, count in by_source:
        print(f"  {source_id}: {count:,}")


def main():
    parser = argparse.ArgumentParser(
        description="Manage Arch's local source-artifact database"
    )
    parser.add_argument(
        "--db",
        help=f"Database path (default: {DEFAULT_DB_PATH})"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    init_parser = subparsers.add_parser("init", help="Initialize database")
    init_parser.set_defaults(func=cmd_init)

    # load-source-files
    source_parser = subparsers.add_parser(
        "load-source-files",
        help="Load full parsed source artifacts into the database",
    )
    source_parser.add_argument(
        "inventory",
        choices=["pe"],
        help="Source-file inventory to load",
    )
    source_parser.add_argument(
        "--jurisdiction",
        choices=["all", "us", "uk"],
        default="all",
        help="Limit the source-file inventory",
    )
    source_parser.add_argument(
        "--pe-us-root",
        default="/Users/maxghenis/PolicyEngine/policyengine-us-data",
        help="Path to the policyengine-us-data checkout",
    )
    source_parser.add_argument(
        "--pe-uk-root",
        default="/Users/maxghenis/PolicyEngine/policyengine-uk-data",
        help="Path to the policyengine-uk-data checkout",
    )
    source_parser.add_argument(
        "--limit",
        type=int,
        help="Load only the first N artifacts, for smoke tests",
    )
    source_parser.set_defaults(func=cmd_load_source_files)

    # source-stats
    source_stats_parser = subparsers.add_parser(
        "source-stats", help="Show source artifact statistics"
    )
    source_stats_parser.set_defaults(func=cmd_source_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
