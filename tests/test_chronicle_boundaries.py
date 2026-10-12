"""Boundary tests for Chronicle source-data ownership."""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml


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


# Legacy US loaders retired because their hand-typed values do not trace to
# publisher bytes, keyed by module name, with the `chronicle load` source each
# one answered to.
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
}
PACKAGE_BACKED_US_LOADERS = ["load_snap_targets", "load_soi_targets"]


def test_retired_us_legacy_etl_modules_are_not_shipped():
    repo_root = Path(__file__).resolve().parents[1]

    for module in RETIRED_US_LEGACY_ETLS:
        assert not (repo_root / "db" / f"{module}.py").exists()
        assert not (repo_root / "tests" / f"test_{module}.py").exists()
        assert importlib.util.find_spec(f"db.{module}") is None


@pytest.mark.parametrize("source", sorted(RETIRED_US_LEGACY_ETLS.values()))
def test_load_cli_rejects_retired_us_legacy_sources(monkeypatch, capsys, source):
    from db import cli

    monkeypatch.setattr(sys, "argv", ["chronicle", "load", source])
    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_us_loader_reexports_only_package_backed_loaders():
    import chronicle.jurisdictions.us as us_loaders
    import chronicle.targets.loaders as target_loaders

    for module in (target_loaders, us_loaders):
        assert sorted(module.__all__) == PACKAGE_BACKED_US_LOADERS
        assert all(callable(getattr(module, name)) for name in module.__all__)


def test_every_legacy_target_row_traces_to_a_checksummed_publisher_file(tmp_path):
    """`chronicle load all` writes only rows whose value file has a checksum."""
    from sqlmodel import Session, select

    from db.cli import cmd_load
    from db.schema import DataSource, Target, get_engine

    repo_root = Path(__file__).resolve().parents[1]
    soi_files = set()
    for table in ("table_1_1", "table_1_4"):
        manifest_path = repo_root / "db" / "data" / "irs_soi" / table / "manifest.yaml"
        for spec in yaml.safe_load(manifest_path.read_text())["files"].values():
            if re.fullmatch(r"[0-9a-f]{64}", spec.get("sha256", "")):
                soi_files.add(spec["source_url"])
    db_path = tmp_path / "targets.db"
    cmd_load(type("Args", (), {"db": str(db_path), "source": "all", "years": None}))

    with Session(get_engine(db_path)) as session:
        rows = session.exec(select(Target)).all()

    by_source = {source: 0 for source in (DataSource.IRS_SOI, DataSource.USDA_SNAP)}
    untraced = []
    for row in rows:
        if row.source == DataSource.IRS_SOI and row.source_url in soi_files:
            by_source[row.source] += 1
        elif row.source == DataSource.USDA_SNAP and re.search(
            r"sha256=[0-9a-f]{64}", row.notes or ""
        ):
            by_source[row.source] += 1
        else:
            untraced.append((row.source, row.variable, row.period, row.source_url))

    assert untraced == []
    assert all(count > 0 for count in by_source.values())


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


# Words the retired loaders used to label values they made up. A legacy loader
# that needs one of them is writing a number no publisher printed.
INVENTED_VALUE_MARKERS = re.compile(
    r"\b(representative|synthetic|scaled|placeholder|illustrative|approximately)\b",
    re.IGNORECASE,
)


def test_remaining_legacy_etl_modules_carry_no_invented_value_markers():
    db_root = Path(__file__).resolve().parents[1] / "db"
    violations = [
        f"{path.name}:{lineno}: {line.strip()}"
        for path in sorted(db_root.glob("etl_*.py"))
        for lineno, line in enumerate(path.read_text().splitlines(), start=1)
        if INVENTED_VALUE_MARKERS.search(line)
    ]

    assert violations == []
