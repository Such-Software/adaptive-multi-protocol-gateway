# Domain Onboarding

> Status: draft | Updated 2026-07-07 | Applies to: clearnet DNS setup

AMPG treats clearnet naming as an operator choice. A site can use a normal owned domain,
a community free subdomain, a Dynamic DNS name, or no clearnet name at all when only
private transports are selected.

## Command

```sh
python3 -m ampg --config gateway.toml dns plan
python3 -m ampg --config gateway.toml dns records --ipv4 203.0.113.10
python3 -m ampg --config gateway.toml dns plan --free-domain-hints
python3 -m ampg --config gateway.toml dns plan --mode dynamic --behind-router
python3 -m ampg --config gateway.toml dns check
```

`dns records` prints provider-ready records for enabled public transports. It can include
`A`/`AAAA` host records, CAA, optional non-mail SPF/DMARC records, and AMPG TXT discovery
hints for transport-aware clients.

## Provider Writes

Provider writes must be previewable and backed up. AMPG keeps the generic record plan
separate from provider mutation:

```sh
python3 -m ampg --config gateway.toml dns records --ipv4 203.0.113.10 --mail-policy disabled
python3 -m ampg --config gateway.toml dns backup --provider namecheap --credentials /etc/ampg/namecheap.ini
python3 -m ampg --config gateway.toml dns apply --provider namecheap --credentials /etc/ampg/namecheap.ini --ipv4 203.0.113.10
python3 -m ampg --config gateway.toml dns apply --provider namecheap --credentials /etc/ampg/namecheap.ini --ipv4 203.0.113.10 --yes
```

`dns apply` is a dry run unless `--yes` is present. Live apply reads the current zone,
writes a backup under `gateway.state_dir/dns-backups`, merges only AMPG-managed records,
and preserves unrelated records such as domain verification TXT entries.

Namecheap's XML API uses replace-all `setHosts`, so AMPG always fetches and merges the
whole zone before applying. The documented Namecheap API record types do not include
`SRV`; AMPG can show SRV records in the generic plan, but the Namecheap writer skips
unsupported record types and relies on TXT discovery hints unless another provider path
is configured.

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
