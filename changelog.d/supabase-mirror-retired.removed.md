Retire the hosted Supabase mirror path and the Supabase client:
- the `chronicle load-supabase-mirror` command, with `load_supabase_mirror`,
  `SupabaseMirrorLoadReport` and `SupabaseTableLoad` in `chronicle.mirror` and
  `load_supabase_mirror_files` in `chronicle.harness`
- `query_sources` (`db.supabase_client`, `chronicle.sources`,
  `chronicle.sources.client`, `policyengine_chronicle.sources`)
- the `POLICYENGINE_LEDGER_SCHEMA` setting and `db.supabase_client.LEDGER_SCHEMA`
- the `db.supabase_client` module (`SupabaseConfig`, `get_supabase_client`) and
  `chronicle.client`, which re-exported it
- the `supabase` dependency and the packages only it required

Since the 2026-06-30 Ledger rename the loader and `query_sources` defaulted to
a `ledger` schema. Read-only checks on 2026-10-12 found no such schema in the
configured Supabase project, so every call with the default schema failed with
`PGRST106 Invalid schema: ledger`. They also found that nothing had read the
copy an earlier version of the loader wrote under `arch`. The client's other
callers, the legacy target-input helpers, were retired first (chronicle#353),
so no shipped module imports a Supabase client. `chronicle export-db-tables`
is unchanged and still writes every `ledger.db` table to JSONL with a
checksummed manifest.

`pypdf` is now required with its `crypto` extra. pypdf needs `cryptography` to
read one AES-encrypted publisher PDF, and `cryptography` used to arrive only
through `supabase`.

Migration: searches on 2026-10-12 found no repository outside Chronicle that
imports these names. Read `ledger.db` from `ledger-derived` or build the
consumer-fact export instead. See `docs/supabase-mirror-retirement.md`.
