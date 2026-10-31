"""
Tests for Supabase client.

TDD: Write tests first, then implement.
"""

import os
import pytest
from unittest.mock import patch, MagicMock


class TestSupabaseClient:
    """Tests for Supabase client initialization and connection."""

    def test_get_client_returns_client_with_env_vars(self):
        """Client is created when environment variables are set."""
        from db.supabase_client import get_supabase_client

        # Skip if no real credentials
        if not os.environ.get("POLICYENGINE_SUPABASE_URL"):
            pytest.skip("POLICYENGINE_SUPABASE_URL not set")
        if not (
            os.environ.get("POLICYENGINE_SUPABASE_SERVICE_KEY")
            or os.environ.get("POLICYENGINE_SUPABASE_SECRET_KEY")
        ):
            pytest.skip("POLICYENGINE_SUPABASE_SERVICE_KEY not set")

        # Clear the lru_cache to ensure fresh client
        get_supabase_client.cache_clear()
        client = get_supabase_client()
        assert client is not None

    def test_config_from_env(self):
        """SupabaseConfig loads from environment variables."""
        from db.supabase_client import SupabaseConfig

        with patch.dict(
            os.environ,
            {
                "POLICYENGINE_SUPABASE_URL": "https://test.supabase.co",
                "POLICYENGINE_SUPABASE_SERVICE_KEY": "test-secret-key",
            },
        ):
            config = SupabaseConfig.from_env()
            assert config.url == "https://test.supabase.co"
            assert config.secret_key == "test-secret-key"

    def test_config_uses_policyengine_secret_key_as_fallback(self):
        """PolicyEngine SECRET_KEY keeps existing deployments working."""
        from db.supabase_client import SupabaseConfig

        with patch.dict(
            os.environ,
            {
                "POLICYENGINE_SUPABASE_URL": "https://test.supabase.co",
                "POLICYENGINE_SUPABASE_SECRET_KEY": "test-secret-key",
            },
            clear=True,
        ):
            config = SupabaseConfig.from_env()
            assert config.url == "https://test.supabase.co"
            assert config.secret_key == "test-secret-key"

    def test_config_missing_url_raises(self):
        """Missing URL raises ValueError."""
        from db.supabase_client import SupabaseConfig

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="POLICYENGINE_SUPABASE_URL"):
                SupabaseConfig.from_env()

    def test_config_missing_key_raises(self):
        """Missing secret key raises ValueError."""
        from db.supabase_client import SupabaseConfig

        with patch.dict(
            os.environ,
            {
                "POLICYENGINE_SUPABASE_URL": "https://test.supabase.co",
            },
            clear=True,
        ):
            with pytest.raises(ValueError, match="POLICYENGINE_SUPABASE_SERVICE_KEY"):
                SupabaseConfig.from_env()


class TestSupabaseQueries:
    """Tests for querying data from Supabase."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Supabase client."""
        client = MagicMock()
        return client

    def test_query_targets_filters_by_jurisdiction(self, mock_client):
        """Querying targets filters by jurisdiction."""
        from db.supabase_client import query_targets

        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "456", "variable": "tax_unit_count", "value": 1000000}
        ]

        with patch("db.supabase_client.get_supabase_client", return_value=mock_client):
            targets = query_targets(jurisdiction="us")
            mock_client.table.assert_called()
            assert isinstance(targets, list)

    def test_query_strata_with_constraints(self, mock_client):
        """Querying strata includes constraints."""
        from db.supabase_client import query_strata

        mock_client.table.return_value.select.return_value.execute.return_value.data = [
            {
                "id": "789",
                "name": "California filers",
                "jurisdiction": "us",
                "constraints": [
                    {"variable": "state_fips", "operator": "==", "value": "06"}
                ],
            }
        ]

        with patch("db.supabase_client.get_supabase_client", return_value=mock_client):
            strata = query_strata()
            assert isinstance(strata, list)
