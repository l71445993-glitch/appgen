import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


VALIDATOR = Path(__file__).resolve().parent / "validate_customization.py"


class MacOSCustomizationValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.bundle_id = "com.rdgen.audit-client"
        self.values = {
            "server": "relay.audit.example",
            "key": "audit-public-key",
            "api": "https://api.audit.example",
            "app": "AuditDesk",
            "company": "Audit Company",
            "url": "https://audit.example",
            "download": "https://audit.example/download",
        }
        self._write_valid_tree()

    def tearDown(self):
        self.temp_dir.cleanup()

    def write(self, relative_path: str, content: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _write_valid_tree(self) -> None:
        cargo_branding = f'{self.values["app"]}\n{self.values["company"]}\n'
        self.write(
            "libs/hbb_common/src/config.rs",
            f'{self.values["server"]}\n{self.values["key"]}\n',
        )
        self.write("src/common.rs", f'{self.values["api"]}\n')
        self.write(
            "flutter/lib/desktop/pages/desktop_setting_page.dart",
            f'{self.values["url"]}\n',
        )
        self.write(
            "flutter/lib/desktop/pages/desktop_home_page.dart",
            f'{self.values["download"]}\n',
        )
        self.write("Cargo.toml", cargo_branding)
        self.write("libs/portable/Cargo.toml", cargo_branding)
        self.write(
            "flutter/macos/Runner/Configs/AppInfo.xcconfig",
            "\n".join(
                (
                    f'PRODUCT_NAME = {self.values["app"]}',
                    f'PRODUCT_BUNDLE_IDENTIFIER = {self.bundle_id}',
                    self.values["company"],
                )
            ),
        )
        self.write(
            "flutter/macos/Runner.xcodeproj/project.pbxproj",
            (f"PRODUCT_BUNDLE_IDENTIFIER = {self.bundle_id};\n" * 3),
        )

    def run_validator(self):
        return subprocess.run(
            (
                sys.executable,
                str(VALIDATOR),
                "--platform=macos",
                f'--server={self.values["server"]}',
                f'--key={self.values["key"]}',
                f'--api-server={self.values["api"]}',
                f'--app-name={self.values["app"]}',
                f'--company={self.values["company"]}',
                f'--url-link={self.values["url"]}',
                f'--download-link={self.values["download"]}',
                f"--macos-bundle-id={self.bundle_id}",
            ),
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_complete_macos_customization_passes(self):
        result = self.run_validator()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Validated macos", result.stdout)

    def test_portable_cargo_must_contain_application_name(self):
        self.write("libs/portable/Cargo.toml", f'{self.values["company"]}\n')

        result = self.run_validator()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Portable application name was not applied",
            result.stderr,
        )

    def test_macos_app_info_must_contain_application_name(self):
        self.write(
            "flutter/macos/Runner/Configs/AppInfo.xcconfig",
            "\n".join(
                (
                    "PRODUCT_NAME = RustDesk",
                    f"PRODUCT_BUNDLE_IDENTIFIER = {self.bundle_id}",
                    self.values["company"],
                )
            ),
        )

        result = self.run_validator()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("macOS application name was not applied", result.stderr)

    def test_default_rustdesk_name_does_not_require_cargo_branding(self):
        self.values["app"] = "rustdesk"
        self.write("Cargo.toml", f'{self.values["company"]}\n')
        self.write("libs/portable/Cargo.toml", f'{self.values["company"]}\n')
        self.write(
            "flutter/macos/Runner/Configs/AppInfo.xcconfig",
            "\n".join(
                (
                    "PRODUCT_NAME = rustdesk",
                    f"PRODUCT_BUNDLE_IDENTIFIER = {self.bundle_id}",
                    self.values["company"],
                )
            ),
        )

        result = self.run_validator()

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bundle_id_must_cover_all_xcode_configurations(self):
        self.write(
            "flutter/macos/Runner.xcodeproj/project.pbxproj",
            (f"PRODUCT_BUNDLE_IDENTIFIER = {self.bundle_id};\n" * 2),
        )

        result = self.run_validator()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "macOS bundle ID was not applied to all three Xcode configurations",
            result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
