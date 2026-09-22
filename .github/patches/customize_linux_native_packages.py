import argparse
import re
import shlex
from pathlib import Path
from typing import Tuple


ROOT = Path.cwd()
UDEV_REFRESH_MARKER = "# RDGen uinput rules"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--filename", required=True)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--url-link", required=True)
    parser.add_argument("--without-beijing-runtime", action="store_true")
    return parser.parse_args()


def validate_filename(filename: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]+", filename):
        raise SystemExit(f"Invalid Linux package name: {filename!r}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", package_name(filename)):
        raise SystemExit(f"Invalid normalized Linux package name: {filename!r}")


def validate_value(value: str, label: str) -> None:
    if not value or any(character in value for character in "\x00\r\n%"):
        raise SystemExit(f"Invalid {label}: {value!r}")


def validate_rpm_url(value: str) -> None:
    validate_value(value, "RPM URL")
    if any(character.isspace() for character in value):
        raise SystemExit(f"Invalid RPM URL: {value!r}")


def quote_shell_double(value: str, label: str) -> str:
    if any(character in value for character in '"`$\\'):
        raise SystemExit(f"Unsafe {label} for package metadata: {value!r}")
    return f'"{value}"'


def package_name(filename: str) -> str:
    return filename.lower().replace("_", "-")


def uri_scheme(filename: str) -> str:
    validate_filename(filename)
    return f"rdgen-{filename.encode('ascii').hex()}"


def runtime_name(app_name: str) -> str:
    value = app_name.lower()
    if value in {".", ".."} or any(character in value for character in "/\\"):
        raise SystemExit(f"Invalid Linux runtime application name: {app_name!r}")
    return value


def project_config_name(app_name: str) -> str:
    value = "".join(part.lower() for part in app_name.split())
    if not value or value in {".", ".."} or any(
        character in value for character in "/\\"
    ):
        raise SystemExit(f"Invalid Linux project configuration name: {app_name!r}")
    return value


def replace_exact(text: str, old: str, new: str, path: Path, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"Unable to identify {label} in {path}")
    return text.replace(old, new, 1)


def set_line(text: str, pattern: str, replacement: str, path: Path, label: str) -> str:
    updated, count = re.subn(
        pattern,
        lambda _match: replacement,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit(f"Unable to identify {label} in {path}")
    return updated


def require_all(path: Path, text: str, expected: Tuple[str, ...]) -> None:
    missing = [value for value in expected if value not in text]
    if missing:
        raise SystemExit(f"Incomplete Linux package customization in {path}: {missing}")


def remove_legacy_sudoers_references(text: str, filename: str) -> str:
    marker = f"/etc/sudoers.d/{filename}-ld-preload"
    return "".join(line for line in text.splitlines(keepends=True) if marker not in line)


def replace_machine_name_outside_headers(
    text: str, filename: str, header_prefixes: Tuple[str, ...]
) -> str:
    lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith(header_prefixes):
            lines.append(line)
        else:
            lines.append(line.replace("rustdesk", filename))
    return "".join(lines)


def restore_resource_sources(text: str, filename: str) -> str:
    for source_name in ("rustdesk.service", "rustdesk.desktop", "rustdesk-link.desktop"):
        text = text.replace(
            source_name.replace("rustdesk", f"$HBB/res/{filename}"),
            f"$HBB/res/{source_name}",
        )
    return text


def udev_refresh_block(indent: str = "") -> str:
    return "\n".join(
        (
            f"{indent}{UDEV_REFRESH_MARKER}",
            f"{indent}if command -v udevadm >/dev/null 2>&1; then",
            f"{indent}    udevadm control --reload-rules || true",
            f"{indent}    udevadm trigger --name-match=uinput || true",
            f"{indent}fi",
        )
    )


def add_udev_refresh(
    text: str, anchor: str, path: Path, expected_count: int, indent: str = ""
) -> str:
    marker = f"{indent}{UDEV_REFRESH_MARKER}"
    marker_count = text.count(marker)
    if marker_count == expected_count:
        return text
    if marker_count != 0 or text.count(anchor) != expected_count:
        raise SystemExit(f"Unable to identify udev refresh hooks in {path}")
    return text.replace(anchor, udev_refresh_block(indent) + "\n" + anchor)


def patch_build_script(path: Path, filename: str, app_name: str) -> None:
    validate_filename(filename)
    validate_value(app_name, "application name")
    config_name = runtime_name(app_name)
    text = path.read_text(encoding="utf-8")
    function_start = text.find("def build_flutter_deb(version, features):")
    function_end = text.find("\ndef build_deb_from_folder", function_start)
    if function_start < 0 or function_end < 0:
        raise SystemExit(f"Unable to identify Flutter DEB builder in {path}")

    marker = f"    # RDGen Linux layout: {filename} / {config_name}\n"
    block = text[function_start:function_end]
    if marker in block:
        require_all(
            path,
            block,
            (
                f"tmpdeb/usr/share/{filename}/custom_.txt",
                f"tmpdeb/usr/share/{filename}/files/systemd/{filename}.service",
                f"tmpdeb/etc/{config_name}/xorg.conf",
                f"tmpdeb/etc/pam.d/{config_name}",
                f"tmpdeb/usr/share/applications/{filename}.desktop",
            ),
        )
        return

    block = replace_exact(
        block,
        "def build_flutter_deb(version, features):\n",
        "def build_flutter_deb(version, features):\n" + marker,
        path,
        "Flutter DEB function",
    )
    build_commands = (
        "    system2('flutter build linux --release')",
        "    system2('flutter-elinux build linux --verbose')",
    )
    matched_commands = [command for command in build_commands if command in block]
    if len(matched_commands) != 1:
        raise SystemExit(f"Unable to identify Flutter build command in {path}")
    build_command = matched_commands[0]
    if filename != "rustdesk":
        block = replace_exact(
            block,
            build_command,
            build_command
            + "\n"
            + f"    system2(f'mv {{flutter_build_dir}}rustdesk {{flutter_build_dir}}{filename}')",
            path,
            "Flutter executable rename",
        )

    machine_root = f"tmpdeb/usr/share/{filename}"
    config_root = f"tmpdeb/etc/{config_name}"
    replacements = (
        (
            "    system2('mkdir -p tmpdeb/usr/share/rustdesk')",
            f"    system2('mkdir -p {machine_root}')\n"
            f"    system2('cp ../custom_.txt {machine_root}/custom_.txt')",
            "DEB application directory",
        ),
        (
            "    system2('mkdir -p tmpdeb/etc/rustdesk/')",
            f"    system2({('mkdir -p ' + shlex.quote(config_root + '/'))!r})",
            "DEB runtime configuration directory",
        ),
        (
            "    system2('mkdir -p tmpdeb/usr/share/rustdesk/files/systemd/')",
            f"    system2('mkdir -p {machine_root}/files/systemd/')",
            "DEB service staging directory",
        ),
        (
            "    system2('rm tmpdeb/usr/bin/rustdesk || true')",
            f"    system2('rm tmpdeb/usr/bin/{filename} || true')",
            "DEB stale executable cleanup",
        ),
        (
            "    system2(\n        f'cp -r {flutter_build_dir}/* tmpdeb/usr/share/rustdesk/')",
            f"    system2(\n        f'cp -r {{flutter_build_dir}}/* {machine_root}/')",
            "DEB Flutter bundle copy",
        ),
        (
            "    system2(\n        'cp ../res/rustdesk.service tmpdeb/usr/share/rustdesk/files/systemd/')",
            f"    system2(\n        'cp ../res/rustdesk.service {machine_root}/files/systemd/{filename}.service')",
            "DEB service copy",
        ),
        (
            "    system2(\n        'cp ../res/128x128@2x.png tmpdeb/usr/share/icons/hicolor/256x256/apps/rustdesk.png')",
            f"    system2(\n        'cp ../res/128x128@2x.png tmpdeb/usr/share/icons/hicolor/256x256/apps/{filename}.png')",
            "DEB PNG icon copy",
        ),
        (
            "    system2(\n        'cp ../res/scalable.svg tmpdeb/usr/share/icons/hicolor/scalable/apps/rustdesk.svg')",
            f"    system2(\n        'cp ../res/scalable.svg tmpdeb/usr/share/icons/hicolor/scalable/apps/{filename}.svg')",
            "DEB SVG icon copy",
        ),
        (
            "    system2(\n        'cp ../res/rustdesk.desktop tmpdeb/usr/share/applications/rustdesk.desktop')",
            f"    system2(\n        'cp ../res/rustdesk.desktop tmpdeb/usr/share/applications/{filename}.desktop')",
            "DEB desktop entry copy",
        ),
        (
            "    system2(\n        'cp ../res/rustdesk-link.desktop tmpdeb/usr/share/applications/rustdesk-link.desktop')",
            f"    system2(\n        'cp ../res/rustdesk-link.desktop tmpdeb/usr/share/applications/{filename}-link.desktop')",
            "DEB URL desktop entry copy",
        ),
        (
            "    system2(\n        'cp ../res/startwm.sh tmpdeb/etc/rustdesk/')",
            f"    system2({('cp ../res/startwm.sh ' + shlex.quote(config_root + '/startwm.sh'))!r})",
            "DEB window-manager script copy",
        ),
        (
            "    system2(\n        'cp ../res/xorg.conf tmpdeb/etc/rustdesk/')",
            f"    system2({('cp ../res/xorg.conf ' + shlex.quote(config_root + '/xorg.conf'))!r})",
            "DEB Xorg configuration copy",
        ),
        (
            "    system2(\n        'cp ../res/pam.d/rustdesk.debian tmpdeb/etc/pam.d/rustdesk')",
            f"    system2({('cp ../res/pam.d/rustdesk.debian ' + shlex.quote('tmpdeb/etc/pam.d/' + config_name))!r})",
            "DEB PAM configuration copy",
        ),
        (
            '    system2(\n        "echo \\"#!/bin/sh\\" >> tmpdeb/usr/share/rustdesk/files/polkit && chmod a+x tmpdeb/usr/share/rustdesk/files/polkit")',
            f'    system2(\n        "echo \\"#!/bin/sh\\" >> {machine_root}/files/polkit && chmod a+x {machine_root}/files/polkit")',
            "DEB polkit helper",
        ),
    )
    for old, new, label in replacements:
        block = replace_exact(block, old, new, path, label)

    expected = (
        f"tmpdeb/usr/share/{filename}/custom_.txt",
        f"tmpdeb/usr/share/{filename}/files/systemd/{filename}.service",
        f"tmpdeb/etc/{config_name}/xorg.conf",
        f"tmpdeb/etc/pam.d/{config_name}",
        f"tmpdeb/usr/share/applications/{filename}.desktop",
    )
    require_all(path, block, expected)
    if filename != "rustdesk" and re.search(
        r"tmpdeb/usr/share/rustdesk(?:/|['\"])", block
    ):
        raise SystemExit(f"Official RustDesk package path remains in {path}")

    text = text[:function_start] + block + text[function_end:]
    package_line = f"Package: {package_name(filename)}"
    if package_line not in text:
        text = replace_exact(
            text,
            "Package: rustdesk",
            package_line,
            path,
            "Debian package name",
        )
    path.write_text(text, encoding="utf-8")


def patch_rpm(
    path: Path,
    filename: str,
    app_name: str,
    company: str,
    url_link: str,
    include_beijing_runtime: bool = True,
) -> None:
    validate_value(app_name, "RPM summary")
    validate_value(company, "RPM vendor")
    validate_rpm_url(url_link)
    text = path.read_text(encoding="utf-8")
    custom_marker = f'"%{{buildroot}}/usr/share/{filename}/custom_.txt"'
    if custom_marker not in text:
        text = replace_machine_name_outside_headers(
            text,
            filename,
            ("Name:", "Summary:", "URL:", "Vendor:"),
        )
        text = restore_resource_sources(text, filename)

        for source_name, destination_name in (
            ("rustdesk.service", f"{filename}.service"),
            ("rustdesk.desktop", f"{filename}.desktop"),
            ("rustdesk-link.desktop", f"{filename}-link.desktop"),
        ):
            source = f"$HBB/res/{source_name}"
            old = f'install -Dm 644 {source} -t "%{{buildroot}}/usr/share/{filename}/files"'
            new = (
                f'install -Dm 644 {source} '
                f'"%{{buildroot}}/usr/share/{filename}/files/{destination_name}"'
            )
            if old not in text:
                raise SystemExit(
                    f"Unable to identify RPM resource install in {path}: {source_name}"
                )
            text = text.replace(old, new, 1)

        copy_bundle = (
            f'mkdir -p "%{{buildroot}}/usr/share/{filename}" && cp -r '
            f'${{HBB}}/flutter/build/linux/x64/release/bundle/* -t '
            f'"%{{buildroot}}/usr/share/{filename}"'
        )
        if copy_bundle not in text:
            raise SystemExit(f"Unable to identify customized bundle copy in {path}")
        install_compat = ""
        if include_beijing_runtime:
            install_compat = "\n" + "\n".join(
                [
                    f'install -Dm 755 ${{HBB}}/.rdgen-beijing/usr/lib/{filename}/librustdesk_no_sysvipc.so "%{{buildroot}}/usr/lib/{filename}/librustdesk_no_sysvipc.so"',
                    f'install -Dm 644 ${{HBB}}/.rdgen-beijing/etc/systemd/system/{filename}.service.d/beijing-custom.conf "%{{buildroot}}/etc/systemd/system/{filename}.service.d/beijing-custom.conf"',
                    f'install -Dm 644 ${{HBB}}/.rdgen-beijing/etc/udev/rules.d/99-{filename}-uinput.rules "%{{buildroot}}/etc/udev/rules.d/99-{filename}-uinput.rules"',
                ]
            )
        text = text.replace(
            copy_bundle,
            copy_bundle
            + f'\ninstall -Dm 644 ${{HBB}}/custom_.txt '
            + f'"%{{buildroot}}/usr/share/{filename}/custom_.txt"\n'
            + install_compat,
            1,
        )

        files_marker = f"/usr/share/{filename}/*\n"
        if text.count(files_marker) != 1:
            raise SystemExit(f"Unable to identify RPM files section in {path}")
        compat_files = ""
        if include_beijing_runtime:
            compat_files = "\n".join(
                [
                    f"/usr/lib/{filename}/librustdesk_no_sysvipc.so",
                    f"/etc/systemd/system/{filename}.service.d/beijing-custom.conf",
                    f"/etc/udev/rules.d/99-{filename}-uinput.rules",
                ]
            )
            text = text.replace(files_marker, files_marker + compat_files + "\n", 1)

    text = remove_legacy_sudoers_references(text, filename)
    text = set_line(text, r"^Name:\s+.*$", f"Name:       {package_name(filename)}", path, "RPM name")
    text = set_line(text, r"^Summary:\s+.*$", f"Summary:    {app_name}", path, "RPM summary")
    text = set_line(text, r"^URL:\s+.*$", f"URL:        {url_link}", path, "RPM URL")
    text = set_line(text, r"^Vendor:\s+.*$", f"Vendor:     {company}", path, "RPM vendor")
    if include_beijing_runtime:
        text = add_udev_refresh(
            text,
            f"systemctl daemon-reload\nsystemctl enable {filename}",
            path,
            expected_count=1,
        )
    expected = [
        f"Name:       {package_name(filename)}",
        f"Summary:    {app_name}",
        f"URL:        {url_link}",
        f"Vendor:     {company}",
        f"/usr/share/{filename}/*",
        f'"%{{buildroot}}/usr/share/{filename}/files/{filename}.service"',
    ]
    if include_beijing_runtime:
        expected.extend(
            (
                f"/usr/lib/{filename}/librustdesk_no_sysvipc.so",
                UDEV_REFRESH_MARKER,
                "udevadm control --reload-rules || true",
                "udevadm trigger --name-match=uinput || true",
            )
        )
    require_all(path, text, tuple(expected))
    if "sudoers.d" in text:
        raise SystemExit(f"Unsafe sudoers packaging remains in {path}")
    path.write_text(text, encoding="utf-8")


def patch_pkgbuild(
    path: Path,
    filename: str,
    app_name: str,
    url_link: str,
    include_beijing_runtime: bool = True,
) -> None:
    text = path.read_text(encoding="utf-8")
    custom_marker = f'"${{pkgdir}}/usr/share/{filename}/custom_.txt"'
    if custom_marker not in text:
        text = replace_machine_name_outside_headers(
            text,
            filename,
            ("pkgname=", "pkgdesc=", "url="),
        )
        text = restore_resource_sources(text, filename)

        for source_name, destination_name in (
            ("rustdesk.service", f"{filename}.service"),
            ("rustdesk.desktop", f"{filename}.desktop"),
            ("rustdesk-link.desktop", f"{filename}-link.desktop"),
        ):
            source = f"$HBB/res/{source_name}"
            old = f'install -Dm 644 {source} -t "${{pkgdir}}/usr/share/{filename}/files"'
            new = (
                f'install -Dm 644 {source} '
                f'"${{pkgdir}}/usr/share/{filename}/files/{destination_name}"'
            )
            if old not in text:
                raise SystemExit(f"Unable to identify Arch resource install: {source_name}")
            text = text.replace(old, new, 1)

        copy_bundle = (
            f'\t  mkdir -p "${{pkgdir}}/usr/share/{filename}" && cp -r '
            f'${{HBB}}/flutter/build/linux/x64/release/bundle/* -t '
            f'"${{pkgdir}}/usr/share/{filename}"'
        )
        if copy_bundle not in text:
            raise SystemExit("Unable to identify customized Arch bundle copy")
        install_compat = ""
        if include_beijing_runtime:
            install_compat = "\n" + "\n".join(
                [
                    f'\t  install -Dm 755 ${{HBB}}/.rdgen-beijing/usr/lib/{filename}/librustdesk_no_sysvipc.so "${{pkgdir}}/usr/lib/{filename}/librustdesk_no_sysvipc.so"',
                    f'\t  install -Dm 644 ${{HBB}}/.rdgen-beijing/etc/systemd/system/{filename}.service.d/beijing-custom.conf "${{pkgdir}}/etc/systemd/system/{filename}.service.d/beijing-custom.conf"',
                    f'\t  install -Dm 644 ${{HBB}}/.rdgen-beijing/etc/udev/rules.d/99-{filename}-uinput.rules "${{pkgdir}}/etc/udev/rules.d/99-{filename}-uinput.rules"',
                ]
            )
        text = text.replace(
            copy_bundle,
            copy_bundle
            + f'\n\t  install -Dm 644 ${{HBB}}/custom_.txt '
            + f'"${{pkgdir}}/usr/share/{filename}/custom_.txt"\n'
            + install_compat,
            1,
        )

    text = remove_legacy_sudoers_references(text, filename)
    text = set_line(text, r"^pkgname=.*$", f"pkgname={package_name(filename)}", path, "Arch package name")
    description_value = quote_shell_double(app_name, "Arch description")
    url_value = quote_shell_double(url_link, "Arch URL")
    text = set_line(text, r"^pkgdesc=.*$", f"pkgdesc={description_value}", path, "Arch description")
    text = set_line(text, r"^url=.*$", f"url={url_value}", path, "Arch URL")
    expected = [
        f"pkgname={package_name(filename)}",
        f"pkgdesc={description_value}",
        f"url={url_value}",
        f"/usr/share/{filename}/{filename}",
        f'"${{pkgdir}}/usr/share/{filename}/files/{filename}.service"',
    ]
    if include_beijing_runtime:
        expected.append(f"/usr/lib/{filename}/librustdesk_no_sysvipc.so")
    require_all(path, text, tuple(expected))
    if "sudoers.d" in text:
        raise SystemExit(f"Unsafe sudoers packaging remains in {path}")
    path.write_text(text, encoding="utf-8")


def patch_pacman_install(
    path: Path, filename: str, include_beijing_runtime: bool = True
) -> None:
    text = path.read_text(encoding="utf-8")
    custom_marker = f"/usr/share/{filename}/files/{filename}.service"
    if custom_marker not in text:
        if "/usr/share/rustdesk/files/rustdesk.service" not in text:
            raise SystemExit(f"Unable to customize pacman install hook in {path}")
        text = text.replace("rustdesk", filename)
    if include_beijing_runtime:
        text = add_udev_refresh(
            text,
            "\tsystemctl daemon-reload",
            path,
            expected_count=2,
            indent="\t",
        )
    expected = [
        f"/usr/share/{filename}/files/{filename}.service",
        f"/etc/systemd/system/{filename}.service",
        f"systemctl enable {filename}",
        f"systemctl start {filename}",
        f"systemctl stop {filename}",
        f"/usr/share/applications/{filename}.desktop",
        f"/usr/share/applications/{filename}-link.desktop",
    ]
    if include_beijing_runtime:
        expected.extend(
            (
                UDEV_REFRESH_MARKER,
                "udevadm control --reload-rules || true",
                "udevadm trigger --name-match=uinput || true",
            )
        )
    require_all(path, text, tuple(expected))
    path.write_text(text, encoding="utf-8")


def patch_desktop(path: Path, filename: str, app_name: str) -> None:
    scheme = uri_scheme(filename)
    text = path.read_text(encoding="utf-8")
    has_uri_handler = "MimeType=x-scheme-handler/" in text
    if f"Exec={filename} %u" not in text or f"Icon={filename}" not in text:
        replacements = {
            "Exec=rustdesk %u": f"Exec={filename} %u",
            "Icon=rustdesk": f"Icon={filename}",
            "TryExec=rustdesk": f"TryExec={filename}",
            "StartupWMClass=rustdesk": f"StartupWMClass={filename}",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
    if has_uri_handler and f"MimeType=x-scheme-handler/{scheme};" not in text:
        text, count = re.subn(
            r"MimeType=x-scheme-handler/[^;]+;",
            f"MimeType=x-scheme-handler/{scheme};",
            text,
            count=1,
        )
        if count != 1:
            raise SystemExit(f"Unable to identify URI handler in {path}")
    lines = []
    display_name_set = False
    for line in text.splitlines(keepends=True):
        if not display_name_set and line.startswith("Name="):
            newline = "\n" if line.endswith("\n") else ""
            lines.append(f"Name={app_name}{newline}")
            display_name_set = True
        else:
            lines.append(line)
    if not display_name_set:
        raise SystemExit(f"Desktop display name is missing in {path}")
    text = "".join(lines)
    expected = [f"Name={app_name}", f"Exec={filename} %u", f"Icon={filename}"]
    if has_uri_handler:
        expected.append(f"MimeType=x-scheme-handler/{scheme};")
    require_all(path, text, tuple(expected))
    path.write_text(text, encoding="utf-8")


def patch_service(path: Path, filename: str, app_name: str) -> None:
    text = path.read_text(encoding="utf-8")
    if f"ExecStart=/usr/bin/{filename} --service" not in text:
        replacements = {
            "ExecStart=/usr/bin/rustdesk --service": (
                f"ExecStart=/usr/bin/{filename} --service"
            ),
            'ExecStop=pkill -f "rustdesk --"': (
                f'ExecStop=pkill -f "{filename} --"'
            ),
            "PIDFile=/run/rustdesk.pid": f"PIDFile=/run/{filename}.pid",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
    lines = []
    description_set = False
    for line in text.splitlines(keepends=True):
        if line.startswith("Description="):
            newline = "\n" if line.endswith("\n") else ""
            lines.append(f"Description={app_name}{newline}")
            description_set = True
        else:
            lines.append(line)
    if not description_set:
        raise SystemExit(f"Service description is missing in {path}")
    text = "".join(lines)
    require_all(
        path,
        text,
        (f"Description={app_name}", f"ExecStart=/usr/bin/{filename} --service"),
    )
    path.write_text(text, encoding="utf-8")


def patch_debian_scripts(directory: Path, filename: str, app_name: str) -> None:
    config_name = project_config_name(app_name)
    config_path = shlex.quote(f"/root/.config/{config_name}")
    for path in directory.iterdir():
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            marker = f"# RDGen package name: {filename}\n"
            if marker not in text:
                text = text.replace("rustdesk", filename)
                lines = text.splitlines(keepends=True)
                insert_at = 1 if lines and lines[0].startswith("#!") else 0
                lines.insert(insert_at, marker)
                text = "".join(lines)
            if path.name == "postrm":
                for old_config_path in (
                    f"/root/.config/{filename}",
                    "/root/.config/rustdesk",
                ):
                    text = text.replace(old_config_path, config_path)
            path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    validate_filename(args.filename)
    app_name = args.app_name
    company = args.company.replace(r"\&", "&")
    validate_value(app_name, "application name")
    validate_value(company, "company")
    validate_value(args.url_link, "URL")
    include_beijing_runtime = not args.without_beijing_runtime

    patch_build_script(ROOT / "build.py", args.filename, app_name)
    for relative_path in ("res/rpm-flutter.spec", "res/rpm-flutter-suse.spec"):
        patch_rpm(
            ROOT / relative_path,
            args.filename,
            app_name,
            company,
            args.url_link,
            include_beijing_runtime,
        )
    patch_pkgbuild(
        ROOT / "res/PKGBUILD",
        args.filename,
        app_name,
        args.url_link,
        include_beijing_runtime,
    )
    patch_pacman_install(
        ROOT / "res/pacman_install", args.filename, include_beijing_runtime
    )
    patch_desktop(ROOT / "res/rustdesk.desktop", args.filename, app_name)
    patch_desktop(ROOT / "res/rustdesk-link.desktop", args.filename, app_name)
    patch_service(ROOT / "res/rustdesk.service", args.filename, app_name)
    patch_debian_scripts(ROOT / "res/DEBIAN", args.filename, app_name)
    print(f"Customized Linux package metadata and paths for {args.filename}")


if __name__ == "__main__":
    main()
