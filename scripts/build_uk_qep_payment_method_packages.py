"""Generate DESNZ's domestic payment-method shares by region for PolicyEngine/chronicle#420.

Run from the repository root:

    uv run python scripts/build_uk_qep_payment_method_packages.py

``--check`` compares the generated YAML with the committed files instead of writing. Each
package is written from its pinned workbook, read with Chronicle's own parser, so every
row number, column and guard cell below is one the package parser sees. The publisher's
text is asserted cell by cell, so a run against different bytes fails rather than
drifting. Nothing is downloaded and no value is computed.

Item 12 of PolicyEngine/chronicle#420, for a Direct Debit, standard credit and
prepayment draw in Microcosm (PolicyEngine/uk-energy-price-cap-jan-2027#4), asked in
PolicyEngine/chronicle#435 for Microcosm's next data PR: the Quarterly Energy Prices
tables that give domestic customers' payment method by region, each quarter from April
2024 and each year from 2024:

- ``desnz-qep-electricity-payment-methods-2026``: table 2.4.2, standard electricity;
- ``desnz-qep-time-of-use-electricity-payment-methods-2026``: table 2.4.3, Economy 7 and
  other time of use electricity;
- ``desnz-qep-gas-payment-methods-2026``: table 2.5.2, gas.
"""

from __future__ import annotations

import argparse
import hashlib
import textwrap
from dataclasses import dataclass
from pathlib import Path

import yaml
from openpyxl.utils import get_column_letter

from chronicle.geography_names import canonical_geography_name
from chronicle.sources.cells import SourceArtifactMetadata, source_cells_from_xlsx

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-11-10"
ISSUE = "PolicyEngine/chronicle#420"
SCRIPT = "scripts/build_uk_qep_payment_method_packages.py"
PAGE = (
    "https://www.gov.uk/government/statistical-data-sets/"
    "quarterly-domestic-energy-price-statistics"
)
FIRST_QUARTER = (2024, 2)  # #420: each published date from April 2024
YEARS = (2024, 2025)


class Flow(dict):
    """A small mapping written on one line, as the occupation packages write guards."""


class PackageDumper(yaml.SafeDumper):
    """Plain YAML with no anchors, so every record set reads on its own."""

    def ignore_aliases(self, data: object) -> bool:
        return True


PackageDumper.add_representer(
    Flow,
    lambda dumper, data: dumper.represent_mapping(
        "tag:yaml.org,2002:map", data, flow_style=True
    ),
)


def render(header: str, payload: dict) -> str:
    """The header's paragraphs, rewrapped as comment lines, then the package."""
    lines: list[str] = []
    for paragraph in textwrap.dedent(header).strip().split("\n\n"):
        if lines:
            lines.append("")
        lines += textwrap.wrap(
            " ".join(paragraph.split()),
            width=88,
            break_long_words=False,
            break_on_hyphens=False,
        )
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


def pinned(directory: str) -> tuple[dict, bytes]:
    """The manifest's one file entry and its bytes, checked against the pinned digest."""
    manifest = yaml.safe_load((DATA / directory / "manifest.yaml").read_text())
    (entry,) = manifest["files"].values()
    content = (DATA / directory / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"], directory
    assert len(content) == entry["size_bytes"], directory
    return entry, content


def grid_of(cells) -> dict[tuple[str, int, str], object]:
    grid: dict[tuple[str, int, str], object] = {}
    for cell in cells:
        if cell.raw_value in (None, ""):
            continue
        grid[
            (cell.sheet_name, cell.row_number, get_column_letter(cell.column_number))
        ] = cell.raw_value
    return grid


def write(directory: str, text: str) -> None:
    path = PACKAGES / directory / "source_package.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def squeeze(text: object) -> str:
    return " ".join(str(text).replace("\xa0", " ").split())


def constraint(variable: str, value: str, label: str) -> Flow:
    return Flow(variable=variable, operator="==", value=value, label=label)


def guard(column: str, value: object, label: str) -> Flow:
    return Flow(column=column, expected_value=value, label=label)


# ---------------------------------------------------------------- regions

# The 14 former Public Electricity Supplier distribution areas, under the ids and names
# the desnz-qep-electricity-unit-fixed-costs-2026 package already gives them.
PES = {
    "East Midlands": "east_midlands",
    "Eastern": "eastern",
    "London": "london",
    "Merseyside & North Wales": "merseyside_and_north_wales",
    "North East": "north_east",
    "North West": "north_west",
    "South East": "south_east",
    "South Wales": "south_wales",
    "South West": "south_west",
    "Southern": "southern",
    "West Midlands": "west_midlands",
    "Yorkshire": "yorkshire",
    "North Scotland": "north_scotland",
    "South Scotland": "south_scotland",
}
# The unit cost packages' value id where it is not the geography slug.
PES_VALUE_IDS = {"merseyside_and_north_wales": "merseyside_north_wales"}
# The nations and unions each table prints below the regions: (value id, code).
AREAS = {
    "England & Wales": ("england_and_wales", "K04000001"),
    "Scotland": ("scotland", "S92000003"),
    "Great Britain": ("great_britain", "K03000001"),
    "Northern Ireland": ("northern_ireland", "N92000002"),
    "United Kingdom": ("united_kingdom", "K02000001"),
    "UK": ("united_kingdom", "K02000001"),  # table 2.4.2's last quarter
}
QUARTERS = {"Jan – Mar": 1, "Apr – Jun": 2, "Jul – Sep": 3, "Oct – Dec": 4}
QUARTER_DATES = {1: ("01-01", "03-31"), 2: ("04-01", "06-30"), 3: ("07-01", "09-30")}
QUARTER_DATES[4] = ("10-01", "12-31")
METHODS = (
    # measure id, column header, the register's label
    ("standard_credit", "Credit (%)", "Standard credit"),
    ("direct_debit", "Direct Debit (%)", "Direct debit"),
    ("prepayment", "Prepayment (%)", "Prepayment"),
)
# The methodology sheet's definitions, quoted in each measure's evidence notes.
DEFINITIONS = {
    "standard_credit": "Note 3. Standard credit customers pay on receipt of their bill which "
    "is usually payment 3 months in arrears.",
    "direct_debit": "Note 4. Direct debit transfers an agreed or variable amount directly from "
    "the customer’s bank account to the energy supplier.",
    "prepayment": "Note 5. Prepayment requires the customer to make advance payment before fuel "
    "can be used.",
}
METHODOLOGY = (
    "Data on gas and electricity tariffs is received directly from a sample of energy "
    "companies that supply electricity and gas across the UK via a quarterly survey.",
    "In order for the sample data to be comparable for the whole market, data is uplifted to "
    "Ofgem's total customer numbers.",
)


def area(label: str, top: str) -> dict:
    """The row's value id, geography and record kind."""
    if label in PES:
        slug = PES[label]
        return {
            "value_id": PES_VALUE_IDS.get(slug, slug),
            "label": label,
            "geography_id": f"desnz:qep:pes:{slug}",
            "geography_level": "statistical_scope",
            "geography_name": label,
            "geography_vintage": "desnz_qep_pes_regions_2026",
            "table_record_kind": "detail",
        }
    value_id, code = AREAS[label]
    name = canonical_geography_name(code)
    assert name is not None, code
    if code == top:
        kind = "total"
    elif code in ("K04000001", "S92000003", "K03000001"):
        kind = "subtotal"
    else:
        kind = "detail"
    return {
        "value_id": value_id,
        "label": name,
        "geography_id": code,
        "geography_level": "country",
        "geography_name": name,
        "geography_vintage": "current",
        "table_record_kind": kind,
    }


# ---------------------------------------------------------------- the tables


@dataclass(frozen=True)
class QepTable:
    number: str
    package_id: str
    directory: str
    cover_title: str  # Cover Sheet row 2
    quarterly_title: str  # A1 of the quarterly sheet
    annual_title: str  # A1 of the annual sheet
    scope: str  # the table's own statement of whom it covers
    regions_note: str  # the note on the regions, quoted
    fuel: str
    metering: str | None
    metering_label: str | None
    concept: str
    label: str
    top: str  # the total row's code
    areas: int  # rows per period


ELECTRICITY_REGIONS = (
    "Note 1. The regions used in this table are the distribution areas of the former Public "
    "Electricity Suppliers (PES regions)."
)
TABLES = (
    QepTable(
        number="2.4.2",
        package_id="desnz-qep-electricity-payment-methods-2026",
        directory="desnz/qep_electricity_payment_methods_2026",
        cover_title="Regional variation of payment method for standard electricity",
        quarterly_title="Table 2.4.2 Regional variation of payment method for standard "
        "electricity, quarterly",
        annual_title="Table 2.4.2 Regional variation of payment method for standard "
        "electricity, annually",
        scope="Includes electricity customers on standard electricity tariffs only.",
        regions_note=ELECTRICITY_REGIONS,
        fuel="electricity",
        metering="standard",
        metering_label="Standard electricity",
        concept="desnz.qep.domestic_electricity_payment_method_share",
        label="DESNZ QEP table 2.4.2: standard electricity customers by payment method and "
        "region, quarterly from April 2024 and annually 2024 and 2025",
        top="K02000001",
        areas=19,
    ),
    QepTable(
        number="2.4.3",
        package_id="desnz-qep-time-of-use-electricity-payment-methods-2026",
        directory="desnz/qep_time_of_use_electricity_payment_methods_2026",
        cover_title="Regional variation of payment method for Economy 7 and other time of use "
        "electricity",
        quarterly_title="Table 2.4.3 Regional variation of payment method for Economy 7 and "
        "other time of use electricity tariffs, quarterly",
        annual_title="Table 2.4.3 Regional variation of payment method for Economy 7 and "
        "other time of use electricity tariffs, annually",
        scope="Includes electricity customers on both Economy 7 and time of use tariffs.",
        regions_note=ELECTRICITY_REGIONS,
        fuel="electricity",
        metering="economy_7_and_time_of_use",
        metering_label="Economy 7 and other time of use electricity",
        concept="desnz.qep.domestic_electricity_payment_method_share",
        label="DESNZ QEP table 2.4.3: Economy 7 and other time of use electricity customers "
        "by payment method and region, quarterly from April 2024 and annually 2024 and 2025",
        top="K02000001",
        areas=19,
    ),
    QepTable(
        number="2.5.2",
        package_id="desnz-qep-gas-payment-methods-2026",
        directory="desnz/qep_gas_payment_methods_2026",
        cover_title="Regional variation of payment method for gas",
        quarterly_title="Table 2.5.2 Regional variation of payment method for gas quarterly",
        annual_title="Table 2.5.2 Regional variation of payment method for gas, annual average",
        scope="Data in these tables shows the regional variation (Public Electricity Supplier "
        "region, for consistency with the electricity tables) of payment method for domestic "
        "gas customers.",
        regions_note=ELECTRICITY_REGIONS,
        fuel="gas",
        metering=None,
        metering_label=None,
        concept="desnz.qep.domestic_gas_payment_method_share",
        label="DESNZ QEP table 2.5.2: gas customers by payment method and region, quarterly "
        "from April 2024 and annually 2024 and 2025",
        top="K03000001",
        areas=17,
    ),
)


def sheet_text(grid: dict, sheet: str, rows: range) -> str:
    return squeeze(" ".join(str(grid.get((sheet, row, "A"), "")) for row in rows))


def header_row(grid: dict, sheet: str) -> int:
    (row,) = [
        row
        for (name, row, column), value in grid.items()
        if name == sheet and column == "A" and squeeze(value) == "Year"
    ]
    return row


def periods(grid: dict, sheet: str, quarterly: bool) -> dict[object, list[tuple]]:
    """{period: [(row, region label)]} for the ported periods, in sheet order."""
    first = header_row(grid, sheet) + 1
    found: dict[object, list[tuple]] = {}
    row = first
    while (sheet, row, "A") in grid:
        year = int(str(grid[(sheet, row, "A")]).strip())
        if year < FIRST_QUARTER[0]:
            row += 1
            continue
        if quarterly:
            quarter = QUARTERS[grid[(sheet, row, "B")]]
            label = grid[(sheet, row, "C")]
            if (year, quarter) >= FIRST_QUARTER:
                found.setdefault((year, quarter), []).append((row, label))
        elif year in YEARS:
            found.setdefault(year, []).append((row, grid[(sheet, row, "B")]))
        row += 1
    return found


def measures(table: QepTable, columns: dict[str, str], header: int) -> list[dict]:
    result = []
    for ordinal, (measure_id, heading, words) in enumerate(METHODS):
        result.append(
            {
                "measure_id": measure_id,
                "label": heading,
                "ordinal": ordinal,
                "column": columns[heading],
                "source_column_id": measure_id,
                "expected_column_header_row": header,
                "expected_column_header": heading,
                "concept": table.concept,
                "source_concept": table.concept,
                "concept_relation": "source_label",
                "concept_authority": "desnz",
                "concept_evidence_url": PAGE,
                "concept_evidence_notes": (
                    f"Quarterly Energy Prices table {table.number}, '{table.cover_title}', "
                    f"column '{heading}': the percentage of the region's customers paying "
                    f"by {words.lower()}. {table.scope} {DEFINITIONS[measure_id]} "
                    + " ".join(METHODOLOGY)
                ),
                "unit": "percent",
                "aggregation": "share",
                "expected_cell_type": "number",
                "filters": {"payment_method": measure_id},
                "constraints": [
                    constraint("payment_method", measure_id, "Payment method")
                ],
            }
        )
    return result


def record_set(
    table: QepTable,
    sheet: str,
    period: object,
    rows: list[tuple],
    grid: dict,
    measure_specs: list[dict],
    annual_note: str,
) -> dict:
    slug = table.number.replace(".", "_")
    if isinstance(period, tuple):
        year, quarter = period
        start, end = QUARTER_DATES[quarter]
        quarter_text = {number: text for text, number in QUARTERS.items()}[quarter]
        record_set_id = f"desnz.qep.table_{slug}.{year}_q{quarter}"
        spec = f"desnz.qep.table_{slug}.payment_methods.quarterly.v1"
        period_fields = {
            "period_type": "quarter",
            "period": f"{year}-Q{quarter}",
            "period_coverage": {
                "start_date": f"{year}-{start}",
                "end_date": f"{year}-{end}",
                "basis": "calendar",
                "source_period_label": f"{year} {quarter_text}",
                "notes": "The quarter the publisher's survey of suppliers covers.",
            },
        }
        header_column = "C"
    else:
        year = period
        record_set_id = f"desnz.qep.table_{slug}.cy{year}"
        spec = f"desnz.qep.table_{slug}.payment_methods.annual.v1"
        period_fields = {
            "period_type": "calendar_year",
            "period": year,
            "period_coverage": {
                "start_date": f"{year}-01-01",
                "end_date": f"{year}-12-31",
                "basis": "calendar",
                "source_period_label": str(year),
                "notes": annual_note,
            },
        }
        header_column = "B"
    shared_filters = {"fuel": table.fuel}
    shared_constraints = [constraint("fuel", table.fuel, "Fuel")]
    if table.metering:
        shared_filters["metering_arrangement"] = table.metering
        shared_constraints.append(
            constraint("metering_arrangement", table.metering, "Metering arrangement")
        )
    top_label = canonical_geography_name(table.top)
    entries = []
    for ordinal, (row, label) in enumerate(rows):
        entry = area(label, table.top)
        guards = [guard("A", year, "reference year")]
        if isinstance(period, tuple):
            guards.append(guard("B", quarter_text, "reference quarter"))
        entries.append(
            {
                "value_id": entry["value_id"],
                "label": entry["label"],
                "ordinal": ordinal,
                "row_number": row,
                "expected_row_header_column": header_column,
                "expected_row_header": label,
                **{key: entry[key] for key in entry if key.startswith("geography")},
                "table_record_kind": entry["table_record_kind"],
                "guard_cells": guards,
            }
        )
    return {
        "record_set_id": record_set_id,
        "provenance_class": "survey_aggregate",
        "assertion": "observation",
        "survey_instrument": "DESNZ Quarterly Energy Prices supplier survey",
        "record_set_spec_id": spec,
        "source_record_id_prefix": record_set_id,
        "sheet_name": sheet,
        **period_fields,
        "geography_id": table.top,
        "geography_level": "country",
        "geography_name": top_label,
        "geography_vintage": "current",
        "entity": "household",
        "entity_role": "domestic_energy_customer",
        "domain": "domestic_energy_prices",
        "groupby_dimension": "desnz.qep.price_region",
        "shared_filters": shared_filters,
        "shared_constraints": shared_constraints,
        "rows": entries,
        "measures": measure_specs,
    }


def build_table(table: QepTable) -> str:
    entry, content = pinned(table.directory)
    grid = grid_of(source_cells_from_xlsx(content, metadata(entry["filename"])))
    quarterly, annual = table.number, f"{table.number} (Annual)"
    assert grid[("Cover Sheet", 2, "A")] == table.cover_title, table.number
    assert grid[("Cover Sheet", 3, "A")] == "Publication date: 29/09/2026"
    assert (
        grid[("Cover Sheet", 4, "A")]
        == "Data period: New data for quarter ending June 2026"
    )
    assert squeeze(grid[(quarterly, 1, "A")]) == table.quarterly_title, table.number
    assert squeeze(grid[(annual, 1, "A")]) == table.annual_title, table.number
    notes = (
        sheet_text(grid, quarterly, range(2, 9))
        + " "
        + sheet_text(grid, "Cover Sheet", range(7, 12))
    )
    for quote in (table.scope, table.regions_note):
        assert squeeze(quote) in notes, (table.number, quote)
    methodology = sheet_text(grid, "Methodology", range(1, 15))
    for quote in (*METHODOLOGY, *DEFINITIONS.values()):
        assert squeeze(quote) in methodology, (table.number, quote)
    annual_text = sheet_text(grid, annual, range(2, 10))
    if (
        "These annual figures are averages of the rounded quarterly figures."
        in annual_text
    ):
        annual_note = (
            "'These annual figures are averages of the rounded quarterly figures' (the "
            "annual sheet)."
        )
    else:
        annual_note = (
            f"The publisher's annual figure for {table.annual_title.split(',')[0]}."
        )
    record_sets = []
    largest_gap = 0
    for sheet, is_quarterly in ((quarterly, True), (annual, False)):
        header = header_row(grid, sheet)
        columns = {
            squeeze(value): column
            for (name, row, column), value in grid.items()
            if name == sheet and row == header
        }
        found = periods(grid, sheet, is_quarterly)
        expected = 9 if is_quarterly else len(YEARS)
        assert len(found) == expected, (sheet, sorted(found))
        specs = measures(table, columns, header)
        for period, rows in found.items():
            labels = [label for _, label in rows]
            assert len(rows) == table.areas, (sheet, period, labels)
            assert sum(label in PES for label in labels) == 14, (sheet, period)
            for row, _ in rows:
                values = [
                    grid[(sheet, row, columns[heading])] for _, heading, _ in METHODS
                ]
                assert all(isinstance(value, int) for value in values), (
                    sheet,
                    row,
                    values,
                )
                largest_gap = max(largest_gap, abs(sum(values) - 100))
            record_sets.append(
                record_set(table, sheet, period, rows, grid, specs, annual_note)
            )
    assert largest_gap <= 2, (table.number, largest_gap)
    dimension_labels = {
        "desnz.qep.price_region": "QEP price region",
        "fuel": "Fuel",
        "payment_method": "Payment method",
    }
    value_labels = {
        "fuel": {table.fuel: table.fuel.capitalize()},
        "payment_method": {measure_id: words for measure_id, _, words in METHODS},
    }
    if table.metering:
        dimension_labels["metering_arrangement"] = "Metering arrangement"
        value_labels["metering_arrangement"] = {table.metering: table.metering_label}
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": table.package_id,
        "label": table.label,
        "dimension_labels": dimension_labels,
        "dimension_value_labels": value_labels,
        "artifact": {
            "source_name": "desnz",
            "source_table": f"Quarterly Energy Prices table {table.number}: "
            f"{table.cover_title[0].lower()}{table.cover_title[1:]}",
            "resource_package": "db",
            "resource_directory": f"data/{table.directory}",
            "manifest": "manifest.yaml",
            "vintage": "qep_2026_09_29",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": f"xlsx used-range cell parse ({entry['filename']})",
            "parser": "xlsx_used_range",
            "sheets": [quarterly, annual],
            "sheet_name": quarterly,
            "artifact_year": 2026,
        },
        "record_sets": record_sets,
    }
    facts = sum(len(rs["rows"]) * len(rs["measures"]) for rs in record_sets)
    regions = "the 14 former Public Electricity Supplier distribution areas" + (
        ", England and Wales, Scotland, Great Britain, Northern Ireland and the United Kingdom"
        if table.top == "K02000001"
        else ", England and Wales, Scotland and Great Britain (the table has no Northern "
        "Ireland or United Kingdom row)"
    )
    header = f"""
    DESNZ, Quarterly Energy Prices table {table.number}, '{table.cover_title}' (updated 29
    September 2026, data to the quarter ending June 2026, {PAGE}), for {ISSUE} item 12: a
    Direct Debit, standard credit and prepayment draw in Microcosm
    (PolicyEngine/uk-energy-price-cap-jan-2027#4), asked in PolicyEngine/chronicle#435 for
    Microcosm's next data PR. Written by {SCRIPT} from the pinned workbook.

    Ported: the percentage of domestic customers paying by standard credit, Direct Debit
    and prepayment, for {regions}, each quarter from April to June 2024 to April to June
    2026 (sheet '{quarterly}') and each year 2024 and 2025 (sheet '{annual}'). {table.scope}
    Payment method is a filter on concept {table.concept}; each region's three shares are
    the publisher's rounded percentages and add to 100 within {largest_gap} point(s). The
    shares come from DESNZ's quarterly survey of a sample of suppliers, 'uplifted to
    Ofgem's total customer numbers' (methodology sheet). Regions are the
    desnz:qep:pes ids the unit cost packages use. {annual_note}

    Not ported: earlier quarters and years, not asked in {ISSUE}; the fixed and online
    tariff sheets; and tables 2.4.1 and 2.5.1, which split customers by supplier type,
    not payment method. The next update is due 17 December 2026 (cover sheet). {facts}
    facts.
    """
    return render(header, payload)


BUILDERS = {
    table.directory: (lambda table=table: build_table(table)) for table in TABLES
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
