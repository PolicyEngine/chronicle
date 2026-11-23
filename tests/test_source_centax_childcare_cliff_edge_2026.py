"""CenTax's childcare cliff-edge workbook, registered raw-only (PolicyEngine/microcosm#1399).

Advani, Flew, Pepin-Hall and Summers (2026), *Removing the £100,000 childcare cliff-edge*,
publish their data for the charts on arunadvani.com. No licence is stated; Arun Advani
(CenTax) has said PolicyEngine may use the published data. So, like the GSGB tables, the
workbook is pinned by its manifest, held in R2 only and git-ignored, and no Chronicle build
parses it: microcosm's builder reads Figures 3.1, 3.3, 3.6 and 3.7 (and Table A.1 and
Figure 3.12 as diagnostics) after checking the bytes against this registration.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import subprocess

import openpyxl
import pytest
import yaml

from chronicle.artifacts import (
    R2_COUNTRY_PUBLISHERS,
    build_r2_key,
    inventory_source_artifacts,
    publish_source_artifacts,
)
from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.source_package import SOURCE_PACKAGE_ALIASES

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = "centax/childcare_cliff_edge_2026"
PACKAGE_DIR = REPOSITORY_ROOT / "db" / "data" / DIRECTORY
PACKAGE_ID = "centax-childcare-cliff-edge-2026"
FILENAME = "AdvaniFlewPepinhallSummers2026_ChildcareThreshold_data.xlsx"
SHA256 = "8c23855745154a601064e766552c64bc2e88de51e043b4df1397c580e969354b"
SIZE_BYTES = 194_075
#: The sheets PolicyEngine/microcosm#1399 reads: each one's header row (from column B)
#: and its bins (first and last label, step), labelled by their upper edge.
CONSUMED_FIGURES = {
    "Fig. 3.1": (
        ("Income Bin (ANI)", "Number of Taxpayer in Income Bin"),
        (500, 200_000, 500),
    ),
    "Fig. 3.3": (
        (
            "Income Bin (ANI)",
            "Number of Taxpayers in Income Bin (Employees)",
            "Number of Taxpayers in Income Bin (Non-Employees)",
        ),
        (1_000, 150_000, 1_000),
    ),
    "Fig. 3.6": (
        (
            "Income Bin (ANI)",
            "Number of Taxpayers in Income Bin (Males)",
            "Number of Taxpayers in Income Bin (Females)",
        ),
        (500, 150_000, 500),
    ),
    "Fig. 3.7": (
        (
            "Income Bin (ANI)",
            "Number of Taxpayers in Income Bin (London)",
            "Number of Taxpayers in Income Bin (North and Midlands)",
            "Number of Taxpayers in Income Bin (South excl. London)",
            "Number of Taxpayers in Income Bin (Scotland)",
        ),
        (1_000, 150_000, 1_000),
    ),
    "Fig. 3.12": (
        (
            "Income Bin (ANI)",
            "Share of Parents with Non-Working Partner (Men & Women)",
            "Share of Parents with Non-Working Partner (Men)",
            "Share of Parents with Non-Working Partner (Women)",
        ),
        (2_500, 150_000, 2_500),
    ),
}


def _manifest() -> dict:
    return yaml.safe_load((PACKAGE_DIR / "manifest.yaml").read_text(encoding="utf-8"))


def test_the_workbook_is_pinned_raw_only_in_r2():
    manifest = _manifest()
    assert manifest["source_id"] == "centax"
    assert manifest["package_id"] == PACKAGE_ID
    assert manifest["registration_kind"] == "raw_only"
    assert "centax" in R2_COUNTRY_PUBLISHERS["uk"]
    assert list(manifest["files"]) == [2026]
    entry = manifest["files"][2026]
    assert entry["filename"] == FILENAME
    assert entry["source_url"] == f"https://arunadvani.com/data/{FILENAME}"
    assert entry["sha256"] == SHA256
    assert entry["size_bytes"] == SIZE_BYTES
    assert entry["vintage"] == "centax_2026_09"

    key = build_r2_key(
        source_id="centax",
        package_id=PACKAGE_ID,
        year=2026,
        sha256=SHA256,
        filename=FILENAME,
        package_path=PACKAGE_DIR / "manifest.yaml",
    )
    assert key == f"raw/uk/centax/{PACKAGE_ID}/2026/{SHA256}/{FILENAME}"
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
        ["git", "check-ignore", "--quiet", str(PACKAGE_DIR / FILENAME)],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    assert ignored.returncode == 0

    assert PACKAGE_ID not in SOURCE_PACKAGE_ALIASES
    assert PACKAGE_ID not in UK_BUNDLE_SOURCES
    assert not (
        REPOSITORY_ROOT / "packages" / DIRECTORY / "source_package.yaml"
    ).exists()


def test_the_manifest_records_the_source_page_the_permission_and_no_licence():
    manifest = _manifest()
    assert manifest["source_page"] == (
        "https://arunadvani.com/policy.html#ChildcareCliffEdge"
    )
    assert manifest["license"] == "None stated"
    assert manifest["license_verified_at"] == "2026-11-23"
    evidence = manifest["license_evidence"]
    assert "Arun Advani (CenTax)" in evidence
    assert "23 November 2026" in evidence
    assert "git-ignored" in evidence
    for author in ("Advani, A.", "Flew, J.", "Pepin-Hall, J.", "Summers, A."):
        assert author in manifest["attribution"]
    assert "HMRC administrative datasets" in manifest["attribution"]
    assert "PolicyEngine/microcosm#1399" in manifest["provenance_notes"]


def test_a_checkout_without_the_workbook_stays_valid(tmp_path):
    target = tmp_path / "db" / "data" / DIRECTORY
    target.mkdir(parents=True)
    (target / "manifest.yaml").write_bytes((PACKAGE_DIR / "manifest.yaml").read_bytes())

    inventory = inventory_source_artifacts(tmp_path / "db" / "data")
    published = publish_source_artifacts(
        tmp_path / "db" / "data", wrangler_command="false"
    )

    assert inventory.valid
    assert inventory.counts["missing_count"] == 0
    assert inventory.counts["r2_only_count"] == 1
    assert published.valid
    assert published.counts["skipped_count"] == 1
    assert published.counts["uploaded_count"] == 0


def test_the_figures_microcosm_reads_keep_their_layout():
    """Checked against a local copy of the bytes; skipped in a checkout without one."""
    path = PACKAGE_DIR / FILENAME
    if not path.is_file():
        pytest.skip(f"{FILENAME} is held in R2 only; no local copy to check.")
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == SHA256
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    assert len(workbook.sheetnames) == 45
    for sheet, (header, (first, last, step)) in CONSUMED_FIGURES.items():
        rows = list(workbook[sheet].iter_rows(values_only=True))
        start = next(
            index
            for index, row in enumerate(rows)
            if tuple(row[1 : 1 + len(header)]) == header
        )
        labels = [row[1] for row in rows[start + 1 :] if row[1] is not None]
        assert labels == list(range(first, last + step, step)), sheet
    table = list(workbook["Tab. A.1"].iter_rows(values_only=True))
    assert table[3][1:5] == ("Sample", "Variable", "Whole Population", "£80k-£140k")
    assert table[4][1:3] == ("3- and 4-year-olds", "Number of Parents")
