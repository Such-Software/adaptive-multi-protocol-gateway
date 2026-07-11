from __future__ import annotations

import json
from typing import Any


MAX_SAFE_INTEGER = 9_007_199_254_740_991


def strict_json_loads(text: str) -> Any:
    """Load the integer-only I-JSON profile used by signed AMPG contracts."""

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key!r}")
            result[key] = value
        return result

    def reject_float(value: str) -> float:
        raise ValueError(f"floating-point JSON numbers are not permitted: {value}")

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-I-JSON number is not permitted: {value}")

    return json.loads(
        text,
        object_pairs_hook=object_pairs,
        parse_float=reject_float,
        parse_constant=reject_constant,
    )


def canonicalize_jcs(value: Any) -> bytes:
    """Return RFC 8785 bytes for AMPG's integer-only I-JSON profile."""

    return _canonicalize(value).encode("utf-8")


def _canonicalize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise ValueError(f"integer exceeds I-JSON safe range: {value}")
        return str(value)
    if isinstance(value, float):
        raise TypeError("floating-point values are not supported by signed AMPG contracts")
    if isinstance(value, str):
        _reject_surrogates(value)
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_canonicalize(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        keys = sorted(value, key=lambda key: key.encode("utf-16-be"))
        return "{" + ",".join(
            _canonicalize(key) + ":" + _canonicalize(value[key]) for key in keys
        ) + "}"
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _reject_surrogates(value: str) -> None:
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError("lone Unicode surrogate is not valid I-JSON")
