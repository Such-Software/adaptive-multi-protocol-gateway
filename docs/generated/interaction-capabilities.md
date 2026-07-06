# Generated Interaction Capabilities

> Status: generated | Updated by `python3 -m ampg docs generate` | Applies to: AMPG

This file is generated from code. Do not edit it by hand.


## Tiers

| Tier | Summary | Examples | Notes |
| --- | --- | --- | --- |
| `static` | Rendered files only. | documentation, landing pages, catalog pages | Works across every currently modeled transport. |
| `interactive-lite` | Client-visible state with deterministic or server-rendered updates. | deterministic games, leaderboards, quote forms, status lookups | Does not require accounts or payment confirmation. Constrained transports may receive static snapshots or form-style actions. |
| `identity` | Authenticated sessions or signed wallet identity. | account pages, wallet sign-in, claim pages | Requires explicit identity adapter selection. HTTP transports can use strict cookies; wallet sign-in uses signed challenges. |
| `transactional` | Server-confirmed orders, wagers, deposits, invoices, or payment intents. | basic stores, paid downloads, game entry fees, donations | Requires explicit payment adapter selection. Callbacks, webhook receivers, and ledger internals remain internal. |
| `realtime` | Live multiplayer, dashboards, websocket streams, or fast state sync. | multiplayer games, live markets, operator consoles | HTTP transports only in the current model. Usually clearnet or private Tor/I2P until transport-specific realtime support exists. |
| `internal` | Private/admin/worker surfaces that must not be published automatically. | admin panels, webhooks, worker APIs, health endpoints | Always deny by default on public outputs. |

## Identity Adapters

| Adapter | Status | Transports | Notes |
| --- | --- | --- | --- |
| `none` | `ready` | clearnet, tor, i2p, gemini, ipfs, reticulum | No account or signed identity required. |
| `http-session` | `planned` | clearnet, tor, i2p | Use HTTP-only cookies and strict transport-specific session scope. Profiles must not be shared across transports. |
| `siwe` | `planned` | clearnet, tor, i2p | Sign-In with Ethereum style challenge/response. Wallet transport availability is a browser-shell concern. |
| `signed-link` | `research` | gemini, reticulum | Use only for narrow flows with short-lived, scoped capabilities. |

## Payment Adapters

| Adapter | Status | Transports | Notes |
| --- | --- | --- | --- |
| `none` | `ready` | clearnet, tor, i2p, gemini, ipfs, reticulum | No payment required. |
| `server-invoice` | `planned` | clearnet, tor, i2p | Server creates invoice or payment intent and confirms settlement. Callback/webhook routes stay internal. |
| `wallet-signature` | `planned` | clearnet, tor, i2p | Browser wallet signs a request; server verifies before fulfilling. |
| `static-instructions` | `planned` | gemini, ipfs, reticulum | Render payment instructions or donation addresses without automatic fulfillment. |

## Transport Limits

| Transport | Public Max Tier | Identity | Payments | Realtime | Notes |
| --- | --- | --- | --- | --- | --- |
| `clearnet` | `realtime` | http-session, siwe | server-invoice, wallet-signature | yes | Highest-fidelity browser surface. |
| `tor` | `transactional` | http-session, siwe | server-invoice, wallet-signature | private-only | Prefer server-rendered flows and reduced JavaScript by default. |
| `i2p` | `transactional` | http-session, siwe | server-invoice, wallet-signature | private-only | Prefer server-rendered flows and reduced JavaScript by default. |
| `gemini` | `interactive-lite` | signed-link research | static-instructions | no | Use curated prompts or polling-friendly status pages. |
| `ipfs` | `static` | none | static-instructions | no | Content-addressed snapshots; no server-confirmed state by default. |
| `reticulum` | `interactive-lite` | signed-link research | static-instructions | research | Resilient/private routing; not an anonymity layer. |
