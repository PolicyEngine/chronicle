Add 30 IRS SOI columns without a state twin to every row of
`soi-congressional-district-2022` (chronicle#447 item 2.3, first candidates):
the total standard deduction, self-employment tax, net investment income tax,
alternative minimum tax, advance and net premium tax credit, child and
dependent care credit, nonrefundable and refundable education credits,
retirement savings contribution credit, self-employed health insurance and
retirement plan deductions, IRA payments, the student loan interest deduction
and total tax liability (returns and amount each). Each measure is pinned to
the documentation guide's definition. The standard deduction amount keeps
Table 1.2's id, and the self-employed health insurance deduction Table 1.4's.
In the file every column's district rows add up exactly to their state row,
so these rows nest in the file's own state rows.
