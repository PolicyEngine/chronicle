"""Source packages for PolicyEngine/chronicle#438: dwellings by sector and capital stocks.

Dwellings (AN.111) by institutional sector, read from the two national balance sheet
workbooks that the land packages already pin, and ONS's gross and net capital stock of
dwellings at current prices from its capital stocks releases of 27 November 2025 and 10
June 2026. Expected values are read from the pinned workbooks here, never written into
this file.
"""

from __future__ import annotations

from collections import Counter, defaultdict
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
# package id -> (artifact year, record sets, facts)
PACKAGES = {
    "ons-national-balance-sheet-dwellings-2025": (2024, 360, 360),
    "ons-national-balance-sheet-dwellings-preliminary-2026": (2026, 12, 12),
    "ons-capital-stocks-dwellings-2025": (2024, 480, 480),
    "ons-capital-stocks-dwellings-preliminary-2026": (2026, 2, 2),
}
# The dwellings package -> the land package whose workbook it reads.
LAND = {
    "ons-national-balance-sheet-dwellings-2025": "ons-national-balance-sheet-land-2025",
    "ons-national-balance-sheet-dwellings-preliminary-2026": (
        "ons-national-balance-sheet-land-preliminary-2026"
    ),
}
NEW_ARTIFACTS = {
    "ons-capital-stocks-dwellings-2025": (
        "71a995c315b016a507532bb16fd454494b3d4f4fce34fdeedd8beb25c9120de7",
        535814,
    ),
    "ons-capital-stocks-dwellings-preliminary-2026": (
        "e88090cfa63ee27939daac86f909c83414f950749a8530ce7feb6c953b6e8f18",
        172136,
    ),
}
# dwellings CDID -> (sheet, entity role)
NBS_SECTORS = {
    "E46Y": ("Table 2", "total_economy"),
    "E46D": ("Table 3", "non_financial_corporations"),
    "E46E": ("Table 4", "public_non_financial_corporations"),
    "E46F": ("Table 5", "private_non_financial_corporations"),
    "E46G": ("Table 6", "financial_corporations"),
    "E46I": ("Table 7", "general_government"),
    "E46K": ("Table 8", "central_government"),
    "E46L": ("Table 9", "local_government"),
    "E46M": ("Table 10", "households_and_npish"),
    "E46V": ("Table 11", "households"),
    "E46W": ("Table 12", "non_profit_institutions_serving_households"),
    "E46X": ("Table 13", "public_sector"),
}
# entity role -> (row header as printed, gross CDID, net CDID)
CS_ROWS = {
    "non_financial_corporations": ("Total non-financial corporations1", "MIM8", "MKV5"),
    "financial_corporations": ("Financial corporations", "J5LD", "J5LF"),
    "central_government": ("Central government", "MJS8", "MJS9"),
    "general_government": ("General government", "MQ2L", "MQ2T"),
    "households": ("Households", "MJY2", "MJY3"),
    "non_profit_institutions_serving_households": ("NPISH2", "J5LL", "J5LN"),
    "households_and_npish": ("Total households & NPISH2", "MK2R", "MK2S"),
    "total_economy": ("Total dwellings (excluding land)", "MJF7", "MJF8"),
}
CS_SHEETS = {"gross": "1.1.1", "net": "2.1.1"}


def _facts(package_id: str) -> list:
    year = PACKAGES[package_id][0]
    return load_source_package(package_id).build_facts(year)


def _package(package_id: str) -> dict:
    path = (
        ROOT / "packages" / SOURCE_PACKAGE_ALIASES[package_id] / "source_package.yaml"
    )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _artifact_dir(package_id: str) -> Path:
    return ROOT / "db" / _package(package_id)["artifact"]["resource_directory"]


def _manifest(package_id: str) -> dict:
    path = _artifact_dir(package_id) / "manifest.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _workbook(package_id: str):
    (entry,) = _manifest(package_id)["files"].values()
    path = _artifact_dir(package_id) / entry["filename"]
    return load_workbook(path, data_only=True, read_only=True)


def _number(value: object) -> int:
    """A cell's figure: ONS's capital stocks tables store most of theirs as text."""
    if isinstance(value, int):
        return value
    assert isinstance(value, str) and value.strip().isdigit(), value
    return int(value)


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
    built = _facts(package_id)
    assert len(built) == count
    assert validate_facts(built).valid
    contract = validate_consumer_fact_contract(built)
    assert contract.valid, contract.to_dict()
    assert max(Counter(build_semantic_fact_key(fact) for fact in built).values()) == 1
    assert {fact.provenance_class for fact in built} == {"model_output"}


def test_generator_reproduces_the_committed_packages():
    generator = runpy.run_path(str(ROOT / "scripts/build_uk_438_packages.py"))
    assert len(generator["BUILDERS"]) == len(PACKAGES)
    for directory, build in generator["BUILDERS"].items():
        path = ROOT / "packages" / directory / "source_package.yaml"
        assert build() == path.read_text(encoding="utf-8"), directory


@pytest.mark.parametrize("package_id", sorted(LAND))
def test_dwellings_read_the_workbook_the_land_package_pins(package_id):
    """No new file: each dwellings package reads its land package's artifact."""
    land = LAND[package_id]
    artifact, land_artifact = (
        _package(package_id)["artifact"],
        _package(land)["artifact"],
    )
    for key in ("resource_package", "resource_directory", "manifest", "vintage"):
        assert artifact[key] == land_artifact[key], key
    assert artifact["artifact_year"] == land_artifact["artifact_year"]
    assert _manifest(package_id)["package_id"] == land
    assert not any(
        fact.measure.concept.startswith("ons.nbs_dwellings") for fact in _facts_of(land)
    )


def _facts_of(package_id: str) -> list:
    package = load_source_package(package_id)
    return package.build_facts(package.artifact.artifact_year)


@pytest.mark.parametrize("package_id", sorted(NEW_ARTIFACTS))
def test_new_manifests_pin_bytes_licence_and_r2(package_id):
    manifest = _manifest(package_id)
    assert manifest["package_id"] == package_id
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-12"
    ((year, entry),) = manifest["files"].items()
    assert year == PACKAGES[package_id][0]
    content = (_artifact_dir(package_id) / entry["filename"]).read_bytes()
    sha256, size = NEW_ARTIFACTS[package_id]
    assert hashlib.sha256(content).hexdigest() == entry["sha256"] == sha256
    assert len(content) == entry["size_bytes"] == size
    assert entry["storage"]["r2"]["uri"].endswith(
        f"/{package_id}/{year}/{sha256}/{entry['filename']}"
    )


def _nbs_series(package_id: str) -> dict[str, dict[int, int]]:
    workbook = _workbook(package_id)
    series = {}
    for cdid, (sheet, _) in NBS_SECTORS.items():
        worksheet = workbook[sheet]
        assert worksheet["B8"].value == cdid
        assert worksheet["B7"].value.strip() == "AN.111"
        assert worksheet["B6"].value.startswith("Dwellings")
        series[cdid] = {
            row[0].value: worksheet[f"B{row[0].row}"].value
            for row in worksheet.iter_rows(min_row=9, max_row=70, max_col=1)
            if isinstance(row[0].value, int) and row[0].value >= 1995
        }
    return series


@pytest.mark.parametrize(
    "package_id,years",
    [
        ("ons-national-balance-sheet-dwellings-2025", range(1995, 2025)),
        ("ons-national-balance-sheet-dwellings-preliminary-2026", range(2025, 2026)),
    ],
)
def test_sector_dwellings_are_the_workbook_cells_and_add_up(package_id, years):
    series = _nbs_series(package_id)
    by_role = {role: cdid for cdid, (_, role) in NBS_SECTORS.items()}
    facts = defaultdict(dict)
    for fact in _facts(package_id):
        assert fact.measure.unit == "gbp"
        facts[by_role[fact.entity.role]][fact.period.value] = fact.value
    for cdid in NBS_SECTORS:
        assert set(facts[cdid]) == set(years), cdid
        for year in years:
            assert facts[cdid][year] == series[cdid][year] * 1_000_000, (cdid, year)
    for year in years:
        dwellings = {cdid: facts[cdid][year] for cdid in NBS_SECTORS}
        # ONS's sector tree: every identity holds exactly in both workbooks.
        assert dwellings["E46D"] == dwellings["E46E"] + dwellings["E46F"]
        assert dwellings["E46I"] == dwellings["E46K"] + dwellings["E46L"]
        assert dwellings["E46M"] == dwellings["E46V"] + dwellings["E46W"]
        assert dwellings["E46X"] == dwellings["E46I"] + dwellings["E46E"]
        assert dwellings["E46Y"] == (
            dwellings["E46D"]
            + dwellings["E46G"]
            + dwellings["E46I"]
            + dwellings["E46M"]
        )
        # Financial corporations and local government print 0, kept as printed.
        assert dwellings["E46G"] == dwellings["E46L"] == 0


def _cs_series(package_id: str) -> dict[tuple[str, str], dict[int, int]]:
    """(measure, entity role) -> {year: GBP billion}, read from the workbook's cells."""
    workbook = _workbook(package_id)
    series = {}
    for kind, sheet in CS_SHEETS.items():
        rows = list(workbook[sheet].iter_rows(values_only=True))
        assert rows[0][0].startswith(f"{sheet} {kind.capitalize()} capital stock: by ")
        assert "£ billion" in rows[0]
        years = {
            _number(value): column
            for column, value in enumerate(rows[1])
            if str(value).strip().isdigit()
        }
        # Every asset block repeats the sector headers: read the dwellings block only.
        (end,) = [
            index
            for index, row in enumerate(rows)
            if row[0] == "Total dwellings (excluding land)"
        ]
        starts = [
            index
            for index, row in enumerate(rows)
            if row[0] == "Dwellings (excluding land):"
        ]
        block = rows[starts[0] + 1 if starts else end : end + 1]
        for role, (header, gross, net) in CS_ROWS.items():
            matches = [row for row in block if row[0] == header]
            if not matches:
                continue
            (row,) = matches
            assert row[1] == (gross if kind == "gross" else net), (sheet, header)
            series[(kind, role)] = {
                year: _number(row[column]) for year, column in years.items()
            }
    return series


@pytest.mark.parametrize(
    "package_id,years,roles",
    [
        ("ons-capital-stocks-dwellings-2025", range(1995, 2025), set(CS_ROWS)),
        (
            "ons-capital-stocks-dwellings-preliminary-2026",
            range(2025, 2026),
            {"total_economy"},
        ),
    ],
)
def test_capital_stocks_are_the_workbook_cells(package_id, years, roles):
    series = _cs_series(package_id)
    assert {role for _, role in series} == roles
    facts = defaultdict(dict)
    for fact in _facts(package_id):
        kind = fact.measure.concept.split(".")[1].split("_")[0]
        assert fact.measure.unit == "gbp"
        facts[(kind, fact.entity.role)][fact.period.value] = fact.value
    assert set(facts) == set(series)
    for key, values in facts.items():
        assert set(values) == set(years), key
        for year in years:
            assert values[year] == series[key][year] * 1_000_000_000, (key, year)


def test_capital_stock_sectors_add_up_to_whole_billions():
    """Each table rounds every figure to a whole billion, so sums can be 1 or 2 off."""
    series = _cs_series("ons-capital-stocks-dwellings-2025")
    for kind in CS_SHEETS:
        for year in range(1995, 2025):
            value = {role: series[(kind, role)][year] for role in CS_ROWS}
            parts = (
                value["non_financial_corporations"]
                + value["financial_corporations"]
                + value["general_government"]
                + value["households_and_npish"]
            )
            assert abs(value["total_economy"] - parts) <= 2, (kind, year)
            households = (
                value["households"]
                + value["non_profit_institutions_serving_households"]
            )
            assert abs(value["households_and_npish"] - households) <= 1, (kind, year)
            # The tables print no local government row for dwellings.
            assert value["general_government"] == value["central_government"]


def test_net_capital_stock_is_the_balance_sheets_dwellings_to_the_billion():
    """The issue's parity check: the 2025 edition's net stock against the balance sheet.

    The balance sheet's dwellings are in GBP million and the capital stocks tables'
    in whole billions, so each pair agrees to within half a billion in every year and
    sector both print. The preliminary editions are not compared here: their end-2025
    figures differ by more than rounding, which the docs report.
    """
    by_role = defaultdict(dict)
    for fact in _facts("ons-national-balance-sheet-dwellings-2025"):
        by_role[fact.entity.role][fact.period.value] = fact.value
    compared = 0
    for fact in _facts("ons-capital-stocks-dwellings-2025"):
        if not fact.measure.concept.startswith("ons.net_capital_stock"):
            continue
        balance_sheet = by_role[fact.entity.role][fact.period.value]
        assert abs(fact.value - balance_sheet) <= 500_000_000, (
            fact.entity.role,
            fact.period.value,
        )
        compared += 1
    assert compared == 8 * 30
