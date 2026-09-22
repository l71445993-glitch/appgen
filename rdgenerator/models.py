from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone


class GenerationQuotaExceeded(Exception):
    """Raised when a non-administrator cannot reserve a generation."""


class UserEntitlement(models.Model):
    """Generation policy for a managed account.

    Built-in Django users remain the source of authentication/activation state;
    this model only governs whether a new client package may be submitted.
    """

    EXPIRATION_TIME = "time"
    EXPIRATION_COUNT = "count"
    EXPIRATION_CHOICES = (
        (EXPIRATION_TIME, "按时间"),
        (EXPIRATION_COUNT, "按生成次数"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="entitlement",
    )
    expiration_mode = models.CharField(
        max_length=10,
        choices=EXPIRATION_CHOICES,
        default=EXPIRATION_TIME,
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    generation_limit = models.PositiveIntegerField(null=True, blank=True)
    generations_used = models.PositiveIntegerField(default=0)
    reserved_generations = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "用户生成额度"
        verbose_name_plural = "用户生成额度"

    @property
    def is_expired(self):
        if self.expiration_mode == self.EXPIRATION_TIME:
            return bool(self.expires_at and timezone.now() >= self.expires_at)
        if self.generation_limit is None:
            return True
        return self.generations_used + self.reserved_generations >= self.generation_limit

    @property
    def can_generate(self):
        return self.can_reserve()

    @property
    def remaining_generations(self):
        if self.generation_limit is None:
            return None
        return max(
            self.generation_limit - self.generations_used - self.reserved_generations,
            0,
        )

    def can_reserve(self):
        if self.expiration_mode == self.EXPIRATION_TIME:
            return not self.is_expired
        return bool(
            self.generation_limit is not None
            and self.generations_used + self.reserved_generations
            < self.generation_limit
        )


class RegistrationEmailCode(models.Model):
    """Short-lived, one-time verification code for public registration.

    The six-digit bearer value is never persisted. Only a keyed digest is
    stored so a database leak cannot be used to complete registration.
    """

    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=64, editable=False)
    request_ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    invalidated_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(
                fields=("email", "created_at"),
                name="rdgen_reg_email_created_idx",
            ),
        ]
        verbose_name = "注册邮箱验证码"
        verbose_name_plural = "注册邮箱验证码"

    @property
    def is_available(self):
        return bool(
            self.consumed_at is None
            and self.invalidated_at is None
            and timezone.now() < self.expires_at
        )

    def __str__(self):
        local, separator, domain = self.email.partition("@")
        masked_local = f"{local[:2]}***" if local else "***"
        masked_email = f"{masked_local}{separator}{domain}" if separator else masked_local
        timestamp = (
            self.created_at.strftime("%Y-%m-%d %H:%M")
            if self.created_at
            else "未发送"
        )
        return f"{masked_email} · {timestamp}"


class ActivationCode(models.Model):
    """One-time membership code.

    Only a keyed digest and a short hint are persisted. The bearer value is
    returned to an administrator once when it is generated.
    """

    PLAN_SINGLE = "single"
    PLAN_THREE_DAY = "3day"
    PLAN_WEEK = "week"
    PLAN_MONTH = "month"
    PLAN_LIFETIME = "lifetime"
    PLAN_CHOICES = (
        (PLAN_SINGLE, "次卡（1 次生成）"),
        (PLAN_THREE_DAY, "3 日卡"),
        (PLAN_WEEK, "周卡（7 天）"),
        (PLAN_MONTH, "月卡（30 天）"),
        (PLAN_LIFETIME, "终身卡"),
    )

    code_hash = models.CharField(max_length=64, unique=True, editable=False)
    code_hint = models.CharField(max_length=4, editable=False)
    plan = models.CharField(max_length=12, choices=PLAN_CHOICES, db_index=True)
    batch_label = models.CharField(max_length=80, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activation_codes_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activation_codes_redeemed",
    )
    redeemed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activation_codes_revoked",
    )
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "会员激活码"
        verbose_name_plural = "会员激活码"

    @property
    def status(self):
        if self.redeemed_at:
            return "redeemed"
        if self.revoked_at:
            return "revoked"
        return "unused"

    @property
    def status_label(self):
        return {
            "redeemed": "已使用",
            "revoked": "已作废",
            "unused": "未使用",
        }[self.status]

    @property
    def masked_code(self):
        prefix = {
            self.PLAN_SINGLE: "1X",
            self.PLAN_THREE_DAY: "3D",
            self.PLAN_WEEK: "7D",
            self.PLAN_MONTH: "30D",
            self.PLAN_LIFETIME: "LIFE",
        }.get(self.plan, "CODE")
        return f"RD-{prefix}-••••-••••-••••-{self.code_hint}"

    def __str__(self):
        return f"{self.get_plan_display()} · {self.masked_code}"


def get_user_entitlement(user):
    entitlement, _created = UserEntitlement.objects.get_or_create(user=user)
    return entitlement


def reserve_generation(user):
    """Atomically reserve one count-based generation for a user.

    Staff and superusers are intentionally unlimited. Time-based policies do
    not need a reservation, but are still checked here so expired accounts are
    blocked before dispatching a workflow.
    """
    if user.is_staff or user.is_superuser:
        return False
    entitlement, _created = UserEntitlement.objects.get_or_create(user=user)
    with transaction.atomic():
        entitlement = UserEntitlement.objects.select_for_update().get(pk=entitlement.pk)
        if not entitlement.can_reserve():
            raise GenerationQuotaExceeded
        if entitlement.expiration_mode == UserEntitlement.EXPIRATION_COUNT:
            updated = UserEntitlement.objects.filter(
                pk=entitlement.pk,
                expiration_mode=UserEntitlement.EXPIRATION_COUNT,
                generation_limit__isnull=False,
                reserved_generations__lt=F("generation_limit") - F("generations_used"),
            ).update(reserved_generations=F("reserved_generations") + 1)
            if not updated:
                raise GenerationQuotaExceeded
            return True
    return False


def release_generation_reservation(run):
    """Release a pending reservation once a run cannot produce an artifact."""
    if not run.quota_reserved or run.quota_counted:
        return False
    with transaction.atomic():
        owner_id = GithubRun.objects.only("owner_id").get(pk=run.pk).owner_id
        released = GithubRun.objects.filter(
            pk=run.pk,
            quota_reserved=True,
            quota_counted=False,
        ).update(quota_reserved=False)
        if not released:
            return False
        if owner_id:
            UserEntitlement.objects.filter(
                user_id=owner_id,
                reserved_generations__gt=0,
            ).update(
                reserved_generations=F("reserved_generations") - 1,
                updated_at=timezone.now(),
            )
        run.quota_reserved = False
        return True


def mark_artifact_uploaded(run, uploaded_at=None, artifact_file_count=None):
    """Record valid package delivery and settle a reservation exactly once."""
    uploaded_at = uploaded_at or timezone.now()
    with transaction.atomic():
        snapshot = GithubRun.objects.select_for_update().only(
            "owner_id",
            "quota_chargeable",
            "quota_reserved",
            "quota_counted",
            "download_ttl_hours",
            "artifact_file_count",
        ).get(pk=run.pk)
        ttl_hours = min(max(int(snapshot.download_ttl_hours or 168), 1), 168)
        if artifact_file_count is None:
            file_count = F("artifact_file_count") + 1
        else:
            file_count = max(
                snapshot.artifact_file_count,
                max(int(artifact_file_count), 1),
            )
        GithubRun.objects.filter(pk=run.pk).update(artifact_file_count=file_count)
        GithubRun.objects.filter(
            pk=run.pk,
            artifact_uploaded_at__isnull=True,
        ).update(
            artifact_uploaded_at=uploaded_at,
            artifact_expires_at=uploaded_at + timedelta(days=7),
            download_expires_at=uploaded_at + timedelta(hours=ttl_hours),
        )
        if not snapshot.quota_counted:
            GithubRun.objects.filter(pk=run.pk).update(
                quota_reserved=False,
                quota_counted=True,
            )
            if snapshot.quota_chargeable and snapshot.owner_id:
                entitlement = UserEntitlement.objects.filter(
                    user_id=snapshot.owner_id,
                )
                settled = 0
                if snapshot.quota_reserved:
                    settled = entitlement.filter(
                        reserved_generations__gt=0,
                    ).update(
                        generations_used=F("generations_used") + 1,
                        reserved_generations=F("reserved_generations") - 1,
                        updated_at=timezone.now(),
                    )
                if not settled:
                    entitlement.update(
                        generations_used=F("generations_used") + 1,
                        updated_at=timezone.now(),
                    )
        run.refresh_from_db()
    return run


class GithubRun(models.Model):
    id = models.AutoField(verbose_name="ID", primary_key=True)
    uuid = models.CharField(verbose_name="uuid", max_length=100)
    status = models.CharField(verbose_name="status", max_length=100)
    github_run_id = models.BigIntegerField(null=True, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="github_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    callback_token_hash = models.CharField(max_length=64, blank=True, default="")
    download_access = models.CharField(max_length=10, default="login")
    download_ttl_hours = models.PositiveSmallIntegerField(default=168)
    download_token_hash = models.CharField(max_length=64, blank=True, default="")
    download_expires_at = models.DateTimeField(null=True, blank=True)
    artifact_uploaded_at = models.DateTimeField(null=True, blank=True)
    artifact_expires_at = models.DateTimeField(null=True, blank=True)
    artifact_file_count = models.PositiveIntegerField(default=0)
    platform = models.CharField(max_length=20, blank=True, default="")
    artifact_stem = models.CharField(max_length=255, blank=True, default="")
    smart_multi_relay = models.BooleanField(default=False)
    quota_chargeable = models.BooleanField(default=False)
    quota_reserved = models.BooleanField(default=False)
    quota_counted = models.BooleanField(default=False)


class GeneratedArtifact(models.Model):
    run = models.ForeignKey(
        GithubRun,
        on_delete=models.CASCADE,
        related_name="artifacts",
    )
    filename = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("run", "filename"),
                name="unique_generated_artifact_per_run",
            ),
        ]


def create_github_run_with_reservation(user, **run_fields):
    """Reserve count quota and persist its run as one database operation."""
    with transaction.atomic():
        quota_reserved = reserve_generation(user)
        return GithubRun.objects.create(
            owner=user,
            quota_chargeable=quota_reserved,
            quota_reserved=quota_reserved,
            **run_fields,
        )
