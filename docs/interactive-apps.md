# Interactive Applications

> Status: draft | Updated 2026-07-05 | Applies to: dynamic app support

AMPG must support real applications without pretending every transport can offer the same
experience. The design goal is graceful capability mapping: expose the safest useful version
of each surface on each protocol, and keep private surfaces private.

## Interaction tiers

`static`
: Rendered files only. Works everywhere.

`forms`
: Server-rendered GET/POST actions with full-page responses. Works on clearnet, Tor, I2P,
  and can be mapped to Gemini input prompts or Reticulum page scripts for simple actions.

`sessions`
: Authenticated account flows. Supported on HTTP transports with strict cookies. Gemini can
  use client certificates or signed links later, but this is not a v1 requirement.

`realtime`
: Rich browser UI, dashboards, live charts, websockets, or client-side state. HTTP transports
  only, and usually clearnet or private Tor/I2P.

`internal`
: Worker APIs, webhooks, private admin APIs, payment callbacks, chain watchers, and service
  health endpoints. AMPG must not publish these automatically.

## Application adapter contract

An application adapter describes what AMPG may expose:

- upstream service and health check.
- OpenAPI spec or route manifest when available.
- route groups with interaction tier, auth requirement, and idempotency behavior.
- form/action schemas for protocol translation.
- public asset and cache policy.
- private route denylist.

Adapters do not bypass the application. They translate constrained protocol input into the
application's public action surface, then render safe responses.

## Protocol mapping

| Tier | Clearnet | Tor/I2P | Gemini | Reticulum |
| --- | --- | --- | --- | --- |
| `static` | yes | yes | yes | yes |
| `forms` | yes | yes, no JS by default | simple single-field prompts | simple scripts/actions |
| `sessions` | yes | yes, strict cookies | later | later |
| `realtime` | yes | optional private surface | no | no |
| `internal` | no public publish | no public publish | no | no |

## Challenge profile: Medusa multi-tenant platform

Source: `../medusa-multi-tenant-platform`.

Why it matters:

- multi-tenant domain routing.
- storefront, tenant admin, backend, worker, database, Redis, S3/MinIO.
- cart, checkout, orders, bookings, blogs, email, payment providers, and webhooks.
- tenant-specific themes and custom domains.

AMPG support target:

- Clearnet: adopt existing Caddy/reverse-proxy deployment.
- Tor/I2P: expose storefront routes with `forms` or `sessions` tier, no JavaScript by default.
- Gemini/Reticulum: expose catalog, blog, policy, product detail, and inquiry/request flows.
- Admin: `internal` unless explicitly bound to a private operator transport.
- Webhooks, payment callbacks, worker queues, health internals: always `internal`.

Required adapter capabilities:

- read tenant/domain registry or accept an exported tenant manifest.
- generate per-tenant protocol targets and daemon plans.
- cap checkout/payment routes by protocol.
- use OpenAPI route metadata where available.
- never expose tenant admin or backend admin by wildcard.

## Challenge profile: evaluetron / ai-gen-bot

Source: `../ai-gen-bot`.

Why it matters:

- OpenAPI-first core.
- customer storefront plus operator console.
- auth, payments, credit ledger, job queue, workers, moderation, and generated artifacts.
- public web channel, Telegram channel, internal worker APIs, and admin APIs.

AMPG support target:

- Clearnet: public storefront and docs.
- Tor/I2P: public storefront with server-rendered account/job flows when enabled.
- Gemini/Reticulum: catalog browsing, deposit instructions, simple generation request, and job
  status lookup only after explicit adapter support.
- Operator console: private clearnet, LAN, mesh, or private onion only.
- Worker/internal routes: never published.

Required adapter capabilities:

- consume `api/openapi.yaml` as the action contract.
- map job creation to idempotent form submissions.
- render job status as polling-friendly pages.
- hide unavailable generators when no worker advertises the required capability.
- preserve the ledger and payment invariants of the upstream app.

## Design constraints learned from the challenge apps

- Public route discovery must start deny-first.
- OpenAPI is useful, but not sufficient; route tiers and privacy intent must be explicit.
- Admin and worker surfaces are separate sites or route groups, not accidental subpaths.
- Gemini and Reticulum need curated actions, not automatic exposure of every POST route.
- Multi-tenant apps need generated protocol targets per tenant, with shared daemon adapters.

## Reusable checklist

- [ ] Classify every route group by interaction tier.
- [ ] Deny private/admin/internal routes before enabling protocols.
- [ ] Prefer OpenAPI or route manifests over HTML scraping for actions.
- [ ] Provide safe alternates for constrained transports.
- [ ] Verify no worker, webhook, payment callback, or admin route is publicly published.
