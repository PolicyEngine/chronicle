"""Publisher fidelity and contract guards for MBIE's monthly bond-rent CSV."""

from __future__ import annotations

import calendar
import csv
import hashlib
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

from chronicle.artifacts import build_r2_key
from chronicle.bundle import _dimension_label_reports, build_bundle_coverage
from chronicle.consumer_contract import (
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.sources import (
    build_source_cell_key,
    validate_source_cells,
)
from chronicle.sources.rows import build_source_row_key, validate_source_rows
from chronicle.sources.specs import resolve_source_record
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
ALIAS = "mbie-tenancy-bond-rents-tla-2026"
DIRECTORY = Path("mbie/tenancy_bond_rents_tla_2026")
DATA_DIRECTORY = REPO_ROOT / "db" / "data" / DIRECTORY
PACKAGE_PATH = REPO_ROOT / "packages" / DIRECTORY / "source_package.yaml"
# MBIE's September 2026 TLA file (published 9 Sep 2026), as fetched by the hub.
FILENAME = "detailed-monthly-tla-tenancy-september.csv"
SHA256 = "a50937ef88e1834c9a804215115586dd6be63468173f9e23495d868c6ca3ee3f"
SOURCE_URL = (
    f"https://www.tenancy.govt.nz/assets/Uploads/Tenancy/Rental-bond-data/{FILENAME}"
    "?m=24491d4fca0935f5cd5d4da6145efa6f3a12ab03"
)
FETCHED_AT = "2026-10-08T22:17:24Z"
SHEET = "tenancy_bonds"
# The file's own header text: UTF-8 BOM, unquoted, no spaces.
HEADERS = [
    "TimeFrame",
    "location_id",
    "location",
    "LodgedBonds",
    "ActiveBonds",
    "ClosedBonds",
    "MedianRent",
    "GeometricMeanRent",
    "UpperQuartileRent",
    "LowerQuartileRent",
    "LogStdDevWeeklyRent",
]
MEASURES = {
    "lodged_bonds": "LodgedBonds",
    "active_bonds": "ActiveBonds",
    "closed_bonds": "ClosedBonds",
    "median_rent": "MedianRent",
    "geometric_mean_rent": "GeometricMeanRent",
    "upper_quartile_rent": "UpperQuartileRent",
    "lower_quartile_rent": "LowerQuartileRent",
}
# The latest 12 months the file publishes (it runs February 1993 to July 2026).
MONTH_ROW_COUNTS = {
    "2025-08": 67,
    "2025-09": 68,
    "2025-10": 67,
    "2025-11": 68,
    "2025-12": 67,
    "2026-01": 67,
    "2026-02": 68,
    "2026-03": 66,
    "2026-04": 68,
    "2026-05": 68,
    "2026-06": 67,
    "2026-07": 68,
}
# The publisher's selected window has 66 positive TA codes. Chatham Islands
# (067) is absent; an official ta_2025 register was not supplied with this CSV.
PUBLISHED_TA_IDS = {
    1,
    2,
    3,
    11,
    12,
    13,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    31,
    32,
    33,
    34,
    35,
    36,
    37,
    38,
    39,
    40,
    41,
    42,
    43,
    44,
    45,
    46,
    47,
    48,
    49,
    50,
    51,
    52,
    53,
    54,
    55,
    56,
    57,
    58,
    59,
    60,
    62,
    63,
    64,
    65,
    66,
    68,
    69,
    70,
    71,
    72,
    73,
    74,
    75,
    76,
}
MISSING_TA_MONTHS = {
    ("2025-08", 54),
    ("2025-10", 54),
    ("2025-12", 57),
    ("2026-01", 66),
    ("2026-03", 54),
    ("2026-03", 66),
    ("2026-06", 54),
}


def _month_label(month):
    """The publisher's TimeFrame text for a YYYY-MM month: d/mm/yyyy, day 1."""
    year, month_number = month.split("-")
    return f"1/{month_number}/{year}"


def _label_month(label):
    day, month_number, year = label.split("/")
    assert day == "1", label
    return f"{year}-{month_number}"


@lru_cache
def _package():
    return load_source_package(ALIAS)


@lru_cache
def _payload():
    return yaml.safe_load(PACKAGE_PATH.read_text())


@lru_cache
def _rows():
    return _package().build_source_rows(2026)


@lru_cache
def _cells():
    return _package().build_source_cells(2026, source_rows=_rows())


@lru_cache
def _facts():
    return _package().build_facts(2026, cells=_cells(), source_rows=_rows())


@lru_cache
def _records():
    return _package().build_source_records(2026, cells=_cells(), source_rows=_rows())


@lru_cache
def _first_location_specs():
    # All seven measure headers and the date/ID/name guards occur in this
    # publisher ALL row. Compile once; full-package resolution is covered by
    # the lineage and suite tests above.
    return _package().build_source_record_specs(2026)[:7]


@lru_cache
def _publisher_window():
    # An independent read with the csv module; utf-8-sig drops the BOM.
    with (DATA_DIRECTORY / FILENAME).open(newline="", encoding="utf-8-sig") as source:
        return {
            (_label_month(row["TimeFrame"]), int(row["location_id"])): row
            for row in csv.DictReader(source)
            if _label_month(row["TimeFrame"]) in MONTH_ROW_COUNTS
        }


def _fact(month, location, measure):
    record_id = f"mbie.tenancy_bonds.m{month}.{location}.{measure}"
    return next(fact for fact in _facts() if fact.source_record_id == record_id)


def _assert_quartile_contract(payload):
    for record_set in payload["record_sets"]:
        measures = {
            measure["measure_id"]: measure for measure in record_set["measures"]
        }
        for measure_id, percentile in (
            ("lower_quartile_rent", 25),
            ("upper_quartile_rent", 75),
        ):
            measure = measures[measure_id]
            assert measure["aggregation"] == "quantile", "quartile must be a cut-point"
            assert measure["unit"] == "nzd_per_week", "quartile must be a rent amount"
            assert measure["filters"]["rent_percentile"] == percentile
            assert measure["source_column_dimensions"]["rent_percentile"] == percentile
            assert any(
                constraint["variable"] == "rent_percentile"
                and constraint["operator"] == "=="
                and constraint["value"] == percentile
                for constraint in measure["constraints"]
            )


def _assert_published_scale_contract(payload):
    for record_set in payload["record_sets"]:
        for measure in record_set["measures"]:
            assert measure["value_scale"] == 1, (
                "publisher values must not be annualised"
            )
            assert measure.get("divisor_column") is None
            expected_unit = (
                "count" if measure["measure_id"].endswith("bonds") else "nzd_per_week"
            )
            assert measure["unit"] == expected_unit, "publisher unit must remain weekly"


def test_mbie_alias_and_package_validation_counts():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == DIRECTORY
    assert _package().package_id == ALIAS
    report = validate_source_package(ALIAS, year=2026)
    assert report.valid
    assert not report.warnings
    assert report.counts == {
        "record_set_count": 12,
        "row_count": 809,
        "measure_count": 84,
        "source_record_count": 5663,
        "source_region_count": 12,
    }


def test_mbie_artifact_preserves_receipt_bytes_and_r2_identity():
    manifest = yaml.safe_load((DATA_DIRECTORY / "manifest.yaml").read_text())
    artifact = manifest["files"][2026]
    path = DATA_DIRECTORY / FILENAME
    assert manifest["source_id"] == "mbie"
    assert manifest["package_id"] == ALIAS
    assert manifest["license"] == "CC BY 3.0 NZ"
    assert "Licence: CC BY 3.0 NZ" in PACKAGE_PATH.read_text().splitlines()[0]
    assert artifact["filename"] == FILENAME
    assert artifact["source_url"] == SOURCE_URL
    assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest() == SHA256
    assert artifact["size_bytes"] == path.stat().st_size == 1_770_533
    assert artifact["fetched_at"] == FETCHED_AT
    # Publisher bytes as fetched: UTF-8 BOM, unquoted headers without spaces,
    # CRLF on every line, d/mm/yyyy months, newest month first, no thousands
    # separators. .gitattributes keeps git from normalising them.
    lines = path.read_bytes().splitlines(keepends=True)
    assert len(lines) == 26_851
    assert all(line.endswith(b"\r\n") for line in lines)
    assert lines[0] == b"\xef\xbb\xbf" + ",".join(HEADERS).encode() + b"\r\n"
    assert (
        lines[1] == b"1/07/2026,-99,ALL,15114,523449,12450,590,564,700,485,0.3833\r\n"
    )
    assert lines[-1] == (
        b"1/02/1993,2,Whangarei District,117,1203,105,120,122,150,100,0.3027\r\n"
    )
    assert (
        f"db/data/{DIRECTORY.as_posix()}/{FILENAME} binary"
        in (REPO_ROOT / ".gitattributes").read_text().splitlines()
    )
    key = build_r2_key(
        source_id="mbie",
        package_id=ALIAS,
        year=2026,
        sha256=SHA256,
        filename=FILENAME,
        package_path=DATA_DIRECTORY,
    )
    assert key == f"raw/nz/mbie/{ALIAS}/2026/{SHA256}/{FILENAME}"
    assert artifact["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }
    assert {fact.source.raw_r2_uri for fact in _facts()} == {f"r2://ledger-raw/{key}"}


def test_mbie_preserves_full_rows_but_selects_only_published_window_cells():
    # Every data line is a source row; the file has no trailing blank line.
    # The parser drops the BOM, so the first column is TimeFrame.
    assert len(_rows()) == 26_850
    assert [list(row.values) for row in (_rows()[0], _rows()[-1])] == [HEADERS] * 2
    assert (_rows()[0].row_number, _rows()[0].values["TimeFrame"]) == (2, "1/07/2026")
    assert (_rows()[-1].row_number, _rows()[-1].values["TimeFrame"]) == (
        26_851,
        "1/02/1993",
    )
    assert validate_source_rows(_rows()).valid
    assert len(_cells()) == 8910 == (809 + 1) * 11
    assert validate_source_cells(_cells()).valid
    assert len(_publisher_window()) == 809
    assert len(_payload()["artifact"]["selected_rows"]) == 809
    assert _payload()["artifact"]["parser"] == "delimited_text_full_rows"
    assert {cell.sheet_name for cell in _cells()} == {SHEET}
    assert Counter(fact.period.value for fact in _facts()) == {
        month: count * 7 for month, count in MONTH_ROW_COUNTS.items()
    }


def test_mbie_every_fact_is_one_unscaled_publisher_cell_with_row_lineage():
    assert len(_facts()) == 5663
    assert validate_facts(_facts()).valid
    assert validate_consumer_fact_contract(_facts()).valid
    assert {fact.provenance_class for fact in _facts()} == {"administrative"}
    assert {fact.assertion for fact in _facts()} == {"observation"}
    assert {fact.source.source_name for fact in _facts()} == {"mbie"}
    assert {fact.source.source_sha256 for fact in _facts()} == {SHA256}
    assert {fact.source.url for fact in _facts()} == {SOURCE_URL}
    cells_by_address = {(cell.sheet_name, cell.address): cell for cell in _cells()}
    cell_keys = {build_source_cell_key(cell) for cell in _cells()}
    rows_by_key = {build_source_row_key(row): row for row in _rows()}
    records_by_id = {record.source_record_id: record for record in _records()}
    for fact in _facts():
        record = records_by_id[fact.source_record_id]
        selector = record.spec.selector
        assert selector.end_address is None
        assert record.spec.divisor_selector is None
        assert record.spec.value_scale == 1
        cell = cells_by_address[(selector.sheet_name, selector.address)]
        assert cell.cell_type == "number"
        assert Decimal(str(fact.value)) == Decimal(str(cell.raw_value))
        assert fact.source_cell_keys and set(fact.source_cell_keys) <= cell_keys
        assert len(fact.source_row_keys) == 1
        assert fact.source_row_keys == record.source_row_keys == (cell.source_row_key,)
        source_row = rows_by_key[cell.source_row_key]
        assert source_row.values["TimeFrame"] == _month_label(fact.period.value)
        assert source_row.values["TimeFrame"] == fact.filters["Time Frame"]
        assert source_row.values["location_id"] == fact.filters["Location Id"]
        assert source_row.values[MEASURES[fact.layout.measure_id]] == fact.value


@pytest.mark.parametrize(
    ("month", "location", "name", "values"),
    [
        ("2026-07", -99, "ALL", (15114, 523449, 12450, 590, 564, 700, 485)),
        ("2026-07", -1, "NA", (1776, 86619, 1869, 575, 540, 700, 449)),
        ("2026-07", 1, "Far North District", (90, 3168, 102, 545, 499, 650, 450)),
        ("2026-07", 47, "Wellington City", (807, 28818, 651, 560, 530, 695, 440)),
        ("2026-07", 54, "Kaikoura District", (6, 219, 3, 500, 432, 500, 330)),
        (
            "2026-07",
            70,
            "Queenstown-Lakes District",
            (201, 5334, 147, 800, 758, 1000, 600),
        ),
        ("2026-07", 76, "Auckland", (5592, 170511, 4254, 640, 620, 750, 520)),
        ("2025-08", -99, "ALL", (14718, 497025, 11595, 590, 560, 695, 485)),
        ("2025-08", 76, "Auckland", (5829, 158133, 4545, 650, 623, 750, 550)),
    ],
)
def test_mbie_exact_publisher_cells(month, location, name, values):
    row = _publisher_window()[month, location]
    assert row["location"] == name
    for (measure_id, column), expected in zip(MEASURES.items(), values):
        fact = _fact(month, location, measure_id)
        assert int(row[column]) == fact.value == expected
        assert fact.layout.groupby_value_label == name
        assert fact.filters["Location Id"] == location
        assert fact.filters["Time Frame"] == row["TimeFrame"] == _month_label(month)


def test_mbie_window_is_the_files_latest_twelve_months():
    published = sorted({_label_month(row.values["TimeFrame"]) for row in _rows()})
    assert (published[0], published[-1], len(published)) == ("1993-02", "2026-07", 402)
    assert list(MONTH_ROW_COUNTS) == published[-12:]
    assert {
        month: len(
            [row for row in _rows() if row.values["TimeFrame"] == _month_label(month)]
        )
        for month in MONTH_ROW_COUNTS
    } == MONTH_ROW_COUNTS


def test_mbie_source_months_are_fixed_even_when_build_year_is_2023():
    expected = {("month", month) for month in MONTH_ROW_COUNTS}
    assert {(fact.period.type, fact.period.value) for fact in _facts()} == expected
    other_year = _package().build_facts(2023, cells=_cells(), source_rows=_rows())
    assert {(fact.period.type, fact.period.value) for fact in other_year} == expected
    assert [(fact.source_record_id, fact.value) for fact in other_year] == [
        (fact.source_record_id, fact.value) for fact in _facts()
    ]
    for fact in _facts():
        year, month = map(int, fact.period.value.split("-"))
        coverage = fact.period_coverage
        assert coverage.basis == "calendar"
        assert coverage.start_date == f"{fact.period.value}-01"
        assert coverage.source_period_label == _month_label(fact.period.value)
        assert (
            coverage.end_date
            == f"{fact.period.value}-{calendar.monthrange(year, month)[1]}"
        )
        assert "no claim of revision-final status" in coverage.notes
        assert "provisional and subject to revision" in coverage.notes


def test_mbie_ta_geographies_and_missing_months_remain_publisher_scoped():
    published_pairs = set(_publisher_window())
    fact_pairs = {(fact.period.value, fact.filters["Location Id"]) for fact in _facts()}
    assert fact_pairs == published_pairs
    positive_ids = {location for _, location in fact_pairs if location > 0}
    assert positive_ids == PUBLISHED_TA_IDS
    assert len(positive_ids) == 66
    missing = {
        (month, location) for month in MONTH_ROW_COUNTS for location in PUBLISHED_TA_IDS
    } - published_pairs
    assert missing == MISSING_TA_MONTHS
    assert not any(fact.geography.id == "nz-ta-067" for fact in _facts())
    for fact in _facts():
        location = fact.filters["Location Id"]
        if location > 0:
            assert (
                fact.geography.level,
                fact.geography.id,
                fact.geography.vintage,
            ) == (
                "local_authority",
                f"nz-ta-{location:03}",
                "ta_2025",
            )
        elif location == -99:
            assert (fact.geography.level, fact.geography.id) == ("country", "NZ")
            assert fact.layout.table_record_kind == "total"
        else:
            assert (fact.geography.level, fact.geography.id) == (
                "statistical_scope",
                "nz-mbie-location-na",
            )


def test_mbie_quartiles_remain_rent_cutpoints():
    _assert_quartile_contract(_payload())
    for measure, percentile in (
        ("lower_quartile_rent", 25),
        ("upper_quartile_rent", 75),
    ):
        facts = [fact for fact in _facts() if fact.layout.measure_id == measure]
        assert len(facts) == 809
        for fact in facts:
            assert fact.aggregation.method == "quantile"
            assert fact.aggregation.denominator is None
            assert fact.measure.unit == "nzd_per_week"
            assert fact.filters["rent_percentile"] == percentile
            assert any(
                constraint.variable == "rent_percentile"
                and constraint.operator == "=="
                and constraint.value == percentile
                for constraint in fact.constraints
            )
            assert "rent cut-point, not a share" in " ".join(
                fact.measure.concept_evidence_notes.split()
            )


def test_mbie_weekly_rent_values_are_not_annualised():
    _assert_published_scale_contract(_payload())
    for fact in _facts():
        if fact.layout.measure_id.endswith("rent"):
            assert fact.measure.unit == "nzd_per_week"
            assert fact.value == int(
                _publisher_window()[fact.period.value, fact.filters["Location Id"]][
                    MEASURES[fact.layout.measure_id]
                ]
            )


def test_mbie_geometric_mean_has_explicit_approximate_mapping():
    facts = [
        fact for fact in _facts() if fact.layout.measure_id == "geometric_mean_rent"
    ]
    assert len(facts) == 809
    for fact in facts:
        assert fact.aggregation.method == "mean"
        assert fact.measure.concept_relation == "approximate"
        assert fact.measure.concept_authority == "mbie"
        assert fact.measure.concept_evidence_url == SOURCE_URL
        assert "not an arithmetic mean" in fact.measure.concept_evidence_notes
        assert "approximate vocabulary mapping" in fact.measure.concept_evidence_notes


def test_mbie_labels_every_dimension_and_value():
    assert _dimension_label_reports(ALIAS, consumer_fact_rows(_facts())) == ([], [])
    fact = _fact("2026-07", 76, "lower_quartile_rent")
    assert fact.layout.groupby_dimension == "Location Id"
    assert fact.dimension_labels == {
        "Location Id": "Published location",
        "Time Frame": "Published month",
        "rent_percentile": "Rent cut-point percentile",
    }
    assert fact.dimension_value_labels["Location Id"] == {"76": "Auckland"}
    assert fact.dimension_value_labels["Time Frame"] == {"1/07/2026": "July 2026"}
    assert fact.dimension_value_labels["rent_percentile"] == {
        "25": "Lower quartile (25th percentile)"
    }


def test_mbie_bond_records_and_rent_population_qualifications_are_explicit():
    assert {(fact.entity.name, fact.entity.role) for fact in _facts()} == {
        ("dwelling", "rental_bond_record")
    }
    assert {fact.layout.measure_id for fact in _facts()} == set(MEASURES)
    count_facts = [
        fact for fact in _facts() if fact.layout.measure_id.endswith("bonds")
    ]
    assert len(count_facts) == 2427
    assert {fact.measure.unit for fact in count_facts} == {"count"}
    assert {fact.aggregation.method for fact in count_facts} == {"sum"}
    headers = list(_publisher_window()["2026-07", -99])
    assert headers == HEADERS
    assert "LogStdDevWeeklyRent" in headers
    assert not {
        "Bedrooms",
        "Dwelling Type",
        "DwellingType",
        "Mean Rent",
        "MeanRent",
    } & set(headers)
    for fact in _facts():
        notes = " ".join(fact.measure.concept_evidence_notes.lower().split())
        assert "newly lodged bonds or active stock" in notes
        assert "population is unspecified" in notes
        assert "bedrooms, dwelling type and arithmetic mean are absent" in notes
        assert "no missing ta/month is imputed" in notes
        assert "weekly-to-annual conversion" in notes
    assert "no supported standard-deviation aggregation" in PACKAGE_PATH.read_text()


def test_mbie_single_source_bundle_coverage_has_no_duplicate_keys():
    coverage = build_bundle_coverage(consumer_fact_rows(_facts()))
    assert coverage["fact_count"] == 5663
    assert coverage["counts"]["by_source"] == {"mbie": 5663}
    assert coverage["counts"]["by_period"] == {
        f"month:{month}": count * 7 for month, count in MONTH_ROW_COUNTS.items()
    }
    assert coverage["counts"]["by_entity"] == {"dwelling": 5663}
    assert coverage["counts"]["by_source_table"] == {
        "mbie:Detailed monthly TLA tenancy bond data": 5663
    }
    geography_counts = {
        f"local_authority:nz-ta-{location:03}": 84 for location in PUBLISHED_TA_IDS
    }
    geography_counts.update(
        {
            "country:NZ": 84,
            "statistical_scope:nz-mbie-location-na": 84,
            "local_authority:nz-ta-054": 56,
            "local_authority:nz-ta-057": 77,
            "local_authority:nz-ta-066": 70,
        }
    )
    assert coverage["counts"]["by_geography"] == geography_counts
    assert coverage["duplicates"] == {
        "aggregate_fact_keys": [],
        "semantic_fact_keys": [],
    }


def test_mbie_build_suite_passes_all_source_acceptance_gates(tmp_path):
    # Exactly one source suite: no full-country or full-bundle materialisation.
    report = build_source_suite(ALIAS, tmp_path / "suite", year=2026)
    assert report.valid
    assert report.agent_acceptance.valid
    assert all(report.agent_acceptance.checks.values())
    assert not report.agent_acceptance.errors
    assert report.source_rows.row_count == 26_850
    assert report.source_cells.cell_count == 8910
    assert report.source_records.resolved_count == 5663
    assert report.source_records.lineage_coverage == 1
    assert report.facts.fact_count == report.consumer_facts.fact_count == 5663
    assert report.agent_acceptance.counts["raw_artifact_count"] == 1
    assert report.agent_acceptance.counts["raw_r2_link_count"] == 1


@pytest.mark.parametrize(
    ("address", "message"),
    [
        ("A2", "published month"),
        ("B2", "published location ID"),
        ("C2", "row header"),
        *[(f"{column}1", "column header") for column in "DEFGHIJ"],
    ],
)
def test_mbie_source_guards_reject_publisher_layout_drift(address, message):
    changed_cells = [
        replace(cell, raw_value="unexpected publisher layout")
        if cell.address == address
        else cell
        for cell in _cells()
    ]
    with pytest.raises(ValueError, match=message):
        for spec in _first_location_specs():
            resolve_source_record(changed_cells, spec)


def test_mbie_numeric_cell_guard_rejects_text():
    changed_cells = [
        replace(cell, cell_type="text", raw_value="suppressed")
        if cell.address == "D2"
        else cell
        for cell in _cells()
    ]
    with pytest.raises(ValueError, match="expected cell type 'number'"):
        resolve_source_record(changed_cells, _first_location_specs()[0])


@pytest.mark.parametrize(
    ("address", "superseded_value", "message"),
    [
        # The superseded v2 file wrote ISO months and spaced headers.
        ("A2", "2025-08-01", "published month"),
        *[
            (f"{column}1", header, "column header")
            for column, header in zip(
                "DEFGHIJ",
                (
                    "Lodged Bonds",
                    "Active Bonds",
                    "Closed Bonds",
                    "Median Rent",
                    "Geometric Mean Rent",
                    "Upper Quartile Rent",
                    "Lower Quartile Rent",
                ),
                strict=True,
            )
        ],
    ],
)
def test_mbie_source_guards_reject_the_superseded_v2_layout(
    address, superseded_value, message
):
    changed_cells = [
        replace(cell, raw_value=superseded_value) if cell.address == address else cell
        for cell in _cells()
    ]
    with pytest.raises(ValueError, match=message):
        for spec in _first_location_specs():
            resolve_source_record(changed_cells, spec)


def _rename_column(row, old, new):
    return replace(
        row,
        values={
            (new if column == old else column): v for column, v in row.values.items()
        },
    )


@pytest.mark.parametrize(
    "mutate",
    [
        # A BOM left on the first header, or v2's spaced header names.
        lambda row: _rename_column(row, "TimeFrame", "\ufeffTimeFrame"),
        lambda row: _rename_column(row, "TimeFrame", "Time Frame"),
        lambda row: _rename_column(row, "location_id", "Location Id"),
        # v2's ISO month text in the newest ALL row.
        lambda row: (
            replace(row, values={**row.values, "TimeFrame": "2026-07-01"})
            if row.row_number == 2
            else row
        ),
    ],
    ids=["bom-header", "v2-month-header", "v2-location-header", "iso-month-value"],
)
def test_mbie_row_selection_rejects_header_and_month_format_drift(mutate):
    changed_rows = [mutate(row) for row in _rows()]
    with pytest.raises(ValueError, match="must match exactly one source row"):
        _package().build_source_cells(2026, source_rows=changed_rows)


def test_mbie_package_records_the_provisional_september_release():
    header = [
        line for line in PACKAGE_PATH.read_text().splitlines() if line.startswith("#")
    ]
    text = " ".join(" ".join(line.lstrip("# ") for line in header).split())
    assert FILENAME in text
    assert "published on 9 Sep 2026" in text
    assert "provisional and subject to revision" in text
    readme = " ".join((PACKAGE_PATH.parent / "README.md").read_text().split())
    assert FILENAME in readme
    assert "9 September 2026" in readme
    assert "provisional" in readme
    assert "fixed random rounding to base 3" in readme
    assert "fewer than 5 bonds" in readme
    assert _payload()["artifact"]["vintage"] == "september_2026_release"


@pytest.mark.parametrize("measure_id", ["lower_quartile_rent", "upper_quartile_rent"])
def test_mbie_quartile_contract_rejects_mutated_yaml_share(measure_id):
    payload = {"record_sets": [deepcopy(_payload()["record_sets"][0])]}
    measure = next(
        measure
        for measure in payload["record_sets"][0]["measures"]
        if measure["measure_id"] == measure_id
    )
    measure["aggregation"] = "share"
    # Exercise the same package invariant against valid, but incorrect, YAML.
    changed_yaml = yaml.safe_load(yaml.safe_dump(payload))
    with pytest.raises(AssertionError, match="quartile must be a cut-point"):
        _assert_quartile_contract(changed_yaml)


@pytest.mark.parametrize(
    "measure_id",
    [
        "median_rent",
        "geometric_mean_rent",
        "upper_quartile_rent",
        "lower_quartile_rent",
    ],
)
def test_mbie_scale_contract_rejects_mutated_yaml_annualisation(measure_id):
    payload = {"record_sets": [deepcopy(_payload()["record_sets"][0])]}
    measure = next(
        measure
        for measure in payload["record_sets"][0]["measures"]
        if measure["measure_id"] == measure_id
    )
    measure["value_scale"] = 52
    changed_yaml = yaml.safe_load(yaml.safe_dump(payload))
    with pytest.raises(AssertionError, match="publisher values must not be annualised"):
        _assert_published_scale_contract(changed_yaml)
