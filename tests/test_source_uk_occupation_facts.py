"""UK occupation facts for PolicyEngine/chronicle#407 (PolicyEngine/microcosm#1490).

Checks the packages scripts/build_uk_occupation_packages.py writes: the Nomis APS218
employment estimates by SOC 2020 major and sub-major group, and ASHE Table 2's weekly
and annual pay by two-digit SOC with their coefficients of variation. Values are
re-read from the pinned files with the csv module and openpyxl, and each fact's cell is
found from the fact's own geography and dimensions, not from the package's coordinates.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import runpy
import zipfile
from collections import Counter
from pathlib import Path

import openpyxl
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
DATA = ROOT / "db/data/ons"

APS_PERIODS = {
    # package id: (directory, file year, period type, period, start, end, facts)
    "ons-aps218-occupation-apr-2024-mar-2025": (
        "aps218_occupation_apr_2024_mar_2025",
        2025,
        "fiscal_year",
        2024,
        "2024-04-01",
        "2025-03-31",
        8306,
    ),
    "ons-aps218-occupation-jan-dec-2025": (
        "aps218_occupation_jan_dec_2025",
        2025,
        "calendar_year",
        2025,
        "2025-01-01",
        "2025-12-31",
        8320,
    ),
    "ons-aps218-occupation-apr-2025-mar-2026": (
        "aps218_occupation_apr_2025_mar_2026",
        2026,
        "fiscal_year",
        2025,
        "2025-04-01",
        "2026-03-31",
        8330,
    ),
}
ASHE_EDITIONS = {
    # edition: (year, survey reference date, zip, member prefix)
    "2024_revised": (2024, "2024-04-17", "ashetable22024revised.zip", ""),
    "2025_revised": (2025, "2025-04-30", "ashetable22025revised.zip", ""),
    "2026_provisional": (
        2026,
        "2026-04-22",
        "ashetable22026provisional.zip",
        "PROV - ",
    ),
}
ASHE_TABLES = {
    # table slug: (Table number, title, CV)
    "weekly_pay_gross": ("2.1a", "Weekly pay - Gross", False),
    "weekly_pay_gross_cv": ("2.1b", "Weekly pay - Gross", True),
    "annual_pay_gross": ("2.7a", "Annual pay - Gross", False),
    "annual_pay_gross_cv": ("2.7b", "Annual pay - Gross", True),
}
ASHE_FACTS = {
    ("2024_revised", "weekly_pay_gross"): 4046,
    ("2024_revised", "weekly_pay_gross_cv"): 4098,
    ("2024_revised", "annual_pay_gross"): 3937,
    ("2024_revised", "annual_pay_gross_cv"): 4020,
    ("2025_revised", "weekly_pay_gross"): 4053,
    ("2025_revised", "weekly_pay_gross_cv"): 4053,
    ("2025_revised", "annual_pay_gross"): 3934,
    ("2025_revised", "annual_pay_gross_cv"): 3934,
    ("2026_provisional", "weekly_pay_gross"): 4056,
    ("2026_provisional", "weekly_pay_gross_cv"): 4056,
    ("2026_provisional", "annual_pay_gross"): 3948,
    ("2026_provisional", "annual_pay_gross_cv"): 3948,
}


def _ashe_package_id(edition: str, table: str) -> str:
    return f"ons-ashe-table2-{table.replace('_', '-')}-{edition.replace('_', '-')}"


PACKAGE_IDS = (
    *APS_PERIODS,
    *(_ashe_package_id(edition, table) for edition, table in ASHE_FACTS),
)

NOMIS_SEX = {"all": "All persons", "male": "Males", "female": "Females"}
NOMIS_ETYPE = {"all": "Total", "employee": "Employee", "self_employed": "Self-employed"}
NOMIS_MEASURES = {"estimate": "Value", "confidence_interval_half_width": "Confidence"}
COUNTRIES = ("E92000001", "W92000004", "S92000003", "N92000002")
REGIONS = tuple(f"E1200000{index}" for index in range(1, 10))
MAJOR_GROUPS = tuple(range(1, 10))
SUB_MAJOR_GROUPS = (
    *(11, 12, 21, 22, 23, 24, 31, 32, 33, 34, 35, 41, 42),
    *(51, 52, 53, 54, 61, 62, 63, 71, 72, 81, 82, 91, 92),
)
ASHE_SHEETS = {
    ("all", "all"): "All",
    ("male", "all"): "Male",
    ("female", "all"): "Female",
    ("all", "full_time"): "Full-Time",
    ("all", "part_time"): "Part-Time",
    ("male", "full_time"): "Male Full-Time",
    ("male", "part_time"): "Male Part-Time",
    ("female", "full_time"): "Female Full-Time",
    ("female", "part_time"): "Female Part-Time",
}
PERCENTILE_COLUMNS = dict(zip((10, 20, 25, 30, 40, 60, 70, 75, 80, 90), range(8, 18)))
ASHE_PORTED_COLUMNS = (3, 4, 6, *PERCENTILE_COLUMNS.values())


@pytest.fixture(scope="module")
def built():
    packages = {}
    for package_id in PACKAGE_IDS:
        package = load_source_package(package_id)
        year = package.artifact.artifact_year
        packages[package_id] = (package, year, package.build_facts(year))
    return packages


def _occupation(fact) -> int | None:
    filters = fact.filters
    assert not (
        "soc2020_major_group" in filters and "soc2020_sub_major_group" in filters
    )
    return filters.get("soc2020_major_group", filters.get("soc2020_sub_major_group"))


# ---------------------------------------------------------------- registration


def test_packages_validate_register_and_carry_no_anchors(built):
    for package_id, (package, year, facts) in built.items():
        report = validate_source_package(package.package_path, year=year)
        assert report.valid, report.to_dict()
        assert not report.warnings
        assert report.counts["source_record_count"] == len(facts)
        relative = package.package_path.relative_to(ROOT / "packages")
        assert SOURCE_PACKAGE_ALIASES[package_id] == relative
        assert package_id in UK_BUNDLE_SOURCES
        text = (package.package_path / "source_package.yaml").read_text(
            encoding="utf-8"
        )
        assert not re.search(r"(:|^\s*-)\s+[&*][A-Za-z_][\w-]*\s*$", text, re.M)
        assert validate_facts(facts).valid
    every = [fact for _, _, facts in built.values() for fact in facts]
    keys = Counter(build_semantic_fact_key(fact) for fact in every)
    assert max(keys.values()) == 1
    assert len(every) == sum(row[-1] for row in APS_PERIODS.values()) + sum(
        ASHE_FACTS.values()
    )


def test_generator_reproduces_the_committed_packages():
    generator = runpy.run_path(str(ROOT / "scripts/build_uk_occupation_packages.py"))
    builders = generator["BUILDERS"]
    assert len(builders) == len(PACKAGE_IDS)
    for directory, build in builders.items():
        committed = ROOT / "packages" / directory / "source_package.yaml"
        assert build() == committed.read_text(encoding="utf-8"), directory


def _manifests() -> list[Path]:
    return sorted(
        [DATA / row[0] / "manifest.yaml" for row in APS_PERIODS.values()]
        + [
            DATA / f"ashe_table2_{edition}" / "manifest.yaml"
            for edition in ASHE_EDITIONS
        ]
    )


def test_manifests_pin_bytes_licence_and_the_r2_key():
    for path in _manifests():
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert manifest["source_id"] == "ons"
        assert manifest["license"] == "Open Government Licence v3.0"
        assert manifest["license_verified_at"] == "2026-11-04"
        ((year, entry),) = manifest["files"].items()
        content = (path.parent / entry["filename"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]
        assert len(content) == entry["size_bytes"]
        host = (
            "www.nomisweb.co.uk" if "aps218" in path.parent.name else "www.ons.gov.uk"
        )
        assert entry["source_url"].startswith(f"https://{host}/")
        # `chronicle publish-raw` uploaded the bytes and wrote storage.r2, and
        # `chronicle verify-raw` read each object back.
        key = (
            f"raw/uk/ons/{manifest['package_id']}/{year}/{entry['sha256']}/"
            f"{entry['filename']}"
        )
        assert entry["storage"]["r2"] == {
            "provider": "r2",
            "bucket": "ledger-raw",
            "key": key,
            "uri": f"r2://ledger-raw/{key}",
        }
    aps = yaml.safe_load(_manifests()[0].read_text(encoding="utf-8"))
    ((_, entry),) = aps["files"].items()
    assert entry["nomis_dataset_last_revised"] == "2023-01-27 10:00:00"


def test_consumer_contract_is_valid(built):
    for package_id, (_, _, facts) in built.items():
        report = validate_consumer_fact_contract(facts)
        assert report.valid, (package_id, report.errors[:3])
        assert all(fact.source.raw_r2_uri for fact in facts), package_id


def test_a_concept_and_its_dimensions_select_one_fact(built):
    """An interval or a CV never shares its estimate's concept.

    A reader that selects by concept, aggregation, period, geography and every
    dimension but ``statistic`` gets exactly one fact, so it can neither sum an
    estimate with its interval or CV nor keep the wrong one.
    """
    keys = Counter()
    for _, _, facts in built.values():
        for fact in facts:
            dimensions = tuple(
                sorted((k, v) for k, v in fact.filters.items() if k != "statistic")
            )
            keys[
                (
                    fact.measure.concept,
                    fact.aggregation.method,
                    fact.period.type,
                    fact.period.value,
                    fact.geography.id,
                    dimensions,
                )
            ] += 1
            statistic = fact.filters["statistic"]
            concept = fact.measure.concept
            if statistic == "confidence_interval_half_width":
                assert (
                    concept
                    == "ons.aps_people_in_employment_confidence_interval_half_width"
                )
            elif statistic == "coefficient_of_variation":
                assert concept.endswith("_coefficient_of_variation"), concept
            else:
                assert statistic == "estimate"
                assert not concept.endswith(("_half_width", "_of_variation")), concept
    assert max(keys.values()) == 1


# ---------------------------------------------------------------- 1. Nomis APS218


def _aps_csv(directory: str) -> dict[tuple, dict]:
    manifest = yaml.safe_load((DATA / directory / "manifest.yaml").read_text())
    ((_, entry),) = manifest["files"].items()
    text = (DATA / directory / entry["filename"]).read_text(encoding="utf-8-sig")
    rows = {}
    for row in csv.DictReader(io.StringIO(text)):
        name = row["SOC2020_FULL_NAME"]
        code = None if name == "Total" else int(name.split(" : ")[0])
        key = (
            row["GEOGRAPHY_CODE"],
            row["C_SEX_NAME"],
            row["ETYPE_NAME"],
            code,
            row["MEASURES_NAME"],
        )
        assert key not in rows
        rows[key] = row
    return rows


def _aps_key(fact) -> tuple:
    return (
        fact.geography.id,
        NOMIS_SEX[fact.filters["sex"]],
        NOMIS_ETYPE[fact.filters["employment_status"]],
        _occupation(fact),
        NOMIS_MEASURES[fact.filters["statistic"]],
    )


def test_aps_facts_are_the_published_cells_and_only_those(built):
    for package_id, row in APS_PERIODS.items():
        directory, _, period_type, period, start, end, count = row
        _, _, facts = built[package_id]
        assert len(facts) == count
        published = _aps_csv(directory)
        numeric = {
            key
            for key, cell in published.items()
            if cell["OBS_VALUE"] not in ("", None)
        }
        seen = set()
        for fact in facts:
            key = _aps_key(fact)
            cell = published[key]
            assert cell["OBS_STATUS"] == "A", key
            assert fact.value == int(cell["OBS_VALUE"]), key
            assert fact.measure.concept == (
                "ons.aps_people_in_employment"
                if fact.filters["statistic"] == "estimate"
                else "ons.aps_people_in_employment_confidence_interval_half_width"
            )
            assert (fact.measure.unit, fact.aggregation.method) == ("count", "sum")
            assert fact.provenance_class == "survey_aggregate"
            assert fact.survey_instrument == "Annual Population Survey"
            assert (fact.entity.name, fact.entity.role) == ("person", "in_employment")
            assert (fact.period.type, fact.period.value) == (period_type, period)
            assert (fact.period_coverage.start_date, fact.period_coverage.end_date) == (
                start,
                end,
            )
            assert fact.period_coverage.source_period_label == cell["DATE_NAME"]
            assert key not in seen
            seen.add(key)
        assert seen == numeric
        # Blank cells are Nomis's suppressions: F (sample of 0 to 2) and H (under 500)
        # for estimates; F and G for intervals Nomis withholds.
        blank = Counter(
            (key[-1], cell["OBS_STATUS"])
            for key, cell in published.items()
            if key not in numeric
        )
        assert set(blank) <= {
            ("Value", "F"),
            ("Value", "H"),
            ("Confidence", "F"),
            ("Confidence", "G"),
        }


def test_aps_estimates_without_an_interval_carry_its_status(built):
    package, year, facts = built["ons-aps218-occupation-apr-2024-mar-2025"]
    published = _aps_csv(APS_PERIODS[package.package_id][0])
    specs = {
        f"{record_set.source_record_id_prefix}.{row.value_id}.{measure.measure_id}": row
        for record_set in package.build_source_record_set_specs(year)
        for row in record_set.rows
        for measure in record_set.measures
    }
    withheld = Counter()
    for fact in facts:
        if fact.filters["statistic"] != "estimate":
            continue
        interval = published[(*_aps_key(fact)[:-1], "Confidence")]
        (status_guard,) = [
            guard
            for guard in specs[fact.source_record_id].guard_cells
            if guard.column == "L"
        ]
        assert status_guard.row == specs[fact.source_record_id].row_number + 1
        assert status_guard.expected_value == interval["OBS_STATUS"]
        withheld[interval["OBS_STATUS"]] += 1
    # 314 estimates Nomis marks unreliable (G) and 78 whose interval it marks F.
    assert withheld == {"A": 3957, "G": 314, "F": 78}


def _aps_estimates(facts) -> dict[tuple, int]:
    return {
        (
            fact.geography.id,
            fact.filters["sex"],
            fact.filters["employment_status"],
            _occupation(fact),
        ): fact.value
        for fact in facts
        if fact.filters["statistic"] == "estimate"
    }


def _within_rounding(parts: list, whole) -> bool | None:
    """Nomis rounds every count to the nearest hundred: 50 per summed cell."""
    if whole is None or None in parts:
        return None
    return abs(sum(parts) - whole) <= 50 * (len(parts) + 1)


def test_aps_parity_sub_major_groups_countries_and_regions(built):
    for package_id in APS_PERIODS:
        estimates = _aps_estimates(built[package_id][2])
        checked = Counter()
        for (geography, sex, status, code), _ in estimates.items():
            if code is None or code > 9:
                continue
            parts = [
                estimates.get((geography, sex, status, sub))
                for sub in SUB_MAJOR_GROUPS
                if sub // 10 == code
            ]
            result = _within_rounding(parts, estimates[(geography, sex, status, code)])
            assert result is not False, (geography, sex, status, code)
            checked["sub_major"] += result is True
        for sex in NOMIS_SEX:
            for status in NOMIS_ETYPE:
                for code in (None, *MAJOR_GROUPS, *SUB_MAJOR_GROUPS):
                    uk = estimates.get(("K02000001", sex, status, code))
                    countries = [
                        estimates.get((c, sex, status, code)) for c in COUNTRIES
                    ]
                    result = _within_rounding(countries, uk)
                    assert result is not False, ("countries", sex, status, code)
                    checked["countries"] += result is True
                    england = estimates.get(("E92000001", sex, status, code))
                    regions = [estimates.get((r, sex, status, code)) for r in REGIONS]
                    result = _within_rounding(regions, england)
                    assert result is not False, ("regions", sex, status, code)
                    checked["regions"] += result is True
        assert checked["sub_major"] > 900, (package_id, checked)
        assert checked["countries"] > 250 and checked["regions"] > 250, checked


def test_aps_parity_major_groups_and_the_total(built):
    """The total is the major groups' sum plus people in no major group.

    Nomis publishes no residual category, and the nine major groups add to slightly
    less than the all-occupations total: never more, beyond rounding, and never by
    more than 1 per cent of it.
    """
    for package_id in APS_PERIODS:
        estimates = _aps_estimates(built[package_id][2])
        gaps = []
        for (geography, sex, status, code), total in estimates.items():
            if code is not None:
                continue
            majors = [
                estimates.get((geography, sex, status, major)) for major in MAJOR_GROUPS
            ]
            if None in majors:
                continue
            gap = total - sum(majors)
            assert -50 * 10 <= gap <= 0.01 * total, (geography, sex, status, gap)
            gaps.append(gap / total)
        assert len(gaps) > 120
        uk = estimates[("K02000001", "all", "all", None)]
        majors = sum(
            estimates[("K02000001", "all", "all", major)] for major in MAJOR_GROUPS
        )
        assert 0 < uk - majors < 0.002 * uk


# ---------------------------------------------------------------- 2. ASHE Table 2


def _ashe_workbook(edition: str, table: str):
    year, _, zip_name, prefix = ASHE_EDITIONS[edition]
    number, title, cv = ASHE_TABLES[table]
    member = (
        f"{prefix}Occupation SOC20 (2) Table {number}   {title} {year}"
        f"{' CV' if cv else ''}.xlsx"
    )
    with zipfile.ZipFile(DATA / f"ashe_table2_{edition}" / zip_name) as archive:
        content = archive.read(member)
    return openpyxl.load_workbook(io.BytesIO(content), data_only=True)


def _ashe_row(sheet, code: int | None) -> int:
    for row in range(6, 42):
        published = sheet.cell(row, 2).value
        if code is None and sheet.cell(row, 1).value == "All employees":
            return row
        if code is not None and str(published or "").lstrip("'") == str(code):
            return row
    raise AssertionError(code)


def _ashe_column(fact) -> int:
    concept = fact.measure.concept.removesuffix("_coefficient_of_variation")
    if concept.endswith("_pay_jobs"):
        return 3
    if fact.aggregation.method == "median":
        return 4
    if fact.aggregation.method == "mean":
        return 6
    assert fact.aggregation.method == "quantile"
    return PERCENTILE_COLUMNS[fact.filters["earnings_percentile"]]


def test_ashe_facts_are_the_published_cells_and_only_those(built):
    for (edition, table), count in ASHE_FACTS.items():
        _, _, facts = built[_ashe_package_id(edition, table)]
        assert len(facts) == count
        year, reference, _, _ = ASHE_EDITIONS[edition]
        cv = ASHE_TABLES[table][2]
        pay = "weekly" if table.startswith("weekly") else "annual"
        workbook = _ashe_workbook(edition, table)
        seen = set()
        for fact in facts:
            sheet_name = ASHE_SHEETS[
                (fact.filters["sex"], fact.filters["working_pattern"])
            ]
            sheet = workbook[sheet_name]
            row, column = _ashe_row(sheet, _occupation(fact)), _ashe_column(fact)
            published = sheet.cell(row, column).value
            jobs = column == 3
            expected = published * 1000 if jobs and not cv else published
            assert fact.value == pytest.approx(expected), (sheet_name, row, column)
            assert fact.filters["statistic"] == (
                "coefficient_of_variation" if cv else "estimate"
            )
            unit = "percent" if cv else ("count" if jobs else "gbp")
            assert fact.measure.unit == unit
            concept = (
                f"ons.ashe_{pay}_pay_jobs" if jobs else f"ons.ashe_gross_{pay}_pay"
            )
            if cv:
                concept += "_coefficient_of_variation"
            assert fact.measure.concept == concept
            assert fact.geography.id == "K02000001"
            assert (fact.entity.name, fact.entity.role) == ("person", "employee_job")
            assert fact.survey_instrument == "Annual Survey of Hours and Earnings"
            if pay == "weekly":
                assert (fact.period.type, fact.period.value) == ("calendar_year", year)
                assert fact.period_coverage.start_date == reference
                assert fact.period_coverage.end_date == reference
            else:
                assert (fact.period.type, fact.period.value) == ("tax_year", year - 1)
                assert fact.period_coverage.start_date == f"{year - 1}-04-06"
                assert fact.period_coverage.end_date == f"{year}-04-05"
            assert (sheet_name, row, column) not in seen
            seen.add((sheet_name, row, column))
        numeric = set()
        marks = Counter()
        for sheet_name in ASHE_SHEETS.values():
            sheet = workbook[sheet_name]
            for row in range(6, 42):
                for column in ASHE_PORTED_COLUMNS:
                    value = sheet.cell(row, column).value
                    if isinstance(value, (int, float)):
                        numeric.add((sheet_name, row, column))
                    else:
                        marks[value] += 1
            assert sheet.cell(42, 1).value == "Not Classified"
            assert sheet.cell(42, 3).value == ":"
        assert seen == numeric
        assert set(marks) <= ({"x", "."} if cv else {"x"}), marks


# The bulletins' headline medians for full-time employees, which they print to the
# penny (weekly) and the pound (annual); Table 2 prints one decimal place.
BULLETIN_HEADLINES = {
    # edition: (bulletin, weekly, annual)
    "2024_revised": ("Employee earnings in the UK: 2025", 728.27, 37439),
    "2025_revised": ("Employee earnings in the UK: 2026", 766.60, 39157),
    "2026_provisional": ("Employee earnings in the UK: 2026", 811.20, 40911),
}


def _headline(built, edition: str, table: str):
    _, _, facts = built[_ashe_package_id(edition, table)]
    (fact,) = [
        fact
        for fact in facts
        if fact.filters["sex"] == "all"
        and fact.filters["working_pattern"] == "full_time"
        and _occupation(fact) is None
        and fact.aggregation.method == "median"
    ]
    return fact


def test_ashe_parity_full_time_median_is_the_bulletin_headline(built):
    for edition, (_, weekly, annual) in BULLETIN_HEADLINES.items():
        assert abs(_headline(built, edition, "weekly_pay_gross").value - weekly) <= 0.05
        assert abs(_headline(built, edition, "annual_pay_gross").value - annual) <= 0.5


def test_ashe_2025_revised_prints_the_police_group_annual_pay(built):
    """ONS suppressed occupation 33's 2025 provisional annual pay for the UK
    (corrections notice of 19 December 2025); the revised edition prints it."""
    _, _, facts = built[_ashe_package_id("2025_revised", "annual_pay_gross")]
    sheets = {
        ASHE_SHEETS[(fact.filters["sex"], fact.filters["working_pattern"])]
        for fact in facts
        if fact.filters.get("soc2020_sub_major_group") == 33
        and fact.aggregation.method == "median"
    }
    assert sheets == set(ASHE_SHEETS.values())


def test_ashe_cvs_describe_the_estimates_they_sit_beside(built):
    for edition in ASHE_EDITIONS:
        for pay in ("weekly", "annual"):
            estimates = built[_ashe_package_id(edition, f"{pay}_pay_gross")][2]
            cvs = built[_ashe_package_id(edition, f"{pay}_pay_gross_cv")][2]

            def key(fact):
                return (
                    fact.measure.concept.removesuffix("_coefficient_of_variation"),
                    fact.aggregation.method,
                    tuple(
                        sorted(
                            (name, value)
                            for name, value in fact.filters.items()
                            if name != "statistic"
                        )
                    ),
                )

            estimate_keys = {key(fact) for fact in estimates}
            cv_keys = {key(fact) for fact in cvs}
            # From 2025 ONS marks the same cells 'x' in both tables. The 2024 CV
            # tables print the CV of each estimate suppressed for a CV over 20 per
            # cent, and '.' ('unavailable') for a few published estimates.
            suppressed, unavailable = {
                "2024_revised": {"weekly": (53, 1), "annual": (85, 2)}[pay],
            }.get(edition, (0, 0))
            assert len(cv_keys - estimate_keys) == suppressed
            assert len(estimate_keys - cv_keys) == unavailable
            for cv in cvs:
                if key(cv) not in estimate_keys:
                    assert cv.value > 20
