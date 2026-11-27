"""IRS county and 118th-Congress totals preserve the 2023 publisher cells."""

import csv
from pathlib import Path

import pytest

from chronicle.source_package import load_source_package


@pytest.mark.parametrize(
    ("package_id", "source_path", "key_columns", "filters", "expected_total"),
    [
        (
            "soi-county-2023",
            "county_2023/23incyallnoagi.csv",
            ("STATEFIPS", "COUNTYFIPS"),
            ("1", "1"),
            25_970,
        ),
        (
            "soi-congressional-district-2023",
            "congressional_district_2023/23incd.csv",
            ("STATEFIPS", "CONG_DISTRICT"),
            ("30", "2"),
            267_360,
        ),
    ],
)
def test_new_geographies_match_the_source(
    package_id, source_path, key_columns, filters, expected_total
):
    package = load_source_package(package_id)
    facts = package.build_facts(2023)
    assert all(str(fact.period.value) == "2023" for fact in facts)
    root = Path(__file__).resolve().parents[1] / "db/data/irs_soi"
    with (root / source_path).open(encoding="utf-8-sig", errors="strict") as file:
        source = next(
            row
            for row in csv.DictReader(file)
            if int(row.get("agi_stub", 0)) == 0
            and all(
                int(row[key]) == int(value)
                for key, value in zip(key_columns, filters, strict=True)
            )
        )
    county = package_id == "soi-county-2023"
    geoid = "0500000US01001" if county else "5001800US3002"
    selected = {
        fact.source_record_id.rsplit(".", 1)[1]: fact
        for fact in facts
        if fact.geography.id == geoid
    }
    assert selected["return_count"].value == expected_total == int(float(source["N1"]))
    assert (
        selected["adjusted_gross_income"].value == int(float(source["A00100"])) * 1000
    )
    if not county:
        assert selected["return_count"].geography.vintage == "118th_congress"
        assert (
            sum(
                fact.geography.level == "congressional_district"
                and fact.source_record_id.endswith(".return_count")
                for fact in facts
            )
            == 429
        )
