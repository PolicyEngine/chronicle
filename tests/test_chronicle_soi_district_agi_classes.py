"""The congressional-district file's AGI classes (chronicle#447 item 2.1).

``22incd.csv`` publishes ``agi_stub`` 1 to 9 for every state and district row;
its US row has only ``agi_stub`` 0. ``soi-congressional-district-2022`` reads the
return count (``N1``) and AGI (``A00100``) of each class into one record set per
class. The nine classes are the nine of Historic Table 2's TY2022 state AGI
package, whose ``500k_plus`` row adds Historic Table 2's stubs 9 and 10, so a
district class row can sit under the state row of the same class.

The documentation guide lists ten classes, the last two $500,000 under
$1,000,000 and $1,000,000 or more. The file has no stub 10, and its stub 9 is
the guide's 9 and 10 together; the last test below shows why.

The class rows' selections come after the 480 all-class selections, so the
all-returns rows keep their virtual row numbers and cell addresses.
"""

from __future__ import annotations

import csv
from functools import cache
from pathlib import Path
import re
from typing import Any

import yaml

from chronicle.source_package import load_source_package

REPO_ROOT = Path(__file__).resolve().parents[1]
IRS_SOI_PACKAGES = REPO_ROOT / "packages" / "irs_soi"
DATA_FILE = REPO_ROOT / "db/data/irs_soi/congressional_district_2022/22incd.csv"
GUIDE_AGI_STUBS = (
    Path(__file__).resolve().parent
    / "data"
    / "irs_soi_doc_guides"
    / "22incddocguide_agi_stub.tsv"
)
DISTRICT = IRS_SOI_PACKAGES / "congressional_district_2022" / "source_package.yaml"
STATE_AGI = IRS_SOI_PACKAGES / "historic_table_2_state_agi_2022" / "source_package.yaml"
PREFIX = "irs_soi.ty2022.congressional_district_2022"
AGI = "us:statutes/26/62#adjusted_gross_income"

# The file's agi_stub, in order, and the state package's row for that class.
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


@cache
def _payload(path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def _record_sets() -> dict[str, dict[str, Any]]:
    return {
        record_set["record_set_id"]: record_set
        for record_set in _payload(DISTRICT)["record_sets"]
    }


@cache
def _values() -> dict[str, float]:
    package = load_source_package("soi-congressional-district-2022")
    return {fact.source_record_id: fact.value for fact in package.build_facts(2022)}


def test_class_record_sets_copy_the_state_agi_classes():
    state_rows = {
        row["value_id"]: row for row in _payload(STATE_AGI)["record_sets"][0]["rows"]
    }
    record_sets = _record_sets()

    assert sorted(record_sets) == sorted(
        [f"{PREFIX}.all_returns"]
        + [f"{PREFIX}.agi_{class_id}" for _, class_id in CLASSES]
    )
    for stub, class_id in CLASSES:
        record_set = record_sets[f"{PREFIX}.agi_{class_id}"]
        state_row = state_rows[class_id]

        assert record_set["shared_filters"] == {
            "filing_status": "all",
            **state_row["filters"],
        }
        assert record_set["shared_constraints"] == state_row["constraints"]
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


def test_class_rows_cover_every_state_and_district_row():
    payload = _payload(DISTRICT)
    record_sets = _record_sets()
    all_returns = record_sets[f"{PREFIX}.all_returns"]
    geographies = [
        (row["value_id"], row["geography_id"])
        for row in all_returns["rows"]
        if row["value_id"] != "us"
    ]
    selected = payload["artifact"]["selected_rows"]

    assert len(geographies) == 479
    # The all-class selections come first, so their virtual rows do not move.
    assert [entry["agi_stub"] for entry in selected[:480]] == [0] * 480
    assert [row["row_number"] for row in all_returns["rows"]] == list(range(2, 482))
    assert len(selected) == 480 + 9 * 479
    for stub, class_id in CLASSES:
        rows = record_sets[f"{PREFIX}.agi_{class_id}"]["rows"]
        assert [(row["value_id"], row["geography_id"]) for row in rows] == geographies
        for row in rows:
            entry = selected[row["row_number"] - 2]
            assert entry["agi_stub"] == stub
            assert entry["STATE"] == row["expected_row_header"]


def test_classes_add_up_to_the_all_returns_row():
    """The file is additive: its nine classes sum exactly to the stub 0 row."""
    values = _values()
    rows = sorted(
        record_id.removeprefix(f"{PREFIX}.agi_under_1.").removesuffix(".return_count")
        for record_id in values
        if record_id.startswith(f"{PREFIX}.agi_under_1.")
        and record_id.endswith(".return_count")
    )

    assert len(rows) == 479
    assert "us" not in rows
    for row in rows:
        for measure_id in MEASURES:
            classes = sum(
                values[f"{PREFIX}.agi_{class_id}.{row}.{measure_id}"]
                for _, class_id in CLASSES
            )
            assert classes == values[f"{PREFIX}.all_returns.{row}.{measure_id}"], (
                row,
                measure_id,
            )


def test_class_amounts_fall_inside_the_class_edges():
    """Each class row's mean AGI lies inside its declared edges.

    The file rounds return counts to tens and publishes AGI in thousands, so
    the bounds allow five returns and $500 either way. Every TY2022 row has
    returns in every class, and the under_1 class's AGI is negative in all 479.
    """
    values = _values()
    record_sets = _record_sets()
    for _, class_id in CLASSES:
        constraints = {
            constraint["operator"]: constraint["value"]
            for constraint in record_sets[f"{PREFIX}.agi_{class_id}"][
                "shared_constraints"
            ]
            if constraint["variable"] == AGI
        }
        lower, upper = constraints.get(">="), constraints.get("<")
        for row in record_sets[f"{PREFIX}.agi_{class_id}"]["rows"]:
            stem = f"{PREFIX}.agi_{class_id}.{row['value_id']}"
            returns = values[f"{stem}.return_count"]
            amount = values[f"{stem}.adjusted_gross_income"]

            assert returns > 0, stem
            if lower is not None:
                assert amount >= lower * (returns - 5) - 500, (stem, amount, returns)
            if upper is not None:
                assert amount <= upper * (returns + 5) + 500, (stem, amount, returns)
            if class_id == "under_1":
                assert amount < 0, stem


def _guide_classes() -> dict[int, str]:
    lines = [
        line
        for line in GUIDE_AGI_STUBS.read_text().splitlines()
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


def test_classes_follow_the_guide_with_its_top_two_classes_together():
    """The guide's classes 1 to 8 are the file's; its 9 and 10 are the file's 9.

    The guide lists agi_stub 9 as $500,000 under $1,000,000 and 10 as
    $1,000,000 or more, but the file has no stub 10. Its nine classes add up
    exactly to the all-class row (test above), and stub 9's mean AGI is above
    $1,000,000 in 474 of the 479 rows, which a class below $1,000,000 cannot
    be. So the package reads stub 9 as $500,000 or more, the bounds Historic
    Table 2's 2022 state package gives its stubs 9 and 10 together.
    """
    guide = _guide_classes()
    record_sets = _record_sets()
    with DATA_FILE.open(newline="", encoding="utf-8-sig") as file:
        file_stubs = {int(row["agi_stub"]) for row in csv.DictReader(file)}

    assert sorted(guide) == list(range(11))
    assert guide[0] == "No AGI Stub"
    assert file_stubs == set(range(10))
    for stub, class_id in CLASSES:
        bounds = {
            constraint["operator"]: constraint["value"]
            for constraint in record_sets[f"{PREFIX}.agi_{class_id}"][
                "shared_constraints"
            ]
            if constraint["variable"] == AGI
        }
        declared = (bounds.get(">="), bounds.get("<"))
        if stub < 9:
            expected = _guide_edges(guide[stub])
        else:
            expected = (_guide_edges(guide[9])[0], _guide_edges(guide[10])[1])
        # The guide's first class is under $1 with no lower bound, as declared.
        assert declared == expected, (stub, declared, expected)

    values = _values()
    above_one_million = [
        row["value_id"]
        for row in record_sets[f"{PREFIX}.agi_500k_plus"]["rows"]
        if values[f"{PREFIX}.agi_500k_plus.{row['value_id']}.adjusted_gross_income"]
        > 1_000_000 * values[f"{PREFIX}.agi_500k_plus.{row['value_id']}.return_count"]
    ]
    assert len(above_one_million) == 474


def test_every_measure_nests_from_districts_to_states_to_the_nation():
    """A district row sits under the state row of the same file (chronicle#447).

    For every record set and measure of the package, a state's district rows
    add up exactly to its state row (the 43 states with more than one
    district), and in the all-class record set the 51 state rows add up to the
    US row. Every column the package reads nests this way in the file; SCHF,
    which it does not read, does not (some state rows differ from their
    districts' sum by a fraction).
    """
    values = _values()
    for record_set in _record_sets().values():
        prefix = record_set["record_set_id"]
        row_ids = [row["value_id"] for row in record_set["rows"]]
        districts: dict[str, list[str]] = {}
        for row_id in row_ids:
            if row_id != "us" and not row_id.endswith("_total"):
                districts.setdefault(row_id.rsplit("_", 1)[0], []).append(row_id)
        assert len(districts) == 43, prefix
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
