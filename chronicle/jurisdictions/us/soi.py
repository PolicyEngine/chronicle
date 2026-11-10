"""IRS SOI fact builders for Chronicle."""

from __future__ import annotations

from importlib.resources import files

from chronicle.core import (
    Aggregation,
    AggregateConstraint,
    EntityDimension,
    GeographyDimension,
    Measure,
    PeriodDimension,
    SourceProvenance,
    AggregateFact,
)
from chronicle.source_package import load_source_package
from chronicle.sources.cells import SourceCell
from chronicle.sources.specs import (
    CellSelectorSpec,
    SourceRecord,
    SourceRegionSpec,
    SourceRecordSetSpec,
    SourceRecordSpec,
)
from chronicle.yaml_io import safe_load as safe_load_yaml
from db.etl_soi import AGI_BRACKETS, TABLE_1_1_AGI_LABEL_TO_BRACKET

SOI_TABLE_1_1_SOURCE_NAME = "irs_soi"
SOI_TABLE_1_1_SOURCE_TABLE = "Publication 1304 Table 1.1"
SOI_TABLE_1_4_SOURCE_TABLE = "Publication 1304 Table 1.4"
SOI_TABLE_1_1_EXTRACTION_DATE = "2026-05-04"
SOI_TABLE_1_1_PACKAGE_DIR = "data/irs_soi/table_1_1"
SOI_TABLE_1_4_PACKAGE_DIR = "data/irs_soi/table_1_4"
SOI_TABLE_1_1_MANIFEST = "manifest.yaml"
SOI_TABLE_1_4_MANIFEST = "manifest.yaml"
AXIOM_IRC_AGI_CONCEPT = "us:statutes/26/62#adjusted_gross_income"
IRS_SOI_AGI_SOURCE_CONCEPT = "irs_soi.adjusted_gross_income"
IRS_SOI_TOTAL_WAGES_SOURCE_CONCEPT = "irs_soi.total_wages"
IRS_SOI_TOTAL_WAGES_RETURNS_SOURCE_CONCEPT = "irs_soi.returns_with_total_wages"
AGI_CONCEPT_EVIDENCE_URL = (
    "https://uscode.house.gov/view.xhtml?req=(title:26%20section:62%20edition:prelim)"
)
AGI_CONCEPT_EVIDENCE_NOTES = (
    "IRS SOI Table 1.1 reports adjusted gross income for individual income tax "
    "returns; IRC section 62 defines adjusted gross income. This Chronicle assertion "
    "treats the SOI AGI column as exactly adopting that legal concept for the "
    "tax-year source record."
)


def build_soi_table_1_1_facts(year: int = 2023) -> list[AggregateFact]:
    """Build source-lineaged Chronicle facts from SOI Table 1.1."""
    return load_source_package("soi-table-1-1").build_facts(year)


def build_soi_table_1_4_facts(year: int = 2023) -> list[AggregateFact]:
    """Build source-lineaged Chronicle facts from SOI Table 1.4."""
    return load_source_package("soi-table-1-4").build_facts(year)


def build_soi_table_1_1_source_cells(year: int = 2023) -> list[SourceCell]:
    """Build whole-workbook source cells from SOI Table 1.1."""
    return load_source_package("soi-table-1-1").build_source_cells(year)


def build_soi_table_1_4_source_cells(year: int = 2023) -> list[SourceCell]:
    """Build whole-workbook source cells from SOI Table 1.4."""
    return load_source_package("soi-table-1-4").build_source_cells(year)


def build_soi_table_1_1_source_records(
    year: int = 2023,
    *,
    cells: list[SourceCell] | None = None,
) -> list[SourceRecord]:
    """Resolve SOI Table 1.1 source records from cell selector specs."""
    return load_source_package("soi-table-1-1").build_source_records(
        year,
        cells=cells,
    )


def build_soi_table_1_4_source_records(
    year: int = 2023,
    *,
    cells: list[SourceCell] | None = None,
) -> list[SourceRecord]:
    """Resolve SOI Table 1.4 source records from cell selector specs."""
    return load_source_package("soi-table-1-4").build_source_records(
        year,
        cells=cells,
    )


def build_soi_table_1_1_source_record_specs(
    year: int = 2023,
) -> list[SourceRecordSpec]:
    """Build atomic source-record specs from a compact Table 1.1 set spec."""
    return load_source_package("soi-table-1-1").build_source_record_specs(year)


def build_soi_table_1_4_source_record_specs(
    year: int = 2023,
) -> list[SourceRecordSpec]:
    """Build atomic source-record specs from a compact Table 1.4 set spec."""
    return load_source_package("soi-table-1-4").build_source_record_specs(year)


def build_soi_table_1_1_source_region_specs(
    year: int = 2023,
) -> list[SourceRegionSpec]:
    """Build source-region specs for selected SOI Table 1.1 cells."""
    return load_source_package("soi-table-1-1").build_source_regions(year)


def build_soi_table_1_4_source_region_specs(
    year: int = 2023,
) -> list[SourceRegionSpec]:
    """Build source-region specs for selected SOI Table 1.4 cells."""
    return load_source_package("soi-table-1-4").build_source_regions(year)


def build_soi_table_1_1_source_record_set_spec(
    year: int = 2023,
) -> SourceRecordSetSpec:
    """Build compact row-by-measure authoring spec for SOI Table 1.1."""
    return load_source_package("soi-table-1-1").build_source_record_set_specs(year)[0]


def build_soi_table_1_4_source_record_set_spec(
    year: int = 2023,
) -> SourceRecordSetSpec:
    """Build compact row-by-measure authoring spec for Table 1.4 wages."""
    return load_source_package("soi-table-1-4").build_source_record_set_specs(year)[0]


def _legacy_soi_table_1_1_source_record_specs(
    year: int = 2023,
) -> list[SourceRecordSpec]:
    """Build the pre-record-set SOI specs for compiler parity tests."""
    rows: list[tuple[str, int, str, dict[str, str | int]]] = [
        ("all", 10, "All returns", _all_returns_filters())
    ]
    for index, (source_label, bracket_name) in enumerate(
        TABLE_1_1_AGI_LABEL_TO_BRACKET.items(),
        start=11,
    ):
        lower, upper = AGI_BRACKETS[bracket_name]
        rows.append(
            (
                bracket_name,
                index,
                source_label,
                _agi_bracket_filters(bracket_name, lower, upper),
            )
        )

    specs = []
    for range_id, row_number, row_label, filters in rows:
        specs.extend(
            [
                _legacy_source_record_spec(
                    year=year,
                    range_id=range_id,
                    row_number=row_number,
                    row_label=row_label,
                    column="B",
                    measure_id="return_count",
                    concept="irs_soi.individual_income_tax_returns",
                    unit="count",
                    aggregation="sum",
                    filters=filters,
                ),
                _legacy_source_record_spec(
                    year=year,
                    range_id=range_id,
                    row_number=row_number,
                    row_label=row_label,
                    column="D",
                    measure_id="adjusted_gross_income",
                    concept=AXIOM_IRC_AGI_CONCEPT,
                    unit="usd",
                    aggregation="sum",
                    filters=filters,
                    source_concept=IRS_SOI_AGI_SOURCE_CONCEPT,
                    concept_relation="exact",
                    concept_authority="ledger-us",
                    concept_evidence_url=AGI_CONCEPT_EVIDENCE_URL,
                    concept_evidence_notes=AGI_CONCEPT_EVIDENCE_NOTES,
                    legal_vintage=f"tax_year_{year}",
                    value_scale=1_000,
                ),
                _legacy_source_record_spec(
                    year=year,
                    range_id=range_id,
                    row_number=row_number,
                    row_label=row_label,
                    column="Q",
                    measure_id="total_income_tax",
                    concept="irs_soi.total_income_tax",
                    unit="usd",
                    aggregation="sum",
                    filters=filters,
                    value_scale=1_000,
                ),
                _legacy_source_record_spec(
                    year=year,
                    range_id=range_id,
                    row_number=row_number,
                    row_label=row_label,
                    column="N",
                    measure_id="income_tax_after_credits_returns",
                    concept="irs_soi.returns_with_income_tax_after_credits",
                    unit="count",
                    aggregation="sum",
                    filters=filters,
                ),
            ]
        )
    return specs


def _fact_from_source_record(
    record: SourceRecord,
    source: SourceProvenance,
) -> AggregateFact:
    spec = record.spec
    return AggregateFact(
        value=record.value,
        period=PeriodDimension(type=spec.period_type, value=spec.period),
        geography=GeographyDimension(
            level=spec.geography_level,
            id=spec.geography_id,
            vintage=spec.geography_vintage,
            name=spec.geography_name,
        ),
        entity=EntityDimension(name=spec.entity, role=spec.entity_role),
        measure=Measure(
            concept=spec.concept,
            unit=spec.unit,
            source_concept=spec.source_concept,
            concept_relation=spec.concept_relation,
            concept_authority=spec.concept_authority,
            concept_evidence_url=spec.concept_evidence_url,
            concept_evidence_notes=spec.concept_evidence_notes,
            legal_vintage=spec.legal_vintage,
        ),
        aggregation=Aggregation(method=spec.aggregation),
        source=source,
        provenance_class=spec.provenance_class,
        survey_instrument=spec.survey_instrument,
        filters=spec.filters,
        domain=spec.domain,
        source_record_id=record.source_record_id,
        source_cell_keys=record.source_cell_keys,
        source_row_keys=record.source_row_keys,
        constraints=spec.constraints,
        layout=spec.layout,
    )


def _legacy_source_record_spec(
    *,
    year: int,
    range_id: str,
    row_number: int,
    row_label: str,
    column: str,
    measure_id: str,
    concept: str,
    unit: str,
    aggregation: str,
    filters: dict[str, str | int],
    source_concept: str | None = None,
    concept_relation: str | None = None,
    concept_authority: str | None = None,
    concept_evidence_url: str | None = None,
    concept_evidence_notes: str | None = None,
    legal_vintage: str | None = None,
    value_scale: int = 1,
) -> SourceRecordSpec:
    source_record_id = f"irs_soi.ty{year}.table_1_1.{range_id}.{measure_id}"
    return SourceRecordSpec(
        source_record_id=source_record_id,
        selector=CellSelectorSpec(
            selector_id=f"{source_record_id}.selector",
            sheet_name="TBL11",
            address=f"{column}{row_number}",
            expected_cell_type="number",
            expected_row_header_address=f"A{row_number}",
            expected_row_header=row_label,
        ),
        concept=concept,
        unit=unit,
        period_type="tax_year",
        period=year,
        geography_id="0100000US",
        geography_level="country",
        geography_name="United States",
        geography_vintage="2020_census",
        entity="tax_unit",
        entity_role="filing_unit",
        aggregation=aggregation,
        provenance_class="administrative",
        filters=filters,
        constraints=_constraints_from_filters(filters),
        domain="all_individual_income_tax_returns",
        value_scale=value_scale,
        source_concept=source_concept,
        concept_relation=concept_relation,
        concept_authority=concept_authority,
        concept_evidence_url=concept_evidence_url,
        concept_evidence_notes=concept_evidence_notes,
        legal_vintage=legal_vintage,
    )


def _source_provenance_from_cells(cells: list[SourceCell]) -> SourceProvenance:
    artifact = cells[0].artifact
    return SourceProvenance(
        source_name=artifact.source_name,
        source_table=artifact.source_table,
        source_file=artifact.source_file,
        url=artifact.url,
        vintage=artifact.vintage,
        extracted_at=artifact.extracted_at,
        extraction_method="CellSelectorSpec and SourceRecordSpec resolved from cells",
        method_notes=(
            "Each fact carries source_record_id, source_cell_keys, and "
            "source_row_keys when available."
        ),
        source_sha256=artifact.sha256,
        source_size_bytes=artifact.size_bytes,
        raw_r2_bucket=artifact.raw_r2_bucket,
        raw_r2_key=artifact.raw_r2_key,
        raw_r2_uri=artifact.raw_r2_uri,
    )


def _all_returns_filters() -> dict[str, str]:
    return {"filing_status": "all", "income_range": "all"}


def _agi_bracket_filters(
    bracket_name: str,
    lower: float,
    upper: float,
) -> dict[str, str | int]:
    filters: dict[str, str | int] = {
        "filing_status": "all",
        "income_range": bracket_name,
    }
    if lower != float("-inf"):
        filters["agi_lower_usd"] = int(lower)
    if upper != float("inf"):
        filters["agi_upper_usd"] = int(upper)
    return filters


def _constraints_from_filters(
    filters: dict[str, str | int],
) -> tuple[AggregateConstraint, ...]:
    constraints: list[AggregateConstraint] = []
    lower = filters.get("agi_lower_usd")
    upper = filters.get("agi_upper_usd")
    if lower is not None:
        constraints.append(
            AggregateConstraint(
                variable=AXIOM_IRC_AGI_CONCEPT,
                operator=">=",
                value=lower,
                unit="usd",
                label="Adjusted gross income lower bound",
            )
        )
    if upper is not None:
        constraints.append(
            AggregateConstraint(
                variable=AXIOM_IRC_AGI_CONCEPT,
                operator="<",
                value=upper,
                unit="usd",
                label="Adjusted gross income upper bound",
            )
        )
    return tuple(constraints)


def _table_1_1_source_artifact(year: int) -> tuple[bytes, str, str]:
    spec = _source_file_spec(year, SOI_TABLE_1_1_PACKAGE_DIR, SOI_TABLE_1_1_MANIFEST)
    filename = spec["filename"]
    path = files("db").joinpath(SOI_TABLE_1_1_PACKAGE_DIR, filename)
    return path.read_bytes(), filename, spec["source_url"]


def _table_1_4_source_artifact(year: int) -> tuple[bytes, str, str]:
    spec = _source_file_spec(year, SOI_TABLE_1_4_PACKAGE_DIR, SOI_TABLE_1_4_MANIFEST)
    filename = spec["filename"]
    path = files("db").joinpath(SOI_TABLE_1_4_PACKAGE_DIR, filename)
    return path.read_bytes(), filename, spec["source_url"]


def _source_file_spec(
    year: int,
    package_dir: str,
    manifest_name: str,
) -> dict[str, str]:
    manifest_path = files("db").joinpath(
        package_dir,
        manifest_name,
    )
    with manifest_path.open("r", encoding="utf-8") as file:
        manifest = safe_load_yaml(file)
    files_by_year = manifest["files"]
    return files_by_year.get(year) or files_by_year[str(year)]
