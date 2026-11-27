"""The congressional-district files' AGI classes (chronicle#447 item 2.1).

``22incd.csv`` and ``23incd.csv`` publish ``agi_stub`` 1 to 9 for every state
and district row; their US row has only ``agi_stub`` 0. Each district package
reads the return count (``N1``) and AGI (``A00100``) of each class into one
record set per class. The nine classes are the nine of Historic Table 2's
TY2022 state AGI package, whose ``500k_plus`` row adds Historic Table 2's stubs
9 and 10, so a district class row can sit under the state row of the same
class. Historic Table 2's TY2023 state package publishes those two stubs as
``500k_to_1m`` and ``1m_plus``; its other eight classes are the district
file's.

Both documentation guides list ten classes, the last two $500,000 under
$1,000,000 and $1,000,000 or more. Neither file has a stub 10, and its stub 9
is the guide's 9 and 10 together; the guide test below shows why.

The class rows' selections come after the all-class selections, so the
all-returns rows keep their virtual row numbers and cell addresses.

``soi-congressional-district-2023`` got the TY2022 package's class record sets
and measures in chronicle#449, as its own series: the TY2023 file's districts
are those of the 118th Congress (``tests/test_chronicle_soi_geography_2023.py``).

Which rows give facts (chronicle#449). Every district row gives a fact for
every measure, and each package holds all 436 districts: a jurisdiction with
one district has only a ``CONG_DISTRICT`` 0 row in the file, and that row is its
district (value id ``<state>_00``). The file's United States row and its state
total rows give a fact only where no other IRS package gives the same quantity:
the same semantic key, the same IRS column in Historic Table 2, or one of the
17 tax-form lines of ``PUBLICATION_1304_LINES`` below.
Those totals sit in the ``*_state_totals`` and ``*_us_total`` record sets, under
the source record ids they had before. Checks about the file itself (its
classes add up, its districts add up to its state rows) read the CSV, where
every row still is.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
import re
from typing import Any

import pytest
import yaml

from chronicle.consumer_contract import build_semantic_fact_key
from chronicle.core import GeographyDimension
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package

REPO_ROOT = Path(__file__).resolve().parents[1]
IRS_SOI_PACKAGES = REPO_ROOT / "packages" / "irs_soi"
GUIDE_DIR = Path(__file__).resolve().parent / "data" / "irs_soi_doc_guides"
BOUNDARIES = GUIDE_DIR / "incddocguide_district_boundaries.tsv"
STATE_TOTALS = GUIDE_DIR / "incddocguide_state_totals.tsv"
AGI = "us:statutes/26/62#adjusted_gross_income"
# The 435 House seats and the District of Columbia's delegate district.
DISTRICTS = 436

# The file's agi_stub, in order, and the class's income_range value.
CLASSES = (
    (1, "under_1"),
    (2, "1_to_10k"),
    (3, "10k_to_25k"),
    (4, "25k_to_50k"),
    (5, "50k_to_75k"),
    (6, "75k_to_100k"),
    (7, "100k_to_200k"),
    (8, "200k_to_500k"),
    (9, "500k_plus"),
)
MEASURES = ("return_count", "adjusted_gross_income")


@dataclass(frozen=True)
class DistrictFile:
    """One tax year's district package and the counts its file publishes."""

    year: int
    congress: int  # the Congress whose districts the file uses
    all_rows: int  # the US row, the state rows and the district rows
    multi_district_states: int
    above_one_million: int  # stub 9 rows whose mean AGI is above $1,000,000
    measures: int  # all-returns measures; each of the nine classes has two
    state_total_facts: int  # state totals no other package gives
    us_total_facts: int  # US totals no other package gives

    @property
    def package_id(self) -> str:
        return f"soi-congressional-district-{self.year}"

    @property
    def prefix(self) -> str:
        return f"irs_soi.ty{self.year}.congressional_district_{self.year}"

    @property
    def package(self) -> Path:
        return (
            IRS_SOI_PACKAGES
            / f"congressional_district_{self.year}"
            / "source_package.yaml"
        )

    @property
    def state_agi(self) -> Path:
        return (
            IRS_SOI_PACKAGES
            / f"historic_table_2_state_agi_{self.year}"
            / "source_package.yaml"
        )

    @property
    def data_file(self) -> Path:
        return (
            REPO_ROOT
            / f"db/data/irs_soi/congressional_district_{self.year}"
            / f"{self.year % 100}incd.csv"
        )

    @property
    def guide_agi_stubs(self) -> Path:
        return GUIDE_DIR / f"{self.year % 100}incddocguide_agi_stub.tsv"

    @property
    def class_rows(self) -> int:
        """The file's state and district rows; each has the nine classes."""
        return self.all_rows - 1

    @property
    def district_facts(self) -> int:
        return DISTRICTS * (self.measures + 2 * len(CLASSES))


TY2022 = DistrictFile(
    year=2022,
    congress=117,
    all_rows=480,
    multi_district_states=43,
    above_one_million=474,
    measures=107,
    state_total_facts=1_836,
    us_total_facts=30,
)
TY2023 = DistrictFile(
    year=2023,
    congress=118,
    all_rows=481,
    multi_district_states=44,
    above_one_million=470,
    measures=106,
    state_total_facts=1_938,
    us_total_facts=30,
)
FILES = pytest.mark.parametrize(
    "district", [TY2022, TY2023], ids=lambda district: f"ty{district.year}"
)


@cache
def _payload(path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def _record_sets(district: DistrictFile) -> dict[str, dict[str, Any]]:
    return {
        record_set["record_set_id"]: record_set
        for record_set in _payload(district.package)["record_sets"]
    }


def _district_record_sets(district: DistrictFile) -> list[dict[str, Any]]:
    """The record sets of district rows: all returns, then the nine classes."""
    record_sets = _record_sets(district)
    return [record_sets[f"{district.prefix}.all_returns"]] + [
        record_sets[f"{district.prefix}.agi_{class_id}"] for _, class_id in CLASSES
    ]


@cache
def _facts(district: DistrictFile) -> dict[str, Any]:
    package = load_source_package(district.package_id)
    facts = package.build_facts(district.year)
    by_record = {fact.source_record_id: fact for fact in facts}
    assert len(by_record) == len(facts)
    return by_record


@cache
def _values(district: DistrictFile) -> dict[str, float]:
    return {record_id: fact.value for record_id, fact in _facts(district).items()}


@cache
def _file(district: DistrictFile) -> dict[tuple[str, int, int], dict[str, str]]:
    """The CSV's rows by (STATE, CONG_DISTRICT, agi_stub), read without the package."""
    with district.data_file.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    by_key = {
        (row["STATE"], int(row["CONG_DISTRICT"]), int(row["agi_stub"])): row
        for row in rows
    }
    assert len(by_key) == len(rows)
    return by_key


def _cell(
    district: DistrictFile, state: str, cong_district: int, agi_stub: int, column: str
) -> float:
    """One cell of the CSV, as published (amounts in thousands)."""
    return float(_file(district)[(state, cong_district, agi_stub)][column])


def _file_states(district: DistrictFile) -> dict[int, str]:
    """State FIPS code -> STATE for the file's 51 states."""
    return {
        int(row["STATEFIPS"]): state
        for (state, _, _), row in _file(district).items()
        if state != "US"
    }


def _one_district_states(district: DistrictFile) -> set[str]:
    """The jurisdictions the guide's section D lists with one district."""
    lines = [
        line for line in BOUNDARIES.read_text().splitlines() if not line.startswith("#")
    ]
    (sentence,) = [
        row["one_district_states"]
        for row in csv.DictReader(lines, delimiter="\t")
        if row["guide"] == f"{district.year % 100}incddocguide"
    ]
    match = re.fullmatch(
        r"(\w+) states \(([A-Z, and]+)\) have only one congressional district, "
        r"therefore the matching procedures are not performed on these states\.",
        sentence,
    )
    states = re.findall(r"[A-Z]{2}", match.group(2))
    assert len(states) == len(set(states)) == {"Seven": 7, "Eight": 8}[match.group(1)]
    return set(states)


def _file_geographies(district: DistrictFile) -> dict[str, tuple[str, int]]:
    """GEOID -> (STATE, CONG_DISTRICT) of the CSV row each geography reads.

    Built from the CSV alone. A state with numbered district rows has one
    district for each, and its CONG_DISTRICT 0 row is the state total. A state
    with only a CONG_DISTRICT 0 row has one district, at large, so that row is
    both its district (GEOID district 00, and 98 for the District of Columbia's
    delegate district) and its state total.
    """
    rows = _file(district)
    numbered = {state for state, cong_district, _ in rows if cong_district}
    summary_level = f"500{district.congress % 100:02d}00US"
    geographies = {"0100000US": ("US", 0)}
    for fips, state in _file_states(district).items():
        geographies[f"0400000US{fips:02d}"] = (state, 0)
        if state not in numbered:
            code = "98" if state == "DC" else "00"
            geographies[f"{summary_level}{fips:02d}{code}"] = (state, 0)
    for state, cong_district, agi_stub in rows:
        if cong_district and agi_stub == 0:
            fips = int(rows[(state, cong_district, 0)]["STATEFIPS"])
            geographies[f"{summary_level}{fips:02d}{cong_district:02d}"] = (
                state,
                cong_district,
            )
    return geographies


def _bounds(constraints: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    bounds = {
        constraint["operator"]: constraint["value"]
        for constraint in constraints
        if constraint["variable"] == AGI
    }
    return bounds.get(">="), bounds.get("<")


@FILES
def test_class_record_sets_copy_the_state_agi_classes(district):
    state_rows = {
        row["value_id"]: row
        for row in _payload(district.state_agi)["record_sets"][0]["rows"]
    }
    record_sets = _record_sets(district)
    prefix = district.prefix

    # A class whose state rows Historic Table 2's state package gives has no
    # state totals here; the other keeps the file's (chronicle#449).
    kept_class_totals = [
        f"{prefix}.agi_{class_id}_state_totals"
        for _, class_id in CLASSES
        if class_id not in state_rows
    ]
    assert kept_class_totals == (
        [f"{prefix}.agi_500k_plus_state_totals"] if district.year == 2023 else []
    )
    assert sorted(record_sets) == sorted(
        [
            f"{prefix}.all_returns",
            f"{prefix}.all_returns_state_totals",
            f"{prefix}.all_returns_us_total",
        ]
        + [f"{prefix}.agi_{class_id}" for _, class_id in CLASSES]
        + kept_class_totals
    )
    for record_set_id in kept_class_totals:
        totals = record_sets[record_set_id]
        classes = record_sets[record_set_id.removesuffix("_state_totals")]
        # The totals share the class's record ids, filters, bounds and measures.
        for field in (
            "source_record_id_prefix",
            "shared_filters",
            "shared_constraints",
            "measures",
        ):
            assert totals[field] == classes[field], (record_set_id, field)
        assert totals["record_set_spec_id"] == (
            f"irs_soi.congressional_district_{district.year}.agi_class_state_totals.v1"
        )
        assert {row["table_record_kind"] for row in totals["rows"]} == {"detail"}
    for stub, class_id in CLASSES:
        record_set = record_sets[f"{prefix}.agi_{class_id}"]
        if class_id in state_rows:
            state_row = state_rows[class_id]
            assert record_set["shared_filters"] == {
                "filing_status": "all",
                **state_row["filters"],
            }
            assert record_set["shared_constraints"] == state_row["constraints"]
        else:
            # Historic Table 2's TY2023 state package splits the class in two.
            assert (district.year, class_id) == (2023, "500k_plus")
            assert record_set["shared_filters"] == {
                "filing_status": "all",
                "income_range": "500k_plus",
            }
            assert _bounds(record_set["shared_constraints"]) == (
                _bounds(state_rows["500k_to_1m"]["constraints"])[0],
                _bounds(state_rows["1m_plus"]["constraints"])[1],
            )
        assert [measure["measure_id"] for measure in record_set["measures"]] == list(
            MEASURES
        )
        # Every row of the class reads its own agi_stub.
        assert {
            guard["expected_value"]
            for row in record_set["rows"]
            for guard in row["guard_cells"]
            if guard["label"] == "AGI stub"
        } == {stub}
        assert {row["table_record_kind"] for row in record_set["rows"]} == {"detail"}


def test_ty2023_classes_are_the_ty2022_classes():
    """The TY2023 class record sets take the TY2022 filters and AGI bounds.

    They are a new series (their own record_set_spec_id), so the TY2023
    districts are never read as the TY2022 districts of the same name.
    """
    ty2022, ty2023 = _record_sets(TY2022), _record_sets(TY2023)
    for _, class_id in CLASSES:
        old = ty2022[f"{TY2022.prefix}.agi_{class_id}"]
        new = ty2023[f"{TY2023.prefix}.agi_{class_id}"]

        assert new["shared_filters"] == old["shared_filters"]
        assert new["shared_constraints"] == old["shared_constraints"]
        assert old["record_set_spec_id"] == (
            "irs_soi.congressional_district_2022.agi_class.v1"
        )
        assert new["record_set_spec_id"] == (
            "irs_soi.congressional_district_2023.agi_class.v1"
        )
    labels = [
        _payload(district.package)["dimension_value_labels"]["income_range"]
        for district in (TY2022, TY2023)
    ]
    assert labels[0] == labels[1]


def _file_key(row: dict[str, Any]) -> tuple[str, int, int]:
    """The (STATE, CONG_DISTRICT, agi_stub) a package row's guards name."""
    guards = {guard["label"]: guard["expected_value"] for guard in row["guard_cells"]}
    return (
        row["expected_row_header"],
        guards["congressional district code"],
        guards["AGI stub"],
    )


@FILES
def test_class_rows_cover_every_district_row(district):
    """Each class has the all-returns record set's 436 district rows.

    The selection still lists the file's US row and every state row
    (chronicle#449 moved no row), so each package row keeps its virtual row
    number, also where a total gives no fact any more.
    """
    payload = _payload(district.package)
    record_sets = _record_sets(district)
    all_returns = record_sets[f"{district.prefix}.all_returns"]
    geographies = [
        (row["value_id"], row["geography_id"]) for row in all_returns["rows"]
    ]
    selected = payload["artifact"]["selected_rows"]
    all_rows = district.all_rows

    assert len(geographies) == DISTRICTS
    assert all_rows == 1 + district.multi_district_states + DISTRICTS
    # The all-class selections come first, so their virtual rows do not move.
    assert [entry["agi_stub"] for entry in selected[:all_rows]] == [0] * all_rows
    # The district rows, the kept state totals and the kept US total together
    # read the file's all-class rows, each at the row number it had before.
    all_class_rows = [
        row["row_number"]
        for suffix in (
            "all_returns",
            "all_returns_state_totals",
            "all_returns_us_total",
        )
        for row in record_sets[f"{district.prefix}.{suffix}"]["rows"]
    ]
    assert sorted(set(all_class_rows)) == list(range(2, all_rows + 2))
    assert len(selected) == all_rows + 9 * district.class_rows
    for stub, class_id in CLASSES:
        rows = record_sets[f"{district.prefix}.agi_{class_id}"]["rows"]
        assert [(row["value_id"], row["geography_id"]) for row in rows] == geographies
        assert {_file_key(row)[2] for row in rows} == {stub}
    # Every row of every record set reads the selection its guards name.
    for record_set in record_sets.values():
        for row in record_set["rows"]:
            entry = selected[row["row_number"] - 2]
            assert (
                entry["STATE"],
                entry["CONG_DISTRICT"],
                entry["agi_stub"],
            ) == _file_key(row), (record_set["record_set_id"], row["value_id"])


@FILES
def test_classes_add_up_to_the_all_returns_row(district):
    """The file is additive: its nine classes sum exactly to the stub 0 row.

    That holds in the CSV for each of the file's state and district rows (the
    US row has no classes), and for the facts of each of the 436 districts.
    """
    rows = _file(district)
    record_sets = _record_sets(district)
    prefix = district.prefix
    columns = [
        measure["source_column_id"]
        for measure in record_sets[f"{prefix}.agi_under_1"]["measures"]
    ]
    all_class = [
        (state, cong_district)
        for state, cong_district, agi_stub in rows
        if agi_stub == 0 and state != "US"
    ]

    assert columns == ["N1", "A00100"]
    assert len(all_class) == district.class_rows
    assert [agi_stub for state, _, agi_stub in rows if state == "US"] == [0]
    for state, cong_district in all_class:
        for column in columns:
            classes = sum(
                _cell(district, state, cong_district, stub, column)
                for stub, _ in CLASSES
            )
            assert classes == _cell(district, state, cong_district, 0, column), (
                state,
                cong_district,
                column,
            )

    values = _values(district)
    districts = sorted(
        record_id.removeprefix(f"{prefix}.agi_under_1.").removesuffix(".return_count")
        for record_id in values
        if record_id.startswith(f"{prefix}.agi_under_1.")
        and record_id.endswith(".return_count")
    )

    assert len(districts) == DISTRICTS
    assert "us" not in districts
    assert not any(row.endswith("_total") for row in districts)
    for row in districts:
        for measure_id in MEASURES:
            classes = sum(
                values[f"{prefix}.agi_{class_id}.{row}.{measure_id}"]
                for _, class_id in CLASSES
            )
            assert classes == values[f"{prefix}.all_returns.{row}.{measure_id}"], (
                row,
                measure_id,
            )


def _assert_inside_the_class_edges(
    class_id: str,
    bounds: tuple[int | None, int | None],
    returns: float,
    amount: float,
    where: Any,
) -> None:
    lower, upper = bounds
    assert returns > 0, where
    if lower is not None:
        assert amount >= lower * (returns - 5) - 500, (where, amount, returns)
    if upper is not None:
        assert amount <= upper * (returns + 5) + 500, (where, amount, returns)
    if class_id == "under_1":
        assert amount < 0, where


@FILES
def test_class_amounts_fall_inside_the_class_edges(district):
    """Each class row's mean AGI lies inside its declared edges.

    The file rounds return counts to tens and publishes AGI in thousands, so
    the bounds allow five returns and $500 either way. Every TY2022 and TY2023
    row has returns in every class, and the under_1 class's AGI is negative in
    every row. The check reads every state and district row of the CSV, and
    then every class fact of the package: the districts' and, where a class
    keeps its state totals (chronicle#449), those too.
    """
    record_sets = _record_sets(district)
    bounds = {
        class_id: _bounds(
            record_sets[f"{district.prefix}.agi_{class_id}"]["shared_constraints"]
        )
        for _, class_id in CLASSES
    }
    rows = _file(district)
    for stub, class_id in CLASSES:
        class_rows = [key for key in rows if key[2] == stub]
        assert len(class_rows) == district.class_rows
        for key in class_rows:
            _assert_inside_the_class_edges(
                class_id,
                bounds[class_id],
                float(rows[key]["N1"]),
                1000 * float(rows[key]["A00100"]),
                key,
            )

    values = _values(district)
    checked = 0
    for record_set in record_sets.values():
        class_id = record_set["source_record_id_prefix"].removeprefix(
            f"{district.prefix}.agi_"
        )
        if class_id not in bounds:
            continue
        assert _bounds(record_set["shared_constraints"]) == bounds[class_id]
        for row in record_set["rows"]:
            stem = f"{district.prefix}.agi_{class_id}.{row['value_id']}"
            checked += 2
            _assert_inside_the_class_edges(
                class_id,
                bounds[class_id],
                values[f"{stem}.return_count"],
                values[f"{stem}.adjusted_gross_income"],
                stem,
            )
    # Every class fact of the package was checked.
    assert checked == sum(
        record_id.startswith(f"{district.prefix}.agi_") for record_id in values
    )


def _guide_classes(district: DistrictFile) -> dict[int, str]:
    lines = [
        line
        for line in district.guide_agi_stubs.read_text().splitlines()
        if not line.startswith("#")
    ]
    reader = csv.DictReader(lines, delimiter="\t")
    assert reader.fieldnames == ["agi_stub", "description"]
    return {int(row["agi_stub"]): row["description"] for row in reader}


DOLLARS = r"\$([\d,]+)"


def _guide_edges(description: str) -> tuple[int | None, int | None]:
    """A guide class's AGI bounds: lower inclusive, upper exclusive."""

    def amount(text: str) -> int:
        return int(text.replace(",", ""))

    if match := re.fullmatch(rf"Under {DOLLARS}", description):
        return None, amount(match.group(1))
    if match := re.fullmatch(rf"{DOLLARS} under {DOLLARS}", description):
        return amount(match.group(1)), amount(match.group(2))
    if match := re.fullmatch(rf"{DOLLARS} or more", description):
        return amount(match.group(1)), None
    raise AssertionError(f"Unparsed guide class: {description!r}")


@FILES
def test_classes_follow_the_guide_with_its_top_two_classes_together(district):
    """The guide's classes 1 to 8 are the file's; its 9 and 10 are the file's 9.

    The guide lists agi_stub 9 as $500,000 under $1,000,000 and 10 as
    $1,000,000 or more, but the file has no stub 10. Its nine classes add up
    exactly to the all-class row (test above), and stub 9's mean AGI is above
    $1,000,000 in 474 of the 479 TY2022 rows and 470 of the 480 TY2023 rows,
    which a class below $1,000,000 cannot be. So the package reads stub 9 as
    $500,000 or more, the bounds Historic Table 2's 2022 state package gives
    its stubs 9 and 10 together. The counts are of the file's state and
    district rows, read from the CSV; the stub 9 facts agree with the CSV for
    every row they read.
    """
    guide = _guide_classes(district)
    record_sets = _record_sets(district)
    prefix = district.prefix
    rows = _file(district)
    file_stubs = {agi_stub for _, _, agi_stub in rows}

    assert sorted(guide) == list(range(11))
    assert guide[0] == "No AGI Stub"
    assert file_stubs == set(range(10))
    for stub, class_id in CLASSES:
        declared = _bounds(
            record_sets[f"{prefix}.agi_{class_id}"]["shared_constraints"]
        )
        if stub < 9:
            expected = _guide_edges(guide[stub])
        else:
            expected = (_guide_edges(guide[9])[0], _guide_edges(guide[10])[1])
        # The guide's first class is under $1 with no lower bound, as declared.
        assert declared == expected, (stub, declared, expected)

    stub_9 = [key for key in rows if key[2] == 9]
    above_one_million = {
        key
        for key in stub_9
        if 1000 * float(rows[key]["A00100"]) > 1_000_000 * float(rows[key]["N1"])
    }
    assert len(stub_9) == district.class_rows
    assert len(above_one_million) == district.above_one_million

    values = _values(district)
    stem = f"{prefix}.agi_500k_plus"
    top_class_rows = [
        row
        for record_set in record_sets.values()
        if record_set["source_record_id_prefix"] == stem
        for row in record_set["rows"]
    ]
    # The 436 districts and, in TY2023, the 51 state totals that stay.
    assert len(top_class_rows) == DISTRICTS + (51 if district.year == 2023 else 0)
    assert 2 * len(top_class_rows) == sum(
        record_id.startswith(f"{stem}.") for record_id in values
    )
    for row in top_class_rows:
        above = (
            values[f"{stem}.{row['value_id']}.adjusted_gross_income"]
            > 1_000_000 * values[f"{stem}.{row['value_id']}.return_count"]
        )
        assert above == (_file_key(row) in above_one_million), row["value_id"]


@FILES
def test_every_measure_nests_from_districts_to_states_to_the_nation(district):
    """A district row sits under the state row of the same file (chronicle#447).

    For every record set of district rows and every measure, a state's district
    facts add up exactly to the file's state row, read from the CSV: the row of
    the state's FIPS code with CONG_DISTRICT 0, and the column by its header.
    The package gives a fact for that state cell only where no other package
    gives the quantity (chronicle#449), so the check reads the file for all of
    them. The 43 TY2022 and 44 TY2023 states with more than one district have
    two or more facts to add; a state with one district has the one fact, of
    the same row. In the file, the 51 state rows of the all-class record set
    add up to the US row. Every column the packages read nests this way in the
    files; SCHF, which they do not read, does not in 22incd.csv (some state
    rows differ from their districts' sum by a fraction).
    """
    facts = _facts(district)
    states = _file_states(district)
    assert len(states) == 51
    for record_set in _district_record_sets(district):
        prefix = record_set["record_set_id"]
        (agi_stub,) = {_file_key(row)[2] for row in record_set["rows"]}
        first_measure = record_set["measures"][0]["measure_id"]
        districts: dict[str, list[str]] = defaultdict(list)
        for row in record_set["rows"]:
            geography = facts[f"{prefix}.{row['value_id']}.{first_measure}"].geography
            assert geography.level == "congressional_district", row["value_id"]
            # After 5001700US or 5001800US come the state FIPS code and the
            # district code.
            districts[states[int(geography.id[9:11])]].append(row["value_id"])
        assert len(districts) == 51, prefix
        assert (
            sum(len(members) > 1 for members in districts.values())
            == district.multi_district_states
        ), prefix
        for measure in record_set["measures"]:
            measure_id = measure["measure_id"]
            column = measure["source_column_id"]
            scale = measure.get("value_scale", 1)
            for state, members in districts.items():
                total = sum(
                    facts[f"{prefix}.{row}.{measure_id}"].value for row in members
                )
                assert total == scale * _cell(district, state, 0, agi_stub, column), (
                    prefix,
                    state,
                    measure_id,
                )
            if agi_stub == 0:
                in_states = sum(
                    _cell(district, state, 0, 0, column) for state in states.values()
                )
                assert in_states == _cell(district, "US", 0, 0, column), measure_id


# Label and geography name of each district that is its state's only one.
AT_LARGE_NAMES = {
    "AK": "Alaska Congressional District (at Large)",
    "DC": "District of Columbia Delegate District (at Large)",
    "DE": "Delaware Congressional District (at Large)",
    "MT": "Montana Congressional District (at Large)",
    "ND": "North Dakota Congressional District (at Large)",
    "SD": "South Dakota Congressional District (at Large)",
    "VT": "Vermont Congressional District (at Large)",
    "WY": "Wyoming Congressional District (at Large)",
}


@FILES
def test_each_package_holds_all_436_districts(district):
    """Every district of the Congress has facts, the at-large ones too (chronicle#449).

    The jurisdictions with one district are the ones the guide's section D
    names, and the ones with only a CONG_DISTRICT 0 row in the file. Each is a
    district row with value id ``<state>_00``, the Congress's GEOID with
    district 00 (98 for the District of Columbia's delegate district) and the
    Congress vintage. The other geographies are the 51 states and the United
    States, for the totals that stay.
    """
    facts = _facts(district)
    rows = _file(district)
    geographies = _file_geographies(district)
    one_district = _one_district_states(district)
    numbered = {state for state, cong_district, _ in rows if cong_district}
    summary_level = f"500{district.congress % 100:02d}00US"

    assert one_district == set(_file_states(district).values()) - numbered
    assert len(one_district) == 51 - district.multi_district_states
    assert one_district <= set(AT_LARGE_NAMES)

    levels = Counter(fact.geography.level for fact in facts.values())
    assert levels == {
        "congressional_district": district.district_facts,
        "state": district.state_total_facts,
        "country": district.us_total_facts,
    }
    assert {
        2022: (54_500, 56_366),
        2023: (54_064, 56_032),
    }[district.year] == (district.district_facts, len(facts))
    by_level: dict[str, set[str]] = defaultdict(set)
    for fact in facts.values():
        by_level[fact.geography.level].add(fact.geography.id)
        expected = (
            f"{district.congress}th_congress"
            if fact.geography.level == "congressional_district"
            else "2020_census"
        )
        assert fact.geography.vintage == expected, fact.source_record_id
    assert set().union(*by_level.values()) == set(geographies)
    assert len(by_level["congressional_district"]) == DISTRICTS
    assert all(
        geography_id.startswith(summary_level)
        for geography_id in by_level["congressional_district"]
    )
    assert len(by_level["state"]) == 51
    assert by_level["country"] == {"0100000US"}

    at_large = {
        f"{state.lower()}_00": (
            f"{summary_level}{fips:02d}{'98' if state == 'DC' else '00'}",
            AT_LARGE_NAMES[state],
        )
        for fips, state in _file_states(district).items()
        if state in one_district
    }
    assert at_large["dc_00"][0] == f"{summary_level}1198"
    for record_set in _district_record_sets(district):
        assert len(record_set["rows"]) == DISTRICTS
        found = {
            row["value_id"]: (row["geography_id"], row["geography_name"])
            for row in record_set["rows"]
            if row["value_id"].endswith("_00") or _file_key(row)[1] == 0
        }
        assert found == at_large, record_set["record_set_id"]
        for row in record_set["rows"]:
            if row["value_id"] in at_large:
                assert row["label"] == row["geography_name"]
                assert row["geography_level"] == "congressional_district"
                assert row["geography_vintage"] == f"{district.congress}th_congress"
                assert _file_key(row)[:2] == (row["value_id"][:2].upper(), 0)


@FILES
def test_every_fact_is_the_file_cell_of_its_geography(district):
    """Each fact is the CSV cell of its own geography, class and column.

    The CSV row is found by STATE and CONG_DISTRICT, from the fact's GEOID and
    not from the package's row: a numbered district reads its own row, and an
    at-large district and a kept state total both read their state's
    CONG_DISTRICT 0 row. The class gives the agi_stub and the column is found
    by its header. Amounts are in thousands in the file, except A59664, which
    is in dollars.
    """
    facts = _facts(district)
    geographies = _file_geographies(district)
    stubs = {"all": 0} | {class_id: stub for stub, class_id in CLASSES}
    scales = {
        (record_set["record_set_id"], measure["measure_id"]): measure.get(
            "value_scale", 1
        )
        for record_set in _record_sets(district).values()
        for measure in record_set["measures"]
    }
    read: Counter[tuple[str, int]] = Counter()
    for record_id, fact in facts.items():
        state, cong_district = geographies[fact.geography.id]
        cell = _cell(
            district,
            state,
            cong_district,
            stubs[fact.filters["income_range"]],
            fact.layout.source_column_id,
        )
        scale = scales[(fact.layout.record_set_id, fact.layout.measure_id)]
        assert fact.value == scale * cell, record_id
        if fact.geography.level == "congressional_district":
            read[(state, cong_district)] += 1
    # Each district has every measure, and no district fact reads the
    # CONG_DISTRICT 0 row of a state that has district rows.
    per_district = district.measures + 2 * len(CLASSES)
    assert set(read.values()) == {per_district}
    assert {state for state, cong_district in read if cong_district == 0} == (
        _one_district_states(district)
    )


@FILES
def test_a_state_total_row_is_never_a_district_fact(district):
    """A state's total is not among its districts' values.

    For a state with district rows, in every record set of district rows, the
    return count of the state's CONG_DISTRICT 0 row differs from each district
    fact of the state, and the district facts are the cells of the state's
    numbered rows.
    """
    facts = _facts(district)
    rows = _file(district)
    states = _file_states(district)
    one_district = _one_district_states(district)
    for record_set in _district_record_sets(district):
        prefix = record_set["record_set_id"]
        (agi_stub,) = {_file_key(row)[2] for row in record_set["rows"]}
        returns: dict[str, list[int]] = defaultdict(list)
        for row in record_set["rows"]:
            fact = facts[f"{prefix}.{row['value_id']}.return_count"]
            returns[states[int(fact.geography.id[9:11])]].append(fact.value)
        for state, values in returns.items():
            if state in one_district:
                continue
            numbered = sorted(
                _cell(district, state, cong_district, agi_stub, "N1")
                for row_state, cong_district, row_stub in rows
                if row_state == state and cong_district and row_stub == agi_stub
            )
            assert sorted(values) == numbered, (prefix, state)
            assert _cell(district, state, 0, agi_stub, "N1") not in values, (
                prefix,
                state,
            )


# (package, tax year) pairs with no file: the package cannot be built then.
NO_FILE_FOR_YEAR = {("soi-table-1-3", 2022)}

# The third rule of chronicle#449: United States totals of the district file
# whose tax-form line Publication 1304 gives for the same tax year, in a fact
# with another domain or concept id. No semantic key and no IRS column pairs
# the two, so the pairs are declared here, once: the district measure id, then
# the Publication 1304 package and its source record id after
# ``irs_soi.ty<year>.``. ``{year}`` is the tax year. The district packages'
# comment above ``record_sets:`` points to this list.
TABLE_2_1 = "table_2_1.itemized_all_returns.all"
TABLE_2_5 = "table_2_5.eitc_by_agi_children"
TABLE_2_5_PACKAGE = "soi-table-2-5-eitc-agi-children-{year}"
PUBLICATION_1304_LINES = {
    # Table 2.1, returns with itemized deductions: Schedule A lines 8a, 8b, 8c,
    # 9 and 14, under the district file's measure ids.
    "mortgage_interest_paid_returns": (
        "soi-table-2-1",
        f"{TABLE_2_1}.mortgage_interest_paid_returns",
    ),
    "mortgage_interest_paid_amount": (
        "soi-table-2-1",
        f"{TABLE_2_1}.mortgage_interest_paid_amount",
    ),
    "home_mortgage_personal_seller_returns": (
        "soi-table-2-1",
        f"{TABLE_2_1}.home_mortgage_personal_seller_returns",
    ),
    "home_mortgage_personal_seller_amount": (
        "soi-table-2-1",
        f"{TABLE_2_1}.home_mortgage_personal_seller_amount",
    ),
    "deductible_points_returns": (
        "soi-table-2-1",
        f"{TABLE_2_1}.deductible_points_returns",
    ),
    "deductible_points_amount": (
        "soi-table-2-1",
        f"{TABLE_2_1}.deductible_points_amount",
    ),
    "investment_interest_paid_returns": (
        "soi-table-2-1",
        f"{TABLE_2_1}.investment_interest_paid_returns",
    ),
    "investment_interest_paid_amount": (
        "soi-table-2-1",
        f"{TABLE_2_1}.investment_interest_paid_amount",
    ),
    "charitable_returns": ("soi-table-2-1", f"{TABLE_2_1}.charitable_returns"),
    "charitable_amount": ("soi-table-2-1", f"{TABLE_2_1}.charitable_amount"),
    # Table 2.5: the EITC for no, one and two qualifying children.
    "eitc_no_children_claims": (
        TABLE_2_5_PACKAGE,
        f"{TABLE_2_5}.no_qualifying_children.total.eitc_returns",
    ),
    "eitc_no_children_amount": (
        TABLE_2_5_PACKAGE,
        f"{TABLE_2_5}.no_qualifying_children.total.eitc_total",
    ),
    "eitc_one_child_claims": (
        TABLE_2_5_PACKAGE,
        f"{TABLE_2_5}.one_qualifying_child.total.eitc_returns",
    ),
    "eitc_one_child_amount": (
        TABLE_2_5_PACKAGE,
        f"{TABLE_2_5}.one_qualifying_child.total.eitc_total",
    ),
    "eitc_two_children_claims": (
        TABLE_2_5_PACKAGE,
        f"{TABLE_2_5}.two_qualifying_children.total.eitc_returns",
    ),
    "eitc_two_children_amount": (
        TABLE_2_5_PACKAGE,
        f"{TABLE_2_5}.two_qualifying_children.total.eitc_total",
    ),
    # Table 1.4: the self-employed retirement plans deduction. Its returns
    # count has no Publication 1304 line, so that US total stays.
    "self_employed_retirement_plans_amount": (
        "soi-table-1-4",
        "table_1_4.all.self_employed_pension_contribution_ald",
    ),
}


@cache
def _semantic_keys(district: DistrictFile) -> dict[str, str]:
    """Semantic fact key by source record id."""
    return {
        record_id: build_semantic_fact_key(fact)
        for record_id, fact in _facts(district).items()
    }


@cache
def _other_irs_facts(year: int) -> dict[str, tuple[Any, ...]]:
    """Package -> facts, for every other ``soi-*`` package of a tax year.

    Each package is built at the tax year. A package pinned to another year's
    file (``artifact_year``) gives that year's facts at any build year, so it
    is left out.
    """
    facts: dict[str, tuple[Any, ...]] = {}
    for package_id in sorted(SOURCE_PACKAGE_ALIASES):
        if not package_id.startswith("soi-") or package_id.startswith(
            "soi-congressional-district-"
        ):
            continue
        package = load_source_package(package_id)
        if package.artifact.artifact_year not in (None, year):
            continue
        if (package_id, year) in NO_FILE_FOR_YEAR:
            with pytest.raises(ValueError, match="No source artifact for year"):
                package.build_facts(year)
            continue
        facts[package_id] = tuple(package.build_facts(year))
        assert {str(fact.period.value) for fact in facts[package_id]} == {str(year)}, (
            package_id
        )
    return facts


@cache
def _other_irs_keys(year: int) -> dict[str, frozenset[str]]:
    """Package -> semantic fact keys of its facts of the tax year."""
    return {
        package_id: frozenset(build_semantic_fact_key(fact) for fact in facts)
        for package_id, facts in _other_irs_facts(year).items()
    }


def _column_read(fact: Any, column: str | None = None) -> tuple[str, str, str]:
    """A fact's geography level, class of returns and IRS column."""
    return (
        fact.geography.level,
        fact.filters["income_range"],
        column or fact.layout.source_column_id,
    )


@cache
def _historic_table_2_columns(year: int) -> frozenset[tuple[str, str, str]]:
    """The IRS columns the tax year's Historic Table 2 packages read.

    Each entry is a level, a class of returns and a column: the state packages
    give ``("state", "all", "N1")``. Historic Table 2's TY2022 national and
    state AGI packages declare no column id for some measures (returns, AGI,
    the EITC total and others); the layout repeats the measure id then, and the
    entry holds that.
    """
    return frozenset(
        _column_read(fact)
        for package_id, facts in _other_irs_facts(year).items()
        if package_id.startswith("soi-historic-table-2")
        for fact in facts
    )


def _in_historic_table_2(fact: Any, year: int) -> bool:
    """Whether Historic Table 2 reads a fact's column at its level and class.

    The fact's measure id is compared too, for the Historic Table 2 measures
    without a declared column id: the district packages use the same measure
    ids for those columns.
    """
    return not _historic_table_2_columns(year).isdisjoint(
        {_column_read(fact), _column_read(fact, fact.layout.measure_id)}
    )


def _publication_1304_records(district: DistrictFile) -> dict[str, tuple[str, str]]:
    """District measure id -> (package, source record id) for the tax year."""
    year = district.year
    return {
        measure_id: (package_id.format(year=year), f"irs_soi.ty{year}.{record}")
        for measure_id, (package_id, record) in PUBLICATION_1304_LINES.items()
    }


def _publication_1304_us_totals(district: DistrictFile) -> set[str]:
    """Source record ids of the US totals that rule 3 pairs."""
    return {
        f"{district.prefix}.all_returns.us.{measure_id}"
        for measure_id in PUBLICATION_1304_LINES
    }


def _constraint_set(fact: Any) -> set[tuple[str, str, Any]]:
    return {
        (constraint.variable, constraint.operator, constraint.value)
        for constraint in fact.constraints
    }


@FILES
def test_publication_1304_gives_each_paired_us_line(district):
    """Each pair of ``PUBLICATION_1304_LINES`` is one tax-form line, twice.

    The Publication 1304 record is in its package built at the tax year. It is
    a United States fact of that tax year for all returns, in the district
    measure's unit and with the same qualifying-children constraint, and its
    domain or its concept id is another: that is why no semantic key pairs the
    two. Its value is close to the district file's US cell, read from the CSV,
    and above it: the district file protects small cells and leaves out returns
    that match no district by ZIP code. Over the 17 pairs and both years the
    cell is 0.8307 to 0.9895 of the Publication 1304 value, so the bound is
    0.80 to 1. A line of the wrong size fails it;
    ``tests/test_chronicle_soi_doc_guide_columns.py`` tells line 8a from the
    line 10 total, which is inside the bound.
    """
    year = district.year
    facts = _facts(district)
    others = _other_irs_facts(year)
    all_returns = _record_sets(district)[f"{district.prefix}.all_returns"]
    measures = {measure["measure_id"]: measure for measure in all_returns["measures"]}
    a_district = all_returns["rows"][0]["value_id"]
    pairs = _publication_1304_records(district)

    assert len(pairs) == 17
    assert {package_id for package_id, _ in pairs.values()} == {
        "soi-table-1-4",
        "soi-table-2-1",
        f"soi-table-2-5-eitc-agi-children-{year}",
    }
    assert len(set(pairs.values())) == 17
    ratios = {}
    for measure_id, (package_id, record_id) in pairs.items():
        (paired,) = [
            fact for fact in others[package_id] if fact.source_record_id == record_id
        ]
        measure = measures[measure_id]
        district_fact = facts[
            f"{district.prefix}.all_returns.{a_district}.{measure_id}"
        ]
        us_cell = measure.get("value_scale", 1) * _cell(
            district, "US", 0, 0, measure["source_column_id"]
        )

        assert (paired.geography.level, paired.geography.id) == (
            "country",
            "0100000US",
        ), measure_id
        assert (paired.period.type, paired.period.value) == ("tax_year", year)
        assert paired.filters["income_range"] == "all", measure_id
        assert paired.measure.unit == district_fact.measure.unit, measure_id
        assert _constraint_set(paired) == _constraint_set(district_fact), measure_id
        assert (paired.domain, paired.measure.concept) != (
            district_fact.domain,
            district_fact.measure.concept,
        ), measure_id
        if package_id == "soi-table-2-1":
            # Table 2.1 uses the district file's measure id and concept id; its
            # domain is the returns with itemized deductions.
            assert record_id.endswith(f".{measure_id}")
            assert paired.measure.concept == district_fact.measure.concept
        ratios[measure_id] = us_cell / paired.value
        assert f"{district.prefix}.all_returns.us.{measure_id}" not in facts
    assert {
        measure_id: round(ratio, 4)
        for measure_id, ratio in ratios.items()
        if not 0.80 <= ratio < 1.0
    } == {}
    assert (round(min(ratios.values()), 4), round(max(ratios.values()), 4)) == {
        2022: (0.8308, 0.9895),
        2023: (0.8307, 0.9859),
    }[year]


@FILES
def test_no_fact_repeats_a_quantity_another_irs_package_gives(district):
    """No district-file fact repeats what another package gives (chronicle#449).

    Three checks. First, no fact has the semantic key of a fact of another
    ``soi-*`` package of the tax year: Historic Table 2 (national and state),
    the Publication 1304 tables, the state data and the rest. Second, no total
    that stays reads an IRS column that a Historic Table 2 package of the tax
    year reads at the same level for the same class of returns. The second
    check is there because the two files give some columns different concept
    ids (A00900, A01700, A06500, A25870, A26270 and their N columns) and
    Historic Table 2's state EITC package has another domain, so the keys
    differ where the column and its guide text are the same. Third, none of
    the 17 United States totals of ``PUBLICATION_1304_LINES`` is a fact. The
    first two are derived here, and only sets of keys and of columns are
    compared.
    """
    year = district.year
    facts = _facts(district)
    others = _other_irs_keys(year)
    keys = _semantic_keys(district)

    assert {
        "soi-historic-table-2" if year == 2022 else f"soi-historic-table-2-{year}",
        f"soi-historic-table-2-state-agi-{year}",
        f"soi-historic-table-2-state-broad-{year}",
        f"soi-historic-table-2-state-eitc-{year}",
        "soi-table-1-1",
        "soi-table-1-2",
        "soi-table-1-4",
        "soi-table-2-1",
        f"soi-state-{year}",
    } <= set(others)
    assert ("soi-table-1-3" in others) == (year == 2023)
    assert len(set(keys.values())) == len(keys)
    shared = {
        record_id: package_id
        for package_id, package_keys in others.items()
        for record_id, key in keys.items()
        if key in package_keys
    }
    assert shared == {}

    assert {
        ("country", "all", "A00900"),
        ("state", "all", "N1"),
        ("state", "all", "N59661"),
        ("state", "under_1", "A00300"),
    } <= _historic_table_2_columns(year)
    repeated = {
        record_id: _column_read(fact)
        for record_id, fact in facts.items()
        if fact.geography.level != "congressional_district"
        and _in_historic_table_2(fact, year)
    }
    assert repeated == {}

    assert not _publication_1304_us_totals(district) & set(facts)


@FILES
def test_a_total_stays_only_where_no_other_package_gives_it(district):
    """The ruling of chronicle#449, checked for every total of the file.

    The file has a state row for each of the 51 states in every record set of
    district rows, and a US row for all returns. For each of those rows and
    each measure, the test builds the semantic key the total has: the key of a
    district fact of the measure, with the total's geography. Another package
    gives the total when (1) a ``soi-*`` package of the tax year has that key,
    (2) a Historic Table 2 package of the tax year reads the same IRS column
    at the same level for the same class of returns, or (3) it is one of the
    17 United States totals of ``PUBLICATION_1304_LINES``. The total is a fact
    exactly when none of the three gives it, and a total that stays keeps the
    source record id it had before. Rules 1 and 2 are derived here, with no
    list of measures; rule 3's pairs are the declared list, and they are the
    only totals that rule 3 alone removes. The counts and the examples below
    follow.
    """
    facts = _facts(district)
    keys = _semantic_keys(district)
    taken = frozenset().union(*_other_irs_keys(district.year).values())
    state_totals = {
        f"{state.lower()}_total": GeographyDimension(
            level="state", id=f"0400000US{fips:02d}", vintage="2020_census"
        )
        for fips, state in _file_states(district).items()
    }
    us_total = {
        "us": GeographyDimension(level="country", id="0100000US", vintage="2020_census")
    }
    publication_1304_lines = _publication_1304_us_totals(district)
    kept: set[str] = set()
    dropped: set[str] = set()
    by_column_only: set[str] = set()
    by_line_only: set[str] = set()
    for record_set in _district_record_sets(district):
        prefix = record_set["source_record_id_prefix"]
        a_district = record_set["rows"][0]["value_id"]
        # The file's US row has only agi_stub 0.
        totals = state_totals | (us_total if prefix.endswith(".all_returns") else {})
        for measure in record_set["measures"]:
            measure_id = measure["measure_id"]
            district_fact = facts[f"{prefix}.{a_district}.{measure_id}"]
            for value_id, geography in totals.items():
                record_id = f"{prefix}.{value_id}.{measure_id}"
                total = replace(district_fact, geography=geography)
                key = build_semantic_fact_key(total)
                same_key = key in taken
                same_column = _in_historic_table_2(total, district.year)
                same_line = record_id in publication_1304_lines
                if same_key or same_column or same_line:
                    assert record_id not in facts, record_id
                    dropped.add(record_id)
                    if same_column and not same_key:
                        by_column_only.add(record_id)
                    if not (same_key or same_column):
                        by_line_only.add(record_id)
                else:
                    assert keys.get(record_id) == key, record_id
                    kept.add(record_id)

    totals_in_package = {
        record_id
        for record_id, fact in facts.items()
        if fact.geography.level != "congressional_district"
    }
    assert kept == totals_in_package
    assert len(kept) == district.state_total_facts + district.us_total_facts
    # 4,539 state and 77 US totals in TY2022, 4,386 and 76 in TY2023.
    assert len(dropped) == {2022: 4_616, 2023: 4_462}[district.year]
    # Each of the 17 pairs is needed: neither a key nor a column removes it.
    assert by_line_only == publication_1304_lines
    assert len(by_line_only) == 17
    # The totals sit in their own record sets, apart from the district rows.
    for record_id, fact in facts.items():
        record_set_id = fact.layout.record_set_id
        expected = {
            "congressional_district": "",
            "state": "_state_totals",
            "country": "_us_total",
        }[fact.geography.level]
        assert record_set_id == record_id.rsplit(".", 2)[0] + expected, record_id
    examples = {
        # Historic Table 2 gives the national and the state AGI and returns.
        "all_returns.us.adjusted_gross_income": False,
        "all_returns.al_total.return_count": False,
        # Historic Table 2 reads the same column under another concept id
        # (A00900), or in a package with another domain (N59660).
        "all_returns.us.schedule_c_income_amount": False,
        "all_returns.al_total.eitc_claims": False,
        # Publication 1304 gives Schedule A line 8a for the nation in Table
        # 2.1, for returns with itemized deductions, and the self-employed
        # retirement plans deduction in Table 1.4 under another concept id.
        "all_returns.us.mortgage_interest_paid_amount": False,
        "all_returns.us.self_employed_retirement_plans_amount": False,
        # No package gives the returns with that deduction or the total tax
        # liability for the nation, or the standard deduction of a state.
        "all_returns.us.self_employed_retirement_plans_returns": True,
        "all_returns.us.total_tax_liability_amount": True,
        "all_returns.al_total.standard_deduction_amount": True,
        # Historic Table 2's TY2023 state package splits $500,000 or more in two.
        "agi_500k_plus.al_total.return_count": district.year == 2023,
        "agi_under_1.al_total.return_count": False,
    }
    for record, stays in examples.items():
        assert (f"{district.prefix}.{record}" in kept) == stays, record
        assert (f"{district.prefix}.{record}" in dropped) != stays, record
    assert {
        f"{district.prefix}.all_returns.us.schedule_c_income_amount",
        f"{district.prefix}.all_returns.al_total.eitc_claims",
    } <= by_column_only


def test_each_guide_sends_the_reader_to_historic_table_2_for_state_totals():
    """Why a state total gives no fact where Historic Table 2 gives the
    quantity (chronicle#449): each guide says that the file's State totals may
    not be comparable to the ones SOI publishes elsewhere, and its footnote 2
    names Historic Table 2 for complete State tabulations. The sentences are
    the guides' own (``incddocguide_state_totals.tsv``)."""
    header, *guides = [
        line.split("\t")
        for line in STATE_TOTALS.read_text().splitlines()
        if not line.startswith("#")
    ]

    assert header == ["guide", "state_totals", "footnote_2"]
    assert [guide for guide, _, _ in guides] == ["22incddocguide", "23incddocguide"]
    for _, sentence, footnote in guides:
        assert sentence.lower().startswith("state totals within the congressional data")
        assert (
            "may not be comparable to State totals published elsewhere by SOI "
            "because of disclosure protection procedures or the exclusion of "
            "returns that did not match based on the ZIP code." in sentence
        )
        assert sentence.endswith("See footnote for complete State totals. [2]")
        assert footnote.startswith(
            "[2] For complete individual income tax tabulations at the State "
            "level, see the historic table posted to Tax Stats at "
        )
        assert "historic-table-2" in footnote.lower()
