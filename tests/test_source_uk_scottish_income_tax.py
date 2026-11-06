"""HMRC Scottish income tax outturn facts for PolicyEngine/chronicle#420 item 8.

Checks the package scripts/build_uk_scottish_income_tax_package.py writes from HMRC's
Scottish Income Tax Outturn Statistics, 2024 to 2025 (PolicyEngine/uk-scottish-budget-2027-28#7):
the NSND Income Tax outturn by component (Table 1), by tax band and marginal rate with the
number of taxpayers (Table 2), by collection method (Table 3), and the indicative in-year
RTI Income Tax by month (Table 4). Values are re-read from the pinned workbook with odfpy,
and each fact's cell is found from the fact's own geography, period and dimensions, not
from the package's coordinates.
"""

from __future__ import annotations

import hashlib
import io
import re
import runpy
from collections import Counter
from pathlib import Path

import pytest
import yaml
from odf import teletype
from odf.opendocument import load
from odf.table import Table, TableRow

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
DIRECTORY = ROOT / "db/data/hmrc/scottish_income_tax_outturn_2024_25"
PACKAGE_ID = "hmrc-scottish-income-tax-outturn-2024-25"
FACTS = 1652
TABLE_FACTS = {"Table_1": 245, "Table_2": 736, "Table_3": 190, "Table_4": 481}
NUMERIC_TEXT = re.compile(r"^-?[\d,]+(\.\d+)?$")
MONTH_COLUMNS = dict(
    zip(
        (
            "April May June July August September October November December January "
            "February March"
        ).split(),
        "CDEFGHIJKLMN",
    )
)


@pytest.fixture(scope="module")
def built():
    package = load_source_package(PACKAGE_ID)
    return package, package.build_facts(package.artifact.artifact_year)


@pytest.fixture(scope="module")
def tables() -> dict[str, dict[tuple[int, str], object]]:
    """Every sheet's non-empty cells, read with odfpy: {sheet: {(row, column): value}}."""
    manifest = yaml.safe_load((DIRECTORY / "manifest.yaml").read_text())
    ((_, entry),) = manifest["files"].items()
    document = load(io.BytesIO((DIRECTORY / entry["filename"]).read_bytes()))
    sheets = {}
    for table in document.spreadsheet.getElementsByType(Table):
        grid = {}
        row_number = 0
        for row in table.getElementsByType(TableRow):
            rows = int(row.getAttribute("numberrowsrepeated") or 1)
            column = 0
            values = []
            for cell in row.childNodes:
                if cell.qname[1] not in ("table-cell", "covered-table-cell"):
                    continue
                repeat = int(cell.getAttribute("numbercolumnsrepeated") or 1)
                value = None
                kind = cell.getAttribute("valuetype")
                if kind in ("float", "percentage", "currency"):
                    number = float(cell.getAttribute("value"))
                    value = int(number) if number.is_integer() else number
                else:
                    text = teletype.extractText(cell).strip()
                    if NUMERIC_TEXT.match(text):
                        number = float(text.replace(",", ""))
                        value = int(number) if "." not in text else number
                    else:
                        value = text or None
                for _ in range(min(repeat, 64)):
                    values.append(value)
                column += repeat
            if any(v is not None for v in values):
                for _ in range(rows):
                    row_number += 1
                    for index, value in enumerate(values):
                        if value is not None:
                            grid[(row_number, chr(65 + index))] = value
            else:
                row_number += rows
        sheets[table.getAttribute("name")] = grid
    return sheets


def _year_label(year: int) -> str:
    return f"{year}-{(year + 1) % 100:02d}"


def _group(text: str) -> tuple[str, str | None]:
    """The printed group's name and Welsh tax devolution basis, independently of the generator."""
    basis = None
    if "(Pre-Welsh tax devolution)" in text:
        basis = "pre_welsh_tax_devolution"
    elif "(Post-Welsh tax devolution)" in text:
        basis = "post_welsh_tax_devolution"
    name = re.sub(r" \((Pre|Post)-Welsh tax devolution\)| \[Note \d+\]", "", text)
    return name.lower(), basis


def _fact_group(fact) -> str:
    concept = fact.measure.concept
    if concept.endswith("_scottish_share_of_uk"):
        return "scottish share of uk"
    return {
        "S92000003": "scottish",
        "W92000004": "welsh",
        "K02000001": "all uk",
        "hmrc:england_and_northern_ireland": "rest of uk",
        "hmrc:england_wales_and_northern_ireland": "rest of uk",
    }[fact.geography.id]


def _rows(grid: dict, fact, band_text: str | None = None) -> list[int]:
    year = fact.period.value if fact.period.type == "tax_year" else None
    if year is None:
        label = fact.period_coverage.source_period_label
        year = int(label.split()[-1][:4])
    basis = fact.filters.get("welsh_tax_devolution_basis")
    return [
        row
        for (row, column), value in grid.items()
        if column == "A"
        and isinstance(value, str)
        and _group(value) == (_fact_group(fact), basis)
        and grid.get((row, "B")) == _year_label(year)
        and (band_text is None or grid.get((row, "C")) == band_text)
    ]


TABLE_1_COLUMNS = dict(
    zip(
        (
            "sa_established_liability",
            "paye_established_liability",
            "estimated_further_liability",
            "adjustment_for_uncollectable_amounts",
            "relief_at_source",
            "gift_aid",
            "all",
        ),
        "CDEFGHI",
    )
)
TABLE_3_AMOUNTS = dict(
    zip(
        (
            "collected_through_paye",
            "paid_through_self_assessment",
            "uncollected_ras_and_gift_aid_repayments",
            "all",
        ),
        "CDEF",
    )
)
TABLE_3_SHARES = {"collected_through_paye": "G", "paid_through_self_assessment": "H"}
RATE_COLUMNS = {
    "starter": "E",
    "basic": "F",
    "intermediate": "G",
    "higher": "H",
    "advanced": "I",
    "all": "K",
}
BAND_TEXTS = {
    "starter": ("Starter Rate",),
    "basic": ("Basic Rate",),
    "intermediate": ("Intermediate Rate",),
    "higher": ("Higher Rate",),
    "advanced": ("Advanced Rate",),
    "top": ("Top Rate",),
    "additional": ("Additional Rate",),
    "additional_or_top": ("Additional/Top Rate", "Additional Rate"),
    "all": ("All Bands",),
}


def _cell(tables: dict, fact) -> tuple[str, int, str]:
    concept = fact.measure.concept
    filters = fact.filters
    if concept.startswith("hmrc.nsnd_income_tax_outturn"):
        sheet, column, band = (
            "Table_1",
            TABLE_1_COLUMNS[filters["nsnd_outturn_component"]],
            None,
        )
    elif concept == "hmrc.nsnd_income_taxpayers":
        sheet, column = "Table_2", "D"
        band = filters.get("marginal_rate", "all")
    elif concept == "hmrc.nsnd_income_tax_by_band":
        sheet = "Table_2"
        band = filters.get("income_tax_band", "all")
        rate = filters["marginal_rate"]
        column = RATE_COLUMNS.get(rate, "J")
    elif concept == "hmrc.nsnd_income_tax_collection_method_share":
        sheet, column, band = (
            "Table_3",
            TABLE_3_SHARES[filters["nsnd_collection_method"]],
            None,
        )
    elif concept.startswith("hmrc.nsnd_income_tax_by_collection_method"):
        sheet, column, band = (
            "Table_3",
            TABLE_3_AMOUNTS[filters["nsnd_collection_method"]],
            None,
        )
    else:
        sheet, band = "Table_4", None
        label = fact.period_coverage.source_period_label
        column = (
            "O" if fact.period.type == "tax_year" else MONTH_COLUMNS[label.split()[0]]
        )
    grid = tables[sheet]
    if band is None:
        (row,) = _rows(grid, fact)
    else:
        (row,) = [r for text in BAND_TEXTS[band] for r in _rows(grid, fact, text)]
    return sheet, row, column


# ---------------------------------------------------------------- registration


def test_package_validates_registers_and_carries_no_anchors(built):
    package, facts = built
    report = validate_source_package(
        package.package_path, year=package.artifact.artifact_year
    )
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["source_record_count"] == len(facts) == FACTS
    assert SOURCE_PACKAGE_ALIASES[PACKAGE_ID] == package.package_path.relative_to(
        ROOT / "packages"
    )
    assert PACKAGE_ID in UK_BUNDLE_SOURCES
    text = (package.package_path / "source_package.yaml").read_text(encoding="utf-8")
    assert not re.search(r"(:|^\s*-)\s+[&*][A-Za-z_][\w-]*\s*$", text, re.M)
    assert validate_facts(facts).valid
    keys = Counter(build_semantic_fact_key(fact) for fact in facts)
    assert max(keys.values()) == 1


def test_generator_reproduces_the_committed_package():
    generator = runpy.run_path(
        str(ROOT / "scripts/build_uk_scottish_income_tax_package.py")
    )
    ((directory, build),) = generator["BUILDERS"].items()
    committed = ROOT / "packages" / directory / "source_package.yaml"
    assert build() == committed.read_text(encoding="utf-8")


def test_manifest_pins_bytes_licence_and_the_r2_key():
    manifest = yaml.safe_load((DIRECTORY / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["source_id"] == "hmrc"
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-06"
    ((year, entry),) = manifest["files"].items()
    content = (DIRECTORY / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    assert entry["source_url"].startswith("https://assets.publishing.service.gov.uk/")
    # `chronicle publish-raw` uploaded the bytes and wrote storage.r2, and
    # `chronicle verify-raw` read the object back.
    key = f"raw/uk/hmrc/{manifest['package_id']}/{year}/{entry['sha256']}/{entry['filename']}"
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


def test_facts_are_the_published_cells_and_only_those(built, tables):
    _, facts = built
    seen = Counter()
    cells = set()
    for fact in facts:
        sheet, row, column = _cell(tables, fact)
        published = tables[sheet][(row, column)]
        scale = 1_000_000 if fact.measure.unit == "gbp" else 1
        assert fact.value == pytest.approx(published * scale, rel=1e-12), (
            sheet,
            row,
            column,
        )
        seen[sheet] += 1
        cells.add((sheet, row, column))
    assert seen == TABLE_FACTS
    assert len(cells) == FACTS
    # Every number printed in the tables' data columns is a fact.
    printed = {
        (sheet, row, column)
        for sheet, columns in (
            ("Table_1", "CDEFGHI"),
            ("Table_2", "DEFGHIJK"),
            ("Table_3", "CDEFGH"),
            ("Table_4", "CDEFGHIJKLMNO"),
        )
        for (row, column), value in tables[sheet].items()
        if column in columns and isinstance(value, (int, float)) and row > 8
    }
    assert cells == printed


def _one(facts, concept, geography, year, **filters):
    matches = [
        f
        for f in facts
        if f.measure.concept == concept
        and f.geography.id == geography
        and f.period.value == year
        and all(f.filters.get(k) == v for k, v in filters.items())
    ]
    assert len(matches) == 1, (concept, geography, year, filters, len(matches))
    return matches[0].value


def test_the_release_headlines_are_the_cells(built):
    _, facts = built
    scotland, rest = "S92000003", "hmrc:england_and_northern_ireland"
    # 'the total amount of NSND Income Tax generated by Scottish taxpayers in the 2024 to
    # 2025 tax year was £18.6 billion'; 3,036,400 Scottish and 32,533,800 rUK taxpayers;
    # rUK £250.2 billion; 'the Scottish share of UK NSND Income Tax ... was 6.7%'.
    outturn = "hmrc.nsnd_income_tax_outturn"
    final = dict(nsnd_outturn_component="all")
    assert _one(facts, outturn, scotland, 2024, **final) == 18_635_000_000
    assert round(_one(facts, outturn, rest, 2024, **final) / 1e8) == 2502
    taxpayers = [
        f.value
        for f in facts
        if f.measure.concept == "hmrc.nsnd_income_taxpayers"
        and f.period.value == 2024
        and "marginal_rate" not in f.filters
    ]
    assert sorted(taxpayers) == [3_036_400, 32_533_800, 37_230_600]
    share = _one(
        facts,
        "hmrc.nsnd_income_tax_outturn_scottish_share_of_uk",
        scotland,
        2024,
        **final,
    )
    assert round(100 * share, 1) == 6.7


def test_parity(built):
    _, facts = built
    by_key: dict[tuple, dict] = {}
    for f in facts:
        key = (
            f.measure.concept,
            f.geography.id,
            f.period.type,
            f.period.value,
            f.filters.get("welsh_tax_devolution_basis"),
        )
        by_key.setdefault(key, {})[
            tuple(
                sorted(
                    (k, v)
                    for k, v in f.filters.items()
                    if k != "welsh_tax_devolution_basis"
                )
            )
        ] = f.value
    for (concept, geography, _, year, _), cells in by_key.items():
        if concept == "hmrc.nsnd_income_tax_outturn":
            final = cells[(("nsnd_outturn_component", "all"),)]
            parts = sum(
                v for k, v in cells.items() if k != (("nsnd_outturn_component", "all"),)
            )
            assert abs(parts - final) <= 3.5e6, (geography, year)
        if concept == "hmrc.nsnd_income_tax_collection_method_share":
            assert abs(sum(cells.values()) - 1) <= 0.0015, (geography, year)
        if concept == "hmrc.nsnd_income_taxpayers":
            total = cells[()]
            parts = sum(v for k, v in cells.items() if k != ())
            assert abs(parts - total) <= 50 * len(cells), (geography, year)
    # The UK's 2024-25 all-bands, all-taxpayers cell omits the Starter band, as printed.
    liability = {
        tuple(sorted(f.filters.items())): f.value
        for f in facts
        if f.measure.concept == "hmrc.nsnd_income_tax_by_band"
        and f.geography.id == "K02000001"
        and f.period.value == 2024
    }
    total = liability[(("marginal_rate", "all"),)]
    types = sum(
        v
        for k, v in liability.items()
        if len(k) == 1 and k != (("marginal_rate", "all"),)
    )
    starter = liability[(("income_tax_band", "starter"), ("marginal_rate", "all"))]
    assert types - total == pytest.approx(starter, abs=1)
    assert round(types / 1e6) == 276_612
    # Table 4's months add to each year's annual total.
    rti: dict[tuple, dict] = {}
    for f in facts:
        if f.measure.concept == "hmrc.rti_income_tax_withheld":
            year = int(f.period_coverage.source_period_label.split()[-1][:4])
            rti.setdefault((f.geography.id, year), {})[f.period.type] = (
                rti.get((f.geography.id, year), {}).get(f.period.type, 0) + f.value
            )
    assert len(rti) == 10 + 7 + 10
    for key, sums in rti.items():
        assert abs(sums["month"] - sums["tax_year"]) <= 6.5e6, key


def test_rest_of_uk_geography_follows_welsh_tax_devolution(built):
    _, facts = built
    rest = {
        (f.period.value, f.filters.get("welsh_tax_devolution_basis"), f.geography.id)
        for f in facts
        if f.geography.level == "statistical_scope"
    }
    for year, basis, geography in rest:
        with_wales = year < 2019 or basis == "pre_welsh_tax_devolution"
        expected = (
            "hmrc:england_wales_and_northern_ireland"
            if with_wales
            else "hmrc:england_and_northern_ireland"
        )
        assert geography == expected, (year, basis)
    assert {basis for year, basis, _ in rest if year == 2019} == {
        "pre_welsh_tax_devolution",
        "post_welsh_tax_devolution",
    }


def test_marginal_rates_follow_each_group_s_bands(built):
    _, facts = built
    rates = Counter(
        (f.geography.id, f.period.value >= 2018, f.filters["marginal_rate"])
        for f in facts
        if f.measure.concept
        in ("hmrc.nsnd_income_tax_by_band", "hmrc.nsnd_income_taxpayers")
        and f.filters.get("marginal_rate") in ("top", "additional", "additional_or_top")
    )
    for (geography, from_2018, rate), _ in rates.items():
        if geography == "S92000003":
            assert rate == ("top" if from_2018 else "additional")
        elif geography == "K02000001":
            assert rate == ("additional_or_top" if from_2018 else "additional")
        else:
            assert rate == "additional"
