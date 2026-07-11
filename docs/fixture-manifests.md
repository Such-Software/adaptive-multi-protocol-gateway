# Fixture Manifests

> Status: draft | Updated 2026-07-11 | Applies to: AMPG and AMPB compatibility checks

AMPG writes deterministic fixture manifests so AMPB can verify that generated site
variants route to the expected browser transport context.

Fixture manifests are test contracts, not signed service discovery. See
[Signed service manifests](service-manifests.md) for the client-facing identity and endpoint
contract.

Current manifests use `ampg.fixture-manifest.v2`. The browser-facing `checks.context`
field is a logical transport context and does not imply a separate browser profile or
window.

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
- expected AMPB transport, logical context, and transport-context isolation.
- declared interaction tier, identity adapter, payment adapter, realtime flag, and
  public exposure flag.
- optional route-group metadata for configured public route policies.

It must not contain private host inventory, hidden-service keys, tunnel keys, credentials,
or deployment notes.

The isolation check is a browser-facing result, not a daemon-management instruction.
AMPG declares which transport context must consume the route; AMPB independently decides
how to isolate that context and whether to adopt or start the local transport needed to
reach it.

## Commands

```sh
python3 -m ampg --config examples/wownero.gateway.toml build
python3 -m ampg --config examples/wownero.gateway.toml manifest
python3 -m ampg --config examples/wownero.gateway.toml addresses list
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage addresses --dry-run --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml addresses capture --profile mobile-i2p
python3 -m ampg --config examples/wownero.gateway.toml preview manifest
python3 -m ampg --config examples/wownero.gateway.toml health-plan
python3 -m ampg --config examples/wownero.gateway.toml health-plan --mode preview
python3 -m ampg --config examples/wownero.gateway.toml deploy apply --stage health --dry-run --profile mobile-i2p
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

`health-plan` consumes the same fixture contract. Published mode prints checks for real
transport URLs. Preview mode prints loopback checks against generated preview URLs.
`deploy apply --stage health` runs the published checks after transport addresses are
configured or captured.

## Address Status

Some transports may not have final public addresses when a fixture is generated. In those
cases AMPG uses route-valid placeholders such as `http://wownero.onion/` so AMPB can still
verify transport selection without contacting the network.

When a managed or adopted daemon writes an actual address, run
`deploy apply --stage addresses --dry-run` before recording it. Captured addresses are
stored under `gateway.state_dir` and replace placeholders in fixture manifests and
published health plans. Operators can then run `deploy apply --stage health --dry-run`
to review the exact transport checks before live verification. Operators can also use
`addresses capture` for a direct write or `addresses set` to store an address manually.

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
