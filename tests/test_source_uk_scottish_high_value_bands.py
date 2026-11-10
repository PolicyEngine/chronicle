"""The Scottish Government's Band I and J estimates for PolicyEngine/chronicle#420 item 13.

Checks the package scripts/build_uk_scottish_high_value_bands_package.py writes from the
"Council Tax High-Value Property Bands (Mansion Tax): consultation" paper. The figures'
data labels are re-read from the pinned PDF with pypdf, in the order the charts print
them, and each fact is matched by its own band and estimate bound.
"""

from __future__ import annotations

import hashlib
import io
import re
import runpy
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import (
    build_semantic_fact_key,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "scotgov-council-tax-high-value-bands-consultation-2026"
DIRECTORY = "scotgov/council_tax_high_value_bands_consultation_2026"
DATA = ROOT / "db/data" / DIRECTORY
PROPERTIES = "scotgov.council_tax.high_value_band_properties_estimate"
REVENUE = "scotgov.council_tax.high_value_band_additional_revenue_estimate"
# The charts print the low estimates for Band I and Band J, then the high estimates.
ORDER = (
    ("I", "low_estimate"),
    ("J", "low_estimate"),
    ("I", "high_estimate"),
    ("J", "high_estimate"),
)


@pytest.fixture(scope="module")
def built():
    package = load_source_package(PACKAGE_ID)
    return package, package.build_facts(2026)


@pytest.fixture(scope="module")
def page_lines():
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text())
    ((_, entry),) = manifest["files"].items()
    content = (DATA / entry["filename"]).read_bytes()
    text = PdfReader(io.BytesIO(content)).pages[8].extract_text()
    return [" ".join(line.split()) for line in text.splitlines()]


def _by_key(facts, concept: str) -> dict[tuple[str, str], float]:
    return {
        (fact.filters["council_tax_band"], fact.filters["statistic"]): fact.value
        for fact in facts
        if fact.measure.concept == concept
    }


def test_package_validates_registers_and_carries_no_anchors(built):
    package, facts = built
    report = validate_source_package(package.package_path, year=2026)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["source_record_count"] == len(facts) == 8
    assert SOURCE_PACKAGE_ALIASES[PACKAGE_ID] == Path(DIRECTORY)
    assert PACKAGE_ID in UK_BUNDLE_SOURCES
    text = (package.package_path / "source_package.yaml").read_text(encoding="utf-8")
    assert not re.search(r"(:|^\s*-)\s+[&*][A-Za-z_][\w-]*\s*$", text, re.M)
    assert validate_facts(facts).valid
    assert len({build_semantic_fact_key(fact) for fact in facts}) == 8
    assert len(package.build_facts(2023)) == 8


def test_generator_reproduces_the_committed_package():
    generator = runpy.run_path(
        str(ROOT / "scripts/build_uk_scottish_high_value_bands_package.py")
    )
    ((directory, build),) = generator["BUILDERS"].items()
    committed = ROOT / "packages" / directory / "source_package.yaml"
    assert build() == committed.read_text(encoding="utf-8")


def test_manifest_pins_bytes_licence_and_the_r2_key():
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["source_id"] == "scotgov"
    assert manifest["package_id"] == PACKAGE_ID
    assert manifest["license"] == "Open Government Licence v3.0"
    assert (
        "This publication is licensed under the terms of the Open Government"
        in (manifest["license_evidence"])
    )
    ((year, entry),) = manifest["files"].items()
    content = (DATA / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    key = f"raw/uk/scotgov/{PACKAGE_ID}/{year}/{entry['sha256']}/{entry['filename']}"
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }


def test_consumer_contract_is_valid(built):
    _, facts = built
    report = validate_consumer_fact_contract(facts)
    assert report.valid, report.errors[:3]
    assert all(fact.source.raw_r2_uri for fact in facts)


def test_facts_are_the_charts_data_labels(built, page_lines):
    _, facts = built
    # Figure 3's four data labels sit just above its legend, Figure 2's just below it.
    legend = page_lines.index(
        "Band I (£1m to £2m)Band J (more than £2m)Estimated Number of Properties,"
        "low estimateEstimated Number of Properties,high estimate"
    )
    counts = [
        int(line.split(" ")[0].replace(",", ""))
        for line in page_lines[legend - 4 : legend]
    ]
    millions = [float(line) for line in page_lines[legend + 1 : legend + 5]]
    assert page_lines[legend + 7] == "£ millions"
    assert page_lines[legend + 8] == (
        "Estimated Additional Revenue,low estimateEstimated Additional Revenue,high estimate"
    )
    assert _by_key(facts, PROPERTIES) == dict(zip(ORDER, counts))
    assert _by_key(facts, REVENUE) == {
        key: round(value * 1_000_000) for key, value in zip(ORDER, millions)
    }


def test_ranges_match_the_papers_own_statements(built):
    _, facts = built
    counts, revenue = _by_key(facts, PROPERTIES), _by_key(facts, REVENUE)
    for values in (counts, revenue):
        for band in "IJ":
            assert values[(band, "low_estimate")] < values[(band, "high_estimate")]
        for bound in ("low_estimate", "high_estimate"):
            assert values[("I", bound)] > values[("J", bound)]
    # "approximately 15,000 properties in total"
    low = counts[("I", "low_estimate")] + counts[("J", "low_estimate")]
    high = counts[("I", "high_estimate")] + counts[("J", "high_estimate")]
    assert low < 15_000 < high
    # "between £12 million and £16 million per year in total across Scotland"
    low = revenue[("I", "low_estimate")] + revenue[("J", "low_estimate")]
    high = revenue[("I", "high_estimate")] + revenue[("J", "high_estimate")]
    assert (round(low / 1e6), round(high / 1e6)) == (12, 16)


def test_estimates_carry_their_semantics(built):
    _, facts = built
    for fact in facts:
        assert fact.geography.id == "S92000003"
        assert fact.provenance_class == "model_output"
        assert set(fact.filters) == {"council_tax_band", "statistic"}
        assert "illustrative" in fact.measure.concept_evidence_notes
        if fact.measure.concept == PROPERTIES:
            assert (fact.period.type, fact.period.value) == ("month", "2026-04")
            assert fact.assertion == "observation"
            assert fact.entity.name == "dwelling"
            assert fact.measure.unit == "count"
        else:
            assert fact.measure.concept == REVENUE
            assert (fact.period.type, str(fact.period.value)) == ("fiscal_year", "2026")
            assert fact.assertion == "source_projection"
            assert fact.entity.name == "government"
            assert fact.measure.unit == "gbp"
