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
wording, where it differs, is kept in ``package_dimension_value_labels``
(``chronicle.consumer_fact.v5``). That wording is the package's, not
necessarily the publisher's: often it is text Chronicle wrote, so the field
says so and nothing presents it as the publisher's text. A
value no register entry covers takes its package's label, and two labels for it
are an error wherever Chronicle can see both: inside one package in
``validate-package``, ``build-suite`` and ``build-bundle``, and across packages
in ``build-bundle``. There is no list of accepted exceptions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import openpyxl
import pytest
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
_REGISTER_PATH_TEXT = "chronicle/dimension_values/canonical_labels.json"
_HARNESS_DOC = Path(__file__).parents[1] / "docs" / "agent-source-package-harness.md"
_ONS_CONSUMER_TRENDS = (
    Path(__file__).parents[1]
    / "db"
    / "data"
    / "ons"
    / "consumer_trends_current_price_2026"
    / "cpnsa.xlsx"
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
        assert fact.package_dimension_value_labels == {
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
        assert row["package_dimension_value_labels"] == {
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
        row["package_dimension_value_labels"]
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
    unlisted, listed = errors[0].message, errors[1].message
    assert "'Heads of household' in ['a-new-package']" in unlisted
    # Two packages emit it, so only a register entry can apply, and the
    # message says how to choose its label.
    assert f"Add it to {_REGISTER_PATH_TEXT}" in unlisted
    assert "the wording most of these packages use" in unlisted
    assert "national statistics office" in unlisted
    assert "scripts/build_dimension_value_register.py --static-check" in unlisted
    # Two packages word it differently, so the script that regenerates the
    # register needs the chosen label too, or it no longer reproduces the
    # register (chronicle#377 re-check, N2).
    assert (
        "add that label to CHOSEN_LABELS in "
        "scripts/build_dimension_value_register.py"
    ) in unlisted
    assert "dimension_value_labels" not in unlisted.replace(
        "package_dimension_value_labels", ""
    )
    # A listed value already has its label: the message names it.
    assert "Chronicle's register labels this value 'Male'" in listed
    assert "rebuild" in listed
    assert "Add it to" not in listed
    assert "CHOSEN_LABELS" not in listed


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
    # One package emits it and the register does not list it: the one remedy
    # is a declaration in this package.
    assert "Declare one label for it in this package's dimension_value_labels" in (
        message
    )
    assert _REGISTER_PATH_TEXT not in message


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
    assert amount.package_dimension_value_labels == {
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
    assert "Declare one label for it in this package's dimension_value_labels" in (
        errors[0].message
    )
    assert _REGISTER_PATH_TEXT not in errors[0].message
    assert warnings == []


def test_a_listed_value_labelled_two_ways_in_old_rows_names_the_register_label():
    """Rows built before the register (or by hand) can still disagree."""
    rows = [
        {
            "aggregate_fact_key": f"ledger.aggregate_fact.v2:{label}",
            "dimensions": {"sex": "male"},
            "dimension_labels": {"sex": "Sex"},
            "dimension_value_labels": {"sex": {"male": label}},
            "layout": {},
        }
        for label in ("Male", "Males")
    ]

    errors, _warnings = bundle._dimension_label_reports("nrs-a", rows)

    assert [(error.code, error.key) for error in errors] == [
        ("conflicting_dimension_value_label", "sex=male")
    ]
    assert "Chronicle's register labels this value 'Male'" in errors[0].message
    assert "Declare one label" not in errors[0].message


# A package declaration cannot contradict the register (chronicle#377 review).


def test_validate_package_refuses_a_declaration_the_register_contradicts(tmp_path):
    package_dir = _week47_copy_with_drifting_line_label(tmp_path)
    package_yaml = package_dir / "source_package.yaml"
    payload = yaml.safe_load(package_yaml.read_text())
    payload["dimension_value_labels"][ADJUSTED_GROSS_INCOME] = {
        "under_1": WEEK47_WORDING
    }
    package_yaml.write_text(yaml.safe_dump(payload, sort_keys=False))

    issues = [
        issue
        for issue in validate_source_package(package_dir, year=2024).errors
        if issue.code == "declared_value_label_differs_from_register"
    ]

    assert len(issues) == 1
    message = issues[0].message
    assert (
        f"dimension_value_labels.{ADJUSTED_GROSS_INCOME}.under_1 declares "
        f"{WEEK47_WORDING!r}"
    ) in message
    assert f"labels this value {IRS_SOI_LABEL!r}" in message
    assert _REGISTER_PATH_TEXT in message
    assert f"Change the declaration to {IRS_SOI_LABEL!r}" in message
    assert str(package_yaml) in message or "source_package.yaml" in message


@pytest.mark.parametrize(
    ("package_dir", "dimension_id", "value_id", "register_label"),
    [
        ("nrs/mye_2025_council_area", "sex", "female", "Female"),
        ("nrs/mye_2025_council_area", "sex", "male", "Male"),
        ("nisra/mye_2025_lgd_single_year_age", "sex", "female", "Female"),
        ("nisra/mye_2025_lgd_single_year_age", "sex", "male", "Male"),
        ("nrs/pcon24_population_by_age_2024_revised_2026", "sex", "female", "Female"),
        ("nrs/pcon24_population_by_age_2024_revised_2026", "sex", "male", "Male"),
        (
            "ons/hpssa_pcon24_year_ending_march_2026",
            "property_type",
            "detached",
            "Detached",
        ),
        (
            "ons/hpssa_pcon24_year_ending_march_2026",
            "property_type",
            "semi_detached",
            "Semi detached",
        ),
        (
            "ons/hpssa_pcon24_year_ending_march_2026",
            "property_type",
            "terraced",
            "Terraced",
        ),
        ("ons/pipr_rents_by_area_august_2026", "property_type", "detached", "Detached"),
        ("ons/pipr_rents_by_area_august_2026", "property_type", "terraced", "Terraced"),
        ("dft/nts0601_age_mode_trips_2025", "age_band", "30 to 39", "30 to 39"),
        ("dft/nts0601_age_mode_trips_2025", "age_band", "40 to 49", "40 to 49"),
    ],
)
def test_the_declarations_the_register_overrode_now_agree_with_it(
    package_dir, dimension_id, value_id, register_label
):
    """The 13 declarations the register silently overrode at e29da32."""
    payload = yaml.safe_load(
        (_PACKAGES / package_dir / "source_package.yaml").read_text()
    )

    assert dimension_labels.canonical_value_label(dimension_id, value_id) == (
        register_label
    )
    assert payload["dimension_value_labels"][dimension_id][value_id] == register_label


# The package's own wording: a field that says what it holds.

# Each wording is text Chronicle wrote, not the publisher's (the chronicle#377
# source-fidelity, contract and boundary reviews): a curated extract's value
# id, a parser's constant, or a package author's phrase. Each must be kept in a
# field that names it as the package's wording and says it is unchecked.
_CHRONICLE_WRITTEN_WORDINGS = [
    # The Statbel ZIP has single-year CD_AGE only; "65_plus" is the curated
    # CSV's value id.
    (
        "statbel-population-structure-2025",
        2025,
        "person.age_band",
        "65_plus",
        "65_plus",
    ),
    # The B01001 JSON holds variable codes and numbers; the text is
    # B01001_FEMALE_AGE_COLUMNS and the parser's sex column.
    ("census-b01001-female-age-2023", 2023, "age", "age_20", "Female 20 years"),
    ("census-b01001-female-age-2023", 2023, "sex", "female", "female"),
    # Eurostat calls D1 "First decile"; the guard checks the code D1.
    (
        "eurostat-ilc-di01",
        2023,
        "quant_inc",
        "d1",
        "First income decile cut-point",
    ),
    # The four Belgian country-total rows: guards check Chronicle identifiers.
    (
        "spf-finances-pit-2023",
        2023,
        "measure",
        "country_total",
        "Belgium PIT federal and local tax before withholding",
    ),
    (
        "onem-rva-unemployment-2024",
        2023,
        "measure",
        "country_total",
        "Complete unemployment benefit recipients",
    ),
    (
        "nbb-national-accounts-household-disposable-income-2024",
        2023,
        "measure",
        "country_total",
        "Household disposable income gross",
    ),
    (
        "onss-contributions-2024",
        2023,
        "measure",
        "country_total",
        "Worker-borne personal social security contributions",
    ),
    # The guard checks the code B2G in column D.
    (
        "eurostat-nasa-10-nf-tr",
        2023,
        "na_item",
        "belgium_household_operating_surplus_gross",
        "Operating surplus, gross (B.2G), paid-direction cell",
    ),
    # The guard checks the code sociale_toeslag.
    (
        "opgroeien-groeipakket-caseload-2025",
        2023,
        "groeipakket.component",
        "sociale_toeslag",
        "Social supplement child caseload",
    ),
]


@pytest.mark.parametrize(
    ("source", "year", "dimension_id", "value_id", "wording"),
    _CHRONICLE_WRITTEN_WORDINGS,
)
def test_text_chronicle_wrote_is_kept_as_the_packages_wording_not_the_publishers(
    source, year, dimension_id, value_id, wording
):
    package = load_source_package(source)
    facts = package.build_facts(year, cells=package.build_source_cells(year))
    rows = consumer_fact_rows(facts)
    description = json.loads(
        (
            Path(__file__).parents[1]
            / "docs"
            / "schemas"
            / "consumer_fact.v5.schema.json"
        ).read_text()
    )["properties"]["package_dimension_value_labels"]["description"]

    wordings = {
        fact.package_dimension_value_labels.get(dimension_id, {}).get(value_id)
        for fact in facts
    }
    assert wording in wordings
    assert all("publisher_dimension_value_labels" not in row for row in rows)
    assert any(
        (row.get("package_dimension_value_labels") or {})
        .get(dimension_id, {})
        .get(value_id)
        == wording
        for row in rows
    )
    assert "text Chronicle wrote" in description


def test_nts0601_age_bands_now_carry_dfts_header_and_no_package_wording():
    """NTS0601's "Age 30 to 39" came from its declaration, now the register's.

    DfT's row header, which the guard checks, is "30 to 39"; the declaration
    "Age 30 to 39" was Chronicle's text in the field at e29da32.
    """
    package = load_source_package("dft-nts0601-age-mode-trips-2025")
    facts = package.build_facts(2023, cells=package.build_source_cells(2023))
    banded = [
        fact
        for fact in facts
        if fact.filters.get("age_band") in {"30 to 39", "40 to 49"}
    ]

    assert len(banded) == 18
    for fact in banded:
        value_id = fact.filters["age_band"]
        assert fact.dimension_value_labels["age_band"] == {value_id: value_id}
        assert "age_band" not in fact.package_dimension_value_labels


def test_a_groupby_value_whose_axis_is_also_a_filter_is_keyed_by_its_row_value():
    """Eurostat ilc_di01: quant_inc is the filter D1 and the groupby row d1."""
    package = load_source_package("eurostat-ilc-di01")
    facts = package.build_facts(2023, cells=package.build_source_cells(2023))
    fact = next(
        fact
        for fact in facts
        if fact.layout.groupby_value_id == "d1" and fact.filters["statinfo"] == "SHARE"
    )

    assert fact.filters["quant_inc"] == "D1"
    assert fact.layout.groupby_value_label == "First income decile"
    assert fact.package_dimension_value_labels == {
        "quant_inc": {"d1": "First income decile share"}
    }


def test_the_harness_doc_says_which_fields_the_guards_check():
    text = " ".join(_HARNESS_DOC.read_text(encoding="utf-8").split())

    assert "a row's `label:` stays the publisher's text" not in text
    assert "package_dimension_value_labels" in text
    assert "publisher_dimension_value_labels" not in text
    assert (
        "The guards compare a row's `expected_row_header` and "
        "`expected_column_header`, which are fields separate from its `label:`"
    ) in text


def test_the_label_module_does_not_call_package_wording_the_publishers():
    """The label-source list names the package's row label and source-row text.

    A row's ``label:`` and the text Chronicle's parser reads into a source row
    are the package's wording, which nothing checks against the publisher's
    file (chronicle#377 re-check, N3).
    """
    docstring = " ".join(dimension_labels.__doc__.split())

    assert "publisher row label" not in docstring
    assert "the publisher's text in the matching column" not in docstring
    assert (
        "the package's row label for the fact (``layout.groupby_value_label``"
    ) in docstring


# ONS COICOP 02: the total includes narcotics (chronicle#377 review).


def test_coicop_02_takes_the_ons_wording_that_names_narcotics():
    assert (
        dimension_labels.canonical_value_label("ons.coicop", "coicop_02")
        == "Alcohol, tobacco and narcotics"
    )


def test_the_ons_coicop_02_total_includes_narcotics():
    """ADFL = ADFM (alcoholic beverages) + ADFN (tobacco) + MNC2 (narcotics)."""
    workbook = openpyxl.load_workbook(
        _ONS_CONSUMER_TRENDS, read_only=True, data_only=True
    )
    sheet_rows = list(workbook["02CN"].iter_rows(values_only=True))
    workbook.close()
    cdid_row = next(row for row in sheet_rows if row[0] == "CDID identifier code")
    column_by_cdid = {cdid: index for index, cdid in enumerate(cdid_row) if cdid}
    annual = [
        row for row in sheet_rows if isinstance(row[0], int) and 1997 <= row[0] <= 2100
    ]

    assert len(annual) >= 29
    for row in annual:
        parts = [row[column_by_cdid[cdid]] for cdid in ("ADFM", "ADFN", "MNC2")]
        assert abs(row[column_by_cdid["ADFL"]] - sum(parts)) < 0.5, row[0]


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
