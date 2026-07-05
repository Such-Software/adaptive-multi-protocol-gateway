# Adaptive Multi-Protocol Gateway

> Status: draft | Updated 2026-07-05 | Applies to: AMPG contributors and operators

Adaptive Multi-Protocol Gateway, or AMPG, turns one canonical site into transport-appropriate
published versions for clearnet web, Tor onion services, I2P, Gemini, and Reticulum.

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
ampg apply
```

`plan` prints rendered output paths, daemon decisions, port bindings, config diffs, and
operator actions. `apply` performs only the approved changes.

## Interaction tiers

AMPG is static-first, but not static-only. Each site or route group declares the highest
interaction tier it wants AMPG to expose:

- `static`: rendered files only.
- `forms`: server-rendered GET/POST actions with full-page responses.
- `sessions`: authenticated account flows with HTTP-only cookies or transport-native identity.
- `realtime`: rich browser/admin surfaces; HTTP transports only.
- `internal`: workers, webhooks, private admin APIs; never published automatically.

Constrained transports receive the safest compatible version. A storefront can have a Gemini
catalog and inquiry flow without exposing its full JavaScript checkout. A worker API remains
internal even when the public site is available on Tor or I2P.

## Documentation

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Daemon management](docs/daemon-management.md)
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
python3 -m ampg --config examples/wownero.gateway.toml build
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

## Reusable checklist

- [ ] Pick source kind: `static-html`, `markdown`, or `ssg-output`.
- [ ] Select protocols and daemon policy.
- [ ] Run `ampg plan`; review output roots, ports, and config changes.
- [ ] Run `ampg build`; inspect generated variants.
- [ ] Run `ampg apply`; publish through adopted or managed daemons.
