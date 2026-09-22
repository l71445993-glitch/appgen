import unittest
from pathlib import Path


WORKFLOW_DIR = Path(__file__).resolve().parents[1] / "workflows"
SMART_WORKFLOWS = {
    "generator-windows.yml": (
        "Stage smart multi-relay patch bundle",
        "Restore bridge files",
    ),
    "generator-windows-x86.yml": (
        "Stage smart multi-relay patch bundle",
        "Install ImageMagick on Windows",
    ),
    "generator-linux.yml": (
        "Stage smart multi-relay patch bundle",
        "Set Swap Space",
    ),
    "generator-android.yml": (
        "Stage customization patches",
        "Install flutter",
    ),
}


def named_step(workflow: str, name: str) -> str:
    marker = f"      - name: {name}\n"
    if marker not in workflow:
        raise AssertionError(f"Missing workflow step: {name}")
    step = workflow.split(marker, 1)[1]
    return step.split("      - name:", 1)[0]


class SmartMultiRelayWorkflowTests(unittest.TestCase):
    def test_lifecycle_invalidation_reuses_the_generated_bridge_contract(self):
        root_patch = (
            Path(__file__).resolve().parent / "smart_multi_relay_149_root.diff"
        ).read_text(encoding="utf-8")
        self.assertIn("unawaited(bind.mainCheckConnectStatus());", root_patch)
        self.assertIn(
            "failed to invalidate smart relay network state: {error}",
            root_patch,
        )
        self.assertNotIn("mainNotifyNetworkChanged", root_patch)

        hbb_patch = (
            Path(__file__).resolve().parent / "smart_multi_relay_149_hbb_common.diff"
        ).read_text(encoding="utf-8")
        self.assertIn("configured_api_server_for_websocket", hbb_patch)
        self.assertIn("hard_api_server_is_used_when_config_api_is_empty", hbb_patch)

    def test_supported_workflows_apply_only_the_locked_true_path(self):
        for workflow_name, (stage_name, first_following_step) in SMART_WORKFLOWS.items():
            with self.subTest(workflow=workflow_name):
                workflow = (WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8")
                stage = named_step(workflow, stage_name)
                apply = named_step(workflow, "Apply locked smart multi-relay patch")

                if stage_name == "Stage smart multi-relay patch bundle":
                    self.assertIn("env.smartMultiRelay == 'true'", stage)
                self.assertIn("env.smartMultiRelay == 'true'", apply)
                self.assertIn("apply_smart_multi_relay_149.py", apply)
                self.assertIn("--enabled true", apply)
                self.assertIn("--source .", apply)
                self.assertIn("--patches", apply)
                self.assertNotIn("continue-on-error", apply)

                stage_index = workflow.index(f"      - name: {stage_name}")
                apply_index = workflow.index(
                    "      - name: Apply locked smart multi-relay patch"
                )
                checkout_indices = []
                offset = 0
                checkout_marker = "      - name: Checkout source code"
                while True:
                    index = workflow.find(checkout_marker, offset)
                    if index < 0:
                        break
                    checkout_indices.append(index)
                    offset = index + len(checkout_marker)
                checkouts_before_apply = [
                    index for index in checkout_indices if index < apply_index
                ]
                self.assertGreaterEqual(len(checkouts_before_apply), 2)
                self.assertLess(stage_index, min(checkouts_before_apply))
                self.assertLess(
                    apply_index,
                    workflow.index(f"      - name: {first_following_step}"),
                )

    def test_smart_patch_bundle_is_complete_and_macos_is_excluded(self):
        patches = Path(__file__).resolve().parent
        for name in (
            "apply_smart_multi_relay_149.py",
            "smart_multi_relay_149_root.diff",
            "smart_multi_relay_149_hbb_common.diff",
        ):
            self.assertTrue((patches / name).is_file(), name)

        macos = (WORKFLOW_DIR / "generator-macos.yml").read_text(encoding="utf-8")
        self.assertNotIn("smartMultiRelay", macos)
        self.assertNotIn("apply_smart_multi_relay_149.py", macos)

    def test_release_validation_uses_private_actions_artifacts(self):
        fetch = (WORKFLOW_DIR / "fetch-encrypted-secrets.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Download prepared release inputs", fetch)
        self.assertIn("source == 'actions-artifact'", fetch)
        self.assertIn("run-id: ${{ fromJSON(inputs.zip_url_json).run_id }}", fetch)
        self.assertIn("github-token: ${{ github.token }}", fetch)
        self.assertIn("source != 'actions-artifact'", fetch)

        release = (WORKFLOW_DIR / "smart-release-validation.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("actions: write", release)
        self.assertIn('"api-server": api_server', release)
        self.assertIn('"allow-websocket": "Y"', release)
        self.assertIn('"allow-insecure-tls-fallback": "N"', release)
        self.assertIn('"smartMultiRelay": "true"', release)
        self.assertIn('"beijingCustom": false', release)
        self.assertIn('"rdgen": "validation"', release)
        self.assertIn('"source": "actions-artifact"', release)
        for workflow_name in SMART_WORKFLOWS:
            self.assertIn(f'"{workflow_name}"', release)

    def test_release_validation_never_calls_generator_cleanup(self):
        for workflow_name in SMART_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8")
                cleanup_count = workflow.count("Finalize and Cleanup zip/json")
                self.assertGreaterEqual(cleanup_count, 1)
                self.assertEqual(
                    workflow.count("always() && env.rdgen != 'validation'"),
                    cleanup_count,
                )

    def test_release_validation_retains_installable_artifacts(self):
        expected_steps = {
            "generator-windows.yml": "Upload validation Windows x64 artifacts",
            "generator-windows-x86.yml": "Upload validation Windows x86 artifact",
            "generator-linux.yml": "Upload validation AppImage",
            "generator-android.yml": "Upload validation universal APK",
        }
        for workflow_name, step_name in expected_steps.items():
            with self.subTest(workflow=workflow_name):
                workflow = (WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8")
                step = named_step(workflow, step_name)
                self.assertIn("env.rdgen == 'validation'", step)
                self.assertIn("actions/upload-artifact@v4", step)
                self.assertIn("if-no-files-found: error", step)
                self.assertIn("retention-days: 3", step)

        linux = (WORKFLOW_DIR / "generator-linux.yml").read_text(encoding="utf-8")
        for step_name in ("Upload validation DEB", "Upload validation Flatpak"):
            with self.subTest(workflow="generator-linux.yml", step=step_name):
                step = named_step(linux, step_name)
                self.assertIn("env.rdgen == 'validation'", step)
                self.assertIn("actions/upload-artifact@v4", step)
                self.assertIn("if-no-files-found: error", step)
                self.assertIn("retention-days: 3", step)

    def test_smart_linux_customization_does_not_require_beijing_runtime(self):
        workflow = (WORKFLOW_DIR / "generator-linux.yml").read_text(encoding="utf-8")
        for step_name in (
            "allow custom_.txt",
            "Validate customization",
            "Customize Flatpak manifest",
        ):
            with self.subTest(step=step_name):
                self.assertIn("env.smartMultiRelay == 'true'", named_step(workflow, step_name))
        beijing_base = named_step(workflow, "Apply Beijing custom Linux base fixes")
        self.assertIn("env.beijingCustom == 'true'", beijing_base)
        self.assertNotIn("env.smartMultiRelay", beijing_base)
        self.assertGreaterEqual(workflow.count("--without-beijing-runtime"), 3)
        self.assertIn("Upload validation DEB", workflow)
        self.assertIn("Upload validation Flatpak", workflow)
        self.assertIn('dpkg --compare-versions "$builder_version" ge 1.3.4', workflow)


if __name__ == "__main__":
    unittest.main()
