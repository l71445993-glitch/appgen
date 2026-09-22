from pathlib import Path


PATH = Path.cwd() / "flutter/lib/desktop/pages/connection_page.dart"


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if "// if (!isIncomingOnly) setupServerWidget()," in text:
        print("Setup server tip is already hidden.")
        return
    old = "            if (!isIncomingOnly) setupServerWidget(),"
    new = "            // if (!isIncomingOnly) setupServerWidget(),"
    if old not in text:
        raise SystemExit("Could not find setupServerWidget() in connection_page.dart")
    PATH.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Hidden the setup server tip.")


if __name__ == "__main__":
    main()
