Five BEA packages now read BEA's newer releases in place (chronicle#449).
`bea-nipa-total-wages-salaries`, `bea-nipa-personal-income-components`,
`bea-nipa-personal-income-disposition` and `bea-nipa-pension-contributions`
read `NipaDataA.txt` as BEA served it after its 25 November 2026 release.
`bea-regional-state-personal-income-components-2024` reads the `SAINC.zip` of
BEA's 30 September 2026 release. Each package keeps its package id, record set
ids, record set specs and record id prefixes. Only its vintage, extraction date
and raw directory change, so its facts keep their semantic and source series
keys and carry the newer values. Against the earlier files, the national series
change only for 2021 to 2025 (the defined contribution series also gain 2025),
and the state statistics for 2009 to 2025 were revised. The earlier files stay
registered in `db/data` as the record of what R2 holds, and no package reads
them.
