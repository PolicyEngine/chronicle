"""Tests for Microplex PolicyEngine-US tax adapters."""

from __future__ import annotations

import sys
import types

import numpy as np
import pandas as pd

from micro.us.policyengine import (
    DEFAULT_SOI_INCOME_TAX_VARIABLE,
    PolicyEngineNotAvailableError,
    PolicyEngineTaxConfig,
    add_policyengine_income_tax,
    add_policyengine_income_tax_from_persons,
)


class FakeSimulation:
    """Small stand-in for policyengine_us.Simulation."""

    calls: list[tuple[dict, str, str | None]] = []

    def __init__(self, *, situation):
        self.situation = situation

    def calculate(self, variable, period=None):
        self.calls.append((self.situation, variable, period))
        values = []
        for tax_unit in self.situation["tax_units"].values():
            wages = 0.0
            self_employment = 0.0
            for member in tax_unit["members"]:
                person = self.situation["people"][member]
                wages += person["employment_income"][period]
                self_employment += person["self_employment_income"][period]
            values.append(wages * 0.10 + self_employment * 0.15)
        return np.array(values)


def install_fake_policyengine(monkeypatch):
    FakeSimulation.calls = []
    fake_module = types.ModuleType("policyengine_us")
    fake_module.Simulation = FakeSimulation
    monkeypatch.setitem(sys.modules, "policyengine_us", fake_module)


def test_add_policyengine_income_tax_uses_soi_comparable_variable(monkeypatch):
    install_fake_policyengine(monkeypatch)
    tax_units = pd.DataFrame(
        {
            "wage_income": [50_000.0, 0.0],
            "self_employment_income": [0.0, 20_000.0],
            "interest_income": [100.0, 0.0],
            "state_fips": [6, 48],
            "age": [35, 55],
        }
    )

    result = add_policyengine_income_tax(tax_units, year=2024, config=None)

    assert result["income_tax_liability"].tolist() == [5_000.0, 3_000.0]
    assert result["income_tax_liability_source"].unique().tolist() == [
        f"policyengine_us:{DEFAULT_SOI_INCOME_TAX_VARIABLE}"
    ]
    _, variable, period = FakeSimulation.calls[0]
    assert variable == "income_tax_before_credits"
    assert period == "2024"


def test_add_policyengine_income_tax_batches(monkeypatch):
    install_fake_policyengine(monkeypatch)
    tax_units = pd.DataFrame(
        {
            "wage_income": [10_000.0, 20_000.0, 30_000.0],
            "self_employment_income": [0.0, 0.0, 0.0],
        }
    )

    result = add_policyengine_income_tax(
        tax_units,
        year=2024,
        config=PolicyEngineTaxConfig(batch_size=2),
    )

    assert result["income_tax_liability"].tolist() == [1_000.0, 2_000.0, 3_000.0]
    assert len(FakeSimulation.calls) == 2


def test_add_policyengine_income_tax_from_persons_preserves_entities(monkeypatch):
    install_fake_policyengine(monkeypatch)
    persons = pd.DataFrame(
        {
            "household_id": [1, 1, 1, 2],
            "tax_unit_id": [10, 10, 11, 20],
            "spm_unit_id": [100, 100, 101, 200],
            "person_seq": [1, 2, 3, 1],
            "age": [40, 38, 16, 55],
            "state_fips": [6, 6, 6, 48],
            "weight": [100.0, 100.0, 100.0, 200.0],
            "wage_salary_income": [50_000.0, 20_000.0, 0.0, 0.0],
            "self_employment_income": [0.0, 0.0, 0.0, 20_000.0],
            "total_person_income": [50_000.0, 20_000.0, 0.0, 20_000.0],
        }
    )

    result = add_policyengine_income_tax_from_persons(persons, year=2024)

    assert result["tax_unit_id"].tolist() == [10, 11, 20]
    assert result["person_count"].tolist() == [2, 1, 1]
    assert result["income_tax_liability"].tolist() == [7_000.0, 0.0, 3_000.0]
    situation, variable, period = FakeSimulation.calls[0]
    assert variable == "income_tax_before_credits"
    assert period == "2024"
    assert [len(unit["members"]) for unit in situation["tax_units"].values()] == [
        2,
        1,
        1,
    ]
    assert [len(unit["members"]) for unit in situation["households"].values()] == [
        3,
        1,
    ]


def test_policyengine_missing_raises_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "policyengine_us", None)

    try:
        add_policyengine_income_tax(pd.DataFrame({"wage_income": [1.0]}), year=2024)
    except PolicyEngineNotAvailableError as exc:
        assert "PolicyEngine-US is required" in str(exc)
    else:
        raise AssertionError("Expected PolicyEngineNotAvailableError")
