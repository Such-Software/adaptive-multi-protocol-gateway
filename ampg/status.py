from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import shutil
import subprocess

from .config import GatewayConfig, ProtocolConfig, SiteConfig
from .platforms import PlatformProvider, detect_platform
from .route_policy import route_issues
from .transports import (
    TransportAdapter,
    fallback_transport_adapter,
    transport_adapter,
)


VALID_DAEMON_POLICIES = {"external", "adopt", "manage", "auto"}
SUPPORTED_RENDERERS = {"clearnet", "privacy-html", "gemtext", "micron"}
PROCESS_NAME_ALIASES = {
    "i2pd": ("i2pd", "i2pd-daemon"),
}


@dataclass(frozen=True)
class DaemonProbe:
    installed: bool
    running: bool
    executable_path: str | None = None


@dataclass(frozen=True)
class TransportStatus:
    site_id: str
    protocol: str
    renderer: str
    daemon: str
    daemon_policy: str
    platform: str
    supervisor: str
    adapter: str
    backend: str
    installed: bool
    running: bool
    adoptable: bool
    manageable: bool
    executable_path: str | None
    status: str
    action: str
    message: str


@dataclass(frozen=True)
class DoctorIssue:
    site_id: str
    severity: str
    code: str
    message: str
    protocol: str = "-"


DaemonProbeFunc = Callable[[TransportAdapter], DaemonProbe]


def gateway_status(
    config: GatewayConfig,
    *,
    platform_provider: PlatformProvider | None = None,
    daemon_probe: DaemonProbeFunc | None = None,
) -> list[TransportStatus]:
    provider = platform_provider or detect_platform()
    probe = daemon_probe or probe_daemon
    statuses: list[TransportStatus] = []
    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            adapter = transport_adapter(protocol.name, protocol.daemon)
            adapter = adapter or fallback_transport_adapter(protocol.name, protocol.daemon)
            daemon = probe(adapter)
            statuses.append(_transport_status(site, protocol, adapter, provider, daemon))
    return statuses


def doctor_gateway(
    config: GatewayConfig,
    *,
    platform_provider: PlatformProvider | None = None,
    daemon_probe: DaemonProbeFunc | None = None,
    statuses: list[TransportStatus] | None = None,
) -> list[DoctorIssue]:
    if statuses is None:
        statuses = gateway_status(
            config,
            platform_provider=platform_provider,
            daemon_probe=daemon_probe,
        )
    issues: list[DoctorIssue] = []

    for site in config.sites:
        if not site.source.path.exists():
            issues.append(
                DoctorIssue(
                    site_id=site.id,
                    severity="error",
                    code="source-missing",
                    message=f"source path does not exist: {site.source.path}",
                )
            )
        elif not site.source.path.is_dir():
            issues.append(
                DoctorIssue(
                    site_id=site.id,
                    severity="error",
                    code="source-not-directory",
                    message=f"source path is not a directory: {site.source.path}",
                )
            )

        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            if protocol.renderer not in SUPPORTED_RENDERERS:
                issues.append(
                    DoctorIssue(
                        site_id=site.id,
                        protocol=protocol.name,
                        severity="error",
                        code="unsupported-renderer",
                        message=f"renderer {protocol.renderer!r} is not implemented",
                    )
                )
            output_root = site.outputs.root / protocol.name
            if not (output_root / ".ampg-output").exists():
                issues.append(
                    DoctorIssue(
                        site_id=site.id,
                        protocol=protocol.name,
                        severity="warning",
                        code="output-missing",
                        message=f"build output is missing: {output_root}",
                    )
                )

    for status in statuses:
        if status.status == "error":
            issues.append(
                DoctorIssue(
                    site_id=status.site_id,
                    protocol=status.protocol,
                    severity="error",
                    code="daemon-status",
                    message=status.message,
                )
            )
        elif status.status == "warn":
            issues.append(
                DoctorIssue(
                    site_id=status.site_id,
                    protocol=status.protocol,
                    severity="warning",
                    code="daemon-status",
                    message=status.message,
                )
            )

    for issue in route_issues(config):
        issues.append(
            DoctorIssue(
                site_id=issue.site_id,
                protocol="-",
                severity="error",
                code=issue.code,
                message=issue.message,
            )
        )

    return issues


def probe_daemon(adapter: TransportAdapter) -> DaemonProbe:
    executable_path = shutil.which(adapter.executable)
    running = _process_running(adapter.executable)
    return DaemonProbe(
        installed=bool(executable_path),
        running=running,
        executable_path=executable_path,
    )


def _transport_status(
    site: SiteConfig,
    protocol: ProtocolConfig,
    adapter: TransportAdapter,
    provider: PlatformProvider,
    daemon: DaemonProbe,
) -> TransportStatus:
    adapter_known = adapter.backend != "unknown"
    adoptable = adapter.adopt_supported and daemon.running
    manageable = adapter.managed_supported and provider.can_manage_daemons
    policy = protocol.daemon_policy

    if policy not in VALID_DAEMON_POLICIES:
        status = "error"
        action = "unavailable"
        message = f"unknown daemon policy {policy!r}"
    elif policy == "external":
        status = "ok" if adapter_known else "warn"
        action = "render-only"
        message = (
            "render outputs and review generated snippets"
            if adapter_known
            else "no registered daemon adapter; render output only"
        )
    elif not adapter_known:
        status = "error"
        action = "unavailable"
        message = f"no registered adapter for {protocol.name}/{protocol.daemon}"
    elif policy == "adopt":
        if adoptable:
            status = "ok"
            action = "adopt-existing"
            message = "existing daemon appears to be running"
        elif daemon.installed:
            status = "error"
            action = "unavailable"
            message = f"{adapter.executable} is installed but not running"
        else:
            status = "error"
            action = "unavailable"
            message = f"{adapter.executable} is not installed or not on PATH"
    elif policy == "manage":
        if manageable:
            status = "ok"
            action = "manage-owned"
            message = f"AMPG can manage {protocol.name} with {provider.name}"
        else:
            status = "error"
            action = "unavailable"
            message = f"{provider.name} cannot manage {protocol.name}/{protocol.daemon}"
    else:
        if adoptable:
            status = "ok"
            action = "adopt-existing"
            message = "existing daemon appears to be running"
        elif manageable:
            status = "ok"
            action = "manage-owned"
            if daemon.installed:
                message = f"{adapter.executable} is installed but not running; AMPG would manage it"
            else:
                message = f"{adapter.executable} is missing; AMPG would prepare managed setup"
        else:
            status = "error"
            action = "unavailable"
            message = f"no running daemon and {provider.name} cannot manage {protocol.name}/{protocol.daemon}"

    return TransportStatus(
        site_id=site.id,
        protocol=protocol.name,
        renderer=protocol.renderer,
        daemon=protocol.daemon,
        daemon_policy=policy,
        platform=provider.name,
        supervisor=provider.process_supervisor,
        adapter=f"{adapter.protocol}/{adapter.daemon}",
        backend=adapter.backend,
        installed=daemon.installed,
        running=daemon.running,
        adoptable=adoptable,
        manageable=manageable,
        executable_path=daemon.executable_path,
        status=status,
        action=action,
        message=message,
    )


def _process_running(executable: str) -> bool:
    pgrep = shutil.which("pgrep")
    if not pgrep:
        return False
    names = PROCESS_NAME_ALIASES.get(executable, (executable,))
    return any(_pgrep_exact(pgrep, name) for name in names)


def _pgrep_exact(pgrep: str, name: str) -> bool:
    try:
        result = subprocess.run(
            [pgrep, "-x", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0
