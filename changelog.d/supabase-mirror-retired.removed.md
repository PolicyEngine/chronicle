Retire the hosted Supabase mirror path:
- the `chronicle load-supabase-mirror` command, with `load_supabase_mirror`,
  `SupabaseMirrorLoadReport` and `SupabaseTableLoad` in `chronicle.mirror` and
  `load_supabase_mirror_files` in `chronicle.harness`
- `query_sources` (`db.supabase_client`, `chronicle.sources`,
  `chronicle.sources.client`, `policyengine_chronicle.sources`)
- the `POLICYENGINE_LEDGER_SCHEMA` setting and `db.supabase_client.LEDGER_SCHEMA`

Since the 2026-06-30 Ledger rename both have defaulted to a `ledger` schema that
does not exist in the configured Supabase project, so every call with the default
schema failed with `PGRST106 Invalid schema: ledger`. Nothing read the copy an
earlier version of the loader wrote under `arch`. `chronicle export-db-tables` is unchanged and still writes
every `ledger.db` table to JSONL with a checksummed manifest.

Migration: no repository outside Chronicle calls these names. Read `ledger.db`
from `ledger-derived` or build the consumer-fact export instead. See
`docs/supabase-mirror-retirement.md`.
