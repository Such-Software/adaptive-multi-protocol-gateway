# Interaction Capabilities

> Status: draft | Updated 2026-07-06 | Applies to: AMPG route exposure policy

Interaction capabilities define what AMPG may expose for dynamic applications. They are
public, generic rules. Non-public project notes belong in `docs/private/`.

## Generated Policy

The code-owned policy tables live in
[generated interaction capabilities](generated/interaction-capabilities.md).

They cover:

- interaction tiers from `static` through `internal`.
- identity adapters such as HTTP sessions and wallet challenge/response.
- payment adapters such as server invoices and wallet-signed requests.
- per-transport limits for clearnet, Tor, I2P, Gemini, IPFS, and Reticulum.

## Rule

AMPG only exposes a route when the route tier, identity adapter, payment adapter, and
transport capability all agree. When in doubt, the route stays private.
