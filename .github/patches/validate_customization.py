from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path.cwd()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--platform",
        choices=("windows", "linux", "sciter", "android", "macos"),
        required=True,
    )
    parser.add_argument("--server", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--api-server", required=True)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--url-link", required=True)
    parser.add_argument("--download-link", required=True)
    parser.add_argument("--android-app-id")
    parser.add_argument("--macos-bundle-id")
    return parser.parse_args()


def read(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.is_file():
        raise SystemExit(f"Required customization file is missing: {relative_path}")
    return path.read_text(encoding="utf-8")


def require(relative_path: str, value: str, label: str) -> None:
    if value not in read(relative_path):
        raise SystemExit(f"{label} was not applied to {relative_path}")


def main() -> None:
    args = parse_args()
    company = args.company.replace(r"\&", "&")
    require("libs/hbb_common/src/config.rs", args.server, "Rendezvous server")
    require("libs/hbb_common/src/config.rs", args.key, "Server public key")
    require("src/common.rs", args.api_server, "API server")

    if args.platform == "sciter":
        require("src/ui/index.tis", args.url_link, "Sciter website URL")
        require("src/ui/index.tis", args.download_link, "Sciter download URL")
    elif args.platform == "android":
        require(
            "flutter/lib/mobile/pages/settings_page.dart",
            args.url_link,
            "Android website URL",
        )
        require(
            "flutter/lib/mobile/pages/connection_page.dart",
            args.download_link,
            "Android download URL",
        )
    else:
        require(
            "flutter/lib/desktop/pages/desktop_setting_page.dart",
            args.url_link,
            "Desktop website URL",
        )
        require(
            "flutter/lib/desktop/pages/desktop_home_page.dart",
            args.download_link,
            "Desktop download URL",
        )

    if args.app_name != "rustdesk":
        require("Cargo.toml", args.app_name, "Application name")
        require("libs/portable/Cargo.toml", args.app_name, "Portable application name")
        if args.platform == "macos":
            require(
                "flutter/macos/Runner/Configs/AppInfo.xcconfig",
                args.app_name,
                "macOS application name",
            )
        elif args.platform == "android":
            require(
                "flutter/android/app/src/main/AndroidManifest.xml",
                args.app_name,
                "Android application name",
            )
        elif args.platform == "windows":
            require(
                "flutter/windows/runner/Runner.rc",
                args.app_name,
                "Flutter Windows application name",
            )

    if company != "Purslane Tech Pte. Ltd.":
        require("Cargo.toml", company, "Company name")
        require("libs/portable/Cargo.toml", company, "Portable company name")
        if args.platform == "sciter":
            require("src/ui/index.tis", company, "Sciter company name")
        elif args.platform == "macos":
            require(
                "flutter/macos/Runner/Configs/AppInfo.xcconfig",
                company,
                "macOS company name",
            )
        elif args.platform == "android":
            require("Cargo.toml", company, "Android build company name")
        elif args.platform in {"windows", "linux"}:
            require(
                "flutter/lib/desktop/pages/desktop_setting_page.dart",
                company,
                "Flutter company name",
            )

    if args.platform == "android" and args.android_app_id:
        require(
            "flutter/android/app/build.gradle",
            f'applicationId "{args.android_app_id}"',
            "Android application ID",
        )

    if args.platform == "macos" and args.macos_bundle_id:
        require(
            "flutter/macos/Runner/Configs/AppInfo.xcconfig",
            f"PRODUCT_BUNDLE_IDENTIFIER = {args.macos_bundle_id}",
            "macOS bundle ID",
        )
        project = read("flutter/macos/Runner.xcodeproj/project.pbxproj")
        expected = f"PRODUCT_BUNDLE_IDENTIFIER = {args.macos_bundle_id};"
        if project.count(expected) != 3:
            raise SystemExit(
                "macOS bundle ID was not applied to all three Xcode configurations"
            )

    print(
        f"Validated {args.platform} server, key, API, branding, and URL customization"
    )


if __name__ == "__main__":
    main()
