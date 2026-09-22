from pathlib import Path


ROOT = Path.cwd()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"Could not find {label}")
    return text.replace(old, new, 1)


def uncomment_block(text: str, inner: str, label: str) -> str:
    commented = f"    /*\n{inner}    */"
    if inner in text and commented not in text:
        return text
    return replace_once(text, commented, inner, label)


def patch_settings_page() -> None:
    path = ROOT / "flutter/lib/desktop/pages/desktop_setting_page.dart"
    text = path.read_text(encoding="utf-8")
    changed = False
    if "hide_cm(!locked).marginOnly" in text and "//   hide_cm(!locked)" not in text:
        print("Safety settings already show hide_cm.")
    else:
        old = """            // if (usePassword)
            //   hide_cm(!locked).marginOnly(left: _kContentHSubMargin - 6),
"""
        new = """            if (usePassword)
              hide_cm(!locked).marginOnly(left: _kContentHSubMargin - 6),
"""
        text = replace_once(text, old, new, "hide_cm settings toggle")
        changed = True
        print("Enabled hide_cm in safety settings.")

    old_persistence = (
        "key: 'allow-hide-cm', value: bool2option('allow-hide-cm', b));"
    )
    new_persistence = "key: 'allow-hide-cm', value: b ? 'Y' : 'N');"
    if old_persistence in text:
        text = replace_exactly_once(
            text,
            old_persistence,
            new_persistence,
            "Flutter allow-hide-cm toggle persistence",
        )
        changed = True
    elif new_persistence not in text:
        raise SystemExit("Could not find Flutter allow-hide-cm toggle persistence")
    if changed:
        path.write_text(text, encoding="utf-8")
    print("Flutter allow-hide-cm writes explicit Y/N values.")


def replace_exactly_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected one {label}, found {count}")
    return text.replace(old, new, 1)


def patch_sciter_settings_page() -> None:
    path = ROOT / "src/ui/index.tis"
    text = path.read_text(encoding="utf-8")
    changed = False
    migrations = (
        (
            "handler.set_option('allow-hide-cm', default_option_no);",
            "handler.set_option('allow-hide-cm', 'N');",
        ),
        (
            "'allow-hide-cm', enabled ? default_option_no : 'Y');",
            "'allow-hide-cm', enabled ? 'N' : 'Y');",
        ),
    )
    for old, new in migrations:
        if old in text:
            text = replace_exactly_once(
                text,
                old,
                new,
                "legacy Sciter allow-hide-cm persistence",
            )
            changed = True
    markers = (
        "<li #allow-hide-cm ",
        "var can_hide_cm = mode == 'password' &&",
        "function resetHideCmIfUnavailable()",
        "if (me.id == 'allow-hide-cm')",
        "handler.set_option('allow-hide-cm', 'N');",
        "'allow-hide-cm', enabled ? 'N' : 'Y');",
    )
    present = tuple(marker in text for marker in markers)
    if all(present):
        if changed:
            path.write_text(text, encoding="utf-8")
        print("Sciter password settings already show allow-hide-cm.")
        return
    if any(present):
        raise SystemExit("Sciter allow-hide-cm patch is only partially applied")

    old_menu = """            { !show_password ? '' : <li #use-both-passwords><span>{svg_checkmark}</span>{translate('Use both passwords')}</li> }
            { !show_password ? '' : <div .separator /> }
"""
    new_menu = """            { !show_password ? '' : <li #use-both-passwords><span>{svg_checkmark}</span>{translate('Use both passwords')}</li> }
            <li #allow-hide-cm title={translate('hide_cm_tip')}><span>{svg_checkmark}</span>{translate('Hide connection management window')}</li>
            { !show_password ? '' : <div .separator /> }
"""
    text = replace_exactly_once(
        text,
        old_menu,
        new_menu,
        "Sciter password-menu insertion point",
    )

    old_state = """        var has_valid_2fa = handler.has_valid_2fa();
        for (var el in this.$$(menu#edit-password-context>li)) {
"""
    new_state = """        var has_valid_2fa = handler.has_valid_2fa();
        var allow_hide_cm = handler.get_option('allow-hide-cm') == 'Y';
        var can_hide_cm = mode == 'password' &&
            pwd_id == 'use-permanent-password';
        for (var el in this.$$(menu#edit-password-context>li)) {
"""
    text = replace_exactly_once(
        text,
        old_state,
        new_state,
        "Sciter password-menu state insertion point",
    )

    old_toggle = """            if (el.id == "clear-password") {
                var has_local_password = handler.is_local_permanent_password_set();
                el.state.disabled = !has_local_password;
            }
            if (el.id == "tfa")
"""
    new_toggle = """            if (el.id == "clear-password") {
                var has_local_password = handler.is_local_permanent_password_set();
                el.state.disabled = !has_local_password;
            }
            if (el.id == "allow-hide-cm") {
                el.attributes.toggleClass("selected", can_hide_cm && allow_hide_cm);
                el.state.disabled = !can_hide_cm ||
                    handler.is_option_fixed('allow-hide-cm');
            }
            if (el.id == "tfa")
"""
    text = replace_exactly_once(
        text,
        old_toggle,
        new_toggle,
        "Sciter allow-hide-cm state block",
    )

    text = replace_exactly_once(
        text,
        "    event click $(svg#edit) (_, me) {\n",
        """    function resetHideCmIfUnavailable() {
        if (handler.get_option('approve-mode') != 'password' ||
            handler.get_option('verification-method') != 'use-permanent-password') {
            handler.set_option('allow-hide-cm', 'N');
        }
    }

    event click $(svg#edit) (_, me) {
""",
        "Sciter hide-cm reset helper insertion point",
    )

    old_click_handler = """    event click $(menu#edit-password-context>li) (_, me) {
        if (me.state.disabled) return;
        if (me.id.indexOf('use-') == 0) {
            handler.set_option('verification-method', me.id);
            this.toggleMenuState();
            passwordArea.update();
        } else if (me.id.indexOf('approve-mode') == 0) {
            var approve_mode;
            if (me.id == 'approve-mode-password')
                approve_mode = 'password';
            else if (me.id == 'approve-mode-click')
                approve_mode = 'click';
            else
                approve_mode = default_option_approve_mode;
            handler.set_option('approve-mode', approve_mode);
            this.toggleMenuState();
            passwordArea.update();
        }
    }
"""
    new_click_handler = """    event click $(menu#edit-password-context>li) (_, me) {
        if (me.state.disabled) return;
        if (me.id == 'allow-hide-cm') {
            var enabled = handler.get_option('allow-hide-cm') == 'Y';
            handler.set_option(
                'allow-hide-cm', enabled ? 'N' : 'Y');
            this.toggleMenuState();
        } else if (me.id.indexOf('use-') == 0) {
            handler.set_option('verification-method', me.id);
            this.resetHideCmIfUnavailable();
            this.toggleMenuState();
            passwordArea.update();
        } else if (me.id.indexOf('approve-mode') == 0) {
            var approve_mode;
            if (me.id == 'approve-mode-password')
                approve_mode = 'password';
            else if (me.id == 'approve-mode-click')
                approve_mode = 'click';
            else
                approve_mode = default_option_approve_mode;
            handler.set_option('approve-mode', approve_mode);
            this.resetHideCmIfUnavailable();
            this.toggleMenuState();
            passwordArea.update();
        }
    }
"""
    text = replace_exactly_once(
        text,
        old_click_handler,
        new_click_handler,
        "Sciter password-menu click handler",
    )
    path.write_text(text, encoding="utf-8")
    print("Enabled allow-hide-cm in Sciter password settings.")


def patch_main() -> None:
    path = ROOT / "flutter/lib/main.dart"
    text = path.read_text(encoding="utf-8")
    if "// gFFI.serverModel.hideCm = hide;" in text:
        print("Connection manager startup already leaves model hideCm untouched.")
        return
    path.write_text(
        replace_once(
            text,
            "  gFFI.serverModel.hideCm = hide;\n",
            "  // gFFI.serverModel.hideCm = hide;\n",
            "connection manager hideCm assignment",
        ),
        encoding="utf-8",
    )
    print("Adjusted connection manager startup hideCm handling.")


def patch_server_model() -> None:
    path = ROOT / "flutter/lib/models/server_model.dart"
    text = path.read_text(encoding="utf-8")
    if "bool hideCm = false;" in text:
        text = text.replace("  bool hideCm = false;\n", "  bool _hideCm = false;\n", 1)
    if "bool get hideCm => _hideCm;" not in text:
        text = replace_once(
            text,
            "  bool get clipboardOk => _clipboardOk;\n\n",
            "  bool get clipboardOk => _clipboardOk;\n\n  bool get hideCm => _hideCm;\n\n",
            "hideCm getter insertion point",
        )

    old_reset = (
        "key: 'allow-hide-cm', value: bool2option('allow-hide-cm', false));"
    )
    new_reset = "key: 'allow-hide-cm', value: 'N');"
    old_reset_count = text.count(old_reset)
    new_reset_count = text.count(new_reset)
    if old_reset_count:
        if old_reset_count != 2:
            raise SystemExit(
                f"Expected two legacy Flutter hide_cm resets, found {old_reset_count}"
            )
        text = text.replace(old_reset, new_reset)
    elif new_reset_count != 2:
        raise SystemExit(
            f"Expected two explicit Flutter hide_cm resets, found {new_reset_count}"
        )

    text = uncomment_block(
        text,
        """    if (method != kUsePermanentPassword) {
      await bind.mainSetOption(
          key: 'allow-hide-cm', value: 'N');
    }
""",
        "verification method hide_cm reset block",
    )
    text = uncomment_block(
        text,
        """    if (mode != 'password') {
      await bind.mainSetOption(
          key: 'allow-hide-cm', value: 'N');
    }
""",
        "approve mode hide_cm reset block",
    )
    text = uncomment_block(
        text,
        """    // initital _hideCm at startup
    final verificationMethod =
        bind.mainGetOptionSync(key: kOptionVerificationMethod);
    final approveMode = bind.mainGetOptionSync(key: kOptionApproveMode);
    _hideCm = option2bool(
        'allow-hide-cm', bind.mainGetOptionSync(key: 'allow-hide-cm'));
    if (!(approveMode == 'password' &&
        verificationMethod == kUsePermanentPassword)) {
      _hideCm = false;
    }
""",
        "initial hide_cm block",
    )
    text = uncomment_block(
        text,
        """    var hideCm = option2bool(
        'allow-hide-cm', await bind.mainGetOption(key: 'allow-hide-cm'));
    if (!(approveMode == 'password' &&
        verificationMethod == kUsePermanentPassword)) {
      hideCm = false;
    }
""",
        "hide_cm polling block",
    )
    text = uncomment_block(
        text,
        """    if (_hideCm != hideCm) {
      _hideCm = hideCm;
      if (desktopType == DesktopType.cm) {
        if (hideCm) {
          await hideCmWindow();
        } else {
          await showCmWindow();
        }
      }
      update = true;
    }
""",
        "hide_cm update block",
    )
    path.write_text(text, encoding="utf-8")
    print("Enabled hide_cm state updates in ServerModel.")


def patch_ipc_hide_cm_gate() -> None:
    path = ROOT / "src/ipc.rs"
    text = path.read_text(encoding="utf-8")
    old = """                } else if name == "hide_cm" {
                    value = if crate::hbbs_http::sync::is_pro() || crate::common::is_custom_client()
                    {
                        Some(hbb_common::password_security::hide_cm().to_string())
                    } else {
                        None
                    };
"""
    new = """                } else if name == "hide_cm" {
                    value = Some(hbb_common::password_security::hide_cm().to_string());
"""
    if new in text:
        print("hide_cm IPC lookup already bypasses pro/custom-client gate.")
        return
    path.write_text(replace_once(text, old, new, "hide_cm IPC pro/custom-client gate"), encoding="utf-8")
    print("Allowed hide_cm IPC lookup for default app-name clients.")


def main() -> None:
    patch_settings_page()
    patch_sciter_settings_page()
    patch_main()
    patch_server_model()
    patch_ipc_hide_cm_gate()


if __name__ == "__main__":
    main()
