Route `packages/treasury` and `db/data/treasury` to the `raw/nz` and
`derived/nz` R2 prefixes, so `verify-raw` and `publish-raw` compute the
`raw/nz/treasury/...` keys the two NZ Treasury manifests declare instead of
`raw/treasury/...`.
