"""The legacy target store and everything built on it stay retired.

The store was a local SQLite ``strata`` / ``stratum_constraints`` / ``targets``
schema filled by hand-written ``db/etl_*.py`` loaders, mirrored to Supabase
through ``arch.targets``, and read back by ``calibration/`` and the Microplex
pipeline in ``micro/us/``. Nothing outside that stack read it. These tests pin
its removal and the property the Thesis append path depends on: the gate and
catalog scripts import nothing from this repository's packages, so retiring
code under ``arch/``, ``db/`` or ``micro/`` cannot change what they execute.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Every module of the retired stack. A module listed here must not exist in
# the tree, must not import, and must not be imported by anything left.
RETIRED_MODULES = (
    "arch.normalization.targets",
    "arch.targets",
    "arch.targets.client",
    "arch.targets.loaders",
    "calibration",
    "calibration.constraints",
    "calibration.loader",
    "calibration.methods",
    "calibration.methods.entropy",
    "calibration.targets",
    "calibration.variables",
    "db.etl_aca_enrollment",
    "db.etl_bls",
    "db.etl_cbo",
    "db.etl_census",
    "db.etl_cps",
    "db.etl_cps_raw",
    "db.etl_hmrc",
    "db.etl_medicaid",
    "db.etl_obr",
    "db.etl_ons",
    "db.etl_snap",
    "db.etl_soi",
    "db.etl_soi_credits",
    "db.etl_soi_deductions",
    "db.etl_soi_income_sources",
    "db.etl_soi_state",
    "db.etl_ssa",
    "db.etl_ssi",
    "db.etl_targets_supabase",
    "micro.us.calibrate",
    "micro.us.district",
    "micro.us.hierarchical_pipeline",
    "micro.us.hierarchy_validation",
    "micro.us.pipeline",
    "micro.us.targets",
    "micro.us.validation_dashboard",
    "scripts.export_to_json",
)

# Names the retired modules exported. None may be defined or imported again.
RETIRED_NAMES = {
    "db.schema": {
        "GeographicLevel",
        "Stratum",
        "StratumConstraint",
        "Target",
        "TargetType",
    },
    "db.supabase_client": {
        "TARGETS_SCHEMA",
        "insert_targets_batch",
        "query_strata",
        "query_targets",
    },
    "arch.normalization": {"TargetBlueprint", "as_target", "target_kwargs"},
}

LEGACY_TARGET_TABLES = {"strata", "stratum_constraints", "targets"}
SOURCE_ARTIFACT_TABLES = {
    "source_artifacts",
    "source_columns",
    "source_rows",
    "source_tables",
}

# The scripts the Thesis append path runs. The append gate executes the
# base commit's check_thesis_facts_append.py (which loads receipt_pins.py);
# the push-path CI step runs verify_release_chain.py; the resolver in
# ThesisInstitute/thesis runs build_series_catalog.py with its own interpreter;
# cut_release_manifest.py and canonical_json.py cut and hash releases.
APPEND_PATH_SCRIPTS = (
    "build_series_catalog",
    "canonical_json",
    "check_thesis_facts_append",
    "cut_release_manifest",
    "receipt_pins",
    "verify_release_chain",
)
# Top-level modules that must never load on the append path: this
# repository's own packages and the third-party libraries only the retired
# stack and the source-artifact store use.
FORBIDDEN_APPEND_PATH_MODULES = {
    "arch",
    "calibration",
    "db",
    "micro",
    "packages",
    "sqlalchemy",
    "sqlmodel",
    "supabase",
}


def _module_path(module: str) -> Path:
    return REPO_ROOT.joinpath(*module.split("."))


@pytest.mark.parametrize("module", RETIRED_MODULES)
def test_retired_module_is_not_in_the_tree(module):
    path = _module_path(module)

    assert not path.with_suffix(".py").exists()
    assert not (path / "__init__.py").exists()


@pytest.mark.parametrize(
    "module", [m for m in RETIRED_MODULES if not m.startswith("scripts.")]
)
def test_retired_module_does_not_import(module):
    # find_spec imports the parent package first, so a submodule of a removed
    # package raises instead of returning None. Both mean "not importable".
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        spec = None
    assert spec is None


def test_no_db_etl_loader_remains():
    assert sorted(path.name for path in (REPO_ROOT / "db").glob("etl_*.py")) == []


def _python_files():
    for root in ("arch", "db", "micro", "packages", "scripts", "tests", "data"):
        yield from sorted((REPO_ROOT / root).rglob("*.py"))


def _imported_modules(tree: ast.AST, package: str) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".") if package else []
                if node.level > 1:
                    parts = parts[: len(parts) - (node.level - 1)]
                base = ".".join([*parts, node.module] if node.module else parts)
            else:
                base = node.module or ""
            imported.add(base)
            imported.update(f"{base}.{alias.name}" for alias in node.names)
    return imported


def test_nothing_left_imports_the_retired_stack():
    retired = set(RETIRED_MODULES)
    offenders = []
    for path in _python_files():
        relative = path.relative_to(REPO_ROOT)
        # The containing package: for pkg/__init__.py and pkg/mod.py alike,
        # drop the last path component.
        package = ".".join(relative.with_suffix("").parts[:-1])
        tree = ast.parse(path.read_text(), filename=str(relative))
        for name in _imported_modules(tree, package):
            if any(name == r or name.startswith(f"{r}.") for r in retired):
                offenders.append(f"{relative}: {name}")
            module, _, attribute = name.rpartition(".")
            if attribute in RETIRED_NAMES.get(module, ()):
                offenders.append(f"{relative}: {name}")

    assert offenders == []


def test_surviving_modules_do_not_define_retired_names():
    import arch.normalization as normalization
    import db.schema as schema
    import db.supabase_client as supabase_client

    modules = {
        "db.schema": schema,
        "db.supabase_client": supabase_client,
        "arch.normalization": normalization,
    }
    for module_name, names in RETIRED_NAMES.items():
        present = sorted(n for n in names if hasattr(modules[module_name], n))
        assert present == [], module_name


@pytest.mark.parametrize(
    "argv",
    [
        ["load", "all"],
        ["load", "soi-state"],
        ["stats"],
        ["query", "--variable", "tax_unit_count"],
    ],
)
def test_cli_rejects_retired_target_commands(monkeypatch, capsys, argv):
    from db import cli

    monkeypatch.setattr(sys, "argv", ["arch", *argv])
    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_init_creates_only_source_artifact_tables(monkeypatch, tmp_path):
    from db import cli

    db_path = tmp_path / "arch.db"
    monkeypatch.setattr(sys, "argv", ["arch", "--db", str(db_path), "init"])
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


def test_source_stats_reads_an_initialized_store(monkeypatch, capsys, tmp_path):
    from db import cli

    db_path = tmp_path / "arch.db"
    for command in ("init", "source-stats"):
        monkeypatch.setattr(sys, "argv", ["arch", "--db", str(db_path), command])
        cli.main()

    output = capsys.readouterr().out
    assert "Source artifacts: 0" in output
    assert "Source rows: 0" in output


def test_append_path_scripts_load_nothing_from_the_repository_packages(tmp_path):
    """Import every append-path script the way its callers do and list modules.

    The scripts run with ``scripts/`` on ``sys.path`` and the repository root
    off it (the gate sets ``PYTHONPATH`` to the base checkout's ``scripts/``
    and runs from the runner's temp directory; the resolver runs the staged
    generator by path). ``-I`` drops the environment and the current directory
    from ``sys.path``; the scripts directory is added back explicitly.
    """
    probe = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT / 'scripts')!r})\n"
        f"for name in {APPEND_PATH_SCRIPTS!r}:\n"
        "    __import__(name)\n"
        "print(json.dumps(sorted({m.split('.')[0] for m in sys.modules})))\n"
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PYTHON")
    }
    completed = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = set(json.loads(completed.stdout))

    assert set(APPEND_PATH_SCRIPTS) <= loaded
    assert loaded & FORBIDDEN_APPEND_PATH_MODULES == set()


def test_ci_does_not_load_the_retired_target_store():
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert " load all" not in workflow
    assert "arch-targets-ci.db" not in workflow
    for module in RETIRED_MODULES:
        assert f"import {module}\n" not in workflow
        assert f"from {module} import" not in workflow
        assert module.replace(".", "/") + ".py" not in workflow
        assert module.replace(".", "/") + "/" not in workflow
