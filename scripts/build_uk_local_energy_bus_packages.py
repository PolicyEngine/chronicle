"""Author the chronicle#356 fact packages from their pinned publisher artifacts.

Writes, from the bytes the manifests pin under ``db/data`` (nothing downloaded and
no fact built):

- ``desnz-subnational-electricity-consumption-northern-ireland-2024`` and
  ``desnz-subnational-gas-consumption-northern-ireland-2024``: DESNZ's Northern
  Ireland sub-national consumption, every year and measure in the workbooks.
- ``desnz-lsoa-domestic-gas-consumption-2024`` and
  ``desnz-lsoa-domestic-electricity-consumption-2024``: domestic meter counts and
  total consumption by LSOA (England and Wales) and data zone (Scotland), 2023 and
  2024. The MSOA and intermediate-zone workbooks are registered raw-only.
- ``dft-bus04i-operating-revenue-2025``: BUS04ai total estimated operating revenue
  for Scotland, Wales and Great Britain, years ending March 2024 and 2025.

Selectors are located by matching publisher text in the parsed source cells, and
every match is asserted, so a re-run against different bytes fails rather than
drifting.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from chronicle.source_package import read_registered_artifact
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


class AnchoredDumper(yaml.SafeDumper):
    """Emit YAML anchors for row mappings two record sets share (LSOA years)."""

    def ignore_aliases(self, data: object) -> bool:
        return not isinstance(data, FlowRow)


class FlowRow(dict):
    """A row mapping written in flow style, one line per row."""


def _represent_flow_row(dumper: yaml.SafeDumper, data: FlowRow) -> yaml.Node:
    return dumper.represent_mapping(
        "tag:yaml.org,2002:map", data.items(), flow_style=True
    )


AnchoredDumper.add_representer(FlowRow, _represent_flow_row)


def write_package(
    directory: Path, payload: dict, comment: str, dumper=PackageDumper
) -> None:
    """Write one package with its explanatory header."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "source_package.yaml").write_text(
        comment
        + yaml.dump(
            payload, Dumper=dumper, sort_keys=False, allow_unicode=True, width=100
        ),
        encoding="utf-8",
    )


def constraint(variable: str, value: object, label: str) -> dict:
    return {"variable": variable, "operator": "==", "value": value, "label": label}


def artifact_meta(name: str) -> SourceArtifactMetadata:
    return SourceArtifactMetadata(
        source_name="x",
        source_table="x",
        source_file=name,
        url=None,
        vintage="x",
        sha256="0",
        size_bytes=0,
        extracted_at="x",
        extraction_method="x",
    )


def grids(cells: list) -> dict[str, dict[tuple[int, str], object]]:
    """Map sheet -> (row, column letter) -> raw value, skipping blank cells."""
    out: dict[str, dict[tuple[int, str], object]] = {}
    for cell in cells:
        if cell.raw_value in (None, ""):
            continue
        column = re.match(r"[A-Z]+", cell.address).group(0)
        out.setdefault(cell.sheet_name, {})[(cell.row_number, column)] = cell.raw_value
    return out


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def iso(day: str) -> str:
    """'15th May 2024' -> '2024-05-15'."""
    match = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th) (\w+) (\d{4})", day.strip())
    assert match, day
    months = {
        m: i
        for i, m in enumerate(
            [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ],
            start=1,
        )
    }
    return f"{match.group(3)}-{months[match.group(2)]:02d}-{int(match.group(1)):02d}"


DESNZ_SHARED_LABELS = {
    "desnz.subnational.area": "Published geography",
    "fuel": "Fuel",
    "domestic_scope": "Domestic scope",
    "temperature_adjustment": "Temperature adjustment",
    "metric": "Metric",
}
DOMESTIC_SCOPES = {
    "domestic_standard": "Domestic standard meters",
    "domestic_economy_7": "Domestic Economy 7 meters",
    "all_domestic": "All domestic meters",
    "all_non_domestic": "All non-domestic meters",
    "all_meters": "All meters",
}
METRICS = {
    "meter_count": "Meter count",
    "consumption": "Consumption",
    "mean_consumption_per_meter": "Mean consumption per meter",
    "median_consumption_per_meter": "Median consumption per meter",
}


# --------------------------------------------------------------- Northern Ireland

NI_ELECTRICITY = "Northern_Ireland_subnational_electricity_consumption_2009-2024.xlsx"
NI_GAS = "Northern_Ireland_subnational_gas_consumption_2015-2024.xlsx"
NI_ELECTRICITY_DIR = "desnz/subnational_electricity_consumption_northern_ireland_2024"
NI_GAS_DIR = "desnz/subnational_gas_consumption_northern_ireland_2024"
NI_ELECTRICITY_URL = (
    "https://www.gov.uk/government/statistics/sub-national-electricity-consumption-"
    "statistics-in-northern-ireland"
)
NI_GAS_URL = (
    "https://www.gov.uk/government/statistics/sub-national-gas-consumption-statistics-"
    "in-northern-ireland"
)
METHODOLOGY_URL = (
    "https://assets.publishing.service.gov.uk/media/6a68b45b83f71b8684d02105/"
    "Subnational-methodology-and-guidance-booklet.pdf"
)
# DESNZ methodology and guidance booklet (July 2026), section 4.1 (page 32): the
# dated Northern Ireland gas years.
NI_GAS_YEARS = {
    2015: ("1st October 2014", "30th September 2015"),
    2016: ("15th July 2016", "15th July 2017"),
    2017: ("15th June 2017", "15th June 2018"),
    2018: ("15th May 2018", "15th May 2019"),
    2019: ("15th May 2019", "15th May 2020"),
    2020: ("15th May 2020", "15th May 2021"),
    2021: ("15th May 2021", "15th May 2022"),
    2022: ("15th May 2022", "15th May 2023"),
    2023: ("15th May 2023", "15th May 2024"),
    2024: ("15th May 2024", "15th May 2025"),
}
NI_UNALLOCATED = {
    "geography_id": "desnz:northern_ireland_unallocated",
    "geography_level": "statistical_scope",
    "geography_name": "Unallocated (Northern Ireland)",
    "geography_vintage": "current",
}


def header_parts(text: str) -> tuple[str, str]:
    """Split a DESNZ two-part header into (metric, domestic scope)."""
    lines = [part.strip() for part in str(text).split("\n") if part.strip()]
    head, scope = lines[0], lines[-1]
    metric = {
        "Number of meters": "meter_count",
        "Total consumption": "consumption",
        "Mean consumption": "mean_consumption_per_meter",
        "Median consumption": "median_consumption_per_meter",
    }[head]
    scope_id = {
        "Domestic Standard": "domestic_standard",
        "Domestic E7": "domestic_economy_7",
        "All Domestic": "all_domestic",
        "Domestic": "all_domestic",
        "All Non-Domestic": "all_non_domestic",
        "Non-Domestic": "all_non_domestic",
        "All meters": "all_meters",
    }[scope]
    return metric, scope_id


def ni_rows(grid, header_row: int, sheet: str, title: str) -> list[dict]:
    """Rows from the first data row to the last code in column A."""
    rows = []
    row = header_row + 1
    while (row, "A") in grid:
        code, name = grid[(row, "A")], grid[(row, "B")]
        if code in ("N92000002", "UKN"):
            geography = {
                "geography_id": "N92000002",
                "geography_level": "country",
                "geography_name": "Northern Ireland",
                "geography_vintage": "current",
            }
            assert name == "Northern Ireland", (sheet, row, name)
        elif code == "Unallocated":
            geography = dict(NI_UNALLOCATED)
        elif re.fullmatch(r"N09\d{6}", code):
            geography = {
                "geography_id": code,
                "geography_level": "local_authority",
                "geography_name": name,
                "geography_vintage": "lgd_2014",
            }
        else:
            assert re.fullmatch(r"UKN\d{4}", code), (sheet, row, code)
            geography = {
                "geography_id": code,
                "geography_level": "local_authority",
                "geography_name": name,
                "geography_vintage": "lgd_1973_nuts_lau",
            }
        rows.append(
            {
                "value_id": code.lower(),
                "label": name,
                "ordinal": len(rows),
                "row_number": row,
                "expected_row_header_column": "A",
                "expected_row_header": code,
                **geography,
                "table_record_kind": "total",
            }
        )
        row += 1
    rows[0]["guard_cells"] = [
        {"column": "A", "row": 1, "expected_value": title, "label": "sheet title"}
    ]
    return rows


def ni_measure(fuel, metric, scope, column, header, header_row, sheet, url, note):
    units = {
        "meter_count": ("count", 1000, "sum", "thousands converted to count"),
        "consumption": ("kwh", 1000000, "sum", "GWh converted to kWh"),
        "mean_consumption_per_meter": ("kwh", None, "mean", "kWh per meter"),
        "median_consumption_per_meter": ("kwh", None, "median", "kWh per meter"),
    }
    unit, scale, aggregation, unit_note = units[metric]
    base = {
        "meter_count": "meter_count",
        "consumption": "consumption",
        "mean_consumption_per_meter": "mean_consumption_per_meter",
        "median_consumption_per_meter": "median_consumption_per_meter",
    }[metric]
    prefix = (
        "domestic_"
        if scope.startswith("domestic") or scope == "all_domestic"
        else ("non_domestic_" if scope == "all_non_domestic" else "")
    )
    concept = f"desnz.subnational.{prefix}{fuel}_{base}"
    # The all-domestic meter count and consumption keep the GB package's measure ids.
    measure_id = (
        f"domestic_{metric}"
        if scope == "all_domestic" and metric in ("meter_count", "consumption")
        else f"{scope}_{metric}"
    )
    measure = {
        "measure_id": measure_id,
        "label": f"{DOMESTIC_SCOPES[scope]}: {METRICS[metric].lower()}",
        "ordinal": 0,
        "column": column,
        "source_column_id": measure_id,
        "expected_column_header_row": header_row,
        "expected_column_header": header,
        "concept": concept,
        "source_concept": concept,
        "concept_relation": "source_label",
        "concept_authority": "desnz",
        "concept_evidence_url": url,
        "concept_evidence_notes": f"DESNZ {sheet} sheet, column {column}: {unit_note}. {note}",
        "unit": unit,
        "aggregation": aggregation,
        "expected_cell_type": "number",
        "filters": {"domestic_scope": scope, "metric": metric},
        "constraints": [
            constraint("domestic_scope", scope, "Domestic scope"),
            constraint("metric", metric, "Metric"),
        ],
    }
    if scale:
        measure["value_scale"] = scale
    return measure


ENTITY_BY_SCOPE = {
    "domestic": (
        "household",
        "domestic_energy_customer",
        "domestic_energy_consumption",
    ),
    "non_domestic": (
        "institutional_sector",
        "non_domestic_energy_customers",
        "energy_consumption",
    ),
    "all_meters": (
        "institutional_sector",
        "all_energy_customers",
        "energy_consumption",
    ),
}


# The methodology booklet (July 2026) on comparing Northern Ireland with Great Britain.
NI_COMPARABILITY = {
    "electricity": (
        "Domestic or non-domestic by NIE Networks tariff (cover sheet). DESNZ: not directly "
        "comparable with Great Britain's electricity statistics, because of differences in "
        "market structure and collection methodology (methodology booklet, July 2026, section "
        "5.3); Northern Ireland's years are financial years from 2012 where Great Britain's "
        "run February to January, and 2015 onwards is not directly comparable with earlier "
        "years (section 5.2)."
    ),
    "gas": (
        "Domestic or non-domestic by meter profile marker; weather corrected (cover sheet). "
        "DESNZ: not directly comparable with Great Britain's gas statistics, which class "
        "every meter under a 73,200 kWh annual quantity as domestic (methodology booklet, "
        "July 2026, sections 4.2 and 4.3)."
    ),
}
NI_DOMESTIC_SCOPES_NOTE = (
    "Northern Ireland files domestic standard, domestic Economy 7 and all-domestic rows "
    "under this concept, told apart by domestic_scope; Great Britain's rows are "
    "all_domestic only, so a selector that does not pin domestic_scope pools the three."
)


def scope_group(scope: str) -> str:
    if scope in ("domestic_standard", "domestic_economy_7", "all_domestic"):
        return "domestic"
    return "non_domestic" if scope == "all_non_domestic" else "all_meters"


def build_ni(fuel: str) -> None:
    filename, directory, url = (
        (NI_ELECTRICITY, NI_ELECTRICITY_DIR, NI_ELECTRICITY_URL)
        if fuel == "electricity"
        else (NI_GAS, NI_GAS_DIR, NI_GAS_URL)
    )
    path = ROOT / "db/data" / directory / filename
    sheet_grids = grids(
        source_cells_from_xlsx(path.read_bytes(), artifact_meta(filename))
    )
    cover = sheet_grids["Cover sheet"]
    cover_text = " ".join(str(v) for v in cover.values())
    years = sorted(int(s) for s in sheet_grids if s.isdigit())
    record_sets = []
    for year in years:
        sheet = str(year)
        grid = sheet_grids[sheet]
        title = grid[(1, "A")]
        noun = "electricity" if fuel == "electricity" else "gas"
        assert title == f"Subnational {noun} consumption, Northern Ireland, {year}", (
            title
        )
        header_row = 5 if fuel == "electricity" else 4
        assert (
            grid[(header_row, "A")] == "Code"
            and grid[(header_row, "B")] == "Local authority"
        )
        rows = ni_rows(grid, header_row, sheet, title)
        columns = sorted(
            (
                column
                for (row, column) in grid
                if row == header_row and column not in ("A", "B")
            ),
            key=lambda c: (len(c), c),
        )
        by_group: dict[str, list[dict]] = {}
        for column in columns:
            header = grid[(header_row, column)]
            metric, scope = header_parts(header)
            note = NI_COMPARABILITY[fuel]
            if fuel == "electricity" and scope_group(scope) == "domestic":
                note += " " + NI_DOMESTIC_SCOPES_NOTE
            by_group.setdefault(scope_group(scope), []).append(
                ni_measure(
                    fuel, metric, scope, column, header, header_row, sheet, url, note
                )
            )
        if fuel == "electricity":
            if year <= 2011:
                period = {
                    "period_type": "calendar_year",
                    "period": year,
                    "period_coverage": {
                        "start_date": f"{year}-01-01",
                        "end_date": f"{year}-12-31",
                        "basis": "calendar",
                        "source_period_label": sheet,
                        "notes": "Cover sheet: 2009 to 2011 are calendar years.",
                    },
                }
            else:
                period = {
                    "period_type": "fiscal_year",
                    "period": year,
                    "period_coverage": {
                        "start_date": f"{year}-04-01",
                        "end_date": f"{year + 1}-03-31",
                        "basis": "fiscal",
                        "source_period_label": sheet,
                        "notes": (
                            "Cover sheet: years from 2012 are financial years, 1 April to 31 "
                            f"March, so {year} is 1 April {year} to 31 March {year + 1}; "
                            "period.value stores the opening year, the publisher's label."
                        ),
                    },
                }
            assert "financial years" in cover_text and "calendar years" in cover_text
        else:
            start, end = NI_GAS_YEARS[year]
            period = {
                "period_type": "gas_year",
                "period": year,
                "period_coverage": {
                    "start_date": iso(start),
                    "end_date": iso(end),
                    "basis": "survey_reference",
                    "source_period_label": f"{year} ({start} to {end})",
                    "notes": (
                        "DESNZ methodology and guidance booklet (July 2026), section 4.1: the "
                        "Northern Ireland gas year under the publisher's year label; weather "
                        "corrected (cover sheet). The dates are DESNZ's as it states them: "
                        "from 2018 consecutive years share their 15 May boundary day, 2016 "
                        "and 2017 overlap by a month, and 2015 ends before 2016 begins."
                    ),
                },
            }
        temperature = "as_reported" if fuel == "electricity" else "weather_corrected"
        for group, measures in by_group.items():
            entity, role, domain = ENTITY_BY_SCOPE[group]
            for ordinal, measure in enumerate(measures):
                measure["ordinal"] = ordinal
            # '[no data]' cells (gas, non-domestic and all meters, two districts) emit
            # no fact; a record set is cut per measure set so every kept cell is a number.
            for subset_id, subset in _split_by_markers(grid, rows, measures):
                record_set_id = (
                    f"desnz.subnational.northern_ireland.{fuel}.{group}.y{year}"
                    + (f".{subset_id}" if subset_id else "")
                )
                kept_rows, kept_measures = subset
                kept_rows = [dict(r, ordinal=i) for i, r in enumerate(kept_rows)]
                if "guard_cells" not in kept_rows[0]:
                    kept_rows[0]["guard_cells"] = [
                        {
                            "column": "A",
                            "row": 1,
                            "expected_value": title,
                            "label": "sheet title",
                        }
                    ]
                record_sets.append(
                    {
                        "record_set_id": record_set_id,
                        "provenance_class": "administrative",
                        "assertion": "observation",
                        "record_set_spec_id": f"{record_set_id}.v1",
                        "source_record_id_prefix": record_set_id,
                        "sheet_name": sheet,
                        **period,
                        "geography_id": "N92000002",
                        "geography_level": "country",
                        "geography_name": "Northern Ireland",
                        "geography_vintage": "current",
                        "entity": entity,
                        "entity_role": role,
                        "domain": domain,
                        "groupby_dimension": "desnz.subnational.area",
                        "shared_filters": {
                            "fuel": fuel,
                            "temperature_adjustment": temperature,
                        },
                        "shared_constraints": [
                            constraint("fuel", fuel, "Fuel"),
                            constraint(
                                "temperature_adjustment",
                                temperature,
                                "Temperature adjustment",
                            ),
                        ],
                        "rows": kept_rows,
                        "measures": [
                            dict(m, ordinal=i) for i, m in enumerate(kept_measures)
                        ],
                    }
                )
    package_id = f"desnz-subnational-{fuel}-consumption-northern-ireland-2024"
    scopes_used = sorted(
        {m["filters"]["domestic_scope"] for rs in record_sets for m in rs["measures"]}
    )
    metrics_used = sorted(
        {m["filters"]["metric"] for rs in record_sets for m in rs["measures"]}
    )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": package_id,
        "label": (
            f"DESNZ subnational {fuel} consumption, Northern Ireland, by local government "
            f"district, {years[0]} to {years[-1]}"
        ),
        "dimension_labels": DESNZ_SHARED_LABELS,
        "dimension_value_labels": {
            "fuel": {fuel: fuel.capitalize()},
            "domestic_scope": {s: DOMESTIC_SCOPES[s] for s in scopes_used},
            "temperature_adjustment": (
                {"as_reported": "As reported"}
                if fuel == "electricity"
                else {"weather_corrected": "Weather corrected"}
            ),
            "metric": {m: METRICS[m] for m in metrics_used},
        },
        "artifact": {
            "source_name": "desnz",
            "source_table": (
                f"Subnational {fuel} consumption statistics in Northern Ireland, "
                f"{years[0]} to {years[-1]}"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{directory}",
            "manifest": "manifest.yaml",
            "vintage": "publication_2025_12_18",
            "extracted_at": "2026-10-15",
            "extraction_method": "XLSX used-range cell parse of the year worksheets",
            "parser": "xlsx_used_range",
            "artifact_year": 2025,
            "sheets": [str(y) for y in years],
        },
        "record_sets": record_sets,
    }
    header = NI_ELECTRICITY_HEADER if fuel == "electricity" else NI_GAS_HEADER
    write_package(ROOT / "packages" / directory, payload, header)


def _split_by_markers(grid, rows, measures):
    """Group a record set's rows so every selected cell holds a number.

    Rows whose cells are all numbers stay in one subset with every measure. A row
    with a '[no data]' marker or a blank (a mean over no meters) keeps only the
    measures it publishes, in a subset of its own named after the row.
    """
    clean, marked = [], []
    for row in rows:
        values = [grid.get((row["row_number"], m["column"])) for m in measures]
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
            clean.append(row)
        else:
            # '[no data]' is a suppressed figure; a blank mean means no meters of the type.
            assert all(
                isinstance(v, (int, float)) or v in ("[no data]", None) for v in values
            ), (row["value_id"], values)
            marked.append(row)
    subsets = [("", (clean, measures))] if clean else []
    for row in marked:
        kept = [
            m
            for m in measures
            if isinstance(grid.get((row["row_number"], m["column"])), (int, float))
        ]
        if kept:
            subsets.append((row["value_id"], ([row], kept)))
    return subsets


NI_ELECTRICITY_HEADER = """\
# DESNZ 'Subnational electricity consumption statistics in Northern Ireland', 2009 to 2024
# (published 18 December 2025), for PolicyEngine/chronicle#356 item 1: every year sheet and
# measure. Microcosm uses the Northern Ireland row to split DESNZ Energy Trends' UK level
# into its GB and NI parts.
#
# Measures, by domestic scope (Domestic Standard, Domestic Economy 7, All Domestic, All
# Non-Domestic and, from 2015, All meters): number of meters (thousands, scaled to a count),
# total consumption (GWh, scaled to kWh), mean consumption per meter (kWh) and, from 2015,
# median consumption per meter (kWh). Domestic measures carry the household entity and the
# concepts the GB package uses (desnz.subnational.domestic_electricity_*); non-domestic and
# all-meter measures are separate record sets on the institutional-sector entity.
#
# Periods (cover sheet; methodology section 5): 2009 to 2011 are calendar years and 2012
# onwards financial years (1 April to 31 March), stamped fiscal_year by opening year, the
# publisher's label. Unlike Great Britain's February-to-January electricity years, and not
# weather corrected. 2015 onwards are on a consistent basis not comparable with earlier
# years (cover sheet). DESNZ says Northern Ireland's electricity statistics are not directly
# comparable with Great Britain's (methodology section 5.3); every measure's evidence notes
# carry that, and the domestic ones that Northern Ireland files three domestic_scope rows
# (standard, Economy 7, all domestic) under one concept.
#
# Geography: the Northern Ireland row (N92000002; 'UKN' before 2015) includes the
# 'Unallocated' meters, which are their own row (desnz:northern_ireland_unallocated). From
# 2015 the rows are the 11 local government districts (N09 codes, 2014 boundaries); 2009 to
# 2014 use the 26 pre-2015 districts under the NUTS/LAU codes the workbook prints (UKN0301
# and so on).
"""

NI_GAS_HEADER = """\
# DESNZ 'Subnational gas consumption statistics in Northern Ireland', 2015 to 2024 (published
# 18 December 2025), for PolicyEngine/chronicle#356 item 1: every year sheet and measure.
#
# Measures, by scope (Domestic, Non-Domestic, All meters): number of meters (thousands,
# scaled to a count), total consumption (GWh, scaled to kWh) and mean consumption per meter
# (kWh). The workbook publishes no median. Domestic or non-domestic follows each meter's
# profile marker, so Northern Ireland is not directly comparable with Great Britain's
# 73,200 kWh threshold (methodology sections 4.2 and 4.3; every measure's evidence notes
# carry it). Figures are weather corrected.
#
# Periods: DESNZ gas years (period_type gas_year, under the publisher's year label) with the
# exact dates the methodology booklet gives for Northern Ireland (section 4.1): 1 October 2014
# to 30 September 2015 for 2015, 15 July and 15 June in 2016 and 2017, and 15 May to 15 May
# from 2018 (2024 is 15 May 2024 to 15 May 2025).
#
# Geography: the Northern Ireland row (N92000002) and the 11 local government districts (N09
# codes, 2014 boundaries); every meter is assigned to a district, so there is no unallocated
# row. '[no data]' marks a figure suppressed so the statistics are not disclosive (cover
# sheet): Fermanagh and Omagh and Mid Ulster's non-domestic and all-meter cells in 2019 to
# 2024. A blank mean means there were no meters of the type (cover sheet). Neither emits a
# fact; the rest of each row is ported.
"""


# --------------------------------------------------------------------------- LSOA

LSOA = {
    "gas": (
        "desnz/lsoa_domestic_gas_consumption_2024",
        "LSOA_domestic_gas_2010-2024.xlsx",
        "https://www.gov.uk/government/statistics/lower-and-middle-super-output-areas-gas-consumption",
    ),
    "electricity": (
        "desnz/lsoa_domestic_electricity_consumption_2024",
        "LSOA_domestic_elec_2010-2024.xlsx",
        "https://www.gov.uk/government/statistics/lower-and-middle-super-output-areas-electricity-consumption",
    ),
}
LSOA_UNALLOCATED = {
    "geography_id": "desnz:great_britain_unallocated",
    "geography_level": "statistical_scope",
    "geography_name": "Unallocated",
    "geography_vintage": "current",
}


def lsoa_geography(code: str, name: str) -> dict:
    if code == "Unallocated":
        return dict(LSOA_UNALLOCATED)
    if re.fullmatch(r"[EW]01\d{6}", code):
        vintage = "lsoa_2021"
    else:
        assert re.fullmatch(r"S01\d{6}", code), code
        vintage = "dz_2022"
    return {
        "geography_id": code,
        "geography_level": "statistical_scope",
        "geography_name": name,
        "geography_vintage": vintage,
    }


def build_lsoa(fuel: str) -> None:
    directory, filename, url = LSOA[fuel]
    # The workbook is R2-only (storage.local: false), so read it through its
    # manifest: committed, cached, or fetched with LEDGER_SOURCE_ARTIFACT_FETCH=1.
    content = read_registered_artifact(
        ROOT / "db/data" / directory / "manifest.yaml", 2025
    )
    cells = source_cells_from_xlsx(
        content,
        artifact_meta(filename),
        sheets=("2023", "2024"),
        read_only=True,
    )
    sheet_grids = grids(cells)
    measures_meta = (
        # (column, header, metric, concept suffix, unit)
        ("G", "meter_count", "meter_count", "count"),
        ("H", "consumption", "consumption", "kwh"),
    )
    shared_rows: dict[tuple, FlowRow] = {}
    record_sets = []
    counts = {}
    for year in (2023, 2024):
        sheet = str(year)
        grid = sheet_grids[sheet]
        noun = "gas" if fuel == "gas" else "electricity"
        title = grid[(1, "A")]
        assert title == (
            f"Domestic {noun} consumption by Lower Layer Super Output Area (LSOA), Great "
            f"Britain, {year}"
        ), title
        assert (
            grid[(5, "E")] == "LSOA code"
            and grid[(5, "F")] == "Lower layer super output area"
        )
        measures = []
        for ordinal, (column, metric, concept_suffix, unit) in enumerate(measures_meta):
            header = grid[(5, column)]
            expected = (
                "Number\nof meters"
                if metric == "meter_count"
                else "Total \nconsumption\n(kWh)"
            )
            assert str(header).rstrip("\n") == expected, (sheet, column, header)
            concept = f"desnz.subnational.domestic_{fuel}_{concept_suffix}"
            notes = (
                f"DESNZ LSOA domestic {noun} workbook, sheet {sheet}, column {column}: "
                + (
                    "number of domestic meters"
                    if metric == "meter_count"
                    else "total domestic consumption, kWh"
                )
                + (
                    " (consuming meters only; non-consuming meters are a separate column, not ported)"
                    if fuel == "gas" and metric == "meter_count"
                    else ""
                )
                + ". Areas with no domestic meters, or whose meters were moved to 'Unallocated' for "
                "disclosure control (fewer than 5 meters, or the top two meters over 90 per cent "
                "of consumption), are blank and emit no fact. DESNZ advises against aggregating "
                "LSOA figures to local authority, region or country (cover sheet)."
            )
            measures.append(
                {
                    "measure_id": f"domestic_{metric}",
                    "label": f"Domestic {noun} "
                    + ("meter count" if metric == "meter_count" else "consumption"),
                    "ordinal": ordinal,
                    "column": column,
                    "source_column_id": f"domestic_{metric}",
                    "expected_column_header_row": 5,
                    "expected_column_header": header,
                    "concept": concept,
                    "source_concept": concept,
                    "concept_relation": "source_label",
                    "concept_authority": "desnz",
                    "concept_evidence_url": url,
                    "concept_evidence_notes": notes,
                    "unit": unit,
                    "aggregation": "sum",
                    "expected_cell_type": "number",
                    "filters": {"metric": metric},
                    "constraints": [constraint("metric", metric, "Metric")],
                }
            )
        rows = []
        blank = 0
        row = 6
        while (row, "E") in grid:
            code = grid[(row, "E")]
            name = grid[(row, "F")]
            values = [grid.get((row, column)) for column, *_ in measures_meta]
            if all(v is None for v in values):
                blank += 1
                row += 1
                continue
            assert all(isinstance(v, (int, float)) for v in values), (
                sheet,
                row,
                values,
            )
            key = (row, code, name)
            if key not in shared_rows:
                shared_rows[key] = FlowRow(
                    value_id=code.lower(),
                    label=name,
                    ordinal=row - 6,
                    row_number=row,
                    expected_row_header_column="E",
                    expected_row_header=code,
                    table_record_kind="total",
                    **lsoa_geography(code, name),
                )
            rows.append(shared_rows[key])
            row += 1
        assert grid[(row - 1, "E")] == "Unallocated", (sheet, row - 1)
        counts[year] = (len(rows), blank)
        if fuel == "gas":
            period = {
                "period_type": "gas_year",
                "period": year,
                "period_coverage": {
                    "basis": "survey_reference",
                    "source_period_label": f"{year} (mid-May {year} to mid-May {year + 1})",
                    "notes": (
                        f"DESNZ's {year} gas year (gas_year, labelled by its opening year): "
                        "mid-May to mid-May, with no exact dates published for Great Britain; "
                        "weather corrected (cover sheet)."
                    ),
                },
            }
            temperature = "weather_corrected"
            record_set_id = f"desnz.lsoa.gas.gy{year}"
        else:
            period = {
                "period_type": "calendar_year",
                "period": year,
                "period_coverage": {
                    "start_date": f"{year}-02-01",
                    "end_date": f"{year + 1}-01-31",
                    "basis": "survey_reference",
                    "source_period_label": str(year),
                    "notes": (
                        "Domestic non-half-hourly electricity meters cover February through "
                        "January (cover sheet), as the local-authority package stamps them."
                    ),
                },
            }
            temperature = "as_reported"
            record_set_id = f"desnz.lsoa.electricity.cy{year}"
        first = dict(rows[0])
        first["guard_cells"] = [
            {"column": "A", "row": 1, "expected_value": title, "label": "sheet title"}
        ]
        rows = [FlowRow(first)] + rows[1:]
        record_sets.append(
            {
                "record_set_id": record_set_id,
                "provenance_class": "administrative",
                "assertion": "observation",
                "record_set_spec_id": f"{record_set_id}.v1",
                "source_record_id_prefix": record_set_id,
                "sheet_name": sheet,
                **period,
                "geography_id": "K03000001",
                "geography_level": "country",
                "geography_name": "Great Britain",
                "geography_vintage": "current",
                "entity": "household",
                "entity_role": "domestic_energy_customer",
                "domain": "domestic_energy_consumption",
                "groupby_dimension": "desnz.subnational.area",
                "shared_filters": {
                    "fuel": fuel,
                    "domestic_scope": "all_domestic",
                    "temperature_adjustment": temperature,
                },
                "shared_constraints": [
                    constraint("fuel", fuel, "Fuel"),
                    constraint("domestic_scope", "all_domestic", "Domestic scope"),
                    constraint(
                        "temperature_adjustment", temperature, "Temperature adjustment"
                    ),
                ],
                "measures": measures,
                "rows": rows,
            }
        )
    print(f"LSOA {fuel}: rows kept/blank by year", counts)
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": f"desnz-lsoa-domestic-{fuel}-consumption-2024",
        "label": (
            f"DESNZ domestic {fuel} meter counts and consumption by LSOA (England and Wales) "
            "and data zone (Scotland), 2023 and 2024"
        ),
        "dimension_labels": DESNZ_SHARED_LABELS,
        "dimension_value_labels": {
            "fuel": {fuel: fuel.capitalize()},
            "domestic_scope": {"all_domestic": DOMESTIC_SCOPES["all_domestic"]},
            "temperature_adjustment": (
                {"weather_corrected": "Weather corrected"}
                if fuel == "gas"
                else {"as_reported": "As reported"}
            ),
            "metric": {
                "meter_count": METRICS["meter_count"],
                "consumption": METRICS["consumption"],
            },
        },
        "artifact": {
            "source_name": "desnz",
            "source_table": (
                f"Domestic {fuel} consumption by Lower Layer Super Output Area (LSOA), Great "
                "Britain, 2010 to 2024"
            ),
            "resource_package": "db",
            "resource_directory": f"data/{directory}",
            "manifest": "manifest.yaml",
            "vintage": "publication_2025_12",
            "extracted_at": "2026-10-15",
            "extraction_method": (
                "XLSX used-range cell parse of the 2023 and 2024 worksheets, streamed read-only"
            ),
            "parser": "xlsx_read_only_used_range",
            "artifact_year": 2025,
            "sheets": ["2023", "2024"],
        },
        "record_sets": record_sets,
    }
    header = LSOA_HEADER.format(fuel=fuel, noun=fuel)
    write_package(ROOT / "packages" / directory, payload, header, dumper=AnchoredDumper)


LSOA_HEADER = """\
# DESNZ domestic {noun} consumption by Lower Layer Super Output Area, Great Britain, 2010 to
# 2024 (December 2025), for PolicyEngine/chronicle#356 item 3. Per the request's ruling
# (meters and kWh at LSOA), the package ports the number of domestic meters and the total
# domestic consumption (kWh) for 2023 and 2024, the years Microcosm reads: the additive
# measures it sums to constituencies through its best-fit supports. Mean and median per
# meter, the gas non-consuming meters and 2010 to 2022 stay in the preserved workbook; the
# MSOA and intermediate-zone workbook is registered raw-only.
#
# Geography: 33,755 English and 1,917 Welsh LSOAs on 2021 boundaries and 7,392 Scottish data
# zones on 2022 boundaries (geography_level statistical_scope, vintages lsoa_2021 and
# dz_2022), as the workbook carries them for 2015 onwards, plus the 'Unallocated' row
# (desnz:great_britain_unallocated): consumption DESNZ could not place, including areas moved
# there for disclosure control. Blank rows (no domestic meters matched, or moved to
# Unallocated) emit no fact; DESNZ uses no text markers. DESNZ advises against aggregating
# these figures to local authority, region or country (cover sheet).
#
# Periods follow the local-authority packages: gas years (gas_year, mid-May to mid-May) for
# gas and February-to-January years for domestic electricity. Rows whose position and labels
# are the same in both years are written once and referenced by YAML alias.
"""


# ------------------------------------------------------------------------ BUS04

BUS04_DIR = "dft/bus04i_operating_revenue_2025"
BUS04_ODS = "bus04i.ods"
BUS04_URL = (
    "https://www.gov.uk/government/statistical-data-sets/bus-statistics-data-tables"
)
BUS04_COUNTRIES = (
    ("F", "Scotland", "S92000003"),
    ("G", "Wales", "W92000004"),
    ("H", "Great Britain", "K03000001"),
)


def build_bus04() -> None:
    path = ROOT / "db/data" / BUS04_DIR / BUS04_ODS
    grid = grids(source_cells_from_ods(path.read_bytes(), artifact_meta(BUS04_ODS)))[
        "BUS04ai"
    ]
    title = grid[(1, "A")]
    assert title.startswith(
        "Operating revenue [note 1] (at current prices [note 2]) on local b"
    ), title
    assert grid[(4, "A")] == "Table BUS04ai" and grid[(7, "A")] == "£ (millions)"
    assert grid[(8, "A")] == "Year ending March"
    record_sets = []
    for row, year_ending in ((28, 2024), (29, 2025)):
        assert grid[(row, "A")] == year_ending, (row, grid[(row, "A")])
        # DfT labels the year by its March end year, a single-year label, which the
        # period keeps (as the BUS05i package does): 2024 is April 2023 to March 2024.
        opening = year_ending - 1
        for column, name, code in BUS04_COUNTRIES:
            assert grid[(8, column)] == name, (column, grid[(8, column)])
            assert isinstance(grid[(row, column)], float)
            record_set_id = (
                f"dft.bus04ai.operating_revenue.{code.lower()}.fy{year_ending}"
            )
            record_sets.append(
                {
                    "record_set_id": record_set_id,
                    "provenance_class": "administrative",
                    "record_set_spec_id": f"{record_set_id}.v1",
                    "source_record_id_prefix": record_set_id,
                    "sheet_name": "BUS04ai",
                    "period_type": "fiscal_year",
                    "period": year_ending,
                    "period_coverage": {
                        "basis": "fiscal",
                        "source_period_label": f"Year ending March {year_ending}",
                        "start_date": f"{opening}-04-01",
                        "end_date": f"{year_ending}-03-31",
                        "accounting_basis": "accrual",
                        "notes": "DfT labels the reporting year by its March end year.",
                    },
                    "geography_id": code,
                    "geography_level": "country",
                    "geography_name": name,
                    "geography_vintage": "current",
                    "entity": "institutional_sector",
                    "entity_role": "local_bus_service_operators",
                    "domain": "local_bus_finance",
                    "groupby_dimension": "dft.bus_area",
                    "rows": [
                        {
                            "value_id": code.lower(),
                            "label": name,
                            "ordinal": 0,
                            "row_number": row,
                            "expected_row_header_column": "A",
                            "expected_row_header": year_ending,
                            "table_record_kind": "total",
                            "guard_cells": [
                                {
                                    "column": "A",
                                    "row": 4,
                                    "expected_value": "Table BUS04ai",
                                    "label": "table id",
                                },
                                {
                                    "column": "A",
                                    "row": 7,
                                    "expected_value": "£ (millions)",
                                    "label": "unit",
                                },
                            ],
                        }
                    ],
                    "measures": [
                        {
                            "measure_id": "total_estimated_operating_revenue",
                            "label": f"Total estimated operating revenue, {name}, year ending March {year_ending}",
                            "ordinal": 0,
                            "column": column,
                            "source_column_id": "total_estimated_operating_revenue",
                            "expected_column_header_row": 8,
                            "expected_column_header": name,
                            "concept": "dft.local_bus_total_estimated_operating_revenue",
                            "source_concept": "dft.local_bus_total_estimated_operating_revenue",
                            "concept_relation": "source_label",
                            "concept_authority": "dft",
                            "concept_evidence_url": BUS04_URL,
                            "concept_evidence_notes": (
                                "DfT BUS04ai, operating revenue on local bus services at current "
                                "prices, GBP million scaled to GBP: passenger fare receipts, "
                                "concessionary travel reimbursement, Bus Service Operators Grant "
                                "and public transport support combined (note 1). DfT publishes no "
                                "split of fares or support for Scotland, Wales or Great Britain; "
                                "BUS05 is England only. Operator survey with imputation for "
                                "non-sampled and non-responding operators (quality report)."
                            ),
                            "unit": "gbp",
                            "aggregation": "sum",
                            "value_scale": 1000000,
                            "expected_cell_type": "number",
                        }
                    ],
                }
            )
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "dft-bus04i-operating-revenue-2025",
        "label": (
            "DfT BUS04ai local bus total estimated operating revenue, Scotland, Wales and Great "
            "Britain, years ending March 2024 and 2025"
        ),
        "dimension_labels": {"dft.bus_area": "Local bus statistics area"},
        "artifact": {
            "source_name": "dft",
            "source_table": "BUS04ai operating revenue on local bus services by area, current prices",
            "resource_package": "db",
            "resource_directory": f"data/{BUS04_DIR}",
            "manifest": "manifest.yaml",
            "vintage": "bus_statistics_2025",
            "extracted_at": "2026-10-15",
            "extraction_method": "ODS whole-workbook used-range cell parse",
            "parser": "ods_used_range",
            "artifact_year": 2025,
        },
        "record_sets": record_sets,
    }
    write_package(ROOT / "packages" / BUS04_DIR, payload, BUS04_HEADER)


BUS04_HEADER = """\
# DfT BUS04ai (bus statistics, March 2026 revision of the 26 November 2025 release), for
# PolicyEngine/chronicle#356 item 5. The request asked for passenger fare receipts and the
# BUS05 support lines for England, Wales, Scotland and Great Britain. DfT publishes neither by
# country: BUS05 covers England and its areas only (dft-bus05i-revenue-support-2025), and
# BUS04ai, the only DfT table with Scotland, Wales and Great Britain, publishes total estimated
# operating revenue alone (fares, concessionary reimbursement, BSOG and support combined; note
# 1). This package ports that line for Scotland, Wales and Great Britain, years ending March
# 2024 and 2025 (FY2023-24 and FY2024-25), GBP million at current prices. DfT labels a year by
# its March end, a single-year label the period keeps, as the BUS05i package does. England is not
# repeated: its BUS04ai cells equal BUS05ai's 'Total estimated operating revenue', which the
# BUS05i package already carries under the same concept.
"""


if __name__ == "__main__":
    build_ni("electricity")
    build_ni("gas")
    build_lsoa("gas")
    build_lsoa("electricity")
    build_bus04()
