# Wownero Integration

> Status: draft | Updated 2026-07-05 | Applies to: Wownero static site publishing

The Wownero integration exercises AMPG against a real public static site. The source is
the existing `wownero.org` website checked out next to this repository as
`../wownero.org-website`.

## Objective

Start with the existing clearnet site, preserve the rich web output, and generate
transport-specific variants with defaults:

- clearnet: faithful static site output.
- Tor: privacy-hardened static HTML.
- I2P: privacy-hardened static HTML.
- Gemini: text-first `.gmi` pages.
- Reticulum: compact Micron `.mu` pages.

## Source Adapter

The Wownero site is a static HTML/CSS/JS tree:

- top-level pages such as `index.html`, `mining.html`, `emission.html`, and
  `wownero-wallet-generator.html`.
- local CSS, JavaScript, image, PDF, text, and icon assets.
- JavaScript-driven translation and UI behavior.
- an `onion-location` meta tag in `index.html`.

This makes `static-html` the right source adapter. Markdown migration is optional and
must not be required for AMPG adoption.

## Generated Outputs

```text
/var/www/ampg/wownero/
  clearnet/
    index.html
    css/
    js/
    img/
  tor/
    index.html
    mining.html
    emission.html
  i2p/
    index.html
    mining.html
    emission.html
  gemini/
    index.gmi
    mining.gmi
    emission.gmi
  reticulum/
    index.mu
    mining.mu
    emission.mu
```

## Renderer Behavior

### Clearnet

Copy the source tree by default, excluding VCS/editor clutter, hidden private files, and
backup artifacts.

### Tor and I2P

Use `privacy-html`:

- remove JavaScript.
- remove inline event handlers.
- remove inline styles.
- keep local CSS only when configured.
- preserve local links to PDFs, text files, and reasonably sized images.
- preserve or generate onion/I2P location metadata only when configured.

### Gemini

Use `gemtext`:

- extract page title, headings, paragraphs, lists, and links.
- emit links near the paragraph that referenced them.
- convert large media to plain download links.
- skip repeated navigation noise.

### Reticulum

Use `micron`:

- prioritize short informational pages.
- omit heavy images by default.
- generate compact navigation.
- treat downloadable files as links with size hints.

## Daemon Policy

Recommended defaults:

```toml
[site.protocols.clearnet]
enabled = true
daemon_policy = "adopt"

[site.protocols.tor]
enabled = true
daemon_policy = "auto"

[site.protocols.i2p]
enabled = true
daemon_policy = "auto"

[site.protocols.gemini]
enabled = false
daemon_policy = "auto"

[site.protocols.reticulum]
enabled = false
daemon_policy = "auto"
```

## Acceptance Criteria

- `ampg plan` identifies the Wownero source tree and selected protocols.
- `ampg build` creates clearnet and Tor output without requiring Markdown.
- Tor output contains no `<script>` tags or inline event handlers.
- Generated Gemini output has readable headings, paragraphs, and links.
- Generated Micron output fits terminal-first browsing.
- `ampg plan` clearly says whether each selected daemon is adopted or managed.

## Local Commands

```sh
python3 -m ampg --config examples/wownero.gateway.toml plan
python3 -m ampg --config examples/wownero.gateway.toml build
python3 -m ampg --config examples/i2p-only.gateway.toml plan
python3 -m ampg --config examples/i2p-only.gateway.toml build
```

## Reusable checklist

- [ ] Build from `../wownero.org-website` using `source.kind = "static-html"`.
- [ ] Preserve clearnet output first.
- [ ] Generate Tor `privacy-html` and verify active content is stripped.
- [ ] Add Gemini conversion fixtures.
- [ ] Add Reticulum/Micron conversion fixtures.
- [ ] Enable I2P and Reticulum daemon management only after static outputs are stable.
