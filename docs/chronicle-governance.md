# Chronicle Contribution Governance

Chronicle is the source-of-truth layer for PolicyEngine government-statistics
release facts. Its job is to preserve publisher-backed facts with provenance.
Microcosm turns those facts into active, aged, reconciled calibration targets.

## Boundary

The store is facts-only, and the line is who asserted the value, not level
versus projection. A government's own forward-looking estimate — a CBO
baseline, a BFP outlook, an SSA trustees table — is a source-backed claim
like any other and enters Chronicle as a fact typed
`assertion: source_projection`. A value PolicyEngine computed — an aged,
uprated, forecast, or reconciled level — is never a fact, whatever object it
hides in. This keeps three properties intact: every value in Chronicle traces to
a publisher; facts never churn when models update, so append-only audit stays
meaningful; and Thesis can resolve forecasts against Chronicle observations
without scoring model output against model output.

Chronicle may:

- register raw publisher artifacts and checksums
- parse source rows and cells
- emit source-backed aggregate facts, including publisher projections typed
  `assertion: source_projection`
- record period-coverage provenance (reference period start/end, basis,
  source period label, accounting basis) for facts whose reference period
  needs disambiguation
- normalize representation, such as units, scales, dates, geography IDs, and
  same-source total/share arithmetic when the publisher defines that relation

Chronicle must not:

- hold records that a non-government publisher produced (a trade
  association, charity, think tank, university, firm, or an aggregator that
  republishes government data); every source folder's publisher is named and
  classified in `docs/source-publishers.yaml`, and edge cases follow the
  2026-10-21 amendment to `docs/adr-chronicle-facts-only.md`
- reconcile across sources
- age facts to a build year
- store PolicyEngine-computed values (aged, uprated, forecast, or reconciled
  levels) as facts or in any other store object
- compute aligned values; it publishes the source period and value unchanged
- impute missing values
- store raw survey or administrative microdata
- own selection, measurement, period-alignment, or model-binding contracts
- choose a support-aware active target subset
- build solver-ready calibration targets
- invent derived facts whose source is Chronicle itself

## Approval Model

The repository uses `.github/CODEOWNERS` to route all changes through
`@PolicyEngine/core-developers`. Branch protection should require code-owner
review.

Approved agent roles live in `.github/chronicle-agents.yml`. Contributions that
touch source packages or consumer contracts should name the
agent role used and attach the required deterministic checks and judge verdicts.

## Judge Model

Chronicle follows the Axiom pattern: deterministic checks run first, then specialist
reviewers judge the source-data boundary with that evidence. The required judge
types are:

- `ledger-source-fidelity`
- `ledger-contract`
- `ledger-boundary`

The overall verdict fails if any required judge fails. A judge must fail if a
change moves reconciliation, aging, imputation, active target selection, or
solver construction from Microcosm into Chronicle, or stores a
PolicyEngine-computed value as a fact.
