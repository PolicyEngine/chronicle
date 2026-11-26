"""Fetch every R2-only artifact a source package reads into the source-artifact cache.

CI runs this before its tests, with LEDGER_SOURCE_ARTIFACT_FETCH=1, so a publisher
outage or a replaced download fails one short step by name instead of a test or a
bundle build part-way through. Artifacts already committed or cached are read, not
fetched, and every one is checked against its pinned sha256. Downloads retry on
transport errors and 5xx answers.

usage: fetch_r2_only_source_artifacts.py
"""

from __future__ import annotations

from pathlib import Path

from chronicle.source_package import r2_only_package_artifacts, read_registered_artifact

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    artifacts = r2_only_package_artifacts(ROOT / "db" / "data")
    for manifest_path, file_key in artifacts:
        content = read_registered_artifact(manifest_path, file_key)
        print(
            f"{manifest_path.parent.relative_to(ROOT)} [{file_key}]: "
            f"{len(content):,} bytes, sha256 verified"
        )
    print(f"{len(artifacts)} R2-only source artifacts available")


if __name__ == "__main__":
    main()
