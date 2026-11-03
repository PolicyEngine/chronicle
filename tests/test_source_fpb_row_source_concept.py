"""Row-grain source concepts on the FPB June 2026 outlook annex.

Each annex row is its own publisher series. A table-wide source concept
(``…t07.published_cell``) gave every row of a table one observed concept, so a
consumer that reads the source concept as series identity, as Microcosm's
roll-forward check does, took total population and working-age population for
one series. Each fact now names its table and row. That moves every key that
hashes the observed concept (the aggregate, legacy, observed-measure and
concept-alignment keys) and the record set's spec hash, and leaves the semantic
key and the value alone.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from functools import lru_cache

import pytest
import yaml

from chronicle.consumer_contract import consumer_fact_rows
from chronicle.source_package import load_source_package

FPB_OUTLOOK = "fpb-economic-outlook-2026-2031-june-2026"
PREFIX = "fpb.economic_outlook_2026_2031"
BUILD_YEARS = (2023, 2026)
ANNEX_YEARS = list(range(2022, 2032))
TABLE_ROWS = {"t01": 4, "t06": 3, "t07": 10, "t11": 21, "t17": 7, "t24": 55}
# sha256 of the sorted [source_record_id, semantic_fact_key, value] rows. The
# same digest holds at 2c7e8357, before the row-grain concepts.
SEMANTIC_DIGEST = "a60a849390016a2da1ed6ca512e9107b571bf0be7dabd8ad33ec9d34d0d0dabb"
# sha256 of the sorted [source_record_id, aggregate_fact_key, legacy_fact_key,
# observed_measure_key, concept_alignment_key] rows under the row-grain concepts.
ROW_KEY_DIGEST = "d9795cd83b3f8dc6d141f5c4f22dcf21f3b28d917cfdaf1382fdcfa7439005f2"
# Publisher row headers, read from column A of DATA_FOR_MLT_FR.xlsx: all ten T07
# rows and a sample of every other table. The package guard ties each header to
# its cell; this table ties each row id, and so each source concept, to its
# header. A consistent swap of ids and concepts between two rows breaks it.
ROW_HEADERS = {
    ("t01", "national_consumer_price_index"): (
        "Indice national des prix à la consommation"
    ),
    ("t06", "gross_domestic_product_at_market_prices"): (
        "1. Produit intérieur brut aux prix du marché"
    ),
    ("t07", "total_population"): "I. Population totale (II+III)",
    ("t07", "working_age_population"): "I.bis Population d'âge actif (15-64 ans)",
    ("t07", "domestic_employment"): "IV. Emploi intérieur",
    ("t07", "domestic_employment_private_sector_employees"): (
        "(a) Salariés du secteur privé"
    ),
    ("t07", "domestic_employment_self_employed"): "(b) Indépendants",
    ("t07", "domestic_employment_public_sector_employees"): (
        "(c) Salariés du secteur public"
    ),
    ("t07", "bfp_unemployment"): "VI. Chômage (concept BFP)",
    ("t07", "bfp_unemployment_registered_jobseekers"): (
        "(a) Demandeurs d'emploi inoccupés (1)"
    ),
    ("t07", "bfp_unemployment_older_non_jobseekers"): (
        "(b) Chômeurs âgés non demandeurs d'emploi (2)"
    ),
    ("t07", "bfp_unemployment_rate"): "Taux de chômage (VI)/(III)",
    ("t11", "total_resources"): "a. Ressources",
    ("t11", "net_property_income"): "4. Revenus nets de la propriété",
    ("t11", "interest_paid"): "Intérêts payés (-)",
    ("t11", "pension_entitlements_adjustment"): (
        "7. Ajustement pour variation des droits des ménages sur les fonds de pension"
    ),
    ("t17", "direct_taxes_households"): "- Ménages",
    ("t24", "general_government_total"): "I. Administrations publiques",
    ("t24", "social_security_cash_private_sector_pensions_total"): (
        "a. Pensions du secteur privé"
    ),
    ("t24", "social_security_cash_unemployment_with_company_supplement"): (
        "c. Allocations de chômage avec complément d'entreprise"
    ),
    ("t24", "federal_government_in_kind_health_care"): (
        "1. Prestations de soins de santé"
    ),
}


@lru_cache
def _facts(year: int) -> tuple:
    package = load_source_package(FPB_OUTLOOK)
    cells = package.build_source_cells(year)
    return tuple(package.build_facts(year, cells=list(cells)))


@lru_cache
def _table_of_record_set() -> dict[str, str]:
    package = load_source_package(FPB_OUTLOOK)
    with (package.package_path / "source_package.yaml").open(encoding="utf-8") as f:
        record_sets = yaml.safe_load(f)["record_sets"]
    return {rs["record_set_id"]: rs["sheet_name"].lower() for rs in record_sets}


def _digest(rows: list[list]) -> str:
    canonical = json.dumps(sorted(rows), separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


@pytest.mark.parametrize("year", BUILD_YEARS)
def test_every_fact_names_its_table_and_row(year):
    tables = _table_of_record_set()
    for fact in _facts(year):
        layout = fact.layout
        assert layout.groupby_value_id == layout.source_row_id
        assert fact.measure.source_concept == (
            f"{PREFIX}.{tables[layout.record_set_id]}.{layout.groupby_value_id}"
        )
        assert fact.measure.concept_relation == "source_label"


@pytest.mark.parametrize("year", BUILD_YEARS)
def test_each_row_is_one_series_across_the_annex_years(year):
    series = defaultdict(list)
    for fact in _facts(year):
        series[fact.measure.source_concept].append(fact)

    assert Counter(concept.split(".")[2] for concept in series) == TABLE_ROWS
    for concept, facts in series.items():
        assert sorted(fact.period.value for fact in facts) == ANNEX_YEARS, concept
        assert len({fact.layout.record_set_spec_id for fact in facts}) == 1
        assert len({fact.measure.concept for fact in facts}) == 1
        assert len({fact.measure.unit for fact in facts}) == 1
    # One row per spec, so no two rows share a source concept.
    specs = {fact.layout.record_set_spec_id for fact in _facts(year)}
    assert len(specs) == len(series) == sum(TABLE_ROWS.values())


def test_population_rows_are_separate_series():
    concepts = {
        fact.layout.groupby_value_id: fact.measure.source_concept
        for fact in _facts(2026)
        if fact.period.value == 2025
    }

    assert concepts["total_population"] == f"{PREFIX}.t07.total_population"
    assert concepts["working_age_population"] == f"{PREFIX}.t07.working_age_population"


@pytest.mark.parametrize("year", BUILD_YEARS)
def test_row_concepts_move_no_semantic_key_or_value(year):
    rows = consumer_fact_rows(list(_facts(year)))

    assert (
        _digest(
            [
                [
                    row["lineage"]["source_record_id"],
                    row["semantic_fact_key"],
                    row["value"],
                ]
                for row in rows
            ]
        )
        == SEMANTIC_DIGEST
    )


@pytest.mark.parametrize("year", BUILD_YEARS)
def test_row_concepts_pin_every_key_they_move(year):
    rows = consumer_fact_rows(list(_facts(year)))

    assert len({row["aggregate_fact_key"] for row in rows}) == len(rows)
    # One observed measure and one alignment per annex row, not per table.
    assert len({row["observed_measure_key"] for row in rows}) == sum(
        TABLE_ROWS.values()
    )
    assert len(
        {row["concept_alignment"]["concept_alignment_key"] for row in rows}
    ) == sum(TABLE_ROWS.values())
    assert (
        _digest(
            [
                [
                    row["lineage"]["source_record_id"],
                    row["aggregate_fact_key"],
                    row["legacy_fact_key"],
                    row["observed_measure_key"],
                    row["concept_alignment"]["concept_alignment_key"],
                ]
                for row in rows
            ]
        )
        == ROW_KEY_DIGEST
    )


@lru_cache
def _guarded_headers() -> dict[tuple[str, str], set[str]]:
    """Each row's ``expected_row_header``, the text the package guard checks."""

    package = load_source_package(FPB_OUTLOOK)
    with (package.package_path / "source_package.yaml").open(encoding="utf-8") as f:
        record_sets = yaml.safe_load(f)["record_sets"]
    headers = defaultdict(set)
    for rs in record_sets:
        for row in rs["rows"]:
            key = (rs["sheet_name"].lower(), row["value_id"])
            headers[key].add(row["expected_row_header"])
    return headers


@pytest.mark.parametrize("year", BUILD_YEARS)
def test_row_ids_name_the_publisher_rows(year):
    headers = _guarded_headers()
    labels = defaultdict(set)
    for fact in _facts(year):
        sheet = fact.measure.source_concept.split(".")[2]
        labels[sheet, fact.layout.groupby_value_id].add(fact.layout.groupby_value_label)

    for key, header in ROW_HEADERS.items():
        assert headers[key] == {header}, key
        assert labels[key] == {header}, key
