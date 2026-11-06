"""DWP Pathways to Work PIP point scores for PolicyEngine/chronicle#420 item 5.

Checks the package scripts/build_dwp_pathways_evidence_pack_package.py writes from the
chapter 2 data tables of DWP's Pathways to Work evidence pack (ODS revised 23 July
2025): Tables 2.9 to 2.12, 2.19 to 2.22, 2.27 and 2.28, for working-age PIP claimants
under normal rules on the January 2025 caseload. Values are re-read from the pinned
workbook with zipfile and ElementTree, counting merged and repeated cells as a
spreadsheet does (Chronicle's ODS parser keeps no covered cells, so a heading after a
merged range reads further left there), and each fact's cell is found from the fact's
own dimensions and the printed headings, not from the package's coordinates.
"""

from __future__ import annotations

import hashlib
import re
import runpy
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree

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
PACKAGE_ID = "dwp-pathways-to-work-pip-points-january-2025"
RAW = ROOT / "db/data/dwp/pathways_to_work_evidence_pack_chapter_2_2025"
FACTS = 1240
SHEETS = {
    "2.9": "T2_9_PIP_DL_Points_by_age",
    "2.10": "T2_10_PIP_Mob_Points_by_age",
    "2.11": "T2_11_PIP_DL_Pts_by_condition",
    "2.12": "T2_12_PIP_Mob_Pts_by_condition",
    "2.19": "T2_19_Max_DL_pts_-_Caseload",
    "2.20": "T2_20_Max_DL_pts_-_DL_Award",
    "2.21": "T2_21_Max_DL_pts_-_Age",
    "2.22": "T2_22_Max_DL_pts_-_Condition",
    "2.27": "T2_27_DL_pts_by_activity",
    "2.28": "T2_28_DL_pts_activity_condition",
}
FACTS_BY_TABLE = {
    "2.9": 91,
    "2.10": 84,
    "2.11": 262,
    "2.12": 252,
    "2.19": 8,
    "2.20": 14,
    "2.21": 48,
    "2.22": 160,
    "2.27": 46,
    "2.28": 275,
}
DAILY_LIVING_BANDS = {
    "0_to_3": "0-3",
    "4_to_7": "4-7",
    "8_to_9": "8-9",
    "10_to_11": "10-11",
    "12_to_13": "12-13",
    "14_to_15": "14-15",
    "16_to_20": "16-20",
    "21_to_25": "21-25",
    "26_to_30": "26-30",
    "31_to_35": "31-35",
    "36_to_40": "36-40",
    "41_and_over": "41+",
}
POINTS_DIMENSIONS = {
    "dwp.pip_daily_living_points_share": "pip_daily_living_points_band",
    "dwp.pip_mobility_points_share": "pip_mobility_points",
    "dwp.pip_max_daily_living_activity_points_share": "pip_max_daily_living_activity_points",
    "dwp.pip_daily_living_activity_points_share": "pip_daily_living_activity_points",
}
VOLUME_HEADINGS = {
    "2.9": "Volume in age group",
    "2.10": "Volume in age group",
    "2.11": "Volume in each condition category",
    "2.12": "Volume in each condition category",
    "2.19": "Volume",
    "2.20": "Volume in award group",
    "2.21": "Volume in age group",
    "2.22": "Volume in each condition category",
}
AGE_TEXT = {
    "all": "All ages",
    "16_to_19": "16 - 19",
    "20_to_29": "20 - 29",
    "30_to_39": "30 - 39",
    "40_to_49": "40 - 49",
    "50_to_59": "50 - 59",
    "60_and_over": "60+",
}
AWARD_TEXT = {"enhanced": "Enhanced Daily Living", "standard": "Standard Daily Living"}
OVERALL_TEXT = (
    "Percentage of working age PIP claimants out of all claimants in receipt of Daily "
    "Living component"
)
DAILY_LIVING_TOTAL = "All working age claimants in receipt of Daily Living component"
CONDITION_TEXT_2_28 = {
    "anxiety_and_depression": "Anxiety and Depression",
    "arthritis": "Arthritis",
    "learning_disabilities": "Learning Disabilities",
    "back_pain": "Back Pain",
    "autistic_spectrum_disorders": "Autistic Spectrum Disorders",
    "all_other_conditions_outside_five_groups": "All other conditions",
}
SCOPE = {
    "pip_policy_ownership": "dwp",
    "pip_claimant_age_group": "working_age",
    "pip_claim_rules": "normal_rules",
}
# Tables 2.9 to 2.12 are the whole caseload, pension age included, whatever DWP's note
# says, so their facts carry no claimant age group (see the package header).
WHOLE_CASELOAD_TABLES = ("2.9", "2.10", "2.11", "2.12")
CASES_PACKAGE_ID = "dwp-pip-cases-country-award-age-january-2024-july-2026"


def _scope(fact) -> dict:
    if _table(fact) in WHOLE_CASELOAD_TABLES:
        return {k: v for k, v in SCOPE.items() if k != "pip_claimant_age_group"}
    return SCOPE


TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
OFFICE_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


# ---------------------------------------------------------------- the workbook


def _pinned() -> tuple[dict, dict, bytes]:
    manifest = yaml.safe_load((RAW / "manifest.yaml").read_text(encoding="utf-8"))
    ((_, entry),) = manifest["files"].items()
    return manifest, entry, (RAW / entry["filename"]).read_bytes()


def _cell_value(cell: ElementTree.Element) -> object:
    value_type = cell.get(f"{{{OFFICE_NS}}}value-type")
    if value_type == "float":
        number = float(cell.get(f"{{{OFFICE_NS}}}value"))
        return int(number) if number.is_integer() else number
    text = " ".join(
        " ".join("".join(p.itertext()).split()) for p in cell.findall(f"{{{TEXT_NS}}}p")
    ).strip()
    return text or None


def _read_workbook(content: bytes) -> dict[str, dict[tuple[int, int], object]]:
    """Every sheet's cells at their spreadsheet positions (1-based row and column)."""
    root = ElementTree.fromstring(
        zipfile.ZipFile(_bytes_io(content)).read("content.xml")
    )
    sheets = {}
    for table in root.iter(f"{{{TABLE_NS}}}table"):
        grid: dict[tuple[int, int], object] = {}
        row_number = 0
        for row in table.iter(f"{{{TABLE_NS}}}table-row"):
            repeat = int(row.get(f"{{{TABLE_NS}}}number-rows-repeated", 1))
            row_number += 1
            column = 0
            for cell in row:
                span = int(cell.get(f"{{{TABLE_NS}}}number-columns-repeated", 1))
                value = (
                    _cell_value(cell)
                    if cell.tag == f"{{{TABLE_NS}}}table-cell"
                    else None
                )
                for _ in range(span):
                    column += 1
                    if value is not None:
                        grid[(row_number, column)] = value
                if column > 200:
                    break
            row_number += repeat - 1
            if row_number > 400:
                break
        sheets[table.get(f"{{{TABLE_NS}}}name")] = grid
    return sheets


def _bytes_io(content: bytes):
    import io

    return io.BytesIO(content)


@pytest.fixture(scope="module")
def workbook():
    _, _, content = _pinned()
    return _read_workbook(content)


@pytest.fixture(scope="module")
def built():
    package = load_source_package(PACKAGE_ID)
    return package, package.build_facts(package.artifact.artifact_year)


def _table(fact) -> str:
    match = re.search(r"\.t2_(\d+)\.", fact.layout.record_set_id)
    return f"2.{match.group(1)}"


def _find(grid: dict, text: object, *, rows=None) -> list[tuple[int, int]]:
    return [
        (row, column)
        for (row, column), value in grid.items()
        if value == text and (rows is None or row in rows)
    ]


def _one(grid: dict, text: object, *, rows=None) -> tuple[int, int]:
    (hit,) = _find(grid, text, rows=rows)
    return hit


def _headings(table: str) -> tuple:
    if table in ("2.9", "2.11"):
        return tuple(DAILY_LIVING_BANDS.values())
    if table in ("2.10", "2.12"):
        return (0, 4, 8, 10, 12, 14, 16, 18, 20, 22, 24)
    if table in ("2.19", "2.20", "2.21", "2.22"):
        return (2, 3, 4, 6, 8, 10, 12)
    return (0, 1, 2, 3, 4, 6, 8, 10, 12)


def _heading_row(grid: dict, table: str) -> tuple[int, dict]:
    """The row printing the table's points headings, and each heading's column."""
    headings = _headings(table)
    for row in sorted({row for row, _ in grid}):
        printed = {
            value: column
            for (r, column), value in grid.items()
            if r == row and value in headings and not isinstance(value, bool)
        }
        if len(printed) == len(headings) and (row > 6 if table != "2.28" else row > 5):
            columns = [printed[heading] for heading in headings]
            if columns == sorted(columns):
                return row, printed
    raise AssertionError(table)


def _row_of(grid: dict, table: str, fact) -> int:
    filters = fact.filters
    heading_row, _ = _heading_row(grid, table)
    below = range(heading_row + 1, heading_row + 80)
    if table in ("2.9", "2.10", "2.21"):
        return _one(grid, AGE_TEXT[filters["age_band"]], rows=below)[0]
    if table in ("2.11", "2.12", "2.22"):
        value = filters["pip_primary_health_condition_group"]
        label = (
            "All health conditions"
            if value == "all"
            else fact.dimension_value_labels["pip_primary_health_condition_group"][
                value
            ]
        )
        label = {
            "All Other Conditions (outside the 18 groups shown)": "All Other Conditions",
        }.get(label, label)
        return _one(grid, label, rows=below)[0]
    if table == "2.19":
        return _one(grid, OVERALL_TEXT, rows=below)[0]
    if table == "2.20":
        return _one(
            grid, AWARD_TEXT[filters["pip_daily_living_award_rate"]], rows=below
        )[0]
    activity = fact.dimension_value_labels["pip_daily_living_activity"][
        filters["pip_daily_living_activity"]
    ]
    if table == "2.27":
        return _one(grid, activity, rows=below)[0]
    block = _one(
        grid,
        CONDITION_TEXT_2_28[filters["pip_primary_health_condition_group"]],
        rows=below,
    )[0]
    return _one(grid, activity, rows=range(block + 1, block + 11))[0]


def _column_of(grid: dict, table: str, fact) -> int:
    heading_row, columns = _heading_row(grid, table)
    if fact.layout.measure_id == "claimants":
        return _one(
            grid, VOLUME_HEADINGS[table], rows=range(heading_row - 2, heading_row + 1)
        )[1]
    value = fact.filters[POINTS_DIMENSIONS[fact.measure.concept]]
    heading = DAILY_LIVING_BANDS[value] if table in ("2.9", "2.11") else value
    return columns[heading]


def _cell_of(workbook: dict, fact) -> tuple[str, int, int]:
    table = _table(fact)
    grid = workbook[SHEETS[table]]
    return table, _row_of(grid, table, fact), _column_of(grid, table, fact)


# ---------------------------------------------------------------- registration


def test_package_validates_registers_and_carries_no_anchors(built):
    package, facts = built
    report = validate_source_package(package.package_path, year=2025)
    assert report.valid, report.to_dict()
    assert not report.warnings
    assert report.counts["source_record_count"] == len(facts) == FACTS
    relative = package.package_path.relative_to(ROOT / "packages")
    assert SOURCE_PACKAGE_ALIASES[PACKAGE_ID] == relative
    assert PACKAGE_ID in UK_BUNDLE_SOURCES
    text = (package.package_path / "source_package.yaml").read_text(encoding="utf-8")
    assert not re.search(r"(:|^\s*-)\s+[&*][A-Za-z_][\w-]*\s*$", text, re.M)
    assert validate_facts(facts).valid
    assert Counter(_table(fact) for fact in facts) == FACTS_BY_TABLE


def test_generator_reproduces_the_committed_package():
    generator = runpy.run_path(
        str(ROOT / "scripts/build_dwp_pathways_evidence_pack_package.py")
    )
    builders = generator["BUILDERS"]
    assert list(builders) == ["dwp/pathways_to_work_pip_points_january_2025"]
    for directory, build in builders.items():
        committed = ROOT / "packages" / directory / "source_package.yaml"
        assert build() == committed.read_text(encoding="utf-8"), directory


def test_manifest_pins_bytes_licence_and_the_r2_key():
    manifest, entry, content = _pinned()
    assert manifest["source_id"] == "dwp"
    assert manifest["package_id"] == "dwp-pathways-to-work-evidence-pack-chapter-2-2025"
    assert manifest["license"] == "Open Government Licence v3.0"
    assert manifest["license_verified_at"] == "2026-11-06"
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert len(content) == entry["size_bytes"] == 832879
    assert entry["source_url"] == (
        "https://assets.publishing.service.gov.uk/media/68808d2f28f29c99778a74eb/"
        "chapter_2_reforming_the_structure.ods"
    )
    assert entry["publisher_last_modified"] == "2025-07-23T07:20:15+00:00"
    # `chronicle publish-raw` uploaded the bytes and wrote storage.r2.
    key = f"raw/uk/dwp/{manifest['package_id']}/2025/{entry['sha256']}/{entry['filename']}"
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


# ---------------------------------------------------------------- the published cells


def _excluded(workbook: dict) -> set[tuple[str, int, int]]:
    """The cells the package documents as not ported, at spreadsheet positions."""
    excluded = set()
    for table in ("2.20", "2.21", "2.22"):
        grid = workbook[SHEETS[table]]
        row, _ = _one(grid, DAILY_LIVING_TOTAL)
        excluded |= {
            (table, row, column) for (r, column) in grid if r == row and column > 1
        }
    grid = workbook[SHEETS["2.11"]]
    row, _ = _one(grid, "All health conditions")
    _, columns = _heading_row(grid, "2.11")
    excluded |= {
        ("2.11", row, column) for heading, column in columns.items() if heading != "0-3"
    }
    grid = workbook[SHEETS["2.28"]]
    block, _ = _one(grid, "Arthritis")
    activity, _ = _one(
        grid, "Activity 1 - Preparing food", rows=range(block + 1, block + 11)
    )
    _, columns = _heading_row(grid, "2.28")
    excluded.add(("2.28", activity, columns[2]))
    return excluded


def test_facts_are_the_published_cells_and_only_those(built, workbook):
    _, facts = built
    seen = set()
    for fact in facts:
        table, row, column = _cell_of(workbook, fact)
        assert workbook[SHEETS[table]][(row, column)] == fact.value, (
            table,
            row,
            column,
        )
        assert (table, row, column) not in seen
        seen.add((table, row, column))
        assert fact.period.type == "month" and fact.period.value == "2025-01"
        assert fact.geography.id == "K04000001"
        scope = _scope(fact)
        assert {key: fact.filters[key] for key in scope} == scope
        if _table(fact) in WHOLE_CASELOAD_TABLES:
            assert "pip_claimant_age_group" not in fact.filters
        assert fact.provenance_class == "administrative"
    excluded = _excluded(workbook)
    assert not seen & excluded
    for table, sheet in SHEETS.items():
        grid = workbook[sheet]
        heading_row, columns = _heading_row(grid, table)
        data_columns = set(columns.values())
        if table in VOLUME_HEADINGS:
            data_columns.add(
                _one(
                    grid,
                    VOLUME_HEADINGS[table],
                    rows=range(heading_row - 2, heading_row + 1),
                )[1]
            )
        source_row = (
            _one(grid, "Source(s):")[0]
            if _find(grid, "Source(s):")
            else _one(grid, "Source(s);")[0]
        )
        published = {
            (table, row, column)
            for (row, column), value in grid.items()
            if heading_row < row < source_row
            and column in data_columns
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        }
        assert published - excluded == {cell for cell in seen if cell[0] == table}, (
            table
        )
        marks = {
            value
            for (row, column), value in grid.items()
            if heading_row < row < source_row
            and column in data_columns
            and not isinstance(value, (int, float))
        }
        assert marks <= {"-"}, (table, marks)


def test_some_published_cells(built):
    _, facts = built

    def value(table, measure_id, **filters):
        (match,) = [
            fact
            for fact in facts
            if _table(fact) == table
            and fact.layout.measure_id == measure_id
            and all(fact.filters.get(k) == v for k, v in filters.items())
        ]
        return match.value

    awarded = dict(pip_daily_living_award_rate="standard_or_enhanced")
    assert value("2.19", "max_points_4", **awarded) == 44.25
    assert value("2.19", "claimants", **awarded) == 2_891_000
    assert (
        value("2.20", "max_points_4", pip_daily_living_award_rate="enhanced") == 70.06
    )
    assert (
        value("2.20", "claimants", pip_daily_living_award_rate="standard") == 1_283_000
    )
    assert value("2.21", "max_points_4", age_band="16_to_19") == 75.39
    assert value("2.9", "points_16_to_20", age_band="16_to_19") == 22
    assert value("2.9", "claimants", age_band="all") == 3_627_000
    assert value("2.10", "points_12", age_band="all") == pytest.approx(29.307, abs=5e-4)
    assert value("2.11", "points_0_to_3", pip_primary_health_condition_group="all") == (
        pytest.approx(1.1668, abs=5e-5)
    )
    assert value("2.27", "points_12", pip_daily_living_activity="activity_7") == 1.68
    assert (
        value(
            "2.28",
            "points_4",
            pip_daily_living_activity="activity_9",
            pip_primary_health_condition_group="autistic_spectrum_disorders",
        )
        == 83.02
    )


def test_points_filters_carry_their_constraints(built):
    _, facts = built
    for fact in facts:
        constraints = {(c.variable, c.operator): c.value for c in fact.constraints}
        for key, value in _scope(fact).items():
            assert constraints[(key, "==")] == value
        if _table(fact) in WHOLE_CASELOAD_TABLES:
            assert ("pip_claimant_age_group", "==") not in constraints
        if fact.layout.measure_id == "claimants":
            assert fact.measure.unit == "count" and fact.aggregation.method == "sum"
            continue
        assert fact.measure.unit == "percent" and fact.aggregation.method == "share"
        dimension = POINTS_DIMENSIONS[fact.measure.concept]
        assert constraints[(dimension, "==")] == fact.filters[dimension]
        if dimension == "pip_daily_living_points_band":
            low, _, high = fact.filters[dimension].partition("_to_")
            low = int(low.replace("_and_over", ""))
            assert constraints[("pip_daily_living_points", ">=")] == low
            if high:
                assert constraints[("pip_daily_living_points", "<=")] == int(high)
            else:
                assert ("pip_daily_living_points", "<=") not in constraints
        if _table(fact) in ("2.19", "2.20", "2.21", "2.22", "2.27", "2.28"):
            award = constraints[("pip_daily_living_award_rate", "==")]
            assert award in ("standard_or_enhanced", "enhanced", "standard")
        else:
            assert ("pip_daily_living_award_rate", "==") not in constraints


def test_only_the_age_and_condition_totals_share_semantic_keys(built):
    """The 'All ages' and 'All health conditions' rows describe the same caseload."""
    _, facts = built
    groups = defaultdict(list)
    for fact in facts:
        groups[build_semantic_fact_key(fact)].append(fact)
    shared = [group for group in groups.values() if len(group) > 1]
    assert len(shared) == 14
    for group in shared:
        tables = sorted(_table(fact) for fact in group)
        assert tables in (["2.11", "2.9"], ["2.10", "2.12"]), tables
        assert all(
            "all"
            in (
                fact.filters.get("age_band"),
                fact.filters.get("pip_primary_health_condition_group"),
            )
            for fact in group
        )
        assert len({fact.layout.measure_id for fact in group}) == 1


# ---------------------------------------------------------------- parity


def _row(grid: dict, table: str, row: int) -> list:
    _, columns = _heading_row(grid, table)
    return [grid.get((row, column)) for column in columns.values()]


def _numbers(values) -> list[float]:
    return [
        v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]


def test_every_distribution_adds_to_100_within_rounding(workbook):
    sums = {}
    for table, sheet in SHEETS.items():
        grid = workbook[sheet]
        heading_row, _ = _heading_row(grid, table)
        for row in sorted({r for r, _ in grid if r > heading_row}):
            values = _numbers(_row(grid, table, row))
            if values:
                sums[(table, row)] = sum(values)
    whole = {round(total) for (table, _), total in sums.items() if table == "2.9"}
    assert whole == {92, 98, 99, 100, 102}
    grid = workbook[SHEETS["2.11"]]
    text_order_row = _one(grid, "All health conditions")[0]
    grid = workbook[SHEETS["2.28"]]
    block = _one(grid, "Arthritis")[0]
    copied_row = _one(
        grid, "Activity 1 - Preparing food", rows=range(block + 1, block + 11)
    )[0]
    assert sums[("2.28", copied_row)] == pytest.approx(98.74)
    others = {
        key: total
        for key, total in sums.items()
        if key[0] != "2.9" and key not in (("2.28", copied_row),)
    }
    assert max(abs(total - 100) for total in others.values()) == pytest.approx(
        0.164, abs=1e-3
    )
    assert others[("2.11", text_order_row)] == pytest.approx(100)


def _weighted(workbook, table: str, rows: list[int], volumes: list[int]) -> list[float]:
    grid = workbook[SHEETS[table]]
    values = [_row(grid, table, row) for row in rows]
    total = sum(volumes)
    return [
        sum(
            (v[i] if isinstance(v[i], (int, float)) else 0) * volume
            for v, volume in zip(values, volumes)
        )
        / total
        for i in range(len(values[0]))
    ]


def _volume(workbook, table: str, row: int) -> int:
    grid = workbook[SHEETS[table]]
    heading_row, _ = _heading_row(grid, table)
    column = _one(
        grid, VOLUME_HEADINGS[table], rows=range(heading_row - 2, heading_row + 1)
    )[1]
    return grid[(row, column)]


def _data_rows(workbook, table: str, first_text: str) -> list[int]:
    grid = workbook[SHEETS[table]]
    first = _one(grid, first_text)[0]
    source = min(r for r, _ in _find(grid, "Source(s):") + _find(grid, "Source(s);"))
    return [r for r in range(first, source) if _numbers(_row(grid, table, r))]


@pytest.mark.parametrize(
    ("table", "total_text", "tolerance"),
    [
        ("2.9", "All ages", 0.6),
        ("2.10", "All ages", 0.001),
        ("2.12", "All health conditions", 0.003),
        ("2.20", DAILY_LIVING_TOTAL, 0.01),
        ("2.21", DAILY_LIVING_TOTAL, 0.01),
        ("2.22", DAILY_LIVING_TOTAL, 0.015),
    ],
)
def test_the_parts_weighted_by_volume_reproduce_the_total(
    workbook, table, total_text, tolerance
):
    """Item 20's split by award, weighted by the award mix, gives item 19's shares."""
    rows = _data_rows(workbook, table, total_text)
    total_row, parts = rows[0], rows[1:]
    average = _weighted(
        workbook, table, parts, [_volume(workbook, table, r) for r in parts]
    )
    printed = _row(workbook[SHEETS[table]], table, total_row)
    gaps = [abs(a - p) for a, p in zip(average, printed) if isinstance(p, (int, float))]
    assert max(gaps) <= tolerance, max(gaps)
    if table in ("2.20", "2.21", "2.22"):
        overall = _row(
            workbook[SHEETS["2.19"]],
            "2.19",
            _data_rows(workbook, "2.19", OVERALL_TEXT)[0],
        )
        assert printed == overall


def test_table_2_11_total_row_prints_its_bands_in_text_order(workbook):
    rows = _data_rows(workbook, "2.11", "All health conditions")
    total_row, parts = rows[0], rows[1:]
    average = dict(
        zip(
            DAILY_LIVING_BANDS.values(),
            _weighted(
                workbook, "2.11", parts, [_volume(workbook, "2.11", r) for r in parts]
            ),
        )
    )
    printed = _row(workbook[SHEETS["2.11"]], "2.11", total_row)
    text_order = sorted(DAILY_LIVING_BANDS.values())
    assert text_order[:4] == ["0-3", "10-11", "12-13", "14-15"]
    for value, band in zip(printed, text_order):
        assert value == pytest.approx(average[band], abs=0.02), band
    assert abs(printed[1] - average["4-7"]) > 10


def test_table_2_28_reproduces_2_27_but_for_one_copied_cell(workbook):
    grid22, grid27, grid28 = (workbook[SHEETS[key]] for key in ("2.22", "2.27", "2.28"))
    volumes = {
        grid22[(row, 1)]: _volume(workbook, "2.22", row)
        for row in _data_rows(workbook, "2.22", "Cancer")
    }
    total = _volume(workbook, "2.22", _one(grid22, DAILY_LIVING_TOTAL)[0])
    blocks = {text: _one(grid28, text)[0] for text in CONDITION_TEXT_2_28.values()}
    weights = {text: volumes[text] for text in list(blocks)[:5]}
    weights["All other conditions"] = total - sum(weights.values())
    _, columns = _heading_row(grid28, "2.28")
    gaps = {}
    for offset in range(10):
        published = _row(
            grid27,
            "2.27",
            _data_rows(workbook, "2.27", "Activity 1 - Preparing food")[offset],
        )
        for index, value in enumerate(published):
            if not isinstance(value, (int, float)):
                continue
            column = list(columns.values())[index]
            average = (
                sum(
                    (
                        v
                        if isinstance(
                            v := grid28.get((blocks[text] + 1 + offset, column)),
                            (int, float),
                        )
                        else 0
                    )
                    * weight
                    for text, weight in weights.items()
                )
                / total
            )
            gaps[(offset + 1, list(columns)[index])] = value - average
    copied = gaps.pop((1, 2))
    assert max(abs(gap) for gap in gaps.values()) <= 0.02
    arthritis = blocks["Arthritis"] + 1
    shortfall = 100 - sum(_numbers(_row(grid28, "2.28", arthritis)))
    assert copied == pytest.approx(weights["Arthritis"] / total * shortfall, abs=0.01)
    assert (
        grid28[(arthritis, columns[2])]
        == grid28[(blocks["Anxiety and Depression"] + 1, columns[2])]
    )


def test_award_volumes_are_the_foi_counts(built):
    _, facts = built
    foi = load_source_package("dwp-pip-daily-living-foi-2025").build_facts(2025)
    counts = {fact.filters["pip_daily_living_award_rate"]: fact.value for fact in foi}
    volumes = {
        fact.filters["pip_daily_living_award_rate"]: fact.value
        for fact in facts
        if _table(fact) == "2.20" and fact.layout.measure_id == "claimants"
    }
    assert volumes == counts == {"enhanced": 1_608_000, "standard": 1_283_000}


def test_tables_2_9_to_2_12_are_the_whole_caseload(built):
    """Their volumes fit Stat-Xplore's caseload at all ages, not its working age."""
    _, facts = built

    def volume(table: str, **filters) -> int:
        (value,) = [
            fact.value
            for fact in facts
            if _table(fact) == table
            and fact.layout.measure_id == "claimants"
            and all(fact.filters.get(k) == v for k, v in filters.items())
        ]
        return value

    cases = load_source_package(CASES_PACKAGE_ID).build_facts(2026)
    by_age: Counter = Counter()
    for fact in cases:
        filters = fact.filters
        if (
            fact.period.value == "2025-01"
            and fact.geography.id in ("E92000001", "W92000004")
            and filters["daily_living_award_status"] == "all"
            and filters["mobility_award_status"] == "all"
        ):
            by_age[filters["age_bands_and_single_year"]] += fact.value
    sixty_to_64 = by_age["60-64"]
    sixty_to_79 = sum(by_age[band] for band in ("60-64", "65-69", "70-74", "75-79"))
    assert (sixty_to_64, sixty_to_79, by_age["all"]) == (503_287, 1_196_452, 3_653_211)
    for table in ("2.9", "2.10"):
        sixty_plus = volume(table, age_band="60_and_over")
        # The 60+ row is all claimants aged 60 to 79, not 60 to 65 ...
        assert abs(sixty_plus / sixty_to_79 - 1) < 0.02
        assert sixty_plus > 2 * sixty_to_64
        # ... and the total the caseload at all ages.
        assert abs(volume(table, age_band="all") / by_age["all"] - 1) < 0.02
    for table in ("2.11", "2.12"):
        total = volume(table, pip_primary_health_condition_group="all")
        assert abs(total / by_age["all"] - 1) < 0.02
    # Table 2.21's 60+ row is the working-age daily living caseload aged 60 to 65.
    assert sixty_to_64 < volume("2.21", age_band="60_and_over") < 0.6 * sixty_to_79


def test_table_2_9_16_to_19_row_is_short_beyond_rounding(workbook):
    """Twelve whole percentages can add to 94 at least; this row adds to 92."""
    grid = workbook[SHEETS["2.9"]]
    heading_row, columns = _heading_row(grid, "2.9")
    row = _one(grid, "16 - 19", rows=range(heading_row + 1, heading_row + 80))[0]
    cells = [grid[(row, column)] for column in columns.values()]
    assert len(cells) == 12 and all(isinstance(cell, int) for cell in cells)
    assert sum(cells) == 92 < 100 - 0.5 * len(cells)
