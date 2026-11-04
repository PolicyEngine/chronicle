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
"""

from __future__ import annotations

import argparse
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


BUILDERS = {
    LVE_DIRECTORY: build_land_values,
    VOA_DIRECTORY: build_bands,
    VOA_PROPERTY_TYPES_DIRECTORY: build_property_types,
    VOA_BUILD_PERIODS_DIRECTORY: build_build_periods,
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
