"""
Database schema for Chronicle's local source-artifact store.

- source_artifacts: source files with provenance and checksum metadata
- source_tables / source_columns / source_rows: their parsed contents

The legacy strata / stratum_constraints / targets tables were retired; see
docs/us-legacy-etl-cleanup.md.
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from sqlmodel import Field, Relationship, Session, SQLModel, create_engine

# Default local storage location for the source-artifact database.
DEFAULT_DB_PATH = Path(__file__).parent.parent / "macro" / "targets.db"


class Jurisdiction(str, Enum):
    """Jurisdictions we support."""

    US = "us"
    US_FEDERAL = "us-federal"
    UK = "uk"
    # States can be added as needed
    US_CA = "us-ca"
    US_NY = "us-ny"
    US_TX = "us-tx"


class DataSource(str, Enum):
    """Administrative data sources."""

    # US sources
    IRS_SOI = "irs-soi"
    CENSUS_ACS = "census-acs"
    CENSUS_PEP = "census-pep"
    CENSUS_STC = "census-stc"
    USDA_SNAP = "usda-snap"
    SSA = "ssa"
    BLS = "bls"
    CMS_MEDICAID = "cms-medicaid"
    CMS_ACA = "cms-aca"  # ACA Marketplace enrollment data
    HHS_ACF_TANF = "hhs-acf-tanf"
    CBO = "cbo"  # Congressional Budget Office projections

    # UK sources
    HMRC = "hmrc"
    DWP = "dwp"
    ONS = "ons"
    OBR = "obr"  # Office for Budget Responsibility projections


class SourceArtifact(SQLModel, table=True):
    """A source file ingested into Chronicle with provenance and checksum metadata."""

    __tablename__ = "source_artifacts"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    origin_project: str = Field(index=True)
    pipeline: str = Field(index=True)
    jurisdiction: Jurisdiction | None = Field(default=None, index=True)
    source_id: str = Field(index=True)
    source_name: str | None = None
    local_path: str | None = None
    source_url: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    sha256: str = Field(index=True)
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    tables: list["SourceTable"] = Relationship(back_populates="artifact")


class SourceTable(SQLModel, table=True):
    """One parsed table, sheet, JSON object list, or zip member."""

    __tablename__ = "source_tables"

    id: Optional[int] = Field(default=None, primary_key=True)
    artifact_id: int = Field(foreign_key="source_artifacts.id", index=True)
    name: str = Field(index=True)
    row_count: int = 0
    column_count: int = 0

    artifact: Optional[SourceArtifact] = Relationship(back_populates="tables")
    columns: list["SourceColumn"] = Relationship(back_populates="table")
    rows: list["SourceRow"] = Relationship(back_populates="table")


class SourceColumn(SQLModel, table=True):
    """Column metadata for a parsed source table."""

    __tablename__ = "source_columns"

    id: Optional[int] = Field(default=None, primary_key=True)
    table_id: int = Field(foreign_key="source_tables.id", index=True)
    position: int
    name: str

    table: Optional[SourceTable] = Relationship(back_populates="columns")


class SourceRow(SQLModel, table=True):
    """A parsed source row stored as JSON keyed by source column name."""

    __tablename__ = "source_rows"

    id: Optional[int] = Field(default=None, primary_key=True)
    table_id: int = Field(foreign_key="source_tables.id", index=True)
    row_number: int = Field(index=True)
    values_json: str

    table: Optional[SourceTable] = Relationship(back_populates="rows")


def get_engine(db_path: Path = DEFAULT_DB_PATH):
    """Get SQLAlchemy engine for the source-artifact database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db(db_path: Path = DEFAULT_DB_PATH):
    """Initialize database tables."""
    engine = get_engine(db_path)
    SQLModel.metadata.create_all(engine)
    return engine


def get_session(db_path: Path = DEFAULT_DB_PATH) -> Session:
    """Get a database session."""
    engine = get_engine(db_path)
    return Session(engine)
