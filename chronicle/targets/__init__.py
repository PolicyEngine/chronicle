"""Chronicle target source coverage.

Chronicle records which source packages back a consumer's target families. The
legacy SQLite and Supabase target tables (``Target``, ``Stratum``,
``StratumConstraint``) were retired; see ``docs/us-legacy-etl-cleanup.md``.
"""

from .us_poverty import (
    US_POVERTY_NONFILER_TARGET_COVERAGE,
    TargetSourceCoverage,
    coverage_entries,
    hard_target_package_aliases,
    source_gap_family_ids,
    validate_us_poverty_nonfiler_source_coverage,
    validation_only_family_ids,
)

__all__ = [
    "TargetSourceCoverage",
    "US_POVERTY_NONFILER_TARGET_COVERAGE",
    "coverage_entries",
    "hard_target_package_aliases",
    "source_gap_family_ids",
    "validate_us_poverty_nonfiler_source_coverage",
    "validation_only_family_ids",
]
