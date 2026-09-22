import hashlib
import os
import shutil
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import (
    GeneratedArtifact,
    GithubRun,
    RegistrationEmailCode,
    UserEntitlement,
)


class GeneratedDownloadAccessTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user("download-owner", password="password")
        self.other = user_model.objects.create_user("download-other", password="password")
        self.staff = user_model.objects.create_user(
            "download-staff",
            password="password",
            is_staff=True,
        )
        self.run_uuid = str(uuid.uuid4())
        self.raw_token = "public-download-token"
        self.run = GithubRun.objects.create(
            uuid=self.run_uuid,
            status="success",
            owner=self.owner,
            download_access="login",
            download_ttl_hours=168,
        )
        self.output_dir = Path("exe") / self.run_uuid
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "client.exe").write_bytes(b"generated-client")

    def tearDown(self):
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def _url(self, token=None, filename="client.exe"):
        url = f"/download?filename={filename}&uuid={self.run_uuid}"
        if token is not None:
            url += f"&token={token}"
        return url

    def test_login_download_allows_owner_and_staff_only(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self._url()).status_code, 200)

        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self._url()).status_code, 200)

        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self._url()).status_code, 404)

    def test_login_download_redirects_anonymous_to_login(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/login/"))

    def test_new_runs_only_download_files_with_committed_receipts(self):
        GeneratedArtifact.objects.create(
            run=self.run,
            filename="client.exe",
            size=len(b"generated-client"),
            sha256=hashlib.sha256(b"generated-client").hexdigest(),
        )
        (self.output_dir / "uncommitted.exe").write_bytes(b"partial")
        self.client.force_login(self.owner)

        self.assertEqual(self.client.get(self._url()).status_code, 200)
        self.assertEqual(
            self.client.get(self._url(filename="uncommitted.exe")).status_code,
            404,
        )

    def test_public_download_requires_token_and_allows_anonymous(self):
        self.run.download_access = "public"
        self.run.download_token_hash = hashlib.sha256(
            self.raw_token.encode("utf-8")
        ).hexdigest()
        self.run.download_expires_at = timezone.now() + timedelta(hours=1)
        self.run.save(
            update_fields=[
                "download_access",
                "download_token_hash",
                "download_expires_at",
            ]
        )

        self.assertEqual(self.client.get(self._url()).status_code, 404)
        response = self.client.get(self._url(token=self.raw_token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"generated-client")

    def test_expired_public_download_returns_gone(self):
        self.run.download_access = "public"
        self.run.download_token_hash = hashlib.sha256(
            self.raw_token.encode("utf-8")
        ).hexdigest()
        self.run.download_expires_at = timezone.now() - timedelta(seconds=1)
        self.run.save(
            update_fields=[
                "download_access",
                "download_token_hash",
                "download_expires_at",
            ]
        )

        response = self.client.get(self._url(token=self.raw_token))
        self.assertEqual(response.status_code, 410)

    def test_artifact_expiry_also_blocks_download(self):
        self.run.artifact_expires_at = timezone.now() - timedelta(seconds=1)
        self.run.save(update_fields=["artifact_expires_at"])
        self.client.force_login(self.owner)

        self.assertEqual(self.client.get(self._url()).status_code, 410)

    def test_legacy_artifact_is_capped_at_seven_days_from_creation(self):
        GithubRun.objects.filter(pk=self.run.pk).update(
            created_at=timezone.now() - timedelta(days=8)
        )
        self.client.force_login(self.owner)

        self.assertEqual(self.client.get(self._url()).status_code, 410)


@override_settings()
class GeneratedCleanupCommandTests(TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="rdgen-cleanup-tests-"))
        self.addCleanup(lambda: shutil.rmtree(self.temp_root, ignore_errors=True))
        self.old_base = Path.cwd()
        self.addCleanup(lambda: None)
        self.owner = get_user_model().objects.create_user("cleanup-owner")

    def _make_run_dir(self, run_uuid, name="client.exe"):
        path = self.temp_root / "exe" / run_uuid
        path.mkdir(parents=True, exist_ok=True)
        (path / name).write_bytes(b"artifact")
        return path

    @override_settings()
    def test_purge_removes_expired_artifacts_and_keeps_row(self):
        run_uuid = str(uuid.uuid4())
        run = GithubRun.objects.create(
            uuid=run_uuid,
            status="success",
            owner=self.owner,
            artifact_expires_at=timezone.now() - timedelta(seconds=1),
        )
        path = self._make_run_dir(run_uuid)

        with self.settings(BASE_DIR=self.temp_root):
            call_command("purge_generated_files")

        self.assertFalse(path.exists())
        self.assertTrue(GithubRun.objects.filter(pk=run.pk).exists())

    def test_purge_keeps_unexpired_artifacts(self):
        run_uuid = str(uuid.uuid4())
        GithubRun.objects.create(
            uuid=run_uuid,
            status="success",
            owner=self.owner,
            artifact_expires_at=timezone.now() + timedelta(days=1),
        )
        path = self._make_run_dir(run_uuid)

        with self.settings(BASE_DIR=self.temp_root):
            call_command("purge_generated_files")

        self.assertTrue(path.exists())
        self.assertTrue((path / "client.exe").exists())

    def test_purge_dry_run_does_not_delete(self):
        run_uuid = str(uuid.uuid4())
        GithubRun.objects.create(
            uuid=run_uuid,
            status="success",
            owner=self.owner,
            artifact_expires_at=timezone.now() - timedelta(seconds=1),
        )
        path = self._make_run_dir(run_uuid)

        with self.settings(BASE_DIR=self.temp_root):
            call_command("purge_generated_files", "--dry-run")

        self.assertTrue(path.exists())

    def test_purge_legacy_run_uses_creation_time(self):
        run_uuid = str(uuid.uuid4())
        run = GithubRun.objects.create(uuid=run_uuid, status="success", owner=self.owner)
        old_created_at = timezone.now() - timedelta(days=8)
        GithubRun.objects.filter(pk=run.pk).update(created_at=old_created_at)
        path = self._make_run_dir(run_uuid)

        with self.settings(BASE_DIR=self.temp_root):
            call_command("purge_generated_files")

        self.assertFalse(path.exists())

    def test_purge_removes_stale_temp_archive_by_mtime(self):
        temp_dir = self.temp_root / "temp_zips"
        temp_dir.mkdir(parents=True, exist_ok=True)
        archive = temp_dir / "secrets_stale_build.zip"
        archive.write_bytes(b"secret")
        old_timestamp = (timezone.now() - timedelta(days=8)).timestamp()
        os.utime(archive, (old_timestamp, old_timestamp))

        with self.settings(BASE_DIR=self.temp_root):
            call_command("purge_generated_files")

        self.assertFalse(archive.exists())

    def test_purge_removes_email_verification_records_after_one_day(self):
        old_code = RegistrationEmailCode.objects.create(
            email="old-code@example.com",
            code_hash="a" * 64,
            expires_at=timezone.now() - timedelta(hours=23),
        )
        recent_code = RegistrationEmailCode.objects.create(
            email="recent-code@example.com",
            code_hash="b" * 64,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        RegistrationEmailCode.objects.filter(pk=old_code.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )

        with self.settings(BASE_DIR=self.temp_root):
            call_command("purge_generated_files")

        self.assertFalse(RegistrationEmailCode.objects.filter(pk=old_code.pk).exists())
        self.assertTrue(RegistrationEmailCode.objects.filter(pk=recent_code.pk).exists())

    def test_purge_releases_stale_count_reservation(self):
        entitlement = UserEntitlement.objects.create(
            user=self.owner,
            expiration_mode="count",
            generation_limit=1,
            reserved_generations=1,
        )
        run = GithubRun.objects.create(
            uuid=str(uuid.uuid4()),
            status="in_progress",
            owner=self.owner,
            quota_reserved=True,
        )
        GithubRun.objects.filter(pk=run.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )

        with self.settings(BASE_DIR=self.temp_root):
            call_command("purge_generated_files")

        run.refresh_from_db()
        entitlement.refresh_from_db()
        self.assertFalse(run.quota_reserved)
        self.assertEqual(run.status, "timed_out")
        self.assertEqual(entitlement.reserved_generations, 0)

    def test_purge_times_out_stale_run_without_count_reservation(self):
        run = GithubRun.objects.create(
            uuid=str(uuid.uuid4()),
            status="artifacts_pending",
            owner=self.owner,
        )
        GithubRun.objects.filter(pk=run.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )

        with self.settings(BASE_DIR=self.temp_root):
            call_command("purge_generated_files")

        run.refresh_from_db()
        self.assertEqual(run.status, "timed_out")
