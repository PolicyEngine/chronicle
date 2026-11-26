"""UCL's house price per square metre deposit, registered raw-only (chronicle#408, item 6).

UK Data Service ReShare 856542 publishes two stored zips, of 3.2 and 4.4 GB, under CC BY
4.0. Both carry Royal Mail address data licensed for non-commercial use. They are pinned and
held in R2 only, uploaded through R2's S3 API because Wrangler takes at most 300 MiB
(chronicle#409), and no build parses them.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

import yaml

from chronicle.artifacts import (
    WRANGLER_PUT_LIMIT_BYTES,
    build_r2_key,
    inventory_source_artifacts,
    publish_source_artifacts,
)
from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.source_package import SOURCE_PACKAGE_ALIASES

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = "ucl/house_price_per_square_metre_856542"
PACKAGE_DIR = REPOSITORY_ROOT / "db" / "data" / DIRECTORY
PACKAGE_ID = "ucl-house-price-per-square-metre-856542"
# file key -> filename, sha256, bytes, and ReShare's ETag, which is the file's MD5.
BUNDLES = {
    "bundle_1": (
        "856542_bundle_1.zip",
        "e397cdac214b918a39f3ccf5266adaf9e4c3d8fb4f71e0bdc1b9c9474734b296",
        3_214_161_126,
        "239aebb08e10939b7cba4c5b2d5f89c9",
    ),
    "bundle_2": (
        "856542_bundle_2.zip",
        "61cbf6a72e35f7569d9121d80eaf89e757fec3bd4c21f1175e37fff44e02da97",
        4_426_805_029,
        "5fa5f769f3061aef86c455a4ed23c97e",
    ),
}


def _manifest() -> dict:
    return yaml.safe_load((PACKAGE_DIR / "manifest.yaml").read_text(encoding="utf-8"))


def test_both_bundles_are_pinned_raw_only_in_r2():
    manifest = _manifest()
    assert manifest["source_id"] == "ucl"
    assert manifest["package_id"] == PACKAGE_ID
    assert manifest["registration_kind"] == "raw_only"
    assert manifest["license"] == (
        "Creative Commons Attribution 4.0 International (CC BY 4.0)"
    )
    assert manifest["license_verified_at"] == "2026-11-06"
    assert "non-commercial" in manifest["license_evidence"]
    assert "10.5255/UKDA-SN-856542" in manifest["attribution"]
    assert list(manifest["files"]) == list(BUNDLES)
    for file_key, (filename, sha256, size_bytes, md5) in BUNDLES.items():
        entry = manifest["files"][file_key]
        number = file_key.removeprefix("bundle_")
        assert entry["filename"] == filename
        assert entry["source_url"] == (
            f"https://reshare.ukdataservice.ac.uk/856542/{number}/{filename}"
        )
        assert entry["sha256"] == sha256
        assert entry["size_bytes"] == size_bytes
        assert md5 in manifest["provenance_notes"]
        # Too large for Wrangler, so publish-raw sends it through the S3 API.
        assert size_bytes > WRANGLER_PUT_LIMIT_BYTES

        key = build_r2_key(
            source_id="ucl",
            package_id=PACKAGE_ID,
            year=file_key,
            sha256=sha256,
            filename=filename,
            package_path=PACKAGE_DIR / "manifest.yaml",
        )
        assert key == f"raw/uk/ucl/{PACKAGE_ID}/{file_key}/{sha256}/{filename}"
        assert entry["storage"] == {
            "local": False,
            "r2": {
                "provider": "r2",
                "bucket": "ledger-raw",
                "key": key,
                "uri": f"r2://ledger-raw/{key}",
            },
        }
        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", str(PACKAGE_DIR / filename)],
            cwd=REPOSITORY_ROOT,
            check=False,
        )
        assert ignored.returncode == 0

    assert PACKAGE_ID not in SOURCE_PACKAGE_ALIASES
    assert PACKAGE_ID not in UK_BUNDLE_SOURCES
    assert not (
        REPOSITORY_ROOT / "packages" / DIRECTORY / "source_package.yaml"
    ).exists()


def test_a_checkout_without_the_bundles_stays_valid(tmp_path):
    target = tmp_path / "db" / "data" / DIRECTORY
    target.mkdir(parents=True)
    (target / "manifest.yaml").write_bytes((PACKAGE_DIR / "manifest.yaml").read_bytes())

    inventory = inventory_source_artifacts(tmp_path / "db" / "data")
    published = publish_source_artifacts(
        tmp_path / "db" / "data", wrangler_command="false"
    )

    assert inventory.valid
    assert inventory.counts["missing_count"] == 0
    assert inventory.counts["r2_only_count"] == 2
    assert published.valid
    assert published.counts["skipped_count"] == 2
    assert published.counts["uploaded_count"] == 0
