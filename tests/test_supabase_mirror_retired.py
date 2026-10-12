"""The hosted Supabase mirror path stays retired.

See docs/supabase-mirror-retirement.md: since the Ledger rename the loader and
`query_sources` defaulted to a `ledger` schema that does not exist in the
configured project, and nothing read a hosted copy.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RETIREMENT_DOC = REPO_ROOT / "docs" / "supabase-mirror-retirement.md"
RETIRED_MIRROR_NAMES = (
    "SupabaseMirrorLoadReport",
    "SupabaseTableLoad",
    "load_supabase_mirror",
)
# Names that should appear only in the retirement record, the changelog and
# this test.
RETIRED_SURFACE_STRINGS = (
    "load-supabase-mirror",
    "load_supabase_mirror",
    "query_sources",
    "POLICYENGINE_LEDGER_SCHEMA",
    "20260504_chronicle_bronze",
)
# Modules allowed to import a Supabase client while the legacy target-input
# helpers remain. The set only shrinks.
SUPABASE_CLIENT_IMPORTERS = {
    "chronicle/client.py",
    "chronicle/targets/__init__.py",
    "chronicle/targets/client.py",
    "db/supabase_client.py",
}
SUPABASE_MODULES = ("supabase", "db.supabase_client", "chronicle.client")


def _shipped_roots() -> list[Path]:
    """Every package the wheel ships, plus the repository scripts."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    packages = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    return [REPO_ROOT / name for name in (*packages, "scripts")]


def _imported_modules(tree: ast.AST) -> set[str]:
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _imports_supabase(modules: set[str]) -> bool:
    return any(
        module == target or module.startswith(f"{target}.")
        for module in modules
        for target in SUPABASE_MODULES
    )


def test_chronicle_cli_rejects_load_supabase_mirror(monkeypatch, capsys):
    from chronicle.cli import main

    monkeypatch.setattr(
        sys, "argv", ["chronicle", "load-supabase-mirror", "--dir", "unused"]
    )
    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 2
    assert "invalid choice: 'load-supabase-mirror'" in capsys.readouterr().err


def test_harness_parser_rejects_load_supabase_mirror(capsys):
    from chronicle.harness import main as harness_main

    with pytest.raises(SystemExit) as excinfo:
        harness_main(["load-supabase-mirror", "--dir", "unused"])

    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_mirror_module_only_exports_local_tables():
    import chronicle.harness as harness
    import chronicle.mirror as mirror

    for name in RETIRED_MIRROR_NAMES:
        assert not hasattr(mirror, name)
    assert not hasattr(harness, "load_supabase_mirror_files")
    assert "supabase" not in inspect.getsource(mirror).lower()


def test_query_sources_is_retired_from_every_namespace():
    import chronicle.sources as chronicle_sources
    import policyengine_chronicle.sources as public_sources

    assert "query_sources" not in chronicle_sources.__all__
    assert not hasattr(chronicle_sources, "query_sources")
    assert "query_sources" not in public_sources.__all__
    with pytest.raises(AttributeError):
        getattr(public_sources, "query_sources")
    assert importlib.util.find_spec("chronicle.sources.client") is None
    # The client module itself goes once the legacy target helpers are retired.
    if importlib.util.find_spec("db.supabase_client") is not None:
        supabase_client = importlib.import_module("db.supabase_client")
        for name in ("query_sources", "LEDGER_SCHEMA"):
            assert not hasattr(supabase_client, name)


def test_supabase_client_is_reached_only_from_legacy_target_helpers():
    importers = set()
    for root in _shipped_roots():
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if _imports_supabase(_imported_modules(tree)):
                importers.add(path.relative_to(REPO_ROOT).as_posix())

    assert importers <= SUPABASE_CLIENT_IMPORTERS


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from supabase import create_client", True),
        ("import supabase", True),
        ("import supabase.client as sc", True),
        ("from db.supabase_client import get_supabase_client", True),
        ("from db import supabase_client", True),
        ("from chronicle.client import get_supabase_client", True),
        ("def load():\n    from supabase import Client\n", True),
        ("from chronicle.sources import SourceFile", False),
        ("from .client import helper", False),
        ("supabase = 'a string, not an import'", False),
    ],
)
def test_supabase_import_detection(source, expected):
    assert _imports_supabase(_imported_modules(ast.parse(source))) is expected


def _surface_files():
    """Live code and docs. Work logs (PROGRESS.md, LANE_*) keep their history."""
    for name in ("README.md", "AGENTS.md", "pyproject.toml"):
        yield REPO_ROOT / name
    yield from sorted((REPO_ROOT / "docs").rglob("*.md"))
    yield from sorted((REPO_ROOT / "ots").rglob("*.md"))
    for pattern in ("*.md", "*.yml", "*.yaml"):
        yield from sorted((REPO_ROOT / ".github").rglob(pattern))
    for root in _shipped_roots():
        for pattern in ("*.py", "*.md"):
            yield from sorted(root.rglob(pattern))


def test_no_code_or_doc_advertises_the_retired_mirror():
    offenders = []
    for path in _surface_files():
        if path == RETIREMENT_DOC or not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for needle in RETIRED_SURFACE_STRINGS:
            if needle in text:
                offenders.append((path.relative_to(REPO_ROOT).as_posix(), needle))

    assert offenders == []


def test_retirement_record_names_every_retired_surface():
    text = RETIREMENT_DOC.read_text(encoding="utf-8")

    for needle in (*RETIRED_SURFACE_STRINGS, *RETIRED_MIRROR_NAMES):
        assert needle in text, needle
    assert "load_supabase_mirror_files" in text
    assert "chronicle.sources.client" in text
