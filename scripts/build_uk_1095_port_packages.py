"""Author the chronicle#357 fact packages from their pinned publisher artifacts.

Microcosm's ports of the policyengine-uk-data wave (PolicyEngine/microcosm#1095)
wait for publisher facts. This script writes, from the bytes the manifests pin
under ``db/data``, nothing downloaded and no fact built:

- ``hmrc-stamp-tax-statistics-2024-25``: HMRC Annual Stamp Tax Statistics 2024 to
  2025 (the 11 March 2026 corrected tables), Tables 6b, 8a and 8b for both
  financial years the workbook carries, and for PolicyEngine/chronicle#408 item 5
  Tables 7, 3a, 5a, 9a and 9d for both years and the quarterly Table 2e.
- the OBR EFO March 2026 receipts package's sheet 3.7 lines, the EFO's only
  breakdown of SDLT receipts (by property type and rate, not by buyer).
- ``dwp-hbai-summary-fye2025``: Households Below Average Income, the FYE 2025
  release's median equivalised income and share of individuals in relative low
  income, before and after housing costs, for every year the release carries.
- ``dwp-hbai-uncertainty-fye2025``: the same release's 95% confidence intervals
  for those four FYE 2025 statistics (Tables 8a and 8b, inside the data-table ZIP).

Selectors are located by matching publisher text in the parsed source cells, and
every match is asserted, so a re-run against different bytes fails rather than
drifting.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from chronicle.sources.cells import (
    SourceArtifactMetadata,
    source_cells_from_ods,
    source_cells_from_xlsx,
)

ROOT = Path(__file__).resolve().parents[1]


class PackageDumper(yaml.SafeDumper):
    """Emit plain YAML with no anchors, so every record set reads alone."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def write_package(directory: Path, payload: dict, comment: str) -> None:
    """Write one package with its explanatory header."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "source_package.yaml").write_text(
        comment
        + yaml.dump(
            payload,
            Dumper=PackageDumper,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        ),
        encoding="utf-8",
    )


def constraint(variable: str, value: object, label: str, operator: str = "==") -> dict:
    """Carry a publisher classification as a first-class constraint."""
    return {"variable": variable, "operator": operator, "value": value, "label": label}


def fiscal_period(opening_year: int, label: str, notes: str) -> dict:
    """Stamp a UK financial year by its opening year, keeping the publisher label."""
    return {
        "period_type": "fiscal_year",
        "period": opening_year,
        "period_coverage": {
            "start_date": f"{opening_year}-04-01",
            "end_date": f"{opening_year + 1}-03-31",
            "basis": "fiscal",
            "source_period_label": label,
            "notes": notes,
        },
    }


def sheet_grid(cells: list, sheet: str) -> dict[tuple[int, str], object]:
    """Map (row, column letter) to the raw value of one parsed sheet."""
    grid = {}
    for cell in cells:
        if cell.sheet_name == sheet and cell.raw_value not in (None, ""):
            column = re.match(r"[A-Z]+", cell.address).group(0)
            grid[(cell.row_number, column)] = cell.raw_value
    assert grid, f"sheet {sheet!r} is empty or missing"
    return grid


def artifact_meta(path: Path) -> SourceArtifactMetadata:
    return SourceArtifactMetadata(
        source_name="x",
        source_table="x",
        source_file=path.name,
        url=None,
        vintage="x",
        sha256="0",
        size_bytes=0,
        extracted_at="x",
        extraction_method="x",
    )


# ----------------------------------------------------------------- HMRC stamps

STAMPS_PACKAGE = ROOT / "packages/hmrc/stamp_tax_statistics_2024_25"
STAMPS_DATA = ROOT / "db/data/hmrc/stamp_tax_statistics_2024_25"
STAMPS_ODS = "Annual_Stamps_2024_25_correction.ods"
STAMPS_PREFIX = "hmrc.stamp_taxes_2024_25"
STAMPS_URL = "https://www.gov.uk/government/statistics/uk-stamp-tax-statistics"
STAMPS_YEARS = ((2024, "2024-25"), (2023, "2023-24"))

ENGLAND_AND_NI = {
    "geography_id": "hmrc:england_and_northern_ireland",
    "geography_level": "statistical_scope",
    "geography_name": "England and Northern Ireland",
    "geography_vintage": "current",
}

# Publisher price-band label, slug, display label. The 8a/8b bands stop at
# "More than GBP 2,000,000"; 6b carries five bands above GBP 2 million.
BANDS_8 = (
    ("£250,000 or less", "gbp_250k_or_less", "GBP 250,000 or less"),
    ("£250,001 to £500,000", "gbp_250k_to_500k", "GBP 250,001 to GBP 500,000"),
    ("£500,001 to £1,000,000", "gbp_500k_to_1m", "GBP 500,001 to GBP 1,000,000"),
    ("£1,000,001 to £1,500,000", "gbp_1m_to_1_5m", "GBP 1,000,001 to GBP 1,500,000"),
    ("£1,500,001 to £2,000,000", "gbp_1_5m_to_2m", "GBP 1,500,001 to GBP 2,000,000"),
    ("More than £2,000,000", "over_gbp_2m", "More than GBP 2,000,000"),
)
BANDS_6B = BANDS_8[:5] + (
    ("£2,000,001 to £3,000,000", "gbp_2m_to_3m", "GBP 2,000,001 to GBP 3,000,000"),
    ("£3,000,001 to £4,000,000", "gbp_3m_to_4m", "GBP 3,000,001 to GBP 4,000,000"),
    ("£4,000,001 to £5,000,000", "gbp_4m_to_5m", "GBP 4,000,001 to GBP 5,000,000"),
    ("£5,000,001 to £10,000,000", "gbp_5m_to_10m", "GBP 5,000,001 to GBP 10,000,000"),
    ("More than £10,000,000", "over_gbp_10m", "More than GBP 10,000,000"),
)
CORPORATE_FLAT_RATE = (
    "Corporate bodies paying flat rate",
    "corporate_bodies_flat_rate",
    "Corporate bodies paying flat rate",
)
ALL_BANDS = "All price bands"

BUYERS = (
    # (header prefix for the three columns, filter value or None, label)
    ("individuals", "individuals", "Individuals"),
    ("other buyers", "other_buyers", "Other buyers"),
    ("all buyers", None, "All buyers"),
)
STAMP_MEASURES_8 = (
    # (header template, measure id, concept, unit, scale)
    (
        "Transactions {by} {buyers}",
        "transactions",
        "hmrc.sdlt.transactions",
        "count",
        None,
    ),
    (
        "Property value for {buyers}",
        "property_value",
        "hmrc.sdlt.property_value",
        "gbp",
        1e6,
    ),
    ("Receipts for {buyers}", "receipts", "hmrc.sdlt.receipts", "gbp", 1e6),
)
UNIVERSE = constraint(
    "sdlt_chargeable_consideration",
    40000,
    "Transactions at GBP 40,000 or above",
    operator=">=",
)
ROUNDING = (
    "Rounded as published: transactions to the nearest 100, property values and "
    "receipts to the nearest GBP 5 million, so bands need not sum to the total "
    "(sheet notes). Transactions at GBP 40,000 or above, England and Northern "
    "Ireland. [X] cells (fewer than 50 transactions, under GBP 2.5 million or not "
    "available) emit no fact."
)


def stamp_band_rows(grid, bands, first_row, header_column="A", corporate=False):
    """Rows for the all-bands total, each band and (8a) the corporate flat rate."""
    expected = [ALL_BANDS] + [label for label, _, _ in bands]
    if corporate:
        expected.append(CORPORATE_FLAT_RATE[0])
    labels = [grid.get((first_row + i, header_column)) for i in range(len(expected))]
    assert labels == expected, labels
    rows = [
        {
            "value_id": "all_price_bands",
            "label": ALL_BANDS,
            "ordinal": 0,
            "row_number": first_row,
            "expected_row_header_column": header_column,
            "expected_row_header": ALL_BANDS,
            "table_record_kind": "total",
        }
    ]
    members = list(bands) + ([CORPORATE_FLAT_RATE] if corporate else [])
    for offset, (label, slug, display) in enumerate(members, start=1):
        rows.append(
            {
                "value_id": slug,
                "label": display,
                "ordinal": offset,
                "row_number": first_row + offset,
                "expected_row_header_column": header_column,
                "expected_row_header": label,
                "table_record_kind": "detail",
                "filters": {"sdlt_price_band": slug},
                "constraints": [constraint("sdlt_price_band", slug, "SDLT price band")],
            }
        )
    return rows


def stamp_record_set(record_set_id, sheet, opening_year, label, extra):
    payload = {
        "record_set_id": record_set_id,
        "provenance_class": "administrative",
        "assertion": "observation",
        "record_set_spec_id": f"{record_set_id}.v1",
        "source_record_id_prefix": record_set_id,
        "sheet_name": sheet,
        **fiscal_period(
            opening_year,
            label,
            "Financial year ending in March; period.value stores the opening year.",
        ),
        **ENGLAND_AND_NI,
        "entity": "return",
        "entity_role": "sdlt_land_transaction",
        "domain": "stamp_duty_land_tax",
        "groupby_dimension": "sdlt_price_band",
    }
    payload.update(extra)
    return payload


# PolicyEngine/chronicle#408 item 5: Tables 7, 3a, 5a, 9a and 9d for both financial
# years, and the quarterly Table 2e.

STAMP_DIMENSION_LABELS = {
    "sdlt_price_band": "SDLT price band",
    "sdlt_property_type": "SDLT property type",
    "sdlt_buyer_type": "Type of buyer",
    "sdlt_higher_rates": "SDLT higher rates",
    "sdlt_purchaser_age_band": "Age of the first-listed purchaser",
    "sdlt_ftbr_liability": "First Time Buyers' Relief claim liability",
    "sdlt_corporate_flat_rate": "Corporate bodies paying the flat rate",
    "hmrc.sdlt_country_region": "Country/Region",
    "hmrc.sdlt_quarter": "Year/Quarter",
}
ENGLAND = {
    "geography_id": "E92000001",
    "geography_level": "country",
    "geography_name": "England",
    "geography_vintage": "current",
}
NORTHERN_IRELAND = {
    "geography_id": "N92000002",
    "geography_level": "country",
    "geography_name": "Northern Ireland",
    "geography_vintage": "current",
}
# SDLT applied in Wales until the Land Transaction Tax replaced it on 1 April 2018.
ENGLAND_WALES_AND_NI = {
    "geography_id": "hmrc:england_wales_and_northern_ireland",
    "geography_level": "statistical_scope",
    "geography_name": "England, Wales and Northern Ireland",
    "geography_vintage": "current",
}
# Country/Region rows of Tables 3a, 5a and 9a: printed name, printed code, geography.
STAMP_AREAS = (
    ("All countries", "[X]", ENGLAND_AND_NI),
    ("England", "E92000001", ENGLAND),
    *(
        (
            name,
            code,
            {
                "geography_id": code,
                "geography_level": "region",
                "geography_name": name,
                "geography_vintage": "current",
            },
        )
        for name, code in (
            ("North East", "E12000001"),
            ("North West", "E12000002"),
            ("Yorkshire and The Humber", "E12000003"),
            ("East Midlands", "E12000004"),
            ("West Midlands", "E12000005"),
            ("East of England", "E12000006"),
            ("London", "E12000007"),
            ("South East", "E12000008"),
            ("South West", "E12000009"),
        )
    ),
    ("Northern Ireland", "N92000002", NORTHERN_IRELAND),
)
# Age of the first-listed purchaser (Tables 7 and 9d): printed label, slug, display.
AGE_BANDS = tuple(
    (label, f"age_{label.lower().replace(' ', '_')}", f"Aged {label.lower()}")
    for label in (
        "0 to 19",
        "20 to 24",
        "25 to 29",
        "30 to 34",
        "35 to 39",
        "40 to 44",
        "45 to 49",
        "50 to 54",
        "55 to 59",
        "60 to 64",
        "65 to 69",
        "70 to 74",
        "75 to 79",
        "Over 79",
    )
) + (("Unknown", "age_unknown", "Age unknown"),)
AGE_COLUMNS = "BCDEFGHIJKLMNOP"
FTBR_LIABILITY = {"exempt": "Exempt transactions", "liable": "Liable transactions"}
CORPORATE_IN_BANDS = "included_in_price_bands"
EDITION = "HMRC Annual Stamp Tax Statistics 2024 to 2025 (corrected 11 March 2026)"
FTBR_2022_THRESHOLDS = (
    "In most cases exempt transactions correspond to purchases below £425,000 and "
    "liable transactions to claims for properties valued between £425,000 and "
    "£625,000 (sheet notes), the thresholds in force from 23 September 2022 to 31 March "
    "2025 (Table 2e notes)."
)


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def stamp_measure(
    measure_id,
    label,
    column,
    header,
    header_row,
    concept,
    unit,
    notes,
    *,
    ordinal,
    scale=None,
    aggregation="sum",
    filters=None,
):
    measure = {
        "measure_id": measure_id,
        "label": label,
        "ordinal": ordinal,
        "column": column,
        "source_column_id": measure_id,
    }
    if filters:
        measure["source_column_dimensions"] = dict(filters)
    measure.update(
        {
            "expected_column_header_row": header_row,
            "expected_column_header": header,
            "concept": concept,
            "source_concept": concept,
            "concept_relation": "source_label",
            "concept_authority": "hmrc",
            "concept_evidence_url": STAMPS_URL,
            "concept_evidence_notes": notes,
            "unit": unit,
            "aggregation": aggregation,
        }
    )
    if filters:
        measure["filters"] = dict(filters)
        measure["constraints"] = [
            constraint(key, value, STAMP_DIMENSION_LABELS[key])
            for key, value in filters.items()
        ]
    measure["expected_cell_type"] = "number"
    if scale:
        measure["value_scale"] = int(scale)
    return measure


def stamp_shared(filters: dict, universe: bool = True) -> dict:
    """Shared filters and constraints, with the GBP 40,000 universe first."""
    constraints = [UNIVERSE] if universe else []
    constraints += [
        constraint(key, value, STAMP_DIMENSION_LABELS[key])
        for key, value in filters.items()
    ]
    shared = {"shared_constraints": constraints}
    if filters:
        shared = {"shared_filters": dict(filters), **shared}
    return shared


def stamp_area_rows(grid: dict, first_row: int, *, all_countries: bool) -> list[dict]:
    """The Country/Region rows, England's regions inside England, as printed."""
    rows = []
    for offset, (name, code, geography) in enumerate(STAMP_AREAS):
        row = first_row + offset
        assert (grid.get((row, "A")), grid.get((row, "B"))) == (name, code), row
        if code == "[X]" and not all_countries:
            continue
        spec = {
            "value_id": re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"),
            "label": name,
            "ordinal": len(rows),
            "row_number": row,
            "expected_row_header_column": "A",
            "expected_row_header": name,
            **geography,
            "table_record_kind": "total",
        }
        if code != "[X]":
            spec["guard_cells"] = [
                {
                    "column": "B",
                    "row": row,
                    "expected_value": code,
                    "label": "Country/Region Code",
                }
            ]
        rows.append(spec)
    assert grid.get((first_row + len(STAMP_AREAS), "A")) == "End of worksheet"
    return rows


def printed_record_sets(
    record_set_id, rows, measures, grid, title, make, extra_guards=()
):
    """One record set for the rows that print every measure, and one per other pattern.

    An [X] cell (fewer than 50 transactions, under the value threshold or not
    available) emits no fact, so a row carries only the measures it prints. Rows that
    print every measure keep the plain record set id; each other pattern of printed
    measures gets ``<id>.subset_<n>`` with only those measures, and a row that prints
    none is left out. The first row of each record set guards the table title, and
    any ``extra_guards``.
    """
    patterns: dict[tuple[str, ...], list[dict]] = {}
    for row in rows:
        printed = []
        for measure in measures:
            value = grid.get((row["row_number"], measure["column"]))
            if is_number(value):
                printed.append(measure["measure_id"])
            else:
                assert value == "[X]", (record_set_id, row["value_id"], value)
        if printed:
            patterns.setdefault(tuple(printed), []).append(row)
    every = tuple(measure["measure_id"] for measure in measures)
    ordered = sorted(
        patterns.items(),
        key=lambda item: (item[0] != every, item[1][0]["row_number"]),
    )
    record_sets = []
    for number, (printed, members) in enumerate(ordered):
        suffix = "" if printed == every else f".subset_{number}"
        kept_rows = []
        for ordinal, row in enumerate(members):
            row = dict(row, ordinal=ordinal)
            if ordinal == 0:
                row["guard_cells"] = (
                    [
                        {
                            "column": "A",
                            "row": 1,
                            "expected_value": title,
                            "label": "table title",
                        }
                    ]
                    + list(extra_guards)
                    + row.get("guard_cells", [])
                )
            kept_rows.append(row)
        kept_measures = [
            dict(measure, ordinal=ordinal)
            for ordinal, measure in enumerate(
                m for m in measures if m["measure_id"] in printed
            )
        ]
        record_sets.append(make(f"{record_set_id}{suffix}", kept_rows, kept_measures))
    return record_sets


def stamp_table_7(cells, opening_year, label) -> list[dict]:
    """Individuals' residential purchases by the first-listed purchaser's age band."""
    sheet = f"Table_7_({label})"
    grid = sheet_grid(cells, sheet)
    title = grid[(1, "A")]
    assert title == (
        f"Table 7 {label}: Age bands by property price band for residential purchases "
        "by individuals."
    ), title
    assert grid[(5, "A")] == (
        "Transactions are rounded to the nearest 100. Percentages are rounded to the "
        "nearest 1%."
    )
    assert grid[(8, "A")] == "Price bands"
    suffix = " transactions" if opening_year == 2023 else ""
    all_ages = grid[(8, "Q")]
    assert all_ages == f"All ages{suffix}", all_ages
    rows = stamp_band_rows(grid, BANDS_8, 9)
    # 'All ages' (column Q) restates Table 8a's individuals: exactly in 2023-24, and
    # to 8a's rounding in 2024-25, where it is also the exact sum of the age columns.
    table_8a = sheet_grid(cells, f"Table_8a_({label})")
    for offset in range(len(rows)):
        printed, restated = grid[(9 + offset, "Q")], table_8a[(8 + offset, "B")]
        assert abs(printed - restated) <= 50, (sheet, offset, printed, restated)
        if opening_year == 2024:
            assert printed == sum(grid[(9 + offset, c)] for c in AGE_COLUMNS)
    notes = (
        f"{EDITION}, {sheet} (row 8 header '{{header}}'): residential SDLT "
        "transactions purchased by individuals at £40,000 or above, by the age of the "
        "first-listed purchaser ('Ages are based on the first listed purchaser'). The "
        "sheet notes 'Transactions are rounded to the nearest 100'"
        + (
            "; this sheet prints unrounded counts, including counts under 50 that "
            "its [X] note would withhold, and they are stored as printed. "
            if opening_year == 2024
            else ". "
        )
        + "[X] cells (fewer than 50 transactions or not available) emit no fact."
    )
    measures = [
        stamp_measure(
            f"transactions_{slug}",
            f"Residential transactions by individuals, first-listed purchaser "
            f"{display.lower()}, {label}",
            column,
            f"{printed}{suffix}",
            8,
            "hmrc.sdlt.transactions",
            "count",
            notes.format(header=f"{printed}{suffix}"),
            ordinal=ordinal,
            filters={"sdlt_purchaser_age_band": slug},
        )
        for ordinal, ((printed, slug, display), column) in enumerate(
            zip(AGE_BANDS, AGE_COLUMNS)
        )
    ]
    for measure in measures:
        assert grid[(8, measure["column"])] == measure["expected_column_header"]
    return printed_record_sets(
        f"{STAMPS_PREFIX}.table_7.individuals.fy{opening_year}",
        rows,
        measures,
        grid,
        title,
        lambda record_set_id, kept_rows, kept_measures: stamp_record_set(
            record_set_id,
            sheet,
            opening_year,
            label,
            {
                **stamp_shared(
                    {
                        "sdlt_property_type": "residential",
                        "sdlt_buyer_type": "individuals",
                    }
                ),
                "rows": kept_rows,
                "measures": kept_measures,
            },
        ),
    )


def stamp_table_3a(cells, opening_year, label) -> list[dict]:
    """Transactions, property value and receipts by property type and area."""
    sheet = f"Table_3a_({label})"
    grid = sheet_grid(cells, sheet)
    title = grid[(1, "A")]
    assert title == (
        f"Table 3a {label}: Stamp Duty Land Tax (SDLT) transactions and receipts by "
        "property type and by country and within England, region."
    ), title
    assert grid[(4, "A")] == (
        "Property values and receipts are shown in millions and rounded to the nearest "
        "£5 million."
    )
    table_8 = {
        table: sheet_grid(cells, f"Table_{table}_({label})") for table in ("8a", "8b")
    }
    record_sets = []
    for property_type, words, columns in (
        ("residential", "Residential", "CDE"),
        ("non_residential", "Non-residential", "FGH"),
        (None, "Total", "IJK"),
    ):
        if property_type:
            # The All countries row restates Table 8a's or 8b's all-buyer totals (to
            # 8a's and 8b's rounding of transactions to the nearest 100).
            restated = table_8["8a" if property_type == "residential" else "8b"]
            for column, column_8 in zip(columns, "HIJ"):
                assert abs(grid[(7, column)] - restated[(8, column_8)]) <= 50
        else:
            for column, left, right in zip(columns, "CDE", "FGH"):
                assert abs(grid[(7, column)] - grid[(7, left)] - grid[(7, right)]) <= 10
        rows = stamp_area_rows(grid, 7, all_countries=property_type is None)
        measures = []
        for ordinal, (
            (measure_id, concept, unit, scale, words_after),
            column,
        ) in enumerate(
            zip(
                (
                    (
                        "transactions",
                        "hmrc.sdlt.transactions",
                        "count",
                        None,
                        "transactions",
                    ),
                    (
                        "property_value",
                        "hmrc.sdlt.property_value",
                        "gbp",
                        1e6,
                        "property value",
                    ),
                    ("receipts", "hmrc.sdlt.receipts", "gbp", 1e6, "receipts"),
                ),
                columns,
            )
        ):
            header = f"{words} {words_after}"
            assert grid[(6, column)] == header, (sheet, column, grid[(6, column)])
            measures.append(
                stamp_measure(
                    measure_id,
                    f"{header}, {label}",
                    column,
                    header,
                    6,
                    concept,
                    unit,
                    f"{EDITION}, {sheet}, column {column} ('{header}'): SDLT "
                    "transactions at £40,000 or above, estimated property value and net "
                    "receipts by property type, by country and within England, region "
                    "(sheet note). Property values and receipts are in millions, rounded "
                    "to the nearest £5 million; the sheet states no rounding for "
                    "transactions and they are stored as printed. 'All countries' is "
                    "England and Northern Ireland, where SDLT applies; its residential "
                    "and non-residential cells restate Tables 8a and 8b's all-buyer "
                    "totals and are not ported again.",
                    ordinal=ordinal,
                    scale=scale,
                )
            )
        for row in rows:
            for measure in measures:
                assert is_number(grid[(row["row_number"], measure["column"])])
        rows[0]["guard_cells"] = [
            {"column": "A", "row": 1, "expected_value": title, "label": "table title"}
        ] + rows[0].get("guard_cells", [])
        record_sets.append(
            stamp_record_set(
                f"{STAMPS_PREFIX}.table_3a.{property_type or 'all_property_types'}"
                f".fy{opening_year}",
                sheet,
                opening_year,
                label,
                {
                    "groupby_dimension": "hmrc.sdlt_country_region",
                    **stamp_shared(
                        {"sdlt_property_type": property_type} if property_type else {}
                    ),
                    "rows": rows,
                    "measures": measures,
                },
            )
        )
    return record_sets


def stamp_table_5a(cells, opening_year, label) -> list[dict]:
    """Residential SDLT by price band and area; the bands include corporate bodies
    paying the flat rate, which Table 8a reports on a row of its own."""
    sheet = f"Table_5a_({label})"
    grid = sheet_grid(cells, sheet)
    title = grid[(1, "A")]
    # The 2024-25 sheet's title (and its contents entry) say 2023-24; its own note
    # says 2024-25, and its totals are Table 8a's 2024-25 totals.
    assert title == (
        "Table 5a 2023-24: Stamp Duty Land Tax (SDLT) transactions and receipts for "
        "residential property by price band and by country and within England, region."
    ), title
    assert grid[(3, "A")] == (
        "This table shows residential SDLT transactions at £40,000 or above, estimated "
        "property value and net receipts by price band and by country and within "
        f"England, region for {label}."
    )
    assert grid[(5, "A")] == (
        "Property values and receipts are shown in millions and rounded to the nearest "
        "£5 million. Transactions are rounded to the nearest 100."
    )
    assert grid[(8, "A")] == "Country/Region"
    table_8a = sheet_grid(cells, f"Table_8a_({label})")
    table_3a = sheet_grid(cells, f"Table_3a_({label})")
    assert [grid[(9, c)] for c in "UVW"] == [table_8a[(8, c)] for c in "HIJ"]
    # 'All price bands' (U to W) restates Table 3a's residential columns, area by area
    # (to the nearest 100 transactions; 3a's 2023-24 transactions print to the 10).
    for offset in range(len(STAMP_AREAS)):
        for column, column_3a in zip("UVW", "CDE"):
            assert (
                abs(grid[(9 + offset, column)] - table_3a[(7 + offset, column_3a)])
                <= 50
            )
    # Above GBP 500,000 the all-countries bands exceed Table 8a's by its corporate
    # flat-rate row: property value by exactly that row's in 2024-25.
    excess = [
        sum(
            grid[(9, "CDEFGHIJKLMNOPQRST"[3 * band + measure])]
            - table_8a[(9 + band, "HIJ"[measure])]
            for band in range(len(BANDS_8))
        )
        for measure in range(3)
    ]
    corporate = [table_8a[(15, c)] for c in "HIJ"]
    assert table_8a[(15, "A")] == CORPORATE_FLAT_RATE[0]
    assert all(abs(e - c) <= 100 for e, c in zip(excess, corporate)), (
        excess,
        corporate,
    )
    rows = stamp_area_rows(grid, 9, all_countries=True)
    record_sets = []
    for band, (printed_band, slug, display) in enumerate(BANDS_8):
        columns = "CDEFGHIJKLMNOPQRST"[3 * band : 3 * band + 3]
        measures = []
        for ordinal, ((measure_id, concept, unit, scale, code), column) in enumerate(
            zip(
                (
                    ("transactions", "hmrc.sdlt.transactions", "count", None, "T"),
                    ("property_value", "hmrc.sdlt.property_value", "gbp", 1e6, "P"),
                    ("receipts", "hmrc.sdlt.receipts", "gbp", 1e6, "Re"),
                ),
                columns,
            )
        ):
            header = f"{printed_band} ({code})"
            assert grid[(8, column)] == header, (sheet, column, grid[(8, column)])
            measures.append(
                stamp_measure(
                    measure_id,
                    f"Residential SDLT {measure_id.replace('_', ' ')}, {display}, "
                    f"{label}",
                    column,
                    header,
                    8,
                    concept,
                    unit,
                    f"{EDITION}, {sheet}, column {column} ('{header}'): residential "
                    "SDLT transactions at £40,000 or above, estimated property value and "
                    "net receipts by price band, by country and within England, region "
                    "(sheet note). Property values and receipts in millions, rounded to "
                    "the nearest £5 million; transactions to the nearest 100. Above "
                    "£500,000 the bands include corporate bodies paying the flat rate, "
                    "which Table 8a reports on a row of its own: the all-countries bands "
                    "exceed 8a's by that row's property value and receipts. [X] cells "
                    "(fewer than 50 transactions, under £2.5 million or not available) "
                    "emit no fact."
                    + (
                        " The sheet's title and its contents entry say 2023-24; its own "
                        "note says 2024-25 and its totals are Table 8a's 2024-25 totals, "
                        "so the period is 2024-25."
                        if opening_year == 2024
                        else ""
                    ),
                    ordinal=ordinal,
                    scale=scale,
                )
            )
        record_sets += printed_record_sets(
            f"{STAMPS_PREFIX}.table_5a.{slug}.fy{opening_year}",
            rows,
            measures,
            grid,
            title,
            lambda record_set_id, kept_rows, kept_measures, slug=slug: stamp_record_set(
                record_set_id,
                sheet,
                opening_year,
                label,
                {
                    "groupby_dimension": "hmrc.sdlt_country_region",
                    **stamp_shared(
                        {
                            "sdlt_property_type": "residential",
                            "sdlt_price_band": slug,
                            "sdlt_corporate_flat_rate": CORPORATE_IN_BANDS,
                        }
                    ),
                    "rows": kept_rows,
                    "measures": kept_measures,
                },
            ),
            # The note that states the period (the title does not, in 2024-25).
            extra_guards=[
                {
                    "column": "A",
                    "row": 3,
                    "expected_value": grid[(3, "A")],
                    "label": "table note",
                }
            ],
        )
    return record_sets


FTBR_MEASURES = (
    # (column, header, measure id, concept, unit, scale, aggregation, liability)
    (
        "C",
        "Amount relieved",
        "ftbr_amount_relieved",
        "hmrc.sdlt.ftbr_amount_relieved",
        "gbp",
        1e6,
        "sum",
        None,
    ),
    (
        "D",
        "Number of transactions",
        "ftbr_claims",
        "hmrc.sdlt.ftbr_claims",
        "count",
        None,
        "sum",
        None,
    ),
    (
        "E",
        "Average FTBR claimed",
        "ftbr_average_amount_relieved",
        "hmrc.sdlt.ftbr_average_amount_relieved",
        "gbp",
        None,
        "mean",
        None,
    ),
    (
        "F",
        "Exempt Transactions",
        "ftbr_claims_exempt",
        "hmrc.sdlt.ftbr_claims",
        "count",
        None,
        "sum",
        "exempt",
    ),
    (
        "G",
        "Liable transactions",
        "ftbr_claims_liable",
        "hmrc.sdlt.ftbr_claims",
        "count",
        None,
        "sum",
        "liable",
    ),
)


def stamp_table_9a(cells, opening_year, label) -> dict:
    """First Time Buyers' Relief claims by country and, within England, region."""
    sheet = f"Table_9a_({label})"
    grid = sheet_grid(cells, sheet)
    title = grid[(1, "A")]
    assert title == (
        f"Table 9a {label}: First Time Buyers' Relief (FTBR) claims by region."
    ), title
    assert grid[(7, "A")] == (
        "Estimated amounts relieved are shown in millions and rounded to the nearest £1 "
        "million. Transactions are rounded to the nearest 100. Average value to the "
        "nearest £100. Percentages are rounded to the nearest 1%."
    )
    assert grid[(10, "H")] == "FTBR percentage"
    rows = stamp_area_rows(grid, 11, all_countries=True)
    measures = []
    for ordinal, (
        column,
        header,
        measure_id,
        concept,
        unit,
        scale,
        aggregation,
        liability,
    ) in enumerate(FTBR_MEASURES):
        assert grid[(10, column)] == header, (sheet, column, grid[(10, column)])
        measures.append(
            stamp_measure(
                measure_id,
                f"First Time Buyers' Relief: {header.lower()}, {label}",
                column,
                header,
                10,
                concept,
                unit,
                f"{EDITION}, {sheet}, column {column} ('{header}'): residential "
                "transactions at £40,000 or above claiming First Time Buyers' Relief, "
                "by country and within England, region (sheet note). Amounts relieved "
                "are estimates in millions, rounded to the nearest £1 million; "
                "transactions to the nearest 100; the average to the nearest £100. "
                f"{FTBR_2022_THRESHOLDS} The FTBR percentage (column H, text that "
                "divides published counts) is not ported.",
                ordinal=ordinal,
                scale=scale,
                aggregation=aggregation,
                filters={"sdlt_ftbr_liability": liability} if liability else None,
            )
        )
    for row in rows:
        for measure in measures:
            assert is_number(grid[(row["row_number"], measure["column"])])
    rows[0]["guard_cells"] = [
        {"column": "A", "row": 1, "expected_value": title, "label": "table title"}
    ] + rows[0].get("guard_cells", [])
    return stamp_record_set(
        f"{STAMPS_PREFIX}.table_9a.ftbr.fy{opening_year}",
        sheet,
        opening_year,
        label,
        {
            "groupby_dimension": "hmrc.sdlt_country_region",
            **stamp_shared({"sdlt_property_type": "residential"}),
            "rows": rows,
            "measures": measures,
        },
    )


def stamp_table_9d(cells, opening_year, label) -> list[dict]:
    """First Time Buyers' Relief claims by the first-listed purchaser's age band."""
    sheet = f"Table_9d_({label})"
    grid = sheet_grid(cells, sheet)
    title = grid[(1, "A")]
    assert title == (
        f"Table 9d {label}: First Time Buyers' Relief (FTBR) claims by age."
    ), title
    assert grid[(6, "A")] == "Transactions are rounded to the nearest 100."
    assert grid[(9, "A")] == "Age bands (Years, inclusive)"
    assert grid[(9, "Q")] == "All ages"
    # 'All ages' (column Q) restates Table 9a's all-countries claims, exempt and liable.
    table_9a = sheet_grid(cells, f"Table_9a_({label})")
    assert [grid[(row, "Q")] for row in (10, 11, 12)] == [
        table_9a[(11, column)] for column in "DFG"
    ]
    rows = []
    for ordinal, (row, printed, liability) in enumerate(
        ((10, "Total", None), (11, "Exempt", "exempt"), (12, "Liable", "liable"))
    ):
        assert grid[(row, "A")] == printed
        spec = {
            "value_id": printed.lower(),
            "label": FTBR_LIABILITY[liability] if liability else "All FTBR claims",
            "ordinal": ordinal,
            "row_number": row,
            "expected_row_header_column": "A",
            "expected_row_header": printed,
            "table_record_kind": "detail" if liability else "total",
        }
        if liability:
            spec["filters"] = {"sdlt_ftbr_liability": liability}
            spec["constraints"] = [
                constraint(
                    "sdlt_ftbr_liability",
                    liability,
                    STAMP_DIMENSION_LABELS["sdlt_ftbr_liability"],
                )
            ]
        rows.append(spec)
    assert grid[(13, "A")] == "End of worksheet"
    measures = []
    for ordinal, ((printed, slug, display), column) in enumerate(
        zip(AGE_BANDS, AGE_COLUMNS)
    ):
        assert grid[(9, column)] == printed, (sheet, column, grid[(9, column)])
        measures.append(
            stamp_measure(
                f"ftbr_claims_{slug}",
                f"First Time Buyers' Relief claims, first-listed purchaser "
                f"{display.lower()}, {label}",
                column,
                printed,
                9,
                "hmrc.sdlt.ftbr_claims",
                "count",
                f"{EDITION}, {sheet}, column {column} ('{printed}'): residential SDLT "
                "transactions purchased by individuals claiming First Time Buyers' "
                "Relief, by age band (years, inclusive), in total and split into "
                "exempt and liable claims; transactions rounded to the nearest 100. "
                f"{FTBR_2022_THRESHOLDS} The table's totals are Table 9a's, which "
                "counts transactions at £40,000 or above, and its 'All ages' column "
                "restates them and is not ported again. [X] cells (fewer than 50 "
                "transactions or not available) emit no fact.",
                ordinal=ordinal,
                filters={"sdlt_purchaser_age_band": slug},
            )
        )
    return printed_record_sets(
        f"{STAMPS_PREFIX}.table_9d.ftbr.fy{opening_year}",
        rows,
        measures,
        grid,
        title,
        lambda record_set_id, kept_rows, kept_measures: stamp_record_set(
            record_set_id,
            sheet,
            opening_year,
            label,
            {
                "groupby_dimension": "sdlt_ftbr_liability",
                **stamp_shared(
                    {
                        "sdlt_property_type": "residential",
                        "sdlt_buyer_type": "individuals",
                    }
                ),
                "rows": kept_rows,
                "measures": kept_measures,
            },
        ),
    )


QUARTER_MONTHS = {
    1: ("01-01", "03-31"),
    2: ("04-01", "06-30"),
    3: ("07-01", "09-30"),
    4: ("10-01", "12-31"),
}


def ftbr_quarter_notes(year: int, quarter: int) -> str:
    """The relief's thresholds (Table 2e notes) in force during a quarter."""
    if (year, quarter) <= (2022, 2):
        thresholds = (
            "zero rate threshold £300,000 and maximum price £500,000, in force from 22 "
            "November 2017 to 22 September 2022"
        )
    elif (year, quarter) == (2022, 3):
        thresholds = (
            "zero rate threshold £300,000 and maximum price £500,000 to 22 September "
            "2022, and £425,000 and £625,000 from 23 September 2022"
        )
    else:
        thresholds = (
            "zero rate threshold £425,000 and maximum price £625,000, in force from 23 "
            "September 2022 to 31 March 2025"
        )
    notes = (
        "In most cases exempt transactions are purchases below the zero rate threshold "
        "and liable transactions claims above it but below the maximum price (sheet "
        f"notes): this quarter, {thresholds}."
    )
    if (year, quarter) == (2017, 4):
        notes += " The relief starts on 22 November 2017."
    if (year, quarter) == (2020, 3):
        notes += (
            " The residential SDLT holiday from 8 July 2020 to 30 June 2021 meant there "
            "was no requirement to claim the relief."
        )
    return notes


def stamp_table_2e(cells) -> list[dict]:
    """Quarterly First Time Buyers' Relief claims, 2017 Q4 to 2025 Q1."""
    sheet = "Table_2e"
    grid = sheet_grid(cells, sheet)
    title = grid[(1, "A")]
    assert title == (
        "Table 2e: Quarterly First Time Buyers' Relief (FTBR) claims by Price Band from "
        "2017 Q4 to 2025 Q1"
    ), title
    assert grid[(4, "A")].endswith(
        "From 22 Nov 2017 to 22 Sep 2022 this was £300,000. From 23 Sep 2022 to 31 Mar "
        "2025 this was £425,000"
    )
    assert grid[(5, "A")].endswith(
        "From 22 Nov 2017 to 22 Sep 2022 this was £500,000. From 23 Sep 2022 to 31 Mar "
        "2025 this was £625,000"
    )
    assert grid[(8, "A")] == (
        "Land transaction taxes were devolved in Scotland in April 2015 and in Wales in "
        "April 2018."
    )
    headers = {
        "B": "Estimated amount relieved",
        "C": "Number of FTBR claims",
        "D": "Exempt transactions",
        "E": "Liable transactions",
        "F": "FTBR transactions as a percentage of residential transactions",
    }
    assert {column: grid[(11, column)] for column in headers} == headers
    record_sets = []
    row = 12
    while grid[(row, "A")] != "End of worksheet":
        printed = grid[(row, "A")]
        match = re.fullmatch(r"(\d{4}) Q([1-4])", printed)
        assert match, printed
        year, quarter = int(match.group(1)), int(match.group(2))
        values = [grid[(row, column)] for column in "BCDEF"]
        if values == ["[X]"] * 5:
            # 2020 Q4 to 2021 Q2: the SDLT holiday (sheet notes).
            assert (2020, 4) <= (year, quarter) <= (2021, 2), printed
            row += 1
            continue
        assert all(is_number(value) for value in values[:4]), (printed, values)
        start, end = QUARTER_MONTHS[quarter]
        before_ltt = (year, quarter) < (2018, 2)
        notes = (
            f"{EDITION}, {sheet}, row '{printed}': residential transactions at £40,000 "
            "or above benefiting from First Time Buyers' Relief, by quarter, in total "
            "and split into exempt and liable claims; despite the table's title it is "
            "not split by price band. Amounts relieved are estimates in millions, "
            "rounded to the nearest £1 million; claims to the nearest 100, except that "
            "2024 Q2 to 2025 Q1 print unrounded, fractional claims, stored as printed. "
            f"{ftbr_quarter_notes(year, quarter)} The percentage of residential "
            "transactions (column F, text that divides published counts) is not ported."
            + (
                " Before April 2018 SDLT also applied in Wales (sheet note: land "
                "transaction taxes were devolved in Wales in April 2018)."
                if before_ltt
                else ""
            )
        )
        measures = [
            stamp_measure(
                measure_id,
                f"First Time Buyers' Relief: {headers[column].lower()}, {printed}",
                column,
                headers[column],
                11,
                concept,
                unit,
                notes,
                ordinal=ordinal,
                scale=scale,
                filters={"sdlt_ftbr_liability": liability} if liability else None,
            )
            for ordinal, (
                column,
                measure_id,
                concept,
                unit,
                scale,
                liability,
            ) in enumerate(
                (
                    (
                        "B",
                        "ftbr_amount_relieved",
                        "hmrc.sdlt.ftbr_amount_relieved",
                        "gbp",
                        1e6,
                        None,
                    ),
                    ("C", "ftbr_claims", "hmrc.sdlt.ftbr_claims", "count", None, None),
                    (
                        "D",
                        "ftbr_claims_exempt",
                        "hmrc.sdlt.ftbr_claims",
                        "count",
                        None,
                        "exempt",
                    ),
                    (
                        "E",
                        "ftbr_claims_liable",
                        "hmrc.sdlt.ftbr_claims",
                        "count",
                        None,
                        "liable",
                    ),
                )
            )
        ]
        record_sets.append(
            stamp_record_set(
                f"{STAMPS_PREFIX}.table_2e.ftbr.{year}_q{quarter}",
                sheet,
                year,
                printed,
                {
                    "period_type": "quarter",
                    "period": f"{year}-Q{quarter}",
                    "period_coverage": {
                        "start_date": f"{year}-{start}",
                        "end_date": f"{year}-{end}",
                        "basis": "calendar",
                        "source_period_label": printed,
                        "notes": "Calendar quarter (Q1 is January to March).",
                    },
                    **(ENGLAND_WALES_AND_NI if before_ltt else {}),
                    "groupby_dimension": "hmrc.sdlt_quarter",
                    **stamp_shared({"sdlt_property_type": "residential"}),
                    "rows": [
                        {
                            "value_id": f"{year}_q{quarter}",
                            "label": printed,
                            "ordinal": 0,
                            "row_number": row,
                            "expected_row_header_column": "A",
                            "expected_row_header": printed,
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
                    "measures": measures,
                },
            )
        )
        row += 1
    assert printed == "2025 Q1"
    return record_sets


def build_stamps() -> None:
    path = STAMPS_DATA / STAMPS_ODS
    # Table 5a's 2023-24 sheet stores some numbers as text ('15800'), so the package
    # parses with numeric-text coercion; no cell the other tables port is text.
    cells = source_cells_from_ods(
        path.read_bytes(), artifact_meta(path), coerce_numeric_text=True
    )
    record_sets = []
    for opening_year, label in STAMPS_YEARS:
        # Tables 8a (residential) and 8b (non-residential).
        for table, property_type, title_word in (
            ("8a", "residential", "Residential"),
            ("8b", "non_residential", "Non-Residential"),
        ):
            sheet = f"Table_{table}_({label})"
            grid = sheet_grid(cells, sheet)
            title = grid[(1, "A")]
            assert title.startswith(
                f"Table {table} {label}: {title_word} Stamp Duty Land Tax (SDLT) "
                "transactions and receipts by price band and buyer type"
            ), title
            assert grid[(7, "A")] == "Price bands"
            corporate = table == "8a"
            rows = stamp_band_rows(grid, BANDS_8, 8, corporate=corporate)
            for buyer_index, (buyer_words, buyer, buyer_label) in enumerate(BUYERS):
                measures = []
                columns = "BCDEFGHIJ"[buyer_index * 3 : buyer_index * 3 + 3]
                for ordinal, (
                    (template, measure_id, concept, unit, scale),
                    column,
                ) in enumerate(zip(STAMP_MEASURES_8, columns)):
                    by = "by" if buyer == "individuals" else "for"
                    header = template.format(by=by, buyers=buyer_words)
                    assert grid[(7, column)] == header, (
                        sheet,
                        column,
                        grid[(7, column)],
                    )
                    measure = {
                        "measure_id": measure_id,
                        "label": f"{header}, {title_word.lower()} SDLT, {label}",
                        "ordinal": ordinal,
                        "column": column,
                        "source_column_id": measure_id,
                        "expected_column_header_row": 7,
                        "expected_column_header": header,
                        "concept": concept,
                        "source_concept": concept,
                        "concept_relation": "source_label",
                        "concept_authority": "hmrc",
                        "concept_evidence_url": STAMPS_URL,
                        "concept_evidence_notes": (
                            f"HMRC Annual Stamp Tax Statistics 2024 to 2025 (corrected "
                            f"11 March 2026), {sheet}, column {column} ('{header}'). "
                            + (
                                "Property value is HMRC's estimate. "
                                if measure_id == "property_value"
                                else ""
                            )
                            + (
                                "Net receipts (sheet note). "
                                if measure_id == "receipts"
                                else ""
                            )
                            + ROUNDING
                        ),
                        "unit": unit,
                        "aggregation": "sum",
                        "expected_cell_type": "number",
                    }
                    if scale:
                        measure["value_scale"] = int(scale)
                    measures.append(measure)
                # [X] cells: the corporate flat-rate row has no individual buyers.
                kept = [
                    row
                    for row in rows
                    if all(
                        isinstance(
                            grid.get((row["row_number"], m["column"])), (int, float)
                        )
                        for m in measures
                    )
                ]
                dropped = [row["value_id"] for row in rows if row not in kept]
                assert all(
                    grid.get((r["row_number"], m["column"])) == "[X]"
                    for r in rows
                    if r["value_id"] in dropped
                    for m in measures
                ), (sheet, buyer, dropped)
                shared_filters = {"sdlt_property_type": property_type}
                shared_constraints = [
                    UNIVERSE,
                    constraint(
                        "sdlt_property_type", property_type, "SDLT property type"
                    ),
                ]
                if buyer:
                    shared_filters["sdlt_buyer_type"] = buyer
                    shared_constraints.append(
                        constraint("sdlt_buyer_type", buyer, "Type of buyer")
                    )
                kept_rows = [dict(row, ordinal=i) for i, row in enumerate(kept)]
                kept_rows[0]["guard_cells"] = [
                    {
                        "column": "A",
                        "row": 1,
                        "expected_value": title,
                        "label": "table title",
                    }
                ]
                record_sets.append(
                    stamp_record_set(
                        f"{STAMPS_PREFIX}.table_{table}.{buyer or 'all_buyers'}.fy{opening_year}",
                        sheet,
                        opening_year,
                        label,
                        {
                            "shared_filters": shared_filters,
                            "shared_constraints": shared_constraints,
                            "rows": kept_rows,
                            "measures": measures,
                        },
                    )
                )

        # Table 6b: transactions paying the higher rates on additional dwellings.
        sheet = f"Table_6b_({label})"
        grid = sheet_grid(cells, sheet)
        title = grid[(1, "A")]
        assert title.startswith(
            f"Table 6b {label}: Higher Rates on Additional Dwellings (HRAD) transactions"
        ), title
        assert grid[(9, "A")] == "Price bands"
        rows = stamp_band_rows(grid, BANDS_6B, 10)
        assert str(grid[(5, "A")]).startswith(
            "HRAD receipts and the surcharge element are shown before accounting for any "
            "HRAD refunds"
        ), grid[(5, "A")]
        measures_6b = (
            (
                "B",
                "HRAD transactions",
                "hrad_transactions",
                "hmrc.sdlt.hrad_transactions",
                "count",
                None,
                "",
            ),
            (
                "D",
                "HRAD property value",
                "hrad_property_value",
                "hmrc.sdlt.hrad_property_value",
                "gbp",
                1e6,
                "Property value is HMRC's estimate. ",
            ),
            (
                "F",
                "HRAD receipts (gross)",
                "hrad_receipts_gross",
                "hmrc.sdlt.hrad_receipts_gross",
                "gbp",
                1e6,
                "All SDLT on HRAD transactions, at standard and surcharge rates, before HRAD refunds "
                "(row 5 note; the row 3 note's 'net' contradicts it and the column header). ",
            ),
            (
                "H",
                "Surcharge Element",
                "hrad_surcharge_element_gross",
                "hmrc.sdlt.hrad_surcharge_element_gross",
                "gbp",
                1e6,
                "The part of HRAD receipts that relates to the surcharge for additional dwellings "
                "(row 4 note), before HRAD refunds (row 5 note). ",
            ),
        )
        measures = []
        for ordinal, (
            column,
            header,
            measure_id,
            concept,
            unit,
            scale,
            note,
        ) in enumerate(measures_6b):
            assert str(grid[(9, column)]).strip() == header, (
                sheet,
                column,
                grid[(9, column)],
            )
            measure = {
                "measure_id": measure_id,
                "label": f"{header}, {label}",
                "ordinal": ordinal,
                "column": column,
                "source_column_id": measure_id,
                "expected_column_header_row": 9,
                "expected_column_header": header,
                "concept": concept,
                "source_concept": concept,
                "concept_relation": "source_label",
                "concept_authority": "hmrc",
                "concept_evidence_url": STAMPS_URL,
                "concept_evidence_notes": (
                    f"HMRC Annual Stamp Tax Statistics 2024 to 2025 (corrected 11 March "
                    f"2026), {sheet}, column {column} ('{header}'). {note}"
                    "Residential transactions paying HRAD, by individuals and companies "
                    "alike. " + ROUNDING
                ),
                "unit": unit,
                "aggregation": "sum",
                "expected_cell_type": "number",
            }
            if scale:
                measure["value_scale"] = int(scale)
            measures.append(measure)
        for row in rows:
            for measure in measures:
                assert isinstance(
                    grid.get((row["row_number"], measure["column"])), (int, float)
                )
        rows[0]["guard_cells"] = [
            {"column": "A", "row": 1, "expected_value": title, "label": "table title"}
        ]
        record_sets.append(
            stamp_record_set(
                f"{STAMPS_PREFIX}.table_6b.hrad.fy{opening_year}",
                sheet,
                opening_year,
                label,
                {
                    "shared_filters": {
                        "sdlt_property_type": "residential",
                        "sdlt_higher_rates": "additional_dwellings",
                    },
                    "shared_constraints": [
                        UNIVERSE,
                        constraint(
                            "sdlt_property_type", "residential", "SDLT property type"
                        ),
                        constraint(
                            "sdlt_higher_rates",
                            "additional_dwellings",
                            "Pays the higher rates on additional dwellings",
                        ),
                    ],
                    "rows": rows,
                    "measures": measures,
                },
            )
        )

    # PolicyEngine/chronicle#408 item 5, after chronicle#357's record sets.
    for opening_year, label in STAMPS_YEARS:
        record_sets += stamp_table_7(cells, opening_year, label)
        record_sets += stamp_table_3a(cells, opening_year, label)
        record_sets += stamp_table_5a(cells, opening_year, label)
        record_sets.append(stamp_table_9a(cells, opening_year, label))
        record_sets += stamp_table_9d(cells, opening_year, label)
    record_sets += stamp_table_2e(cells)

    band_labels = {
        slug: display
        for _, slug, display in BANDS_6B + BANDS_8 + (CORPORATE_FLAT_RATE,)
    }
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "hmrc-stamp-tax-statistics-2024-25",
        "label": (
            "HMRC Annual Stamp Tax Statistics 2024 to 2025 (corrected): SDLT transactions, "
            "property value and receipts by price band and buyer type (Tables 8a, 8b), "
            "higher rates on additional dwellings (Table 6b), purchases by the purchaser's "
            "age (Table 7), by country and region (Tables 3a, 5a) and First Time Buyers' "
            "Relief (Tables 9a, 9d), 2023-24 and 2024-25, and quarterly First Time Buyers' "
            "Relief, 2017 Q4 to 2025 Q1 (Table 2e)"
        ),
        "dimension_labels": STAMP_DIMENSION_LABELS,
        "dimension_value_labels": {
            "sdlt_price_band": band_labels,
            "sdlt_property_type": {
                "residential": "Residential",
                "non_residential": "Non-residential",
            },
            "sdlt_buyer_type": {
                "individuals": "Individuals",
                "other_buyers": "Other buyers (non-natural persons)",
            },
            "sdlt_higher_rates": {
                "additional_dwellings": "Higher rates on additional dwellings (HRAD)",
            },
            "sdlt_purchaser_age_band": {
                slug: display for _, slug, display in AGE_BANDS
            },
            "sdlt_ftbr_liability": FTBR_LIABILITY,
            "sdlt_corporate_flat_rate": {
                CORPORATE_IN_BANDS: "Included in the price bands",
            },
        },
        "artifact": {
            "source_name": "hmrc",
            "source_table": (
                "UK Stamp Tax Statistics 2024 to 2025, corrected tables (11 March 2026): "
                "Tables 6b, 8a and 8b"
            ),
            "resource_package": "db",
            "resource_directory": "data/hmrc/stamp_tax_statistics_2024_25",
            "manifest": "manifest.yaml",
            "vintage": "annual_stamp_tax_statistics_2024_25_corrected_2026_03_11",
            "extracted_at": "2026-10-15",
            "extraction_method": (
                "ODS whole-workbook used-range parse with numeric-text coercion"
            ),
            "parser": "ods_numeric_text_used_range",
            "artifact_year": 2025,
        },
        "record_sets": record_sets,
    }
    write_package(STAMPS_PACKAGE, payload, STAMPS_HEADER)


STAMPS_HEADER = """\
# HMRC Annual Stamp Tax Statistics 2024 to 2025, the corrected tables of 11 March 2026
# (first released 11 December 2025), for PolicyEngine/chronicle#357 item 1. The
# correction changed only the NRSDLT-overlap percentages in Tables 6b and 6c (column I),
# which are not ported; every cell ported here is identical in the December 2025 file.
#
# Ported, for both financial years the workbook carries (2023-24 and 2024-25, one sheet
# each):
# - Table 8a, residential SDLT, and Table 8b, non-residential SDLT: transactions, estimated
#   property value and receipts by price band, for individuals, other buyers and all
#   buyers. HMRC's sheets say 'other buyers'; its commentary (section 8) calls them
#   non-natural persons (companies, partnerships and collective investment schemes).
#   Table 8a's 'Corporate bodies paying flat rate' row is outside the price bands (rows 9
#   to 15 partition row 8), and carries no individuals ([X]).
# - Table 6b, transactions paying the higher rates on additional dwellings (HRAD): HRAD
#   transactions, HRAD property value, HRAD receipts (gross) and the surcharge element,
#   in total and by the table's ten price bands. Both receipts columns are before HRAD
#   refunds (row 5 note), so the surcharge element is gross; the OBR's 'Higher rates on
#   additional dwellings' line (EFO table 3.7) is net and matches the workbook's Table 2f
#   net surcharge instead. The table separates no buyer types and covers individuals and
#   companies alike.
#
# Not ported: Table 6b's percentage columns (C, G and I, text cells that divide published
# counts), its 'Residential receipts' column (E, which restates Table 8a's all-buyer
# receipts and Table 6a's residential receipts by band) and its corporate-bodies row (only
# column E is published). The workbook's other tables were not asked for by #357;
# PolicyEngine/chronicle#408's are below.
#
# Coverage: SDLT applies in England and Northern Ireland (publication page; commentary
# section 3.1), so facts carry the scope hmrc:england_and_northern_ireland. Transactions
# at GBP 40,000 or above (each sheet's note) ride as a constraint on every fact. Rounding
# is as published (transactions to the nearest 100, values and receipts to the nearest
# GBP 5 million), so bands need not sum to the 'All price bands' row; [X] marks fewer
# than 50 transactions, under GBP 2.5 million or not available, and emits no fact.
# Periods are financial years ending in March. The vintage names the corrected edition.
#
# Added for PolicyEngine/chronicle#408 item 5, from the same pinned workbook:
# - Table 7, individuals' residential purchases by the first-listed purchaser's age band
#   (fifteen bands, 'Unknown' among them) and price band, both years. The sheet says
#   transactions are rounded to the nearest 100, but the 2024-25 sheet prints unrounded
#   counts, including counts under 50 that its [X] note would withhold; they are stored
#   as printed. 'All ages' restates Table 8a's individuals (exactly in 2023-24, to 8a's
#   rounding in 2024-25, where it is also the exact sum of the age columns) and is not
#   ported again; nor are the percentage columns.
# - Table 3a, transactions, property value and receipts by property type, by country
#   and, within England, region. 'All countries' is England and Northern Ireland; its
#   residential and non-residential cells restate Tables 8a and 8b's all-buyer totals and
#   are not ported again, its totals are.
# - Table 5a, residential SDLT by price band, by country and region. Its price bands
#   include corporate bodies paying the flat rate, which Table 8a reports on a row of its
#   own: the all-countries bands above GBP 500,000 exceed 8a's by that row (in 2024-25 by
#   exactly its GBP 405 million of property value). Its facts carry
#   sdlt_corporate_flat_rate: included_in_price_bands. Its 'All price bands' columns
#   restate Table 3a's residential columns and are not ported again. The 2024-25 sheet's
#   title and contents entry say 2023-24; its own note says 2024-25 and its totals are 8a's
#   2024-25 totals, so it is stamped 2024-25. The 2023-24 sheet stores some numbers as
#   text ('15800'), which the package now reads with numeric-text coercion; no cell the
#   chronicle#357 record sets read is text, and their facts are unchanged.
# - Table 9a, First Time Buyers' Relief (FTBR) by country and region: amount relieved,
#   claims, the average relief, and exempt and liable claims.
# - Table 9d, FTBR claims by the first-listed purchaser's age band, in total and exempt
#   and liable; its 'All ages' column restates 9a's all-countries claims.
# - Table 2e, quarterly FTBR, 2017 Q4 to 2025 Q1: amount relieved, claims, and exempt and
#   liable claims. Despite its title it is not split by price band. 2024 Q2 to 2025 Q1
#   print unrounded, fractional claims, stored as printed; 2020 Q4 to 2021 Q2 are [X]
#   (the SDLT holiday) and emit no fact. Quarters before April 2018 carry England, Wales
#   and Northern Ireland, where SDLT then applied (sheet note).
# - Exempt claims are in most cases purchases below the zero rate threshold, and liable
#   claims those above it but below the maximum price: GBP 425,000 and GBP 625,000 from 23
#   September 2022 to 31 March 2025, which covers both years' relief counts, and GBP
#   300,000 and GBP 500,000 before (Table 2e notes).
# - Not ported: the FTBR percentages (9a column H, 2e column F) and Table 7's percentages,
#   text that divides published counts, as for Table 6b; Tables 4a to 4d, 9b and 9c. The
#   artifact's source_table still names Tables 6b, 8a and 8b: it is part of every fact's
#   key, so changing it would re-key chronicle#357's facts.
"""


# ------------------------------------------------------------------ OBR 3.7

OBR_RECEIPTS_YAML = ROOT / "packages/obr/efo_receipts_march_2026/source_package.yaml"
OBR_RECEIPTS_XLSX = ROOT / "db/data/obr/efo_receipts_march_2026/efo_receipts.xlsx"
OBR_RECEIPTS_URL = (
    "https://obr.uk/download/march-2026-economic-and-fiscal-outlook-detailed-forecast-"
    "tables-receipts/"
)
OBR_OCTOBER_RECEIPTS_YAML = (
    ROOT / "packages/obr/efo_receipts_october_2026/source_package.yaml"
)


def obr_line_year(record_set: dict) -> tuple:
    """A record set's line and year, whatever its id: concept, unit, universe,
    geography, entity and period."""
    (measure,) = record_set["measures"]
    constraints = sorted(
        (item["variable"], item["operator"], str(item["value"]))
        for item in record_set.get("shared_constraints", [])
    )
    return (
        measure["concept"],
        measure["unit"],
        tuple(constraints),
        record_set["domain"],
        record_set["geography_id"],
        record_set["entity"],
        record_set["entity_role"],
        record_set["period_type"],
        record_set["period"],
    )


def obr_october_line_years() -> set[tuple]:
    """The lines and years the October 2026 receipts package publishes.

    chronicle#397: where two vintages publish a number for the same line and year,
    Chronicle keeps the later one, so the March package leaves out every record set
    October has a number for, whatever line id October gives it: table 4.1's
    'Betting and gaming taxes' carries sheet 3.10's 2025-26 total."""
    payload = yaml.safe_load(OBR_OCTOBER_RECEIPTS_YAML.read_text(encoding="utf-8"))
    return {obr_line_year(record_set) for record_set in payload["record_sets"]}


OBR_3_7_MARKER = (
    "# chronicle#357: sheet 3.7, generated by scripts/build_uk_1095_port_packages.py\n"
)
OBR_3_7_LINES = (
    # (row, publisher label, line id, display label, notes)
    (
        8,
        "SDLT from residential property",
        "sdlt_residential",
        "SDLT from residential property",
        "SDLT on residential property, all buyers.",
    ),
    (
        10,
        "Main rates",
        "sdlt_residential_main_rates",
        "SDLT from residential property: main rates",
        "Residential SDLT at the main rates, an 'of which' of row 8.",
    ),
    (
        11,
        "Higher rates on additional dwellings",
        "sdlt_residential_higher_rates_additional_dwellings",
        "SDLT from residential property: higher rates on additional dwellings",
        "Residential SDLT from the higher rates on additional dwellings, an 'of which' of row 8; "
        "it matches HMRC's net surcharge (Annual Stamp Tax Statistics Table 2f), not the gross "
        "surcharge element of Table 6b.",
    ),
    (
        12,
        "Non-UK resident surcharge",
        "sdlt_residential_non_uk_resident_surcharge",
        "SDLT from residential property: non-UK resident surcharge",
        "Residential SDLT from the non-UK resident surcharge, an 'of which' of row 8.",
    ),
    (
        13,
        "SDLT from non-residential property",
        "sdlt_non_residential",
        "SDLT from non-residential property",
        "SDLT on non-residential property, all buyers.",
    ),
)


def obr_3_7_blocks() -> str:
    cells = source_cells_from_xlsx(
        OBR_RECEIPTS_XLSX.read_bytes(), artifact_meta(OBR_RECEIPTS_XLSX)
    )
    grid = sheet_grid(cells, "3.7")
    assert grid[(2, "B")] == "3.7 Property transactions taxes: Receipts by sector", (
        grid[(2, "B")]
    )
    assert grid[(3, "C")] == "£ billion"
    assert grid[(4, "C")] == "Outturn" and grid[(4, "D")] == "Forecast"
    years = []
    for index, column in enumerate("CDEFGHI"):
        opening = 2024 + index
        assert grid[(5, column)] == f"{opening}-{str(opening + 1)[2:]}", grid[
            (5, column)
        ]
        years.append((opening, column))
    october = obr_october_line_years()
    blocks = []
    for row, header, line, display, note in OBR_3_7_LINES:
        assert grid[(row, "B")] == header, (row, grid[(row, "B")])
        kept = 0
        for opening, column in years:
            label = f"{opening}-{str(opening + 1)[2:]}"
            assert isinstance(grid[(row, column)], (int, float)), (row, column)
            record_set_id = f"obr.efo_2026_03.receipts.{line}.fy{opening}"
            notes = (
                f"OBR EFO March 2026 detailed forecast tables, sheet 3.7 ('Property transactions "
                f"taxes: Receipts by sector'), row {row} ('{header}'), GBP billion. {note} The EFO "
                "publishes no split of SDLT by type of buyer (chronicle#357 item 2); SDLT applies "
                "in England and Northern Ireland, and the line is stamped United Kingdom like the "
                "rest of this package's receipts."
            )
            record = {
                "record_set_id": record_set_id,
                "provenance_class": "model_output",
                "assertion": "observation" if opening == 2024 else "source_projection",
                "record_set_spec_id": f"{record_set_id}.v1",
                "source_record_id_prefix": record_set_id,
                "sheet_name": "3.7",
                "period_type": "fiscal_year",
                "period": opening,
                "geography_id": "K02000001",
                "geography_level": "country",
                "geography_name": "United Kingdom",
                "geography_vintage": "current",
                "entity": "person",
                "entity_role": "resident_population",
                "domain": "public_sector_finances",
                "groupby_dimension": "obr.efo_line",
                "rows": [
                    {
                        "value_id": line,
                        "label": display,
                        "ordinal": 0,
                        "row_number": row,
                        "expected_row_header_column": "B",
                        "expected_row_header": header,
                        "table_record_kind": "total",
                    }
                ],
                "measures": [
                    {
                        "measure_id": "amount",
                        "label": f"{display}, FY{label}",
                        "ordinal": 0,
                        "column": column,
                        "source_column_id": "amount",
                        "expected_column_header_row": 5,
                        "expected_column_header": label,
                        "concept": f"obr.{line}",
                        "source_concept": f"obr.{line}",
                        "concept_relation": "source_label",
                        "concept_authority": "obr",
                        "concept_evidence_url": OBR_RECEIPTS_URL,
                        "concept_evidence_notes": notes,
                        "unit": "gbp",
                        "aggregation": "sum",
                        "value_scale": 1000000000,
                        "expected_cell_type": "number",
                    }
                ],
            }
            if obr_line_year(record) in october:
                continue
            kept += 1
            blocks.append(
                yaml.dump(
                    [record],
                    Dumper=PackageDumper,
                    sort_keys=False,
                    allow_unicode=True,
                    width=100,
                )
            )
        # Each line keeps a year October does not print, so the October build
        # (scripts/build_obr_efo_october_2026.py) still finds it here.
        assert kept, line
    return OBR_3_7_MARKER + "".join(blocks)


def build_obr_3_7() -> None:
    """Append (or replace) the generated sheet 3.7 record sets in the receipts package."""
    text = OBR_RECEIPTS_YAML.read_text(encoding="utf-8")
    text = text.split(OBR_3_7_MARKER)[0]
    if not text.endswith("\n"):
        text += "\n"
    OBR_RECEIPTS_YAML.write_text(text + obr_3_7_blocks(), encoding="utf-8")


# ----------------------------------------------------------------------- HBAI

HBAI_URL = (
    "https://www.gov.uk/government/statistics/households-below-average-income-for-"
    "financial-years-ending-1995-to-2025"
)
HBAI_SUMMARY_PACKAGE = ROOT / "packages/dwp/hbai_summary_fye2025"
HBAI_SUMMARY_DATA = ROOT / "db/data/dwp/hbai_summary_fye2025"
HBAI_SUMMARY_ODS = "summary-hbai-1994-95-2024-25-tables.ods"
HBAI_UNCERTAINTY_PACKAGE = ROOT / "packages/dwp/hbai_uncertainty_fye2025"
HBAI_UNCERTAINTY_DATA = ROOT / "db/data/dwp/hbai_uncertainty_fye2025"
HBAI_ZIP = "hbai-data_tables-2025.zip"
HBAI_UNCERTAINTY_MEMBER = "uncertainty-hbai-2024-25-tables.ods"
HBAI_VINTAGE = "hbai_fye2025_release_2026_03_26"
HBAI_PRICE_BASIS = "average_2024_25_prices"
HOUSING_COSTS = {
    "before_housing_costs": "Before housing costs",
    "after_housing_costs": "After housing costs",
}
HBAI_NOTES = (
    "Households Below Average Income, FYE 1995 to FYE 2025 release (26 March 2026). "
    "Weekly net disposable household income, equivalised with the modified OECD scale "
    "(couple without children = 1; the AHC companion scale after housing costs), "
    "individuals ranked by their household's income. Relative low income is income "
    "below 60 per cent of the same year's median. From FYE 2022 the survey is linked to "
    "DWP and HMRC administrative records, a break in series (Note 1). Figures are for "
    "the United Kingdom from 2002/03 and Great Britain before (Notes). Family Resources "
    "Survey estimates carry sampling error."
)


HBAI_PANDEMIC_NOTE = (
    " Note 5: in 2020/21 and 2021/22, the two years spanning the coronavirus (COVID-19) "
    "pandemic, FRS interviewing was by telephone only, which changed the sample's "
    "composition; DWP asks that changes since 2019/20 be read with that in mind."
)


def hbai_notes(opening_year: int) -> str:
    """The release's notes, with Note 5's caution on the two pandemic years."""
    return HBAI_NOTES + (HBAI_PANDEMIC_NOTE if opening_year in (2020, 2021) else "")


def hbai_geography(opening_year: int) -> dict:
    if opening_year >= 2002:
        return {
            "geography_id": "K02000001",
            "geography_level": "country",
            "geography_name": "United Kingdom",
            "geography_vintage": "current",
        }
    return {
        "geography_id": "K03000001",
        "geography_level": "country",
        "geography_name": "Great Britain",
        "geography_vintage": "current",
    }


def hbai_year_label(opening_year: int) -> str:
    return f"{opening_year}/{str(opening_year + 1)[2:]}"


def hbai_record_set(record_set_id, sheet, opening_year, extra) -> dict:
    payload = {
        "record_set_id": record_set_id,
        "provenance_class": "survey_aggregate",
        "survey_instrument": "Family Resources Survey",
        "assertion": "observation",
        "record_set_spec_id": f"{record_set_id}.v1",
        "source_record_id_prefix": record_set_id,
        "sheet_name": sheet,
        **fiscal_period(
            opening_year,
            hbai_year_label(opening_year),
            f"Financial year ending March {opening_year + 1} (FYE {opening_year + 1}); "
            "period.value stores the opening year.",
        ),
        **hbai_geography(opening_year),
        "entity": "person",
        "entity_role": "individual_in_private_household",
        "domain": "household_income_distribution",
    }
    payload.update(extra)
    return payload


def housing_cost_filters(basis: str) -> tuple[dict, list]:
    return (
        {"housing_costs": basis},
        [constraint("housing_costs", basis, "Housing costs")],
    )


def build_hbai_summary() -> None:
    path = HBAI_SUMMARY_DATA / HBAI_SUMMARY_ODS
    cells = source_cells_from_ods(path.read_bytes(), artifact_meta(path))
    record_sets = []

    # Table 1.2b: quintile 3, the median, in average 2024/25 prices.
    grid = sheet_grid(cells, "1_2b")
    title = grid[(1, "A")]
    assert title == (
        "Table 1.2b: Estimated Gini coefficient, and money values of estimated quintile "
        "medians and overall population mean in average 2024/25 prices, United Kingdom"
    ), title
    assert grid[(7, "P")] == "£pw equivalised, 2024/25 prices"
    assert grid[(9, "F")] == "Quintile 3 (median)"
    blocks = (
        ("before_housing_costs", "Income Before Housing Costs", 10),
        ("after_housing_costs", "Income After Housing Costs", 45),
    )
    for basis, heading, heading_row in blocks:
        assert grid[(heading_row, "A")] == heading, (
            heading_row,
            grid[(heading_row, "A")],
        )
        year_rows = []
        row = heading_row + 1
        for opening_year in range(1994, 2025):
            label = hbai_year_label(opening_year)
            if grid.get((row, "A")) != label:
                # The break-in-series row before 2021/22 carries text, not a year.
                assert opening_year == 2021, (row, grid.get((row, "A")))
                assert str(grid[(row, "A")]).startswith("Admin-linked benefits data"), (
                    grid[(row, "A")]
                )
                row += 1
            assert grid[(row, "A")] == label, (row, grid[(row, "A")], label)
            year_rows.append((opening_year, row))
            row += 1
        filters, constraints = housing_cost_filters(basis)
        filters["price_basis"] = HBAI_PRICE_BASIS
        constraints.append(constraint("price_basis", HBAI_PRICE_BASIS, "Price basis"))
        for opening_year, row in year_rows:
            value = grid[(row, "F")]
            assert isinstance(value, float), (row, value)
            record_set_id = f"dwp.hbai_fye2025.median_income.{basis}.fy{opening_year}"
            record_sets.append(
                hbai_record_set(
                    record_set_id,
                    "1_2b",
                    opening_year,
                    {
                        "groupby_dimension": "housing_costs",
                        "rows": [
                            {
                                "value_id": basis,
                                "label": HOUSING_COSTS[basis],
                                "ordinal": 0,
                                "row_number": row,
                                "expected_row_header_column": "A",
                                "expected_row_header": hbai_year_label(opening_year),
                                "table_record_kind": "detail",
                                "filters": filters,
                                "constraints": constraints,
                                "guard_cells": [
                                    {
                                        "column": "A",
                                        "row": heading_row,
                                        "expected_value": heading,
                                        "label": "housing-cost block heading",
                                    },
                                    {
                                        "column": "P",
                                        "row": 7,
                                        "expected_value": "£pw equivalised, 2024/25 prices",
                                        "label": "unit and price basis",
                                    },
                                ],
                            }
                        ],
                        "measures": [
                            {
                                "measure_id": "median_equivalised_household_income",
                                "label": (
                                    f"Median equivalised household income, {HOUSING_COSTS[basis].lower()}, "
                                    f"{hbai_year_label(opening_year)}, average 2024/25 prices"
                                ),
                                "ordinal": 0,
                                "column": "F",
                                "source_column_id": "quintile_3_median",
                                "expected_column_header_row": 9,
                                "expected_column_header": "Quintile 3 (median)",
                                "concept": "dwp.hbai.median_equivalised_household_income",
                                "source_concept": "dwp.hbai.median_equivalised_household_income",
                                "concept_relation": "source_label",
                                "concept_authority": "dwp",
                                "concept_evidence_url": HBAI_URL,
                                "concept_evidence_notes": (
                                    "HBAI summary results, Table 1.2b, 'Quintile 3 (median)': the median "
                                    "of equivalised weekly household income, in average 2024/25 prices "
                                    "(the release re-prices the whole series each year, so the price "
                                    "basis is a filter). " + hbai_notes(opening_year)
                                ),
                                "unit": "gbp_per_week",
                                "aggregation": "median",
                                "expected_cell_type": "number",
                            }
                        ],
                    },
                )
            )

    # Table 1.3a: percentage of individuals in relative low income.
    grid = sheet_grid(cells, "1_3a")
    title = grid[(1, "A")]
    assert title == (
        "Table 1.3a: Estimated percentage of individuals in relative/absolute low income, "
        "United Kingdom"
    ), title
    assert grid[(7, "J")] == "Percentage of individuals"
    assert (
        grid[(8, "D")] == "Before housing costs"
        and grid[(8, "I")] == "After housing costs"
    )
    assert (
        grid[(9, "C")] == "Relative low income"
        and grid[(9, "H")] == "Relative low income"
    )
    assert grid[(10, "A")] == "FRS (GB)" and grid[(18, "A")] == "FRS (UK)"
    for basis, column, group_column in (
        ("before_housing_costs", "C", "D"),
        ("after_housing_costs", "H", "I"),
    ):
        filters, constraints = housing_cost_filters(basis)
        filters["low_income_threshold"] = "below_60pct_contemporary_median"
        constraints.append(
            constraint(
                "low_income_threshold",
                "below_60pct_contemporary_median",
                "Household income below 60 per cent of the same year's median",
            )
        )
        for offset, opening_year in enumerate(range(1994, 2025)):
            row = 10 + offset
            assert grid[(row, "B")] == hbai_year_label(opening_year), (
                row,
                grid[(row, "B")],
            )
            assert isinstance(grid[(row, column)], float), (row, column)
            record_set_id = (
                f"dwp.hbai_fye2025.relative_low_income.{basis}.fy{opening_year}"
            )
            record_sets.append(
                hbai_record_set(
                    record_set_id,
                    "1_3a",
                    opening_year,
                    {
                        "groupby_dimension": "housing_costs",
                        "rows": [
                            {
                                "value_id": basis,
                                "label": HOUSING_COSTS[basis],
                                "ordinal": 0,
                                "row_number": row,
                                "expected_row_header_column": "B",
                                "expected_row_header": hbai_year_label(opening_year),
                                "table_record_kind": "detail",
                                "filters": filters,
                                "constraints": constraints,
                                "guard_cells": [
                                    {
                                        "column": group_column,
                                        "row": 8,
                                        "expected_value": HOUSING_COSTS[
                                            basis
                                        ].capitalize(),
                                        "label": "housing-cost column group",
                                    },
                                    {
                                        "column": "A",
                                        "row": 10 if opening_year < 2002 else 18,
                                        "expected_value": "FRS (GB)"
                                        if opening_year < 2002
                                        else "FRS (UK)",
                                        "label": "survey coverage of the year block",
                                    },
                                ],
                            }
                        ],
                        "measures": [
                            {
                                "measure_id": "relative_low_income_share",
                                "label": (
                                    f"Individuals in relative low income, {HOUSING_COSTS[basis].lower()}, "
                                    f"{hbai_year_label(opening_year)}"
                                ),
                                "ordinal": 0,
                                "column": column,
                                "source_column_id": f"relative_low_income_{basis}",
                                "expected_column_header_row": 9,
                                "expected_column_header": "Relative low income",
                                "concept": "dwp.hbai.relative_low_income_share",
                                "source_concept": "dwp.hbai.relative_low_income_share",
                                "concept_relation": "source_label",
                                "concept_authority": "dwp",
                                "concept_evidence_url": HBAI_URL,
                                "concept_evidence_notes": (
                                    "HBAI summary results, Table 1.3a: percentage of individuals in "
                                    "households with income below 60 per cent of the contemporary "
                                    "median. " + hbai_notes(opening_year)
                                ),
                                "unit": "percent",
                                "aggregation": "share",
                                "expected_cell_type": "number",
                            }
                        ],
                    },
                )
            )

    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "dwp-hbai-summary-fye2025",
        "label": (
            "DWP Households Below Average Income, FYE 2025 release: median equivalised "
            "household income and percentage of individuals in relative low income, before "
            "and after housing costs, FYE 1995 to FYE 2025"
        ),
        "dimension_labels": {
            "housing_costs": "Housing costs",
            "price_basis": "Price basis",
            "low_income_threshold": "Low income threshold",
        },
        "dimension_value_labels": {
            "housing_costs": HOUSING_COSTS,
            "price_basis": {HBAI_PRICE_BASIS: "Average 2024/25 prices"},
            "low_income_threshold": {
                "below_60pct_contemporary_median": "Below 60% of the same year's median income",
            },
        },
        "artifact": {
            "source_name": "dwp",
            "source_table": (
                "Households Below Average Income, FYE 1995 to FYE 2025: HBAI summary results, "
                "Tables 1.2b and 1.3a"
            ),
            "resource_package": "db",
            "resource_directory": "data/dwp/hbai_summary_fye2025",
            "manifest": "manifest.yaml",
            "vintage": HBAI_VINTAGE,
            "extracted_at": "2026-10-15",
            "extraction_method": "ODS whole-workbook used-range cell parse",
            "parser": "ods_used_range",
            "artifact_year": 2025,
        },
        "record_sets": record_sets,
    }
    write_package(HBAI_SUMMARY_PACKAGE, payload, HBAI_SUMMARY_HEADER)


HBAI_SUMMARY_HEADER = """\
# DWP Households Below Average Income (HBAI), the FYE 1995 to FYE 2025 release of 26 March
# 2026 (accredited official statistics), for PolicyEngine/chronicle#357 item 5. Microcosm
# checks its income distribution against HBAI as validation only (microcosm#968's
# hbai_basis), never as a target.
#
# Ported, every year the release carries (1994/95 to 2024/25, FYE 1995 to FYE 2025):
# - Table 1.2b's 'Quintile 3 (median)', the median of equivalised weekly household income,
#   before and after housing costs, GBP per week in average 2024/25 prices. HBAI re-prices
#   the whole series in each release's latest-year prices, so every median carries
#   price_basis: average_2024_25_prices and a later release's restatement differs in that
#   filter and its vintage.
# - Table 1.3a's percentage of individuals in relative low income (below 60 per cent of the
#   same year's median), before and after housing costs.
# The release is the vintage on every fact, so a later release's revisions sit beside them.
# The confidence intervals are in the release's data-table ZIP, ported by
# dwp-hbai-uncertainty-fye2025; DWP publishes intervals only for the release's latest year.
#
# Coverage: the United Kingdom from 2002/03 and Great Britain for 1994/95 to 2001/02 (Notes;
# Table 1.3a labels the blocks FRS (GB) and FRS (UK)), so those years carry Great Britain.
# A break in series sits between 2020/21 and 2021/22, when the survey was linked to
# administrative benefit records (Note 1); both sides are ported as published. The
# methodology report advises caution on FYE 2021 and FYE 2022 (pandemic data collection).
# DWP plans to revise FYE 2025 in March 2027 (council tax variable and a Census-based back
# series); that release would be a new vintage.
#
# Not ported: the other quintiles, the mean, the Gini coefficient, absolute low income, the
# change rows and the other tables, none of which the request names.
"""


def build_hbai_uncertainty() -> None:
    import zipfile

    with zipfile.ZipFile(HBAI_UNCERTAINTY_DATA / HBAI_ZIP) as archive:
        content = archive.read(HBAI_UNCERTAINTY_MEMBER)
    cells = source_cells_from_ods(content, artifact_meta(Path(HBAI_UNCERTAINTY_MEMBER)))
    record_sets = []
    bounds = (
        ("ci_95_lower_bound", "lower bound"),
        ("ci_95_upper_bound", "upper bound"),
    )

    # Table 8a: the median is the Quintile 3 row of each housing-cost block.
    grid = sheet_grid(cells, "8a")
    title = grid[(1, "A")]
    assert title.startswith(
        "Table 8a: Confidence intervals for the Gini coefficient, quintile medians and "
        "overall population mean income in average 2024/25 prices, United Kingdom"
    ), title
    assert grid[(4, "A")] == "Source: FRS 2024/25"
    assert grid[(6, "C")] == "Estimate" and grid[(6, "F")] == "95% Confidence Interval"
    for basis, heading, heading_row, row in (
        ("before_housing_costs", "Before Housing Costs", 7, 9),
        ("after_housing_costs", "After Housing Costs", 14, 16),
    ):
        assert grid[(heading_row, "A")] == heading and grid[(row, "B")] == "Quintile 3"
        assert grid[(row, "F")] == ","
        filters, constraints = housing_cost_filters(basis)
        filters["price_basis"] = HBAI_PRICE_BASIS
        constraints.append(constraint("price_basis", HBAI_PRICE_BASIS, "Price basis"))
        measures = []
        for ordinal, ((statistic, words), column) in enumerate(zip(bounds, "EG")):
            measures.append(
                {
                    "measure_id": f"median_equivalised_household_income_{statistic}",
                    "label": f"Median equivalised household income, {HOUSING_COSTS[basis].lower()}, 2024/25, 95% confidence interval {words}",
                    "ordinal": ordinal,
                    "column": column,
                    "source_column_id": statistic,
                    "source_column_dimensions": {"statistic": statistic},
                    "filters": {"statistic": statistic},
                    "constraints": [constraint("statistic", statistic, "Statistic")],
                    "expected_column_header_row": 6,
                    "expected_column_header": "95% Confidence Interval"
                    if column == "F"
                    else None,
                    "concept": "dwp.hbai.median_equivalised_household_income",
                    "source_concept": "dwp.hbai.median_equivalised_household_income",
                    "concept_relation": "source_label",
                    "concept_authority": "dwp",
                    "concept_evidence_url": HBAI_URL,
                    "concept_evidence_notes": (
                        f"HBAI communicating uncertainty tables (data-table ZIP member "
                        f"{HBAI_UNCERTAINTY_MEMBER}), Table 8a, Quintile 3 row: the 95% "
                        f"confidence interval {words} for the FYE 2025 median (column C, which "
                        "equals Table 1.2b's estimate), GBP per week in average 2024/25 prices, "
                        "as stored (the sheet displays it rounded). DWP bootstraps the "
                        "interval (500 resamples of the FRS design, regrossed; methodology "
                        "report). " + HBAI_NOTES
                    ),
                    "unit": "gbp_per_week",
                    "aggregation": "median",
                    "expected_cell_type": "number",
                }
            )
        for measure in measures:
            if measure["expected_column_header"] is None:
                del (
                    measure["expected_column_header"],
                    measure["expected_column_header_row"],
                )
        record_sets.append(
            hbai_record_set(
                f"dwp.hbai_fye2025.median_income_ci95.{basis}.fy2024",
                "8a",
                2024,
                {
                    "groupby_dimension": "housing_costs",
                    "rows": [
                        {
                            "value_id": basis,
                            "label": HOUSING_COSTS[basis],
                            "ordinal": 0,
                            "row_number": row,
                            "expected_row_header_column": "B",
                            "expected_row_header": "Quintile 3",
                            "table_record_kind": "detail",
                            "filters": filters,
                            "constraints": constraints,
                            "guard_cells": [
                                {
                                    "column": "A",
                                    "row": heading_row,
                                    "expected_value": heading,
                                    "label": "housing-cost block heading",
                                },
                                {
                                    "column": "F",
                                    "row": 6,
                                    "expected_value": "95% Confidence Interval",
                                    "label": "interval header",
                                },
                                {
                                    "column": "F",
                                    "row": row,
                                    "expected_value": ",",
                                    "label": "separator between the lower and upper bounds",
                                },
                            ],
                        }
                    ],
                    "measures": measures,
                },
            )
        )

    # Table 8b: relative low income, all individuals.
    grid = sheet_grid(cells, "8b")
    title = grid[(1, "A")]
    assert title.startswith(
        "Table 8b: Confidence intervals for the percentage of individuals in "
        "relative/absolute low income, United Kingdom"
    ), title
    assert grid[(7, "D")] == "All Individuals" and grid[(8, "C")] == "Estimate"
    assert grid[(8, "E")] == "95% Confidence Intervals"
    for basis, heading, heading_row, row in (
        ("before_housing_costs", "Before Housing Costs", 9, 10),
        ("after_housing_costs", "After Housing Costs", 14, 15),
    ):
        assert grid[(heading_row, "A")] == heading
        assert grid[(row, "A")] == "Relative Low Income"
        assert grid[(row, "B")] == "Percentage below 60% of relative median income"
        assert grid[(row, "E")] == ","
        filters, constraints = housing_cost_filters(basis)
        filters["low_income_threshold"] = "below_60pct_contemporary_median"
        constraints.append(
            constraint(
                "low_income_threshold",
                "below_60pct_contemporary_median",
                "Household income below 60 per cent of the same year's median",
            )
        )
        measures = []
        for ordinal, ((statistic, words), column) in enumerate(zip(bounds, "DF")):
            measures.append(
                {
                    "measure_id": f"relative_low_income_share_{statistic}",
                    "label": f"Individuals in relative low income, {HOUSING_COSTS[basis].lower()}, 2024/25, 95% confidence interval {words}",
                    "ordinal": ordinal,
                    "column": column,
                    "source_column_id": statistic,
                    "source_column_dimensions": {"statistic": statistic},
                    "filters": {"statistic": statistic},
                    "constraints": [constraint("statistic", statistic, "Statistic")],
                    "concept": "dwp.hbai.relative_low_income_share",
                    "source_concept": "dwp.hbai.relative_low_income_share",
                    "concept_relation": "source_label",
                    "concept_authority": "dwp",
                    "concept_evidence_url": HBAI_URL,
                    "concept_evidence_notes": (
                        f"HBAI communicating uncertainty tables (data-table ZIP member "
                        f"{HBAI_UNCERTAINTY_MEMBER}), Table 8b, all individuals: the 95% "
                        f"confidence interval {words} for the FYE 2025 percentage in relative low "
                        "income (column C, which equals Table 1.3a's estimate), percentage "
                        "points, as stored (the sheet displays it rounded). DWP bootstraps the "
                        "interval (methodology report). " + HBAI_NOTES
                    ),
                    "unit": "percent",
                    "aggregation": "share",
                    "expected_cell_type": "number",
                }
            )
        record_sets.append(
            hbai_record_set(
                f"dwp.hbai_fye2025.relative_low_income_ci95.{basis}.fy2024",
                "8b",
                2024,
                {
                    "groupby_dimension": "housing_costs",
                    "rows": [
                        {
                            "value_id": basis,
                            "label": HOUSING_COSTS[basis],
                            "ordinal": 0,
                            "row_number": row,
                            "expected_row_header_column": "A",
                            "expected_row_header": "Relative Low Income",
                            "table_record_kind": "detail",
                            "filters": filters,
                            "constraints": constraints,
                            "guard_cells": [
                                {
                                    "column": "A",
                                    "row": heading_row,
                                    "expected_value": heading,
                                    "label": "housing-cost block heading",
                                },
                                {
                                    "column": "D",
                                    "row": 7,
                                    "expected_value": "All Individuals",
                                    "label": "population group",
                                },
                                {
                                    "column": "E",
                                    "row": 8,
                                    "expected_value": "95% Confidence Intervals",
                                    "label": "interval header",
                                },
                                {
                                    "column": "B",
                                    "row": row,
                                    "expected_value": "Percentage below 60% of relative median income",
                                    "label": "threshold definition",
                                },
                            ],
                        }
                    ],
                    "measures": measures,
                },
            )
        )

    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "dwp-hbai-uncertainty-fye2025",
        "label": (
            "DWP Households Below Average Income, FYE 2025 release: 95% confidence intervals "
            "for the FYE 2025 median equivalised household income and percentage of "
            "individuals in relative low income, before and after housing costs"
        ),
        "dimension_labels": {
            "housing_costs": "Housing costs",
            "price_basis": "Price basis",
            "low_income_threshold": "Low income threshold",
            "statistic": "Statistic",
        },
        "dimension_value_labels": {
            "housing_costs": HOUSING_COSTS,
            "price_basis": {HBAI_PRICE_BASIS: "Average 2024/25 prices"},
            "low_income_threshold": {
                "below_60pct_contemporary_median": "Below 60% of the same year's median income",
            },
            "statistic": {
                "ci_95_lower_bound": "95% confidence interval lower bound",
                "ci_95_upper_bound": "95% confidence interval upper bound",
            },
        },
        "artifact": {
            "source_name": "dwp",
            "source_table": (
                "Households Below Average Income, FYE 2025: HBAI data tables (ZIP), "
                "communicating uncertainty, Tables 8a and 8b"
            ),
            "resource_package": "db",
            "resource_directory": "data/dwp/hbai_uncertainty_fye2025",
            "manifest": "manifest.yaml",
            "vintage": HBAI_VINTAGE,
            "extracted_at": "2026-10-15",
            "extraction_method": "ODS whole-workbook used-range cell parse",
            "parser": "zip_ods_used_range",
            "archive_member": HBAI_UNCERTAINTY_MEMBER,
            "artifact_year": 2025,
        },
        "record_sets": record_sets,
    }
    write_package(HBAI_UNCERTAINTY_PACKAGE, payload, HBAI_UNCERTAINTY_HEADER)


HBAI_UNCERTAINTY_HEADER = """\
# DWP Households Below Average Income, FYE 2025 release (26 March 2026): the 95% confidence
# intervals for the four statistics dwp-hbai-summary-fye2025 carries, for
# PolicyEngine/chronicle#357 item 5. They are only in the release's data-table ZIP, in
# 'Communicating uncertainty' (member uncertainty-hbai-2024-25-tables.ods), read through the
# zip_ods_used_range parser.
#
# Ported: Table 8a's interval for Quintile 3 (the median) and Table 8b's interval for all
# individuals in relative low income, before and after housing costs, each as two facts on
# the statistic dimension (ci_95_lower_bound, ci_95_upper_bound). The estimates the
# intervals bracket (column C) equal the summary package's FYE 2025 facts and are not
# repeated; the bounds are the stored values, which the sheet displays rounded. DWP
# publishes intervals only for each release's latest year (FYE 2025 here), bootstrapped
# from the FRS design (methodology report).
#
# Not ported: the other quintiles, mean, Gini, absolute low income, the children,
# working-age and pensioner groups, and the intervals on the year-on-year change.
"""


if __name__ == "__main__":
    build_stamps()
    build_obr_3_7()
    build_hbai_summary()
    build_hbai_uncertainty()
