"""Federal Reserve Z.1 household net worth from the release of 2026-06-11
(chronicle#449).

``federal-reserve-z1-household-net-worth`` now reads table S1M.b of the Z.1
release of 2026-06-11, in place of table B.101 of the release of 2026-03-19.
That release numbers the tables with SNA codes. Net worth is still line 40,
series FL152090005, and footnote 1 still defines the sector in the same words.
The page prints no units line; the release PDF heads S1M.b "Billions of
dollars; amounts outstanding end of period, not seasonally adjusted", as the
B.101 page did. Releases from 2026-09-11 change the sector's coverage, so the
package reads the dated June folder, not ``/current/``.

The expected values are read from the publisher page with Python's
html.parser, not through Chronicle's parsers.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from chronicle.core import validate_facts
from chronicle.source_package import load_source_package
from chronicle.sources.cells import validate_source_cells

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "federal-reserve-z1-household-net-worth"
DATA = REPO_ROOT / "db" / "data" / "federal_reserve" / "z1_household_net_worth_2026"
PAGE = DATA / "federal_reserve_z1_20260611_s1m_b.html"
SHA256 = "a4f0c0ed9b0cb84768fce2497d6a22588dda5735d183203a9604433e347b77a0"
SOURCE_URL = "https://www.federalreserve.gov/releases/z1/20260611/html/S1M_b.htm"
R2_KEY = f"raw/federal_reserve/{PACKAGE}/2026/{SHA256}/{PAGE.name}"
SOURCE_TABLE = "Z.1 S1M.b Households and nonprofit organizations"
SECTOR_NOTE = (
    "Sector includes domestic hedge funds, private equity funds, and personal trusts."
)


class _Page(HTMLParser):
    """The table heading, the text of each row's th and td cells, the
    numbered footnotes and the "Last Update" line of a Z.1 table page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heading = ""
        self.rows: list[list[str]] = []
        self.footnotes: dict[int, str] = {}
        self.last_update = ""
        self._into: str | None = None
        self._footnote = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "h5" and attributes.get("class") == "tablehead":
            self._into = "heading"
        elif tag == "a" and self._into == "heading":
            # The title ends where its description and PDF links start.
            self._into = None
        elif tag == "tr":
            self.rows.append([])
        elif tag in ("th", "td") and self.rows:
            self.rows[-1].append("")
            self._into = "cell"
        elif tag == "li" and (attributes.get("id") or "").startswith("footnote-"):
            self._footnote = int(attributes["id"].removeprefix("footnote-"))
            self.footnotes[self._footnote] = ""
            self._into = "footnote"
        elif tag == "div" and attributes.get("id") == "lastUpdate":
            self._into = "update"

    def handle_endtag(self, tag):
        if tag in ("h5", "th", "td", "li", "div"):
            self._into = None

    def handle_data(self, data):
        if self._into == "heading":
            self.heading += data
        elif self._into == "cell":
            self.rows[-1][-1] += data
        elif self._into == "footnote":
            self.footnotes[self._footnote] += data
        elif self._into == "update":
            self.last_update += data


def _words(text: str) -> str:
    return " ".join(text.split())


@pytest.fixture(scope="module")
def page() -> _Page:
    parser = _Page()
    parser.feed(PAGE.read_text(encoding="utf-8"))
    parser.close()
    return parser


def _net_worth_row(page: _Page) -> tuple[list[str], list[str]]:
    rows = [[_words(cell) for cell in row] for row in page.rows if row]
    (row,) = [row for row in rows if len(row) > 2 and row[2] == "FL152090005"]
    return rows[0], row


def test_manifest_registers_the_june_page_in_place():
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text())
    entry = manifest["files"][2026]

    assert manifest["package_id"] == PACKAGE
    assert manifest["table"] == SOURCE_TABLE
    assert manifest["published_at"] == "2026-06-11"
    assert manifest["source_page"] == (
        "https://www.federalreserve.gov/releases/z1/20260611/"
    )
    assert (
        "The bytes were uploaded to storage.r2 on 2026-11-27 with chronicle "
        "publish-raw and checked there with chronicle verify-raw."
    ) in manifest["notes"]
    assert list(manifest["files"]) == [2026]
    assert hashlib.sha256(PAGE.read_bytes()).hexdigest() == SHA256
    assert entry["filename"] == PAGE.name
    assert entry["source_url"] == SOURCE_URL
    assert entry["sha256"] == SHA256
    assert entry["size_bytes"] == 151_519 == PAGE.stat().st_size
    assert entry["storage"]["r2"]["key"] == R2_KEY
    assert entry["storage"]["r2"]["uri"] == f"r2://ledger-raw/{R2_KEY}"
    # The B.101 page of 2026-03-19 is replaced, not kept beside it.
    assert sorted(path.name for path in DATA.iterdir()) == [PAGE.name, "manifest.yaml"]


def test_june_page_keeps_the_net_worth_line_and_the_sector(page):
    header, row = _net_worth_row(page)

    assert _words(page.heading) == "S1M.b Households and nonprofit organizations"
    assert _words(page.last_update) == "Last Update: June 11, 2026"
    assert header[:6] == ["Line", "Description", "Series", "2023", "2024", "2025"]
    assert row[:3] == ["Line 40", "Net worth (assets minus liabilities)", "FL152090005"]
    # The releases from 2026-09-11 say "domestic hedge funds (through 2012q3)".
    assert _words(page.footnotes[1]).startswith(SECTOR_NOTE)
    assert "through 2012q3" not in page.footnotes[1]


@pytest.mark.parametrize("year", [2023, 2024, 2025])
def test_fact_is_the_line_40_cell_for_its_year(page, year):
    package = load_source_package(PACKAGE)
    cells = package.build_source_cells(year)
    facts = package.build_facts(year, cells=cells)
    header, row = _net_worth_row(page)
    billions = Decimal(row[header.index(str(year))])

    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    (fact,) = facts
    assert Decimal(str(fact.value)) == billions * 10**9
    assert (fact.period.type, fact.period.value) == ("calendar_year", year)
    assert (fact.measure.unit, fact.geography.id) == ("usd", "0100000US")
    assert fact.source.source_table == SOURCE_TABLE
    assert fact.source.vintage == "z1_2026_06_11"
    assert fact.source.source_file == PAGE.name
    assert fact.source.url == SOURCE_URL
    assert fact.source.source_sha256 == SHA256
    assert fact.source.raw_r2_uri == f"r2://ledger-raw/{R2_KEY}"


def test_default_bundle_year_fact():
    # The default bundle builds 2023: 156,278.8 billion dollars in the release
    # of 2026-06-11, where B.101 of 2026-03-19 printed 156,080.7.
    package = load_source_package(PACKAGE)
    (fact,) = package.build_facts(2023)

    assert fact.source_record_id == (
        "federal_reserve_z1.cy2023.households_nonprofits_balance_sheet."
        "net_worth.fl152090005.amount_outstanding"
    )
    assert fact.value == 156_278_800_000_000
