from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import GatewayConfig


@dataclass(frozen=True)
class PlanLine:
    site_id: str
    protocol: str
    renderer: str
    output_root: Path
    daemon: str
    daemon_policy: str
    action: str


def plan_gateway(config: GatewayConfig) -> list[PlanLine]:
    lines: list[PlanLine] = []
    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            lines.append(
                PlanLine(
                    site_id=site.id,
                    protocol=protocol.name,
                    renderer=protocol.renderer,
                    output_root=site.outputs.root / protocol.name,
                    daemon=protocol.daemon,
                    daemon_policy=protocol.daemon_policy,
                    action=_action_for_policy(protocol.daemon_policy),
                )
            )
    return lines


def _action_for_policy(policy: str) -> str:
    if policy == "external":
        return "render outputs and config snippets only"
    if policy == "adopt":
        return "adopt existing daemon; fail if missing"
    if policy == "manage":
        return "create AMPG-owned daemon instance"
    if policy == "auto":
        return "adopt healthy daemon, otherwise manage AMPG-owned instance"
    return "unknown policy; no apply support"
