#!/usr/bin/env python3
"""Upload build artifacts to rdgen: prefer COS/OSS, fall back to direct POST.

Usage:
  upload_artifacts_to_rdgen.py --genurl URL --token TOKEN --uuid UUID [--defer] FILE [FILE...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def _req(method, url, token, data=None, headers=None, timeout=120):
    body = None
    if data is not None:
        body = data if isinstance(data, (bytes, bytearray)) else json.dumps(data).encode()
    h = {"Authorization": f"Bearer {token}", "User-Agent": "rdgen-actions"}
    if headers:
        h.update(headers)
    if body is not None and "Content-Type" not in h:
        h["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        raw = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        if "json" in ctype or (raw[:1] in (b"{", b"[")):
            return json.loads(raw.decode() or "{}")
        return {"raw": raw.decode(errors="replace")}


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _curl(args: list[str]) -> None:
    print("+", " ".join(args[:12]), "..." if len(args) > 12 else "")
    subprocess.check_call(args)


def upload_via_object_storage(genurl, token, run_uuid, files, defer: bool) -> bool:
    try:
        prepare = _req(
            "POST",
            f"{genurl.rstrip('/')}/prepare_artifact_upload",
            token,
            {"uuid": run_uuid, "files": [os.path.basename(p) for p in files]},
            timeout=60,
        )
    except Exception as exc:
        print("prepare_artifact_upload failed:", exc)
        return False

    mode = prepare.get("mode") or "direct"
    print("upload_mode", mode, "provider", prepare.get("provider"))
    if mode != "object_storage":
        return False

    uploads = {item["filename"]: item for item in prepare.get("uploads") or []}
    artifacts = []
    for path in files:
        name = os.path.basename(path)
        item = uploads.get(name)
        if not item or not item.get("put_url"):
            print("missing put_url for", name)
            return False
        size = os.path.getsize(path)
        digest = _sha256_file(path)
        put_headers = {"User-Agent": "rdgen-actions"}
        put_headers.update(item.get("headers") or {})
        cmd = [
            "curl",
            "--fail",
            "--show-error",
            "--http1.1",
            "--connect-timeout",
            "30",
            "--max-time",
            "1800",
            "--retry",
            "2",
            "--retry-delay",
            "15",
            "-X",
            "PUT",
            "--upload-file",
            path,
            item["put_url"],
        ]
        for key, value in put_headers.items():
            cmd.extend(["-H", f"{key}: {value}"])
        print("putting", name, "bytes", size)
        try:
            _curl(cmd)
        except subprocess.CalledProcessError as exc:
            print("COS/OSS PUT failed:", exc)
            return False
        artifacts.append(
            {
                "filename": name,
                "object_key": item["object_key"],
                "size": size,
                "sha256": digest,
            }
        )

    try:
        complete = _req(
            "POST",
            f"{genurl.rstrip('/')}/complete_artifact_upload",
            token,
            {
                "uuid": run_uuid,
                "defer_completion": defer,
                "artifacts": artifacts,
            },
            timeout=1800,
        )
    except Exception as exc:
        print("complete_artifact_upload failed:", exc)
        return False
    print("complete", complete)
    return True


def upload_direct(genurl, token, run_uuid, files, defer: bool) -> None:
    for path in files:
        name = os.path.basename(path)
        size = os.path.getsize(path)
        cmd = [
            "curl",
            "--fail",
            "--show-error",
            "--http1.1",
            "--connect-timeout",
            "30",
            "--max-time",
            "1800",
            "--retry",
            "3",
            "--retry-delay",
            "20",
            "--retry-all-errors",
            "-X",
            "POST",
            "-H",
            f"Authorization: Bearer {token}",
            "-F",
            f"file=@{path}",
            "-F",
            f"uuid={run_uuid}",
        ]
        if defer:
            cmd.extend(["-F", "defer_completion=true"])
        cmd.append(f"{genurl.rstrip('/')}/save_custom_client")
        print("direct_upload", name, "bytes", size)
        _curl(cmd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--genurl", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--uuid", required=True)
    parser.add_argument("--defer", action="store_true")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()

    files = []
    for path in args.files:
        if not os.path.isfile(path):
            print("missing file:", path, file=sys.stderr)
            return 2
        files.append(path)

    if upload_via_object_storage(args.genurl, args.token, args.uuid, files, args.defer):
        print("upload_ok object_storage")
        return 0

    print("falling back to direct multipart upload")
    upload_direct(args.genurl, args.token, args.uuid, files, args.defer)
    print("upload_ok direct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
