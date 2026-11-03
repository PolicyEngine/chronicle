"""Author the chronicle#326 package: NRS UV404 household tenure by 2022 output area.

Writes ``nrs-census2022-uv404-tenure-output-area`` from the bytes the manifest pins
under ``db/data`` (nothing downloaded and no fact built): all occupied households
and the published 'Private rented: Total' for each of Scotland's 46,363 output
areas, the counts Microcosm sums to Broad Rental Market Areas. Cells NRS prints as
'-' emit no fact; the parsed source rows keep the symbol.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = "nrs/census2022_uv404_tenure_output_area"
FILENAME = "census2022_uv404_household_tenure_households_oa.csv"
HEADER_ROW = 4
MEASURES = (
    # (column, publisher header, record set slug)
    ("B", "All occupied households", "all_occupied_households"),
    ("I", "Private rented: Total", "private_rented_total"),
)


class AnchoredDumper(yaml.SafeDumper):
    """Emit YAML anchors for the row mappings both record sets share."""

    def ignore_aliases(self, data: object) -> bool:
        return not isinstance(data, FlowRow)


class FlowRow(dict):
    """A row mapping written in flow style."""


AnchoredDumper.add_representer(
    FlowRow,
    lambda dumper, data: dumper.represent_mapping(
        "tag:yaml.org,2002:map", data.items(), flow_style=True
    ),
)


def build() -> None:
    text = (ROOT / "db/data" / DIRECTORY / FILENAME).read_bytes().decode("ascii")
    lines = text.splitlines()
    assert lines[0] == "Scotland's Census 2022 - National Records of Scotland", lines[0]
    assert lines[1] == "Table UV404 - Household tenure - Households", lines[1]
    assert lines[2] == "All occupied households", lines[2]
    reader = csv.reader(io.StringIO("\n".join(lines[HEADER_ROW - 1 :])))
    header = next(reader)
    assert header[0] == "" and len(header) == 12, header
    for column, label, _ in MEASURES:
        assert header[ord(column) - 65] == label, (column, header[ord(column) - 65])
    data = []
    for values in reader:
        if len(values) == 12 and values[0].startswith("S00"):
            data.append(values)
        else:
            break
    assert len(data) == 46363, len(data)

    rows_by_code: dict[str, FlowRow] = {}
    record_sets = []
    markers = {}
    for column, label, slug in MEASURES:
        index = ord(column) - 65
        rows = []
        marked = 0
        for offset, values in enumerate(data):
            code, raw = values[0], values[index]
            if raw == "-":
                marked += 1
                continue
            assert raw.isdigit(), (code, label, raw)
            if code not in rows_by_code:
                row_number = offset + 2  # virtual table: header on row 1
                rows_by_code[code] = FlowRow(
                    value_id=code.lower(),
                    label=code,
                    ordinal=offset,
                    row_number=row_number,
                    expected_row_header_column="A",
                    expected_row_header=code,
                    geography_id=code,
                    geography_level="statistical_scope",
                    geography_name=code,
                    geography_vintage="oa_2022",
                    table_record_kind="total",
                )
            rows.append(rows_by_code[code])
        markers[label] = marked
        first = FlowRow(rows[0])
        first["guard_cells"] = [
            {
                "column": column,
                "row": 1,
                "expected_value": label,
                "label": "publisher tenure column",
            }
        ]
        rows = [first] + rows[1:]
        record_set_id = f"nrs.census2022.uv404.oa.{slug}"
        record_sets.append(
            {
                "record_set_id": record_set_id,
                "provenance_class": "census",
                "record_set_spec_id": f"{record_set_id}.v1",
                "source_record_id_prefix": record_set_id,
                "sheet_name": FILENAME,
                "period_type": "calendar_year",
                "period": 2022,
                "period_coverage": {
                    "start_date": "2022-03-20",
                    "end_date": "2022-03-20",
                    "basis": "calendar",
                    "source_period_label": "Census 2022",
                    "notes": "Census day 20 March 2022; occupied households.",
                },
                "geography_id": "S92000003",
                "geography_level": "country",
                "geography_name": "Scotland",
                "geography_vintage": "current",
                "entity": "household",
                "entity_role": "occupied_household",
                "domain": "housing_tenure",
                "groupby_dimension": "geography",
                "measures": [
                    {
                        "measure_id": "households",
                        "label": f"Occupied households: {label}",
                        "ordinal": 0,
                        "column": column,
                        "source_column_id": label,
                        "source_column_dimensions": {"household_tenure": label},
                        "filters": {"household_tenure": label},
                        "constraints": [
                            {
                                "variable": "household_tenure",
                                "operator": "==",
                                "value": label,
                                "label": "publisher tenure category",
                            }
                        ],
                        "expected_column_header_row": 1,
                        "expected_column_header": label,
                        "concept": "nrs.census2022_households",
                        "concept_evidence_url": (
                            "https://www.scotlandscensus.gov.uk/documents/2022-output-area-data/"
                        ),
                        "concept_evidence_notes": (
                            f"UV404 column {column} ('{label}'), as published: NRS's own "
                            + (
                                "all-households total"
                                if column == "B"
                                else "private-rented total, not a sum of its two details"
                            )
                            + ". Cells are disclosure-controlled (record swapping and cell key "
                            "perturbation) and need not add up; '-' cells emit no fact."
                        ),
                        "unit": "count",
                        "aggregation": "sum",
                        "expected_cell_type": "number",
                    }
                ],
                "rows": rows,
            }
        )
    print("UV404 OA '-' cells skipped:", markers)
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": "nrs-census2022-uv404-tenure-output-area",
        "label": (
            "Scotland's Census 2022 UV404: all occupied households and private-rented "
            "households, 2022 output areas"
        ),
        # The council-area and constituency UV404 packages label the tenure axis
        # 'publisher tenure category' and each value by its publisher text; the
        # bundle refuses a dimension two packages label differently.
        "dimension_labels": {
            "geography": "Geography",
            "household_tenure": "publisher tenure category",
        },
        "dimension_value_labels": {
            "household_tenure": {header: header for _, header, _ in MEASURES},
        },
        "artifact": {
            "source_name": "nrs",
            "source_table": "Scotland's Census 2022 UV404 household tenure, households, 2022 output areas",
            "resource_package": "db",
            "resource_directory": f"data/{DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "census_2022_output_area_release_2024",
            "extracted_at": "2026-10-15",
            "extraction_method": (
                "Delimited text full-row parse below the three-line title preamble, one source "
                "row per output area"
            ),
            "parser": "delimited_text_full_rows",
            "sheet_name": FILENAME,
            "header_row": HEADER_ROW,
            "artifact_year": 2022,
        },
        "record_sets": record_sets,
    }
    directory = ROOT / "packages" / DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "source_package.yaml").write_text(
        HEADER
        + yaml.dump(
            payload,
            Dumper=AnchoredDumper,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        ),
        encoding="utf-8",
    )


HEADER = """\
# Scotland's Census 2022 UV404 (household tenure, households) for the 46,363 2022 output
# areas, for PolicyEngine/chronicle#326. Census day 20 March 2022.
#
# Route: the issue's original request was the table-builder export of tenure by bedrooms for
# the 355 2022 electoral wards (household2022ftb), which PolicyEngine/microcosm#1092 pins as
# sha256 03d6157d. That export was not found in any repository, release or cache, and a new
# one needs a guest session that accepts NRS's table-builder user agreement and would not
# reproduce the pinned checksum. Chronicle takes the alternative #313 offers and the issue's
# completion criteria allow: NRS's public UV404 output-area table (Open Government Licence
# v3). It gives the bedroom-independent private-renter counts for Microcosm's BRMA targets
# without proportional ward splitting. It carries no tenure-by-bedrooms joint distribution;
# that limitation stands, and Chronicle synthesizes no joint counts.
#
# Artifact: the UK Data Service copy of the CSV, byte for byte the 'UV404 - Household tenure
# - Households.csv' member of NRS's 2022 output-area topic ZIP (Census-2022-Output-Area-v1.zip,
# sha256 6e1673ba, 73.6 MB, landing page https://www.scotlandscensus.gov.uk/documents/2022-
# output-area-data/). Three title lines, a header row whose first field (the output-area code
# column) is blank, one row per output area, then a five-line footer.
#
# Ported, as the ruling of 15 October 2026 sets: column B 'All occupied households' and column
# I 'Private rented: Total', NRS's own published total, not a sum of its two detail columns.
# The other tenure columns stay in the preserved file and its parsed source rows.
#
# Markers: NRS prints '-' in 4,910 'Private rented: Total' cells (none in column B). No NRS
# page or file defines the symbol. NRS's disclosure control (targeted record swapping and
# cell key perturbation) publishes small counts, including zero, rather than suppressing them,
# and with '-' read as zero the output-area sums match the ward and council tables within
# perturbation noise, so '-' most likely means zero. The file supports that too: across its
# ten count columns it prints 168,890 '-' cells and not one literal '0'. Without a primary
# definition, Chronicle keeps the symbol in the source rows and emits no fact for those cells,
# so 4,910 output areas (10.6%) carry no private-rented fact.
#
# Geography: NRS gives output areas no names; the only label it prints for an area is its
# code, so the code is each fact's geography name as well as its id (statistical_scope,
# vintage oa_2022). Rows the two record sets share are written once and referenced by alias.
"""


if __name__ == "__main__":
    build()
