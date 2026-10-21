# ADR: Chronicle is a facts-only store

Status: accepted 2026-07-02 (supersedes the facts-plus-projections split
originally proposed in issue #71); amended 2026-10-21 to admit
government-produced records only (see the amendment at the end)

## Decision

Chronicle stores source-published values only. The boundary is **who asserted
the value**, not level versus projection:

1. Anything a publisher asserted is a fact — including the publisher's own
   projections. "CBO's January 2026 baseline projects individual income tax
   receipts of $X in 2027" is a source-backed claim with lineage, exactly
   like an SOI observation. These facts carry
   `assertion: source_projection`; measured or administered outcomes carry
   the default `assertion: observation`.
2. Anything PolicyEngine computed — an aged, uprated, forecast, or
   reconciled level — is never a Chronicle object. Such values are regenerable
   build artifacts and live in the consumer (Microcosm calibration owns
   aging), implemented as named, versioned models that consume growth-factor
   facts from Chronicle and emit their own lineage.

Instead of projection objects, Chronicle contributes two guarantees:

- **Reference-period semantics.** `PeriodDimension` identifies the period a
  value refers to; `PeriodCoverage` records non-identity provenance (start
  and end dates, basis, the publisher's period label, accounting basis) for
  cases like BE-SILC incomes that reference the year before the survey
  label.
- **Facts-only consumer artifacts.** Chronicle publishes schema-validated fact
  rows with manifest hashes. Consumers own the selection, measurement,
  period-alignment, and model-binding contracts that interpret those rows. The
  facts-only artifact is `policyengine_ledger.consumer_artifact.v2`; the version
  bump makes the removal of v1's embedded profiles and resolution surface an
  explicit incompatible transition.

## Why not facts plus projections in one schema

- **Thesis stays clean.** Thesis resolves forecasts against Chronicle facts as
  official observations. If the store held PolicyEngine-computed
  projections, a forecast could be scored against partly-model output —
  circular. A facts-only store is a model-free resolution substrate.
- **Append-only stays meaningful.** Facts never churn. PolicyEngine-computed
  projections would churn on every CBO update and every aging-model version
  bump, turning an auditable chronicle into a store of volatile derivations.
- **The consumer set does not need it.** Thesis does not want
  PolicyEngine-computed aging; a government's own estimates are
  source-published and therefore facts; the only consumer of
  PolicyEngine-computed aged values is Microcosm calibration, so that is
  where the code belongs (PolicyEngine/microcosm#116).
- **The microcosm#212 lesson is a contract lesson.** The failure was not
  where aging lived; it was that un-aged consumption was silent — SOI
  TY2022/23 dollar levels calibrated exactly at 2024 while simulated 2025
  aggregates ran ~6–10% under current-year projections. The fix is making
  silent period mismatch impossible, which is a consumption-contract
  property, not a projection-object property.

## Consequences

- The `assertion` field enters canonical key payloads only when it is not
  the default, so every pre-existing observation fact keeps byte-identical
  v1 and v2 keys and byte-identical JSONL serialization.
- Source packages declare `assertion` and `period_coverage` per record set;
  values other than `observation` and `source_projection` fail validation
  with an error explaining that PolicyEngine-computed values are not facts.
- Consumer-contract rows always carry `assertion` explicitly, and the
  consumer artifact (`chronicle build-consumer-artifact`) contains only fact
  rows and the manifest hashes needed to verify them. Microcosm packages its
  own selection contracts and builds its target registry without Chronicle
  profiles (issues #166 and #172).
- The retired `policyengine_ledger.target_profile.v1` and
  `policyengine_ledger.resolved_target.v1` schema IDs have no v2 successor in
  issue #143. The Chronicle-side Belgian profile plan in issue #70 is
  superseded; Belgian contracts also live consumer-side.
- Geography vintage translation (microcosm#205) follows the same pattern: a
  declared consumer-side transform over facts, never an edit to them.

## Amendment 2026-10-21: government-produced records only

Chronicle admits a record only when a government produced it. The publisher
that asserted the value must be part of a national, subnational, or
supranational government: a legislature or one of its offices (CBO, JCT), a
ministry or department and its agencies (DWP, HMRC, the IRS), a statistics
office (ONS, Statbel, Stats NZ), or a public body that a government set up to
publish official figures (OBR, the Federal Planning Bureau). Government
estimates of a policy change, such as JCT revenue estimates, are government
records like any other.

- Records from trade associations, charities, think tanks, universities,
  firms, and secondary aggregators are not Chronicle facts, however reliable.
  When an aggregator republishes a government series, Chronicle takes the
  series from the government publisher.
- Comparisons of PolicyEngine estimates against outside scores and analyses
  live in the separate scorecard (PolicyEngine/policyengine-scorecard), which
  keeps its own provenance. This amendment removed TPC from the source
  projection examples in this ADR, the README, AGENTS.md, the governance doc,
  and the `AggregateFact` docstring: TPC is not a government publisher, and
  Chronicle never held a TPC package.
- The rule turns on who produced a record, not where it was fetched. A
  government record that reached Chronicle through a third-party host keeps
  the government as its publisher.
- `docs/source-publishers.yaml` names the publisher of every source folder and
  classifies it; `tests/test_source_publishers.py` fails when a folder is
  unclassified or a new non-government folder appears.

### Edge cases (proposed treatment, awaiting a ruling)

Until a ruling, existing packages in these categories stay as they are.

| Category | Where | Proposed treatment | Basis |
|---|---|---|---|
| Central banks | `nbb`, `federal_reserve`; central-bank rows in the Thesis observation journal (`codex/thesis-ledger-facts`: Bank of England, ECB, Bank of Japan, Reserve Bank of Australia, Bank of Canada, Federal Reserve) | In, for statistics and policy decisions they publish under a public mandate | The Belgian State holds half of the NBB's shares, and the NBB compiles Belgium's national accounts on behalf of the National Accounts Institute; the Federal Reserve Board is a federal agency |
| Regulators | `ofgem`, `orr` | In | GOV.UK lists both as non-ministerial departments |
| Public corporations and other public bodies | `nithc`, `slc` | In, for records of their own statutory functions | NITHC (Translink) is a public corporation set up under the Transport Act (Northern Ireland) 1967 and wholly owned by government; GOV.UK lists SLC as an executive non-departmental public body |
| Intergovernmental bodies | `eurostat`, `jrc` | In | Both are directorates-general of the European Commission |
| Government records on a third-party host | `dwp/pip_daily_living_foi_2025` (a DWP FOI reply on WhatDoTheyKnow); NRS census tables mirrored by the UK Data Service; `welshgov/brma_boundaries_2012` (University of Edinburgh DataShare); `treasury/an24_01_fiscal_totals` (the NZ Treasury Analytics & Insights GitHub organisation); journal rows fetched through ALFRED or the Internet Archive | In, with the government named as publisher; prefer the government-hosted copy when one exists | The producer decides, not the host |
| Government-funded work published by others | None today | Out, unless a government body publishes it under its own name | A university or contractor is then the publisher |

### Packages that do not meet the rule

These predate the amendment. Each stays until its migration is ruled on, so
no consumer loses a fact before a replacement exists.

| Folder | Publisher | Government replacement |
|---|---|---|
| `isc` (`isc-annual-census-2023` to `isc-annual-census-2026`) | Independent Schools Council, the umbrella body for UK independent-school associations | DfE *Schools, pupils and their characteristics*, which counts independent-school pupils in England (all independent schools, not ISC members only) |
| `ici` (`ici-fact-book-table-30`) | Investment Company Institute, the trade association of US regulated funds | IRS SOI Table 1.4 capital gain distributions, already in Chronicle (a narrower concept: distributions reported on Form 1040) |
| `kff` (`kff-marketplace-effectuated-enrollment`) | KFF, a nonprofit; this table republishes CMS data | CMS effectuated enrollment reports; Chronicle already holds the 2022 edition (`cms_aca/effectuated_enrollment_2022`) |

Two smaller items fall under the same rule: `db/pe_source_inventory.py` lists
a Disability Rights UK news page under `source_id: dwp` and the ISC census
page as source artifacts, and the curated Statbel NIS 2025 crosswalk
(`statbel/nis_2025_commune_crosswalk`) cites publisys.eu next to Statbel's
REFNIS file.
