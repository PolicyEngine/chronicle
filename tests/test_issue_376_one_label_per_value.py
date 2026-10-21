"""One Chronicle-declared label per dimension value (chronicle#376).

Microcosm copies every fact's dimension and value labels into the targets it
compiles, and the calibration-diagnostics dashboard refuses a release whose
targets label one value two ways. IRS SOI's filing-season week-47 package
labelled ``under_1`` of the adjusted-gross-income dimension "No adjusted gross
income and deficit", the IRS's column header, while every other IRS SOI package
writes "No adjusted gross income", and US release
``populace-us-2024-0fb05b6-4b57d15a287c-20260930T150401Z`` carried both. The
bundle check only compared packages built for one year, and Microcosm merges
packages built for different years into one feed.

Each (dimension id, value id) that more than one package emits now has one
label in Chronicle's register, ``chronicle/dimension_values/canonical_labels.json``.
Every fact takes that label when it is built, at any build year, in
``dimension_value_labels`` and ``layout.groupby_value_label``. A package's own
wording, where it differs, is kept in ``publisher_dimension_value_labels``
(``chronicle.consumer_fact.v5``), as chronicle#281 did for geography names. A
value no register entry covers takes its package's label, and two labels for it
are an error wherever Chronicle can see both: inside one package in
``validate-package``, ``build-suite`` and ``build-bundle``, and across packages
in ``build-bundle``. There is no list of accepted exceptions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from chronicle import bundle, dimension_labels
from chronicle.consumer_contract import consumer_fact_rows, write_consumer_facts_jsonl
from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)
from chronicle.suite import build_source_suite
from policyengine_chronicle.consumer import (
    build_consumer_artifact,
    load_consumer_artifact,
)

ADJUSTED_GROSS_INCOME = "us:statutes/26/62#adjusted_gross_income"
WEEK47 = "soi-filing-season-week47-2024-eitc-total"
IRS_SOI_LABEL = "No adjusted gross income"
WEEK47_WORDING = "No adjusted gross income and deficit"
WEEK47_COLUMN_HEADER = "No adjusted gross\nincome and deficit"
FILING_SEASON_LINE = "irs_soi.filing_season_line"
_PACKAGES = Path(__file__).parents[1] / "packages"
_REGISTER = (
    Path(__file__).parents[1]
    / "chronicle"
    / "dimension_values"
    / "canonical_labels.json"
)


def _week47_facts():
    package = load_source_package(WEEK47)
    return package.build_facts(2024, cells=package.build_source_cells(2024))


def _below_one_dollar(facts):
    return [
        fact
        for fact in facts
        if fact.layout.groupby_dimension == ADJUSTED_GROSS_INCOME
        and fact.layout.groupby_value_id == "under_1"
    ]


def _package_rows(source: str, year: int) -> list[dict]:
    package = load_source_package(source)
    facts = package.build_facts(year, cells=package.build_source_cells(year))
    return consumer_fact_rows(facts)


def _week47_copy_with_drifting_line_label(tmp_path: Path) -> Path:
    """A copy of week 47 whose EITC amount row names its line differently."""
    source = _PACKAGES / SOURCE_PACKAGE_ALIASES[WEEK47] / "source_package.yaml"
    package_dir = tmp_path / "week47_drift"
    package_dir.mkdir()
    payload = yaml.safe_load(source.read_text())
    amount = next(
        record_set
        for record_set in payload["record_sets"]
        if record_set["record_set_id"].endswith("eitc_all_returns.amount")
    )
    amount["rows"][0]["label"] = "Earned income credit amount"
    (package_dir / "source_package.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    )
    return package_dir


# The register and the three US labels the maintainer chose.


def test_the_register_holds_the_three_chosen_us_labels():
    assert (
        dimension_labels.canonical_value_label(ADJUSTED_GROSS_INCOME, "under_1")
        == "No adjusted gross income"
    )
    assert (
        dimension_labels.canonical_value_label(ADJUSTED_GROSS_INCOME, "all")
        == "All returns, total"
    )
    assert dimension_labels.canonical_value_label("age", "85_plus") == "Age 85 plus"


def test_the_register_is_one_file_with_one_label_per_value():
    payload = json.loads(_REGISTER.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "chronicle.dimension_value_labels.v1"
    assert payload["labels"]
    for dimension_id, value_labels in payload["labels"].items():
        assert dimension_id.strip() == dimension_id and dimension_id
        for value_id, label in value_labels.items():
            assert isinstance(label, str) and label.strip() == label and label, (
                dimension_id,
                value_id,
            )
    assert dimension_labels.REGISTER_PATH == _REGISTER


def test_there_is_no_list_of_accepted_label_variants():
    assert not hasattr(dimension_labels, "REVIEWED_VALUE_LABEL_VARIANTS")
    assert not hasattr(dimension_labels, "is_reviewed_value_label_variant")
    assert not hasattr(bundle, "_cross_package_value_label_warnings")


# The week-47 package: the register's label, and the IRS wording beside it.


def test_week47_facts_carry_the_register_label_and_keep_the_irs_wording():
    below_one_dollar = _below_one_dollar(_week47_facts())

    assert len(below_one_dollar) == 2
    for fact in below_one_dollar:
        assert fact.dimension_value_labels[ADJUSTED_GROSS_INCOME] == {
            "under_1": IRS_SOI_LABEL
        }
        assert fact.layout.groupby_value_label == IRS_SOI_LABEL
        assert fact.publisher_dimension_value_labels == {
            ADJUSTED_GROSS_INCOME: {"under_1": WEEK47_WORDING}
        }
        assert [
            (constraint.variable, constraint.operator, constraint.value)
            for constraint in fact.constraints
        ] == [(ADJUSTED_GROSS_INCOME, "<", 1)]

    for row in consumer_fact_rows(below_one_dollar):
        assert row["schema_version"] == "chronicle.consumer_fact.v5"
        assert row["dimension_value_labels"][ADJUSTED_GROSS_INCOME] == {
            "under_1": IRS_SOI_LABEL
        }
        assert row["layout"]["groupby_value_label"] == IRS_SOI_LABEL
        assert row["publisher_dimension_value_labels"] == {
            ADJUSTED_GROSS_INCOME: {"under_1": WEEK47_WORDING}
        }


def test_week47_rows_keep_the_irs_wording_checked_against_its_column():
    """The package's row label is the IRS's text, which its column guard checks."""
    package_yaml = _PACKAGES / SOURCE_PACKAGE_ALIASES[WEEK47] / "source_package.yaml"
    package = yaml.safe_load(package_yaml.read_text())
    rows = [
        row
        for record_set in package["record_sets"]
        if record_set["groupby_dimension"] == ADJUSTED_GROSS_INCOME
        for row in record_set["rows"]
        if row["value_id"] == "under_1"
    ]

    assert [(row["label"], row["expected_column_header"]) for row in rows] == [
        (WEEK47_WORDING, WEEK47_COLUMN_HEADER),
        (WEEK47_WORDING, WEEK47_COLUMN_HEADER),
    ]


def test_week47_fact_keys_and_record_set_hashes_are_unchanged():
    """Labels are display metadata: no key moves, and the row text is main's."""
    rows = sorted(
        consumer_fact_rows(_week47_facts()),
        key=lambda row: row["lineage"]["source_record_id"],
    )
    key_fields = [
        [
            row["lineage"]["source_record_id"],
            row["aggregate_fact_key"],
            row["semantic_fact_key"],
            row["legacy_fact_key"],
            row["dimension_set_key"],
        ]
        for row in rows
    ]

    assert len(rows) == 34
    # The 34 facts' keys as built on main at aa288c3.
    assert (
        hashlib.sha256(json.dumps(key_fields).encode()).hexdigest()
        == "ddbdbaca7cbfe0f0a035db899d944e60cf2f1077a89339d3bc54564dbbea28ee"
    )
    assert {
        row["lineage"]["source_record_id"].rsplit(".", 1)[-1]: row["layout"][
            "record_set_spec_hash"
        ]
        for row in rows
        if row["layout"].get("groupby_value_id") == "under_1"
    } == {
        "total_earned_income_credit_returns": "5baf962c82f213018a03f6c3",
        "total_earned_income_credit_amount": "164f9b82a4305158d1a57b85",
    }


def test_a_row_with_the_publisher_wording_loads_with_its_fact_key(tmp_path):
    """The validator's recomputed key ignores the new display field (cf. #284)."""
    facts = _below_one_dollar(_week47_facts())
    facts_path = tmp_path / "consumer_facts.jsonl"
    write_consumer_facts_jsonl(facts, facts_path)

    build_consumer_artifact(tmp_path / "artifact", facts_path=facts_path)
    artifact = load_consumer_artifact(tmp_path / "artifact")

    assert artifact.manifest["consumer_fact_schema_versions"] == [
        "chronicle.consumer_fact.v5"
    ]
    assert sorted(row["aggregate_fact_key"] for row in artifact.rows) == [
        "ledger.aggregate_fact.v2:d7be16a1db07493be1500058",
        "ledger.aggregate_fact.v2:fba2311e623134c71d8c78cd",
    ]
    assert all(
        row["publisher_dimension_value_labels"]
        == {ADJUSTED_GROSS_INCOME: {"under_1": WEEK47_WORDING}}
        for row in artifact.rows
    )


# One label at every build year.


def test_a_value_carries_one_label_across_packages_built_at_different_years():
    """Microcosm merges packages built for different years into one feed.

    Week 47 builds only at 2024 and Publication 1304 Table 1.4 at 2023; ACS
    S0101 builds only at 2024 and the B01001 female table only at 2023. No
    single-year bundle holds both packages of either pair, so the facts must
    agree on their own.
    """
    labels_by_value: dict[tuple[str, str], dict[str, list[str]]] = {}
    for source, year in (
        (WEEK47, 2024),
        ("soi-table-1-4", 2023),
        ("census-acs-s0101-national-age-2024", 2024),
        ("census-b01001-female-age-2023", 2023),
    ):
        for value, labels in bundle._value_labels(_package_rows(source, year)).items():
            for label in labels:
                labels_by_value.setdefault(value, {}).setdefault(label, []).append(
                    source
                )

    assert bundle._cross_package_value_label_errors(labels_by_value) == []
    assert labels_by_value[(ADJUSTED_GROSS_INCOME, "under_1")] == {
        IRS_SOI_LABEL: [WEEK47, "soi-table-1-4"]
    }
    for value_id in ("age_25_to_29", "age_30_to_34", "age_35_to_39", "age_40_to_44"):
        assert list(labels_by_value[("age", value_id)]) == [
            dimension_labels.canonical_value_label("age", value_id)
        ]


def test_a_value_two_packages_label_differently_is_refused_with_its_remedy():
    labels_by_value = {
        ("filing_status", "head_of_household"): {
            "Head of household": ["soi-table-1-2"],
            "Heads of household": ["a-new-package"],
        },
        # A registered value is refused too if two labels reach the bundle:
        # nothing is an accepted exception.
        ("sex", "male"): {"Male": ["ons-a"], "Males": ["nrs-b"]},
        ("filing_status", "all"): {"All filing statuses": ["soi-table-1-1"]},
    }

    errors = bundle._cross_package_value_label_errors(labels_by_value)

    assert [(error.code, error.key) for error in errors] == [
        (
            "conflicting_value_label_across_packages",
            "filing_status=head_of_household",
        ),
        ("conflicting_value_label_across_packages", "sex=male"),
    ]
    message = errors[0].message
    assert "'Heads of household' in ['a-new-package']" in message
    assert "chronicle/dimension_values/canonical_labels.json" in message
    assert "publisher_dimension_value_labels" in message


# One label inside one package, refused as early as validate-package.


def test_validate_package_refuses_a_value_one_package_labels_two_ways(tmp_path):
    package_dir = _week47_copy_with_drifting_line_label(tmp_path)

    report = validate_source_package(package_dir, year=2024)

    issues = [
        issue for issue in report.errors if issue.code == "conflicting_value_label"
    ]
    assert len(issues) == 1
    message = issues[0].message
    assert f"{FILING_SEASON_LINE!r} value 'earned_income_credit'" in message
    assert "'Earned income credit'" in message
    assert "'Earned income credit amount'" in message
    assert "dimension_value_labels" in message
    assert "chronicle/dimension_values/canonical_labels.json" in message


def test_build_suite_refuses_a_value_one_package_labels_two_ways(tmp_path):
    package_dir = _week47_copy_with_drifting_line_label(tmp_path)

    report = build_source_suite(package_dir, tmp_path / "suite", year=2024)

    assert not report.valid
    assert [
        issue.code
        for issue in report.agent_acceptance.errors
        if issue.code == "conflicting_value_label"
    ] == ["conflicting_value_label"]


def test_a_package_declaration_settles_its_own_value_and_keeps_the_rows(tmp_path):
    """A value only one package emits needs no register entry: it declares one."""
    package_dir = _week47_copy_with_drifting_line_label(tmp_path)
    package_yaml = package_dir / "source_package.yaml"
    payload = yaml.safe_load(package_yaml.read_text())
    payload["dimension_value_labels"][FILING_SEASON_LINE] = {
        "earned_income_credit": "Earned income credit"
    }
    package_yaml.write_text(yaml.safe_dump(payload, sort_keys=False))

    assert [
        issue.code
        for issue in validate_source_package(package_dir, year=2024).errors
        if issue.code == "conflicting_value_label"
    ] == []
    package = load_source_package(package_dir)
    facts = package.build_facts(2024, cells=package.build_source_cells(2024))
    amount = next(
        fact
        for fact in facts
        if fact.source_record_id.endswith(
            "eitc_all_returns.earned_income_credit.total_earned_income_credit_amount"
        )
    )
    assert amount.layout.groupby_value_label == "Earned income credit"
    assert amount.publisher_dimension_value_labels == {
        FILING_SEASON_LINE: {"earned_income_credit": "Earned income credit amount"}
    }


def test_the_bundle_refuses_a_value_one_package_labels_two_ways():
    rows = [
        {
            "aggregate_fact_key": f"ledger.aggregate_fact.v2:{label}",
            "dimensions": {},
            "dimension_labels": {FILING_SEASON_LINE: "Filing season line"},
            "dimension_value_labels": {
                FILING_SEASON_LINE: {"earned_income_credit": label}
            },
            "layout": {
                "groupby_dimension": FILING_SEASON_LINE,
                "groupby_dimension_label": "Filing season line",
                "groupby_value_id": "earned_income_credit",
                "groupby_value_label": label,
            },
        }
        for label in ("Earned income credit", "Earned income credit amount")
    ]

    errors, warnings = bundle._dimension_label_reports(WEEK47, rows)

    assert [(error.code, error.key) for error in errors] == [
        (
            "conflicting_groupby_value_label",
            f"{FILING_SEASON_LINE}=earned_income_credit",
        )
    ]
    assert "chronicle/dimension_values/canonical_labels.json" in errors[0].message
    assert warnings == []


def test_irs_soi_packages_label_the_band_below_one_dollar_one_way(tmp_path):
    report = bundle.build_bundle(
        tmp_path / "bundle",
        year=2023,
        sources=[
            WEEK47,
            "soi-historic-table-2",
            "soi-table-2-5-eitc-agi-children-2023",
        ],
    )

    assert report.valid, [issue.to_dict() for issue in report.errors]
    assert [
        issue.to_dict()
        for issue in (*report.errors, *report.warnings)
        if issue.key == f"{ADJUSTED_GROSS_INCOME}=under_1"
    ] == []
