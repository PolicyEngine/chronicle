"""The artifact-year restamp guard (PolicyEngine/chronicle#117).

``artifact_year`` pins which file a source package reads: every build year reads
the artifact year's file. A build at another year that selects exactly the cells
the artifact-year build selects, but renders different labels (period, record
ids, vintage, legal_vintage, ...), would restamp one year's data as another
year. The guard refuses those builds and lets year-selecting packages through.

Invariant under test: for a package pinned to artifact year A and any build
year Y, the build at Y either raises, or emits no fact whose value,
``source_cell_keys`` and ``source_row_keys`` equal a fact of the A build while
any other field differs.
"""

from __future__ import annotations

import functools
import hashlib
import itertools
import json
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
import yaml

import chronicle.bundle as bundle_module
import chronicle.source_package as source_package_module
from chronicle.bundle import build_bundle
from chronicle.harness import main as harness_main
from chronicle.source_package import (
    ARTIFACT_YEAR_RESTAMP_CODE,
    ArtifactYearRestampError,
    DeclarativeRecordSet,
    SourceArtifactSpec,
    SourcePackage,
    artifact_year_restamp_issues,
    discover_source_package_dirs,
    load_source_package,
    validate_source_package,
)
from chronicle.store import fact_to_mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_YEAR = 2021
BUILD_YEARS = (2020, 2021, 2022, 2023, 2024)
# Years the synthetic publisher file covers. 2023 is deliberately absent, so a
# year-selecting package has nothing to read at 2023 and must fail loudly.
FILE_YEARS = (2020, 2021, 2022, 2024)
VALUES = {2020: 100, 2021: 110, 2022: 120, 2024: 140}
WIDE_COLUMNS = {2020: "C", 2021: "D", 2022: "E", 2024: "F"}
# Every label a synthetic package can template with {year}.
LABEL_FIELDS = (
    "period",
    "record_ids",
    "legal_vintage",
    "artifact_vintage",
    "source_table",
    "filter",
)
# How a synthetic package reads the year: not at all (a fixed column of the
# pinned file), or by column, by source row or by sheet.
MECHANISMS = ("none", "column_by_year", "selected_rows", "sheet_name_by_year")


# --- synthetic packages -----------------------------------------------------


def _wide_csv() -> bytes:
    header = ",".join(["Item", "Unit", *(str(year) for year in FILE_YEARS)])
    row = ",".join(["Returns", "count", *(str(VALUES[y]) for y in FILE_YEARS)])
    return f"{header}\n{row}\n".encode()


def _long_csv() -> bytes:
    lines = ["Item,Period,Value"]
    lines.extend(f"Returns,{year},{VALUES[year]}" for year in FILE_YEARS)
    return ("\n".join(lines) + "\n").encode()


@functools.cache
def _sheets_xlsx() -> bytes:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for year in FILE_YEARS:
        sheet = workbook.create_sheet(f"TY{year}")
        sheet.append(["Item", "Unit", "Value"])
        sheet.append(["Returns", "count", VALUES[year]])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _artifact_bytes(mechanism: str) -> tuple[bytes, str]:
    if mechanism in {"none", "column_by_year"}:
        return _wide_csv(), "synthetic_wide.csv"
    if mechanism == "selected_rows":
        return _long_csv(), "synthetic_long.csv"
    return _sheets_xlsx(), "synthetic_sheets.xlsx"


def _payload(templated: frozenset[str], mechanism: str) -> dict:
    """A source-package payload pinned to ARTIFACT_YEAR.

    Each field in ``templated`` renders ``{year}``; every other label is the
    literal artifact year. ``mechanism`` decides how the build reads the year.
    """

    def label(field: str, pattern: str) -> str:
        year = "{year}" if field in templated else str(ARTIFACT_YEAR)
        return pattern.replace("@", year)

    artifact = {
        "source_name": "test",
        "source_table": label("source_table", "Synthetic returns, tax year @"),
        "vintage": label("artifact_vintage", "tax_year_@"),
        "extracted_at": "2026-09-25",
        "extraction_method": "synthetic test artifact",
        "artifact_year": ARTIFACT_YEAR,
    }
    measure = {
        "measure_id": "count",
        "label": "Returns",
        "ordinal": 0,
        "concept": "test.returns",
        "unit": "count",
        "aggregation": "sum",
        "legal_vintage": label("legal_vintage", "tax_year_@"),
    }
    record_set = {
        "record_set_id": label("record_ids", "test.ty@.returns"),
        "provenance_class": "administrative",
        "record_set_spec_id": "test.returns.v1",
        "source_record_id_prefix": label("record_ids", "test.ty@.returns"),
        "period_type": "tax_year",
        "period": label("period", "@"),
        "geography_id": "0100000US",
        "geography_level": "country",
        "entity": "tax_unit",
        "domain": "test",
        "groupby_dimension": "test.item",
        # A universe filter and its explicit constraint: labels on the fact.
        "shared_filters": {"tax_year": label("filter", "@")},
        "shared_constraints": [
            {
                "variable": "tax_year",
                "operator": "==",
                "value": label("filter", "@"),
                "label": "Tax year",
            }
        ],
        "rows": [
            {
                "value_id": "returns",
                "label": "Returns",
                "ordinal": 0,
                "row_number": 2,
                "expected_row_header_column": "A",
                "table_record_kind": "total",
            }
        ],
        "measures": [measure],
    }
    if mechanism in {"none", "column_by_year"}:
        artifact.update(parser="delimited_text_full_rows", sheet_name="synthetic")
        record_set["sheet_name"] = "synthetic"
        if mechanism == "none":
            measure["column"] = WIDE_COLUMNS[ARTIFACT_YEAR]
        else:
            measure["column_by_year"] = dict(WIDE_COLUMNS)
    elif mechanism == "selected_rows":
        artifact.update(
            parser="delimited_text_full_rows",
            sheet_name="synthetic",
            selected_rows=[{"Item": "Returns", "Period": "{year}"}],
        )
        record_set["sheet_name"] = "synthetic"
        measure["column"] = "C"
    elif mechanism == "sheet_name_by_year":
        artifact.update(parser="xlsx_used_range")
        record_set["sheet_name_by_year"] = {year: f"TY{year}" for year in FILE_YEARS}
        measure["column"] = "C"
    else:
        raise AssertionError(mechanism)
    return {
        "schema_version": "ledger.source_package.v1",
        "package_id": "test-artifact-year-restamp",
        "dimension_labels": {"test.item": "Test item"},
        "artifact": artifact,
        "record_sets": [record_set],
    }


class _PinnedInlineArtifact(SourceArtifactSpec):
    """A pinned artifact held in memory: the same bytes at every build year."""

    def __init__(self, *, content: bytes, filename: str, **fields) -> None:
        super().__init__(
            resource_package="unused",
            resource_directory="unused",
            manifest="unused",
            **fields,
        )
        object.__setattr__(self, "_content", content)
        object.__setattr__(self, "_filename", filename)

    def _artifact_content(self, year: int) -> tuple[bytes, str, str, dict[str, str]]:
        key = f"raw/test/test-artifact-year-restamp/{self.artifact_year}/x"
        return (
            self._content,
            self._filename,
            f"https://example.test/{self._filename}",
            {"bucket": "test", "key": key, "uri": f"r2://test/{key}"},
        )


def _package(templated=frozenset(), mechanism="none") -> SourcePackage:
    payload = _payload(frozenset(templated), mechanism)
    artifact = dict(payload["artifact"])
    selected_rows = tuple(artifact.pop("selected_rows", ()))
    content, filename = _artifact_bytes(mechanism)
    return SourcePackage(
        package_id=payload["package_id"],
        label=None,
        artifact=_PinnedInlineArtifact(
            content=content,
            filename=filename,
            selected_rows=selected_rows,
            **artifact,
        ),
        record_sets=tuple(DeclarativeRecordSet(rs) for rs in payload["record_sets"]),
        package_path=Path("synthetic"),
        dimension_labels=payload["dimension_labels"],
    )


def _write_package(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    templated=frozenset(),
    mechanism: str = "none",
    *,
    name: str = "package",
) -> Path:
    """Write a synthetic package and its pinned artifact to disk; return its dir."""
    resource = (
        "restamp_fixture_" + hashlib.sha256(str(root / name).encode()).hexdigest()[:16]
    )
    resource_dir = root / "resources" / resource
    data_dir = resource_dir / "data" / "synthetic"
    data_dir.mkdir(parents=True)
    (resource_dir / "__init__.py").write_text("", encoding="utf-8")
    content, filename = _artifact_bytes(mechanism)
    (data_dir / filename).write_bytes(content)
    manifest = {
        "files": {
            ARTIFACT_YEAR: {
                "filename": filename,
                "source_url": f"https://example.test/{filename}",
                "sha256": hashlib.sha256(content).hexdigest(),
                "storage": {
                    "r2": {
                        "provider": "r2",
                        "bucket": "test",
                        "key": f"raw/test/{name}/{ARTIFACT_YEAR}/{filename}",
                        "uri": f"r2://test/raw/test/{name}/{ARTIFACT_YEAR}/{filename}",
                    }
                },
            }
        }
    }
    (data_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    monkeypatch.syspath_prepend(str(root / "resources"))
    payload = _payload(frozenset(templated), mechanism)
    payload["package_id"] = f"test-artifact-year-restamp-{name}"
    payload["artifact"].update(
        resource_package=resource,
        resource_directory="data/synthetic",
        manifest="manifest.yaml",
    )
    package_dir = root / "packages" / name
    package_dir.mkdir(parents=True)
    (package_dir / "source_package.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    return package_dir


# --- fact comparison ---------------------------------------------------------


def _serialized(fact) -> str:
    return json.dumps(fact_to_mapping(fact), sort_keys=True, default=str)


def _lineage(fact) -> tuple:
    return (
        json.dumps(fact.value, default=str),
        tuple(fact.source_cell_keys),
        tuple(fact.source_row_keys or ()),
    )


def _restamped_facts(facts_at_year, facts_at_artifact_year) -> list:
    """Facts that repeat an artifact-year fact's value and lineage but not its labels."""
    by_lineage: dict[tuple, set[str]] = {}
    for fact in facts_at_artifact_year:
        by_lineage.setdefault(_lineage(fact), set()).add(_serialized(fact))
    return [
        fact
        for fact in facts_at_year
        if _lineage(fact) in by_lineage
        and _serialized(fact) not in by_lineage[_lineage(fact)]
    ]


def _unguarded_facts(package: SourcePackage, year: int):
    """build_facts without the guard; None when the build fails for another reason."""
    original = source_package_module.artifact_year_restamp_issues
    source_package_module.artifact_year_restamp_issues = lambda package, year: []
    try:
        return package.build_facts(year)
    except (KeyError, TypeError, ValueError):
        return None
    finally:
        source_package_module.artifact_year_restamp_issues = original


# --- unit tests: refuse ------------------------------------------------------


def test_pinned_package_with_year_templated_period_refuses_off_year_builds():
    package = _package({"period", "record_ids", "legal_vintage", "artifact_vintage"})

    facts = package.build_facts(ARTIFACT_YEAR)
    assert [fact.period.value for fact in facts] == [ARTIFACT_YEAR]
    assert facts[0].value == VALUES[ARTIFACT_YEAR]

    for build in (
        package.build_facts,
        package.build_source_rows,
        package.build_source_cells,
        package.build_source_record_set_specs,
        package.build_source_record_specs,
        package.build_source_regions,
        package.build_source_records,
    ):
        with pytest.raises(ArtifactYearRestampError) as raised:
            build(ARTIFACT_YEAR + 3)
        assert raised.value.package_id == "test-artifact-year-restamp"
        assert raised.value.artifact_year == ARTIFACT_YEAR
        assert raised.value.year == ARTIFACT_YEAR + 3
        assert [issue.code for issue in raised.value.issues] == [
            ARTIFACT_YEAR_RESTAMP_CODE
        ]
    # The error is a ValueError, so existing `except ValueError` paths (bundle
    # source-suite failures, CLI) report it rather than crash differently.
    assert issubclass(ArtifactYearRestampError, ValueError)


def test_restamp_message_names_the_package_years_and_moved_labels():
    package = _package({"period", "record_ids", "legal_vintage", "artifact_vintage"})

    (issue,) = artifact_year_restamp_issues(package, 2024)

    assert issue.code == ARTIFACT_YEAR_RESTAMP_CODE
    assert issue.record_set_id == "test.ty2024.returns"
    message = issue.message
    assert "'test-artifact-year-restamp' pins artifact_year 2021" in message
    assert "a build at year 2024 reads the same cells as the 2021 build" in message
    assert "artifact.vintage 'tax_year_2021' -> 'tax_year_2024'" in message
    assert "record_set_id 'test.ty2021.returns' -> 'test.ty2024.returns'" in message
    assert "period 2021 -> 2024" in message
    assert "measures[0].legal_vintage 'tax_year_2021' -> 'tax_year_2024'" in message
    assert "column_by_year" in message


@pytest.mark.parametrize(
    "templated",
    [{"legal_vintage"}, {"artifact_vintage"}, {"source_table"}, {"filter"}],
    ids=lambda fields: "-".join(sorted(fields)),
)
def test_a_single_templated_label_is_enough_to_refuse(templated):
    package = _package(templated)

    assert artifact_year_restamp_issues(package, 2024)
    with pytest.raises(ArtifactYearRestampError):
        package.build_facts(2024)
    # The period is literal, so only the templated label would have moved.
    unguarded = _unguarded_facts(package, 2024)
    assert [fact.period.value for fact in unguarded] == [ARTIFACT_YEAR]
    assert _restamped_facts(unguarded, package.build_facts(ARTIFACT_YEAR))


def test_validate_reports_restamp_as_an_error(tmp_path, monkeypatch, capsys):
    package_dir = _write_package(
        tmp_path,
        monkeypatch,
        {"period", "record_ids", "legal_vintage", "artifact_vintage"},
    )

    at_artifact_year = validate_source_package(package_dir, year=ARTIFACT_YEAR)
    off_year = validate_source_package(package_dir, year=2024)

    assert at_artifact_year.valid, at_artifact_year.to_dict()
    assert not off_year.valid
    assert [error.code for error in off_year.errors] == [ARTIFACT_YEAR_RESTAMP_CODE]
    # Counts still describe the package, so the report stays useful.
    assert off_year.counts == at_artifact_year.counts
    assert harness_main(["validate-package", str(package_dir), "--year", "2024"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"][0]["code"] == ARTIFACT_YEAR_RESTAMP_CODE


# --- unit tests: allow -------------------------------------------------------


@pytest.mark.parametrize(
    "mechanism",
    ["column_by_year", "selected_rows", "sheet_name_by_year"],
)
def test_year_selecting_pinned_package_builds_off_year_with_that_years_value(
    mechanism,
):
    package = _package(set(LABEL_FIELDS), mechanism)

    assert artifact_year_restamp_issues(package, 2024) == []
    facts = package.build_facts(2024)
    base = package.build_facts(ARTIFACT_YEAR)

    assert [(fact.period.value, fact.value) for fact in facts] == [(2024, 140)]
    assert [(fact.period.value, fact.value) for fact in base] == [(2021, 110)]
    # A different column or sheet gives different source cells; a different
    # selected source row lands on the same virtual cell but a different
    # source row. Either way the lineage differs from the artifact-year fact.
    assert _lineage(facts[0]) != _lineage(base[0])
    assert _restamped_facts(facts, base) == []


@pytest.mark.parametrize(
    "mechanism",
    ["column_by_year", "selected_rows", "sheet_name_by_year"],
)
def test_year_selecting_package_fails_loudly_for_a_year_its_file_lacks(mechanism):
    package = _package(set(LABEL_FIELDS), mechanism)

    assert artifact_year_restamp_issues(package, 2023) == []
    with pytest.raises(ValueError) as raised:
        package.build_facts(2023)
    assert not isinstance(raised.value, ArtifactYearRestampError)


def test_literal_labels_build_the_artifact_year_facts_at_any_year():
    package = _package()
    base = [_serialized(fact) for fact in package.build_facts(ARTIFACT_YEAR)]

    for year in BUILD_YEARS:
        assert artifact_year_restamp_issues(package, year) == []
        assert [_serialized(fact) for fact in package.build_facts(year)] == base


def test_guard_ignores_unpinned_packages_and_the_artifact_year_itself():
    package = _package({"period"})
    unpinned = SourcePackage(
        package_id=package.package_id,
        label=None,
        artifact=_PinnedInlineArtifact(
            content=package.artifact._content,
            filename=package.artifact._filename,
            **{
                **{
                    name: getattr(package.artifact, name)
                    for name in (
                        "source_name",
                        "source_table",
                        "vintage",
                        "extracted_at",
                        "extraction_method",
                        "parser",
                        "sheet_name",
                    )
                },
                "artifact_year": None,
            },
        ),
        record_sets=package.record_sets,
        package_path=package.package_path,
    )

    assert artifact_year_restamp_issues(package, ARTIFACT_YEAR) == []
    assert artifact_year_restamp_issues(unpinned, 2024) == []
    assert unpinned.build_facts(2024)[0].period.value == 2024
    # Non-integer build keys (release labels, chronicle#79) render no {year}.
    assert artifact_year_restamp_issues(package, "release_2026") == []


def test_guard_verdict_is_cached_per_package_and_year():
    package = _package({"period"})

    first = artifact_year_restamp_issues(package, 2024)
    assert package._restamp_issues_by_year == {2024: tuple(first)}
    assert artifact_year_restamp_issues(package, 2024) == first
    assert artifact_year_restamp_issues(_package(), 2024) == []


# --- bundles -----------------------------------------------------------------


def _bundle_rows(output_dir: Path) -> list[dict]:
    text = (output_dir / "consumer_facts.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_default_bundle_skips_a_restamping_package_and_says_why(
    tmp_path,
    monkeypatch,
):
    restamp = str(
        _write_package(tmp_path, monkeypatch, {"period", "record_ids"}, name="r")
    )
    literal = str(_write_package(tmp_path, monkeypatch, name="literal"))
    monkeypatch.setattr(bundle_module, "DEFAULT_BUNDLE_SOURCES", (restamp, literal))
    monkeypatch.setattr(bundle_module, "assert_alias_map_covers_packages", lambda: None)

    report = build_bundle(tmp_path / "bundle", year=2024)

    (skipped,) = report.skipped_sources
    assert skipped.source == restamp
    assert ARTIFACT_YEAR_RESTAMP_CODE in skipped.reason
    assert [error["code"] for error in skipped.validation["errors"]] == [
        ARTIFACT_YEAR_RESTAMP_CODE
    ]
    # The literal-label package still builds, with its own year's period.
    assert [source.source for source in report.source_packages] == [literal]
    assert "source_suite_build_failed" not in {error.code for error in report.errors}
    assert {row["period"]["value"] for row in _bundle_rows(tmp_path / "bundle")} == {
        ARTIFACT_YEAR
    }


def test_explicit_source_that_would_restamp_fails_the_bundle(
    tmp_path,
    monkeypatch,
    capsys,
):
    restamp = str(
        _write_package(tmp_path, monkeypatch, {"period", "record_ids"}, name="r")
    )

    at_artifact_year = build_bundle(
        tmp_path / "at-artifact-year",
        year=ARTIFACT_YEAR,
        sources=[restamp],
    )
    report = build_bundle(tmp_path / "off-year", year=2024, sources=[restamp])

    assert "source_suite_build_failed" not in {
        error.code for error in at_artifact_year.errors
    }
    assert not report.valid
    assert [(error.code, error.source) for error in report.errors] == [
        ("source_suite_build_failed", restamp)
    ]
    assert "pins artifact_year 2021" in report.errors[0].message
    assert _bundle_rows(tmp_path / "off-year") == []
    exit_code = harness_main(
        [
            "build-bundle",
            "--year",
            "2024",
            "--source",
            restamp,
            "--out",
            str(tmp_path / "cli"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["valid"] is False
    assert payload["errors"][0]["code"] == "source_suite_build_failed"


# --- property: exhaustive enumeration ----------------------------------------


def test_guard_matches_the_restamp_invariant_over_every_synthetic_combination():
    """Exhaustive over label subsets x selection mechanisms x build years.

    Hypothesis is not a Chronicle dependency (see pyproject.toml / uv.lock), so
    this enumerates the whole space instead of sampling it: 2**6 templated label
    subsets x 4 mechanisms x 5 build years = 1,280 cases. For each case it
    checks that

    - the guard fires exactly when the year selects nothing (mechanism
      "none"), Y != A, and at least one label is templated;
    - a refused build raises ArtifactYearRestampError, and the build the guard
      refused would have restamped (differential: without the guard the build
      emits a fact with A's value and lineage but different labels);
    - an allowed build either fails with its own error or emits exactly what
      the unguarded build emits, and none of it is a restamp.
    """
    cases = 0
    for size in range(len(LABEL_FIELDS) + 1):
        for templated in itertools.combinations(LABEL_FIELDS, size):
            for mechanism in MECHANISMS:
                package = _package(frozenset(templated), mechanism)
                base = _unguarded_facts(package, ARTIFACT_YEAR)
                assert base, (templated, mechanism)
                for year in BUILD_YEARS:
                    cases += 1
                    case = (templated, mechanism, year)
                    expected = (
                        year != ARTIFACT_YEAR
                        and mechanism == "none"
                        and bool(templated)
                    )
                    issues = artifact_year_restamp_issues(package, year)
                    assert bool(issues) is expected, case
                    unguarded = _unguarded_facts(package, year)
                    if expected:
                        with pytest.raises(ArtifactYearRestampError):
                            package.build_facts(year)
                        assert unguarded is not None, case
                        assert _restamped_facts(unguarded, base), case
                        continue
                    if unguarded is None:
                        # Only a year-selecting package at a year its file
                        # lacks fails; it must fail with its own error.
                        assert mechanism != "none" and year not in FILE_YEARS, case
                        with pytest.raises(ValueError) as raised:
                            package.build_facts(year)
                        assert not isinstance(raised.value, ArtifactYearRestampError)
                        continue
                    guarded = package.build_facts(year)
                    assert [_serialized(f) for f in guarded] == [
                        _serialized(f) for f in unguarded
                    ], case
                    assert _restamped_facts(guarded, base) == [], case
    assert cases == 2 ** len(LABEL_FIELDS) * len(MECHANISMS) * len(BUILD_YEARS)


# --- the real package tree ---------------------------------------------------


def _pinned_year_dependent_packages() -> list[str]:
    """Pinned packages whose YAML renders {year}/{filing_year} or has *_by_year."""
    packages = []
    for sub in discover_source_package_dirs(REPO_ROOT / "packages"):
        path = REPO_ROOT / "packages" / sub / "source_package.yaml"
        text = path.read_text(encoding="utf-8")
        if "artifact_year:" not in text:
            continue
        if "{year" in text or "{filing_year" in text or "_by_year:" in text:
            packages.append(str(sub))
    return sorted(packages)


PINNED_YEAR_DEPENDENT = _pinned_year_dependent_packages()


def test_real_tree_has_pinned_year_dependent_packages_to_check():
    # Guards the parametrization below against silently checking nothing.
    assert len(PINNED_YEAR_DEPENDENT) >= 10
    assert "bea/regional_personal_income_state" in PINNED_YEAR_DEPENDENT


@pytest.mark.parametrize("package_path", PINNED_YEAR_DEPENDENT)
def test_no_pinned_package_restamps_at_neighbouring_or_default_years(package_path):
    """Every pinned, year-dependent package passes the guard at A-1, A+1, 2023.

    2023 is the default bundle year (``build-bundle --year`` default).
    """
    package = load_source_package(REPO_ROOT / "packages" / package_path)
    artifact_year = package.artifact.artifact_year
    for year in sorted({artifact_year - 1, artifact_year + 1, 2023} - {artifact_year}):
        assert artifact_year_restamp_issues(package, year) == [], (package_path, year)


# A representative subset of pinned packages whose builds take a second or
# two, covering each way a pinned package meets a non-artifact build year:
# literal labels (the W-2, IRA and Historic Table 2 packages and ICI, whose
# labels this change pinned to the artifact year), column_by_year (BEA
# regional, CBO projections, CMS NHE), a column_by_year that lacks the artifact
# year itself (CBO receipts, Federal Reserve Z.1) and selected_rows that filter
# on {year} (Census projections). The slow builds (soi-state-2022 at 50-90 s,
# the BEA NIPA packages at ~6 s, the 26,880-fact congressional-district
# package) stay out of the default suite; the guard-only test above covers
# them, and the PR's before/after build evidence covers their facts.
REPRESENTATIVE_PINNED_PACKAGES = (
    "irs_soi/w2_statistics_2020",
    "irs_soi/ira_roth_contributions_2022",
    "irs_soi/ira_traditional_contributions_2022",
    "irs_soi/historic_table_2",
    "ici/fact_book_table_30",
    "bea/regional_personal_income_state",
    "cbo/revenue_projections_income_by_source_2026_02",
    "cbo/individual_income_tax_receipts_2026_02",
    "cms_nhe/table_24",
    "federal_reserve/z1_household_net_worth",
    "census/population_projections_2023",
)


@pytest.mark.parametrize("package_path", REPRESENTATIVE_PINNED_PACKAGES)
def test_real_pinned_builds_never_restamp_the_artifact_year_facts(package_path):
    """The invariant on real bytes, and the guard agreeing with the built facts."""
    package = load_source_package(REPO_ROOT / "packages" / package_path)
    artifact_year = package.artifact.artifact_year
    years = (artifact_year - 1, artifact_year + 1)
    base = _unguarded_facts(package, artifact_year)
    for year in years:
        issues = artifact_year_restamp_issues(package, year)
        unguarded = _unguarded_facts(package, year)
        would_restamp = bool(
            base is not None
            and unguarded is not None
            and _restamped_facts(unguarded, base)
        )
        assert bool(issues) is would_restamp, (package_path, year)
        try:
            facts = package.build_facts(year)
        except ValueError:
            continue  # the build raises: the invariant holds
        if base is not None:  # else A has no facts (column_by_year lacks A)
            assert _restamped_facts(facts, base) == [], (package_path, year)


def _as_origin_main_had_it(tmp_path: Path, package_path: str, edit) -> Path:
    """Copy a real package into tmp_path with ``edit`` applied to its payload.

    The copy keeps ``resource_package: db``, so it reads the real pinned bytes.
    """
    payload = yaml.safe_load(
        (REPO_ROOT / "packages" / package_path / "source_package.yaml").read_text(
            encoding="utf-8"
        )
    )
    edit(payload)
    package_dir = tmp_path / package_path.replace("/", "__")
    package_dir.mkdir(parents=True)
    (package_dir / "source_package.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    return package_dir


def _template_ira_labels(payload: dict) -> None:
    # soi-ira-roth-contributions-2022 at origin/main: every label follows --year.
    payload["artifact"]["vintage"] = "tax_year_{year}"
    for record_set in payload["record_sets"]:
        record_set["period"] = "{year}"
        for key in ("record_set_id", "source_record_id_prefix"):
            record_set[key] = record_set[key].replace("ty2022", "ty{year}")


def _fix_bea_regional_column(payload: dict) -> None:
    # BEA regional at origin/main: the 2024 column under a {year} period, which
    # relabelled CY2024 values as CY2023 in a --year 2023 build.
    for record_set in payload["record_sets"]:
        for measure in record_set["measures"]:
            measure.pop("column_by_year")
            measure.pop("expected_column_header_row", None)
            measure.pop("expected_column_header_by_year", None)
            measure["column"] = "AI"


@pytest.mark.parametrize(
    ("package_path", "edit"),
    [
        ("irs_soi/ira_roth_contributions_2022", _template_ira_labels),
        ("bea/regional_personal_income_state", _fix_bea_regional_column),
    ],
    ids=["ira-roth-templated-labels", "bea-regional-fixed-column"],
)
def test_guard_flags_real_bytes_exactly_when_the_unguarded_build_restamps(
    tmp_path,
    package_path,
    edit,
):
    """Differential on real bytes: origin/main's YAML restamps; the guard agrees."""
    package = load_source_package(_as_origin_main_had_it(tmp_path, package_path, edit))
    artifact_year = package.artifact.artifact_year
    base = _unguarded_facts(package, artifact_year)
    assert base

    for year in (artifact_year - 1, artifact_year + 1):
        restamped = _restamped_facts(_unguarded_facts(package, year), base)
        issues = artifact_year_restamp_issues(package, year)
        # Without the guard every artifact-year fact comes back relabelled.
        assert len(restamped) == len(base), year
        assert {fact.period.value for fact in restamped} == {year}
        assert issues
        assert {issue.code for issue in issues} == {ARTIFACT_YEAR_RESTAMP_CODE}
        with pytest.raises(ArtifactYearRestampError):
            package.build_facts(year)
