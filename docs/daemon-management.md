# Daemon Management

> Status: draft | Updated 2026-07-05 | Applies to: protocol adapters

AMPG can use daemons that already exist on a server or create AMPG-owned daemons when
the selected protocol is not running. This keeps simple deployments simple while avoiding
surprise edits to operator-owned services.

## Ownership rules

Adopted daemons:

- are already installed and healthy.
- keep their existing service manager and primary config ownership.
- receive generated snippets only after the operator approves the plan.
- are never rewritten wholesale by AMPG.

Managed daemons:

- store config under `state_dir`.
- expose logs and health through AMPG.
- use AMPG-owned ports, sockets, hidden-service dirs, key files, and output roots.
- can be stopped, restarted, or removed by AMPG.

## Discovery order

For each enabled protocol, AMPG checks:

1. Explicit config in `gateway.toml`.
2. AMPG-owned state from previous runs.
3. Common system services and ports.
4. Known config paths for supported daemons.

The result is shown in `ampg status`. `ampg plan` shows rendered outputs and reviewable
config artifacts.

## Preflight commands

```sh
python3 -m ampg --config gateway.toml status
python3 -m ampg --config gateway.toml doctor
python3 -m ampg --config gateway.toml install-plan --profile mobile-i2p
python3 -m ampg --config gateway.toml apply --dry-run
python3 -m ampg --config gateway.toml apply --dry-run --profile mobile-i2p
python3 -m ampg --config gateway.toml apply --dry-run --protocol i2p
python3 -m ampg --config gateway.toml apply --dry-run --write-artifacts
python3 -m ampg --config gateway.toml doctor --platform android-termux
```

`status` prints one row per enabled protocol with the selected platform provider,
adapter, installed/running daemon probe, action, and policy result.

`doctor` checks source paths, renderer support, route exposure, output readiness, and
daemon policy feasibility. It exits nonzero only for errors; missing build output is a
warning so operators can run it before the first build.

`install-plan` prints the package, state-directory, managed-config, supervisor, and
health-check steps needed for AMPG-owned daemons. It is dry-run only. Adopted daemons and
external-policy targets are shown as skipped, while unsupported platform/daemon pairs are
blocked.

`apply --dry-run` prints the activation sequence for each enabled protocol: generated
output readiness, config artifacts to review, daemon action, and post-apply health
checks. It exits nonzero when any step is blocked. `--write-artifacts` writes reviewable
config snippets to the configured plan root but still does not install or reload
services.

`--protocol` scopes operational commands to selected enabled protocols. A clearnet
`adopt` failure will block a full activation run, but it will not block
`apply --dry-run --protocol i2p` because clearnet is outside that selected run.

`--profile` loads named command defaults from `gateway.toml`. Profiles can set selected
protocols, platform provider, and safe artifact-writing defaults. Explicit command-line
flags override profile defaults.

Platform providers describe how AMPG may supervise managed daemons:

- `linux-systemd`: system service management after approval.
- `linux-user`: user-space foreground or user service management.
- `macos-launchd`: user LaunchAgents or foreground processes.
- `android-termux`: Termux-style user-space daemons for mobile/server experiments.
- `unknown`: render and plan only; daemon management is disabled.

Package commands in `install-plan` are review hints, not executed actions. Systemd hosts
currently emit `apt`-style package hints, Termux emits `pkg`, macOS emits `brew`, and
user-space Linux asks the operator to use the local user package manager.

## Adapter notes

### Clearnet

Default daemon: nginx.

AMPG should usually adopt clearnet ingress instead of managing it. Existing TLS,
firewall, and reverse proxy rules are operator-owned. Managed clearnet is useful for
development and single-purpose boxes.

### Tor

Default daemon: Tor.

If Tor is already running, AMPG can add a hidden service snippet that points to the
`privacy-html` local server. If Tor is missing and policy is `auto` or `manage`, AMPG
creates an AMPG-owned Tor instance or service unit and stores hidden-service material
under the AMPG state directory.

### I2P

Default daemon: i2pd.

AMPG first supports server tunnels through i2pd. I2P-Zero can be added as a second
adapter with the same interface. Managed I2P must keep destination keys in AMPG state
and include backup warnings in the plan.

### Gemini

Default daemon: Agate.

Gemini is static-friendly and can be managed safely. AMPG generates `.gmi` output,
certificates when requested, and Agate plan values pointing at the Gemini output root.

### Reticulum

Default daemon: rnsd or a compatible page server.

Reticulum management is split: AMPG can manage generated Micron pages and a page-serving
process, but physical interfaces such as LoRa, serial, packet radio, or custom transports
may require explicit operator setup. `ampg plan` must distinguish page-server readiness
from transport-interface readiness.

## Safety requirements

- Show every config write before applying it.
- Generate snippets into the plan root before any install or reload step.
- Back up any adopted-daemon snippet AMPG touches.
- Never delete hidden-service keys, I2P keys, or Reticulum identities without an explicit
  destructive command.
- Refuse to bind public ports when the selected renderer is not built.
- Health-check every enabled protocol after apply.

## Reusable checklist

- [ ] Adapter detects existing daemon state.
- [ ] Adapter can produce a dry-run plan.
- [ ] Managed config is isolated under AMPG state.
- [ ] Key material is backed up or clearly called out.
- [ ] Health check validates the generated site through the selected transport.
