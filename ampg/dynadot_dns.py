"""Guarded Dynadot REST v2 DNS provider.

Dynadot updates replace the full zone and use one zone-wide TTL.  The provider
therefore models every documented record field and rejects lossy or mixed-TTL
writes.  Credentials are sent only in signed headers, never in URLs or output.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable

from .dns import (
    DEFAULT_TTL,
    DNSZoneSnapshot,
    ProviderDNSRecord,
    _read_key_value_credentials,
)


DYNADOT_SUPPORTED_RECORD_TYPES = {
    "A",
    "AAAA",
    "ANAME",
    "CAA",
    "CNAME",
    "EMAIL",
    "FORWARD",
    "MX",
    "SRV",
    "STEALTH",
    "TXT",
}
DYNADOT_API_ORIGINS = {
    "https://api.dynadot.com",
    "https://api-sandbox.dynadot.com",
}


def dynadot_signature(
    api_key: str,
    api_secret: str,
    path_and_query: str,
    request_id: str,
    request_body: str = "",
) -> str:
    message = "\n".join(
        (api_key, path_and_query, request_id or "", request_body or "")
    )
    digest = hmac.new(
        api_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _validated_origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.rstrip("/"))
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if (
        origin not in DYNADOT_API_ORIGINS
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
    ):
        raise ValueError("Dynadot api_base_url is not an approved HTTPS origin")
    return origin


def _validated_source_cidr(value: str) -> str:
    try:
        network = ipaddress.ip_network(value, strict=True)
    except ValueError as error:
        raise ValueError("Dynadot allowed_source_cidr must be a valid CIDR") from error
    if network.version != 4 or network.prefixlen != 32:
        raise ValueError("Dynadot allowed_source_cidr must be an IPv4 /32")
    return str(network)


def _required_mapping(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(message)
    return value


def _record_value(record: dict[str, Any], name: str) -> str | None:
    value = record.get(name)
    if value is None:
        return None
    if not isinstance(value, (str, int)):
        raise RuntimeError("Dynadot returned an unsupported DNS record shape")
    return str(value)


class DynadotDNSProvider:
    name = "dynadot"
    backup_format = "json"

    def __init__(
        self,
        *,
        credentials: Path,
        opener: Callable[..., Any] | None = None,
        request_id_factory: Callable[[], str] | None = None,
    ):
        config = _read_key_value_credentials(credentials)
        self.api_base_url = _validated_origin(
            config.get("api_base_url", "")
        )
        self.api_key = config.get("api_key")
        self.api_secret = config.get("api_secret")
        self.allowed_source_cidr = _validated_source_cidr(
            config.get("allowed_source_cidr", "")
        )
        if not self.api_key:
            raise ValueError(f"missing Dynadot api_key in {credentials}")
        if not self.api_secret:
            raise ValueError(f"missing Dynadot api_secret in {credentials}")
        self._opener = opener or urllib.request.urlopen
        self._request_id_factory = request_id_factory or (
            lambda: str(uuid.uuid4())
        )

    def get_hosts(self, domain: str) -> DNSZoneSnapshot:
        response = self._request("GET", self._records_path(domain))
        data = _required_mapping(
            response.get("data"), "Dynadot DNS response omitted data"
        )
        glue = _required_mapping(
            data.get("glue_info"), "Dynadot DNS response omitted glue_info"
        )
        glue_type = str(glue.get("glue_type", "")).upper()
        if glue_type and glue_type != "DNS":
            raise RuntimeError("Dynadot zone is not using Dynadot DNS")
        ttl = glue.get("ttl", DEFAULT_TTL)
        if not isinstance(ttl, int) or ttl < 60 or ttl > 86400:
            raise RuntimeError("Dynadot returned an invalid zone TTL")
        records: list[ProviderDNSRecord] = []
        for field, name_field in (
            ("dns_main_list", None),
            ("dns_sub_list", "sub_host"),
        ):
            raw_records = glue.get(field, [])
            if not isinstance(raw_records, list):
                raise RuntimeError("Dynadot returned an unsupported DNS record list")
            for raw_record in raw_records:
                item = _required_mapping(
                    raw_record, "Dynadot returned an unsupported DNS record"
                )
                record_type = str(item.get("record_type", "")).upper()
                if record_type not in DYNADOT_SUPPORTED_RECORD_TYPES:
                    raise RuntimeError(
                        "Dynadot returned an unsupported DNS record type"
                    )
                name = "@" if name_field is None else _record_value(item, name_field)
                value1 = _record_value(item, "value1")
                value2 = _record_value(item, "value2")
                if not name or value1 is None:
                    raise RuntimeError("Dynadot returned an incomplete DNS record")
                mx_pref = None
                provider_value2 = value2
                if record_type == "MX":
                    try:
                        mx_pref = int(value2) if value2 is not None else None
                    except ValueError as error:
                        raise RuntimeError(
                            "Dynadot returned an invalid MX preference"
                        ) from error
                    if mx_pref is None or not 0 <= mx_pref <= 65535:
                        raise RuntimeError("Dynadot returned an invalid MX preference")
                    provider_value2 = None
                records.append(
                    ProviderDNSRecord(
                        name=name,
                        type=record_type,
                        value=value1,
                        ttl=ttl,
                        mx_pref=mx_pref,
                        provider_value2=provider_value2,
                    )
                )
        raw = json.dumps(response, indent=2, sort_keys=True) + "\n"
        return DNSZoneSnapshot(
            self.name,
            domain,
            raw,
            tuple(records),
            "ok",
            "zone fetched from Dynadot",
            ttl,
        )

    def set_hosts(
        self,
        domain: str,
        records: tuple[ProviderDNSRecord, ...],
        *,
        mail_policy: str,
    ) -> None:
        if mail_policy != "preserve":
            raise ValueError("Dynadot full-zone updates require mail_policy=preserve")
        if not records:
            raise ValueError("refusing to replace a Dynadot zone with no records")
        ttls = {int(record.ttl) for record in records}
        if len(ttls) != 1:
            raise ValueError("Dynadot full-zone updates require one observed zone TTL")
        ttl = next(iter(ttls))
        if ttl < 60 or ttl > 86400:
            raise ValueError("Dynadot zone TTL is invalid")
        main: list[dict[str, str]] = []
        sub: list[dict[str, str]] = []
        for record in records:
            record_type = record.type.upper()
            if record_type not in DYNADOT_SUPPORTED_RECORD_TYPES:
                raise ValueError("Dynadot record type is unsupported")
            item = {
                "record_type": record_type,
                "value1": record.value,
            }
            value2 = (
                str(record.mx_pref)
                if record_type == "MX"
                else record.provider_value2
            )
            if record_type == "MX" and record.mx_pref is None:
                raise ValueError("Dynadot MX records require mx_pref")
            if value2 is not None:
                item["value2"] = value2
            normalized_name = record.name.strip().rstrip(".").lower() or "@"
            if normalized_name == "@":
                main.append(item)
            else:
                item["sub_host"] = normalized_name
                sub.append(item)
        if len(main) > 20 or len(sub) > 100:
            raise ValueError("Dynadot zone exceeds documented record limits")
        body = {
            "dns_main_list": main,
            "dns_sub_list": sub,
            "ttl": ttl,
            "add_dns_to_current_setting": False,
        }
        self._request("POST", self._records_path(domain), body)

    @staticmethod
    def _records_path(domain: str) -> str:
        normalized = domain.strip().rstrip(".").lower()
        if not normalized or "/" in normalized:
            raise ValueError("invalid Dynadot domain")
        return "/restful/v2/domains/" + urllib.parse.quote(normalized) + "/records"

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_body = (
            json.dumps(body, sort_keys=True, separators=(",", ":"))
            if body is not None
            else ""
        )
        request_id = self._request_id_factory()
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
            "X-Signature": dynadot_signature(
                self.api_key,
                self.api_secret,
                path,
                request_id,
                request_body,
            ),
        }
        request = urllib.request.Request(
            self.api_base_url + path,
            data=request_body.encode("utf-8") if body is not None else None,
            method=method,
        )
        # Assigned rather than passed to the constructor, which routes every
        # header through add_header() and capitalises the name: X-Request-ID
        # becomes X-request-id on the wire.
        #
        # Header names are case-insensitive per RFC 9110, and Dynadot's gateway
        # is not. It matches X-Request-ID exactly, does not find the rewritten
        # form, and therefore computes the signature with an empty request id
        # while we computed ours with the UUID. The result is a valid signature
        # over a different string, reported as "the X-Signature provided is not
        # valid", which points at the algorithm and the credentials rather than
        # at a header we did send.
        request.headers = headers
        try:
            with self._opener(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            # Dynadot explains the refusal in the body. Discarding it left the
            # operator with a status code and nothing to act on, which for a 400
            # is the difference between "the domain is not in this account" and
            # "the signature is wrong". Bounded and quoted because it is remote
            # text, and the credential is never in it: the key travels in a
            # header and the signature is computed, not echoed.
            detail = ""
            try:
                body = error.read().decode("utf-8", "replace").strip()
                if body:
                    detail = f": {body[:400]}"
            except Exception:  # noqa: BLE001 - a body is a bonus, never required
                detail = ""
            raise RuntimeError(
                f"Dynadot API rejected {method} {path} with HTTP {error.code}{detail}"
            ) from error
        except urllib.error.URLError as error:
            raise RuntimeError(
                f"Dynadot API connectivity failed for {method} {path}"
            ) from error
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError("Dynadot API returned non-JSON data") from error
        if not isinstance(document, dict):
            raise RuntimeError("Dynadot API returned an unsupported response")
        code = document.get("code")
        if code is not None and str(code) not in {"200", "201", "0"}:
            raise RuntimeError(f"Dynadot API rejected {method} {path}")
        if document.get("success") is False:
            raise RuntimeError(f"Dynadot API rejected {method} {path}")
        return document
