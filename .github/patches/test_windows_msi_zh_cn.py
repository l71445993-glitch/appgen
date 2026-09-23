import tempfile
import unittest
from pathlib import Path
from xml.dom import minidom

from configure_windows_msi_zh_cn import CULTURE, PRODUCT_LANGUAGE_ZH_CN, configure_msi_zh_cn


PACKAGE_XML = """<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
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
  <String Id="MyInstallDirDlgDesktopShortcuts" Value="Create desktop icon" />
  <String Id="MyInstallDirDlgStartMenuShortcuts" Value="Create start menu shortcuts" />
  <String Id="MyInstallDirDlgPrinter" Value="Install RustDesk Printer" />
  <String Id="DowngradeError" Value="A newer version of [ProductName] is already installed." />
</WixLocalization>
"""

WIXEXT_XML = """<WixLocalization Culture="en-us"
  xmlns="http://wixtoolset.org/schemas/v4/wxl">
  <String Id="WixSchedFirewallExceptionsInstall" Overridable="yes" Value="Configuring Windows Firewall" />
</WixLocalization>
"""

WIXPROJ = """<Project Sdk="WixToolset.Sdk/4.0.5">
  <PropertyGroup>
    <Configurations>Release</Configurations>
  </PropertyGroup>
</Project>
"""

WIXUI_XML = """<WixLocalization Culture="zh-cn" Codepage="936" xmlns="http://wixtoolset.org/schemas/v4/wxl">
  <String Id="WixUINext" Overridable="yes" Value="下一步(&amp;N)" />
  <String Id="WixUIBack" Overridable="yes" Value="上一步(&amp;B)" />
  <String Id="WixUICancel" Overridable="yes" Value="取消" />
  <String Id="InstallDirDlgTitle" Overridable="yes" Value="{\\WixUI_Font_Title}目标文件夹" />
</WixLocalization>
"""


def element_by_id(document, string_id):
    for element in document.getElementsByTagName("*"):
        if element.localName == "String" and element.getAttribute("Id") == string_id:
            return element
    raise AssertionError(f"Missing String Id={string_id}")


class WindowsMsiZhCnTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        language = self.root / "res/msi/Package/Language"
        language.mkdir(parents=True)
        (self.root / "res/msi/Package").mkdir(parents=True, exist_ok=True)
        (language / "Package.en-us.wxl").write_text(LOCALIZATION_XML, encoding="utf-8")
        (language / "WixExt_en-us.wxl").write_text(WIXEXT_XML, encoding="utf-8")
        (self.root / "res/msi/Package/Package.wixproj").write_text(WIXPROJ, encoding="utf-8")
        (self.root / "WixUI_zh-CN.wxl").write_text(WIXUI_XML, encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rewrites_package_strings_and_pins_zh_cn(self):
        self.assertTrue(configure_msi_zh_cn(self.root))

        package = minidom.parse(str(self.root / "res/msi/Package/Language/Package.en-us.wxl"))
        root = package.documentElement
        self.assertEqual(root.getAttribute("Culture"), CULTURE)
        self.assertEqual(
            element_by_id(package, "ProductLanguage").getAttribute("Value"),
            PRODUCT_LANGUAGE_ZH_CN,
        )
        self.assertEqual(
            element_by_id(package, "MyInstallDirDlgDesktopShortcuts").getAttribute("Value"),
            "创建桌面图标",
        )
        self.assertEqual(
            element_by_id(package, "MyInstallDirDlgStartMenuShortcuts").getAttribute("Value"),
            "创建开始菜单快捷方式",
        )
        self.assertIn(
            "打印机",
            element_by_id(package, "MyInstallDirDlgPrinter").getAttribute("Value"),
        )

        wixui = self.root / "res/msi/Package/Language/WixUI_zh-CN.wxl"
        self.assertTrue(wixui.is_file())
        wixui_doc = minidom.parse(str(wixui))
        self.assertEqual(wixui_doc.documentElement.getAttribute("Culture"), CULTURE)
        self.assertEqual(
            element_by_id(wixui_doc, "WixUINext").getAttribute("Value"),
            "下一步(&N)",
        )

        wixproj = (self.root / "res/msi/Package/Package.wixproj").read_text(encoding="utf-8")
        self.assertIn(f"<Cultures>{CULTURE}</Cultures>", wixproj)

        # Idempotent
        self.assertFalse(configure_msi_zh_cn(self.root))


if __name__ == "__main__":
    unittest.main()
