"""Generate the source package for PolicyEngine/chronicle#420 item 5: PIP point scores.

Run from the repository root:

    uv run python scripts/build_dwp_pathways_evidence_pack_package.py

``--check`` compares the generated YAML with the committed file instead of writing.
The package is written from its pinned artifact, read with Chronicle's own ODS parser,
so every row number, column and guard cell below is one the package parser sees. The
publisher's text is asserted cell by cell, and the parity checks the header reports
are asserted on the published cells, so a run against different bytes fails rather
than drifting. Nothing is downloaded and no value is computed into a fact.

- ``dwp-pathways-to-work-pip-points-january-2025``: DWP's "Pathways to Work: Evidence
  pack: Chapter 2 reforming the structure" data tables (ODS, revised 23 July 2025),
  Tables 2.9 to 2.12 (daily living and mobility points by age and by primary health
  condition), 2.19 to 2.22 (the most points scored on any one daily living activity:
  overall, by daily living award, by age and by condition), 2.27 (points on each daily
  living activity) and 2.28 (2.27 by condition), for working-age PIP claimants under
  normal rules on the January 2025 caseload under DWP policy ownership.
"""

from __future__ import annotations

import argparse
import hashlib
import textwrap
from dataclasses import dataclass
from pathlib import Path

import yaml
from openpyxl.utils import column_index_from_string, get_column_letter

from chronicle.sources.cells import SourceArtifactMetadata, source_cells_from_ods

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-11-06"
ISSUE = "PolicyEngine/chronicle#420"
CONSUMER = "PolicyEngine/uk-pip-review-2026#3"
SCRIPT = "scripts/build_dwp_pathways_evidence_pack_package.py"
RAW_DIRECTORY = "dwp/pathways_to_work_evidence_pack_chapter_2_2025"
PACKAGE_DIRECTORY = "dwp/pathways_to_work_pip_points_january_2025"
PACKAGE_ID = "dwp-pathways-to-work-pip-points-january-2025"
PAGE = (
    "https://www.gov.uk/government/consultations/"
    "pathways-to-work-reforming-benefits-and-support-to-get-britain-working-green-paper/"
    "pathways-to-work-evidence-pack-chapter-2-reforming-the-structure"
)
FOI_PACKAGE_ID = "dwp-pip-daily-living-foi-2025"


class Flow(dict):
    """A small mapping written on one line, as the families package writes guards."""


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


def write(directory: str, text: str) -> None:
    path = PACKAGES / directory / "source_package.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def constraint(variable: str, value: object, label: str, operator: str = "==") -> Flow:
    return Flow(variable=variable, operator=operator, value=value, label=label)


def guard(column: str, row: int, value: object, label: str) -> Flow:
    return Flow(column=column, row=row, expected_value=value, label=label)


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def squeeze(text: object) -> str:
    return " ".join(str(text).replace("\xa0", " ").split())


# ---------------------------------------------------------------- dimensions

# The population every table describes, as the FOI2025/24990 package
# (dwp-pip-daily-living-foi-2025) words it for the same January 2025 caseload.
SCOPE = (
    ("pip_policy_ownership", "dwp", "DWP policy ownership (England, Wales and Abroad)"),
    ("pip_claimant_age_group", "working_age", "Working-age claimants"),
    (
        "pip_claim_rules",
        "normal_rules",
        "Normal rules only (special rules for end of life excluded)",
    ),
)
DAILY_LIVING_AWARDED = "standard_or_enhanced"

AGE_GROUPS = (
    # printed text, value id, label, lower bound, upper bound (exclusive). The labels
    # take the register's 'Age 65 and over' wording, as the chronicle#420 young people
    # packages' age bands do.
    ("16 - 19", "16_to_19", "Age 16 to 19", 16, 20),
    ("20 - 29", "20_to_29", "Age 20 to 29", 20, 30),
    ("30 - 39", "30_to_39", "Age 30 to 39", 30, 40),
    ("40 - 49", "40_to_49", "Age 40 to 49", 40, 50),
    ("50 - 59", "50_to_59", "Age 50 to 59", 50, 60),
    ("60+", "60_and_over", "Age 60 and over", 60, None),
)
# The 18 condition groups Tables 2.11, 2.12 and 2.22 print, then their 'All Other
# Conditions' and 'Unknown or Missing' rows, in the order printed.
CONDITIONS = (
    ("Cancer", "cancer"),
    ("Anxiety and Depression", "anxiety_and_depression"),
    ("Autistic Spectrum Disorders", "autistic_spectrum_disorders"),
    ("Learning Disabilities", "learning_disabilities"),
    ("ADHD / ADD", "adhd_add"),
    ("Psychotic Disorders", "psychotic_disorders"),
    ("Other Psychiatric Disorders", "other_psychiatric_disorders"),
    ("Arthritis", "arthritis"),
    ("Chronic Pain Syndromes", "chronic_pain_syndromes"),
    ("Back Pain", "back_pain"),
    (
        "Other Regional Musculoskeletal Diseases",
        "other_regional_musculoskeletal_diseases",
    ),
    ("Cerebrovascular Diseases", "cerebrovascular_diseases"),
    ("Epilepsy", "epilepsy"),
    (
        "Multiple Sclerosis and Neuropathic Diseases",
        "multiple_sclerosis_and_neuropathic_diseases",
    ),
    (
        "Cerebral Palsy and Neurological Muscular Diseases",
        "cerebral_palsy_and_neurological_muscular_diseases",
    ),
    ("Other Neurological Diseases", "other_neurological_diseases"),
    ("Respiratory Diseases", "respiratory_diseases"),
    ("Cardiovascular Diseases", "cardiovascular_diseases"),
    ("All Other Conditions", "all_other_conditions"),
    ("Unknown or Missing", "unknown_or_missing"),
)
# Table 2.28 prints five condition groups and its own 'All other conditions', which
# takes in the other 13 groups of Table 2.11 and 'Unknown or Missing' (note 9), so it
# is a different group from Table 2.11's 'All Other Conditions'.
CONDITIONS_2_28 = (
    ("Anxiety and Depression", "anxiety_and_depression"),
    ("Arthritis", "arthritis"),
    ("Learning Disabilities", "learning_disabilities"),
    ("Back Pain", "back_pain"),
    ("Autistic Spectrum Disorders", "autistic_spectrum_disorders"),
    ("All other conditions", "all_other_conditions_outside_five_groups"),
)
ACTIVITIES = (
    "Preparing food",
    "Taking nutrition",
    "Managing therapy or monitoring a health condition",
    "Washing and bathing",
    "Managing toilet needs or incontinence",
    "Dressing and undressing",
    "Communicating verbally",
    "Reading and understanding signs, symbols and words",
    "Engaging with other people face to face",
    "Making budgeting decisions",
)

DIMENSION_LABELS = {
    "pip_policy_ownership": "PIP policy ownership",
    "pip_claimant_age_group": "Claimant age group",
    "pip_claim_rules": "PIP claim rules",
    "pip_daily_living_award_rate": "PIP daily living award rate",
    "age_band": "Age band",
    "pip_primary_health_condition_group": "Primary health condition group",
    "pip_daily_living_points_band": "PIP daily living points band",
    "pip_mobility_points": "PIP mobility points",
    "pip_max_daily_living_activity_points": (
        "Most points scored on any one daily living activity"
    ),
    "pip_daily_living_activity": "PIP daily living activity",
    "pip_daily_living_activity_points": "Points scored on the daily living activity",
}
VALUE_LABELS = {
    # The FOI2025/24990 package's labels for the values the two packages share.
    "pip_policy_ownership": {"dwp": "DWP (England, Wales and abroad)"},
    "pip_claimant_age_group": {"working_age": "Working age"},
    "pip_claim_rules": {
        "normal_rules": "Normal rules (special rules for end of life excluded)"
    },
    "pip_daily_living_award_rate": {
        "enhanced": "Enhanced",
        "standard": "Standard",
        DAILY_LIVING_AWARDED: "Standard or enhanced (in receipt of the daily living component)",
    },
    "age_band": {
        "all": "All ages",
        **{value_id: label for _, value_id, label, _, _ in AGE_GROUPS},
    },
    "pip_primary_health_condition_group": {
        "all": "All health conditions",
        **{value_id: text for text, value_id in CONDITIONS},
        "all_other_conditions": "All Other Conditions (outside the 18 groups shown)",
        "all_other_conditions_outside_five_groups": (
            "All other conditions (outside the five groups shown, Unknown or Missing included)"
        ),
    },
}


# ---------------------------------------------------------------- point columns


@dataclass(frozen=True)
class Points:
    """One points column: its measure id, header cell, filter value and bounds."""

    measure_id: str
    header: object
    value: object
    low: int
    high: int | None  # inclusive; None is open


# Tables 2.9 and 2.11: daily living points in bands, columns B to M.
DAILY_LIVING_BANDS = tuple(
    Points(
        measure_id=f"points_{low}_to_{high}"
        if high is not None
        else f"points_{low}_and_over",
        header=f"{low}-{high}" if high is not None else f"{low}+",
        value=f"{low}_to_{high}" if high is not None else f"{low}_and_over",
        low=low,
        high=high,
    )
    for low, high in (
        (0, 3),
        (4, 7),
        (8, 9),
        (10, 11),
        (12, 13),
        (14, 15),
        (16, 20),
        (21, 25),
        (26, 30),
        (31, 35),
        (36, 40),
        (41, None),
    )
)
VALUE_LABELS["pip_daily_living_points_band"] = {
    band.value: str(band.header) for band in DAILY_LIVING_BANDS
}


def exact_points(scores: tuple[int, ...], prefix: str = "points") -> tuple[Points, ...]:
    return tuple(
        Points(
            measure_id=f"{prefix}_{score}",
            header=score,
            value=score,
            low=score,
            high=score,
        )
        for score in scores
    )


# Tables 2.10 and 2.12: the mobility total, every total the two activities can make.
MOBILITY_POINTS = exact_points((0, 4, 8, 10, 12, 14, 16, 18, 20, 22, 24))
# Tables 2.19 to 2.22: the most points scored on any one daily living activity.
MAX_ACTIVITY_POINTS = exact_points((2, 3, 4, 6, 8, 10, 12), prefix="max_points")
# Tables 2.27 and 2.28: the points scored on each activity.
ACTIVITY_POINTS = exact_points((0, 1, 2, 3, 4, 6, 8, 10, 12))


@dataclass(frozen=True)
class Family:
    """What one kind of table measures."""

    key: str
    dimension: str  # the points filter
    share_concept: str
    claimants_concept: str | None
    what: str  # the share, in words
    base: str  # the claimants the share is of


FAMILIES = {
    "daily_living": Family(
        key="daily_living",
        dimension="pip_daily_living_points_band",
        share_concept="dwp.pip_daily_living_points_share",
        claimants_concept="dwp.pip_daily_living_points_claimants",
        what="the share of the group's claimants whose daily living points total falls in the band",
        base="claimants in the group (the share's base)",
    ),
    "mobility": Family(
        key="mobility",
        dimension="pip_mobility_points",
        share_concept="dwp.pip_mobility_points_share",
        claimants_concept="dwp.pip_mobility_points_claimants",
        what="the share of the group's claimants whose mobility points total is the value",
        base="claimants in the group (the share's base)",
    ),
    "max_activity": Family(
        key="max_activity",
        dimension="pip_max_daily_living_activity_points",
        share_concept="dwp.pip_max_daily_living_activity_points_share",
        claimants_concept="dwp.pip_max_daily_living_activity_points_claimants",
        what=(
            "the share of the group's daily living claimants whose highest score on any "
            "one daily living activity is the value"
        ),
        base="daily living claimants in the group (the share's base)",
    ),
    "activity": Family(
        key="activity",
        dimension="pip_daily_living_activity_points",
        share_concept="dwp.pip_daily_living_activity_points_share",
        claimants_concept=None,
        what="the share of daily living claimants scoring the value on the activity",
        base="",
    ),
}


# ---------------------------------------------------------------- the workbook

SOURCE_LINE = "Figures derived from DWP administrative data"
# Key phrases of the scope notes, found in each table's notes and guarded whole.
NOTE_PHRASES = {
    "caseload": "Figures are based on the PIP caseload at end January 2025",
    "working_age": "working age claimants",
    "ownership": (
        "Data only includes claimants living in regions under DWP policy ownership "
        "(England, Wales and Abroad)."
    ),
    "normal_rules": (
        "Data includes normal rules claimants only, and excludes special rules for end "
        "of life (SREL) claimants as they typically receive maximum or very high scores."
    ),
    "daily_living": "Data only includes claimants awarded Daily Living component",
}


@dataclass(frozen=True)
class Table:
    key: str  # 2.9
    sheet: str
    item: str  # the chapter's chart number
    family: str
    breakdown: str  # age / condition / award / overall / activity / activity_condition
    title_row: int
    title: str
    header_row: int
    first_column: str  # the first points column
    volume_column: str | None
    # Where the parser reads the volume heading, and the text: a heading after a
    # merged range moves left, because the parser keeps no covered cells.
    volume_heading: tuple[str, int, str] | None
    first_row: int
    last_row: int
    daily_living_only: bool
    label_column: str = "A"

    @property
    def points(self) -> tuple[Points, ...]:
        return {
            "daily_living": DAILY_LIVING_BANDS,
            "mobility": MOBILITY_POINTS,
            "max_activity": MAX_ACTIVITY_POINTS,
            "activity": ACTIVITY_POINTS,
        }[self.family]

    @property
    def columns(self) -> tuple[str, ...]:
        start = column_index_from_string(self.first_column)
        return tuple(get_column_letter(start + i) for i in range(len(self.points)))

    @property
    def slug(self) -> str:
        return "t" + self.key.replace(".", "_")


TABLES = (
    Table(
        key="2.9",
        sheet="T2_9_PIP_DL_Points_by_age",
        item="2.9",
        family="daily_living",
        breakdown="age",
        title_row=9,
        title=(
            "Table 2.9: Daily Living points scored by age group of claimant (January 2025 "
            "normal rules caseload)"
        ),
        header_row=12,
        first_column="B",
        volume_column="N",
        volume_heading=("C", 11, "Volume in age group"),
        first_row=13,
        last_row=19,
        daily_living_only=False,
    ),
    Table(
        key="2.10",
        sheet="T2_10_PIP_Mob_Points_by_age",
        item="2.10",
        family="mobility",
        breakdown="age",
        title_row=10,
        title=(
            "Table 2.10: Mobility points scored by age group of claimant (January 2025 "
            "normal rules caseload)"
        ),
        header_row=13,
        first_column="B",
        volume_column="M",
        volume_heading=("C", 12, "Volume in age group"),
        first_row=14,
        last_row=20,
        daily_living_only=False,
    ),
    Table(
        key="2.11",
        sheet="T2_11_PIP_DL_Pts_by_condition",
        item="2.11",
        family="daily_living",
        breakdown="condition",
        title_row=9,
        title=(
            "Table 2.11: Daily Living points scored by primary health condition of "
            "claimant (January 2025 normal rules caseload)"
        ),
        header_row=12,
        first_column="B",
        volume_column="N",
        volume_heading=("C", 11, "Volume in each condition category"),
        first_row=13,
        last_row=33,
        daily_living_only=False,
    ),
    Table(
        key="2.12",
        sheet="T2_12_PIP_Mob_Pts_by_condition",
        item="2.12",
        family="mobility",
        breakdown="condition",
        title_row=9,
        title=(
            "Table 2.12: Mobility points scored by primary health condition of claimant "
            "(January 2025 normal rules caseload)"
        ),
        header_row=12,
        first_column="B",
        volume_column="M",
        volume_heading=("C", 11, "Volume in each condition category"),
        first_row=13,
        last_row=33,
        daily_living_only=False,
    ),
    Table(
        key="2.19",
        sheet="T2_19_Max_DL_pts_-_Caseload",
        item="2.19",
        family="max_activity",
        breakdown="overall",
        title_row=9,
        title=(
            "Table 2.19: Maximum points scored on any Daily Living activity by PIP "
            "claimants awarded Daily Living component"
        ),
        header_row=12,
        first_column="B",
        volume_column="I",
        volume_heading=("I", 12, "Volume"),
        first_row=13,
        last_row=13,
        daily_living_only=True,
    ),
    Table(
        key="2.20",
        sheet="T2_20_Max_DL_pts_-_DL_Award",
        item="2.20",
        family="max_activity",
        breakdown="award",
        title_row=9,
        title=(
            "Table 2.20: Maximum points scored on any Daily Living activity by PIP "
            "claimants per Daily Living Award"
        ),
        header_row=12,
        first_column="B",
        volume_column="I",
        volume_heading=("C", 11, "Volume in award group"),
        first_row=13,
        last_row=15,
        daily_living_only=True,
    ),
    Table(
        key="2.21",
        sheet="T2_21_Max_DL_pts_-_Age",
        item="2.21",
        family="max_activity",
        breakdown="age",
        title_row=9,
        title=(
            "Table 2.21 : Maximum points scored on Daily Living activity by age group of "
            "claimant (January 2025 normal rules caseload)"
        ),
        header_row=12,
        first_column="B",
        volume_column="I",
        volume_heading=("I", 12, "Volume in age group"),
        first_row=13,
        last_row=19,
        daily_living_only=True,
    ),
    Table(
        key="2.22",
        sheet="T2_22_Max_DL_pts_-_Condition",
        item="2.22",
        family="max_activity",
        breakdown="condition",
        title_row=9,
        title=(
            "Table 2.22: Maximum points scored on Daily Living activity by primary health "
            "condition of claimant (January 2025 normal rules caseload)"
        ),
        header_row=12,
        first_column="B",
        volume_column="I",
        volume_heading=("C", 11, "Volume in each condition category"),
        first_row=13,
        last_row=33,
        daily_living_only=True,
    ),
    Table(
        key="2.27",
        sheet="T2_27_DL_pts_by_activity",
        item="2.27",
        family="activity",
        breakdown="activity",
        title_row=9,
        title=(
            "Table 2.27: Proportion of PIP claimants point scores for each of the Daily "
            "Living activities (January 2025 normal rules caseload)"
        ),
        header_row=12,
        first_column="D",
        volume_column=None,
        volume_heading=None,
        first_row=13,
        last_row=22,
        daily_living_only=True,
        label_column="C",
    ),
    Table(
        key="2.28",
        sheet="T2_28_DL_pts_activity_condition",
        item="",
        family="activity",
        breakdown="activity_condition",
        title_row=4,
        title=(
            "Table 2.28: Proportion of Working Age PIP claimants point scores for each of "
            "the Daily Living activities by primary health condition of claimant "
            "(January 2025 normal rules caseload)"
        ),
        header_row=8,
        first_column="D",
        volume_column=None,
        volume_heading=None,
        first_row=9,
        last_row=79,
        daily_living_only=True,
        label_column="C",
    ),
)
TABLES_BY_KEY = {table.key: table for table in TABLES}
TOTAL_ROW_TEXT = {
    "age": "All ages",
    "condition": "All health conditions",
}
DAILY_LIVING_TOTAL = "All working age claimants in receipt of Daily Living component"
AWARD_ROWS = (
    ("Enhanced Daily Living", "enhanced"),
    ("Standard Daily Living", "standard"),
)
# Table 2.11's 'All health conditions' row (row 13) prints its bands in text order:
# the cell under '4-7' holds the share at 10-11 points, and so on, because '10-11'
# sorts before '4-7' as text. Every misplaced cell is the volume-weighted average of
# the 20 condition rows for the band text order gives it; the generator asserts this
# and ports only the row's '0-3' cell, which is in place, and its volume.
TEXT_ORDER_EXCLUSION = ("2.11", 13)
TEXT_ORDER_TOLERANCE = 0.02
# Table 2.28's Arthritis 'Activity 1 - Preparing food' row (row 22) prints 79.83 at 2
# points, the cell of the Anxiety and Depression block's row 10, and adds to 98.74.
# Weighted by Table 2.22's daily living volumes (the 'All other conditions' weight
# being the total less the five groups'), Table 2.28's blocks reproduce Table 2.27 in
# every cell but this one, where the gap is Arthritis's weight times the row's
# shortfall; the generator asserts this and does not port the cell.
COPIED_CELL = ("2.28", 22, "F")
COPIED_FROM_ROW = 10
COPIED_TOLERANCE = 0.01
REPRODUCTION_TOLERANCE = 0.02
MARKER = "-"


def workbook() -> tuple[dict, str, dict]:
    entry, content = pinned(RAW_DIRECTORY)
    cells = source_cells_from_ods(content, metadata(entry["filename"]))
    grid: dict[tuple[str, int, str], object] = {}
    for cell in cells:
        if cell.raw_value in (None, ""):
            continue
        grid[
            (cell.sheet_name, cell.row_number, get_column_letter(cell.column_number))
        ] = cell.raw_value
    return grid, entry["filename"], entry


def note_cell(grid: dict, table: Table, phrase: str) -> tuple[int, str]:
    """The one column-A cell of the sheet's notes that contains the phrase."""
    hits = [
        (row, text)
        for (sheet, row, column), text in grid.items()
        if sheet == table.sheet
        and column == "A"
        and row > table.last_row
        and isinstance(text, str)
        and phrase.lower() in text.lower()
    ]
    assert len(hits) == 1, (table.key, phrase, hits)
    return hits[0]


def scope_guards(grid: dict, table: Table) -> list[Flow]:
    guards = [guard("A", table.title_row, table.title, "table title")]
    phrases = ["caseload", "working_age", "ownership", "normal_rules"]
    if table.daily_living_only:
        phrases.append("daily_living")
    for key in phrases:
        row, text = note_cell(grid, table, NOTE_PHRASES[key])
        guards.append(guard("A", row, text, f"note: {key.replace('_', ' ')}"))
    row, text = note_cell(grid, table, SOURCE_LINE)
    assert text == SOURCE_LINE, (table.key, text)
    guards.append(guard("A", row, text, "source"))
    return guards


# ---------------------------------------------------------------- measures


def share_measure(table: Table, points: Points, column: str, ordinal: int) -> dict:
    family = FAMILIES[table.family]
    header = points.header
    if family.key == "daily_living":
        label = f"Share with {header} daily living points"
        bounds = [
            constraint(
                "pip_daily_living_points",
                points.low,
                "Daily living points lower bound",
                ">=",
            )
        ]
        if points.high is not None:
            bounds.append(
                constraint(
                    "pip_daily_living_points",
                    points.high,
                    "Daily living points upper bound",
                    "<=",
                )
            )
    elif family.key == "mobility":
        label = f"Share with {header} mobility points"
        bounds = []
    elif family.key == "max_activity":
        label = (
            f"Share whose highest score on any one daily living activity is {header}"
        )
        bounds = []
    else:
        label = f"Share scoring {header} on the activity"
        bounds = []
    notes = (
        f"DWP Pathways to Work evidence pack, chapter 2, Table {table.key} (sheet "
        f"'{table.sheet}'), column {column} headed {header!r}: {family.what}, as a "
        f"percentage, as published. Source: '{SOURCE_LINE}'."
    )
    measure = {
        "measure_id": points.measure_id,
        "label": label,
        "ordinal": ordinal,
        "column": column,
        "source_column_id": points.measure_id,
        "expected_column_header_row": table.header_row,
        "expected_column_header": header,
        "concept": family.share_concept,
        "source_concept": family.share_concept,
        "concept_relation": "source_label",
        "concept_authority": "dwp",
        "concept_evidence_url": PAGE,
        "concept_evidence_notes": notes,
        "unit": "percent",
        "aggregation": "share",
        "expected_cell_type": "number",
        "filters": Flow({family.dimension: points.value}),
        "constraints": [
            constraint(
                family.dimension, points.value, DIMENSION_LABELS[family.dimension]
            ),
            *bounds,
        ],
    }
    return measure


def claimants_measure(table: Table, ordinal: int) -> dict:
    family = FAMILIES[table.family]
    assert table.volume_column and family.claimants_concept
    column = table.volume_column
    heading = table.volume_heading[2]
    notes = (
        f"DWP Pathways to Work evidence pack, chapter 2, Table {table.key} (sheet "
        f"'{table.sheet}'), column {column}, headed '{heading}': the {family.base}, "
        "printed in whole thousands. Source: "
        f"'{SOURCE_LINE}'."
    )
    measure = {
        "measure_id": "claimants",
        "label": heading,
        "ordinal": ordinal,
        "column": column,
        "source_column_id": "claimants",
    }
    if table.volume_heading[0] == column:
        measure["expected_column_header_row"] = table.volume_heading[1]
        measure["expected_column_header"] = heading
    measure.update(
        {
            "concept": family.claimants_concept,
            "source_concept": family.claimants_concept,
            "concept_relation": "source_label",
            "concept_authority": "dwp",
            "concept_evidence_url": PAGE,
            "concept_evidence_notes": notes,
            "unit": "count",
            "aggregation": "sum",
            "expected_cell_type": "number",
        }
    )
    return measure


# ---------------------------------------------------------------- rows


@dataclass
class Row:
    number: int
    text: str
    value_id: str
    label: str
    kind: str
    filters: dict
    constraints: list
    extra_guards: list
    record_filters: (
        dict  # filters shared by the row's record set (Table 2.28's condition)
    )
    record_constraints: list
    record_slug: str


def awarded_constraint() -> Flow:
    """Claimants in receipt of the daily living component, at either rate."""
    return constraint(
        "pip_daily_living_award_rate",
        DAILY_LIVING_AWARDED,
        DIMENSION_LABELS["pip_daily_living_award_rate"],
    )


def age_semantics(text: str) -> tuple[str, str, Flow, list]:
    for printed, value_id, label, low, high in AGE_GROUPS:
        if printed == text:
            constraints = [
                constraint("age_band", value_id, DIMENSION_LABELS["age_band"]),
                constraint("age", low, "Age lower bound", ">="),
            ]
            if high is not None:
                constraints.append(constraint("age", high, "Age upper bound", "<"))
            return value_id, label, Flow(age_band=value_id), constraints
    raise AssertionError(text)


def condition_semantics(text: str, groups=CONDITIONS) -> tuple[str, str, Flow, list]:
    for printed, value_id in groups:
        if printed == text:
            label = VALUE_LABELS["pip_primary_health_condition_group"][value_id]
            return (
                value_id,
                label,
                Flow(pip_primary_health_condition_group=value_id),
                [
                    constraint(
                        "pip_primary_health_condition_group",
                        value_id,
                        DIMENSION_LABELS["pip_primary_health_condition_group"],
                    )
                ],
            )
    raise AssertionError(text)


def table_rows(grid: dict, table: Table) -> list[Row]:
    rows: list[Row] = []
    if table.breakdown in ("age", "condition"):
        expected = [TOTAL_ROW_TEXT[table.breakdown]]
        if table.daily_living_only:
            expected = [DAILY_LIVING_TOTAL]
        expected += (
            [printed for printed, *_ in AGE_GROUPS]
            if table.breakdown == "age"
            else [printed for printed, _ in CONDITIONS]
        )
        numbers = list(range(table.first_row, table.last_row + 1))
        assert [grid[(table.sheet, n, "A")] for n in numbers] == expected, table.key
        for number, text in zip(numbers, expected):
            if number == table.first_row:
                if table.daily_living_only:
                    continue  # Table 2.19's row, printed again; asserted below
                dimension = (
                    "age_band"
                    if table.breakdown == "age"
                    else ("pip_primary_health_condition_group")
                )
                rows.append(
                    Row(
                        number,
                        text,
                        "all",
                        VALUE_LABELS[dimension]["all"],
                        "total",
                        Flow({dimension: "all"}),
                        [],
                        [],
                        {},
                        [],
                        "",
                    )
                )
                continue
            value_id, label, filters, constraints = (
                age_semantics(text)
                if table.breakdown == "age"
                else condition_semantics(text)
            )
            rows.append(
                Row(
                    number,
                    text,
                    value_id,
                    label,
                    "detail",
                    filters,
                    constraints,
                    [],
                    {},
                    [],
                    "",
                )
            )
    elif table.breakdown == "overall":
        assert grid[(table.sheet, 13, "A")] == (
            "Percentage of working age PIP claimants out of all claimants in receipt of "
            "Daily Living component"
        )
        rows.append(
            Row(
                13,
                grid[(table.sheet, 13, "A")],
                DAILY_LIVING_AWARDED,
                VALUE_LABELS["pip_daily_living_award_rate"][DAILY_LIVING_AWARDED],
                "total",
                Flow(pip_daily_living_award_rate=DAILY_LIVING_AWARDED),
                [awarded_constraint()],
                [],
                {},
                [],
                "",
            )
        )
    elif table.breakdown == "award":
        assert grid[(table.sheet, 13, "A")] == DAILY_LIVING_TOTAL
        for number, (text, value_id) in zip((14, 15), AWARD_ROWS):
            assert grid[(table.sheet, number, "A")] == text, (table.key, number)
            rows.append(
                Row(
                    number,
                    text,
                    value_id,
                    VALUE_LABELS["pip_daily_living_award_rate"][value_id],
                    "detail",
                    Flow(pip_daily_living_award_rate=value_id),
                    [
                        constraint(
                            "pip_daily_living_award_rate",
                            value_id,
                            DIMENSION_LABELS["pip_daily_living_award_rate"],
                        )
                    ],
                    [],
                    {},
                    [],
                    "",
                )
            )
    elif table.breakdown == "activity":
        for offset, name in enumerate(ACTIVITIES):
            number = table.first_row + offset
            rows.append(activity_row(grid, table, number, offset, name, {}, [], ""))
    else:
        number = table.first_row
        for printed, value_id in CONDITIONS_2_28:
            assert grid[(table.sheet, number, "A")] == printed, (table.key, number)
            assert not any(
                (table.sheet, number, column) in grid for column in ("B", "C", "D")
            )
            _, _, filters, constraints = condition_semantics(printed, CONDITIONS_2_28)
            block_guard = guard("A", number, printed, "condition group")
            for offset, name in enumerate(ACTIVITIES):
                row = activity_row(
                    grid,
                    table,
                    number + 1 + offset,
                    offset,
                    name,
                    filters,
                    constraints,
                    value_id,
                )
                row.extra_guards.append(block_guard)
                rows.append(row)
            number += 12
        assert number - 2 == table.last_row, number
    return rows


def activity_row(
    grid, table, number, offset, name, record_filters, record_constraints, slug
):
    text = f"Activity {offset + 1} - {name}"
    assert grid[(table.sheet, number, table.label_column)] == text, (table.key, number)
    value_id = f"activity_{offset + 1}"
    return Row(
        number,
        text,
        value_id,
        text,
        "detail",
        Flow(pip_daily_living_activity=value_id),
        [
            constraint(
                "pip_daily_living_activity",
                value_id,
                DIMENSION_LABELS["pip_daily_living_activity"],
            )
        ],
        [],
        dict(record_filters),
        list(record_constraints),
        slug,
    )


VALUE_LABELS["pip_daily_living_activity"] = {
    f"activity_{index + 1}": f"Activity {index + 1} - {name}"
    for index, name in enumerate(ACTIVITIES)
}


# ---------------------------------------------------------------- checks


def row_values(grid: dict, table: Table, number: int) -> list[object]:
    return [grid.get((table.sheet, number, column)) for column in table.columns]


def check_headers(grid: dict, table: Table) -> None:
    title = grid[(table.sheet, table.title_row, "A")]
    assert title == table.title, (table.key, title)
    for points, column in zip(table.points, table.columns):
        assert grid[(table.sheet, table.header_row, column)] == points.header, (
            table.key,
            column,
        )
    if table.volume_heading:
        column, row, text = table.volume_heading
        assert grid[(table.sheet, row, column)] == text, (table.key, column, row)


def check_reprints(grid: dict) -> None:
    """Tables 2.20 to 2.22 open with Table 2.19's row: the same cells and volume."""
    overall = TABLES_BY_KEY["2.19"]
    expected = row_values(grid, overall, 13) + [grid[(overall.sheet, 13, "I")]]
    for key in ("2.20", "2.21", "2.22"):
        table = TABLES_BY_KEY[key]
        assert grid[(table.sheet, 13, "A")] == DAILY_LIVING_TOTAL, key
        printed = row_values(grid, table, 13) + [grid[(table.sheet, 13, "I")]]
        assert printed == expected, (key, printed, expected)


def weighted(parts: list[tuple[list, int]], width: int) -> list[float]:
    total = sum(volume for _, volume in parts)
    return [
        sum(
            (values[i] if is_number(values[i]) else 0) * volume
            for values, volume in parts
        )
        / total
        for i in range(width)
    ]


def check_text_order_row(grid: dict) -> dict[str, str]:
    """Assert Table 2.11's 'All health conditions' row prints its bands in text order.

    Returns, for each misplaced cell, the band whose share it holds.
    """
    table = TABLES_BY_KEY[TEXT_ORDER_EXCLUSION[0]]
    number = TEXT_ORDER_EXCLUSION[1]
    assert grid[(table.sheet, number, "A")] == "All health conditions"
    parts = [
        (row_values(grid, table, row), grid[(table.sheet, row, table.volume_column)])
        for row in range(number + 1, table.last_row + 1)
    ]
    average = dict(zip((band.header for band in table.points), weighted(parts, 12)))
    printed = row_values(grid, table, number)
    text_order = sorted((band.header for band in table.points), key=str)
    placed = {}
    for column, value, band in zip(table.columns, printed, text_order):
        assert abs(value - average[band]) <= TEXT_ORDER_TOLERANCE, (column, value, band)
        placed[column] = band
    # The in-place reading is wrong from '4-7' on: '4-7' prints 16.80, the average 5.52.
    in_place = [
        abs(value - average[band.header]) for value, band in zip(printed, table.points)
    ]
    assert in_place[0] <= TEXT_ORDER_TOLERANCE and min(in_place[1:]) > 1, in_place
    return {column: band for column, band in placed.items() if column != "B"}


def check_copied_cell(grid: dict) -> dict:
    """Assert the Arthritis Activity 1 2-point cell of Table 2.28 repeats another block's.

    Returns the evidence the header quotes.
    """
    t22, t27, t28 = (TABLES_BY_KEY[key] for key in ("2.22", "2.27", "2.28"))
    key, number, column = COPIED_CELL
    assert key == "2.28"
    assert grid[(t28.sheet, 21, "A")] == "Arthritis"
    assert grid[(t28.sheet, number, "C")] == "Activity 1 - Preparing food"
    assert grid[(t28.sheet, COPIED_FROM_ROW, "C")] == "Activity 1 - Preparing food"
    value = grid[(t28.sheet, number, column)]
    assert value == grid[(t28.sheet, COPIED_FROM_ROW, column)], value
    row_sum = sum(v for v in row_values(grid, t28, number) if is_number(v))
    shortfall = 100 - row_sum
    volumes = {
        grid[(t22.sheet, row, "A")]: grid[(t22.sheet, row, "I")]
        for row in range(14, 34)
    }
    total = grid[(t22.sheet, 13, "I")]
    blocks = [
        (printed, t28.first_row + 12 * index)
        for index, (printed, _) in enumerate(CONDITIONS_2_28)
    ]
    weights = {printed: volumes[printed] for printed, _ in blocks[:5]}
    weights[blocks[5][0]] = total - sum(weights.values())
    gaps = {}
    for offset in range(len(ACTIVITIES)):
        for col in t27.columns:
            published = grid.get((t27.sheet, t27.first_row + offset, col))
            if not is_number(published):
                continue
            average = (
                sum(
                    (
                        v
                        if is_number(
                            v := grid.get((t28.sheet, start + 1 + offset, col))
                        )
                        else 0
                    )
                    * weights[printed]
                    for printed, start in blocks
                )
                / total
            )
            gaps[(offset + 1, col)] = published - average
    copied = gaps.pop((1, column))
    weight = weights["Arthritis"] / total
    assert abs(copied - weight * shortfall) <= COPIED_TOLERANCE, (
        copied,
        weight,
        shortfall,
    )
    worst = max(abs(gap) for gap in gaps.values())
    assert worst <= REPRODUCTION_TOLERANCE, worst
    return {
        "value": value,
        "row_sum": row_sum,
        "shortfall": shortfall,
        "gap": copied,
        "weight": weights["Arthritis"],
        "total": total,
        "worst_other_gap": worst,
        "published_2_27": grid[(t27.sheet, t27.first_row, column)],
    }


@dataclass
class Parity:
    sums: dict  # (table, row text) -> sum of the row's numeric cells
    weighted_gaps: dict  # table -> (largest gap, what was compared)


def parity(grid: dict) -> Parity:
    sums = {}
    for table in TABLES:
        for number in range(table.first_row, table.last_row + 1):
            values = row_values(grid, table, number)
            numbers = [value for value in values if is_number(value)]
            if not numbers:
                continue
            label = grid[(table.sheet, number, table.label_column)]
            if table.breakdown == "activity_condition":
                block = max(
                    (
                        row
                        for row in range(table.first_row, number)
                        if (table.sheet, row, "A") in grid
                    ),
                )
                label = f"{grid[(table.sheet, block, 'A')]}: {label}"
            sums[(table.key, label)] = sum(numbers)
    gaps = {}

    def gap(key: str, total_row: int, part_rows: range) -> float:
        table = TABLES_BY_KEY[key]
        parts = [
            (
                row_values(grid, table, row),
                grid[(table.sheet, row, table.volume_column)],
            )
            for row in part_rows
        ]
        average = weighted(parts, len(table.points))
        printed = row_values(grid, table, total_row)
        return max(abs(a - p) for a, p in zip(average, printed) if is_number(p))

    gaps["2.9"] = gap("2.9", 13, range(14, 20))
    gaps["2.10"] = gap("2.10", 14, range(15, 21))
    gaps["2.12"] = gap("2.12", 13, range(14, 34))
    overall = TABLES_BY_KEY["2.19"]
    for key, rows in (
        ("2.20", range(14, 16)),
        ("2.21", range(14, 20)),
        ("2.22", range(14, 34)),
    ):
        table = TABLES_BY_KEY[key]
        parts = [
            (row_values(grid, table, row), grid[(table.sheet, row, "I")])
            for row in rows
        ]
        average = weighted(parts, 7)
        printed = row_values(grid, overall, 13)
        gaps[key] = max(abs(a - p) for a, p in zip(average, printed))
    return Parity(sums=sums, weighted_gaps=gaps)


# Row sums (the published cells of each distribution) outside 100 +/- this are listed
# in the header; Table 2.9 prints whole percentages and its rows reach 92 to 102.
SUM_TOLERANCE = 0.2
TABLE_2_9_SUMS = {
    "All ages": 98,
    "16 - 19": 92,
    "20 - 29": 100,
    "30 - 39": 99,
    "40 - 49": 100,
    "50 - 59": 100,
    "60+": 102,
}


# ---------------------------------------------------------------- the package


def record_set_for(
    grid: dict,
    table: Table,
    rows: list[Row],
    measures: list[dict],
    suffix: str,
    record_filters: dict,
    record_constraints: list,
) -> dict:
    family = FAMILIES[table.family]
    filters = {variable: value for variable, value, _ in SCOPE}
    constraints = [
        constraint(variable, value, label) for variable, value, label in SCOPE
    ]
    if table.daily_living_only and table.breakdown not in ("overall", "award"):
        filters["pip_daily_living_award_rate"] = DAILY_LIVING_AWARDED
        constraints.append(awarded_constraint())
    filters.update(record_filters)
    constraints += record_constraints
    groupby = {
        "age": "age_band",
        "condition": "pip_primary_health_condition_group",
        "overall": "pip_daily_living_award_rate",
        "award": "pip_daily_living_award_rate",
        "activity": "pip_daily_living_activity",
        "activity_condition": "pip_daily_living_activity",
    }[table.breakdown]
    record_set_id = f"dwp.pathways_pip_points.jan2025.{table.slug}.{family.key}{suffix}"
    first = True
    yaml_rows = []
    for ordinal, row in enumerate(rows):
        spec = {
            "value_id": row.value_id,
            "label": row.label,
            "ordinal": ordinal,
            "row_number": row.number,
            "expected_row_header_column": table.label_column,
            "expected_row_header": row.text,
            "table_record_kind": row.kind,
        }
        if row.filters:
            spec["filters"] = row.filters
        if row.constraints:
            spec["constraints"] = row.constraints
        guards = list(row.extra_guards)
        if first:
            guards = scope_guards(grid, table) + guards
            if table.volume_heading and table.volume_heading[0] != table.volume_column:
                column, number, text = table.volume_heading
                guards.append(
                    guard(
                        column,
                        number,
                        text,
                        f"heading of column {table.volume_column}, read at {column}{number}: "
                        "the parser keeps no covered cells of the merged points heading",
                    )
                )
            first = False
        if guards:
            spec["guard_cells"] = guards
        yaml_rows.append(spec)
    return {
        "record_set_id": record_set_id,
        "provenance_class": "administrative",
        "assertion": "observation",
        "record_set_spec_id": f"{record_set_id}.v1",
        "source_record_id_prefix": record_set_id,
        "sheet_name": table.sheet,
        "period_type": "month",
        "period": "2025-01",
        "period_coverage": {
            "source_period_label": "PIP caseload at end January 2025",
            "notes": (
                "'Figures are based on the PIP caseload at end January 2025' (Table "
                f"{table.key}, note 1); the ODS states no day."
            ),
        },
        "geography_id": "K04000001",
        "geography_level": "country",
        "geography_name": "England and Wales",
        "geography_vintage": "current",
        "entity": "person",
        "entity_role": "pip_claimant",
        "domain": "personal_independence_payment",
        "groupby_dimension": groupby,
        "shared_filters": filters,
        "shared_constraints": constraints,
        "rows": yaml_rows,
        "measures": measures,
    }


def build_table(
    grid: dict, table: Table, excluded: dict[tuple[str, int], set[str]]
) -> tuple[list[dict], int]:
    check_headers(grid, table)
    rows = table_rows(grid, table)
    by_signature: dict[tuple, list[Row]] = {}
    marked = 0
    for row in rows:
        values = row_values(grid, table, row.number)
        signature = []
        for points, column, value in zip(table.points, table.columns, values):
            if column in excluded.get((table.key, row.number), ()):
                assert is_number(value), (table.key, row.number, column)
                continue
            if is_number(value):
                signature.append(points.measure_id)
                continue
            assert value == MARKER, (table.key, row.number, column, value)
            marked += 1
        if table.volume_column:
            volume = grid[(table.sheet, row.number, table.volume_column)]
            assert is_number(volume) and volume % 1000 == 0, (
                table.key,
                row.number,
                volume,
            )
            signature.append("claimants")
        key = (row.record_slug, tuple(signature))
        by_signature.setdefault(key, []).append(row)
    record_sets = []
    for (slug, signature), group in by_signature.items():
        measures = []
        for points, column in zip(table.points, table.columns):
            if points.measure_id in signature:
                measures.append(share_measure(table, points, column, len(measures)))
        if "claimants" in signature:
            measures.append(claimants_measure(table, len(measures)))
        excluded_here = {
            points.measure_id
            for row in group
            for points, column in zip(table.points, table.columns)
            if column in excluded.get((table.key, row.number), ())
        }
        missing = [
            p.measure_id
            for p in table.points
            if p.measure_id not in signature and p.measure_id not in excluded_here
        ]
        suffix = f".{slug}" if slug else ""
        if group[0].kind == "total" and len(by_signature) > 1:
            suffix += ".total"
        if (table.key, group[0].number) == TEXT_ORDER_EXCLUSION:
            suffix += ".text_ordered_bands_not_ported"
        elif missing:
            suffix += ".without_" + "_".join(
                m.replace("max_points_", "").replace("points_", "") for m in missing
            )
        if excluded_here and (table.key, group[0].number) != TEXT_ORDER_EXCLUSION:
            suffix += (
                ".copied_"
                + "_".join(m.replace("points_", "") for m in sorted(excluded_here))
                + "_not_ported"
            )
        record_sets.append(
            record_set_for(
                grid,
                table,
                group,
                measures,
                suffix,
                group[0].record_filters,
                group[0].record_constraints,
            )
        )
    ids = [record_set["record_set_id"] for record_set in record_sets]
    assert len(ids) == len(set(ids)), ids
    return record_sets, marked


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
    assert set(used) <= set(DIMENSION_LABELS), set(used) - set(DIMENSION_LABELS)
    value_labels = {
        key: {
            value: label
            for value, label in VALUE_LABELS[key].items()
            if value in used[key]
        }
        for key in VALUE_LABELS
        if used.get(key)
    }
    for key, values in used.items():
        if key in VALUE_LABELS:
            assert values <= set(VALUE_LABELS[key]), (
                key,
                values - set(VALUE_LABELS[key]),
            )
    return dimension_labels, value_labels


COPIED_ROW_LABEL = "Arthritis: Activity 1 - Preparing food"


def build() -> str:
    grid, filename, entry = workbook()
    check_reprints(grid)
    misplaced_cells = check_text_order_row(grid)
    copied = check_copied_cell(grid)
    excluded = {
        TEXT_ORDER_EXCLUSION: set(misplaced_cells),
        COPIED_CELL[:2]: {COPIED_CELL[2]},
    }
    checks = parity(grid)
    for (key, label), total in checks.sums.items():
        if key == "2.9":
            assert total == TABLE_2_9_SUMS[label], (label, total)
        elif (key, label) == ("2.28", COPIED_ROW_LABEL):
            assert abs(total - copied["row_sum"]) < 1e-9, total
        elif not (key == TEXT_ORDER_EXCLUSION[0] and label == "All health conditions"):
            assert abs(total - 100) <= SUM_TOLERANCE, (key, label, total)
    for key, value in checks.weighted_gaps.items():
        assert value <= (0.6 if key == "2.9" else 0.02), (key, value)
    record_sets = []
    marked = {}
    for table in TABLES:
        sets, count = build_table(grid, table, excluded)
        record_sets += sets
        marked[table.key] = count
    dimension_labels, value_labels = declarations(record_sets)
    facts = sum(len(rs["rows"]) * len(rs["measures"]) for rs in record_sets)

    def total_measures(key: str) -> set[str]:
        sheet = TABLES_BY_KEY[key].sheet
        return {
            measure["measure_id"]
            for rs in record_sets
            if rs["sheet_name"] == sheet
            and any(row["value_id"] == "all" for row in rs["rows"])
            for measure in rs["measures"]
        }

    pairs = sum(
        len(total_measures(age) & total_measures(condition))
        for age, condition in (("2.9", "2.11"), ("2.10", "2.12"))
    )
    shared_semantic_keys = f"{2 * pairs} facts in {pairs} pairs"
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": (
            "DWP Pathways to Work evidence pack, chapter 2: PIP daily living and mobility "
            "point scores, January 2025 normal rules caseload (Tables 2.9 to 2.12, 2.19 to "
            "2.22, 2.27 and 2.28)"
        ),
        "dimension_labels": dimension_labels,
        "dimension_value_labels": value_labels,
        "artifact": {
            "source_name": "dwp",
            "source_table": (
                "Pathways to Work: Evidence pack: Chapter 2 reforming the structure, data "
                "tables 2.9 to 2.12, 2.19 to 2.22, 2.27 and 2.28 (ODS revised 23 July 2025)"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{RAW_DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "pathways_to_work_evidence_pack_chapter_2_2025_07_23",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": f"ODS used-range cell parse ({filename})",
            "parser": "ods_used_range",
            "artifact_year": 2025,
        },
        "record_sets": record_sets,
    }
    sums_2_9 = ", ".join(f"{label} {total}" for label, total in TABLE_2_9_SUMS.items())
    off_100 = sorted(
        (abs(total - 100), key, label, total)
        for (key, label), total in checks.sums.items()
        if key != "2.9"
        and (key, label) != ("2.28", COPIED_ROW_LABEL)
        and not (key == TEXT_ORDER_EXCLUSION[0] and label == "All health conditions")
    )
    largest = off_100[-1]
    bands_2_11 = TABLES_BY_KEY["2.11"].points
    misplaced = ", ".join(
        f"under {bands_2_11[column_index_from_string(column) - 2].header!r} the share "
        f"at {band}"
        for column, band in misplaced_cells.items()
    )
    header = f"""
    DWP, 'Pathways to Work: Evidence pack: Chapter 2 reforming the structure' ({PAGE}),
    the chapter's data tables (ODS; published 2 May 2025 with the full evidence pack;
    the consultation page records updates to this file on 17 and 23 July 2025, and the
    pinned file is the 23 July one), for {ISSUE} item 5 ({CONSUMER}). Written by
    {SCRIPT} from the pinned workbook; edit that, not this.

    Ported, with the chapter's chart of the same number: Tables 2.9 and 2.10 (daily
    living and mobility points scored by age group), 2.11 and 2.12 (the same by
    primary health condition), 2.19 (the most points scored on any one daily living
    activity), 2.20 (2.19 by daily living award), 2.21 (by age group), 2.22 (by
    condition), 2.27 (the points scored on each daily living activity) and 2.28 (2.27
    by condition, five condition groups and the rest). Not ported: Tables 2.25 and 2.26
    (by local authority and constituency; not requested), and the workbook's other
    tables (awards, prevalence, employment, reassessments, assessment channels, and 2.18,
    2.23 and 2.24: the most points on an activity at clearance, by gender and by
    region).

    Population, in DWP's notes to every table: 'Figures are based on the PIP caseload at
    end January 2025'; 'Data includes working age claimants only'; 'Data only includes
    claimants living in regions under DWP policy ownership (England, Wales and Abroad)';
    'Data includes normal rules claimants only, and excludes special rules for end of
    life (SREL) claimants as they typically receive maximum or very high scores'.
    Tables 2.9 to 2.12 cover the caseload (some claimants 'receive only one award
    element from Daily Living or Mobility', and the caseload 'does not include those
    claimants who were not awarded either component'); Tables 2.19 to 2.22, 2.27 and 2.28
    'only include claimants awarded Daily Living component'. The facts carry these as
    filters and constraints worded as dwp-pip-daily-living-foi-2025 words them for the
    same caseload, and geography K04000001 (England and Wales), the nearest GSS
    footprint; the claimants living abroad are in every figure and have no code. DWP's
    description of the source, on every table: '{SOURCE_LINE}'. Period: month 2025-01.

    Shares are percentages as published, unit percent, aggregation share: of the
    group's claimants in each points band (daily living, 2.9 and 2.11), at each mobility
    total (2.10 and 2.12), at each highest score on any one daily living activity (2.19 to
    2.22), or scoring each value on an activity (2.27 and 2.28). Precision is the
    workbook's: Table 2.9 prints whole percentages, 2.10 to 2.12 full precision, the
    others mostly two decimals. The 'Volume' columns (claimants in the group, the shares'
    base, printed in whole thousands) are ported as counts. Each points column carries
    its value as a filter with a constraint, and the daily living bands their bounds;
    a share of claimants scoring 4 or more on one activity is the sum of Table 2.19's
    shares from 4 up, which Chronicle does not compute. Value ids for age groups, award
    rates, conditions and activities are Chronicle's; each row guards the printed text.

    Each of Tables 2.20 to 2.22 opens with Table 2.19's row ('{DAILY_LIVING_TOTAL}'),
    printed again with the same cells and volume, which the generator asserts and does
    not port again: Table 2.19 carries it, with daily living award rate
    standard_or_enhanced. The 'All ages' and 'All health conditions' rows of Tables 2.9
    to 2.12 carry age_band or condition group 'all'. Both describe the whole caseload,
    on bases DWP prints differently (daily living 3,627,000 by age and 3,701,000 by
    condition; mobility 3,620,000 and 3,691,000), so a total row of the age table and of
    the condition table carry the same constraints and share semantic keys:
    {shared_semantic_keys}, which the bundle reports as semantic duplicates, and a
    consumer chooses the table. Table 2.28's 'All other conditions'
    takes in every group but its five (Unknown or Missing included, note 9), so it is a
    value of its own, not Table 2.11's 'All Other Conditions'. A cell marked '-' emits no
    fact: in Tables 2.27 and 2.28 it is a score the activity's descriptors do not give
    (Activity 1 scores 0, 2, 4 or 8), and in Table 2.20 the standard award's 10 and 12;
    the notes do not define it. {sum(marked.values())} marked cells are not ported.

    Not ported, as publisher errors, 12 cells. First, Table 2.11's 'All health
    conditions' row (row 13) prints its bands in text order ('0-3', '10-11', '12-13',
    ..., '36-40', '4-7', '41+', '8-9'), not in the order of the headings above it: {misplaced}.
    Each of these 11 cells is, within {TEXT_ORDER_TOLERANCE} points, the volume-weighted
    average of the table's 20 condition rows for the band text order gives it; read in
    place, the '4-7' cell would be 16.80 against an average of 5.52. The row's '0-3'
    cell, which is in place, and its volume are ported, and Table 2.9's 'All ages' row
    gives the same distribution in whole percentages. Second, Table 2.28's Arthritis
    'Activity 1 - Preparing food' row (row 22) prints {copied["value"]} at 2 points, the
    cell of the Anxiety and Depression block's row 10, and adds to
    {copied["row_sum"]:.2f}. Weighted by Table 2.22's volumes (the 'All other
    conditions' weight being {copied["total"]:,} less the five groups' volumes), Table
    2.28's blocks reproduce Table 2.27 within {copied["worst_other_gap"]:.3f} points in
    every cell but that one, where the gap, {copied["gap"]:.3f}, is Arthritis's weight
    ({copied["weight"]:,} of {copied["total"]:,}) times the row's
    {copied["shortfall"]:.2f}-point shortfall; the row's other cells are ported.

    Parity, asserted by the generator on the published cells: every distribution adds to
    100 within {SUM_TOLERANCE} points (the largest gap, {largest[0]:.3f}, is Table
    {largest[1]}'s '{largest[2]}'), except the two rows above and Table 2.9's whole
    percentages, whose rows add to: {sums_2_9}. Weighted by the published volumes, the
    parts reproduce the total row within: Table 2.9 {checks.weighted_gaps["2.9"]:.2f}
    points (whole percentages), 2.10 {checks.weighted_gaps["2.10"]:.3f}, 2.12
    {checks.weighted_gaps["2.12"]:.3f}; and Table 2.19's overall shares within
    {checks.weighted_gaps["2.20"]:.3f} (2.20, by award), {checks.weighted_gaps["2.21"]:.3f}
    (2.21, by age) and {checks.weighted_gaps["2.22"]:.3f} (2.22, by condition). Table
    2.20's award volumes, 1,608,000 enhanced and 1,283,000 standard, are the counts
    FOI2025/24990 ({FOI_PACKAGE_ID}) gives for the same caseload. {facts} facts.
    """
    return render(header, payload)


BUILDERS = {PACKAGE_DIRECTORY: build}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the generated YAML with the committed file instead of writing.",
    )
    args = parser.parse_args()
    stale = []
    for directory, builder in BUILDERS.items():
        text = builder()
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
