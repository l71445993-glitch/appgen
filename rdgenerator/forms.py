import ipaddress
import re
from urllib.parse import urlsplit

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm, UserCreationForm
from django.db import transaction
from django.utils import timezone
from django.core.validators import RegexValidator, URLValidator
from PIL import Image

from .email_verification import (
    EmailVerificationError,
    consume_registration_email_code,
    normalize_registration_email,
    validate_registration_email_code,
)
from .membership import normalize_activation_code
from .models import (
    ActivationCode,
    SiteAliyunOssConfig,
    SiteEmailConfig,
    SiteOpsConfig,
    SiteTencentCosConfig,
    SiteWecomConfig,
    UserEntitlement,
    get_user_entitlement,
)
from .validators import minimum_password_help_text


User = get_user_model()

PASSWORD_HELP_TEXT = minimum_password_help_text(settings.PASSWORD_MIN_LENGTH)
PASSWORD_CONFIRM_HELP_TEXT = "请再次输入相同的密码。"


class UsernameAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "用户名或密码不正确。",
        "inactive": "用户名或密码不正确。",
    }

    username = forms.CharField(
        label="用户名",
        error_messages={"required": "请输入用户名。"},
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="密码",
        strip=False,
        error_messages={"required": "请输入密码。"},
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class AdminAuthenticationForm(UsernameAuthenticationForm):
    """Superuser login with a one-shot visual captcha."""

    captcha = forms.CharField(
        label="验证码",
        max_length=8,
        min_length=4,
        strip=True,
        error_messages={"required": "请输入验证码。"},
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "autocapitalize": "characters",
                "spellcheck": "false",
                "inputmode": "text",
                "placeholder": "不区分大小写",
            }
        ),
    )

    def clean(self):
        from .admin_captcha import verify_admin_captcha

        captcha = self.cleaned_data.get("captcha")
        if not verify_admin_captcha(self.request, captcha):
            self.add_error("captcha", "验证码不正确或已过期，请刷新后重试。")
            # Drop credentials so AuthenticationForm does not authenticate.
            self.cleaned_data.pop("password", None)
            return self.cleaned_data
        return super().clean()


class PublicRegistrationForm(UserCreationForm):
    error_messages = {
        "password_mismatch": "两次输入的密码不一致。",
    }

    email = forms.EmailField(
        label="邮箱",
        required=True,
        help_text="用于接收注册验证码，每个邮箱只能注册一个账号。",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    verification_code = forms.CharField(
        label="邮箱验证码",
        max_length=6,
        min_length=6,
        strip=True,
        error_messages={"required": "请输入邮箱验证码。"},
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "pattern": "[0-9]{6}",
                "placeholder": "6 位验证码",
            }
        ),
    )
    field_order = ("username", "email", "verification_code", "password1", "password2")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "用户名"
        self.fields["username"].widget.attrs.update(
            {"autofocus": True, "autocomplete": "username"}
        )
        self.fields["password1"].label = "密码"
        self.fields["password1"].help_text = PASSWORD_HELP_TEXT
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].label = "确认密码"
        self.fields["password2"].help_text = PASSWORD_CONFIRM_HELP_TEXT
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"

    def clean_email(self):
        email = normalize_registration_email(self.cleaned_data.get("email", ""))
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("该邮箱已被其他账号使用。")
        return email

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        verification_code = cleaned.get("verification_code")
        if email and verification_code:
            try:
                validate_registration_email_code(
                    email=email,
                    raw_code=verification_code,
                )
            except EmailVerificationError as exc:
                self.add_error("verification_code", str(exc))
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get("email", "")
        if not commit:
            return user
        with transaction.atomic():
            consume_registration_email_code(
                email=user.email,
                raw_code=self.cleaned_data["verification_code"],
            )
            user.save()
            UserEntitlement.objects.create(
                user=user,
                expiration_mode=UserEntitlement.EXPIRATION_COUNT,
                generation_limit=None,
            )
        return user


class RegistrationEmailCodeRequestForm(forms.Form):
    email = forms.EmailField(
        label="邮箱",
        required=True,
        error_messages={
            "required": "请输入邮箱地址。",
            "invalid": "请输入有效的邮箱地址。",
        },
    )

    def clean_email(self):
        email = normalize_registration_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("该邮箱已被其他账号使用。")
        return email


class SiteEmailConfigForm(forms.ModelForm):
    password = forms.CharField(
        label="授权码 / SMTP 密码",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="留空表示不修改已保存的授权码。",
    )
    test_recipient = forms.EmailField(
        label="测试收件邮箱",
        required=False,
        widget=forms.EmailInput(
            attrs={
                "placeholder": "留空则发到当前登录账号邮箱",
                "autocomplete": "email",
            }
        ),
        help_text="点「发送测试邮件」时使用。会先保存上方设置再发信。",
    )

    class Meta:
        model = SiteEmailConfig
        fields = (
            "enabled",
            "host",
            "port",
            "username",
            "password",
            "from_email",
            "use_ssl",
            "use_tls",
        )
        labels = {
            "enabled": "启用邮件发送",
            "host": "SMTP 服务器",
            "port": "端口",
            "username": "发信账号",
            "from_email": "发件人地址",
            "use_ssl": "使用 SSL（常见 465）",
            "use_tls": "使用 TLS（常见 587）",
        }
        help_texts = {
            "host": "例如 smtp.qq.com / smtp.163.com",
            "from_email": "留空则使用发信账号作为发件人。",
            "use_ssl": "与 TLS 一般二选一，不要同时开启。",
            "use_tls": "与 SSL 一般二选一，不要同时开启。",
        }

    def __init__(self, *args, **kwargs):
        self._default_test_recipient = (kwargs.pop("default_test_recipient", "") or "").strip()
        super().__init__(*args, **kwargs)
        self._existing_password = ""
        if self.instance and self.instance.pk:
            self._existing_password = self.instance.password or ""
        if self._default_test_recipient and not self.data:
            self.fields["test_recipient"].initial = self._default_test_recipient

    def clean(self):
        cleaned = super().clean()
        use_ssl = cleaned.get("use_ssl")
        use_tls = cleaned.get("use_tls")
        if use_ssl and use_tls:
            raise forms.ValidationError("SSL 与 TLS 不要同时开启，QQ 邮箱请只勾选 SSL。")
        if cleaned.get("enabled"):
            if not cleaned.get("host"):
                self.add_error("host", "启用邮件时必须填写 SMTP 服务器。")
            if not cleaned.get("username"):
                self.add_error("username", "启用邮件时必须填写发信账号。")
            if not (cleaned.get("password") or self._existing_password):
                self.add_error("password", "启用邮件时必须填写授权码。")
        return cleaned

    def resolved_test_recipient(self):
        value = (self.cleaned_data.get("test_recipient") or "").strip()
        return value or self._default_test_recipient

    def save(self, commit=True):
        obj = super().save(commit=False)
        new_password = self.cleaned_data.get("password") or ""
        if new_password:
            obj.password = new_password
        else:
            obj.password = self._existing_password
        if commit:
            obj.save()
        return obj


class ActivationCodeForm(forms.Form):
    code = forms.CharField(
        label="会员激活码",
        max_length=64,
        strip=True,
        error_messages={"required": "请输入激活码。"},
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "autocapitalize": "characters",
                "spellcheck": "false",
                "placeholder": "RD-XXXX-XXXX-XXXX-XXXX",
            }
        ),
    )

    def clean_code(self):
        raw_code = self.cleaned_data["code"]
        normalized = normalize_activation_code(raw_code)
        if not normalized.startswith("RD") or not 20 <= len(normalized) <= 22:
            raise forms.ValidationError("激活码格式不正确。")
        return raw_code


class ActivationCodeGenerationForm(forms.Form):
    request_token = forms.CharField(widget=forms.HiddenInput)
    plan = forms.ChoiceField(label="卡种", choices=ActivationCode.PLAN_CHOICES)
    quantity = forms.IntegerField(
        label="生成数量",
        min_value=1,
        max_value=100,
        initial=1,
        widget=forms.NumberInput(attrs={"min": 1, "max": 100}),
    )
    batch_label = forms.CharField(
        label="批次备注",
        max_length=80,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "例如：闲鱼 8 月第一批"}),
    )
    expires_at = forms.DateTimeField(
        label="未使用过期时间（可选）",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
        help_text="到期后未使用的码会自动作废。留空表示不过期。",
    )

    def clean_expires_at(self):
        expires_at = self.cleaned_data.get("expires_at")
        if expires_at and timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at)
        if expires_at and expires_at <= timezone.now():
            raise forms.ValidationError("过期时间必须晚于当前时间。")
        return expires_at


class SiteOpsConfigForm(forms.ModelForm):
    class Meta:
        model = SiteOpsConfig
        fields = ("maintenance_enabled", "maintenance_message", "announcement")
        labels = {
            "maintenance_enabled": "开启维护模式",
            "maintenance_message": "维护页提示文案",
            "announcement": "公告内容",
        }
        widgets = {
            "maintenance_message": forms.Textarea(attrs={"rows": 3}),
            "announcement": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "例如：今晚 23:00–01:00 系统升级，生成可能延迟。",
                }
            ),
        }
        help_texts = {
            "maintenance_enabled": "开启后前台对普通用户显示整页维护；超管可继续访问。",
            "maintenance_message": "仅出现在维护页，不会作为弹窗。",
            "announcement": "留空则不弹窗。有内容时在前台弹窗显示（非维护页横幅）。",
        }


class SiteWecomConfigForm(forms.ModelForm):
    class Meta:
        model = SiteWecomConfig
        fields = (
            "enabled",
            "webhook_url",
            "notify_remote_login",
            "notify_admin_login",
            "notify_build_failure",
            "notify_build_success",
        )
        labels = {
            "enabled": "启用企业微信通知",
            "webhook_url": "群机器人 Webhook",
            "notify_remote_login": "异地登录提醒",
            "notify_admin_login": "超管登录成功提醒",
            "notify_build_failure": "构建失败提醒",
            "notify_build_success": "构建成功提醒",
        }
        widgets = {
            "webhook_url": forms.URLInput(
                attrs={
                    "placeholder": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...",
                    "autocomplete": "off",
                }
            ),
        }
        help_texts = {
            "webhook_url": "企业微信群 → 添加群机器人 → 复制 Webhook 地址。仅用于超管后台提醒。",
            "notify_admin_login": "每次超管成功登录都推一条（可能较吵，默认关）。",
            "notify_build_failure": "构建进入失败/取消/超时等终态时推送。",
            "notify_build_success": "安装包回传成功后推送（可能较吵，默认关）。",
        }

    def clean_webhook_url(self):
        url = (self.cleaned_data.get("webhook_url") or "").strip()
        if not url:
            return ""
        if not url.startswith("https://"):
            raise forms.ValidationError("Webhook 必须是 https:// 地址。")
        if "qyapi.weixin.qq.com" not in url:
            raise forms.ValidationError("请填写企业微信官方机器人 Webhook 地址。")
        if "key=" not in url:
            raise forms.ValidationError("Webhook 地址缺少 key 参数。")
        return url

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("enabled") and not cleaned.get("webhook_url"):
            self.add_error("webhook_url", "启用通知时必须填写 Webhook 地址。")
        return cleaned


class SiteTencentCosConfigForm(forms.ModelForm):
    secret_key = forms.CharField(
        label="SecretKey",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="留空表示不修改已保存的 SecretKey。",
    )

    class Meta:
        model = SiteTencentCosConfig
        fields = ("enabled", "key_prefix", "secret_id", "secret_key", "region", "bucket")
        labels = {
            "enabled": "启用腾讯云 COS",
            "key_prefix": "对象前缀",
            "secret_id": "SecretId",
            "region": "地域",
            "bucket": "桶名",
        }
        widgets = {
            "secret_id": forms.TextInput(attrs={"autocomplete": "off"}),
            "region": forms.TextInput(attrs={"placeholder": "ap-guangzhou"}),
            "bucket": forms.TextInput(
                attrs={"placeholder": "rdgen-artifacts-125xxxxxxx", "autocomplete": "off"}
            ),
            "key_prefix": forms.TextInput(attrs={"placeholder": "rdgen"}),
        }
        help_texts = {
            "enabled": "仅控制腾讯云 COS，与阿里云 OSS 互不影响。",
            "key_prefix": "对象路径前缀，最终形如 rdgen/{uuid}/xxx.exe。",
            "bucket": "只填桶名，例如 rdgen-artifacts-125xxxxxxx。不要填 https:// 或 .cos.xxx.myqcloud.com。",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._existing_secret_key = ""
        if self.instance and self.instance.pk:
            self._existing_secret_key = self.instance.secret_key or ""

    def clean_key_prefix(self):
        value = (self.cleaned_data.get("key_prefix") or "").strip().strip("/")
        return value or "rdgen"

    def clean_bucket(self):
        import re

        value = (self.cleaned_data.get("bucket") or "").strip()
        if not value:
            return ""
        value = value.replace("https://", "").replace("http://", "")
        value = value.split("/")[0]
        if ".cos." in value:
            value = value.split(".cos.")[0]
        if not re.fullmatch(r"[A-Za-z0-9-]+", value):
            raise forms.ValidationError(
                "桶名只能包含字母、数字和短横线 -。请填 rdgen-artifacts-125xxxxxxx，不要填访问域名。"
            )
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("enabled"):
            for field in ("secret_id", "region", "bucket"):
                if not (cleaned.get(field) or "").strip():
                    self.add_error(field, "启用腾讯云 COS 时必填。")
            if not (cleaned.get("secret_key") or self._existing_secret_key):
                self.add_error("secret_key", "启用腾讯云 COS 时必须填写 SecretKey。")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.secret_key = self.cleaned_data.get("secret_key") or self._existing_secret_key
        if commit:
            obj.save()
        return obj


class SiteAliyunOssConfigForm(forms.ModelForm):
    access_key_secret = forms.CharField(
        label="AccessKeySecret",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="留空表示不修改已保存的 AccessKeySecret。",
    )

    class Meta:
        model = SiteAliyunOssConfig
        fields = (
            "enabled",
            "key_prefix",
            "access_key_id",
            "access_key_secret",
            "endpoint",
            "bucket",
        )
        labels = {
            "enabled": "启用阿里云 OSS",
            "key_prefix": "对象前缀",
            "access_key_id": "AccessKeyId",
            "endpoint": "Endpoint",
            "bucket": "桶名",
        }
        widgets = {
            "access_key_id": forms.TextInput(attrs={"autocomplete": "off"}),
            "endpoint": forms.TextInput(
                attrs={"placeholder": "https://oss-cn-hangzhou.aliyuncs.com"}
            ),
            "bucket": forms.TextInput(attrs={"autocomplete": "off"}),
            "key_prefix": forms.TextInput(attrs={"placeholder": "rdgen"}),
        }
        help_texts = {
            "enabled": "仅控制阿里云 OSS，与腾讯云 COS 互不影响。",
            "key_prefix": "对象路径前缀，最终形如 rdgen/{uuid}/xxx.exe。",
            "endpoint": "建议带 https://；地域需与桶一致。",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._existing_access_key_secret = ""
        if self.instance and self.instance.pk:
            self._existing_access_key_secret = self.instance.access_key_secret or ""

    def clean_key_prefix(self):
        value = (self.cleaned_data.get("key_prefix") or "").strip().strip("/")
        return value or "rdgen"

    def clean_endpoint(self):
        endpoint = (self.cleaned_data.get("endpoint") or "").strip()
        if not endpoint:
            return ""
        if endpoint.startswith("http://"):
            raise forms.ValidationError("请使用 https:// Endpoint。")
        if not endpoint.startswith("https://"):
            endpoint = f"https://{endpoint}"
        return endpoint.rstrip("/")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("enabled"):
            for field in ("access_key_id", "endpoint", "bucket"):
                if not (cleaned.get(field) or "").strip():
                    self.add_error(field, "启用阿里云 OSS 时必填。")
            if not (cleaned.get("access_key_secret") or self._existing_access_key_secret):
                self.add_error(
                    "access_key_secret",
                    "启用阿里云 OSS 时必须填写 AccessKeySecret。",
                )
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.access_key_secret = (
            self.cleaned_data.get("access_key_secret") or self._existing_access_key_secret
        )
        if commit:
            obj.save()
        return obj


class ManagedUserCreationForm(UserCreationForm):
    error_messages = {
        "password_mismatch": "两次输入的密码不一致。",
    }

    email = forms.EmailField(label="邮箱", required=False)
    first_name = forms.CharField(label="名", max_length=150, required=False)
    last_name = forms.CharField(label="姓", max_length=150, required=False)
    is_staff = forms.BooleanField(label="管理员", required=False)
    is_active = forms.BooleanField(label="允许登录", required=False, initial=True)
    expiration_mode = forms.ChoiceField(
        label="生成额度类型",
        choices=UserEntitlement.EXPIRATION_CHOICES,
        initial=UserEntitlement.EXPIRATION_TIME,
        required=False,
    )
    expires_at = forms.DateTimeField(
        label="过期时间（北京时间）",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )
    generation_limit = forms.IntegerField(
        label="可生成次数",
        required=False,
        min_value=1,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "email",
            "last_name",
            "first_name",
            "is_staff",
            "is_active",
            "expiration_mode",
            "expires_at",
            "generation_limit",
        )

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.fields["username"].label = "用户名"
        self.fields["password1"].label = "密码"
        self.fields["password1"].help_text = PASSWORD_HELP_TEXT
        self.fields["password2"].label = "确认密码"
        self.fields["password2"].help_text = PASSWORD_CONFIRM_HELP_TEXT
        if not actor or not actor.is_superuser:
            self.fields.pop("is_staff", None)

    def save(self, commit=True):
        user = super().save(commit=False)
        if not self.actor or not self.actor.is_superuser:
            user.is_staff = False
        if commit:
            user.save()
            self._save_entitlement(user)
        return user

    def clean(self):
        cleaned = super().clean()
        _clean_entitlement_fields(self, cleaned)
        return cleaned

    def _save_entitlement(self, user):
        entitlement, _created = UserEntitlement.objects.get_or_create(user=user)
        _apply_entitlement_fields(entitlement, self.cleaned_data)


class ManagedUserEditForm(forms.ModelForm):
    email = forms.EmailField(label="邮箱", required=False)
    first_name = forms.CharField(label="名", max_length=150, required=False)
    last_name = forms.CharField(label="姓", max_length=150, required=False)
    is_staff = forms.BooleanField(label="管理员", required=False)
    is_active = forms.BooleanField(label="允许登录", required=False)
    expiration_mode = forms.ChoiceField(
        label="生成额度类型",
        choices=UserEntitlement.EXPIRATION_CHOICES,
        required=False,
    )
    expires_at = forms.DateTimeField(
        label="过期时间（北京时间）",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )
    generation_limit = forms.IntegerField(
        label="可生成次数",
        required=False,
        min_value=1,
    )
    disable_reason = forms.CharField(
        label="禁用原因",
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"placeholder": "停用时可填写原因，便于复盘"}),
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "last_name",
            "first_name",
            "is_staff",
            "is_active",
            "expiration_mode",
            "expires_at",
            "generation_limit",
            "disable_reason",
        )
        labels = {"username": "用户名"}

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        entitlement = get_user_entitlement(self.instance)
        self.initial.update(
            {
                "expiration_mode": entitlement.expiration_mode,
                "expires_at": entitlement.expires_at,
                "generation_limit": entitlement.generation_limit,
                "disable_reason": entitlement.disable_reason,
            }
        )
        if not actor or not actor.is_superuser:
            self.fields.pop("is_staff", None)

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            entitlement, _created = UserEntitlement.objects.get_or_create(user=user)
            _apply_entitlement_fields(entitlement, self.cleaned_data)
            reason = (self.cleaned_data.get("disable_reason") or "").strip()
            if not user.is_active:
                entitlement.disable_reason = reason
            elif user.is_active and not reason:
                entitlement.disable_reason = ""
            else:
                entitlement.disable_reason = reason
            entitlement.save(update_fields=["disable_reason", "updated_at"])
        return user

    def clean(self):
        cleaned = super().clean()
        _clean_entitlement_fields(self, cleaned)
        return cleaned

    def clean_is_active(self):
        is_active = self.cleaned_data["is_active"]
        if self.instance.pk == getattr(self.actor, "pk", None) and not is_active:
            raise forms.ValidationError("不能停用当前登录账号。")
        if self.instance.is_superuser and not is_active:
            has_another_superuser = User.objects.filter(
                is_superuser=True,
                is_active=True,
            ).exclude(pk=self.instance.pk).exists()
            if not has_another_superuser:
                raise forms.ValidationError("不能停用最后一个可用的超级管理员。")
        return is_active

    def clean_is_staff(self):
        is_staff = self.cleaned_data["is_staff"]
        if self.instance.is_superuser and not is_staff:
            raise forms.ValidationError("超级管理员必须保留管理员权限。")
        return is_staff


def _clean_entitlement_fields(form, cleaned):
    mode = cleaned.get("expiration_mode") or UserEntitlement.EXPIRATION_TIME
    cleaned["expiration_mode"] = mode
    expires_at = cleaned.get("expires_at")
    generation_limit = cleaned.get("generation_limit")
    if mode == UserEntitlement.EXPIRATION_TIME:
        if expires_at and timezone.is_naive(expires_at):
            cleaned["expires_at"] = timezone.make_aware(expires_at)
        cleaned["generation_limit"] = None
    elif mode == UserEntitlement.EXPIRATION_COUNT:
        if not generation_limit or generation_limit < 1:
            form.add_error("generation_limit", "按生成次数时必须填写大于 0 的次数。")
        cleaned["expires_at"] = None
    return cleaned


def _apply_entitlement_fields(entitlement, cleaned):
    previous_mode = entitlement.expiration_mode
    entitlement.expiration_mode = (
        cleaned.get("expiration_mode") or UserEntitlement.EXPIRATION_TIME
    )
    entitlement.expires_at = cleaned.get("expires_at")
    entitlement.generation_limit = cleaned.get("generation_limit")
    if previous_mode != entitlement.expiration_mode:
        entitlement.generations_used = 0
        entitlement.reserved_generations = 0
    entitlement.save(
        update_fields=[
            "expiration_mode",
            "expires_at",
            "generation_limit",
            "generations_used",
            "reserved_generations",
            "updated_at",
        ]
    )


class ManagedSetPasswordForm(SetPasswordForm):
    error_messages = {
        "password_mismatch": "两次输入的密码不一致。",
    }

    new_password1 = forms.CharField(
        label="新密码",
        strip=False,
        help_text=PASSWORD_HELP_TEXT,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        label="确认新密码",
        strip=False,
        help_text=PASSWORD_CONFIRM_HELP_TEXT,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )


SAFE_PACKAGE_NAME = RegexValidator(
    regex=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    message="仅允许英文字母、数字、下划线和连字符，且首字符必须是字母或数字。",
)
SAFE_NAME_TEXT = RegexValidator(
    regex=r"""^[^\x00-\x1f\x7f"'`;&|$<>:\\/?*]+$""",
    message="名称包含构建脚本不支持的字符。",
)
SAFE_SCRIPT_VALUE = RegexValidator(
    regex=r"""^[^\x00-\x1f\x7f"'`;&|$<>\\]+$""",
    message="内容包含构建脚本不支持的字符。",
)
SINGLE_RELAY_SERVER = RegexValidator(
    regex=r"^[^,]+$",
    message="固定中继服务器只能填写一个地址；多中继列表应配置在 hbbs。",
)
SAFE_COMPANY_VALUE = RegexValidator(
    regex=r"""^[^\x00-\x1f\x7f"'`;|$<>\\]+$""",
    message="公司名称包含构建脚本不支持的字符。",
)
HTTP_URL = URLValidator(
    schemes=("http", "https"),
    message="请输入以 http:// 或 https:// 开头的完整地址。",
)
ANDROID_APP_ID = RegexValidator(
    regex=r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$",
    message="Android App ID 必须是类似 com.example.app 的合法包名。",
)

WINDOWS_RESERVED_NAME = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])$",
    re.IGNORECASE,
)
MAX_BUILD_NAME_UTF8_BYTES = 200
BEIJING_LINUX_VERSIONS = {"1.4.7", "1.4.8", "1.4.9"}
FORM_SCHEMA_VERSION = "2"
SMART_MULTI_RELAY_PLATFORMS = {'windows', 'windows-x86', 'linux', 'android'}
SMART_RENDEZVOUS_DOMAIN = re.compile(
    r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z"
)


def validate_portable_name(value):
    if len(value.encode("utf-8")) > MAX_BUILD_NAME_UTF8_BYTES:
        raise forms.ValidationError("名称的 UTF-8 编码长度不能超过 200 字节。")
    if value.startswith("-"):
        raise forms.ValidationError("名称不能以连字符开头。")
    if value.endswith((".", " ")):
        raise forms.ValidationError("名称不能以句点或空格结尾。")
    stem = value.split(".", 1)[0].rstrip(" ")
    if WINDOWS_RESERVED_NAME.fullmatch(stem):
        raise forms.ValidationError("名称不能使用 Windows 保留设备名。")


def parse_manual_settings(value):
    settings = {}
    for line_number, raw_line in enumerate((value or "").splitlines(), start=1):
        if not raw_line.strip():
            continue
        key, separator, setting_value = raw_line.partition("=")
        if not separator or not key.strip():
            raise forms.ValidationError(
                f"第 {line_number} 行必须使用 key=value 格式，且 key 不能为空。"
            )
        settings[key.strip()] = setting_value.strip()
    return settings


def extract_manual_setting(value, target_key):
    setting_value = None
    retained_lines = []
    for raw_line in (value or "").splitlines():
        key, separator, value_part = raw_line.partition("=")
        normalized_key = key.strip().replace('_', '-')
        if separator and normalized_key == target_key:
            setting_value = value_part.strip()
        else:
            retained_lines.append(raw_line)
    return setting_value, "\n".join(retained_lines)


def version_at_least(value, minimum):
    if value == 'master':
        return True
    try:
        current = tuple(int(part) for part in value.split('.'))
    except (AttributeError, ValueError):
        return False
    return current >= minimum


def is_smart_rendezvous_domain(value):
    value = (value or '').strip()
    if not value or '://' in value or any(character.isspace() for character in value):
        return False
    try:
        parsed = urlsplit(f'//{value}')
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    if not hostname or (port is not None and not 1 <= port <= 65535):
        return False
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return SMART_RENDEZVOUS_DOMAIN.fullmatch(hostname) is not None
    return False


def is_https_api_server(value):
    try:
        parsed = urlsplit((value or '').strip())
    except ValueError:
        return False
    return parsed.scheme.lower() == 'https' and bool(parsed.hostname)


class GenerateForm(forms.Form):
    sh_secret_field = forms.CharField(required=False)
    formSchemaVersion = forms.CharField(
        initial=FORM_SCHEMA_VERSION,
        required=False,
        widget=forms.HiddenInput(),
    )
    smartMultiRelay = forms.BooleanField(
        label="智能多中继",
        initial=False,
        required=False,
    )
    #Platform
    platform = forms.ChoiceField(choices=[
        ('windows', 'Windows 64 位'),
        ('windows-x86', 'Windows 32 位'),
        ('linux', 'Linux'),
        ('android', 'Android'),
        ('macos', 'macOS'),
        ('ios', 'iOS（未签名 IPA）'),
    ], initial='windows')
    version = forms.ChoiceField(
        choices=[('master','nightly'),('1.4.9','1.4.9'),('1.4.8','1.4.8'),('1.4.7','1.4.7'),('1.4.6','1.4.6'),('1.4.5','1.4.5'),('1.4.4','1.4.4'),('1.4.3','1.4.3'),('1.4.2','1.4.2'),('1.4.1','1.4.1'),('1.4.0','1.4.0'),('1.3.9','1.3.9'),('1.3.8','1.3.8'),('1.3.7','1.3.7'),('1.3.6','1.3.6'),('1.3.5','1.3.5'),('1.3.4','1.3.4'),('1.3.3','1.3.3')],
        initial='1.4.9',
        help_text="nightly 是开发版，功能更新但稳定性可能较低"
    )
    delayFix = forms.BooleanField(initial=True, required=False)
    beijingCustom = forms.BooleanField(label="北京 Linux 定制", initial=False, required=False)

    # Delivery policy for generated packages. The artifact upload callback
    # starts both retention clocks; values are persisted on GithubRun.
    download_access = forms.ChoiceField(
        label="下载权限",
        choices=[
            ("login", "必须登录下载"),
            ("public", "无需登录下载"),
        ],
        initial="login",
        required=False,
    )
    download_ttl_hours = forms.TypedChoiceField(
        label="下载链接有效期",
        choices=[
            (1, "1 小时"),
            (24, "1 天"),
            (72, "3 天"),
            (168, "7 天"),
        ],
        coerce=int,
        initial=168,
        required=False,
    )

    #General
    exename = forms.CharField(
        label="配置名称",
        required=True,
        max_length=64,
        validators=[SAFE_PACKAGE_NAME, validate_portable_name],
    )
    appname = forms.CharField(
        label="应用名称",
        required=False,
        max_length=64,
        validators=[SAFE_NAME_TEXT, validate_portable_name],
    )
    direction = forms.ChoiceField(widget=forms.RadioSelect, choices=[
        ('incoming', '仅允许被控'),
        ('outgoing', '仅允许主控'),
        ('both', '双向连接')
    ], initial='both')
    installation = forms.ChoiceField(label="安装能力", choices=[
        ('installationY', '允许安装'),
        ('installationN', '禁用安装')
    ], initial='installationY')
    settings = forms.ChoiceField(label="设置入口", choices=[
        ('settingsY', '允许设置'),
        ('settingsN', '禁用设置')
    ], initial='settingsY')
    hideNetworkSetting = forms.BooleanField(initial=False, required=False)
    defaultViewStyle = forms.ChoiceField(label="默认显示方式", choices=[
        ('adaptive', '适应窗口'),
        ('original', '原始尺寸')
    ], initial='adaptive')
    removeSetupServerTip = forms.BooleanField(initial=True, required=False)
    silentInstallOnDoubleClick = forms.BooleanField(initial=False, required=False)
    silentAgentMode = forms.BooleanField(
        label="隐藏主窗口并静默运行",
        initial=False,
        required=False,
    )
    copyIdPasswordButton = forms.BooleanField(initial=False, required=False)
    manualTemporaryPassword = forms.BooleanField(initial=False, required=False)
    showStartOnBootCheckbox = forms.BooleanField(initial=False, required=False)
    incomingCompactMode = forms.BooleanField(initial=False, required=False)
    incomingContentWidth = forms.IntegerField(
        label="仅被控内容宽度",
        initial=220,
        required=False,
        min_value=180,
        max_value=640,
        widget=forms.NumberInput(attrs={'min': 180, 'max': 640, 'step': 1})
    )
    incomingContentHeight = forms.IntegerField(
        label="仅被控内容高度",
        initial=300,
        required=False,
        min_value=220,
        max_value=840,
        widget=forms.NumberInput(attrs={'min': 220, 'max': 840, 'step': 1})
    )
    androidappid = forms.CharField(
        label="自定义 Android App ID", required=False, validators=[ANDROID_APP_ID]
    )

    #Custom Server
    serverIP = forms.CharField(
        label="ID 服务器（hbbs）",
        required=False,
        validators=[SAFE_SCRIPT_VALUE],
        widget=forms.TextInput(
            attrs={
                "placeholder": "hbbs.example.com 或 hbbs.example.com:21116",
                "autocomplete": "off",
            }
        ),
    )
    relayServer = forms.CharField(
        label="固定中继服务器（hbbr）",
        required=False,
        validators=[SAFE_SCRIPT_VALUE, SINGLE_RELAY_SERVER],
        widget=forms.TextInput(
            attrs={
                "placeholder": "通常留空；例 hbbr.example.com:21117",
                "autocomplete": "off",
            }
        ),
    )
    apiServer = forms.CharField(
        label="API 服务器",
        required=False,
        validators=[SAFE_SCRIPT_VALUE, HTTP_URL],
        widget=forms.TextInput(
            attrs={
                "placeholder": "Pro：http://主机:21114 或 https://域名",
                "autocomplete": "off",
            }
        ),
    )
    key = forms.CharField(
        label="密钥（公钥 Key）",
        required=False,
        validators=[SAFE_SCRIPT_VALUE],
        widget=forms.TextInput(
            attrs={
                "placeholder": "id_ed25519.pub 文件内容",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        ),
    )
    urlLink = forms.CharField(
        label="站内链接地址", required=False, validators=[SAFE_SCRIPT_VALUE, HTTP_URL]
    )
    downloadLink = forms.CharField(
        label="更新下载地址", required=False, validators=[SAFE_SCRIPT_VALUE, HTTP_URL]
    )
    compname = forms.CharField(label="公司名称", required=False, validators=[SAFE_COMPANY_VALUE])

    #Visual
    iconfile = forms.FileField(label="自定义应用图标（PNG）", required=False, widget=forms.FileInput(attrs={'accept': 'image/png'}))
    logofile = forms.FileField(label="自定义应用 Logo（PNG）", required=False, widget=forms.FileInput(attrs={'accept': 'image/png'}))
    privacyfile = forms.FileField(label="自定义隐私屏幕（PNG）", required=False, widget=forms.FileInput(attrs={'accept': 'image/png'}))
    iconbase64 = forms.CharField(required=False)
    logobase64 = forms.CharField(required=False)
    privacybase64 = forms.CharField(required=False)
    theme = forms.ChoiceField(choices=[
        ('light', '浅色'),
        ('dark', '深色'),
        ('system', '跟随系统')
    ], initial='system')
    themeDorO = forms.ChoiceField(choices=[('default', '默认'),('override', '强制覆盖')], initial='default')

    #Security
    passApproveMode = forms.ChoiceField(choices=[('password','通过密码接受连接'),('click','通过点击接受连接'),('password-click','密码和点击均可')],initial='password-click')
    permanentPassword = forms.CharField(widget=forms.PasswordInput(), required=False)
    #runasadmin = forms.ChoiceField(choices=[('false','No'),('true','Yes')], initial='false')
    denyLan = forms.BooleanField(initial=False, required=False)
    enableDirectIP = forms.BooleanField(initial=False, required=False)
    #ipWhitelist = forms.BooleanField(initial=False, required=False)
    autoClose = forms.BooleanField(initial=False, required=False)

    #Permissions
    permissionsDorO = forms.ChoiceField(choices=[('default', '默认'),('override', '强制覆盖')], initial='default')
    permissionsType = forms.ChoiceField(choices=[('custom', '自定义'),('full', '完全访问'),('view','仅屏幕共享')], initial='custom')
    enableKeyboard =  forms.BooleanField(initial=True, required=False)
    enableClipboard = forms.BooleanField(initial=True, required=False)
    enableFileCopyPaste = forms.BooleanField(initial=True, required=False)
    enableFileTransfer = forms.BooleanField(initial=True, required=False)
    forceDisableFileTransfer = forms.BooleanField(initial=False, required=False)
    enableAudio = forms.BooleanField(initial=True, required=False)
    enableTCP = forms.BooleanField(initial=True, required=False)
    enableRemoteRestart = forms.BooleanField(initial=True, required=False)
    enableRecording = forms.BooleanField(initial=True, required=False)
    enableBlockingInput = forms.BooleanField(initial=True, required=False)
    enableRemoteModi = forms.BooleanField(initial=True, required=False)
    hidecm = forms.BooleanField(
        label="启用隐藏连接窗口功能",
        initial=False,
        required=False,
    )
    hidecmDefaultEnabled = forms.BooleanField(
        label="构建后默认开启隐藏连接窗口",
        initial=False,
        required=False,
    )
    enablePrinter = forms.BooleanField(initial=True, required=False)
    enableCamera = forms.BooleanField(initial=True, required=False)
    enableTerminal = forms.BooleanField(initial=True, required=False)

    #Other
    hideTray = forms.BooleanField(initial=False, required=False)
    removeWallpaper = forms.BooleanField(initial=False, required=False)

    defaultManual = forms.CharField(widget=forms.Textarea, required=False)
    overrideManual = forms.CharField(widget=forms.Textarea, required=False)

    #custom added features
    cycleMonitor = forms.BooleanField(initial=False, required=False)
    xOffline = forms.BooleanField(initial=False, required=False)
    removeNewVersionNotif = forms.BooleanField(initial=False, required=False)
    hideSettingsMenu = forms.BooleanField(initial=False, required=False)
    removeRecentSessions = forms.BooleanField(initial=False, required=False)

    # White-label / enterprise extras
    defaultStartOnBoot = forms.BooleanField(
        label="默认开启开机自启",
        initial=False,
        required=False,
        help_text="写入客户端设置，安装后默认勾选并启用开机自启。",
    )
    sloganText = forms.CharField(
        label="关于页 Slogan",
        required=False,
        max_length=80,
        validators=[SAFE_SCRIPT_VALUE],
        widget=forms.TextInput(
            attrs={"placeholder": "例如：企业内部远程协助客户端", "autocomplete": "off"}
        ),
    )
    macosBundleId = forms.CharField(
        label="macOS Bundle ID",
        required=False,
        max_length=120,
        validators=[SAFE_SCRIPT_VALUE],
        widget=forms.TextInput(
            attrs={
                "placeholder": "留空则自动 com.rdgen.{配置名}",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        ),
    )
    iosBundleId = forms.CharField(
        label="iOS Bundle ID",
        required=False,
        max_length=120,
        validators=[ANDROID_APP_ID],
        widget=forms.TextInput(
            attrs={
                "placeholder": "留空则自动 com.rdgen.{配置名}；重签时常需改成你的 ID",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        ),
    )
    defaultImageQuality = forms.ChoiceField(
        label="默认画质",
        required=False,
        choices=[
            ("", "不强制（跟随客户端）"),
            ("best", "最佳"),
            ("balanced", "均衡"),
            ("low", "流畅优先"),
        ],
        initial="",
    )
    defaultCodec = forms.ChoiceField(
        label="默认编码",
        required=False,
        choices=[
            ("", "不强制（自动）"),
            ("auto", "自动"),
            ("vp9", "VP9"),
            ("av1", "AV1"),
            ("h264", "H264"),
        ],
        initial="",
    )
    preferWebsocket = forms.BooleanField(
        label="默认优先 WebSocket 中继",
        initial=False,
        required=False,
    )
    sessionIdleMinutes = forms.IntegerField(
        label="会话空闲超时（分钟）",
        required=False,
        min_value=1,
        max_value=1440,
        widget=forms.NumberInput(attrs={"min": 1, "max": 1440, "placeholder": "留空不限制"}),
    )
    allowIdPrefixes = forms.CharField(
        label="仅允许连接的 ID 前缀",
        required=False,
        max_length=200,
        validators=[SAFE_SCRIPT_VALUE],
        widget=forms.TextInput(
            attrs={
                "placeholder": "逗号分隔，例如 12,34（写入 whitelist）",
                "autocomplete": "off",
            }
        ),
    )
    msiDesktopShortcut = forms.ChoiceField(
        label="安装时桌面图标",
        required=False,
        choices=[
            ("default", "默认勾选"),
            ("off", "默认不勾选"),
        ],
        initial="default",
    )
    msiStartMenuShortcut = forms.ChoiceField(
        label="安装时开始菜单",
        required=False,
        choices=[
            ("default", "默认勾选"),
            ("off", "默认不勾选"),
        ],
        initial="default",
    )
    msiInstallPrinter = forms.ChoiceField(
        label="安装时打印机驱动",
        required=False,
        choices=[
            ("off", "默认不勾选"),
            ("default", "默认勾选"),
        ],
        initial="off",
    )

    def clean_defaultManual(self):
        value = self.cleaned_data.get('defaultManual', '')
        parse_manual_settings(value)
        return value

    def clean_overrideManual(self):
        value = self.cleaned_data.get('overrideManual', '')
        parse_manual_settings(value)
        return value

    def clean(self):
        cleaned = super().clean()
        platform = cleaned.get('platform')
        version = cleaned.get('version')
        manual_hide_tray_values = {}
        normalized_manual_settings = {}
        manual_hide_tray_invalid = False
        for field in ('defaultManual', 'overrideManual'):
            value, normalized = extract_manual_setting(
                cleaned.get(field),
                'hide-tray',
            )
            normalized_manual_settings[field] = normalized
            if value is None:
                continue
            if value not in {'Y', 'N'}:
                self.add_error(
                    field,
                    'hide-tray 仅支持 Y 或 N，请使用“隐藏系统托盘图标”开关。',
                )
                manual_hide_tray_invalid = True
                continue
            manual_hide_tray_values[field] = value
        manual_hide_tray_source = None
        if manual_hide_tray_values and not manual_hide_tray_invalid:
            for field, normalized in normalized_manual_settings.items():
                cleaned[field] = normalized
            manual_hide_tray_source = (
                'overrideManual'
                if 'overrideManual' in manual_hide_tray_values
                else 'defaultManual'
            )
            cleaned['hideTray'] = (
                manual_hide_tray_values[manual_hide_tray_source] == 'Y'
            )

        # Preserve fixed relays stored by older exported configurations in the
        # free-form advanced settings. The dedicated field is authoritative for
        # new submissions, while a valid legacy value is promoted when that
        # field is empty. Override settings take precedence over defaults.
        manual_relay_values = {}
        normalized_relay_settings = {}
        manual_relay_invalid = False
        for field in ('defaultManual', 'overrideManual'):
            value, normalized = extract_manual_setting(
                cleaned.get(field),
                'relay-server',
            )
            normalized_relay_settings[field] = normalized
            if value is None:
                continue
            try:
                manual_relay_values[field] = self.fields['relayServer'].clean(value)
            except forms.ValidationError as errors:
                self.add_error(field, errors)
                manual_relay_invalid = True
        if manual_relay_values and not manual_relay_invalid:
            for field, normalized in normalized_relay_settings.items():
                cleaned[field] = normalized
            source = (
                'overrideManual'
                if 'overrideManual' in manual_relay_values
                else 'defaultManual'
            )
            if not cleaned.get('relayServer'):
                cleaned['relayServer'] = manual_relay_values[source]

        smart_multi_relay = bool(cleaned.get('smartMultiRelay'))
        if smart_multi_relay:
            if version != '1.4.9':
                self.add_error(
                    'smartMultiRelay',
                    '智能多中继仅支持 RustDesk 1.4.9；nightly 和其他版本暂不支持。',
                )
            if platform not in SMART_MULTI_RELAY_PLATFORMS:
                self.add_error(
                    'smartMultiRelay',
                    '智能多中继仅支持 Windows 64 位、Windows 32 位、Linux 和 Android；macOS 暂不支持。',
                )
            if cleaned.get('relayServer'):
                conflict_message = '智能多中继不能与固定中继服务器同时启用。'
                self.add_error('smartMultiRelay', conflict_message)
                self.add_error('relayServer', conflict_message)
            if not is_smart_rendezvous_domain(cleaned.get('serverIP')):
                self.add_error(
                    'serverIP',
                    '智能多中继要求使用可由受信任证书覆盖的 hbbs 域名，可附带端口；不能使用 IP 地址。',
                )
            if not is_https_api_server(cleaned.get('apiServer')):
                self.add_error(
                    'apiServer',
                    '智能多中继要求显式填写以 https:// 开头的 API 地址，以启用严格 WSS。',
                )
            if not cleaned.get('key'):
                self.add_error(
                    'key',
                    '智能多中继要求填写服务器公钥，用于验证服务器签名的中继选择。',
                )

        silent_agent_mode = bool(cleaned.get('silentAgentMode'))
        if silent_agent_mode:
            if platform not in {'windows', 'windows-x86'}:
                self.add_error(
                    'silentAgentMode',
                    '隐藏主窗口的静默代理模式仅支持 Windows 64 位和 Windows 32 位。',
                )
            if version != '1.4.9':
                self.add_error(
                    'silentAgentMode',
                    '隐藏主窗口的静默代理模式当前仅支持 RustDesk 1.4.9。',
                )
            if cleaned.get('installation') != 'installationY':
                self.add_error(
                    'installation',
                    '静默代理模式必须允许安装，后台接入由已安装的 Windows 服务提供。',
                )
            if cleaned.get('direction') == 'outgoing':
                self.add_error(
                    'direction',
                    '静默代理模式不能用于“仅允许主控”，请选择“仅允许被控”或“双向连接”。',
                )

            # Silent-agent builds have no usable main-window controls. Keep
            # unattended access deterministic and suppress the remaining user
            # surfaces through the already-audited capabilities.
            cleaned['silentInstallOnDoubleClick'] = True
            cleaned['hideTray'] = True
            cleaned['hidecm'] = True
            cleaned['hidecmDefaultEnabled'] = True
            cleaned['passApproveMode'] = 'password'

        legacy_hidecm_submission = (
            cleaned.get('hidecm')
            and 'hidecmDefaultEnabled' not in self.data
            and 'formSchemaVersion' not in self.data
        )
        if legacy_hidecm_submission:
            cleaned['hidecmDefaultEnabled'] = True

        if platform == 'linux' and cleaned.get('beijingCustom'):
            if version not in BEIJING_LINUX_VERSIONS:
                self.add_error(
                    'beijingCustom',
                    '北京 Linux 定制仅支持已验证的 RustDesk 1.4.7、1.4.8 和 1.4.9。',
                )
            if len(cleaned.get('exename') or '') < 2:
                self.add_error(
                    'exename',
                    '北京 Linux 定制的包名称至少需要 2 个字符。',
                )
            for field in ('appname', 'compname', 'urlLink'):
                value = cleaned.get(field) or ''
                if '%' in value:
                    self.add_error(
                        field,
                        '北京 Linux 定制的 RPM 包元数据不支持百分号。',
                    )
            if any(character.isspace() for character in (cleaned.get('urlLink') or '')):
                self.add_error(
                    'urlLink',
                    '北京 Linux 定制的 RPM 主页地址不能包含空白字符。',
                )

        version_requirements = {
            'incomingCompactMode': ((1, 4, 2), '仅被控紧凑布局'),
            'hideNetworkSetting': ((1, 4, 4), '隐藏网络设置'),
            'hideSettingsMenu': ((1, 4, 4), '隐藏主界面设置菜单'),
            'forceDisableFileTransfer': ((1, 4, 5), '从源码强制禁用文件传输'),
        }
        for field, (minimum, label) in version_requirements.items():
            if cleaned.get(field) and not version_at_least(version, minimum):
                minimum_text = '.'.join(str(part) for part in minimum)
                self.add_error(
                    field,
                    f'{label}要求 RustDesk {minimum_text} 或更高版本。',
                )

        if cleaned.get('hidecmDefaultEnabled') and not cleaned.get('hidecm'):
            self.add_error(
                'hidecmDefaultEnabled',
                '构建后默认隐藏前，必须先启用隐藏连接窗口功能。',
            )
        if cleaned.get('hidecmDefaultEnabled') and not (
            cleaned.get('permanentPassword') or ''
        ).strip():
            self.add_error(
                'permanentPassword',
                '构建后默认隐藏连接窗口时必须设置固定密码。',
            )
        if (
            cleaned.get('hidecm')
            and cleaned.get('settings') == 'settingsN'
            and not legacy_hidecm_submission
        ):
            self.add_error(
                'settings',
                '启用隐藏连接窗口功能时必须保留设置入口。',
            )

        if platform != 'windows' and (
            cleaned.get('privacyfile') or cleaned.get('privacybase64')
        ):
            self.add_error('privacyfile', '自定义隐私屏幕目前仅支持 Windows 64 位。')

        if platform in {'windows-x86', 'android'} and (
            cleaned.get('logofile') or cleaned.get('logobase64')
        ):
            self.add_error('logofile', 'Windows 32 位和 Android 暂不支持自定义 Logo。')

        if platform == 'windows-x86':
            unsupported = {
                'cycleMonitor': '显示器切换按钮',
                'xOffline': '离线 X 标记',
                'copyIdPasswordButton': 'ID/密码复制按钮',
                'manualTemporaryPassword': '手动临时密码',
                'showStartOnBootCheckbox': '开机自启选项',
                'incomingCompactMode': '仅被控紧凑布局',
            }
            for field, label in unsupported.items():
                if cleaned.get(field):
                    self.add_error(field, f'Windows 32 位不支持{label}。')

        if platform == 'android':
            if cleaned.get('hideSettingsMenu'):
                self.add_error('hideSettingsMenu', 'Android 不支持隐藏主界面设置菜单。')
            if cleaned.get('hideTray'):
                self.add_error(
                    manual_hide_tray_source or 'hideTray',
                    'Android 不支持系统托盘图标。',
                )

        if platform == 'ios':
            unsupported = {
                'cycleMonitor': '显示器切换按钮',
                'showStartOnBootCheckbox': '开机自启选项',
                'defaultStartOnBoot': '默认开机自启',
                'silentInstallOnDoubleClick': '双击静默安装',
                'silentAgentMode': '静默被控模式',
                'incomingCompactMode': '仅被控紧凑布局',
                'hideTray': '系统托盘图标',
                'copyIdPasswordButton': 'ID/密码复制按钮',
            }
            for field, label in unsupported.items():
                if cleaned.get(field):
                    self.add_error(field, f'iOS 不支持{label}。')
            if cleaned.get('logofile') or cleaned.get('logobase64'):
                self.add_error('logofile', 'iOS 暂不支持自定义 Logo（请用应用图标）。')

        if (
            platform == 'linux'
            and not cleaned.get('beijingCustom')
            and cleaned.get('hideTray')
        ):
            self.add_error(
                manual_hide_tray_source or 'hideTray',
                '标准 Linux 构建暂不支持系统托盘图标。',
            )

        return cleaned

    def clean_iconfile(self):
        image = self.cleaned_data['iconfile']
        if image:
            try:
                # Open the image using Pillow
                img = Image.open(image)

                # Check if the image is a PNG (optional, but good practice)
                if img.format != 'PNG':
                    raise forms.ValidationError("仅允许上传 PNG 图片。")

                # Get image dimensions
                width, height = img.size

                # Check for square dimensions
                if width != height:
                    raise forms.ValidationError("自定义应用图标必须是正方形。")
                
                return image
            except OSError:  # Handle cases where the uploaded file is not a valid image
                raise forms.ValidationError("图标文件无效。")
            except Exception as e: # Catch any other image processing errors
                raise forms.ValidationError(f"处理图标时出错：{e}")
