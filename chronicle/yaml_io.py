"""YAML loading for Chronicle's declarative files.

Source packages, artifact manifests and the PE source plan all read YAML, and
the packages tree alone holds about 141 MB of it. PyYAML's pure-Python
``SafeLoader`` is the slow part of reading it. On 2026-10-08 it took 110 s on
an Apple-silicon laptop to parse every ``packages/**/*.yaml`` file, where
libyaml took 20 s. On a GitHub-hosted runner testing a branch with 314 MB of
package YAML, each of the three tests in
``tests/test_chronicle_pe_source_plan.py`` that parse the whole tree once took
467-474 s.

``yaml.CSafeLoader`` is ``CParser`` (libyaml's scanner, parser and composer)
combined with the same ``SafeConstructor`` and ``Resolver`` classes that
``yaml.SafeLoader`` uses (see ``yaml/cyaml.py``). Only the text-to-node parse
moves to C; implicit typing and object construction run the same Python code.
All 280 package files and the 283 other tracked YAML files loaded to equal,
same-typed objects under both loaders, and ``tests/test_yaml_io.py`` keeps a
differential check on edge cases, generated documents and the small files.

PyYAML built without libyaml has no ``CSafeLoader``; loading then falls back to
the pure-Python loader, which is correct but slow. The test suite fails on
GitHub Actions if that happens, so CI cannot lose the speedup silently.
"""

from __future__ import annotations

from typing import Any

import yaml

SafeLoader: type = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def safe_load(stream: Any) -> Any:
    """Parse one YAML document exactly as ``yaml.safe_load`` does, faster.

    ``stream`` may be a string, bytes or an open file, as for ``yaml.safe_load``.
    """
    return yaml.load(stream, Loader=SafeLoader)
