"""SSA SSI Monthly Statistics, December 2025, Table 1 (chronicle#449).

``ssa-ssi-monthly-statistics-2025-12`` is the edition after
``ssa-ssi-monthly-statistics-2024-12``. Both read the "Total with— Federal
payment" row of Table 1 by age group from a CSV extracted from the published
HTML page, and keep the verbatim page capture beside the CSV. ssa.gov refuses
automated downloads, so the maintainer saved the December 2025 page from a
browser on 2026-11-27.

These tests read the expected values from the HTML captures with the
standard-library HTML parser, not through Chronicle's parsers. They check that
the December 2025 table keeps the rows, columns and notes of the December 2024
table, that each fact is its cell on the page, that the CSV is the page's row
in the December 2024 CSV's layout, and that the package declares what its
predecessor declares apart from the edition's ids, month, artifact and
evidence.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from functools import cache
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from chronicle.consumer_contract import build_semantic_fact_key
from chronicle.core import validate_facts
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package
from chronicle.sources.cells import validate_source_cells
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "db" / "data" / "ssa"
PACKAGES_ROOT = REPO_ROOT / "packages"

PACKAGE = "ssa-ssi-monthly-statistics-2025-12"
PREDECESSOR = "ssa-ssi-monthly-statistics-2024-12"
RESOURCES = DATA / "ssi_monthly_statistics_2025_12"
PREDECESSOR_RESOURCES = DATA / "ssi_monthly_statistics_2024_12"
CAPTURE = RESOURCES / "ssi_monthly_2025_12_table01.html"
CSV_FILE = RESOURCES / "ssi_monthly_2025_12_table01.csv"
PREDECESSOR_CAPTURE = PREDECESSOR_RESOURCES / "ssi_monthly_2024_12_table01.html"
PREDECESSOR_CSV = PREDECESSOR_RESOURCES / "ssi_monthly_2024_12_table01.csv"
URL = "https://www.ssa.gov/policy/docs/statcomps/ssi_monthly/2025-12/table01.html"
CAPTURE_SHA256 = "497bd7c68e59186e5c7dc24d38ea7b4d0274865e6c9106fa6c43e31e25de8b50"
CSV_SHA256 = "c1a80d0f568f8911c99451d47e2e7e379143d01fe30a8ee73be76c7e6b825e01"
PREFIX = "ssa_ssi_monthly.month2025_12.ssi_federal_payment_recipients.by_age."

# Table 1's header cells, by the ids the page gives them. Both editions use
# these ids and texts; only the month in the title and caption changes.
HEADERS = {
    "c1": "Type of payment",
    "c2": "All recipients",
    "c3": "Eligibility category",
    "c4": "Age",
    "c5": "Aged",
    "c6": "Blind and disabled a",
    "c7": "Under 18",
    "c8": "18–64",
    "c9": "65 or older b",
    "r1": "Number of recipients c",
    "r6": "Total with—",
    "r7": "Federal payment",
    "r8": "State supplementation",
}
# The package's age value -> (the CSV's age label, the page's column id).
AGES = {
    "all_ages": ("All ages", "c2"),
    "under_18": ("Aged 0-17", "c7"),
    "age_18_to_64": ("Aged 18-64", "c8"),
    "age_65_or_older": ("Aged 65 and over", "c9"),
}
# The "Total with— Federal payment" line sits in the "Number of recipients"
# panel (r1) under "Total with—" (r6).
FEDERAL_PAYMENT_LINE = ["r1", "r6", "r7"]


class _Table1(HTMLParser):
    """Collect Table 1's title, caption, header cells and data cells."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self.captions: list[str] = []
        self.headers: dict[str, dict] = {}
        self.data: list[dict] = []
        self.notes: list[str] = []
        self._in_title = False
        self._caption: list[str] | None = None
        self._cell: dict | None = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "style"}:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "caption":
            self._caption = []
        elif tag in {"td", "th"}:
            self._cell = {
                "tag": tag,
                "id": attributes.get("id"),
                "headers": (attributes.get("headers") or "").split(),
                "class": attributes.get("class") or "",
                "text": [],
            }

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "caption" and self._caption is not None:
            self.captions.append(" ".join("".join(self._caption).split()))
            self._caption = None
        elif tag in {"td", "th"} and self._cell is not None:
            cell, self._cell = self._cell, None
            cell["text"] = " ".join("".join(cell["text"]).split())
            if cell["id"]:
                self.headers[cell["id"]] = cell
            elif "note" in cell["class"].casefold():
                self.notes.append(cell["text"])
            elif cell["tag"] == "td" and cell["headers"]:
                self.data.append(cell)

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title.append(data)
        if self._caption is not None:
            self._caption.append(data)
        elif self._cell is not None:
            self._cell["text"].append(data)


@cache
def _page(path: Path) -> _Table1:
    parser = _Table1()
    parser.feed(path.read_bytes().decode("utf-8"))
    return parser


def _federal_payment_line(path: Path) -> dict[str, int]:
    """The "Total with— Federal payment" line's counts, by column id."""
    line = {}
    for cell in _page(path).data:
        if cell["headers"][:3] == FEDERAL_PAYMENT_LINE:
            column = cell["headers"][-1]
            assert column not in line, column
            assert re.fullmatch(r"\d{1,3}(,\d{3})*", cell["text"]), cell["text"]
            line[column] = int(cell["text"].replace(",", ""))
    assert sorted(line) == ["c2", "c5", "c6", "c7", "c8", "c9"]
    return line


def _csv_text(path: Path) -> str:
    """The CSV the packages read, written from the page's line."""
    line = _federal_payment_line(path)
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "payment_type",
            "payment_type_label",
            "geography_id",
            "geography_level",
            "geography_name",
            "age",
            "recipient_count",
        ]
    )
    for age, column in AGES.values():
        writer.writerow(
            [
                "federal_payment",
                "Total with federal payment",
                "0100000US",
                "country",
                "United States",
                age,
                line[column],
            ]
        )
    return stream.getvalue()


@pytest.fixture(scope="module")
def built():
    package = load_source_package(PACKAGE)
    cells = package.build_source_cells(2025)
    facts = package.build_facts(2025, cells=cells)
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    return cells, facts


def test_manifest_registers_the_csv_and_the_browser_capture():
    manifest = yaml.safe_load((RESOURCES / "manifest.yaml").read_text())
    entry = manifest["files"][2025]
    capture = manifest["files"]["source_capture"]

    assert manifest["package_id"] == PACKAGE
    assert manifest["source_page"] == (
        "https://www.ssa.gov/policy/docs/statcomps/ssi_monthly/2025-12/index.html"
    )
    for item, path, sha256, size in (
        (entry, CSV_FILE, CSV_SHA256, 475),
        (capture, CAPTURE, CAPTURE_SHA256, 17_588),
    ):
        assert item["filename"] == path.name
        assert item["source_url"] == URL
        assert item["sha256"] == sha256
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha256
        assert item["size_bytes"] == size == path.stat().st_size
        assert item["fetched_at"] == "2026-11-27"
        assert item["storage"]["r2"]["uri"] == (
            f"r2://ledger-raw/{item['storage']['r2']['key']}"
        )
    assert entry["storage"]["r2"]["key"] == (
        f"raw/ssa/{PACKAGE}/2025/{CSV_SHA256}/{CSV_FILE.name}"
    )
    assert capture["storage"]["r2"]["key"] == (
        f"raw/ssa/{PACKAGE}/source_capture/{CAPTURE_SHA256}/{CAPTURE.name}"
    )
    assert "saved it from a browser on" in capture["notes"]
    assert "2026-11-27 because ssa.gov refuses automated downloads" in " ".join(
        capture["notes"].split()
    )


@pytest.mark.parametrize(
    ("path", "month"),
    [(PREDECESSOR_CAPTURE, "December 2024"), (CAPTURE, "December 2025")],
)
def test_table_1_keeps_its_rows_columns_and_notes(path, month):
    """The December 2025 page gives Table 1 the December 2024 page's header
    cells, the "Total with— Federal payment" line and the count footnote."""
    page = _page(path)

    assert " ".join("".join(page.title).split()) == (
        f"SSI Monthly Statistics, {month} - Table 1"
    )
    assert page.captions == [
        "Table 1. Number of recipients, total payments, average monthly "
        "payment, and number of awards, by type of payment, eligibility "
        f"category, and age, {month}"
    ]
    for cell_id, text in HEADERS.items():
        assert page.headers[cell_id]["text"] == text, cell_id
    assert page.headers["r7"]["headers"] == ["r1", "r6", "c1"]
    assert page.headers["r6"]["headers"] == ["r1", "c1"]
    for column in ("c7", "c8", "c9"):
        assert page.headers[column]["headers"] == ["c4"]
    assert "c. Includes retroactive payments." in page.notes
    assert page.notes[0] == (
        "SOURCE: Social Security Administration, Supplemental Security "
        "Record, 100 percent data."
    )


def test_both_pages_give_the_same_cell_ids_and_header_texts():
    """Apart from their numbers, the two pages' cells are the same."""

    def shape(path):
        page = _page(path)
        return (
            {cell_id: cell["text"] for cell_id, cell in page.headers.items()},
            [tuple(cell["headers"]) for cell in page.data],
            [re.sub(r"\d[\d,]*", "N", note) for note in page.notes],
        )

    assert shape(PREDECESSOR_CAPTURE) == shape(CAPTURE)


def test_each_fact_is_its_cell_on_the_page(built):
    _, facts = built
    line = _federal_payment_line(CAPTURE)

    assert len(facts) == 4
    for fact in facts:
        value_id = fact.layout.groupby_value_id
        assert fact.source_record_id == f"{PREFIX}{value_id}.recipient_count"
        assert fact.value == line[AGES[value_id][1]], value_id
    # Federal payment recipients: everyone but the state-supplementation-only
    # recipients; the age groups and the eligibility categories add up.
    assert line["c7"] + line["c8"] + line["c9"] == line["c2"] == 7_264_734
    assert line["c5"] + line["c6"] == line["c2"]


def test_the_csv_is_the_pages_line_in_the_predecessors_layout():
    """The same writer gives the December 2024 package's CSV byte for byte
    from its capture, and the December 2025 CSV from the new capture."""
    assert _csv_text(PREDECESSOR_CAPTURE).encode() == PREDECESSOR_CSV.read_bytes()
    assert _csv_text(CAPTURE).encode() == CSV_FILE.read_bytes()


def test_fact_period_source_and_vintage(built):
    _, facts = built
    manifest = yaml.safe_load((RESOURCES / "manifest.yaml").read_text())
    entry = manifest["files"][2025]

    for fact in facts:
        assert (fact.period.type, fact.period.value) == ("month", "2025-12")
        assert fact.source.vintage == "ssi_monthly_statistics_2025_12"
        assert fact.source.source_table == (
            "SSI Monthly Statistics, December 2025, Table 1"
        )
        assert fact.source.source_file == CSV_FILE.name
        assert fact.source.source_sha256 == CSV_SHA256
        assert fact.source.url == URL
        assert fact.source.raw_r2_uri == entry["storage"]["r2"]["uri"]


def test_no_fact_repeats_the_december_2024_edition(built):
    """A new month is a new package: no semantic key is shared."""
    _, facts = built
    previous = load_source_package(PREDECESSOR)
    previous_facts = previous.build_facts(2024, cells=previous.build_source_cells(2024))

    assert not {build_semantic_fact_key(fact) for fact in facts} & {
        build_semantic_fact_key(fact) for fact in previous_facts
    }


@pytest.mark.parametrize("build_year", [2023, 2024])
def test_building_at_another_year_does_not_relabel_the_2025_page(built, build_year):
    package = load_source_package(PACKAGE)
    other = package.build_facts(
        build_year, cells=package.build_source_cells(build_year)
    )
    _, facts = built

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


# The package's declarations that name its edition.
EDITION_FIELDS = {
    ("package_id",): PACKAGE,
    ("label",): (
        "SSA SSI Monthly Statistics December 2025 Table 1 federal payment "
        "recipients by age"
    ),
    ("artifact", "source_table"): "SSI Monthly Statistics, December 2025, Table 1",
    ("artifact", "resource_directory"): "data/ssa/ssi_monthly_statistics_2025_12",
    ("artifact", "vintage"): "ssi_monthly_statistics_2025_12",
    ("artifact", "extracted_at"): "2026-11-27",
    ("artifact", "artifact_year"): 2025,
    ("artifact", "sheet_name"): "ssi_monthly_2025_12_table01",
    ("record_sets", 0, "record_set_id"): PREFIX.rstrip("."),
    ("record_sets", 0, "source_record_id_prefix"): PREFIX.rstrip("."),
    ("record_sets", 0, "sheet_name"): "ssi_monthly_2025_12_table01",
    ("record_sets", 0, "period"): "2025-12",
    ("record_sets", 0, "measures", 0, "concept_evidence_url"): URL,
}
# Free text that describes the edition: the extraction and the evidence note.
EDITION_TEXT = {
    ("artifact", "extraction_method"),
    ("record_sets", 0, "measures", 0, "concept_evidence_notes"),
}


def test_package_mirrors_its_predecessor():
    """Differential: apart from the edition's ids, month, artifact and
    evidence, every declaration (concepts, units, labels, rows, filters,
    constraints, guards, record set spec) equals the predecessor's."""
    old = dict(_leaves(_declarations(PREDECESSOR)))
    new = dict(_leaves(_declarations(PACKAGE)))

    assert old.keys() == new.keys()
    changed = {path for path in old if old[path] != new[path]}
    assert changed == set(EDITION_FIELDS) | EDITION_TEXT
    for path, value in EDITION_FIELDS.items():
        assert new[path] == value, path
    assert "December 2025" in new[("artifact", "extraction_method")]
    notes = " ".join(
        new[("record_sets", 0, "measures", 0, "concept_evidence_notes")].split()
    )
    assert "federal SSI payment in December 2025" in notes
    assert "7,264,734 = 1,015,006 + 3,820,243 + 2,429,485" in notes
    assert "excludes the 127,467 people" in notes
    line = _federal_payment_line(CAPTURE)
    state_supplementation_only = next(
        int(cell["text"].replace(",", ""))
        for cell in _page(CAPTURE).data
        if cell["headers"] == ["r1", "r5", "c2"]
    )
    assert _page(CAPTURE).headers["r5"]["text"] == "State supplementation only"
    assert state_supplementation_only == 127_467
    assert line["c2"] + state_supplementation_only == next(
        int(cell["text"].replace(",", ""))
        for cell in _page(CAPTURE).data
        if cell["headers"] == ["r1", "r2", "c2"]
    )


def test_source_suite_passes_agent_acceptance(tmp_path):
    suite = build_source_suite(PACKAGE, tmp_path / PACKAGE, year=2025)

    assert suite.agent_acceptance.valid
    assert suite.agent_acceptance.counts["row_semantic_error_count"] == 0
