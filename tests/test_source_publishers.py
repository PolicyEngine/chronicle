"""Every source folder names its publisher, and only government ones are added.

Chronicle holds government-produced records only (the 2026-10-21 amendment to
docs/adr-chronicle-facts-only.md). docs/source-publishers.yaml classifies the
publisher of each folder under packages/ and db/data/.
"""

from __future__ import annotations

from pathlib import Path

from chronicle.yaml_io import safe_load


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "docs" / "source-publishers.yaml"

STATUSES = {"government", "edge_case", "non_government"}
EDGE_CASES = {"central_bank", "regulator", "public_corporation", "intergovernmental"}
# Non-government folders that predate the rule and await a migration ruling.
# A new non-government source must not be added here: take the series from the
# government publisher instead.
PREDATING_NON_GOVERNMENT = {"isc", "ici", "kff"}


def _registry() -> dict:
    return safe_load(REGISTRY_PATH.read_text())


def _source_folders() -> set[str]:
    folders = {path.name for path in (ROOT / "packages").iterdir() if path.is_dir()} | {
        path.name for path in (ROOT / "db" / "data").iterdir() if path.is_dir()
    }
    return {name for name in folders if not name.startswith(("_", "."))}


def test_registry_names_exactly_the_source_folders():
    registered = set(_registry()["folders"])
    folders = _source_folders()

    assert sorted(folders - registered) == [], (
        "source folders without a publisher entry in docs/source-publishers.yaml"
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
    non_government = {
        folder
        for folder, entry in _registry()["folders"].items()
        if entry["status"] == "non_government"
    }

    assert non_government <= PREDATING_NON_GOVERNMENT, (
        "Chronicle holds government-produced records only; "
        f"new non-government folders: {sorted(non_government - PREDATING_NON_GOVERNMENT)}"
    )
