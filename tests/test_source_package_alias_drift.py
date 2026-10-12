"""Tests for source-package alias/directory drift detection (PolicyEngine/chronicle#78).

``chronicle build-bundle`` used to iterate a hand-maintained alias map, so a
``packages/*`` directory that was renamed, consolidated, or added without a
matching alias entry was silently dropped from the merged
``consumer_facts.jsonl`` instead of failing. These tests pin the guard that
makes such drift loud.
"""

from __future__ import annotations

import pytest
from pathlib import Path

import chronicle.bundle
from chronicle.bundle import (
    NZ_BUNDLE_SOURCE_PREFIXES,
    NZ_BUNDLE_SOURCES,
    UK_BUNDLE_SOURCE_PREFIXES,
    UK_BUNDLE_SOURCES,
    assert_nz_bundle_sources_match_aliases,
    assert_uk_bundle_sources_match_aliases,
    build_bundle,
    nz_bundle_sources_from_aliases,
)
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    SourcePackageAliasDriftError,
    _declarations_depend_on_year,
    assert_alias_map_covers_packages,
    discover_source_package_dirs,
    find_alias_map_drift,
    load_source_package,
    source_package_root,
)

# Stats NZ regional council codes (there is no 10 or 11) and 99, Area Outside
# Region: one child package per code under each Census 2023 place-summary root.
NZ_CENSUS_REGION_CODES = (
    "01",
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "08",
    "09",
    "12",
    "13",
    "14",
    "15",
    "16",
    "17",
    "18",
    "99",
)
NZ_CENSUS_ROOTS = (
    "stats-nz-census-2023-family-type",
    "stats-nz-census-2023-households-by-region",
    "stats-nz-census-2023-weekly-rent",
)
NZ_CENSUS_MEMBERS = tuple(
    alias
    for root in NZ_CENSUS_ROOTS
    for alias in (root, *(f"{root}-rc-{code}" for code in NZ_CENSUS_REGION_CODES))
)


def _write_package(root, rel_path):
    """Create a minimal package directory under ``root`` at ``rel_path``."""
    package_dir = root / rel_path
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "source_package.yaml").write_text(
        "schema_version: ledger.source_package.v1\n"
        f"package_id: {rel_path.replace('/', '-')}\n",
        encoding="utf-8",
    )
    return package_dir


@pytest.mark.parametrize(
    "alias,raw_directory",
    [
        ("nrs-pcon24-population-by-age-2024", "nrs/pcon24_population_by_age_2024"),
        (
            "dwp-uc-households-by-constituency-may-2025",
            "dwp/uc_households_by_constituency_may_2025",
        ),
        (
            "dwp-uc-households-by-local-authority-may-2025",
            "dwp/uc_households_by_local_authority_may_2025",
        ),
        (
            "dwp-uc-households-by-constituency-children-may-2025",
            "dwp/uc_households_by_constituency_children_may_2025",
        ),
    ],
)
def test_superseded_editions_are_archived_without_active_fact_packages(
    alias, raw_directory
):
    root = Path(__file__).resolve().parents[1]
    assert alias not in SOURCE_PACKAGE_ALIASES
    assert alias not in UK_BUNDLE_SOURCES
    assert not (root / "packages" / raw_directory / "source_package.yaml").exists()
    assert (root / "db/data" / raw_directory / "manifest.yaml").is_file()


def test_repo_alias_map_matches_packages_on_disk():
    """The committed alias map must cover every committed package directory.

    This is the regression guard: it fails the moment an alias entry points at
    a missing directory, or a ``packages/*`` directory has no alias entry.
    """
    missing_dirs, unmapped_dirs = find_alias_map_drift()
    assert missing_dirs == []
    assert unmapped_dirs == []
    # And the strict assertion form does not raise for the committed tree.
    assert_alias_map_covers_packages()


def test_uk_bundle_sources_match_uk_prefixed_aliases():
    """The UK bundle suite must include every alias under a UK source prefix."""
    expected = tuple(
        sorted(
            alias
            for alias, path in SOURCE_PACKAGE_ALIASES.items()
            if path.parts and path.parts[0] in UK_BUNDLE_SOURCE_PREFIXES
        )
    )

    assert UK_BUNDLE_SOURCES == expected
    assert_uk_bundle_sources_match_aliases()


def test_uk_bundle_drift_message_is_unchanged(monkeypatch):
    """Factoring the suites through one check keeps the UK error text."""
    monkeypatch.setattr(
        chronicle.bundle,
        "UK_BUNDLE_SOURCES",
        (*UK_BUNDLE_SOURCES[1:], "zz-planted-uk-package"),
    )

    with pytest.raises(ValueError) as excinfo:
        assert_uk_bundle_sources_match_aliases()

    assert str(excinfo.value) == (
        "UK_BUNDLE_SOURCES drifted from UK-prefixed SOURCE_PACKAGE_ALIASES: "
        "missing=['desnz-energy-trends-domestic-electricity-2026'], "
        "extra=['zz-planted-uk-package']"
    )


def test_nz_bundle_sources_match_nz_prefixed_aliases():
    """The NZ bundle suite must include every alias under an NZ source prefix."""
    expected = tuple(
        sorted(
            alias
            for alias, path in SOURCE_PACKAGE_ALIASES.items()
            if path.parts and path.parts[0] in NZ_BUNDLE_SOURCE_PREFIXES
        )
    )

    assert NZ_BUNDLE_SOURCE_PREFIXES == ("ird", "mbie", "msd", "stats_nz", "treasury")
    assert len(NZ_BUNDLE_SOURCES) == 66
    assert NZ_BUNDLE_SOURCES == expected == nz_bundle_sources_from_aliases()
    assert_nz_bundle_sources_match_aliases()


def test_nz_bundle_sources_include_every_census_place_summary_package():
    """All 54 Census 2023 place-summary packages, roots and rc_XX children."""
    assert len(NZ_CENSUS_MEMBERS) == len(set(NZ_CENSUS_MEMBERS)) == 54
    assert set(NZ_CENSUS_MEMBERS) <= set(NZ_BUNDLE_SOURCES)
    census_in_suite = {
        alias for alias in NZ_BUNDLE_SOURCES if alias.startswith("stats-nz-census-")
    }
    assert census_in_suite == set(NZ_CENSUS_MEMBERS)
    for alias in NZ_CENSUS_MEMBERS:
        root = next(root for root in NZ_CENSUS_ROOTS if alias.startswith(root))
        directory = Path("stats_nz") / root.removeprefix("stats-nz-").replace("-", "_")
        suffix = alias.removeprefix(root)
        expected = directory / f"rc_{suffix[-2:]}" if suffix else directory
        assert SOURCE_PACKAGE_ALIASES[alias] == expected


def test_nz_bundle_sources_cover_every_nz_package_on_disk():
    """Every NZ source_package.yaml, at any depth, is a suite member."""
    root = source_package_root()
    on_disk = {
        manifest.parent.relative_to(root)
        for prefix in NZ_BUNDLE_SOURCE_PREFIXES
        for manifest in (root / prefix).rglob("source_package.yaml")
    }

    assert len(on_disk) == 66
    assert on_disk == {SOURCE_PACKAGE_ALIASES[alias] for alias in NZ_BUNDLE_SOURCES}


def test_nz_and_uk_bundle_suites_are_disjoint():
    assert not set(NZ_BUNDLE_SOURCE_PREFIXES) & set(UK_BUNDLE_SOURCE_PREFIXES)
    assert not set(NZ_BUNDLE_SOURCES) & set(UK_BUNDLE_SOURCES)
    assert all(
        SOURCE_PACKAGE_ALIASES[alias].parts[0] in NZ_BUNDLE_SOURCE_PREFIXES
        for alias in NZ_BUNDLE_SOURCES
    )


@pytest.mark.parametrize(
    "roster,missing,extra",
    [
        pytest.param(
            tuple(
                alias
                for alias in NZ_BUNDLE_SOURCES
                if alias != "stats-nz-census-2023-households-by-region-rc-07"
            ),
            ["stats-nz-census-2023-households-by-region-rc-07"],
            [],
            id="drop-census-rc-member",
        ),
        pytest.param(
            tuple(
                alias
                for alias in NZ_BUNDLE_SOURCES
                if alias != "treasury-an24-01-fiscal-totals"
            ),
            ["treasury-an24-01-fiscal-totals"],
            [],
            id="drop-treasury-package",
        ),
        pytest.param(
            tuple(sorted((*NZ_BUNDLE_SOURCES, "ons-mye-2025-uk"))),
            [],
            ["ons-mye-2025-uk"],
            id="add-uk-package",
        ),
    ],
)
def test_nz_bundle_drift_guard_rejects_a_changed_roster(
    monkeypatch, roster, missing, extra
):
    monkeypatch.setattr(chronicle.bundle, "NZ_BUNDLE_SOURCES", roster)

    with pytest.raises(ValueError) as excinfo:
        assert_nz_bundle_sources_match_aliases()

    assert str(excinfo.value) == (
        "NZ_BUNDLE_SOURCES drifted from NZ-prefixed SOURCE_PACKAGE_ALIASES: "
        f"missing={missing}, extra={extra}"
    )


def test_nz_bundle_drift_guard_rejects_a_new_nz_alias(monkeypatch):
    monkeypatch.setitem(
        SOURCE_PACKAGE_ALIASES, "treasury-planted-package", Path("treasury/planted")
    )

    with pytest.raises(ValueError, match=r"missing=\['treasury-planted-package'\]"):
        assert_nz_bundle_sources_match_aliases()


def test_nz_bundle_drift_guard_rejects_a_dropped_nz_alias(monkeypatch):
    monkeypatch.delitem(
        SOURCE_PACKAGE_ALIASES, "stats-nz-census-2023-family-type-rc-99"
    )

    with pytest.raises(
        ValueError, match=r"extra=\['stats-nz-census-2023-family-type-rc-99'\]"
    ):
        assert_nz_bundle_sources_match_aliases()


def test_nz_bundle_members_use_year_independent_declarations():
    """``--year`` is inert for the NZ suite.

    A package that pins ``artifact_year`` reads that year's manifest file at
    every build year, and one whose declarations render no ``{year}`` and use
    no ``*_by_year`` mapping selects and labels the same cells at every year.
    """
    for alias in NZ_BUNDLE_SOURCES:
        package = load_source_package(alias)
        assert package.artifact.artifact_year is not None, alias
        assert not _declarations_depend_on_year(package), alias


def test_discover_source_package_dirs_finds_real_packages():
    """Discovery must return real package directories (prove it can find some)."""
    discovered = discover_source_package_dirs()
    assert discovered, "expected to discover committed source packages"
    # A known committed package must be discovered.
    assert "usda_snap/fy69_to_current" in {str(path) for path in discovered}


def test_discover_source_package_dirs_scans_given_root(tmp_path):
    """Discovery scans the two-level ``<source>/<package>`` layout under a root."""
    _write_package(tmp_path, "alpha/one")
    _write_package(tmp_path, "beta/two")
    # A stray top-level file must not be mistaken for a package.
    (tmp_path / "not_a_package.yaml").write_text("x: 1\n", encoding="utf-8")

    discovered = {str(path) for path in discover_source_package_dirs(root=tmp_path)}
    assert discovered == {"alpha/one", "beta/two"}


def test_discover_source_package_dirs_finds_nested_members(tmp_path):
    """A package family's nested members are discovered alongside its root."""
    _write_package(tmp_path, "alpha/family")
    _write_package(tmp_path, "alpha/family/rc_01")
    _write_package(tmp_path, "alpha/family/rc_02")

    discovered = {str(path) for path in discover_source_package_dirs(root=tmp_path)}
    assert discovered == {"alpha/family", "alpha/family/rc_01", "alpha/family/rc_02"}


def test_find_alias_map_drift_flags_an_unmapped_nested_member(tmp_path):
    """Dropping a nested member's alias is reported, not silently skipped."""
    _write_package(tmp_path, "alpha/family")
    _write_package(tmp_path, "alpha/family/rc_01")
    aliases = {"alpha-family": type(tmp_path)("alpha/family")}

    missing_dirs, unmapped_dirs = find_alias_map_drift(root=tmp_path, aliases=aliases)

    assert missing_dirs == []
    assert [str(path) for path in unmapped_dirs] == ["alpha/family/rc_01"]


def test_discover_source_package_dirs_follows_symlinked_packages(tmp_path):
    """A symlinked package or family is found under its link path, nested members included."""
    root = tmp_path / "packages"
    outside = tmp_path / "outside"
    _write_package(outside, "linked_package")
    _write_package(outside, "linked_family/rc_01")
    (root / "alpha").mkdir(parents=True)
    (root / "alpha" / "linked").symlink_to(
        outside / "linked_package", target_is_directory=True
    )
    (root / "beta").symlink_to(outside / "linked_family", target_is_directory=True)

    discovered = {str(path) for path in discover_source_package_dirs(root=root)}
    assert discovered == {"alpha/linked", "beta/rc_01"}

    missing_dirs, unmapped_dirs = find_alias_map_drift(root=root, aliases={})
    assert missing_dirs == []
    assert [str(path) for path in unmapped_dirs] == ["alpha/linked", "beta/rc_01"]


def test_discover_source_package_dirs_reports_each_link_to_one_package(tmp_path):
    """A directory and a link to it are separate discoveries, as under the old glob."""
    _write_package(tmp_path, "alpha/real")
    (tmp_path / "beta").mkdir()
    (tmp_path / "beta" / "alias").symlink_to(
        tmp_path / "alpha" / "real", target_is_directory=True
    )

    discovered = {str(path) for path in discover_source_package_dirs(root=tmp_path)}
    assert discovered == {"alpha/real", "beta/alias"}


def test_discover_source_package_dirs_stops_at_a_symlink_cycle(tmp_path):
    """A link back into its own ancestry ends the walk instead of recursing forever."""
    _write_package(tmp_path, "alpha/family")
    (tmp_path / "alpha" / "family" / "loop").symlink_to(
        tmp_path / "alpha", target_is_directory=True
    )

    discovered = {str(path) for path in discover_source_package_dirs(root=tmp_path)}
    assert discovered == {"alpha/family"}


def test_find_alias_map_drift_flags_unmapped_directory(tmp_path):
    """An on-disk package with no alias entry is reported as unmapped."""
    _write_package(tmp_path, "alpha/mapped")
    _write_package(tmp_path, "beta/unmapped")
    aliases = {"alpha-mapped-alias": type(tmp_path)("alpha/mapped")}

    missing_dirs, unmapped_dirs = find_alias_map_drift(root=tmp_path, aliases=aliases)

    assert missing_dirs == []
    assert [str(path) for path in unmapped_dirs] == ["beta/unmapped"]


def test_find_alias_map_drift_flags_missing_directory(tmp_path):
    """An alias entry pointing at a missing directory is reported as missing."""
    _write_package(tmp_path, "alpha/mapped")
    aliases = {
        "alpha-mapped-alias": type(tmp_path)("alpha/mapped"),
        "gone-alias": type(tmp_path)("gamma/gone"),
    }

    missing_dirs, unmapped_dirs = find_alias_map_drift(root=tmp_path, aliases=aliases)

    assert [str(path) for path in missing_dirs] == ["gamma/gone"]
    assert unmapped_dirs == []


def test_assert_alias_map_covers_packages_raises_on_unmapped(tmp_path):
    """The strict assertion fails loudly and names the offending directory."""
    _write_package(tmp_path, "alpha/mapped")
    _write_package(tmp_path, "beta/unmapped")
    aliases = {"alpha-mapped-alias": type(tmp_path)("alpha/mapped")}

    with pytest.raises(SourcePackageAliasDriftError) as excinfo:
        assert_alias_map_covers_packages(root=tmp_path, aliases=aliases)

    assert "beta/unmapped" in str(excinfo.value)


def test_build_bundle_fails_loudly_on_unmapped_package(tmp_path, monkeypatch):
    """A default build-bundle must error, not silently skip, on alias drift.

    Planting an on-disk package directory with no alias entry makes the default
    (non-explicit) bundle build fail loudly rather than produce a
    silently-incomplete consumer_facts.jsonl.
    """
    import chronicle.source_package as source_package

    packages_root = source_package.SOURCE_PACKAGE_ROOT
    planted = _write_package(packages_root, "zz_planted_source/zz_planted_package")
    try:
        with pytest.raises(SourcePackageAliasDriftError) as excinfo:
            build_bundle(tmp_path / "bundle", year=2023)
        assert "zz_planted_source/zz_planted_package" in str(excinfo.value)
    finally:
        (planted / "source_package.yaml").unlink()
        planted.rmdir()
        planted.parent.rmdir()
