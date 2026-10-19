"""Tests for merged Arch consumer bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import arch.bundle
from arch.bundle import build_bundle, build_bundle_coverage
from arch.harness import main as harness_main


def _load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


@pytest.fixture
def prune_suite_intermediates(monkeypatch):
    """Delete each source suite's intermediates once the suite is built.

    Every suite in the default bundle writes source_rows.jsonl,
    source_cells.jsonl, facts.jsonl and a per-source arch.db, and
    build_bundle then reads back only its consumer_facts.jsonl.
    A BEA NIPA suite alone writes a 494 MB source_rows.jsonl and a 1 GB
    arch.db for 65 KB of consumer facts.
    The suites are still built, validated and merged exactly as before; only
    files nothing reads afterwards are removed, so they no longer pile up
    across the bundle's source packages.
    """
    build_source_suite = arch.bundle.build_source_suite

    def build_then_prune(*args, **kwargs):
        report = build_source_suite(*args, **kwargs)
        for output in ("source_rows", "source_cells", "facts", "database"):
            Path(report.outputs[output]).unlink(missing_ok=True)
        return report

    monkeypatch.setattr(arch.bundle, "build_source_suite", build_then_prune)


@pytest.mark.usefixtures("prune_suite_intermediates")
def test_build_bundle_writes_merged_consumer_contract(tmp_path):
    """Pin the merged default bundle to exact counts so drift is loud.

    Every count below is deliberately hardcoded: any change to bundle
    inputs (``arch/``, ``packages/``, ``db/data/``) must update this test
    in the same change. On this branch those inputs are frozen — the
    thesis-facts branch takes ledger appends, not source-package work —
    so a failure here is a tripwire, not routine drift. The counts were
    regenerated 2026-07-11 from the fork-point package set (main PRs
    #34-#48 landed before this branch forked and were never reflected
    here because CI did not run this file). Regenerate by rebuilding:
    ``uv run arch build-bundle --year 2023 --out <dir>`` and reading the
    artifacts it writes.

    CI runs this file as the standalone "Arch bundle drift" job, and it
    is deliberately NOT in the required "Arch checks" pytest whitelist:
    the merged build takes ~6 minutes, and the required set gates the
    Thesis resolver's daily append PRs, which cannot affect bundle
    inputs. Keeping the slow pin visible-but-nonblocking protects append
    merge latency; the omission from the whitelist is not an oversight.
    """
    output_dir = tmp_path / "bundle"

    report = build_bundle(output_dir, year=2023)
    summary = json.loads(
        (output_dir / "reports" / "build_bundle.json").read_text()
    )
    rows = _load_jsonl(output_dir / "consumer_facts.jsonl")
    source_packages = json.loads((output_dir / "source_packages.json").read_text())
    coverage = json.loads((output_dir / "coverage.json").read_text())

    assert report.valid
    assert summary["valid"]
    assert summary["counts"] == {
        "aggregate_duplicate_key_count": 0,
        "entity_count": 6,
        "error_count": 0,
        "fact_count": 10268,
        "geography_count": 483,
        "period_count": 9,
        "semantic_duplicate_key_count": 3,
        "skipped_source_count": 8,
        "source_count": 16,
        "source_package_count": 39,
        "warning_count": 1,
    }
    assert len(rows) == 10268
    assert rows[0]["aggregate_fact_key"].startswith("arch.aggregate_fact.v2:")
    assert rows[0]["semantic_fact_key"].startswith("arch.semantic_fact.v2:")
    assert source_packages["source_package_count"] == 39
    assert source_packages["skipped_source_count"] == 8
    assert sorted(item["source"] for item in source_packages["skipped_sources"]) == [
        "census-acs-s0101-congressional-district-age-2024",
        "census-acs-s0101-national-age-2024",
        "census-acs-s0101-state-age-2024",
        "census-acs-s2201-congressional-district-snap-2024",
        "cms-aca-effectuated-enrollment-2022",
        "cms-aca-oep-state-level",
        "cms-aca-oep-state-level-2022",
        "cms-aca-oep-state-level-2025",
    ]
    assert {
        item["reason"] for item in source_packages["skipped_sources"]
    } == {"source package is not available for requested year"}
    assert coverage["fact_count"] == 10268
    assert coverage["counts"]["by_source"] == {
        "bea": 443,
        "cbo": 6,
        "census_acs": 468,
        "census_pep": 988,
        "census_population_projections": 86,
        "census_stc": 46,
        "cms_medicaid": 515,
        "cms_medicare": 1,
        "cms_nhe": 1,
        "federal_reserve": 1,
        "hhs_acf_liheap": 2,
        "hhs_acf_tanf": 110,
        "irs_soi": 6911,
        "kff": 52,
        "ssa": 422,
        "usda_snap": 216,
    }
    assert coverage["counts"]["by_source_table"] == {
        "bea:BEA NIPA annual data flat file": 27,
        "bea:BEA Regional annual state personal income CSV ZIP": 416,
        (
            "cbo:Revenue Projections, by Category, February 2026, sheet "
            "3.Individual Income Tax Details"
        ): 6,
        (
            "census_acs:ACS 2023 1-year detailed table B01001 female age "
            "bands by state"
        ): 468,
        (
            "census_pep:Annual Estimates of the Resident Population by "
            "Single Year of Age and Sex for the United States"
        ): 19,
        (
            "census_pep:Annual State Resident Population Estimates by "
            "Single Year of Age, Sex, Race, and Hispanic Origin"
        ): 969,
        (
            "census_population_projections:2023 National Population "
            "Projections Main Series, middle series"
        ): 86,
        "census_stc:FY2023 STC Flat File item T40 Individual Income Taxes": 46,
        (
            "cms_medicaid:State Medicaid and CHIP Applications, "
            "Eligibility Determinations, and Enrollment Data"
        ): 515,
        "cms_medicare:2025 Medicare Trustees Report Table III.C3": 1,
        (
            "cms_nhe:National Health Expenditures by type of service and "
            "source of funds, CY 1960-2024"
        ): 1,
        "federal_reserve:Z.1 B.101 Households and nonprofit organizations": 1,
        "hhs_acf_liheap:LIHEAP FY2023 National Profile (All States)": 1,
        "hhs_acf_liheap:LIHEAP FY2024 National Profile (All States)": 1,
        "hhs_acf_tanf:FY 2024 Federal TANF and State MOE Financial Data": 52,
        "hhs_acf_tanf:TANF Caseload Data 2024": 58,
        "irs_soi:Congressional District Data 2022": 1440,
        "irs_soi:Historic Table 2": 605,
        "irs_soi:Historic Table 2 state AGI facts": 918,
        "irs_soi:Historic Table 2 state broad totals": 2703,
        "irs_soi:Historic Table 2 state data, United States total": 4,
        "irs_soi:Historic Table 2 state EITC totals": 510,
        "irs_soi:Publication 1304 Table 1.1": 80,
        "irs_soi:Publication 1304 Table 1.2": 7,
        "irs_soi:Publication 1304 Table 1.4": 340,
        "irs_soi:Publication 1304 Table 2.1": 37,
        "irs_soi:Publication 1304 Table 2.5": 8,
        "irs_soi:Publication 1304 Table 2.5 EITC by AGI and qualifying children": 232,
        "irs_soi:Publication 1304 Table 4.3": 18,
        (
            "irs_soi:Table 4.B. Summary of Items for Taxpayers with Form W-2, "
            "by Return and Earner Type, Tax Year 2020"
        ): 5,
        (
            "irs_soi:Table 5. Taxpayers with Traditional Individual Retirement "
            "Arrangement (IRA) Plan Contributions, by Size of Contribution and "
            "Age of Taxpayer"
        ): 2,
        (
            "irs_soi:Table 6. Taxpayers with Roth Individual Retirement "
            "Arrangement (IRA) Plan Contributions, by Size of Contribution and "
            "Age of Taxpayer"
        ): 2,
        "kff:Full Year Average Marketplace Effectuated Enrollment, 2017-2024": 52,
        "ssa:SSA Annual Statistical Supplement 2025 Table 7.B1": 416,
        (
            "ssa:SSA Annual Statistical Supplement 2025 extracted OASDI "
            "and SSI target rows"
        ): 6,
        (
            "usda_snap:SNAP Monthly State Participation and Benefit "
            "Summary FY69 to current"
        ): 216,
    }
    assert coverage["counts"]["by_period"] == {
        "calendar_year:2018": 1,
        "calendar_year:2023": 997,
        "calendar_year:2024": 1464,
        "fiscal_year:2023": 47,
        "fiscal_year:2024": 327,
        "month:2024-12": 260,
        "month:2025-12": 255,
        "tax_year:2022": 4968,
        "tax_year:2023": 1949,
    }
    assert coverage["counts"]["by_geography"]["country:0100000US"] == 1527
    assert coverage["counts"]["by_geography"]["state:0400000US06"] == 146
    assert len(coverage["counts"]["by_geography"]) == 483
    assert coverage["counts"]["by_entity"] == {
        "family": 107,
        "government": 101,
        "household": 56,
        "institutional_sector": 1,
        "person": 3086,
        "tax_unit": 6917,
    }
    assert not coverage["duplicates"]["aggregate_fact_keys"]
    assert len(coverage["duplicates"]["semantic_fact_keys"]) == 3
    assert summary["warnings"] == [
        {
            "code": "duplicate_semantic_fact_key",
            "message": (
                "One or more semantic facts appear in multiple rows; downstream "
                "consumers should reconcile or select sources."
            ),
        }
    ]
    assert (output_dir / "sources" / "soi-table-1-1" / "consumer_facts.jsonl").exists()
    assert (
        output_dir
        / "sources"
        / "soi-table-1-4"
        / "reports"
        / "build_summary.json"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "hhs-acf-liheap-fy2024-national-profile"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "soi-ira-roth-contributions-2022"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir / "sources" / "census-stc-individual-income-tax" / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "cms-medicare-trustees-report-2025-part-b-premium-income"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "cms-nhe-historical-service-source"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "federal-reserve-z1-household-net-worth"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir / "sources" / "usda-snap-fy69-to-current" / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir / "sources" / "soi-historic-table-2" / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir / "sources" / "hhs-acf-tanf-caseload-2024" / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir / "sources" / "hhs-acf-tanf-financial-2024" / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "cms-medicaid-chip-monthly-enrollment-december-2024"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "soi-historic-table-2-state-broad-2022"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "kff-marketplace-effectuated-enrollment"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "bea-nipa-personal-income-components"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "soi-congressional-district-2022"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "ssa-ssi-table-7b1-2024"
        / "consumer_facts.jsonl"
    ).exists()


def test_build_bundle_cli_supports_explicit_sources(tmp_path, capsys):
    output_dir = tmp_path / "bundle"

    exit_code = harness_main(
        [
            "build-bundle",
            "--year",
            "2023",
            "--source",
            "soi-table-1-1",
            "--out",
            str(output_dir),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["valid"]
    assert payload["counts"]["source_package_count"] == 1
    assert payload["counts"]["fact_count"] == 80
    assert payload["outputs"]["consumer_facts"] == str(
        output_dir / "consumer_facts.jsonl"
    )
    assert payload["coverage"]["counts"]["by_source_table"] == {
        "irs_soi:Publication 1304 Table 1.1": 80
    }


def test_build_bundle_cli_supports_historic_table_2_source(tmp_path, capsys):
    output_dir = tmp_path / "bundle"

    exit_code = harness_main(
        [
            "build-bundle",
            "--year",
            "2023",
            "--source",
            "soi-historic-table-2",
            "--out",
            str(output_dir),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["valid"]
    assert payload["counts"]["source_package_count"] == 1
    assert payload["counts"]["fact_count"] == 605
    assert payload["coverage"]["counts"]["by_source_table"] == {
        "irs_soi:Historic Table 2": 605
    }
    assert (
        output_dir / "sources" / "soi-historic-table-2" / "source_rows.jsonl"
    ).exists()


def test_build_bundle_cli_supports_ssa_supplement_source(tmp_path, capsys):
    output_dir = tmp_path / "bundle"

    exit_code = harness_main(
        [
            "build-bundle",
            "--year",
            "2024",
            "--source",
            "ssa-annual-statistical-supplement-2025",
            "--out",
            str(output_dir),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    rows = _load_jsonl(output_dir / "consumer_facts.jsonl")

    assert exit_code == 0
    assert payload["valid"]
    assert payload["counts"]["source_package_count"] == 1
    assert payload["counts"]["fact_count"] == 6
    assert payload["coverage"]["counts"]["by_source"] == {"ssa": 6}
    assert payload["coverage"]["counts"]["by_entity"] == {"person": 6}
    assert {
        row["universe_constraints"]["constraints"][0]["value"]
        for row in rows
    } == {
        "social_security_benefits",
        "social_security_retirement_benefits",
        "social_security_survivors_benefits",
        "social_security_disability_benefits",
        "social_security_dependents_benefits",
        "ssi_payments",
    }


def test_build_bundle_coverage_reports_duplicate_keys():
    rows = [
        {
            "aggregate_fact_key": "arch.aggregate_fact.v2:a",
            "semantic_fact_key": "arch.semantic_fact.v2:s",
            "legacy_fact_key": "arch.fact.v1:one",
            "source": {
                "source_name": "irs_soi",
                "source_table": "Publication 1304 Table 1.1",
            },
            "period": {"type": "tax_year", "value": 2023},
            "geography": {"level": "country", "id": "0100000US"},
            "entity": {"name": "tax_unit"},
            "observed_measure": {
                "source_name": "irs_soi",
                "source_measure_id": "return_count",
                "source_concept": "irs_soi.individual_income_tax_returns",
            },
        },
        {
            "aggregate_fact_key": "arch.aggregate_fact.v2:a",
            "semantic_fact_key": "arch.semantic_fact.v2:s",
            "legacy_fact_key": "arch.fact.v1:two",
            "source": {
                "source_name": "irs_soi",
                "source_table": "Publication 1304 Table 1.1",
            },
            "period": {"type": "tax_year", "value": 2023},
            "geography": {"level": "country", "id": "0100000US"},
            "entity": {"name": "tax_unit"},
            "observed_measure": {
                "source_name": "irs_soi",
                "source_measure_id": "return_count",
                "source_concept": "irs_soi.individual_income_tax_returns",
            },
        },
    ]

    coverage = build_bundle_coverage(
        rows,
        aggregate_duplicates=[
            {
                "key": "arch.aggregate_fact.v2:a",
                "count": 2,
                "sources": ["irs_soi:Publication 1304 Table 1.1"],
                "legacy_fact_keys": ["arch.fact.v1:one", "arch.fact.v1:two"],
            }
        ],
        semantic_duplicates=[
            {
                "key": "arch.semantic_fact.v2:s",
                "count": 2,
                "sources": ["irs_soi:Publication 1304 Table 1.1"],
                "legacy_fact_keys": ["arch.fact.v1:one", "arch.fact.v1:two"],
            }
        ],
    )

    assert coverage["counts"]["by_source"] == {"irs_soi": 2}
    assert coverage["duplicates"]["aggregate_fact_keys"][0]["count"] == 2
    assert coverage["duplicates"]["semantic_fact_keys"][0]["count"] == 2
