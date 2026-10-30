"""Generate the source packages for PolicyEngine/chronicle#395.

Run from the repository root:

    uv run python scripts/build_uk_395_packages.py

``--check`` compares the generated YAML with the committed files instead of writing.
Each package is written from its pinned artifact, read with Chronicle's own parsers, so
every row number, column and guard cell below is one the package parser sees.

- ``lps-domestic-rates-paid-2026``: Land & Property Services' domestic rates paid and
  paying occupancies by district council, rating years 2020-21 to 2025-26 (item 1).
- ``lps-lone-pensioner-allowance-ye-2024`` and ``lps-disabled-persons-allowance-ye-2024``:
  LPS's statistics of the two domestic reliefs, awards and net amounts by council,
  2009-10 to 2023-24 (item 1).
- ``ons-crpsf-ni-domestic-rates-fye2025``: ONS country and regional public sector
  finances, Northern Ireland's regional and district domestic rates, 1999-00 to 2024-25
  (item 1).
- ``dft-bus01-wales-journeys-2025``: DfT BUS01a passenger journeys and BUS01c
  concessionary journeys for Wales, from the workbook dft-bus01-passenger-journeys-2025
  already pins (item 2).
- ``welshgov-childcare-offer-report-2023-24``: the Childcare Offer for Wales report's
  Table 4, take-up in 2023-24 with its numerator and denominator (item 3).
- ``ons-pusf-vehicle-duty-{households,businesses}-october-2026``: ONS series CDDZ and
  EKED, vehicle duty paid by households and by businesses (the VED comment).
- ``ons-mm23-cpi-weight-*`` and ``ons-mm23-cpi-index-*``: ONS CPI weights for COICOP
  04.5.2 and its two classes, and the two classes' indices (the bottled gas comment).

The OBR's vehicle excise duties line is added to the March 2026 receipts package by
scripts/build_uk_excise_packages.py and carried to October by
scripts/build_obr_efo_october_2026.py.
"""

from __future__ import annotations

import argparse
import textwrap
from dataclasses import dataclass
from pathlib import Path

import yaml
from openpyxl.utils import get_column_letter

from chronicle.sources.cells import (
    SourceArtifactMetadata,
    source_cells_from_ods,
    source_cells_from_pdf_text_numbers,
    source_cells_from_xlsx,
)
from chronicle.sources.rows import (
    source_cells_from_source_rows,
    source_rows_from_delimited_text,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-10-30"
ISSUE = "PolicyEngine/chronicle#395"

NORTHERN_IRELAND = {
    "geography_id": "N92000002",
    "geography_level": "country",
    "geography_name": "Northern Ireland",
    "geography_vintage": "current",
}
WALES = {
    "geography_id": "W92000004",
    "geography_level": "country",
    "geography_name": "Wales",
    "geography_vintage": "current",
}
UNITED_KINGDOM = {
    "geography_id": "K02000001",
    "geography_level": "country",
    "geography_name": "United Kingdom",
    "geography_vintage": "current",
}
# Local government districts (2014), as the other NI district packages code them.
NI_COUNCILS = {
    "Antrim and Newtownabbey": "N09000001",
    "Armagh City, Banbridge and Craigavon": "N09000002",
    "Belfast": "N09000003",
    "Causeway Coast and Glens": "N09000004",
    "Derry City and Strabane": "N09000005",
    "Fermanagh and Omagh": "N09000006",
    "Lisburn and Castlereagh": "N09000007",
    "Mid and East Antrim": "N09000008",
    "Mid Ulster": "N09000009",
    "Newry, Mourne and Down": "N09000010",
    "Ards and North Down": "N09000011",
}


# Labels of the constraints that pair with a record set's shared filters; the England
# BUS01 package labels journey_category the same way.
FILTER_LABELS = {
    "journey_category": "Journey Category",
    "lpa_tenure": "Lone Pensioner Allowance tenure",
}


class PackageDumper(yaml.SafeDumper):
    """Plain YAML with no anchors, so every record set reads on its own."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def render(header: str, payload: dict) -> str:
    """The header's paragraphs, rewrapped as comment lines, then the package."""
    lines: list[str] = []
    for paragraph in textwrap.dedent(header).strip().split("\n\n"):
        if lines:
            lines.append("")
        lines += textwrap.wrap(" ".join(paragraph.split()), width=88)
    comment = "".join(f"# {line}".rstrip() + "\n" for line in lines)
    return comment + yaml.dump(
        payload, Dumper=PackageDumper, sort_keys=False, allow_unicode=True, width=100
    )


def metadata(filename: str) -> SourceArtifactMetadata:
    return SourceArtifactMetadata(
        source_name="",
        source_table="",
        source_file=filename,
        url=None,
        vintage="",
        sha256="",
        size_bytes=0,
        extracted_at="",
        extraction_method="",
    )


def manifest_file(directory: str) -> tuple[str, Path]:
    manifest = yaml.safe_load((DATA / directory / "manifest.yaml").read_text())
    (entry,) = manifest["files"].values()
    return entry["filename"], DATA / directory / entry["filename"]


def grid_of(cells) -> dict[tuple[str, int, str], object]:
    """Index parsed cells by (sheet, row, column letter)."""
    return {
        (cell.sheet_name, cell.row_number, get_column_letter(cell.column_number)): (
            cell.raw_value
        )
        for cell in cells
    }


def csv_grid(directory: str) -> tuple[str, dict[tuple[int, str], object]]:
    filename, path = manifest_file(directory)
    sheet = Path(filename).stem
    rows = source_rows_from_delimited_text(
        path.read_bytes(), metadata(filename), sheet_name=sheet
    )
    cells = source_cells_from_source_rows(rows, selected_rows=())
    return sheet, {
        (row, column): value for (_s, row, column), value in grid_of(cells).items()
    }


def artifact(
    source_name: str,
    source_table: str,
    directory: str,
    vintage: str,
    parser: str,
    extraction_method: str,
    artifact_year: int,
    **extra: object,
) -> dict:
    block = {
        "source_name": source_name,
        "source_table": source_table,
        "resource_package": "db",
        "resource_directory": f"data/{directory}",
        "manifest": "manifest.yaml",
        "vintage": vintage,
        "extracted_at": EXTRACTED_AT,
        "extraction_method": extraction_method,
        "parser": parser,
        "artifact_year": artifact_year,
    }
    block.update(extra)
    return block


def record_set(
    record_set_id: str,
    *,
    provenance_class: str,
    sheet_name: str,
    period_type: str,
    period: int | str,
    geography: dict,
    entity: str,
    entity_role: str,
    domain: str,
    groupby_dimension: str,
    rows: list[dict],
    measures: list[dict],
    period_coverage: dict | None = None,
    survey_instrument: str | None = None,
    shared_filters: dict | None = None,
) -> dict:
    record = {"record_set_id": record_set_id, "provenance_class": provenance_class}
    if survey_instrument is not None:
        record["survey_instrument"] = survey_instrument
    record.update(
        {
            "assertion": "observation",
            "record_set_spec_id": f"{record_set_id}.v1",
            "source_record_id_prefix": record_set_id,
            "sheet_name": sheet_name,
            "period_type": period_type,
            "period": period,
        }
    )
    if period_coverage is not None:
        record["period_coverage"] = period_coverage
    record.update(geography)
    record.update(
        {
            "entity": entity,
            "entity_role": entity_role,
            "domain": domain,
            "groupby_dimension": groupby_dimension,
        }
    )
    if shared_filters:
        record["shared_filters"] = dict(shared_filters)
        record["shared_constraints"] = [
            {
                "variable": key,
                "operator": "==",
                "value": value,
                "label": FILTER_LABELS[key],
            }
            for key, value in shared_filters.items()
        ]
    record["rows"] = rows
    record["measures"] = measures
    return record


def measure(
    measure_id: str,
    label: str,
    column: str,
    *,
    concept: str,
    source_concept: str,
    authority: str,
    evidence_url: str,
    notes: str,
    unit: str,
    aggregation: str,
    value_scale: int | None = None,
    header: object = None,
    header_row: int = 1,
) -> dict:
    spec = {
        "measure_id": measure_id,
        "label": label,
        "ordinal": 0,
        "column": column,
        "source_column_id": measure_id,
    }
    if header is not None:
        spec["expected_column_header_row"] = header_row
        spec["expected_column_header"] = header
    spec.update(
        {
            "concept": concept,
            "source_concept": source_concept,
            "concept_relation": "source_label",
            "concept_authority": authority,
            "concept_evidence_url": evidence_url,
            "concept_evidence_notes": notes,
            "unit": unit,
            "aggregation": aggregation,
        }
    )
    if value_scale is not None:
        spec["value_scale"] = value_scale
    spec["expected_cell_type"] = "number"
    return spec


def fiscal_coverage(opening: int, label: str) -> dict:
    return {
        "start_date": f"{opening}-04-01",
        "end_date": f"{opening + 1}-03-31",
        "basis": "fiscal",
        "source_period_label": label,
    }


def slug(text: str) -> str:
    return (
        "".join(c if c.isalnum() else "_" for c in text.lower())
        .strip("_")
        .replace("__", "_")
    )


def write(directory: str, text: str) -> None:
    path = PACKAGES / directory / "source_package.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ------------------------------------------------------------- 1. LPS rates paid

LPS_DIRECTORY = "lps/domestic_rates_paid_2026"
LPS_URL = (
    "https://www.data.gov.uk/dataset/30535a44-0a05-4bff-98cf-001301a6b4d6/"
    "rates-paid-by-district-council-and-sector"
)
LPS_NOTES = (
    "LPS, Rates paid by District Council and Sector (OpenDataNI): 'amounts of rates paid "
    "against ratepayer accounts as at 31st March each year, as recorded on the Land & "
    "Property (LPS) rating system'; the number of occupancies ('a liable person, persons, "
    "business or organisation at a property at a given time') 'that made a payment (value "
    "greater than £0) within the rating year', including occupancies paid in full and "
    "those with a balance left at the end of the year. 'The totals included in the tables "
    "are not adjusted for receipts at year end which have been paid by ratepayers, but "
    "not yet allocated to a particular rate account.'"
)
LPS_HEADER = f"""
Land & Property Services, 'Rates paid by District Council and Sector' (OpenDataNI,
resources updated 8 May 2026), its 'Domestic Rates collected by District Council' CSV,
for {ISSUE} item 1. Written by scripts/build_uk_395_packages.py.

Domestic rates paid against ratepayer accounts as at 31 March of each rating year, and
the number of domestic occupancies that made a payment within the rating year, for the
11 district councils and Northern Ireland, rating years 2020-21 to 2025-26. A domestic
bill is the regional and the district rate together, levied as one bill, less the
reliefs applied to it. The CSV publishes the amount paid, not the amount levied; it
gives no relief as a separate figure and does not say whether credits such as rate
rebate count as payments. The CSV prints amounts as '£' text
with thousands separators and counts with separators (the 2025-26 counts with a trailing
space); the delimited parser reads both as numbers. Each rating year is a fiscal-year
period (April to March), stamped by its opening year.
"""


def council_row(name: str, row: int, ordinal: int) -> dict:
    """A district council's row, or Northern Ireland's, with its geography."""
    if name == "Northern Ireland":
        geography = dict(NORTHERN_IRELAND)
    else:
        geography = {
            "geography_id": NI_COUNCILS[name],
            "geography_level": "local_authority",
            "geography_name": name,
            "geography_vintage": "lgd_2014",
        }
    return {
        "value_id": slug(name),
        "label": name,
        "ordinal": ordinal,
        "row_number": row,
        "expected_row_header_column": "A",
        "expected_row_header": name,
        **geography,
        "table_record_kind": "total",
    }


def check_council_rows(rows: list[dict]) -> None:
    assert [row["label"] for row in rows][-1] == "Northern Ireland"
    assert sorted(row["label"] for row in rows[:-1]) == sorted(NI_COUNCILS)


def build_lps() -> str:
    sheet, grid = csv_grid(LPS_DIRECTORY)
    headers = {grid[(1, column)]: column for (row, column) in grid if row == 1}
    assert grid[(1, "A")] == "District Council"
    data_rows = sorted({row for (row, column) in grid if row > 1})
    rows = [
        council_row(grid[(row, "A")], row, ordinal)
        for ordinal, row in enumerate(data_rows)
    ]
    check_council_rows(rows)
    record_sets = []
    for opening in range(2020, 2026):
        label = f"{opening}-{(opening + 1) % 100:02d}"
        count_header = f"Number of Domestic occupancies with a rates payment made in {label} rating year"
        paid_header = f"Domestic Rates paid as at 31st March {opening + 1}"
        count_column, paid_column = headers[count_header], headers[paid_header]
        measures = [
            measure(
                "occupancies_with_payment",
                f"Domestic occupancies with a rates payment made in the {label} rating year",
                count_column,
                concept="lps.domestic_occupancies_with_rates_payment",
                source_concept="lps.domestic_occupancies_with_rates_payment",
                authority="lps",
                evidence_url=LPS_URL,
                notes=LPS_NOTES,
                unit="count",
                aggregation="sum",
                header=count_header,
            ),
            measure(
                "domestic_rates_paid",
                f"Domestic rates paid as at 31 March {opening + 1}",
                paid_column,
                concept="lps.domestic_rates_paid",
                source_concept="lps.domestic_rates_paid",
                authority="lps",
                evidence_url=LPS_URL,
                notes=LPS_NOTES,
                unit="gbp",
                aggregation="sum",
                header=paid_header,
            ),
        ]
        measures[1]["ordinal"] = 1
        record_sets.append(
            record_set(
                f"lps.domestic_rates_paid_2026.fy{opening}",
                provenance_class="administrative",
                sheet_name=sheet,
                period_type="fiscal_year",
                period=opening,
                period_coverage=fiscal_coverage(opening, f"{label} rating year"),
                geography=NORTHERN_IRELAND,
                entity="household",
                entity_role="domestic_ratepayer_occupancy",
                domain="domestic_rates",
                groupby_dimension="lps.district_council",
                rows=rows,
                measures=measures,
            )
        )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "lps-domestic-rates-paid-2026",
        "label": "LPS domestic rates paid and paying domestic occupancies by district "
        "council, rating years 2020-21 to 2025-26",
        "dimension_labels": {"lps.district_council": "District Council"},
        "artifact": artifact(
            "lps",
            "Rates paid by District Council and Sector: Domestic Rates collected by "
            "District Council",
            LPS_DIRECTORY,
            "opendatani_2026_05_08",
            "delimited_text_full_rows",
            "delimited text full-row parse of the publisher CSV",
            2026,
        ),
        "record_sets": record_sets,
    }
    return render(LPS_HEADER, payload)


# ------------------------------------- 1b. LPS's Lone Pensioner and Disabled Person's Allowances

ALLOWANCES_URL = (
    "https://www.finance-ni.gov.uk/publications/"
    "lone-pensioner-and-disabled-person-allowance-statistics"
)
LPA_DIRECTORY = "lps/lone_pensioner_allowance_ye_2024"
DPA_DIRECTORY = "lps/disabled_persons_allowance_ye_2024"
LPA_SHEETS = ("Table 1.1", "Table 1.2 ", "Table 1.3", "Table 1.4", "Table 1.5")
DPA_SHEETS = ("Table 1.1", "Table 1.2", "Table 1.3")
# Table 1.5's columns beyond owner occupiers (column B, Table 1.2's Northern Ireland row).
LPA_TENURES = (
    (
        "C",
        "Net Amount of LPA awarded (Private Rented Sector)",
        "private_rented_sector",
        "Private Rented Sector",
    ),
    ("D", "Net Amount of LPA awarded (NIHE)", "nihe", "NIHE"),
    (
        "E",
        "Net Amount of LPA awarded (Housing Association)",
        "housing_association",
        "Housing Association",
    ),
    ("F", "Total Net amount of LPA awarded in Northern Ireland", "all", "All tenures"),
)
LPA_COUNT_NOTES = (
    "LPS, Lone Pensioner Allowance statistics to year end 2024 (29 May 2024), Table 1.1: "
    "'The number of people are those that have a current award for Lone Pensioner "
    "Allowance at year end.' 'Nil awards have been included in the number of people "
    "awarded Lone Pensioner Allowance.' Owner occupiers: LPS processes their applications "
    "and NIHE those of ratepayers who rent."
)
LPA_AMOUNT_NOTES = (
    "LPS, Lone Pensioner Allowance statistics to year end 2024 (29 May 2024), Tables 1.2 "
    "and 1.5: 'The Net Amount of Lone Pensioner Allowance is the amount payable for all "
    "persons that have an entitlement to Lone Pensioner Allowance over the course of the "
    "financial year.' 'The Net Amount of LPA Awarded by NIHE are for invoiced amounts that "
    "have been posted to the LPS system during the financial year.'"
)
DPA_COUNT_NOTES = (
    "LPS, Disabled Person's Allowance statistics to year end 2024 (29 May 2024), Table "
    "1.1: 'The number of properties are those that have a current award for Disabled "
    "Person's Allowance at year-end.' The statistics count properties, not people, as more "
    "than one disabled person could live in a property."
)
DPA_AMOUNT_NOTES = (
    "LPS, Disabled Person's Allowance statistics to year end 2024 (29 May 2024), Table "
    "1.2: 'The Net Amount of Disabled Person's Allowance is the amount awarded for all "
    "properties that have an entitlement to Disabled Person's Allowance over the course of "
    "the financial year.'"
)
LPA_HEADER = f"""
Land & Property Services, Lone Pensioner Allowance statistics to year end 2024 (published
29 May 2024), for {ISSUE} item 1. Written by scripts/build_uk_395_packages.py.

Lone Pensioner Allowance is a 20% reduction in the rates of ratepayers aged 70 or over
who live alone. LPS processes owner occupiers' applications and NIHE those of
ratepayers who rent. Table 1.1: owner occupiers with a current award at year-end 31
March 2010 to 2024, nil awards included. Table 1.2: the net amount payable to owner
occupiers over each financial year. Both are by district council, under today's council
names for every year as the notes say, and for Northern Ireland. Table 1.5: Northern
Ireland's net amounts for the private rented sector, NIHE and housing association
tenants, and for all tenures.

Every amount shares one concept and carries its tenure as lpa_tenure. Table 1.5's
owner-occupier column restates Table 1.2's Northern Ireland row, Table 1.3 restates the
Northern Ireland rows of Tables 1.1 and 1.2, and Table 1.4 restates Table 1.5's renting
columns: none is ported again, and the build asserts each copy equal. Counts are stamped
by the calendar year of the 31 March they are current on, and amounts by the financial
year's opening year. No 2024-25 edition is published yet.
"""
DPA_HEADER = f"""
Land & Property Services, Disabled Person's Allowance statistics to year end 2024
(published 29 May 2024), for {ISSUE} item 1. Written by scripts/build_uk_395_packages.py.

Disabled Person's Allowance is a 25% reduction in rates, not means tested, where a
person with a disability lives in a property adapted for their needs. Table 1.1:
properties with a current award at year-end 31 March 2010 to 2024. Table 1.2: the net
amount awarded over each financial year. Both are by district council, under today's
council names for every year as the notes say, and for Northern Ireland.

Table 1.3 restates the Northern Ireland rows of Tables 1.1 and 1.2: it is not ported
again, and the build asserts it equal. Counts are stamped by the calendar year of the
31 March they are current on, and amounts by the financial year's opening year. No
2024-25 edition is published yet.
"""


def xlsx_grid(
    directory: str, sheets: tuple[str, ...]
) -> dict[tuple[str, int, str], object]:
    filename, path = manifest_file(directory)
    cells = source_cells_from_xlsx(path.read_bytes(), metadata(filename), sheets=sheets)
    return grid_of(cells)


def year_end(text: object) -> int:
    """A year-end header such as '2024-03-31T00:00:00', as its calendar year."""
    assert isinstance(text, str) and text.endswith("-03-31T00:00:00"), text
    return int(text[:4])


def year_end_period(year: int, kind: str) -> dict:
    """Counts are awards current on 31 March, stamped by that calendar year. Amounts are
    payable over the financial year that ends then, stamped by its opening year."""
    if kind == "count":
        return {
            "period_type": "calendar_year",
            "period": year,
            "period_coverage": {
                "start_date": f"{year}-03-31",
                "end_date": f"{year}-03-31",
                "basis": "calendar",
                "source_period_label": f"current awards at year-end 31 March {year}",
            },
        }
    return {
        "period_type": "fiscal_year",
        "period": year - 1,
        "period_coverage": fiscal_coverage(
            year - 1, f"{year - 1}-{year % 100:02d}, year-end 31 March {year}"
        ),
    }


def council_table(grid: dict, sheet: str) -> tuple[int, list[dict], dict[int, str]]:
    """A council-by-year table's header row, its rows and its year-end columns."""
    (header_row,) = [
        row
        for (name, row, column), value in grid.items()
        if name == sheet and column == "A" and value == "District Council"
    ]
    found = sorted(
        (row, value)
        for (name, row, column), value in grid.items()
        if name == sheet
        and column == "A"
        and row > header_row
        and value in {*NI_COUNCILS, "Northern Ireland"}
    )
    rows = [
        council_row(label, row, ordinal) for ordinal, (row, label) in enumerate(found)
    ]
    check_council_rows(rows)
    rows[-1]["guard_cells"] = [
        {
            "column": "A",
            "row": 1,
            "expected_value": grid[(sheet, 1, "A")],
            "label": "table title",
        }
    ]
    years = {}
    for index in range(2, 17):
        column = get_column_letter(index)
        years[year_end(grid[(sheet, header_row, column)])] = column
    assert sorted(years) == list(range(2010, 2025)), sorted(years)
    return header_row, rows, years


def council_record_sets(
    grid: dict,
    sheet: str,
    *,
    prefix: str,
    kind: str,
    measure_id: str,
    measure_label: str,
    concept: str,
    unit: str,
    entity: str,
    entity_role: str,
    notes: str,
    shared_filters: dict | None = None,
) -> list[dict]:
    header_row, rows, years = council_table(grid, sheet)
    record_sets = []
    for year, column in years.items():
        period = year_end_period(year, kind)
        stamp = "cy" if kind == "count" else "fy"
        record_sets.append(
            record_set(
                f"{prefix}.{stamp}{period['period']}",
                provenance_class="administrative",
                sheet_name=sheet,
                **period,
                geography=NORTHERN_IRELAND,
                entity=entity,
                entity_role=entity_role,
                domain="domestic_rates",
                groupby_dimension="lps.district_council",
                shared_filters=shared_filters,
                rows=rows,
                measures=[
                    measure(
                        measure_id,
                        f"{measure_label}, year-end 31 March {year}",
                        column,
                        concept=concept,
                        source_concept=concept,
                        authority="lps",
                        evidence_url=ALLOWANCES_URL,
                        notes=notes,
                        unit=unit,
                        aggregation="sum",
                        header=grid[(sheet, header_row, column)],
                        header_row=header_row,
                    )
                ],
            )
        )
    return record_sets


def northern_ireland_cells(grid: dict, sheet: str) -> dict[int, object]:
    """A council table's Northern Ireland row, by year end."""
    header_row, rows, years = council_table(grid, sheet)
    row = rows[-1]["row_number"]
    return {year: grid[(sheet, row, column)] for year, column in years.items()}


def restates(copy: object, value: object) -> bool:
    """A restated cell equals its source, up to the float noise between two cells that
    print the same pennies (DPA's 2017-18 amount is 3374738.57 in one table and
    3374738.5700000003 in the other)."""
    return abs(float(copy) - float(value)) < 1e-4


def year_rows(grid: dict, sheet: str) -> dict[int, int]:
    """A Northern Ireland table's year-end rows (rows 6 to 20)."""
    assert grid[(sheet, 5, "A")] == "Year-end"
    rows = {year_end(grid[(sheet, row, "A")]): row for row in range(6, 21)}
    assert sorted(rows) == list(range(2010, 2025)), sorted(rows)
    return rows


def allowance_payload(
    package_id: str, label: str, directory: str, table: str, sheets: list[str]
) -> dict:
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": package_id,
        "label": label,
        "dimension_labels": {"lps.district_council": "District Council"},
    }
    if package_id.startswith("lps-lone-pensioner"):
        payload["dimension_labels"]["lpa_tenure"] = FILTER_LABELS["lpa_tenure"]
        payload["dimension_value_labels"] = {
            "lpa_tenure": {
                "owner_occupier": "Owner occupier",
                **{value: text for _c, _h, value, text in LPA_TENURES},
            }
        }
    payload["artifact"] = artifact(
        "lps",
        table,
        directory,
        "lps_allowance_statistics_2024_05_29",
        "xlsx_used_range",
        "xlsx used-range cell parse of the declared tables",
        2024,
        sheets=sheets,
    )
    return payload


def build_lpa() -> str:
    grid = xlsx_grid(LPA_DIRECTORY, LPA_SHEETS)
    assert str(grid[("Table 1.1", 1, "A")]).startswith(
        "Table 1.1  Number of people1,2 (owner occupier)"
    )
    assert str(grid[("Table 1.2 ", 1, "A")]).startswith(
        "Table 1.2  Net Amount1 of Lone Pensioner Allowance (owner occupier)"
    )
    people = northern_ireland_cells(grid, "Table 1.1")
    owners = northern_ireland_cells(grid, "Table 1.2 ")
    totals = year_rows(grid, "Table 1.5")
    # The tables that restate rows ported here, each asserted equal to its copy.
    for year, row in year_rows(grid, "Table 1.3").items():
        assert restates(grid[("Table 1.3", row, "B")], people[year]), year
        assert restates(grid[("Table 1.3", row, "C")], owners[year]), year
    for year, row in year_rows(grid, "Table 1.4").items():
        for source, copy in (("B", "C"), ("C", "D"), ("D", "E")):
            assert restates(
                grid[("Table 1.4", row, source)],
                grid[("Table 1.5", totals[year], copy)],
            ), year
    for year, row in totals.items():
        assert restates(grid[("Table 1.5", row, "B")], owners[year]), year
    owner = {"lpa_tenure": "owner_occupier"}
    record_sets = council_record_sets(
        grid,
        "Table 1.1",
        prefix="lps.lpa_ye_2024.table_1_1",
        kind="count",
        measure_id="people_awarded",
        measure_label="Owner occupiers with a current Lone Pensioner Allowance award",
        concept="lps.lone_pensioner_allowance_recipients",
        unit="count",
        entity="person",
        entity_role="lone_pensioner_allowance_recipient",
        notes=LPA_COUNT_NOTES,
        shared_filters=owner,
    )
    record_sets += council_record_sets(
        grid,
        "Table 1.2 ",
        prefix="lps.lpa_ye_2024.table_1_2",
        kind="amount",
        measure_id="net_amount",
        measure_label="Net amount of Lone Pensioner Allowance awarded to owner occupiers",
        concept="lps.lone_pensioner_allowance_net_amount",
        unit="gbp",
        entity="person",
        entity_role="lone_pensioner_allowance_recipient",
        notes=LPA_AMOUNT_NOTES,
        shared_filters=owner,
    )
    title = grid[("Table 1.5", 1, "A")]
    assert str(title).startswith(
        "Table 1.5  Total Net Amount1,2 of Lone Pensioner Allowance"
    )
    for year, row in totals.items():
        period = year_end_period(year, "amount")
        for column, header, tenure, _text in LPA_TENURES:
            assert grid[("Table 1.5", 5, column)] == header
            record_sets.append(
                record_set(
                    f"lps.lpa_ye_2024.table_1_5.{tenure}.fy{period['period']}",
                    provenance_class="administrative",
                    sheet_name="Table 1.5",
                    **period,
                    geography=NORTHERN_IRELAND,
                    entity="person",
                    entity_role="lone_pensioner_allowance_recipient",
                    domain="domestic_rates",
                    groupby_dimension="lps.district_council",
                    shared_filters={"lpa_tenure": tenure},
                    rows=[
                        {
                            "value_id": "northern_ireland",
                            "label": "Northern Ireland",
                            "ordinal": 0,
                            "row_number": row,
                            "expected_row_header_column": "A",
                            "expected_row_header": grid[("Table 1.5", row, "A")],
                            **NORTHERN_IRELAND,
                            "table_record_kind": "total",
                            "guard_cells": [
                                {
                                    "column": "A",
                                    "row": 1,
                                    "expected_value": title,
                                    "label": "table title",
                                }
                            ],
                        }
                    ],
                    measures=[
                        measure(
                            "net_amount",
                            f"{header}, year-end 31 March {year}",
                            column,
                            concept="lps.lone_pensioner_allowance_net_amount",
                            source_concept="lps.lone_pensioner_allowance_net_amount",
                            authority="lps",
                            evidence_url=ALLOWANCES_URL,
                            notes=LPA_AMOUNT_NOTES,
                            unit="gbp",
                            aggregation="sum",
                            header=header,
                            header_row=5,
                        )
                    ],
                )
            )
    payload = allowance_payload(
        "lps-lone-pensioner-allowance-ye-2024",
        "LPS Lone Pensioner Allowance: owner occupiers awarded and net amounts by district "
        "council, and Northern Ireland's net amounts by tenure, 2009-10 to 2023-24",
        LPA_DIRECTORY,
        "Lone Pensioner Allowance statistics to year end 2024, Tables 1.1, 1.2 and 1.5",
        ["Table 1.1", "Table 1.2 ", "Table 1.5"],
    )
    payload["record_sets"] = record_sets
    return render(LPA_HEADER, payload)


def build_dpa() -> str:
    grid = xlsx_grid(DPA_DIRECTORY, DPA_SHEETS)
    assert str(grid[("Table 1.1", 1, "A")]).startswith(
        "Table 1.1  Number of Properties1"
    )
    assert str(grid[("Table 1.2", 1, "A")]).startswith(
        "Table 1.2  Net Amount1 of Disabled Person's Allowance"
    )
    properties = northern_ireland_cells(grid, "Table 1.1")
    amounts = northern_ireland_cells(grid, "Table 1.2")
    for year, row in year_rows(grid, "Table 1.3").items():
        assert restates(grid[("Table 1.3", row, "B")], properties[year]), year
        assert restates(grid[("Table 1.3", row, "C")], amounts[year]), year
    record_sets = council_record_sets(
        grid,
        "Table 1.1",
        prefix="lps.dpa_ye_2024.table_1_1",
        kind="count",
        measure_id="properties_awarded",
        measure_label="Properties with a current Disabled Person's Allowance award",
        concept="lps.disabled_persons_allowance_properties",
        unit="count",
        entity="dwelling",
        entity_role="disabled_persons_allowance_property",
        notes=DPA_COUNT_NOTES,
    )
    record_sets += council_record_sets(
        grid,
        "Table 1.2",
        prefix="lps.dpa_ye_2024.table_1_2",
        kind="amount",
        measure_id="net_amount",
        measure_label="Net amount of Disabled Person's Allowance awarded",
        concept="lps.disabled_persons_allowance_net_amount",
        unit="gbp",
        entity="dwelling",
        entity_role="disabled_persons_allowance_property",
        notes=DPA_AMOUNT_NOTES,
    )
    payload = allowance_payload(
        "lps-disabled-persons-allowance-ye-2024",
        "LPS Disabled Person's Allowance: properties awarded and net amounts by district "
        "council, 2009-10 to 2023-24",
        DPA_DIRECTORY,
        "Disabled Person's Allowance statistics to year end 2024, Tables 1.1 and 1.2",
        ["Table 1.1", "Table 1.2"],
    )
    payload["record_sets"] = record_sets
    return render(DPA_HEADER, payload)


# ---------------------------------------------------- 2. ONS CRPSF, NI domestic rates

CRPSF_DIRECTORY = "ons/crpsf_ni_domestic_rates_fye2025"
CRPSF_SHEET = "Northern Ireland"
CRPSF_URL = (
    "https://www.ons.gov.uk/economy/governmentpublicsectorandtaxes/publicsectorfinance/"
    "datasets/countryandregionalpublicsectorfinancesrevenuetables"
)
CRPSF_TITLE = (
    "Total Public Sector (PS) Current Receipts excluding PS Banks for Northern Ireland"
)
CRPSF_LINES = (
    (51, "Northern Ireland Regional Domestic Rates", "ni_regional_domestic_rates"),
    (52, "Northern Ireland District Domestic Rates", "ni_district_domestic_rates"),
)
CRPSF_HEADER = f"""
ONS, Country and regional public sector finances revenue tables, financial year ending
2025 (published 26 May 2026), for {ISSUE} item 1. Written by
scripts/build_uk_395_packages.py. Only the 'Northern Ireland' worksheet is parsed.

Its two domestic rates rows, 'Northern Ireland Regional Domestic Rates' (row 51) and
'Northern Ireland District Domestic Rates' (row 52), in every published financial year,
1999 to 2000 through 2024 to 2025: GBP million, financial years April to March, as the
sheet states. The regional rate is Northern Ireland Executive revenue and the district
rate the councils'; together they are the domestic bill, which LPS levies as one. Each
row is its own concept; the package derives no total. The sheet's non-domestic rows (38
and 47) are not asked for and are not ported. The workbook does not state whether these
rows are accrued or cash, or gross or net of reliefs and rebates, so they are not the
same measure as lps-domestic-rates-paid-2026, which is cash paid against the year's
accounts (2024-25: GBP 498 million and GBP 441 million here, GBP 889.5 million paid
there).
"""


def build_crpsf() -> str:
    filename, path = manifest_file(CRPSF_DIRECTORY)
    grid = {
        (row, column): value
        for (_sheet, row, column), value in grid_of(
            source_cells_from_xlsx(
                path.read_bytes(), metadata(filename), sheets=(CRPSF_SHEET,)
            )
        ).items()
    }
    assert grid[(1, "A")] == CRPSF_TITLE
    assert grid[(3, "A")] == "£ million"
    statement = grid[(2, "A")]
    assert "All numeric values equate to £ millions" in statement
    columns = []
    for index in range(2, 28):
        column = get_column_letter(index)
        header = grid[(3, column)]
        start, end = header.split(" to ")
        assert int(end) == int(start) + 1, header
        columns.append((int(start), column, header))
    assert columns[-1][2] == "2024 to 2025"
    guards = [
        {
            "column": "A",
            "row": 1,
            "expected_value": CRPSF_TITLE,
            "label": "sheet title",
        },
        {
            "column": "A",
            "row": 2,
            "expected_value": statement,
            "label": "unit and period statement",
        },
        {"column": "A", "row": 3, "expected_value": "£ million", "label": "unit cell"},
    ]
    record_sets = []
    for row, label, line_id in CRPSF_LINES:
        assert grid[(row, "A")] == label
        concept = "ons." + slug(label)
        for opening, column, header in columns:
            record_sets.append(
                record_set(
                    f"ons.crpsf_fye2025.{line_id}.fy{opening}",
                    provenance_class="administrative",
                    sheet_name=CRPSF_SHEET,
                    period_type="fiscal_year",
                    period=opening,
                    period_coverage=fiscal_coverage(opening, header),
                    geography=NORTHERN_IRELAND,
                    entity="household",
                    entity_role="domestic_ratepayer",
                    domain="public_sector_finances",
                    groupby_dimension="ons.crpsf_revenue_line",
                    rows=[
                        {
                            "value_id": line_id,
                            "label": label,
                            "ordinal": 0,
                            "row_number": row,
                            "expected_row_header_column": "A",
                            "expected_row_header": label,
                            "table_record_kind": "total",
                            "guard_cells": guards,
                        }
                    ],
                    measures=[
                        measure(
                            "amount",
                            f"{label}, {header}",
                            column,
                            concept=concept,
                            source_concept=concept,
                            authority="ons",
                            evidence_url=CRPSF_URL,
                            notes=(
                                "ONS country and regional public sector finances, financial "
                                f"year ending 2025, worksheet '{CRPSF_SHEET}', row {row} "
                                f"('{label}'), column '{header}'. {statement}"
                            ),
                            unit="gbp",
                            aggregation="sum",
                            value_scale=1000000,
                            header=header,
                            header_row=3,
                        )
                    ],
                )
            )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "ons-crpsf-ni-domestic-rates-fye2025",
        "label": "ONS country and regional public sector finances: Northern Ireland "
        "regional and district domestic rates, 1999-00 to 2024-25",
        "dimension_labels": {
            "ons.crpsf_revenue_line": "Country and regional public sector finances revenue line"
        },
        "artifact": artifact(
            "ons",
            "Country and regional public sector finances revenue tables, financial year "
            "ending 2025: Total Public Sector (PS) Current Receipts excluding PS Banks for "
            "Northern Ireland",
            CRPSF_DIRECTORY,
            "crpsf_fye2025_2026_05_26",
            "xlsx_used_range",
            "xlsx used-range cell parse of the Northern Ireland worksheet",
            2025,
            sheets=[CRPSF_SHEET],
        ),
        "record_sets": record_sets,
    }
    return render(CRPSF_HEADER, payload)


# ------------------------------------------------------- 3. BUS01 for Wales

BUS01_DIRECTORY = "dft/bus01_passenger_journeys_2025"
BUS01_URL = (
    "https://www.gov.uk/government/statistical-data-sets/bus-statistics-data-tables"
)
BUS01C_TYPES = (
    ("elderly_disabled_concessionary", "Elderly/Disabled journeys"),
    ("total_concessionary", "Total concessionary journeys"),
)
BUS01_HEADER = f"""
DfT BUS01 (revised 24 March 2026) for Wales, for {ISSUE} item 2. Written by
scripts/build_uk_395_packages.py. It reads the workbook dft-bus01-passenger-journeys-2025
already pins (data/dft/bus01_passenger_journeys_2025), whose England package leaves the
devolved and Great Britain columns out of its declared scope.

BUS01a passenger journeys on local bus services in Wales (column R), years ending March
2005 to 2025, and BUS01c concessionary passenger journeys in Wales (column P), years
ending March 2008 to 2025, for both of the table's Type values: 'Elderly/Disabled
journeys' and 'Total concessionary journeys' (which includes youth schemes, BUS01 note
4). Fare-paying journeys are not published; the package derives no difference. The
record sets mirror the England package's: the same concepts, journey categories, period
stamps (the year ending March, by its closing year) and guards.

welshgov-bus-statistics-2024-25 carries the same journeys, as the Welsh Government
publishes them rounded, under its own concept and stamped by opening year. This
package's fiscal_year 2025 (the year ending March 2025, 71.7 million) is that package's
fiscal_year 2024 (2024-25), and likewise for 2023 and 2022. Join the two on their
coverage dates, not their period values.
"""


def build_bus01_wales() -> str:
    filename, path = manifest_file(BUS01_DIRECTORY)
    grid = grid_of(source_cells_from_ods(path.read_bytes(), metadata(filename)))
    record_sets = []

    def common_guards(sheet: str, unit_heading_row: int = 7) -> list[dict]:
        guards = [
            {
                "column": "A",
                "row": 4,
                "expected_value": f"Table {sheet}",
                "label": "table identity",
            },
            {
                "column": "A",
                "row": unit_heading_row,
                "expected_value": grid[(sheet, unit_heading_row, "A")],
                "label": "published unit heading",
            },
            {
                "column": "A",
                "row": 8,
                "expected_value": "Year ending March",
                "label": "fiscal-year heading",
            },
        ]
        assert grid[(sheet, 4, "A")] == f"Table {sheet}"
        assert grid[(sheet, unit_heading_row, "A")] == "Passenger journeys (millions)"
        assert grid[(sheet, 8, "A")] == "Year ending March"
        return guards

    def wales_row(
        sheet: str, column: str, row: int, year: int, guards: list[dict]
    ) -> dict:
        assert grid[(sheet, 8, column)] == "Wales"
        return {
            "value_id": "wales",
            "label": "Wales",
            "ordinal": 0,
            "row_number": row,
            "column": column,
            "source_column_id": "wales",
            "expected_row_header_column": "A",
            "expected_row_header": year,
            "expected_column_header_row": 8,
            "expected_column_header": "Wales",
            **WALES,
            "table_record_kind": "total",
            "guard_cells": guards,
        }

    def coverage(year: int) -> dict:
        return {
            "basis": "fiscal",
            "source_period_label": f"Year ending March {year}",
            "start_date": f"{year - 1}-04-01",
            "end_date": f"{year}-03-31",
            "notes": "DfT labels the reporting year by its March closing year.",
        }

    a_rows = {
        grid[("BUS01a", row, "A")]: row
        for (sheet, row, column) in grid
        if sheet == "BUS01a"
        and column == "A"
        and row > 8
        and isinstance(grid[(sheet, row, column)], int)
    }
    assert sorted(a_rows) == list(range(2005, 2026)), sorted(a_rows)
    base = common_guards("BUS01a")
    for year in range(2005, 2026):
        row = a_rows[year]
        guards = [
            {
                "column": "A",
                "expected_value": year,
                "label": "fiscal-year closing year",
            },
            *base,
        ]
        record_sets.append(
            record_set(
                f"dft.bus01.wales.bus01a.passenger_journeys.fy{year}",
                provenance_class="administrative",
                sheet_name="BUS01a",
                period_type="fiscal_year",
                period=year,
                period_coverage=coverage(year),
                geography=WALES,
                entity="person",
                entity_role="bus_passenger",
                domain="local_bus_travel",
                groupby_dimension="dft.bus_area",
                rows=[wales_row("BUS01a", "R", row, year, guards)],
                measures=[
                    measure(
                        "passenger_journeys",
                        "Passenger journeys",
                        "R",
                        concept="dft.local_bus_passenger_journeys",
                        source_concept="dft.local_bus_passenger_journeys",
                        authority="dft",
                        evidence_url=BUS01_URL,
                        notes="BUS01a Passenger journeys (millions).",
                        unit="count",
                        aggregation="sum",
                        value_scale=1000000,
                    )
                ],
            )
        )
    base = common_guards("BUS01c")
    assert grid[("BUS01c", 8, "B")] == "Type"
    c_rows = {
        (grid[("BUS01c", row, "A")], grid[("BUS01c", row, "B")]): row
        for (sheet, row, column) in grid
        if sheet == "BUS01c"
        and column == "A"
        and row > 8
        and isinstance(grid[(sheet, row, column)], int)
    }
    for journey_category, type_label in BUS01C_TYPES:
        for year in range(2008, 2026):
            row = c_rows[(year, type_label)]
            guards = [
                {
                    "column": "A",
                    "expected_value": year,
                    "label": "fiscal-year closing year",
                },
                {
                    "column": "B",
                    "expected_value": type_label,
                    "label": "BUS01c Type value",
                },
                *base,
                {
                    "column": "B",
                    "row": 8,
                    "expected_value": "Type",
                    "label": "Type column heading",
                },
            ]
            record_sets.append(
                record_set(
                    f"dft.bus01.wales.bus01c.{journey_category}.fy{year}",
                    provenance_class="administrative",
                    sheet_name="BUS01c",
                    period_type="fiscal_year",
                    period=year,
                    period_coverage=coverage(year),
                    geography=WALES,
                    entity="person",
                    entity_role="bus_passenger",
                    domain="local_bus_travel",
                    groupby_dimension="dft.bus_area",
                    shared_filters={"journey_category": journey_category},
                    rows=[wales_row("BUS01c", "P", row, year, guards)],
                    measures=[
                        measure(
                            "passenger_journeys",
                            "Concessionary passenger journeys",
                            "P",
                            concept="dft.local_bus_passenger_journeys",
                            source_concept="dft.local_bus_passenger_journeys",
                            authority="dft",
                            evidence_url=BUS01_URL,
                            notes="BUS01c Passenger journeys (millions), distinguished by the "
                            "publisher Type column.",
                            unit="count",
                            aggregation="sum",
                            value_scale=1000000,
                        )
                    ],
                )
            )
    england = yaml.safe_load(
        (PACKAGES / "dft/bus01_passenger_journeys_2025/source_package.yaml").read_text()
    )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "dft-bus01-wales-journeys-2025",
        "label": "DfT BUS01 local bus passenger and concessionary journeys in Wales, years "
        "ending March 2005 to 2025",
        "dimension_labels": england["dimension_labels"],
        "dimension_value_labels": england["dimension_value_labels"],
        "artifact": dict(england["artifact"]),
        "record_sets": record_sets,
    }
    payload["artifact"]["source_table"] = (
        "BUS01a passenger journeys and BUS01c concessionary passenger journeys, Wales"
    )
    payload["artifact"]["extracted_at"] = EXTRACTED_AT
    return render(BUS01_HEADER, payload)


# ------------------------------------------- 4. Childcare Offer for Wales, Table 4

CHILDCARE_DIRECTORY = "welshgov/childcare_offer_report_2023_24"
CHILDCARE_URL = (
    "https://www.gov.wales/report-childcare-offer-wales-september-2023-august-2024"
)
CHILDCARE_TABLE = (
    "Table 4. Estimated take-up rate of the Childcare Offer for Wales, 2023-24"
)
CHILDCARE_LINES = (
    # (line prefix, number text, value id, concept, provenance, role, unit, aggregation)
    (
        "Children in Offer-funded childcare this year",
        "21,283",
        "children_in_offer_funded_childcare",
        "administrative",
        "child_in_offer_funded_childcare",
        "count",
        "sum",
    ),
    (
        "Estimated eligible population for this year",
        "36,600",
        "estimated_eligible_population",
        "model_output",
        "child_eligible_for_childcare_offer",
        "count",
        "sum",
    ),
    (
        "Estimated take-up rate",
        "58",
        "estimated_take_up_rate",
        "model_output",
        "child_eligible_for_childcare_offer",
        "percent",
        "share",
    ),
)
CHILDCARE_NOTES = (
    "Welsh Government, Report of the Childcare Offer for Wales: September 2023 to August "
    "2024 (social research 99/2025), 'Table 4. Estimated take-up rate of the Childcare "
    "Offer for Wales, 2023-24'. Paragraph 2.2: 'To consider the reach of the Offer, we "
    "estimate a 'take-up rate'. This is estimated using a modelled estimate of the "
    "eligible population.' Paragraph 2.3: 'Based on current eligibility criteria, we "
    "estimate that 58% of eligible children accessed the Offer in 2023-24.' Table 4's "
    "sources: 'Childcare Offer for Wales monitoring data, Welsh Government analysis of the "
    "ONS Annual Population Survey 2023'."
)
CHILDCARE_HEADER = f"""
Welsh Government, Report of the Childcare Offer for Wales: September 2023 to August 2024
(social research 99/2025, 15 October 2025), archived PDF on the pdf_text_numbers lane,
for {ISSUE} item 3. Written by scripts/build_uk_395_packages.py.

Table 4's three figures, for the Offer year September 2023 to August 2024: children in
Offer-funded childcare (21,283; the Offer's monitoring information), the estimated
eligible population under the current eligibility criteria (36,600; Welsh Government
analysis of the ONS Annual Population Survey 2023, so calendar-2023 survey data behind a
fact for the 2023-24 Offer year) and the estimated take-up rate (58%). The report publishes
the rate rounded; the package stores the published figures and derives none. The Offer
year runs September to August, so the facts are academic-year periods stamped by their
opening year, with dates and no fiscal or calendar basis. No later report is published
yet.
"""


def build_childcare() -> str:
    filename, path = manifest_file(CHILDCARE_DIRECTORY)
    cells = source_cells_from_pdf_text_numbers(path.read_bytes(), metadata(filename))
    numbers: dict[int, dict[int, object]] = {}
    for cell in cells:
        numbers.setdefault(cell.row_number, {})[cell.column_number] = cell.raw_value
    rows = [
        {"row": row, "page": v[1], "line": v[2], "text": v[3], "number_text": v[4]}
        for row, v in sorted(numbers.items())
        if row > 1
    ]
    # The parser reads no number from 'Table 4.' (a full stop follows the 4), so the
    # title line's first number row is its '2023'. The contents page's line differs.
    (title,) = [
        row
        for row in rows
        if row["text"] == CHILDCARE_TABLE and row["number_text"] == "2023"
    ]
    record_sets = []
    for (
        prefix,
        number_text,
        value_id,
        provenance,
        role,
        unit,
        aggregation,
    ) in CHILDCARE_LINES:
        (found,) = [
            row
            for row in rows
            if row["page"] == title["page"]
            and str(row["text"]).startswith(prefix)
            and row["number_text"] == number_text
        ]
        record_sets.append(
            record_set(
                f"welshgov.childcare_offer_report_2023_24.table_4.{value_id}.ay2023",
                provenance_class=provenance,
                sheet_name="document_numbers",
                period_type="academic_year",
                period=2023,
                period_coverage={
                    "start_date": "2023-09-01",
                    "end_date": "2024-08-31",
                    "source_period_label": "September 2023 to August 2024 (2023-24)",
                },
                geography=WALES,
                entity="person",
                entity_role=role,
                domain="childcare",
                groupby_dimension="welshgov.childcare_offer_table_4_line",
                rows=[
                    {
                        "value_id": value_id,
                        "label": prefix,
                        "ordinal": 0,
                        "row_number": found["row"],
                        "expected_row_header_column": "C",
                        "expected_row_header": found["text"],
                        "table_record_kind": "total",
                        "guard_cells": [
                            {
                                "column": "A",
                                "expected_value": found["page"],
                                "label": "PDF page number",
                            },
                            {
                                "column": "B",
                                "expected_value": found["line"],
                                "label": "PDF extracted line number",
                            },
                            {
                                "column": "D",
                                "expected_value": number_text,
                                "label": "source number text",
                            },
                            {
                                "column": "C",
                                "row": title["row"],
                                "expected_value": CHILDCARE_TABLE,
                                "label": "table title line",
                            },
                        ],
                    }
                ],
                measures=[
                    measure(
                        value_id,
                        prefix,
                        "E",
                        concept=f"welshgov.childcare_offer.{value_id}",
                        source_concept=f"welshgov.childcare_offer.{value_id}",
                        authority="welshgov",
                        evidence_url=CHILDCARE_URL,
                        notes=CHILDCARE_NOTES + f" Line: '{found['text']}'.",
                        unit=unit,
                        aggregation=aggregation,
                        header="numeric_value",
                    )
                ],
            )
        )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "welshgov-childcare-offer-report-2023-24",
        "label": "Welsh Government Childcare Offer for Wales report, Table 4: children "
        "funded, estimated eligible population and estimated take-up, 2023-24",
        "dimension_labels": {
            "welshgov.childcare_offer_table_4_line": "Childcare Offer report Table 4 line"
        },
        "artifact": artifact(
            "welshgov",
            "Report of the Childcare Offer for Wales: September 2023 to August 2024, Table 4",
            CHILDCARE_DIRECTORY,
            "childcare_offer_report_2025_10_15",
            "pdf_text_numbers",
            "pypdf text-line number extraction from the full publisher PDF",
            2025,
        ),
        "record_sets": record_sets,
    }
    return render(CHILDCARE_HEADER, payload)


# ----------------------------------------------------- 5. ONS time series (PUSF, MM23)

PSF_TOPIC = "economy/governmentpublicsectorandtaxes/publicsectorfinance"
CPI_TOPIC = "economy/inflationandpriceindices"


@dataclass(frozen=True)
class Series:
    directory: str
    package_id: str
    cdid: str
    dataset: str
    topic: str
    concept: str
    measure_label: str
    unit: str
    aggregation: str
    value_scale: int | None
    entity: str
    entity_role: str
    domain: str
    provenance_class: str
    periods: tuple[tuple[object, str, object], ...]
    package_label: str
    header: str
    survey_instrument: str | None = None


def annual(years: range) -> tuple[tuple[object, str, object], ...]:
    return tuple((year, "calendar_year", year) for year in years)


def januaries(years: range) -> tuple[tuple[object, str, object], ...]:
    return tuple((f"{year} JAN", "month", f"{year}-01") for year in years)


VED_NOTE = """
Annual calendar-year observations, 2018 to 2025, as the series publishes them; its
quarters and months are not ported. CDDZ (households, 'Other taxes') and EKED
(businesses, 'Taxes on production') are the national accounts' split of vehicle excise
duty, which the OBR forecasts as one total. The package derives no total and no
financial year. The series' metadata state no accounting basis, while the OBR's VED line
is on a cash basis: use the split for the households' and businesses' shares, not as
levels against the OBR line.
"""
WEIGHT_NOTE = """
The weights for weight years 2024 to 2026, as published. ONS states the weights in parts
per thousand of the CPI basket: CJXB's series metadata says so, and L89X and L89Y, whose
metadata leave the unit blank, are CJXB's two classes (L89X + L89Y equals CJXB in each
of these years). ONS bases the weights for index year Y on household spending in year
Y-2, price-updated to January of Y ('Consumer price inflation, updating weights: 2026');
the package stores the weights as published and undoes nothing.
"""
INDEX_NOTE = """
The index's annual figures for 2023 to 2025 and its January values for 2023 to 2026, as
published (2015=100). ONS's annual figure for an index is the average of its twelve
monthly values.
"""
SERIES = (
    Series(
        "ons/pusf_vehicle_duty_households_october_2026",
        "ons-pusf-vehicle-duty-households-october-2026",
        "cddz",
        "pusf",
        PSF_TOPIC,
        "ons.vehicle_duty_paid_by_households",
        "Vehicle duty paid by households",
        "gbp",
        "sum",
        1000000,
        "household",
        "vehicle_excise_duty_payer",
        "public_sector_finances",
        "administrative",
        annual(range(2018, 2026)),
        "ONS PUSF CDDZ: vehicle duty paid by households, calendar years 2018 to 2025",
        "ONS public sector finances time series CDDZ (PUSF), 'CG: Current receipts: Other "
        "taxes: Vehicle duty paid by households: £m CPNSA', released 21 October 2026, for "
        f"{ISSUE} (comment of 29 October, vehicle excise duty)." + "\n\n" + VED_NOTE,
    ),
    Series(
        "ons/pusf_vehicle_duty_businesses_october_2026",
        "ons-pusf-vehicle-duty-businesses-october-2026",
        "eked",
        "pusf",
        PSF_TOPIC,
        "ons.vehicle_duty_paid_by_businesses",
        "Vehicle duty paid by businesses",
        "gbp",
        "sum",
        1000000,
        "firm",
        "vehicle_excise_duty_payer",
        "public_sector_finances",
        "administrative",
        annual(range(2018, 2026)),
        "ONS PUSF EKED: vehicle duty paid by businesses, calendar years 2018 to 2025",
        "ONS public sector finances time series EKED (PUSF), 'CG: Current receipts: Taxes "
        "on production: Vehicle duty paid by businesses: £m', released 21 October 2026, "
        f"for {ISSUE} (comment of 29 October, vehicle excise duty)."
        + "\n\n"
        + VED_NOTE,
    ),
    Series(
        "ons/mm23_cpi_weight_gas_october_2026",
        "ons-mm23-cpi-weight-gas-october-2026",
        "cjxb",
        "mm23",
        CPI_TOPIC,
        "ons.cpi_weight_04_5_2_gas",
        "CPI weight, 04.5.2 Gas",
        "parts_per_thousand",
        "share",
        None,
        "household",
        "cpi_household_expenditure",
        "consumer_prices",
        "model_output",
        annual(range(2024, 2027)),
        "ONS MM23 CJXB: CPI weight for COICOP 04.5.2 Gas, weight years 2024 to 2026",
        "ONS consumer price inflation time series CJXB (MM23), 'CPI WEIGHTS 04.5.2 : GAS', "
        f"released 21 October 2026, for {ISSUE} (comment of 29 October, bottled gas)."
        + "\n\n"
        + WEIGHT_NOTE,
    ),
    Series(
        "ons/mm23_cpi_weight_natural_gas_october_2026",
        "ons-mm23-cpi-weight-natural-gas-october-2026",
        "l89x",
        "mm23",
        CPI_TOPIC,
        "ons.cpi_weight_04_5_2_1_natural_gas_and_town_gas",
        "CPI weight, 04.5.2.1 Natural gas and town gas",
        "parts_per_thousand",
        "share",
        None,
        "household",
        "cpi_household_expenditure",
        "consumer_prices",
        "model_output",
        annual(range(2024, 2027)),
        "ONS MM23 L89X: CPI weight for COICOP 04.5.2.1 Natural gas and town gas, weight "
        "years 2024 to 2026",
        "ONS consumer price inflation time series L89X (MM23), 'CPI WEIGHTS 04.5.2.1 "
        f"Natural gas and town gas', released 21 October 2026, for {ISSUE} (comment of 29 "
        "October, bottled gas)." + "\n\n" + WEIGHT_NOTE,
    ),
    Series(
        "ons/mm23_cpi_weight_liquefied_hydrocarbons_october_2026",
        "ons-mm23-cpi-weight-liquefied-hydrocarbons-october-2026",
        "l89y",
        "mm23",
        CPI_TOPIC,
        "ons.cpi_weight_04_5_2_2_liquefied_hydrocarbons",
        "CPI weight, 04.5.2.2 Liquefied hydrocarbons",
        "parts_per_thousand",
        "share",
        None,
        "household",
        "cpi_household_expenditure",
        "consumer_prices",
        "model_output",
        annual(range(2024, 2027)),
        "ONS MM23 L89Y: CPI weight for COICOP 04.5.2.2 Liquefied hydrocarbons, weight "
        "years 2024 to 2026",
        "ONS consumer price inflation time series L89Y (MM23), 'CPI WEIGHTS 04.5.2.2 "
        "Liquefied hydrocarbons (butane, propane,etc)', released 21 October 2026, for "
        f"{ISSUE} (comment of 29 October, bottled gas)." + "\n\n" + WEIGHT_NOTE,
    ),
    Series(
        "ons/mm23_cpi_index_natural_gas_october_2026",
        "ons-mm23-cpi-index-natural-gas-october-2026",
        "l7e9",
        "mm23",
        CPI_TOPIC,
        "ons.cpi_index_04_5_2_1_natural_gas_and_town_gas",
        "CPI index, 04.5.2.1 Natural gas and town gas (2015=100)",
        "index_2015_100",
        "ratio",
        None,
        "household",
        "cpi_household_expenditure",
        "consumer_prices",
        "survey_aggregate",
        annual(range(2023, 2026)) + januaries(range(2023, 2027)),
        "ONS MM23 L7E9: CPI index for COICOP 04.5.2.1 Natural gas and town gas, 2023 to "
        "2026",
        "ONS consumer price inflation time series L7E9 (MM23), 'CPI INDEX 04.5.2.1 Natural "
        f"gas and town gas 2015=100', released 21 October 2026, for {ISSUE} (comment of 29 "
        "October, bottled gas)." + "\n\n" + INDEX_NOTE,
        survey_instrument="ONS consumer price index price collection",
    ),
    Series(
        "ons/mm23_cpi_index_liquefied_hydrocarbons_october_2026",
        "ons-mm23-cpi-index-liquefied-hydrocarbons-october-2026",
        "l7ea",
        "mm23",
        CPI_TOPIC,
        "ons.cpi_index_04_5_2_2_liquefied_hydrocarbons",
        "CPI index, 04.5.2.2 Liquefied hydrocarbons (2015=100)",
        "index_2015_100",
        "ratio",
        None,
        "household",
        "cpi_household_expenditure",
        "consumer_prices",
        "survey_aggregate",
        annual(range(2023, 2026)) + januaries(range(2023, 2027)),
        "ONS MM23 L7EA: CPI index for COICOP 04.5.2.2 Liquefied hydrocarbons, 2023 to 2026",
        "ONS consumer price inflation time series L7EA (MM23), 'CPI INDEX 04.5.2.2 "
        "Liquefied hydrocarbons (butane, propane etc) 2015=100', released 21 October 2026, "
        f"for {ISSUE} (comment of 29 October, bottled gas)." + "\n\n" + INDEX_NOTE,
        survey_instrument="ONS consumer price index price collection",
    ),
)
SERIES_DIMENSIONS = {
    "pusf": ("ons.pusf_series", "Public sector finances (PUSF) series"),
    "mm23": ("ons.mm23_series", "Consumer price inflation (MM23) series"),
}


def build_series(series: Series) -> str:
    sheet, grid = csv_grid(series.directory)
    title = grid[(1, "B")]
    assert grid[(1, "A")] == "Title"
    assert (grid[(2, "A")], grid[(2, "B")]) == ("CDID", series.cdid.upper())
    assert (grid[(3, "A")], grid[(3, "B")]) == (
        "Source dataset ID",
        series.dataset.upper(),
    )
    assert (grid[(6, "A")], grid[(6, "B")]) == ("Release date", "21-10-2026")
    rows_by_label = {
        grid[(row, "A")]: row for (row, column) in grid if column == "A" and row > 8
    }
    guards = [
        {
            "column": "A",
            "row": 2,
            "expected_value": "CDID",
            "label": "series identifier heading",
        },
        {
            "column": "B",
            "row": 2,
            "expected_value": series.cdid.upper(),
            "label": "series identifier",
        },
        {
            "column": "B",
            "row": 3,
            "expected_value": series.dataset.upper(),
            "label": "source dataset",
        },
        {
            "column": "B",
            "row": 6,
            "expected_value": "21-10-2026",
            "label": "release date",
        },
    ]
    for row, label in ((4, "PreUnit"), (5, "Unit")):
        assert grid[(row, "A")] == label
        if grid[(row, "B")] is not None:
            guards.append(
                {
                    "column": "B",
                    "row": row,
                    "expected_value": grid[(row, "B")],
                    "label": f"{label} cell",
                }
            )
    dimension, dimension_label = SERIES_DIMENSIONS[series.dataset]
    url = f"https://www.ons.gov.uk/{series.topic}/timeseries/{series.cdid}/{series.dataset}"
    record_sets = []
    for label, period_type, period in series.periods:
        row = rows_by_label[label]
        period_id = (
            f"cy{period}"
            if period_type == "calendar_year"
            else f"m{str(period).replace('-', '_')}"
        )
        record_sets.append(
            record_set(
                f"ons.{series.dataset}_{series.cdid}.{period_id}",
                provenance_class=series.provenance_class,
                survey_instrument=series.survey_instrument,
                sheet_name=sheet,
                period_type=period_type,
                period=period,
                geography=UNITED_KINGDOM,
                entity=series.entity,
                entity_role=series.entity_role,
                domain=series.domain,
                groupby_dimension=dimension,
                rows=[
                    {
                        "value_id": series.cdid,
                        "label": title,
                        "ordinal": 0,
                        "row_number": row,
                        "expected_row_header_column": "A",
                        "expected_row_header": label,
                        "table_record_kind": "total",
                        "guard_cells": guards,
                    }
                ],
                measures=[
                    measure(
                        "value",
                        f"{series.measure_label}, {label}",
                        "B",
                        concept=series.concept,
                        source_concept=f"ons.{series.dataset}_{series.cdid}",
                        authority="ons",
                        evidence_url=url,
                        notes=f"ONS time series {series.cdid.upper()} ({series.dataset.upper()}), "
                        f"'{title}', released 21 October 2026; the row labelled '{label}'.",
                        unit=series.unit,
                        aggregation=series.aggregation,
                        value_scale=series.value_scale,
                        header=title,
                    )
                ],
            )
        )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": series.package_id,
        "label": series.package_label,
        "dimension_labels": {dimension: dimension_label},
        "artifact": artifact(
            "ons",
            f"{series.dataset.upper()} time series {series.cdid.upper()}: {title}",
            series.directory,
            f"{series.dataset}_2026_10_21",
            "delimited_text_full_rows",
            "delimited text full-row parse of the ONS time series CSV",
            2026,
        ),
        "record_sets": record_sets,
    }
    return render(series.header, payload)


BUILDERS = {
    LPS_DIRECTORY: build_lps,
    LPA_DIRECTORY: build_lpa,
    DPA_DIRECTORY: build_dpa,
    CRPSF_DIRECTORY: build_crpsf,
    "dft/bus01_wales_journeys_2025": build_bus01_wales,
    CHILDCARE_DIRECTORY: build_childcare,
    **{
        series.directory: (lambda series=series: build_series(series))
        for series in SERIES
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the generated YAML with the committed files instead of writing.",
    )
    args = parser.parse_args()
    stale = []
    for directory, build in BUILDERS.items():
        text = build()
        path = PACKAGES / directory / "source_package.yaml"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(directory)
        else:
            write(directory, text)
    for directory in stale:
        print(f"stale: packages/{directory}/source_package.yaml")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
