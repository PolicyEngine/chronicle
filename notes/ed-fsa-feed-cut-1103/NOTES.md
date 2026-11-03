# ed_fsa US feed cut, 3 November 2026

A cloud build session for the student debt pilot hub wrote these notes. Every
command below ran in this session, and every statement about code cites the
file and line it read. Paths without a commit name refer to the cut,
`41b2fb2b`.

## Result

| | |
|---|---|
| Cut branch | `feed/us-a9026cc-ed-fsa-1103`, pushed once at `41b2fb2b`. Not tagged: the hub tags it |
| Tests | `test_chronicle_ed_fsa_portfolio.py` 28 passed; `test_chronicle_census_acs_s1501.py` 9 passed; `test_chronicle_bundle.py` **13 passed, 1 failed**, the same failure as the base `a9026cc`'s own run of that file (section 2) |
| Cut commit | `41b2fb2b864a28c0eda03322b77a97ef147dfa3c`: `a9026cc8f` plus a cherry-pick of `4448a7c96`, and nothing else |
| Scope | 706 pairs: #1345's 640 plus **66** ed_fsa pairs (not 6), all at build year 2026; 72 package runs; sha256 `73a39c166a8f78c8a8a1ae711515e5d2e6b76a74952e67d7783cf974a4615633` |
| Feed | 40,642 rows, 171,661,396 bytes, `facts_sha256` `1d45a89c28177a95371b4cc4068d3657c7bf12bd8edad7c82fe25bf453f9ea07`, bare feed (`--skip-artifact`) |
| Old rows | Dropping the 66 new pairs leaves 40,181 lines whose bytes hash to `4d89e4a498ffd73a407821d9ce2c45837072901e0a29acf3206160d1fafd7c14`: #1345's feed exactly, in order |
| New rows | 461 rows in the 66 pairs, every one `chronicle.consumer_fact.v3` |
| #1357 fixture | 0 of its 244 rows appear byte for byte. All 244 match one of my rows on `aggregate_fact_key`, and each is byte-identical to that row once my row's `schema_version` reads v4. The fixture lacks 217 of my 461 rows (35 pairs) |

**For the hub to decide: the FSA rows are `chronicle.consumer_fact.v3`, not the
v4 that #1357 expects.** The packages don't need later code. They load,
validate and pass their own tests at the cut, and the cut builds them. But the
cut's exporter stamps every row with one constant, and at `a9026cc` that
constant is v3. `chronicle/consumer_contract.py:35` sets
`CONSUMER_FACT_SCHEMA_VERSION = CONSUMER_FACT_EMIT_SCHEMA_VERSION`, and `:664`
writes it as every row's `schema_version`. That constant is the last entry of
`CONSUMER_FACT_ROW_CONTRACTS` (`chronicle/epoch.py:171-176`), and the tuple
ends at v3. In the FSA rows, that stamp is the only thing that differs from
#347's export. I built the six packages
at `acbedb5` as well: 461 v4 rows, the fixture's 244 among them byte for byte,
and every one of my 461 rows is byte-identical to its `acbedb5` row once its
stamp reads v4. So the FSA facts, keys, labels, lineage and provenance are
#347's exactly; only the stamp differs. v4 entered main in `0ec21e5` ("Give
every UK geography one canonical name", chronicle#281, merged in #282 as
`00b4b14` on 2026-09-22), which appends v4 to `CONSUMER_FACT_ROW_CONTRACTS`
and also adds the UK geography register, the v4 schema files and changes to
`chronicle/bundle.py`, `chronicle/consumer_contract.py` and
`chronicle/source_package.py` (12 files). Because the stamp is one constant,
taking that commit would stamp **every** feed row v4, so the 40,181 old rows
could no longer match #1345's bytes. I read that code but did not pull the
commit in or try it. Its register (`chronicle/geography/uk_canonical_names.json`
at `0ec21e5`) holds 953 identifiers, none containing "US", so I would expect
the stamp to be the only change on US rows, but I have not run it.

## Preflight

- Fetched at #1345's head `b04b3f59f474f3d3e4ffd105c27fbc667baadcfc` through
  raw.githubusercontent.com, all exit 0:

  | File | Bytes | sha256 |
  |---|---|---|
  | `docs/us-chronicle-feed-repin.md` | 21,666 | `b2d3768ca67c209021018997f03cccbe20a068e98051db3af7391f4a8bc31c4c` |
  | `tools/build_us_chronicle_feed.py` | 11,843 | `c9f781f0338b2d341736baad66d667172d8b682ef306651c053395e94aabf355` |
  | `packages/microcosm-build/src/microcosm/build/us/chronicle_feed_scope.json` | 181,175 | `04460f39e5c2b79011724ce33cac4ccf3b0f42812bc7179b6b532773483fe04e` (equals the pin's `scope_sha256`) |
  | `packages/microcosm-build/src/microcosm/build/us/chronicle_feed.json` (the pin; read for its digests) | 1,540 | `71fe5b364323bcda709bf4f74c1d9aafd18baa45045b0748b3d18bf75d2ecdd7` |

  The pin reads as the brief says: `source_commit` `a9026cc8f…`, 40,181 rows,
  `facts_sha256` `4d89e4a4…`, `scope_sha256` `04460f39…`, schema
  `chronicle.consumer_fact.v3`.
- `gh api repos/PolicyEngine/chronicle --jq .full_name` printed
  `PolicyEngine/chronicle`.
- Read Chronicle's `AGENTS.md` (there is no `CLAUDE.md`). Nothing here adds
  a computed value: every fact is a published FSA cell, and the scope only
  selects rows.
- The scope round-trips through `json.dumps(scope, indent=1) + "\n"` byte for
  byte, and its 640 pairs are sorted by (`record_set_id`, `period_type`,
  `period_value`). Each `runs` list is sorted.
- No branch `feed/us-a9026cc-ed-fsa` existed on the remote (`git ls-remote`
  listed five `feed/*` branches, none of them it), so no earlier session made
  one, and I used the brief's names. No `hub-notes/*` branch existed either.

## 1. The cut

- The clone was shallow; `git fetch --unshallow` and a tag fetch made it whole.
  Tag `microcosm-us-feed-1343-v1` is an annotated tag (object `d4e4a728…`)
  that peels to `a9026cc8f80307af0c4527fdb3779fab32ffad9f`, which is also the
  head of `feed/us-cf9ece2-agi-age-labels`.
- `git checkout -b feed/us-a9026cc-ed-fsa-1103 a9026cc8f`, then
  `git cherry-pick 4448a7c96`, with nothing else. The cut is
  `41b2fb2b864a28c0eda03322b77a97ef147dfa3c`: parent `a9026cc8f`, author kept
  as the original commit's, and the original message followed by a note on the
  resolution and `(cherry picked from commit 4448a7c…)`.
- #347 is `4448a7c` plus one merge of main into it (`81e3f98`). The ed_fsa
  files are the same at `4448a7c96`, `81e3f98` and `acbedb5`.
- `chronicle/source_package.py` and `chronicle/sources/rows.py` merged
  without conflicts. The one conflict was `tests/test_chronicle_bundle.py`:
  `a9026cc` and main pin different 2023 bundle counts there.
- **Check against #347:** `git diff acbedb5 41b2fb2b -- packages/ed_fsa
  db/data/ed_fsa` is empty (0 bytes). The same holds for
  `packages/census/acs_s1501_state_2024` and
  `db/data/census/acs_s1501_state_2024`, against both `acbedb5` and
  `4448a7c96`.
- The cut and `4448a7c96` both change 29 files with 48,489 insertions and 2
  deletions. `git range-diff a5280e18e..4448a7c96 a9026cc8f..41b2fb2b` shows
  that no added or removed line differs.

### Hunks that differ from `4448a7c96`'s patch

Only context lines differ, and only in two hunks of
`tests/test_chronicle_bundle.py`. Every added and removed line is
`4448a7c96`'s.

1. `tests/test_chronicle_bundle.py`, `@@ -139,7 +139,10 @@` (the cut) against
   `@@ -404,7 +404,10 @@` (`4448a7c96`): the 2023 bundle's `summary["counts"]`.
   The change is the same: `"skipped_source_count": 10` becomes the chronicle#310
   comment plus `17`. The surrounding lines are `a9026cc`'s:
   `"geography_count": 12586`, `"period_count": 493`,
   `"semantic_duplicate_key_count": 213`, `"source_count": 50`,
   `"source_package_count": 217`. At `4448a7c96` they are 20548, 511, 2324
   (with comments), 56 and 377. **Why:** the conflict was resolved by keeping
   `a9026cc`'s lines and adding only #347's change. The base has 217 packages,
   so its 2023 bundle is not main's. The test fails at this assert, but on
   three base counts this hunk leaves alone, not on the line it changes
   (section 2).
2. `tests/test_chronicle_bundle.py`, `@@ -167,16 +170,23 @@` against
   `@@ -449,16 +452,23 @@`: the `source_packages` asserts. The changes are the
   same, `skipped_source_count == 10` becoming `== 17` plus seven skipped ids
   (`census-acs-s1501-state-attainment-2024` and the six `ed-fsa-*`). The
   context keeps `a9026cc`'s `rows[0]` key-prefix asserts and
   `source_package_count == 217`, where `4448a7c96` has 377. **Why:** same as
   hunk 1.

Every other hunk equals `4448a7c96`'s, context included, apart from line
numbers. The `chronicle/source_package.py` hunks sit further down the file at
`4448a7c96`, whose alias map is longer, but carry the same lines between the
same neighbours: the import (`:51`), the ACS alias (`:280`), the six ed_fsa
aliases (`:382-395`) and the two parser branches (`:616`, `:892`). The `chronicle/sources/rows.py` hunk is at
the same line (`:689`, `S1501_ATTAINMENT_COLUMNS` at `:700`). The changelog,
the packages, their data files and both new test files are byte-identical.

The cherry-pick also brings `packages/census/acs_s1501_state_2024` and its
parser, because `4448a7c96` carries them. The brief says to take that commit
and nothing else. The scope does not include the ACS package (see section 3).

## 2. Tests

Each file ran in its own process (`uv run --frozen pytest -p no:cacheprovider
<file>`), in the main checkout with its tree equal to the cut. `pytest-xdist`
is not in the cut's lockfile, so no `-n`.

| File | Result |
|---|---|
| `tests/test_chronicle_ed_fsa_portfolio.py` | 28 passed |
| `tests/test_chronicle_census_acs_s1501.py` | 9 passed |
| `tests/test_chronicle_bundle.py` | **13 passed, 1 failed** (63 min). At the base `a9026cc` the same file gives the same result with the same failure (61 min), so the failure is the base's, not the cherry-pick's; see below |

The warnings are dependency deprecations (pyiceberg, pydantic). I also ran
two files the brief does not name, because they check the alias map that the
cherry-pick extends: `tests/test_source_package_alias_drift.py` 8 passed and
`tests/test_us_poverty_target_coverage.py` 6 passed.

**The bundle test ran three times:** twice at the cut (the first run died, see
below) and once at the base. Its
`test_build_bundle_writes_merged_consumer_contract` builds the whole 2023
bundle of 236 default sources in pytest's temp directory. The first run
shared the disk with my first feed build, and the session's disk allowance ran
out at 19:47 UTC: `OSError: [Errno 28] No space left on device`. Just after,
the test's temp held about 16 GB for its first 121 sources, mostly per-source
`ledger.db` (9.0 GB), `source_cells.jsonl` (3.9 GB) and `source_rows.jsonl`
(2.4 GB).
`mhclg-council-taxbase-england-2025` stopped mid-build in that window (3 of 9
outputs). `build_bundle` catches a source's exception, records
`source_suite_build_failed` and goes on (`chronicle/bundle.py:371-389`), so
that run could not have passed. I stopped it and deleted its temp directory.

From the input sizes of the sources still to come, I estimated the whole bundle
at about 31 GB of per-source outputs. The allowance has about 29 GB free when
nothing else runs. So the rerun at the cut ran alone, beside a janitor
(`bundle_test_janitor.py`, described here, not committed). For each source
whose build had finished, it deleted only those three intermediate files, and
only in that test's bundle. A source counts as finished once a later source in
`DEFAULT_BUNDLE_SOURCES` order has a directory. Why this cannot change the
result:

- `build_bundle` builds sources one at a time (`chronicle/bundle.py:369-416`).
  After a source's suite returns it reads only that source's
  `consumer_facts.jsonl` (`:399`), and after the loop it works from rows in
  memory (`:418-494`). It never reads `ledger.db`, `source_cells.jsonl` or
  `source_rows.jsonl`; the file never names them.
- The test (`tests/test_chronicle_bundle.py:123-1387`) reads the merged
  outputs. Per source, it only checks that `consumer_facts.jsonl` and, for
  one source, `reports/build_summary.json` exist (`:1230-1385`). The janitor
  keeps both. The one other reference to `source_rows.jsonl` (`:1440`) is a
  separate test that builds its own bundle in its own temp directory.

At the cut, the janitor cleaned 218 of the 219 built sources (the last has no
later source) and freed 26.91 GB. Every source directory it cleaned kept its
six other outputs and its 11 reports. The base run (below) used the same
janitor, which freed the same 26.91 GB.

**The one failure, and why it is the base's.**
`test_build_bundle_writes_merged_consumer_contract` stops at its first
assert, `summary["counts"] == {...}` (`tests/test_chronicle_bundle.py:134`).
Eight counts match, `"skipped_source_count": 17` among them (the cherry-pick's
change). Three differ:

| Count | Built | Expected | Difference |
|---|---|---|---|
| `source_package_count` | 219 | 217 | +2 |
| `fact_count` | 340,969 | 339,948 | +1,021 |
| `warning_count` | 168 | 171 | -3 |

`report.valid` and `summary["valid"]` passed. The skipped sources are exactly
the 17 the test lists. The expected values are `c5e5bf8`'s:
`git log c5e5bf8..a9026cc8f -- tests/test_chronicle_bundle.py` is empty, so
none of the base's six commits after `c5e5bf8` (`51aa40f`, `2744154`,
`cf9ece2`, `2431ba8`, `d1d28dc`, `a9026cc`) updated this test. Two of them add
packages to the default bundle, and in this run's bundle those account for the
gap exactly:

- `51aa40f`, `soi-historic-table-2-state-agi-2023`: 1,020 facts;
- `cf9ece2`, `bea-nipa-private-group-health-insurance`: 1 fact.

That is +2 packages and +1,021 facts. `2744154` backports a guard match.
`2431ba8`, `d1d28dc` and `a9026cc` give AGI `under_1` and `all` and age
`85_plus` one label each. No warning in this run's report mentions those
values, and `conflicting_value_label_across_packages` counts 6. That fits
three fewer warnings than the test expects.

**The base fails the same way.** I ran the same file at `a9026cc8f`, in its
own worktree, with the same command and the same janitor: **13 passed, 1
failed** (61 min). It fails at the same assert,
`tests/test_chronicle_bundle.py:134`, on the same three counts (219 against
217, 340,969 against 339,948, 168 against 171). Its `skipped_source_count` is
10, as the base's test expects. I then compared the two runs' 2023 bundles:

- the merged `consumer_facts.jsonl` (340,969 rows, sha256
  `4218767537051da2ffa9843d900ff12d12183c4c4c2275bdae6818d9f5a090ee`) and
  `coverage.json` are byte-identical;
- the 219 built packages' entries in `source_packages.json` are identical;
- the report's errors, warnings and validity are identical, and its counts
  differ only in `skipped_source_count`: 17 at the cut, 10 at the base;
- the cut skips seven sources the base does not have,
  `census-acs-s1501-state-attainment-2024` and the six `ed-fsa-*` packages.
  The ten skipped sources both share differ only in
  `validation.package_path`, which names the checkout the run used.

So the cherry-pick changes the 2023 bundle only by those seven skipped
sources, which is exactly what its test lines assert. The failing assert
fails the same way without the cherry-pick.

## 3. Scope: the pairs added

`chronicle_feed_scope.json` here is #1345's scope with:

- `source_commit` set to `41b2fb2b864a28c0eda03322b77a97ef147dfa3c`;
- **66 pairs added**, one per (record set, period) that the six
  `packages/ed_fsa` packages emit at build year 2026, in the file's entry form
  and its sort order (record_set_id, period_type, period_value). They land
  between `cms_nhe.*` and `federal_reserve_z1.*`. The 640 old entries keep
  their order and bytes;
- `runs["2026"]` gaining the six packages, kept sorted (2 packages to 8);
- `pair_count` 640 to 706. `runs` now lists 72 package runs (66 before);
- `rule` gaining one clause before its closing "each built from ..." sentence:
  "plus the 66 Federal Student Aid loan portfolio record sets of the six
  packages/ed_fsa packages (ed_fsa.*, chronicle#347, microcosm#1357), each one
  quarter-end month from 2025-12 to 2026-06 and built at 2026, the only year
  their manifests carry a file for".

It is written as `json.dumps(scope, indent=1) + "\n"`. The builder's
`load_scope` accepts it. Its sha256 is
`73a39c166a8f78c8a8a1ae711515e5d2e6b76a74952e67d7783cf974a4615633`.

**Why 66 and not 6.** Each package has one record set per table, quarter and
measure, and each record set has a single `period` (the quarter-end month), so
a pair is a record set. That gives 36 + 4 + 4 + 12 + 1 + 9 = 66 record sets,
with distinct ids across the six packages. Six is the package count. I found
66 two ways:

1. from the six `source_package.yaml` files at the cut, as the scope script
   reads them;
2. from `chronicle build-bundle --year 2026` over those six packages alone, at
   the cut: 461 rows (227 + 24 + 36 + 42 + 108 + 24), all valid, in exactly the
   same 66 pairs.

Before the feed build I also ran the scope's whole 2026 run as a trial: the
six packages plus `cbo/revenue_projections_income_by_source_2026_02` and
`jct/obbba_revenue_estimates_2025`. It exited 0, valid, with 0 errors, 0
warnings and 469 facts from 8 packages. Each ed_fsa package's
`consumer_facts.jsonl` came out byte-identical to the six-package run's, so
sharing a run with other packages does not change the FSA rows.

| Package | Pairs | Rows |
|---|---|---|
| `packages/ed_fsa/dl_portfolio_by_repayment_plan_fy2026_q3` | 36 | 227 |
| `packages/ed_fsa/portfolio_by_age_fy2026_q2` | 4 | 24 |
| `packages/ed_fsa/portfolio_by_debt_size_fy2026_q2` | 4 | 36 |
| `packages/ed_fsa/portfolio_by_loan_type_fy2026_q3` | 12 | 42 |
| `packages/ed_fsa/portfolio_by_location_fy2026_q2` | 1 | 108 |
| `packages/ed_fsa/portfolio_summary_fy2026_q3` | 9 | 24 |

The periods are `month` 2025-12 (23 pairs), 2026-03 (24) and 2026-06 (19).

**Why build year 2026 for all.** The repin doc's rule is "the pair's own period
year when the package emits the pair for that year, otherwise the earliest
export year that emits it". Each of the six manifests keys exactly one file
year, 2026. `test_other_years_have_no_artifact` passes, so `--year 2025`
raises "No source artifact for year 2025". That makes 2026 the earliest
emitting year for the 23 pairs dated 2025-12, and the own year for the rest.

## 4. Build and receipt

The build used a clean worktree at the cut (`git worktree add --detach <dir>
41b2fb2b`, then `uv sync --frozen`; `git status --porcelain` empty), outside
the main checkout, and wrote to a directory outside both:

```bash
uv run --no-project python -I build_us_chronicle_feed.py \
  --chronicle-root <worktree at 41b2fb2b> \
  --scope chronicle_feed_scope.json --out <out dir> --skip-artifact
```

`build_us_chronicle_feed.py` is #1345's builder, sha256 `c9f781f0…`. It
checks that the checkout is clean at the scope's commit
(`build_us_chronicle_feed.py:120-133`). It runs one `chronicle build-bundle
--year Y --source …` per build year (`:136-154`, `:274-280`). It keeps a row
only from the run its pair is scoped to and refuses a scoped pair with no row
(`:178-210`).

The receipt (`receipt.json` here, sha256 `366cc29b…`):

| Field | Value |
|---|---|
| `row_count` | **40,642** (40,181 + 461) |
| `facts_sha256` | **`1d45a89c28177a95371b4cc4068d3657c7bf12bd8edad7c82fe25bf453f9ea07`** |
| `scope_sha256` | `73a39c166a8f78c8a8a1ae711515e5d2e6b76a74952e67d7783cf974a4615633` (this directory's `chronicle_feed_scope.json`) |
| `source_commit` | `41b2fb2b864a28c0eda03322b77a97ef147dfa3c` |
| `pair_count` | 706 |
| `rows_per_pair_min` / `max` | 1 / 26,880 |
| `runs` | 10 years, 72 package runs: 2020 (4), 2021 (1), 2022 (7), 2023 (28), 2024 (19), 2025 (2), 2026 (8), 2027 (1), 2028 (1), 2029 (1) |
| `artifact` | `null` (`--skip-artifact`, as #1345) |

The run took 23 min 46 s. Its `scope`, `chronicle_root` and `facts_path` are
this session's scratch paths. I recomputed the sha256 of the written
`consumer_facts.jsonl` and it equals `facts_sha256`.

**The feed build ran twice as well.** The first attempt shared the disk with
the first bundle-test run and stopped with `Errno 28` partway through its 2024
run; I deleted its output. The second ran beside the bundle test's run at the
base (section 2), and the two would not fit on the disk side by side
uncleaned. So it ran with a second janitor (`feed_build_janitor.py`), and the
session's disk use peaked at 23 GB during its 2023 run. Once a later
year's bundle directory existed, the janitor deleted `ledger.db`,
`source_cells.jsonl` and `source_rows.jsonl` under that earlier year's
`bundles/<year>/sources/*/`: 15.75 GB over 2020 to 2028. That cannot change
the feed. The builder starts the next year only after the year's
`chronicle build-bundle` subprocess has returned (`run_bundle`,
`build_us_chronicle_feed.py:136-154`) and `package_fact_files` has read that
year's `source_packages.json` (`:157-175`). After that it reads only each
package's `consumer_facts.jsonl` (`select_rows`, `:178-210`). The janitor
kept both files, and the old rows match #1345's digest.

Every source file came from the commit. `chronicle/source_package.py:2493-2525`
reads the package's file and otherwise only a local cache, and fetches only
when `LEDGER_SOURCE_ARTIFACT_FETCH` is set. It was not set, and
`~/.cache/policyengine-chronicle` did not exist before or after the build.

## 5. Checks

### The receipt

40,642 rows, `facts_sha256` `1d45a89c…`, as above. The feed is sorted by
`aggregate_fact_key`, every key is unique, and every row belongs to a scoped
pair.

### The old rows: passed

I dropped every row whose (record set, period type, period value) is one of
the 66 new pairs and kept the rest in feed order. That leaves **40,181 lines,
sha256 `4d89e4a498ffd73a407821d9ce2c45837072901e0a29acf3206160d1fafd7c14`**,
the count and digest #1345's pin records. So the rest of the feed is #1345's
feed byte for byte and in order, and I did not need to rebuild #1345's feed.

### The new rows

461 rows in the 66 pairs, every pair with at least one row: 227 + 24 + 36 + 42
+ 108 + 24 by package. **All 461 are `chronicle.consumer_fact.v3`, and so are
all 40,181 other rows**, so the feed has one schema version, v3, the one the
pin lists in `consumer_fact_schema_versions`. The FSA rows are not the v4 that
#1357 expects (see the top of these notes). `ed_fsa_rows.jsonl` holds these
461 lines in feed order. They are byte-identical to the six-package
`build-bundle --year 2026` run at the cut, so the `acbedb5` comparison applies
to them.

Rows per pair, and whether #1357's fixture has them:

| Record set | Period | Rows | In #1357's fixture |
|---|---|---|---|
| **`packages/ed_fsa/dl_portfolio_by_repayment_plan_fy2026_q3`** | | **227** | |
| `ed_fsa.dl_by_repayment_plan.fy2026_q1.dollars_outstanding` | month 2025-12 | 10 | no |
| `ed_fsa.dl_by_repayment_plan.fy2026_q1.recipients` | month 2025-12 | 9 | no |
| `ed_fsa.dl_by_repayment_plan.fy2026_q2.dollars_outstanding` | month 2026-03 | 10 | yes |
| `ed_fsa.dl_by_repayment_plan.fy2026_q2.recipients` | month 2026-03 | 9 | no |
| `ed_fsa.dl_by_repayment_plan.fy2026_q3.dollars_outstanding` | month 2026-06 | 10 | no |
| `ed_fsa.dl_by_repayment_plan.fy2026_q3.recipients` | month 2026-06 | 9 | no |
| `ed_fsa.dl_idr_by_partial_financial_hardship.fy2026_q1.dollars_outstanding` | month 2025-12 | 4 | no |
| `ed_fsa.dl_idr_by_partial_financial_hardship.fy2026_q1.recipients` | month 2025-12 | 4 | no |
| `ed_fsa.dl_idr_by_partial_financial_hardship.fy2026_q2.dollars_outstanding` | month 2026-03 | 4 | no |
| `ed_fsa.dl_idr_by_partial_financial_hardship.fy2026_q2.recipients` | month 2026-03 | 4 | no |
| `ed_fsa.dl_idr_by_partial_financial_hardship.fy2026_q3.dollars_outstanding` | month 2026-06 | 4 | no |
| `ed_fsa.dl_idr_by_partial_financial_hardship.fy2026_q3.recipients` | month 2026-06 | 4 | no |
| `ed_fsa.ed_held_ffel_by_repayment_plan.fy2026_q1.dollars_outstanding` | month 2025-12 | 8 | no |
| `ed_fsa.ed_held_ffel_by_repayment_plan.fy2026_q1.recipients` | month 2025-12 | 7 | no |
| `ed_fsa.ed_held_ffel_by_repayment_plan.fy2026_q2.dollars_outstanding` | month 2026-03 | 8 | no |
| `ed_fsa.ed_held_ffel_by_repayment_plan.fy2026_q2.recipients` | month 2026-03 | 7 | no |
| `ed_fsa.ed_held_ffel_by_repayment_plan.fy2026_q3.dollars_outstanding` | month 2026-06 | 8 | no |
| `ed_fsa.ed_held_ffel_by_repayment_plan.fy2026_q3.recipients` | month 2026-06 | 7 | no |
| `ed_fsa.ed_held_ffel_idr_by_partial_financial_hardship.fy2026_q1.dollars_outstanding` | month 2025-12 | 2 | no |
| `ed_fsa.ed_held_ffel_idr_by_partial_financial_hardship.fy2026_q1.recipients` | month 2025-12 | 2 | no |
| `ed_fsa.ed_held_ffel_idr_by_partial_financial_hardship.fy2026_q2.dollars_outstanding` | month 2026-03 | 2 | no |
| `ed_fsa.ed_held_ffel_idr_by_partial_financial_hardship.fy2026_q2.recipients` | month 2026-03 | 2 | no |
| `ed_fsa.ed_held_ffel_idr_by_partial_financial_hardship.fy2026_q3.dollars_outstanding` | month 2026-06 | 2 | no |
| `ed_fsa.ed_held_ffel_idr_by_partial_financial_hardship.fy2026_q3.recipients` | month 2026-06 | 2 | no |
| `ed_fsa.federally_managed_by_repayment_plan.fy2026_q1.dollars_outstanding` | month 2025-12 | 11 | no |
| `ed_fsa.federally_managed_by_repayment_plan.fy2026_q1.recipients` | month 2025-12 | 10 | no |
| `ed_fsa.federally_managed_by_repayment_plan.fy2026_q2.dollars_outstanding` | month 2026-03 | 11 | no |
| `ed_fsa.federally_managed_by_repayment_plan.fy2026_q2.recipients` | month 2026-03 | 11 | no |
| `ed_fsa.federally_managed_by_repayment_plan.fy2026_q3.dollars_outstanding` | month 2026-06 | 11 | no |
| `ed_fsa.federally_managed_by_repayment_plan.fy2026_q3.recipients` | month 2026-06 | 11 | no |
| `ed_fsa.federally_managed_idr_by_partial_financial_hardship.fy2026_q1.dollars_outstanding` | month 2025-12 | 4 | no |
| `ed_fsa.federally_managed_idr_by_partial_financial_hardship.fy2026_q1.recipients` | month 2025-12 | 4 | no |
| `ed_fsa.federally_managed_idr_by_partial_financial_hardship.fy2026_q2.dollars_outstanding` | month 2026-03 | 4 | no |
| `ed_fsa.federally_managed_idr_by_partial_financial_hardship.fy2026_q2.recipients` | month 2026-03 | 4 | no |
| `ed_fsa.federally_managed_idr_by_partial_financial_hardship.fy2026_q3.dollars_outstanding` | month 2026-06 | 4 | no |
| `ed_fsa.federally_managed_idr_by_partial_financial_hardship.fy2026_q3.recipients` | month 2026-06 | 4 | no |
| **`packages/ed_fsa/portfolio_by_age_fy2026_q2`** | | **24** | |
| `ed_fsa.portfolio_by_age.fy2026_q1.borrowers` | month 2025-12 | 6 | yes |
| `ed_fsa.portfolio_by_age.fy2026_q1.dollars_outstanding` | month 2025-12 | 6 | yes |
| `ed_fsa.portfolio_by_age.fy2026_q2.borrowers` | month 2026-03 | 6 | yes |
| `ed_fsa.portfolio_by_age.fy2026_q2.dollars_outstanding` | month 2026-03 | 6 | yes |
| **`packages/ed_fsa/portfolio_by_debt_size_fy2026_q2`** | | **36** | |
| `ed_fsa.portfolio_by_debt_size.fy2026_q1.borrowers` | month 2025-12 | 9 | yes |
| `ed_fsa.portfolio_by_debt_size.fy2026_q1.dollars_outstanding` | month 2025-12 | 9 | yes |
| `ed_fsa.portfolio_by_debt_size.fy2026_q2.borrowers` | month 2026-03 | 9 | yes |
| `ed_fsa.portfolio_by_debt_size.fy2026_q2.dollars_outstanding` | month 2026-03 | 9 | yes |
| **`packages/ed_fsa/portfolio_by_loan_type_fy2026_q3`** | | **42** | |
| `ed_fsa.portfolio_by_loan_type.fy2026_q1.dollars_outstanding` | month 2025-12 | 6 | yes |
| `ed_fsa.portfolio_by_loan_type.fy2026_q1.recipients` | month 2025-12 | 6 | yes |
| `ed_fsa.portfolio_by_loan_type.fy2026_q1.stafford_combined_dollars_outstanding` | month 2025-12 | 1 | yes |
| `ed_fsa.portfolio_by_loan_type.fy2026_q1.stafford_combined_unique_recipients` | month 2025-12 | 1 | yes |
| `ed_fsa.portfolio_by_loan_type.fy2026_q2.dollars_outstanding` | month 2026-03 | 6 | yes |
| `ed_fsa.portfolio_by_loan_type.fy2026_q2.recipients` | month 2026-03 | 6 | yes |
| `ed_fsa.portfolio_by_loan_type.fy2026_q2.stafford_combined_dollars_outstanding` | month 2026-03 | 1 | yes |
| `ed_fsa.portfolio_by_loan_type.fy2026_q2.stafford_combined_unique_recipients` | month 2026-03 | 1 | yes |
| `ed_fsa.portfolio_by_loan_type.fy2026_q3.dollars_outstanding` | month 2026-06 | 6 | yes |
| `ed_fsa.portfolio_by_loan_type.fy2026_q3.recipients` | month 2026-06 | 6 | yes |
| `ed_fsa.portfolio_by_loan_type.fy2026_q3.stafford_combined_dollars_outstanding` | month 2026-06 | 1 | yes |
| `ed_fsa.portfolio_by_loan_type.fy2026_q3.stafford_combined_unique_recipients` | month 2026-06 | 1 | yes |
| **`packages/ed_fsa/portfolio_by_location_fy2026_q2`** | | **108** | |
| `ed_fsa.portfolio_by_location.2026_03_31` | month 2026-03 | 108 | yes |
| **`packages/ed_fsa/portfolio_summary_fy2026_q3`** | | **24** | |
| `ed_fsa.portfolio_summary.fy2026_q1.dollars_outstanding` | month 2025-12 | 4 | yes |
| `ed_fsa.portfolio_summary.fy2026_q1.recipients` | month 2025-12 | 3 | yes |
| `ed_fsa.portfolio_summary.fy2026_q1.unduplicated_recipients` | month 2025-12 | 1 | yes |
| `ed_fsa.portfolio_summary.fy2026_q2.dollars_outstanding` | month 2026-03 | 4 | yes |
| `ed_fsa.portfolio_summary.fy2026_q2.recipients` | month 2026-03 | 3 | yes |
| `ed_fsa.portfolio_summary.fy2026_q2.unduplicated_recipients` | month 2026-03 | 1 | yes |
| `ed_fsa.portfolio_summary.fy2026_q3.dollars_outstanding` | month 2026-06 | 4 | yes |
| `ed_fsa.portfolio_summary.fy2026_q3.recipients` | month 2026-06 | 3 | yes |
| `ed_fsa.portfolio_summary.fy2026_q3.unduplicated_recipients` | month 2026-06 | 1 | yes |
| **total** | | **461** | 244 rows in 31 pairs |

### Against #1357's fixture

The fixture at #1357's head `0ff293b1a335a29d46f1598f2039beffa242e632` is
`packages/microcosm-build/tests/fixtures/us_fsa_portfolio_chronicle_347_facts.jsonl.gz`:
50,445 bytes, sha256 `9faed0e3…`. Gunzipped it is 244 lines, 1,300,986 bytes,
sha256 `424e1d35…`, all `chronicle.consumer_fact.v4`.

- **Byte for byte: none of its 244 rows appears among mine.**
- **The rows that differ: all 244, and only in `schema_version`.** Each
  fixture row matches one of mine on `aggregate_fact_key` (244 of 244). The
  parsed rows differ in exactly one field: `schema_version`, `v4` in the
  fixture and `v3` in mine. Rewriting my line's
  `"schema_version": "chronicle.consumer_fact.v3"` to `…v4` makes all 244
  lines byte-identical to the fixture's.
- **The rows it lacks: 217 of my 461, in 35 whole pairs**, all from
  `packages/ed_fsa/dl_portfolio_by_repayment_plan_fy2026_q3`: every pair of
  that package except `ed_fsa.dl_by_repayment_plan.fy2026_q2.dollars_outstanding`.
  The fixture holds that pair's 10 rows, and its 31 pairs are whole: every
  pair of the other five packages, plus that one. The table above marks each
  pair.
- **Reference build at `acbedb5`:** the six packages built there give 461
  rows, all v4. The fixture's 244 lines are byte-identical to 244 of them, as
  the brief says. They have the same 461 `aggregate_fact_key`s as mine, and
  each of my rows equals its `acbedb5` row once its stamp reads v4. So the
  217 rows the fixture lacks also match #347 apart from the stamp.

## 6. Judgment calls

1. **66 pairs, not 6** (section 3). The brief says to add all the pairs I find.
2. **I did not stop over v3 against v4.** The brief says to stop if the
   packages *need* code that only later commits carry. They don't: they load,
   validate, pass their own 28 tests, and build valid at the cut. The schema
   stamp is the cut exporter's one constant, not something the packages ask
   for. I pulled nothing in, built the feed, and set out above what v4 would
   take. Whether the pin accepts v3 FSA rows or waits for a v4 base is the
   hub's call.
3. **I built the six packages at `acbedb5` as well** (a throwaway worktree,
   `chronicle build-bundle --year 2026` over the six alone). The brief does
   not ask for it, but it is the only way to tell whether the 217 rows the
   fixture lacks also match #347, and to check that the fixture is
   `acbedb5`'s export. Both held (section 5).
4. **The conflict resolution kept the base's numbers** in the bundle test
   (section 1) and did not "fix" the three stale ones. The brief says to take
   `a9026cc`'s lines and add only #347's. Updating 217, 339,948 and 171 would
   have been a change of my own to the base's test.
5. **The rule text.** I added one clause in the style of the existing ones
   rather than rewriting the rule. The doc also states the build-year rule, and
   the clause states the year the pairs are built at.
6. **How the builder ran.** I ran `uv run --no-project python -I
   <builder> ...` from an empty scratch directory, rather than the brief's
   `uv run python <builder>` from a microcosm checkout, which this session
   does not have. `--no-project` and `-I` keep any project or stray module
   out of the builder's imports. It imports only the standard library when
   `--scope` is given.
7. **Two extra test files** (section 2) because the cherry-pick extends the
   alias map. Both passed. I did not run the rest of the suite.
8. **Commit trailers.** The cut's message ends with `Co-Authored-By: Claude
   Opus 5.5 <noreply@anthropic.com>`, as the brief asks. The session link
   trailer sits just above it. The original commit's own `Co-Authored-By`
   line stays where it was in the copied message.
9. **The ACS S1501 package came with the cherry-pick** and stays out of the
   scope. The brief's scope covers only `packages/ed_fsa`.
10. **Disk.** The whole-year 2023 bundle test needs more disk than this
    session's allowance holds, and my first runs of the test and the build
    shared the disk and both died of it. That was my mistake: I should have
    run them one at a time. I reran both, each beside a janitor that deletes
    only files the code reads no more (sections 2 and 4). Neither janitor
    changes code, the test, the scope or the builder. Both log what they
    deleted, and neither touches a `consumer_facts.jsonl`.
11. **I pushed the cut although `tests/test_chronicle_bundle.py` fails.** The
    brief says to push after its tests pass. On this base that test cannot
    pass without editing counts beyond #347's lines, which the brief also
    forbids. So I ran the same file at `a9026cc` before pushing. It fails
    there on the same assert with the same counts, and the two 2023 bundles
    differ only by the seven skipped sources (section 2). The cherry-pick
    adds no failure. I pushed once, after that. An unpushed cut would leave
    the feed's `source_commit` unreachable on GitHub. If the hub would rather not use a
    cut whose bundle test fails, the fix belongs on the base: update the three
    counts that the base's own commits left stale. It is not part of this cut.

## Files in this directory

| File | What | Bytes | sha256 |
|---|---|---|---|
| `NOTES.md` | these notes | | |
| `chronicle_feed_scope.json` | the scope, byte for byte as the build used it (the receipt's `scope_sha256`) | 202,080 | `73a39c166a8f78c8a8a1ae711515e5d2e6b76a74952e67d7783cf974a4615633` |
| `receipt.json` | the builder's receipt | 10,300 | `366cc29ba690934fffa6b0e1aec3f81ac0ca474087819d8cdbcdce4f9a8b6067` |
| `ed_fsa_rows.jsonl` | the 66 new pairs' 461 rows, in feed order, as they sit in the feed | 2,604,985 | `afcdea5a8ed606d97992548806628590ece1f5d4c19f767ef252f361b9b106de` |
| `consumer_facts.jsonl.gz` | the whole feed through `gzip -n -9` (under 90 MB) | **19,454,590** | `ffd1258734c68d8f85fb5408b77592e81ef732d78e196e90aeae552deca71b6f` |

`gzip -dc consumer_facts.jsonl.gz` gives 171,661,396 bytes with sha256
`1d45a89c…`, the receipt's `facts_sha256`. I checked this with `cmp` against
the built file.

The scripts this session wrote stay in its scratch space and are not
committed. They are described where they are used: the scope edit
(section 3), the checks (section 5) and the two disk janitors (sections 2
and 4).
