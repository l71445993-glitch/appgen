from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import GithubRun


User = get_user_model()


class BuildRecordListTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("record-owner", password="password")
        self.other = User.objects.create_user("record-other", password="password")
        self.staff = User.objects.create_user(
            "record-admin",
            password="password",
            is_staff=True,
        )
        self.owner_run = GithubRun.objects.create(
            uuid="11111111-1111-4111-8111-111111111111",
            status="success",
            owner=self.owner,
            platform="windows",
            artifact_stem="OwnerClient",
            smart_multi_relay=True,
            github_run_id=101,
            artifact_file_count=2,
            download_expires_at=timezone.now() + timedelta(days=1),
        )
        self.other_run = GithubRun.objects.create(
            uuid="22222222-2222-4222-8222-222222222222",
            status="failure",
            owner=self.other,
            platform="android",
            artifact_stem="OtherClient",
            github_run_id=202,
        )
        deleted_owner = User.objects.create_user("deleted-owner", password="password")
        self.deleted_run = GithubRun.objects.create(
            uuid="33333333-3333-4333-8333-333333333333",
            status="timed_out",
            owner=deleted_owner,
            platform="linux",
            artifact_stem="LegacyClient",
        )
        deleted_owner.delete()

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("users:build_records"))

        self.assertRedirects(
            response,
            f"/login/?next={reverse('users:build_records')}",
            fetch_redirect_response=False,
        )

    def test_regular_user_only_sees_own_records(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("users:build_records"))

        self.assertContains(response, "OwnerClient")
        self.assertNotContains(response, "OtherClient")
        self.assertNotContains(response, "LegacyClient")
        self.assertContains(response, "查看结果")
        self.assertContains(response, "智能多中继")
        self.assertNotContains(response, "全部用户")

    def test_build_history_distinguishes_smart_and_standard_relay_modes(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("users:build_records"))

        self.assertContains(response, "智能多中继", count=1)
        self.assertContains(response, "标准中继", count=2)

    def test_staff_sees_all_records_including_deleted_owner(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("users:build_records"))

        self.assertContains(response, "OwnerClient")
        self.assertContains(response, "OtherClient")
        self.assertContains(response, "LegacyClient")
        self.assertContains(response, "账号已删除")
        self.assertContains(response, "record-owner")
        self.assertContains(response, "只读记录", count=3)

    def test_staff_can_filter_by_owner_status_platform_period_and_query(self):
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("users:build_records"),
            {
                "owner": str(self.other.pk),
                "status": "failure",
                "platform": "android",
                "period": "7d",
                "q": "OtherClient",
            },
        )

        self.assertContains(response, "OtherClient")
        self.assertNotContains(response, "OwnerClient")
        self.assertNotContains(response, "LegacyClient")
        self.assertContains(response, "筛选结果 1 条")

    def test_deleted_owner_filter_only_returns_orphaned_records(self):
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("users:build_records"),
            {"owner": "deleted"},
        )

        self.assertContains(response, "LegacyClient")
        self.assertNotContains(response, "OwnerClient")
        self.assertNotContains(response, "OtherClient")

    def test_invalid_filters_are_ignored(self):
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("users:build_records"),
            {
                "owner": "999999",
                "status": "not-a-status",
                "platform": "not-a-platform",
                "period": "forever",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_owner"], "")
        self.assertEqual(response.context["selected_status"], "")
        self.assertEqual(response.context["selected_platform"], "")
        self.assertEqual(response.context["selected_period"], "")
        self.assertEqual(response.context["page_obj"].paginator.count, 3)

    def test_sensitive_run_tokens_are_not_rendered(self):
        GithubRun.objects.filter(pk=self.owner_run.pk).update(
            callback_token_hash="callback-secret-hash",
            download_token_hash="download-secret-hash",
        )
        self.client.force_login(self.staff)

        response = self.client.get(reverse("users:build_records"))

        self.assertNotContains(response, "callback-secret-hash")
        self.assertNotContains(response, "download-secret-hash")

    def test_navigation_shows_build_records_for_regular_user(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("users:build_records"))

        self.assertContains(response, 'href="/build-records/" aria-current="page"')
        self.assertContains(response, ">构建记录</span>")
