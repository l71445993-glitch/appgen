import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from xml.dom import minidom

from configure_windows_msi_utf8 import configure_msi_utf8


PACKAGE_XML = """<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <?include Includes.wxi?>
  <Package Name="$(var.Product)" Manufacturer="$(var.Manufacturer)"
      Scope="perMachine">
    <SummaryInformation Codepage="!(loc.SummaryCodepage)" />
  </Package>
</Wix>
"""
LOCALIZATION_XML = """<!-- localization strings -->
<WixLocalization Culture="en-us" Codepage="1252"
  xmlns="http://wixtoolset.org/schemas/v4/wxl">
  <String Id="SummaryCodepage" Value="1252" />
  <String Id="ProductLanguage" Value="1033" />
</WixLocalization>
"""


def element_by_local_name(document, local_name, **attributes):
    matches = []
    for element in document.getElementsByTagName("*"):
        if element.localName != local_name:
            continue
        if any(element.getAttribute(key) != value for key, value in attributes.items()):
            continue
        matches.append(element)
    if len(matches) != 1:
        raise AssertionError(f"Expected one {local_name}, found {len(matches)}")
    return matches[0]


class WindowsMsiUtf8Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.package_path = self.root / "res/msi/Package/Package.wxs"
        self.localization_path = (
            self.root / "res/msi/Package/Language/Package.en-us.wxl"
        )
        self.package_path.parent.mkdir(parents=True)
        self.localization_path.parent.mkdir(parents=True)
        self.package_path.write_text(PACKAGE_XML, encoding="utf-8")
        self.localization_path.write_text(LOCALIZATION_XML, encoding="utf-8")
        (self.package_path.parent / "Includes.wxi").write_text(
            "<Include />\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_configures_package_and_localization_codepages(self):
        self.assertTrue(configure_msi_utf8(self.root))

        package_document = minidom.parse(str(self.package_path))
        localization_document = minidom.parse(str(self.localization_path))
        package = element_by_local_name(package_document, "Package")
        summary_information = element_by_local_name(
            package_document,
            "SummaryInformation",
        )
        summary_codepage = element_by_local_name(
            localization_document,
            "String",
            Id="SummaryCodepage",
        )

        self.assertEqual(package.getAttribute("Codepage"), "65001")
        self.assertEqual(
            localization_document.documentElement.getAttribute("Codepage"),
            "65001",
        )
        self.assertEqual(
            localization_document.documentElement.getAttribute(
                "SummaryInformationCodepage"
            ),
            "1252",
        )
        self.assertEqual(summary_codepage.getAttribute("Value"), "1252")
        self.assertEqual(
            summary_information.getAttribute("Description"),
            "Customized RustDesk client installer",
        )
        self.assertEqual(summary_information.getAttribute("Manufacturer"), "RDGen")
        self.assertEqual(package.getAttribute("Name"), "$(var.Product)")
        self.assertEqual(
            package.getAttribute("Manufacturer"), "$(var.Manufacturer)"
        )
        self.assertIn("<?include Includes.wxi?>", self.package_path.read_text("utf-8"))
        self.assertIn(
            "<!-- localization strings -->",
            self.localization_path.read_text("utf-8"),
        )

    def test_second_run_is_a_no_op(self):
        configure_msi_utf8(self.root)
        package_after_first_run = self.package_path.read_bytes()
        localization_after_first_run = self.localization_path.read_bytes()

        self.assertFalse(configure_msi_utf8(self.root))
        self.assertEqual(self.package_path.read_bytes(), package_after_first_run)
        self.assertEqual(
            self.localization_path.read_bytes(),
            localization_after_first_run,
        )

    def test_missing_summary_codepage_fails_without_writing_either_file(self):
        self.localization_path.write_text(
            LOCALIZATION_XML.replace(' Id="SummaryCodepage"', ' Id="Other"'),
            encoding="utf-8",
        )
        package_before = self.package_path.read_bytes()
        localization_before = self.localization_path.read_bytes()

        with self.assertRaises(SystemExit):
            configure_msi_utf8(self.root)

        self.assertEqual(self.package_path.read_bytes(), package_before)
        self.assertEqual(self.localization_path.read_bytes(), localization_before)

    @unittest.skipUnless(os.environ.get("WIX_EXE"), "WIX_EXE is not configured")
    def test_wix_builds_unicode_product_with_ansi_summary(self):
        self.package_path.write_text(
            PACKAGE_XML.replace(
                '<Package Name="$(var.Product)" Manufacturer="$(var.Manufacturer)"\n'
                '      Scope="perMachine">',
                '<Package Name="Unicode Client" Version="1.0.0" '
                'Manufacturer="Unicode Vendor" Language="1033" '
                'UpgradeCode="{2DCDB65D-7F9C-456B-BB77-A75C7D87EA8D}" '
                'Scope="perMachine">',
            ).replace("Unicode Client", "\u4e2d\u6587\u5ba2\u6237\u7aef")
            .replace("Unicode Vendor", "\u4e2d\u6587\u5382\u5546"),
            encoding="utf-8",
        )

        configure_msi_utf8(self.root)
        output_path = self.root / "unicode-client.msi"
        completed = subprocess.run(
            [
                os.environ["WIX_EXE"],
                "build",
                "-nologo",
                "-out",
                str(output_path),
                "-loc",
                str(self.localization_path),
                str(self.package_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertEqual(
            completed.returncode,
            0,
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        self.assertTrue(output_path.is_file())


if __name__ == "__main__":
    unittest.main()
