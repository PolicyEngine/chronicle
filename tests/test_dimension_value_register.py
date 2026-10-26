"""The script that builds and checks Chronicle's dimension value register.

``chronicle/dimension_values/canonical_labels.json`` gives one label to every
dimension value two or more packages emit, and to every value its packages
word more than one way (chronicle#376). The chronicle#377 reviews found that
the script which generated it was not committed and that nothing checked the
register against the packages, so a value two packages start sharing could
reach a feed with two labels. ``scripts/build_dimension_value_register.py``
regenerates the register from built packages, and its ``--static-check`` reads
only the package files: every value two packages' files name must be listed,
every listed value must be named by some package file, and no package may
declare a label that differs from the register's.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_REGISTER = ROOT / "chronicle" / "dimension_values" / "canonical_labels.json"


def _script():
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return importlib.import_module("build_dimension_value_register")


def test_the_static_check_passes_on_the_repository():
    assert _script().static_check_problems() == []


def test_the_static_check_reports_a_shared_value_the_register_does_not_list():
    problems = _script().register_problems(
        register={"sex": {"female": "Female"}},
        emitters={
            ("sex", "female"): {"ons-a", "nrs-b"},
            ("filing_status", "single"): {"soi-a", "soi-b"},
        },
        declarations={},
    )

    assert problems == [
        "filing_status=single is emitted by 2 packages (soi-a, soi-b) but the "
        "register does not list it; add it to "
        "chronicle/dimension_values/canonical_labels.json with one label."
    ]


def test_the_static_check_reports_a_listed_value_no_package_emits():
    problems = _script().register_problems(
        register={"sex": {"female": "Female", "unknown": "Unknown"}},
        emitters={("sex", "female"): {"ons-a", "nrs-b"}},
        declarations={},
    )

    assert problems == [
        "sex=unknown is in the register but no package emits it; remove it "
        "from chronicle/dimension_values/canonical_labels.json."
    ]


def test_the_static_check_reports_a_declaration_the_register_contradicts():
    problems = _script().register_problems(
        register={"sex": {"female": "Female"}},
        emitters={("sex", "female"): {"ons-a", "nrs-b"}},
        declarations={("nrs-b", "sex", "female"): "Females"},
    )

    assert problems == [
        "nrs-b declares dimension_value_labels.sex.female 'Females', but the "
        "register labels it 'Female'; change the declaration to 'Female'."
    ]


def test_the_register_is_built_from_each_packages_own_wording():
    script = _script()
    rows_by_package = {
        "pkg-a": [
            {
                "geography": {"id": "UK"},
                "dimension_value_labels": {"sex": {"female": "Female"}},
                "layout": {},
            }
        ],
        "pkg-b": [
            {
                "geography": {"id": "UK"},
                # Built after the register: the label is the register's, the
                # package's wording is kept beside it.
                "dimension_value_labels": {"sex": {"female": "Female"}},
                "package_dimension_value_labels": {"sex": {"female": "Females"}},
                "layout": {},
            },
            {
                "geography": {"id": "UK"},
                "dimension_value_labels": {"region": {"uk": "UK"}},
                "layout": {
                    "groupby_dimension": "line",
                    "groupby_value_id": "total",
                    "groupby_value_label": "Total",
                },
            },
        ],
    }

    wordings = script.wordings_by_value(rows_by_package)
    labels = script.register_labels(wordings, chosen={("sex", "female"): "Female"})

    assert wordings[("sex", "female")] == {
        "Female": {"pkg-a": 1},
        "Females": {"pkg-b": 1},
    }
    # The region value equals the row's geography id, so it is not a value.
    assert ("region", "uk") not in wordings
    assert labels == {"sex": {"female": "Female"}}
    with pytest.raises(SystemExit, match="sex=female"):
        script.register_labels(wordings, chosen={})


def test_the_chosen_labels_are_the_registers_labels():
    script = _script()
    register = json.loads(_REGISTER.read_text(encoding="utf-8"))["labels"]

    assert len(script.CHOSEN_LABELS) == 43
    for (dimension_id, value_id), label in script.CHOSEN_LABELS.items():
        assert register[dimension_id][value_id] == label


def test_the_register_records_what_it_was_built_from():
    payload = json.loads(_REGISTER.read_text(encoding="utf-8"))
    sources = payload["sources"]

    assert sources["script"] == "scripts/build_dimension_value_register.py"
    assert sources["packages"] == "chronicle.bundle.DEFAULT_BUNDLE_SOURCES"
    assert sources["built_at_chronicle_commit"].startswith("dece5e9")
    assert sources["default_build_year"] == 2023
    assert sources["build_years"] == {
        "census-acs-s0101-congressional-district-age-2024": 2024,
        "census-acs-s0101-national-age-2024": 2024,
        "census-acs-s0101-state-age-2024": 2024,
        "census-acs-s1501-state-attainment-2024": 2024,
        "census-acs-s2201-congressional-district-snap-2024": 2024,
        "census-acs5-b01003-county-2024": 2024,
        "census-acs5-b11001-county-2024": 2024,
        "census-acs5-b19001-county-2024": 2024,
        "census-acs5-b19013-county-2024": 2024,
        "census-acs5-b19025-county-2024": 2024,
        "census-acs5-b19051-county-2024": 2024,
        "census-acs5-b19061-county-2024": 2024,
        "cms-aca-effectuated-enrollment-2022": 2022,
        "cms-aca-oep-state-level": 2024,
        "cms-aca-oep-state-level-2022": 2022,
        "cms-aca-oep-state-level-2025": 2025,
        "ed-fsa-dl-portfolio-by-repayment-plan-fy2026-q3": 2026,
        "ed-fsa-portfolio-by-age-fy2026-q2": 2026,
        "ed-fsa-portfolio-by-debt-size-fy2026-q2": 2026,
        "ed-fsa-portfolio-by-loan-type-fy2026-q3": 2026,
        "ed-fsa-portfolio-by-location-fy2026-q2": 2026,
        "ed-fsa-portfolio-summary-fy2026-q3": 2026,
        "jct-obbba-revenue-estimates-2025": 2026,
        "jct-tax-expenditures-2024": 2024,
    }
    assert sorted(sources["chosen_labels"]) == sorted(
        f"{dimension_id}={value_id}"
        for dimension_id, value_id in _script().CHOSEN_LABELS
    )
