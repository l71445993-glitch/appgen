from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path


ROOT_BASELINE = "6c578292e8ebbbec708b76986ba8c4bc7c509747"
HBB_COMMON_BASELINE = "7e1c392c62d39c364127307cd408421dd5f8cfb0"

ROOT_PATCH_NAME = "smart_multi_relay_149_root.diff"
ROOT_PATCH_SHA256 = "d6f7bfd3e641205895d22ecddd3c461a5fed01afba6030095fbc3731ee0c7be2"
ROOT_PATCH_PATHS = (
    "Cargo.lock",
    "Cargo.toml",
    "flutter/lib/main.dart",
    "src/client.rs",
    "src/flutter_ffi.rs",
    "src/lib.rs",
    "src/rendezvous_mediator.rs",
    "src/smart_relay.rs",
)

HBB_COMMON_PATCH_NAME = "smart_multi_relay_149_hbb_common.diff"
HBB_COMMON_PATCH_SHA256 = "f8b07957bb5187959a42ab06a51b749c3235f9593e8d28ab12bea176e1f5910b"
HBB_COMMON_PATCH_PATHS = (
    "Cargo.toml",
    "protos/rendezvous.proto",
    "src/lib.rs",
    "src/smart_relay.rs",
    "src/stream.rs",
    "src/websocket.rs",
)

ROOT_PRE_MARKERS = (
    (
        "src/client.rs",
        "if !key.is_empty() && !token.is_empty() {",
        2,
    ),
    ("src/lib.rs", "mod client;", 1),
    ("src/rendezvous_mediator.rs", "pub struct RendezvousMediator {", 1),
)
HBB_COMMON_PRE_MARKERS = (
    ("protos/rendezvous.proto", "message HealthCheck {", 1),
    ("src/lib.rs", "pub mod protos;", 1),
    ("src/websocket.rs", "pub struct WsFramedStream {", 1),
)

ROOT_POST_MARKERS = (
    ("Cargo.toml", 'features = ["test-ws-tls"]'),
    ("src/lib.rs", "mod smart_relay;"),
    ("src/smart_relay.rs", "pub(crate) fn signed_relay_connect_offer("),
    ("src/client.rs", "struct FrozenRendezvousConnection {"),
    ("src/client.rs", "fn strict_wss_probe_trust_for_connected_stream("),
    ("src/client.rs", "enum RelayRefusalDisposition {"),
    ("src/client.rs", "struct SmartRendezvousRestart {"),
    (
        "src/flutter_ffi.rs",
        "failed to invalidate smart relay network state: {error}",
    ),
    ("flutter/lib/main.dart", "unawaited(bind.mainCheckConnectStatus());"),
    (
        "src/smart_relay.rs",
        "pub(crate) fn invalidate_configured_smart_relay_network()",
    ),
    ("src/rendezvous_mediator.rs", "fn rendezvous_stream_origin("),
    (
        "src/rendezvous_mediator.rs",
        "handle_configured_smart_relay_probe_request_from_mediator",
    ),
)
HBB_COMMON_POST_MARKERS = (
    ("Cargo.toml", "test-ws-tls = []"),
    ("protos/rendezvous.proto", "message SmartRelayCapability {"),
    (
        "protos/rendezvous.proto",
        "SmartRelayProbeRequest smart_relay_probe_request = 1001;",
    ),
    ("src/lib.rs", "pub mod smart_relay;"),
    ("src/smart_relay.rs", "pub const SMART_RELAY_PROTOCOL_V1: u32 = 1;"),
    ("src/stream.rs", "pub fn has_strict_websocket_tls_handshake(&self) -> bool"),
    ("src/websocket.rs", "pub fn has_strict_tls_handshake(&self) -> bool"),
    ("src/websocket.rs", "fn configured_api_server_for_websocket() -> String"),
)

FORBIDDEN_PATCH_TOKENS = (
    "e2e-peer-fixture",
    "smart-relay-e2e-peer",
    "smart_relay_e2e_peer",
    "src/client/e2e_peer.rs",
    "configure_e2e_lan_ipv4",
    "set_e2e_identity",
    "docs/SMART_RELAY_MILESTONE4_CLIENT.md",
    "diff --git a/libs/hbb_common b/libs/hbb_common",
)
FORBIDDEN_SOURCE_MARKERS = (
    ("Cargo.toml", "e2e-peer-fixture"),
    ("src/lib.rs", "pub mod e2e_peer;"),
    ("src/smart_relay.rs", "configure_e2e_lan_ipv4"),
    ("libs/hbb_common/Cargo.toml", "e2e-peer-fixture"),
    ("libs/hbb_common/src/config.rs", "set_e2e_identity"),
    ("libs/hbb_common/src/smart_relay.rs", "configure_e2e_lan_ipv4"),
)
FORBIDDEN_SOURCE_PATHS = (
    "src/client/e2e_peer.rs",
    "src/smart_relay_e2e_peer.rs",
)


class ContractError(RuntimeError):
    pass


def run_git(
    repository: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        suffix = f": {detail}" if detail else ""
        raise ContractError(
            f"git {' '.join(arguments)} failed in {repository}{suffix}"
        )
    return result


def git_output(repository: Path, *arguments: str) -> str:
    return run_git(repository, *arguments).stdout.strip()


def read_text(root: Path, relative_path: str) -> str:
    path = root / relative_path
    if not path.is_file():
        raise ContractError(f"Required source file is missing: {path}")
    return path.read_text(encoding="utf-8")


def assert_repository(repository: Path, label: str) -> None:
    if not repository.is_dir():
        raise ContractError(f"{label} repository is missing: {repository}")
    if git_output(repository, "rev-parse", "--is-inside-work-tree") != "true":
        raise ContractError(f"{label} is not a Git worktree: {repository}")


def assert_baselines(source: Path, hbb_common: Path) -> None:
    root_head = git_output(source, "rev-parse", "HEAD")
    if root_head != ROOT_BASELINE:
        raise ContractError(
            "RustDesk root baseline mismatch: "
            f"expected {ROOT_BASELINE}, found {root_head}"
        )

    root_gitlink = git_output(source, "rev-parse", "HEAD:libs/hbb_common")
    if root_gitlink != HBB_COMMON_BASELINE:
        raise ContractError(
            "RustDesk hbb_common gitlink baseline mismatch: "
            f"expected {HBB_COMMON_BASELINE}, found {root_gitlink}"
        )

    hbb_head = git_output(hbb_common, "rev-parse", "HEAD")
    if hbb_head != HBB_COMMON_BASELINE:
        raise ContractError(
            "hbb_common worktree baseline mismatch: "
            f"expected {HBB_COMMON_BASELINE}, found {hbb_head}"
        )


def extract_patch_paths(patch_text: str) -> set[str]:
    paths: set[str] = set()
    for line in patch_text.splitlines():
        if not line.startswith("diff --git "):
            continue
        match = re.fullmatch(r"diff --git a/(.+) b/(.+)", line)
        if match is None or match.group(1) != match.group(2):
            raise ContractError(f"Unexpected patch path header: {line}")
        paths.add(match.group(1))
    return paths


def validate_patch(
    patch: Path,
    expected_sha256: str,
    expected_paths: tuple[str, ...],
) -> None:
    if not patch.is_file():
        raise ContractError(f"Smart multi-relay patch is missing: {patch}")
    patch_bytes = patch.read_bytes()
    actual_sha256 = hashlib.sha256(patch_bytes).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ContractError(
            f"Patch digest mismatch for {patch.name}: "
            f"expected {expected_sha256}, found {actual_sha256}"
        )

    patch_text = patch_bytes.decode("utf-8")
    actual_paths = extract_patch_paths(patch_text)
    if actual_paths != set(expected_paths):
        raise ContractError(
            f"Patch path contract mismatch for {patch.name}: "
            f"expected {sorted(expected_paths)}, found {sorted(actual_paths)}"
        )
    forbidden = [token for token in FORBIDDEN_PATCH_TOKENS if token in patch_text]
    if forbidden:
        raise ContractError(
            f"Fixture-only or out-of-scope content found in {patch.name}: "
            + ", ".join(forbidden)
        )


def marker_hits(root: Path, markers: tuple[tuple[str, str], ...]) -> list[str]:
    hits: list[str] = []
    cache: dict[str, str] = {}
    for relative_path, marker in markers:
        path = root / relative_path
        if not path.is_file():
            continue
        if relative_path not in cache:
            cache[relative_path] = path.read_text(encoding="utf-8")
        if marker in cache[relative_path]:
            hits.append(f"{relative_path}: {marker}")
    return hits


def assert_markers_absent(
    source: Path,
    markers: tuple[tuple[str, str], ...],
    context: str,
) -> None:
    hits = marker_hits(source, markers)
    if hits:
        raise ContractError(f"{context}; found " + "; ".join(hits))


def assert_markers_present(
    source: Path,
    markers: tuple[tuple[str, str], ...],
    context: str,
) -> None:
    hits = set(marker_hits(source, markers))
    expected = {f"{path}: {marker}" for path, marker in markers}
    missing = sorted(expected - hits)
    if missing:
        raise ContractError(f"{context}; missing " + "; ".join(missing))


def assert_pre_markers(
    root: Path,
    markers: tuple[tuple[str, str, int], ...],
    label: str,
) -> None:
    for relative_path, marker, expected_count in markers:
        actual_count = read_text(root, relative_path).count(marker)
        if actual_count != expected_count:
            raise ContractError(
                f"{label} pre-marker mismatch in {relative_path}: "
                f"expected {expected_count} occurrence(s) of {marker!r}, "
                f"found {actual_count}"
            )


def assert_fixture_content_absent(source: Path) -> None:
    forbidden_paths = [
        relative_path
        for relative_path in FORBIDDEN_SOURCE_PATHS
        if (source / relative_path).exists()
    ]
    if forbidden_paths:
        raise ContractError(
            "E2E fixture-only source path(s) must not exist: "
            + ", ".join(forbidden_paths)
        )
    assert_markers_absent(
        source,
        FORBIDDEN_SOURCE_MARKERS,
        "E2E fixture-only source marker(s) must not exist",
    )


def assert_patch_targets_clean(
    repository: Path,
    paths: tuple[str, ...],
    label: str,
) -> None:
    result = run_git(repository, "diff", "--quiet", "HEAD", "--", *paths, check=False)
    if result.returncode == 1:
        raise ContractError(
            f"{label} patch targets differ from the locked baseline before apply"
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ContractError(f"Unable to inspect {label} patch targets: {detail}")


def assert_new_targets_absent(source: Path, hbb_common: Path) -> None:
    new_targets = (source / "src/smart_relay.rs", hbb_common / "src/smart_relay.rs")
    existing = [str(path) for path in new_targets if path.exists()]
    if existing:
        raise ContractError(
            "Smart multi-relay new-file target(s) already exist before apply: "
            + ", ".join(existing)
        )


def assert_unpatched(source: Path) -> None:
    root_hits = marker_hits(source, ROOT_POST_MARKERS)
    hbb_hits = marker_hits(source / "libs/hbb_common", HBB_COMMON_POST_MARKERS)
    hits = root_hits + [f"libs/hbb_common/{hit}" for hit in hbb_hits]
    if hits:
        raise ContractError(
            "Smart multi-relay must be absent when enabled=false; found "
            + "; ".join(hits)
        )


def assert_not_already_or_partially_applied(source: Path) -> None:
    root_hits = marker_hits(source, ROOT_POST_MARKERS)
    hbb_hits = marker_hits(source / "libs/hbb_common", HBB_COMMON_POST_MARKERS)
    hit_count = len(root_hits) + len(hbb_hits)
    expected_count = len(ROOT_POST_MARKERS) + len(HBB_COMMON_POST_MARKERS)
    if hit_count == expected_count:
        raise ContractError(
            "Smart multi-relay patch is already applied; repeated enabled=true "
            "application is rejected by contract"
        )
    if hit_count:
        hits = root_hits + [f"libs/hbb_common/{hit}" for hit in hbb_hits]
        raise ContractError(
            "Partial or stale smart multi-relay markers exist before apply: "
            + "; ".join(hits)
        )


def apply_checked_patch(repository: Path, patch: Path) -> None:
    run_git(repository, "apply", "--whitespace=nowarn", str(patch))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply the locked RustDesk 1.4.9 production smart multi-relay patch"
    )
    parser.add_argument("--enabled", choices=("true", "false"), required=True)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument(
        "--patches",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    args = parser.parse_args()

    source = args.source.resolve()
    hbb_common = source / "libs/hbb_common"
    assert_repository(source, "RustDesk root")
    assert_repository(hbb_common, "hbb_common")
    assert_baselines(source, hbb_common)
    assert_fixture_content_absent(source)

    if args.enabled == "false":
        assert_unpatched(source)
        print(
            "Smart multi-relay disabled; locked baselines verified and production "
            "protocol/runtime markers are absent."
        )
        return

    patches = args.patches.resolve()
    root_patch = patches / ROOT_PATCH_NAME
    hbb_patch = patches / HBB_COMMON_PATCH_NAME
    validate_patch(root_patch, ROOT_PATCH_SHA256, ROOT_PATCH_PATHS)
    validate_patch(hbb_patch, HBB_COMMON_PATCH_SHA256, HBB_COMMON_PATCH_PATHS)
    assert_not_already_or_partially_applied(source)
    assert_patch_targets_clean(source, ROOT_PATCH_PATHS, "RustDesk root")
    assert_patch_targets_clean(hbb_common, HBB_COMMON_PATCH_PATHS, "hbb_common")
    assert_new_targets_absent(source, hbb_common)
    assert_pre_markers(source, ROOT_PRE_MARKERS, "RustDesk root")
    assert_pre_markers(hbb_common, HBB_COMMON_PRE_MARKERS, "hbb_common")

    run_git(source, "apply", "--check", "--whitespace=nowarn", str(root_patch))
    run_git(hbb_common, "apply", "--check", "--whitespace=nowarn", str(hbb_patch))
    apply_checked_patch(hbb_common, hbb_patch)
    apply_checked_patch(source, root_patch)

    assert_baselines(source, hbb_common)
    assert_markers_present(
        source,
        ROOT_POST_MARKERS,
        "RustDesk smart multi-relay runtime markers are incomplete after apply",
    )
    assert_markers_present(
        hbb_common,
        HBB_COMMON_POST_MARKERS,
        "hbb_common smart multi-relay protocol markers are incomplete after apply",
    )
    assert_fixture_content_absent(source)
    run_git(
        source,
        "apply",
        "--reverse",
        "--check",
        "--whitespace=nowarn",
        str(root_patch),
    )
    run_git(
        hbb_common,
        "apply",
        "--reverse",
        "--check",
        "--whitespace=nowarn",
        str(hbb_patch),
    )
    print(
        "Applied locked RustDesk 1.4.9 production smart multi-relay patches; "
        "protocol, runtime, strict-WSS, and fixture-exclusion markers verified."
    )


if __name__ == "__main__":
    try:
        main()
    except ContractError as error:
        raise SystemExit(str(error)) from error
