import unittest
from pathlib import Path


WORKFLOW_DIR = Path(__file__).resolve().parents[1] / "workflows"
WINDOWS_WORKFLOWS = (
    "generator-windows.yml",
    "sh-generator-windows.yml",
)
WINDOWS_UTF8_WORKFLOWS = WINDOWS_WORKFLOWS + ("generator-windows-x86.yml",)


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


class WindowsWorkflowCommandTests(unittest.TestCase):
    def test_windows_python_uses_utf8_for_non_ascii_application_names(self):
        for workflow_name in WINDOWS_UTF8_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8")
                global_env = workflow.split("env:\n", 1)[1].split("\njobs:\n", 1)[0]
                portable_step = named_step(workflow, "Build self-extracted executable")

                self.assertIn('PYTHONUTF8: "1"', global_env)
                self.assertIn('PYTHONIOENCODING: "utf-8"', global_env)
                self.assertIn("python3 ./generate.py", portable_step)

    def test_windows_x64_configures_msi_utf8_before_build(self):
        for workflow_name in WINDOWS_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8")
                configure_step = named_step(
                    workflow,
                    "Configure MSI UTF-8 codepage",
                )
                zh_step = named_step(workflow, "Configure MSI Chinese UI")

                self.assertIn("shell: pwsh", configure_step)
                self.assertNotIn("continue-on-error: true", configure_step)
                self.assertIn(
                    "https://raw.githubusercontent.com/${{ github.repository }}/"
                    "${{ github.sha }}/.github/patches/configure_windows_msi_utf8.py",
                    configure_step,
                )
                self.assertIn("python configure_windows_msi_utf8.py", configure_step)
                self.assertIn("configure_windows_msi_zh_cn.py", zh_step)
                self.assertIn("WixUI_zh-CN.wxl", zh_step)
                self.assertIn("python configure_windows_msi_zh_cn.py", zh_step)
                self.assertLess(
                    workflow.index("      - name: Configure MSI UTF-8 codepage"),
                    workflow.index("      - name: Configure MSI Chinese UI"),
                )
                self.assertLess(
                    workflow.index("      - name: Configure MSI Chinese UI"),
                    workflow.index("      - name: Build msi"),
                )
                build_step = named_step(workflow, "Build msi")
                self.assertIn("Get-ChildItem ./Package/bin/x64/Release -Recurse -Filter Package.msi", build_step)
                self.assertNotIn("Release/en-us/Package.msi", build_step)

    def test_silent_agent_patch_runs_for_every_windows_builder(self):
        for workflow_name in WINDOWS_UTF8_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8")
                step = named_step(workflow, "silent agent mode")

                self.assertIn("if: env.silentAgentMode == 'true'", step)
                self.assertIn(".github/patches/silent_agent_mode.py", step)
                self.assertIn("python silent_agent_mode.py", step)
                self.assertLess(
                    workflow.index("      - name: silent agent mode"),
                    workflow.index("      - name: Build rustdesk"),
                )

    def test_update_notification_patch_uses_windows_available_downloader(self):
        for workflow_name in WINDOWS_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8")
                step = named_step(workflow, "removeNewVersionNotif")

                self.assertIn("shell: pwsh", step)
                self.assertIn("Invoke-WebRequest", step)
                self.assertIn("-OutFile remove_new_version_notif.py", step)
                self.assertIn("python remove_new_version_notif.py", step)
                self.assertNotIn("wget ", step)

    def test_windows_x64_requires_and_finalizes_both_installers(self):
        for workflow_name in WINDOWS_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8")
                finalize_step = named_step(workflow, "finalize files on rdgen server")

                for step_name in (
                    "Build msi",
                    "zip exe and msi",
                    "unzip exe and msi",
                    "rename rustdesk.msi to filename.msi",
                ):
                    self.assertNotIn(
                        "continue-on-error: true",
                        named_step(workflow, step_name),
                    )

                if "upload artifacts to rdgen (COS/OSS or direct)" in workflow:
                    upload_step = named_step(
                        workflow,
                        "upload artifacts to rdgen (COS/OSS or direct)",
                    )
                    self.assertIn('EXE="./SignOutput/${{ env.filename }}.exe"', upload_step)
                    self.assertIn('MSI="./SignOutput/${{ env.filename }}.msi"', upload_step)
                    self.assertIn('test -s "$EXE"', upload_step)
                    self.assertIn('test -s "$MSI"', upload_step)
                else:
                    exe_upload_step = named_step(workflow, "send exe to rdgen server")
                    msi_upload_step = named_step(workflow, "send msi to rdgen server")
                    self.assertIn(
                        'test -s "./SignOutput/${{ env.filename }}.exe"',
                        exe_upload_step,
                    )
                    self.assertIn(
                        'test -s "./SignOutput/${{ env.filename }}.msi"',
                        msi_upload_step,
                    )

                self.assertIn("/finalize_custom_client", finalize_step)
                self.assertNotIn("/save_custom_client", finalize_step)

    def test_rdgen_failures_are_reported_without_masking_build_failure(self):
        for workflow_name in WINDOWS_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                workflow = (WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8")
                step = named_step(workflow, "report generation failure to rdgen server")

                self.assertIn("always()", step)
                self.assertIn("!success()", step)
                self.assertIn("env.rdgen == 'true'", step)
                self.assertIn("continue-on-error: true", step)
                self.assertIn('Authorization: Bearer ${{ env.token }}', step)
                self.assertIn('"status":"failure"', step)
                self.assertIn("${{ secrets.GENURL }}/updategh", step)

                job = named_job(workflow, "report-build-failure")
                self.assertIn("always()", job)
                self.assertIn(
                    "needs.build-for-windows-flutter.result != 'success'",
                    job,
                )
                self.assertIn("setup", job)
                self.assertIn("generate-bridge", job)
                self.assertIn("build-RustDeskTempTopMostWindow", job)
                self.assertIn("build-for-windows-flutter", job)
                self.assertIn("metadata['status_signature']", job)
                self.assertIn("/updategh?signature=", job)
                self.assertIn("for attempt in range(3)", job)


if __name__ == "__main__":
    unittest.main()
