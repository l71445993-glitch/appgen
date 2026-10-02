#!/usr/bin/env python3
"""Dispatch locked smart multi-relay patches by RustDesk version."""
from __future__ import annotations

import argparse
import re
import runpy
import sys
from pathlib import Path


def source_version(source: Path) -> str:
    cargo = (source / "Cargo.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', cargo, re.MULTILINE)
    if not match:
        raise SystemExit("Unable to read RustDesk version from Cargo.toml")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply locked smart multi-relay patches for the checked-out RustDesk version"
    )
    parser.add_argument("--enabled", choices=("true", "false"), required=True)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument(
        "--patches",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    args, unknown = parser.parse_known_args()
    if unknown:
        raise SystemExit(f"Unexpected arguments: {unknown}")

    version = source_version(args.source.resolve())
    patches = args.patches.resolve()
    if version == "1.4.9":
        script = patches / "apply_smart_multi_relay_149.py"
    elif version == "1.5.0":
        script = patches / "apply_smart_multi_relay_150.py"
    else:
        raise SystemExit(
            f"Smart multi-relay is locked to RustDesk 1.4.9 and 1.5.0; got {version}"
        )

    sys.argv = [
        str(script),
        "--enabled",
        args.enabled,
        "--source",
        str(args.source),
        "--patches",
        str(patches),
    ]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
