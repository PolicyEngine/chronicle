"""IRS Table 4.B uses tax-year workbooks and distinguishes returns from taxpayers."""

from pathlib import Path

import openpyxl
import pytest

from chronicle.source_package import load_source_package
from chronicle.store import fact_to_mapping

W2_DIR = Path(__file__).resolve().parents[1] / "db/data/irs_soi/w2_statistics"
# Column B counts returns, column C counts taxpayers, column D is USD thousands.
MEASURES = (
    ("form_w2_social_security_tip_returns", "B13", "count"),
    ("form_w2_social_security_tip_taxpayers", "C13", "count"),
    ("form_w2_social_security_tip_income", "D13", "usd"),
    ("form_w2_401k_elective_deferrals", "D21", "usd"),
    ("form_w2_designated_roth_401k_contributions", "D40", "usd"),
)


@pytest.mark.parametrize(
    "year, published",
    [
        (2021, (6_149_053, 6_214_583, 39_851_946, 290_307_369, 40_546_442)),
        (2022, (6_649_288, 6_733_323, 51_018_944, 314_371_538, 47_678_686)),
        (2023, (6_801_876, 6_883_254, 51_752_972, 339_406_401, 55_437_008)),
    ],
)
def test_w2_table_4b_values_and_source_year(year, published):
    package = load_source_package("soi-w2-statistics")
    facts = [fact_to_mapping(fact) for fact in package.build_facts(year)]
    indexed = {fact["measure"]["concept"]: fact for fact in facts}
    assert len(facts) == len(indexed) == len(MEASURES)

    filename = f"{year % 100}in04w2all.xlsx"
    workbook = openpyxl.load_workbook(W2_DIR / filename, read_only=True, data_only=True)
    try:
        sheet = workbook["Table 4.B"]
        for (concept, address, unit), source_value in zip(
            MEASURES, published, strict=True
        ):
            fact = indexed[f"irs_soi.{concept}"]
            assert sheet[address].value == source_value
            assert fact["value"] == source_value * (1_000 if unit == "usd" else 1)
            assert fact["measure"]["unit"] == unit
            assert fact["period"] == {"type": "tax_year", "value": year}
            assert fact["source"]["vintage"] == f"tax_year_{year}"
            assert fact["source"]["source_table"] == sheet["A1"].value
            assert fact["source"]["source_file"] == filename
            assert (
                fact["source"]["url"] == f"https://www.irs.gov/pub/irs-soi/{filename}"
            )
    finally:
        workbook.close()


@pytest.mark.parametrize("year", [2020, 2024, 2025])
def test_w2_annual_requires_the_requested_years_own_workbook(year):
    package = load_source_package("soi-w2-statistics")
    with pytest.raises(ValueError, match=f"No source artifact for year {year}"):
        package.build_facts(year)
