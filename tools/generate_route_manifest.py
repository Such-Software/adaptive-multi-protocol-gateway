#!/usr/bin/env python3
"""Generate an AMPG route manifest from a small app route catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ampg.route_manifest import ROUTE_MANIFEST_SCHEMA, validate_route_manifest  # noqa: E402


PASSTHROUGH_FIELDS = ("tier", "identity", "payments", "realtime", "public_allowed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path, help="Input app route catalog JSON.")
    parser.add_argument("output", type=Path, help="Output ampg.route-manifest.v1 JSON.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if output differs instead of writing it.",
    )
    args = parser.parse_args(argv)

    try:
        catalog = _load_json(args.catalog)
        manifest = route_manifest_from_catalog(catalog)
        content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        if args.check:
            existing = args.output.read_text(encoding="utf-8")
            if existing != content:
                print(
                    f"ROUTE_MANIFEST_GENERATE status=stale output={args.output}",
                    file=sys.stderr,
                )
                return 1
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
        print(
            "ROUTE_MANIFEST_GENERATE "
            f"status=ok catalog={args.catalog} output={args.output} routes={len(manifest['routes'])}"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should print concise failures.
        print(f"ROUTE_MANIFEST_GENERATE status=error message=\"{exc}\"", file=sys.stderr)
        return 1


def route_manifest_from_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(catalog, dict):
        raise ValueError("catalog must be a JSON object")
    routes = catalog.get("routes")
    if not isinstance(routes, list):
        raise ValueError("catalog.routes must be an array")

    manifest: dict[str, Any] = {
        "schema": ROUTE_MANIFEST_SCHEMA,
        "routes": [_route_policy(route, index) for index, route in enumerate(routes)],
    }
    if "default_tier" in catalog:
        manifest["default_tier"] = catalog["default_tier"]
    if "deny_routes" in catalog:
        manifest["deny_routes"] = catalog["deny_routes"]

    issues = validate_route_manifest(manifest)
    if issues:
        joined = "; ".join(f"{issue.path}: {issue.message}" for issue in issues)
        raise ValueError(f"generated route manifest is invalid: {joined}")
    return manifest


def _route_policy(route: Any, index: int) -> dict[str, Any]:
    if not isinstance(route, dict):
        raise ValueError(f"catalog.routes[{index}] must be an object")
    path = route.get("path", route.get("match"))
    if not isinstance(path, str) or not path:
        raise ValueError(f"catalog.routes[{index}].path must be a non-empty string")

    policy: dict[str, Any] = {"match": path}
    for field in PASSTHROUGH_FIELDS:
        if field in route:
            policy[field] = route[field]
    return policy


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    sys.exit(main())
