# Configuration

> Status: draft | Updated 2026-07-06 | Applies to: `gateway.toml`

AMPG is configured from one TOML file. The file declares global paths, sites, source
adapters, render targets, and daemon policy.

## Create A Config

For an existing static HTML site, start with `init site`:

```sh
python3 -m ampg --config gateway.toml init site example \
  --domain example.org \
  --source ../example.org \
  --preset full
```

Presets are concise transport bundles:

- `full`: clearnet, Tor, and I2P.
- `privacy`: Tor and I2P.
- `i2p-only`, `tor-only`, `clearnet-only`, or `gemini-only`: one transport.

Use `--protocol` to select exact transports instead of a preset:

```sh
python3 -m ampg --config gateway.toml init site example \
  --domain example.org \
  --source ../example.org \
  --protocol i2p
```

The generated config keeps common transports as `enabled = true/false` toggles and
creates practical profiles such as `vps-full`, `tor-i2p`, and `mobile-i2p` when they
apply.

Then run `deploy plan` for a concise checklist:

```sh
python3 -m ampg --config gateway.toml deploy plan --profile vps-full
```

For clearnet on a changing home/laptop address, use Dynamic DNS planning:

```sh
python3 -m ampg --config gateway.toml dns plan --mode dynamic --behind-router
```

## Minimal Wownero pilot config

```toml
[gateway]
state_dir = "/var/lib/ampg"
cache_dir = "/var/cache/ampg"
run_dir = "/run/ampg"
user = "ampg"

[[site]]
id = "wownero"
domain = "wownero.org"

[site.source]
kind = "static-html"
path = "../wownero.org-website"
canonical_url = "https://wownero.org"

[site.outputs]
root = "/var/www/ampg/wownero"
plan_root = "/var/lib/ampg/plans"

[site.interactions]
default_tier = "static"
deny_routes = ["/admin/*", "/internal/*", "/webhooks/*"]

[[site.interactions.route]]
match = "/checkout/*"
tier = "transactional"
identity = "http-session"
payments = "server-invoice"

[[site.interactions.route]]
match = "/admin/*"
tier = "internal"
public_allowed = false

[site.protocols.clearnet]
enabled = true
renderer = "clearnet"
daemon = "nginx"
daemon_policy = "adopt"

[site.protocols.tor]
enabled = true
renderer = "privacy-html"
daemon = "tor"
daemon_policy = "auto"
local_port = 18080
onion_location = "auto"
max_asset_bytes = 1048576
script_policy = "strip"

[site.protocols.i2p]
enabled = false
renderer = "privacy-html"
daemon = "i2pd"
daemon_policy = "auto"
local_port = 18081
keys_file = "wownero-web.dat"
tunnel_name = "wownero-web"
max_asset_bytes = 1048576
script_policy = "strip"

[site.protocols.gemini]
enabled = true
renderer = "gemtext"
daemon = "agate"
daemon_policy = "auto"
port = 1965
max_asset_bytes = 1048576

[site.protocols.ipfs]
enabled = false
renderer = "clearnet"
daemon = "ipfs"
daemon_policy = "auto"
cid = ""

[site.protocols.reticulum]
enabled = false
renderer = "micron"
daemon = "rnsd"
daemon_policy = "auto"
aspect = "web"
```

## Defaults

Selected protocols default to `daemon_policy = "auto"` unless the protocol is clearnet.
Clearnet defaults to `adopt`, because most operators already have a web server and TLS
workflow.

| Protocol | Default renderer | Default daemon | Default policy |
| --- | --- | --- | --- |
| clearnet | `clearnet` | `nginx` | `adopt` |
| tor | `privacy-html` | `tor` | `auto` |
| i2p | `privacy-html` | `i2pd` | `auto` |
| gemini | `gemtext` | `agate` | `auto` |
| ipfs | `clearnet` | `ipfs` | `auto` |
| reticulum | `micron` | `rnsd` | `auto` |

## Gateway paths

`[gateway]` paths are resolved relative to `gateway.toml` when they are not absolute.

`state_dir`
: AMPG-owned durable state. Managed daemon identities, generated transport state, daemon
  logs, daemon-written addresses, and the captured address registry live here.

`cache_dir`
: Rebuildable intermediate data.

`run_dir`
: Runtime sockets, pid files, and process metadata for managed daemons.

`user`
: Preferred service user emitted into generated managed-daemon artifacts.

Transport URLs are resolved in this order:

1. Explicit protocol config such as `fixture_url`, `browser_url`, `onion_url`, `i2p_url`,
   `gemini_url`, `rns_url`, `ipfs_url`, or `cid`.
2. Captured state from `ampg addresses capture` or `ampg addresses set`.
3. A derived URL for clearnet/Gemini or a deterministic placeholder for identity-based
   transports whose final address is not known yet.

Use `address_file` on a protocol target when an adopted daemon writes its public hostname
outside AMPG's managed state layout.

## Renderer defaults

`privacy-html` removes:

- `<script>` blocks and event handler attributes.
- remote fonts, analytics, and third-party embeds.
- localStorage/sessionStorage assumptions.
- non-local asset references unless explicitly allowed.
- JavaScript files when `script_policy = "strip"`.
- assets larger than `max_asset_bytes`.

`gemtext` defaults:

- one `.gmi` page per HTML or Markdown page.
- inline links emitted after the paragraph that referenced them.
- images and PDFs emitted as links with file size metadata when known.
- local `.html` links rewritten to `.gmi`.
- JavaScript, CSS, source maps, and oversized assets skipped.

`micron` defaults:

- one `.mu` page per HTML page.
- headings, lists, links, and image references converted to terminal-safe text.
- local `.html` links rewritten to `.mu`.
- JavaScript, CSS, source maps, and oversized assets skipped.

## Daemon policy values

`external`
: Build outputs and print config. Never inspect, write, start, or reload daemons.

`adopt`
: Use a configured or detected daemon. Fail with a clear diagnostic if missing.

`manage`
: Create an AMPG-owned daemon instance and supervise it.

`auto`
: Adopt a healthy daemon when one is found. Otherwise create an AMPG-owned instance.

## Interactive app config

Applications can declare route groups and upstreams. AMPG only exposes the tiers each
transport can safely support.

```toml
[[site]]
id = "shop_platform"
domain = "example-shop.net"

[site.source]
kind = "reverse-proxy"
upstream = "http://127.0.0.1:8000"
openapi = "http://127.0.0.1:9000/openapi.json"

[site.interactions]
default_tier = "interactive-lite"
route_manifest = "./routes.json"
session_policy = "http-only-cookie"
deny_routes = ["/admin/*", "/api/internal/*", "/webhooks/*"]

[[site.interactions.route]]
match = "/admin/*"
tier = "internal"

[[site.interactions.route]]
match = "/checkout/*"
tier = "transactional"
identity = "http-session"
payments = "server-invoice"

[[site.interactions.route]]
match = "/catalog/*"
tier = "interactive-lite"

[site.protocols.tor]
enabled = true
renderer = "privacy-html"
daemon_policy = "auto"
allow_javascript = false

[site.protocols.gemini]
enabled = true
renderer = "gemtext"
daemon_policy = "auto"
max_tier = "interactive-lite"
```

`max_tier` is a hard cap. If a route needs a higher tier than the protocol allows, AMPG
omits it or renders a safe alternate page.

## Route manifests

Applications can generate a JSON route manifest instead of hand-maintaining every route
group in TOML. Paths are resolved relative to `gateway.toml`; inline TOML routes are
appended after manifest routes.

The public schema is committed at `schemas/ampg.route-manifest.v1.schema.json`.
Applications can validate generated manifests before AMPG config parsing:

```sh
python3 tools/generate_route_manifest.py examples/route-catalog.json examples/route-manifest.json
python3 -m ampg route-manifest validate routes.json
```

`examples/route-catalog.json` is a neutral app-side input shape. Real framework adapters
can replace it with generated route data from the application's router, then emit the same
AMPG route-manifest contract.

```json
{
  "schema": "ampg.route-manifest.v1",
  "default_tier": "interactive-lite",
  "deny_routes": ["/admin/*", "/api/internal/*", "/webhooks/*"],
  "routes": [
    {"match": "/play/*"},
    {
      "match": "/checkout/*",
      "tier": "transactional",
      "identity": "http-session",
      "payments": "server-invoice"
    },
    {
      "match": "/webhooks/*",
      "tier": "internal",
      "public_allowed": false
    }
  ]
}
```

Route entries use the same fields as `[[site.interactions.route]]`. The manifest should
describe public intent only; credentials, keys, deployment notes, and private hostnames do
not belong in it.

## Protocol-only deployments

Enabled protocols are independent. A config can omit clearnet entirely and publish only
to I2P, Tor, Gemini, IPFS, Reticulum, or any combination of supported targets.

## Deployment profiles

Profiles are named command defaults stored in `gateway.toml`. They can select enabled
protocols, set a default platform provider, and turn on safe plan artifact writes.

```toml
[profiles.mobile-i2p]
description = "User-space I2P-only deployment for Android/Termux-style hosts."
protocols = ["i2p"]
platform = "android-termux"

[profiles.vps-full]
description = "Full VPS deployment."
protocols = ["clearnet", "tor", "i2p", "gemini"]
platform = "linux-systemd"
write_artifacts = true
```

Use profiles with operational commands:

```sh
python3 -m ampg --config gateway.toml build --profile mobile-i2p
python3 -m ampg --config gateway.toml apply --dry-run --profile mobile-i2p
```

Explicit `--protocol` and `--platform` flags override profile defaults for that command.

For an existing HTML site that should publish only to I2P:

```toml
[[site]]
id = "example_i2p_only"
domain = "example.org"

[site.source]
kind = "static-html"
path = "../example.org"

[site.outputs]
root = "/var/www/ampg/example"
plan_root = "/var/lib/ampg/plans"

[site.protocols.i2p]
enabled = true
renderer = "privacy-html"
daemon = "i2pd"
daemon_policy = "auto"
local_port = 18081
keys_file = "example-web.dat"
tunnel_name = "example-web"
max_asset_bytes = 524288
script_policy = "strip"
```

This builds only the I2P output root and only the I2P/nginx plan snippets.

For IPFS, use the `clearnet` renderer to create a static output tree that can be served
through a local gateway or pinned by a later publishing step.

## Plan artifacts

`ampg plan` prints expected artifact paths. `ampg plan --write-artifacts` writes
reviewable snippets under `site.outputs.plan_root`.

Generated snippets are not installed by `plan`:

- nginx server blocks for static HTTP roots.
- Tor hidden-service snippets for loopback HTTP targets.
- i2pd server tunnel snippets for I2P web publishing.
- Agate plan values for Gemini publishing.

I2P web tunnels should use a web-specific key file such as `wownero-web.dat`; AMPG does
not reuse daemon RPC/P2P tunnel keys for web publishing.

## Reusable checklist

- [ ] Keep paths explicit in production configs.
- [ ] Use `ampg plan` before `ampg apply`.
- [ ] Use `daemon_policy = "external"` for package-maintainer examples.
- [ ] Use `daemon_policy = "auto"` for single-box deployments.
