# Domain Onboarding

> Status: reviewed adapter contract | Updated 2026-07-31 | Applies to: clearnet DNS setup

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

Dynadot REST v2 is also supported. Its DNS update replaces the complete zone and
uses one zone-wide TTL, so AMPG preserves every documented `value1`, `value2`, and
`sub_host` field and refuses a write if the merged records have mixed TTLs. The
Dynadot credential input must contain `api_base_url`, `api_key`, `api_secret`, and
an operator-observed IPv4 `/32` `allowed_source_cidr`. Keys and signatures travel
only in request headers. Because Dynadot labels REST v2 beta, production use also
requires a pinned adapter commit, a sandbox proof, a connected production plan,
and a private raw backup before the exact-zone apply.

Application and service onboarding can use a secretless JSON manifest without
creating a synthetic `gateway.toml`:

```sh
ampg-dns-manifest --manifest ~/Build/example/dns-manifest.json --offline
ampg-dns-manifest \
  --manifest ~/Build/example/dns-manifest.json \
  --credentials /tmp/ephemeral-namecheap.ini \
  --client-ip 203.0.113.10
ampg-dns-manifest \
  --manifest ~/Build/example/dns-manifest.json \
  --credentials /tmp/ephemeral-namecheap.ini \
  --client-ip 203.0.113.10 \
  --backup-dir ~/Build/example/dns-backups \
  --apply-zone example.com
```

For Dynadot, omit `--client-ip` and provide the ephemeral four-field Dynadot
credential file. A connected plan first observes the existing zone-wide TTL.
The secretless manifest must be rendered with that exact TTL before apply;
AMPG fails closed instead of changing the TTL on unmanaged records.

The generic writer is also read-only by default. The exact `--apply-zone`
sentinel and an absolute backup directory are mandatory for a write.
`protected_names` can forbid all changes at sensitive names such as `@`.
Each managed record explicitly chooses whether to replace all values at its
name/type or only values with a known prefix; unrelated TXT values survive.
Credential files must be short-lived inputs created by the approved secret
handoff and must never be committed or placed in Seafile.

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
