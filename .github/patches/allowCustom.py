from __future__ import annotations

import argparse
import re
from pathlib import Path


PATH = Path.cwd() / "src/common.rs"
LINUX_PATH = Path.cwd() / "src/platform/linux.rs"
SIGNATURE_BLOCK = re.compile(
    r'''(?ms)^\s*const KEY: &str = "5Qbwsde3unUcJBtrx9ZkvUmwFNoExHzpryHuPUdqlWM=";\n'''
    r'''\s*let Some\(pk\) = get_rs_pk\(KEY\) else \{\n'''
    r'''\s*log::error!\("Failed to parse public key of custom client"\);\n'''
    r'''\s*return;\n'''
    r'''\s*\};\n'''
    r'''\s*let Ok\(data\) = sign::verify\(&data, &pk\) else \{\n'''
    r'''\s*log::error!\("Failed to dec custom client config"\);\n'''
    r'''\s*return;\n'''
    r'''\s*\};\n'''
)
URI_PREFIX_FUNCTION = '''pub fn get_uri_prefix() -> String {
    format!("{}://", get_app_name().to_lowercase())
}'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--linux-uri-filename")
    return parser.parse_args()


def linux_uri_scheme(filename: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]+", filename):
        raise SystemExit(f"Invalid Linux URI filename: {filename!r}")
    return f"rdgen-{filename.encode('ascii').hex()}"


def patch_uri_prefix(text: str, filename: str) -> str:
    scheme = linux_uri_scheme(filename)
    replacement = f'''pub fn get_uri_prefix() -> String {{
    "{scheme}://".to_owned()
}}'''
    if replacement in text:
        return text
    if text.count(URI_PREFIX_FUNCTION) != 1:
        raise SystemExit("Could not safely identify the RustDesk URI prefix function")
    return text.replace(URI_PREFIX_FUNCTION, replacement, 1)


def patch_linux_project_config(text: str) -> str:
    old = '''        let app_name_lower = crate::get_app_name().to_lowercase();
        let app_name0 = crate::get_app_name();
        let config_subdir = format!(".config/{}", app_name_lower);'''
    new = '''        // Match directories-next ProjectDirs naming on Linux.
        let app_name_lower = crate::get_app_name()
            .split_whitespace()
            .map(|part| part.to_lowercase())
            .collect::<Vec<_>>()
            .join("");
        let app_name0 = crate::get_app_name();
        let config_subdir = format!(".config/{}", app_name_lower);'''
    if new in text:
        return text
    if text.count(old) != 1:
        raise SystemExit("Could not safely identify the Linux service config path")
    return text.replace(old, new, 1)


def main() -> None:
    args = parse_args()
    if not PATH.is_file():
        raise SystemExit(f"{PATH} not found; run this from the RustDesk source root")

    text = PATH.read_text(encoding="utf-8")
    matches = list(SIGNATURE_BLOCK.finditer(text))
    if len(matches) == 1:
        text = SIGNATURE_BLOCK.sub("", text, count=1)
        print("Disabled the upstream custom-config signature requirement.")
    elif len(matches) > 1:
        raise SystemExit(
            f"Expected one custom-config signature block, found {len(matches)}"
        )
    elif "get_rs_pk(KEY)" in text or "sign::verify(&data, &pk)" in text:
        raise SystemExit("Could not safely identify the custom-config signature block")
    else:
        print("Custom-config signature requirement is already disabled.")

    plain_count = text.count('"custom.txt"')
    if plain_count:
        text = text.replace('"custom.txt"', '"custom_.txt"')
        print(f"Renamed {plain_count} custom config path(s) to custom_.txt.")
    elif '"custom_.txt"' not in text:
        raise SystemExit("Could not find the RustDesk custom config path")
    else:
        print("Custom config paths already use custom_.txt.")

    if "let Ok(mut data)" not in text:
        raise SystemExit("Custom-config JSON parsing block is missing after patching")

    if args.linux_uri_filename:
        text = patch_uri_prefix(text, args.linux_uri_filename)
        print(
            "Set Linux URI scheme to "
            f"{linux_uri_scheme(args.linux_uri_filename)}://."
        )

        if not LINUX_PATH.is_file():
            raise SystemExit(f"{LINUX_PATH} not found")
        linux_text = LINUX_PATH.read_text(encoding="utf-8")
        linux_text = patch_linux_project_config(linux_text)
        LINUX_PATH.write_text(linux_text, encoding="utf-8")
        print("Aligned Linux service config paths with ProjectDirs.")

    PATH.write_text(text, encoding="utf-8")

if __name__ == "__main__":
    main()
