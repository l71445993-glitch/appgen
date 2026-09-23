"""Force the Windows MSI installer UI to Simplified Chinese (zh-CN).

RustDesk ships only en-us WiX localizations. This patch:

1. Rewrites Package.en-us.wxl into a zh-cn localization with Chinese
   product / custom-dialog strings and ProductLanguage 2052.
2. Drops in the official WixUI_zh-CN.wxl (Next/Back/Cancel, Welcome, …).
3. Translates WixExt firewall strings and switches them to zh-cn.
4. Pins Package.wixproj Cultures=zh-cn so the build emits zh-cn/Package.msi.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from xml.dom import minidom
from xml.parsers.expat import ExpatError


UTF8_CODEPAGE = "65001"
SUMMARY_CODEPAGE = "1252"
PRODUCT_LANGUAGE_ZH_CN = "2052"
CULTURE = "zh-cn"

PACKAGE_WXL = Path("res/msi/Package/Language/Package.en-us.wxl")
WIXEXT_WXL = Path("res/msi/Package/Language/WixExt_en-us.wxl")
WIXUI_DEST = Path("res/msi/Package/Language/WixUI_zh-CN.wxl")
PACKAGE_WIXPROJ = Path("res/msi/Package/Package.wixproj")

# Bundled next to this script when downloaded by the workflow, or under patches/msi.
WIXUI_CANDIDATES = (
    Path("WixUI_zh-CN.wxl"),
    Path(".github/patches/msi/WixUI_zh-CN.wxl"),
    Path(__file__).resolve().parent / "msi" / "WixUI_zh-CN.wxl",
    Path(__file__).resolve().parent / "WixUI_zh-CN.wxl",
)

PACKAGE_STRINGS = {
    "SummaryCodepage": SUMMARY_CODEPAGE,
    "ProductLanguage": PRODUCT_LANGUAGE_ZH_CN,
    "DowngradeError": "已安装更新版本的 [ProductName]。",
    "AR_Comment": "[ProductName]",
    "F_App": "[ProductName]",
    "F_App_Desc": "[ProductName] 主程序。",
    "SC_Uninstall": "卸载 [ProductName]",
    "SC_Uninstall_Desc": "从计算机中移除 [ProductName] 或其组件",
    "F_Client": "客户端",
    "F_Client_Desc": "用户界面。",
    "F_LAVFilters": "LAV Filters",
    "F_LAVFilters_Desc": "推荐的 DirectShow 筛选器，用于更好的音视频播放体验。",
    "SC_Client": "[ProductName]",
    "SC_Client_Desc": "启动 [ProductName]。",
    "SC_Client_Tray": "[ProductName] 托盘",
    "SC_Client_Tray_Desc": "启动 [ProductName] 托盘。",
    "F_Server": "服务",
    "F_Server_Desc": "[ProductName] 服务端组件。",
    "Service_DisplayName": "[ProductName] 服务",
    "Service_Description": "此服务用于运行 [ProductName]。",
    "LC_OS": "[ProductName] 需要 Windows 7 / 2008 R2 或更高版本。",
    "LC_ADMIN": "需要管理员权限才能安装 [ProductName]。",
    "AnotherAppDialogTitle": "取消安装",
    "AnotherAppDialogDescription": "检测到已通过自解压方式安装的应用程序，请先卸载后再继续。",
    "MyInstallDirDlgDesktopShortcuts": "创建桌面图标",
    "MyInstallDirDlgStartMenuShortcuts": "创建开始菜单快捷方式",
    "MyInstallDirDlgPrinter": "安装 [ProductName] 打印机",
}

WIXEXT_STRINGS = {
    "msierrFirewallCannotConnect": "无法连接到 Windows 防火墙。([2]   [3]   [4]   [5])",
    "WixSchedFirewallExceptionsInstall": "正在配置 Windows 防火墙",
    "WixSchedFirewallExceptionsUninstall": "正在配置 Windows 防火墙",
    "WixRollbackFirewallExceptionsInstall": "正在回滚 Windows 防火墙配置",
    "WixExecFirewallExceptionsInstall": "正在安装 Windows 防火墙配置",
    "WixRollbackFirewallExceptionsUninstall": "正在回滚 Windows 防火墙配置",
    "WixExecFirewallExceptionsUninstall": "正在卸载 Windows 防火墙配置",
    "msierrSecureObjectsFailedCreateSD": "无法创建安全描述符 [3]\\[4]，错误：[2]",
    "msierrSecureObjectsFailedSet": "无法应用对象安全描述符 [3]，错误：[2]",
    "msierrSecureObjectsUnknownType": "未知对象类型 [3]，错误：[2]",
}


def _load_xml(path: Path) -> minidom.Document:
    if not path.is_file():
        raise SystemExit(f"Required MSI source file is missing: {path}")
    try:
        return minidom.parse(str(path))
    except (OSError, ExpatError) as exc:
        raise SystemExit(f"Unable to parse MSI XML file {path}: {exc}") from exc


def _write_xml(document: minidom.Document, path: Path) -> None:
    temporary_path = path.with_name(f"{path.name}.rdgen.tmp")
    try:
        temporary_path.write_bytes(document.toxml(encoding="utf-8"))
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _set_localization_culture(document: minidom.Document) -> None:
    root = document.documentElement
    if root is None or root.localName != "WixLocalization":
        raise SystemExit("Expected a WixLocalization root element")
    root.setAttribute("Culture", CULTURE)
    root.setAttribute("Codepage", UTF8_CODEPAGE)
    # Keep summary metadata ANSI-safe for Explorer details pane.
    root.setAttribute("SummaryInformationCodepage", SUMMARY_CODEPAGE)


def _upsert_strings(document: minidom.Document, values: dict[str, str]) -> int:
    changed = 0
    root = document.documentElement
    by_id: dict[str, any] = {}
    for element in document.getElementsByTagName("*"):
        if element.localName != "String":
            continue
        string_id = element.getAttribute("Id")
        if string_id:
            by_id[string_id] = element

    for string_id, value in values.items():
        element = by_id.get(string_id)
        if element is None:
            element = document.createElement("String")
            element.setAttribute("Id", string_id)
            element.setAttribute("Value", value)
            element.setAttribute("Overridable", "yes")
            root.appendChild(document.createTextNode("\n\t"))
            root.appendChild(element)
            changed += 1
            continue
        if element.getAttribute("Value") != value:
            element.setAttribute("Value", value)
            changed += 1
        if not element.hasAttribute("Overridable"):
            element.setAttribute("Overridable", "yes")
            changed += 1
    return changed


def _find_wixui_source(root: Path) -> Path:
    for candidate in WIXUI_CANDIDATES:
        path = candidate if candidate.is_absolute() else root / candidate
        if path.is_file():
            return path
    raise SystemExit(
        "WixUI_zh-CN.wxl not found. Place it next to this script or under "
        ".github/patches/msi/WixUI_zh-CN.wxl"
    )


def _install_wixui(root: Path) -> bool:
    source = _find_wixui_source(root)
    destination = root / WIXUI_DEST
    text = source.read_text(encoding="utf-8-sig")
    # Normalize culture/codepage so it merges cleanly with our Package.wxl.
    text = re.sub(
        r'<WixLocalization\b[^>]*>',
        f'<WixLocalization Culture="{CULTURE}" Codepage="{UTF8_CODEPAGE}" '
        f'SummaryInformationCodepage="{SUMMARY_CODEPAGE}" '
        'xmlns="http://wixtoolset.org/schemas/v4/wxl">',
        text,
        count=1,
    )
    previous = destination.read_text(encoding="utf-8") if destination.is_file() else None
    if previous == text:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(text.encode("utf-8"))
    print(f"Installed {destination} from {source}")
    return True


def _pin_cultures(root: Path) -> bool:
    path = root / PACKAGE_WIXPROJ
    if not path.is_file():
        raise SystemExit(f"Required MSI project is missing: {path}")
    text = path.read_text(encoding="utf-8-sig")
    if re.search(r"<Cultures>\s*zh-cn\s*</Cultures>", text, flags=re.I):
        return False
    if "<Cultures>" in text:
        updated = re.sub(
            r"<Cultures>.*?</Cultures>",
            f"<Cultures>{CULTURE}</Cultures>",
            text,
            count=1,
            flags=re.I | re.S,
        )
    else:
        updated = text.replace(
            "<PropertyGroup>",
            f"<PropertyGroup>\n    <Cultures>{CULTURE}</Cultures>",
            1,
        )
    if updated == text:
        raise SystemExit(f"Unable to pin Cultures={CULTURE} in {path}")
    path.write_bytes(updated.encode("utf-8"))
    print(f"Pinned Cultures={CULTURE} in {path}")
    return True


def configure_msi_zh_cn(root: Path) -> bool:
    package_path = root / PACKAGE_WXL
    wixext_path = root / WIXEXT_WXL

    package_document = _load_xml(package_path)
    _set_localization_culture(package_document)
    package_changes = _upsert_strings(package_document, PACKAGE_STRINGS)
    if package_changes:
        _write_xml(package_document, package_path)
        print(f"Updated {package_path} with {package_changes} Chinese string(s).")

    wixext_changes = 0
    if wixext_path.is_file():
        wixext_document = _load_xml(wixext_path)
        _set_localization_culture(wixext_document)
        wixext_changes = _upsert_strings(wixext_document, WIXEXT_STRINGS)
        if wixext_changes:
            _write_xml(wixext_document, wixext_path)
            print(f"Updated {wixext_path} with {wixext_changes} Chinese string(s).")

    wixui_changed = _install_wixui(root)
    cultures_changed = _pin_cultures(root)
    changed = bool(package_changes or wixext_changes or wixui_changed or cultures_changed)
    if not changed:
        print("Windows MSI sources already use Simplified Chinese UI.")
    else:
        print("Configured Windows MSI installer UI for Simplified Chinese (zh-CN).")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    configure_msi_zh_cn(args.root.resolve())


if __name__ == "__main__":
    main()
