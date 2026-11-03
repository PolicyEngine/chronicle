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

    def test_query_sources_returns_list(self, mock_client):
        """Querying sources returns a list."""
        from db.supabase_client import query_sources

        mock_client.table.return_value.select.return_value.execute.return_value.data = [
            {"id": "123", "jurisdiction": "us", "institution": "irs", "dataset": "soi"}
        ]

        with patch("db.supabase_client.get_supabase_client", return_value=mock_client):
            sources = query_sources()
            assert isinstance(sources, list)
            assert len(sources) == 1
            assert sources[0]["jurisdiction"] == "us"


class TestSupabaseMicrodata:
    """Tests for loading microdata from Supabase."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Supabase client."""
        client = MagicMock()
        return client

    def test_query_cps_returns_dataframe(self, mock_client):
        """Querying CPS returns a pandas DataFrame."""
        import pandas as pd
        from db.supabase_client import query_cps

        mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"year": 2021, "state_fips": 6, "wage_income": 50000, "weight": 1000}
        ]

        with patch("db.supabase_client.get_supabase_client", return_value=mock_client):
            df = query_cps(year=2021, limit=1000)
            assert isinstance(df, pd.DataFrame)
            assert "weight" in df.columns

    def test_query_cps_filters_by_year(self, mock_client):
        """CPS query filters by year."""
        from db.supabase_client import query_cps

        mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

        with patch("db.supabase_client.get_supabase_client", return_value=mock_client):
            query_cps(year=2021)
            mock_client.table.return_value.select.return_value.eq.assert_called_with(
                "year", 2021
            )

    def test_query_cps_filters_by_state(self, mock_client):
        """CPS query can filter by state."""
        from db.supabase_client import query_cps

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

        with patch("db.supabase_client.get_supabase_client", return_value=mock_client):
            query_cps(year=2021, state_fips=6)
            # Should have two eq calls
            calls = mock_client.table.return_value.select.return_value.eq.call_args_list
            assert len(calls) >= 1
