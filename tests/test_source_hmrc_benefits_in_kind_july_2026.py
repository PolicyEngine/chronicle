"""HMRC benefits in kind statistics, July 2026 (PolicyEngine/uk-autumn-budget-dashboard-2026#316).

Checks the package build_package.py writes from Tables 1, 2A, 2C, 2E, 3A, 3B and 4 of
HMRC's Tables 1 to 4 workbook. Values are re-read from the workbook with pandas,
located by the publisher's labels rather than by the package's coordinates.
"""

from __future__ import annotations

import hashlib
import re
import runpy
from collections import Counter
from dataclasses import replace
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
PACKAGE = ROOT / "packages/hmrc/benefits_in_kind_july_2026"
DATA = ROOT / "db/data/hmrc/benefits_in_kind_july_2026"
ODS = DATA / "2026_Tables_1_to_4.ods"
PACKAGE_ID = "hmrc-benefits-in-kind-july-2026"
PREFIX = "hmrc.benefits_in_kind_july_2026"
YEARS = range(2011, 2025)
MARKERS = {"<0.5", "<2.5", "[note 3]"}


@pytest.fixture(scope="module")
def facts():
    package = load_source_package(PACKAGE)
    return {fact.source_record_id: fact for fact in package.build_facts(2026)}


@pytest.fixture(scope="module")
def sheets():
    return pd.read_excel(ODS, sheet_name=None, header=None, engine="odf")


def _value(facts: dict, record_id: str) -> float:
    return facts[f"{PREFIX}.{record_id}"].value


def _row(sheet: pd.DataFrame, label: str) -> int:
    labels = sheet.iloc[:, 0].astype(str).str.strip()
    (row,) = labels.index[labels == label]
    return row


def _year_columns(sheet: pd.DataFrame, header_label: str) -> dict[int, int]:
    """Tax year -> column, read from the row whose first cell is ``header_label``."""
    header = sheet.iloc[_row(sheet, header_label)]
    columns = {}
    for column, label in enumerate(header):
        match = re.match(r"(\d{4}) to (\d{4})", str(label))
        if match:
            assert int(match.group(2)) == int(match.group(1)) + 1
            columns[int(match.group(1))] = column
    assert sorted(columns) == list(YEARS)
    return columns


def test_package_validates_registers_and_carries_no_anchors(facts):
    report = validate_source_package(PACKAGE, year=2026)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["record_set_count"] == 121
    assert report.counts["source_record_count"] == 544
    assert SOURCE_PACKAGE_ALIASES[PACKAGE_ID] == PACKAGE.relative_to(ROOT / "packages")
    assert PACKAGE_ID in UK_BUNDLE_SOURCES
    text = (PACKAGE / "source_package.yaml").read_text(encoding="utf-8")
    assert not any(
        isinstance(token, (yaml.AnchorToken, yaml.AliasToken))
        for token in yaml.scan(text)
    )
    assert validate_facts(list(facts.values())).valid
    keys = Counter(build_semantic_fact_key(fact) for fact in facts.values())
    assert max(keys.values()) == 1


def test_generator_reproduces_the_committed_package():
    generator = runpy.run_path(str(PACKAGE / "build_package.py"))
    assert generator["package"]() == (PACKAGE / "source_package.yaml").read_text(
        encoding="utf-8"
    )


def _manifest_entry() -> tuple[dict, dict]:
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text(encoding="utf-8"))
    return manifest, manifest["files"][2026]


def _r2_uri(manifest: dict, entry: dict) -> str:
    return (
        f"r2://ledger-raw/raw/uk/hmrc/{manifest['package_id']}/2026/"
        f"{entry['sha256']}/{entry['filename']}"
    )


def test_manifest_pins_bytes_licence_and_the_r2_key():
    manifest, entry = _manifest_entry()
    assert manifest["package_id"] == PACKAGE_ID
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-10-30"
    assert entry["source_url"].startswith("https://assets.publishing.service.gov.uk/")
    content = ODS.read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"]
    # `chronicle publish-raw` uploads the bytes and writes storage.r2; until it has
    # run there is no storage block at all, never a partial or guessed one.
    if "storage" in entry:
        assert entry["storage"]["r2"]["uri"] == _r2_uri(manifest, entry)
    else:
        assert set(entry) == {
            "filename",
            "source_url",
            "sha256",
            "size_bytes",
            "fetched_at",
        }


def test_consumer_contract_waits_only_on_the_r2_location(facts):
    built = list(facts.values())
    report = validate_consumer_fact_contract(built)
    manifest, entry = _manifest_entry()
    if "storage" in entry:
        assert report.valid
        return
    assert {(issue.code, issue.field) for issue in report.errors} == {
        ("missing_contract_provenance", "source.raw_r2_uri")
    }
    uri = _r2_uri(manifest, entry)
    located = [
        replace(fact, source=replace(fact.source, raw_r2_uri=uri)) for fact in built
    ]
    assert validate_consumer_fact_contract(located).valid


def test_provenance_concepts_and_counts_by_table(facts):
    by_table = Counter()
    for record_id, fact in facts.items():
        table = record_id.split(".")[2]
        by_table[
            (
                table,
                fact.provenance_class,
                fact.measure.concept,
                fact.aggregation.method,
            )
        ] += 1
        # Tables 3A, 3B and 4 are grossed from the SPI-matched sample; the rest come
        # from the P11D and RTI records, or (liabilities) HMRC's model on them.
        if table in ("table3a", "table3b", "table4"):
            assert fact.survey_instrument == (
                "Survey of Personal Incomes matched to employers' P11D and Real Time "
                "Information company car records"
            )
        else:
            assert fact.survey_instrument is None
        assert fact.assertion == "observation"
        assert fact.entity.name == "person"
        assert fact.entity.role == "benefit_in_kind_recipient"
        assert fact.domain == "company_car_benefits"
        assert fact.period.type == "tax_year"
    recipients = ("hmrc.benefit_in_kind_recipients", "sum")
    value = ("hmrc.benefit_in_kind_taxable_value", "sum")
    mean = ("hmrc.benefit_in_kind_mean_taxable_value", "mean")
    survey = "survey_aggregate"
    assert by_table == {
        ("table1", "administrative", *recipients): 42,
        ("table1", "administrative", *value): 42,
        ("table1", "administrative", *mean): 28,
        (
            "table1",
            "model_output",
            "hmrc.benefit_in_kind_income_tax_liability",
            "sum",
        ): 42,
        (
            "table1",
            "model_output",
            "hmrc.benefit_in_kind_class_1a_nic_liability",
            "sum",
        ): 42,
        ("table2a", "administrative", *recipients): 207,
        ("table2c", "administrative", *recipients): 34,
        (
            "table2e",
            "administrative",
            "hmrc.company_car_mean_co2_emissions",
            "mean",
        ): 14,
        ("table3a", survey, *recipients): 11,
        ("table3a", survey, *value): 11,
        ("table3a", survey, *mean): 11,
        ("table3b", survey, *recipients): 5,
        ("table3b", survey, *value): 8,
        ("table3b", survey, *mean): 8,
        ("table4", survey, *recipients): 13,
        ("table4", survey, *value): 13,
        ("table4", survey, *mean): 13,
    }
    assert Counter(fact.period.value for fact in facts.values()) == {
        2011: 27,
        2012: 27,
        2013: 28,
        2014: 29,
        2015: 29,
        2016: 30,
        2017: 30,
        2018: 30,
        2019: 31,
        2020: 38,
        2021: 38,
        2022: 38,
        2023: 38,
        2024: 131,
    }


TABLE_1_ROWS = {
    "recipients": (
        1000,
        "Car benefit recipients (thousands)",
        "Fuel benefit recipients (thousands)",
        "Car and fuel benefit recipients (thousands) [note 2]",
    ),
    "taxable_value": (
        1000000,
        "Car benefit total taxable value (£millions)",
        "Fuel benefit total taxable value (£millions)",
        "Car and fuel benefit total taxable value (£millions)",
    ),
    "income_tax_liability": (
        1000000,
        "Car benefit total Income Tax liability (£millions)",
        "Fuel benefit total Income Tax liability (£millions)",
        "Car and car fuel benefit total Income Tax liability (£millions)",
    ),
    "class_1a_nic_liability": (
        1000000,
        "Car benefit total NIC liability (£millions)",
        "Fuel benefit total NIC liability (£millions)",
        "Car and fuel benefit total NIC liability (£millions)",
    ),
}


def test_table_1_matches_the_workbook_by_label(facts, sheets):
    sheet = sheets["1_car_and_car_fuel_benefit"]
    columns = _year_columns(sheet, "Tax Year")
    checked = 0
    for measure, (scale, *labels) in TABLE_1_ROWS.items():
        for benefit, label in zip(("car", "fuel", "all"), labels):
            row = _row(sheet, label)
            for year, column in columns.items():
                record_id = f"table1.{measure}.ty{year}.{benefit}.{measure}"
                assert _value(facts, record_id) == sheet.iloc[row, column] * scale
                checked += 1
    assert checked == 4 * 3 * 14
    # 2024-25: 920 thousand car benefit recipients and GBP 3,070 million.
    assert _value(facts, "table1.recipients.ty2024.car.recipients") == 920000
    assert _value(facts, "table1.taxable_value.ty2024.car.taxable_value") == 3070000000
    # The average rows are ported as printed, in GBP, car and fuel only.
    for benefit, label in (
        ("car", "Car benefit average taxable value (£)"),
        ("fuel", "Fuel benefit average taxable value (£)"),
    ):
        row = _row(sheet, label)
        for year, column in columns.items():
            record_id = (
                f"table1.average_taxable_value.ty{year}.{benefit}.average_taxable_value"
            )
            fact = facts[f"{PREFIX}.{record_id}"]
            assert fact.value == sheet.iloc[row, column]
            assert fact.aggregation.method == "mean"
            assert fact.measure.unit == "gbp"
    assert not any(
        record_id.startswith(f"{PREFIX}.table1.average_taxable_value.")
        and record_id.split(".")[-2] == "all"
        for record_id in facts
    )
    # HMRC averages before rounding, so the quotient of the rounded cells (GBP 3,337)
    # is not the printed GBP 3,330.
    assert (
        _value(facts, "table1.average_taxable_value.ty2024.car.average_taxable_value")
        == 3330
    )
    assert round(3070000000 / 920000) == 3337


def _band_id(label: str) -> str:
    """'Zero' -> co2_0, '165- 169' -> co2_165_to_169, '170 g/km and over' ->
    co2_170_plus, read from the publisher's label."""
    if label == "Zero":
        return "co2_0"
    numbers = re.findall(r"\d+", label)
    if label.endswith("and over"):
        return f"co2_{numbers[0]}_plus"
    return f"co2_{numbers[0]}_to_{numbers[1]}"


def _band_bounds(fact) -> tuple[float, float]:
    low, high = 0.0, float("inf")
    for item in fact.constraints:
        if item.variable != "company_car_co2_emissions":
            continue
        assert item.unit == "g_co2_per_km"
        if item.operator == "==":
            low = high = item.value
        elif item.operator in (">", ">="):
            low = item.value
        else:
            assert item.operator == "<"
            high = item.value
    return low, high


def test_table_2a_matches_the_workbook_and_its_bands_tile(facts, sheets):
    sheet = sheets["2A_CO2_recipients"]
    columns = _year_columns(sheet, "CO2 emission band")
    first, total_row = _row(sheet, "Zero"), _row(sheet, "Total")
    for year, column in columns.items():
        prefix = f"{PREFIX}.table2a.recipients.ty{year}."
        ported = {
            record_id.removeprefix(prefix): fact
            for record_id, fact in facts.items()
            if record_id.startswith(prefix)
        }
        cells = {
            str(sheet.iloc[row, 0]).strip(): sheet.iloc[row, column]
            for row in range(first, total_row)
            if pd.notna(sheet.iloc[row, column])
        }
        numbers = {label: v for label, v in cells.items() if v not in MARKERS}
        # Each printed number is a fact, found by the band its label names.
        assert {_band_id(label): value * 1000 for label, value in numbers.items()} == {
            fact.layout.groupby_value_id: fact.value for fact in ported.values()
        }
        for fact in ported.values():
            assert fact.measure.unit == "count"
            assert fact.filters["company_car_benefit_type"] == "car"
            assert fact.value != 0
        # A year prints one scheme: 13 bands to 2019-20 and 20 from 2020-21, marked
        # cells included, and the bands it ports never overlap and end open.
        assert len(cells) == (20 if year >= 2020 else 13)
        bands = sorted(_band_bounds(fact) for fact in ported.values())
        assert all(a[1] <= b[0] for a, b in zip(bands, bands[1:])), (year, bands)
        assert bands[-1][1] == float("inf")
        # The Total row restates Table 1, and the bands sum to it within rounding.
        sheet_total = sheet.iloc[total_row, column]
        assert sheet_total * 1000 == _value(
            facts, f"table1.recipients.ty{year}.car.recipients"
        )
        assert abs(sum(numbers.values()) - sheet_total) <= 10, year
    assert _value(facts, "table2a.recipients.ty2024.co2_0.recipients") == 467000
    assert _value(facts, "table2a.recipients.ty2024.co2_170_plus.recipients") == 10000
    assert _value(facts, "table2a.recipients.ty2019.co2_51_to_75.recipients") == 4000
    for missing in (
        "table2a.recipients.ty2014.co2_0.recipients",  # '[note 3]'
        "table2a.recipients.ty2013.co2_1_to_50.recipients",  # '<0.5'
        "table2a.recipients.ty2015.co2_51_to_75.recipients",  # '<0.5'
        "table2a.recipients.ty2024.co2_51_to_75.recipients",  # not this year's band
        "table2a.recipients.ty2019.co2_51_to_54.recipients",  # not this year's band
    ):
        assert f"{PREFIX}.{missing}" not in facts, missing


def test_table_2c_matches_the_workbook(facts, sheets):
    sheet = sheets["2C_fuel_type_recipients"]
    columns = _year_columns(sheet, "Type of fuel")
    rows = {
        "diesel_including_hybrids": _row(sheet, "Diesel (including hybrids)"),
        "petrol_including_hybrids": _row(sheet, "Petrol (including hybrids)"),
        "fully_electric": _row(sheet, "Fully Electric"),
    }
    total = _row(sheet, "Total")
    checked = 0
    for year, column in columns.items():
        numbers = 0
        for fuel, row in rows.items():
            cell = sheet.iloc[row, column]
            record_id = f"{PREFIX}.table2c.recipients.ty{year}.{fuel}.recipients"
            if cell in MARKERS:
                assert record_id not in facts
                continue
            assert facts[record_id].value == cell * 1000
            assert facts[record_id].filters["company_car_fuel_type"] == fuel
            numbers += cell
            checked += 1
        # Rounded to the nearest 5 thousand, the rows sit within 10 thousand of the
        # Total row, which restates Table 1 and is ported from Table 1.
        assert abs(numbers - sheet.iloc[total, column]) <= 10, year
    assert checked == 34
    assert (
        _value(facts, "table2c.recipients.ty2024.fully_electric.recipients") == 465000
    )
    assert (
        _value(facts, "table2c.recipients.ty2024.diesel_including_hybrids.recipients")
        == 60000
    )


def test_table_2e_matches_the_workbook(facts, sheets):
    sheet = sheets["2E_average_CO2"]
    columns = _year_columns(sheet, "Tax Year")
    row = _row(sheet, "Average CO2 emissions (g/km)")
    for year, column in columns.items():
        record_id = f"table2e.average_co2_emissions.ty{year}.car.average_co2_emissions"
        fact = facts[f"{PREFIX}.{record_id}"]
        assert fact.value == sheet.iloc[row, column]
        assert fact.measure.unit == "g_co2_per_km"
        assert fact.measure.concept == "hmrc.company_car_mean_co2_emissions"
        assert fact.aggregation.method == "mean"
        assert fact.filters["company_car_benefit_type"] == "car"
    # The commentary's 41 g/km for 2024-25, electric cars included.
    assert (
        _value(facts, "table2e.average_co2_emissions.ty2024.car.average_co2_emissions")
        == 41
    )
    assert (
        _value(facts, "table2e.average_co2_emissions.ty2011.car.average_co2_emissions")
        == 140
    )


@pytest.mark.parametrize(
    ("sheet_name", "table", "benefit", "first_label", "rows", "recipients_marked"),
    [
        ("3A_car_recipients_income", "3a", "car", "£0 to £8,499", 11, set()),
        (
            "3B_fuel_recipients_income",
            "3b",
            "fuel",
            "£0 to £29,999",
            8,
            {"income_0_to_29999", "income_30000_to_39999", "income_150000_to_199999"},
        ),
        ("4_car_region", "4", "car", "North East", 13, set()),
    ],
)
def test_tables_3_and_4_match_the_workbook_by_label(
    facts, sheets, sheet_name, table, benefit, first_label, rows, recipients_marked
):
    sheet = sheets[sheet_name]
    first, all_row = _row(sheet, first_label), _row(sheet, "All")
    assert all_row - first == rows
    header = sheet.iloc[first - 1].astype(str).tolist()
    recipients_column = header.index("Recipients (thousands)")
    value_column = header.index("Taxable value (£millions)")
    average_column = header.index("Average value (£)")
    for measure, column, scale in (
        ("recipients", recipients_column, 1000),
        ("taxable_value", value_column, 1000000),
        ("average_taxable_value", average_column, 1),
    ):
        prefix = f"{PREFIX}.table{table}.{measure}.ty2024."
        ported = {
            fact.layout.groupby_value_label: fact
            for record_id, fact in facts.items()
            if record_id.startswith(prefix)
        }
        expected = {
            str(sheet.iloc[row, 0]).strip(): sheet.iloc[row, column]
            for row in range(first, all_row)
            if sheet.iloc[row, column] not in MARKERS
        }
        assert {label: fact.value for label, fact in ported.items()} == {
            label: cell * scale for label, cell in expected.items()
        }
        for fact in ported.values():
            assert fact.filters["company_car_benefit_type"] == benefit
            assert fact.period.value == 2024
            assert fact.provenance_class == "survey_aggregate"
        recipients_ids = {
            fact.layout.groupby_value_id
            for fact in facts.values()
            if fact.source_record_id.startswith(f"{PREFIX}.table{table}.recipients")
        }
        for other in ("taxable_value", "average_taxable_value"):
            marked = {
                fact.layout.groupby_value_id
                for fact in facts.values()
                if fact.source_record_id.startswith(f"{PREFIX}.table{table}.{other}.")
            } - recipients_ids
            assert marked == recipients_marked
    # The 'All' row's recipients and taxable value print the same as Table 1's 2024-25
    # cells, which carry them; its average matches Table 1's in Tables 3A and 3B only.
    record = f"table1.recipients.ty2024.{benefit}.recipients"
    assert sheet.iloc[all_row, recipients_column] * 1000 == _value(facts, record)
    record = f"table1.taxable_value.ty2024.{benefit}.taxable_value"
    assert sheet.iloc[all_row, value_column] * 1000000 == _value(facts, record)
    record = f"table1.average_taxable_value.ty2024.{benefit}.average_taxable_value"
    assert (sheet.iloc[all_row, average_column] == _value(facts, record)) == (
        table != "4"
    )
    assert not any(
        record_id.startswith(f"{PREFIX}.table{table}.")
        and fact.layout.groupby_value_id in ("all", "K02000001")
        for record_id, fact in facts.items()
    )


def test_income_bands_and_regions_carry_their_universe(facts):
    lowest = facts[f"{PREFIX}.table3a.recipients.ty2024.income_0_to_8499.recipients"]
    bounds = {(c.variable, c.operator, c.value) for c in lowest.constraints}
    assert ("total_income", "<", 8500) in bounds
    top = facts[
        f"{PREFIX}.table3b.taxable_value.ty2024.income_200000_plus.taxable_value"
    ]
    bounds = {(c.variable, c.operator, c.value) for c in top.constraints}
    assert ("total_income", ">=", 200000) in bounds
    assert not any(c.operator == "<" for c in top.constraints)
    regions = {
        fact.geography.id: (fact.geography.level, fact.geography.name)
        for record_id, fact in facts.items()
        if record_id.startswith(f"{PREFIX}.table4.recipients.")
    }
    assert regions["E12000008"] == ("region", "South East")
    assert regions["S92000003"] == ("country", "Scotland")
    assert regions["hmrc:recipient_region_unknown"] == ("statistical_scope", "Unknown")
    assert len(regions) == 13
    assert _value(facts, "table4.recipients.ty2024.E12000008.recipients") == 140000


def test_notes_carry_rounding_markers_and_the_publisher_caveats(facts):
    for record_id, fact in facts.items():
        year = fact.period.value
        coverage = fact.period_coverage.notes
        notes = fact.measure.concept_evidence_notes
        assert ("provisional (note 1)" in coverage) == (year == 2024), record_id
        assert ("under-reported in every year since April 2016" in coverage) == (
            year >= 2016
        ), record_id
        assert ("zero-rate charge" in coverage) == (year <= 2014), record_id
        assert "rounded" in notes or "no rounding rule" in notes, record_id
        if ".table3" in record_id or ".table4." in record_id:
            assert "will not necessarily match the figure in Table 1" in notes
            assert "standard SPI grossing factors" in notes
            assert "Its 'All' row" in notes
            assert (
                fact.period_coverage.source_period_label
                == "Tax year 2024 to 2025 [note 1]"
            )
        if "average" in record_id.split(".")[3]:
            assert (
                "ported as published, not derived" in notes or ".table2e." in record_id
            )
    notes_2011 = facts[f"{PREFIX}.table2a.recipients.ty2011.co2_76_to_94.recipients"]
    text = notes_2011.measure.concept_evidence_notes
    assert "'[note 3]'" in text and "'<0.5'" in text
    assert "for 'Zero'" in text and "'1 - 50' and '51 - 75'" in text
    clean = facts[f"{PREFIX}.table2a.recipients.ty2024.co2_0.recipients"]
    assert "HMRC prints" not in clean.measure.concept_evidence_notes
    marked = facts[
        f"{PREFIX}.table3b.taxable_value.ty2024.income_0_to_29999.taxable_value"
    ]
    assert "'<2.5'" in marked.measure.concept_evidence_notes
    assert (
        len(marked.source_cell_keys)
        == len(
            facts[
                f"{PREFIX}.table3b.taxable_value.ty2024.income_40000_to_49999.taxable_value"
            ].source_cell_keys
        )
        + 1
    )
    marked_average = facts[
        f"{PREFIX}.table3b.average_taxable_value.ty2024.income_0_to_29999.average_taxable_value"
    ]
    assert "'<2.5'" in marked_average.measure.concept_evidence_notes
    assert marked_average.value == 2390
    nic = facts[
        f"{PREFIX}.table1.class_1a_nic_liability.ty2024.car.class_1a_nic_liability"
    ]
    assert "Class 1A" in nic.measure.concept_evidence_notes
    assert "projected forward one year" in nic.period_coverage.notes
    assert (
        "projected forward"
        not in facts[
            f"{PREFIX}.table1.recipients.ty2024.car.recipients"
        ].period_coverage.notes
    )
    table_4 = facts[
        f"{PREFIX}.table4.average_taxable_value.ty2024.E12000001.average_taxable_value"
    ]
    assert "prints a different value" in table_4.measure.concept_evidence_notes
