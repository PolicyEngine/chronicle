"""Generate the Scottish Government's Band I and J estimates for PolicyEngine/chronicle#420.

Run from the repository root:

    uv run python scripts/build_uk_scottish_high_value_bands_package.py

``--check`` compares the generated YAML with the committed file instead of writing. The
package is written from the pinned consultation paper, read with Chronicle's own PDF
parser, so every row number and guard cell below is one the package parser sees. The
publisher's text is asserted, so a run against different bytes fails rather than
drifting. Nothing is downloaded and no value is computed.

Item 13 of PolicyEngine/chronicle#420, asked in PolicyEngine/chronicle#435 for
Microcosm's next data PR, for extending Microcosm's home-value step to Scotland
(PolicyEngine/uk-scottish-budget-2027-28#5; PolicyEngine/microcosm#1112): the
consultation's estimates of homes in the proposed council tax Bands I (more than £1
million and up to £2 million) and J (more than £2 million) at 1 April 2026 values, and of
the additional revenue they would raise, as the published ranges. The item's other part,
Registers of Scotland's sales over £1 million, is the package
ros-property-market-report-2025-26 (scripts/build_uk_ros_high_value_sales_package.py).
RoS publishes no split above £2 million.
"""

from __future__ import annotations

import argparse
import hashlib
import textwrap
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import yaml
from pypdf import PdfReader

from chronicle.sources.cells import (
    SourceArtifactMetadata,
    source_cells_from_pdf_text_numbers,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
DATA = ROOT / "db/data"
EXTRACTED_AT = "2026-11-10"
ISSUE = "PolicyEngine/chronicle#420"
SCRIPT = "scripts/build_uk_scottish_high_value_bands_package.py"
PACKAGE_ID = "scotgov-council-tax-high-value-bands-consultation-2026"
DIRECTORY = "scotgov/council_tax_high_value_bands_consultation_2026"
PAGE = (
    "https://www.gov.scot/publications/"
    "consultation-council-tax-high-value-property-bands-mansion-tax/"
)
TITLE = "Council Tax High-Value Property Bands (Mansion Tax): consultation"
FIGURE_PAGE = 9


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


def pinned(directory: str) -> tuple[dict, bytes]:
    """The manifest's one file entry and its bytes, checked against the pinned digest."""
    manifest = yaml.safe_load((DATA / directory / "manifest.yaml").read_text())
    (entry,) = manifest["files"].values()
    content = (DATA / directory / entry["filename"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"], directory
    assert len(content) == entry["size_bytes"], directory
    return entry, content


def squeeze(text: object) -> str:
    return " ".join(str(text).split())


def constraint(variable: str, value: str, label: str) -> Flow:
    return Flow(variable=variable, operator="==", value=value, label=label)


def guard(column: str, value: object, label: str) -> Flow:
    return Flow(column=column, expected_value=value, label=label)


def pdf_pages(content: bytes):
    return PdfReader(BytesIO(content)).pages


def number_rows(content: bytes, filename: str) -> dict[int, dict[int, object]]:
    """{row: {column: value}} of the parser's document_numbers sheet."""
    metadata = SourceArtifactMetadata(
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
    rows: dict[int, dict[int, object]] = defaultdict(dict)
    for cell in source_cells_from_pdf_text_numbers(content, metadata):
        rows[cell.row_number][cell.column_number] = cell.raw_value
    return rows


# The paper's text the package relies on, asserted against the pinned bytes.
BANDS_TEXT = (
    "Band I: for properties with an estimated open market capital value of more than £1 "
    "million and up to £2 million as at 1 April 2026.",
    "Band J: for properties with an estimated open market capital value of more than £2 "
    "million as at 1 April 2026.",
    "The Scottish Government estimates that this is expected to affect fewer than 1% of all "
    "homes in Scotland - approximately 15,000 properties in total (see Figure 3 below).",
)
REVENUE_TEXT = (
    "The rates below are illustrative.",
    "2.886 for Band I - equivalent to an annual charge of around £4,770 (based on 2026-27 "
    "Band D charges).",
    "4.628 for Band J - equivalent to an annual charge of around £7,650 (based on 2026-27 "
    "Band D charges).",
    "the new bands are estimated to raise between £12 million and £16 million per year in "
    "total across Scotland.",
)
# What the revenue is measured against: each band's increase over the average Band H
# charge. Figure 2 is Figure 3's property estimates times these increases.
BAND_H_TEXT = (
    "This means that, compared to the average Band H charge, it is estimated that:",
    "Band I properties (valued between £1 million and £2 million) would pay around £720 "
    "more per year than the Band H.",
    "Band J properties (valued at over £2 million) would pay around £3,600 more per year "
    "than the Band H.",
)
BAND_H_INCREASE = {"I": 720, "J": 3_600}
SOURCE = (
    "Source: Illustrative Scottish Government estimates based on Records of Scotland data, "
    "CTAXBASE statistics and analysis by the Institute for Fiscal Studies"
)
LEGENDS = {
    "properties": "Band I (£1m to £2m)Band J (more than £2m)Estimated Number of "
    "Properties,low estimateEstimated Number of Properties,high estimate",
    "revenue": "Estimated Additional Revenue,low estimateEstimated Additional Revenue,high "
    "estimate",
}
# The charts print their data labels series by series: the low estimates for Band I and
# Band J, then the high estimates, as the legends order them.
ORDER = (("I", "low_estimate"), ("J", "low_estimate"), ("I", "high_estimate"))
ORDER += (("J", "high_estimate"),)
BAND_WORDS = {"I": "Band I (£1m to £2m)", "J": "Band J (more than £2m)"}
STATISTIC_WORDS = {"low_estimate": "low estimate", "high_estimate": "high estimate"}


def figure_rows(rows: dict, first_line: int, count: int) -> list[tuple[int, dict]]:
    """The parser rows of the first number on each of ``count`` lines from ``first_line``."""
    found = []
    for line in range(first_line, first_line + count):
        (row,) = [
            number
            for number, values in rows.items()
            if values.get(1) == FIGURE_PAGE
            and values.get(2) == line
            and values.get(4) == squeeze(values.get(3)).split(" ")[0]
        ]
        found.append((row, rows[row]))
    return found


def record_rows(found: list[tuple[int, dict]], what: str) -> list[dict]:
    entries = []
    for ordinal, ((band, statistic), (row, values)) in enumerate(zip(ORDER, found)):
        entries.append(
            {
                "value_id": f"band_{band.lower()}_{statistic}",
                "label": f"Band {band}, {STATISTIC_WORDS[statistic]}",
                "ordinal": ordinal,
                "row_number": row,
                "expected_row_header_column": "D",
                "expected_row_header": values[4],
                "table_record_kind": "detail",
                "filters": {"council_tax_band": band, "statistic": statistic},
                "constraints": [
                    constraint("council_tax_band", band, "Council tax band"),
                    constraint("statistic", statistic, "Statistic"),
                ],
                "guard_cells": [
                    guard("A", FIGURE_PAGE, f"PDF page number ({what})"),
                    guard("C", values[3], "PDF line text"),
                ],
            }
        )
    return entries


def build() -> str:
    entry, content = pinned(DIRECTORY)
    text = squeeze(" ".join(page.extract_text() or "" for page in pdf_pages(content)))
    for quote in (*BANDS_TEXT, *REVENUE_TEXT, *BAND_H_TEXT, SOURCE):
        assert squeeze(quote) in text, quote
    page_text = squeeze(pdf_pages(content)[FIGURE_PAGE - 1].extract_text())
    assert (
        "Figure 2: Estimates of additional annual revenue from Bands I and J"
        in page_text
    )
    assert "Figure 3: Estimates of number of properties in Bands I and J" in page_text
    for legend in LEGENDS.values():
        assert legend in page_text, legend
    assert "£ millions" in page_text
    rows = number_rows(content, entry["filename"])
    properties = figure_rows(rows, 5, 4)
    revenue = figure_rows(rows, 10, 4)
    counts = {key: values[5] for key, (_, values) in zip(ORDER, properties)}
    millions = {key: values[5] for key, (_, values) in zip(ORDER, revenue)}
    # The order the labels are read in, checked against the paper's own statements.
    for values in (counts, millions):
        for band in "IJ":
            assert values[(band, "low_estimate")] < values[(band, "high_estimate")]
        for statistic in STATISTIC_WORDS:
            assert values[("I", statistic)] > values[("J", statistic)]
    low = counts[("I", "low_estimate")] + counts[("J", "low_estimate")]
    high = counts[("I", "high_estimate")] + counts[("J", "high_estimate")]
    assert low < 15_000 < high, (
        low,
        high,
    )  # "approximately 15,000 properties in total"
    low_revenue = millions[("I", "low_estimate")] + millions[("J", "low_estimate")]
    high_revenue = millions[("I", "high_estimate")] + millions[("J", "high_estimate")]
    assert (round(low_revenue), round(high_revenue)) == (
        12,
        16,
    )  # "between £12m and £16m"
    # Each revenue label is its property label times the band's increase over the
    # average Band H charge, to the £0.01m the chart prints.
    for band, statistic in ORDER:
        revenue_millions = counts[(band, statistic)] * BAND_H_INCREASE[band] / 1e6
        assert abs(revenue_millions - millions[(band, statistic)]) <= 0.005, (
            band,
            statistic,
        )
    common = {
        "provenance_class": "model_output",
        "sheet_name": "document_numbers",
        "geography_id": "S92000003",
        "geography_level": "country",
        "geography_name": "Scotland",
        "geography_vintage": "current",
    }
    notes = (
        f"{TITLE} (published 6 July 2026), section 4. "
        + " ".join(f"'{quote}'" for quote in BANDS_TEXT[:2])
        + f" '{SOURCE}.' The paper calls its rates and estimates illustrative: "
        f"'{REVENUE_TEXT[0]}'"
    )
    record_sets = [
        {
            "record_set_id": "scotgov.high_value_bands_consultation_2026.properties",
            "provenance_class": common["provenance_class"],
            "assertion": "observation",
            "record_set_spec_id": "scotgov.high_value_bands_consultation_2026.properties.v1",
            "source_record_id_prefix": "scotgov.high_value_bands_consultation_2026.properties",
            "sheet_name": common["sheet_name"],
            "period_type": "month",
            "period": "2026-04",
            "period_coverage": {
                "start_date": "2026-04-01",
                "end_date": "2026-04-01",
                "basis": "calendar",
                "source_period_label": "as at 1 April 2026",
                "notes": "The bands are defined on estimated open market capital values as at "
                "1 April 2026.",
            },
            **{key: common[key] for key in common if key.startswith("geography")},
            "entity": "dwelling",
            "entity_role": "banded_property",
            "domain": "council_tax_stock",
            "groupby_dimension": "scotgov.high_value_band_estimate",
            "rows": record_rows(properties, "Figure 3"),
            "measures": [
                {
                    "measure_id": "properties",
                    "label": "Estimated number of properties",
                    "ordinal": 0,
                    "column": "E",
                    "source_column_id": "numeric_value",
                    "expected_column_header_row": 1,
                    "expected_column_header": "numeric_value",
                    "concept": "scotgov.council_tax.high_value_band_properties_estimate",
                    "source_concept": "scotgov.council_tax.high_value_band_properties_estimate",
                    "concept_relation": "source_label",
                    "concept_authority": "scotgov",
                    "concept_evidence_url": PAGE,
                    "concept_evidence_notes": "Figure 3: Estimates of number of properties in "
                    "Bands I and J (page 9), the chart's data labels: 'Estimated Number of "
                    "Properties', low and high estimates. " + notes,
                    "unit": "count",
                    "aggregation": "sum",
                    "expected_cell_type": "number",
                }
            ],
        },
        {
            "record_set_id": "scotgov.high_value_bands_consultation_2026.revenue",
            "provenance_class": common["provenance_class"],
            "assertion": "source_projection",
            "record_set_spec_id": "scotgov.high_value_bands_consultation_2026.revenue.v1",
            "source_record_id_prefix": "scotgov.high_value_bands_consultation_2026.revenue",
            "sheet_name": common["sheet_name"],
            "period_type": "fiscal_year",
            "period": 2026,
            "period_coverage": {
                "start_date": "2026-04-01",
                "end_date": "2027-03-31",
                "basis": "fiscal",
                "source_period_label": "per year, based on 2026-27 Band D charges",
                "notes": "Additional revenue per year compared to the average Band H "
                "charge, at the paper's illustrative multipliers (2.886 for Band I, 4.628 "
                "for Band J) on 2026-27 Band D charges; the period value stores the opening "
                "year of 2026-27.",
            },
            **{key: common[key] for key in common if key.startswith("geography")},
            "entity": "government",
            "entity_role": "billing_authority",
            "domain": "council_tax",
            "groupby_dimension": "scotgov.high_value_band_estimate",
            "rows": record_rows(revenue, "Figure 2"),
            "measures": [
                {
                    "measure_id": "additional_revenue",
                    "label": "Estimated additional revenue (£ millions)",
                    "ordinal": 0,
                    "column": "E",
                    "source_column_id": "numeric_value",
                    "expected_column_header_row": 1,
                    "expected_column_header": "numeric_value",
                    "concept": "scotgov.council_tax.high_value_band_additional_revenue_estimate",
                    "source_concept": (
                        "scotgov.council_tax.high_value_band_additional_revenue_estimate"
                    ),
                    "concept_relation": "source_label",
                    "concept_authority": "scotgov",
                    "concept_evidence_url": PAGE,
                    "concept_evidence_notes": "Figure 2: Estimates of additional annual "
                    "revenue from Bands I and J (page 9), the chart's data labels in £ "
                    "millions: 'Estimated Additional Revenue', low and high estimates. "
                    + " ".join(f"'{quote}'" for quote in BAND_H_TEXT)
                    + " Each figure is the matching property estimate times £720 (Band I) "
                    "or £3,600 (Band J), to the £0.01m the chart prints, so it applies the "
                    "full increase over the average Band H charge to every estimated "
                    "property. " + notes,
                    "unit": "gbp",
                    "value_scale": 1000000,
                    "aggregation": "sum",
                    "expected_cell_type": "number",
                }
            ],
        },
    ]
    payload = {
        "schema_version": "ledger.source_package.v1",
        "package_id": PACKAGE_ID,
        "label": "Scottish Government council tax Bands I and J consultation: estimated "
        "properties and additional revenue, low and high estimates",
        "dimension_labels": {
            "scotgov.high_value_band_estimate": "Band I and J estimate",
            "council_tax_band": "Council tax band",
            "statistic": "Statistic",
        },
        "dimension_value_labels": {
            "council_tax_band": {"I": "Band I", "J": "Band J"},
            "statistic": {
                "low_estimate": "Low estimate",
                "high_estimate": "High estimate",
            },
        },
        "artifact": {
            "source_name": "scotgov",
            "source_table": f"{TITLE}, Figures 2 and 3",
            "resource_package": "db",
            "resource_directory": f"data/{DIRECTORY}",
            "manifest": "manifest.yaml",
            "vintage": "high_value_bands_consultation_2026_07_06",
            "extracted_at": EXTRACTED_AT,
            "extraction_method": f"PDF text numbers ({entry['filename']})",
            "parser": "pdf_text_numbers",
            "artifact_year": 2026,
        },
        "record_sets": record_sets,
    }
    header = f"""
    Scottish Government, '{TITLE}' (published 6 July 2026, closed 24 August 2026,
    {PAGE}), Figures 2 and 3 on page 9 of the consultation paper, for {ISSUE} item 13
    (PolicyEngine/uk-scottish-budget-2027-28#5; PolicyEngine/microcosm#1112), asked in
    PolicyEngine/chronicle#435. Written by {SCRIPT} from the pinned PDF.

    Ported, at Scotland, as the published low and high estimates: the number of properties
    in the proposed Band I (more than £1 million and up to £2 million) and Band J (more
    than £2 million) at 1 April 2026 values, {counts[("I", "low_estimate")]:,} to
    {counts[("I", "high_estimate")]:,} and {counts[("J", "low_estimate")]:,} to
    {
        counts[
            ("J", "high_estimate")
        ]:,} (Figure 3); and the additional annual revenue, compared to the
    average Band H charge, at the paper's illustrative multipliers on 2026-27 Band D
    charges, £{millions[("I", "low_estimate")]}m to £{
        millions[("I", "high_estimate")]
    }m and £{millions[("J", "low_estimate")]}m to £{
        millions[("J", "high_estimate")]
    }m (Figure 2, '£ millions',
    scaled to pounds). Band is council_tax_band I or J and the bound is statistic
    low_estimate or high_estimate, filters on the two estimate concepts. The facts are
    model_output estimates: the paper calls its rates illustrative, and the figures'
    source reads '{SOURCE}'.

    Reading the labels: the charts print their data labels series by series, the low
    estimates for Band I and Band J and then the high estimates, as their legends order
    them. The generator asserts that order against the paper's own text: each band's high
    estimate exceeds its low, Band I exceeds Band J, the property ranges bracket
    'approximately 15,000 properties in total', and the revenue ranges sum to the 'between
    £12 million and £16 million per year' the paper states.

    What the revenue is measured against: 'compared to the average Band H charge', Band I
    properties 'would pay around £720 more per year' and Band J properties 'around £3,600
    more per year'. Each revenue label is its property label times that increase, to the
    £0.01m the chart prints (the generator asserts it), so the figures apply the full
    increase over the average Band H charge to every estimated property.

    The item's other part, Registers of Scotland's residential sales over £1 million, is
    the package ros-property-market-report-2025-26. RoS publishes no split above £2
    million. 8 facts.
    """
    return render(header, payload)


BUILDERS = {DIRECTORY: build}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the generated YAML with the committed file instead of writing.",
    )
    args = parser.parse_args()
    stale = []
    for directory, build_package in BUILDERS.items():
        text = build_package()
        path = PACKAGES / directory / "source_package.yaml"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(directory)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    for directory in stale:
        print(f"stale: packages/{directory}/source_package.yaml")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
