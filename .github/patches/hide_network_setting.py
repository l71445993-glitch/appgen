from __future__ import annotations

from pathlib import Path


ROOT = Path.cwd()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"{label} is already patched.")
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Unable to patch {label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def patch_flutter_settings() -> None:
    path = ROOT / "flutter/lib/desktop/pages/desktop_setting_page.dart"
    text = path.read_text(encoding="utf-8")
    marker = "    // Generator policy: hide the Network settings tab.\n"
    block = """    if (!bind.isDisableSettings() &&
        bind.mainGetBuildinOption(key: kOptionHideNetworkSetting) != 'Y')
      SettingsTabKey.network,
"""
    if marker in text:
        print("Flutter Network tab is already hidden.")
    elif block in text:
        text = text.replace(block, marker, 1)
        path.write_text(text, encoding="utf-8")
        print("Removed the Network tab from Flutter desktop settings.")
    else:
        raise SystemExit("Could not find the expected Flutter Network tab block")


def patch_sciter_settings() -> None:
    path = ROOT / "src/ui/index.tis"
    text = path.read_text(encoding="utf-8")
    old = """const hide_server_settings = handler.get_builtin_option("hide-server-settings") == "Y";
const hide_proxy_settings = handler.get_builtin_option("hide-proxy-settings") == "Y";
const hide_websocket_settings = handler.get_builtin_option("hide-websocket-settings") == "Y";
"""
    new = """const hide_network_setting = handler.get_builtin_option("hide-network-setting") == "Y";
const hide_server_settings = hide_network_setting || handler.get_builtin_option("hide-server-settings") == "Y";
const hide_proxy_settings = hide_network_setting || handler.get_builtin_option("hide-proxy-settings") == "Y";
const hide_websocket_settings = hide_network_setting || handler.get_builtin_option("hide-websocket-settings") == "Y";
"""
    text = replace_once(text, old, new, "Sciter network setting flags")
    text = replace_once(
        text,
        """                {!disable_settings && !using_public_server && !outgoing_only && <li #disable-udp class={disable_udp ? "selected" : "line-through"}><span>{svg_checkmark}</span>{translate('Disable UDP')}</li>}
                {!disable_settings && !using_public_server && <li #allow-insecure-tls-fallback><span>{svg_checkmark}</span>{translate('Allow insecure TLS fallback')}</li>}
""",
        """                {!disable_settings && !hide_network_setting && !using_public_server && !outgoing_only && <li #disable-udp class={disable_udp ? "selected" : "line-through"}><span>{svg_checkmark}</span>{translate('Disable UDP')}</li>}
                {!disable_settings && !hide_network_setting && !using_public_server && <li #allow-insecure-tls-fallback><span>{svg_checkmark}</span>{translate('Allow insecure TLS fallback')}</li>}
""",
        "Sciter UDP and TLS network menu items",
    )
    text = replace_once(
        text,
        "                {!disable_settings && <DirectServer />}\n",
        "                {!disable_settings && !hide_network_setting && <DirectServer />}\n",
        "Sciter direct server network menu item",
    )
    path.write_text(text, encoding="utf-8")
    print("Hidden network controls from Sciter settings.")


def main() -> None:
    patch_flutter_settings()
    patch_sciter_settings()


if __name__ == "__main__":
    main()
