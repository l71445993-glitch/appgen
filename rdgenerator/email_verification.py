import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import RegistrationEmailCode


logger = logging.getLogger(__name__)
CODE_DIGEST_SALT = "rdgenerator.registration-email-code.v1"


class EmailVerificationError(Exception):
    """Base class for user-safe registration email errors."""


class EmailVerificationRateLimited(EmailVerificationError):
    def __init__(self, message, *, retry_after=60):
        super().__init__(message)
        self.retry_after = max(int(retry_after), 1)


class EmailVerificationDeliveryError(EmailVerificationError):
    pass


class InvalidEmailVerificationCode(EmailVerificationError):
    pass


@dataclass(frozen=True)
class IssuedEmailVerificationCode:
    record_id: int
    expires_at: object
    resend_after: int


def normalize_registration_email(email):
    return (email or "").strip().casefold()


def registration_email_code_digest(email, raw_code):
    normalized_email = normalize_registration_email(email)
    return salted_hmac(
        CODE_DIGEST_SALT,
        f"{normalized_email}\0{raw_code}",
        algorithm="sha256",
    ).hexdigest()


def _setting_int(name, default):
    return max(int(getattr(settings, name, default)), 1)


def _ensure_email_backend_is_configured():
    backend = settings.EMAIL_BACKEND
    if backend.endswith("smtp.EmailBackend") and (
        not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD
    ):
        raise EmailVerificationDeliveryError(
            "邮件服务暂未配置，请联系管理员。"
        )
    if backend.endswith("dummy.EmailBackend"):
        raise EmailVerificationDeliveryError(
            "邮件服务暂未配置，请联系管理员。"
        )
    if backend.endswith("console.EmailBackend") and not settings.DEBUG:
        raise EmailVerificationDeliveryError(
            "邮件服务暂未配置，请联系管理员。"
        )


def issue_registration_email_code(*, email, request_ip=None, now=None):
    normalized_email = normalize_registration_email(email)
    now = now or timezone.now()
    resend_seconds = _setting_int("EMAIL_VERIFICATION_RESEND_SECONDS", 60)
    email_hourly_limit = _setting_int(
        "EMAIL_VERIFICATION_EMAIL_HOURLY_LIMIT",
        5,
    )
    ip_hourly_limit = _setting_int("EMAIL_VERIFICATION_IP_HOURLY_LIMIT", 20)
    ttl_seconds = _setting_int("EMAIL_VERIFICATION_CODE_TTL_SECONDS", 300)
    hour_ago = now - timedelta(hours=1)

    _ensure_email_backend_is_configured()

    latest = (
        RegistrationEmailCode.objects.filter(email=normalized_email)
        .order_by("-created_at", "-pk")
        .first()
    )
    if latest:
        elapsed = max((now - latest.created_at).total_seconds(), 0)
        if elapsed < resend_seconds:
            retry_after = max(int(resend_seconds - elapsed + 0.999), 1)
            raise EmailVerificationRateLimited(
                f"发送过于频繁，请 {retry_after} 秒后重试。",
                retry_after=retry_after,
            )

    if RegistrationEmailCode.objects.filter(
        email=normalized_email,
        created_at__gte=hour_ago,
    ).count() >= email_hourly_limit:
        raise EmailVerificationRateLimited(
            "该邮箱获取验证码次数过多，请一小时后再试。",
            retry_after=3600,
        )

    if request_ip and RegistrationEmailCode.objects.filter(
        request_ip=request_ip,
        created_at__gte=hour_ago,
    ).count() >= ip_hourly_limit:
        raise EmailVerificationRateLimited(
            "当前网络获取验证码次数过多，请一小时后再试。",
            retry_after=3600,
        )

    raw_code = f"{secrets.randbelow(1_000_000):06d}"
    record = RegistrationEmailCode.objects.create(
        email=normalized_email,
        code_hash=registration_email_code_digest(normalized_email, raw_code),
        request_ip=request_ip,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )

    ttl_minutes = max((ttl_seconds + 59) // 60, 1)
    message = EmailMessage(
        subject="RustDesk 生成器注册验证码",
        body=(
            f"你的注册验证码是：{raw_code}\n\n"
            f"验证码将在 {ttl_minutes} 分钟后失效，且只能使用一次。\n"
            "如果不是你本人操作，请忽略此邮件。"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[normalized_email],
    )
    try:
        sent_count = message.send(fail_silently=False)
        if sent_count != 1:
            raise RuntimeError("Email backend did not accept the message")
    except Exception as exc:
        RegistrationEmailCode.objects.filter(pk=record.pk).update(
            invalidated_at=timezone.now()
        )
        logger.exception("Unable to deliver a registration verification email")
        raise EmailVerificationDeliveryError(
            "验证码发送失败，请稍后重试。"
        ) from exc

    RegistrationEmailCode.objects.filter(
        email=normalized_email,
        consumed_at__isnull=True,
        invalidated_at__isnull=True,
        created_at__lte=record.created_at,
    ).exclude(pk=record.pk).update(invalidated_at=now)

    return IssuedEmailVerificationCode(
        record_id=record.pk,
        expires_at=record.expires_at,
        resend_after=resend_seconds,
    )


def _verify_registration_email_code(*, email, raw_code, consume, now=None):
    normalized_email = normalize_registration_email(email)
    submitted_code = (raw_code or "").strip()
    now = now or timezone.now()
    max_attempts = _setting_int("EMAIL_VERIFICATION_MAX_ATTEMPTS", 5)
    error = None
    record = None

    with transaction.atomic():
        record = (
            RegistrationEmailCode.objects.select_for_update()
            .filter(
                email=normalized_email,
                consumed_at__isnull=True,
                invalidated_at__isnull=True,
            )
            .order_by("-created_at", "-pk")
            .first()
        )
        if record is None:
            error = InvalidEmailVerificationCode(
                "请先获取邮箱验证码，或重新获取后再试。"
            )
        elif now >= record.expires_at:
            record.invalidated_at = now
            record.save(update_fields=["invalidated_at"])
            error = InvalidEmailVerificationCode("验证码已过期，请重新获取。")
        elif record.failed_attempts >= max_attempts:
            record.invalidated_at = now
            record.save(update_fields=["invalidated_at"])
            error = InvalidEmailVerificationCode(
                "验证码尝试次数过多，请重新获取。"
            )
        elif not (
            len(submitted_code) == 6
            and submitted_code.isascii()
            and submitted_code.isdigit()
            and constant_time_compare(
                record.code_hash,
                registration_email_code_digest(normalized_email, submitted_code),
            )
        ):
            record.failed_attempts += 1
            update_fields = ["failed_attempts"]
            if record.failed_attempts >= max_attempts:
                record.invalidated_at = now
                update_fields.append("invalidated_at")
                error = InvalidEmailVerificationCode(
                    "验证码尝试次数过多，请重新获取。"
                )
            else:
                error = InvalidEmailVerificationCode(
                    "验证码不正确，请检查后重试。"
                )
            record.save(update_fields=update_fields)
        elif consume:
            consumed = RegistrationEmailCode.objects.filter(
                pk=record.pk,
                consumed_at__isnull=True,
                invalidated_at__isnull=True,
            ).update(consumed_at=now)
            if consumed:
                record.consumed_at = now
            else:
                error = InvalidEmailVerificationCode(
                    "验证码已经使用或失效，请重新获取。"
                )

    if error:
        raise error
    return record


def validate_registration_email_code(*, email, raw_code, now=None):
    return _verify_registration_email_code(
        email=email,
        raw_code=raw_code,
        consume=False,
        now=now,
    )


def consume_registration_email_code(*, email, raw_code, now=None):
    return _verify_registration_email_code(
        email=email,
        raw_code=raw_code,
        consume=True,
        now=now,
    )
