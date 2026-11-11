"""Generate HMRC's Scottish income tax outturn package for PolicyEngine/chronicle#420.

Run from the repository root:

    uv run python scripts/build_uk_scottish_income_tax_package.py

``--check`` compares the generated YAML with the committed file instead of writing.
The package is written from its pinned workbook, read with Chronicle's own parser, so
every row number, column and guard cell below is one the package parser sees. The
publisher's text is asserted cell by cell, so a run against different bytes fails
rather than drifting. Nothing is downloaded and no value is computed.

- ``hmrc-scottish-income-tax-outturn-2024-25``: HMRC's Scottish Income Tax Outturn
  Statistics, 2024 to 2025 (published 9 July 2026), all four statistical tables: the
  non-savings non-dividend (NSND) Income Tax outturn by component (Table 1), by tax band
  and taxpayer marginal rate with the number of taxpayers (Table 2) and by collection
  method (Table 3), for Scottish, rest of UK, Welsh and all UK taxpayers from 2016 to
  2017, and the indicative in-year Income Tax from HMRC's RTI system by month (Table 4).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import textwrap
from pathlib import Path

import yaml

from chronicle.sources.cells import SourceArtifactMetadata, source_cells_from_ods
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-11-06"
ISSUE = "PolicyEngine/chronicle#420"
CONSUMER = "PolicyEngine/uk-scottish-budget-2027-28#7"
SCRIPT = "scripts/build_uk_scottish_income_tax_package.py"
DIRECTORY = "hmrc/scottish_income_tax_outturn_2024_25"
PACKAGE_ID = "hmrc-scottish-income-tax-outturn-2024-25"
PAGE = "https://www.gov.uk/government/statistics/scottish-income-tax-outturn-statistics-2024-to-2025"
RELEASE = PAGE + "/scottish-income-tax-outturn-statistics-2024-to-2025"
QUALITY_REPORT = PAGE + "/scottish-income-tax-background-quality-report"


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
    """The header's paragraphs, rewrapped as comment lines, then the package."""
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


def constraint(variable: str, value: object, label: str) -> Flow:
    return Flow(variable=variable, operator="==", value=value, label=label)


def guard(column: str, row: int, value: object, label: str) -> Flow:
    return Flow(column=column, row=row, expected_value=value, label=label)


def squeeze(text: object) -> str:
    return " ".join(str(text).replace("\xa0", " ").split())


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


NOT_APPLICABLE = "[Not Applicable]"

# Labels for every dimension and value the package uses. The package declares the ones
# its facts use; values another package also emits (marginal_rate's basic, higher and
# additional, worded as hmrc-income-tax-liabilities-july-2026 words them, and all, worded
# as hmrc-spi-income-bands-2023-24 words it) are listed in
# chronicle/dimension_values/canonical_labels.json.
DIMENSION_LABELS = {
    "geography": "Geography",
    "nsnd_outturn_component": "NSND Income Tax outturn component",
    "nsnd_collection_method": "NSND Income Tax collection method",
    "income_tax_band": "Income Tax band",
    "marginal_rate": "Marginal rate payable",
    "welsh_tax_devolution_basis": "Basis for Welsh tax devolution",
}
RATES = {
    "starter": "Starter rate",
    "basic": "Basic rate",
    "intermediate": "Intermediate rate",
    "higher": "Higher rate",
    "advanced": "Advanced rate",
    "top": "Top rate",
    "additional": "Additional rate",
    "additional_or_top": "Additional or top rate",
}
VALUE_LABELS = {
    "nsnd_outturn_component": {
        "sa_established_liability": "SA established liability",
        "paye_established_liability": "PAYE established liability",
        "estimated_further_liability": "Estimated further liability",
        "adjustment_for_uncollectable_amounts": "Adjustment for uncollectable amounts",
        "relief_at_source": "Relief at Source (RAS)",
        "gift_aid": "Gift Aid",
        "all": "Final NSND Income Tax revenue",
    },
    "nsnd_collection_method": {
        "collected_through_paye": "Collected through PAYE",
        "paid_through_self_assessment": "Paid through Self Assessment",
        "uncollected_ras_and_gift_aid_repayments": "Uncollected, RAS and Gift Aid repayments",
        "all": "Final NSND Income Tax revenue",
    },
    "income_tax_band": {**RATES, "all": "All bands"},
    "marginal_rate": {**RATES, "all": "All rates"},
    "welsh_tax_devolution_basis": {
        "pre_welsh_tax_devolution": "Pre-Welsh tax devolution",
        "post_welsh_tax_devolution": "Post-Welsh tax devolution",
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
        if record_set["groupby_dimension"] in VALUE_LABELS:
            used[record_set["groupby_dimension"]].update(
                str(row["value_id"]) for row in record_set["rows"]
            )
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


def category(variable: str, value: str) -> tuple[Flow, list[Flow]]:
    """A publisher category as a filter and, unless it is 'all', a constraint."""
    if value == "all":
        return Flow({variable: value}), []
    return Flow({variable: value}), [
        constraint(variable, value, DIMENSION_LABELS[variable])
    ]


# ---------------------------------------------------------------- taxpayer groups

SCOTLAND = {
    "geography_id": "S92000003",
    "geography_level": "country",
    "geography_name": "Scotland",
    "geography_vintage": "current",
}
WALES = {
    "geography_id": "W92000004",
    "geography_level": "country",
    "geography_name": "Wales",
    "geography_vintage": "current",
}
UNITED_KINGDOM = {
    "geography_id": "K02000001",
    "geography_level": "country",
    "geography_name": "United Kingdom",
    "geography_vintage": "current",
}
# The rest of the UK as hmrc-stamp-tax-statistics-2024-25 stores it: England, Wales and
# Northern Ireland while Welsh taxpayers are in it, England and Northern Ireland after.
REST_OF_UK_WITH_WALES = {
    "geography_id": "hmrc:england_wales_and_northern_ireland",
    "geography_level": "statistical_scope",
    "geography_name": "England, Wales and Northern Ireland",
    "geography_vintage": "current",
}
REST_OF_UK = {
    "geography_id": "hmrc:england_and_northern_ireland",
    "geography_level": "statistical_scope",
    "geography_name": "England and Northern Ireland",
    "geography_vintage": "current",
}
GROUP_LABEL = re.compile(
    r"^(Scottish|Rest of UK|Welsh|All UK|Scottish [Ss]hare of UK)"
    r"(?: \((Pre|Post)-Welsh tax devolution\))?(?: \[Note \d+\])?$"
)
BASES = {"Pre": "pre_welsh_tax_devolution", "Post": "post_welsh_tax_devolution"}
TAX_YEAR = re.compile(r"^(\d{4})-(\d{2})$")


def tax_year(text: str) -> int:
    match = TAX_YEAR.match(text)
    assert match and int(match.group(2)) == (int(match.group(1)) + 1) % 100, text
    return int(match.group(1))


def group_of(label: str, year: int) -> tuple[str, dict, str | None, bool]:
    """The printed taxpayer group as (slug, geography, Welsh devolution basis, share).

    Rest of UK figures 'for tax years prior to the 2020 to 2021 tax year include
    non-savings non-dividends income tax for Welsh taxpayers (except "Post-Welsh tax
    devolution" figures)' (each table's notes), so their geography follows the year
    and the basis; 2019-20 is printed on both bases, which the basis filter tells apart.
    """
    match = GROUP_LABEL.match(label)
    assert match, label
    name, basis_word = match.group(1), match.group(2)
    basis = BASES[basis_word] if basis_word else None
    assert basis is None or year == 2019, (label, year)
    if name == "Scottish":
        return "scottish", SCOTLAND, basis, False
    if name == "Welsh":
        assert year >= 2019, (label, year)
        return "welsh", WALES, basis, False
    if name == "All UK":
        return "all_uk", UNITED_KINGDOM, basis, False
    if name == "Rest of UK":
        with_wales = year < 2019 or basis == "pre_welsh_tax_devolution"
        return (
            "rest_of_uk",
            REST_OF_UK_WITH_WALES if with_wales else REST_OF_UK,
            basis,
            False,
        )
    return "scottish_share_of_uk", SCOTLAND, basis, True


def assert_bases(grid: dict, sheet: str, first: int) -> None:
    """Tables 1 to 3 print 2019-20 on both Welsh tax devolution bases for every group but
    the Scottish and Welsh ones, and every other year on one."""
    for row in data_rows(grid, sheet, first):
        label, year = grid[(sheet, row, "A")], tax_year(grid[(sheet, row, "B")])
        slug, _, basis, _ = group_of(label, year)
        two_bases = year == 2019 and slug not in ("scottish", "welsh")
        assert (basis is not None) == two_bases, (sheet, row, label)


def year_coverage(year: int, notes: str) -> dict:
    return {
        "start_date": f"{year}-04-06",
        "end_date": f"{year + 1}-04-05",
        "basis": "tax",
        "source_period_label": f"{year}-{(year + 1) % 100:02d}",
        "notes": notes,
    }


def population_words(slug: str, geography: dict) -> str:
    return {
        "scottish": "Scottish taxpayers",
        "welsh": "Welsh taxpayers",
        "all_uk": "all UK taxpayers",
        "rest_of_uk": f"rest of UK taxpayers ({geography['geography_name']})",
        "scottish_share_of_uk": "the Scottish share of the UK",
    }[slug]


def measure_spec(
    measure_id: str,
    label: str,
    ordinal: int,
    column: str,
    header_row: int,
    header: object,
    *,
    concept: str,
    unit: str,
    aggregation: str,
    notes: str,
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
        "concept_authority": "hmrc",
        "concept_evidence_url": RELEASE,
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


def record_set(
    record_set_id: str,
    sheet: str,
    period_type: str,
    period: object,
    coverage: dict,
    geography: dict,
    groupby: str,
    rows: list[dict],
    measures: list[dict],
    basis: str | None,
) -> dict:
    spec = {
        "record_set_id": record_set_id,
        "provenance_class": "administrative",
        "assertion": "observation",
        "record_set_spec_id": f"{record_set_id}.v1",
        "source_record_id_prefix": record_set_id,
        "sheet_name": sheet,
        "period_type": period_type,
        "period": period,
        "period_coverage": coverage,
        **geography,
        "entity": "person",
        "entity_role": "taxpayer",
        "domain": "income_tax",
        "groupby_dimension": groupby,
    }
    if basis is not None:
        filters, constraints = category("welsh_tax_devolution_basis", basis)
        spec["shared_filters"] = filters
        spec["shared_constraints"] = constraints
    spec["rows"] = rows
    spec["measures"] = [{**m, "ordinal": i} for i, m in enumerate(measures)]
    return spec


def geography_row(row: int, label: str, geography: dict, guards: list[Flow]) -> dict:
    return {
        "value_id": geography["geography_id"],
        "label": geography["geography_name"],
        "ordinal": 0,
        "row_number": row,
        "expected_row_header_column": "A",
        "expected_row_header": label,
        "table_record_kind": "detail",
        "guard_cells": guards,
    }


def data_rows(grid: dict, sheet: str, first: int) -> list[int]:
    """The table's data rows: from ``first`` to the row before 'End of worksheet'."""
    rows = sorted(r for (s, r, c) in grid if s == sheet and c == "A" and r >= first)
    end = next(r for r in rows if grid[(sheet, r, "A")] == "End of worksheet")
    assert rows == list(range(first, end + 1)), sheet
    return list(range(first, end))


# ---------------------------------------------------------------- Table 1

TABLE_1 = "Table_1"
TABLE_1_TITLE = "Table 1: Income Tax on non-savings non-dividend income"
TABLE_1_COLUMNS = (
    ("C", "SA Established liability [Note 1]", "sa_established_liability"),
    ("D", "PAYE Established liability [Note 2, 4]", "paye_established_liability"),
    ("E", "Estimated further liability [Note 3, 4]", "estimated_further_liability"),
    (
        "F",
        "Adjustment for uncollectable amounts [Note 5]",
        "adjustment_for_uncollectable_amounts",
    ),
    ("G", "Relief at Source (RAS) [Note 6, 7]", "relief_at_source"),
    ("H", "Gift Aid [Note 6, 8]", "gift_aid"),
    ("I", "Final NSND Income Tax revenue", "all"),
)
TABLE_1_NOTES = (
    "All amounts are measured in £million. Percentages have been rounded to the nearest "
    "0.1%.",
    "Figures may not sum to totals due to rounding. Scottish shares are based on "
    "unrounded figures.",
)


def build_table_1(grid: dict) -> tuple[list[dict], dict]:
    sheet = TABLE_1
    assert grid[(sheet, 1, "A")] == TABLE_1_TITLE
    assert_bases(grid, sheet, 9)
    for row, text in zip((3, 4), TABLE_1_NOTES):
        assert grid[(sheet, row, "A")] == text, row
    assert grid[(sheet, 8, "A")] == "Income Tax" and grid[(sheet, 8, "B")] == "Tax year"
    for column, header, _ in TABLE_1_COLUMNS:
        assert grid[(sheet, 8, column)] == header, column
    record_sets = []
    final = {}
    for row in data_rows(grid, sheet, 9):
        label, year = grid[(sheet, row, "A")], tax_year(grid[(sheet, row, "B")])
        slug, geography, basis, share = group_of(label, year)
        values = [grid[(sheet, row, column)] for column, _, _ in TABLE_1_COLUMNS]
        assert all(is_number(value) for value in values), (sheet, row)
        if share:
            assert all(0 < value < 1 for value in values), (sheet, row)
        else:
            # The six components add to the final revenue, each rounded to £1 million.
            assert abs(sum(values[:-1]) - values[-1]) <= 3.5, (sheet, row, values)
            final[(slug, geography["geography_id"], year, basis)] = values[-1]
        population = population_words(slug, geography)
        measures = []
        for column, header, component in TABLE_1_COLUMNS:
            filters, constraints = category("nsnd_outturn_component", component)
            component_words = VALUE_LABELS["nsnd_outturn_component"][component]
            measures.append(
                measure_spec(
                    f"{component}_share_of_uk" if share else component,
                    (
                        f"Scottish share of UK: {component_words}"
                        if share
                        else component_words
                    ),
                    0,
                    column,
                    8,
                    header,
                    concept=(
                        "hmrc.nsnd_income_tax_outturn_scottish_share_of_uk"
                        if share
                        else "hmrc.nsnd_income_tax_outturn"
                    ),
                    unit="share" if share else "gbp",
                    aggregation="share" if share else "sum",
                    notes=(
                        f"HMRC Scottish Income Tax Outturn Statistics 2024 to 2025, Table 1 "
                        f"'{TABLE_1_TITLE}', column {column} ('{header}'): "
                        + (
                            f"Scottish taxpayers' share of the UK's {component_words.lower()}, "
                            "a fraction, 'based on unrounded figures' and printed to the "
                            "nearest 0.1%."
                            if share
                            else f"{component_words.lower()} of NSND Income Tax for "
                            f"{population}, £ million."
                        )
                        + (
                            NOTE_4_COLUMN
                            if component
                            in (
                                "paye_established_liability",
                                "estimated_further_liability",
                            )
                            else ""
                        )
                    ),
                    filters=filters,
                    constraints=constraints,
                    scale=None if share else 1_000_000,
                )
            )
        basis_slug = f".{basis}" if basis else ""
        record_sets.append(
            record_set(
                f"hmrc.scottish_income_tax_2024_25.table1.{slug}{basis_slug}.ty{year}",
                sheet,
                "tax_year",
                year,
                year_coverage(
                    year,
                    f"{population.capitalize()}, tax year {year}-{(year + 1) % 100:02d}.",
                ),
                geography,
                "geography",
                [
                    geography_row(
                        row,
                        label,
                        geography,
                        [
                            guard("A", 1, TABLE_1_TITLE, "table title"),
                            guard("B", row, grid[(sheet, row, "B")], "tax year"),
                        ],
                    )
                ],
                measures,
                basis,
            )
        )
    shares = {}
    for row in data_rows(grid, sheet, 9):
        year = tax_year(grid[(sheet, row, "B")])
        _, _, basis, share = group_of(grid[(sheet, row, "A")], year)
        if share:
            shares[(year, basis)] = grid[(sheet, row, "I")]
    # The Scottish share of the UK is Scottish over Scottish, rest of UK and Welsh.
    for (year, basis), share in shares.items():
        scottish = final[("scottish", "S92000003", year, None)]
        (rest,) = [
            v
            for (s, _, y, b), v in final.items()
            if s == "rest_of_uk" and y == year and b == basis
        ]
        without_wales = year > 2019 or basis == "post_welsh_tax_devolution"
        welsh = final[("welsh", "W92000004", year, None)] if without_wales else 0
        assert abs(scottish / (scottish + rest + welsh) - share) <= 0.0006, (
            year,
            basis,
        )
    return record_sets, final


# ---------------------------------------------------------------- Table 2

TABLE_2 = "Table_2"
TABLE_2_TITLE = (
    "Table 2: Income Tax on non-saving non-dividend income by tax rate and taxpayer "
    "marginal rate"
)
TABLE_2_NOTES = {
    3: "All amounts are measured in £million. All taxpayer numbers are rounded to "
    "nearest hundred.",
    4: "Figures may not sum to totals due to rounding.",
    5: "This table only covers individuals with some liability to tax on their "
    "non-savings non-dividend income.",
    7: "Taxpayers have been classified as a Starter/Basic/Intermediate/Higher/Top (or "
    "just Basic/Higher/Additional for rUK) rate taxpayer based on their non-savings "
    "non-dividends tax liabilities only.",
}
TABLE_2_HEADERS = {
    "A": "Taxpayer",
    "B": "Tax year",
    "C": "Tax band",
    "D": "Number of taxpayers",
}
# The liability columns: column, header, the taxpayer type it holds (J by group).
TABLE_2_LIABILITY_COLUMNS = (
    ("E", "Starter rate taxpayers", "starter"),
    ("F", "Basic rate taxpayers", "basic"),
    ("G", "Intermediate rate taxpayers", "intermediate"),
    ("H", "Higher rate taxpayers", "higher"),
    ("I", "Advanced rate taxpayers", "advanced"),
    ("J", "Additional/Top rate taxpayers", None),
    ("K", "All taxpayers", "all"),
)
BAND_TEXT = {
    "Starter Rate": "starter",
    "Basic Rate": "basic",
    "Intermediate Rate": "intermediate",
    "Higher Rate": "higher",
    "Advanced Rate": "advanced",
    "Top Rate": "top",
    "Additional Rate": "additional",
    "Additional/Top Rate": "additional_or_top",
    "All Bands": "all",
}


# One publisher error, ported as published: the UK's 2024-25 'All Bands' row prints all
# taxpayers' NSND Income Tax (cell K157) as the bands' total without the Starter band,
# 1,254.7 (£ million) below its own taxpayer types and its own bands, which both add to
# 276,611.8 (Scottish, rest of UK and Welsh revenue). The generator pins the gap.
UK_2024_ALL_BANDS_GAP_IS_THE_STARTER_BAND = ("all_uk", 2024, None)


def top_rate(slug: str, year: int) -> str:
    """Column J's taxpayers, and the band 'Additional Rate' names, for the group.

    Scotland's additional rate became its top rate in 2018-19; the rest of the UK keeps
    the additional rate; the UK rows combine both from 2018-19, and print 'Additional
    Rate' for them on the pre-Welsh tax devolution basis of 2019-20, where Scotland's
    15,500 top rate taxpayers and the rest of the UK's 351,200 make its 366,700.
    """
    if slug == "scottish":
        return "top" if year >= 2018 else "additional"
    if slug == "all_uk":
        return "additional_or_top" if year >= 2018 else "additional"
    return "additional"


def band_of(text: str, slug: str, year: int) -> str:
    band = BAND_TEXT[text]
    if band in ("additional", "additional_or_top", "top"):
        assert band == top_rate(slug, year) or (
            slug == "all_uk" and band == "additional"
        ), (text, slug, year)
        return top_rate(slug, year)
    return band


def build_table_2(grid: dict, final: dict) -> list[dict]:
    sheet = TABLE_2
    assert grid[(sheet, 1, "A")] == TABLE_2_TITLE
    for row, text in TABLE_2_NOTES.items():
        assert grid[(sheet, row, "A")] == text, row
    for column, text in TABLE_2_HEADERS.items():
        assert grid[(sheet, 9, column)] == text, column
    for column, text, _ in TABLE_2_LIABILITY_COLUMNS:
        assert grid[(sheet, 9, column)] == text, column
    assert_bases(grid, sheet, 10)
    blocks: dict[tuple, list[int]] = {}
    for row in data_rows(grid, sheet, 10):
        key = (grid[(sheet, row, "A")], grid[(sheet, row, "B")])
        blocks.setdefault(key, []).append(row)
    record_sets = []
    for (label, year_text), rows in blocks.items():
        year = tax_year(year_text)
        slug, geography, basis, share = group_of(label, year)
        assert not share and slug in ("scottish", "rest_of_uk", "all_uk"), label
        assert grid[(sheet, rows[-1], "C")] == "All Bands", (label, year)
        bands = [band_of(grid[(sheet, row, "C")], slug, year) for row in rows]
        population = population_words(slug, geography)
        basis_slug = f".{basis}" if basis else ""
        prefix = f"hmrc.scottish_income_tax_2024_25.table2.{slug}{basis_slug}.ty{year}"
        coverage = year_coverage(
            year,
            f"{population.capitalize()} with some liability to tax on their NSND income, "
            f"tax year {year}-{(year + 1) % 100:02d}.",
        )
        title_guard = guard("A", 1, TABLE_2_TITLE, "table title")
        # Taxpayers: the row's band is the taxpayers' marginal rate.
        counts = []
        taxpayer_rows = []
        for ordinal, (row, band) in enumerate(zip(rows, bands)):
            value = grid[(sheet, row, "D")]
            assert is_number(value) and value % 100 == 0, (sheet, row, value)
            counts.append(value)
            spec = {
                "value_id": band,
                "label": VALUE_LABELS["marginal_rate"][band],
                "ordinal": ordinal,
                "row_number": row,
                "expected_row_header_column": "C",
                "expected_row_header": grid[(sheet, row, "C")],
                "table_record_kind": "total" if band == "all" else "detail",
                "guard_cells": [
                    guard("A", row, label, "taxpayer group"),
                    guard("B", row, year_text, "tax year"),
                ],
            }
            if band != "all":
                spec["filters"], spec["constraints"] = category("marginal_rate", band)
            taxpayer_rows.append(spec)
        taxpayer_rows[0]["guard_cells"].insert(0, title_guard)
        # Rounded to the nearest hundred, so the parts add within fifty a figure.
        assert abs(sum(counts[:-1]) - counts[-1]) <= 50 * len(counts), (label, year)
        record_sets.append(
            record_set(
                f"{prefix}.taxpayers",
                sheet,
                "tax_year",
                year,
                coverage,
                geography,
                "marginal_rate",
                taxpayer_rows,
                [
                    measure_spec(
                        "taxpayers",
                        "Number of taxpayers",
                        0,
                        "D",
                        9,
                        "Number of taxpayers",
                        concept="hmrc.nsnd_income_taxpayers",
                        unit="count",
                        aggregation="sum",
                        notes=(
                            f"HMRC Scottish Income Tax Outturn Statistics 2024 to 2025, Table "
                            f"2, column D ('Number of taxpayers'): {population} by highest "
                            "marginal rate on their NSND income ('the Income Tax band that a "
                            "taxpayer would pay their next pound of Income Tax into'), on "
                            "the row's band, rounded to the nearest hundred."
                        ),
                    )
                ],
                basis,
            )
        )
        # Liabilities: the row's band is the tax band, the column the taxpayers' marginal rate.
        grid_values = {}
        for row, band in zip(rows, bands):
            measures = []
            for column, header, rate in TABLE_2_LIABILITY_COLUMNS:
                value = grid[(sheet, row, column)]
                if value == NOT_APPLICABLE:
                    continue
                assert is_number(value), (sheet, row, column, value)
                rate = rate or top_rate(slug, year)
                grid_values[(band, rate)] = value
                filters, constraints = category("marginal_rate", rate)
                rate_words = VALUE_LABELS["marginal_rate"][rate].lower()
                band_words = VALUE_LABELS["income_tax_band"][band].lower()
                measures.append(
                    measure_spec(
                        f"liability_{rate}",
                        f"NSND Income Tax, {band_words}, {rate_words}"
                        + ("" if rate == "all" else " taxpayers"),
                        0,
                        column,
                        9,
                        header,
                        concept="hmrc.nsnd_income_tax_by_band",
                        unit="gbp",
                        aggregation="sum",
                        notes=(
                            f"HMRC Scottish Income Tax Outturn Statistics 2024 to 2025, Table "
                            f"2, column {column} ('{header}'): NSND Income Tax in the row's "
                            f"tax band paid by {population} whose highest marginal rate is "
                            f"the column's, £ million."
                        ),
                        filters=filters,
                        constraints=constraints,
                        scale=1_000_000,
                    )
                )
            spec = {
                "value_id": band,
                "label": VALUE_LABELS["income_tax_band"][band],
                "ordinal": 0,
                "row_number": row,
                "expected_row_header_column": "C",
                "expected_row_header": grid[(sheet, row, "C")],
                "table_record_kind": "total" if band == "all" else "detail",
                "guard_cells": [
                    title_guard,
                    guard("A", row, label, "taxpayer group"),
                    guard("B", row, year_text, "tax year"),
                ],
            }
            if band != "all":
                spec["filters"], spec["constraints"] = category("income_tax_band", band)
            record_sets.append(
                record_set(
                    f"{prefix}.liability.{band}",
                    sheet,
                    "tax_year",
                    year,
                    coverage,
                    geography,
                    "income_tax_band",
                    [spec],
                    measures,
                    basis,
                )
            )
        # Each row's taxpayer types add to all taxpayers; each type's bands add to all
        # bands, within the cells' rounding (to £1 million where printed rounded).
        rates = {rate for _, rate in grid_values}
        misprinted = (slug, year, basis) == UK_2024_ALL_BANDS_GAP_IS_THE_STARTER_BAND
        for band in bands:
            parts = [v for (b, r), v in grid_values.items() if b == band and r != "all"]
            gap = sum(parts) - grid_values[(band, "all")]
            if misprinted and band == "all":
                assert abs(gap - grid_values[("starter", "all")]) < 1e-6, gap
                continue
            assert abs(gap) <= 0.5 * (len(parts) + 1), (label, year, band, gap)
        for rate in rates:
            parts = [v for (b, r), v in grid_values.items() if r == rate and b != "all"]
            gap = sum(parts) - grid_values[("all", rate)]
            if misprinted and rate == "all":
                assert abs(gap - grid_values[("starter", "all")]) < 1e-6, gap
                continue
            assert abs(gap) <= 0.5 * (len(parts) + 1), (label, year, rate, gap)
        # All bands and all taxpayers is Table 1's final revenue, to Table 1's rounding.
        if slug != "all_uk":
            total = final[(slug, geography["geography_id"], year, basis)]
            assert abs(grid_values[("all", "all")] - total) <= 0.5, (label, year)
    return record_sets


# ---------------------------------------------------------------- Table 3

TABLE_3 = "Table_3"
TABLE_3_TITLE = (
    "Table 3: Established Scottish and Rest of UK Income Tax on non-saving non-dividend "
    "income by collection method"
)
TABLE_3_AMOUNTS = (
    ("C", "Collected through PAYE [Note 11, 13, 14]", "collected_through_paye"),
    ("D", "Paid through Self Assessment [Note 12, 13]", "paid_through_self_assessment"),
    (
        "E",
        "Uncollected, RAS and Gift Aid repayments",
        "uncollected_ras_and_gift_aid_repayments",
    ),
    ("F", "Final NSND Income Tax revenue", "all"),
)
TABLE_3_SHARES = (
    ("G", "Collected through PAYE [Note 15]", "collected_through_paye"),
    ("H", "Paid through Self Assessment [Note 15]", "paid_through_self_assessment"),
)


def build_table_3(grid: dict, final: dict) -> list[dict]:
    sheet = TABLE_3
    assert grid[(sheet, 1, "A")] == TABLE_3_TITLE
    assert grid[(sheet, 3, "A")] == (
        "All amounts are measured in £million. Percentages have been rounded to nearest "
        "0.1%. Scottish shares are based on unrounded figures."
    )
    for column, header, _ in TABLE_3_AMOUNTS + TABLE_3_SHARES:
        assert grid[(sheet, 8, column)] == header, column
    assert_bases(grid, sheet, 9)
    record_sets = []
    for row in data_rows(grid, sheet, 9):
        label, year = grid[(sheet, row, "A")], tax_year(grid[(sheet, row, "B")])
        slug, geography, basis, share = group_of(label, year)
        population = population_words(slug, geography)
        measures = []
        amounts = [grid[(sheet, row, column)] for column, _, _ in TABLE_3_AMOUNTS]
        assert all(is_number(value) for value in amounts), (sheet, row)
        for column, header, method in TABLE_3_AMOUNTS:
            filters, constraints = category("nsnd_collection_method", method)
            words = VALUE_LABELS["nsnd_collection_method"][method]
            measures.append(
                measure_spec(
                    f"{method}_share_of_uk" if share else method,
                    f"Scottish share of UK: {words}" if share else words,
                    0,
                    column,
                    8,
                    header,
                    concept=(
                        "hmrc.nsnd_income_tax_by_collection_method_scottish_share_of_uk"
                        if share
                        else "hmrc.nsnd_income_tax_by_collection_method"
                    ),
                    unit="share" if share else "gbp",
                    aggregation="share" if share else "sum",
                    notes=(
                        f"HMRC Scottish Income Tax Outturn Statistics 2024 to 2025, Table 3, "
                        f"column {column} ('{header}'): "
                        + (
                            f"Scottish taxpayers' share of the UK's NSND Income Tax "
                            f"{words.lower()}, a fraction printed to the nearest 0.1%."
                            if share
                            else f"NSND Income Tax of {population}, {words.lower()}, "
                            "£ million: 'an estimate for how much of the non-savings "
                            "non-dividend outturn established liability was collected "
                            "through PAYE or paid through Self Assessment' (table notes)."
                        )
                        + (NOTE_14_COLUMN if method == "collected_through_paye" else "")
                    ),
                    filters=filters,
                    constraints=constraints,
                    scale=None if share else 1_000_000,
                )
            )
        if share:
            for column, _, _ in TABLE_3_SHARES:
                assert grid[(sheet, row, column)] == NOT_APPLICABLE, (
                    sheet,
                    row,
                    column,
                )
        else:
            # PAYE, Self Assessment and the repayments add to the final revenue, which is
            # Table 1's.
            assert abs(sum(amounts[:-1]) - amounts[-1]) <= 2, (sheet, row)
            assert amounts[-1] == final[(slug, geography["geography_id"], year, basis)]
            shares = [grid[(sheet, row, column)] for column, _, _ in TABLE_3_SHARES]
            assert abs(sum(shares) - 1) <= 0.0015, (sheet, row)
            assert abs(amounts[0] / (amounts[0] + amounts[1]) - shares[0]) <= 0.0006
            for column, header, method in TABLE_3_SHARES:
                filters, constraints = category("nsnd_collection_method", method)
                words = VALUE_LABELS["nsnd_collection_method"][method]
                measures.append(
                    measure_spec(
                        f"{method}_share",
                        f"Share {words[0].lower()}{words[1:]}",
                        0,
                        column,
                        8,
                        header,
                        concept="hmrc.nsnd_income_tax_collection_method_share",
                        unit="share",
                        aggregation="share",
                        notes=(
                            f"HMRC Scottish Income Tax Outturn Statistics 2024 to 2025, "
                            f"Table 3, column {column} ('{header}'): the share of "
                            f"{population}' NSND Income Tax {words.lower()}, a fraction "
                            "printed to the nearest 0.1%: 'The percentages for what is "
                            "collected via PAYE and SA is based on the PAYE and SA "
                            "liabilities and excludes the Outturn components for "
                            "Uncollected, RAS and Gift Aid repayments' (Note 15)."
                        ),
                        filters=filters,
                        constraints=constraints,
                    )
                )
        basis_slug = f".{basis}" if basis else ""
        record_sets.append(
            record_set(
                f"hmrc.scottish_income_tax_2024_25.table3.{slug}{basis_slug}.ty{year}",
                sheet,
                "tax_year",
                year,
                year_coverage(
                    year,
                    f"{population.capitalize()}, tax year {year}-{(year + 1) % 100:02d}.",
                ),
                geography,
                "geography",
                [
                    geography_row(
                        row,
                        label,
                        geography,
                        [
                            guard("A", 1, TABLE_3_TITLE, "table title"),
                            guard("B", row, grid[(sheet, row, "B")], "tax year"),
                        ],
                    )
                ],
                measures,
                basis,
            )
        )
    return record_sets


# ---------------------------------------------------------------- Table 4

TABLE_4 = "Table_4"
TABLE_4_TITLE = "Table 4: Indicative In-Year Income Tax taken from HMRC’s Real Time Information system"
MONTHS = (
    ("C", "April", 4),
    ("D", "May", 5),
    ("E", "June", 6),
    ("F", "July", 7),
    ("G", "August", 8),
    ("H", "September", 9),
    ("I", "October", 10),
    ("J", "November", 11),
    ("K", "December", 12),
    ("L", "January", 1),
    ("M", "February", 2),
    ("N", "March", 3),
)
TABLE_4_NOTES = {
    4: "The sum of these figures will not equate to the final Scottish Income Tax outturn "
    "calculation and are only intended to be an indication of part of Scottish Income Tax "
    "(from employments and pensions covered by PAYE).",
    5: "RTI data does not include payments made via Self-Assessment but shows all amounts "
    "collected through PAYE for anything coded out and will include savings, non-Income "
    "Tax charges (eg. HICBC) and reflects overpayments.",
    6: "RTI data in-year is subject to revision and update throughout the year. Any "
    "end-of-year updates that occur are not included.",
}


def build_table_4(grid: dict) -> list[dict]:
    sheet = TABLE_4
    assert grid[(sheet, 1, "A")] == TABLE_4_TITLE
    for row, text in TABLE_4_NOTES.items():
        assert grid[(sheet, row, "A")] == text, row
    for column, name, _ in MONTHS:
        assert grid[(sheet, 9, column)] == name, column
    assert grid[(sheet, 9, "O")] == "Annual Total"
    record_sets = []
    totals: dict[tuple, dict] = {}
    for row in data_rows(grid, sheet, 10):
        label, year = grid[(sheet, row, "A")], tax_year(grid[(sheet, row, "B")])
        slug, geography, basis, share = group_of(label, year)
        assert basis is None, label
        values = {column: grid[(sheet, row, column)] for column, _, _ in MONTHS}
        values["O"] = grid[(sheet, row, "O")]
        assert all(is_number(v) for v in values.values()), (sheet, row)
        if not share:
            # The months add to the annual total, each rounded to £1 million.
            assert abs(sum(values[c] for c, _, _ in MONTHS) - values["O"]) <= 6.5
        totals[(slug, year)] = values
        population = population_words(slug, geography)
        concept = (
            "hmrc.rti_income_tax_withheld_scottish_share_of_uk"
            if share
            else "hmrc.rti_income_tax_withheld"
        )
        what = (
            "Scottish taxpayers' share of the UK's indicative in-year Income Tax reported "
            "as withheld in RTI, a fraction printed to the nearest 0.01%"
            if share
            else f"indicative in-year Income Tax reported as withheld in RTI for "
            f"{population}, £ million"
        )
        for column, name, month in MONTHS + (("O", "Annual Total", None),):
            calendar_year = year if month is None or month >= 4 else year + 1
            if month is None:
                period_type, period = "tax_year", year
                coverage = year_coverage(
                    year,
                    "The annual total of HMRC's monthly RTI series for the tax year; 'RTI "
                    "data in-year is subject to revision and update throughout the year. "
                    "Any end-of-year updates that occur are not included.'",
                )
            else:
                period_type, period = "month", f"{calendar_year}-{month:02d}"
                coverage = {
                    "basis": "tax",
                    "source_period_label": f"{name} {year}-{(year + 1) % 100:02d}",
                    "notes": (
                        f"Month '{name}' of tax year {year}-{(year + 1) % 100:02d} in HMRC's "
                        "monthly RTI series; the release does not say whether a month is "
                        "the calendar month or the tax month from the 6th, so no dates are "
                        "stored. 'RTI data in-year is subject to revision and update "
                        "throughout the year.'"
                    ),
                }
            measure_id = "annual_total" if month is None else name.lower()
            record_sets.append(
                record_set(
                    f"hmrc.scottish_income_tax_2024_25.table4.{slug}.ty{year}.{measure_id}",
                    sheet,
                    period_type,
                    period,
                    coverage,
                    geography,
                    "geography",
                    [
                        geography_row(
                            row,
                            label,
                            geography,
                            [
                                guard("A", 1, TABLE_4_TITLE, "table title"),
                                guard("B", row, grid[(sheet, row, "B")], "tax year"),
                            ],
                        )
                    ],
                    [
                        measure_spec(
                            measure_id,
                            f"{'Scottish share of UK: ' if share else ''}Income Tax "
                            f"withheld in RTI, {name}",
                            0,
                            column,
                            9,
                            name,
                            concept=concept,
                            unit="share" if share else "gbp",
                            aggregation="share" if share else "sum",
                            notes=(
                                f"HMRC Scottish Income Tax Outturn Statistics 2024 to 2025, "
                                f"Table 4, column {column} ('{name}'): {what}. 'RTI data does "
                                "not include payments made via Self-Assessment but shows all "
                                "amounts collected through PAYE for anything coded out and "
                                "will include savings, non-Income Tax charges (eg. HICBC) "
                                "and reflects overpayments' (table notes), so it is not NSND "
                                "Income Tax."
                            ),
                            scale=None if share else 1_000_000,
                        )
                    ],
                    None,
                )
            )
    # The Scottish share is Scottish over all UK, 'based on unrounded figures'.
    for (slug, year), values in totals.items():
        if slug != "scottish_share_of_uk":
            continue
        for column, value in values.items():
            computed = (
                totals[("scottish", year)][column] / totals[("all_uk", year)][column]
            )
            assert abs(computed - value) <= 0.0003, (year, column, computed, value)
    return record_sets


# ---------------------------------------------------------------- the package

COVER_QUOTES = (
    "The data tables in this spreadsheet were originally published at 9:30am 9th July 2026",
    "All figures in these table relate to Income Tax devolved to Scotland based on "
    "Scotland Act 2016 - all tax due on non-savings non-dividends (NSND) Income.",
)
NOTE_4 = (
    "The estimated further liability includes an increase in the number of unreconciled "
    "PAYE cases. These unreconciled PAYE cases account for around £37m of the Scottish "
    "estimated further liability and £4,242m of the non-Scottish estimated further "
    "liability. For 2018/19, these cases account for £36m and £398m of the Scottish and "
    "non-Scottish estimated further liability respectively. For 2019/20, these cases "
    "account for £9m and £87m of the Scottish and non-Scottish estimated further liability "
    "respectively. For 2020/21, these cases account for £10m and £87m of the Scottish and "
    "non-Scottish estimated further liability respectively. For 2021/22, these cases account "
    "for less than £1m and £2m of the Scottish and non-Scottish estimated further liability "
    "respectively. For 2022/23, these cases account for less than £1m and £2m of the "
    "Scottish and non-Scottish estimated further liability respectively. For 2023/24, these "
    "cases account for £2m and £291m of the Scottish and non-Scottish estimated further "
    "liability respectively. For 2024/25, these cases account for £37m and £4,272m of the "
    "Scottish and non-Scottish estimated further liability respectively. For a more "
    "consistent comparison between all years these amounts should be deducted from "
    '"estimated further liability" and added to "PAYE established liability".'
)
NOTE_14 = (
    "The parts of the further estimated liabiltiy component relating to unreconciled PAYE "
    'cases have been fully assigned "collected through PAYE".'
)
# What Table 1's PAYE established and estimated further liability columns add to their
# notes (both cite Note 4), and Table 3's PAYE column (it cites Note 14).
NOTE_4_COLUMN = (
    " Note 4: unreconciled PAYE cases sit in the estimated further liability (2024-25: "
    "£37m Scottish and £4,272m non-Scottish; 2023-24: £2m and £291m), and 'For a more "
    "consistent comparison between all years these amounts should be deducted from "
    '"estimated further liability" and added to "PAYE established liability"\'.'
)
NOTE_14_COLUMN = (
    " Note 14: 'The parts of the further estimated liabiltiy component relating to "
    'unreconciled PAYE cases have been fully assigned "collected through PAYE".\''
)
NOTE_9 = (
    "Scottish/Welsh taxpayers are identified using the Scottish/Welsh taxpayer indicator in "
    "the NPS (National Insurance and PAYE Service) system which identifies an individual "
    "being taxed under the Scottish/Welsh tax system."
)


def build_package() -> str:
    entry, content = pinned(DIRECTORY)
    grid = grid_of(
        source_cells_from_ods(
            content, metadata(entry["filename"]), coerce_numeric_text=True
        )
    )
    cover = squeeze(
        " ".join(str(v) for (s, _, _), v in grid.items() if s == "Cover_Sheet")
    )
    for quote in COVER_QUOTES:
        assert squeeze(quote) in cover, quote
    assert grid[("Notes", 11, "A")] == 9 and grid[("Notes", 11, "B")] == NOTE_9
    assert grid[("Notes", 6, "A")] == 4 and grid[("Notes", 6, "B")] == NOTE_4
    assert grid[("Notes", 16, "A")] == 14 and grid[("Notes", 16, "B")] == NOTE_14
    table_1, final = build_table_1(grid)
    table_2 = build_table_2(grid, final)
    table_3 = build_table_3(grid, final)
    table_4 = build_table_4(grid)
    record_sets = table_1 + table_2 + table_3 + table_4
    dimension_labels, value_labels = declarations(record_sets)
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": (
            "HMRC Scottish Income Tax Outturn Statistics, 2024 to 2025: NSND Income Tax by "
            "component, tax band and marginal rate, and collection method, Scottish, rest of "
            "UK, Welsh and UK taxpayers, 2016-17 to 2024-25, and indicative in-year RTI "
            "Income Tax to 2025-26"
        ),
        "dimension_labels": dimension_labels,
        "dimension_value_labels": value_labels,
        "artifact": {
            "source_name": "hmrc",
            "source_table": (
                "Scottish Income Tax Outturn Statistics: 2024 to 2025, statistical tables 1 to 4"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "scottish_income_tax_outturn_2026_07_09",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": (
                f"ODS used-range cell parse with numeric text read as numbers ({entry['filename']})"
            ),
            "parser": "ods_numeric_text_used_range",
            "artifact_year": 2026,
        },
        "record_sets": record_sets,
    }
    counts = {
        name: sum(len(rs["rows"]) * len(rs["measures"]) for rs in sets)
        for name, sets in (
            ("1", table_1),
            ("2", table_2),
            ("3", table_3),
            ("4", table_4),
        )
    }
    scottish = final[("scottish", "S92000003", 2024, None)]
    header = f"""
    HMRC 'Scottish Income Tax Outturn Statistics: 2024 to 2025' (published 9 July 2026;
    {PAGE}), its statistical tables, for {ISSUE} item 8 ({CONSUMER}): a Microcosm
    diagnostic of Scottish non-savings non-dividend (NSND) Income Tax and its band
    shares. Written by {SCRIPT} from the pinned workbook. The asset's Last-Modified header
    reads 2 September 2026; the publication page records no update, and the workbook
    says its tables 'were originally published at 9:30am 9th July 2026'.

    All four tables are ported, every cell HMRC prints as a number. Table 1 (Income Tax
    on NSND income): the SA and PAYE established liabilities, the estimated further
    liability, the adjustment for uncollectable amounts, Relief at Source, Gift Aid and the
    final NSND Income Tax revenue, concept hmrc.nsnd_income_tax_outturn ({counts["1"]}
    facts). Table 2 (by tax rate and taxpayer marginal rate): the number of taxpayers by
    their highest marginal rate, hmrc.nsnd_income_taxpayers, and the NSND Income Tax in each
    tax band paid by each type of taxpayer, hmrc.nsnd_income_tax_by_band ({counts["2"]}).
    Table 3 (by collection method): collected through PAYE, paid through Self Assessment,
    uncollected, RAS and Gift Aid repayments and the final revenue, with the PAYE and SA
    shares ({counts["3"]}). Table 4: the indicative in-year Income Tax reported as
    withheld in RTI by month, 2016-17 to 2025-26, hmrc.rti_income_tax_withheld
    ({counts["4"]}), which is not NSND Income Tax: it 'will include savings, non-Income Tax
    charges (eg. HICBC) and reflects overpayments'. Each table's 'Scottish share of UK'
    rows are their own concepts (_scottish_share_of_uk), as fractions. Amounts are £
    million as printed; Table 2's taxpayer numbers are 'rounded to nearest hundred'; the
    rest of UK and UK rows of Table 2, and its Scottish 2023-24 all-bands row, print
    unrounded figures, ported as printed. Cells marked '[Not Applicable]' emit no fact.

    Each table's three totals are separate concepts and are not reconciled by Chronicle:
    Table 2's all-bands, all-taxpayers cell and Table 3's final revenue equal Table 1's
    final revenue (to Table 1's £1 million rounding), which the generator asserts.

    One publisher error, ported as published: the UK's 2024-25 'All Bands' row prints all
    taxpayers' NSND Income Tax as £275,357.1 million, the bands' total without the Starter
    band (£1,254.7 million). Its own taxpayer types, and the bands above it, add to
    £276,611.8 million, which is the Scottish, rest of UK and Welsh revenue together. The
    generator pins the gap, so a corrected edition fails the build rather than passing
    silently.

    Scottish taxpayers: 'The definition of a Scottish taxpayer is based on where an
    individual resides in the course of a tax year. Scottish taxpayer status applies for a
    whole tax year' and 'The location of a person's employer is not relevant' (release,
    section 6.2); 'Scottish/Welsh taxpayers are identified using the Scottish/Welsh
    taxpayer indicator in the NPS (National Insurance and PAYE Service) system' (Note 9).
    The facts sit at S92000003 for Scottish taxpayers and W92000004 for Welsh, which is
    taxpayer status, not address. The rest of the UK is hmrc:england_wales_and_northern_ireland
    to 2018-19 and on the 2019-20 'Pre-Welsh tax devolution' basis, and
    hmrc:england_and_northern_ireland on the 'Post-Welsh tax devolution' basis and from
    2020-21 ('All rUK figures in this bulletin include England and Northern Ireland outturn
    only'); 2019-20's two bases carry welsh_tax_devolution_basis (Note 10), and so do
    the UK and Scottish share rows printed for each.

    Marginal rates: 'Taxpayers have been classified as a Starter/Basic/Intermediate/Higher/
    Top (or just Basic/Higher/Additional for rUK) rate taxpayer based on their non-savings
    non-dividends tax liabilities only' (Table 2). Column J, 'Additional/Top rate
    taxpayers', is marginal_rate top for Scottish taxpayers from 2018-19 (additional before),
    additional for the rest of the UK, and additional_or_top for the UK from 2018-19, which
    combines both; the UK's 2019-20 pre-Welsh tax devolution row prints its band as
    'Additional Rate' and is additional_or_top too (Scotland's 15,500 top rate taxpayers
    and the rest of the UK's 351,200 make its 366,700). marginal_rate's basic, higher and
    additional are hmrc-income-tax-liabilities-july-2026's values and labels, and its all
    is hmrc-spi-income-bands-2023-24's ('All rates'); the rates here are NSND rates.

    Outturn: 'Over 95% of the final outturn figure comes from established Income Tax
    liabilities, the remaining amount is estimated to account for liabilities which may be
    established in the future' (background quality report, {QUALITY_REPORT}), so the
    estimated further liability is under 5%. HMRC revised earlier years in the 2020 to 2021
    and 2022 to 2023 releases (quality report, section 6.3); these facts are this edition's.

    Unreconciled PAYE cases move liability between two of Table 1's components, as Note 4
    says (both columns cite it, and their facts' notes carry it): '{NOTE_4}' The note's
    first sentence and its 2024/25 sentence give the non-Scottish amount as £4,242m and
    £4,272m; both are quoted as printed. So the rest of the UK's estimated further
    liability rising from 2023-24 to 2024-25, and the Scottish share of it falling, is
    mostly that effect; the facts are as published, and a consumer comparing years moves
    the note's amounts itself. Table 3's 'Collected through PAYE' cites Note 14: '{NOTE_14}'

    Parity, asserted by the generator: Table 1's six components add to the final revenue
    within rounding, and the Scottish share is Scottish over Scottish, rest of UK and Welsh
    revenue (the UK); Table 2's bands add to all bands and its taxpayer types to all
    taxpayers, and its taxpayer numbers to the total within the hundreds' rounding; Table
    3's methods add to the final revenue and its PAYE and SA shares to one; Table 4's
    months add to the annual total and its share is Scottish over UK. The release's 2024
    to 2025 headlines are the cells: £{scottish:,} million of NSND Income Tax ('£18.6
    billion') from 3,036,400 Scottish taxpayers, and the rest of the UK's 32,533,800
    taxpayers and £250,212 million ('£250.2 billion'). {sum(counts.values())} facts.
    """
    return render(header, payload)


BUILDERS = {DIRECTORY: build_package}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the generated YAML with the committed file instead of writing.",
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
