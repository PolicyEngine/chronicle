"""Reconcile every curated Kindergeld fact to the captured publisher article.

The evidence reader is deliberately separate from the package generator: it
uses HTMLParser and Decimal, and never imports the production extractor.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from chronicle.bundle import build_bundle_coverage
from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.dimension_labels import dimension_label_issues
from chronicle.source_package import load_source_package, validate_source_package
from chronicle.sources.cells import validate_source_cells

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "ostbelgien-kindergeld-2025"
PACKAGE_DIR = ROOT / "packages/ostbelgien/kindergeld_2025"
DATA_DIR = ROOT / "db/data/ostbelgien/kindergeld_2025"
CAPTURE = DATA_DIR / "kindergeld-in-ostbelgien.article.html"
CSV = DATA_DIR / "ostbelgien_kindergeld_2025.csv"
CAPTURE_SHA256 = "c570d9b5cef3bb100c4caf1ca8db528376d6f7b3176968d3d259bb947d2801c5"
SOURCE_URL = (
    "https://ostbelgienstatistik.be/desktopdefault.aspx/tabid-3748/6766_read-39090/"
)
AGE_TABLE = "Verteilung des Kindergelds nach Altersgruppen"
SUPPLEMENT_TABLE = "Verteilung des Kindergelds nach Zuschlag"
EXPENDITURE_TABLE = "Ausgaben Familienleistungen im Jahr 2025"
COMMUNES = {
    "63023": "Eupen",
    "63040": "Kelmis",
    "63048": "Lontzen",
    "63061": "Raeren",
    "63001": "Amel",
    "63012": "Büllingen",
    "63087": "Burg-Reuland",
    "63013": "Bütgenbach",
    "63067": "Sankt Vith",
}


@dataclass
class _Element:
    tag: str
    children: list[str | _Element] = field(default_factory=list)

    def text(self) -> str:
        return " ".join(
            " ".join(
                child.text() if isinstance(child, _Element) else child
                for child in self.children
            ).split()
        )

    def descendants(self, tag: str):
        for child in self.children:
            if isinstance(child, _Element):
                if child.tag == tag:
                    yield child
                yield from child.descendants(tag)


class _ArticleParser(HTMLParser):
    """A tiny DOM sufficient for headings, paragraphs, rows and nested cells."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Element("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Element(tag)
        self.stack[-1].children.append(node)
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "hr",
            "img",
            "input",
            "link",
            "meta",
        }:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _article():
    parser = _ArticleParser()
    parser.feed(CAPTURE.read_text(encoding="utf-8"))
    articles = list(parser.root.descendants("article"))
    assert len(articles) == 1
    return articles[0]


def _tables(article):
    """Associate each nonempty table with the publisher heading before it."""
    result = {}
    heading = None

    def walk(node):
        nonlocal heading
        if node.tag in {"h1", "h2", "h3"}:
            heading = node.text()
        if node.tag == "table":
            rows = [
                [cell.text() for cell in row.children if isinstance(cell, _Element)]
                for row in node.descendants("tr")
            ]
            if rows:
                assert heading not in result
                assert rows[0] == ["", "2025"]
                result[heading] = dict(rows[1:])
            return
        for child in node.children:
            if isinstance(child, _Element):
                walk(child)

    walk(article)
    assert set(result) == {AGE_TABLE, SUPPLEMENT_TABLE, EXPENDITURE_TABLE}
    return result


def _row_cells(fragment):
    """The cell texts of one ``<tr>`` fragment, read with the test's own parser."""
    parser = _ArticleParser()
    parser.feed(fragment)
    rows = list(parser.root.descendants("tr"))
    assert len(rows) == 1, fragment
    return [cell.text() for cell in rows[0].children if isinstance(cell, _Element)]


def _paragraph(article, contains):
    matches = [p.text() for p in article.descendants("p") if contains in p.text()]
    assert len(matches) == 1, contains
    return matches[0]


def _number(raw):
    if raw == "einmal":
        return Decimal(1)
    return Decimal(raw.replace(".", "").replace(",", ".").replace(" %", ""))


def _match(pattern, text):
    found = re.search(pattern, text)
    assert found is not None, (pattern, text)
    return found.groupdict()


def _narrative(article):
    """Read the six stock counts, four printed shares and two premium counts."""
    headline = _paragraph(article, "Neue Zahlen zum Kindergeld")
    recipients = _paragraph(article, "verteilen sich auf")
    transition = _paragraph(article, "eine Übergangsregelung geschaffen")
    premium = _paragraph(article, "2025 wurde die Geburtsprämie")
    result = _match(r"Dezember 2025 für (?P<children_total>[\d.]+) Kinder", headline)
    result.update(_match(r"auf (?P<recipients_total>[\d.]+) Empfänger", recipients))
    result.update(
        _match(
            r"Dezember 2025 erhielten (?P<children_protected>[\d.]+) Kinder, d.h. "
            r"(?P<children_protected_share>[\d,]+ %)"
            r", einen festgehaltenen Betrag und (?P<children_new>[\d.]+) Kinder, d.h. "
            r"(?P<children_new_share>[\d,]+ %)",
            transition,
        )
    )
    result.update(
        _match(
            r"Empfänger bezogen erhielten (?P<recipients_protected>[\d.]+) "
            r"\((?P<recipients_protected_share>[\d,]+ %)\) einen festgehaltenen und "
            r"(?P<recipients_new>[\d.]+) Empfänger "
            r"\((?P<recipients_new_share>[\d,]+ %)\)",
            transition,
        )
    )
    result.update(
        _match(
            r"2025 wurde die Geburtsprämie (?P<birth_premium_payments>[\d.]+) "
            r"und die Adoptionsprämie (?P<adoption_premium_payments>einmal) ausgezahlt",
            premium,
        )
    )
    assert len(result) == 12
    return result


@pytest.fixture(scope="module")
def curated_rows():
    with CSV.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


@pytest.fixture(scope="module")
def package():
    return load_source_package(PACKAGE_ID)


@pytest.fixture(scope="module")
def facts(package):
    return package.build_facts(2025)


def test_evidence_capture_is_the_declared_attributed_transcription():
    raw = CAPTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CAPTURE_SHA256
    text = raw.decode("utf-8")
    assert "Captured 2026-10-24" in text
    assert "not the publisher's byte stream" in text
    assert "Aktualisierung vom 31.03.2026" in _article().text()
    manifest_text = (DATA_DIR / "manifest.yaml").read_text(encoding="utf-8")
    manifest = yaml.safe_load(manifest_text)
    csv_entry = manifest["files"][2025]
    assert csv_entry["filename"] == CSV.name
    assert csv_entry["sha256"] == hashlib.sha256(CSV.read_bytes()).hexdigest()
    assert csv_entry["size_bytes"] == CSV.stat().st_size
    assert SOURCE_URL in manifest_text
    # The tables' own attribution line names the publisher.
    assert f"<em>Quelle: {manifest['publisher']}</em>" in text
    assert CAPTURE_SHA256 in manifest_text
    assert CAPTURE.name in manifest_text
    assert "no licence stated; figures cited with attribution" in manifest_text
    assert "transcription" in manifest_text.lower()
    capture_entry = manifest["files"]["source_capture"]
    assert capture_entry["filename"] == CAPTURE.name
    assert capture_entry["sha256"] == CAPTURE_SHA256
    assert capture_entry["size_bytes"] == len(raw)
    assert capture_entry["artifact_kind"] == "sanitized_browser_transcription"
    assert csv_entry["storage"]["r2"]["bucket"] == "ledger-raw"
    assert csv_entry["sha256"] in csv_entry["storage"]["r2"]["key"]


def test_every_curated_value_and_built_fact_matches_independent_html_parse(
    curated_rows, facts
):
    capture = CAPTURE.read_text(encoding="utf-8")
    article = _article()
    tables = _tables(article)
    narrative = _narrative(article)
    assert len(curated_rows) == len(facts) == 35
    assert len({row["value_id"] for row in curated_rows}) == 35
    by_id = {fact.layout.groupby_value_id: fact for fact in facts}
    assert set(by_id) == {row["value_id"] for row in curated_rows}
    seen_tables = Counter()
    seen_narrative = set()
    for row in curated_rows:
        if row["table"] in tables:
            expected_raw = tables[row["table"]][row["row_label"]]
            seen_tables[row["table"]] += 1
            # Structured coordinates, not a quotation; the evidence column carries
            # the captured row itself, which must occur once, verbatim.
            assert row["source_locator"] == (
                f'Tabelle "{row["table"]}"; Zeile "{row["row_label"]}"; Spalte "2025"'
            )
            assert capture.count(row["source_evidence"]) == 1
            assert _row_cells(row["source_evidence"]) == [
                row["row_label"],
                expected_raw,
            ]
        else:
            expected_raw = narrative[row["value_id"]]
            seen_narrative.add(row["value_id"])
            assert row["source_locator"] in {p.text() for p in article.descendants("p")}
            assert row["source_evidence"] == row["source_locator"]
            assert row["source_evidence"] in capture
            assert expected_raw in row["source_evidence"]
        assert row["value_raw"] == expected_raw
        assert Decimal(row["value"]) == _number(expected_raw)
        fact = by_id[row["value_id"]]
        assert Decimal(str(fact.value)) == _number(expected_raw)
        assert fact.measure.unit == row["unit"]
        assert fact.aggregation.method == (
            "share" if row["unit"] == "percent" else "sum"
        )
        assert fact.entity.name == row["entity"]
        assert fact.entity.role == row["entity_role"]
        assert fact.layout.table_record_kind == row["table_record_kind"]
        assert fact.source_cell_keys and fact.source_row_keys
        assert fact.provenance_class == "administrative"
        assert fact.assertion == "observation"
        assert fact.domain == "child_benefit"
    assert seen_tables == {AGE_TABLE: 4, SUPPLEMENT_TABLE: 5, EXPENDITURE_TABLE: 14}
    assert seen_narrative == set(narrative)


def test_published_totals_and_shares_are_preserved_without_inventing_a_supplement_total(
    curated_rows, facts
):
    tables = _tables(_article())
    narrative = {key: _number(value) for key, value in _narrative(_article()).items()}
    assert (
        narrative["children_protected"] + narrative["children_new"]
        == narrative["children_total"]
    )
    assert (
        narrative["recipients_protected"] + narrative["recipients_new"]
        == narrative["recipients_total"]
    )
    assert {
        key: value for key, value in narrative.items() if key.endswith("share")
    } == {
        "children_protected_share": Decimal("1.2"),
        "children_new_share": Decimal("98.8"),
        "recipients_protected_share": Decimal("1.7"),
        "recipients_new_share": Decimal("98.3"),
    }
    age = {label: _number(value) for label, value in tables[AGE_TABLE].items()}
    assert (
        sum(value for label, value in age.items() if label != "Total") == age["Total"]
    )
    expenditure = {
        label: _number(value) for label, value in tables[EXPENDITURE_TABLE].items()
    }
    assert sum(list(expenditure.values())[:7]) == expenditure["Kindergeld neuer Betrag"]
    assert (
        expenditure["Geburtsprämie"] + expenditure["Adoptionsprämie"]
        == expenditure["Prämien"]
    )
    assert (
        sum(
            expenditure[label]
            for label in (
                "Kindergeld neuer Betrag",
                "Kindergeld festgehaltener Betrag",
                "Prämien",
                "Sonstiges (Korrekturen, Verträge etc.)",
            )
        )
        == expenditure["Total Familienleistungen"]
    )
    assert (
        _number(
            _match(
                r"Familienleistungen (?P<total>[\d.,]+) Euro",
                _paragraph(_article(), "betrugen die Ausgaben im Jahr 2025"),
            )["total"]
        )
        == expenditure["Total Familienleistungen"]
    )
    supplement_rows = [row for row in curated_rows if row["table"] == SUPPLEMENT_TABLE]
    assert len(supplement_rows) == 5
    assert {row["row_label"] for row in supplement_rows} == set(
        tables[SUPPLEMENT_TABLE]
    )
    assert all("total" not in row["row_label"].lower() for row in supplement_rows)
    assert "zwei Zuschläge" in _paragraph(_article(), "zum Stand Ende Dezember 2025")
    by_id = {fact.layout.groupby_value_id: fact for fact in facts}
    printed_totals = {
        "Total",
        "Kindergeld neuer Betrag",
        "Prämien",
        "Total Familienleistungen",
    }
    for row in curated_rows:
        fact = by_id[row["value_id"]]
        if row["row_label"] in printed_totals:
            assert fact.layout.table_record_kind == "total"
        if fact.layout.table_record_kind == "detail":
            assert fact.constraints


def test_package_validation_lineage_and_source_only_coverage(package, facts):
    assert validate_source_package(package.package_path, year=2025).valid
    cells = package.build_source_cells(2025)
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    coverage = build_bundle_coverage(consumer_fact_rows(facts))
    assert coverage["fact_count"] == 35
    assert coverage["unique_counts"]["aggregate_fact_key"] == 35
    assert coverage["unique_counts"]["semantic_fact_key"] == 35
    assert coverage["duplicates"] == {
        "aggregate_fact_keys": [],
        "semantic_fact_keys": [],
    }
    assert len(coverage["counts"]["by_geography"]) == 1
    assert len(coverage["counts"]["by_source"]) == 1
    assert coverage["counts"]["by_period"] == {"calendar_year:2025": 35}
    assert coverage["counts"]["by_entity"] == {
        "person": 19,
        "benefit_unit": 2,
        "government": 14,
    }
    assert not dimension_label_issues(consumer_fact_rows(facts))
    assert all(fact.dimension_labels for fact in facts)
    assert all(fact.dimension_value_labels for fact in facts)


# Each basis maps to the span the article states, with the phrase that states it.
# The age table states no span, so its coverage carries the label and no dates.
EXPECTED_COVERAGE = {
    "december_2025": ("2025-12-01", "2025-12-31", "im Dezember 2025"),
    "end_2025": ("2025-12-31", "2025-12-31", "zum Stand Ende Dezember 2025"),
    "calendar_year_2025": ("2025-01-01", "2025-12-31", "im Jahr 2025"),
    "publisher_year_2025_ambiguous": (None, None, None),
}


def test_publisher_periods_do_not_change_with_build_year(package, facts, curated_rows):
    assert package.build_facts(2026) == facts
    assert {fact.period.value for fact in facts} == {2025}
    assert {fact.period.type for fact in facts} == {"calendar_year"}
    text = _article().text()
    by_id = {fact.layout.groupby_value_id: fact for fact in facts}
    assert {row["reference_basis"] for row in curated_rows} == set(EXPECTED_COVERAGE)
    for row in curated_rows:
        coverage = by_id[row["value_id"]].period_coverage
        start, end, phrase = EXPECTED_COVERAGE[row["reference_basis"]]
        assert coverage.start_date == start
        assert coverage.end_date == end
        assert coverage.basis == ("calendar" if start else None)
        assert coverage.source_period_label == row["source_period_label"]
        if phrase:
            assert phrase in text
            assert phrase in coverage.notes
        if row["reference_basis"] == "calendar_year_2025":
            assert "2025 wurde" in coverage.notes
        if row["entity_role"] == "benefit_recipient" and row["value_id"].startswith(
            "recipients"
        ):
            assert "verteilen sich auf 8.302 Empfänger" in coverage.notes
        if row["table"] == AGE_TABLE:
            assert coverage.source_period_label == "2025"
            assert (
                "die 2025 Kindergeld von der Deutschsprachigen Gemeinschaft erhalten haben"
                in coverage.notes
            )
            assert "the article states none" in coverage.notes
            assert "does not establish" in coverage.notes
        if row["table"] == SUPPLEMENT_TABLE:
            assert "rows overlap and no total is published" in coverage.notes


def test_declarations_guard_every_row_and_explicitly_declare_provenance(curated_rows):
    spec_text = (PACKAGE_DIR / "source_package.yaml").read_text(encoding="utf-8")
    assert not any(
        isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken))
        for token in yaml.scan(spec_text)
    )
    spec = yaml.safe_load(spec_text)
    assert spec_text.count("provenance_class: administrative") == len(
        spec["record_sets"]
    )
    by_id = {row["value_id"]: row for row in curated_rows}
    for record_set in spec["record_sets"]:
        assert record_set["provenance_class"] == "administrative"
        assert record_set["assertion"] == "observation"
        assert record_set["source_record_id_prefix"]
        assert record_set["record_set_spec_id"]
        coverages = set()
        for selected in record_set["rows"]:
            source_row = by_id[selected["value_id"]]
            coverages.add(source_row["reference_basis"])
            assert selected["expected_row_header"] == source_row["value_id"]
            guards = {
                guard["label"]: guard["expected_value"]
                for guard in selected["guard_cells"]
            }
            for key in (
                "table",
                "row_label",
                "unit",
                "reference_basis",
                "source_locator",
                "source_evidence",
            ):
                assert guards[key] == source_row[key]
            filters = {
                **record_set.get("shared_filters", {}),
                **selected.get("filters", {}),
            }
            constraints = record_set.get("shared_constraints", []) + selected.get(
                "constraints", []
            )
            for key, value in filters.items():
                assert source_row[key] == value
                assert any(
                    c["variable"] == key
                    and c["operator"] == "=="
                    and c["value"] == value
                    for c in constraints
                )
        assert len(coverages) == 1


def test_non_nuts_publisher_scope_contains_the_nine_verified_communes(facts):
    statbel = (
        ROOT
        / "db/data/statbel/population_structure_commune_2025/statbel_population_structure_commune_2025.csv"
    )
    with statbel.open(encoding="utf-8", newline="") as stream:
        source = {
            row["geography_id"]: row
            for row in csv.DictReader(stream)
            if row["value_id"].endswith("_total")
        }
    for code, name in COMMUNES.items():
        assert source[code]["geography_name"] == name
        assert source[code]["geography_vintage"] == "nis_2025"
        assert source[code]["geography_level"] == "commune"
        assert source[code]["nuts1_id"] == "BE3"
    assert {fact.geography.level for fact in facts} == {"statistical_scope"}
    assert len({fact.geography.id for fact in facts}) == 1
    assert len({fact.geography.name for fact in facts}) == 1
    assert all(fact.geography.name for fact in facts)
    # The publisher's own wording for the area, printed in the article.
    assert facts[0].geography.name == "Deutschsprachige Gemeinschaft"
    assert facts[0].geography.name in CAPTURE.read_text(encoding="utf-8")
    manifest = yaml.safe_load((DATA_DIR / "manifest.yaml").read_text(encoding="utf-8"))
    scope = manifest["geography_scope"]
    assert scope["level"] == "statistical_scope"
    assert scope["vintage"] == "nis_2025"
    assert "not a NUTS region" in scope["definition"]
    assert {
        member["nis_2025"]: member["geography_name"] for member in scope["communes"]
    } == COMMUNES
    assert all(fact.geography.id == scope["id"] for fact in facts)
    assert all(fact.geography.name == scope["name"] for fact in facts)
    readme = (PACKAGE_DIR / "README.md").read_text(encoding="utf-8")
    for code, name in COMMUNES.items():
        assert code in readme and name in readme
    assert "no licence stated; figures cited with attribution" in readme
