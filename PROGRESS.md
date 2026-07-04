# PROGRESS: ledger hygiene fixes (#77/#78/#79)

Executed by general-purpose subagent per Fable lead session direction.
Using pre-existing worktrees/branches (found already staged at origin/main tip,
one per issue): fix/etl-snap-fabricated-data (#77), fix/build-bundle-alias-drift (#78),
fix/source-package-label-year-keys (#79). Three separate PRs (branches were already
split this way, and the three fixes touch unrelated files/modules).

Protected branch codex/thesis-ledger-facts: NOT touched, confirmed untouched.

## Status
- [ ] #77 etl_snap.py SNAP_DATA — investigate dead/live, then fix
- [ ] #78 build-bundle alias drift — fix + TDD loud-failure test
- [ ] #79 source_package.py string year keys — fix + test both paths
- [ ] Full test suite green (pipefail-verified)
- [ ] PRs opened (not merged)
