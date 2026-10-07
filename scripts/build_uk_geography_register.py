"""Build Chronicle's canonical UK geography-name register from ONS lookups.

Chronicle keeps each publisher's own text for a geography (chronicle#266), and
publishers disagree: HMRC appends " UA" to every English unitary, DWP writes
Welsh authorities bilingually, MHCLG drops ", City of", and two ONS packages
spell one region two ways. A consumer that selects facts from two such packages
for one area sees two names and refuses them (chronicle#281).

The register answers with one name per identifier, and it is a publisher's name
rather than PolicyEngine's: every entry is read from an ONS lookup artifact
Chronicle already pins, keyed by the identifier that artifact states. Rerun this
script after re-pinning any of those artifacts and commit the result.

    uv run python scripts/build_uk_geography_register.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from chronicle.sources.cells import SourceArtifactMetadata, source_cells_from_xlsx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "chronicle" / "geography" / "uk_canonical_names.json"

# (package directory, code column, name column, geography level). One row per
# output area repeats a parent's name, so every row of an identifier must agree.
SOURCES = (
    ("ons/lad_dec2024_itl_jan2025_lookup", "LAD24CD", "LAD24NM", "local_authority"),
    (
        "ons/oa21_parncp_lad_rgn_ctry_dec2024_lookup",
        "RGN24CD",
        "RGN24NM",
        "region",
    ),
    (
        "ons/oa21_parncp_lad_rgn_ctry_dec2024_lookup",
        "CTRY24CD",
        "CTRY24NM",
        "country",
    ),
    ("ons/oa21_pcon_jul2024_lookup", "PCON25CD", "PCON25NM", "constituency"),
)

# The country-level identifiers are not in the output-area lookups. ONS states
# them in the mid-year estimates' MYE1 sheet, codes on one row and names on the
# row above; the names carry trailing spaces and a line break from the layout,
# which is presentation and is normalized away.
COUNTRY_SOURCE = ("ons/mye_2023_uk_countries", "MYE1", 8, 7, "country")


def _artifact(package: str) -> tuple[Path, dict]:
    directory = ROOT / "db" / "data" / package
    manifest = yaml.safe_load((directory / "manifest.yaml").read_text())
    entry = next(iter(manifest["files"].values()))
    return directory / entry["filename"], {
        "package_id": manifest["package_id"],
        "filename": entry["filename"],
        "sha256": entry["sha256"],
    }


def _country_names(package: str, sheet: str, code_row: int, name_row: int):
    """Return the ONS mid-year-estimates country code-to-name row pair."""
    path, meta = _artifact(package)
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != meta["sha256"]:
        raise SystemExit(f"checksum drift on {path}")
    artifact = SourceArtifactMetadata(
        source_name="ons",
        source_table=sheet,
        source_file=path.name,
        url=None,
        vintage=meta["package_id"],
        sha256=digest,
        size_bytes=len(content),
        extracted_at="register",
        extraction_method="register",
    )
    cells = {
        (cell.row_number, cell.column_number): cell.raw_value
        for cell in source_cells_from_xlsx(content, artifact, sheets=(sheet,))
        if cell.raw_value is not None
    }
    found = {}
    for (row_number, column_number), value in cells.items():
        if row_number != code_row or not isinstance(value, str):
            continue
        name = cells.get((name_row, column_number))
        if not isinstance(name, str):
            continue
        found[value.strip()] = re.sub(r"\s+", " ", name).strip()
    return found, meta


def main() -> int:
    names: dict[str, str] = {}
    levels: dict[str, str] = {}
    conflicts: dict[str, set[str]] = defaultdict(set)
    provenance: list[dict] = []
    seen: set[str] = set()

    for package, code_column, name_column, level in SOURCES:
        path, meta = _artifact(package)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != meta["sha256"]:
            print(f"checksum drift on {path}", file=sys.stderr)
            return 1
        found = 0
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                code = (row.get(code_column) or "").strip()
                name = (row.get(name_column) or "").strip()
                if not code or not name:
                    continue
                if code in names and names[code] != name:
                    conflicts[code].update({names[code], name})
                    continue
                if code not in names:
                    found += 1
                names[code] = name
                levels[code] = level
        key = (meta["package_id"], code_column)
        if key not in seen:
            seen.add(key)
            provenance.append(
                {
                    **meta,
                    "code_column": code_column,
                    "name_column": name_column,
                    "level": level,
                    "identifier_count": found,
                }
            )

    package, sheet, code_row, name_row, level = COUNTRY_SOURCE
    country_names, meta = _country_names(package, sheet, code_row, name_row)
    added = 0
    for code, name in sorted(country_names.items()):
        if code in names and names[code] != name:
            conflicts[code].update({names[code], name})
            continue
        added += code not in names
        names[code] = name
        levels[code] = level
    provenance.append(
        {
            **meta,
            "code_column": f"{sheet}!row {code_row}",
            "name_column": f"{sheet}!row {name_row}",
            "level": level,
            "identifier_count": added,
        }
    )

    if conflicts:
        for code, spellings in sorted(conflicts.items()):
            print(f"{code}: {sorted(spellings)}", file=sys.stderr)
        print("the lookups disagree; resolve before writing", file=sys.stderr)
        return 1

    payload = {
        "description": (
            "One canonical name per UK geography identifier, read from the ONS "
            "lookup artifacts Chronicle pins. Generated by "
            "scripts/build_uk_geography_register.py; do not edit by hand."
        ),
        "sources": provenance,
        "names": {code: names[code] for code in sorted(names)},
        "levels": {code: levels[code] for code in sorted(levels)},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(names)} identifiers to {OUT.relative_to(ROOT)}")
    for entry in provenance:
        print(
            f"  {entry['package_id']} {entry['code_column']}: "
            f"{entry['identifier_count']} new"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
