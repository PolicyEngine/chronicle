Retire the legacy SQLite target tables (`targets`, `strata`,
`stratum_constraints`) and everything that wrote or read them:
- the `chronicle load`, `chronicle stats` and `chronicle query` commands
- the last two loaders, `db/etl_soi.py` and `db/etl_snap.py`
- the Supabase `query_targets` / `query_strata` / `insert_targets_batch` helpers,
  and with them, as their last callers, `db/supabase_client.py`,
  `chronicle/client.py` and the `supabase` dependency
- `scripts/export_to_json.py`
- the `as_target` / `target_kwargs` / `TargetBlueprint` normalization helpers
- the legacy names in `chronicle.targets` and `policyengine_chronicle.targets`

Nothing reads these tables today. The values the last two loaders wrote (IRS
SOI Tables 1.1 and 1.4, and SNAP) are published as source-package facts through
the bundle and consumer-fact export, which are unchanged.

`chronicle init` now creates only the source-artifact tables. The AGI-bracket
tables the SOI harness used move into `chronicle/jurisdictions/us/soi.py`.
`policyengine_chronicle.targets` keeps the US poverty/nonfiler target source
coverage.

Migration: Chronicle was never published on PyPI, and no live repository
imports these names. Archived Cosilico-era repositories once did. Code that called `query_targets` should read consumer facts from a
pinned bundle (`chronicle build-bundle`, `chronicle build-consumer-artifact`)
instead.
