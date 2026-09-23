"""Set Windows MSI install-wizard checkbox defaults from rdgen secrets.

Properties live in res/msi/Package/Fragments/ShortcutProperties.wxs:

- DESKTOPSHORTCUTS / STARTMENUSHORTCUTS default to Value=\"1\"
- PRINTER defaults to empty (unchecked)

Pass --desktop=off / --start-menu=off / --printer=on to flip defaults.
Silent-agent mode already forces desktop off; re-applying off is a no-op.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


PROPERTIES_PATH = Path("res/msi/Package/Fragments/ShortcutProperties.wxs")


def _read(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    return text, bom


def _write(path: Path, text: str, bom: bool) -> None:
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)


def _set_property_value(text: str, prop_id: str, value: str | None) -> str:
    """Set or clear the Value= attribute on <Property Id=\"PROP\" …>."""
    pattern = re.compile(
        rf'(<Property\s+Id="{re.escape(prop_id)}"[^>]*?)(/?>)',
        re.IGNORECASE,
    )

    def repl(match: re.Match[str]) -> str:
        head, tail = match.group(1), match.group(2)
        head = re.sub(r'\s+Value="[^"]*"', "", head)
        if value is None:
            return f"{head}{tail}"
        return f'{head} Value="{value}"{tail}'

    updated, count = pattern.subn(repl, text, count=1)
    if count != 1:
        raise SystemExit(f"Property Id={prop_id!r} not found in {PROPERTIES_PATH}")
    return updated


def configure_msi_install_defaults(
    root: Path,
    *,
    desktop: str = "default",
    start_menu: str = "default",
    printer: str = "off",
) -> bool:
    path = root / PROPERTIES_PATH
    if not path.is_file():
        raise SystemExit(f"Missing {path}")

    text, bom = _read(path)
    original = text

    if desktop == "off":
        text = _set_property_value(text, "DESKTOPSHORTCUTS", "0")
    if start_menu == "off":
        text = _set_property_value(text, "STARTMENUSHORTCUTS", "0")
    if printer in ("default", "on", "1", "true"):
        text = _set_property_value(text, "PRINTER", "1")

    if text == original:
        print("MSI install defaults unchanged")
        return False

    _write(path, text, bom)
    print(
        "Applied MSI install defaults:"
        f" desktop={desktop} start_menu={start_menu} printer={printer}"
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--desktop",
        choices=("default", "off"),
        default="default",
        help="Desktop shortcut checkbox default",
    )
    parser.add_argument(
        "--start-menu",
        choices=("default", "off"),
        default="default",
        help="Start menu shortcut checkbox default",
    )
    parser.add_argument(
        "--printer",
        choices=("off", "default", "on"),
        default="off",
        help="Printer driver checkbox default",
    )
    args = parser.parse_args()
    configure_msi_install_defaults(
        args.root.resolve(),
        desktop=args.desktop,
        start_menu=args.start_menu,
        printer=args.printer,
    )


if __name__ == "__main__":
    main()
