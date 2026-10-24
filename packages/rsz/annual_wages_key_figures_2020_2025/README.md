# RSZ/ONSS annual wage key figures, 2020–2025

This package preserves every numeric data cell in **Kerncijfers-Chiffres Clés**
of the RSZ/ONSS workbook **Lonen en bezoldigde prestaties**, captured
`2026-10-24T01:05:27Z`. The publisher's
[voorpublicatie ruwe data page](https://www.rsz.be/stats/voorpublicatie-ruwe-data)
was updated **22/10/2026** and describes this release as a pre-publication of
the raw data. The product link says “Jaaroverzicht - 2024 en 2025”; the selected
sheet actually publishes **2020–2025**. In particular, the 2024–2025 observations
are pre-publication figures, with no assertion that they are final.

The immutable [publisher workbook](https://www.rsz.be/file/6103c41969844d308979992d7f84d51e59927e1e/c4c5776181e3dd24273ecb6b9486065cb468fadb/ruwedata-donneesbrutes-periods-wages.xlsx)
is stored at `db/data/rsz/annual_wages_key_figures_2020_2025/rsz-ruwedata-periods-wages.xlsx`.
Its SHA-256 is
`7eea6aa74dd8c3c287c54bf591fef0e8e5d5507404988f94a05bf259fd6883af`.
The manifest also preserves the landing page, both methodology pages, licence
evidence and the acquisition's `CAPTURED_AT.txt` and `SHA256SUMS.txt` receipts.
All raw bytes were copied unchanged from the capture. Every manifest file is
stored under its content-addressed key in the `ledger-raw` R2 bucket, verified
by SHA-256 readback on 2026-10-24.

## Cells, units and coverage

The package emits **252 facts**: **216 detail cells** (six years × three worker
types × two sexes × six measures) and **36 separately published total cells**.
The source worker-type labels are `Arbeider - Ouvrier`, `Bediende - Employé`
and `Ambtenaar - Fonctionnaire`; the sex labels are `Man - Homme` and
`Vrouw - Femme`. Printed labels remain in the extract. Blank year and worker-type
cells inherit the surrounding workbook block's header; no numeric cell is
filled or imputed.

| Column | Published measure | Preserved unit |
|---|---|---|
| D | gewone bezoldiging / rémunération ordinaire | `EUR_thousands` |
| E | verbrekingsvergoeding / indemnité de rupture | `EUR_thousands` |
| F | premies / primes | `EUR_thousands` |
| G | enkel vertrekvakantiegeld / pécule simple de sortie | `EUR_thousands` |
| H | Dagen Voltijds / Journées Temps Plein | `day` |
| I | Uren deeltijds / Heures temps partiel | `hour_thousands` |

The monetary heading is **“Bezoldiging - rémunération (x 1.000 Eur)”** and
the part-time-hours heading says **“(x 1.000)”**. Values remain in those
published thousands, following
[Stats NZ household net worth's unscaled `NZD_thousands` and `household_thousands` convention](../../stats_nz/household_net_worth_2024/README.md).
There is no `value_scale` multiplication. Full-time paid days remain in days.
`aggregation: sum` identifies the additive measure; each selector reads a
single published data cell and performs no sum.

Each measure has its own record set for each calendar year, with coverage
from **1 January through 31 December**. Sets share the table's
`record_set_spec_id` and a per-year `source_record_id_prefix`; moving a measure
between sets does not change the publisher-record IDs. These annual flows
are neither quarter-end stocks nor annualized daily wage rates. The package
pins the October 2026 release while keeping each observation's original year;
requesting another build year does not align or age a value.

Geography is `BE`, country, **Belgium**, using the existing Statbel canonical
name. The scope is **RSZ-registered employment** of employees only.
Employees resident abroad, mainly inbound cross-border workers, are included;
workers posted to Belgium are not (common criteria page).
This administrative employment population differs from Statbel's fiscal
declarations. Amounts in a worker-type/sex cell describe that administrative
population and are not a distribution of annual earnings per individual.

## Definitions and limits

The captured [common variables page](https://www.rsz.be/gemeenschappelijke-variabelen)
defines remuneration:

> De bezoldigingen die we vermelden in onze statistieken komen overeen met het
> brutoloon van de werknemers. Zowel de RSZ- werknemersbijdrage als de
> bedrijfsvoorheffing zitten nog in dat brutoloon.

It also explains the holiday-pay population difference:

> Het enkel vakantiegeld van deze arbeiders maakt dan ook geen deel uit van de
> bezoldigingen die we vermelden in onze statistieken.

That page's component table includes ordinary remuneration, contractual
premiums and certain severance payments, includes employees' simple holiday
pay, and excludes double holiday pay. Some special worker categories use a
statutory flat-rate basis rather than actually received remuneration. This
package preserves the six published headings without constructing a broader
wage total, wage rate, average or ratio.

The related quarterly employment product uses distinct period semantics. The
same methodology page states:

> De statistische telling van de arbeidsplaatsen op het einde van een kwartaal
> gebeurt door op het einde van dat kwartaal het aantal werknemers te tellen
> bij elke werkgever.

> In de hier opgenomen telling worden dubbeltellingen te wijten aan meerdere
> arbeidsbetrekkingen op het einde van een kwartaal van eenzelfde werknemer
> verwijderd.

> De bepaling van het arbeidsvolume gebeurt op basis van alle aangegeven
> bezoldigde arbeidsprestaties over het ganse kwartaal met uitsluiting van de
> zuiver fictieve prestaties (vergoeding en arbeidsdagen bij beëindiging van
> de arbeidsovereenkomst).

Thus jobs and employed-worker counts in the companion daily-wage package
are quarter-end stocks, whereas FTE covers the full quarter. Workers are
deduplicated by INSZ and assigned their principal job's characteristics.
This annual wages package emits no quarterly counts or FTE values.

The captured [common criteria page](https://www.rsz.be/gemeenschappelijke-criteria)
defines the different concept used by the daily-wage-class tables:

> Het dagloon is een afgeleid gegeven, berekend op basis van de normale bruto
> bezoldiging, die als basis dient voor de berekening van de
> socialezekerheidsbijdragen.

It divides ordinary gross pay by paid days for full-time workers and
multiplies the equivalent hourly wage by 7.6 for part-time workers. The daily
wage excludes double holiday pay, premiums, profit shares, the thirteenth
month and severance. **Daily-wage classes rank earning rates, not annual
earnings.** Chronicle performs none of those calculations here.

## Totals, precision and exclusions

The workbook was independently opened with **`data_only=False`**. In this
sheet, **all 36 numeric cells in `Totaal 2020` through `Totaal 2025` are typed
numeric values, not `SUBTOTAL` formulas or other formulas**. They are therefore
retained as publisher-asserted total cells, at rows 10, 17, 24, 31, 38 and 45.
No formula subtotal was excluded from this sheet. The generator excludes a
total data cell if it is a `SUBTOTAL` formula and rejects other formulas;
the independent tests verify the actual typed totals of this pinned release.
Totals are never constructed from detail. Rounded detail need not sum exactly
to a separately rounded, independently published total.

Every selected cell uses **`#,##0.0`**, displaying **one decimal place**. The
generator reads each cell's number format and quantizes its cached value to
an exact decimal string with `Decimal` and `ROUND_HALF_UP`. For example,
`D4`'s cached `21462847.451270003` becomes `21462847.5` thousand EUR and
`I39`'s cached `276000.22620999994` becomes `276000.2` thousand hours.
The CSV retains the original cached value, number format, printed labels and
exact workbook / sheet / cell locator alongside that representation. Tests
independently reread **every one of the 252 selected cells**, including noisy
sample cells and every typed total.

There is a single source workbook and no overlapping annual source release
to reconcile. The 2024 overlap check between the two quarterly workbooks
belongs to the companion daily-wage package; this package never selects an
annual observation from either of those workbooks.

Only `Kerncijfers-Chiffres Clés` contributes facts. Available follow-ups in
the same preserved workbook are:

- `Wages-Periods NAC08` and `Wages-Periods NAC2025` (NACE activity);
- `Wages_periods PC_CP` (joint committee);
- `Wages_periods Wnpl_domic_LT2024` and `Wages_periods Wnpl_domic_GT2024`
  (arrondissement / worker residence);
- `Wages_periods_keng_cat` (employer category);
- `Nac08- 61`, `Nace25- 38`, `Arrondissem` and
  `Sectorgroep_groupe Sectoriel` (classification/look-up sheets).

## Licence, attribution and reproduction

The captured [RSZ Open Data / Data Governance Act page](https://www.rsz.be/open-data-data-governance-act)
states:

> Wanneer u deze gegevens gebruikt, moet u de bijgevoegde licentie (CC BY 4.0)
> naleven.

Licence: **[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)**.
Attribution: **RSZ/ONSS, Directie Statistiek, Lonen en bezoldigde prestaties,
October 2026 pre-publication; retrieved 2026-10-24. Representation normalized
by PolicyEngine Chronicle; CC BY 4.0.**

Run from the repository root:

```bash
python packages/rsz/annual_wages_key_figures_2020_2025/build_package.py
chronicle validate-package rsz-annual-wages-key-figures-2020-2025 --year 2025
chronicle build-suite rsz-annual-wages-key-figures-2020-2025 --year 2025 --out /tmp/rsz-annual-wages-suite --replace
```

The generator reproduces the checked CSV, manifest and package YAML byte for
byte. Every record set explicitly declares `provenance_class: administrative`;
YAML anchors and merge keys are disabled. No computed or reconciled value,
consumer target, measurement binding or period alignment enters this package.
