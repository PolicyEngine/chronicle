"""Strict geography-vintage contracts for Belgian subnational facts.

Chronicle preserves the geography codes asserted by a publisher. This module
compiles those identities into join keys only after a consumer declares the
code-set vintage it expects. It can translate NIS identities through a
publisher-backed crosswalk, but it deliberately never combines or changes fact
values.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping


class GeographyVintageError(ValueError):
    """Base error for a geography-vintage compile failure."""


class GeographyVintageMissingError(GeographyVintageError):
    """Raised when a subnational record omits its code-set vintage."""


class GeographyVintageMismatchError(GeographyVintageError):
    """Raised when a record and consumer declare different vintages."""


class NISCrosswalkError(ValueError):
    """Raised when a NIS crosswalk is malformed or internally ambiguous."""


class NISCrosswalkLookupError(NISCrosswalkError):
    """Raised when a requested NIS translation is not publisher-declared."""


@dataclass(frozen=True)
class GeographyVintageDeclaration:
    """The exact geography code set a consumer is prepared to join."""

    level: str
    vintage: str

    def __post_init__(self) -> None:
        if not self.level.strip():
            raise GeographyVintageError("Geography level must be non-empty")
        if not self.vintage.strip():
            raise GeographyVintageError("Geography vintage must be non-empty")


@dataclass(frozen=True)
class GeographyJoinKey:
    """A join key whose vintage has passed the consumer declaration gate."""

    level: str
    geography_id: str
    vintage: str


@dataclass(frozen=True)
class NISCodeTranslation:
    """One publisher-declared NIS identity translation, without fact values."""

    source_nis: str
    source_name: str
    source_vintage: str
    target_nis: str
    target_name: str
    target_vintage: str
    effective_date: date
    relationship: str
    source_url: str


def compile_geography_keys(
    records: Iterable[Any],
    declaration: GeographyVintageDeclaration,
) -> tuple[GeographyJoinKey, ...]:
    """Compile exact-vintage join keys or fail before a partial join.

    ``records`` may contain Chronicle ``AggregateFact`` objects or consumer-fact
    mappings. Records at another geography level are rejected, rather than
    silently discarded, because dropping them would make a partial join look
    successful.
    """

    keys: list[GeographyJoinKey] = []
    missing_ids: list[str] = []
    wrong_levels: dict[str, list[str]] = {}
    wrong_vintages: dict[str, list[str]] = {}

    for record in records:
        level, geography_id, vintage = _geography_parts(record)
        if level != declaration.level:
            wrong_levels.setdefault(level or "<missing>", []).append(geography_id)
            continue
        if not vintage:
            missing_ids.append(geography_id)
            continue
        if vintage != declaration.vintage:
            wrong_vintages.setdefault(vintage, []).append(geography_id)
            continue
        keys.append(
            GeographyJoinKey(
                level=level,
                geography_id=geography_id,
                vintage=vintage,
            )
        )

    if wrong_levels:
        details = _format_groups(wrong_levels)
        raise GeographyVintageMismatchError(
            f"Expected geography level {declaration.level!r}; received {details}"
        )
    if missing_ids:
        ids = ", ".join(sorted(set(missing_ids)))
        raise GeographyVintageMissingError(
            "Subnational geography vintage is required for "
            f"{declaration.level!r} records: {ids}"
        )
    if wrong_vintages:
        details = _format_groups(wrong_vintages)
        raise GeographyVintageMismatchError(
            f"Expected geography vintage {declaration.vintage!r} for "
            f"level {declaration.level!r}; received {details}"
        )
    return tuple(keys)


class NISCodeCrosswalk:
    """A validated, immutable index of publisher-declared NIS code changes."""

    def __init__(self, rows: Iterable[NISCodeTranslation]) -> None:
        translations = tuple(rows)
        if not translations:
            raise NISCrosswalkError("NIS crosswalk must contain at least one row")

        by_source: dict[tuple[str, str, str], NISCodeTranslation] = {}
        for row in translations:
            _validate_translation(row)
            key = (row.source_vintage, row.target_vintage, row.source_nis)
            prior = by_source.get(key)
            if prior is not None and prior != row:
                raise NISCrosswalkError(
                    "Ambiguous NIS crosswalk mapping for "
                    f"{row.source_nis!r} from {row.source_vintage!r} to "
                    f"{row.target_vintage!r}"
                )
            by_source[key] = row

        self._rows = translations
        self._by_source = by_source

    @classmethod
    def from_csv(cls, path: str | Path) -> NISCodeCrosswalk:
        """Load and validate the complete publisher-backed crosswalk CSV."""

        input_path = Path(path)
        with input_path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            required = {
                "source_nis",
                "source_name",
                "source_vintage",
                "target_nis",
                "target_name",
                "target_vintage",
                "effective_date",
                "relationship",
                "source_url",
            }
            missing = sorted(required - set(reader.fieldnames or ()))
            if missing:
                raise NISCrosswalkError(
                    "NIS crosswalk is missing columns: " + ", ".join(missing)
                )
            rows = []
            for line_number, payload in enumerate(reader, start=2):
                try:
                    rows.append(
                        NISCodeTranslation(
                            source_nis=payload["source_nis"].strip(),
                            source_name=payload["source_name"].strip(),
                            source_vintage=payload["source_vintage"].strip(),
                            target_nis=payload["target_nis"].strip(),
                            target_name=payload["target_name"].strip(),
                            target_vintage=payload["target_vintage"].strip(),
                            effective_date=date.fromisoformat(
                                payload["effective_date"].strip()
                            ),
                            relationship=payload["relationship"].strip(),
                            source_url=payload["source_url"].strip(),
                        )
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise NISCrosswalkError(
                        f"Invalid NIS crosswalk row at line {line_number}: {error}"
                    ) from error
        return cls(rows)

    @property
    def rows(self) -> tuple[NISCodeTranslation, ...]:
        """Return all validated publisher rows in source order."""

        return self._rows

    def translate(
        self,
        source_nis: str,
        *,
        source_vintage: str,
        target_vintage: str,
    ) -> NISCodeTranslation:
        """Return one declared code translation or fail on missing coverage."""

        key = (source_vintage, target_vintage, source_nis)
        try:
            return self._by_source[key]
        except KeyError as error:
            raise NISCrosswalkLookupError(
                "No NIS crosswalk row for "
                f"{source_nis!r} from {source_vintage!r} to {target_vintage!r}"
            ) from error

    def translation_plan(
        self,
        source_ids: Iterable[str],
        *,
        source_vintage: str,
        target_vintage: str,
    ) -> tuple[NISCodeTranslation, ...]:
        """Compile identity translations without reconciling or summing values."""

        return tuple(
            self.translate(
                source_id,
                source_vintage=source_vintage,
                target_vintage=target_vintage,
            )
            for source_id in source_ids
        )


def _geography_parts(record: Any) -> tuple[str, str, str | None]:
    if isinstance(record, Mapping):
        geography = record.get("geography", record)
        if not isinstance(geography, Mapping):
            raise GeographyVintageError("Record geography must be a mapping")
        level = _required_geography_text(geography, "level")
        geography_id = _required_geography_text(geography, "id")
        vintage_value = geography.get("vintage")
    else:
        try:
            geography = record.geography
            level = str(geography.level).strip()
            geography_id = str(geography.id).strip()
            vintage_value = geography.vintage
        except AttributeError as error:
            raise GeographyVintageError(
                "Record must expose geography or be a geography mapping"
            ) from error
        if not level or not geography_id:
            raise GeographyVintageError(
                "Record geography level and id must be non-empty"
            )
    vintage = str(vintage_value).strip() if vintage_value is not None else None
    return level, geography_id, vintage or None


def _required_geography_text(geography: Mapping[str, Any], field: str) -> str:
    value = geography.get(field)
    text = str(value).strip() if value is not None else ""
    if not text:
        raise GeographyVintageError(
            f"Record geography field {field!r} must be non-empty"
        )
    return text


def _validate_translation(row: NISCodeTranslation) -> None:
    for field_name in ("source_nis", "target_nis"):
        code = getattr(row, field_name)
        if len(code) != 5 or not code.isascii() or not code.isdigit():
            raise NISCrosswalkError(
                f"{field_name} must be a five-digit NIS code: {code!r}"
            )
    for field_name in (
        "source_name",
        "source_vintage",
        "target_name",
        "target_vintage",
    ):
        if not getattr(row, field_name).strip():
            raise NISCrosswalkError(f"{field_name} must be non-empty")
    if row.relationship not in {"merged", "unchanged"}:
        raise NISCrosswalkError(
            f"Unsupported NIS relationship: {row.relationship!r}"
        )
    if row.relationship == "unchanged" and row.source_nis != row.target_nis:
        raise NISCrosswalkError(
            "An unchanged NIS relationship must preserve the code: "
            f"{row.source_nis!r} -> {row.target_nis!r}"
        )
    if not row.source_url.startswith("https://statbel.fgov.be/"):
        raise NISCrosswalkError(
            "NIS crosswalk rows must cite a public Statbel publisher URL: "
            f"{row.source_url!r}"
        )


def _format_groups(groups: Mapping[str, list[str]]) -> str:
    return "; ".join(
        f"{group!r} for {', '.join(sorted(set(ids)))}"
        for group, ids in sorted(groups.items())
    )
