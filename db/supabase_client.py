"""
Supabase client for Chronicle.

Chronicle has no hosted relational mirror. The hosted mirror loader and the
hosted source-registry query were retired because the schema they defaulted to
does not exist in the configured project and nothing read a hosted copy; see
docs/supabase-mirror-retirement.md. The legacy Supabase target-input helpers
(query_targets, query_strata, insert_targets_batch) were retired; see
docs/us-legacy-etl-cleanup.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from unittest.mock import Mock

from supabase import create_client, Client


def _env(*names: str) -> str | None:
    """Read PolicyEngine-owned storage config."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


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
