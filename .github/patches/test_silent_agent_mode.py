import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import silent_agent_mode


class SilentAgentModePatchTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        for relative in (
            "src/core_main.rs",
            "src/platform/windows.rs",
            "res/msi/Package/Components/RustDesk.wxs",
            "res/msi/Package/Fragments/ShortcutProperties.wxs",
            "res/msi/Package/UI/MyInstallDirDlg.wxs",
        ):
            (self.root / relative).parent.mkdir(parents=True, exist_ok=True)

        (self.root / "src/core_main.rs").write_text(
            """fn demo() {
    #[cfg(any(target_os = "linux", target_os = "windows"))]
    if args.is_empty() {
        start_default();
    }
        } else if args[0] == "--tray" {
            if !crate::check_process("--tray", true) {
                crate::tray::start_tray();
            }
            return None;
}
""",
            encoding="utf-8",
        )
        (self.root / "src/platform/windows.rs").write_text(
            r"""pub fn install_me(options: &str, path: String, silent: bool, debug: bool) -> ResultType<()> {
    let uninstall_str = get_uninstall(false, false);
    let tray_shortcuts = if config::is_outgoing_only() {
        "".to_owned()
    } else {
        format!("
cscript \"{tray_shortcut}\"
copy /Y \"{tmp_path}\\{app_name} Tray.lnk\" \"%PROGRAMDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\\"
")
    };
}
""",
            encoding="utf-8",
        )
        (self.root / "res/msi/Package/Components/RustDesk.wxs").write_text(
            """<Component Id="App.Desktop.Shortcut" Guid="CA8FB7AA-17F7-4E36-A58A-5A016A303709" Condition="DESKTOPSHORTCUTS = 1 OR DESKTOPSHORTCUTS = &quot;Y&quot; OR DESKTOPSHORTCUTS = &quot;y&quot;">
<Component Id="App.StartupFolder.ShortcutTray" Guid="B1D1E2BB-E53E-E159-DB7C-744D5C726A8C" Condition="STARTUPSHORTCUTS = 1 AND (NOT CC_CONNECTION_TYPE=&quot;outgoing&quot;)">
""",
            encoding="utf-8-sig",
        )
        (self.root / "res/msi/Package/Fragments/ShortcutProperties.wxs").write_text(
            """<Property Id="DESKTOPSHORTCUTS" Value="1" Secure="yes"></Property>
<SetProperty Id="DESKTOPSHORTCUTS" Value="" After="RestoreSavedDesktopShortcutsValue" Sequence="first" Condition="CREATEDESKTOPSHORTCUTS AND NOT (CREATESTARTMENUSHORTCUTS = 1 OR CREATEDESKTOPSHORTCUTS = &quot;Y&quot; OR CREATEDESKTOPSHORTCUTS = &quot;y&quot;)" />
""".replace("CREATESTARTMENUSHORTCUTS", "CREATEDESKTOPSHORTCUTS"),
            encoding="utf-8-sig",
        )
        (self.root / "res/msi/Package/UI/MyInstallDirDlg.wxs").write_text(
            '<Control Id="ChkBoxDesktopShortcuts" Type="CheckBox" X="20" Y="160" Width="290" Height="17" Property="DESKTOPSHORTCUTS" CheckBoxValue="1" Text="!(loc.MyInstallDirDlgDesktopShortcuts)" />\n',
            encoding="utf-8-sig",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_patch_is_complete_and_idempotent(self):
        with patch.object(silent_agent_mode, "ROOT", self.root):
            silent_agent_mode.main()
            silent_agent_mode.main()

        core = (self.root / "src/core_main.rs").read_text(encoding="utf-8")
        windows = (self.root / "src/platform/windows.rs").read_text(encoding="utf-8")
        components = (
            self.root / "res/msi/Package/Components/RustDesk.wxs"
        ).read_text(encoding="utf-8-sig")
        properties = (
            self.root / "res/msi/Package/Fragments/ShortcutProperties.wxs"
        ).read_text(encoding="utf-8-sig")
        dialog = (
            self.root / "res/msi/Package/UI/MyInstallDirDlg.wxs"
        ).read_text(encoding="utf-8-sig")

        self.assertEqual(core.count("suppresses the installed main window"), 1)
        self.assertEqual(core.count("suppresses the tray process"), 1)
        self.assertEqual(windows.count('options.replace("desktopicon", "")'), 1)
        self.assertIn('Id="App.Desktop.Shortcut"', components)
        self.assertEqual(components.count('Condition="0"'), 2)
        self.assertIn('<Property Id="DESKTOPSHORTCUTS" Value="0"', properties)
        self.assertNotIn("ChkBoxDesktopShortcuts", dialog)


if __name__ == "__main__":
    unittest.main()
