# Hosted Supabase mirror retirement

Chronicle used to document a hosted Supabase/Postgres copy of each accepted
build, loaded with `chronicle load-supabase-mirror` and queried with
`query_sources`. Both once addressed live tables under older schema names, but
successive renames left them pointing at a schema nobody created. Since the
Ledger rename (2026-06-30) both have defaulted to a `ledger` schema that does
not exist in the configured project. Nothing read the copy that was loaded.
chronicle#351 retired both on that evidence, which dates from 2026-10-12, and
deleted the Supabase client and the `supabase` dependency with them.

## What was retired

| Surface | Where it lived | What it did |
|---------|----------------|-------------|
| `chronicle load-supabase-mirror` | `chronicle/harness.py`, `chronicle/cli.py` | Upserted `export-db-tables` JSONL into a Supabase schema (default `ledger`) through the Data API |
| `load_supabase_mirror`, `SupabaseMirrorLoadReport`, `SupabaseTableLoad` | `chronicle/mirror.py` | The loader behind the command |
| `load_supabase_mirror_files` | `chronicle/harness.py` | Harness wrapper for the loader |
| `query_sources` | `db/supabase_client.py`, re-exported by `chronicle.sources`, `chronicle.sources.client` and `policyengine_chronicle.sources` | Read a `sources` table from the same schema |
| `LEDGER_SCHEMA` / `POLICYENGINE_LEDGER_SCHEMA` | `db/supabase_client.py` | Named that schema |
| `SupabaseConfig`, `get_supabase_client` | `db/supabase_client.py`, re-exported by `chronicle.client` | Read `POLICYENGINE_SUPABASE_URL` and a service key from the environment and built the Supabase client |
| `chronicle.client` | `chronicle/client.py` | Re-exported those two names |
| The `supabase` dependency | `pyproject.toml`, `uv.lock` | Installed the Supabase client library and the packages only it required |

Besides the loader and `query_sources`, only the legacy target-input helpers
(`query_targets`, `query_strata`, `insert_targets_batch`) used the client.
chronicle#353 retired those first, so chronicle#351 deleted the client module,
its re-export and the dependency as well. No shipped module imports a Supabase
client (`tests/test_supabase_mirror_retired.py`).

`cryptography` used to arrive only through `supabase`. pypdf needs it to read
the one AES-encrypted publisher PDF Chronicle keeps
(`db/data/sfpd/pension_amount_bands_2025/nl_statistiek_2025.pdf`), so
`pyproject.toml` now asks for `pypdf[crypto]`.

## What stays

- `chronicle export-db-tables` still writes every table of a `ledger.db`
  artifact to deterministic JSONL plus a checksummed `manifest.json`. Use it to
  load Chronicle tables into another store, to diff builds, or to archive them.
- `ledger.db` itself is the relational artifact. `build-suite` writes it, and
  `publish-derived` can upload it to `ledger-derived`.
- `publish-derived --build-artifacts-out` still writes `build_artifacts` rows
  for the objects it published.

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
   Retained API edge logs start on 2026-07-15. From then to 2026-10-12 the Data
   API received 22 requests in all: 8 for `rules`, 11 for
   `credit_packages`, and 3 from the audit itself, one of them to `sources`.
   None asked for a mirror table.
4. **No code consumer.** The search covered:
   - 1,797 local checkouts (each default branch and checked-out commit) at the
     top level and in the worktree folders of the PolicyEngine,
     TheAxiomFoundation, CosilicoAI and ThesisInstitute directories;
   - 246 organization repositories with no local clone, archived ones included;
   - non-default branches updated since December 2025 in 392 repositories,
     plus all 424 branch tips of `axiom-corpus`, which failed to fetch and was
     scanned from its local clone instead;
   - GitHub code search of those organizations and the MaxGhenis account.

   The retired names appear only in Chronicle itself: its branches and its
   clones, including one under an earlier name, `arch-data`. The other matches
   are unrelated uses of the same search terms, or read a local SQLite file;
   none reads the mirror or calls `query_sources`. No workflow runs the loader, and no workflow
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
Chronicle reads and writes no Supabase schema, so the plan has no Supabase
schema to rename. The retirement takes no other store out of that plan:
Chronicle still reads and writes the R2 buckets `ledger-raw` and
`ledger-derived`, and `ledger.db` keeps its file name and its `ledger_builds`
table. The `CHRONICLE_SCHEMA` handling that PR #226 adds for the loader is no
longer needed.
