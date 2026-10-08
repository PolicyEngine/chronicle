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

from chronicle.bundle import (
    UK_BUNDLE_SOURCE_PREFIXES,
    UK_BUNDLE_SOURCES,
    assert_uk_bundle_sources_match_aliases,
    build_bundle,
)
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    SourcePackageAliasDriftError,
    assert_alias_map_covers_packages,
    discover_source_package_dirs,
    find_alias_map_drift,
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
