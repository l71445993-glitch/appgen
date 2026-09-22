from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path.cwd()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def get_text(changes: dict[Path, str], path: Path) -> str:
    return changes.get(path, read_text(path))


def set_text(changes: dict[Path, str], path: Path, text: str) -> None:
    changes[path] = text


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"Could not find {label}")
    return text.replace(old, new, 1)


def insert_before(text: str, marker: str, insert: str, label: str) -> str:
    index = text.find(marker)
    if index == -1:
        raise SystemExit(f"Could not find insertion point for {label}")
    return text[:index] + insert + text[index:]


def insert_after_function_open(text: str, signature: str, insert: str, label: str) -> str:
    start = text.find(signature)
    if start == -1:
        raise SystemExit(f"Could not find {label}")
    open_brace = text.find("{", start)
    if open_brace == -1:
        raise SystemExit(f"Could not find opening brace for {label}")
    line_end = text.find("\n", open_brace)
    if line_end == -1:
        raise SystemExit(f"Could not find insertion line for {label}")
    return text[: line_end + 1] + insert + text[line_end + 1 :]


def insert_before_function_end(text: str, start_marker: str, next_marker: str, insert: str, label: str) -> str:
    start = text.find(start_marker)
    if start == -1:
        raise SystemExit(f"Could not find {label}")
    end = text.find(next_marker, start)
    if end == -1:
        raise SystemExit(f"Could not find end marker for {label}")
    block = text[start:end]
    last_close = block.rfind("\n}")
    if last_close == -1:
        raise SystemExit(f"Could not find final brace for {label}")
    updated = block[:last_close] + insert + block[last_close:]
    return text[:start] + updated + text[end:]


def patch_copy_id_password(changes: dict[Path, str]) -> None:
    path = ROOT / "flutter/lib/desktop/pages/desktop_home_page.dart"
    text = get_text(changes, path)
    if "Icons.copy_outlined" in text and "一次性密码:" in text:
        print("Copy ID + password button is already present.")
        return
    old = """                  Flexible(
                    child: GestureDetector(
                      onDoubleTap: () {
                        Clipboard.setData(
                            ClipboardData(text: model.serverId.text));
                        showToast(translate("Copied"));
                      },
                      child: TextFormField(
                        controller: model.serverId,
                        readOnly: true,
                        decoration: InputDecoration(
                          border: InputBorder.none,
                          contentPadding: EdgeInsets.only(top: 10, bottom: 10),
                        ),
                        style: TextStyle(
                          fontSize: 22,
                        ),
                      ).workaroundFreezeLinuxMint(),
                    ),
                  )
"""
    new = """                  Flexible(
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        Expanded(
                          child: GestureDetector(
                            onDoubleTap: () {
                              Clipboard.setData(
                                  ClipboardData(text: model.serverId.text));
                              showToast(translate("Copied"));
                            },
                            child: Container(
                              height: 32,
                              alignment: Alignment.centerLeft,
                              child: ValueListenableBuilder<TextEditingValue>(
                                valueListenable: model.serverId,
                                builder: (context, value, child) {
                                  return AutoSizeText(
                                    value.text,
                                    maxLines: 1,
                                    minFontSize: 12,
                                    stepGranularity: 0.5,
                                    style: TextStyle(
                                      fontSize: 22,
                                    ),
                                  );
                                },
                              ),
                            ),
                          ),
                        ),
                        InkWell(
                          borderRadius: BorderRadius.circular(6),
                          onTap: () {
                            Clipboard.setData(ClipboardData(
                                text:
                                    'ID: ${model.serverId.text.trim()}\\n一次性密码: ${model.serverPasswd.text.trim()}'));
                            showToast(translate("Copied"));
                          },
                          child: Container(
                            height: 26,
                            width: 54,
                            decoration: BoxDecoration(
                              color: MyTheme.accent.withOpacity(0.08),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(
                                  color: MyTheme.accent.withOpacity(0.35)),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: const [
                                Icon(Icons.copy_outlined,
                                    size: 14, color: MyTheme.accent),
                                SizedBox(width: 2),
                                Text(
                                  '复制',
                                  style: TextStyle(
                                      fontSize: 13, color: MyTheme.accent),
                                ),
                              ],
                            ),
                          ),
                        ).marginOnly(left: 3, right: 0, top: 4),
                      ],
                    ),
                  )
"""
    set_text(changes, path, replace_once(text, old, new, "copy ID/password button block"))
    print("Added the copy ID + password button.")


def patch_manual_temporary_password(changes: dict[Path, str]) -> None:
    connection_path = ROOT / "src/server/connection.rs"
    text = get_text(changes, connection_path)
    old = """        if conn.authorized {
            password::update_temporary_password();
        }
"""
    if old in text:
        text = text.replace(old, "", 1)
        set_text(changes, connection_path, text)
        print("Disabled auto-refresh of temporary passwords after a connection ends.")
    elif "password::update_temporary_password();" in text:
        print("Temporary password auto-refresh is already disabled.")
    else:
        raise SystemExit("Could not find temporary password auto-refresh block in src/server/connection.rs")

    ipc_path = ROOT / "src/ipc.rs"
    text = get_text(changes, ipc_path)
    old = """                } else if name == "temporary-password" {
                    password::update_temporary_password();
                } else if name == "permanent-password" {
"""
    new = """                } else if name == "temporary-password" {
                    if value.is_empty() {
                        password::update_temporary_password();
                    } else {
                        *password::TEMPORARY_PASSWORD.write().unwrap() = value;
                    }
                } else if name == "permanent-password" {
"""
    if "password::TEMPORARY_PASSWORD.write().unwrap()" in text:
        print("IPC temporary password setter is already present.")
    else:
        set_text(changes, ipc_path, replace_once(text, old, new, "IPC temporary password branch"))
        print("Added IPC support for setting a custom temporary password.")

    ffi_path = ROOT / "src/flutter_ffi.rs"
    text = get_text(changes, ffi_path)
    if 'key == "temporary-password"' in text:
        print("mainSetOption already handles temporary-password.")
    else:
        insert = """    if key == "temporary-password" {
        #[cfg(any(target_os = "android", target_os = "ios"))]
        {
            *hbb_common::password_security::TEMPORARY_PASSWORD
                .write()
                .unwrap() = value;
        }
        #[cfg(not(any(target_os = "android", target_os = "ios")))]
        hbb_common::allow_err!(crate::ipc::set_config("temporary-password", value));
        return;
    }
"""
        text = insert_after_function_open(
            text,
            "pub fn main_set_option(key: String, value: String)",
            insert,
            "main_set_option temporary-password hook",
        )
        set_text(changes, ffi_path, text)
        print("Routed mainSetOption(temporary-password) through the daemon.")

    home_path = ROOT / "flutter/lib/desktop/pages/desktop_home_page.dart"
    text = get_text(changes, home_path)
    if "key: 'temporary-password', value: password" in text:
        print("Desktop home page already uses the custom temporary password dialog.")
    else:
        old = """                      if (!bind.isDisableSettings())
                        InkWell(
                          child: Tooltip(
                            message: translate('Change Password'),
                            child: Obx(
                              () => Icon(
                                Icons.edit,
                                color: editHover.value
                                    ? textColor
                                    : Color(0xFFDDDDDD),
                                size: 22,
                              ).marginOnly(right: 8, top: 4),
                            ),
                          ),
                          onTap: () => DesktopSettingPage.switch2page(
                              SettingsTabKey.safety),
                          onHover: (value) => editHover.value = value,
                        ),
"""
        new = """                      if (!bind.isDisableSettings())
                        InkWell(
                          child: Tooltip(
                            message: '自定义临时密码',
                            child: Obx(
                              () => Icon(
                                Icons.edit,
                                color: editHover.value
                                    ? textColor
                                    : Color(0xFFDDDDDD),
                                size: 22,
                              ).marginOnly(right: 8, top: 4),
                            ),
                          ),
                          onTap: () {
                            final controller = TextEditingController(
                                text: model.serverPasswd.text == '-'
                                    ? ''
                                    : model.serverPasswd.text);

                            submit() async {
                              final password = controller.text.trim();
                              if (password.isEmpty) {
                                return;
                              }
                              await bind.mainSetOption(
                                  key: 'temporary-password', value: password);
                              model.serverPasswd.text = password;
                              showToast(translate("Successful"));
                              gFFI.dialogManager.dismissAll();
                            }

                            gFFI.dialogManager.show(
                                (setState, close, context) {
                              return CustomAlertDialog(
                                title: const Text('自定义临时密码'),
                                content: SizedBox(
                                  width: 320,
                                  child: TextField(
                                    controller: controller,
                                    autofocus: true,
                                    obscureText: false,
                                    decoration: const InputDecoration(
                                      border: OutlineInputBorder(),
                                      labelText: '临时密码',
                                      hintText: '请输入临时密码',
                                    ),
                                    onSubmitted: (_) => submit(),
                                  ),
                                ),
                                actions: [
                                  dialogButton('Cancel',
                                      onPressed: close, isOutline: true),
                                  dialogButton('OK', onPressed: submit),
                                ],
                                onSubmit: submit,
                                onCancel: close,
                              );
                            });
                          },
                          onHover: (value) => editHover.value = value,
                        ),
"""
        text = replace_once(text, old, new, "temporary password edit button")
        set_text(changes, home_path, text)
        print("Replaced the password edit button with a custom temporary password dialog.")


def patch_start_on_boot(changes: dict[Path, str]) -> None:
    windows_path = ROOT / "src/platform/windows.rs"
    text = get_text(changes, windows_path)
    if "pub fn is_start_on_boot_enabled() -> bool" in text:
        print("Windows start-on-boot helpers are already present.")
    else:
        helpers = r"""pub fn is_start_on_boot_enabled() -> bool {
    let program_data =
        std::env::var("PROGRAMDATA").unwrap_or_else(|_| "C:\\ProgramData".to_owned());
    PathBuf::from(program_data)
        .join("Microsoft")
        .join("Windows")
        .join("Start Menu")
        .join("Programs")
        .join("Startup")
        .join(format!("{} Tray.lnk", crate::get_app_name()))
        .exists()
}

pub fn start_self_service() -> ResultType<()> {
    if config::is_outgoing_only() || !is_installed() || is_self_service_running() {
        return Ok(());
    }
    let app_name = crate::get_app_name();
    let cmds = format!(
        "
chcp 65001
sc start {app_name}
"
    );
    run_cmds(cmds, false, "start_service")?;
    Ok(())
}

pub fn set_start_on_boot(enable: bool) -> ResultType<()> {
    let app_name = crate::get_app_name();
    let tmp_path = std::env::temp_dir().to_string_lossy().to_string();
    if enable {
        let (_, install_dir, _, exe) = get_install_info();
        let tray_shortcut = get_tray_shortcut(&install_dir, &exe, &exe, &tmp_path)?;
        let cmds = format!(
            "
chcp 65001
cscript \"{tray_shortcut}\"
copy /Y \"{tmp_path}\\{app_name} Tray.lnk\" \"%PROGRAMDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\\"
sc config {app_name} start= auto
sc start {app_name}
if exist \"{tray_shortcut}\" del /f /q \"{tray_shortcut}\"
if exist \"{tmp_path}\\{app_name} Tray.lnk\" del /f /q \"{tmp_path}\\{app_name} Tray.lnk\"
"
        );
        run_cmds(cmds, false, "start_on_boot")?;
    } else {
        let cmds = format!(
            "
chcp 65001
if exist \"%PROGRAMDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\{app_name} Tray.lnk\" del /f /q \"%PROGRAMDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\{app_name} Tray.lnk\"
sc config {app_name} start= demand
"
        );
        run_cmds(cmds, false, "start_on_boot")?;
    }
    Ok(())
}

"""
        text = insert_before(
            text,
            "fn get_import_config(exe: &str) -> String {",
            helpers,
            "Windows start-on-boot helpers",
        )
        set_text(changes, windows_path, text)
        print("Added Windows start-on-boot helpers.")

    ffi_path = ROOT / "src/flutter_ffi.rs"
    text = get_text(changes, ffi_path)
    if 'key == "start-on-boot"' in text and "is_start_on_boot_enabled" in text:
        print("Existing option bridge already handles start-on-boot.")
    else:
        text = replace_once(
            text,
            """pub fn main_get_option(key: String) -> String {
    get_option(key)
}
""",
            """pub fn main_get_option(key: String) -> String {
    #[cfg(windows)]
    if key == "start-on-boot" {
        return if crate::platform::windows::is_start_on_boot_enabled() {
            "Y".to_owned()
        } else {
            "N".to_owned()
        };
    }
    get_option(key)
}
""",
            "main_get_option start-on-boot hook",
        )
        text = replace_once(
            text,
            """pub fn main_get_option_sync(key: String) -> SyncReturn<String> {
    SyncReturn(get_option(key))
}
""",
            """pub fn main_get_option_sync(key: String) -> SyncReturn<String> {
    #[cfg(windows)]
    if key == "start-on-boot" {
        return SyncReturn(if crate::platform::windows::is_start_on_boot_enabled() {
            "Y".to_owned()
        } else {
            "N".to_owned()
        });
    }
    SyncReturn(get_option(key))
}
""",
            "main_get_option_sync start-on-boot hook",
        )
        insert = """    #[cfg(windows)]
    if key == "start-on-boot" {
        let enable = config::option2bool("start-on-boot", &value);
        hbb_common::allow_err!(crate::platform::windows::set_start_on_boot(enable));
        return;
    }
"""
        text = insert_after_function_open(
            text,
            "pub fn main_set_option(key: String, value: String)",
            insert,
            "main_set_option start-on-boot hook",
        )
        if "crate::platform::windows::start_self_service()" not in text:
            text = insert_before_function_end(
                text,
                "pub fn main_start_service() {",
                "\npub fn main_update_temporary_password()",
                """
    #[cfg(windows)]
    {
        config::Config::set_option("stop-service".into(), "".into());
        hbb_common::allow_err!(crate::platform::windows::start_self_service());
    }""",
                "main_start_service Windows hook",
            )
        set_text(changes, ffi_path, text)
        print("Exposed start-on-boot through existing option helpers.")

    home_path = ROOT / "flutter/lib/desktop/pages/desktop_home_page.dart"
    text = get_text(changes, home_path)
    if "start-on-boot" in text and "开机自启" in text:
        print("Desktop home page already includes the start-on-boot checkbox.")
    else:
        text = replace_once(
            text,
            "  var svcStopped = false.obs;\n",
            "  var svcStopped = false.obs;\n  final RxBool _startOnBoot = true.obs;\n",
            "start-on-boot state variable",
        )
        text = replace_once(
            text,
            """      final v = await mainGetBoolOption(kOptionStopService);
      if (v != svcStopped.value) {
        svcStopped.value = v;
        setState(() {});
      }
""",
            """      final v = await mainGetBoolOption(kOptionStopService);
      if (v != svcStopped.value) {
        svcStopped.value = v;
        setState(() {});
      }
      if (isWindows) {
        final startOnBoot = option2bool('start-on-boot',
            bind.mainGetOptionSync(key: 'start-on-boot'));
        if (startOnBoot != _startOnBoot.value) {
          _startOnBoot.value = startOnBoot;
          setState(() {});
        }
      }
""",
            "start-on-boot sync block",
        )
        text = text.replace("            height: 52,\n", "            height: 76,\n", 1)
        text = replace_once(
            text,
            """                          onHover: (value) => editHover.value = value,
                        ),
                    ],
                  ),
                ],
""",
            """                          onHover: (value) => editHover.value = value,
                        ),
                    ],
                  ),
                  if (isWindows)
                    Obx(() => Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            SizedBox(
                              width: 18,
                              height: 18,
                              child: Checkbox(
                                value: _startOnBoot.value,
                                activeColor: MyTheme.accent,
                                visualDensity: VisualDensity.compact,
                                materialTapTargetSize:
                                    MaterialTapTargetSize.shrinkWrap,
                                onChanged: (value) async {
                                  if (value == null) {
                                    return;
                                  }
                                  _startOnBoot.value = value;
                                  await bind.mainSetOption(
                                      key: 'start-on-boot',
                                      value:
                                          bool2option('start-on-boot', value));
                                  _startOnBoot.value = option2bool(
                                      'start-on-boot',
                                      bind.mainGetOptionSync(
                                          key: 'start-on-boot'));
                                  setState(() {});
                                },
                              ),
                            ),
                            const SizedBox(width: 4),
                            Text(
                              '开机自启',
                              style: TextStyle(
                                  fontSize: 14,
                                  color: textColor?.withOpacity(0.75)),
                            ),
                          ],
                        ).marginOnly(top: 1)),
                ],
""",
            "start-on-boot checkbox block",
        )
        set_text(changes, home_path, text)
        print("Added the start-on-boot checkbox.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual-temporary-password", action="store_true")
    parser.add_argument("--show-start-on-boot", action="store_true")
    parser.add_argument("--copy-id-password", action="store_true")
    args = parser.parse_args()

    changes: dict[Path, str] = {}

    if args.copy_id_password:
        patch_copy_id_password(changes)
    if args.manual_temporary_password:
        patch_manual_temporary_password(changes)
    if args.show_start_on_boot:
        patch_start_on_boot(changes)

    if not (args.copy_id_password or args.manual_temporary_password or args.show_start_on_boot):
        print("No runtime desktop feature patches requested.")
        return

    for path, text in changes.items():
        write_text(path, text)


if __name__ == "__main__":
    main()
