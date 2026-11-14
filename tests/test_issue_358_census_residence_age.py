"""Regression tests for chronicle#358: census residence type by age, 90 and over split out.

- ONS Census 2021 (England and Wales): UR_HH and UR_CE by single year of age, by sex
  and for all persons, for countries and English regions, from the Census API.
- NISRA Census 2021: residence type by single year of age, by sex and for all persons,
  for Northern Ireland, its districts and its 2024 constituencies.
- NRS Scotland's Census 2022: UV101a at Scotland level, whose top band is 85 and over;
  NRS publishes nothing finer by residence type.

Values are the publishers' as fetched on 2026-10-15.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.core import validate_facts
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package
from chronicle.sources.cells import SourceArtifactMetadata
from chronicle.sources.rows import (
    ons_census_observation_labels,
    source_rows_from_ons_census_observations_json,
)

DATA = Path(__file__).resolve().parents[1] / "db" / "data"

ONS = {
    f"ons-census2021-ur-{pt}-age101-{kind}-{area}": count
    for pt in ("hh", "ce")
    for kind, area, count in (
        ("sex", "ctry", 404),
        ("sex", "rgn", 1818),
        ("persons", "ctry", 202),
        ("persons", "rgn", 909),
    )
}
NISRA = {
    "nisra-census2021-residence-type-age-sex-ni": 404,
    "nisra-census2021-residence-type-age-sex-lgd14": 4444,
    "nisra-census2021-residence-type-age-sex-parlcon24": 7272,
    "nisra-census2021-residence-type-age-persons-ni": 202,
    "nisra-census2021-residence-type-age-persons-lgd14": 2222,
    "nisra-census2021-residence-type-age-persons-parlcon24": 3636,
}
NRS = {"nrs-census2022-uv101a-scotland": 189}


@pytest.mark.parametrize("alias,count", sorted({**ONS, **NISRA, **NRS}.items()))
def test_packages_are_registered_valid_and_complete(alias, count):
    assert alias in SOURCE_PACKAGE_ALIASES and alias in UK_BUNDLE_SOURCES
    year = 2022 if alias.startswith("nrs") else 2021
    facts = load_source_package(alias).build_facts(year)
    assert len(facts) == count
    assert validate_facts(facts).valid
    assert {f.measure.unit for f in facts} == {"count"}


def test_ons_parser_reads_population_type_and_dimensions():
    path = (
        DATA
        / "ons/census2021_ur_ce_age101_sex_ctry/census2021_ur_ce_ctry_resident_age_101a_sex.json"
    )
    artifact = SourceArtifactMetadata(
        source_name="ons",
        source_table="t",
        source_file=path.name,
        url=None,
        vintage="v",
        sha256="0",
        size_bytes=0,
        extracted_at="2026-10-15",
        extraction_method="test",
    )
    rows = source_rows_from_ons_census_observations_json(
        path.read_bytes(), artifact, sheet_name="observations"
    )
    assert len(rows) == 404
    assert list(rows[0].values) == [
        "population_type",
        "ctry",
        "ctry_code",
        "resident_age_101a",
        "resident_age_101a_code",
        "sex",
        "sex_code",
        "observation",
    ]
    assert {row.values["population_type"] for row in rows} == {"UR_CE"}
    # Each dimension carries ONS's label beside its option code, never the code twice.
    assert rows[0].values["ctry"] == "England"
    assert rows[0].values["ctry_code"] == "E92000001"
    assert {
        (row.values["resident_age_101a_code"], row.values["resident_age_101a"])
        for row in rows
        if row.values["resident_age_101a_code"] in {"0", "90", "100"}
    } == {
        ("0", "Aged under 1 year"),
        ("90", "Aged 90 years"),
        ("100", "Aged 100 years and over"),
    }
    assert ons_census_observation_labels(path.read_bytes()) == {
        "ctry": "Countries",
        "resident_age_101a": "Age (101 categories)",
        "sex": "Sex (2 categories)",
    }
    malformed = json.loads(path.read_bytes())
    malformed["observations"][1]["dimensions"] = malformed["observations"][1][
        "dimensions"
    ][:2]
    with pytest.raises(ValueError, match="one dimension layout"):
        source_rows_from_ons_census_observations_json(
            json.dumps(malformed).encode(), artifact, sheet_name="observations"
        )


def test_ons_ages_90_and_over_by_residence_type():
    def cells(pt):
        facts = load_source_package(
            f"ons-census2021-ur-{pt}-age101-sex-ctry"
        ).build_facts(2021)
        return {
            (f.geography.id, f.filters["sex"], f.filters["resident_age_101a"]): f.value
            for f in facts
        }

    households, communal = cells("hh"), cells("ce")
    england = "E92000001"
    assert communal[(england, "Female", "Aged 90 years")] == 10_697
    assert communal[(england, "Male", "Aged 100 years and over")] == 601
    assert households[(england, "Female", "Aged 85 years")] == 119_705

    # The communal share rises steeply above 85, the point of the request.
    def share(age, sex):
        return communal[(england, sex, age)] / (
            communal[(england, sex, age)] + households[(england, sex, age)]
        )

    assert share("Aged 99 years", "Female") > 0.35 > share("Aged 85 years", "Female")


def test_ons_wales_is_ported_once():
    for pt in ("hh", "ce"):
        for kind in ("sex", "persons"):
            regions = load_source_package(
                f"ons-census2021-ur-{pt}-age101-{kind}-rgn"
            ).build_facts(2021)
            assert {f.geography.id[:3] for f in regions} == {"E12"}
            assert len({f.geography.id for f in regions}) == 9
            countries = load_source_package(
                f"ons-census2021-ur-{pt}-age101-{kind}-ctry"
            ).build_facts(2021)
            assert {f.geography.id for f in countries} == {"E92000001", "W92000004"}
            assert {f.filters["population_type"] for f in countries} == {
                f"UR_{pt.upper()}"
            }


def test_nisra_single_years_and_geographies():
    facts = load_source_package(
        "nisra-census2021-residence-type-age-sex-parlcon24"
    ).build_facts(2021)
    assert Counter(f.filters["Residence Type Label"] for f in facts) == {
        "Person in a household": 3636,
        "Person in a communal establishment": 3636,
    }
    assert {f.geography.level for f in facts} == {"constituency"}
    assert len({f.geography.id for f in facts}) == 18
    assert {f.filters["Age Label"] for f in facts} >= {
        "90 years",
        "99 years",
        "100+ years",
    }
    ni = load_source_package("nisra-census2021-residence-type-age-sex-ni").build_facts(
        2021
    )
    assert {f.geography.id for f in ni} == {"N92000002"}
    oldest = {
        (f.filters["Residence Type Label"], f.filters["Sex Label"]): f.value
        for f in ni
        if f.filters["Age Label"] == "100+ years"
    }
    assert oldest[("Person in a communal establishment", "Female")] == 100
    assert oldest[("Person in a communal establishment", "Male")] == 16


def test_nrs_publishes_nothing_above_85_by_residence_type():
    facts = load_source_package("nrs-census2022-uv101a-scotland").build_facts(2022)
    # The full-row parser reads the single-age band '15' as the number 15.
    ages = {str(f.filters["Age"]) for f in facts}
    assert "85 and over" in ages and not any("90" in age for age in ages)
    assert {f.geography.id for f in facts} == {"S92000003"}
    total = next(
        f
        for f in facts
        if f.filters
        == {
            "Sex": "All people",
            "Residence Type Indicator": "All people",
            "Age": "Total",
        }
    )
    assert total.value == 5_439_842
