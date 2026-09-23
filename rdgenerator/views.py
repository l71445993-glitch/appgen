import io
import hashlib
import hmac
import math
import mimetypes
import tempfile
from datetime import timedelta
from ipaddress import ip_address
from pathlib import Path
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
import os
import secrets
import re
import requests
import base64
import json
import uuid
import pyzipper
from urllib.parse import urlencode, urlsplit
from django.conf import settings as _settings
from .build_config import build_config_snapshot
from .build_notify import maybe_notify_build_success
from .forms import GenerateForm
from .models import (
    create_github_run_with_reservation,
    GeneratedArtifact,
    GenerationQuotaExceeded,
    GithubRun,
    UserEntitlement,
    get_user_entitlement,
    mark_artifact_uploaded,
    release_generation_reservation,
)
from PIL import Image


ZIP_DOWNLOAD_MAX_AGE = 6 * 60 * 60
ZIP_DOWNLOAD_SALT = "rdgenerator.get_zip"
STATUS_UPDATE_MAX_AGE = 24 * 60 * 60
STATUS_UPDATE_SALT = "rdgenerator.update_status"
DISPATCH_FAILURE_SALT = "rdgenerator.dispatch_failure"
CALLBACK_TOKEN_MAX_AGE = timedelta(hours=24)
TERMINAL_RUN_STATUSES = {
    "success",
    "failure",
    "cancelled",
    "timed_out",
    "skipped",
    "action_required",
    "artifact_incomplete",
    "dispatch_failed",
}
FAILED_TERMINAL_RUN_STATUSES = TERMINAL_RUN_STATUSES - {"success"}
ARTIFACT_PENDING_STATUS = "artifacts_pending"
ARTIFACT_INCOMPLETE_STATUS = "artifact_incomplete"
# Typical GitHub Actions wall time used only for soft progress estimation.
EXPECTED_BUILD_SECONDS = 40 * 60
WAITING_STATUS_LABELS = {
    "queued": "排队中",
    "starting": "准备中",
    "in_progress": "构建中",
    "artifacts_pending": "正在上传安装包",
    "success": "构建成功",
    "failure": "构建失败",
    "artifact_incomplete": "文件不完整",
    "dispatch_failed": "提交失败",
    "cancelled": "已取消",
    "timed_out": "已超时",
    "skipped": "已跳过",
    "action_required": "需要处理",
}
VALID_ARTIFACT_SUFFIXES = (
    ".exe",
    ".msi",
    ".apk",
    ".deb",
    ".rpm",
    ".appimage",
    ".flatpak",
    ".dmg",
    ".ipa",
    ".pkg.tar.zst",
)


def _waiting_status_label(status):
    raw = (status or "").strip()
    key = raw.lower()
    if key in WAITING_STATUS_LABELS:
        return WAITING_STATUS_LABELS[key]
    if "start" in key:
        return "正在启动构建"
    return raw or "处理中"


def _waiting_progress_percent(run, status=None):
    """Estimate progress from status + elapsed time. Never claims 100% until done."""
    status = (status or getattr(run, "status", "") or "").strip().lower()
    if status == "success":
        return 100
    if status in FAILED_TERMINAL_RUN_STATUSES:
        return 100

    created = getattr(run, "created_at", None)
    if created:
        if timezone.is_naive(created):
            created = timezone.make_aware(created, timezone.get_current_timezone())
        elapsed = max((timezone.now() - created).total_seconds(), 0.0)
    else:
        elapsed = 0.0
    # Asymptotic time factor so long builds keep creeping without hitting the cap.
    time_factor = 1.0 - math.exp(-elapsed / float(EXPECTED_BUILD_SECONDS))

    if status in {"", "queued", "starting"} or "start" in status:
        low, high = 4, 18
    elif status == ARTIFACT_PENDING_STATUS:
        low, high = 82, 96
    elif status == "in_progress":
        low, high = 18, 80
    else:
        low, high = 12, 70
    return int(round(low + (high - low) * time_factor))


def _waiting_page_context(run, *, filename, platform, log_url, status=None):
    current = status if status is not None else (run.status or "")
    created = getattr(run, "created_at", None)
    created_ms = int(created.timestamp() * 1000) if created else 0
    return {
        "filename": filename,
        "uuid": str(run.uuid),
        "status": current,
        "status_label": _waiting_status_label(current),
        "progress_percent": _waiting_progress_percent(run, current),
        "created_at_ms": created_ms,
        "platform": platform,
        "log_url": log_url,
        "download_access": run.download_access,
        "download_ttl_hours": run.download_ttl_hours,
    }


def _default_api_server(server):
    value = (server or "").strip()
    authority = value.split("://", 1)[-1].split("/", 1)[0]
    host = None
    if not authority.startswith("[") and authority.count(":") > 1:
        try:
            address = ip_address(authority)
        except ValueError:
            pass
        else:
            if address.version == 6:
                host = str(address)
    try:
        if not host:
            parsed = urlsplit(value if "://" in value else f"//{value}")
            host = parsed.hostname
    except ValueError:
        pass
    if not host:
        if authority.startswith("[") and "]" in authority:
            host = authority[1 : authority.index("]")]
        elif authority.count(":") == 1:
            host = authority.rsplit(":", 1)[0]
        else:
            host = authority
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:21114"


def _canonical_run_uuid(value):
    try:
        canonical = str(uuid.UUID(value))
    except (AttributeError, TypeError, ValueError):
        raise Http404("Build not found")
    if value != canonical:
        raise Http404("Build not found")
    return canonical


def _user_run_or_404(request, run_uuid):
    run_uuid = _canonical_run_uuid(run_uuid)
    return get_object_or_404(GithubRun, uuid=run_uuid, owner=request.user)


def _safe_output_filename(value):
    if (
        not value
        or len(value) > 255
        or value in {".", ".."}
        or os.path.basename(value) != value
        or any(char in value for char in ('/', '\\', '"', ';', '\r', '\n'))
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise Http404("Generated file not found")
    return value


def _callback_token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def download_token_for_run(run_uuid):
    """Return a deterministic per-run share token without storing plaintext."""
    return hmac.new(
        str(_settings.SECRET_KEY).encode("utf-8"),
        str(run_uuid).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _valid_artifact_filename(filename, platform=None):
    platform_suffixes = {
        "windows": (".exe", ".msi"),
        "windows-x86": (".exe",),
        "android": (".apk",),
        "macos": (".dmg",),
        "ios": (".ipa",),
        "linux": (".deb", ".rpm", ".appimage", ".flatpak", ".pkg.tar.zst"),
    }
    allowed_suffixes = platform_suffixes.get(platform, VALID_ARTIFACT_SUFFIXES)
    return bool(
        filename
        and not filename.startswith(".upload-")
        and filename.lower().endswith(allowed_suffixes)
    )


def _windows_artifact_names(run):
    if run.platform != "windows" or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]*",
        run.artifact_stem or "",
    ):
        return ()
    return (f"{run.artifact_stem}.exe", f"{run.artifact_stem}.msi")


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as artifact_file:
        for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_token(request):
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if separator and scheme.lower() == "bearer":
        return token.strip()
    return ""


def _machine_run(request, raw_uuid):
    try:
        run_uuid = _canonical_run_uuid(raw_uuid)
    except Http404:
        return None, HttpResponse("Build not found", status=404)

    token = _request_token(request)
    if not token:
        return None, HttpResponse("Unauthorized", status=401)

    try:
        run = GithubRun.objects.get(uuid=run_uuid)
    except GithubRun.DoesNotExist:
        return None, HttpResponse("Build not found", status=404)
    if timezone.now() - run.created_at > CALLBACK_TOKEN_MAX_AGE:
        return None, HttpResponse("Unauthorized", status=401)

    supplied_hash = _callback_token_hash(token)
    if not run.callback_token_hash or not secrets.compare_digest(
        supplied_hash,
        run.callback_token_hash,
    ):
        return None, HttpResponse("Unauthorized", status=401)
    return run, None


def _status_run(request, raw_uuid, requested_status):
    if _request_token(request):
        return _machine_run(request, raw_uuid)
    try:
        run_uuid = _canonical_run_uuid(raw_uuid)
    except Http404:
        return None, HttpResponse("Build not found", status=404)
    signature = request.GET.get("signature", "")
    try:
        signed = signing.loads(
            signature,
            salt=STATUS_UPDATE_SALT,
            max_age=STATUS_UPDATE_MAX_AGE,
        )
    except (BadSignature, SignatureExpired):
        if requested_status not in FAILED_TERMINAL_RUN_STATUSES:
            return None, HttpResponse("Unauthorized", status=401)
        try:
            signed = signing.loads(
                signature,
                salt=DISPATCH_FAILURE_SALT,
                max_age=STATUS_UPDATE_MAX_AGE,
            )
        except (BadSignature, SignatureExpired):
            return None, HttpResponse("Unauthorized", status=401)
    if not isinstance(signed, dict) or signed.get("uuid") != run_uuid:
        return None, HttpResponse("Unauthorized", status=401)
    try:
        return GithubRun.objects.get(uuid=run_uuid), None
    except GithubRun.DoesNotExist:
        return None, HttpResponse("Build not found", status=404)


def _shared_api_authorized(request):
    token = _request_token(request)
    expected = _settings.API_SHARED_SECRET
    return bool(token and expected and secrets.compare_digest(token, expected))


def _generated_file_or_404(run_uuid, filename):
    if filename.startswith(".upload-"):
        raise Http404("Generated file not found")
    output_dir = (Path("exe") / run_uuid).resolve()
    file_path = (output_dir / filename).resolve()
    try:
        file_path.relative_to(output_dir)
    except ValueError:
        raise Http404("Generated file not found")
    if not file_path.is_file():
        raise Http404("Generated file not found")
    return file_path


def _committed_artifact_file_or_404(run, filename):
    artifact = GeneratedArtifact.objects.filter(
        run=run,
        filename=filename,
    ).first()
    if artifact is None:
        raise Http404("Generated file not found")
    file_path = _generated_file_or_404(run.uuid, filename)
    if file_path.stat().st_size != artifact.size:
        raise Http404("Generated file not found")
    return file_path, artifact

def list_generated_files(run_uuid):
    output_dir = Path("exe") / run_uuid
    if not output_dir.is_dir():
        return []
    run = GithubRun.objects.filter(uuid=run_uuid).only("pk", "platform").first()
    has_receipt_contract = bool(
        run
        and (
            run.platform
            or GeneratedArtifact.objects.filter(run=run).exists()
        )
    )
    if has_receipt_contract:
        files = [
            artifact.filename
            for artifact in GeneratedArtifact.objects.filter(run=run)
            if (output_dir / artifact.filename).is_file()
            and (output_dir / artifact.filename).stat().st_size == artifact.size
        ]
    else:
        files = [
            path.name
            for path in output_dir.iterdir()
            if path.is_file() and not path.name.startswith(".upload-")
        ]
    android_order = ['-universal.apk', '-aarch64.apk', '-armv7.apk', '-x86_64.apk']
    return sorted(files, key=lambda name: (
        next((idx for idx, suffix in enumerate(android_order) if name.endswith(suffix)), len(android_order)),
        name.lower(),
    ))


def _download_links(run, files):
    """Build task-scoped links without exposing a token for login-only files."""
    expires_at = run.download_expires_at
    token = download_token_for_run(run.uuid) if run.download_token_hash else ""
    links = []
    for filename in files:
        params = {"filename": filename, "uuid": run.uuid}
        if run.download_access == "public" and token:
            params["token"] = token
        links.append(
            {
                "filename": filename,
                "url": f"/download?{urlencode(params)}",
                "requires_login": run.download_access != "public",
                "expires_at": expires_at,
            }
        )
    return links


def _delivery_context(run, files):
    return {
        "files": files,
        "download_links": _download_links(run, files),
        "download_access": run.download_access,
        "download_ttl_hours": run.download_ttl_hours,
        "download_expires_at": run.download_expires_at,
    }


def _entitlement_summary(user):
    """Build the ordinary-user entitlement shown on the generator page."""
    if not user.is_authenticated or user.is_staff or user.is_superuser:
        return None

    entitlement = get_user_entitlement(user)
    if entitlement.expiration_mode == UserEntitlement.EXPIRATION_COUNT:
        limit = entitlement.generation_limit
        remaining = entitlement.remaining_generations
        can_generate = entitlement.can_generate
        if limit is None:
            status = "unconfigured"
            status_label = "等待激活"
        elif can_generate:
            status = "active"
            status_label = "可生成"
        else:
            status = "exhausted"
            status_label = "已用尽"
        return {
            "mode": UserEntitlement.EXPIRATION_COUNT,
            "plan_label": "未开通会员" if limit is None else "次数会员",
            "status": status,
            "status_label": status_label,
            "can_generate": can_generate,
            "block_reason": (
                None
                if can_generate
                else "count_unconfigured" if limit is None else "count_exhausted"
            ),
            "submit_label": (
                "生成自定义客户端"
                if can_generate
                else "请先激活会员" if limit is None else "生成次数已用尽"
            ),
            "generation_limit": limit,
            "generation_limit_configured": limit is not None,
            "generations_used": entitlement.generations_used,
            "reserved_generations": entitlement.reserved_generations,
            "remaining_generations": remaining,
        }

    expires_at = entitlement.expires_at
    if expires_at is None:
        return {
            "mode": UserEntitlement.EXPIRATION_TIME,
            "plan_label": "永久会员",
            "status": "permanent",
            "status_label": "长期有效",
            "can_generate": True,
            "block_reason": None,
            "submit_label": "生成自定义客户端",
            "expires_at": None,
            "expires_at_display": None,
            "remaining_label": "长期有效",
        }

    now = timezone.now()
    local_expires_at = timezone.localtime(expires_at)
    expires_at_display = local_expires_at.strftime("%Y-%m-%d %H:%M")
    if now >= expires_at:
        return {
            "mode": UserEntitlement.EXPIRATION_TIME,
            "plan_label": "有效期会员",
            "status": "expired",
            "status_label": "已到期",
            "can_generate": False,
            "block_reason": "time_expired",
            "submit_label": "会员已到期",
            "expires_at": local_expires_at,
            "expires_at_display": expires_at_display,
            "remaining_label": "已到期",
        }

    remaining_seconds = (expires_at - now).total_seconds()
    remaining_days = math.ceil(remaining_seconds / timedelta(days=1).total_seconds())
    remaining_label = (
        "剩余不足 1 天"
        if remaining_seconds < timedelta(days=1).total_seconds()
        else f"剩余 {remaining_days} 天"
    )
    return {
        "mode": UserEntitlement.EXPIRATION_TIME,
        "plan_label": "有效期会员",
        "status": "active",
        "status_label": "有效",
        "can_generate": True,
        "block_reason": None,
        "submit_label": "生成自定义客户端",
        "expires_at": local_expires_at,
        "expires_at_display": expires_at_display,
        "remaining_days": remaining_days,
        "remaining_label": remaining_label,
    }


def _generator_context(request, form):
    return {
        "form": form,
        "entitlement_summary": _entitlement_summary(request.user),
    }

@login_required
def generator_view(request):
    if request.method == 'POST':
        form = GenerateForm(request.POST, request.FILES)
        if form.is_valid():
            user_secret = form.cleaned_data['sh_secret_field']
            if _settings.SH_SECRET and _settings.SH_SECRET == user_secret:
                selfhosted = True
            else:
                selfhosted = False
            platform = form.cleaned_data['platform']
            desktop_platforms = {'windows', 'windows-x86', 'linux', 'macos'}
            flutter_desktop_platforms = {'windows', 'linux', 'macos'}
            windows_platforms = {'windows', 'windows-x86'}
            version = form.cleaned_data['version']
            silentAgentMode = (
                form.cleaned_data['silentAgentMode']
                and platform in windows_platforms
                and version == '1.4.9'
            )
            smartMultiRelay = form.cleaned_data['smartMultiRelay']
            beijingCustom = form.cleaned_data['beijingCustom'] and platform == 'linux'
            linuxCustomAllowed = platform != 'linux' or beijingCustom or smartMultiRelay
            default_server = 'rs-ny.rustdesk.com'
            default_key = 'OeVuKk5nlHiXp+APNn0Y3pC1Iwpwn44JGqrQCsWqmBw='
            default_url_link = "https://rustdesk.com"
            default_download_link = "https://rustdesk.com/download"
            default_appname = "rustdesk"
            default_compname = "Purslane Tech Pte. Ltd."
            delayFix = form.cleaned_data['delayFix'] and linuxCustomAllowed
            cycleMonitor = form.cleaned_data['cycleMonitor'] and platform in flutter_desktop_platforms and linuxCustomAllowed
            xOffline = form.cleaned_data['xOffline'] and platform in (flutter_desktop_platforms | {'android'}) and linuxCustomAllowed
            hidecm = form.cleaned_data['hidecm'] and platform in desktop_platforms and linuxCustomAllowed
            hidecmDefaultEnabled = (
                form.cleaned_data['hidecmDefaultEnabled'] and hidecm
            )
            removeNewVersionNotif = form.cleaned_data['removeNewVersionNotif'] and linuxCustomAllowed
            hideSettingsMenu = form.cleaned_data['hideSettingsMenu'] and platform in desktop_platforms and linuxCustomAllowed
            removeRecentSessions = form.cleaned_data['removeRecentSessions'] and platform in desktop_platforms and linuxCustomAllowed
            server = form.cleaned_data['serverIP']
            relayServer = form.cleaned_data['relayServer']
            key = form.cleaned_data['key']
            apiServer = form.cleaned_data['apiServer']
            urlLink = form.cleaned_data['urlLink']
            downloadLink = form.cleaned_data['downloadLink']
            if not server:
                server = default_server
            if not key:
                key = default_key
            if not apiServer:
                apiServer = _default_api_server(server)
            if not urlLink:
                urlLink = default_url_link
            if not downloadLink:
                downloadLink = default_download_link
            direction = form.cleaned_data['direction']
            installation = form.cleaned_data['installation']
            settings = form.cleaned_data['settings']
            hideNetworkSetting = form.cleaned_data['hideNetworkSetting'] and platform in desktop_platforms and linuxCustomAllowed
            defaultViewStyle = form.cleaned_data['defaultViewStyle'] if linuxCustomAllowed else 'adaptive'
            removeSetupServerTip = form.cleaned_data['removeSetupServerTip'] and platform in desktop_platforms and linuxCustomAllowed
            silentInstallOnDoubleClick = form.cleaned_data['silentInstallOnDoubleClick'] and platform in windows_platforms
            copyIdPasswordButton = form.cleaned_data['copyIdPasswordButton'] and platform in flutter_desktop_platforms and linuxCustomAllowed
            manualTemporaryPassword = form.cleaned_data['manualTemporaryPassword'] and platform in flutter_desktop_platforms and linuxCustomAllowed
            showStartOnBootCheckbox = form.cleaned_data['showStartOnBootCheckbox'] and platform == 'windows'
            defaultStartOnBoot = (
                form.cleaned_data.get('defaultStartOnBoot')
                and platform in flutter_desktop_platforms
                and linuxCustomAllowed
            )
            if defaultStartOnBoot and platform == 'windows':
                showStartOnBootCheckbox = True
            sloganText = (form.cleaned_data.get('sloganText') or '').strip()
            macosBundleId = (form.cleaned_data.get('macosBundleId') or '').strip()
            iosBundleId = (form.cleaned_data.get('iosBundleId') or '').strip()
            defaultImageQuality = (form.cleaned_data.get('defaultImageQuality') or '').strip()
            defaultCodec = (form.cleaned_data.get('defaultCodec') or '').strip()
            preferWebsocket = bool(form.cleaned_data.get('preferWebsocket')) and linuxCustomAllowed
            sessionIdleMinutes = form.cleaned_data.get('sessionIdleMinutes')
            allowIdPrefixes = (form.cleaned_data.get('allowIdPrefixes') or '').strip()
            msiDesktopShortcut = form.cleaned_data.get('msiDesktopShortcut') or 'default'
            msiStartMenuShortcut = form.cleaned_data.get('msiStartMenuShortcut') or 'default'
            msiInstallPrinter = form.cleaned_data.get('msiInstallPrinter') or 'off'
            incomingCompactMode = (
                form.cleaned_data['incomingCompactMode']
                and direction == 'incoming'
                and platform in flutter_desktop_platforms
                and linuxCustomAllowed
            )
            incomingContentWidth = form.cleaned_data.get('incomingContentWidth') or 220
            incomingContentHeight = form.cleaned_data.get('incomingContentHeight') or 300
            appname = form.cleaned_data['appname']
            if not appname:
                appname = default_appname
            filename = form.cleaned_data['exename']
            compname = form.cleaned_data['compname']
            if not compname:
                compname = default_compname
            androidappid = form.cleaned_data['androidappid']
            if not androidappid:
                androidappid = "com.carriez.flutter_hbb"
            compname = compname.replace("&", "\\&")
            permPass = form.cleaned_data['permanentPassword']
            theme = form.cleaned_data['theme']
            themeDorO = form.cleaned_data['themeDorO']
            #runasadmin = form.cleaned_data['runasadmin']
            passApproveMode = form.cleaned_data['passApproveMode']
            denyLan = form.cleaned_data['denyLan']
            enableDirectIP = form.cleaned_data['enableDirectIP']
            #ipWhitelist = form.cleaned_data['ipWhitelist']
            autoClose = form.cleaned_data['autoClose']
            permissionsDorO = form.cleaned_data['permissionsDorO']
            permissionsType = form.cleaned_data['permissionsType']
            enableKeyboard = form.cleaned_data['enableKeyboard']
            enableClipboard = form.cleaned_data['enableClipboard']
            enableFileCopyPaste = form.cleaned_data['enableFileCopyPaste']
            enableFileTransfer = form.cleaned_data['enableFileTransfer']
            forceDisableFileTransfer = form.cleaned_data['forceDisableFileTransfer'] and linuxCustomAllowed
            enableAudio = form.cleaned_data['enableAudio']
            enableTCP = form.cleaned_data['enableTCP']
            enableRemoteRestart = form.cleaned_data['enableRemoteRestart']
            enableRecording = form.cleaned_data['enableRecording']
            enableBlockingInput = form.cleaned_data['enableBlockingInput']
            enableRemoteModi = form.cleaned_data['enableRemoteModi']
            hideTray = form.cleaned_data['hideTray'] and platform in desktop_platforms and linuxCustomAllowed
            removeWallpaper = form.cleaned_data['removeWallpaper']
            defaultManual = form.cleaned_data['defaultManual']
            overrideManual = form.cleaned_data['overrideManual']
            enablePrinter = form.cleaned_data['enablePrinter']
            enableCamera = form.cleaned_data['enableCamera']
            enableTerminal = form.cleaned_data['enableTerminal']

            if all(char.isascii() for char in filename):
                filename = re.sub(r'[^\w\s-]', '_', filename).strip()
                filename = filename.replace(" ","_")
            else:
                filename = "rustdesk"
            if not linuxCustomAllowed:
                server = default_server
                relayServer = ""
                key = default_key
                apiServer = _default_api_server(default_server)
                urlLink = default_url_link
                downloadLink = default_download_link
                direction = "both"
                appname = default_appname
                filename = default_appname
                compname = default_compname
            myuuid = str(uuid.uuid4())
            protocol = _settings.PROTOCOL
            host = request.get_host()
            full_url = f"{protocol}://{host}"
            try:
                iconfile = form.cleaned_data.get('iconfile')
                if not iconfile:
                    iconfile = form.cleaned_data.get('iconbase64')
                iconlink_url, iconlink_uuid, iconlink_file = save_png(iconfile,myuuid,full_url,"icon.png")
            except:
                print("failed to get icon, using default")
                iconlink_url = "false"
                iconlink_uuid = "false"
                iconlink_file = "false"
            try:
                logofile = form.cleaned_data.get('logofile')
                if not logofile:
                    logofile = form.cleaned_data.get('logobase64')
                logolink_url, logolink_uuid, logolink_file = save_png(logofile,myuuid,full_url,"logo.png")
            except:
                print("failed to get logo")
                logolink_url = "false"
                logolink_uuid = "false"
                logolink_file = "false"
            try:
                privacyfile = form.cleaned_data.get('privacyfile')
                if not privacyfile:
                    privacyfile = form.cleaned_data.get('privacybase64')
                privacylink_url, privacylink_uuid, privacylink_file = save_png(privacyfile,myuuid,full_url,"privacy.png")
            except:
                print("failed to get logo")
                privacylink_url = "false"
                privacylink_uuid = "false"
                privacylink_file = "false"
            if not linuxCustomAllowed:
                iconlink_url = "false"
                iconlink_uuid = "false"
                iconlink_file = "false"
                logolink_url = "false"
                logolink_uuid = "false"
                logolink_file = "false"
                privacylink_url = "false"
                privacylink_uuid = "false"
                privacylink_file = "false"

            callback_token = secrets.token_urlsafe(32)

            ###create the custom.txt json here and send in as inputs below
            decodedCustom = {}
            if direction != "both":
                decodedCustom['conn-type'] = direction
            if installation == "installationN":
                decodedCustom['disable-installation'] = 'Y'
            if settings == "settingsN":
                decodedCustom['disable-settings'] = 'Y'
            if hideNetworkSetting:
                decodedCustom['hide-network-setting'] = 'Y'
            if appname.upper() != "RUSTDESK":
                decodedCustom['app-name'] = appname
            decodedCustom['custom-rendezvous-server'] = server
            decodedCustom['api-server'] = apiServer
            decodedCustom['key'] = key
            decodedCustom['override-settings'] = {}
            decodedCustom['default-settings'] = {}
            if platform in desktop_platforms and linuxCustomAllowed:
                decodedCustom['default-settings']['view-style'] = defaultViewStyle
            if permPass != "":
                decodedCustom['password'] = permPass
            if theme != "system":
                if themeDorO == "default":
                    if platform == "windows-x86":
                        decodedCustom['default-settings']['allow-darktheme'] = 'Y' if theme == "dark" else 'N'
                    else:
                        decodedCustom['default-settings']['theme'] = theme
                elif themeDorO == "override":
                    if platform == "windows-x86":
                        decodedCustom['override-settings']['allow-darktheme'] = 'Y' if theme == "dark" else 'N'
                    else:
                        decodedCustom['override-settings']['theme'] = theme
            decodedCustom['enable-lan-discovery'] = 'N' if denyLan else 'Y'
            #decodedCustom['direct-server'] = 'Y' if enableDirectIP else 'N'
            decodedCustom['allow-auto-disconnect'] = 'Y' if autoClose else 'N'
            effectiveApproveMode = 'password' if hidecmDefaultEnabled else passApproveMode
            effectiveEnableFileTransfer = enableFileTransfer and not forceDisableFileTransfer
            if permissionsDorO == "default":
                decodedCustom['default-settings']['access-mode'] = permissionsType
                decodedCustom['default-settings']['enable-keyboard'] = 'Y' if enableKeyboard else 'N'
                decodedCustom['default-settings']['enable-clipboard'] = 'Y' if enableClipboard else 'N'
                decodedCustom['default-settings']['enable-file-copy-paste'] = 'Y' if enableFileCopyPaste else 'N'
                decodedCustom['default-settings']['enable-file-transfer'] = 'Y' if effectiveEnableFileTransfer else 'N'
                decodedCustom['default-settings']['enable-audio'] = 'Y' if enableAudio else 'N'
                decodedCustom['default-settings']['enable-tunnel'] = 'Y' if enableTCP else 'N'
                decodedCustom['default-settings']['enable-remote-restart'] = 'Y' if enableRemoteRestart else 'N'
                decodedCustom['default-settings']['enable-record-session'] = 'Y' if enableRecording else 'N'
                decodedCustom['default-settings']['enable-block-input'] = 'Y' if enableBlockingInput else 'N'
                decodedCustom['default-settings']['allow-remote-config-modification'] = 'Y' if enableRemoteModi else 'N'
                decodedCustom['default-settings']['direct-server'] = 'Y' if enableDirectIP else 'N'
                decodedCustom['default-settings']['verification-method'] = 'use-permanent-password' if hidecmDefaultEnabled else 'use-both-passwords'
                decodedCustom['default-settings']['approve-mode'] = effectiveApproveMode
                decodedCustom['default-settings']['allow-hide-cm'] = 'Y' if hidecmDefaultEnabled else 'N'
                decodedCustom['default-settings']['allow-remove-wallpaper'] = 'Y' if removeWallpaper else 'N'
                decodedCustom['default-settings']['enable-remote-printer'] = 'Y' if enablePrinter else 'N'
                decodedCustom['default-settings']['enable-camera'] = 'Y' if enableCamera else 'N'
                decodedCustom['default-settings']['enable-terminal'] = 'Y' if enableTerminal else 'N'
            else:
                decodedCustom['override-settings']['access-mode'] = permissionsType
                decodedCustom['override-settings']['enable-keyboard'] = 'Y' if enableKeyboard else 'N'
                decodedCustom['override-settings']['enable-clipboard'] = 'Y' if enableClipboard else 'N'
                decodedCustom['override-settings']['enable-file-copy-paste'] = 'Y' if enableFileCopyPaste else 'N'
                decodedCustom['override-settings']['enable-file-transfer'] = 'Y' if effectiveEnableFileTransfer else 'N'
                decodedCustom['override-settings']['enable-audio'] = 'Y' if enableAudio else 'N'
                decodedCustom['override-settings']['enable-tunnel'] = 'Y' if enableTCP else 'N'
                decodedCustom['override-settings']['enable-remote-restart'] = 'Y' if enableRemoteRestart else 'N'
                decodedCustom['override-settings']['enable-record-session'] = 'Y' if enableRecording else 'N'
                decodedCustom['override-settings']['enable-block-input'] = 'Y' if enableBlockingInput else 'N'
                decodedCustom['override-settings']['allow-remote-config-modification'] = 'Y' if enableRemoteModi else 'N'
                decodedCustom['override-settings']['direct-server'] = 'Y' if enableDirectIP else 'N'
                decodedCustom['override-settings']['verification-method'] = 'use-permanent-password' if hidecmDefaultEnabled else 'use-both-passwords'
                decodedCustom['override-settings']['approve-mode'] = effectiveApproveMode
                decodedCustom['override-settings']['allow-hide-cm'] = 'Y' if hidecmDefaultEnabled else 'N'
                decodedCustom['override-settings']['allow-remove-wallpaper'] = 'Y' if removeWallpaper else 'N'
                decodedCustom['override-settings']['enable-remote-printer'] = 'Y' if enablePrinter else 'N'
                decodedCustom['override-settings']['enable-camera'] = 'Y' if enableCamera else 'N'
                decodedCustom['override-settings']['enable-terminal'] = 'Y' if enableTerminal else 'N'

            if linuxCustomAllowed:
                for line in defaultManual.splitlines():
                    if not line.strip():
                        continue
                    k, _separator, value = line.partition('=')
                    decodedCustom['default-settings'][k.strip()] = value.strip()

                for line in overrideManual.splitlines():
                    if not line.strip():
                        continue
                    k, _separator, value = line.partition('=')
                    decodedCustom['override-settings'][k.strip()] = value.strip()

            # Legacy manual hide-tray lines are promoted to this field by the
            # form, leaving one authoritative setting in the generated config.
            if hideTray:
                decodedCustom['override-settings']['hide-tray'] = 'Y'

            if defaultStartOnBoot:
                decodedCustom['override-settings']['start-on-boot'] = 'Y'
            if defaultImageQuality:
                decodedCustom['override-settings']['image-quality'] = defaultImageQuality
            if defaultCodec:
                decodedCustom['override-settings']['codec-preference'] = defaultCodec
            if preferWebsocket and not smartMultiRelay:
                decodedCustom['override-settings']['allow-websocket'] = 'Y'
            if sessionIdleMinutes:
                decodedCustom['allow-auto-disconnect'] = 'Y'
                decodedCustom['override-settings']['auto-disconnect-timeout'] = str(
                    int(sessionIdleMinutes) * 60
                )
            if allowIdPrefixes:
                prefixes = [
                    part.strip()
                    for part in allowIdPrefixes.replace('，', ',').split(',')
                    if part.strip()
                ]
                if prefixes:
                    decodedCustom['override-settings']['whitelist'] = ','.join(prefixes)

            hidecm_settings = (
                'approve-mode',
                'verification-method',
                'allow-hide-cm',
            )
            if hidecm:
                for key_name in hidecm_settings:
                    decodedCustom['override-settings'].pop(key_name, None)
                decodedCustom['default-settings'].update({
                    'approve-mode': 'password' if hidecmDefaultEnabled else passApproveMode,
                    'verification-method': (
                        'use-permanent-password'
                        if hidecmDefaultEnabled
                        else 'use-both-passwords'
                    ),
                    'allow-hide-cm': 'Y' if hidecmDefaultEnabled else 'N',
                })

            # Keep relay selection authoritative for generated clients. An empty
            # override makes RustDesk use the relay returned by hbbs even when a
            # previous installation left a local fixed relay in CONFIG2.
            decodedCustom['override-settings']['relay-server'] = relayServer
            if smartMultiRelay:
                # Production smart relay negotiation is accepted only over a
                # certificate-verified WSS rendezvous stream. Keep api-server
                # in the ordinary override map as well as the top-level hard
                # setting because hbb_common's transport selector reads the
                # ordinary Config option.
                decodedCustom['override-settings']['api-server'] = apiServer
                decodedCustom['override-settings']['allow-websocket'] = 'Y'
                decodedCustom['override-settings']['allow-insecure-tls-fallback'] = 'N'

            if not linuxCustomAllowed:
                decodedCustom = {}
            
            decodedCustomJson = json.dumps(decodedCustom)

            string_bytes = decodedCustomJson.encode("ascii")
            base64_bytes = base64.b64encode(string_bytes)
            encodedCustom = base64_bytes.decode("ascii")

            # #github limits inputs to 10, so lump extras into one with json
            # extras = {}
            # extras['genurl'] = _settings.GENURL
            # #extras['runasadmin'] = runasadmin
            # extras['urlLink'] = urlLink
            # extras['downloadLink'] = downloadLink
            # extras['delayFix'] = 'true' if delayFix else 'false'
            # extras['rdgen'] = 'true'
            # extras['cycleMonitor'] = 'true' if cycleMonitor else 'false'
            # extras['xOffline'] = 'true' if xOffline else 'false'
            # extras['removeNewVersionNotif'] = 'true' if removeNewVersionNotif else 'false'
            # extras['hideSettingsMenu'] = 'true' if hideSettingsMenu else 'false'
            # extras['compname'] = compname
            # extras['androidappid'] = androidappid
            # extra_input = json.dumps(extras)

            ####from here run the github action, we need user, repo, access token.
            if platform == 'windows':
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-windows.yml/dispatches'
                if selfhosted:
                    url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/sh-generator-windows.yml/dispatches'
            if platform == 'windows-x86':
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-windows-x86.yml/dispatches'
            elif platform == 'linux':
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-linux.yml/dispatches'
            elif platform == 'android':
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-android.yml/dispatches'
            elif platform == 'macos':
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-macos.yml/dispatches'
            elif platform == 'ios':
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-ios.yml/dispatches'
            else:
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-windows.yml/dispatches'
                if selfhosted:
                    url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/sh-generator-windows.yml/dispatches'

            #url = 'https://api.github.com/repos/'+_settings.GHUSER+'/rustdesk/actions/workflows/test.yml/dispatches'  
            inputs_raw = {
                "server":server,
                "key":key,
                "apiServer":apiServer,
                "custom":encodedCustom,
                "uuid":myuuid,
                "iconlink_url":iconlink_url,
                "iconlink_uuid":iconlink_uuid,
                "iconlink_file":iconlink_file,
                "logolink_url":logolink_url,
                "logolink_uuid":logolink_uuid,
                "logolink_file":logolink_file,
                "privacylink_url":privacylink_url,
                "privacylink_uuid":privacylink_uuid,
                "privacylink_file":privacylink_file,
                "appname":appname,
                "genurl":_settings.GENURL,
                "urlLink":urlLink,
                "downloadLink":downloadLink,
                "delayFix": 'true' if delayFix else 'false',
                "smartMultiRelay": 'true' if smartMultiRelay else 'false',
                "beijingCustom": 'true' if beijingCustom else 'false',
                "rdgen":'true',
                "direction": direction,
                "hideNetworkSetting": 'true' if hideNetworkSetting else 'false',
                "defaultViewStyle": defaultViewStyle,
                "removeSetupServerTip": 'true' if removeSetupServerTip else 'false',
                "silentInstallOnDoubleClick": 'true' if silentInstallOnDoubleClick else 'false',
                "silentAgentMode": 'true' if silentAgentMode else 'false',
                "hidecm": 'true' if hidecm else 'false',
                "hidecmDefaultEnabled": 'true' if hidecmDefaultEnabled else 'false',
                "copyIdPasswordButton": 'true' if copyIdPasswordButton else 'false',
                "manualTemporaryPassword": 'true' if manualTemporaryPassword else 'false',
                "showStartOnBootCheckbox": 'true' if showStartOnBootCheckbox else 'false',
                "defaultStartOnBoot": 'true' if defaultStartOnBoot else 'false',
                "sloganText": sloganText,
                "macosBundleId": macosBundleId,
                "iosBundleId": iosBundleId,
                "msiDesktopShortcut": msiDesktopShortcut,
                "msiStartMenuShortcut": msiStartMenuShortcut,
                "msiInstallPrinter": msiInstallPrinter,
                "incomingCompactMode": 'true' if incomingCompactMode else 'false',
                "incomingContentWidth": str(incomingContentWidth),
                "incomingContentHeight": str(incomingContentHeight),
                "forceDisableFileTransfer": 'true' if forceDisableFileTransfer else 'false',
                "cycleMonitor": 'true' if cycleMonitor else 'false',
                "xOffline": 'true' if xOffline else 'false',
                "removeNewVersionNotif": 'true' if removeNewVersionNotif else 'false',
                "hideSettingsMenu": 'true' if hideSettingsMenu else 'false',
                "removeRecentSessions": 'true' if removeRecentSessions else 'false',
                "compname": compname,
                "androidappid":androidappid,
                "filename":filename,
                "token": callback_token,
                "status_signature": signing.dumps(
                    {"uuid": myuuid},
                    salt=STATUS_UPDATE_SALT,
                ),
            }

            Path("temp_zips").mkdir(parents=True, exist_ok=True)
            zip_filename = f"secrets_{myuuid}_{uuid.uuid4()}.zip"
            zip_path = os.path.join("temp_zips", zip_filename)

            # Write the JSON directly into the encrypted archive. This avoids
            # a plaintext secret file and Windows file-lock races in cleanup.
            with pyzipper.AESZipFile(
                zip_path,
                "w",
                compression=pyzipper.ZIP_LZMA,
                encryption=pyzipper.WZ_AES,
            ) as zf:
                zf.setpassword(_settings.ZIP_PASSWORD.encode())
                zf.writestr("secrets.json", json.dumps(inputs_raw).encode("utf-8"))

            zipJson = {}
            zipJson['url'] = full_url
            zipJson['file'] = zip_filename
            zipJson['signature'] = signing.dumps(
                {'filename': zip_filename},
                salt=ZIP_DOWNLOAD_SALT,
            )
            zipJson['uuid'] = myuuid
            zipJson['status_signature'] = signing.dumps(
                {"uuid": myuuid},
                salt=DISPATCH_FAILURE_SALT,
            )

            zip_url = json.dumps(zipJson)

            data = {
                "ref":_settings.GHBRANCH,
                "inputs":{
                    "version":version,
                    "zip_url":zip_url
                },
                "return_run_details": True
            } 
            #print(data)
            from .github_auth import github_auth_headers

            headers = {
                **github_auth_headers(),
                "Content-Type": "application/json",
            }
            download_access = form.cleaned_data.get("download_access") or "login"
            download_ttl_hours = min(
                max(int(form.cleaned_data.get("download_ttl_hours") or 168), 1),
                168,
            )
            download_token = download_token_for_run(myuuid)
            initial_status = (
                ARTIFACT_PENDING_STATUS
                if platform == "windows"
                else "in_progress"
            )
            config_snapshot = build_config_snapshot(
                form_data=form.cleaned_data,
                decoded_custom=decodedCustom,
                effective={
                    "platform": platform,
                    "version": version,
                    "appname": appname,
                    "filename": filename,
                    "compname": compname,
                    "androidappid": androidappid,
                    "direction": direction,
                    "installation": installation,
                    "settings": settings,
                    "server": server,
                    "relayServer": relayServer,
                    "apiServer": apiServer,
                    "key": key,
                    "smartMultiRelay": smartMultiRelay,
                    "beijingCustom": beijingCustom,
                    "urlLink": urlLink,
                    "downloadLink": downloadLink,
                    "hasIcon": iconlink_file not in (None, "", "false"),
                    "hasLogo": logolink_file not in (None, "", "false"),
                    "hasPrivacyImage": privacylink_file not in (None, "", "false"),
                    "permPass": permPass,
                    "passApproveMode": passApproveMode,
                    "hidecm": hidecm,
                    "hidecmDefaultEnabled": hidecmDefaultEnabled,
                    "silentAgentMode": silentAgentMode,
                    "denyLan": denyLan,
                    "enableDirectIP": enableDirectIP,
                    "theme": theme,
                    "themeDorO": themeDorO,
                    "defaultViewStyle": defaultViewStyle,
                    "hideNetworkSetting": hideNetworkSetting,
                    "hideSettingsMenu": hideSettingsMenu,
                    "hideTray": hideTray,
                    "removeSetupServerTip": removeSetupServerTip,
                    "removeNewVersionNotif": removeNewVersionNotif,
                    "removeRecentSessions": removeRecentSessions,
                    "incomingCompactMode": incomingCompactMode,
                    "incomingContentWidth": incomingContentWidth,
                    "incomingContentHeight": incomingContentHeight,
                    "copyIdPasswordButton": copyIdPasswordButton,
                    "manualTemporaryPassword": manualTemporaryPassword,
                    "showStartOnBootCheckbox": showStartOnBootCheckbox,
                    "defaultStartOnBoot": defaultStartOnBoot,
                    "sloganText": sloganText,
                    "macosBundleId": macosBundleId,
                    "iosBundleId": iosBundleId,
                    "defaultImageQuality": defaultImageQuality,
                    "defaultCodec": defaultCodec,
                    "preferWebsocket": preferWebsocket,
                    "sessionIdleMinutes": sessionIdleMinutes,
                    "allowIdPrefixes": allowIdPrefixes,
                    "msiDesktopShortcut": msiDesktopShortcut,
                    "msiStartMenuShortcut": msiStartMenuShortcut,
                    "msiInstallPrinter": msiInstallPrinter,
                    "permissionsDorO": permissionsDorO,
                    "permissionsType": permissionsType,
                    "enableKeyboard": enableKeyboard,
                    "enableClipboard": enableClipboard,
                    "enableFileCopyPaste": enableFileCopyPaste,
                    "enableFileTransfer": enableFileTransfer,
                    "forceDisableFileTransfer": forceDisableFileTransfer,
                    "enableAudio": enableAudio,
                    "enableTCP": enableTCP,
                    "enableRemoteRestart": enableRemoteRestart,
                    "enableRecording": enableRecording,
                    "enableBlockingInput": enableBlockingInput,
                    "enableRemoteModi": enableRemoteModi,
                    "enablePrinter": enablePrinter,
                    "enableCamera": enableCamera,
                    "enableTerminal": enableTerminal,
                    "removeWallpaper": removeWallpaper,
                    "autoClose": autoClose,
                    "delayFix": delayFix,
                    "cycleMonitor": cycleMonitor,
                    "xOffline": xOffline,
                    "silentInstallOnDoubleClick": silentInstallOnDoubleClick,
                    "selfhosted": selfhosted,
                    "linuxCustomAllowed": linuxCustomAllowed,
                    "download_access": download_access,
                    "download_ttl_hours": download_ttl_hours,
                },
            )
            try:
                new_github_run = create_github_run_with_reservation(
                    request.user,
                    uuid=myuuid,
                    status=initial_status,
                    platform=platform,
                    artifact_stem=filename,
                    smart_multi_relay=smartMultiRelay,
                    callback_token_hash=_callback_token_hash(callback_token),
                    download_access=download_access,
                    download_ttl_hours=download_ttl_hours,
                    download_token_hash=_callback_token_hash(download_token),
                    config_snapshot=config_snapshot,
                )
            except GenerationQuotaExceeded:
                # The form has already been normalized and temporary files
                # may exist; do not dispatch a workflow when the entitlement
                # is exhausted or expired.
                form.add_error(None, "当前账号的生成额度已用尽或已过期，无法开始新的生成任务。")
                return render(request, "generator.html", _generator_context(request, form))

            # Persist the run before dispatch so any rejected/failed request
            # can release a count reservation atomically.
            try:
                response = requests.post(url, json=data, headers=headers)
                print(response)
                if response.status_code == 204 or response.status_code == 200:
                    github_data = {}
                    if response.content:
                        try:
                            github_data = response.json()
                            print(github_data)
                        except ValueError as e:
                            print(f"GitHub dispatch returned non-JSON success body: {e}")
                    workflow_run_id = github_data.get('workflow_run_id')
                    if workflow_run_id:
                        GithubRun.objects.filter(
                            pk=new_github_run.pk,
                            status=initial_status,
                        ).update(github_run_id=workflow_run_id)

                    log_url = github_data.get('html_url') or f"https://github.com/{_settings.GHUSER}/{_settings.REPONAME}/actions"
                    return render(
                        request,
                        "waiting.html",
                        _waiting_page_context(
                            new_github_run,
                            filename=filename,
                            platform=platform,
                            log_url=log_url,
                            status=new_github_run.status or "queued",
                        ),
                    )
                else:
                    transitioned = GithubRun.objects.filter(
                        pk=new_github_run.pk,
                        status=initial_status,
                    ).update(status="dispatch_failed")
                    if transitioned:
                        new_github_run.refresh_from_db()
                        release_generation_reservation(new_github_run)
                    return JsonResponse({"error": "GitHub rejected the start request", "details": response.text}, status=500)
            except Exception as e:
                # A connection error is ambiguous: GitHub may have accepted the
                # dispatch before the response was lost. Keep the run able to
                # receive its authenticated callbacks and artifacts.
                return JsonResponse({"error": f"Connection error: {str(e)}"}, status=500)
    else:
        form = GenerateForm()
    #return render(request, 'maintenance.html')
    return render(request, 'generator.html', _generator_context(request, form))


@login_required
@require_GET
def check_for_file(request):
    filename = request.GET.get('filename')
    run_uuid = request.GET.get('uuid')
    platform = request.GET.get('platform')
    gh_run = _user_run_or_404(request, run_uuid)
    current_status = (gh_run.status or '').lower()
    if gh_run.github_run_id:
        github_log_url = f"https://github.com/{_settings.GHUSER}/{_settings.REPONAME}/actions/runs/{gh_run.github_run_id}"
    else:
        github_log_url = f"https://github.com/{_settings.GHUSER}/{_settings.REPONAME}/actions"

    if gh_run.github_run_id and current_status not in TERMINAL_RUN_STATUSES:
        from .github_auth import github_auth_headers

        headers = github_auth_headers()
        api_url = f"https://api.github.com/repos/{_settings.GHUSER}/{_settings.REPONAME}/actions/runs/{gh_run.github_run_id}"
        
        try:
            gh_response = requests.get(api_url, headers=headers)
            if gh_response.status_code == 200:
                gh_data = gh_response.json()
                
                if gh_data['status'] == 'completed':
                    conclusion = gh_data['conclusion']
                    if conclusion == "success" and current_status == ARTIFACT_PENDING_STATUS:
                        # A deferred workflow must explicitly confirm that every
                        # required installer reached this server. The conditional
                        # write avoids racing a successful finalization request.
                        GithubRun.objects.filter(
                            pk=gh_run.pk,
                            status=ARTIFACT_PENDING_STATUS,
                        ).update(status=ARTIFACT_INCOMPLETE_STATUS)
                        gh_run.refresh_from_db(fields=["status"])
                    else:
                        GithubRun.objects.filter(
                            pk=gh_run.pk,
                            status=current_status,
                        ).update(status=conclusion)
                        gh_run.refresh_from_db(fields=["status"])
                    current_status = (gh_run.status or '').lower()
        except Exception as e:
            print(f"Error checking GitHub: {e}")

    if current_status in FAILED_TERMINAL_RUN_STATUSES and not gh_run.artifact_uploaded_at:
        # A failed/cancelled workflow must not hold a reserved count forever.
        release_generation_reservation(gh_run)
        gh_run.refresh_from_db()
    
    if current_status == "success":
        files = list_generated_files(run_uuid)
        success_ctx = {
            "filename": filename,
            "uuid": run_uuid,
            "platform": platform,
            **_delivery_context(gh_run, files),
        }
        if request.GET.get("format") == "json":
            return JsonResponse(
                {
                    "state": "success",
                    "status": current_status,
                    "status_label": _waiting_status_label(current_status),
                    "progress": 100,
                    "redirect": f"/check_for_file?{urlencode({'filename': filename, 'uuid': run_uuid, 'platform': platform})}",
                }
            )
        return render(request, "generated.html", success_ctx)

    if current_status in FAILED_TERMINAL_RUN_STATUSES:
        files = list_generated_files(run_uuid)
        if request.GET.get("format") == "json":
            return JsonResponse(
                {
                    "state": "failed",
                    "status": current_status,
                    "status_label": _waiting_status_label(current_status),
                    "progress": 100,
                    "redirect": f"/check_for_file?{urlencode({'filename': filename, 'uuid': run_uuid, 'platform': platform})}",
                }
            )
        return render(
            request,
            "failure.html",
            {
                "log_url": github_log_url,
                "filename": filename,
                "uuid": run_uuid,
                "platform": platform,
                "status": gh_run.status,
                **_delivery_context(gh_run, files),
            },
        )

    waiting_ctx = _waiting_page_context(
        gh_run,
        filename=filename,
        platform=platform,
        log_url=github_log_url,
        status=gh_run.status,
    )
    if request.GET.get("format") == "json":
        return JsonResponse(
            {
                "state": "waiting",
                "status": waiting_ctx["status"],
                "status_label": waiting_ctx["status_label"],
                "progress": waiting_ctx["progress_percent"],
                "created_at_ms": waiting_ctx["created_at_ms"],
            }
        )
    return render(request, "waiting.html", waiting_ctx)

@require_GET
def download(request):
    filename = _safe_output_filename(request.GET.get('filename'))
    run_uuid = _canonical_run_uuid(request.GET.get('uuid'))
    run = get_object_or_404(GithubRun, uuid=run_uuid)

    # A public link is authorized solely by its per-run token. The token is
    # deterministic so result pages can reconstruct it, while only its hash is
    # persisted for request-time verification.
    supplied_token = (request.GET.get("token") or "").strip()
    if run.download_access == "public" and run.download_token_hash:
        expected_hash = run.download_token_hash
        if not supplied_token or not secrets.compare_digest(
            _callback_token_hash(supplied_token),
            expected_hash,
        ):
            raise Http404("Download link not found")
    elif run.download_access == "public":
        # Legacy public rows cannot be safely shared because they have no
        # persisted token.  Treat them as unavailable rather than falling back
        # to UUID-only access.
        raise Http404("Download link not found")
    else:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if run.owner_id != request.user.pk and not (
            request.user.is_staff or request.user.is_superuser
        ):
            raise Http404("Download link not found")

    now = timezone.now()
    if run.download_expires_at and now >= run.download_expires_at:
        return HttpResponse("Download link expired", status=410)
    artifact_expires_at = run.artifact_expires_at or (
        run.created_at + timedelta(days=7)
    )
    if now >= artifact_expires_at:
        return HttpResponse("Generated file expired", status=410)

    if run.platform or GeneratedArtifact.objects.filter(run=run).exists():
        file_path, artifact = _committed_artifact_file_or_404(run, filename)
    else:
        # Rows created before artifact receipts were introduced remain
        # downloadable until their existing retention window expires.
        file_path = _generated_file_or_404(run_uuid, filename)
        artifact = None
    with open(file_path, 'rb') as file:
        content = file.read()
    if artifact and hashlib.sha256(content).hexdigest() != artifact.sha256:
        raise Http404("Generated file not found")
    try:
        from .ops import record_download_event

        record_download_event(
            run=run,
            user=request.user,
            filename=filename,
            request=request,
        )
    except Exception:
        pass
    content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    response = HttpResponse(content, headers={
        'Content-Type': content_type,
        'Content-Disposition': f'attachment; filename="{filename}"'
    })
    return response

@require_GET
def get_png(request):
    filename = _safe_output_filename(request.GET.get('filename'))
    run_uuid = request.GET.get('uuid')
    run, error = _machine_run(request, run_uuid)
    if error:
        return error
    png_root = (Path("png") / run.uuid).resolve()
    file_path = (png_root / filename).resolve()
    try:
        file_path.relative_to(png_root)
    except ValueError:
        raise Http404("Image not found")
    if not file_path.is_file():
        raise Http404("Image not found")
    with open(file_path, "rb") as file:
        return HttpResponse(file.read(), headers={
            "Content-Type": "image/png",
            "Content-Disposition": f'inline; filename="{filename}"',
        })


@csrf_exempt
@require_POST
def update_github_run(request):
    try:
        data = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return HttpResponse("Invalid JSON", status=400)
    myuuid = data.get("uuid")
    mystatus = str(data.get("status") or "").strip().lower()
    allowed_statuses = {
        "in_progress", "queued", "success", "failure", "cancelled",
        "timed_out", "skipped", "action_required",
    }
    if mystatus not in allowed_statuses:
        return HttpResponse("Invalid status", status=400)
    run, error = _status_run(request, myuuid, mystatus)
    if error:
        return error
    blocked_sources = set(TERMINAL_RUN_STATUSES)
    if mystatus not in FAILED_TERMINAL_RUN_STATUSES:
        blocked_sources.add(ARTIFACT_PENDING_STATUS)
    status_filter = GithubRun.objects.filter(pk=run.pk).exclude(
        status__in=blocked_sources,
    )
    if mystatus == "success" and run.platform == "windows":
        status_filter = status_filter.exclude(platform="windows")
    status_filter.update(status=mystatus)

    run.refresh_from_db(fields=["status", "artifact_uploaded_at", "quota_reserved", "quota_counted"])
    if run.status in FAILED_TERMINAL_RUN_STATUSES and not run.artifact_uploaded_at:
        release_generation_reservation(run)
        try:
            from .wecom_notify import format_build_failure_alert, notify_wecom_if_enabled

            notify_wecom_if_enabled(
                "build_failure",
                format_build_failure_alert(run=run),
            )
        except Exception:
            pass
    return HttpResponse("")

def resize_and_encode_icon(imagefile):
    maxWidth = 200
    try:
        with io.BytesIO() as image_buffer:
            for chunk in imagefile.chunks():
                image_buffer.write(chunk)
            image_buffer.seek(0)

            img = Image.open(image_buffer)
            imgcopy = img.copy()
    except (IOError, OSError):
        raise ValueError("Uploaded file is not a valid image format.")

    # Check if resizing is necessary
    if img.size[0] <= maxWidth:
        with io.BytesIO() as image_buffer:
            imgcopy.save(image_buffer, format=imagefile.content_type.split('/')[1])
            image_buffer.seek(0)
            return_image = ContentFile(image_buffer.read(), name=imagefile.name)
        return base64.b64encode(return_image.read())

    # Calculate resized height based on aspect ratio
    wpercent = (maxWidth / float(img.size[0]))
    hsize = int((float(img.size[1]) * float(wpercent)))

    # Resize the image while maintaining aspect ratio using LANCZOS resampling
    imgcopy = imgcopy.resize((maxWidth, hsize), Image.Resampling.LANCZOS)

    with io.BytesIO() as resized_image_buffer:
        imgcopy.save(resized_image_buffer, format=imagefile.content_type.split('/')[1])
        resized_image_buffer.seek(0)

        resized_imagefile = ContentFile(resized_image_buffer.read(), name=imagefile.name)

    # Return the Base64 encoded representation of the resized image
    resized64 = base64.b64encode(resized_imagefile.read())
    #print(resized64)
    return resized64
 
@csrf_exempt
@require_POST
def startgh(request):
    #print(request)
    if not _shared_api_authorized(request):
        return HttpResponse("Unauthorized", status=401)
    try:
        data_ = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return HttpResponse("Invalid JSON", status=400)
    ####from here run the github action, we need user, repo, access token.
    url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-'+data_.get('platform')+'.yml/dispatches'  
    data = {
        "ref": _settings.GHBRANCH,
        "inputs":{
            "server":data_.get('server'),
            "key":data_.get('key'),
            "apiServer":data_.get('apiServer'),
            "custom":data_.get('custom'),
            "uuid":data_.get('uuid'),
            "iconlink":data_.get('iconlink'),
            "logolink":data_.get('logolink'),
            "appname":data_.get('appname'),
            "extras":data_.get('extras'),
            "filename":data_.get('filename')
        }
    } 
    from .github_auth import github_auth_headers

    headers = {
        **github_auth_headers(),
        "Content-Type": "application/json",
    }
    response = requests.post(url, json=data, headers=headers)
    print(response)
    return HttpResponse(status=204)

def save_png(file, uuid, domain, name):
    file_save_path = "png/%s/%s" % (uuid, name)
    Path("png/%s" % uuid).mkdir(parents=True, exist_ok=True)

    if isinstance(file, str):  # Check if it's a base64 string
        try:
            header, encoded = file.split(';base64,')
            decoded_img = base64.b64decode(encoded)
            file = ContentFile(decoded_img, name=name) # Create a file-like object
        except ValueError:
            print("Invalid base64 data")
            return None  # Or handle the error as you see fit
        except Exception as e:  # Catch general exceptions during decoding
            print(f"Error decoding base64: {e}")
            return None
        
    with open(file_save_path, "wb+") as f:
        for chunk in file.chunks():
            f.write(chunk)
    # imageJson = {}
    # imageJson['url'] = domain
    # imageJson['uuid'] = uuid
    # imageJson['file'] = name
    #return "%s/%s" % (domain, file_save_path)
    return domain, uuid, name

@csrf_exempt
@require_POST
def save_custom_client(request):
    file = request.FILES.get("file")
    myuuid = request.POST.get("uuid")
    if file is None or not myuuid:
        return HttpResponse("Missing file or UUID", status=400)
    max_upload = int(getattr(_settings, "DATA_UPLOAD_MAX_MEMORY_SIZE", 0) or 0)
    if max_upload > 0:
        declared = int(getattr(file, "size", 0) or 0)
        if declared > max_upload:
            return HttpResponse("Upload too large", status=413)
    run, error = _machine_run(request, myuuid)
    if error:
        return error
    if run.status in FAILED_TERMINAL_RUN_STATUSES:
        return HttpResponse("Run no longer accepts artifacts", status=409)
    defer_completion = str(
        request.POST.get("defer_completion", "false")
    ).strip().lower()
    if defer_completion not in {"true", "false"}:
        return HttpResponse("Invalid completion mode", status=400)
    defer_completion = defer_completion == "true"
    filename = _safe_output_filename(file.name)
    output_root = (Path("exe") / run.uuid).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    file_save_path = (output_root / filename).resolve()
    try:
        file_save_path.relative_to(output_root)
    except ValueError:
        raise Http404("Generated file not found")
    temp_path = None
    digest = hashlib.sha256()
    size = 0
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_root,
            prefix=".upload-",
            suffix=".part",
            delete=False,
        ) as output_file:
            temp_path = Path(output_file.name)
            for chunk in file.chunks():
                output_file.write(chunk)
                digest.update(chunk)
                size += len(chunk)
                if max_upload > 0 and size > max_upload:
                    return HttpResponse("Upload too large", status=413)

        if not size or not _valid_artifact_filename(filename, run.platform or None):
            return HttpResponse("File saved successfully!")

        with transaction.atomic():
            # Make the first statement a write so SQLite serializes only this
            # short commit section, never the multipart upload itself.
            claimed = GithubRun.objects.filter(pk=run.pk).exclude(
                status__in=FAILED_TERMINAL_RUN_STATUSES,
            ).update(status=models.F("status"))
            if not claimed:
                return HttpResponse("Run no longer accepts artifacts", status=409)

            run = GithubRun.objects.get(pk=run.pk)
            expected_windows_files = _windows_artifact_names(run)
            if run.platform == "windows" and not expected_windows_files:
                return HttpResponse("Artifact contract is invalid", status=409)
            if expected_windows_files and filename not in expected_windows_files:
                return HttpResponse("Artifact does not match this run", status=409)

            content_hash = digest.hexdigest()
            existing = GeneratedArtifact.objects.filter(
                run=run,
                filename=filename,
            ).first()
            if existing:
                if existing.size != size or existing.sha256 != content_hash:
                    return HttpResponse("Artifact content does not match", status=409)
                # The staged upload matches the immutable receipt, so it can
                # also repair a missing or externally corrupted disk copy.
                os.replace(temp_path, file_save_path)
                temp_path = None
                return HttpResponse("File saved successfully!")

            if expected_windows_files and run.status == "success":
                return HttpResponse("Finalized artifacts are immutable", status=409)

            os.replace(temp_path, file_save_path)
            temp_path = None
            GeneratedArtifact.objects.create(
                run=run,
                filename=filename,
                size=size,
                sha256=content_hash,
            )
            artifact_file_count = GeneratedArtifact.objects.filter(run=run).count()
            mark_artifact_uploaded(
                run,
                artifact_file_count=artifact_file_count,
            )
            if run.platform == "windows":
                GithubRun.objects.filter(pk=run.pk).exclude(
                    status__in=TERMINAL_RUN_STATUSES,
                ).update(status=ARTIFACT_PENDING_STATUS)
            elif (
                run.status not in TERMINAL_RUN_STATUSES
                and run.status != ARTIFACT_PENDING_STATUS
            ):
                GithubRun.objects.filter(pk=run.pk, status=run.status).update(
                    status=ARTIFACT_PENDING_STATUS if defer_completion else "success"
                )
                if not defer_completion:
                    maybe_notify_build_success(run.pk)
        return HttpResponse("File saved successfully!")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@csrf_exempt
@require_POST
def finalize_custom_client(request):
    try:
        data = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return HttpResponse("Invalid JSON", status=400)

    run, error = _machine_run(request, data.get("uuid"))
    if error:
        return error
    if run.status not in {ARTIFACT_PENDING_STATUS, "success"}:
        return HttpResponse("Run is not awaiting artifacts", status=409)

    expected_files = list(_windows_artifact_names(run))
    if not expected_files:
        return HttpResponse("Artifact contract is invalid", status=409)
    output_root = (Path("exe") / run.uuid).resolve()
    receipts = {
        artifact.filename: artifact
        for artifact in GeneratedArtifact.objects.filter(
            run=run,
            filename__in=expected_files,
        )
    }
    missing_files = []
    invalid_files = []
    for filename in expected_files:
        receipt = receipts.get(filename)
        file_path = (output_root / filename).resolve()
        try:
            file_path.relative_to(output_root)
        except ValueError:
            return HttpResponse("Invalid artifact path", status=400)
        if receipt is None or not file_path.is_file():
            missing_files.append(filename)
        elif (
            file_path.stat().st_size != receipt.size
            or _sha256_file(file_path) != receipt.sha256
        ):
            invalid_files.append(filename)

    if missing_files or invalid_files:
        return JsonResponse(
            {
                "error": "Required artifacts are missing or invalid",
                "missing": missing_files,
                "invalid": invalid_files,
            },
            status=409,
        )

    artifact_file_count = GeneratedArtifact.objects.filter(run=run).count()

    if run.status == ARTIFACT_PENDING_STATUS:
        updated = GithubRun.objects.filter(
            pk=run.pk,
            status=ARTIFACT_PENDING_STATUS,
        ).update(status="success")
        if not updated:
            run.refresh_from_db(fields=["status"])
            if run.status != "success":
                return HttpResponse("Run is no longer awaiting artifacts", status=409)
    elif not GithubRun.objects.filter(pk=run.pk, status="success").exists():
        return HttpResponse("Run is no longer successful", status=409)

    GithubRun.objects.filter(
        pk=run.pk,
        status="success",
        artifact_file_count__lt=artifact_file_count,
    ).update(artifact_file_count=artifact_file_count)
    maybe_notify_build_success(run.pk)
    return JsonResponse({"status": "success", "files": expected_files})


def _commit_downloaded_artifact(run, filename, file_path, size, content_hash, *, defer_completion):
    """Register a local artifact file that already matches size/sha256."""
    output_root = (Path("exe") / run.uuid).resolve()
    file_save_path = (output_root / filename).resolve()
    try:
        file_save_path.relative_to(output_root)
    except ValueError:
        return HttpResponse("Invalid artifact path", status=400)

    with transaction.atomic():
        claimed = GithubRun.objects.filter(pk=run.pk).exclude(
            status__in=FAILED_TERMINAL_RUN_STATUSES,
        ).update(status=models.F("status"))
        if not claimed:
            return HttpResponse("Run no longer accepts artifacts", status=409)

        run = GithubRun.objects.get(pk=run.pk)
        expected_windows_files = _windows_artifact_names(run)
        if run.platform == "windows" and not expected_windows_files:
            return HttpResponse("Artifact contract is invalid", status=409)
        if expected_windows_files and filename not in expected_windows_files:
            return HttpResponse("Artifact does not match this run", status=409)

        existing = GeneratedArtifact.objects.filter(run=run, filename=filename).first()
        if existing:
            if existing.size != size or existing.sha256 != content_hash:
                return HttpResponse("Artifact content does not match", status=409)
            if file_path.resolve() != file_save_path:
                os.replace(file_path, file_save_path)
            return None

        if expected_windows_files and run.status == "success":
            return HttpResponse("Finalized artifacts are immutable", status=409)

        if file_path.resolve() != file_save_path:
            os.replace(file_path, file_save_path)
        GeneratedArtifact.objects.create(
            run=run,
            filename=filename,
            size=size,
            sha256=content_hash,
        )
        artifact_file_count = GeneratedArtifact.objects.filter(run=run).count()
        mark_artifact_uploaded(run, artifact_file_count=artifact_file_count)
        if run.platform == "windows":
            GithubRun.objects.filter(pk=run.pk).exclude(
                status__in=TERMINAL_RUN_STATUSES,
            ).update(status=ARTIFACT_PENDING_STATUS)
        elif (
            run.status not in TERMINAL_RUN_STATUSES
            and run.status != ARTIFACT_PENDING_STATUS
        ):
            GithubRun.objects.filter(pk=run.pk, status=run.status).update(
                status=ARTIFACT_PENDING_STATUS if defer_completion else "success"
            )
            if not defer_completion:
                maybe_notify_build_success(run.pk)
    return None


@csrf_exempt
@require_POST
def prepare_artifact_upload(request):
    """Issue object-storage PUT URLs when COS/OSS is enabled; else ask for direct upload."""
    try:
        data = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return HttpResponse("Invalid JSON", status=400)

    run, error = _machine_run(request, data.get("uuid"))
    if error:
        return error
    if run.status in FAILED_TERMINAL_RUN_STATUSES:
        return HttpResponse("Run no longer accepts artifacts", status=409)

    files = data.get("files") or []
    if not isinstance(files, list) or not files:
        return HttpResponse("Missing files", status=400)

    from .object_storage import (
        ObjectStorageError,
        artifact_object_key,
        create_presigned_put_url,
        get_active_object_storage,
    )

    provider, config = get_active_object_storage()
    if not provider or config is None:
        return JsonResponse({"mode": "direct", "provider": None, "uploads": []})

    uploads = []
    try:
        for raw_name in files:
            filename = _safe_output_filename(str(raw_name or ""))
            if not filename or not _valid_artifact_filename(filename, run.platform or None):
                return HttpResponse(f"Invalid filename: {raw_name}", status=400)
            object_key = artifact_object_key(config, run.uuid, filename)
            signed = create_presigned_put_url(provider, config, object_key)
            uploads.append(
                {
                    "filename": filename,
                    "object_key": object_key,
                    "put_url": signed["put_url"],
                    "headers": signed.get("headers") or {},
                }
            )
    except ObjectStorageError as exc:
        return JsonResponse({"error": str(exc), "mode": "direct"}, status=503)

    return JsonResponse(
        {
            "mode": "object_storage",
            "provider": provider,
            "uploads": uploads,
        }
    )


@csrf_exempt
@require_POST
def complete_artifact_upload(request):
    """Pull uploaded objects from COS/OSS into local exe/ and create receipts."""
    try:
        data = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return HttpResponse("Invalid JSON", status=400)

    run, error = _machine_run(request, data.get("uuid"))
    if error:
        return error
    if run.status in FAILED_TERMINAL_RUN_STATUSES:
        return HttpResponse("Run no longer accepts artifacts", status=409)

    defer_completion = str(data.get("defer_completion", "true")).strip().lower() in {
        "1",
        "true",
        "yes",
    }
    artifacts = data.get("artifacts") or []
    if not isinstance(artifacts, list) or not artifacts:
        return HttpResponse("Missing artifacts", status=400)

    from .object_storage import (
        ObjectStorageError,
        delete_object,
        download_object_to_path,
        get_active_object_storage,
    )

    provider, config = get_active_object_storage()
    if not provider or config is None:
        return HttpResponse("Object storage is not configured", status=409)

    output_root = (Path("exe") / run.uuid).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    imported = []

    for item in artifacts:
        if not isinstance(item, dict):
            return HttpResponse("Invalid artifact entry", status=400)
        filename = _safe_output_filename(str(item.get("filename") or ""))
        object_key = str(item.get("object_key") or "").strip()
        expected_size = int(item.get("size") or 0)
        expected_sha = str(item.get("sha256") or "").strip().lower()
        if not filename or not object_key:
            return HttpResponse("Missing filename or object_key", status=400)
        if not object_key.startswith(f"{config.normalized_prefix}/{run.uuid}/"):
            return HttpResponse("object_key does not belong to this run", status=400)

        dest = (output_root / filename).resolve()
        try:
            dest.relative_to(output_root)
        except ValueError:
            return HttpResponse("Invalid artifact path", status=400)

        try:
            size, content_hash = download_object_to_path(provider, config, object_key, dest)
        except ObjectStorageError as exc:
            return HttpResponse(str(exc), status=502)

        if expected_size and size != expected_size:
            dest.unlink(missing_ok=True)
            return HttpResponse("Downloaded size mismatch", status=409)
        if expected_sha and content_hash != expected_sha:
            dest.unlink(missing_ok=True)
            return HttpResponse("Downloaded checksum mismatch", status=409)

        err = _commit_downloaded_artifact(
            run,
            filename,
            dest,
            size,
            content_hash,
            defer_completion=defer_completion,
        )
        if err is not None:
            return err
        imported.append({"filename": filename, "size": size, "sha256": content_hash})
        delete_object(provider, config, object_key)

    return JsonResponse(
        {
            "status": "ok",
            "provider": provider,
            "imported": imported,
        }
    )


@csrf_exempt
@require_POST
def cleanup_secrets(request):
    # Pass the UUID as a query param or in JSON body
    try:
        data = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return HttpResponse("Invalid JSON", status=400)
    my_uuid = data.get('uuid')
    if not my_uuid:
        return HttpResponse("Missing UUID", status=400)
    run, error = _machine_run(request, my_uuid)
    if error:
        return error
    # 1. Find the files in your temp directory matching the UUID
    temp_dir = os.path.join('temp_zips')
    
    # We look for any file starting with 'secrets_' and containing the uuid
    for filename in os.listdir(temp_dir):
        if filename.startswith(f"secrets_{run.uuid}_") and filename.endswith('.zip'):
            file_path = os.path.join(temp_dir, filename)
            try:
                os.remove(file_path)
                print(f"Successfully deleted {file_path}")
            except OSError as e:
                print(f"Error deleting file: {e}")

    return HttpResponse("Cleanup successful", status=200)

@require_GET
def get_zip(request):
    filename = _safe_output_filename(request.GET.get("filename"))
    signature = request.GET.get("signature", "")
    try:
        signed = signing.loads(
            signature,
            salt=ZIP_DOWNLOAD_SALT,
            max_age=ZIP_DOWNLOAD_MAX_AGE,
        )
    except (BadSignature, SignatureExpired):
        return HttpResponse("Invalid or expired download link", status=403)
    if signed.get("filename") != filename:
        return HttpResponse("Invalid download link", status=403)
    if not filename.startswith("secrets_") or not filename.endswith(".zip"):
        return HttpResponse("Invalid download link", status=403)
    temp_root = Path("temp_zips").resolve()
    file_path = (temp_root / filename).resolve()
    try:
        file_path.relative_to(temp_root)
    except ValueError:
        raise Http404("Archive not found")
    if not file_path.is_file():
        raise Http404("Archive not found")
    with open(file_path, "rb") as file:
        return HttpResponse(file.read(), headers={
            "Content-Type": "application/zip",
            "Content-Disposition": f'attachment; filename="{filename}"',
        })
