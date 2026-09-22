from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT_BASELINE = "6c578292e8ebbbec708b76986ba8c4bc7c509747"
HBB_COMMON_BASELINE = "7e1c392c62d39c364127307cd408421dd5f8cfb0"
ROOT_WRONG_BASELINE = "287f8a453cda3e47f46cf83eee7856456d620cd9"
HBB_COMMON_WRONG_BASELINE = "d58fd1141af901f493259697786822b773c5ed3e"


def offline_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["GIT_NO_LAZY_FETCH"] = "1"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return environment


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    expect_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=offline_environment(),
    )
    if expect_success and result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stdout}{result.stderr}"
        )
    if not expect_success and result.returncode == 0:
        raise RuntimeError(
            f"Command unexpectedly succeeded: {' '.join(command)}\n{result.stdout}"
        )
    return result


def git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return run(["git", *arguments], cwd=repository)


def clone_baseline(source_repository: Path, destination: Path) -> Path:
    rustdesk = destination / "rustdesk"
    run(
        [
            "git",
            "clone",
            "--shared",
            "--no-checkout",
            str(source_repository),
            str(rustdesk),
        ]
    )
    git(rustdesk, "checkout", "--detach", ROOT_BASELINE)

    hbb_source = source_repository / "libs/hbb_common"
    hbb_destination = rustdesk / "libs/hbb_common"
    run(
        [
            "git",
            "clone",
            "--shared",
            "--no-checkout",
            str(hbb_source),
            str(hbb_destination),
        ]
    )
    git(hbb_destination, "checkout", "--detach", HBB_COMMON_BASELINE)
    return rustdesk


def run_helper(
    helper: Path,
    source: Path,
    patches: Path,
    enabled: str,
    *,
    expect_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            str(helper),
            "--enabled",
            enabled,
            "--source",
            str(source),
            "--patches",
            str(patches),
        ],
        expect_success=expect_success,
    )


def status(repository: Path) -> str:
    return git(
        repository,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ).stdout


def assert_contains(path: Path, marker: str) -> None:
    if marker not in path.read_text(encoding="utf-8"):
        raise RuntimeError(f"Expected marker {marker!r} is missing from {path}")


def assert_fixture_absent(source: Path) -> None:
    forbidden_paths = (
        source / "src/client/e2e_peer.rs",
        source / "src/smart_relay_e2e_peer.rs",
    )
    present = [str(path) for path in forbidden_paths if path.exists()]
    if present:
        raise RuntimeError("Fixture-only paths were applied: " + ", ".join(present))

    forbidden_markers = (
        (source / "Cargo.toml", "e2e-peer-fixture"),
        (source / "libs/hbb_common/Cargo.toml", "e2e-peer-fixture"),
        (source / "libs/hbb_common/src/config.rs", "set_e2e_identity"),
        (
            source / "libs/hbb_common/src/smart_relay.rs",
            "configure_e2e_lan_ipv4",
        ),
    )
    hits = [
        f"{path}: {marker}"
        for path, marker in forbidden_markers
        if path.is_file() and marker in path.read_text(encoding="utf-8")
    ]
    if hits:
        raise RuntimeError("Fixture-only markers were applied: " + "; ".join(hits))


def assert_reverse_checks(source: Path, patches: Path) -> None:
    git(
        source,
        "apply",
        "--reverse",
        "--check",
        "--whitespace=nowarn",
        str(patches / "smart_multi_relay_149_root.diff"),
    )
    git(
        source / "libs/hbb_common",
        "apply",
        "--reverse",
        "--check",
        "--whitespace=nowarn",
        str(patches / "smart_multi_relay_149_hbb_common.diff"),
    )


def exercise_disabled_and_enabled(
    helper: Path,
    source_repository: Path,
    patches: Path,
    temporary_root: Path,
) -> None:
    source = clone_baseline(source_repository, temporary_root / "on-off")
    initial_root_status = status(source)
    initial_hbb_status = status(source / "libs/hbb_common")

    missing_patch_directory = temporary_root / "patches-not-downloaded"
    first_disabled = run_helper(
        helper,
        source,
        missing_patch_directory,
        "false",
    )
    second_disabled = run_helper(
        helper,
        source,
        missing_patch_directory,
        "false",
    )
    for result in (first_disabled, second_disabled):
        if "markers are absent" not in result.stdout:
            raise RuntimeError("Disabled verification did not report its marker contract")
    if status(source) != initial_root_status or status(
        source / "libs/hbb_common"
    ) != initial_hbb_status:
        raise RuntimeError("enabled=false mutated the baseline source")
    print("[ok] enabled=false is mutation-free, repeatable, and needs no patch bundle")

    enabled = run_helper(helper, source, patches, "true")
    if "strict-WSS" not in enabled.stdout:
        raise RuntimeError("Enabled apply did not report strict-WSS verification")
    assert_contains(source / "src/lib.rs", "mod smart_relay;")
    assert_contains(
        source / "src/client.rs",
        "fn strict_wss_probe_trust_for_connected_stream(",
    )
    assert_contains(
        source / "src/client.rs",
        "enum RelayRefusalDisposition {",
    )
    assert_contains(
        source / "src/client.rs",
        "struct SmartRendezvousRestart {",
    )
    assert_contains(
        source / "src/flutter_ffi.rs",
        "failed to invalidate smart relay network state: {error}",
    )
    assert_contains(
        source / "flutter/lib/main.dart",
        "unawaited(bind.mainCheckConnectStatus());",
    )
    assert_contains(
        source / "src/smart_relay.rs",
        "pub(crate) fn invalidate_configured_smart_relay_network()",
    )
    assert_contains(
        source / "libs/hbb_common/protos/rendezvous.proto",
        "message SmartRelayCapability {",
    )
    assert_contains(
        source / "libs/hbb_common/src/smart_relay.rs",
        "pub const SMART_RELAY_PROTOCOL_V1: u32 = 1;",
    )
    assert_reverse_checks(source, patches)
    assert_fixture_absent(source)
    print("[ok] enabled=true applies the locked production protocol/runtime patches")

    repeated = run_helper(
        helper,
        source,
        patches,
        "true",
        expect_success=False,
    )
    repeated_output = f"{repeated.stdout}\n{repeated.stderr}"
    if "already applied" not in repeated_output or "rejected" not in repeated_output:
        raise RuntimeError("Repeated enabled=true apply did not fail with the locked contract")
    assert_reverse_checks(source, patches)
    print("[ok] repeated enabled=true application is rejected without corruption")

    disabled_after_apply = run_helper(
        helper,
        source,
        missing_patch_directory,
        "false",
        expect_success=False,
    )
    if "must be absent when enabled=false" not in (
        f"{disabled_after_apply.stdout}\n{disabled_after_apply.stderr}"
    ):
        raise RuntimeError("enabled=false accepted a patched source tree")
    print("[ok] enabled=false rejects smart protocol/runtime markers")


def exercise_wrong_baselines(
    helper: Path,
    source_repository: Path,
    patches: Path,
    temporary_root: Path,
) -> None:
    source = clone_baseline(source_repository, temporary_root / "wrong-baseline")
    git(source, "checkout", "--detach", ROOT_WRONG_BASELINE)
    wrong_root = run_helper(
        helper,
        source,
        patches,
        "true",
        expect_success=False,
    )
    if "RustDesk root baseline mismatch" not in (
        f"{wrong_root.stdout}\n{wrong_root.stderr}"
    ):
        raise RuntimeError("Wrong RustDesk root baseline was not rejected explicitly")
    print("[ok] wrong RustDesk root baseline is rejected")

    git(source, "checkout", "--detach", ROOT_BASELINE)
    git(
        source / "libs/hbb_common",
        "checkout",
        "--detach",
        HBB_COMMON_WRONG_BASELINE,
    )
    wrong_hbb = run_helper(
        helper,
        source,
        patches,
        "true",
        expect_success=False,
    )
    if "hbb_common worktree baseline mismatch" not in (
        f"{wrong_hbb.stdout}\n{wrong_hbb.stderr}"
    ):
        raise RuntimeError("Wrong hbb_common baseline was not rejected explicitly")
    print("[ok] wrong hbb_common worktree baseline is rejected")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Offline smoke coverage for the locked RustDesk 1.4.9 smart "
            "multi-relay patch helper"
        )
    )
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument(
        "--patches",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    args = parser.parse_args()

    source_repository = args.source_repo.resolve()
    patches = args.patches.resolve()
    helper = patches / "apply_smart_multi_relay_149.py"
    if not helper.is_file():
        raise SystemExit(f"Patch helper is missing: {helper}")
    if not (source_repository / "libs/hbb_common").is_dir():
        raise SystemExit(
            "Source repository must include the local hbb_common repository: "
            f"{source_repository}"
        )

    with tempfile.TemporaryDirectory(prefix="rdsmart-149-smoke-") as temporary:
        temporary_root = Path(temporary)
        exercise_disabled_and_enabled(
            helper,
            source_repository,
            patches,
            temporary_root,
        )
        exercise_wrong_baselines(
            helper,
            source_repository,
            patches,
            temporary_root,
        )
    print("All smart multi-relay 1.4.9 offline smoke checks passed.")


if __name__ == "__main__":
    main()
