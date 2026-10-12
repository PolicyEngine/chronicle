"""The hosted Supabase mirror path stays retired.

See docs/supabase-mirror-retirement.md: the `ledger` schema the loader and
`query_sources` addressed never existed in the configured project, and nothing
read a hosted copy.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
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
# Modules allowed to import the Supabase client while the legacy target-input
# helpers remain. The set only shrinks.
SUPABASE_CLIENT_IMPORTERS = {
    "chronicle/client.py",
    "chronicle/targets/__init__.py",
    "chronicle/targets/client.py",
}


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
    import db.supabase_client as supabase_client
    import policyengine_chronicle.sources as public_sources

    for name in ("query_sources", "LEDGER_SCHEMA"):
        assert not hasattr(supabase_client, name)
    assert "query_sources" not in chronicle_sources.__all__
    assert not hasattr(chronicle_sources, "query_sources")
    assert "query_sources" not in public_sources.__all__
    with pytest.raises(AttributeError):
        getattr(public_sources, "query_sources")
    assert importlib.util.find_spec("chronicle.sources.client") is None


def test_supabase_client_is_reached_only_from_legacy_target_helpers():
    importers = set()
    for root in ("chronicle", "policyengine_chronicle", "db", "scripts"):
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            relative = path.relative_to(REPO_ROOT).as_posix()
            if relative == "db/supabase_client.py":
                continue
            text = path.read_text(encoding="utf-8")
            if "supabase_client" in text or "import supabase" in text:
                importers.add(relative)

    assert importers <= SUPABASE_CLIENT_IMPORTERS


def _surface_files():
    yield from sorted(REPO_ROOT.glob("*.md"))
    yield from sorted((REPO_ROOT / "docs").rglob("*.md"))
    for root in ("chronicle", "policyengine_chronicle", "db", "scripts"):
        yield from sorted((REPO_ROOT / root).rglob("*.py"))
    yield from sorted((REPO_ROOT / ".github").rglob("*.yml"))
    yield REPO_ROOT / "pyproject.toml"


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
