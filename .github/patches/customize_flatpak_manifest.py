from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="flatpak/rustdesk.json")
    parser.add_argument("--filename", required=True)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--url-link", required=True)
    parser.add_argument("--without-beijing-runtime", action="store_true")
    return parser.parse_args()


def validate_filename(filename: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]+", filename):
        raise SystemExit(f"Invalid Flatpak executable name: {filename!r}")


def application_id(filename: str) -> str:
    segment = filename.encode("ascii").hex()
    return f"com.rdgen.app_{segment}"


def validate_url(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or any(character.isspace() for character in value)
    ):
        raise SystemExit(f"Invalid Flatpak homepage URL: {value!r}")


def set_element_text(root: ET.Element, path: str, value: str, label: str) -> None:
    element = root.find(path)
    if element is None:
        raise SystemExit(f"Flatpak metainfo has no {label}")
    element.text = value


def patch_metainfo(
    path: Path, app_id: str, app_name: str, company: str, url_link: str
) -> None:
    if not path.is_file():
        raise SystemExit(f"Flatpak metainfo is missing: {path}")
    tree = ET.parse(path)
    root = tree.getroot()
    original_id = root.findtext("./id")
    set_element_text(root, "./id", app_id, "application ID")
    set_element_text(
        root, "./launchable[@type='desktop-id']", f"{app_id}.desktop", "desktop ID"
    )
    developer = root.find("./developer")
    if developer is None:
        raise SystemExit("Flatpak metainfo has no developer")
    developer.set("id", "com.rdgen")
    set_element_text(root, "./developer/name", company, "developer name")
    set_element_text(root, "./name", app_name, "application name")
    set_element_text(root, "./summary", f"Remote desktop access with {app_name}", "summary")
    description = root.find("./description")
    if description is None:
        raise SystemExit("Flatpak metainfo has no description")
    if original_id != app_id:
        for element in description.iter():
            if element.text:
                element.text = element.text.replace("RustDesk", app_name)
            if element.tail:
                element.tail = element.tail.replace("RustDesk", app_name)
    homepage = root.find("./url[@type='homepage']")
    if homepage is None:
        raise SystemExit("Flatpak metainfo has no homepage URL")
    homepage.text = url_link
    for element in list(root.findall("./url")):
        if element is not homepage:
            root.remove(element)
    for tag in ("screenshots", "branding"):
        element = root.find(f"./{tag}")
        if element is not None:
            root.remove(element)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def customize(
    path: Path,
    filename: str,
    app_name: str,
    company: str,
    url_link: str,
    include_beijing_runtime: bool = True,
) -> None:
    validate_filename(filename)
    validate_url(url_link)
    app_id = application_id(filename)
    manifest = json.loads(path.read_text(encoding="utf-8"))

    manifest["id"] = app_id
    manifest["command"] = filename
    manifest["rename-desktop-file"] = f"{filename}.desktop"
    manifest["rename-icon"] = filename
    finish_args = manifest.get("finish-args")
    if not isinstance(finish_args, list):
        raise SystemExit("Flatpak finish-args are missing")
    if include_beijing_runtime:
        preload_arg = f"--env=LD_PRELOAD=/app/lib/{filename}/librustdesk_no_sysvipc.so"
        if preload_arg not in finish_args:
            finish_args.append(preload_arg)
        for key, value in {
            "RUSTDESK_NO_SYSVIPC_SHIM_LOG": "0",
            "RUSTDESK_UINPUT_INPUT_FALLBACK": "0",
            "RUSTDESK_UINPUT_INPUT_LOG": "1",
            "RUSTDESK_XCB_MOUSE_FALLBACK": "1",
            "RUSTDESK_UINPUT_MOUSE_MODE": "anchor",
            "RUSTDESK_UINPUT_MOUSE_REL_SCALE": "2",
            "RUSTDESK_UINPUT_WIDTH": "1024",
            "RUSTDESK_UINPUT_HEIGHT": "600",
            "RUSTDESK_FORCE_CM_NO_UI": "1",
            "RUSTDESK_DISABLE_TRAY": "1",
            "RUSTDESK_PREWARM_CM_NO_UI": "1",
        }.items():
            env_arg = f"--env={key}={value}"
            if env_arg not in finish_args:
                finish_args.append(env_arg)
    while "--device=all" in finish_args:
        finish_args.remove("--device=all")

    modules = manifest.get("modules")
    if not isinstance(modules, list):
        raise SystemExit("Flatpak manifest has no modules list")

    rustdesk_module = next(
        (
            module
            for module in modules
            if isinstance(module, dict) and module.get("name") == "rustdesk"
        ),
        None,
    )
    if not rustdesk_module:
        raise SystemExit("Flatpak rustdesk module is missing")

    commands = rustdesk_module.get("build-commands")
    if not isinstance(commands, list):
        raise SystemExit("Flatpak rustdesk build commands are missing")

    link_index = next(
        (index for index, command in enumerate(commands) if "ln -s " in command), None
    )
    if link_index is None:
        raise SystemExit("Flatpak executable symlink command is missing")
    commands[link_index] = (
        f"mkdir -p /app/bin && ln -s /app/share/{filename}/{filename} "
        f"/app/bin/{filename}"
    )
    sources = rustdesk_module.get("sources")
    if not isinstance(sources, list):
        raise SystemExit("Flatpak rustdesk sources are missing")
    metainfo_sources = [
        source
        for source in sources
        if isinstance(source, dict)
        and isinstance(source.get("path"), str)
        and source["path"].endswith(".metainfo.xml")
    ]
    if len(metainfo_sources) != 1:
        raise SystemExit("Flatpak metainfo source is ambiguous")
    metainfo_name = f"{app_id}.metainfo.xml"
    metainfo_sources[0]["path"] = metainfo_name
    metainfo_install = (
        f"install -Dm644 {metainfo_name} /app/share/metainfo/{metainfo_name}"
    )
    commands[:] = [command for command in commands if "metainfo.xml" not in command]
    commands.append(metainfo_install)

    original_metainfo = path.parent / "com.rustdesk.RustDesk.metainfo.xml"
    target_metainfo = path.parent / metainfo_name
    if target_metainfo.is_file():
        metainfo_path = target_metainfo
    elif original_metainfo.is_file():
        metainfo_path = original_metainfo
    else:
        raise SystemExit("Flatpak metainfo file is missing")
    patch_metainfo(
        metainfo_path,
        app_id,
        app_name,
        company.replace(r"\&", "&"),
        url_link,
    )
    if metainfo_path != target_metainfo:
        metainfo_path.replace(target_metainfo)

    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Customized Flatpak manifest for {filename} ({app_id})")


def main() -> None:
    args = parse_args()
    customize(
        Path(args.manifest),
        args.filename,
        args.app_name,
        args.company,
        args.url_link,
        not args.without_beijing_runtime,
    )


if __name__ == "__main__":
    main()
