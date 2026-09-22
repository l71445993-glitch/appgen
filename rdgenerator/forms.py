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
from .models import ActivationCode, UserEntitlement, get_user_entitlement
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
            }
        )
        if not actor or not actor.is_superuser:
            self.fields.pop("is_staff", None)

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            entitlement, _created = UserEntitlement.objects.get_or_create(user=user)
            _apply_entitlement_fields(entitlement, self.cleaned_data)
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
    platform = forms.ChoiceField(choices=[('windows','Windows 64 位'),('windows-x86','Windows 32 位'),('linux','Linux'),('android','Android'),('macos','macOS')], initial='windows')
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
    serverIP = forms.CharField(label="ID 服务器", required=False, validators=[SAFE_SCRIPT_VALUE])
    relayServer = forms.CharField(
        label="固定中继服务器",
        required=False,
        validators=[SAFE_SCRIPT_VALUE, SINGLE_RELAY_SERVER],
    )
    apiServer = forms.CharField(
        label="API 服务", required=False, validators=[SAFE_SCRIPT_VALUE, HTTP_URL]
    )
    key = forms.CharField(label="密钥", required=False, validators=[SAFE_SCRIPT_VALUE])
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
