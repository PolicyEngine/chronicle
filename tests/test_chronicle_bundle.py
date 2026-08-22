"""Tests for merged Chronicle consumer bundles."""

from __future__ import annotations

import json

from chronicle.bundle import UK_BUNDLE_SOURCES, build_bundle, build_bundle_coverage
from chronicle.harness import build_bundle_dir
from chronicle.harness import main as harness_main


def _load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_build_bundle_dir_uk_suite_uses_curated_sources(tmp_path, monkeypatch):
    captured = {}

    class FakeReport:
        valid = True

        def to_dict(self):
            return {"valid": True}

    def fake_build_bundle(output_dir, **kwargs):
        captured["output_dir"] = output_dir
        captured.update(kwargs)
        return FakeReport()

    monkeypatch.setattr("chronicle.harness.build_bundle", fake_build_bundle)

    report = build_bundle_dir(tmp_path / "bundle", year=2023, suite="uk")

    assert report.valid
    assert tuple(captured["sources"]) == UK_BUNDLE_SOURCES
    assert captured["output_dir"] == tmp_path / "bundle"


def test_build_bundle_cli_accepts_uk_suite(tmp_path, monkeypatch):
    captured = {}

    class FakeReport:
        valid = True

        def to_dict(self):
            return {"valid": True}

    def fake_build_bundle_dir(output_dir, **kwargs):
        captured["output_dir"] = output_dir
        captured.update(kwargs)
        return FakeReport()

    monkeypatch.setattr("chronicle.harness.build_bundle_dir", fake_build_bundle_dir)

    status = harness_main(["build-bundle", "--suite", "uk", "--out", str(tmp_path)])

    assert status == 0
    assert captured["suite"] == "uk"


def test_build_bundle_writes_merged_consumer_contract(tmp_path):
    output_dir = tmp_path / "bundle"

    report = build_bundle(output_dir, year=2023)
    summary = json.loads((output_dir / "reports" / "build_bundle.json").read_text())
    rows = _load_jsonl(output_dir / "consumer_facts.jsonl")
    source_packages = json.loads((output_dir / "source_packages.json").read_text())
    coverage = json.loads((output_dir / "coverage.json").read_text())

    assert report.valid
    assert summary["valid"]
    assert summary["counts"] == {
        "aggregate_duplicate_key_count": 0,
        "entity_count": 11,
        "error_count": 0,
        "fact_count": 155869,
        "geography_count": 12536,
        "period_count": 191,
        "semantic_duplicate_key_count": 12,
        "skipped_source_count": 10,
        "source_count": 41,
        "source_package_count": 135,
        "warning_count": 1,
    }
    assert len(rows) == 155869
    assert {row["provenance_class"] for row in rows} <= {
        "administrative",
        "census",
        "model_output",
        "survey_aggregate",
    }
    assert all(
        (
            isinstance(row.get("survey_instrument"), str)
            and row["survey_instrument"].strip()
        )
        if row["provenance_class"] == "survey_aggregate"
        else "survey_instrument" not in row
        for row in rows
    )
    assert rows[0]["aggregate_fact_key"].startswith("ledger.aggregate_fact.v2:")
    assert rows[0]["semantic_fact_key"].startswith("ledger.semantic_fact.v2:")
    assert source_packages["source_package_count"] == 135
    assert source_packages["skipped_source_count"] == 10
    assert sorted(item["source"] for item in source_packages["skipped_sources"]) == [
        "census-acs-s0101-congressional-district-age-2024",
        "census-acs-s0101-national-age-2024",
        "census-acs-s0101-state-age-2024",
        "census-acs-s2201-congressional-district-snap-2024",
        "cms-aca-effectuated-enrollment-2022",
        "cms-aca-oep-state-level",
        "cms-aca-oep-state-level-2022",
        "cms-aca-oep-state-level-2025",
        "jct-obbba-revenue-estimates-2025",
        "jct-tax-expenditures-2024",
    ]
    assert coverage["fact_count"] == 155869
    assert coverage["counts"]["by_source"] == {
        "bea": 445,
        "bfp_economic_outlook": 5,
        "cbo": 7,
        "census_acs": 468,
        "census_pep": 4132,
        "census_population_projections": 86,
        "census_stc": 46,
        "cms_medicaid": 515,
        "cms_medicare": 1,
        "cms_nhe": 3,
        "dft": 81,
        "dwp": 6547,
        "eurostat": 108,
        "federal_reserve": 1,
        "hhs_acf_liheap": 2,
        "hhs_acf_tanf": 110,
        "hmrc": 20533,
        "ici": 12,
        "irs_soi": 40243,
        "isc": 2,
        "jrc_euromod_be": 18,
        "kff": 52,
        "mhclg": 2672,
        "nbb_national_accounts": 1,
        "nisra": 510,
        "nrs": 5589,
        "obr": 253,
        "onem_rva_unemployment": 1,
        "ons": 65646,
        "onss_contributions": 1,
        "opgroeien_groeipakket": 11,
        "scotgov": 2504,
        "sfpd_pensions": 4,
        "slc": 199,
        "spf_finances_pit": 1,
        "ssa": 426,
        "statbel_fiscal_income": 565,
        "statbel_population_structure": 18,
        "usda_snap": 852,
        "voa": 3001,
        "welshgov": 198,
    }
    table_counts = coverage["counts"]["by_source_table"]
    assert len(table_counts) == 130
    assert table_counts["irs_soi:Publication 1304 Table 1.4"] == 740
    assert (
        table_counts["irs_soi:Publication 4801 Form 8960, pages 214–215"] == 20
    )
    assert (
        table_counts[
            "dwp:Universal Credit childcare element statistics to August 2025, Table 1"
        ]
        == 54
    )
    assert (
        table_counts[
            "dwp:Households on Universal Credit with carer entitlement, "
            "April to December 2025"
        ]
        == 9
    )
    assert (
        table_counts[
            "dwp:Households on Universal Credit by number of children, "
            "April to December 2025"
        ]
        == 72
    )
    assert (
        table_counts[
            "dwp:Households on Universal Credit by family type, April to December 2025"
        ]
        == 45
    )
    assert (
        table_counts[
            "dwp:Households on Universal Credit with housing entitlement, "
            "April to December 2025"
        ]
        == 9
    )
    assert (
        table_counts[
            "dwp:Households on Universal Credit with LCWRA entitlement, "
            "April to December 2025"
        ]
        == 9
    )
    assert table_counts["usda_snap:SNAP FY2025 Monthly State Participation"] == 636
    assert table_counts["irs_soi:Congressional District Data 2022"] == 26880
    assert table_counts["irs_soi:IRS SOI County Data 2022"] == 6286
    assert table_counts["census_pep:Vintage 2024 County Population Totals"] == 3144
    assert (
        table_counts[
            "dwp:Universal Credit deductions statistics March 2025 to February 2026, Table 1"
        ]
        == 35
    )
    assert (
        table_counts[
            "cms_nhe:Employer-Sponsored Private Health Insurance: "
            "Calendar Years 1987-2024"
        ]
        == 2
    )
    assert table_counts["ssa:SSI Monthly Statistics, December 2024, Table 1"] == 4
    assert table_counts["irs_soi:Publication 1304 Table 1.1"] == 80
    assert (
        table_counts[
            "irs_soi:Publication 1304 Table 2.5 EITC by AGI and qualifying children"
        ]
        == 464
    )
    assert table_counts["bea:BEA Regional annual state personal income CSV ZIP"] == 416
    assert (
        table_counts["cbo:CBO budget and economic data, individual income tax receipts"]
        == 1
    )
    assert (
        table_counts[
            "cbo:Revenue Projections, by Category, February 2026, "
            "sheet 3.Individual Income Tax Details"
        ]
        == 6
    )
    assert (
        table_counts[
            "census_acs:ACS 2023 1-year detailed table B01001 female age bands by state"
        ]
        == 468
    )
    assert (
        table_counts[
            "cms_medicaid:State Medicaid and CHIP Applications, Eligibility "
            "Determinations, and Enrollment Data"
        ]
        == 515
    )
    assert table_counts["ssa:SSA Annual Statistical Supplement 2025 Table 7.B1"] == 416
    assert (
        table_counts[
            "ons:UK Business, Activity, Size and Location 2025 enterprise "
            "counts by SIC division, turnover band, and employment size band"
        ]
        == 1232
    )
    assert (
        table_counts[
            "ons:UK Business, Activity, Size and Location 2025 enterprise "
            "turnover and employment size bands"
        ]
        == 14
    )
    assert (
        table_counts[
            "hmrc:Annual UK VAT Statistics 2024 to 2025 VAT trader "
            "population and net VAT liability by trade sector"
        ]
        == 176
    )
    assert (
        table_counts[
            "hmrc:Annual UK VAT Statistics 2024 to 2025 VAT trader "
            "population and net VAT liability by turnover band"
        ]
        == 17
    )
    assert (
        table_counts[
            "statbel_fiscal_income:Personal income tax statistics by municipality, "
            "income year 2023, 2025 NIS geography"
        ]
        == 565
    )
    assert (
        table_counts[
            "spf_finances_pit:Personal income tax statistics total taxes, income year "
            "2023"
        ]
        == 1
    )
    assert (
        table_counts[
            "statbel_population_structure:Population by place of residence, nationality, "
            "marital status, age and sex, 2026"
        ]
        == 18
    )
    assert (
        table_counts[
            "onss_contributions:Declared contributions 2024, Table 6 by sector, "
            "status and sex"
        ]
        == 1
    )
    assert (
        table_counts[
            "onem_rva_unemployment:Annual report complete unemployment benefit "
            "recipients, 2024"
        ]
        == 1
    )
    assert (
        table_counts[
            "nbb_national_accounts:Household income accounts, gross disposable income, "
            "Belgium"
        ]
        == 1
    )
    assert (
        table_counts[
            "jrc_euromod_be:EUROMOD Country Report Belgium 2025 validation tables"
        ]
        == 18
    )
    assert (
        table_counts[
            "eurostat:Eurostat gov_10a_taxag Main national accounts tax "
            "aggregates for Belgium, Germany, and France"
        ]
        == 24
    )
    assert (
        table_counts[
            "eurostat:Eurostat spr_exp_func Expenditure on social benefits by "
            "function for Belgium, Germany, and France"
        ]
        == 27
    )
    assert (
        table_counts[
            "eurostat:Eurostat ilc_li02 At-risk-of-poverty rate by poverty "
            "threshold, age and sex - EU-SILC and ECHP surveys for Belgium, "
            "Germany, and France"
        ]
        == 3
    )
    assert (
        table_counts[
            "eurostat:Eurostat ilc_di01 Distribution of income by quantiles "
            "for Belgium, Germany, and France"
        ]
        == 54
    )
    assert coverage["counts"]["by_period"] == {
        "academic_year:2013": 6,
        "academic_year:2014": 6,
        "academic_year:2015": 6,
        "academic_year:2016": 6,
        "academic_year:2017": 6,
        "academic_year:2018": 6,
        "academic_year:2019": 6,
        "academic_year:2020": 6,
        "academic_year:2021": 6,
        "academic_year:2022": 6,
        "academic_year:2023": 6,
        "academic_year:2024": 26,
        "academic_year:2025": 20,
        "academic_year:2026": 20,
        "academic_year:2027": 20,
        "academic_year:2028": 20,
        "academic_year:2029": 16,
        "calendar_year:1951": 3,
        "calendar_year:1961": 3,
        "calendar_year:1971": 3,
        "calendar_year:1981": 3,
        "calendar_year:1995": 3,
        "calendar_year:1996": 36,
        "calendar_year:1997": 36,
        "calendar_year:1998": 36,
        "calendar_year:1999": 36,
        "calendar_year:2000": 36,
        "calendar_year:2001": 36,
        "calendar_year:2002": 39,
        "calendar_year:2003": 39,
        "calendar_year:2004": 39,
        "calendar_year:2005": 39,
        "calendar_year:2006": 39,
        "calendar_year:2007": 39,
        "calendar_year:2008": 39,
        "calendar_year:2009": 39,
        "calendar_year:2010": 39,
        "calendar_year:2011": 39,
        "calendar_year:2012": 39,
        "calendar_year:2013": 72,
        "calendar_year:2014": 72,
        "calendar_year:2015": 74,
        "calendar_year:2016": 72,
        "calendar_year:2017": 72,
        "calendar_year:2018": 86,
        "calendar_year:2019": 85,
        "calendar_year:2020": 85,
        "calendar_year:2021": 3992,
        "calendar_year:2022": 1913,
        "calendar_year:2023": 6202,
        "calendar_year:2024": 33799,
        "calendar_year:2025": 4446,
        "calendar_year:2026": 241,
        "calendar_year:2027": 220,
        "calendar_year:2028": 220,
        "calendar_year:2029": 220,
        "calendar_year:2031": 2,
        "fiscal_year:1996": 33,
        "fiscal_year:1997": 33,
        "fiscal_year:1998": 33,
        "fiscal_year:1999": 33,
        "fiscal_year:2000": 33,
        "fiscal_year:2001": 33,
        "fiscal_year:2002": 33,
        "fiscal_year:2003": 33,
        "fiscal_year:2004": 33,
        "fiscal_year:2005": 33,
        "fiscal_year:2006": 33,
        "fiscal_year:2007": 33,
        "fiscal_year:2008": 33,
        "fiscal_year:2009": 33,
        "fiscal_year:2010": 33,
        "fiscal_year:2011": 33,
        "fiscal_year:2012": 33,
        "fiscal_year:2013": 33,
        "fiscal_year:2014": 33,
        "fiscal_year:2015": 33,
        "fiscal_year:2016": 33,
        "fiscal_year:2017": 33,
        "fiscal_year:2018": 33,
        "fiscal_year:2019": 33,
        "fiscal_year:2020": 33,
        "fiscal_year:2021": 33,
        "fiscal_year:2022": 33,
        "fiscal_year:2023": 385,
        "fiscal_year:2024": 611,
        "fiscal_year:2025": 1288,
        "fiscal_year:2026": 1443,
        "fiscal_year:2027": 32,
        "fiscal_year:2028": 32,
        "fiscal_year:2029": 32,
        "fiscal_year:2030": 28,
        "month:2021-03": 1,
        "month:2021-04": 1,
        "month:2021-05": 1,
        "month:2021-06": 1,
        "month:2021-07": 1,
        "month:2021-08": 1,
        "month:2021-09": 1,
        "month:2021-10": 1,
        "month:2021-11": 1,
        "month:2021-12": 1,
        "month:2022-01": 1,
        "month:2022-02": 1,
        "month:2022-03": 1,
        "month:2022-04": 1,
        "month:2022-05": 1,
        "month:2022-06": 1,
        "month:2022-07": 1,
        "month:2022-08": 1,
        "month:2022-09": 1,
        "month:2022-10": 1,
        "month:2022-11": 1,
        "month:2022-12": 1,
        "month:2023-01": 2,
        "month:2023-02": 1,
        "month:2023-03": 1,
        "month:2023-04": 1,
        "month:2023-05": 1,
        "month:2023-06": 1,
        "month:2023-07": 1,
        "month:2023-08": 1,
        "month:2023-09": 1,
        "month:2023-10": 1,
        "month:2023-11": 1,
        "month:2023-12": 7,
        "month:2024-01": 2,
        "month:2024-02": 1,
        "month:2024-03": 1,
        "month:2024-04": 1,
        "month:2024-05": 1,
        "month:2024-06": 1,
        "month:2024-07": 1,
        "month:2024-08": 1,
        "month:2024-09": 1,
        "month:2024-10": 107,
        "month:2024-11": 107,
        "month:2024-12": 377,
        "month:2025-01": 109,
        "month:2025-02": 107,
        "month:2025-03": 229,
        "month:2025-04": 112,
        "month:2025-05": 6221,
        "month:2025-06": 20,
        "month:2025-07": 20,
        "month:2025-08": 24,
        "month:2025-09": 28,
        "month:2025-10": 19,
        "month:2025-11": 34,
        "month:2025-12": 275,
        "month:2026-01": 3,
        "month:2026-02": 7,
        "month:2026-06": 348,
        "tax_year:1987": 9,
        "tax_year:1988": 9,
        "tax_year:1989": 9,
        "tax_year:1990": 9,
        "tax_year:1991": 9,
        "tax_year:1992": 9,
        "tax_year:1993": 9,
        "tax_year:1994": 9,
        "tax_year:1995": 9,
        "tax_year:1996": 9,
        "tax_year:1997": 9,
        "tax_year:1998": 9,
        "tax_year:1999": 9,
        "tax_year:2000": 9,
        "tax_year:2001": 9,
        "tax_year:2002": 9,
        "tax_year:2003": 9,
        "tax_year:2004": 9,
        "tax_year:2005": 9,
        "tax_year:2006": 9,
        "tax_year:2007": 9,
        "tax_year:2008": 9,
        "tax_year:2009": 9,
        "tax_year:2010": 9,
        "tax_year:2011": 9,
        "tax_year:2012": 9,
        "tax_year:2013": 9,
        "tax_year:2014": 9,
        "tax_year:2015": 9,
        "tax_year:2016": 9,
        "tax_year:2017": 9,
        "tax_year:2018": 9,
        "tax_year:2019": 9,
        "tax_year:2020": 9,
        "tax_year:2021": 9,
        "tax_year:2022": 41237,
        "tax_year:2023": 48616,
        "tax_year:2024": 40,
    }
    assert coverage["counts"]["by_geography"]["country:BE"] == 67
    assert coverage["counts"]["by_geography"]["country:DE"] == 36
    assert coverage["counts"]["by_geography"]["country:FR"] == 36
    assert coverage["counts"]["by_geography"]["nuts1:BE1"] == 6
    assert coverage["counts"]["by_geography"]["nuts1:BE2"] == 17
    assert coverage["counts"]["by_geography"]["nuts1:BE3"] == 6
    assert coverage["counts"]["by_geography"]["commune:11002"] == 1
    assert coverage["counts"]["by_geography"]["country:0100000US"] == 2289
    assert coverage["counts"]["by_geography"]["state:0400000US06"] == 229
    assert (
        coverage["counts"]["by_geography"]["congressional_district:5001700US0601"] == 56
    )
    assert coverage["counts"]["by_geography"]["country:K02000001"] == 4262
    assert coverage["counts"]["by_geography"]["country:K03000001"] == 497
    assert len(coverage["counts"]["by_geography"]) == 12536
    assert coverage["counts"]["by_entity"] == {
        "benefit_unit": 233,
        "dwelling": 12708,
        "family": 107,
        "firm": 1439,
        "government": 294,
        "household": 40435,
        "institutional_sector": 103,
        "pension_plan": 2,
        "person": 60272,
        "social_protection_scheme": 27,
        "tax_unit": 40249,
    }
    assert not coverage["duplicates"]["aggregate_fact_keys"]
    assert len(coverage["duplicates"]["semantic_fact_keys"]) == 12
    assert summary["warnings"] == [
        {
            "code": "duplicate_semantic_fact_key",
            "message": (
                "One or more semantic facts appear in multiple rows; downstream "
                "consumers should reconcile or select sources."
            ),
        }
    ]
    for source in (
        "dwp-uc-childcare-element-march-2021-august-2025",
        "dwp-uc-households-carer-entitlement-april-december-2025",
        "dwp-uc-households-children-april-december-2025",
        "dwp-uc-households-family-type-april-december-2025",
        "dwp-uc-households-housing-entitlement-april-december-2025",
        "dwp-uc-households-lcwra-entitlement-april-december-2025",
    ):
        assert (output_dir / "sources" / source / "consumer_facts.jsonl").exists()
    assert (output_dir / "sources" / "soi-table-1-1" / "consumer_facts.jsonl").exists()
    assert (
        output_dir / "sources" / "soi-table-1-4" / "reports" / "build_summary.json"
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
        output_dir
        / "sources"
        / "census-stc-individual-income-tax"
        / "consumer_facts.jsonl"
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
        output_dir / "sources" / "cms-nhe-table-24" / "consumer_facts.jsonl"
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
        output_dir
        / "sources"
        / "usda-snap-fy2025-monthly-state-caseloads"
        / "consumer_facts.jsonl"
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
        / "soi-congressional-district-2022"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "cbo-revenue-projections-income-by-source-2026-02"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "bea-regional-state-personal-income-components-2024"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir / "sources" / "ssa-ssi-table-7b1-2024" / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "ssa-ssi-monthly-statistics-2024-12"
        / "consumer_facts.jsonl"
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
        / "ons-uk-business-firm-targets-2025"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "ons-uk-business-firm-sector-targets-2025"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "hmrc-vat-firm-targets-2024-25"
        / "consumer_facts.jsonl"
    ).exists()
    assert (
        output_dir
        / "sources"
        / "hmrc-vat-firm-sector-targets-2024-25"
        / "consumer_facts.jsonl"
    ).exists()
    for source in (
        "eurostat-gov-10a-taxag",
        "eurostat-spr-exp-func",
        "eurostat-ilc-li02",
        "eurostat-ilc-di01",
    ):
        assert (output_dir / "sources" / source / "consumer_facts.jsonl").exists()


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
    assert {row["universe_constraints"]["constraints"][0]["value"] for row in rows} == {
        "social_security_benefits",
        "social_security_retirement_benefits",
        "social_security_survivors_benefits",
        "social_security_disability_benefits",
        "social_security_dependents_benefits",
        "ssi_payments",
    }


def test_build_bundle_cli_supports_jct_tax_expenditure_source(tmp_path, capsys):
    output_dir = tmp_path / "bundle"

    exit_code = harness_main(
        [
            "build-bundle",
            "--year",
            "2024",
            "--source",
            "jct-tax-expenditures-2024",
            "--out",
            str(output_dir),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    rows = _load_jsonl(output_dir / "consumer_facts.jsonl")

    assert exit_code == 0
    assert payload["valid"]
    assert payload["counts"]["source_package_count"] == 1
    assert payload["counts"]["fact_count"] == 11
    assert payload["coverage"]["counts"]["by_source"] == {"jct": 11}
    assert payload["coverage"]["counts"]["by_entity"] == {"tax_unit": 11}
    assert {row["lineage"]["source_record_id"] for row in rows} == {
        "jct.tax_expenditures.cy2024.salt_deduction.revenue_loss",
        "jct.tax_expenditures.cy2024.medical_expense_deduction.revenue_loss",
        "jct.tax_expenditures.cy2024.charitable_deduction.revenue_loss",
        "jct.tax_expenditures.cy2024.deductible_mortgage_interest.revenue_loss",
        "jct.tax_expenditures.cy2024.qualified_business_income_deduction.revenue_loss",
        # JCX-48-24 extension (microcosm#514 anchors):
        "jct.tax_expenditures.cy2024.self_employed_health_insurance_deduction.revenue_loss",
        "jct.tax_expenditures.cy2024.health_savings_account_deduction.revenue_loss",
        "jct.tax_expenditures.cy2024.student_loan_interest_deduction.revenue_loss",
        "jct.tax_expenditures.cy2024.self_employed_pension_contribution_deduction.revenue_loss",
        "jct.tax_expenditures.cy2024.traditional_ira_deduction.revenue_loss",
        "jct.tax_expenditures.cy2024.cdcc_and_employer_child_care_exclusion.revenue_loss",
    }


def test_build_bundle_cli_supports_jct_obbba_source(tmp_path, capsys):
    output_dir = tmp_path / "bundle"

    exit_code = harness_main(
        [
            "build-bundle",
            "--year",
            "2026",
            "--source",
            "jct-obbba-revenue-estimates-2025",
            "--out",
            str(output_dir),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    rows = _load_jsonl(output_dir / "consumer_facts.jsonl")

    assert exit_code == 0
    assert payload["valid"]
    assert payload["counts"]["source_package_count"] == 1
    assert payload["counts"]["fact_count"] == 2
    assert payload["coverage"]["counts"]["by_source"] == {"jct": 2}
    assert payload["coverage"]["counts"]["by_entity"] == {"tax_unit": 2}
    assert {row["lineage"]["source_record_id"] for row in rows} == {
        "jct.obbba_title_vii.fy2026.no_tax_on_tips.revenue_effect",
        "jct.obbba_title_vii.fy2026.no_tax_on_overtime.revenue_effect",
    }
    values = {row["lineage"]["source_record_id"]: row["value"] for row in rows}
    # JCX-35-25 FY2026: tips -$10,121M, overtime -$32,806M.
    assert (
        values["jct.obbba_title_vii.fy2026.no_tax_on_tips.revenue_effect"]
        == -10_121_000_000
    )
    assert (
        values["jct.obbba_title_vii.fy2026.no_tax_on_overtime.revenue_effect"]
        == -32_806_000_000
    )


def test_build_bundle_coverage_reports_duplicate_keys():
    rows = [
        {
            "aggregate_fact_key": "ledger.aggregate_fact.v2:a",
            "semantic_fact_key": "ledger.semantic_fact.v2:s",
            "legacy_fact_key": "ledger.fact.v1:one",
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
            "aggregate_fact_key": "ledger.aggregate_fact.v2:a",
            "semantic_fact_key": "ledger.semantic_fact.v2:s",
            "legacy_fact_key": "ledger.fact.v1:two",
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
                "key": "ledger.aggregate_fact.v2:a",
                "count": 2,
                "sources": ["irs_soi:Publication 1304 Table 1.1"],
                "legacy_fact_keys": ["ledger.fact.v1:one", "ledger.fact.v1:two"],
            }
        ],
        semantic_duplicates=[
            {
                "key": "ledger.semantic_fact.v2:s",
                "count": 2,
                "sources": ["irs_soi:Publication 1304 Table 1.1"],
                "legacy_fact_keys": ["ledger.fact.v1:one", "ledger.fact.v1:two"],
            }
        ],
    )

    assert coverage["counts"]["by_source"] == {"irs_soi": 2}
    assert coverage["duplicates"]["aggregate_fact_keys"][0]["count"] == 2
    assert coverage["duplicates"]["semantic_fact_keys"][0]["count"] == 2
