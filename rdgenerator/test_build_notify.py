import hashlib
import uuid
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .build_notify import maybe_notify_build_success
from .models import GeneratedArtifact, GithubRun, SiteEmailConfig
from .views import download_token_for_run


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    GENURL="https://app.example.test",
    SECRET_KEY="test-secret-key-for-build-notify",
    SECURE_SSL_REDIRECT=False,
    HTTPS_ENABLED=False,
)
class BuildSuccessNotifyTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            "notify-owner",
            email="customer@example.com",
            password="secret-pass-123",
        )
        self.token = download_token_for_run("placeholder")
        self.run_uuid = str(uuid.uuid4())
        self.download_token = download_token_for_run(self.run_uuid)
        self.run = GithubRun.objects.create(
            uuid=self.run_uuid,
            status="success",
            owner=self.owner,
            platform="windows",
            artifact_stem="MyClient",
            download_access="login",
            download_ttl_hours=24,
            download_token_hash=hashlib.sha256(
                self.download_token.encode()
            ).hexdigest(),
            download_expires_at=timezone.now() + timedelta(hours=24),
            artifact_uploaded_at=timezone.now(),
        )
        GeneratedArtifact.objects.create(
            run=self.run,
            filename="MyClient.exe",
            size=12,
            sha256=hashlib.sha256(b"hello-client").hexdigest(),
        )
        GeneratedArtifact.objects.create(
            run=self.run,
            filename="MyClient.msi",
            size=12,
            sha256=hashlib.sha256(b"hello-installer").hexdigest(),
        )
        SiteEmailConfig.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "host": "smtp.example.test",
                "port": 465,
                "username": "noreply@example.test",
                "password": "auth-code",
                "use_ssl": True,
                "use_tls": False,
                "from_email": "noreply@example.test",
            },
        )

    def test_sends_one_email_with_download_links(self):
        self.assertTrue(maybe_notify_build_success(self.run.pk))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["customer@example.com"])
        self.assertIn("构建成功", message.subject)
        self.assertIn("MyClient.exe", message.body)
        self.assertIn("MyClient.msi", message.body)
        self.assertIn("https://app.example.test/download?", message.body)
        self.assertIn(self.run_uuid, message.body)
        self.assertIn("需登录后下载", message.body)
        self.run.refresh_from_db()
        self.assertIsNotNone(self.run.success_email_sent_at)

        # Second call must not spam.
        self.assertFalse(maybe_notify_build_success(self.run.pk))
        self.assertEqual(len(mail.outbox), 1)

    def test_skips_when_owner_has_no_email(self):
        self.owner.email = ""
        self.owner.save(update_fields=["email"])
        self.assertFalse(maybe_notify_build_success(self.run.pk))
        self.assertEqual(len(mail.outbox), 0)
        self.run.refresh_from_db()
        self.assertIsNotNone(self.run.success_email_sent_at)

    def test_finalize_triggers_email(self):
        token = "callback-token-for-notify"
        run_uuid = str(uuid.uuid4())
        owner = get_user_model().objects.create_user(
            "finalize-owner",
            email="finalize@example.com",
            password="secret-pass-123",
        )
        run = GithubRun.objects.create(
            uuid=run_uuid,
            status="artifacts_pending",
            owner=owner,
            platform="windows",
            artifact_stem="WinApp",
            callback_token_hash=hashlib.sha256(token.encode()).hexdigest(),
            download_access="public",
            download_token_hash=hashlib.sha256(
                download_token_for_run(run_uuid).encode()
            ).hexdigest(),
            download_expires_at=timezone.now() + timedelta(hours=12),
        )
        exe_dir = Path("exe") / run_uuid
        exe_dir.mkdir(parents=True, exist_ok=True)
        exe_bytes = b"exe-bytes-here"
        msi_bytes = b"msi-bytes-here"
        (exe_dir / "WinApp.exe").write_bytes(exe_bytes)
        (exe_dir / "WinApp.msi").write_bytes(msi_bytes)
        GeneratedArtifact.objects.create(
            run=run,
            filename="WinApp.exe",
            size=len(exe_bytes),
            sha256=hashlib.sha256(exe_bytes).hexdigest(),
        )
        GeneratedArtifact.objects.create(
            run=run,
            filename="WinApp.msi",
            size=len(msi_bytes),
            sha256=hashlib.sha256(msi_bytes).hexdigest(),
        )

        client = Client()
        response = client.post(
            "/finalize_custom_client",
            data='{"uuid":"%s"}' % run_uuid,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["finalize@example.com"])
        self.assertIn("token=", mail.outbox[0].body)
        run.refresh_from_db()
        self.assertEqual(run.status, "success")
        self.assertIsNotNone(run.success_email_sent_at)
