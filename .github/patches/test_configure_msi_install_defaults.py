import tempfile
import unittest
from pathlib import Path

from configure_msi_install_defaults import configure_msi_install_defaults


SAMPLE = """\ufeff<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
\t<Fragment>
\t\t<Property Id="STARTMENUSHORTCUTS" Value="1" Secure="yes"></Property>
\t\t<Property Id="DESKTOPSHORTCUTS" Value="1" Secure="yes"></Property>
\t\t<Property Id="STARTUPSHORTCUTS" Value="1" Secure="yes"></Property>
\t\t<Property Id="PRINTER" Secure="yes"></Property>
\t</Fragment>
</Wix>
"""


class ConfigureMsiInstallDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        path = self.root / "res/msi/Package/Fragments/ShortcutProperties.wxs"
        path.parent.mkdir(parents=True)
        path.write_bytes(SAMPLE.encode("utf-8"))

    def tearDown(self):
        self.tmp.cleanup()

    def _text(self) -> str:
        return (
            self.root / "res/msi/Package/Fragments/ShortcutProperties.wxs"
        ).read_text(encoding="utf-8-sig")

    def test_noop_when_defaults_requested(self):
        self.assertFalse(
            configure_msi_install_defaults(
                self.root, desktop="default", start_menu="default", printer="off"
            )
        )
        text = self._text()
        self.assertIn('Id="DESKTOPSHORTCUTS" Value="1"', text)
        self.assertIn('Id="STARTMENUSHORTCUTS" Value="1"', text)
        self.assertIn('<Property Id="PRINTER" Secure="yes">', text)

    def test_turns_shortcuts_off_and_printer_on(self):
        self.assertTrue(
            configure_msi_install_defaults(
                self.root, desktop="off", start_menu="off", printer="default"
            )
        )
        text = self._text()
        self.assertRegex(text, r'Id="DESKTOPSHORTCUTS"[^>]*Value="0"')
        self.assertRegex(text, r'Id="STARTMENUSHORTCUTS"[^>]*Value="0"')
        self.assertRegex(text, r'Id="PRINTER"[^>]*Value="1"')
        self.assertTrue(
            (self.root / "res/msi/Package/Fragments/ShortcutProperties.wxs")
            .read_bytes()
            .startswith(b"\xef\xbb\xbf")
        )


if __name__ == "__main__":
    unittest.main()
