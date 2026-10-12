"""ETL loaders that populate Chronicle target inputs."""

from db.etl_snap import load_snap_targets
from db.etl_soi import load_soi_targets

__all__ = [
    "load_snap_targets",
    "load_soi_targets",
]
