#!/usr/bin/env python3
import argparse
import re
import shutil
import subprocess
from pathlib import Path


SHIM_NAME = "librustdesk_no_sysvipc.so"
MARKER = "Beijing custom compatibility"
UINPUT_MARKER = "Beijing custom uinput compatibility"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--filename", required=True)
    return parser.parse_args()


def validate_filename(filename: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]+", filename):
        raise SystemExit(f"Invalid package filename for service/path use: {filename!r}")


def remove_legacy_sudoers(root: Path, filename: str) -> None:
    relative_path = Path("etc") / "sudoers.d" / f"{filename}-ld-preload"
    for base in (root / "flutter" / "tmpdeb", root / ".rdgen-beijing"):
        path = base / relative_path
        if path.exists():
            path.unlink()


def build_shim(source_dir: Path) -> Path:
    output = source_dir / SHIM_NAME
    sources = [
        source_dir / "rustdesk_no_sysvipc_shim.c",
        source_dir / "rustdesk_uinput_input_fallback.c",
    ]
    missing = [str(path) for path in sources if not path.exists()]
    if missing:
        raise SystemExit(f"Missing shim source files: {', '.join(missing)}")

    subprocess.run(
        [
            "gcc",
            "-O2",
            "-g",
            "-fPIC",
            "-Wall",
            "-Wextra",
            "-shared",
            "-o",
            str(output),
            *(str(path) for path in sources),
            "-ldl",
            "-pthread",
        ],
        check=True,
    )
    output.chmod(0o755)
    return output


def write_dropin(root: Path, filename: str, shim_path: str) -> None:
    dropin_dir = root / "flutter" / "tmpdeb" / "etc" / "systemd" / "system" / f"{filename}.service.d"
    dropin_dir.mkdir(parents=True, exist_ok=True)
    dropin = dropin_dir / "beijing-custom.conf"
    dropin.write_text(
        "\n".join(
            [
                "[Service]",
                f"Environment=LD_PRELOAD={shim_path}",
                "Environment=RUSTDESK_NO_SYSVIPC_SHIM_LOG=0",
                "Environment=RUSTDESK_UINPUT_INPUT_FALLBACK=0",
                "Environment=RUSTDESK_UINPUT_INPUT_LOG=1",
                "Environment=RUSTDESK_XCB_MOUSE_FALLBACK=1",
                "Environment=RUSTDESK_UINPUT_MOUSE_MODE=anchor",
                "Environment=RUSTDESK_UINPUT_MOUSE_REL_SCALE=2",
                "Environment=RUSTDESK_UINPUT_WIDTH=1024",
                "Environment=RUSTDESK_UINPUT_HEIGHT=600",
                "Environment=RUSTDESK_FORCE_CM_NO_UI=1",
                "Environment=RUSTDESK_DISABLE_TRAY=1",
                "Environment=RUSTDESK_PREWARM_CM_NO_UI=1",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_uinput_udev_rule(root: Path, filename: str) -> None:
    rules_dir = root / "flutter" / "tmpdeb" / "etc" / "udev" / "rules.d"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rule = rules_dir / f"99-{filename}-uinput.rules"
    rule.write_text(
        "\n".join(
            [
                f"# {UINPUT_MARKER}",
                'KERNEL=="uinput", MODE="0660", TAG+="uaccess"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def patch_postinst(root: Path, filename: str) -> None:
    postinst = root / "res" / "DEBIAN" / "postinst"
    if not postinst.exists():
        raise SystemExit(f"{postinst} not found")

    text = postinst.read_text(encoding="utf-8")
    text = re.sub(
        r"\n[ \t]*if \[ -e /dev/uinput \]; then\n"
        r"[ \t]*chmod 0666 /dev/uinput \|\| true\n"
        r"[ \t]*fi",
        "",
        text,
    )
    if MARKER in text:
        postinst.write_text(text, encoding="utf-8")
        return

    lines = text.splitlines()
    target = f"systemctl start {filename}"
    for index, line in enumerate(lines):
        if line.strip() == target:
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = (
                f"{indent}# {UINPUT_MARKER}: allow the user-mode server to open /dev/uinput.\n"
                f"{indent}if command -v udevadm >/dev/null 2>&1; then\n"
                f"{indent}    udevadm control --reload-rules || true\n"
                f"{indent}    udevadm trigger --name-match=uinput || true\n"
                f"{indent}fi\n"
                f"{indent}# {MARKER}: restart so the drop-in applies on upgrades.\n"
                f"{indent}systemctl restart {filename} || systemctl start {filename}"
            )
            postinst.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return

    raise SystemExit(f"Unable to find postinst line: {target}")


def persist_native_package_files(root: Path, filename: str) -> None:
    package_root = root / "flutter" / "tmpdeb"
    persistent_root = root / ".rdgen-beijing"
    relative_paths = [
        Path("usr") / "lib" / filename / SHIM_NAME,
        Path("etc")
        / "systemd"
        / "system"
        / f"{filename}.service.d"
        / "beijing-custom.conf",
        Path("etc") / "udev" / "rules.d" / f"99-{filename}-uinput.rules",
    ]
    for relative_path in relative_paths:
        source = package_root / relative_path
        if not source.is_file():
            raise SystemExit(f"Missing Beijing package file: {source}")
        destination = persistent_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main() -> None:
    args = parse_args()
    filename = args.filename
    validate_filename(filename)

    root = Path.cwd()
    source_dir = Path(args.source_dir).resolve()
    shim = build_shim(source_dir)

    shim_rel_path = Path("usr") / "lib" / filename / SHIM_NAME
    shim_install_path = root / "flutter" / "tmpdeb" / shim_rel_path
    shim_install_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(shim, shim_install_path)
    shim_install_path.chmod(0o755)

    remove_legacy_sudoers(root, filename)
    write_dropin(root, filename, f"/{shim_rel_path.as_posix()}")
    write_uinput_udev_rule(root, filename)
    patch_postinst(root, filename)
    persist_native_package_files(root, filename)
    print(f"Applied Beijing custom Linux packaging for {filename}")


if __name__ == "__main__":
    main()
