"""Author the chronicle#343 fact packages from their pinned publisher artifacts.

Two packages are written, both declarative, both read from the bytes the
manifests pin under ``db/data``; nothing is downloaded and no fact is built:

- ``obr-hvcts-costing-april-2026``: Tables 1.1, 1.2 and 1.5 of the OBR's
  2 April 2026 costing note for the high value council tax surcharge, and the
  four parameters the note states in its text.
- ``ons-hpssa-pcon24-year-ending-march-2026``: residential property sales and
  median price paid by 2024 constituency and property type, for the four
  rolling years ending in March, 2023 to 2026.

Selectors are located by matching publisher text in the parsed source cells,
and every match is asserted, so a re-run against different bytes fails rather
than drifting.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from chronicle.sources.cells import (
    SourceArtifactMetadata,
    source_cells_from_pdf_text_numbers,
)

ROOT = Path(__file__).resolve().parents[1]

OBR_PACKAGE = ROOT / "packages/obr/hvcts_costing_april_2026"
OBR_DATA = ROOT / "db/data/obr/hvcts_costing_april_2026"
OBR_PDF = (
    "Supplementary-forecast-information-high-value-council-tax-surcharge-costing.pdf"
)
OBR_PREFIX = "obr.hvcts_costing_2026_04"
OBR_EVIDENCE_URL = (
    "https://obr.uk/docs/dlm_uploads/"
    "Supplementary-forecast-information-high-value-council-tax-surcharge-costing.pdf"
)

HPSSA_PACKAGE = ROOT / "packages/ons/hpssa_pcon24_year_ending_march_2026"
HPSSA_DATA = ROOT / "db/data/ons/hpssa_pcon24_year_ending_march_2026"
HPSSA_XLSX = "housepricestatisticsparlicon.xlsx"
HPSSA_PREFIX = "ons.hpssa_ye_mar2026.pcon24"
HPSSA_YEARS_ENDING_MARCH = (2023, 2024, 2025, 2026)

ENGLAND = {
    "geography_id": "E92000001",
    "geography_level": "country",
    "geography_name": "England",
    "geography_vintage": "current",
}

# Publisher band labels (Tables 1.1 and 1.2, column 'Price band (GBP m)') and
# the slug each fact's property_value_band filter carries.
OBR_BANDS = (
    ("2.0 to 2.5", "gbp_2m_to_2_5m", "GBP 2m to GBP 2.5m"),
    ("2.5 to 3.5", "gbp_2_5m_to_3_5m", "GBP 2.5m to GBP 3.5m"),
    ("3.5 to 5.0", "gbp_3_5m_to_5m", "GBP 3.5m to GBP 5m"),
    ("Over 5", "over_gbp_5m", "Over GBP 5m"),
)
OBR_BAND_YEARS = (2028, 2029, 2030)

# Table 1.5 lines: (line text prefix, value id, label, record kind, parent). The
# parent is documentation only; the 'of which' label carries it on the fact.
OBR_COSTING_LINES = (
    ("Static costing", "static_costing", "Static costing", "total", None),
    (
        "Behavioural response",
        "behavioural_response",
        "Behavioural response",
        "detail",
        None,
    ),
    (
        "Price capitalisation, bunching, and supply impacts",
        "price_capitalisation_bunching_and_supply",
        "of which: price capitalisation, bunching, and supply impacts",
        "detail",
        "behavioural_response",
    ),
    (
        "adjustments",
        "compliance_appeals_and_support_scheme",
        "of which: compliance, appeals and support scheme adjustments",
        "detail",
        "behavioural_response",
    ),
    (
        "Other tax heads impact",
        "other_tax_heads",
        "of which: other tax heads impact",
        "detail",
        "behavioural_response",
    ),
    (
        "Post-behavioural costing",
        "post_behavioural_costing",
        "Post-behavioural costing",
        "total",
        None,
    ),
)
OBR_COSTING_YEARS = (2026, 2027, 2028, 2029, 2030)

# Workbook sheet, measure family, property type slug, publisher wording.
HPSSA_SHEETS = (
    ("1a", "sales_count", "all", "all residential property types"),
    ("1b", "sales_count", "detached", "detached houses"),
    ("1c", "sales_count", "semi_detached", "semi-detached houses"),
    ("1d", "sales_count", "terraced", "terraced houses"),
    ("1e", "sales_count", "flat_maisonette", "flats/maisonettes"),
    ("2a", "median_price", "all", "all residential property types"),
    ("2b", "median_price", "detached", "detached houses"),
    ("2c", "median_price", "semi_detached", "semi-detached houses"),
    ("2d", "median_price", "terraced", "terraced houses"),
    ("2e", "median_price", "flat_maisonette", "flats/maisonettes"),
)
HPSSA_MEASURES = {
    "sales_count": {
        "measure_id": "residential_property_sales",
        "label": "Number of residential property sales",
        "concept": "ons.hpssa.residential_property_sales",
        "unit": "count",
        "aggregation": "sum",
        "concept_evidence_notes": (
            "Count of residential property sales registered with HM Land Registry "
            "in the four consecutive quarters ending in March (cover sheet), "
            "standard price paid transactions at market value, by the property "
            "type of the table."
        ),
    },
    "median_price": {
        "measure_id": "median_price_paid",
        "label": "Median price paid",
        "concept": "ons.hpssa.median_price_paid",
        "unit": "gbp",
        "aggregation": "median",
        "concept_evidence_notes": (
            "Median price paid (GBP) over the same sales. The publisher prints "
            "[x] where there were fewer than five sales of the type in the year "
            "(cover sheet notes); no fact is emitted for those cells."
        ),
    },
}


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


def constraint(variable: str, value: str, label: str) -> dict:
    """Carry a publisher classification as a first-class equality constraint."""
    return {"variable": variable, "operator": "==", "value": value, "label": label}


def fiscal_period(opening_year: int, label: str) -> dict:
    """Stamp a UK fiscal year by its opening year, keeping the publisher label."""
    return {
        "period_type": "fiscal_year",
        "period": opening_year,
        "period_coverage": {
            "start_date": f"{opening_year}-04-01",
            "end_date": f"{opening_year + 1}-03-31",
            "basis": "fiscal",
            "source_period_label": label,
            "notes": "period.value stores the opening year of the publisher period.",
        },
    }


# --------------------------------------------------------------------------- OBR


def obr_document_rows() -> list[dict]:
    """Parse the pinned PDF exactly as the package parser does."""
    artifact = SourceArtifactMetadata(
        source_name="obr",
        source_table="",
        source_file=OBR_PDF,
        url=None,
        vintage="",
        sha256="",
        size_bytes=0,
        extracted_at="",
        extraction_method="",
    )
    cells = source_cells_from_pdf_text_numbers(
        (OBR_DATA / OBR_PDF).read_bytes(), artifact
    )
    rows: dict[int, dict[int, object]] = {}
    for cell in cells:
        rows.setdefault(cell.row_number, {})[cell.column_number] = cell.raw_value
    return [
        {
            "row_number": row_number,
            "page": values[1],
            "line": values[2],
            "text": values[3],
            "number_text": values[4],
            "value": values[5],
        }
        for row_number, values in sorted(rows.items())
        if row_number > 1
    ]


def obr_line_numbers(
    rows: list[dict], *, page: int, prefix: str, count: int
) -> list[dict]:
    """Return the number rows of the one PDF line that starts with ``prefix``."""
    lines = {
        (row["page"], row["line"])
        for row in rows
        if row["page"] == page and str(row["text"]).startswith(prefix)
    }
    assert len(lines) == 1, (page, prefix, lines)
    (key,) = lines
    numbers = [row for row in rows if (row["page"], row["line"]) == key]
    assert len(numbers) == count, (prefix, [row["number_text"] for row in numbers])
    return numbers


def obr_guards(row: dict, ordinal: int, count: int) -> list[dict]:
    return [
        {
            "column": "A",
            "row": row["row_number"],
            "expected_value": row["page"],
            "label": "PDF page",
        },
        {
            "column": "D",
            "row": row["row_number"],
            "expected_value": row["number_text"],
            "label": f"number {ordinal} of {count} on the line",
        },
    ]


def obr_record_set(
    *,
    family: str,
    opening_year: int,
    entity_role: str,
    groupby: str,
    rows: list[dict],
    measure: dict,
    extra: dict | None = None,
) -> dict:
    record_set_id = f"{OBR_PREFIX}.{family}.fy{opening_year}"
    payload = {
        "record_set_id": record_set_id,
        "provenance_class": "model_output",
        "assertion": "source_projection",
        "record_set_spec_id": f"{record_set_id}.v1",
        "source_record_id_prefix": record_set_id,
        "sheet_name": "document_numbers",
        **fiscal_period(opening_year, f"{opening_year}-{(opening_year + 1) % 100:02}"),
        **ENGLAND,
        "entity": "dwelling",
        "entity_role": entity_role,
        "domain": "council_tax",
        "groupby_dimension": groupby,
    }
    if extra:
        payload.update(extra)
    payload["rows"] = rows
    payload["measures"] = [measure]
    return payload


def build_obr() -> None:
    rows = obr_document_rows()
    record_sets = []

    for table, page, basis, basis_label in (
        ("1.1", 2, "static", "static, before behavioural responses"),
        ("1.2", 5, "post_behaviour", "post-behaviour"),
    ):
        lines = {
            band: obr_line_numbers(
                rows, page=page, prefix=band, count=5 if band != "Over 5" else 4
            )
            for band, _, _ in OBR_BANDS
        }
        total = obr_line_numbers(
            rows, page=page, prefix="Total estimated properties in scope", count=3
        )
        for year_index, opening_year in enumerate(OBR_BAND_YEARS):
            selected = []
            for ordinal, (band, slug, band_label) in enumerate(OBR_BANDS):
                numbers = lines[band]
                offset = 2 if band != "Over 5" else 1
                number = numbers[offset + year_index]
                selected.append(
                    {
                        "value_id": slug,
                        "label": band_label,
                        "ordinal": ordinal,
                        "row_number": number["row_number"],
                        "table_record_kind": "detail",
                        "expected_row_header_column": "C",
                        "expected_row_header": number["text"],
                        "filters": {"property_value_band": slug},
                        "constraints": [
                            constraint(
                                "property_value_band", slug, "Property value band"
                            )
                        ],
                        "guard_cells": obr_guards(
                            number, offset + year_index + 1, len(numbers)
                        ),
                    }
                )
            number = total[year_index]
            selected.append(
                {
                    "value_id": "total",
                    "label": "Total estimated properties in scope",
                    "ordinal": len(OBR_BANDS),
                    "row_number": number["row_number"],
                    "table_record_kind": "total",
                    "expected_row_header_column": "C",
                    "expected_row_header": number["text"],
                    "guard_cells": obr_guards(number, year_index + 1, len(total)),
                }
            )
            record_sets.append(
                obr_record_set(
                    family=f"properties_in_scope.{basis}",
                    opening_year=opening_year,
                    entity_role="hvcts_property_in_scope",
                    groupby="property_value_band",
                    rows=selected,
                    extra={
                        "shared_filters": {"behaviour_basis": basis},
                        "shared_constraints": [
                            constraint("behaviour_basis", basis, "Behaviour basis")
                        ],
                    },
                    measure={
                        "measure_id": "properties_in_scope",
                        "label": "Estimated properties in scope (thousands)",
                        "ordinal": 0,
                        "column": "E",
                        "source_column_id": "numeric_value",
                        "concept": "obr.hvcts_costing.properties_in_scope",
                        "source_concept": "obr.hvcts_costing.properties_in_scope",
                        "concept_relation": "source_label",
                        "concept_authority": "obr",
                        "concept_evidence_url": OBR_EVIDENCE_URL,
                        "concept_evidence_notes": (
                            f"OBR Table {table} 'Estimated properties in scope by band, "
                            f"{'static' if basis == 'static' else 'post-behaviour'}', "
                            f"thousands, {basis_label}. Properties in England valued "
                            "over GBP 2 million by the Valuation Office in 2026 prices "
                            "(paragraph 1.3), after the assumed exemptions (paragraph "
                            "1.5)."
                        ),
                        "unit": "count",
                        "aggregation": "sum",
                        "expected_cell_type": "number",
                        "value_scale": 1000,
                    },
                )
            )

    costing_numbers = {
        value_id: obr_line_numbers(rows, page=7, prefix=prefix, count=5)
        for prefix, value_id, _, _, _ in OBR_COSTING_LINES
    }
    for year_index, opening_year in enumerate(OBR_COSTING_YEARS):
        selected = []
        for ordinal, (_, value_id, label, kind, parent) in enumerate(OBR_COSTING_LINES):
            number = costing_numbers[value_id][year_index]
            row = {
                "value_id": value_id,
                "label": label,
                "ordinal": ordinal,
                "row_number": number["row_number"],
                "table_record_kind": kind,
                "expected_row_header_column": "C",
                "expected_row_header": number["text"],
                "filters": {"costing_line": value_id},
                "constraints": [constraint("costing_line", value_id, "Costing line")],
                "guard_cells": obr_guards(number, year_index + 1, 5),
            }
            selected.append(row)
        record_sets.append(
            obr_record_set(
                family="costing",
                opening_year=opening_year,
                entity_role="hvcts_property_in_scope",
                groupby="costing_line",
                rows=selected,
                measure={
                    "measure_id": "psnb_impact",
                    "label": "Costing, GBP million (negative = reduction in PSNB)",
                    "ordinal": 0,
                    "column": "E",
                    "source_column_id": "numeric_value",
                    "concept": "obr.hvcts_costing.psnb_impact",
                    "source_concept": "obr.hvcts_costing.psnb_impact",
                    "concept_relation": "source_label",
                    "concept_authority": "obr",
                    "concept_evidence_url": OBR_EVIDENCE_URL,
                    "concept_evidence_notes": (
                        "OBR Table 1.5 'Costing of high value council tax surcharge', "
                        "GBP million. The table's note: a negative figure means a "
                        "reduction in PSNB, and the impacts are rounded to the "
                        "nearest GBP 5 million. The three 'of which' lines partition "
                        "the behavioural response; static plus behavioural is the "
                        "post-behavioural costing."
                    ),
                    "unit": "gbp",
                    "aggregation": "sum",
                    "expected_cell_type": "number",
                    "value_scale": 1000000,
                },
            )
        )

    # Parameters stated in the text (paragraph 1.13). The note dates none of
    # them; they are the costing's assumptions for the charge, which starts in
    # 2028-29, so they carry that year.
    stated = (
        (
            "non_owner_occupied_share",
            4,
            "around 40 per cent of properties liable to the tax are non-owner-occupied",
            2,
            0,
            "Share of liable properties that are non-owner-occupied",
            "obr.hvcts_costing.non_owner_occupied_share",
            "share",
            "Paragraph 1.13: 'SDLT data shows that around 40 per cent of properties "
            "liable to the tax are non-owner-occupied'.",
            "hvcts_property_in_scope",
            None,
        ),
        (
            "non_uk_resident_owner_share",
            4,
            "owners (14 per cent of properties impacted by the charge)",
            1,
            0,
            "Share of properties impacted by the charge with non-UK resident owners",
            "obr.hvcts_costing.non_uk_resident_owner_share",
            "share",
            "Paragraph 1.13: 'Non-UK resident property owners (14 per cent of "
            "properties impacted by the charge) are assumed to be high-wealth owners "
            "and able to pay the charge'.",
            "hvcts_property_in_scope",
            None,
        ),
        (
            "support_scheme_take_up",
            5,
            "and the costing assumes a 75 per cent take up rate from the eligible",
            1,
            0,
            "Assumed support scheme take-up among eligible households",
            "obr.hvcts_costing.support_scheme_take_up",
            "rate",
            "Paragraph 1.13: the support scheme is assumed available to households "
            "with net income under GBP 30,000 a year, with 'a 75 per cent take up "
            "rate from the eligible households'.",
            "hvcts_support_scheme_eligible_household",
            {
                "variable": "household_net_income",
                "operator": "<",
                "value": 30000,
                "unit": "gbp_per_year",
                "label": "Net household income under GBP 30,000 a year",
            },
        ),
    )
    for (
        family,
        page,
        prefix,
        count,
        index,
        label,
        concept,
        aggregation,
        notes,
        entity_role,
        income_constraint,
    ) in stated:
        numbers = obr_line_numbers(rows, page=page, prefix=prefix, count=count)
        number = numbers[index]
        extra = None
        if income_constraint:
            threshold = obr_line_numbers(
                rows,
                page=4,
                prefix="households with net income under £30,000 per year will be able",
                count=1,
            )[0]
            extra = {"shared_constraints": [income_constraint]}
        row = {
            "value_id": family,
            "label": label,
            "ordinal": 0,
            "row_number": number["row_number"],
            "table_record_kind": "total",
            "expected_row_header_column": "C",
            "expected_row_header": number["text"],
            "guard_cells": obr_guards(number, index + 1, count),
        }
        if income_constraint:
            row["guard_cells"].append(
                {
                    "column": "D",
                    "row": threshold["row_number"],
                    "expected_value": threshold["number_text"],
                    "label": "support scheme income threshold",
                }
            )
        record_sets.append(
            obr_record_set(
                family=family,
                opening_year=2028,
                entity_role=entity_role,
                groupby="costing_parameter",
                rows=[row],
                extra=extra,
                measure={
                    "measure_id": family,
                    "label": label,
                    "ordinal": 0,
                    "column": "E",
                    "source_column_id": "numeric_value",
                    "concept": concept,
                    "source_concept": concept,
                    "concept_relation": "source_label",
                    "concept_authority": "obr",
                    "concept_evidence_url": OBR_EVIDENCE_URL,
                    "concept_evidence_notes": notes,
                    "unit": "percent",
                    "aggregation": aggregation,
                    "expected_cell_type": "number",
                },
            )
        )
        record_sets[-1]["period_coverage"]["notes"] = (
            "period.value stores the opening year of 2028-29, the charge's first "
            "year; the note states the parameter without a year."
        )
        if entity_role == "hvcts_support_scheme_eligible_household":
            record_sets[-1]["entity"] = "household"

    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "obr-hvcts-costing-april-2026",
        "label": (
            "OBR costing of the high value council tax surcharge: properties in scope "
            "by value band (static and post-behaviour), the costing, and stated "
            "parameters, 2026-27 to 2030-31"
        ),
        "dimension_labels": {
            "property_value_band": "Property value band",
            "behaviour_basis": "Behaviour basis",
            "costing_line": "High value council tax surcharge costing line",
            "costing_parameter": "Costing parameter",
        },
        "dimension_value_labels": {
            "property_value_band": {slug: label for _, slug, label in OBR_BANDS},
            "behaviour_basis": {
                "static": "Static, before behavioural responses",
                "post_behaviour": "Post-behaviour",
            },
        },
        "artifact": {
            "source_name": "obr",
            "source_table": (
                "Supplementary forecast information release: costing of high value "
                "council tax surcharge, Tables 1.1, 1.2 and 1.5 and paragraph 1.13"
            ),
            "resource_package": "db",
            "resource_directory": "data/obr/hvcts_costing_april_2026",
            "manifest": "manifest.yaml",
            "vintage": "supplementary_forecast_information_2026_04_02",
            "extracted_at": "2026-10-12",
            "extraction_method": "PDF text-line number extraction",
            "parser": "pdf_text_numbers",
            "artifact_year": 2026,
        },
        "record_sets": record_sets,
    }
    write_package(OBR_PACKAGE, payload, OBR_HEADER)


OBR_HEADER = """\
# OBR supplementary forecast information release 'Costing of high value council tax
# surcharge' (2 April 2026), for PolicyEngine/chronicle#343 section 5. The surcharge
# (announced at Budget 2025) is an annual charge from April 2028 on properties in England
# valued over GBP 2 million by the Valuation Office in 2026 prices, in four bands from
# GBP 2,500 to GBP 7,500 a year (paragraph 1.3), so the facts are stamped England.
#
# Ported, every cell:
# - Table 1.1, estimated properties in scope by band, static, thousands, 2028-29 to
#   2030-31 (four bands and the total);
# - Table 1.2, the same post-behaviour;
# - Table 1.5, the costing in GBP million, 2026-27 to 2030-31: static costing,
#   behavioural response and its three 'of which' lines, and the post-behavioural costing.
#   The table's note: a negative figure is a reduction in PSNB (a yield to the
#   Exchequer), and impacts are rounded to the nearest GBP 5 million.
# Ported from the text (paragraph 1.13), as the issue asks:
# - around 40 per cent of liable properties are non-owner-occupied (SDLT data);
# - non-UK resident owners hold 14 per cent of the properties the charge affects;
# - the support scheme take-up of 75 per cent, among households with net income under
#   GBP 30,000 a year (carried as the fact's constraint).
# The note dates none of the paragraph 1.13 parameters; they carry 2028-29, the charge's
# first year, and each record set says so.
#
# Not ported: Table 1.3 (the charge rates are policy parameters, and the other lines are
# modelling assumptions the issue does not ask for), Table 1.4 (the CPI growth and house
# price index determinants the costing used, which are economy forecasts rather than
# costing outputs), and the paragraph percentages that Table 1.3 restates.
#
# All are HMRC costings certified by the OBR: provenance model_output, assertion
# source_projection.
"""


# ------------------------------------------------------------------------ HPSSA


def build_hpssa() -> None:
    workbook = load_workbook(HPSSA_DATA / HPSSA_XLSX, read_only=True)
    record_sets = []
    suppressed: dict[str, int] = {}
    seats: list[tuple[str, str]] | None = None

    for sheet, family, property_type, wording in HPSSA_SHEETS:
        values = list(workbook[sheet].iter_rows(values_only=True))
        title = values[0][0]
        assert title.startswith(f"Table {sheet} - "), title
        header = values[2]
        assert header[:2] == ("Area Code", "Area Name"), header[:2]
        sheet_seats = [(row[0], row[1]) for row in values[3:]]
        if seats is None:
            seats = sheet_seats
            assert len(seats) == 575, len(seats)
            assert all(re.fullmatch(r"(E14001|W07000)\d{3}", code) for code, _ in seats)
        assert sheet_seats == seats, sheet

        for year_ending in HPSSA_YEARS_ENDING_MARCH:
            label = f"Year ending Mar {year_ending}"
            column_index = header.index(label)
            column = get_column_letter(column_index + 1)
            opening_year = year_ending - 1
            record_set_id = f"{HPSSA_PREFIX}.{family}.{property_type}.fy{opening_year}"
            rows = []
            for offset, (code, name) in enumerate(seats):
                value = values[3 + offset][column_index]
                if value == "[x]":
                    suppressed[sheet] = suppressed.get(sheet, 0) + 1
                    continue
                assert isinstance(value, (int, float)), (sheet, code, label, value)
                row = {
                    "value_id": code.lower(),
                    "label": name,
                    "ordinal": len(rows),
                    "row_number": 4 + offset,
                    "expected_row_header_column": "A",
                    "expected_row_header": code,
                    "geography_id": code,
                    "geography_level": "constituency",
                    "geography_name": name,
                    "geography_vintage": "pcon_2024",
                    "table_record_kind": "total",
                }
                if not rows:
                    row["guard_cells"] = [
                        {
                            "column": "A",
                            "row": 1,
                            "expected_value": title,
                            "label": "table title naming the measure and property type",
                        }
                    ]
                rows.append(row)

            payload = {
                "record_set_id": record_set_id,
                "provenance_class": "administrative",
                "record_set_spec_id": f"{record_set_id}.v1",
                "source_record_id_prefix": record_set_id,
                "sheet_name": sheet,
                **fiscal_period(opening_year, label),
                "geography_id": "K04000001",
                "geography_level": "country",
                "geography_name": "England and Wales",
                "geography_vintage": "current",
                "entity": "dwelling",
                "entity_role": "residential_property_sale",
                "domain": "residential_property_transactions",
                "groupby_dimension": "geography",
            }
            payload["period_coverage"]["notes"] = (
                "Sales registered in the four consecutive quarters ending in March; "
                "period.value stores the opening year."
            )
            if property_type != "all":
                payload["shared_filters"] = {"property_type": property_type}
                payload["shared_constraints"] = [
                    constraint("property_type", property_type, "Property type")
                ]
            measure = dict(HPSSA_MEASURES[family])
            payload["measures"] = [
                {
                    "measure_id": measure["measure_id"],
                    "label": f"{measure['label']}, {wording}",
                    "ordinal": 0,
                    "column": column,
                    "source_column_id": label,
                    "concept": measure["concept"],
                    "unit": measure["unit"],
                    "aggregation": measure["aggregation"],
                    "expected_cell_type": "number",
                    "expected_column_header_row": 3,
                    "expected_column_header": label,
                    "concept_evidence_notes": measure["concept_evidence_notes"],
                }
            ]
            payload["rows"] = rows
            record_sets.append(payload)

    print("HPSSA suppressed cells skipped:", suppressed)
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "ons-hpssa-pcon24-year-ending-march-2026",
        "label": (
            "ONS house price statistics for small areas by parliamentary constituency "
            "(2024 boundaries), England and Wales: residential property sales and "
            "median price paid by property type, years ending March 2023 to 2026"
        ),
        "dimension_labels": {
            "geography": "Geography",
            "property_type": "Property Type",
        },
        "dimension_value_labels": {
            "property_type": {
                "detached": "Detached houses",
                "semi_detached": "Semi-detached houses",
                "terraced": "Terraced houses",
                "flat_maisonette": "Flats/maisonettes",
            }
        },
        "artifact": {
            "source_name": "ons",
            "source_table": (
                "House price statistics for small areas by parliamentary constituency, "
                "year ending December 1995 to year ending March 2026, Tables 1a to 2e"
            ),
            "resource_package": "db",
            "resource_directory": "data/ons/hpssa_pcon24_year_ending_march_2026",
            "manifest": "manifest.yaml",
            "vintage": "hpssa_year_ending_march_2026",
            "extracted_at": "2026-10-12",
            "extraction_method": (
                "xlsx used-range cell parse restricted to the sales-count and "
                "median-price worksheets"
            ),
            "parser": "xlsx_used_range",
            "sheets": [sheet for sheet, *_ in HPSSA_SHEETS],
            "artifact_year": 2026,
        },
        "record_sets": record_sets,
    }
    write_package(HPSSA_PACKAGE, payload, HPSSA_HEADER)


HPSSA_HEADER = """\
# ONS 'House price statistics for small areas by parliamentary constituency' (formerly HPSSA
# datasets 21, 24 and 26), edition year ending March 2026, released 17 September 2026, for
# PolicyEngine/chronicle#343 section 3. ONS computes the statistics from HM Land Registry
# Price Paid Data: the count and median price of residential sales registered in four
# consecutive quarters, England and Wales.
#
# Boundaries: the workbook's 575 rows carry July 2024 constituency codes (543 E14001xxx and
# 32 W07000xxx), the set Microcosm's geography uses, so rows are stamped pcon_2024.
#
# Ported: Tables 1a to 1e (number of sales) and 2a to 2e (median price paid), all property
# types and detached, semi-detached, terraced and flats/maisonettes, for the four rolling
# years ending in March 2023, 2024, 2025 and 2026. A year ending in March is a UK fiscal
# year, so each carries fiscal_year with its opening year and the publisher label. One
# record set per table and year; the property type rides on shared_filters and
# shared_constraints, and each record set's first row guards the table title that names it.
#
# Not ported: the other 118 rolling years back to year ending December 1995 (each later
# quarter's year overlaps the March years, and the issue's use is the latest year and its
# neighbours), and Tables 3a to 3e (lower quartile price, not asked for).
#
# Suppression: the publisher prints [x] where a seat had fewer than five sales of a type in
# the year (cover sheet). Those cells emit no fact. Counts of zero are published values and
# are ported.
#
# The workbook has no England and Wales total row, so the issue's parity check (seat sales
# against the national total in the same file) cannot be run inside it; the tests pin the
# seat sum instead.
"""


if __name__ == "__main__":
    build_obr()
    build_hpssa()
