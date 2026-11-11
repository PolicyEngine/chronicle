"""Independent source audits for FPS Finance's assessment-year 2026 rates."""

from __future__ import annotations

import csv
import hashlib
import re
import runpy
import unicodedata
from collections import Counter
from dataclasses import replace
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

from chronicle.bundle import _dimension_label_reports, build_bundle_coverage
from chronicle.consumer_contract import (
    build_aggregate_fact_key,
    build_semantic_fact_key,
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources.cells import build_source_cell_key, validate_source_cells

REPO_ROOT = Path(__file__).resolve().parents[1]
ALIAS = "spf-finances-municipal-tax-rate-ay2026"
PACKAGE_DIR = REPO_ROOT / "packages/spf_finances/municipal_tax_rate_ay2026"
DATA_DIR = REPO_ROOT / "db/data/spf_finances/municipal_tax_rate_ay2026"
RAW_PATH = DATA_DIR / "municipal-tax-rate-2026.pdf"
CSV_PATH = DATA_DIR / "spf_finances_municipal_tax_rate_ay2026.csv"
AUDIT_PATH = PACKAGE_DIR / "commune_mapping_audit.csv"
STATBEL_PATH = (
    REPO_ROOT
    / "db/data/statbel/population_structure_commune_2025"
    / "statbel_population_structure_commune_2025.csv"
)
RAW_SHA256 = "051211d85f05367002c31ad1879b294af50b8c14119d2127451bc976bd5e1606"
NORMALIZED_LABELS = {
    "Blégny",
    "Braine-l'Alleud",
    "Fontaine-l'Evêque",
    "Les-Bons-Villers",
    "Mont-de-l'Enclus",
    "Ottignies-Louvain-La-Neuve",
    "Villers-le-Bouillet",
}
# Communes whose SPF-printed name differs from Statbel's canonical name. Facts
# carry the publisher's wording (harness, chronicle#266); identity is the NIS code.
PUBLISHER_NAME_DIFFERS = {
    "21004": ("Bruxelles", "Brussels"),
    "25014": ("Braine-l'Alleud", "Braine-l’Alleud"),
    "25121": ("Ottignies-Louvain-La-Neuve", "Ottignies-Louvain-la-Neuve"),
    "52022": ("Fontaine-l'Evêque", "Fontaine-l’Evêque"),
    "52075": ("Les-Bons-Villers", "Les Bons Villers"),
    "57095": ("Mont-de-l'Enclus", "Mont-de-l’Enclus"),
    "61068": ("Villers-le-Bouillet", "Villers-Le-Bouillet"),
    "62119": ("Blégny", "Blegny"),
    "63080": ("Waimes", "Weismes"),
}


def _csv_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _orthographic_key(text):
    # This intentionally does not call the generator's normalization helper.
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    unaccented = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[\s\-'’]", "", unaccented)


@pytest.fixture(scope="module")
def curated_rows():
    return _csv_rows(CSV_PATH)


@pytest.fixture(scope="module")
def statbel_communes():
    communes = {}
    for row in _csv_rows(STATBEL_PATH):
        code = row["geography_id"]
        if code in communes:
            for name in (
                "geography_name",
                "source_municipality_nl",
                "source_municipality_fr",
            ):
                assert communes[code][name] == row[name]
        communes[code] = row
    assert len(communes) == 565
    return communes


@pytest.fixture(scope="module")
def publisher_rows():
    """Read every printed cell by visual column, independently of the generator.

    Layout extraction puts rates beside the first line of a wrapped name. The
    generator instead uses the default extraction's sequential text lines.
    Header gaps determine the three visual blocks, avoiding fixed PDF widths.
    """
    document = PdfReader(RAW_PATH)
    assert len(document.pages) == 5
    assert document.metadata.title == "Municipal tax rate | FPS Finance"
    result = []
    for page_number, page in enumerate(document.pages, start=1):
        lines = page.extract_text(extraction_mode="layout").splitlines()
        header_number, header = next(
            (number, text)
            for number, text in enumerate(lines)
            if "CITY OR MUNICIPALITY" in text
        )
        starts = [
            match.start() for match in re.finditer("CITY OR MUNICIPALITY", header)
        ]
        ends = [match.end() for match in re.finditer(r"Rate \(%\)", header)]
        assert len(starts) == len(ends) == 3
        boundaries = [
            0,
            *((ends[index] + starts[index + 1]) // 2 for index in range(2)),
            None,
        ]
        for block, (start, end) in enumerate(pairwise(boundaries), start=1):
            current = None
            for line in lines[header_number + 1 :]:
                if re.fullmatch(r"\s*\d / 5\s*", line):
                    break
                chunk = line[start:end].strip()
                if not chunk:
                    continue
                match = re.fullmatch(r"(.+?)\s+(\d+,\d+)", chunk)
                if match:
                    if current is not None:
                        result.append(current)
                    current = {
                        "publisher_commune": match[1],
                        "source_rate_text": match[2],
                        "source_page": page_number,
                        "source_column_block": block,
                    }
                else:
                    assert current is not None, (page_number, block, chunk)
                    assert current["publisher_commune"].endswith("-"), current
                    current["publisher_commune"] += chunk
            if current is not None:
                result.append(current)
    assert len(result) == 565
    assert len({row["publisher_commune"] for row in result}) == 565
    return result


@pytest.fixture(scope="module")
def municipal_rates():
    package = load_source_package(ALIAS)
    source_rows = package.build_source_rows(2025)
    cells = package.build_source_cells(2025, source_rows=source_rows)
    facts = package.build_facts(2025, source_rows=source_rows, cells=cells)
    return package, cells, facts


def test_every_published_cell_and_exact_pdf_locator_is_preserved(
    curated_rows, publisher_rows
):
    expected = {row["publisher_commune"]: row for row in publisher_rows}
    actual = {row["publisher_commune"]: row for row in curated_rows}
    assert len(curated_rows) == len(actual) == 565
    assert actual.keys() == expected.keys()
    document = PdfReader(RAW_PATH)
    page_lines = [page.extract_text().splitlines() for page in document.pages]
    for label, row in actual.items():
        published = expected[label]
        assert Decimal(row["value"]) == Decimal(
            published["source_rate_text"].replace(",", ".")
        )
        assert row["source_rate_text"] == published["source_rate_text"]
        assert int(row["source_page"]) == published["source_page"]
        assert int(row["source_column_block"]) == published["source_column_block"]
        assert row["source_sha256"] == RAW_SHA256
        lines = page_lines[int(row["source_page"]) - 1]
        start = int(row["source_line_start"])
        end = int(row["source_line_end"])
        rate_line = int(row["source_rate_line"])
        assert 1 <= start <= rate_line <= end <= len(lines)
        fragments = [line.strip() for line in lines[start - 1 : end]]
        assert fragments
        assert sum("CITY OR MUNICIPALITY" in line for line in lines[:start]) == int(
            row["source_column_block"]
        )
        text = " ".join(fragments)
        assert text.endswith(row["source_rate_text"])
        assert lines[rate_line - 1].strip().endswith(row["source_rate_text"])
        # The default text stream puts a wrapped name on successive lines,
        # followed by its rate. Join only its printed hyphenated line breaks.
        name = text[: -len(row["source_rate_text"])].strip()
        assert re.sub(r"-\s+", "-", name) == label


def test_mapping_is_bijective_and_matches_statbel_names_including_german_communes(
    curated_rows, statbel_communes
):
    assert {row["geography_id"] for row in curated_rows} == statbel_communes.keys()
    assert Counter(row["geography_id"] for row in curated_rows) == {
        code: 1 for code in statbel_communes
    }
    normalized = set()
    differing = {}
    for row in curated_rows:
        label = row["publisher_commune"]
        exact = {
            code
            for code, commune in statbel_communes.items()
            if label
            in (commune["source_municipality_nl"], commune["source_municipality_fr"])
        }
        if exact:
            assert exact == {row["geography_id"]}
            assert row["match_tier"] == "exact_statbel"
        else:
            candidates = {
                code
                for code, commune in statbel_communes.items()
                if _orthographic_key(label)
                in {
                    _orthographic_key(commune["source_municipality_nl"]),
                    _orthographic_key(commune["source_municipality_fr"]),
                }
            }
            assert candidates == {row["geography_id"]}
            assert row["match_tier"] == "orthographic_normalization"
            normalized.add(label)
        assert row["geography_name"] == label
        statbel_name = statbel_communes[row["geography_id"]]["geography_name"]
        if label != statbel_name:
            differing[row["geography_id"]] = (label, statbel_name)
        assert row["geography_level"] == "commune"
        assert row["geography_vintage"] == "nis_2025"
        assert row["period"] == "2025"
        # Source-row evidence for the record set's year constraints.
        assert (row["income_year"], row["assessment_year"]) == ("2025", "2026")
    assert normalized == NORMALIZED_LABELS
    assert differing == PUBLISHER_NAME_DIFFERS
    assert Counter(row["match_tier"] for row in curated_rows) == {
        "exact_statbel": 558,
        "orthographic_normalization": 7,
    }
    by_name = {row["publisher_commune"]: row for row in curated_rows}
    for label in (
        "Amel",
        "Büllingen",
        "Bütgenbach",
        "Burg-Reuland",
        "Eupen",
        "Kelmis",
        "Lontzen",
        "Raeren",
        "Sankt Vith",
    ):
        row = by_name[label]
        assert row["match_tier"] == "exact_statbel"
        commune = statbel_communes[row["geography_id"]]
        assert label in (
            commune["source_municipality_nl"],
            commune["source_municipality_fr"],
        )
    assert {
        "Beveren-Kruibeke-Zwijndrecht",
        "Bilzen-Hoeselt",
        "Tongeren-Borgloon",
        "Pajottegem",
    } <= by_name.keys()
    assert "Borsbeek" not in by_name


def test_mapping_audit_preserves_every_source_cell_and_matching_evidence(
    curated_rows, statbel_communes
):
    audit = _csv_rows(AUDIT_PATH)
    assert len(audit) == 565
    by_label = {row["publisher_commune"]: row for row in audit}
    assert len(by_label) == len(audit)
    for row in curated_rows:
        evidence = by_label[row["publisher_commune"]]
        assert {key: evidence[key] for key in row} == row
        commune = statbel_communes[row["geography_id"]]
        for field in ("source_municipality_nl", "source_municipality_fr"):
            assert evidence[field] == commune[field]
        assert evidence["statbel_geography_name"] == commune["geography_name"]


def test_alias_validation_and_explicit_provenance():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == Path(
        "spf_finances/municipal_tax_rate_ay2026"
    )
    report = validate_source_package(ALIAS, year=2025)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["row_count"] == report.counts["source_record_count"] == 565
    source = (PACKAGE_DIR / "source_package.yaml").read_text()
    payload = yaml.safe_load(source)
    assert all(
        record_set["provenance_class"] == "administrative"
        for record_set in payload["record_sets"]
    )
    assert sum(
        line.strip() == "provenance_class: administrative"
        for line in source.splitlines()
    ) == len(payload["record_sets"])
    assert not any(
        isinstance(token, (yaml.AliasToken, yaml.AnchorToken))
        for token in yaml.scan(source)
    )


def test_rates_preserve_published_tax_period_unit_and_source_lineage(
    municipal_rates, curated_rows
):
    package, cells, facts = municipal_rates
    assert len(facts) == 565
    assert validate_source_cells(cells).valid
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    cell_keys = {build_source_cell_key(cell) for cell in cells}
    by_code = {row["geography_id"]: row for row in curated_rows}
    for fact in facts:
        row = by_code[fact.geography.id]
        assert Decimal(str(fact.value)) == Decimal(row["value"])
        assert fact.entity.name == "government"
        assert fact.measure.unit == "percent"
        assert fact.aggregation.method == "rate"
        assert fact.provenance_class == "administrative"
        assert fact.assertion == "observation"
        # Income-year key, as in the other Belgian tax packages; the printed
        # assessment year survives in the label and the constraint below.
        assert (fact.period.type, fact.period.value) == ("tax_year", 2025)
        coverage = fact.period_coverage
        assert coverage is not None
        assert coverage.basis == "tax"
        assert coverage.source_period_label == "for tax assessment year 2026"
        assert "2025" in coverage.notes
        assert fact.geography.name == row["publisher_commune"]
        assert fact.geography.vintage == "nis_2025"
        # The NIS code identifies the commune; its spelling is not identity.
        assert not fact.filters
        assert {constraint.variable for constraint in fact.constraints} == {
            "income_year",
            "assessment_year",
        }
        assert fact.source_record_id
        assert fact.source_row_keys
        assert fact.source_cell_keys
        assert set(fact.source_cell_keys) <= cell_keys
    assert package.artifact.artifact_year == 2025
    payload = yaml.safe_load((PACKAGE_DIR / "source_package.yaml").read_text())
    (record_set,) = payload["record_sets"]
    assert record_set["shared_constraints"] == [
        {
            "variable": "income_year",
            "operator": "==",
            "value": 2025,
            "label": "Publisher income year",
        },
        {
            "variable": "assessment_year",
            "operator": "==",
            "value": 2026,
            "label": "Publisher assessment year",
        },
    ]


def _respell(fact, old, new):
    """Replace a printed name wherever a fact carries it: name, filters, constraints."""
    return replace(
        fact,
        geography=replace(fact.geography, name=new),
        filters={
            key: new if value == old else value for key, value in fact.filters.items()
        },
        constraints=tuple(
            replace(constraint, value=new) if constraint.value == old else constraint
            for constraint in fact.constraints
        ),
    )


def test_printed_spelling_never_changes_fact_identity(
    municipal_rates, statbel_communes
):
    """For every fact, respelling its commune leaves both keys unchanged.

    The NIS code is the identity; the printed name is a label (fact identity
    ADR v2). Changing the code, by contrast, must change the keys.
    """
    _, _, facts = municipal_rates
    codes = sorted(statbel_communes)
    for fact in facts:
        keys = (build_aggregate_fact_key(fact), build_semantic_fact_key(fact))
        name = fact.geography.name
        spellings = {
            statbel_communes[fact.geography.id]["geography_name"],
            name.casefold(),
            name.upper(),
            _orthographic_key(name),
        } - {name}
        assert spellings
        for spelling in spellings:
            respelled = _respell(fact, name, spelling)
            assert (
                build_aggregate_fact_key(respelled),
                build_semantic_fact_key(respelled),
            ) == keys
        other = codes[(codes.index(fact.geography.id) + 1) % len(codes)]
        moved = replace(fact, geography=replace(fact.geography, id=other))
        assert build_aggregate_fact_key(moved) != keys[0]
        assert build_semantic_fact_key(moved) != keys[1]


def test_source_capture_hash_and_r2_storage_are_declared():
    manifest = yaml.safe_load((DATA_DIR / "manifest.yaml").read_text())
    assert manifest["source_id"] == "belgium"
    assert manifest["package_id"] == ALIAS
    by_filename = {entry["filename"]: entry for entry in manifest["files"].values()}
    assert RAW_PATH.name in by_filename
    assert CSV_PATH.name in by_filename
    for path in (RAW_PATH, CSV_PATH):
        content = path.read_bytes()
        entry = by_filename[path.name]
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]
        assert len(content) == entry["size_bytes"]
        storage = entry["storage"]["r2"]
        assert storage["provider"] == "r2"
        assert storage["bucket"] == "ledger-raw"
        assert storage["key"].startswith(f"raw/belgium/{ALIAS}/")
        assert storage["key"].endswith(f"/{entry['sha256']}/{path.name}")
        assert storage["uri"] == f"r2://ledger-raw/{storage['key']}"
    assert by_filename[RAW_PATH.name]["sha256"] == RAW_SHA256
    assert by_filename[RAW_PATH.name]["size_bytes"] == 182_097
    capture = by_filename[RAW_PATH.name]
    assert capture["retrieved_at"] == "2026-10-23"
    assert capture["source_url"].endswith(
        "/sites/default/files/media/documents/municipal-tax-rate-2026.pdf"
    )
    assert {row["source_url"] for row in _csv_rows(CSV_PATH)} == {capture["source_url"]}


def test_source_only_coverage_and_identity_do_not_add_duplicate_facts(municipal_rates):
    _, _, facts = municipal_rates
    rows = consumer_fact_rows(facts)
    assert _dimension_label_reports(ALIAS, rows) == ([], [])
    coverage = build_bundle_coverage(rows)
    assert coverage["fact_count"] == 565
    assert coverage["counts"]["by_period"] == {"tax_year:2025": 565}
    assert coverage["counts"]["by_entity"] == {"government": 565}
    assert coverage["counts"]["by_source"] == {"spf_finances_municipal_tax_rate": 565}
    assert coverage["counts"]["by_source_table"] == {
        "spf_finances_municipal_tax_rate:Municipal tax rates (%) "
        "for tax assessment year 2026": 565
    }
    assert len(coverage["counts"]["by_geography"]) == 565
    assert set(coverage["counts"]["by_geography"].values()) == {1}
    assert not coverage["duplicates"]["aggregate_fact_keys"]
    assert not coverage["duplicates"]["semantic_fact_keys"]
    for row in rows:
        assert row["lineage"]["source_cell_keys"]
        assert row["source"]["raw_r2_key"].startswith(f"raw/belgium/{ALIAS}/")
        assert not {"target", "solver", "calibration", "uprating_factor"} & row.keys()


def test_generator_reproduces_all_curated_and_declared_bytes():
    generator = runpy.run_path(str(PACKAGE_DIR / "build_package.py"))
    outputs = generator["render_outputs"]()
    assert {
        CSV_PATH,
        AUDIT_PATH,
        DATA_DIR / "manifest.yaml",
        PACKAGE_DIR / "source_package.yaml",
    } <= outputs.keys()
    for path, expected in outputs.items():
        assert path.read_bytes() == expected, path.relative_to(REPO_ROOT)


def test_mapping_fails_closed_for_unresolved_ambiguous_and_duplicate_communes():
    generator = runpy.run_path(str(PACKAGE_DIR / "build_package.py"))
    communes = generator["load_communes"]()
    with pytest.raises(ValueError, match="(?i)unresolved|not match|unknown"):
        generator["match_commune"]("Not a Belgian municipality", communes)
    duplicated = dict(communes)
    duplicated["99999"] = dict(communes["11001"])
    with pytest.raises(ValueError, match="(?i)ambiguous"):
        generator["match_commune"]("Aartselaar", duplicated)
    source_rows = generator["parse_pdf"]()
    with pytest.raises(ValueError, match="(?i)duplicate|bijective|unique"):
        generator["assemble_rows"](source_rows=[*source_rows, source_rows[0]])


def test_geography_guard_rejects_semantic_drift(municipal_rates):
    package, cells, _ = municipal_rates
    changed = [
        replace(cell, raw_value="99999", display_value="99999")
        if cell.address == "C2"
        else cell
        for cell in cells
    ]
    with pytest.raises(ValueError, match="expected"):
        package.build_facts(2025, cells=changed)
