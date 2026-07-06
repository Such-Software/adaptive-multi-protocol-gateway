# Architecture

> Status: draft | Updated 2026-07-05 | Applies to: AMPG core

AMPG is a compiler plus an ingress manager. The compiler turns one site into a
protocol-neutral content graph, then renders protocol-specific outputs. The ingress
manager connects those outputs to daemons selected by the operator.

## System shape

```text
source site
  -> source adapter
  -> content graph
  -> render profiles
  -> output roots
  -> daemon adapters
  -> clearnet / Tor / I2P / Gemini / IPFS / Reticulum
```

## Source adapters

`static-html`
: Reads an existing static site tree. AMPG preserves the clearnet version, parses HTML
  into a content graph, rewrites local links, and extracts text for Gemini and Micron
  renderers. This is the default path for the Wownero pilot.

`markdown`
: Reads Markdown plus frontmatter. This is the cleanest authoring model for new sites.

`ssg-output`
: Reads the built output of another static site generator. AMPG does not own that
  generator; it adapts the generated files.

## Source quality

AMPG gets better results from semantic, accessible source documents. Authors should use
one `h1`, ordered heading levels, meaningful link text, alt text for images, and ordinary
flowing document structure before decorative layout. This keeps clearnet accessible and
gives constrained renderers a clean outline for Gemtext, Micron, and other text-first
targets.

`ampg audit` reports source-quality warnings. The audit is advisory by default and can be
made strict in CI with `--fail-on-warn`.

## Content graph

The internal graph is intentionally small:

- `Site`: domain, aliases, selected protocols, source metadata.
- `Page`: route, title, language, headings, body blocks, links, assets.
- `Asset`: path, media type, size, dimensions, privacy policy.
- `Link`: target, relation, transport compatibility.

Renderers should not scrape each other. They read the content graph and write their
own output.

## Render profiles

`clearnet`
: High-fidelity output. Static HTML sources are copied by default. Markdown sources render
  to full HTML and may include CSS, JavaScript, web fonts, and rich media.

`privacy-html`
: Tor and I2P default. Removes JavaScript, tracking pixels, external fonts, third-party
  embeds, remote assets, and stateful browser storage assumptions. CSS is local and small.

`gemtext`
: Gemini output. Converts headings, paragraphs, lists, code blocks, and links to `.gmi`.
  Inline links become block links near the paragraph by default.

`clearnet` for IPFS
: Static web output suitable for a local IPFS gateway or later pinning. IPFS is treated
  as content-addressed distribution, not an anonymity layer.

`micron`
: Reticulum/Nomad output. Produces terminal-oriented Micron markup with small pages,
  plain links, and no heavy media by default.

## Daemon adapters

Daemon adapters provide a common interface:

- `detect`: find existing services, ports, config files, and health endpoints.
- `plan`: decide whether to adopt, manage, or fail.
- `render_config`: produce config snippets and complete managed configs.
- `apply`: write approved managed config and start or reload services.
- `health`: verify the selected transport can serve the generated output.
- `manifest`: emit AMPB route/profile expectations for generated fixtures.

Adapters must be conservative. They do not modify non-AMPG config without showing a
plan first, and managed config lives under AMPG-owned state directories.

## Platform providers

Platform providers decide what daemon management means on the current host. AMPG detects
systemd Linux, user-space Linux, macOS user launchd, Termux-style Android, and unknown
platforms. A provider can allow managed daemons without allowing system config writes.

Operators can override detection for dry runs:

```sh
python3 -m ampg --config gateway.toml doctor --platform linux-systemd
python3 -m ampg --config gateway.toml doctor --platform android-termux
```

This keeps the same gateway config portable across a VPS, laptop, old phone, or manual
render-only environment while making daemon ownership decisions explicit.

## Deploy plan

`ampg deploy plan` is the operator-friendly layer over build, doctor, install-plan,
approvals, address capture, and apply dry-run. It emits stage rows with `ready`, `todo`,
`review`, `blocked`, or `skipped` status and short next-step commands. It is read-only.

## Clearnet reachability

`ampg dns plan` handles the public web edge for clearnet deployments. Static hosts use
A/AAAA records. Dynamic or behind-router hosts can use Dynamic DNS, provider-specific
apex aliases, API-updated records, port forwarding, IPv6, reverse tunnels, or DNS-01
certificate validation. Provider and router automation should remain opt-in.

## Activation plan

`ampg apply --dry-run` turns daemon status and generated config artifacts into an ordered
activation sequence. Each enabled protocol gets output, artifact, daemon, and health
steps, plus an address step when AMPG must capture or confirm a generated transport
identity. With `--write-artifacts`, it also prints copies from approved artifacts into
managed state and planned supervisor start/reload actions. The command emits an
`AMPG_APPLY_PREFLIGHT` verdict across activation, state-copy, and supervisor rows.
Blocked or unapproved preflight items stop mutation before any live apply path can touch
services.

`ampg deploy apply --stage state` is the narrow live stage for managed state. It reads
the same approved artifact plan, refuses missing, stale, or unapproved inputs, and copies
only approved generated daemon config into AMPG-owned state. Service installation,
supervisor registration, daemon start, address capture, and health verification remain
separate stages.

The dry-run command is intentionally stricter than `doctor`: missing generated output is
blocked during activation, because AMPG must not point a transport at an unbuilt output
root.

## Install plan

`ampg install-plan` translates managed daemon decisions into package, state, config,
supervisor, and health-check steps. It does not install packages, create directories, or
start services. The output is a reviewable bridge between daemon ownership decisions and
future live apply support.

With `--write-artifacts`, install-plan writes managed config and supervisor files under
the configured `plan_root`; those files are review artifacts, not installed service
state. `ampg approvals approve` records reviewed artifact digests under
`gateway.state_dir`. Generated managed-daemon configs point runtime state at
`gateway.state_dir`.

Tor and I2P HTTP publishing include the transport daemon and the loopback web-serving
layer in the install plan, because the hidden service or tunnel must have a local HTTP
target.

## Health plan

`ampg health-plan` turns fixture manifests into post-start verification checks. Published
mode targets real transport URLs. Preview mode rewrites checks to loopback HTTP preview
endpoints so local generated output can be verified before live daemons exist.

Missing generated output blocks health checks. Placeholder transport addresses are
reported for review, because the operator must capture the real onion, I2P destination,
or other transport identity before published checks are exact.

## Interaction boundary

v1 is static-first, but the architecture reserves a path for interactive applications.
Interactivity is declared per route group:

- `static`: files only.
- `forms`: server-rendered actions and full-page responses.
- `sessions`: authenticated flows with strict session policy.
- `realtime`: rich browser/admin interfaces; HTTP transports only.
- `internal`: workers, webhooks, private admin APIs; never published automatically.

Dynamic support comes through application adapters that expose action metadata. HTTP
transports can use normal forms or reverse proxies. Gemini uses status-code input prompts
for simple actions. Reticulum uses page scripts or Micron action links. The core compiler
must remain useful when no application adapter is configured.

## Reusable checklist

- [ ] Add a source adapter only when it can produce the content graph.
- [ ] Add a renderer only when it reads the graph directly.
- [ ] Add a daemon adapter only with `detect`, `plan`, `render_config`, `apply`, and `health`.
- [ ] Keep privacy defaults stricter than clearnet defaults.
