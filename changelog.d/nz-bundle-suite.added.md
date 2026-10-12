Add `chronicle build-bundle --suite nz`, a curated New Zealand bundle suite for
Microcosm's NZ feed. It builds all 48 packages under `packages/ird`,
`packages/mbie`, `packages/msd`, `packages/stats_nz` and `packages/treasury`,
including the 36 national, regional-council and area-outside-region Census
2023 place-summary packages. A drift guard fails when an alias under those
directories is added or dropped without updating the
suite. Like `--suite uk`, it refuses `--source`, and `--year` does not change
what it builds because every NZ package pins its artifact year.
