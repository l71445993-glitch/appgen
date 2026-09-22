from __future__ import annotations

from pathlib import Path


ROOT = Path.cwd()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"{label} is already patched.")
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Unable to patch {label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def patch_flutter_home() -> None:
    path = ROOT / "flutter/lib/desktop/pages/desktop_home_page.dart"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "                        buildPopupMenu(context)\n",
        "                        const SizedBox(width: 30, height: 30)\n",
        "Flutter settings menu button",
    )
    path.write_text(text, encoding="utf-8")


def patch_sciter_home() -> None:
    path = ROOT / "src/ui/index.tis"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        """        return <div #myid>
            {this.renderPop()}
            ID{svg_menu}
        </div>;
""",
        """        return <div #myid>
            ID
        </div>;
""",
        "Sciter ID settings menu button",
    )
    text = replace_once(
        text,
        """                            {outgoing_only ? <span .link #open-settings style="position:absolute; right:0; bottom:0; transform:scale(0.6); transform-origin:right bottom; opacity:0.85">{svg_menu}</span> : ""}
""",
        """                            {outgoing_only ? <span /> : ""}
""",
        "Sciter outgoing-only settings menu button",
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_flutter_home()
    patch_sciter_home()
    print("Hidden settings menu entry points in Flutter and Sciter clients.")


if __name__ == "__main__":
    main()
