"""Fidelity and invariant tests for SSA Supplement 2025 Table 7.B1.

The package parses SSA's own section 7.B workbook (``7b.xlsx``). These tests
check every emitted fact against an independent rendering of the same table,
the Wayback capture of the 7.B web page, parsed here with the standard-library
HTML parser. Arithmetic properties alone cannot catch invented values (the
hand-typed CSV this package used before was internally additive), so the
cross-format comparison is the load-bearing check.
"""

from __future__ import annotations

from dataclasses import replace
from functools import cache
import hashlib
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from chronicle.artifacts import build_r2_key
from chronicle.consumer_contract import build_semantic_fact_key
from chronicle.source_package import load_source_package

REPO = Path(__file__).resolve().parents[1]
PACKAGE = "packages/ssa/ssi_table_7b1_2024"
RESOURCES = REPO / "db/data/ssa/ssi_table_7b1_2024"
YEAR = 2024

XLSX_SHA256 = "6363d2efb1e9f76a672ef380ad41e6a2426ebe63c86a31d5dd78534a3aa31bd6"
HTML_SHA256 = "0e88bd5e7c365f175504e4279c23255058d78ae4d6c47ac7b488758c3d9945dc"

CATEGORIES = ("total", "aged", "blind", "disabled")
MEASURES = {
    # measure_id: (first workbook column, offset into the 8 published values, scale)
    "recipient_count": ("D", 0, 1),
    "payment_amount": ("H", 4, 1000),
}
RECORD_PREFIX = {
    "recipient_count": "ssa_supplement.cy2024.ssi_recipients.by_area_category",
    "payment_amount": "ssa_supplement.cy2024.ssi_payments.by_area_category",
}
OUTLYING_AREA = "Northern Mariana Islands"
STATE_FIPS = {
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12", "13", "15",
    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
    "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "40", "41", "42", "44", "45", "46", "47", "48", "49", "50", "51", "53",
    "54", "55", "56",
}  # fmt: skip

# sha256 of the sorted "source_record_id<TAB>semantic_fact_key" lines, taken
# from the package before its values were corrected. The correction must not
# move any fact's semantic identity.
SEMANTIC_IDENTITY_DIGEST = (
    "1f9e6746536ea833578069c28e4863fccac005bdff6ef6c5b44444584e77ba76"
)


class _Table7B1Parser(HTMLParser):
    """Collect the cell text of every row of the first table in ``#table7.b1``."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._armed = False
        self._done = False
        self._table_depth = 0
        self._in_target = False
        self._cell: list[str] | None = None
        self._row: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if dict(attrs).get("id") == "table7.b1":
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


def _integer(text: str) -> int | None:
    digits = text.replace(",", "")
    return int(digits) if digits.isdigit() else None


@cache
def published_rows() -> dict[str, tuple[int, ...]]:
    """Area label -> 8 published values, from the pinned HTML capture."""
    parser = _Table7B1Parser()
    parser.feed((RESOURCES / "7b_wayback_20260101161547.html").read_text("utf-8"))
    rows: dict[str, tuple[int, ...]] = {}
    for cells in parser.rows:
        if len(cells) < 9:
            continue
        values = tuple(_integer(cell) for cell in cells[1:9])
        if all(value is not None for value in values):
            assert cells[0] not in rows, cells[0]
            rows[cells[0]] = values
    return rows


@cache
def package_cells():
    package = load_source_package(PACKAGE)
    return package, tuple(package.build_source_cells(YEAR))


@cache
def package_facts():
    package, cells = package_cells()
    return tuple(package.build_facts(YEAR, cells=list(cells)))


def _cell_grid() -> dict[str, object]:
    _, cells = package_cells()
    return {cell.address: cell.raw_value for cell in cells if cell.sheet_name == "7.B1"}


def _area_label(fact) -> str:
    if fact.geography.level == "country":
        return "All areas"
    return fact.geography.name


def _category(fact) -> str:
    return fact.source_record_id.rsplit(".", 2)[-2].rsplit("_", 1)[-1]


def test_manifest_pins_publisher_bytes_and_canonical_r2_keys():
    manifest = yaml.safe_load((RESOURCES / "manifest.yaml").read_text("utf-8"))
    expected = {2024: XLSX_SHA256, "source_capture": HTML_SHA256}
    assert set(manifest["files"]) == set(expected)
    for label, entry in manifest["files"].items():
        content = (RESOURCES / entry["filename"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == entry["sha256"] == expected[label]
        assert len(content) == entry["size_bytes"]
        key = build_r2_key(
            source_id=manifest["source_id"],
            package_id=manifest["package_id"],
            year=label,
            sha256=entry["sha256"],
            filename=entry["filename"],
            package_path=RESOURCES / "manifest.yaml",
        )
        assert entry["storage"]["r2"]["key"] == key
        assert entry["storage"]["r2"]["uri"] == f"r2://ledger-raw/{key}"
    assert not (RESOURCES / "ssi_table_7b1_2024.csv").exists()


def test_html_capture_renders_the_full_published_table():
    rows = published_rows()
    assert len(rows) == 53
    assert list(rows)[0] == "All areas"
    assert list(rows)[-1] == OUTLYING_AREA
    assert "Outlying area" not in rows
    assert rows["All areas"] == (
        7_423_856, 1_190_660, 63_747, 6_169_449,
        63_079_493, 7_716_669, 561_663, 54_801_161,
    )  # fmt: skip


def test_workbook_and_html_capture_agree_on_every_published_cell():
    """Differential: all 53 x 8 = 424 workbook cells equal the HTML rendering."""
    grid = _cell_grid()
    rows = published_rows()
    labels = {"All areas": 5, OUTLYING_AREA: 58}
    for offset, label in enumerate(list(rows)[1:52]):
        labels[label] = 6 + offset
    label_columns = {"All areas": "C", OUTLYING_AREA: "B"}
    compared = 0
    for label, row in labels.items():
        assert grid[f"{label_columns.get(label, 'A')}{row}"] == label
        for index, column in enumerate("DEFGHIJK"):
            assert grid[f"{column}{row}"] == rows[label][index], (label, column)
            compared += 1
    assert compared == 424


def test_every_fact_equals_its_published_cell():
    """For every emitted fact: value == published cell x unit scale, exactly."""
    rows = published_rows()
    facts = package_facts()
    assert len(facts) == 416
    for fact in facts:
        measure_id = fact.source_record_id.rsplit(".", 1)[-1]
        _, offset, scale = MEASURES[measure_id]
        published = rows[_area_label(fact)][offset + CATEGORIES.index(_category(fact))]
        assert fact.value == published * scale, fact.source_record_id


def test_facts_cover_all_areas_states_and_dc_exactly_once():
    facts = package_facts()
    record_ids = [fact.source_record_id for fact in facts]
    assert len(set(record_ids)) == len(record_ids) == 416
    geographies = {(fact.geography.level, fact.geography.id) for fact in facts}
    assert geographies == {("country", "0100000US")} | {
        ("state", f"0400000US{fips}") for fips in STATE_FIPS
    }
    for measure_id, prefix in RECORD_PREFIX.items():
        for fact_geo in geographies:
            for category in CATEGORIES:
                matches = [
                    fact
                    for fact in facts
                    if (fact.geography.level, fact.geography.id) == fact_geo
                    and fact.source_record_id.startswith(prefix)
                    and fact.source_record_id.endswith(f"_{category}.{measure_id}")
                ]
                assert len(matches) == 1, (measure_id, fact_geo, category)


def test_outlying_area_row_is_parsed_but_not_emitted():
    """All areas includes the Northern Mariana Islands; the package keeps it out."""
    grid = _cell_grid()
    assert grid["B58"] == OUTLYING_AREA
    assert all(fact.geography.id != "0400000US69" for fact in package_facts())


def test_recipient_counts_are_additive_across_categories_and_areas():
    rows = published_rows()
    for label, values in rows.items():
        assert values[0] == sum(values[1:4]), label
    for index in range(4):
        areas = sum(
            values[index] for label, values in rows.items() if label != "All areas"
        )
        assert areas == rows["All areas"][index]


def test_payment_rounding_residuals_stay_within_the_published_footnote():
    """Footnote a: payment totals need not equal the sum of rounded components."""
    rows = published_rows()
    for label, values in rows.items():
        assert values[4] - sum(values[5:8]) in {-1, 0, 1}, label
    residuals = [
        rows["All areas"][index]
        - sum(values[index] for label, values in rows.items() if label != "All areas")
        for index in range(4, 8)
    ]
    assert residuals == [-1, 0, 3, -2]


def test_components_never_exceed_their_totals():
    rows = published_rows()
    national = rows["All areas"]
    for label, values in rows.items():
        assert all(value >= 0 for value in values), label
        assert max(values[1:4]) <= values[0], label
        assert max(values[5:8]) <= values[4], label
        assert all(value <= national[index] for index, value in enumerate(values))


def test_semantic_identity_is_unchanged_by_the_correction():
    lines = sorted(
        f"{fact.source_record_id}\t{build_semantic_fact_key(fact)}"
        for fact in package_facts()
    )
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    assert digest == SEMANTIC_IDENTITY_DIGEST


def test_facts_point_at_the_publisher_workbook():
    for fact in package_facts():
        assert fact.source.source_sha256 == XLSX_SHA256
        assert fact.source.raw_r2_uri.endswith(f"/2024/{XLSX_SHA256}/7b.xlsx")
        assert fact.source.url.endswith("/supplement/2025/7b.xlsx")


def _mutated_build(address: str, value: str) -> None:
    package, cells = package_cells()
    mutated = [
        replace(cell, raw_value=value, display_value=value)
        if cell.sheet_name == "7.B1" and cell.address == address
        else cell
        for cell in cells
    ]
    assert mutated != list(cells)
    package.build_facts(YEAR, cells=mutated)


def _guarded_label_addresses() -> list[str]:
    addresses = ["A2", "D3", "H3"]  # title, column-group spanners
    addresses += [f"{column}4" for column in "DEFGHIJK"]  # category headings
    addresses += ["C5"] + [f"A{row}" for row in range(6, 57)]  # area labels
    return addresses


@pytest.mark.parametrize("address", _guarded_label_addresses())
def test_every_guarded_label_rejects_layout_drift(address):
    """Exhaustive over the 63 label cells the selectors guard."""
    with pytest.raises(ValueError):
        _mutated_build(address, "shifted")
