"""Enterprise WeChat (WeCom) group-robot notifications for admin alerts."""

from __future__ import annotations

import logging

import requests
from django.utils import timezone

from .models import SiteWecomConfig


logger = logging.getLogger(__name__)


class WecomNotifyError(Exception):
    """User-facing WeCom delivery failure."""


def _config():
    return SiteWecomConfig.load()


def send_wecom_text(content, *, config=None, mention_all=False):
    """Post a text message to the configured WeCom robot webhook."""
    config = config or _config()
    if not config.is_configured:
        raise WecomNotifyError("企业微信通知未启用或 Webhook 未正确配置。")
    payload = {
        "msgtype": "text",
        "text": {
            "content": (content or "").strip()[:2000] or "（空消息）",
        },
    }
    if mention_all:
        payload["text"]["mentioned_list"] = ["@all"]
    try:
        response = requests.post(
            config.webhook_url.strip(),
            json=payload,
            timeout=10,
        )
    except Exception as exc:
        logger.exception("WeCom webhook request failed")
        raise WecomNotifyError(f"企业微信请求失败：{exc}") from exc
    if response.status_code != 200:
        raise WecomNotifyError(f"企业微信 HTTP {response.status_code}")
    try:
        data = response.json()
    except Exception as exc:
        raise WecomNotifyError("企业微信返回了无法解析的响应。") from exc
    if int(data.get("errcode") or 0) != 0:
        raise WecomNotifyError(
            f"企业微信返回错误：{data.get('errmsg') or data.get('errcode')}"
        )
    return True


def notify_wecom_if_enabled(kind, content, *, mention_all=False):
    """Fire-and-forget admin alert. Returns True when a message was accepted."""
    config = _config()
    if not config.is_configured:
        return False
    allowed = {
        "remote_login": config.notify_remote_login,
        "admin_login": config.notify_admin_login,
        "build_failure": config.notify_build_failure,
        "build_success": getattr(config, "notify_build_success", False),
        "test": True,
    }
    if not allowed.get(kind, False):
        return False
    try:
        send_wecom_text(content, config=config, mention_all=mention_all)
        return True
    except WecomNotifyError:
        logger.exception("WeCom notify skipped for kind=%s", kind)
        return False
    except Exception:
        logger.exception("Unexpected WeCom notify failure for kind=%s", kind)
        return False


def format_remote_login_alert(*, user, previous, current):
    when = timezone.localtime(current.created_at).strftime("%Y-%m-%d %H:%M:%S")
    entry = "超管后台" if current.is_admin else "前台"
    return (
        "【异地登录提醒】\n"
        f"账号：{getattr(user, 'username', '')}\n"
        f"入口：{entry}\n"
        f"上次 IP：{previous.ip_address}\n"
        f"本次 IP：{current.ip_address}\n"
        f"时间：{when}"
    )


def format_admin_login_alert(*, user, request_ip):
    when = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S")
    return (
        "【超管登录】\n"
        f"账号：{getattr(user, 'username', '')}\n"
        f"IP：{request_ip or '未知'}\n"
        f"时间：{when}"
    )


def format_build_failure_alert(*, run):
    owner = getattr(getattr(run, "owner", None), "username", None) or "已删除账号"
    when = timezone.localtime(run.created_at).strftime("%Y-%m-%d %H:%M:%S") if run.created_at else "-"
    return (
        "【构建失败】\n"
        f"用户：{owner}\n"
        f"平台：{run.platform or '未知'}\n"
        f"状态：{run.status}\n"
        f"UUID：{run.uuid}\n"
        f"GitHub Run：{run.github_run_id or '-'}\n"
        f"提交时间：{when}"
    )


def format_build_success_alert(*, run, filenames=None):
    owner = getattr(getattr(run, "owner", None), "username", None) or "已删除账号"
    when = timezone.localtime(run.created_at).strftime("%Y-%m-%d %H:%M:%S") if run.created_at else "-"
    files = [str(name) for name in (filenames or []) if name]
    file_line = "、".join(files[:5]) if files else "（已回传）"
    if len(files) > 5:
        file_line += f" 等 {len(files)} 个"
    return (
        "【构建成功】\n"
        f"用户：{owner}\n"
        f"平台：{run.platform or '未知'}\n"
        f"UUID：{run.uuid}\n"
        f"文件：{file_line}\n"
        f"提交时间：{when}"
    )
