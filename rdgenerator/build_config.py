"""Persist and present the customer-facing generator configuration."""

from __future__ import annotations

from copy import deepcopy


SNAPSHOT_VERSION = 1


def build_config_snapshot(
    *,
    form_data,
    decoded_custom,
    effective,
):
    """Build a JSON-serializable snapshot of one generation request.

    ``effective`` holds the post-normalization values actually sent to CI
    (servers, filename, feature flags after platform gates, etc.).
    """
    custom = deepcopy(decoded_custom) if isinstance(decoded_custom, dict) else {}
    return {
        "version": SNAPSHOT_VERSION,
        "basic": {
            "platform": effective.get("platform"),
            "version": effective.get("version"),
            "appname": effective.get("appname"),
            "exename": effective.get("filename"),
            "compname": effective.get("compname"),
            "androidappid": effective.get("androidappid"),
            "direction": effective.get("direction"),
            "installation": effective.get("installation"),
            "settings": effective.get("settings"),
        },
        "servers": {
            "serverIP": effective.get("server"),
            "relayServer": effective.get("relayServer"),
            "apiServer": effective.get("apiServer"),
            "key": effective.get("key"),
            "smartMultiRelay": bool(effective.get("smartMultiRelay")),
            "beijingCustom": bool(effective.get("beijingCustom")),
        },
        "branding": {
            "urlLink": effective.get("urlLink"),
            "downloadLink": effective.get("downloadLink"),
            "hasIcon": bool(effective.get("hasIcon")),
            "hasLogo": bool(effective.get("hasLogo")),
            "hasPrivacyImage": bool(effective.get("hasPrivacyImage")),
        },
        "security": {
            "permanentPassword": effective.get("permPass") or "",
            "passApproveMode": effective.get("passApproveMode"),
            "hidecm": bool(effective.get("hidecm")),
            "hidecmDefaultEnabled": bool(effective.get("hidecmDefaultEnabled")),
            "silentAgentMode": bool(effective.get("silentAgentMode")),
            "denyLan": bool(effective.get("denyLan")),
            "enableDirectIP": bool(effective.get("enableDirectIP")),
        },
        "ui": {
            "theme": effective.get("theme"),
            "themeDorO": effective.get("themeDorO"),
            "defaultViewStyle": effective.get("defaultViewStyle"),
            "hideNetworkSetting": bool(effective.get("hideNetworkSetting")),
            "hideSettingsMenu": bool(effective.get("hideSettingsMenu")),
            "hideTray": bool(effective.get("hideTray")),
            "removeSetupServerTip": bool(effective.get("removeSetupServerTip")),
            "removeNewVersionNotif": bool(effective.get("removeNewVersionNotif")),
            "removeRecentSessions": bool(effective.get("removeRecentSessions")),
            "incomingCompactMode": bool(effective.get("incomingCompactMode")),
            "incomingContentWidth": effective.get("incomingContentWidth"),
            "incomingContentHeight": effective.get("incomingContentHeight"),
            "copyIdPasswordButton": bool(effective.get("copyIdPasswordButton")),
            "manualTemporaryPassword": bool(effective.get("manualTemporaryPassword")),
            "showStartOnBootCheckbox": bool(effective.get("showStartOnBootCheckbox")),
            "defaultStartOnBoot": bool(effective.get("defaultStartOnBoot")),
            "sloganText": effective.get("sloganText") or "",
            "macosBundleId": effective.get("macosBundleId") or "",
            "defaultImageQuality": effective.get("defaultImageQuality") or "",
            "defaultCodec": effective.get("defaultCodec") or "",
            "preferWebsocket": bool(effective.get("preferWebsocket")),
            "sessionIdleMinutes": effective.get("sessionIdleMinutes"),
            "allowIdPrefixes": effective.get("allowIdPrefixes") or "",
            "msiDesktopShortcut": effective.get("msiDesktopShortcut") or "default",
            "msiStartMenuShortcut": effective.get("msiStartMenuShortcut") or "default",
            "msiInstallPrinter": effective.get("msiInstallPrinter") or "off",
        },
        "permissions": {
            "permissionsDorO": effective.get("permissionsDorO"),
            "permissionsType": effective.get("permissionsType"),
            "enableKeyboard": bool(effective.get("enableKeyboard")),
            "enableClipboard": bool(effective.get("enableClipboard")),
            "enableFileCopyPaste": bool(effective.get("enableFileCopyPaste")),
            "enableFileTransfer": bool(effective.get("enableFileTransfer")),
            "forceDisableFileTransfer": bool(effective.get("forceDisableFileTransfer")),
            "enableAudio": bool(effective.get("enableAudio")),
            "enableTCP": bool(effective.get("enableTCP")),
            "enableRemoteRestart": bool(effective.get("enableRemoteRestart")),
            "enableRecording": bool(effective.get("enableRecording")),
            "enableBlockingInput": bool(effective.get("enableBlockingInput")),
            "enableRemoteModi": bool(effective.get("enableRemoteModi")),
            "enablePrinter": bool(effective.get("enablePrinter")),
            "enableCamera": bool(effective.get("enableCamera")),
            "enableTerminal": bool(effective.get("enableTerminal")),
            "removeWallpaper": bool(effective.get("removeWallpaper")),
            "autoClose": bool(effective.get("autoClose")),
        },
        "build_options": {
            "delayFix": bool(effective.get("delayFix")),
            "cycleMonitor": bool(effective.get("cycleMonitor")),
            "xOffline": bool(effective.get("xOffline")),
            "silentInstallOnDoubleClick": bool(
                effective.get("silentInstallOnDoubleClick")
            ),
            "selfhosted": bool(effective.get("selfhosted")),
            "linuxCustomAllowed": bool(effective.get("linuxCustomAllowed")),
        },
        "delivery": {
            "download_access": effective.get("download_access"),
            "download_ttl_hours": effective.get("download_ttl_hours"),
        },
        "manual": {
            "defaultManual": (form_data.get("defaultManual") or "").strip(),
            "overrideManual": (form_data.get("overrideManual") or "").strip(),
        },
        "custom_client": custom,
    }


BOOL_LABELS = {
    True: "是",
    False: "否",
}

FIELD_LABELS = {
    "platform": "平台",
    "version": "RustDesk 版本",
    "appname": "应用名称",
    "exename": "产物文件名",
    "compname": "公司名称",
    "androidappid": "Android 包名",
    "direction": "连接方向",
    "installation": "安装能力",
    "settings": "设置入口",
    "serverIP": "ID 服务器（hbbs）",
    "relayServer": "中继服务器（hbbr）",
    "apiServer": "API 服务器",
    "key": "密钥（公钥 Key）",
    "smartMultiRelay": "智能多中继",
    "beijingCustom": "北京 Linux 定制",
    "urlLink": "主页链接",
    "downloadLink": "下载链接",
    "hasIcon": "自定义图标",
    "hasLogo": "自定义 Logo",
    "hasPrivacyImage": "隐私屏图片",
    "permanentPassword": "固定密码",
    "passApproveMode": "连接审批方式",
    "hidecm": "隐藏连接窗口",
    "hidecmDefaultEnabled": "默认隐藏连接窗口",
    "silentAgentMode": "静默代理模式",
    "denyLan": "禁止局域网发现",
    "enableDirectIP": "允许直连 IP",
    "theme": "主题",
    "themeDorO": "主题默认/覆盖",
    "defaultViewStyle": "默认显示方式",
    "hideNetworkSetting": "隐藏网络设置",
    "hideSettingsMenu": "隐藏设置菜单",
    "hideTray": "隐藏托盘",
    "removeSetupServerTip": "移除服务器设置提示",
    "removeNewVersionNotif": "移除新版本提示",
    "removeRecentSessions": "移除最近会话",
    "incomingCompactMode": "仅被控紧凑布局",
    "incomingContentWidth": "紧凑布局宽度",
    "incomingContentHeight": "紧凑布局高度",
    "copyIdPasswordButton": "复制 ID/密码按钮",
    "manualTemporaryPassword": "手动临时密码",
    "showStartOnBootCheckbox": "开机启动勾选",
    "defaultStartOnBoot": "默认开机自启",
    "sloganText": "关于页 Slogan",
    "macosBundleId": "macOS Bundle ID",
    "defaultImageQuality": "默认画质",
    "defaultCodec": "默认编码",
    "preferWebsocket": "优先 WebSocket",
    "sessionIdleMinutes": "会话空闲超时(分)",
    "allowIdPrefixes": "允许的 ID 前缀",
    "msiDesktopShortcut": "安装桌面图标默认",
    "msiStartMenuShortcut": "安装开始菜单默认",
    "msiInstallPrinter": "安装打印机默认",
    "permissionsDorO": "权限默认/覆盖",
    "permissionsType": "权限类型",
    "enableKeyboard": "键盘",
    "enableClipboard": "剪贴板",
    "enableFileCopyPaste": "文件复制粘贴",
    "enableFileTransfer": "文件传输",
    "forceDisableFileTransfer": "强制禁用文件传输",
    "enableAudio": "音频",
    "enableTCP": "TCP 隧道",
    "enableRemoteRestart": "远程重启",
    "enableRecording": "会话录制",
    "enableBlockingInput": "屏蔽输入",
    "enableRemoteModi": "允许远程改配置",
    "enablePrinter": "打印机",
    "enableCamera": "摄像头",
    "enableTerminal": "终端",
    "removeWallpaper": "移除壁纸",
    "autoClose": "自动断开",
    "delayFix": "延迟修复",
    "cycleMonitor": "循环显示器",
    "xOffline": "离线增强",
    "silentInstallOnDoubleClick": "双击静默安装",
    "selfhosted": "自托管构建机",
    "linuxCustomAllowed": "允许 Linux 深度定制",
    "download_access": "下载访问",
    "download_ttl_hours": "下载有效小时",
    "defaultManual": "默认设置手工项",
    "overrideManual": "覆盖设置手工项",
}

DIRECTION_LABELS = {
    "both": "双向",
    "incoming": "仅被控",
    "outgoing": "仅主控",
}
INSTALL_LABELS = {
    "installationY": "允许安装",
    "installationN": "禁用安装",
}
SETTINGS_LABELS = {
    "settingsY": "保留设置入口",
    "settingsN": "隐藏设置入口",
}
DOWNLOAD_ACCESS_LABELS = {
    "login": "登录后下载",
    "public": "公开链接下载",
}


def _format_value(key, value, *, reveal_secrets):
    if key == "permanentPassword":
        text = str(value or "")
        if not text:
            return "（未设置）"
        if reveal_secrets:
            return text
        if len(text) <= 2:
            return "*" * len(text)
        return text[0] + ("*" * (len(text) - 2)) + text[-1]
    if key == "key" and value and not reveal_secrets:
        text = str(value)
        if len(text) <= 8:
            return text[:2] + "***"
        return text[:4] + "…" + text[-4:]
    if isinstance(value, bool):
        return BOOL_LABELS[value]
    if key == "direction":
        return DIRECTION_LABELS.get(value, value or "—")
    if key == "installation":
        return INSTALL_LABELS.get(value, value or "—")
    if key == "settings":
        return SETTINGS_LABELS.get(value, value or "—")
    if key == "download_access":
        return DOWNLOAD_ACCESS_LABELS.get(value, value or "—")
    if value in (None, ""):
        return "—"
    return str(value)


SECTION_TITLES = (
    ("basic", "基础信息"),
    ("servers", "服务器与中继"),
    ("branding", "品牌与链接"),
    ("security", "安全与连接"),
    ("ui", "界面与交互"),
    ("permissions", "权限开关"),
    ("build_options", "构建选项"),
    ("delivery", "交付策略"),
    ("manual", "手工覆盖项"),
)


def config_display_sections(snapshot, *, reveal_secrets=False):
    if not isinstance(snapshot, dict) or not snapshot:
        return []
    sections = []
    for key, title in SECTION_TITLES:
        raw = snapshot.get(key) or {}
        if not isinstance(raw, dict) or not raw:
            continue
        rows = []
        for field, value in raw.items():
            if key == "manual" and not (value or "").strip():
                continue
            rows.append(
                {
                    "label": FIELD_LABELS.get(field, field),
                    "value": _format_value(field, value, reveal_secrets=reveal_secrets),
                }
            )
        if rows:
            sections.append({"title": title, "rows": rows})

    custom = snapshot.get("custom_client") or {}
    if isinstance(custom, dict) and custom:
        flat_rows = []
        for ckey, cval in custom.items():
            if ckey in {"default-settings", "override-settings"} and isinstance(cval, dict):
                for nested_key, nested_val in cval.items():
                    flat_rows.append(
                        {
                            "label": f"{ckey} / {nested_key}",
                            "value": _format_value(
                                nested_key,
                                nested_val,
                                reveal_secrets=reveal_secrets,
                            ),
                        }
                    )
            else:
                flat_rows.append(
                    {
                        "label": ckey,
                        "value": _format_value(
                            ckey,
                            cval,
                            reveal_secrets=reveal_secrets,
                        ),
                    }
                )
        if flat_rows:
            sections.append({"title": "写入客户端的 custom 配置", "rows": flat_rows})
    return sections
