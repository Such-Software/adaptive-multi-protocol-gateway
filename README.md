# Adaptive Multi-Protocol Gateway

> Status: draft | Updated 2026-07-07 | Applies to: AMPG contributors and operators

Adaptive Multi-Protocol Gateway, or AMPG, turns one canonical site into transport-appropriate
published versions for clearnet web, Tor onion services, I2P, Gemini, IPFS, and
Reticulum.

The first use case is practical: start from an existing clearnet static site such as
`wownero.org`, keep the rich web version intact, and generate privacy-hardened or
low-bandwidth variants with sensible defaults.

## Goals

- Start from real sites, including static HTML/CSS/JS trees, not only new Markdown projects.
- Produce protocol-specific builds from one source graph.
- Strip active browser behavior by default on anonymity networks.
- Manage selected protocol daemons when no suitable daemon is already running.
- Stay operator-friendly: every generated config can be inspected before it is applied.

## Non-goals for v1

- Full dynamic SaaS hosting across every transport.
- Replacing Tor, i2pd, Caddy, Agate, or Reticulum.
- Managing blockchain daemons as part of the core gateway.
- Guaranteeing feature parity between rich web pages and constrained transports.
- Exposing private admin, worker, webhook, or payment-internal surfaces by default.

## Operating model

AMPG has two responsibilities:

1. Build transport-specific site outputs.
2. Connect those outputs to selected protocol ingress points.

For each enabled protocol, AMPG follows a daemon policy:

- `external`: render files and config snippets only.
- `adopt`: use an existing daemon, and fail if none is healthy.
- `manage`: create and supervise an AMPG-owned daemon instance.
- `auto`: adopt an existing healthy daemon when possible; otherwise manage one.

The default for selected non-clearnet protocols is `auto`.

## Target workflow

```sh
python3 -m ampg --config gateway.toml init site wownero \
  --domain wownero.org \
  --source ../wownero.org-website \
  --preset full

python3 -m ampg --config gateway.toml deploy plan --profile vps-full
python3 -m ampg --config gateway.toml dns plan --mode dynamic --behind-router
python3 -m ampg --config gateway.toml dns plan --free-domain-hints
python3 -m ampg --config gateway.toml build
python3 -m ampg --config gateway.toml doctor
python3 -m ampg --config gateway.toml install-plan --profile vps-full --write-artifacts
python3 -m ampg --config gateway.toml deploy apply --stage packages --dry-run --profile vps-full
python3 -m ampg --config gateway.toml approvals list --profile vps-full
python3 -m ampg --config gateway.toml approvals approve --profile vps-full --all
python3 -m ampg --config gateway.toml apply --dry-run --profile vps-full
python3 -m ampg --config gateway.toml deploy apply --stage state --dry-run --profile vps-full
python3 -m ampg --config gateway.toml deploy apply --stage supervisor --dry-run --profile vps-full
python3 -m ampg --config gateway.toml deploy apply --stage start --dry-run --profile vps-full
python3 -m ampg --config gateway.toml deploy apply --stage addresses --dry-run --profile vps-full
python3 -m ampg --config gateway.toml deploy apply --stage health --dry-run --profile vps-full
```

`init site` writes a readable `gateway.toml` with selected transports enabled and common
transports left as one-line toggles. `deploy plan` condenses the lower-level checks into
clear next steps. `dns plan` covers static DNS, Dynamic DNS, and behind-router
reachability hints. `apply --dry-run` prints the activation sequence and a preflight
verdict without changing services. `deploy apply --stage packages` installs selected
managed-daemon packages using structured platform commands. `deploy apply --stage state`
copies approved managed-daemon config into AMPG-owned state. `deploy apply --stage
supervisor` installs approved supervisor files after state exists. `deploy apply --stage
start` starts AMPG-owned services after state and supervisor files are present. `deploy
apply --stage addresses` captures daemon-written public addresses into the address registry.
`deploy apply --stage health` verifies published fixture URLs through the selected
transport.

## Interaction tiers

AMPG is static-first, but not static-only. Each site or route group declares the highest
interaction tier it wants AMPG to expose:

- `static`: rendered files only.
- `interactive-lite`: deterministic games, status lookups, quote forms, and other flows
  without account state or payment confirmation.
- `identity`: authenticated sessions, wallet sign-in, or signed capability links.
- `transactional`: server-confirmed orders, deposits, invoices, donations, or payment intents.
- `realtime`: multiplayer, dashboards, websockets, streaming updates, or fast shared state.
- `internal`: workers, webhooks, private admin APIs; never published automatically.

Constrained transports receive the safest compatible version. A storefront can have a
Gemini catalog and inquiry flow without exposing its full JavaScript checkout. A worker
API remains internal even when the public site is available on Tor or I2P.

## Documentation

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Daemon management](docs/daemon-management.md)
- [Domain onboarding](docs/domain-onboarding.md)
- [Fixture manifests](docs/fixture-manifests.md)
- [State contract](docs/state-contract.md)
- [Interaction capabilities](docs/interaction-capabilities.md)
- [Interactive applications](docs/interactive-apps.md)
- [Wownero integration](docs/wownero-integration.md)
- [Autodocs and drift gates](docs/autodocs.md)

## Checks

```sh
python3 tools/docs_check.py
python3 -m ampg docs generate --check
```

## Local Commands

The current implementation is dependency-free Python:

```sh
python3 -m ampg --config gateway.toml init site wownero --domain wownero.org --source ../wownero.org-website --preset full
python3 -m ampg --config examples/wownero.gateway.toml deploy plan --profile vps-full
python3 -m ampg --config examples/wownero.gateway.toml dns plan --profile vps-full
python3 -m ampg --config examples/wownero.gateway.toml dns plan --profile vps-full --free-domain-hints
python3 -m ampg --config examples/wownero.gateway.toml dns plan --profile vps-full --mode dynamic --behind-router
python3 -m ampg --config examples/wownero.gateway.toml dns check --profile vps-full
python3 -m ampg --config examples/wownero.gateway.toml plan
python3 -m ampg --config examples/wownero.gateway.toml plan --write-artifacts
python3 -m ampg --config examples/wownero.gateway.toml status
python3 -m ampg --config examples/wownero.gateway.toml doctor
python3 -m ampg --config examples/wownero.gateway.toml install-plan --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml install-plan --profile mobile-i2p --write-artifacts
python3 -m ampg --config examples/wownero.gateway.toml health-plan --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml health-plan --profile mobile-i2p --mode preview
python3 -m ampg --config examples/wownero.gateway.toml apply --dry-run
python3 -m ampg --config examples/wownero.gateway.toml apply --dry-run --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml apply --dry-run --protocol i2p
python3 -m ampg --config examples/wownero.gateway.toml apply --dry-run --write-artifacts
python3 -m ampg --config examples/wownero.gateway.toml approvals list --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml approvals approve --profile mobile-i2p --all
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage packages --dry-run --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage packages --profile mobile-i2p --yes
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage state --dry-run --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage state --profile mobile-i2p --yes
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage supervisor --dry-run --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage supervisor --profile mobile-i2p --yes
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage start --dry-run --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage start --profile mobile-i2p --yes
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage addresses --dry-run --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage addresses --profile mobile-i2p --yes
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage health --dry-run --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage health --profile mobile-i2p --yes
python3 -m ampg --config examples/wownero.gateway.toml build
python3 -m ampg --config examples/wownero.gateway.toml build --profile tor-i2p
python3 -m ampg --config examples/wownero.gateway.toml build --protocol tor --protocol i2p
python3 -m ampg --config examples/wownero.gateway.toml manifest
python3 -m ampg --config examples/wownero.gateway.toml addresses list
python3 -m ampg --config examples/wownero.gateway.toml addresses capture --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml addresses set --site wownero --protocol i2p --url example.b32.i2p
python3 -m ampg --config examples/wownero.gateway.toml state-contract --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml preview endpoints
python3 -m ampg --config examples/wownero.gateway.toml preview manifest
python3 -m ampg --config examples/wownero.gateway.toml routes explain
python3 -m ampg --config examples/wownero.gateway.toml routes validate
python3 tools/generate_route_manifest.py examples/route-catalog.json examples/route-manifest.json
python3 -m ampg route-manifest validate examples/route-manifest.json
python3 -m ampg --config examples/wownero.gateway.toml audit
python3 -m ampg --config examples/i2p-only.gateway.toml build
python3 -m ampg docs generate
python3 -m unittest discover -s tests
```

The Wownero build writes generated files under `dist/wownero/`. Each protocol output
root contains `.ampg-output`; AMPG refuses to clean a non-empty output directory unless
that marker is present.

Plan artifacts are written under `dist/ampg-plan/` only when `--write-artifacts` is
passed. They are reviewable snippets, not installed daemon config.

Managed install artifacts are also written under `dist/ampg-plan/` when
`install-plan --write-artifacts` is passed. They include reviewable daemon configs and
platform supervisor files, but are not installed or started. Managed daemon configs point
runtime state at `gateway.state_dir`.

Captured transport addresses are written under `gateway.state_dir` by
`deploy apply --stage addresses`, `addresses capture`, or `addresses set`. Fixture
manifests and health plans use explicit config first, then captured addresses, then
deterministic placeholders.

`approvals list` reports whether generated artifact digests are missing, stale,
unapproved, or approved. `approvals approve` records reviewed digests under
`gateway.state_dir`; edited or regenerated artifacts automatically fall back to review.

`apply --dry-run` includes an address stage and an `AMPG_APPLY_PREFLIGHT` gate.
Placeholder addresses remain review items until the generated transport identity is
captured or configured. With `--write-artifacts`, apply also prints config artifacts that
would be copied into managed state and the supervisor services that would be registered
or started. The preflight gate reports `blocked`, `review`, or `ready` across activation
steps, managed-state copies, and supervisor actions.

`deploy apply --stage packages --dry-run` shows managed-daemon packages that can be
installed automatically for the selected platform. The live form requires `--yes`, runs
only allowlisted package-manager commands, and leaves config, services, keys, and
addresses unchanged. Adopted and external daemons are skipped.

`deploy apply --stage state --dry-run` shows approved managed-daemon artifacts that are
ready to copy into `gateway.state_dir`. The live form requires `--yes`; it creates only
AMPG-owned state directories and copies approved artifact contents. It does not install
packages, change adopted daemons, start services, or remove keys.

`deploy apply --stage supervisor --dry-run` shows approved supervisor files that can be
installed after managed state config exists. The live form requires `--yes`; it writes
only AMPG-named service files for the selected platform. It does not install packages,
invoke `systemctl`, `launchctl`, or `sv-enable`, start daemons, or remove service files.

`deploy apply --stage start --dry-run` shows the service-manager commands for
AMPG-owned services whose state and supervisor files are already installed. The live form
requires `--yes`; it runs only structured platform commands for AMPG-named services. It
does not install packages, rewrite config, delete files, capture addresses, or run health
checks.

`deploy apply --stage addresses --dry-run` shows daemon-written public addresses that can
be recorded. The live form requires `--yes`; it writes captured addresses to
`gateway.state_dir` and leaves health verification for the next stage.

`deploy apply --stage health --dry-run` shows published fixture checks after addresses
are configured or captured. The live form requires `--yes`; it runs the transport check
commands and reports pass/fail without changing config or state.

`dns plan --free-domain-hints` prints optional community subdomain services that may help
new users get a clearnet name without buying a domain. These are third-party registries;
operators still need to review current terms, availability, content rules, and DNS
record support before relying on one.

Use `--protocol` to scope operational commands to one or more enabled protocols. This
lets a full site config build or activate only Tor, only I2P, or a selected subset without
unselected transports blocking the run.

Use `--profile` to load a named deployment target from `gateway.toml`. Profiles can set
selected protocols, a default platform provider, and safe artifact-writing defaults.
Explicit `--protocol` and `--platform` flags override the profile when present.

## Reusable checklist

- [ ] Pick source kind: `static-html`, `markdown`, or `ssg-output`.
- [ ] Select protocols and daemon policy.
- [ ] Run `ampg plan`; review output roots, ports, and config changes.
- [ ] Run `ampg status` or `ampg doctor`; review daemon ownership decisions.
- [ ] Run `ampg install-plan`; review managed daemon package, state, and supervisor steps.
- [ ] Run `ampg build`; inspect generated variants.
- [ ] Run AMPB fixture checks against generated manifests.
- [ ] Run `ampg health-plan`; review post-start transport checks.
- [ ] Run `ampg approvals approve --all` after reviewing generated artifacts.
- [ ] Run `ampg apply --dry-run`; review the activation sequence and preflight gate.
- [ ] Run `ampg deploy apply --stage packages --dry-run`; confirm package-manager commands.
- [ ] Run `ampg deploy apply --stage state --dry-run`; confirm approved state copies.
- [ ] Run `ampg deploy apply --stage supervisor --dry-run`; confirm approved service files.
- [ ] Run `ampg deploy apply --stage start --dry-run`; confirm service-manager commands.
- [ ] Run `ampg deploy apply --stage addresses --dry-run`; confirm captured transport addresses.
- [ ] Run `ampg deploy apply --stage health --dry-run`; confirm published health checks.
- [ ] Run live apply after the preflight gate is ready.
