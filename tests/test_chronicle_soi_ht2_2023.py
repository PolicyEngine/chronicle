"""IRS SOI Historic Table 2 TY2023 national, state broad and state EITC packages.

Each package mirrors its TY2022 twin and reads ``23in55cmcsv.csv``. That file
inserts two columns at DP (N07262/A07262/N07265/A07265 replace N07260/A07260),
so every column from DP on sits two places right of its TY2022 position. Every
measure therefore names its CSV variable and guards its header.

These tests read the publisher CSV with the standard library, so the values
they check do not depend on Chronicle's own row parser.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest
import yaml
from openpyxl.utils import column_index_from_string

from chronicle.core import validate_facts
from chronicle.source_package import SOURCE_PACKAGE_ALIASES, load_source_package
from chronicle.sources.cells import validate_source_cells
from chronicle.sources.rows import validate_source_rows
from chronicle.suite import build_source_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "db" / "data" / "irs_soi" / "historic_table_2"
CSV_2022 = RAW_DIR / "22in55cmcsv.csv"
CSV_2023 = RAW_DIR / "23in55cmcsv.csv"
CSV_SHA256 = "d1f7c8901fcefb2c46f5dd14f22715b7c8513794ce7b9ea6a6a947f1c548668f"
PACKAGES_ROOT = REPO_ROOT / "packages"

# TY2023 package -> (TY2022 twin, fact count)
PACKAGES = {
    "soi-historic-table-2-2023": ("soi-historic-table-2", 605),
    "soi-historic-table-2-state-broad-2023": (
        "soi-historic-table-2-state-broad-2022",
        2703,
    ),
    "soi-historic-table-2-state-eitc-2023": (
        "soi-historic-table-2-state-eitc-2022",
        510,
    ),
}
NATIONAL = "soi-historic-table-2-2023"
BROAD = "soi-historic-table-2-state-broad-2023"
EITC = "soi-historic-table-2-state-eitc-2023"
STUB_BY_INCOME_RANGE = {
    "all": 0, "under_1": 1, "1_to_10k": 2, "10k_to_25k": 3, "25k_to_50k": 4,
    "50k_to_75k": 5, "75k_to_100k": 6, "100k_to_200k": 7, "200k_to_500k": 8,
    "500k_to_1m": 9, "1m_plus": 10,
}  # fmt: skip
# Census state FIPS codes (50 states and DC), independent of the packages.
STATE_BY_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}  # fmt: skip
# The CSV variable each measure must read, from the IRS documentation guide
# for the TY2023 state data (23incmdocguide.doc; its TY2022 guide agrees).
# This is the semantic check: the per-cell test only proves each fact equals
# the variable its package names.
DOCUMENTED_VARIABLE = {
    "return_count": "N1",
    "tax_filer_individual_count": "N2",
    "adjusted_gross_income": "A00100",
    "income_tax_before_credits_returns": "N05800",
    "income_tax_before_credits_amount": "A05800",
    "premium_tax_credit_returns": "N85770",
    "premium_tax_credit_amount": "A85770",
    "eitc_claims": "N59660",
    "eitc_amount": "A59660",
    "real_estate_taxes_claims": "N18500",
    "real_estate_taxes_amount": "A18500",
    "limited_state_local_taxes_returns": "N18460",
    "limited_state_local_taxes_amount": "A18460",
    "total_income_returns": "N02650",
    "total_income_amount": "A02650",
    "wages_salaries_returns": "N00200",
    "wages_salaries_amount": "A00200",
    "taxable_interest_returns": "N00300",
    "taxable_interest_amount": "A00300",
    "tax_exempt_interest_returns": "N00400",
    "tax_exempt_interest_amount": "A00400",
    "ordinary_dividends_returns": "N00600",
    "ordinary_dividends_amount": "A00600",
    "qualified_dividends_returns": "N00650",
    "qualified_dividends_amount": "A00650",
    "schedule_c_income_returns": "N00900",
    "schedule_c_income_amount": "A00900",
    "net_capital_gains_returns": "N01000",
    "net_capital_gains_amount": "A01000",
    "taxable_ira_distributions_returns": "N01400",
    "taxable_ira_distributions_amount": "A01400",
    "taxable_pension_income_returns": "N01700",
    "taxable_pension_income_amount": "A01700",
    "unemployment_compensation_returns": "N02300",
    "unemployment_compensation_amount": "A02300",
    "taxable_social_security_returns": "N02500",
    "taxable_social_security_amount": "A02500",
    "partnership_scorp_income_returns": "N26270",
    "partnership_scorp_income_amount": "A26270",
    "itemized_deductions_returns": "N04470",
    "itemized_deductions_amount": "A04470",
    "medical_dental_expense_returns": "N17000",
    "medical_dental_expense_amount": "A17000",
    "taxable_income_returns": "N04800",
    "taxable_income_amount": "A04800",
    "income_tax_liability_returns": "N06500",
    "income_tax_liability_amount": "A06500",
    "qbi_claims": "N04475",
    "qbi_amount": "A04475",
    "rental_royalty_income_returns": "N25870",
    "rental_royalty_income_amount": "A25870",
    "ctc_claims": "N07225",
    "ctc_amount": "A07225",
    "actc_claims": "N11070",
    "actc_amount": "A11070",
    "eitc_no_children_claims": "N59661",
    "eitc_no_children_amount": "A59661",
    "eitc_one_child_claims": "N59662",
    "eitc_one_child_amount": "A59662",
    "eitc_two_children_claims": "N59663",
    "eitc_two_children_amount": "A59663",
    "eitc_three_or_more_children_claims": "N59664",
    "eitc_three_or_more_children_amount": "A59664",
}
# TY2022's QBI measures read N03270/A03270, which both guides define as the
# self-employment health insurance deduction; the QBI deduction is
# N04475/A04475. The TY2023 packages read the documented variables.
TY2022_QBI_CORRECTION = {
    "qbi_claims": ("N03270", "N04475"),
    "qbi_amount": ("A03270", "A04475"),
}
# The publisher rounds return counts to tens, so a sum of n count cells can
# miss its published total by up to 5n.
ROUNDING_PER_COUNT_CELL = 5


def _header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return next(csv.reader(handle))


def _publisher_rows() -> dict[tuple[str, int], dict[str, int]]:
    with CSV_2023.open(newline="", encoding="utf-8-sig") as handle:
        return {
            (row["STATE"], int(row["AGI_STUB"])): {
                key: int(value.replace(",", ""))
                for key, value in row.items()
                if key not in {"STATE", "AGI_STUB"}
            }
            for row in csv.DictReader(handle)
        }


def _package_yaml(package_id: str) -> dict:
    path = PACKAGES_ROOT / SOURCE_PACKAGE_ALIASES[package_id] / "source_package.yaml"
    return yaml.safe_load(path.read_text())


def _build(package_id: str, year: int):
    package = load_source_package(package_id)
    rows = package.build_source_rows(year)
    cells = package.build_source_cells(year, source_rows=rows)
    facts = package.build_facts(year, cells=cells, source_rows=rows)
    return rows, cells, facts


@pytest.fixture(scope="module")
def built():
    facts_by_package = {}
    for package_id in PACKAGES:
        rows, cells, facts = _build(package_id, 2023)
        assert validate_source_rows(rows).valid
        assert validate_source_cells(cells).valid
        assert validate_facts(facts).valid
        facts_by_package[package_id] = facts
    return facts_by_package


def _state(fact) -> str:
    if fact.geography.level == "country":
        assert fact.geography.id == "0100000US"
        return "US"
    assert fact.geography.level == "state"
    return STATE_BY_FIPS[fact.geography.id.removeprefix("0400000US")]


def _stub(fact) -> int:
    return STUB_BY_INCOME_RANGE[fact.filters.get("income_range", "all")]


def _scale(fact) -> int:
    return 1000 if fact.measure.unit == "usd" else 1


def test_manifest_registers_the_publisher_file():
    manifest = yaml.safe_load((RAW_DIR / "manifest.yaml").read_text())
    entry = manifest["files"][2023]

    assert hashlib.sha256(CSV_2023.read_bytes()).hexdigest() == CSV_SHA256
    assert entry["filename"] == "23in55cmcsv.csv"
    assert entry["source_url"] == "https://www.irs.gov/pub/irs-soi/23in55cmcsv.csv"
    assert entry["sha256"] == CSV_SHA256
    assert entry["size_bytes"] == CSV_2023.stat().st_size == 757_078


def test_packages_emit_their_fact_counts_and_published_totals(built):
    for package_id, (_, count) in PACKAGES.items():
        assert len(built[package_id]) == count, package_id

    by_id = {fact.source_record_id: fact for fact in built[NATIONAL]}
    prefix = "irs_soi.ty2023.historic_table_2.us.all"
    # The same totals appear in the TY2023 United States workbook 23in54us.xlsx
    # (rows 9, 26 and 138-139), a separate publisher file.
    assert by_id[f"{prefix}.return_count"].value == 159_949_000
    assert by_id[f"{prefix}.adjusted_gross_income"].value == 15_234_086_106_000
    assert by_id[f"{prefix}.eitc_claims"].value == 23_923_110
    assert by_id[f"{prefix}.eitc_amount"].value == 65_006_308_000
    # The qualified business income deduction (N04475/A04475), not the
    # self-employment health insurance deduction TY2022 reads.
    assert by_id[f"{prefix}.qbi_claims"].value == 26_391_030
    assert by_id[f"{prefix}.qbi_amount"].value == 213_733_168_000


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_each_fact_is_exactly_one_publisher_cell(built, package_id):
    """Invariant: value == the named CSV cell x scale, one source row per fact,
    with the fact's geography, stub and variable naming that cell."""
    publisher = _publisher_rows()
    seen = set()
    for fact in built[package_id]:
        state, stub = _state(fact), _stub(fact)
        variable = fact.layout.source_column_id
        assert fact.value == publisher[(state, stub)][variable] * _scale(fact), (
            fact.source_record_id
        )
        assert len(fact.source_row_keys) == 1, fact.source_record_id
        assert fact.source_record_id.startswith("irs_soi.ty2023.historic_table_2.")
        assert fact.period.type == "tax_year"
        assert fact.period.value == 2023
        assert fact.source.source_sha256 == CSV_SHA256
        assert fact.source.vintage == "tax_year_2023"
        if fact.measure.legal_vintage is not None:
            assert fact.measure.legal_vintage == "tax_year_2023"
        seen.add((state, stub, variable))
    assert len(seen) == len(built[package_id])


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_every_measure_column_heads_its_variable(package_id):
    header = _header(CSV_2023)
    spec = _package_yaml(package_id)
    text = (
        PACKAGES_ROOT / SOURCE_PACKAGE_ALIASES[package_id] / "source_package.yaml"
    ).read_text()

    assert "{year}" not in text
    assert "2022" not in text
    for record_set in spec["record_sets"]:
        for measure in record_set["measures"]:
            variable = measure["source_column_id"]
            assert header[column_index_from_string(measure["column"]) - 1] == variable
            assert measure["expected_column_header_row"] == 1
            assert measure["expected_column_header"] == variable


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_every_measure_reads_its_documented_variable(package_id):
    for record_set in _package_yaml(package_id)["record_sets"]:
        for measure in record_set["measures"]:
            assert (
                measure["source_column_id"]
                == DOCUMENTED_VARIABLE[measure["measure_id"]]
            ), (package_id, measure["measure_id"])


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_packages_mirror_their_2022_twins(package_id):
    """Differential: with year labels removed and each column replaced by the
    variable it heads in its own year's file, the TY2023 declarations equal the
    TY2022 ones, apart from the header guards TY2023 adds."""
    twin_id = PACKAGES[package_id][0]
    headers = {2022: _header(CSV_2022), 2023: _header(CSV_2023)}

    def normalised(spec: dict, year: int) -> dict:
        spec = json.loads(json.dumps(spec))
        for key in ("package_id", "label"):
            spec.pop(key)
        for key in ("vintage", "extracted_at", "artifact_year"):
            spec["artifact"].pop(key)
        for record_set in spec["record_sets"]:
            for key in ("record_set_id", "source_record_id_prefix", "period"):
                assert str(year) in str(record_set.pop(key))
            for measure in record_set["measures"]:
                column = measure.pop("column")
                variable = headers[year][column_index_from_string(column) - 1]
                if year == 2022 and measure["measure_id"] in TY2022_QBI_CORRECTION:
                    wrong, right = TY2022_QBI_CORRECTION[measure["measure_id"]]
                    assert variable == wrong
                    variable = right
                measure["variable"] = variable
                measure.pop("legal_vintage", None)
                for key in (
                    "source_column_id",
                    "expected_cell_type",
                    "expected_column_header_row",
                    "expected_column_header",
                ):
                    measure.pop(key, None)
        return spec

    assert normalised(_package_yaml(package_id), 2023) == normalised(
        _package_yaml(twin_id), 2022
    )


@pytest.mark.parametrize("build_year", [2022, 2024])
def test_building_at_another_year_does_not_relabel_the_2023_file(built, build_year):
    """The artifact is pinned and every label is literal, so any build year
    yields the same TY2023 facts."""
    for package_id in PACKAGES:
        _, _, other = _build(package_id, build_year)
        assert sorted((f.source_record_id, f.value, f.period.value) for f in other) == (
            sorted(
                (f.source_record_id, f.value, f.period.value) for f in built[package_id]
            )
        )


def _gap_ok(fact_total: int, published: int, cells: int, unit: str) -> bool:
    if unit == "usd":
        return fact_total == published
    return abs(fact_total - published) <= ROUNDING_PER_COUNT_CELL * cells


def test_national_agi_bands_add_up_to_the_all_returns_row(built):
    """Invariant: per measure, the ten AGI bands sum to the all-returns fact:
    dollars exactly, rounded counts within their rounding."""
    by_measure: dict[str, dict[str, object]] = {}
    for fact in built[NATIONAL]:
        entry = by_measure.setdefault(fact.layout.measure_id, {"bands": 0})
        if _stub(fact) == 0:
            entry["total"] = fact
        else:
            entry["bands"] += fact.value
    assert len(by_measure) == 55
    for measure_id, entry in by_measure.items():
        total = entry["total"]
        assert _gap_ok(entry["bands"], total.value, 11, total.measure.unit), measure_id


def test_state_totals_add_up_to_the_national_total(built):
    """Invariant: for every measure the state broad and state EITC packages
    share with the national package, the 50 states and DC plus the file's two
    non-state rows (OA, PR) sum to the national all-returns fact."""
    publisher = _publisher_rows()
    national = {
        fact.layout.source_column_id: fact
        for fact in built[NATIONAL]
        if _stub(fact) == 0
    }
    for package_id in (BROAD, EITC):
        sums: dict[str, int] = {}
        states: dict[str, set[str]] = {}
        for fact in built[package_id]:
            variable = fact.layout.source_column_id
            sums[variable] = sums.get(variable, 0) + fact.value
            states.setdefault(variable, set()).add(_state(fact))
        shared = set(sums) & set(national)
        assert shared, package_id
        for variable in shared:
            assert len(states[variable]) == 51
            total = national[variable]
            scale = _scale(total)
            other = sum(publisher[(row, 0)][variable] * scale for row in ("OA", "PR"))
            assert _gap_ok(
                sums[variable] + other, total.value, 54, total.measure.unit
            ), (package_id, variable)


def test_eitc_child_counts_add_up_to_each_states_eitc_total(built):
    """Invariant: no, one, two and three-or-more qualifying children partition
    each state's EITC returns and amount. Each of the five cells is rounded
    separately; the published file's largest gap is 20 returns and $4,000."""
    by_state: dict[tuple[str, str], dict[str, int]] = {}
    for fact in built[EITC]:
        variable = fact.layout.source_column_id
        kind = variable[0]  # N = returns, A = amount
        entry = by_state.setdefault((_state(fact), kind), {})
        entry[variable[1:]] = fact.value
    assert len(by_state) == 51 * 2
    for (state, kind), values in by_state.items():
        children = sum(values[f"5966{k}"] for k in (1, 2, 3, 4))
        tolerance = 25 if kind == "N" else 5_000
        assert abs(children - values["59660"]) <= tolerance, (state, kind)


@pytest.mark.parametrize("package_id", sorted(PACKAGES))
def test_source_suite_passes_agent_acceptance(package_id, tmp_path):
    suite = build_source_suite(package_id, tmp_path / package_id, year=2023)

    assert suite.agent_acceptance.valid
    assert suite.agent_acceptance.counts["row_semantic_error_count"] == 0
