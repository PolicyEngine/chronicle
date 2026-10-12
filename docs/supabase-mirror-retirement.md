# Hosted Supabase mirror retirement

Chronicle used to document a hosted Supabase/Postgres copy of each accepted
build, loaded with `chronicle load-supabase-mirror` and queried with
`query_sources`. Neither ever worked against the configured project, and
nothing read the hosted copy, so both were retired on 2026-10-12.

## What was retired

| Surface | Where it lived | What it did |
|---------|----------------|-------------|
| `chronicle load-supabase-mirror` | `chronicle/harness.py`, `chronicle/cli.py` | Upserted `export-db-tables` JSONL into a Supabase schema (default `ledger`) through the Data API |
| `load_supabase_mirror`, `SupabaseMirrorLoadReport`, `SupabaseTableLoad` | `chronicle/mirror.py` | The loader behind the command |
| `load_supabase_mirror_files` | `chronicle/harness.py` | Harness wrapper for the loader |
| `query_sources` | `db/supabase_client.py`, re-exported by `chronicle.sources`, `chronicle.sources.client` and `policyengine_chronicle.sources` | Read a `sources` table from the same schema |
| `LEDGER_SCHEMA` / `POLICYENGINE_LEDGER_SCHEMA` | `db/supabase_client.py` | Named that schema |

## What stays

- `chronicle export-db-tables` still writes every table of a `ledger.db`
  artifact to deterministic JSONL plus a checksummed `manifest.json`. Use it to
  load Chronicle tables into another store, to diff builds, or to archive them.
- `ledger.db` itself is the relational artifact. `build-suite` writes it and
  `publish-derived` uploads it to `ledger-derived` per build.
- `publish-derived --build-artifacts-out` still writes `build_artifacts` rows
  for the objects it published.
- `SupabaseConfig` and `get_supabase_client` stay in `db/supabase_client.py`
  only because the legacy target-input helpers (`query_targets`, `query_strata`,
  `insert_targets_batch`) still call them. Those helpers are being retired
  separately; the client and the `supabase` dependency go with them.

## Why

Checked on 2026-10-12 with read-only access to the project that the
repository's `POLICYENGINE_SUPABASE_URL` variable names.

1. **The target schema does not exist.** The project has no `ledger` or
   `chronicle` schema. A Data API request for `ledger` returns HTTP 406
   `PGRST106 Invalid schema: ledger`, whose hint lists the exposed schemas
   (`public`, `graphql_public`, `microplex`, `rac`, `akn`, `raw`, `arch`). No
   recorded statement has ever named a `ledger` or `chronicle` schema. Statement
   statistics start on 2025-12-28, before the project's first schema was created,
   and none have been evicted. No applied migration creates either schema.
2. **`query_sources` could not be fixed by changing the schema name.** It reads
   a `sources` table with `jurisdiction` and `institution` columns. Chronicle's
   DB build does not create a `sources` table (see
   `test_export_covers_every_table_the_db_build_writes`), and the mirror loader
   did not write one. That shape is the December 2025 `microplex.sources`
   registry from the pre-Chronicle Cosilico schema.
3. **Nothing reads a hosted copy.** The only mirror-shaped tables in the project
   are nine tables in `arch`. They hold three builds, loaded on 2026-05-05 in an
   older layout (`arch_builds`, `aggregate_facts.target_key`). Statement
   statistics show only two kinds of read: the owner role's verification queries
   on the load day and one audit count on 2026-10-12. No application role (`anon`,
   `authenticated`, `service_role`) has ever read them. The API edge log has no
   request for any mirror table or `sources` path from 2026-07-01 to 2026-10-12,
   apart from the audit's own probes.
4. **No code consumer.** A search of every local clone under the PolicyEngine,
   TheAxiomFoundation, CosilicoAI and ThesisInstitute folders (each checkout's
   default branch and checked-out commit) found no caller outside Chronicle.
   So did GitHub code search of those organizations and the MaxGhenis account.
   No workflow runs the loader, and no workflow reads the repository's Supabase
   variable or secret.
5. **The documented migration never existed.** The docs pointed to
   `supabase/migrations/20260504_chronicle_bronze.sql`. No commit in this
   repository has ever touched a `supabase/` directory.

Fixing the path would have meant creating a schema and thirteen tables in a
shared hosted project, exposing them through the Data API, and running a loader
on a schedule, all for a reader that does not exist.

## Bringing a hosted mirror back

If a consumer needs a hosted query surface later, reintroduce it with:

- a checked-in migration that creates the schema and one table per
  `LEDGER_MIRROR_TABLES` entry, keyed as `LEDGER_MIRROR_PRIMARY_KEYS` orders the
  export;
- the schema exposed through the Data API;
- a scheduled workflow that loads each accepted build;
- a named consumer and the queries it runs;
- tests against a real Postgres, not only a fake client.

Until then, consumers should read `ledger.db` from `ledger-derived` or the
consumer-fact export (`chronicle build-consumer-artifact`).

The rename plan in issue #143 lists the Supabase `ledger` schema and mirror
tables among the operational stores to rename. With the mirror retired, there
is nothing hosted to rename. The `CHRONICLE_SCHEMA` handling that PR #226 adds
for the loader is no longer needed.
