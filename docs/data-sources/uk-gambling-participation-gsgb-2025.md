# GSGB 2025 gambling participation for PolicyEngine/microcosm#1381

PolicyEngine/microcosm#1381 tops up gambling incidence on the frame to the share of
adults who gamble, which the LCFS diary under-records. These facts give it the
Gambling Commission's published participation rates. Everything here is a published
aggregate; no microdata is involved. `scripts/build_uk_excise_packages.py`
(`build_gsgb_participation`) regenerates the package from the pinned bytes.

## Source

"Gambling Survey for Great Britain - Annual Report, 2025 Data tables",
`GSGB_annual_report_2025_data_tables.xlsx` (484,303 bytes, sha256 `ccee2269…`), published
16 July 2026 on the
[publication page](https://www.gamblingcommission.gov.uk/statistics-and-research/publication/gambling-survey-for-great-britain-annual-report-2025-official-statistics).
Official statistics: 20,775 adults aged 18 and over in Great Britain, with fieldwork from
13 January 2025 to 22 January 2026.

- **Stored in R2 only.** The manifest has `storage.local: false`, and `.gitignore` keeps
  the workbook out of the repository. The Commission states no licence for the file: not
  on the workbook, the publication page or data.gov.uk. Its website terms require prior
  approval to copy its material unless otherwise stated. The manifest records this under
  `license_evidence`. Builds read the file from the source-artifact cache, or, with
  `LEDGER_SOURCE_ARTIFACT_FETCH=1` as CI sets, from `source_url`.
- **Period.** Every fact is calendar year 2025, with `survey_reference` coverage from
  13 January 2025 to 22 January 2026. "Past 12 months" and "past four weeks" are the
  questionnaire's recall windows (GSGB is self-completed, online or on paper).
- **Values.** Each value is the stored cell. Participation cells hold proportions, which
  the workbook displays as percentages to 0 decimal places. Some bases carry
  floating-point noise from the file (1231.999999999998 for 1,232), kept as published.

## Package

`gambling-commission-gsgb-annual-report-2025`: 1,024 facts. Entity `person`, role
`survey_population`, provenance `survey_aggregate`, survey instrument "Gambling Survey for
Great Britain". Record-set ids start `gambling_commission.gsgb_2025.`.

**Concepts.**
- `gambling_commission.gsgb.participation` (870 facts): the share of adults who took
  part, unit `share`.
- `gambling_commission.gsgb.unweighted_base` (104): each table's unweighted base, unit
  `count`, as printed.
  - B.1 to B.4 print the base of their first measure, any gambling in the window.
  - B.9 and B.10 print that of any gambling activity in the past four weeks.
  - For these six tables, the footnotes say other bases "vary but are of a similar
    magnitude".
  - B.13's base is its own denominator: productive individuals who gambled in the past
    four weeks.
- `gambling_commission.gsgb.activity_count_distribution` (40): among people who gambled
  in the past four weeks, the share by number of activities.
- `gambling_commission.gsgb.mean_activity_count` (10): their mean number of activities,
  unit `gambling_activities`, aggregation `mean`.

**Dimensions.**
- Participation facts, and the bases of B.1 to B.4, B.9 and B.10, carry
  `participation_window`, `participation_scope`, `gambling_channel`, `sex`, `age_band`,
  `survey_base` and `source_sheet`.
- B.13's facts carry `participation_window`, `sex`, `age_band`, `survey_base` and
  `source_sheet`. Its shares also carry `activity_count_band`.

The values:
- `participation_window`: `past_12_months` or `past_4_weeks`.
- `participation_scope`: `any_gambling`, `excluding_lottery_draw_only`, or one of B.9's
  activities. The activities are:
  - lottery draws: `any_lottery_draw`, `national_lottery_draws` and
    `other_charity_lottery_draws`;
  - scratchcards: `scratchcards`, `national_lottery_scratchcards` and
    `other_scratchcards`;
  - online instant win games: `online_instant_win_games`,
    `national_lottery_online_instant_win_games` and `other_online_instant_win_games`;
  - betting: `betting`, `betting_on_sports_and_racing` and
    `betting_on_the_outcome_of_events`;
  - the rest: `bingo`, `casino_games`, `fruit_and_slots_games`,
    `another_form_of_gambling`, `football_pools` and `private_betting`.
- `gambling_channel`: `all`, `online`, `in_person`, `venue` (bingo at a venue), `casino`
  (casino games at a casino) or `machine_in_a_venue`. A row with no stated channel is
  `all`; online instant win games are `online`.
- `activity_count_band` (B.13 only): `one`, `two_to_three`, `four_to_six` or
  `seven_or_more`.
- `sex`: `all`, `male` or `female`.
- `age_band`: `all`, `age_18_to_24`, `age_25_to_34`, `age_35_to_44`, `age_45_to_54`,
  `age_55_to_64`, `age_65_to_74` or `age_75_plus`.
- `survey_base`: `productive_individuals`, or `gambled_in_the_past_four_weeks` for B.13.
- `source_sheet`: the table, such as `Table B.9`.
- **Geography:** Great Britain (`K03000001`), or England (`E92000001`), Scotland
  (`S92000003`), Wales (`W92000004`) and the nine English regions (`E12000001` to
  `E12000009`) for B.2, B.4 and B.10.

**Tables.**
- B.1 and B.3: participation in the past 12 months and the past four weeks.
  - Measures: any gambling, and excluding lottery-draw-only players.
  - Rows: all adults, by sex, by seven age bands, and by sex crossed with age band (24
    rows).
- B.2 and B.4: the same two measures by country and English region (12 areas).
- B.9: past-four-week participation by activity and its online and in-person sub-rows,
  for all adults, by sex and by age band (not crossed).
- B.10: the same activities by country and English region.
- B.13: the number of activities among people who gambled in the past four weeks, by sex
  and by age band, with the mean.

## Choices

- **Restated rows.** B.9 and B.10's "Any gambling" row equals B.3 and B.4's past-four-week
  column cell for cell, which the generator asserts. Chronicle emits it once, from B.3
  and B.4. The online and in-person rows that follow it are B.9 and B.10's own.
- **Bases.** B.9 and B.10's bases differ from B.3 and B.4's by one in three cells (ages
  55 to 64 and 65 to 74, and Scotland). So each table keeps its own bases, and every fact
  carries its `source_sheet`.
- **Row labels are each table's own text,** with whitespace collapsed and footnote
  markers dropped.
  - B.9's row 6 reads "Tickets National Lottery draws bought in person", where B.10's
    reads "Tickets for National Lottery draws bought in person".
  - Both are kept, so the bundle reports a groupby-label warning for that row.
  - B.2 and B.4's rows are named by area, on a `gambling_commission.gsgb_area` axis.
- **Left out:**
  - weighted bases;
  - B.13's standard deviation, which has no Chronicle aggregation;
  - tables A.1 to A.6, B.5 to B.8, B.11, B.12, C.1 to C.3 and D.1 to D.21;
  - `-` cells, which mark a base under 50 or a count of 0. None fall in these tables, and
    the generator asserts every emitted cell is a number.
- **Publisher guidance.** The Commission's guidance on using GSGB statistics advises
  against direct comparisons with other gambling or health surveys, whose methods
  differ. It also gives a 95% confidence interval as p ± 1.96 × √(p(1 − p)/n), where n is
  the base. The bases are kept for that reason.
