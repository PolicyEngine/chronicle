"""Social Security Scotland caseloads for PolicyEngine/chronicle#420 item 7.

Checks the packages scripts/build_uk_scottish_social_security_packages.py writes from
Social Security Scotland's latest editions: Adult Disability Payment to 31 July 2026,
Carer Support Payment to 30 June 2026, Child Disability Payment to 30 June 2026 and
Pension Age Disability Payment to 31 July 2026. Values are re-read from the pinned
workbooks with openpyxl, and each fact's cell is found from the fact's own type of
client, month, award level, age band or council, not from the package's coordinates.
"""

from __future__ import annotations

import hashlib
import io
import re
import runpy
from collections import Counter
from pathlib import Path

import openpyxl
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
DATA = ROOT / "db/data/scotgov"

PACKAGES = {
    # package id: (package directory, data directory, facts)
    "scotgov-adp-caseload-july-2026": (
        "scotgov/adp_caseload_july_2026",
        "adp_statistics_july_2026",
        1885,
    ),
    "scotgov-carer-support-payment-caseload-june-2026": (
        "scotgov/carer_support_payment_caseload_june_2026",
        "carer_support_payment_statistics_june_2026",
        282,
    ),
    "scotgov-child-disability-payment-caseload-june-2026": (
        "scotgov/child_disability_payment_caseload_june_2026",
        "child_disability_payment_statistics_june_2026",
        81,
    ),
    "scotgov-padp-caseload-july-2026": (
        "scotgov/padp_caseload_july_2026",
        "padp_statistics_july_2026",
        66,
    ),
}
ROUTES = {
    "scotgov-adp-caseload-july-2026": {
        "all": "All",
        "new_applicant": "New Applicant",
        "case_transfer": "Case Transfer",
    },
    "scotgov-carer-support-payment-caseload-june-2026": {
        "all": "All",
        "new_applicant": "New application",
        "case_transfer": "Case transfer",
    },
    "scotgov-child-disability-payment-caseload-june-2026": {
        "all": "All",
        "new_applicant": "New Applicants",
        "case_transfer": "Case Transfers",
    },
    "scotgov-padp-caseload-july-2026": {
        "all": "All",
        "new_applicant": "New applicants",
        "case_transfer": "Case transfers",
    },
}


@pytest.fixture(scope="module")
def built():
    packages = {}
    for package_id in PACKAGES:
        package = load_source_package(package_id)
        packages[package_id] = (package, package.build_facts(2026))
    return packages


def _workbook(data_directory: str):
    manifest = yaml.safe_load((DATA / data_directory / "manifest.yaml").read_text())
    ((_, entry),) = manifest["files"].items()
    content = (DATA / data_directory / entry["filename"]).read_bytes()
    return openpyxl.load_workbook(io.BytesIO(content), data_only=True)


def _squeeze(text: object) -> str:
    return " ".join(str(text).split())


def _monthly(worksheet, header_row: int = 6) -> tuple[dict, dict]:
    """{(type of client, month label): row} and {header text: column} for a long table."""
    headers = {
        _squeeze(cell.value): cell.column
        for cell in worksheet[header_row]
        if cell.value is not None
    }
    rows = {}
    for row in worksheet.iter_rows(min_row=header_row + 1):
        route, month = row[0].value, row[1].value
        if not isinstance(route, str) or route.startswith("[note"):
            break
        rows[(route, month)] = row[0].row
    return rows, headers


def _month_label(fact) -> str:
    return fact.period_coverage.source_period_label


# ---------------------------------------------------------------- registration


def test_packages_validate_register_and_carry_no_anchors(built):
    for package_id, (package, facts) in built.items():
        directory, _, count = PACKAGES[package_id]
        report = validate_source_package(package.package_path, year=2026)
        assert report.valid, report.to_dict()
        assert not report.warnings
        assert report.counts["source_record_count"] == len(facts) == count
        assert SOURCE_PACKAGE_ALIASES[package_id] == Path(directory)
        assert package_id in UK_BUNDLE_SOURCES
        text = (package.package_path / "source_package.yaml").read_text(
            encoding="utf-8"
        )
        assert not re.search(r"(:|^\s*-)\s+[&*][A-Za-z_][\w-]*\s*$", text, re.M)
        assert validate_facts(facts).valid
        keys = Counter(build_semantic_fact_key(fact) for fact in facts)
        assert max(keys.values()) == 1, package_id
        assert len(package.build_facts(2023)) == count


def test_generator_reproduces_the_committed_packages():
    generator = runpy.run_path(
        str(ROOT / "scripts/build_uk_scottish_social_security_packages.py")
    )
    builders = generator["BUILDERS"]
    assert sorted(builders) == sorted(row[0] for row in PACKAGES.values())
    for directory, build in builders.items():
        committed = ROOT / "packages" / directory / "source_package.yaml"
        assert build() == committed.read_text(encoding="utf-8"), directory


@pytest.mark.parametrize("data_directory", [row[1] for row in PACKAGES.values()])
def test_manifests_pin_bytes_licence_and_the_r2_key(data_directory):
    path = DATA / data_directory / "manifest.yaml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert manifest["source_id"] == "scotgov"
    assert manifest["publisher"].startswith("Social Security Scotland")
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-06"
    ((year, entry),) = manifest["files"].items()
    content = (path.parent / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    assert entry["source_url"].startswith(
        "https://www.socialsecurity.gov.scot/binaries/socialsecurity/publications/2026/"
    )
    # `chronicle publish-raw` uploaded the bytes and wrote storage.r2, and
    # `chronicle verify-raw` read each object back.
    key = (
        f"raw/uk/scotgov/{manifest['package_id']}/{year}/{entry['sha256']}/"
        f"{entry['filename']}"
    )
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }


def test_consumer_contract_is_valid(built):
    for package_id, (_, facts) in built.items():
        report = validate_consumer_fact_contract(facts)
        assert report.valid, (package_id, report.errors[:3])
        assert all(fact.source.raw_r2_uri for fact in facts), package_id


# ---------------------------------------------------------------- published cells

ADP_LEVEL_HEADERS = {
    (
        "adp_award_components",
        "daily_living_only",
    ): "Number in receipt of Daily Living Award only",
    (
        "adp_award_components",
        "mobility_only",
    ): "Number in receipt of Mobility award only",
    (
        "adp_award_components",
        "both",
    ): "Number in receipt of both Daily Living and Mobility award",
}
ADP_DL_HEADERS = {
    "enhanced": "Number on Enhanced Daily Living",
    "standard": "Number on Standard Daily Living",
    "transitional": "Number on transitional Daily Living",
    "not_awarded": "Number not awarded",
}
ADP_MOB_HEADERS = {
    "enhanced": "Number on Enhanced Mobility",
    "standard": "Number on Standard Mobility",
    "not_awarded": "Number not awarded",
}
LEVEL_WORDS = {
    "enhanced": "Enhanced",
    "standard": "Standard",
    "transitional": "Transitional",
    "not_awarded": "Not Awarded",
}
ADP_AGES = {
    "16_to_18": "16-18",
    "19_to_24": "19-24",
    "25_to_34": "25-34",
    "35_to_44": "35-44",
    "45_to_54": "45-54",
    "55_to_64": "55-64",
    "65_and_over": "65 and older",
}
CSP_AGES = {
    "under_18": "Under 18",
    "18_to_24": "18-24",
    "25_to_29": "25-29",
    "30_to_34": "30-34",
    "35_to_39": "35-39",
    "40_to_44": "40-44",
    "45_to_49": "45-49",
    "50_to_54": "50-54",
    "55_to_59": "55-59",
    "60_to_64": "60-64",
    "65_and_over": "65 and over",
}


def _snapshot(worksheet) -> dict[str, object]:
    return {
        row[0].value: row[1].value
        for row in worksheet.iter_rows(min_row=7)
        if isinstance(row[0].value, str) and not row[0].value.startswith("[note")
    }


def test_adp_facts_are_the_published_cells(built):
    package_id = "scotgov-adp-caseload-july-2026"
    _, facts = built[package_id]
    workbook = _workbook("adp_statistics_july_2026")
    sheets = {
        name: _monthly(workbook[name])
        for name in (
            "T15 Caseload by award type",
            "T16 Caseload by DL award",
            "T17 Caseload by mob award",
            "T18 Caseload by award level",
        )
    }
    ages = _snapshot(workbook["T19 Caseload by age"])
    councils = {
        _squeeze(name): value
        for name, value in _snapshot(workbook["T25 Caseload by LA"]).items()
    }
    by_sheet = Counter()
    for fact in facts:
        filters = fact.filters
        assert fact.measure.concept == "scotgov.adp_caseload"
        if "age_band" in filters:
            assert fact.period.value == "2026-07"
            assert fact.value == ages[ADP_AGES[filters["age_band"]]]
            by_sheet["T19"] += 1
            continue
        if fact.geography.level == "local_authority":
            assert fact.value == councils[fact.geography.name]
            by_sheet["T25"] += 1
            continue
        living = filters.get("adp_daily_living_award_level")
        mobility = filters.get("adp_mobility_award_level")
        if "adp_award_components" in filters:
            sheet, header = (
                "T15 Caseload by award type",
                ADP_LEVEL_HEADERS[
                    ("adp_award_components", filters["adp_award_components"])
                ],
            )
        elif living and mobility:
            sheet = "T18 Caseload by award level"
            header = (
                f"Mobility {LEVEL_WORDS[mobility]} - Daily Living {LEVEL_WORDS[living]}"
            )
        elif living:
            sheet, header = "T16 Caseload by DL award", ADP_DL_HEADERS[living]
        elif mobility:
            sheet, header = "T17 Caseload by mob award", ADP_MOB_HEADERS[mobility]
        else:
            sheet, header = "T15 Caseload by award type", "Caseload"
        rows, headers = sheets[sheet]
        route = ROUTES[package_id][filters["case_route"]]
        cell = workbook[sheet].cell(rows[(route, _month_label(fact))], headers[header])
        assert fact.value == cell.value, (sheet, route, _month_label(fact), header)
        by_sheet[sheet] += 1
    # 28 months by three types of client: T15's caseload and three award types, T16's
    # four levels, T17's three and T18's eleven, less two [c] cells; 7 ages; 32 councils.
    assert by_sheet == {
        "T15 Caseload by award type": 28 * 3 * 4,
        "T16 Caseload by DL award": 28 * 3 * 4,
        "T17 Caseload by mob award": 28 * 3 * 3,
        "T18 Caseload by award level": 28 * 3 * 11 - 2,
        "T19": 7,
        "T25": 32,
    }
    (latest,) = [
        fact.value
        for fact in facts
        if fact.period.value == "2026-07"
        and fact.filters == {"case_route": "all"}
        and fact.geography.id == "S92000003"
    ]
    assert latest == 510_150


def test_carer_support_payment_facts_are_the_published_cells(built):
    package_id = "scotgov-carer-support-payment-caseload-june-2026"
    _, facts = built[package_id]
    workbook = _workbook("carer_support_payment_statistics_june_2026")
    rows, headers = _monthly(workbook["Table 9 Caseload"])
    ages = _snapshot(workbook["Table 11 Caseload by age"])
    councils = {
        _squeeze(name): value
        for name, value in _snapshot(workbook["Table 10 Caseload by LA"]).items()
    }
    status_headers = {
        None: "Total Caseload",
        "in_payment": "In Payment",
        "underlying_entitlement": "Underlying entitlement",
    }
    counts = Counter()
    for fact in facts:
        filters = fact.filters
        if "age_band" in filters:
            assert fact.value == ages[CSP_AGES[filters["age_band"]]]
            counts["age"] += 1
        elif fact.geography.level == "local_authority":
            assert fact.value == councils[fact.geography.name]
            counts["council"] += 1
        else:
            header = status_headers[filters.get("carer_support_payment_status")]
            route = ROUTES[package_id][filters["case_route"]]
            row = rows[(route, _month_label(fact))]
            cell = workbook["Table 9 Caseload"].cell(row, headers[header])
            assert fact.value == cell.value
            counts["monthly"] += 1
    # 27 months by three types of client and three columns, less four [c] cells.
    assert counts == {"monthly": 27 * 3 * 3 - 4, "age": 11, "council": 32}


@pytest.mark.parametrize(
    ("package_id", "data_directory", "sheet", "header", "first", "last", "latest"),
    [
        (
            "scotgov-child-disability-payment-caseload-june-2026",
            "child_disability_payment_statistics_june_2026",
            "T14 Caseload by award type",
            "Total number of children in receipt [note 4] [note 6]",
            "2024-04",
            "2026-06",
            104_185,
        ),
        (
            "scotgov-padp-caseload-july-2026",
            "padp_statistics_july_2026",
            "T13 Caseload by award level",
            "Caseload",
            "2024-10",
            "2026-07",
            186_390,
        ),
    ],
)
def test_child_and_pension_age_totals_are_the_published_cells(
    built, package_id, data_directory, sheet, header, first, last, latest
):
    _, facts = built[package_id]
    workbook = _workbook(data_directory)
    rows, headers = _monthly(workbook[sheet])
    for fact in facts:
        route = ROUTES[package_id][fact.filters["case_route"]]
        cell = workbook[sheet].cell(rows[(route, _month_label(fact))], headers[header])
        assert fact.value == cell.value
    months = sorted({fact.period.value for fact in facts})
    assert months[0] == first and months[-1] == last
    assert len(facts) == 3 * len(months)
    (value,) = [
        fact.value
        for fact in facts
        if fact.period.value == last and fact.filters["case_route"] == "all"
    ]
    assert value == latest


# ---------------------------------------------------------------- parity


def _by(facts, *keys):
    index = {}
    for fact in facts:
        if fact.geography.id != "S92000003" or "age_band" in fact.filters:
            continue
        key = tuple(fact.filters.get(k) for k in keys) + (fact.period.value,)
        index[key] = fact.value
    return index


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_types_of_client_add_to_all_clients(built, package_id):
    _, facts = built[package_id]
    other = [
        k
        for k in (
            "adp_award_components",
            "adp_daily_living_award_level",
            "adp_mobility_award_level",
            "carer_support_payment_status",
        )
    ]
    index = _by(facts, "case_route", *other)
    checked = 0
    for (route, *rest), value in index.items():
        if route != "all":
            continue
        parts = [
            index.get(("new_applicant", *rest)),
            index.get(("case_transfer", *rest)),
        ]
        if None in parts:
            continue  # a suppressed part
        assert abs(sum(parts) - value) <= 10, (package_id, rest)
        checked += 1
    assert checked


def test_adp_levels_ages_and_councils_add_up(built):
    _, facts = built["scotgov-adp-caseload-july-2026"]
    caseload = {
        (f.filters["case_route"], f.period.value): f.value
        for f in facts
        if set(f.filters) == {"case_route"} and f.geography.id == "S92000003"
    }
    living = Counter()
    mobility = Counter()
    for f in facts:
        keys = set(f.filters)
        if keys == {"case_route", "adp_daily_living_award_level"}:
            living[(f.filters["case_route"], f.period.value)] += f.value
        elif keys == {"case_route", "adp_mobility_award_level"}:
            mobility[(f.filters["case_route"], f.period.value)] += f.value
    for key, value in caseload.items():
        assert abs(living[key] - value) <= 15, key
        assert abs(mobility[key] - value) <= 15, key
    july = caseload[("all", "2026-07")]
    ages = sum(f.value for f in facts if "age_band" in f.filters)
    councils = sum(f.value for f in facts if f.geography.level == "local_authority")
    assert abs(ages - july) <= 15
    # Table 25's 'Other' row (1,420: postcodes that match no council) has no code.
    assert july - councils == 1_420
