import base64
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import pyzipper
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .forms import GenerateForm
from .models import GithubRun, UserEntitlement
from .views import _default_api_server


@override_settings(
    GHUSER="test-owner",
    REPONAME="test-repo",
    GHBRANCH="master",
    GENURL="http://generator.example",
    PROTOCOL="http",
    ZIP_PASSWORD="test-zip-password",
)
class GeneratorFeaturePayloadTests(TestCase):
    def setUp(self):
        self.created_secret_zips = []
        self.user = get_user_model().objects.create_user(
            username="generator-test-user",
            password="test-password",
        )
        self.client.force_login(self.user)

    def tearDown(self):
        for path in self.created_secret_zips:
            if path.exists():
                path.unlink()

    def test_generator_import_renders_png_previews_without_inner_html(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "renderImportedPngPreview")
        self.assertContains(response, "replaceChildren(image)")
        self.assertNotContains(response, 'innerHTML = `<img src="${formData[key]}">`')

    def test_generator_exposes_server_managed_relay_as_the_default(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ID 服务器")
        self.assertContains(response, 'name="relayServer"')
        self.assertContains(response, "通常留空，由 ID 服务器选择健康中继")
        self.assertContains(response, "填写后将强制使用单个 hbbr")
        self.assertContains(response, "不能填写逗号分隔的列表")
        self.assertNotContains(
            response,
            'id="relayServerOptions" class="advanced-server-options field-block field-block--full" open',
        )

    def test_generator_migrates_legacy_manual_relay_in_the_browser(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "function migrateManualRelaySetting()")
        self.assertContains(
            response,
            "readManualSetting(overrideManualInput, 'relay-server')",
        )
        self.assertContains(
            response,
            "relayServerInput.value = selectedSetting.value",
        )
        self.assertContains(
            response,
            "removeManualSetting(setting, 'relay-server')",
        )
        self.assertContains(
            response,
            "defaultManualInput.value = ''",
        )
        self.assertContains(
            response,
            "overrideManualInput.value = ''",
        )

    def test_smart_multi_relay_data_field_is_staged_for_import_export(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="checkbox" name="smartMultiRelay"')
        self.assertContains(response, '智能多中继（严格 WSS）')
        self.assertContains(
            response,
            "hasOwnProperty.call(formData, 'smartMultiRelay')",
        )
        self.assertContains(response, "smartMultiRelayInput.checked = false")

    def test_ambiguous_dispatch_error_keeps_windows_run_receivable(self):
        with (
            patch("rdgenerator.views.requests.post", side_effect=TimeoutError("lost response")),
            patch("rdgenerator.views.save_png", side_effect=ValueError("no image in test")),
        ):
            response = self.client.post(
                "/generator",
                data=self._feature_payload(platform="windows"),
            )

        self.assertEqual(response.status_code, 500)
        run = GithubRun.objects.get()
        self.assertEqual(run.status, "artifacts_pending")
        self.assertTrue(run.callback_token_hash)
        self.created_secret_zips.extend(
            Path("temp_zips").glob(f"secrets_{run.uuid}_*.zip")
        )

    def test_dispatch_response_cannot_overwrite_early_terminal_callback(self):
        def dispatch_after_failure(*_args, **_kwargs):
            GithubRun.objects.update(status="failure")
            return SimpleNamespace(status_code=204, content=b"", text="")

        with (
            patch("rdgenerator.views.requests.post", side_effect=dispatch_after_failure),
            patch("rdgenerator.views.save_png", side_effect=ValueError("no image in test")),
        ):
            response = self.client.post(
                "/generator",
                data=self._feature_payload(platform="windows"),
            )

        self.assertEqual(response.status_code, 200)
        run = GithubRun.objects.get()
        self.assertEqual(run.status, "failure")
        self.created_secret_zips.extend(
            Path("temp_zips").glob(f"secrets_{run.uuid}_*.zip")
        )

    def test_rejected_dispatch_marks_run_failed_without_reviving_callback(self):
        github_response = SimpleNamespace(
            status_code=422,
            content=b'{"message":"invalid"}',
            text="invalid",
        )
        with (
            patch("rdgenerator.views.requests.post", return_value=github_response),
            patch("rdgenerator.views.save_png", side_effect=ValueError("no image in test")),
        ):
            response = self.client.post(
                "/generator",
                data=self._feature_payload(platform="windows"),
            )

        self.assertEqual(response.status_code, 500)
        run = GithubRun.objects.get()
        self.assertEqual(run.status, "dispatch_failed")
        self.created_secret_zips.extend(
            Path("temp_zips").glob(f"secrets_{run.uuid}_*.zip")
        )

    def test_exhausted_user_cannot_bypass_disabled_button_with_forged_post(self):
        UserEntitlement.objects.create(
            user=self.user,
            expiration_mode=UserEntitlement.EXPIRATION_COUNT,
            generation_limit=1,
            generations_used=1,
        )
        existing_archives = set(Path("temp_zips").glob("secrets_*.zip"))

        with (
            patch("rdgenerator.views.requests.post") as post_mock,
            patch("rdgenerator.views.save_png", side_effect=ValueError("no image in test")),
        ):
            response = self.client.post("/generator", data=self._feature_payload())

        self.created_secret_zips.extend(
            set(Path("temp_zips").glob("secrets_*.zip")) - existing_archives
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "当前账号的生成额度已用尽或已过期")
        self.assertContains(response, "生成次数已用尽")
        self.assertIn(
            "disabled",
            re.search(
                r'<button id="generateSubmit"[^>]*>',
                response.content.decode(),
            ).group(0),
        )
        self.assertFalse(response.context["entitlement_summary"]["can_generate"])
        post_mock.assert_not_called()
        self.assertFalse(GithubRun.objects.exists())

    def _feature_payload(self, platform="windows", direction="incoming"):
        data = {
            "platform": platform,
            "version": "1.4.9",
            "formSchemaVersion": "2",
            "delayFix": "on",
            "beijingCustom": "on",
            "exename": "AllFeatures",
            "appname": "WuYouDesk",
            "direction": direction,
            "installation": "installationN",
            "settings": "settingsY",
            "hideNetworkSetting": "on",
            "defaultViewStyle": "adaptive",
            "removeSetupServerTip": "on",
            "silentInstallOnDoubleClick": "on",
            "copyIdPasswordButton": "on",
            "manualTemporaryPassword": "on",
            "showStartOnBootCheckbox": "on",
            "incomingCompactMode": "on",
            "incomingContentWidth": "260",
            "incomingContentHeight": "360",
            "androidappid": "com.example.wuyoudesk",
            "serverIP": "10.0.0.1",
            "relayServer": "",
            "apiServer": "",
            "key": "test-server-key",
            "urlLink": "https://example.com",
            "downloadLink": "https://example.com/download",
            "compname": "Example Ltd",
            "theme": "system",
            "themeDorO": "default",
            "passApproveMode": "password-click",
            "permanentPassword": "fixed-password",
            "denyLan": "on",
            "enableDirectIP": "on",
            "autoClose": "on",
            "permissionsDorO": "default",
            "permissionsType": "custom",
            "enableKeyboard": "on",
            "enableClipboard": "on",
            "enableFileCopyPaste": "on",
            "enableFileTransfer": "on",
            "forceDisableFileTransfer": "on",
            "enableAudio": "on",
            "enableTCP": "on",
            "enableRemoteRestart": "on",
            "enableRecording": "on",
            "enableBlockingInput": "on",
            "enableRemoteModi": "on",
            "enablePrinter": "on",
            "enableCamera": "on",
            "enableTerminal": "on",
            "hidecm": "on",
            "hidecmDefaultEnabled": "on",
            "removeWallpaper": "on",
            "defaultManual": "custom-option=Y",
            "overrideManual": "override-option=N",
            "cycleMonitor": "on",
            "xOffline": "on",
            "removeNewVersionNotif": "on",
            "hideSettingsMenu": "on",
            "removeRecentSessions": "on",
        }
        return data

    def _smart_multi_relay_payload(self, platform="windows", version="1.4.9"):
        data = self._feature_payload(platform=platform)
        data["smartMultiRelay"] = "on"
        data["version"] = version
        data["serverIP"] = "hbbs.example.com:21116"
        data["apiServer"] = "https://api.example.com"
        if platform == "windows-x86":
            for field in (
                "cycleMonitor",
                "xOffline",
                "copyIdPasswordButton",
                "manualTemporaryPassword",
                "showStartOnBootCheckbox",
                "incomingCompactMode",
            ):
                data[field] = ""
        if platform == "android":
            data["hideSettingsMenu"] = ""
        return data

    def _silent_agent_payload(self, platform="windows", version="1.4.9"):
        data = self._feature_payload(platform=platform)
        data["version"] = version
        data["installation"] = "installationY"
        data["silentAgentMode"] = "on"
        if platform == "windows-x86":
            for field in (
                "cycleMonitor",
                "xOffline",
                "copyIdPasswordButton",
                "manualTemporaryPassword",
                "showStartOnBootCheckbox",
                "incomingCompactMode",
            ):
                data[field] = ""
        return data

    def _post_and_read_inputs(self, data):
        counter = iter(range(1, 20))

        def fake_uuid4():
            return UUID(int=next(counter))

        github_response = SimpleNamespace(status_code=204, content=b"", text="")
        with (
            patch("rdgenerator.views.uuid.uuid4", side_effect=fake_uuid4),
            patch("rdgenerator.views.requests.post", return_value=github_response) as post_mock,
            patch("rdgenerator.views.save_png", side_effect=ValueError("no image in test")),
        ):
            response = self.client.post("/generator", data=data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(GithubRun.objects.get().owner, self.user)
        post_payload = post_mock.call_args.kwargs["json"]
        self.last_dispatch_payload = post_payload
        zip_url = json.loads(post_payload["inputs"]["zip_url"])
        self.last_dispatch_metadata = zip_url
        zip_path = Path("temp_zips") / zip_url["file"]
        self.created_secret_zips.append(zip_path)
        with pyzipper.AESZipFile(zip_path) as zf:
            zf.setpassword(settings.ZIP_PASSWORD.encode())
            inputs_raw = json.loads(zf.read("secrets.json").decode("utf-8"))
        custom_config = json.loads(base64.b64decode(inputs_raw["custom"]).decode("ascii"))
        return post_mock.call_args.args[0], inputs_raw, custom_config

    def test_windows_all_features_are_serialized_for_generation(self):
        data = self._feature_payload(platform="windows", direction="incoming")
        data["hideTray"] = "on"
        dispatch_url, inputs_raw, custom_config = self._post_and_read_inputs(data)

        self.assertTrue(dispatch_url.endswith("/actions/workflows/generator-windows.yml/dispatches"))
        run = GithubRun.objects.get()
        self.assertEqual(run.status, "artifacts_pending")
        self.assertEqual(run.platform, "windows")
        self.assertEqual(run.artifact_stem, "AllFeatures")
        matching_archives = list(
            Path("temp_zips").glob(f"secrets_{run.uuid}_*.zip")
        )
        self.assertEqual(len(matching_archives), 1)
        self.assertEqual(self.last_dispatch_metadata["uuid"], run.uuid)
        self.assertTrue(self.last_dispatch_metadata["status_signature"])
        expected_true_flags = [
            "delayFix",
            "hideNetworkSetting",
            "removeSetupServerTip",
            "silentInstallOnDoubleClick",
            "hidecm",
            "hidecmDefaultEnabled",
            "copyIdPasswordButton",
            "manualTemporaryPassword",
            "showStartOnBootCheckbox",
            "incomingCompactMode",
            "forceDisableFileTransfer",
            "cycleMonitor",
            "xOffline",
            "removeNewVersionNotif",
            "hideSettingsMenu",
            "removeRecentSessions",
        ]
        for key in expected_true_flags:
            self.assertEqual(inputs_raw[key], "true", key)
        self.assertEqual(inputs_raw["direction"], "incoming")
        self.assertEqual(inputs_raw["beijingCustom"], "false")
        self.assertEqual(inputs_raw["incomingContentWidth"], "260")
        self.assertEqual(inputs_raw["incomingContentHeight"], "360")
        self.assertEqual(inputs_raw["apiServer"], "http://10.0.0.1:21114")

        self.assertEqual(custom_config["conn-type"], "incoming")
        self.assertEqual(custom_config["disable-installation"], "Y")
        self.assertNotIn("disable-settings", custom_config)
        self.assertEqual(custom_config["hide-network-setting"], "Y")
        self.assertEqual(custom_config["custom-rendezvous-server"], "10.0.0.1")
        self.assertNotIn("relay-server", custom_config)
        self.assertEqual(custom_config["api-server"], "http://10.0.0.1:21114")
        self.assertEqual(custom_config["key"], "test-server-key")
        self.assertEqual(custom_config["password"], "fixed-password")

        default_settings = custom_config["default-settings"]
        self.assertNotIn("relay-server", default_settings)
        self.assertEqual(default_settings["view-style"], "adaptive")
        self.assertEqual(default_settings["enable-file-copy-paste"], "Y")
        self.assertEqual(default_settings["enable-file-transfer"], "N")
        self.assertEqual(default_settings["approve-mode"], "password")
        self.assertEqual(default_settings["verification-method"], "use-permanent-password")
        self.assertEqual(default_settings["allow-hide-cm"], "Y")
        self.assertEqual(default_settings["allow-remove-wallpaper"], "Y")
        self.assertEqual(default_settings["allow-remote-config-modification"], "Y")
        self.assertEqual(default_settings["direct-server"], "Y")
        self.assertEqual(default_settings["custom-option"], "Y")
        override_settings = custom_config["override-settings"]
        self.assertEqual(override_settings["relay-server"], "")
        self.assertNotIn("approve-mode", override_settings)
        self.assertNotIn("verification-method", override_settings)
        self.assertNotIn("allow-hide-cm", override_settings)
        self.assertEqual(override_settings["hide-tray"], "Y")
        self.assertEqual(override_settings["override-option"], "N")

    def test_windows_silent_agent_mode_implies_hidden_unattended_runtime(self):
        data = self._feature_payload(platform="windows", direction="incoming")
        data["installation"] = "installationY"
        data["silentAgentMode"] = "on"
        data["silentInstallOnDoubleClick"] = ""
        data["hideTray"] = ""
        data["hidecm"] = ""
        data["hidecmDefaultEnabled"] = ""
        data["passApproveMode"] = "password-click"

        _, inputs_raw, custom_config = self._post_and_read_inputs(data)

        for key in (
            "silentAgentMode",
            "silentInstallOnDoubleClick",
            "hidecm",
            "hidecmDefaultEnabled",
        ):
            self.assertEqual(inputs_raw[key], "true", key)
        self.assertEqual(custom_config["override-settings"]["hide-tray"], "Y")
        self.assertEqual(
            custom_config["default-settings"]["approve-mode"],
            "password",
        )
        self.assertEqual(
            custom_config["default-settings"]["verification-method"],
            "use-permanent-password",
        )
        self.assertEqual(
            custom_config["default-settings"]["allow-hide-cm"],
            "Y",
        )

    def test_fixed_relay_server_replaces_server_managed_empty_override(self):
        data = self._feature_payload(platform="windows")
        data["relayServer"] = "relay.example.com:21117"

        _, _, custom_config = self._post_and_read_inputs(data)

        self.assertEqual(
            custom_config["custom-rendezvous-server"],
            "10.0.0.1",
        )
        self.assertEqual(
            custom_config["override-settings"]["relay-server"],
            "relay.example.com:21117",
        )
        self.assertNotIn("relay-server", custom_config["default-settings"])
        self.assertNotIn("relay-server", custom_config)

    def test_id_server_port_is_not_reused_as_the_api_port(self):
        data = self._feature_payload(platform="windows")
        data["serverIP"] = "10.0.0.1:22116"

        _, inputs_raw, custom_config = self._post_and_read_inputs(data)

        self.assertEqual(inputs_raw["server"], "10.0.0.1:22116")
        self.assertEqual(inputs_raw["apiServer"], "http://10.0.0.1:21114")
        self.assertEqual(
            custom_config["custom-rendezvous-server"],
            "10.0.0.1:22116",
        )
        self.assertEqual(custom_config["api-server"], "http://10.0.0.1:21114")
        self.assertNotIn("relay-server", custom_config)

    def test_explicit_api_server_is_preserved(self):
        data = self._feature_payload(platform="windows")
        data["serverIP"] = "10.0.0.1:22116"
        data["apiServer"] = "https://api.example.com:9443"

        _, inputs_raw, custom_config = self._post_and_read_inputs(data)

        self.assertEqual(inputs_raw["apiServer"], "https://api.example.com:9443")
        self.assertEqual(custom_config["api-server"], "https://api.example.com:9443")

    def test_default_api_server_supports_ipv6(self):
        self.assertEqual(
            _default_api_server("2001:db8::1"),
            "http://[2001:db8::1]:21114",
        )
        self.assertEqual(
            _default_api_server("[2001:db8::1]:22116"),
            "http://[2001:db8::1]:21114",
        )

    def test_legacy_payload_without_relay_field_uses_server_selection(self):
        data = self._feature_payload(platform="windows")
        data.pop("relayServer")

        _, _, custom_config = self._post_and_read_inputs(data)

        self.assertEqual(custom_config["custom-rendezvous-server"], "10.0.0.1")
        self.assertNotIn("relay-server", custom_config)
        self.assertNotIn("relay-server", custom_config["default-settings"])
        self.assertEqual(custom_config["override-settings"]["relay-server"], "")

    def test_legacy_manual_relay_is_promoted_to_the_dedicated_field(self):
        data = self._feature_payload(platform="windows")
        data["relayServer"] = ""
        data["defaultManual"] = "relay-server=relay-default.example.com:21117"
        data["overrideManual"] = "relay-server=relay-override.example.com:21117"

        _, _, custom_config = self._post_and_read_inputs(data)

        self.assertEqual(
            custom_config["override-settings"]["relay-server"],
            "relay-override.example.com:21117",
        )
        self.assertNotIn("relay-server", custom_config["default-settings"])

    def test_dedicated_relay_wins_over_legacy_manual_relay(self):
        data = self._feature_payload(platform="windows")
        data["relayServer"] = "relay-new.example.com:21117"
        data["overrideManual"] = "relay-server=relay-old.example.com:21117"

        _, _, custom_config = self._post_and_read_inputs(data)

        self.assertEqual(
            custom_config["override-settings"]["relay-server"],
            "relay-new.example.com:21117",
        )

    def test_rejects_legacy_manual_relay_lists(self):
        data = self._feature_payload(platform="windows")
        data["relayServer"] = ""
        data["overrideManual"] = "relay-server=relay-a.example.com,relay-b.example.com"
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("overrideManual", form.errors)
        self.assertIn("多中继列表应配置在 hbbs", form.errors["overrideManual"][0])

    def test_other_settings_start_disabled_and_serialize_as_opt_in(self):
        form = GenerateForm()
        self.assertFalse(form.fields["hideTray"].initial)
        self.assertFalse(form.fields["removeWallpaper"].initial)
        self.assertFalse(form.fields["silentAgentMode"].initial)
        self.assertNotIn("checked", str(form["hideTray"]))
        self.assertNotIn("checked", str(form["removeWallpaper"]))
        self.assertNotIn("checked", str(form["silentAgentMode"]))

        data = self._feature_payload(platform="windows")
        data.pop("removeWallpaper")
        _, _, custom_config = self._post_and_read_inputs(data)

        self.assertNotIn("hide-tray", custom_config["override-settings"])
        self.assertEqual(
            custom_config["default-settings"]["allow-remove-wallpaper"],
            "N",
        )

    def test_legacy_manual_hide_tray_setting_migrates_to_toggle(self):
        data = self._feature_payload(platform="windows")
        data["overrideManual"] = (
            "override-option=N\nhide-tray=maybe\nhide-tray=Y"
        )

        _, _, custom_config = self._post_and_read_inputs(data)

        self.assertEqual(custom_config["override-settings"]["hide-tray"], "Y")
        self.assertEqual(custom_config["override-settings"]["override-option"], "N")

    def test_default_manual_hide_tray_setting_migrates_to_override_toggle(self):
        data = self._feature_payload(platform="windows")
        data["defaultManual"] = "default-option=Y\nhide_tray=Y"

        _, _, custom_config = self._post_and_read_inputs(data)

        self.assertEqual(custom_config["default-settings"]["default-option"], "Y")
        self.assertNotIn("hide-tray", custom_config["default-settings"])
        self.assertNotIn("hide_tray", custom_config["default-settings"])
        self.assertEqual(custom_config["override-settings"]["hide-tray"], "Y")

    def test_override_manual_hide_tray_takes_precedence_over_default_manual(self):
        data = self._feature_payload(platform="windows")
        data["hideTray"] = "on"
        data["defaultManual"] = "default-option=Y\nhide-tray=Y"
        data["overrideManual"] = "override-option=N\nhide-tray=N"

        _, _, custom_config = self._post_and_read_inputs(data)

        self.assertEqual(custom_config["default-settings"]["default-option"], "Y")
        self.assertEqual(custom_config["override-settings"]["override-option"], "N")
        self.assertNotIn("hide-tray", custom_config["default-settings"])
        self.assertNotIn("hide-tray", custom_config["override-settings"])

    def test_manual_hide_tray_n_clears_checked_toggle(self):
        data = self._feature_payload(platform="windows")
        data["hideTray"] = "on"
        data["overrideManual"] = "hide-tray=N"
        form = GenerateForm(data=data)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["hideTray"])
        self.assertEqual(form.cleaned_data["overrideManual"], "")

    def test_manual_hide_tray_rejects_unknown_value(self):
        data = self._feature_payload(platform="windows")
        data["overrideManual"] = "hide-tray=maybe"
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("overrideManual", form.errors)

    def test_default_manual_hide_tray_rejects_unknown_value(self):
        data = self._feature_payload(platform="windows")
        data["defaultManual"] = "hide-tray=maybe"
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("defaultManual", form.errors)

    def test_android_rejects_hide_tray_toggle(self):
        data = self._feature_payload(platform="android")
        data["hideSettingsMenu"] = ""
        data["hideTray"] = "on"
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("hideTray", form.errors)

    def test_android_rejects_manual_hide_tray_setting(self):
        data = self._feature_payload(platform="android")
        data["hideSettingsMenu"] = ""
        data["defaultManual"] = "hide_tray=Y"
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("defaultManual", form.errors)
        self.assertIn("Android 不支持系统托盘图标。", form.errors["defaultManual"])

    def test_standard_linux_rejects_manual_hide_tray_setting(self):
        data = self._feature_payload(platform="linux")
        data["beijingCustom"] = ""
        data["overrideManual"] = "hide-tray=Y"
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("overrideManual", form.errors)

    def test_hide_connection_window_capability_starts_disabled_without_password(self):
        data = self._feature_payload(platform="windows")
        data["hidecmDefaultEnabled"] = ""
        data["permanentPassword"] = ""
        data["permissionsDorO"] = "override"
        data["settings"] = "settingsY"
        data["overrideManual"] = "\n".join([
            "approve-mode=click",
            "verification-method=use-permanent-password",
            "allow-hide-cm=Y",
        ])

        _, inputs_raw, custom_config = self._post_and_read_inputs(data)

        self.assertEqual(inputs_raw["hidecm"], "true")
        self.assertEqual(inputs_raw["hidecmDefaultEnabled"], "false")
        self.assertNotIn("password", custom_config)
        self.assertEqual(
            custom_config["default-settings"]["approve-mode"],
            "password-click",
        )
        self.assertEqual(
            custom_config["default-settings"]["verification-method"],
            "use-both-passwords",
        )
        self.assertEqual(
            custom_config["default-settings"]["allow-hide-cm"],
            "N",
        )
        self.assertNotIn("approve-mode", custom_config["override-settings"])
        self.assertNotIn("verification-method", custom_config["override-settings"])
        self.assertNotIn("allow-hide-cm", custom_config["override-settings"])

    def test_default_hidden_connection_window_remains_user_configurable(self):
        data = self._feature_payload(platform="windows")
        data["permissionsDorO"] = "override"
        data["overrideManual"] = "\n".join([
            "approve-mode=click",
            "verification-method=use-both-passwords",
            "allow-hide-cm=N",
        ])

        _, _, custom_config = self._post_and_read_inputs(data)

        self.assertEqual(
            custom_config["default-settings"]["approve-mode"],
            "password",
        )
        self.assertEqual(
            custom_config["default-settings"]["verification-method"],
            "use-permanent-password",
        )
        self.assertEqual(
            custom_config["default-settings"]["allow-hide-cm"],
            "Y",
        )
        self.assertNotIn("approve-mode", custom_config["override-settings"])
        self.assertNotIn("verification-method", custom_config["override-settings"])
        self.assertNotIn("allow-hide-cm", custom_config["override-settings"])

    def test_legacy_hide_connection_window_post_keeps_default_enabled(self):
        data = self._feature_payload(platform="windows")
        data.pop("formSchemaVersion")
        data.pop("hidecmDefaultEnabled")
        data["settings"] = "settingsN"

        _, inputs_raw, custom_config = self._post_and_read_inputs(data)

        self.assertEqual(inputs_raw["hidecm"], "true")
        self.assertEqual(inputs_raw["hidecmDefaultEnabled"], "true")
        self.assertEqual(custom_config["disable-settings"], "Y")
        self.assertEqual(
            custom_config["default-settings"]["allow-hide-cm"],
            "Y",
        )

    def test_company_name_is_sed_escaped_in_workflow_input(self):
        data = self._feature_payload(platform="windows")
        data["compname"] = "Research & Development"
        _, inputs_raw, _ = self._post_and_read_inputs(data)
        self.assertEqual(inputs_raw["compname"], r"Research \& Development")

    def test_windows_x86_keeps_windows_options_but_skips_flutter_only_flags(self):
        data = self._feature_payload(platform="windows-x86", direction="incoming")
        data["cycleMonitor"] = ""
        data["xOffline"] = ""
        data["copyIdPasswordButton"] = ""
        data["manualTemporaryPassword"] = ""
        data["showStartOnBootCheckbox"] = ""
        data["incomingCompactMode"] = ""
        _, inputs_raw, _ = self._post_and_read_inputs(
            data
        )

        self.assertEqual(inputs_raw["hideNetworkSetting"], "true")
        self.assertEqual(inputs_raw["silentInstallOnDoubleClick"], "true")
        self.assertEqual(inputs_raw["copyIdPasswordButton"], "false")
        self.assertEqual(inputs_raw["manualTemporaryPassword"], "false")
        self.assertEqual(inputs_raw["showStartOnBootCheckbox"], "false")
        self.assertEqual(inputs_raw["incomingCompactMode"], "false")
        self.assertEqual(inputs_raw["removeRecentSessions"], "true")
        self.assertEqual(inputs_raw["beijingCustom"], "false")

    def test_android_generation_suppresses_desktop_only_flags(self):
        data = self._feature_payload(platform="android", direction="incoming")
        data["hideSettingsMenu"] = ""
        _, inputs_raw, custom_config = self._post_and_read_inputs(
            data
        )

        expected_false_flags = [
            "hideNetworkSetting",
            "removeSetupServerTip",
            "silentInstallOnDoubleClick",
            "silentAgentMode",
            "copyIdPasswordButton",
            "manualTemporaryPassword",
            "showStartOnBootCheckbox",
            "incomingCompactMode",
            "removeRecentSessions",
            "beijingCustom",
            "hidecm",
            "hidecmDefaultEnabled",
            "hideSettingsMenu",
        ]
        for key in expected_false_flags:
            self.assertEqual(inputs_raw[key], "false", key)
        self.assertEqual(inputs_raw["forceDisableFileTransfer"], "true")
        self.assertEqual(inputs_raw["xOffline"], "true")
        self.assertNotIn("hide-network-setting", custom_config)

    def test_linux_generation_serializes_beijing_custom_when_checked(self):
        dispatch_url, inputs_raw, custom_config = self._post_and_read_inputs(
            self._feature_payload(platform="linux", direction="incoming")
        )

        self.assertTrue(dispatch_url.endswith("/actions/workflows/generator-linux.yml/dispatches"))
        self.assertEqual(inputs_raw["beijingCustom"], "true")
        self.assertEqual(inputs_raw["hideNetworkSetting"], "true")
        self.assertEqual(inputs_raw["removeSetupServerTip"], "true")
        self.assertEqual(inputs_raw["hidecm"], "true")
        self.assertEqual(inputs_raw["copyIdPasswordButton"], "true")
        self.assertEqual(inputs_raw["manualTemporaryPassword"], "true")
        self.assertEqual(inputs_raw["incomingCompactMode"], "true")
        self.assertEqual(inputs_raw["forceDisableFileTransfer"], "true")
        self.assertEqual(inputs_raw["removeRecentSessions"], "true")
        self.assertEqual(custom_config["hide-network-setting"], "Y")
        self.assertEqual(custom_config["default-settings"]["view-style"], "adaptive")
        self.assertEqual(custom_config["default-settings"]["enable-file-transfer"], "N")

    def test_linux_generation_without_beijing_custom_suppresses_linux_custom_features(self):
        data = self._feature_payload(platform="linux", direction="incoming")
        data.pop("beijingCustom")
        dispatch_url, inputs_raw, custom_config = self._post_and_read_inputs(data)

        self.assertTrue(dispatch_url.endswith("/actions/workflows/generator-linux.yml/dispatches"))
        expected_false_flags = [
            "beijingCustom",
            "delayFix",
            "hideNetworkSetting",
            "removeSetupServerTip",
            "silentAgentMode",
            "hidecm",
            "hidecmDefaultEnabled",
            "copyIdPasswordButton",
            "manualTemporaryPassword",
            "incomingCompactMode",
            "forceDisableFileTransfer",
            "cycleMonitor",
            "xOffline",
            "removeNewVersionNotif",
            "hideSettingsMenu",
            "removeRecentSessions",
        ]
        for key in expected_false_flags:
            self.assertEqual(inputs_raw[key], "false", key)
        self.assertEqual(inputs_raw["direction"], "both")
        self.assertEqual(inputs_raw["server"], "rs-ny.rustdesk.com")
        self.assertEqual(inputs_raw["apiServer"], "http://rs-ny.rustdesk.com:21114")
        self.assertEqual(inputs_raw["key"], "OeVuKk5nlHiXp+APNn0Y3pC1Iwpwn44JGqrQCsWqmBw=")
        self.assertEqual(inputs_raw["appname"], "rustdesk")
        self.assertEqual(inputs_raw["filename"], "rustdesk")
        self.assertEqual(inputs_raw["iconlink_url"], "false")
        self.assertEqual(inputs_raw["logolink_url"], "false")
        self.assertEqual(inputs_raw["privacylink_url"], "false")

    def test_default_version_is_1_4_9(self):
        self.assertEqual(GenerateForm().fields["version"].initial, "1.4.9")

    def test_smart_multi_relay_missing_input_defaults_false_and_is_serialized(self):
        data = self._feature_payload()
        form = GenerateForm(data=data)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["smartMultiRelay"])

        _, inputs_raw, custom_config = self._post_and_read_inputs(data)
        run = GithubRun.objects.get()
        self.assertFalse(run.smart_multi_relay)
        self.assertEqual(inputs_raw["smartMultiRelay"], "false")
        self.assertEqual(custom_config["override-settings"]["relay-server"], "")

    def test_smart_multi_relay_accepts_only_locked_platform_matrix(self):
        for platform in ("windows", "windows-x86", "linux", "android"):
            with self.subTest(platform=platform):
                form = GenerateForm(data=self._smart_multi_relay_payload(platform))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertTrue(form.cleaned_data["smartMultiRelay"])

    def test_smart_multi_relay_rejects_nightly_and_other_versions(self):
        for version in ("master", "1.4.8"):
            with self.subTest(version=version):
                form = GenerateForm(
                    data=self._smart_multi_relay_payload(version=version)
                )
                self.assertFalse(form.is_valid())
                self.assertIn("smartMultiRelay", form.errors)
                self.assertIn("仅支持 RustDesk 1.4.9", form.errors["smartMultiRelay"][0])

    def test_smart_multi_relay_rejects_macos(self):
        form = GenerateForm(data=self._smart_multi_relay_payload("macos"))

        self.assertFalse(form.is_valid())
        self.assertIn("smartMultiRelay", form.errors)
        self.assertIn("macOS 暂不支持", form.errors["smartMultiRelay"][0])

    def test_smart_multi_relay_rejects_explicit_fixed_relay(self):
        data = self._smart_multi_relay_payload()
        data["relayServer"] = "relay.example.com:21117"
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("smartMultiRelay", form.errors)
        self.assertIn("relayServer", form.errors)
        self.assertIn("不能与固定中继服务器同时启用", form.errors["relayServer"][0])

    def test_smart_multi_relay_requires_strict_wss_deployment_inputs(self):
        cases = (
            ("serverIP", "192.0.2.10:21116", "不能使用 IP 地址"),
            ("serverIP", "hbbs", "不能使用 IP 地址"),
            ("apiServer", "http://api.example.com", "https://"),
            ("apiServer", "", "https://"),
            ("key", "", "服务器公钥"),
        )
        for field, value, message in cases:
            with self.subTest(field=field, value=value):
                data = self._smart_multi_relay_payload()
                data[field] = value
                form = GenerateForm(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
                self.assertIn(message, form.errors[field][0])

    def test_smart_multi_relay_rejects_manual_fixed_relay(self):
        data = self._smart_multi_relay_payload()
        data["relayServer"] = ""
        data["overrideManual"] = "relay-server=relay.example.com:21117"
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("smartMultiRelay", form.errors)
        self.assertIn("relayServer", form.errors)

    def test_silent_agent_mode_accepts_locked_windows_matrix(self):
        for platform in ("windows", "windows-x86"):
            with self.subTest(platform=platform):
                form = GenerateForm(data=self._silent_agent_payload(platform))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertTrue(form.cleaned_data["silentAgentMode"])
                self.assertTrue(form.cleaned_data["silentInstallOnDoubleClick"])
                self.assertTrue(form.cleaned_data["hideTray"])
                self.assertTrue(form.cleaned_data["hidecm"])
                self.assertTrue(form.cleaned_data["hidecmDefaultEnabled"])
                self.assertEqual(form.cleaned_data["passApproveMode"], "password")

    def test_silent_agent_mode_rejects_other_versions(self):
        for version in ("master", "1.4.8"):
            with self.subTest(version=version):
                form = GenerateForm(
                    data=self._silent_agent_payload(version=version)
                )
                self.assertFalse(form.is_valid())
                self.assertIn("silentAgentMode", form.errors)
                self.assertIn("仅支持 RustDesk 1.4.9", form.errors["silentAgentMode"][0])

    def test_silent_agent_mode_rejects_non_windows_platforms(self):
        for platform in ("linux", "macos", "android"):
            with self.subTest(platform=platform):
                form = GenerateForm(data=self._silent_agent_payload(platform))
                self.assertFalse(form.is_valid())
                self.assertIn("silentAgentMode", form.errors)
                self.assertIn("仅支持 Windows", form.errors["silentAgentMode"][0])

    def test_silent_agent_mode_requires_installation(self):
        data = self._silent_agent_payload()
        data["installation"] = "installationN"
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("installation", form.errors)

    def test_silent_agent_mode_rejects_outgoing_only_build(self):
        data = self._silent_agent_payload()
        data["direction"] = "outgoing"
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("direction", form.errors)

    def test_silent_agent_mode_requires_permanent_password(self):
        data = self._silent_agent_payload()
        data["permanentPassword"] = ""
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("permanentPassword", form.errors)

    def test_silent_agent_mode_keeps_settings_access_available(self):
        data = self._silent_agent_payload()
        data["settings"] = "settingsN"
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("settings", form.errors)

    def test_smart_multi_relay_is_persisted_and_encrypted_for_generation(self):
        _, inputs_raw, custom_config = self._post_and_read_inputs(
            self._smart_multi_relay_payload()
        )
        run = GithubRun.objects.get()

        self.assertTrue(run.smart_multi_relay)
        self.assertEqual(inputs_raw["smartMultiRelay"], "true")
        self.assertEqual(custom_config["override-settings"]["relay-server"], "")
        self.assertEqual(
            custom_config["override-settings"]["api-server"],
            "https://api.example.com",
        )
        self.assertEqual(
            custom_config["override-settings"]["allow-websocket"],
            "Y",
        )
        self.assertEqual(
            custom_config["override-settings"]["allow-insecure-tls-fallback"],
            "N",
        )
        self.assertNotIn("smartMultiRelay", self.last_dispatch_payload["inputs"])

    def test_smart_multi_relay_linux_keeps_wss_server_configuration(self):
        _, inputs_raw, custom_config = self._post_and_read_inputs(
            self._smart_multi_relay_payload("linux")
        )

        self.assertEqual(inputs_raw["smartMultiRelay"], "true")
        self.assertEqual(
            custom_config["custom-rendezvous-server"],
            "hbbs.example.com:21116",
        )
        self.assertEqual(custom_config["api-server"], "https://api.example.com")
        self.assertEqual(
            custom_config["override-settings"]["api-server"],
            "https://api.example.com",
        )
        self.assertEqual(
            custom_config["override-settings"]["allow-websocket"],
            "Y",
        )

    def test_hide_connection_window_capability_allows_empty_permanent_password(self):
        data = self._feature_payload()
        data["hidecmDefaultEnabled"] = ""
        data["permanentPassword"] = ""
        data["settings"] = "settingsY"
        form = GenerateForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_new_form_missing_default_checkbox_means_default_disabled(self):
        data = self._feature_payload()
        data.pop("hidecmDefaultEnabled")
        data["permanentPassword"] = ""
        form = GenerateForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["hidecmDefaultEnabled"])

    def test_unknown_form_schema_does_not_use_legacy_hide_defaults(self):
        data = self._feature_payload()
        data["formSchemaVersion"] = "3"
        data.pop("hidecmDefaultEnabled")
        data["settings"] = "settingsN"
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("settings", form.errors)
        self.assertFalse(form.cleaned_data["hidecmDefaultEnabled"])

    def test_hide_connection_window_capability_requires_settings_access(self):
        data = self._feature_payload()
        data["hidecmDefaultEnabled"] = ""
        data["settings"] = "settingsN"
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("settings", form.errors)

    def test_default_hidden_connection_window_requires_permanent_password(self):
        data = self._feature_payload()
        data["permanentPassword"] = ""
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("permanentPassword", form.errors)

    def test_default_hidden_connection_window_requires_settings_access(self):
        data = self._feature_payload()
        data["settings"] = "settingsN"
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("settings", form.errors)

    def test_default_hidden_connection_window_requires_capability(self):
        data = self._feature_payload()
        data["hidecm"] = ""
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("hidecmDefaultEnabled", form.errors)

    def test_manual_settings_allow_blank_lines_and_equals_in_value(self):
        data = self._feature_payload()
        data["hidecm"] = ""
        data["hidecmDefaultEnabled"] = ""
        data["defaultManual"] = "\ntoken=part=two\n"
        data["overrideManual"] = ""
        form = GenerateForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_manual_setting_is_a_form_error(self):
        data = self._feature_payload()
        data["hidecm"] = ""
        data["hidecmDefaultEnabled"] = ""
        data["defaultManual"] = "missing-separator"
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("defaultManual", form.errors)

    def test_android_rejects_logo(self):
        data = self._feature_payload(platform="android")
        data["hidecm"] = ""
        data["hidecmDefaultEnabled"] = ""
        data["logobase64"] = "data:image/png;base64,AA=="
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("logofile", form.errors)

    def test_privacy_image_is_windows_64_only(self):
        data = self._feature_payload(platform="macos")
        data["hidecm"] = ""
        data["hidecmDefaultEnabled"] = ""
        data["privacybase64"] = "data:image/png;base64,AA=="
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("privacyfile", form.errors)

    def test_windows_x86_rejects_flutter_only_options(self):
        data = self._feature_payload(platform="windows-x86")
        data["hidecm"] = ""
        data["hidecmDefaultEnabled"] = ""
        data["cycleMonitor"] = "on"
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("cycleMonitor", form.errors)

    def test_android_rejects_desktop_settings_menu_option(self):
        data = self._feature_payload(platform="android")
        data["hidecm"] = ""
        data["hidecmDefaultEnabled"] = ""
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("hideSettingsMenu", form.errors)

    def test_version_gated_features_reject_unsupported_versions(self):
        requirements = {
            "incomingCompactMode": "1.4.1",
            "hideNetworkSetting": "1.4.3",
            "hideSettingsMenu": "1.4.3",
            "forceDisableFileTransfer": "1.4.4",
        }
        gated_fields = list(requirements)
        for field, version in requirements.items():
            with self.subTest(field=field, version=version):
                data = self._feature_payload()
                for gated_field in gated_fields:
                    data[gated_field] = ""
                data["version"] = version
                data[field] = "on"
                form = GenerateForm(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_master_allows_version_gated_features(self):
        data = self._feature_payload()
        data["version"] = "master"
        form = GenerateForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_compact_dimensions_are_optional_when_feature_is_disabled(self):
        data = self._feature_payload()
        data["incomingCompactMode"] = ""
        data.pop("incomingContentWidth")
        data.pop("incomingContentHeight")
        form = GenerateForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_build_script_metacharacters(self):
        data = self._feature_payload()
        data["exename"] = "client;touch-pwned"
        data["serverIP"] = "server.example.com'"
        data["relayServer"] = "relay.example.com'"
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("exename", form.errors)
        self.assertIn("serverIP", form.errors)
        self.assertIn("relayServer", form.errors)

    def test_rejects_relay_server_lists(self):
        data = self._feature_payload()
        data["relayServer"] = "relay-a.example.com,relay-b.example.com"
        form = GenerateForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("relayServer", form.errors)
        self.assertIn("多中继列表应配置在 hbbs", form.errors["relayServer"][0])

    def test_relay_validation_error_opens_advanced_server_options(self):
        data = self._feature_payload()
        data["relayServer"] = "relay-a.example.com,relay-b.example.com"

        response = self.client.post("/generator", data=data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="relayServerOptions" class="advanced-server-options field-block field-block--full" open',
        )

    def test_rejects_nonportable_build_names(self):
        invalid_names = (
            ("exename", "CON"),
            ("appname", "NUL.txt"),
            ("appname", "Client?"),
            ("appname", "Client."),
            ("appname", "-Client"),
        )
        for field, value in invalid_names:
            with self.subTest(field=field, value=value):
                data = self._feature_payload()
                data[field] = value
                form = GenerateForm(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_rejects_build_names_that_exceed_filesystem_limits(self):
        invalid_names = (
            ("exename", "a" * 65),
            ("appname", "\U0001F600" * 51),
        )
        for field, value in invalid_names:
            with self.subTest(field=field):
                data = self._feature_payload()
                data[field] = value
                form = GenerateForm(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_linux_package_name_requires_at_least_two_characters(self):
        data = self._feature_payload(platform="linux")
        data["exename"] = "A"
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("exename", form.errors)

    def test_beijing_linux_rejects_unverified_versions(self):
        for version in ("1.4.6", "master"):
            with self.subTest(version=version):
                data = self._feature_payload(platform="linux")
                data["version"] = version
                form = GenerateForm(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn("beijingCustom", form.errors)

    def test_single_character_name_remains_valid_for_windows(self):
        data = self._feature_payload(platform="windows")
        data["exename"] = "A"
        form = GenerateForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_linux_package_metadata_rejects_shell_substitution(self):
        data = self._feature_payload(platform="linux")
        data["appname"] = "$(touch unsafe)"
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("appname", form.errors)

    def test_linux_package_metadata_rejects_rpm_macros(self):
        invalid_values = {
            "appname": "Client%(printf unsafe)",
            "compname": "Company%{lua:unsafe}",
            "urlLink": "https://example.com/%{unsafe}",
        }
        for field, value in invalid_values.items():
            with self.subTest(field=field):
                data = self._feature_payload(platform="linux")
                data[field] = value
                form = GenerateForm(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_linux_rpm_url_rejects_whitespace(self):
        data = self._feature_payload(platform="linux")
        data["urlLink"] = "https://example.com/a b"
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("urlLink", form.errors)

    def test_percent_encoded_url_is_allowed_without_linux_rpm_customization(self):
        data = self._feature_payload(platform="linux")
        data["beijingCustom"] = ""
        data["urlLink"] = "https://example.com/a%20b"
        form = GenerateForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_invalid_android_app_id(self):
        data = self._feature_payload(platform="android")
        data["hidecm"] = ""
        data["hidecmDefaultEnabled"] = ""
        data["hideSettingsMenu"] = ""
        data["androidappid"] = "invalid-app-id"
        form = GenerateForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("androidappid", form.errors)

    def test_rejects_non_absolute_http_urls(self):
        invalid_values = {
            "apiServer": "api.example.com",
            "urlLink": "not-a-url",
            "downloadLink": "ftp://example.com/client",
        }
        for field, value in invalid_values.items():
            with self.subTest(field=field):
                data = self._feature_payload()
                data[field] = value
                form = GenerateForm(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
