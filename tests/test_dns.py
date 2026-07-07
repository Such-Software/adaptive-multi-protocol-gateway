import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from ampg.cli import main
from ampg.config import load_config
from ampg.dns import ProviderDNSRecord, dns_check, merge_dns_records


def _source(root: Path) -> Path:
    source = root / "site"
    source.mkdir()
    (source / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
    return source


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(args)
    return status, stdout.getvalue(), stderr.getvalue()


def _init_config(root: Path, *, preset: str = "clearnet-only") -> Path:
    config_path = root / "gateway.toml"
    status, _, error = _run_cli(
        [
            "--config",
            str(config_path),
            "init",
            "site",
            "example",
            "--domain",
            "example.test",
            "--source",
            str(_source(root)),
            "--preset",
            preset,
        ]
    )
    if status != 0:
        raise AssertionError(error)
    return config_path


class DNSTest(unittest.TestCase):
    def test_dns_plan_static_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _init_config(Path(tmp).resolve())

            status, output, error = _run_cli(
                [
                    "--config",
                    str(config_path),
                    "dns",
                    "plan",
                    "--ipv4",
                    "203.0.113.10",
                ]
            )

        self.assertEqual(0, status, error)
        self.assertIn("AMPG_DNS_RECORD site=example domain=example.test name=@ type=A", output)
        self.assertIn('value="203.0.113.10"', output)
        self.assertIn("AMPG_DNS_RECORD site=example domain=example.test name=www type=CNAME", output)
        self.assertIn("AMPG_DNS_SUMMARY status=todo", output)

    def test_dns_plan_dynamic_records_and_router_hints(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _init_config(Path(tmp).resolve())

            status, output, error = _run_cli(
                [
                    "--config",
                    str(config_path),
                    "dns",
                    "plan",
                    "--mode",
                    "dynamic",
                    "--dynamic-hostname",
                    "example.dynamic.test",
                    "--behind-router",
                ]
            )

        self.assertEqual(0, status, error)
        self.assertIn("type=CNAME", output)
        self.assertIn('value="example.dynamic.test"', output)
        self.assertIn("type=ALIAS/ANAME", output)
        self.assertIn("AMPG_CONNECTIVITY_HINT method=port-forward", output)
        self.assertIn("AMPG_CONNECTIVITY_HINT method=reverse-tunnel", output)

    def test_dns_plan_can_include_free_domain_hints(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _init_config(Path(tmp).resolve())

            status, output, error = _run_cli(
                [
                    "--config",
                    str(config_path),
                    "dns",
                    "plan",
                    "--free-domain-hints",
                ]
            )

        self.assertEqual(0, status, error)
        self.assertIn("AMPG_FREE_DOMAIN_HINT", output)
        self.assertIn('provider="is-a.dev"', output)
        self.assertIn('suffixes="js.org"', output)
        self.assertIn("status=verify-before-use", output)
        self.assertIn("free_domain_hints=4", output)

    def test_dns_plan_skips_when_clearnet_is_not_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _init_config(Path(tmp).resolve(), preset="i2p-only")

            status, output, error = _run_cli(["--config", str(config_path), "dns", "plan"])

        self.assertEqual(0, status, error)
        self.assertIn("AMPG_DNS_SUMMARY status=skipped", output)

    def test_dns_check_compares_expected_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_init_config(Path(tmp).resolve()))

            results = dns_check(
                config,
                ipv4="203.0.113.10",
                resolver=lambda domain: {"203.0.113.10", "2001:db8::10"},
            )

        self.assertEqual(1, len(results))
        self.assertEqual("matched", results[0].status)
        self.assertEqual(("203.0.113.10",), results[0].resolved)

    def test_dns_records_include_service_and_transport_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = _source(root)
            config_path = root / "gateway.toml"
            config_path.write_text(
                f"""
[[site]]
id = "example"
domain = "example.test"

[site.source]
kind = "static-html"
path = "{source}"

[site.outputs]
root = "{root / 'dist'}"

[site.protocols.clearnet]
enabled = true

[site.protocols.tor]
enabled = true
fixture_url = "http://exampleabcdefghijklmnop.onion/"

[site.protocols.i2p]
enabled = true
i2p_url = "exampleabcdefghijklmnop.b32.i2p"

[site.protocols.gemini]
enabled = true
port = 1966

[site.protocols.reticulum]
enabled = true
rns_url = "rns://0123456789abcdef/"
port = 4242
""",
                encoding="utf-8",
            )

            status, output, error = _run_cli(
                [
                    "--config",
                    str(config_path),
                    "dns",
                    "records",
                    "--ipv4",
                    "203.0.113.10",
                    "--mail-policy",
                    "disabled",
                ]
            )

        self.assertEqual(0, status, error)
        self.assertIn("AMPG_DNS_PROVIDER_RECORD site=example domain=example.test name=@", output)
        self.assertIn("name=gemini type=A", output)
        self.assertIn("name=reticulum type=A", output)
        self.assertIn("name=_gemini._tcp type=SRV", output)
        self.assertIn('value="0 0 1966 gemini.example.test."', output)
        self.assertIn("name=_reticulum._tcp type=SRV", output)
        self.assertIn("name=_tor type=TXT", output)
        self.assertIn("name=_i2p type=TXT", output)
        self.assertIn("name=_reticulum type=TXT", output)
        self.assertIn("name=_dmarc type=TXT", output)

    def test_merge_dns_records_preserves_unmanaged_records(self):
        existing = (
            ProviderDNSRecord("@", "A", "198.51.100.9"),
            ProviderDNSRecord("@", "TXT", "google-site-verification=keep"),
            ProviderDNSRecord("@", "TXT", "v=spf1 include:old.example -all"),
            ProviderDNSRecord("@", "MX", "mail.example.test.", mx_pref=10),
            ProviderDNSRecord("www", "CNAME", "parking.example.test."),
            ProviderDNSRecord("notes", "TXT", "keep me"),
        )
        desired = (
            ProviderDNSRecord("@", "A", "203.0.113.10"),
            ProviderDNSRecord("www", "A", "203.0.113.10"),
            ProviderDNSRecord("@", "TXT", "v=spf1 -all"),
            ProviderDNSRecord("_dmarc", "TXT", "v=DMARC1; p=reject"),
        )

        merged = merge_dns_records(existing, desired, mail_policy="disabled")
        identities = {(record.name, record.type, record.value) for record in merged}

        self.assertIn(("@", "A", "203.0.113.10"), identities)
        self.assertIn(("www", "A", "203.0.113.10"), identities)
        self.assertIn(("@", "TXT", "google-site-verification=keep"), identities)
        self.assertIn(("notes", "TXT", "keep me"), identities)
        self.assertNotIn(("@", "A", "198.51.100.9"), identities)
        self.assertNotIn(("@", "TXT", "v=spf1 include:old.example -all"), identities)
        self.assertNotIn(("@", "MX", "mail.example.test."), identities)
        self.assertNotIn(("www", "CNAME", "parking.example.test."), identities)


if __name__ == "__main__":
    unittest.main()
