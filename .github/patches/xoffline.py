from pathlib import Path


PATH = Path.cwd() / "flutter/lib/common/widgets/peer_card.dart"
OLD = """          child: CircleAvatar(
              radius: 3, backgroundColor: online ? Colors.green : kColorWarn)))"""
NEW = """          child: online
              ? CircleAvatar(radius: 3, backgroundColor: Colors.green)
              : Icon(
                  Icons.close,
                  color: Colors.red,
                  size: 12.0,
                )))"""


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if NEW in text:
        print("Offline X marker is already present.")
        return
    count = text.count(OLD)
    if count != 1:
        raise SystemExit(
            "Could not safely patch online status marker in peer_card.dart: "
            f"expected 1 match, found {count}"
        )
    PATH.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("Changed offline status to a red X marker.")


if __name__ == "__main__":
    main()
