# CenTax childcare cliff-edge workbook (raw only)

`centax-childcare-cliff-edge-2026` (`db/data/centax/childcare_cliff_edge_2026`) registers the
data for the charts of Advani, Flew, Pepin-Hall and Summers (2026), *Removing the £100,000
childcare cliff-edge: Impacts and cost of reform* (CenTax Policy Report, September 2026). The
workbook, `AdvaniFlewPepinhallSummers2026_ChildcareThreshold_data.xlsx` (194,075 bytes), is linked
as "Data for the charts" beside the report on
[arunadvani.com/policy.html](https://arunadvani.com/policy.html#ChildcareCliffEdge). CenTax's own
report page links only the PDF.

## What it holds

45 sheets: two section dividers, the report's tables (3.1 to 4.3, A.1 to A.5, B.1, B.2, C.1 to
C.11) and its figures (1.1, 2.1, 3.1 to 3.12, A.1 to A.4, B.1). Every sheet is the authors'
calculations based on HMRC administrative datasets. "2022" is the 2021-22 tax year.

| Sheet | Contents | Bins |
| --- | --- | --- |
| Fig. 3.1 | Parents of 3- and 4-year-olds in England by adjusted net income (ANI), 2021-22 | £500 to £200,000 |
| Fig. 3.3 | The same, employees and non-employees (main source of income) | £1,000 to £150,000 |
| Fig. 3.6 | The same, by sex | £500 to £150,000 |
| Fig. 3.7 | The same by region group (London, North and Midlands, South excluding London) and Scotland, pooled over 2018-19 to 2021-22 | £1,000 to £150,000 |
| Fig. 3.12 | Share of parents with a partner not in work | £2,500 to £150,000 |
| Tab. A.1 | Sample statistics: parents, partners, sex, age and mean ANI, whole population and £80k-£140k | |

Bins are labelled by their upper edge: Figure 3.1's labels run from 500 to 200,000. The sheets
of Figures 3.1 and 3.6 say the report's charts aggregate their £500 bins into £1,000 bins. Figure
3.7's sheet does not say which English regions make up its two groups outside London. The other
sheets hold the authors' model outputs: bunching, friction parameters, elasticities, notch
sizes, marginal bunchers and fiscal costs.

## Registration

Raw only: no Chronicle build parses the workbook. PolicyEngine/microcosm#1399 checks the bytes
against this manifest (sha256, size), derives its CenTax parent cells from Figures 3.1, 3.3, 3.6
and 3.7, and reads Table A.1 and Figure 3.12 as diagnostics. No consumer binds the model
outputs.

No licence is stated on the linking page, CenTax's report page or the workbook. Arun Advani
(CenTax) has said he is open to PolicyEngine using the data published at the source URL (relayed
on 23 November 2026). As with the Gambling Commission's GSGB tables, the bytes are therefore held
in R2 only (`storage.local: false`) and git-ignored. A build that needs them reads them from the
source-artifact cache, or with `LEDGER_SOURCE_ARTIFACT_FETCH=1` from the source URL; either route
is checked against the pinned sha256.
