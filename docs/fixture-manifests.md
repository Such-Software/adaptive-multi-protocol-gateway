# Fixture Manifests

> Status: draft | Updated 2026-07-06 | Applies to: AMPG and AMPB compatibility checks

AMPG writes deterministic fixture manifests so AMPB can verify that generated site
variants route to the expected browser transport and profile.

## Output

`ampg build` writes one manifest per site:

```text
<site.outputs.root>/ampg-fixture-manifest.json
```

The manifest contains public route expectations only:

- site id, domain, and canonical URL.
- enabled protocol fixtures.
- protocol renderer and relative output path.
- route URL for AMPB checks.
- expected AMPB transport and profile.
- declared interaction tier, identity adapter, payment adapter, realtime flag, and
  public exposure flag.
- optional route-group metadata for configured public route policies.

It must not contain private host inventory, hidden-service keys, tunnel keys, credentials,
or deployment notes.

## Commands

```sh
python3 -m ampg --config examples/wownero.gateway.toml build
python3 -m ampg --config examples/wownero.gateway.toml manifest
python3 -m ampg --config examples/wownero.gateway.toml preview manifest
```

`build` emits the manifest after writing protocol outputs. `manifest` rewrites only the
manifest and does not rebuild protocol outputs.

`preview manifest` writes:

```text
<site.outputs.root>/ampg-preview-fixture-manifest.json
```

Preview manifests point fixture URLs at loopback HTTP servers for generated output roots.
They preserve the intended published URL and transport checks under each fixture's
`published` metadata. Use preview manifests to verify generated output with AMPB before
real Tor, I2P, Gemini, or other transport daemons are installed or adopted.

## Address Status

Some transports may not have final public addresses when a fixture is generated. In those
cases AMPG uses route-valid placeholders such as `http://wownero.onion/` so AMPB can still
verify transport selection without contacting the network.

## Interaction Policy

Fixture interaction policy defaults to:

```json
{
  "tier": "static",
  "identity": "none",
  "payments": "none",
  "realtime": false,
  "public_allowed": true
}
```

Protocol-level options can declare the base fixture policy that AMPB should check.

When `[[site.interactions.route]]` entries are configured, AMPG emits additional fixtures
for public route groups. Routes with `tier = "internal"`, `public_allowed = false`, or a
match covered by `deny_routes` are not emitted.

Routes imported from `site.interactions.route_manifest` are treated the same way as inline
TOML routes.

AMPG also omits route fixtures whose interaction tier exceeds the protocol target's
`max_tier`. When `max_tier` is not configured, AMPG uses the transport capability defaults
from the generated interaction capability matrix.
