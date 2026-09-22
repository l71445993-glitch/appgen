# Project Overview

## What This Project Is

`rdgen` is a Django web application for generating customized RustDesk clients.
The web UI collects RustDesk client customization options, then triggers GitHub Actions workflows to build platform-specific installers or packages.

## Main User Flow

1. User opens the generator page.
2. User selects a target platform: Windows 64-bit, Windows 32-bit, Linux, Android, or macOS.
3. User fills customization fields such as RustDesk version, server host, key, API server, app name, icon, logo, permissions, and advanced settings.
4. Django validates and serializes the form data into a custom RustDesk configuration.
5. Sensitive build inputs are placed into an encrypted zip.
6. Django dispatches the appropriate GitHub Actions workflow.
7. The waiting page polls GitHub run status.
8. The generated client is uploaded back to the Django service and exposed for download.

## Important Source Areas

- `rdgenerator/forms.py`: Django form fields, defaults, choices, and upload validation.
- `rdgenerator/views.py`: form handling, custom config generation, GitHub Actions dispatch, file download/upload endpoints.
- `rdgenerator/templates/generator.html`: main generator UI, inline CSS, inline JavaScript, save/load config behavior.
- `rdgenerator/templates/waiting.html`: build progress page.
- `rdgenerator/templates/generated.html`: successful build download page.
- `rdgenerator/templates/failure.html`: failed build page.
- `.github/workflows/`: platform-specific RustDesk build workflows.
- `rdgen/settings.py`: environment-driven Django/GitHub configuration.

## Live Site Observations

The author's live generator is available at:
`https://rdgen.crayoneater.org/`

Observed page headings:

- RustDesk Custom Client Builder
- Save/Load Configuration
- Select Platform
- General
- Custom Server
- Security
- Visual
- Permissions
- Code Changes
- Other

Observed platform options:

- Windows 64Bit
- Windows 32Bit
- Linux
- Android
- macOS

Observed RustDesk version options:

- nightly / `master`
- `1.4.6` through `1.3.3`

Platform switching on the live page did not visibly hide platform-specific fields. For example, the Android App ID field remains visible for Windows, Linux, and macOS.

## Current Local Artifacts

Screenshots from the live site are saved under:

- `output/playwright/rdgen-home.png`
- `output/playwright/rdgen-windows.png`
- `output/playwright/rdgen-windows-x86.png`
- `output/playwright/rdgen-linux.png`
- `output/playwright/rdgen-android.png`
- `output/playwright/rdgen-macos.png`

## Related Prior Project

The user previously deployed and modified a separate rdgen fork at:
`D:\rustdesk_web客户端\rdgen-repo`

That repository's remote is:
`https://github.com/zhenzhen122/rdgen.git`

The prior project contains useful fixes, but it also includes personal/custom behavior that should not be copied directly into this general-purpose generator.

Prior project themes that appear broadly reusable:

- UTF-8 handling in encrypted secrets extraction.
- MSI Unicode codepage fixes for Windows packaging.
- Longer upload timeouts for large generated artifacts.
- Splitting Windows EXE upload from optional MSI upload.
- Showing only Windows download links for files that actually exist.
- Resolving callback URLs through reusable environment variables.
- Better progress/failure status updates from workflows.
- For hide connection window, forcing password approval mode when `hidecm` is enabled.

Prior project themes that are personal/specific and should be isolated or avoided for a generic generator:

- Checkout and overlay from `zhenzhen122/rustdesk`.
- Custom module copying from that overlay.
- Account/auth gate/client module changes tied to the user's RustDesk fork.
- Chinese-only end-user status strings unless the new project explicitly chooses Chinese localization.

## Current Customized Direction

The current project has moved away from the author's public English UI and toward the user's deployed generator:

- Visible generator UI is Chinese.
- Main visual theme is blue and white.
- Sponsor/source-code footer links were removed from the generator page.
- The generated/download/failure/waiting pages have been localized and styled consistently enough for current deployment.
- The generator is intended to remain generally usable, not locked to the user's older personal fork.

## Current Implemented Feature Set

Important implemented changes compared with the upstream author's baseline:

- Hide connection window support:
  - `hidecm` now forces `approve-mode = password` in generated settings.
  - `verification-method` is set to permanent-password behavior when hiding the connection window.
  - Windows workflows apply `hidecm.diff` before build.
- Hide RustDesk settings entry:
  - Form field `settings` controls whether client settings are allowed or disabled.
  - `settingsN` writes `disable-settings = Y`.
  - Windows workflows can apply `hide_settings_menu.diff`.
- Built-in server settings:
  - `rdgenerator/views.py` embeds the ID server, API server, and server key used by the build workflow.
  - Relay selection is server-managed by default: an empty `override-settings.relay-server`
    makes the client use the healthy relay returned by hbbs, including when an older local
    RustDesk configuration still contains a fixed relay.
  - The optional fixed-relay field writes one explicit address to
    `override-settings.relay-server`; comma-separated relay pools belong in hbbs, not the client.
  - Legacy exported configs that stored `relay-server` in the manual default/override text
    are promoted into the dedicated field (manual override wins) instead of being silently lost.
- Windows self-signed code signing:
  - GitHub Actions can sign generated Windows EXE, DLL, and MSI outputs using `CODE_SIGN_PFX_BASE64` and `CODE_SIGN_PFX_PASSWORD`.
  - External signing service behavior remains available if configured.
  - If no signing secrets are configured, workflows skip signing rather than fail.
- Android universal APK output:
  - Android matrix still builds three ABI split APKs.
  - The deploy job now creates and uploads a fourth `-universal.apk`.
  - The intended Android download set is:
    - `${filename}-universal.apk`
    - `${filename}-aarch64.apk`
    - `${filename}-armv7.apk`
    - `${filename}-x86_64.apk`

## Frozen Phase-two Smart Multi-relay Plan

Phase one is implemented and verified: generated clients leave relay choice to hbbs, official OSS hbbs accepts multiple hbbr addresses, and real Windows clients used both test relays and reconnected after the active relay stopped.

Phase two is fully specified and implementation has started in isolated writable worktrees. The authoritative design records are:

- `MULTI_RELAY_PHASE2_DECISIONS.md`: product decisions 0–44 with no pending question.
- `MULTI_RELAY_PHASE2_SPEC.md`: frozen protocol, scheduler, accounting, agent, security, installer, generator, release, and validation contract.

The planned first release uses a custom RustDesk server `1.1.16` hbbs/controller, unchanged official hbbr nodes, a lightweight outbound-HTTPS agent on each relay host, and modified RustDesk `1.4.9` clients for Windows x64/x86, Linux, and Android. It selects one relay per connection from at most six candidates using the two peers' combined RTT, a per-peer latency guardrail, configured bandwidth, live utilization, metered/unmetered traffic policy, quota, maintenance, and host protection. Missing monitoring data falls back to the official TCP-healthy pool without overriding explicit disable/maintenance or confirmed quota exhaustion.

This design supports at most 50 IPv4 relay nodes, keeps a signed smart requester's retries on the same signed relay while using a new UUID per attempt, and leaves the official hbbr data path unchanged. The frozen compatibility correction makes smart admission directional: an offer-absent official/old requester always stays on the complete OSS path, with no probe wait, selection, smart owner, or anonymous IP/NAT index, even when the target is smart. A signed smart requester can still interoperate with an official/old target through a verifiable unique legacy owner. New smart data does not persist complete peer IPs or raw per-session measurements; upstream PeerMap registration-security behavior remains unchanged. The first release is CLI/config driven; customer API, web administration, notifications, runtime licensing, automatic upgrades, IPv6, macOS smart builds, and hbbs HA remain deferred.

On 2026-08-13, the first real local-process S1 integration passed with server commit `f8d1766a9b4393cf179dda976103cde8f26799a7` (tree `493565835e617b2353441e3ce9f8c6ec0d02d6c4`), client commit `2441b53d5667050cc6fe80c1428f18e178311346`, and client `hbb_common` commit `b3183ee848c1566e59737e878a418bbb177dc2bc`. Attempt UUID `91a64b5d-dec0-4d90-9782-2e0d2a2b883d` completed in 8.3 seconds: selected relay R2 recorded one new request and one completed pair, while non-selected R1 recorded neither (`R2 1/1`, `R1 0/0`). This verifies the bounded S1 fixture across real local hbbs, two hbbr processes, target B, and requester A.

The S1-only LAN endpoint allowance, rendezvous key-exchange helper, and metrics-availability bridge are feature-gated test support. They are not production configuration and do not prove a production raw-TCP smart rendezvous closed loop; production validation should prefer strict WSS. Nothing from this milestone was pushed or deployed, and no production system was accessed.

The same-UUID S2 local milestone also passed on 2026-08-13 with server commit `fa464c262fd3401a6db87dcbe74e7fe3991e0c1b` (tree `0bbf9db7ea43aa1be4986f3963bcc743ec18499b`), client parent `0b997fea0caa69cd4f69d3cfcd6a681d3b7e8992`, and client `hbb_common` `b3183ee848c1566e59737e878a418bbb177dc2bc`. Its UUID was `0737e04a-77f4-4a84-8bfc-8f0019492b9f`; all three same-UUID lanes produced the same decrypted protobuf frame SHA-256 `b362d0f9fe11d8a84fe96243e80ab130d1b81b3b92a0214c35b53d987689e3aa`. hbbs observed one each of owner, enqueue, join, and replay; B created and requested pairing once; A requested hbbr owner pairing once; selected R2 recorded one new request and one pair, while R1 remained at zero (`R2 1/1`, `R1 0/0`). The run finished in about 9.18 seconds, below the 30-second bound. S1/S2 contract, dry-run, and offline checks passed, and test worktrees/processes were cleaned. Nothing was pushed or deployed.

The different-UUID S3 final local milestone passed on 2026-08-13 with server HEAD `d34bcaec3b86d89614037df03dffcff43d01ee4f` (tree `a2173c417b968a7dda45e8c1ba2dd230d16d36e7`), client `051a54c23a55c5c76272a09c3b9de0557088a80a`, and client `hbb_common` `b3183ee848c1566e59737e878a418bbb177dc2bc`. UUID1 `68c25b4d-f9de-4a4b-a66d-2098b924ec5f` and UUID2 `25075eb6-fefd-447c-8bfd-507ec3ad2c37` produced response SHA-256 values `fbb650ead7c078533bbc1ad7c5e0a6197512d6ff684c6d7cc772413326e0790` and `12dd0e3fea68f17a045fe97dc12d4fdcab3cc927f819ecdadd8ac5dbc8e34ef1`, respectively. The recovery interval was 5 ms and the run completed in 7,563 ms. For each UUID, hbbs owner/enqueue/join/replay was `1/1/0/0`, and B create/pairing was `1/1`; A was `0/0` for UUID1 and `1/1` for UUID2. R1 remained `0/0` for both UUIDs; R2 was `1/0` for UUID1 and `1/1` for UUID2. S1/S2/S3 contract checks and locked server/client offline checks passed; the database was restored, and remaining test processes and owned run roots were both zero. Nothing was pushed or deployed, and no production system was accessed. The next phase is total integration closeout: merge modules not yet present in integration, resolve the uncommitted handler work, run the full regression suite, and then produce a runnable vertical slice.

By 2026-08-20, the production-path closeout had moved beyond those fixture milestones. Server integration `9ddf237` includes the separated relay-supervisor composition, signal-aware shutdown, audited maintenance convergence, and bounded read-only node inventory. Generator commits `fd13daf`, `c99801e`, and `ab1497e` add an off-by-default smart mode locked to RustDesk 1.4.9, strict-WSS deployment validation, supported-platform gating, build history, true-only four-workflow patch application, exact baseline/digest/marker checks, production client patches, compatibility fallback, and bridge-compatible lifecycle invalidation. The generator's 200 Django tests, checks, migration check, workflow tests, `actionlint`, and offline patch smoke all pass. These are local implementation results, not released artifacts: no smart workflow was dispatched, pushed, or deployed, and the real four-platform artifact/install/runtime and strict-WSS multi-host release gates remain open.

## External Systems

- Live generator URL: `https://120.55.0.199/`
- Live generator host directory: `/opt/rdgen`
- Live generator Docker service: `rdgen-rdgen-1`
- Current project repo/fork: `https://github.com/zhenzhenwq/rdgen.git`
- Upstream author's repo: `https://github.com/bryangerlach/rdgen`
- Author's public generator: `https://rdgen.crayoneater.org/`
- Old user project, read-only only: `D:\rustdesk_web客户端\rdgen-repo`

Secrets are intentionally not stored here. Ask the user or use already configured secure stores when a task requires SSH, GitHub, or signing credentials.

## Current Test Links

- Server-managed relay Windows verification:
  `https://120.55.0.199/check_for_file?filename=RelayPoolTest&uuid=42bd21b0-77d2-4182-9ac9-db6758388754&platform=windows`

- Android universal verification:
  `https://120.55.0.199/check_for_file?filename=WuYouDesk&uuid=9de4743a-ec38-4266-b155-cd383ae64685&platform=android`
- Old Android report that only has pre-fix split APKs:
  `https://120.55.0.199/check_for_file?filename=WuYouDesk&uuid=dcaa5218-3b21-4883-a4e9-d28a96c467eb&platform=android`
