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
)
