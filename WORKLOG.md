# Worklog

## 2026-05-08

### Repository Setup

- Started in `D:\rustdesk-生成器`.
- Directory was initially empty and not a Git repository.
- Initial clone failed because global Git proxy pointed to `http://127.0.0.1:7892`, which was unavailable.
- Cloned upstream successfully with temporary proxy overrides:
  `git -c http.proxy= -c https.proxy= clone --depth 1 https://github.com/bryangerlach/rdgen.git rdgen`
- Local repository path:
  `D:\rustdesk-生成器\rdgen`
- Checked latest local commit:
  `0537a2c Applied missing branding and icon customization to .deb and AppImage builds (#248)`
- Repository status after clone was clean.

### Upstream / Live Generator Review

- Reviewed `https://github.com/bryangerlach/rdgen`.
- Reviewed the author's live generator at:
  `https://rdgen.crayoneater.org/`
- Did not submit the live generator form.
- Chrome DevTools MCP connection failed to attach to local Chrome.
- Used Playwright fallback with a temporary install in `%TEMP%\rdgen-pw-inspect`.
- Captured live-page screenshots into `output/playwright/`.

### Live Page Findings

- Main live form sections:
  - Select Platform
  - General
  - Custom Server
  - Security
  - Visual
  - Permissions
  - Code Changes
  - Other
- Supported platforms visible in the UI:
  - Windows 64Bit
  - Windows 32Bit
  - Linux
  - Android
  - macOS
- Platform switching was tested for all five platform options.
- No major field visibility changes were observed between platforms.
- The Android App ID field remains visible for all platforms.

### Local Code Review Notes

- Read `rdgenerator/templates/generator.html`.
- Read `rdgenerator/forms.py`.
- Read `rdgenerator/views.py`.
- Noted that the generator UI is mostly inline CSS/JS in `generator.html`.
- Noted a likely JavaScript bug in permission preset handling:
  `enableTerminal.disable = true` should likely be `enableTerminal.disabled = true`.
- Noted that manual settings parsing in `views.py` assumes every non-empty line contains `=`.
- Noted that download and image endpoints build paths from request query parameters and should be reviewed before public deployment.

### Memory Files

- Created `AGENTS.md`.
- Created `PROJECT_OVERVIEW.md`.
- Created `ROADMAP.md`.
- Created `WORKLOG.md`.

### Prior Project Review

- User provided previous customized project path:
  `D:\rustdesk_web客户端\rdgen-repo`
- Confirmed it is a Git repository.
- Remote:
  `https://github.com/zhenzhen122/rdgen.git`
- Current branch:
  `master`
- Latest commit:
  `8bd0b4b fix: add rendezvous_mediator.rs to x86 workflow copy list`
- Working tree had one local modification:
  `.github/workflows/sh-generator-windows.yml`
- Performed read-only comparisons against the clean upstream clone at:
  `D:\rustdesk-生成器\rdgen`

Observed reusable improvements from the prior project:

- UTF-8 handling in `.github/actions/decrypt-secrets/action.yml`.
- Windows workflow environment adds `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`.
- Windows MSI codepage patch changes `1252` to `65001`.
- Workflow upload timeout increased for generated artifacts.
- Windows EXE and MSI uploads split so optional MSI failure does not hide the EXE.
- Generated page can hide download links until files exist.
- Workflow status callbacks report progress and failure/cancel states.
- `hidecm` causes approve mode to be forced to `password`.

Observed personal/non-generic changes:

- Workflows check out `zhenzhen122/rustdesk` as `custom-overlay`.
- Workflows copy custom modules from that overlay into RustDesk source.
- This overlay appears tied to account/auth/device-login/client-specific behavior and should not be copied directly into the generic generator.

User constraint recorded:

- The old project at `D:\rustdesk_web客户端\rdgen-repo` is read-only reference material.
- Do not write, edit, format, move, delete, clean, or generate files inside that old project.

### Hide Connection Window Investigation

- Focused on the UI option:
  `Allow hiding the connection window from remote screen.`
- Compared current clean upstream project with old read-only project.
- The local `.github/patches/hidecm.diff` file is identical between both projects.
- Current clean upstream applies `hidecm.diff` in Android, Linux, and macOS workflows.
- Current clean upstream does not apply `hidecm.diff` in:
  - `.github/workflows/generator-windows.yml`
  - `.github/workflows/generator-windows-x86.yml`
  - `.github/workflows/sh-generator-windows.yml`
- Old project adds `hide-cm` workflow steps to those Windows workflows.
- Old project also changes `rdgenerator/views.py` so when `hidecm` is selected, `approve-mode` is forced to `password`.
- Conclusion: the generic fix should port only the backend `effectiveApproveMode` behavior and Windows workflow patch application steps. Do not port personal overlay logic.

### Hide Connection Window Fix Applied

- Updated current project `rdgenerator/views.py`:
  - Added `effectiveApproveMode = 'password' if hidecm else passApproveMode`.
  - Used `effectiveApproveMode` for both default and override `approve-mode`.
- Updated current project Windows workflows to apply `.github/patches/hidecm.diff` before build:
  - `.github/workflows/generator-windows.yml`
  - `.github/workflows/generator-windows-x86.yml`
  - `.github/workflows/sh-generator-windows.yml`
- Verification:
  - `python -m py_compile rdgenerator\views.py` passed.
  - `npx --yes js-yaml` parsed all three modified workflow YAML files successfully.

### GitHub Deployment Preparation

- Checked `setup.md` for the author's recommended deployment flow.
- Confirmed `gh` CLI is not installed on this machine.
- Renamed local remote:
  - `origin` -> `upstream`
  - `upstream` points to `https://github.com/bryangerlach/rdgen.git`
- Left `origin` unset until the user's own GitHub fork/repository URL is available.
- Updated `docker-compose.yml` to use `build: .` instead of the author's published image, because this deployment must include the local `hidecm` fix.
- Added `output/` to `.gitignore` so Playwright screenshots are not pushed.
- Created local commit:
  `8a7c216 fix hide connection window builds`
- Server/GitHub secrets still require user-specific values:
  - GitHub fork/repository URL
  - GitHub username
  - Fine-grained GitHub token for the fork
  - Public server URL for `GENURL`
  - Matching `ZIP_PASSWORD` in GitHub Actions secret and server environment

### GitHub Fork Setup

- Created and prepared the user's GitHub fork:
  `https://github.com/zhenzhenwq/rdgen`
- Added `origin` remote pointing to the fork and kept the author's repository as `upstream`.
- Pushed the local fixed branch to `origin/master`.
- Enabled GitHub Actions on the fork through the GitHub web UI.
- Added repository Actions secret `ZIP_PASSWORD` through the GitHub web UI.
- Created fine-grained personal access token `rdgen-build-dispatch` through the GitHub web UI:
  - Resource owner: `zhenzhenwq`
  - Repository access: only `zhenzhenwq/rdgen`
  - Expiration: no expiration
  - Repository permissions:
    - `Actions`: read and write
    - `Workflows`: read and write
    - `Metadata`: read-only, required by GitHub
- The token value was copied in the browser and must be stored by the user for the server `GHBEARER` environment variable. Do not commit or log the token value.
- Still pending:
  - Public server URL/domain for GitHub Actions secret `GENURL`
  - Server deployment environment values

### Server Deployment Preparation

- Received deployment server details:
  - Host: `120.55.0.199`
  - SSH user: `root`
  - SSH port: `22`
- Verified SSH port 22 is reachable.
- Verified the server OS and runtime state:
  - OS: CentOS Linux 8
  - Docker is installed.
  - Docker Compose v2 is installed.
  - `git` is not installed.
  - Port 80 is already used by nginx.
  - Port 8000 was not occupied during the initial check.
- Added GitHub Actions secret `GENURL` with the initial direct-IP URL:
  `http://120.55.0.199:8000`
- Updated `docker-compose.yml` to read deployment settings from `.env` instead of storing placeholder values directly in the compose file.
- Added `.env.example` for non-secret deployment configuration reference.
- Updated `.dockerignore` so `.env` and runtime artifact directories are not copied into the Docker image.
- Added Docker build args `PIP_INDEX_URL` and `PIP_TRUSTED_HOST` so deployments with restricted or unstable PyPI access can use a local/regional package mirror without hardcoding it.
- Planned deployment path:
  `/opt/rdgen`
- Planned public test URL:
  `http://120.55.0.199:8000`

### Server Deployment Completed

- Deployed current fork code to:
  `/opt/rdgen`
- Wrote server-local `.env` with deployment secrets and runtime settings. The `.env` file is not committed and is excluded from the Docker build context.
- Because the server does not have `git`, deployment used the GitHub branch archive download:
  `https://github.com/zhenzhenwq/rdgen/archive/refs/heads/master.tar.gz`
- Server-local `.env` uses an Aliyun PyPI mirror for Docker builds because the default PyPI index failed from inside the server build container.
- Built and started the service with:
  `docker compose up -d --build`
- Docker container status after deployment:
  `healthy`
- Public URL verified with HTTP 200:
  `http://120.55.0.199:8000/`
- Browser check confirmed the deployed page loads and contains:
  `Allow hiding the connection window from remote screen.`

### 500 During Generation Investigation

- User reported a 500 error when testing with:
  `C:\Users\32590\Downloads\Desk (1).json`
- Read the JSON locally and confirmed the configuration loads as a dictionary and has required form-like fields such as `platform`, `version`, `exename`, `passApproveMode`, and `hidecm`.
- The config enables `hidecm`, so it exercises the fixed hide-connection-window path.
- Identified a backend bug in `rdgenerator/views.py`:
  - GitHub workflow dispatch normally succeeds with HTTP `204 No Content`.
  - The current code treated `204` as success but still called `response.json()`.
  - Parsing an empty `204` response raises an exception and returns a 500 even when GitHub accepted the dispatch.
- Applied a compatibility fix:
  - Only parse JSON when the response body is non-empty.
  - Save the `GithubRun` record and render the waiting page on `204` success.
  - Fall back to the repository Actions page when no workflow run URL is available.
  - Avoid polling a `/runs/None` GitHub API URL when the dispatch response does not include a run id.
- Reproduced another 500 root cause inside the deployed container:
  - Host bind-mounted directories `exe/`, `png/`, and `temp_zips/` were created as root-owned.
  - The container application runs as Unix user `user` (`uid=1000`) and could not write `temp_zips/secrets_*.zip`.
  - Fixed the live server by changing those host directory owners to uid/gid `1000:1000`.
  - Added `entrypoint.sh` so future container starts create and chown runtime artifact directories before dropping to the app user.
- Reproduced the browser-only 500 with the imported config after the directory ownership fix:
  - The imported form data was accepted by the frontend and included `platform=windows`, `hidecm=on`, and the imported base64 images.
  - The backend still returned Django's generic 500 page before it printed a GitHub dispatch response.
  - Confirmed `GithubRun` DB writes work and the container can reach `https://api.github.com`.
  - Confirmed the app user cannot write files in `/opt/rdgen` but can write inside `temp_zips/`.
  - Root cause: `generator_view` wrote `data_*.json` to the project root before zipping secrets. After the Docker entrypoint began running Gunicorn as the unprivileged app user, that root-level temporary file write raised `PermissionError`.
- Fixed the browser-only 500 path:
  - Moved the temporary `data_*.json` file into `temp_zips/`, the same runtime directory already created and chowned for app writes.
  - Used UTF-8 when writing the temporary JSON because imported configs may contain non-ASCII company names.
  - Marked `GithubRun` as `success` when GitHub Actions uploads a finished client to `/save_custom_client`.
  - Normalized status comparisons in `/check_for_file` so both workflow conclusions and upload callbacks can advance the waiting page.
- During redeploy from the GitHub branch archive, Docker failed to execute `/opt/rdgen/entrypoint.sh` because tarball checkout did not preserve the executable bit.
- Added `chmod +x /opt/rdgen/entrypoint.sh` inside the Docker build so archive-based deployments start reliably.
- After that fix, the imported config successfully reached GitHub dispatch and GitHub returned a workflow run id, but the view still returned:
  `Connection error: attempt to write a readonly database`
- Root cause:
  - Docker image build created `db.sqlite3` as root.
  - Runtime Gunicorn now runs as the unprivileged `user`, so it could not insert the generated `GithubRun` record.
- Fixed database persistence and permissions:
  - Moved SQLite to `/opt/rdgen/data/db.sqlite3` by default through `SQLITE_PATH`.
  - Added a `./data:/opt/rdgen/data` Compose mount.
  - Updated `entrypoint.sh` to create/chown `data`, run migrations as the app user, then start Gunicorn.
  - Removed build-time migration so the runtime database owns its files correctly.
- Verified the browser flow with `C:\Users\32590\Downloads\Desk (1).json` after the database fix:
  - `/generator` returned HTTP 200.
  - The page navigated to `/check_for_file`.
  - A `GithubRun` record was saved with the returned GitHub run id.
- The triggered Windows workflow then failed in `.github/actions/decrypt-secrets` during `Load Secrets`.
- Root cause:
  - The imported config contains a non-ASCII company name.
  - On Windows runners, the Python action used the platform default output/file encoding and raised `UnicodeEncodeError` while masking/writing secrets.
- Fixed the decrypt action to use UTF-8 stdout/stderr and UTF-8 `GITHUB_ENV` writes, and to stringify values before masking/exporting.
- Re-ran the imported JSON flow after the UTF-8 fix:
  - GitHub Actions run `25533835760` completed successfully.
  - The server received `Desk.exe`.
  - The waiting page moved to the generated-download page.
- Found another upstream usability bug after successful generation:
  - `generated.html` always showed platform-specific hardcoded download links, including `Desk.msi`, even when only `Desk.exe` was uploaded.
  - Clicking a missing artifact would raise a backend 500.
- Fixed generated/failure pages to list only files actually present under the run's output directory, and changed `/download` to return 404 for missing generated files.

### Generator UI Chinese / Blue-White Theme

- User requested `$frontend-design` changes for a blue-white generator page with Chinese display.
- Updated `rdgenerator/templates/generator.html`:
  - Reworked the main generator page from the original dark theme to a blue-white theme.
  - Translated visible form section names, labels, buttons, help text, and client-side save/load errors into Chinese.
  - Removed the bottom GitHub source-code and sponsor links so they are no longer displayed or clickable.
- Updated `rdgenerator/forms.py`:
  - Translated form choice labels and validation messages into Chinese while keeping submitted values unchanged.
- Updated flow templates for a consistent Chinese display:
  - `rdgenerator/templates/waiting.html`
  - `rdgenerator/templates/generated.html`
  - `rdgenerator/templates/failure.html`
  - `rdgenerator/templates/maintenance.html`
- Verification:
  - `python -m py_compile rdgenerator\forms.py rdgenerator\views.py` passed.
  - `git diff --check` passed.
- Follow-up frontend fix:
  - Avoid saving empty file-input objects into exported JSON.
  - Only render imported image previews when the imported value is a PNG data URL, preventing `/[object Object]` preview requests.
- Deployment verification:
  - Deployed commit `c6717f35d769bd58a3e9460e6ae2feb58ae4f837` to `/opt/rdgen`.
  - Docker container reported `healthy`.
  - Public homepage returned HTTP 200 at `http://120.55.0.199:8000/`.
  - Browser import test with `C:\Users\32590\Downloads\Desk (1).json` populated the form without triggering a new build.
  - Confirmed source-code and sponsor links are absent from the generator page.
  - Saved browser screenshot to `output/playwright/rdgen-blue-chinese-home.png`.

### Hide Desktop Three-Dot Settings Menu

- User requested hiding the RustDesk desktop client main-page three-dot menu shown beside the local ID.
- Analyzed RustDesk client source directly, without reading the old project:
  - The visible three-dot button is in `flutter/lib/desktop/pages/desktop_home_page.dart`.
  - It is rendered from `buildPopupMenu(context)` in the ID row and opens settings via `DesktopTabPage.onAddSetting`.
- Added generator option:
  - `hideSettingsMenu` / `隐藏主界面右上角三点菜单`.
- Added `.github/patches/hide_settings_menu.diff`:
  - Replaces the desktop home-page `buildPopupMenu(context)` call with a fixed-size empty `SizedBox`.
  - This hides the three-dot widget and removes its click target while preserving row spacing.
- Wired the option through `rdgenerator/views.py` into the encrypted Actions payload.
- Added workflow patch steps for:
  - Windows x64
  - Windows x86
  - Self-hosted Windows
  - Linux
  - Android
  - macOS
- Compatibility check:
  - `git apply --check` passed against RustDesk tags `1.3.3` through `1.4.6` and current `master`.

### Bridge Workflow Pub Cache Failure

- Investigated failed generation URL:
  - `/check_for_file?filename=Jssvag&uuid=074406d3-2a5e-420b-a779-004c905be33f&platform=windows`
  - GitHub Actions run: `25543182149`
- Result:
  - The waiting page correctly moved to the failure page.
  - No generated files existed under `exe/074406d3-2a5e-420b-a779-004c905be33f`.
- Root cause:
  - The workflow failed before Windows compilation.
  - `generate-bridge / Install flutter rust bridge deps` failed during `flutter pub get`.
  - Dart pub crashed with `Null check operator used on a null value` inside `HostedSource._getAdvisories.readAdvisoriesFromCache`.
  - This appears tied to restored pub advisory cache data, not the RustDesk three-dot menu patch.
- Fix:
  - Disabled Flutter pub-cache restore in `.github/workflows/bridge.yml`.
  - Removed `${PUB_CACHE}/hosted/pub.dev/.cache` before bridge `flutter pub get`.
  - Kept cargo/tool caches intact.

### Jssvag Clean Local Config Retest

- Backed up and removed local client state:
  - `C:\Users\32590\AppData\Roaming\Jssvag`
  - `C:\Users\32590\AppData\Local\Jssvag`
  - Backup directory: `D:\rustdesk-生成器\backups\Jssvag-20260508-173215`
- Started `C:\Users\32590\Downloads\Jssvag (7).exe`; it launched from `%LOCALAPPDATA%\Jssvag`.
- Fresh client config no longer contained the old `vwag.cc` rendezvous server.
- Fresh client log showed:
  - generated new ID `6568890`
  - `start rendezvous mediator of desk.jssvag.com`
  - UDP/NAT responses from `desk.jssvag.com:21116` and `desk.jssvag.com:21115`
  - `sysinfo updated`
  - repeated `register_pk of desk due to key not confirmed`
- DNS confirmed `desk.jssvag.com -> 45.207.213.2`.
- Pulled read-only database snapshots from the RustDesk server to `D:\rustdesk-生成器\server-snapshots\rustdesk-20260508-173643`.
- The RustDesk API database recorded the fresh Windows 11 client:
  - peer ID `6568890`
  - hostname `desktop-s1vq4l4`
  - version `1.4.6`
  - last IP `220.166.163.248`
  - created `2026-05-08 17:33:59 +08:00`
  - updated `2026-05-08 17:36:20 +08:00`
- Server observation:
  - formal container `rustdesk-rustdesk-1` still had `MUST_LOGIN=Y` in the running environment.
  - test container `rustdesk-test` had `MUST_LOGIN=N` and separate `22114-22119` ports.

### RustDesk Server OSS Native Retest

- User reported Jssvag UI still shows `Not ready. Please check your connection`.
- Installed official RustDesk Server OSS `.deb` packages on `45.207.213.2`:
  - `rustdesk-server-hbbs_1.1.15_amd64.deb`
  - `rustdesk-server-hbbr_1.1.15_amd64.deb`
- Backed up previous Docker data to `/root/rd-official-install/backup-before-official-20260508-094704`.
- Stopped Docker RustDesk containers and disabled their restart policy:
  - `rustdesk-rustdesk-1`
  - `rustdesk-test`
- Started official native systemd services:
  - `rustdesk-hbbs.service`
  - `rustdesk-hbbr.service`
- Reused the original server key pair from `/data/rustdesk/server` in `/var/lib/rustdesk-server`.
- Added systemd overrides:
  - `hbbs`: `/usr/bin/hbbs -r 45.207.213.2:21117 -k dH0WO9xf8kmRM1IjDhprjn+MhuXnIEvhnTWQR21agIY=`
  - `hbbr`: `/usr/bin/hbbr -k dH0WO9xf8kmRM1IjDhprjn+MhuXnIEvhnTWQR21agIY=`
- Verified listeners are native `hbbs/hbbr` on `21115-21119`; Docker no longer owns those ports.
- Read the user's reference script `C:\Users\32590\Desktop\阿里云服务器信息写入.bat`; it uses `xdesk.exe --config "host=...,key=..."`.
- Confirmed RustDesk 1.4.6 source only applies `--config` when the client is installed and running with admin/root privileges, so it does not update the portable Jssvag runtime.
- Directly wrote Jssvag local config in `Jssvag2.toml`:
  - `custom-rendezvous-server = '45.207.213.2'`
  - `relay-server = '45.207.213.2:21117'`
  - `key = 'dH0WO9xf8kmRM1IjDhprjn+MhuXnIEvhnTWQR21agIY='`
- Found local DNS/proxy issue:
  - `desk.jssvag.com` resolved locally to `198.18.0.75`, not `45.207.213.2`.
  - MaoMaoCloud TUN was a default route and HTTP proxy was enabled at `127.0.0.1:7892`.
- Added a host route for `45.207.213.2/32` via `WLAN` gateway `192.168.31.1`; `Test-NetConnection` then used source `192.168.31.25`.
- After bypassing TUN and using direct IP, Jssvag log showed stable NAT responses from `45.207.213.2:21116` and `45.207.213.2:21115`, but still repeated:
  - `register_pk of 45.207.213.2:21116 due to key not confirmed`
- Forced TCP by setting `disable-udp = 'Y'`; client connected but timed out waiting for rendezvous handshake:
  - `rendezvous mediator error: deadline has elapsed`
- Server `/var/lib/rustdesk-server/db_v2.sqlite3` `peer` table remained empty.
- Current conclusion:
  - Official native server is installed and owns ports correctly.
  - Local fake-IP/proxy was a real problem and was bypassed for `45.207.213.2`.
  - The current pre-existing `Jssvag (7).exe` still does not complete key confirmation with the native server; likely needs a newly generated client that embeds server fields using the generator fix committed later (`fa50cd9`).

### RustDesk Official Client Same Failure

- User confirmed the official RustDesk client shows the same connection problem as Jssvag.
- Temporarily configured the official client to use the RustDesk server:
  - `custom-rendezvous-server = '45.207.213.2'`
  - `relay-server = '45.207.213.2:21117'`
  - `key = 'dH0WO9xf8kmRM1IjDhprjn+MhuXnIEvhnTWQR21agIY='`
- Official client log repeated:
  - `register_pk of 45.207.213.2:21116 due to key not confirmed`
  - TCP NAT test responses from `45.207.213.2:21116` and `45.207.213.2:21115`
- Verified the native official server is active and listening:
  - `hbbs`: TCP `21115`, TCP/UDP `21116`, TCP `21118`
  - `hbbr`: TCP `21117`, TCP `21119`
  - Linux firewall/UFW is not blocking input.
- Synthetic UDP tests:
  - From the local PC, explicitly bound to WLAN `192.168.31.25`, UDP packets to `45.207.213.2:21116` did not appear on `45.207.213.2` `ens17`.
  - From the separate server `120.55.0.199`, UDP packets to `45.207.213.2:21116` also did not appear on `45.207.213.2` `ens17`.
  - From `45.207.213.2` to `120.55.0.199`, UDP packets were captured successfully on `120.55.0.199`.
  - From the local PC to `120.55.0.199:21116`, UDP packets were captured successfully.
- Conclusion:
  - The shared failure is not caused by the generator or by the official Windows client configuration.
  - `45.207.213.2` is not receiving inbound public UDP traffic on `21116`; this happens before packets reach the server OS.
  - The likely fix is in the cloud/provider firewall or security group for `45.207.213.2`: allow inbound `21116/UDP` at minimum, and keep the RustDesk TCP ports open.

### Multi-Method UDP Recheck

- Re-ran several independent checks after the user requested more test methods.
- Method 1: `tcpdump` on `45.207.213.2` `ens17` with local PC and `120.55.0.199` sending synthetic UDP to `45.207.213.2:21116`.
  - Result: `0` matching UDP packets captured.
- Method 2: same server capture with TCP and UDP to the same destination port.
  - Local TCP connection to `45.207.213.2:21116` was captured immediately.
  - Local UDP packet to `45.207.213.2:21116` was not captured.
- Method 3: `120.55.0.199` sent UDP to multiple destination ports on `45.207.213.2`: `53`, `443`, `21115`, `21116`, `21117`, `21118`, `21119`, `40000`.
  - Result: no inbound UDP packets to `45.207.213.2` were captured.
- Method 4: reverse sanity check from `45.207.213.2` to `120.55.0.199:41116`.
  - Result: UDP packets were captured successfully on `120.55.0.199`, proving the testing method works and UDP outbound from `45.207.213.2` works.
- Method 5: server network/firewall counters.
  - `hbbs` listens on `*:21116/UDP`.
  - `INPUT` policy is `ACCEPT`; no host firewall rule explains the drop.
  - After synthetic test bursts, host-level packet counters did not reflect the missing inbound UDP test packets.
- Method 6: real official RustDesk client restart while capturing `21115-21119`.
  - Server captured only TCP NAT-test traffic on `21115/21116`.
  - No UDP packets were captured.
  - Official client log still showed `start udp: 45.207.213.2:21116` and repeated `register_pk ... due to key not confirmed`.
- Updated conclusion:
  - External inbound UDP to `45.207.213.2` is blocked before the packet reaches the server OS.
  - This appears broader than only `21116/UDP`; tested external UDP to several destination ports did not reach `45.207.213.2`.
  - Fix remains provider-side security group/firewall/upstream UDP policy, not generator code.

### Windows Self-Signed Code Signing

- User chose the self-signed certificate path for generated Windows clients.
- Generated a local self-signed code signing certificate:
  - PFX: `D:\rustdesk-生成器\codesign\rdgen-selfsigned-codesign.pfx`
  - Public CER: `D:\rustdesk-生成器\codesign\rdgen-selfsigned-codesign.cer`
  - PFX base64 and password helper files are in the same `codesign` directory.
  - Certificate thumbprint: `198E54637FF5B21D964BDB7A06E964B79BAD0FFA`
- Added GitHub Actions repository secrets through the GitHub API:
  - `CODE_SIGN_PFX_BASE64`
  - `CODE_SIGN_PFX_PASSWORD`
- Updated Windows workflows to support local Authenticode signing with `signtool.exe`:
  - `.github/workflows/generator-windows.yml`
  - `.github/workflows/generator-windows-x86.yml`
  - `.github/workflows/sh-generator-windows.yml`
- Signing behavior:
  - If `CODE_SIGN_PFX_BASE64` and `CODE_SIGN_PFX_PASSWORD` are configured, workflows decode the PFX and sign generated `.exe`, `.dll`, and `.msi` files.
  - Timestamp signing is attempted first with `http://timestamp.digicert.com`; if timestamping fails, the workflow retries signing without timestamping.
  - If no self-signing secrets exist, the existing external signing service path using `SIGN_BASE_URL` / `SIGN_API_KEY` remains supported.
  - If neither signing method is configured, the workflow keeps the old skip behavior and continues with unsigned files.
- Validation:
  - Parsed the modified workflow YAML files successfully with PyYAML.
  - Secrets were accepted by GitHub API during creation.
- Caveat:
  - Self-signed signatures prove file integrity after signing, but Windows will not trust the publisher on other machines until the public `.cer` certificate is installed into trusted certificate stores.

### SignTest Build Verification

- Triggered a real Windows x64 generator build through the deployed generator at `120.55.0.199:8000`.
- Test input:
  - filename/app name: `SignTest`
  - UUID: `82f5ea38-c4ab-461e-a090-4e03f5d014bd`
  - RustDesk version: `1.4.6`
- GitHub Actions run:
  - `26007760512`
  - `Build Windows` completed successfully.
  - `sign dlls` completed successfully.
  - `sign exe and msi` completed successfully.
- Downloaded generated files from the generator server:
  - `D:\rustdesk-生成器\sign-test-output\SignTest.exe`
  - `D:\rustdesk-生成器\sign-test-output\SignTest.msi`
- Authenticode verification:
  - Both files have a signature.
  - Signer subject: `CN=RDGen Self-Signed Code Signing`
  - Thumbprint: `198E54637FF5B21D964BDB7A06E964B79BAD0FFA`
  - PowerShell status: `UnknownError` with message that the chain terminates in an untrusted root, which is expected until `rdgen-selfsigned-codesign.cer` is installed as trusted.

### Android Universal APK Output

- User reported Android generation only showed inconsistent split APK variants and asked for both:
  - one all-in-one APK
  - three separate ABI APKs
- Checked generated files for UUID `dcaa5218-3b21-4883-a4e9-d28a96c467eb`.
- Current deployed output contained only split APKs:
  - `WuYouDesk-aarch64.apk`
  - `WuYouDesk-armv7.apk`
  - `WuYouDesk-x86_64.apk`
- Root cause:
  - `.github/workflows/generator-android.yml` builds a three-entry ABI matrix and uploads each split APK separately.
  - No workflow step produced or uploaded a universal APK.
- Implemented workflow change:
  - Each ABI matrix job uploads its split APK as an Actions artifact.
  - The `deploy` job downloads the three split APK artifacts after the matrix completes.
  - The `deploy` job creates `${filename}-universal.apk` by combining the native `lib/` folders from `aarch64`, `armv7`, and `x86_64` split APKs.
  - The universal APK is zipaligned, signed with the configured Android release key if present, otherwise with a generated debug key, and verified with `apksigner`.
  - The universal APK is uploaded back to the generator server/API server beside the split APKs.
- Expected Android output after the change:
  - `${filename}-universal.apk`
  - `${filename}-aarch64.apk`
  - `${filename}-armv7.apk`
  - `${filename}-x86_64.apk`
- Also updated `list_generated_files()` ordering so Android universal output appears before split APKs.
- Pushed commit `65b491a add android universal apk output` to GitHub.
- Triggered and monitored a test Android build:
  - Filename: `WuYouDesk`
  - UUID: `9de4743a-ec38-4266-b155-cd383ae64685`
  - Result on generator server:
    - `WuYouDesk-universal.apk`
    - `WuYouDesk-aarch64.apk`
    - `WuYouDesk-armv7.apk`
    - `WuYouDesk-x86_64.apk`
- Verified the old reported UUID `dcaa5218-3b21-4883-a4e9-d28a96c467eb` still only has the three split APKs because it was generated before the workflow change.

### New Window Handoff Preparation

- User planned to switch to a new conversation/window and requested durable project memory.
- Updated:
  - `AGENTS.md`
  - `PROJECT_OVERVIEW.md`
  - `ROADMAP.md`
  - `WORKLOG.md`
- Added a dedicated handoff file:
  - `NEW_WINDOW_HANDOFF.md`
- Important handoff constraints:
  - Do not write to the old project `D:\rustdesk_web客户端\rdgen-repo`.
  - Do not store plaintext server passwords, GitHub tokens, or signing passwords in repo files.
  - Continue from `D:\rustdesk-生成器\rdgen`.
  - Verify GitHub remote state before assuming local `origin/master` is current.

### Feature Document Gap Pass

- Read the detailed feature document from `C:/Users/32590/Desktop/01-代码修改文档.md` and compared it against the current generator.
- Added generator options for previously missing desktop runtime behaviors:
  - ID-side copy button that copies ID plus temporary password.
  - Manual temporary password dialog and no automatic temporary-password refresh after a connection.
  - Windows start-on-boot checkbox under the temporary-password area.
  - Hide Network entry in desktop settings.
  - Incoming-only compact layout with configurable content width and height.
- Added/extended source patch scripts under `.github/patches/`:
  - `runtime_features.py`
  - `hide_network_setting.py`
  - `incoming_compact.py`
  - `force_disable_file_transfer.py`
  - `silent_install.py`
- Updated workflows so the new optional patches are applied to the appropriate build paths:
  - Windows x64 and self-hosted Windows
  - Windows x86 where applicable
  - Linux
  - macOS
  - Android for force-disabling file transfer
- UI behavior verified locally:
  - Windows x64 shows desktop runtime options and incoming compact width/height when direction is incoming.
  - Windows x86 hides Flutter-only options but keeps Windows silent install.
  - Android hides the desktop behavior section.
- Validation completed locally:
  - Python compile checks for generator and patch scripts.
  - `git diff --check` passed with only line-ending warnings.
  - Workflow YAML parsed successfully.
  - Django `manage.py check` passed in a temporary venv.
  - Browser/Chrome DevTools MCP smoke test passed on the local generator page.
- Caveat: real GitHub Actions builds still need to verify that every exact-source patch applies cleanly to the selected RustDesk source version.

### RustDesk Linux Default Fix Wiring

- User asked to regenerate the previously prepared RustDesk fixes through the generator instead of treating `rustdesk-src` as the main delivery path.
- Confirmed the Linux generator workflow did not yet apply the packaged default RustDesk fix diff as a dedicated step.
- Added a workflow step in `.github/workflows/generator-linux.yml` to download and apply `.github/patches/rustdesk_default_linux.diff` before dependency setup and build.
- This keeps the generator as the packaging layer while still carrying the earlier RustDesk capture/input/CM fixes into generated Linux builds.

## 2026-07-13

### RustDesk 1.4.9 Generator Adaptation

- Updated the form and all platform generator workflow defaults to RustDesk `1.4.9`.
- Ported the optional source customization scripts across RustDesk `1.4.7`, `1.4.8`, and `1.4.9`, keeping each selected patch strict instead of silently continuing after a mismatch.
- Added dedicated patch helpers for Android custom config, Linux base fixes and package formats, connection-delay handling, settings-menu hiding, customization validation, and repeatable patch-chain smoke testing.
- Added server-side version and platform capability validation, safer manual-setting parsing, build-script input validation, portable filename constraints, and Windows reserved-name rejection.
- Updated the generator UI to hide and disable unsupported controls when the selected version or platform changes. Added an explicit `[hidden]` rule so layout CSS cannot override hidden state.
- Verified the desktop and mobile form layouts with Playwright. Screenshots are kept under ignored `output/playwright/` runtime storage.

### Linux Packaging And Workflow Reliability

- Applied the RustDesk `1.4.9` Linux capture/input/connection-manager fixes through a dedicated version-aware helper.
- Kept `.deb`, RPM, SUSE RPM, Arch, AppImage, and Flatpak customization consistent for the Beijing Linux option.
- Stopped aarch64 and `master` jobs from attempting to upload an Arch package that is not produced.
- Made AppImage output discovery use the actual generated versioned filename, including nightly builds.
- Pinned `setuptools_scm<10`, aligned Flatpak x86 with Ubuntu 22.04, and customized `pacman_install` so Arch post-install actions use the renamed service.
- Separated machine names from visible application/company/homepage metadata across native packages, AppImage, and Flatpak; collision names such as `RustDesk` no longer trigger a second replacement.
- Replaced world-writable `/dev/uinput` permissions with `0660` plus `uaccess`, and removed the sudoers rules that allowed caller-controlled `LD_*` variables in privileged processes.
- Made generator/API uploads fail on HTTP errors and use bounded connection, transfer, and retry windows.

### macOS, Windows, Android, And Shared Workflows

- Pinned NASM `2.16.03` ahead of Homebrew paths for both macOS runner architectures.
- Packaged `custom_.txt` into the macOS app resources and Flutter assets before signing.
- Changed P12 signing to sign the complete `.app` bundle once with `rcodesign`, clean the temporary certificate through a trap, and verify the result with deep strict `codesign` verification. The no-P12 path performs an ad-hoc deep re-sign.
- Kept Android universal plus split APK output and made Android, Windows, macOS, Linux, and external Windows signing POST requests fail on HTTP errors.
- Updated shared workflow actions, cache keys, and reusable-workflow input definitions; removed the unused undefined upload-tag input.

### Verification And Release Boundary

- Ran every Windows, Windows x86, Linux, macOS, and Android optional patch chain twice against RustDesk `1.4.7`, `1.4.8`, and `1.4.9` source trees.
- Ran Linux AppImage, Flatpak, RPM, SUSE, and Arch customization helpers twice to verify repeatability.
- Django suite passes with 29 tests and no system-check findings.
- Twenty focused Linux packaging regression tests pass, including real-layout edge cases and repeatability coverage.
- `actionlint`, Python AST parsing, workflow YAML parsing, workflow patch-reference checks, and `git diff --check` pass.
- Runtime `data/` and `output/` content remains ignored and outside the release diff.
- No real GitHub Actions compilation for this `1.4.9` batch has been run yet.
- The deployed generator at `120.55.0.199:8000` has not been updated with this batch, and no live generator form was submitted.

## 2026-07-14

### Release Preflight Hardening

- Independently re-audited the Linux native/AppImage/Flatpak paths and the complete release diff before staging.
- Fixed same-file `mv` failures when the exact machine name is `rustdesk` in both native DEB layout and AppImage preparation.
- Added the missing Python runtime to the Flatpak build container and made the native packaging helper compatible with the Ubuntu 18.04 container's Python 3.6.
- Restricted Beijing Linux customization to the verified RustDesk `1.4.7`, `1.4.8`, and `1.4.9` versions in both Django and the dynamic UI.
- Rejected RPM macro expansion and whitespace-invalid RPM homepage values at both form and helper boundaries.
- Added a stable, legal, case-preserving `rdgen-<filename hex>` Linux URI scheme and synchronized the Rust runtime with desktop MIME registration.
- Matched Linux service configuration copying and DEB purge cleanup to `directories-next` project-directory normalization, including segmented Unicode lowercase behavior and shell-quoted cleanup targets.
- Made Flatpak application IDs case-preserving and collision-resistant, synchronized manifest/metainfo/bundle references, validated absolute homepage URLs, and added real removal coverage for duplicate `--device=all` entries.
- Confirmed the Flatpak permission boundary: `--device=dri` remains, but `/dev/uinput` is not exposed; unattended Wayland input is therefore not promised for this package path.
- Added regression coverage for exact default names, URL validation, AppImage YAML keywords, Flatpak case collisions and repeatability, udev migration, DEB purge paths, URI schemes, Python 3.6 parsing, and container prerequisites.

### Final Local Verification

- Django: 29 tests pass with no system-check findings.
- Linux packaging: 20 tests pass.
- Linux optional patch chain ran twice on clean real RustDesk `1.4.7`, `1.4.8`, and `1.4.9` worktrees.
- Native Linux package helper ran twice on real `1.4.7`, `1.4.8`, and `1.4.9` packaging files; exact lowercase `rustdesk`, custom names, runtime config paths, and URI handlers were checked.
- Python AST/YAML parsing, `actionlint`, workflow patch references, curl POST failure detection, secret scanning, ignored runtime directory checks, and `git diff --check` pass.
- No real client compilation, Flatpak runtime installation, live generator submission, or deployment was triggered for this batch.

## 2026-07-15

### Hidden Connection Window Compatibility Follow-Up

- Confirmed the core `1.4.9` release commit `8e33770` and the first capability-state follow-up `cd2c358` were already on `origin/master` after the interrupted session resumed.
- Kept build-time hidden-window capability separate from its default state while requiring new submissions to preserve the client settings entry.
- Added form schema versioning so old pages and direct POST clients that only send `hidecm=on` retain the former default-on behavior; an unchecked new checkbox remains default-off.
- Added the `allow-hide-cm` control to the Sciter password menu, including authentication-mode gating, fixed-option handling, reset behavior, strict anchors, and idempotence. This makes capability-only mode usable on Windows x86.
- Made both Flutter and Sciter persist explicit `N` values when users disable hidden-window behavior or switch to an incompatible authentication mode. Empty values would otherwise fall back to a build default of `Y` for the default `RustDesk` application name.
- Sciter reads the hidden-window state when a new connection-manager process starts; an already-open Sciter connection-manager window does not respond live to a setting change.

### Follow-Up Verification And Remote State

- Django: 38 tests pass with no system-check findings.
- Linux packaging: 20 tests continue to pass.
- Windows x86 patch chains ran twice against real RustDesk `1.4.7`, `1.4.8`, and `1.4.9` sources with the Sciter result markers verified after every pass.
- Focused Playwright checks passed for capability-only/default-on transitions, password-mode submission, legacy/current JSON import behavior, and JavaScript page errors.
- Successful Windows `workflow_dispatch` runs exist for `8e33770` (`29318081070`) and `cd2c358` (`29326063260`). They were not caused by push; public metadata cannot distinguish UI dispatch from generator/API dispatch.
- Automatic Docker runs `29317047756` and `29325337747` both failed before build at Docker Hub login because the username/password inputs were unavailable. No Docker image was built or pushed by those runs.
- This continuation did not dispatch a client build, submit the live generator form, or repair repository secrets/variables.

### Live Generator Deployment

- Pushed the compatibility fix as `23d1cf3` (`Fix hide window capability compatibility`) and deployed that exact source archive to `http://120.55.0.199:8000/`.
- The server-side build used the uploaded archive SHA-256 `aab0c37012c105a2250bf7b2e9d28deb879a700456eb32957fe8ef0fb3bc782c`; the automatic Docker Hub workflow remained blocked at login and was not needed for this local source build.
- Before switching production, saved the old source, root-only `.env`, an online SQLite backup, and the old image under deployment ID `20260715-020154-23d1cf3941b2`.
- Built candidate image `sha256:36169d635fb2936ecf723b3076a47e4db6564d59f1197c4387ea0cb74ead561b` while the old container stayed live. The image test suite and a temporary-database instance on `127.0.0.1:18000` passed before production was touched.
- Production container `e795637a48fee39243879c0a0bcd3d8ba85309ce2a9a8bc28c72efa12844ea48` started at `2026-07-15T02:13:55Z` and verified as `running`, `healthy`, and restart count `0`.
- Container-internal, host-loopback, server-hairpin, and independent public GET checks all returned the new form schema `2`, `settingsY` migration behavior, and RustDesk `1.4.9` default. No generator form POST was made.
- `.env`, `data`, `exe`, `png`, `temp_zips`, and `data/db.sqlite3` retained their original inodes. The `.env` hash stayed unchanged, SQLite `quick_check` returned `ok`, and the database remained `135168` bytes.
- Rollback material remains at `/opt/rdgen-backups/20260715-020154-23d1cf3941b2`, `/opt/rdgen-previous-20260715-020154-23d1cf3941b2`, and image tag `rdgen-rollback:20260715-020154-23d1cf3941b2`.

### Authenticated User Management And HTTPS Deployment

- Added Django login/session/CSRF protection, administrator-created user management, password change/reset, disable controls, and POST-only logout. There is no public registration.
- Bound generated tasks to their owner, added strict UUID/path checks, per-task callback bearer tokens, signed expiring ZIP downloads, and authenticated workflow callbacks.
- Verified 67/67 tests under Django `5.2.16`, parsed all 13 workflow YAML files, and passed system, migration-drift, compile, Compose, secret-scan, and whitespace checks.
- Committed the application as `13408fbc11eb6561a9128bb1a57dc48c059a5c90` (`Add authenticated user management`) with tree `c1b8bd7ed1dd30209a13f6e59fbf42297aaf3056`.
- Obtained a trusted Let's Encrypt short-lived IPv4 certificate for `120.55.0.199`, configured Nginx on 80/443, enabled 5/minute login rate limiting, closed public port 8000, and enabled twice-daily certificate renewal checks. Staging issuance and renewal dry-run both succeeded.
- Updated GitHub Actions secret `GENURL` to `https://120.55.0.199`, drained all active generator workflows, and deployed under ID `20260715-174900-d90b5bd` without submitting a live generator form.
- Built and tested candidate image `sha256:16f1ef12baa5b21a5e66fdf5eeff2053a206937ed35d793c2ac3b7ef75a2173e`. A copy of the production database migrated with all 16 task rows preserved before the live switch.
- Live verification passed for HTTPS trust, HTTP redirect, HSTS, secure session/CSRF cookies, anonymous redirects, admin login, user management, POST logout, invalid-host rejection, login 429 responses, database integrity, container health, zero restarts, and clean live logs.
- Production rollback material is `/opt/rdgen-backups/20260715-174900-d90b5bd`, `/opt/rdgen-previous-20260715-174900-d90b5bd`, and image tag `rdgen-rollback:20260715-174900-d90b5bd`.
- Automatic Docker workflow run `29406597406` still failed at `Login to Docker Hub`; this did not affect the directly built and verified production image.

## 2026-07-21

### Generator Console UI And Account Controls

- Reworked the generator and authenticated account pages into a responsive console layout with a fixed desktop sidebar, compact mobile navigation, section navigation, platform cards, build summaries, and consistent form controls.
- Corrected mixed field/toggle grids that stretched controls or left accidental gaps. Dynamic desktop options, uploads, and advanced options now redistribute visible items across Windows, Windows x86, Android, Linux, and macOS states.
- Added safe account deletion with confirmation, protection against self-deletion and deleting the last superuser, staff ownership boundaries, and retained historical build rows through `SET_NULL` ownership.
- Fixed the password-reset description to reflect Django session invalidation behavior.
- Replaced imported PNG preview `innerHTML` interpolation with strict base64 validation and DOM node creation. A malicious JSON payload was reproduced against the old path, then verified unable to execute after the fix; valid PNG imports continue to render.
- Verified desktop, tablet, and mobile layouts with Playwright. Django `5.2.16` passes 73 tests, system checks and migration-drift checks pass, and `git diff --check` reports no whitespace errors.

### Production Deployment

- Committed the application as `7e3c9fd1caed966b68234112517af295bea13ac0` (`Refresh generator UI and harden account management`, tree `c35ec1d2bf48fe05b13946ba645600ff6310fc1b`). The source archive SHA-256 is `b11dfaf8891d5aadf0025fae14eac2d9b884cb82af985a7cee9fb12ee2319492`.
- Created an online SQLite backup and rollback image while the old service remained healthy, then built candidate image `sha256:f957ac977fb5a715a5ec7142c4dcc0d3ba27ce1407a372b7656e719f243dd050` directly on the server.
- The candidate passed all 73 tests, production security checks, migration checks, SQLite integrity checks, authenticated template rendering, and an isolated healthy instance on `127.0.0.1:18000` before production was stopped.
- Deployed under ID `20260721-201116-7e3c9fd1caed`. The live `rdgen-rdgen-1` container is healthy with zero restarts and clean logs; HTTP redirects to trusted HTTPS, anonymous access redirects to login, the new login markup is public, and port 8000 remains loopback-only.
- `.env`, `data`, `exe`, `png`, `temp_zips`, and SQLite inodes were preserved. The production database retained 4 users and all 26 task rows; no schema migration was added.
- Rollback material is `/opt/rdgen-backups/20260721-201116-7e3c9fd1caed`, `/opt/rdgen-previous-20260721-201116-7e3c9fd1caed`, and image tag `rdgen-rollback:20260721-201116-7e3c9fd1caed`. Both 2026-07-15 rollback sets remain intact.
- No live generator form was submitted, no account was deleted, and no client workflow was dispatched during deployment. One stale database row labeled `in_progress` maps to a GitHub run already completed as cancelled.

## 2026-07-22

### Account Entitlements And Expiring Downloads

- Added permanent/time-based and successful-package-count account policies. Count reservations are created atomically with task rows, released on failure/timeout, and consumed once only after the first valid installer upload; settlement guards administrative mode changes and concurrent cleanup.
- Added per-build login-required or public-token download delivery with 1-hour, 1-day, 3-day, or 7-day link expiry starting at the first valid installer upload. Physical artifacts are capped at seven days.
- Added user-management quota controls and status display, Beijing-time expiry input/display, delivery controls and summaries, authenticated/public download enforcement, and retained history/download access after account expiry.
- Added migrations `0004`-`0006`, the `purge_generated_files` command, and focused entitlement/download/cleanup tests. Alpine now installs `tzdata` for `Asia/Shanghai`.
- Fixed two release-audit race conditions before deployment: reservation and run creation now commit together, and artifact settlement locks the run while guarding reservation decrements from going negative.
- Local and candidate-image Django suites both pass 94/94 tests; system, migration-drift, Compose, whitespace, timezone, and archive-content checks passed.

### Production Deployment

- Deployed application commit `80f255ac1bddd5a71401afa4fcd80594297fff0d` (tree `fab056c083c4714dbfc37389e14926c61232e3a4`) from source archive SHA-256 `8f07129d6e1c3cce0300cddffe10bafccddfff7a520d73f95d0d498b2df63c52` under ID `20260722-103341-80f255ac1bdd`.
- Built image `sha256:523119eb6245e22b365e39a210a5c9632ba887fa9ae6095e5a2040ab60764765` directly on the server. Django `5.2.16` passed all 94 tests, and a copied production database applied migrations `0004`-`0006` and passed authenticated template/health checks on `127.0.0.1:18000` before switching.
- Live `rdgen-rdgen-1` is `running`, `healthy`, restart count `0`; HTTP redirects to HTTPS, `/` redirects to login, `/login/` and `/healthz` return 200, HSTS remains enabled, and port 8000 is loopback-only.
- `.env` plus `data`, `exe`, `png`, `temp_zips`, and SQLite inodes were preserved. SQLite `quick_check` passed with 2 users, 2 entitlement rows, and all 26 historical task rows retained.
- Installed `/etc/cron.d/rdgen-cleanup` with hourly `flock` protection. Initial enforcement removed 13 expired secret ZIPs and one empty directory, no generated installer and no quota reservation; a follow-up dry-run reported zero pending removals.
- Current rollback material is `/opt/rdgen-backups/20260722-103341-80f255ac1bdd`, `/opt/rdgen-previous-20260722-103341-80f255ac1bdd`, and image tag `rdgen-rollback:20260722-103341-80f255ac1bdd`.
- No live generator form was submitted and no GitHub client workflow was dispatched during deployment. The single legacy `in_progress` database row still maps to a GitHub run already completed as cancelled.

### Relaxed Password Policy And Chinese Validation

- Replaced Django's similarity, common-password, and numeric-password restrictions with one minimum-length rule of 6 characters. Six-digit numeric passwords, common combinations, and passwords matching the username are accepted; five-character passwords remain rejected.
- Set the Django language to Simplified Chinese and added a project-owned minimum-length validator so creation, administrator reset, and personal password-change guidance/errors stay Chinese under the production Django `5.2.16` runtime.
- Added regression coverage for all three password paths, the relaxed cases, the 5/6-character boundary, Chinese help, and Chinese mismatch errors. Local and candidate-image suites pass 99/99 tests with no migration drift.
- The first isolated candidate correctly caught that Django `5.2.16` left the short-password error in English; that candidate never reached production. Commit `276fb0c016c64336b1b1845ebbb2d1ec9fdf5ce4` (tree `cf337c395443d4fb9d28fba4dd2a4a8d9883d125`) adds the version-independent Chinese validator.
- Deployed source archive SHA-256 `c690078b033bb60c4141a32170d4e755d4668186a2e87dbde53bf24fb00c061d` under ID `20260722-110755-276fb0c016c6`; live image is `sha256:934bc6a9342d3d93d1b36cdbf2142ad22047de8c84bc26e44b9fc99a4108e66c`.
- Deployment waited for user build run `29886880669` to finish. Its two installers (49,280,160 bytes total) uploaded successfully and its quota reservation settled before the container switch.
- Production verification passed for HTTPS, authenticated password pages, explicit Chinese validation, SQLite integrity, persistent inode preservation, clean logs, container health, and zero restarts. The live database retained 3 users, 3 entitlement rows, and 27 tasks.
- Current rollback material is `/opt/rdgen-backups/20260722-110755-276fb0c016c6`, `/opt/rdgen-previous-20260722-110755-276fb0c016c6`, and image tag `rdgen-rollback:20260722-110755-276fb0c016c6`.

### Windows EXE And MSI Completion

- Diagnosed task 27: `21313.exe` arrived first and changed the task to success, while `21313.msi` arrived about six seconds later. The generated page enumerates both formats correctly, but the already-rendered result page did not refresh after the second upload.
- Windows x64 dispatches now start in `artifacts_pending`. Both workflows require MSI build, signing archive extraction, rename, and non-empty EXE/MSI files; each file uploads with deferred completion, followed by a task-authenticated finalization request that validates both expected files before success.
- GitHub success/progress callbacks cannot bypass deferred completion. Completed GitHub runs without finalization become `artifact_incomplete`; conditional database updates prevent polling, finalization, late callbacks, and failures from overwriting each other with stale state.
- Local and candidate-image Django suites pass 104/104 tests. Two focused workflow tests pass, all workflow YAML parses, system checks and migration-drift checks pass, and no migration was added.
- Deployed application commit `f2f8ea0ecc0ccff4178e81e1ca95dbb179005a81` (tree `3499379ef567692978e4b55f917e6f9b5dce54b8`) from archive SHA-256 `1d098e67da45d229bf8a401a948954411ea14c799daf9f90f0592fbcbad72af3` under ID `20260722-124503-f2f8ea0ecc0c`.
- Live image `sha256:f87baa88f651ccb10b8b8c9312c54a1661d11cacce4541766dd4f16b138921db` is `running`, `healthy`, restart count `0`. SQLite `quick_check`, `migrate --check`, HTTPS health/login redirects, clean logs, and the existing page containing both `21313.exe` and `21313.msi` were verified with 3 users and all 27 tasks retained.
- Current rollback material is `/opt/rdgen-backups/20260722-124503-f2f8ea0ecc0c`, `/opt/rdgen-previous-20260722-124503-f2f8ea0ecc0c`, and image tag `rdgen-rollback:20260722-124503-f2f8ea0ecc0c`. The immediately preceding `20260722-122857-11ce7a56af22` deployment remains available.
- No live generator form was submitted and no client workflow was dispatched for this fix.

### Atomic Windows Artifact Delivery Follow-Up

- Replaced filename/disk-only completion with a persisted run contract and `GeneratedArtifact` receipts keyed by run and filename. Each receipt stores size and SHA-256; Windows x64 finalization derives the exact expected EXE/MSI names from the database and validates both receipts plus final disk hashes.
- Uploads now stream to hidden same-directory staging files before a short SQLite write transaction and atomic replacement. Identical retries are idempotent and can repair a missing/corrupted disk copy, while different content for an existing receipt returns conflict and cannot replace a published installer.
- Dispatch and callback transitions use conditional updates. Ambiguous GitHub dispatch network failures remain callback-capable, terminal states absorb late callbacks, Windows success cannot bypass finalization, and independent workflow failure jobs cover setup, bridge, third-party dependency, and main-build failures.
- The hourly cleanup now marks nonterminal runs older than the 24-hour callback lifetime as `timed_out` and releases unconsumed quota reservations. Migration `0007_githubrun_artifact_contract_generatedartifact` adds the persisted platform/stem contract and receipt table while leaving historical rows on the verified legacy fallback.
- Local verification passed 124 Django tests, 42 focused machine/cleanup tests, three workflow command tests, both workflow YAML parses, `actionlint`, system checks, migration-drift checks, and `git diff --check`. Independent review found no remaining steady-state P1/P2 blocker after the CAS, staging, receipt, finalization, and failure-reporting fixes.
- Deployed commit `c92c48cc71d6123b2f401863c15407bc03c524ed` (tree `6b2d6cf3b6ac092fa80538973a6a96176c701102`) from archive SHA-256 `258f97022b1774993b13e1630a687c411d3f7778c258b7235fcd14d4a1caeab3` under ID `20260722-163349-c92c48cc71d6`. Live image `sha256:274761ab3fdec4dbbaaaf12f399cce99f846cc6e3263362b1caded9a089ec815` is healthy with zero restarts.
- Production migration and post-deploy checks retained 3 users and all 27 tasks, applied `0007`, reported SQLite `quick_check=ok`, and verified task 27 still renders both `21313.exe` and `21313.msi`. The former cancelled legacy row was later timed out by cleanup, leaving zero active database/GitHub client workflows.
- GitHub `master` was non-force fast-forwarded to `c92c48c` after verifying all 11 blobs, the tree, and commit SHA. Push-triggered Docker run `29907047085` failed at the existing Docker Hub login step; it did not trigger a client generation and does not affect the directly deployed production image.
- No live generator form was submitted and no fresh public client build was dispatched. Full generation depends on the public GitHub callback path; local Docker is not a meaningful end-to-end test environment and is only useful for optional UI/form inspection.
- Current rollback material is `/opt/rdgen-backups/20260722-163349-c92c48cc71d6`, `/opt/rdgen-previous-20260722-163349-c92c48cc71d6`, and image tag `rdgen-rollback:20260722-163349-c92c48cc71d6`.

### Generator Workspace Entitlement Summary

- Added a single `entitlement_summary` context for every generator-page render branch. Ordinary count-plan users see total, used, in-progress reservations, and remaining generations; time-plan users see permanent, remaining-day, Beijing expiry, or expired status. Staff and superusers remain unlimited and do not receive the panel.
- Exhausted counts, missing count limits, and expired memberships render explicit unavailable states and disable the submit button with matching Chinese text. The existing atomic backend reservation check remains authoritative and a forged valid POST was verified unable to create a task or call GitHub.
- Added 10 focused page/security tests; the complete Django `5.2.16` suite now passes 134/134 locally and in the production candidate image. No database field or migration was added.
- Playwright screenshots at 1440x1000, 900x900, and 390x844 verified the desktop sidebar placement and responsive navigation-under status strip without account/nav overlap or page-level horizontal scrolling.
- Deployed commit `fe7ee968c91a0eead6e5d31267e41cc013522eb9` (tree `057845f4718b4987e01eb634cad3a58dbe9127de`) from archive SHA-256 `cb7133b2f8c48fb1f3566317a7987dbefec2ee11dae5cd5c7cc4ae627abd9b5e` under ID `20260722-180717-fe7ee968c91a`.
- Live image `sha256:2d89717ea403ccc92c639254b28695c489ebf5bc72586844269130395bb64c50` is `running`, `healthy`, restart count `0`. The final stop-time SQLite snapshot passed `quick_check`, retained 3 users and all 27 tasks, and both pre/post gates reported zero active GitHub client workflows.
- Production-only rendering verified both ordinary accounts against their actual entitlement rows and verified the administrator has no entitlement panel or disabled submit button. Public `/healthz` and `/login/` returned 200, Nginx validation passed, and live logs had no error fingerprints.
- Current rollback material is `/opt/rdgen-backups/20260722-180717-fe7ee968c91a`, `/opt/rdgen-previous-20260722-180717-fe7ee968c91a`, and image tag `rdgen-rollback:20260722-180717-fe7ee968c91a`. The previous atomic-artifact deployment remains available.
- No live generator form was submitted and no client workflow was dispatched during deployment or verification.
- GitHub `master` was non-force fast-forwarded through `c620190` with all blob/tree/commit identities verified. Push-triggered Docker run `29911513230` failed only at the existing Docker Hub login step and did not dispatch a client build.

### Embedded Local Generator Icons

- Replaced the five Cloudflare Font Awesome loaders with `templates/includes/local_icons.html`, which embeds a minimal Font Awesome 6.4.0 WOFF2 subset and its OFL license. Corrected all 43 CSS glyph escapes and changed the success message to the included `U+F00C` check glyph.
- Generated three transparent PNG masks for the client-generator navigation item, user-management navigation item, and bottom generate-client action. The final project assets are `client-generator.png`, `user-management.png`, and `generate-client.png`; generation intermediates were removed and no endpoint or credential was stored in the repository.
- Verified every mapped solid/brand glyph, conditional entitlement and user-management states, download icons, and the JavaScript copy/check transition. Desktop, user-management, bottom-action, and 390x844 mobile screenshots showed no missing-glyph boxes, horizontal overflow, or Font Awesome CDN requests.
- Django `5.2.16` passed 134/134 tests locally and in the candidate image. `manage.py check`, migration-drift detection, archive-content checks, production template rendering, browser console/network inspection, and `git diff --check` all passed.

### Local Icon Production Deployment

- Committed application release `4da7e535f35a4aeefda2faf4bef6585856fe2e44` (`Embed local generator icons`, tree `539488f3f0b7627f820c756138ddb396230bd4ac`) and deployed archive SHA-256 `e483f9c7728b56248b8a8df797f509bb58af1fd701dc80bdcb74b69a87a394c4` under ID `20260722-204633-4da7e535f35a`.
- Live image `sha256:26d2c7e458024868899adc85505e05632cd20988cfbf40a834074303bc8342e7` is `running`, `healthy`, restart count `0`. Nginx validation, HTTPS health/login behavior, loopback-only port 8000, migrations, SQLite `quick_check`, icon file hashes, clean logs, and persisted-directory preservation passed.
- The production database retained 3 users, 27 task rows, 3 entitlement rows, and 0 artifact receipts. Pre-deployment and stop-time snapshots both passed `quick_check`; database and GitHub client-build gates were zero before and after the switch.
- Current rollback material is `/opt/rdgen-backups/20260722-204633-4da7e535f35a`, `/opt/rdgen-previous-20260722-204633-4da7e535f35a`, and image tag `rdgen-rollback:20260722-204633-4da7e535f35a`. The preceding entitlement deployment remains available.
- `origin/master` was fast-forwarded to `4da7e53`. Push-triggered Docker run `29920197862` failed only at the repository's existing Docker Hub login step and did not dispatch a client build. No live generator form was submitted during deployment or verification.

## 2026-07-23

### macOS Dual-Architecture Workflow Validation

- Fixed macOS customization so the requested application name is applied to the validated Cargo metadata without renaming RustDesk package or binary identifiers. Added focused workflow and customization regression tests.
- Added an isolated `validation_mode` to `.github/workflows/generator-macos.yml`. It uses fixed non-production configuration, keeps signing secrets out of global environment state, forces ad-hoc signing, validates bundle metadata and the expected Mach-O architecture, verifies the DMG, uploads one-day artifacts, and skips all production upload and cleanup callbacks.
- Workflow implementation commit `5694553478ccde3967446c460e734ae719f278d6` passed GitHub Actions run `29975374837`. The `aarch64` job reported `Built executable architectures: arm64`; the Intel job reported `Built executable architectures: x86_64`. Both app bundles passed `codesign --verify`, and both DMGs passed `hdiutil verify`.
- The generated outputs are `MacAudit-aarch64.dmg` (25,787,953 bytes, SHA-256 `849022e5ca9a84b24cbb7ef233cbb253e0fee8e24a3d1b05b85d18207662eb67`) and `MacAudit-x86_64.dmg` (32,348,623 bytes, SHA-256 `25151cb4d1349fa2055f98393547174c05c7f536bb391d4ba962e072333e234e`). Both downloaded files have the expected UDIF `koly` trailer and are archived under `D:\rustdesk-生成器\rdgen\output\macos-validation-29975374837`. They are separate architecture-specific images rather than a Universal binary. Production P12 signing, notarization, and stapling were not exercised.
- Local verification before dispatch passed 36 patch tests, all 134 Django tests, Django system and migration-drift checks, workflow YAML parsing, `actionlint`, the RustDesk 1.4.9 macOS patch-chain smoke test, and `git diff --check`.
- This was a workflow-only validation. The generator server remained on application commit `4da7e53`; no production generator form, upload callback, cleanup callback, or server deployment was triggered.

### Hide Tray Setting And Wallpaper Default

- Added a dedicated “隐藏系统托盘图标” option under Advanced / Other Settings. Selected desktop builds serialize `override-settings.hide-tray=Y`; Android and standard Linux combinations are rejected server-side.
- Changed “传入会话期间移除壁纸” from default-on to explicit opt-in. Both controls render unchecked on new forms.
- Legacy `hide-tray` and RustDesk-equivalent `hide_tray` entries are normalized from either manual textarea into the dedicated toggle. Override settings take precedence over default settings, duplicate lines are removed, and unsupported imported configurations retain their line so a Chinese validation error is shown instead of silently losing the value.
- Local browser checks covered Windows legacy import, Android rejection, unsupported Beijing Linux versions, default unchecked state, and browser console errors. Django `5.2.16` passed all 144 tests; system, migration-drift, archive, and whitespace checks passed.

### Hide Tray Production Deployment

- The first deployment candidate from `465f29b` passed 139 tests and isolated-container checks but failed a post-switch markup assertion. The signal-aware deployment script restored the prior source, image, and final SQLite snapshot; follow-up checks confirmed the old service healthy with 3 users, 27 tasks, and zero active client builds.
- Independent review then found manual `defaultManual` and underscore-alias bypasses plus an unsupported Linux-version import edge. These were fixed before release and covered by the final 144-test suite.
- Deployed application commit `e7e4740f698643c3acfc7f4e3ee015290a45bc7e` (tree `b64fe2c202a97762496fa0f6991353047c76d534`) from archive SHA-256 `ab2afb959829927dc1484768df9ccd258bdaf9e1739027e354e9aa47a4c269b5` under ID `20260723-162446-e7e4740f6986`.
- Candidate image `sha256:0caa747a28c97703f3c6568582800d7ead2d55e352e3425584a3e74f3fe9715c` passed all 144 tests, migration and security checks, copied-production SQLite integrity, authenticated RequestFactory rendering, and a healthy isolated instance on `127.0.0.1:18000` before cutover.
- Production `rdgen-rdgen-1` is `running`, `healthy`, restart count `0`. Public HTTP/HTTPS, login, health, HSTS, Nginx, database snapshots, entitlement rendering, hide-tray alias parsing, clean logs, and zero active GitHub client runs were independently rechecked. The database retained 3 users and all 27 task rows.
- Current rollback material is `/opt/rdgen-backups/20260723-162446-e7e4740f6986`, `/opt/rdgen-previous-20260723-162446-e7e4740f6986`, and image tag `rdgen-rollback:20260723-162446-e7e4740f6986`. The previous icon deployment rollback set remains available.
- No live generator form was submitted and no client workflow was dispatched during deployment or verification.

## 2026-08-05

### Membership, Activation Codes, And Verified Registration

- Added public registration with username, unique email, password, and a required email verification code. Registration codes are normalized per email, stored only as salted digests, expire after five minutes, enforce resend, per-email, per-IP, and failed-attempt limits, and are consumed atomically when the account is created.
- Newly registered accounts start without membership and cannot generate clients until activated. Existing administrator behavior remains unlimited.
- Added hashed membership activation codes for one generation, 3 days, 7 days, 30 days, and lifetime. Activation is transactional, prevents reuse and conflicting plans, and updates the user's entitlement from the generator workspace.
- Added a staff-only activation-code console for controlled batch generation, masked listing/filtering, redemption metadata, and revocation of unused codes. Plaintext codes are returned only once in the generation response and are never stored in the database.
- Added QQ SMTP configuration support and the user-facing send-code control on `/register/`. The mailbox and authorization value are intentionally absent from repository files and this log.
- Added migrations `0008_activationcode` and `0009_registrationemailcode`, cleanup for expired verification rows, responsive account/registration templates, navigation entries, administrator registrations, and focused security/lifecycle tests.
- Application commit `16389d36cd355089ff72d7030648567644a7fca0` (`Add memberships and verified registration`, tree `7b1d52640717ff2ad9a8ed7bda89d45d3157e1dc`) was fast-forwarded to `origin/master`. Push-triggered Docker run `30992470460` failed at the repository's existing Docker Hub login step and did not dispatch a client build.

### Production Deployment

- Deployed source archive SHA-256 `bc131b2efd9bcbc86137beb78a1a48bc6a9c6a9c65b873d2158098ceb653d907` under ID `20260805-171543-16389d36cd35`. The server built candidate image `sha256:bbae70fc379f02227cba3c6cfab37e781e2cf30b325d4fd3ead3eda2c5078fd0` using the configured Alibaba PyPI mirror.
- Local and candidate-image Django `5.2.16` suites passed all 169 tests. The first candidate test invocation inherited the production HTTPS setting and therefore exposed only 301 test-client redirects; rerunning the same image with test-only HTTPS and in-memory-mail overrides passed 169/169. The copied production database, both new migrations, isolated login/registration pages, and QQ SMTP authentication also passed before cutover.
- The first cutover reached a responding new container but treated Docker's initial `starting` health state as failure. Its signal-aware handler restored the previous source, image, environment, and final SQLite snapshot; the old service returned healthy with 3 users, 39 runs, and migrations only through `0007`.
- The corrected cutover waited for Docker `healthy`, repeated both stop-time database and GitHub activity gates, applied `0008` and `0009`, and completed at 2026-08-05 17:55 China time. Live `rdgen-rdgen-1` is `running`, `healthy`, restart count `0`, and uses the candidate image.
- Public HTTPS checks passed for `/healthz`, `/login/`, and `/register/`; GET on `/register/email-code/` returns 405, HTTP redirects to HTTPS, and HSTS remains enabled. The production container successfully authenticated to QQ SMTP over SSL port 465 without sending a post-deploy message.
- SQLite `quick_check` and `migrate --check` pass with all 3 users and 39 historical runs retained. Activation-code and registration-email-code tables began empty, persistent `data`, database, `exe`, `png`, and `temp_zips` inodes were preserved, and post-deploy logs contain no error fingerprints.
- Current rollback material is `/opt/rdgen-backups/20260805-171543-16389d36cd35`, `/opt/rdgen-previous-20260805-171543-16389d36cd35`, and image tag `rdgen-rollback:20260805-171543-16389d36cd35`. The backup set includes online and both stop-time SQLite snapshots, prior environment, source archive, build/test logs, and image metadata.
- Database and GitHub gates reported zero active client workflows before, during, and after the switch. No live generator form was submitted and no client workflow was dispatched during deployment or verification.

## 2026-08-06

### Login Page Redesign And Production Deployment

- Added the approved two-column login page with an independently scoped stylesheet and a generated square build-flow illustration. The visual expresses configuration, cloud build, and multi-platform delivery without pricing or membership copy. Authenticated generator, user-management, activation-code, result, and registration templates remain unchanged from the preceding production application.
- Application commit `19141a9b8d063b23b64fd4147500c3b9ec9c7e4e` (`Redesign login page with build illustration`, tree `7eb56cc2782695f17c30242a14eaee5e032bfe2c`) was pushed to `origin/master`. The fixed-commit source archive SHA-256 is `63393cbf94e9016d25618b3889071206e11570afeaa5928315e5d906ccd1458c`.
- Production previously proxied every `/static/` request to Django, which returns 404 under Gunicorn with `DEBUG=False`. The deployment therefore added two exact, read-only Nginx aliases for `login-modern.css` and `auth-build-flow.png`; it did not expose the general static directory or alter TLS, HSTS, login rate limiting, redirects, or application proxy settings. The original and replacement Nginx files are both in the rollback backup.
- Deployed under ID `20260806-084425-19141a9b8d06`. Candidate and live image `sha256:8849d63de8389d1c6f9b67ef4400da64fa1146bcd68596629699818c5504d2c6` passed the complete 169-test suite on Django `5.2.16`, deployment and migration-drift checks, copied-production migration rehearsal, isolated login/registration rendering, static-asset hash checks, and a healthy isolated instance before cutover.
- The cutover repeated database and GitHub activity gates before and after stopping the old container, saved an online and final SQLite snapshot, and preserved `.env`, `data`, `exe`, `png`, and `temp_zips`. Production returned `running`/`healthy`, restart count `0`, with 3 users, all 39 historical runs, SQLite `quick_check=ok`, `migrate --check`, and zero active builds.
- Public `/login/`, `/register/`, `/healthz`, the CSS, and the illustration return 200; GET `/register/email-code/` returns 405, anonymous `/` redirects to login, HTTP redirects to HTTPS, and HSTS remains enabled. The served asset hashes match the committed files. Browser verification found the stylesheet and 1254×1254 image loaded, no horizontal overflow, and no console issues.
- Post-deploy `diff -qr` confirmed that every template other than `registration/login.html` matches the previous source. No live generator form was submitted and no RustDesk client workflow was dispatched.
- Current rollback material is `/opt/rdgen-backups/20260806-084425-19141a9b8d06`, `/opt/rdgen-previous-20260806-084425-19141a9b8d06`, and `rdgen-rollback:20260806-084425-19141a9b8d06`. The prior membership deployment rollback remains available.

### Login Form Centering Follow-up

- The legacy `.login-panel { width: min(430px, 100%) }` rule in the shared account stylesheet constrained the new login grid item to the left edge. Release `519e12ac765233f22e7e86e0dc90aea1b3079b21` makes the login-specific panel span its full grid column while retaining the 410px centered inner form. The stylesheet URL now uses `?v=2` so clients do not retain the previously cached layout.
- The complete 169-test suite passed locally and in the candidate image. The isolated candidate, production-database migration rehearsal, public template and static-asset checks, mobile layout check, Nginx validation, and post-cutover health checks passed without submitting the generator form.
- Deployed source archive SHA-256 `292ccb173d38d64b15f731d06ddd363fda834d346f6ee917ebc94f41504b267d` under ID `20260806-095234-519e12ac7652`. Live image `sha256:53916132e3ffb7b16de22175c76734372041ce971b6bc8398256b2a364bea996` is running and healthy with restart count `0`.
- SQLite `quick_check` passes with 4 users, all 39 historical runs, and zero active runs. Database and GitHub gates stayed clear throughout the switch; recent logs contain no error fingerprints. Current rollback material is `/opt/rdgen-backups/20260806-095234-519e12ac7652`, `/opt/rdgen-previous-20260806-095234-519e12ac7652`, and `rdgen-rollback:20260806-095234-519e12ac7652`.

### Scoped Build History Dashboard

- Added `/build-records/` and a navigation entry for every authenticated user. Staff can view all retained tasks, including orphaned history from deleted accounts; members are scoped to `owner=request.user` before any filters are applied. The page is read-only and never renders callback or download-token hashes.
- The dashboard shows total/success/active/failed counts, 30-row pagination, build name and UUID, owner, platform, localized status, submission time, artifact count and download expiry. Staff filters cover owner, status, platform, time, name, UUID, username, and numeric GitHub run ID; members receive the same task filters without the owner selector.
- Eight focused access/filter tests raised the complete suite to 177 passing tests. A 43-row browser fixture verified desktop layout, pagination, filter interaction and zero horizontal overflow; production-candidate and live RequestFactory checks verified authenticated administrator rendering and member isolation without writing to production data.
- Deployed application commit `c304e1573be862d719f9a3454b5304b267182f35` (tree `bf3dd672afd11af6c8c300a7a15864a3a23e061c`) from archive SHA-256 `b9899fd6cc2ae87ecf0ad7af080e0a879cc55a7db7b0b343b09bc81388e85a85` under ID `20260806-112556-c304e1573be8`. Live image `sha256:c22c67d9dd83c555f04688d02ff0a9afc4521c80514cf7a476fbd99e14f1af6d` is running and healthy with restart count `0`.
- Production retained 4 users and all 39 historical tasks; SQLite `quick_check`, migrations, database/GitHub activity gates, public redirect behavior and recent logs passed. No generator form or client workflow was submitted. Current rollback material is `/opt/rdgen-backups/20260806-112556-c304e1573be8`, `/opt/rdgen-previous-20260806-112556-c304e1573be8`, and `rdgen-rollback:20260806-112556-c304e1573be8`.

### Full-width Management Workspace

- Removed the shared 1180px desktop cap from `base_account.html`. On desktop, the main workspace now fills all width to the right of the fixed 248px sidebar, so build records, user management, and activation-code management no longer leave a large unused column on wide screens. Login/auth layouts and form panels retain their own width constraints.
- Local browser geometry checks covered all three management routes without horizontal overflow; the complete local and candidate-image Django suites passed 177/177 tests, along with system checks, migration-drift checks, compile checks, copied-production migration rehearsal, authenticated rendering, and build-record permission isolation.
- Application commit `11bd5bd3f877ef02c702096dbb2a606302d136f9` (tree `0f5b6f760ced089e1b82ee540c9777a879ccc9c9`) was deployed from archive SHA-256 `e496589895e3e69e8f8071fb859bd3d28281f9b1d143ae84586b280e31538b94` under ID `20260806-114847-11bd5bd3f877`. Live image `sha256:3661f8b5f014a789656915bb18cbc719aa1575bb0c61ed9c549c311ae0e9a63f` is `running`, `healthy`, and has restart count `0`.
- Production preserved 4 users and all 39 historical tasks, with SQLite `quick_check=ok`, zero active builds, all three management-page full-width assertions passing, and no recent error fingerprints. No generator form or client workflow was submitted. Current rollback material is `/opt/rdgen-backups/20260806-114847-11bd5bd3f877`, `/opt/rdgen-previous-20260806-114847-11bd5bd3f877`, and `rdgen-rollback:20260806-114847-11bd5bd3f877`.

## 2026-08-09

### Official RustDesk Client Source Sync

- Reused the clean official clone at `D:\rustdesk-生成器\rustdesk-src` rather than creating another duplicate. It previously pointed at detached tag `1.4.6`; the separate dirty `rustdesk-src-147-inspect` and `rustdesk-src-149-inspect` patch-test trees were inspected read-only and left untouched.
- Fetched the official `https://github.com/rustdesk/rustdesk.git` default branch with proxy overrides and created local tracking branch `upstream-master`. Local HEAD and the independently queried official remote HEAD both equal `11190fa54e45fd244ad46b46052f92be6a01d3c5` (`docs: fix comma splice gui tutorial in README.md (#15787)`, 2026-08-08 09:33:58 +0800).
- Fetched and recorded latest stable tag `1.4.9` at `6c578292e8ebbbec708b76986ba8c4bc7c509747`. Current master declares `version = "1.4.9"` in `Cargo.toml` and `1.4.9+67` in `flutter/pubspec.yaml`.
- Initialized `libs/hbb_common` recursively at `69cea8dafee147848ae88702029f4bf7df7224c3`. Verified the main worktree and submodule are clean, required Rust/Flutter manifests exist, and the main repository plus submodule contain 984 tracked entries. The clone remains intentionally shallow/partial (`blob:none`); additional history can be fetched if later source questions require it.

### Official RustDesk OSS Server Source Sync

- Cloned `https://github.com/rustdesk/rustdesk-server.git` into the independent sibling directory `D:\rustdesk-生成器\rustdesk-server-src` using a shallow partial clone with recursively initialized submodules.
- Local `master` and an independent official remote HEAD query both resolve to `a7736be5e40f85bfc141120dce587e836e5d4b80` (`Delete .github/dependabot.yml`, 2026-08-07 16:56:36 +0800). The worktree and submodule are clean.
- Fetched and recorded latest stable tag `1.1.16` at `73523b31cfd25d77dee862e6fc9f5e1fb5e485ef`; current master declares development version `1.1.17` in `Cargo.toml`.
- Initialized `libs/hbb_common` at `69cea8dafee147848ae88702029f4bf7df7224c3`. The main repository plus submodule contain 144 tracked entries, including the `hbbs` default binary source in `src/main.rs`, `hbbr` in `src/hbbr.rs`, and Docker/systemd/Debian/Kubernetes deployment material.
- Recorded this directory as the clean, read-only-by-default OSS server reference. Its repository-local `AGENTS.md` must be read before future edits and requires semantic-only diffs plus explicit error handling in production Rust code.

## 2026-08-10

### Generator Host RustDesk Server Audit

- At the user's request, performed a root-level, read-only audit of `120.55.0.199` before any destructive action. The host's only running Docker workload is the healthy `rdgen-rdgen-1` generator under compose project `/opt/rdgen`; its restart count is `0` and public `/healthz` returns `200`.
- Found no RustDesk `hbbs`/`hbbr` containers, images, processes, systemd services, commands, installed packages, Docker volumes/networks, cron entries, Nginx references, firewall rules, exact-named deployment files/directories, or TCP/UDP listeners on ports 21114-21119.
- Matches containing `rustdesk` in the first broad filesystem scan were generator patch/workflow files inside `/opt/rdgen` and preserved generator rollback trees. They are not RustDesk server installations and were deliberately preserved.
- Because the user's deletion condition was “delete it if present” and no RustDesk server target existed, no service, container, file, data, firewall rule, or image was deleted. The host boundary is now explicitly generator-only unless the user later authorizes a RustDesk server installation.

### OSS Multi-relay Phase-one Deployment And Client Validation

- The user explicitly changed the host boundary for a temporary functional test. Deployed the official stable RustDesk OSS server `1.1.16` release under `/opt/rdgen-relay-test`; the downloaded Linux amd64 archive matched SHA-256 `0565c41affe6c3f409b0bddfaf5a24ccbf3f64f5f8e3fec250b69a0d5f6bdbcf`.
- The isolated topology is one hbbs at `120.55.0.199:22116`, relay A at `120.55.0.199:22117`, and relay B at `120.55.0.199:23117`. The relay field must remain blank in clients so hbbs can select a node. `ALWAYS_USE_RELAY=Y` made the client test unambiguous.
- Created locked service user `rdgen-relay-test` and transient systemd units `rdgen-relay-test-hbbs.service`, `rdgen-relay-test-hbbr-a.service`, and `rdgen-relay-test-hbbr-b.service`. Each unit is sandboxed and limited to 128 MB memory, 25% CPU, and 64 tasks. The generator container was not modified.
- Server-side runtime-console checks reported both relays healthy and alternated B/A/B/A. Public TCP reachability passed for hbbs/NAT/WebSocket ports `22115-22119` and relay-B ports `23117`/`23119`.
- Two real clients on different external networks provided the end-to-end proof. The first forced-relay session paired through B at 09:12:06; the second paired through A at 09:13:24 with two live TCP connections. Both hbbr logs reported a successful pair and raw relay transport.
- For failover, relay A was stopped at 09:14:13. hbbs removed it from the healthy list, and the connected clients automatically established a new paired session through B at 09:14:21, about eight seconds later. This is reconnect-on-failure rather than seamless migration of the original transport.
- Relay A was re-created with its original transient-unit restrictions after the stop unloaded it. Final verification reported A active, both relays back in the healthy pool, and `rdgen-rdgen-1` still running/healthy with restart count `0`.
- This same-machine, different-port arrangement validates OSS relay-list parsing, health filtering, round-robin selection, forced relay, and client reconnection. It does not validate geographic routing, latency/load-aware selection, independent-server failure, or production capacity. Keep the test isolated and preserve its private key outside repository memory.

### Generator-managed Relay Selection

- Source tracing found that the old generated top-level `relay-server` value only entered RustDesk `HARD_SETTINGS`, while the rendezvous mediator reads `override-settings`, local configuration, and `default-settings`. The old field therefore did not reliably control relay selection.
- Commit `d4ec7e498a60f0996b9b10372b8ac0d1b365d10c` (tree `eba9444758cb4b1bc82fc5aef29c269633a4497e`) replaces that inert output with an explicit `override-settings.relay-server`. The default empty value suppresses an old local fixed relay and accepts the healthy relay selected by hbbs; a nonempty advanced field forces exactly one hbbr. Client-side comma lists are rejected because the OSS pool belongs in hbbs.
- The form now distinguishes ID server from fixed relay, derives the default API URL safely from a host with an optional port, opens the advanced section on errors/imported values, and migrates legacy manual `relay-server` lines into the dedicated field without silently changing their meaning.
- RustDesk source compatibility was checked across every generator-supported release from `1.3.3` through `1.4.9`. Empty and nonempty override values follow the required priority in all of them; top-level `relay-server` is ineffective in all of them.
- Final local verification passed all 189 Django tests, system checks, migration-drift checks, workflow YAML parsing, `actionlint`, browser desktop/mobile/import checks, and `git diff --check`. Push-triggered Docker run `31349924535` failed only at the pre-existing Docker Hub login step and had no effect on production.

### Relay-aware Generator Deployment And Real Build

- The first candidate deployment `20260810-102934-d4ec7e498a60` stopped before cutover because its expected CSS checksum came from the CRLF worktree instead of the LF-normalized Git archive. Production remained untouched and healthy. The corrected archive process used Git-blob bytes.
- Deployment `20260810-103245-d4ec7e498a60` installed commit `d4ec7e4` from archive SHA-256 `b5b2ff4cfa00ffcac5c9668618a71e6a0541d6c781fd2c9b89ea330e7bf577bb`. Candidate image `sha256:d2358abecb4c7bf741e4a96d90bc766c9ad70e876fa27cfc78e29bee71c147c7` passed the complete 189-test suite and isolated production checks before cutover. Live `rdgen-rdgen-1` is healthy with restart count `0`.
- Persistent data and configuration were preserved. SQLite `quick_check` and migrations pass; production retained 4 users and 39 prior task rows. Current rollback material is `/opt/rdgen-backups/20260810-103245-d4ec7e498a60`, `/opt/rdgen-previous-20260810-103245-d4ec7e498a60`, and `rdgen-rollback:20260810-103245-d4ec7e498a60`.
- The user-authorized Windows x64 build `RelayPoolTest` used RustDesk `1.4.9`, ID server `120.55.0.199:22116`, and no fixed relay. It completed as UUID `42bd21b0-77d2-4182-9ac9-db6758388754`, database row 40, and GitHub Actions run `31350450912`; all build, MSI, signing, upload, receipt, and finalization steps succeeded.
- Downloaded outputs are `output/relay-client-42bd21b0/RelayPoolTest.exe` (24,463,008 bytes, SHA-256 `eafc6f3d4913a50a8f36c32bc26c066fdbe2df237034859dd1cdf17ebccfc1ea`) and `RelayPoolTest.msi` (24,805,376 bytes, SHA-256 `f1d6d6a545f6b59f70e703a2b650ba1c6af9b57a9b557d8cd8657679e3b90480`). Both report RustDesk `1.4.9` and contain a timestamped self-signature whose public root certificate is not trusted by Windows by default; the PFX/private key remains confidential and must never be distributed.
- Administrative MSI extraction confirmed a complete payload and successfully decoded `custom_.txt`: the ID server is correct, no top-level relay key exists, and `override-settings.relay-server` is present and empty.
- Two real Windows devices then ran this exact portable EXE. hbbr logs showed successful raw pairing on both relay A and relay B across reconnects. With two live connections on A, relay A was stopped at 11:46:42; hbbs removed it from the healthy list, and both clients automatically re-paired through B at 11:47:00, about 18 seconds later.
- Relay A was re-created at 11:47:09 with the original transient-unit user, limits, and hardening. Final verification showed hbbs, A, B, and `rdgen-rdgen-1` active/healthy, generator restart count `0`, both relay addresses back in the healthy pool, and the live session still carried by B. This completes the generated-client phase-one validation; geographic and independent-host resilience remain outside this same-host test.

### Phase-two Intelligent Multi-relay Discovery And Frozen Specification

- After phase-one validation, separated the official OSS capability from the proposed phase-two product: OSS already parses a relay list, performs TCP reachability filtering, rotates healthy nodes, and relies on client reconnect; it does not provide two-peer latency, live capacity, quota, geographic, maintenance, or agent management intelligence.
- Worked through the first-release product choices one question at a time and recorded decisions 0-44 in `MULTI_RELAY_PHASE2_DECISIONS.md`. The user locked a self-hosted model, one custom hbbs with unchanged official hbbr nodes, outbound HTTPS agents, two-peer RTT-sum placement with a per-leg guardrail, bandwidth plus metered/unmetered plans, 50 IPv4 nodes, Windows x64/x86/Linux/Android smart clients, CLI/config-first operations, and a complete specification before production coding.
- Exact source review fixed the implementation baseline to RustDesk client `1.4.9` (`6c578292...`, hbb `7e1c392c...`) and rustdesk-server `1.1.16` (`73523b31...`, hbb `83419b65...`). It also found that the two proto baselines differ, so the server fork must additive-backport the client fields/enums needed for one canonical signing transcript instead of replacing either complete submodule.
- Wrote and froze `MULTI_RELAY_PHASE2_SPEC.md`, covering architecture, additive wire messages and canonical Ed25519 signatures, bounded two-client TCP connect measurement, same-selection/new-UUID relay retries, scheduler gates and score, Mbps/quota accounting, crash-safe traffic journals, secure enrollment/rotation, TLS rollover, forced-offline supervision, SQLite bounds, CLI, native installers, backups, generator integration, release/license gates, and real multi-host/50-node verification.
- Decision 44 resolves the only product-level conflict found during source review: rustdesk-server's pre-existing PeerMap IP persistence remains for registration security, while all newly added smart measurement, scheduling, aggregation, logs, CLI, events, and backups may not persist complete peer IPs or raw per-session measurements.
- Independent protocol, scheduler/accounting, and operations/security reviews iterated until no P0/P1 conflict remained. Important corrections included RequestRelay secure/conn-type binding, old/new-client fallback, new UUID per retry with one signed selection, monitoring-vs-data-plane fallback, bps/Bps consistency, bounded/idempotent accounting, crash-consistent gap markers, WAL limits, endpoint uniqueness, administrator-authorized key rotation, complete trust material, and anti-rollback backup restore.
- This work changed documentation and durable project memory only. No RustDesk client/server/agent production code was written, no artifact or generator workflow was launched, no clean upstream reference was modified, and nothing was deployed or expanded on `120.55.0.199`.

## 2026-08-13

### Phase-two Official-requester Compatibility Specification Correction

- Corrected the frozen compatibility contract after read-only tracing of RustDesk client 1.4.9 and rustdesk-server 1.1.16 wire behavior. An official/old requester has no signed requester identity or initial nonce, and its later unsigned `RequestRelay` arrives on a new TCP connection, so it cannot be safely bound to an anonymous selection.
- Offer-absent requester attempts now explicitly remain on the complete upstream OSS path with no smart probe wait, selection, owner/replay state, or source-IP/NAT alias. The smart-A/old-B direction remains supported through a verifiable unique legacy owner because A supplies the signed admission context.
- Expanded the documented server 1.1.16 additive proto backport to the exact existing client 1.4.9 field numbers needed across initial punch, intranet, response, and relay envelopes. The contract continues to forbid replacing either baseline's complete `hbb_common` submodule.
- This was a specification and project-memory correction only. No client/server/agent/generator source was changed, no build or test workflow was launched, and nothing was deployed or published.

### Phase-two S1 Real Local Integration Milestone

- Completed the first real local-process S1 integration across hbbs, two hbbr processes, target B, and requester A. The verified server version is `f8d1766a9b4393cf179dda976103cde8f26799a7` with tree `493565835e617b2353441e3ce9f8c6ec0d02d6c4`; the verified client version is `2441b53d5667050cc6fe80c1428f18e178311346` with client `hbb_common` `b3183ee848c1566e59737e878a418bbb177dc2bc`.
- Attempt UUID `91a64b5d-dec0-4d90-9782-2e0d2a2b883d` completed in 8.3 seconds. Selected relay R2 recorded exactly one new request and one successful pair, while non-selected R1 recorded zero new requests and zero pairs (`R2 1/1`, `R1 0/0`).
- The local LAN endpoint allowance, rendezvous key-exchange helper, and metrics-availability bridge are feature-gated fixture support only. They do not change the production contract and do not prove a production raw-TCP smart rendezvous closed loop; production validation should prefer strict WSS.
- No change from this milestone was pushed or deployed, and no production system was accessed. The next bounded implementation and verification target is S2: duplicate requests using the same UUID.

### Phase-two S2 Same-UUID Local Integration Milestone

- Completed the bounded S2 duplicate-request integration with server `fa464c262fd3401a6db87dcbe74e7fe3991e0c1b` (tree `0bbf9db7ea43aa1be4986f3963bcc743ec18499b`), client parent `0b997fea0caa69cd4f69d3cfcd6a681d3b7e8992`, and client `hbb_common` `b3183ee848c1566e59737e878a418bbb177dc2bc`.
- The three request lanes shared UUID `0737e04a-77f4-4a84-8bfc-8f0019492b9f`. Their decrypted protobuf frames all had SHA-256 `b362d0f9fe11d8a84fe96243e80ab130d1b81b3b92a0214c35b53d987689e3aa`, demonstrating identical successful final frames for the same request context.
- hbbs recorded exactly one owner, one enqueue, one join, and one replay. Target B recorded one create and one pairing request; requester A recorded one hbbr owner/pairing request. Selected relay R2 recorded one new request and one completed pair, while non-selected R1 remained at zero (`R2 1/1`, `R1 0/0`).
- The run completed in about 9.18 seconds, below the 30-second limit. S1/S2 contract, dry-run, and offline checks passed, and test worktrees/processes were cleaned after verification.
- Nothing was pushed or deployed. The next bounded implementation and verification target is S3: immediate recovery using a different UUID.

### Phase-two S3 Different-UUID Local Integration Milestone

- Completed the final bounded S3 local integration with server HEAD `d34bcaec3b86d89614037df03dffcff43d01ee4f` (tree `a2173c417b968a7dda45e8c1ba2dd230d16d36e7`), client `051a54c23a55c5c76272a09c3b9de0557088a80a`, and client `hbb_common` `b3183ee848c1566e59737e878a418bbb177dc2bc`.
- UUID1 `68c25b4d-f9de-4a4b-a66d-2098b924ec5f` produced response SHA-256 `fbb650ead7c078533bbc1ad7c5e0a6197512d6ff684c6d7cc772413326e0790`; UUID2 `25075eb6-fefd-447c-8bfd-507ec3ad2c37` produced response SHA-256 `12dd0e3fea68f17a045fe97dc12d4fdcab3cc927f819ecdadd8ac5dbc8e34ef1`. The recovery interval was 5 ms, and total run duration was 7,563 ms.
- For each UUID, hbbs owner/enqueue/join/replay was `1/1/0/0`, and target B create/pairing was `1/1`. Requester A was `0/0` for UUID1 and `1/1` for UUID2.
- R1 recorded `0/0` for both UUIDs. R2 recorded `1/0` for UUID1 and `1/1` for UUID2, confirming immediate recovery on the second request identity.
- S1/S2/S3 contract checks and locked server/client offline checks passed. The database was restored after verification, and remaining processes and owned run roots were both zero.
- Nothing was pushed or deployed, and no production system was accessed. The next phase is total integration closeout: merge modules not yet present in integration, resolve the uncommitted handler work, run the full regression suite, and then produce a runnable vertical slice.

## 2026-08-20

### Phase-two Production Integration Closeout

- Consolidated the server production path on `rdsmart/phase2-integration-116`. The current local HEAD is `9ddf237`; important closeout commits include `248cacb` for the separate relay-supervisor UID/IPC composition, `a4e2f0c` for audited drain/force-offline/resume operations and evidence-based convergence, and `9ddf237` for the bounded, sorted, strict read-only node inventory.
- Verified `node list` on Windows and Rocky 8: four focused tests pass on both platforms, local-admin is 27/27, `rdsmartctl` is 16/16, local-admin protocol is 14/14, the Linux `rdsmartctl` binary builds, and packaging shell/static gates pass. The earlier full Linux library run remains 649/684 with 35 environment/security-fixture failures unrelated to the affected paths, so the complete suite is not claimed green.
- The VM already has a valid generation-1 credential and enrolled node. Its controller database is the only authoritative state; the earlier local SQLite copy predates node creation and must never be restored. No agent/hbbr process or local relay listener currently runs. Re-enrollment is both unsafe and rejected while the active credential exists.
- The planned VM run cannot use `1.1.1.1`: that address is not assigned locally, and public reachability caused a false-positive health result. Before an authorized slice, use an actually owned endpoint and remediate controller logging/rotation plus the observed permissive private-key and database modes. No VM deployment, process restart, state deletion, or credential mutation was performed.

### Locked Generator Integration And Verification

- Commit `fd13daf` added the off-by-default `smartMultiRelay` field, migration/history display, exact RustDesk 1.4.9 and supported-platform validation, strict-WSS hostname/API requirements, fixed-relay conflicts, encrypted workflow input staging, true-only Windows x64/x86/Linux/Android workflow steps, and locked production root plus `hbb_common` patches. macOS remains excluded.
- Follow-up `c99801e` added the missing network/lifecycle invalidation bridge and tightened apply/smoke markers. The patch helper pins root `6c578292e8ebbbec708b76986ba8c4bc7c509747` and `hbb_common` `7e1c392c62d39c364127307cd408421dd5f8cfb0`, validates exact patch digests and path sets, rejects partial/repeated/wrong-baseline application, and excludes fixture-only paths and markers.
- Reverification passed all 200 Django tests, Django system checks, migration-drift checks, three workflow contract tests, `actionlint`, and the complete offline enabled/disabled/repeated/wrong-root/wrong-hbb patch smoke. No live form was submitted, no GitHub Actions workflow was dispatched, and nothing was pushed or deployed.
- A final workflow-path review found that the first lifecycle bridge introduced a new `mainNotifyNetworkChanged` FFI method after the reusable bridge job had already generated its artifact from unpatched 1.4.9 source. The subsequent artifact restore would therefore omit that binding and break Flutter compilation. Commit `ab1497e` fixes the issue without a new ABI: lifecycle resume calls the official existing `mainCheckConnectStatus`, whose smart-patched Rust implementation now also rotates the network epoch. The locked digest/path/marker contract, three workflow tests, full offline smoke, and `actionlint` pass after the correction.
- Cleaned large build artifacts after verification: the server default target had already freed about 28.9 GiB, and the final mixed-platform `target-rocky8` cache removed another 20.0 GiB (27,752 files). The temporary 5.4 GiB Rocky 8 target lived only in Docker overlay and was also removed. User data and the pre-existing `db_v2.sqlite3` working-tree change were preserved.

### Real VM Controller, Supervisor, And Agent Vertical Slice

- Pushed generator commits through `34e6e23` to `zhenzhenwq/rdgen`. Push-triggered run `32362878501` failed at Docker Hub login before build/push; production remained on `d4ec7e4`, and no smart client workflow was dispatched. HTTPS still redirects unauthenticated requests to the live login page. Direct root SSH to `120.55.0.199` rejected the supplied password and no workstation SSH key exists for that host.
- Built Rocky 8 release `hbbs`, `rdsmartctl`, `rdsmart-agent`, and `rdsmart-hbbr-supervisor`. The first hbbs correctly refused the authoritative VM DB because the Windows bind mount had converted the SQLx migration files to CRLF. Offline inspection proved that all ten recorded checksums exactly matched LF-normalized source. Commit `03792f3` pins `migrations/smart_relay/*.sql` to LF, and the corrected release then opened the existing schema-10 DB with no migration or data rewrite.
- Before upgrade, gracefully stopped hbbs and created `/opt/rdsmart-slice/backups/pre-9ddf237-20260820T112143Z.tar.gz` (50,070,161 bytes, mode `0600`, SHA-256 `b9cc10e82534fe0b37d8442ba0e7d7ef01ce93c6866e4a314ff9eab5ac750f1d`). The original generation-1 node credential and agent key hashes remained unchanged while state moved to `/var/lib/rdsmart/agent` under its dedicated UID.
- Installed corrected release `03792f3`; active hbbs SHA-256 is `fe90e42f6aafca5971f14683cc0cd5f413d08a9714d7977fb27fd5484986e9f3`. `node list` and `node show` confirmed the original node `35255ea8-658d-4d46-8e98-8fbeac4ce769` with no re-enrollment.
- Created distinct no-login `rdsmart-agent` UID 979 and `rdsmart-relay` UID 980 accounts plus IPC GID 980. Enabled the separate supervisor and agent services. Supervisor socket/state identities are `0660 relay:ipc` and `0600 relay:ipc`; official hbbr is the supervisor's sole child. A real stop gate reaped the child, closed port 24117, removed the socket, preserved durable state, and then rebound with new supervisor/child PIDs.
- Applied audited `node drain` as desired revision 1 and `node resume` as desired revision 2. Two bounded `rdsmart-agent run --max-applied 2` executions exited successfully. Post-gate journal evidence is accepted sequence 12 from the prior 8, next sequence 13, applied and desired revision 2, active mode, normal safety, and no pending report. The permanent agent is enabled/active, a systemd restart completed cleanly, and node inventory reports fresh telemetry.
- Local route and TCP connect to `1.1.1.1:24117` pass because the VM currently owns a local `/32` alias, but the route is local through `lo` and does not prove external ownership/reachability. Firewalld was not expanded. The controller remains a temporary root-run process because the host NSS includes `sss` and the frozen non-root local-admin socket ownership blocker still prevents a production packaging claim.
- Removed both VM upload staging trees, the invalid CRLF release, the expired enrollment artifact (recoverable from the root-only backup), and the temporary bounded unit. Preserved the retired v1 config as `/opt/rdsmart-slice/run.v1-retired-20260820.json`. Both release target directories were cleaned (about 1.4 GiB each), the obsolete local 22 MiB CRLF release was removed, and three unused Docker images were deleted without touching the active Rocky 8 build container.
- Remaining blockers are generator host/registry access, live deployment of `34e6e23`, four smart platform workflow artifacts, and a real hostname plus trusted-certificate strict-WSS requester/target slice. These are not satisfied by the IP-only lab topology or the prior fixture milestones.

## 2026-08-21

### Four Smart Workflows And Production Strict-WSS Slice

- Advanced generator `master` to `5591f33` and synchronized it with `origin/master`. The supported smart Windows x64, Windows x86, Linux, and Android workflows all completed successfully after moving Flatpak construction to modern native runners. This closes the four-workflow compilation gate; it does not by itself prove Windows or Android installation/runtime behavior.
- Retained `D:\rustdesk-生成器\artifacts\validation-20260821\linux-x86_64-deb\RDSmartWss149Live-x86_64.deb` (23,521,216 bytes, SHA-256 `0ba90ac80d850df86b5118899efe6b98fb262752b063754b6be608a1ca76edc3`) as the audited Linux artifact.
- Fixed the server WSS production route through `c861f74` (restore peer registration after restart), `80fe38a` (refresh the peer lease), and `bfb771e` (verified relay routing over WebSocket). Together with `163b1f3`, these commits preserve agent traffic rollups and recover safely from counter resets.
- Completed a real strict-WSS production-client requester/target slice rather than using the S1-S3 magic-handshake fixture. The normal client start/relay path created four established WebSocket data sockets on hbbr port `24119`, sustained them for at least five seconds, completed smart relay selection, returned 1280x720 target information, and initialized the VP9 decoder. Using an X11 target avoided unrelated Wayland capture errors.
- The key deployment contract remains that strict WSS requires a hostname, trusted certificate, HTTPS API endpoint, and hbbr WebSocket data port `base + 2`. The earlier IP-only lab and fixture handshakes remain insufficient proof on their own.

### Audited Traffic Correction Command

- Added the frozen `rdsmartctl node traffic-correct` operation end to end and committed it locally as `29d5376` (`feat: add audited traffic correction command`). The CLI has strict parsing and stable error/output mappings; the local-admin path uses a bounded mutation queue; the Store writes an append-only adjustment with explicit-UUID idempotency and fails closed if the same UUID is reused for a different exact payload.
- Optional accounting-gap correction now updates the linked gap marker and checkpoint atomically with the adjustment. Migration `20260821120000_phase4_traffic_correction_link.sql` advances the schema to 11, records the `gap_marker_id` relationship, adds the bounded uniqueness invariant, and participates in the schema-manifest tamper check.
- Linux `cargo test --locked --no-run` succeeded. Migration-chain and committed-v9 upgrade checks passed, and `cargo test --locked traffic_correction -- --test-threads=1` passed all six protocol/parser/CLI/local-admin/Store/schema-tamper tests. All Store, migration, traffic-correction, and scheduler tests passed.
- A clean dedicated-ext4 full Linux run reported 666 passes and 36 failures. Every failure is in the pre-existing Linux file-identity/enrollment/journal/hbbr fixture baseline, not the traffic-correction paths. The full suite is therefore not green and must not be described as such. `git diff --check` is clean; the only remaining server worktree change is the user's pre-existing `db_v2.sqlite3`, which was preserved.
- The integration branch has no matching origin ref and was not pushed. No current server binary was installed on the VM, and the new command has not mutated the authoritative VM database.

### Disk Cleanup And Safe Lab Pause

- Removed the disposable Rocky test container, image, named ext4 volume, and about 9.8 GiB of `target-rocky8` build cache. Removed only the temporary Docker proxy override fields, retained Docker authentication/context configuration, and stopped Docker Desktop. Final local verification showed about 244 GiB free on `D:`.
- Stopped all explicit candidate hbbs, Cloudflare WSS, and requester/target E2E services on the lab VM. Removed six exact temporary deployment paths, the installed test client, cloudflared and candidate binaries, and the two E2E users/homes after verifying they had no live processes. These disposable artifacts and cleared build caches are not recoverable.
- Preserved the authoritative generation-1 agent credential at `/var/lib/rdsmart/agent/credential.json` (`0600`, `rdsmart-agent`), the agent key/state, and `/opt/rdsmart-controller/state.sqlite3` (`0600`, `root`). The permanent agent and separate hbbr supervisor remain active, and the official hbbr still listens on `24117`/`24119`. Candidate ports `25115`/`25117` are closed, temporary paths/users both count zero, and `hbbs.out` grew zero bytes during the final two-second audit. The VM root filesystem had about 14 GiB free.
- Retained the VM-local `1.1.1.1/32` alias only because the current lab core depends on it. It remains collision-prone, can produce false reachability, and is not suitable for production. The next operational design must use an owned endpoint and a permanent least-privilege controller service with bounded SQL logging/rotation and verified private-key permissions.
- No production host was changed and no server branch was pushed. The next bounded sequence is: address the 36 Linux baseline failures, close controller/logging/address packaging, rebuild the current integration, and—only with explicit authorization—run a VM `--max-applied 2` plus real traffic-correction slice without re-enrolling the existing node.

### Linux Baseline Repair And Boot-Safe Agent Release

- Repaired the complete 36-failure Linux fixture baseline and committed the server integration locally as `974a2a4` (`fix: harden Linux agent state and hbbr cleanup`). The final Rocky 8 dedicated-ext4 run used the exact non-root service HOME and passed all 707 tests with zero failures. A later strengthened exact interface-mismatch/boot-transition test also passed; `git diff --check` is clean. Rustfmt reports only three pre-existing formatting deviations outside the new code.
- A real cold VM boot exposed a production-path Agent defect that the old fixture baseline had hidden: the journal rejected a changed kernel boot ID whenever preserved accounting evidence remained. Commit `6cc7478` (`fix: preserve agent accounting across host reboot`) adds one atomic boot transition that changes only the boot identity/time and raw-counter baseline while preserving the counter epoch, cumulative/preserved totals, report and traffic sequences, minute buckets, and gap markers. It refuses virgin journals, invalid samples, interface mismatches, and pending reports without partial mutation.
- The same full run exposed a clean-stop race in `rdsmart-hbbr-supervisor`: the child could exit between `try_wait` and `/proc/<pid>/fd` inspection, turning a successful SIGTERM into a false `EACCES` failure. The supervisor now reaps once more after observation errors and remains fail-closed only if the child is still live. Nine focused supervisor tests pass, including the vanished-PID case.
- Built stripped Rocky 8 release binaries from a source snapshot whose three modified-file hashes matched the Windows worktree. `rdsmart-agent` is 5,328,488 bytes with SHA-256 `5464491b5a473854d339d81d9d7e6cbbfed1dcdcf9d45e5610318bad0a8115dc`; `rdsmart-hbbr-supervisor` is 752,232 bytes with SHA-256 `b2d2b5a66da7678897fcaef3ea0e7f48399e635fe8d1b99dceca566baab17fdc`. Both require no GLIBC newer than 2.28.

### Authorized Lab Upgrade, Correction Proof, And Reboot Evidence

- Created root-only rollback backup `/var/backups/rdsmart/pre-6cc7478-20260821T091315Z`, installed immutable release `/usr/local/libexec/rdsmart/6cc7478`, and changed only the Agent and supervisor release drop-ins. The controller remains the audited `974a2a4` build. The lab-only address, controller, supervisor, and Agent units are enabled and active; the controller is still root-run and therefore does not close the production least-privilege packaging gate.
- A bounded exact-UID Agent run completed with JSON `ok=true`, `status=applied`, exit 0, and revision 2. Before/after journal inspection with SQLite 3.49 reported integrity `ok`, preserved the accounting epoch, kept cumulative counters and all accepted/next sequences monotonic, retained backlog evidence, left no pending report, and kept safety `normal`. The Agent key and credential remained byte-identical to the pre-upgrade backup.
- Exercised `node traffic-correct` against an isolated metered copy: first application returned changed=true at sequence 319, exact replay returned changed=false, and UUID/payload collision failed with exit 4. The authoritative node uses the unmetered plan, so the same operation correctly failed with exit 2 and did not change authoritative accounting. This proves both mutation semantics and traffic-correct rejection without converting or replacing the authoritative node.
- Completed two consecutive real whole-VM reboots. Boot IDs advanced from `69be83a3-a237-47d5-90b1-3a891cd205cf` to `2091f64d-1873-48bf-94c8-a8556702efd4` and then `a40959b8-92cd-4cc2-879c-906561fa1672`. After each boot all four lab units were enabled/active with zero restarts/failures, ports 24117/24119 were listening, both running binary hashes matched the release, controller telemetry was fresh, and credentials/keys were unchanged. Both post-boot SQLite audits passed integrity and monotonic accounting/sequence assertions with revision 2, normal safety, and zero pending reports.
- Explicitly restarted the new supervisor after boot: systemd recorded one clean deactivation, zero failure records, zero automatic restarts, and both official hbbr listeners returned. This supplies a direct runtime proof for the clean-stop race fix despite the VM using a volatile journal across whole reboots.

### Final Space Cleanup And Safety State

- On the VM, removed only verified disposable staging trees, isolated correction copies, seven local test snapshots, three unreferenced old release directories, stale standalone hbbs output files, DNF metadata, and PackageKit cache. Preserved current releases `6cc7478`/`974a2a4`, rollback releases `03792f3`/`163b1f3`, all `/var/backups/rdsmart` sets, live databases, keys, credentials, and unrelated files. Root usage fell from 63% to 59% and available space rose from about 14 GiB to 15 GiB; all four services and fresh telemetry remained healthy afterward.
- Locally, removed the three Rocky test containers, temporary image, base image, named ext4 volume, all Docker build state, the current test SQLite copies, the one-time rustup installer, the 0.25 GiB Rocky Cargo cache, and stale Codex temp directories. Docker now reports zero images, containers, volumes, and build cache. Stopping Docker Desktop automatically shrank `docker_data.vhdx` from 35.48 GiB to 6.38 GiB, raising C: free space from 27.86 GiB to 57.03 GiB; D: ended near 244.66 GiB free. Manual `Optimize-VHD` was unnecessary and was refused by the current Windows authorization policy without changing the disk.
- Production was not touched, no workflow was dispatched, and neither repository was pushed. Server `rdsmart/phase2-integration-116` ends at local `6cc7478` with only the user's pre-existing `db_v2.sqlite3` modification. Remaining gates are Windows/Android installation/runtime, multi-host three-region behavior, 50-node load, the supported-distribution install/repair/reboot/uninstall matrix, and a production package using an owned endpoint plus a non-root controller with bounded logging and verified key ownership.
