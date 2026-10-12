# Catalog curation backlog

These series lineages remain split because the catalog builder scopes
concept and alias inheritance to an exact geography and entity slice.
Curating an alias cannot move an observation across entity keys, and the
catalog must not lose observations merely to present one lineage.

On 2026-08-07, a disposable-copy experiment attempted each entity-drift
fold by deleting the unpinned row and adding its canonical concept to the
docket-pinned row. Regeneration restored both rows and produced a catalog
and UUID registry byte-identical to the originals: all seven pairs still
held one observation on each entity. They must remain split until the
upstream observation metadata is corrected.

| Concept | Docket-pinned entity and UUID | Other entity and UUID | Blocker |
| --- | --- | --- | --- |
| `bls.cpi.u.headline_mom` | `household/cpi_u_all_items`, `3e796803-a194-4c83-9dc9-27cc870ff08e` | `economy/aggregate`, `70ca2ecf-4323-4453-b42f-23350cb95f22` | May and June observations disagree on entity. |
| `bls.cpi.u.core_mom` | `household/cpi_u_less_food_energy`, `d85c3c7f-874b-4caa-bfad-1ec7a473c293` | `economy/aggregate`, `e5e402d5-1a65-4c5d-a67a-07e3cf03cbf8` | May and June observations disagree on entity. |
| `bls.cps.unemployment_rate` | `person/civilian_labor_force`, `8dbbd54f-4bfd-4735-ad0d-5b55b8bb4ec5` | `economy/aggregate`, `db2f3857-e0fa-48f8-9ab1-6c8989307fd2` | May and June observations disagree on entity. |
| `fed.g17.industrial_production.total_index_mom` | `economy/aggregate`, `dbfd5050-e5df-40af-8922-dc8927d6363a` | `institutional_sector/total_industrial_production`, `d5634fc4-dbe0-4203-a5b7-728708b85a14` | May and June observations disagree on entity. The same-dimension `us.frb` spelling is folded into the latter row separately. |
| `fed.g17.capacity_utilization.total_industry` | `economy/aggregate`, `9668ecdb-5f61-422d-a653-8e8956257ade` | `institutional_sector/total_industry_capacity`, `978252a9-c452-41eb-aece-323340e796fc` | May and June observations disagree on entity. |
| `census.housing_starts.saar` | `economy/aggregate`, `8c999902-84e2-4e90-b49c-325cd535062a` | `dwelling/housing_start`, `d0212a1e-b360-460a-80a8-1cf4ad5ce427` | May and June observations disagree on entity. The same-dimension `us.census` spelling is folded into the latter row separately. |
| `bls.import_price_index.all_imports_mom` | `economy/aggregate`, `1d271205-0e71-4a74-9d5f-47e77577e2b2` | `household/all_imports`, `e8e6e43e-2c46-4620-a070-91d2da004b1c` | May and June observations disagree on entity. |

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

The same metadata explains two entries in the catalog's `stripped_segments`
that look like a naming bug: `week_2026-06-13` and `week_2026_06_13`. Both
come from the one 2026-06-13 row (ledger line 44), whose `source_record_id`
spells the week with ISO hyphens and whose `measure.concept` spells it with
underscores. The builder strips period tokens from both identifier fields
and records each distinct spelling, so the audit is right to list both. They
strip as `overlap`, not `derived`, because the row declares a month. Both
are recorded as reviewed overlap strips, each in its own field and shape, in
`tests/fixtures/series_catalog/reviewed_stripped_segments.json`. A
supersede correction that re-spells or re-periods that row will make the
audit report both as gone; the same change then updates the fixture.

## Reviewing period strips (2026-09-30, scoped by shape 2026-10-12)

`test_committed_catalog_is_current_and_valid` used to pin the exact list of
stripped period spellings, so every resolver append that recorded the next
weekly claims print failed the required "Arch checks" status, and the
resolver's admin merge went past it. The test now audits every strip against
the reviewed map in
`tests/fixtures/series_catalog/reviewed_stripped_segments.json`
(`build_series_catalog.stripped_segment_review_problems`).

A reviewed decision covers one canonical concept, one identifier field
(`measure.concept` or `source_record_id`) and one strip shape
(`build_series_catalog.strip_shape`). The shape is the field's family
pattern with each `{P}` written `{P:<template>}`, for example
`abs.cpi.all_groups.yoy.{P:9999_99}.first_print`. It fixes every kept
segment, where each stripped segment sits, and how it is spelled
(`period_spelling_template`). A strip passes without review only when its
concept already has a reviewed strip in the same field and the same shape
(the identifier differs from a reviewed one only in calendar values: the
next week or month, written the same way, in the same place) and every
current observation behind it spells its own declared period directly (kind
`derived`). The audit reports:

- a strip in a shape its concept has never stripped in, in that field: a new
  series, a new spelling template, a period spelled in a new field or
  position, a new kept segment (`.revised` beside `.first_print`), or a
  statute, cohort, or edition label that happens to spell its row's period;
- an unreviewed `overlap` strip, or a reviewed strip that gains the
  `overlap` kind;
- a reviewed strip that disappears from its field and shape.

The first version (2026-09-30) keyed decisions on concept and spelling
template only. The review of chronicle#309 showed why that was too loose: a
copy of the 2026-08 ABS CPI print moved to 2026-09 with the period also
spelled inside `measure.concept` (`abs.cpi.2026_09.all_groups.yoy`) folds
into the reviewed `abs.cpi.all_groups.yoy` identity under a new family
pattern, `abs.cpi.{P}.all_groups.yoy`. Its strip borrowed the approval of
the `source_record_id` period suffix. An unreviewed cohort or edition slot
must not inherit a decision about a different slot, so each decision now
names its field and shape.

To clear a report, decide whether the segment is the row's period. Then add
the strip to the fixture under the concept, field and shape the report
names, with its kinds, and add a note when the reason is not obvious. A
concept-spelling duplicate shows up here first: a docket placeholder such as
`abs.labour.unemployment_rate` taking its first print beside an
already-observed `abs.labour.unemployment_rate.australia` is a new concept
stripping for the first time.

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
