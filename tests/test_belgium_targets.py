"""Tests for Belgium Chronicle target source packages."""

from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)


REPO_ROOT = Path(__file__).resolve().parents[1]

BELGIUM_TARGET_STREAMS = (
    (
        "statbel-population-structure-2025",
        2025,
        "statbel_population_structure",
        "nuts1",
        "people",
        18,
    ),
    (
        "statbel-population-structure-2026",
        2026,
        "statbel_population_structure",
        "nuts1",
        "people",
        18,
    ),
    (
        "statbel-fiscal-income-2023-nis-2025",
        2023,
        "statbel_fiscal_income",
        "commune",
        "belgium_pit_taxable_income",
        565,
    ),
    (
        "spf-finances-pit-2023",
        2023,
        "spf_finances_pit",
        "country",
        "belgium_pit_federal_and_local_tax_before_withholding",
        1,
    ),
    (
        "onss-contributions-2024",
        2024,
        "onss_contributions",
        "country",
        "belgium_worker_article_17_uncapped_component_contribution",
        1,
    ),
    (
        "onem-rva-unemployment-2024",
        2024,
        "onem_rva_unemployment",
        "country",
        "receives_unemployment_benefit",
        1,
    ),
    (
        "nbb-national-accounts-household-disposable-income-2024",
        2024,
        "nbb_national_accounts",
        "country",
        "household_disposable_income",
        1,
    ),
)
EUROMOD_BE_COMPARATOR_ALIAS = "jrc-euromod-be-baseline-statistics-2025"
FISCAL_DISTRIBUTION_ALIAS = "statbel-fiscal-income-distribution-2023"
EUROMOD_BE_COMPARATOR_PATH = (
    REPO_ROOT
    / "db"
    / "data"
    / "jrc"
    / "euromod_be_baseline_statistics_2025"
    / "jrc_euromod_be_baseline_statistics_2025.csv"
)


@lru_cache
def _facts(alias: str, year: int):
    return tuple(load_source_package(alias).build_facts(year))


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_belgium_target_aliases_are_registered():
    aliases = {alias for alias, *_rest in BELGIUM_TARGET_STREAMS}
    aliases.add(EUROMOD_BE_COMPARATOR_ALIAS)

    assert aliases <= set(SOURCE_PACKAGE_ALIASES)


def test_statbel_fiscal_distribution_alias_resolves():
    assert SOURCE_PACKAGE_ALIASES[FISCAL_DISTRIBUTION_ALIAS] == Path(
        "statbel/fiscal_income_distribution_2023"
    )
    assert (
        load_source_package(FISCAL_DISTRIBUTION_ALIAS).package_id
        == FISCAL_DISTRIBUTION_ALIAS
    )


def test_statbel_fiscal_distribution_generator_keeps_ledger_schema_bytes():
    payload = yaml.safe_load(
        (
            REPO_ROOT
            / "packages"
            / "statbel"
            / "fiscal_income_distribution_2023"
            / "source_package.yaml"
        ).read_text()
    )

    assert payload["schema_version"] == "ledger.source_package.v1"


def test_statbel_fiscal_distribution_generator_runs_as_direct_file(tmp_path):
    relative_script = Path(
        "packages/statbel/fiscal_income_distribution_2023/build_package.py"
    )
    checkout = tmp_path / "checkout"
    script = checkout / relative_script
    script.parent.mkdir(parents=True)
    script.write_bytes((REPO_ROOT / relative_script).read_bytes())

    chronicle_dir = checkout / "chronicle"
    chronicle_dir.mkdir()
    for filename in ("__init__.py", "epoch.py"):
        (chronicle_dir / filename).write_bytes(
            (REPO_ROOT / "chronicle" / filename).read_bytes()
        )

    openpyxl_dir = script.parent / "openpyxl"
    openpyxl_dir.mkdir()
    (openpyxl_dir / "__init__.py").write_text("")
    (openpyxl_dir / "utils.py").write_text(
        "def get_column_letter(index):\n    return str(index)\n"
    )
    (script.parent / "yaml.py").write_text("")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = ""
    result = subprocess.run(
        [sys.executable, "-S", str(script)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 1
    assert "FileNotFoundError: Missing staged Statbel workbooks" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr


def test_statbel_fiscal_distribution_artifact_pins_and_r2_keys():
    data_dir = REPO_ROOT / "db" / "data" / "statbel" / "fiscal_income_distribution_2023"
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text())
    expected = {
        "A_1": (
            "b51711ed09bc4339bd331785c533d7d728c36c7e4f2e3eb63f91537838932f96",
            616745,
        ),
        "A_2": (
            "b5e4fc0ad47101bdf3664237020286824a09025ae38021d010448623d57ef683",
            411403,
        ),
        "A_3": (
            "e2f10edd92c55c010a1ed0d2f0fd8757f39114ad2ef1da944b745cada9fc011a",
            361545,
        ),
        "B_1": (
            "b5dd48ed14cfadd2aa65addd49828387fc70d517da87847608f1cf66eb516c38",
            326306,
        ),
        "B_2": (
            "4a80321f8d40478d183c6950defde45709619f9842bca45cfc6be26354e70224",
            451903,
        ),
        "B_3": (
            "2ede83e4f813c7f7675281996ca2a1815e0dc1db1c219600370f2c26dfa57198",
            82136,
        ),
        "B_4": (
            "7b00e340c74c7de4d2cb1fa5ea2f86fe9bd15e9a259d98a4af92fc4fd322f660",
            101224,
        ),
        "B_5": (
            "ff84f65475e19037a82cd8f504ee1022372daa379abc8820cecbb4b1184ee3d4",
            360249,
        ),
    }

    assert manifest["source_id"] == "belgium"
    for table, (expected_sha, expected_size) in expected.items():
        spec = manifest["files"][table]
        path = data_dir / spec["filename"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha
        assert path.stat().st_size == expected_size
        assert spec["sha256"] == expected_sha
        assert spec["size_bytes"] == expected_size
        assert spec["storage"]["r2"]["key"] == (
            "raw/belgium/statbel-fiscal-income-distribution-2023/2023/"
            f"{expected_sha}/{spec['filename']}"
        )


def test_statbel_fiscal_distribution_curated_rows_retain_source_cells():
    rows = _csv_rows(
        REPO_ROOT
        / "db"
        / "data"
        / "statbel"
        / "fiscal_income_distribution_2023"
        / "statbel_fiscal_income_distribution_2023.csv"
    )
    by_id = {row["row_id"]: row for row in rows}

    income_class = by_id["a1.taxable_income.class_19_20"]
    assert income_class["source_workbook"] == "fisc2023_A_1_NL.xlsx"
    assert income_class["be_source_sheet"] == "België"
    assert income_class["be_source_row"] == "29"
    assert json.loads(income_class["be_source_cells"]) == {
        "amount_eur": "D29",
        "amount_share": "E29",
        "declaration_share": "C29",
        "declarations": "B29",
    }
    assert income_class["be_amount_eur"] == "3773400213.25"
    assert json.loads(income_class["be_source_raw_values"])["amount_eur"] == (
        "3773400213.2535701"
    )
    assert income_class["income_year"] == "2023"
    assert income_class["assessment_year"] == "2024"
    assert income_class["tax_return.net_taxable_income_class"] == "class_19_20"
    assert income_class["tax_return.net_taxable_income_lower_bound"] == "19000"
    assert income_class["tax_return.net_taxable_income_upper_bound"] == "20000"

    low_decile = by_id["b1.decile_01"]
    assert json.loads(low_decile["be_source_cells"])["total_tax_eur"] == "F9"
    assert low_decile["be_total_tax_eur"] == "-29166612.99"

    joint_age = by_id["b4.joint.age_25_29.decile_01"]
    assert json.loads(joint_age["be_source_cells"])["declarations"] == "C27"
    assert joint_age["be_declarations"] == "509"
    assert joint_age["tax_return.declaration_type"] == "joint"
    assert joint_age["tax_return.age_band"] == "age_25_29"
    assert joint_age["tax_return.decile"] == "1"


def test_statbel_fiscal_distribution_class_counts_and_commune_consistency():
    distribution = _facts(FISCAL_DISTRIBUTION_ALIAS, 2023)
    by_id = {fact.source_record_id: fact for fact in distribution}
    prefix = (
        "statbel.fiscal_income_distribution.income_year2023."
        "taxable_income.by_income_class_eur1000"
    )
    total_income = Decimal(str(by_id[f"{prefix}.total.taxable_income_eur"].value))
    detail_declarations = [
        fact
        for fact in distribution
        if fact.geography.id == "BE"
        and fact.source_record_id.startswith(f"{prefix}.class_")
        and fact.layout.measure_id == "declarations"
    ]

    assert len(detail_declarations) == 101
    assert sum(fact.value for fact in detail_declarations) == 6_846_186
    assert by_id[f"{prefix}.total.declarations"].value == 6_846_186
    assert total_income == Decimal("274707991587.37")
    assert (
        by_id[
            "statbel.fiscal_income_distribution.income_year2023."
            "zero_income_declarations.total.declarations"
        ].value
        == 523_770
    )
    assert (
        by_id[
            "statbel.fiscal_income_distribution.income_year2023.regions.be2."
            "taxable_income.by_income_class_eur1000.total.taxable_income_eur"
        ].value
        == 170_249_544_832.83
    )

    # The existing commune package preserves 565 independently rounded
    # publisher cells. Their sum is €0.45 above A.1's national cell; pin the
    # residual instead of reconciling either publisher-backed value.
    commune_total = sum(
        Decimal(str(fact.value))
        for fact in _facts("statbel-fiscal-income-2023-nis-2025", 2023)
    )
    assert commune_total == Decimal("274707991587.82")
    assert commune_total - total_income == Decimal("0.45")
    assert abs(commune_total - total_income) < Decimal("1")


def test_statbel_fiscal_distribution_decile_amounts_and_tax_signs():
    facts = _facts(FISCAL_DISTRIBUTION_ALIAS, 2023)
    by_id = {fact.source_record_id: fact for fact in facts}
    prefix = "statbel.fiscal_income_distribution.income_year2023.by_decile"

    for measure, expected_total in {
        "taxable_income_eur": Decimal("274707991587.39"),
        "total_tax_eur": Decimal("62840116133.93"),
        "payable_tax_eur": Decimal("5232698748.97"),
        "tax_refund_eur": Decimal("5300763663.38"),
    }.items():
        decile_sum = sum(
            Decimal(str(by_id[f"{prefix}.decile_{decile:02d}.{measure}"].value))
            for decile in range(1, 11)
        )
        assert Decimal(str(by_id[f"{prefix}.total.{measure}"].value)) == expected_total
        assert decile_sum == expected_total

    assert by_id[f"{prefix}.decile_01.total_tax_eur"].value == -29_166_612.99
    assert by_id[f"{prefix}.decile_02.total_tax_eur"].value == -60_702_856.71
    assert by_id[f"{prefix}.decile_10.total_tax_eur"].layout.record_set_id.endswith(
        ".decile_values"
    )
    assert by_id[
        f"{prefix}.percentile_100.total_tax_eur"
    ].layout.record_set_id.endswith(".top_decile_percentile_values")


def test_statbel_fiscal_distribution_preserves_exact_age_bands():
    facts = _facts(FISCAL_DISTRIBUTION_ALIAS, 2023)
    by_id = {fact.source_record_id: fact for fact in facts}
    prefix = (
        "statbel.fiscal_income_distribution.income_year2023."
        "declaration_type_age.by_decile"
    )

    assert by_id[f"{prefix}.joint.age_25_29.decile_01.declarations"].value == 509
    assert by_id[f"{prefix}.joint.age_30_34.decile_01.declarations"].value == 973
    assert not any("age_25_34" in fact.source_record_id for fact in facts)

    age_total = by_id[f"{prefix}.joint.total.decile_01.declarations"]
    assert age_total.filters["tax_return.age_band"] == "all"
    assert age_total.layout.table_record_kind == "total"

    # The workbook literally labels this category "Minder dan 24 jaar", but
    # its values equal the publisher's through-age-24 Home bins. Keep the
    # literal category and do not invent a numeric age boundary.
    publisher_under_24 = by_id[f"{prefix}.individual.under_24.decile_01.declarations"]
    assert publisher_under_24.filters["tax_return.age_band"] == "under_24"
    assert all(
        constraint.variable != "tax_return.age"
        for constraint in publisher_under_24.constraints
    )


def test_statbel_fiscal_distribution_zero_income_ids_are_geography_neutral():
    zero_income_facts = [
        fact
        for fact in _facts(FISCAL_DISTRIBUTION_ALIAS, 2023)
        if ".zero_income_declarations." in fact.source_record_id
    ]

    assert len(zero_income_facts) == 4
    assert all(
        fact.source_record_id.endswith(".total.declarations")
        for fact in zero_income_facts
    )


def test_belgium_target_packages_have_expected_fact_count():
    facts = [
        fact
        for alias, year, *_rest in BELGIUM_TARGET_STREAMS
        for fact in _facts(alias, year)
    ]

    assert len(facts) == 605
    assert validate_facts(facts).valid


def test_belgium_microcosm_selectors_match_one_package_stream():
    facts_by_alias = {
        alias: _facts(alias, year) for alias, year, *_rest in BELGIUM_TARGET_STREAMS
    }

    for (
        expected_alias,
        _year,
        source_name,
        geography_level,
        concept,
        expected_count,
    ) in BELGIUM_TARGET_STREAMS:
        matching_aliases = {
            alias
            for alias, facts in facts_by_alias.items()
            if any(
                fact.source.source_name == source_name
                and fact.geography.level == geography_level
                and fact.measure.concept == concept
                and fact.period.value == _year
                for fact in facts
            )
        }
        matching_facts = [
            fact
            for fact in facts_by_alias[expected_alias]
            if fact.source.source_name == source_name
            and fact.geography.level == geography_level
            and fact.measure.concept == concept
            and fact.period.value == _year
        ]

        assert matching_aliases == {expected_alias}
        assert len(matching_facts) == expected_count


def test_belgium_subnational_facts_carry_current_vintages():
    population_2025 = _facts("statbel-population-structure-2025", 2025)
    population = _facts("statbel-population-structure-2026", 2026)
    fiscal = _facts("statbel-fiscal-income-2023-nis-2025", 2023)

    assert {fact.geography.vintage for fact in population_2025} == {"NUTS_2024"}
    assert {fact.geography.vintage for fact in population} == {"NUTS_2024"}
    assert {fact.geography.level for fact in fiscal} == {"commune"}
    assert {fact.geography.vintage for fact in fiscal} == {"nis_2025"}


def test_belgium_period_basis_is_preserved_by_source():
    periods_by_alias = {
        alias: {(fact.period.type, fact.period.value) for fact in _facts(alias, year)}
        for alias, year, *_rest in BELGIUM_TARGET_STREAMS
    }

    assert periods_by_alias["statbel-population-structure-2026"] == {
        ("calendar_year", 2026)
    }
    assert periods_by_alias["statbel-population-structure-2025"] == {
        ("calendar_year", 2025)
    }
    assert periods_by_alias["statbel-fiscal-income-2023-nis-2025"] == {
        ("tax_year", 2023)
    }
    assert periods_by_alias["spf-finances-pit-2023"] == {("tax_year", 2023)}
    assert periods_by_alias["onss-contributions-2024"] == {("calendar_year", 2024)}
    assert periods_by_alias["onem-rva-unemployment-2024"] == {("calendar_year", 2024)}
    assert periods_by_alias[
        "nbb-national-accounts-household-disposable-income-2024"
    ] == {("calendar_year", 2024)}


def test_belgium_nis_2025_crosswalk_round_trips_merged_communes():
    crosswalk = _csv_rows(
        REPO_ROOT
        / "db"
        / "data"
        / "statbel"
        / "nis_2025_commune_crosswalk"
        / "statbel_nis_2025_commune_crosswalk.csv"
    )
    fiscal_rows = _csv_rows(
        REPO_ROOT
        / "db"
        / "data"
        / "statbel"
        / "fiscal_income_commune_2023_nis_2025"
        / "statbel_fiscal_income_commune_2023_nis_2025.csv"
    )
    merged_sources_by_target: dict[str, set[str]] = {}
    for row in crosswalk:
        if row["relationship"] == "merged":
            merged_sources_by_target.setdefault(row["target_nis"], set()).add(
                row["source_nis"]
            )
    fiscal_by_geo = {row["geography_id"]: row for row in fiscal_rows}

    assert len(crosswalk) == 581
    assert sum(row["relationship"] == "merged" for row in crosswalk) == 30
    assert len(fiscal_rows) == 565
    assert merged_sources_by_target["82039"] == {"82003", "82005"}
    assert fiscal_by_geo["82039"]["source_nis_codes"] == "82003;82005"
    assert fiscal_by_geo["82039"]["geography_name"] == "Bastogne"
    assert merged_sources_by_target["46030"] == {"11056", "46003", "46013"}
    assert fiscal_by_geo["46030"]["source_nis_codes"] == "11056;46003;46013"


def test_belgium_euromod_comparator_has_source_urls_per_row():
    comparator_rows = _csv_rows(EUROMOD_BE_COMPARATOR_PATH)
    facts = _facts(EUROMOD_BE_COMPARATOR_ALIAS, 2025)

    assert len(comparator_rows) == 90
    assert len(facts) == 90
    assert {row["source_url"] for row in comparator_rows} == {
        "https://euromod-web.jrc.ec.europa.eu/sites/default/files/2025-02/Y15_CR_BE_final.pdf"
    }
    assert {fact.source.source_name for fact in facts} == {"jrc_euromod_be"}
    assert {fact.geography.id for fact in facts} == {"BE"}
    assert {fact.measure.unit for fact in facts} == {
        "count",
        "eur",
        "percent",
        "ratio",
    }
    assert sum(fact.provenance_class == "administrative" for fact in facts) == 25
    assert sum(fact.provenance_class == "model_output" for fact in facts) == 63
    assert sum(fact.provenance_class == "survey_aggregate" for fact in facts) == 2
    assert sum(row["validation.series"] == "euromod" for row in comparator_rows) == 32
    assert sum(row["validation.series"] == "ratio" for row in comparator_rows) == 29
    assert {
        fact.provenance_class
        for fact in facts
        if fact.filters["validation.series"] in {"euromod", "ratio"}
    } == {"model_output"}
    survey_facts = [
        fact for fact in facts if fact.provenance_class == "survey_aggregate"
    ]
    assert {fact.survey_instrument for fact in survey_facts} == {"EU-SILC"}
    assert validate_facts(facts).valid


def test_belgium_euromod_comparator_preserves_original_rows_byte_for_byte():
    original_prefix = b"".join(
        EUROMOD_BE_COMPARATOR_PATH.read_bytes().splitlines(keepends=True)[:42]
    )

    # Header plus the original 41 rows is exactly the C2 artifact.
    assert hashlib.sha256(original_prefix).hexdigest() == (
        "2ef69251a72caaab042706c77143fa4f86dde2f800747ebb421b5f7b9a45e394"
    )


def test_belgium_euromod_comparator_pairs_c2_rows_with_model_outputs():
    comparator_rows = _csv_rows(EUROMOD_BE_COMPARATOR_PATH)
    ids = {row["value_id"] for row in comparator_rows}
    c2_rows = comparator_rows[18:41]

    assert len(c2_rows) == 23
    assert {row["validation.series"] for row in c2_rows} == {"external", "silc"}

    # The cached report has no blank same-period EUROMOD cells for these rows.
    documented_euromod_blanks: set[str] = set()
    missing_euromod = {
        row["value_id"]
        for row in c2_rows
        if row["value_id"]
        .replace("_external_", "_euromod_")
        .replace("_silc_", "_euromod_")
        not in ids
    }
    assert missing_euromod == documented_euromod_blanks

    missing_ratios = {
        row["value_id"]
        for row in c2_rows
        if row["value_id"].replace("_external_", "_ratio_").replace("_silc_", "_ratio_")
        not in ids
    }
    assert not missing_ratios

    # A3.2 prints these EUROMOD yse amounts but no External values or ratios.
    yse_amounts = {
        int(row["period"]): int(row["value"])
        for row in comparator_rows
        if row["table_id"] == "A3.2"
        and row["validation.metric"] == "self_employment_income_yse"
        and row["validation.series"] == "euromod"
    }
    assert yse_amounts == {2021: 20_965, 2022: 21_981, 2023: 23_764}
    assert not any(
        row["table_id"] == "A3.2"
        and row["validation.metric"] == "self_employment_income_yse"
        and row["validation.series"] == "ratio"
        for row in comparator_rows
    )


SFPD_PENSION_ALIAS = "sfpd-legal-pension-caseload-2025"
GROEIPAKKET_ALIAS = "opgroeien-groeipakket-caseload-2025"
BFP_OUTLOOK_ALIAS = "bfp-economic-outlook-2026-06"
FPB_ANNEX_ALIAS = "fpb-economic-outlook-2026-2031-june-2026"


def test_belgium_supplementary_publisher_aliases_are_registered():
    assert {
        SFPD_PENSION_ALIAS,
        GROEIPAKKET_ALIAS,
        BFP_OUTLOOK_ALIAS,
        FPB_ANNEX_ALIAS,
    } <= set(SOURCE_PACKAGE_ALIASES)


def test_sfpd_legal_pension_caseload_matches_published_cells():
    facts = _facts(SFPD_PENSION_ALIAS, 2025)
    by_scheme = {fact.filters["sfpd.scheme"]: fact.value for fact in facts}

    # Exact published counts from PensionStat.be (SFP/SFPD), January 2025.
    assert by_scheme == {
        "all": 2674520,
        "employee": 2357954,
        "self_employed": 690590,
        "civil_servant": 604506,
    }
    # Scheme counts are per-scheme recipients (mixed careers), not a partition:
    # their sum exceeds the all-schemes total.
    scheme_sum = sum(v for k, v in by_scheme.items() if k != "all")
    assert scheme_sum > by_scheme["all"]
    assert {fact.source.source_name for fact in facts} == {"sfpd_pensions"}
    assert {fact.geography.level for fact in facts} == {"country"}
    assert {fact.measure.unit for fact in facts} == {"count"}
    assert validate_facts(facts).valid


def test_groeipakket_caseload_matches_published_component_cells():
    facts = _facts(GROEIPAKKET_ALIAS, 2025)
    children = {
        fact.filters["groeipakket.component"]: fact.value
        for fact in facts
        if fact.measure.concept == "groeipakket_children_receiving_component"
    }
    families = {
        fact.filters["groeipakket.component"]: fact.value
        for fact in facts
        if fact.measure.concept == "groeipakket_families_receiving_component"
    }

    # Exact published caseload cells from Opgroeien (Flemish agency).
    assert children == {
        "social_supplement": 522148,
        "orphan_supplement": 21741,
        "care_supplement": 51261,
        "foster_care_supplement": 7348,
        "school_allowance": 499339,
        "support_supplement": 8735,
    }
    assert families == {
        "social_supplement": 281551,
        "orphan_supplement": 14824,
        "care_supplement": 46748,
        "foster_care_supplement": 5891,
        "basic_amount": 930010,
    }
    # basisbedrag child count is published only as a rounded ">1.6M" lower bound,
    # so it is intentionally omitted from the child record set (recorded as a gap).
    assert "basic_amount" not in children
    assert {fact.geography.id for fact in facts} == {"BE2"}
    assert {fact.geography.vintage for fact in facts} == {"NUTS_2024"}
    assert validate_facts(facts).valid


def test_bfp_economic_outlook_facts_are_typed_source_projection():
    facts = _facts(BFP_OUTLOOK_ALIAS, 2026)
    by_key = {(fact.period.value, fact.measure.concept): fact.value for fact in facts}

    # Exact published headline figures from the BFP June 2026 outlook.
    assert by_key == {
        (2026, "bfp.real_gdp_growth_projection"): 0.7,
        (2026, "bfp.consumer_price_inflation_projection"): 3.4,
        (2026, "bfp.general_government_deficit_pct_gdp_projection"): 5.1,
        (2031, "bfp.consumer_price_inflation_projection"): 1.7,
        (2031, "bfp.general_government_deficit_pct_gdp_projection"): 6.4,
    }
    # Publisher projections must be typed source_projection, never observation.
    assert {fact.assertion for fact in facts} == {"source_projection"}
    assert {fact.source.source_name for fact in facts} == {"bfp_economic_outlook"}
    assert {fact.geography.id for fact in facts} == {"BE"}
    assert validate_facts(facts).valid


@lru_cache
def _fpb_annex_outputs():
    package = load_source_package(FPB_ANNEX_ALIAS)
    cells = tuple(package.build_source_cells(2026))
    facts = tuple(package.build_facts(2026, cells=list(cells)))
    return cells, facts


def test_fpb_annex_has_requested_table_counts_and_vintage_boundary():
    _cells, facts = _fpb_annex_outputs()
    package_report = validate_source_package(FPB_ANNEX_ALIAS, year=2026)

    assert package_report.valid, package_report.to_dict()
    assert package_report.counts == {
        "record_set_count": 1000,
        "row_count": 1000,
        "measure_count": 1000,
        "source_record_count": 1000,
        "source_region_count": 1000,
    }
    assert Counter(fact.measure.source_concept for fact in facts) == {
        "fpb.economic_outlook_2026_2031.t01.published_cell": 40,
        "fpb.economic_outlook_2026_2031.t06.published_cell": 30,
        "fpb.economic_outlook_2026_2031.t07.published_cell": 100,
        "fpb.economic_outlook_2026_2031.t11.published_cell": 210,
        "fpb.economic_outlook_2026_2031.t17.published_cell": 70,
        "fpb.economic_outlook_2026_2031.t24.published_cell": 550,
    }
    assert Counter((fact.period.value, fact.assertion) for fact in facts) == {
        **{(year, "observation"): 100 for year in range(2022, 2026)},
        **{(year, "source_projection"): 100 for year in range(2026, 2032)},
    }
    assert {fact.provenance_class for fact in facts} == {"model_output"}
    assert validate_facts(facts).valid


def test_fpb_annex_pins_publisher_cells_and_compiled_values():
    cells, facts = _fpb_annex_outputs()
    cells_by_coordinate = {
        (cell.sheet_name, cell.address): cell.raw_value for cell in cells
    }
    facts_by_record = {fact.source_record_id: fact for fact in facts}

    assert cells_by_coordinate[("T11", "AE8")] == 320578
    assert cells_by_coordinate[("T17", "AE8")] == 77771
    assert cells_by_coordinate[("T24", "AE20")] == 5602

    compensation = facts_by_record[
        "fpb.economic_outlook_2026_2031.cy2025.household_account."
        "compensation_of_employees.amount_meur"
    ]
    direct_tax = facts_by_record[
        "fpb.economic_outlook_2026_2031.cy2025.general_government_account."
        "direct_taxes_households.amount_meur"
    ]
    unemployment = facts_by_record[
        "fpb.economic_outlook_2026_2031.cy2025.social_benefits_detail."
        "social_security_cash_unemployment.amount_meur"
    ]

    assert compensation.value == 320_578_000_000
    assert compensation.layout.groupby_value_label == "3. Rémunération des salariés"
    assert direct_tax.value == 77_771_000_000
    assert direct_tax.layout.groupby_value_label == "- Ménages"
    assert unemployment.value == 5_602_000_000
    assert unemployment.layout.groupby_value_label == "a. Chômage"

    resources_2023 = facts_by_record[
        "fpb.economic_outlook_2026_2031.cy2023.household_account."
        "total_resources.amount_meur"
    ]
    resources_2025 = facts_by_record[
        "fpb.economic_outlook_2026_2031.cy2025.household_account."
        "total_resources.amount_meur"
    ]
    assert resources_2023.value == 518_286_000_000
    assert resources_2025.value == 554_117_000_000
    assert resources_2023.layout.groupby_value_label == "a. Ressources"
    assert resources_2025.layout.groupby_value_label == "a. Ressources"


def test_statbel_2025_population_matches_fpb_annual_average_with_declared_tolerance():
    statbel_facts = _facts("statbel-population-structure-2025", 2025)
    statbel_total = sum(fact.value for fact in statbel_facts)
    _cells, fpb_facts = _fpb_annex_outputs()
    fpb_population = next(
        fact.value
        for fact in fpb_facts
        if fact.source_record_id
        == "fpb.economic_outlook_2026_2031.cy2025.labour_market.levels."
        "total_population.level_thousand"
    )
    relative_gap = abs(fpb_population - statbel_total) / fpb_population

    assert statbel_total == 11_825_551
    assert Counter(fact.geography.id for fact in statbel_facts) == {
        "BE1": 6,
        "BE2": 6,
        "BE3": 6,
    }
    assert fpb_population == 11_850_400
    assert fpb_population - statbel_total == 24_849
    assert relative_gap == pytest.approx(0.002096891244177412)
    # Observed gap is 0.2097%: use a stated 0.25% ceiling for the January 1
    # Statbel stock versus FPB annual-average population, not a tuned equality.
    assert relative_gap < 0.0025


def test_statbel_2025_artifacts_are_hash_pinned():
    data_dir = REPO_ROOT / "db" / "data" / "statbel" / "population_structure_nuts1_2025"
    curated = data_dir / "statbel_population_structure_nuts1_2025.csv"
    raw_zip = data_dir / "TF_SOC_POP_STRUCT_2025.zip"
    package_report = validate_source_package(
        "statbel-population-structure-2025", year=2025
    )

    assert package_report.valid, package_report.to_dict()
    assert package_report.counts == {
        "record_set_count": 1,
        "row_count": 18,
        "measure_count": 1,
        "source_record_count": 18,
        "source_region_count": 1,
    }
    assert hashlib.sha256(curated.read_bytes()).hexdigest() == (
        "2243aa1be7600535dba7e3d804ef482b6edac07c1e3813f4882c3bf4a34ff2ad"
    )
    assert hashlib.sha256(raw_zip.read_bytes()).hexdigest() == (
        "33910ea36437e39cfffd82ad82c759a2a8d1f2ab7662d45ce71c8ec9f336716c"
    )
