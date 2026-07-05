# Generated Config Schema

> Status: generated | Updated by `python3 -m ampg docs generate` | Applies to: AMPG

This file is generated from code. Do not edit it by hand.

| Section | Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| site | `id` | string | yes | - | Stable site identifier used in output paths. |
| site | `domain` | string | yes | - | Canonical public domain for the site. |
| site.source | `kind` | enum | yes | static-html | Source adapter kind. |
| site.source | `path` | path | yes | - | Source tree path. |
| site.source | `canonical_url` | url | no | - | Canonical clearnet URL. |
| site.outputs | `root` | path | yes | - | Generated output root. |
| site.outputs | `plan_root` | path | no | ../dist/ampg-plan | Generated plan artifact root. |
| site.interactions | `default_tier` | enum | no | static | Default interaction tier for routes. |
| site.interactions | `deny_routes` | array<string> | no | [] | Route patterns that must not be published. |
| site.protocols.<name> | `enabled` | boolean | no | false | Whether this protocol target is built and planned. |
| site.protocols.<name> | `renderer` | enum | no | <protocol> | Renderer profile to use for this protocol. |
| site.protocols.<name> | `daemon` | enum | no | protocol default | Ingress daemon adapter. |
| site.protocols.<name> | `daemon_policy` | enum | no | protocol default | Whether AMPG adopts, manages, or only renders config. |
| site.protocols.<name> | `max_asset_bytes` | integer | no | 1048576 | Maximum asset size copied by privacy-html render targets. |
| site.protocols.<name> | `script_policy` | enum | no | strip | Script handling policy for privacy-html render targets. |
