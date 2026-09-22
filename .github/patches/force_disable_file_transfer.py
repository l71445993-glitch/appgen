import re
from pathlib import Path


ROOT = Path.cwd()
PATH = ROOT / "src/server/connection.rs"
PERMISSION_MARKER = "if enable_prefix_option == keys::OPTION_ENABLE_FILE_TRANSFER"
RUNTIME_MARKER = "Generator policy: file transfer stays disabled at runtime."
PATTERN = re.compile(
    r"(?m)^(?P<indent>\s*)fn permission\(\n"
    r"(?P=indent)    enable_prefix_option: &str,\n"
    r"(?P=indent)    control_permissions: &Option<ControlPermissions>,\n"
    r"(?P=indent)\) -> bool \{\n"
)

RUNTIME_PATTERN = re.compile(
    r'(?m)^(?P<indent>\s*)\} else if &name == "file" \{\n'
    r"(?P=indent)    conn\.file = enabled;\n"
)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    changes = []

    if PERMISSION_MARKER not in text:
        match = PATTERN.search(text)
        if not match:
            raise SystemExit("Could not find permission() function in src/server/connection.rs")
        indent = match.group("indent")
        insert = (
            match.group(0)
            + f"{indent}    if enable_prefix_option == keys::OPTION_ENABLE_FILE_TRANSFER {{\n"
            + f"{indent}        return false;\n"
            + f"{indent}    }}\n"
        )
        text = text[: match.start()] + insert + text[match.end() :]
        changes.append("initial permission checks")

    if RUNTIME_MARKER not in text:
        match = RUNTIME_PATTERN.search(text)
        if not match:
            raise SystemExit(
                "Could not find the runtime file-permission branch in "
                "src/server/connection.rs"
            )
        indent = match.group("indent")
        insert = (
            f'{indent}}} else if &name == "file" {{\n'
            + f"{indent}    // {RUNTIME_MARKER}\n"
            + f"{indent}    let enabled = false;\n"
            + f"{indent}    conn.file = enabled;\n"
        )
        text = text[: match.start()] + insert + text[match.end() :]
        changes.append("runtime permission switches")

    if not changes:
        print("File transfer is already forced off for initial and runtime checks.")
        return

    PATH.write_text(text, encoding="utf-8")
    print(f"Forced file transfer off for {', '.join(changes)}.")


if __name__ == "__main__":
    main()
