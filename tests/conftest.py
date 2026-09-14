"""Shared pytest configuration for Chronicle tests."""

from __future__ import annotations

import shutil

import pytest


@pytest.fixture
def tmp_path(tmp_path):
    """Remove everything a test wrote under ``tmp_path`` once it finishes.

    Several tests build real source-package suites and merged bundles under
    ``tmp_path``; the merged consumer bundle alone writes about 14 GB of nested
    suites. pytest keeps the three newest ``pytest-N`` base directories and only
    prunes older ones when no other pytest session holds a lock on them, so with
    many sessions running concurrently the outputs accumulate for days. Deleting
    the per-test directory here keeps the base temp directory bounded regardless
    of how many sessions are active.
    """
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)
