import hashlib
import json
import shutil
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import GeneratedArtifact, GithubRun
from .views import (
    ARTIFACT_INCOMPLETE_STATUS,
    ARTIFACT_PENDING_STATUS,
    DISPATCH_FAILURE_SALT,
    STATUS_UPDATE_SALT,
    ZIP_DOWNLOAD_SALT,
)


class MachineEndpointTests(TestCase):
    def setUp(self):
        self.token = "callback-token-for-tests"
        self.run_uuid = str(uuid.uuid4())
        owner = get_user_model().objects.create_user("machine-owner")
        self.run = GithubRun.objects.create(
            uuid=self.run_uuid,
            status="in_progress",
            owner=owner,
            platform="windows",
            artifact_stem="client",
            callback_token_hash=hashlib.sha256(self.token.encode()).hexdigest(),
        )
        self.png_dir = Path("png") / self.run_uuid
        self.exe_dir = Path("exe") / self.run_uuid
        self.temp_dir = Path("temp_zips")
        self.png_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        (self.png_dir / "icon.png").write_bytes(b"png-data")
        self.created_temp_files = []

    def tearDown(self):
        shutil.rmtree(self.png_dir, ignore_errors=True)
        shutil.rmtree(self.exe_dir, ignore_errors=True)
        for path in self.created_temp_files:
            path.unlink(missing_ok=True)

    def _bearer(self, token=None):
        return {"HTTP_AUTHORIZATION": f"Bearer {token or self.token}"}

    def test_png_requires_matching_callback_token(self):
        url = f"/get_png?filename=icon.png&uuid={self.run_uuid}"

        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(
            self.client.get(url, **self._bearer("wrong-token")).status_code,
            401,
        )
        response = self.client.get(url, **self._bearer())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"png-data")

    def test_expired_callback_token_is_rejected(self):
        GithubRun.objects.filter(uuid=self.run_uuid).update(
            created_at=timezone.now() - timedelta(days=2)
        )

        response = self.client.get(
            f"/get_png?filename=icon.png&uuid={self.run_uuid}",
            **self._bearer(),
        )

        self.assertEqual(response.status_code, 401)

    def test_status_update_requires_matching_callback_token(self):
        self.run.platform = ""
        self.run.artifact_stem = ""
        self.run.save(update_fields=["platform", "artifact_stem"])
        payload = json.dumps({"uuid": self.run_uuid, "status": "success"})

        self.assertEqual(
            self.client.post("/updategh", payload, content_type="application/json").status_code,
            401,
        )
        response = self.client.post(
            "/updategh",
            payload,
            content_type="application/json",
            **self._bearer(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            GithubRun.objects.get(uuid=self.run_uuid).status,
            "success",
        )

    def test_status_update_accepts_task_scoped_signed_url(self):
        signature = signing.dumps(
            {"uuid": self.run_uuid},
            salt=STATUS_UPDATE_SALT,
        )

        response = self.client.post(
            f"/updategh?signature={signature}",
            json.dumps({"uuid": self.run_uuid, "status": "failure"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            GithubRun.objects.get(uuid=self.run_uuid).status,
            "failure",
        )

    def test_dispatch_failure_signature_only_authorizes_failure_status(self):
        signature = signing.dumps(
            {"uuid": self.run_uuid},
            salt=DISPATCH_FAILURE_SALT,
        )

        rejected = self.client.post(
            f"/updategh?signature={signature}",
            json.dumps({"uuid": self.run_uuid, "status": "success"}),
            content_type="application/json",
        )
        accepted = self.client.post(
            f"/updategh?signature={signature}",
            json.dumps({"uuid": self.run_uuid, "status": "failure"}),
            content_type="application/json",
        )

        self.assertEqual(rejected.status_code, 401)
        self.assertEqual(accepted.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "failure")

    def test_status_callbacks_cannot_bypass_deferred_artifact_finalize(self):
        self.run.status = ARTIFACT_PENDING_STATUS
        self.run.save(update_fields=["status"])

        for status in ("queued", "in_progress", "success"):
            with self.subTest(status=status):
                response = self.client.post(
                    "/updategh",
                    json.dumps({"uuid": self.run_uuid, "status": status}),
                    content_type="application/json",
                    **self._bearer(),
                )

                self.assertEqual(response.status_code, 200)
                self.run.refresh_from_db()
                self.assertEqual(self.run.status, ARTIFACT_PENDING_STATUS)

    def test_terminal_statuses_absorb_late_callbacks(self):
        for terminal_status in ("success", "failure", "dispatch_failed"):
            for late_status in ("queued", "in_progress", "success", "failure"):
                with self.subTest(terminal=terminal_status, late=late_status):
                    GithubRun.objects.filter(pk=self.run.pk).update(status=terminal_status)
                    response = self.client.post(
                        "/updategh",
                        json.dumps({"uuid": self.run_uuid, "status": late_status}),
                        content_type="application/json",
                        **self._bearer(),
                    )

                    self.assertEqual(response.status_code, 200)
                    self.run.refresh_from_db()
                    self.assertEqual(self.run.status, terminal_status)

    def test_stale_success_callback_cannot_overwrite_pending_state(self):
        stale_run = GithubRun.objects.get(pk=self.run.pk)
        GithubRun.objects.filter(pk=self.run.pk).update(status=ARTIFACT_PENDING_STATUS)

        with patch("rdgenerator.views._status_run", return_value=(stale_run, None)):
            response = self.client.post(
                "/updategh",
                json.dumps({"uuid": self.run_uuid, "status": "success"}),
                content_type="application/json",
                **self._bearer(),
            )

        self.assertEqual(response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ARTIFACT_PENDING_STATUS)

    def test_windows_success_callback_cannot_bypass_finalize_before_pending(self):
        self.run.status = "in_progress"
        self.run.save(update_fields=["status"])

        response = self.client.post(
            "/updategh",
            json.dumps({"uuid": self.run_uuid, "status": "success"}),
            content_type="application/json",
            **self._bearer(),
        )

        self.assertEqual(response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "in_progress")

    def test_finalize_cannot_resurrect_a_failed_run(self):
        self.run.status = "failure"
        self.run.save(update_fields=["status"])

        response = self.client.post(
            "/finalize_custom_client",
            json.dumps(
                {
                    "uuid": self.run_uuid,
                    "platform": "windows",
                    "filename": "client",
                }
            ),
            content_type="application/json",
            **self._bearer(),
        )

        self.assertEqual(response.status_code, 409)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "failure")

    def test_repeated_finalize_observes_a_concurrent_failure(self):
        self.run.status = "success"
        self.run.artifact_uploaded_at = timezone.now()
        self.run.save(update_fields=["status", "artifact_uploaded_at"])
        self.exe_dir.mkdir(parents=True, exist_ok=True)
        (self.exe_dir / "client.exe").write_bytes(b"exe-data")
        (self.exe_dir / "client.msi").write_bytes(b"msi-data")
        GeneratedArtifact.objects.create(
            run=self.run,
            filename="client.exe",
            size=len(b"exe-data"),
            sha256=hashlib.sha256(b"exe-data").hexdigest(),
        )
        GeneratedArtifact.objects.create(
            run=self.run,
            filename="client.msi",
            size=len(b"msi-data"),
            sha256=hashlib.sha256(b"msi-data").hexdigest(),
        )

        original_filter = GithubRun.objects.filter

        def filter_then_fail(*args, **kwargs):
            if kwargs.get("pk") == self.run.pk and kwargs.get("status") == "success":
                original_filter(pk=self.run.pk).update(status="failure")
            return original_filter(*args, **kwargs)

        with patch.object(GithubRun.objects, "filter", side_effect=filter_then_fail):
            response = self.client.post(
                "/finalize_custom_client",
                json.dumps(
                    {
                        "uuid": self.run_uuid,
                        "platform": "windows",
                        "filename": "client",
                    }
                ),
                content_type="application/json",
                **self._bearer(),
            )

        self.assertEqual(response.status_code, 409)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "failure")

    def test_upload_requires_token_and_saves_only_under_run_directory(self):
        GithubRun.objects.filter(pk=self.run.pk).update(platform="", artifact_stem="")
        upload = SimpleUploadedFile("client.exe", b"client-data")

        self.assertEqual(
            self.client.post(
                "/save_custom_client",
                {"uuid": self.run_uuid, "file": upload},
            ).status_code,
            401,
        )
        upload = SimpleUploadedFile("client.exe", b"client-data")
        response = self.client.post(
            "/save_custom_client",
            {"uuid": self.run_uuid, "file": upload},
            **self._bearer(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual((self.exe_dir / "client.exe").read_bytes(), b"client-data")
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "success")

    def test_pending_windows_upload_cannot_skip_finalize(self):
        self.run.status = ARTIFACT_PENDING_STATUS
        self.run.save(update_fields=["status"])

        for filename in ("client.exe", "client.msi"):
            with self.subTest(filename=filename):
                response = self.client.post(
                    "/save_custom_client",
                    {
                        "uuid": self.run_uuid,
                        "file": SimpleUploadedFile(filename, b"package-data"),
                    },
                    **self._bearer(),
                )
                self.assertEqual(response.status_code, 200)
                self.run.refresh_from_db()
                self.assertEqual(self.run.status, ARTIFACT_PENDING_STATUS)

        retry_response = self.client.post(
            "/save_custom_client",
            {
                "uuid": self.run_uuid,
                "file": SimpleUploadedFile("client.exe", b"package-data"),
            },
            **self._bearer(),
        )
        self.assertEqual(retry_response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ARTIFACT_PENDING_STATUS)
        self.assertEqual(self.run.artifact_file_count, 2)

        finalize_response = self.client.post(
            "/finalize_custom_client",
            json.dumps(
                {
                    "uuid": self.run_uuid,
                    "platform": "windows",
                    "filename": "client",
                }
            ),
            content_type="application/json",
            **self._bearer(),
        )
        self.assertEqual(finalize_response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "success")
        self.assertEqual(self.run.artifact_file_count, 2)

    def test_dispatch_failure_cannot_be_revived_by_late_upload(self):
        self.run.status = "dispatch_failed"
        self.run.save(update_fields=["status"])

        response = self.client.post(
            "/save_custom_client",
            {
                "uuid": self.run_uuid,
                "file": SimpleUploadedFile("client.exe", b"late-package"),
            },
            **self._bearer(),
        )

        self.assertEqual(response.status_code, 409)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "dispatch_failed")
        self.assertFalse((self.exe_dir / "client.exe").exists())
        self.assertIsNone(self.run.artifact_uploaded_at)
        self.assertFalse(self.run.quota_counted)

    def test_upload_does_not_overwrite_concurrent_failure(self):
        original_filter = GithubRun.objects.filter
        injected_failure = False

        def filter_after_failure(*args, **kwargs):
            nonlocal injected_failure
            if kwargs.get("pk") == self.run.pk and not injected_failure:
                injected_failure = True
                original_filter(pk=self.run.pk).update(status="failure")
            return original_filter(*args, **kwargs)

        with patch.object(
            GithubRun.objects,
            "filter",
            side_effect=filter_after_failure,
        ):
            response = self.client.post(
                "/save_custom_client",
                {
                    "uuid": self.run_uuid,
                    "file": SimpleUploadedFile("client.exe", b"package-data"),
                },
                **self._bearer(),
            )

        self.assertEqual(response.status_code, 409)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "failure")
        self.assertFalse((self.exe_dir / "client.exe").exists())
        self.assertIsNone(self.run.artifact_uploaded_at)
        self.assertFalse(self.run.quota_counted)

    def test_different_same_name_retry_is_rejected_without_overwrite(self):
        self.assertEqual(
            self.client.post(
                "/save_custom_client",
                {
                    "uuid": self.run_uuid,
                    "file": SimpleUploadedFile("client.exe", b"original"),
                },
                **self._bearer(),
            ).status_code,
            200,
        )

        response = self.client.post(
            "/save_custom_client",
            {
                "uuid": self.run_uuid,
                "file": SimpleUploadedFile("client.exe", b"replacement"),
            },
            **self._bearer(),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual((self.exe_dir / "client.exe").read_bytes(), b"original")
        self.assertFalse(list(self.exe_dir.glob(".upload-*.part")))

    def test_windows_upload_rejects_filename_outside_persisted_contract(self):
        response = self.client.post(
            "/save_custom_client",
            {
                "uuid": self.run_uuid,
                "file": SimpleUploadedFile("spoofed.exe", b"package-data"),
            },
            **self._bearer(),
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse((self.exe_dir / "spoofed.exe").exists())
        self.assertFalse(GeneratedArtifact.objects.filter(run=self.run).exists())

    def test_zero_byte_retry_does_not_truncate_committed_artifact(self):
        self.assertEqual(
            self.client.post(
                "/save_custom_client",
                {
                    "uuid": self.run_uuid,
                    "file": SimpleUploadedFile("client.exe", b"original"),
                },
                **self._bearer(),
            ).status_code,
            200,
        )

        response = self.client.post(
            "/save_custom_client",
            {
                "uuid": self.run_uuid,
                "file": SimpleUploadedFile("client.exe", b""),
            },
            **self._bearer(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual((self.exe_dir / "client.exe").read_bytes(), b"original")
        self.assertFalse(list(self.exe_dir.glob(".upload-*.part")))

    def test_identical_retry_repairs_committed_disk_copy(self):
        self.assertEqual(
            self.client.post(
                "/save_custom_client",
                {
                    "uuid": self.run_uuid,
                    "file": SimpleUploadedFile("client.exe", b"original"),
                },
                **self._bearer(),
            ).status_code,
            200,
        )
        (self.exe_dir / "client.exe").write_bytes(b"corrupted")

        response = self.client.post(
            "/save_custom_client",
            {
                "uuid": self.run_uuid,
                "file": SimpleUploadedFile("client.exe", b"original"),
            },
            **self._bearer(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual((self.exe_dir / "client.exe").read_bytes(), b"original")
        self.assertFalse(list(self.exe_dir.glob(".upload-*.part")))

    def test_staging_files_are_not_listed_or_downloadable(self):
        self.exe_dir.mkdir(parents=True, exist_ok=True)
        staging_file = self.exe_dir / ".upload-incomplete.part"
        staging_file.write_bytes(b"partial-data")
        self.run.status = "success"
        self.run.save(update_fields=["status"])
        self.client.force_login(self.run.owner)

        generated_response = self.client.get(
            "/check_for_file",
            {
                "filename": "client",
                "uuid": self.run_uuid,
                "platform": "windows",
            },
        )
        download_response = self.client.get(
            "/download",
            {"filename": staging_file.name, "uuid": self.run_uuid},
        )

        self.assertNotContains(generated_response, staging_file.name)
        self.assertEqual(download_response.status_code, 404)

    def test_orphan_final_name_is_not_listed_for_contracted_run(self):
        self.exe_dir.mkdir(parents=True, exist_ok=True)
        orphan = self.exe_dir / "client.exe"
        orphan.write_bytes(b"orphaned-before-db-commit")
        self.run.status = "success"
        self.run.save(update_fields=["status"])
        self.client.force_login(self.run.owner)

        generated_response = self.client.get(
            "/check_for_file",
            {
                "filename": "client",
                "uuid": self.run_uuid,
                "platform": "windows",
            },
        )
        download_response = self.client.get(
            "/download",
            {"filename": orphan.name, "uuid": self.run_uuid},
        )

        self.assertNotContains(generated_response, orphan.name)
        self.assertEqual(download_response.status_code, 404)

    def test_deferred_windows_upload_waits_for_exe_and_msi_finalize(self):
        owner = self.run.owner
        self.client.force_login(owner)

        exe_response = self.client.post(
            "/save_custom_client",
            {
                "uuid": self.run_uuid,
                "file": SimpleUploadedFile("client.exe", b"exe-data"),
                "defer_completion": "true",
            },
            **self._bearer(),
        )
        self.run.refresh_from_db()

        self.assertEqual(exe_response.status_code, 200)
        self.assertEqual(self.run.status, ARTIFACT_PENDING_STATUS)
        pending_response = self.client.get(
            "/check_for_file",
            {
                "filename": "client",
                "uuid": self.run_uuid,
                "platform": "windows",
            },
        )
        self.assertTemplateUsed(pending_response, "waiting.html")

        early_finalize = self.client.post(
            "/finalize_custom_client",
            json.dumps(
                {
                    "uuid": self.run_uuid,
                    "platform": "windows",
                    "filename": "client",
                }
            ),
            content_type="application/json",
            **self._bearer(),
        )
        self.assertEqual(early_finalize.status_code, 409)
        self.assertEqual(early_finalize.json()["missing"], ["client.msi"])

        msi_response = self.client.post(
            "/save_custom_client",
            {
                "uuid": self.run_uuid,
                "file": SimpleUploadedFile("client.msi", b"msi-data"),
                "defer_completion": "true",
            },
            **self._bearer(),
        )
        self.assertEqual(msi_response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ARTIFACT_PENDING_STATUS)

        finalize_response = self.client.post(
            "/finalize_custom_client",
            json.dumps(
                {
                    "uuid": self.run_uuid,
                    "platform": "android",
                    "filename": "spoofed",
                }
            ),
            content_type="application/json",
            **self._bearer(),
        )
        self.assertEqual(finalize_response.status_code, 200)
        self.assertEqual(
            finalize_response.json()["files"],
            ["client.exe", "client.msi"],
        )
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "success")

        generated_response = self.client.get(
            "/check_for_file",
            {
                "filename": "client",
                "uuid": self.run_uuid,
                "platform": "windows",
            },
        )
        self.assertTemplateUsed(generated_response, "generated.html")
        self.assertContains(generated_response, "client.exe")
        self.assertContains(generated_response, "client.msi")

    def test_completed_github_run_without_finalize_is_not_reported_successful(self):
        self.run.status = ARTIFACT_PENDING_STATUS
        self.run.github_run_id = 123456
        self.run.save(update_fields=["status", "github_run_id"])
        (self.exe_dir / "client.exe").parent.mkdir(parents=True, exist_ok=True)
        (self.exe_dir / "client.exe").write_bytes(b"exe-only")
        self.client.force_login(self.run.owner)
        github_response = type(
            "GithubResponse",
            (),
            {
                "status_code": 200,
                "json": lambda self: {
                    "status": "completed",
                    "conclusion": "success",
                },
            },
        )()

        with patch("rdgenerator.views.requests.get", return_value=github_response):
            response = self.client.get(
                "/check_for_file",
                {
                    "filename": "client",
                    "uuid": self.run_uuid,
                    "platform": "windows",
                },
            )

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ARTIFACT_INCOMPLETE_STATUS)
        self.assertTemplateUsed(response, "failure.html")
        self.assertNotContains(response, "client.exe")

        second_response = self.client.get(
            "/check_for_file",
            {
                "filename": "client",
                "uuid": self.run_uuid,
                "platform": "windows",
            },
        )
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ARTIFACT_INCOMPLETE_STATUS)
        self.assertTemplateUsed(second_response, "failure.html")

    def test_github_poll_does_not_overwrite_concurrent_finalize(self):
        self.run.status = ARTIFACT_PENDING_STATUS
        self.run.github_run_id = 123456
        self.run.save(update_fields=["status", "github_run_id"])
        self.client.force_login(self.run.owner)

        class GithubResponse:
            status_code = 200

            def json(inner_self):
                GithubRun.objects.filter(pk=self.run.pk).update(status="success")
                return {"status": "completed", "conclusion": "success"}

        with patch("rdgenerator.views.requests.get", return_value=GithubResponse()):
            response = self.client.get(
                "/check_for_file",
                {
                    "filename": "client",
                    "uuid": self.run_uuid,
                    "platform": "windows",
                },
            )

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "success")
        self.assertTemplateUsed(response, "generated.html")

    def test_cleanup_requires_token_and_deletes_only_matching_archive(self):
        matching = self.temp_dir / f"secrets_{self.run_uuid}_build.zip"
        unrelated = self.temp_dir / f"secrets_{uuid.uuid4()}_build.zip"
        matching.write_bytes(b"matching")
        unrelated.write_bytes(b"unrelated")
        self.created_temp_files.extend([matching, unrelated])
        payload = json.dumps({"uuid": self.run_uuid})

        response = self.client.post(
            "/cleanzip",
            payload,
            content_type="application/json",
            **self._bearer(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(matching.exists())
        self.assertTrue(unrelated.exists())

    def test_signed_zip_rejects_missing_tampered_and_expired_signatures(self):
        filename = f"secrets_{self.run_uuid}_build.zip"
        archive = self.temp_dir / filename
        archive.write_bytes(b"zip-data")
        self.created_temp_files.append(archive)
        signature = signing.dumps(
            {"filename": filename},
            salt=ZIP_DOWNLOAD_SALT,
        )

        self.assertEqual(self.client.get(f"/get_zip?filename={filename}").status_code, 403)
        self.assertEqual(
            self.client.get(
                f"/get_zip?filename=secrets_other.zip&signature={signature}"
            ).status_code,
            403,
        )
        response = self.client.get(
            f"/get_zip?filename={filename}&signature={signature}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"zip-data")

        with patch("rdgenerator.views.ZIP_DOWNLOAD_MAX_AGE", -1):
            expired = self.client.get(
                f"/get_zip?filename={filename}&signature={signature}"
            )
        self.assertEqual(expired.status_code, 403)

    @override_settings(API_SHARED_SECRET="shared-api-token")
    def test_startgh_rejects_requests_without_shared_api_token(self):
        response = self.client.post(
            "/startgh",
            json.dumps({"platform": "windows"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_machine_post_endpoints_are_csrf_exempt_after_token_auth(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            "/updategh",
            json.dumps({"uuid": self.run_uuid, "status": "success"}),
            content_type="application/json",
            **self._bearer(),
        )

        self.assertEqual(response.status_code, 200)
