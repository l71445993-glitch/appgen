from __future__ import annotations

import importlib.util
import ast
import json
import shlex
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


PATCH_DIR = Path(__file__).resolve().parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PATCH_DIR / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


native = load_module("customize_linux_native_packages", "customize_linux_native_packages.py")
appimage = load_module("customize_appimage_recipe", "customize_appimage_recipe.py")
flatpak = load_module("customize_flatpak_manifest", "customize_flatpak_manifest.py")
beijing = load_module("beijing_custom_linux_packaging", "beijing_custom_linux_packaging.py")
allow_custom = load_module("allow_custom", "allowCustom.py")


BUILD_PY = textwrap.dedent(
    r'''
    def generate_control_file(version):
        content = """Package: rustdesk
    Version: %s
    """


    def build_flutter_deb(version, features):
        if not skip_cargo:
            system2(f'cargo build --locked --features {features} --lib --release')
        os.chdir('flutter')
        system2('flutter build linux --release')
        system2('mkdir -p tmpdeb/usr/bin/')
        system2('mkdir -p tmpdeb/usr/share/rustdesk')
        system2('mkdir -p tmpdeb/etc/rustdesk/')
        system2('mkdir -p tmpdeb/etc/pam.d/')
        system2('mkdir -p tmpdeb/usr/share/rustdesk/files/systemd/')
        system2('mkdir -p tmpdeb/usr/share/icons/hicolor/256x256/apps/')
        system2('mkdir -p tmpdeb/usr/share/icons/hicolor/scalable/apps/')
        system2('mkdir -p tmpdeb/usr/share/applications/')
        system2('mkdir -p tmpdeb/usr/share/polkit-1/actions')
        system2('rm tmpdeb/usr/bin/rustdesk || true')
        system2(
            f'cp -r {flutter_build_dir}/* tmpdeb/usr/share/rustdesk/')
        system2(
            'cp ../res/rustdesk.service tmpdeb/usr/share/rustdesk/files/systemd/')
        system2(
            'cp ../res/128x128@2x.png tmpdeb/usr/share/icons/hicolor/256x256/apps/rustdesk.png')
        system2(
            'cp ../res/scalable.svg tmpdeb/usr/share/icons/hicolor/scalable/apps/rustdesk.svg')
        system2(
            'cp ../res/rustdesk.desktop tmpdeb/usr/share/applications/rustdesk.desktop')
        system2(
            'cp ../res/rustdesk-link.desktop tmpdeb/usr/share/applications/rustdesk-link.desktop')
        system2(
            'cp ../res/startwm.sh tmpdeb/etc/rustdesk/')
        system2(
            'cp ../res/xorg.conf tmpdeb/etc/rustdesk/')
        system2(
            'cp ../res/pam.d/rustdesk.debian tmpdeb/etc/pam.d/rustdesk')
        system2(
            "echo \"#!/bin/sh\" >> tmpdeb/usr/share/rustdesk/files/polkit && chmod a+x tmpdeb/usr/share/rustdesk/files/polkit")


    def build_deb_from_folder(version, binary_folder):
        pass
    '''
).lstrip()

RPM_SPEC = textwrap.dedent(
    '''
    Name:       rustdesk
    Version:    1.4.9
    Release:    0
    Summary:    RPM package
    URL:        https://rustdesk.com
    Vendor:     rustdesk

    %install
    mkdir -p "%{buildroot}/usr/share/rustdesk" && cp -r ${HBB}/flutter/build/linux/x64/release/bundle/* -t "%{buildroot}/usr/share/rustdesk"
    install -Dm 644 $HBB/res/rustdesk.service -t "%{buildroot}/usr/share/rustdesk/files"
    install -Dm 644 $HBB/res/rustdesk.desktop -t "%{buildroot}/usr/share/rustdesk/files"
    install -Dm 644 $HBB/res/rustdesk-link.desktop -t "%{buildroot}/usr/share/rustdesk/files"

    %files
    /usr/share/rustdesk/*

    %post
    ln -sf /usr/share/rustdesk/rustdesk /usr/bin/rustdesk
    systemctl daemon-reload
    systemctl enable rustdesk
    systemctl start rustdesk
    '''
).lstrip()

PKGBUILD = '''pkgname=rustdesk
pkgdesc=""
url=""
package() {
\t  mkdir -p "${pkgdir}/usr/share/rustdesk" && cp -r ${HBB}/flutter/build/linux/x64/release/bundle/* -t "${pkgdir}/usr/share/rustdesk"
\t  pushd ${pkgdir} && ln -s /usr/share/rustdesk/rustdesk usr/bin/rustdesk && popd
\t  install -Dm 644 $HBB/res/rustdesk.service -t "${pkgdir}/usr/share/rustdesk/files"
\t  install -Dm 644 $HBB/res/rustdesk.desktop -t "${pkgdir}/usr/share/rustdesk/files"
\t  install -Dm 644 $HBB/res/rustdesk-link.desktop -t "${pkgdir}/usr/share/rustdesk/files"
}
'''

PACMAN_INSTALL = '''post_install() {
\tcp /usr/share/rustdesk/files/rustdesk.service /etc/systemd/system/rustdesk.service
\tcp /usr/share/rustdesk/files/rustdesk.desktop /usr/share/applications/
\tcp /usr/share/rustdesk/files/rustdesk-link.desktop /usr/share/applications/
\tsystemctl daemon-reload
\tsystemctl enable rustdesk
\tsystemctl start rustdesk
}
pre_upgrade() {
\tsystemctl stop rustdesk || true
}
post_upgrade() {
\tcp /usr/share/rustdesk/files/rustdesk.service /etc/systemd/system/rustdesk.service
\tcp /usr/share/rustdesk/files/rustdesk.desktop /usr/share/applications/
\tcp /usr/share/rustdesk/files/rustdesk-link.desktop /usr/share/applications/
\tsystemctl daemon-reload
\tsystemctl enable rustdesk
\tsystemctl start rustdesk
}
post_remove() {
\trm /usr/share/applications/rustdesk.desktop || true
\trm /usr/share/applications/rustdesk-link.desktop || true
}
'''

DESKTOP = '''[Desktop Entry]
Name=RustDesk
Exec=rustdesk %u
Icon=rustdesk
TryExec=rustdesk
StartupWMClass=rustdesk
MimeType=x-scheme-handler/rustdesk;
'''

SERVICE = '''[Unit]
Description=RustDesk
[Service]
ExecStart=/usr/bin/rustdesk --service
ExecStop=pkill -f "rustdesk --"
PIDFile=/run/rustdesk.pid
'''

APPIMAGE_RECIPE = '''version: 1
script:
 - bsdtar -zxvf rustdesk.deb
 - cp ../res/32x32.png ./AppDir/usr/share/icons/hicolor/32x32/apps/rustdesk.png
 - cp ../res/scalable.svg ./AppDir/usr/share/icons/hicolor/scalable/apps/rustdesk.svg
AppDir:
  app_info:
    id: rustdesk
    name: rustdesk
    icon: rustdesk
    exec: usr/share/rustdesk/rustdesk
  runtime:
    env:
      APPDIR_LIBRARY_PATH: $APPDIR/usr/share/rustdesk/lib
'''

METAINFO = '''<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>com.rustdesk.RustDesk</id>
  <developer id="com.rustdesk"><name>RustDesk</name></developer>
  <launchable type="desktop-id">com.rustdesk.RustDesk.desktop</launchable>
  <name>RustDesk</name>
  <summary>Secure remote desktop access</summary>
  <description><p>RustDesk remote access.</p></description>
  <screenshots><screenshot><image>https://rustdesk.com/s.png</image></screenshot></screenshots>
  <branding><color type="primary">#000000</color></branding>
  <url type="homepage">https://rustdesk.com</url>
  <url type="help">https://rustdesk.com/docs</url>
</component>
'''


class LinuxPackagingCustomizationTests(unittest.TestCase):
    filename = "RustDesk"
    app_name = "Custom Desk"
    company = "Example Company"
    url_link = "https://example.com/product"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "res" / "DEBIAN").mkdir(parents=True)
        self.write("build.py", BUILD_PY)
        self.write("res/rpm-flutter.spec", RPM_SPEC)
        self.write("res/rpm-flutter-suse.spec", RPM_SPEC)
        self.write("res/PKGBUILD", PKGBUILD)
        self.write("res/pacman_install", PACMAN_INSTALL)
        self.write("res/rustdesk.desktop", DESKTOP)
        self.write("res/rustdesk-link.desktop", DESKTOP)
        self.write("res/rustdesk.service", SERVICE)
        self.write("res/DEBIAN/postinst", "#!/bin/bash\nsystemctl start rustdesk\n")
        self.write("res/DEBIAN/prerm", "#!/bin/bash\nsystemctl stop rustdesk || true\n")
        self.write(
            "res/DEBIAN/postrm",
            "#!/bin/bash\nrm -rf /root/.config/rustdesk || true\n",
        )
        self.write("appimage/AppImageBuilder-x86_64.yml", APPIMAGE_RECIPE)
        self.write(
            "flatpak/rustdesk.json",
            json.dumps(
                {
                    "id": "com.rustdesk.RustDesk",
                    "command": "rustdesk",
                    "rename-desktop-file": "rustdesk.desktop",
                    "rename-icon": "rustdesk",
                    "modules": [
                        {
                            "name": "rustdesk",
                            "build-commands": [
                                "bsdtar -Oxf rustdesk.deb data.tar.xz | bsdtar -xf -",
                                "mkdir -p /app/bin && ln -s /app/share/rustdesk/rustdesk /app/bin/rustdesk",
                            ],
                            "sources": [
                                {"type": "file", "path": "rustdesk.deb"},
                                {
                                    "type": "file",
                                    "path": "com.rustdesk.RustDesk.metainfo.xml",
                                },
                            ],
                        }
                    ],
                    "finish-args": ["--device=dri", "--device=all", "--device=all"],
                },
                indent=2,
            )
            + "\n",
        )
        self.write("flatpak/com.rustdesk.RustDesk.metainfo.xml", METAINFO)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative_path: str, content: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_native_metadata_layout_and_repeatability(self):
        for _ in range(2):
            native.patch_build_script(
                self.root / "build.py", self.filename, self.app_name
            )
            for name in ("rpm-flutter.spec", "rpm-flutter-suse.spec"):
                native.patch_rpm(
                    self.root / "res" / name,
                    self.filename,
                    self.app_name,
                    self.company,
                    self.url_link,
                )
            native.patch_pkgbuild(
                self.root / "res" / "PKGBUILD",
                self.filename,
                self.app_name,
                self.url_link,
            )
            native.patch_pacman_install(
                self.root / "res" / "pacman_install", self.filename
            )
            native.patch_desktop(
                self.root / "res" / "rustdesk.desktop",
                self.filename,
                self.app_name,
            )
            native.patch_desktop(
                self.root / "res" / "rustdesk-link.desktop",
                self.filename,
                self.app_name,
            )
            native.patch_service(
                self.root / "res" / "rustdesk.service",
                self.filename,
                self.app_name,
            )
            native.patch_debian_scripts(
                self.root / "res" / "DEBIAN", self.filename, self.app_name
            )

        build_text = (self.root / "build.py").read_text(encoding="utf-8")
        build_block = build_text.split("def build_flutter_deb", 1)[1].split(
            "\ndef build_deb_from_folder", 1
        )[0]
        self.assertIn("tmpdeb/usr/share/RustDesk/custom_.txt", build_block)
        self.assertIn("tmpdeb/etc/custom desk/xorg.conf", build_block)
        self.assertIn("tmpdeb/etc/pam.d/custom desk", build_block)
        self.assertNotIn("tmpdeb/usr/share/rustdesk/", build_block)

        rpm = (self.root / "res" / "rpm-flutter.spec").read_text(encoding="utf-8")
        self.assertIn("Name:       rustdesk", rpm)
        self.assertIn(f"Summary:    {self.app_name}", rpm)
        self.assertIn(f"URL:        {self.url_link}", rpm)
        self.assertIn(f"Vendor:     {self.company}", rpm)
        self.assertIn("/usr/share/RustDesk/RustDesk", rpm)
        self.assertNotIn("sudoers.d", rpm)
        self.assertEqual(rpm.count(native.UDEV_REFRESH_MARKER), 1)

        pacman = (self.root / "res" / "pacman_install").read_text(encoding="utf-8")
        self.assertEqual(pacman.count(native.UDEV_REFRESH_MARKER), 2)
        self.assertEqual(pacman.count("udevadm trigger --name-match=uinput"), 2)

        desktop = (self.root / "res" / "rustdesk.desktop").read_text(encoding="utf-8")
        self.assertIn(f"Name={self.app_name}", desktop)
        self.assertIn("Exec=RustDesk %u", desktop)
        self.assertIn(
            f"MimeType=x-scheme-handler/{native.uri_scheme(self.filename)};", desktop
        )
        service = (self.root / "res" / "rustdesk.service").read_text(encoding="utf-8")
        self.assertIn(f"Description={self.app_name}", service)
        self.assertIn("ExecStart=/usr/bin/RustDesk --service", service)
        postrm = (self.root / "res" / "DEBIAN" / "postrm").read_text(
            encoding="utf-8"
        )
        self.assertIn("/root/.config/customdesk", postrm)
        self.assertNotIn("/root/.config/RustDesk", postrm)
        cleanup = next(line for line in postrm.splitlines() if "rm -rf" in line)
        target = cleanup.split("rm -rf", 1)[1].split("||", 1)[0].strip()
        self.assertEqual(shlex.split(target), ["/root/.config/customdesk"])

    def test_smart_linux_customization_omits_beijing_runtime(self):
        native.patch_build_script(
            self.root / "build.py", self.filename, self.app_name
        )
        for name in ("rpm-flutter.spec", "rpm-flutter-suse.spec"):
            native.patch_rpm(
                self.root / "res" / name,
                self.filename,
                self.app_name,
                self.company,
                self.url_link,
                False,
            )
        native.patch_pkgbuild(
            self.root / "res" / "PKGBUILD",
            self.filename,
            self.app_name,
            self.url_link,
            False,
        )
        native.patch_pacman_install(
            self.root / "res" / "pacman_install", self.filename, False
        )

        rpm = (self.root / "res" / "rpm-flutter.spec").read_text(encoding="utf-8")
        pkgbuild = (self.root / "res" / "PKGBUILD").read_text(encoding="utf-8")
        pacman = (self.root / "res" / "pacman_install").read_text(encoding="utf-8")
        self.assertIn(f"/usr/share/{self.filename}/custom_.txt", rpm)
        self.assertIn(f"/usr/share/{self.filename}/custom_.txt", pkgbuild)
        for text in (rpm, pkgbuild, pacman):
            self.assertNotIn(".rdgen-beijing", text)
            self.assertNotIn("librustdesk_no_sysvipc.so", text)
            self.assertNotIn(native.UDEV_REFRESH_MARKER, text)

        appimage_path = self.root / "appimage" / "AppImageBuilder-x86_64.yml"
        for _ in range(2):
            appimage.customize(
                appimage_path, self.filename, self.app_name, False
            )
        appimage_text = appimage_path.read_text(encoding="utf-8")
        self.assertIn(f"usr/share/{self.filename}/{self.filename}", appimage_text)
        self.assertNotIn("librustdesk_no_sysvipc.so", appimage_text)

        manifest_path = self.root / "flatpak" / "rustdesk.json"
        for _ in range(2):
            flatpak.customize(
                manifest_path,
                self.filename,
                self.app_name,
                self.company,
                self.url_link,
                False,
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertFalse(
            any("librustdesk_no_sysvipc.so" in arg for arg in manifest["finish-args"])
        )

    def test_debian_purge_quotes_shell_glob_characters(self):
        directory = self.root / "purge-quote" / "DEBIAN"
        directory.mkdir(parents=True)
        path = directory / "postrm"
        path.write_text(
            "#!/bin/bash\nrm -rf /root/.config/rustdesk || true\n",
            encoding="utf-8",
        )
        native.patch_debian_scripts(directory, "Client", "Custom [Desk]")
        text = path.read_text(encoding="utf-8")
        self.assertIn("'/root/.config/custom[desk]'", text)

    def test_build_script_accepts_aarch64_and_rustdesk_prefix_names(self):
        path = self.write(
            "build-aarch64.py",
            BUILD_PY.replace(
                "flutter build linux --release", "flutter-elinux build linux --verbose"
            ),
        )
        for _ in range(2):
            native.patch_build_script(path, "rustdesk2", "Unicode Desk")
        text = path.read_text(encoding="utf-8")
        self.assertIn("tmpdeb/usr/share/rustdesk2/custom_.txt", text)
        self.assertIn("flutter-elinux build linux --verbose", text)

    def test_build_script_keeps_original_rustdesk_executable_in_place(self):
        path = self.write("build-rustdesk.py", BUILD_PY)
        for _ in range(2):
            native.patch_build_script(path, "rustdesk", "RustDesk")
        text = path.read_text(encoding="utf-8")
        self.assertIn("tmpdeb/usr/share/rustdesk/custom_.txt", text)
        self.assertNotIn(
            "mv {flutter_build_dir}rustdesk {flutter_build_dir}rustdesk", text
        )

        desktop = self.write("res/rustdesk-default-link.desktop", DESKTOP)
        for _ in range(2):
            native.patch_desktop(desktop, "rustdesk", "RustDesk")
        desktop_text = desktop.read_text(encoding="utf-8")
        self.assertIn(
            f"MimeType=x-scheme-handler/{native.uri_scheme('rustdesk')};",
            desktop_text,
        )

    def test_linux_uri_scheme_is_valid_unique_and_matches_runtime_patch(self):
        upper = native.uri_scheme("Client_A")
        lower = native.uri_scheme("client-a")
        self.assertRegex(upper, r"^[a-z][a-z0-9+.-]*$")
        self.assertNotEqual(upper, lower)
        source = allow_custom.URI_PREFIX_FUNCTION
        patched = allow_custom.patch_uri_prefix(source, "Client_A")
        patched = allow_custom.patch_uri_prefix(patched, "Client_A")
        self.assertIn(f'"{upper}://".to_owned()', patched)

        linux_source = '''        let app_name_lower = crate::get_app_name().to_lowercase();
        let app_name0 = crate::get_app_name();
        let config_subdir = format!(".config/{}", app_name_lower);'''
        linux_patched = allow_custom.patch_linux_project_config(linux_source)
        linux_patched = allow_custom.patch_linux_project_config(linux_patched)
        self.assertIn(".split_whitespace()", linux_patched)

    def test_project_config_name_matches_segmented_unicode_lowercase(self):
        self.assertEqual(native.project_config_name("ΟΣ Α"), "οςα")
        self.assertNotEqual(native.project_config_name("ΟΣ Α"), "οσα")

    def test_flatpak_workflow_uses_modern_native_builder_and_guards_same_file_move(self):
        workflow = (PATCH_DIR.parent / "workflows" / "generator-linux.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("on: ubuntu-24.04,", workflow)
        self.assertIn("on: ubuntu-24.04-arm,", workflow)
        self.assertIn("sudo apt-get install -y git flatpak flatpak-builder python3", workflow)
        self.assertIn('dpkg --compare-versions "$builder_version" ge 1.3.4', workflow)
        flatpak_job = workflow.split("\n  build-flatpak:\n", 1)[1].split(
            "\n  deploy:\n", 1
        )[0]
        self.assertNotIn("rustdesk-org/run-on-arch-action@amd64-support", flatpak_job)
        self.assertIn(
            'if [[ "${{ env.filename }}" != "rustdesk" ]]; then', workflow
        )

    def test_native_helper_parses_as_python_3_6(self):
        source = (PATCH_DIR / "customize_linux_native_packages.py").read_text(
            encoding="utf-8"
        )
        ast.parse(source, filename="customize_linux_native_packages.py", feature_version=6)

    def test_rpm_metadata_rejects_macro_expansion(self):
        unsafe = (
            ("Client%(printf unsafe)", self.company, self.url_link),
            (self.app_name, "Company%{lua:unsafe}", self.url_link),
            (self.app_name, self.company, "https://example.com/%{unsafe}"),
        )
        for index, values in enumerate(unsafe):
            with self.subTest(values=values):
                path = self.write(f"unsafe-{index}.spec", RPM_SPEC)
                with self.assertRaises(SystemExit):
                    native.patch_rpm(path, "SafeName", *values)

    def test_rpm_metadata_rejects_whitespace_in_url(self):
        path = self.write("unsafe-url.spec", RPM_SPEC)
        with self.assertRaises(SystemExit):
            native.patch_rpm(
                path,
                "SafeName",
                self.app_name,
                self.company,
                "https://example.com/a b",
            )

    def test_arch_metadata_rejects_shell_substitution(self):
        with self.assertRaises(SystemExit):
            native.patch_pkgbuild(
                self.root / "res" / "PKGBUILD",
                "SafeName",
                "$(touch unsafe)",
                self.url_link,
            )

    def test_appimage_keeps_display_and_machine_names_separate(self):
        path = self.root / "appimage" / "AppImageBuilder-x86_64.yml"
        for _ in range(2):
            appimage.customize(path, self.filename, self.app_name)
        text = path.read_text(encoding="utf-8")
        self.assertIn('    id: "RustDesk"', text)
        self.assertIn(f'    name: "{self.app_name}"', text)
        self.assertIn('    icon: "RustDesk"', text)
        self.assertIn("    exec: usr/share/RustDesk/RustDesk", text)
        self.assertIn("$APPDIR/usr/lib/RustDesk/librustdesk_no_sysvipc.so", text)

    def test_appimage_quotes_yaml_keyword_and_numeric_names(self):
        for filename in ("on", "no", "null", "123"):
            with self.subTest(filename=filename):
                path = self.write(f"appimage/{filename}.yml", APPIMAGE_RECIPE)
                appimage.customize(path, filename, self.app_name)
                text = path.read_text(encoding="utf-8")
                self.assertIn(f'    id: "{filename}"', text)
                self.assertIn(f'    icon: "{filename}"', text)

    def test_flatpak_uses_independent_identity_and_restrained_devices(self):
        manifest_path = self.root / "flatpak" / "rustdesk.json"
        for _ in range(2):
            flatpak.customize(
                manifest_path,
                self.filename,
                self.app_name,
                self.company,
                self.url_link,
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        app_id = flatpak.application_id(self.filename)
        metainfo_name = f"{app_id}.metainfo.xml"
        self.assertEqual(manifest["id"], app_id)
        self.assertEqual(manifest["command"], self.filename)
        self.assertEqual(manifest["rename-desktop-file"], f"{self.filename}.desktop")
        self.assertIn("--device=dri", manifest["finish-args"])
        self.assertNotIn("--device=all", manifest["finish-args"])

        module = next(
            item
            for item in manifest["modules"]
            if isinstance(item, dict) and item.get("name") == "rustdesk"
        )
        self.assertIn(
            f"install -Dm644 {metainfo_name} /app/share/metainfo/{metainfo_name}",
            module["build-commands"],
        )
        source_paths = [source["path"] for source in module["sources"]]
        self.assertIn(metainfo_name, source_paths)
        self.assertNotIn("com.rustdesk.RustDesk.metainfo.xml", source_paths)

        metainfo_path = self.root / "flatpak" / metainfo_name
        root = ET.parse(metainfo_path).getroot()
        self.assertEqual(root.findtext("./id"), app_id)
        self.assertEqual(root.findtext("./launchable"), f"{app_id}.desktop")
        self.assertEqual(root.findtext("./name"), self.app_name)
        self.assertEqual(root.find("./developer").get("id"), "com.rdgen")
        self.assertEqual(root.findtext("./developer/name"), self.company)
        self.assertEqual(root.findtext("./url[@type='homepage']"), self.url_link)
        self.assertEqual(len(root.findall("./url")), 1)
        self.assertIsNone(root.find("./screenshots"))
        self.assertIsNone(root.find("./branding"))
        self.assertNotIn("RustDesk", ET.tostring(root, encoding="unicode"))
        self.assertFalse(
            (self.root / "flatpak" / "com.rustdesk.RustDesk.metainfo.xml").exists()
        )

    def test_flatpak_ids_do_not_collide_for_hyphen_and_underscore(self):
        self.assertNotEqual(
            flatpak.application_id("Client-A"), flatpak.application_id("Client_A")
        )

    def test_flatpak_ids_preserve_filename_case(self):
        self.assertNotEqual(
            flatpak.application_id("Client"), flatpak.application_id("client")
        )

    def test_flatpak_rejects_invalid_homepage_url(self):
        for url in ("not-a-url", "https://example.com/a b"):
            with self.subTest(url=url), self.assertRaises(SystemExit):
                flatpak.customize(
                    self.root / "flatpak" / "rustdesk.json",
                    self.filename,
                    self.app_name,
                    self.company,
                    url,
                )

    def test_flatpak_description_is_repeatable_when_name_contains_rustdesk(self):
        manifest_path = self.root / "flatpak" / "rustdesk.json"
        app_name = "Acme RustDesk"
        for _ in range(2):
            flatpak.customize(
                manifest_path,
                self.filename,
                app_name,
                self.company,
                self.url_link,
            )
        app_id = flatpak.application_id(self.filename)
        root = ET.parse(self.root / "flatpak" / f"{app_id}.metainfo.xml").getroot()
        description = ET.tostring(root.find("./description"), encoding="unicode")
        self.assertIn(app_name, description)
        self.assertNotIn("Acme Acme RustDesk", description)

    def test_legacy_world_writable_uinput_is_removed(self):
        legacy = '''#!/bin/bash
systemctl enable RustDesk
# Beijing custom uinput compatibility: allow the user-mode server to open /dev/uinput.
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
    udevadm trigger --name-match=uinput || true
fi
if [ -e /dev/uinput ]; then
    chmod 0666 /dev/uinput || true
fi
# Beijing custom compatibility: restart so the drop-in applies on upgrades.
systemctl restart RustDesk || systemctl start RustDesk
'''
        path = self.write("res/DEBIAN/postinst", legacy)
        beijing.patch_postinst(self.root, "RustDesk")
        beijing.patch_postinst(self.root, "RustDesk")
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("chmod 0666", text)
        self.assertEqual(text.count(beijing.MARKER), 1)
        self.assertIn("udevadm trigger --name-match=uinput", text)

        rule_root = self.root / "rule-test"
        beijing.write_uinput_udev_rule(rule_root, "RustDesk")
        rule = next(rule_root.rglob("*.rules")).read_text(encoding="utf-8")
        self.assertIn('MODE="0660", TAG+="uaccess"', rule)
        self.assertNotIn('MODE="0666"', rule)

    def test_packaging_scripts_do_not_restore_ld_sudoers(self):
        script = (PATCH_DIR / "beijing_custom_linux_packaging.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("env_delete", script)
        self.assertNotIn("setenv", script)


if __name__ == "__main__":
    unittest.main()
