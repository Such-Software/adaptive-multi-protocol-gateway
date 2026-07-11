from __future__ import annotations

import hashlib


SECP256K1_FIELD_SIZE = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_GENERATOR = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)
Point = tuple[int, int] | None


def tagged_hash(tag: str, value: bytes) -> bytes:
    tag_hash = hashlib.sha256(tag.encode("utf-8")).digest()
    return hashlib.sha256(tag_hash + tag_hash + value).digest()


def bip340_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Verify a BIP-340 signature over the 32-byte AMPG contract digest."""

    if len(public_key) != 32 or len(message) != 32 or len(signature) != 64:
        return False
    point = _lift_x(int.from_bytes(public_key, "big"))
    if point is None:
        return False
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    if r >= SECP256K1_FIELD_SIZE or s >= SECP256K1_ORDER:
        return False
    challenge = int.from_bytes(
        tagged_hash("BIP0340/challenge", signature[:32] + public_key + message), "big"
    ) % SECP256K1_ORDER
    result = point_add(
        point_mul(s, SECP256K1_GENERATOR),
        point_mul(SECP256K1_ORDER - challenge, point),
    )
    return result is not None and result[1] % 2 == 0 and result[0] == r


def _lift_x(x: int) -> Point:
    if x >= SECP256K1_FIELD_SIZE:
        return None
    y_sq = (pow(x, 3, SECP256K1_FIELD_SIZE) + 7) % SECP256K1_FIELD_SIZE
    y = pow(y_sq, (SECP256K1_FIELD_SIZE + 1) // 4, SECP256K1_FIELD_SIZE)
    if pow(y, 2, SECP256K1_FIELD_SIZE) != y_sq:
        return None
    return x, y if y % 2 == 0 else SECP256K1_FIELD_SIZE - y


def point_add(left: Point, right: Point) -> Point:
    if left is None:
        return right
    if right is None:
        return left
    x1, y1 = left
    x2, y2 = right
    if x1 == x2 and y1 != y2:
        return None
    if left == right:
        if y1 == 0:
            return None
        slope = (
            (3 * x1 * x1)
            * pow(2 * y1, SECP256K1_FIELD_SIZE - 2, SECP256K1_FIELD_SIZE)
            % SECP256K1_FIELD_SIZE
        )
    else:
        slope = (
            (y2 - y1)
            * pow(
                (x2 - x1) % SECP256K1_FIELD_SIZE,
                SECP256K1_FIELD_SIZE - 2,
                SECP256K1_FIELD_SIZE,
            )
            % SECP256K1_FIELD_SIZE
        )
    x3 = (slope * slope - x1 - x2) % SECP256K1_FIELD_SIZE
    y3 = (slope * (x1 - x3) - y1) % SECP256K1_FIELD_SIZE
    return x3, y3


def point_mul(scalar: int, point: Point) -> Point:
    result: Point = None
    addend = point
    while scalar:
        if scalar & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        scalar >>= 1
    return result
