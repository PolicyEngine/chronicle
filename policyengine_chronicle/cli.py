"""Chronicle CLI entry point."""

from __future__ import annotations

import sys

__all__ = ["main"]


def main() -> None:
    """Dispatch Chronicle commands without eager-loading the DB clients."""
    if sys.argv[1:2] in ([], ["-h"], ["--help"]):
        print(
            "Usage: chronicle <command> [options]\n\n"
            "Common commands:\n"
            "  build-bundle\n"
            "  validate-facts\n"
            "  validate-source-cells\n"
            "  export-consumer-facts\n"
            "  build-consumer-artifact\n"
            "  init\n"
            "  load-source-files\n"
            "  source-stats\n\n"
            "Run `chronicle <command> --help` for command-specific help."
        )
        return

    from chronicle.cli import main as legacy_main

    legacy_main()


if __name__ == "__main__":
    main()
