# Interactive Applications

> Status: draft | Updated 2026-07-06 | Applies to: dynamic app support

AMPG must support real applications without pretending every transport can offer the same
experience. The design goal is graceful capability mapping: expose the safest useful
version of each public surface on each protocol, and keep private surfaces private.

## Interaction Tiers

`static`
: Rendered files only. Works everywhere.

`interactive-lite`
: Deterministic games, status lookups, quote forms, and other flows that do not require
  account state or payment confirmation.

`identity`
: Authenticated sessions, wallet sign-in, or signed capability links.

`transactional`
: Server-confirmed orders, wagers, deposits, invoices, donations, or payment intents.

`realtime`
: Multiplayer, dashboards, websockets, streaming updates, or fast shared state.

`internal`
: Admin, worker APIs, webhooks, callback endpoints, chain watchers, health checks, and
  private operator surfaces. AMPG must not publish these automatically.

The code-owned capability matrix lives in
[generated interaction capabilities](generated/interaction-capabilities.md).

## Application Adapter Contract

An application adapter describes what AMPG may expose:

- upstream service and health check.
- OpenAPI spec or route manifest when available.
- route groups with interaction tier, auth requirement, payment requirement, and idempotency behavior.
- form/action schemas for protocol translation.
- public asset and cache policy.
- private route denylist.

Adapters do not bypass the application. They translate constrained protocol input into the
application's public action surface, then render safe responses.

## Protocol Mapping

| Tier | Clearnet | Tor/I2P | Gemini | IPFS | Reticulum |
| --- | --- | --- | --- | --- | --- |
| `static` | yes | yes | yes | yes | yes |
| `interactive-lite` | yes | yes | curated prompts/status pages | static snapshots only | curated actions |
| `identity` | yes | yes, strict sessions | research | no | research |
| `transactional` | yes | yes, explicit adapter | instructions/status only | instructions only | instructions/status only |
| `realtime` | yes | private/opt-in only | no | no | research |
| `internal` | no public publish | no public publish | no | no | no |

## Identity And Payments

Identity and payments are optional adapters, not default site behavior. A route group must
explicitly request them before AMPG exposes account or payment flows on any transport.

Supported design tracks:

- strict HTTP sessions for clearnet, Tor, and I2P.
- Sign-In with Ethereum style challenge/response for HTTP transports.
- server-created invoices or payment intents with internal callbacks.
- wallet-signed requests verified by the upstream app.
- static payment instructions for read-only or constrained outputs.

Payment callbacks, webhooks, ledger internals, worker routes, and private reconciliation
jobs remain `internal` even when public checkout or donation pages are exposed.

## Design Constraints

- Public route discovery must start deny-first.
- OpenAPI is useful, but not sufficient; route tiers and privacy intent must be explicit.
- Admin and worker surfaces are separate sites or route groups, not accidental subpaths.
- Gemini, IPFS, and Reticulum need curated outputs, not automatic exposure of every POST route.
- Multi-tenant apps need generated protocol targets per tenant, with shared daemon adapters.

## Reusable Checklist

- [ ] Classify every route group by interaction tier.
- [ ] Deny private/admin/internal routes before enabling protocols.
- [ ] Prefer OpenAPI or route manifests over HTML scraping for actions.
- [ ] Provide safe alternates for constrained transports.
- [ ] Verify no worker, webhook, payment callback, ledger internal, or admin route is publicly published.
