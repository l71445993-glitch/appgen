import shutil
import uuid
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .models import GithubRun


@override_settings(LOGIN_URL="/login/")
class TaskAccessTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user("owner", password="password")
        self.other_user = user_model.objects.create_user("other", password="password")
        self.staff = user_model.objects.create_user(
            "staff",
            password="password",
            is_staff=True,
        )
        self.run_uuid = str(uuid.uuid4())
        self.run = GithubRun.objects.create(
            uuid=self.run_uuid,
            status="success",
            owner=self.owner,
        )
        self.output_dir = Path("exe") / self.run_uuid
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "client.exe").write_bytes(b"generated-client")

    def tearDown(self):
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def _status_url(self, run_uuid=None):
        return (
            "/check_for_file?filename=client&platform=windows&uuid="
            f"{run_uuid or self.run_uuid}"
        )

    def _download_url(self, filename="client.exe", run_uuid=None):
        return (
            f"/download?filename={filename}&uuid={run_uuid or self.run_uuid}"
        )

    def test_anonymous_generator_status_and_download_redirect_to_login(self):
        for url in ("/", "/generator", self._status_url(), self._download_url()):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith("/login/"))

    def test_owner_can_view_status_and_download_output(self):
        self.client.force_login(self.owner)

        status_response = self.client.get(self._status_url())
        download_response = self.client.get(self._download_url())

        self.assertEqual(status_response.status_code, 200)
        self.assertContains(status_response, "client.exe")
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.content, b"generated-client")

    def test_other_user_cannot_view_status_or_download_output(self):
        self.client.force_login(self.other_user)

        self.assertEqual(self.client.get(self._status_url()).status_code, 404)
        self.assertEqual(self.client.get(self._download_url()).status_code, 404)

    def test_staff_can_download_but_cannot_view_another_users_task_status(self):
        self.client.force_login(self.staff)

        self.assertEqual(self.client.get(self._status_url()).status_code, 404)
        self.assertEqual(self.client.get(self._download_url()).status_code, 200)

    def test_legacy_task_without_owner_is_not_exposed(self):
        legacy_uuid = str(uuid.uuid4())
        GithubRun.objects.create(uuid=legacy_uuid, status="success")
        self.client.force_login(self.owner)

        self.assertEqual(self.client.get(self._status_url(legacy_uuid)).status_code, 404)
        self.assertEqual(self.client.get(self._download_url(run_uuid=legacy_uuid)).status_code, 404)

    def test_download_rejects_noncanonical_uuid_and_path_components(self):
        self.client.force_login(self.owner)

        uppercase_uuid = self.run_uuid.upper()
        self.assertEqual(self.client.get(self._download_url(run_uuid=uppercase_uuid)).status_code, 404)
        for filename in ("../client.exe", "..\\client.exe", "sub/client.exe"):
            with self.subTest(filename=filename):
                self.assertEqual(
                    self.client.get(self._download_url(filename=filename)).status_code,
                    404,
                )
