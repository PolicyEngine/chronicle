Add `chronicle build-bundle --suite be`, a curated Belgian bundle suite for
Microcosm-BE's feed. It builds the 18 packages under `packages/bfp`, `fpb`,
`nbb`, `onem_rva`, `onss`, `opgroeien`, `ostbelgien`, `rsz`, `sfpd`,
`spf_finances` and `statbel`, plus the 8 Eurostat packages that cover Belgium.
Eurostat publishes for every member state, so `packages/eurostat/` can hold
packages that cover only other countries; the drift guard counts a Eurostat
package only when one of its rows reports for Belgium or a Belgian NUTS
region, or it reads a euro exchange-rate series. A test sweeps every package
for a Belgian country or NUTS geography or the commune level, so a test fails
when someone adds such a package under a new publisher directory without
adding it to the suite or naming it out. The suite leaves out the JRC
EUROMOD-BE comparison package while decision d1822 is open. Like the NZ and UK
suites, `--suite be` refuses `--source`, and `--year` does not change what it
builds.
