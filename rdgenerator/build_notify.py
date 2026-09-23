"""Notify the build owner by email when a client package is ready."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from .email_verification import (
    EmailVerificationDeliveryError,
    _build_email_connection,
    _ensure_email_backend_is_configured,
    _resolve_email_runtime,
)
from .models import GeneratedArtifact, GithubRun


logger = logging.getLogger(__name__)

PLATFORM_LABELS = {
    "windows": "Windows 64 位",
    "windows-x86": "Windows 32 位",
    "linux": "Linux",
    "android": "Android",
    "macos": "macOS",
    "ios": "iOS",
}


def _public_base_url():
    return (getattr(settings, "GENURL", "") or "").rstrip("/")


def _absolute_url(path_or_url):
    base = _public_base_url()
    if not path_or_url:
        return base or ""
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    if not base:
        return path_or_url
    if not path_or_url.startswith("/"):
        path_or_url = f"/{path_or_url}"
    return f"{base}{path_or_url}"


def _download_lines(run, files):
    # Lazy import keeps models/email free of views circular imports.
    from .views import download_token_for_run

    token = download_token_for_run(run.uuid) if run.download_token_hash else ""
    lines = []
    for filename in files:
        params = {"filename": filename, "uuid": run.uuid}
        if run.download_access == "public" and token:
            params["token"] = token
        url = _absolute_url(f"/download?{urlencode(params)}")
        note = ""
        if run.download_access != "public":
            note = "（需登录后下载）"
        lines.append(f"- {filename}{note}\n  {url}")
    return lines


def _result_page_url(run):
    filename = (run.artifact_stem or "client").strip() or "client"
    params = {
        "filename": filename,
        "uuid": run.uuid,
        "platform": run.platform or "windows",
    }
    return _absolute_url(f"/check_for_file?{urlencode(params)}")


def _format_expires(run):
    expires = run.download_expires_at or run.artifact_expires_at
    if not expires:
        return "约 7 天内有效"
    try:
        local = timezone.localtime(expires)
    except Exception:
        local = expires
    return local.strftime("%Y-%m-%d %H:%M %Z")


def _release_email_claim(run_id):
    GithubRun.objects.filter(pk=run_id).update(success_email_sent_at=None)


def maybe_notify_build_success(run_id):
    """Send one success email per run. Safe to call repeatedly.

    Returns True when a message was accepted by the mail backend.
    """
    if not run_id:
        return False

    now = timezone.now()
    claimed = GithubRun.objects.filter(
        pk=run_id,
        status="success",
        success_email_sent_at__isnull=True,
    ).update(success_email_sent_at=now)
    if not claimed:
        return False

    run = (
        GithubRun.objects.select_related("owner")
        .filter(pk=run_id, status="success")
        .first()
    )
    if run is None:
        return False

    files = list(
        GeneratedArtifact.objects.filter(run=run)
        .order_by("filename")
        .values_list("filename", flat=True)
    )
    if not files:
        # Artifacts not committed yet; allow a later finalize/upload to retry.
        _release_email_claim(run.pk)
        return False

    try:
        from .wecom_notify import format_build_success_alert, notify_wecom_if_enabled

        notify_wecom_if_enabled(
            "build_success",
            format_build_success_alert(run=run, filenames=files),
        )
    except Exception:
        logger.exception(
            "Unable to deliver WeCom build success alert for run %s",
            run.uuid,
        )

    owner = run.owner
    recipient = (getattr(owner, "email", "") or "").strip() if owner else ""
    if not recipient:
        logger.info(
            "Skip build success email for run %s: owner has no email",
            run.uuid,
        )
        # Keep claim so WeCom (and this path) do not double-fire on later finalize.
        return False

    try:
        _ensure_email_backend_is_configured()
    except EmailVerificationDeliveryError:
        logger.info(
            "Skip build success email for run %s: SMTP is not configured",
            run.uuid,
        )
        return False

    platform_label = PLATFORM_LABELS.get(
        run.platform,
        run.platform or "未知平台",
    )
    download_lines = _download_lines(run, files)
    body = (
        f"你好{(' ' + owner.username) if owner and owner.username else ''}，\n\n"
        f"你的 RustDesk 客户端已构建成功。\n\n"
        f"平台：{platform_label}\n"
        f"任务 ID：{run.uuid}\n"
        f"下载有效期至：{_format_expires(run)}\n\n"
        f"下载文件：\n"
        + ("\n".join(download_lines) if download_lines else "（暂无文件列表）")
        + "\n\n"
        f"结果页：\n{_result_page_url(run)}\n\n"
        "如果不是你本人发起的构建，请忽略此邮件。"
    )

    runtime = _resolve_email_runtime()
    connection = _build_email_connection(runtime)
    message = EmailMessage(
        subject=f"RustDesk 客户端构建成功（{platform_label}）",
        body=body,
        from_email=runtime["from_email"] or settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
        connection=connection,
    )
    try:
        sent_count = message.send(fail_silently=False)
        if sent_count != 1:
            raise RuntimeError("Email backend did not accept the message")
    except Exception as exc:
        _release_email_claim(run.pk)
        logger.exception(
            "Unable to deliver build success email for run %s",
            run.uuid,
        )
        try:
            from .ops import record_email_delivery
            from .models import EmailDeliveryLog

            record_email_delivery(
                kind=EmailDeliveryLog.KIND_BUILD_SUCCESS,
                to_email=recipient,
                success=False,
                subject=f"RustDesk 客户端构建成功（{platform_label}）",
                error_message=str(exc)[:500],
                related_run=run,
                related_user=owner,
            )
        except Exception:
            pass
        return False

    try:
        from .ops import record_email_delivery
        from .models import EmailDeliveryLog

        record_email_delivery(
            kind=EmailDeliveryLog.KIND_BUILD_SUCCESS,
            to_email=recipient,
            success=True,
            subject=f"RustDesk 客户端构建成功（{platform_label}）",
            related_run=run,
            related_user=owner,
        )
    except Exception:
        pass

    return True
