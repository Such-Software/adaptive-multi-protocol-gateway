# Autodocs And Drift Gates

> Status: draft | Updated 2026-07-11 | Applies to: AMPG generated docs

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

`schemas/ampg.route-manifest.v1.schema.json`
: Generated from the route-manifest validator. App repos can use it to emit and validate
  `ampg.route-manifest.v1` without depending on AMPG internals.

`openapi.json`
: Generated if AMPG exposes a local control API for status, builds, plans, and daemon
  health.

## Drift gates

CI should run:

```sh
python3 -m ampg docs generate
python3 -m ampg docs generate --check
git diff --exit-code docs/generated schemas openapi.json
python3 tools/docs_check.py
```

`python3 tools/docs_check.py` verifies:

- every Markdown file starts with a `> Status:` header.
- internal links resolve.
- local links stay inside the repository.
- public docs do not name private fixture targets.
- public docs do not contain obvious private-key blocks, common API tokens, or assigned
  secret values.

`python3 -m ampg docs generate --check` verifies that generated docs and schemas match
the code-owned metadata.

## Public/private boundary

Public docs include reusable contracts, generated references, and concise operator-facing
guidance. Private docs are ignored under `docs/private/` and are the place for
non-public planning, deployment inventory, working notes, and real host-specific
material.

Public docs can include example domains, ports, and fake keys. Real daemon keys,
production paths with secrets, private host inventory, and internal planning notes belong
outside the public repo.

## Reusable checklist

- [ ] Generate config schema docs from code.
- [ ] Generate daemon adapter docs from registered adapters.
- [ ] Generate renderer docs from renderer defaults.
- [ ] Generate route-manifest JSON Schema from code.
- [ ] Commit generated artifacts.
- [ ] Fail CI when regeneration produces a diff.
