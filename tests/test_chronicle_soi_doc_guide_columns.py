"""IRS SOI geographic-file measures read the column their documentation guide defines.

Historic Table 2, the congressional-district file and the county file publish
one CSV column per IRS variable (``N18460``, ``A18460``, ...). Each file's
documentation guide defines every variable with a description and a form line.
``GUIDE_DEFINITIONS`` pins every ``measure_id`` those packages declare to one
guide definition, and the tests below check that every package, in any vintage,
reads the one column that definition names. Extracts of the guides live in
``tests/data/irs_soi_doc_guides``; each records its irs.gov URL and sha256.

Four mappings broke this rule until they were fixed together:

- ``congressional_district_2022`` ``limited_state_local_taxes_*`` read
  ``N18425``/``A18425``, "State and local income taxes" (Schedule A line 5a),
  instead of ``N18460``/``A18460``, "Limited state and local taxes" (line 5e).
  Historic Table 2 already read line 5e.
- The same package's ``premium_tax_credit_*`` read ``N85530``/``A85530``,
  "Additional Medicare tax" (Form 8959 line 24), instead of
  ``N85770``/``A85770``, "Total premium tax credit", which Historic Table 2
  already read.
- The same package's ``interest_paid_deduction_*`` read ``N19300``/``A19300``,
  "Mortgage interest paid" (Schedule A line 8a). Table 2.1 uses that measure id
  for the line 10 total, which no geographic file publishes. The line 8a
  columns are now ``mortgage_interest_paid_*``, Table 2.1's line 8a ids, next
  to new line 8b, 8c and 9 measures.
- ``historic_table_2`` and ``historic_table_2_state_broad_2022`` ``qbi_*`` read
  ``N03270``/``A03270``, "Self-employment health insurance deduction", instead
  of ``N04475``/``A04475``, "Qualified business income deduction".

``docs/concept-migrations.md`` records the change.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest
import yaml

from chronicle.source_package import load_source_package
from chronicle.sources.specs import compile_source_record_set_specs

REPO_ROOT = Path(__file__).resolve().parents[1]
IRS_SOI_PACKAGES = REPO_ROOT / "packages" / "irs_soi"
GUIDE_DIR = Path(__file__).resolve().parent / "data" / "irs_soi_doc_guides"
IRS_VARIABLE = re.compile(r"^[NA]\d+$")

# The guide extract that documents each data file a package reads.
GUIDE_BY_DATA_FILE = {
    "22incd.csv": "22incddocguide",
    "22incyallnoagi.csv": "22incydocguide",
    "22in55cmcsv.csv": "22incmdocguide",
    "23in55cmcsv.csv": "23incmdocguide",
}

# IRS-variable columns a data file carries that its guide does not define.
# No package may read them.
UNDOCUMENTED_COLUMNS = {
    "22incd.csv": frozenset({"A00101"}),
    "22incyallnoagi.csv": frozenset({"A00101"}),
}

# The TY2022 guides print form "8926" for these variables; the TY2023 Historic
# Table 2 guide prints "8962" for the same variables and descriptions.
LINE_ERRATA = {"8926:24": "8962:24", "8926:25": "8962:25"}

# measure_id -> (form line, guide description, later guide wordings ...).
# Descriptions are the TY2022 guide wording and match case-insensitively; each
# must name exactly one variable in every guide a package reads.
GUIDE_DEFINITIONS: dict[str, tuple[str, ...]] = {
    "return_count": ("", "Number of returns"),
    "tax_filer_individual_count": ("", "Number of individuals"),
    "adjusted_gross_income": ("1040:11", "Adjust gross income (AGI)"),
    "total_income_returns": ("1040:9", "Number of returns with total income"),
    "total_income_amount": ("1040:9", "Total income amount"),
    "wages_salaries_returns": ("1040:1z", "Number of returns with salaries and wages"),
    "wages_salaries_amount": ("1040:1z", "Salaries and wages amount"),
    "taxable_interest_returns": ("1040:2b", "Number of returns with taxable interest"),
    "taxable_interest_amount": ("1040:2b", "Taxable interest amount"),
    "tax_exempt_interest_returns": ("1040:2a", "Number of returns tax-exempt interest"),
    "tax_exempt_interest_amount": ("1040:2a", "Tax-exempt interest amount"),
    "ordinary_dividends_returns": (
        "1040:3b",
        "Number of returns with ordinary dividends",
    ),
    "ordinary_dividends_amount": ("1040:3b", "Ordinary dividends amount"),
    "qualified_dividends_returns": (
        "1040:3a",
        "Number of returns with qualified dividends",
    ),
    "qualified_dividends_amount": ("1040:3a", "Qualified dividends amount"),
    "schedule_c_income_returns": (
        "Schedule 1:3",
        "Number of returns with business or professional net income (less loss)",
    ),
    "schedule_c_income_amount": (
        "Schedule 1:3",
        "Business or professional net income (less loss) amount",
    ),
    "net_capital_gains_returns": (
        "1040:7",
        "Number of returns with net capital gain (less loss)",
    ),
    "net_capital_gains_amount": ("1040:7", "Net capital gain (less loss) amount"),
    "taxable_ira_distributions_returns": (
        "1040:4b",
        (
            "Number of returns with taxable individual retirement arrangements "
            "distributions"
        ),
    ),
    "taxable_ira_distributions_amount": (
        "1040:4b",
        "Taxable individual retirement arrangements distributions amount",
    ),
    "taxable_pension_income_returns": (
        "1040:5b",
        "Number of returns with taxable pensions and annuities",
    ),
    "taxable_pension_income_amount": (
        "1040:5b",
        "Taxable pensions and annuities amount",
    ),
    "unemployment_compensation_returns": (
        "Schedule 1:7",
        "Number of returns with unemployment compensation",
    ),
    "unemployment_compensation_amount": (
        "Schedule 1:7",
        "Unemployment compensation amount",
    ),
    "taxable_social_security_returns": (
        "1040:6b",
        "Number of returns with taxable Social Security benefits",
    ),
    "taxable_social_security_amount": (
        "1040:6b",
        "Taxable Social Security benefits amount",
    ),
    "partnership_scorp_income_returns": (
        "Schedule E:32",
        "Number of returns with partnership/S-corp net income (less loss)",
    ),
    "partnership_scorp_income_amount": (
        "Schedule E:32",
        "Partnership/S-corp net income (less loss) amount",
    ),
    "rental_royalty_income_returns": (
        "Schedule E:26",
        "Number of returns with total rental and royalty net income (less loss)",
    ),
    "rental_royalty_income_amount": (
        "Schedule E:26",
        "Total rental and royalty net income (less loss)",
    ),
    "itemized_deductions_returns": (
        "1040:12",
        "Number of returns with itemized deductions",
    ),
    "itemized_deductions_amount": ("1040:12", "Total itemized deductions amount"),
    "medical_dental_expense_returns": (
        "Schedule A:4",
        "Number of returns with Total medical and dental expense deduction",
    ),
    "medical_dental_expense_amount": (
        "Schedule A:4",
        "Total medical and dental expense deduction amount",
    ),
    "real_estate_taxes_claims": (
        "Schedule A:5b",
        "Number of returns with real estate taxes",
    ),
    "real_estate_taxes_amount": ("Schedule A:5b", "Real estate taxes amount"),
    "limited_state_local_taxes_returns": (
        "Schedule A:5e",
        "Number of returns with Limited state and local taxes",
    ),
    "limited_state_local_taxes_amount": (
        "Schedule A:5e",
        "Limited state and local taxes",
    ),
    "mortgage_interest_paid_returns": (
        "Schedule A:8a",
        "Number of returns with mortgage interest paid",
    ),
    "mortgage_interest_paid_amount": ("Schedule A:8a", "Mortgage interest paid amount"),
    "home_mortgage_personal_seller_returns": (
        "Schedule A:8b",
        "Number of returns with Home mortgage from personal seller",
    ),
    "home_mortgage_personal_seller_amount": (
        "Schedule A:8b",
        "Home mortgage from personal seller amount",
    ),
    "deductible_points_returns": (
        "Schedule A:8c",
        "Number of returns with Deductible points",
    ),
    "deductible_points_amount": ("Schedule A:8c", "Deductible points amount"),
    "investment_interest_paid_returns": (
        "Schedule A:9",
        "Number of returns with Investment interest paid",
    ),
    "investment_interest_paid_amount": (
        "Schedule A:9",
        "Investment interest paid amount",
    ),
    "charitable_returns": (
        "Schedule A:14",
        "Number of returns with Total charitable contributions",
    ),
    "charitable_amount": ("Schedule A:14", "Total charitable contributions amount"),
    "qbi_claims": (
        "1040:13",
        "Number of returns with Qualified business income deduction",
    ),
    "qbi_amount": ("1040:13", "Qualified business income deduction amount"),
    "qualified_business_income_deduction_returns": (
        "1040:13",
        "Number of returns with Qualified business income deduction",
    ),
    "qualified_business_income_deduction_amount": (
        "1040:13",
        "Qualified business income deduction amount",
    ),
    "taxable_income_returns": ("1040:15", "Number of returns with taxable income"),
    "taxable_income_amount": ("1040:15", "Taxable income amount"),
    "income_tax_before_credits_returns": (
        "1040:16",
        "Number of returns with income tax before credits",
    ),
    "income_tax_before_credits_amount": ("1040:16", "Income tax before credits amount"),
    "ctc_claims": (
        "1040:19",
        "Number of returns with nonrefundable child and other dependent tax credit",
    ),
    "ctc_amount": (
        "1040:19",
        "Nonrefundable child and other dependent tax credit amount",
    ),
    "premium_tax_credit_returns": (
        "8962:24",
        "Number of returns with total premium tax credit",
    ),
    "premium_tax_credit_amount": ("8962:24", "Total premium tax credit amount"),
    "eitc_claims": ("1040:27", "Number of returns with earned income credit"),
    "eitc_amount": ("1040:27", "Earned income credit amount"),
    "eitc_no_children_claims": (
        "1040:27",
        "Number of returns with earned income credit with no qualifying children",
    ),
    "eitc_no_children_amount": (
        "1040:27",
        "Earned income credit with no qualifying children amount",
    ),
    "eitc_one_child_claims": (
        "1040:27",
        "Number of returns with earned income credit with one qualifying child",
    ),
    "eitc_one_child_amount": (
        "1040:27",
        "Earned income credit with one qualifying child amount",
    ),
    "eitc_two_children_claims": (
        "1040:27",
        "Number of returns with earned income credit with two qualifying children",
    ),
    "eitc_two_children_amount": (
        "1040:27",
        "Earned income credit with two qualifying children amount",
    ),
    # The guides say "three"; these ids and their labels say "three or more".
    "eitc_three_or_more_children_claims": (
        "1040:27",
        "Number of returns with earned income credit with three qualifying children",
    ),
    "eitc_three_or_more_children_amount": (
        "1040:27",
        "Earned income credit with three qualifying children amount",
    ),
    "actc_claims": (
        "1040:28",
        (
            "Number of returns with refundable child tax credit or additional "
            "child tax credit"
        ),
        "Number of returns with additional child tax credit",  # TY2023 guide
    ),
    "actc_amount": (
        "1040:28",
        "Refundable child tax credit or additional child tax credit amount",
        "Additional child tax credit amount",  # TY2023 guide
    ),
    "income_tax_liability_returns": (
        "1040:22",
        "Number of returns with income tax after credits",
    ),
    "income_tax_liability_amount": ("1040:22", "Income tax after credits amount"),
}

# Measure ids that mean a line no geographic file publishes. No package that
# reads an IRS-variable file may declare them.
NOT_IN_GEOGRAPHIC_FILES = {
    "interest_paid_deduction_returns": (
        "Table 2.1's Schedule A line 10 interest paid deduction; the geographic "
        "files publish only its parts N19300 (8a), N19500 (8b), N19530 (8c) and "
        "N19570 (9)"
    ),
    "interest_paid_deduction_amount": (
        "Table 2.1's Schedule A line 10 interest paid deduction; the geographic "
        "files publish only its parts A19300 (8a), A19500 (8b), A19530 (8c) and "
        "A19570 (9)"
    ),
}


@dataclass(frozen=True)
class ColumnRead:
    """One distinct cell selector of a package that reads an IRS-variable file.

    Built from the compiled source-record specs, so a row-level ``column``,
    ``source_column_id`` or header guard counts the way the build reads it
    (``row.column or measure.column``).
    """

    package_dir: str
    measure_id: str
    data_file: str
    data_path: Path
    column: str
    header: str
    declared: tuple[Any, ...]
    header_guard_address: str | None
    expected_header_address: str
    divisor_column: str | None
    concept: str
    label: str
    example_record: str


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _column_index(letters: str) -> int:
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - ord("A") + 1
    return index - 1


@cache
def _guide(stem: str) -> dict[str, tuple[str, str]]:
    path = GUIDE_DIR / f"{stem}.tsv"
    lines = [line for line in path.read_text().splitlines() if not line.startswith("#")]
    reader = csv.DictReader(lines, delimiter="\t")
    assert reader.fieldnames == ["variable", "description", "line_reference"]
    guide: dict[str, tuple[str, str]] = {}
    for row in reader:
        assert IRS_VARIABLE.match(row["variable"]), (stem, row)
        assert row["variable"] not in guide, (stem, row["variable"])
        guide[row["variable"]] = (row["description"], row["line_reference"])
    return guide


def _artifact_file(artifact: dict[str, Any]) -> tuple[str, Path]:
    root = files(artifact["resource_package"]).joinpath(artifact["resource_directory"])
    manifest = yaml.safe_load(root.joinpath(artifact["manifest"]).read_text())
    spec = manifest["files"][artifact["artifact_year"]]
    return spec["filename"], Path(str(root.joinpath(spec["filename"])))


@cache
def _header(path: Path) -> tuple[str, ...]:
    with path.open("rb") as file:
        first_line = file.readline().decode("utf-8-sig")
    return tuple(next(csv.reader([first_line])))


CELL_ADDRESS = re.compile(r"^([A-Z]+)(\d+)$")


def _package_reads(path: Path, package_dir: str) -> tuple[ColumnRead, ...] | None:
    """Every distinct selector a package compiles, or None for other parsers."""
    payload = yaml.safe_load(path.read_text())
    artifact = payload["artifact"]
    if artifact.get("parser") != "delimited_text_full_rows":
        return None
    assert artifact.get("artifact_year"), (
        f"{package_dir}: a delimited IRS package without artifact_year can read "
        "a different file per year; extend this test to check each"
    )
    data_file, data_path = _artifact_file(artifact)
    header = _header(data_path)
    header_row = artifact.get("header_row", 1)
    package = load_source_package(path)
    reads: dict[tuple[Any, ...], ColumnRead] = {}
    year = artifact["artifact_year"]
    for record_set in package.build_source_record_set_specs(year):
        rows = {row.value_id: row for row in record_set.rows}
        measures = {measure.measure_id: measure for measure in record_set.measures}
        for spec in compile_source_record_set_specs(record_set):
            selector, layout = spec.selector, spec.layout
            match = CELL_ADDRESS.match(selector.address)
            assert match, spec.source_record_id
            column = match.group(1)
            # A row range (Historic Table 2 state AGI bands sum adjacent stubs)
            # must stay in one column.
            if selector.end_address is not None:
                end = CELL_ADDRESS.match(selector.end_address)
                assert end and end.group(1) == column, spec.source_record_id
            # The column id the package declares, row before measure, as the
            # build resolves it. Without one the layout repeats the measure id,
            # which is not a declaration.
            declared_id = (
                rows[layout.groupby_value_id].source_column_id
                or measures[layout.measure_id].source_column_id
            )
            declared = tuple(
                value
                for value in (declared_id, selector.expected_column_header)
                if value is not None
            )
            divisor = spec.divisor_selector
            read = ColumnRead(
                package_dir=package_dir,
                measure_id=layout.measure_id,
                data_file=data_file,
                data_path=data_path,
                column=column,
                header=header[_column_index(column)],
                declared=declared,
                header_guard_address=(
                    selector.expected_column_header_address
                    if selector.expected_column_header is not None
                    else None
                ),
                expected_header_address=f"{column}{header_row}",
                divisor_column=(
                    CELL_ADDRESS.match(divisor.address).group(1)
                    if divisor is not None
                    else None
                ),
                concept=spec.concept,
                label=layout.measure_label,
                example_record=spec.source_record_id,
            )
            # Every field but the example record: two selectors that differ in
            # anything checked below both stay.
            key = (
                read.measure_id,
                read.column,
                read.declared,
                read.header_guard_address,
                read.divisor_column,
                read.concept,
                read.label,
            )
            reads.setdefault(key, read)
    return tuple(reads.values())


@cache
def _column_reads() -> tuple[ColumnRead, ...]:
    reads: list[ColumnRead] = []
    for path in sorted(IRS_SOI_PACKAGES.glob("*/source_package.yaml")):
        package_reads = _package_reads(path, path.parent.name)
        if package_reads is not None:
            reads.extend(package_reads)
    return tuple(reads)


def _defined_variable(measure_id: str, guide_stem: str) -> str | None:
    wordings = {_normalize(text) for text in GUIDE_DEFINITIONS[measure_id][1:]}
    matches = [
        variable
        for variable, (description, _line) in _guide(guide_stem).items()
        if _normalize(description) in wordings
    ]
    assert len(matches) <= 1, (measure_id, guide_stem, matches)
    return matches[0] if matches else None


def test_irs_variable_packages_are_found():
    packages = {read.package_dir for read in _column_reads()}

    assert {
        "congressional_district_2022",
        "county_2022",
        "historic_table_2",
        "historic_table_2_state_agi_2022",
        "historic_table_2_state_agi_2023",
        "historic_table_2_state_broad_2022",
        "historic_table_2_state_eitc_2022",
    } <= packages
    assert all(IRS_VARIABLE.match(read.header) for read in _column_reads())


def test_guide_extracts_define_every_column_their_files_publish():
    data_files = {read.data_file for read in _column_reads()}
    assert data_files <= set(GUIDE_BY_DATA_FILE), sorted(data_files)

    for data_file in sorted(data_files):
        path = next(
            read.data_path for read in _column_reads() if read.data_file == data_file
        )
        published = {name for name in _header(path) if IRS_VARIABLE.match(name)}
        documented = set(_guide(GUIDE_BY_DATA_FILE[data_file]))
        undocumented = UNDOCUMENTED_COLUMNS.get(data_file, frozenset())

        assert published - documented == undocumented, data_file
        assert documented <= published, data_file


def test_guide_descriptions_name_one_variable_each():
    for stem in sorted(set(GUIDE_BY_DATA_FILE.values())):
        by_description: dict[str, list[str]] = defaultdict(list)
        for variable, (description, _line) in _guide(stem).items():
            by_description[_normalize(description)].append(variable)

        assert {
            description: variables
            for description, variables in by_description.items()
            if len(variables) > 1
        } == {}, stem


def test_every_definition_names_the_same_variable_in_every_guide():
    for measure_id in sorted(GUIDE_DEFINITIONS):
        variables = {
            stem: _defined_variable(measure_id, stem)
            for stem in sorted(set(GUIDE_BY_DATA_FILE.values()))
        }
        named = set(variables.values()) - {None}

        assert len(named) == 1, (measure_id, variables)


def _column_read_failures(reads: tuple[ColumnRead, ...]) -> list[str]:
    failures = []
    meanings: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for read in reads:
        meanings[(read.package_dir, read.measure_id)].add((read.concept, read.label))
    for (package_dir, measure_id), declared in sorted(meanings.items()):
        if len(declared) > 1:
            failures.append(
                f"{package_dir}:{measure_id} declares more than one concept or "
                f"label: {sorted(declared)}"
            )
    for read in reads:
        where = (
            f"{read.package_dir}:{read.measure_id} (column {read.column}, "
            f"e.g. {read.example_record})"
        )
        if read.measure_id in NOT_IN_GEOGRAPHIC_FILES:
            failures.append(
                f"{where} reads {read.header}, but the id means "
                f"{NOT_IN_GEOGRAPHIC_FILES[read.measure_id]}"
            )
            continue
        if read.measure_id not in GUIDE_DEFINITIONS:
            failures.append(
                f"{where} reads {read.header} and has no GUIDE_DEFINITIONS entry; "
                "pin it to the guide description of the column it should read"
            )
            continue
        if any(declared != read.header for declared in read.declared):
            failures.append(
                f"{where} declares {read.declared}, header is {read.header}"
            )
        if read.divisor_column is not None:
            failures.append(
                f"{where} divides by column {read.divisor_column}; these packages "
                "publish levels, so extend this test before adding a divisor"
            )
        if read.header_guard_address not in {None, read.expected_header_address}:
            failures.append(
                f"{where} guards header cell {read.header_guard_address}, not "
                f"{read.expected_header_address}"
            )
        guide_stem = GUIDE_BY_DATA_FILE[read.data_file]
        guide = _guide(guide_stem)
        if read.header not in guide:
            failures.append(f"{where} reads {read.header}, which {guide_stem} omits")
            continue
        expected = _defined_variable(read.measure_id, guide_stem)
        description, line = guide[read.header]
        if read.header != expected:
            failures.append(
                f"{where} reads {read.header} ({description!r}, {line}); "
                f"{guide_stem} defines {read.measure_id} as {expected}"
            )
            continue
        if LINE_ERRATA.get(line, line) != GUIDE_DEFINITIONS[read.measure_id][0]:
            failures.append(f"{where}: {guide_stem} puts {read.header} on line {line}")
    return failures


def test_every_measure_reads_the_column_its_guide_definition_names():
    assert _column_read_failures(_column_reads()) == []


def _move_a_row_to_agi(payload: dict[str, Any]) -> None:
    # The build reads ``row.column or measure.column``, so one row can move
    # every measure in it to another column.
    row = payload["record_sets"][0]["rows"][1]
    assert row["value_id"] == "under_1"
    row["column"] = "T"  # A00100, adjusted gross income


def _declare_the_measure_id_as_column_id(payload: dict[str, Any]) -> None:
    # Indistinguishable in the layout from the fallback for no declaration.
    _ht2_measure(payload, "return_count")["source_column_id"] = "return_count"


def _divide_by_agi(payload: dict[str, Any]) -> None:
    _ht2_measure(payload, "return_count")["divisor_column"] = "T"


def _relabel_in_a_second_record_set(payload: dict[str, Any]) -> None:
    record_set = deepcopy(payload["record_sets"][0])
    for key in ("record_set_id", "record_set_spec_id", "source_record_id_prefix"):
        record_set[key] += "_copy"
    _ht2_measure({"record_sets": [record_set]}, "qbi_amount")["concept"] = (
        "irs_soi.self_employed_health_insurance_deduction"
    )
    payload["record_sets"].append(record_set)


def _ht2_measure(payload: dict[str, Any], measure_id: str) -> dict[str, Any]:
    return next(
        measure
        for measure in payload["record_sets"][0]["measures"]
        if measure["measure_id"] == measure_id
    )


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            _move_a_row_to_agi,
            "historic_table_2:return_count (column T, e.g. "
            "irs_soi.ty2022.historic_table_2.us.under_1.return_count) reads A00100",
        ),
        (
            _declare_the_measure_id_as_column_id,
            "historic_table_2:return_count (column C, e.g. "
            "irs_soi.ty2022.historic_table_2.us.all.return_count) declares "
            "('return_count',), header is N1",
        ),
        (
            _divide_by_agi,
            "historic_table_2:return_count (column C, e.g. "
            "irs_soi.ty2022.historic_table_2.us.all.return_count) divides by column T",
        ),
        (
            _relabel_in_a_second_record_set,
            "historic_table_2:qbi_amount declares more than one concept or label",
        ),
    ],
)
def test_package_mutations_are_caught(tmp_path, mutate, expected):
    """Each mutation compiles, so only this module's checks can catch it."""
    source = IRS_SOI_PACKAGES / "historic_table_2" / "source_package.yaml"
    payload = yaml.safe_load(source.read_text())
    mutate(payload)
    path = tmp_path / "historic_table_2" / "source_package.yaml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump(payload, sort_keys=False))

    failures = _column_read_failures(_package_reads(path, "historic_table_2"))

    assert _column_read_failures(_package_reads(source, "historic_table_2")) == []
    assert any(failure.startswith(expected) for failure in failures), failures


def test_measure_ids_shared_across_packages_read_one_column():
    headers: dict[str, set[str]] = defaultdict(set)
    packages: dict[str, set[str]] = defaultdict(set)
    for read in _column_reads():
        headers[read.measure_id].add(read.header)
        packages[read.measure_id].add(read.package_dir)
    shared = {measure_id for measure_id, dirs in packages.items() if len(dirs) > 1}

    assert {
        "limited_state_local_taxes_amount",
        "premium_tax_credit_amount",
        "return_count",
    } <= shared
    assert {
        measure_id: sorted(headers[measure_id])
        for measure_id in shared
        if len(headers[measure_id]) > 1
    } == {}


def test_guide_definitions_have_no_stale_entries():
    read_ids = {read.measure_id for read in _column_reads()}

    assert set(GUIDE_DEFINITIONS) - read_ids == set()
    assert set(GUIDE_DEFINITIONS) & set(NOT_IN_GEOGRAPHIC_FILES) == set()


def test_line_10_interest_paid_ids_keep_their_table_2_1_meaning():
    table_2_1 = yaml.safe_load(
        (IRS_SOI_PACKAGES / "table_2_1" / "source_package.yaml").read_text()
    )
    table_2_1_ids = {
        measure["measure_id"]
        for record_set in table_2_1["record_sets"]
        for measure in record_set["measures"]
    }

    assert set(NOT_IN_GEOGRAPHIC_FILES) <= table_2_1_ids
    assert not {read.measure_id for read in _column_reads()} & set(
        NOT_IN_GEOGRAPHIC_FILES
    )


SCHEDULE_A_INTEREST_PARTS = (
    "mortgage_interest_paid",  # line 8a
    "home_mortgage_personal_seller",  # line 8b
    "deductible_points",  # line 8c
    "investment_interest_paid",  # line 9
)


def test_congressional_district_interest_parts_share_table_2_1_ids():
    table_2_1 = {
        measure["measure_id"]: measure
        for record_set in yaml.safe_load(
            (IRS_SOI_PACKAGES / "table_2_1" / "source_package.yaml").read_text()
        )["record_sets"]
        for measure in record_set["measures"]
    }
    district = {
        read.measure_id: read
        for read in _column_reads()
        if read.package_dir == "congressional_district_2022"
    }

    for part in SCHEDULE_A_INTEREST_PARTS:
        for suffix in ("returns", "amount"):
            measure_id = f"{part}_{suffix}"
            assert district[measure_id].concept == table_2_1[measure_id]["concept"]
            assert district[measure_id].label == table_2_1[measure_id]["label"]


@cache
def _facts(package_id: str, year: int) -> dict[str, Any]:
    package = load_source_package(package_id)
    return {fact.source_record_id: fact for fact in package.build_facts(year)}


def _us_values(package_id: str, prefix: str) -> dict[str, float]:
    return {
        record_id.removeprefix(prefix): fact.value
        for record_id, fact in _facts(package_id, 2022).items()
        if record_id.startswith(prefix)
    }


# Historic Table 2 and the congressional-district file use different ids for
# the qualified business income deduction columns.
HT2_TO_DISTRICT_IDS = {
    "qbi_claims": "qualified_business_income_deduction_returns",
    "qbi_amount": "qualified_business_income_deduction_amount",
}


def test_congressional_district_us_row_is_a_subset_of_historic_table_2():
    """Differential check of the two TY2022 IRS tabulations of one population.

    The district file drops returns without a ZIP code that matches the state,
    and it suppresses small cells, so its US row should not exceed Historic
    Table 2's. Every TY2022 ratio lies in [0.92, 0.99]. The columns the
    district package used to read gave 2.04 (SALT amount), 0.72 (SALT returns),
    0.87 and 0.26 (PTC returns and amount), and the district QBI deduction was
    6.65 times what Historic Table 2's ``qbi_amount`` read.
    """
    district = _us_values(
        "soi-congressional-district-2022",
        "irs_soi.ty2022.congressional_district_2022.all_returns.us.",
    )
    ht2 = _us_values("soi-historic-table-2", "irs_soi.ty2022.historic_table_2.us.all.")
    pairs = {
        measure_id: (district[HT2_TO_DISTRICT_IDS.get(measure_id, measure_id)], value)
        for measure_id, value in ht2.items()
        if HT2_TO_DISTRICT_IDS.get(measure_id, measure_id) in district
    }

    assert {
        "limited_state_local_taxes_returns",
        "limited_state_local_taxes_amount",
        "premium_tax_credit_returns",
        "premium_tax_credit_amount",
        "qbi_claims",
        "qbi_amount",
    } <= set(pairs)
    assert len(pairs) == 44
    assert {
        measure_id: round(cd / ht2_value, 4)
        for measure_id, (cd, ht2_value) in pairs.items()
        if not 0.90 <= cd / ht2_value <= 1.0
    } == {}


def test_district_interest_parts_match_table_2_1_lines_8a_and_10():
    """Differential check of the line 8a relabel against Publication 1304.

    Schedule A (2022) line 10 adds lines 8e and 9, and line 8e adds lines 8a
    through 8c (8d is reserved). The district's line 8a column is close to
    Table 2.1's line 8a, well short of its line 10 total, and the four parts
    together come close to line 10.
    """
    district = _us_values(
        "soi-congressional-district-2022",
        "irs_soi.ty2022.congressional_district_2022.all_returns.us.",
    )
    table_2_1 = _us_values(
        "soi-table-2-1", "irs_soi.ty2022.table_2_1.itemized_all_returns.all."
    )
    line_8a = district["mortgage_interest_paid_amount"]
    parts = sum(district[f"{part}_amount"] for part in SCHEDULE_A_INTEREST_PARTS)

    assert line_8a / table_2_1["mortgage_interest_paid_amount"] == pytest.approx(
        0.984, abs=0.001
    )
    assert line_8a / table_2_1["interest_paid_deduction_amount"] < 0.85
    assert parts / table_2_1["interest_paid_deduction_amount"] == pytest.approx(
        0.960, abs=0.001
    )


@pytest.mark.parametrize(
    ("package_id", "year"),
    [
        ("soi-congressional-district-2022", 2022),
        ("soi-historic-table-2", 2022),
        ("soi-historic-table-2-state-broad-2022", 2022),
        ("soi-table-2-1", 2022),
        ("soi-table-2-1", 2023),
    ],
)
def test_limited_salt_amounts_respect_the_10000_cap(package_id, year):
    """Schedule A (2022) line 5e is the smaller of line 5d or $10,000.

    Each return's limited SALT is at most $10,000, so a row's amount is at most
    $10,000 times its returns. The geographic files round return counts to the
    nearest ten and every package publishes amounts in thousands, so the bound
    allows five more returns and $500. Line 5a, which the district package used
    to read, averaged $23,098 a return for the US; the highest average on the
    corrected columns is $9,820.
    """
    by_row: dict[str, dict[str, float]] = defaultdict(dict)
    for record_id, fact in _facts(package_id, year).items():
        row, measure_id = record_id.rsplit(".", 1)
        if measure_id.startswith("limited_state_local_taxes_"):
            by_row[row][measure_id] = fact.value

    assert by_row
    for row, values in by_row.items():
        returns = values["limited_state_local_taxes_returns"]
        amount = values["limited_state_local_taxes_amount"]
        assert amount <= 10_000 * (returns + 5) + 500, (row, amount, returns)
