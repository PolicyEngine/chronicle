Add the IRS SOI congressional-district file's nine AGI classes to
`soi-congressional-district-2022` (chronicle#447 item 2.1): the return count
(`N1`) and adjusted gross income (`A00100`) of `agi_stub` 1 to 9, for every
state and district row (the file's US row has no class rows). The nine
classes are the nine of `soi-historic-table-2-state-agi-2022`, with the same
`income_range` values and AGI bounds: under $1, $1 under $10,000, then
$10,000, $25,000, $50,000, $75,000, $100,000 and $200,000 edges, and $500,000
or more. Each class is one record set. The new selections come after the 480
all-class selections, so the existing facts keep their cells. The label
register lists `income_range=500k_plus`, which two packages now emit.
