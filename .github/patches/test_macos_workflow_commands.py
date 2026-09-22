import unittest
from pathlib import Path


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1] / "workflows" / "generator-macos.yml"
)


def named_step(workflow: str, name: str) -> str:
    marker = f"      - name: {name}\n"
    if marker not in workflow:
        raise AssertionError(f"Missing workflow step: {name}")
    step = workflow.split(marker, 1)[1]
    return step.split("      - name:", 1)[0]


def named_job(workflow: str, name: str) -> str:
    marker = f"  {name}:\n"
    if marker not in workflow:
        raise AssertionError(f"Missing workflow job: {name}")
    job = workflow.split(marker, 1)[1]
    lines = []
    for line in job.splitlines():
        if line.startswith("  ") and not line.startswith("    "):
            break
        lines.append(line)
    return "\n".join(lines)


class MacOSWorkflowCommandTests(unittest.TestCase):
    def test_cargo_branding_is_applied_before_customization_validation(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        update_step = named_step(workflow, "Update macOS Info.plist and settings")

        replacements = (
            (
                'description = "RustDesk Remote Desktop"',
                'description = "${{ env.appname }}"',
            ),
            ('ProductName = "RustDesk"', 'ProductName = "${{ env.appname }}"'),
            (
                'FileDescription = "RustDesk Remote Desktop"',
                'FileDescription = "${{ env.appname }}"',
            ),
            (
                'OriginalFilename = "rustdesk.exe"',
                'OriginalFilename = "${{ env.appname }}.exe"',
            ),
        )
        for manifest in ("./Cargo.toml", "./libs/portable/Cargo.toml"):
            for source, target in replacements:
                with self.subTest(manifest=manifest, source=source):
                    self.assertIn(
                        f"sed -i '' -e 's|{source}|{target}|' {manifest}",
                        update_step,
                    )

        self.assertLess(
            workflow.index("      - name: Update macOS Info.plist and settings"),
            workflow.index("      - name: Validate customization"),
        )
        self.assertLess(
            workflow.index("      - name: Validate customization"),
            workflow.index("      - name: Build rustdesk"),
        )

    def test_macos_branding_and_validator_use_the_same_inputs(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        update_step = named_step(workflow, "Update macOS Info.plist and settings")
        validate_step = named_step(workflow, "Validate customization")

        self.assertIn('info["CFBundleName"] = "${{ env.appname }}"', update_step)
        self.assertIn(
            'info["CFBundleDisplayName"] = "${{ env.appname }}"',
            update_step,
        )
        self.assertIn("PRODUCT_NAME = ${{ env.appname }}", update_step)
        self.assertIn('MACOS_BUNDLE_ID="com.rdgen.${BUNDLE_SUFFIX}"', update_step)
        self.assertIn("--platform=macos", validate_step)
        self.assertIn('--app-name="${{ env.appname }}"', validate_step)
        self.assertIn('--macos-bundle-id="com.rdgen.${BUNDLE_SUFFIX}"', validate_step)

    def test_both_architectures_produce_distinct_dmg_names(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        create_step = named_step(workflow, "Create DMG")
        rename_step = named_step(workflow, "Rename rustdesk")
        upload_step = named_step(workflow, "Upload macOS DMG artifact")

        self.assertIn("x86_64-apple-darwin", workflow)
        self.assertIn("aarch64-apple-darwin", workflow)
        self.assertIn('${{ env.appname }}-${{ matrix.job.arch }}.dmg', create_step)
        self.assertIn('${{ env.filename }}-${{ matrix.job.arch }}.dmg', rename_step)
        self.assertIn("uses: actions/upload-artifact@v4", upload_step)
        self.assertIn(
            "name: ${{ env.filename }}-${{ matrix.job.arch }}-dmg",
            upload_step,
        )
        self.assertIn(
            "path: ${{ github.workspace }}/${{ env.filename }}-${{ matrix.job.arch }}.dmg",
            upload_step,
        )
        self.assertIn("retention-days: 1", upload_step)

    def test_generator_cleanup_only_calls_back_for_rdgen_tasks(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        cleanup_step = named_step(workflow, "Finalize and Cleanup zip/json")

        self.assertIn("always()", cleanup_step)
        self.assertIn("env.rdgen == 'true'", cleanup_step)
        self.assertIn("continue-on-error: true", cleanup_step)

    def test_isolated_validation_mode_skips_secrets_and_production_callbacks(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        validate_inputs_job = named_job(workflow, "validate-inputs")
        setup_job = named_job(workflow, "setup")
        build_job = named_job(workflow, "build-for-macos")
        cleanup_job = named_job(workflow, "cleanup")
        validation_step = named_step(workflow, "Load isolated validation inputs")
        download_step = workflow.split("      - uses: actions/download-artifact@v4\n", 1)[1]
        download_step = download_step.split("      - name:", 1)[0]
        load_secrets_step = named_step(workflow, "Load Secrets")
        detect_signing_step = named_step(workflow, "Detect macOS signing certificate")
        default_status_step = named_step(workflow, "Set default status URL")
        rdgen_upload_step = named_step(workflow, "send file to rdgen server")
        api_upload_step = named_step(workflow, "send file to api server")
        global_env = workflow.split("env:\n", 1)[1].split("\njobs:\n", 1)[0]

        self.assertIn("validation_mode:", workflow)
        self.assertIn("type: boolean", workflow)
        self.assertIn("zip_url is required unless validation_mode is enabled", validate_inputs_job)
        self.assertIn("needs: validate-inputs", setup_job)
        self.assertIn("if: ${{ !inputs.validation_mode }}", setup_job)
        self.assertIn("inputs.validation_mode", build_job)
        self.assertIn("needs.validate-inputs.result == 'success'", build_job)
        self.assertIn("needs.setup.result == 'skipped'", build_job)
        self.assertIn("if: ${{ !inputs.validation_mode }}", download_step)
        self.assertIn("if: ${{ !inputs.validation_mode }}", load_secrets_step)
        self.assertIn("if: ${{ inputs.validation_mode }}", validation_step)
        self.assertIn("rdgen=validation", validation_step)
        self.assertIn("appname=MacAudit", validation_step)
        self.assertIn("server=relay.audit.example", validation_step)
        self.assertNotIn("secrets.MACOS_P12_BASE64", global_env)
        self.assertNotIn("secrets.ANDROID_SIGNING_KEY", global_env)
        self.assertNotIn("secrets.SIGN_BASE_URL", global_env)
        self.assertIn("if: ${{ !inputs.validation_mode }}", detect_signing_step)
        self.assertIn("MACOS_P12_BASE64: ${{ secrets.MACOS_P12_BASE64 }}", detect_signing_step)
        self.assertIn("if: ${{ !inputs.validation_mode }}", default_status_step)
        self.assertIn("secrets.GENURL", default_status_step)
        self.assertIn("if: ${{ env.rdgen == 'true' }}", rdgen_upload_step)
        self.assertIn("if: ${{ env.rdgen == 'false' }}", api_upload_step)
        self.assertIn("!inputs.validation_mode", cleanup_job)

    def test_app_bundle_and_dmg_are_verified_before_upload(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        verify_step = named_step(workflow, "Verify macOS app bundle")
        create_step = named_step(workflow, "Create DMG")

        self.assertIn("CFBundleName", verify_step)
        self.assertIn("CFBundleDisplayName", verify_step)
        self.assertIn("CFBundleIdentifier", verify_step)
        self.assertIn("CFBundleExecutable", verify_step)
        self.assertIn("lipo -archs", verify_step)
        self.assertIn("grep -qw x86_64", verify_step)
        self.assertIn("grep -qw arm64", verify_step)
        self.assertIn("codesign --verify --deep --strict", verify_step)
        self.assertIn("hdiutil verify", create_step)

    def test_dmg_rename_is_safe_when_app_and_filename_match(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        rename_step = named_step(workflow, "Rename rustdesk")

        self.assertIn('TARGET_FILE="${{ env.filename }}-${{ matrix.job.arch }}.dmg"', rename_step)
        self.assertIn('[ "$DMG_FILE" != "./$TARGET_FILE" ]', rename_step)
        self.assertIn("DMG already has the requested name", rename_step)
        self.assertIn('test -s "$TARGET_FILE"', rename_step)

    def test_production_p12_is_scoped_to_signing_steps(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        install_step = named_step(workflow, "Install rcodesign tool")
        sign_step = named_step(workflow, "Sign macOS app bundle")
        adhoc_step = named_step(workflow, "Ad-hoc sign macOS app bundle")

        self.assertIn("env.HAS_MACOS_P12 == 'true'", install_step)
        self.assertIn("env.HAS_MACOS_P12 == 'true'", sign_step)
        self.assertIn("MACOS_P12_BASE64: ${{ secrets.MACOS_P12_BASE64 }}", sign_step)
        self.assertIn("/usr/bin/base64 -D", sign_step)
        self.assertIn("env.HAS_MACOS_P12 != 'true'", adhoc_step)


if __name__ == "__main__":
    unittest.main()
