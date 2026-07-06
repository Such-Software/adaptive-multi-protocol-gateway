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
| site.interactions | `route_manifest` | path | no | - | JSON route manifest generated or maintained by the application. |
| site.interactions.route | `match` | glob | no | - | Route pattern for an explicit interaction policy. |
| site.interactions.route | `tier` | enum | no | site.interactions.default_tier | Interaction tier for a route group. |
| site.interactions.route | `identity` | enum | no | none | Identity adapter required by a route group. |
| site.interactions.route | `payments` | enum | no | none | Payment adapter required by a route group. |
| site.interactions.route | `realtime` | boolean | no | false | Whether a route group requires live state or streaming updates. |
| site.interactions.route | `public_allowed` | boolean | no | true | Whether this route group may be emitted into public protocol outputs. |
| site.protocols.<name> | `enabled` | boolean | no | false | Whether this protocol target is built and planned. |
| site.protocols.<name> | `renderer` | enum | no | <protocol> | Renderer profile to use for this protocol. |
| site.protocols.<name> | `daemon` | enum | no | protocol default | Ingress daemon adapter. |
| site.protocols.<name> | `daemon_policy` | enum | no | protocol default | Whether AMPG adopts, manages, or only renders config. |
| site.protocols.<name> | `max_asset_bytes` | integer | no | 1048576 | Maximum asset size copied by privacy-html render targets. |
| site.protocols.<name> | `script_policy` | enum | no | strip | Script handling policy for privacy-html render targets. |
| site.protocols.<name> | `max_tier` | enum | no | transport default | Maximum interaction tier this protocol target may expose. |
| profiles.<name> | `description` | string | no | - | Human-readable deployment profile description. |
| profiles.<name> | `protocols` | array<string> | no | all enabled protocols | Enabled protocols selected by this deployment profile. |
| profiles.<name> | `platform` | enum | no | detected platform | Platform provider used by status, doctor, and apply when not overridden. |
| profiles.<name> | `write_artifacts` | boolean | no | false | Whether plan/apply dry-run writes review artifacts by default. |
