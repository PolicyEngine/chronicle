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
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import cache
from pathlib import Path
import re
from typing import Any

import pytest
import yaml

from chronicle.source_package import load_source_package

REPO_ROOT = Path(__file__).resolve().parents[1]
IRS_SOI_PACKAGES = REPO_ROOT / "packages" / "irs_soi"
GUIDE_DIR = Path(__file__).resolve().parent / "data" / "irs_soi_doc_guides"
AGI = "us:statutes/26/62#adjusted_gross_income"

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
    all_rows: int  # the US row, the state rows and the district rows
    multi_district_states: int
    above_one_million: int  # stub 9 rows whose mean AGI is above $1,000,000

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
        return self.all_rows - 1


TY2022 = DistrictFile(
    year=2022, all_rows=480, multi_district_states=43, above_one_million=474
)
TY2023 = DistrictFile(
    year=2023, all_rows=481, multi_district_states=44, above_one_million=470
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


@cache
def _values(district: DistrictFile) -> dict[str, float]:
    package = load_source_package(district.package_id)
    return {
        fact.source_record_id: fact.value for fact in package.build_facts(district.year)
    }


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

    assert sorted(record_sets) == sorted(
        [f"{prefix}.all_returns"]
        + [f"{prefix}.agi_{class_id}" for _, class_id in CLASSES]
    )
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


@FILES
def test_class_rows_cover_every_state_and_district_row(district):
    payload = _payload(district.package)
    record_sets = _record_sets(district)
    all_returns = record_sets[f"{district.prefix}.all_returns"]
    geographies = [
        (row["value_id"], row["geography_id"])
        for row in all_returns["rows"]
        if row["value_id"] != "us"
    ]
    selected = payload["artifact"]["selected_rows"]
    all_rows = district.all_rows

    assert len(geographies) == district.class_rows
    # The all-class selections come first, so their virtual rows do not move.
    assert [entry["agi_stub"] for entry in selected[:all_rows]] == [0] * all_rows
    assert [row["row_number"] for row in all_returns["rows"]] == list(
        range(2, all_rows + 2)
    )
    assert len(selected) == all_rows + 9 * district.class_rows
    for stub, class_id in CLASSES:
        rows = record_sets[f"{district.prefix}.agi_{class_id}"]["rows"]
        assert [(row["value_id"], row["geography_id"]) for row in rows] == geographies
        for row in rows:
            entry = selected[row["row_number"] - 2]
            assert entry["agi_stub"] == stub
            assert entry["STATE"] == row["expected_row_header"]


@FILES
def test_classes_add_up_to_the_all_returns_row(district):
    """The file is additive: its nine classes sum exactly to the stub 0 row."""
    values = _values(district)
    prefix = district.prefix
    rows = sorted(
        record_id.removeprefix(f"{prefix}.agi_under_1.").removesuffix(".return_count")
        for record_id in values
        if record_id.startswith(f"{prefix}.agi_under_1.")
        and record_id.endswith(".return_count")
    )

    assert len(rows) == district.class_rows
    assert "us" not in rows
    for row in rows:
        for measure_id in MEASURES:
            classes = sum(
                values[f"{prefix}.agi_{class_id}.{row}.{measure_id}"]
                for _, class_id in CLASSES
            )
            assert classes == values[f"{prefix}.all_returns.{row}.{measure_id}"], (
                row,
                measure_id,
            )


@FILES
def test_class_amounts_fall_inside_the_class_edges(district):
    """Each class row's mean AGI lies inside its declared edges.

    The file rounds return counts to tens and publishes AGI in thousands, so
    the bounds allow five returns and $500 either way. Every TY2022 and TY2023
    row has returns in every class, and the under_1 class's AGI is negative in
    every row.
    """
    values = _values(district)
    record_sets = _record_sets(district)
    for _, class_id in CLASSES:
        record_set = record_sets[f"{district.prefix}.agi_{class_id}"]
        lower, upper = _bounds(record_set["shared_constraints"])
        for row in record_set["rows"]:
            stem = f"{district.prefix}.agi_{class_id}.{row['value_id']}"
            returns = values[f"{stem}.return_count"]
            amount = values[f"{stem}.adjusted_gross_income"]

            assert returns > 0, stem
            if lower is not None:
                assert amount >= lower * (returns - 5) - 500, (stem, amount, returns)
            if upper is not None:
                assert amount <= upper * (returns + 5) + 500, (stem, amount, returns)
            if class_id == "under_1":
                assert amount < 0, stem


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
    its stubs 9 and 10 together.
    """
    guide = _guide_classes(district)
    record_sets = _record_sets(district)
    prefix = district.prefix
    with district.data_file.open(newline="", encoding="utf-8-sig") as file:
        file_stubs = {int(row["agi_stub"]) for row in csv.DictReader(file)}

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

    values = _values(district)
    above_one_million = [
        row["value_id"]
        for row in record_sets[f"{prefix}.agi_500k_plus"]["rows"]
        if values[f"{prefix}.agi_500k_plus.{row['value_id']}.adjusted_gross_income"]
        > 1_000_000 * values[f"{prefix}.agi_500k_plus.{row['value_id']}.return_count"]
    ]
    assert len(above_one_million) == district.above_one_million


@FILES
def test_every_measure_nests_from_districts_to_states_to_the_nation(district):
    """A district row sits under the state row of the same file (chronicle#447).

    For every record set and measure of the package, a state's district rows
    add up exactly to its state row (the 43 TY2022 and 44 TY2023 states with
    more than one district), and in the all-class record set the 51 state rows
    add up to the US row. Every column the packages read nests this way in the
    files; SCHF, which they do not read, does not in 22incd.csv (some state
    rows differ from their districts' sum by a fraction).
    """
    values = _values(district)
    for record_set in _record_sets(district).values():
        prefix = record_set["record_set_id"]
        row_ids = [row["value_id"] for row in record_set["rows"]]
        districts: dict[str, list[str]] = {}
        for row_id in row_ids:
            if row_id != "us" and not row_id.endswith("_total"):
                districts.setdefault(row_id.rsplit("_", 1)[0], []).append(row_id)
        assert len(districts) == district.multi_district_states, prefix
        for measure in record_set["measures"]:
            measure_id = measure["measure_id"]
            for state, members in districts.items():
                total = sum(values[f"{prefix}.{row}.{measure_id}"] for row in members)
                assert total == values[f"{prefix}.{state}_total.{measure_id}"], (
                    prefix,
                    state,
                    measure_id,
                )
            if "us" in row_ids:
                states = sum(
                    values[f"{prefix}.{row}.{measure_id}"]
                    for row in row_ids
                    if row.endswith("_total")
                )
                assert states == values[f"{prefix}.us.{measure_id}"], measure_id
