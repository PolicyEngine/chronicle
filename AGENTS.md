# Chronicle Agent Rules

Chronicle is a source-backed fact store. It may parse publisher artifacts, normalize
representation, and preserve provenance. Selection and measurement contracts live
in consumers such as Microcosm.

Every fact value must trace to a publisher. The boundary is who asserted the
value, not level versus projection: a government's own projection (CBO
baseline, BFP outlook, SSA trustees) is a fact typed
`assertion: source_projection`. PolicyEngine-computed values — aged, uprated,
forecast, or reconciled levels — are never Chronicle facts.

Chronicle holds government-produced records only. Before adding a source
folder or package, confirm the publisher is part of a government and add or
update its entry in `docs/source-publishers.yaml`; `tests/test_source_publishers.py`
fails on an unclassified folder or a new non-government one. Do not add
records from trade associations, charities, think tanks, universities,
firms, or aggregators that republish government data: take the series from
the government publisher instead. Comparisons against outside scores belong
in PolicyEngine/policyengine-scorecard, not here. Edge cases (central banks,
regulators, public corporations, intergovernmental bodies, government records
on a third-party host) follow the 2026-10-21 amendment in
`docs/adr-chronicle-facts-only.md`.

Do not put Microcosm work in Chronicle:

- no cross-source reconciliation
- no aging to a build year
- no imputation
- no support-aware target activation
- no solver-ready target construction
- no target profiles or model-measurement bindings
- no PolicyEngine-computed values stored as facts

Chronicle records every fact's publisher reference period. Consumers own and
enforce any declaration that aligns those facts to another period; Chronicle
returns the published level and never an aligned number.

Only approved Chronicle agent roles in `.github/chronicle-agents.yml` should add or
modify source packages or contract schemas. Source-data PRs
need deterministic validation plus the listed Chronicle judge reviews before merge.
