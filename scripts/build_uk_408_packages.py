"""Generate the source packages for PolicyEngine/chronicle#408, the UK land value inputs.

Run from the repository root:

    uv run python scripts/build_uk_408_packages.py

``--check`` compares the generated YAML with the committed files instead of writing.
Each package is written from its pinned artifact, read with Chronicle's own parsers, so
every row number, column and guard cell below is one the package parser sees.

- ``mhclg-land-value-estimates-2023``: MHCLG's land value estimates for policy appraisal
  2023, all eight sheets (item 1).
"""

from __future__ import annotations

import argparse
import re
import textwrap
from pathlib import Path

import yaml
from openpyxl.utils import get_column_letter

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


BUILDERS = {
    LVE_DIRECTORY: build_land_values,
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
