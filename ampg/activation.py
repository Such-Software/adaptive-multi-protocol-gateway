from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex

from .addresses import AddressRecord, address_registry_path, effective_address_records
from .config import GatewayConfig, ProtocolConfig, SiteConfig
from .install_plan import write_install_artifacts
from .plan import plan_artifacts, write_plan_artifacts
from .platforms import PlatformProvider
from .status import (
    DaemonProbeFunc,
    TransportStatus,
    doctor_gateway,
    gateway_status,
)


@dataclass(frozen=True)
class ActivationStep:
    site_id: str
    protocol: str
    stage: str
    action: str
    target: str
    status: str
    message: str
    command: str = "-"


def activation_steps(
    config: GatewayConfig,
    *,
    platform_provider: PlatformProvider | None = None,
    daemon_probe: DaemonProbeFunc | None = None,
) -> list[ActivationStep]:
    statuses = gateway_status(
        config,
        platform_provider=platform_provider,
        daemon_probe=daemon_probe,
    )
    status_by_protocol = {
        (status.site_id, status.protocol): status for status in statuses
    }
    address_by_protocol = {
        (record.site_id, record.protocol): record
        for record in effective_address_records(config)
    }
    steps: list[ActivationStep] = []

    for issue in doctor_gateway(
        config,
        platform_provider=platform_provider,
        daemon_probe=daemon_probe,
        statuses=statuses,
    ):
        if issue.code in {"daemon-status", "output-missing"}:
            continue
        steps.append(
            ActivationStep(
                site_id=issue.site_id,
                protocol=issue.protocol,
                stage="preflight",
                action="fix-issue",
                target="-",
                status=_issue_activation_status(issue.severity),
                message=f"{issue.code}: {issue.message}",
            )
        )

    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            output_ready = _output_ready(site, protocol)
            transport_status = status_by_protocol[(site.id, protocol.name)]
            steps.extend(
                _protocol_steps(
                    config,
                    site,
                    protocol,
                    transport_status=transport_status,
                    address_record=address_by_protocol[(site.id, protocol.name)],
                    output_ready=output_ready,
                )
            )

    return steps


def blocked_steps(steps: list[ActivationStep]) -> list[ActivationStep]:
    return [step for step in steps if step.status == "blocked"]


def _protocol_steps(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
    *,
    transport_status: TransportStatus,
    address_record: AddressRecord,
    output_ready: bool,
) -> list[ActivationStep]:
    output_root = site.outputs.root / protocol.name
    steps = [
        ActivationStep(
            site_id=site.id,
            protocol=protocol.name,
            stage="output",
            action="verify-output",
            target=str(output_root),
            status="ready" if output_ready else "blocked",
            message=(
                "generated output marker exists"
                if output_ready
                else "generated output is missing; run build before apply"
            ),
        )
    ]

    artifacts = plan_artifacts(site, protocol)
    if artifacts:
        for artifact in artifacts:
            steps.append(
                ActivationStep(
                    site_id=site.id,
                    protocol=protocol.name,
                    stage="artifact",
                    action="review-config",
                    target=str(artifact.path),
                    status="review",
                    message="review generated config before installing or reloading services",
                )
            )
    else:
        steps.append(
            ActivationStep(
                site_id=site.id,
                protocol=protocol.name,
                stage="artifact",
                action="review-config",
                target="-",
                status="planned",
                message="no generated config artifact is available for this adapter yet",
            )
        )

    steps.append(
        ActivationStep(
            site_id=site.id,
            protocol=protocol.name,
            stage="daemon",
            action=transport_status.action,
            target=protocol.daemon,
            status=_transport_activation_status(transport_status),
            message=transport_status.message,
        )
    )
    steps.append(_address_step(config, site, protocol, address_record))
    steps.append(
        ActivationStep(
            site_id=site.id,
            protocol=protocol.name,
            stage="health",
            action="check-transport",
            target=protocol.name,
            status=_health_activation_status(
                output_ready=output_ready,
                transport_status=transport_status,
                address_record=address_record,
            ),
            message=_health_activation_message(
                output_ready=output_ready,
                transport_status=transport_status,
                address_record=address_record,
            ),
        )
    )
    return steps


def _address_step(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
    address_record: AddressRecord,
) -> ActivationStep:
    if address_record.address_status == "placeholder":
        return ActivationStep(
            site_id=site.id,
            protocol=protocol.name,
            stage="address",
            action="capture-address",
            target=str(address_registry_path(config)),
            status="review",
            message="generated transport address is not known yet",
            command=_address_capture_command(config, protocol),
        )
    return ActivationStep(
        site_id=site.id,
        protocol=protocol.name,
        stage="address",
        action="use-address",
        target=address_record.url,
        status="ready",
        message=f"using {address_record.address_status} transport address",
        command="-",
    )


def _address_capture_command(config: GatewayConfig, protocol: ProtocolConfig) -> str:
    config_path = shlex.quote(str(config.config_path))
    return f"python3 -m ampg --config {config_path} addresses capture --protocol {protocol.name}"


def _health_activation_status(
    *,
    output_ready: bool,
    transport_status: TransportStatus,
    address_record: AddressRecord,
) -> str:
    if not output_ready or transport_status.status == "error":
        return "blocked"
    if address_record.address_status == "placeholder":
        return "review"
    return "planned"


def _health_activation_message(
    *,
    output_ready: bool,
    transport_status: TransportStatus,
    address_record: AddressRecord,
) -> str:
    if not output_ready or transport_status.status == "error":
        return "health check is blocked until output and daemon steps are ready"
    if address_record.address_status == "placeholder":
        return "capture or configure the generated transport address before published checks"
    return "verify generated site through this transport after apply"


def _output_ready(site: SiteConfig, protocol: ProtocolConfig) -> bool:
    return ((site.outputs.root / protocol.name) / ".ampg-output").exists()


def _issue_activation_status(severity: str) -> str:
    if severity == "error":
        return "blocked"
    return "review"


def _transport_activation_status(status: TransportStatus) -> str:
    if status.status == "error":
        return "blocked"
    if status.action == "render-only" or status.status == "warn":
        return "review"
    return "ready"


def write_activation_artifacts(
    config: GatewayConfig,
    *,
    platform_provider: PlatformProvider | None = None,
    daemon_probe: DaemonProbeFunc | None = None,
) -> tuple[Path, ...]:
    paths = [artifact.path for artifact in write_plan_artifacts(config)]
    paths.extend(
        artifact.path
        for artifact in write_install_artifacts(
            config,
            platform_provider=platform_provider,
            daemon_probe=daemon_probe,
        )
    )
    return tuple(paths)
