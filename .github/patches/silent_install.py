from pathlib import Path


PATH = Path.cwd() / "libs/portable/src/main.rs"
OLD = 'args = vec!["--install".to_owned()];'
NEW = 'args = vec!["--silent-install".to_owned()];'


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if NEW in text:
        print("Silent install behavior already present.")
        return
    if OLD not in text:
        raise SystemExit("Could not find portable installer click_setup branch.")
    PATH.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("Changed portable installer double-click behavior to silent install.")


if __name__ == "__main__":
    main()
