"""Generate the source packages for PolicyEngine/chronicle#408, the UK land value inputs.

Run from the repository root:

    uv run python scripts/build_uk_408_packages.py

``--check`` compares the generated YAML with the committed files instead of writing.
Each package is written from its pinned artifact, read with Chronicle's own parsers, so
every row number, column and guard cell below is one the package parser sees.

- ``mhclg-land-value-estimates-2023``: MHCLG's land value estimates for policy appraisal
  2023, all eight sheets (item 1).
- ``voa-council-tax-bands-2026``, ``voa-council-tax-property-types-2026`` and
  ``voa-council-tax-build-periods-2026``: the VOA's Council Tax stock of properties 2026,
  tables CTSOP1.0 and 2.0, 3.0 and 4.0, at every geography they print (item 3). The three
  small-area zips are raw-only registrations under db/data/voa/ctsop*_lsoa_2026.
- ``mhclg-epc-d3-domestic-2026-q3`` and ``mhclg-live-table-126-dwelling-density-2026``:
  EPC live table D3's domestic lodgements, floor area and habitable rooms, and Live Table
  126's dwelling stock density (item 7).
- ``mhclg-council-tax-collection-by-authority-2025-26`` and
  ``mhclg-council-tax-qrc4-2025-26``: MHCLG's Tables 6a and 9a; and the per-authority rows
  of the pinned Welsh Table 2 (both years) and SLGFS Tables 2.8 and 2.11, written as a
  block after those packages' own record sets (item 4).
"""

from __future__ import annotations

import argparse
import json
import re
import textwrap
from functools import cache
from pathlib import Path

import yaml
from openpyxl.utils import column_index_from_string, get_column_letter

from chronicle.geography_names import canonical_geography_level
from chronicle.sources.cells import (
    SourceArtifactMetadata,
    source_cells_from_ods,
    source_cells_from_xlsx,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-11-04"
ISSUE = "PolicyEngine/chronicle#408"

# Labels of the dimensions that filters and constraints name.
FILTER_LABELS = {
    "site_density_scenario": "Site density scenario",
    "new_build_price_percentile": "Percentile of new-build house price per square metre",
    "agricultural_land_grade": "Agricultural land grade",
    "office_accommodation_type": "Office accommodation type",
    "retail_location_type": "Urban/suburban type",
    "council_tax_band": "Council tax band",
    "geography_match": "Geography match",
    "voa_property_type": "Property type",
    "voa_bedrooms": "Number of bedrooms",
    "voa_build_period": "Build period",
    "billing_authority_class": "Billing authority class",
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
        lines += textwrap.wrap(
            " ".join(paragraph.split()), width=88, break_on_hyphens=False
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


def xlsx_grid(
    directory: str, sheets: tuple[str, ...]
) -> dict[tuple[str, int, str], object]:
    filename, path = manifest_file(directory)
    cells = source_cells_from_xlsx(path.read_bytes(), metadata(filename), sheets=sheets)
    return grid_of(cells)


def ods_grid(directory: str) -> dict[tuple[str, int, str], object]:
    filename, path = manifest_file(directory)
    return grid_of(source_cells_from_ods(path.read_bytes(), metadata(filename)))


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


def constraints_for(filters: dict) -> list[dict]:
    return [
        {"variable": key, "operator": "==", "value": value, "label": FILTER_LABELS[key]}
        for key, value in filters.items()
    ]


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
        record["shared_constraints"] = constraints_for(shared_filters)
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
    ordinal: int = 0,
    value_scale: int | None = None,
    header: object = None,
    header_row: int = 1,
    filters: dict | None = None,
) -> dict:
    spec = {
        "measure_id": measure_id,
        "label": label,
        "ordinal": ordinal,
        "column": column,
        "source_column_id": measure_id,
    }
    if filters:
        spec["source_column_dimensions"] = dict(filters)
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
    if filters:
        spec["filters"] = dict(filters)
        spec["constraints"] = constraints_for(filters)
    spec["expected_cell_type"] = "number"
    return spec


def area_row(
    value_id: str,
    label: str,
    row: int,
    header_column: str,
    header: object,
    geography: dict,
    *,
    ordinal: int,
    guards: list[dict] | None = None,
    filters: dict | None = None,
) -> dict:
    """A table row for one area; a row that a filter narrows is a detail row."""
    spec = {
        "value_id": value_id,
        "label": label,
        "ordinal": ordinal,
        "row_number": row,
        "expected_row_header_column": header_column,
        "expected_row_header": header,
        **geography,
        "table_record_kind": "detail" if filters else "total",
    }
    if filters:
        spec["filters"] = dict(filters)
        spec["constraints"] = constraints_for(filters)
    if guards:
        spec["guard_cells"] = guards
    return spec


def guard(column: str, row: int, value: object, label: str) -> dict:
    return {"column": column, "row": row, "expected_value": value, "label": label}


def subsets(
    record_set_id: str,
    rows: list[tuple[dict, frozenset[str]]],
    measures: list[dict],
    build,
) -> list[dict]:
    """One record set for the rows that print every measure, and one per other pattern.

    A cell the publisher does not report (MHCLG's '-') is not a value, so a row emits
    facts only for the measures it prints. As in the VOA's 2025 CTSOP1.1 package, rows
    that print every measure share the ``full`` record set and each other pattern gets
    a ``subset_<n>`` record set with only the measures its rows print; a row that prints
    none is left out.
    """
    every = frozenset(spec["measure_id"] for spec in measures)
    patterns: dict[frozenset[str], list[dict]] = {}
    for row, printed in rows:
        if printed:
            patterns.setdefault(printed, []).append(row)
    ordered = sorted(
        patterns.items(),
        key=lambda item: (item[0] != every, min(row["row_number"] for row in item[1])),
    )
    record_sets = []
    for number, (printed, members) in enumerate(ordered):
        suffix = "full" if printed == every else f"subset_{number}"
        kept = [spec for spec in measures if spec["measure_id"] in printed]
        record_sets.append(build(f"{record_set_id}.{suffix}", members, kept))
    return record_sets


def slug(text: str) -> str:
    return (
        "".join(c if c.isalnum() else "_" for c in text.lower())
        .strip("_")
        .replace("__", "_")
        .replace("__", "_")
    )


def write(directory: str, text: str) -> None:
    path = PACKAGES / directory / "source_package.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ------------------------------------------------ 1. MHCLG land value estimates 2023

LVE_DIRECTORY = "mhclg/land_value_estimates_2023"
LVE_PAGE = (
    "https://www.gov.uk/government/publications/"
    "land-value-estimates-for-policy-appraisal-2023"
)
LVE_GUIDE = f"{LVE_PAGE}/land-value-estimates-for-policy-appraisal-guidelines-for-use"
LVE_RESIDENTIAL = "Residential"
LVE_FLOOR = "Residential (adj for floor)"
LVE_SHEETS = (
    LVE_RESIDENTIAL,
    LVE_FLOOR,
    "Industrial",
    "Distribution",
    "Agriculture",
    "Office",
    "Retail",
    "Car Park",
)
LVE_VALUATION_DATE = "2023-10-01T00:00:00"
LVE_PERIOD = {
    "period_type": "month",
    "period": "2023-10",
    "period_coverage": {
        "start_date": "2023-10-01",
        "end_date": "2023-10-01",
        "basis": "calendar",
        "source_period_label": "valuation date 1 October 2023",
    },
}
LVE_ENGLAND = {
    "geography_id": "E92000001",
    "geography_level": "country",
    "geography_name": "England",
    "geography_vintage": "gss_2023",
}
LVE_NOT_MARKET = (
    "MHCLG, Land value estimates for policy appraisal: guidelines for use (16 March "
    "2026): the estimates value a hypothetical 1 hectare site 'with services provided up "
    "to the boundary, without contamination or abnormal development costs ... with "
    "planning permission granted', for use in economic appraisal. 'These land values do "
    "not represent the market value of land', and they 'are therefore not directly "
    "comparable with the 2019 land value estimates for policy appraisal, or previous "
    "publications.' Valuation date 1 October 2023."
)
LVE_RESIDENTIAL_NOTES = (
    f"{LVE_NOT_MARKET} Residential values come from MHCLG's residual land valuation "
    "model: the gross development value less development costs, for a site with a net "
    "developable area of 80% of the gross (outside London), under a low, central "
    "('Medium') and high site density scenario, at the lower quartile, 40th percentile, "
    "median, 60th percentile and upper quartile of new-build house price per square "
    "metre in the council area. Sheet 'Residential' is the estimate before MHCLG's "
    "minimum 'floor value'; it does not report negative values ('a site may not be "
    "viable'), so those cells emit no fact."
)
LVE_FLOOR_NOTES = (
    f"{LVE_NOT_MARKET} Sheet 'Residential (adj for floor)', 'Residential Land - "
    "Adjusted for Floor Values': the same estimates with MHCLG's minimum 'floor value' "
    "applied ('A minimum floor value for each estimate has been applied for each "
    "estimate for use in economic appraisal'), designed so that land value uplift "
    "calculations 'give a credible lower bound result'."
)
LVE_DENSITY_NOTES = (
    "MHCLG, Land value estimates for policy appraisal 2023, sheet 'Residential': site "
    "density (dwellings per hectare) under the low, central ('Medium') and high scenarios "
    "for each council area. The central scenario is the implied average density of "
    "developments in the area over the last 10 years (net additional dwellings and land "
    "use change statistics); the low and high scenarios vary it using Glenigan data. A "
    "density floor of 30 and a ceiling of 400 dwellings per hectare apply. The sheet "
    "'Residential (adj for floor)' prints the same densities."
)
LVE_FILTERS = (
    "site_density_scenario",
    "new_build_price_percentile",
    "agricultural_land_grade",
    "office_accommodation_type",
    "retail_location_type",
)
LVE_DENSITIES = (("low", "Low "), ("medium", "Medium "), ("high", "High "))
LVE_PERCENTILES = (
    ("p25", 25, "25th percentile"),
    ("p40", 40, "40th percentile"),
    ("p50", "50 (Median)", "median"),
    ("p60", 60, "60th percentile"),
    ("p75", 75, "75th percentile"),
)
# Value columns under each density heading: low H:L, medium M:Q, high R:V.
LVE_VALUE_COLUMNS = {"low": "HIJKL", "medium": "MNOPQ", "high": "RSTUV"}
LVE_DENSITY_COLUMNS = {"low": "E", "medium": "F", "high": "G"}
LVE_HEADER = f"""
MHCLG, Land value estimates for policy appraisal 2023 (published 16 March 2026,
valuation date 1 October 2023, England), the eight data sheets of its XLSX, for {ISSUE}
item 1. Written by scripts/build_uk_408_packages.py.

These are MHCLG's modelled values of a hypothetical serviced 1 hectare development site
with planning permission, for economic appraisal. The guidelines say they 'do not
represent the market value of land' and are not directly comparable with the 2019
edition or earlier ones, so every record set is provenance class model_output. The
residential values are MHCLG's residual valuation model; the non-residential ones are the
VOA's valuations of selected locations, procured by MHCLG.

Residential (295 council areas, no Isles of Scilly): the site density (dwellings per
hectare) under the low, 'Medium' (central) and high scenarios, and under each the value
in GBP per hectare at the 25th, 40th, 50th, 60th and 75th percentiles of new-build house
price per square metre. 'Residential' is the estimate before MHCLG's minimum 'floor
value' and prints '-' where the residual is negative ('Negative values are not
reported'); those cells emit no fact. 'Residential (adj for floor)' applies the floor;
its densities repeat the first sheet's and are asserted equal rather than ported twice.
Councils carry the codes printed, current at the valuation date: Barnsley E08000016 and
Sheffield E08000019, which ONS replaced with E08000038 and E08000039 in 2025 after a
boundary change.

Non-residential, GBP per hectare: Industrial, Office and Retail for the seven major
commercial centres and 102 other built-up areas (ONS BUA 2022 codes, Chester's
cross-border K08000001 among them) and ten London locations (the publisher's names, no
codes); Office by accommodation type and Retail by urban or suburban type in the major
commercial centres; Distribution for the nine English regions; Agriculture for the nine
regions by land grade (Low is ALC grades 4 and 5, Medium 3a and 3b, High 1 and 2); Car
Park for 109 locations named by postcode district. Office and Retail print '-' where the
value is negative, and those cells emit no fact.
"""


def lve_value(text: object) -> float | int | None:
    """A printed value, or None for MHCLG's '-' (not reported)."""
    if isinstance(text, str) and text.strip() == "-":
        return None
    assert isinstance(text, (int, float)), text
    return text


def lve_authority_rows(grid: dict, sheet: str) -> list[tuple[int, str, str]]:
    """(row, code, name) of each council area on a residential sheet."""
    found = [
        (row, code, grid[(sheet, row, "D")])
        for (name, row, column), code in grid.items()
        if name == sheet
        and column == "C"
        and isinstance(code, str)
        and code[:1] == "E"
        and code[1:3] in {"06", "07", "08", "09"}
    ]
    return sorted(found)


def lve_authority_geography(code: str, name: str) -> dict:
    return {
        "geography_id": code,
        "geography_level": "local_authority",
        "geography_name": name,
        "geography_vintage": "lad_2023",
    }


def lve_record_set(record_set_id: str, sheet: str, rows, measures, **context) -> dict:
    return record_set(
        record_set_id,
        provenance_class="model_output",
        sheet_name=sheet,
        geography=LVE_ENGLAND,
        domain="land_value",
        rows=rows,
        measures=measures,
        **LVE_PERIOD,
        **context,
    )


def lve_residential(grid: dict) -> list[dict]:
    record_sets = []
    authorities = lve_authority_rows(grid, LVE_RESIDENTIAL)
    assert len(authorities) == 295, len(authorities)
    assert [code for _, code, _ in authorities] == [
        code for _, code, _ in lve_authority_rows(grid, LVE_FLOOR)
    ]
    for sheet in (LVE_RESIDENTIAL, LVE_FLOOR):
        assert grid[(sheet, 3, "B")] == LVE_VALUATION_DATE
        assert (grid[(sheet, 5, "C")], grid[(sheet, 5, "D")]) == (
            "LA Code",
            "Local Authority Name",
        )
    # Site densities, from the first sheet; the second prints the same numbers.
    density_measures = [
        measure(
            f"site_density_{density}",
            f"Site density, {density} scenario (dwellings per hectare)",
            LVE_DENSITY_COLUMNS[density],
            concept="mhclg.residential_site_density",
            source_concept="mhclg.residential_site_density",
            authority="mhclg",
            evidence_url=LVE_PAGE,
            notes=LVE_DENSITY_NOTES,
            unit="dwellings_per_hectare",
            aggregation="mean",
            ordinal=ordinal,
            header=header,
            header_row=5,
            filters={"site_density_scenario": density},
        )
        for ordinal, (density, header) in enumerate(LVE_DENSITIES)
    ]
    rows = []
    for ordinal, (row, code, name) in enumerate(authorities):
        for density, _ in LVE_DENSITIES:
            column = LVE_DENSITY_COLUMNS[density]
            assert (
                grid[(LVE_FLOOR, row, column)] == grid[(LVE_RESIDENTIAL, row, column)]
            )
            assert isinstance(grid[(LVE_RESIDENTIAL, row, column)], int)
        rows.append(
            area_row(
                slug(f"{code} {name}"),
                name,
                row,
                "C",
                code,
                lve_authority_geography(code, name),
                ordinal=ordinal,
            )
        )
    record_sets.append(
        lve_record_set(
            "mhclg.lve_2023.residential.site_density",
            LVE_RESIDENTIAL,
            rows,
            density_measures,
            entity="dwelling",
            entity_role="residential_development_site",
            groupby_dimension="mhclg.local_authority",
        )
    )
    for sheet, key, concept, notes in (
        (
            LVE_RESIDENTIAL,
            "residential_before_floor",
            "mhclg.residential_land_value_before_floor",
            LVE_RESIDENTIAL_NOTES,
        ),
        (
            LVE_FLOOR,
            "residential_floor_adjusted",
            "mhclg.residential_land_value_floor_adjusted",
            LVE_FLOOR_NOTES,
        ),
    ):
        for density, _ in LVE_DENSITIES:
            columns = LVE_VALUE_COLUMNS[density]
            measures = [
                measure(
                    f"{density}_density_{percentile}",
                    f"Land value, {density} site density, {label} of new-build "
                    "house price per square metre (GBP per hectare)",
                    columns[ordinal],
                    concept=concept,
                    source_concept=concept,
                    authority="mhclg",
                    evidence_url=LVE_GUIDE,
                    notes=notes,
                    unit="gbp_per_hectare",
                    aggregation="mean",
                    ordinal=ordinal,
                    header=header,
                    header_row=5,
                    filters={
                        "site_density_scenario": density,
                        "new_build_price_percentile": percentile,
                    },
                )
                for ordinal, (percentile, header, label) in enumerate(LVE_PERCENTILES)
            ]
            members = []
            for ordinal, (row, code, name) in enumerate(authorities):
                printed = frozenset(
                    spec["measure_id"]
                    for spec in measures
                    if lve_value(grid[(sheet, row, spec["column"])]) is not None
                )
                members.append(
                    (
                        area_row(
                            slug(f"{code} {name}"),
                            name,
                            row,
                            "C",
                            code,
                            lve_authority_geography(code, name),
                            ordinal=ordinal,
                        ),
                        printed,
                    )
                )
            record_sets += subsets(
                f"mhclg.lve_2023.{key}.{density}_density",
                members,
                measures,
                lambda record_set_id, rows, kept, sheet=sheet: lve_record_set(
                    record_set_id,
                    sheet,
                    rows,
                    kept,
                    entity="dwelling",
                    entity_role="residential_development_site",
                    groupby_dimension="mhclg.local_authority",
                ),
            )
    return record_sets


def lve_bua_geography(code: str, name: str) -> dict:
    return {
        "geography_id": code,
        "geography_level": "statistical_scope",
        "geography_name": name.strip(),
        "geography_vintage": "bua_2022",
    }


def lve_london_geography(name: str) -> dict:
    return {
        "geography_id": f"mhclg-lve-2023-london:{slug(name)}",
        "geography_level": "statistical_scope",
        "geography_name": name.strip(),
        "geography_vintage": "mhclg_lve_2023_london_location",
    }


def lve_region_geography(code: str, name: str) -> dict:
    return {
        "geography_id": code,
        "geography_level": "region",
        "geography_name": name.strip(),
        "geography_vintage": "gss_2023",
    }


def lve_sheet_rows(grid: dict, sheet: str) -> list[int]:
    return sorted({row for (name, row, _column) in grid if name == sheet})


def lve_london_rows(grid: dict, sheet: str) -> list[int]:
    """The rows of the 'London Locations' block, between its header and the notes."""
    rows = lve_sheet_rows(grid, sheet)
    (start,) = [
        row for row in rows if grid.get((sheet, row, "B")) == "London Locations"
    ]
    assert str(grid[(sheet, start + 1, "B")]).strip() == "Location"
    found = []
    for row in rows:
        if row <= start + 1:
            continue
        label = grid.get((sheet, row, "B"))
        if label in (None, "") or str(label).startswith("Notes"):
            break
        found.append(row)
    assert len(found) == 10, (sheet, found)
    return found


def lve_bua_rows(grid: dict, sheet: str) -> list[int]:
    return [
        row
        for row in lve_sheet_rows(grid, sheet)
        if str(grid.get((sheet, row, "C")) or "")[:3] in {"E63", "K08"}
    ]


def lve_commercial(
    grid: dict,
    sheet: str,
    key: str,
    concept: str,
    entity_role: str,
    description: str,
    type_column: str | None,
    type_filter: str | None,
) -> list[dict]:
    """Industrial, Office or Retail: built-up areas, then the London locations."""
    value_column = "F" if type_column else "E"
    header = "£/ha*" if type_column else "£/ha"
    notes = (
        f"{LVE_NOT_MARKET} {description} Non-residential values are VOA valuations of "
        "selected locations, procured by MHCLG. Negative values are not reported."
    )

    def value_measure(column: str, header_row: int, header_text: str) -> dict:
        return measure(
            f"{key}_land_value",
            f"{description.split(' – ')[0]} land value (GBP per hectare)",
            column,
            concept=concept,
            source_concept=concept,
            authority="mhclg",
            evidence_url=LVE_GUIDE,
            notes=notes,
            unit="gbp_per_hectare",
            aggregation="mean",
            header=header_text,
            header_row=header_row,
        )

    def build(record_set_id: str, rows: list[dict], measures: list[dict]) -> dict:
        return lve_record_set(
            record_set_id,
            sheet,
            rows,
            measures,
            entity="firm",
            entity_role=entity_role,
            groupby_dimension="mhclg.lve_location",
        )

    assert grid[(sheet, 3, "B")] == LVE_VALUATION_DATE
    assert grid[(sheet, 5, "C")] == "BUA Code"
    assert grid[(sheet, 5, value_column)] == header, grid[(sheet, 5, value_column)]
    record_sets = []
    plain, typed = [], []
    for row in lve_bua_rows(grid, sheet):
        code, name = grid[(sheet, row, "C")], grid[(sheet, row, "D")]
        value = lve_value(grid[(sheet, row, value_column)])
        kind = grid.get((sheet, row, type_column)) if type_column else None
        if value is None:
            continue
        if kind:
            filters = {type_filter: slug(kind)}
            typed.append(
                area_row(
                    slug(f"{code} {name} {kind}"),
                    f"{name.strip()}, {kind.strip()}",
                    row,
                    "C",
                    code,
                    lve_bua_geography(code, name),
                    ordinal=len(typed),
                    guards=[guard(type_column, row, kind, FILTER_LABELS[type_filter])],
                    filters=filters,
                )
            )
        else:
            plain.append(
                area_row(
                    slug(f"{code} {name}"),
                    name.strip(),
                    row,
                    "C",
                    code,
                    lve_bua_geography(code, name),
                    ordinal=len(plain),
                )
            )
    record_sets.append(
        build(
            f"mhclg.lve_2023.{key}.built_up_areas",
            plain,
            [value_measure(value_column, 5, header)],
        )
    )
    if typed:
        record_sets.append(
            build(
                f"mhclg.lve_2023.{key}.major_commercial_centres",
                typed,
                [value_measure(value_column, 5, header)],
            )
        )
    london = []
    rows = lve_london_rows(grid, sheet)
    london_header = grid[(sheet, rows[0] - 1, "C")]
    for row in rows:
        name = grid[(sheet, row, "B")]
        if lve_value(grid[(sheet, row, "C")]) is None:
            continue
        london.append(
            area_row(
                slug(name),
                name.strip(),
                row,
                "B",
                name,
                lve_london_geography(name),
                ordinal=len(london),
            )
        )
    record_sets.append(
        build(
            f"mhclg.lve_2023.{key}.london_locations",
            london,
            [value_measure("C", rows[0] - 1, london_header)],
        )
    )
    return record_sets


def lve_distribution(grid: dict) -> dict:
    sheet = "Distribution"
    assert grid[(sheet, 3, "B")] == LVE_VALUATION_DATE
    assert grid[(sheet, 5, "D")] == "£/ha"
    rows = [
        area_row(
            slug(grid[(sheet, row, "C")]),
            grid[(sheet, row, "C")].strip(),
            row,
            "B",
            grid[(sheet, row, "B")],
            lve_region_geography(grid[(sheet, row, "B")], grid[(sheet, row, "C")]),
            ordinal=ordinal,
        )
        for ordinal, row in enumerate(
            row
            for row in lve_sheet_rows(grid, sheet)
            if str(grid.get((sheet, row, "B")) or "").startswith("E12")
        )
    ]
    assert len(rows) == 9
    return lve_record_set(
        "mhclg.lve_2023.distribution.regions",
        sheet,
        rows,
        [
            measure(
                "distribution_land_value",
                "Distribution land value (GBP per hectare)",
                "D",
                concept="mhclg.distribution_land_value",
                source_concept="mhclg.distribution_land_value",
                authority="mhclg",
                evidence_url=LVE_GUIDE,
                notes=(
                    f"{LVE_NOT_MARKET} Distribution: 'a distribution warehouse with "
                    "adjoining motorway links'; values for the nine English regions."
                ),
                unit="gbp_per_hectare",
                aggregation="mean",
                header="£/ha",
                header_row=5,
            )
        ],
        entity="firm",
        entity_role="distribution_warehouse_site",
        groupby_dimension="mhclg.lve_location",
    )


def lve_agriculture(grid: dict) -> dict:
    sheet = "Agriculture"
    assert grid[(sheet, 3, "B")] == LVE_VALUATION_DATE
    rows = [
        area_row(
            slug(grid[(sheet, row, "C")]),
            grid[(sheet, row, "C")].strip(),
            row,
            "B",
            grid[(sheet, row, "B")],
            lve_region_geography(grid[(sheet, row, "B")], grid[(sheet, row, "C")]),
            ordinal=ordinal,
        )
        for ordinal, row in enumerate(
            row
            for row in lve_sheet_rows(grid, sheet)
            if str(grid.get((sheet, row, "B")) or "").startswith("E12")
        )
    ]
    assert len(rows) == 9
    notes = (
        f"{LVE_NOT_MARKET} Agriculture: 'farmland in a typical agricultural location "
        "within the area', GBP per hectare by grade: 'Low' is Agricultural Land "
        "Classification grades 4 and 5, 'Medium' grades 3a and 3b, 'High' grades 1 and 2."
    )
    return lve_record_set(
        "mhclg.lve_2023.agriculture.regions",
        sheet,
        rows,
        [
            measure(
                f"agricultural_land_value_{grade}",
                f"Agricultural land value, {grade} grade (GBP per hectare)",
                column,
                concept="mhclg.agricultural_land_value",
                source_concept="mhclg.agricultural_land_value",
                authority="mhclg",
                evidence_url=LVE_GUIDE,
                notes=notes,
                unit="gbp_per_hectare",
                aggregation="mean",
                ordinal=ordinal,
                header=grade.title(),
                header_row=6,
                filters={"agricultural_land_grade": grade},
            )
            for ordinal, (grade, column) in enumerate(
                (("low", "D"), ("medium", "E"), ("high", "F"))
            )
        ],
        entity="firm",
        entity_role="agricultural_land",
        groupby_dimension="mhclg.lve_location",
    )


def lve_car_park(grid: dict) -> dict:
    sheet = "Car Park"
    assert grid[(sheet, 3, "B")] == LVE_VALUATION_DATE
    assert str(grid[(sheet, 5, "B")]).strip() == "Location"
    rows = []
    for row in lve_sheet_rows(grid, sheet):
        label = grid.get((sheet, row, "B"))
        if row <= 5 or not label:
            continue
        # 'AL3 - St Albans'; one label prints 'LS1- Leeds'.
        match = re.fullmatch(r"([A-Z]{1,2}[0-9][0-9A-Z]?)\s*-\s*(\S.*)", str(label))
        assert match, label
        district = match.group(1)
        rows.append(
            area_row(
                slug(district),
                str(label).strip(),
                row,
                "B",
                label,
                {
                    "geography_id": f"postcode-district:{district}",
                    "geography_level": "statistical_scope",
                    "geography_name": str(label).strip(),
                    "geography_vintage": "postcode_district",
                },
                ordinal=len(rows),
            )
        )
    assert len(rows) == 109, len(rows)
    return lve_record_set(
        "mhclg.lve_2023.car_park.locations",
        sheet,
        rows,
        [
            measure(
                "car_park_land_value",
                "Car park land value (GBP per hectare)",
                "C",
                concept="mhclg.car_park_land_value",
                source_concept="mhclg.car_park_land_value",
                authority="mhclg",
                evidence_url=LVE_GUIDE,
                notes=(
                    f"{LVE_NOT_MARKET} Car parks: 'a typical commercial car park', open "
                    "surface parking valued by the investment method on 385 spaces per "
                    "hectare, net of 6.5% maintenance and running costs. Locations are "
                    "named by postcode district and town, as printed."
                ),
                unit="gbp_per_hectare",
                aggregation="mean",
                header="£/ha",
                header_row=5,
            )
        ],
        entity="firm",
        entity_role="car_park_site",
        groupby_dimension="mhclg.lve_location",
    )


def build_land_values() -> str:
    grid = xlsx_grid(LVE_DIRECTORY, LVE_SHEETS)
    record_sets = lve_residential(grid)
    record_sets += lve_commercial(
        grid,
        "Industrial",
        "industrial",
        "mhclg.industrial_land_value",
        "industrial_development_site",
        "Industrial – a typical urban/suburban brownfield location with industrial or "
        "warehouse use.",
        None,
        None,
    )
    record_sets.append(lve_distribution(grid))
    record_sets.append(lve_agriculture(grid))
    record_sets += lve_commercial(
        grid,
        "Office",
        "office",
        "mhclg.office_land_value",
        "office_development_site",
        "Office – a town and city centre office in urban locations and an out of town "
        "office in smaller urban and rural locations; the seven major commercial centres "
        "by Primary, Secondary and Tertiary accommodation, the other built-up areas for "
        "the most prevalent office type for the location, London on the city central "
        "appraisal.",
        "E",
        "office_accommodation_type",
    )
    record_sets += lve_commercial(
        grid,
        "Retail",
        "retail",
        "mhclg.retail_land_value",
        "retail_development_site",
        "Retail – typical two-storey shops; the seven major commercial centres by "
        "urban (city or town centre) and suburban units, the other built-up areas and "
        "London on city or town centre assumptions.",
        "E",
        "retail_location_type",
    )
    record_sets.append(lve_car_park(grid))
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "mhclg-land-value-estimates-2023",
        "label": "MHCLG land value estimates for policy appraisal 2023 (valuation date "
        "1 October 2023)",
        "dimension_labels": {
            "mhclg.local_authority": "Local authority",
            "mhclg.lve_location": "Location",
            **{key: FILTER_LABELS[key] for key in LVE_FILTERS},
        },
        "artifact": artifact(
            "mhclg",
            "Land value estimates for policy appraisal 2023",
            LVE_DIRECTORY,
            "lve_2023",
            "xlsx_used_range",
            "xlsx used-range cell parse of the eight data sheets",
            2023,
            sheets=list(LVE_SHEETS),
        ),
        "record_sets": record_sets,
    }
    return render(LVE_HEADER, payload)


# ------------------------------------------ 3. VOA Council Tax: stock of properties 2026

VOA_DIRECTORY = "voa/council_tax_bands_2026"
VOA_PROPERTY_TYPES_DIRECTORY = "voa/council_tax_property_types_2026"
VOA_BUILD_PERIODS_DIRECTORY = "voa/council_tax_build_periods_2026"
VOA_PAGE = (
    "https://www.gov.uk/government/statistics/council-tax-stock-of-properties-2026"
)
VOA_PERIOD = {
    "period_type": "month",
    "period": "2026-03",
    "period_coverage": {
        "start_date": "2026-03-31",
        "end_date": "2026-03-31",
        "basis": "calendar",
        "source_period_label": "as at 31 March 2026",
    },
}
VOA_ENGLAND_AND_WALES = {
    "geography_id": "K04000001",
    "geography_level": "country",
    "geography_name": "England and Wales",
    "geography_vintage": "gss_2025",
}
VOA_ROUNDING = (
    "All counts are rounded to the nearest 10, with counts between 1 and 4 suppressed "
    "and presented as [c]."
)
VOA_BAND_I = (
    "Council Tax band I is only used in the Council Tax Valuation List effective in "
    "Wales from 1 April 2005; England's band I cells are [z]."
)
VOA_SHEET_TITLES = {
    "CTSOP1_0": "number of properties by Council Tax band and administrative area as "
    "at 31 March 2026",
    "CTSOP2_0": "number of properties by Council Tax band, Westminster Parliamentary "
    "Constituency, and Region, as at 31 March 2026",
    "CTSOP3_0": "number of properties by Council Tax band, property type and "
    "administrative area as at 31 March 2026",
    "CTSOP4_0": "number of properties by Council Tax band, property build period and "
    "administrative area as at 31 March 2026",
}
VOA_BANDS = tuple("ABCDEFGHI")
# Not values: [z] is band I outside Wales, [c] a suppressed count of 1 to 4.
VOA_MARKERS = {"[z]", "[c]"}
# Geography kinds as note 1 names them, and the level and vintage each takes here.
VOA_KINDS = {
    "ENGWAL": ("country", "gss_2025"),
    "NATL": ("country", "gss_2025"),
    "REGL": ("region", "gss_2025"),
    "CTYMET": ("county", "gss_2025"),
    "LAUA": ("local_authority", "lad_2025"),
    "PCON": ("constituency", "pcon_2024"),
}
VOA_MATCH_LABELS = {
    "matched": "Properties whose postcode was matched to a Westminster constituency "
    "(note 15)",
    "unmatched": "Properties whose postcode could not be matched to a Westminster "
    "constituency (note 15)",
}
VOA_PROPERTY_TYPES = {
    "Bungalow": "bungalow",
    "Flat / Maisonette": "flat_maisonette",
    "Terraced House": "terraced_house",
    "Semi-Detached House": "semi_detached_house",
    "Detached House": "detached_house",
    "Annexe": "annexe",
    "Caravan/ Houseboat/ Mobile Home": "caravan_houseboat_mobile_home",
    "Unknown": "unknown",
}
VOA_BEDROOMS = {
    "1 Bedroom": "1_bedroom",
    "2 Bedrooms": "2_bedrooms",
    "3 Bedrooms": "3_bedrooms",
    "4 Bedrooms": "4_bedrooms",
    "5 Bedrooms": "5_bedrooms",
    "6+ Bedrooms": "6_plus_bedrooms",
    "Not Known": "not_known",
}
# The runs of columns that share record sets in CTSOP3.0 and CTSOP4.0. A row repeats in
# each run's record sets and a measure in each of a run's printed-cell patterns; these
# runs keep the two packages near their smallest.
VOA_PROPERTY_TYPE_GROUPS = (
    ("bungalow_1_to_3_bedrooms", "F", "H"),
    ("bungalow_4_plus_not_known_and_total", "I", "M"),
    ("flat_maisonette_1_to_3_bedrooms", "N", "P"),
    ("flat_maisonette_4_plus_not_known_and_total", "Q", "U"),
    ("terraced_house_1_to_3_bedrooms", "V", "X"),
    ("terraced_house_4_plus_not_known_and_total", "Y", "AC"),
    ("semi_detached_house_1_to_3_bedrooms", "AD", "AF"),
    ("semi_detached_house_4_plus_not_known_and_total", "AG", "AK"),
    ("detached_house_1_to_3_bedrooms", "AL", "AN"),
    ("detached_house_4_plus_not_known_and_total", "AO", "AS"),
    ("annexe_caravan_unknown_and_all", "AT", "AW"),
)
VOA_BUILD_PERIOD_GROUPS = (
    ("built_before_1983", "F", "M"),
    ("built_1983_to_2013", "N", "U"),
    ("built_2014_to_2021", "V", "AC"),
    ("built_2022_to_2026_unknown_and_all", "AD", "AJ"),
)
VOA_HEADER_NOTES = """
All counts are rounded to the nearest 10, with counts between 1 and 4 suppressed and
presented as '[c]'; band I is used only in Wales's valuation list from 1 April 2005, and
England's band I cells are '[z]'. Neither marker is a value, so those cells emit no
fact. Areas carry the ONS codes and names the workbook prints (note markers dropped from
names): ENGWAL and NATL rows are countries, REGL regions, CTYMET counties, metropolitan
counties and Inner and Outer London (typed as regions, as other packages type them), LAUA billing authorities (Powys and
Carmarthenshire each combine three billing authorities, notes 13 and 14), PCON 2024
Westminster constituencies. Barnsley and Sheffield are E08000038 and E08000039, the codes
ONS gave them in 2025.
"""
VOA_BANDS_HEADER = f"""
VOA (HMRC Valuation Office statistics), Council Tax: stock of properties 2026, summary
tables (published 24 September 2026; counts from the Valuation Office's administrative
database as at 31 March 2026, England and Wales), sheets CTSOP1.0 and CTSOP2.0, for
{ISSUE} item 3. Written by scripts/build_uk_408_packages.py. The workbook's
CTSOP3.0 and CTSOP4.0 are the 2026 property-type and build-period packages.

CTSOP1.0 counts every property in the England (1993) and Wales (2005) valuation lists
by band and administrative area: England and Wales, the two countries, the nine English
regions, counties, and every billing authority. CTSOP2.0 assigns properties to
Westminster constituencies by postcode (ONS NSPL): its 575 constituency rows, and its
country and regional rows, which count only the properties matched to a constituency
and carry geography_match == matched. Its 'Unmatched' row (note 15) counts the rest,
on the England-and-Wales footprint with geography_match == unmatched, as in the
2025 package. Its England and Wales row repeats CTSOP1.0's and is asserted
equal rather than ported twice. The 2025 package's country and regional rows are
CTSOP2.0's, without the filter.

{VOA_HEADER_NOTES}
"""
VOA_PROPERTY_TYPES_HEADER = f"""
VOA (HMRC Valuation Office statistics), Council Tax: stock of properties 2026, summary
tables (published 24 September 2026, counts as at 31 March 2026, England and Wales),
sheet CTSOP3.0: the number of properties by Council Tax band and property type in each
administrative area, for {ISSUE} item 3. Written by
scripts/build_uk_408_packages.py; the artifact is the summary workbook the 2026
bands package pins.

Each area prints a row per band ('All', then A to H, and I in Wales) and a column per
property type and number of bedrooms ('Not Known', note 16: the type is known, the
bedrooms are not), each type's total, Annexe, Caravan/ Houseboat/ Mobile Home, Unknown
(note 17: attributes not recorded) and All Properties. Every cell is ported as printed
under voa.ct_stock_by_property_type, the band as council_tax_band (none on the 'All'
rows), the type as voa_property_type and the bedrooms as voa_bedrooms (none on a type's
total, neither on All Properties). The 'All' row and the All Properties column restate
CTSOP1.0's counts, which the tests assert. Record sets run per band and per group of
columns, each split by the cells its rows print.

{VOA_HEADER_NOTES}
"""
VOA_BUILD_PERIODS_HEADER = f"""
VOA (HMRC Valuation Office statistics), Council Tax: stock of properties 2026, summary
tables (published 24 September 2026, counts as at 31 March 2026, England and Wales),
sheet CTSOP4.0: the number of properties by Council Tax band and build period in each
administrative area, for {ISSUE} item 3. Written by
scripts/build_uk_408_packages.py; the artifact is the summary workbook the 2026
bands package pins.

Each area prints a row per band ('All', then A to H, and I in Wales) and a column per
build period as VOA classifies it (Pre 1900, then periods to 2000 to 2008, then single
years 2009 to 2026; the classification has no 1940 to 1944 period), Unknown (note 17)
and All properties. Every cell is ported as printed under voa.ct_stock_by_build_period,
the band as council_tax_band (none on the 'All' rows) and the period as
voa_build_period (single years as year_<yyyy>; none on All properties). The 'All' row
and the All properties column restate CTSOP1.0's counts, which the tests assert. Record
sets run per band and per group of columns, each split by the cells its rows print.

{VOA_HEADER_NOTES}
"""


@cache
def voa_grid() -> dict[tuple[str, int, str], object]:
    filename, path = manifest_file(VOA_DIRECTORY)
    return grid_of(source_cells_from_ods(path.read_bytes(), metadata(filename)))


def voa_sheet_rows(grid: dict, sheet: str) -> list[int]:
    """The sheet's data rows: those whose column A names a geography kind."""
    return sorted(
        row
        for (name, row, column), value in grid.items()
        if name == sheet and column == "A" and value in {*VOA_KINDS, "UNMD"}
    )


def voa_name(text: object) -> str:
    """An area name without its note marker ('Powys / Powys [note 13]')."""
    return re.sub(r"\s*\[note \d+\]$", "", str(text)).strip()


def voa_geography(kind: str, code: str, name: object) -> dict:
    level, vintage = VOA_KINDS[kind]
    if code.startswith("E13"):
        # Inner and Outer London print among the CTYMET rows; other packages type
        # them as regions.
        level = "region"
    return {
        "geography_id": code,
        "geography_level": level,
        "geography_name": voa_name(name),
        "geography_vintage": vintage,
    }


def voa_count(value: object) -> int | None:
    """A printed count, or None for a marker that is not a value."""
    if isinstance(value, str) and value in VOA_MARKERS:
        return None
    assert isinstance(value, int), value
    return value


def voa_slug(text: str) -> str:
    return slug(text.replace("+", " plus"))


def voa_notes(sheet: str, column_label: str, extra: str = "") -> str:
    table = sheet.replace("_", ".")
    if sheet in {"CTSOP3_0", "CTSOP4_0"}:
        # Thousands of measures repeat this; the package header carries the title.
        return (
            f"VOA, Council Tax: stock of properties 2026, table {table}, column "
            f"'{column_label}', as at 31 March 2026. {VOA_ROUNDING}"
        )
    return (
        f"VOA, Council Tax: stock of properties 2026, summary tables, table {table} "
        f"({VOA_SHEET_TITLES[sheet]}), column: {column_label}. {VOA_ROUNDING}"
        + (f" {extra}" if extra else "")
    )


def voa_record_set(record_set_id: str, sheet: str, rows, measures, **extra) -> dict:
    return record_set(
        record_set_id,
        provenance_class="administrative",
        sheet_name=sheet,
        geography=VOA_ENGLAND_AND_WALES,
        entity="dwelling",
        entity_role="banded_property",
        domain="council_tax_stock",
        groupby_dimension="voa.geography_row",
        rows=rows,
        measures=measures,
        **VOA_PERIOD,
        **extra,
    )


def voa_band_measures(grid: dict, sheet: str) -> list[dict]:
    """CTSOP1.0 and 2.0's band columns E to M and All properties, N."""
    measures = []
    for ordinal, band in enumerate(VOA_BANDS):
        column = chr(ord("E") + ordinal)
        assert grid[(sheet, 5, column)] == band
        measures.append(
            measure(
                f"band_{band.lower()}",
                f"Number of properties, Band {band}",
                column,
                concept=f"voa.ct_stock_band_{band.lower()}",
                source_concept=f"voa.ct_stock_band_{band.lower()}",
                authority="voa",
                evidence_url=VOA_PAGE,
                notes=voa_notes(
                    sheet, f"Band {band}", VOA_BAND_I if band == "I" else ""
                ),
                unit="count",
                aggregation="sum",
                ordinal=ordinal,
                header=band,
                header_row=5,
            )
        )
    assert grid[(sheet, 5, "N")] == "All properties"
    measures.append(
        measure(
            "all_properties",
            "Number of properties, All properties",
            "N",
            concept="voa.ct_stock_all_properties",
            source_concept="voa.ct_stock_all_properties",
            authority="voa",
            evidence_url=VOA_PAGE,
            notes=voa_notes(sheet, "All properties"),
            unit="count",
            aggregation="sum",
            ordinal=len(VOA_BANDS),
            header="All properties",
            header_row=5,
        )
    )
    return measures


def voa_printed(grid: dict, sheet: str, row: int, measures: list[dict]) -> frozenset:
    return frozenset(
        spec["measure_id"]
        for spec in measures
        if voa_count(grid[(sheet, row, spec["column"])]) is not None
    )


def voa_area_row(grid: dict, sheet: str, row: int, ordinal: int) -> dict:
    kind, code, name = (grid[(sheet, row, column)] for column in "ACD")
    if kind == "UNMD":
        spec = area_row(
            "unmatched",
            "Unmatched (properties not matched to a constituency)",
            row,
            "C",
            code,
            VOA_ENGLAND_AND_WALES,
            ordinal=ordinal,
            guards=[
                guard("A", row, kind, "geography kind"),
                guard("D", row, name, "area name"),
            ],
            filters={"geography_match": "unmatched"},
        )
    else:
        matched = sheet == "CTSOP2_0" and kind in {"NATL", "REGL"}
        spec = area_row(
            voa_slug(code),
            voa_name(name),
            row,
            "C",
            code,
            voa_geography(kind, code, name),
            ordinal=ordinal,
            guards=[
                guard("A", row, kind, "geography kind"),
                guard("D", row, name, "area name"),
            ],
            filters={"geography_match": "matched"} if matched else None,
        )
    for constraint in spec.get("constraints", ()):
        constraint["label"] = VOA_MATCH_LABELS[constraint["value"]]
    return spec


def build_bands() -> str:
    grid = voa_grid()
    record_sets = []
    for sheet in ("CTSOP1_0", "CTSOP2_0"):
        assert str(grid[(sheet, 1, "A")]).startswith(
            f"Table {sheet.replace('_', '.')}:"
        )
        measures = voa_band_measures(grid, sheet)
        rows = voa_sheet_rows(grid, sheet)
        if sheet == "CTSOP2_0":
            # Its England and Wales row is CTSOP1.0's, cell for cell.
            assert grid[(sheet, rows[0], "A")] == "ENGWAL"
            assert [grid[(sheet, rows[0], c)] for c in "CDEFGHIJKLMN"] == [
                grid[("CTSOP1_0", 6, c)] for c in "CDEFGHIJKLMN"
            ]
            rows = rows[1:]
        members = [
            (
                voa_area_row(grid, sheet, row, ordinal),
                voa_printed(grid, sheet, row, measures),
            )
            for ordinal, row in enumerate(rows)
        ]
        record_sets += subsets(
            f"voa.ctsop2026.{sheet.lower()}",
            members,
            measures,
            lambda record_set_id, rows, kept, sheet=sheet: voa_record_set(
                record_set_id, sheet, rows, kept
            ),
        )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "voa-council-tax-bands-2026",
        "label": "VOA Council Tax stock of properties 2026: properties by band, by "
        "administrative area and by constituency (CTSOP1.0, CTSOP2.0)",
        "dimension_labels": {
            "voa.geography_row": "Geography",
            "geography_match": "Geography match",
        },
        "dimension_value_labels": {
            "geography_match": {
                "matched": "Matched to a constituency",
                "unmatched": "Not matched to a constituency",
            }
        },
        "artifact": voa_artifact(
            "Council Tax: stock of properties 2026, summary tables CTSOP1.0 and "
            "CTSOP2.0 (band by administrative area and by constituency)"
        ),
        "record_sets": record_sets,
    }
    return render(VOA_BANDS_HEADER, payload)


def voa_artifact(source_table: str) -> dict:
    return artifact(
        "voa",
        source_table,
        VOA_DIRECTORY,
        "ctsop_2026",
        "ods_used_range",
        "ods whole-workbook used-range cell parse",
        2026,
    )


def voa_column_letters(first: str, last: str) -> list[str]:
    return [
        get_column_letter(index)
        for index in range(
            column_index_from_string(first), column_index_from_string(last) + 1
        )
    ]


def voa_property_type_filters(header: str) -> dict:
    """'Bungalow: 1 Bedroom' -> type and bedrooms; 'Bungalow' -> type; 'All Properties'
    -> nothing."""
    text = voa_name(header)
    if text == "All Properties":
        return {}
    kind, _, bedrooms = text.partition(": ")
    filters = {"voa_property_type": VOA_PROPERTY_TYPES[kind]}
    if bedrooms:
        filters["voa_bedrooms"] = VOA_BEDROOMS[bedrooms]
    return filters


def voa_build_period_filters(header: object) -> dict:
    """'Pre 1900' -> pre_1900; '1900 to 1918' -> 1900_to_1918; 2009 -> year_2009."""
    if header == "All properties":
        return {}
    if isinstance(header, int):
        return {"voa_build_period": f"year_{header}"}
    return {"voa_build_period": slug(voa_name(header))}


def voa_crossed_package(
    sheet: str,
    concept: str,
    groups: tuple[tuple[str, str, str], ...],
    filters_of,
) -> list[dict]:
    """CTSOP3.0 or 4.0: a record set per band and column group, split by printed cells."""
    grid = voa_grid()
    assert str(grid[(sheet, 1, "A")]).startswith(f"Table {sheet.replace('_', '.')}:")
    assert grid[(sheet, 5, "C")] == "ONS area code [note 3]"
    assert grid[(sheet, 5, "E")] == "Band"
    rows = voa_sheet_rows(grid, sheet)
    columns = [
        column
        for _, first, last in groups
        for column in voa_column_letters(first, last)
    ]
    # The groups cover every column from F to the sheet's last.
    after = get_column_letter(column_index_from_string(columns[-1]) + 1)
    assert columns[0] == "F" and grid.get((sheet, 5, after)) is None
    assert columns == voa_column_letters("F", columns[-1])
    measures = {}
    for ordinal, column in enumerate(columns):
        header = grid[(sheet, 5, column)]
        label = voa_name(header) if isinstance(header, str) else str(header)
        measures[column] = measure(
            voa_slug(label) if not isinstance(header, int) else f"year_{header}",
            f"Number of properties, {label}",
            column,
            concept=concept,
            source_concept=concept,
            authority="voa",
            evidence_url=VOA_PAGE,
            notes=voa_notes(sheet, str(header)),
            unit="count",
            aggregation="sum",
            ordinal=ordinal,
            header=header,
            header_row=5,
            filters=filters_of(header),
        )
    record_sets = []
    for band in ("All", *VOA_BANDS):
        band_rows = [row for row in rows if grid[(sheet, row, "E")] == band]
        shared = {} if band == "All" else {"council_tax_band": band}
        for group, first, last in groups:
            kept = [measures[column] for column in voa_column_letters(first, last)]
            members = []
            for ordinal, row in enumerate(band_rows):
                kind, code, name = (grid[(sheet, row, column)] for column in "ACD")
                members.append(
                    (
                        area_row(
                            voa_slug(code),
                            voa_name(name),
                            row,
                            "C",
                            code,
                            voa_geography(kind, code, name),
                            ordinal=ordinal,
                            guards=[guard("E", row, band, "Council Tax band")],
                        ),
                        voa_printed(grid, sheet, row, kept),
                    )
                )
            record_sets += subsets(
                f"voa.ctsop2026.{sheet.lower()}.band_{band.lower()}.{group}",
                members,
                kept,
                lambda record_set_id, rows, measures, shared=shared: voa_record_set(
                    record_set_id, sheet, rows, measures, shared_filters=shared
                ),
            )
    return record_sets


def build_property_types() -> str:
    record_sets = voa_crossed_package(
        "CTSOP3_0",
        "voa.ct_stock_by_property_type",
        VOA_PROPERTY_TYPE_GROUPS,
        voa_property_type_filters,
    )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "voa-council-tax-property-types-2026",
        "label": "VOA Council Tax stock of properties 2026: properties by band and "
        "property type, by administrative area (CTSOP3.0)",
        "dimension_labels": {
            "voa.geography_row": "Geography",
            "council_tax_band": "Council tax band",
            "voa_property_type": "Property type",
            "voa_bedrooms": "Number of bedrooms",
        },
        "dimension_value_labels": {
            "voa_property_type": {
                value: label for label, value in VOA_PROPERTY_TYPES.items()
            },
            "voa_bedrooms": {value: label for label, value in VOA_BEDROOMS.items()},
        },
        "artifact": voa_artifact(
            "Council Tax: stock of properties 2026, summary table CTSOP3.0 (band by "
            "property type and administrative area)"
        ),
        "record_sets": record_sets,
    }
    return render(VOA_PROPERTY_TYPES_HEADER, payload)


def build_build_periods() -> str:
    grid = voa_grid()
    record_sets = voa_crossed_package(
        "CTSOP4_0",
        "voa.ct_stock_by_build_period",
        VOA_BUILD_PERIOD_GROUPS,
        voa_build_period_filters,
    )
    periods = {}
    for column in voa_column_letters("F", "AI"):
        header = grid[("CTSOP4_0", 5, column)]
        (value,) = voa_build_period_filters(header).values()
        periods[value] = voa_name(header) if isinstance(header, str) else str(header)
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "voa-council-tax-build-periods-2026",
        "label": "VOA Council Tax stock of properties 2026: properties by band and "
        "build period, by administrative area (CTSOP4.0)",
        "dimension_labels": {
            "voa.geography_row": "Geography",
            "council_tax_band": "Council tax band",
            "voa_build_period": "Build period",
        },
        "dimension_value_labels": {"voa_build_period": periods},
        "artifact": voa_artifact(
            "Council Tax: stock of properties 2026, summary table CTSOP4.0 (band by "
            "build period and administrative area)"
        ),
        "record_sets": record_sets,
    }
    return render(VOA_BUILD_PERIODS_HEADER, payload)


# Local authority codes ONS retired before its December 2024 lookup (the register's),
# by the last December vintage that carried them: the reorganisations of 1 April 2019
# (Dorset, Suffolk, Somerset West and Taunton), 2020 (Buckinghamshire), 2021
# (Northamptonshire) and 2023 (Cumbria, North Yorkshire, Somerset).
RETIRED_LAD = {
    **dict.fromkeys(
        (
            "E06000028",
            "E06000029",
            "E07000048",
            "E07000049",
            "E07000050",
            "E07000051",
            "E07000052",
            "E07000053",
            "E07000190",
            "E07000191",
            "E07000201",
            "E07000204",
            "E07000205",
            "E07000206",
        ),
        "lad_2018",
    ),
    **dict.fromkeys(("E07000004", "E07000005", "E07000006", "E07000007"), "lad_2019"),
    **dict.fromkeys((f"E07000{n}" for n in range(150, 157)), "lad_2020"),
    **dict.fromkeys(
        (
            *(f"E070000{n}" for n in range(26, 32)),
            *(f"E07000{n}" for n in range(163, 170)),
            "E07000187",
            "E07000188",
            "E07000189",
            "E07000246",
        ),
        "lad_2022",
    ),
}
# ONS replaced Barnsley's and Sheffield's codes in 2025, after a boundary change.
NEW_LAD = {"E08000038": "lad_2025", "E08000039": "lad_2025"}


def lad_vintage(code: str) -> str:
    """The latest December ONS lookup that carries a local authority code."""
    if code in NEW_LAD:
        return NEW_LAD[code]
    if canonical_geography_level(code) == "local_authority":
        return "lad_2024"
    return RETIRED_LAD[code]


def local_authority(code: str, name: str) -> dict:
    return {
        "geography_id": code,
        "geography_level": "local_authority",
        "geography_name": str(name).strip(),
        "geography_vintage": lad_vintage(code),
    }


ENGLAND_AND_WALES = {
    "geography_id": "K04000001",
    "geography_level": "country",
    "geography_name": "England and Wales",
    "geography_vintage": "current",
}
ENGLAND = {
    "geography_id": "E92000001",
    "geography_level": "country",
    "geography_name": "England",
    "geography_vintage": "current",
}
WALES = {
    "geography_id": "W92000004",
    "geography_level": "country",
    "geography_name": "Wales",
    "geography_vintage": "current",
}
# D3 names regions without codes; these are their ONS codes.
REGION_CODES = {
    "North East": "E12000001",
    "North West": "E12000002",
    "Yorkshire and The Humber": "E12000003",
    "East Midlands": "E12000004",
    "West Midlands": "E12000005",
    "East of England": "E12000006",
    "London": "E12000007",
    "South East": "E12000008",
    "South West": "E12000009",
}


def region(code: str, name: str) -> dict:
    return {
        "geography_id": code,
        "geography_level": "region",
        "geography_name": str(name).strip(),
        "geography_vintage": "gss_2024",
    }


# ------------------------------------------------------------ 7a. EPC live table D3

D3_DIRECTORY = "mhclg/epc_d3_domestic_2026_q3"
D3_PAGE = (
    "https://www.gov.uk/government/statistical-data-sets/"
    "live-tables-on-energy-performance-of-buildings-certificates"
)
D3_NATIONAL = (
    ("D3_England_and_Wales", "england_and_wales", ENGLAND_AND_WALES),
    ("D3_England_Only", "england", ENGLAND),
    ("D3_Wales_Only", "wales", WALES),
)
D3_REGION = "D3_by_Region"
D3_LA = "D3_by_LA"
D3_SHEETS = tuple(sheet for sheet, _, _ in D3_NATIONAL) + (D3_REGION, D3_LA)
# Certificates whose region or authority the register does not record. D3_by_Region
# and D3_by_LA print the same 'Unknown' rows; parity puts them inside England.
D3_UNKNOWN = {
    "geography_id": "mhclg-epc-d3:england-area-unknown",
    "geography_level": "statistical_scope",
    "geography_name": "Unknown",
    "geography_vintage": "epc_d3_2026_q3",
}
D3_MEASURES = (
    (
        "lodgements",
        "Number Lodgements",
        "Number of domestic EPC lodgements",
        "mhclg.epc_domestic_lodgements",
        "count",
    ),
    (
        "total_floor_area",
        "Total Floor Area (m2)",
        "Total floor area of the lodged certificates (square metres)",
        "mhclg.epc_domestic_total_floor_area",
        "square_metres",
    ),
    (
        "habitable_rooms",
        "Number Habitable Rooms",
        "Number of habitable rooms on the lodged certificates",
        "mhclg.epc_domestic_habitable_rooms",
        "count",
    ),
)
D3_NOTES = (
    "MHCLG, Energy Performance of Buildings Certificates live table D3, 'Domestic "
    "Properties ... in each Year/Quarter to 30 September 2026' (published 29 October "
    "2026). Counts are of certificates lodged on the EPC register, not of dwellings: "
    "'The counts in the tables cover all EPCs whether valid or invalid (excluding "
    "cancelled reports), although be aware individual buildings may have more than one "
    "certificate.' 'Buildings only require an EPC when, sold, let or constructed. These "
    "statistics should, therefore, not be interpreted as a true representation of the "
    "whole of the building stock in England and Wales' (note 3). 'On the 20 September "
    "2021 the register transitioned to www.gov.uk, prior to this data were provided by a "
    "contractor (Landmark)' (note 1). 'Data are aligned to the address level data "
    "published on Open Data Communities, and as a result will reflect lower figures "
    "compared to previous publications for all quarters. The methodology for allocating "
    "regions and local authorities has been updated'. Quarters are calendar quarters "
    "(Q1=Jan-Mar), printed as 'YYYY/Q'."
)
D3_HEADER = f"""
MHCLG, Energy Performance of Buildings Certificates (EPC) live table D3, 'Domestic
Properties ... by Energy Use, Carbon Dioxide Emissions and Fuel Costs', to 30 September
2026 (published 29 October 2026), for {ISSUE} item 7. Written by
scripts/build_uk_408_packages.py.

Three columns of each sheet are ported: Number Lodgements, Total Floor Area (m2) and
Number Habitable Rooms. The energy use, carbon dioxide and fuel cost columns are not.
Each quarter is its own record set, 2008/4 to 2026/3 (calendar quarters, Q1=Jan-Mar).
The three national sheets (England and Wales, England, Wales) also print
calendar-year rows, 2009 to 2025, each the sum of its four quarters, which are ported as calendar_year facts; their
'(Total)' row sums every quarter since 2008/4 and has no stampable period, so it is left
out, as are D3_by_Region's all-period rows for each region.

D3 counts certificates lodged, not dwellings: a dwelling with several certificates counts
each time, and homes never sold, let or built since 2008 are absent. All certificates
count, valid or invalid, except cancelled reports.

D3_by_Region names regions without codes, mapped here to their ONS codes; its 'Unknown'
rows are certificates whose region the register does not record. D3_by_LA prints the
same 'Unknown' rows under the code 'Unknown', so they are ported once, from
D3_by_Region, and asserted equal; with them the regions and the authorities sum to
England. D3_by_LA's first column is headed 'Region' but holds the authority's name.
Authorities carry the code printed for each quarter: the register codes a lodgement to
the authority current when it was lodged, so retired districts stop and their
successors start at reorganisations, and Barnsley and Sheffield print as E08000016 and
E08000019 to 2025/4 and as E08000038 and E08000039 from 2025/4 (both codes in 2025/4).
Each code's geography_vintage is the latest December ONS lookup that carries it.
"""


def quarter_period(label: str) -> dict:
    year, quarter = (int(part) for part in label.split("/"))
    first = 3 * quarter - 2
    last_day = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[quarter]
    return {
        "period_type": "quarter",
        "period": f"{year}-Q{quarter}",
        "period_coverage": {
            "start_date": f"{year}-{first:02d}-01",
            "end_date": f"{year}-{last_day}",
            "basis": "calendar",
            "source_period_label": label,
        },
    }


def year_period(year: int) -> dict:
    return {
        "period_type": "calendar_year",
        "period": year,
        "period_coverage": {
            "start_date": f"{year}-01-01",
            "end_date": f"{year}-12-31",
            "basis": "calendar",
            "source_period_label": str(year),
        },
    }


def d3_measures(columns: str) -> list[dict]:
    return [
        measure(
            key,
            label,
            column,
            concept=concept,
            source_concept=concept,
            authority="mhclg",
            evidence_url=D3_PAGE,
            notes=D3_NOTES,
            unit=unit,
            aggregation="sum",
            ordinal=ordinal,
            header=header,
            header_row=4,
        )
        for ordinal, (column, (key, header, label, concept, unit)) in enumerate(
            zip(columns, D3_MEASURES)
        )
    ]


def d3_record_set(
    record_set_id: str, sheet: str, period: dict, rows: list[dict], columns: str
) -> dict:
    return record_set(
        record_set_id,
        provenance_class="administrative",
        sheet_name=sheet,
        geography=ENGLAND_AND_WALES,
        entity="dwelling",
        entity_role="domestic_epc_lodgement",
        domain="energy_performance_certificates",
        groupby_dimension="mhclg.epc_area",
        rows=rows,
        measures=d3_measures(columns),
        **period,
    )


def d3_numbers(grid: dict, sheet: str, row: int, columns: str) -> None:
    for column in columns:
        assert isinstance(grid[(sheet, row, column)], int), (sheet, row, column)


def sheet_rows(grid: dict, sheet: str) -> list[int]:
    return sorted({row for (name, row, _column) in grid if name == sheet and row > 4})


def d3_period_key(label: str) -> str:
    year, quarter = label.split("/")
    return f"{year}_q{quarter}"


def d3_national(grid: dict) -> list[dict]:
    record_sets = []
    for sheet, key, geography in D3_NATIONAL:
        assert [grid[(sheet, 4, column)] for column in "ABCDE"] == [
            "Year",
            "Quarter",
            *(header for _, header, _, _, _ in D3_MEASURES),
        ]
        years, quarters = [], []
        for row in sheet_rows(grid, sheet):
            year, quarter = grid[(sheet, row, "A")], grid.get((sheet, row, "B"))
            if year == "(Total)":
                continue
            d3_numbers(grid, sheet, row, "CDE")
            (quarters if quarter else years).append((row, year, quarter))
        assert [int(year) for _, year, _ in years] == list(range(2009, 2026))
        for row, year, _ in years:
            record_sets.append(
                d3_record_set(
                    f"mhclg.epc_d3_2026q3.{key}.calendar_{year}",
                    sheet,
                    year_period(int(year)),
                    [
                        area_row(
                            key,
                            geography["geography_name"],
                            row,
                            "A",
                            year,
                            geography,
                            ordinal=0,
                        )
                    ],
                    "CDE",
                )
            )
        for row, year, quarter in quarters:
            assert quarter.split("/")[0] == year, (sheet, row)
            record_sets.append(
                d3_record_set(
                    f"mhclg.epc_d3_2026q3.{key}.{d3_period_key(quarter)}",
                    sheet,
                    quarter_period(quarter),
                    [
                        area_row(
                            key,
                            geography["geography_name"],
                            row,
                            "B",
                            quarter,
                            geography,
                            ordinal=0,
                            guards=[guard("A", row, year, "Year")],
                        )
                    ],
                    "CDE",
                )
            )
    return record_sets


def d3_quarters(grid: dict) -> list[str]:
    sheet = D3_NATIONAL[0][0]
    return [
        grid[(sheet, row, "B")]
        for row in sheet_rows(grid, sheet)
        if grid.get((sheet, row, "B"))
    ]


def d3_regions(grid: dict) -> list[dict]:
    sheet = D3_REGION
    assert [grid[(sheet, 4, column)] for column in "ABCDE"] == [
        "Region",
        "Quarter",
        *(header for _, header, _, _, _ in D3_MEASURES),
    ]
    by_quarter: dict[str, list[dict]] = {}
    for row in sheet_rows(grid, sheet):
        name, quarter = grid[(sheet, row, "A")], grid.get((sheet, row, "B"))
        if not quarter:
            continue  # the all-period row for each region
        d3_numbers(grid, sheet, row, "CDE")
        geography = (
            D3_UNKNOWN if name == "Unknown" else region(REGION_CODES[name], name)
        )
        members = by_quarter.setdefault(quarter, [])
        members.append(
            area_row(
                slug(name),
                name,
                row,
                "A",
                name,
                geography,
                ordinal=len(members),
                guards=[guard("B", row, quarter, "Quarter")],
            )
        )
    assert list(by_quarter) == d3_quarters(grid)
    return [
        d3_record_set(
            f"mhclg.epc_d3_2026q3.regions.{d3_period_key(quarter)}",
            sheet,
            quarter_period(quarter),
            rows,
            "CDE",
        )
        for quarter, rows in by_quarter.items()
    ]


def d3_unknown_restated(grid: dict) -> list[tuple[int, int]]:
    """(LA row, region row) pairs: D3_by_LA's 'Unknown' rows restate D3_by_Region's."""
    regions = {
        grid[(D3_REGION, row, "B")]: row
        for row in sheet_rows(grid, D3_REGION)
        if grid[(D3_REGION, row, "A")] == "Unknown" and grid.get((D3_REGION, row, "B"))
    }
    pairs = []
    for row in sheet_rows(grid, D3_LA):
        if grid[(D3_LA, row, "B")] != "Unknown":
            continue
        assert grid[(D3_LA, row, "A")] == "Unknown"
        match = regions[grid[(D3_LA, row, "C")]]
        assert [grid[(D3_LA, row, column)] for column in "DEF"] == [
            grid[(D3_REGION, match, column)] for column in "CDE"
        ]
        pairs.append((row, match))
    assert len(pairs) == len(regions)
    return pairs


def d3_local_authorities(grid: dict) -> list[dict]:
    sheet = D3_LA
    assert [grid[(sheet, 4, column)] for column in "ABCDEF"] == [
        "Region",
        "Local Authority Code",
        "Quarter",
        *(header for _, header, _, _, _ in D3_MEASURES),
    ]
    d3_unknown_restated(grid)
    by_quarter: dict[str, list[dict]] = {quarter: [] for quarter in d3_quarters(grid)}
    for row in sheet_rows(grid, sheet):
        name, code, quarter = (grid[(sheet, row, column)] for column in "ABC")
        if code == "Unknown":
            continue
        d3_numbers(grid, sheet, row, "DEF")
        members = by_quarter[quarter]
        members.append(
            area_row(
                slug(code),
                str(name).strip(),
                row,
                "B",
                code,
                local_authority(code, name),
                ordinal=len(members),
                guards=[guard("C", row, quarter, "Quarter")],
            )
        )
    return [
        d3_record_set(
            f"mhclg.epc_d3_2026q3.local_authorities.{d3_period_key(quarter)}",
            sheet,
            quarter_period(quarter),
            rows,
            "DEF",
        )
        for quarter, rows in by_quarter.items()
    ]


def build_epc_d3() -> str:
    grid = ods_grid(D3_DIRECTORY)
    record_sets = d3_national(grid) + d3_regions(grid) + d3_local_authorities(grid)
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "mhclg-epc-d3-domestic-2026-q3",
        "label": "MHCLG EPC live table D3: domestic certificates lodged, floor area and "
        "habitable rooms, by quarter, to 30 September 2026",
        "dimension_labels": {"mhclg.epc_area": "Area"},
        "artifact": artifact(
            "mhclg",
            "Energy Performance of Buildings Certificates live table D3: domestic "
            "properties, to 30 September 2026",
            D3_DIRECTORY,
            "epc_d3_2026_q3",
            "ods_used_range",
            "ods whole-workbook used-range cell parse",
            2026,
        ),
        "record_sets": record_sets,
    }
    return render(D3_HEADER, payload)


# ------------------------------------------------------------- 7b. Live Table 126

LT126_DIRECTORY = "mhclg/live_table_126_dwelling_density_2026"
LT126_PAGE = (
    "https://www.gov.uk/government/statistical-data-sets/"
    "live-tables-on-dwelling-stock-including-vacants"
)
LT126_SHEET = "LT_126"
LT126_HEADER_ROW = 5
LT126_NOTES = (
    "MHCLG, Live Table 126, 'Dwelling stock density estimates by local authority "
    "district, England, 2011 - 2025' (published 21 May 2026): 'the number of dwellings "
    "per hectare as at 31 March by English local authority district from 2011 to 2025. "
    "Dwelling density is calculated for each area by dividing total dwelling stock (as "
    "published in Live Table 125) by land area in hectares (as published as "
    "AREALHECT).' The stock 'use[s] the Census as a baseline and apply annual net "
    "changes to the dwelling stock as measured by the related Housing supply: net "
    "additional dwellings statistics'. Column markers: '[p] These figures are "
    "provisional and subject to scheduled revisions and revisions pending the release of "
    "future census dwelling stock data.' '[r] These figures have been revised.' Cells "
    "marked '[x] Data is not available.' emit no fact. [note 7]: 'Net additional "
    "dwellings figures for 2023-24 were imputed for the local authority Ribble Valley due "
    "to a lack of data.'"
)
LT126_HEADER = f"""
MHCLG, Live Table 126, dwelling stock density estimates by local authority district,
England, 2011 to 2025 (published 21 May 2026; 'Source: Dwelling stock estimates in
England: 2025'), sheet LT_126, for {ISSUE} item 7. Written by
scripts/build_uk_408_packages.py.

Dwellings per hectare at 31 March of each year: the dwelling stock (Live Table 125)
divided by the land area in hectares (ONS AREALHECT). Each year column is its own record
set, a calendar_year period stamped 31 March, with the column's printed header kept as
the measure's expected header, so its markers stay: '[p]' provisional (2022 to 2025),
'[r]' revised (2024), and notes 2 to 4 on the 2019, 2020 and 2021 reorganisations. '[x]'
(data not available) emits no fact: each authority prints values only for the years it
existed in.

Rows are England, the regions, the counties and metropolitan counties, Inner and Outer
London and every local authority district, keyed by the 'New ONS code' and guarded by the
'Old ONS code' where one is printed. The table prints four codes twice: Cumberland,
Westmorland and Furness and North Yorkshire with identical rows, and Suffolk twice, the
first row without its 2023 value. Each is ported once, from the row that prints the most
values, and the other is asserted to agree wherever both print. Tyne and Wear prints
under E11000004, with values to 2022. Densities are ratios and are not additive.
"""

# County codes retired before 2024, by the last December vintage that carried them.
RETIRED_COUNTY = {
    "E10000009": "gss_2018",  # Dorset, 1 April 2019
    "E10000002": "gss_2019",  # Buckinghamshire, 1 April 2020
    "E10000021": "gss_2020",  # Northamptonshire, 1 April 2021
    "E10000006": "gss_2022",  # Cumbria, 1 April 2023
    "E10000023": "gss_2022",  # North Yorkshire, 1 April 2023
    "E10000027": "gss_2022",  # Somerset, 1 April 2023
    "E11000004": "gss_2022",  # Tyne and Wear, printed to 2022
}


def lt126_geography(code: str, name: str) -> dict:
    name = str(name).strip()
    if code == "E92000001":
        return dict(ENGLAND)
    if code.startswith("E12"):
        return region(code, name)
    if code[:3] in {"E06", "E07", "E08", "E09"}:
        return local_authority(code, name)
    if code[:3] in {"E10", "E11"}:
        return {
            "geography_id": code,
            "geography_level": "county",
            "geography_name": name,
            "geography_vintage": RETIRED_COUNTY.get(code, "gss_2024"),
        }
    assert code.startswith("E13"), code
    return {
        "geography_id": code,
        "geography_level": "region",
        "geography_name": name,
        "geography_vintage": "gss_2024",
    }


def lt126_year_columns(grid: dict) -> list[tuple[str, int, str]]:
    """(column, year, printed header) for each year column."""
    found = []
    for column in "DEFGHIJKLMNOPQR":
        header = grid[(LT126_SHEET, LT126_HEADER_ROW, column)]
        found.append((column, int(str(header)[:4]), header))
    assert [year for _, year, _ in found] == list(range(2011, 2026))
    assert grid[(LT126_SHEET, LT126_HEADER_ROW, "S")] == "Notes"
    return found


def lt126_value(value: object) -> float | None:
    if value == "[x]":
        return None
    assert isinstance(value, float), value
    return value


def lt126_rows(grid: dict) -> dict[str, int]:
    """The row ported for each code, and a check that its repeats agree with it."""
    columns = [column for column, _, _ in lt126_year_columns(grid)]
    rows: dict[str, list[int]] = {}
    for row in sorted({r for (s, r, _c) in grid if s == LT126_SHEET and r > 5}):
        rows.setdefault(grid[(LT126_SHEET, row, "B")], []).append(row)
    chosen = {}
    for code, found in rows.items():
        printed = {
            row: {
                column: lt126_value(grid[(LT126_SHEET, row, column)])
                for column in columns
            }
            for row in found
        }
        best = max(
            found,
            key=lambda row: (sum(v is not None for v in printed[row].values()), -row),
        )
        for row in found:
            assert grid[(LT126_SHEET, row, "C")] == grid[(LT126_SHEET, best, "C")]
            for column, value in printed[row].items():
                if value is not None and printed[best][column] is not None:
                    assert value == printed[best][column], (code, row, column)
                elif value is not None:
                    raise AssertionError(
                        (code, row, column, "printed only on a repeat")
                    )
        chosen[code] = best
    return chosen


def build_live_table_126() -> str:
    grid = ods_grid(LT126_DIRECTORY)
    sheet = LT126_SHEET
    assert [grid[(sheet, LT126_HEADER_ROW, column)] for column in "ABC"] == [
        "Old ONS code",
        "New ONS code",
        "Area",
    ]
    chosen = lt126_rows(grid)
    record_sets = []
    for column, year, header in lt126_year_columns(grid):
        rows = []
        for code, row in sorted(chosen.items(), key=lambda item: item[1]):
            if lt126_value(grid[(sheet, row, column)]) is None:
                continue
            old = grid.get((sheet, row, "A"))
            rows.append(
                area_row(
                    slug(code),
                    str(grid[(sheet, row, "C")]).strip(),
                    row,
                    "B",
                    code,
                    lt126_geography(code, grid[(sheet, row, "C")]),
                    ordinal=len(rows),
                    guards=[guard("A", row, old, "Old ONS code")] if old else None,
                )
            )
        marker = header[4:].strip()
        record_sets.append(
            record_set(
                f"mhclg.lt126_2026.dwelling_density.{year}",
                provenance_class="model_output",
                sheet_name=sheet,
                period_type="calendar_year",
                period=year,
                period_coverage={
                    "start_date": f"{year}-03-31",
                    "end_date": f"{year}-03-31",
                    "basis": "calendar",
                    "source_period_label": f"31 March {year}"
                    + (f" {marker}" if marker else ""),
                },
                geography=ENGLAND,
                entity="dwelling",
                entity_role="dwelling_stock",
                domain="dwelling_stock",
                groupby_dimension="mhclg.lt126_area",
                rows=rows,
                measures=[
                    measure(
                        "dwelling_density",
                        f"Dwelling stock density at 31 March {year}"
                        + (f" {marker}" if marker else "")
                        + " (dwellings per hectare)",
                        column,
                        concept="mhclg.dwelling_stock_density",
                        source_concept="mhclg.dwelling_stock_density",
                        authority="mhclg",
                        evidence_url=LT126_PAGE,
                        notes=LT126_NOTES,
                        unit="dwellings_per_hectare",
                        aggregation="ratio",
                        header=header,
                        header_row=LT126_HEADER_ROW,
                    )
                ],
            )
        )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "mhclg-live-table-126-dwelling-density-2026",
        "label": "MHCLG Live Table 126: dwelling stock density by local authority "
        "district, England, 2011 to 2025",
        "dimension_labels": {"mhclg.lt126_area": "Area"},
        "artifact": artifact(
            "mhclg",
            "Live Table 126: dwelling stock density estimates by local authority "
            "district, England, 2011 to 2025",
            LT126_DIRECTORY,
            "lt126_2026_05",
            "ods_used_range",
            "ods whole-workbook used-range cell parse",
            2026,
        ),
        "record_sets": record_sets,
    }
    return render(LT126_HEADER, payload)


CT_PAGE = (
    "https://www.gov.uk/government/statistics/"
    "collection-rates-for-council-tax-and-non-domestic-rates-in-england-2025-to-2026"
)
CT_RELEASE = (
    "MHCLG, Collection rates for Council Tax and non-domestic rates in England, 2025 to "
    "2026 (published 24 June 2026, revised 31 July 2026)"
)
CT_ENGLAND = {
    "geography_id": "E92000001",
    "geography_level": "country",
    "geography_name": "England",
    "geography_vintage": "current",
}
# Class codes of the class total rows, which precede the 296 billing authorities.
CT_CLASS_CODES = ("LB", "ILB", "OLB", "MD", "UA", "SD")
# Table 9a prints Barnsley and Sheffield under the codes ONS gave them in 2025 (Table 6a
# under E08000016 and E08000019), as mhclg-council-taxbase-england-2025 does.
CT_2025_CODES = {"E08000038": "lad_2025", "E08000039": "lad_2025"}
BLOCK_MARKER = "# Record sets below: scripts/build_uk_408_packages.py (PolicyEngine/chronicle#408).\n"


def fiscal_coverage(opening: int, label: str) -> dict:
    return {
        "start_date": f"{opening}-04-01",
        "end_date": f"{opening + 1}-03-31",
        "basis": "fiscal",
        "source_period_label": label,
    }


def year_label(opening: int) -> str:
    return f"{opening}-{(opening + 1) % 100:02d}"


def ct_rows(
    grid: dict, sheet: str, first: int, *, england: bool
) -> tuple[list[dict], list[dict]]:
    """England (if wanted) and the class rows, then the billing authority rows."""
    rows = sorted(
        row
        for (name, row, column), value in grid.items()
        if name == sheet and column == "A" and row >= first and value
    )
    totals, authorities = [], []
    for row in rows:
        label, ecode = grid[(sheet, row, "A")], grid[(sheet, row, "B")]
        code, kind = grid[(sheet, row, "C")], grid[(sheet, row, "D")]
        if ecode == "E-ENG":
            assert (label, code, kind) == ("England", "[z]", "Eng"), row
            if not england:
                continue
            totals.append(
                area_row(
                    "england",
                    "England",
                    row,
                    "A",
                    label,
                    CT_ENGLAND,
                    ordinal=len(totals),
                    guards=[guard("B", row, ecode, "E-Code")],
                )
            )
        elif code == "[z]":
            name = label.removeprefix("of which: ")
            assert kind in CT_CLASS_CODES, (row, kind)
            totals.append(
                area_row(
                    slug(name),
                    name,
                    row,
                    "A",
                    label,
                    CT_ENGLAND,
                    ordinal=len(totals),
                    guards=[guard("D", row, kind, "Class")],
                    filters={"billing_authority_class": slug(name)},
                )
            )
        else:
            assert code[:3] in {"E06", "E07", "E08", "E09"}, (row, code)
            authorities.append(
                area_row(
                    slug(f"{code} {label}"),
                    label,
                    row,
                    "C",
                    code,
                    {
                        "geography_id": code,
                        "geography_level": "local_authority",
                        "geography_name": label,
                        "geography_vintage": CT_2025_CODES.get(code, "lad_2023"),
                    },
                    ordinal=len(authorities),
                )
            )
    assert [row["value_id"] for row in totals] == ["england"] * england + [
        "london_boroughs",
        "inner_london_boroughs",
        "outer_london_boroughs",
        "metropolitan_districts",
        "unitary_authorities",
        "shire_districts",
    ], [row["value_id"] for row in totals]
    assert len(authorities) == 296, len(authorities)
    return totals, authorities


def ct_record_set(record_set_id: str, sheet: str, rows, measures, **period) -> dict:
    return record_set(
        record_set_id,
        provenance_class="administrative",
        sheet_name=sheet,
        geography=CT_ENGLAND,
        entity="government",
        entity_role="billing_authority",
        domain="council_tax",
        groupby_dimension="mhclg.billing_authority",
        rows=rows,
        measures=measures,
        **period,
    )


# ------------------------------------------- 4a. MHCLG Table 6a, collection by authority

CT6_DIRECTORY = "mhclg/council_tax_collection_by_authority_2025_26"
CT6_SHEET = "Table_6a_-_council_tax"
# (opening year, column, measure, QRC4 line and its description on worksheet 'Table_6')
CT6_COLUMNS = (
    (
        2024,
        "F",
        "net_collectable_debit",
        "Estimate of amount of council tax collectable in the year 2024-25 (£ thousand)",
        "QRC4 line 1, 'Estimated net collectable debit in respect of 2024-25' ([note a] "
        "'Also known as the Net Collectable Debit')",
    ),
    (
        2024,
        "G",
        "amount_collected_in_year",
        "Amount of council tax collected by 31 March 2025 relating to 2024-25 "
        "(£ thousand)",
        "QRC4 line 4, 'Total 2024-25 receipts, net of refunds granted in respect of "
        "2024-25 only'",
    ),
    (
        2025,
        "I",
        "net_collectable_debit",
        "Estimate of amount of council tax collectable in the year 2025-26 (£ thousand)",
        "QRC4 line 1, 'Estimated net collectable debit in respect of 2025-26' ([note a] "
        "'Also known as the Net Collectable Debit')",
    ),
    (
        2025,
        "J",
        "amount_collected_in_year",
        "Amount council tax collected by 31 March 2026 relating to 2025-26 (£ thousand)",
        "QRC4 line 4, 'Total 2025-26 receipts, net of refunds granted in respect of "
        "2025-26 only'",
    ),
)
# The in-year collection rate columns, which the publisher defines as arithmetic over
# the ported columns (worksheet 'Table_6', line 5).
CT6_RATE_HEADERS = {
    "H": "Amount council tax collected by 31 March 2025 as a percentage of amount "
    "collectable 2024-25 (%)",
    "K": "Amount of council tax collected by 31 March 2026 as a percentage of amount "
    "collectable 2025-26 (%)",
}
CT6_RATE_DEFINITION = "In-year collection rate for 2024-25 (%) = (Line 4/Line 1 x 100, to 2 decimal places)"
CT6_HEADER = """
MHCLG, Collection rates for Council Tax and non-domestic rates in England, 2025 to 2026,
'Table 6: Council tax and non-domestic rates - collection amounts and rates, 2024-25 and
2025-26' (published 24 June 2026, revised 31 July 2026 to include Kensington & Chelsea),
worksheet 'Table_6a_-_council_tax', for {ISSUE} item 4. Written by
scripts/build_uk_408_packages.py.

For the six authority classes (London Boroughs and, of which, Inner and Outer London
Boroughs; Metropolitan Districts; Unitary Authorities; Shire Districts), as England with
the class as a filter, and for each of the 296 billing authorities, in GBP thousands
(value_scale 1000): the estimated council tax collectable in the year, QRC4 line 1, the
net collectable debit (note a: 'Also known as the Net Collectable Debit'); and the amount
collected by 31 March relating to that year, QRC4 line 4 (receipts net of refunds). Both
for 2024-25 and 2025-26, each a fiscal_year period stamped by its opening year. The
concepts are those mhclg-council-tax-collection-england-2025-26 uses for the same lines of
the release's Table 5.

Not ported: the England row, which restates Table 5's England figures for both years in
GBP thousands (asserted equal in the tests, not ported again); the two in-year collection
rate columns, which the publisher defines as arithmetic over the ported columns
('In-year collection rate ... = (Line 4/Line 1 x 100, to 2 decimal places)', worksheet
'Table_6'); and the non-domestic rates sheet 6b.
Authorities carry the ONS codes printed: Barnsley E08000016 and Sheffield E08000019,
which ONS replaced with E08000038 and E08000039 in 2025 (the release's Table 9a prints
the new codes). The notes column flags four rows '[r]': revised to include Kensington &
Chelsea.
""".replace("{ISSUE}", ISSUE)


def build_collection_by_authority() -> str:
    grid = ods_grid(CT6_DIRECTORY)
    sheet = CT6_SHEET
    assert grid[(sheet, 1, "A")] == (
        "Table 6a: Council tax - collection amounts and rates, England, 2024-25 and "
        "2025-26"
    )
    assert (grid[(sheet, 3, "A")], grid[(sheet, 3, "C")]) == ("Authority", "ONS Code")
    for column, header in CT6_RATE_HEADERS.items():
        assert grid[(sheet, 3, column)] == header, column
    assert grid[("Table_6", 16, "B")] == CT6_RATE_DEFINITION
    classes, authorities = ct_rows(grid, sheet, 4, england=False)
    record_sets = []
    for opening in (2024, 2025):
        label = year_label(opening)
        measures = []
        for year, column, measure_id, header, line in CT6_COLUMNS:
            if year != opening:
                continue
            assert grid[(sheet, 3, column)] == header, column
            what = (
                "net collectable debit"
                if measure_id == "net_collectable_debit"
                else "amount collected by 31 March relating to the year"
            )
            measures.append(
                measure(
                    measure_id,
                    f"Council tax {what}, {label} (GBP thousands)",
                    column,
                    concept=f"mhclg.council_tax.{measure_id}",
                    source_concept=f"mhclg.council_tax.{measure_id}",
                    authority="mhclg",
                    evidence_url=CT_PAGE,
                    notes=(
                        f"{CT_RELEASE}, Table 6, worksheet '{sheet}', column {column} "
                        f"'{header}': {line}. GBP thousands (value_scale 1000)."
                    ),
                    unit="gbp",
                    aggregation="sum",
                    ordinal=len(measures),
                    value_scale=1000,
                    header=header,
                    header_row=3,
                )
            )
        period = {
            "period_type": "fiscal_year",
            "period": opening,
            "period_coverage": fiscal_coverage(opening, label),
        }
        prefix = "mhclg.ct_collection_by_authority_2025_26.table_6a"
        record_sets.append(
            ct_record_set(
                f"{prefix}.classes.fy{opening}",
                sheet,
                classes,
                measures,
                **period,
            )
        )
        record_sets.append(
            ct_record_set(
                f"{prefix}.billing_authorities.fy{opening}",
                sheet,
                authorities,
                measures,
                **period,
            )
        )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "mhclg-council-tax-collection-by-authority-2025-26",
        "label": "MHCLG collection rates 2025-26, Table 6a: council tax net collectable "
        "debit and amount collected by billing authority, England, 2024-25 and 2025-26",
        "dimension_labels": {
            "mhclg.billing_authority": "Billing authority",
            "billing_authority_class": FILTER_LABELS["billing_authority_class"],
        },
        "artifact": artifact(
            "mhclg",
            "Collection rates for Council Tax and non-domestic rates in England, 2025 to "
            "2026, Table 6: Council tax and non-domestic rates - collection amounts and "
            "rates, 2024-25 and 2025-26",
            CT6_DIRECTORY,
            "collection_rates_2025_26",
            "ods_used_range",
            "ods used-range cell parse of the Table 6 workbook",
            2026,
        ),
        "record_sets": record_sets,
    }
    return render(CT6_HEADER, payload)


# ------------------------------------------------- 4b. MHCLG Table 9a, QRC4 by authority

CT9_DIRECTORY = "mhclg/council_tax_qrc4_2025_26"
CT9_SHEET = "Table_9a_-_Council_Tax"
CT9_FORM = "QRC4_Form"
# Ported QRC4 lines: (line, column, measure and concept, label). Lines 9 to 12 are the
# receipts of each quarter of 2025-26 and are stamped by their quarter.
CT9_LINES = (
    (
        "2",
        "G",
        "prepayments_received_in_previous_years",
        "prepayments, cash receipts collected in previous years in respect of 2025-26",
    ),
    (
        "3",
        "H",
        "in_year_receipts_net_of_refunds",
        "estimated 2025-26 receipts collected "
        "in 2025-26, net of refunds granted in respect of 2025-26",
    ),
    (
        "6",
        "K",
        "receipts_of_previous_years_taxes",
        "estimated receipts in 2025-26 of "
        "previous years' council taxes, net of refunds made in respect of those years",
    ),
    (
        "7",
        "L",
        "receipts_of_following_year_taxes",
        "estimated receipts of 2026-27 "
        "council taxes received before 1 April 2026, and other credits carried forward on "
        "31 March 2026",
    ),
    (
        "13",
        "R",
        "arrears_brought_forward",
        "arrears for 2024-25 and earlier years brought forward on 1 April 2025",
    ),
    (
        "14",
        "S",
        "net_adjustments_to_arrears",
        "net adjustments made in 2025-26 to the "
        "arrears for 2024-25 and earlier years included in line 13",
    ),
    (
        "16",
        "U",
        "arrears_collected_relating_to_earlier_years",
        "arrears relating to 2023-24 or earlier years collected in 2025-26",
    ),
    (
        "17",
        "V",
        "arrears_collected_relating_to_previous_year",
        "arrears relating to 2024-25 only collected in 2025-26",
    ),
    (
        "18",
        "W",
        "arrears_written_off_relating_to_earlier_years",
        "amounts relating to 2023-24 and earlier years written off in 2025-26",
    ),
    (
        "19",
        "X",
        "arrears_written_off_relating_to_previous_year",
        "amounts relating to 2024-25 only written off in 2025-26",
    ),
    (
        "20a",
        "Z",
        "arrears_outstanding_relating_to_earlier_years",
        "arrears relating to "
        "2023-24 and earlier years outstanding at 31 March 2026 (included in line 20)",
    ),
    (
        "20b",
        "AA",
        "arrears_outstanding_relating_to_previous_year",
        "arrears relating to "
        "2024-25 outstanding at 31 March 2026 (included in line 20)",
    ),
    (
        "21",
        "AB",
        "amount_uncollected_in_year",
        "amounts uncollected in 2025-26 (the net "
        "collectable debit less receipts relating to 2025-26, plus costs)",
    ),
    (
        "22",
        "AC",
        "in_year_written_off",
        "write-offs made in 2025-26 that related to 2025-26 only",
    ),
    (
        "25",
        "AF",
        "court_and_administration_costs_in_arrears",
        "court and administration "
        "costs included in the total arrears outstanding at 31 March 2026 (line 24)",
    ),
)
CT9_QUARTERS = (
    ("9", "N", "2025-Q2", "2025-04-01", "2025-06-30", "April 2025 - June 2025"),
    ("10", "O", "2025-Q3", "2025-07-01", "2025-09-30", "July 2025 - September 2025"),
    ("11", "P", "2025-Q4", "2025-10-01", "2025-12-31", "October 2025 - December 2025"),
    ("12", "Q", "2026-Q1", "2026-01-01", "2026-03-31", "January 2026 - March 2026"),
)
# Line 1, the estimated net collectable debit, restates Table 6a's 2025-26 column for
# every row and is not ported again.
CT9_RESTATED = {"1": "F"}
# QRC4 lines the form defines as arithmetic over other lines of the return, whose
# operands are ported; line 21's formula adds costs the return does not print.
CT9_ARITHMETIC = {
    "4": ("I", "= (Line 2 + Line 3)"),
    "5": ("J", "= (Line 4/Line 1 x 100, to 2 decimal places)"),
    "8": ("M", "= (Line 3 + Line 6 + Line 7)"),
    "15": ("T", "= (Line 13 + Line 14)"),
    "20": ("Y", "= (Line 15 - Line 16 - Line 17 - Line 18 - Line 19)"),
    "23": ("AD", "= (Line 21 - Line 22)"),
    "24": ("AE", "= (Line 20 + Line 23)"),
}
CT9_NOTE_A = (
    "[note a] 'Line 16 is reported as 0 for some authorities, this indicates that the "
    "authority was unable to separate arrears between lines 16 and 17.'"
)
CT9_NOTE_B = (
    "[note b] 'These figures may be under-estimated as some local authorities have only "
    "reported court and administration cost added in the financial year and not "
    "accumulated costs.'"
)
CT9_GROSS = (
    "Section II of the form: 'Information in this section is gross arrears and includes "
    "administration and court costs.'"
)
CT9_HEADER = """
MHCLG, Collection rates for Council Tax and non-domestic rates in England, 2025 to 2026,
'Table 9: Quarterly return of Council Tax and non-domestic rates QRC4, 2025 to 2026'
(published 24 June 2026, revised 31 July 2026 to include Kensington & Chelsea and to
correct arrears for Bradford and Stoke-on-Trent), worksheet 'Table_9a_-_Council_Tax',
for {ISSUE} item 4. Written by scripts/build_uk_408_packages.py.

Each billing authority's QRC4 return for 2025-26, and the England and class totals, in
GBP thousands (value_scale 1000), under the publisher's line numbers and labels. Lines 2,
3, 6, 7, 13, 14, 16 to 19, 20a, 20b, 21, 22 and 25 are fiscal_year 2025 (the return's
year; stocks such as the arrears brought forward on 1 April 2025 and outstanding on 31
March 2026 are stamped by it too, as the Welsh collection packages do). Lines 9 to 12,
the receipts collected in each quarter whatever year they relate to, are quarter
periods.

Not ported: line 1, the estimated net collectable debit, which restates the 2025-26
column of Table 6a (mhclg-council-tax-collection-by-authority-2025-26) for every row
(asserted equal in the tests, not ported again); and the lines the QRC4 form (worksheet
'QRC4_Form') defines as arithmetic over other lines of the return: 4 = (2 + 3), 5 = (4/1
x 100), 8 = (3 + 6 + 7), 15 = (13 + 14), 20 = (15 - 16 - 17 - 18 - 19), 23 = (21 - 22)
and 24 = (20 + 23). Their operands are ported here, or for line 1 in Table 6a, whose
2025-26 amount collected is also line 4. Line 21 is ported: its formula, (Line 1 - Line 4
+ Costs), adds costs the return does not print. The non-domestic rates sheet 9b is not
ported. Barnsley and Sheffield are printed under E08000038 and E08000039,
the codes ONS gave them in 2025 (geography_vintage lad_2025); Table 6a prints E08000016
and E08000019. The form's line 7 text reads 'receipts of 2025-26 council taxes';
the table's column heading, ported here, reads 2026-27.
""".replace("{ISSUE}", ISSUE)


def ct9_form_lines(grid: dict) -> dict[str, str]:
    """The QRC4 form's line descriptions, keyed by line number as printed."""
    lines = {}
    for (name, row, column), value in grid.items():
        if name == CT9_FORM and column == "A" and 17 <= row <= 50 and value is not None:
            lines[str(value)] = grid.get((CT9_FORM, row, "B"))
    return lines


def build_qrc4() -> str:
    grid = ods_grid(CT9_DIRECTORY)
    sheet = CT9_SHEET
    assert grid[(sheet, 1, "A")] == (
        "Table 9a: Council tax - total receipts and arrears information, England, 2025-26"
    )
    assert (grid[(sheet, 4, "A")], grid[(sheet, 4, "C")]) == ("Authority", "ONS Code")
    form = ct9_form_lines(grid)
    headers = {
        str(grid[(sheet, 4, column)]).split(". ", 1)[0]: (
            column,
            grid[(sheet, 4, column)],
        )
        for (name, row, column) in grid
        if name == sheet and row == 4 and column not in {"A", "B", "C", "D", "E", "AG"}
    }
    assert len(headers) == 27, sorted(headers)
    for line, (column, formula) in CT9_ARITHMETIC.items():
        assert headers[line][0] == column, line
        assert form[line].endswith(formula), (line, form[line])
    assert form["21"].endswith("= (Line 1 - Line 4 + Costs)"), form["21"]
    totals, authorities = ct_rows(grid, sheet, 5, england=True)
    ported = {line for line, *_ in CT9_LINES} | {line for line, *_ in CT9_QUARTERS}
    assert ported | set(CT9_ARITHMETIC) | set(CT9_RESTATED) == set(headers)
    for line, column in CT9_RESTATED.items():
        assert headers[line][0] == column, line

    def notes(line: str, column: str) -> str:
        extra = []
        if line in {"16", "17"}:
            extra.append(CT9_NOTE_A)
        if line == "25":
            extra.append(CT9_NOTE_B)
        if line[:2].isdigit() and int(line[:2]) >= 13:
            extra.append(CT9_GROSS)
        return " ".join(
            [
                f"{CT_RELEASE}, Table 9, worksheet '{sheet}', column {column} "
                f"'{headers[line][1]}'. QRC4 form line {line}: '{form[line]}'.",
                *extra,
                "GBP thousands (value_scale 1000).",
            ]
        )

    record_sets = []
    measures = []
    for line, column, measure_id, label in CT9_LINES:
        assert headers[line][0] == column, line
        measures.append(
            measure(
                measure_id,
                f"QRC4 line {line}: {label} (GBP thousands)",
                column,
                concept=f"mhclg.council_tax.{measure_id}",
                source_concept=f"mhclg.council_tax.{measure_id}",
                authority="mhclg",
                evidence_url=CT_PAGE,
                notes=notes(line, column),
                unit="gbp",
                aggregation="sum",
                ordinal=len(measures),
                value_scale=1000,
                header=headers[line][1],
                header_row=4,
            )
        )
    prefix = "mhclg.ct_qrc4_2025_26.table_9a"
    period = {
        "period_type": "fiscal_year",
        "period": 2025,
        "period_coverage": fiscal_coverage(2025, "2025-26"),
    }
    for kind, rows in (
        ("england_and_classes", totals),
        ("billing_authorities", authorities),
    ):
        record_sets.append(
            ct_record_set(f"{prefix}.{kind}.fy2025", sheet, rows, measures, **period)
        )
    for line, column, quarter, start, end, months in CT9_QUARTERS:
        assert headers[line] == (
            column,
            f"{line}. Receipts collected between {months} (£ thousand)",
        ), line
        quarter_measures = [
            measure(
                "receipts_collected_in_quarter",
                f"QRC4 line {line}: council tax receipts collected between {months}, "
                "irrespective of the year to which they relate (GBP thousands)",
                column,
                concept="mhclg.council_tax.receipts_collected_in_quarter",
                source_concept="mhclg.council_tax.receipts_collected_in_quarter",
                authority="mhclg",
                evidence_url=CT_PAGE,
                notes=(
                    f"{notes(line, column)[: -len('GBP thousands (value_scale 1000).')]}"
                    "The form's Part B gives receipts by quarter 'irrespective of the "
                    "financial year (previous, current or future years) to which the "
                    "receipts relate'. GBP thousands (value_scale 1000)."
                ),
                unit="gbp",
                aggregation="sum",
                value_scale=1000,
                header=headers[line][1],
                header_row=4,
            )
        ]
        quarter_period = {
            "period_type": "quarter",
            "period": quarter,
            "period_coverage": {
                "start_date": start,
                "end_date": end,
                "basis": "calendar",
                "source_period_label": f"{months} (QRC4 line {line})",
            },
        }
        suffix = "receipts_" + quarter.lower().replace("-", "_")
        for kind, rows in (
            ("england_and_classes", totals),
            ("billing_authorities", authorities),
        ):
            record_sets.append(
                ct_record_set(
                    f"{prefix}.{kind}.{suffix}",
                    sheet,
                    rows,
                    quarter_measures,
                    **quarter_period,
                )
            )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "mhclg-council-tax-qrc4-2025-26",
        "label": "MHCLG collection rates 2025-26, Table 9a: each billing authority's "
        "council tax QRC4 return for 2025-26, England",
        "dimension_labels": {
            "mhclg.billing_authority": "Billing authority",
            "billing_authority_class": FILTER_LABELS["billing_authority_class"],
        },
        "artifact": artifact(
            "mhclg",
            "Collection rates for Council Tax and non-domestic rates in England, 2025 to "
            "2026, Table 9: Quarterly return of Council Tax and non-domestic rates QRC4, "
            "2025 to 2026",
            CT9_DIRECTORY,
            "collection_rates_2025_26",
            "ods_used_range",
            "ods used-range cell parse of the Table 9 workbook",
            2026,
        ),
        "record_sets": record_sets,
    }
    return render(CT9_HEADER, payload)


# ------------------------------- 4c. Per-authority rows of the pinned Welsh and SLGFS tables


def register_codes(prefix: str) -> dict[str, str]:
    """Each area's code by its ONS name, from Chronicle's geography register."""
    register = json.loads(
        (ROOT / "chronicle/geography/uk_canonical_names.json").read_text()
    )
    return {
        name: code
        for code, name in register["names"].items()
        if code.startswith(prefix)
    }


def package_prefix(directory: str) -> tuple[Path, str, dict]:
    """The committed package text before this script's block, and its parse."""
    path = PACKAGES / directory / "source_package.yaml"
    prefix = path.read_text(encoding="utf-8").split(BLOCK_MARKER)[0]
    assert prefix.endswith("\n")
    return path, prefix, yaml.safe_load(prefix)


def appended(prefix: str, record_sets: list[dict]) -> str:
    block = yaml.dump(
        record_sets,
        Dumper=PackageDumper,
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    return prefix + BLOCK_MARKER + block


def adapted_measures(
    record_set: dict, pattern: str, rows_text: str, extra: str = ""
) -> list[dict]:
    """The pinned total row's measures, their notes pointed at the authority rows."""
    measures = []
    for spec in record_set["measures"]:
        spec = dict(spec)
        notes, count = re.subn(pattern, rows_text, spec["concept_evidence_notes"])
        assert count == 1, (spec["measure_id"], spec["concept_evidence_notes"])
        # The total row's own note 5 is restated below for the rows that carry it.
        notes = re.sub(r" Publisher note 5 on this row: [^.]*\.", "", notes)
        if extra:
            head, _, tail = notes.rpartition(" GBP thousands")
            notes = f"{head} {extra} GBP thousands{tail}"
        spec["concept_evidence_notes"] = notes
        measures.append(spec)
    return measures


WELSH_DIRECTORIES = {
    2024: "welshgov/council_tax_collection_2024_25",
    2025: "welshgov/council_tax_collection_2025_26",
}
WELSH_NOTE_5 = (
    "Rows marked '[Note 5]' ({rows}): publisher note 5, any differences compared to "
    "arrears carried forward are due to incorrectly stated arrears in the previous year."
)


def build_welsh(opening: int) -> str:
    directory = WELSH_DIRECTORIES[opening]
    path, prefix, package = package_prefix(directory)
    (wales,) = package["record_sets"]
    filename, artifact_path = manifest_file(directory)
    grid = grid_of(
        source_cells_from_xlsx(
            artifact_path.read_bytes(), metadata(filename), sheets=("Table2",)
        )
    )
    codes = register_codes("W06")
    total_row = wales["rows"][0]["row_number"]
    rows = []
    for row in range(5, total_row):
        printed = grid[("Table2", row, "A")]
        name = printed.removesuffix(" [Note 5]")
        rows.append(
            area_row(
                slug(f"{codes[name]} {name}"),
                name,
                row,
                "A",
                printed,
                {
                    "geography_id": codes[name],
                    "geography_level": "local_authority",
                    "geography_name": name,
                    "geography_vintage": "lad_2023",
                },
                ordinal=len(rows),
            )
        )
    assert len(rows) == 22 and {row["geography_id"] for row in rows} == set(
        codes.values()
    )
    noted = [row["label"] for row in rows if row["expected_row_header"].endswith("]")]
    measures = adapted_measures(
        wales,
        r"'Total Wales( \[Note 5\])?' row",
        "the 22 billing authority rows",
        WELSH_NOTE_5.format(rows=" and ".join(noted)) if noted else "",
    )
    record_set = {
        **{
            key: value
            for key, value in wales.items()
            if key not in {"rows", "measures"}
        },
        "record_set_id": wales["record_set_id"].replace(
            ".wales", ".billing_authorities"
        ),
        "record_set_spec_id": wales["record_set_spec_id"].replace(
            ".wales.", ".billing_authorities."
        ),
        "source_record_id_prefix": wales["source_record_id_prefix"].replace(
            ".wales", ".billing_authorities"
        ),
        "rows": rows,
        "measures": measures,
    }
    return appended(prefix, [record_set])


SLGFS_DIRECTORY = "scotgov/slgfs_council_tax_2024_25"
SLGFS_INCOME_NOTE = (
    "The sheet: 'figures that relate to income collected in 2024-25, which can include "
    "amounts that were billed in previous years' (LFR A0): income after CTR, not a net "
    "collectable debit. 2024-25 is the latest year until the next SLGFS."
)


def build_slgfs() -> str:
    path, prefix, package = package_prefix(SLGFS_DIRECTORY)
    filename, artifact_path = manifest_file(SLGFS_DIRECTORY)
    sheets = ("Table 2.8", "Table 2.11")
    grid = grid_of(
        source_cells_from_xlsx(
            artifact_path.read_bytes(), metadata(filename), sheets=sheets
        )
    )
    codes = {
        name.replace(" and ", " & "): code
        for name, code in register_codes("S12").items()
    }
    record_sets = []
    for scotland in package["record_sets"]:
        sheet = scotland["sheet_name"]
        if sheet not in sheets:
            continue
        assert scotland["record_set_id"].endswith(".scotland"), scotland[
            "record_set_id"
        ]
        assert scotland["rows"][0]["row_number"] == 39
        rows = []
        for row in range(7, 39):
            name = grid[(sheet, row, "A")]
            code = codes.get(name) or codes[name.replace(" and ", " & ")]
            rows.append(
                area_row(
                    slug(f"{code} {name}"),
                    name,
                    row,
                    "A",
                    name,
                    {
                        "geography_id": code,
                        "geography_level": "local_authority",
                        "geography_name": name,
                        "geography_vintage": "ca_2019",
                    },
                    ordinal=len(rows),
                )
            )
        assert len({row["geography_id"] for row in rows}) == 32
        measures = adapted_measures(
            scotland,
            r"Scotland row",
            "the 32 local authority rows",
            SLGFS_INCOME_NOTE if sheet == "Table 2.8" else "",
        )
        record_sets.append(
            {
                **{
                    key: value
                    for key, value in scotland.items()
                    if key not in {"rows", "measures"}
                },
                "record_set_id": scotland["record_set_id"].replace(
                    ".scotland", ".councils"
                ),
                "record_set_spec_id": scotland["record_set_spec_id"].replace(
                    ".scotland.", ".councils."
                ),
                "source_record_id_prefix": scotland["source_record_id_prefix"].replace(
                    ".scotland", ".councils"
                ),
                "rows": rows,
                "measures": measures,
            }
        )
    assert len(record_sets) == 3, [spec["record_set_id"] for spec in record_sets]
    return appended(prefix, record_sets)


BUILDERS = {
    LVE_DIRECTORY: build_land_values,
    VOA_DIRECTORY: build_bands,
    VOA_PROPERTY_TYPES_DIRECTORY: build_property_types,
    VOA_BUILD_PERIODS_DIRECTORY: build_build_periods,
    D3_DIRECTORY: build_epc_d3,
    LT126_DIRECTORY: build_live_table_126,
    CT6_DIRECTORY: build_collection_by_authority,
    CT9_DIRECTORY: build_qrc4,
    WELSH_DIRECTORIES[2024]: lambda: build_welsh(2024),
    WELSH_DIRECTORIES[2025]: lambda: build_welsh(2025),
    SLGFS_DIRECTORY: build_slgfs,
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
