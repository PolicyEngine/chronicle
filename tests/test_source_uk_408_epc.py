"""Source packages for PolicyEngine/chronicle#408 item 7.

MHCLG's EPC live table D3 (domestic certificates lodged, floor area and habitable rooms,
by quarter and year, for England and Wales, each nation, region and local authority) and
Live Table 126 (dwelling stock density by local authority district, 2011 to 2025).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from functools import cache
import hashlib
from pathlib import Path

import pandas as pd
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
D3 = "mhclg-epc-d3-domestic-2026-q3"
LT126 = "mhclg-live-table-126-dwelling-density-2026"
# package id -> (artifact year, record sets, facts)
PACKAGES = {D3: (2026, 411, 75051), LT126: (2026, 15, 5406)}
D3_CONCEPTS = (
    "mhclg.epc_domestic_lodgements",
    "mhclg.epc_domestic_total_floor_area",
    "mhclg.epc_domestic_habitable_rooms",
)
NATIONS = {
    "D3_England_and_Wales": "K04000001",
    "D3_England_Only": "E92000001",
    "D3_Wales_Only": "W92000004",
}
REGIONS = {
    "North East": "E12000001",
    "North West": "E12000002",
    "Yorkshire and The Humber": "E12000003",
    "East Midlands": "E12000004",
    "West Midlands": "E12000005",
    "East of England": "E12000006",
    "London": "E12000007",
    "South East": "E12000008",
    "South West": "E12000009",
}
UNKNOWN = "mhclg-epc-d3:england-area-unknown"


@cache
def _facts(package_id: str) -> tuple:
    return tuple(load_source_package(package_id).build_facts(PACKAGES[package_id][0]))


def _artifact(package_id: str) -> Path:
    data_dir = DATA / SOURCE_PACKAGE_ALIASES[package_id]
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text(encoding="utf-8"))
    (entry,) = manifest["files"].values()
    return data_dir / entry["filename"]


@cache
def _sheets(package_id: str) -> dict[str, pd.DataFrame]:
    """An independent parse (pandas with odfpy); frame row i is sheet row i + 1."""
    return pd.read_excel(
        _artifact(package_id), engine="odf", sheet_name=None, header=None
    )


def _period(label: object) -> tuple[str, object]:
    if isinstance(label, str) and "/" in label:
        year, quarter = label.split("/")
        return ("quarter", f"{year}-Q{quarter}")
    return ("calendar_year", int(label))


def _fact_key(fact) -> tuple:
    return (
        fact.geography.id,
        (fact.period.type, fact.period.value),
        fact.measure.concept,
    )


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
    built = list(_facts(package_id))
    assert len(built) == count
    assert validate_facts(built).valid
    assert max(Counter(build_semantic_fact_key(fact) for fact in built).values()) == 1
    assert validate_consumer_fact_contract(built).valid


@pytest.mark.parametrize(
    ("package_id", "sha256", "size"),
    [
        (
            D3,
            "834b564e838681fe786b2dbc04d92453e23dfb96011f11f89783a88308a062be",
            4506479,
        ),
        (
            LT126,
            "6d74dde0004a6f058121559dd66089ef239813abbe69d48bc45892606410fadb",
            90471,
        ),
    ],
)
def test_manifests_pin_bytes_and_licence(package_id, sha256, size):
    data_dir = DATA / SOURCE_PACKAGE_ALIASES[package_id]
    manifest = yaml.safe_load((data_dir / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["package_id"] == package_id
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-04"
    (entry,) = manifest["files"].values()
    content = (data_dir / entry["filename"]).read_bytes()
    assert entry["sha256"] == sha256 == hashlib.sha256(content).hexdigest()
    assert entry["size_bytes"] == size == len(content)


def _d3_national(sheet: str) -> dict[tuple, tuple[int, int, int]]:
    """Each year and quarter row of a national sheet; '(Total)' is checked apart."""
    frame = _sheets(D3)[sheet]
    assert list(frame.iloc[3, :5]) == [
        "Year",
        "Quarter",
        "Number Lodgements",
        "Total Floor Area (m2)",
        "Number Habitable Rooms",
    ]
    found = {}
    for _, row in frame.iloc[4:].iterrows():
        if row[0] == "(Total)":
            continue
        label = row[1] if isinstance(row[1], str) else row[0]
        found[_period(label)] = tuple(int(value) for value in row[2:5])
    return found


def _d3_expected() -> dict[tuple, int]:
    expected = {}
    for sheet, code in NATIONS.items():
        for period, values in _d3_national(sheet).items():
            for concept, value in zip(D3_CONCEPTS, values):
                expected[(code, period, concept)] = value
    for _, row in _sheets(D3)["D3_by_Region"].iloc[4:].iterrows():
        if not isinstance(row[1], str):
            continue  # each region's all-period row
        code = UNKNOWN if row[0] == "Unknown" else REGIONS[row[0]]
        for concept, value in zip(D3_CONCEPTS, row[2:5]):
            expected[(code, _period(row[1]), concept)] = int(value)
    for _, row in _sheets(D3)["D3_by_LA"].iloc[4:].iterrows():
        if row[1] == "Unknown":
            continue  # restates D3_by_Region's 'Unknown' rows
        for concept, value in zip(D3_CONCEPTS, row[3:6]):
            key = (row[1], _period(row[2]), concept)
            assert key not in expected
            expected[key] = int(value)
    return expected


def test_d3_facts_are_the_workbook_cells():
    facts = {_fact_key(fact): fact.value for fact in _facts(D3)}
    assert facts == _d3_expected()
    units = Counter((fact.measure.concept, fact.measure.unit) for fact in _facts(D3))
    assert set(units) == {
        ("mhclg.epc_domestic_lodgements", "count"),
        ("mhclg.epc_domestic_total_floor_area", "square_metres"),
        ("mhclg.epc_domestic_habitable_rooms", "count"),
    }
    assert {fact.provenance_class for fact in _facts(D3)} == {"administrative"}
    assert {(fact.entity.name, fact.entity.role) for fact in _facts(D3)} == {
        ("dwelling", "domestic_epc_lodgement")
    }


def test_d3_quarters_cover_2008_q4_to_2026_q3_and_years_2009_to_2025():
    periods = Counter(
        (fact.period.type, fact.period.value)
        for fact in _facts(D3)
        if fact.geography.id == "K04000001"
    )
    quarters = sorted(value for kind, value in periods if kind == "quarter")
    years = sorted(value for kind, value in periods if kind == "calendar_year")
    assert len(quarters) == 72
    assert (quarters[0], quarters[-1]) == ("2008-Q4", "2026-Q3")
    assert years == list(range(2009, 2026))
    fact = next(f for f in _facts(D3) if f.period.value == "2026-Q3")
    assert (fact.period_coverage.start_date, fact.period_coverage.end_date) == (
        "2026-07-01",
        "2026-09-30",
    )


def test_d3_years_and_total_sum_the_quarters():
    for sheet in NATIONS:
        found = _d3_national(sheet)
        sums = defaultdict(lambda: [0, 0, 0])
        for (kind, value), values in found.items():
            if kind == "quarter":
                for index, number in enumerate(values):
                    sums[int(value[:4])][index] += number
        for (kind, value), values in found.items():
            if kind == "calendar_year":
                assert list(values) == sums[value], (sheet, value)
        frame = _sheets(D3)[sheet]
        total = [int(v) for v in frame.iloc[4, 2:5]]
        assert frame.iloc[4, 0] == "(Total)"
        assert total == [
            sum(
                values[index]
                for (kind, _), values in found.items()
                if kind == "quarter"
            )
            for index in range(3)
        ]


def _differences(left: dict, right: dict) -> dict[tuple, tuple[int, int, int]]:
    return {
        key: tuple(a - b for a, b in zip(left[key], right[key]))
        for key in left
        if tuple(left[key]) != tuple(right[key])
    }


def test_d3_nations_add_up_and_floor_area_rounds():
    """England + Wales = England and Wales, except floor area by 1 m² in 2009 and 2009/2."""
    ew, england, wales = (_d3_national(sheet) for sheet in NATIONS)
    added = {key: [a + b for a, b in zip(england[key], wales[key])] for key in ew}
    assert _differences(ew, added) == {
        ("calendar_year", 2009): (0, -1, 0),
        ("quarter", "2009-Q2"): (0, -1, 0),
    }


def _d3_area_sums(
    sheet: str, area: int, first: int
) -> dict[str, dict[tuple, list[int]]]:
    """Per quarter, the sums of a sheet's areas by nation (the 'Unknown' rows in England)."""
    sums: dict[str, dict] = {
        "E": defaultdict(lambda: [0, 0, 0]),
        "W": defaultdict(lambda: [0, 0, 0]),
    }
    for _, row in _sheets(D3)[sheet].iloc[4:].iterrows():
        quarter = row[area + 1]
        if not isinstance(quarter, str):
            continue
        nation = "W" if str(row[area]).startswith("W06") else "E"
        for index, value in enumerate(row[first : first + 3]):
            sums[nation][_period(quarter)][index] += int(value)
    return sums


def test_d3_regions_and_authorities_add_up_to_the_nations():
    """Counts and rooms add up exactly; floor area differs by a few m² to 2012 Q1."""
    england, wales = _d3_national("D3_England_Only"), _d3_national("D3_Wales_Only")
    regions = _d3_area_sums("D3_by_Region", 0, 2)["E"]
    regions_gap = _differences({key: england[key] for key in regions}, regions)
    assert all(gap[0] == gap[2] == 0 for gap in regions_gap.values())
    assert (len(regions_gap), max(abs(gap[1]) for gap in regions_gap.values())) == (
        10,
        2,
    )
    authorities = _d3_area_sums("D3_by_LA", 1, 3)
    england_gap = _differences(
        {key: england[key] for key in authorities["E"]}, authorities["E"]
    )
    wales_gap = _differences(
        {key: wales[key] for key in authorities["W"]}, authorities["W"]
    )
    for gaps, count, largest in ((england_gap, 13, 11), (wales_gap, 11, 3)):
        assert all(gap[0] == gap[2] == 0 for gap in gaps.values())
        assert (len(gaps), max(abs(gap[1]) for gap in gaps.values())) == (
            count,
            largest,
        )
    late = [
        key for key in (*regions_gap, *england_gap, *wales_gap) if key[1] > "2012-Q1"
    ]
    assert not late


def test_d3_unknown_rows_are_ported_once():
    regions = _sheets(D3)["D3_by_Region"].iloc[4:]
    authorities = _sheets(D3)["D3_by_LA"].iloc[4:]
    by_region = {
        row[1]: tuple(row[2:5])
        for _, row in regions.iterrows()
        if row[0] == "Unknown" and isinstance(row[1], str)
    }
    by_authority = {
        row[2]: tuple(row[3:6])
        for _, row in authorities.iterrows()
        if row[1] == "Unknown"
    }
    assert by_region == by_authority and len(by_region) == 62
    unknown = [fact for fact in _facts(D3) if fact.geography.id == UNKNOWN]
    assert len(unknown) == 3 * 62
    assert {fact.geography.level for fact in unknown} == {"statistical_scope"}


def test_d3_barnsley_and_sheffield_switch_codes_in_2025_q4():
    quarters = defaultdict(set)
    vintages = defaultdict(set)
    for fact in _facts(D3):
        if fact.geography.level == "local_authority":
            quarters[fact.geography.id].add(fact.period.value)
            vintages[fact.geography.id].add(fact.geography.vintage)
    for old, new in (("E08000016", "E08000038"), ("E08000019", "E08000039")):
        assert (min(quarters[old]), max(quarters[old])) == ("2008-Q4", "2025-Q4")
        assert sorted(quarters[new]) == ["2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"]
        assert (vintages[old], vintages[new]) == ({"lad_2024"}, {"lad_2025"})
    names = defaultdict(set)
    for _, row in _sheets(D3)["D3_by_LA"].iloc[4:].iterrows():
        names[row[0]].add(row[1])
    assert {name for name, codes in names.items() if len(codes) > 1} == {
        "Barnsley",
        "Sheffield",
    }


def test_d3_retired_codes_stop_where_their_vintage_says():
    """A code retired on 1 April of year Y + 1 carries lad_Y and prints to Y + 1 Q1."""
    last = defaultdict(str)
    vintage = {}
    for fact in _facts(D3):
        if fact.geography.level == "local_authority":
            last[fact.geography.id] = max(last[fact.geography.id], fact.period.value)
            vintage[fact.geography.id] = fact.geography.vintage
    for code, final in last.items():
        if final == "2026-Q3":
            assert vintage[code] == (
                "lad_2025" if code in {"E08000038", "E08000039"} else "lad_2024"
            )
        elif code in {"E08000016", "E08000019"}:
            assert vintage[code] == "lad_2024"
        else:
            year = int(vintage[code].removeprefix("lad_"))
            assert final == f"{year + 1}-Q1", (code, final, vintage[code])


def _lt126_frame() -> pd.DataFrame:
    frame = _sheets(LT126)["LT_126"]
    assert list(frame.iloc[4, :3]) == ["Old ONS code", "New ONS code", "Area"]
    return frame


def _lt126_expected() -> dict[tuple, float]:
    frame = _lt126_frame()
    years = [int(str(header)[:4]) for header in frame.iloc[4, 3:18]]
    assert years == list(range(2011, 2026))
    expected: dict[tuple, float] = {}
    for _, row in frame.iloc[5:].iterrows():
        for year, value in zip(years, row[3:18]):
            if value == "[x]":
                continue
            key = (row[1], ("calendar_year", year), "mhclg.dwelling_stock_density")
            assert expected.setdefault(key, float(value)) == float(value), key
    return expected


def test_lt126_facts_are_the_printed_cells():
    facts = {_fact_key(fact): fact.value for fact in _facts(LT126)}
    assert facts == _lt126_expected()
    assert {fact.measure.unit for fact in _facts(LT126)} == {"dwellings_per_hectare"}
    england = [fact for fact in _facts(LT126) if fact.geography.id == "E92000001"]
    assert sorted(fact.period.value for fact in england) == list(range(2011, 2026))
    fact = england[0]
    assert (fact.period_coverage.start_date, fact.period_coverage.end_date) == (
        f"{fact.period.value}-03-31",
        f"{fact.period.value}-03-31",
    )


def test_lt126_repeated_codes_are_ported_once_from_the_fullest_row():
    frame = _lt126_frame()
    rows = defaultdict(list)
    for index, row in frame.iloc[5:].iterrows():
        rows[row[1]].append(index + 1)
    assert {code: found for code, found in rows.items() if len(found) > 1} == {
        "E06000063": [27, 28],
        "E06000064": [29, 30],
        "E06000065": [74, 75],
        "E10000029": [223, 224],
    }
    package = yaml.safe_load(
        (
            ROOT / "packages" / SOURCE_PACKAGE_ALIASES[LT126] / "source_package.yaml"
        ).read_text()
    )
    used = {
        row["geography_id"]: row["row_number"]
        for record_set in package["record_sets"]
        for row in record_set["rows"]
    }
    assert [
        used[code] for code in ("E06000063", "E06000064", "E06000065", "E10000029")
    ] == [
        27,
        29,
        74,
        224,
    ]
    # Suffolk's first row lacks only its 2023 value.
    assert frame.iloc[222, 15] == "[x]" and frame.iloc[223, 15] != "[x]"


def test_lt126_markers_stay_in_the_headers_and_labels():
    package = yaml.safe_load(
        (
            ROOT / "packages" / SOURCE_PACKAGE_ALIASES[LT126] / "source_package.yaml"
        ).read_text()
    )
    headers = {
        record_set["period"]: record_set["measures"][0]["expected_column_header"]
        for record_set in package["record_sets"]
    }
    assert headers[2020] == "2020 [note 2]"
    assert headers[2022] == "2022 [p] [note 4]"
    assert headers[2024] == "2024 [r] [p]"
    assert headers[2025] == "2025 [p]"
    labels = {
        record_set["period"]: record_set["measures"][0]["label"]
        for record_set in package["record_sets"]
    }
    assert "[r] [p]" in labels[2024] and "[p]" in labels[2025]


def test_lt126_geographies():
    levels = Counter(fact.geography.level for fact in _facts(LT126))
    assert set(levels) == {"country", "region", "county", "local_authority"}
    # Inner and Outer London are typed as regions, as DESNZ's packages type them.
    assert {
        fact.geography.level
        for fact in _facts(LT126)
        if fact.geography.id.startswith("E13")
    } == {"region"}
    vintages = {fact.geography.id: fact.geography.vintage for fact in _facts(LT126)}
    assert vintages["E08000016"] == "lad_2024"
    assert vintages["E07000190"] == "lad_2018"  # Taunton Deane, to 1 April 2019
    assert vintages["E07000004"] == "lad_2019"  # Aylesbury Vale, to 1 April 2020
    assert vintages["E07000150"] == "lad_2020"  # Corby, to 1 April 2021
    assert vintages["E07000026"] == "lad_2022"  # Allerdale, to 1 April 2023
    assert vintages["E10000006"] == "gss_2022"
    assert vintages["E11000004"] == "gss_2022"
    last = defaultdict(int)
    for fact in _facts(LT126):
        last[fact.geography.id] = max(last[fact.geography.id], fact.period.value)
    for code, vintage in vintages.items():
        if vintage.startswith("lad_20") and vintage != "lad_2024":
            year = int(vintage[4:])
            assert last[code] in {year, year + 1}, (code, vintage, last[code])
