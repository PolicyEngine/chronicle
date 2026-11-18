"""Generate the young people and work review packages for PolicyEngine/chronicle#442.

Run from the repository root:

    uv run python scripts/build_uk_young_people_work_review_packages.py

``--check`` compares the generated YAML with the committed files instead of writing.
Each package is written from its pinned workbook, read with Chronicle's own ODS parser,
so every row number, column and guard cell below is one the package parser sees. The
publisher's text is asserted cell by cell, so a run against different bytes fails
rather than drifting. Nothing is downloaded and no value is computed.

- ``dwp-young-people-pip-lcwra-projections-2026``: 'Young people and work: interim
  report', analytical annex data tables (DWP, published 28 May 2026, updated 10 August
  2026), Table 28: the PIP and Universal Credit health element (LCWRA) caseloads and
  expenditure of 16 to 24 year olds in England and Wales, 2019-20 to 2040-41.
- ``dwp-welfare-state-to-working-state-tables-2026``: 'From a Welfare State to a
  Working State: a new settlement for the next generation' (DWP, 17 November 2026),
  data tables 2 (the recommended policies' annual cost and saving by policy area in
  2036-37) and 3 (the NEET rate projected with and without the recommendations,
  2026-27 to 2036-37).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import textwrap
from pathlib import Path

import yaml
from openpyxl.utils import get_column_letter

from chronicle.sources.cells import SourceArtifactMetadata, source_cells_from_ods

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-11-18"
ISSUE = "PolicyEngine/chronicle#442"
DASHBOARD = "PolicyEngine/uk-milburn-review-dashboard"
SCRIPT = "scripts/build_uk_young_people_work_review_packages.py"


class Flow(dict):
    """A small mapping written on one line, as the other packages write guards."""


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


def grid_of(content: bytes, filename: str) -> dict[tuple[str, int, str], object]:
    """{(sheet, row, column letter): value} of the parser's non-empty cells."""
    grid: dict[tuple[str, int, str], object] = {}
    for cell in source_cells_from_ods(content, metadata(filename)):
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


def constraint(variable: str, value: object, label: str) -> Flow:
    return Flow(variable=variable, operator="==", value=value, label=label)


def bound(operator: str, value: int, label: str) -> Flow:
    return Flow(
        variable="age", operator=operator, value=value, unit="years", label=label
    )


def guard(column: str, row: int, value: object, label: str) -> Flow:
    return Flow(column=column, row=row, expected_value=value, label=label)


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def dash_year(opening: int) -> str:
    """2019-20, as Table 28 heads its columns."""
    return f"{opening}-{str(opening + 1)[2:]}"


def slash_year(opening: int) -> str:
    """2026/27, as the final report's tables print years."""
    return f"{opening}/{str(opening + 1)[2:]}"


def fiscal_coverage(opening: int, label: str, notes: str) -> dict:
    return {
        "start_date": f"{opening}-04-01",
        "end_date": f"{opening + 1}-03-31",
        "basis": "fiscal",
        "source_period_label": label,
        "notes": notes,
    }


def geography(code: str, name: str) -> dict:
    return {
        "geography_id": code,
        "geography_level": "country",
        "geography_name": name,
        "geography_vintage": "current",
    }


ENGLAND_AND_WALES = geography("K04000001", "England and Wales")
UNITED_KINGDOM = geography("K02000001", "United Kingdom")
GREAT_BRITAIN = geography("K03000001", "Great Britain")
ENGLAND = geography("E92000001", "England")

# Labels for every dimension and value the packages use. A package declares the ones
# its facts use; the register (chronicle/dimension_values/canonical_labels.json) holds
# age_band 16_to_24 as 'Age 16 to 24' for the other packages that emit it.
DIMENSION_LABELS = {
    "health_and_disability_benefit": "Health and Disability benefit",
    "age_band": "Age band",
    "policy_area": "Policy area",
    "price_basis": "Price basis",
    "neet_rate_projection": "NEET rate projections",
}
VALUE_LABELS = {
    "health_and_disability_benefit": {
        "uc_health_lcwra": "UCH - LCWRA",
        "personal_independence_payment": "PIP",
    },
    "age_band": {"16_to_24": "Age 16 to 24"},
    "policy_area": {
        "opportunity_and_support_guarantees": "Opportunity and Support Guarantees",
        "health": "Health",
        "education": "Education",
        "youth_hiring_incentives": "Youth hiring incentives",
        "welfare_savings": "Welfare savings",
        "fiscal_offsets": "Fiscal offsets",
        "total_net_cost": "Total NET Cost",
    },
    "price_basis": {"2026_27_prices": "2026/27 prices"},
    "neet_rate_projection": {
        "baseline": "Projected baseline NEET rate",
        "with_report_recommendations": "Projected NEET rate with report recommendations",
    },
}
AGE_16_TO_24 = {"age_band": "16_to_24"}
AGE_16_TO_24_CONSTRAINTS = [
    constraint("age_band", "16_to_24", DIMENSION_LABELS["age_band"]),
    bound(">=", 16, "Age lower bound"),
    bound("<", 25, "Age upper bound"),
]


def declarations(record_sets: list[dict]) -> tuple[dict, dict]:
    """The dimension and value labels the record sets' facts use."""
    used: dict[str, set[str]] = {}
    for record_set in record_sets:
        used.setdefault(record_set["groupby_dimension"], set())
        filters = [record_set.get("shared_filters", {})]
        filters += [row.get("filters", {}) for row in record_set["rows"]]
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


def package_payload(
    *, package_id: str, label: str, record_sets: list[dict], artifact: dict
) -> dict:
    dimension_labels, value_labels = declarations(record_sets)
    return {
        "schema_version": "ledger.source_package.v1",
        "package_id": package_id,
        "label": label,
        "dimension_labels": dimension_labels,
        "dimension_value_labels": value_labels,
        "artifact": artifact,
        "record_sets": record_sets,
    }


def fact_count(payload: dict) -> int:
    return sum(len(rs["rows"]) * len(rs["measures"]) for rs in payload["record_sets"])


def measure_spec(
    measure_id: str,
    label: str,
    column: str,
    header_row: int,
    header: str,
    *,
    concept: str,
    unit: str,
    aggregation: str,
    evidence_url: str,
    notes: str,
    relation: str = "source_label",
    scale: int | None = None,
) -> dict:
    measure = {
        "measure_id": measure_id,
        "label": label,
        "ordinal": 0,
        "column": column,
        "source_column_id": measure_id,
        "expected_column_header_row": header_row,
        "expected_column_header": header,
        "concept": concept,
        "source_concept": concept,
        "concept_relation": relation,
        "concept_authority": "dwp",
        "concept_evidence_url": evidence_url,
        "concept_evidence_notes": notes,
        "unit": unit,
        "aggregation": aggregation,
    }
    if scale is not None:
        measure["value_scale"] = scale
    measure["expected_cell_type"] = "number"
    return measure


def category_row(
    dimension: str,
    value_id: str,
    ordinal: int,
    row: int,
    *,
    kind: str = "detail",
    guards: list[Flow] | None = None,
) -> dict:
    """A publisher row: its label as printed in column A, and its filter."""
    label = VALUE_LABELS[dimension][value_id]
    entry = {
        "value_id": value_id,
        "label": label,
        "ordinal": ordinal,
        "row_number": row,
        "expected_row_header_column": "A",
        "expected_row_header": label,
        "table_record_kind": kind,
        "filters": Flow({dimension: value_id}),
        "constraints": [constraint(dimension, value_id, DIMENSION_LABELS[dimension])],
    }
    if guards:
        entry["guard_cells"] = guards
    return entry


# ------------------------------------------------- 1. the interim report's Table 28

INTERIM_DIRECTORY = "dwp/young_people_pip_lcwra_projections_2026"
INTERIM_PACKAGE_ID = "dwp-young-people-pip-lcwra-projections-2026"
INTERIM_PAGE = (
    "https://www.gov.uk/government/publications/young-people-and-work-interim-report"
)
INTERIM_ANNEX = f"{INTERIM_PAGE}/young-people-and-work-interim-report-analytical-annex"
T28 = "Table_28"
T28_TITLE = (
    "Table 28: PIP and UCH-LCWRA caseload and expenditure projections, aged 16-24"
)
T28_POPULATION = "Population: England and Wales"
T28_NOTES = {
    11: "Note 1: Caseloads have been rounded to the nearest 1,000.",
    12: (
        "Note 2: Expenditure has been expressed in millions and has been rounded to the "
        "nearest 10 for UCH - LCWRA and nearest 100 for PIP"
    ),
}
# Benefit, its caseload and expenditure rows, and the expenditure's rounding (£ million).
T28_BENEFITS = (
    ("uc_health_lcwra", 7, 8, 10),
    ("personal_independence_payment", 9, 10, 100),
)
T28_KINDS = {"caseload": "Caseload", "expenditure": "Expenditure (£m)"}
T28_FIRST_YEAR, T28_LAST_YEAR = 2019, 2040  # columns C (2019-20) to X (2040-41)
# The annex's forecasts rest on the Autumn Budget 2025 benefit caseload and expenditure
# tables, which still forecast 2025-26 (dwp-benefit-expenditure-caseload-spring-2026
# types the year the same way), so DWP's projections start there: a year before the
# table's period line, which names 2026-27 to 2040-41.
T28_FIRST_FORECAST = 2025
# The annex's findings (section 18.5) quote these cells of the table; the generator
# asserts them, so the table cannot drift from the text DWP wrote about it.
T28_ANNEX_FINDINGS = {
    # 'Annual PIP expenditure for 16 to 24 year olds rose from approximately £1.3
    # billion in the financial year ending 2020 to around £3.3 billion in the
    # financial year ending 2025.'
    ("personal_independence_payment", "expenditure", 2019): 1_300,
    ("personal_independence_payment", "expenditure", 2024): 3_300,
    # 'The PIP caseload and expenditure are projected to increase by financial year
    # ending 2041, up to 877,000 and £9.2 billion respectively.'
    ("personal_independence_payment", "caseload", 2040): 877_000,
    ("personal_independence_payment", "expenditure", 2040): 9_200,
    # 'The LCWRA caseload is projected to rise to 229,000 in financial year ending
    # 2041. However, the LCWRA caseload is projected to fall to £750 million in
    # financial year ending 2041.' (the second 'caseload' is the expenditure)
    ("uc_health_lcwra", "caseload", 2040): 229_000,
    ("uc_health_lcwra", "expenditure", 2040): 750,
}
# The annex's section 18 (https://www.gov.uk/.../analytical-annex), quoted in the notes.
T28_DEFINITION = (
    "UC Health (UC-H) in this analysis refers to claimants in receipt of the 'limited "
    "capability to work' element, also known as the 'health element', which is offered "
    "to claimants receiving a LCWRA WCA outcome"
)
T28_DATA_SOURCE = (
    "PIP and UC-H / LCWRA caseload and expenditure forecasts for 16 to 24 year olds are "
    "based on data from Stat-Xplore and Autumn Budget 2025 benefit caseload and "
    "expenditure tables"
)
T28_METHOD = (
    "Prevalence projections are derived from caseload/populations using a weighted "
    "average and year on year change to project forward a rate, which is then applied to "
    "population projections to produce fifteen-year caseload projections by age"
)
T28_CAVEATS = (
    "The forecast outputs are compared to final Autumn Budget 2025 forecasts for PIP and "
    "DLA to 2031 and an average uplift is assumed for the years 2031 to 2042. Forecast "
    "outputs have used a simple methodology and should be treated as an indication only. "
    "Forecast estimates are based on the proportion of young people and therefore may not "
    "align with published benefit expenditure and caseload tables."
)
T28_AWARDS = (
    "Average awards are projected in a similar way to prevalence but capped so that "
    "weekly amounts cannot exceed maximum award levels"
)


def t28_notes(kind: str, column: str, year: int) -> str:
    source = (
        "Young people and work: interim report, analytical annex data tables (DWP, "
        "published 28 May 2026; the 10 August 2026 update changed Table 23 only), "
        f"Table 28 '{T28_TITLE.split(': ', 1)[1]}', '{T28_POPULATION}', 'Source: DWP "
        f"administrative data'; column {column} ('{dash_year(year)}'). "
    )
    if kind == "caseload":
        what = (
            "The caseload, 'rounded to the nearest 1,000' (Note 1). The analytical "
            f"annex (section 18) defines the UC health caseload: '{T28_DEFINITION}', so "
            "it counts claimants, not households or awards. "
        )
    else:
        what = (
            "Expenditure, £ million: 'rounded to the nearest 10 for UCH - LCWRA and "
            "nearest 100 for PIP' (Note 2), scaled to pounds. Neither the table nor the "
            f"annex names a price basis; the annex adds: '{T28_AWARDS}'. "
        )
    return (
        source
        + what
        + f"Data source: '{T28_DATA_SOURCE}'. Method: '{T28_METHOD}'. Caveats: "
        f"'{T28_CAVEATS}'"
    )


def build_interim() -> str:
    entry, content = pinned(INTERIM_DIRECTORY)
    grid = grid_of(content, entry["filename"])
    cover = {
        1: "Young People and Work Interim Report Analytical Annex",
        3: "Published:28 May 2025",  # sic: GOV.UK published the report on 28 May 2026
    }
    for row, text in cover.items():
        assert grid[("Cover", row, "A")] == text, row
    assert grid[("Cover", 46, "A")] == "Table 28"
    assert grid[("Cover", 46, "B")] == T28_TITLE.split(": ", 1)[1]
    assert grid[(T28, 1, "A")] == "This worksheet contains one table."
    assert grid[(T28, 2, "A")] == T28_TITLE
    assert grid[(T28, 3, "A")] == T28_POPULATION
    period_line = grid[(T28, 4, "A")]
    match = re.fullmatch(r"Period: (\d{4})-\d{2} to (\d{4})-\d{2}", period_line)
    assert match, period_line
    first_projection, last_projection = int(match[1]), int(match[2])
    assert (first_projection, last_projection) == (2026, T28_LAST_YEAR)
    assert T28_FIRST_FORECAST == first_projection - 1
    assert grid[(T28, 5, "A")] == "Source: DWP administrative data"
    assert grid[(T28, 6, "A")] == "Health and Disability benefit"
    assert grid[(T28, 6, "B")] == "Caseload or expenditure"
    columns: dict[int, str] = {}
    for offset, year in enumerate(range(T28_FIRST_YEAR, T28_LAST_YEAR + 1)):
        column = get_column_letter(3 + offset)
        assert grid[(T28, 6, column)] == dash_year(year), (column, year)
        columns[year] = column
    assert (T28, 6, get_column_letter(3 + len(columns))) not in grid
    for row, note in T28_NOTES.items():
        assert grid[(T28, row, "A")] == note, row
    assert max(row for sheet, row, _ in grid if sheet == T28) == 12
    values: dict[tuple[str, str, int], int] = {}
    for benefit, caseload_row, expenditure_row, rounding in T28_BENEFITS:
        label = VALUE_LABELS["health_and_disability_benefit"][benefit]
        for kind, row, step in (
            ("caseload", caseload_row, 1_000),
            ("expenditure", expenditure_row, rounding),
        ):
            assert grid[(T28, row, "A")] == label, row
            assert grid[(T28, row, "B")] == T28_KINDS[kind], row
            for year, column in columns.items():
                value = grid[(T28, row, column)]
                assert isinstance(value, int) and value > 0, (row, column, value)
                assert value % step == 0, (row, column, value)
                values[(benefit, kind, year)] = value
    for key, expected in T28_ANNEX_FINDINGS.items():
        assert values[key] == expected, key
    # 'In 5 years' time, we estimate that PIP, on the current trajectory, will have
    # further doubled in cost to £6.5 billion and cover 700,000 young people.'
    assert values[("personal_independence_payment", "expenditure", 2031)] == 6_500
    assert round(values[("personal_independence_payment", "caseload", 2031)], -5) == (
        700_000
    )
    record_sets = []
    for kind in T28_KINDS:
        caseload = kind == "caseload"
        for year, column in columns.items():
            projection = year >= T28_FIRST_FORECAST
            record_set_id = (
                f"dwp.young_people_work_interim_2026.table_28.{kind}.fy{year}"
            )
            rows = []
            for ordinal, (benefit, caseload_row, expenditure_row, _) in enumerate(
                T28_BENEFITS
            ):
                row = caseload_row if caseload else expenditure_row
                guards = [guard("B", row, T28_KINDS[kind], "caseload or expenditure")]
                if ordinal == 0:
                    guards = [
                        guard("A", 2, T28_TITLE, "table title"),
                        guard("A", 3, T28_POPULATION, "population"),
                        guard("A", 4, period_line, "projection period"),
                    ] + guards
                rows.append(
                    category_row(
                        "health_and_disability_benefit",
                        benefit,
                        ordinal,
                        row,
                        guards=guards,
                    )
                )
            if year >= first_projection:
                period_notes = (
                    f"DWP's projection for the review: Table 28's '{period_line}' is "
                    "the annex's 'fifteen-year caseload projections'. The period value "
                    "stores the opening year."
                )
            elif projection:
                period_notes = (
                    f"The year before Table 28's projection period ('{period_line}'). "
                    f"The annex: '{T28_DATA_SOURCE}', and those tables still forecast "
                    "2025-26 (dwp-benefit-expenditure-caseload-spring-2026 types the "
                    "year the same way), so it is typed as DWP's projection. The period "
                    "value stores the opening year."
                )
            else:
                period_notes = (
                    f"A year before Table 28's projection period ('{period_line}'), and "
                    "an outturn year in the Autumn Budget 2025 benefit caseload and "
                    "expenditure tables. The period value stores the opening year."
                )
            record_sets.append(
                {
                    "record_set_id": record_set_id,
                    "provenance_class": "model_output"
                    if projection
                    else "administrative",
                    "assertion": "source_projection" if projection else "observation",
                    "record_set_spec_id": f"{record_set_id}.v1",
                    "source_record_id_prefix": record_set_id,
                    "sheet_name": T28,
                    "period_type": "fiscal_year",
                    "period": year,
                    "period_coverage": fiscal_coverage(
                        year, dash_year(year), period_notes
                    ),
                    **ENGLAND_AND_WALES,
                    "entity": "person" if caseload else "government",
                    "entity_role": "claimant" if caseload else "payer",
                    "domain": "social_security",
                    "groupby_dimension": "health_and_disability_benefit",
                    "shared_filters": dict(AGE_16_TO_24),
                    "shared_constraints": list(AGE_16_TO_24_CONSTRAINTS),
                    "rows": rows,
                    "measures": [
                        measure_spec(
                            f"{kind}_{year}",
                            f"{T28_KINDS[kind]}, aged 16-24, {dash_year(year)}",
                            column,
                            6,
                            dash_year(year),
                            concept=(
                                "dwp.benefit_caseload_count"
                                if caseload
                                else "dwp.benefit_expenditure_amount"
                            ),
                            unit="count" if caseload else "gbp",
                            aggregation="sum",
                            evidence_url=INTERIM_ANNEX,
                            notes=t28_notes(kind, column, year),
                            scale=None if caseload else 1_000_000,
                        )
                    ],
                }
            )
    payload = package_payload(
        package_id=INTERIM_PACKAGE_ID,
        label=(
            "DWP, Young people and work: interim report, analytical annex Table 28: PIP "
            "and UC health element (LCWRA) caseloads and expenditure, aged 16-24, "
            "England and Wales, 2019-20 to 2040-41"
        ),
        record_sets=record_sets,
        artifact={
            "source_name": "dwp",
            "source_table": (
                "Young people and work: interim report, analytical annex data tables, "
                f"{T28_TITLE}"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{INTERIM_DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "young_people_work_interim_annex_2026_08_10",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": f"ODS used-range cell parse ({entry['filename']})",
            "parser": "ods_used_range",
            "artifact_year": 2026,
        },
    )
    history = [year for year in columns if year < T28_FIRST_FORECAST]
    header = f"""
    DWP, 'Young people and work: interim report' ({INTERIM_PAGE}), analytical annex
    data tables (ODS; published with the report on 28 May 2026, the file replaced on 10
    August 2026 when 'an error in the Excel formula' was corrected in Table 23 only),
    Table 28, for {ISSUE} item 1 ({DASHBOARD}#1). Written by {SCRIPT} from the pinned
    workbook; edit that, not this.

    Ported: Table 28 '{T28_TITLE.split(": ", 1)[1]}', all four rows (the UC health
    element, 'UCH - LCWRA', and PIP; caseload and expenditure) in every year the table
    prints, {dash_year(T28_FIRST_YEAR)} to {dash_year(T28_LAST_YEAR)}. Benefit is the
    filter health_and_disability_benefit (uc_health_lcwra, personal_independence_payment),
    on DWP's own concepts dwp.benefit_caseload_count and dwp.benefit_expenditure_amount
    (as dwp-benefit-expenditure-caseload-spring-2026 uses them), at age_band 16_to_24
    (ages 16 to 24, as the title says) and England and Wales ('{T28_POPULATION}').
    Caseloads are people (entity person, role claimant): the annex defines UC Health as
    '{T28_DEFINITION}'. Expenditure is entity government, role payer, scaled from £
    million to pounds. The workbook's other 57 tables are not ported.

    Outturn and projection: the table's period line reads '{period_line}', the annex's
    'fifteen-year caseload projections'. The annex: '{T28_DATA_SOURCE}', and those
    tables still forecast 2025-26 (dwp-benefit-expenditure-caseload-spring-2026 types
    the year the same way). So {dash_year(T28_FIRST_FORECAST)} to
    {dash_year(last_projection)} are DWP's projections (provenance model_output,
    assertion source_projection), and {dash_year(history[0])} to
    {dash_year(history[-1])}, outturn years in those tables, are the series' history
    (administrative, observation; 'Source: DWP administrative data'). The annex:
    '{T28_CAVEATS}'

    Rounding (the table's notes): '{T28_NOTES[11]}' '{T28_NOTES[12]}'. Neither the
    table nor the annex names a price basis, so none is asserted.

    Checks: the annex's findings (section 18.5) quote this table, and the generator
    asserts each: PIP expenditure 'approximately £1.3 billion in the financial year
    ending 2020' and 'around £3.3 billion in the financial year ending 2025'; '£6.5
    billion and cover 700,000 young people' in five years' time (2031-32: 6,500 and
    703,000); 'up to 877,000 and £9.2 billion' and the LCWRA caseload '229,000' and
    '£750 million' in the financial year ending 2041. The cover sheet prints
    'Published:28 May 2025', a slip for 2026. {fact_count(payload)} facts.
    """
    return render(header, payload)


# ---------------------------------------- 2. the final report's data tables 2 and 3

FINAL_DIRECTORY = "dwp/welfare_state_to_working_state_tables_2026"
FINAL_PACKAGE_ID = "dwp-welfare-state-to-working-state-tables-2026"
FINAL_PAGE = (
    "https://www.gov.uk/government/publications/"
    "from-a-welfare-state-to-a-working-state-a-new-settlement-for-the-next-generation"
)
FINAL_ANNEX = f"{FINAL_PAGE}/from-a-welfare-state-to-a-working-state-analytical-annex"
FINAL_TITLE = "From a Welfare State to a Working State"
FINAL_GUIDANCE = {
    9: (
        "Analysis to inform the From a Welfare State to a Working State report has been "
        "led and coordinated by an independent team of government and external analysts."
    ),
    12: (
        "The analysis produced to inform the From a Welfare State to a Working State "
        "report, including the material contained in this annex, should not be regarded "
        "as official government analysis or as representing agreed government policy."
    ),
}
FINAL_NOTES = {
    3: ("[Note 1]", "These figures have been rounded to the nearest £100 million"),
    4: (
        "[Note 2]",
        "[low] denotes a negligible figure, i.e. a figure that rounds to zero but is not "
        "zero",
    ),
    5: ("[Note 3]", "These figures have been rounded to the nearest 1 decimal place"),
}
T2_TITLE = (
    "Table 2: Annual cost and saving per policy area in 2036/37, £m, 2026/27 prices"
)
T2_SOURCE = (
    "Source: internal modelling for the From a Welfare State to a Working State, this "
    "analysis is explained in sections 1 and 3 of the accompanying analytical annex"
)
# The geographical coverage the analytical annex states for each policy area ('The
# geographical coverage of the costs vary, in part depending on the devolved
# responsibilities of the departments involved'), as (record set, geography, concept
# relation, the annex's words). 'Approximate' marks a stamp the costs only partly
# share: youth hiring incentives mix Great Britain grants with England-only
# apprenticeships; section 3 names no coverage for the fiscal offsets; and the net total
# sums all of them.
T2_COVERAGE = {
    "opportunity_and_support_guarantees": (
        "great_britain",
        GREAT_BRITAIN,
        "source_label",
        "Costs are modelled on the assumption of the support being available across "
        "Great Britain.",
    ),
    "health": (
        "england",
        ENGLAND,
        "source_label",
        "The costs associated with these policies are for England only as health "
        "responsibilities outside England are devolved policy.",
    ),
    "education": (
        "england",
        ENGLAND,
        "source_label",
        "The costs associated with these policies are for England only as education "
        "responsibilities outside England are devolved policy.",
    ),
    "youth_hiring_incentives": (
        "great_britain_mixed",
        GREAT_BRITAIN,
        "approximate",
        "The grants will be available to young people not in employment, education or "
        "training aged up to 24 years old and in Great Britain. ... The costs associated "
        "with this policy are for England only as apprenticeships outside England are "
        "devolved policy.",
    ),
    "welfare_savings": (
        "united_kingdom",
        UNITED_KINGDOM,
        "source_label",
        "The estimates cover impacts on PIP and UC expenditure across the UK.",
    ),
    "fiscal_offsets": (
        "united_kingdom_mixed",
        UNITED_KINGDOM,
        "approximate",
        "(section 3 names no coverage) 'As young people stop being NEET and move into "
        "employment, this will generate income in the form of tax, National Insurance "
        "and indirect tax as they increase their spending. If they were claiming "
        "benefits, their claims may reduce or stop resulting in savings for the State.'",
    ),
    "total_net_cost": (
        "united_kingdom_mixed",
        UNITED_KINGDOM,
        "approximate",
        "'The net cost value is the sum of the gross costs, direct welfare savings from "
        "proposed reforms and fiscal offsets' (section 3), whose coverage varies by "
        "policy area.",
    ),
}
# Row, policy area (None for 'Local system reform', whose '[low]' emits no fact) and the
# cell as printed.
T2_ROWS = (
    (9, None, "Local system reform", "[low]"),
    (10, "opportunity_and_support_guarantees", None, 1900),
    (11, "health", None, 700),
    (12, "education", None, 2100),
    (13, "youth_hiring_incentives", None, 1100),
    (14, "welfare_savings", None, -3600),
    (15, "fiscal_offsets", None, -2400),
    (16, "total_net_cost", None, -200),
)
T2_GEOGRAPHY_NAMES = {
    "great_britain": "Great Britain",
    "england": "England",
    "great_britain_mixed": "Great Britain (mixed coverage)",
    "united_kingdom": "United Kingdom",
    "united_kingdom_mixed": "United Kingdom (mixed coverage)",
}
T3_TITLE = "Table 3: Total NEET rate impact profile, UK, 2026/27 to 2036/27"
T3_SOURCE = (
    "Source: internal modelling for the From a Welfare State to a Working State, this "
    "analysis is explained in section 2 of the accompanying analytical annex"
)
T3_ROWS = ((9, "baseline"), (10, "with_report_recommendations"))
T3_FIRST_YEAR, T3_LAST_YEAR = 2026, 2036  # columns B (2026/27) to L (2036/37)
# The analytical annex's section 2, quoted in the notes.
T3_BASELINE = (
    "The baseline forecast was derived from a central, seasonally-adjusted NEET "
    "projection scenario from Youth Futures Foundation (YFF) SARIMAX modelling using "
    "Labour Force Survey data from the Office for National Statistics (ONS) and Office "
    "for Budget Responsibility economic projections."
)
T3_ADJUSTMENTS = (
    "DWP and DfE internal analysis informed further adjustments to the baseline for the "
    "impacts of some employment programmes and education changes already in train or "
    "announced but not captured in the underlying data."
)
T3_AGES = (
    "Reductions in the headline NEET rates and volumes for 16 to 24 year olds are built "
    "up from the individual key policies included in the costs in section 1 above."
)


def final_caveat() -> str:
    return f"The data tables' guidance: '{FINAL_GUIDANCE[9]}' '{FINAL_GUIDANCE[12]}'"


def build_final() -> str:
    entry, content = pinned(FINAL_DIRECTORY)
    grid = grid_of(content, entry["filename"])
    assert grid[("Cover", 1, "A")] == FINAL_TITLE
    assert grid[("Cover", 3, "A")] == "Published:17th November 2026"
    contents = {
        9: (1, "Average annual investment in major NEET schemes, UK, £bn, 2026 prices"),
        10: (2, "Annual cost and saving per policy area in 2036/37, £m, 2026 prices"),
        11: (3, "Total NEET rate impact profile, UK, 2026/27 to 2036/27"),
    }
    for row, (number, description) in contents.items():
        assert grid[("Contents", row, "A")] == number, row
        assert grid[("Contents", row, "B")] == description, row
    for row, (note, text) in FINAL_NOTES.items():
        assert grid[("Notes", row, "A")] == note and grid[("Notes", row, "B")] == text
    for row, text in FINAL_GUIDANCE.items():
        assert grid[("Guidance", row, "A")] == text, row
    # Table 2.
    assert grid[("2", 3, "A")] == (
        "Relevant notes can be found on the notes worksheet. See notes [1] and [2]."
    )
    assert grid[("2", 5, "A")] == T2_SOURCE
    assert grid[("2", 6, "A")] == T2_TITLE
    assert grid[("2", 7, "B")] == "£ millions"
    assert grid[("2", 8, "A")] == "Policy area"
    assert grid[("2", 8, "B")] == "Annual cost/saving"
    published: dict[str, int] = {}
    for row, area, printed, value in T2_ROWS:
        label = printed if area is None else VALUE_LABELS["policy_area"][area]
        assert grid[("2", row, "A")] == label, row
        assert grid[("2", row, "B")] == value, (row, grid[("2", row, "B")])
        if area is not None:
            published[area] = value
    assert max(row for sheet, row, _ in grid if sheet == "2") == 16
    details = sum(
        value for area, value in published.items() if area != "total_net_cost"
    )
    # 'Local system reform' is '[low]', a figure that rounds to zero.
    assert details == published["total_net_cost"], details
    # Table 3.
    assert grid[("3", 3, "A")] == (
        "Relevant notes can be found on the notes worksheet. See note [3]."
    )
    assert grid[("3", 5, "A")] == T3_SOURCE
    assert grid[("3", 6, "A")] == T3_TITLE
    assert grid[("3", 7, "L")] == "Percentage"
    assert grid[("3", 8, "A")] == "NEET rate projections"
    t3_columns: dict[int, str] = {}
    for offset, year in enumerate(range(T3_FIRST_YEAR, T3_LAST_YEAR + 1)):
        column = get_column_letter(2 + offset)
        assert grid[("3", 8, column)] == slash_year(year), (column, year)
        t3_columns[year] = column
    assert ("3", 8, get_column_letter(2 + len(t3_columns))) not in grid
    rates: dict[tuple[str, int], float] = {}
    for row, scenario in T3_ROWS:
        assert grid[("3", row, "A")] == VALUE_LABELS["neet_rate_projection"][scenario]
        for year, column in t3_columns.items():
            value = grid[("3", row, column)]
            assert is_number(value) and 0 < value < 100, (row, column, value)
            assert abs(value - round(value, 1)) < 1e-9, (row, column, value)  # Note 3
            rates[(scenario, year)] = value
    assert max(row for sheet, row, _ in grid if sheet == "3") == 10
    # The recommendations start after 2026/27, and lower the rate every year after.
    assert rates[("baseline", 2026)] == rates[("with_report_recommendations", 2026)]
    for year in range(T3_FIRST_YEAR + 1, T3_LAST_YEAR + 1):
        assert rates[("with_report_recommendations", year)] < rates[("baseline", year)]
    # 'The modelling shows that in 2036 the reforms and policies that are proposed in
    # this report will lead to: a NEET rate of around 6.8%' (annex section 2).
    assert round(rates[("with_report_recommendations", 2036)], 1) == 6.8
    caveat = final_caveat()
    record_sets = []
    t2_row_numbers = {area: row for row, area, _, _ in T2_ROWS if area is not None}
    for group in T2_GEOGRAPHY_NAMES:
        areas = [area for area, coverage in T2_COVERAGE.items() if coverage[0] == group]
        _, place, relation, _ = T2_COVERAGE[areas[0]]
        record_set_id = (
            f"dwp.welfare_state_to_working_state_2026.table_2.{group}.fy2036"
        )
        rows = []
        for ordinal, area in enumerate(areas):
            row = t2_row_numbers[area]
            guards = [guard("A", 6, T2_TITLE, "table title")] if ordinal == 0 else None
            rows.append(
                category_row(
                    "policy_area",
                    area,
                    ordinal,
                    row,
                    kind="total" if area == "total_net_cost" else "detail",
                    guards=guards,
                )
            )
        coverage = " ".join(
            f"{VALUE_LABELS['policy_area'][area]}: '{T2_COVERAGE[area][3]}'"
            if not T2_COVERAGE[area][3].startswith(("(", "'"))
            else f"{VALUE_LABELS['policy_area'][area]}: {T2_COVERAGE[area][3]}"
            for area in areas
        )
        notes = (
            f"From a Welfare State to a Working State data tables (DWP, 17 November "
            f"2026), {T2_TITLE}: '{T2_SOURCE}'. Column B ('Annual cost/saving', £ "
            "millions; savings negative), 'rounded to the nearest £100 million' (Note "
            "1), scaled to pounds. The annex's Table 1 prints the same 2036/37 figures "
            "'in real-terms 2026/27 prices'. Coverage, as the annex states it for each "
            f"policy area: {coverage} {caveat}"
        )
        record_sets.append(
            {
                "record_set_id": record_set_id,
                "provenance_class": "model_output",
                "assertion": "source_projection",
                "record_set_spec_id": f"{record_set_id}.v1",
                "source_record_id_prefix": record_set_id,
                "sheet_name": "2",
                "period_type": "fiscal_year",
                "period": 2036,
                "period_coverage": fiscal_coverage(
                    2036,
                    "2036/37",
                    "The recommended policies' annual cost or saving in 2036/37, in "
                    "2026/27 prices; the period value stores the opening year.",
                ),
                **place,
                "entity": "government",
                "entity_role": "public_sector",
                "domain": "public_sector_finances",
                "groupby_dimension": "policy_area",
                "shared_filters": {"price_basis": "2026_27_prices"},
                "shared_constraints": [
                    constraint(
                        "price_basis", "2026_27_prices", DIMENSION_LABELS["price_basis"]
                    )
                ],
                "rows": rows,
                "measures": [
                    measure_spec(
                        "annual_cost_or_saving_2036",
                        "Annual cost/saving, 2036/37, £m, 2026/27 prices",
                        "B",
                        8,
                        "Annual cost/saving",
                        concept="dwp.recommended_policy_package_annual_cost",
                        unit="gbp",
                        aggregation="sum",
                        evidence_url=FINAL_ANNEX,
                        notes=notes,
                        relation=relation,
                        scale=1_000_000,
                    )
                ],
            }
        )
    for year, column in t3_columns.items():
        record_set_id = (
            f"dwp.welfare_state_to_working_state_2026.table_3.neet_rate.fy{year}"
        )
        rows = [
            category_row(
                "neet_rate_projection",
                scenario,
                ordinal,
                row,
                guards=[guard("A", 6, T3_TITLE, "table title")]
                if ordinal == 0
                else None,
            )
            for ordinal, (row, scenario) in enumerate(T3_ROWS)
        ]
        notes = (
            f"From a Welfare State to a Working State data tables (DWP, 17 November "
            f"2026), {T3_TITLE} (sic: the columns run to 2036/37): '{T3_SOURCE}'. Column "
            f"{column} ('{slash_year(year)}'), percentage, 'rounded to the nearest 1 "
            f"decimal place' (Note 3). The analytical annex (section 2): '{T3_AGES}' "
            f"'{T3_BASELINE}' '{T3_ADJUSTMENTS}' {caveat}"
        )
        record_sets.append(
            {
                "record_set_id": record_set_id,
                "provenance_class": "model_output",
                "assertion": "source_projection",
                "record_set_spec_id": f"{record_set_id}.v1",
                "source_record_id_prefix": record_set_id,
                "sheet_name": "3",
                "period_type": "fiscal_year",
                "period": year,
                "period_coverage": fiscal_coverage(
                    year,
                    slash_year(year),
                    "A projection by the review's analysts; the period value stores "
                    "the opening year.",
                ),
                **UNITED_KINGDOM,
                "entity": "person",
                "entity_role": "young_person",
                "domain": "employment",
                "groupby_dimension": "neet_rate_projection",
                "shared_filters": dict(AGE_16_TO_24),
                "shared_constraints": list(AGE_16_TO_24_CONSTRAINTS),
                "rows": rows,
                "measures": [
                    measure_spec(
                        f"neet_rate_{year}",
                        f"NEET rate, aged 16-24, {slash_year(year)}",
                        column,
                        8,
                        slash_year(year),
                        concept="dwp.neet_rate_projection",
                        unit="percent",
                        aggregation="share",
                        evidence_url=FINAL_ANNEX,
                        notes=notes,
                    )
                ],
            }
        )
    payload = package_payload(
        package_id=FINAL_PACKAGE_ID,
        label=(
            "DWP, From a Welfare State to a Working State data tables 2 and 3: the "
            "recommended policies' annual cost and saving by policy area in 2036-37, and "
            "the NEET rate projected with and without them, 2026-27 to 2036-37"
        ),
        record_sets=record_sets,
        artifact={
            "source_name": "dwp",
            "source_table": (
                "From a Welfare State to a Working State: data tables, Table 2 (annual "
                "cost and saving per policy area in 2036/37) and Table 3 (total NEET rate "
                "impact profile)"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{FINAL_DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "welfare_state_to_working_state_2026_11_17",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": f"ODS used-range cell parse ({entry['filename']})",
            "parser": "ods_used_range",
            "artifact_year": 2026,
        },
    )
    header = f"""
    DWP, '{FINAL_TITLE}: a new settlement for the next generation' (published 17
    November 2026, {FINAL_PAGE}), the accompanying data tables (ODS), for {ISSUE} item
    2 ({DASHBOARD}#1). Written by {SCRIPT} from the pinned workbook; edit that, not
    this.

    The workbook holds three tables, and none carries young people's PIP or UC health
    caseloads or spending: the review's annex (section 9) takes its 2036/37 PIP and DLA
    caseloads from the interim report's forecasts, which
    dwp-young-people-pip-lcwra-projections-2026 ports (Table 28). Ported here, as #442
    asks, the two comparators:

    Table 2, '{T2_TITLE.split(": ", 1)[1]}': the annual cost (positive) or saving
    (negative) of the review's recommended policies in 2036/37 by policy area, and the
    'Total NET Cost', on concept dwp.recommended_policy_package_annual_cost with filters
    policy_area and price_basis 2026_27_prices, scaled from £ million to pounds. The
    annex: 'The geographical coverage of the costs vary, in part depending on the
    devolved responsibilities of the departments involved', so each policy area carries
    the coverage the annex states for it (Opportunity and Support Guarantees Great
    Britain; health and education England; welfare savings the United Kingdom). Youth
    hiring incentives mix Great Britain grants with England-only apprenticeships, the
    annex names no coverage for the fiscal offsets, and the net total sums them all:
    those three are stamped Great Britain, the United Kingdom and the United Kingdom,
    with concept relation approximate. 'Local system reform' is '[low]', '{FINAL_NOTES[4][1]}'
    (the annex: 'less than £100m'), and emits no fact; the other rows sum to the total.

    Table 3, '{T3_TITLE.split(": ", 1)[1]}' (sic: its columns run 2026/27 to 2036/37):
    the 'Projected baseline NEET rate' and the 'Projected NEET rate with report
    recommendations', filter neet_rate_projection, for 16 to 24 year olds in the United
    Kingdom, on concept dwp.neet_rate_projection, percent. The annex: '{T3_BASELINE}'
    '{T3_ADJUSTMENTS}' The generator asserts that the two agree in 2026/27, that the
    recommendations lower the rate every later year, and the annex's 'a NEET rate of
    around 6.8%' in 2036.

    Both tables are the review's 'internal modelling' (provenance model_output,
    assertion source_projection). {caveat} Not ported: Table 1 ('Average annual
    investment in major NEET schemes, UK, 2026 prices'), whose schemes' periods the
    table does not give. {fact_count(payload)} facts.
    """
    return render(header, payload)


# ---------------------------------------------------------------- the packages

BUILDERS = {
    INTERIM_DIRECTORY: build_interim,
    FINAL_DIRECTORY: build_final,
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
