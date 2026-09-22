# Multi-relay Phase Two Decisions

## Status

- Product discovery is complete; the first-release technical specification is frozen after protocol, scheduler/accounting, and operations/security cross-review.
- The decisions numbered 0–44 below are the authoritative first-release product baseline.
- Any implementation detail that would change one of these decisions must return to the user as a focused decision before coding.

## Verified Baseline

- Phase one confirmed that RustDesk OSS hbbs accepts multiple hbbr addresses, filters unhealthy nodes, and selects a healthy relay for each session.
- The generator now leaves relay selection under hbbs control by emitting an empty `override-settings.relay-server`; one explicit fixed relay remains available as an advanced option.
- The generated `RelayPoolTest` Windows client used both test relays and automatically re-paired through relay B about 18 seconds after active relay A was stopped.
- Phase one proves server-managed selection and reconnect-on-failure. It does not provide geographic, latency-aware, load-aware, capacity-aware, or seamless in-session migration.

## Decision Log

### 0. Phase-two Capability Target

- Decision: build an intelligent multi-relay layer rather than stopping at productization of the official OSS multi-relay behavior.
- Status: locked by the user after explicitly reviewing the distinction.
- Existing OSS behavior remains the foundation: configured relay lists, TCP health filtering, round-robin selection, and reconnect-on-failure will not be unnecessarily reimplemented.
- Phase-two custom work targets capabilities missing from OSS: geographic or latency-aware placement, load and capacity awareness, node maintenance controls, secure node enrollment, operational visibility, and a manageable self-hosted product experience.
- Monitoring-agent reports supplement the existing hbbs TCP health check with load and capacity data; they do not replace basic relay reachability checks.
- The previously settled decisions 1 through 6 remain applicable to this intelligent self-hosted design.

### 1. Product Delivery Model

- Decision: self-hosted deployment for each customer.
- Status: locked by the user.
- Customer owns and operates the ID server and relay nodes and bears the associated bandwidth, infrastructure, and remote-session data responsibilities.
- The product will not depend on a shared vendor-operated rendezvous or relay network.
- Product work must prioritize repeatable installation, secure configuration, upgrades, health visibility, backup, and diagnostics for customer-operated infrastructure.
- A centralized multi-tenant relay control plane, shared traffic billing, and shared-customer data isolation are outside the current phase-two scope.

### 2. Server Implementation Boundary

- Decision: modify hbbs, keep the official hbbr binary, and run a lightweight monitoring agent beside each hbbr node.
- Status: locked by the user.
- The custom hbbs owns relay registration, health state, metrics ingestion, scoring, and final relay selection.
- The official hbbr data path remains unchanged, reducing the long-term cost of tracking upstream RustDesk server releases.
- A bundled node agent reports heartbeat, connection, bandwidth, and host-load signals to hbbs through an authenticated channel.
- The deployment and upgrade system must version the custom hbbs and monitoring agent while checking compatibility with the selected official hbbr release.
- External DNS or generic load balancing will not be used as the relay selector because both session endpoints must reach the same hbbr instance.

### 3. Rendezvous-server Topology

- Decision: the first phase-two release supports one custom hbbs with multiple hbbr nodes.
- Status: locked by the user.
- Relay-node redundancy and intelligent selection are in scope; hbbs high availability is not part of the first release.
- Registry, metrics, scheduler state, and administration can remain local to one hbbs deployment, with no distributed consensus or shared control-plane database.
- The internal registry and selector should still use clean interfaces so a future primary/standby or multi-hbbs design does not require rewriting the scheduling core.
- Documentation must state that relay failure is covered while hbbs remains a single point of failure in this release.

### 4. Relay-node Enrollment

- Decision: administrators pre-create each relay node and enroll its monitoring agent with a single-use connection code.
- Status: locked by the user.
- The plaintext enrollment code is shown only when created, expires after a short period, works once, and is stored by hbbs only as a secure digest.
- After successful enrollment, hbbs issues a unique long-lived credential for that node; relay nodes never share one global secret.
- Administrators can revoke or rotate one node credential without interrupting other relays.
- The issued credential is limited to that node's heartbeat and metrics operations and does not grant general hbbs administration rights.
- Re-enrollment after credential loss or node replacement requires a newly generated one-time code.

### 5. Agent Network Direction

- Decision: each monitoring agent initiates its connection to hbbs.
- Status: locked by the user.
- Relay nodes expose no new inbound management port; they only need outbound access to the configured hbbs management endpoint.
- Heartbeat and metrics transport must use TLS and the node-specific credential issued during enrollment.
- hbbs marks a node stale when reports stop arriving; the agent retries with bounded exponential backoff after network failures.
- Any future configuration response or maintenance instruction must travel over the same agent-initiated exchange rather than requiring hbbs to open a new connection to the relay host.

### 6. Agent Reporting Pattern

- Decision: the agent sends short periodic HTTPS reports rather than maintaining a continuous connection.
- Status: locked by the user.
- Each report is independently authenticated, bounded in size, safe to retry, and acknowledged by hbbs.
- The stateless request pattern must work through a conventional Nginx reverse proxy and recover without connection-session restoration.
- hbbs may return a small configuration version or maintenance response with the acknowledgement, but the first release does not require a bidirectional command channel.
- Reporting interval, missed-report threshold, retry schedule, and metric payload are engineering parameters to be selected through failure and load testing.

### 7. Reporting Reliability

- Requirement: a single failed or delayed metrics report must never make a relay node unusable.
- Status: reliability behavior is locked by the user; exact retry timing is delegated to implementation validation.
- The agent must retry failed HTTPS reports automatically instead of waiting for manual intervention.
- hbbs must distinguish metrics-channel freshness from the existing relay TCP reachability check and from active data-plane sessions.
- Existing relay sessions must not be terminated merely because monitoring reports are delayed or missing.
- A recovered agent must return to normal reporting and scheduling eligibility automatically.
- Decision 7A: when metrics become stale while the relay remains TCP-reachable, stop assigning new sessions to that node.
- Status of decision 7A: locked by the user.
- Existing sessions continue undisturbed, and the node automatically becomes eligible for new sessions after a fresh authenticated report is accepted.
- A metrics-stale node remains operationally distinct from a TCP-unhealthy node so the UI and diagnostics report the correct cause.
- Architecture correction: the existing hbbs TCP reachability check remains authoritative for whether a relay is usable. Agent telemetry never replaces this check and can never classify a TCP-healthy relay as failed.
- Agent data answers only which reachable relay is preferable. While fresh-metrics alternatives exist, a stale-metrics node is excluded from intelligent placement as selected in decision 7A.
- If the intelligent layer cannot produce any candidate because all metrics are stale or the metrics subsystem is unavailable, hbbs must automatically select from its existing TCP-healthy relay pool using the official baseline behavior. A monitoring-plane failure must never reduce remote-control availability below the OSS baseline.
- This fallback is an engineering availability invariant rather than an optional product mode.

### 8. Scheduling Objective And Node Capacity Inputs

- Decision: optimize for connection speed and remote-control quality first.
- Status: locked by the user.
- "Speed first" does not mean blindly choosing the lowest-latency node. The selector must also avoid saturated links and protect finite monthly traffic allowances because both directly affect session quality and operating cost.
- Each relay node must support administrator-configured bandwidth capacity in Mbps.
- Bandwidth and monthly traffic are not two mandatory simultaneous limits. Node setup must first select the provider-plan model and show only the relevant controls.
- An unmetered fixed-bandwidth node configures its sustained bandwidth capacity and has no monthly-traffic penalty or cutoff.
- A metered traffic-package node configures both its available/peak bandwidth and its monthly traffic allowance.
- The agent must report current bandwidth utilization and cumulative traffic usage so hbbs can calculate bandwidth headroom and remaining monthly traffic.
- A fixed 20 Mbps node represents limited sustained throughput even if its monthly traffic is abundant. A 300 Mbps node with a 1 TB monthly allowance represents strong burst performance but scarce monthly capacity. These nodes must not receive identical placement treatment.
- Among eligible nodes, latency remains the primary experience signal; bandwidth headroom and remaining monthly allowance constrain or penalize selection.
- Billing-period progress and projected exhaustion may be displayed for planning, but decision 37 forbids using remaining days to dynamically change placement priority.
- Exact latency measurement, traffic accounting direction, billing-cycle reset, reserve thresholds, and score weights remain separate decisions.

### 9. Monthly-traffic Protection

- Decision: use progressive monthly-traffic protection for metered nodes, with administrator-customizable thresholds.
- Status: locked by the user.
- As usage crosses configured warning and reserve thresholds, intelligent placement progressively lowers that node's priority.
- At the configured exhaustion threshold, the node accepts no new sessions; existing sessions are not forcibly terminated.
- Sensible defaults will be provided, but thresholds can be customized per node to match the provider plan and the customer's tolerance for overage.
- This policy is disabled for fixed-bandwidth unmetered nodes.

### 10. Metered-traffic Direction

- Decision: configure traffic-counting direction independently for each metered relay node.
- Status: locked by the user.
- Supported accounting modes are outbound-only and combined inbound-plus-outbound traffic.
- The agent always reports inbound and outbound counters separately; hbbs applies the selected provider-billing rule instead of discarding either raw direction.
- Keeping both raw counters permits later policy changes and accurate diagnostics without pretending all cloud providers bill traffic identically.
- The node UI must explain the two modes in provider-oriented language rather than requiring users to understand network-interface terminology.

### 11. Dedicated Relay Hosts

- Decision: the first phase-two release requires each relay node to be a dedicated server.
- Status: locked by the user.
- A supported node runs the official hbbr binary, the monitoring agent, and necessary operating-system components only; unrelated websites, databases, proxies, or application workloads are outside the supported topology.
- Whole-host CPU, memory, and network measurements can therefore represent relay capacity without attempting unreliable per-process attribution.
- Installation preflight and documentation must detect or warn about conflicting listeners and material unrelated workloads instead of silently claiming accurate scheduling data.
- Small operating-system management traffic may still make local counters differ slightly from provider billing; the UI must not claim byte-for-byte cloud-invoice equivalence.

### 12. Traffic Billing Cycle

- Decision: configure the billing-cycle reset schedule and timezone independently for every metered relay node.
- Status: locked by the user.
- The node configuration stores an explicit monthly reset rule and named timezone rather than assuming the first day of the month or the hbbs machine's local clock.
- Traffic usage, remaining allowance, protection thresholds, and projected burn rate are evaluated within that node's own billing period.
- Counter resets must be persisted and auditable so hbbs or agent restarts cannot reset monthly usage accidentally.
- Changing a live node's reset schedule requires an explicit confirmation and audit entry because it changes quota calculations.
- Calendar edge cases will use an unambiguous supported rule, such as valid fixed days plus a last-day option, rather than silently shifting invalid dates.

### 13. Mid-cycle Traffic Baseline

- Decision: when a metered node joins mid-cycle, an administrator manually enters the traffic already used in the current billing period.
- Status: locked by the user.
- The agent and hbbs add newly observed traffic to this baseline instead of incorrectly starting the provider allowance at zero.
- The baseline must be nonnegative, must be displayed with its unit and effective timestamp, and must warn when it already exceeds configured thresholds or allowance.
- Administrators can make later audited corrections for provider/local-counter differences; corrections never silently rewrite history.
- Cloud-provider API credentials and vendor-specific usage integrations are outside the first-release scope.

### 14. Client-assisted Latency Signal

- Decision: modifying generated RustDesk clients and extending the rendezvous exchange for real candidate-relay latency measurement is allowed.
- Status: locked by the user and explicitly supersedes the earlier server-estimation-only choice.
- hbbs-side observation of public IP, geolocation, ASN, and historical path quality remains useful context, but it is not a substitute for client-to-relay measurement.
- Modified clients may receive a bounded candidate-relay set, measure it safely, and return authenticated results for the scheduler.
- Direct hbbs or hbbr ICMP probing of arbitrary peer IPs is not the primary method because NAT, carrier-grade NAT, firewalls, and ICMP filtering make it unreliable and create avoidable privacy/abuse concerns.
- Exact probe transport, measurement frequency, candidate limit, result lifetime, and compatibility behavior for unmodified clients remain separate decisions.

### 15. Two-peer Latency Objective

- Decision: choose the eligible relay with the lowest combined latency from both session peers while enforcing a per-peer quality guardrail.
- Status: locked by the user.
- The scheduler minimizes the sum of both peers' valid candidate-relay measurements rather than optimizing only the controller or only the slower peer.
- A relay whose measurement for either peer exceeds the configured quality ceiling is penalized or rejected so a low total cannot hide one unusably poor path.
- Bandwidth headroom, monthly-traffic policy, health, maintenance state, and capacity gates are applied before or alongside the latency ranking; low latency cannot override an exhausted or unavailable node.
- Missing, stale, or inconsistent measurements require a defined compatibility fallback rather than silently treating zero or missing data as the best result.

### 16. Client Backward Compatibility

- Decision: retain connection compatibility with official and older clients that do not implement candidate-relay measurement.
- Status: locked by the user.
- Relay-measurement support is an optional negotiated capability, not a requirement for registering with hbbs or establishing a session.
- When both peers support measurement, the scheduler uses both real result sets.
- Direction matters because only requester A can supply the signed admission context. When smart A supplies a valid signed offer and B is official/old, hbbs may combine A's real results with a conservative estimate for B; it may send B additive fields that B ignores and may inject the cached signed selection back to A only through a verifiable unique legacy owner.
- When requester A is official/old, its offer is absent. Even if B advertises smart capability, hbbs immediately uses the complete upstream OSS flow: no smart probe wait, no selection, no smart owner/replay state, no guaranteed intelligent placement, and the later unsigned relay remains unbound to a selection.
- When neither peer supports measurement, hbbs likewise retains the complete OSS flow without added intelligent delay or state.
- Missing capability or measurement data never becomes a zero-latency score and never causes an otherwise compatible official client to be rejected.
- Protocol changes must remain additive and versioned so older protobuf implementations safely ignore unknown fields.
- Security rationale: the official 1.4.9 requester wire has no requester identity or initial origin nonce, and its later unsigned `RequestRelay` uses a new TCP connection. hbbs therefore cannot safely associate that request with an anonymous selection; source-IP/NAT-route, target-only, or endpoint-only indexes are forbidden because they collide for shared NAT/proxy users and do not prove requester identity.

### 17. Client Measurement Timing

- Decision: use a hybrid background-cache and connection-time refresh model.
- Status: locked by the user.
- Modified clients maintain a low-frequency, bounded cache of recent candidate-relay measurements while active.
- A material network change invalidates incompatible cached results; stale or missing results trigger a short bounded refresh when a connection starts.
- Measurement timeout never blocks remote control indefinitely. The scheduler falls back to still-valid cached data, server estimates, or the compatible OSS baseline.
- hbbs prefilters unhealthy, exhausted, maintenance, and clearly unsuitable relays before sending a small candidate set, preventing every client from probing an unbounded node list.
- Candidate limit, cache lifetime, refresh deadline, retry count, jitter, and mobile power/network safeguards are implementation parameters to be validated rather than product decisions.

### 18. Client Platform Scope

- Decision: the first intelligent-relay client release covers Windows x64, Windows x86, Linux, and Android; macOS is excluded.
- Status: locked by the user.
- Shared Rust/protobuf code should implement capability negotiation, candidate handling, measurement, caching, and result reporting once wherever the upstream architecture permits.
- Platform release gates still require real builds and connection tests for Windows x64/x86, supported Linux packaging, and Android because lifecycle, background-network, and power constraints differ even when the core is shared.
- Android measurement must remain bounded and respect metered-network and background-execution constraints.
- macOS receives no phase-two client investment while the current output lacks a practically usable trusted signing/notarization path; compatible basic server behavior remains available to unmodified clients.

### 19. Generator Exposure

- Decision: expose intelligent multi-relay support as an explicit generator option rather than silently including it in every build.
- Status: locked by the user.
- Supported platform forms receive a dedicated "enable intelligent multi-relay" control; macOS does not expose it in the first release.
- Enabled builds include and activate capability negotiation, candidate measurement, caching, and authenticated result reporting.
- Disabled builds retain the current server-managed OSS relay behavior without intelligent client measurement.
- The option participates in backend validation, encrypted build inputs, configuration export/import, build-history summaries, and regression coverage rather than existing only as a cosmetic browser toggle.
- Default state, server-compatibility validation, and membership/product entitlement remain separate decisions.

### 20. Generator Default State

- Decision: the intelligent multi-relay option is off by default for every new build configuration.
- Status: locked by the user.
- Users must explicitly opt in after deploying or selecting a compatible intelligent hbbs service.
- Legacy POSTs and imported configurations that do not contain the new field remain disabled rather than being silently migrated to enabled.
- Platform switching and form resets must not accidentally enable the option.
- Help text must distinguish this optional intelligent layer from the already-supported OSS server-managed multi-relay behavior.

### 21. Generator Compatibility Check

- Decision: perform a best-effort smart-hbbs compatibility check and show a clear warning when compatibility cannot be confirmed, but allow the build to continue.
- Status: locked by the user.
- The check is advisory because private networking, firewall policy, or a temporary outage can make a compatible customer server unreachable from the hosted generator.
- Runtime capability negotiation is authoritative. An unsupported or unresponsive smart extension falls back to compatible basic relay behavior instead of breaking remote control.
- The build record stores the warning outcome without falsely recording the server as permanently incompatible.
- Any server-side probe must use strict timeouts, response-size limits, redirect restrictions, public-address validation, and DNS-rebinding/SSRF defenses; it never sends deployment or administrator credentials.
- Users can explicitly retry the compatibility check before submission.

### 22. First-release Management Surface

- Decision: keep the first release simple with command-line and configuration-based management; add the customer-facing API and web interface later.
- Status: locked by the user.
- The first release does not depend on the hosted generator as a relay control plane and does not include a customer node-management website.
- Supported commands must cover node creation, one-time enrollment-code generation, listing/status, capacity and traffic-plan configuration, maintenance/disable, credential rotation, and removal without requiring direct database edits.
- Human-readable output is accompanied by stable machine-readable JSON so a later API layer can call the same service operations rather than duplicating business logic.
- Configuration validation, audit records, and authorization boundaries live below the future API/UI layer from the beginning.
- API authentication, remote management, and web design are explicitly deferred to a later user-requested phase.

### 23. Native Linux Installation

- Decision: ship native Linux one-command installers and persistent systemd services; Docker Compose is outside the first release.
- Status: locked by the user.
- Separate controller and relay-node installation flows deploy the custom hbbs/CLI and the official hbbr/monitoring agent respectively.
- Native services run under dedicated least-privilege accounts, store state in documented persistent locations, and use explicit systemd resource and security hardening.
- Preflight checks verify architecture, supported distribution, ports, dedicated-host assumptions, time synchronization, disk space, and conflicting services before mutation.
- Enrollment secrets are accepted through a protected interactive/file mechanism rather than exposed in process arguments or shell history.
- Packages or release archives require checksums and version metadata; clean install, repair, status, and uninstall are part of the first-release installer contract.
- Installed state is separated from versioned binaries so upgrade and rollback can be designed later under decision 40 without rebuilding the storage model.
- Firewall changes are displayed and scoped to exact required ports instead of silently opening broad ranges.

### 24. Supported Linux Distributions

- Decision: support both the Debian/Ubuntu family and the RHEL 9-compatible family in the first native installer release.
- Status: locked by the user.
- Verified targets are Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Debian 12, Rocky Linux 9, AlmaLinux 9, and CentOS Stream 9.
- The installer uses the appropriate apt or dnf path, verifies systemd and required runtime capabilities, and fails clearly on unverified distributions instead of silently applying a near-match.
- First-release verification includes clean install, repair, service restart, reboot persistence, and uninstall checks for both package-manager families.
- Upgrade, migration, and rollback workflow verification is deferred with decision 40.
- Distribution-specific firewall tooling is handled explicitly while preserving an administrator's existing unrelated rules.

### 25. Server CPU Architecture

- Decision: the first controller, official-hbbr bundle, and monitoring-agent release supports x86_64/AMD64 only.
- Status: locked by the user.
- The installer rejects unsupported architectures before downloading or modifying services and does not rely on emulation.
- Build and release verification produce architecture-labelled checksummed artifacts for x86_64.
- ARM64 and older ARM server architectures are deferred; this decision does not reduce the previously selected Windows x64/x86, Linux-client, or Android-client scope.

### 26. Relay Location And Network Metadata

- Decision: automatically identify relay location/provider metadata from its public IP and allow administrators to correct or enrich the result.
- Status: locked by the user.
- Automatic data includes country, region, city, provider/ASN, and any safely inferable network context.
- Administrators can override incorrect geography and attach controlled line tags such as Telecom, Unicom, Mobile, or BGP for candidate prefiltering.
- Detected values and administrator overrides are stored separately and changes are audited, so refreshes never silently erase deliberate corrections.
- A public-IP change triggers re-detection and a review warning rather than automatically trusting stale location metadata.
- Client-reported real measurements remain authoritative for final latency ranking; metadata narrows the candidate set and supplies compatibility fallback context.

### 27. Single Bandwidth-capacity Value

- Decision: configure one usable bandwidth-capacity value per relay node rather than separate inbound and outbound limits or automatic speed tests.
- Status: locked by the user.
- The configured Mbps value represents the node's effective contracted bottleneck, not the NIC link speed or an optimistic provider marketing value.
- The agent still reports inbound and outbound live throughput separately for diagnostics.
- Scheduling uses a conservative utilization calculation against the single configured capacity so a saturated direction cannot be hidden by averaging it with an idle direction.
- Help text explains that administrators should enter the practical limiting bandwidth when the provider is asymmetric.
- Automatic bandwidth speed tests are outside the first release because they consume traffic, perturb live sessions, and may trigger provider throttling.

### 28. Live-bandwidth Protection

- Decision: apply progressive live-bandwidth protection with administrator-customizable thresholds per node.
- Status: locked by the user.
- Rising sustained utilization progressively lowers placement priority; a configured near-saturation threshold pauses new sessions on that node.
- Existing sessions are never forcibly terminated solely because the bandwidth threshold is crossed.
- The agent and scheduler use bounded rolling averages rather than reacting to a single short spike.
- Separate entry and recovery thresholds plus a minimum stable period provide hysteresis and prevent rapid eligibility flapping.
- Defaults are supplied, while node-specific overrides accommodate different provider shaping and desired quality reserves.

### 29. No Concurrent-session Cap

- Decision: do not configure or enforce a maximum concurrent-session count per relay node.
- Status: locked by the user.
- Session count is not a reliable capacity proxy because idle, low-resolution, and high-motion/high-resolution sessions consume very different resources.
- The agent may still report an approximate active-connection/session count for diagnostics and future APIs, but it does not become a hard placement gate or an administrator-required field.
- Latency, sustained bandwidth utilization, monthly-traffic policy, reachability, maintenance state, and later-decided host-health safeguards determine placement.
- The scheduler must not derive and enforce an arbitrary session cap from configured Mbps.

### 30. Host-resource Safety Guard

- Decision: sustained dangerous CPU or memory pressure pauses new placement, but normal CPU/memory levels do not participate in routine relay scoring.
- Status: locked by the user.
- Bandwidth and latency remain the primary quality signals; a lightly lower CPU percentage does not outweigh a materially better network path.
- CPU and memory protection use sustained windows, entry/recovery hysteresis, and conservative defaults rather than reacting to one sample.
- Existing sessions are not terminated solely because a host-resource guard activates.
- A protected node automatically becomes eligible after resource pressure clears and remains stable for the configured recovery period.
- Metrics and protection reason remain visible in CLI/status output for later API integration.

### 31. Maintenance And Forced Offline Modes

- Decision: provide both graceful drain and explicit forced-offline operations.
- Status: locked by the user.
- Graceful drain is the default maintenance action: the node immediately stops receiving new sessions while existing sessions continue until they end naturally.
- Forced offline is a separate high-impact command that disconnects current sessions and requires explicit confirmation and a stated reason.
- Maintenance state, drain progress, active-connection diagnostics, actor, reason, and timestamps are included in audit and machine-readable status output.
- Returning a node to service requires successful reachability and fresh required metrics; it does not bypass health or capacity gates.
- Maintenance operations use graceful drain by default and never silently select forced offline; a future upgrade workflow must preserve the same rule.

### 32. Domain-optional Encrypted Deployment

- Decision: a customer domain is optional; public-IP deployments are supported without allowing plaintext management traffic.
- Status: locked by the user.
- The controller installer creates a deployment-specific certificate identity when no administrator-supplied trusted certificate is available.
- The protected one-time enrollment bundle conveys the expected controller address, the complete trust material needed to verify it, and that material's fingerprint; agents recompute/pin the identity before sending credentials or metrics.
- Administrators may use a domain and publicly trusted certificate, but this is an optional replacement path rather than a prerequisite.
- Certificate rotation supports an authenticated overlap/rollover procedure so agents are not stranded or taught to disable verification.
- Insecure verification bypasses and plain HTTP enrollment/metrics modes are not supported.

### 33. Peer-IP And Measurement Privacy

- Decision: do not persist complete peer public IP addresses after the active scheduling operation.
- Status: locked by the user.
- Raw peer IPs and opaque per-session measurement sets exist only for the bounded time needed to authenticate, match both peers, choose a relay, and diagnose the immediate transaction in memory.
- Durable optimization data is aggregated by coarse location, ASN/provider, relay, time bucket, and quality distribution without retaining a reversible full-IP key.
- Logs, CLI output, audits, and future API responses redact peer addresses by default and never expose raw measurement payloads unnecessarily.
- Aggregation requires minimum sample thresholds and bounded retention so a low-volume bucket cannot trivially identify one user.
- This privacy choice does not remove node IPs, administrator identities, or operational node metrics, which are infrastructure data rather than peer-session IP history.
- Decision 44 clarifies that this rule governs the new intelligent module; it does not rewrite rustdesk-server 1.1.16's pre-existing PeerMap registration-security storage.

### 34. Deferred Notifications And API

- Decision: keep first-release operational reporting simple and defer outbound notifications, the management API, and the web administration interface.
- Status: locked by the user and reinforces decision 22.
- The first release provides structured local logs, machine-readable status commands, and a minimal internal event record for node health, stale metrics, capacity guards, traffic thresholds, maintenance, and certificate state.
- It does not send SMTP mail or webhooks and does not expose a remote customer-management API.
- Event types, stable reason codes, timestamps, severity, and structured payload boundaries are designed now so a later API/backend integration can consume them without rewriting scheduling logic.
- Further notification-channel and management-UI questions are deferred until the user explicitly starts the API/backend phase.

### 35. RustDesk Client Version Scope

- Decision: the first intelligent multi-relay build option supports RustDesk client version 1.4.9 only.
- Status: locked by the user.
- Windows x64/x86, Linux, and Android intelligent builds all target the same verified 1.4.9 protocol and source baseline.
- Other generator versions and nightly retain compatible basic OSS multi-relay behavior but cannot enable the intelligent-measurement option.
- UI visibility and backend validation enforce the version boundary; an imported unsupported configuration receives an explicit error rather than silently dropping or pretending to apply the feature.
- Adding a later stable RustDesk version requires an explicit source compatibility review, patch/update path, real platform builds, and protocol fallback tests.

### 36. rustdesk-server Baseline

- Decision: base the first custom intelligent hbbs release on official stable rustdesk-server 1.1.16.
- Status: locked by the user.
- The verified 1.1.16 OSS relay-list, health-filtering, round-robin, and reconnect behavior remains the compatibility baseline.
- The official 1.1.16 hbbr data path remains unmodified; custom work is concentrated in the 1.1.16 hbbs fork and the separate monitoring agent.
- Development master/1.1.17 is reference material only and is not shipped as the first production baseline.
- Upstream security and stable-release updates require deliberate review, porting, regression tests, and a versioned upgrade rather than automatically tracking master.

### 37. Fixed Monthly-traffic Thresholds

- Decision: monthly-traffic placement uses administrator-configured fixed usage thresholds and does not dynamically pace consumption against elapsed billing-period time.
- Status: locked by the user.
- The progressive warning, priority reduction, reserve, and exhaustion thresholds selected in decision 9 remain the controlling policy.
- Billing-period progress, remaining days, current burn rate, and an estimated exhaustion date may be shown in structured status for planning, but they do not silently alter placement priority.
- This keeps scheduling behavior predictable and directly tied to values the administrator configured.

### 38. Latency-quality Degradation

- Decision: if every otherwise eligible relay exceeds the per-peer latency guardrail, still connect through the candidate with the lowest two-peer combined latency.
- Status: locked by the user.
- The guardrail influences normal ranking and prevents one bad leg from being hidden when better candidates exist, but it is not an availability kill switch.
- A no-good-candidate session receives an explicit degraded-quality reason in structured operational data rather than pretending the quality target was met.
- Missing measurement and genuinely high measured latency remain distinct fallback reasons.
- Default latency guardrails are supplied and can be adjusted through the first-release configuration/CLI.

### 39. No First-release Runtime License Check

- Decision: the first self-hosted intelligent hbbs and monitoring-agent release has no runtime license activation or call-home requirement.
- Status: locked by the user.
- Access to release downloads may be controlled by the hosted generator's existing membership/download permissions, but deployed software continues operating independently after installation.
- Forwarded installation artifacts cannot be technically restricted in the first release; documentation must not claim otherwise.
- Offline signed licenses, hardware/deployment binding, account activation, and recurring online entitlement checks are deferred with the later API/backend phase.
- Distribution of modified OSS components still requires a separate license-compliance review before commercial publication; the absence of a runtime license does not remove upstream obligations.

### 40. Upgrade Workflow Deferred

- Decision: do not design or implement the installed-software upgrade workflow before the first intelligent-relay version exists and is validated.
- Status: explicitly deferred by the user.
- First development focuses on a clean installation, core protocol, measurements, metrics, scheduling, configuration, and repeatable validation.
- Release artifacts still carry explicit versions and checksums, and persistent state stays separated from binaries so a later safe upgrade design remains possible.
- Automatic updates, maintenance windows, migration orchestration, and rollback UX will be decided only after the working first version.
- This later decision supersedes any earlier wording that could be read as requiring a first-release upgrade or rollback workflow; it does not weaken artifact versioning, state separation, repair, or uninstall requirements.

### 41. Per-deployment Relay Scale

- Decision: support and validate up to 50 registered relay nodes behind one first-release hbbs deployment.
- Status: locked by the user.
- Health, metrics ingestion, state updates, and scheduling data structures must remain bounded and responsive at 50 nodes with the selected periodic reporting model.
- hbbs applies hard eligibility gates and metadata prefiltering before sending a small bounded candidate set; clients never probe all 50 nodes for one connection.
- Test coverage includes 50-node heartbeat/metrics load, mixed healthy/stale/maintenance/capacity states, concurrent scheduling, and deterministic fallback behavior.
- Counts beyond 50 are rejected or clearly unsupported in the first release rather than silently operating without a capacity guarantee.

### 42. IPv4-only First Release

- Decision: the first intelligent controller, relay-node, and client-candidate protocol supports IPv4 only.
- Status: locked by the user.
- Public IPv4 literals and hostnames that resolve to usable IPv4 addresses are accepted; IPv6 literals and AAAA-only names receive an explicit unsupported-version error.
- Candidate measurement, address normalization, enrollment metadata, reachability checks, firewall guidance, and compatibility tests use one unambiguous IPv4 path.
- Internal address types and protocol versioning must avoid assumptions that make a later dual-stack extension require a destructive schema rewrite.

### 43. Specification Before Implementation

- Decision: produce and review the complete technical specification, protocol design, implementation milestones, default engineering parameters, and verification plan before writing production code.
- Status: locked by the user.
- Specification work may resolve internal engineering details, but it must not silently change any locked product decision.
- Any real conflict discovered between locked decisions is documented and returned to the user as one focused decision rather than hidden in implementation.

### 44. Scope Of Peer-IP Non-persistence

- Decision: apply peer-IP non-persistence to the new intelligent measurement, scheduling, aggregation, logging, CLI, event, and backup data only; retain rustdesk-server 1.1.16's existing PeerMap behavior.
- Status: option 1 locked by the user.
- Source finding: rustdesk-server 1.1.16 already persists peer IP in its upstream `PeerMap` database for registration and IP/public-key change checks. This predates and is separate from the phase-two measurement/scheduling store.
- The custom fork must not add raw peer IP copies to the intelligent SQLite, aggregate keys, logs, CLI, events, backups, or probe history.
- Removing or redesigning upstream PeerMap IP persistence is outside the first release and would require a separate registration-security and migration design.

## Discovery Result

There are no pending first-release product questions. Exact source review resolved the PeerMap privacy boundary in decision 44 and later corrected the directional compatibility contract in decision 16: unsigned official/old requesters remain fully OSS, while signed smart requesters retain the smart-to-old target compatibility owner.
