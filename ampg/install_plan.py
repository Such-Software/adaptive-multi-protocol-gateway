from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import GatewayConfig, ProtocolConfig, SiteConfig
from .platforms import PlatformProvider, detect_platform
from .status import DaemonProbeFunc, TransportStatus, gateway_status
from .transports import fallback_transport_adapter, transport_adapter


@dataclass(frozen=True)
class InstallStep:
    site_id: str
    protocol: str
    platform: str
    stage: str
    action: str
    target: str
    status: str
    command: str
    message: str


def install_plan(
    config: GatewayConfig,
    *,
    platform_provider: PlatformProvider | None = None,
    daemon_probe: DaemonProbeFunc | None = None,
) -> list[InstallStep]:
    provider = platform_provider or detect_platform()
    statuses = gateway_status(
        config,
        platform_provider=provider,
        daemon_probe=daemon_probe,
    )
    status_by_protocol = {
        (status.site_id, status.protocol): status for status in statuses
    }
    steps: list[InstallStep] = []
    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            status = status_by_protocol[(site.id, protocol.name)]
            steps.extend(_protocol_install_steps(site, protocol, provider, status))
    return steps


def blocked_install_steps(steps: list[InstallStep]) -> list[InstallStep]:
    return [step for step in steps if step.status == "blocked"]


def _protocol_install_steps(
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
    status: TransportStatus,
) -> list[InstallStep]:
    if status.action == "adopt-existing":
        return [
            _step(
                site,
                protocol,
                provider,
                stage="daemon",
                action="adopt-existing",
                target=protocol.daemon,
                status="skipped",
                command="-",
                message="existing daemon is running; no AMPG-owned install is planned",
            )
        ]
    if status.action == "render-only":
        return [
            _step(
                site,
                protocol,
                provider,
                stage="daemon",
                action="render-only",
                target=protocol.daemon,
                status="skipped",
                command="-",
                message="external policy renders outputs and review artifacts only",
            )
        ]

    if status.action != "manage-owned" or status.status == "error":
        return [
            _step(
                site,
                protocol,
                provider,
                stage="daemon",
                action=status.action,
                target=protocol.daemon,
                status="blocked",
                command="-",
                message=status.message,
            )
        ]

    adapter = transport_adapter(protocol.name, protocol.daemon)
    adapter = adapter or fallback_transport_adapter(protocol.name, protocol.daemon)
    package_steps = [
        _package_step(site, protocol, provider, protocol.daemon, installed=status.installed)
    ]
    package_steps.extend(
        _package_step(site, protocol, provider, support_daemon, installed=False)
        for support_daemon in _support_daemons(protocol)
    )
    return [
        *package_steps,
        _step(
            site,
            protocol,
            provider,
            stage="state",
            action="create-state",
            target=str(_state_dir(provider, site, protocol)),
            status="planned",
            command=_mkdir_command(provider, _state_dir(provider, site, protocol)),
            message="create AMPG-owned state directory for daemon config, keys, and logs",
        ),
        _step(
            site,
            protocol,
            provider,
            stage="config",
            action="write-managed-config",
            target=str(_state_dir(provider, site, protocol) / "config"),
            status="planned",
            command="-",
            message=f"write managed {adapter.backend} config after plan review",
        ),
        _step(
            site,
            protocol,
            provider,
            stage="supervisor",
            action="configure-supervisor",
            target=_service_name(site, protocol),
            status="planned",
            command=_supervisor_command(provider, site, protocol),
            message=f"register AMPG-owned service with {provider.process_supervisor}",
        ),
        _step(
            site,
            protocol,
            provider,
            stage="health",
            action="check-transport",
            target=protocol.name,
            status="planned",
            command="-",
            message="verify generated site through the managed transport after start",
        ),
    ]


def _package_step(
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
    daemon: str,
    *,
    installed: bool,
) -> InstallStep:
    package = _package_name(provider, daemon)
    return _step(
        site,
        protocol,
        provider,
        stage="package",
        action="ensure-package",
        target=package,
        status="ready" if installed else "planned",
        command="-" if installed else _package_command(provider, package),
        message=(
            f"{daemon} executable is already present"
            if installed
            else f"install package providing {daemon}"
        ),
    )


def _support_daemons(protocol: ProtocolConfig) -> tuple[str, ...]:
    if protocol.name in {"tor", "i2p"}:
        return ("nginx",)
    return ()


def _package_name(provider: PlatformProvider, daemon: str) -> str:
    if provider.name == "macos-launchd" and daemon == "ipfs":
        return "kubo"
    return daemon


def _package_command(provider: PlatformProvider, package: str) -> str:
    if provider.name == "android-termux":
        return f"pkg install {package}"
    if provider.name == "linux-systemd":
        return f"sudo apt install {package}"
    if provider.name == "macos-launchd":
        return f"brew install {package}"
    if provider.name == "linux-user":
        return f"install {package} with the user package manager"
    return "-"


def _mkdir_command(provider: PlatformProvider, path: Path) -> str:
    prefix = "sudo " if provider.can_write_system_config else ""
    return f"{prefix}mkdir -p {path}"


def _supervisor_command(
    provider: PlatformProvider,
    site: SiteConfig,
    protocol: ProtocolConfig,
) -> str:
    service = _service_name(site, protocol)
    if provider.name == "android-termux":
        return f"sv-enable {service}"
    if provider.name == "linux-systemd":
        return f"sudo systemctl enable --now {service}.service"
    if provider.name == "macos-launchd":
        return f"launchctl bootstrap gui/$UID ~/Library/LaunchAgents/org.ampg.{service}.plist"
    if provider.name == "linux-user":
        return f"run {service} under the user supervisor"
    return "-"


def _state_dir(
    provider: PlatformProvider,
    site: SiteConfig,
    protocol: ProtocolConfig,
) -> Path:
    return provider.state_root / site.id / protocol.name


def _service_name(site: SiteConfig, protocol: ProtocolConfig) -> str:
    return f"ampg-{site.id}-{protocol.name}"


def _step(
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
    *,
    stage: str,
    action: str,
    target: str,
    status: str,
    command: str,
    message: str,
) -> InstallStep:
    return InstallStep(
        site_id=site.id,
        protocol=protocol.name,
        platform=provider.name,
        stage=stage,
        action=action,
        target=target,
        status=status,
        command=command,
        message=message,
    )
