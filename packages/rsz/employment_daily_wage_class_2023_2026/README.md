# RSZ/ONSS employment by daily-wage class, 2023Q1–2026Q1

Publisher: Rijksdienst voor Sociale Zekerheid / Office national de sécurité sociale
(RSZ/ONSS), Directie Statistiek. Product: **Arbeidsmarktanalyse: gedetailleerde
kwartaalgegevens**, [landing page](https://www.rsz.be/stats/arbeidsmarktanalyse-gedetailleerde-kwartaalgegevens),
updated 26/08/2026. Source bytes were retrieved **2026-10-24T01:05:27Z**, copied
without alteration from the supplied captures, and SHA-256 verified against their
`SHA256SUMS.txt`. Exact XLSX, landing, definitions and licence captures and the
representation-only CSV live in `db/data/rsz/employment_daily_wage_class_2023_2026`.
The manifest supplies original URLs, hashes, byte sizes, retrieval time and R2
keys. Every manifest file is stored under its key in the `ledger-raw` R2 bucket,
verified by SHA-256 readback on 2026-10-24.

CC BY 4.0 applies. The captured [open-data page](https://www.rsz.be/open-data-data-governance-act)
states: “Wanneer u deze gegevens gebruikt, moet u de bijgevoegde licentie (CC BY
4.0) naleven.” Attribution: **Source: RSZ/ONSS, Directie Statistiek,
Arbeidsmarktanalyse: gedetailleerde kwartaalgegevens, updated 26/08/2026,
retrieved 2026-10-24; CC BY 4.0. Chronicle selected publisher cells and normalized
display representation and the documented labels below.**

## Coverage and cells

- **T17**, “Indeling naar dagloon, leeftijd en geslacht”: daily-wage class ×
  published age class × published sex, 2023Q1–2026Q1, **5,616 facts**. 2023 comes
  from `rsz-arbeidsmarktanalyse-per-kwartaal-2023-2024.xlsx`; 2024 onward comes
  from `rsz-arbeidsmarktanalyse-per-kwartaal-2024-2026.xlsx`.
- **T7**, “Indeling naar activiteitstak, dagloon en geslacht en statuut”:
  published worker status × sex × NACE 2025 activity × daily-wage class,
  2024Q1–2026Q1 from the newer workbook, **29,013 facts**. The publisher explicitly
  retropolated the four 2024 quarters to **NACE 2025**, for comparison with 2025;
  this is the publisher's classification, not a Chronicle reconciliation.
- **34,629 facts** in total, one per selected published numeric cell. Each
  measure has its own record set and period coverage, while the table's
  `record_set_spec_id` and category's `source_record_id_prefix` remain shared.
  The YAML is about 14.1 MB.

Geography is **Belgium** (`BE`, country, current), matching existing Statbel
country naming. The statistical population is RSZ-registered employment, not
Belgian resident fiscal declarations. It covers employees only. Employees
resident abroad, mainly inbound cross-border workers, are included; workers
posted to Belgium are not (common criteria page). FTE follows the publisher's
performance-based scope and exclusions; it is not a count of every job.
These populations differ from Statbel's fiscal-income declarations.

## Period semantics and quoted definitions

The captured [common variables](https://www.rsz.be/gemeenschappelijke-variabelen)
page defines jobs:

> De statistische telling van de arbeidsplaatsen op het einde van een kwartaal
> gebeurt door op het einde van dat kwartaal het aantal werknemers te tellen bij
> elke werkgever.

> Werknemers die op de laatste dag van het kwartaal bij meer dan een werkgever
> zijn tewerkgesteld, worden meermaals geteld.

Thus **Arbeidsplaatsen** are worker–employer relationships, a **quarter-end
stock**. Start and end coverage dates both equal the last calendar day of the
quarter. This follows the existing [ONS employee-job convention](../../ons/employee_workplace_pensions_summary_2024/source_package.yaml):
entity `person`, role `employee_job`. A worker with two employers counts twice;
this does not assert a deduplicated person count.

For **Tewerkgestelde werknemers**, the page states:

> In de hier opgenomen telling worden dubbeltellingen te wijten aan meerdere
> arbeidsbetrekkingen op het einde van een kwartaal van eenzelfde werknemer
> verwijderd. Het opzoeken van deze meervoudige prestaties gebeurt op basis van
> het unieke identificatienummer van de werknemer binnen het netwerk van de
> sociale zekerheid (INSZ).

> Indien een werknemer meerdere gelijktijdige arbeidsbetrekkingen heeft, wordt
> hij slechts eenmaal geteld en worden enkel die kenmerken (werkgevers- en
> prestatiegebonden kenmerken) weerhouden die verbonden zijn met de belangrijkste
> arbeidsovereenkomst.

Workers are therefore deduplicated by INSZ and carry their principal job's
characteristics. They too are a **quarter-end stock**, with start = end = the
quarter's last day. Entity is `person`, role `employee`.

For **VTE / ETP**, the page states:

> Voor de berekening van het arbeidsvolume in termen van voltijdsequivalenten,
> wordt de verhouding berekend tussen de arbeidsprestaties (bezoldigde- en
> vakantieprestaties) van de werknemer ten opzichte van de prestaties van de
> fictieve referentiepersoon voor een volledig kwartaal. Voor voltijdse
> werknemers gebeurt de berekening op basis van de prestaties uitgedrukt in
> dagen, voor deeltijdse werknemers op basis van prestaties uitgedrukt in uren.

> Deze definitie van voltijdsequivalenten is niet gebaseerd op de in de
> arbeidsovereenkomst contractueel voorziene arbeidsduur maar op de aangegeven
> prestaties.

FTE is work volume (entity `person`, role `full_time_equivalent_employee`)
**over the entire quarter**, with coverage from its first
through last day. All three measures retain the same publisher quarter label;
coverage distinguishes snapshots from period volume. No year alignment occurs.

## Daily-wage classes and other dimensions

The captured [common criteria](https://www.rsz.be/gemeenschappelijke-criteria)
page states:

> Het dagloon is een afgeleid gegeven, berekend op basis van de normale bruto
> bezoldiging, die als basis dient voor de berekening van de
> socialezekerheidsbijdragen.

> Er wordt geen rekening gehouden met het dubbel vakantiegeld, noch met premies,
> winstdeelnemingen, dertiende maand, gratificaties of gelijkaardige voordelen,
> noch met ontslagvergoedingen.

> Voor de voltijdse werknemers wordt de totale bruto bezoldiging zoals hierboven
> omschreven, gedeeld door het aantal bezoldigde dagen. Voor de deeltijdse
> prestaties wordt het gelijkaardig berekend uurloon vermenigvuldigd met 7,6
> (7u36) wat overeenkomt met het dagloon in geval van voltijdse prestaties,
> rekening houdend met een gebruikelijke arbeidsduur van 38 uur per week.

This is the publisher's normal gross **earning rate**, not annual earnings.
Chronicle ingests published classes and measures; it never computes a daily wage.
The class labels are `<100`, `100 - 149`, `150 - 199`, `200 - 299`, `>= 300`, and
`Onbekend-Inconnu`, in **EUR per day**. The source also prints
`Onbekend-inconnu`; both spellings normalize to `Onbekend-Inconnu` while the
printed form remains in each source locator. Numeric interval endpoints and
cent-level inclusivity are **unverified** and are not encoded as constraints.
The definition page lists finer boundaries (€50, €60, €70, €80, €90, €100,
€110, €125, €150, €200, €250) which these tables do not use.

Ages are exactly `-20`, `20-24`, `25-29`, `30-34`, `35-39`, `40-44`, `45-49`,
`50-54`, `55-59`, `60-64`, `65-69`, `70+`. Mixed integer `-20` and string `"-20"`
normalize to the same string label. No age bounds are inferred. The criteria
page states: “De leeftijd is deze die bereikt wordt op de laatste dag van het
kwartaal.”

Printed sex strings are preserved, including `Man-Homme`/`Man-homme` and
`Vrouw-Femme`/`Vrouw-femme`; these case variants are not silently merged.
Worker status retains the bilingual published `Arbeider-Ouvrier`,
`Bediende-Employé`, `Ambtenaar-Fonctionnaire` labels. NACE activity uses the
published code as its stable category. The first encountered (latest-quarter)
published NL/FR label pair is declared as its display label. Spelling, case and
wording variants remain in every locator and are enumerated in
`nace_label_variants.json`. Those label choices do not add or alter measures. The latest published CH label
pairs Dutch “Vervaardiging van farmaceutische grondstoffen en producten” with
French metallurgy wording; this source-label anomaly is preserved, not corrected.

## Display precision, overlap and formula exclusions

Cached FTE numbers contain binary noise. **All selected FTE number formats
display one decimal** (`#,##0.0`); jobs and workers display integers. The generator reads every cell's
format and uses `Decimal(str(cached_value))` with decimal `ROUND_HALF_UP` at
that precision. The CSV stores an exact decimal string, without rescaling.
For example, old T17 `G2` has cache `10283.759999999998` and is recorded as
`10283.8`; newer T17 `G2` has `6975.98` and is recorded as `6976.0`.
Raw cache values and formats remain available in the locators.

The full 2024 T17 overlap between the two workbooks comprises **576 category
rows / 1,728 cells**. All 1,728 agree at two decimals; **285 raw caches**
differ, all FTE.
Direct one-decimal conversion produces **15 differences at half-tenth
boundaries**. `workbook_audit.json` reports **every** old/new cell coordinate,
raw cache and displayed decimal. The newer workbook is selected for each,
including `G474` (old `58038.1`) versus `G1199` (new `58038.2`). Tests independently
reproduce the entire comparison and the complete difference report.

Every `Totaal …` row in T17 in both workbooks and newer T7 is an Excel
`SUBTOTAL(9,…)` formula under `data_only=False`. **None is emitted as a fact.**
Tests check every formula range: integer detail sums equal cached subtotals,
and cached FTE detail cells sum exactly at two decimals to the cached subtotal.
The separately rounded, one-decimal FTE facts do **not** always sum to the
rounded cached subtotal (for T7 the differences range from +1.6 to +5.9 FTE).
Exact equality of rounded facts and cached subtotals is therefore not a
property of the source; tests check cache consistency and displayed
representation separately. `workbook_audit.json` records all subtotal
checks and display differences. No balancing adjustments or derived total facts
are introduced. Missing demographic combinations are not imputed as zeros.

## Reproduction and limits

Run `python packages/rsz/employment_daily_wage_class_2023_2026/build_package.py`.
It reads the packaged, checksum-pinned XLSX files and deterministically reproduces
CSV, YAML, manifest and NACE-variant report. An optional source-directory argument
stages the pinned captures first. No network is used. A source cell locator
preserves workbook, sheet, coordinate, original dimensions, raw cached value and
number format. The representation-only CSV makes precision explicit and avoids
T17's inflated Excel used range (16,380 columns).

Focused tests: `tests/test_source_rsz_employment_daily_wage_class.py`.
Run `chronicle validate-package rsz-employment-daily-wage-class-2023-2026 --year 2026`
and `chronicle build-suite rsz-employment-daily-wage-class-2023-2026 --year 2026
--out <temporary-directory> --replace`. All covered quarters are literals: a
build year never restamps the source. No cross-source reconciliation, annual earnings estimate, age projection,
consumer profile or model binding is supplied.
