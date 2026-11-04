"""Generate the source packages for PolicyEngine/chronicle#407.

Run from the repository root:

    uv run python scripts/build_uk_occupation_packages.py

``--check`` compares the generated YAML with the committed files instead of writing.
Every package is written from its pinned artifact, read with Chronicle's own parsers,
so every row number, column and guard cell below is one the package parser sees. The
publisher's text is asserted cell by cell, so a run against different bytes fails
rather than drifting. Nothing is downloaded and no value is computed.

- ``ons-aps218-occupation-*``: ONS Annual Population Survey estimates on Nomis (dataset
  APS218, NM_218_1) of people in employment by SOC 2020 major and sub-major group, by
  sex and by employee or self-employed status, for the UK, its four countries and the
  nine English regions: April 2024 to March 2025, January to December 2025 and April
  2025 to March 2026, each estimate with the half-width of its confidence interval
  where Nomis publishes one.
- ``ons-ashe-table2-*``: ONS ASHE Table 2 (earnings by two-digit SOC 2020) for the UK,
  2024 revised, 2025 revised and 2026 provisional: Tables 2.1a (gross weekly pay) and
  2.7a (gross annual pay), and the coefficients of variation ONS publishes for them in
  Tables 2.1b and 2.7b.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import textwrap
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from openpyxl.utils import get_column_letter

from chronicle.sources.cells import SourceArtifactMetadata, source_cells_from_xlsx
from chronicle.sources.rows import source_rows_from_delimited_text

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-11-04"
ISSUE = "PolicyEngine/chronicle#407"
CONSUMER = "PolicyEngine/microcosm#1490"
SCRIPT = "scripts/build_uk_occupation_packages.py"


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


def constraint(variable: str, value: object, label: str) -> Flow:
    return Flow(variable=variable, operator="==", value=value, label=label)


def guard(column: str, row: int, value: object, label: str) -> Flow:
    return Flow(column=column, row=row, expected_value=value, label=label)


# ---------------------------------------------------------------- SOC 2020 groups

# The nine major and 26 sub-major groups of SOC 2020, in ASHE Table 2's wording, which
# the generator asserts against every ASHE sheet. Nomis prints the same codes with its
# own capitalisation (and truncates major group 1); its text is guarded on each row.
SOC_MAJOR_GROUPS = {
    1: "Managers, directors and senior officials",
    2: "Professional occupations",
    3: "Associate professional occupations",
    4: "Administrative and secretarial occupations",
    5: "Skilled trades occupations",
    6: "Caring, leisure and other service occupations",
    7: "Sales and customer service occupations",
    8: "Process, plant and machine operatives",
    9: "Elementary occupations",
}
SOC_SUB_MAJOR_GROUPS = {
    11: "Corporate managers and directors",
    12: "Other managers and proprietors",
    21: "Science, research, engineering and technology professionals",
    22: "Health professionals",
    23: "Teaching and other educational professionals",
    24: "Business, media and public service professionals",
    31: "Science, engineering and technology associate professionals",
    32: "Health and social care associate professionals",
    33: "Protective service occupations",
    34: "Culture, media and sports occupations",
    35: "Business and public service associate professionals",
    41: "Administrative occupations",
    42: "Secretarial and related occupations",
    51: "Skilled agricultural and related trades",
    52: "Skilled metal, electrical and electronic trades",
    53: "Skilled construction and building trades",
    54: "Textiles, printing and other skilled trades",
    61: "Caring personal service occupations",
    62: "Leisure, travel and related personal service occupations",
    63: "Community and civil enforcement occupations",
    71: "Sales occupations",
    72: "Customer service occupations",
    81: "Process, plant and machine operatives",
    82: "Transport and mobile machine drivers and operatives",
    91: "Elementary trades and related occupations",
    92: "Elementary administration and service occupations",
}
ALL_OCCUPATIONS = "All occupations"


@dataclass(frozen=True)
class Occupation:
    code: int | None  # None for all occupations
    label: str

    @property
    def value_id(self) -> str:
        return "all" if self.code is None else f"soc_{self.code}"

    @property
    def major(self) -> bool:
        return self.code is not None and self.code < 10

    def dimension(self) -> tuple[str, int] | None:
        if self.code is None:
            return None
        return (
            ("soc2020_major_group", self.code)
            if self.major
            else ("soc2020_sub_major_group", self.code)
        )


# All occupations, then each major group followed by its sub-major groups: the order
# both publishers print them in.
OCCUPATIONS = (Occupation(None, ALL_OCCUPATIONS),) + tuple(
    occupation
    for major, label in SOC_MAJOR_GROUPS.items()
    for occupation in (
        Occupation(major, label),
        *(
            Occupation(code, sub_label)
            for code, sub_label in SOC_SUB_MAJOR_GROUPS.items()
            if code // 10 == major
        ),
    )
)
assert len(OCCUPATIONS) == 36

SOC_DIMENSION_LABELS = {
    "soc2020_major_group": "SOC 2020 major group",
    "soc2020_sub_major_group": "SOC 2020 sub-major group",
}

# Labels for every dimension and value the packages use. A package declares the
# ones its facts use (Chronicle refuses a declaration no fact uses); the values two
# packages emit are also in chronicle/dimension_values/canonical_labels.json.
DIMENSION_LABELS = {
    "soc2020_group": "SOC 2020 occupation group",
    **SOC_DIMENSION_LABELS,
    "sex": "Sex",
    "employment_status": "Employment status",
    "working_pattern": "Working pattern",
    "statistic": "Statistic",
    "earnings_percentile": "Earnings percentile",
}
VALUE_LABELS = {
    "soc2020_major_group": {
        str(code): label for code, label in SOC_MAJOR_GROUPS.items()
    },
    "soc2020_sub_major_group": {
        str(code): label for code, label in SOC_SUB_MAJOR_GROUPS.items()
    },
    "sex": {"all": "All", "male": "Male", "female": "Female"},
    "employment_status": {
        "all": "All in employment",
        "employee": "Employees",
        "self_employed": "Self-employed",
    },
    "working_pattern": {
        "all": "Full-time and part-time",
        "full_time": "Full-time",
        "part_time": "Part-time",
    },
    "statistic": {
        "estimate": "Estimate",
        "confidence_interval_half_width": "Confidence interval half-width",
        "coefficient_of_variation": "Coefficient of variation",
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
    label = DIMENSION_LABELS[variable]
    return {variable: value}, [constraint(variable, value, label)]


def shared(*pairs: tuple[str, str]) -> tuple[dict, list[Flow]]:
    filters: dict = {}
    constraints: list[Flow] = []
    for variable, value in pairs:
        more_filters, more_constraints = category(variable, value)
        filters.update(more_filters)
        constraints += more_constraints
    return filters, constraints


def occupation_semantics(occupation: Occupation) -> tuple[Flow, list[Flow]] | None:
    dimension = occupation.dimension()
    if dimension is None:
        return None
    variable, code = dimension
    return Flow({variable: code}), [
        constraint(variable, code, SOC_DIMENSION_LABELS[variable])
    ]


UNITED_KINGDOM = {
    "geography_id": "K02000001",
    "geography_level": "country",
    "geography_name": "United Kingdom",
    "geography_vintage": "current",
}


# ---------------------------------------------------------------- 1. Nomis APS218

NOMIS_PAGE = "https://www.nomisweb.co.uk/datasets/aps218"
NOMIS_SOURCES = "https://www.nomisweb.co.uk/sources/aps"
NOMIS_TITLE = "annual population survey - regional - occupation (SOC2020) by sex by employment type"
APS_INSTRUMENT = "Annual Population Survey"
APS_COLUMNS = (
    "DATE_NAME",
    "GEOGRAPHY_CODE",
    "GEOGRAPHY_NAME",
    "C_SEX_NAME",
    "ETYPE_NAME",
    "FTPT_NAME",
    "JTYPE_NAME",
    "SOC2020_FULL_NAME",
    "MEASURE_NAME",
    "MEASURES_NAME",
    "OBS_VALUE",
    "OBS_STATUS",
    "OBS_STATUS_NAME",
)
COLUMN = {name: get_column_letter(index + 1) for index, name in enumerate(APS_COLUMNS)}
# Nomis's observation statuses in these responses, as its OBS_STATUS_NAME column words them.
APS_STATUSES = {
    "A": "Normal Value",
    "F": (
        "Estimate and confidence interval not available since the group sample size is "
        "zero or disclosive (0-2)"
    ),
    "G": (
        "Estimate and confidence interval unreliable since the group sample size is "
        "small (3-9)"
    ),
    "H": "Estimate is less than 500",
}
# Geography code, Chronicle level, and the name Chronicle's UK register gives it (Nomis
# names E12000006 'East').
APS_GEOGRAPHIES = (
    ("K02000001", "country", "United Kingdom"),
    ("E92000001", "country", "England"),
    ("W92000004", "country", "Wales"),
    ("S92000003", "country", "Scotland"),
    ("N92000002", "country", "Northern Ireland"),
    ("E12000001", "region", "North East"),
    ("E12000002", "region", "North West"),
    ("E12000003", "region", "Yorkshire and The Humber"),
    ("E12000004", "region", "East Midlands"),
    ("E12000005", "region", "West Midlands"),
    ("E12000006", "region", "East of England"),
    ("E12000007", "region", "London"),
    ("E12000008", "region", "South East"),
    ("E12000009", "region", "South West"),
)
APS_COUNTRIES = ("E92000001", "W92000004", "S92000003", "N92000002")
APS_REGIONS = tuple(code for code, level, _ in APS_GEOGRAPHIES if level == "region")
# Chronicle value id and the Nomis C_SEX_NAME and ETYPE_NAME it reads.
APS_SEXES = (("all", "All persons"), ("male", "Males"), ("female", "Females"))
APS_EMPLOYMENT = (
    ("all", "Total"),
    ("employee", "Employee"),
    ("self_employed", "Self-employed"),
)
# Chronicle statistic and the Nomis MEASURES_NAME it reads.
APS_STATISTICS = (
    ("estimate", "Value"),
    ("confidence_interval_half_width", "Confidence"),
)
APS_CONCEPT = "ons.aps_people_in_employment"
# The interval has a concept of its own, as the ACS packages' margins of error do, so a
# reader that selects by concept never sums an estimate with its interval.
APS_INTERVAL_CONCEPT = f"{APS_CONCEPT}_confidence_interval_half_width"
# Every major group adds to slightly less than the all-occupations total; the most the
# packages' totals exceed their parts by, as a share of the total.
APS_MAJOR_GAP_LIMIT = 0.01


@dataclass(frozen=True)
class ApsPeriod:
    slug: str
    nomis_date: str
    label: str
    period_type: str
    period: int
    start_date: str
    end_date: str
    released: str
    artifact_year: int
    title: str

    @property
    def package_id(self) -> str:
        return f"ons-aps218-occupation-{self.slug.replace('_', '-')}"

    @property
    def directory(self) -> str:
        return f"ons/aps218_occupation_{self.slug}"

    @property
    def filename(self) -> str:
        return f"aps218_occupation_{self.slug}.csv"


APS_PERIODS = (
    ApsPeriod(
        slug="apr_2024_mar_2025",
        nomis_date="2025-03",
        label="Apr 2024-Mar 2025",
        period_type="fiscal_year",
        period=2024,
        start_date="2024-04-01",
        end_date="2025-03-31",
        released="17 July 2025",
        artifact_year=2025,
        title="April 2024 to March 2025",
    ),
    ApsPeriod(
        slug="jan_dec_2025",
        nomis_date="2025-12",
        label="Jan 2025-Dec 2025",
        period_type="calendar_year",
        period=2025,
        start_date="2025-01-01",
        end_date="2025-12-31",
        released="21 April 2026",
        artifact_year=2025,
        title="January to December 2025",
    ),
    ApsPeriod(
        slug="apr_2025_mar_2026",
        nomis_date="2026-03",
        label="Apr 2025-Mar 2026",
        period_type="fiscal_year",
        period=2025,
        start_date="2025-04-01",
        end_date="2026-03-31",
        released="21 July 2026",
        artifact_year=2026,
        title="April 2025 to March 2026",
    ),
)


def nomis_occupation_label(text: str) -> int | None:
    """Nomis's 'Total' -> None; '11 : Corporate Managers And Directors' -> 11."""
    if text == "Total":
        return None
    code, _, name = text.partition(" : ")
    assert code.isdigit() and name, text
    return int(code)


def aps_notes(period: ApsPeriod) -> str:
    return (
        f"Nomis APS218 (NM_218_1), {period.label}, revision 0 released {period.released}: "
        "people in employment resident in the area, by occupation (SOC 2020), full-time "
        "and part-time and all job types together, rounded to the nearest hundred. A "
        "cell Nomis marks F (sample of 0 to 2) or H (estimate under 500) is blank and "
        "emits no fact. An estimate whose interval Nomis marks G ('unreliable since the "
        "group sample size is small (3-9)') or F is published without the interval; "
        "the interval's status is guarded in the estimate's lineage. Nomis's one "
        "revision of the dataset, on 27 January 2023, re-released October 2021 to "
        "September 2022 ('Estimates revised due to identified error'), not this period."
    )


def aps_measure(statistic: str, dimensions: dict) -> dict:
    if statistic == "estimate":
        concept = APS_CONCEPT
        measure_id, label = "people_in_employment", "People in employment"
        notes = (
            "Nomis APS218 measure 'Value' of measure 'Count': the estimated number of "
            "people in employment in the cell, rounded to the nearest hundred."
        )
    else:
        concept = APS_INTERVAL_CONCEPT
        measure_id = "people_in_employment_confidence_interval_half_width"
        label = "People in employment, confidence interval half-width"
        notes = (
            "Nomis APS218 measure 'Confidence' of measure 'Count', published beside "
            "each estimate: the half-width (plus or minus) of the estimate's confidence "
            "interval, in people. Nomis's dataset pages do not state the interval's "
            "level; Scottish Government APS publications call the confidence limits "
            "Nomis publishes 95 per cent limits."
        )
    return {
        "measure_id": measure_id,
        "label": label,
        "ordinal": 0,
        "column": COLUMN["OBS_VALUE"],
        "source_column_id": "OBS_VALUE",
        "source_column_dimensions": Flow(dimensions),
        "expected_column_header_row": 1,
        "expected_column_header": "OBS_VALUE",
        "concept": concept,
        "source_concept": concept,
        "concept_relation": "source_label",
        "concept_authority": "ons",
        "concept_evidence_url": NOMIS_PAGE,
        "concept_evidence_notes": notes,
        "unit": "count",
        "aggregation": "sum",
        "expected_cell_type": "number",
    }


def aps_rows(period: ApsPeriod) -> tuple[dict, dict]:
    """Index the pinned response's rows by their dimension text, asserting its layout."""
    entry, content = pinned(period.directory)
    assert entry["filename"] == period.filename
    assert f"date={period.nomis_date}&" in entry["source_url"]
    rows = source_rows_from_delimited_text(
        content, metadata(period.filename), sheet_name=period.filename
    )
    assert len(rows) == 14 * 3 * 3 * 36 * 2, len(rows)
    index: dict[tuple[str, str, str, int | None, str], object] = {}
    for row in rows:
        values = row.values
        assert tuple(values) == APS_COLUMNS, tuple(values)
        assert values["DATE_NAME"] == period.label, values
        assert (values["FTPT_NAME"], values["JTYPE_NAME"], values["MEASURE_NAME"]) == (
            "Total",
            "Total",
            "Count",
        ), values
        status = values["OBS_STATUS"]
        assert APS_STATUSES[status] == values["OBS_STATUS_NAME"], values
        assert (values["OBS_VALUE"] in (None, "")) == (status != "A"), values
        key = (
            values["GEOGRAPHY_CODE"],
            values["C_SEX_NAME"],
            values["ETYPE_NAME"],
            nomis_occupation_label(values["SOC2020_FULL_NAME"]),
            values["MEASURES_NAME"],
        )
        assert key not in index, key
        index[key] = row
    return entry, index


def aps_check_parity(period: ApsPeriod, index: dict) -> float:
    """Assert the issue's parity checks on the published estimates.

    Sub-major groups add to their major group, the countries to the UK and the regions
    to England, each within the rounding of every count to the nearest hundred. The
    major groups add to the all-occupations total less people in no major group, so
    the total is at least their sum, within rounding, and at most 1 per cent above it.
    Returns the largest gap between a total and its major groups, as a share.
    """

    def value(geography: str, sex: str, status: str, code: int | None) -> int | None:
        row = index[(geography, sex, status, code, "Value")]
        number = row.values["OBS_VALUE"]
        return None if number in (None, "") else number

    def within(parts: list, whole: int | None) -> bool | None:
        if whole is None or None in parts:
            return None
        return abs(sum(parts) - whole) <= 50 * (len(parts) + 1)

    largest_gap = 0.0
    for _, sex in APS_SEXES:
        for _, status in APS_EMPLOYMENT:
            for geography, _, _ in APS_GEOGRAPHIES:
                total = value(geography, sex, status, None)
                majors = [
                    value(geography, sex, status, code) for code in SOC_MAJOR_GROUPS
                ]
                if total is not None and None not in majors:
                    gap = total - sum(majors)
                    assert gap >= -50 * (len(majors) + 1), (geography, sex, status, gap)
                    assert gap <= APS_MAJOR_GAP_LIMIT * total, (
                        geography,
                        sex,
                        status,
                        gap,
                    )
                    largest_gap = max(largest_gap, gap / total)
                for major in SOC_MAJOR_GROUPS:
                    parts = [
                        value(geography, sex, status, code)
                        for code in SOC_SUB_MAJOR_GROUPS
                        if code // 10 == major
                    ]
                    whole = value(geography, sex, status, major)
                    assert within(parts, whole) is not False, (
                        geography,
                        sex,
                        status,
                        major,
                    )
            for occupation in OCCUPATIONS:
                code = occupation.code
                countries = [
                    value(country, sex, status, code) for country in APS_COUNTRIES
                ]
                assert (
                    within(countries, value("K02000001", sex, status, code))
                    is not False
                )
                regions = [value(region, sex, status, code) for region in APS_REGIONS]
                assert (
                    within(regions, value("E92000001", sex, status, code)) is not False
                )
    return largest_gap


def build_aps(period: ApsPeriod) -> str:
    entry, index = aps_rows(period)
    largest_gap = aps_check_parity(period, index)
    coverage = {
        "start_date": period.start_date,
        "end_date": period.end_date,
        "basis": "survey_reference",
        "source_period_label": period.label,
        "notes": aps_notes(period),
    }
    record_sets = []
    for geography, level, name in APS_GEOGRAPHIES:
        for sex, sex_text in APS_SEXES:
            for status, status_text in APS_EMPLOYMENT:
                for statistic, measures_text in APS_STATISTICS:
                    filters, constraints = shared(
                        ("sex", sex),
                        ("employment_status", status),
                        ("statistic", statistic),
                    )
                    rows = []
                    for ordinal, occupation in enumerate(OCCUPATIONS):
                        row = index[
                            (
                                geography,
                                sex_text,
                                status_text,
                                occupation.code,
                                measures_text,
                            )
                        ]
                        if row.values["OBS_STATUS"] != "A":
                            continue
                        number = row.row_number
                        guards = [
                            guard(
                                COLUMN["GEOGRAPHY_CODE"], number, geography, "geography"
                            ),
                            guard(COLUMN["C_SEX_NAME"], number, sex_text, "sex"),
                            guard(
                                COLUMN["ETYPE_NAME"],
                                number,
                                status_text,
                                "employment type",
                            ),
                            guard(
                                COLUMN["MEASURES_NAME"],
                                number,
                                measures_text,
                                "measure",
                            ),
                        ]
                        if statistic == "estimate":
                            interval = index[
                                (
                                    geography,
                                    sex_text,
                                    status_text,
                                    occupation.code,
                                    "Confidence",
                                )
                            ]
                            assert interval.row_number == number + 1
                            guards.append(
                                guard(
                                    COLUMN["OBS_STATUS"],
                                    interval.row_number,
                                    interval.values["OBS_STATUS"],
                                    "interval status",
                                )
                            )
                        spec = {
                            "value_id": occupation.value_id,
                            "label": occupation.label,
                            "ordinal": ordinal,
                            "row_number": number,
                            "expected_row_header_column": COLUMN["SOC2020_FULL_NAME"],
                            "expected_row_header": row.values["SOC2020_FULL_NAME"],
                            "table_record_kind": "total"
                            if occupation.code is None
                            else "detail",
                        }
                        semantics = occupation_semantics(occupation)
                        if semantics is not None:
                            row_filters, row_constraints = semantics
                            spec["filters"] = row_filters
                            spec["constraints"] = row_constraints
                            spec["source_row_dimensions"] = Flow(row_filters)
                        spec["guard_cells"] = guards
                        rows.append(spec)
                    if not rows:
                        continue
                    record_set_id = f"ons.aps218.{period.slug}.{geography.lower()}.{sex}.{status}.{statistic}"
                    record_set = {
                        "record_set_id": record_set_id,
                        "provenance_class": "survey_aggregate",
                        "survey_instrument": APS_INSTRUMENT,
                        "assertion": "observation",
                        "record_set_spec_id": f"{record_set_id}.v1",
                        "source_record_id_prefix": record_set_id,
                        "sheet_name": period.filename,
                        "period_type": period.period_type,
                        "period": period.period,
                        "period_coverage": coverage,
                        "geography_id": geography,
                        "geography_level": level,
                        "geography_name": name,
                        "geography_vintage": "current",
                        "entity": "person",
                        "entity_role": "in_employment",
                        "domain": "employment",
                        "groupby_dimension": "soc2020_group",
                        "shared_filters": filters,
                        "shared_constraints": constraints,
                        "rows": rows,
                        "measures": [aps_measure(statistic, filters)],
                    }
                    record_sets.append(record_set)
    dimension_labels, value_labels = declarations(record_sets)
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": period.package_id,
        "label": (
            "ONS Annual Population Survey (Nomis APS218): people in employment by SOC 2020 "
            "major and sub-major group, sex and employment status, UK, countries and English "
            f"regions, {period.title}"
        ),
        "dimension_labels": dimension_labels,
        "dimension_value_labels": value_labels,
        "artifact": {
            "source_name": "ons",
            "source_table": (
                f"Annual Population Survey, Nomis dataset APS218 (NM_218_1), '{NOMIS_TITLE}', "
                f"{period.label}"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{period.directory}",
            "manifest": "manifest.yaml",
            "vintage": f"nomis_aps218_{period.slug}_revision_0",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": (
                "Nomis API delimited text full-row parse, one source row per geography, "
                "employment type, sex, occupation and measure"
            ),
            "parser": "delimited_text_full_rows",
            "sheet_name": period.filename,
            "artifact_year": period.artifact_year,
        },
        "record_sets": record_sets,
    }
    facts = sum(len(record_set["rows"]) for record_set in record_sets)
    header = f"""
    ONS Annual Population Survey estimates on Nomis, dataset APS218 ('{NOMIS_TITLE}',
    NM_218_1), {period.label}, for {ISSUE} ({CONSUMER}). Written by {SCRIPT} from the
    pinned Nomis API response, long format, one row per geography, employment type,
    sex, occupation and measure.

    People in employment, resident in the UK, its four countries and the nine English
    regions, by sex (all persons, males, females) and by employment type (all,
    employees, self-employed; Nomis's fourth type, 'Other', which 'includes unpaid
    family worker', is not ported), for all occupations and each SOC 2020 major group
    (9) and sub-major group (26), counting full-time and part-time workers and all job
    types together. Nomis describes the APS as 'a residence based labour market
    survey' ({NOMIS_SOURCES}). Each estimate (Nomis 'Value') is a fact of concept
    {APS_CONCEPT}, statistic estimate; the half-width of its confidence interval (Nomis
    'Confidence') is a second fact, of concept {APS_INTERVAL_CONCEPT}
    and statistic confidence_interval_half_width, where Nomis publishes one.
    Nomis does not state the interval's level on the dataset's pages; Scottish
    Government APS publications call the limits Nomis publishes 95 per cent limits.
    Nomis's pages also do not say whether the occupation is that of the main job.
    {facts} facts.

    Nomis rounds counts to the nearest hundred and flags every cell in OBS_STATUS: A
    'Normal Value'; F 'Estimate and confidence interval not available since the group
    sample size is zero or disclosive (0-2)'; G 'Estimate and confidence interval
    unreliable since the group sample size is small (3-9)'; H 'Estimate is less than
    500'. A blank cell (F, H) emits no fact. Nomis marks an interval G, and sometimes
    F, while publishing its estimate: the estimate is ported with its interval's status
    cell guarded, so the flag is in its lineage, and the interval emits no fact.

    Record sets are one per geography, sex, employment type and statistic, with the
    occupations as rows (groupby soc2020_group). A major group's facts carry
    soc2020_major_group, a sub-major group's soc2020_sub_major_group; the
    all-occupations rows are the record sets' totals. The detail rows hold both levels,
    so select one level by its filter and never sum across both. Row labels are SOC 2020
    names in ASHE Table 2's wording; each row's guards compare Nomis's own text.

    Parity on the published estimates, asserted by the generator: each major group's
    sub-major groups add to it, the four countries to the UK and the nine regions to
    England, within Nomis's rounding (50 per summed cell). The nine major groups add to
    less than the all-occupations total, by at most {largest_gap:.2%} of it here; Nomis
    publishes no residual category, so the difference is people in employment who are
    in the total and in no major group.

    Nomis's metadata records one revision of the dataset: on 27 January 2023 it
    re-released October 2021 to September 2022, 'Estimates revised due to identified
    error'. That period is not ported; this one is Nomis revision 0, released
    {period.released}.
    """
    return render(header, payload)


# ---------------------------------------------------------------- 2. ASHE Table 2

ASHE_PAGE = (
    "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/"
    "datasets/occupation2digitsocashetable2"
)
ASHE_INSTRUMENT = "Annual Survey of Hours and Earnings"
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
FIRST_ROW, LAST_ROW, NOT_CLASSIFIED_ROW = 6, 41, 42
PERCENTILES = (10, 20, 25, 30, 40, 60, 70, 75, 80, 90)
# Ported columns: measure id, column, header row, header text.
ASHE_COLUMNS = (
    ("jobs", "C", 4, "of jobsb"),
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
    correction: str

    @property
    def directory(self) -> str:
        return f"ons/ashe_table2_{self.slug}"


BULLETINS = (
    "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/"
    "bulletins/annualsurveyofhoursandearnings/"
)
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
        correction=(
            "ONS's corrections notice of 3 November 2025: 'For the 2024 revised table, we "
            "published the 2024 provisional data instead of the revised data on release "
            "day, 23 October 2025. ... We have now corrected this and the 2024 revised "
            "table now contains the 2024 revised data.' The pinned zip, fetched on 4 "
            "November 2026, is the corrected table."
        ),
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
        correction=(
            "ONS's corrections notice of 19 December 2025 suppressed the 2025 provisional "
            "annual pay estimates for occupations 3312, 331 and 33 for London, the South "
            "East, East and the UK 'for quality reasons', to 'be reviewed for our revised "
            "2025 dataset'. This revised edition prints the UK row of sub-major group 33 "
            "in every sheet of Table 2.7a, with 'x' only where its CV is over 20 per cent."
        ),
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
        correction="",
    ),
)


@dataclass(frozen=True)
class AsheTable:
    key: str  # 2.1a
    pay: str  # weekly / annual
    cv: bool

    @property
    def number(self) -> str:
        return f"Table 2.{self.key}"

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
            f"{edition.member_prefix}Occupation SOC20 (2) {self.number}   "
            f"{self.title} {edition.year}{suffix}.xlsx"
        )

    def package_id(self, edition: AsheEdition) -> str:
        return f"ons-ashe-table2-{self.slug.replace('_', '-')}-{edition.slug.replace('_', '-')}"

    def directory(self, edition: AsheEdition) -> str:
        return f"ons/ashe_table2_{self.slug}_{edition.slug}"


ASHE_TABLES = (
    AsheTable("1a", "weekly", False),
    AsheTable("1b", "weekly", True),
    AsheTable("7a", "annual", False),
    AsheTable("7b", "annual", True),
)


def ashe_grid(edition: AsheEdition, table: AsheTable) -> tuple[str, dict]:
    entry, content = pinned(edition.directory)
    member = table.member(edition)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        (name,) = [item for item in archive.namelist() if item.endswith(member)]
        member_content = archive.read(name)
    cells = source_cells_from_xlsx(member_content, metadata(name))
    grid: dict[tuple[str, int, str], object] = {}
    for cell in cells:
        if cell.raw_value in (None, ""):
            continue
        grid[
            (cell.sheet_name, cell.row_number, get_column_letter(cell.column_number))
        ] = cell.raw_value
    return name, grid


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def ashe_code(grid: dict, sheet: str, row: int) -> object:
    """The code cell as published: "'11" from 2025, '11' in 2024, blank for all employees."""
    return grid.get((sheet, row, "B"))


def ashe_measure(
    edition: AsheEdition, table: AsheTable, sheet: str, population: str, spec: tuple
) -> dict:
    measure_id, column, header_row, header = spec
    pay = "gross weekly pay" if table.pay == "weekly" else "gross annual pay"
    concept = f"ons.ashe_gross_{table.pay}_pay"
    if measure_id == "jobs":
        concept = f"ons.ashe_{table.pay}_pay_jobs"
        label = "Number of jobs"
        what = (
            f"the number of jobs (thousand) in the {pay} estimates, which ONS calls "
            "'for indicative purposes only' (footnote b)"
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
    if table.cv:
        # A concept of its own, as the APS interval has, so a CV is never read as pay.
        concept = f"{concept}_coefficient_of_variation"
        label = f"Coefficient of variation: {label[0].lower()}{label[1:]}"
        what = f"the coefficient of variation (per cent) of {what}"
        unit, scale = "percent", None
    notes = (
        f"ASHE {table.number} ({edition.year} {edition.status}), sheet '{sheet}', column "
        f"{column}: {what}, {population}, United Kingdom."
    )
    measure = {
        "measure_id": measure_id,
        "label": label,
        "ordinal": [item[0] for item in ASHE_COLUMNS].index(measure_id),
        "column": column,
        "source_column_id": measure_id,
        "expected_column_header_row": header_row,
        "expected_column_header": header,
        "concept": concept,
        "source_concept": concept,
        "concept_relation": "source_label",
        "concept_authority": "ons",
        "concept_evidence_url": ASHE_PAGE,
        "concept_evidence_notes": notes,
        "unit": unit,
        "aggregation": aggregation,
    }
    if scale is not None:
        measure["value_scale"] = scale
    measure["expected_cell_type"] = "number"
    if aggregation == "quantile":
        measure["filters"] = Flow(earnings_percentile=header)
        measure["constraints"] = [
            constraint(
                "earnings_percentile", header, DIMENSION_LABELS["earnings_percentile"]
            )
        ]
    return measure


def ashe_coverage(edition: AsheEdition, table: AsheTable) -> tuple[str, int, dict]:
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
                    "affected by absence (table footnote a)."
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
                f"{edition.reference_label}."
            ),
        },
    )


# Sentences the package headers quote, asserted against the workbooks' notes sheets
# and footnotes (whitespace normalised: the 2024 weekly footnote has a no-break space).
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
    ". = unavailable",
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
    "b Figures for Number of Jobs are for indicative purposes only and should not be "
    "considered an accurate estimate of employee job counts."
)


def squeeze(text: object) -> str:
    return " ".join(str(text).replace("\xa0", " ").split())


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
    period_type, period, coverage = ashe_coverage(edition, table)
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
        assert squeeze(grid[(sheet, 43, "A")]).startswith(FOOTNOTE_A[table.pay]), sheet
        assert squeeze(grid[(sheet, 44, "A")]) == FOOTNOTE_B, sheet
        by_signature: dict[tuple[str, ...], list[dict]] = {}
        for offset, occupation in enumerate(OCCUPATIONS):
            row = FIRST_ROW + offset
            text = grid[(sheet, row, "A")]
            code = ashe_code(grid, sheet, row)
            if occupation.code is None:
                assert text == "All employees" and code is None, (
                    sheet,
                    row,
                    text,
                    code,
                )
            else:
                indent = "" if occupation.major else "  "
                assert text == indent + occupation.label, (sheet, row, text)
                assert str(code).lstrip("'") == str(occupation.code), (sheet, row, code)
            ported = []
            for measure_id, column, _, _ in ASHE_COLUMNS:
                value = grid.get((sheet, row, column))
                if is_number(value):
                    ported.append(measure_id)
                    continue
                # 'x' is a CV over 20 per cent, in both tables; a CV table may also
                # print '.', 'unavailable' in its key (the 2024 tables).
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
                "value_id": occupation.value_id,
                "label": occupation.label,
                "ordinal": offset,
                "row_number": row,
                "expected_row_header_column": "A",
                "expected_row_header": text,
                "table_record_kind": "total" if occupation.code is None else "detail",
            }
            semantics = occupation_semantics(occupation)
            if semantics is not None:
                spec["filters"], spec["constraints"] = semantics
                spec["guard_cells"] = [guard("B", row, code, "SOC 2020 code")]
            by_signature.setdefault(tuple(ported), []).append(spec)
        statistic = "coefficient_of_variation" if table.cv else "estimate"
        filters, constraints = shared(
            ("sex", sex), ("working_pattern", pattern), ("statistic", statistic)
        )
        sheet_slug = sheet.lower().replace("-", "_").replace(" ", "_")
        for signature, rows in by_signature.items():
            first = rows[0]
            first["guard_cells"] = [guard("A", 1, title, "table title")] + first.get(
                "guard_cells", []
            )
            missing = [item[0] for item in ASHE_COLUMNS if item[0] not in signature]
            record_set_id = f"ons.ashe_table2.{edition.slug}.{table.slug}.{sheet_slug}"
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
                    "period_coverage": coverage,
                    **UNITED_KINGDOM,
                    "entity": "person",
                    "entity_role": "employee_job",
                    "domain": "employment_earnings",
                    "groupby_dimension": "soc2020_group",
                    "shared_filters": filters,
                    "shared_constraints": constraints,
                    "rows": rows,
                    "measures": [
                        ashe_measure(edition, table, sheet, population, spec)
                        for spec in ASHE_COLUMNS
                        if spec[0] in signature
                    ],
                }
            )
    dimension_labels, value_labels = declarations(record_sets)
    status = f"{edition.year} {edition.status}"
    kind = "coefficients of variation for " if table.cv else ""
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": table.package_id(edition),
        "label": (
            f"ONS ASHE {table.number}: {kind}{table.title.lower()} by two-digit SOC 2020 "
            f"occupation, sex and working pattern, United Kingdom, {status}"
        ),
        "dimension_labels": dimension_labels,
        "dimension_value_labels": value_labels,
        "artifact": {
            "source_name": "ons",
            "source_table": (
                f"ASHE Table 2 (occupation by two-digit SOC), {table.number} "
                f"{'Coefficients of variation for ' if table.cv else ''}{table.title} (£), "
                f"United Kingdom, {status}"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{edition.directory}",
            "manifest": "manifest.yaml",
            "vintage": f"ashe_table2_{edition.slug}",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": f"ZIP member xlsx used-range cell parse ({member})",
            "parser": "zip_xlsx_used_range",
            "archive_member": member,
            "artifact_year": edition.year,
        },
        "record_sets": record_sets,
    }
    facts = sum(len(rs["rows"]) * len(rs["measures"]) for rs in record_sets)
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
        and unit percent. ONS colours
        the estimates by these CVs (5 per cent or less 'precise', over 5 to 10
        'reasonably precise', over 10 to 20 'acceptable') and suppresses those over 20;
        Chronicle reads no colours, so these facts carry the bands.
        """
        marks = (
            "A cell marked 'x' (CV over 20 per cent; the estimate is suppressed) or '.' "
            "('unavailable' in the CV key) emits no fact."
        )
    else:
        content = f"""
        The number of jobs (thousand; 'for indicative purposes only and should not be
        considered an accurate estimate of employee job counts', footnote b), the
        median, the mean and the 10th to 90th percentiles of {table.pay} pay, with
        statistic estimate; the annual percentage changes are not ported. ONS colours
        each estimate by its coefficient of variation; Chronicle reads no colours, and
        {other.number} ({other.package_id(edition)}) carries the CVs.
        """
        marks = (
            "A cell ONS suppresses ('x': 'Estimates with a CV greater than 20% are "
            "suppressed from publication on quality grounds') emits no fact."
        )
    correction = (
        edition.correction
        if (table.pay == "annual" or edition.slug == "2024_revised")
        else ""
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
        bulletin's rounding; tests/test_source_uk_occupation_facts.py checks it.
        """
    )
    header = f"""
    ONS Annual Survey of Hours and Earnings (ASHE) Table 2, occupation by two-digit SOC
    2020, {table.number} '{kind}{table.title} (£)', United Kingdom, {status} (released
    {edition.released}), for {ISSUE} ({CONSUMER}). Written by {SCRIPT} from the member
    '{member}' of the pinned zip.

    Every sheet but the notes is ported: all employee jobs, male, female, full-time,
    part-time, and the four sex by working-pattern sheets. Each sheet's 'All employees'
    row is its record sets' total, and its rows for the nine SOC 2020 major groups and
    26 sub-major groups carry soc2020_major_group or soc2020_sub_major_group (groupby
    soc2020_group). The detail rows hold both levels, so select one level by its filter
    and never sum across both. {content}

    {marks} A row with such a cell sits in a record set whose measures leave that
    column out ('without_p90' and the like), so the row's other cells are ported. The
    'Not Classified' row prints ':' ('not applicable') and emits no fact. {suppressed}
    marked cells are not ported; {facts} facts.

    ASHE counts employee jobs, not people: it 'is based on a 1% sample of jobs taken
    from HM Revenue and Customs' Pay As You Earn (PAYE) records', so 'individuals with
    more than one job may appear in the sample more than once', and it 'does not cover
    the self-employed, nor does it cover employees not paid during the reference
    period' (Notes sheet).

    {coverage["notes"]} {correction}
    {parity}
    """
    return render(header, payload)


# ---------------------------------------------------------------- the packages

BUILDERS = {
    **{
        period.directory: (lambda period=period: build_aps(period))
        for period in APS_PERIODS
    },
    **{
        table.directory(edition): (
            lambda edition=edition, table=table: build_ashe(edition, table)
        )
        for edition in ASHE_EDITIONS
        for table in ASHE_TABLES
    },
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
