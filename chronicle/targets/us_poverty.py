"""US poverty and nonfiler source-target coverage.

Chronicle only records source-backed inputs. Microcosm owns the active calibration
profile, source reconciliation, aging, and model variable mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from chronicle.source_package import SOURCE_PACKAGE_ALIASES, SOURCE_PACKAGE_FILENAME


CoverageRole = Literal["hard_target", "validation_only", "source_gap"]


@dataclass(frozen=True)
class TargetSourceCoverage:
    """Coverage status for one source family relevant to poverty calibration."""

    family_id: str
    label: str
    role: CoverageRole
    source_scope: str
    package_aliases: tuple[str, ...] = ()
    missing_source_packages: tuple[str, ...] = ()
    notes: str = ""

    @property
    def has_chronicle_package(self) -> bool:
        """Return whether this family has at least one Chronicle package alias."""
        return bool(self.package_aliases)


US_POVERTY_NONFILER_TARGET_COVERAGE: tuple[TargetSourceCoverage, ...] = (
    TargetSourceCoverage(
        family_id="population_age_sex",
        label="Population by age, sex, state, and congressional district",
        role="hard_target",
        source_scope="Census population estimates and ACS demographics",
        package_aliases=(
            "census-pep-2024-national-age-sex",
            "census-pep-2024-state-age-sex",
            "census-acs-s0101-national-age-2024",
            "census-acs-s0101-state-age-2024",
            "census-acs-s0101-congressional-district-age-2024",
        ),
        notes=(
            "Use PEP for population controls. ACS geography/detail can support "
            "local allocation and validation."
        ),
    ),
    TargetSourceCoverage(
        family_id="nipa_personal_income",
        label="NIPA personal income, transfers, taxes, and pensions",
        role="hard_target",
        source_scope="BEA NIPA full-population aggregates",
        package_aliases=(
            "bea-nipa-total-wages-salaries",
            "bea-nipa-personal-income-components",
            "bea-nipa-personal-income-disposition",
            "bea-nipa-pension-contributions",
        ),
        notes=(
            "This is the main non-SOI full-population backstop for wages, "
            "proprietors' income, rental income, interest, dividends, UI, "
            "Social Security, SSI, SNAP, Medicare, Medicaid, TANF, personal "
            "taxes, and disposable personal income."
        ),
    ),
    TargetSourceCoverage(
        family_id="irs_soi_filer_income_tax_credits",
        label="SOI filer income, taxes, deductions, and credits",
        role="hard_target",
        source_scope="IRS SOI filer administrative totals",
        package_aliases=(
            "soi-table-1-1",
            "soi-table-1-2",
            "soi-table-1-4",
            "soi-table-2-1",
            "soi-table-2-5",
            "soi-table-2-5-eitc-agi-children-2023",
            "soi-filing-season-week47-2024-eitc-total",
            "soi-table-4-3",
            "soi-state-2022",
            "soi-historic-table-2",
            "soi-historic-table-2-state-agi-2022",
            "soi-historic-table-2-state-agi-2023",
            "soi-historic-table-2-state-broad-2022",
            "soi-historic-table-2-state-eitc-2022",
            "soi-w2-statistics-2020",
        ),
        notes=(
            "Use for filer and tax-form aggregates. Pair with NIPA/program "
            "administrative controls to avoid making nonfilers inherit SOI-only "
            "coverage."
        ),
    ),
    TargetSourceCoverage(
        family_id="social_security_ssi",
        label="Social Security and SSI payments",
        role="hard_target",
        source_scope="SSA administrative program totals",
        package_aliases=(
            "ssa-annual-statistical-supplement-2025",
            "ssa-ssi-table-7b1-2024",
        ),
        notes=("SSA gives program-specific checks on the broader NIPA transfer lines."),
    ),
    TargetSourceCoverage(
        family_id="snap_admin",
        label="SNAP participation and benefit cost",
        role="hard_target",
        source_scope="USDA FNS administrative totals",
        package_aliases=("usda-snap-fy69-to-current",),
    ),
    TargetSourceCoverage(
        family_id="tanf_admin",
        label="TANF caseload and financial data",
        role="hard_target",
        source_scope="HHS ACF administrative totals",
        package_aliases=(
            "hhs-acf-tanf-caseload-2024",
            "hhs-acf-tanf-financial-2024",
        ),
    ),
    TargetSourceCoverage(
        family_id="liheap_admin",
        label="LIHEAP households and benefits",
        role="hard_target",
        source_scope="HHS ACF LIHEAP administrative profile",
        package_aliases=(
            "hhs-acf-liheap-fy2023-national-profile",
            "hhs-acf-liheap-fy2024-national-profile",
        ),
    ),
    TargetSourceCoverage(
        family_id="health_programs",
        label="Medicaid, CHIP, ACA, Medicare, and NHE controls",
        role="hard_target",
        source_scope="CMS administrative enrollment and expenditure totals",
        package_aliases=(
            "cms-medicaid-chip-monthly-enrollment-dataset",
            "cms-medicaid-chip-monthly-enrollment-december-2024",
            "cms-nhe-historical-service-source",
            "cms-aca-oep-state-level",
            "cms-aca-oep-state-level-2022",
            "cms-aca-oep-state-level-2025",
            "cms-aca-effectuated-enrollment-2022",
            "cms-medicare-trustees-report-2025-part-b-premium-income",
        ),
        notes=(
            "Health coverage and public health spending affect SPM resources "
            "mostly through premiums, subsidies, and out-of-pocket costs."
        ),
    ),
    TargetSourceCoverage(
        family_id="state_income_tax_collections",
        label="State individual income tax collections",
        role="hard_target",
        source_scope="Census Annual Survey of State Government Tax Collections",
        package_aliases=("census-stc-individual-income-tax",),
    ),
    TargetSourceCoverage(
        family_id="snap_local_proxy",
        label="SNAP congressional district household estimates",
        role="validation_only",
        source_scope="ACS S2201 survey estimates",
        package_aliases=("census-acs-s2201-congressional-district-snap-2024",),
        notes=(
            "ACS is not CPS, but it is still a survey estimate. Use for local "
            "validation or allocation, not as a national hard target."
        ),
    ),
    TargetSourceCoverage(
        family_id="cbo_income_revenue_projection",
        label="CBO income and revenue projections",
        role="validation_only",
        source_scope="CBO projection tables",
        package_aliases=("cbo-revenue-projections-income-by-source-2026-02",),
        notes="Use for forecast/aging checks, not contemporaneous calibration.",
    ),
    TargetSourceCoverage(
        family_id="wealth_balance_sheet",
        label="Household net worth balance-sheet checks",
        role="validation_only",
        source_scope="Federal Reserve Financial Accounts",
        package_aliases=("federal-reserve-z1-household-net-worth",),
    ),
    TargetSourceCoverage(
        family_id="census_cps_spm",
        label="Census CPS ASEC SPM poverty, resources, and thresholds",
        role="validation_only",
        source_scope="CPS-derived official poverty measurement",
        notes=(
            "Use to diagnose the SPM result. Do not hard-target it while fixing "
            "CPS/Microcosm poverty-resource construction."
        ),
    ),
    TargetSourceCoverage(
        family_id="dina_distributional_accounts",
        label="Distributional national accounts",
        role="validation_only",
        source_scope="Distributional estimates partly informed by CPS/SCF/SOI",
        notes=(
            "Useful for reasonableness checks, but not an independent poverty "
            "target because it can reintroduce CPS distributional assumptions."
        ),
    ),
    TargetSourceCoverage(
        family_id="acs_poverty_income_distribution",
        label="ACS poverty and income distributions",
        role="validation_only",
        source_scope="ACS survey estimates",
        notes=(
            "Independent of CPS sampling, but still survey-based and not SPM "
            "resources. Use as validation."
        ),
    ),
    TargetSourceCoverage(
        family_id="hud_assisted_housing",
        label="Housing assistance and subsidy controls",
        role="source_gap",
        source_scope="HUD administrative program data",
        missing_source_packages=(
            "HUD Picture of Subsidized Households",
            "HUD assisted-housing expenditure or unit-count tables",
        ),
        notes=(
            "Needed for SPM capped housing subsidy resources. Current Chronicle has "
            "no HUD source package for this family."
        ),
    ),
    TargetSourceCoverage(
        family_id="usda_wic",
        label="WIC participation and benefits",
        role="source_gap",
        source_scope="USDA FNS administrative totals",
        missing_source_packages=("USDA FNS WIC program data",),
        notes="Needed for SPM WIC resources.",
    ),
    TargetSourceCoverage(
        family_id="usda_school_meals",
        label="School lunch and breakfast benefits",
        role="source_gap",
        source_scope="USDA FNS administrative totals",
        missing_source_packages=(
            "USDA FNS National School Lunch Program data",
            "USDA FNS School Breakfast Program data",
        ),
        notes="Needed for SPM school meal resources.",
    ),
    TargetSourceCoverage(
        family_id="ocse_child_support",
        label="Child support received and paid",
        role="source_gap",
        source_scope="HHS OCSE administrative collections/disbursements",
        missing_source_packages=("HHS OCSE child support annual report tables",),
        notes=(
            "Small in the SPM-rate decomposition, but should be modeled and "
            "chronicled for completeness."
        ),
    ),
    TargetSourceCoverage(
        family_id="dol_workers_compensation",
        label="Workers' compensation benefits",
        role="source_gap",
        source_scope="Program-specific workers' compensation administrative data",
        missing_source_packages=(
            "DOL or NASI workers' compensation benefit totals",
            "State workers' compensation benefit totals",
        ),
        notes=(
            "BEA has broad transfer aggregates, but not the program-specific "
            "source package needed for a clean model target."
        ),
    ),
    TargetSourceCoverage(
        family_id="moop_work_childcare_costs",
        label="MOOP, work expenses, and childcare expense validation",
        role="source_gap",
        source_scope="MEPS, BLS CE, AHS, or other non-CPS validation sources",
        missing_source_packages=(
            "MEPS out-of-pocket medical spending tables",
            "BLS Consumer Expenditure work-related expense tables",
            "Childcare expense validation source",
        ),
        notes=(
            "These are SPM deductions rather than resources. They should be "
            "validation or imputation benchmarks, not blind hard targets."
        ),
    ),
)


def coverage_entries(
    *,
    role: CoverageRole | None = None,
) -> tuple[TargetSourceCoverage, ...]:
    """Return poverty/nonfiler source coverage entries, optionally by role."""
    if role is None:
        return US_POVERTY_NONFILER_TARGET_COVERAGE
    return tuple(
        entry for entry in US_POVERTY_NONFILER_TARGET_COVERAGE if entry.role == role
    )


def hard_target_package_aliases() -> tuple[str, ...]:
    """Return package aliases required for source-backed hard target coverage."""
    aliases = {
        alias
        for entry in coverage_entries(role="hard_target")
        for alias in entry.package_aliases
    }
    return tuple(sorted(aliases))


def validation_only_family_ids() -> tuple[str, ...]:
    """Return validation-only source family IDs."""
    return tuple(entry.family_id for entry in coverage_entries(role="validation_only"))


def source_gap_family_ids() -> tuple[str, ...]:
    """Return source-gap family IDs."""
    return tuple(entry.family_id for entry in coverage_entries(role="source_gap"))


def validate_us_poverty_nonfiler_source_coverage(
    *,
    package_root: str | Path | None = None,
) -> tuple[str, ...]:
    """Validate that hard-target package aliases are registered and present.

    Args:
        package_root: Optional packages directory to check for package YAMLs.

    Returns:
        A tuple of validation error messages.
    """
    errors: list[str] = []
    root = Path(package_root) if package_root is not None else None
    for alias in hard_target_package_aliases():
        package_path = SOURCE_PACKAGE_ALIASES.get(alias)
        if package_path is None:
            errors.append(f"Missing source package alias: {alias}")
            continue
        if root is not None:
            source_package = root / package_path / SOURCE_PACKAGE_FILENAME
            if not source_package.exists():
                errors.append(
                    f"Missing source package file for {alias}: {source_package}"
                )
    return tuple(errors)


__all__ = [
    "CoverageRole",
    "TargetSourceCoverage",
    "US_POVERTY_NONFILER_TARGET_COVERAGE",
    "coverage_entries",
    "hard_target_package_aliases",
    "source_gap_family_ids",
    "validate_us_poverty_nonfiler_source_coverage",
    "validation_only_family_ids",
]
