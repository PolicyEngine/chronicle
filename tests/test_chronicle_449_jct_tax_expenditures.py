"""``jct-tax-expenditures-2025``: JCX-45-25, the edition after JCX-48-24
(chronicle#449).

The package reads a CSV extract of 13 lines of Table 1 of "Estimates of
Federal Tax Expenditures for Fiscal Years 2025-2029" (JCX-45-25, December 3,
2025): the fiscal year 2025 column of the Individuals block, in billions of
dollars. It declares its predecessor's concept, measure, unit, labels, filters
and constraints. One difference: JCT prints the charitable deduction on three
lines, and this package reads each line as its own row. It stores no sum; the
predecessor's ``charitable_deduction`` row is the sum of the three.

The publisher PDF is registered raw-only beside the package. These tests read
its text with pypdf, not through Chronicle's parsers, and check each CSV value
against its Table 1 line.
"""

from __future__ import annotations

import csv
import hashlib
import re
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

from chronicle.core import validate_facts
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package
from chronicle.sources.cells import validate_source_cells

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "db" / "data" / "jct"
PACKAGES_ROOT = REPO_ROOT / "packages"
PACKAGE = "jct-tax-expenditures-2025"
PREDECESSOR = "jct-tax-expenditures-2024"
CSV_PATH = DATA / "tax_expenditures_2025" / "jct_tax_expenditures_2025.csv"
CSV_SHA256 = "5eb22e8a889d7fc5d0150120e2e12a150dc480063eef6c48217c08896c03a956"
CSV_SIZE = 3_947
RAW_ONLY = DATA / "tax_expenditures_2025_raw_only"
PDF = RAW_ONLY / "x-45-25.pdf"
PDF_SHA256 = "d1532ca4ee461292f206344f790a6869cf60b990d45c635e180a6a3c858c20ab"
PDF_SIZE = 699_015
PUBLICATION_PAGE = "https://www.jct.gov/publications/2025/jcx-45-25/"

# One printed entry of a Table 1 row: no estimate, "[2]" (a positive tax
# expenditure of less than $50 million) or a number with one decimal. pypdf
# sometimes puts a space inside a number ("59. 5"), so rows are parsed with
# their spaces removed.
ENTRY = re.compile(r"---|\[2\]|-?[\d,]+\.\d")

# Row -> (PDF page, printed page, the row's label lines as the PDF prints
# them, fiscal year 2025 Individuals entry in billions of dollars).
TABLE_1_ROWS = {
    "salt_deduction": (
        45,
        43,
        ["Deduction of nonbusiness State and local government", "taxes"],
        "49.1",
    ),
    "medical_expense_deduction": (
        43,
        41,
        ["Deduction for medical expenses and long-term care", "expenses"],
        "12.8",
    ),
    "charitable_deduction_other_than_education_and_health": (
        43,
        41,
        [
            "Deduction for charitable contributions, other than for",
            "education and health [12]",
        ],
        "49.2",
    ),
    "charitable_deduction_education": (
        41,
        39,
        ["Deduction for charitable contributions to educational", "institutions"],
        "9.1",
    ),
    "charitable_deduction_health": (
        43,
        41,
        ["Deduction for charitable contributions to health", "organizations"],
        "5.9",
    ),
    "deductible_mortgage_interest": (
        38,
        36,
        ["Deduction for mortgage interest on owner-occupied", "residences"],
        "45.5",
    ),
    "qualified_business_income_deduction": (
        39,
        37,
        ["Deduction for qualified business income"],
        "75.5",
    ),
    "self_employed_health_insurance_deduction": (
        43,
        41,
        [
            "Deduction for health insurance premiums and long-term",
            "care insurance premiums by the self-employed",
        ],
        "9.5",
    ),
    "health_savings_account_deduction": (
        43,
        41,
        ["Health savings accounts [14]"],
        "13.1",
    ),
    "student_loan_interest_deduction": (
        41,
        39,
        ["Deduction for interest on student loans"],
        "2.6",
    ),
    "self_employed_pension_contribution_deduction": (
        44,
        42,
        [
            "Net exclusion of pension contributions and earnings:",
            "Plans covering partners and sole proprietors (sometimes",
            'referred to as "Keogh plans")',
        ],
        "16.2",
    ),
    "traditional_ira_deduction": (
        44,
        42,
        ["Individual retirement arrangements:", "Traditional IRAs"],
        "19.1",
    ),
    "cdcc_and_employer_child_care_exclusion": (
        42,
        40,
        [
            "Credit for child and dependent care and exclusion of",
            "employer-provided child care [3][11]",
        ],
        "5.0",
    ),
}
CHARITABLE_ROWS = [
    "charitable_deduction_other_than_education_and_health",
    "charitable_deduction_education",
    "charitable_deduction_health",
]


@pytest.fixture(scope="module")
def pdf_pages():
    reader = PdfReader(PDF)
    return {
        number: reader.pages[number - 1].extract_text().split("\n")
        for number in {1, 36, *(row[0] for row in TABLE_1_ROWS.values())}
    }


@pytest.fixture(scope="module")
def csv_rows():
    with CSV_PATH.open(newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def built():
    package = load_source_package(PACKAGE)
    cells = package.build_source_cells(2025)
    facts = package.build_facts(2025, cells=cells)
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    return cells, facts


def _entries(lines: list[str], labels: list[str]) -> list[str]:
    """The 11 printed entries of the one row whose label lines are ``labels``:
    five Corporations years, five Individuals years and the 2025-29 total."""
    found = []
    for start in range(len(lines) - len(labels) + 1):
        window = [line.strip() for line in lines[start : start + len(labels)]]
        if window[:-1] != labels[:-1]:
            continue
        match = re.fullmatch(re.escape(labels[-1]) + r"\s*[.…]{4,}(.*)", window[-1])
        if match:
            found.append(match.group(1).replace(" ", ""))
    assert len(found) == 1, labels
    entries = ENTRY.findall(found[0])
    assert "".join(entries) == found[0], labels
    assert len(entries) == 11, labels
    return entries


def _number(entry: str) -> Decimal:
    return Decimal(entry.replace(",", ""))


def test_manifests_register_the_extract_and_the_publisher_pdf():
    manifest = yaml.safe_load((CSV_PATH.parent / "manifest.yaml").read_text())
    entry = manifest["files"][2025]

    assert manifest["package_id"] == PACKAGE
    assert manifest["source_page"] == PUBLICATION_PAGE
    assert hashlib.sha256(CSV_PATH.read_bytes()).hexdigest() == CSV_SHA256
    assert entry["filename"] == CSV_PATH.name
    assert entry["sha256"] == CSV_SHA256
    assert entry["size_bytes"] == CSV_SIZE == CSV_PATH.stat().st_size
    assert entry["storage"]["r2"]["key"] == (
        f"raw/jct/{PACKAGE}/2025/{CSV_SHA256}/{CSV_PATH.name}"
    )

    raw_only = yaml.safe_load((RAW_ONLY / "manifest.yaml").read_text())
    pdf = raw_only["files"]["report_pdf"]
    assert raw_only["package_id"] == PACKAGE
    assert raw_only["registration_kind"] == "raw_only"
    assert list(raw_only["files"]) == ["report_pdf"]
    assert hashlib.sha256(PDF.read_bytes()).hexdigest() == PDF_SHA256
    assert pdf["filename"] == PDF.name
    assert pdf["sha256"] == PDF_SHA256
    assert pdf["size_bytes"] == PDF_SIZE == PDF.stat().st_size
    assert pdf["storage"]["r2"]["key"] == (
        f"raw/jct/{PACKAGE}/report_pdf/{PDF_SHA256}/{PDF.name}"
    )


def test_the_pdf_is_jcx_45_25_and_table_1_is_in_billions(pdf_pages):
    cover = " ".join(line.strip() for line in pdf_pages[1])
    table_1 = " ".join(line.strip() for line in pdf_pages[36])

    assert "ESTIMATES OF FEDERAL TAX EXPENDITURES FOR FISCAL YEARS 2025-2029" in cover
    assert "December 3, 2025" in cover
    assert "JCX-45-25" in cover
    assert "Tax Expenditure Estimates By Budget Function, Fiscal Years 2025" in table_1
    assert "[Billions of Dollars]" in table_1
    for page, printed, _, _ in TABLE_1_ROWS.values():
        lines = pdf_pages[page]
        # Each Table 1 page repeats the five fiscal years for both blocks.
        assert "Function 2025 2026 2027 2028 2029 2025 2026 2027 2028 2029" in lines
        assert lines[-1].strip() == str(printed)


def test_the_first_five_entries_are_corporations_and_the_next_five_individuals(
    pdf_pages,
):
    """Table 1 prints the Corporations block first and the Individuals block
    second (checked by eye on the rendered pages; pypdf returns the two block
    headings as one out-of-order chunk). Two control lines on PDF page 43 show
    the same order in the text: only corporations claim the orphan drug credit
    and only individuals claim the earned income credit."""
    lines = pdf_pages[43]
    orphan_drug = _entries(lines, ["Credit for orphan drug research"])
    earned_income = _entries(lines, ["Earned income credit [3]"])

    assert orphan_drug[:5] == ["1.6", "1.7", "1.8", "1.9", "2.0"]
    assert orphan_drug[5:10] == ["---"] * 5
    assert earned_income[:5] == ["---"] * 5
    assert earned_income[5:10] == ["66.9", "67.2", "67.4", "67.6", "67.8"]


def test_every_csv_value_is_its_table_1_entry(pdf_pages, csv_rows):
    assert [row["tax_expenditure"] for row in csv_rows] == list(TABLE_1_ROWS)
    for row in csv_rows:
        page, printed, labels, expected = TABLE_1_ROWS[row["tax_expenditure"]]
        entries = _entries(pdf_pages[page], labels)
        individuals_2025 = entries[5]

        assert individuals_2025 == expected, row["tax_expenditure"]
        assert Decimal(row["individual_revenue_loss_2025"]) == (
            _number(individuals_2025) * Decimal(10) ** 9
        )
        assert int(row["jct_table_1_printed_page"]) == printed
        # The row is read whole: its ten yearly entries add up to its printed
        # 2025-29 total, to within JCT's rounding ("Details may not add to
        # totals due to rounding").
        years = [_number(entry) for entry in entries[:10] if entry != "---"]
        assert "[2]" not in entries
        assert abs(sum(years) - _number(entries[10])) <= Decimal("0.3")
        # The label column is the line as printed, without footnote marks.
        printed_label = re.sub(r"\s*\[\d+\]", "", " ".join(labels))
        assert row["jct_line_label"] == printed_label


def test_facts_are_the_fiscal_year_2025_individual_estimates(built):
    cells, facts = built
    by_id = {fact.source_record_id: fact for fact in facts}

    assert len(facts) == 13
    assert set(by_id) == {
        f"jct.tax_expenditures.fy2025.{row}.revenue_loss" for row in TABLE_1_ROWS
    }
    for row, (_, _, _, expected) in TABLE_1_ROWS.items():
        fact = by_id[f"jct.tax_expenditures.fy2025.{row}.revenue_loss"]
        assert Decimal(repr(fact.value)) == Decimal(expected) * Decimal(10) ** 9
        assert fact.filters == {"tax_expenditure": row}
    assert {(fact.period.type, fact.period.value) for fact in facts} == {
        ("fiscal_year", 2025)
    }
    assert {(fact.geography.id, fact.geography.level) for fact in facts} == {
        ("0100000US", "country")
    }
    assert {(fact.entity.name, fact.entity.role) for fact in facts} == {
        ("tax_unit", "federal_income_tax_unit")
    }
    assert {fact.measure.concept for fact in facts} == {
        "jct.individual_tax_expenditure_revenue_loss"
    }
    assert {fact.measure.unit for fact in facts} == {"usd"}
    assert {fact.source.vintage for fact in facts} == {"jcx_45_25"}
    assert {fact.source.source_file for fact in facts} == {CSV_PATH.name}
    assert {fact.source.url for fact in facts} == {PUBLICATION_PAGE}


def test_the_charitable_lines_stay_apart_and_no_sum_is_stored(built, csv_rows):
    _, facts = built
    rows = {fact.filters["tax_expenditure"]: fact.value for fact in facts}

    assert "charitable_deduction" not in rows
    assert "charitable_deduction" not in {row["tax_expenditure"] for row in csv_rows}
    assert [rows[row] for row in CHARITABLE_ROWS] == [
        49_200_000_000,
        9_100_000_000,
        5_900_000_000,
    ]
    # No fact holds the three lines' total (64.2 billion dollars).
    assert 64_200_000_000 not in rows.values()


def _declarations(package_id: str) -> dict:
    path = PACKAGES_ROOT / SOURCE_PACKAGE_ALIASES[package_id] / "source_package.yaml"
    return yaml.safe_load(path.read_text())


def test_package_mirrors_its_predecessor_except_the_charitable_lines():
    """Differential: apart from the edition's ids, period, vintage and
    artifact references, the measure's column name and the charitable lines,
    every declaration equals the predecessor's."""
    old = _declarations(PREDECESSOR)
    new = _declarations(PACKAGE)
    old_set, new_set = old["record_sets"][0], new["record_sets"][0]

    assert {key: new[key] for key in ("schema_version", "dimension_labels")} == {
        key: old[key] for key in ("schema_version", "dimension_labels")
    }
    assert new["package_id"] == PACKAGE
    assert new["label"] == old["label"].replace("2024", "2025")
    edition = {
        "source_table": (
            "Estimates of Federal Tax Expenditures for Fiscal Years 2025-2029"
        ),
        "resource_directory": "data/jct/tax_expenditures_2025",
        "vintage": "jcx_45_25",
        "extracted_at": "2026-11-27",
        "extraction_method": old["artifact"]["extraction_method"].replace(
            "JCX-48-24", "JCX-45-25"
        ),
        "sheet_name": "jct_tax_expenditures_2025",
    }
    assert new["artifact"] == {**old["artifact"], **edition}
    relabelled = {
        "record_set_id": "jct.tax_expenditures.fy2025",
        "source_record_id_prefix": "jct.tax_expenditures.fy2025",
        "sheet_name": "jct_tax_expenditures_2025",
        "period": 2025,
    }
    for key in set(old_set) - {"rows", "measures"}:
        assert new_set[key] == relabelled.get(key, old_set[key]), key
    assert set(new_set) == set(old_set)

    # One measure: only the CSV column's name carries the year.
    (old_measure,), (new_measure,) = old_set["measures"], new_set["measures"]
    year_named = {"source_column_id", "expected_column_header"}
    for key, value in old_measure.items():
        expected = value.replace("2024", "2025") if key in year_named else value
        assert new_measure[key] == expected, key
    assert set(new_measure) == set(old_measure)

    # Rows: the ten shared lines keep every declaration except their position;
    # the predecessor's one summed charitable row becomes the three lines.
    def by_id(record_set):
        return {row["value_id"]: row for row in record_set["rows"]}

    old_rows, new_rows = by_id(old_set), by_id(new_set)
    assert set(old_rows) - set(new_rows) == {"charitable_deduction"}
    assert set(new_rows) - set(old_rows) == set(CHARITABLE_ROWS)
    position = {"ordinal", "row_number"}
    for value_id in set(old_rows) & set(new_rows):
        assert {k: v for k, v in new_rows[value_id].items() if k not in position} == {
            k: v for k, v in old_rows[value_id].items() if k not in position
        }, value_id
    template = old_rows["charitable_deduction"]
    for value_id in CHARITABLE_ROWS:
        row = new_rows[value_id]
        assert set(row) == set(template)
        assert row["label"].startswith("Charitable contribution deduction, ")
        assert row["expected_row_header"] == value_id
        assert row["filters"] == {"tax_expenditure": value_id}
        assert row["constraints"] == [{**template["constraints"][0], "value": value_id}]
        assert row["table_record_kind"] == template["table_record_kind"]
    assert [row["ordinal"] for row in new_set["rows"]] == list(range(13))
    assert [row["row_number"] for row in new_set["rows"]] == list(range(2, 15))
    assert [row["value_id"] for row in new_set["rows"]] == list(TABLE_1_ROWS)
