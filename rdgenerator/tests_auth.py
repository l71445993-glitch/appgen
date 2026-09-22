from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import GithubRun


User = get_user_model()


class AuthenticationTests(TestCase):
    def setUp(self):
        self.password = "ValidPass-4096"
        self.user = User.objects.create_user(
            username="builder",
            password=self.password,
        )

    def test_login_succeeds_and_redirects_to_generator(self):
        response = self.client.post(
            reverse("users:login"),
            {"username": self.user.username, "password": self.password},
        )

        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    @override_settings(
        SECURE_SSL_REDIRECT=True,
        SECURE_REDIRECT_EXEMPT=[r"^healthz$"],
    )
    def test_health_check_stays_available_behind_https_redirect(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)

    def test_login_rejects_external_next_redirect(self):
        response = self.client.post(
            reverse("users:login"),
            {
                "username": self.user.username,
                "password": self.password,
                "next": "https://attacker.example/steal-session",
            },
        )

        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_health_check_is_available_without_login(self):
        response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_wrong_password_uses_generic_error(self):
        response = self.client.post(
            reverse("users:login"),
            {"username": self.user.username, "password": "wrong-password"},
        )

        self.assertContains(response, "用户名或密码不正确。")
        self.assertNotContains(response, "builder 不存在")

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("users:login"),
            {"username": self.user.username, "password": self.password},
        )

        self.assertContains(response, "用户名或密码不正确。")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_user_can_change_password_to_six_digit_numeric_value(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("users:password_change"),
            {
                "old_password": self.password,
                "new_password1": "123456",
                "new_password2": "123456",
            },
        )

        self.assertRedirects(response, reverse("users:password_change_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("123456"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_password_change_guidance_is_chinese(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("users:password_change"))

        self.assertContains(response, "密码至少 6 位，允许使用字母、数字或符号。")
        self.assertNotContains(response, "Your password")
        self.assertNotContains(response, "Enter the same password")

    def test_logout_rejects_get_and_accepts_csrf_protected_post(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.get(reverse("users:password_change"))
        csrf_token = response.cookies["csrftoken"].value

        get_response = client.get(reverse("users:logout"))
        self.assertEqual(get_response.status_code, 405)
        self.assertIn("_auth_user_id", client.session)

        no_csrf_response = client.post(reverse("users:logout"))
        self.assertEqual(no_csrf_response.status_code, 403)
        self.assertIn("_auth_user_id", client.session)

        post_response = client.post(
            reverse("users:logout"),
            {"csrfmiddlewaretoken": csrf_token},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertRedirects(post_response, "/login/", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", client.session)


class UserManagementTests(TestCase):
    def setUp(self):
        self.password = "ValidPass-4096"
        self.member = User.objects.create_user("member", password=self.password)
        self.staff = User.objects.create_user(
            "manager",
            password=self.password,
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            "root-admin",
            "root@example.com",
            self.password,
        )

    def test_regular_user_cannot_open_user_management(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse("users:list"))

        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_to_login_for_user_management(self):
        response = self.client.get(reverse("users:list"))

        self.assertRedirects(
            response,
            f"/login/?next={reverse('users:list')}",
            fetch_redirect_response=False,
        )

    def test_relaxed_password_policy_accepts_previously_rejected_passwords(self):
        self.client.force_login(self.staff)
        cases = (
            ("samepass", "samepass"),
            ("common-user", "password"),
            ("numeric-user", "123456"),
        )

        for username, password in cases:
            with self.subTest(username=username):
                response = self.client.post(
                    reverse("users:create"),
                    {
                        "username": username,
                        "is_active": "on",
                        "password1": password,
                        "password2": password,
                    },
                )

                self.assertRedirects(response, reverse("users:list"))
                self.assertTrue(
                    User.objects.get(username=username).check_password(password)
                )

    def test_password_policy_rejects_fewer_than_six_characters_in_chinese(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("users:create"),
            {
                "username": "short-password-user",
                "is_active": "on",
                "password1": "12345",
                "password2": "12345",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "密码至少需要 6 个字符。")
        self.assertFalse(User.objects.filter(username="short-password-user").exists())

    def test_password_guidance_is_chinese(self):
        self.client.force_login(self.staff)

        create_response = self.client.get(reverse("users:create"))
        reset_response = self.client.get(
            reverse("users:password", args=[self.member.pk])
        )

        for response in (create_response, reset_response):
            with self.subTest(path=response.request["PATH_INFO"]):
                self.assertContains(
                    response,
                    "密码至少 6 位，允许使用字母、数字或符号。",
                )
                self.assertContains(response, "请再次输入相同的密码。")
                self.assertNotContains(response, "Your password")
                self.assertNotContains(response, "Enter the same password")

        mismatch_response = self.client.post(
            reverse("users:create"),
            {
                "username": "mismatch-user",
                "is_active": "on",
                "password1": "abcdef",
                "password2": "abcdeg",
            },
        )
        self.assertContains(mismatch_response, "两次输入的密码不一致。")

    def test_staff_can_create_edit_reset_and_disable_regular_user(self):
        self.client.force_login(self.staff)
        create_response = self.client.post(
            reverse("users:create"),
            {
                "username": "new-builder",
                "email": "builder@example.com",
                "last_name": "Build",
                "first_name": "User",
                "is_active": "on",
                "is_staff": "on",
                "password1": "FreshPass-8192",
                "password2": "FreshPass-8192",
            },
        )
        self.assertRedirects(create_response, reverse("users:list"))
        created = User.objects.get(username="new-builder")
        self.assertFalse(created.is_staff)

        edit_response = self.client.post(
            reverse("users:edit", args=[created.pk]),
            {
                "username": "renamed-builder",
                "email": "renamed@example.com",
                "last_name": "Build",
                "first_name": "User",
                "is_active": "on",
            },
        )
        self.assertRedirects(edit_response, reverse("users:list"))
        created.refresh_from_db()
        self.assertEqual(created.username, "renamed-builder")

        password_response = self.client.post(
            reverse("users:password", args=[created.pk]),
            {
                "new_password1": "ResetPass-16384",
                "new_password2": "ResetPass-16384",
            },
        )
        self.assertRedirects(password_response, reverse("users:list"))
        created.refresh_from_db()
        self.assertTrue(created.check_password("ResetPass-16384"))

        toggle_response = self.client.post(reverse("users:toggle", args=[created.pk]))
        self.assertRedirects(toggle_response, reverse("users:list"))
        created.refresh_from_db()
        self.assertFalse(created.is_active)

    def test_staff_can_confirm_and_delete_regular_user(self):
        target = User.objects.create_user("delete-me", password=self.password)
        run = GithubRun.objects.create(
            id=701,
            uuid="delete-user-history",
            status="finished",
            owner=target,
        )
        self.client.force_login(self.staff)

        confirmation_response = self.client.get(reverse("users:delete", args=[target.pk]))

        self.assertEqual(confirmation_response.status_code, 200)
        self.assertContains(confirmation_response, "delete-me")
        self.assertTrue(User.objects.filter(pk=target.pk).exists())

        delete_response = self.client.post(reverse("users:delete", args=[target.pk]))

        self.assertRedirects(delete_response, reverse("users:list"))
        self.assertFalse(User.objects.filter(pk=target.pk).exists())
        run.refresh_from_db()
        self.assertIsNone(run.owner)

    def test_staff_cannot_delete_another_staff_user(self):
        other_staff = User.objects.create_user(
            "other-manager-to-delete",
            password=self.password,
            is_staff=True,
        )
        self.client.force_login(self.staff)

        response = self.client.get(reverse("users:delete", args=[other_staff.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=other_staff.pk).exists())

    def test_account_cannot_delete_itself(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("users:delete", args=[self.staff.pk]))

        self.assertRedirects(response, reverse("users:list"))
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())

        post_response = self.client.post(reverse("users:delete", args=[self.staff.pk]))

        self.assertRedirects(post_response, reverse("users:list"))
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())

    def test_superuser_cannot_delete_last_active_superuser(self):
        self.client.force_login(self.superuser)

        response = self.client.post(reverse("users:delete", args=[self.superuser.pk]))

        self.assertRedirects(response, reverse("users:list"))
        self.assertTrue(User.objects.filter(pk=self.superuser.pk).exists())

    def test_superuser_can_delete_another_superuser_when_one_remains(self):
        another_superuser = User.objects.create_superuser(
            "another-root",
            "another-root@example.com",
            self.password,
        )
        self.client.force_login(self.superuser)

        response = self.client.post(reverse("users:delete", args=[another_superuser.pk]))

        self.assertRedirects(response, reverse("users:list"))
        self.assertFalse(User.objects.filter(pk=another_superuser.pk).exists())

    def test_staff_cannot_manage_another_staff_user(self):
        other_staff = User.objects.create_user(
            "other-manager",
            password=self.password,
            is_staff=True,
        )
        self.client.force_login(self.staff)

        response = self.client.get(reverse("users:edit", args=[other_staff.pk]))

        self.assertEqual(response.status_code, 403)

    def test_resetting_own_password_keeps_current_session(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("users:password", args=[self.staff.pk]),
            {
                "new_password1": "ChangedPass-32768",
                "new_password2": "ChangedPass-32768",
            },
        )

        self.assertRedirects(response, reverse("users:list"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.staff.pk)

    def test_account_cannot_disable_itself(self):
        self.client.force_login(self.staff)

        response = self.client.post(reverse("users:toggle", args=[self.staff.pk]))

        self.assertRedirects(response, reverse("users:list"))
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_superuser_can_assign_staff_role(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse("users:edit", args=[self.member.pk]),
            {
                "username": self.member.username,
                "email": "",
                "last_name": "",
                "first_name": "",
                "is_staff": "on",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, reverse("users:list"))
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_staff)
