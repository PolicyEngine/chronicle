"""Differential tests: Chronicle's YAML loader must match ``yaml.safe_load``.

``chronicle.yaml_io.safe_load`` swaps PyYAML's pure-Python parser for libyaml
to make CI tractable. The swap is only safe if every document Chronicle reads
loads to the same objects either way, so these tests compare the two loaders
on hand-picked edge cases, on seeded generated documents and on every tracked
YAML file small enough to parse cheaply with the pure-Python loader.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
import os
from pathlib import Path
import random
import re

import pytest
import yaml

from chronicle import yaml_io


REPO_ROOT = Path(__file__).resolve().parents[1]
# Pure-Python parsing runs at well under 1 MB/s on hosted runners; files under
# this size add up to about 3 MB (416 of the 563 tracked files on 2026-10-08).
SMALL_FILE_BYTES = 64 * 1024


def _same(left, right) -> bool:
    """Equal, with equal types throughout, in the same key order."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        if list(map(type, left)) != list(map(type, right)):
            return False
        return list(left) == list(right) and all(
            _same(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if isinstance(left, float) and math.isnan(left):
        return math.isnan(right)
    return left == right


def _both(text: str):
    return yaml_io.safe_load(text), yaml.safe_load(text)


def test_libyaml_loader_is_used_on_github_actions():
    # The speedup depends on PyYAML shipping libyaml for the runner's platform.
    # Fail loudly on CI if it ever does not, rather than slowing down silently.
    if os.environ.get("GITHUB_ACTIONS") != "true":
        pytest.skip("only asserted on GitHub-hosted runners")
    assert yaml.__with_libyaml__
    assert yaml_io.SafeLoader is yaml.CSafeLoader


def test_loader_falls_back_to_pure_python_without_libyaml():
    expected = yaml.CSafeLoader if yaml.__with_libyaml__ else yaml.SafeLoader
    assert yaml_io.SafeLoader is expected


EDGE_CASES = {
    "yaml11_booleans": "a: yes\nb: No\nc: on\nd: OFF\ne: true\nf: 'yes'\n",
    "integers": "dec: 1_000\noct: 0o17\nold_oct: 017\nhex: 0x1F\nneg: -42\n"
    "zero_padded: '0123'\nsexagesimal: 1:20\n",
    "floats": "a: 1e3\nb: 1.5e-3\nc: .inf\nd: -.Inf\ne: .nan\nf: 6.8523015e+5\n"
    "g: 3.\nh: 1_000.5\n",
    "nulls": "a: null\nb: ~\nc:\nd: Null\ne: ''\n",
    "dates": "d: 2024-06-30\nts: 2024-06-30T12:00:00Z\n"
    "tz: 2001-12-14t21:59:43.10-05:00\nspace: 2001-12-14 21:59:43.10 -5\n"
    "quoted: '2024-06-30'\n",
    "anchors_and_merge": "base: &base {x: 1, y: [a, b]}\n"
    "child:\n  <<: *base\n  y: [c]\nalias: *base\n",
    "block_scalars": "lit: |\n  line one\n    indented\n\n  after blank\n"
    "fold: >-\n  folded\n  text\n\nkeep: |+\n  kept\n\n",
    "quoting_and_escapes": 'dq: "tab\\tnew\\nline \\u00e9 \\x41"\n'
    "sq: 'it''s'\nplain: a # comment\nhash: 'a # not comment'\n"
    "colon: 'k: v'\n",
    "unicode": "pound: £20\naccent: Région\ncjk: 東京\nkey_é: 1\n",
    "flow_collections": "m: {a: 1, b: [2, 3], c: {d: e}}\nl: [1, 'two', 3.0, null]\n",
    "mixed_key_types": "1: int\n'1': str\ntrue: bool\nnull: none\n2.5: float\n",
    "explicit_tags": "s: !!str 123\ni: !!int '7'\nf: !!float '1'\nb: !!bool 'yes'\n",
    "nested_lists": "- - a\n  - b\n- - c\n-\n  - d: 1\n    e: 2\n",
    "multiline_plain": "text: first line\n  continues here\n\n  new paragraph\n",
    "crlf_line_endings": "a: 1\r\nb:\r\n  - x\r\n  - y\r\n",
    "byte_order_mark": "\ufeffa: 1\n",
    "document_markers": "---\na: 1\n...\n",
    "empty_document": "",
    "comment_only": "# nothing here\n",
    "long_plain_scalar": "k: " + "word " * 400 + "\n",
    "complex_key": "? |\n  block key\n: value\n",
    "source_package_shape": """\
schema_version: chronicle.source_package.v1
package_id: example-2024
artifact:
  resource_package: db
  resource_directory: data/example/table_1
  manifest: manifest.yaml
  artifact_year: 2024
record_sets:
  - record_set_id: example.table_1
    period: '2024'
    provenance_class: administrative
    rows:
      - {row_label: 'All returns', selector: 'A1', value: 1234.5}
      - {row_label: 'Under $1', selector: 'A2', value: -0.0}
    measures: [count, amount]
""",
}


@pytest.mark.parametrize("name", sorted(EDGE_CASES))
def test_loaders_agree_on_edge_cases(name):
    fast, reference = _both(EDGE_CASES[name])
    assert _same(fast, reference), name


@pytest.mark.parametrize(
    "text",
    [
        "a: [1, 2\n",
        "a: 'unterminated\n",
        "a:\n\t- tab indented\n",
        "a: 1\n a: 2\n",
        "- a\nb: c\n",
        "*undefined_alias\n",
        "a: !!python/object:os.system x\n",
    ],
)
def test_loaders_reject_the_same_malformed_or_unsafe_documents(text):
    # Callers catch yaml.YAMLError, so the fast loader must raise one too.
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(text)
    with pytest.raises(yaml.YAMLError):
        yaml_io.safe_load(text)


_TEXT_ALPHABET = "abcxyzABC019 _-.,:;#'\"!?&*|>%@`{}[]\\/\t\néü£€東"
_TRICKY_WORDS = [
    "yes",
    "No",
    "on",
    "OFF",
    "null",
    "~",
    "true",
    "1e3",
    "0x1F",
    "017",
    "1_000",
    ".nan",
    "-.inf",
    "2024-06-30",
    "12:30",
    "- item",
    "a: b",
    "#",
    "",
    " ",
    "'",
    '"',
    "<<",
    "=",
    "?",
]


def _random_scalar(rng: random.Random):
    kind = rng.randrange(8)
    if kind == 0:
        return rng.randint(-(10**12), 10**12)
    if kind == 1:
        return rng.choice(
            [
                0.0,
                -0.0,
                1.5,
                -2.25e-7,
                6.02e23,
                float("inf"),
                float("-inf"),
                rng.uniform(-1e6, 1e6),
            ]
        )
    if kind == 2:
        return rng.choice([True, False, None])
    if kind == 3:
        return date(2000, 1, 1) + timedelta(days=rng.randrange(20000))
    if kind == 4:
        return datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(
            seconds=rng.randrange(10**8)
        )
    if kind == 5:
        return rng.choice(_TRICKY_WORDS)
    length = rng.randrange(0, 40)
    return "".join(rng.choice(_TEXT_ALPHABET) for _ in range(length))


def _random_document(rng: random.Random, depth: int = 0):
    if depth >= 4 or rng.random() < 0.3:
        return _random_scalar(rng)
    if rng.random() < 0.5:
        return [_random_document(rng, depth + 1) for _ in range(rng.randrange(5))]
    keys = {}
    for _ in range(rng.randrange(6)):
        key = (
            _random_scalar(rng)
            if rng.random() < 0.2
            else rng.choice(_TRICKY_WORDS + ["package_id", "rows", "value", "période"])
        )
        if isinstance(key, float) and math.isnan(key):
            continue
        keys[key] = _random_document(rng, depth + 1)
    return keys


@pytest.mark.parametrize("seed", range(10))
def test_loaders_agree_and_round_trip_on_generated_documents(seed):
    # Property: for any document safe_dump writes, both loaders rebuild the
    # same value, and that value is the one that was dumped.
    rng = random.Random(seed)
    for case in range(60):
        document = _random_document(rng)
        for flow, unicode in ((False, True), (True, False), (None, True)):
            text = yaml.safe_dump(
                document,
                default_flow_style=flow,
                allow_unicode=unicode,
                sort_keys=False,
                width=rng.choice([20, 80, 10**6]),
            )
            fast, reference = _both(text)
            assert _same(fast, reference), (seed, case, text)
            assert _same(fast, document), (seed, case, text)


def _small_repository_yaml_files():
    roots = ("packages", "db", "chronicle", "docs", ".github")
    for root in roots:
        for path in sorted((REPO_ROOT / root).rglob("*")):
            if path.suffix in {".yaml", ".yml"} and path.is_file():
                if path.stat().st_size <= SMALL_FILE_BYTES:
                    yield path


def test_loaders_agree_on_every_small_repository_yaml_file():
    files = list(_small_repository_yaml_files())
    # Package manifests, source packages, workflows and governance files.
    assert len(files) > 300
    mismatched = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        fast, reference = _both(text)
        if not _same(fast, reference):
            mismatched.append(str(path.relative_to(REPO_ROOT)))
    assert mismatched == []


def test_chronicle_modules_load_yaml_through_the_shared_loader():
    # A direct yaml.safe_load call would quietly reintroduce the slow parser.
    offenders = []
    for path in sorted((REPO_ROOT / "chronicle").rglob("*.py")):
        if path.name == "yaml_io.py":
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if re.search(r"\byaml\.(safe_load|load)\(", line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert offenders == []
