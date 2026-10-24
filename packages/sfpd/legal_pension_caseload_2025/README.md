# PensionStat 2025

This extends the existing `sfpd-legal-pension-caseload-2025` package rather than
registering an overlapping source family. It replaces the four curated webpage
headline counts with direct selectors into the captured publisher workbook.
Those four headlines are not printed workbook cells, so they are not reconstructed
by summing categories. The package ID, alias and `sfpd_pensions` source name remain.
The source release vintage changes to distinguish the workbook capture.

The manifest registers the exact 5,939,528-byte XLSX capture retrieved on
2026-10-23. The R2 locations are declarations for the Belgium session's upload;
this lane does not upload bytes. Attribution: PensionStat.be (Federale
Pensioendienst / Sigedis), data 2025, retrieved 2026-10-23. The acquisition's
reuse terms identify CC0 and request source/date attribution.

`Info!A13` attributes the data to the Federale Pensioendienst; `Info!A14` gives
2019–2025. The rest of Info is a sheet index, without detailed definitions.
The January/gross-amount reference and exclusion of pensioners paid only through
the kadaster are acquisition context supplied with the source page. They apply
to the pensioner tables; Jaaruitgave separately retains its published kadaster
categories, including `Y`.

Only the 2025 rows become facts. The harness parses the complete used ranges of
Info and the five selected data sheets, preserving their historical cells as
source evidence without relabeling them as 2025 facts.

| Worksheet | Published cells selected | Reference period |
| --- | --- | --- |
| Gepensioneerden | I: Aantal; J: Gemiddeld bedrag januari | January 2025 |
| Gepensioneerden_gemeente | C: Aantal | January 2025 |
| IGO | I: Aantal | 1 January 2025 (stock) |
| IGO | J: Gemiddeld bedrag; K: Mediaanbedrag | January 2025 |
| Jaaruitgave | G: Jaaruitgave | Printed year 2025 |
| MinP_aantal | I: Aantal | January 2025 |

The reference dates follow PensionStat's definition pages, retrieved
2026-10-23. The [pensioner](https://www.pensionstat.be/nl/kerncijfers/wettelijk-pensioen/gepensioneerden)
and [minimum-pension](https://www.pensionstat.be/nl/kerncijfers/wettelijk-pensioen/minimumpensioen)
pages count everyone who received a legal FPD pension in January 2025. Their
amounts are gross January 2025 amounts. The
[IGO page](https://www.pensionstat.be/nl/kerncijfers/wettelijk-pensioen/igo)
instead dates its counts to 1 January 2025, and its mean and median amounts
are gross monthly amounts for January 2025.

The IGO sheet is therefore two record sets. Counts have period coverage
1 January 2025 to 1 January 2025; amounts have coverage 1–31 January 2025.
They share one spec ID and source-record-ID prefix, so fact keys and
source-record IDs do not depend on the split. Every monthly fact keeps the
compact period `month:2025-01`.

Each fact selects one numeric cell, with an exact sheet/row/column locator,
native header guard and guards for every category and year in its source row.
All amounts remain in euros at their published precision. Published averages
and medians use `mean` and `median`; counts and printed expenditure cells use
`sum` over a single cell. No range sums, ratios, rescaling, count-times-average
values, aging, reconciliation, imputation or consumer target bindings are created.
Measure concepts retain the publisher's sheet and column labels, without claiming
that an unqualified IGO amount column measures only the IGO component.

Native dimensions retain their Dutch text and codes. Category IDs hash the native
semantic dimensions, excluding row positions and values. Domestic residence
regions use BE1/BE2/BE3 with NUTS 2024 vintage; `BUI` remains an explicitly
publisher-local statistical scope rather than being assigned to Belgian residents.

Commune mapping assigns each of the 565 Dutch-edition commune names exactly one
NIS 2025 code, and the generator fails unless the result is a bijection onto
Statbel's 565 communes. The reference is the official Dutch and French commune
names Statbel publishes in its population file
(`statbel-population-structure-commune-2025`). The geography name is Statbel's
canonical name, as in that package; the publisher's label stays in the
`pensionstat.gemeente` dimension. The tiers, in order:

| Tier | Communes | Evidence |
| --- | ---: | --- |
| `statbel_nl_exact` | 551 | Equal to Statbel's Dutch name |
| `statbel_nl_orthographic` | 9 | Equal after case, diacritics, apostrophe style and `œ` |
| `publisher_fr_label_*` | 4 | PensionStat's French edition labels the commune with Statbel's French name |
| `publisher_section_label` | 1 | Montegnée is NIS 62093 (Saint-Nicolas, Liège province) |

The French-edition tier uses `data-2025-fr.xlsx`, the same publisher's French
workbook, registered in the manifest as label evidence that yields no facts.
Each Dutch-edition commune is paired with the French-edition row that has the
identical 2019–2025 count series; all 565 series are distinct. This resolves
Belle (Belœil), Gembloers (Gembloux), Heilissem (Hélécine) and 's-Gravenbrakel
(Braine-le-Comte), where Statbel's Dutch name is the French one or is spelled
differently.

Montegnée is a section of Saint-Nicolas (Liège province), and PensionStat uses
that label in both editions. Its French edition gives the label "Saint-Nicolas"
to Sint-Niklaas (NIS 46021), whose series and Dutch name both identify it. The
generator declares that one collision and that one section label, and fails if
either stops holding. Saint-Nicolas is also the only NIS 2025 commune left
without a row once the other 564 are assigned. No translation, fuzzy matching,
old-boundary mapping or merger aggregation is used. `commune_mapping.json` lists
every commune with its tier, the French-edition label and cell, Statbel's names
and the exact value-cell locator.

Regenerate the YAML and commune audit from the checked raw workbook:

```sh
python packages/sfpd/legal_pension_caseload_2025/build_package.py
chronicle validate-package sfpd-legal-pension-caseload-2025 --year 2025
chronicle build-suite sfpd-legal-pension-caseload-2025 --year 2025 --out /tmp/pensionstat-suite --replace
```

The generator verifies the workbook hash, exact column headers, native category
uniqueness, numeric values and integral counts, and emits no YAML aliases or merge
keys. Focused tests independently reopen the workbook, check full selected-cell
coverage, and resolve samples with independently parsed header/category evidence.
Status is `semantic_candidate` until deterministic checks and required source
fidelity/boundary reviews pass; human acceptance remains with the Belgium session.
