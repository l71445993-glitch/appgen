# New Window Handoff

This is the current durable handoff for the RustDesk generator work.

## Workspace And Safety

- Main repository: `D:\rustdesk-生成器\rdgen`
- Branch: `master`
- User fork/build repository: `https://github.com/zhenzhenwq/rdgen.git`
- Upstream: `https://github.com/bryangerlach/rdgen.git`
- Deployed generator: `https://120.55.0.199/`
- Host-purpose boundary: `120.55.0.199` remains the generator production host. A root audit on 2026-08-10 found no pre-existing RustDesk server; afterward, the user explicitly approved one isolated temporary multi-relay test. Its exact footprint is `/opt/rdgen-relay-test`, user `rdgen-relay-test`, and the three `rdgen-relay-test-*` transient systemd units. Do not expand it into a production server without fresh approval.
- Old reference project: `D:\rustdesk_web客户端\rdgen-repo`

The old reference project is strictly read-only. Do not edit, format, move, delete, clean, or generate files inside it.

Do not write server passwords, GitHub tokens, signing passwords, private certificate material, Django secrets, or API bearer tokens into repository files or answers. Code-signing material under `D:\rustdesk-生成器\codesign\` is sensitive and outside this repository.

Do not submit the live generator form unless the user explicitly asks. A push to `master` automatically starts the repository's Docker image workflow, but it does not dispatch a RustDesk client generation workflow.

The full generator path requires public GitHub Actions callbacks. Local Docker cannot provide meaningful end-to-end generation coverage and is not a release prerequisite; use local services only for UI/form inspection unless the user explicitly requests local container work.

## Resume Checkpoint (2026-08-21 pause after host provisioning)

- Generator application integration remains `5591f33`, synchronized with `origin/master`; local `master` contains documentation-only checkpoints and has not been pushed. The four supported smart workflows pass, and the retained Linux DEB remains `D:\rustdesk-生成器\artifacts\validation-20260821\linux-x86_64-deb\RDSmartWss149Live-x86_64.deb`, 23,521,216 bytes, SHA-256 `0ba90ac80d850df86b5118899efe6b98fb262752b063754b6be608a1ca76edc3`. The real strict-WSS requester/target production-client slice remains proven on hbbr WSS data port 24119.
- Server integration is local-only at `5259251`, after `8471cc4`, `b929a7e`, `594da12`, `1b5093b`, `3087e53`, and `9611a91` on top of the reboot-safe `6cc7478` baseline. `1b5093b` closes the controller local-admin ownership conflict with a root-owned systemd socket unit, root/admin `0660` socket, root/admin `0750` runtime directory, exact fd 3 activation validation, and a direct-process fallback that retains process ownership. `3087e53` removes an enrollment-expiry millisecond clock race without weakening expiry semantics. Do not push this branch without explicit authorization. Its only remaining worktree change is the user's pre-existing `db_v2.sqlite3`; preserve it.
- `9611a91` adds `hbbs --validate-smart-relay-config <config>` and wires it after the packaging shell validator as a second `ExecStartPre`. It loads only the existing mode-`0600`, single-link, service-owned hbbs key; exercises the authoritative strict TOML, controller database, deployment identity, TLS/trust, DNS-origin, enrollment-secret, and local-admin activation validators; and exits before listener binding, writable service opening, migration, replay-journal creation, or update-thread startup. The actual failure-path CLI probe left its key and state unchanged.
- `594da12` fixes a real concurrent idempotency race found by the unrestricted full suite: an identical enrollment request that commits between the initial replay lookup and fast admission check now replays through the existing secret/parameter checks, while a different pending enrollment remains fail-closed. The isolated concurrency test passed 100 consecutive runs. The final WSL Ubuntu 24.04 library suite is green at 715/715, `cargo check --bin hbbs` passes, and the packaging static plus executable root shell tests pass.
- `b929a7e` adds a recoverable controller package lifecycle with a fixed nine-file allowlist, atomic transaction manifest, exact same-version payload hashing, bounded repair backups, interrupted-transaction recovery, status, repair, and state-preserving uninstall. It never starts/enables services or purges controller state. `8471cc4` adds the deterministic payload renderer: it validates source binaries and package inputs, renders the fixed controller filesystem contract into a private sibling scratch directory, applies the shell and Rust semantic configuration preflights, verifies systemd/socket/tmpfiles/logrotate consistency, and atomically publishes only a new output directory. The complete packaging static and executable shell suite passes.
- `5259251` adds the resumable controller host-account/filesystem transaction. It creates dedicated no-login identities through `systemd-sysusers`, records immutable UID/GID values, creates the empty config/state/secret/dotenv/log boundaries, resumes an injected interruption, and rejects later drift instead of rewriting it. It intentionally creates no TOML, database, certificate, deployment key, firewall rule, or service state. The complete packaging static and executable root shell suite passes. Resume with the production cryptographic provisioner in hbbs, then connect this host step, package lifecycle, signature preflight, semantic validation, and bounded service activation through the public installer.
- The authorized lab VM still runs controller `974a2a4` and Agent/supervisor release `6cc7478`; this checkpoint made no lab or production mutation. `rdsmart-lab-address`, `rdsmart-controller`, `rdsmart-hbbr-supervisor`, and `rdsmart-agent` were previously proven enabled/active across two whole-VM reboots with zero failed RDSmart units, fresh telemetry, byte-identical credentials/keys, monotonic accounting evidence, normal safety, and zero pending reports. Root-only backup `/var/backups/rdsmart/pre-6cc7478-20260821T091315Z` and the earlier backups remain. Never re-enroll the generation-1 node, replace its credential/key, or restore `vm-xfer/state.sqlite3`.
- The loopback `1.1.1.1/32` address and root-run controller remain lab-only. They are not a production packaging or reachability claim. The native payload/lifecycle is source-tested but has not yet passed the supported-distribution clean-install/repair/reboot/uninstall matrix on owned non-root endpoints. Production generator and relay-test host `120.55.0.199` were not changed.
- Local cleanup deleted only the verified `/tmp/rdsmart-*` WSL build target, SQLx scratch database, and test logs, reclaiming 6.9 GiB inside Ubuntu. Docker had zero images, containers, volumes, and build cache and was stopped; Ubuntu and `docker-desktop` are both stopped. `fstrim` completed, but the exact 8.962 GiB Ubuntu VHDX could not be compacted because `Optimize-VHD` requires administrator permission. Final host free space was approximately 56.45 GiB on C: and 243.58 GiB on D:. No repository file, retained validation artifact, VM transfer release, backup, credential, key, or database was deleted.
- The current usable milestone includes the four smart workflow builds, retained Linux strict-WSS requester/target evidence, the 715-test server suite, reboot-safe lab controller/Agent/supervisor operation, semantic side-effect-free preflight, and the source-tested native payload/lifecycle. Full release still requires public one-command account/configuration/secret provisioning, native firewall and backup/restore mutations, Windows x64/x86 and Android installation/runtime, the six-distribution lifecycle matrix, multi-host three-region behavior, the 50-node load test, and owned-endpoint non-root production verification. No production deployment, workflow dispatch, repository push, or authoritative plan conversion was performed.

## Pause Checkpoint (2026-08-20 23:10 +08)

- Generator `master` was pushed through `815b1b0` (`fix: enforce smart release WSS API config`). Smart builds now place the HTTPS API endpoint in both the top-level custom configuration and `override-settings.api-server`; the locked hbb patch was regenerated and all focused Django, packaging, workflow, patch-smoke, actionlint, and exact hbb WSS tests passed. Client source checkpoints are root commit `6f1bf55` and hbb commit `67026baa`.
- Linux validation run `32379145134` built both native architectures and both AppImages successfully. Its final conclusion is failure only because both Flatpak jobs reached `appstream-compose` and then failed with `bwrap: execvp appstream-compose: No such file or directory`. The retained artifacts are x86_64 AppImage `9411630527`, aarch64 AppImage `9411626373`, and bridge artifact `9410364917`; the temporary DEB artifacts were removed by workflow cleanup before the interrupted VM download completed. Fix/install the Flatpak builder dependency and rerun Linux before claiming a complete Linux matrix.
- A real generic 1.4.9 Linux client proved that the configured endpoint changes from `ws://` to strict `wss://` when the hard API fallback is present. That test exposed a second production blocker: hbbs returned `NOT_SUPPORT` to `RegisterPk` on WSS and smart target traffic still used UDP, so a strict-WSS target could not remain registered or receive probe/selection/relay requests.
- Server integration commit `9f4c257` (`fix: support smart relay target delivery over WSS`) shares UDP/WSS registration validation, keeps a generation-guarded WSS target writer registry, sends probe/selection/RequestRelay over the registered target stream, and maintains liveness with a 10-second heartbeat. Linux `cargo test --no-run`, the two focused `target_stream` tests, and two live candidate hbbs restarts passed. A real production client registered over Cloudflare WSS, stayed connected across multiple heartbeat periods, accepted a generated permanent password, and no longer logged `unknown RegisterPkResponse`.
- The two-client requester-to-target gate is not complete. The fresh DEB download timed out and was cancelled when work paused. Resume by fixing/rerunning Linux, downloading the x86_64 DEB promptly, then run isolated requester and target users through real `--connect <id> --password <value>` and prove smart negotiation plus hbbr traffic before promoting the server snapshot.
- The lab was returned to a safe baseline before pausing: `rdsmart-hbbs-baseline.service` runs `/usr/local/libexec/rdsmart/03792f3/hbbs`; its four ports and `rdsmart-agent.service` are active. Temporary WSS, Xvfb, target-client services, target user/home, password/ID files, partial downloads, installed test client, and candidate hbbs binary were removed. The authoritative controller DB and generation-1 agent credential were not changed or re-enrolled.
- Local Docker cleanup removed 8.4 GiB of Rust target data, the 2.58 GiB task container, and its 298 MiB Rocky Linux image. Docker now has zero images/containers/build cache; `D:` has about 276 GiB free. The reusable Cargo registry cache under `.build-cache/cargo-rocky8` is about 0.25 GiB and was retained after the shell safety policy rejected recursive deletion.
- Production remains unchanged and healthy on old application `d4ec7e4`. SSH to `120.55.0.199` still rejects the supplied password, so deployment cannot resume until access is restored or a key is installed. Do not retry the rejected password repeatedly, and do not deploy or expand the temporary relay footprint without fresh confirmation.

## Latest Operational Checkpoint (2026-08-20 19:47 +08)

- The latest generator application commit is `34e6e23`; `master` also contains the current durable handoff. Push-triggered Docker runs `32362878501` and `32365731821` reached GitHub successfully and failed only at `Login to Docker Hub`; no client workflow was dispatched. The public production generator still redirects to its healthy login page and remains on application commit `d4ec7e4`. The supplied root password is accepted by the lab VM but was rejected by `120.55.0.199`, and this workstation has no SSH key for that host. Do not claim that `fd13daf..34e6e23` is deployed until host access or the registry credential is repaired and the live tree is verified.
- Server integration is at local commit `03792f3`. That commit pins `migrations/smart_relay/*.sql` to LF after a Rocky build from the Windows bind mount embedded CRLF SQLx checksums and correctly refused the existing LF-created database. All ten durable migration checksums were matched offline before the corrected build was installed. The active VM hbbs SHA-256 is `fe90e42f6aafca5971f14683cc0cd5f413d08a9714d7977fb27fd5484986e9f3`.
- The authoritative VM node `35255ea8-658d-4d46-8e98-8fbeac4ce769` retains its original generation-1 credential. Never re-enroll it. The controller DB, credential key, and agent key were backed up before the upgrade; the main rollback archive is `/opt/rdsmart-slice/backups/pre-9ddf237-20260820T112143Z.tar.gz`, mode `0600`, SHA-256 `b9cc10e82534fe0b37d8442ba0e7d7ef01ce93c6866e4a314ff9eab5ac750f1d`.
- The VM now has distinct no-login `rdsmart-agent` UID 979 and `rdsmart-relay` UID 980 accounts with IPC GID 980. `rdsmart-hbbr-supervisor.service` and `rdsmart-agent.service` are enabled and active. The supervisor owns the official hbbr child, `/run/rdsmart-hbbr-supervisor/control.sock` is `0660 rdsmart-relay:rdsmart-ipc`, and the durable supervisor state is `0600` at revision 2/mode active. A real stop/reap/socket-delete/port-close/rebind/restart gate passed.
- The bounded gate ran twice with `--max-applied 2`: revision 1 applied `draining`, revision 2 applied `active`, both services exited 0, and the offline agent journal moved from accepted sequence 8 to 12 with `next_report_sequence=13`, `applied_revision=desired_revision=2`, no pending report, and safety `normal`. The permanent agent then started and a systemd restart preserved fresh telemetry. Local TCP connect to `1.1.1.1:24117` passed, but this is a VM-local `/32` lab alias routed through `lo`; it is not proof of external ownership or client reachability.
- The controller remains an explicitly temporary root-run process rather than the gated non-root controller systemd candidate. The host's NSS configuration includes `sss`, so the strict packaging validator intentionally rejects it, and the frozen local-admin socket ownership conflict is still unresolved. Do not turn this lab slice into a production packaging claim. Firewalld was not expanded because `1.1.1.1` is only a local collision-prone test alias.
- VM upload staging, the invalid CRLF release, and the expired enrollment artifact were removed after the verified backup. The retired v1 run config was preserved as `/opt/rdsmart-slice/run.v1-retired-20260820.json`. Local default/rocky targets remain absent; two release builds each cleaned about 1.4 GiB of container target data, and three unused Docker images were removed. The only retained local release is `D:\rustdesk-生成器\vm-xfer\release-03792f3-rocky8-deploy` (about 22 MiB).
- Remaining release blockers are: restore generator production access or registry delivery, deploy and verify `34e6e23`, dispatch and pass the four smart Windows x64/x86/Linux/Android workflows, and execute a real domain/certificate-backed strict-WSS requester/target vertical slice. The current IP-only lab topology and S1-S3 fixtures do not satisfy that client release gate.

## Upstream RustDesk Source References

### Client

- Clean current-source directory: `D:\rustdesk-生成器\rustdesk-src`.
- Official remote: `https://github.com/rustdesk/rustdesk.git`; branch `upstream-master` tracks `origin/master`.
- Verified against the official remote HEAD on 2026-08-09 at `11190fa54e45fd244ad46b46052f92be6a01d3c5`, committed 2026-08-08 09:33:58 +0800 with subject `docs: fix comma splice gui tutorial in README.md (#15787)`.
- Latest stable tag observed is `1.4.9` at `6c578292e8ebbbec708b76986ba8c4bc7c509747`. The current master manifests declare `1.4.9` / Flutter `1.4.9+67`.
- `libs/hbb_common` is initialized at `69cea8dafee147848ae88702029f4bf7df7224c3`. The clone is shallow and partial but the current source working tree is complete and clean; fetch additional history on demand.
- Use this directory for later questions about the latest official client. Do not confuse it with the dirty, preserved patch-test directories `rustdesk-src-147-inspect` and `rustdesk-src-149-inspect`, and do not edit any of the three without a user-requested source change.

### OSS Server

- Clean current-source directory: `D:\rustdesk-生成器\rustdesk-server-src`.
- Official remote: `https://github.com/rustdesk/rustdesk-server.git`; local `master` tracks `origin/master`.
- Verified against official remote HEAD on 2026-08-09 at `a7736be5e40f85bfc141120dce587e836e5d4b80`, committed 2026-08-07 16:56:36 +0800 with subject `Delete .github/dependabot.yml`.
- Latest stable tag observed is `1.1.16` at `73523b31cfd25d77dee862e6fc9f5e1fb5e485ef`; current master declares development version `1.1.17`.
- `libs/hbb_common` is initialized at `69cea8dafee147848ae88702029f4bf7df7224c3`. The shallow/partial clone has a complete and clean current worktree containing the `hbbs`, `hbbr`, Docker, systemd, Debian, and Kubernetes sources.
- Use this directory for later questions about the official OSS rendezvous/relay server. Read its repository-local `AGENTS.md` before editing and keep it unchanged unless the user requests a source modification.

## Frozen Phase-two Smart Multi-relay Design

- `MULTI_RELAY_PHASE2_DECISIONS.md` contains decisions 0-44. Product discovery is complete and there is no pending first-release question.
- `MULTI_RELAY_PHASE2_SPEC.md` is the frozen first-release engineering contract. Protocol, scheduler/accounting, and operations/security terminal reviews found no remaining P0/P1 conflict.
- Exact implementation baselines are client `1.4.9` (`6c578292...`, hbb `7e1c392c...`) and server `1.1.16` (`73523b31...`, hbb `83419b65...`). The clean source-reference directories remain read-only; implementation requires separate writable worktrees.
- Planned components are custom hbbs/controller, unchanged official hbbr, one outbound-HTTPS relay agent, local CLI, and smart client patches for Windows x64/x86, Linux, and Android. The first release is IPv4-only, one controller, and at most 50 relays; macOS/API/Web UI/notifications/upgrades/runtime licensing/HA are deferred.
- Scheduling uses two-peer RTT sum with a per-leg guardrail plus bandwidth, utilization, metered quota, maintenance, and host-safety policy. Client probing is bounded to six candidates. Missing monitoring falls back to compatible official TCP-health selection while explicit admin policy and confirmed quota exhaustion remain authoritative.
- Every smart `RequestRelay` retry generates a new UUID as upstream does, but reuses one server-signed selection and endpoint. This is the frozen compatibility rule for both smart and old target clients.
- Decision 44 preserves upstream PeerMap's existing registration-security IP storage; all newly added smart measurement/session data obeys the stricter non-persistence boundary.
- Phase-two implementation now exists only in isolated writable worktrees. The first real local-process S1 integration passed on 2026-08-13 with server `f8d1766a9b4393cf179dda976103cde8f26799a7` (tree `493565835e617b2353441e3ce9f8c6ec0d02d6c4`), client `2441b53d5667050cc6fe80c1428f18e178311346`, and client `hbb_common` `b3183ee848c1566e59737e878a418bbb177dc2bc`.
- S1 attempt UUID `91a64b5d-dec0-4d90-9782-2e0d2a2b883d` completed in 8.3 seconds. Selected R2 recorded one new request and one pair; non-selected R1 recorded neither (`R2 1/1`, `R1 0/0`). The fixture crossed real local hbbs, two hbbr processes, target B, and requester A.
- The LAN endpoint allowance, rendezvous key-exchange helper, and metrics-availability bridge are feature-only S1 test support. They are not production behavior and do not establish a production raw-TCP smart closed loop; production validation should prefer strict WSS.
- The same-UUID S2 local milestone passed with server `fa464c262fd3401a6db87dcbe74e7fe3991e0c1b` (tree `0bbf9db7ea43aa1be4986f3963bcc743ec18499b`), client parent `0b997fea0caa69cd4f69d3cfcd6a681d3b7e8992`, and client `hbb_common` `b3183ee848c1566e59737e878a418bbb177dc2bc`. UUID `0737e04a-77f4-4a84-8bfc-8f0019492b9f` completed in about 9.18 seconds, below the 30-second limit.
- All three same-UUID lanes produced decrypted protobuf frames with SHA-256 `b362d0f9fe11d8a84fe96243e80ab130d1b81b3b92a0214c35b53d987689e3aa`. hbbs recorded owner/enqueue/join/replay once each; B create/pairing and A hbbr owner/pairing each occurred once; selected R2 was `1/1`, and R1 was `0/0`.
- S1/S2 contract, dry-run, and offline checks passed, and test worktrees/processes were cleaned.
- The different-UUID S3 final local milestone passed with server HEAD `d34bcaec3b86d89614037df03dffcff43d01ee4f` (tree `a2173c417b968a7dda45e8c1ba2dd230d16d36e7`), client `051a54c23a55c5c76272a09c3b9de0557088a80a`, and client `hbb_common` `b3183ee848c1566e59737e878a418bbb177dc2bc`. UUID1 `68c25b4d-f9de-4a4b-a66d-2098b924ec5f` and UUID2 `25075eb6-fefd-447c-8bfd-507ec3ad2c37` produced response SHA-256 values `fbb650ead7c078533bbc1ad7c5e0a6197512d6ff684c6d7cc772413326e0790` and `12dd0e3fea68f17a045fe97dc12d4fdcab3cc927f819ecdadd8ac5dbc8e34ef1`, respectively. The recovery interval was 5 ms and total duration was 7,563 ms.
- For each S3 UUID, hbbs owner/enqueue/join/replay was `1/1/0/0`, and B create/pairing was `1/1`. A was `0/0` for UUID1 and `1/1` for UUID2; R1 stayed `0/0` for both UUIDs, while R2 was `1/0` for UUID1 and `1/1` for UUID2.
- S1/S2/S3 contract checks and locked server/client offline checks passed. The database was restored, and remaining processes and owned run roots were both zero. Those milestones remain fixture evidence rather than a production strict-WSS proof.
- Total integration closeout has since advanced substantially. Server branch `rdsmart/phase2-integration-116` is at local commit `03792f3` after `248cacb` (separate relay-supervisor UID/IPC composition), `a4e2f0c` (audited drain/force-offline/resume convergence), `9ddf237` (strict read-only `node list`), and the LF migration build lock. Rocky 8 release builds and focused Linux tests pass. The full 684-test Linux library run previously reported 649 passes and 35 environment/security-fixture failures; the affected integration, protocol, local-admin, CLI, supervisor, and packaging gates are green, but the full suite must not be described as green.
- Generator commits `fd13daf`, `c99801e`, and `ab1497e` add the off-by-default `smartMultiRelay` form/history/migration path, exact 1.4.9 and strict-WSS validation, true-only application in Windows x64/x86, Linux, and Android workflows, locked root plus `hbb_common` production patches, fixture exclusion, reason-code compatibility fallback, and network/lifecycle invalidation. `ab1497e` fixes the lifecycle bridge to reuse official `mainCheckConnectStatus`; a new FFI method would have been absent from the bridge artifact generated before smart patch application. On 2026-08-20, all 200 Django tests, system checks, migration-drift checks, three workflow tests, `actionlint`, and the complete offline apply/disable/wrong-baseline smoke contract passed. Commits through `34e6e23` are pushed, but the Docker image run failed at the existing Docker Hub login gate and no smart client workflow or artifact exists yet.
- The VM node is already enrolled with credential generation 1 and must not be re-enrolled. Its controller DB is authoritative. The corrected controller, separate supervisor, official hbbr child, and permanent agent now run the verified revision-2 active state with fresh telemetry. This completes the local server/agent vertical slice, not a production endpoint or strict-WSS client proof; retain the packaging, external-address, generator-deployment, and four-platform gates above.

## Current Release Batch

The active batch adapts the generator to RustDesk `1.4.9` while retaining `1.4.7` and `1.4.8` compatibility for strict optional patches.

The batch includes:

- RustDesk `1.4.9` as the form and workflow default.
- Windows x64, Windows x86, Linux, macOS, and Android patch-chain compatibility.
- Strict patch failures instead of `continue-on-error` for selected customizations.
- Version/platform capability checks in Django and matching dynamic UI visibility.
- Hidden-connection-window capability is separate from its default state. New forms keep the settings entry available, legacy POSTs retain their old default-on meaning, and Windows x86 exposes the same user toggle through Sciter. Flutter and Sciter write explicit `Y`/`N` overrides so users can disable a build default even when the app name remains `RustDesk`.
- Safer build inputs, manual settings, portable artifact names, Windows reserved-name checks, and bounded name lengths.
- Linux native packages, AppImage, and Flatpak customization and upload reliability fixes.
- Beijing Linux customization is accepted only for the verified `1.4.7`, `1.4.8`, and `1.4.9` tags; the UI and Django validation both enforce this boundary.
- macOS NASM `2.16.03`, packaged custom config, whole-bundle P12 signing, verification, and ad-hoc fallback signing.
- Android universal plus split APK output retained and hardened.
- Strict HTTP failure handling for generator/API uploads and external Windows signing requests.
- Shared Actions/cache/reusable-workflow cleanup.

Eleven new patch and test files belong to the batch and must never be omitted from its commit:

- `.github/patches/android_custom_config.py`
- `.github/patches/apply_linux_base_fixes.py`
- `.github/patches/customize_appimage_recipe.py`
- `.github/patches/customize_flatpak_manifest.py`
- `.github/patches/customize_linux_native_packages.py`
- `.github/patches/delay_fix.py`
- `.github/patches/hide_settings_menu.py`
- `.github/patches/rustdesk_default_linux_149.diff`
- `.github/patches/smoke_149_patch_chain.py`
- `.github/patches/test_linux_packaging_customization.py`
- `.github/patches/validate_customization.py`

Runtime patch helpers are downloaded from the current `${{ github.sha }}`; the smoke and packaging test scripts are local verification tools. Keep all eleven files in the same release commit so the implementation and its repeatable checks remain complete.

## Repository State

- Development baseline: `8ff0593`, which matched `origin/master` when this batch resumed.
- Core release commit: `8e33770` (`Adapt generator for RustDesk 1.4.9`).
- First capability-state follow-up: `cd2c358` (`Decouple hide window capability from default state`).
- Compatibility follow-up: `23d1cf3` (`Fix hide window capability compatibility`).
- Auth and task-security release: `13408fb` (`Add authenticated user management`, tree `c1b8bd7ed1dd30209a13f6e59fbf42297aaf3056`).
- Current deployed application release: `d4ec7e498a60f0996b9b10372b8ac0d1b365d10c` (`Support server-managed relay selection`, tree `eba9444758cb4b1bc82fc5aef29c269633a4497e`). It retains the full-width management workspace and adds an advanced fixed-relay field while making hbbs-selected relay the default.
- The live application is built from `d4ec7e4`. Documentation-only commits after that application commit do not change the server image. Push-triggered Docker run `31349924535` stopped at the known Docker Hub login step and did not dispatch a RustDesk client workflow.
- Treat the latest `master` commit containing this handoff as the authoritative batch state.
- The latest documentation state also includes the frozen phase-two decision/specification files; it does not change the live `d4ec7e4` application image.

## Verified State

- The optional patch chains for Windows, Windows x86, Linux, macOS, and Android were each run twice against RustDesk `1.4.7`, `1.4.8`, and `1.4.9` sources.
- Linux AppImage, Flatpak, RPM, SUSE, Arch, URI-scheme, service-config, and DEB purge customizations passed repeatability checks against real RustDesk `1.4.7`, `1.4.8`, and `1.4.9` file layouts.
- Django: 38 tests pass; system checks report no issues. Coverage includes new-form unchecked semantics, legacy POST migration, unknown schema handling, and settings-entry requirements for both hidden-window default states.
- Windows x86 patch chains ran twice on real RustDesk `1.4.7`, `1.4.8`, and `1.4.9` sources after adding the Sciter `allow-hide-cm` control.
- Linux packaging customization: 20 focused regression tests pass. They cover Python 3.6 compatibility in the Ubuntu 18.04 native container, exact `rustdesk` name handling, RPM metadata rejection, AppImage YAML quoting, Flatpak identity/metainfo/device permissions, URI protocol consistency, runtime configuration paths, udev migration, and repeatability.
- `actionlint`: no findings.
- Python AST and workflow YAML parsing: pass.
- Workflow patch references: no missing concrete files.
- Every workflow curl POST now uses HTTP failure detection.
- `git diff --check`: no whitespace errors; Git only reports the repository's existing LF-to-CRLF checkout warnings.
- Playwright desktop/mobile and platform switching checks passed. A focused follow-up also verified capability-only/default-on transitions, forced password submission, and old/current JSON import behavior with no page errors.
- Screenshots: `output/playwright/resume-149-desktop.png` and `output/playwright/resume-149-mobile.png`.
- `data/` and `output/` are ignored runtime directories and must not be committed.
- Authentication and task security add Django sessions/CSRF, administrator-created accounts, strict per-user task ownership, callback bearer tokens, signed expiring downloads, and POST-only logout. Public registration now requires a short-lived, hashed email code; new accounts begin without membership.
- Staff can create, list, filter, and revoke unused hashed activation codes for one generation, 3 days, 7 days, 30 days, or lifetime. Plaintext codes are available only in the creation response, and users activate them from the generator workspace.
- Django `5.2.16`: 189 tests pass locally and in the candidate release path. Coverage includes build-history scoping, registration and activation security, entitlement, artifact delivery, relay defaults/fixed-address validation, legacy relay migration, and forged POST rejection. System checks, migration-drift checks, compile checks, `actionlint`, and `git diff --check` pass.
- Relay configuration is effective through `override-settings`, not a top-level custom JSON key. Empty override forces use of the relay chosen by hbbs even over an older local fixed relay; a nonempty override forces one hbbr. Comma-separated pools are configured on hbbs and are rejected in the client field. This behavior was source-verified for every supported client version `1.3.3` through `1.4.9`.
- The exact generated `RelayPoolTest` client completed real two-device runtime validation. Sessions were observed on both A and B. With two live connections on A, relay A was stopped at 11:46:42; hbbs removed it, and both clients re-paired through B at 11:47:00, about 18 seconds later. A was restored at 11:47:09, both relays returned to the healthy pool, and the generator remained healthy with zero restarts.
- Entitlement UI screenshots passed at 1440px desktop, 900px tablet, and 390px mobile with no page-level horizontal overflow or overlap. Desktop uses the sidebar account area; narrower layouts use a navigation-under status strip with two-column mobile metrics.
- Desktop, 768px tablet, and 390px mobile layouts passed Playwright checks across Windows, Windows x86, Android, standard/custom Linux, and macOS visibility states. Imported PNG previews now use strict base64 validation plus DOM node creation; a malicious JSON import was verified not to execute while valid PNG previews still render.
- The live generator was deployed from tree `eba9444758cb4b1bc82fc5aef29c269633a4497e`. Windows x64 task success still requires exact persisted `.exe` and `.msi` receipts whose size and SHA-256 match the final files; uploads are staged and atomically committed, retries cannot replace immutable content, and terminal status callbacks cannot revive or bypass finalization.
- The generator, account, waiting, generated, and failure templates no longer load Font Awesome from Cloudflare. `local_icons.html` embeds a minimal Font Awesome 6.4.0 WOFF2 subset and three generated transparent PNG masks. All 43 glyph mappings, conditional entitlement/user/download icons, the JavaScript copy/check transition, desktop and 390x844 mobile layouts were visually verified without missing-glyph boxes, horizontal overflow, or Font Awesome CDN requests.
- macOS validation run `29975374837` succeeded on real GitHub-hosted macOS runners for both `x86_64` and `aarch64`. Each matrix job passed customization validation, RustDesk compilation, embedded configuration packaging, ad-hoc signing, bundle metadata and architecture checks, DMG creation, `hdiutil verify`, and artifact upload. The outputs are two architecture-specific DMGs, not one Universal image; validation mode skipped all production callbacks. Local copies are under `output/macos-validation-29975374837`; SHA-256 is `25151cb4d1349fa2055f98393547174c05c7f536bb391d4ba962e072333e234e` for x86_64 and `849022e5ca9a84b24cbb7ef233cbb253e0fee8e24a3d1b05b85d18207662eb67` for aarch64.

Important Linux/Flatpak boundaries:

- The native package helper rejects RPM macro characters and whitespace-invalid RPM URLs, avoids same-file `mv` failures for the exact `rustdesk` name, and keeps binary/service names separate from visible app/company metadata.
- Linux deep links use a stable `rdgen-<filename hex>` URI scheme in both Rust runtime code and the desktop handler. Service config copying and DEB purge cleanup follow `directories-next` whitespace/lowercase behavior and shell-quote cleanup paths.
- Uinput rules use `0660` plus `uaccess`; install/upgrade hooks reload and trigger udev, and legacy `chmod 0666 /dev/uinput` blocks are removed.
- Flatpak uses a case-preserving hex-derived `com.rdgen.app_<hex>` ID and keeps manifest ID, desktop rename, metainfo component/launchable, and `build-bundle` ref synchronized. `--device=dri` remains and `--device=all` is removed.
- Consequently, Flatpak must not be advertised as supporting `/dev/uinput`-based unattended Wayland input. X11 remains the expected path; a real X11/Wayland portal smoke test is still required before making a stronger runtime claim.

## Live Deployment

- URL: `https://120.55.0.199/` (`http://120.55.0.199/` redirects to HTTPS; public port 8000 is closed).
- Application source commit: `d4ec7e498a60f0996b9b10372b8ac0d1b365d10c`; application tree: `eba9444758cb4b1bc82fc5aef29c269633a4497e`.
- Deployment ID: `20260810-103245-d4ec7e498a60`.
- Source archive SHA-256: `b5b2ff4cfa00ffcac5c9668618a71e6a0541d6c781fd2c9b89ea330e7bf577bb`.
- Live image: `sha256:d2358abecb4c7bf741e4a96d90bc766c9ad70e876fa27cfc78e29bee71c147c7`.
- Live container is `rdgen-rdgen-1`, verified `running`, `healthy`, restart count `0`, with zero post-deploy traceback/critical/worker-timeout fingerprints. Online RequestFactory checks confirmed full-width rendering for build records, user management, and activation-code management, while build-record member scoping still passes. Public registration, email verification, membership activation, entitlement, platform validation, and administrator-unlimited behavior remain intact.
- Nginx terminates TLS and rate-limits `/login/`; the container binds only `127.0.0.1:8000`. The trusted Let's Encrypt IP certificate is renewed by the enabled `rdgen-certbot-renew.timer`; staging renewal passed.
- The production `admin` superuser exists. Never add its password to Git, memory files, shell history, or chat summaries.
- Persistent `.env`, `data`, `exe`, `png`, `temp_zips`, and SQLite inodes were preserved. `.env` remains mode `600`; migrations `0008_activationcode` and `0009_registrationemailcode` are applied, and SQLite `quick_check` passes with 4 users and 40 task rows after the authorized relay build.
- Production uses QQ SMTP over SSL on port 465. The live container authenticated successfully without sending a post-deploy message; the mailbox and authorization value are secrets and must never be copied into Git, memory files, commands that print them, or answers.
- Account expiry now supports permanent/time-based and successful-package-count policies. Download delivery supports creator/admin login or public token access with 1-hour, 1-day, 3-day, or 7-day expiry beginning at the first valid installer upload. Quota reservation creation and artifact settlement are atomic and guard administrative mode changes.
- `/etc/cron.d/rdgen-cleanup` runs hourly with `flock`. Initial enforcement removed 13 expired secret ZIPs and one empty directory, no installer and no reservation; the immediate post-run dry-run reported zero pending removals.
- Root-only rollback material is under `/opt/rdgen-backups/20260810-103245-d4ec7e498a60`, `/opt/rdgen-previous-20260810-103245-d4ec7e498a60`, and `rdgen-rollback:20260810-103245-d4ec7e498a60`. The backup contains online/final SQLite snapshots plus the prior environment, Nginx configuration, source, build/test logs, and image metadata. Earlier rollback sets remain present.
- The hourly cleanup converted the former cancelled legacy `in_progress` row to `timed_out`. Current database and GitHub gates report zero active client workflows.
- Deployment itself submitted no generator form. The later user-authorized `RelayPoolTest` Windows x64 build succeeded as GitHub Actions run `31350450912`; its EXE/MSI receipts, hashes, embedded configuration, real two-device relay selection, and controlled failover were independently verified.
- The pre-test host audit checked Docker, systemd, processes, packages, cron, Nginx, firewall, filesystem, and ports 21114-21119; no pre-existing RustDesk server target existed, so nothing was deleted. The later user-authorized test runs official OSS server `1.1.16` with hbbs on `120.55.0.199:22116`, relay A on `:22117`, relay B on `:23117`, and forced relay enabled. Real clients verified B/A round-robin plus automatic reconnection to B roughly eight seconds after A was stopped. A was restored; all three test units are active, both relays are healthy, and the generator remains healthy with zero restarts. The same-host topology is only a functional proof, not geographic or host-level redundancy.

## Not Yet Verified

- Public Actions history contains successful manually dispatched Windows generator runs `29318081070` at `8e33770` and `29326063260` at `cd2c358`. They were not push-triggered; their artifacts and runtime behavior have not been audited here, and the public API cannot distinguish a GitHub UI dispatch from a generator/API dispatch.
- The supported smart Windows x64/x86, Linux, and Android workflow builds now pass, and the retained Linux x86_64 DEB completed a real strict-WSS requester/target relay slice. Windows x64/x86 and Android installation/runtime behavior is still unverified; macOS is intentionally outside smart mode, although generic macOS Intel and Apple Silicon compilation is covered by run `29975374837`.
- Docker image runs, including application push run `31349924535` and subsequent documentation-only pushes, fail at `Login to Docker Hub` because repository Docker Hub credentials are unavailable. The production image was built and tested directly on the server; repair `vars.DOCKERHUB_USERNAME` and `secrets.DOCKERHUB_TOKEN` separately.
- macOS ad-hoc signing is verified on real runners. Production P12 signing with configured secrets, Apple notarization, and stapling remain unverified.
- No real Flatpak bundle installation/runtime smoke test has been run for this batch.
- Phase two is no longer design-only: S1/S2/S3 fixtures, production-path client/controller/agent/supervisor code, native packaging, generator wiring, four smart workflow builds, the Linux production-path strict-WSS slice, audited traffic correction, the green 707-test Linux suite, and two consecutive boot-safe Agent transitions are verified at the scope described above. Windows/Android runtime smoke, the supported-distribution lifecycle matrix, three-region testing, the 50-node load test, an owned endpoint with production least-privilege packaging, server push, and production deployment remain undone.

## Resume Checklist

1. Run `git status --short --branch` and `git log --oneline -n 8 --decorate`.
2. Start from generator application integration `5591f33` plus the latest local documentation commit, and server integration `6cc7478`. Preserve the server worktree's pre-existing `db_v2.sqlite3`; do not merge the superseded journal branch or unrelated publish snapshot.
3. After server edits, run the focused affected tests, the exact boot-transition and supervisor suites, the dedicated-ext4 non-root-HOME full suite, and `git diff --check`. After generator edits, rerun Django, workflow, `actionlint`, and locked patch-smoke gates.
4. Keep the authorized VM on generation 1 and revision 2. Do not re-enroll it, convert the authoritative unmetered plan merely to exercise correction, replace credentials/keys, or restore `vm-xfer/state.sqlite3`. Retain `/var/backups/rdsmart/pre-6cc7478-20260821T091315Z` and the current/rollback release directories.
5. Before any production claim, replace the collision-prone `1.1.1.1/32` lab alias with an owned endpoint and package the controller as non-root with bounded SQL logging/rotation and verified private-key ownership. The lab systemd topology is durable but does not satisfy that production gate.
6. Complete Windows x64/x86 and Android install/runtime checks, the supported-distribution install/repair/reboot/uninstall matrix, independent-host three-region testing, and the 50-node load gate.
7. Do not edit clean upstream references or push, dispatch, deploy, restart production, or expand the `120.55.0.199` relay footprint without explicit authorization. Keep build caches bounded and remove exact disposable targets/containers after each verification batch.

## Deployment Notes

The deployed host directory is `/opt/rdgen`; the Docker service is `rdgen-rdgen-1` on loopback port `8000`, behind Nginx on public ports 80/443. The host is CentOS 9 with Docker `29.6.1` and Compose `v5.2.0`; `/opt/rdgen` is a controlled source snapshot rather than a Git checkout.

For a future deployment, preserve `.env`, `exe`, `png`, `temp_zips`, and `data`. On Windows, use `git -c core.autocrlf=false archive` when byte-for-byte Git blob fidelity matters. Build and test the candidate while the old container remains live; before a schema-changing cutover, stop or block public writes, take and verify a final SQLite snapshot, recheck GitHub activity from the isolated snapshot, then switch and keep signal-aware rollback responsibility until health checks pass. Do not perform a blind destructive sync or remove current rollback material before the next deployment is verified.

Historical work, previous real Windows signing and Android universal APK verification, and RustDesk server network investigation remain documented in `WORKLOG.md`.
