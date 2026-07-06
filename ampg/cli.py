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
        config = load_config(args.config)
        if args.command == "plan":
            return _cmd_plan(config, write_artifacts=args.write_artifacts)
        if args.command == "build":
            return _cmd_build(config)
        if args.command == "manifest":
            return _cmd_manifest(config)
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
