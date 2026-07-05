# Autodocs And Drift Gates

> Status: draft | Updated 2026-07-05 | Applies to: AMPG generated docs

AMPG should publish concise hand-written docs and generate the parts that can drift from
code. Generated artifacts are committed, then checked in CI by regenerating and diffing.

## Generated artifacts

`docs/generated/config-schema.md`
: Generated from the `gateway.toml` schema. Includes fields, defaults, enum values, and
  examples.

`docs/generated/daemon-adapters.md`
: Generated from registered daemon adapters. Lists supported daemons, discovery paths,
  managed-state paths, health checks, and known limitations.

`docs/generated/render-profiles.md`
: Generated from renderer definitions. Lists stripped tags, asset limits, link modes,
  and defaults for each target.

`openapi.json`
: Generated if AMPG exposes a local control API for status, builds, plans, and daemon
  health.

## Drift gates

CI should run:

```sh
python3 -m ampg docs generate
python3 -m ampg docs generate --check
git diff --exit-code docs/generated openapi.json
python3 tools/docs_check.py
```

`ampg docs check` should verify:

- every Markdown file starts with a `> Status:` header.
- internal links resolve.
- generated docs are not edited by hand.
- public docs contain no private keys, onion keys, I2P keys, Reticulum identities, or
  local production secrets.

## Public/private boundary

Public docs include reusable contracts, generated references, and concise operator-facing
guidance. Private docs are ignored under `docs/private/` and are the place for strategy,
internal discussion, deployment inventory, working notes, tracking, timelines, and any
real host-specific material.

Public docs can include example domains, ports, and fake keys. Real daemon keys,
production paths with secrets, private host inventory, and internal planning notes belong
outside the public repo.

## Reusable checklist

- [ ] Generate config schema docs from code.
- [ ] Generate daemon adapter docs from registered adapters.
- [ ] Generate renderer docs from renderer defaults.
- [ ] Commit generated artifacts.
- [ ] Fail CI when regeneration produces a diff.
