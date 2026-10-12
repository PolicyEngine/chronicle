# Catalog curation backlog

## Entity-drift families: folded 2026-10-12

Seven series each held two observed lineages because their hand-recorded
May 2026 rows carry a bespoke entity while every resolver print carries
`economy/aggregate`, the default entity the Thesis resolver writes. The
catalog builder scopes concept and alias inheritance to one geography and
entity slice, so curating an alias could not join them: on 2026-08-07 a
disposable-copy experiment deleted the unpinned row and aliased its concept
on the docket-pinned row, and regeneration restored both rows byte for
byte. The same experiment was repeated on 2026-09-22 with the same result.

Max ruled on 2026-09-27 (d353) that the `economy/aggregate` lineage
survives for all seven. The builder gained curated entity folds
(`ledger/seeds/entity_folds.json`, described in the
`build_series_catalog.py` module docstring): before identities are grouped,
a fold reads the absorbed entity's current rows as carrying the survivor
entity, without changing the observation file. Regenerating with the seven
folds retired seven bindings and kept every survivor's UUID; the catalog
went from 228 to 221 series and the observed `observation_count` still sums
to the 233 current rows.

| Concept | Survivor (`economy/aggregate`) | Retired |
| --- | --- | --- |
| `bls.cpi.u.headline_mom` | `70ca2ecf-4323-4453-b42f-23350cb95f22` | `household/cpi_u_all_items`, `3e796803-a194-4c83-9dc9-27cc870ff08e` |
| `bls.cpi.u.core_mom` | `e5e402d5-1a65-4c5d-a67a-07e3cf03cbf8` | `household/cpi_u_less_food_energy`, `d85c3c7f-874b-4caa-bfad-1ec7a473c293` |
| `bls.cps.unemployment_rate` | `db2f3857-e0fa-48f8-9ab1-6c8989307fd2` | `person/civilian_labor_force`, `8dbbd54f-4bfd-4735-ad0d-5b55b8bb4ec5` |
| `fed.g17.industrial_production.total_index_mom` | `dbfd5050-e5df-40af-8922-dc8927d6363a` | `institutional_sector/total_industrial_production`, `d5634fc4-dbe0-4203-a5b7-728708b85a14` (its folded `us.frb` spelling joins too) |
| `fed.g17.capacity_utilization.total_industry` | `9668ecdb-5f61-422d-a653-8e8956257ade` | `institutional_sector/total_industry_capacity`, `978252a9-c452-41eb-aece-323340e796fc` |
| `census.housing_starts.saar` | `8c999902-84e2-4e90-b49c-325cd535062a` | `dwelling/housing_start`, `d0212a1e-b360-460a-80a8-1cf4ad5ce427` (its folded `us.census` spelling joins too) |
| `bls.import_price_index.all_imports_mom` | `1d271205-0e71-4a74-9d5f-47e77577e2b2` | `household/all_imports`, `e8e6e43e-2c46-4620-a070-91d2da004b1c` |

Three of these were docket-pinned to the retired lineage
(`bls.cps.unemployment_rate`, `bls.cpi.u.headline_mom`,
`bls.cpi.u.core_mom`); Thesis re-stamps those pins in the same rollout.

Two more concepts still hold sibling lineages and were not folded:
`bls.ces.total_nonfarm_payroll_change` (`person/nonfarm_payroll_employee`
from May beside `economy/aggregate` from June; the Thesis docket observes a
third concept, `bls.ces.nonfarm_payrolls.change`) and
`statcan.employment_insurance.regular_beneficiaries.canada` (two
hand-chosen person roles, April and May). Fold them with a seed entry and
a reviewed regeneration if a consumer ever needs one lineage.

To undo a fold, remove its entry from the seed's `folds` list and
regenerate: the absorbed identity revives with its original UUID. The
names the fold moved onto the survivor's `aliases` stay there as curated
memory; remove them by hand if they should go. Never delete the seed file
while the committed catalog declares `entity_folds_sha256`; the builder
refuses that, because it would split the lineages silently.

## Initial claims cadence metadata

The `us.dol.initial_claims.sa` rows are one weekly series, not a legitimate
weekly/monthly aggregate split. The two observations declared as monthly
carry week-ending identifiers (`2026-06-06` and `2026-06-13`) and values in
weekly thousands, immediately preceding the weekly observations beginning
`2026-06-20`. After folding their two concept spellings, they remain on
`person/ui_initial_claimant` with monthly cadence under UUID
`830e68bb-9ed6-493c-a8a4-440ba8e53f76`; the docket-pinned weekly rows remain
on `person/ui_claimant` under UUID
`1ad67747-d9d8-4ff9-9ebc-58206e658518`. Correct the two upstream rows'
period and entity metadata before folding these lineages; an alias cannot
bridge either mismatch safely.

## Builder polish

The two LOW residuals accepted in the chronicle#145 merge disposition
were closed on 2026-08-09 by chronicle#153:

- `_plan_enrichment` now verifies the live binding owns the catalog
  row's UUID (`registry.binding(prior_own_key) == row_uuid`) instead of
  inferring ownership from the historical first-owner map plus key
  liveness. A stale catalog row carrying a UUID its key superseded away
  from fails at plan time with the UUID-reuse ceremony diagnostic;
  previously the invalid retire + succeeds plan was only rejected later,
  by staging replay. Builder output for valid states is byte-unchanged.
- The previously untested state — a stale catalog UUID after the same
  placeholder key was superseded — is pinned by two regressions: staging
  replay rejects the hand-forged plan before any write reaches disk, and
  the builder end-to-end refuses the stale catalog, leaving both
  artifacts untouched.

## Country geography on Colorado-scoped concepts, and one raw series id (2026-09-04)

Three concepts minted by the 2026-08-23 first-print wave (c2aa68d, manifest
0015-fdcfd0e570214f6b) name Colorado in the concept string while their rows
carry country-level geography copied from the observation payload
(`{"level": "country", "id": "0100000US", "vintage": "current"}`):
`bls.laus.colorado.labor_force` (d496bea3), `ssa.ssi.recipients.colorado`
(5e368043) and `ssa.ssi.recipients.colorado.aged_65_plus` (2cb31293). The
ledger already records state geography elsewhere (for example the SNAP payment
error rate observation for Colorado, `0400000US08`), so the scope belongs in
the geography, not the name. The same wave minted `bls.cps.LNU02374597`
(34af6867) under the raw BLS series id, recorded deliberately by the adapter
(`concept_relation: source_label`) where the other 227 rows use lowercase
slugs; the catalog flags it as a suspect segment and the test pins it as the
one expected suspect.

Neither is wrong data, and neither changes what the derived pins must be.
The correction path for either is an appended observation with
`assertionVersion.supersedes`, never an in-place edit of a released row: all
four rows sit under signed, timestamped manifests 0015 to 0020.
