"""
Database layer for Arch source artifacts and Supabase registries.

Supports two backends:
- SQLite (local source-artifact store via SQLModel)
- Supabase (hosted source and microdata registries via supabase-py)

The legacy target-input tables and their ETL loaders were retired.
"""
