import re
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .membership import (
    ActivationCodeUnavailable,
    MembershipPlanConflict,
    activation_code_digest,
    generate_activation_codes,
    redeem_activation_code,
)
from .models import ActivationCode, RegistrationEmailCode, UserEntitlement


User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.com",
)
class PublicRegistrationTests(TestCase):
    def _request_code(self, email="member@example.com", ip="203.0.113.10"):
        response = self.client.post(
            reverse("users:registration_email_code"),
            {"email": email},
            REMOTE_ADDR=ip,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        match = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_registration_creates_logged_in_account_without_membership(self):
        verification_code = self._request_code()
        response = self.client.post(
            reverse("users:register"),
            {
                "username": "new-member",
                "email": "member@example.com",
                "verification_code": verification_code,
                "password1": "Register-Password-2026",
                "password2": "Register-Password-2026",
            },
        )

        self.assertRedirects(response, reverse("generator"))
        user = User.objects.get(username="new-member")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        entitlement = user.entitlement
        self.assertEqual(entitlement.expiration_mode, UserEntitlement.EXPIRATION_COUNT)
        self.assertIsNone(entitlement.generation_limit)
        self.assertFalse(entitlement.can_generate)
        email_code = RegistrationEmailCode.objects.get()
        self.assertIsNotNone(email_code.consumed_at)
        self.assertNotEqual(email_code.code_hash, verification_code)

        workspace = self.client.get(reverse("generator"))
        self.assertContains(workspace, "未开通会员")
        self.assertContains(workspace, "请先激活会员")
        self.assertContains(workspace, reverse("users:activate"))

    def test_registration_page_is_public_and_linked_from_login(self):
        response = self.client.get(reverse("users:register"))
        login_response = self.client.get(reverse("users:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "创建账号")
        self.assertContains(response, "获取验证码")
        self.assertContains(login_response, reverse("users:register"))

    def test_email_code_is_sent_and_raw_value_is_not_stored(self):
        verification_code = self._request_code("Verified@Example.com")

        record = RegistrationEmailCode.objects.get()
        self.assertEqual(record.email, "verified@example.com")
        self.assertNotEqual(record.code_hash, verification_code)
        self.assertEqual(mail.outbox[0].to, ["verified@example.com"])

    def test_resend_is_rate_limited(self):
        self._request_code()

        response = self.client.post(
            reverse("users:registration_email_code"),
            {"email": "member@example.com"},
            REMOTE_ADDR="203.0.113.10",
        )

        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.json()["ok"])
        self.assertGreater(response.json()["retry_after"], 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_wrong_email_code_rejects_registration_and_counts_attempt(self):
        verification_code = self._request_code()
        wrong_code = "000000" if verification_code != "000000" else "000001"

        response = self.client.post(
            reverse("users:register"),
            {
                "username": "wrong-code-member",
                "email": "member@example.com",
                "verification_code": wrong_code,
                "password1": "Register-Password-2026",
                "password2": "Register-Password-2026",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "验证码不正确")
        self.assertFalse(User.objects.filter(username="wrong-code-member").exists())
        self.assertEqual(RegistrationEmailCode.objects.get().failed_attempts, 1)

    def test_expired_email_code_rejects_registration(self):
        verification_code = self._request_code()
        RegistrationEmailCode.objects.update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        response = self.client.post(
            reverse("users:register"),
            {
                "username": "expired-code-member",
                "email": "member@example.com",
                "verification_code": verification_code,
                "password1": "Register-Password-2026",
                "password2": "Register-Password-2026",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "验证码已过期")
        self.assertFalse(User.objects.filter(username="expired-code-member").exists())

    def test_email_code_cannot_be_used_for_another_address(self):
        verification_code = self._request_code("first@example.com")

        response = self.client.post(
            reverse("users:register"),
            {
                "username": "different-email-member",
                "email": "second@example.com",
                "verification_code": verification_code,
                "password1": "Register-Password-2026",
                "password2": "Register-Password-2026",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "请先获取邮箱验证码")
        self.assertFalse(User.objects.filter(username="different-email-member").exists())

    def test_send_code_endpoint_requires_post(self):
        response = self.client.get(reverse("users:registration_email_code"))

        self.assertEqual(response.status_code, 405)

    def test_registration_rejects_duplicate_email_case_insensitively(self):
        User.objects.create_user("existing", email="Member@Example.com")

        response = self.client.post(
            reverse("users:register"),
            {
                "username": "duplicate-email",
                "email": "member@example.com",
                "verification_code": "123456",
                "password1": "Register-Password-2026",
                "password2": "Register-Password-2026",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "该邮箱已被其他账号使用")
        self.assertFalse(User.objects.filter(username="duplicate-email").exists())

    def test_authenticated_user_is_redirected_away_from_registration(self):
        user = User.objects.create_user("already-signed-in")
        self.client.force_login(user)

        response = self.client.get(reverse("users:register"))

        self.assertRedirects(response, reverse("generator"))


class ActivationCodeServiceTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("code-admin", is_staff=True)
        self.user = User.objects.create_user("code-user")
        self.entitlement = UserEntitlement.objects.create(
            user=self.user,
            expiration_mode=UserEntitlement.EXPIRATION_COUNT,
            generation_limit=None,
        )
        self.now = datetime(2026, 8, 5, 4, 0, tzinfo=datetime_timezone.utc)

    def _code(self, plan):
        return generate_activation_codes(
            plan=plan,
            quantity=1,
            created_by=self.staff,
            batch_label="test-batch",
        )[0]

    def test_generated_code_is_hashed_and_can_be_entered_without_separators(self):
        generated = self._code(ActivationCode.PLAN_SINGLE)
        stored = generated.activation_code

        self.assertRegex(generated.raw_code, r"^RD-1X(?:-[A-Z2-9]{4}){4}$")
        self.assertEqual(stored.code_hash, activation_code_digest(generated.raw_code))
        self.assertNotIn(generated.raw_code, stored.__dict__.values())

        result = redeem_activation_code(
            user=self.user,
            raw_code=generated.raw_code.replace("-", "").lower(),
            now=self.now,
        )

        self.assertEqual(result.activation_code.pk, stored.pk)
        self.entitlement.refresh_from_db()
        self.assertEqual(self.entitlement.generation_limit, 1)
        self.assertEqual(self.entitlement.remaining_generations, 1)

    def test_repeated_single_cards_add_one_remaining_generation(self):
        self.entitlement.generation_limit = 2
        self.entitlement.generations_used = 2
        self.entitlement.save(
            update_fields=["generation_limit", "generations_used"]
        )
        first = self._code(ActivationCode.PLAN_SINGLE)
        second = self._code(ActivationCode.PLAN_SINGLE)

        redeem_activation_code(user=self.user, raw_code=first.raw_code, now=self.now)
        redeem_activation_code(user=self.user, raw_code=second.raw_code, now=self.now)

        self.entitlement.refresh_from_db()
        self.assertEqual(self.entitlement.generation_limit, 4)
        self.assertEqual(self.entitlement.remaining_generations, 2)

    def test_duration_cards_start_now_and_extend_existing_expiry(self):
        three_day = self._code(ActivationCode.PLAN_THREE_DAY)
        week = self._code(ActivationCode.PLAN_WEEK)

        redeem_activation_code(user=self.user, raw_code=three_day.raw_code, now=self.now)
        self.entitlement.refresh_from_db()
        self.assertEqual(self.entitlement.expires_at, self.now + timedelta(days=3))

        redeem_activation_code(user=self.user, raw_code=week.raw_code, now=self.now)
        self.entitlement.refresh_from_db()
        self.assertEqual(self.entitlement.expires_at, self.now + timedelta(days=10))

    def test_month_card_is_thirty_days(self):
        month = self._code(ActivationCode.PLAN_MONTH)

        redeem_activation_code(user=self.user, raw_code=month.raw_code, now=self.now)

        self.entitlement.refresh_from_db()
        self.assertEqual(self.entitlement.expires_at, self.now + timedelta(days=30))

    def test_lifetime_card_grants_permanent_membership(self):
        lifetime = self._code(ActivationCode.PLAN_LIFETIME)

        redeem_activation_code(user=self.user, raw_code=lifetime.raw_code, now=self.now)

        self.entitlement.refresh_from_db()
        self.assertEqual(self.entitlement.expiration_mode, UserEntitlement.EXPIRATION_TIME)
        self.assertIsNone(self.entitlement.expires_at)
        self.assertTrue(self.entitlement.can_generate)

    def test_used_code_cannot_be_redeemed_twice(self):
        generated = self._code(ActivationCode.PLAN_SINGLE)
        other_user = User.objects.create_user("other-code-user")
        UserEntitlement.objects.create(
            user=other_user,
            expiration_mode=UserEntitlement.EXPIRATION_COUNT,
        )
        redeem_activation_code(
            user=self.user,
            raw_code=generated.raw_code,
            now=self.now,
        )

        with self.assertRaises(ActivationCodeUnavailable):
            redeem_activation_code(
                user=other_user,
                raw_code=generated.raw_code,
                now=self.now,
            )

    def test_conflicting_plan_does_not_consume_code_or_change_entitlement(self):
        self.entitlement.generation_limit = 2
        self.entitlement.generations_used = 0
        self.entitlement.save(
            update_fields=["generation_limit", "generations_used"]
        )
        duration = self._code(ActivationCode.PLAN_THREE_DAY)

        with self.assertRaises(MembershipPlanConflict):
            redeem_activation_code(
                user=self.user,
                raw_code=duration.raw_code,
                now=self.now,
            )

        duration.activation_code.refresh_from_db()
        self.entitlement.refresh_from_db()
        self.assertIsNone(duration.activation_code.redeemed_at)
        self.assertEqual(self.entitlement.expiration_mode, UserEntitlement.EXPIRATION_COUNT)
        self.assertEqual(self.entitlement.generation_limit, 2)

    def test_active_time_member_cannot_waste_single_card(self):
        self.entitlement.expiration_mode = UserEntitlement.EXPIRATION_TIME
        self.entitlement.expires_at = self.now + timedelta(days=1)
        self.entitlement.generation_limit = None
        self.entitlement.save(
            update_fields=["expiration_mode", "expires_at", "generation_limit"]
        )
        single = self._code(ActivationCode.PLAN_SINGLE)

        with self.assertRaises(MembershipPlanConflict):
            redeem_activation_code(
                user=self.user,
                raw_code=single.raw_code,
                now=self.now,
            )

        single.activation_code.refresh_from_db()
        self.assertIsNone(single.activation_code.redeemed_at)


class ActivationCodeViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("view-admin", is_staff=True)
        self.user = User.objects.create_user("view-member")
        UserEntitlement.objects.create(
            user=self.user,
            expiration_mode=UserEntitlement.EXPIRATION_COUNT,
            generation_limit=None,
        )

    def _generation_token(self):
        response = self.client.get(reverse("users:activation_codes"))
        return response.context["generation_form"]["request_token"].value()

    def test_staff_can_generate_batch_and_later_list_only_masked_codes(self):
        self.client.force_login(self.staff)
        request_token = self._generation_token()

        response = self.client.post(
            reverse("users:activation_codes"),
            {
                "request_token": request_token,
                "plan": ActivationCode.PLAN_THREE_DAY,
                "quantity": 2,
                "batch_label": "xianyu",
            },
        )

        self.assertEqual(response.status_code, 200)
        raw_codes = re.findall(
            r"RD-3D(?:-[A-Z2-9]{4}){4}",
            response.content.decode(),
        )
        self.assertEqual(len(set(raw_codes)), 2)
        self.assertEqual(ActivationCode.objects.count(), 2)

        later_response = self.client.get(reverse("users:activation_codes"))
        for raw_code in raw_codes:
            self.assertNotContains(later_response, raw_code)
        self.assertContains(later_response, "RD-3D-••••-••••-••••-")

    def test_refreshing_generation_response_does_not_create_duplicate_codes(self):
        self.client.force_login(self.staff)
        request_token = self._generation_token()
        payload = {
            "request_token": request_token,
            "plan": ActivationCode.PLAN_SINGLE,
            "quantity": 2,
            "batch_label": "idempotent-batch",
        }

        first_response = self.client.post(reverse("users:activation_codes"), payload)
        repeated_response = self.client.post(reverse("users:activation_codes"), payload)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(ActivationCode.objects.count(), 2)
        self.assertContains(repeated_response, "该生成请求已处理或页面已过期")
        self.assertNotContains(repeated_response, "本次生成结果")
        self.assertEqual(ActivationCode.objects.count(), 2)

    def test_regular_user_cannot_open_or_generate_codes(self):
        self.client.force_login(self.user)

        get_response = self.client.get(reverse("users:activation_codes"))
        post_response = self.client.post(
            reverse("users:activation_codes"),
            {"plan": ActivationCode.PLAN_SINGLE, "quantity": 1},
        )

        self.assertEqual(get_response.status_code, 403)
        self.assertEqual(post_response.status_code, 403)
        self.assertFalse(ActivationCode.objects.exists())

    def test_user_can_activate_from_workspace_and_code_becomes_used(self):
        generated = generate_activation_codes(
            plan=ActivationCode.PLAN_SINGLE,
            quantity=1,
            created_by=self.staff,
        )[0]
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("users:activate"),
            {"code": generated.raw_code},
            follow=True,
        )

        self.assertRedirects(response, reverse("generator"))
        self.assertContains(response, "激活成功，已增加 1 次生成额度")
        self.user.entitlement.refresh_from_db()
        self.assertEqual(self.user.entitlement.remaining_generations, 1)
        generated.activation_code.refresh_from_db()
        self.assertEqual(generated.activation_code.redeemed_by, self.user)

    def test_staff_can_revoke_unused_code_and_revoked_code_cannot_activate(self):
        generated = generate_activation_codes(
            plan=ActivationCode.PLAN_SINGLE,
            quantity=1,
            created_by=self.staff,
        )[0]
        self.client.force_login(self.staff)
        revoke_response = self.client.post(
            reverse(
                "users:activation_code_revoke",
                args=[generated.activation_code.pk],
            )
        )
        self.assertRedirects(revoke_response, reverse("users:activation_codes"))

        self.client.force_login(self.user)
        activation_response = self.client.post(
            reverse("users:activate"),
            {"code": generated.raw_code},
            follow=True,
        )

        self.assertContains(activation_response, "该激活码已作废")
        self.user.entitlement.refresh_from_db()
        self.assertIsNone(self.user.entitlement.generation_limit)

    def test_activation_requires_login(self):
        response = self.client.post(reverse("users:activate"), {"code": "anything"})

        self.assertRedirects(
            response,
            f"{reverse('users:login')}?next={reverse('users:activate')}",
            fetch_redirect_response=False,
        )
