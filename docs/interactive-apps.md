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

Configured public route groups are emitted into fixture manifests so AMPB can verify the
route and interaction policy for each selected transport. Internal route groups are not
emitted.

## Route Manifest Contract

Apps may provide `ampg.route-manifest.v1` JSON. AMPG imports it from
`site.interactions.route_manifest`, merges its denylist with inline TOML, and appends any
inline TOML route entries after the imported route entries.

The schema is generated at `schemas/ampg.route-manifest.v1.schema.json`, and app repos can
validate generated manifests with:

```sh
python3 tools/generate_route_manifest.py examples/route-catalog.json examples/route-manifest.json
python3 -m ampg route-manifest validate routes.json
```

`examples/route-catalog.json` shows the adapter side of the workflow: app route metadata
goes in, the stable AMPG route manifest comes out.

Required top-level fields:

- `schema`: must be `ampg.route-manifest.v1`.
- `routes`: route policy objects using `match`, `tier`, `identity`, `payments`,
  `realtime`, and `public_allowed`.

Optional top-level fields:

- `default_tier`: inherited by route entries without a `tier`.
- `deny_routes`: route patterns that must not be published.

## Route Exposure Checks

Use route checks before publishing an application target:

```sh
python3 -m ampg --config gateway.toml routes explain
python3 -m ampg --config gateway.toml routes validate
```

`routes explain` prints one decision per route and enabled protocol. Decisions include the
route source, tier, protocol `max_tier`, status, and reason.

`routes validate` exits nonzero when a public, non-denied route has no compatible enabled
protocol. Routes marked `internal`, `public_allowed = false`, or matched by
`deny_routes` are treated as intentionally unpublished.

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
