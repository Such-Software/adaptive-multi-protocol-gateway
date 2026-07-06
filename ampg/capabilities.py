from __future__ import annotations


TIER_ORDER = {
    "static": 0,
    "interactive-lite": 1,
    "identity": 2,
    "transactional": 3,
    "realtime": 4,
    "internal": 5,
}
INTERACTION_TIERS = tuple(TIER_ORDER.keys())

IDENTITY_ADAPTERS = (
    "none",
    "http-session",
    "siwe",
    "signed-link",
)

PAYMENT_ADAPTERS = (
    "none",
    "server-invoice",
    "wallet-signature",
    "static-instructions",
)

DEFAULT_MAX_TIERS = {
    "clearnet": "realtime",
    "tor": "transactional",
    "i2p": "transactional",
    "gemini": "interactive-lite",
    "ipfs": "static",
    "reticulum": "interactive-lite",
}
