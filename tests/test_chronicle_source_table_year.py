"""A fact's period is the tax year its source table says it is for.

IRS SOI titles each table with the tax year it covers ("..., Tax Year 2020"),
and a package states that title as ``artifact.source_table``. The artifact-year
restamp guard (``test_chronicle_artifact_year_restamp.py``) refuses a pinned
package whose labels follow ``--year``. It compares one build with another, so
it cannot see a package whose labels are simply the wrong year. These tests
compare the labels with what the publisher printed.

Invariant under test: when a package's source table title names exactly one
tax year, every fact the package builds at its artifact year has that year as
its period, in its ``tax_year_<year>`` vintage and in its record ids.

Origin: until PolicyEngine/chronicle#292, ``soi-w2-statistics-2020`` rendered
its labels from ``--year``, and the microcosm US feed built it at ``--year
2023``. Five cells of IRS SOI Table 4.B for Tax Year 2020 went out as ty2023
facts, and microcosm aged the Box 7 tips total one year to 2024 where it needed
four.
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

import openpyxl
import pytest
import yaml

from chronicle.source_package import (
    SOURCE_PACKAGE_FILENAME,
    artifact_year_restamp_issues,
    discover_source_package_dirs,
    load_source_package,
)
from chronicle.store import fact_to_mapping

REPO_ROOT = Path(__file__).resolve().parents[1]

_YEAR = r"(?<!\d)(?:19|20)\d{2}(?!\d)"
# The year or years that follow "Tax Year(s)" in a table title. A trailing
# "-21" or "/21" abbreviates a second year the span cannot read, so a title
# like "tax year 2023-24" matches nothing.
_TAX_YEAR_SPAN = re.compile(
    rf"\btax\s+years?\s+({_YEAR}"
    rf"(?:\s*(?:,|-|–|—|&|\bto\b|\band\b|\bthrough\b)\s*(?:and\s+)?{_YEAR})*)"
    r"(?!\s*[-–—/]\s*\d)",
    re.IGNORECASE,
)
_TAX_YEAR_VINTAGE = re.compile(r"tax_year_(\d{4})")
_TAX_YEAR_ID_TOKEN = re.compile(r"(?<![a-z0-9])ty(\d{4})(?![0-9])")


def title_tax_year(title: str) -> int | None:
    """The one tax year a source table title names, else ``None``.

    ``None`` covers a title that names no tax year and a title that names more
    than one: neither says which year a cell of the table is for.
    """
    years = {
        int(year)
        for span in _TAX_YEAR_SPAN.findall(title)
        for year in re.findall(_YEAR, span)
    }
    return years.pop() if len(years) == 1 else None


# --- the title reader --------------------------------------------------------

W2_TITLE = (
    "Table 4.B. Summary of Items for Taxpayers with Form W-2, by Return and "
    "Earner Type, Tax Year 2020"
)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (W2_TITLE, 2020),
        ("Table 4.B, Tax Year 2020 (revised January 2026)", 2020),
        ("Table 1, Tax Year 2020, and Table 2, Tax Year 2020", 2020),
        ("table 1.4, tax  year\n2023", 2023),
        ("Individual returns, Tax Years 2019 and 2020", None),
        ("Individual returns, Tax Years 2019-2020", None),
        ("Individual returns, tax years 2019, 2020 and 2021", None),
        ("Individual returns, Tax Year 2020 through 2022", None),
        ("Table 1, Tax Year 2019, and Table 2, Tax Year 2020", None),
        ("SPI Tables 3.1 to 3.11, tax year 2023-24", None),
        ("SPI Tables 3.1 to 3.11, tax year 2023/24", None),
        ("Tax Year 20201", None),
        ("Estimates of Federal Tax Expenditures for Fiscal Years 2024-2028", None),
        ("Employer-Sponsored Insurance: Calendar Years 1987-2024", None),
        ("2020 Form W-2 statistics", None),
        ("", None),
    ],
)
def test_title_tax_year_reads_publisher_titles(title, expected):
    assert title_tax_year(title) == expected


PREFIXES = ("", "Table 4.B. Items for Taxpayers with Form W-2, ", "2020 release: ")
SUFFIXES = ("", ".", " (revised)", " [1]", ", all returns")
CONNECTORS = (" and ", "-", "–", " to ", " through ", ", ", " & ")
YEARS = (1999, 2019, 2020, 2023, 2099)


def test_title_tax_year_over_every_synthetic_title():
    """One year reads back; two different years never read as one."""
    for prefix, suffix, year in itertools.product(PREFIXES, SUFFIXES, YEARS):
        assert title_tax_year(f"{prefix}Tax Year {year}{suffix}") == year
        assert title_tax_year(f"{prefix}tax year {year}{suffix}") == year
        # No "Tax Year" marker: a year elsewhere in the title is not a tax year.
        assert title_tax_year(f"{prefix}Calendar Year {year}{suffix}") is None
    for prefix, suffix, connector, first, second in itertools.product(
        PREFIXES, SUFFIXES, CONNECTORS, YEARS, YEARS
    ):
        title = f"{prefix}Tax Years {first}{connector}{second}{suffix}"
        assert title_tax_year(title) == (first if first == second else None), title


# --- the real package tree ---------------------------------------------------


def _single_tax_year_packages() -> dict[str, int]:
    """Pinned packages whose source table title names exactly one tax year."""
    packages = {}
    for sub in discover_source_package_dirs(REPO_ROOT / "packages"):
        path = REPO_ROOT / "packages" / sub / SOURCE_PACKAGE_FILENAME
        text = path.read_text(encoding="utf-8")
        if "artifact_year:" not in text or not re.search(r"(?i)tax\s+year", text):
            continue
        artifact = yaml.safe_load(text).get("artifact") or {}
        year = title_tax_year(str(artifact.get("source_table") or ""))
        if year is not None:
            packages[str(sub)] = year
    return dict(sorted(packages.items()))


SINGLE_TAX_YEAR_PACKAGES = _single_tax_year_packages()


def test_real_tree_has_a_single_tax_year_title_to_check():
    # Guards the parametrization below against silently checking nothing.
    assert SINGLE_TAX_YEAR_PACKAGES.get("irs_soi/w2_statistics_2020") == 2020


@pytest.mark.parametrize("package_path", sorted(SINGLE_TAX_YEAR_PACKAGES))
def test_facts_carry_the_tax_year_their_source_table_names(package_path):
    package = load_source_package(REPO_ROOT / "packages" / package_path)
    table_year = SINGLE_TAX_YEAR_PACKAGES[package_path]
    facts = [
        fact_to_mapping(fact)
        for fact in package.build_facts(package.artifact.artifact_year)
    ]
    assert facts, package_path
    for fact in facts:
        where = (package_path, fact["source_record_id"])
        assert title_tax_year(fact["source"]["source_table"]) == table_year, where
        if fact["period"]["type"] != "tax_year":
            continue
        assert fact["period"]["value"] == table_year, where
        vintage = _TAX_YEAR_VINTAGE.fullmatch(fact["source"]["vintage"])
        if vintage is not None:
            assert int(vintage.group(1)) == table_year, where
        for identifier in (fact["source_record_id"], fact["layout"]["record_set_id"]):
            stamped = {int(year) for year in _TAX_YEAR_ID_TOKEN.findall(identifier)}
            assert stamped <= {table_year}, (where, identifier)


# --- IRS SOI Table 4.B (Form W-2 items) --------------------------------------

W2_PACKAGE = "irs_soi/w2_statistics_2020"
W2_WORKBOOK = (
    REPO_ROOT / "db" / "data" / "irs_soi" / "w2_statistics" / "20in04w2all.xlsx"
)
# (record-set slug, row, measure id, column, scale) for every cell the package
# reads from sheet "Table 4.B"; money amounts are in thousands of dollars.
W2_CELLS = (
    ("form_w2_social_security_tips", 13, "return_count", "B", 1),
    ("form_w2_social_security_tips", 13, "taxpayer_count", "C", 1),
    ("form_w2_social_security_tips", 13, "amount", "D", 1000),
    ("form_w2_401k_elective_deferrals", 22, "amount", "D", 1000),
    ("form_w2_designated_roth_401k_contributions", 41, "amount", "D", 1000),
)
# What IRS printed, read from the workbook on 2026-10-10.
W2_PUBLISHED = {
    "irs_soi.ty2020.form_w2_social_security_tips.box_7_social_security_tips.return_count": 6_038_613,
    "irs_soi.ty2020.form_w2_social_security_tips.box_7_social_security_tips.taxpayer_count": 6_105_713,
    "irs_soi.ty2020.form_w2_social_security_tips.box_7_social_security_tips.amount": 26_786_522_000,
    "irs_soi.ty2020.form_w2_401k_elective_deferrals.box_12_d_401k_elective_deferrals.amount": 277_859_181_000,
    "irs_soi.ty2020.form_w2_designated_roth_401k_contributions.box_12_aa_designated_roth_401k_contributions.amount": 32_302_509_000,
}


def _w2_facts(year: int) -> list[dict]:
    package = load_source_package(REPO_ROOT / "packages" / W2_PACKAGE)
    return [fact_to_mapping(fact) for fact in package.build_facts(year)]


def test_w2_package_title_is_the_workbooks_own_title_cell():
    """The declared title is the bytes' title, so the year check reads IRS."""
    sheet = openpyxl.load_workbook(W2_WORKBOOK, read_only=True)["Table 4.B"]
    printed = sheet["A1"].value
    package = load_source_package(REPO_ROOT / "packages" / W2_PACKAGE)
    assert printed == package.artifact.source_table == W2_TITLE
    assert title_tax_year(printed) == 2020 == package.artifact.artifact_year


def test_w2_facts_are_the_published_tax_year_2020_cells():
    """Differential: the package's facts against a direct read of the sheet."""
    sheet = openpyxl.load_workbook(W2_WORKBOOK, read_only=True)["Table 4.B"]
    facts = {fact["source_record_id"]: fact for fact in _w2_facts(2020)}
    assert {key: fact["value"] for key, fact in facts.items()} == W2_PUBLISHED
    read_directly = {}
    for record_set, row, measure, column, scale in W2_CELLS:
        (key,) = (
            key
            for key in facts
            if f".{record_set}." in key and key.endswith(f".{measure}")
        )
        read_directly[key] = sheet[f"{column}{row}"].value * scale
    assert read_directly == W2_PUBLISHED
    for fact in facts.values():
        assert fact["period"] == {"type": "tax_year", "value": 2020}
        assert fact["source"]["vintage"] == "tax_year_2020"
        assert fact["source"]["source_table"] == W2_TITLE
        assert fact["source"]["source_file"] == "20in04w2all.xlsx"


@pytest.mark.parametrize("year", [2019, 2021, 2022, 2023, 2024, 2025])
def test_w2_package_builds_the_same_tax_year_2020_facts_at_every_year(year):
    """``--year`` never relabels the table: 2023 is the year microcosm built."""
    package = load_source_package(REPO_ROOT / "packages" / W2_PACKAGE)
    assert artifact_year_restamp_issues(package, year) == []

    def serialized(facts):
        return [json.dumps(fact, sort_keys=True, default=str) for fact in facts]

    assert serialized(_w2_facts(year)) == serialized(_w2_facts(2020))
