from __future__ import annotations

from pathlib import Path


ROOT = Path.cwd()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected one {label}, found {count}")
    return text.replace(old, new, 1)


def read_text(path: Path, *, bom: bool = False) -> str:
    return path.read_text(encoding="utf-8-sig" if bom else "utf-8")


def write_text(path: Path, text: str, *, bom: bool = False) -> None:
    path.write_text(text, encoding="utf-8-sig" if bom else "utf-8")


def patch_core_main() -> None:
    path = ROOT / "src/core_main.rs"
    text = read_text(path)

    main_marker = "Silent agent mode suppresses the installed main window."
    if main_marker not in text:
        old = """    #[cfg(any(target_os = "linux", target_os = "windows"))]
    if args.is_empty() {
"""
        new = """    #[cfg(windows)]
    if args.is_empty()
        && crate::platform::is_cur_exe_the_installed()
        && !crate::common::is_setup(&arg_exe)
    {
        log::info!("Silent agent mode suppresses the installed main window.");
        return None;
    }
    #[cfg(any(target_os = "linux", target_os = "windows"))]
    if args.is_empty() {
"""
        text = replace_once(text, old, new, "empty-argument startup branch")

    tray_marker = "Silent agent mode suppresses the tray process."
    if tray_marker not in text:
        old = """        } else if args[0] == "--tray" {
            if !crate::check_process("--tray", true) {
                crate::tray::start_tray();
            }
            return None;
"""
        new = """        } else if args[0] == "--tray" {
            log::info!("Silent agent mode suppresses the tray process.");
            return None;
"""
        text = replace_once(text, old, new, "tray startup branch")

    write_text(path, text)


def patch_windows_installer() -> None:
    path = ROOT / "src/platform/windows.rs"
    text = read_text(path)

    option_marker = 'let silent_options = options.replace("desktopicon", "");'
    if option_marker not in text:
        old = """pub fn install_me(options: &str, path: String, silent: bool, debug: bool) -> ResultType<()> {
    let uninstall_str = get_uninstall(false, false);
"""
        new = """pub fn install_me(options: &str, path: String, silent: bool, debug: bool) -> ResultType<()> {
    let silent_options = options.replace("desktopicon", "");
    let options = silent_options.as_str();
    let uninstall_str = get_uninstall(false, false);
"""
        text = replace_once(text, old, new, "Windows installer entry")

    tray_marker = "// Silent agent mode is service-only and never installs a tray shortcut."
    if tray_marker not in text:
        old = r"""    let tray_shortcuts = if config::is_outgoing_only() {
        "".to_owned()
    } else {
        format!("
cscript \"{tray_shortcut}\"
copy /Y \"{tmp_path}\\{app_name} Tray.lnk\" \"%PROGRAMDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\\"
")
    };
"""
        new = """    // Silent agent mode is service-only and never installs a tray shortcut.
    let tray_shortcuts = "".to_owned();
"""
        text = replace_once(text, old, new, "Windows tray shortcut block")

    write_text(path, text)


def patch_msi_shortcuts() -> None:
    components_path = ROOT / "res/msi/Package/Components/RustDesk.wxs"
    text = read_text(components_path, bom=True)
    desktop_old = '<Component Id="App.Desktop.Shortcut" Guid="CA8FB7AA-17F7-4E36-A58A-5A016A303709" Condition="DESKTOPSHORTCUTS = 1 OR DESKTOPSHORTCUTS = &quot;Y&quot; OR DESKTOPSHORTCUTS = &quot;y&quot;">'
    desktop_new = '<Component Id="App.Desktop.Shortcut" Guid="CA8FB7AA-17F7-4E36-A58A-5A016A303709" Condition="0">'
    if desktop_new not in text:
        text = replace_once(text, desktop_old, desktop_new, "MSI desktop shortcut component")
    tray_old = '<Component Id="App.StartupFolder.ShortcutTray" Guid="B1D1E2BB-E53E-E159-DB7C-744D5C726A8C" Condition="STARTUPSHORTCUTS = 1 AND (NOT CC_CONNECTION_TYPE=&quot;outgoing&quot;)">'
    tray_new = '<Component Id="App.StartupFolder.ShortcutTray" Guid="B1D1E2BB-E53E-E159-DB7C-744D5C726A8C" Condition="0">'
    if tray_new not in text:
        text = replace_once(text, tray_old, tray_new, "MSI tray shortcut component")
    write_text(components_path, text, bom=True)

    properties_path = ROOT / "res/msi/Package/Fragments/ShortcutProperties.wxs"
    text = read_text(properties_path, bom=True)
    default_old = '<Property Id="DESKTOPSHORTCUTS" Value="1" Secure="yes"></Property>'
    default_new = '<Property Id="DESKTOPSHORTCUTS" Value="0" Secure="yes"></Property>'
    if default_new not in text:
        text = replace_once(text, default_old, default_new, "MSI desktop shortcut default")
    reset_old = '<SetProperty Id="DESKTOPSHORTCUTS" Value="" After="RestoreSavedDesktopShortcutsValue" Sequence="first" Condition="CREATEDESKTOPSHORTCUTS AND NOT (CREATEDESKTOPSHORTCUTS = 1 OR CREATEDESKTOPSHORTCUTS = &quot;Y&quot; OR CREATEDESKTOPSHORTCUTS = &quot;y&quot;)" />'
    reset_new = '<SetProperty Id="DESKTOPSHORTCUTS" Value="" After="RestoreSavedDesktopShortcutsValue" Sequence="first" />'
    if reset_new not in text:
        text = replace_once(text, reset_old, reset_new, "MSI desktop shortcut override")
    write_text(properties_path, text, bom=True)

    dialog_path = ROOT / "res/msi/Package/UI/MyInstallDirDlg.wxs"
    text = read_text(dialog_path, bom=True)
    control_old = '<Control Id="ChkBoxDesktopShortcuts" Type="CheckBox" X="20" Y="160" Width="290" Height="17" Property="DESKTOPSHORTCUTS" CheckBoxValue="1" Text="!(loc.MyInstallDirDlgDesktopShortcuts)" />'
    control_new = '<!-- Silent agent mode never offers a desktop shortcut. -->'
    if control_new not in text:
        text = replace_once(text, control_old, control_new, "MSI desktop shortcut checkbox")
    write_text(dialog_path, text, bom=True)


def validate_result() -> None:
    core = read_text(ROOT / "src/core_main.rs")
    windows = read_text(ROOT / "src/platform/windows.rs")
    components = read_text(
        ROOT / "res/msi/Package/Components/RustDesk.wxs", bom=True
    )
    properties = read_text(
        ROOT / "res/msi/Package/Fragments/ShortcutProperties.wxs", bom=True
    )
    dialog = read_text(ROOT / "res/msi/Package/UI/MyInstallDirDlg.wxs", bom=True)
    required = {
        "installed main-window guard": "Silent agent mode suppresses the installed main window." in core,
        "tray process guard": "Silent agent mode suppresses the tray process." in core,
        "portable desktop shortcut filter": 'options.replace("desktopicon", "")' in windows,
        "portable tray shortcut filter": "service-only and never installs a tray shortcut" in windows,
        "MSI desktop shortcut disable": (
            '<Component Id="App.Desktop.Shortcut" '
            'Guid="CA8FB7AA-17F7-4E36-A58A-5A016A303709" Condition="0">'
        ) in components,
        "MSI tray shortcut disable": (
            '<Component Id="App.StartupFolder.ShortcutTray" '
            'Guid="B1D1E2BB-E53E-E159-DB7C-744D5C726A8C" Condition="0">'
        ) in components,
        "MSI desktop default disable": '<Property Id="DESKTOPSHORTCUTS" Value="0"' in properties,
        "MSI desktop override disable": (
            '<SetProperty Id="DESKTOPSHORTCUTS" Value="" '
            'After="RestoreSavedDesktopShortcutsValue" Sequence="first" />'
        ) in properties,
        "MSI desktop option removal": "Silent agent mode never offers a desktop shortcut." in dialog,
    }
    missing = [label for label, present in required.items() if not present]
    if missing:
        raise SystemExit("Silent agent patch is incomplete: " + ", ".join(missing))


def main() -> None:
    patch_core_main()
    patch_windows_installer()
    patch_msi_shortcuts()
    validate_result()
    print("Enabled Windows silent agent mode and disabled desktop/tray shortcuts.")


if __name__ == "__main__":
    main()
