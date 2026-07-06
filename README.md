# Adaptive Multi-Protocol Gateway

> Status: draft | Updated 2026-07-06 | Applies to: AMPG contributors and operators

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
ampg init site wownero \
  --domain wownero.org \
  --source ../wownero.org-website \
  --source-kind static-html

ampg enable wownero tor gemini i2p reticulum
ampg plan
ampg build
ampg apply --dry-run
```

`plan` prints rendered output paths, daemon decisions, port bindings, config diffs, and
operator actions. The current `apply --dry-run` prints the activation sequence without
changing services. Live apply support will perform only approved changes.

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
`addresses capture` or `addresses set`. Fixture manifests and health plans use explicit
config first, then captured addresses, then deterministic placeholders.

`apply --dry-run` includes an address stage. Placeholder addresses remain review items
until the generated transport identity is captured or configured. With `--write-artifacts`,
apply also prints the reviewed config artifacts that would be copied into managed state.

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
- [ ] Run `ampg apply --dry-run`; review the activation sequence.
- [ ] Run live apply after the activation sequence is clean.
