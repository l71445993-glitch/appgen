from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", required=True)
    parser.add_argument("--filename", required=True)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--without-beijing-runtime", action="store_true")
    return parser.parse_args()


def customize(
    path: Path,
    filename: str,
    app_name: str,
    include_beijing_runtime: bool = True,
) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]+", filename):
        raise SystemExit(f"Invalid AppImage executable name: {filename!r}")
    text = path.read_text(encoding="utf-8")
    shim_path = f"$APPDIR/usr/lib/{filename}/librustdesk_no_sysvipc.so"
    preload_line = f"      LD_PRELOAD: {shim_path}\n"
    expected = (
        f"    exec: usr/share/{filename}/{filename}\n",
        f"    id: {json.dumps(filename)}\n",
        f"    icon: {json.dumps(filename)}\n",
        f"    name: {json.dumps(app_name, ensure_ascii=False)}\n",
    )
    if all(value in text for value in expected):
        if include_beijing_runtime != (preload_line in text):
            raise SystemExit("AppImage runtime mode does not match the requested mode")
        print(f"AppImage recipe is already customized in {path}")
        return
    replacements = {
        "bsdtar -zxvf rustdesk.deb": f"bsdtar -zxvf {filename}.deb",
        "/apps/rustdesk.png": f"/apps/{filename}.png",
        "/apps/rustdesk.svg": f"/apps/{filename}.svg",
        "    id: rustdesk\n": f"    id: {json.dumps(filename)}\n",
        "    name: rustdesk\n": f"    name: {json.dumps(app_name, ensure_ascii=False)}\n",
        "    icon: rustdesk\n": f"    icon: {json.dumps(filename)}\n",
        "    exec: usr/share/rustdesk/rustdesk\n": (
            f"    exec: usr/share/{filename}/{filename}\n"
        ),
        "$APPDIR/usr/share/rustdesk/lib": f"$APPDIR/usr/share/{filename}/lib",
    }
    for old, new in replacements.items():
        if old not in text:
            raise SystemExit(f"Unable to identify AppImage field: {old!r}")
        text = text.replace(old, new)
    if include_beijing_runtime:
        env_marker = "  runtime:\n    env:\n"
        if text.count(env_marker) != 1:
            raise SystemExit("Unable to identify AppImage runtime environment")
        env = "".join(
            f"      {key}: {value}\n"
            for key, value in {
                "LD_PRELOAD": shim_path,
                "RUSTDESK_NO_SYSVIPC_SHIM_LOG": "0",
                "RUSTDESK_UINPUT_INPUT_FALLBACK": "0",
                "RUSTDESK_UINPUT_INPUT_LOG": "1",
                "RUSTDESK_XCB_MOUSE_FALLBACK": "1",
                "RUSTDESK_UINPUT_MOUSE_MODE": "anchor",
                "RUSTDESK_UINPUT_MOUSE_REL_SCALE": "2",
                "RUSTDESK_UINPUT_WIDTH": "1024",
                "RUSTDESK_UINPUT_HEIGHT": "600",
                "RUSTDESK_FORCE_CM_NO_UI": "1",
                "RUSTDESK_DISABLE_TRAY": "1",
                "RUSTDESK_PREWARM_CM_NO_UI": "1",
            }.items()
        )
        text = text.replace(env_marker, env_marker + env, 1)
    path.write_text(text, encoding="utf-8")
    print(f"Customized AppImage recipe in {path}")


def main() -> None:
    args = parse_args()
    customize(
        Path(args.recipe),
        args.filename,
        args.app_name,
        not args.without_beijing_runtime,
    )


if __name__ == "__main__":
    main()
