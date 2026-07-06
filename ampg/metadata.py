from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT_DAEMONS, DEFAULT_POLICIES
from .renderers import ACTIVE_TAGS


@dataclass(frozen=True)
class ConfigField:
    section: str
    field: str
    kind: str
    required: bool
    default: str
    description: str


@dataclass(frozen=True)
class RenderProfile:
    name: str
    summary: str
    output: str
    defaults: tuple[str, ...]


@dataclass(frozen=True)
class DaemonAdapter:
    daemon: str
    protocols: tuple[str, ...]
    default_policy: str
    generated_artifacts: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class InteractionTier:
    name: str
    summary: str
    examples: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class IdentityAdapter:
    name: str
    status: str
    transports: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class PaymentAdapter:
    name: str
    status: str
    transports: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class TransportInteractionCapability:
    transport: str
    public_max_tier: str
    identity: str
    payments: str
    realtime: str
    notes: tuple[str, ...]


CONFIG_FIELDS = (
    ConfigField("site", "id", "string", True, "", "Stable site identifier used in output paths."),
    ConfigField("site", "domain", "string", True, "", "Canonical public domain for the site."),
    ConfigField("site.source", "kind", "enum", True, "static-html", "Source adapter kind."),
    ConfigField("site.source", "path", "path", True, "", "Source tree path."),
    ConfigField("site.source", "canonical_url", "url", False, "", "Canonical clearnet URL."),
    ConfigField("site.outputs", "root", "path", True, "", "Generated output root."),
    ConfigField("site.outputs", "plan_root", "path", False, "../dist/ampg-plan", "Generated plan artifact root."),
    ConfigField(
        "site.interactions",
        "default_tier",
        "enum",
        False,
        "static",
        "Default interaction tier for routes.",
    ),
    ConfigField(
        "site.interactions",
        "deny_routes",
        "array<string>",
        False,
        "[]",
        "Route patterns that must not be published.",
    ),
    ConfigField(
        "site.interactions",
        "route_manifest",
        "path",
        False,
        "",
        "JSON route manifest generated or maintained by the application.",
    ),
    ConfigField(
        "site.interactions.route",
        "match",
        "glob",
        False,
        "",
        "Route pattern for an explicit interaction policy.",
    ),
    ConfigField(
        "site.interactions.route",
        "tier",
        "enum",
        False,
        "site.interactions.default_tier",
        "Interaction tier for a route group.",
    ),
    ConfigField(
        "site.interactions.route",
        "identity",
        "enum",
        False,
        "none",
        "Identity adapter required by a route group.",
    ),
    ConfigField(
        "site.interactions.route",
        "payments",
        "enum",
        False,
        "none",
        "Payment adapter required by a route group.",
    ),
    ConfigField(
        "site.interactions.route",
        "realtime",
        "boolean",
        False,
        "false",
        "Whether a route group requires live state or streaming updates.",
    ),
    ConfigField(
        "site.interactions.route",
        "public_allowed",
        "boolean",
        False,
        "true",
        "Whether this route group may be emitted into public protocol outputs.",
    ),
    ConfigField(
        "site.protocols.<name>",
        "enabled",
        "boolean",
        False,
        "false",
        "Whether this protocol target is built and planned.",
    ),
    ConfigField(
        "site.protocols.<name>",
        "renderer",
        "enum",
        False,
        "<protocol>",
        "Renderer profile to use for this protocol.",
    ),
    ConfigField(
        "site.protocols.<name>",
        "daemon",
        "enum",
        False,
        "protocol default",
        "Ingress daemon adapter.",
    ),
    ConfigField(
        "site.protocols.<name>",
        "daemon_policy",
        "enum",
        False,
        "protocol default",
        "Whether AMPG adopts, manages, or only renders config.",
    ),
    ConfigField(
        "site.protocols.<name>",
        "max_asset_bytes",
        "integer",
        False,
        "1048576",
        "Maximum asset size copied by privacy-html render targets.",
    ),
    ConfigField(
        "site.protocols.<name>",
        "script_policy",
        "enum",
        False,
        "strip",
        "Script handling policy for privacy-html render targets.",
    ),
    ConfigField(
        "site.protocols.<name>",
        "max_tier",
        "enum",
        False,
        "transport default",
        "Maximum interaction tier this protocol target may expose.",
    ),
    ConfigField(
        "profiles.<name>",
        "description",
        "string",
        False,
        "",
        "Human-readable deployment profile description.",
    ),
    ConfigField(
        "profiles.<name>",
        "protocols",
        "array<string>",
        False,
        "all enabled protocols",
        "Enabled protocols selected by this deployment profile.",
    ),
    ConfigField(
        "profiles.<name>",
        "platform",
        "enum",
        False,
        "detected platform",
        "Platform provider used by status, doctor, and apply when not overridden.",
    ),
    ConfigField(
        "profiles.<name>",
        "write_artifacts",
        "boolean",
        False,
        "false",
        "Whether plan/apply dry-run writes review artifacts by default.",
    ),
)


INTERACTION_TIERS = (
    InteractionTier(
        name="static",
        summary="Rendered files only.",
        examples=("documentation", "landing pages", "catalog pages"),
        notes=("Works across every currently modeled transport.",),
    ),
    InteractionTier(
        name="interactive-lite",
        summary="Client-visible state with deterministic or server-rendered updates.",
        examples=("deterministic games", "leaderboards", "quote forms", "status lookups"),
        notes=(
            "Does not require accounts or payment confirmation.",
            "Constrained transports may receive static snapshots or form-style actions.",
        ),
    ),
    InteractionTier(
        name="identity",
        summary="Authenticated sessions or signed wallet identity.",
        examples=("account pages", "wallet sign-in", "claim pages"),
        notes=(
            "Requires explicit identity adapter selection.",
            "HTTP transports can use strict cookies; wallet sign-in uses signed challenges.",
        ),
    ),
    InteractionTier(
        name="transactional",
        summary="Server-confirmed orders, wagers, deposits, invoices, or payment intents.",
        examples=("basic stores", "paid downloads", "game entry fees", "donations"),
        notes=(
            "Requires explicit payment adapter selection.",
            "Callbacks, webhook receivers, and ledger internals remain internal.",
        ),
    ),
    InteractionTier(
        name="realtime",
        summary="Live multiplayer, dashboards, websocket streams, or fast state sync.",
        examples=("multiplayer games", "live markets", "operator consoles"),
        notes=(
            "HTTP transports only in the current model.",
            "Usually clearnet or private Tor/I2P until transport-specific realtime support exists.",
        ),
    ),
    InteractionTier(
        name="internal",
        summary="Private/admin/worker surfaces that must not be published automatically.",
        examples=("admin panels", "webhooks", "worker APIs", "health endpoints"),
        notes=("Always deny by default on public outputs.",),
    ),
)


IDENTITY_ADAPTERS = (
    IdentityAdapter(
        name="none",
        status="ready",
        transports=("clearnet", "tor", "i2p", "gemini", "ipfs", "reticulum"),
        notes=("No account or signed identity required.",),
    ),
    IdentityAdapter(
        name="http-session",
        status="planned",
        transports=("clearnet", "tor", "i2p"),
        notes=(
            "Use HTTP-only cookies and strict transport-specific session scope.",
            "Profiles must not be shared across transports.",
        ),
    ),
    IdentityAdapter(
        name="siwe",
        status="planned",
        transports=("clearnet", "tor", "i2p"),
        notes=(
            "Sign-In with Ethereum style challenge/response.",
            "Wallet transport availability is a browser-shell concern.",
        ),
    ),
    IdentityAdapter(
        name="signed-link",
        status="research",
        transports=("gemini", "reticulum"),
        notes=("Use only for narrow flows with short-lived, scoped capabilities.",),
    ),
)


PAYMENT_ADAPTERS = (
    PaymentAdapter(
        name="none",
        status="ready",
        transports=("clearnet", "tor", "i2p", "gemini", "ipfs", "reticulum"),
        notes=("No payment required.",),
    ),
    PaymentAdapter(
        name="server-invoice",
        status="planned",
        transports=("clearnet", "tor", "i2p"),
        notes=(
            "Server creates invoice or payment intent and confirms settlement.",
            "Callback/webhook routes stay internal.",
        ),
    ),
    PaymentAdapter(
        name="wallet-signature",
        status="planned",
        transports=("clearnet", "tor", "i2p"),
        notes=("Browser wallet signs a request; server verifies before fulfilling.",),
    ),
    PaymentAdapter(
        name="static-instructions",
        status="planned",
        transports=("gemini", "ipfs", "reticulum"),
        notes=("Render payment instructions or donation addresses without automatic fulfillment.",),
    ),
)


TRANSPORT_INTERACTION_CAPABILITIES = (
    TransportInteractionCapability(
        transport="clearnet",
        public_max_tier="realtime",
        identity="http-session, siwe",
        payments="server-invoice, wallet-signature",
        realtime="yes",
        notes=("Highest-fidelity browser surface.",),
    ),
    TransportInteractionCapability(
        transport="tor",
        public_max_tier="transactional",
        identity="http-session, siwe",
        payments="server-invoice, wallet-signature",
        realtime="private-only",
        notes=("Prefer server-rendered flows and reduced JavaScript by default.",),
    ),
    TransportInteractionCapability(
        transport="i2p",
        public_max_tier="transactional",
        identity="http-session, siwe",
        payments="server-invoice, wallet-signature",
        realtime="private-only",
        notes=("Prefer server-rendered flows and reduced JavaScript by default.",),
    ),
    TransportInteractionCapability(
        transport="gemini",
        public_max_tier="interactive-lite",
        identity="signed-link research",
        payments="static-instructions",
        realtime="no",
        notes=("Use curated prompts or polling-friendly status pages.",),
    ),
    TransportInteractionCapability(
        transport="ipfs",
        public_max_tier="static",
        identity="none",
        payments="static-instructions",
        realtime="no",
        notes=("Content-addressed snapshots; no server-confirmed state by default.",),
    ),
    TransportInteractionCapability(
        transport="reticulum",
        public_max_tier="interactive-lite",
        identity="signed-link research",
        payments="static-instructions",
        realtime="research",
        notes=("Resilient/private routing; not an anonymity layer.",),
    ),
)


RENDER_PROFILES = (
    RenderProfile(
        name="clearnet",
        summary="High-fidelity static web output.",
        output="HTML/CSS/JS/assets",
        defaults=(
            "Copies source files except hidden/editor/VCS clutter.",
            "Keeps local JavaScript and rich media.",
            "Writes only to AMPG-marked generated output roots.",
        ),
    ),
    RenderProfile(
        name="privacy-html",
        summary="Static HTML for Tor and I2P.",
        output="HTML/CSS/assets",
        defaults=(
            f"Removes active tags: {', '.join(sorted(ACTIVE_TAGS))}.",
            "Removes inline event handlers such as onclick and onload.",
            "Removes inline style attributes.",
            "Skips JavaScript and source-map files.",
            "Skips oversized assets above max_asset_bytes.",
            "Removes remote src/poster/link asset references.",
        ),
    ),
    RenderProfile(
        name="gemtext",
        summary="Text-first Gemini output from semantic HTML.",
        output="Gemtext plus linked/downloadable assets",
        defaults=(
            "Converts HTML headings to Gemtext heading lines.",
            "Converts paragraphs and list items to flowing text.",
            "Converts anchors and images to Gemtext link lines.",
            "Rewrites local .html links to .gmi links.",
            "Skips JavaScript, CSS, source maps, and oversized assets.",
        ),
    ),
)


DAEMON_ADAPTERS = (
    DaemonAdapter(
        daemon="nginx",
        protocols=("clearnet", "tor", "i2p"),
        default_policy=DEFAULT_POLICIES["clearnet"],
        generated_artifacts=("server block snippets",),
        notes=(
            "Clearnet defaults to adopt because TLS and public vhost policy are operator-owned.",
            "Tor/I2P HTTP targets can use loopback-only server blocks.",
        ),
    ),
    DaemonAdapter(
        daemon=DEFAULT_DAEMONS["tor"],
        protocols=("tor",),
        default_policy=DEFAULT_POLICIES["tor"],
        generated_artifacts=("torrc hidden-service snippet",),
        notes=(
            "AMPG should preserve existing HiddenServiceDir material when adopting.",
            "Managed hidden-service keys belong under AMPG state.",
        ),
    ),
    DaemonAdapter(
        daemon=DEFAULT_DAEMONS["i2p"],
        protocols=("i2p",),
        default_policy=DEFAULT_POLICIES["i2p"],
        generated_artifacts=("i2pd server tunnel snippet",),
        notes=(
            "Web tunnels should use web-specific key files.",
            "Existing RPC/P2P tunnel keys are not reused for web publishing.",
        ),
    ),
    DaemonAdapter(
        daemon=DEFAULT_DAEMONS["gemini"],
        protocols=("gemini",),
        default_policy=DEFAULT_POLICIES["gemini"],
        generated_artifacts=("Agate plan values",),
        notes=(
            "Gemini serves generated Gemtext output directly.",
            "Certificate and key paths are plan values until install/apply support exists.",
        ),
    ),
    DaemonAdapter(
        daemon=DEFAULT_DAEMONS["ipfs"],
        protocols=("ipfs",),
        default_policy=DEFAULT_POLICIES["ipfs"],
        generated_artifacts=("fixture manifest route expectations",),
        notes=(
            "IPFS output is static web content for a local gateway or later pinning.",
            "IPFS is content-addressed distribution, not an anonymity layer.",
        ),
    ),
    DaemonAdapter(
        daemon=DEFAULT_DAEMONS["reticulum"],
        protocols=("reticulum",),
        default_policy=DEFAULT_POLICIES["reticulum"],
        generated_artifacts=("Reticulum page-service plan",),
        notes=(
            "Reticulum output is planned as small page-service content.",
            "Reticulum is resilient/private routing, not an anonymity layer.",
            "Physical interfaces may require explicit operator setup.",
        ),
    ),
)
