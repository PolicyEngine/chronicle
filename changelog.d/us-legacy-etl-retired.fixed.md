Retire 12 of the 14 US legacy `db/etl_*.py` loaders and their `chronicle load`
sources, keeping only `etl_soi.py` and `etl_snap.py`, which read checksummed
publisher artifacts. The four state SOI loaders wrote invented values (fixed
amounts per claim, digit runs, population-scaled splits) under IRS source URLs:
6 of 1,581 state values for 2021 are within 0.5% of IRS Historic Table 2. The
ACA, BLS, CBO, Census, CPS, Medicaid, SSA and SSI loaders mixed transcribed,
rounded, computed and invented numbers with no artifact behind them.
`docs/us-legacy-etl-cleanup.md` records the evidence and where each series is
now published, and a boundary test requires every row `chronicle load all`
writes to equal a fact built from a checksummed publisher file.
