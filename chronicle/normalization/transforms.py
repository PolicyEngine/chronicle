"""Lineage-recording transforms for source facts.

These helpers are for low-assumption structural normalization: unit/scale
standardization and same-source arithmetic with explicit lineage. Modeling
choices such as inflation, aging, target reconciliation, or simulator-specific
allocation belong in downstream calibration recipes.
"""

from __future__ import annotations

from typing import Any

from chronicle.facts import DerivationStep, SourceFact


def scale_value(
    fact: SourceFact,
    factor: float,
    *,
    name: str | None = None,
    unit: str | None = None,
    operation: str = "scale_value",
    note: str | None = None,
) -> SourceFact:
    """Scale a published fact value while recording normalization lineage."""
    parameters: dict[str, Any] = {
        "factor": factor,
        "input_unit": fact.unit,
        "output_unit": unit if unit is not None else fact.unit,
    }
    if note:
        parameters["note"] = note

    return fact.with_step(
        DerivationStep(operation=operation, parameters=parameters),
        name=name,
        value=fact.value * factor,
        unit=unit,
    )


def convert_units(
    fact: SourceFact,
    factor: float,
    to_unit: str,
    *,
    name: str | None = None,
    note: str | None = None,
) -> SourceFact:
    """Normalize a published unit or scale with a multiplicative factor."""
    return scale_value(
        fact,
        factor,
        name=name,
        unit=to_unit,
        operation="convert_units",
        note=note,
    )


def apply_share(
    total_fact: SourceFact,
    share: float,
    *,
    name: str,
    share_name: str | None = None,
    unit: str | None = None,
) -> SourceFact:
    """Materialize a same-source total/share relationship.

    Use this only when the source publishes both the total and the share. Do
    not use it for model-driven allocation or target reconciliation.
    """
    return total_fact.with_step(
        DerivationStep(
            operation="apply_share",
            parameters={
                "share": share,
                "share_name": share_name,
                "total_fact": total_fact.name,
            },
        ),
        name=name,
        value=total_fact.value * share,
        unit=unit,
    )


def format_derivation(steps: tuple[DerivationStep, ...]) -> str:
    """Format derivation steps for notes or diagnostics."""
    parts = []
    for step in steps:
        params = ", ".join(f"{key}={value}" for key, value in step.parameters.items())
        parts.append(f"{step.operation}({params})" if params else step.operation)
    return "; ".join(parts)
