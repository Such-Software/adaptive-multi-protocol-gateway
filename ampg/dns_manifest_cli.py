"""CLI for generic preserve-unmanaged DNS manifest reconciliation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .dns_manifest import (
    DNSManifestError,
    load_dns_manifest,
    offline_plan,
    provider_from_credentials,
    reconcile_dns_manifest,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ampg-dns-manifest")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="validate and render the manifest without provider access",
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        help="Provider key-value credential file; required for provider access",
    )
    parser.add_argument("--client-ip")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="absolute backup root; required for live apply",
    )
    parser.add_argument(
        "--apply-zone",
        help="exact zone sentinel required for writes; omit for read-only plan",
    )
    return parser


def main(arguments: list[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    try:
        manifest = load_dns_manifest(options.manifest)
        if options.offline:
            if options.apply_zone or options.credentials:
                raise ValueError(
                    "--offline cannot be combined with credentials or apply"
                )
            result = offline_plan(manifest)
        else:
            if options.credentials is None:
                raise ValueError("--credentials is required")
            apply = options.apply_zone is not None
            if apply and options.apply_zone != manifest.zone:
                raise ValueError("--apply-zone must exactly match manifest zone")
            if apply and options.backup_dir is None:
                raise ValueError("--backup-dir is required for live apply")
            provider = provider_from_credentials(
                manifest.provider, options.credentials, options.client_ip
            )
            result = reconcile_dns_manifest(
                manifest,
                provider,
                apply=apply,
                backup_dir=options.backup_dir,
            )
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    except (DNSManifestError, OSError, RuntimeError, ValueError) as error:
        print(f"ampg-dns-manifest: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
