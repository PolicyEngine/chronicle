"""Exact publisher values and lineage for Eurostat's annual USD exchange rates."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from yaml.tokens import AliasToken, AnchorToken

from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import build_fact_key, validate_facts
from chronicle.source_package import load_source_package, validate_source_package
from chronicle.sources.cells import build_source_cell_key, validate_source_cells
from chronicle.sources.rows import build_source_row_key, validate_source_rows

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages/eurostat/ert_bil_eur_a_usd"
DATA = ROOT / "db/data/eurostat/ert_bil_eur_a_usd"
RAW = DATA / "ert_bil_eur_a_USD.json"
SHA256 = "3c96ca57c15266d07e1976d90ba806a5bb90ab46a503b6311df3aaa9f5ba66c7"
SOURCE_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
    "ert_bil_eur_a?currency=USD&statinfo=AVG&format=JSON&lang=EN"
)


@pytest.fixture(scope="module")
def published_cells():
    """Decode cube indexes independently of the package and Chronicle parser."""
    payload = json.loads(RAW.read_text(), parse_float=Decimal)
    cells = {}
    for flat_index, value in payload["value"].items():
        remaining = int(flat_index)
        coordinates = {}
        for dimension, size in reversed(
            list(zip(payload["id"], payload["size"], strict=True))
        ):
            remaining, position = divmod(remaining, size)
            indexes = payload["dimension"][dimension]["category"]["index"]
            coordinates[dimension] = next(
                code for code, index in indexes.items() if index == position
            )
        assert remaining == 0
        cells[int(flat_index)] = (coordinates, value)
    return cells


@pytest.fixture(scope="module")
def package_data():
    package = load_source_package(PACKAGE)
    rows = package.build_source_rows(2024)
    cells = package.build_source_cells(2024, source_rows=rows)
    facts = package.build_facts(2024, cells=cells, source_rows=rows)
    return package, rows, cells, facts


def test_capture_is_hash_pinned_and_declares_content_addressed_r2_storage():
    content = RAW.read_bytes()
    assert len(content) == 4488
    assert hashlib.sha256(content).hexdigest() == SHA256
    payload = json.loads(content)
    assert payload["updated"] == "2026-07-08T11:00:00+0200"
    artifact = yaml.safe_load((DATA / "manifest.yaml").read_text())["files"][2026]
    assert artifact["filename"] == RAW.name
    assert artifact["sha256"] == SHA256
    assert artifact["size_bytes"] == len(content)
    assert artifact["source_url"] == SOURCE_URL
    assert artifact["retrieved_at"] == "2026-10-23"
    assert "CC BY 4.0" in artifact["license"]
    storage = artifact["storage"]["r2"]
    assert storage["provider"] == "r2"
    assert storage["bucket"] == "ledger-raw"
    assert storage["key"] == (
        f"raw/eurostat/eurostat-ert-bil-eur-a-usd/2026/{SHA256}/{RAW.name}"
    )
    assert storage["uri"] == f"r2://ledger-raw/{storage['key']}"
    assert "upload is pending" in artifact["notes"]
    assert "ECB reference rates" in artifact["notes"]


def test_full_source_rows_preserve_every_json_stat_observation(
    package_data, published_cells
):
    package, rows, cells, _ = package_data
    assert package.artifact.parser == "json_stat_2_full_rows"
    assert not package.artifact.selected_rows
    assert len(rows) == len(published_cells) == 55
    assert len(cells) == 56 * 13  # Header plus every data row, including labels.
    assert {row.values["source_index"] for row in rows} == set(range(55))
    for row in rows:
        index = row.values["source_index"]
        coordinates, value = published_cells[index]
        assert row.row_number == index + 1
        assert {dimension: row.values[dimension] for dimension in coordinates} == (
            coordinates
        )
        assert Decimal(str(row.values["value"])) == value
        assert row.values["status"] is None


def test_every_published_year_becomes_exactly_one_untransformed_fact(
    package_data, published_cells
):
    facts = package_data[3]
    expected = {
        int(coordinates["time"]): value
        for coordinates, value in published_cells.values()
    }
    assert len(facts) == len(expected) == 55
    assert {fact.period.value for fact in facts} == set(range(1971, 2026))
    assert {fact.period.value: Decimal(str(fact.value)) for fact in facts} == expected
    assert len({build_fact_key(fact) for fact in facts}) == 55


@pytest.mark.parametrize(
    ("year", "value"),
    [
        (1971, "1.0478"),
        (1999, "1.0658"),
        (2000, "0.9236"),
        (2024, "1.0824"),
        (2025, "1.1300"),
    ],
)
def test_independent_sample_values_keep_the_published_direction(
    package_data, published_cells, year, value
):
    coordinates, published_value = next(
        cell for cell in published_cells.values() if cell[0]["time"] == str(year)
    )
    assert coordinates == {
        "freq": "A",
        "statinfo": "AVG",
        "unit": "NAC",
        "currency": "USD",
        "time": str(year),
    }
    assert published_value == Decimal(value)
    fact = next(fact for fact in package_data[3] if fact.period.value == year)
    assert Decimal(str(fact.value)) == published_value
    assert fact.measure.unit == "usd_per_eur"


def test_facts_keep_publisher_period_mean_and_currency_market_scope(package_data):
    for fact in package_data[3]:
        assert fact.period.type == "calendar_year"
        assert fact.measure.unit == "usd_per_eur"
        assert fact.aggregation.method == "mean"
        assert fact.provenance_class == "administrative"
        assert fact.assertion == "observation"
        assert fact.survey_instrument is None
        assert fact.geography.level == "statistical_scope"
        assert fact.geography.id == "eurostat:ert_bil_eur_a:USD"
        assert fact.entity.name == "institutional_sector"
        assert fact.entity.role == "currency_market"
        assert fact.layout.groupby_dimension == "currency"
        assert fact.layout.groupby_value_id == "USD"
        assert fact.filters == {
            "freq": "A",
            "statinfo": "AVG",
            "unit": "NAC",
            "currency": "USD",
            "time": fact.period.value,
        }
        assert {
            (constraint.variable, constraint.operator, constraint.value)
            for constraint in fact.constraints
        } == {(key, "==", value) for key, value in fact.filters.items()}
        assert fact.source.source_name == "eurostat"
        assert fact.source.source_sha256 == SHA256
        assert fact.source.source_size_bytes == 4488
        assert fact.source.url == SOURCE_URL
        assert fact.source.vintage == "eurostat_ert_bil_eur_a_usd_updated_2026_07_08"
        assert fact.source.extracted_at == "2026-10-23"


def test_every_fact_traces_its_value_and_all_dimension_guards_to_raw_rows(
    package_data, published_cells
):
    _, rows, cells, facts = package_data
    by_cell_key = {build_source_cell_key(cell): cell for cell in cells}
    by_row_key = {build_source_row_key(row): row for row in rows}
    for fact in facts:
        source_index, (coordinates, value) = next(
            item
            for item in published_cells.items()
            if item[1][0]["time"] == str(fact.period.value)
        )
        virtual_row = source_index + 2
        lineage = {
            by_cell_key[key].address: by_cell_key[key] for key in fact.source_cell_keys
        }
        assert set(lineage) == {
            "F1",
            *(f"{column}{virtual_row}" for column in "ABCDEF"),
        }
        assert lineage["F1"].raw_value == "value"
        for column, dimension in zip(
            "ABCDE", ("freq", "statinfo", "unit", "currency", "time"), strict=True
        ):
            assert (
                str(lineage[f"{column}{virtual_row}"].raw_value)
                == (coordinates[dimension])
            )
        value_cell = lineage[f"F{virtual_row}"]
        assert Decimal(str(value_cell.raw_value)) == value
        assert value_cell.sheet_name == "ert_bil_eur_a"
        assert value_cell.source_row_key in by_row_key
        source_row = by_row_key[value_cell.source_row_key]
        assert source_row.values["source_index"] == source_index
        assert fact.source_row_keys == (value_cell.source_row_key,)
        assert all(
            cell.source_row_key == value_cell.source_row_key
            for address, cell in lineage.items()
            if address != "F1"
        )
        notes = fact.measure.concept_evidence_notes
        assert f"value['{source_index}']" in notes
        assert f"row {virtual_row}, column F" in notes
        assert "ECB reference rates" in notes


def test_package_rows_cells_facts_and_consumer_contract_validate(package_data):
    _, rows, cells, facts = package_data
    reports = [
        validate_source_package(PACKAGE, year=2024),
        validate_source_rows(rows),
        validate_source_cells(cells),
        validate_facts(facts),
        validate_consumer_fact_contract(facts),
    ]
    for report in reports:
        assert report.valid, report.to_dict()
    consumer_rows = consumer_fact_rows(facts)
    assert len(consumer_rows) == 55
    assert {row["assertion"] for row in consumer_rows} == {"observation"}
    assert {row["provenance_class"] for row in consumer_rows} == {"administrative"}


def test_other_build_years_preserve_the_same_publisher_years(package_data):
    package, rows, cells, facts = package_data
    off_year = package.build_facts(2030, cells=cells, source_rows=rows)
    assert off_year == facts
    assert {fact.period.value for fact in off_year} == set(range(1971, 2026))
    assert validate_source_package(PACKAGE, year=2030).valid


def test_generator_reproduces_files_with_textual_provenance_and_no_aliases():
    script = PACKAGE / "build_package.py"
    spec = importlib.util.spec_from_file_location(
        "eurostat_exchange_rate_generator", script
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    generated = module.generate()
    assert set(generated) == {DATA / "manifest.yaml", PACKAGE / "source_package.yaml"}
    assert generated == module.generate()
    for path, text in generated.items():
        assert text == path.read_text()
        assert not any(
            isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(text)
        )
    package_text = generated[PACKAGE / "source_package.yaml"]
    payload = yaml.safe_load(package_text)
    assert len(payload["record_sets"]) == 55
    assert package_text.count("provenance_class: administrative") == 55
    for record_set in payload["record_sets"]:
        assert record_set["provenance_class"] == "administrative"
        assert len(record_set["rows"]) == len(record_set["measures"]) == 1
        assert record_set["measures"][0]["value_scale"] == 1
