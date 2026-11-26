"""People on Universal Credit by country, age and conditionality regime, for
PolicyEngine/chronicle#420 item 3 (PolicyEngine/uk-young-people-work-review#3 and #7).

Checks the package scripts/build_dwp_uc_people_age_conditionality_package.py writes from
the pinned Stat-Xplore response. Values are re-read from the response with the json
module, and each fact's cell is found from the fact's own period, geography and
dimensions, not from the package's row numbers.
"""

from __future__ import annotations

import hashlib
import json
import runpy
from collections import Counter, defaultdict
from pathlib import Path

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
PACKAGE_ID = "dwp-uc-people-country-age-conditionality-regime-april-2024-may-2026"
DIRECTORY = Path("dwp/uc_people_country_age_conditionality_regime_april_2024_may_2026")
FILENAME = "people_on_uc_by_country_age_conditionality_regime_april_2024_may_2026.json"
DATA = ROOT / "db/data" / DIRECTORY
YEAR = 2026
FACTS = 16510
# (country, age, regime) series that are zero in every month and emit no fact.
ZERO_SERIES = 121
COUNT = "str:count:UC_Monthly:V_F_UC_CASELOAD_FULL"
GB = "K03000001"
COUNTRIES = {"England": "E92000001", "Wales": "W92000004", "Scotland": "S92000003"}
MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}
NOT_AVAILABLE = "Not available prior to April 2015"
TOTAL = "Total"


@pytest.fixture(scope="module")
def built():
    package = load_source_package(ROOT / "packages" / DIRECTORY)
    return package, package.build_facts(YEAR)


def _response() -> dict:
    return json.loads((DATA / FILENAME).read_bytes())


def _period(label: str) -> str:
    name, year = label.split()
    return f"{year}-{MONTHS[name]:02d}"


def _age_value(label: str) -> object:
    """A fact's age filter for a response label: digits are ints, Total is 'all'."""
    if label == TOTAL:
        return "all"
    return int(label) if label.isdigit() else label


def _published_cells() -> dict[tuple, int]:
    """Every response cell, keyed as a fact's period, geography and filters."""
    data = _response()
    labels = [
        [item["labels"][0] for item in field["items"]] for field in data["fields"]
    ]
    months, areas, ages, regimes = labels
    cube = data["cubes"][COUNT]["values"]
    cells = {}
    for m, month in enumerate(months):
        for g, area in enumerate(areas):
            geography = GB if area == TOTAL else COUNTRIES.get(area, area)
            for a, age in enumerate(ages):
                for r, regime in enumerate(regimes):
                    key = (
                        _period(month),
                        geography,
                        _age_value(age),
                        "all" if regime == TOTAL else regime,
                    )
                    cells[key] = cube[m][g][a][r]
    return cells


def _fact_key(fact) -> tuple:
    return (
        fact.period.value,
        fact.geography.id,
        fact.filters["age_bands_and_single_year"],
        fact.filters["conditionality_regime"],
    )


# ---------------------------------------------------------------- registration


def test_package_is_registered():
    assert SOURCE_PACKAGE_ALIASES[PACKAGE_ID] == DIRECTORY
    assert PACKAGE_ID in UK_BUNDLE_SOURCES


def test_package_validates_and_builds_one_fact_per_published_cell(built):
    package, facts = built
    report = validate_source_package(package.package_path, year=YEAR)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["source_record_count"] == len(facts) == FACTS
    assert validate_facts(facts).valid
    keys = Counter(build_semantic_fact_key(fact) for fact in facts)
    assert max(keys.values()) == 1


def test_generator_reproduces_the_committed_package():
    generator = runpy.run_path(
        str(ROOT / "scripts/build_dwp_uc_people_age_conditionality_package.py")
    )
    committed = ROOT / "packages" / DIRECTORY / "source_package.yaml"
    assert generator["build"]() == committed.read_text(encoding="utf-8")


def test_manifest_pins_bytes_and_the_r2_key():
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["source_id"] == "dwp"
    assert manifest["package_id"] == PACKAGE_ID
    ((year, entry),) = manifest["files"].items()
    assert year == YEAR
    content = (DATA / entry["filename"]).read_bytes()
    assert entry["filename"] == FILENAME
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    assert entry["source_url"] == "https://stat-xplore.dwp.gov.uk/webapi/rest/v1/table"
    # `chronicle publish-raw` uploaded the bytes and wrote storage.r2.
    key = f"raw/uk/dwp/{PACKAGE_ID}/{year}/{entry['sha256']}/{FILENAME}"
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }


def test_consumer_contract_is_valid(built):
    _, facts = built
    report = validate_consumer_fact_contract(facts)
    assert report.valid, report.errors[:3]
    assert all(fact.source.raw_r2_uri for fact in facts)


# ---------------------------------------------------------------- the cells


def test_facts_are_the_published_cells_and_only_those(built):
    _, facts = built
    published = _published_cells()
    by_key = {_fact_key(fact): fact for fact in facts}
    assert len(by_key) == len(facts)
    for key, fact in by_key.items():
        assert fact.value == published[key], key
        assert fact.measure.concept == "dwp.uc_people"
        assert fact.measure.unit == "count"
        assert fact.aggregation.method == "sum"
        assert fact.period.type == "month"
        assert (fact.entity.name, fact.entity.role) == (
            "person",
            "universal_credit_claimant",
        )
    # What is not ported: the unknown-residence item, and the series that are zero
    # in every month (DWP's pre-April 2015 regime marker among them).
    series = defaultdict(list)
    for (period, geography, age, regime), value in published.items():
        if geography != "Unknown":
            series[geography, age, regime].append((period, value))
    zero = {key for key, cells in series.items() if not any(v for _, v in cells)}
    assert len(zero) == ZERO_SERIES
    assert {key for key in series if key[2] == NOT_AVAILABLE} <= zero
    expected = {
        (period, *key)
        for key, cells in series.items()
        if key not in zero
        for period, _ in cells
    }
    assert set(by_key) == expected
    assert {fact.geography.id for fact in facts} == {GB, *COUNTRIES.values()}
    assert not any(
        fact.filters["conditionality_regime"] == NOT_AVAILABLE for fact in facts
    )
    assert {fact.period.value for fact in facts} == {
        f"{year}-{month:02d}"
        for year, month in [(2024, m) for m in range(4, 13)]
        + [(2025, m) for m in range(1, 13)]
        + [(2026, m) for m in range(1, 6)]
    }


def test_published_cells_and_the_employment_indicator_totals(built):
    _, facts = built
    by_key = {_fact_key(fact): fact.value for fact in facts}
    # May 2026: Great Britain, every age and regime, and the single years 16 to 24.
    assert by_key["2026-05", GB, "all", "all"] == 8_359_744
    assert [by_key["2026-05", GB, age, "all"] for age in range(16, 25)] == [
        1_644,
        7_510,
        61_470,
        101_423,
        114_215,
        116_016,
        122_978,
        127_764,
        131_481,
    ]
    assert by_key["2026-05", GB, "all", "No work requirements"] == 4_267_212
    assert by_key["2026-05", GB, 18, "Searching for work"] == 38_519
    assert [
        by_key["2024-04", geography, "all", "all"]
        for geography in (GB, *COUNTRIES.values())
    ] == [
        6_677_225,
        5_798_926,
        334_723,
        540_374,
    ]
    # DWP's Great Britain total is the employment indicator package's total, month by
    # month: both are Stat-Xplore's all-people count, unknown residence included.
    other = json.loads(
        (
            ROOT
            / "db/data/dwp/uc_people_employment_indicator_january_2023_may_2026"
            / "people_on_uc_by_employment_indicator_january_2023_may_2026.json"
        ).read_bytes()
    )
    totals = {
        _period(item["labels"][0]): row[-1]
        for item, row in zip(
            other["fields"][0]["items"], other["cubes"][COUNT]["values"]
        )
    }
    ours = {
        key[0]: value for key, value in by_key.items() if key[1:] == (GB, "all", "all")
    }
    assert len(ours) == 26
    assert all(totals[period] == value for period, value in ours.items())


# ---------------------------------------------------------------- parity


def test_regimes_and_ages_add_to_their_totals_within_disclosure_control(built):
    """Stat-Xplore perturbs each cell, so parts and totals differ by a few people."""
    _, facts = built
    by_key = {_fact_key(fact): fact.value for fact in facts}
    regime_sums, age_sums = defaultdict(int), defaultdict(int)
    for (period, geography, age, regime), value in by_key.items():
        if regime != "all":
            regime_sums[period, geography, age] += value
        if age != "all":
            age_sums[period, geography, regime] += value
    worst = {"regimes": 0, "ages": 0}
    for (period, geography, age), parts in regime_sums.items():
        total = by_key[period, geography, age, "all"]
        gap = abs(parts - total)
        worst["regimes"] = max(worst["regimes"], gap)
        if total >= 1_000:
            assert gap <= 0.01 * total, (period, geography, age, parts, total)
    for (period, geography, regime), parts in age_sums.items():
        total = by_key[period, geography, "all", regime]
        gap = abs(parts - total)
        worst["ages"] = max(worst["ages"], gap)
        if total >= 1_000:
            assert gap <= 0.005 * total, (period, geography, regime, parts, total)
    assert worst == {"regimes": 18, "ages": 26}


def test_countries_add_to_great_britain_but_for_unknown_residence():
    """The three countries plus 'Unknown' make DWP's Great Britain total; the unknown
    residence item emits no fact."""
    data = _response()
    cube = data["cubes"][COUNT]["values"]
    areas = [item["labels"][0] for item in data["fields"][1]["items"]]
    assert areas == ["England", "Wales", "Scotland", "Unknown", TOTAL]
    gaps = [
        abs(sum(by_area[:4]) - by_area[4])
        for by_month in cube
        for by_area_age in zip(*by_month)
        for by_area in zip(*by_area_age)
    ]
    assert max(gaps) == 13
    may = cube[-1]
    assert may[4][-1][-1] - sum(may[g][-1][-1] for g in range(3)) == 9_994
    assert may[3][-1][-1] == 9_991


def test_ages_carry_bounds_and_the_open_items_carry_none(built):
    _, facts = built
    bounds_by_age = {}
    for fact in facts:
        age = fact.filters["age_bands_and_single_year"]
        bounds = tuple(
            sorted(
                (c.operator, c.value) for c in fact.constraints if c.variable == "age"
            )
        )
        assert bounds_by_age.setdefault(age, bounds) == bounds, age
    for age in range(16, 25):
        assert bounds_by_age[age] == (("<", age + 1), (">=", age))
    assert bounds_by_age["25-29"] == (("<", 30), (">=", 25))
    assert bounds_by_age["65-70"] == (("<", 71), (">=", 65))
    # 'Over 70' is DWP's 71 to 90; it takes the open top band's lower bound only.
    assert bounds_by_age["Over 70"] == ((">=", 71),)
    for age in ("Unknown/Missing", "all"):
        assert bounds_by_age[age] == ()
