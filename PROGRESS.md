# Progress: chronicle#179 passive pass-through anchors

## State

Complete. Both source ingestions, repository-wide snapshots, changelog, and
final validation are finished on branch `passive-pass-through-anchors` in
`.claude/worktrees/passive-179`.

## Done

- Read the applicable repository instructions in `AGENTS.md` and the parent
  `CLAUDE.md`.
- Confirmed that the existing `irs_soi.table_1_4` package already pins the
  supplied TY2023 workbook, so this task will extend that package rather than
  duplicate it.
- Mapped record-set, fact, provenance, source-identity, test, and changelog
  conventions; the repository has no Makefile or established changelog file.
- Added `soi-form-8960-2023`: 10 tax-year record sets and 20 administrative
  facts (return count plus USD amount for each requested line), pinned to
  Publication 4801 (Rev. 6-2026) and its supervisor-verified transcripts.
- Added source-level tests for every Form 8960 value, unit, provenance pin, and
  the published one-$1,000 line 4 rounding residual.
- Passed the focused tests (10 tests), source-package validation, and the full
  Form 8960 source-suite build (20 consumer facts; all reports valid).
- Extended the existing `irs_soi.ty2023.table_1_4` record set with partnership
  and S-corporation net-income/net-loss return counts and amounts across all 20
  AGI classes (160 new facts); the existing estate/trust measures remain intact.
- Added strict per-measure year scoping so TY2020 retains its combined
  partnership/S-corporation layout while TY2021 through TY2023 ingest the
  separately published lines.
- Passed Table 1.4 source-package compilation for TY2020 and TY2023, focused
  package/suite tests, Ruff checks, and full fact builds for TY2020 through
  TY2023 (580 facts in 2020; 740 facts in each later year).
- Ran the full 651-test suite once: 649 passed, one skipped, and the sole
  failure was the expected stale merged-bundle count snapshot. Updated that
  snapshot from the generated bundle's exact coverage report (+180 facts and
  +1 source package).
- Rebuilt the canonical merged bundle after the snapshot update; its complete
  aggregate-contract test passed (1 test in 12m31s).
- Added the required functional-change fragment at
  `changelog.d/179.added.md`, following the parent repository convention.
- Passed the final repository-wide checks: Ruff; 67 targeted governance,
  boundary, facts-only, consumer-contract, alias, and Form tests; both package
  validators and source-suite builds; and the full suite with 650 passed, one
  skipped, and no failures.
- Wrote the requested handoff, record-set/fact inventory, exact Microcosm
  concept IDs, and check results to `FINAL_REPORT.md`.

## Next

- No implementation work remains. The branch is ready for supervisor review.
