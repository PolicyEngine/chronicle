"""UK young people facts for PolicyEngine/chronicle#420 (PolicyEngine/uk-young-people-work-review).

Checks the packages scripts/build_uk_young_people_packages.py writes: ONS NEET (August
2026), LFS table A06 seasonally adjusted and not (October 2026), PAYE RTI by age (October
2026), ASHE Table 6 by age group (2024 revised, 2025 revised, 2026 provisional) and
HMRC's employer NICs reliefs for young employees (January 2026). Values are re-read from
the pinned files with openpyxl and xlrd, and each fact's cell is found from the fact's
own dimensions and period, not from the package's coordinates.
"""

from __future__ import annotations

import hashlib
import io
import re
import runpy
import zipfile
from collections import Counter
from pathlib import Path

import openpyxl
import pytest
import xlrd
import yaml
from openpyxl.utils import column_index_from_string, get_column_letter

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

ASHE_EDITIONS = ("2024_revised", "2025_revised", "2026_provisional")
ASHE_TABLES = (
    "weekly_pay_gross",
    "weekly_pay_gross_cv",
    "annual_pay_gross",
    "annual_pay_gross_cv",
)
FACT_COUNTS = {
    "ons-neet-august-2026": 945,
    "ons-a06-sa-october-2026": 1701,
    "ons-a06-nsa-october-2026": 2831,
    "ons-paye-rti-age-nsa-october-2026": 826,
    "ons-ashe-table6-weekly-pay-gross-2024-revised": 928,
    "ons-ashe-table6-weekly-pay-gross-cv-2024-revised": 930,
    "ons-ashe-table6-annual-pay-gross-2024-revised": 862,
    "ons-ashe-table6-annual-pay-gross-cv-2024-revised": 904,
    "ons-ashe-table6-weekly-pay-gross-2025-revised": 928,
    "ons-ashe-table6-weekly-pay-gross-cv-2025-revised": 928,
    "ons-ashe-table6-annual-pay-gross-2025-revised": 877,
    "ons-ashe-table6-annual-pay-gross-cv-2025-revised": 877,
    "ons-ashe-table6-weekly-pay-gross-2026-provisional": 924,
    "ons-ashe-table6-weekly-pay-gross-cv-2026-provisional": 924,
    "ons-ashe-table6-annual-pay-gross-2026-provisional": 862,
    "ons-ashe-table6-annual-pay-gross-cv-2026-provisional": 862,
    "hmrc-employer-nics-age-reliefs-january-2026": 22,
}
QUARTERS = (
    [f"{year}-Q{q}" for year, q in [(2024, 2), (2024, 3), (2024, 4)]]
    + [f"{year}-Q{q}" for year in (2025,) for q in (1, 2, 3, 4)]
    + ["2026-Q1", "2026-Q2"]
)
QUARTER_WORDS = {1: "Jan-Mar", 2: "Apr-Jun", 3: "Jul-Sep", 4: "Oct-Dec"}


@pytest.fixture(scope="module")
def built():
    packages = {}
    for package_id in FACT_COUNTS:
        package = load_source_package(package_id)
        year = package.artifact.artifact_year
        packages[package_id] = (package, year, package.build_facts(year))
    return packages


def _pinned(directory: str) -> tuple[dict, bytes]:
    manifest = yaml.safe_load((DATA / directory / "manifest.yaml").read_text())
    ((_, entry),) = manifest["files"].items()
    return entry, (DATA / directory / entry["filename"]).read_bytes()


def _quarter_label(period: str) -> str:
    year, quarter = period.split("-Q")
    return f"{QUARTER_WORDS[int(quarter)]} {year}"


def _rows_by_label(values_by_row: dict[int, object]) -> dict[str, int]:
    rows = {}
    for row, value in values_by_row.items():
        if isinstance(value, str):
            rows[value.removesuffix(" [r]")] = row
    return rows


def _column(first: str, offset: int) -> str:
    return get_column_letter(column_index_from_string(first) + offset)


# ---------------------------------------------------------------- registration


def test_packages_validate_register_and_carry_no_anchors(built):
    for package_id, (package, year, facts) in built.items():
        report = validate_source_package(package.package_path, year=year)
        assert report.valid, report.to_dict()
        assert not report.warnings
        assert (
            report.counts["source_record_count"]
            == len(facts)
            == FACT_COUNTS[package_id]
        )
        relative = package.package_path.relative_to(ROOT / "packages")
        assert SOURCE_PACKAGE_ALIASES[package_id] == relative
        assert package_id in UK_BUNDLE_SOURCES
        text = (package.package_path / "source_package.yaml").read_text(
            encoding="utf-8"
        )
        assert not re.search(r"(:|^\s*-)\s+[&*][A-Za-z_][\w-]*\s*$", text, re.M)
        assert validate_facts(facts).valid
        keys = Counter(build_semantic_fact_key(fact) for fact in facts)
        assert max(keys.values()) == 1, package_id


def test_generator_reproduces_the_committed_packages():
    generator = runpy.run_path(str(ROOT / "scripts/build_uk_young_people_packages.py"))
    builders = generator["BUILDERS"]
    assert len(builders) == len(FACT_COUNTS)
    for directory, build in builders.items():
        committed = ROOT / "packages" / directory / "source_package.yaml"
        assert build() == committed.read_text(encoding="utf-8"), directory


MANIFESTS = (
    "ons/neet_august_2026",
    "ons/a06_sa_october_2026",
    "ons/a06_nsa_october_2026",
    "ons/paye_rti_nsa_october_2026",
    *(f"ons/ashe_table6_{edition}" for edition in ASHE_EDITIONS),
    "hmrc/tax_relief_statistics_january_2026",
)


@pytest.mark.parametrize("directory", MANIFESTS)
def test_manifests_pin_bytes_licence_and_the_r2_key(directory):
    path = DATA / directory / "manifest.yaml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert manifest["source_id"] == directory.split("/")[0]
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-06"
    ((year, entry),) = manifest["files"].items()
    content = (path.parent / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    host = (
        "assets.publishing.service.gov.uk"
        if directory.startswith("hmrc")
        else "www.ons.gov.uk"
    )
    assert entry["source_url"].startswith(f"https://{host}/")
    # `chronicle publish-raw` uploaded the bytes and wrote storage.r2, and
    # `chronicle verify-raw` read each object back.
    key = (
        f"raw/uk/{manifest['source_id']}/{manifest['package_id']}/{year}/"
        f"{entry['sha256']}/{entry['filename']}"
    )
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }


def test_consumer_contract_is_valid(built):
    for package_id, (_, _, facts) in built.items():
        report = validate_consumer_fact_contract(facts)
        assert report.valid, (package_id, report.errors[:3])
        assert all(fact.source.raw_r2_uri for fact in facts), package_id


# ---------------------------------------------------------------- 1. ONS NEET

NEET_GROUPS = {"16_to_24": "B", "16_to_17": "G", "18_to_24": "L"}
NEET_SINGLE = {
    "18_to_20": "People 18-20 - NSA",
    "21_to_22": "People 21-22 - NSA",
    "23_to_24": "People 23-24 - NSA",
}
NEET_SEX = {"all": "People", "male": "Men", "female": "Women"}


def _neet_workbook():
    entry, content = _pinned("ons/neet_august_2026")
    return openpyxl.load_workbook(io.BytesIO(content), data_only=True)


def _neet_cell(workbook, fact) -> object:
    band = fact.filters["age_band"]
    adjustment = (
        "SA" if fact.filters["seasonal_adjustment"] == "seasonally_adjusted" else "NSA"
    )
    if band in NEET_SINGLE:
        sheet, first = NEET_SINGLE[band], "B"
    else:
        sheet, first = (
            f"{NEET_SEX[fact.filters['sex']]} - {adjustment}",
            NEET_GROUPS[band],
        )
    worksheet = workbook[sheet]
    rows = _rows_by_label({cell.row: cell.value for cell in worksheet["A"]})
    row = rows[_quarter_label(fact.period.value)]
    concept = fact.measure.concept
    if concept == "ons.lfs_neet_people":
        offset = {"all": 0, "unemployed": 1, "economically_inactive": 2}[
            fact.filters["economic_activity"]
        ]
    else:
        offset = {"ons.lfs_people": 3, "ons.lfs_neet_rate": 4}[concept]
    return worksheet[f"{_column(first, offset)}{row}"].value


def test_neet_facts_are_the_published_cells_and_only_those(built):
    _, _, facts = built["ons-neet-august-2026"]
    workbook = _neet_workbook()
    seen = Counter()
    for fact in facts:
        assert fact.value == _neet_cell(workbook, fact), fact.layout.measure_id
        assert fact.period.type == "quarter" and fact.period.value in QUARTERS
        seen[fact.period.value] += 1
    # Six sheets of 15 cells and three of five, every quarter.
    assert seen == {quarter: 6 * 15 + 3 * 5 for quarter in QUARTERS}


def _neet(
    facts,
    period,
    concept,
    band,
    sex="all",
    adjustment="seasonally_adjusted",
    status=None,
):
    matches = [
        fact
        for fact in facts
        if fact.period.value == period
        and fact.measure.concept == concept
        and fact.filters["age_band"] == band
        and fact.filters["sex"] == sex
        and fact.filters["seasonal_adjustment"] == adjustment
        and (status is None or fact.filters["economic_activity"] == status)
    ]
    assert len(matches) == 1, (period, concept, band, sex, adjustment, status)
    return matches[0].value


def test_neet_bulletin_headlines_and_parity(built):
    _, _, facts = built["ons-neet-august-2026"]
    # 'There were an estimated 981,000 young people aged 16 to 24 years in the UK who
    # were NEET in April to June 2026'; 13.0%; 894,000 aged 18 to 24; 393,000
    # unemployed and 588,000 inactive; 530,000 men and 451,000 women.
    q = "2026-Q2"
    assert (
        round(_neet(facts, q, "ons.lfs_neet_people", "16_to_24", status="all"), -3)
        == 981_000
    )
    assert round(_neet(facts, q, "ons.lfs_neet_rate", "16_to_24"), 1) == 13.0
    assert (
        round(_neet(facts, q, "ons.lfs_neet_people", "18_to_24", status="all"), -3)
        == 894_000
    )
    assert (
        round(
            _neet(facts, q, "ons.lfs_neet_people", "16_to_24", status="unemployed"), -3
        )
        == 393_000
    )
    assert (
        round(
            _neet(
                facts,
                q,
                "ons.lfs_neet_people",
                "16_to_24",
                status="economically_inactive",
            ),
            -3,
        )
        == 588_000
    )
    assert (
        round(
            _neet(facts, q, "ons.lfs_neet_people", "16_to_24", "male", status="all"), -3
        )
        == 530_000
    )
    assert (
        round(
            _neet(facts, q, "ons.lfs_neet_people", "16_to_24", "female", status="all"),
            -3,
        )
        == 451_000
    )
    for quarter in QUARTERS:
        for sex in NEET_SEX:
            for adjustment in ("seasonally_adjusted", "not_seasonally_adjusted"):
                args = dict(sex=sex, adjustment=adjustment)
                for status in ("all", "unemployed", "economically_inactive"):
                    whole = _neet(
                        facts,
                        quarter,
                        "ons.lfs_neet_people",
                        "16_to_24",
                        status=status,
                        **args,
                    )
                    parts = sum(
                        _neet(
                            facts,
                            quarter,
                            "ons.lfs_neet_people",
                            band,
                            status=status,
                            **args,
                        )
                        for band in ("16_to_17", "18_to_24")
                    )
                    assert parts == pytest.approx(whole, rel=1e-9)
                neet = _neet(
                    facts,
                    quarter,
                    "ons.lfs_neet_people",
                    "16_to_24",
                    status="all",
                    **args,
                )
                assert neet == pytest.approx(
                    _neet(
                        facts,
                        quarter,
                        "ons.lfs_neet_people",
                        "16_to_24",
                        status="unemployed",
                        **args,
                    )
                    + _neet(
                        facts,
                        quarter,
                        "ons.lfs_neet_people",
                        "16_to_24",
                        status="economically_inactive",
                        **args,
                    ),
                    rel=1e-9,
                )


def test_neet_women_nsa_population_gap_is_ported_as_published(built):
    """ONS's 'Women - NSA' 18-24 population sits below the SA sheet's and A06's."""
    _, _, facts = built["ons-neet-august-2026"]
    _, _, a06 = built["ons-a06-nsa-october-2026"]
    generator = runpy.run_path(str(ROOT / "scripts/build_uk_young_people_packages.py"))
    gaps = generator["NEET_WOMEN_NSA_POPULATION_GAPS"]
    for quarter in QUARTERS:
        nsa = dict(sex="female", adjustment="not_seasonally_adjusted")
        whole = _neet(facts, quarter, "ons.lfs_people", "16_to_24", **nsa)
        parts = _neet(facts, quarter, "ons.lfs_people", "16_to_17", **nsa) + _neet(
            facts, quarter, "ons.lfs_people", "18_to_24", **nsa
        )
        assert whole - parts == gaps[quarter]
        sa = _neet(facts, quarter, "ons.lfs_people", "18_to_24", sex="female")
        assert (
            sa - _neet(facts, quarter, "ons.lfs_people", "18_to_24", **nsa)
            == gaps[quarter]
        )
        a06_total = [
            fact.value
            for fact in a06
            if fact.period.value == quarter
            and fact.measure.concept == "ons.lfs_people"
            and fact.filters["sex"] == "female"
            and fact.filters["age_band"] == "18_to_24"
            and fact.filters["full_time_education"] == "all"
            and fact.filters["economic_activity"] == "all"
        ]
        assert a06_total == [sa]


def test_a_corrected_women_nsa_population_fails_the_build():
    """The pinned gap is a check: if ONS corrects the cell, the generator refuses it."""
    generator = runpy.run_path(str(ROOT / "scripts/build_uk_young_people_packages.py"))
    entry, content = generator["pinned"](generator["NEET_DIRECTORY"])
    grid = generator["grid_of"](
        generator["source_cells_from_xlsx"](
            content, generator["metadata"](entry["filename"])
        )
    )
    sheet, groups = "Women - NSA", generator["NEET_MAIN_GROUPS"]
    latest = generator["quarters"](grid, sheet, rolling=False)[-1]
    # As published, the row passes.
    generator["neet_check_parity"](grid, sheet, latest, groups)
    # A corrected edition: the 18-24 population (O) becomes the SA sheet's, and its
    # NEET share (P) is recomputed on it, so only the pinned gap no longer holds.
    corrected = dict(grid)
    corrected[(sheet, latest.row, "O")] = grid[("Women - SA", latest.row, "O")]
    corrected[(sheet, latest.row, "P")] = (
        100 * grid[(sheet, latest.row, "L")] / corrected[(sheet, latest.row, "O")]
    )
    with pytest.raises(AssertionError):
        generator["neet_check_parity"](corrected, sheet, latest, groups)


# ---------------------------------------------------------------- 2. LFS A06

A06_GROUP_FIRST = {
    "16_to_17": "B",
    "18_to_24": "W",
    "16_to_24": "AR",
    "18_to_21": "B",
    "22_to_24": "W",
}
A06_BLOCK = {
    ("levels", "all"): 0,
    ("levels", "in_full_time_education"): 4,
    ("levels", "not_in_full_time_education"): 8,
    ("rates", "all"): 12,
    ("rates", "in_full_time_education"): 15,
    ("rates", "not_in_full_time_education"): 18,
}
A06_LEVEL_STATUS = {
    "all": 0,
    "employed": 1,
    "unemployed": 2,
    "economically_inactive": 3,
}
A06_RATE = {
    "ons.lfs_employment_rate": 0,
    "ons.lfs_unemployment_rate": 1,
    "ons.lfs_economic_inactivity_rate": 2,
}


def _a06_sheet_name(fact, key: str) -> str:
    sex = NEET_SEX[fact.filters["sex"]]
    if key == "sa":
        return sex
    return f"{sex} {'18_24' if fact.filters['age_band'] in ('18_to_21', '22_to_24') else '16_24'}"


@pytest.mark.parametrize("key", ["sa", "nsa"])
def test_a06_facts_are_the_published_cells_and_only_those(built, key):
    _, _, facts = built[f"ons-a06-{key}-october-2026"]
    entry, content = _pinned(f"ons/a06_{key}_october_2026")
    book = xlrd.open_workbook(file_contents=content)
    seen = set()
    for fact in facts:
        sheet = book.sheet_by_name(_a06_sheet_name(fact, key))
        rows = {sheet.cell_value(r, 0): r for r in range(sheet.nrows)}
        row = rows[_quarter_label(fact.period.value)]
        concept = fact.measure.concept
        education = fact.filters["full_time_education"]
        if concept == "ons.lfs_people":
            offset = (
                A06_BLOCK[("levels", education)]
                + A06_LEVEL_STATUS[fact.filters["economic_activity"]]
            )
        else:
            offset = A06_BLOCK[("rates", education)] + A06_RATE[concept]
        column = (
            column_index_from_string(A06_GROUP_FIRST[fact.filters["age_band"]])
            - 1
            + offset
        )
        assert fact.value == sheet.cell_value(row, column), fact.layout.measure_id
        seen.add((sheet.name, row, column))
    # Every numeric cell of the ported rows and groups is a fact; '*' cells are not.
    expected = set()
    suppressed = 0
    for sheet in book.sheets():
        if sheet.name in ("Note", "Pre-1992 estimates"):
            continue
        rows = {sheet.cell_value(r, 0): r for r in range(sheet.nrows)}
        firsts = ("B", "W") if sheet.name.endswith("18_24") else ("B", "W", "AR")
        for quarter in QUARTERS:
            row = rows[_quarter_label(quarter)]
            for first in firsts:
                for offset in range(21):
                    column = column_index_from_string(first) - 1 + offset
                    value = sheet.cell_value(row, column)
                    if value == "*":
                        suppressed += 1
                        continue
                    expected.add((sheet.name, row, column))
    assert seen == expected
    assert suppressed == (0 if key == "sa" else 4)


@pytest.mark.parametrize("key", ["sa", "nsa"])
def test_a06_parity(built, key):
    _, _, facts = built[f"ons-a06-{key}-october-2026"]
    levels = {
        (
            fact.period.value,
            fact.filters["sex"],
            fact.filters["age_band"],
            fact.filters["full_time_education"],
            fact.filters["economic_activity"],
        ): fact.value
        for fact in facts
        if fact.measure.concept == "ons.lfs_people"
    }
    for (quarter, sex, band, education, status), value in levels.items():
        if status == "all":
            parts = [
                levels.get((quarter, sex, band, education, s))
                for s in ("employed", "unemployed", "economically_inactive")
            ]
            if None not in parts:
                assert sum(parts) == pytest.approx(value, rel=1e-9)
        if education == "all":
            parts = [
                levels.get((quarter, sex, band, e, status))
                for e in ("in_full_time_education", "not_in_full_time_education")
            ]
            if None not in parts:
                assert sum(parts) == pytest.approx(value, rel=1e-9)
        if band == "16_to_24":
            parts = [
                levels.get((quarter, sex, b, education, status))
                for b in ("16_to_17", "18_to_24")
            ]
            assert sum(parts) == pytest.approx(value, rel=1e-9)
        if band == "18_to_24" and key == "nsa":
            parts = [
                levels.get((quarter, sex, b, education, status))
                for b in ("18_to_21", "22_to_24")
            ]
            if None not in parts:
                assert sum(parts) == pytest.approx(value, rel=1e-9)
    # Only the calendar-quarter windows have a period type.
    assert {fact.period.value for fact in facts} == set(QUARTERS)


# ---------------------------------------------------------------- 4a. PAYE RTI

RTI_SHEETS = {
    "ons.paye_rti_payrolled_employees": "28. Employees (Age)",
    "ons.paye_rti_median_monthly_pay": "29. Median pay (Age)",
    "ons.paye_rti_mean_monthly_pay": "30. Mean pay (Age)",
    "ons.paye_rti_aggregate_monthly_pay": "31. Aggregate pay (Age)",
}
RTI_COLUMNS = {
    "0_to_17": "B",
    "18_to_24": "C",
    "25_to_34": "D",
    "35_to_49": "E",
    "50_to_64": "F",
    "65_and_over": "G",
    "all": "H",
}


def test_rti_facts_are_the_published_cells(built):
    _, _, facts = built["ons-paye-rti-age-nsa-october-2026"]
    entry, content = _pinned("ons/paye_rti_nsa_october_2026")
    workbook = openpyxl.load_workbook(
        io.BytesIO(content), read_only=True, data_only=True
    )
    sheets = {}
    for concept, name in RTI_SHEETS.items():
        rows = {}
        for row in workbook[name].iter_rows(min_row=7, values_only=True):
            if isinstance(row[0], str):
                rows[row[0]] = dict(zip("ABCDEFGH", row[:8]))
        sheets[concept] = rows
    months = Counter()
    for fact in facts:
        label = fact.period_coverage.source_period_label
        cells = sheets[fact.measure.concept][label]
        assert fact.value == cells[RTI_COLUMNS[fact.filters["age_band"]]]
        months[fact.measure.concept] += 1
    # Employees and median pay: April 2024 to September 2026 (30 months); mean and
    # aggregate pay to August 2026 (29), seven columns each.
    assert months == {
        "ons.paye_rti_payrolled_employees": 210,
        "ons.paye_rti_median_monthly_pay": 210,
        "ons.paye_rti_mean_monthly_pay": 203,
        "ons.paye_rti_aggregate_monthly_pay": 203,
    }
    flash = [fact for fact in facts if fact.period.value == "2026-09"]
    assert flash and all(
        "early estimates" in fact.period_coverage.notes for fact in flash
    )


def test_rti_bands_add_to_the_uk(built):
    _, _, facts = built["ons-paye-rti-age-nsa-october-2026"]
    for concept in (
        "ons.paye_rti_payrolled_employees",
        "ons.paye_rti_aggregate_monthly_pay",
    ):
        by_month: dict[str, dict] = {}
        for fact in facts:
            if fact.measure.concept == concept:
                by_month.setdefault(fact.period.value, {})[fact.filters["age_band"]] = (
                    fact.value
                )
        for month, values in by_month.items():
            uk = values.pop("all")
            assert abs(sum(values.values()) - uk) <= 2, (concept, month)
    # September 2026 (flash): 30,337,783 payrolled employees, as the bulletin's '30.3 million'.
    (uk,) = [
        fact.value
        for fact in facts
        if fact.period.value == "2026-09"
        and fact.measure.concept == "ons.paye_rti_payrolled_employees"
        and fact.filters["age_band"] == "all"
    ]
    assert uk == 30_337_783


# ---------------------------------------------------------------- 4b. ASHE Table 6

ASHE_SHEETS = {
    ("all", "all"): "All",
    ("male", "all"): "Male",
    ("female", "all"): "Female",
    ("all", "full_time"): "Full-Time",
    ("all", "part_time"): "Part-Time",
    ("male", "full_time"): "Male Full-Time",
    ("male", "part_time"): "Male Part-Time",
    ("female", "full_time"): "Female Full-Time",
    ("female", "part_time"): "Female Part-Time",
}
ASHE_ROWS = {
    "all": 6,
    "16_to_17": 7,
    "18_to_21": 8,
    "22_to_29": 9,
    "30_to_39": 10,
    "40_to_49": 11,
    "50_to_59": 12,
    "60_and_over": 13,
}
PERCENTILE_COLUMNS = dict(zip((10, 20, 25, 30, 40, 60, 70, 75, 80, 90), range(8, 18)))
TABLE_KEYS = {
    "weekly_pay_gross": "6.1a",
    "weekly_pay_gross_cv": "6.1b",
    "annual_pay_gross": "6.7a",
    "annual_pay_gross_cv": "6.7b",
}


def _ashe_member(edition: str, table: str):
    entry, content = _pinned(f"ons/ashe_table6_{edition}")
    key = TABLE_KEYS[table]
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        (name,) = [
            item
            for item in archive.namelist()
            if f"Table {key} " in item
            and item.endswith(
                (" CV.xlsx" if key.endswith("b") else f"{edition[:4]}.xlsx")
            )
        ]
        return openpyxl.load_workbook(io.BytesIO(archive.read(name)), data_only=True)


@pytest.mark.parametrize("edition", ASHE_EDITIONS)
@pytest.mark.parametrize("table", ASHE_TABLES)
def test_ashe6_facts_are_the_published_cells_and_only_those(built, edition, table):
    package_id = (
        f"ons-ashe-table6-{table.replace('_', '-')}-{edition.replace('_', '-')}"
    )
    _, _, facts = built[package_id]
    workbook = _ashe_member(edition, table)
    seen = set()
    for fact in facts:
        sheet = ASHE_SHEETS[(fact.filters["sex"], fact.filters["working_pattern"])]
        row = ASHE_ROWS[fact.filters.get("age_band", "all")]
        measure = fact.layout.measure_id
        column = {"jobs": 3, "median": 4, "mean": 6}.get(measure)
        if column is None:
            column = PERCENTILE_COLUMNS[int(measure[1:])]
        value = workbook[sheet].cell(row=row, column=column).value
        expected = (
            value * 1000 if measure == "jobs" and not table.endswith("_cv") else value
        )
        assert fact.value == expected, (sheet, row, column)
        seen.add((sheet, row, column))
    published = {
        (sheet, row, column)
        for sheet in ASHE_SHEETS.values()
        for row in ASHE_ROWS.values()
        for column in (3, 4, 6, *PERCENTILE_COLUMNS.values())
        if isinstance(workbook[sheet].cell(row=row, column=column).value, (int, float))
    }
    assert seen == published


@pytest.mark.parametrize("edition", ASHE_EDITIONS)
def test_ashe6_totals_are_table2s_and_jobs_add_up(built, edition):
    year = int(edition[:4])
    headline = {2024: 728.27, 2025: 766.60, 2026: 811.20}[year]
    for table in ASHE_TABLES:
        package_id = (
            f"ons-ashe-table6-{table.replace('_', '-')}-{edition.replace('_', '-')}"
        )
        _, _, facts = built[package_id]
        table2 = load_source_package(package_id.replace("table6", "table2"))
        table2_facts = table2.build_facts(table2.artifact.artifact_year)
        totals = {
            build_semantic_fact_key(f): f.value
            for f in facts
            if f.layout.table_record_kind == "total"
        }
        table2_totals = {
            build_semantic_fact_key(f): f.value
            for f in table2_facts
            if f.layout.table_record_kind == "total"
        }
        # Every sheet's 'All employees' row is Table 2's, so the facts share keys.
        assert totals and totals.items() <= table2_totals.items()
        if table == "weekly_pay_gross":
            (median,) = [
                f.value
                for f in facts
                if f.layout.table_record_kind == "total"
                and f.layout.measure_id == "median"
                and f.filters["sex"] == "all"
                and f.filters["working_pattern"] == "full_time"
            ]
            assert median == pytest.approx(headline, abs=0.05)
        if table in ("weekly_pay_gross", "annual_pay_gross"):
            jobs: dict[tuple, dict] = {}
            for f in facts:
                if f.layout.measure_id == "jobs":
                    key = (f.filters["sex"], f.filters["working_pattern"])
                    jobs.setdefault(key, {})[f.filters.get("age_band", "all")] = f.value
            for key, values in jobs.items():
                total = values.pop("all")
                if len(values) == 7:  # every age group printed
                    assert abs(sum(values.values()) - total) <= 7 * 500, key


# ---------------------------------------------------------------- 9. HMRC NICs reliefs


def test_employer_nics_reliefs(built):
    _, _, facts = built["hmrc-employer-nics-age-reliefs-january-2026"]
    cost = {
        (f.filters["employer_nics_relief"], f.period.value): (f.value, f.assertion)
        for f in facts
        if f.measure.concept == "hmrc.tax_relief_cost"
    }
    claimants = {
        (f.filters["employer_nics_relief"], f.period.value): f.value
        for f in facts
        if f.measure.concept == "hmrc.tax_relief_claimants"
    }
    # Table 2, £ million: 2025-26 is HMRC's first forecast year.
    for year, value in zip(range(2020, 2026), (560, 670, 850, 960, 1100, 1900)):
        expected = "source_projection" if year == 2025 else "observation"
        assert cost[("employees_under_21", year)] == (value * 1_000_000, expected)
    for year, value in zip(range(2020, 2026), (190, 230, 290, 320, 370, 570)):
        expected = "source_projection" if year == 2025 else "observation"
        assert cost[("apprentices_under_25", year)] == (value * 1_000_000, expected)
    # Table 5: employers claiming; 2025-26 'Not available'.
    assert claimants == {
        **{
            ("employees_under_21", y): v
            for y, v in zip(range(2020, 2025), (270000, 321000, 326000, 330000, 340000))
        },
        **{
            ("apprentices_under_25", y): v
            for y, v in zip(range(2020, 2025), (66000, 78000, 76000, 73000, 72000))
        },
    }
    assert {f.entity.name for f in facts} == {"firm"}
    assert {f.entity.role for f in facts} == {"employer"}
