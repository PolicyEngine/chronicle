# Eurostat annual USD per EUR/ECU exchange rates

This package preserves all 55 published cells in the staged Eurostat
`ert_bil_eur_a` JSON-stat response: annual averages for 1971–2025, including
2024 at **1.0824 USD per EUR**. Eurostat publishes the modern euro series from
ECB reference rates. The publisher's historical Euro/ECU series is retained
under its original years; earlier observations are not relabeled as ECB euro
reference rates.

The source codes are `freq=A`, `statinfo=AVG`, `unit=NAC` (National currency),
and `currency=USD`. The fact unit `usd_per_eur` records the published direction
(US dollars per one euro/ECU); scale is 1. `mean` describes the publisher's
annual average. Each fact reads a single value without inversion, rescaling,
or recomputing the average.

There is no country or institutional-sector axis in the response. The harness
represents this market rate with statistical scope `eurostat:ert_bil_eur_a:USD`
and entity `institutional_sector`, role `currency_market`; these are technical
representations, not additional publisher dimensions. The measurement basis
is `administrative` and the assertion is `observation`.

The capture was retrieved on 2026-10-23; Eurostat's dataset update timestamp
is `2026-07-08T11:00:00+0200`. The manifest pins the 4,488 original bytes with
SHA-256 `3c96ca57c15266d07e1976d90ba806a5bb90ab46a503b6311df3aaa9f5ba66c7`.
Its 2026 artifact entry pins this release, while facts retain their publisher
calendar years at every build year. New bytes at the API URL require a new
vintage. Reuse follows Eurostat's CC BY 4.0 policy with source acknowledgement.
The manifest declares a content-addressed `ledger-raw` R2 key for the Belgium
session to upload after review; this lane has not uploaded it.

For year `y`, its JSON-stat source index is the value of
`dimension.time.category.index[str(y)]`. The exact value locator is
`value[str(source_index)]`. The existing full-cube parser retains the index and
all five codes, plus publisher labels. On its `ert_bil_eur_a` sheet, the value
is column F, row `source_index + 2`; columns A–E are respectively `freq`,
`statinfo`, `unit`, `currency`, and `time`. Selectors guard all five codes and
the `value` column header. These normalized sheet coordinates are parser
locators; the original artifact is JSON, not a publisher spreadsheet.

Regenerate metadata and selectors from the immutable capture:

```sh
python packages/eurostat/ert_bil_eur_a_usd/build_package.py
chronicle validate-package eurostat-ert-bil-eur-a-usd --year 2023
chronicle build-suite eurostat-ert-bil-eur-a-usd --year 2023 --out /tmp/ert-bil-eur-a-usd --replace
```

The focused tests independently decode the JSON-stat positions and compare
publisher values with facts and their source-cell lineage. Consumer currency
bridges, year alignment, and policy calculations remain outside this package.
