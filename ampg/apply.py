from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from .config import GatewayConfig
from .install_plan import InstallStateCopy, install_state_copies
from .platforms import PlatformProvider
from .state_contract import gateway_state_root
from .status import DaemonProbeFunc


@dataclass(frozen=True)
class StateApplyResult:
    site_id: str
    protocol: str
    platform: str
    kind: str
    source: Path
    target: Path
    status: str
    mode: str
    message: str


def apply_state(
    config: GatewayConfig,
    *,
    dry_run: bool,
    platform_provider: PlatformProvider | None = None,
    daemon_probe: DaemonProbeFunc | None = None,
) -> list[StateApplyResult]:
    copies = install_state_copies(
        config,
        platform_provider=platform_provider,
        daemon_probe=daemon_probe,
    )
    results: list[StateApplyResult] = []
    for copy in copies:
        validation = _validate_state_copy(config, copy, dry_run=dry_run)
        if validation.status == "blocked":
            results.append(validation)
            continue
        if not dry_run:
            copy.target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copy.source, copy.target)
        results.append(
            StateApplyResult(
                site_id=copy.site_id,
                protocol=copy.protocol,
                platform=copy.platform,
                kind=copy.kind,
                source=copy.source,
                target=copy.target,
                status="planned" if dry_run else "written",
                mode="dry-run" if dry_run else "live",
                message=(
                    "would copy approved artifact into AMPG-owned state"
                    if dry_run
                    else "copied approved artifact into AMPG-owned state"
                ),
            )
        )
    return results


def _validate_state_copy(
    config: GatewayConfig,
    copy: InstallStateCopy,
    *,
    dry_run: bool,
) -> StateApplyResult:
    if copy.status != "planned":
        return _result(
            copy,
            status="blocked",
            mode="dry-run" if dry_run else "live",
            message=copy.message,
        )
    state_root = gateway_state_root(config).resolve()
    target = copy.target.resolve()
    if not _is_relative_to(target, state_root):
        return _result(
            copy,
            status="blocked",
            mode="dry-run" if dry_run else "live",
            message=f"target is outside AMPG state root: {target}",
        )
    if not copy.source.exists():
        return _result(
            copy,
            status="blocked",
            mode="dry-run" if dry_run else "live",
            message="approved source artifact is missing",
        )
    if copy.source.is_dir():
        return _result(
            copy,
            status="blocked",
            mode="dry-run" if dry_run else "live",
            message="approved source artifact is a directory",
        )
    return _result(
        copy,
        status="ready",
        mode="dry-run" if dry_run else "live",
        message="state copy passed safety checks",
    )


def _result(
    copy: InstallStateCopy,
    *,
    status: str,
    mode: str,
    message: str,
) -> StateApplyResult:
    return StateApplyResult(
        site_id=copy.site_id,
        protocol=copy.protocol,
        platform=copy.platform,
        kind=copy.kind,
        source=copy.source,
        target=copy.target,
        status=status,
        mode=mode,
        message=message,
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
