"""Generic, preserve-unmanaged DNS manifest reconciliation.

The existing AMPG DNS provider already performs safe Namecheap getHosts and
setHosts calls. This module adds a provider-neutral manifest projection for
application onboarding without coupling it to a gateway.toml transport plan.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable

from .dns import (
    DEFAULT_TTL,
    NAMECHEAP_SUPPORTED_RECORD_TYPES,
    NamecheapDNSProvider,
    ProviderDNSRecord,
)
from .dynadot_dns import (
    DYNADOT_SUPPORTED_RECORD_TYPES,
    DynadotDNSProvider,
)


_PROVIDER_RECORD_TYPES = {
    "namecheap": NAMECHEAP_SUPPORTED_RECORD_TYPES,
    "dynadot": DYNADOT_SUPPORTED_RECORD_TYPES,
}


_HOSTNAME = re.compile(
    r"(?=^.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_RELATIVE_NAME = re.compile(
    r"@|(?:[a-z0-9_*](?:[a-z0-9_*-]{0,61}[a-z0-9_*])?\.)*"
    r"[a-z0-9_*](?:[a-z0-9_*-]{0,61}[a-z0-9_*])?"
)


@dataclass(frozen=True)
class ManagedDNSRecord:
    record: ProviderDNSRecord
    replace: str
    match_value_prefix: str | None
    conflict_types: tuple[str, ...]


@dataclass(frozen=True)
class DNSManifest:
    contract_version: int
    app_id: str
    zone: str
    provider: str
    preserve_unmanaged: bool
    protected_names: tuple[str, ...]
    records: tuple[ManagedDNSRecord, ...]


class DNSManifestError(RuntimeError):
    """Safe-to-display manifest or reconciliation failure."""


def _required_string(document: dict[str, Any], name: str) -> str:
    value = document.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _record_name(value: str) -> str:
    normalized = value.strip().rstrip(".").lower() or "@"
    if len(normalized) > 253 or not _RELATIVE_NAME.fullmatch(normalized):
        raise ValueError(f"invalid relative DNS name: {value}")
    return normalized


def _record_identity(record: ProviderDNSRecord) -> tuple[Any, ...]:
    return (
        _record_name(record.name),
        record.type.upper(),
        record.value.strip(),
        int(record.ttl),
        record.mx_pref,
        record.provider_value2,
    )


def _record_sort_key(record: ProviderDNSRecord) -> tuple[str, str, str, int]:
    return (
        _record_name(record.name),
        record.type.upper(),
        record.value.strip(),
        int(record.mx_pref or 0),
    )


def _load_record(raw: Any, provider: str) -> ManagedDNSRecord:
    if not isinstance(raw, dict):
        raise ValueError("managed DNS records must be objects")
    name = _record_name(_required_string(raw, "name"))
    record_type = _required_string(raw, "type").upper()
    supported_types = _PROVIDER_RECORD_TYPES[provider]
    if record_type not in supported_types:
        raise ValueError(f"unsupported {provider} record type: {record_type}")
    value = _required_string(raw, "value")
    if (
        "\n" in value
        or "\r" in value
        or "{{" in value
        or "${" in value
        or (value.startswith("<") and value.endswith(">"))
    ):
        raise ValueError(f"record {name}/{record_type} has an unresolved value")
    ttl = raw.get("ttl", DEFAULT_TTL)
    if not isinstance(ttl, int) or ttl < 60 or ttl > 86400:
        raise ValueError(f"record {name}/{record_type} has an invalid TTL")
    mx_pref = raw.get("mx_pref")
    if record_type == "MX":
        if not isinstance(mx_pref, int) or not 0 <= mx_pref <= 65535:
            raise ValueError(f"record {name}/MX requires mx_pref")
    elif mx_pref is not None:
        raise ValueError(f"record {name}/{record_type} cannot set mx_pref")
    provider_value2 = raw.get("provider_value2")
    if provider_value2 is not None:
        if provider != "dynadot" or record_type == "MX":
            raise ValueError(
                f"record {name}/{record_type} cannot set provider_value2"
            )
        if not isinstance(provider_value2, str) or not provider_value2:
            raise ValueError(
                f"record {name}/{record_type} has invalid provider_value2"
            )

    replace = raw.get("replace", "all")
    if replace not in {"all", "value_prefix"}:
        raise ValueError(f"record {name}/{record_type} has invalid replace mode")
    match_value_prefix = raw.get("match_value_prefix")
    if replace == "value_prefix":
        if not isinstance(match_value_prefix, str) or not match_value_prefix:
            raise ValueError(
                f"record {name}/{record_type} requires match_value_prefix"
            )
    elif match_value_prefix is not None:
        raise ValueError(
            f"record {name}/{record_type} cannot set match_value_prefix"
        )

    raw_conflicts = raw.get("conflict_types", [])
    if (
        not isinstance(raw_conflicts, list)
        or not all(isinstance(item, str) for item in raw_conflicts)
    ):
        raise ValueError(f"record {name}/{record_type} has invalid conflicts")
    conflict_types = tuple(item.upper() for item in raw_conflicts)
    if any(item not in supported_types for item in conflict_types):
        raise ValueError(f"record {name}/{record_type} has unsupported conflicts")

    return ManagedDNSRecord(
        record=ProviderDNSRecord(
            name, record_type, value, ttl, mx_pref, provider_value2
        ),
        replace=replace,
        match_value_prefix=match_value_prefix,
        conflict_types=conflict_types,
    )


def load_dns_manifest(path: Path) -> DNSManifest:
    if path.is_symlink() or not path.is_file():
        raise ValueError("DNS manifest must be a regular, non-symlink file")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("DNS manifest is not valid JSON") from error
    if not isinstance(document, dict) or document.get("contract_version") != 1:
        raise ValueError("unsupported DNS manifest contract")
    app_id = _required_string(document, "app_id")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", app_id):
        raise ValueError("app_id is invalid")
    zone = _required_string(document, "zone").lower().rstrip(".")
    if not _HOSTNAME.fullmatch(zone):
        raise ValueError("zone must be a DNS hostname")
    provider = _required_string(document, "provider")
    if provider not in _PROVIDER_RECORD_TYPES:
        raise ValueError("contract version 1 has an unsupported DNS provider")
    if document.get("preserve_unmanaged") is not True:
        raise ValueError("preserve_unmanaged must be true")
    raw_protected = document.get("protected_names", [])
    if (
        not isinstance(raw_protected, list)
        or not all(isinstance(item, str) for item in raw_protected)
    ):
        raise ValueError("protected_names must be a list")
    protected_names = tuple(_record_name(item) for item in raw_protected)
    raw_records = document.get("records")
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("records must be a non-empty list")
    if len(raw_records) > 100:
        raise ValueError("DNS manifest has too many managed records")
    records = tuple(_load_record(raw, provider) for raw in raw_records)
    for managed in records:
        if _record_name(managed.record.name) in protected_names:
            raise ValueError(
                f"managed record targets protected name {managed.record.name}"
            )
    identities = [_record_identity(managed.record) for managed in records]
    if len(identities) != len(set(identities)):
        raise ValueError("DNS manifest contains a duplicate record")
    return DNSManifest(
        contract_version=1,
        app_id=app_id,
        zone=zone,
        provider=provider,
        preserve_unmanaged=True,
        protected_names=protected_names,
        records=records,
    )


def _is_replaced(
    existing: ProviderDNSRecord, managed: ManagedDNSRecord
) -> bool:
    existing_name = _record_name(existing.name)
    desired_name = _record_name(managed.record.name)
    existing_type = existing.type.upper()
    desired_type = managed.record.type.upper()
    if existing_name != desired_name:
        return False
    if existing_type in managed.conflict_types:
        return True
    if existing_type != desired_type:
        return False
    if managed.replace == "all":
        return True
    assert managed.match_value_prefix is not None
    return existing.value.lower().startswith(
        managed.match_value_prefix.lower()
    )


def merge_dns_manifest_records(
    existing: Iterable[ProviderDNSRecord],
    managed_records: Iterable[ManagedDNSRecord],
) -> tuple[ProviderDNSRecord, ...]:
    managed = tuple(managed_records)
    retained = [
        record
        for record in existing
        if not any(_is_replaced(record, desired) for desired in managed)
    ]
    desired = [entry.record for entry in managed]
    return tuple(sorted(retained + desired, key=_record_sort_key))


def _changes(
    before: Iterable[ProviderDNSRecord],
    after: Iterable[ProviderDNSRecord],
) -> list[dict[str, Any]]:
    before_set = {_record_identity(record) for record in before}
    after_set = {_record_identity(record) for record in after}
    changes: list[dict[str, Any]] = []
    for identity in sorted(before_set - after_set, key=repr):
        name, record_type, value, ttl, mx_pref, provider_value2 = identity
        changes.append(
            {
                "action": "remove",
                "name": name,
                "type": record_type,
                "value": value,
                "ttl": ttl,
                "mx_pref": mx_pref,
                "provider_value2": provider_value2,
            }
        )
    for identity in sorted(after_set - before_set, key=repr):
        name, record_type, value, ttl, mx_pref, provider_value2 = identity
        changes.append(
            {
                "action": "add",
                "name": name,
                "type": record_type,
                "value": value,
                "ttl": ttl,
                "mx_pref": mx_pref,
                "provider_value2": provider_value2,
            }
        )
    return changes


def offline_plan(manifest: DNSManifest) -> dict[str, Any]:
    return {
        "contract_version": 1,
        "app_id": manifest.app_id,
        "zone": manifest.zone,
        "provider": manifest.provider,
        "mode": "offline-plan",
        "preserve_unmanaged": True,
        "protected_names": list(manifest.protected_names),
        "managed_records": [
            {
                "name": entry.record.name,
                "type": entry.record.type,
                "value": entry.record.value,
                "ttl": entry.record.ttl,
                "mx_pref": entry.record.mx_pref,
                "provider_value2": entry.record.provider_value2,
                "replace": entry.replace,
            }
            for entry in manifest.records
        ],
    }


def _write_backup(
    provider: str,
    zone: str,
    raw: str,
    backup_dir: Path,
    extension: str,
) -> Path:
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S_%f")
    path = backup_dir / provider / f"{zone}.{stamp}.{extension}"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as backup:
        backup.write(raw)
    os.chmod(path, 0o600)
    return path


def reconcile_dns_manifest(
    manifest: DNSManifest,
    provider: Any,
    *,
    apply: bool = False,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    if getattr(provider, "name", None) != manifest.provider:
        raise DNSManifestError("provider credentials do not match the manifest")
    snapshot = provider.get_hosts(manifest.zone)
    if snapshot.status != "ok":
        raise DNSManifestError(
            f"provider fetch failed for {manifest.zone}: {snapshot.message}"
        )
    if manifest.provider == "dynadot":
        if snapshot.zone_ttl is None:
            raise DNSManifestError("Dynadot did not return the observed zone TTL")
        desired_ttls = {entry.record.ttl for entry in manifest.records}
        if desired_ttls != {snapshot.zone_ttl}:
            raise DNSManifestError(
                "Dynadot manifest TTL must equal the observed zone-wide TTL"
            )
    next_records = merge_dns_manifest_records(
        snapshot.records, manifest.records
    )
    changes = _changes(snapshot.records, next_records)
    backup_path = None
    if apply and changes:
        if backup_dir is None or not backup_dir.is_absolute():
            raise DNSManifestError("live apply requires an absolute backup_dir")
        extension = getattr(provider, "backup_format", "txt")
        backup_path = _write_backup(
            manifest.provider,
            manifest.zone,
            snapshot.raw,
            backup_dir,
            extension,
        )
        provider.set_hosts(
            manifest.zone, next_records, mail_policy="preserve"
        )
        verified = provider.get_hosts(manifest.zone)
        if verified.status != "ok":
            raise DNSManifestError("post-apply provider verification failed")
        projected = merge_dns_manifest_records(
            verified.records, manifest.records
        )
        if {_record_identity(record) for record in projected} != {
            _record_identity(record) for record in verified.records
        }:
            raise DNSManifestError(
                "post-apply zone does not match the managed projection"
            )
    return {
        "contract_version": 1,
        "app_id": manifest.app_id,
        "zone": manifest.zone,
        "provider": manifest.provider,
        "mode": "apply" if apply else "connected-plan",
        "status": (
            "applied"
            if apply and changes
            else "planned"
            if changes
            else "verified"
        ),
        "preserve_unmanaged": True,
        "changes": changes,
        "backup_path": str(backup_path) if backup_path else None,
    }


def namecheap_provider(
    credentials: Path, client_ip: str | None
) -> NamecheapDNSProvider:
    return NamecheapDNSProvider(
        credentials=credentials, client_ip=client_ip
    )


def provider_from_credentials(
    provider: str,
    credentials: Path,
    client_ip: str | None,
) -> NamecheapDNSProvider | DynadotDNSProvider:
    if provider == "namecheap":
        return namecheap_provider(credentials, client_ip)
    if provider == "dynadot":
        if client_ip is not None:
            raise ValueError("--client-ip is only valid for Namecheap")
        return DynadotDNSProvider(credentials=credentials)
    raise ValueError("unsupported DNS provider")
