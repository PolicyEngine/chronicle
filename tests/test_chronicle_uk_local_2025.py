"""Publisher coverage and period regressions for chronicle#313."""

import hashlib
from pathlib import Path

import pytest
import yaml

from chronicle.consumer_contract import validate_consumer_fact_contract
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package


def test_mid2025_local_authority_population_keeps_all_four_nations():
    """Nomis NM_31_1 must retain NI's eleven districts alongside GB."""
    facts = load_source_package("ons-lad-population-by-age-2025").build_facts(2025)
    totals = [f for f in facts if f.filters == {"age_name": "All ages"}]
    assert len(totals) == 361
    assert len({f.geography.id for f in totals}) == 361
    assert sum(f.geography.id.startswith("N09") for f in totals) == 11
    assert {f.period.value for f in facts} == {2025}
    assert {f.source.vintage for f in facts} == {"mid_2025"}
    assert all(f.source_cell_keys and f.source_row_keys for f in facts)
    assert validate_consumer_fact_contract(facts).valid


def test_lfs_household_totals_cover_countries_regions_and_all_published_years():
    """Table 7 country/region totals retain the publisher's survey uncertainty."""
    facts = load_source_package(
        "ons-household-totals-country-region-2015-2025"
    ).build_facts(2025)
    totals = [f for f in facts if f.measure.concept == "ons.households_total"]
    assert len(totals) == 12 * 11
    assert {f.period.value for f in totals} == set(range(2015, 2026))
    assert len({f.geography.id for f in totals}) == 12
    latest = {f.geography.id: f for f in totals if f.period.value == 2025}
    # ONS Table 7, all-households row, 2025 Estimate (thousands).
    assert latest["E92000001"].value == 24_329_000
    assert latest["W92000004"].value == 1_404_000
    assert latest["S92000003"].value == 2_520_000
    for fact in totals:
        assert fact.provenance_class == "survey_aggregate"
        assert fact.survey_instrument == "Labour Force Survey"
        assert "95%" in fact.measure.concept_evidence_notes
        assert "CV" in fact.measure.concept_evidence_notes
        assert fact.period_coverage.start_date == f"{fact.period.value}-04-01"
        assert fact.period_coverage.end_date == f"{fact.period.value}-06-30"
        assert fact.source_cell_keys
    assert validate_consumer_fact_contract(totals).valid


def test_household_controls_keep_private_households_projections_and_stock_distinct():
    nrs = load_source_package("nrs-households-dwellings-2025").build_facts(2025)
    national = {
        f.measure.concept: f
        for f in nrs
        if f.geography.id == "S92000003" and f.period.value == 2025
    }
    assert national["nrs.households_total"].value == 2_570_799
    assert national["nrs.households_total"].period_coverage.end_date == "2025-06-30"
    assert national["nrs.dwellings_total"].value == 2_757_863
    assert national["nrs.dwellings_total"].period_coverage.end_date == "2025-09-30"

    welsh = load_source_package("welshgov-household-estimates-mid2024").build_facts(
        2024
    )
    assert len(welsh) == 23 * 3
    assert {f.period.value for f in welsh} == {2022, 2023, 2024}
    assert all(f.filters["Data description"] == "Number of households" for f in welsh)
    latest = next(
        f for f in welsh if f.period.value == 2024 and f.geography.id == "W92000004"
    )
    assert latest.value == pytest.approx(1_388_543.065)
    assert "private-household" in latest.period_coverage.notes

    england = load_source_package("ons-household-projections-2022-based").build_facts(
        2025
    )
    assert {f.period.value for f in england} == set(range(2022, 2048))
    assert all(f.assertion == "source_projection" for f in england)
    assert (
        next(
            f.value
            for f in england
            if f.geography.id == "E92000001" and f.period.value == 2025
        )
        == 24_440_280
    )
    projected = load_source_package(
        "welshgov-household-projections-2022-based"
    ).build_facts(2025)
    assert len(projected) == 23
    assert {f.assertion for f in projected} == {"source_projection"}
    assert next(f.value for f in projected if f.geography.id == "W92000004") == (
        pytest.approx(1_401_715.087)
    )

    stock = load_source_package("lps-housing-stock-lgd-2026").build_facts(2026)
    assert len(stock) == 72
    assert {f.period.value for f in stock} == set(range(2021, 2027))
    assert all(f.entity.name == "dwelling" for f in stock)
    assert {f.period_coverage.end_date for f in stock} == {
        f"{year}-04-01" for year in range(2021, 2027)
    }


def test_rm120_retains_age_sex_residence_and_2023_lad_boundaries():
    facts = load_source_package(
        "ons-census2021-rm120-pcon24-residence2-sex0"
    ).build_facts(2021)
    assert len(facts) == 575 * 24
    totals = {
        f.geography.id: f for f in facts if f.filters["C2021_AGE_24_NAME"] == "Total"
    }
    assert totals["E14001319"].value == 14_262  # Leeds Central and Headingley
    assert totals["E14001467"].value == 13_306  # Sheffield Central
    assert all(
        f.filters["C2021_RESTYPE_3_NAME"] == "Lives in a communal establishment"
        for f in facts
    )
    assert all(f.period_coverage.start_date == "2021-03-21" for f in facts)
    assert all(f.source_row_keys and f.source_cell_keys for f in facts)
    local = load_source_package("ons-census2021-rm120-lad-residence1-sex1").build_facts(
        2021
    )
    assert len(local) == 318 * 24
    assert {f.geography.vintage for f in local} == {"lad_2023"}
    assert "E06000063" in {f.geography.id for f in local}  # Cumberland
    assert {f.period.value for f in local} == {2021}


def test_scottish_census_keeps_disclosure_controlled_residence_counts():
    facts = load_source_package("nrs-census2022-uv101a-ukpc24").build_facts(2022)
    assert len({f.geography.id for f in facts}) == 57
    assert {f.filters["Residence Type Indicator"] for f in facts} == {
        "Lives in a household",
        "Lives in a communal establishment",
    }
    assert len({f.filters["Age"] for f in facts}) == 21  # 20 categories plus total
    assert all(f.period_coverage.end_date == "2022-03-20" for f in facts)
    assert all(f.source_row_keys and f.source_cell_keys for f in facts)
    assert all(
        "disclosure-controlled" in f.measure.concept_evidence_notes for f in facts
    )


def test_ni_communal_counts_preserve_positions_and_exclude_percentage_table():
    district = load_source_package(
        "nisra-census2021-ct0105-communal-residents-lgd"
    ).build_facts(2021)
    assert len(district) == 11 * 2 * 7 * 2
    assert len({f.filters["position_in_establishment"] for f in district}) == 2
    ward = load_source_package(
        "nisra-census2021-ms-f04-communal-residents-ward"
    ).build_facts(2021)
    assert len(ward) == 462 * 15
    assert {f.geography.level for f in ward} == {"statistical_scope"}
    assert (
        next(
            f.value
            for f in ward
            if f.geography.id == "N08000101"
            and f.filters["sex"] == "All persons"
            and f.filters["age_band"] == "All ages"
        )
        == 21
    )


@pytest.mark.parametrize(
    "grain,areas", [("constituency", 632), ("local-authority", 350)]
)
def test_uc_area_packages_preserve_all_months_and_extraction_vintage(grain, areas):
    facts = load_source_package(
        f"dwp-uc-households-by-{grain}-january-2025-may-2026"
    ).build_facts(2025)
    months = {f"2025-{month:02d}" for month in range(1, 13)} | {
        f"2026-{month:02d}" for month in range(1, 6)
    }
    assert len(facts) == areas * 17
    assert {f.period.value for f in facts} == months
    assert all(f.period.type == "month" for f in facts)
    assert {f.source.vintage for f in facts} == {"stat_xplore_extracted_2026_10_07"}
    assert all(f.source_row_keys and f.source_cell_keys for f in facts)


def test_scottish_rent_statistics_keep_unavailable_cells_out_of_numeric_facts():
    facts = load_source_package("scotgov-private-sector-rents-2025").build_facts(2025)
    brma = [f for f in facts if f.geography.id.startswith("S33")]
    assert len(brma) == 18 * 5 * 4
    assert {f.filters["Measure"] for f in brma} == {
        "Mean",
        "Median",
        "Lower Quartile",
        "Upper Quartile",
    }
    assert all(
        f.filters["Measure"] == "Mean" for f in facts if f.geography.id == "S92000003"
    )
    assert all(f.period_coverage.start_date == "2024-10-01" for f in facts)
    assert all(f.period_coverage.end_date == "2025-09-30" for f in facts)


def test_pipr_keeps_independent_bedroom_and_property_breakdowns():
    facts = load_source_package("ons-pipr-rents-by-area-august-2026").build_facts(2026)
    latest = [
        f
        for f in facts
        if f.period.value == "2026-08" and f.geography.id.startswith("S33")
    ]
    assert len(latest) == 18 * 9  # all dwellings, four bedrooms, four property types
    assert all(not ({"bedrooms", "property_type"} <= f.filters.keys()) for f in facts)
    assert len([f for f in latest if not f.filters]) == 18
    assert {f.measure.unit for f in facts} == {"gbp"}
    assert all(f.source_row_keys and f.source_cell_keys for f in facts)
    ni = [f for f in facts if f.geography.id == "N92000002" and not f.filters]
    assert max(f.period.value for f in ni) == "2026-06"


def test_devolved_mid2025_population_keeps_single_years_and_open_age_band():
    scotland = load_source_package("nrs-mye-2025-council-area").build_facts(2025)
    assert len(scotland) == 33 * 3 * 92
    assert all(f.geography.id.startswith(("S12", "S92")) for f in scotland)
    assert (
        next(
            f.value
            for f in scotland
            if f.geography.id == "S92000003"
            and f.filters == {"sex": "all", "age": "All ages"}
        )
        == 5_545_500
    )
    ni = load_source_package("nisra-mye-2025-lgd-single-year-age").build_facts(2025)
    assert len(ni) == 12 * 3 * 91
    oldest = [f for f in ni if f.filters["age"] == 90]
    assert len(oldest) == 12 * 3
    assert all("90 and over" in f.measure.concept_evidence_notes for f in oldest)
    assert all(f.period_coverage.end_date == "2025-06-30" for f in scotland + ni)
    revised = load_source_package("nrs-pcon24-population-by-age-2024-revised-2026")
    specs = revised.build_source_record_set_specs(2024)
    assert {s.period for s in specs} == set(range(2011, 2025))
    assert revised.artifact.vintage == "nrs_revised_small_area_2026_09_01_dz2022"
    assert all(len(s.rows) == 57 and len(s.measures) == 92 for s in specs)


@pytest.mark.parametrize(
    "directory,pinned_sha",
    [
        (
            "scotgov/brma_boundaries_2009",
            "4d121236a35ce896edeb663a7c2c390053c0deebe0cc149c84696bbfd4bddec0",
        ),
        ("scotgov/brma_postcode_lookup_2023", "50366fea"),
        (
            "scotgov/brma_market_evidence_2016_2021",
            "dba86fa1cce920c8f646460bb13e1d99e16927d57fdf290e874f9631e804ed06",
        ),
        ("nrs/oa2022_population_weighted_centroids", "509d7d93"),
        ("voa/brma_boundaries_2020", None),
        ("welshgov/brma_boundaries_2012", None),
        ("ons/lsoa2021_population_weighted_centroids_v4", None),
        ("voa/shadow_list_of_rents_april_2026", None),
        ("welshgov/shadow_list_of_rents_2023", None),
    ],
)
def test_brma_geometry_and_record_level_rents_remain_raw_only(directory, pinned_sha):
    path = Path(__file__).resolve().parents[1] / "db/data" / directory
    manifest = yaml.safe_load((path / "manifest.yaml").read_text())
    assert manifest["registration_kind"] == "raw_only"
    assert directory not in {str(p) for p in SOURCE_PACKAGE_ALIASES.values()}
    for spec in manifest["files"].values():
        content = (path / spec["filename"]).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        assert digest == spec["sha256"]
        assert len(content) == spec["size_bytes"]
        assert spec["storage"]["r2"]["uri"].startswith("r2://ledger-raw/raw/uk/")
        if pinned_sha:
            assert digest.startswith(pinned_sha)
