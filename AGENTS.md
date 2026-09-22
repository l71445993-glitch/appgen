# Agent Notes

## Project Context

This repository is a local clone of `https://github.com/bryangerlach/rdgen`.
The working directory is `D:\rustdesk-生成器\rdgen`.

The user wants to optimize this RustDesk custom client generator. Keep changes scoped and preserve upstream behavior unless the requested optimization requires a behavior change.

## Operating Rules

- Use PowerShell commands from the repository root unless a task requires another shell.
- Prefer `rg` / `rg --files` for source discovery.
- Use `apply_patch` for manual edits.
- Do not overwrite user changes. Check `git status --short` before edits.
- Avoid submitting the live generator form unless the user explicitly asks.
- Full generation depends on public GitHub Actions callbacks and cannot be proven with a local-only Docker stack. Do not treat local Docker parity as a release requirement; local services are useful only for UI/form inspection unless the user explicitly asks for local container work.
- Browser inspection artifacts should go under `output/playwright/`.

## Git / Network Notes

- The machine has global Git proxy configured as `http://127.0.0.1:7892` for both HTTP and HTTPS.
- That proxy was unavailable during the initial clone attempt.
- The repo was cloned successfully with temporary proxy overrides:
  `git -c http.proxy= -c https.proxy= clone --depth 1 https://github.com/bryangerlach/rdgen.git rdgen`

## Browser Notes

- The Chrome DevTools MCP connection did not work in this session even after launching Chrome with `--remote-debugging-port=9222`.
- Playwright was used as fallback through a temporary install in `%TEMP%\rdgen-pw-inspect`, using system Chrome as the executable.
- Saved screenshots currently exist in `output/playwright/`.

## Prior Project Reference

- Previous user-customized fork: `D:\rustdesk_web客户端\rdgen-repo`.
- Treat it as strictly read-only. Do not write, edit, format, move, delete, clean, or generate files inside this old project.
- Useful generic fixes may be ported, but avoid copying personal overlay behavior tied to `zhenzhen122/rustdesk`.

## Upstream RustDesk Source References

### Client

- Current official client source reference: `D:\rustdesk-生成器\rustdesk-src`.
- Remote: `https://github.com/rustdesk/rustdesk.git`; local branch `upstream-master` tracks `origin/master`.
- Synced on 2026-08-09 to official default-branch commit `11190fa54e45fd244ad46b46052f92be6a01d3c5` (`docs: fix comma splice gui tutorial in README.md (#15787)`, committed 2026-08-08 09:33:58 +0800).
- Latest stable tag observed during that sync is `1.4.9` at `6c578292e8ebbbec708b76986ba8c4bc7c509747`; the synced master worktree currently declares RustDesk `1.4.9` in `Cargo.toml` and `1.4.9+67` in `flutter/pubspec.yaml`.
- The `libs/hbb_common` submodule is initialized at `69cea8dafee147848ae88702029f4bf7df7224c3` (`main`). The clone is intentionally shallow and partial (`blob:none`) but has a complete current working tree; fetch more history only when a later question needs it.
- Treat this directory as the clean current-upstream reference for future source questions. Do not modify it unless the user explicitly asks for an upstream-source change. The dirty `rustdesk-src-147-inspect` and `rustdesk-src-149-inspect` trees are separate patch experiments and must not be cleaned or overwritten.

### OSS Server

- Current official OSS server source reference: `D:\rustdesk-生成器\rustdesk-server-src`.
- Remote: `https://github.com/rustdesk/rustdesk-server.git`; local `master` tracks `origin/master`.
- Synced on 2026-08-09 to official default-branch commit `a7736be5e40f85bfc141120dce587e836e5d4b80` (`Delete .github/dependabot.yml`, committed 2026-08-07 16:56:36 +0800).
- Latest stable tag observed during the sync is `1.1.16` at `73523b31cfd25d77dee862e6fc9f5e1fb5e485ef`; current master declares development version `1.1.17` in `Cargo.toml`.
- The `libs/hbb_common` submodule is initialized at `69cea8dafee147848ae88702029f4bf7df7224c3`. The clone is intentionally shallow and partial (`blob:none`) with a complete, clean current working tree.
- Treat this as the clean current OSS server reference for later `hbbs`/`hbbr` questions. Do not modify it unless explicitly requested, and read its own `AGENTS.md` before any future edit; it forbids production `unwrap()`/`expect()` outside stated exceptions and formatting-only churn.

## Current Session Handoff Rules

- Primary working repo remains `D:\rustdesk-生成器\rdgen`.
- The current GitHub repo/fork used for builds is `https://github.com/zhenzhenwq/rdgen.git`.
- `upstream` remains `https://github.com/bryangerlach/rdgen.git`.
- Do not store plaintext server passwords, GitHub tokens, PFX passwords, or API bearer tokens in repository files.
- Credentials were provided in chat during previous work, but repository memory files intentionally omit the secret values.
- Code signing certificate material is outside the repo at `D:\rustdesk-生成器\codesign\`; treat the PFX and password file as sensitive.
- Generator server is reachable at `https://120.55.0.199/`; HTTP port 80 redirects to HTTPS.
- `120.55.0.199` was originally generator-only; a two-pass root audit on 2026-08-10 found no pre-existing RustDesk server. The user then explicitly authorized one isolated, temporary phase-one multi-relay test on this host. The only authorized RustDesk server footprint is `/opt/rdgen-relay-test`, locked user `rdgen-relay-test`, and transient units `rdgen-relay-test-hbbs.service`, `rdgen-relay-test-hbbr-a.service`, and `rdgen-relay-test-hbbr-b.service`. Do not expand this test into a production server or alter the generator without fresh authorization.
- RustDesk-named files under `/opt/rdgen*` are generator source patches and rollback snapshots, not deployed RustDesk services; preserve them with the generator deployment and never delete them as false positives.
- The deployed generator directory on `120.55.0.199` is `/opt/rdgen`, but that server currently does not have `git` installed.
- The live Docker service is `rdgen-rdgen-1`. Container port `8000` is bound only to `127.0.0.1`; Nginx owns public ports 80/443 and applies login rate limiting.
- Let's Encrypt issues the trusted IP certificate. `rdgen-certbot-renew.timer` checks renewal twice daily and reloads Nginx after successful renewal.
- If deploying source changes to `120.55.0.199`, do not assume `git pull` works there. Either install git deliberately, upload a controlled source snapshot, or rebuild/recreate the Docker service from a known copied tree.
- The old project `D:\rustdesk_web客户端\rdgen-repo` remains read-only even if it contains useful reference fixes.

## Phase-Two Smart Multi-relay Design State

- Product discovery and the first-release engineering contract are frozen in `MULTI_RELAY_PHASE2_DECISIONS.md` and `MULTI_RELAY_PHASE2_SPEC.md`. Decisions 0-44 are locked; there is no pending product question.
- The implementation baseline is RustDesk client `1.4.9` at `6c578292e8ebbbec708b76986ba8c4bc7c509747` / `hbb_common` `7e1c392c62d39c364127307cd408421dd5f8cfb0`, plus rustdesk-server `1.1.16` at `73523b31cfd25d77dee862e6fc9f5e1fb5e485ef` / `hbb_common` `83419b6549636ee39dacef7776c473f5802e08d6`.
- Planned architecture is one custom hbbs/controller, unchanged official hbbr `1.1.16` nodes, one outbound-HTTPS agent per relay host, and smart RustDesk `1.4.9` clients on Windows x64/x86, Linux, and Android. macOS is excluded from the smart build.
- Selection optimizes two-peer RTT sum with a per-leg guardrail, then considers configured Mbps, metered/unmetered traffic policy, current utilization, quota, maintenance, and host protection. At most 50 relay nodes are supported; clients probe at most 6 IPv4 candidates.
- Smart `RequestRelay` preserves RustDesk's safe retry pattern: each retry uses a new UUID, but every retry must reuse the same server-signed relay selection and endpoint. Do not reintroduce same-UUID UDP retransmission to old clients.
- Decision 44 keeps upstream rustdesk-server PeerMap IP persistence unchanged for registration security. New smart measurement, scheduling, aggregation, logs, CLI, events, and backups must not persist complete peer IPs or raw per-session measurements.
- The frozen specification passed independent protocol, scheduler/accounting, and operations/security review with no remaining P0/P1 conflicts. This is no longer design-only: production-path client, controller/agent/supervisor, packaging, generator integration, four supported smart workflow builds, and a real Linux strict-WSS requester/target slice exist. No server integration or production deployment is authorized; do not confuse workflow artifacts or the lab VM with a production release.
- Current generator application integration is `5591f33`, synchronized with `origin/master`; local `master` also contains documentation checkpoint `d02ed47`. It is locked to client `1.4.9` root `6c578292...` and `hbb_common` `7e1c392c...`, defaults off, supports only Windows x64/x86, Linux, and Android, requires strict WSS deployment inputs, and excludes macOS. Current server integration branch `rdsmart/phase2-integration-116` is local-only at `6cc7478`: audited traffic correction is followed by Linux state/identity hardening, boot-safe Agent accounting, and a clean-stop supervisor race fix. Its only unrelated worktree change is the user's pre-existing `db_v2.sqlite3`; preserve it. Keep the clean upstream references unchanged and official `hbbr` source unmodified.
- The Rocky 8 dedicated-ext4, non-root-HOME Linux suite is now green at 707/707, and the final strengthened boot-transition/interface-mismatch test also passes. The current Agent and supervisor release is installed only on the authorized lab VM; two consecutive real reboots preserved journal accounting/sequence monotonicity, credentials, keys, revision 2, normal safety, and fresh controller telemetry. The isolated metered traffic-correction proof passed apply/replay/collision behavior; the authoritative unmetered node correctly rejected correction without an accounting mutation. Never re-enroll that node or restore the stale local SQLite snapshot.
- Remaining release gates include Windows/Android install/runtime checks, multi-host/three-region testing, the 50-node load test, the broader supported-distribution install/repair/reboot/uninstall matrix, and production packaging with a non-root controller, bounded logging, verified key ownership, and an actually owned endpoint instead of the lab-only `1.1.1.1/32` alias. Do not push the server branch, dispatch another workflow, alter the production generator/server, or claim production readiness without explicit authorization. Keep disposable build caches bounded because local and VM disk space are operational constraints.

## Current Release State

- The development baseline for the RustDesk `1.4.9` batch was `8ff0593`, matching `origin/master` when work resumed on 2026-07-13.
- The core batch was committed as `8e33770`; `cd2c358` separated hidden-window capability from its default state, and `23d1cf3` completed the compatibility follow-up. Use the latest `master` commit for subsequent fixes.
- The batch changes the form and platform workflows, ports strict optional patch chains, and hardens Linux packaging, macOS signing, uploads, and build inputs.
- Eleven new patch/test files under `.github/patches/` were tracked by the release commit; runtime workflows download patch helpers from the exact `${{ github.sha }}`.
- Public Actions history contains successful manual Windows generator runs for `8e33770` and `cd2c358`, but their artifacts were not audited here. No Linux or Android build has been verified for this batch. macOS was compiled on real GitHub-hosted macOS runners for both Intel and Apple Silicon in validation run `29975374837`.
- The automatic Docker runs for `8e33770` and `cd2c358` failed before image build because Docker Hub login inputs were unavailable.
- The current deployed application release is `d4ec7e498a60f0996b9b10372b8ac0d1b365d10c` (tree `eba9444758cb4b1bc82fc5aef29c269633a4497e`). It retains the full-width management pages and adds server-managed relay selection: generated clients force an empty `override-settings.relay-server` by default so hbbs supplies the relay, while an advanced field can force one explicit hbbr address.
- New registrations require a short-lived email code and start without membership. Staff can create, list, filter, and revoke unused codes for one generation, 3 days, 7 days, 30 days, or lifetime; plaintext activation codes are shown only at creation and stored as hashes. The production SMTP account and authorization value are intentionally absent from repository memory.
- The server application is built from `d4ec7e4`; later documentation-only commits do not change the live image. Push-triggered Docker run `31349924535` failed only at the repository's known Docker Hub login step; it did not dispatch a client build or affect the directly deployed server image.
- GitHub Actions run `29975374837` passed the complete validation matrix for `x86_64` and `aarch64`: customization validation, compilation, embedded configuration packaging, ad-hoc code signing, bundle metadata and architecture checks, DMG creation, `hdiutil verify`, and artifact upload. Validation mode skipped production upload and cleanup callbacks by design.
- A push to `master` starts `docker-build.yml`; it does not dispatch a RustDesk client generator workflow.
- Confirm the current local and remote state with `git status --short --branch`, `git log --oneline -n 8 --decorate`, and a fresh remote query before follow-up release work.

## Current Deployment State

- Deployment ID: `20260810-103245-d4ec7e498a60`.
- Source archive SHA-256: `b5b2ff4cfa00ffcac5c9668618a71e6a0541d6c781fd2c9b89ea330e7bf577bb`. Verified live image: `sha256:d2358abecb4c7bf741e4a96d90bc766c9ad70e876fa27cfc78e29bee71c147c7`.
- The service is `running`, `healthy`, restart count `0`, and has no post-deploy error fingerprints. The complete 189-test suite passed locally and again in the candidate image running Django `5.2.16`; migration rehearsal, relay-form/config assertions, authenticated page checks, static-asset hashes, and an isolated candidate instance also passed.
- Production Nginx now serves only the two exact login assets at `/static/rdgenerator/login-modern.css` and `/static/rdgenerator/auth-build-flow.png`. The prior Nginx configuration is in the rollback backup, `nginx -t` passes, and the existing TLS, redirect, HSTS, login rate-limit, and application proxy rules remain unchanged.
- Public `/login/`, `/register/`, both new static assets, and `/healthz` return 200; `/register/email-code/` rejects GET with 405, HTTP redirects to HTTPS, and anonymous generator access still redirects to `/login/`. Browser verification found the stylesheet and 1254×1254 illustration loaded, no horizontal overflow, and no console issues.
- `.env`, `data`, `exe`, `png`, and `temp_zips` were preserved. `migrate --check` and SQLite `quick_check` pass. The deployment retained 4 users and 39 task rows; the authorized relay test build then added successful row 40. No active client build remains.
- Keep `/opt/rdgen-backups/20260810-103245-d4ec7e498a60`, `/opt/rdgen-previous-20260810-103245-d4ec7e498a60`, and image tag `rdgen-rollback:20260810-103245-d4ec7e498a60` for the current rollback. The backup includes online and final SQLite snapshots, the prior environment and Nginx configuration, the exact source archive, build/test logs, and image metadata. Retain the earlier rollback sets as fallbacks.
- Deployment checks did not submit the live form. After cutover, the user-authorized `RelayPoolTest` Windows x64 build was dispatched specifically to verify the new relay configuration path; it completed successfully and is recorded below.
- The temporary OSS multi-relay test uses official server `1.1.16`: hbbs `120.55.0.199:22116`, relay A `:22117`, and relay B `:23117`, with `ALWAYS_USE_RELAY=Y`. Each transient service is capped at 128 MB and 25% CPU. Real clients verified B/A round-robin and, after A was stopped, automatic reconnection to B in about eight seconds; A was restored and both relays are healthy. This same-host test proves basic list/health/round-robin/failover behavior, not geographic redundancy or independent-host resilience. Preserve the test directory and private key; never copy the private key into Git or chat.

## Historical Verified Outputs

- macOS dual-architecture validation:
  - implementation commit: `5694553478ccde3967446c460e734ae719f278d6`
  - GitHub Actions run: `29975374837`
  - outputs: `MacAudit-x86_64.dmg` and `MacAudit-aarch64.dmg` as separate architecture-specific images, not a Universal binary
  - both app bundles passed architecture, ad-hoc codesign, and DMG checksum verification on real macOS runners
  - local SHA-256: x86_64 `25151cb4d1349fa2055f98393547174c05c7f536bb391d4ba962e072333e234e`; aarch64 `849022e5ca9a84b24cbb7ef233cbb253e0fee8e24a3d1b05b85d18207662eb67`
  - local archive directory: `D:\rustdesk-生成器\rdgen\output\macos-validation-29975374837`
  - production P12 signing, notarization, and stapling were not exercised
- Windows self-signed signing test:
  - filename: `SignTest`
  - UUID: `82f5ea38-c4ab-461e-a090-4e03f5d014bd`
  - GitHub Actions run: `26007760512`
  - Local downloaded outputs:
    - `D:\rustdesk-生成器\sign-test-output\SignTest.exe`
    - `D:\rustdesk-生成器\sign-test-output\SignTest.msi`
  - Both were signed by `CN=RDGen Self-Signed Code Signing`.
- Windows server-managed relay build:
  - filename: `RelayPoolTest`
  - UUID: `42bd21b0-77d2-4182-9ac9-db6758388754`
  - GitHub Actions run: `31350450912`
  - local outputs: `D:\rustdesk-生成器\rdgen\output\relay-client-42bd21b0\RelayPoolTest.exe` and `RelayPoolTest.msi`
  - SHA-256: EXE `eafc6f3d4913a50a8f36c32bc26c066fdbe2df237034859dd1cdf17ebccfc1ea`; MSI `f1d6d6a545f6b59f70e703a2b650ba1c6af9b57a9b557d8cd8657679e3b90480`
  - extracted MSI `custom_.txt` confirms ID server `120.55.0.199:22116`, no top-level relay field, and an empty `override-settings.relay-server`; two real Windows devices then used both relays, and a controlled stop of active relay A caused automatic re-pairing through B in about 18 seconds
  - relay A was restored immediately after the failover test; hbbs, both hbbr units, and the generator finished healthy, with the active session remaining on B
  - both artifacts are timestamped and self-signed by `CN=RDGen Self-Signed Code Signing`; Windows reports an untrusted root unless the public root certificate is explicitly trusted in the appropriate certificate store, so do not describe these signatures as publicly trusted and never distribute the PFX/private key
- Android universal output test:
  - filename: `WuYouDesk`
  - UUID: `9de4743a-ec38-4266-b155-cd383ae64685`
  - Expected and verified outputs on generator server:
    - `WuYouDesk-universal.apk`
    - `WuYouDesk-aarch64.apk`
    - `WuYouDesk-armv7.apk`
    - `WuYouDesk-x86_64.apk`
