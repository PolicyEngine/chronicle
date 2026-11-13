"""Every source folder names its publisher, and only government ones are added.

Chronicle admits only government-produced records (the 2026-10-21 amendment to
docs/adr-chronicle-facts-only.md). docs/source-publishers.yaml classifies the
publisher of each folder under packages/ and db/data/.

The guard has two limits. It reads folder entries, so a package from another
publisher inside a government folder passes; reviewers check each package's
publisher. And it trusts the status the author writes, so a non-government
folder labelled ``government`` passes; it catches only a folder labelled for
what it is.
"""

from __future__ import annotations

from pathlib import Path

from chronicle.yaml_io import safe_load


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "docs" / "source-publishers.yaml"

STATUSES = {"government", "edge_case", "non_government"}
EDGE_CASES = {"central_bank", "regulator", "public_body", "supranational"}
# Folders added before the rule took effect. Neither set may grow: a new
# non-government source is taken from the government publisher instead, and a
# new folder in an edge-case category waits for the ruling on edge cases.
PREDATING_NON_GOVERNMENT = {"isc", "ici", "kff", "tpa", "ucl"}
PREDATING_EDGE_CASE = {
    "eurostat",
    "federal_reserve",
    "gambling_commission",
    "jrc",
    "nbb",
    "nithc",
    "ofgem",
    "orr",
    "slc",
}


def _registry() -> dict:
    return safe_load(REGISTRY_PATH.read_text())


def _source_folders() -> set[str]:
    folders = {path.name for path in (ROOT / "packages").iterdir() if path.is_dir()} | {
        path.name for path in (ROOT / "db" / "data").iterdir() if path.is_dir()
    }
    return {name for name in folders if not name.startswith(("_", "."))}


def _folders_with_status(status: str) -> set[str]:
    return {
        folder
        for folder, entry in _registry()["folders"].items()
        if entry["status"] == status
    }


def test_registry_names_exactly_the_source_folders():
    registered = set(_registry()["folders"])
    folders = _source_folders()

    assert sorted(folders - registered) == [], (
        "source folders without an entry in docs/source-publishers.yaml; "
        "add one naming the publisher and its status"
    )
    assert sorted(registered - folders) == [], (
        "docs/source-publishers.yaml entries with no packages/ or db/data/ folder"
    )


def test_every_folder_has_a_publisher_and_a_known_status():
    registry = _registry()
    assert registry["schema_version"] == "chronicle.source_publishers.v1"

    for folder, entry in registry["folders"].items():
        assert entry["publisher"].strip(), folder
        assert entry["status"] in STATUSES, folder
        if entry["status"] == "edge_case":
            assert entry["edge_case"] in EDGE_CASES, folder
        else:
            assert "edge_case" not in entry, folder


def test_no_new_non_government_source_folders():
    non_government = _folders_with_status("non_government")

    assert non_government <= PREDATING_NON_GOVERNMENT, (
        "Chronicle admits only government-produced records; "
        f"new non-government folders: {sorted(non_government - PREDATING_NON_GOVERNMENT)}"
    )


def test_no_new_edge_case_source_folders():
    edge_cases = _folders_with_status("edge_case")

    assert edge_cases <= PREDATING_EDGE_CASE, (
        "a new folder in an edge-case category waits for the ruling on edge "
        "cases in docs/adr-chronicle-facts-only.md; "
        f"new edge-case folders: {sorted(edge_cases - PREDATING_EDGE_CASE)}"
    )
