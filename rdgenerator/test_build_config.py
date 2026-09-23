from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .build_config import build_config_snapshot, config_display_sections
from .dual_session import ADMIN_SESSION_COOKIE_NAME
from .models import GithubRun


User = get_user_model()


def force_admin_login(client, user):
    """Log in through the front session cookie and mirror it for /admin/."""
    client.force_login(user)
    session_cookie = client.cookies.get("sessionid")
    if session_cookie is not None:
        client.cookies[ADMIN_SESSION_COOKIE_NAME] = session_cookie.value


class BuildConfigSnapshotTests(TestCase):
    def test_snapshot_sections_include_core_fields(self):
        snapshot = build_config_snapshot(
            form_data={"defaultManual": "foo=1", "overrideManual": ""},
            decoded_custom={
                "app-name": "Demo",
                "default-settings": {"theme": "dark"},
            },
            effective={
                "platform": "windows",
                "version": "1.4.9",
                "appname": "Demo",
                "filename": "Demo",
                "compname": "Acme",
                "androidappid": "",
                "direction": "both",
                "installation": "installationY",
                "settings": "settingsY",
                "server": "hbbs.example",
                "relayServer": "hbbr.example",
                "apiServer": "https://api.example",
                "key": "public-key-value",
                "smartMultiRelay": True,
                "beijingCustom": False,
                "urlLink": "https://example.com",
                "downloadLink": "https://example.com/dl",
                "hasIcon": True,
                "hasLogo": False,
                "hasPrivacyImage": False,
                "permPass": "secret123",
                "passApproveMode": "password",
                "hidecm": False,
                "hidecmDefaultEnabled": False,
                "silentAgentMode": False,
                "denyLan": False,
                "enableDirectIP": True,
                "theme": "dark",
                "themeDorO": "default",
                "defaultViewStyle": "adaptive",
                "hideNetworkSetting": False,
                "hideSettingsMenu": False,
                "hideTray": False,
                "removeSetupServerTip": False,
                "removeNewVersionNotif": False,
                "removeRecentSessions": False,
                "incomingCompactMode": False,
                "incomingContentWidth": 220,
                "incomingContentHeight": 300,
                "copyIdPasswordButton": False,
                "manualTemporaryPassword": False,
                "showStartOnBootCheckbox": False,
                "permissionsDorO": "default",
                "permissionsType": "custom",
                "enableKeyboard": True,
                "enableClipboard": True,
                "enableFileCopyPaste": True,
                "enableFileTransfer": True,
                "forceDisableFileTransfer": False,
                "enableAudio": True,
                "enableTCP": True,
                "enableRemoteRestart": True,
                "enableRecording": False,
                "enableBlockingInput": False,
                "enableRemoteModi": False,
                "enablePrinter": False,
                "enableCamera": False,
                "enableTerminal": False,
                "removeWallpaper": False,
                "autoClose": False,
                "delayFix": True,
                "cycleMonitor": False,
                "xOffline": False,
                "silentInstallOnDoubleClick": False,
                "selfhosted": False,
                "linuxCustomAllowed": True,
                "download_access": "login",
                "download_ttl_hours": 24,
            },
        )
        sections = config_display_sections(snapshot, reveal_secrets=True)
        titles = [section["title"] for section in sections]
        self.assertIn("基础信息", titles)
        self.assertIn("服务器与中继", titles)
        self.assertIn("写入客户端的 custom 配置", titles)
        joined = " ".join(
            f'{row["label"]}:{row["value"]}'
            for section in sections
            for row in section["rows"]
        )
        self.assertIn("固定密码:secret123", joined)
        self.assertIn("智能多中继:是", joined)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    HTTPS_ENABLED=False,
    ALLOWED_HOSTS=["*"],
)
class AdminBuildDetailTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            "cfg-admin",
            email="cfg-admin@example.com",
            password="secret-pass-123",
        )
        self.member = User.objects.create_user(
            "cfg-member",
            email="cfg-member@example.com",
            password="secret-pass-123",
        )
        self.run = GithubRun.objects.create(
            uuid="11111111-1111-1111-1111-111111111111",
            status="success",
            owner=self.member,
            platform="windows",
            artifact_stem="CfgClient",
            config_snapshot={
                "version": 1,
                "basic": {"platform": "windows", "version": "1.4.9", "appname": "Cfg"},
                "servers": {"serverIP": "1.2.3.4", "smartMultiRelay": False},
                "security": {"permanentPassword": "pw-visible"},
            },
        )

    def test_admin_detail_shows_config(self):
        force_admin_login(self.client, self.admin)
        response = self.client.get(
            reverse("console:build_detail", args=[self.run.pk]),
            HTTP_HOST="testserver",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "基础信息")
        self.assertContains(response, "pw-visible")
        self.assertContains(response, "CfgClient")
