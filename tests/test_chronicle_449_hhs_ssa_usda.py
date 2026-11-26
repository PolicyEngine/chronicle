"""Next editions of the LIHEAP national profile and the SNAP FY69-to-current
archive (chronicle#449).

- ``hhs-acf-liheap-fy2025-national-profile`` reads the FY2025 National Profile
  (All States) PDF, the edition after ``hhs-acf-liheap-fy2024-national-profile``.
  The PDF's text moved: "Total Households Served by State Programs" is now
  parser row 5 and text line 10 (row 3 and line 12 in FY2024).
- ``usda-snap-fy69-to-current-fy2025`` reads FY25.xlsx in the publisher's
  ``snap-zip-fy69tocurrent-11.zip``, the edition after
  ``usda-snap-fy69-to-current`` (FY24.xlsx in the ``-6`` zip). No cell moved.

The expected values are read from the publisher files directly (pypdf for the
PDF, zipfile and openpyxl for the workbook), not through Chronicle's parsers.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import openpyxl
import pytest
import yaml
from pypdf import PdfReader

from chronicle.core import validate_facts
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package
from chronicle.sources.cells import validate_source_cells
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "db" / "data"
PACKAGES_ROOT = REPO_ROOT / "packages"

LIHEAP = "hhs-acf-liheap-fy2025-national-profile"
SNAP = "usda-snap-fy69-to-current-fy2025"
LIHEAP_PDF = (
    DATA
    / "hhs_acf_liheap"
    / "fy2025_national_profile"
    / "acf_liheap_fy2025_all_states_national_profile.pdf"
)
LIHEAP_FY2024_PDF = (
    DATA
    / "hhs_acf_liheap"
    / "fy2024_national_profile"
    / "acf_liheap_fy2024_all_states_national_profile.pdf"
)
SNAP_ZIP = (
    DATA / "usda_snap" / "fy69_to_current_fy2025" / "snap-zip-fy69tocurrent-11.zip"
)

# package -> (predecessor, manifest, raw file, sha256, size, source_url)
PACKAGES = {
    LIHEAP: (
        "hhs-acf-liheap-fy2024-national-profile",
        LIHEAP_PDF.parent / "manifest.yaml",
        LIHEAP_PDF,
        "8843728772d541c4560d48565371fe9f4915f7142e6ce58fe2b3c7d836c2e762",
        125_216,
        "https://liheappm.acf.gov/sites/default/files/private/congress/profiles/"
        "2025/FY%202025%20AllStates(National)%20Profile.pdf",
    ),
    SNAP: (
        "usda-snap-fy69-to-current",
        SNAP_ZIP.parent / "manifest.yaml",
        SNAP_ZIP,
        "3feaab40ff04c232351fb5cd4f74378cd071c061f87c5e71e4c2e0b1f601a611",
        1_662_747,
        "https://www.fna.usda.gov/sites/default/files/resource-files/"
        "snap-zip-fy69tocurrent-11.zip",
    ),
}
FACT_COUNTS = {LIHEAP: 1, SNAP: 216}
CELL_COUNTS = {LIHEAP: 372, SNAP: 6_288}

# The SNAP workbook's measure columns and the header cells above them.
SNAP_COLUMNS = {
    "average_monthly_households": ("B", "B7", "Household"),
    "average_monthly_persons": ("C", "C7", "Persons"),
    "total_benefits": ("D", "D6", "Cost"),
    "average_monthly_benefit_per_person": ("F", "F7", "Persons"),
}
SNAP_TITLE = (
    "SNAP Monthly State Participation and Benefit Summary P-EBT/Other Excluded"
    " - Public Data, Fiscal Year 2025"
)
SNAP_MONTHS = (
    "Oct 2024",
    "Nov 2024",
    "Dec 2024",
    "Jan 2025",
    "Feb 2025",
    "Mar 2025",
    "Apr 2025",
    "May 2025",
    "Jun 2025",
    "Jul 2025",
    "Aug 2025",
    "Sep 2025",
)


def _build(package_id: str, year: int):
    package = load_source_package(package_id)
    cells = package.build_source_cells(year)
    return cells, package.build_facts(year, cells=cells)


@pytest.fixture(scope="module")
def built():
    built_packages = {}
    for package_id in PACKAGES:
        cells, facts = _build(package_id, 2023)
        assert validate_source_cells(cells).valid
        assert validate_facts(facts).valid
        built_packages[package_id] = (cells, facts)
    return built_packages


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_manifest_registers_the_publisher_file(package_id):
    _, manifest_path, raw_file, sha256, size, source_url = PACKAGES[package_id]
    manifest = yaml.safe_load(manifest_path.read_text())
    entry = manifest["files"][2025]

    assert manifest["package_id"] == package_id
    assert hashlib.sha256(raw_file.read_bytes()).hexdigest() == sha256
    assert entry["filename"] == raw_file.name
    assert entry["source_url"] == source_url
    assert entry["sha256"] == sha256
    assert entry["size_bytes"] == size == raw_file.stat().st_size
    assert entry["storage"]["r2"]["key"].endswith(
        f"/{package_id}/2025/{sha256}/{raw_file.name}"
    )
    assert entry["storage"]["r2"]["uri"] == (
        f"r2://ledger-raw/{entry['storage']['r2']['key']}"
    )


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_fact_count_period_and_vintage(built, package_id):
    cells, facts = built[package_id]
    _, manifest_path, raw_file, sha256, _, source_url = PACKAGES[package_id]
    entry = yaml.safe_load(manifest_path.read_text())["files"][2025]

    # A zip package's facts cite the member they read; its cells' extraction
    # method names the outer file's checksum.
    if package_id == SNAP:
        with zipfile.ZipFile(raw_file) as archive:
            read_sha256 = hashlib.sha256(archive.read("FY25.xlsx")).hexdigest()
        assert all(
            cell.artifact.extraction_method.endswith(f"from outer SHA-256 {sha256}")
            for cell in cells
        )
    else:
        read_sha256 = sha256

    assert len(cells) == CELL_COUNTS[package_id]
    assert len(facts) == FACT_COUNTS[package_id]
    assert len({fact.source_record_id for fact in facts}) == len(facts)
    for fact in facts:
        assert (fact.period.type, fact.period.value) == ("fiscal_year", 2025)
        assert fact.source.vintage == "fiscal_year_2025"
        assert fact.source.source_sha256 == read_sha256
        assert fact.source.url == source_url
        assert fact.source.source_file.startswith(raw_file.name)
        assert fact.source.raw_r2_uri == entry["storage"]["r2"]["uri"]


def _pdf_lines(path: Path) -> list[tuple[int, str]]:
    """Page 1's text lines as pypdf extracts them, numbered as the package's
    PDF parser numbers them, with runs of white space collapsed."""
    text = PdfReader(path).pages[0].extract_text()
    return [
        (number, " ".join(line.split()))
        for number, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]


def _households_served(path: Path) -> tuple[int, int]:
    """The number printed under the "Total Households Served by State
    Programs" heading, and its text line number."""
    lines = _pdf_lines(path)
    texts = [text for _, text in lines]
    heading = texts.index("Total Households Served by")
    assert texts[heading + 1] == "State Programs"
    line_number, number_text = lines[heading + 2]
    assert re.fullmatch(r"\d{1,3}(,\d{3})+", number_text)
    return int(number_text.replace(",", "")), line_number


def test_liheap_fact_is_the_households_served_cell(built):
    _, facts = built[LIHEAP]
    (fact,) = facts
    households, line_number = _households_served(LIHEAP_PDF)

    assert fact.source_record_id == (
        "hhs_acf_liheap.fy2025.national_profile.state_programs.households_served"
    )
    assert fact.value == households == 5_703_340
    assert line_number == 10
    assert fact.measure.concept == "hhs_acf_liheap.households_served_by_state_programs"
    assert fact.measure.unit == "count"
    assert fact.geography.id == "0100000US"
    assert fact.entity.name == "household"
    assert fact.source.source_file == LIHEAP_PDF.name
    assert {
        (item.variable, item.operator, item.value) for item in fact.constraints
    } == {("program", "==", "liheap"), ("administering_entity", "==", "state_programs")}


def test_liheap_editions_print_the_same_line_for_the_same_universe():
    """The reader that finds FY2025's cell finds FY2024's published value, and
    both profiles cover all states without tribal and territory grantees."""
    previous, previous_line = _households_served(LIHEAP_FY2024_PDF)
    _, previous_facts = _build("hhs-acf-liheap-fy2024-national-profile", 2024)

    assert previous_line == 12
    assert [fact.value for fact in previous_facts] == [previous] == [5_876_646]
    for path, year in ((LIHEAP_FY2024_PDF, 2024), (LIHEAP_PDF, 2025)):
        text = " ".join(line for _, line in _pdf_lines(path))
        assert text.startswith(
            f"Low Income Home Energy Assistance – FY{year} National Profile "
            "(All States)"
        )
        assert "Excludes Tribal and Territory Grant Recipients" in text


def _snap_book():
    with zipfile.ZipFile(SNAP_ZIP) as archive:
        content = archive.read("FY25.xlsx")
    return openpyxl.load_workbook(io.BytesIO(content), data_only=True)


def _snap_total_row(sheet, block: str) -> int:
    """The "Total" row of a geography block, found by the block's name."""
    starts = [
        row for row in range(1, sheet.max_row + 1) if sheet.cell(row, 1).value == block
    ]
    assert len(starts) == 1, (sheet.title, block)
    start = starts[0]
    months = tuple(sheet.cell(start + offset, 1).value for offset in range(1, 13))
    assert months == SNAP_MONTHS, (sheet.title, block)
    for row in range(start + 1, start + 13):
        for column in "BCDEF":
            assert isinstance(sheet[f"{column}{row}"].value, (int, float)), (
                sheet.title,
                block,
                f"{column}{row}",
            )
    assert sheet.cell(start + 13, 1).value == "Total"
    return start + 13


def test_snap_facts_are_their_total_cells(built):
    """Each fact is the "Total" row of its sheet's geography block, found by
    name: the fiscal-year figure over twelve published months."""
    _, facts = built[SNAP]
    book = _snap_book()
    for sheet in book.worksheets:
        assert sheet["A2"].value == SNAP_TITLE
        assert sheet["B6"].value == "Participation 1/"
        assert sheet["E6"].value == "Cost Per"
        for _, address, header in SNAP_COLUMNS.values():
            assert sheet[address].value == header

    for fact in facts:
        parts = fact.source_record_id.split(".")
        measure_id, value_id = parts[-1], parts[-2]
        if value_id == "national_total":
            sheet, block = book["US Summary"], "US Summary"
            assert fact.geography.id == "0100000US"
        else:
            sheet, block = book[parts[-3].upper()], fact.geography.name
            assert fact.geography.level == "state"
        column = SNAP_COLUMNS[measure_id][0]
        expected = sheet[f"{column}{_snap_total_row(sheet, block)}"].value

        assert fact.value == expected, fact.source_record_id
        assert fact.source.source_file == "snap-zip-fy69tocurrent-11.zip!FY25.xlsx"


def test_snap_published_national_totals(built):
    _, facts = built[SNAP]
    values = {fact.source_record_id: fact.value for fact in facts}
    prefix = "usda_snap.fy2025."

    # US Summary, row 21 "Total", as printed in FY25.xlsx.
    assert values[
        prefix + "national_average_monthly_households.national_total."
        "average_monthly_households"
    ] == pytest.approx(22_580_311.3333)
    assert values[
        prefix + "national_average_monthly_persons.national_total."
        "average_monthly_persons"
    ] == pytest.approx(42_142_183.75)
    benefits = prefix + "national_benefits.national_total.total_benefits"
    assert values[benefits] == 95_757_193_976


@pytest.mark.parametrize("build_year", [2023, 2024])
def test_building_at_another_year_does_not_relabel_the_2025_files(built, build_year):
    for package_id in PACKAGES:
        _, other = _build(package_id, build_year)
        _, facts = built[package_id]
        assert sorted(
            (fact.source_record_id, fact.value, fact.period.value) for fact in other
        ) == sorted(
            (fact.source_record_id, fact.value, fact.period.value) for fact in facts
        )


def _declarations(package_id: str) -> dict:
    path = PACKAGES_ROOT / SOURCE_PACKAGE_ALIASES[package_id] / "source_package.yaml"
    return yaml.safe_load(path.read_text())


def _leaves(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, (*path, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _leaves(value, (*path, index))
    else:
        yield path, node


def _pattern(path: tuple) -> tuple:
    return tuple("*" if isinstance(part, int) else part for part in path)


# Each new package's top-level declarations that name its edition.
EDITION_FIELDS = {
    LIHEAP: {
        ("package_id",): "hhs-acf-liheap-fy2025-national-profile",
        ("label",): "HHS ACF LIHEAP FY2025 National Profile",
        ("artifact", "source_table"): "LIHEAP FY2025 National Profile (All States)",
        ("artifact", "resource_directory"): (
            "data/hhs_acf_liheap/fy2025_national_profile"
        ),
        ("artifact", "vintage"): "fiscal_year_2025",
        ("artifact", "extracted_at"): "2026-11-26",
        ("artifact", "artifact_year"): 2025,
    },
    SNAP: {
        ("package_id",): "usda-snap-fy69-to-current-fy2025",
        ("label",): (
            "USDA FNS SNAP FY69 to current archive FY25 national and state summary"
        ),
        ("artifact", "resource_directory"): "data/usda_snap/fy69_to_current_fy2025",
        ("artifact", "vintage"): "fiscal_year_2025",
        ("artifact", "extracted_at"): "2026-11-26",
        ("artifact", "archive_member"): "FY25.xlsx",
        ("artifact", "artifact_year"): 2025,
    },
}
# Per record set: ids and period carry the fiscal year.
RELABELLED = {
    ("record_sets", "*", "record_set_id"),
    ("record_sets", "*", "source_record_id_prefix"),
    ("record_sets", "*", "period"),
}
# Cell positions and guards the FY2025 PDF moved: the row, its header text
# (the number itself), the text line number and the number in the line.
LIHEAP_MOVED = {
    ("record_sets", 0, "rows", 0, "row_number"): (3, 5),
    ("record_sets", 0, "rows", 0, "expected_row_header"): ("5,876,646", "5,703,340"),
    ("record_sets", 0, "rows", 0, "guard_cells", 1, "expected_value"): (12, 10),
    ("record_sets", 0, "rows", 0, "guard_cells", 2, "expected_value"): (
        "5,876,646",
        "5,703,340",
    ),
    ("record_sets", 0, "rows", 0, "guard_cells", 3, "expected_value"): (
        "Total Households Served by State Programs 5,876,646 State Maximum Income "
        "Eligibility Requirements for",
        "Total Households Served by State Programs 5,703,340 State Maximum Income "
        "Eligibility Requirements for",
    ),
}


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_packages_mirror_their_predecessors(package_id):
    """Differential: apart from the edition's ids, period, vintage, artifact
    references and the positions the new file moved, every declaration
    (concepts, units, labels, rows, columns, filters, constraints, guards)
    equals the predecessor's."""
    predecessor = PACKAGES[package_id][0]
    old = dict(_leaves(_declarations(predecessor)))
    new = dict(_leaves(_declarations(package_id)))

    assert old.keys() == new.keys()
    changed = {path for path in old if old[path] != new[path]}
    edition = EDITION_FIELDS[package_id]
    for path, value in edition.items():
        assert new[path] == value, path
    for path in changed - set(edition):
        if _pattern(path) in RELABELLED:
            assert str(new[path]) == str(old[path]).replace("2024", "2025"), path
        elif package_id == LIHEAP:
            assert (old[path], new[path]) == LIHEAP_MOVED[path], path
        else:
            # The SNAP title guard (A2) names the fiscal year; no cell moved.
            assert _pattern(path) == (
                "record_sets",
                "*",
                "rows",
                "*",
                "guard_cells",
                "*",
                "expected_value",
            ), path
            assert old[path] == SNAP_TITLE.replace("2025", "2024")
            assert new[path] == SNAP_TITLE
    if package_id == LIHEAP:
        assert set(LIHEAP_MOVED) <= changed
    # LIHEAP: 7 edition fields, 3 relabelled ids and period, 5 moved positions.
    # SNAP: 7 edition fields, 3 x 24 record sets, 162 title guards.
    assert len(changed) == {LIHEAP: 15, SNAP: 241}[package_id]
    assert "{year}" not in json.dumps(_declarations(package_id))


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_source_suite_passes_agent_acceptance(package_id, tmp_path):
    suite = build_source_suite(package_id, tmp_path / package_id, year=2023)

    assert suite.agent_acceptance.valid
    assert suite.agent_acceptance.counts["row_semantic_error_count"] == 0
