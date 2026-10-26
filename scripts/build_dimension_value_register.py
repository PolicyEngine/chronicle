"""Build and check Chronicle's register of dimension value labels (chronicle#376).

``chronicle/dimension_values/canonical_labels.json`` gives one label to every
(dimension id, value id) that two or more default-bundle packages emit, and to
every value its packages word more than one way. Each fact a package builds
takes the register's label for a value it lists, so a consumer that merges
packages built for different years sees one label per value.

The register is Chronicle's display text, not a publisher's file. A value with
one wording keeps it. A value worded more than one way takes the label in
``CHOSEN_LABELS`` below, chosen by the rule in
``docs/agent-source-package-harness.md`` (the wording most packages use, a tie
going to the national statistics office's wording) or by the maintainer.

Usage:

    # Rebuild every default-bundle package at its build year and rewrite the
    # register (slow: every package is built).
    uv run python scripts/build_dimension_value_register.py

    # The same, but fail instead of writing when the register differs.
    uv run python scripts/build_dimension_value_register.py --check

    # Read already-built packages (directories of <package>/consumer_facts.jsonl,
    # as build-suite writes them) instead of building them.
    uv run python scripts/build_dimension_value_register.py \\
        --from-consumer-facts BUILDS_DIR [BUILDS_DIR ...] [--check]

    # Compare the register with the package files only, without building:
    # every value two packages' files name must be listed, every listed value
    # must be named by some package file, and no package may declare a label
    # the register contradicts. Runs in CI through
    # tests/test_dimension_value_register.py.
    uv run python scripts/build_dimension_value_register.py --static-check

The static check reads groupby rows' value ids, filters and declarations from
each package file compiled at its build year. It cannot see a value a package
only takes from its source rows at build time, so the full ``--check`` is the
complete comparison.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chronicle.dimension_labels import (  # noqa: E402
    REGISTER_DISPLAY_PATH,
    REGISTER_PATH,
    dimension_value_id,
)

SCRIPT_DISPLAY_PATH = "scripts/build_dimension_value_register.py"
SCHEMA_VERSION = "chronicle.dimension_value_labels.v1"
#: The Chronicle commit whose package builds the register was generated from.
BUILT_AT_CHRONICLE_COMMIT = "dece5e9"
DEFAULT_BUILD_YEAR = 2023
#: Default-bundle packages that do not build at DEFAULT_BUILD_YEAR.
BUILD_YEARS = {
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

AGI = "us:statutes/26/62#adjusted_gross_income"
#: The label of each value its packages word more than one way. The three US
#: labels are the maintainer's choice; the other 40 were proposed in
#: chronicle#377 and approved on 2026-10-21, coicop_02 with ONS's overview
#: wording after review.
CHOSEN_LABELS: dict[tuple[str, str], str] = {
    (AGI, "under_1"): "No adjusted gross income",
    (AGI, "all"): "All returns, total",
    ("age", "85_plus"): "Age 85 plus",
    ("age", "age_20"): "Age 20",
    ("age", "age_21"): "Age 21",
    ("age", "age_25_to_29"): "Age 25 to 29",
    ("age", "age_30_to_34"): "Age 30 to 34",
    ("age", "age_35_to_39"): "Age 35 to 39",
    ("age", "age_40_to_44"): "Age 40 to 44",
    ("age_band", "30 to 39"): "30 to 39",
    ("age_band", "40 to 49"): "40 to 49",
    (
        "early_year_award_line",
        "new_returning_total_returning_31_33_35",
    ): "Total returning [31][33][35]",
    ("groeipakket.component", "pleegzorgtoeslag"): "Foster care supplement",
    ("groeipakket.component", "sociale_toeslag"): "Social supplement",
    ("groeipakket.component", "wezentoeslag"): "Orphan supplement",
    ("groeipakket.component", "zorgtoeslag"): "Care supplement",
    (
        "household_type",
        "couple_3_plus_children_households",
    ): "3 or more dependent children",
    (
        "ons.household_type",
        "couple_3_plus_children_households",
    ): "3 or more dependent children",
    ("measure", "country_total"): "Country total",
    (
        "na_item",
        "belgium_household_disposable_income_gross",
    ): "Disposable income, gross (B.6G)",
    ("na_item", "belgium_household_mixed_income_gross"): "Mixed income, gross (B.3G)",
    (
        "na_item",
        "belgium_household_operating_surplus_gross",
    ): "Operating surplus, gross (B.2G)",
    # ONS's detailed-worksheet wording without its footnote marker, except
    # where noted.
    ("ons.coicop", "coicop_01"): "Food and non-alcoholic beverages",
    # ONS's overview (0CN) wording: the total, CDID ADFL, includes narcotics
    # (ADFL = ADFM + ADFN + MNC2), which the 02CN column header leaves out.
    ("ons.coicop", "coicop_02"): "Alcohol, tobacco and narcotics",
    ("ons.coicop", "coicop_04"): "Housing, water, electricity, gas and other fuel",
    # The overview (0CN) wording; 05CN abbreviates it.
    (
        "ons.coicop",
        "coicop_05",
    ): "Furnishings, household equipment and routine maintenance of the house",
    # The overview (0CN) wording; 11CN writes "Restaurant and hotels".
    ("ons.coicop", "coicop_11"): "Restaurants and hotels",
    ("ons.coicop", "coicop_12"): "Miscellaneous goods and services",
    ("person.age_band", "65_plus"): "65+",
    ("property_type", "detached"): "Detached",
    ("property_type", "semi_detached"): "Semi detached",
    ("property_type", "terraced"): "Terraced",
    ("quant_inc", "d1"): "First income decile",
    ("quant_inc", "d2"): "Second income decile",
    ("quant_inc", "d3"): "Third income decile",
    ("quant_inc", "d4"): "Fourth income decile",
    ("quant_inc", "d5"): "Fifth income decile",
    ("quant_inc", "d6"): "Sixth income decile",
    ("quant_inc", "d7"): "Seventh income decile",
    ("quant_inc", "d8"): "Eighth income decile",
    ("quant_inc", "d9"): "Ninth income decile",
    ("sex", "female"): "Female",
    ("sex", "male"): "Male",
}

DESCRIPTION = (
    "One label per dimension value (chronicle#376). Every fact built from a "
    "source package carries the label listed here for a value in "
    "dimension_value_labels and, for its groupby value, "
    "layout.groupby_value_label; the package's own wording, where it differs, "
    "is kept in package_dimension_value_labels. A value enters this register "
    "when two or more packages emit it or when its packages word it more than "
    "one way. These are Chronicle's display labels, not a publisher's file: a "
    "value with one wording keeps it, and a value worded more than one way "
    "takes the label chosen in scripts/build_dimension_value_register.py. A "
    "package may not declare a different label for a listed value. A value no "
    "entry covers takes its package's label, and build-bundle refuses it if "
    "two packages label it differently."
)

ValueKey = tuple[str, str]
#: (dimension id, value id) -> wording -> package id -> fact count.
Wordings = dict[ValueKey, dict[str, dict[str, int]]]


def build_year(package_id: str) -> int:
    """Return the year the register builds *package_id* at."""

    return BUILD_YEARS.get(package_id, DEFAULT_BUILD_YEAR)


def wordings_by_value(
    rows_by_package: Mapping[str, Iterable[Mapping[str, Any]]],
) -> Wordings:
    """Count each package's own wording of each value in its consumer rows.

    A row built before the register carries its package's wording as the
    label; a row built after carries the register's label, with the package's
    wording in ``package_dimension_value_labels`` where it differs. A value id
    equal to the row's geography id names the area, not a dimension value.
    """

    found: Wordings = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for package_id, rows in rows_by_package.items():
        for row in rows:
            geography_id = str((row.get("geography") or {}).get("id") or "").casefold()
            package_wording = row.get("package_dimension_value_labels") or {}
            seen: set[tuple[str, str, str]] = set()
            for dimension_id, value_labels in (
                row.get("dimension_value_labels") or {}
            ).items():
                for value_id, label in value_labels.items():
                    wording = (package_wording.get(dimension_id) or {}).get(
                        value_id, label
                    )
                    seen.add((dimension_id, str(value_id), str(wording).strip()))
            layout = row.get("layout") or {}
            groupby = layout.get("groupby_dimension")
            if groupby and layout.get("groupby_value_id") is not None:
                value_id = dimension_value_id(layout["groupby_value_id"])
                wording = (package_wording.get(groupby) or {}).get(
                    value_id, layout.get("groupby_value_label") or ""
                )
                seen.add((groupby, value_id, str(wording).strip()))
            for dimension_id, value_id, wording in seen:
                if not wording or value_id.casefold() == geography_id:
                    continue
                found[(dimension_id, value_id)][wording][package_id] += 1
    return {
        key: {wording: dict(packages) for wording, packages in wordings.items()}
        for key, wordings in found.items()
    }


def register_labels(
    wordings: Wordings,
    *,
    chosen: Mapping[ValueKey, str] = CHOSEN_LABELS,
) -> dict[str, dict[str, str]]:
    """Return the register's labels for the package wordings counted."""

    labels: dict[str, dict[str, str]] = defaultdict(dict)
    unresolved = []
    for (dimension_id, value_id), by_wording in sorted(wordings.items()):
        packages = {package for counts in by_wording.values() for package in counts}
        if len(packages) < 2 and len(by_wording) < 2:
            continue
        if (dimension_id, value_id) in chosen:
            label = chosen[(dimension_id, value_id)]
        elif len(by_wording) == 1:
            label = next(iter(by_wording))
        else:
            unresolved.append(f"{dimension_id}={value_id}: {sorted(by_wording)}")
            continue
        labels[dimension_id][value_id] = label
    if unresolved:
        raise SystemExit(
            "Values worded more than one way need a label in CHOSEN_LABELS "
            f"({SCRIPT_DISPLAY_PATH}), chosen by the rule in "
            "docs/agent-source-package-harness.md:\n  " + "\n  ".join(unresolved)
        )
    return {
        dimension_id: dict(sorted(values.items()))
        for dimension_id, values in sorted(labels.items())
    }


def register_payload(labels: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    """Return the register file's content for *labels*."""

    return {
        "schema_version": SCHEMA_VERSION,
        "description": DESCRIPTION,
        "sources": {
            "script": SCRIPT_DISPLAY_PATH,
            "packages": "chronicle.bundle.DEFAULT_BUNDLE_SOURCES",
            "built_at_chronicle_commit": BUILT_AT_CHRONICLE_COMMIT,
            "default_build_year": DEFAULT_BUILD_YEAR,
            "build_years": dict(sorted(BUILD_YEARS.items())),
            "chosen_labels": sorted(
                f"{dimension_id}={value_id}" for dimension_id, value_id in CHOSEN_LABELS
            ),
        },
        "labels": {
            dimension_id: dict(sorted(values.items()))
            for dimension_id, values in sorted(labels.items())
        },
    }


def register_text(labels: Mapping[str, Mapping[str, str]]) -> str:
    return json.dumps(register_payload(labels), indent=2, ensure_ascii=False) + "\n"


def _stored_rows(builds_dirs: Iterable[Path]) -> dict[str, list[dict[str, Any]]]:
    rows_by_package: dict[str, list[dict[str, Any]]] = {}
    for builds_dir in builds_dirs:
        for package_dir in sorted(Path(builds_dir).iterdir()):
            facts_path = package_dir / "consumer_facts.jsonl"
            if not facts_path.is_file():
                continue
            with facts_path.open(encoding="utf-8") as stream:
                rows_by_package[package_dir.name] = [
                    json.loads(line) for line in stream if line.strip()
                ]
    return rows_by_package


def _built_rows() -> dict[str, list[dict[str, Any]]]:
    from chronicle.bundle import DEFAULT_BUNDLE_SOURCES
    from chronicle.consumer_contract import consumer_fact_rows
    from chronicle.source_package import load_source_package

    rows_by_package = {}
    for source in DEFAULT_BUNDLE_SOURCES:
        package = load_source_package(source)
        year = build_year(package.package_id)
        facts = package.build_facts(year, cells=package.build_source_cells(year))
        rows_by_package[package.package_id] = consumer_fact_rows(facts)
        print(f"built {package.package_id} at {year}", file=sys.stderr)
    return rows_by_package


# The static check: package files only.


def static_package_values() -> tuple[
    dict[ValueKey, set[str]], dict[tuple[str, str, str], str]
]:
    """Return the values each package file names, and its declarations.

    Each default-bundle package is compiled at its build year without reading
    its source file. A value is a groupby row's value id or a filter value
    (record set, row or measure), skipping a value equal to the row's
    geography id; declarations are the package's ``dimension_value_labels``.
    """

    from chronicle.bundle import DEFAULT_BUNDLE_SOURCES
    from chronicle.source_package import load_source_package

    emitters: dict[ValueKey, set[str]] = defaultdict(set)
    declarations: dict[tuple[str, str, str], str] = {}
    for source in DEFAULT_BUNDLE_SOURCES:
        package = load_source_package(source)
        package_id = package.package_id
        record_sets = package._compile_record_set_specs(build_year(package_id))
        for record_set in record_sets:
            groupby = (record_set.groupby_dimension or "").strip()
            for row in record_set.rows:
                geography_id = str(
                    row.geography_id or record_set.geography_id or ""
                ).casefold()
                named = []
                if groupby and row.value_id is not None:
                    named.append((groupby, row.value_id))
                named.extend((record_set.shared_filters or {}).items())
                named.extend((row.filters or {}).items())
                for measure in record_set.measures:
                    named.extend((measure.filters or {}).items())
                for dimension_id, value in named:
                    if value is None:
                        continue
                    value_id = dimension_value_id(value)
                    if value_id.casefold() == geography_id:
                        continue
                    emitters[(str(dimension_id), value_id)].add(package_id)
        for dimension_id, value_labels in (
            package.dimension_value_labels or {}
        ).items():
            for value_id, label in (value_labels or {}).items():
                emitters[(str(dimension_id), str(value_id))].add(package_id)
                declarations[(package_id, str(dimension_id), str(value_id))] = str(
                    label
                ).strip()
    return dict(emitters), declarations


def register_problems(
    *,
    register: Mapping[str, Mapping[str, str]],
    emitters: Mapping[ValueKey, set[str]],
    declarations: Mapping[tuple[str, str, str], str],
) -> list[str]:
    """Compare the register with the values and declarations package files name."""

    listed = {
        (dimension_id, value_id)
        for dimension_id, values in register.items()
        for value_id in values
    }
    problems = []
    for (dimension_id, value_id), packages in sorted(emitters.items()):
        if len(packages) >= 2 and (dimension_id, value_id) not in listed:
            problems.append(
                f"{dimension_id}={value_id} is emitted by {len(packages)} packages "
                f"({', '.join(sorted(packages))}) but the register does not list "
                f"it; add it to {REGISTER_DISPLAY_PATH} with one label."
            )
    for dimension_id, value_id in sorted(listed - set(emitters)):
        problems.append(
            f"{dimension_id}={value_id} is in the register but no package emits "
            f"it; remove it from {REGISTER_DISPLAY_PATH}."
        )
    for (package_id, dimension_id, value_id), declared in sorted(declarations.items()):
        canonical = register.get(dimension_id, {}).get(value_id)
        if canonical is not None and declared != canonical:
            problems.append(
                f"{package_id} declares dimension_value_labels.{dimension_id}."
                f"{value_id} {declared!r}, but the register labels it "
                f"{canonical!r}; change the declaration to {canonical!r}."
            )
    return problems


def committed_register() -> dict[str, dict[str, str]]:
    return json.loads(REGISTER_PATH.read_text(encoding="utf-8"))["labels"]


def static_check_problems() -> list[str]:
    """Run the static check against the committed register."""

    emitters, declarations = static_package_values()
    return register_problems(
        register=committed_register(),
        emitters=emitters,
        declarations=declarations,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--static-check", action="store_true")
    parser.add_argument("--from-consumer-facts", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=REGISTER_PATH)
    arguments = parser.parse_args(argv)

    if arguments.static_check:
        problems = static_check_problems()
        for problem in problems:
            print(problem, file=sys.stderr)
        print(
            f"static check: {len(problems)} problem(s) in {REGISTER_DISPLAY_PATH}",
            file=sys.stderr,
        )
        return 1 if problems else 0

    rows_by_package = (
        _stored_rows(arguments.from_consumer_facts)
        if arguments.from_consumer_facts
        else _built_rows()
    )
    text = register_text(register_labels(wordings_by_value(rows_by_package)))
    if arguments.check:
        current = REGISTER_PATH.read_text(encoding="utf-8")
        if current != text:
            print(
                f"{REGISTER_DISPLAY_PATH} differs from the register the packages "
                f"give; rerun {SCRIPT_DISPLAY_PATH} without --check and review "
                "the change.",
                file=sys.stderr,
            )
            return 1
        print(f"{REGISTER_DISPLAY_PATH} matches the packages.", file=sys.stderr)
        return 0
    arguments.output.write_text(text, encoding="utf-8")
    labels = json.loads(text)["labels"]
    print(
        f"wrote {sum(len(values) for values in labels.values())} values in "
        f"{len(labels)} dimensions to {arguments.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
