"""IRS county and 118th-Congress totals preserve the 2023 publisher cells.

The TY2023 district file uses the districts of the 118th Congress, and the
TY2022 file those of the 117th; each guide says so in section D
(``tests/data/irs_soi_doc_guides/incddocguide_district_boundaries.tsv``). So
``soi-congressional-district-2023`` is its own series: 118th-Congress GEOIDs
(``5001800US``), its own record_set_spec_ids, and no district key that a
117th-Congress district also uses. It reads the columns and AGI classes
chronicle#448 added to the TY2022 package (chronicle#449).
"""

import csv
from copy import deepcopy
from functools import cache
from pathlib import Path
import re

import pytest
import yaml

from chronicle.source_package import load_source_package

REPO_ROOT = Path(__file__).resolve().parents[1]
IRS_SOI_PACKAGES = REPO_ROOT / "packages" / "irs_soi"
BOUNDARIES = (
    Path(__file__).resolve().parent
    / "data"
    / "irs_soi_doc_guides"
    / "incddocguide_district_boundaries.tsv"
)
PREFIX = "irs_soi.ty2023.congressional_district_2023"
DISTRICT_2023_PAGE = (
    "https://www.irs.gov/statistics/soi-tax-stats-data-by-congressional-district-2023"
)


@cache
def _payload(year: int) -> dict:
    path = IRS_SOI_PACKAGES / f"congressional_district_{year}" / "source_package.yaml"
    return yaml.safe_load(path.read_text())


@cache
def _facts_2023() -> dict:
    package = load_source_package("soi-congressional-district-2023")
    return {fact.source_record_id: fact for fact in package.build_facts(2023)}


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
    # The district package also reads nine AGI classes; compare its
    # all-returns record set with the agi_stub 0 row.
    all_returns = (
        "irs_soi.ty2023.county_totals." if county else f"{PREFIX}.all_returns."
    )
    selected = {
        fact.source_record_id.rsplit(".", 1)[1]: fact
        for fact in facts
        if fact.geography.id == geoid and fact.source_record_id.startswith(all_returns)
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
                and fact.source_record_id.startswith(all_returns)
                and fact.source_record_id.endswith(".return_count")
                for fact in facts
            )
            == 429
        )


def _guide_sentences() -> dict[str, dict[str, str]]:
    lines = [
        line for line in BOUNDARIES.read_text().splitlines() if not line.startswith("#")
    ]
    reader = csv.DictReader(lines, delimiter="\t")
    assert reader.fieldnames == ["guide", "boundaries", "one_district_states"]
    return {row["guide"]: row for row in reader}


@pytest.mark.parametrize("year", [2022, 2023])
def test_district_rows_use_the_congress_their_guide_names(year):
    """Every district row carries the GEOID and vintage of the guide's Congress.

    A 118th-Congress district is ``5001800US`` + state FIPS + district (the
    Congress's last two digits after summary level 500), as the Census Bureau
    writes it; the ACS district packages use ``5001900US`` for the 119th
    Congress. The states the guide lists with one district publish no district
    row; every other state publishes two or more.
    """
    sentences = _guide_sentences()[f"{year % 100}incddocguide"]
    congress = re.fullmatch(
        r"District boundaries are based on the (\d+)th Congress\.",
        sentences["boundaries"],
    ).group(1)
    one_district = set(
        re.fullmatch(
            r"\w+ states \(([A-Z, and]+)\) have only one congressional district, "
            r"therefore the matching procedures are not performed on these states\.",
            sentences["one_district_states"],
        )
        .group(1)
        .replace(" and ", " ")
        .replace(",", " ")
        .split()
    )
    assert {"2022": "117", "2023": "118"}[str(year)] == congress
    summary_level = f"500{int(congress) % 100:02d}00US"
    for record_set in _payload(year)["record_sets"]:
        districts_by_state: dict[str, int] = {}
        for row in record_set["rows"]:
            if row["geography_level"] != "congressional_district":
                assert row["geography_vintage"] == "2020_census", row["value_id"]
                assert not row["geography_id"].startswith("500"), row["value_id"]
                continue
            guards = {guard["label"]: guard for guard in row["guard_cells"]}
            fips = guards["state FIPS"]["expected_value"]
            district = guards["congressional district code"]["expected_value"]
            assert row["geography_vintage"] == f"{congress}th_congress"
            assert row["geography_id"] == f"{summary_level}{fips:02d}{district:02d}"
            state = row["expected_row_header"]
            districts_by_state[state] = districts_by_state.get(state, 0) + 1
        states = {
            row["expected_row_header"]
            for row in record_set["rows"]
            if row["geography_level"] == "state"
        }
        assert len(states) == 51
        assert one_district <= states
        assert set(districts_by_state) == states - one_district
        assert min(districts_by_state.values()) >= 2


def test_ty2023_districts_are_their_own_series():
    """No TY2023 district key is a TY2022 (117th Congress) district key."""
    old, new = _payload(2022), _payload(2023)

    def district_ids(payload):
        return {
            row["geography_id"]
            for record_set in payload["record_sets"]
            for row in record_set["rows"]
            if row["geography_level"] == "congressional_district"
        }

    def spec_ids(payload):
        return {
            record_set["record_set_spec_id"] for record_set in payload["record_sets"]
        }

    assert len(district_ids(old)) == 428
    assert len(district_ids(new)) == 429
    assert not district_ids(old) & district_ids(new)
    assert spec_ids(new) == {
        "irs_soi.congressional_district_2023.all_returns.v1",
        "irs_soi.congressional_district_2023.agi_class.v1",
    }
    assert not spec_ids(old) & spec_ids(new)
    assert all(
        record_set["source_record_id_prefix"].startswith(f"{PREFIX}.")
        for record_set in new["record_sets"]
    )


def test_ty2023_reads_the_columns_448_added_to_ty2022():
    """The 45 measures chronicle#448 added keep the TY2022 identities.

    Each reads the 23incd.csv column of the same IRS variable, which the
    TY2023 guide defines the same way (tests/test_chronicle_soi_doc_guide_columns.py).
    Only the wage measure's legal vintage and evidence page name TY2023. The
    TY2023 package has every TY2022 measure, in order, but ``eitc_amount``.
    """
    old = _payload(2022)["record_sets"][0]["measures"]
    new = _payload(2023)["record_sets"][0]["measures"]
    with (REPO_ROOT / "db/data/irs_soi/congressional_district_2023/23incd.csv").open(
        newline="", encoding="utf-8-sig"
    ) as file:
        header = next(csv.reader(file))

    def letters(index: int) -> str:
        text, index = "", index + 1
        while index:
            index, rem = divmod(index - 1, 26)
            text = chr(ord("A") + rem) + text
        return text

    assert [measure["measure_id"] for measure in new] == [
        measure["measure_id"]
        for measure in old
        if measure["measure_id"] != "eitc_amount"
    ]
    assert len(new) == 106
    for old_measure, new_measure in zip(old[62:], new[61:], strict=True):
        expected = deepcopy(old_measure)
        expected["column"] = letters(header.index(old_measure["source_column_id"]))
        if old_measure["measure_id"] == "wages_salaries_amount":
            expected["legal_vintage"] = "tax_year_2023"
            expected["concept_evidence_url"] = DISTRICT_2023_PAGE
        assert new_measure == expected


def test_ty2023_district_cells():
    """Cells of the new measures and classes, as 23incd.csv publishes them."""
    facts = _facts_2023()
    cells = {
        "all_returns.us.wages_salaries_amount": (10_090_847_180_000, "A00200"),
        "all_returns.us.standard_deduction_amount": (2_775_570_555_000, "A04450"),
        "all_returns.us.total_tax_liability_amount": (2_246_087_774_000, "A10300"),
        "all_returns.mt_02.itemized_deductions_returns": (18_530, "N04470"),
        "all_returns.ca_total.real_estate_taxes_claims": (2_393_990, "N18500"),
        "all_returns.al_01.net_investment_income_tax_amount": (32_347_000, "A85300"),
        "all_returns.co_08.self_employed_health_insurance_ald": (43_844_000, "A03270"),
        "agi_under_1.al_total.return_count": (27_030, "N1"),
        "agi_under_1.al_total.adjusted_gross_income": (-929_106_000, "A00100"),
        "agi_500k_plus.ca_12.return_count": (12_660, "N1"),
    }
    for record, expected in cells.items():
        fact = facts[f"{PREFIX}.{record}"]
        assert (fact.value, fact.layout.source_column_id) == expected, record
    top = facts[f"{PREFIX}.agi_500k_plus.ca_12.return_count"]
    assert top.geography.id == "5001800US0612"
    assert top.geography.vintage == "118th_congress"
    assert {
        (constraint.variable, constraint.operator, constraint.value)
        for constraint in top.constraints
    } == {("us:statutes/26/62#adjusted_gross_income", ">=", 500_000)}
    assert not any(
        record.startswith(f"{PREFIX}.agi_") and ".us." in record for record in facts
    )
    assert len(facts) == 106 * 481 + 2 * 9 * 480


EITC_AMOUNT_COLUMNS = ("A59660", "A59661", "A59662", "A59663", "A59664")


def _eitc_rows(year: int) -> list[dict[str, float]]:
    path = (
        REPO_ROOT
        / f"db/data/irs_soi/congressional_district_{year}"
        / f"{year % 100}incd.csv"
    )
    with path.open(newline="", encoding="utf-8-sig") as file:
        return [
            {
                "agi_stub": int(row["agi_stub"]),
                **{column: float(row[column]) for column in EITC_AMOUNT_COLUMNS},
            }
            for row in csv.DictReader(file)
        ]


def test_ty2023_eitc_total_column_adds_a_dollar_column_to_thousands():
    """23incd.csv's A59660 is not in thousands of dollars, so it is left out.

    Both district files publish A59664 (three or more children) in dollars and
    the other EITC amounts in thousands; the packages read A59664 with
    value_scale 1. In 22incd.csv each all-class row's total A59660 is within
    1.3% of A59661 + A59662 + A59663 + A59664 / 1000. In every row of
    23incd.csv, A59660 equals the plain sum, so it adds dollars to thousands:
    read in thousands, the US total is $15.3 trillion, against $65.0 billion in
    Historic Table 2. So soi-congressional-district-2023 reads no A59660 and
    computes no total (chronicle#449). If the IRS corrects the file, the sum
    check below fails: read A59660 again then.
    """
    rows_2022 = [row for row in _eitc_rows(2022) if row["agi_stub"] == 0]
    assert len(rows_2022) == 480
    for row in rows_2022:
        parts = row["A59661"] + row["A59662"] + row["A59663"] + row["A59664"] / 1000
        assert abs(row["A59660"] - parts) <= 0.013 * row["A59660"], row
    rows_2023 = _eitc_rows(2023)
    assert len(rows_2023) == 4801
    for row in rows_2023:
        parts = row["A59661"] + row["A59662"] + row["A59663"] + row["A59664"]
        assert row["A59660"] == parts, row
    (us_2023,) = [row for row in rows_2023 if row["A59660"] == 15_325_005_218]
    assert us_2023["A59664"] == 15_275_346_253

    reads = {
        measure["source_column_id"]: measure
        for record_set in _payload(2023)["record_sets"]
        for measure in record_set["measures"]
    }
    assert "A59660" not in reads
    assert not any(record.endswith(".eitc_amount") for record in _facts_2023())
    # The four child amounts stay, as published.
    assert {
        column: reads[column].get("value_scale") for column in EITC_AMOUNT_COLUMNS[1:]
    } == {
        "A59661": 1000,
        "A59662": 1000,
        "A59663": 1000,
        "A59664": 1,
    }
    facts = _facts_2023()
    three_plus = facts[f"{PREFIX}.all_returns.us.eitc_three_or_more_children_amount"]
    assert three_plus.value == 15_275_346_253
    # In TY2022 the total stays: the file publishes it in thousands.
    old_reads = {
        measure["source_column_id"]: measure["measure_id"]
        for measure in _payload(2022)["record_sets"][0]["measures"]
    }
    assert old_reads["A59660"] == "eitc_amount"
