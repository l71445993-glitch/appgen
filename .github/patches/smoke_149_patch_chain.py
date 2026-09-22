from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


CHAINS = {
    "windows": [
        ("allowCustom.py", []),
        ("remove_setup_server_tip.py", []),
        ("delay_fix.py", []),
        ("cycle_monitor.py", []),
        ("xoffline.py", []),
        ("remove_new_version_notif.py", []),
        ("hidecm.py", []),
        ("hide_settings_menu.py", []),
        ("hide_network_setting.py", []),
        ("runtime_features.py", ["--copy-id-password", "--manual-temporary-password", "--show-start-on-boot"]),
        ("remove_recent_sessions.py", []),
        ("force_disable_file_transfer.py", []),
        ("silent_install.py", []),
        ("silent_agent_mode.py", []),
        ("incoming_compact.py", ["--width", "260", "--height", "360"]),
    ],
    "windows-x86": [
        ("allowCustom.py", []),
        ("remove_setup_server_tip.py", []),
        ("delay_fix.py", []),
        ("remove_new_version_notif.py", []),
        ("hidecm.py", []),
        ("hide_settings_menu.py", []),
        ("hide_network_setting.py", []),
        ("remove_recent_sessions.py", []),
        ("force_disable_file_transfer.py", []),
        ("silent_install.py", []),
        ("silent_agent_mode.py", []),
    ],
    "linux": [
        ("allowCustom.py", ["--linux-uri-filename", "SmokeClient"]),
        ("remove_setup_server_tip.py", []),
        ("delay_fix.py", []),
        ("cycle_monitor.py", []),
        ("xoffline.py", []),
        ("hidecm.py", []),
        ("hide_settings_menu.py", []),
        ("hide_network_setting.py", []),
        ("runtime_features.py", ["--copy-id-password", "--manual-temporary-password"]),
        ("remove_recent_sessions.py", []),
        ("remove_new_version_notif.py", []),
        ("force_disable_file_transfer.py", []),
        ("incoming_compact.py", ["--width", "260", "--height", "360"]),
    ],
    "macos": [
        ("allowCustom.py", []),
        ("remove_setup_server_tip.py", []),
        ("delay_fix.py", []),
        ("cycle_monitor.py", []),
        ("xoffline.py", []),
        ("hidecm.py", []),
        ("hide_settings_menu.py", []),
        ("hide_network_setting.py", []),
        ("runtime_features.py", ["--copy-id-password", "--manual-temporary-password"]),
        ("remove_recent_sessions.py", []),
        ("remove_new_version_notif.py", []),
        ("force_disable_file_transfer.py", []),
        ("incoming_compact.py", ["--width", "260", "--height", "360"]),
    ],
    "android": [
        ("allowCustom.py", []),
        ("android_custom_config.py", []),
        ("delay_fix.py", []),
        ("xoffline.py", []),
        ("remove_new_version_notif.py", []),
        ("force_disable_file_transfer.py", []),
    ],
}


def validate_platform_result(platform: str, source: Path) -> None:
    if platform == "android":
        return
    flutter_settings = (
        source / "flutter/lib/desktop/pages/desktop_setting_page.dart"
    ).read_text(encoding="utf-8")
    flutter_model = (source / "flutter/lib/models/server_model.dart").read_text(
        encoding="utf-8"
    )
    if "key: 'allow-hide-cm', value: b ? 'Y' : 'N'" not in flutter_settings:
        raise SystemExit("Flutter hide connection window toggle does not persist N")
    reset_marker = "key: 'allow-hide-cm', value: 'N'"
    if flutter_model.count(reset_marker) != 2:
        raise SystemExit("Flutter hide connection window resets do not persist N")

    if platform != "windows-x86":
        return
    sciter_settings = (source / "src/ui/index.tis").read_text(encoding="utf-8")
    markers = (
        "<li #allow-hide-cm ",
        "var can_hide_cm = mode == 'password' &&",
        "function resetHideCmIfUnavailable()",
        "if (me.id == 'allow-hide-cm')",
        "handler.set_option('allow-hide-cm', 'N');",
        "'allow-hide-cm', enabled ? 'N' : 'Y');",
    )
    missing = [marker for marker in markers if marker not in sciter_settings]
    if missing:
        raise SystemExit(
            "Sciter hide connection window controls are incomplete: "
            + ", ".join(missing)
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=CHAINS, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--patches", type=Path, required=True)
    parser.add_argument("--passes", type=int, default=2)
    args = parser.parse_args()

    source = args.source.resolve()
    patches = args.patches.resolve()
    if not (source / "Cargo.toml").is_file():
        raise SystemExit(f"RustDesk source root is invalid: {source}")

    for pass_number in range(1, args.passes + 1):
        for script_name, script_args in CHAINS[args.platform]:
            command = [sys.executable, str(patches / script_name), *script_args]
            print(f"[{args.platform} pass {pass_number}] {script_name}", flush=True)
            subprocess.run(command, cwd=source, check=True)
        validate_platform_result(args.platform, source)


if __name__ == "__main__":
    main()
