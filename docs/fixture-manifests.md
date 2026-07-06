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

It must not contain private host inventory, hidden-service keys, tunnel keys, credentials,
or deployment notes.

## Commands

```sh
python3 -m ampg --config examples/wownero.gateway.toml build
python3 -m ampg --config examples/wownero.gateway.toml manifest
```

`build` emits the manifest after writing protocol outputs. `manifest` rewrites only the
manifest and does not rebuild protocol outputs.

## Address Status

Some transports may not have final public addresses when a fixture is generated. In those
cases AMPG uses route-valid placeholders such as `http://wownero.onion/` so AMPB can still
verify transport selection without contacting the network.
