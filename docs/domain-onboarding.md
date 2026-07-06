# Domain Onboarding

> Status: draft | Updated 2026-07-06 | Applies to: clearnet DNS setup

AMPG treats clearnet naming as an operator choice. A site can use a normal owned domain,
a community free subdomain, a Dynamic DNS name, or no clearnet name at all when only
private transports are selected.

## Command

```sh
python3 -m ampg --config gateway.toml dns plan
python3 -m ampg --config gateway.toml dns plan --free-domain-hints
python3 -m ampg --config gateway.toml dns plan --mode dynamic --behind-router
python3 -m ampg --config gateway.toml dns check
```

`dns plan --free-domain-hints` prints `AMPG_FREE_DOMAIN_HINT` rows for optional
third-party services that may provide free subdomains for personal sites, hobby apps, or
open-source projects. AMPG does not register these names automatically because each
provider has its own review process, terms, availability, and DNS record support.

## Choices

Owned domain:
: Best for production sites, long-lived projects, storefronts, and anything that needs
  strong brand control.

Free community subdomain:
: Useful for experiments, personal projects, demos, and users who cannot buy a domain
  yet. Review the provider's current rules before relying on it.

Dynamic DNS:
: Useful for laptops, home servers, old phones, or other hosts whose public IP can
  change. Apex-domain support depends on the DNS provider.

Behind-router hosting:
: Use port forwarding, public IPv6, an explicit router mapping, a reverse tunnel, or
  DNS-01 certificate validation when inbound port 80 is unavailable.

## Included Hints

AMPG includes conservative hints for:

- `is-a.dev`: developer personal sites and projects.
- `js.org`: JavaScript ecosystem projects; narrower content rules.
- Open Domains: student and open-source project subdomains through the current web app.
- Other community GitHub registries such as `is-an.app`, `wip.la`, `thedev.id`,
  `io.day`, `jsid.dev`, `is-a.co`, `is-a-good.dev`, `is-really.cool`, and `js.cool`.

These hints are naming ideas, not guarantees. Verify current status before adding a
domain to a public deployment.
