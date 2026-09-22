from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path.cwd()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patches", type=Path, required=True)
    return parser.parse_args()


def source_version() -> str:
    cargo = (ROOT / "Cargo.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', cargo, re.MULTILINE)
    if not match:
        raise SystemExit("Unable to read RustDesk version from Cargo.toml")
    return match.group(1)


def apply(patch: Path, includes: tuple[str, ...] = ()) -> None:
    command = ["git", "apply"]
    command.extend(f"--include={path}" for path in includes)
    command.append(str(patch.resolve()))
    subprocess.run(command, cwd=ROOT, check=True)


def run(script: Path) -> None:
    subprocess.run([sys.executable, str(script.resolve())], cwd=ROOT, check=True)


def main() -> None:
    args = parse_args()
    patches = args.patches.resolve()
    version = source_version()

    if version == "1.4.9":
        apply(patches / "rustdesk_default_linux_149.diff")
    else:
        legacy = patches / "rustdesk_default_linux.diff"
        if version == "1.4.7":
            apply(
                legacy,
                (
                    "libs/enigo/src/linux/nix_impl.rs",
                    "libs/scrap/src/x11/capturer.rs",
                    "libs/scrap/src/x11/ffi.rs",
                    "res/rustdesk.service",
                    "src/core_main.rs",
                ),
            )
            run(patches / "beijing_linux_147_compat.py")
        else:
            apply(legacy)
            apply(patches / "mrkj_legacy_uinput_keyboard.diff")

    run(patches / "mrkj_linux_fast_service.py")
    run(patches / "mrkj_linux_x11_mouse_uinput_keyboard.py")
    print(f"Applied Beijing Linux base fixes for RustDesk {version}")


if __name__ == "__main__":
    main()
