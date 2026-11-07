"""Generate the young people source packages for PolicyEngine/chronicle#420.

Run from the repository root:

    uv run python scripts/build_uk_young_people_packages.py

``--check`` compares the generated YAML with the committed files instead of writing.
Every package is written from its pinned artifact, read with Chronicle's own parsers,
so every row number, column and guard cell below is one the package parser sees. The
publisher's text is asserted cell by cell, so a run against different bytes fails
rather than drifting. Nothing is downloaded and no value is computed.

- ``ons-neet-august-2026``: ONS 'Young people not in education, employment or training
  (NEET)', UK, August 2026 edition: NEET people (all, unemployed, economically
  inactive), the population and the NEET share, ages 16-17, 18-24 and 16-24 by sex,
  seasonally adjusted and not, and the not seasonally adjusted 18-20, 21-22 and 23-24
  sheets, each quarter from April to June 2024 to April to June 2026.
- ``ons-a06-sa-october-2026`` and ``ons-a06-nsa-october-2026``: LFS table A06,
  educational status and labour market status of people aged 16 to 24, October 2026
  edition, the calendar-quarter windows from April to June 2024 to April to June 2026.
- ``ons-paye-rti-age-nsa-october-2026``: PAYE Real Time Information, payrolled
  employees and median, mean and aggregate monthly pay by age band, UK, not seasonally
  adjusted, April 2024 to the latest month.
- ``ons-ashe-table6-*``: ASHE Table 6 (earnings by age group) for the UK, 2024 revised,
  2025 revised and 2026 provisional: Tables 6.1a and 6.7a and their CVs, 6.1b and 6.7b.
- ``hmrc-employer-nics-age-reliefs-january-2026``: HMRC's tax relief statistics
  (January 2026), the cost (Table 2) and claimants (Table 5) of the employer NICs reliefs
  for employees under 21 and apprentices under 25.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import textwrap
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml
from openpyxl.utils import column_index_from_string, get_column_letter

from chronicle.sources.cells import (
    SourceArtifactMetadata,
    source_cells_from_ods,
    source_cells_from_xls,
    source_cells_from_xlsx,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-11-06"
ISSUE = "PolicyEngine/chronicle#420"
CONSUMER = "PolicyEngine/uk-young-people-work-review"
SCRIPT = "scripts/build_uk_young_people_packages.py"


class Flow(dict):
    """A small mapping written on one line, as the occupation packages write guards."""


class PackageDumper(yaml.SafeDumper):
    """Plain YAML with no anchors, so every record set reads on its own."""

    def ignore_aliases(self, data: object) -> bool:
        return True


PackageDumper.add_representer(
    Flow,
    lambda dumper, data: dumper.represent_mapping(
        "tag:yaml.org,2002:map", data, flow_style=True
    ),
)


def render(header: str, payload: dict) -> str:
    """The header's paragraphs, rewrapped as comment lines, then the package.

    URLs and package ids are long and hyphenated, so lines break only at spaces.
    """
    lines: list[str] = []
    for paragraph in textwrap.dedent(header).strip().split("\n\n"):
        if lines:
            lines.append("")
        lines += textwrap.wrap(
            " ".join(paragraph.split()),
            width=88,
            break_long_words=False,
            break_on_hyphens=False,
        )
    comment = "".join(f"# {line}".rstrip() + "\n" for line in lines)
    return comment + yaml.dump(
        payload, Dumper=PackageDumper, sort_keys=False, allow_unicode=True, width=100
    )


def metadata(filename: str) -> SourceArtifactMetadata:
    return SourceArtifactMetadata(
        source_name="",
        source_table="",
        source_file=filename,
        url=None,
        vintage="",
        sha256="",
        size_bytes=0,
        extracted_at="",
        extraction_method="",
    )


def pinned(directory: str) -> tuple[dict, bytes]:
    """The manifest's one file entry and its bytes, checked against the pinned digest."""
    manifest = yaml.safe_load((DATA / directory / "manifest.yaml").read_text())
    (entry,) = manifest["files"].values()
    content = (DATA / directory / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"], directory
    assert len(content) == entry["size_bytes"], directory
    return entry, content


def grid_of(cells) -> dict[tuple[str, int, str], object]:
    grid: dict[tuple[str, int, str], object] = {}
    for cell in cells:
        if cell.raw_value in (None, ""):
            continue
        grid[
            (cell.sheet_name, cell.row_number, get_column_letter(cell.column_number))
        ] = cell.raw_value
    return grid


def write(directory: str, text: str) -> None:
    path = PACKAGES / directory / "source_package.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def constraint(variable: str, value: object, label: str, **extra) -> Flow:
    return Flow(variable=variable, operator="==", value=value, label=label, **extra)


def bound(operator: str, value: int, label: str) -> Flow:
    return Flow(
        variable="age", operator=operator, value=value, unit="years", label=label
    )


def guard(column: str, row: int, value: object, label: str) -> Flow:
    return Flow(column=column, row=row, expected_value=value, label=label)


def squeeze(text: object) -> str:
    return " ".join(str(text).replace("\xa0", " ").split())


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def column_offset(column: str, offset: int) -> str:
    return get_column_letter(column_index_from_string(column) + offset)


UNITED_KINGDOM = {
    "geography_id": "K02000001",
    "geography_level": "country",
    "geography_name": "United Kingdom",
    "geography_vintage": "current",
}

# Labels for every dimension and value the packages use. A package declares the
# ones its facts use (Chronicle refuses a declaration no fact uses); the values two
# packages emit are also in chronicle/dimension_values/canonical_labels.json.
DIMENSION_LABELS = {
    "ons.neet_quarter": "NEET table quarter",
    "ons.a06_sa_quarter": "A06 SA three-month period",
    "ons.a06_nsa_quarter": "A06 NSA three-month period",
    "ons.paye_rti_month": "PAYE RTI month",
    "age_group": "ASHE age group",
    "employer_nics_relief": "Employer NICs relief",
    "age_band": "Age band",
    "sex": "Sex",
    "seasonal_adjustment": "Seasonal adjustment",
    "full_time_education": "Full-time education",
    "economic_activity": "Economic activity",
    "working_pattern": "Working pattern",
    "statistic": "Statistic",
    "earnings_percentile": "Earnings percentile",
}
AGE_BANDS = {
    "all": "All ages",
    "0_to_17": "0 to 17",
    "16_to_17": "16 to 17",
    "16_to_24": "16 to 24",
    "18_to_20": "18 to 20",
    "18_to_21": "18 to 21",
    "18_to_24": "18 to 24",
    "21_to_22": "21 to 22",
    "22_to_24": "22 to 24",
    "22_to_29": "22 to 29",
    "23_to_24": "23 to 24",
    "25_to_34": "25 to 34",
    "30_to_39": "30 to 39",
    "35_to_49": "35 to 49",
    "40_to_49": "40 to 49",
    "50_to_59": "50 to 59",
    "50_to_64": "50 to 64",
    "60_and_over": "60 and over",
    "65_and_over": "65 and over",
}
# The register words age bands 'Age 65 and over' (HMRC) and 'Age 0 to 16' (DfT), so
# these packages' labels do too; AGE_BANDS stays the words used in measure labels.
AGE_BAND_LABELS = {
    band: "All ages" if band == "all" else f"Age {words}"
    for band, words in AGE_BANDS.items()
}
VALUE_LABELS = {
    "age_band": AGE_BAND_LABELS,
    "sex": {"all": "All", "male": "Male", "female": "Female"},
    "seasonal_adjustment": {
        "seasonally_adjusted": "Seasonally adjusted",
        "not_seasonally_adjusted": "Not seasonally adjusted",
    },
    "full_time_education": {
        "all": "In or not in full-time education",
        "in_full_time_education": "In full-time education",
        "not_in_full_time_education": "Not in full-time education",
    },
    "economic_activity": {
        "all": "All economic activity statuses",
        "employed": "Employed",
        "unemployed": "Unemployed",
        "economically_inactive": "Economically inactive",
    },
    "working_pattern": {
        "all": "Full-time and part-time",
        "full_time": "Full-time",
        "part_time": "Part-time",
    },
    "statistic": {
        "estimate": "Estimate",
        "coefficient_of_variation": "Coefficient of variation",
    },
    "employer_nics_relief": {
        "apprentices_under_25": (
            "Relief on employer National Insurance contributions for apprentices "
            "under 25"
        ),
        "employees_under_21": (
            "Relief on employer National Insurance contributions for employees under 21"
        ),
    },
}


def declarations(record_sets: list[dict]) -> tuple[dict, dict]:
    """The dimension and value labels the record sets' facts use."""
    used: dict[str, set[str]] = {}
    for record_set in record_sets:
        used.setdefault(record_set["groupby_dimension"], set())
        filters = [record_set.get("shared_filters", {})]
        filters += [row.get("filters", {}) for row in record_set["rows"]]
        filters += [measure.get("filters", {}) for measure in record_set["measures"]]
        for mapping in filters:
            for key, value in mapping.items():
                used.setdefault(key, set()).add(str(value))
    dimension_labels = {
        key: DIMENSION_LABELS[key] for key in DIMENSION_LABELS if key in used
    }
    value_labels = {
        key: {
            value: label
            for value, label in VALUE_LABELS[key].items()
            if value in used[key]
        }
        for key in VALUE_LABELS
        if used.get(key)
    }
    return dimension_labels, value_labels


def category(variable: str, value: str) -> tuple[dict, list[Flow]]:
    """A publisher category as a filter and, unless it is 'all', a constraint."""
    if value == "all":
        return {variable: value}, []
    return {variable: value}, [constraint(variable, value, DIMENSION_LABELS[variable])]


def categories(*pairs: tuple[str, str]) -> tuple[dict, list[Flow]]:
    filters: dict = {}
    constraints: list[Flow] = []
    for variable, value in pairs:
        more_filters, more_constraints = category(variable, value)
        filters.update(more_filters)
        constraints += more_constraints
    return filters, constraints


def age_semantics(
    band: str, lower: int | None, upper: int | None
) -> tuple[Flow, list[Flow]]:
    """The age band as a filter, and as a constraint with its age bounds."""
    filters, constraints = category("age_band", band)
    if lower is not None:
        constraints.append(bound(">=", lower, "Age lower bound"))
    if upper is not None:
        constraints.append(bound("<", upper, "Age upper bound"))
    return Flow(filters), constraints


QUARTERS = {
    "Jan-Mar": (1, "01-01", "03-31"),
    "Apr-Jun": (2, "04-01", "06-30"),
    "Jul-Sep": (3, "07-01", "09-30"),
    "Oct-Dec": (4, "10-01", "12-31"),
}
QUARTER_LABEL = re.compile(r"^(Jan-Mar|Apr-Jun|Jul-Sep|Oct-Dec) (\d{4})( \[r\])?$")
FIRST_QUARTER = (2024, 2)  # April to June 2024, #420's first requested period


@dataclass(frozen=True)
class Quarter:
    row: int
    label: str  # as printed, with any ' [r]'
    year: int
    number: int

    @property
    def period(self) -> str:
        return f"{self.year}-Q{self.number}"

    @property
    def slug(self) -> str:
        return f"{self.year}_q{self.number}"

    @property
    def window(self) -> str:
        return QUARTER_LABEL.match(self.label).group(1)

    @property
    def start(self) -> str:
        return f"{self.year}-{QUARTERS[self.window][1]}"

    @property
    def end(self) -> str:
        return f"{self.year}-{QUARTERS[self.window][2]}"

    @property
    def revised(self) -> bool:
        return self.label.endswith(" [r]")


def quarters(grid: dict, sheet: str, *, rolling: bool) -> list[Quarter]:
    """The calendar-quarter rows from April to June 2024 to the latest, in order.

    A06's rows are rolling three-month periods (Mar-May, Apr-Jun, May-Jul, ...); only
    the four calendar-quarter windows have a Chronicle period type, so ``rolling``
    skips the others, which must still run month by month to the sheet's end.
    """
    found: list[Quarter] = []
    last_period_row = None
    for (name, row, column), value in sorted(grid.items(), key=lambda item: item[0][1]):
        if name != sheet or column != "A" or not isinstance(value, str):
            continue
        match = QUARTER_LABEL.match(value)
        if match is None:
            if rolling and re.match(r"^[A-Z][a-z]{2}-[A-Z][a-z]{2} \d{4}$", value):
                last_period_row = row
            continue
        last_period_row = row
        year, number = int(match.group(2)), QUARTERS[match.group(1)][0]
        if (year, number) >= FIRST_QUARTER:
            found.append(Quarter(row, value, year, number))
    assert found, sheet
    # Contiguous quarters, and nothing published after the last one but rolling
    # windows that end later (A06's May-Jul and Jun-Aug 2026).
    for before, after in zip(found, found[1:]):
        expected = (
            (before.year, before.number + 1)
            if before.number < 4
            else (before.year + 1, 1)
        )
        assert (after.year, after.number) == expected, (sheet, before, after)
        assert after.row == before.row + (3 if rolling else 1), (sheet, before, after)
    assert last_period_row - found[-1].row == (2 if rolling else 0), (
        sheet,
        last_period_row,
        found[-1],
    )
    return found


def quarter_coverage(quarter: Quarter, notes: str) -> dict:
    return {
        "start_date": quarter.start,
        "end_date": quarter.end,
        "basis": "survey_reference",
        "source_period_label": quarter.label,
        "notes": notes,
    }


def measure_spec(
    measure_id: str,
    label: str,
    ordinal: int,
    column: str,
    header_row: int,
    header: str,
    *,
    concept: str,
    unit: str,
    aggregation: str,
    evidence_url: str,
    notes: str,
    authority: str = "ons",
    filters: Flow | None = None,
    constraints: list[Flow] | None = None,
    scale: int | None = None,
) -> dict:
    measure = {
        "measure_id": measure_id,
        "label": label,
        "ordinal": ordinal,
        "column": column,
        "source_column_id": measure_id,
        "expected_column_header_row": header_row,
        "expected_column_header": header,
        "concept": concept,
        "source_concept": concept,
        "concept_relation": "source_label",
        "concept_authority": authority,
        "concept_evidence_url": evidence_url,
        "concept_evidence_notes": notes,
        "unit": unit,
        "aggregation": aggregation,
    }
    if scale is not None:
        measure["value_scale"] = scale
    measure["expected_cell_type"] = "number"
    if filters:
        measure["filters"] = filters
    if constraints:
        measure["constraints"] = constraints
    return measure


def numbered(measures: list[dict]) -> list[dict]:
    """The record set's measures with ordinals 0, 1, 2, ... in column order."""
    return [{**measure, "ordinal": ordinal} for ordinal, measure in enumerate(measures)]


def package_payload(
    *,
    package_id: str,
    label: str,
    record_sets: list[dict],
    artifact: dict,
) -> dict:
    dimension_labels, value_labels = declarations(record_sets)
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": package_id,
        "label": label,
        "dimension_labels": dimension_labels,
    }
    if value_labels:
        payload["dimension_value_labels"] = value_labels
    payload["artifact"] = artifact
    payload["record_sets"] = record_sets
    return payload


def fact_count(payload: dict) -> int:
    return sum(len(rs["rows"]) * len(rs["measures"]) for rs in payload["record_sets"])


# ---------------------------------------------------------------- 1. ONS NEET

NEET_DIRECTORY = "ons/neet_august_2026"
NEET_PAGE = (
    "https://www.ons.gov.uk/employmentandlabourmarket/peoplenotinwork/unemployment/"
    "datasets/youngpeoplenotineducationemploymentortrainingneettable1"
)
NEET_BULLETIN = (
    "https://www.ons.gov.uk/employmentandlabourmarket/peoplenotinwork/unemployment/"
    "bulletins/youngpeoplenotineducationemploymentortrainingneet/august2026"
)
LFS = "Labour Force Survey"
# Sheet, sex, seasonal adjustment, the words its title ends with, and its age groups:
# first column, age band, header text, lower and upper age bound.
NEET_MAIN_GROUPS = (
    ("B", "16_to_24", "Aged 16-24", 16, 25),
    ("G", "16_to_17", "Aged 16-17", 16, 18),
    ("L", "18_to_24", "Aged 18-24", 18, 25),
)
NEET_SHEETS = (
    (
        "People - SA",
        "all",
        "seasonally_adjusted",
        "People (seasonally adjusted)",
        NEET_MAIN_GROUPS,
    ),
    (
        "Men - SA",
        "male",
        "seasonally_adjusted",
        "Men (seasonally adjusted)",
        NEET_MAIN_GROUPS,
    ),
    (
        "Women - SA",
        "female",
        "seasonally_adjusted",
        "Women (seasonally adjusted)",
        NEET_MAIN_GROUPS,
    ),
    (
        "People - NSA",
        "all",
        "not_seasonally_adjusted",
        "People (not seasonally adjusted)",
        NEET_MAIN_GROUPS,
    ),
    (
        "Men - NSA",
        "male",
        "not_seasonally_adjusted",
        "Men (not seasonally adjusted)",
        NEET_MAIN_GROUPS,
    ),
    (
        "Women - NSA",
        "female",
        "not_seasonally_adjusted",
        "Women (not seasonally adjusted)",
        NEET_MAIN_GROUPS,
    ),
    (
        "People 18-20 - NSA",
        "all",
        "not_seasonally_adjusted",
        "People aged from 18 to 20 (not seasonally adjusted)",
        (("B", "18_to_20", "Aged 18-20", 18, 21),),
    ),
    (
        "People 21-22 - NSA",
        "all",
        "not_seasonally_adjusted",
        "People aged from 21 to 22 (not seasonally adjusted)",
        (("B", "21_to_22", "Aged 21-22", 21, 23),),
    ),
    (
        "People 23-24 - NSA",
        "all",
        "not_seasonally_adjusted",
        "People aged from 23 to 24 (not seasonally adjusted)",
        (("B", "23_to_24", "Aged 23-24", 23, 25),),
    ),
)
# Column offset in an age group, kind, header row and header text.
NEET_COLUMNS = (
    (0, "neet", 7, "Total"),
    (1, "neet_unemployed", 7, "Unemployed"),
    (2, "neet_inactive", 7, "Economically inactive"),
    (3, "population", 6, "Total people in relevant population group"),
    (
        4,
        "neet_rate",
        6,
        "People who were NEET as a percentage of people in relevant population group",
    ),
)
NEET_NOTE_QUOTES = (
    "Estimates from January to March 2025 include the full effect of the improvements "
    "in LFS data collection and sampling methods introduced from January 2024 onwards.",
    "These are official statistics.",
)
NEET_SHEET_QUOTES = (
    "1. Data from January to March 2019 onward has been reweighted, causing a step "
    "change discontinuity.",
)


def neet_measures(group: tuple, sheet: str, population: str) -> list[dict]:
    first, band, header, lower, upper = group
    age_filters, age_constraints = age_semantics(band, lower, upper)
    ages = AGE_BANDS[band]
    measures = []
    for offset, kind, header_row, text in NEET_COLUMNS:
        column = column_offset(first, offset)
        if kind.startswith("neet") and kind != "neet_rate":
            status = {
                "neet": "all",
                "neet_unemployed": "unemployed",
                "neet_inactive": "economically_inactive",
            }[kind]
            status_filters, status_constraints = category("economic_activity", status)
            what = {
                "neet": "young people who were NEET",
                "neet_unemployed": "young people who were NEET and unemployed",
                "neet_inactive": "young people who were NEET and economically inactive",
            }[kind]
            measures.append(
                measure_spec(
                    f"{kind}_{band}",
                    f"{what[0].upper()}{what[1:]}, aged {ages}",
                    len(measures),
                    column,
                    header_row,
                    text,
                    concept="ons.lfs_neet_people",
                    unit="count",
                    aggregation="sum",
                    evidence_url=NEET_PAGE,
                    notes=(
                        f"ONS NEET Table 1 (August 2026), sheet '{sheet}', column {column} "
                        f"under '{header}' and 'Young people who were NEET': {what}, "
                        f"{population}, United Kingdom, people (the sheet's 'thousands' "
                        "is the cells' display format; the cells hold people)."
                    ),
                    filters=Flow({**age_filters, **status_filters}),
                    constraints=age_constraints + status_constraints,
                )
            )
        elif kind == "population":
            measures.append(
                measure_spec(
                    f"population_{band}",
                    f"People aged {ages}",
                    len(measures),
                    column,
                    header_row,
                    text,
                    concept="ons.lfs_people",
                    unit="count",
                    aggregation="sum",
                    evidence_url=NEET_PAGE,
                    notes=(
                        f"ONS NEET Table 1 (August 2026), sheet '{sheet}', column {column} "
                        f"under '{header}': total people in the relevant population "
                        f"group, {population}, United Kingdom, people."
                    ),
                    filters=age_filters,
                    constraints=age_constraints,
                )
            )
        else:
            measures.append(
                measure_spec(
                    f"neet_rate_{band}",
                    f"Share of people aged {ages} who were NEET",
                    len(measures),
                    column,
                    header_row,
                    text,
                    concept="ons.lfs_neet_rate",
                    unit="percent",
                    aggregation="share",
                    evidence_url=NEET_PAGE,
                    notes=(
                        f"ONS NEET Table 1 (August 2026), sheet '{sheet}', column {column} "
                        f"under '{header}': people who were NEET as a percentage of "
                        f"people in the relevant population group, {population}, "
                        "United Kingdom."
                    ),
                    filters=age_filters,
                    constraints=age_constraints,
                )
            )
    return measures


# The 'Women - NSA' sheet prints an 18-24 population (column O) below the 'Women -
# SA' sheet's, A06 NSA's and 16-24 minus 16-17 in every ported quarter, by these many
# people; its 18-24 NEET share (column P) is computed on it. Ported as published.
NEET_WOMEN_NSA_POPULATION_GAPS = {
    "2024-Q2": 5141,
    "2024-Q3": 6434,
    "2024-Q4": 6308,
    "2025-Q1": 12623,
    "2025-Q2": 18933,
    "2025-Q3": 7633,
    "2025-Q4": 7469,
    "2026-Q1": 7453,
    "2026-Q2": 7539,
}


def neet_check_parity(grid: dict, sheet: str, quarter: Quarter, groups) -> None:
    def value(column: str) -> float:
        return grid[(sheet, quarter.row, column)]

    for first, *_ in groups:
        neet, unemployed, inactive, people, rate = (
            value(column_offset(first, offset)) for offset in range(5)
        )
        # Unemployed plus inactive is NEET, and the share is NEET over the population.
        assert abs(unemployed + inactive - neet) < 1e-6 * neet, (sheet, quarter)
        assert abs(100 * neet / people - rate) < 1e-9 * rate, (sheet, quarter)
    if len(groups) == 3:
        # 16-17 plus 18-24 is 16-24, for NEET people and the population.
        for offset in (0, 1, 2, 3):
            whole = value(column_offset("B", offset))
            parts = value(column_offset("G", offset)) + value(
                column_offset("L", offset)
            )
            if sheet == "Women - NSA" and offset == 3:
                gap = NEET_WOMEN_NSA_POPULATION_GAPS[quarter.period]
                assert whole - parts == gap, (sheet, quarter, whole - parts)
                sa_row = quarter.row  # the SA sheet's rows are the NSA sheet's
                assert grid[("Women - SA", sa_row, "O")] == value("O") + gap
                continue
            assert abs(parts - whole) < 1e-6 * whole, (sheet, quarter, offset)


def build_neet() -> str:
    entry, content = pinned(NEET_DIRECTORY)
    grid = grid_of(source_cells_from_xlsx(content, metadata(entry["filename"])))
    notes = squeeze(" ".join(str(v) for (s, _, _), v in grid.items() if s == "Note"))
    for quote in NEET_NOTE_QUOTES:
        assert squeeze(quote) in notes, quote
    record_sets = []
    periods: list[Quarter] = []
    for sheet, sex, adjustment, title_end, groups in NEET_SHEETS:
        title = grid[(sheet, 1, "A")]
        assert (
            title
            == f"Not in Education, Employment or Training ('NEET') by age: {title_end}"
        )
        adjusted = adjustment.replace("_", " ")
        unit_line = f"United Kingdom (thousands) {adjusted}"
        assert grid[(sheet, 4, "B")] == unit_line, (sheet, grid.get((sheet, 4, "B")))
        sheet_text = squeeze(
            " ".join(str(v) for (s, _, _), v in grid.items() if s == sheet)
        )
        for quote in NEET_SHEET_QUOTES:
            assert squeeze(quote) in sheet_text, (sheet, quote)
        guards = [
            guard("A", 1, title, "table title"),
            guard("B", 4, unit_line, "geography, unit and adjustment"),
        ]
        for first, band, header, _, _ in groups:
            assert grid[(sheet, 5, first)] == header, (sheet, first)
            assert grid[(sheet, 6, first)] == "Young people who were NEET", (
                sheet,
                first,
            )
            for offset, _, header_row, text in NEET_COLUMNS:
                column = column_offset(first, offset)
                assert grid[(sheet, header_row, column)] == text, (sheet, column)
            guards.append(guard(first, 5, header, "age group"))
        population = (
            f"{'people' if sex == 'all' else 'men' if sex == 'male' else 'women'}, "
            f"{adjusted}"
        )
        sheet_quarters = quarters(grid, sheet, rolling=False)
        if not periods:
            periods = sheet_quarters
        assert [q.period for q in sheet_quarters] == [q.period for q in periods], sheet
        for quarter in sheet_quarters:
            row_values = [
                grid.get((sheet, quarter.row, column_offset(first, offset)))
                for first, *_ in groups
                for offset in range(5)
            ]
            assert all(is_number(value) for value in row_values), (sheet, quarter)
            neet_check_parity(grid, sheet, quarter, groups)
            filters, constraints = categories(
                ("sex", sex), ("seasonal_adjustment", adjustment)
            )
            sheet_slug = (
                sheet.lower().replace(" - ", "_").replace("-", "_").replace(" ", "_")
            )
            record_set_id = f"ons.neet.august_2026.{sheet_slug}.{quarter.slug}"
            revised = (
                " ONS marks the quarter [r], 'Data revised due to a seasonal "
                "adjustment review'."
                if quarter.revised
                else ""
            )
            record_sets.append(
                {
                    "record_set_id": record_set_id,
                    "provenance_class": "survey_aggregate",
                    "survey_instrument": LFS,
                    "assertion": "observation",
                    "record_set_spec_id": f"{record_set_id}.v1",
                    "source_record_id_prefix": record_set_id,
                    "sheet_name": sheet,
                    "period_type": "quarter",
                    "period": quarter.period,
                    "period_coverage": quarter_coverage(
                        quarter,
                        f"LFS estimate for the three months {quarter.label.removesuffix(' [r]')}, "
                        f"{adjusted}.{revised}",
                    ),
                    **UNITED_KINGDOM,
                    "entity": "person",
                    "entity_role": "young_person",
                    "domain": "employment",
                    "groupby_dimension": "ons.neet_quarter",
                    "shared_filters": filters,
                    "shared_constraints": constraints,
                    "rows": [
                        {
                            "value_id": quarter.slug,
                            "label": quarter.label.removesuffix(" [r]"),
                            "ordinal": 0,
                            "row_number": quarter.row,
                            "expected_row_header_column": "A",
                            "expected_row_header": quarter.label,
                            "table_record_kind": "detail",
                            "guard_cells": guards,
                        }
                    ],
                    "measures": numbered(
                        [
                            measure
                            for group in groups
                            for measure in neet_measures(group, sheet, population)
                        ]
                    ),
                }
            )
    payload = package_payload(
        package_id="ons-neet-august-2026",
        label=(
            "ONS young people not in education, employment or training (NEET), UK, "
            f"August 2026: ages 16 to 24 by sex, {periods[0].label.removesuffix(' [r]')} "
            f"to {periods[-1].label.removesuffix(' [r]')}"
        ),
        record_sets=record_sets,
        artifact={
            "source_name": "ons",
            "source_table": (
                "Young people not in education, employment or training (NEET), UK: "
                "August 2026, NEET Table 1"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{NEET_DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "neet_2026_08_27",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": f"xlsx used-range cell parse ({entry['filename']})",
            "parser": "xlsx_used_range",
            "artifact_year": 2026,
        },
    )
    header = f"""
    ONS 'Young people not in education, employment or training (NEET), UK: August 2026'
    (released 27 August 2026; next edition 26 November 2026), NEET Table 1, for {ISSUE}
    item 1 ({CONSUMER}#7). Written by {SCRIPT} from the pinned workbook.

    Every quarter from April to June 2024 to April to June 2026 of all nine data sheets:
    people, men and women, seasonally adjusted and not, at ages 16-24, 16-17 and 18-24,
    and the not seasonally adjusted sheets for people aged 18-20, 21-22 and 23-24 (which
    print no sex split). Each age group's five cells are ported: young people who were
    NEET (concept ons.lfs_neet_people, economic_activity all), of whom unemployed and
    economically inactive, the total people in the age group (ons.lfs_people) and the
    NEET share of it in per cent (ons.lfs_neet_rate). The sheets say 'thousands', which
    is the cells' display format ('#,##0,'): the cells hold people, so no scale applies.

    ONS's definition (bulletin glossary, {NEET_BULLETIN}): people are in education or
    training if they 'are enrolled on an education course and are still attending or
    waiting for term to start or restart', 'are doing an apprenticeship', 'are on a
    government-supported employment or training programme', 'are working or studying
    towards a qualification' or 'have had job-related training or education in the last
    four weeks'; 'Anybody who is not in any of the forms of education or training
    previously listed and not in employment is considered to be NEET', so 'a person
    identified as NEET will always be either unemployed or economically inactive'. Part-
    time study counts as education: LFS table A06's 'not in full-time education' is not
    NEET.

    Status: 'These labour market statistics, based on the Labour Force Survey, were
    designated as official statistics in development until 11 August 2026. They are now
    designated as official statistics' (the August 2026 bulletin); the workbook's Note
    sheet says 'These are official statistics'. Quality notes as published: 'Estimates
    from January to March 2025 include the full effect of the improvements in LFS data
    collection and sampling methods introduced from January 2024 onwards', with 'Some
    volatility' remaining 'particularly for estimates for mid-2023 and throughout 2024,
    and for granular breakdowns'; 'Data from January to March 2019 onward has been
    reweighted, causing a step change discontinuity'; the seasonally adjusted sheets
    mark quarters from January to March 2020 '[r]', 'Data revised due to a seasonal
    adjustment review', and each period's coverage notes carry the mark. No cell in the
    ported quarters is suppressed ('*').

    Parity, asserted by the generator for every ported row: 16-17 plus 18-24 is 16-24
    for NEET people, the unemployed, the inactive and the population; unemployed plus
    inactive is NEET; the share is NEET over the population. The bulletin's April to June
    2026 figures ('981,000 young people aged 16 to 24 years', 13.0%) are the People - SA
    sheet's to its rounding; tests/test_source_uk_young_people_facts.py checks them.

    One publisher inconsistency, ported as published: the 'Women - NSA' sheet's 18-24
    population (column O) is below the 'Women - SA' sheet's, LFS table A06 NSA's and
    its own 16-24 minus 16-17 in every ported quarter, by {min(NEET_WOMEN_NSA_POPULATION_GAPS.values()):,}
    to {max(NEET_WOMEN_NSA_POPULATION_GAPS.values()):,} people (April to June 2025 the
    most), and its 18-24 NEET share (column P) is computed on that population. The NEET
    counts on the sheet add up. The generator pins each quarter's gap, so a corrected
    edition fails the build rather than passing silently. {fact_count(payload)} facts.
    """
    return render(header, payload)


# ---------------------------------------------------------------- 2. LFS table A06

A06_PAGES = {
    "sa": (
        "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/"
        "employmentandemployeetypes/datasets/"
        "educationalstatusandlabourmarketstatusforpeopleagedfrom16to24seasonallyadjusteda06sa"
    ),
    "nsa": (
        "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/"
        "employmentandemployeetypes/datasets/"
        "educationalstatusandlabourmarketstatusforpeopleagedfrom16to24notseasonallyadjusteda06nsa"
    ),
}
# Each age group's 21 columns: the offset of each block from the group's first
# column, its full-time education status, and whether it holds levels or rates.
A06_BLOCKS = (
    (0, "all", "levels"),
    (4, "in_full_time_education", "levels"),
    (8, "not_in_full_time_education", "levels"),
    (12, "all", "rates"),
    (15, "in_full_time_education", "rates"),
    (18, "not_in_full_time_education", "rates"),
)
A06_LEVEL_STATUSES = ("all", "employed", "unemployed", "economically_inactive")
A06_RATE_STATUSES = ("employed", "unemployed", "economically_inactive")
A06_STATUS_TEXT = {
    "all": "Total",
    "employed": "Employed",
    "unemployed": "Unemployed",
    "economically_inactive": "Economically inactive",
}
A06_RATE_CONCEPTS = {
    "employed": (
        "ons.lfs_employment_rate",
        "employment rate",
        "people in employment as a percentage of all people in the group",
    ),
    "unemployed": (
        "ons.lfs_unemployment_rate",
        "unemployment rate",
        "unemployed people as a percentage of the economically active in the group",
    ),
    "economically_inactive": (
        "ons.lfs_economic_inactivity_rate",
        "economic inactivity rate",
        "economically inactive people as a percentage of all people in the group",
    ),
}
A06_GROUP_HEADER = re.compile(
    r"^All aged (\d+) to (\d+)(?: (in|not in) full-time education)?"
    r"(?: \((thousands|rates)\))? ?[\d,]*$"
)
A06_FOOTNOTES = (
    "1. Not in full-time education includes people in part-time education and/or some "
    "form of training. Estimates of the number of young people who are not in "
    'employment, education or training ("NEET") cannot therefore be derived from this '
    "table.",
    "2. People in full-time education are employed if they have a part-time job or "
    "unemployed if they are looking for part-time employment.",
    "3. Denominator = all persons in the relevant age group for economically active, "
    "total in employment and economically inactive; economically active for "
    "unemployment.",
    "4. Data from January to March 2019 onward has been reweighted, causing a step "
    "change discontinuity.",
    "Shaded estimates are based on a small sample size. This may result in less precise "
    "estimates, which should be used with caution.",
    "* Estimate has been suppressed on disclosure grounds.",
)
# Age groups: first column, age band, the ages the header names, lower and upper bound.
A06_GROUPS_16_24 = (
    ("B", "16_to_17", (16, 17), 16, 18),
    ("W", "18_to_24", (18, 24), 18, 25),
    ("AR", "16_to_24", (16, 24), 16, 25),
)
A06_GROUPS_18_24 = (
    ("B", "18_to_21", (18, 21), 18, 22),
    ("W", "22_to_24", (22, 24), 22, 25),
)
# The NSA 18_24 sheets repeat the 16_24 sheets' 18-24 group in columns AR to BL: it is
# asserted equal, cell by cell, and ported once.
A06_REPEATED_GROUP = ("AR", (18, 24))


@dataclass(frozen=True)
class A06Edition:
    key: str  # sa / nsa
    directory: str
    package_id: str
    adjustment: str
    groupby: str
    sheets: tuple  # (sheet, sex, title words, groups, repeats the 18-24 group)

    @property
    def adjusted(self) -> str:
        return self.adjustment.replace("_", " ")


A06_EDITIONS = (
    A06Edition(
        "sa",
        "ons/a06_sa_october_2026",
        "ons-a06-sa-october-2026",
        "seasonally_adjusted",
        "ons.a06_sa_quarter",
        (
            ("People", "all", "People aged 16 to 24", A06_GROUPS_16_24, False),
            ("Men", "male", "Men aged 16 to 24", A06_GROUPS_16_24, False),
            ("Women", "female", "Women aged 16 to 24", A06_GROUPS_16_24, False),
        ),
    ),
    A06Edition(
        "nsa",
        "ons/a06_nsa_october_2026",
        "ons-a06-nsa-october-2026",
        "not_seasonally_adjusted",
        "ons.a06_nsa_quarter",
        (
            ("People 16_24", "all", "People aged 16 to 24", A06_GROUPS_16_24, False),
            ("Men 16_24", "male", "Men aged 16 to 24", A06_GROUPS_16_24, False),
            ("Women 16_24", "female", "Women aged 16 to 24", A06_GROUPS_16_24, False),
            ("People 18_24", "all", "People aged 18 to 24", A06_GROUPS_18_24, True),
            ("Men 18_24", "male", "Men aged 18 to 24", A06_GROUPS_18_24, True),
            ("Women 18_24", "female", "Women aged 18 to 24", A06_GROUPS_18_24, True),
        ),
    ),
)


def a06_header_parts(text: str) -> tuple[int, int, str, str | None]:
    match = A06_GROUP_HEADER.match(text)
    assert match, text
    status = {
        None: "all",
        "in": "in_full_time_education",
        "not in": "not_in_full_time_education",
    }[match.group(3)]
    return int(match.group(1)), int(match.group(2)), status, match.group(4)


def a06_columns(grid: dict, sheet: str, first: str, ages: tuple[int, int]):
    """Yield (column, block, status, row-6 header) for an age group's 21 columns."""
    for offset, education, kind in A06_BLOCKS:
        header = grid[(sheet, 5, column_offset(first, offset))]
        lower, upper, status, unit = a06_header_parts(header)
        assert (lower, upper) == ages and status == education, (sheet, header)
        assert (unit == "rates") == (kind == "rates"), (sheet, header)
        statuses = A06_LEVEL_STATUSES if kind == "levels" else A06_RATE_STATUSES
        for index, economic in enumerate(statuses):
            column = column_offset(first, offset + index)
            text = grid[(sheet, 6, column)]
            assert re.sub(r"[\d,]+$", "", text) == A06_STATUS_TEXT[economic], (
                sheet,
                column,
                text,
            )
            assert grid[(sheet, 7, column)] == (
                "level" if kind == "levels" else "rate (%)"
            )
            yield column, (offset, education, kind, header), economic, text


def a06_measures(
    grid: dict, edition: A06Edition, sheet: str, row: int, group: tuple, population: str
) -> list[dict]:
    """The group's measures for one row; a suppressed cell ('*') has none."""
    first, band, ages, lower, upper = group
    age_filters, age_constraints = age_semantics(band, lower, upper)
    label_ages = AGE_BANDS[band]
    page = A06_PAGES[edition.key]
    measures = []
    for column, block, economic, text in a06_columns(grid, sheet, first, ages):
        if not is_number(grid[(sheet, row, column)]):
            continue
        _, education, kind, group_header = block
        education_filters, education_constraints = category(
            "full_time_education", education
        )
        place = (
            f"LFS table A06 {edition.key.upper()} (October 2026), sheet '{sheet}', column "
            f"{column} under '{group_header}' and '{text}'"
        )
        education_words = {
            "all": "",
            "in_full_time_education": " in full-time education",
            "not_in_full_time_education": " not in full-time education",
        }[education]
        if kind == "levels":
            status_filters, status_constraints = category("economic_activity", economic)
            what = {
                "all": "people",
                "employed": "people in employment",
                "unemployed": "unemployed people",
                "economically_inactive": "economically inactive people",
            }[economic]
            measures.append(
                measure_spec(
                    f"{band}__{education}__{economic}",
                    f"{what[0].upper()}{what[1:]} aged {label_ages}{education_words}",
                    len(measures),
                    column,
                    6,
                    text,
                    concept="ons.lfs_people",
                    unit="count",
                    aggregation="sum",
                    evidence_url=page,
                    notes=(
                        f"{place}: {what} aged {label_ages}{education_words}, {population}, "
                        "United Kingdom, people (the sheet's 'thousands' is the cells' display "
                        "format; the cells hold people)."
                    ),
                    filters=Flow(
                        {**age_filters, **education_filters, **status_filters}
                    ),
                    constraints=age_constraints
                    + education_constraints
                    + status_constraints,
                )
            )
        else:
            concept, name, definition = A06_RATE_CONCEPTS[economic]
            measures.append(
                measure_spec(
                    f"{band}__{education}__{economic}_rate",
                    f"{name[0].upper()}{name[1:]}, aged {label_ages}{education_words}",
                    len(measures),
                    column,
                    6,
                    text,
                    concept=concept,
                    unit="percent",
                    aggregation="rate",
                    evidence_url=page,
                    notes=(
                        f"{place}: the {name}, {definition} (footnote 3), aged "
                        f"{label_ages}{education_words}, {population}, United Kingdom."
                    ),
                    filters=Flow({**age_filters, **education_filters}),
                    constraints=age_constraints + education_constraints,
                )
            )
    return measures


A06_TOLERANCE = 1e-6  # relative; the LFS cells are unrounded weighted estimates


def a06_check_parity(
    grid: dict, sheet: str, row: int, groups: tuple, gaps: dict
) -> None:
    """Assert A06's identities on one row; a check with a suppressed cell is skipped."""

    def value(column: str) -> float | None:
        cell = grid[(sheet, row, column)]
        return cell if is_number(cell) else None

    def check(name: str, parts: list, whole: float | None, rate=None) -> None:
        if whole is None or any(part is None for part in parts):
            gaps["checks skipped for a suppressed cell"] = (
                gaps.get("checks skipped for a suppressed cell", 0) + 1
            )
            return
        computed = rate(*parts) if rate else sum(parts)
        gap = abs(computed - whole) / whole if whole else abs(computed - whole)
        gaps[name] = max(gaps.get(name, 0.0), gap)
        assert gap < A06_TOLERANCE, (sheet, row, name, parts, whole)

    levels = {}
    for first, band, *_ in groups:
        for offset, education, kind in A06_BLOCKS:
            if kind != "levels":
                continue
            cells = [value(column_offset(first, offset + index)) for index in range(4)]
            levels[(band, education)] = cells
            check("statuses add to the total", cells[1:], cells[0])
        for index in range(4):
            check(
                "in and not in full-time education add to the total",
                [
                    levels[(band, "in_full_time_education")][index],
                    levels[(band, "not_in_full_time_education")][index],
                ],
                levels[(band, "all")][index],
            )
        for offset, education, kind in A06_BLOCKS:
            if kind != "rates":
                continue
            total, employed, unemployed, inactive = levels[(band, education)]
            employed_rate, unemployed_rate, inactive_rate = (
                value(column_offset(first, offset + index)) for index in range(3)
            )
            check(
                "employment rate",
                [employed, total],
                employed_rate,
                rate=lambda part, whole: 100 * part / whole,
            )
            check(
                "unemployment rate",
                [unemployed, employed],
                unemployed_rate,
                rate=lambda part, other: 100 * part / (part + other),
            )
            check(
                "inactivity rate",
                [inactive, total],
                inactive_rate,
                rate=lambda part, whole: 100 * part / whole,
            )
    bands = [band for _, band, *_ in groups]
    if bands == ["16_to_17", "18_to_24", "16_to_24"]:
        for education in (
            "all",
            "in_full_time_education",
            "not_in_full_time_education",
        ):
            for index in range(4):
                check(
                    "16-17 and 18-24 add to 16-24",
                    [
                        levels[("16_to_17", education)][index],
                        levels[("18_to_24", education)][index],
                    ],
                    levels[("16_to_24", education)][index],
                )


def build_a06(edition: A06Edition) -> str:
    entry, content = pinned(edition.directory)
    grid = grid_of(source_cells_from_xls(content, metadata(entry["filename"])))
    note = squeeze(" ".join(str(v) for (s, _, _), v in grid.items() if s == "Note"))
    assert "These are official statistics." in note
    record_sets = []
    periods: list[Quarter] = []
    gaps: dict[str, float] = {}
    suppressed = 0
    for sheet, sex, title_words, groups, repeats in edition.sheets:
        title = grid[(sheet, 1, "A")]
        assert title == (
            "Table A06:  Educational status, economic activity & inactivity of young "
            f"people: {title_words} by educational status, economic activity and "
            f"inactivity ({edition.adjusted})"
        ), title
        unit_line = f"United Kingdom (thousands) {edition.adjusted}"
        assert grid[(sheet, 4, "A")] == unit_line, (sheet, grid.get((sheet, 4, "A")))
        sheet_text = squeeze(
            " ".join(str(v) for (s, _, _), v in grid.items() if s == sheet)
        )
        for quote in A06_FOOTNOTES:
            assert squeeze(quote) in sheet_text, (sheet, quote)
        guards = [
            guard("A", 1, title, "table title"),
            guard("A", 4, unit_line, "geography, unit and adjustment"),
        ]
        for first, _, ages, _, _ in groups:
            for offset, _, _ in A06_BLOCKS:
                column = column_offset(first, offset)
                guards.append(
                    guard(column, 5, grid[(sheet, 5, column)], "age group and status")
                )
        population = (
            f"{'people' if sex == 'all' else 'men' if sex == 'male' else 'women'}, "
            f"{edition.adjusted}"
        )
        sheet_quarters = quarters(grid, sheet, rolling=True)
        if not periods:
            periods = sheet_quarters
        assert [q.period for q in sheet_quarters] == [q.period for q in periods], sheet
        for quarter in sheet_quarters:
            cells = [
                grid.get((sheet, quarter.row, column_offset(first, index)))
                for first, *_ in groups
                for index in range(21)
            ]
            suppressed += sum(1 for cell in cells if cell == "*")
            assert all(is_number(cell) or cell == "*" for cell in cells), (
                sheet,
                quarter,
            )
            a06_check_parity(grid, sheet, quarter.row, groups, gaps)
            if repeats:
                # The repeated 18-24 group equals the 16_24 sheet's, cell by cell.
                first, ages = A06_REPEATED_GROUP
                assert grid[(sheet, 5, first)].startswith("All aged 18 to 24")
                other = sheet.replace("18_24", "16_24")
                for index in range(21):
                    # Equal to the last binary digit or so: ONS recomputes the rates.
                    repeated = grid[(sheet, quarter.row, column_offset(first, index))]
                    original = grid[(other, quarter.row, column_offset("W", index))]
                    assert abs(repeated - original) <= 1e-12 * abs(original), (
                        sheet,
                        quarter,
                        index,
                    )
                parts = [
                    grid[(sheet, quarter.row, column_offset(start, index))]
                    for start in ("B", "W")
                    for index in range(12)
                ]
                for index in range(12):
                    whole = grid[(sheet, quarter.row, column_offset(first, index))]
                    if not (is_number(parts[index]) and is_number(parts[12 + index])):
                        continue  # a suppressed 22-24 cell
                    gap = abs(parts[index] + parts[12 + index] - whole) / whole
                    gaps["18-21 and 22-24 add to 18-24"] = max(
                        gaps.get("18-21 and 22-24 add to 18-24", 0.0), gap
                    )
                    assert gap < A06_TOLERANCE, (sheet, quarter, index)
            filters, constraints = categories(
                ("sex", sex), ("seasonal_adjustment", edition.adjustment)
            )
            sheet_slug = sheet.lower().replace(" ", "_")
            record_set_id = (
                f"ons.a06_{edition.key}.october_2026.{sheet_slug}.{quarter.slug}"
            )
            record_sets.append(
                {
                    "record_set_id": record_set_id,
                    "provenance_class": "survey_aggregate",
                    "survey_instrument": LFS,
                    "assertion": "observation",
                    "record_set_spec_id": f"{record_set_id}.v1",
                    "source_record_id_prefix": record_set_id,
                    "sheet_name": sheet,
                    "period_type": "quarter",
                    "period": quarter.period,
                    "period_coverage": quarter_coverage(
                        quarter,
                        f"LFS estimate for the three months {quarter.label}, a rolling "
                        f"three-month period of table A06, {edition.adjusted}.",
                    ),
                    **UNITED_KINGDOM,
                    "entity": "person",
                    "entity_role": "young_person",
                    "domain": "employment",
                    "groupby_dimension": edition.groupby,
                    "shared_filters": filters,
                    "shared_constraints": constraints,
                    "rows": [
                        {
                            "value_id": quarter.slug,
                            "label": quarter.label,
                            "ordinal": 0,
                            "row_number": quarter.row,
                            "expected_row_header_column": "A",
                            "expected_row_header": quarter.label,
                            "table_record_kind": "detail",
                            "guard_cells": guards,
                        }
                    ],
                    "measures": numbered(
                        [
                            measure
                            for group in groups
                            for measure in a06_measures(
                                grid, edition, sheet, quarter.row, group, population
                            )
                        ]
                    ),
                }
            )
    payload = package_payload(
        package_id=edition.package_id,
        label=(
            f"ONS LFS table A06 {edition.key.upper()}: educational status and labour market "
            f"status of people aged 16 to 24 by sex, UK, {edition.adjusted}, "
            f"{periods[0].label} to {periods[-1].label} (October 2026)"
        ),
        record_sets=record_sets,
        artifact={
            "source_name": "ons",
            "source_table": (
                f"A06 {edition.key.upper()}: Educational status and labour market status "
                f"for people aged from 16 to 24 ({edition.adjusted}), October 2026"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{edition.directory}",
            "manifest": "manifest.yaml",
            "vintage": f"a06_{edition.key}_2026_10_20",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": f"xls used-range cell parse ({entry['filename']})",
            "parser": "xls_used_range",
            "artifact_year": 2026,
        },
    )
    sheets = ", ".join(f"'{sheet}'" for sheet, *_ in edition.sheets)
    nsa_ages = (
        """
        The not seasonally adjusted edition also splits 18-24 into 18-21 and 22-24 (the
        18_24 sheets). Those sheets print the 18-24 group a second time in columns AR to
        BL; the generator asserts it equal to the 16_24 sheets' cell by cell, and it is
        ported once, from the 16_24 sheets.
        """
        if edition.key == "nsa"
        else ""
    )
    max_gap = max(
        gap for name, gap in gaps.items() if not name.startswith("checks skipped")
    )
    skipped = gaps.get("checks skipped for a suppressed cell", 0)
    header = f"""
    ONS Labour Force Survey table A06 {edition.key.upper()}, 'Educational status, economic
    activity & inactivity of young people', United Kingdom, {edition.adjusted} (released
    20 October 2026; next edition 17 November 2026), for {ISSUE} item 2 ({CONSUMER}#7).
    Written by {SCRIPT} from the pinned workbook.

    Sheets {sheets}: people, men and women aged 16 to 17, 18 to 24 and 16 to 24 by
    full-time education (all, in, not in) and economic activity (all, employed,
    unemployed, economically inactive), as levels (concept ons.lfs_people) and as the
    employment, unemployment and inactivity rates (ons.lfs_employment_rate,
    ons.lfs_unemployment_rate, ons.lfs_economic_inactivity_rate). The sheets say
    'thousands', which is the cells' display format: the cells hold people, so no scale
    applies. {nsa_ages}

    Periods: A06 publishes rolling three-month periods every month. Chronicle's period
    types cover the calendar-quarter windows only (as chronicle#407 ported Nomis's
    April-to-March and January-to-December windows only), so this package ports January
    to March, April to June, July to September and October to December, from April to
    June 2024 to April to June 2026, each with its dates in period_coverage. The other
    rolling windows, including the latest, June to August 2026, have no period type and
    are not ported; July to September 2026 is in the 17 November edition.

    Footnotes as published: '1. Not in full-time education includes people in part-time
    education and/or some form of training. Estimates of the number of young people who
    are not in employment, education or training ("NEET") cannot therefore be derived
    from this table.' '2. People in full-time education are employed if they have a
    part-time job or unemployed if they are looking for part-time employment.' '3.
    Denominator = all persons in the relevant age group for economically active, total
    in employment and economically inactive; economically active for unemployment.' '4.
    Data from January to March 2019 onward has been reweighted, causing a step change
    discontinuity.' ONS shades estimates 'based on a small sample size', which 'should
    be used with caution'; Chronicle reads no shading, so a consumer that needs the flag
    goes back to the workbook. {suppressed} cells in the ported rows are suppressed
    ('*'); none emit facts.

    Status: the Note sheet says 'These are official statistics' (designated official
    statistics from 11 August 2026; until then official statistics in development).

    Parity, asserted by the generator for every ported row: employed, unemployed and
    inactive add to each total; in and not in full-time education add to the total;
    16-17 and 18-24 add to 16-24; each rate is its levels' quotient (unemployment over
    the economically active). The largest relative gap is {max_gap:.1e}; {skipped}
    checks that need a suppressed cell are skipped. {fact_count(payload)} facts.
    """
    return render(header, payload)


# ---------------------------------------------------------------- 4a. PAYE RTI by age

RTI_DIRECTORY = "ons/paye_rti_nsa_october_2026"
RTI_PACKAGE_DIRECTORY = "ons/paye_rti_age_nsa_october_2026"
RTI_PAGE = (
    "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/"
    "datasets/realtimeinformationstatisticsreferencetablenonseasonallyadjusted"
)
RTI_BULLETIN = (
    "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/"
    "bulletins/earningsandemploymentfrompayasyouearnrealtimeinformationuk/october2026"
)
# Sheet, its title, units line, measure kind, concept, unit, aggregation.
RTI_SHEETS = (
    (
        "28. Employees (Age)",
        "28. Payrolled employees from PAYE RTI",
        "Payrolled employees",
        "employees",
        "ons.paye_rti_payrolled_employees",
        "count",
        "sum",
    ),
    (
        "29. Median pay (Age)",
        "29. Median pay from PAYE RTI",
        "£ per month",
        "median_pay",
        "ons.paye_rti_median_monthly_pay",
        "gbp",
        "median",
    ),
    (
        "30. Mean pay (Age)",
        "30. Mean pay from PAYE RTI",
        "£ per month",
        "mean_pay",
        "ons.paye_rti_mean_monthly_pay",
        "gbp",
        "mean",
    ),
    (
        "31. Aggregate pay (Age)",
        "31. Aggregate pay from PAYE RTI",
        "£ per month, cells formatted to show in millions",
        "aggregate_pay",
        "ons.paye_rti_aggregate_monthly_pay",
        "gbp",
        "sum",
    ),
)
# Column, header, age band, lower and upper bound.
RTI_COLUMNS = (
    ("B", "0 to 17", "0_to_17", None, 18),
    ("C", "18 to 24", "18_to_24", 18, 25),
    ("D", "25 to 34", "25_to_34", 25, 35),
    ("E", "35 to 49", "35_to_49", 35, 50),
    ("F", "50 to 64", "50_to_64", 50, 65),
    ("G", "65 and over", "65_and_over", 65, None),
    ("H", "UK", "all", None, None),
)
RTI_FIRST_MONTH = date(2024, 4, 1)  # #420: April 2024 to the latest
RTI_INDEX_QUOTES = (
    "1. Figures for September 2026 are early estimates and are more likely to be subject "
    "to more significant revisions.",
    "2. These data are accredited official statistics.",
    "3. The number of payrolled employees here is defined as the number of people "
    "receiving paid renumeration included in PAYE RTI within the reference period, "
    "including people who have not done work but are an employee - such as those on "
    "paid leave.",
    "4. Values for the month are an average of employee counts in each day of the "
    "month. It is a measure of people who are payrolled employees, as opposed to a "
    "measure of employee jobs.",
    "5. These statistics include only individuals paid through PAYE and do not cover "
    "other sources of income such as from pensions, self-employment or investments.",
    "6. PAYE covers occupational pension income as well as employment. In these tables "
    "pension income is excluded.",
    "9. These data include imputation for payments not yet received by HMRC which would "
    "relate to the respective work periods.",
    "10. Figures have been rounded to the nearest £ or unit.",
    "12. Pay figures are based on gross earnings.",
)
RTI_FLASH_MONTH = "September 2026"
MONTH_NAMES = (
    "January February March April May June July August September October November "
    "December"
).split()


def rti_month(text: object) -> date | None:
    if not isinstance(text, str):
        return None
    parts = text.split()
    if len(parts) != 2 or parts[0] not in MONTH_NAMES or not parts[1].isdigit():
        return None
    return date(int(parts[1]), MONTH_NAMES.index(parts[0]) + 1, 1)


def month_end(month: date) -> date:
    following = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return date.fromordinal(following.toordinal() - 1)


def build_rti() -> str:
    entry, content = pinned(RTI_DIRECTORY)
    sheets = ["Index", *(sheet for sheet, *_ in RTI_SHEETS)]
    grid = grid_of(
        source_cells_from_xlsx(content, metadata(entry["filename"]), sheets=sheets)
    )
    index = squeeze(" ".join(str(v) for (s, _, _), v in grid.items() if s == "Index"))
    for quote in RTI_INDEX_QUOTES:
        assert squeeze(quote) in index, quote
    assert grid[("Index", 2, "A")] == "Date of publication: 20 October 2026"
    record_sets = []
    months_by_sheet = {}
    gaps = {"employees": 0, "aggregate_pay": 0}
    for sheet, title, units, kind, concept, unit, aggregation in RTI_SHEETS:
        assert grid[(sheet, 1, "A")] == title, sheet
        assert grid[(sheet, 2, "A")] == "UK, all industries, not seasonally adjusted"
        assert grid[(sheet, 4, "A")] == "Units" and grid[(sheet, 4, "B")] == units
        assert grid[(sheet, 6, "A")] == "Date"
        for column, header, *_ in RTI_COLUMNS:
            assert grid[(sheet, 6, column)] == header, (sheet, column)
        rows = sorted(
            (row, rti_month(value))
            for (name, row, column), value in grid.items()
            if name == sheet and column == "A" and rti_month(value) is not None
        )
        assert [row for row, _ in rows] == list(range(7, 7 + len(rows))), sheet
        ported = [(row, month) for row, month in rows if month >= RTI_FIRST_MONTH]
        for (_, before), (_, after) in zip(ported, ported[1:]):
            assert month_end(before).toordinal() + 1 == after.toordinal(), sheet
        months_by_sheet[sheet] = [month for _, month in ported]
        guards = [
            guard("A", 1, title, "table title"),
            guard("A", 2, "UK, all industries, not seasonally adjusted", "coverage"),
            guard("B", 4, units, "units"),
        ]
        for row, month in ported:
            values = [grid[(sheet, row, column)] for column, *_ in RTI_COLUMNS]
            assert all(is_number(value) for value in values), (sheet, month)
            if kind in gaps:
                gaps[kind] = max(gaps[kind], abs(sum(values[:-1]) - values[-1]))
            label = grid[(sheet, row, "A")]
            flash = label == RTI_FLASH_MONTH
            notes = {
                "employees": (
                    "Payrolled employees in the month, 'an average of employee counts in "
                    "each day of the month' (Index note 4)"
                ),
                "median_pay": "Median gross monthly pay of payrolled employees in the month",
                "mean_pay": "Mean gross monthly pay of payrolled employees in the month",
                "aggregate_pay": "Aggregate gross pay of payrolled employees in the month",
            }[kind]
            if flash:
                notes += (
                    "; 'Figures for September 2026 are early estimates and are more likely "
                    "to be subject to more significant revisions' (Index note 1)"
                )
            filters, constraints = categories(
                ("seasonal_adjustment", "not_seasonally_adjusted")
            )
            record_set_id = f"ons.paye_rti.october_2026.{kind}_by_age.{month:%Y_%m}"
            measures = []
            for column, header, band, lower, upper in RTI_COLUMNS:
                age_filters, age_constraints = age_semantics(band, lower, upper)
                ages = "all ages" if band == "all" else f"aged {AGE_BANDS[band]}"
                measures.append(
                    measure_spec(
                        f"{kind}_{band}",
                        {
                            "employees": f"Payrolled employees, {ages}",
                            "median_pay": f"Median monthly pay, {ages}",
                            "mean_pay": f"Mean monthly pay, {ages}",
                            "aggregate_pay": f"Aggregate monthly pay, {ages}",
                        }[kind],
                        len(measures),
                        column,
                        6,
                        header,
                        concept=concept,
                        unit=unit,
                        aggregation=aggregation,
                        evidence_url=RTI_PAGE,
                        notes=(
                            f"PAYE RTI non-seasonally adjusted reference table (October 2026), "
                            f"sheet '{sheet}', column {column} ('{header}'): "
                            f"{notes[0].lower()}{notes[1:]}, {ages} (age at the time of "
                            "payment), United Kingdom, in "
                            + ("people." if kind == "employees" else "pounds (gross).")
                        ),
                        filters=age_filters,
                        constraints=age_constraints,
                    )
                )
            record_sets.append(
                {
                    "record_set_id": record_set_id,
                    "provenance_class": "administrative",
                    "assertion": "observation",
                    "record_set_spec_id": f"{record_set_id}.v1",
                    "source_record_id_prefix": record_set_id,
                    "sheet_name": sheet,
                    "period_type": "month",
                    "period": f"{month:%Y-%m}",
                    "period_coverage": {
                        "start_date": f"{month:%Y-%m-%d}",
                        "end_date": f"{month_end(month):%Y-%m-%d}",
                        "basis": "calendar",
                        "source_period_label": label,
                        "notes": f"{notes}.",
                    },
                    **UNITED_KINGDOM,
                    "entity": "person",
                    "entity_role": "payrolled_employee",
                    "domain": "employment_earnings",
                    "groupby_dimension": "ons.paye_rti_month",
                    "shared_filters": filters,
                    "shared_constraints": constraints,
                    "rows": [
                        {
                            "value_id": f"{month:%Y_%m}",
                            "label": label,
                            "ordinal": 0,
                            "row_number": row,
                            "expected_row_header_column": "A",
                            "expected_row_header": label,
                            "table_record_kind": "detail",
                            "guard_cells": guards,
                        }
                    ],
                    "measures": measures,
                }
            )
    # Employees and median pay run to the flash month; mean and aggregate pay stop a
    # month earlier.
    assert (
        months_by_sheet["28. Employees (Age)"]
        == months_by_sheet["29. Median pay (Age)"]
    )
    assert (
        months_by_sheet["30. Mean pay (Age)"]
        == months_by_sheet["31. Aggregate pay (Age)"]
    )
    assert (
        months_by_sheet["28. Employees (Age)"][:-1]
        == months_by_sheet["30. Mean pay (Age)"]
    )
    assert months_by_sheet["28. Employees (Age)"][-1] == date(2026, 9, 1)
    assert gaps["employees"] <= 2 and gaps["aggregate_pay"] <= 2, gaps
    payload = package_payload(
        package_id="ons-paye-rti-age-nsa-october-2026",
        label=(
            "ONS and HMRC PAYE Real Time Information: payrolled employees and median, mean "
            "and aggregate monthly pay by age band, UK, not seasonally adjusted, April "
            "2024 to September 2026 (October 2026)"
        ),
        record_sets=record_sets,
        artifact={
            "source_name": "ons",
            "source_table": (
                "Earnings and employment from Pay As You Earn Real Time Information, "
                "non-seasonally adjusted, October 2026: Tables 28 to 31 (age)"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{RTI_DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "paye_rti_nsa_2026_10_20",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": (
                f"xlsx used-range cell parse ({entry['filename']}), sheets Index and 28 "
                "to 31"
            ),
            "parser": "xlsx_used_range",
            "sheets": sheets,
            "artifact_year": 2026,
        },
    )
    header = f"""
    Earnings and employment from Pay As You Earn Real Time Information (PAYE RTI), UK,
    non-seasonally adjusted reference table, October 2026 (ONS with HM Revenue and
    Customs; released 20 October 2026, next 17 November 2026), Tables 28 to 31: payrolled
    employees and median, mean and aggregate monthly pay by age band, for {ISSUE} item 4a
    ({CONSUMER}#6, PolicyEngine/microcosm#1374). Written by {SCRIPT} from the pinned
    workbook.

    Every month from April 2024: employees and median pay to September 2026, mean and
    aggregate pay to August 2026, the sheets' last rows. Age bands as published, 0 to
    17, 18 to 24, 25 to 34, 35 to 49, 50 to 64 and 65 and over, and the UK column (all
    ages). The table publishes no single years of age, so #420's single years at 16 to
    24 are not available here, and no band splits at 21: 18 to 24 is the closest.

    Semantics as published: 'The age figures in this bulletin are calculated based on an
    individual's age at the time they receive a payment' (October 2026 bulletin,
    {RTI_BULLETIN}); 'The number of payrolled employees here is defined as the number of
    people receiving paid renumeration included in PAYE RTI within the reference period'
    and 'Values for the month are an average of employee counts in each day of the
    month. It is a measure of people who are payrolled employees, as opposed to a
    measure of employee jobs' (Index notes 3 and 4), so each employee counts once
    whatever their number of jobs; 'These statistics include only individuals paid
    through PAYE and do not cover other sources of income such as from pensions,
    self-employment or investments' (note 5), and occupational pension income is
    excluded (note 6); the data 'include imputation for payments not yet received by
    HMRC' (note 9); 'Figures have been rounded to the nearest £ or unit' (note 10); pay
    is gross (note 12). Aggregate pay is in pounds, 'cells formatted to show in
    millions'. 'These data are accredited official statistics' (note 2).

    Revisions: 'Figures for September 2026 are early estimates and are more likely to be
    subject to more significant revisions' (note 1); its coverage notes say so. Later
    editions revise recent months, so a consumer pins this edition or moves to a newer
    one; it does not mix months across editions.

    Parity, asserted by the generator for every ported month: the six bands add to the
    UK column for employees (largest gap {gaps["employees"]}) and for aggregate pay
    (largest gap £{gaps["aggregate_pay"]}, the UK figure's rounding). {fact_count(payload)}
    facts.
    """
    return render(header, payload)


# ---------------------------------------------------------------- 4b. ASHE Table 6

ASHE6_PAGE = (
    "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/"
    "datasets/agegroupashetable6"
)
ASHE_INSTRUMENT = "Annual Survey of Hours and Earnings"
BULLETINS = (
    "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/"
    "bulletins/annualsurveyofhoursandearnings/"
)
# Sheet, the Chronicle sex and working pattern it reads, and the population its title names.
ASHE_SHEETS = (
    ("All", "all", "all", "all employee jobs"),
    ("Male", "male", "all", "male employee jobs"),
    ("Female", "female", "all", "female employee jobs"),
    ("Full-Time", "all", "full_time", "full-time employee jobs"),
    ("Part-Time", "all", "part_time", "part-time employee jobs"),
    ("Male Full-Time", "male", "full_time", "male full-time employee jobs"),
    ("Male Part-Time", "male", "part_time", "male part-time employee jobs"),
    ("Female Full-Time", "female", "full_time", "female full-time employee jobs"),
    ("Female Part-Time", "female", "part_time", "female part-time employee jobs"),
)
ALL_EMPLOYEES_ROW, NOT_CLASSIFIED_ROW = 6, 14
# Row, printed label (after its indent), age band, lower and upper bound.
ASHE6_AGE_GROUPS = (
    (7, "16-17b", "16_to_17", 16, 18),
    (8, "18-21", "18_to_21", 18, 22),
    (9, "22-29", "22_to_29", 22, 30),
    (10, "30-39", "30_to_39", 30, 40),
    (11, "40-49", "40_to_49", 40, 50),
    (12, "50-59", "50_to_59", 50, 60),
    (13, "60+", "60_and_over", 60, None),
)
PERCENTILES = (10, 20, 25, 30, 40, 60, 70, 75, 80, 90)
# Ported columns: measure id, column, header row, header text.
ASHE_COLUMNS = (
    ("jobs", "C", 4, "of jobsc"),
    ("median", "D", 5, "Median"),
    ("mean", "F", 5, "Mean"),
    *(
        (f"p{percentile}", get_column_letter(8 + index), 5, percentile)
        for index, percentile in enumerate(PERCENTILES)
    ),
)
assert ASHE_COLUMNS[-1][1] == "Q"


@dataclass(frozen=True)
class AsheEdition:
    slug: str
    year: int
    status: str
    released: str
    reference_date: str
    reference_label: str
    bulletin: str
    bulletin_url: str
    headline_weekly: str
    headline_annual: str
    member_prefix: str

    @property
    def directory(self) -> str:
        return f"ons/ashe_table6_{self.slug}"


ASHE_EDITIONS = (
    AsheEdition(
        slug="2024_revised",
        year=2024,
        status="revised",
        released="23 October 2025",
        reference_date="2024-04-17",
        reference_label="17 April 2024",
        bulletin="Employee earnings in the UK: 2025",
        bulletin_url=BULLETINS + "2025",
        headline_weekly="£728.27 in April 2024",
        headline_annual="£37,439 in April 2024",
        member_prefix="",
    ),
    AsheEdition(
        slug="2025_revised",
        year=2025,
        status="revised",
        released="22 October 2026",
        reference_date="2025-04-30",
        reference_label="30 April 2025",
        bulletin="Employee earnings in the UK: 2026",
        bulletin_url=BULLETINS + "2026",
        headline_weekly="£766.60 in April 2025",
        headline_annual="£39,157 in April 2025",
        member_prefix="",
    ),
    AsheEdition(
        slug="2026_provisional",
        year=2026,
        status="provisional",
        released="22 October 2026",
        reference_date="2026-04-22",
        reference_label="22 April 2026",
        bulletin="Employee earnings in the UK: 2026",
        bulletin_url=BULLETINS + "2026",
        headline_weekly="£811.20 in April 2026",
        headline_annual="£40,911 in April 2026",
        member_prefix="PROV - ",
    ),
)


@dataclass(frozen=True)
class AsheTable:
    key: str  # 1a
    pay: str  # weekly / annual
    cv: bool

    @property
    def number(self) -> str:
        return f"Table 6.{self.key}"

    @property
    def title(self) -> str:
        return {"weekly": "Weekly pay - Gross", "annual": "Annual pay - Gross"}[
            self.pay
        ]

    @property
    def slug(self) -> str:
        return f"{self.pay}_pay_gross" + ("_cv" if self.cv else "")

    def member(self, edition: AsheEdition) -> str:
        suffix = " CV" if self.cv else ""
        return (
            f"{edition.member_prefix}Age Group {self.number}   {self.title} "
            f"{edition.year}{suffix}.xlsx"
        )

    def package_id(self, edition: AsheEdition) -> str:
        return f"ons-ashe-table6-{self.slug.replace('_', '-')}-{edition.slug.replace('_', '-')}"

    def directory(self, edition: AsheEdition) -> str:
        return f"ons/ashe_table6_{self.slug}_{edition.slug}"


ASHE_TABLES = (
    AsheTable("1a", "weekly", False),
    AsheTable("1b", "weekly", True),
    AsheTable("7a", "annual", False),
    AsheTable("7b", "annual", True),
)


def ashe_grid(edition: AsheEdition, table: AsheTable) -> tuple[str, dict]:
    _, content = pinned(edition.directory)
    member = table.member(edition)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        (name,) = [item for item in archive.namelist() if item.endswith(member)]
        member_content = archive.read(name)
    return name, grid_of(source_cells_from_xlsx(member_content, metadata(name)))


def ashe_measure(
    edition: AsheEdition,
    table: AsheTable,
    sheet: str,
    population: str,
    spec: tuple,
    young: bool,
) -> dict:
    measure_id, column, header_row, header = spec
    pay = "gross weekly pay" if table.pay == "weekly" else "gross annual pay"
    concept = f"ons.ashe_gross_{table.pay}_pay"
    filters = constraints = None
    if measure_id == "jobs":
        concept = f"ons.ashe_{table.pay}_pay_jobs"
        label = "Number of jobs"
        what = (
            f"the number of jobs (thousand) in the {pay} estimates, which ONS calls "
            "'for indicative purposes only' (footnote c)"
        )
        unit, aggregation, scale = "count", "sum", 1000
    elif measure_id == "median":
        label, what = f"Median {pay}", f"median {pay} (£)"
        unit, aggregation, scale = "gbp", "median", None
    elif measure_id == "mean":
        label, what = f"Mean {pay}", f"mean {pay} (£)"
        unit, aggregation, scale = "gbp", "mean", None
    else:
        label, what = (
            f"{header}th percentile of {pay}",
            f"the {header}th percentile of {pay} (£)",
        )
        unit, aggregation, scale = "gbp", "quantile", None
        filters = Flow(earnings_percentile=header)
        constraints = [
            constraint(
                "earnings_percentile", header, DIMENSION_LABELS["earnings_percentile"]
            )
        ]
    if table.cv:
        # A concept of its own, as Table 2's CVs have, so a CV is never read as pay.
        concept = f"{concept}_coefficient_of_variation"
        label = f"Coefficient of variation: {label[0].lower()}{label[1:]}"
        what = f"the coefficient of variation (per cent) of {what}"
        unit, scale = "percent", None
    young_words = (
        "; for 16 to 17 year olds the figures 'include employees not on adult rates of "
        "pay' (footnote b)"
        if young
        else ""
    )
    return measure_spec(
        measure_id,
        label,
        [item[0] for item in ASHE_COLUMNS].index(measure_id),
        column,
        header_row,
        header,
        concept=concept,
        unit=unit,
        aggregation=aggregation,
        evidence_url=ASHE6_PAGE,
        notes=(
            f"ASHE {table.number} ({edition.year} {edition.status}), sheet '{sheet}', "
            f"column {column}: {what}, {population}, United Kingdom{young_words}."
        ),
        filters=filters,
        constraints=constraints,
        scale=scale,
    )


def ashe_coverage(
    edition: AsheEdition, table: AsheTable, young: bool
) -> tuple[str, int, dict]:
    young_words = (
        " Figures for 16 to 17 year olds 'include employees not on adult rates of pay' "
        "(footnote b)."
        if young
        else ""
    )
    if table.pay == "weekly":
        return (
            "calendar_year",
            edition.year,
            {
                "start_date": edition.reference_date,
                "end_date": edition.reference_date,
                "basis": "survey_reference",
                "source_period_label": f"Pay period including {edition.reference_label}",
                "notes": (
                    f"ASHE {edition.year} {edition.status} estimates 'relate to the pay "
                    f"period that includes {edition.reference_label}' ({edition.bulletin}); "
                    "employees on adult rates whose pay for the survey pay-period was not "
                    f"affected by absence (table footnote a).{young_words}"
                ),
            },
        )
    opening = edition.year - 1
    return (
        "tax_year",
        opening,
        {
            "start_date": f"{opening}-04-06",
            "end_date": f"{edition.year}-04-05",
            "basis": "tax",
            "source_period_label": f"Tax year ending 5 April {edition.year}",
            "notes": (
                "'Annual estimates are provided for the tax year that ended on 5th April "
                f"in the reference year' (Notes sheet), here {edition.year}; employees on "
                "adult rates who have been in the same job for more than a year (table "
                "footnote a). ASHE samples their jobs in the pay period including "
                f"{edition.reference_label}.{young_words}"
            ),
        },
    )


# Sentences the package headers quote, asserted against the workbooks' notes sheets
# and footnotes (whitespace normalised).
NOTES_QUOTES = (
    "ASHE covers employee jobs in the United Kingdom. It does not cover the "
    "self-employed, nor does it cover employees not paid during the reference period.",
    "ASHE is based on a 1% sample of jobs taken from HM Revenue and Customs' Pay As You "
    "Earn (PAYE) records. Consequently, individuals with more than one job may appear "
    "in the sample more than once.",
    "Annual estimates are provided for the tax year that ended on 5th April in the "
    "reference year.",
    "Estimates with a CV greater than 20% are suppressed from publication on quality "
    "grounds",
)
CV_NOTES_QUOTES = (
    "The CV is the ratio of the standard error of an estimate to the estimate itself "
    "and is expressed as a percentage.",
    "Estimates with a CV greater than 20% are suppressed from publication on quality "
    "grounds",
)
FOOTNOTE_A = {
    "weekly": "a Employees on adult rates whose pay for the survey pay-period was not "
    "affected by absence.",
    "annual": "a Employees on adult rates who have been in the same job for more than "
    "a year.",
}
FOOTNOTE_B = (
    "b Figures for 16 to 17 year olds include employees not on adult rates of pay."
)
FOOTNOTE_C = (
    "c Figures for Number of Jobs are for indicative purposes only and should not be "
    "considered an accurate estimate of employee job counts."
)


def sheet_text(grid: dict, sheet: str) -> str:
    cells = sorted(
        (row, column, value)
        for (name, row, column), value in grid.items()
        if name == sheet
    )
    return squeeze(" ".join(str(value) for _, _, value in cells))


def build_ashe(edition: AsheEdition, table: AsheTable) -> str:
    member, grid = ashe_grid(edition, table)
    estimates = AsheTable(table.key[0] + "a", table.pay, False)
    _, estimates_grid = ashe_grid(edition, estimates) if table.cv else (member, grid)
    notes = sheet_text(estimates_grid, "Notes")
    for quote in NOTES_QUOTES:
        assert squeeze(quote) in notes, quote
    if table.cv:
        cv_notes = sheet_text(grid, "CV notes")
        for quote in CV_NOTES_QUOTES:
            assert squeeze(quote) in cv_notes, quote
    record_sets = []
    suppressed = 0
    for sheet, sex, pattern, population in ASHE_SHEETS:
        title = grid[(sheet, 1, "A")]
        kind = (
            f"Coefficients of variation for {table.title} (£)"
            if table.cv
            else f"{table.title} (£)"
        )
        assert f"{kind} - For {population}a: United Kingdom" in title, title
        # "Table 6 .1a ... 2025" from 2025, "Table 6.1a ..., 2024" in 2024.
        assert re.match(rf"^Table 6 ?\.{table.key} ", title), title
        assert title.endswith(str(edition.year)), title
        for _, column, header_row, header in ASHE_COLUMNS:
            assert grid[(sheet, header_row, column)] == header, (sheet, column)
        assert (
            grid[(sheet, 3, "C")] == "Number" and grid[(sheet, 4, "H")] == "Percentiles"
        )
        assert grid[(sheet, NOT_CLASSIFIED_ROW, "A")] == "Not Classified"
        assert grid[(sheet, NOT_CLASSIFIED_ROW, "C")] == ":"
        assert not any(
            (sheet, NOT_CLASSIFIED_ROW, column) in grid
            for _, column, _, _ in ASHE_COLUMNS[1:]
        )
        assert squeeze(grid[(sheet, 15, "A")]).startswith(FOOTNOTE_A[table.pay]), sheet
        assert squeeze(grid[(sheet, 16, "A")]) == FOOTNOTE_B, sheet
        assert squeeze(grid[(sheet, 17, "A")]) == FOOTNOTE_C, sheet
        assert grid[(sheet, ALL_EMPLOYEES_ROW, "A")] == "All employees"
        rows_spec = [(ALL_EMPLOYEES_ROW, "All employees", "all", None, None)] + [
            (row, label, band, lower, upper)
            for row, label, band, lower, upper in ASHE6_AGE_GROUPS
        ]
        by_signature: dict[tuple, list[dict]] = {}
        for ordinal, (row, label, band, lower, upper) in enumerate(rows_spec):
            text = grid[(sheet, row, "A")]
            assert squeeze(text) == label, (sheet, row, text)
            assert (sheet, row, "B") not in grid, (sheet, row)
            ported = []
            for measure_id, column, _, _ in ASHE_COLUMNS:
                value = grid.get((sheet, row, column))
                if is_number(value):
                    ported.append(measure_id)
                    continue
                # 'x' is a CV over 20 per cent, in both tables; a CV table may also
                # print '.', 'unavailable' in its key.
                assert value == "x" or (table.cv and value == "."), (
                    sheet,
                    row,
                    column,
                    value,
                )
                suppressed += 1
            if not ported:
                continue
            spec = {
                "value_id": band,
                "label": AGE_BAND_LABELS[band],
                "ordinal": ordinal,
                "row_number": row,
                "expected_row_header_column": "A",
                "expected_row_header": text,
                "table_record_kind": "total" if band == "all" else "detail",
            }
            if band != "all":
                spec["filters"], spec["constraints"] = age_semantics(band, lower, upper)
            young = band == "16_to_17"
            by_signature.setdefault((tuple(ported), young), []).append(spec)
        statistic = "coefficient_of_variation" if table.cv else "estimate"
        filters, constraints = categories(
            ("sex", sex), ("working_pattern", pattern), ("statistic", statistic)
        )
        sheet_slug = sheet.lower().replace("-", "_").replace(" ", "_")
        period_type, period, _ = ashe_coverage(edition, table, False)
        for (signature, young), rows in by_signature.items():
            first = rows[0]
            first["guard_cells"] = [guard("A", 1, title, "table title")]
            missing = [item[0] for item in ASHE_COLUMNS if item[0] not in signature]
            record_set_id = f"ons.ashe_table6.{edition.slug}.{table.slug}.{sheet_slug}"
            if young:
                record_set_id += ".age_16_to_17"
            if missing:
                record_set_id += ".without_" + "_".join(missing)
            record_sets.append(
                {
                    "record_set_id": record_set_id,
                    "provenance_class": "survey_aggregate",
                    "survey_instrument": ASHE_INSTRUMENT,
                    "assertion": "observation",
                    "record_set_spec_id": f"{record_set_id}.v1",
                    "source_record_id_prefix": record_set_id,
                    "sheet_name": sheet,
                    "period_type": period_type,
                    "period": period,
                    "period_coverage": ashe_coverage(edition, table, young)[2],
                    **UNITED_KINGDOM,
                    "entity": "person",
                    "entity_role": "employee_job",
                    "domain": "employment_earnings",
                    "groupby_dimension": "age_band",
                    "shared_filters": filters,
                    "shared_constraints": constraints,
                    "rows": rows,
                    "measures": [
                        ashe_measure(edition, table, sheet, population, spec, young)
                        for spec in ASHE_COLUMNS
                        if spec[0] in signature
                    ],
                }
            )
    status = f"{edition.year} {edition.status}"
    kind = "coefficients of variation for " if table.cv else ""
    payload = package_payload(
        package_id=table.package_id(edition),
        label=(
            f"ONS ASHE {table.number}: {kind}{table.title.lower()} by age group, sex and "
            f"working pattern, United Kingdom, {status}"
        ),
        record_sets=record_sets,
        artifact={
            "source_name": "ons",
            "source_table": (
                f"ASHE Table 6 (age group), {table.number} "
                f"{'Coefficients of variation for ' if table.cv else ''}{table.title} (£), "
                f"United Kingdom, {status}"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{edition.directory}",
            "manifest": "manifest.yaml",
            "vintage": f"ashe_table6_{edition.slug}",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": f"ZIP member xlsx used-range cell parse ({member})",
            "parser": "zip_xlsx_used_range",
            "archive_member": member,
            "artifact_year": edition.year,
        },
    )
    other = AsheTable(
        table.key[0] + ("a" if table.cv else "b"), table.pay, not table.cv
    )
    if table.cv:
        content = f"""
        The coefficient of variation (CV) ONS publishes for each estimate in
        {other.number} ({other.package_id(edition)}): 'The CV is the ratio of the
        standard error of an estimate to the estimate itself and is expressed as a
        percentage' (CV notes). Each fact takes its estimate's concept with the suffix
        _coefficient_of_variation, so a CV is never read as pay or jobs, and keeps the
        estimate's aggregation and dimensions, with statistic coefficient_of_variation
        and unit percent.
        """
        marks = (
            "A cell marked 'x' (CV over 20 per cent; the estimate is suppressed) or '.' "
            "('unavailable' in the CV key) emits no fact."
        )
    else:
        content = f"""
        The number of jobs (thousand; 'for indicative purposes only and should not be
        considered an accurate estimate of employee job counts', footnote c), the
        median, the mean and the 10th to 90th percentiles of {table.pay} pay, with
        statistic estimate; the annual percentage changes are not ported. ONS colours
        each estimate by its coefficient of variation; Chronicle reads no colours, and
        {other.number} ({other.package_id(edition)}) carries the CVs.
        """
        marks = (
            "A cell ONS suppresses ('x': 'Estimates with a CV greater than 20% are "
            "suppressed from publication on quality grounds') emits no fact."
        )
    headline = (
        edition.headline_weekly if table.pay == "weekly" else edition.headline_annual
    )
    parity = (
        ""
        if table.cv
        else f"""
        Parity: the full-time all-employees median (sheet 'Full-Time', row 6) is the
        figure {edition.bulletin} ({edition.bulletin_url}) prints, {headline}, to the
        bulletin's rounding, and every sheet's 'All employees' row is ASHE Table 2's
        (chronicle#407's ons-ashe-table2-{table.slug.replace("_", "-")}-{edition.slug.replace("_", "-")}),
        so the two tables' total facts share a semantic key; the age groups' jobs add to
        the all-employees jobs within the thousands' rounding. tests/test_source_uk_young_people_facts.py
        checks all three.
        """
    )
    header = f"""
    ONS Annual Survey of Hours and Earnings (ASHE) Table 6, age group, {table.number}
    '{kind}{table.title} (£)', United Kingdom, {status} (released {edition.released}),
    for {ISSUE} item 4b ({CONSUMER}#6). Written by {SCRIPT} from the member '{member}' of
    the pinned zip.

    Every sheet but the notes is ported: all employee jobs, male, female, full-time,
    part-time, and the four sex by working-pattern sheets. Each sheet's 'All employees'
    row is its record sets' total; its seven age groups, 16-17, 18-21, 22-29, 30-39,
    40-49, 50-59 and 60+, carry age_band with age bounds (groupby age_band). The 16-17
    row sits in record sets of its own ('age_16_to_17'), whose notes carry footnote b:
    'Figures for 16 to 17 year olds include employees not on adult rates of pay', where
    every other row covers employees on adult rates (footnote a). {content}

    {marks} A row with such a cell sits in a record set whose measures leave that
    column out ('without_p90' and the like), so the row's other cells are ported. The
    'Not Classified' row prints ':' ('not applicable') and emits no fact. {suppressed}
    marked cells are not ported; {fact_count(payload)} facts.

    ASHE counts employee jobs, not people: it 'is based on a 1% sample of jobs taken
    from HM Revenue and Customs' Pay As You Earn (PAYE) records', so 'individuals with
    more than one job may appear in the sample more than once', and it 'does not cover
    the self-employed, nor does it cover employees not paid during the reference
    period' (Notes sheet).

    {ashe_coverage(edition, table, False)[2]["notes"]}
    {parity}
    """
    return render(header, payload)


# ---------------------------------------------------------------- 9. HMRC NICs reliefs

RELIEF_DIRECTORY = "hmrc/tax_relief_statistics_january_2026"
RELIEF_PACKAGE_DIRECTORY = "hmrc/employer_nics_age_reliefs_january_2026"
RELIEF_PAGE = "https://www.gov.uk/government/statistics/tax-reliefs/tax-relief-statistics-january-2026"
# Relief, its Table 2 and Table 5 rows, code and name as printed.
RELIEFS = (
    (
        "apprentices_under_25",
        79,
        56,
        "NIC - NS1",
        "Relief on employer National Insurance contributions for apprentices under 25",
        "A zero rate of Class 1 secondary NICs for apprentices under 25 up to the "
        "apprentice upper secondary threshold",
    ),
    (
        "employees_under_21",
        80,
        57,
        "NIC - NS2",
        "Relief on employer National Insurance contributions for employees under 21",
        "A zero rate of Class 1 secondary NICs for employees under 21 up to the upper "
        "secondary threshold",
    ),
)
TAX_YEAR_COLUMNS = (
    ("F", 2020),
    ("G", 2021),
    ("H", 2022),
    ("I", 2023),
    ("J", 2024),
    ("K", 2025),
)


def tax_year_label(opening: int) -> str:
    return f"{opening} to {opening + 1}"


def build_reliefs() -> str:
    entry, content = pinned(RELIEF_DIRECTORY)
    grid = grid_of(
        source_cells_from_ods(
            content, metadata(entry["filename"]), coerce_numeric_text=True
        )
    )
    assert grid[("Cover_sheet", 3, "A")] == "Release date: 22 January 2026"
    tables = {
        "Table_2": (
            "Table 2: Six-year cost estimates (figures given in £ million)",
            "First forecasted costing year",
        ),
        "Table_5": ("Table 5: Claimants estimates", "First forecasted claimant year"),
    }
    for sheet, (title, forecast_header) in tables.items():
        assert grid[(sheet, 1, "A")] == title, sheet
        headers = {
            "A": "Name",
            "B": "Code",
            "C": "Tax type",
            "D": "Relief type",
            "E": forecast_header,
        }
        headers.update(
            {column: tax_year_label(year) for column, year in TAX_YEAR_COLUMNS}
        )
        for column, text in headers.items():
            assert grid[(sheet, 2, column)] == text, (sheet, column)
    notes_text = grid[("Table_2", 80, "N")]
    assert grid[("Table_2", 79, "N")].startswith(
        "The under 25 apprentice employer NICs relief takes precedence over the under 21 "
        "employer NICs relief (for apprentices under the age of 21)."
    )
    assert notes_text.endswith(
        "As this is a relief for the employer, we report the number of employers claiming "
        "the relief."
    )
    record_sets = []
    published = {}
    for sheet in ("Table_2", "Table_5"):
        cost = sheet == "Table_2"
        forecasts = set()
        rows_by_year: dict[int, list[dict]] = {}
        for relief, cost_row, claimant_row, code, name, description in RELIEFS:
            row = cost_row if cost else claimant_row
            assert grid[(sheet, row, "A")] == name, (sheet, row)
            assert grid[(sheet, row, "B")] == code and grid[(sheet, row, "C")] == "NICs"
            assert grid[(sheet, row, "D")] == "Non-structural"
            assert grid[(sheet, row, "L")] == description, (sheet, row)
            first_forecast = grid[(sheet, row, "E")]
            forecasts.add(first_forecast)
            for column, year in TAX_YEAR_COLUMNS:
                value = grid[(sheet, row, column)]
                if value == "Not available":
                    continue
                assert is_number(value), (sheet, row, column, value)
                published[(sheet, relief, year)] = value
                filters, constraints = category("employer_nics_relief", relief)
                rows_by_year.setdefault(year, []).append(
                    {
                        "value_id": relief,
                        "label": name,
                        "ordinal": len(rows_by_year.get(year, [])),
                        "row_number": row,
                        "expected_row_header_column": "A",
                        "expected_row_header": name,
                        "table_record_kind": "detail",
                        "filters": filters,
                        "constraints": constraints,
                        "guard_cells": [
                            guard("B", row, code, "relief code"),
                            guard("E", row, first_forecast, forecast_header_text(cost)),
                        ],
                    }
                )
        assert len(forecasts) == 1, (sheet, forecasts)
        (first_forecast,) = forecasts
        forecast_year = (
            int(first_forecast.split()[0])
            if first_forecast != "Not available"
            else None
        )
        for year, rows in sorted(rows_by_year.items()):
            projection = forecast_year is not None and year >= forecast_year
            column = dict((y, c) for c, y in TAX_YEAR_COLUMNS)[year]
            kind = "cost" if cost else "claimants"
            record_set_id = (
                f"hmrc.tax_reliefs.january_2026.employer_nics_age.{kind}.ty{year}"
            )
            rows[0]["guard_cells"] = [
                guard("A", 1, grid[(sheet, 1, "A")], "table title")
            ] + rows[0]["guard_cells"]
            record_sets.append(
                {
                    "record_set_id": record_set_id,
                    "provenance_class": "administrative",
                    "assertion": "source_projection" if projection else "observation",
                    "record_set_spec_id": f"{record_set_id}.v1",
                    "source_record_id_prefix": record_set_id,
                    "sheet_name": sheet,
                    "period_type": "tax_year",
                    "period": year,
                    "period_coverage": {
                        "start_date": f"{year}-04-06",
                        "end_date": f"{year + 1}-04-05",
                        "basis": "tax",
                        "source_period_label": tax_year_label(year),
                        "notes": (
                            f"HMRC's forecast: Table 2's 'First forecasted costing year' is "
                            f"'{first_forecast}'."
                            if projection
                            else (
                                "HMRC's estimate for a year before its first forecast year "
                                f"('{first_forecast}')."
                                if cost
                                else "Table 5 gives claimants for years with data only."
                            )
                        ),
                    },
                    **UNITED_KINGDOM,
                    "entity": "firm",
                    "entity_role": "employer",
                    "domain": "national_insurance_reliefs",
                    "groupby_dimension": "employer_nics_relief",
                    "rows": rows,
                    "measures": [
                        measure_spec(
                            f"{kind}_{year}",
                            (
                                f"Cost of the relief, {tax_year_label(year)}"
                                if cost
                                else f"Employers claiming the relief, {tax_year_label(year)}"
                            ),
                            0,
                            column,
                            2,
                            tax_year_label(year),
                            concept="hmrc.tax_relief_cost"
                            if cost
                            else "hmrc.tax_relief_claimants",
                            unit="gbp" if cost else "count",
                            aggregation="sum",
                            evidence_url=RELIEF_PAGE,
                            authority="hmrc",
                            notes=(
                                (
                                    "HMRC tax relief statistics (January 2026), Table 2 "
                                    "'Six-year cost estimates (figures given in £ million)', "
                                    f"column {column} ('{tax_year_label(year)}'): the "
                                    "estimated cost of the relief, £ million."
                                )
                                if cost
                                else (
                                    "HMRC tax relief statistics (January 2026), Table 5 "
                                    f"'Claimants estimates', column {column} "
                                    f"('{tax_year_label(year)}'): 'As this is a relief for "
                                    "the employer, we report the number of employers "
                                    "claiming the relief' (Table 2's notes)."
                                )
                            ),
                            scale=1_000_000 if cost else None,
                        )
                    ],
                }
            )
    payload = package_payload(
        package_id="hmrc-employer-nics-age-reliefs-january-2026",
        label=(
            "HMRC tax relief statistics (January 2026): cost and claimants of the employer "
            "NICs reliefs for employees under 21 and apprentices under 25, 2020-21 to 2025-26"
        ),
        record_sets=record_sets,
        artifact={
            "source_name": "hmrc",
            "source_table": (
                "Tax relief statistics (January 2026), Table 2 (six-year cost estimates) and "
                "Table 5 (claimants estimates)"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{RELIEF_DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "tax_relief_statistics_2026_01_22",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": (
                f"ODS used-range cell parse with numeric text read as numbers ({entry['filename']})"
            ),
            "parser": "ods_numeric_text_used_range",
            "artifact_year": 2026,
        },
    )
    under_21 = [
        published[("Table_2", "employees_under_21", year)]
        for _, year in TAX_YEAR_COLUMNS
    ]
    claimants = [
        published[("Table_5", "employees_under_21", year)]
        for _, year in TAX_YEAR_COLUMNS
        if ("Table_5", "employees_under_21", year) in published
    ]
    # The HTML page's section 3.28 prints the same under-21 series.
    assert under_21 == [560, 670, 850, 960, 1100, 1900], under_21
    assert claimants == [270000, 321000, 326000, 330000, 340000], claimants
    header = f"""
    HMRC 'Tax relief statistics (January 2026)' (published 22 January 2026), {RELIEF_PAGE},
    the employer National Insurance reliefs for young employees, for {ISSUE} item 9
    ({CONSUMER}#6): the cost of each relief in Table 2 ('Six-year cost estimates (figures
    given in £ million)') and its claimants in Table 5 ('Claimants estimates'). Written
    by {SCRIPT} from the pinned workbook.

    The two reliefs, as HMRC describes them: 'Relief on employer National Insurance
    contributions for employees under 21' (NIC - NS2), 'A zero rate of Class 1 secondary
    NICs for employees under 21 up to the upper secondary threshold'; and 'Relief on
    employer National Insurance contributions for apprentices under 25' (NIC - NS1), 'A
    zero rate of Class 1 secondary NICs for apprentices under 25 up to the apprentice
    upper secondary threshold'. HMRC's notes: 'The under 25 apprentice employer NICs
    relief takes precedence over the under 21 employer NICs relief (for apprentices
    under the age of 21)', so the two costs do not overlap; 'The larger than usual
    increase in cost presented in the 2025-26 forecast is expected due to the employer
    NICs changes which came into effect in April 2025, namely the reduction of the
    secondary threshold from £9,100 to £5,000 and the increase of the employer NICs rate
    from 13.8% to 15%'; and 'As this is a relief for the employer, we report the number
    of employers claiming the relief', so the claimants are employers (entity firm).

    Years 2020-21 to 2025-26, period the opening year (tax_year 2020 is 2020 to 2021).
    Table 2's 'First forecasted costing year' is '2025 to 2026' for both reliefs, so the
    2025-26 costs are HMRC's forecast (assertion source_projection) and the earlier years
    its estimates (observation). Table 5 prints no 2025-26 claimants ('Not available'),
    which emit no fact. The cost cells are numbers held as text in the workbook ('1,100'),
    read as numbers by the parser. The publication page's section 3.28 prints the same
    under-21 series (560, 670, 850, 960, 1,100 and 1,900*, £ million; 270,000 to 340,000
    claimants); the generator asserts it. {fact_count(payload)} facts.
    """
    return render(header, payload)


def forecast_header_text(cost: bool) -> str:
    return "first forecasted costing year" if cost else "first forecasted claimant year"


# ---------------------------------------------------------------- the packages

BUILDERS = {
    NEET_DIRECTORY: build_neet,
    **{
        edition.directory: (lambda edition=edition: build_a06(edition))
        for edition in A06_EDITIONS
    },
    RTI_PACKAGE_DIRECTORY: build_rti,
    **{
        table.directory(edition): (
            lambda edition=edition, table=table: build_ashe(edition, table)
        )
        for edition in ASHE_EDITIONS
        for table in ASHE_TABLES
    },
    RELIEF_PACKAGE_DIRECTORY: build_reliefs,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the generated YAML with the committed files instead of writing.",
    )
    args = parser.parse_args()
    stale = []
    for directory, build in BUILDERS.items():
        text = build()
        path = PACKAGES / directory / "source_package.yaml"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(directory)
        else:
            write(directory, text)
    for directory in stale:
        print(f"stale: packages/{directory}/source_package.yaml")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
