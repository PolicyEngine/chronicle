# Kindergeld in Ostbelgien, 2025

This curated source package records 35 published figures from the **Ministerium der
Deutschsprachigen Gemeinschaft**, as the article's tables attribute them
(“Quelle: Ministerium der Deutschsprachigen Gemeinschaft”), via Ostbelgien Statistik: [Kindergeld in
Ostbelgien](https://ostbelgienstatistik.be/desktopdefault.aspx/tabid-3748/6766_read-39090/),
labelled **“Aktualisierung vom 31.03.2026”**. The figures are administrative
observations in the `child_benefit` domain.

## Evidence and reuse

The evidence is
`db/data/ostbelgien/kindergeld_2025/kindergeld-in-ostbelgien.article.html`, SHA-256
`c570d9b5cef3bb100c4caf1ca8db528376d6f7b3176968d3d259bb947d2801c5`.
Its header records capture on **2026-10-24, approximately 01:10Z**, in the Claude
desktop built-in browser. It contains the article element's `outerHTML`, with
script/style elements, `class`/`style`/`id`/`data-*` attributes and comments stripped, and
whitespace collapsed. It is a browser transcription preserved as evidence;
it is not the publisher's original byte stream. Plain HTTP clients receive a
Cloudflare challenge; this package does not fetch or bypass it.

The manifest distinguishes `ostbelgien_kindergeld_2025.csv` from this evidence
capture and records their hashes and source URLs. Both are stored under their
manifest keys in the `ledger-raw` R2 bucket, verified by SHA-256 readback on
2026-10-24. Each CSV row carries two pointers into the evidence. The
`source_locator` names the article sentence, or gives structured table, row and
column coordinates. The `source_evidence` column quotes the capture verbatim: the
sentence, or the table row's own `<tr>…</tr>` HTML, which occurs exactly once in
the capture. `build_package.py` reproducibly extracts the figures and generates
the CSV, manifest and package declaration.

The [Impressum](https://ostbelgienstatistik.be/desktopdefault.aspx/tabid-2399/)
names the Ministry as publisher and states no data licence. Reuse status:
**no licence stated; figures cited with attribution**. The capture is committed as
evidence, as other packages commit publisher HTML pages (for example
`db/data/kff/marketplace_effectuated_enrollment`); the article is attributed
to the Ministry here and in the manifest. The embedded 2015–2025 graph, which this
package does not use, carries a different line: “Quelle: Famifed und Ministerium der
Deutschsprachigen Gemeinschaft”. The expenditure table prints no source line.

## Figures and reference periods

| Published section | Facts | Reference basis |
| --- | ---: | --- |
| Text: children, Empfänger and protected/new amounts | 6 | “im Dezember 2025” |
| Text: protected/new amount shares | 4 | “im Dezember 2025” |
| Verteilung des Kindergelds nach Altersgruppen | 4 | Publisher's column label “2025”; ambiguity below |
| Verteilung des Kindergelds nach Zuschlag | 5 | “zum Stand Ende Dezember 2025” |
| Text: Geburtsprämie and Adoptionsprämie payment instances | 2 | Calendar year 2025 |
| Ausgaben Familienleistungen im Jahr 2025 | 14 | Calendar year 2025; EUR |

Counts use German thousands separators and expenditure uses thousands dots and
decimal commas: `15.533` is stored as `15533`, and `33.958.484,38` as
`33958484.38`. The published shares **1,2 %, 98,8 %, 1,7 %, 98,3 %** are retained
as published percentage values. The facts-only ADR makes anything a publisher
asserted a fact, and other packages record published shares the same way (for
example `dwp/hbai_summary_fye2025`); none is recomputed from the counts.
Repeated prose mentions of 15.533 children and the expenditure total
46.892.862,30 EUR do not create additional facts for the same observation.

All facts retain the coarse identity `calendar_year:2025`, following the
Opgroeien package. Explicit coverage gives dates only where the article states
the span, and quotes the phrase that states it:

| Reference basis | Coverage | Article wording |
| --- | --- | --- |
| `december_2025` | 2025-12-01 to 2025-12-31 | “im Dezember 2025”: the month, not a day |
| `end_2025` | 2025-12-31 | “zum Stand Ende Dezember 2025” |
| `calendar_year_2025` | 2025-01-01 to 2025-12-31 | “im Jahr 2025”, “2025 wurde” |
| `publisher_year_2025_ambiguous` | no dates | column label “2025” only |

The payee total comes from the sentence “Die 15.533 Kinder … verteilen sich auf
8.302 Empfänger”, which refers back to the December child count, so it shares
the December coverage.
Record sets are split where coverage differs while retaining the same
`record_set_spec_id` and `source_record_id_prefix` for measures from one table.
Opgroeien preserves `december_2025` and `end_2025` only in its CSV
`reference_basis`, without explicit `period_coverage`; adding coverage here is an
intentional clarification of that convention.

For the age table the publisher writes **“die 2025 Kindergeld von der
Deutschsprachigen Gemeinschaft erhalten haben”**, and the column header is
**“2025”**. Its total is the same as the December count, but the article does not
resolve whether this is an annual recipient count or a December distribution. The
package keeps the label “2025” as its `source_period_label`, gives no start or end
date, and records the ambiguity in the coverage notes; it infers neither a
December snapshot from the matching total nor a full-year span from the label. The `25 Jahre und älter`
row is preserved without inferring unreported eligibility conditions.

The age-table `Total` and the expenditure subtotals `Kindergeld neuer Betrag`
and `Prämien`, and `Total Familienleistungen`, are published total cells and are
marked as totals. Their arithmetic is a check, not the origin of their values.
Supplement counts overlap: the article says a child can receive two supplements
and appear twice. They have no added total and cannot be summed as a child
caseload.

## Publisher definitions and scope

The article says the Community began paying family benefits under its own law
in January 2019. Its transitional **festgehaltener Betrag** preserves the amount
a recipient received in December 2018 until the new system would pay more or the
number of eligible children changes. `Empfänger` means the recipients of the
payments, distinct from the children for whom Kindergeld is paid. Child and
payee observations use `person` / `benefit_recipient`; no household count is
inferred. The article says the Geburtsprämie was paid 700 times and the Adoptionsprämie
once ("700 und die Adoptionsprämie einmal ausgezahlt"), so these annual counts are
payment instances, not children or families. They are recorded under the
receiving unit, `benefit_unit` / `premium_payment`, following the convention of
counting activity under the participating entity, as
`scotgov/bus_coach_statistics_2024_25` counts passenger journeys under `person` /
`bus_passenger`. Spending has `government` / `payer` as its entity.

The supplement definitions are those given in the article:

- **Zuschlag für kinderreiche Familien:** for the third and each subsequent child.
- **Sozialzuschlag:** support for low-income families, paid where there is an
  entitlement to increased health-insurance reimbursement.
- **Zuschlag für Kinder mit Beeinträchtigung:** the amount depends on the child's
  independence.
- **Halbwaisenzuschlag:** where one parent has died or been declared missing and
  the surviving parent has neither remarried nor entered legal cohabitation.
- **Vollwaisenzuschlag:** where both parents have died or been declared missing.

The article explains that the child-benefit count is below the population count
because EU rules can require another state to pay, for example when both parents
earn their income in Germany or Luxembourg. These are the Community's published
payment statistics, not a census of all resident children or all entitled
children across payers.

The geography is the German-speaking Community, named as the article prints it,
**Deutschsprachige Gemeinschaft**, declared as `statistical_scope`, identifier
`ostbelgien:deutschsprachige_gemeinschaft`, vintage `nis_2025`. It is the scope of
nine communes in Liège province, not a NUTS region. The following code/name pairs
are quoted from `geography_id` and `geography_name` on the total rows of
`db/data/statbel/population_structure_commune_2025/statbel_population_structure_commune_2025.csv`:

| NIS 2025 code | Statbel CSV name |
| --- | --- |
| 63001 | Amel |
| 63012 | Büllingen |
| 63013 | Bütgenbach |
| 63023 | Eupen |
| 63040 | Kelmis |
| 63048 | Lontzen |
| 63061 | Raeren |
| 63067 | Sankt Vith |
| 63087 | Burg-Reuland |

The commune membership defines the publisher scope; it does not create or
reconcile commune-level benefit facts. The embedded 2015–2025 interactive graph
is an iframe whose underlying observations are absent from this capture, so the
package contains no historical graph series.

## Validation and limits

Regenerate and validate with:

```sh
python3 packages/ostbelgien/kindergeld_2025/build_package.py
uv run chronicle validate-package ostbelgien-kindergeld-2025 --year 2025
uv run chronicle build-suite ostbelgien-kindergeld-2025 --year 2025 --out .hub-scratch/ostbelgien-kindergeld-suite --replace
```

The focused tests in `tests/test_source_ostbelgien_kindergeld_2025.py` parse the
HTML independently and check every selected figure, period declaration and
published arithmetic. They also check that every `source_evidence` value occurs
verbatim in the capture, and that each table fragment's cells are exactly the
row label and the printed value. Every record set declares `provenance_class:
administrative` textually. Every fact has curated-CSV row lineage, a sentence or
table-cell locator and a verbatim evidence fragment.
Concepts retain source labels; no external canonical concept alignment is
asserted.

Chronicle preserves the publisher's figures and periods;
consumer selection, period alignment, reconciliation, aging and model bindings
remain outside this package.
