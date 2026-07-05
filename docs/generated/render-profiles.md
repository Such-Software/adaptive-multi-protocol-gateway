# Generated Render Profiles

> Status: generated | Updated by `python3 -m ampg docs generate` | Applies to: AMPG

This file is generated from code. Do not edit it by hand.


## clearnet

High-fidelity static web output.

- Output: HTML/CSS/JS/assets

Defaults:
- Copies source files except hidden/editor/VCS clutter.
- Keeps local JavaScript and rich media.
- Writes only to AMPG-marked generated output roots.

## privacy-html

Static HTML for Tor and I2P.

- Output: HTML/CSS/assets

Defaults:
- Removes active tags: script, style.
- Removes inline event handlers such as onclick and onload.
- Removes inline style attributes.
- Skips JavaScript and source-map files.
- Skips oversized assets above max_asset_bytes.
- Removes remote src/poster/link asset references.
