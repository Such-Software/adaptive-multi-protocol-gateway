# Configuration

> Status: draft | Updated 2026-07-05 | Applies to: `gateway.toml`

AMPG is configured from one TOML file. The file declares global paths, sites, source
adapters, render targets, and daemon policy.

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
daemon = "caddy"
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
| clearnet | `clearnet` | `caddy` | `adopt` |
| tor | `privacy-html` | `tor` | `auto` |
| i2p | `privacy-html` | `i2pd` | `auto` |
| gemini | `gemtext` | `agate` | `auto` |
| ipfs | `clearnet` | `ipfs` | `auto` |
| reticulum | `micron` | `rnsd` | `auto` |

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

- one `.mu` page per high-value page.
- headings converted to terminal-safe emphasis.
- images omitted unless the site config opts into small downloadable assets.

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

## Protocol-only deployments

Enabled protocols are independent. A config can omit clearnet entirely and publish only
to I2P, Tor, Gemini, IPFS, Reticulum, or any combination of supported targets.

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
