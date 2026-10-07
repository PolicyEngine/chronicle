"""Chronicle's canonical name for a UK geography identifier.

Chronicle keeps each publisher's own text for an area (chronicle#266), and the
publishers disagree: HMRC appends " UA" to every English unitary, DWP writes
Welsh authorities bilingually, MHCLG drops ", City of", and two ONS packages
spell one region two ways. Microcosm's calibration hierarchy refuses a target
whose member facts name one geography twice, so the first target that spans two
such packages is refused upstream (chronicle#281).

The register answers with one name per identifier. It is a publisher's name and
not PolicyEngine's: every entry is read from an ONS lookup artifact Chronicle
already pins, by ``scripts/build_uk_geography_register.py``. An exported fact
carries that name as its ``geography.name`` and the publisher's own text as
``geography.publisher_name``, so nothing is lost and a consumer still sees one
name per area. Identifiers the register does not cover keep the publisher's
name, which is what the bundle's ``conflicting_geography_name_across_packages``
warning then reports: the areas the register has yet to reach.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

REGISTER_PATH = Path(__file__).with_name("geography") / "uk_canonical_names.json"


@cache
def _register() -> Mapping[str, str]:
    payload = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    return MappingProxyType(dict(payload["names"]))


@cache
def _levels() -> Mapping[str, str]:
    payload = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    return MappingProxyType(dict(payload["levels"]))


def canonical_geography_name(geography_id: str | None) -> str | None:
    """Return the register's name for *geography_id*, or None if it has none.

    The lookup is by identifier alone. A GSS identifier names one area at one
    level, so a package that states the wrong level for a known identifier
    still gets the right name, and a package that states an identifier the
    register does not carry keeps its publisher's text.
    """

    if not geography_id:
        return None
    return _register().get(str(geography_id).strip())


def canonical_geography_level(geography_id: str | None) -> str | None:
    """Return the level the register's source artifact states for an area."""

    if not geography_id:
        return None
    return _levels().get(str(geography_id).strip())


def register_size() -> int:
    """Return how many identifiers the register names."""

    return len(_register())
