Retire the legacy `db/etl_soi_state.py`, `db/etl_soi_credits.py`,
`db/etl_soi_deductions.py` and `db/etl_soi_income_sources.py` loaders and their
`chronicle load soi-state | soi-credits | soi-deductions | soi-income-sources`
sources. They wrote invented state values (fixed amounts per claim, digit runs,
population-scaled splits) under IRS source URLs; 6 of 1,581 state values for
2021 are within 0.5% of IRS Historic Table 2 for that year. Where the
publisher's values now live is recorded in `docs/us-legacy-etl-cleanup.md`.
