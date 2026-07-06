import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from ampg.cli import main
from ampg.config import load_config
from ampg.dns import dns_check


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


if __name__ == "__main__":
    unittest.main()
