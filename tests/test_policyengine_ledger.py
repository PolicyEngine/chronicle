"""Invariants for the checked-in PolicyEngine Ledger observation facts.

The old version of this file hard-coded a closed inventory of 49
source_record_ids, went stale at the first append, and was dropped from CI.
These tests assert the properties that must hold at ANY row count instead:
the frozen prefix is immutable, every row is a valid publisher fact, and
duplicate identities only exist as explicit supersede corrections.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from arch.core import (
    AggregateFact,
    Aggregation,
    EntityDimension,
    GeographyDimension,
    Measure,
    PeriodDimension,
    SourceProvenance,
    validate_facts,
)
from arch.store import fact_from_mapping, fact_to_mapping

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "ledger" / "official_observations.jsonl"
PREFIX_PATH = ROOT / "ledger" / "immutable_prefix.json"

sys.path.insert(0, str(ROOT / "scripts"))

from check_thesis_facts_append import (  # noqa: E402
    check_rows,
    effective_current_rows,
    expected_assertion_version_id,
)


# What each scaled unit measures, and the power of ten one of it holds. Thesis's
# scripts/ledger_units.py writes rows from the same table.
BASE_UNITS = {
    "thousands": ("count", 3),
    "millions": ("count", 6),
    "usd_millions": ("usd", 6),
    "usd_billions": ("usd", 9),
    "billions USD": ("usd", 9),
    "gbp_billions": ("gbp", 9),
    "million_cubic_feet": ("cubic_feet", 6),
}


def _prefix_manifest() -> dict:
    return json.loads(PREFIX_PATH.read_text(encoding="utf-8"))


def _read_lines() -> list[str]:
    return [
        line
        for line in LEDGER_PATH.read_text(encoding="utf-8").split("\n")
        if line.strip()
    ]


def _read_ledger_facts() -> list[dict]:
    return [json.loads(line) for line in _read_lines()]


LEDGER_ROW_KEYS = {
    "label",
    "observed_at",
    "source_record_id",
    "source_cell_keys",
    "source_row_keys",
    # Resolution provenance attached by the Thesis resolver.
    "ledgerRepoSha",
    "sourceVintage",
    "retrievedAt",
    "responseArchive",
    "targetContentHash",
    "sourceBindingProjection",
    "assertionVersion",
}


def _to_aggregate_fact(row: dict) -> AggregateFact:
    return AggregateFact(
        value=row["value"],
        period=PeriodDimension(**row["period"]),
        geography=GeographyDimension(**row["geography"]),
        entity=EntityDimension(**row["entity"]),
        measure=Measure(**row["measure"]),
        aggregation=Aggregation(**row["aggregation"]),
        source=SourceProvenance(**row["source"]),
        filters=row.get("filters", {}),
        domain=row.get("domain", "all"),
        label=row.get("label"),
        source_record_id=row.get("source_record_id"),
        source_cell_keys=tuple(row.get("source_cell_keys", ())),
        source_row_keys=tuple(row.get("source_row_keys", ())),
    )


def test_immutable_prefix_is_intact():
    # The manifest records a digest per frozen line and one over the frozen
    # region as a whole. Both are recomputed here from the ledger as it stands,
    # so a rewritten frozen line fails whichever of the two it moved.
    manifest = _prefix_manifest()
    count = int(manifest["prefixLineCount"])
    lines = _read_lines()

    assert count >= 128
    assert len(lines) >= count
    assert [
        hashlib.sha256(line.encode("utf-8")).hexdigest() for line in lines[:count]
    ] == manifest["lineSha256s"]
    assert (
        hashlib.sha256(("\n".join(lines[:count]) + "\n").encode("utf-8")).hexdigest()
        == manifest["prefixSha256"]
    )


def test_every_row_satisfies_the_append_invariants():
    lines = _read_lines()

    # Raises on any malformed row, unexplained duplicate identity,
    # mis-addressed assertion version, or missing post-prefix binding.
    check_rows(lines, int(_prefix_manifest()["prefixLineCount"]))


def test_official_observation_ledger_contains_facts_not_predictions():
    for row in _read_ledger_facts():
        assert "prediction" not in json.dumps(row).lower()
        assert "forecast" not in json.dumps(row).lower()
        assert row["source_record_id"]
        assert row["source"]["url"].startswith("https://")
        assert row["source"]["vintage"]


def test_official_observations_validate_as_aggregate_facts():
    # ``validate_facts`` rejects two rows sharing a semantic aggregate key, so
    # the journal is validated as its supersede-aware effective current view
    # (latest non-superseded row per identity) rather than as raw duplicates.
    current = effective_current_rows(_read_ledger_facts())
    facts = [_to_aggregate_fact(row) for row in current]

    report = validate_facts(facts)

    assert report.valid, report.to_dict()
    assert report.counts["missing_lineage"]["count"] == 0


def test_rows_carry_no_unknown_top_level_fields():
    known = set(AggregateFact.__dataclass_fields__) | LEDGER_ROW_KEYS
    for number, row in enumerate(_read_ledger_facts(), start=1):
        unknown = set(row) - known
        assert not unknown, f"line {number} has unknown fields: {sorted(unknown)}"


def _moved_by_power_of_ten(recorded: int | float, power: int) -> Decimal:
    """The recorded value in base units, with no rounding at any length."""
    sign, digits, exponent = Decimal(repr(recorded)).as_tuple()
    return Decimal((sign, digits, exponent + power))


def _recorded_pair_problems(rows: list[dict]) -> list[str]:
    """Rows whose recorded pair does not state the value they store, exactly."""
    problems = []
    for number, row in enumerate(rows, start=1):
        source = row["source"]
        if "recorded_value" not in source and "recorded_unit" not in source:
            continue
        unit = source.get("recorded_unit")
        recorded = source.get("recorded_value")
        if unit not in BASE_UNITS or not isinstance(recorded, (int, float)):
            problems.append(f"line {number} records {recorded!r} {unit!r}")
            continue
        base, power = BASE_UNITS[unit]
        if row["measure"]["unit"] != base:
            problems.append(f"line {number} stores {row['measure']['unit']!r}, not {base!r}")
        elif Decimal(repr(row["value"])) != _moved_by_power_of_ten(recorded, power):
            problems.append(f"line {number} stores {row['value']!r}, not {recorded!r} {unit}")
    return problems


def _unit_restatement_problems(rows: list[dict]) -> list[str]:
    """Restatements that do not repeat the recorded pair of the row they name."""
    problems = []
    by_id: dict[str, dict] = {}
    for number, row in enumerate(rows, start=1):
        version = row.get("assertionVersion") or {}
        if version.get("relation") == "unit_restatement":
            prior = by_id.get(version.get("supersedes"))
            if prior is None:
                problems.append(f"line {number} restates a row no earlier line holds")
            elif prior["measure"]["unit"] not in BASE_UNITS:
                problems.append(f"line {number} restates a row with no scale word")
            elif (row["source"].get("recorded_value"), row["source"].get("recorded_unit")) != (
                prior["value"],
                prior["measure"]["unit"],
            ):
                problems.append(f"line {number} changes what the row it restates says")
        elif "relation" in version:
            problems.append(f"line {number} has relation {version['relation']!r}")
        by_id[version.get("id") or expected_assertion_version_id(row)] = row
    return problems


def test_recorded_pairs_state_the_stored_values():
    rows = _read_ledger_facts()
    assert _recorded_pair_problems(rows) == []
    assert _unit_restatement_problems(rows) == []


def _scaled_row() -> dict:
    return {
        "value": 7.716,
        "measure": {"unit": "millions"},
        "source": {},
        "assertionVersion": {"id": "av2:prior", "supersedes": None},
    }


def _restatement(**changes) -> dict:
    return {
        "value": 7716000,
        "measure": {"unit": "count"},
        "source": {"recorded_value": 7.716, "recorded_unit": "millions"},
        "assertionVersion": {
            "id": "av2:restated",
            "supersedes": "av2:prior",
            "relation": "unit_restatement",
        },
        **changes,
    }


def test_a_sound_restatement_passes_both_checks():
    rows = [_scaled_row(), _restatement()]
    assert _recorded_pair_problems(rows) == []
    assert _unit_restatement_problems(rows) == []


def test_recorded_pair_checks_refuse_a_changed_quantity():
    for changes, problem in (
        ({"value": 7716001}, "stores 7716001"),
        ({"measure": {"unit": "usd"}}, "stores 'usd'"),
        (
            {"source": {"recorded_value": 7.716, "recorded_unit": "thousands"}},
            "stores 7716000, not 7.716 thousands",
        ),
        ({"source": {"recorded_value": 7.716}}, "records 7.716 None"),
        ({"source": {"recorded_value": "7.716", "recorded_unit": "millions"}}, "records '7.716'"),
    ):
        problems = _recorded_pair_problems([_restatement(**changes)])
        assert len(problems) == 1 and problem in problems[0]


def test_recorded_pair_checks_hold_past_decimal_precision():
    # 29 significant digits, one more than Decimal's default context keeps.
    source = {"recorded_value": 10**28 + 1, "recorded_unit": "millions"}
    assert _recorded_pair_problems([_restatement(value=10**34 + 10**6, source=source)]) == []
    rounded = _recorded_pair_problems([_restatement(value=10**34, source=source)])
    assert len(rounded) == 1 and "stores" in rounded[0]


def test_restatement_checks_refuse_a_row_that_changes_the_prior_pair():
    changed = _restatement(
        value=7717000,
        source={"recorded_value": 7.717, "recorded_unit": "millions"},
    )
    assert _recorded_pair_problems([_scaled_row(), changed]) == []
    assert "changes what the row" in _unit_restatement_problems([_scaled_row(), changed])[0]


def test_restatement_checks_refuse_a_row_with_no_scaled_prior():
    plain = {**_scaled_row(), "measure": {"unit": "percent"}}
    assert "no scale word" in _unit_restatement_problems([plain, _restatement()])[0]
    assert "no earlier line" in _unit_restatement_problems([_restatement()])[0]


def test_restatement_checks_refuse_an_unknown_relation():
    other = _restatement(
        assertionVersion={"id": "av2:x", "supersedes": None, "relation": "other"}
    )
    assert "relation 'other'" in _unit_restatement_problems([other])[0]


def test_a_recorded_pair_survives_the_fact_store():
    row = _read_ledger_facts()[0]
    plain = _to_aggregate_fact(row)
    assert "recorded_value" not in fact_to_mapping(plain)["source"]
    assert "recorded_unit" not in fact_to_mapping(plain)["source"]
    assert fact_from_mapping(fact_to_mapping(plain)) == plain

    source = {**row["source"], "recorded_value": 7.716, "recorded_unit": "millions"}
    paired = _to_aggregate_fact({**row, "source": source})
    assert fact_to_mapping(paired)["source"]["recorded_value"] == 7.716
    assert fact_from_mapping(fact_to_mapping(paired)) == paired


def _git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_a_rewritten_prefix_line_is_detected(tmp_path):
    lines = _read_lines()
    row = json.loads(lines[0])
    row["value"] = 999999
    tampered = [json.dumps(row, separators=(",", ":")), *lines[1:]]
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    (ledger_dir / "official_observations.jsonl").write_text("\n".join(tampered) + "\n")
    (ledger_dir / "immutable_prefix.json").write_text(PREFIX_PATH.read_text())
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    for name in (
        "check_thesis_facts_append.py",
        "canonical_json.py",
        "verify_release_chain.py",
    ):
        (scripts_dir / name).write_text((ROOT / "scripts" / name).read_text())

    # The checker judges a commit it checks out itself, so the tampering has to
    # be committed before it can be asked about.
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Ledger Invariants Test")
    _git(tmp_path, "config", "user.email", "ledger-invariants@example.invalid")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "tampered prefix")

    completed = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "check_thesis_facts_append.py"),
            "--commit",
            _git(tmp_path, "rev-parse", "HEAD"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "was rewritten" in completed.stderr


def _appended_row(original: dict, *, value_delta: float = 0) -> dict:
    row = {
        **original,
        "value": original["value"] + value_delta,
        "retrievedAt": "2026-07-11T00:00:00Z",
        "sourceVintage": "2026-07-11",
        "ledgerRepoSha": "a" * 40,
        "responseArchive": {"sha256": "b" * 64, "contentEncoding": "gzip"},
    }
    row.pop("targetContentHash", None)
    row.pop("sourceBindingProjection", None)
    return row


def test_a_duplicate_identity_without_supersedes_is_detected():
    lines = _read_lines()
    duplicate = _appended_row(json.loads(lines[-1]))
    duplicate["assertionVersion"] = {
        "id": expected_assertion_version_id(duplicate),
        "supersedes": None,
    }
    try:
        check_rows([*lines, json.dumps(duplicate, separators=(",", ":"))], len(lines))
    except ValueError as error:
        assert "without superseding" in str(error)
    else:
        raise AssertionError("duplicate identity was accepted silently")


def test_an_explicit_supersede_correction_is_accepted():
    # A correction supersedes the row's recomputable content address.
    lines = _read_lines()
    original = json.loads(lines[-1])
    correction = _appended_row(original, value_delta=1)
    correction["assertionVersion"] = {
        "id": expected_assertion_version_id(correction),
        "supersedes": expected_assertion_version_id(original),
    }

    check_rows([*lines, json.dumps(correction, separators=(",", ":"))], len(lines))


def test_a_correction_naming_a_stale_version_is_rejected():
    lines = _read_lines()
    original = json.loads(lines[-1])
    correction = _appended_row(original, value_delta=1)
    correction["assertionVersion"] = {
        "id": expected_assertion_version_id(correction),
        "supersedes": "av2:" + "0" * 64,
    }
    try:
        check_rows([*lines, json.dumps(correction, separators=(",", ":"))], len(lines))
    except ValueError as error:
        assert "the active version" in str(error)
    else:
        raise AssertionError("stale supersedes target was accepted")
