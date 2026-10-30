"""Generate the source packages for PolicyEngine/chronicle#395.

Run from the repository root:

    uv run python scripts/build_uk_395_packages.py

Each package is written from its pinned artifact, read with Chronicle's own parsers, so
every row number, column and guard cell below is one the package parser sees.

- ``lps-domestic-rates-paid-2026``: Land & Property Services' domestic rates paid and
  paying occupancies by district council, rating years 2020-21 to 2025-26 (item 1).
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
                "label": "Journey Category",
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
bill is the regional and the district rate together, levied as one bill net of the
reliefs credited to the account; the CSV publishes the amount paid, not the amount
levied, and gives no relief as a separate figure. The CSV prints amounts as '£' text
with thousands separators and counts with separators (the 2025-26 counts with a trailing
space); the delimited parser reads both as numbers. Each rating year is a fiscal-year
period (April to March), stamped by its opening year.
"""


def build_lps() -> str:
    sheet, grid = csv_grid(LPS_DIRECTORY)
    headers = {grid[(1, column)]: column for (row, column) in grid if row == 1}
    assert grid[(1, "A")] == "District Council"
    rows = []
    data_rows = sorted({row for (row, column) in grid if row > 1})
    for ordinal, row in enumerate(data_rows):
        name = grid[(row, "A")]
        if name == "Northern Ireland":
            geography = dict(NORTHERN_IRELAND)
        else:
            geography = {
                "geography_id": NI_COUNCILS[name],
                "geography_level": "local_authority",
                "geography_name": name,
                "geography_vintage": "lgd_2014",
            }
        rows.append(
            {
                "value_id": slug(name),
                "label": name,
                "ordinal": ordinal,
                "row_number": row,
                "expected_row_header_column": "A",
                "expected_row_header": name,
                **geography,
                "table_record_kind": "total",
            }
        )
    assert [row["label"] for row in rows][-1] == "Northern Ireland"
    assert {row["label"] for row in rows[:-1]} == set(NI_COUNCILS)
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
and 47) are not asked for and are not ported.
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
    "estimate that 58% of eligible children accessed the Offer in 2023-24.'"
)
CHILDCARE_HEADER = f"""
Welsh Government, Report of the Childcare Offer for Wales: September 2023 to August 2024
(social research 99/2025, 15 October 2025), archived PDF on the pdf_text_numbers lane,
for {ISSUE} item 3. Written by scripts/build_uk_395_packages.py.

Table 4's three figures, for the Offer year September 2023 to August 2024: children in
Offer-funded childcare (21,283; the Offer's monitoring information), the estimated
eligible population under the current eligibility criteria (36,600; modelled from the
ONS Annual Population Survey) and the estimated take-up rate (58%). The report publishes
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
financial year.
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
    CRPSF_DIRECTORY: build_crpsf,
    "dft/bus01_wales_journeys_2025": build_bus01_wales,
    CHILDCARE_DIRECTORY: build_childcare,
    **{
        series.directory: (lambda series=series: build_series(series))
        for series in SERIES
    },
}


def main() -> None:
    for directory, build in BUILDERS.items():
        write(directory, build())


if __name__ == "__main__":
    main()
