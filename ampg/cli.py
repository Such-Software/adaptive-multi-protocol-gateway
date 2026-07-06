from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .audit import audit_gateway
from .build import build_gateway
from .config import load_config
from .docsgen import generate_docs
from .manifest import write_fixture_manifests
from .plan import plan_gateway, write_plan_artifacts
from .route_manifest import (
    load_route_manifest,
    route_manifest_schema_json,
    validate_route_manifest,
)
from .route_policy import RouteExposure, RouteIssue, route_exposures, route_issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ampg")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("gateway.toml"),
        help="Path to gateway TOML config.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    plan_parser = subcommands.add_parser("plan", help="Print a dry-run plan.")
    plan_parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="Write generated config snippets to the configured plan root.",
    )
    subcommands.add_parser("build", help="Build enabled protocol outputs.")
    subcommands.add_parser("manifest", help="Write AMPB fixture manifests.")
    routes_parser = subcommands.add_parser("routes", help="Explain route exposure policy.")
    routes_subcommands = routes_parser.add_subparsers(dest="routes_command", required=True)
    routes_subcommands.add_parser("explain", help="Print per-protocol route decisions.")
    routes_subcommands.add_parser(
        "validate",
        help="Fail when a public route has no compatible enabled protocol.",
    )
    manifest_parser = subcommands.add_parser(
        "route-manifest",
        help="Validate or print the app route manifest contract.",
    )
    manifest_subcommands = manifest_parser.add_subparsers(
        dest="route_manifest_command",
        required=True,
    )
    manifest_validate = manifest_subcommands.add_parser(
        "validate",
        help="Validate an ampg.route-manifest.v1 JSON file.",
    )
    manifest_validate.add_argument("path", type=Path, help="Route manifest JSON path.")
    manifest_schema = manifest_subcommands.add_parser(
        "schema",
        help="Print the JSON Schema for route manifests.",
    )
    manifest_schema.add_argument(
        "--output",
        type=Path,
        help="Write the JSON Schema to this path instead of stdout.",
    )
    audit_parser = subcommands.add_parser("audit", help="Audit source HTML quality.")
    audit_parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help="Exit non-zero when warnings are found.",
    )
    docs_parser = subcommands.add_parser("docs", help="Generate or check generated docs.")
    docs_subcommands = docs_parser.add_subparsers(dest="docs_command", required=True)
    docs_generate = docs_subcommands.add_parser("generate", help="Generate docs from code.")
    docs_generate.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated docs are stale instead of writing them.",
    )

    args = parser.parse_args(argv)

    try:
        if args.command == "docs":
            return _cmd_docs(args)
        if args.command == "route-manifest":
            return _cmd_route_manifest(args)
        config = load_config(args.config)
        if args.command == "plan":
            return _cmd_plan(config, write_artifacts=args.write_artifacts)
        if args.command == "build":
            return _cmd_build(config)
        if args.command == "manifest":
            return _cmd_manifest(config)
        if args.command == "routes":
            return _cmd_routes(config, args)
        if args.command == "audit":
            return _cmd_audit(config, fail_on_warn=args.fail_on_warn)
    except Exception as exc:  # noqa: BLE001 - CLI should print concise failures.
        print(f"AMPG status=error message={exc}", file=sys.stderr)
        return 1
    return 1


def _cmd_plan(config, *, write_artifacts: bool) -> int:
    for line in plan_gateway(config):
        artifact_text = ",".join(str(path) for path in line.artifacts) if line.artifacts else "-"
        print(
            "AMPG_PLAN "
            f"site={line.site_id} "
            f"protocol={line.protocol} "
            f"renderer={line.renderer} "
            f"output={line.output_root} "
            f"daemon={line.daemon} "
            f"policy={line.daemon_policy} "
            f"artifacts={artifact_text} "
            f"action=\"{line.action}\""
        )
    if write_artifacts:
        artifacts = write_plan_artifacts(config)
        for artifact in artifacts:
            print(f"AMPG_ARTIFACT path={artifact.path}")
    return 0


def _cmd_build(config) -> int:
    for result in build_gateway(config):
        extra = ""
        if result.privacy_stats is not None:
            stats = result.privacy_stats
            extra = (
                f" removed_active_tags={stats.removed_active_tags}"
                f" removed_event_handlers={stats.removed_event_handlers}"
                f" removed_inline_styles={stats.removed_inline_styles}"
                f" removed_remote_assets={stats.removed_remote_assets}"
            )
        print(
            "AMPG_BUILD "
            f"site={result.site_id} "
            f"protocol={result.protocol} "
            f"renderer={result.renderer} "
            f"output={result.output_root} "
            f"files={result.files_written}"
            f" skipped={result.files_skipped}"
            f"{extra}"
        )
    for manifest in write_fixture_manifests(config):
        print(
            "AMPG_MANIFEST "
            f"site={manifest.site_id} "
            f"path={manifest.path} "
            f"fixtures={manifest.fixture_count}"
        )
    return 0


def _cmd_manifest(config) -> int:
    for manifest in write_fixture_manifests(config):
        print(
            "AMPG_MANIFEST "
            f"site={manifest.site_id} "
            f"path={manifest.path} "
            f"fixtures={manifest.fixture_count}"
        )
    return 0


def _cmd_routes(config, args) -> int:
    exposures = route_exposures(config)
    issues = route_issues(config)
    for exposure in exposures:
        _print_route_exposure(exposure)
    for issue in issues:
        _print_route_issue(issue)
    print(
        "AMPG_ROUTE_SUMMARY "
        f"sites={len(config.sites)} "
        f"routes={sum(len(site.interactions.routes) for site in config.sites)} "
        f"decisions={len(exposures)} "
        f"exposed={sum(1 for exposure in exposures if exposure.status == 'exposed')} "
        f"skipped={sum(1 for exposure in exposures if exposure.status == 'skipped')} "
        f"issues={len(issues)}"
    )
    if args.routes_command == "validate" and issues:
        return 1
    return 0


def _cmd_route_manifest(args) -> int:
    if args.route_manifest_command == "schema":
        content = route_manifest_schema_json()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            print(f"AMPG_ROUTE_MANIFEST_SCHEMA path={args.output}")
        else:
            print(content, end="")
        return 0

    if args.route_manifest_command == "validate":
        try:
            data = load_route_manifest(args.path)
        except ValueError:
            try:
                import json

                data = json.loads(args.path.read_text(encoding="utf-8"))
                issues = validate_route_manifest(data)
            except Exception as exc:  # noqa: BLE001 - CLI should print concise failures.
                print(
                    "AMPG_ROUTE_MANIFEST "
                    f"path={args.path} status=error message=\"{exc}\"",
                    file=sys.stderr,
                )
                return 1
            for issue in issues:
                print(
                    "AMPG_ROUTE_MANIFEST_ISSUE "
                    f"path={args.path} json_path={issue.path} "
                    f"code={issue.code} message=\"{issue.message}\""
                )
            print(
                "AMPG_ROUTE_MANIFEST "
                f"path={args.path} status=fail issues={len(issues)}"
            )
            return 1

        print(
            "AMPG_ROUTE_MANIFEST "
            f"path={args.path} schema={data['schema']} routes={len(data['routes'])} status=ok"
        )
        return 0

    return 1


def _print_route_exposure(exposure: RouteExposure) -> None:
    print(
        "AMPG_ROUTE "
        f"site={exposure.site_id} "
        f"protocol={exposure.protocol} "
        f"route_index={exposure.route_index} "
        f"route=\"{exposure.match}\" "
        f"source={exposure.source} "
        f"tier={exposure.tier} "
        f"identity={exposure.identity} "
        f"payments={exposure.payments} "
        f"realtime={str(exposure.realtime).lower()} "
        f"public_allowed={str(exposure.public_allowed).lower()} "
        f"max_tier={exposure.max_tier} "
        f"status={exposure.status} "
        f"reason=\"{exposure.reason}\""
    )


def _print_route_issue(issue: RouteIssue) -> None:
    print(
        "AMPG_ROUTE_ISSUE "
        f"site={issue.site_id} "
        f"route_index={issue.route_index} "
        f"route=\"{issue.match}\" "
        f"source={issue.source} "
        f"tier={issue.tier} "
        f"code={issue.code} "
        f"message=\"{issue.message}\""
    )


def _cmd_audit(config, *, fail_on_warn: bool) -> int:
    issues = audit_gateway(config)
    for issue in issues:
        print(
            "AMPG_AUDIT "
            f"site={issue.site_id} "
            f"severity={issue.severity} "
            f"code={issue.code} "
            f"path={issue.path} "
            f"message=\"{issue.message}\""
        )
    print(f"AMPG_AUDIT_SUMMARY issues={len(issues)}")
    if issues and fail_on_warn:
        return 1
    return 0


def _cmd_docs(args) -> int:
    if args.docs_command == "generate":
        changed = generate_docs(Path.cwd(), check=args.check)
        changed_text = ",".join(str(path) for path in changed) if changed else "-"
        mode = "check" if args.check else "write"
        print(f"AMPG_DOCS status=ok mode={mode} changed={changed_text}")
        return 0
    return 1
