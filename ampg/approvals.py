from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Iterable

from .config import GatewayConfig
from .state_contract import gateway_state_root


SCHEMA = "ampg.artifact-approvals.v1"
GENERIC_PLATFORM = "generic"
ACTIVATION_ARTIFACT_KIND = "activation-artifact"
ApprovalKey = tuple[str, str, str, str, str]
ApprovalRegistry = dict[ApprovalKey, "ArtifactApproval"]


@dataclass(frozen=True)
class ApprovalInput:
    site_id: str
    protocol: str
    platform: str
    kind: str
    path: Path
    content: str


@dataclass(frozen=True)
class ArtifactApproval:
    site_id: str
    protocol: str
    platform: str
    kind: str
    path: Path
    digest: str
    approved_at: str
    source: str


@dataclass(frozen=True)
class ApprovalCheck:
    candidate: ApprovalInput
    status: str
    digest: str
    message: str


@dataclass(frozen=True)
class ApprovalWriteResult:
    candidate: ApprovalInput
    status: str
    digest: str
    message: str


def approval_registry_path(config: GatewayConfig) -> Path:
    return gateway_state_root(config) / "approvals.json"


def artifact_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_approval_registry(config: GatewayConfig) -> ApprovalRegistry:
    path = approval_registry_path(config)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid approval registry {path}: {exc}") from exc
    if data.get("schema") != SCHEMA:
        raise ValueError(f"invalid approval registry schema in {path}")
    approvals: ApprovalRegistry = {}
    for raw_approval in data.get("approvals", []):
        if not isinstance(raw_approval, dict):
            continue
        approval = ArtifactApproval(
            site_id=str(raw_approval.get("site", "")),
            protocol=str(raw_approval.get("protocol", "")),
            platform=str(raw_approval.get("platform", "")),
            kind=str(raw_approval.get("kind", "")),
            path=_normalized_path(Path(str(raw_approval.get("path", "")))),
            digest=str(raw_approval.get("sha256", "")),
            approved_at=str(raw_approval.get("approved_at", "")),
            source=str(raw_approval.get("source", "manual")),
        )
        if all(
            (
                approval.site_id,
                approval.protocol,
                approval.platform,
                approval.kind,
                approval.digest,
            )
        ):
            approvals[_approval_key_for_values(
                approval.site_id,
                approval.protocol,
                approval.platform,
                approval.kind,
                approval.path,
            )] = approval
    return approvals


def write_approval_registry(
    config: GatewayConfig,
    approvals: ApprovalRegistry,
) -> Path:
    path = approval_registry_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema": SCHEMA,
        "approvals": [
            {
                "site": approval.site_id,
                "protocol": approval.protocol,
                "platform": approval.platform,
                "kind": approval.kind,
                "path": str(approval.path),
                "sha256": approval.digest,
                "approved_at": approval.approved_at,
                "source": approval.source,
            }
            for approval in sorted(
                approvals.values(),
                key=lambda item: (
                    item.site_id,
                    item.protocol,
                    item.platform,
                    item.kind,
                    str(item.path),
                ),
            )
        ],
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def approval_check(
    candidate: ApprovalInput,
    approvals: ApprovalRegistry,
) -> ApprovalCheck:
    expected_digest = artifact_digest(candidate.content)
    if not candidate.path.exists():
        return ApprovalCheck(
            candidate=candidate,
            status="missing",
            digest=expected_digest,
            message="artifact is missing; rerun with --write-artifacts first",
        )
    actual_digest = _path_digest(candidate.path)
    if actual_digest != expected_digest:
        return ApprovalCheck(
            candidate=candidate,
            status="stale",
            digest=expected_digest,
            message="artifact differs from current generator output; rerun with --write-artifacts",
        )
    approval = approvals.get(approval_key(candidate))
    if approval is None:
        return ApprovalCheck(
            candidate=candidate,
            status="review",
            digest=expected_digest,
            message="artifact content is not approved; run approvals approve after review",
        )
    if approval.digest != expected_digest:
        return ApprovalCheck(
            candidate=candidate,
            status="review",
            digest=expected_digest,
            message="approval digest does not match current artifact content",
        )
    return ApprovalCheck(
        candidate=candidate,
        status="approved",
        digest=expected_digest,
        message="artifact content digest is approved",
    )


def approve_artifacts(
    config: GatewayConfig,
    candidates: Iterable[ApprovalInput],
    *,
    source: str = "manual",
) -> list[ApprovalWriteResult]:
    approvals = load_approval_registry(config)
    results: list[ApprovalWriteResult] = []
    changed = False
    for candidate in candidates:
        check = approval_check(candidate, approvals)
        if check.status in {"missing", "stale"}:
            results.append(
                ApprovalWriteResult(
                    candidate=candidate,
                    status=check.status,
                    digest=check.digest,
                    message=check.message,
                )
            )
            continue
        status = "current" if check.status == "approved" else "written"
        if status == "written":
            changed = True
            approvals[approval_key(candidate)] = ArtifactApproval(
                site_id=candidate.site_id,
                protocol=candidate.protocol,
                platform=candidate.platform,
                kind=candidate.kind,
                path=_normalized_path(candidate.path),
                digest=check.digest,
                approved_at=_utc_now(),
                source=source,
            )
        results.append(
            ApprovalWriteResult(
                candidate=candidate,
                status=status,
                digest=check.digest,
                message="approval recorded" if status == "written" else check.message,
            )
        )
    if changed:
        write_approval_registry(config, approvals)
    return results


def approval_key(candidate: ApprovalInput) -> ApprovalKey:
    return _approval_key_for_values(
        candidate.site_id,
        candidate.protocol,
        candidate.platform,
        candidate.kind,
        candidate.path,
    )


def _approval_key_for_values(
    site_id: str,
    protocol: str,
    platform: str,
    kind: str,
    path: Path,
) -> ApprovalKey:
    return (site_id, protocol, platform, kind, str(_normalized_path(path)))


def _path_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_path(path: Path) -> Path:
    return path.expanduser().resolve()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
