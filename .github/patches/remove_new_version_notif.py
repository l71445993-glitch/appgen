from pathlib import Path


ROOT = Path.cwd()


def main() -> None:
    home_path = ROOT / "flutter/lib/desktop/pages/desktop_home_page.dart"
    text = home_path.read_text(encoding="utf-8")
    if "updateUrl.isNotEmpty" in text:
        text = text.replace("updateUrl.isNotEmpty", "false", 1)
        home_path.write_text(text, encoding="utf-8")
        print("Disabled the desktop update card.")
    else:
        print("Desktop update card already disabled.")

    common_path = ROOT / "src/common.rs"
    text = common_path.read_text(encoding="utf-8")
    marker = "pub fn check_software_update() {\n"
    insert = "    return;\n"
    if marker + insert in text:
        print("Software update check is already disabled.")
        return
    if marker not in text:
        raise SystemExit("Could not find check_software_update() in src/common.rs")
    common_path.write_text(text.replace(marker, marker + insert, 1), encoding="utf-8")
    print("Disabled the software update check.")


if __name__ == "__main__":
    main()
