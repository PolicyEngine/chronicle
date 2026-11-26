"""Chronicle target source coverage helpers.

Chronicle owns source-backed facts and target source coverage. Consumers such
as Microcosm own selection contracts, decide which rows their support universe
can activate, and calibrate outside Chronicle.
"""

__all__ = [
    "TargetSourceCoverage",
    "US_POVERTY_NONFILER_TARGET_COVERAGE",
    "coverage_entries",
    "hard_target_package_aliases",
    "source_gap_family_ids",
    "validate_us_poverty_nonfiler_source_coverage",
    "validation_only_family_ids",
]


def __getattr__(name: str):
    """Load target source coverage helpers only when explicitly requested."""
    if name not in __all__:
        raise AttributeError(name)
    from chronicle import targets

    return getattr(targets, name)
