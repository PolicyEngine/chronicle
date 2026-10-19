"""Regression tests for the series-catalog generator.

Sections mirror the adversarial reviews of the first two generators: the
token-grammar findings (live period spellings, identifiers that must never
be stripped), and the v2 identity findings (wholesale reminting invisible
to --check, cross-dimension alias inheritance, source labels treated as
identity, string-keyed UUID uniqueness, silent seed loss, mismatched
period tokens silently stripped).
"""

from __future__ import annotations

import datetime as dt
import doctest
import json
import pathlib
import sys
import tempfile
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_series_catalog as bsc  # noqa: E402

# The curated map of reviewed period strips (canonical concept -> identifier
# field -> strip shape -> spelling -> classify_segments kinds) that
# test_committed_catalog_is_current_and_valid audits the committed catalog
# against; its "comment" says how to extend it.
REVIEWED_STRIPPED_SEGMENTS_PATH = (
    ROOT / "tests" / "fixtures" / "series_catalog"
    / "reviewed_stripped_segments.json"
)
REVIEWED_STRIPPED_FIXTURE = json.loads(
    REVIEWED_STRIPPED_SEGMENTS_PATH.read_text(encoding="utf-8")
)
REVIEWED_STRIPS: dict[str, dict[str, dict[str, dict[str, list[str]]]]] = (
    REVIEWED_STRIPPED_FIXTURE["strips"]
)

PERIOD_SEGMENTS = [
    "fy2026",
    "2026-05",
    "2026_05",
    "2026-05-02",
    "2026_06_18",
    "may_2026",
    "feb_2026",
    "sept_2026",
    "q1_2026",
    "2026_q2",
    "week_2026-06-13",
    "week_2026_06_13",
    "week_ending_2026_06_06",
    "february_to_april_2026",
    "after_june_2026",
    "after_mpc_june_2026",
]

NON_PERIOD_SEGMENTS = [
    "36-10-0434-01",  # StatCan table id
    "g17",
    "adv44x72",
    "j5ii",
    "m3",
    "2026_13",  # date-shaped noise: no such month
    "2026-02-30",  # date-shaped noise: no such day
    "first_print",
    "third_estimate",
    "original_submission",
    "australia",
    "total_nonfarm_payroll_change",
]


@pytest.mark.parametrize("segment", PERIOD_SEGMENTS)
def test_period_segments_recognized(segment: str) -> None:
    assert bsc.is_period_segment(segment), segment


@pytest.mark.parametrize("segment", NON_PERIOD_SEGMENTS)
def test_non_period_segments_retained(segment: str) -> None:
    assert not bsc.is_period_segment(segment), segment


def test_abbreviated_months_index_correctly() -> None:
    # Generator v2 kept "sept" inside MONTHS_ABBREV, shifting the derived
    # abbreviations for October-December.
    variants = bsc.period_token_variants({"type": "month", "value": "2026-10"})
    assert "oct_2026" in variants and "october_2026" in variants
    variants = bsc.period_token_variants({"type": "month", "value": "2026-12"})
    assert "dec_2026" in variants


MONTH_2026_06 = {"type": "month", "value": "2026-06"}


def test_semantic_pass_strips_unseen_spelling() -> None:
    # A spelling derivable from the row period is the period.
    assert (
        bsc.family_pattern("agency.rate.june_2026", MONTH_2026_06)
        == "agency.rate.{P}"
    )


@pytest.mark.parametrize(
    ("identifier", "period", "expected"),
    [
        # Finer-grained tokens inside the row's declared period strip.
        (
            "dol.eta.initial_claims.sa.week_ending_2026_06_06",
            MONTH_2026_06,
            "dol.eta.initial_claims.sa.{P}",
        ),
        ("boe.bank_rate.2026-06-18", MONTH_2026_06, "boe.bank_rate.{P}"),
        (
            "boe.bank_rate.after_mpc_june_2026",
            MONTH_2026_06,
            "boe.bank_rate.{P}",
        ),
        # A month-range whose window covers the row period strips.
        (
            "ons.labour.unemployment_rate.february_to_april_2026",
            {"type": "month", "value": "2026-04"},
            "ons.labour.unemployment_rate.{P}",
        ),
        (
            "bls.eci.private_wages_salaries_qoq.2026_q2.first_print",
            {"type": "quarter", "value": "2026-04"},
            "bls.eci.private_wages_salaries_qoq.{P}.first_print",
        ),
        ("fns.snap.rate.fy2024", {"type": "fiscal_year", "value": 2024},
         "fns.snap.rate.{P}"),
    ],
)
def test_tokens_matching_row_period_strip(identifier, period, expected) -> None:
    assert bsc.family_pattern(identifier, period) == expected


@pytest.mark.parametrize(
    ("identifier", "period"),
    [
        # Disjoint from the row period: a real date, but not THIS row's.
        ("agency.rate.2025_12", MONTH_2026_06),
        ("agency.rate.week_ending_2026_01_03", MONTH_2026_06),
        ("fns.snap.rate.fy2023", {"type": "fiscal_year", "value": 2024}),
    ],
)
def test_mismatched_tokens_flagged_not_stripped(identifier, period) -> None:
    pattern = bsc.family_pattern(identifier, period)
    assert pattern == identifier  # kept in the identity
    assert bsc.suspect_segments(pattern) == [identifier.rsplit(".", 1)[1]]


def test_suspect_segments_flag_but_never_strip() -> None:
    pattern = bsc.family_pattern("agency.series.mid2026wave")
    assert pattern == "agency.series.mid2026wave"
    assert bsc.suspect_segments(pattern) == ["mid2026wave"]


US = {"level": "country", "id": "0100000US", "vintage": "current",
      "name": "United States"}
CALIFORNIA = {"level": "state", "id": "0400000US06", "vintage": "current",
              "name": "California"}
BRITAIN = {"level": "country", "id": "GB", "vintage": "current", "name": None}


def _row(
    concept: str,
    *,
    rid: str | None = None,
    unit: str = "percent",
    period: dict | None = None,
    geography: dict | None = None,
    entity: dict | None = None,
    source_concept: str | None = None,
) -> dict:
    period = period or {"type": "month", "value": "2026-05"}
    return {
        "value": 1.0,
        "observed_at": "2026-06-01",
        "period": period,
        "geography": geography or dict(US),
        "entity": entity or {"name": "economy", "role": "aggregate"},
        "measure": {
            "concept": concept,
            "unit": unit,
            **({"source_concept": source_concept} if source_concept else {}),
        },
        "source": {"source_name": "test"},
        "source_record_id": rid or f"{concept}.first_print",
    }


def _registry(tmp_path: pathlib.Path, entries: list[dict] | None = None):
    path = tmp_path / "registry.jsonl"
    if not path.exists() or entries is not None:
        body = "".join(
            bsc.UuidRegistry.render_entry(e) + "\n" for e in (entries or [])
        )
        path.write_text(body, encoding="utf-8")
    return bsc.UuidRegistry.load(path)


def _build(
    tmp_path: pathlib.Path,
    rows: list[dict],
    existing: dict | None = None,
    registry_entries: list[dict] | None = None,
    docket: dict | None = None,
):
    observations = tmp_path / "obs.jsonl"
    observations.write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    catalog_path = tmp_path / "catalog.json"
    if existing is not None:
        catalog_path.write_text(json.dumps(existing) + "\n", encoding="utf-8")
    docket_path = None
    if docket is not None:
        docket_path = tmp_path / "seed.json"
        docket_path.write_text(json.dumps(docket), encoding="utf-8")
    return bsc.build_catalog(
        observations,
        docket_path,
        bsc.ExistingCatalog(catalog_path),
        _registry(tmp_path, registry_entries),
    )


def test_geography_splits_identity(tmp_path: pathlib.Path) -> None:
    rows = [
        _row("fns.snap.error_rate"),
        _row("fns.snap.error_rate", geography=dict(CALIFORNIA)),
    ]
    catalog, plan = _build(tmp_path, rows)
    assert len(catalog["series"]) == 2
    ids = {(r["geography"] or {}).get("id") for r in catalog["series"]}
    assert ids == {"0100000US", "0400000US06"}
    assert len(plan["mints"]) == 2


def test_geography_vintage_splits_identity(tmp_path: pathlib.Path) -> None:
    v1 = {"level": "state", "id": "0400000US06", "vintage": "2020"}
    v2 = {"level": "state", "id": "0400000US06", "vintage": "2024"}
    rows = [
        _row("fns.snap.error_rate", geography=v1),
        _row("fns.snap.error_rate", geography=v2,
             period={"type": "month", "value": "2026-06"}),
    ]
    catalog, _ = _build(tmp_path, rows)
    assert len(catalog["series"]) == 2
    forward = [r["geography"]["vintage"] for r in catalog["series"]]
    catalog_reversed, _ = _build(tmp_path, list(reversed(rows)))
    assert forward == [
        r["geography"]["vintage"] for r in catalog_reversed["series"]
    ]
    assert sorted(forward) == ["2020", "2024"]


def test_cross_geography_name_match_never_inherits(
    tmp_path: pathlib.Path,
) -> None:
    # v2 repro: a prior US row plus a later California-only observation of
    # the same concept silently moved the US UUID to California.
    first, _ = _build(tmp_path, [_row("fns.snap.error_rate")])
    us_uuid = first["series"][0]["uuid"]
    later, plan = _build(
        tmp_path,
        [_row("fns.snap.error_rate", geography=dict(CALIFORNIA))],
        existing=first,
    )
    assert later["series"][0]["uuid"] != us_uuid
    # The US identity's UUID vanishing is loud, not silent.
    assert [key for key, _ in plan["dropped"]] == [
        (
            "fns.snap.error_rate",
            bsc._geo_key(US),
            bsc._entity_key({"name": "economy", "role": "aggregate"}),
        )
    ]


def test_new_geography_added_incrementally(tmp_path: pathlib.Path) -> None:
    # v2 failed this with an ambiguous global name match once a concept had
    # several prior geographies.
    states = [dict(CALIFORNIA), {"level": "state", "id": "0400000US36",
                                 "vintage": "current"}]
    rows = [_row("fns.snap.error_rate")] + [
        _row("fns.snap.error_rate", geography=g) for g in states
    ]
    first, first_plan = _build(tmp_path, rows)
    assert len(first["series"]) == 3
    added = rows + [
        _row(
            "fns.snap.error_rate",
            geography={"level": "state", "id": "0400000US48",
                       "vintage": "current"},
        )
    ]
    second, plan = _build(
        tmp_path, added, existing=first,
        registry_entries=first_plan["mints"],
    )
    assert len(second["series"]) == 4
    old = {r["uuid"] for r in first["series"]}
    assert old < {r["uuid"] for r in second["series"]}
    # Only the genuinely new geography mints; the registered three inherit.
    assert len(plan["mints"]) == 1 and not plan["dropped"]
    assert plan["mints"][0]["geography"]["id"] == "0400000US48"


def test_source_concept_never_drives_inheritance(
    tmp_path: pathlib.Path,
) -> None:
    # v2 repro: agency.rate_b with agency.rate_a's source label silently
    # became (or merged into) agency.rate_a.
    first, _ = _build(
        tmp_path, [_row("agency.rate_a", source_concept="OFFICIAL_SHARED")]
    )
    a_uuid = first["series"][0]["uuid"]
    assert first["series"][0]["aliases"] == []
    assert first["series"][0]["source_concepts"] == ["OFFICIAL_SHARED"]
    solo_b, _ = _build(
        tmp_path,
        [_row("agency.rate_b", source_concept="OFFICIAL_SHARED")],
        existing=first,
    )
    assert [r["concept"] for r in solo_b["series"]] == ["agency.rate_b"]
    assert solo_b["series"][0]["uuid"] != a_uuid
    both, _ = _build(
        tmp_path,
        [
            _row("agency.rate_a", source_concept="OFFICIAL_SHARED"),
            _row("agency.rate_b", source_concept="OFFICIAL_SHARED"),
        ],
        existing=first,
    )
    concepts = [r["concept"] for r in both["series"]]
    assert concepts == ["agency.rate_a", "agency.rate_b"]
    assert both["series"][0]["uuid"] == a_uuid
    assert both["series"][0]["observation_count"] == 1  # no silent merge


def test_curated_alias_inherits_within_dimensions(
    tmp_path: pathlib.Path,
) -> None:
    first, _ = _build(tmp_path, [_row("abs.cpi.all_groups.yoy")])
    row = first["series"][0]
    row["aliases"] = ["abs.cpi_indicator.allgroups.yoy"]
    merged, plan = _build(
        tmp_path,
        [_row("abs.cpi_indicator.allgroups.yoy")],
        existing=first,
    )
    assert merged["series"][0]["uuid"] == row["uuid"]
    assert merged["series"][0]["concept"] == "abs.cpi.all_groups.yoy"
    assert "abs.cpi_indicator.allgroups.yoy" in merged["series"][0]["aliases"]
    assert not plan["dropped"] and not plan["supersedes"]


def test_curated_alias_does_not_inherit_across_geography(
    tmp_path: pathlib.Path,
) -> None:
    first, _ = _build(tmp_path, [_row("boe.bank_rate")])
    first["series"][0]["aliases"] = ["bank_rate.official"]
    stolen, _ = _build(
        tmp_path,
        [_row("bank_rate.official", geography=dict(BRITAIN))],
        existing=first,
    )
    assert stolen["series"][0]["uuid"] != first["series"][0]["uuid"]


def test_ambiguous_alias_never_drives_inheritance(
    tmp_path: pathlib.Path,
) -> None:
    # A name held as an alias by two rows resolves to neither: the
    # incoming spelling mints fresh and the ambiguity stays surfaced.
    existing = {
        "series": [
            {
                "uuid": "11111111-1111-4111-8111-111111111111",
                "concept": "a.one",
                "geography": dict(US),
                "entity": {"name": "economy", "role": "aggregate"},
                "aliases": ["SHARED"],
            },
            {
                "uuid": "22222222-2222-4222-8222-222222222222",
                "concept": "a.two",
                "geography": dict(US),
                "entity": {"name": "economy", "role": "aggregate"},
                "aliases": ["SHARED"],
            },
        ]
    }
    # Without a competing spelling, the double alias simply stays
    # surfaced and resolves to nothing.
    catalog, _ = _build(
        tmp_path, [_row("a.one"), _row("a.two")], existing=existing
    )
    assert catalog["ambiguous_aliases"] == ["SHARED"]
    assert {r["uuid"] for r in catalog["series"]} == {
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
    }
    # An incoming observation SPELLED like the ambiguous name inherits
    # nothing; the resulting same-dimension canonical/alias collision is
    # the contradiction hard-error, never a silent theft.
    with pytest.raises(SystemExit, match="contradictory curation"):
        _build(
            tmp_path,
            [_row("a.one"), _row("a.two"), _row("SHARED")],
            existing=existing,
        )


def test_docket_placeholder_enrichment_keeps_uuid(
    tmp_path: pathlib.Path,
) -> None:
    placeholder_uuid = "33333333-3333-4333-8333-333333333333"
    existing = {
        "series": [
            {
                "uuid": placeholder_uuid,
                "concept": "census.m3.new_orders",
                "geography": {"level": "country", "id": "0100000US",
                              "name": "United States"},
                "entity": None,
                "aliases": [],
                "status": "docket-only",
            }
        ]
    }
    catalog, plan = _build(
        tmp_path, [_row("census.m3.new_orders")], existing=existing
    )
    assert len(catalog["series"]) == 1
    row = catalog["series"][0]
    assert row["uuid"] == placeholder_uuid
    assert row["status"] == "observed"
    assert row["entity"] == {"name": "economy", "role": "aggregate"}
    assert not plan["dropped"]  # lineage survives on the enriched identity


def test_docket_placeholder_never_enriches_across_country(
    tmp_path: pathlib.Path,
) -> None:
    existing = {
        "series": [
            {
                "uuid": "44444444-4444-4444-8444-444444444444",
                "concept": "labour.unemployment_rate",
                "geography": {"level": "country", "id": "0100000US",
                              "name": "United States"},
                "entity": None,
                "aliases": [],
                "status": "docket-only",
            }
        ]
    }
    catalog, _ = _build(
        tmp_path,
        [_row("labour.unemployment_rate", geography=dict(BRITAIN))],
        existing=existing,
    )
    observed = [r for r in catalog["series"] if r["status"] == "observed"]
    assert observed[0]["uuid"] != "44444444-4444-4444-8444-444444444444"


def test_unit_conflict_is_a_hard_error(tmp_path: pathlib.Path) -> None:
    rows = [
        _row("fed.rate", unit="percent"),
        _row(
            "fed.rate",
            unit="index_points",
            period={"type": "month", "value": "2026-06"},
        ),
    ]
    with pytest.raises(SystemExit, match="unit conflict"):
        _build(tmp_path, rows)


def test_uuid_validation_requires_canonical_and_parsed_uniqueness() -> None:
    base = "abcd1234-ab12-4ab1-8ab1-abcd1234abcd"
    catalog = {
        "series": [
            {"uuid": "not-a-uuid", "concept": "a"},
            {"uuid": base, "concept": "b"},
            {"uuid": base, "concept": "c"},
            {"uuid": base.upper(), "concept": "d"},
            {"uuid": base.replace("-", ""), "concept": "e"},
            {"uuid": "{" + base + "}", "concept": "f"},
        ]
    }
    problems = bsc.validate_uuids(catalog)
    assert any("does not parse" in p for p in problems)
    # Every non-canonical spelling is rejected AND still counted as the
    # same 128-bit value.
    assert sum("not canonical lowercase" in p for p in problems) == 3
    assert sum("same 128-bit value" in p for p in problems) == 4


def test_registry_chain_validation(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "registry.jsonl"
    mint = {"concept": "a.one", "geography": None, "entity": None,
            "uuid": "11111111-1111-4111-8111-111111111111"}
    rebind = {"concept": "a.one", "geography": None, "entity": None,
              "uuid": "22222222-2222-4222-8222-222222222222"}
    path.write_text(
        json.dumps(mint) + "\n" + json.dumps(rebind) + "\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="re-binds without supersedes"):
        bsc.UuidRegistry.load(path)
    chained = dict(rebind, supersedes=mint["uuid"], note="curated remint")
    path.write_text(
        json.dumps(mint) + "\n" + json.dumps(chained) + "\n", encoding="utf-8"
    )
    registry = bsc.UuidRegistry.load(path)
    key = ("a.one", bsc._geo_key(None), bsc._entity_key(None))
    assert registry.binding(key) == rebind["uuid"]
    wrong_chain = dict(
        rebind, supersedes="99999999-9999-4999-8999-999999999999", note="x"
    )
    path.write_text(
        json.dumps(mint) + "\n" + json.dumps(wrong_chain) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="prior binding is"):
        bsc.UuidRegistry.load(path)
    no_note = dict(rebind, supersedes=mint["uuid"])
    path.write_text(
        json.dumps(mint) + "\n" + json.dumps(no_note) + "\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="requires a substantive note"):
        bsc.UuidRegistry.load(path)


def test_registry_append_only_check() -> None:
    base = b'{"concept": "a", "uuid": "x"}\n'
    assert bsc.append_only_problem(base, base) is None
    assert bsc.append_only_problem(base, base + b'{"more": 1}\n') is None
    assert bsc.append_only_problem(base, b'{"edited": true}\n') is not None
    assert bsc.append_only_problem(base, b"") is not None


SEED = {
    "series": [
        {
            "series": "abs.labour.unemployment_rate",
            "cadence": "monthly",
            "extras": {"country": "AU", "targetUnit": "percent"},
        }
    ]
}


def _repo(tmp_path: pathlib.Path, rows: list[dict], seed: dict = SEED):
    (tmp_path / "obs.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    (tmp_path / "seed.json").write_text(json.dumps(seed), encoding="utf-8")
    (tmp_path / "registry.jsonl").write_text("", encoding="utf-8")
    return [
        "--observations", str(tmp_path / "obs.jsonl"),
        "--catalog", str(tmp_path / "catalog.json"),
        "--docket", str(tmp_path / "seed.json"),
        "--registry", str(tmp_path / "registry.jsonl"),
    ]


def test_main_builds_and_is_byte_idempotent(
    tmp_path: pathlib.Path, capsys
) -> None:
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")])
    assert bsc.main(argv) == 0
    catalog_1 = (tmp_path / "catalog.json").read_bytes()
    registry_1 = (tmp_path / "registry.jsonl").read_bytes()
    assert bsc.main(argv) == 0
    assert (tmp_path / "catalog.json").read_bytes() == catalog_1
    assert (tmp_path / "registry.jsonl").read_bytes() == registry_1
    assert bsc.main(argv + ["--check"]) == 0
    assert "catalog current: 2 series" in capsys.readouterr().out


def test_main_missing_seed_is_a_hard_error(tmp_path: pathlib.Path) -> None:
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")])
    assert bsc.main(argv) == 0
    (tmp_path / "seed.json").unlink()
    with pytest.raises(SystemExit, match="docket seed missing"):
        bsc.main(argv)
    with pytest.raises(SystemExit, match="docket seed missing"):
        bsc.main(argv + ["--check"])


def test_main_missing_registry_is_a_hard_error(
    tmp_path: pathlib.Path,
) -> None:
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")])
    (tmp_path / "registry.jsonl").unlink()
    with pytest.raises(SystemExit, match="uuid registry missing"):
        bsc.main(argv)


def test_main_remint_guard_and_ceremony(tmp_path: pathlib.Path) -> None:
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")])
    assert bsc.main(argv) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    observed = next(
        r for r in catalog["series"] if r["status"] == "observed"
    )
    old_uuid = observed["uuid"]
    observed["uuid"] = "55555555-5555-4555-8555-555555555555"
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    registry_before = (tmp_path / "registry.jsonl").read_bytes()
    # Refuses without the flag, and writes nothing.
    assert bsc.main(argv) == 1
    assert (tmp_path / "registry.jsonl").read_bytes() == registry_before
    # A pending remint also fails --check.
    assert bsc.main(argv + ["--check"]) == 1
    with pytest.raises(SystemExit, match="requires --remint-note"):
        bsc.main(argv + ["--allow-remint"])
    assert (
        bsc.main(argv + ["--allow-remint", "--remint-note", "test remint"])
        == 0
    )
    lines = (tmp_path / "registry.jsonl").read_text().splitlines()
    event = json.loads(lines[-1])
    assert event["supersedes"] == old_uuid
    assert event["uuid"] == "55555555-5555-4555-8555-555555555555"
    assert event["note"] == "test remint"
    assert bsc.main(argv + ["--check"]) == 0


def test_main_dropped_identity_retires_then_revives(
    tmp_path: pathlib.Path,
) -> None:
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")])
    assert bsc.main(argv) == 0
    original = json.loads((tmp_path / "catalog.json").read_text())
    docket_uuid = next(
        r["uuid"] for r in original["series"] if r["status"] == "docket-only"
    )
    (tmp_path / "seed.json").write_text(
        json.dumps({"series": []}), encoding="utf-8"
    )
    assert bsc.main(argv) == 1  # docket-only row would vanish
    assert bsc.main(argv + ["--allow-remint", "--remint-note", "seed cut"]) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    assert len(catalog["series"]) == 1
    # The drop is an explicit retire event; no line was edited or removed.
    lines = (tmp_path / "registry.jsonl").read_text().splitlines()
    assert len(lines) == 3
    retire = json.loads(lines[-1])
    assert retire["retired"] is True and retire["uuid"] == docket_uuid
    assert retire["note"] == "seed cut"
    assert bsc.main(argv + ["--check"]) == 0
    # Re-seeding the identity revives the SAME uuid — minted once, ever.
    (tmp_path / "seed.json").write_text(json.dumps(SEED), encoding="utf-8")
    assert bsc.main(argv) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    revived_row = next(
        r for r in catalog["series"] if r["status"] == "docket-only"
    )
    assert revived_row["uuid"] == docket_uuid
    lines = (tmp_path / "registry.jsonl").read_text().splitlines()
    assert len(lines) == 4
    revive = json.loads(lines[-1])
    assert revive["revived"] is True and revive["uuid"] == docket_uuid
    assert bsc.main(argv + ["--check"]) == 0


def test_partial_catalog_deletion_cannot_silently_remint(
    tmp_path: pathlib.Path,
) -> None:
    # The v3-review follow-up: deleting SOME rows (not the whole catalog)
    # must not let their identities re-mint silently — every live binding's
    # uuid has to stay in the catalog or be explicitly retired.
    argv = _repo(
        tmp_path,
        [_row("bls.cps.unemployment_rate"), _row("bea.real_gdp.saar")],
    )
    assert bsc.main(argv) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    kept = [r for r in catalog["series"] if r["concept"] != "bea.real_gdp.saar"]
    removed_uuid = next(
        r["uuid"] for r in catalog["series"]
        if r["concept"] == "bea.real_gdp.saar"
    )
    catalog["series"] = kept
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    # The observations still exist, so rebuilding restores the row with its
    # registry uuid — but a tampered catalog alone must fail --check on the
    # liveness rule before any rebuild.
    problems = bsc.registry_agreement_problems(
        catalog, bsc.UuidRegistry.load(tmp_path / "registry.jsonl")
    )
    assert any(removed_uuid in p and "no catalog row" in p for p in problems)
    assert bsc.main(argv + ["--check"]) == 1
    # Rebuild heals: the registry still holds the binding.
    assert bsc.main(argv) == 0
    healed = json.loads((tmp_path / "catalog.json").read_text())
    assert any(r["uuid"] == removed_uuid for r in healed["series"])


def test_dimension_keys_are_injective() -> None:
    # Delimiter-joined keys let crafted values collide across fields.
    assert bsc._geo_key(
        {"level": "a|b", "id": "c", "vintage": None}
    ) != bsc._geo_key({"level": "a", "id": "b|c", "vintage": None})
    assert bsc._geo_key({"level": "None"}) != bsc._geo_key(None)
    assert bsc._entity_key(
        {"name": 'x", "y', "role": None}
    ) != bsc._entity_key({"name": "x", "role": "y"})


def test_check_rejects_uuid_disjoint_catalog(tmp_path: pathlib.Path) -> None:
    # v2 repro: two UUID-disjoint catalogs for the same inputs both passed
    # --check. The registry now pins the bindings.
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")])
    assert bsc.main(argv) == 0
    body = (tmp_path / "catalog.json").read_text()
    catalog = json.loads(body)
    for i, row in enumerate(catalog["series"]):
        row["uuid"] = f"7777777{i}-7777-4777-8777-777777777777"
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    assert bsc.main(argv + ["--check"]) == 1


def test_verify_registry_append_only_mode(
    tmp_path: pathlib.Path, capsys
) -> None:
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")])
    assert bsc.main(argv) == 0
    registry = tmp_path / "registry.jsonl"
    base = tmp_path / "base.jsonl"
    base.write_bytes(registry.read_bytes())
    verify = ["--registry", str(registry),
              "--verify-registry-append-only", str(base)]
    assert bsc.main(verify) == 0
    assert "append-only vs base: ok" in capsys.readouterr().out
    # An absent base (registry introduced by this change) is fine.
    assert bsc.main(
        ["--registry", str(registry),
         "--verify-registry-append-only", str(tmp_path / "nope.jsonl")]
    ) == 0
    # Any edit to committed lines fails.
    lines = registry.read_text().splitlines()
    first = json.loads(lines[0])
    first["uuid"] = "66666666-6666-4666-8666-666666666666"
    registry.write_text(
        "\n".join([json.dumps(first)] + lines[1:]) + "\n", encoding="utf-8"
    )
    assert bsc.main(verify) == 1


def test_doctests_pass() -> None:
    results = doctest.testmod(bsc)
    assert results.failed == 0


def test_committed_catalog_is_current_and_valid() -> None:
    """The committed artifact must regenerate byte-identically from the
    committed inputs, agree with the committed registry binding-for-binding,
    and carry canonical, parsed-unique UUIDv4s."""
    committed_text = bsc.CATALOG.read_text(encoding="utf-8")
    committed = json.loads(committed_text)
    registry = bsc.UuidRegistry.load(bsc.UUID_REGISTRY)
    catalog, plan = bsc.build_catalog(
        bsc.OBSERVATIONS,
        bsc.DOCKET_SEED,
        bsc.ExistingCatalog(bsc.CATALOG),
        registry,
        bsc.ENTITY_FOLDS,
    )
    assert not plan["mints"] and not plan["supersedes"] and not plan["dropped"]
    catalog["uuid_registry_sha256"] = registry.sha256()
    assert bsc.render(catalog) == committed_text
    assert bsc.validate_uuids(committed) == []
    assert bsc.registry_agreement_problems(committed, registry) == []
    # Curated 2026-09-04: LNU02374597 is the BLS CPS series id for the
    # employment-population ratio of persons with a disability, recorded
    # under its raw id by the 2026-08-23 first-print wave (c2aa68d). Its
    # digit run 2374 trips the year hint; it is an identifier, not a date,
    # and stays in the identity because the observation was recorded so.
    assert committed["suspect_segments"] == ["LNU02374597"]
    # EVERY stripped spelling is audited, mapped to the canonical concepts
    # it touched: a statute or edition label colliding with a period
    # spelling can only be caught here. Until 2026-09-30 this was an exact
    # list of spellings, so every append that recorded the next weekly
    # claims print (week_2026-08-29, ...) failed this required check and
    # the resolver merged past it. The audit now asks the question the list
    # stood for, strip by strip: has a curator already decided that this
    # concept's segments in this identifier field and shape (same kept
    # segments, same position, same spelling template) are period labels,
    # and does every observation behind the strip spell its own declared
    # period directly? New concepts, new templates, a period spelled in a
    # new field or position, overlap strips, and reviewed strips that
    # disappear or change kind still fail. See REVIEWED_STRIPPED_SEGMENTS_PATH.
    problems = bsc.stripped_segment_review_problems(
        committed["stripped_segments"],
        plan["strips"],
        REVIEWED_STRIPS,
    )
    assert problems == [], (
        "unreviewed period strips — review each and record it in "
        f"{REVIEWED_STRIPPED_SEGMENTS_PATH.relative_to(ROOT)}:\n"
        + "\n".join(problems)
    )
    assert committed["stripped_segments"]["after_mpc_june_2026"] == [
        "boe.bank_rate"
    ]
    assert all(
        occurrences and occurrences == sorted(set(occurrences))
        for occurrences in committed["stripped_segments"].values()
    )
    assert committed["docket_seed_sha256"] is not None
    assert committed["uuid_registry_sha256"] == registry.sha256()
    assert bsc.DOCKET_SEED.exists()
    # 228 -> 221 at the d353 entity fold (2026-10-12): seven hand-recorded
    # May 2026 lineages folded into their economy/aggregate siblings.
    assert committed["entity_folds_sha256"] == bsc.hashlib.sha256(
        bsc.ENTITY_FOLDS.read_bytes()
    ).hexdigest()
    assert len(committed["series"]) == 221


# --- The stripped-segment audit ---------------------------------------------


CLAIMS = "us.dol.initial_claims.sa"
CONTINUED = "dol.eta.continued_claims.sa"
RID = "source_record_id"
CONCEPT_FIELD = "measure.concept"


def _committed_build() -> tuple[dict, dict]:
    committed = json.loads(bsc.CATALOG.read_text(encoding="utf-8"))
    _, plan = bsc.build_catalog(
        bsc.OBSERVATIONS,
        bsc.DOCKET_SEED,
        bsc.ExistingCatalog(bsc.CATALOG),
        bsc.UuidRegistry.load(bsc.UUID_REGISTRY),
        bsc.ENTITY_FOLDS,
    )
    return committed, plan


def _pairs(stripped: dict) -> set[tuple[str, str]]:
    return {(s, c) for s, concepts in stripped.items() for c in concepts}


def _names(problems: list[str], spelling: str, concept: str) -> list[str]:
    return [p for p in problems if p.startswith(f"{spelling!r} on {concept!r}")]


def _strips(records: dict) -> dict:
    """Nest ``{(concept, field, shape, spelling): kinds}`` records as a
    ``strips`` map (concept -> field -> shape -> spelling -> kinds)."""
    out: dict = {}
    for (concept, field, shape, spelling), kinds in records.items():
        out.setdefault(concept, {}).setdefault(field, {}).setdefault(
            shape, {}
        )[spelling] = sorted(kinds)
    return out


def _segments(records) -> dict[str, list[str]]:
    """The catalog ``stripped_segments`` those records amount to."""
    out: dict[str, set[str]] = {}
    for concept, _, _, spelling in records:
        out.setdefault(spelling, set()).add(concept)
    return {s: sorted(out[s]) for s in sorted(out)}


def test_reviewed_stripped_segments_fixture_is_wellformed() -> None:
    fixture = REVIEWED_STRIPPED_FIXTURE
    assert set(fixture) == {
        "comment", "reviewed_catalog_commit", "notes", "strips",
    }
    reviewed = fixture["strips"]
    committed = json.loads(bsc.CATALOG.read_text(encoding="utf-8"))
    row_concepts = {row["concept"] for row in committed["series"]}
    assert list(reviewed) == sorted(reviewed)
    assert set(reviewed) <= row_concepts
    for concept, by_field in reviewed.items():
        assert by_field and list(by_field) == sorted(by_field), concept
        assert set(by_field) <= set(bsc.IDENTIFIER_FIELDS), concept
        for field, by_shape in by_field.items():
            assert by_shape and list(by_shape) == sorted(by_shape), field
            for shape, by_spelling in by_shape.items():
                slots = bsc.shape_slot_templates(shape)
                assert slots, shape
                assert by_spelling and list(by_spelling) == sorted(
                    by_spelling
                ), shape
                for spelling, kinds in by_spelling.items():
                    assert bsc._is_strippable_spelling(spelling), spelling
                    assert bsc.period_spelling_template(spelling) in slots, (
                        shape, spelling,
                    )
                    assert kinds and kinds == sorted(set(kinds)), kinds
                    assert set(kinds) <= {"derived", "overlap"}, kinds
    records = bsc.strip_records(reviewed)
    assert set(fixture["notes"]) <= {spelling for *_, spelling in records}
    # The June 13 initial-claims pair is one observation's week, spelled
    # with hyphens in its source_record_id and underscores in its concept;
    # both are kept, in their own fields and shapes, and both are overlap
    # strips (see the fixture notes).
    assert {
        key: kinds for key, kinds in records.items()
        if key[3] in ("week_2026-06-13", "week_2026_06_13")
    } == {
        (CLAIMS, CONCEPT_FIELD, f"{CLAIMS}.{{P:week_9999_99_99}}",
         "week_2026_06_13"): {"overlap"},
        (CLAIMS, RID, f"{CLAIMS}.{{P:week_9999-99-99}}",
         "week_2026-06-13"): {"overlap"},
    }
    rows = [
        json.loads(line)
        for line in bsc.OBSERVATIONS.read_text(encoding="utf-8").splitlines()
        if "week_2026-06-13" in line or "week_2026_06_13" in line
    ]
    assert len(rows) == 1
    assert rows[0]["source_record_id"].endswith(".week_2026-06-13")
    assert rows[0]["measure"]["concept"].endswith(".week_2026_06_13")
    assert rows[0]["period"] == {"type": "month", "value": "2026-06"}


def test_strips_match_an_independent_replay() -> None:
    """Differential: re-derive every strip from the committed ledger with
    classify_segments and period_spelling_template alone (its identifier
    field, its shape, and its kinds), resolving each observation to its
    catalog row through that row's concept and aliases at the same
    geography and entity, and require the builder's plan and the catalog
    to agree. A row an active entity fold absorbs (its geography and
    entity are the fold's, and its concept is one of the fold's declared
    absorbed_names, all read straight from the seed) resolves at the
    fold's survivor entity."""
    from check_thesis_facts_append import effective_current_rows

    committed, plan = _committed_build()
    owners: dict[tuple[str, str, str], set[str]] = {}
    for row in committed["series"]:
        dims = (
            bsc._geo_key(row.get("geography")),
            bsc._entity_key(row.get("entity")),
        )
        for name in [row["concept"], *row["aliases"]]:
            owners.setdefault((name, *dims), set()).add(row["concept"])
    rows = [
        json.loads(line)
        for line in bsc.OBSERVATIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    seed = json.loads(bsc.ENTITY_FOLDS.read_text(encoding="utf-8"))
    active = [fold for fold in seed["folds"] if not fold.get("undone")]
    replay: dict[tuple[str, str, str, str], set[str]] = {}
    folded = 0
    for obs in effective_current_rows(rows):
        period = obs.get("period") or {}
        raw = obs["measure"]["concept"]
        dims = (
            bsc._geo_key(obs.get("geography") or None),
            bsc._entity_key(obs.get("entity") or None),
        )
        pattern_concept = bsc.concept_for(bsc.family_pattern(raw, period))
        survivors = {
            bsc._entity_key(fold["survivor_entity"])
            for fold in active
            if dims == (
                bsc._geo_key(fold["geography"]),
                bsc._entity_key(fold["absorbed_entity"]),
            )
            and pattern_concept in fold["absorbed_names"]
        }
        if survivors:
            (survivor,) = survivors
            dims = (dims[0], survivor)
            folded += 1
        (canonical,) = owners.get((pattern_concept, *dims)) or owners[
            (raw, *dims)
        ]
        for field, identifier in (
            (CONCEPT_FIELD, raw), (RID, obs["source_record_id"]),
        ):
            classified = bsc.classify_segments(identifier, period)
            shape = ".".join(
                segment if kind == "kept"
                else "{P:" + bsc.period_spelling_template(segment) + "}"
                for segment, kind in classified
            )
            for segment, kind in classified:
                if kind != "kept":
                    replay.setdefault(
                        (canonical, field, shape, segment), set()
                    ).add(kind)
    assert active and folded >= len(active)  # the folds are exercised
    assert plan["strips"] == _strips(replay)
    assert _segments(replay) == committed["stripped_segments"]


@pytest.mark.parametrize("continued_claims_printed", [False, True])
def test_committed_audit_fails_on_corrupted_catalogs(
    continued_claims_printed: bool,
) -> None:
    # Each corruption must add a problem naming its pair, whatever else the
    # committed catalog is waiting on (that is the committed test's job).
    committed, plan = _committed_build()
    segments = {s: list(c) for s, c in committed["stripped_segments"].items()}
    live = bsc.strip_records(plan["strips"])
    audit = bsc.stripped_segment_review_problems
    claims_shape = f"{CLAIMS}.{{P:week_9999-99-99}}"
    # A week no initial-claims print has reached: a year past the latest
    # week this concept's source_record_id strips, so the cases below keep
    # naming an unprinted week as weekly claims prints land
    # (week_2026-09-19, the original choice, was printed at d7e45bc5).
    printed_weeks = sorted(
        spelling[len("week_"):]
        for concept, field, shape, spelling in live
        if (concept, field, shape) == (CLAIMS, RID, claims_shape)
    )
    unprinted_week = "week_" + (
        dt.date.fromisoformat(printed_weeks[-1]) + dt.timedelta(weeks=52)
    ).isoformat()
    # Only the initial-claims pair need be unprinted: another concept may
    # print that week first (continued claims, parametrized below), which
    # is a valid strip and must not break this self-test.
    assert CLAIMS not in segments.get(unprinted_week, [])
    if continued_claims_printed:
        continued_shape = f"{CONTINUED}.{{P:week_9999-99-99}}.first_print"
        assert (CONTINUED, RID, continued_shape) in {k[:3] for k in live}
        before = audit(segments, _strips(live), REVIEWED_STRIPS)
        live[(CONTINUED, RID, continued_shape, unprinted_week)] = {"derived"}
        segments.setdefault(unprinted_week, []).append(CONTINUED)
        assert audit(segments, _strips(live), REVIEWED_STRIPS) == before
        assert unprinted_week in segments
    baseline = set(audit(segments, _strips(live), REVIEWED_STRIPS))

    def corrupt(spelling, concept, strip_kinds, field, shape, *,
                in_plan=True):
        bad_segments = {s: list(c) for s, c in segments.items()}
        if concept not in bad_segments.get(spelling, []):
            bad_segments.setdefault(spelling, []).append(concept)
        bad = dict(live)
        if in_plan:
            bad[(concept, field, shape, spelling)] = set(strip_kinds)
        return _names(
            sorted(
                set(audit(bad_segments, _strips(bad), REVIEWED_STRIPS))
                - baseline
            ),
            spelling, concept,
        )

    # A reviewed spelling disappears.
    gone = {k: v for k, v in live.items() if k[3] != "after_mpc_june_2026"}
    assert _names(
        audit(_segments(gone), _strips(gone), REVIEWED_STRIPS),
        "after_mpc_june_2026", "boe.bank_rate",
    )
    # A concept strips for the first time, as the 2026-09-24 proposal (#289)
    # did when abs.labour.unemployment_rate took its first print beside the
    # already-observed abs.labour.unemployment_rate.australia.
    never = "corrupt.never_observed.rate"
    assert corrupt(
        "2026_08", never, ["derived"], RID, f"{never}.{{P:9999_99}}"
    )
    # A reviewed concept strips a spelling template it never used.
    assert corrupt(
        "2026_08", CLAIMS, ["derived"], RID, f"{CLAIMS}.{{P:9999_99}}"
    )
    # A reviewed concept and template in a new shape: the review of #309 at
    # 0852fcd6 (its period spelled inside measure.concept, where it moves
    # the family pattern), in the other field, or beside a new kept segment.
    cpi = "abs.cpi.all_groups.yoy"
    cpi_rid = f"{cpi}.{{P:9999_99}}.first_print"
    assert (cpi, RID, cpi_rid, "2026_08") in live
    for field, shape in (
        (CONCEPT_FIELD, "abs.cpi.{P:9999_99}.all_groups.yoy"),
        (CONCEPT_FIELD, cpi_rid),
        (RID, f"{cpi}.{{P:9999_99}}.revised"),
    ):
        named = corrupt("2026_09", cpi, ["derived"], field, shape)
        assert named and f"first strip in {field} shape {shape!r}" in (
            named[0]
        ), named
    assert not corrupt("2026_09", cpi, ["derived"], RID, cpi_rid)
    # A reviewed concept and shape, but an overlap strip.
    assert corrupt(unprinted_week, CLAIMS, ["overlap"], RID, claims_shape)
    # A reviewed strip that an observation now reaches as an overlap.
    assert corrupt(
        "week_2026-08-22", CLAIMS, ["derived", "overlap"], RID, claims_shape
    )
    # A statute label on a reviewed concept.
    assert corrupt(
        "section_2026", "boe.bank_rate", ["derived"], RID,
        "boe.bank_rate.{P:section_9999}",
    )
    # A plan strip whose spelling fills no slot of its (reviewed) shape.
    assert corrupt("2026_08", CLAIMS, ["derived"], RID, claims_shape) == [
        f"'2026_08' on '{CLAIMS}': stripped spelling fills no slot of its "
        f"source_record_id shape '{claims_shape}'"
    ]
    # A non-period spelling is refused even when a curator listed it.
    bogus_key = (
        "boe.bank_rate", RID, "boe.bank_rate.{P:section_9999}",
        "section_2026",
    )
    bogus_live = {**live, bogus_key: {"derived"}}
    bogus_reviewed = _strips(
        {**bsc.strip_records(REVIEWED_STRIPS), bogus_key: {"derived"}}
    )
    assert set(audit(
        _segments(bogus_live), _strips(bogus_live), bogus_reviewed
    )) - baseline == {
        "'section_2026' on 'boe.bank_rate': stripped spelling is not a "
        "period token"
    }
    # The catalog claims a strip the build plan does not make.
    assert corrupt(
        unprinted_week, CLAIMS, ["derived"], RID, claims_shape,
        in_plan=False,
    )
    # And the routine case the exact list used to reject passes.
    assert not corrupt(unprinted_week, CLAIMS, ["derived"], RID, claims_shape)


def test_a_reviewed_template_in_a_new_concept_position_needs_review(
    tmp_path: pathlib.Path,
) -> None:
    """Regression from the review of #309 at 0852fcd6, on the real ledger:
    a copy of the 2026-08 ABS CPI first print moved to 2026-09, with the
    period also spelled INSIDE measure.concept. The builder folds it into
    the reviewed identity (family pattern abs.cpi.{P}.all_groups.yoy,
    canonical concept abs.cpi.all_groups.yoy: no mint), so an audit keyed
    on concept and spelling template alone let the slot borrow the
    source_record_id decision. Scoped by field and shape, it is reported,
    and only the new measure.concept shape is."""
    _, committed_plan = _committed_build()
    committed = json.loads(bsc.CATALOG.read_text(encoding="utf-8"))
    baseline = set(bsc.stripped_segment_review_problems(
        committed["stripped_segments"], committed_plan["strips"],
        REVIEWED_STRIPS,
    ))
    text = bsc.OBSERVATIONS.read_text(encoding="utf-8")
    (source,) = [
        json.loads(line) for line in text.splitlines()
        if json.loads(line)["source_record_id"]
        == "abs.cpi.all_groups.yoy.2026_08.first_print"
    ]
    assert source["period"] == {"type": "month", "value": "2026-08"}
    row = json.loads(json.dumps(source))
    row.pop("assertionVersion", None)
    row["period"]["value"] = "2026-09"
    row["measure"]["concept"] = "abs.cpi.2026_09.all_groups.yoy"
    row["source_record_id"] = "abs.cpi.all_groups.yoy.2026_09.first_print"
    observations = tmp_path / "obs.jsonl"
    observations.write_text(text + json.dumps(row) + "\n", encoding="utf-8")
    catalog, plan = bsc.build_catalog(
        observations,
        bsc.DOCKET_SEED,
        bsc.ExistingCatalog(bsc.CATALOG),
        bsc.UuidRegistry.load(bsc.UUID_REGISTRY),
        bsc.ENTITY_FOLDS,
    )
    assert not plan["mints"] and not plan["supersedes"]
    assert not plan["dropped"]
    (series,) = [
        s for s in catalog["series"] if s["concept"] == "abs.cpi.all_groups.yoy"
    ]
    assert "abs.cpi.{P}.all_groups.yoy" in series["family_patterns"]
    cpi = plan["strips"]["abs.cpi.all_groups.yoy"]
    assert cpi[RID]["abs.cpi.all_groups.yoy.{P:9999_99}.first_print"][
        "2026_09"
    ] == ["derived"]
    problems = bsc.stripped_segment_review_problems(
        catalog["stripped_segments"], plan["strips"], REVIEWED_STRIPS
    )
    assert set(problems) - baseline == {
        "'2026_09' on 'abs.cpi.all_groups.yoy': first strip in "
        "measure.concept shape 'abs.cpi.{P:9999_99}.all_groups.yoy' for "
        "this concept — confirm it is a period label, not a statute, "
        "cohort, or edition label, and add it to the reviewed map"
    }


def _successor(period: dict) -> dict | None:
    ptype, value = period.get("type"), str(period.get("value"))
    if ptype == "week_ending":
        end = dt.date.fromisoformat(value) + dt.timedelta(days=7)
        return {"type": ptype, "value": end.isoformat()}
    if ptype in ("month", "quarter"):
        year, month = map(int, value.split("-"))
        month += 1 if ptype == "month" else 3
        year, month = year + (month - 1) // 12, (month - 1) % 12 + 1
        return {"type": ptype, "value": f"{year}-{month:02d}"}
    if ptype in ("fiscal_year", "year", "calendar_year", "tax_year"):
        return {"type": ptype, "value": str(int(value) + 1)}
    return None


def _month_styles(spelling: str) -> tuple[str, ...]:
    """How each month word of ``spelling`` is written: ``full``, ``abbrev``,
    or ``either`` for ``may``, which is both."""
    return tuple(
        "either" if word == "may"
        else "full" if word in bsc.MONTHS_FULL
        else "abbrev"
        for word in bsc._MONTH_WORD_RE.findall(spelling)
    )


def _respell(identifier: str, period: dict, successor: dict) -> str | None:
    """``identifier`` with each strip of ``period`` rewritten as the same
    template's spelling of ``successor``, month words kept full or
    abbreviated as they were; None if any strip has no such spelling (an
    overlap strip). ``may`` is both styles, so its successor is written in
    full (``june``, not ``jun``); either is a continuation of the shape."""
    variants = bsc.period_token_variants(successor)
    parts = []
    for segment, kind in bsc.classify_segments(identifier, period):
        if kind == "kept":
            parts.append(segment)
            continue
        template = bsc.period_spelling_template(segment)
        styles = _month_styles(segment)
        same = [
            v for v in variants
            if bsc.period_spelling_template(v) == template
            and all(
                "either" in (a, b) or a == b
                for a, b in zip(styles, _month_styles(v))
            )
        ]
        if len(same) > 1:
            same = [v for v in same if "abbrev" not in _month_styles(v)]
        if kind != "derived" or len(same) != 1:
            return None
        parts.append(same[0])
    return ".".join(parts)


def test_next_period_of_every_committed_series_passes_the_audit(
    tmp_path: pathlib.Path,
) -> None:
    """The append the exact list rejected, on real data: for EVERY current
    observation whose source_record_id strips a period and whose strips are
    all direct spellings of its period, append the NEXT period written the
    same way. The rebuilt catalog grows new spellings and lands them on the
    existing identities, and with the committed strips taken as reviewed,
    none of the new ones needs review. (Whether the committed strips ARE
    reviewed is the committed test's question; on a clean branch the two
    maps agree.)"""
    from check_thesis_facts_append import effective_current_rows

    rows = [
        json.loads(line)
        for line in bsc.OBSERVATIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    appended = []
    eligible = 0
    for obs in effective_current_rows(rows):
        period = obs.get("period") or {}
        successor = _successor(period)
        kinds = [
            kind
            for identifier in (obs["source_record_id"], obs["measure"]["concept"])
            for _, kind in bsc.classify_segments(identifier, period)
            if kind != "kept"
        ]
        if successor is None or not any(
            kind != "kept"
            for _, kind in bsc.classify_segments(obs["source_record_id"], period)
        ) or set(kinds) != {"derived"}:
            continue
        eligible += 1
        rid = _respell(obs["source_record_id"], period, successor)
        concept = _respell(obs["measure"]["concept"], period, successor)
        if rid is None or concept is None:
            continue
        nxt = json.loads(json.dumps(obs))
        nxt.pop("assertionVersion", None)
        nxt["period"] = successor
        nxt["source_record_id"] = rid
        nxt["measure"]["concept"] = concept
        appended.append(nxt)
    # Every eligible observation, month names included; most of the ledger.
    assert len(appended) == eligible >= 200
    observations = tmp_path / "obs.jsonl"
    observations.write_text(
        bsc.OBSERVATIONS.read_text(encoding="utf-8")
        + "".join(json.dumps(r) + "\n" for r in appended),
        encoding="utf-8",
    )
    catalog, plan = bsc.build_catalog(
        observations,
        bsc.DOCKET_SEED,
        bsc.ExistingCatalog(bsc.CATALOG),
        bsc.UuidRegistry.load(bsc.UUID_REGISTRY),
        bsc.ENTITY_FOLDS,
    )
    assert not plan["mints"] and not plan["supersedes"]
    assert not plan["dropped"] and not plan["enrich_retires"]
    committed = json.loads(bsc.CATALOG.read_text(encoding="utf-8"))
    new_pairs = _pairs(catalog["stripped_segments"]) - _pairs(
        committed["stripped_segments"]
    )
    assert len(new_pairs) >= 50
    _, committed_plan = _committed_build()
    # Every new strip lands in a shape its concept already strips in.
    assert {key[:3] for key in bsc.strip_records(plan["strips"])} == {
        key[:3] for key in bsc.strip_records(committed_plan["strips"])
    }
    assert bsc.stripped_segment_review_problems(
        catalog["stripped_segments"],
        plan["strips"],
        committed_plan["strips"],
    ) == []


def _strip_builds(
    tmp_path: pathlib.Path,
    base: list[dict],
    appended: list[dict],
    reviewed: dict | None = None,
) -> tuple[dict, dict, list[str]]:
    """Build ``base`` (its strips become the reviewed map unless one is
    given), append ``appended``, rebuild on the first build's catalog, and
    audit the result. UUID staging is not under test here, so the builds
    skip ``main`` (and its git calls) and inherit from the catalog alone.
    Returns the reviewed map, the rebuilt catalog, and the problems."""
    first, first_plan = _build(tmp_path, base, docket=SEED)
    if reviewed is None:
        reviewed = first_plan["strips"]
    catalog, plan = _build(
        tmp_path, [*base, *appended], existing=first, docket=SEED
    )
    problems = bsc.stripped_segment_review_problems(
        catalog["stripped_segments"], plan["strips"], reviewed
    )
    return reviewed, catalog, problems


def _strip_audit(
    tmp_path: pathlib.Path,
    base: list[dict],
    appended: list[dict],
    reviewed: dict | None = None,
) -> list[str]:
    return _strip_builds(tmp_path, base, appended, reviewed)[2]


def _weekly(end: str, role: str = "ui_claimant") -> dict:
    return _row(
        CLAIMS,
        rid=f"{CLAIMS}.week_{end}",
        unit="thousands",
        period={"type": "week_ending", "value": end},
        entity={"name": "person", "role": role},
    )


def test_strip_audit_passes_the_next_print(tmp_path: pathlib.Path) -> None:
    def monthly(value: str) -> dict:
        return _row(
            "census.m3.orders_mom",
            rid=f"census.m3.orders_mom.{value.replace('-', '_')}",
            period={"type": "month", "value": value},
        )

    assert _strip_audit(
        tmp_path,
        [_weekly("2026-08-15"), _weekly("2026-08-22"), monthly("2026-06")],
        [_weekly("2026-08-29"), _weekly("2026-09-05"), monthly("2026-07")],
    ) == []


def test_strip_audit_flags_a_label_on_a_new_concept(
    tmp_path: pathlib.Path,
) -> None:
    # A statute label that spells its row's own period: mechanically a
    # period, and only a curator can say otherwise. Its concept has never
    # stripped, so nothing reviewed covers it.
    statute = _row(
        "treasury.debt_limit.suspension_act",
        rid="treasury.debt_limit.suspension_act.2026_09.first_print",
        period={"type": "month", "value": "2026-09"},
    )
    problems = _strip_audit(tmp_path, [_weekly("2026-08-22")], [statute])
    assert problems == [
        "'2026_09' on 'treasury.debt_limit.suspension_act': first strip in "
        "source_record_id shape "
        "'treasury.debt_limit.suspension_act.{P:9999_99}.first_print' for "
        "this concept — confirm it is a period label, not a statute, "
        "cohort, or edition label, and add it to the reviewed map"
    ]


def test_strip_audit_flags_a_new_template_on_a_reviewed_concept(
    tmp_path: pathlib.Path,
) -> None:
    ending = _row(
        CLAIMS,
        rid=f"{CLAIMS}.week_ending_2026_08_29",
        unit="thousands",
        period={"type": "week_ending", "value": "2026-08-29"},
        entity={"name": "person", "role": "ui_claimant"},
    )
    problems = _strip_audit(tmp_path, [_weekly("2026-08-22")], [ending])
    assert len(problems) == 1
    assert _names(problems, "week_ending_2026_08_29", CLAIMS)
    assert (
        f"first strip in source_record_id shape "
        f"'{CLAIMS}.{{P:week_ending_9999_99_99}}'"
    ) in problems[0]


@pytest.mark.parametrize(
    ("concept", "rid", "field", "shape"),
    [
        # The review of #309 at 0852fcd6: the period also spelled inside
        # measure.concept, where it moves the family pattern but not the
        # canonical concept.
        ("agency.2026_09.rate", "agency.rate.2026_09",
         CONCEPT_FIELD, "agency.{P:9999_99}.rate"),
        # The very shape string of the reviewed source_record_id strips,
        # but in the other field.
        ("agency.rate.2026_09", "agency.rate.2026_09",
         CONCEPT_FIELD, "agency.rate.{P:9999_99}"),
        # A new kept segment beside a reviewed slot (a revision).
        ("agency.rate", "agency.rate.2026_09.revised",
         RID, "agency.rate.{P:9999_99}.revised"),
        # The reviewed template in a new position of source_record_id.
        ("agency.rate", "agency.2026_09.rate",
         RID, "agency.{P:9999_99}.rate"),
    ],
)
def test_strip_audit_flags_a_reviewed_template_in_a_new_shape(
    tmp_path: pathlib.Path, concept: str, rid: str, field: str, shape: str,
) -> None:
    def monthly(value: str, concept: str, rid: str) -> dict:
        return _row(concept, rid=rid, period={"type": "month", "value": value})

    # Reviewed: agency.rate's source_record_id strips, in shape
    # agency.rate.{P:9999_99}.
    base = [
        monthly("2026-07", "agency.rate", "agency.rate.2026_07"),
        monthly("2026-08", "agency.rate", "agency.rate.2026_08"),
    ]
    _, catalog, problems = _strip_builds(
        tmp_path, base, [monthly("2026-09", concept, rid)]
    )
    # Every case folds into the reviewed identity, so nothing but the
    # strip audit sees it.
    assert [row["concept"] for row in catalog["series"]].count(
        "agency.rate"
    ) == 1
    assert problems == [
        f"'2026_09' on 'agency.rate': first strip in {field} shape "
        f"{shape!r} for this concept — confirm it is a period label, not a "
        "statute, cohort, or edition label, and add it to the reviewed map"
    ]


def test_strip_audit_flags_an_overlap_strip_on_a_reviewed_template(
    tmp_path: pathlib.Path,
) -> None:
    # The June 13 defect again: a weekly print declared as a month, on a
    # second entity of the reviewed concept.
    monthly = _row(
        CLAIMS,
        rid=f"{CLAIMS}.week_2026-09-12",
        unit="thousands",
        period={"type": "month", "value": "2026-09"},
        entity={"name": "person", "role": "ui_initial_claimant"},
    )
    problems = _strip_audit(tmp_path, [_weekly("2026-08-22")], [monthly])
    assert problems == [
        f"'week_2026-09-12' on '{CLAIMS}': unreviewed overlap strip "
        f"(kinds ['overlap']) in source_record_id shape "
        f"'{CLAIMS}.{{P:week_9999-99-99}}' — the identifier names a window "
        "that only overlaps its row's declared period; review it"
    ]


def test_strip_audit_flags_a_reviewed_strip_reached_by_overlap(
    tmp_path: pathlib.Path,
) -> None:
    # Same spelling, same concept, same shape, already reviewed — but this
    # observation declares a month, so the reviewed strip gains a kind.
    monthly = _row(
        CLAIMS,
        rid=f"{CLAIMS}.week_2026-08-22",
        unit="thousands",
        period={"type": "month", "value": "2026-08"},
        entity={"name": "person", "role": "ui_initial_claimant"},
    )
    problems = _strip_audit(tmp_path, [_weekly("2026-08-22")], [monthly])
    assert len(problems) == 1
    assert "gained kinds ['overlap']" in problems[0]


def test_strip_audit_flags_a_reviewed_strip_that_is_gone(
    tmp_path: pathlib.Path,
) -> None:
    claims_shape = f"{CLAIMS}.{{P:week_9999-99-99}}"
    reviewed = _strips({
        (CLAIMS, RID, claims_shape, "week_2026-08-22"): {"derived"},
        (CONTINUED, RID, f"{CONTINUED}.{{P:week_9999-99-99}}.first_print",
         "week_2026-08-29"): {"derived"},
        # Still stripped, but no longer in this shape.
        (CLAIMS, CONCEPT_FIELD, claims_shape, "week_2026-08-22"): {
            "derived"
        },
    })
    problems = _strip_audit(
        tmp_path, [_weekly("2026-08-22")], [], reviewed=reviewed
    )
    assert problems == [
        "'week_2026-08-22' on 'us.dol.initial_claims.sa': reviewed strip in "
        f"measure.concept shape '{claims_shape}' is gone from the catalog "
        "— a superseded observation, curation, or a builder change; "
        "re-review and update the reviewed map",
        "'week_2026-08-29' on 'dol.eta.continued_claims.sa': reviewed strip "
        "in source_record_id shape "
        f"'{CONTINUED}.{{P:week_9999-99-99}}.first_print' is gone from the "
        "catalog — a superseded observation, curation, or a builder "
        "change; re-review and update the reviewed map",
    ]


# --- Properties of the stripped-segment audit --------------------------------
#
# Invariants, for every input:
#  T1  a spelling's template depends only on how it is written, never on the
#      period it names (same family, any two dates -> same template);
#  T2  different ways of writing a period get different templates;
#  T3  every family used below spells its own period directly;
#  T4  an identifier's strip shape depends only on its kept segments, where
#      its period sits, and how it is written: never on the period named,
#      and different positions or templates give different shapes;
#  A1  routine continuation passes: appending further periods of observed
#      series, each written as that series already writes them, never
#      creates a problem (end to end, through the real builder);
#  A2  soundness: a strip on a concept with no reviewed strip in its field
#      and shape (a new concept, a new template, the period spelled in a
#      new field or position, a new kept segment), or with an unreviewed
#      overlap kind, is always reported by name (end to end);
#  A3  persistence: every reviewed strip missing from the plan is reported;
#  A4  monotone in review: reviewing more live strips never adds problems,
#      and reviewing every live strip as it is leaves none;
#  A5  the output is sorted and independent of input ordering;
#  A6  exactness: the strips the audit names are exactly those a direct
#      reading of the rule names (a differential against a reference
#      model, in both directions).
# Runs are derandomized so the required check stays deterministic.

AUDIT_SETTINGS = settings(
    derandomize=True,
    deadline=None,
    max_examples=60,
    suppress_health_check=[HealthCheck.too_slow],
)

_DATES = st.dates(min_value=dt.date(1901, 1, 1), max_value=dt.date(2998, 12, 1))


def _month(d: dt.date) -> str:
    return bsc.MONTHS_FULL[d.month - 1]


def _quarter(d: dt.date) -> int:
    return (d.month - 1) // 3 + 1


def _week(d: dt.date) -> dict:
    return {"type": "week_ending", "value": d.isoformat()}


def _monthly(d: dt.date) -> dict:
    return {"type": "month", "value": f"{d:%Y-%m}"}


def _quarterly(d: dt.date) -> dict:
    return {"type": "quarter", "value": f"{d:%Y-%m}"}


# family -> (spelling of a date, the period that spelling denotes directly)
FAMILIES = {
    "week_iso": (lambda d: f"week_{d.isoformat()}", _week),
    "week_us": (lambda d: f"week_{d:%Y_%m_%d}", _week),
    "week_ending_iso": (lambda d: f"week_ending_{d.isoformat()}", _week),
    "week_ending_us": (lambda d: f"week_ending_{d:%Y_%m_%d}", _week),
    "month_iso": (lambda d: f"{d:%Y-%m}", _monthly),
    "month_us": (lambda d: f"{d:%Y_%m}", _monthly),
    "month_name": (lambda d: f"{_month(d)}_{d.year}", _monthly),
    "month_abbrev": (
        lambda d: f"{bsc.MONTHS_ABBREV[d.month - 1]}_{d.year}", _monthly,
    ),
    "quarter_q_first": (lambda d: f"q{_quarter(d)}_{d.year}", _quarterly),
    "quarter_year_first": (lambda d: f"{d.year}_q{_quarter(d)}", _quarterly),
    "fiscal": (
        lambda d: f"fy{d.year}",
        lambda d: {"type": "fiscal_year", "value": d.year},
    ),
    "annual": (
        lambda d: f"{d.year}",
        lambda d: {"type": "year", "value": str(d.year)},
    ),
}
# Spellings only the overlap grammar produces (never a direct variant).
SHAPES_ONLY = {
    "day_iso": lambda d: d.isoformat(),
    "day_us": lambda d: f"{d:%Y_%m_%d}",
    "after_month": lambda d: f"after_{_month(d)}_{d.year}",
    "after_mpc_month": lambda d: f"after_mpc_{_month(d)}_{d.year}",
    "month_range": lambda d: f"january_to_{_month(d)}_{d.year}",
}
ALL_SHAPES = {name: spell for name, (spell, _) in FAMILIES.items()}
ALL_SHAPES.update(SHAPES_ONLY)
# Full and abbreviated month names deliberately share one template.
SAME_TEMPLATE = {frozenset({"month_name", "month_abbrev"})}


@AUDIT_SETTINGS
@given(st.sampled_from(sorted(ALL_SHAPES)), _DATES, _DATES)
def test_template_depends_only_on_the_spelling_family(name, d1, d2) -> None:
    spell = ALL_SHAPES[name]
    first, second = spell(d1), spell(d2)
    assert bsc._is_strippable_spelling(first)
    assert bsc.period_spelling_template(first) == bsc.period_spelling_template(
        second
    )


@AUDIT_SETTINGS
@given(
    st.sampled_from(sorted(ALL_SHAPES)),
    st.sampled_from(sorted(ALL_SHAPES)),
    _DATES,
    _DATES,
)
def test_template_separates_spelling_families(a, b, d1, d2) -> None:
    same = bsc.period_spelling_template(
        ALL_SHAPES[a](d1)
    ) == bsc.period_spelling_template(ALL_SHAPES[b](d2))
    assert same == (a == b or frozenset({a, b}) in SAME_TEMPLATE)


@AUDIT_SETTINGS
@given(st.sampled_from(sorted(FAMILIES)), _DATES)
def test_every_family_spells_its_period_directly(name, d) -> None:
    spell, period = FAMILIES[name]
    assert spell(d) in bsc.period_token_variants(period(d))
    assert bsc.classify_segments(f"x.{spell(d)}", period(d)) == [
        ("x", "kept"), (spell(d), "derived"),
    ]


# Where a period can sit in an identifier around the kept segments a.b.c.
POSITIONS = {
    "before": lambda p: f"{p}.a.b.c",
    "inside": lambda p: f"a.{p}.b.c",
    "after": lambda p: f"a.b.c.{p}",
    "twice": lambda p: f"a.{p}.b.{p}",
}


@AUDIT_SETTINGS
@given(
    st.sampled_from(sorted(FAMILIES)),
    st.sampled_from(sorted(FAMILIES)),
    st.sampled_from(sorted(POSITIONS)),
    st.sampled_from(sorted(POSITIONS)),
    _DATES,
    _DATES,
)
def test_strip_shape_is_the_identifier_up_to_calendar_values(
    a, b, at_a, at_b, d1, d2,
) -> None:
    def shape(name: str, at: str, d: dt.date) -> str:
        spell, period = FAMILIES[name]
        return bsc.strip_shape(POSITIONS[at](spell(d)), period(d))

    first = shape(a, at_a, d1)
    template = bsc.period_spelling_template(FAMILIES[a][0](d1))
    assert first == POSITIONS[at_a]("{P:%s}" % template)
    assert bsc.shape_slot_templates(first) == [template] * (
        2 if at_a == "twice" else 1
    )
    same_family = a == b or frozenset({a, b}) in SAME_TEMPLATE
    assert (first == shape(b, at_b, d2)) == (same_family and at_a == at_b)


def _step(name: str, d: dt.date, n: int) -> dt.date:
    """A date in the n-th period after the one holding d, for ``name``."""
    if name.startswith("week"):
        return d + dt.timedelta(days=7 * n)
    if name in ("fiscal", "annual"):
        return dt.date(d.year + n, 1, 1)
    months = 3 if name.startswith("quarter") else 1
    total = d.year * 12 + d.month - 1 + months * n
    return dt.date(total // 12, total % 12 + 1, 1)


CONCEPT_POOL = [f"agency{i}.series{i}.rate" for i in range(6)]

_series = st.lists(
    st.tuples(
        st.sampled_from(CONCEPT_POOL),
        st.sampled_from(sorted(FAMILIES)),
        st.dates(min_value=dt.date(2000, 1, 1), max_value=dt.date(2090, 1, 1)),
        st.integers(min_value=1, max_value=3),  # observed periods
        st.integers(min_value=1, max_value=3),  # appended periods
        st.booleans(),  # the period is also spelled in measure.concept
    ),
    min_size=1,
    max_size=4,
    unique_by=lambda spec: spec[0],
)


def _series_rows(specs, appended: bool) -> list[dict]:
    rows = []
    for concept, name, start, observed, extra, in_concept in specs:
        spell, period = FAMILIES[name]
        steps = range(observed, observed + extra) if appended else range(
            observed
        )
        for n in steps:
            d = _step(name, start, n)
            rows.append(_row(
                f"{concept}.{spell(d)}" if in_concept else concept,
                rid=f"{concept}.{spell(d)}.first_print",
                period=period(d),
            ))
    return rows


@AUDIT_SETTINGS
@given(_series)
def test_routine_appends_never_need_review(specs) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        reviewed, catalog, problems = _strip_builds(
            pathlib.Path(tmp),
            _series_rows(specs, appended=False),
            _series_rows(specs, appended=True),
        )
    assert problems == []
    # Not vacuous: every appended period adds a strip nobody reviewed.
    new_pairs = _pairs(catalog["stripped_segments"]) - {
        (spelling, concept)
        for concept, _, _, spelling in bsc.strip_records(reviewed)
    }
    assert len(new_pairs) >= sum(extra for *_, extra, _ in specs)


# The period each family's spelling only overlaps: coarser than its own.
COARSER = {
    "week": _monthly,
    "month": _quarterly,
    "quarter": lambda d: {"type": "year", "value": str(d.year)},
    "fiscal": lambda d: {"type": "year", "value": str(d.year)},
}


@AUDIT_SETTINGS
@given(
    _series,
    st.sampled_from(["new_concept", "new_template", "new_shape", "overlap"]),
    st.data(),
)
def test_unreviewed_strips_are_always_reported(specs, novelty, data) -> None:
    concept, family, start, observed, _, _ = specs[0]
    other = {"name": "person", "role": "second_entity"}
    if novelty == "new_concept":
        concept = "novel.series.rate"
        name = data.draw(st.sampled_from(sorted(FAMILIES)), label="family")
        d = data.draw(_DATES, label="date")
        spelling = FAMILIES[name][0](d)
        row = _row(
            concept, rid=f"{concept}.{spelling}", period=FAMILIES[name][1](d)
        )
    elif novelty == "new_template":
        seen = bsc.period_spelling_template(FAMILIES[family][0](start))
        fresh = [
            f for f in sorted(FAMILIES)
            if bsc.period_spelling_template(FAMILIES[f][0](start)) != seen
        ]
        name = data.draw(st.sampled_from(fresh), label="fresh family")
        spelling = FAMILIES[name][0](start)
        row = _row(
            concept, rid=f"{concept}.{spelling}",
            period=FAMILIES[name][1](start), entity=other,
        )
    elif novelty == "new_shape":
        # The next period, spelled the reviewed way, but somewhere no
        # reviewed strip of this concept sits: inside measure.concept (the
        # review of #309 at 0852fcd6; the row then folds into the reviewed
        # identity) or beside a new kept segment of source_record_id.
        spell, period = FAMILIES[family]
        d = _step(family, start, observed)
        spelling = spell(d)
        agency, rest = concept.split(".", 1)
        raw, rid = data.draw(st.sampled_from([
            (f"{agency}.{spelling}.{rest}", f"{concept}.{spelling}.first_print"),
            (concept, f"{concept}.{spelling}.revised"),
        ]), label="where")
        row = _row(raw, rid=rid, period=period(d))
    else:
        if family == "annual":  # a bare year overlaps nothing; use a month
            family, concept = "month_us", "novel.series.rate"
        # Either the very spelling already reviewed (it gains a kind) or a
        # later period in the reviewed template (a new overlap strip): both
        # must be reported once an observation reaches them by overlap.
        when = _step(family, start, data.draw(
            st.sampled_from([0, 7]), label="periods after the first"
        ))
        spelling = FAMILIES[family][0](when)
        coarser = COARSER[family.split("_")[0]](when)
        row = _row(
            concept, rid=f"{concept}.{spelling}", period=coarser, entity=other
        )
    with tempfile.TemporaryDirectory() as tmp:
        problems = _strip_audit(
            pathlib.Path(tmp), _series_rows(specs, appended=False), [row]
        )
    assert _names(problems, spelling, concept), (novelty, spelling, problems)


_KINDS = st.sampled_from([["derived"], ["overlap"], ["derived", "overlap"]])
# Where a strip is recorded: field, and what follows the period slot.
_PLACES = [(CONCEPT_FIELD, ""), (RID, ".first_print"), (RID, ".flash")]


def _record(concept, name, d, place, kinds):
    spelling = ALL_SHAPES[name](d)
    field, suffix = place
    template = bsc.period_spelling_template(spelling)
    shape = f"{concept}.{{P:{template}}}{suffix}"
    return (concept, field, shape, spelling), frozenset(kinds)


_live_records = st.lists(
    st.builds(
        _record,
        st.sampled_from(CONCEPT_POOL),
        st.sampled_from(sorted(ALL_SHAPES)),
        _DATES,
        st.sampled_from(_PLACES),
        _KINDS,
    ),
    max_size=8,
).map(dict)


def _subset(records: dict, keys) -> dict:
    return _strips({key: records[key] for key in keys})


@AUDIT_SETTINGS
@given(_live_records, st.data())
def test_audit_is_monotone_in_review_and_order_free(records, data) -> None:
    keys = sorted(records)
    subsets = st.lists(st.sampled_from(keys), unique=True) if keys else (
        st.just([])
    )
    chosen = data.draw(subsets, label="reviewed")
    more = data.draw(subsets, label="more reviewed")
    live, segments = _strips(records), _segments(records)
    audit = bsc.stripped_segment_review_problems
    fewer = audit(segments, live, _subset(records, chosen))
    most = audit(segments, live, _subset(records, set(chosen) | set(more)))
    assert set(most) <= set(fewer)  # A4
    assert audit(segments, live, live) == []  # A4
    assert fewer == sorted(fewer)  # A5

    def reverse(nested):
        if isinstance(nested, dict):
            return {k: reverse(nested[k]) for k in reversed(list(nested))}
        return nested

    shuffled_segments = {
        s: segments[s][::-1] for s in reversed(list(segments))
    }
    assert audit(
        shuffled_segments, reverse(live), reverse(
            _subset(records, chosen[::-1])
        )
    ) == fewer  # A5
    # A3: a reviewed strip that is not live is reported as gone.
    ghost_key = ("ghost.series", RID, "ghost.series.{P:fy9999}", "fy1999")
    ghost = _strips({
        **{key: records[key] for key in chosen}, ghost_key: {"derived"},
    })
    reported = _names(audit(segments, live, ghost), "fy1999", "ghost.series")
    assert len(reported) == 1 and "is gone" in reported[0]


@AUDIT_SETTINGS
@given(_live_records, st.data())
def test_audit_names_exactly_what_the_rule_names(records, data) -> None:
    """A6: a reference model of the rule, read straight off its statement,
    names the same (spelling, concept) pairs as the audit. Reviewed strips
    are drawn from the live ones (possibly with fewer kinds) plus strays
    that are not live, so every branch of the rule is exercised."""
    keys = sorted(records)
    chosen = data.draw(
        st.lists(st.sampled_from(keys), unique=True) if keys else st.just([]),
        label="reviewed",
    )
    reviewed = {}
    for key in chosen:
        kinds = sorted(records[key])
        reviewed[key] = frozenset(
            data.draw(st.sampled_from([kinds, kinds[:1]]), label="kinds")
        )
    strays = data.draw(_live_records, label="stray reviews")
    reviewed.update({k: v for k, v in strays.items() if k not in records})
    shapes = {key[:3] for key in reviewed}
    expected = set()
    for key, kinds in records.items():
        concept, _, _, spelling = key
        if key in reviewed:
            unreviewed = kinds - reviewed[key]
        else:
            unreviewed = (kinds - {"derived"}) or (
                set() if key[:3] in shapes else {"new shape"}
            )
        if unreviewed:
            expected.add((spelling, concept))
    expected |= {
        (spelling, concept)
        for concept, _, _, spelling in reviewed.keys() - records.keys()
    }
    problems = bsc.stripped_segment_review_problems(
        _segments(records), _strips(records), _strips(reviewed)
    )
    named = {
        (spelling, concept)
        for spelling, concept in _pairs(_segments({**records, **reviewed}))
        if _names(problems, spelling, concept)
    }
    assert named == expected
    assert len(problems) == len(set(problems))


def test_rebuild_without_prior_catalog_is_gated(
    tmp_path: pathlib.Path,
) -> None:
    # Deleting the committed catalog loses curated naming/alias memory: a
    # renamed identity would re-key away from its registry binding and
    # fresh-mint silently. The builder must treat a bare-registry rebuild
    # as an identity event.
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")])
    assert bsc.main(argv) == 0
    (tmp_path / "catalog.json").unlink()
    assert bsc.main(argv) == 1
    assert bsc.main(
        argv + ["--allow-remint", "--remint-note", "rebuild from registry"]
    ) == 0


def _mint(concept: str, uuid: str, geography=None, entity=None) -> dict:
    return {
        "concept": concept,
        "geography": geography,
        "entity": entity,
        "uuid": uuid,
    }


U1 = "aaaaaaaa-1111-4111-8111-111111111111"
U2 = "bbbbbbbb-2222-4222-8222-222222222222"


def test_mint_never_reuses_a_bound_uuid(tmp_path: pathlib.Path) -> None:
    # Third-review repro: re-key identities and swap their prior-catalog
    # UUIDs — both "new" identities would previously mint the swapped
    # values as ordinary mints.
    registry_entries = [
        _mint("old.one", U1, entity={"name": "economy", "role": "aggregate"}),
        _mint("old.two", U2, entity={"name": "economy", "role": "aggregate"}),
    ]
    existing = {
        "series": [
            {
                "uuid": U2,  # swapped
                "concept": "new.one",
                "geography": dict(US),
                "entity": {"name": "economy", "role": "aggregate"},
                "aliases": [],
                "status": "observed",
            },
            {
                "uuid": U1,  # swapped
                "concept": "new.two",
                "geography": dict(US),
                "entity": {"name": "economy", "role": "aggregate"},
                "aliases": [],
                "status": "observed",
            },
        ]
    }
    with pytest.raises(SystemExit, match=r"already knows \(first bound to"):
        _build(
            tmp_path,
            [_row("new.one"), _row("new.two")],
            existing=existing,
            registry_entries=registry_entries,
        )


def test_registry_rejects_forged_shared_uuid_mint(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "registry.jsonl"
    path.write_text(
        json.dumps(_mint("a.one", U1)) + "\n"
        + json.dumps(_mint("a.two", U1)) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="reuses uuid"):
        bsc.UuidRegistry.load(path)


def test_registry_rejects_duplicate_json_members(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "registry.jsonl"
    line = (
        '{"concept": "a.one", "geography": null, "entity": null, '
        f'"uuid": "{U1}", "uuid": "{U2}"}}'
    )
    path.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not strict JSON"):
        bsc.UuidRegistry.load(path)


def test_registry_requires_lf_discipline(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "registry.jsonl"
    body = json.dumps(_mint("a.one", U1))
    path.write_bytes(body.encode())  # no trailing newline
    with pytest.raises(SystemExit, match="end with a newline"):
        bsc.UuidRegistry.load(path)
    path.write_bytes(body.encode() + b"\r\n")
    with pytest.raises(SystemExit, match="LF-only"):
        bsc.UuidRegistry.load(path)


def test_registry_rejects_hollow_notes_and_noop_supersedes(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "registry.jsonl"
    mint = _mint("a.one", U1)
    hollow = dict(_mint("a.one", U2), supersedes=U1, note="​")
    path.write_text(
        json.dumps(mint) + "\n" + json.dumps(hollow) + "\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="substantive note"):
        bsc.UuidRegistry.load(path)
    noop = dict(_mint("a.one", U1), supersedes=U1, note="says nothing changed")
    path.write_text(
        json.dumps(mint) + "\n" + json.dumps(noop) + "\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="no-op"):
        bsc.UuidRegistry.load(path)


def test_agreement_is_identity_aware(tmp_path: pathlib.Path) -> None:
    # Rows carrying live UUIDs under the WRONG identities must fail even
    # though every UUID is "present somewhere" in the catalog.
    entries = [_mint("a.one", U1), _mint("a.two", U2)]
    registry = _registry(tmp_path, entries)
    catalog = {
        "series": [
            {"uuid": U1, "concept": "b.one", "geography": None, "entity": None},
            {"uuid": U2, "concept": "b.two", "geography": None, "entity": None},
        ]
    }
    problems = bsc.registry_agreement_problems(catalog, registry)
    assert sum("no catalog row at its identity" in p for p in problems) == 2


def test_enrichment_records_retire_and_succeeds_events(
    tmp_path: pathlib.Path,
) -> None:
    seed = {
        "series": [
            {
                "series": "census.m3.new_orders",
                "cadence": "monthly",
                "extras": {"country": "US", "targetUnit": "percent"},
            }
        ]
    }
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")], seed=seed)
    assert bsc.main(argv) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    placeholder_uuid = next(
        r["uuid"] for r in catalog["series"] if r["status"] == "docket-only"
    )
    (tmp_path / "obs.jsonl").write_text(
        "".join(
            json.dumps(r) + "\n"
            for r in [
                _row("bls.cps.unemployment_rate"),
                _row("census.m3.new_orders"),
            ]
        ),
        encoding="utf-8",
    )
    assert bsc.main(argv) == 0  # enrichment needs no ceremony flag
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    enriched = next(
        r for r in catalog["series"] if r["concept"] == "census.m3.new_orders"
    )
    assert enriched["status"] == "observed"
    assert enriched["uuid"] == placeholder_uuid
    lines = [
        json.loads(line)
        for line in (tmp_path / "registry.jsonl").read_text().splitlines()
    ]
    retire = next(line for line in lines if line.get("retired"))
    succeed = next(line for line in lines if line.get("succeeds"))
    assert retire["uuid"] == succeed["uuid"] == placeholder_uuid
    assert succeed["succeeds"]["concept"] == "census.m3.new_orders"
    assert bsc.main(argv + ["--check"]) == 0


def test_placeholder_with_conflicting_vintage_never_enriches(
    tmp_path: pathlib.Path,
) -> None:
    existing = {
        "series": [
            {
                "uuid": U1,
                "concept": "labour.rate",
                "geography": {"level": "country", "id": "0100000US",
                              "vintage": "2020"},
                "entity": None,
                "aliases": [],
                "status": "docket-only",
            }
        ]
    }
    catalog, plan = _build(
        tmp_path,
        [_row("labour.rate")],  # arrives with vintage "current"
        existing=existing,
        registry_entries=[
            _mint(
                "labour.rate",
                U1,
                geography={"level": "country", "id": "0100000US",
                           "vintage": "2020"},
            )
        ],
    )
    observed = next(r for r in catalog["series"] if r["status"] == "observed")
    assert observed["uuid"] != U1
    # The stranded placeholder binding is a gated retire, never silent.
    assert [e["uuid"] for e in plan["retire_pending"]] == [U1]


def test_docket_claim_is_dimension_scoped(tmp_path: pathlib.Path) -> None:
    gb_row = _row("boe.bank_rate", geography=dict(BRITAIN))
    us_entry = {
        "series": "boe.bank_rate",
        "cadence": "monthly",
        "extras": {"country": "US", "targetUnit": "percent"},
    }
    catalog, _ = _build(tmp_path, [gb_row], docket={"series": [us_entry]})
    assert len(catalog["series"]) == 2  # GB observed + US docket-only
    statuses = {
        (r["geography"] or {}).get("id"): r["status"] for r in catalog["series"]
    }
    assert statuses == {"GB": "observed", "0100000US": "docket-only"}

    undeclared = {"series": "boe.bank_rate", "cadence": "monthly"}
    catalog, _ = _build(tmp_path, [gb_row], docket={"series": [undeclared]})
    assert len(catalog["series"]) == 1  # no country claim: GB row claims

    with pytest.raises(SystemExit, match="duplicate docket series id"):
        _build(
            tmp_path,
            [gb_row],
            docket={"series": [undeclared, dict(undeclared)]},
        )


def test_statute_spelling_stripped_but_audited(
    tmp_path: pathlib.Path,
) -> None:
    # A statute/edition label spelling the row's own period is
    # indistinguishable from a period label; it strips, but the spelling
    # is published — mapped to every canonical concept it touched, so a
    # second occurrence is visible rather than absorbed into a set.
    catalog, _ = _build(
        tmp_path,
        [
            _row("agency.statute.2026_05.rate",
                 rid="agency.statute.2026_05.rate.first_print"),
            _row("other.report.2026_05.level",
                 rid="other.report.2026_05.level.first_print"),
        ],
    )
    concepts = {r["concept"] for r in catalog["series"]}
    assert concepts == {"agency.statute.rate", "other.report.level"}
    assert catalog["stripped_segments"]["2026_05"] == [
        "agency.statute.rate", "other.report.level",
    ]


@pytest.mark.parametrize(
    "period",
    [
        {"type": "month", "value": "2026-13"},
        {"type": "quarter", "value": "2026-13"},
        {"type": "week_ending", "value": "2026-13-40"},
    ],
)
def test_malformed_periods_are_hard_errors(
    tmp_path: pathlib.Path, period: dict
) -> None:
    with pytest.raises(SystemExit, match="malformed period"):
        _build(tmp_path, [_row("agency.rate", period=period)])


def test_remint_of_retired_identity_stages_valid_chain(
    tmp_path: pathlib.Path,
) -> None:
    # Third-review repro: retire an identity, then bring it back with an
    # edited prior-catalog UUID under --allow-remint. The writer must
    # stage revive THEN supersede (a valid chain) — and staging always
    # revalidates the whole registry before anything is written.
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")])
    assert bsc.main(argv) == 0
    (tmp_path / "seed.json").write_text(
        json.dumps({"series": []}), encoding="utf-8"
    )
    assert bsc.main(
        argv + ["--allow-remint", "--remint-note", "seed entry cut"]
    ) == 0
    (tmp_path / "seed.json").write_text(json.dumps(SEED), encoding="utf-8")
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    # Hand-plant a divergent uuid for the returning docket identity.
    replacement = "cccccccc-3333-4333-8333-333333333333"
    lines = (tmp_path / "registry.jsonl").read_text().splitlines()
    retired_uuid = json.loads(lines[-1])["uuid"]
    catalog["series"].append(
        {
            "uuid": replacement,
            "concept": "abs.labour.unemployment_rate",
            "geography": bsc.COUNTRY_GEOGRAPHY["AU"],
            "entity": None,
            "aliases": [],
            "status": "docket-only",
        }
    )
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    assert bsc.main(argv) == 1  # gated
    assert (
        bsc.main(argv + ["--allow-remint", "--remint-note", "planned swap"])
        == 0
    )
    events = [
        json.loads(line)
        for line in (tmp_path / "registry.jsonl").read_text().splitlines()
    ]
    revive = events[-2]
    supersede = events[-1]
    assert revive["revived"] is True and revive["uuid"] == retired_uuid
    assert supersede["supersedes"] == retired_uuid
    assert supersede["uuid"] == replacement
    # The staged file reloads cleanly and the catalog checks green.
    bsc.UuidRegistry.load(tmp_path / "registry.jsonl")
    assert bsc.main(argv + ["--check"]) == 0


def test_identity_uuid_map_matches_reviewed_anchor() -> None:
    """The registry's introduction commit cannot be continuity-checked by
    the append-only gate (there is no prior registry to extend), so the
    identity->uuid map verified by the adversarial review of PR #128 is
    pinned here. Changing any live binding — or adding or retiring one —
    must edit this constant in the same diff, making wholesale remints
    impossible to slip through as regeneration noise.

    Update the constant only alongside registry events that justify it.
    """
    import hashlib

    catalog = json.loads(bsc.CATALOG.read_text(encoding="utf-8"))
    lines = sorted(
        json.dumps(
            [
                row["uuid"],
                row["concept"],
                bsc._geo_key(row.get("geography")),
                bsc._entity_key(row.get("entity")),
            ]
        )
        for row in catalog["series"]
    )
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    # Updated 2026-08-05 alongside five registry events: two docket
    # placeholders enriched by their first observations (retire+succeeds,
    # UUIDs preserved: bls.jolts.hires_rate,
    # census.construction_spending.total_mom) and one fresh mint
    # (irs.actc.total_claims docket placeholder). 201 prior bindings all
    # unchanged.
    # Updated 2026-08-06 alongside one registry mint: the Thesis docket
    # registered census.spm.child_poverty_rate; its placeholder joins the
    # seed snapshot. All 205 prior bindings unchanged.
    # Updated 2026-08-07: +6 docket-only mints for thesis#138 wave-1
    # admission (bea fixed-investment x2, usaspending dhs title-vi, irs soi
    # 30D claims+amount, irs actc amount) — see that commit's seed diff.
    # Updated 2026-08-07: three same-dimension concept-spelling duplicates
    # retired and folded into surviving lineages; 209 live bindings became
    # 206 without changing any surviving UUID.
    # Updated 2026-08-08: +3 docket-only mints for the thesis SBA
    # custody-family admission (sba.disaster.loan_program charge-off
    # amount, charge-off rate on UPB, post-charge-off recovery —
    # thesis#145); builder reported minted=3, superseded=0, suspects=0,
    # so all 206 prior bindings are unchanged.
    # Updated 2026-08-09 alongside ten registry events: five docket
    # placeholders enriched by their first recorded observations
    # (retire+succeeds pairs, UUIDs preserved:
    # bls.cps.u6_underemployment_rate,
    # bls.productivity.nonfarm_unit_labor_costs_qoq_prelim, and the three
    # fed.g19 consumer-credit annual rates). No fresh UUIDs, no
    # supersedes; builder reported minted=5 (all succeeds), superseded=0,
    # suspects=0. The other 204 bindings are byte-unchanged; row count
    # stays 209.
    # Updated 2026-08-11: +7 mints, superseded=0, suspects=0, all 209
    # prior bindings unchanged (209 -> 216). Four docket-only
    # placeholders for the thesis bills full-coverage wave's in-review
    # usaspending-api extensions (thesis#159 Wave A verified requests;
    # implementation, tests, anchors, and docket admission were still
    # outstanding at mint time),
    # with the defining filter carried in each concept identity so a
    # differently filtered series can never enrich these lineages:
    # usaspending.cdfi.assistance_transaction_obligations,
    # usaspending.ondcp.hidta_al95001_obligations,
    # usaspending.ntia.broadband_al11038_obligations, and
    # usaspending.usfs.minnesota_place_of_performance_obligations
    # (country-level geography by seed-schema design; the Minnesota
    # place-of-performance scope lives in the concept string, so a
    # future state-geography series is a distinct identity). Plus the
    # three observed BLS CES defense-employment identities whose first
    # prints were recorded 2026-08-10 ahead of their catalog rows
    # (aerospace_product_and_parts, federal_department_of_defense,
    # ship_and_boat_building employment) — deterministic auto-mints any
    # next build would produce.
    # Updated 2026-08-12: +2 docket-only mints for the Thesis Wave B3
    # BLS QCEW U.S.-private NAICS 624410 annual-average employment
    # admission and the exact BEA ITA Table 5.1 line 18 QSA
    # personal-transfer-payments identity. The BEA source-linked seed makes
    # clear that only future release-day custody can enrich it; all 216 prior
    # live bindings remain unchanged (216 -> 218).
    # Updated 2026-08-13 alongside two registry events: the docket-only
    # usaspending.dod.prime_award_obligations placeholder gains its declared
    # U.S. country geography through a retire+succeeds pair, preserving its
    # UUID. The other 217 live bindings are unchanged; row count stays 218.
    # Updated 2026-08-13 alongside one registry mint: the Thesis FLARE Act
    # context admission adds the U.S. annual EIA N9040US2 vented-and-flared
    # identity in million cubic feet. All 218 prior live bindings are
    # unchanged (218 -> 219).
    # Updated 2026-09-04 to the catalog at 55bbf3d, six resolve_pending.py
    # waves after the previous pin: c2aa68d (2026-08-23, manifest
    # 0015-fdcfd0e570214f6b), 54dbabc8 (0016-5226191699ae168d), 734beb8
    # (0017-efa7d60fece304f7), 9526211 (0018-20974a5bdeeace01), d77afe2
    # (0019-01d2f0bfb2ebff75) and 55bbf3d (2026-09-03,
    # 0020-7f669f1e1364c5cc); 0018 and 0019 changed occurrences and
    # aliases only, so the anchor tuples are identical from 734beb8 through
    # d77afe2. Recomputed per commit
    # with this test's algorithm, the previous pin was exact at c2aa68d^ and
    # the delta to 55bbf3d is nine mints from first observed identities, all
    # at c2aa68d (bls.ces.home_health_care_services.employment,
    # bls.cps.LNU02374597, bls.cps.lfpr_55_plus,
    # bls.laus.colorado.labor_force, ssa.oasdi.disabled_worker_beneficiaries,
    # ssa.ssi.recipients.colorado, ssa.ssi.recipients.colorado.aged_65_plus,
    # ssa.ssi.recipients_aged_65_plus, va.vba.mmwr.claims_inventory), plus
    # eight docket placeholders enriched by their first observed identity
    # through retire-and-reissue pairs that preserve the UUID and take the
    # observation's U.S. country geography and economy aggregate entity: six
    # at c2aa68d (bls.export_prices.all_commodities_mom,
    # census.housing.completions_saar, census.housing.permits_saar,
    # fed.g17.capacity_utilization.manufacturing,
    # fed.g17.manufacturing_production_mom, ssa.ssi.total_recipients),
    # census.new_residential_sales.new_single_family_houses_sold_saar at
    # 734beb8 and bea.trade.goods_services_deficit at 55bbf3d. Geography and
    # entity on all seventeen rows are copied from the observation payload
    # (the seed rows carry no country or entity; the docket-only country path
    # is not involved), which is why the three Colorado-named concepts carry
    # country-level geography: the observations were recorded that way. The
    # other 211 live bindings are byte-unchanged (219 -> 228).
    # Updated 2026-10-12 alongside seven registry retire events (Max's
    # ruling d353, ledger/seeds/entity_folds.json): the entity-drift families
    # of docs/catalog-curation-backlog.md fold into their economy/aggregate
    # lineages. Retired, with their rows' observations joining the survivor:
    # 8dbbd54f (bls.cps.unemployment_rate person/civilian_labor_force),
    # 3e796803 (bls.cpi.u.headline_mom household/cpi_u_all_items), d85c3c7f
    # (bls.cpi.u.core_mom household/cpi_u_less_food_energy), e8e6e43e
    # (bls.import_price_index.all_imports_mom household/all_imports),
    # d0212a1e (census.housing_starts.saar dwelling/housing_start), 978252a9
    # (fed.g17.capacity_utilization.total_industry institutional_sector) and
    # d5634fc4 (fed.g17.industrial_production.total_index_mom
    # institutional_sector). No mint, no supersede; the other 221 live
    # bindings keep their UUIDs (228 -> 221).
    # Updated 2026-10-18 to the catalog at dd929cba (chronicle#361, manifest
    # 0024-b2328c1685c09fd7) alongside its ten registry events: five
    # geography-free docket placeholders enriched by their FY2026 first
    # prints through retire+succeeds pairs that keep each UUID and take the
    # observation's U.S. country (vintage current) geography and economy
    # aggregate entity: usaspending.dod.new_prime_awards (8146ecb0),
    # prime_award_transactions (82ff2d7f), prime_contract_obligations
    # (11ea0d3d), small_business_contract_obligation_share (91e3b668) and
    # unique_prime_contract_recipients (96d17026). Recomputed with this
    # test's algorithm, 8c4a0f86 gives the previous pin exactly and the delta
    # to dd929cba is those five tuples re-keyed with the same UUIDs. No mint,
    # no supersede; the other 216 bindings are unchanged; 221 rows.
    # Updated 2026-10-19 to the catalog at 61475bf8 (chronicle#369, Thesis
    # resolver run 39198762190) alongside its ten registry events: five more
    # geography-free docket placeholders enriched by their FY2026 first
    # prints through retire+succeeds pairs that keep each UUID and take the
    # observation's U.S. country (vintage current) geography and economy
    # aggregate entity: usaspending.cdfi.assistance_transaction_obligations
    # (69834e1f), dhs.title_vi.award_transaction_obligations (e64ea5db),
    # dod.prime_award_obligations (a2649fd9), ntia.broadband_al11038_obligations
    # (f37307e0) and usfs.minnesota_place_of_performance_obligations
    # (720be189). Recomputed with this test's algorithm, 7adcc72f gives the
    # previous pin exactly and the delta to 61475bf8 is those five tuples
    # re-keyed with the same UUIDs. No mint, no supersede; the other 216
    # bindings are unchanged; 221 rows.
    assert digest == (
        "d5b88530f3f0c9e709dc0a0d379302db539d2600f76f60ed7fdd83f7474e5eef"
    )


def test_supersede_never_recycles_a_historical_uuid(
    tmp_path: pathlib.Path,
) -> None:
    # Fourth-review repro: U1 -> U2 -> U1 restored the original map while
    # hiding the excursion in two "valid" events.
    path = tmp_path / "registry.jsonl"
    mint = _mint("a.one", U1)
    away = dict(_mint("a.one", U2), supersedes=U1, note="planned change one")
    back = dict(_mint("a.one", U1), supersedes=U2, note="planned change two")
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in (mint, away, back)),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="recycles uuid"):
        bsc.UuidRegistry.load(path)


def test_succeeds_lineage_is_consumed_once_and_dimension_bound(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "registry.jsonl"
    mint = _mint("a.one", U1)
    retire = dict(_mint("a.one", U1), retired=True, note="placeholder done")
    succ = {"concept": "a.one", "geography": None, "entity": None}

    def entry(concept, uuid, **kw):
        return dict(_mint(concept, uuid), **kw)

    # Fork: two successors of one predecessor.
    b = entry("a.one", U1, succeeds=succ,
              entity={"name": "economy", "role": "aggregate"})
    b_away = dict(
        entry("a.one", U2, entity={"name": "economy", "role": "aggregate"}),
        supersedes=U1, note="moved along again",
    )
    c = entry("a.one", U1, succeeds=succ,
              entity={"name": "person", "role": "aggregate"})
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in (mint, retire, b, b_away, c)),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="consumed exactly once"):
        bsc.UuidRegistry.load(path)

    # Cross-concept lineage transfer.
    other = entry("b.two", U1, succeeds=succ)
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in (mint, retire, other)),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="never crosses concepts"):
        bsc.UuidRegistry.load(path)

    # Predecessor with a known entity is not a placeholder.
    known = _mint("a.one", U1,
                  entity={"name": "economy", "role": "aggregate"})
    known_retire = dict(known, retired=True, note="placeholder done")
    successor = entry(
        "a.one", U1,
        succeeds={"concept": "a.one", "geography": None,
                  "entity": {"name": "economy", "role": "aggregate"}},
    )
    path.write_text(
        "".join(
            json.dumps(e) + "\n" for e in (known, known_retire, successor)
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="entity-less placeholders"):
        bsc.UuidRegistry.load(path)


def test_literal_placeholder_segment_is_reserved(
    tmp_path: pathlib.Path,
) -> None:
    with pytest.raises(SystemExit, match="reserved placeholder"):
        _build(tmp_path, [_row("agency.statute.{P}.rate")])
    with pytest.raises(SystemExit, match="reserved placeholder"):
        _build(
            tmp_path,
            [_row("agency.rate", rid="agency.rate.{P}.first_print")],
        )
    # Strip shapes write a stripped segment as {P:<template>}; a literal
    # one would let a kept segment pass for a stripped one.
    with pytest.raises(SystemExit, match="reserved placeholder"):
        _build(tmp_path, [_row("agency.{P:9999_99}.rate")])
    with pytest.raises(SystemExit, match="reserved placeholder"):
        _build(
            tmp_path,
            [_row("agency.rate", rid="agency.rate.{P:fy9999}.first_print")],
        )
    # Braces elsewhere are ordinary characters.
    catalog, _ = _build(tmp_path, [_row("agency.{Q}.rate")])
    assert "agency.{Q}.rate" in {row["concept"] for row in catalog["series"]}


@pytest.mark.parametrize(
    "segment",
    ["fy0000", "fy0001", "0000_01", "week_ending_0001_01_01", "q1_0000",
     "9999_13", "3100_13"],
)
def test_out_of_window_calendar_tokens_kept_and_flagged(
    segment: str,
) -> None:
    assert bsc.parse_period_token(segment) is None
    pattern = bsc.family_pattern(
        f"agency.rate.{segment}", {"type": "month", "value": "2026-05"}
    )
    assert pattern == f"agency.rate.{segment}"
    # Period-SHAPED but unparseable: always a suspect, even outside the
    # year-hint window.
    assert bsc.suspect_segments(pattern) == [segment]


def test_bare_year_variant_strips_only_for_annual_rows(
    tmp_path: pathlib.Path,
) -> None:
    rows = [
        _row("agency.annual.total.2025",
             rid="agency.annual.total.2025.final",
             period={"type": "year", "value": "2025"}),
        _row("agency.annual.total.2026",
             rid="agency.annual.total.2026.final",
             period={"type": "year", "value": "2026"}),
    ]
    catalog, _ = _build(tmp_path, rows)
    assert [r["concept"] for r in catalog["series"]] == [
        "agency.annual.total"
    ]
    assert catalog["series"][0]["observation_count"] == 2
    # A bare year that is NOT the row's own period never strips.
    pattern = bsc.family_pattern(
        "agency.annual.total.2019", {"type": "year", "value": "2025"}
    )
    assert pattern == "agency.annual.total.2019"


def test_consumed_lineage_is_terminal(tmp_path: pathlib.Path) -> None:
    # Fifth-review repro: retire A -> B succeeds A -> B moves to U2 ->
    # retire B -> revive A restored the banned U1 excursion via detour.
    path = tmp_path / "registry.jsonl"
    succ = {"concept": "a.one", "geography": None, "entity": None}
    events = [
        _mint("a.one", U1),
        dict(_mint("a.one", U1), retired=True, note="placeholder done"),
        dict(_mint("a.one", U1), succeeds=succ,
             entity={"name": "economy", "role": "aggregate"}),
        dict(_mint("a.one", U2,
                   entity={"name": "economy", "role": "aggregate"}),
             supersedes=U1, note="moved along deliberately"),
        dict(_mint("a.one", U2,
                   entity={"name": "economy", "role": "aggregate"}),
             retired=True, note="successor done too"),
        dict(_mint("a.one", U1), revived=True),
    ]
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="terminal"):
        bsc.UuidRegistry.load(path)


def test_builder_mints_fresh_for_consumed_identity(
    tmp_path: pathlib.Path,
) -> None:
    # Observations reappearing under a handed-over identity are a NEW
    # series claim: fresh uuid, no revival of the terminal lineage.
    succ = {"concept": "census.m3.new_orders", "geography": None,
            "entity": None}
    entries = [
        _mint("census.m3.new_orders", U1),
        dict(_mint("census.m3.new_orders", U1), retired=True,
             note="placeholder enriched"),
        dict(_mint("census.m3.new_orders", U1), succeeds=succ,
             geography={"level": "country", "id": "0100000US",
                        "vintage": "current"},
             entity={"name": "economy", "role": "aggregate"}),
    ]
    rows = [
        _row("census.m3.new_orders"),
        _row("census.m3.new_orders",
             geography=None if False else {"level": "country", "id": "GB",
                                           "vintage": "current"},
             rid="census.m3.new_orders.gb.first_print"),
    ]
    catalog, plan = _build(tmp_path, rows, registry_entries=entries)
    us_row = next(
        r for r in catalog["series"]
        if (r["geography"] or {}).get("id") == "0100000US"
    )
    gb_row = next(
        r for r in catalog["series"]
        if (r["geography"] or {}).get("id") == "GB"
    )
    assert us_row["uuid"] == U1  # the enriched successor identity
    assert gb_row["uuid"] not in (U1, U2)  # fresh, never the old lineage
    assert len(plan["revives"]) == 0


def test_live_uuid_uniqueness_holds_per_event_prefix(
    tmp_path: pathlib.Path,
) -> None:
    # Two live holders of one uuid mid-sequence must fail even if a later
    # event would "fix" the final state.
    path = tmp_path / "registry.jsonl"
    events = [
        _mint("a.one", U1),
        _mint("a.two", U2),
        # a.two jumps onto U1 while a.one still holds it live...
        dict(_mint("a.two", U1), supersedes=U2, note="deliberate theft"),
        # ...and a.one is retired only afterwards.
        dict(_mint("a.one", U1), retired=True, note="too late to matter"),
    ]
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="after every event"):
        bsc.UuidRegistry.load(path)


def test_reserved_placeholder_rejected_in_docket_and_registry(
    tmp_path: pathlib.Path,
) -> None:
    with pytest.raises(SystemExit, match="reserved placeholder"):
        _build(
            tmp_path,
            [_row("agency.rate")],
            docket={"series": [{"series": "agency.{P}.rate",
                                "cadence": "monthly"}]},
        )
    path = tmp_path / "registry.jsonl"
    path.write_text(
        json.dumps(_mint("agency.{P}.rate", U1)) + "\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="reserved placeholder"):
        bsc.UuidRegistry.load(path)


def test_registry_rejects_json_constants_and_empty_dimensions(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "registry.jsonl"
    nan_line = (
        '{"concept": "a.one", "geography": {"level": "country", '
        f'"id": "US", "vintage": NaN}}, "entity": null, "uuid": "{U1}"}}'
    )
    path.write_text(nan_line + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not strict JSON"):
        bsc.UuidRegistry.load(path)
    empty_vintage = _mint(
        "a.one", U1,
        geography={"level": "country", "id": "US", "vintage": ""},
    )
    path.write_text(json.dumps(empty_vintage) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="nonempty string or null"):
        bsc.UuidRegistry.load(path)


def test_observation_dimension_domains_are_enforced(
    tmp_path: pathlib.Path,
) -> None:
    bad = _row("agency.rate")
    bad["geography"] = {"level": "country", "id": "0100000US", "vintage": ""}
    with pytest.raises(SystemExit, match="nonempty string or null"):
        _build(tmp_path, [bad])


@pytest.mark.parametrize(
    ("identifier", "period"),
    [
        ("agency.rate.january_1899", MONTH_2026_06),
        ("agency.rate.january_3000", MONTH_2026_06),
    ],
)
def test_boundary_year_month_names_neither_strip_nor_crash(
    identifier: str, period: dict
) -> None:
    assert bsc.family_pattern(identifier, period) == identifier


@pytest.mark.parametrize("value", ["1899-01", "3000-01"])
def test_out_of_window_quarter_periods_are_malformed(
    tmp_path: pathlib.Path, value: str
) -> None:
    with pytest.raises(SystemExit, match="malformed period"):
        _build(
            tmp_path,
            [_row("agency.rate", period={"type": "quarter", "value": value})],
        )


@pytest.mark.parametrize("segment", ["1899_13", "2999_13", "3000_13"])
def test_out_of_window_impossible_tokens_are_flagged(segment: str) -> None:
    pattern = bsc.family_pattern(f"agency.rate.{segment}", MONTH_2026_06)
    assert pattern == f"agency.rate.{segment}"
    assert bsc.suspect_segments(pattern) == [segment]


def test_reclaimed_mint_grammar(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "registry.jsonl"
    succ = {"concept": "a.one", "geography": None, "entity": None}
    base = [
        _mint("a.one", U1),
        dict(_mint("a.one", U1), retired=True, note="placeholder done"),
        dict(_mint("a.one", U1), succeeds=succ,
             entity={"name": "economy", "role": "aggregate"}),
    ]
    fresh = "dddddddd-4444-4444-8444-444444444444"
    good = dict(_mint("a.one", fresh), reclaimed=True,
                note="re-established after handover")
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in base + [good]),
        encoding="utf-8",
    )
    registry = bsc.UuidRegistry.load(path)
    assert registry.binding(("a.one", bsc._geo_key(None),
                             bsc._entity_key(None))) == fresh
    # Reclaim of a merely-retired (not consumed) key is invalid.
    unconsumed = [
        _mint("b.two", U2),
        dict(_mint("b.two", U2), retired=True, note="ordinary retirement"),
        dict(_mint("b.two", fresh), reclaimed=True,
             note="not a handover case"),
    ]
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in unconsumed), encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="not handed over"):
        bsc.UuidRegistry.load(path)
    # Reclaim must mint fresh, never reuse.
    reuse = dict(_mint("a.one", U1), reclaimed=True,
                 note="tries to take U1 back")
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in base + [reuse]),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="mints fresh"):
        bsc.UuidRegistry.load(path)


def test_consumed_key_reclaims_fresh_lineage(tmp_path: pathlib.Path) -> None:
    # Sixth-review repro: a docket entry re-forming a handed-over key must
    # take an explicit reclaim path (previously it staged a markerless
    # mint that its own validator rejected).
    succ = {"concept": "census.m3.new_orders", "geography": None,
            "entity": None}
    entries = [
        _mint("census.m3.new_orders", U1),
        dict(_mint("census.m3.new_orders", U1), retired=True,
             note="placeholder enriched"),
        dict(_mint("census.m3.new_orders", U1), succeeds=succ,
             geography={"level": "country", "id": "0100000US",
                        "vintage": "current"},
             entity={"name": "economy", "role": "aggregate"}),
        _mint("bls.cps.unemployment_rate", U2,
              geography={"level": "country", "id": "0100000US",
                         "vintage": "current"},
              entity={"name": "economy", "role": "aggregate"}),
    ]
    existing = {
        "series": [
            {
                "uuid": U2,
                "concept": "bls.cps.unemployment_rate",
                "geography": dict(US),
                "entity": {"name": "economy", "role": "aggregate"},
                "aliases": [],
                "status": "observed",
            }
        ]
    }
    observations = tmp_path / "obs.jsonl"
    observations.write_text(
        json.dumps(_row("bls.cps.unemployment_rate")) + "\n",
        encoding="utf-8",
    )
    docket_path = tmp_path / "seed.json"
    docket_path.write_text(
        json.dumps({"series": [{"series": "census.m3.new_orders",
                                "cadence": "monthly"}]}),
        encoding="utf-8",
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(existing) + "\n", encoding="utf-8")
    registry = _registry(tmp_path, entries)
    catalog, plan = bsc.build_catalog(
        observations, docket_path, bsc.ExistingCatalog(catalog_path), registry
    )
    docket_row = next(
        r for r in catalog["series"] if r["status"] == "docket-only"
    )
    assert docket_row["uuid"] != U1  # fresh lineage, old uuid stays put
    reclaim = next(e for e in plan["mints"] if e.get("reclaimed"))
    assert reclaim["uuid"] == docket_row["uuid"]
    # The enriched identity has no row in this synthetic catalog, so its
    # live binding is a gated retire — and the staged whole must reload.
    staged = registry.stage(
        plan["enrich_retires"] + plan["mints"] + plan["revives"]
        + plan["supersedes"]
        + [dict(e, note="synthetic gate approval")
           for e in plan["retire_pending"]]
    )
    assert staged.entries[-1] is not None


def test_docket_seed_rejects_json_constants(tmp_path: pathlib.Path) -> None:
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")])
    (tmp_path / "seed.json").write_text(
        '{"series": [{"series": "a.b", "cadence": "monthly", '
        '"extras": {"valueScale": NaN}}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not allowed"):
        bsc.main(argv)


def test_observation_duplicate_members_rejected(
    tmp_path: pathlib.Path,
) -> None:
    row = _row("agency.rate")
    line = json.dumps(row)
    line = line.replace(
        '"geography": {', '"geography": {"level": "state", ', 1
    )
    observations = tmp_path / "obs.jsonl"
    observations.write_text(
        line.replace('"geography": {"level": "state", "level"',
                     '"geography": {"level": "state", "level"') + "\n",
        encoding="utf-8",
    )
    registry = _registry(tmp_path)
    with pytest.raises(ValueError, match="duplicate JSON member"):
        bsc.build_catalog(
            observations, None,
            bsc.ExistingCatalog(tmp_path / "catalog.json"), registry,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("geography", ""), ("geography", []), ("entity", []), ("entity", "x")],
)
def test_falsey_or_nonobject_dimensions_rejected(
    tmp_path: pathlib.Path, field: str, value
) -> None:
    bad = _row("agency.rate")
    bad[field] = value
    with pytest.raises(SystemExit, match="must be an object or null"):
        _build(tmp_path, [bad])


def test_succeeds_schema_is_enforced(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "registry.jsonl"
    base = [
        _mint("a.one", U1),
        dict(_mint("a.one", U1), retired=True, note="placeholder done"),
    ]
    forged = dict(
        _mint("a.one", U1, entity={"name": "economy", "role": "aggregate"}),
        succeeds={"concept": "a.one", "geography": None, "entity": None,
                  "extra": "field"},
    )
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in base + [forged]),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="non-identity fields"):
        bsc.UuidRegistry.load(path)
    bad_geo = dict(
        _mint("a.one", U1, entity={"name": "economy", "role": "aggregate"}),
        succeeds={"concept": "a.one",
                  "geography": {"level": "country", "id": ""},
                  "entity": None},
    )
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in base + [bad_geo]),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="nonempty string or null"):
        bsc.UuidRegistry.load(path)


def test_registry_rejects_hidden_line_separators(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "registry.jsonl"
    two_on_one = (
        json.dumps(_mint("a.one", U1))
        + " "
        + json.dumps(_mint("a.two", U2))
    )
    path.write_text(two_on_one + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not strict JSON"):
        bsc.UuidRegistry.load(path)
    with_vt = (
        json.dumps(_mint("a.one", U1))
        + "\x0b"
        + json.dumps(_mint("a.two", U2))
    )
    path.write_bytes(with_vt.encode("utf-8") + b"\n")
    with pytest.raises(SystemExit, match="not strict JSON"):
        bsc.UuidRegistry.load(path)


def test_reclaim_restores_ordinary_lineage(tmp_path: pathlib.Path) -> None:
    # Seventh-review repro: consumption used to be permanent, so every
    # later re-add of a reclaimed key minted ANOTHER fresh uuid without
    # ceremony. A reclaimed identity is ordinary again: drops retire
    # (gated) and returns REVIVE the same uuid.
    path = tmp_path / "registry.jsonl"
    succ = {"concept": "a.one", "geography": None, "entity": None}
    fresh = "dddddddd-4444-4444-8444-444444444444"
    events = [
        _mint("a.one", U1),
        dict(_mint("a.one", U1), retired=True, note="placeholder done"),
        dict(_mint("a.one", U1), succeeds=succ,
             entity={"name": "economy", "role": "aggregate"}),
        dict(_mint("a.one", fresh), reclaimed=True,
             note="re-established after handover"),
        dict(_mint("a.one", fresh), retired=True,
             note="approved retirement"),
        dict(_mint("a.one", fresh), revived=True),
    ]
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )
    registry = bsc.UuidRegistry.load(path)
    key = ("a.one", bsc._geo_key(None), bsc._entity_key(None))
    assert registry.binding(key) == fresh and registry.is_live(key)
    # A SECOND reclaim after the revival is invalid: nothing was handed
    # over the second time.
    second = "eeeeeeee-5555-4555-8555-555555555555"
    bad = events[:5] + [dict(_mint("a.one", second), reclaimed=True,
                             note="tries to churn again")]
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in bad), encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="not handed over"):
        bsc.UuidRegistry.load(path)


def test_first_event_reclaim_marker_is_rejected(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "registry.jsonl"
    stray = dict(_mint("a.one", U1), reclaimed=True,
                 note="no predecessor at all")
    path.write_text(json.dumps(stray) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no prior binding"):
        bsc.UuidRegistry.load(path)
    false_marker = dict(_mint("b.two", U2), reclaimed=False)
    path.write_text(json.dumps(false_marker) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no prior binding"):
        bsc.UuidRegistry.load(path)


def test_succeeds_missing_concept_is_a_schema_finding(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "registry.jsonl"
    base = [
        _mint("a.one", U1),
        dict(_mint("a.one", U1), retired=True, note="placeholder done"),
    ]
    headless = dict(
        _mint("a.one", U1, entity={"name": "economy", "role": "aggregate"}),
        succeeds={"geography": None, "entity": None},
    )
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in base + [headless]),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="nonempty string"):
        bsc.UuidRegistry.load(path)


def test_incomplete_geography_never_merges_places(
    tmp_path: pathlib.Path,
) -> None:
    # Seventh-review repro: two countries with null ids collapsed into one
    # identity showing only the first name.
    us = _row("trade.balance")
    us["geography"] = {"level": "country", "id": None, "vintage": "current",
                       "name": "United States"}
    with pytest.raises(SystemExit, match="geography.id is required"):
        _build(tmp_path, [us])
    entityless = _row("trade.balance")
    entityless["entity"] = {"name": "economy", "role": None}
    with pytest.raises(SystemExit, match="entity.role is required"):
        _build(tmp_path, [entityless])
    registry_path = tmp_path / "registry.jsonl"
    registry_path.write_text(
        json.dumps(
            _mint("trade.balance", U1,
                  geography={"level": "country", "id": None,
                             "vintage": "current"})
        ) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="geography.id is required"):
        bsc.UuidRegistry.load(registry_path)


def test_observation_hidden_separators_rejected(
    tmp_path: pathlib.Path,
) -> None:
    two_on_one = (
        json.dumps(_row("agency.rate"))
        + " "
        + json.dumps(_row("agency.other"))
    )
    observations = tmp_path / "obs.jsonl"
    observations.write_text(two_on_one + "\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        bsc.build_catalog(
            observations, None,
            bsc.ExistingCatalog(tmp_path / "catalog.json"),
            _registry(tmp_path),
        )


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda r: r["period"].update(type="decade"), "unknown period type"),
        (lambda r: r["period"].update(value=None), "period.value is required"),
        (lambda r: r.update(period="2026-05"), "period must be an object"),
        (lambda r: r["measure"].update(unit=7), "measure.unit"),
        (lambda r: r["source"].update(source_name=""), "source.source_name"),
    ],
)
def test_observation_schema_floors(tmp_path: pathlib.Path, mutate, match):
    row = _row("agency.rate")
    mutate(row)
    with pytest.raises(SystemExit, match=match):
        _build(tmp_path, [row])


def test_docket_extras_must_be_an_object(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SystemExit, match="extras must be an object"):
        _build(
            tmp_path,
            [_row("agency.rate")],
            docket={"series": [{"series": "some.series",
                                "cadence": "monthly", "extras": ""}]},
        )


@pytest.mark.parametrize("field", ["geography", "entity"])
def test_empty_dimension_object_never_spells_null(
    tmp_path: pathlib.Path, field: str
) -> None:
    # Eighth-review repro: null vs {} pairs collapsed into one identity.
    bad = _row("trade.balance")
    bad[field] = {}
    with pytest.raises(SystemExit, match="never an empty object"):
        _build(tmp_path, [bad])
    registry_path = tmp_path / "registry.jsonl"
    registry_path.write_text(
        json.dumps(dict(_mint("trade.balance", U1), **{field: {}})) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="never an empty object"):
        bsc.UuidRegistry.load(registry_path)


def test_empty_period_object_rejected(tmp_path: pathlib.Path) -> None:
    bad = _row("agency.rate")
    bad["period"] = {}
    with pytest.raises(SystemExit, match="never an empty object"):
        _build(tmp_path, [bad])


def test_docket_shape_floors(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SystemExit, match="docket.series must be a list"):
        _build(tmp_path, [_row("agency.rate")], docket={"series": {}})
    with pytest.raises(SystemExit, match="docket.series must be a list"):
        _build(tmp_path, [_row("agency.rate")], docket={"series": ""})
    with pytest.raises(SystemExit, match="nonempty string 'series'"):
        _build(tmp_path, [_row("agency.rate")], docket={"series": [{}]})
    with pytest.raises(SystemExit, match="targetUnit must be a nonempty"):
        _build(
            tmp_path,
            [_row("agency.rate")],
            docket={"series": [{"series": "a.b", "cadence": "monthly",
                                "extras": {"targetUnit": {"u": "x"}}}]},
        )


def test_source_concept_value_floor(tmp_path: pathlib.Path) -> None:
    bad = _row("agency.rate")
    bad["measure"]["source_concept"] = ""
    with pytest.raises(SystemExit, match="source_concept must be a nonempty"):
        _build(tmp_path, [bad])
    typed = _row("agency.rate")
    typed["measure"]["source_concept"] = 7
    with pytest.raises(SystemExit, match="source_concept must be a nonempty"):
        _build(tmp_path, [typed])


def test_render_entry_refuses_malformed_events() -> None:
    with pytest.raises(ValueError, match="must be literally true"):
        bsc.UuidRegistry.render_entry(
            dict(_mint("a.one", U1), reclaimed=False)
        )
    with pytest.raises(ValueError, match="mixes markers"):
        bsc.UuidRegistry.render_entry(
            dict(_mint("a.one", U1), retired=True, revived=True,
                 note="impossible event")
        )


def test_year_grain_labels_agree_by_number(tmp_path: pathlib.Path) -> None:
    # Eighth-review repro: calendar-2024 + fy2025 and calendar-2025 +
    # fy2026 merged end to end because the fiscal window overlaps both.
    rows = [
        _row("budget.total.fy2025", rid="budget.total.fy2025.final",
             period={"type": "year", "value": "2024"}),
        _row("budget.total.fy2026", rid="budget.total.fy2026.final",
             period={"type": "year", "value": "2025"}),
    ]
    catalog, _ = _build(tmp_path, rows)
    assert [r["concept"] for r in catalog["series"]] == [
        "budget.total.fy2025", "budget.total.fy2026",
    ]
    assert sorted(catalog["suspect_segments"]) == ["fy2025", "fy2026"]
    # Equal year-number DOES strip: the label names the row's own year.
    same = _row("budget.total.fy2025", rid="budget.total.fy2025.final",
                period={"type": "year", "value": "2025"})
    catalog, _ = _build(tmp_path, [same])
    assert catalog["series"][0]["concept"] == "budget.total"


def test_geography_name_conflict_is_a_hard_error(
    tmp_path: pathlib.Path,
) -> None:
    us = _row("trade.balance")
    fake = _row("trade.balance",
                period={"type": "month", "value": "2026-06"})
    fake["geography"] = dict(US, name="Canada")
    with pytest.raises(SystemExit, match="geography name conflict"):
        _build(tmp_path, [us, fake])


def test_whitespace_identity_fields_never_fork(
    tmp_path: pathlib.Path,
) -> None:
    # Ninth-review repro: vintage "current " minted a parallel UUID beside
    # vintage "current".
    padded = _row("agency.rate", period={"type": "month", "value": "2026-06"})
    padded["geography"] = dict(US, vintage="current ")
    with pytest.raises(SystemExit, match="surrounding whitespace"):
        _build(tmp_path, [_row("agency.rate"), padded])
    spaced_concept = _row(" agency.rate", rid="agency.rate.first_print")
    with pytest.raises(SystemExit, match="surrounding whitespace"):
        _build(tmp_path, [spaced_concept])
    registry_path = tmp_path / "registry.jsonl"
    registry_path.write_text(
        json.dumps(
            _mint("agency.rate", U1,
                  geography={"level": "country", "id": "0100000US",
                             "vintage": "current "})
        ) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="surrounding whitespace"):
        bsc.UuidRegistry.load(registry_path)
    with pytest.raises(SystemExit, match="surrounding whitespace"):
        _build(
            tmp_path,
            [_row("agency.rate")],
            docket={"series": [{"series": "docket.name ",
                                "cadence": "monthly"}]},
        )


def test_alias_merged_buckets_check_display_names(
    tmp_path: pathlib.Path,
) -> None:
    # Ninth-review repro: alias-linked spellings smuggled contradictory
    # geography names past the per-bucket conflict check.
    first, _ = _build(tmp_path, [_row("agency.rate")])
    first["series"][0]["aliases"] = ["agency.alt"]
    canada = _row("agency.alt",
                  period={"type": "month", "value": "2026-06"})
    canada["geography"] = dict(US, name="Canada")
    with pytest.raises(SystemExit, match="geography name conflict"):
        _build(tmp_path, [_row("agency.rate"), canada], existing=first)


@pytest.mark.parametrize(
    "segment", ["after_mpc_9999_13", "after_release_fy0000",
                "after_mpc_q1_9999"],
)
def test_qualified_out_of_window_tokens_are_flagged(segment: str) -> None:
    pattern = bsc.family_pattern(
        f"agency.rate.{segment}", {"type": "month", "value": "2026-05"}
    )
    assert pattern == f"agency.rate.{segment}"
    assert bsc.suspect_segments(pattern) == [segment]


def test_unicode_cosmetic_twins_never_fork(tmp_path: pathlib.Path) -> None:
    # Tenth-review repro: NFC café vs NFD cafe + combining acute
    # minted two identities; a zero-width suffix did the same.
    nfd = "agency.café.rate"
    with pytest.raises(SystemExit, match="not NFC-normalized"):
        _build(tmp_path, [_row(nfd, rid="agency.cafe.rate.first_print")])
    hidden = "agency.rate​"
    with pytest.raises(SystemExit, match="invisible character U\\+200B"):
        _build(tmp_path, [_row(hidden, rid="agency.rate.first_print")])
    padded_dim = _row("agency.rate")
    padded_dim["entity"] = {"name": "economy", "role": "aggre​gate"}
    with pytest.raises(SystemExit, match="invisible character"):
        _build(tmp_path, [padded_dim])
    registry_path = tmp_path / "registry.jsonl"
    registry_path.write_text(
        json.dumps(_mint(nfd, U1)) + "\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="not NFC-normalized"):
        bsc.UuidRegistry.load(registry_path)


def test_superseded_assertions_leave_the_catalog(
    tmp_path: pathlib.Path,
) -> None:
    # Tenth-review repro: a unit correction (append + supersedes link)
    # previously hard-errored as a unit conflict because identity was
    # built from raw journal lines instead of the current view.
    original = _row("agency.rate", unit="percent")
    original["assertionVersion"] = {"id": "av-1"}
    correction = _row("agency.rate", unit="index_points")
    correction["assertionVersion"] = {"id": "av-2", "supersedes": "av-1"}
    catalog, _ = _build(tmp_path, [original, correction])
    assert len(catalog["series"]) == 1
    row = catalog["series"][0]
    assert row["unit"] == "index_points"
    assert row["observation_count"] == 1
    assert catalog["observation_rows"] == 2
    assert catalog["current_assertion_rows"] == 1


def test_arch_annual_period_types_accepted(tmp_path: pathlib.Path) -> None:
    rows = [
        _row("agency.calendar.total.2025",
             rid="agency.calendar.total.2025.final",
             period={"type": "calendar_year", "value": "2025"}),
        _row("irs.actc.total_claims.2027",
             rid="irs.actc.total_claims.2027.first_print",
             period={"type": "tax_year", "value": "2027"}),
    ]
    catalog, _ = _build(tmp_path, rows)
    concepts = sorted(r["concept"] for r in catalog["series"])
    assert concepts == ["agency.calendar.total", "irs.actc.total_claims"]
    # A tax year assumes no calendar bounds: a same-number fy token stays
    # in the identity and is flagged for curation.
    flagged = bsc.family_pattern(
        "irs.actc.fy2027.total", {"type": "tax_year", "value": "2027"}
    )
    assert flagged == "irs.actc.fy2027.total"
    assert bsc.suspect_segments(flagged) == ["fy2027"]


def test_alias_naming_a_same_dimension_canonical_is_contradictory(
    tmp_path: pathlib.Path,
) -> None:
    # Eleventh-review repro: one exact name resolving to two live UUIDs
    # with ambiguous_aliases empty.
    first, _ = _build(
        tmp_path, [_row("agency.one"), _row("agency.rate")]
    )
    one = next(r for r in first["series"] if r["concept"] == "agency.one")
    one["aliases"] = ["agency.rate"]
    with pytest.raises(SystemExit, match="contradictory curation"):
        _build(
            tmp_path,
            [_row("agency.one"), _row("agency.rate")],
            existing=first,
        )
    # Across dimensions the collision is surfaced, not silent: the name
    # appears in ambiguous_aliases and never drives claims.
    gb_first, _ = _build(tmp_path, [_row("agency.gb", geography=dict(BRITAIN))])
    gb_first["series"][0]["aliases"] = ["agency.rate"]
    catalog, _ = _build(
        tmp_path,
        [_row("agency.gb", geography=dict(BRITAIN)), _row("agency.rate")],
        existing=gb_first,
    )
    assert catalog["ambiguous_aliases"] == ["agency.rate"]


def test_curated_aliases_pass_identity_string_rules(
    tmp_path: pathlib.Path,
) -> None:
    first, _ = _build(tmp_path, [_row("agency.café.rate".encode("utf-8").decode())])
    row = first["series"][0]
    row["aliases"] = ["agency.café.rate"]  # NFD twin of the canonical
    with pytest.raises(SystemExit, match="not NFC-normalized"):
        _build(tmp_path, [_row("agency.café.rate")], existing=first)
    row["aliases"] = ["agency.rate​"]
    with pytest.raises(SystemExit, match="invisible character"):
        _build(tmp_path, [_row("agency.café.rate")], existing=first)


def test_assertion_version_preconditions(tmp_path: pathlib.Path) -> None:
    # Eleventh-review repro: duplicate ids collapsed three identities to
    # one; a two-row cycle emptied the current view. Standalone runs now
    # enforce the append gate's preconditions themselves.
    a = _row("agency.one")
    a["assertionVersion"] = {"id": "dup"}
    b = _row("agency.two")
    b["assertionVersion"] = {"id": "dup"}
    with pytest.raises(SystemExit, match="duplicates row"):
        _build(tmp_path, [a, b])

    c = _row("agency.one")
    c["assertionVersion"] = {"id": "x", "supersedes": "y"}
    d = _row("agency.two")
    d["assertionVersion"] = {"id": "y", "supersedes": "x"}
    with pytest.raises(SystemExit, match="supersede cycle"):
        _build(tmp_path, [c, d])

    e = _row("agency.one")
    e["assertionVersion"] = {"id": "z", "supersedes": "z"}
    with pytest.raises(SystemExit, match="supersedes itself"):
        _build(tmp_path, [e])

    f = _row("agency.one")
    f["assertionVersion"] = {"id": "w", "supersedes": "missing"}
    with pytest.raises(SystemExit, match="unknown version"):
        _build(tmp_path, [f])


def test_cross_dimension_ambiguous_alias_never_steals(
    tmp_path: pathlib.Path,
) -> None:
    # Twelfth-review repro: GB canonical agency.rate + US row aliased to
    # it; an incoming US agency.rate observation previously inherited the
    # US alias-holder's UUID silently. Now the ambiguous name resolves to
    # nothing and the resulting same-dimension collision refuses loudly.
    first, _ = _build(
        tmp_path,
        [_row("agency.rate", geography=dict(BRITAIN)), _row("agency.other")],
    )
    us_row = next(
        r for r in first["series"] if r["concept"] == "agency.other"
    )
    us_row["aliases"] = ["agency.rate"]
    with pytest.raises(SystemExit, match="contradictory curation"):
        _build(
            tmp_path,
            [
                _row("agency.rate", geography=dict(BRITAIN)),
                _row("agency.other"),
                _row("agency.rate"),
            ],
            existing=first,
        )


def test_reenrichment_of_a_retired_successor(tmp_path: pathlib.Path) -> None:
    # Twelfth-review lifecycle: placeholder A/U1 -> enriched B/U1 ->
    # B retired + A reclaimed as U2 -> B observations return. The
    # grammar accepts B returning via succeeds on the CURRENT placeholder
    # lineage (consuming A/U2) instead of dead-ending.
    fresh = "dddddddd-4444-4444-8444-444444444444"
    a_key = {"concept": "census.m3.new_orders", "geography": None,
             "entity": None}
    b_geo = {"level": "country", "id": "0100000US", "vintage": "current"}
    b_ent = {"name": "economy", "role": "aggregate"}
    events = [
        _mint("census.m3.new_orders", U1),
        dict(_mint("census.m3.new_orders", U1), retired=True,
             note="placeholder enriched"),
        dict(_mint("census.m3.new_orders", U1, geography=b_geo,
                   entity=b_ent), succeeds=a_key),
        dict(_mint("census.m3.new_orders", U1, geography=b_geo,
                   entity=b_ent), retired=True,
             note="observation withdrawn upstream"),
        dict(_mint("census.m3.new_orders", fresh), reclaimed=True,
             note="placeholder re-established after handover"),
        dict(_mint("census.m3.new_orders", fresh), retired=True,
             note="placeholder enriched again"),
        dict(_mint("census.m3.new_orders", fresh, geography=b_geo,
                   entity=b_ent), succeeds=a_key),
    ]
    path = tmp_path / "registry.jsonl"
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )
    registry = bsc.UuidRegistry.load(path)
    b_binding = registry.binding((
        "census.m3.new_orders", bsc._geo_key(b_geo), bsc._entity_key(b_ent)
    ))
    assert b_binding == fresh and registry.is_live((
        "census.m3.new_orders", bsc._geo_key(b_geo), bsc._entity_key(b_ent)
    ))


def test_registry_event_keyset_is_closed(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "registry.jsonl"
    typo = dict(_mint("a.one", U1), supersedez=U2)
    path.write_text(json.dumps(typo) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="undeclared event fields"):
        bsc.UuidRegistry.load(path)
    nulled = dict(_mint("a.one", U1), retired=None)
    path.write_text(json.dumps(nulled) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="null-valued marker"):
        bsc.UuidRegistry.load(path)
    chatty = dict(_mint("a.one", U1), note="a mint explaining itself")
    path.write_text(json.dumps(chatty) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="takes none"):
        bsc.UuidRegistry.load(path)


def test_fiscal_labels_never_assume_a_jurisdiction() -> None:
    # Twelfth-review repro: fy2026 stripped from an AU July-2026 monthly
    # row through the hard-coded US fiscal window.
    pattern = bsc.family_pattern(
        "au.agency.edition.fy2026.rate",
        {"type": "month", "value": "2026-07"},
    )
    assert pattern == "au.agency.edition.fy2026.rate"
    assert bsc.suspect_segments(pattern) == ["fy2026"]
    # Year-number agreement still strips on year-grained rows.
    assert bsc.family_pattern(
        "agency.total.fy2025", {"type": "fiscal_year", "value": 2025}
    ) == "agency.total.{P}"


def test_self_succeeds_is_forbidden(tmp_path: pathlib.Path) -> None:
    # Thirteenth-review repro: retire -> self-succeeds -> retire ->
    # reclaim changed an exact identity's UUID with zero ceremony.
    fresh = "dddddddd-4444-4444-8444-444444444444"
    self_key = {"concept": "abs.labour.unemployment_rate",
                "geography": None, "entity": None}
    events = [
        _mint("abs.labour.unemployment_rate", U1),
        dict(_mint("abs.labour.unemployment_rate", U1), retired=True,
             note="withdrawn for the forgery"),
        dict(_mint("abs.labour.unemployment_rate", U1), succeeds=self_key),
        dict(_mint("abs.labour.unemployment_rate", U1), retired=True,
             note="second retirement"),
        dict(_mint("abs.labour.unemployment_rate", fresh), reclaimed=True,
             note="fresh uuid without ceremony"),
    ]
    path = tmp_path / "registry.jsonl"
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="succeeds ITSELF"):
        bsc.UuidRegistry.load(path)


def test_check_compares_bytes_not_text(tmp_path: pathlib.Path) -> None:
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")])
    assert bsc.main(argv) == 0
    catalog_path = tmp_path / "catalog.json"
    crlf = catalog_path.read_bytes().replace(b"\n", b"\r\n")
    catalog_path.write_bytes(crlf)
    assert bsc.main(argv + ["--check"]) == 1  # byte drift is drift


def test_builder_plans_reenrichment_of_retired_successor(
    tmp_path: pathlib.Path,
) -> None:
    # Fourteenth-review follow-up: placeholder A/U1 -> enriched B/U1 ->
    # B retired (observation withdrawn) + A reclaimed as U2 -> B returns.
    # The builder must plan retire(A/U2) + succeeds(B/U2) instead of
    # aborting on UUID ownership before enrichment planning.
    fresh = "dddddddd-4444-4444-8444-444444444444"
    a_key = {"concept": "census.m3.new_orders", "geography": None,
             "entity": None}
    b_geo = {"level": "country", "id": "0100000US", "vintage": "current"}
    b_ent = {"name": "economy", "role": "aggregate"}
    entries = [
        _mint("census.m3.new_orders", U1),
        dict(_mint("census.m3.new_orders", U1), retired=True,
             note="placeholder enriched"),
        dict(_mint("census.m3.new_orders", U1, geography=b_geo,
                   entity=b_ent), succeeds=a_key),
        dict(_mint("census.m3.new_orders", U1, geography=b_geo,
                   entity=b_ent), retired=True,
             note="observation withdrawn upstream"),
        dict(_mint("census.m3.new_orders", fresh), reclaimed=True,
             note="placeholder re-established after handover"),
    ]
    existing = {
        "series": [
            {
                "uuid": fresh,
                "concept": "census.m3.new_orders",
                "geography": None,
                "entity": None,
                "aliases": [],
                "status": "docket-only",
            }
        ]
    }
    catalog, plan = _build(
        tmp_path,
        [_row("census.m3.new_orders", geography=dict(b_geo), entity=b_ent)],
        existing=existing,
        registry_entries=entries,
    )
    row = catalog["series"][0]
    assert row["uuid"] == fresh and row["status"] == "observed"
    retire = next(e for e in plan["enrich_retires"] if e.get("retired"))
    succeed = next(e for e in plan["mints"] if e.get("succeeds"))
    assert retire["uuid"] == succeed["uuid"] == fresh
    # The staged whole must reload: succeeds lands on B's RETIRED key.
    registry = _registry(tmp_path, entries)
    staged = registry.stage(
        plan["enrich_retires"] + plan["mints"] + plan["revives"]
        + plan["supersedes"] + plan["retire_pending"]
    )
    b_full_key = ("census.m3.new_orders", bsc._geo_key(b_geo),
                  bsc._entity_key(b_ent))
    assert staged.binding(b_full_key) == fresh
    assert staged.is_live(b_full_key)


def test_malformed_succeeds_geography_is_a_schema_finding(
    tmp_path: pathlib.Path,
) -> None:
    # Fourteenth-review follow-up: a non-object succeeds.geography raised
    # a raw AttributeError inside key derivation.
    path = tmp_path / "registry.jsonl"
    base = [
        _mint("a.one", U1),
        dict(_mint("a.one", U1), retired=True, note="placeholder done"),
    ]
    forged = dict(
        _mint("a.one", U1, entity={"name": "economy", "role": "aggregate"}),
        succeeds={"concept": "a.one", "geography": "not-an-object",
                  "entity": None},
    )
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in base + [forged]),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="must be an object or null"):
        bsc.UuidRegistry.load(path)


def test_stage_rejects_stale_uuid_retire_after_supersede(
    tmp_path: pathlib.Path,
) -> None:
    # Fifteenth-review follow-up: a stale catalog row can retain U1 after
    # its own placeholder key superseded to U2. The enrichment plan the
    # old guard built from that row — retire(A/U1) + succeeds(B/U1) —
    # must die in staging replay before anything reaches disk.
    entries = [
        _mint("census.m3.new_orders", U1),
        dict(_mint("census.m3.new_orders", U2), supersedes=U1,
             note="curated remint of the placeholder"),
    ]
    registry = _registry(tmp_path, entries)
    raw_before = (tmp_path / "registry.jsonl").read_bytes()
    b_geo = {"level": "country", "id": "0100000US", "vintage": "current"}
    b_ent = {"name": "economy", "role": "aggregate"}
    invalid = [
        dict(_mint("census.m3.new_orders", U1), retired=True,
             note="docket placeholder enriched by first observed identity"),
        dict(_mint("census.m3.new_orders", U1, geography=b_geo,
                   entity=b_ent),
             succeeds={"concept": "census.m3.new_orders",
                       "geography": None, "entity": None}),
    ]
    with pytest.raises(SystemExit, match="must keep uuid"):
        registry.stage(invalid)
    assert (tmp_path / "registry.jsonl").read_bytes() == raw_before


def test_stale_catalog_uuid_after_supersede_fails_before_write(
    tmp_path: pathlib.Path,
) -> None:
    # Fifteenth-review follow-up: the builder itself must refuse the
    # stale row at plan time — the LIVE binding, not historical UUID
    # ownership, decides enrichment — and leave both artifacts untouched.
    seed = {
        "series": [
            {
                "series": "census.m3.new_orders",
                "cadence": "monthly",
                "extras": {"country": "US", "targetUnit": "percent"},
            }
        ]
    }
    argv = _repo(tmp_path, [_row("bls.cps.unemployment_rate")], seed=seed)
    assert bsc.main(argv) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    row = next(r for r in catalog["series"] if r["status"] == "docket-only")
    stale_uuid = row["uuid"]
    row["uuid"] = "55555555-5555-4555-8555-555555555555"
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    assert (
        bsc.main(argv + ["--allow-remint", "--remint-note", "curated remint"])
        == 0
    )
    # Regress the row to its pre-supersede UUID: a stale catalog.
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    row = next(r for r in catalog["series"] if r["status"] == "docket-only")
    row["uuid"] = stale_uuid
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    catalog_before = (tmp_path / "catalog.json").read_bytes()
    registry_before = (tmp_path / "registry.jsonl").read_bytes()
    (tmp_path / "obs.jsonl").write_text(
        "".join(
            json.dumps(r) + "\n"
            for r in [
                _row("bls.cps.unemployment_rate"),
                _row("census.m3.new_orders"),
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="explicit ceremony"):
        bsc.main(argv)
    assert (tmp_path / "catalog.json").read_bytes() == catalog_before
    assert (tmp_path / "registry.jsonl").read_bytes() == registry_before


# --- curated entity folds (Max's ruling d353, 2026-09-27) -------------------

HAND_ENTITY = {"name": "person", "role": "civilian_labor_force"}
ECONOMY = {"name": "economy", "role": "aggregate"}
US_IDENTITY = {"level": "country", "id": "0100000US", "vintage": "current"}
FOLD_NOTE = "test fold: hand-recorded rows join the resolver lineage"


def _fold_month(value: str) -> dict:
    return {"type": "month", "value": value}


def _drift_rows(hand_months=("2026-05",), economy_months=("2026-06", "2026-07")):
    """One series recorded twice: hand rows with a bespoke entity, resolver
    rows with economy/aggregate — the shape of the seven families."""
    rows = []
    for month in hand_months:
        rows.append(_row(
            "bls.cps.unemployment_rate",
            rid=f"bls.cps.unemployment_rate.{month}.hand",
            period=_fold_month(month),
            entity=dict(HAND_ENTITY),
            source_concept="bls.cps.unemployment_rate",
        ))
    for month in economy_months:
        rows.append(_row(
            f"bls.cps.unemployment_rate.{month}",
            rid=f"bls.cps.unemployment_rate.{month}.first_print",
            period=_fold_month(month),
            source_concept="UNRATE",
        ))
    return rows


def _fold(**overrides) -> dict:
    fold = {
        "concept": "bls.cps.unemployment_rate",
        "geography": dict(US_IDENTITY),
        "absorbed_entity": dict(HAND_ENTITY),
        "survivor_entity": dict(ECONOMY),
        "note": FOLD_NOTE,
    }
    fold.update(overrides)
    fold.setdefault("absorbed_names", [fold["concept"]])
    return fold


# The hand lineage of the industrial-production fixtures after its curated
# same-dimension merge: its concept, its observed spelling, the merged
# spelling and that spelling's observed form.
IP_ABSORBED_NAMES = [
    "fed.g17.ip.mom", "fed.g17.ip.mom.may_2026",
    "us.frb.ip.mom", "us.frb.ip.mom.2026_04",
]


def _write_folds(tmp_path: pathlib.Path, folds: list, **doc_overrides) -> bytes:
    doc = {"schemaVersion": bsc.ENTITY_FOLDS_SCHEMA, "folds": folds}
    doc.update(doc_overrides)
    (tmp_path / "seeds").mkdir(exist_ok=True)
    raw = (json.dumps(doc, indent=2) + "\n").encode()
    (tmp_path / "seeds" / "entity_folds.json").write_bytes(raw)
    return raw


def _observed(tmp_path: pathlib.Path, concept: str) -> list[dict]:
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    return [
        r for r in catalog["series"]
        if r["concept"] == concept and r["status"] == "observed"
    ]


def _uuid_for(rows: list[dict], entity: dict) -> str:
    (row,) = [r for r in rows if r["entity"] == entity]
    return row["uuid"]


def _without_digests(catalog: dict) -> dict:
    """A catalog minus the commitments an undo legitimately changes."""
    return {
        k: v for k, v in catalog.items()
        if k not in ("entity_folds_sha256", "uuid_registry_sha256")
    }


def _folded_repo(tmp_path: pathlib.Path, rows=None) -> tuple[list[str], str, str]:
    """A repo whose two drift lineages were folded; returns argv and the
    survivor and absorbed uuids."""
    argv = _repo(tmp_path, rows or _drift_rows())
    assert bsc.main(argv) == 0
    before = _observed(tmp_path, "bls.cps.unemployment_rate")
    survivor = _uuid_for(before, ECONOMY)
    absorbed = _uuid_for(before, HAND_ENTITY)
    _write_folds(tmp_path, [_fold()])
    assert bsc.main(argv + ["--allow-remint", "--remint-note", FOLD_NOTE]) == 0
    return argv, survivor, absorbed


def test_entity_fold_joins_the_lineages_and_retires_the_absorbed_binding(
    tmp_path: pathlib.Path,
) -> None:
    argv = _repo(tmp_path, _drift_rows())
    assert bsc.main(argv) == 0
    before = _observed(tmp_path, "bls.cps.unemployment_rate")
    assert len(before) == 2
    survivor = _uuid_for(before, ECONOMY)
    absorbed = _uuid_for(before, HAND_ENTITY)
    seed = _write_folds(tmp_path, [_fold()])
    registry_before = (tmp_path / "registry.jsonl").read_bytes()
    # A first fold retires a live binding: refused without the ceremony,
    # pending under --check, and nothing written.
    assert bsc.main(argv) == 1
    assert bsc.main(argv + ["--check"]) == 1
    assert (tmp_path / "registry.jsonl").read_bytes() == registry_before
    assert bsc.main(argv + ["--allow-remint", "--remint-note", FOLD_NOTE]) == 0

    (row,) = _observed(tmp_path, "bls.cps.unemployment_rate")
    assert row["uuid"] == survivor and row["entity"] == ECONOMY
    assert row["observation_count"] == 3
    assert row["first_observed_period"] == "2026-05"
    assert row["last_observed_period"] == "2026-07"
    assert set(row["source_concepts"]) == {"UNRATE", "bls.cps.unemployment_rate"}
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    assert catalog["entity_folds_sha256"] == bsc.hashlib.sha256(seed).hexdigest()
    assert absorbed not in {r["uuid"] for r in catalog["series"]}

    lines = (tmp_path / "registry.jsonl").read_text().splitlines()
    retire = json.loads(lines[-1])
    assert retire["retired"] is True and retire["uuid"] == absorbed
    assert retire["entity"] == HAND_ENTITY and retire["note"] == FOLD_NOTE
    assert len(lines) == len(registry_before.decode().splitlines()) + 1

    assert bsc.main(argv + ["--check"]) == 0
    catalog_bytes = (tmp_path / "catalog.json").read_bytes()
    registry_bytes = (tmp_path / "registry.jsonl").read_bytes()
    assert bsc.main(argv) == 0
    assert (tmp_path / "catalog.json").read_bytes() == catalog_bytes
    assert (tmp_path / "registry.jsonl").read_bytes() == registry_bytes


def test_entity_fold_never_writes_the_observation_journal(
    tmp_path: pathlib.Path,
) -> None:
    rows = _drift_rows()
    journal = "".join(json.dumps(r) + "\n" for r in rows).encode()
    argv, _, _ = _folded_repo(tmp_path, rows)
    assert (tmp_path / "obs.jsonl").read_bytes() == journal
    assert bsc.main(argv) == 0
    assert (tmp_path / "obs.jsonl").read_bytes() == journal


def test_entity_fold_seed_cannot_silently_vanish(tmp_path: pathlib.Path) -> None:
    argv, _, _ = _folded_repo(tmp_path)
    (tmp_path / "seeds" / "entity_folds.json").unlink()
    with pytest.raises(SystemExit, match="entity-fold seed missing"):
        bsc.main(argv)
    with pytest.raises(SystemExit, match="entity-fold seed missing"):
        bsc.main(argv + ["--check"])


def test_an_undone_fold_revives_the_absorbed_uuid(
    tmp_path: pathlib.Path,
) -> None:
    argv, survivor, absorbed = _folded_repo(tmp_path)
    undone = _write_folds(tmp_path, [{**_fold(), "undone": True}])
    # Removing a fold moves observations between lineages: a ceremony.
    registry_bytes = (tmp_path / "registry.jsonl").read_bytes()
    assert bsc.main(argv) == 1
    assert (tmp_path / "registry.jsonl").read_bytes() == registry_bytes
    assert bsc.main(argv + ["--allow-remint", "--remint-note", "undo"]) == 0
    rows = _observed(tmp_path, "bls.cps.unemployment_rate")
    assert _uuid_for(rows, ECONOMY) == survivor
    assert _uuid_for(rows, HAND_ENTITY) == absorbed
    revive = json.loads(
        (tmp_path / "registry.jsonl").read_text().splitlines()[-1]
    )
    assert revive["revived"] is True and revive["uuid"] == absorbed
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    assert catalog["entity_folds_sha256"] == bsc.hashlib.sha256(undone).hexdigest()
    assert bsc.main(argv + ["--check"]) == 0


def test_entity_fold_matching_no_current_row_is_inert(
    tmp_path: pathlib.Path,
) -> None:
    # A later correction can leave the absorbed entity with no current row;
    # that must never block regeneration (the Thesis resolver regenerates on
    # every append).
    argv, survivor, _ = _folded_repo(tmp_path)
    registry_bytes = (tmp_path / "registry.jsonl").read_bytes()
    (tmp_path / "obs.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in _drift_rows(hand_months=())),
        encoding="utf-8",
    )
    assert bsc.main(argv) == 0
    (row,) = _observed(tmp_path, "bls.cps.unemployment_rate")
    assert row["uuid"] == survivor and row["observation_count"] == 2
    assert (tmp_path / "registry.jsonl").read_bytes() == registry_bytes
    assert bsc.main(argv + ["--check"]) == 0


def test_entity_fold_reaches_rows_spelled_by_a_curated_alias(
    tmp_path: pathlib.Path,
) -> None:
    # The shape of census.housing_starts.saar and the G.17 industrial
    # production pair: the hand lineage already absorbed a second spelling by
    # a same-dimension curated merge, and those rows must fold too.
    sector = {"name": "institutional_sector", "role": "total_industrial_production"}
    rows = [
        _row("fed.g17.ip.mom.may_2026", rid="fed.g17.ip.mom.may_2026.hand",
             period=_fold_month("2026-05"), entity=dict(sector)),
        _row("us.frb.ip.mom.2026_04", rid="us.frb.ip.mom.2026_04.hand",
             period=_fold_month("2026-04"), entity=dict(sector)),
        _row("fed.g17.ip.mom.2026-06", rid="fed.g17.ip.mom.2026-06.first_print",
             period=_fold_month("2026-06"), source_concept="INDPRO"),
    ]
    argv = _repo(tmp_path, rows)
    assert bsc.main(argv) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    spelled = next(r for r in catalog["series"] if r["concept"] == "us.frb.ip.mom")
    hand = next(
        r for r in catalog["series"]
        if r["concept"] == "fed.g17.ip.mom" and r["entity"] == sector
    )
    catalog["series"].remove(spelled)
    hand["aliases"] = sorted({*hand["aliases"], "us.frb.ip.mom"})
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    assert bsc.main(argv + ["--allow-remint", "--remint-note", "spelling"]) == 0
    economy = _uuid_for(_observed(tmp_path, "fed.g17.ip.mom"), ECONOMY)

    _write_folds(tmp_path, [_fold(
        concept="fed.g17.ip.mom", absorbed_entity=sector,
        absorbed_names=IP_ABSORBED_NAMES,
    )])
    assert bsc.main(argv + ["--allow-remint", "--remint-note", FOLD_NOTE]) == 0
    (row,) = _observed(tmp_path, "fed.g17.ip.mom")
    assert row["uuid"] == economy and row["observation_count"] == 3
    assert "us.frb.ip.mom.{P}" in row["family_patterns"]
    assert not _observed(tmp_path, "us.frb.ip.mom")
    assert bsc.main(argv + ["--check"]) == 0


def test_appends_after_a_fold_never_touch_the_registry(
    tmp_path: pathlib.Path,
) -> None:
    # The Thesis resolver regenerates the catalog on every append and refuses
    # any registry change other than a first observation's mint. A later
    # print of a folded series, carrying either entity, must regenerate with
    # the registry byte-unchanged.
    argv, survivor, absorbed = _folded_repo(tmp_path)
    registry_bytes = (tmp_path / "registry.jsonl").read_bytes()
    later = _drift_rows(hand_months=("2026-09",), economy_months=("2026-08",))
    with (tmp_path / "obs.jsonl").open("a", encoding="utf-8") as journal:
        for row in later:
            journal.write(json.dumps(row) + "\n")
    assert bsc.main(argv) == 0
    assert (tmp_path / "registry.jsonl").read_bytes() == registry_bytes
    (row,) = _observed(tmp_path, "bls.cps.unemployment_rate")
    assert row["uuid"] == survivor and row["observation_count"] == 5
    assert row["last_observed_period"] == "2026-09"
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    assert absorbed not in {r["uuid"] for r in catalog["series"]}
    assert bsc.main(argv + ["--check"]) == 0


def test_undoing_a_fold_restores_earlier_spelling_merges(
    tmp_path: pathlib.Path,
) -> None:
    # The absorbed lineage had already absorbed a second spelling by a
    # same-dimension curated merge. Removing the fold must revive exactly the
    # absorbed identity, with that spelling back inside it, and must not
    # revive the spelling's own long-retired identity.
    sector = {"name": "institutional_sector", "role": "total_industrial_production"}
    rows = [
        _row("fed.g17.ip.mom.may_2026", rid="fed.g17.ip.mom.may_2026.hand",
             period=_fold_month("2026-05"), entity=dict(sector)),
        _row("us.frb.ip.mom.2026_04", rid="us.frb.ip.mom.2026_04.hand",
             period=_fold_month("2026-04"), entity=dict(sector)),
        _row("fed.g17.ip.mom.2026-06", rid="fed.g17.ip.mom.2026-06.first_print",
             period=_fold_month("2026-06"), source_concept="INDPRO"),
    ]
    argv = _repo(tmp_path, rows)
    assert bsc.main(argv) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    spelled = next(r for r in catalog["series"] if r["concept"] == "us.frb.ip.mom")
    hand = next(
        r for r in catalog["series"]
        if r["concept"] == "fed.g17.ip.mom" and r["entity"] == sector
    )
    catalog["series"].remove(spelled)
    hand["aliases"] = sorted({*hand["aliases"], "us.frb.ip.mom"})
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    assert bsc.main(argv + ["--allow-remint", "--remint-note", "spelling"]) == 0
    prefold = json.loads((tmp_path / "catalog.json").read_text())
    _write_folds(tmp_path, [_fold(
        concept="fed.g17.ip.mom", absorbed_entity=sector,
        absorbed_names=IP_ABSORBED_NAMES,
    )])
    assert bsc.main(argv + ["--allow-remint", "--remint-note", FOLD_NOTE]) == 0
    lines_before_undo = (tmp_path / "registry.jsonl").read_text().splitlines()

    _write_folds(
        tmp_path,
        [{**_fold(
            concept="fed.g17.ip.mom", absorbed_entity=sector,
            absorbed_names=IP_ABSORBED_NAMES,
        ), "undone": True}],
    )
    assert bsc.main(argv + ["--allow-remint", "--remint-note", "undo"]) == 0
    lines = (tmp_path / "registry.jsonl").read_text().splitlines()
    events = [json.loads(line) for line in lines[len(lines_before_undo):]]
    assert [(e.get("revived"), e["uuid"]) for e in events] == [(True, hand["uuid"])]
    restored = _observed(tmp_path, "fed.g17.ip.mom")
    (back,) = [r for r in restored if r["entity"] == sector]
    assert back["uuid"] == hand["uuid"] and back["observation_count"] == 2
    assert "us.frb.ip.mom.{P}" in back["family_patterns"]
    assert not _observed(tmp_path, "us.frb.ip.mom")
    undone = json.loads((tmp_path / "catalog.json").read_text())
    assert undone["ambiguous_aliases"] == []
    assert _without_digests(undone) == _without_digests(prefold)
    assert bsc.main(argv + ["--check"]) == 0


def test_retargeting_a_fold_needs_the_ceremony(tmp_path: pathlib.Path) -> None:
    # Moving a fold's survivor from one existing lineage to another plans no
    # registry event, yet moves observations between UUIDs.
    household = {"name": "household", "role": "aggregate"}
    rows = _drift_rows() + [
        _row("bls.cps.unemployment_rate", rid="bls.cps.unemployment_rate.2026-08.hh",
             period=_fold_month("2026-08"), entity=dict(household)),
    ]
    argv, survivor, _ = _folded_repo(tmp_path, rows)
    household_uuid = _uuid_for(_observed(tmp_path, "bls.cps.unemployment_rate"), household)
    catalog_bytes = (tmp_path / "catalog.json").read_bytes()
    registry_bytes = (tmp_path / "registry.jsonl").read_bytes()
    _write_folds(tmp_path, [_fold(survivor_entity=dict(household))])
    assert bsc.main(argv) == 1
    assert (tmp_path / "catalog.json").read_bytes() == catalog_bytes
    assert (tmp_path / "registry.jsonl").read_bytes() == registry_bytes
    assert bsc.main(argv + ["--check"]) == 1
    assert bsc.main(argv + ["--allow-remint", "--remint-note", "retarget"]) == 0
    rows_after = _observed(tmp_path, "bls.cps.unemployment_rate")
    counts = {r["uuid"]: r["observation_count"] for r in rows_after}
    assert counts == {survivor: 2, household_uuid: 2}
    assert (tmp_path / "registry.jsonl").read_bytes() == registry_bytes


def test_a_folded_rows_own_entity_is_still_validated(
    tmp_path: pathlib.Path,
) -> None:
    rows = _drift_rows()
    argv, _, _ = _folded_repo(tmp_path, rows)
    rows[0]["entity"] = {**HAND_ENTITY, "bogus": "x"}
    (tmp_path / "obs.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="entity.bogus is not an identity field"):
        bsc.main(argv)


def test_a_correction_superseding_an_absorbed_row_regenerates(
    tmp_path: pathlib.Path,
) -> None:
    # A versioned absorbed row corrected by an appended superseding row, with
    # its own entity or the survivor's, keeps one lineage and no registry
    # event. (Superseding a pre-versioning row is refused by the builder
    # whatever the folds say; that is a separate, pre-existing limitation.)
    rows = _drift_rows()
    rows[0]["assertionVersion"] = {"id": "av-test:hand-may", "supersedes": None}
    argv, survivor, absorbed = _folded_repo(tmp_path, rows)
    registry_bytes = (tmp_path / "registry.jsonl").read_bytes()
    for entity, version in ((HAND_ENTITY, "av-test:fix-1"), (ECONOMY, "av-test:fix-2")):
        correction = json.loads(json.dumps(rows[0]))
        correction["value"] = 4.4
        correction["entity"] = dict(entity)
        previous = "av-test:hand-may" if version.endswith("1") else "av-test:fix-1"
        correction["assertionVersion"] = {"id": version, "supersedes": previous}
        with (tmp_path / "obs.jsonl").open("a", encoding="utf-8") as journal:
            journal.write(json.dumps(correction) + "\n")
        assert bsc.main(argv) == 0
        (row,) = _observed(tmp_path, "bls.cps.unemployment_rate")
        assert row["uuid"] == survivor and row["observation_count"] == 3
        assert (tmp_path / "registry.jsonl").read_bytes() == registry_bytes
        assert bsc.main(argv + ["--check"]) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    assert absorbed not in {r["uuid"] for r in catalog["series"]}


def test_retired_identities_never_capture_rows_without_an_undone_fold(
    tmp_path: pathlib.Path,
) -> None:
    # The review's append-only replay: a household lineage retired by an
    # ordinary curated correction, a curated alias held only on the economy
    # row, then a new household row spelled by that alias. With no fold
    # undone, the row must mint its own identity, never revive the retired
    # one.
    household = {"name": "household", "role": "aggregate"}
    rows = [
        _row("a.one", rid="a.one.2026-05", period=_fold_month("2026-05"),
             entity=dict(household)),
        _row("a.one", rid="a.one.2026-06", period=_fold_month("2026-06")),
    ]
    rows[0]["assertionVersion"] = {"id": "av-test:a-may", "supersedes": None}
    argv = _repo(tmp_path, rows)
    assert bsc.main(argv) == 0
    household_uuid = _uuid_for(_observed(tmp_path, "a.one"), household)
    # Retire the household lineage by an appended correction that moves its
    # only row to the economy entity; the journal stays append-only.
    correction = json.loads(json.dumps(rows[0]))
    correction["entity"] = {"name": "economy", "role": "aggregate"}
    correction["assertionVersion"] = {"id": "av-test:a-may-fix", "supersedes": "av-test:a-may"}
    with (tmp_path / "obs.jsonl").open("a", encoding="utf-8") as journal:
        journal.write(json.dumps(correction) + "\n")
    assert bsc.main(argv + [
        "--allow-remint", "--remint-note",
        "household lineage corrected away by a curated correction",
    ]) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    (economy,) = [r for r in catalog["series"] if r["concept"] == "a.one"]
    economy["aliases"] = sorted({*economy["aliases"], "b.one"})
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    registry_lines = (tmp_path / "registry.jsonl").read_text().splitlines()
    with (tmp_path / "obs.jsonl").open("a", encoding="utf-8") as journal:
        journal.write(json.dumps(_row(
            "b.one", rid="b.one.2026-07", period=_fold_month("2026-07"),
            entity=dict(household),
        )) + "\n")
    assert bsc.main(argv) == 0
    events = [
        json.loads(line)
        for line in (tmp_path / "registry.jsonl").read_text().splitlines()[
            len(registry_lines):
        ]
    ]
    assert [(e["concept"], "revived" in e) for e in events] == [("b.one", False)]
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    assert household_uuid not in {r["uuid"] for r in catalog["series"]}


def test_a_fold_cannot_be_deleted_while_head_holds_it(
    tmp_path: pathlib.Path,
) -> None:
    import subprocess

    argv, _, _ = _folded_repo(tmp_path)
    for command in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "f"],
    ):
        subprocess.run(command, cwd=tmp_path, check=True)
    _write_folds(tmp_path, [])
    with pytest.raises(SystemExit, match="mark it undone|marking it undone"):
        bsc.main(argv + ["--allow-remint", "--remint-note", "delete"])
    _write_folds(tmp_path, [{**_fold(), "undone": True}])
    assert bsc.main(argv + ["--allow-remint", "--remint-note", "undo"]) == 0


def test_unobserved_curated_aliases_round_trip_through_undo(
    tmp_path: pathlib.Path,
) -> None:
    # absorbed_names records every name of the absorbed lineage, so a curated
    # alias no row spells moves to the survivor and back again.
    argv = _repo(tmp_path, _drift_rows())
    assert bsc.main(argv) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    hand = next(
        r for r in catalog["series"]
        if r["concept"] == "bls.cps.unemployment_rate" and r["entity"] == HAND_ENTITY
    )
    hand["aliases"] = sorted({*hand["aliases"], "labor.market.unemployment_rate"})
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    prefold = json.loads((tmp_path / "catalog.json").read_text())
    names = ["bls.cps.unemployment_rate", "labor.market.unemployment_rate"]
    _write_folds(tmp_path, [_fold(absorbed_names=names)])
    assert bsc.main(argv + ["--allow-remint", "--remint-note", FOLD_NOTE]) == 0
    (folded,) = _observed(tmp_path, "bls.cps.unemployment_rate")
    assert "labor.market.unemployment_rate" in folded["aliases"]
    _write_folds(tmp_path, [{**_fold(absorbed_names=names), "undone": True}])
    assert bsc.main(argv + ["--allow-remint", "--remint-note", "undo"]) == 0
    rows = _observed(tmp_path, "bls.cps.unemployment_rate")
    by_entity = {r["entity"]["name"]: r for r in rows}
    assert "labor.market.unemployment_rate" not in by_entity["economy"]["aliases"]
    assert "labor.market.unemployment_rate" in by_entity["person"]["aliases"]
    undone = json.loads((tmp_path / "catalog.json").read_text())
    assert _without_digests(undone) == _without_digests(prefold)
    assert bsc.main(argv + ["--check"]) == 0


def test_a_fold_never_captures_a_spelling_only_the_survivor_holds(
    tmp_path: pathlib.Path,
) -> None:
    # The round-5 review's replay: b.one is curated on the economy survivor
    # alone; a new person row spelled b.one is a new identity, not part of
    # the absorbed lineage.
    argv, survivor, _ = _folded_repo(tmp_path)
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    (economy,) = [
        r for r in catalog["series"] if r["concept"] == "bls.cps.unemployment_rate"
    ]
    economy["aliases"] = sorted({*economy["aliases"], "b.one"})
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    registry_lines = (tmp_path / "registry.jsonl").read_text().splitlines()
    with (tmp_path / "obs.jsonl").open("a", encoding="utf-8") as journal:
        journal.write(json.dumps(_row(
            "b.one", rid="b.one.2026-08", period=_fold_month("2026-08"),
            entity=dict(HAND_ENTITY),
        )) + "\n")
    assert bsc.main(argv) == 0
    (row,) = _observed(tmp_path, "bls.cps.unemployment_rate")
    assert row["uuid"] == survivor and row["observation_count"] == 3
    events = [
        json.loads(line)
        for line in (tmp_path / "registry.jsonl").read_text().splitlines()[
            len(registry_lines):
        ]
    ]
    assert [(e["concept"], e["entity"]) for e in events] == [("b.one", HAND_ENTITY)]


def test_a_fold_refuses_names_already_held_in_the_survivor_slice(
    tmp_path: pathlib.Path,
) -> None:
    # A name on both lineages makes undo inexact; resolve it before folding.
    argv = _repo(tmp_path, _drift_rows())
    assert bsc.main(argv) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    for row in catalog["series"]:
        if row["concept"] == "bls.cps.unemployment_rate":
            row["aliases"] = sorted({*row["aliases"], "labor.market.unemployment_rate"})
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    names = ["bls.cps.unemployment_rate", "labor.market.unemployment_rate"]
    _write_folds(tmp_path, [_fold(absorbed_names=names)])
    with pytest.raises(SystemExit, match="already belong to a row in the survivor"):
        bsc.main(argv + ["--allow-remint", "--remint-note", FOLD_NOTE])


@pytest.mark.parametrize("edit", ["drop", "move"])
def test_a_standing_fold_refuses_inconsistent_spelling_ownership(
    tmp_path: pathlib.Path, edit: str
) -> None:
    # The round-6 review's replay: after the fold, a hand edit takes an
    # absorbed name off the survivor (and, for "move", gives it to another
    # economy series). Folded rows must not follow it.
    argv = _repo(tmp_path, _drift_rows() + [
        _row("other.series", rid="other.series.2026-06", period=_fold_month("2026-06")),
    ])
    assert bsc.main(argv) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    hand = next(
        r for r in catalog["series"]
        if r["concept"] == "bls.cps.unemployment_rate" and r["entity"] == HAND_ENTITY
    )
    hand["aliases"] = sorted({*hand["aliases"], "labor.market.unemployment_rate"})
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    names = ["bls.cps.unemployment_rate", "labor.market.unemployment_rate"]
    _write_folds(tmp_path, [_fold(absorbed_names=names)])
    assert bsc.main(argv + ["--allow-remint", "--remint-note", FOLD_NOTE]) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    for row in catalog["series"]:
        if row["concept"] == "bls.cps.unemployment_rate":
            row["aliases"] = [a for a in row["aliases"] if a != names[1]]
        if edit == "move" and row["concept"] == "other.series":
            row["aliases"] = sorted({*row["aliases"], names[1]})
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="must hold every absorbed name alone"):
        bsc.main(argv)


def test_a_fold_must_declare_exactly_the_absorbed_names(
    tmp_path: pathlib.Path,
) -> None:
    argv = _repo(tmp_path, _drift_rows())
    assert bsc.main(argv) == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    hand = next(
        r for r in catalog["series"]
        if r["concept"] == "bls.cps.unemployment_rate" and r["entity"] == HAND_ENTITY
    )
    hand["aliases"] = ["labor.market.unemployment_rate"]
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    _write_folds(tmp_path, [_fold()])
    with pytest.raises(SystemExit, match="absorbed_names must be exactly"):
        bsc.main(argv + ["--allow-remint", "--remint-note", FOLD_NOTE])


def test_entity_fold_naming_an_unbound_identity_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    argv = _repo(tmp_path, _drift_rows())
    assert bsc.main(argv) == 0
    typo = {"name": "person", "role": "civilian_labour_force"}
    _write_folds(tmp_path, [_fold(absorbed_entity=typo)])
    with pytest.raises(SystemExit, match="registry has never bound"):
        bsc.main(argv + ["--allow-remint", "--remint-note", FOLD_NOTE])


def test_entity_fold_without_a_committed_survivor_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    argv = _repo(tmp_path, _drift_rows())
    assert bsc.main(argv) == 0
    _write_folds(
        tmp_path,
        [_fold(survivor_entity={"name": "household", "role": "aggregate"})],
    )
    with pytest.raises(SystemExit, match="no committed observed catalog row"):
        bsc.main(argv + ["--allow-remint", "--remint-note", FOLD_NOTE])


@pytest.mark.parametrize(
    ("folds", "doc", "match"),
    [
        ([_fold()], {"extra": 1}, "unknown fields"),
        ([_fold()], {"schemaVersion": "v0"}, "schemaVersion must be"),
        ([_fold()], {"comment": 3}, "comment must be a string"),
        ([{k: v for k, v in _fold().items() if k != "note"}], {}, "exactly the fields"),
        ([{**_fold(), "extra": 1}], {}, "exactly the fields"),
        ([{**_fold(), "undone": False}], {}, "undone must be true"),
        ([_fold(absorbed_names=[])], {}, "absorbed_names must be a sorted list"),
        ([_fold(absorbed_names=["z.one", "bls.cps.unemployment_rate"])], {},
         "absorbed_names must be a sorted list"),
        ([_fold(absorbed_names=["a.other"])], {}, "must include the concept"),
        ([{**_fold(), "undone": "yes"}], {}, "undone must be true"),
        ([_fold(note="  ")], {}, "note must be a nonempty string"),
        ([_fold(survivor_entity=dict(HAND_ENTITY))], {}, "into itself"),
        ([_fold(), _fold()], {}, "repeats the fold"),
        (
            [
                _fold(),
                _fold(
                    absorbed_entity=dict(ECONOMY),
                    survivor_entity={"name": "household", "role": "aggregate"},
                ),
            ],
            {},
            "both absorbed and a survivor",
        ),
        ([_fold(geography={"level": "country"})], {}, "geography.id is required"),
        ([_fold(absorbed_entity={"name": "person"})], {}, "absorbed_entity.role"),
        ([_fold(concept="bls.cps.unemployment_rate.{P}")], {}, "concept"),
    ],
)
def test_entity_fold_seed_schema_is_closed(
    tmp_path: pathlib.Path, folds: list, doc: dict, match: str
) -> None:
    argv = _repo(tmp_path, _drift_rows())
    assert bsc.main(argv) == 0
    _write_folds(tmp_path, folds, **doc)
    with pytest.raises(SystemExit, match=match):
        bsc.main(argv + ["--allow-remint", "--remint-note", FOLD_NOTE])


@pytest.mark.parametrize(
    "text",
    [
        '{"schemaVersion": "chronicle_entity_folds_v1", "folds": [], "folds": []}',
        '{"schemaVersion": "chronicle_entity_folds_v1", "folds": [NaN]}',
        '{"schemaVersion": "chronicle_entity_folds_v1", "folds": [Infinity]}',
    ],
    ids=["duplicate-key", "nan", "infinity"],
)
def test_entity_fold_seed_must_be_strict_json(
    tmp_path: pathlib.Path, text: str
) -> None:
    argv = _repo(tmp_path, _drift_rows())
    assert bsc.main(argv) == 0
    (tmp_path / "seeds").mkdir()
    (tmp_path / "seeds" / "entity_folds.json").write_text(text, encoding="utf-8")
    with pytest.raises(SystemExit, match="not strict JSON"):
        bsc.main(argv)


def test_entity_fold_default_path_sits_beside_the_catalog(
    tmp_path: pathlib.Path,
) -> None:
    # The Thesis resolver runs the generator with no arguments inside a
    # staged tree; the seed must resolve from the catalog's own directory.
    argv, _, _ = _folded_repo(tmp_path)
    explicit = argv + ["--entity-folds", str(tmp_path / "seeds" / "entity_folds.json")]
    assert bsc.main(explicit + ["--check"]) == 0
    assert bsc.main(argv + ["--check"]) == 0
    assert bsc.ENTITY_FOLDS == bsc.CATALOG.parent / "seeds" / "entity_folds.json"


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    hand=st.sets(st.sampled_from(["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]),
                 min_size=1, max_size=3),
    economy=st.sets(st.sampled_from(["2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]),
                    min_size=1, max_size=3),
)
def test_entity_fold_invariants_hold_for_any_split(
    tmp_path_factory: pytest.TempPathFactory, hand: set, economy: set
) -> None:
    """For every split of one series across two entities (months may
    overlap): the fold conserves observations, mints nothing, keeps the
    survivor's UUID, retires exactly the absorbed one, is byte-idempotent,
    and marking the fold undone revives exactly the absorbed UUID."""
    tmp_path = tmp_path_factory.mktemp("fold")
    rows = _drift_rows(hand_months=sorted(hand), economy_months=sorted(economy))
    argv = _repo(tmp_path, rows)
    assert bsc.main(argv) == 0
    before = json.loads((tmp_path / "catalog.json").read_text())
    unfolded = _observed(tmp_path, "bls.cps.unemployment_rate")
    survivor, absorbed = _uuid_for(unfolded, ECONOMY), _uuid_for(unfolded, HAND_ENTITY)

    _write_folds(tmp_path, [_fold()])
    assert bsc.main(argv + ["--allow-remint", "--remint-note", FOLD_NOTE]) == 0
    after = json.loads((tmp_path / "catalog.json").read_text())

    def observed_total(catalog: dict) -> int:
        return sum(
            r["observation_count"] for r in catalog["series"]
            if r["status"] == "observed"
        )

    assert observed_total(after) == after["current_assertion_rows"] == len(rows)
    assert observed_total(before) == observed_total(after)
    before_uuids = {r["uuid"] for r in before["series"]}
    after_uuids = {r["uuid"] for r in after["series"]}
    assert before_uuids - after_uuids == {absorbed}
    assert after_uuids <= before_uuids
    (row,) = _observed(tmp_path, "bls.cps.unemployment_rate")
    assert row["uuid"] == survivor
    assert row["observation_count"] == len(rows)
    assert row["first_observed_period"] == min(hand | economy)
    assert row["last_observed_period"] == max(hand | economy)
    events = [
        json.loads(line)
        for line in (tmp_path / "registry.jsonl").read_text().splitlines()
    ]
    assert [e["uuid"] for e in events if e.get("retired")] == [absorbed]
    assert not any("supersedes" in e for e in events)

    snapshot = (tmp_path / "catalog.json").read_bytes()
    assert bsc.main(argv) == 0
    assert (tmp_path / "catalog.json").read_bytes() == snapshot

    _write_folds(tmp_path, [{**_fold(), "undone": True}])
    assert bsc.main(argv + ["--allow-remint", "--remint-note", "undo"]) == 0
    restored = _observed(tmp_path, "bls.cps.unemployment_rate")
    assert {r["uuid"] for r in restored} == {survivor, absorbed}
    # Undo is exact: the catalog is the pre-fold catalog again.
    undone = json.loads((tmp_path / "catalog.json").read_text())
    assert _without_digests(undone) == _without_digests(before)
    assert bsc.main(argv + ["--check"]) == 0


# --- chained placeholder enrichment (2026-10-16) ----------------------------
#
# A docket placeholder can be enriched more than once. The geography-free
# placeholder becomes a geography-only one when its docket entry learns a
# country, and that one becomes the observed identity when the first print
# lands. Each hop is a retire + succeeds pair carrying one UUID. The guard is
# the LIVE binding of the row's own key. uuid_owner records first ownership
# and never moves, so it names the first hop's predecessor, never the
# second's: requiring it (the guard before this fix) refused every second
# hop. Thesis run 38962977031 hit exactly that on
# usaspending.dod.prime_award_obligations.

DOD = "usaspending.dod.prime_award_obligations"
CHAIN_NOTE = "docket placeholder enriched by first observed identity"
US_UNDECLARED = {"level": "country", "id": "0100000US", "vintage": None}
U3 = "cccccccc-3333-4333-8333-333333333333"
U4 = "eeeeeeee-5555-4555-8555-555555555555"


def _key(fields: dict) -> tuple[str, str, str]:
    return bsc.UuidRegistry.entry_key(fields)


def _owner(registry: bsc.UuidRegistry, row_uuid: str):
    return registry.uuid_owner.get(uuid.UUID(row_uuid).int)


def _plan_events(plan: dict) -> list[dict]:
    """Every registry event a plan stages, in main's order."""
    return (
        plan["enrich_retires"] + plan["mints"] + plan["revives"]
        + plan["supersedes"] + plan["retire_pending"]
    )


def _event_kind(event: dict) -> str:
    # Planned events carry absent markers as None; rendered lines omit them.
    for marker in ("succeeds", "supersedes", "retired", "revived", "reclaimed"):
        if event.get(marker) is not None:
            return marker
    return "mint"


def _registry_lines(tmp_path: pathlib.Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (tmp_path / "registry.jsonl").read_text().splitlines()
    ]


def _dod_observation() -> dict:
    """The FY2026 first print as Thesis records it (registered snapshot)."""
    return _row(
        f"{DOD}.fy2026",
        rid=f"{DOD}.fy2026.registered_query_snapshot",
        unit="billions USD",
        period={"type": "year", "value": "2026"},
    )


def _dod_chain() -> list[dict]:
    """Registry lines 196, 249 and 250 for a2649fd9, with U1 for the UUID."""
    return [
        _mint(DOD, U1),
        dict(_mint(DOD, U1), retired=True, note=CHAIN_NOTE),
        dict(
            _mint(DOD, U1, geography=US_UNDECLARED),
            succeeds={"concept": DOD, "geography": None, "entity": None},
        ),
    ]


def _docket_row(concept: str, row_uuid: str, geography: dict | None) -> dict:
    return {
        "uuid": row_uuid,
        "concept": concept,
        "geography": geography,
        "entity": None,
        "aliases": [],
        "status": "docket-only",
    }


def test_a_placeholder_enriched_once_is_enriched_again(
    tmp_path: pathlib.Path,
) -> None:
    # Production repro (Thesis run 38962977031, 2026-10-16). The catalog
    # still holds the geography-only placeholder docket-only; its first
    # print must take the second hop instead of falling through to the
    # UUID-reuse refusal.
    registry = _registry(tmp_path, _dod_chain())
    geo_key = _key({"concept": DOD, "geography": US_UNDECLARED, "entity": None})
    # The trap: the live placeholder holds U1 without having first owned it.
    assert registry.is_live(geo_key) and registry.binding(geo_key) == U1
    assert _owner(registry, U1) != geo_key
    existing = {
        "series": [
            _docket_row(DOD, U1, dict(bsc.COUNTRY_GEOGRAPHY["US"]))
        ]
    }
    catalog, plan = _build(
        tmp_path, [_dod_observation()], existing=existing,
        registry_entries=_dod_chain(),
    )
    (row,) = catalog["series"]
    assert (row["concept"], row["uuid"], row["status"]) == (DOD, U1, "observed")
    assert row["entity"] == ECONOMY
    # Exactly the pair the diagnosis's patched generator wrote (and that
    # thesis#362's append guard admits): retire the geography-only
    # placeholder, then succeed it at the observed identity, one UUID.
    assert [
        bsc.UuidRegistry.render_entry(e) for e in _plan_events(plan)
    ] == [
        bsc.UuidRegistry.render_entry(e)
        for e in (
            dict(_mint(DOD, U1, geography=US_UNDECLARED), retired=True,
                 note=CHAIN_NOTE),
            dict(
                _mint(DOD, U1, geography=US_IDENTITY, entity=ECONOMY),
                succeeds={"concept": DOD, "geography": US_UNDECLARED,
                          "entity": None},
            ),
        )
    ]
    assert not plan["dropped"]
    staged = registry.stage(_plan_events(plan))
    observed_key = _key(row)
    assert staged.is_live(observed_key) and staged.binding(observed_key) == U1
    assert not staged.is_live(geo_key) and geo_key in staged.consumed
    assert [k for k, e in staged.live_bindings() if e["uuid"] == U1] == [
        observed_key
    ]
    assert bsc.registry_agreement_problems(catalog, staged) == []


def test_placeholder_chain_keeps_one_uuid_through_main(
    tmp_path: pathlib.Path,
) -> None:
    # The same chain end to end through main: the docket entry starts with
    # no country, learns "US" (first hop, docket to docket), then its first
    # print lands (second hop). Neither hop needs a ceremony flag, the UUID
    # never changes, and --check passes after each.
    entry = {"series": DOD, "cadence": "annual",
             "extras": {"targetUnit": "billions USD"}}
    bystander = _row("bls.cps.unemployment_rate")
    argv = _repo(tmp_path, [bystander], seed={"series": [entry]})

    def rows_by_concept() -> dict[str, dict]:
        catalog = json.loads((tmp_path / "catalog.json").read_text())
        return {r["concept"]: r for r in catalog["series"]}

    assert bsc.main(argv) == 0
    placeholder = rows_by_concept()[DOD]
    assert placeholder["status"] == "docket-only"
    assert placeholder["geography"] is None
    lineage = placeholder["uuid"]
    bystander_uuid = rows_by_concept()["bls.cps.unemployment_rate"]["uuid"]

    entry["extras"]["country"] = "US"
    (tmp_path / "seed.json").write_text(
        json.dumps({"series": [entry]}), encoding="utf-8"
    )
    assert bsc.main(argv) == 0
    country = rows_by_concept()[DOD]
    assert (country["uuid"], country["status"]) == (lineage, "docket-only")
    assert country["geography"] == bsc.COUNTRY_GEOGRAPHY["US"]
    assert bsc.main(argv + ["--check"]) == 0

    (tmp_path / "obs.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in [bystander, _dod_observation()]),
        encoding="utf-8",
    )
    assert bsc.main(argv) == 0
    observed = rows_by_concept()[DOD]
    assert (observed["uuid"], observed["status"]) == (lineage, "observed")
    assert observed["entity"] == ECONOMY
    assert rows_by_concept()["bls.cps.unemployment_rate"]["uuid"] == (
        bystander_uuid
    )
    assert bsc.main(argv + ["--check"]) == 0

    events = _registry_lines(tmp_path)
    assert [
        (e["geography"], e["entity"], _event_kind(e))
        for e in events
        if e["concept"] == DOD
    ] == [
        (None, None, "mint"),
        (None, None, "retired"),
        (US_UNDECLARED, None, "succeeds"),
        (US_UNDECLARED, None, "retired"),
        (US_IDENTITY, ECONOMY, "succeeds"),
    ]
    assert {e["uuid"] for e in events if e["concept"] == DOD} == {lineage}
    assert not any(
        _event_kind(e) in ("supersedes", "reclaimed") for e in events
    )
    catalog_bytes = (tmp_path / "catalog.json").read_bytes()
    registry_bytes = (tmp_path / "registry.jsonl").read_bytes()
    assert bsc.main(argv) == 0
    assert (tmp_path / "catalog.json").read_bytes() == catalog_bytes
    assert (tmp_path / "registry.jsonl").read_bytes() == registry_bytes


# Each stage is (docket entry declares a country, observation present).
_CHAINS = (
    ((False, False), (True, False)),
    ((False, False), (False, True)),
    ((True, False), (True, True)),
    ((False, False), (True, False), (True, True)),
)


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    chain=st.sampled_from(_CHAINS),
    country=st.sampled_from(sorted(bsc.COUNTRY_GEOGRAPHY)),
    vintage=st.sampled_from(["current", "2020", None]),
    entity=st.sampled_from([ECONOMY, HAND_ENTITY]),
)
def test_any_placeholder_chain_keeps_one_uuid_and_passes_check(
    tmp_path_factory: pytest.TempPathFactory,
    chain: tuple,
    country: str,
    vintage: str | None,
    entity: dict,
) -> None:
    """For every chain of placeholder enrichments the builder can reach
    (geography-free -> country, geography-free -> observed, country ->
    observed, and all three hops), in any country, at any observed
    vintage and entity: every hop writes exactly one retire + succeeds
    pair handing over the binding it retired, needs no ceremony flag,
    keeps the lineage's one UUID, leaves exactly one live binding for it
    (at the row's identity), leaves unrelated series untouched, passes
    --check, and is byte-idempotent."""
    tmp_path = tmp_path_factory.mktemp("chain")
    concept = "agency.chain.series"
    neighbour = {"series": "agency.chain.neighbour", "cadence": "monthly",
                 "extras": {"country": "US", "targetUnit": "percent"}}
    bystander = _row("bls.cps.unemployment_rate")
    observation = _row(
        concept,
        geography={**bsc.COUNTRY_GEOGRAPHY[country], "vintage": vintage},
        entity=entity,
    )

    def write_stage(stage: tuple[bool, bool]) -> None:
        declares_country, observed = stage
        extras = {"targetUnit": "percent"}
        if declares_country:
            extras["country"] = country
        seed = {"series": [
            {"series": concept, "cadence": "monthly", "extras": extras},
            neighbour,
        ]}
        (tmp_path / "seed.json").write_text(json.dumps(seed), encoding="utf-8")
        rows = [bystander] + ([observation] if observed else [])
        (tmp_path / "obs.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )

    def catalog_rows() -> list[dict]:
        return json.loads((tmp_path / "catalog.json").read_text())["series"]

    argv = _repo(tmp_path, [])
    write_stage(chain[0])
    assert bsc.main(argv) == 0
    (first,) = [r for r in catalog_rows() if r["concept"] == concept]
    lineage = first["uuid"]
    others = {
        _key(r): r["uuid"] for r in catalog_rows() if r["concept"] != concept
    }
    for stage in chain[1:]:
        before = len(_registry_lines(tmp_path))
        write_stage(stage)
        assert bsc.main(argv) == 0  # no --allow-remint
        (row,) = [r for r in catalog_rows() if r["concept"] == concept]
        assert row["uuid"] == lineage
        assert row["status"] == ("observed" if stage[1] else "docket-only")
        hop = _registry_lines(tmp_path)[before:]
        assert [_event_kind(e) for e in hop] == ["retired", "succeeds"]
        assert {e["uuid"] for e in hop} == {lineage}
        assert _key(hop[1]["succeeds"]) == _key(hop[0])
        assert _key(hop[1]) == _key(row)
        assert {
            _key(r): r["uuid"] for r in catalog_rows() if r["concept"] != concept
        } == others
        registry = bsc.UuidRegistry.load(tmp_path / "registry.jsonl")
        assert [
            k for k, e in registry.live_bindings() if e["uuid"] == lineage
        ] == [_key(row)]
        assert bsc.main(argv + ["--check"]) == 0
        snapshot = (
            (tmp_path / "catalog.json").read_bytes(),
            (tmp_path / "registry.jsonl").read_bytes(),
        )
        assert bsc.main(argv) == 0
        assert (
            (tmp_path / "catalog.json").read_bytes(),
            (tmp_path / "registry.jsonl").read_bytes(),
        ) == snapshot
    assert {
        e["uuid"] for e in _registry_lines(tmp_path) if e["concept"] == concept
    } == {lineage}


def _stale_after_chain(scenario: str):
    """(registry events, stale docket-only row, observed identity): the
    DOD chain (geography-free -> geography-only, U1) and then whatever made
    the committed catalog's row stale."""
    chain = _dod_chain()
    observed_economy = {"concept": DOD, "geography": US_IDENTITY,
                        "entity": ECONOMY}
    observed_hand = dict(observed_economy, entity=HAND_ENTITY)
    geo_row = dict(bsc.COUNTRY_GEOGRAPHY["US"])
    handed_on = chain + [
        dict(_mint(DOD, U1, geography=US_UNDECLARED), retired=True,
             note=CHAIN_NOTE),
        dict(observed_economy, uuid=U1,
             succeeds={"concept": DOD, "geography": US_UNDECLARED,
                       "entity": None}),
    ]
    if scenario == "superseded":
        # A curated remint moved the placeholder to U2; the row kept U1.
        events = chain + [
            dict(_mint(DOD, U2, geography=US_UNDECLARED), supersedes=U1,
                 note="curated remint of the placeholder"),
        ]
        return events, _docket_row(DOD, U1, geo_row), observed_economy
    if scenario == "retired":
        # The docket entry was withdrawn (gated retire); the row lingers.
        events = chain + [
            dict(_mint(DOD, U1, geography=US_UNDECLARED), retired=True,
                 note="docket entry withdrawn"),
        ]
        return events, _docket_row(DOD, U1, geo_row), observed_economy
    if scenario == "handed over":
        # The placeholder already took its second hop; the row predates it.
        return handed_on, _docket_row(DOD, U1, geo_row), observed_hand
    if scenario == "reclaimed":
        # After the hand-over the observation was withdrawn and the
        # placeholder re-established on a fresh UUID; the row kept U1.
        events = handed_on + [
            dict(observed_economy, uuid=U1, retired=True,
                 note="observation withdrawn upstream"),
            dict(_mint(DOD, U2, geography=US_UNDECLARED), reclaimed=True,
                 note="placeholder re-established after handover"),
        ]
        return events, _docket_row(DOD, U1, geo_row), observed_hand
    if scenario == "chain root":
        # The row is the geography-free placeholder the first hop retired.
        return chain, _docket_row(DOD, U1, None), observed_economy
    if scenario == "another series' uuid":
        # The row carries a UUID that another live series holds.
        events = chain + [_mint("agency.other", U3)]
        return events, _docket_row(DOD, U3, geo_row), observed_economy
    raise AssertionError(scenario)


@pytest.mark.parametrize(
    "scenario",
    ["superseded", "retired", "handed over", "reclaimed", "chain root",
     "another series' uuid"],
)
def test_stale_rows_after_a_chain_are_still_refused(
    tmp_path: pathlib.Path, scenario: str
) -> None:
    # The case the dropped owner check was written for: a catalog row that
    # no longer carries its key's LIVE binding. With the owner check gone,
    # the live-binding conditions alone must refuse each one at plan time
    # with the ceremony diagnostic, and main must leave both artifacts
    # byte-untouched.
    events, stale_row, observed = _stale_after_chain(scenario)
    registry = _registry(tmp_path, events)
    stale_key = _key(stale_row)
    assert not (
        registry.is_live(stale_key)
        and registry.binding(stale_key) == stale_row["uuid"]
    )
    observation = _row(
        DOD, geography=dict(observed["geography"], name="United States"),
        entity=observed["entity"],
    )
    with pytest.raises(SystemExit, match="explicit ceremony"):
        _build(
            tmp_path, [observation], existing={"series": [stale_row]},
            registry_entries=events,
        )
    argv = _repo(tmp_path, [observation], seed={"series": []})
    _registry(tmp_path, events)
    (tmp_path / "catalog.json").write_text(
        json.dumps({"series": [stale_row]}) + "\n", encoding="utf-8"
    )
    catalog_before = (tmp_path / "catalog.json").read_bytes()
    registry_before = (tmp_path / "registry.jsonl").read_bytes()
    with pytest.raises(SystemExit, match="explicit ceremony"):
        bsc.main(argv)
    assert (tmp_path / "catalog.json").read_bytes() == catalog_before
    assert (tmp_path / "registry.jsonl").read_bytes() == registry_before


def test_a_returned_placeholder_never_hands_over_twice(
    tmp_path: pathlib.Path,
) -> None:
    # Independent-review counterexample (chronicle#360, 2026-10-18). A
    # placeholder B hands U1 to its observed identity C. The observation is
    # withdrawn and the docket loses its country (fresh placeholder A/U2),
    # then the country returns and B takes U2 from A. B is live and bound
    # to U2, but it is still consumed: it already handed over once, and the
    # grammar never lets a predecessor hand over twice. When C's
    # observation returns, the builder must refuse at plan time, naming the
    # cause. Without the consumed check it planned retire(B/U2) + C
    # succeeds B, which staging rejected. Base refused too (B never
    # first-owned U2), but with a remint message that blamed a supersede
    # nobody made. The diagnostic names the cause and prescribes nothing:
    # the right curation depends on the lineage (a delta review showed that
    # deleting the placeholder's row loses curated aliases held only there,
    # and that a consumed observed identity reclaims rather than revives).
    concept = "agency.lineage"
    bystander = _row("bls.cps.unemployment_rate")
    observed = _row(concept)

    def stage(country: bool, rows: list[dict]) -> None:
        extras = {"targetUnit": "percent"}
        if country:
            extras["country"] = "US"
        seed = {"series": [
            {"series": concept, "cadence": "monthly", "extras": extras},
        ]}
        (tmp_path / "seed.json").write_text(json.dumps(seed), encoding="utf-8")
        (tmp_path / "obs.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )

    argv = _repo(tmp_path, [])
    remint = ["--allow-remint", "--remint-note", "observation withdrawn"]
    stage(True, [bystander])
    assert bsc.main(argv) == 0  # mint B/U1
    stage(True, [bystander, observed])
    assert bsc.main(argv) == 0  # retire B, C succeeds B with U1
    stage(False, [bystander])
    assert bsc.main(argv + remint) == 0  # mint A/U2, retire C
    stage(True, [bystander])
    assert bsc.main(argv) == 0  # retire A, B succeeds A with U2
    assert bsc.main(argv + ["--check"]) == 0
    a_key = (concept, bsc._geo_key(None), bsc._entity_key(None))
    b_key = (concept, bsc._geo_key(US_UNDECLARED), bsc._entity_key(None))
    c_key = (concept, bsc._geo_key(US_IDENTITY), bsc._entity_key(ECONOMY))
    assert [
        (_key(e), _event_kind(e))
        for e in _registry_lines(tmp_path)
        if e["concept"] == concept
    ] == [
        (b_key, "mint"),
        (b_key, "retired"),
        (c_key, "succeeds"),
        (a_key, "mint"),
        (c_key, "retired"),
        (a_key, "retired"),
        (b_key, "succeeds"),
    ]
    registry = bsc.UuidRegistry.load(tmp_path / "registry.jsonl")
    u2 = registry.binding(a_key)
    assert registry.is_live(b_key) and registry.binding(b_key) == u2
    assert b_key in registry.consumed  # the state the live binding misses

    stage(True, [bystander, observed])
    catalog_before = (tmp_path / "catalog.json").read_bytes()
    registry_before = (tmp_path / "registry.jsonl").read_bytes()
    for flags in ([], remint):
        with pytest.raises(SystemExit, match="hands over at most once"):
            bsc.main(argv + flags)
        assert (tmp_path / "catalog.json").read_bytes() == catalog_before
        assert (tmp_path / "registry.jsonl").read_bytes() == registry_before

    # One curation that resolves this lineage (no curated aliases on B, and
    # C has an unconsumed retired binding): delete B's catalog row and
    # rerun with --allow-remint. C revives its own U1; B's U2 retires.
    catalog = json.loads(catalog_before)
    catalog["series"] = [
        r for r in catalog["series"] if r["concept"] != concept
    ]
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
    )
    assert bsc.main(argv) == 1  # retiring B's live binding is gated
    assert bsc.main(argv + remint) == 0
    assert bsc.main(argv + ["--check"]) == 0
    registry = bsc.UuidRegistry.load(tmp_path / "registry.jsonl")
    u1 = registry.binding(c_key)
    assert registry.is_live(c_key) and u1 != u2
    assert not registry.is_live(b_key) and registry.binding(b_key) == u2
    assert [
        (_key(e), _event_kind(e))
        for e in _registry_lines(tmp_path)[len(registry_before.splitlines()):]
    ] == [(c_key, "revived"), (b_key, "retired")]
    (row,) = [
        r for r in json.loads((tmp_path / "catalog.json").read_text())["series"]
        if r["concept"] == concept
    ]
    assert (row["uuid"], row["status"], _key(row)) == (u1, "observed", c_key)


def test_a_docket_alias_never_plans_a_cross_concept_hop(
    tmp_path: pathlib.Path,
) -> None:
    # Independent-review finding (chronicle#360, LOW, pre-existing): a
    # docket entry naming a placeholder by its curated alias keys the
    # docket row under the alias, so the planned succeeds crossed concepts
    # and died only in staging replay. The builder now refuses at plan time
    # naming the cause, and the remedy it names (call the docket entry by
    # the placeholder's own concept) enriches cleanly.
    existing = {"series": [
        dict(_docket_row("agency.a", U1, None), aliases=["agency.b"]),
    ]}
    entry = {"series": "agency.b", "cadence": "monthly",
             "extras": {"country": "US", "targetUnit": "percent"}}
    with pytest.raises(SystemExit, match="never crosses concepts") as refused:
        _build(
            tmp_path, [], existing=existing,
            registry_entries=[_mint("agency.a", U1)],
            docket={"series": [entry]},
        )
    assert "name the docket entry 'agency.a'" in str(refused.value)
    catalog, plan = _build(
        tmp_path, [], existing=existing,
        registry_entries=[_mint("agency.a", U1)],
        docket={"series": [dict(entry, series="agency.a")]},
    )
    (row,) = catalog["series"]
    assert (row["concept"], row["uuid"], row["status"]) == (
        "agency.a", U1, "docket-only"
    )
    assert [_event_kind(e) for e in _plan_events(plan)] == [
        "retired", "succeeds"
    ]
    staged = _registry(tmp_path, [_mint("agency.a", U1)]).stage(
        _plan_events(plan)
    )
    assert bsc.registry_agreement_problems(catalog, staged) == []


# A small identity universe for generated registry histories: two concepts
# (so a row can carry another series' UUID), geographies at every
# refinement level, three entities, and six UUIDs (so stale rows collide
# with known values).
_GEN_CONCEPT, _GEN_OTHER = "agency.lineage", "agency.elsewhere"
_PLACEHOLDER_GEOS = (
    None,
    {"level": "country", "id": "0100000US", "vintage": None},
    {"level": "country", "id": "0100000US", "vintage": "current"},
    {"level": "country", "id": "0100000US", "vintage": "2020"},
    {"level": "country", "id": "GB", "vintage": None},
)
_OBSERVED_GEOS = (
    {"level": "country", "id": "0100000US", "vintage": "current"},
    {"level": "country", "id": "0100000US", "vintage": "2020"},
    {"level": "country", "id": "GB", "vintage": "current"},
)
_GEN_GEOS = _PLACEHOLDER_GEOS + _OBSERVED_GEOS[2:]
_GEN_ENTITIES = (None, ECONOMY, HAND_ENTITY)
_GEN_UUIDS = (
    U1, U2, U3, U4,
    "ffffffff-6666-4666-8666-666666666666",
    "abababab-7777-4777-8777-777777777777",
)
_GEN_IDENTS = tuple(
    {"concept": concept, "geography": geography, "entity": entity}
    for concept in (_GEN_CONCEPT, _GEN_OTHER)
    for geography in _GEN_GEOS
    for entity in _GEN_ENTITIES
)


def _ident(entry: dict) -> dict:
    return {key: entry[key] for key in ("concept", "geography", "entity")}


def _refines(placeholder: dict | None, geography: dict | None) -> bool:
    """Whether an enrichment hop from ``placeholder`` to ``geography`` is
    plausible. Used only to steer generation toward chains; the registry
    grammar alone decides what a history may contain."""
    if placeholder is None:
        return True
    geography = geography or {}
    return (placeholder["level"], placeholder["id"]) == (
        geography.get("level"), geography.get("id")
    ) and placeholder["vintage"] in (None, geography.get("vintage"))


def _generated_registry(data: st.DataObject) -> bsc.UuidRegistry:
    """A registry grown from random events that the grammar accepts.

    Each step draws a move the current state allows: mint an unbound
    identity on an unused UUID, retire a live binding, revive a retired
    one, supersede or reclaim onto an unused UUID, take an enrichment hop
    (retire an entity-less binding and succeed it at a refinement), or
    return (mint a coarser placeholder and hop it onto a retired key that
    already handed over).
    The move is kept only if UuidRegistry accepts it, so every history is
    one the grammar itself admits. Hops chain, so placeholders enriched
    once, twice and three times occur alongside stale, superseded,
    retired, handed-over and reclaimed keys, and keys that handed over and
    then returned as a later hop's successor (live, but consumed)."""
    registry = bsc.UuidRegistry(pathlib.Path("generated.jsonl"), b"")
    for _ in range(data.draw(st.integers(1, 12), label="steps")):
        held = list(registry.latest.values())
        live = [e for e in held if not e.get("retired")]
        retired = [e for e in held if e.get("retired")]
        consumed = [e for e in retired if _key(e) in registry.consumed]
        unbound = [i for i in _GEN_IDENTS if _key(i) not in registry.latest]
        unused = [u for u in _GEN_UUIDS if _owner(registry, u) is None]
        moves = []
        if unbound and unused:
            moves += ["mint", "mint"]
        if live:
            moves += ["retire"]
        if live and unused:
            moves += ["supersede"]
        if retired:
            moves += ["revive"]
        if consumed and unused:
            moves += ["reclaim"]
        if any(e["entity"] is None for e in live):
            moves += ["hop", "hop", "hop"]
        # A consumed placeholder can take a lineage again as a later hop's
        # successor (main writes this when a docket entry loses its
        # country, which mints a fresh coarser placeholder, and regains
        # it): mint a coarser placeholder and hop it straight onto the key.
        returns = [
            (coarser, entry)
            for entry in consumed
            if entry["entity"] is None
            for coarser in unbound
            if coarser["concept"] == entry["concept"]
            and coarser["entity"] is None
            and _key(coarser) != _key(entry)
            and _refines(coarser["geography"], entry["geography"])
        ]
        if returns and unused:
            moves += ["return", "return"]
        if not moves:
            break
        move = data.draw(st.sampled_from(moves))
        if move == "mint":
            # Placeholders (entity-less) are minted twice as often.
            pool = [i for i in unbound if i["entity"] is None] * 2 + unbound
            events = [dict(data.draw(st.sampled_from(pool)),
                           uuid=data.draw(st.sampled_from(unused)))]
        elif move == "retire":
            entry = data.draw(st.sampled_from(live))
            events = [dict(_ident(entry), uuid=entry["uuid"], retired=True,
                           note="generated retirement")]
        elif move == "supersede":
            entry = data.draw(st.sampled_from(live))
            events = [dict(_ident(entry),
                           uuid=data.draw(st.sampled_from(unused)),
                           supersedes=entry["uuid"],
                           note="generated curated remint")]
        elif move == "revive":
            entry = data.draw(st.sampled_from(retired))
            events = [dict(_ident(entry), uuid=entry["uuid"], revived=True)]
        elif move == "reclaim":
            entry = data.draw(st.sampled_from(consumed))
            events = [dict(_ident(entry),
                           uuid=data.draw(st.sampled_from(unused)),
                           reclaimed=True,
                           note="generated reclaim after handover")]
        elif move == "return":
            coarser, entry = data.draw(st.sampled_from(returns))
            fresh = data.draw(st.sampled_from(unused))
            events = [
                dict(coarser, uuid=fresh),
                dict(coarser, uuid=fresh, retired=True, note=CHAIN_NOTE),
                dict(_ident(entry), uuid=fresh, succeeds=coarser),
            ]
        else:
            entry = data.draw(st.sampled_from(
                [e for e in live if e["entity"] is None]
            ))
            targets = [
                ident for ident in _GEN_IDENTS
                if ident["concept"] == entry["concept"]
                and _key(ident) != _key(entry)
                and _refines(entry["geography"], ident["geography"])
            ]
            # Entity-less targets are weighted up so hops chain, and retired
            # ones further still so lineages return onto keys that already
            # handed over (live again, but consumed).
            retired_keys = {_key(e) for e in retired}
            target = data.draw(st.sampled_from(
                [t for t in targets if _key(t) in retired_keys] * 6
                + [t for t in targets if t["entity"] is None] * 3
                + targets
            ))
            events = [
                dict(_ident(entry), uuid=entry["uuid"], retired=True,
                     note=CHAIN_NOTE),
                dict(target, uuid=entry["uuid"], succeeds=_ident(entry)),
            ]
        try:
            registry = registry.stage(events)
        except SystemExit:
            continue
    return registry


@settings(max_examples=400, deadline=None)
@given(data=st.data())
def test_a_live_binding_its_key_never_first_owned_came_by_succeeds(
    data: st.DataObject,
) -> None:
    """Why the owner check was redundant where it was right. In every
    history the grammar admits, a live binding (K, U) either has K as U's
    first owner, or K's binding was established by a succeeds event. So
    the conjunct uuid_owner[U] == K, on top of the live-binding
    conditions, refused nothing but enrichment chains."""
    registry = _generated_registry(data)
    for key, entry in registry.live_bindings():
        if _owner(registry, entry["uuid"]) == key:
            continue
        establishing = [
            e for e in registry.entries
            if _key(e) == key and _event_kind(e) not in ("retired", "revived")
        ]
        assert _event_kind(establishing[-1]) == "succeeds", (key, entry)


@settings(
    max_examples=400,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(data=st.data())
def test_enrichment_is_planned_exactly_when_the_grammar_admits_it(
    tmp_path_factory: pytest.TempPathFactory, data: st.DataObject
) -> None:
    """Differential: plan-time guard vs. the registry grammar.

    For any history the grammar admits, any docket-only row (live, live
    but already handed over, stale, superseded, retired, handed over,
    reclaimed, the root of a chain, or carrying another series' UUID) and
    any observation of its concept:

    * completeness: the builder plans the retire + succeeds pair exactly
      when UuidRegistry would accept that very pair (so no enrichment
      chain is refused);
    * soundness: everything the builder plans stages cleanly and agrees
      with the catalog it built (so no stale row slips through);
    * a refusal is a plan-time diagnostic, never a crash;
    * when no enrichment is planned, the row takes its own key's binding
      or a UUID new to the registry, never a UUID another key holds.
    """
    tmp_path = tmp_path_factory.mktemp("differential")
    registry = _generated_registry(data)
    (tmp_path / "registry.jsonl").write_bytes(registry.raw)
    placeholders = [
        e for e in registry.latest.values()
        if e["concept"] == _GEN_CONCEPT and e["entity"] is None
    ]
    # Steer toward rows at keys the history holds, carrying their last
    # binding: live ones (the chained case lives here), live ones that
    # already handed over (consumed), and stale ones (retired, handed
    # over). Any geography with any UUID stays possible.
    live = [e for e in placeholders if not e.get("retired")]
    candidates = (
        [(e["geography"], e["uuid"]) for e in live] * 8
        + [(e["geography"], e["uuid"]) for e in live
           if _key(e) in registry.consumed] * 16
        + [(e["geography"], e["uuid"]) for e in placeholders] * 2
        + [(g, u) for g in _PLACEHOLDER_GEOS for u in _GEN_UUIDS]
    )
    geography, row_uuid = data.draw(st.sampled_from(candidates))
    placeholder = {"concept": _GEN_CONCEPT, "geography": geography,
                   "entity": None}
    # Observations that refine the row's geography are weighted up; any
    # observed geography stays possible (cross-country, vintage clash).
    observed = {
        "concept": _GEN_CONCEPT,
        "geography": data.draw(st.sampled_from(
            [g for g in _OBSERVED_GEOS if _refines(geography, g)] * 3
            + list(_OBSERVED_GEOS)
        )),
        "entity": data.draw(st.sampled_from((ECONOMY, HAND_ENTITY))),
    }
    retire = dict(placeholder, uuid=row_uuid, retired=True, note=CHAIN_NOTE)
    succeed = dict(observed, uuid=row_uuid, succeeds=placeholder)
    try:
        registry.stage([retire, succeed])
        admitted = True
    except SystemExit:
        admitted = False
    observation = _row(
        _GEN_CONCEPT,
        geography=dict(observed["geography"], name=None),
        entity=observed["entity"],
    )
    try:
        catalog, plan = _build(
            tmp_path, [observation],
            existing={"series": [_docket_row(_GEN_CONCEPT, row_uuid,
                                             geography)]},
        )
    except SystemExit as exc:
        assert not admitted, exc
        assert any(
            diagnostic in str(exc)
            for diagnostic in (
                "explicit ceremony",
                "superseding UUIDs must be new",
                "hands over at most once",
            )
        ), exc
        return
    hop = [e for e in plan["mints"] if "succeeds" in e]
    assert bool(hop) == admitted
    (row,) = catalog["series"]
    if admitted:
        assert row["uuid"] == row_uuid
        assert [
            bsc.UuidRegistry.render_entry(e)
            for e in plan["enrich_retires"] + hop
        ] == [bsc.UuidRegistry.render_entry(e) for e in (retire, succeed)]
    else:
        assert row["uuid"] == registry.binding(_key(observed)) or (
            _owner(registry, row["uuid"]) is None
        )
    # main attaches the ceremony note to gated events before staging.
    for event in plan["supersedes"] + plan["retire_pending"]:
        event["note"] = "generated ceremony"
    staged = registry.stage(_plan_events(plan))
    assert bsc.registry_agreement_problems(catalog, staged) == []
