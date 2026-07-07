# Visual Guide

> Status: draft | Updated 2026-07-07 | Applies to: AMPG operators and contributors

This guide shows the core AMPG flows and common deployment topologies. Diagrams use
Mermaid so they render in GitHub Markdown and can later be reused by a public docs site.

## Build Flow

AMPG starts from one canonical site and renders transport-appropriate outputs. Rich web
output can stay rich on clearnet, while constrained or privacy-oriented transports get
safer defaults.

```mermaid
flowchart LR
  source["Source site<br/>static HTML, Markdown, or generated output"]
  graph["AMPG content graph"]
  clearnet["clearnet<br/>HTML/CSS/assets"]
  tor["Tor<br/>privacy HTML"]
  i2p["I2P<br/>privacy HTML"]
  gemini["Gemini<br/>Gemtext"]
  ipfs["IPFS<br/>static tree"]
  reticulum["Reticulum<br/>Micron"]
  manifest["fixture manifest<br/>routes and expected transports"]

  source --> graph
  graph --> clearnet
  graph --> tor
  graph --> i2p
  graph --> gemini
  graph --> ipfs
  graph --> reticulum
  clearnet --> manifest
  tor --> manifest
  i2p --> manifest
  gemini --> manifest
  ipfs --> manifest
  reticulum --> manifest
```

## Deployment Spine

Live deploy work is split into narrow stages. Each stage has a dry-run form first, and
live stages require explicit confirmation.

```mermaid
flowchart TD
  init["init site"]
  build["build outputs"]
  plan["install-plan<br/>review package, state, supervisor steps"]
  packages["deploy apply --stage packages<br/>install selected daemon packages"]
  approve["approvals approve<br/>record reviewed artifact digests"]
  state["deploy apply --stage state<br/>copy approved config into AMPG state"]
  supervisor["deploy apply --stage supervisor<br/>install AMPG-named service files"]
  start["deploy apply --stage start<br/>start AMPG-owned services"]
  addresses["deploy apply --stage addresses<br/>capture daemon-written public addresses"]
  health["deploy apply --stage health<br/>verify published fixtures"]

  init --> build --> plan --> packages --> approve --> state --> supervisor --> start --> addresses --> health
```

## Ownership Boundaries

AMPG tries to keep operator-owned services, AMPG-owned generated state, and
daemon-written identity material distinct.

```mermaid
flowchart LR
  operator["Operator-owned<br/>DNS, router, existing reverse proxy, adopted daemons"]
  ampg["AMPG-owned<br/>generated outputs, reviewed artifacts, state registry"]
  daemon["Daemon-written<br/>onion hostname, I2P destination, keys, logs"]
  public["Public routes<br/>clearnet, Tor, I2P, Gemini, IPFS, Reticulum"]

  operator -- may be adopted by policy --> ampg
  ampg -- starts or configures managed service --> daemon
  daemon -- writes transport identity --> ampg
  ampg -- publishes selected outputs --> public
```

## VPS Multi-Transport

A normal VPS is the cleanest full-stack topology. AMPG can adopt existing daemons or
manage missing ones, while clearnet DNS and TLS remain operator-controlled by default.

```mermaid
flowchart TB
  dns["DNS provider<br/>A/AAAA/CNAME records"]
  internet["public internet"]
  vps["VPS host"]
  ampg["AMPG"]
  outputs["/var/www/ampg/site outputs"]
  nginx["nginx or Caddy<br/>clearnet ingress"]
  tor["Tor daemon<br/>onion service"]
  i2p["i2pd<br/>server tunnel"]
  gemini["Gemini daemon"]
  users["Visitors and AMPB checks"]

  dns --> internet --> vps
  vps --> ampg --> outputs
  outputs --> nginx
  outputs --> tor
  outputs --> i2p
  outputs --> gemini
  nginx --> users
  tor --> users
  i2p --> users
  gemini --> users
```

## Home Server Behind A Router

Behind-router clearnet publishing may need port forwarding, IPv6, Dynamic DNS, a reverse
tunnel, or DNS-01 certificate validation. Tor and I2P can often avoid inbound clearnet
port forwarding.

```mermaid
flowchart LR
  visitor["Visitor"]
  dns["DNS or Dynamic DNS"]
  router["Home router<br/>NAT and firewall"]
  host["Laptop or mini server"]
  ampg["AMPG"]
  clearnet["clearnet web server"]
  tor["Tor onion service"]
  i2p["I2P server tunnel"]

  visitor --> dns --> router --> clearnet
  router --> host
  host --> ampg
  ampg --> clearnet
  ampg --> tor
  ampg --> i2p
  visitor -. no router port forward required for many cases .-> tor
  visitor -. no router port forward required for many cases .-> i2p
```

## Android Or Termux Server

An old phone can be useful for mobile-server experiments. AMPG plans user-space daemons,
Termux package installs, and service scripts, while battery policy, storage, and public
reachability remain device-owned.

```mermaid
flowchart TB
  phone["Android phone<br/>Termux"]
  ampg["AMPG CLI"]
  pkg["pkg install<br/>tor, i2pd, nginx"]
  state["Termux state<br/>AMPG config, keys, logs"]
  services["termux-services<br/>AMPG-named daemons"]
  transports["Tor/I2P/Gemini/Reticulum routes"]
  checks["health checks<br/>fixture URLs"]

  phone --> ampg
  ampg --> pkg
  ampg --> state
  state --> services
  services --> transports
  transports --> checks
```

## Single-Transport Deployments

AMPG should also work when the operator wants only one selected transport. This is useful
for I2P-only, Tor-only, Gemini-only, or Reticulum-focused deployments.

```mermaid
flowchart LR
  source["existing site"]
  ampg["AMPG"]
  selected["selected transport only"]
  daemon["adopted or managed daemon"]
  public["published route"]

  source --> ampg --> selected --> daemon --> public
```

## Browser Test Loop

AMPG writes fixture manifests so a companion browser or checker can verify that each
route uses the expected transport profile.

```mermaid
sequenceDiagram
  participant Site as Source site
  participant AMPG as AMPG
  participant Manifest as Fixture manifest
  participant AMPB as AMPB/browser checker
  participant Transport as Selected transport

  Site->>AMPG: build selected outputs
  AMPG->>Manifest: write route expectations
  AMPB->>Manifest: load fixtures
  AMPB->>Transport: request fixture URL through expected profile
  Transport-->>AMPB: return generated output
  AMPB-->>AMPG: report pass or failure
```

## Public Docs Site Path

The first public docs site should be generated from the public Markdown docs in this
repository. A GitHub Pages build can later reuse these Mermaid diagrams with MkDocs,
mdBook, or another static docs generator. Private strategy notes, deployment inventory,
and host-specific material should stay under private docs and outside any Pages build.

## Example Site Roles

`ampgateway.online`
: Public system guide. It explains AMPG concepts, transport flows, topologies, domain
  onboarding, and deploy stages. It should stay concise, visual, and operator-facing.

`ampgateway.site`
: Public demo site. It should behave like a real small site someone might deploy: static
  catalog, plain form fallback, optional clearnet enhancement, and comments in source
  that explain how the same content survives privacy HTML, Gemtext, and Micron outputs.

Both sites are source inputs consumed by AMPG. Clearnet output can remain visually rich;
Tor and I2P use privacy HTML; Gemini uses Gemtext; Reticulum uses Micron.
