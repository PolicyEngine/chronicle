"""Boundary tests for Chronicle source-data ownership."""

from __future__ import annotations

import ast
import functools
import importlib.util
import re
import sys
from pathlib import Path

import pytest
from markdown_it import MarkdownIt


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


# The cleanup doc's "Where the publisher's values live" tables name, in this
# column, each package that replaces a retired series and then the ids it
# declares, for example `soi-historic-table-2-state-broad-2022` `ctc_*`
# (`N07225`/`A07225`). A cell splits into clauses at each `;` outside
# parentheses. Within a clause, an id belongs to every package listed since the
# previous id: `a`, `b`: `x` claims `x` for both packages, `a` `x`, `y` claims
# both ids for `a`. An exact id must be a measure id or a record-set row value
# id the package declares; a `prefix_*` wildcard must match at least one of its
# measure ids. An IRS column code names a source column that a measure matched
# by the id before it reads. Every backticked token in this column is a claim,
# so a historical id is written without backticks.
REPLACEMENT_COLUMN = "Chronicle package and measures"
DOC_PACKAGE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+")
DOC_DECLARED_ID = re.compile(r"[a-z0-9][a-z0-9_]*(?:_\*)?")
DOC_COLUMN_CODE = re.compile(r"[AN][0-9]+")

# measure id -> the source column ids it reads, and the row value ids.
Declarations = tuple[dict[str, set[str]], set[str]]


def _markdown_tables(doc: str) -> list[tuple[str, list[str], list[list[str]]]]:
    """Return each table as (the heading above it, header cells, body rows).

    The doc is read by a CommonMark parser with GitHub's table extension, so a
    table counts wherever GitHub renders one: indented, without outer pipes, in
    a blockquote, list item or HTML block, under a heading of any form. A cell
    is its Markdown source, with `\\|` read as a pipe; a short row is padded.
    """
    tables: list[tuple[str, list[str], list[list[str]]]] = []
    heading = ""
    in_heading = in_header = in_cell = False
    row: list[str] = []
    for token in MarkdownIt("commonmark", {"html": True}).enable("table").parse(doc):
        kind = token.type
        if kind in ("heading_open", "heading_close"):
            in_heading = kind == "heading_open"
        elif kind in ("thead_open", "thead_close"):
            in_header = kind == "thead_open"
            if in_header:
                tables.append((heading, [], []))
        elif kind == "tr_open":
            row = tables[-1][1] if in_header else []
            if not in_header:
                tables[-1][2].append(row)
        elif kind in ("th_open", "td_open", "th_close", "td_close"):
            in_cell = kind.endswith("_open")
        elif kind == "inline" and in_heading:
            heading = token.content
        elif kind == "inline" and in_cell:
            row.append(token.content)
    return tables


def _is_replacement_column(header_cell: str) -> bool:
    """Whether a header cell, read without emphasis, code or escape marks, is it."""
    return re.sub(r"[\\*_`]", "", header_cell).strip().casefold() == (
        REPLACEMENT_COLUMN.casefold()
    )


def _replacement_cells(doc: str) -> list[str]:
    """Return every cell of every "Chronicle package and measures" column."""
    return [
        row[column]
        for _, header, rows in _markdown_tables(doc)
        for row in rows
        for column, cell in enumerate(header)
        if _is_replacement_column(cell)
    ]


def _clauses(cell: str) -> list[str]:
    """Split a cell at each `;` outside parentheses."""
    clauses = []
    depth = start = 0
    for index, char in enumerate(cell):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == ";" and depth == 0:
            clauses.append(cell[start:index])
            start = index + 1
    clauses.append(cell[start:])
    return clauses


@functools.cache
def _declarations(package_path: Path) -> Declarations:
    """Return a package's measure ids with their source columns, and its row ids."""
    from chronicle.source_package import load_source_package

    measures: dict[str, set[str]] = {}
    rows: set[str] = set()
    for record_set in load_source_package(package_path).record_sets:
        for measure in record_set.payload["measures"]:
            columns = measures.setdefault(measure["measure_id"], set())
            if measure.get("source_column_id") is not None:
                columns.add(str(measure["source_column_id"]))
        rows.update(row["value_id"] for row in record_set.payload["rows"])
    return measures, rows


def _matching_measures(declared_id: str, measures: dict[str, set[str]]) -> list[str]:
    """Return the measure ids an exact id or a `prefix_*` wildcard names."""
    if declared_id.endswith("_*"):
        return [measure for measure in measures if measure.startswith(declared_id[:-1])]
    return [declared_id] if declared_id in measures else []


def _replacement_claim_errors(
    cells: list[str], declarations: dict[str, Declarations]
) -> tuple[list[tuple[str, ...]], list[str]]:
    """Check every package, id and column claim the cells make.

    ``declarations`` holds every shipped package the cells name. Returns the
    claims checked and a message for each that the packages do not back.
    """
    claims: list[tuple[str, ...]] = []
    errors: list[str] = []
    for cell in cells:
        for clause in _clauses(cell):
            packages: list[str] = []
            last_id = None
            for token in re.findall(r"`([^`]+)`", clause):
                if DOC_PACKAGE_ID.fullmatch(token):
                    if last_id is not None:
                        packages, last_id = [], None
                    packages.append(token)
                    if token not in declarations:
                        errors.append(f"`{token}` is not a shipped package")
                elif DOC_COLUMN_CODE.fullmatch(token):
                    if last_id is None:
                        errors.append(f"{clause.strip()!r}: `{token}` follows no id")
                        continue
                    for package in packages:
                        if package not in declarations:
                            continue
                        measures = declarations[package][0]
                        claims.append((package, last_id, token))
                        if not any(
                            token in measures[measure]
                            for measure in _matching_measures(last_id, measures)
                        ):
                            errors.append(
                                f"{package}: no `{last_id}` measure reads `{token}`"
                            )
                elif DOC_DECLARED_ID.fullmatch(token):
                    if not packages:
                        errors.append(
                            f"{clause.strip()!r}: `{token}` follows no package"
                        )
                    for package in packages:
                        if package not in declarations:
                            continue
                        measures, rows = declarations[package]
                        claims.append((package, token))
                        # Row ids never end in `_*`, so a wildcard matches
                        # measures only.
                        if (
                            not _matching_measures(token, measures)
                            and token not in rows
                        ):
                            errors.append(f"{package}: declares no `{token}`")
                    last_id = token
                else:
                    errors.append(f"{clause.strip()!r}: cannot read `{token}`")
    return claims, errors


@functools.cache
def _shipped_package_paths() -> dict[str, Path]:
    """Map each package id under packages/ to its source_package.yaml."""
    return {
        line.split(":", 1)[1].strip(): path
        for path in (Path(__file__).resolve().parents[1] / "packages").rglob(
            "source_package.yaml"
        )
        for line in path.read_text().splitlines()
        if line.startswith("package_id:")
    }


REPLACEMENT_SECTION = "Where the publisher's values live"
REPLACEMENT_HEADER = ["ETL series", REPLACEMENT_COLUMN, "Gap"]
# Every table in the cleanup doc, as (heading above it, header). A table added,
# moved or reheaded fails the doc test until it is listed here, so no table can
# make replacement claims the check does not read.
DOC_TABLES = [
    ("US legacy ETL cleanup", ["Loader", "Outcome", "Why"]),
    (
        "Retired: invented IRS SOI state values",
        ["Module", "What its comments said", "Rows it wrote"],
    ),
    (
        "Evidence",
        [
            "Legacy series (2021, 51 geographies)",
            "IRS column",
            "Within 0.5%",
            "Median error",
            "Example, legacy vs IRS",
        ],
    ),
    (REPLACEMENT_SECTION, REPLACEMENT_HEADER),
    (
        "Retired: hand-typed values from other publishers",
        ["Module", "Rows on main", "Evidence"],
    ),
    (REPLACEMENT_SECTION, REPLACEMENT_HEADER),
]
LAYOUT_ERROR = "the cleanup doc's tables differ from DOC_TABLES"


def _us_legacy_etl_cleanup_doc_claim_errors(
    doc: str,
) -> tuple[list[tuple[str, ...]], list[str]]:
    """Check the doc's table layout and the claims its replacement cells make.

    The doc's tables must be DOC_TABLES. The claims of every replacement column
    are checked, wherever its table is.
    """
    layout = [(heading, header) for heading, header, _ in _markdown_tables(doc)]
    layout_errors = [] if layout == DOC_TABLES else [LAYOUT_ERROR]

    cells = _replacement_cells(doc)
    paths = _shipped_package_paths()
    named = {
        token
        for cell in cells
        for token in re.findall(r"`([^`]+)`", cell)
        if DOC_PACKAGE_ID.fullmatch(token)
    }
    declarations = {
        package_id: _declarations(paths[package_id])
        for package_id in sorted(named & set(paths))
    }
    claims, errors = _replacement_claim_errors(cells, declarations)
    return claims, layout_errors + errors


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
    package_ids = set(_shipped_package_paths())
    named = set(
        re.findall(r"`((?:soi|cms|census|ssa|cbo|usda|kff)-[a-z0-9-]+)`", doc)
    ) - set(RETIRED_US_LEGACY_ETLS.values())
    assert named
    assert named <= package_ids

    # Each "Where the publisher's values live" section holds one replacement
    # table. Every id a replacement cell names next to a package is one that
    # package declares, and every IRS column code is one its measure reads.
    cells = _replacement_cells(doc)
    assert cells
    for cell in cells:
        tokens = re.findall(r"`([^`]+)`", cell)
        assert cell == "—" or any(DOC_PACKAGE_ID.fullmatch(t) for t in tokens), cell
    claims, errors = _us_legacy_etl_cleanup_doc_claim_errors(doc)
    assert errors == []
    assert {package for package, *_ in claims} >= {
        "soi-historic-table-2-state-broad-2022",
        "soi-congressional-district-2022",
        "cms-aca-oep-state-level-2025",
        "ssa-annual-statistical-supplement-2025",
    }


# Packages for the replacement-claim check, as (measure id -> source columns,
# row value ids).
FAKE_DECLARATIONS: dict[str, Declarations] = {
    "pkg-a": (
        {
            "return_count": {"N1"},
            "ctc_claims": {"N07225"},
            "ctc_amount": {"A07225"},
            "payment_amount": set(),
        },
        {"ssi_payments"},
    ),
    "pkg-b": ({"return_count": {"N1"}}, set()),
}


def _fake_row_claim_errors(cell: str) -> tuple[list[tuple[str, ...]], list[str]]:
    """Check one replacement cell, in a one-row table, against FAKE_DECLARATIONS."""
    doc = (
        f"| Series | {REPLACEMENT_COLUMN} | Gap |\n|---|---|---|\n| x | {cell} | y |\n"
    )
    return _replacement_claim_errors(_replacement_cells(doc), FAKE_DECLARATIONS)


@pytest.mark.parametrize(
    ("cell", "claims"),
    [
        ("`pkg-a` `return_count`", [("pkg-a", "return_count")]),
        (
            "`pkg-a` `ctc_*` (`N07225`/`A07225`, state rows; see note)",
            [
                ("pkg-a", "ctc_*"),
                ("pkg-a", "ctc_*", "N07225"),
                ("pkg-a", "ctc_*", "A07225"),
            ],
        ),
        (
            "`pkg-a` (2024), `pkg-b`: `return_count` by state",
            [("pkg-a", "return_count"), ("pkg-b", "return_count")],
        ),
        (
            "`pkg-a` `ctc_claims` and `pkg-b` `return_count`; `pkg-b`",
            [("pkg-a", "ctc_claims"), ("pkg-b", "return_count")],
        ),
        (
            "`pkg-a` `payment_amount` (`ssi_payments` row)",
            [("pkg-a", "payment_amount"), ("pkg-a", "ssi_payments")],
        ),
        ("—", []),
    ],
)
def test_replacement_claim_check_accepts_declared_ids(cell, claims):
    assert _fake_row_claim_errors(cell) == (claims, [])


@pytest.mark.parametrize(
    ("cell", "error"),
    [
        ("`pkg-a` `return_counts`", "pkg-a: declares no `return_counts`"),
        ("`pkg-a` `actc_*`", "pkg-a: declares no `actc_*`"),
        ("`pkg-a` `ssi_*`", "pkg-a: declares no `ssi_*`"),
        ("`pkg-a`, `pkg-b`: `ctc_claims`", "pkg-b: declares no `ctc_claims`"),
        ("`pkg-a` `ctc_*` (`N11070`)", "pkg-a: no `ctc_*` measure reads `N11070`"),
        (
            "`pkg-a` `ssi_payments` (`N1`)",
            "pkg-a: no `ssi_payments` measure reads `N1`",
        ),
        ("`pkg-c` `return_count`", "`pkg-c` is not a shipped package"),
        (
            "`return_count` in `pkg-a`",
            "'`return_count` in `pkg-a`': `return_count` follows no package",
        ),
        (
            "`pkg-a`; `return_count`",
            "'`return_count`': `return_count` follows no package",
        ),
        ("`pkg-a` (`N1`)", "'`pkg-a` (`N1`)': `N1` follows no id"),
        (
            "`pkg-a` `Return count`",
            "'`pkg-a` `Return count`': cannot read `Return count`",
        ),
    ],
)
def test_replacement_claim_check_flags_undeclared_ids(cell, error):
    assert _fake_row_claim_errors(cell)[1] == [error]


def test_markdown_tables_read_cells_as_github_renders_them():
    doc = (
        "## Heading ##\n\nProse | with a pipe\n\n"
        f"| Series | {REPLACEMENT_COLUMN} | Gap |\n|---|---|---|\n"
        "| x | `pkg-a` `N1`\\|`A1` | y | not rendered |\n"
        "  w | `pkg-b`\n"
    )

    assert _markdown_tables(doc) == [
        (
            "Heading",
            ["Series", REPLACEMENT_COLUMN, "Gap"],
            [["x", "`pkg-a` `N1`|`A1`", "y"], ["w", "`pkg-b`", ""]],
        )
    ]


def test_replacement_cells_read_every_replacement_column():
    doc = (
        f"| Series | **{REPLACEMENT_COLUMN}** | `{REPLACEMENT_COLUMN.lower()}` |\n"
        "| :--- | --- | ---: |\n"
        "| x | `pkg-a` | `pkg-b` |\n\n"
        f"> | Series | {REPLACEMENT_COLUMN}\\* |\n> |---|---|\n> | x | `pkg-c` |\n\n"
        "| Series | Chronicle packages |\n|---|---|\n| x | `pkg-d` |\n"
    )

    assert _replacement_cells(doc) == ["`pkg-a`", "`pkg-b`", "`pkg-c`"]


# Edits to the real doc, as ((text, replacement) pairs, the errors they must
# raise). Each is valid GitHub Markdown that shows the edited claim in a
# rendered replacement column; the indented row, row without outer pipes,
# escaped pipe, bold or escaped header, repeated column and tables in a
# blockquote, list item or HTML block each got past an earlier table reader.
BROAD = "soi-historic-table-2-state-broad-2022"
MEDICAL_ROW = (
    "| `db/etl_soi_deductions.py` `medical_claims`, `medical_amount` (state) "
    f"| `{BROAD}` `medical_dental_expense_*` | None for 2022. |"
)
BAD_MEDICAL_ROW = MEDICAL_ROW.replace("expense_*", "expense_amt")
BAD_MEDICAL_ERROR = f"{BROAD}: declares no `medical_dental_expense_amt`"
BAD_MEDICAL_TABLE = (
    f"| {' | '.join(REPLACEMENT_HEADER)} |\n|---|---|---|\n{BAD_MEDICAL_ROW}"
)
OTHER_PUBLISHERS = "## Retired: hand-typed values from other publishers"
ACA_HEADER = (
    f"| {' | '.join(REPLACEMENT_HEADER)} |\n|---|---|---|\n"
    "| `db/etl_aca_enrollment.py` state and national plan selections"
)
ACA_GAP = (
    "| The OEP packages publish state rows only, so national totals are a gap, "
    "and the 2023 OEP file is not packaged. |"
)


def _move_bad_medical_row(table: str) -> list[tuple[str, str]]:
    """Edits that move the medical row, mistyped, into `table` further down."""
    return [
        (MEDICAL_ROW + "\n", ""),
        (OTHER_PUBLISHERS, f"{table}\n\n{OTHER_PUBLISHERS}"),
    ]


DOC_MUTATIONS = {
    "renamed measure": (
        [
            (
                f"`{BROAD}` `return_count`, `adjusted_gross_income`",
                f"`{BROAD}` `return_counts`, `adjusted_gross_income`",
            )
        ],
        [f"{BROAD}: declares no `return_counts`"],
    ),
    "indented row": (
        [(MEDICAL_ROW, "  " + BAD_MEDICAL_ROW)],
        [BAD_MEDICAL_ERROR],
    ),
    "row without outer pipes": (
        [(MEDICAL_ROW, BAD_MEDICAL_ROW.strip("|"))],
        [BAD_MEDICAL_ERROR],
    ),
    "escaped pipe between column codes": (
        [("`N19300`/`A19300`", "`N19300`\\|`A19301`")],
        [f"{BROAD}: no `mortgage_interest_paid_*` measure reads `A19301`"],
    ),
    "second table with a bold header": (
        [
            (
                MEDICAL_ROW,
                f"\n| ETL series | **{REPLACEMENT_COLUMN}** | Gap |\n|---|---|---|\n"
                + BAD_MEDICAL_ROW,
            )
        ],
        [LAYOUT_ERROR, BAD_MEDICAL_ERROR],
    ),
    "repeated replacement column": (
        [
            (ACA_HEADER, ACA_HEADER.replace("| Gap |", f"| {REPLACEMENT_COLUMN} |")),
            (ACA_GAP, f"| `{BROAD}` `medical_dental_expense_amt` |"),
        ],
        [LAYOUT_ERROR, BAD_MEDICAL_ERROR],
    ),
    "row moved into a blockquote": (
        _move_bad_medical_row(
            "\n".join(f"> {line}" for line in BAD_MEDICAL_TABLE.splitlines())
        ),
        [LAYOUT_ERROR, BAD_MEDICAL_ERROR],
    ),
    "row moved into a list item": (
        _move_bad_medical_row("- " + BAD_MEDICAL_TABLE.replace("\n", "\n  ")),
        [LAYOUT_ERROR, BAD_MEDICAL_ERROR],
    ),
    "row moved into an HTML block": (
        _move_bad_medical_row(f"<details>\n\n{BAD_MEDICAL_TABLE}\n\n</details>"),
        [LAYOUT_ERROR, BAD_MEDICAL_ERROR],
    ),
    "row moved to a new table with an escaped header": (
        _move_bad_medical_row(
            "### More replacements\n\n"
            + BAD_MEDICAL_TABLE.replace(REPLACEMENT_COLUMN, REPLACEMENT_COLUMN + "\\*")
        ),
        [LAYOUT_ERROR, BAD_MEDICAL_ERROR],
    ),
}


@pytest.mark.parametrize("mutation", sorted(DOC_MUTATIONS))
def test_us_legacy_etl_cleanup_doc_check_flags_edited_claims(mutation):
    """A claim the doc's tables make next to a real package must still hold."""
    doc = (
        Path(__file__).resolve().parents[1] / "docs" / "us-legacy-etl-cleanup.md"
    ).read_text()
    edits, expected = DOC_MUTATIONS[mutation]
    for text, replacement in edits:
        assert doc.count(text) == 1
        doc = doc.replace(text, replacement)

    assert _us_legacy_etl_cleanup_doc_claim_errors(doc)[1] == expected


@pytest.mark.parametrize(
    "heading",
    [
        " ### Where the publisher's values live ###  ",
        "Where the publisher's values live\n---",
        "Where the publisher's values live\n===",
    ],
)
def test_us_legacy_etl_cleanup_doc_check_reads_any_heading_form(heading):
    doc = (
        Path(__file__).resolve().parents[1] / "docs" / "us-legacy-etl-cleanup.md"
    ).read_text()
    original = "### Where the publisher's values live"
    assert doc.count(original) == 2

    claims, errors = _us_legacy_etl_cleanup_doc_claim_errors(
        doc.replace(original, heading)
    )

    assert errors == []
    assert claims
