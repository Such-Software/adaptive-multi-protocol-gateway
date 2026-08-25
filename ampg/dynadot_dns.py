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
import http.client
import io
import ssl
import time
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


def _zone_ttl(value: Any) -> int:
    """Dynadot reports the zone TTL as a string.

    A live zone came back with "300" and the read path required an int, so every
    Dynadot zone was unreadable while the write path, which already coerces with
    int(record.ttl), would have accepted the same value. Reading was stricter
    than writing, which is the wrong way round.

    A bool is excluded explicitly because it is an int in Python and True would
    otherwise pass as a TTL of 1 and be rejected for the wrong reason.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text.isdigit():
            raise RuntimeError("Dynadot returned an invalid zone TTL")
        value = int(text)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError("Dynadot returned an invalid zone TTL")
    if value < 60 or value > 86400:
        raise RuntimeError("Dynadot returned an invalid zone TTL")
    return value


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


class _Body:
    """The slice of the response interface the caller uses."""

    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        return False

    def read(self) -> bytes:
        return self._data


# Dynadot drops connections. Three plain requests to their API from one machine
# gave 000, 200, 000 within a few seconds, and a full-zone write died mid-TLS
# with UNEXPECTED_EOF_WHILE_READING.
#
# Only a connection that produced no response is retried. An HTTP status is an
# answer, however unwelcome, and repeating a request the server already judged
# would turn one refusal into several.
#
# Retrying a POST is safe here specifically because set_hosts replaces the whole
# zone with add_dns_to_current_setting false. The same body applied twice leaves
# the same zone, so a reply lost on the way back costs a duplicate write and
# nothing else. This reasoning does not transfer to an endpoint that appends.
_CONNECTION_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = (0.5, 2.0)


def _send_with_exact_header_names(request, timeout: int = 30):
    """Send the request without urllib rewriting the header names.

    urllib.request title-cases every header inside do_open, so X-Request-ID goes
    out as X-Request-Id. Header names are case-insensitive under RFC 9110 and
    Dynadot's gateway is not: it matches X-Request-ID exactly, does not find the
    rewritten form, and signs with an empty request id while we signed with the
    UUID. Every request was refused as a bad signature, which is the one thing
    the signature was not.

    No spelling survives .title() as X-Request-ID, so urllib cannot be persuaded
    to send it and the request goes out through http.client instead. The
    urllib.request.Request stays as the unit passed to an injected opener, so
    tests keep inspecting exactly what would be transmitted.
    """
    parsed = urllib.parse.urlsplit(request.full_url)
    target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    last_error = None
    for attempt in range(_CONNECTION_ATTEMPTS):
        connection = http.client.HTTPSConnection(
            parsed.hostname, parsed.port, timeout=timeout
        )
        try:
            connection.request(
                request.get_method(),
                target,
                body=request.data,
                headers=dict(request.header_items()),
            )
            response = connection.getresponse()
            payload = response.read()
            status, reason, headers = response.status, response.reason, response.headers
            break
        except (ssl.SSLError, http.client.HTTPException, ConnectionError, TimeoutError, OSError) as error:
            last_error = error
            if attempt == _CONNECTION_ATTEMPTS - 1:
                raise urllib.error.URLError(
                    f"Dynadot connection failed after {_CONNECTION_ATTEMPTS} attempts: {error}"
                ) from error
            time.sleep(_RETRY_BACKOFF_SECONDS[attempt])
        finally:
            connection.close()
    if status >= 400:
        # Raised so the caller's existing error handling, which reads the body
        # to surface the provider's own explanation, keeps working unchanged.
        raise urllib.error.HTTPError(
            request.full_url, status, reason, headers, io.BytesIO(payload)
        )
    return _Body(payload)


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
        self._opener = opener or _send_with_exact_header_names
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
        ttl = _zone_ttl(glue.get("ttl", DEFAULT_TTL))
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
                # Dynadot answers with record_value1 and writes back value1.
                # The read path only knew the write spelling, so every record on
                # a live zone came back incomplete. Both are accepted, response
                # spelling first, because that is what a real zone sends.
                value1 = _record_value(item, "record_value1")
                if value1 is None:
                    value1 = _record_value(item, "value1")
                value2 = _record_value(item, "record_value2")
                if value2 is None:
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
            # record_value1, not value1. Dynadot uses the same spelling in both
            # directions; the reader was corrected to accept it and the writer
            # was left alone on the assumption that the two differed. They do
            # not, and Dynadot answers a write in the old spelling with "if
            # record_type is entered, record_value1 must be entered", which
            # reads like a missing value rather than a misnamed one.
            item = {
                "record_type": record_type,
                "record_value1": record.value,
            }
            value2 = (
                str(record.mx_pref)
                if record_type == "MX"
                else record.provider_value2
            )
            if record_type == "MX" and record.mx_pref is None:
                raise ValueError("Dynadot MX records require mx_pref")
            if value2 is not None:
                item["record_value2"] = value2
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
