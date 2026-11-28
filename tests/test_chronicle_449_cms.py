"""CMS 2026 editions of two packages in the US feed (chronicle#449).

``cms-aca-oep-state-level-2026`` reads the 2026 OEP State-Level Public Use
File and mirrors ``cms-aca-oep-state-level-2025``. The 2026 CSV inserts five
columns at O for consumers assisted by an agent or broker (``AB_Cnsmr`` to
``AB_Auto_Renrl``) and ends each line with an empty column, so ``APTC_Cnsmr``
moves from AJ to AO and ``APTC_Cnsmr_Avg_APTC`` from AK to AP; ``Cnsmr`` stays
at H. The zip keeps its two members in a folder, ``2026 OEP State-Level PUF/``.

``cms-medicare-trustees-report-2026-part-b-premium-income`` reads Table III.C3
of the 2026 Medicare Trustees Report and mirrors the 2025 package: Part B
premiums from enrollees, the actual amount for calendar year 2025, on PDF
page 92 instead of 91.

The tests read the CSV with the standard library and the PDF page with pypdf
directly, so the values they check do not depend on Chronicle's cell parsers.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from pathlib import Path

import pytest
import yaml
from openpyxl.utils import column_index_from_string
from pypdf import PdfReader

from chronicle.core import validate_facts
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package
from chronicle.sources.cells import validate_source_cells
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "db" / "data"
PACKAGES_ROOT = REPO_ROOT / "packages"

OEP = "cms-aca-oep-state-level-2026"
OEP_2025 = "cms-aca-oep-state-level-2025"
OEP_ZIP = DATA / "cms_aca/oep_state_level_2026/2026-oep-state-level-public-use-file.zip"
OEP_ZIP_2025 = (
    DATA / "cms_aca/oep_state_level_2025/2025-oep-state-level-public-use-file.zip"
)
OEP_MEMBER = "2026 OEP State-Level PUF/2026 OEP State-Level Public Use File.csv"
OEP_MEASURES = {
    "marketplace_enrollment": "Cnsmr",
    "aptc_recipients": "APTC_Cnsmr",
    "average_monthly_aptc": "APTC_Cnsmr_Avg_APTC",
}

TRUSTEES = "cms-medicare-trustees-report-2026-part-b-premium-income"
TRUSTEES_2025 = "cms-medicare-trustees-report-2025-part-b-premium-income"
TRUSTEES_PDF = (
    DATA / "cms_medicare/medicare_trustees_report_2026"
    "/cms_2026_medicare_trustees_report.pdf"
)
TRUSTEES_PDF_2025 = (
    DATA / "cms_medicare/medicare_trustees_report_2025"
    "/cms_2025_medicare_trustees_report.pdf"
)
TRUSTEES_RECORD = "premiums_from_enrollees.actual_amount"
TRUSTEES_CONTEXT = (
    "percentage of estimate Premiums from enrollees $150,318 $154,844 97% "
    "$155,046 97% Government contributions 422,9352 423,450 100 423,380 100 "
    "Benefit payments3 578,426 573,050 101 564,843 102"
)

# package -> (raw file, sha256, size, publisher URL)
FILES = {
    OEP: (
        OEP_ZIP,
        "11555f328f4df04f52b9c2c833bfb5710d50d48bbf45ef6c09d10274ef5cfefe",
        140_039,
        "https://www.cms.gov/files/zip/2026-oep-state-level-public-use-file.zip",
    ),
    TRUSTEES: (
        TRUSTEES_PDF,
        "ffa56b9137006872300b0346149eae1613d09a172b6ba118aad48e66dfc48fa8",
        2_844_621,
        "https://www.cms.gov/oact/tr/2026",
    ),
}
# Census state FIPS codes (50 states and DC), independent of the packages.
FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56",
}  # fmt: skip

# Every difference between each new package file and its predecessor's, with
# the new value: the edition's ids, labels, period and artifact, and the
# positions that moved. Everything else (concepts, units, scales, filters,
# constraints, labels, rows) is unchanged.
OEP_CHANGES = {
    ("package_id",): OEP,
    ("label",): "CMS Marketplace 2026 OEP state-level public use file",
    ("artifact", "source_table"): "2026 OEP State-Level Public Use File",
    ("artifact", "resource_directory"): "data/cms_aca/oep_state_level_2026",
    ("artifact", "vintage"): "2026_open_enrollment_period",
    ("artifact", "extracted_at"): "2026-11-26",
    ("artifact", "archive_member"): OEP_MEMBER,
    ("artifact", "sheet_name"): OEP_MEMBER,
    ("record_sets", 0, "sheet_name"): OEP_MEMBER,
    ("record_sets", 0, "measures", 1, "column"): "AO",  # AJ in 2025
    ("record_sets", 0, "measures", 2, "column"): "AP",  # AK in 2025
}
_GUARDS = ("record_sets", 0, "rows", 0, "guard_cells")
TRUSTEES_CHANGES = {
    ("package_id",): TRUSTEES,
    ("label",): "CMS Medicare Trustees Report 2026 Part B premium income",
    ("artifact", "source_table"): "2026 Medicare Trustees Report Table III.C3",
    ("artifact", "resource_directory"): (
        "data/cms_medicare/medicare_trustees_report_2026"
    ),
    ("artifact", "vintage"): "trustees_report_2026",
    ("artifact", "extracted_at"): "2026-11-26",
    ("artifact", "artifact_year"): 2026,
    ("record_sets", 0, "record_set_id"): "cms_medicare.cy2025.part_b_premium_income",
    ("record_sets", 0, "source_record_id_prefix"): (
        "cms_medicare.cy2025.part_b_premium_income"
    ),
    ("record_sets", 0, "period"): 2025,
    ("record_sets", 0, "rows", 0, "row_number"): 3440,
    ("record_sets", 0, "rows", 0, "expected_row_header"): (
        "Premiums from enrollees $150,318 $154,844 97% $155,046 97%"
    ),
    (*_GUARDS, 0, "expected_value"): 92,
    (*_GUARDS, 1, "expected_value"): 45,
    (*_GUARDS, 2, "expected_value"): "$150,318",
    (*_GUARDS, 3, "expected_value"): TRUSTEES_CONTEXT,
}


def _package_yaml(package_id: str) -> dict:
    path = PACKAGES_ROOT / SOURCE_PACKAGE_ALIASES[package_id] / "source_package.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _build(package_id: str, year: int):
    package = load_source_package(package_id)
    rows = package.build_source_rows(year)
    cells = package.build_source_cells(year, source_rows=rows)
    facts = package.build_facts(year, cells=cells, source_rows=rows)
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    return facts


@pytest.fixture(scope="module")
def built():
    return {
        OEP: _build(OEP, 2026),
        OEP_2025: _build(OEP_2025, 2025),
        TRUSTEES: _build(TRUSTEES, 2026),
        TRUSTEES_2025: _build(TRUSTEES_2025, 2025),
    }


def _csv_lines(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        (member,) = [name for name in archive.namelist() if name.endswith(".csv")]
        text = archive.read(member).decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def _number(text: str) -> int:
    """A CSV cell as printed, such as "1,927,371" or "$579 "."""
    return int(text.strip().removeprefix("$").replace(",", ""))


def _diff_paths(old, new, path: tuple = ()) -> set[tuple]:
    if isinstance(old, dict) and isinstance(new, dict):
        paths = {path + (key,) for key in old.keys() ^ new.keys()}
        for key in old.keys() & new.keys():
            paths |= _diff_paths(old[key], new[key], path + (key,))
        return paths
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        paths = set()
        for index, (old_item, new_item) in enumerate(zip(old, new, strict=True)):
            paths |= _diff_paths(old_item, new_item, path + (index,))
        return paths
    return set() if old == new else {path}


@pytest.mark.parametrize("package_id", sorted(FILES))
def test_manifest_registers_the_publisher_file(package_id):
    path, sha256, size, url = FILES[package_id]
    manifest = yaml.safe_load((path.parent / "manifest.yaml").read_text())
    entry = manifest["files"][2026]

    assert manifest["package_id"] == package_id
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha256
    assert entry["filename"] == path.name
    assert entry["source_url"] == url
    assert entry["sha256"] == sha256
    assert entry["size_bytes"] == size == path.stat().st_size
    assert entry["storage"]["r2"]["key"] == (
        f"raw/{manifest['source_id']}/{package_id}/2026/{sha256}/{path.name}"
    )


def test_oep_zip_keeps_its_members_in_a_folder():
    with zipfile.ZipFile(OEP_ZIP) as archive:
        assert archive.namelist() == [
            OEP_MEMBER,
            "2026 OEP State-Level PUF/2026 OEP State-Level Public Use File.xlsx",
        ]


def test_oep_facts_are_their_publisher_cells(built):
    lines = _csv_lines(OEP_ZIP)
    header = lines[0]
    states = {line[0]: line for line in lines[1:52]}
    assert sorted(states) == sorted(FIPS)

    seen = set()
    for fact in built[OEP]:
        state = fact.layout.groupby_value_id.upper()
        column = OEP_MEASURES[fact.layout.measure_id]
        assert fact.layout.source_column_id == column
        assert fact.value == _number(states[state][header.index(column)]), (
            fact.source_record_id
        )
        assert fact.source_record_id == (
            f"cms_aca.oep2026.state_marketplace.{state.lower()}."
            f"{fact.layout.measure_id}"
        )
        assert fact.geography.level == "state"
        assert fact.geography.id == f"0400000US{FIPS[state]}"
        assert len(fact.source_row_keys) == 1
        assert fact.period.type == "calendar_year"
        assert fact.period.value == 2026
        assert fact.source.vintage == "2026_open_enrollment_period"
        assert fact.source.source_sha256 == FILES[OEP][1]
        seen.add((state, column))
    assert len(built[OEP]) == 153
    assert seen == {
        (state, column) for state in FIPS for column in OEP_MEASURES.values()
    }


def test_oep_columns_move_only_by_the_inserted_agent_broker_columns():
    header_2025 = _csv_lines(OEP_ZIP_2025)[0]
    header = _csv_lines(OEP_ZIP)[0]

    assert header[14:19] == [
        "AB_Cnsmr",
        "AB_New_Cnsmr",
        "AB_Tot_Renrl",
        "AB_Actv_Renrl",
        "AB_Auto_Renrl",
    ]
    assert header[107:] == [""]
    assert header[:14] + header[19:107] == header_2025


def test_oep_measure_columns_and_rows_head_their_cells():
    lines = _csv_lines(OEP_ZIP)
    (record_set,) = _package_yaml(OEP)["record_sets"]

    columns = {}
    for measure in record_set["measures"]:
        variable = measure["source_column_id"]
        assert lines[0][column_index_from_string(measure["column"]) - 1] == variable
        assert measure["expected_column_header_row"] == 1
        assert measure["expected_column_header"] == variable
        columns[variable] = measure["column"]
    assert columns == {"Cnsmr": "H", "APTC_Cnsmr": "AO", "APTC_Cnsmr_Avg_APTC": "AP"}
    assert len(record_set["rows"]) == 51
    for row in record_set["rows"]:
        assert row["expected_row_header_column"] == "A"
        assert (
            lines[row["row_number"] - 1][0]
            == row["expected_row_header"]
            == row["value_id"].upper()
        )


def test_oep_illinois_and_dc_rows_change_population_not_columns(built):
    """Illinois left HealthCare.gov for its own exchange in 2026, and DC's
    Basic Health Program enrollment appears in its own column. Both rows keep
    the three measures."""
    header_2025, *lines_2025 = _csv_lines(OEP_ZIP_2025)
    header, *lines = _csv_lines(OEP_ZIP)
    rows_2025 = {line[0]: line for line in lines_2025[:51]}
    rows = {line[0]: line for line in lines[:51]}

    assert [state for state in rows if rows[state][1] != rows_2025[state][1]] == ["IL"]
    assert (rows_2025["IL"][1], rows["IL"][1]) == ("HC.gov", "SBE")
    bhp_2025, bhp = header_2025.index("BHP_Enrlmnt"), header.index("BHP_Enrlmnt")
    assert (rows_2025["DC"][bhp_2025], rows["DC"][bhp]) == ("+", "15,722")
    record_ids = {fact.source_record_id for fact in built[OEP]}
    for state in ("il", "dc"):
        for measure_id in OEP_MEASURES:
            assert f"cms_aca.oep2026.state_marketplace.{state}.{measure_id}" in (
                record_ids
            )


@pytest.mark.parametrize(
    ("package_id", "pdf", "page_number", "calendar_year"),
    [(TRUSTEES, TRUSTEES_PDF, 92, 2025), (TRUSTEES_2025, TRUSTEES_PDF_2025, 91, 2024)],
)
def test_trustees_fact_is_the_actual_amount_in_table_iii_c3(
    built, package_id, pdf, page_number, calendar_year
):
    """Each report's Table III.C3 has the same title, unit, columns and row;
    the fact is the row's first amount, the actual one, in millions."""
    text = PdfReader(pdf).pages[page_number - 1].extract_text()
    lines = [line.strip() for line in text.splitlines()]

    title = lines.index(
        "Table III.C3.—Comparison of Actual and Estimated Operations of the "
        "Part B Account"
    )
    assert lines[title + 1 : title + 3] == [
        f"in the SMI Trust Fund, Calendar Year {calendar_year}",
        "[Dollar amounts in millions]",
    ]
    item = lines.index("Item")
    assert lines[item + 1 : item + 3] == ["Actual", "amount"]
    (row,) = [line for line in lines if line.startswith("Premiums from enrollees $")]
    actual = re.match(r"Premiums from enrollees \$([\d,]+) ", row).group(1)

    (fact,) = built[package_id]
    assert fact.value == int(actual.replace(",", "")) * 1_000_000
    assert fact.source_record_id == (
        f"cms_medicare.cy{calendar_year}.part_b_premium_income.{TRUSTEES_RECORD}"
    )
    assert fact.period.type == "calendar_year"
    assert fact.period.value == calendar_year


def test_trustees_2026_fact_count_period_and_vintage(built):
    (fact,) = built[TRUSTEES]

    assert fact.value == 150_318_000_000
    assert fact.period.value == 2025
    assert fact.source.vintage == "trustees_report_2026"
    assert fact.source.source_sha256 == FILES[TRUSTEES][1]
    assert fact.source.source_file == TRUSTEES_PDF.name


@pytest.mark.parametrize(
    ("package_id", "predecessor", "changes"),
    [(OEP, OEP_2025, OEP_CHANGES), (TRUSTEES, TRUSTEES_2025, TRUSTEES_CHANGES)],
)
def test_package_file_equals_its_predecessor_apart_from_the_edition(
    package_id, predecessor, changes
):
    new, old = _package_yaml(package_id), _package_yaml(predecessor)

    assert _diff_paths(old, new) == set(changes)
    for path, value in changes.items():
        node = new
        for key in path:
            node = node[key]
        assert node == value, path


def _definition(fact) -> tuple:
    layout = fact.layout
    return (
        fact.measure,
        fact.aggregation,
        fact.entity,
        fact.geography,
        fact.filters,
        fact.constraints,
        fact.domain,
        fact.provenance_class,
        fact.assertion,
        fact.period.type,
        fact.dimension_labels,
        fact.dimension_value_labels,
        layout.record_set_spec_id,
        layout.groupby_dimension,
        layout.groupby_value_id,
        layout.groupby_value_label,
        layout.groupby_ordinal,
        layout.measure_id,
        layout.measure_label,
        layout.measure_ordinal,
        layout.source_column_id,
        layout.table_record_kind,
    )


@pytest.mark.parametrize(
    ("package_id", "predecessor", "old_token", "new_token"),
    [
        (OEP, OEP_2025, ".oep2025.", ".oep2026."),
        (TRUSTEES, TRUSTEES_2025, ".cy2024.", ".cy2025."),
    ],
)
def test_facts_keep_their_predecessors_definitions(
    built, package_id, predecessor, old_token, new_token
):
    old = {
        fact.source_record_id.replace(old_token, new_token): fact
        for fact in built[predecessor]
    }
    new = {fact.source_record_id: fact for fact in built[package_id]}

    assert set(new) == set(old)
    for record_id, fact in new.items():
        assert _definition(fact) == _definition(old[record_id]), record_id
        assert fact.period.value == old[record_id].period.value + 1


def test_build_years():
    """The OEP package has only the 2026 file, so the 2023 bundle skips it; the
    Trustees package pins its 2026 report, so any build year gives its fact."""
    with pytest.raises(ValueError, match="No source artifact for year 2023"):
        load_source_package(OEP).build_source_rows(2023)
    assert [
        (fact.source_record_id, fact.value, fact.period.value)
        for fact in _build(TRUSTEES, 2023)
    ] == [
        (
            f"cms_medicare.cy2025.part_b_premium_income.{TRUSTEES_RECORD}",
            150_318_000_000,
            2025,
        )
    ]


@pytest.mark.parametrize("package_id", sorted(FILES))
def test_source_suite_passes_agent_acceptance(package_id, tmp_path):
    suite = build_source_suite(package_id, tmp_path / package_id, year=2026)

    assert suite.agent_acceptance.valid
    assert suite.agent_acceptance.counts["row_semantic_error_count"] == 0
