"""Boundary tests for Chronicle source-data ownership."""

from __future__ import annotations

import ast
import hashlib
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


# The publisher measure each surviving legacy target row must reproduce, keyed by
# the row's variable and target type. IRS rows name the Publication 1304 table
# whose source package builds the fact.
IRS_ROW_MEASURES = {
    ("tax_unit_count", "COUNT"): (
        "soi-table-1-1",
        "irs_soi.individual_income_tax_returns",
    ),
    ("adjusted_gross_income", "AMOUNT"): (
        "soi-table-1-1",
        "us:statutes/26/62#adjusted_gross_income",
    ),
    ("income_tax_liability", "AMOUNT"): ("soi-table-1-1", "irs_soi.total_income_tax"),
    ("employment_income", "COUNT"): (
        "soi-table-1-4",
        "irs_soi.returns_with_total_wages",
    ),
    ("employment_income", "AMOUNT"): ("soi-table-1-4", "us:statutes/26/62#input.wages"),
}
SNAP_ROW_MEASURES = {
    ("snap_household_count", "COUNT"): (
        "usda_snap.average_monthly_households",
        "count",
    ),
    ("snap_participant_count", "COUNT"): ("usda_snap.average_monthly_persons", "count"),
    ("snap_benefits", "AMOUNT"): ("usda_snap.total_benefits", "dollars"),
}
IRS_AGI_CONCEPT = "us:statutes/26/62#adjusted_gross_income"
IRS_SOURCE_TABLES = {"soi-table-1-1": "Table 1.1", "soi-table-1-4": "Table 1.4"}


def _constraint_value(value: object) -> object:
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _irs_stratum(fact) -> frozenset:
    """The stratum definition a legacy row needs to carry this IRS fact."""
    bounds = {
        ("adjusted_gross_income", c.operator, _constraint_value(c.value))
        for c in fact.constraints
        if c.variable == IRS_AGI_CONCEPT
    }
    if len(bounds) != len(fact.constraints):
        return frozenset({("unsupported fact constraint", "", "")})
    return frozenset(bounds or {("is_tax_filer", "==", 1.0)})


def _snap_stratum(fact) -> frozenset:
    """The stratum definition a legacy row needs to carry this SNAP fact."""
    stratum = {("snap", "==", 1.0)}
    if fact.geography.id.startswith("0400000US"):
        fips = fact.geography.id.removeprefix("0400000US")
        stratum.add(("state_fips", "==", _constraint_value(fips)))
    elif fact.geography.id != "0100000US" or fact.constraints:
        return frozenset({("unsupported fact geography", "", "")})
    return frozenset(stratum)


# The top stratum of each surviving loader. Every other stratum it writes must
# hang directly under it.
NATIONAL_STRATA = {
    "irs-soi": frozenset({("is_tax_filer", "==", 1.0)}),
    "usda-snap": frozenset({("snap", "==", 1.0)}),
}


def _snap_provenance_note(fact, output_unit: str) -> str:
    """The lineage a SNAP row must record for this fact, field by field.

    The trailing derivation records the loader's identity unit conversion
    (factor 1), so the stored value is the published one.
    """
    source = fact.source
    parts = [f"USDA FNS {source.source_table}" if source.source_table else "USDA FNS"]
    for key, value in (
        ("source_file", source.source_file),
        ("vintage", source.vintage),
        ("sha256", source.source_sha256),
        ("raw", source.raw_r2_uri),
        ("record", fact.source_record_id),
    ):
        if value:
            parts.append(f"{key}={value}")
    return (
        "; ".join(parts) + " Derived via: convert_units(factor=1, "
        f"input_unit={fact.measure.unit}, output_unit={output_unit})."
    )


def _stratum_labels(fact, source: str) -> tuple[str, str, str]:
    """The name, description and group a loader gives the stratum of this fact."""
    if source == "irs-soi":
        band = fact.source_record_id.split(".")[3]
        if band == "all":
            return (
                "US All Filers",
                "All individual income tax returns filed in the US",
                "national",
            )
        return (
            f"US Filers AGI {band}",
            f"Tax filers with AGI in {band} bracket",
            "agi_brackets",
        )
    if fact.geography.id == "0100000US":
        return (
            "US SNAP Recipients",
            "All SNAP recipient households/individuals in the US",
            "snap_national",
        )
    name = fact.geography.name
    return f"{name} SNAP Recipients", f"SNAP recipients in {name}", "snap_states"


def _legacy_rows_without_publisher_fact(db_path: Path) -> list[tuple]:
    """Return target rows that do not reproduce their own publisher cell.

    Each row must match exactly one source-package fact on measure, period and
    the complete stratum definition (every constraint, with its operator), and
    equal that fact's value. IRS rows must cite the Table 1.1 or 1.4 workbook
    the fact was built from, by URL and table name, and the workbook's committed
    bytes must hash to its manifest sha256. SNAP rows must cite the package's
    source page and summary table, name the fact's source record and carry its
    sha256, and record every other lineage field (file, vintage, raw URI) as the
    fact does; IRS rows carry no notes. Each stratum must have the jurisdiction
    the loader assigns that geography, the name, description and group the loader
    gives it, and a definition hash that matches its constraints, and must sit
    directly under the loader's top stratum, whose own parent is null. No row may add a margin of error, a preliminary flag or a geographic
    level the fact does not support, or repeat a cell another row carries.
    """
    from sqlmodel import Session, select

    from chronicle.source_package import load_source_package
    from db.schema import (
        DataSource,
        Jurisdiction,
        Stratum,
        StratumConstraint,
        Target,
        get_engine,
    )

    repo_root = Path(__file__).resolve().parents[1]
    irs_files = {}
    for table, package_id in (
        ("table_1_1", "soi-table-1-1"),
        ("table_1_4", "soi-table-1-4"),
    ):
        table_dir = repo_root / "db" / "data" / "irs_soi" / table
        manifest = yaml.safe_load((table_dir / "manifest.yaml").read_text())
        for year, spec in manifest["files"].items():
            content = (table_dir / spec["filename"]).read_bytes()
            if hashlib.sha256(content).hexdigest() == spec["sha256"]:
                irs_files[spec["source_url"]] = (package_id, int(year), spec)
    snap_manifest = yaml.safe_load(
        (
            repo_root
            / "db"
            / "data"
            / "usda_snap"
            / "fy69_to_current"
            / "manifest.yaml"
        ).read_text()
    )

    irs_facts: dict[tuple[str, int], list] = {}
    snap_package = load_source_package("usda-snap-fy69-to-current")
    snap_facts = snap_package.build_facts(snap_package.artifact.artifact_year)

    with Session(get_engine(db_path)) as session:
        rows = session.exec(select(Target)).all()
        stratum_rows = {
            stratum.id: stratum for stratum in session.exec(select(Stratum)).all()
        }
        strata: dict[int, set] = {}
        raw_constraints: dict[int, list] = {}
        for constraint in session.exec(select(StratumConstraint)).all():
            raw_constraints.setdefault(constraint.stratum_id, []).append(
                (constraint.variable, constraint.operator, constraint.value)
            )
            strata.setdefault(constraint.stratum_id, set()).add(
                (
                    constraint.variable,
                    constraint.operator,
                    _constraint_value(constraint.value),
                )
            )

    untraced = []
    reproduced: set[tuple] = set()
    for row in rows:
        stratum = frozenset(strata.get(row.stratum_id, set()))
        measure_key = (row.variable, row.target_type.name)
        matched = []
        if (
            row.source == DataSource.IRS_SOI
            and row.source_url in irs_files
            and measure_key in IRS_ROW_MEASURES
        ):
            package_id, year, spec = irs_files[row.source_url]
            row_package, concept = IRS_ROW_MEASURES[measure_key]
            if (package_id, year) not in irs_facts:
                irs_facts[package_id, year] = load_source_package(
                    package_id
                ).build_facts(year)
            if (
                row_package == package_id
                and row.source_table == IRS_SOURCE_TABLES[package_id]
            ):
                matched = [
                    fact
                    for fact in irs_facts[package_id, year]
                    if fact.measure.concept == concept
                    and fact.period.value == row.period
                    and _irs_stratum(fact) == stratum
                    and fact.source.source_file == spec["filename"]
                    and fact.source.source_sha256 == spec["sha256"]
                ]
        elif (
            row.source == DataSource.USDA_SNAP
            and measure_key in SNAP_ROW_MEASURES
            and row.source_url == snap_manifest["source_page"]
        ):
            record = re.search(r"record=([^;\s]+)", row.notes or "")
            sha = re.search(r"sha256=([0-9a-f]{64})", row.notes or "")
            matched = [
                fact
                for fact in snap_facts
                if fact.measure.concept == SNAP_ROW_MEASURES[measure_key][0]
                and fact.period.value == row.period
                and _snap_stratum(fact) == stratum
                and row.source_table
                == (
                    "SNAP National Summary"
                    if fact.geography.id == "0100000US"
                    else "SNAP State Summary"
                )
                and record is not None
                and sha is not None
                and fact.source_record_id == record.group(1)
                and fact.source.source_sha256 == sha.group(1)
            ]
        fact = matched[0] if len(matched) == 1 else None
        if fact is None:
            untraced.append((row.source, row.variable, row.period, row.value))
            continue
        national = fact.geography.id == "0100000US"
        top = NATIONAL_STRATA[row.source]
        row_stratum = stratum_rows[row.stratum_id]
        parent = stratum_rows.get(row_stratum.parent_id)
        if row.source == DataSource.IRS_SOI:
            jurisdiction = Jurisdiction.US_FEDERAL
            notes_ok = not row.notes
        else:
            jurisdiction = Jurisdiction.US_FEDERAL if national else Jurisdiction.US
            notes_ok = (row.notes or "") == _snap_provenance_note(
                fact, SNAP_ROW_MEASURES[measure_key][1]
            )
        if stratum == top:
            parent_ok = row_stratum.parent_id is None
        else:
            parent_ok = (
                parent is not None
                and frozenset(strata.get(parent.id, set())) == top
                and parent.parent_id is None
                and parent.jurisdiction == Jurisdiction.US_FEDERAL
            )
        if (
            fact.value != row.value
            or (fact.source_record_id, fact.measure.concept) in reproduced
            or row.margin_of_error is not None
            or row.is_preliminary
            or row.geographic_level not in (None, "national" if national else "state")
            or row_stratum.jurisdiction != jurisdiction
            or (row_stratum.name, row_stratum.description, row_stratum.stratum_group_id)
            != _stratum_labels(fact, row.source)
            or row_stratum.definition_hash
            != Stratum.compute_hash(
                raw_constraints.get(row.stratum_id, []), row_stratum.jurisdiction
            )
            or not parent_ok
            or not notes_ok
        ):
            untraced.append((row.source, row.variable, row.period, row.value))
        else:
            reproduced.add((fact.source_record_id, fact.measure.concept))
    return untraced


@pytest.fixture(scope="module")
def loaded_legacy_db(tmp_path_factory):
    """A targets database built by `chronicle load all`."""
    from db.cli import cmd_load

    db_path = tmp_path_factory.mktemp("legacy") / "targets.db"
    cmd_load(type("Args", (), {"db": str(db_path), "source": "all", "years": None}))
    return db_path


def test_every_legacy_target_row_equals_a_checksummed_publisher_fact(loaded_legacy_db):
    """Every row `chronicle load all` writes reproduces its own publisher cell."""
    from sqlmodel import Session, select

    from db.schema import DataSource, Target, get_engine

    with Session(get_engine(loaded_legacy_db)) as session:
        sources = {row.source for row in session.exec(select(Target)).all()}

    assert _legacy_rows_without_publisher_fact(loaded_legacy_db) == []
    assert sources == {DataSource.IRS_SOI, DataSource.USDA_SNAP}


_NATIONAL_2021 = "stratum_id = (select id from strata where name = 'US All Filers') and period = 2021"
_SNAP_STATE_ROW = (
    "(select t.{column} from targets t join stratum_constraints c "
    "on c.stratum_id = t.stratum_id where c.variable = 'state_fips' "
    "and c.value = '{fips}' and t.variable = 'snap_household_count')"
)
PROVENANCE_MUTATIONS = {
    "every value set to 1.0": ("update targets set value = 1.0", 562),
    "every period set to 1900": ("update targets set period = 1900", 562),
    "SNAP checksums zeroed": (
        "update targets set notes = replace(notes, substr(notes, "
        "instr(notes, 'sha256=') + 7, 64), '" + "0" * 64 + "') "
        "where source = 'USDA_SNAP'",
        162,
    ),
    "one IRS value plus 1": (
        "update targets set value = value + 1 where id = "
        "(select min(id) from targets where source = 'IRS_SOI')",
        1,
    ),
    "one SNAP value plus 1": (
        "update targets set value = value + 1 where id = "
        "(select min(id) from targets where source = 'USDA_SNAP')",
        1,
    ),
    "national income tax replaced by national AGI from the same workbook": (
        f"update targets set value = (select value from targets where {_NATIONAL_2021} "
        f"and variable = 'adjusted_gross_income') where {_NATIONAL_2021} "
        "and variable = 'income_tax_liability'",
        1,
    ),
    "Maine SNAP households replaced by Connecticut's value and record": (
        "update targets set value = "
        + _SNAP_STATE_ROW.format(column="value", fips="09")
        + ", notes = "
        + _SNAP_STATE_ROW.format(column="notes", fips="09")
        + " where id = "
        + _SNAP_STATE_ROW.format(column="id", fips="23"),
        1,
    ),
    "Maine's state_fips constraint negated": (
        "update stratum_constraints set operator = '!=' "
        "where variable = 'state_fips' and value = '23'",
        3,
    ),
    "national SNAP households moved into an AGI band": (
        "update targets set stratum_id = "
        "(select id from strata where name = 'US Filers AGI 50k_to_75k') "
        "where variable = 'snap_household_count' and stratum_id = "
        "(select id from strata where name = 'US SNAP Recipients')",
        1,
    ),
    "SNAP rows citing an IRS workbook": (
        "update targets set source_url = 'https://www.irs.gov/pub/irs-soi/23in11si.xls' "
        "where source = 'USDA_SNAP'",
        162,
    ),
    "every source table renamed": (
        "update targets set source_table = 'Table 9.9'",
        562,
    ),
    "a valid row duplicated": (
        "insert into targets (stratum_id, variable, period, value, target_type, "
        "source, source_table, source_url, notes, is_preliminary, created_at, "
        "updated_at) select stratum_id, variable, period, value, target_type, source, "
        "source_table, source_url, notes, is_preliminary, created_at, updated_at "
        "from targets where source = 'USDA_SNAP' limit 1",
        1,
    ),
    "a margin of error added": (
        "update targets set margin_of_error = 1000 where id = (select min(id) from targets)",
        1,
    ),
    "a national row labelled state": (
        f"update targets set geographic_level = 'STATE' where {_NATIONAL_2021} "
        "and variable = 'tax_unit_count'",
        1,
    ),
    # The 20 national rows, plus the 380 AGI-band rows whose parent it is.
    "national IRS stratum moved to the UK": (
        "update strata set jurisdiction = 'UK' where name = 'US All Filers'",
        400,
    ),
    "SNAP rows naming an IRS workbook as their file": (
        "update targets set notes = replace(notes, "
        "'source_file=snap-zip-fy69tocurrent-6.zip!FY24.xlsx', "
        "'source_file=23in11si.xls') where source = 'USDA_SNAP'",
        162,
    ),
    "an AGI band re-parented under the SNAP stratum": (
        "update strata set parent_id = (select id from strata "
        "where name = 'US SNAP Recipients') where name = 'US Filers AGI 50k_to_75k'",
        20,
    ),
    "an IRS row given a note": (
        "update targets set notes = 'sha256=' || hex(randomblob(32)) "
        "where id = (select min(id) from targets where source = 'IRS_SOI')",
        1,
    ),
    "national IRS stratum renamed": (
        "update strata set name = 'Canada All Filers' where name = 'US All Filers'",
        20,
    ),
    "national IRS stratum described as the UK": (
        "update strata set description = "
        "'All individual income tax returns filed in the UK' "
        "where name = 'US All Filers'",
        20,
    ),
    "national IRS stratum filed under the AGI-band group": (
        "update strata set stratum_group_id = 'agi_brackets' "
        "where name = 'US All Filers'",
        20,
    ),
    "SNAP state strata filed under the national group": (
        "update strata set stratum_group_id = 'snap_national' "
        "where stratum_group_id = 'snap_states'",
        159,
    ),
    # A dangling parent on a top stratum flags its rows and every row under it.
    "national IRS stratum given a dangling parent": (
        "update strata set parent_id = 999999 where name = 'US All Filers'",
        400,
    ),
    "national SNAP stratum given a dangling parent": (
        "update strata set parent_id = 999999 where name = 'US SNAP Recipients'",
        162,
    ),
    "national IRS definition hash zeroed": (
        "update strata set definition_hash = '0000000000000000' "
        "where name = 'US All Filers'",
        20,
    ),
    # Several statements, because the hash column is unique.
    "national and one AGI-band definition hashes swapped": (
        (
            "create temp table saved as select name, definition_hash from strata "
            "where name in ('US All Filers', 'US Filers AGI 50k_to_75k')",
            "update strata set definition_hash = 'swapping' where name = 'US All Filers'",
            "update strata set definition_hash = (select definition_hash from saved "
            "where name = 'US All Filers') where name = 'US Filers AGI 50k_to_75k'",
            "update strata set definition_hash = (select definition_hash from saved "
            "where name = 'US Filers AGI 50k_to_75k') where name = 'US All Filers'",
        ),
        40,
    ),
    "row from a retired source": (
        "insert into targets (stratum_id, variable, period, value, target_type, "
        "source, is_preliminary, created_at, updated_at) select stratum_id, "
        "'ssi_recipients', 2023, 7425331, target_type, 'SSA', 0, created_at, "
        "updated_at from targets limit 1",
        1,
    ),
}


@pytest.mark.parametrize("mutation", sorted(PROVENANCE_MUTATIONS))
def test_provenance_check_flags_rows_that_do_not_reproduce_their_cell(
    loaded_legacy_db, tmp_path, mutation
):
    import shutil
    import sqlite3

    sql, expected = PROVENANCE_MUTATIONS[mutation]
    statements = (sql,) if isinstance(sql, str) else sql
    mutated = tmp_path / "mutated.db"
    shutil.copy(loaded_legacy_db, mutated)
    with sqlite3.connect(mutated) as connection:
        for statement in statements:
            changed = connection.execute(statement).rowcount
            if statement.startswith(("update", "insert")):
                assert changed >= 1

    assert len(_legacy_rows_without_publisher_fact(mutated)) == expected


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
