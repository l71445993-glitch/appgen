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
    disable_reason = models.CharField(max_length=255, blank=True, default="")
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
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="未使用激活码的过期时间；到期后自动作废。",
    )
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
        if self.expires_at and timezone.now() >= self.expires_at:
            return "expired"
        return "unused"

    @property
    def status_label(self):
        return {
            "redeemed": "已使用",
            "revoked": "已作废",
            "expired": "已过期",
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
    success_email_sent_at = models.DateTimeField(null=True, blank=True)
    config_snapshot = models.JSONField(null=True, blank=True, default=None)
    failure_summary = models.TextField(blank=True, default="")
    failure_summary_at = models.DateTimeField(null=True, blank=True)


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


class SiteEmailConfig(models.Model):
    """Singleton SMTP settings editable by superusers in the web UI."""

    host = models.CharField("SMTP 服务器", max_length=255, blank=True, default="smtp.qq.com")
    port = models.PositiveIntegerField("端口", default=465)
    username = models.CharField("发信账号", max_length=255, blank=True, default="")
    password = models.CharField("授权码/密码", max_length=255, blank=True, default="")
    use_ssl = models.BooleanField("使用 SSL", default=True)
    use_tls = models.BooleanField("使用 TLS", default=False)
    from_email = models.EmailField("发件人地址", blank=True, default="")
    enabled = models.BooleanField("启用邮件发送", default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "站点邮件配置"
        verbose_name_plural = "站点邮件配置"

    def __str__(self):
        return f"SiteEmailConfig<{self.host}:{self.port}>"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_configured(self):
        return bool(
            self.enabled
            and self.host
            and self.port
            and self.username
            and self.password
            and (self.from_email or self.username)
        )

    @property
    def effective_from_email(self):
        return (self.from_email or self.username or "").strip()


class SiteWecomConfig(models.Model):
    """Singleton WeCom group-robot webhook for admin-console alerts."""

    enabled = models.BooleanField("启用企业微信通知", default=False)
    webhook_url = models.URLField("机器人 Webhook 地址", blank=True, default="", max_length=500)
    notify_remote_login = models.BooleanField("异地登录提醒", default=True)
    notify_admin_login = models.BooleanField("超管登录成功提醒", default=False)
    notify_build_failure = models.BooleanField("构建失败提醒", default=True)
    notify_build_success = models.BooleanField("构建成功提醒", default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "企业微信通知配置"
        verbose_name_plural = "企业微信通知配置"

    def __str__(self):
        return f"SiteWecomConfig<enabled={self.enabled}>"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_configured(self):
        url = (self.webhook_url or "").strip()
        return bool(
            self.enabled
            and url.startswith("https://")
            and "qyapi.weixin.qq.com" in url
        )


class SiteTencentCosConfig(models.Model):
    """Singleton Tencent COS settings (independent from Aliyun OSS)."""

    enabled = models.BooleanField("启用腾讯云 COS", default=False)
    key_prefix = models.CharField(
        "对象前缀",
        max_length=128,
        blank=True,
        default="rdgen",
        help_text="例如 rdgen → rdgen/{uuid}/filename.exe",
    )
    secret_id = models.CharField("SecretId", max_length=255, blank=True, default="")
    secret_key = models.CharField("SecretKey", max_length=255, blank=True, default="")
    region = models.CharField(
        "地域",
        max_length=64,
        blank=True,
        default="ap-guangzhou",
        help_text="例如 ap-guangzhou / ap-shanghai",
    )
    bucket = models.CharField(
        "桶名",
        max_length=255,
        blank=True,
        default="",
        help_text="完整桶名，含 APPID，例如 rdgen-artifacts-125xxxxxxx",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "腾讯云 COS 配置"
        verbose_name_plural = "腾讯云 COS 配置"

    def __str__(self):
        return f"SiteTencentCosConfig<enabled={self.enabled}>"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def normalized_prefix(self):
        return (self.key_prefix or "rdgen").strip().strip("/")

    @property
    def is_ready(self):
        return bool(
            (self.secret_id or "").strip()
            and (self.secret_key or "").strip()
            and (self.region or "").strip()
            and (self.bucket or "").strip()
        )

    @property
    def is_configured(self):
        return bool(self.enabled and self.is_ready)

    @property
    def status_label(self):
        if not self.enabled:
            return "已关闭"
        return "可用" if self.is_ready else "未完成（凭证不齐）"


class SiteAliyunOssConfig(models.Model):
    """Singleton Aliyun OSS settings (independent from Tencent COS)."""

    enabled = models.BooleanField("启用阿里云 OSS", default=False)
    key_prefix = models.CharField(
        "对象前缀",
        max_length=128,
        blank=True,
        default="rdgen",
        help_text="例如 rdgen → rdgen/{uuid}/filename.exe",
    )
    access_key_id = models.CharField("AccessKeyId", max_length=255, blank=True, default="")
    access_key_secret = models.CharField(
        "AccessKeySecret", max_length=255, blank=True, default=""
    )
    endpoint = models.CharField(
        "Endpoint",
        max_length=255,
        blank=True,
        default="https://oss-cn-hangzhou.aliyuncs.com",
        help_text="例如 https://oss-cn-hangzhou.aliyuncs.com",
    )
    bucket = models.CharField("桶名", max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "阿里云 OSS 配置"
        verbose_name_plural = "阿里云 OSS 配置"

    def __str__(self):
        return f"SiteAliyunOssConfig<enabled={self.enabled}>"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def normalized_prefix(self):
        return (self.key_prefix or "rdgen").strip().strip("/")

    @property
    def is_ready(self):
        return bool(
            (self.access_key_id or "").strip()
            and (self.access_key_secret or "").strip()
            and (self.endpoint or "").strip()
            and (self.bucket or "").strip()
        )

    @property
    def is_configured(self):
        return bool(self.enabled and self.is_ready)

    @property
    def status_label(self):
        if not self.enabled:
            return "已关闭"
        return "可用" if self.is_ready else "未完成（凭证不齐）"


class SiteOpsConfig(models.Model):
    """Singleton site operations toggles (maintenance / announcement)."""

    maintenance_enabled = models.BooleanField("维护模式", default=False)
    maintenance_message = models.TextField(
        "维护提示",
        blank=True,
        default="生成器正在维护中，请稍后再试。",
    )
    announcement = models.TextField("前台公告", blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "站点运维配置"
        verbose_name_plural = "站点运维配置"

    def __str__(self):
        return f"SiteOpsConfig<maintenance={self.maintenance_enabled}>"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class EmailDeliveryLog(models.Model):
    KIND_REGISTRATION = "registration"
    KIND_BUILD_SUCCESS = "build_success"
    KIND_TEST = "test"
    KIND_EXPIRY_REMINDER = "expiry_reminder"
    KIND_LOGIN_ALERT = "login_alert"
    KIND_CHOICES = (
        (KIND_REGISTRATION, "注册验证码"),
        (KIND_BUILD_SUCCESS, "构建成功通知"),
        (KIND_TEST, "SMTP 测试"),
        (KIND_EXPIRY_REMINDER, "会员到期提醒"),
        (KIND_LOGIN_ALERT, "异地登录提醒"),
    )

    kind = models.CharField(max_length=32, choices=KIND_CHOICES, db_index=True)
    to_email = models.EmailField(db_index=True)
    success = models.BooleanField(default=False, db_index=True)
    error_message = models.CharField(max_length=500, blank=True, default="")
    subject = models.CharField(max_length=255, blank=True, default="")
    related_run = models.ForeignKey(
        GithubRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_logs",
    )
    related_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_delivery_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "邮件投递日志"
        verbose_name_plural = "邮件投递日志"

    def __str__(self):
        state = "成功" if self.success else "失败"
        return f"{self.get_kind_display()} · {self.to_email} · {state}"


class DownloadEvent(models.Model):
    run = models.ForeignKey(
        GithubRun,
        on_delete=models.CASCADE,
        related_name="download_events",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="download_events",
    )
    filename = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "下载审计"
        verbose_name_plural = "下载审计"
        indexes = [
            models.Index(fields=("run", "created_at"), name="rdgen_dl_run_created_idx"),
        ]

    def __str__(self):
        return f"{self.filename} · {self.created_at}"


class AdminAuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_audit_logs",
    )
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    detail = models.JSONField(null=True, blank=True, default=None)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "超管操作审计"
        verbose_name_plural = "超管操作审计"

    def __str__(self):
        actor = getattr(self.actor, "username", None) or "系统"
        return f"{actor} · {self.action} · {self.created_at}"


class LoginEvent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="login_events",
    )
    success = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    remote_alert_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "登录事件"
        verbose_name_plural = "登录事件"

    def __str__(self):
        return f"{self.user_id} · {self.ip_address} · {self.created_at}"
