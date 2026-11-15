"""The hosted Supabase mirror path and the Supabase client stay retired.

See docs/supabase-mirror-retirement.md: since the Ledger rename the loader and
`query_sources` defaulted to a `ledger` schema that does not exist in the
configured project, and nothing read a hosted copy. The client module and the
`supabase` dependency went with their last callers.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import re
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
    "POLICYENGINE_SUPABASE_URL",
    "get_supabase_client",
    "SupabaseConfig",
)
# Modules allowed to import a Supabase client. The legacy target-input helpers
# were its last callers; with them and the client retired, none may. The test
# compares for equality, so an entry that names no importer fails it too.
SUPABASE_CLIENT_IMPORTERS: frozenset[str] = frozenset()
# The `supabase` distribution and the client packages it is assembled from: the
# five that main's `uv.lock` listed under it before the retirement, then
# `gotrue` and `supafunc`, the names under which PyPI first carried
# `supabase-auth` and `supabase-functions`.
SUPABASE_DISTRIBUTIONS = frozenset(
    {
        "supabase",
        "postgrest",
        "realtime",
        "storage3",
        "supabase-auth",
        "supabase-functions",
        "gotrue",
        "supafunc",
    }
)
# Each of those installs one import package of the same name, with `-` as `_`.
SUPABASE_MODULES = (
    *sorted(name.replace("-", "_") for name in SUPABASE_DISTRIBUTIONS),
    "db.supabase_client",
    "chronicle.client",
)


def _shipped_roots() -> list[Path]:
    """Every package the wheel ships, plus the repository scripts."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    packages = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    return [REPO_ROOT / name for name in (*packages, "scripts")]


def _package_of(path: Path) -> str:
    """Dotted package a module at `path` belongs to, for resolving `from .x`."""
    relative = path.relative_to(REPO_ROOT).with_suffix("")
    return ".".join(relative.parts[:-1])


def _absolute(name: str, package: str) -> str | None:
    """`name` with its leading dots resolved against `package`, if they resolve."""
    try:
        return importlib.util.resolve_name(name, package)
    except ImportError:
        return None


def _argument(call: ast.Call, position: int, keyword: str) -> ast.expr | None:
    if len(call.args) > position:
        return call.args[position]
    return next((item.value for item in call.keywords if item.arg == keyword), None)


def _literal(node: ast.expr | None, kind: type = str):
    if isinstance(node, ast.Constant) and isinstance(node.value, kind):
        return node.value
    return None


# What each import-machinery name refers to before a module rebinds it. The
# function names count even where nothing imports them, as `__import__` does.
IMPORT_MACHINERY_NAMES = {
    "importlib": "importlib",
    "builtins": "builtins",
    "import_module": "import_module",
    "__import__": "__import__",
}
# The import functions those two modules carry.
IMPORT_FUNCTIONS = {
    ("importlib", "import_module"): "import_module",
    ("importlib", "__import__"): "__import__",
    ("builtins", "__import__"): "__import__",
}


def _machinery(node: ast.expr, bindings: dict[str, set[str]]) -> set[str]:
    """What `node` may refer to: `importlib`, `builtins` or an import function."""
    if isinstance(node, ast.Name):
        return bindings.get(node.id, set())
    if isinstance(node, ast.Attribute):
        owner, attribute = node.value, node.attr
    elif (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
    ):
        owner, attribute = node.args[0], _literal(node.args[1])
    else:
        return set()
    return {
        IMPORT_FUNCTIONS[(kind, attribute)]
        for kind in _machinery(owner, bindings)
        if (kind, attribute) in IMPORT_FUNCTIONS
    }


def _bound_names(node: ast.AST, bindings: dict[str, set[str]]):
    """(name, what it refers to) for each import-machinery name `node` binds."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            module = alias.name if alias.asname else alias.name.split(".")[0]
            if module in ("importlib", "builtins"):
                yield alias.asname or module, module
    elif isinstance(node, ast.ImportFrom) and node.level == 0:
        for alias in node.names:
            function = IMPORT_FUNCTIONS.get((node.module, alias.name))
            if function:
                yield alias.asname or alias.name, function
    elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        kinds = _machinery(node.value, bindings) if node.value else set()
        for target in targets:
            if isinstance(target, ast.Name):
                yield from ((target.id, kind) for kind in kinds)


def _machinery_bindings(tree: ast.AST) -> dict[str, set[str]]:
    """Every name `tree` binds to import machinery, aliases of aliases included.

    The scan ignores scope and order: a name bound to an import function
    anywhere in the module counts everywhere in it.
    """
    bindings = {name: {kind} for name, kind in IMPORT_MACHINERY_NAMES.items()}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            for name, kind in list(_bound_names(node, bindings)):
                if kind not in bindings.setdefault(name, set()):
                    bindings[name].add(kind)
                    changed = True
    return bindings


def _dynamically_imported(call: ast.Call, function: str, package: str) -> set[str]:
    """Modules `call` imports through `function` when a string literal names them.

    `function` is `import_module`, called as `import_module(name, package)`,
    or `__import__`, called as `__import__(name, globals, locals, fromlist,
    level)`.
    """
    name = _literal(_argument(call, 0, "name"))
    if name is None:
        return set()
    if function == "import_module":
        module = _absolute(name, _literal(_argument(call, 1, "package")) or "")
        return {module} if module else set()
    if name.startswith("."):  # `__import__` takes its dots from `level`
        return set()
    level = _literal(_argument(call, 4, "level"), int) or 0
    # A level above the package's depth cannot resolve. Checking first keeps a
    # large fifth argument, such as a 1_000_000_000 scale factor, from building
    # a string of that many dots.
    if level > (package.count(".") + 1 if package else 0):
        return set()
    module = _absolute("." * level + name, package)
    if module is None:
        return set()
    fromlist = _argument(call, 3, "fromlist")
    items = fromlist.elts if isinstance(fromlist, (ast.List, ast.Tuple)) else []
    return {module, *(f"{module}.{item}" for item in map(_literal, items) if item)}


def _imported_modules(tree: ast.AST, package: str) -> set[str]:
    """Modules that import statements or import-function calls in `tree` name."""
    bindings = _machinery_bindings(tree)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            name = _absolute("." * node.level + (node.module or ""), package)
            if name is None:
                continue
            modules.add(name)
            modules.update(f"{name}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            for function in _machinery(node.func, bindings):
                if function in ("import_module", "__import__"):
                    modules.update(_dynamically_imported(node, function, package))
    return modules


def _imports_supabase(modules: set[str]) -> bool:
    return any(
        module == target or module.startswith(f"{target}.")
        for module in modules
        for target in SUPABASE_MODULES
    )


def _requirements(pyproject: dict) -> list[str]:
    """Every requirement `pyproject` installs from, uv's older dev list included."""
    project = pyproject["project"]
    return [
        *project["dependencies"],
        *(
            requirement
            for group in project.get("optional-dependencies", {}).values()
            for requirement in group
        ),
        *(
            requirement
            for group in pyproject.get("dependency-groups", {}).values()
            for requirement in group
            if isinstance(requirement, str)
        ),
        *pyproject.get("tool", {}).get("uv", {}).get("dev-dependencies", []),
    ]


def _distribution(requirement: str) -> str:
    """The distribution `requirement` names, normalised as package indexes do."""
    name = re.match(r"[A-Za-z0-9]+(?:[-_.]+[A-Za-z0-9]+)*", requirement.strip())
    return re.sub(r"[-_.]+", "-", name.group()).lower() if name else ""


def _requires_supabase(requirement: str) -> bool:
    distribution = _distribution(requirement)
    return distribution in SUPABASE_DISTRIBUTIONS or distribution.startswith("supabase")


def _retired_surfaces_named(text: str) -> list[str]:
    return [needle for needle in RETIRED_SURFACE_STRINGS if needle in text]


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


def test_no_shipped_module_imports_a_supabase_client():
    importers = set()
    for root in _shipped_roots():
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if _imports_supabase(_imported_modules(tree, _package_of(path))):
                importers.add(path.relative_to(REPO_ROOT).as_posix())

    assert importers == SUPABASE_CLIENT_IMPORTERS


def test_supabase_is_not_a_dependency():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    requirements = _requirements(pyproject)

    assert requirements
    assert not [
        requirement for requirement in requirements if _requires_supabase(requirement)
    ]


@pytest.mark.parametrize(
    "pyproject",
    [
        '[project]\ndependencies = ["supabase"]',
        '[project]\ndependencies = []\noptional-dependencies.hosted = ["supabase"]',
        "[project]\ndependencies = []\n[dependency-groups]\n"
        'dev = ["supabase", {include-group = "docs"}]',
        '[project]\ndependencies = []\n[tool.uv]\ndev-dependencies = ["supabase"]',
    ],
)
def test_requirements_come_from_every_table_that_installs(pyproject):
    assert _requirements(tomllib.loads(pyproject)) == ["supabase"]


@pytest.mark.parametrize(
    ("requirement", "expected"),
    [
        ("supabase>=2.0", True),
        ("Supabase", True),
        ("supabase-py==0.0.2", True),
        ("postgrest>=2.27", True),
        ("realtime", True),
        ("storage3==2.27.0", True),
        ("supabase-auth>=2", True),
        ("supabase_auth ; python_version >= '3.14'", True),
        ("Supabase.Functions[all]", True),
        ("gotrue", True),
        ("supafunc<1", True),
        ("httpx>=0.27.0", False),
        ("pypdf[crypto]>=6.14.2", False),
        ("postgres>=1", False),
    ],
)
def test_supabase_requirement_detection(requirement, expected):
    assert _requires_supabase(requirement) is expected


@pytest.mark.parametrize(
    ("source", "package", "expected"),
    [
        ("from supabase import create_client", "chronicle", True),
        ("import supabase", "chronicle", True),
        ("import supabase.client as sc", "chronicle", True),
        ("from db.supabase_client import get_supabase_client", "chronicle", True),
        ("from db import supabase_client", "chronicle", True),
        ("from chronicle.client import get_supabase_client", "packages", True),
        ("def load():\n    from supabase import Client\n", "db", True),
        ("from .supabase_client import get_supabase_client", "db", True),
        ("from . import supabase_client", "db", True),
        ("from ..client import get_supabase_client", "chronicle.targets", True),
        ("from .client import get_supabase_client", "chronicle", True),
        ("importlib.import_module('supabase')", "chronicle", True),
        ("import_module(name='supabase.client')", "chronicle", True),
        ("importlib.import_module('.client', package='chronicle')", "db", True),
        ("importlib.import_module('..supabase_client', 'db.x')", "chronicle", True),
        ("__import__('supabase')", "chronicle", True),
        ("builtins.__import__('db.supabase_client')", "chronicle", True),
        ("__import__('db', fromlist=['supabase_client'])", "chronicle", True),
        ("__import__('supabase_client', globals(), None, [], 1)", "db", True),
        ("from postgrest import SyncPostgrestClient", "chronicle", True),
        ("import storage3", "db", True),
        ("from realtime import AsyncRealtimeClient", "chronicle", True),
        ("from supabase_auth import SyncGoTrueClient", "chronicle", True),
        ("import supabase_functions.errors", "chronicle", True),
        ("import gotrue", "chronicle", True),
        ("from supafunc import SyncFunctionsClient", "chronicle", True),
        ("importlib.import_module('postgrest')", "chronicle", True),
        # The scan follows every name bound to an import function.
        ("from importlib import import_module as load\nload('supabase')", "db", True),
        ("load = importlib.import_module\nload('storage3')", "chronicle", True),
        (
            "from importlib import import_module as load\n"
            "load('.client', package='chronicle')",
            "db",
            True,
        ),
        ("getattr(importlib, 'import_module')('supabase')", "chronicle", True),
        ("load = getattr(importlib, 'import_module')\nload('supabase')", "db", True),
        ("import importlib as il\nil.import_module('supabase')", "chronicle", True),
        (
            "def client():\n    import importlib as il\n\n"
            "    return il.import_module('postgrest')\n",
            "db",
            True,
        ),
        ("load = importlib.import_module\nfetch = load\nfetch('supabase')", "db", True),
        # ast.walk reaches `fetch = load` before the guarded import binds `load`.
        (
            "try:\n    from importlib import import_module as load\n"
            "except ImportError:\n    load = None\nfetch = load\nfetch('supabase')",
            "db",
            True,
        ),
        ("if load := importlib.import_module:\n    load('supabase')", "db", True),
        ("from importlib import __import__ as imp\nimp('supabase')", "chronicle", True),
        ("import builtins as b\nb.__import__('realtime')", "chronicle", True),
        ("imp = __import__\nimp('db', fromlist=['supabase_client'])", "db", True),
        (
            "imp = __import__\nimp('supabase_client', globals(), None, [], 1)",
            "db",
            True,
        ),
        (
            "imp = __import__\nimp('supabase_client', globals(), None, [], 2)",
            "db",
            False,
        ),
        (
            "imp = __import__\n"
            "imp('supabase_client', None, None, [], 100_000_000_000_000_000_000)",
            "db",
            False,
        ),
        # Any other call imports nothing, whatever string it passes.
        ("print('supabase')", "chronicle", False),
        ("importlib.metadata.version('supabase')", "chronicle", False),
        ("import importlib.metadata as md\nmd.version('supabase')", "chronicle", False),
        ("logger.warning('supabase')", "chronicle", False),
        ("host.endswith('supabase.co')", "chronicle", False),
        ("load = print\nload('supabase')", "chronicle", False),
        ("def load(name):\n    return name\n\n\nload('supabase')", "chronicle", False),
        ("from .client import helper", "chronicle.sources", False),
        ("from chronicle.sources import SourceFile", "chronicle", False),
        ("supabase = 'a string, not an import'", "chronicle", False),
        ("importlib.import_module('chronicle.sources')", "chronicle", False),
        ("importlib.import_module(module_name)", "chronicle", False),
        ("importlib.import_module('.client')", "chronicle", False),
        ("load = importlib.import_module\nload('.client')", "chronicle", False),
        ("print('supabase is retired')", "chronicle", False),
        ("log.info('importing %s', 'supabase')", "chronicle", False),
        ("from .realtime import feed", "chronicle.sources", False),
        ("from chronicle import realtime", "chronicle", False),
        ("import postgres", "chronicle", False),
    ],
)
def test_supabase_import_detection(source, package, expected):
    modules = _imported_modules(ast.parse(source), package)

    assert _imports_supabase(modules) is expected


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
        relative = path.relative_to(REPO_ROOT).as_posix()
        for needle in _retired_surfaces_named(path.read_text(encoding="utf-8")):
            offenders.append((relative, needle))

    assert offenders == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Run `chronicle load-supabase-mirror --dir out`.", ["load-supabase-mirror"]),
        ("Set `POLICYENGINE_SUPABASE_URL` first.", ["POLICYENGINE_SUPABASE_URL"]),
        (
            'httpx.post(os.environ["POLICYENGINE_SUPABASE_URL"] + path, json=rows)',
            ["POLICYENGINE_SUPABASE_URL"],
        ),
        ("from chronicle.client import get_supabase_client", ["get_supabase_client"]),
        ("config = SupabaseConfig.from_env()", ["SupabaseConfig"]),
        ("`db/supabase_client.py`'s `query_targets` and `query_strata`", []),
        ("https://stat-xplore.dwp.gov.uk/webapi/rest/v1/table", []),
    ],
)
def test_retired_surface_detection(text, expected):
    assert _retired_surfaces_named(text) == expected


def test_retirement_record_names_every_retired_surface():
    text = RETIREMENT_DOC.read_text(encoding="utf-8")

    for needle in (*RETIRED_SURFACE_STRINGS, *RETIRED_MIRROR_NAMES):
        assert needle in text, needle
    assert "load_supabase_mirror_files" in text
    assert "chronicle.sources.client" in text
