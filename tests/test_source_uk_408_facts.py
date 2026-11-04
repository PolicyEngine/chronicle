"""Source packages for PolicyEngine/chronicle#408, the UK land value inputs.

MHCLG's land value estimates for policy appraisal 2023 (item 1), and the generator that
writes the issue's packages.
"""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import runpy

from openpyxl import load_workbook
import pytest
import yaml

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import (
    build_semantic_fact_key,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "db/data"
# package id -> (artifact year, record sets, facts)
PACKAGES = {
    "mhclg-land-value-estimates-2023": (2023, 25, 10101),
}
LVE = "mhclg-land-value-estimates-2023"


def _facts(package_id: str) -> dict[str, object]:
    year = PACKAGES[package_id][0]
    package = load_source_package(package_id)
    return {fact.source_record_id: fact for fact in package.build_facts(year)}


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_packages_validate_register_and_carry_no_anchors(package_id):
    year, record_sets, count = PACKAGES[package_id]
    package_dir = ROOT / "packages" / SOURCE_PACKAGE_ALIASES[package_id]
    report = validate_source_package(package_dir, year=year)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["record_set_count"] == record_sets
    assert package_id in UK_BUNDLE_SOURCES
    text = (package_dir / "source_package.yaml").read_text(encoding="utf-8")
    assert not any(
        isinstance(token, (yaml.AnchorToken, yaml.AliasToken))
        for token in yaml.scan(text)
    )
    built = list(_facts(package_id).values())
    assert len(built) == count
    assert validate_facts(built).valid
    assert validate_consumer_fact_contract(built).valid
    assert max(Counter(build_semantic_fact_key(fact) for fact in built).values()) == 1


def test_generator_reproduces_the_committed_packages():
    generator = runpy.run_path(str(ROOT / "scripts/build_uk_408_packages.py"))
    for directory, build in generator["BUILDERS"].items():
        path = ROOT / "packages" / directory / "source_package.yaml"
        assert build() == path.read_text(encoding="utf-8"), directory


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_manifests_pin_bytes_licence_and_r2(package_id):
    data_dir = DATA / SOURCE_PACKAGE_ALIASES[package_id]
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["package_id"] == package_id
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-04"
    (entry,) = manifest["files"].values()
    content = (data_dir / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    assert entry["storage"]["r2"]["uri"].endswith(
        f"/{package_id}/{PACKAGES[package_id][0]}/{entry['sha256']}/{entry['filename']}"
    )


# ----------------------------------------------- MHCLG land value estimates 2023

LVE_FILE = (
    DATA
    / "mhclg/land_value_estimates_2023"
    / "Land_value_estimates_for_policy_appraisal_2023.xlsx"
)
LVE_COLUMNS = {"low": "HIJKL", "medium": "MNOPQ", "high": "RSTUV"}
LVE_PERCENTILES = ("p25", "p40", "p50", "p60", "p75")


def _lve_workbook():
    return load_workbook(LVE_FILE, data_only=True)


def _lve_authorities(sheet) -> dict[str, int]:
    """Council code -> row, for the rows that print an E06-E09 code in column C."""
    found = {}
    for row in range(1, sheet.max_row + 1):
        code = sheet[f"C{row}"].value
        if isinstance(code, str) and code[:3] in {"E06", "E07", "E08", "E09"}:
            found[code] = row
    return found


def _printed(value) -> bool:
    return not (isinstance(value, str) and value.strip() == "-")


def test_land_values_are_the_residential_cells():
    workbook = _lve_workbook()
    facts = list(_facts(LVE).values())
    for sheet_name, concept in (
        ("Residential", "mhclg.residential_land_value_before_floor"),
        ("Residential (adj for floor)", "mhclg.residential_land_value_floor_adjusted"),
    ):
        sheet = workbook[sheet_name]
        rows = _lve_authorities(sheet)
        assert len(rows) == 295
        built = {
            (
                fact.geography.id,
                fact.filters["site_density_scenario"],
                fact.filters["new_build_price_percentile"],
            ): fact.value
            for fact in facts
            if fact.measure.concept == concept
        }
        expected = {}
        for code, row in rows.items():
            for density, columns in LVE_COLUMNS.items():
                for column, percentile in zip(columns, LVE_PERCENTILES):
                    value = sheet[f"{column}{row}"].value
                    if _printed(value):
                        expected[(code, density, percentile)] = value
        assert built == expected
    unreported = [
        value
        for row in workbook["Residential"].iter_rows(min_row=6, max_row=300)
        for value in (cell.value for cell in row)
        if not _printed(value)
    ]
    assert len(unreported) == 35


def test_site_densities_are_printed_once_and_both_sheets_agree():
    workbook = _lve_workbook()
    before, floor = workbook["Residential"], workbook["Residential (adj for floor)"]
    densities = {
        (fact.geography.id, fact.filters["site_density_scenario"]): fact.value
        for fact in _facts(LVE).values()
        if fact.measure.concept == "mhclg.residential_site_density"
    }
    assert len(densities) == 295 * 3
    for code, row in _lve_authorities(before).items():
        for density, column in (("low", "E"), ("medium", "F"), ("high", "G")):
            assert before[f"{column}{row}"].value == floor[f"{column}{row}"].value
            assert densities[(code, density)] == before[f"{column}{row}"].value


def test_land_values_rise_with_the_house_price_percentile():
    """The issue's parity check. No printed value falls as the percentile rises; on
    the floor-adjusted sheet Cumberland's median and 60th percentile values are equal
    under all three densities, the only values that do not rise."""
    workbook = _lve_workbook()
    flat = []
    for sheet_name in ("Residential", "Residential (adj for floor)"):
        sheet = workbook[sheet_name]
        for code, row in _lve_authorities(sheet).items():
            for density, columns in LVE_COLUMNS.items():
                values = [sheet[f"{column}{row}"].value for column in columns]
                printed = [value for value in values if _printed(value)]
                assert all(b >= a for a, b in zip(printed, printed[1:])), (
                    code,
                    density,
                )
                if any(b == a for a, b in zip(printed, printed[1:])):
                    flat.append((sheet_name, sheet[f"D{row}"].value, density))
    assert flat == [
        ("Residential (adj for floor)", "Cumberland", "low"),
        ("Residential (adj for floor)", "Cumberland", "medium"),
        ("Residential (adj for floor)", "Cumberland", "high"),
    ]


def test_floor_adjusted_values_are_never_below_the_estimates_before_the_floor():
    facts = _facts(LVE).values()
    before = {
        (
            fact.geography.id,
            fact.filters["site_density_scenario"],
            fact.filters["new_build_price_percentile"],
        ): fact.value
        for fact in facts
        if fact.measure.concept == "mhclg.residential_land_value_before_floor"
    }
    after = {
        (
            fact.geography.id,
            fact.filters["site_density_scenario"],
            fact.filters["new_build_price_percentile"],
        ): fact.value
        for fact in facts
        if fact.measure.concept == "mhclg.residential_land_value_floor_adjusted"
    }
    assert set(before) < set(after)
    assert all(after[key] >= value for key, value in before.items())


def test_barnsley_and_sheffield_keep_their_printed_codes():
    names = {
        fact.geography.id: fact.geography.name
        for fact in _facts(LVE).values()
        if fact.geography.level == "local_authority"
    }
    assert len(names) == 295
    assert names["E08000016"] == "Barnsley"
    assert names["E08000019"] == "Sheffield"
    assert not {"E08000038", "E08000039"} & set(names)
    assert {fact.period.value for fact in _facts(LVE).values()} == {"2023-10"}


def test_non_residential_sheets():
    workbook = _lve_workbook()
    facts = list(_facts(LVE).values())

    def values(concept, level=None):
        return {
            (fact.geography.id, tuple(sorted(fact.filters.items()))): fact.value
            for fact in facts
            if fact.measure.concept == concept
            and (level is None or fact.geography.level == level)
        }

    industrial = values("mhclg.industrial_land_value")
    assert len(industrial) == 119
    assert industrial[("K08000001", ())] == workbook["Industrial"]["E30"].value
    distribution = values("mhclg.distribution_land_value", "region")
    assert len(distribution) == 9
    agriculture = values("mhclg.agricultural_land_value", "region")
    assert len(agriculture) == 27
    assert {dict(key[1])["agricultural_land_grade"] for key in agriculture} == {
        "low",
        "medium",
        "high",
    }
    office = values("mhclg.office_land_value")
    retail = values("mhclg.retail_land_value")
    sheet_office, sheet_retail = workbook["Office"], workbook["Retail"]
    printed_office = sum(
        _printed(row[0].value)
        for row in sheet_office.iter_rows(min_row=6, min_col=6, max_col=6)
        if row[0].value is not None
    ) + sum(_printed(sheet_office[f"C{row}"].value) for row in range(132, 142))
    assert len(office) == printed_office == 48
    assert len(retail) == 89
    assert {
        dict(key[1]).get("office_accommodation_type") for key in office if dict(key[1])
    } == {"primary", "secondary"}
    assert {
        dict(key[1]).get("retail_location_type") for key in retail if dict(key[1])
    } == {"urban", "suburban"}
    car_park = values("mhclg.car_park_land_value")
    assert len(car_park) == 109
    assert ("postcode-district:LS1", ()) in car_park
    assert sheet_retail["B123"].value == "London Locations"

