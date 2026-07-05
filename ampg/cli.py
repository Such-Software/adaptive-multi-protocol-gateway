from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .build import build_gateway
from .config import load_config
from .docsgen import generate_docs
from .plan import plan_gateway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ampg")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("gateway.toml"),
        help="Path to gateway TOML config.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("plan", help="Print a dry-run plan.")
    subcommands.add_parser("build", help="Build enabled protocol outputs.")
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
            return _cmd_plan(config)
        if args.command == "build":
            return _cmd_build(config)
    except Exception as exc:  # noqa: BLE001 - CLI should print concise failures.
        print(f"AMPG status=error message={exc}", file=sys.stderr)
        return 1
    return 1


def _cmd_plan(config) -> int:
    for line in plan_gateway(config):
        print(
            "AMPG_PLAN "
            f"site={line.site_id} "
            f"protocol={line.protocol} "
            f"renderer={line.renderer} "
            f"output={line.output_root} "
            f"daemon={line.daemon} "
            f"policy={line.daemon_policy} "
            f"action=\"{line.action}\""
        )
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
    return 0


def _cmd_docs(args) -> int:
    if args.docs_command == "generate":
        changed = generate_docs(Path.cwd(), check=args.check)
        changed_text = ",".join(str(path) for path in changed) if changed else "-"
        mode = "check" if args.check else "write"
        print(f"AMPG_DOCS status=ok mode={mode} changed={changed_text}")
        return 0
    return 1
