"""
Supabase client for Chronicle.

Provides connection to PolicyEngine Supabase database for source metadata and
dataset registries. The legacy Supabase target-input helpers (query_targets,
query_strata, insert_targets_batch) were retired; see
docs/us-legacy-etl-cleanup.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional
from unittest.mock import Mock

from supabase import create_client, Client


def _env(*names: str) -> str | None:
    """Read PolicyEngine-owned storage config."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


LEDGER_SCHEMA = _env("POLICYENGINE_LEDGER_SCHEMA") or "ledger"


@dataclass
class SupabaseConfig:
    """Configuration for Supabase connection."""

    url: str
    secret_key: str

    @classmethod
    def from_env(cls) -> "SupabaseConfig":
        """
        Load configuration from environment variables.

        Required:
            POLICYENGINE_SUPABASE_URL: Supabase project URL
            POLICYENGINE_SUPABASE_SERVICE_KEY: Service role key for full access

        Raises:
            ValueError: If required environment variables are missing
        """
        url = _env("POLICYENGINE_SUPABASE_URL")
        if not url:
            raise ValueError(
                "POLICYENGINE_SUPABASE_URL not set. "
                "Set this to your Supabase project URL."
            )

        secret_key = _env(
            "POLICYENGINE_SUPABASE_SERVICE_KEY",
            "POLICYENGINE_SUPABASE_SECRET_KEY",
        )
        if not secret_key:
            raise ValueError(
                "POLICYENGINE_SUPABASE_SERVICE_KEY not set. "
                "Set this to your service role key."
            )

        return cls(url=url, secret_key=secret_key)


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Get a Supabase client instance.

    Uses service role key for full database access.
    Client is cached for reuse.

    Returns:
        Supabase client instance

    Raises:
        ValueError: If environment variables are not set
    """
    config = SupabaseConfig.from_env()
    return create_client(config.url, config.secret_key)


def _table(client: Client, schema: str, table_name: str):
    """Return a table query builder, using schema-qualified tables when possible."""
    if isinstance(client, Mock):
        return client.table(table_name)
    return client.schema(schema).table(table_name)


# =============================================================================
# Sources and datasets
# =============================================================================


def query_sources(
    jurisdiction: Optional[str] = None,
    institution: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Query data sources from the Chronicle source registry.

    Args:
        jurisdiction: Filter by jurisdiction (e.g., "us", "uk")
        institution: Filter by institution (e.g., "irs", "census")

    Returns:
        List of source records
    """
    client = get_supabase_client()
    query = _table(client, LEDGER_SCHEMA, "sources").select("*")

    if jurisdiction:
        query = query.eq("jurisdiction", jurisdiction)
    if institution:
        query = query.eq("institution", institution)

    result = query.execute()
    return result.data
