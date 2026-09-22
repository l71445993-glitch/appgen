from pathlib import Path


PATH = Path.cwd() / "src/client.rs"
SOURCE_CONDITION = "if !key.is_empty() && !token.is_empty() {"
PATCHED_CONDITION = "if false && !token.is_empty() {"
EXPECTED_MATCHES = 2


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    source_count = text.count(SOURCE_CONDITION)
    patched_count = text.count(PATCHED_CONDITION)

    if source_count + patched_count != EXPECTED_MATCHES:
        raise SystemExit(
            "Expected exactly two rendezvous secure_tcp conditions in src/client.rs, "
            f"found {source_count} unpatched and {patched_count} patched"
        )

    if source_count == 0:
        print("Connection delay compatibility fix is already applied.")
        return

    text = text.replace(SOURCE_CONDITION, PATCHED_CONDITION)
    if text.count(PATCHED_CONDITION) != EXPECTED_MATCHES:
        raise SystemExit("Failed to patch both rendezvous secure_tcp conditions")

    PATH.write_text(text, encoding="utf-8")
    print(f"Applied connection delay compatibility fix at {source_count} location(s).")


if __name__ == "__main__":
    main()
