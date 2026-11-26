"""UK PIP cases with entitlement for PolicyEngine/chronicle#420 item 6.

Checks the packages scripts/build_dwp_pip_cases_packages.py writes from DWP Stat-Xplore's
'PIP Cases with Entitlement from 2019' (PIP_Monthly_new), extracted 6 November 2026: cases
by country, daily living and mobility award and age band; by country, End of Life Rules
indicator and award; by country, disability category and award; by English region and
award, each quarter-end month from January 2024 to July 2026; and by constituency and
local authority at July 2026. Values are re-read from the pinned responses with the json
module, and each fact's cell is found from the fact's own period, geography and filters,
not from the package's coordinates.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
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
DATA = ROOT / "db/data/dwp"
WINDOW = "january_2024_july_2026"

AWARD_AGE = "dwp-pip-cases-country-award-age-january-2024-july-2026"
RULES = "dwp-pip-cases-country-end-of-life-rules-award-january-2024-july-2026"
DISABILITY = "dwp-pip-cases-country-disability-award-january-2024-july-2026"
REGION = "dwp-pip-cases-region-award-january-2024-july-2026"
CONSTITUENCY = "dwp-pip-cases-by-constituency-july-2026"
LOCAL_AUTHORITY = "dwp-pip-cases-by-local-authority-july-2026"

PACKAGES = {
    # package id: (directory stem, the filter keys in the response's field order, facts)
    AWARD_AGE: (
        f"pip_cases_country_award_age_{WINDOW}",
        (
            "daily_living_award_status",
            "mobility_award_status",
            "age_bands_and_single_year",
        ),
        7997,
    ),
    RULES: (
        f"pip_cases_country_end_of_life_rules_award_{WINDOW}",
        (
            "end_of_life_rules_indicator",
            "daily_living_award_status",
            "mobility_award_status",
        ),
        1078,
    ),
    DISABILITY: (
        f"pip_cases_country_disability_award_{WINDOW}",
        ("disability", "daily_living_award_status", "mobility_award_status"),
        10769,
    ),
    REGION: (
        f"pip_cases_region_award_{WINDOW}",
        ("daily_living_award_status", "mobility_award_status"),
        1881,
    ),
    CONSTITUENCY: ("pip_cases_by_constituency_july_2026", (), 632),
    LOCAL_AUTHORITY: ("pip_cases_by_local_authority_july_2026", (), 350),
}
MONTHLY = (AWARD_AGE, RULES, DISABILITY, REGION)
AREAS = {CONSTITUENCY: "constituency", LOCAL_AUTHORITY: "local_authority"}
MONTHS = {
    f"{year}-{month:02d}": f"{name}-{str(year)[2:]}"
    for year in (2024, 2025, 2026)
    for month, name in ((1, "Jan"), (4, "Apr"), (7, "Jul"), (10, "Oct"))
    if (year, month) <= (2026, 7)
}
NOT_AREAS = ("XXZZZZZZZ", "ZZXXXXXXX")  # Abroad and Unknown: no GSS code, no fact
ENGLAND, WALES, SCOTLAND = "E92000001", "W92000004", "S92000003"
REGIONS = tuple(f"E1200000{index}" for index in range(1, 10))


def _tolerance(parts: int) -> int:
    """Stat-Xplore adjusts every cell slightly, so parts and totals agree only within it."""
    return 3 * parts + 10


@pytest.fixture(scope="module")
def built():
    packages = {}
    for package_id in PACKAGES:
        package = load_source_package(package_id)
        packages[package_id] = (package, package.build_facts(2026))
    return packages


def _response(package_id: str) -> dict:
    stem = PACKAGES[package_id][0]
    return json.loads((DATA / stem / f"{stem}.json").read_bytes().decode("utf-8"))


def _cells(package_id: str) -> dict[tuple, int]:
    """Every cube cell by (month label, area code, *item labels), read with json only."""
    data = _response(package_id)
    axes = []
    for index, field in enumerate(data["fields"]):
        items = []
        for item in field["items"]:
            label = item["labels"][0]
            if index == 1:  # geography: the GSS code ends the item's value URI
                label = item["uris"][0].rsplit(":", 1)[1]
            items.append(label)
        axes.append(items)
    ((_, cube),) = data["cubes"].items()
    cells = {}
    for index in itertools.product(*(range(len(axis)) for axis in axes)):
        node = cube["values"]
        for position in index:
            node = node[position]
        cells[tuple(axis[i] for axis, i in zip(axes, index))] = node
    return cells


def _key(package_id: str, fact) -> tuple:
    keys = PACKAGES[package_id][1]
    labels = tuple(
        "Total" if fact.filters[key] == "all" else fact.filters[key] for key in keys
    )
    return (MONTHS[fact.period.value], fact.geography.id, *labels)


def _value(facts, package_id, period, geography, **filters):
    keys = PACKAGES[package_id][1]
    wanted = {key: filters.get(key, "all") for key in keys}
    matches = [
        fact
        for fact in facts
        if fact.period.value == period
        and fact.geography.id == geography
        and all(fact.filters.get(key) == value for key, value in wanted.items())
    ]
    assert len(matches) == 1, (package_id, period, geography, filters, len(matches))
    return matches[0].value


# ---------------------------------------------------------------- registration


def test_packages_validate_register_and_build(built):
    every = []
    for package_id, (package, facts) in built.items():
        stem, _, count = PACKAGES[package_id]
        report = validate_source_package(package.package_path, year=2026)
        assert report.valid, report.to_dict()
        assert not report.warnings
        assert report.counts["source_record_count"] == len(facts) == count
        relative = package.package_path.relative_to(ROOT / "packages")
        assert SOURCE_PACKAGE_ALIASES[package_id] == relative == Path("dwp") / stem
        assert package_id in UK_BUNDLE_SOURCES
        assert validate_facts(facts).valid
        assert {fact.measure.concept for fact in facts} == {
            "dwp.pip_cases_with_entitlement"
        }
        assert {fact.provenance_class for fact in facts} == {"administrative"}
        assert {fact.period.type for fact in facts} == {"month"}
        every += facts
    # No fact is stated twice: the rules and disability fields request no total, so
    # their all-rules and all-conditions margins are the award-and-age package's.
    keys = Counter(build_semantic_fact_key(fact) for fact in every)
    assert max(keys.values()) == 1
    assert len(every) == sum(row[-1] for row in PACKAGES.values())


def test_generator_reproduces_the_committed_packages():
    generator = runpy.run_path(str(ROOT / "scripts/build_dwp_pip_cases_packages.py"))
    builders = generator["BUILDERS"]
    assert sorted(builders) == sorted(f"dwp/{row[0]}" for row in PACKAGES.values())
    for directory, build in builders.items():
        committed = ROOT / "packages" / directory / "source_package.yaml"
        assert build() == committed.read_text(encoding="utf-8"), directory


def test_manifests_pin_bytes_licence_and_the_r2_key():
    for package_id, (stem, _, _) in PACKAGES.items():
        manifest = yaml.safe_load((DATA / stem / "manifest.yaml").read_text())
        assert manifest["source_id"] == "dwp"
        assert manifest["package_id"] == package_id
        assert manifest["license"] == "Open Government Licence v3.0"
        assert manifest["license_verified_at"] == "2026-11-06"
        ((year, entry),) = manifest["files"].items()
        assert year == 2026 and entry["filename"] == f"{stem}.json"
        content = (DATA / stem / entry["filename"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]
        assert len(content) == entry["size_bytes"]
        assert (
            entry["source_url"] == "https://stat-xplore.dwp.gov.uk/webapi/rest/v1/table"
        )
        assert entry["fetched_at"].startswith("2026-11-06T")
        # `chronicle publish-raw` uploaded the bytes and wrote storage.r2.
        key = f"raw/uk/dwp/{package_id}/2026/{entry['sha256']}/{entry['filename']}"
        assert entry["storage"]["r2"] == {
            "provider": "r2",
            "bucket": "ledger-raw",
            "key": key,
            "uri": f"r2://ledger-raw/{key}",
        }
        # The response echoes the query: one database, one count measure.
        data = json.loads(content.decode("utf-8"))
        assert data["query"]["database"] == "str:database:PIP_Monthly_new"
        assert data["query"]["measures"] == [
            "str:count:PIP_Monthly_new:V_F_PIP_MONTHLY"
        ]


def test_consumer_contract_is_valid(built):
    for package_id, (_, facts) in built.items():
        report = validate_consumer_fact_contract(facts)
        assert report.valid, (package_id, report.errors[:3])
        assert all(fact.source.raw_r2_uri for fact in facts), package_id


# ---------------------------------------------------------------- the cells


def test_monthly_facts_are_the_published_cells_and_only_those(built):
    for package_id in MONTHLY:
        _, facts = built[package_id]
        cells = _cells(package_id)
        seen = set()
        for fact in facts:
            key = _key(package_id, fact)
            assert fact.value == cells[key], (package_id, key)
            assert key not in seen
            seen.add(key)
        # A series is every month of one area and item combination. One that is zero
        # in every month is not ported; a published zero inside a kept series is.
        series = defaultdict(list)
        for key, value in cells.items():
            series[key[1:]].append(value)
        kept = {key for key in cells if any(value != 0 for value in series[key[1:]])}
        assert seen == kept, package_id
        assert {key[0] for key in seen} == set(MONTHS.values())


def test_area_facts_are_every_area_but_abroad_and_unknown(built):
    for package_id, level in AREAS.items():
        _, facts = built[package_id]
        cells = _cells(package_id)
        assert {key[0] for key in cells} == {"Jul-26"}
        published = {key[1]: value for key, value in cells.items()}
        assert {code for code in published if code in NOT_AREAS} == set(NOT_AREAS)
        assert {fact.geography.id: fact.value for fact in facts} == {
            code: value for code, value in published.items() if code not in NOT_AREAS
        }
        assert {fact.geography.level for fact in facts} == {level}
        assert {fact.period.value for fact in facts} == {"2026-07"}
        assert all(not fact.filters for fact in facts)


def test_rules_and_disability_carry_no_all_margin(built):
    for package_id, key in (
        (RULES, "end_of_life_rules_indicator"),
        (DISABILITY, "disability"),
    ):
        _, facts = built[package_id]
        assert all(fact.filters[key] != "all" for fact in facts), package_id
    rules = {fact.filters["end_of_life_rules_indicator"] for fact in built[RULES][1]}
    # 'Missing or Unknown' is zero in every month, so its series are not ported.
    assert rules == {"Normal Rules", "SREL"}


def test_age_bands_carry_age_bounds(built):
    _, facts = built[AWARD_AGE]
    bounds = defaultdict(set)
    for fact in facts:
        band = fact.filters["age_bands_and_single_year"]
        bounds[band].add(
            tuple(
                sorted(
                    (c.operator, c.value)
                    for c in fact.constraints
                    if c.variable == "age"
                )
            )
        )
    assert bounds["16-19"] == {(("<", 20), (">=", 16))}
    assert bounds["65-69"] == {(("<", 70), (">=", 65))}
    assert bounds["all"] == {()}
    for band, values in bounds.items():
        if band == "all":
            continue
        low, high = (int(part) for part in re.fullmatch(r"(\d+)-(\d+)", band).groups())
        assert values == {(("<", high + 1), (">=", low))}, band


# ---------------------------------------------------------------- parity


def test_awards_and_ages_add_to_their_totals(built):
    """Each field's items add to its Total, within Stat-Xplore's cell adjustment."""
    for package_id in MONTHLY:
        cells = _cells(package_id)
        checked = 0
        for position in range(2, 2 + len(PACKAGES[package_id][1])):
            parts = defaultdict(list)
            totals = {}
            for key, value in cells.items():
                rest = key[:position] + key[position + 1 :]
                if key[position] == "Total":
                    totals[rest] = value
                else:
                    parts[rest].append(value)
            if not totals:
                continue  # the rules and disability fields request no total
            assert set(totals) == set(parts), (package_id, position)
            for rest, total in totals.items():
                values = parts[rest]
                assert abs(sum(values) - total) <= _tolerance(len(values)), (
                    package_id,
                    position,
                    rest,
                    sum(values),
                    total,
                )
                checked += 1
        assert checked, package_id


def test_regions_add_to_england(built):
    _, award_age = built[AWARD_AGE]
    _, regions = built[REGION]
    for period in MONTHS:
        england = _value(award_age, AWARD_AGE, period, ENGLAND)
        parts = [_value(regions, REGION, period, code) for code in REGIONS]
        assert abs(sum(parts) - england) <= _tolerance(len(parts)), period
    # July 2026: the nine regions add to 3,788,676 against England's 3,788,671.
    assert (
        sum(_value(regions, REGION, "2026-07", code) for code in REGIONS) == 3_788_676
    )


def test_areas_add_to_the_countries_at_july_2026(built):
    _, award_age = built[AWARD_AGE]
    countries = {
        code: _value(award_age, AWARD_AGE, "2026-07", code)
        for code in (ENGLAND, WALES, SCOTLAND)
    }
    assert countries == {ENGLAND: 3_788_671, WALES: 296_847, SCOTLAND: 919}
    for package_id in AREAS:
        _, facts = built[package_id]
        by_country = defaultdict(list)
        for fact in facts:
            by_country[fact.geography.id[0]].append(fact.value)
        for code, total in countries.items():
            parts = by_country[code[0]]
            gap = sum(parts) - total
            assert abs(gap) <= _tolerance(len(parts)), (package_id, code, gap)
            if code != SCOTLAND:
                assert abs(gap) / total < 1e-4, (package_id, code, gap)


def test_july_2026_matches_the_release_headlines(built):
    """'4.1 million claimants entitled to PIP' in England and Wales at 31 July 2026, '35,000
    (1%)' under SREL and '37% received the highest level of award' (PIP statistics to July
    2026, which add the few cases abroad or of unknown residence to England and Wales)."""
    _, award_age = built[AWARD_AGE]
    _, rules = built[RULES]
    both = (ENGLAND, WALES)
    caseload = sum(_value(award_age, AWARD_AGE, "2026-07", code) for code in both)
    assert caseload == 4_085_518 and round(caseload / 1e5) / 10 == 4.1
    srel = sum(
        _value(rules, RULES, "2026-07", code, end_of_life_rules_indicator="SREL")
        for code in both
    )
    assert srel == 34_869 and round(srel, -3) == 35_000
    highest = sum(
        _value(
            award_age,
            AWARD_AGE,
            "2026-07",
            code,
            daily_living_award_status="Daily Living - Enhanced",
            mobility_award_status="Mobility Award - Enhanced",
        )
        for code in both
    )
    assert round(100 * highest / caseload) == 37


def test_scotland_falls_as_cases_move_to_adult_disability_payment(built):
    _, facts = built[AWARD_AGE]
    scotland = [_value(facts, AWARD_AGE, period, SCOTLAND) for period in MONTHS]
    assert scotland[0] == 218_589 and scotland[-1] == 919
    assert scotland == sorted(scotland, reverse=True)
    # Social Security Scotland completed the case transfer by the end of June 2025.
    assert _value(facts, AWARD_AGE, "2025-04", SCOTLAND) < 3_000
