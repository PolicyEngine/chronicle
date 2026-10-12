# Hosted Supabase mirror retirement

Chronicle used to document a hosted Supabase/Postgres copy of each accepted
build, loaded with `chronicle load-supabase-mirror` and queried with
`query_sources`. Both once addressed live tables under older schema names, but
successive renames left them pointing at a schema nobody created. Since the
Ledger rename (2026-06-30) both have defaulted to a `ledger` schema that does
not exist in the configured project. Nothing read the copy that was loaded, so
both were retired on 2026-10-12.

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
- `ledger.db` itself is the relational artifact. `build-suite` writes it, and
  `publish-derived` can upload it to `ledger-derived`.
- `publish-derived --build-artifacts-out` still writes `build_artifacts` rows
  for the objects it published.
- When this retirement landed, `SupabaseConfig` and `get_supabase_client` stayed
  in `db/supabase_client.py` only for the legacy target-input helpers
  (`query_targets`, `query_strata`, `insert_targets_batch`). Those helpers are
  being retired separately, and the client and the `supabase` dependency go with
  them.

## History

| Date | `query_sources` addressed | Hosted mirror and loader |
|------|----------------------|--------------|
| 2025-12-28 | `microplex.sources`, the Cosilico-era registry (26 rows, with `jurisdiction` and `institution` columns) | (no loader yet) |
| 2026-04-27 | `arch.sources`, a table the project does not have today | (no loader yet) |
| 2026-05-05 | `arch.sources` | Nine `arch` tables, a subset of the Arch-era loader's thirteen, were created by DDL run as the owner role and filled with three builds through Data API upserts |
| 2026-05-27 | `arch.sources` | The loader reached `main` with default schema `arch` |
| 2026-06-30 | `ledger.sources` (does not exist) | Default schema `ledger` (does not exist) |

Statement history from December 2025 shows reads of `microplex.sources` in
exactly `query_sources`'s shapes, including the `jurisdiction` and
`institution` filters. The docs cited a migration under three names in turn
(`20260504_arch_bronze.sql`, `20260504_ledger_bronze.sql`,
`20260504_chronicle_bronze.sql`). No such file was ever committed to this
repository, and none is among the project's applied migrations; the `arch`
tables came from DDL run directly on 2026-05-05.

## Why retire

Checked on 2026-10-12 with read-only access to the project that the
repository's `POLICYENGINE_SUPABASE_URL` variable names.

1. **The current target schema does not exist.** The project has no `ledger`
   or `chronicle` schema, so every call with the default schema fails: a Data
   API request for `ledger` returns HTTP 406 `PGRST106 Invalid schema: ledger`.
   No recorded statement has ever named a `ledger` or `chronicle` schema.
   Statement statistics start on 2025-12-28, before any application schema was
   created, and none have been evicted. No applied migration creates either
   schema.
2. **Renaming the schema would not give `query_sources` anything Chronicle
   builds.** It reads a `sources` table with `jurisdiction` and `institution`
   columns. Chronicle's DB build does not create a `sources` table (see
   `test_export_covers_every_table_the_db_build_writes`), and the mirror loader
   did not write one. A schema setting can only point it back at the
   Cosilico-era `microplex.sources`.
3. **Nothing reads the hosted copy.** The nine `arch` tables from 2026-05-05 are
   the only mirror-shaped tables in the project. Their layout predates the
   current loader: `aggregate_facts` is keyed on `target_key`, and four of
   today's thirteen tables are missing. Statement statistics show only two kinds
   of read: the owner role's verification queries on the load day and one audit
   count on 2026-10-12. No application role (`anon`, `authenticated`,
   `service_role`) has ever read them, and no view or function depends on them.
   The API edge log keeps 90 days (2026-07-15 to 2026-10-12). In that window the
   Data API received 22 requests in all: 8 for `rules`, 11 for
   `credit_packages`, and 3 from the audit itself, one of them to `sources`.
   None asked for a mirror table.
4. **No code consumer.** The search covered:
   - 1,797 local checkouts (each default branch and checked-out commit) at the
     top level and in the worktree folders of the PolicyEngine,
     TheAxiomFoundation, CosilicoAI and ThesisInstitute directories;
   - 246 organization repositories with no local clone, archived ones included;
   - non-default branches updated since December 2025 in 394 repositories;
   - GitHub code search of those organizations and the MaxGhenis account.

   The retired names appear only in Chronicle itself: its branches and its
   clones, including one under its previous name, `arch-data`. The other hits
   are archived Cosilico-era repositories that read the `microplex` tables
   directly or a local SQLite file. No workflow runs the loader, and no workflow
   reads the repository's Supabase variable or secret.

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
tables among the operational stores to rename. With the mirror retired,
nothing Chronicle writes or reads is hosted, so there is nothing to rename. The
`CHRONICLE_SCHEMA` handling that PR #226 adds for the loader is no longer
needed.
