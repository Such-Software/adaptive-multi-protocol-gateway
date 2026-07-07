from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from .config import GatewayConfig
from .install_plan import (
    InstallStateCopy,
    InstallSupervisorAction,
    install_state_copies,
    install_supervisor_actions,
)
from .platforms import PlatformProvider, detect_platform
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


@dataclass(frozen=True)
class SupervisorApplyResult:
    site_id: str
    protocol: str
    platform: str
    kind: str
    service: str
    source: Path
    target: Path
    status: str
    mode: str
    command: str
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


def apply_supervisor(
    config: GatewayConfig,
    *,
    dry_run: bool,
    platform_provider: PlatformProvider | None = None,
    daemon_probe: DaemonProbeFunc | None = None,
) -> list[SupervisorApplyResult]:
    provider = platform_provider or detect_platform()
    actions = install_supervisor_actions(
        config,
        platform_provider=provider,
        daemon_probe=daemon_probe,
    )
    state_copies = install_state_copies(
        config,
        platform_provider=provider,
        daemon_probe=daemon_probe,
    )
    state_targets = {
        (copy.site_id, copy.protocol, copy.platform, copy.kind): copy.target
        for copy in state_copies
    }
    results: list[SupervisorApplyResult] = []
    for action in actions:
        target = supervisor_target(provider, action)
        validation = _validate_supervisor_action(
            action,
            target=target,
            state_targets=state_targets,
            dry_run=dry_run,
        )
        if validation.status == "blocked":
            results.append(validation)
            continue
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(action.source, target)
            _chmod_supervisor_target(provider, target)
        results.append(
            SupervisorApplyResult(
                site_id=action.site_id,
                protocol=action.protocol,
                platform=action.platform,
                kind=action.kind,
                service=action.service,
                source=action.source,
                target=target,
                status="planned" if dry_run else "written",
                mode="dry-run" if dry_run else "live",
                command=action.command,
                message=(
                    "would install approved supervisor file"
                    if dry_run
                    else "installed approved supervisor file"
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


def _validate_supervisor_action(
    action: InstallSupervisorAction,
    *,
    target: Path,
    state_targets: dict[tuple[str, str, str, str], Path],
    dry_run: bool,
) -> SupervisorApplyResult:
    mode = "dry-run" if dry_run else "live"
    if action.status != "planned":
        return _supervisor_result(
            action,
            target=target,
            status="blocked",
            mode=mode,
            message=action.message,
        )
    if not _valid_service_name(action.service):
        return _supervisor_result(
            action,
            target=target,
            status="blocked",
            mode=mode,
            message=f"invalid AMPG supervisor service name: {action.service}",
        )
    required_state_kind = _required_state_kind(action.kind)
    if required_state_kind is not None:
        state_target = state_targets.get(
            (action.site_id, action.protocol, action.platform, required_state_kind)
        )
        if state_target is None:
            return _supervisor_result(
                action,
                target=target,
                status="blocked",
                mode=mode,
                message="no managed state config is planned for this supervisor",
            )
        if not state_target.exists():
            return _supervisor_result(
                action,
                target=target,
                status="blocked",
                mode=mode,
                message="managed state config is missing; run deploy apply --stage state first",
            )
    if not action.source.exists():
        return _supervisor_result(
            action,
            target=target,
            status="blocked",
            mode=mode,
            message="approved supervisor artifact is missing",
        )
    if action.source.is_dir():
        return _supervisor_result(
            action,
            target=target,
            status="blocked",
            mode=mode,
            message="approved supervisor artifact is a directory",
        )
    return _supervisor_result(
        action,
        target=target,
        status="ready",
        mode=mode,
        message="supervisor file passed safety checks",
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


def _supervisor_result(
    action: InstallSupervisorAction,
    *,
    target: Path,
    status: str,
    mode: str,
    message: str,
) -> SupervisorApplyResult:
    return SupervisorApplyResult(
        site_id=action.site_id,
        protocol=action.protocol,
        platform=action.platform,
        kind=action.kind,
        service=action.service,
        source=action.source,
        target=target,
        status=status,
        mode=mode,
        command=action.command,
        message=message,
    )


def supervisor_target(provider: PlatformProvider, action: InstallSupervisorAction) -> Path:
    if provider.name == "linux-systemd":
        return Path("/etc/systemd/system") / f"{action.service}.service"
    if provider.name == "macos-launchd":
        return Path("~/Library/LaunchAgents").expanduser() / f"org.ampg.{action.service}.plist"
    if provider.name == "android-termux":
        prefix = _termux_prefix(provider.state_root)
        return prefix / "var/service" / action.service / "run"
    return provider.state_root / "services" / action.service / action.source.name


def _termux_prefix(state_root: Path) -> Path:
    if len(state_root.parts) >= 3 and state_root.parts[-3:] == ("var", "lib", "ampg"):
        return state_root.parents[2]
    return state_root


def _required_state_kind(supervisor_kind: str) -> str | None:
    if supervisor_kind == "daemon-supervisor":
        return "daemon-config"
    if supervisor_kind == "loopback-supervisor":
        return "loopback-config"
    return None


def _valid_service_name(service: str) -> bool:
    if not service.startswith("ampg-"):
        return False
    return all(char.isalnum() or char in {"-", "_", "."} for char in service)


def _chmod_supervisor_target(provider: PlatformProvider, target: Path) -> None:
    if provider.name not in {"android-termux", "linux-user"}:
        return
    target.chmod(target.stat().st_mode | 0o111)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
