"""Boundary tests for Chronicle source-data ownership."""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest


FORBIDDEN_PACKAGE_ROOTS = {"calibration", "micro"}


def test_chronicle_modules_do_not_import_non_chronicle_runtime_packages():
    chronicle_root = Path(__file__).resolve().parents[1] / "chronicle"
    violations: list[str] = []

    for path in sorted(chronicle_root.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            imported_roots: list[str] = []
            if isinstance(node, ast.Import):
                imported_roots = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_roots = [node.module.split(".", 1)[0]]

            for root in imported_roots:
                if root in FORBIDDEN_PACKAGE_ROOTS:
                    relative_path = path.relative_to(chronicle_root.parent)
                    violations.append(f"{relative_path}:{node.lineno}: {root}")

    assert violations == []


def test_repository_does_not_ship_raw_microdata_namespace():
    repo_root = Path(__file__).resolve().parents[1]

    assert not (repo_root / "chronicle" / "microdata").exists()
    assert not (repo_root / "policyengine_chronicle" / "microdata").exists()
    assert not (repo_root / "micro").exists()
    assert not (repo_root / "calibration").exists()
    assert not (repo_root / "storage").exists()


def test_uk_legacy_etl_cleanup_checklist_accounts_for_legacy_series():
    repo_root = Path(__file__).resolve().parents[1]
    checklist = (repo_root / "docs" / "pe-uk-source-checklist.md").read_text()

    required_entries = [
        "`db/etl_obr.py` `gdp`",
        "`db/etl_obr.py` `total_receipts`",
        "`db/etl_obr.py` `total_managed_expenditure`",
        "`db/etl_obr.py` `public_sector_net_borrowing`",
        "`db/etl_obr.py` `public_sector_net_debt`",
        "`db/etl_obr.py` `real_gdp_growth`",
        "`db/etl_obr.py` `unemployment_rate`",
        "`db/etl_obr.py` `cpi_inflation`",
        "`db/etl_obr.py` `rpi_inflation`",
        "`db/etl_obr.py` `bank_rate`",
        "`db/etl_obr.py` `employment`",
        "`db/etl_ons.py` `population_total`",
        "`db/etl_ons.py` `population_age_0_15`",
        "`db/etl_ons.py` `population_age_16_64`",
        "`db/etl_ons.py` `population_age_65_plus`",
        "`db/etl_ons.py` `households_total`",
        "`db/etl_ons.py` `average_household_size`",
        "`db/etl_hmrc.py` `income_tax`",
        "`db/etl_hmrc.py` `national_insurance`",
        "`db/etl_hmrc.py` `capital_gains_tax`",
        "`db/etl_hmrc.py` `inheritance_tax`",
        "`db/etl_hmrc.py` `taxpayers`, `higher_rate_taxpayers`, `additional_rate_taxpayers`",
        "`db/etl_hmrc.py` `total_income`",
        "`db/etl_hmrc.py` `benefits.universal_credit.{recipients,expenditure}`",
        "`db/etl_hmrc.py` `benefits.child_benefit.{recipients,expenditure}`",
        "`db/etl_hmrc.py` `benefits.state_pension.{recipients,expenditure}`",
        "`db/etl_hmrc.py` `benefits.housing_benefit.{recipients,expenditure}`",
        "`db/etl_hmrc.py` `benefits.pension_credit.{recipients,expenditure}`",
    ]

    for entry in required_entries:
        assert entry in checklist

    assert "obr-efo-economy-march-2026" in checklist
    assert "obr-efo-aggregates-march-2026" in checklist
    assert "ons-families-households-2025" in checklist
    assert "2026-2034 remain gaps" in checklist
    assert "Explicit source gap or non-equivalence" in checklist
    assert "assertion" in checklist
    assert "period_type" in checklist
    assert "2023 through 2026" in checklist


def test_retired_uk_legacy_etl_modules_are_not_shipped():
    repo_root = Path(__file__).resolve().parents[1]

    assert not (repo_root / "db" / "etl_obr.py").exists()
    assert not (repo_root / "db" / "etl_ons.py").exists()
    assert not (repo_root / "tests" / "test_etl_obr.py").exists()
    assert not (repo_root / "tests" / "test_etl_ons.py").exists()
    assert not (repo_root / "db" / "etl_hmrc.py").exists()
    assert not (repo_root / "tests" / "test_etl_hmrc.py").exists()


def test_load_cli_no_longer_accepts_retired_uk_legacy_etl_sources():
    cli_source = (Path(__file__).resolve().parents[1] / "db" / "cli.py").read_text()

    assert 'if args.source == "obr"' not in cli_source
    assert 'if args.source == "ons"' not in cli_source
    assert 'if args.source == "hmrc"' not in cli_source
    assert "load_obr_targets" not in cli_source
    assert "load_ons_targets" not in cli_source
    assert "load_hmrc_targets" not in cli_source
    assert '"obr",' not in cli_source
    assert '"ons",' not in cli_source
    assert '"hmrc",' not in cli_source


# Legacy US loaders, keyed by module name, with the `chronicle load` source each
# one answered to. The first twelve were retired because their hand-typed values
# do not trace to publisher bytes; `etl_soi` and `etl_snap` went with the legacy
# targets table they wrote, which nothing read.
RETIRED_US_LEGACY_ETLS = {
    "etl_soi_state": "soi-state",
    "etl_soi_credits": "soi-credits",
    "etl_soi_deductions": "soi-deductions",
    "etl_soi_income_sources": "soi-income-sources",
    "etl_aca_enrollment": "aca",
    "etl_bls": "bls",
    "etl_cbo": "cbo",
    "etl_census": "census",
    "etl_cps": "cps",
    "etl_medicaid": "medicaid",
    "etl_ssa": "ssa",
    "etl_ssi": "ssi",
    "etl_soi": "soi",
    "etl_snap": "snap",
}
LEGACY_TARGET_TABLES = {"strata", "stratum_constraints", "targets"}
SOURCE_ARTIFACT_TABLES = {
    "source_artifacts",
    "source_columns",
    "source_rows",
    "source_tables",
}


def test_retired_us_legacy_etl_modules_are_not_shipped():
    repo_root = Path(__file__).resolve().parents[1]

    for module in RETIRED_US_LEGACY_ETLS:
        assert not (repo_root / "db" / f"{module}.py").exists()
        assert not (repo_root / "tests" / f"test_{module}.py").exists()
        assert importlib.util.find_spec(f"db.{module}") is None


def test_no_legacy_db_etl_loaders_remain():
    db_root = Path(__file__).resolve().parents[1] / "db"

    assert sorted(path.name for path in db_root.glob("etl_*.py")) == []


@pytest.mark.parametrize(
    "argv",
    [
        ["load", "all"],
        *(["load", source] for source in sorted(RETIRED_US_LEGACY_ETLS.values())),
        ["stats"],
        ["query", "--variable", "snap_household_count"],
    ],
)
def test_cli_rejects_retired_legacy_target_commands(monkeypatch, capsys, argv):
    from db import cli

    monkeypatch.setattr(sys, "argv", ["chronicle", *argv])
    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_init_creates_only_source_artifact_tables(monkeypatch, tmp_path):
    import sqlite3

    from db import cli

    db_path = tmp_path / "chronicle.db"
    monkeypatch.setattr(sys, "argv", ["chronicle", "--db", str(db_path), "init"])
    cli.main()

    with sqlite3.connect(db_path) as connection:
        tables = {
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert tables == SOURCE_ARTIFACT_TABLES
    assert not tables & LEGACY_TARGET_TABLES


def test_legacy_target_api_is_retired():
    import chronicle.jurisdictions.us as us_jurisdiction
    import chronicle.normalization as chronicle_normalization
    import chronicle.targets as chronicle_targets
    import db.schema as schema
    import db.supabase_client as supabase_client
    import policyengine_chronicle.targets as public_targets

    repo_root = Path(__file__).resolve().parents[1]
    legacy_names = {
        "DEFAULT_DB_PATH",
        "DataSource",
        "GeographicLevel",
        "Jurisdiction",
        "Stratum",
        "StratumConstraint",
        "Target",
        "TargetType",
        "get_engine",
        "get_session",
        "init_db",
        "insert_targets_batch",
        "query_strata",
        "query_targets",
    }

    assert us_jurisdiction.__all__ == []
    assert importlib.util.find_spec("chronicle.targets.loaders") is None
    assert importlib.util.find_spec("chronicle.targets.client") is None
    assert not legacy_names & set(chronicle_targets.__all__)
    assert not legacy_names & set(public_targets.__all__)
    for name in legacy_names:
        assert not hasattr(chronicle_targets, name)
        with pytest.raises(AttributeError):
            getattr(public_targets, name)
    for name in (
        "GeographicLevel",
        "Stratum",
        "StratumConstraint",
        "Target",
        "TargetType",
    ):
        assert not hasattr(schema, name)
    for name in (
        "TARGETS_SCHEMA",
        "insert_targets_batch",
        "query_strata",
        "query_targets",
    ):
        assert not hasattr(supabase_client, name)
    for name in ("TargetBlueprint", "as_target", "target_kwargs"):
        assert not hasattr(chronicle_normalization, name)
    assert importlib.util.find_spec("chronicle.normalization.targets") is None
    assert not (repo_root / "scripts" / "export_to_json.py").exists()


def test_us_legacy_etl_cleanup_doc_accounts_for_retired_series():
    repo_root = Path(__file__).resolve().parents[1]
    doc = (repo_root / "docs" / "us-legacy-etl-cleanup.md").read_text()

    for module in RETIRED_US_LEGACY_ETLS:
        assert f"`db/{module}.py`" in doc

    required_entries = [
        "`db/etl_soi_state.py` `tax_unit_count`, `adjusted_gross_income` (state)",
        "`db/etl_soi_state.py` `income_tax_liability` (state)",
        "`db/etl_soi_state.py` AGI-band rows",
        "`db/etl_soi_credits.py` `eitc_claims`, `eitc_amount` (state)",
        "`db/etl_soi_credits.py` `ctc_claims`, `ctc_amount`, `actc_claims`, `actc_amount` (state)",
        "`db/etl_soi_credits.py` EITC by number of children (national)",
        "`db/etl_soi_credits.py` CTC and ACTC by number of children (national)",
        "`db/etl_soi_deductions.py` `salt_claims`, `salt_amount` (state)",
        "`db/etl_soi_deductions.py` `mortgage_interest_claims`, `mortgage_interest_amount` (state)",
        "`db/etl_soi_deductions.py` `charitable_claims`, `charitable_amount` (state)",
        "`db/etl_soi_deductions.py` `medical_claims`, `medical_amount` (state)",
        "`db/etl_soi_deductions.py` `qbi_claims`, `qbi_amount` (state)",
        "`db/etl_soi_income_sources.py` `short_term_capital_gains_*`, `long_term_capital_gains_*`",
        "`db/etl_soi_income_sources.py` `state_local_refunds_*`",
        "`db/etl_soi_income_sources.py` `alimony_received_*`",
    ]
    for entry in required_entries:
        assert entry in doc

    # Every replacement the tables name is a package Chronicle ships.
    package_ids = {
        line.split(":", 1)[1].strip()
        for path in (repo_root / "packages").rglob("source_package.yaml")
        for line in path.read_text().splitlines()
        if line.startswith("package_id:")
    }
    named = set(
        re.findall(r"`((?:soi|cms|census|ssa|cbo|usda|kff)-[a-z0-9-]+)`", doc)
    ) - set(RETIRED_US_LEGACY_ETLS.values())
    assert named
    assert named <= package_ids
