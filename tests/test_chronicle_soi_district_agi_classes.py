"""The congressional-district file's AGI classes (chronicle#447 item 2.1).

``22incd.csv`` publishes ``agi_stub`` 1 to 9 for every state and district row;
its US row has only ``agi_stub`` 0. ``soi-congressional-district-2022`` reads the
return count (``N1``) and AGI (``A00100``) of each class into one record set per
class. The nine classes are the nine of Historic Table 2's TY2022 state AGI
package, whose ``500k_plus`` row adds the file's stubs 9 and 10, so a district
class row can sit under the state row of the same class.

The class rows' selections come after the 480 all-class selections, so the
all-returns rows keep their virtual row numbers and cell addresses.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

from chronicle.source_package import load_source_package

IRS_SOI_PACKAGES = Path(__file__).resolve().parents[1] / "packages" / "irs_soi"
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
