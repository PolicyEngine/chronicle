"""Chronicle source lineage helpers."""

__all__ = [
    "CellSelectorSpec",
    "SourceArtifactMetadata",
    "SourceArtifact",
    "SourceCell",
    "SourceCellIssue",
    "SourceCellReport",
    "SourceColumn",
    "SourceFile",
    "SourceRecord",
    "SourceRecordSetMeasure",
    "SourceRecordSetRow",
    "SourceRecordSetSpec",
    "SourceRecordSpec",
    "SourceReference",
    "SourceRegionSpec",
    "SourceRow",
    "SourceTable",
    "build_source_cell_key",
    "compile_source_record_set_specs",
    "load_source_cells_jsonl",
    "resolve_cell_selector",
    "resolve_source_record",
    "save_source_cells_jsonl",
    "source_cells_from_delimited_text",
    "source_cells_from_html_tables_and_text",
    "source_cells_from_ods",
    "source_cells_from_xls",
    "source_cells_from_xlsx",
    "source_regions_from_record_set_spec",
    "validate_source_cells",
]


def __getattr__(name: str):
    """Load legacy source helpers only when they are explicitly requested."""
    if name not in __all__:
        raise AttributeError(name)
    from chronicle import sources

    return getattr(sources, name)
