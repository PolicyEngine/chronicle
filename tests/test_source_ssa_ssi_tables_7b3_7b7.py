"""Fidelity and invariant tests for SSA Supplement 2025 Tables 7.B3 and 7.B7.

Both packages read SSA's section 7.B workbook (``7b.xlsx``), the file the
Table 7.B1 package pins. Sheet 7.B3 gives December 2024 recipients and average
monthly payments by type of payment; sheet 7.B7 gives calendar 2024 payment
amounts. These tests check every emitted fact against the Wayback capture of
the 7.B web page, parsed here with the standard-library HTML parser, and check
the two tables against each other and against Table 7.B1.
"""

from __future__ import annotations

from dataclasses import replace
from functools import cache
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import runpy

import pytest
import yaml

from chronicle.bundle import DEFAULT_BUNDLE_SOURCES
from chronicle.consumer_contract import (
    build_aggregate_fact_key,
    build_semantic_fact_key,
    consumer_fact_rows,
)
from chronicle.core import PeriodCoverage, PeriodDimension
from chronicle.dimension_labels import dimension_label_issues
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package

REPO = Path(__file__).resolve().parents[1]
RESOURCES = REPO / "db/data/ssa/ssi_table_7b1_2024"
REGISTER = REPO / "chronicle/dimension_values/canonical_labels.json"
MONTHLY_STATISTICS = "packages/ssa/ssi_monthly_statistics_2024_12"
YEAR = 2024

XLSX_SHA256 = "6363d2efb1e9f76a672ef380ad41e6a2426ebe63c86a31d5dd78534a3aa31bd6"

PACKAGES = {
    "7.B3": ("ssa-ssi-table-7b3-2024", "packages/ssa/ssi_table_7b3_2024"),
    "7.B7": ("ssa-ssi-table-7b7-2024", "packages/ssa/ssi_table_7b7_2024"),
}
# The published columns after each area label, in workbook order.
COLUMNS = {"7.B1": "DEFGHIJK", "7.B3": "DEFG", "7.B7": "DEF"}
# Record-set token -> (sheet, workbook column, unit scale).
MEASURES = {
    "ssi_federal_payment_recipients": ("7.B3", "D", 1),
    "ssi_federal_average_monthly_payment": ("7.B3", "E", 1),
    "ssi_state_supplementation_recipients": ("7.B3", "F", 1),
    "ssi_state_supplementation_average_monthly_payment": ("7.B3", "G", 1),
    "ssi_federal_payments": ("7.B7", "E", 1000),
    "ssi_state_supplementation_payments": ("7.B7", "F", 1000),
}
# Record-set token -> the measure label its package gives it.
MEASURE_LABELS = {
    "ssi_federal_payment_recipients": "Federal SSI recipients",
    "ssi_federal_average_monthly_payment": "Federal SSI average monthly payment",
    "ssi_state_supplementation_recipients": (
        "Federally administered state supplementation recipients"
    ),
    "ssi_state_supplementation_average_monthly_payment": (
        "Federally administered state supplementation average monthly payment"
    ),
    "ssi_federal_payments": "Federal SSI payments",
    "ssi_state_supplementation_payments": (
        "Federally administered state supplementation payments"
    ),
}
# The All-areas row of each sheet. The 50 states and DC follow it, then an
# "Outlying area" heading and the Northern Mariana Islands.
ALL_AREAS_ROW = {"7.B3": 5, "7.B7": 4}
OUTLYING_AREA = "Northern Mariana Islands"
LABEL_COLUMN = {"All areas": "C", OUTLYING_AREA: "B"}
NOT_APPLICABLE = ". . ."
STATE_FIPS = {
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12", "13", "15",
    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
    "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "40", "41", "42", "44", "45", "46", "47", "48", "49", "50", "51", "53",
    "54", "55", "56",
}  # fmt: skip

# sha256 of the sorted "source_record_id<TAB>semantic_fact_key" lines of both
# packages. A change to a record-set id, value id, measure or concept moves it.
SEMANTIC_IDENTITY_DIGEST = (
    "f23a4f74480fa736da9e2674572a80b9cbfda417ee320d7ef6b0e62e599d1421"
)
# The same lines with each fact's aggregate_fact_key. That key hashes the
# source release, the source series and the observed measure, which the
# semantic key leaves out, so a wrong source table, vintage or source concept
# moves this digest while the semantic one holds. The aggregate key hashes each
# measure's source concept in place of its canonical concept, which only the
# semantic pin guards.
AGGREGATE_IDENTITY_DIGEST = (
    "c842bb741d1a2e8829f1ecfc47f8717dfaa07220e809894959795aaf37c14373"
)


class _TableParser(HTMLParser):
    """Collect the cell text of every row of the first table after an element id."""

    def __init__(self, element_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.element_id = element_id
        self.rows: list[list[str]] = []
        self._armed = False
        self._done = False
        self._table_depth = 0
        self._in_target = False
        self._cell: list[str] | None = None
        self._row: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if dict(attrs).get("id") == self.element_id:
            self._armed = True
        if tag == "table":
            if self._in_target:
                self._table_depth += 1
            elif self._armed and not self._done:
                self._in_target = True
                self._table_depth = 1
        if not self._in_target:
            return
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"}:
            self._cell = []

    def handle_endtag(self, tag):
        if not self._in_target:
            return
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._table_depth -= 1
            if self._table_depth == 0:
                self._in_target = False
                self._done = True

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _published_value(text: str) -> int | float | str:
    if re.fullmatch(r"\d{1,3}(,\d{3})*", text):
        return int(text.replace(",", ""))
    if re.fullmatch(r"\d+\.\d+", text):
        return float(text)
    return text


@cache
def published(table: str) -> dict[str, tuple[int | float | str, ...]]:
    """Area label -> published values, from the pinned HTML capture."""
    parser = _TableParser(f"table{table.lower()}")
    parser.feed((RESOURCES / "7b_wayback_20260101161547.html").read_text("utf-8"))
    width = len(COLUMNS[table])
    rows: dict[str, tuple[int | float | str, ...]] = {}
    for cells in parser.rows:
        if len(cells) != width + 1:
            continue
        values = tuple(_published_value(cell) for cell in cells[1:])
        if any(isinstance(value, (int, float)) for value in values):
            assert cells[0] not in rows, cells[0]
            rows[cells[0]] = values
    return rows


def _amount(value: int | float | str) -> int | float:
    """A published number, or zero where SSA prints ". . ." (not applicable)."""
    if isinstance(value, str):
        assert value == NOT_APPLICABLE, value
        return 0
    return value


@cache
def package_build(table: str):
    package = load_source_package(PACKAGES[table][1])
    cells = tuple(package.build_source_cells(YEAR))
    facts = tuple(package.build_facts(YEAR, cells=list(cells)))
    return package, cells, facts


def _grid(table: str) -> dict[str, object]:
    _, cells, _ = package_build(table)
    return {cell.address: cell.raw_value for cell in cells if cell.sheet_name == table}


def _area_rows(table: str) -> dict[str, int]:
    """Area label -> workbook row."""
    first = ALL_AREAS_ROW[table]
    rows = {"All areas": first, OUTLYING_AREA: first + 53}
    for offset, label in enumerate(list(published(table))[1:52]):
        rows[label] = first + 1 + offset
    return rows


def _token(fact) -> str:
    return fact.source_record_id.split(".")[2]


def _area(fact) -> str:
    return "All areas" if fact.geography.level == "country" else fact.geography.name


def _facts_by_measure() -> dict[tuple[str, str], object]:
    facts = {}
    for table in PACKAGES:
        for fact in package_build(table)[2]:
            key = (_token(fact), _area(fact))
            assert key not in facts, key
            facts[key] = fact
    return facts


def _spec(table: str) -> dict:
    path = REPO / PACKAGES[table][1] / "source_package.yaml"
    return yaml.safe_load(path.read_text("utf-8"))


def test_both_packages_read_the_workbook_the_table_7b1_package_pins():
    manifest = yaml.safe_load((RESOURCES / "manifest.yaml").read_text("utf-8"))
    assert manifest["files"][2024]["sha256"] == XLSX_SHA256
    for table, (package_id, _) in PACKAGES.items():
        spec = _spec(table)
        assert spec["package_id"] == package_id
        assert spec["artifact"]["resource_directory"] == "data/ssa/ssi_table_7b1_2024"
        assert spec["artifact"]["sheets"] == [table]
        for fact in package_build(table)[2]:
            assert fact.source.source_sha256 == XLSX_SHA256
            assert fact.source.raw_r2_uri.endswith(f"/2024/{XLSX_SHA256}/7b.xlsx")
            assert fact.source.url.endswith("/supplement/2025/7b.xlsx")


def test_html_capture_renders_both_tables_in_full():
    for table in PACKAGES:
        rows = published(table)
        assert len(rows) == 53
        assert list(rows)[0] == "All areas"
        assert list(rows)[-1] == OUTLYING_AREA
        assert "Outlying area" not in rows
    assert published("7.B3")["All areas"] == (
        7_289_843, 670.65, "a 1,327,153", "a 212.86",
    )  # fmt: skip
    assert published("7.B7")["All areas"] == (63_079_493, 59_665_127, 3_414_366)


@pytest.mark.parametrize("table", list(PACKAGES))
def test_workbook_and_html_capture_agree_on_every_published_cell(table):
    """Differential: every area cell of the sheet equals the HTML rendering."""
    grid = _grid(table)
    rows = published(table)
    compared = 0
    for label, row in _area_rows(table).items():
        assert grid[f"{LABEL_COLUMN.get(label, 'A')}{row}"] == label
        for index, column in enumerate(COLUMNS[table]):
            cell = grid.get(f"{column}{row}")
            if isinstance(cell, str):
                cell = " ".join(cell.split())
            assert cell == rows[label][index], (label, column)
            compared += 1
    assert compared == 53 * len(COLUMNS[table])


def test_every_fact_equals_its_published_cell():
    """For every emitted fact: value == published cell x unit scale, exactly."""
    checked = 0
    for table in PACKAGES:
        for fact in package_build(table)[2]:
            sheet, column, scale = MEASURES[_token(fact)]
            assert sheet == table
            cell = published(table)[_area(fact)][COLUMNS[table].index(column)]
            assert isinstance(cell, (int, float)), fact.source_record_id
            assert fact.value == cell * scale, fact.source_record_id
            checked += 1
    assert checked == 193


def test_facts_cover_every_numeric_area_cell_once_and_nothing_else():
    facts = _facts_by_measure()
    expected = set()
    for token, (table, column, _) in MEASURES.items():
        for label, values in published(table).items():
            cell = values[COLUMNS[table].index(column)]
            if label != OUTLYING_AREA and isinstance(cell, (int, float)):
                expected.add((token, label))
    assert set(facts) == expected
    assert len(expected) == 193
    assert {(fact.geography.level, fact.geography.id) for fact in facts.values()} == {
        ("country", "0100000US")
    } | {("state", f"0400000US{fips}") for fips in STATE_FIPS}
    record_ids = [fact.source_record_id for fact in facts.values()]
    assert len(set(record_ids)) == len(record_ids)


def test_cells_without_a_plain_number_emit_no_fact():
    """'. . .' marks not applicable. Footnote a marks the All-areas state
    supplementation cells of Table 7.B3: they include recipients and payments
    not assigned to a specific state or other area, so the national count
    exceeds the sum of the areas, and the workbook stores both cells as text."""
    grid = _grid("7.B3")
    assert (grid["F5"], grid["G5"]) == ("a 1,327,153", "a 212.86")
    areas = [label for label in published("7.B3") if label != "All areas"]
    state_recipients = sum(_amount(published("7.B3")[label][2]) for label in areas)
    assert 1_327_153 - state_recipients == 323
    not_applicable = {
        table: sum(
            value == NOT_APPLICABLE
            for values in published(table).values()
            for value in values
        )
        for table in PACKAGES
    }
    assert not_applicable == {"7.B3": 80, "7.B7": 40}
    facts = _facts_by_measure()
    assert ("ssi_state_supplementation_recipients", "All areas") not in facts
    assert all(fact.geography.id != "0400000US69" for fact in facts.values())


def test_table_7b7_total_column_repeats_table_7b1_payment_totals():
    """The Table 7.B7 package reads only columns E and F. Its Total column
    equals Table 7.B1's total payments in all 53 rows, and the Table 7.B1
    package already emits 52 of them, every row but the Northern Mariana
    Islands'."""
    b1, b7 = published("7.B1"), published("7.B7")
    assert list(b1) == list(b7)
    assert all(b7[label][0] == b1[label][4] for label in b1)
    assert {
        row["column"]
        for record_set in _spec("7.B7")["record_sets"]
        for row in record_set["rows"]
    } == {"E", "F"}
    b1_package = load_source_package("packages/ssa/ssi_table_7b1_2024")
    b1_totals = sorted(
        (_area(fact), fact.period.type, fact.period.value, fact.value)
        for fact in b1_package.build_facts(
            YEAR, cells=list(b1_package.build_source_cells(YEAR))
        )
        if fact.measure.concept == "ssa.ssi_payment_amount"
        and not fact.filters
        and not fact.constraints
    )
    assert b1_totals == sorted(
        (label, "calendar_year", YEAR, values[0] * 1000)
        for label, values in b7.items()
        if label != OUTLYING_AREA
    )


def test_table_7b7_totals_equal_federal_plus_state_payments_within_rounding():
    """Table 7.B7's note: totals do not necessarily equal the sum of rounded
    components ($000)."""
    rows = published("7.B7")
    residuals = {
        label: values[0] - values[1] - _amount(values[2])
        for label, values in rows.items()
    }
    assert {label: value for label, value in residuals.items() if value} == {
        "California": 1,
        "Michigan": -1,
        "Nevada": 1,
    }
    areas = [label for label in rows if label != "All areas"]
    assert [
        rows["All areas"][index] - sum(_amount(rows[label][index]) for label in areas)
        for index in range(3)
    ] == [-1, 0, 0]


def test_table_7b3_federal_recipients_add_up_across_areas():
    rows = published("7.B3")
    areas = [label for label in rows if label != "All areas"]
    assert rows["All areas"][0] == sum(rows[label][0] for label in areas)


def test_table_7b1_totals_lie_between_the_larger_type_count_and_their_sum():
    """Table 7.B1 counts recipients of federally administered payments; Table
    7.B3 splits them by type of payment. Every area's 7.B1 total lies between
    the larger of its two 7.B3 counts and their sum, except Alabama's, which
    exceeds its federal SSI count by 4 where Table 7.B3 shows no federally
    administered state supplementation."""
    b1, b3 = published("7.B1"), published("7.B3")
    above_sum = {}
    for label, values in b3.items():
        federal = values[0]
        state = 1_327_153 if label == "All areas" else _amount(values[2])
        total = b1[label][0]
        assert max(federal, state) <= total, label
        if total > federal + state:
            above_sum[label] = total - federal - state
    assert above_sum == {"Alabama": 4}
    assert b1["All areas"][0] - b3["All areas"][0] == 134_013


def test_annual_payments_agree_with_december_caseloads_in_units():
    """A unit check on the emitted facts, not an identity: calendar 2024
    payments in dollars against 12 x December recipients x December average
    payment. Missing the $000 scale would put the ratio near 0.001."""
    facts = _facts_by_measure()
    measures = {
        "federal": (
            "ssi_federal_payment_recipients",
            "ssi_federal_average_monthly_payment",
            "ssi_federal_payments",
        ),
        "state_supplementation": (
            "ssi_state_supplementation_recipients",
            "ssi_state_supplementation_average_monthly_payment",
            "ssi_state_supplementation_payments",
        ),
    }
    ratios = {
        kind: {
            area: facts[(payments, area)].value
            / (12 * facts[(recipients, area)].value * facts[(average, area)].value)
            for token, area in facts
            if token == recipients
        }
        for kind, (recipients, average, payments) in measures.items()
    }
    assert len(ratios["federal"]) == 52
    assert 0.99 < min(ratios["federal"].values())
    assert max(ratios["federal"].values()) < 1.06
    assert len(ratios["state_supplementation"]) == 12
    assert 0.85 < min(ratios["state_supplementation"].values())
    assert max(ratios["state_supplementation"].values()) < 1.25


def test_national_federal_recipients_repeat_ssi_monthly_statistics_table_1():
    """The one semantic key these packages share with another package: SSI
    Monthly Statistics Table 1 prints the same December 2024 national count,
    and Chronicle keeps both as published."""
    monthly = load_source_package(MONTHLY_STATISTICS)
    monthly_facts = monthly.build_facts(
        YEAR, cells=list(monthly.build_source_cells(YEAR))
    )
    by_key = {build_semantic_fact_key(fact): fact for fact in monthly_facts}
    shared = [
        (fact, by_key[build_semantic_fact_key(fact)])
        for table in PACKAGES
        for fact in package_build(table)[2]
        if build_semantic_fact_key(fact) in by_key
    ]
    assert len(shared) == 1
    fact, other = shared[0]
    assert _token(fact) == "ssi_federal_payment_recipients"
    assert _area(fact) == "All areas"
    assert fact.value == other.value == 7_289_843
    assert other.source_record_id.endswith(".by_age.all_ages.recipient_count")


def _identity_digest(key) -> str:
    lines = sorted(
        f"{fact.source_record_id}\t{key(fact)}"
        for table in PACKAGES
        for fact in package_build(table)[2]
    )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def test_semantic_identity_digest():
    assert _identity_digest(build_semantic_fact_key) == SEMANTIC_IDENTITY_DIGEST


def test_aggregate_identity_digest():
    assert _identity_digest(build_aggregate_fact_key) == AGGREGATE_IDENTITY_DIGEST


def test_record_set_ids_name_their_record_ids_and_specs():
    """``layout.record_set_id`` and ``source_record_id`` carry the same token."""
    for table in PACKAGES:
        for record_set in _spec(table)["record_sets"]:
            record_set_id = record_set["record_set_id"]
            token = record_set_id.split(".")[2]
            assert token in MEASURES and MEASURES[token][0] == table
            assert record_set["source_record_id_prefix"] == record_set_id
            assert (
                record_set["record_set_spec_id"] == f"ssa_supplement.{token}.by_area.v1"
            )


def test_facts_carry_each_table_period_and_coverage():
    """Table 7.B3 counts December 2024 under period identity month 2024-12, as
    SSI Monthly Statistics does; Table 7.B7 sums calendar 2024. No fact key
    hashes period coverage, so the semantic identity digest can't catch a wrong
    coverage date."""
    calendar_2024 = PeriodCoverage(
        start_date="2024-01-01",
        end_date="2024-12-31",
        basis="calendar",
        source_period_label="calendar year 2024",
        notes="Payments during calendar year 2024.",
    )
    expected = {
        "7.B3": (PeriodDimension("month", "2024-12"), None),
        "7.B7": (PeriodDimension("calendar_year", 2024), calendar_2024),
    }
    for table, (period, coverage) in expected.items():
        facts = package_build(table)[2]
        assert {fact.period for fact in facts} == {period}
        assert {fact.period_coverage for fact in facts} == {coverage}


def test_national_facts_are_table_totals_and_measures_keep_their_labels():
    """Each All-areas fact is its table's total record and each area fact a
    detail record. Each measure states its concept exactly."""
    for table in PACKAGES:
        for fact in package_build(table)[2]:
            kind = "total" if _area(fact) == "All areas" else "detail"
            assert fact.layout.table_record_kind == kind, fact.source_record_id
            assert fact.layout.measure_label == MEASURE_LABELS[_token(fact)]
            assert fact.measure.concept_relation == "exact"


def test_consumer_rows_label_each_area_with_its_workbook_row_heading():
    """Each package names every area by SSA's row heading, and the register
    gives the shared area values those same labels. The register's label
    reaches the consumer rows; a row that worded its area otherwise would
    leave that wording in ``package_dimension_value_labels``."""
    register = json.loads(REGISTER.read_text("utf-8"))["labels"]["geography"]
    for table in PACKAGES:
        grid = _grid(table)
        for record_set in _spec(table)["record_sets"]:
            for row in record_set["rows"]:
                heading = grid[
                    f"{row['expected_row_header_column']}{row['row_number']}"
                ]
                assert row["label"] == row["expected_row_header"] == heading
        facts = package_build(table)[2]
        assert all(fact.package_dimension_value_labels == {} for fact in facts)
        rows = consumer_fact_rows(list(facts))
        assert dimension_label_issues(rows) == []
        labels: dict[str, set[str]] = {}
        for row in rows:
            assert row["dimension_labels"] == {"geography": "Geography"}
            assert row["dimensions"] == {}
            for value_id, label in row["dimension_value_labels"]["geography"].items():
                labels.setdefault(value_id, set()).add(label)
        assert all(len(texts) == 1 for texts in labels.values())
        headings = {
            grid[f"{LABEL_COLUMN.get(label, 'A')}{row}"]
            for label, row in _area_rows(table).items()
            if label != OUTLYING_AREA
        }
        assert {next(iter(texts)) for texts in labels.values()} == headings
        assert len(headings) == 52
        assert {value_id: register[value_id] for value_id in labels} == {
            value_id: next(iter(texts)) for value_id, texts in labels.items()
        }


def test_both_packages_join_the_default_bundle():
    for package_id, path in PACKAGES.values():
        assert SOURCE_PACKAGE_ALIASES[package_id] == Path(
            path.removeprefix("packages/")
        )
        assert package_id in DEFAULT_BUNDLE_SOURCES


def test_generator_reproduces_the_committed_packages():
    generator = runpy.run_path(str(REPO / "scripts/build_ssa_ssi_7b_packages.py"))
    built = generator["build_packages"]()
    assert sorted(path.relative_to(REPO) for path in built) == sorted(
        Path(path) / "source_package.yaml" for _, path in PACKAGES.values()
    )
    for path, text in built.items():
        assert text == path.read_text(encoding="utf-8"), path


def _mutated_build(table: str, address: str, value: str) -> None:
    package, cells, _ = package_build(table)
    mutated = [
        replace(cell, raw_value=value, display_value=value)
        if cell.sheet_name == table and cell.address == address
        else cell
        for cell in cells
    ]
    assert mutated != list(cells)
    package.build_facts(YEAR, cells=mutated)


def _guarded_label_addresses(table: str) -> list[str]:
    """Every cell a row's selector checks: row heading, column heading, guards."""
    addresses = set()
    for record_set in _spec(table)["record_sets"]:
        for row in record_set["rows"]:
            addresses.add(f"{row['expected_row_header_column']}{row['row_number']}")
            addresses.add(f"{row['column']}{row['expected_column_header_row']}")
            for guard in row.get("guard_cells", []):
                addresses.add(f"{guard['column']}{guard['row']}")
    return sorted(addresses)


def test_selectors_guard_the_title_headings_and_every_area_label():
    assert _guarded_label_addresses("7.B3") == sorted(
        ["A2", "D3", "F3", "D4", "E4", "F4", "G4", "C5"]
        + [f"A{row}" for row in range(6, 57)]
    )
    assert _guarded_label_addresses("7.B7") == sorted(
        ["A2", "E3", "F3", "C4"] + [f"A{row}" for row in range(5, 56)]
    )


@pytest.mark.parametrize(
    ("table", "address"),
    [
        (table, address)
        for table in PACKAGES
        for address in _guarded_label_addresses(table)
    ],
)
def test_every_guarded_label_rejects_layout_drift(table, address):
    """Exhaustive over the 59 + 55 label cells the selectors guard."""
    with pytest.raises(ValueError):
        _mutated_build(table, address, "shifted")
