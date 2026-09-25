"""Publisher-labelled US facts must survive the consumer-artifact boundary (#277)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from chronicle.bundle import build_bundle
from chronicle.consumer_contract import consumer_fact_row, write_consumer_facts_jsonl
from chronicle.source_package import load_source_package
from policyengine_chronicle.consumer import (
    build_consumer_artifact,
    load_consumer_artifact,
)
from policyengine_chronicle.schema import validate_consumer_fact_row


@pytest.mark.parametrize(
    "alias,year,authority,count,source_month",
    [
        ("cms-medicaid-chip-monthly-enrollment-dataset", 2026, "cms", 255, "2025-12"),
        (
            "cms-medicaid-chip-monthly-enrollment-december-2024",
            2026,
            "cms",
            260,
            "2024-12",
        ),
        ("census-b01001-female-age-2023", 2023, "census", 468, None),
        ("jct-tax-expenditures-2024", 2024, "jct", 11, None),
    ],
)
def test_source_label_facts_retain_publisher_authority_in_artifacts(
    tmp_path, alias, year, authority, count, source_month
):
    # These checked-in publisher fixtures cover the 994 rows reported in #277;
    # the two CMS packages select different months from the same source file.
    facts = load_source_package(alias).build_facts(year)
    assert len(facts) == count
    if source_month is not None:
        assert {(fact.period.type, fact.period.value) for fact in facts} == {
            ("month", source_month)
        }

    facts_path = tmp_path / "consumer_facts.jsonl"
    write_consumer_facts_jsonl(facts, facts_path)
    rows = [json.loads(line) for line in facts_path.read_text().splitlines()]
    for fact, row in zip(facts, rows, strict=True):
        assert fact.measure.concept_relation == "source_label"
        assert row["concept_alignment"]["authority"] == authority
        validate_consumer_fact_row(row, 1, facts_path)

        # Naming the publisher changes alignment identity, not the observation,
        # value, provenance or the aggregate/semantic source-fact identity.
        before = consumer_fact_row(
            replace(fact, measure=replace(fact.measure, concept_authority=None))
        )
        assert (
            before["concept_alignment"]["concept_alignment_key"]
            != (row["concept_alignment"]["concept_alignment_key"])
        )
        for field in (
            "value",
            "source",
            "lineage",
            "observed_measure",
            "aggregate_fact_key",
            "semantic_fact_key",
        ):
            assert row[field] == before[field]

    artifact_dir = tmp_path / "artifact"
    report = build_consumer_artifact(artifact_dir, facts_path=facts_path)
    assert report.fact_row_count == count
    assert list(load_consumer_artifact(artifact_dir).rows) == rows


def test_source_label_bundle_is_accepted_by_the_artifact_validator(tmp_path):
    # Exercise the shared suite -> bundle -> artifact path with the 11-row JCT
    # fixture, rather than running a whole-country bundle.
    bundle_dir = tmp_path / "bundle"
    report = build_bundle(bundle_dir, year=2024, sources=["jct-tax-expenditures-2024"])
    assert report.valid

    artifact_dir = tmp_path / "artifact"
    artifact_report = build_consumer_artifact(
        artifact_dir, facts_path=bundle_dir / "consumer_facts.jsonl"
    )
    assert artifact_report.fact_row_count == 11
    rows = load_consumer_artifact(artifact_dir).rows
    assert {row["concept_alignment"]["authority"] for row in rows} == {"jct"}


def test_source_label_authority_remains_required_by_artifact_schema(tmp_path):
    fact = load_source_package("jct-tax-expenditures-2024").build_facts(2024)[0]
    row = consumer_fact_row(fact)
    row["concept_alignment"].pop("authority", None)
    facts_path = tmp_path / "missing-authority.jsonl"
    facts_path.write_text(json.dumps(row) + "\n")

    with pytest.raises(ValueError, match="'authority' is a required property"):
        build_consumer_artifact(tmp_path / "artifact", facts_path=facts_path)
