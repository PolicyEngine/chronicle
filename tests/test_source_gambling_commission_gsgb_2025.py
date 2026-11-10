"""Regression tests for the GSGB 2025 participation facts behind PolicyEngine/microcosm#1381.

The Gambling Commission's Gambling Survey for Great Britain, Annual Report 2025 data
tables (published 16 July 2026): participation in the past 12 months and the past four
weeks by sex, age band, country and English region (B.1 to B.4), by activity (B.9 and
B.10), and the number of activities among people who gambled (B.13). The workbook is
stored in R2 only, so these tests skip when it is neither cached nor fetched.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
import yaml

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.consumer_contract import (
    build_semantic_fact_key,
    consumer_fact_rows,
    validate_consumer_fact_contract,
)
from chronicle.core import validate_facts
from chronicle.dimension_labels import dimension_label_issues
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    read_registered_artifact,
)

ALIAS = "gambling-commission-gsgb-annual-report-2025"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = Path("gambling_commission/gsgb_annual_report_2025")
MANIFEST = REPOSITORY_ROOT / "db" / "data" / DIRECTORY / "manifest.yaml"
WORKBOOK = "GSGB_annual_report_2025_data_tables.xlsx"


def _workbook_bytes() -> bytes:
    try:
        return read_registered_artifact(MANIFEST, 2026)
    except FileNotFoundError as error:
        pytest.skip(f"R2-only GSGB workbook unavailable: {error}")


@pytest.fixture(scope="module")
def facts():
    _workbook_bytes()
    return load_source_package(ALIAS).build_facts(2026)


@pytest.fixture(scope="module")
def cells():
    workbook = openpyxl.load_workbook(
        BytesIO(_workbook_bytes()), read_only=True, data_only=True
    )
    try:
        return {
            name: {
                (cell.row, cell.column_letter): cell.value
                for row in workbook[name].iter_rows()
                for cell in row
                if getattr(cell, "column_letter", None) and cell.value is not None
            }
            for name in (
                "Table B.1",
                "Table B.2",
                "Table B.3",
                "Table B.4",
                "Table B.9",
                "Table B.10",
                "Table B.13",
            )
        }
    finally:
        workbook.close()


def one(facts, **expected):
    """The one fact whose dimensions, concept or geography match ``expected``."""
    matches = [
        fact
        for fact in facts
        if all(
            (
                fact.measure.concept.rsplit(".", 1)[-1]
                if key == "concept"
                else fact.geography.id
                if key == "geography"
                else fact.filters.get(key)
            )
            == value
            for key, value in expected.items()
        )
    ]
    assert len(matches) == 1, (expected, len(matches))
    return matches[0]


def test_package_is_registered_r2_only_and_licence_recorded():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == DIRECTORY
    assert ALIAS in UK_BUNDLE_SOURCES
    manifest = yaml.safe_load(MANIFEST.read_text())
    (entry,) = manifest["files"].values()
    assert entry["sha256"] == (
        "ccee22692bb49f627cec5ed78f7acb5590a87f728de0567e786090f55496f271"
    )
    # No licence is stated, so the bytes live in R2 only and are not committed.
    assert entry["storage"]["local"] is False
    assert entry["storage"]["r2"]["key"].startswith(
        "raw/uk/gambling_commission/gambling-commission-gsgb-annual-report-2025/"
    )
    assert manifest["license"] == "None stated"
    assert "terms-of-use" in manifest["license_evidence"]
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(Path("db/data") / DIRECTORY / WORKBOOK)],
        cwd=REPOSITORY_ROOT,
    )
    assert ignored.returncode == 0


def test_facts_are_valid_labelled_and_unique(facts):
    assert len(facts) == 1024
    assert validate_facts(facts).valid
    assert validate_consumer_fact_contract(facts).valid
    # B.9 and B.10 word row 6 differently. Chronicle's label register gives the
    # value B.10's wording (chronicle#376), and B.9's facts keep their row's
    # text as the package's wording.
    issues = dimension_label_issues(consumer_fact_rows(facts))
    assert [(issue.code, issue.value_id) for issue in issues] == []
    in_person = [
        fact
        for fact in facts
        if fact.layout.groupby_value_id == "national_lottery_draws_in_person"
    ]
    assert {fact.layout.groupby_value_label for fact in in_person} == {
        "Tickets for National Lottery draws bought in person"
    }
    assert {
        fact.filters["source_sheet"]: (
            fact.package_dimension_value_labels.get(
                "gambling_commission.gsgb_activity", {}
            ).get("national_lottery_draws_in_person")
        )
        for fact in in_person
    } == {
        "Table B.9": "Tickets National Lottery draws bought in person",
        "Table B.10": None,
    }
    assert max(Counter(build_semantic_fact_key(f) for f in facts).values()) == 1
    assert Counter(f.filters["source_sheet"] for f in facts) == {
        "Table B.1": 72,
        "Table B.2": 36,
        "Table B.3": 72,
        "Table B.4": 36,
        "Table B.9": 340,
        "Table B.10": 408,
        "Table B.13": 60,
    }
    assert Counter(f.measure.concept for f in facts) == {
        "gambling_commission.gsgb.participation": 870,
        "gambling_commission.gsgb.unweighted_base": 104,
        "gambling_commission.gsgb.activity_count_distribution": 40,
        "gambling_commission.gsgb.mean_activity_count": 10,
    }
    assert {f.period.value for f in facts} == {2025}
    assert {
        (f.period_coverage.start_date, f.period_coverage.end_date) for f in facts
    } == {("2025-01-13", "2026-01-22")}
    assert {f.provenance_class for f in facts} == {"survey_aggregate"}
    assert all(f.source_cell_keys for f in facts)


def test_participation_by_sex_and_age_equals_the_cells(facts, cells):
    for sheet, window in (
        ("Table B.1", "past_12_months"),
        ("Table B.3", "past_4_weeks"),
    ):
        grid = cells[sheet]
        table = [f for f in facts if f.filters["source_sheet"] == sheet]
        for row, sex, band in (
            (3, "all", "all"),
            (4, "male", "all"),
            (12, "all", "age_75_plus"),
            (13, "male", "age_18_to_24"),
            (26, "female", "age_75_plus"),
        ):
            for column, scope in (
                ("B", "any_gambling"),
                ("C", "excluding_lottery_draw_only"),
            ):
                fact = one(
                    table,
                    concept="participation",
                    participation_scope=scope,
                    sex=sex,
                    age_band=band,
                )
                assert fact.value == grid[(row, column)]
                assert fact.filters["participation_window"] == window
            base = one(table, concept="unweighted_base", sex=sex, age_band=band)
            assert base.value == grid[(row, "D")]
            assert base.filters["participation_scope"] == "any_gambling"
    # The headline rates: 59% of adults gambled in the past 12 months, 40% outside
    # lottery draws.
    b1 = [f for f in facts if f.filters["source_sheet"] == "Table B.1"]
    assert (
        round(
            one(
                b1,
                concept="participation",
                participation_scope="any_gambling",
                sex="all",
                age_band="all",
            ).value,
            4,
        )
        == 0.5903
    )
    assert (
        round(
            one(
                b1,
                concept="participation",
                participation_scope="excluding_lottery_draw_only",
                sex="all",
                age_band="all",
            ).value,
            4,
        )
        == 0.4022
    )


def test_adult_universe_and_footnotes_ride_with_the_facts(facts):
    bounds = {
        "all": [(">=", 18)],
        "age_18_to_24": [(">=", 18), ("<", 25)],
        "age_45_to_54": [(">=", 45), ("<", 55)],
        "age_75_plus": [(">=", 75)],
    }
    for fact in facts:
        ages = [(c.operator, c.value) for c in fact.constraints if c.variable == "age"]
        if fact.filters["age_band"] in bounds:
            assert ages == bounds[fact.filters["age_band"]]
        assert ages[0][0] == ">=" and ages[0][1] >= 18
    excluded = [
        f
        for f in facts
        if f.filters.get("participation_scope") == "excluding_lottery_draw_only"
    ]
    assert len(excluded) == 72
    for fact in excluded:
        assert (
            "Excluding participants who had only played National Lottery or other "
            "charity lottery draw based games." in fact.measure.concept_evidence_notes
        )
    for fact in facts:
        if fact.filters["source_sheet"] in {"Table B.1", "Table B.2"}:
            assert "could not be derived for 95" in fact.measure.concept_evidence_notes
        if fact.filters["source_sheet"] in {"Table B.3", "Table B.4"}:
            assert "could not be derived for 299" in fact.measure.concept_evidence_notes


def test_areas_take_their_codes(facts, cells):
    for sheet in ("Table B.2", "Table B.4"):
        table = [f for f in facts if f.filters["source_sheet"] == sheet]
        assert {f.geography.id for f in table} == {
            "E92000001",
            "S92000003",
            "W92000004",
            *(f"E1200000{n}" for n in range(1, 10)),
        }
        london = one(
            table,
            geography="E12000007",
            concept="participation",
            participation_scope="any_gambling",
        )
        assert london.value == cells[sheet][(6, "B")]
        wales = one(table, geography="W92000004", concept="unweighted_base")
        assert wales.value == cells[sheet][(14, "D")]


def test_activities_equal_the_cells_and_restated_rows_are_left_out(facts, cells):
    b9 = [f for f in facts if f.filters["source_sheet"] == "Table B.9"]
    betting_men = one(
        b9,
        concept="participation",
        participation_scope="betting",
        gambling_channel="all",
        sex="male",
        age_band="all",
    )
    assert betting_men.value == cells["Table B.9"][(16, "C")]
    casino_venue = one(
        b9,
        concept="participation",
        participation_scope="casino_games",
        gambling_channel="machine_in_a_venue",
        sex="all",
        age_band="age_18_to_24",
    )
    assert casino_venue.value == cells["Table B.9"][(27, "E")]
    base = one(b9, concept="unweighted_base", sex="all", age_band="age_55_to_64")
    # B.9's bases are its own: 3,540 here, where B.3 prints 3,541.
    assert base.value == cells["Table B.9"][(37, "I")] == 3540
    assert cells["Table B.3"][(10, "D")] == 3541

    b10 = [f for f in facts if f.filters["source_sheet"] == "Table B.10"]
    london_online_casino = one(
        b10,
        geography="E12000007",
        concept="participation",
        participation_scope="casino_games",
        gambling_channel="online",
    )
    assert london_online_casino.value == cells["Table B.10"][(25, "G")]
    scotland_base = one(b10, geography="S92000003", concept="unweighted_base")
    assert scotland_base.value == cells["Table B.10"][(37, "C")] == 1858

    # "Any gambling" in all channels restates B.3 and B.4, so only they carry it.
    for table in (b9, b10):
        assert not [
            f
            for f in table
            if f.filters.get("participation_scope") == "any_gambling"
            and f.filters.get("gambling_channel") == "all"
            and f.measure.concept.endswith("participation")
        ]
    assert cells["Table B.9"][(34, "B")] == cells["Table B.3"][(3, "B")]
    assert cells["Table B.10"][(34, "C")] == cells["Table B.4"][(13, "B")]
    online = one(
        b9,
        concept="participation",
        participation_scope="any_gambling",
        gambling_channel="online",
        sex="all",
        age_band="all",
    )
    assert online.value == cells["Table B.9"][(35, "B")]


def test_number_of_activities_among_gamblers(facts, cells):
    b13 = [f for f in facts if f.filters["source_sheet"] == "Table B.13"]
    assert {f.filters["survey_base"] for f in b13} == {"gambled_in_the_past_four_weeks"}
    seven = one(
        b13,
        concept="activity_count_distribution",
        activity_count_band="seven_or_more",
        sex="all",
        age_band="age_18_to_24",
    )
    assert seven.value == cells["Table B.13"][(6, "E")]
    mean = one(b13, concept="mean_activity_count", sex="all", age_band="all")
    assert mean.value == cells["Table B.13"][(7, "B")]
    assert mean.aggregation.method == "mean"
    # The four bands, the mean and the bases are every B.13 fact: the standard
    # deviation (row 8) has no Chronicle aggregation and stays in the source cells.
    assert cells["Table B.13"][(8, "A")] == "Standard Deviation"
    assert Counter(f.measure.concept.rsplit(".", 1)[-1] for f in b13) == {
        "activity_count_distribution": 40,
        "mean_activity_count": 10,
        "unweighted_base": 10,
    }
    # Weighted bases are left out: the 104 bases are B.1 to B.4's column D and the
    # unweighted-base rows of B.9, B.10 and B.13.
    bases = [f for f in facts if f.measure.concept.endswith("unweighted_base")]
    assert len(bases) == 104
    assert all(
        f.source_record_id.endswith(".unweighted_base")
        or ".base.unweighted_base." in f.source_record_id
        for f in bases
    )
