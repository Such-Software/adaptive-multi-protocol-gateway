import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from ampg.cli import main
from ampg.config import load_config


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


class OnboardingTest(unittest.TestCase):
    def test_init_site_writes_loadable_gateway_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config_path = root / "gateway.toml"

            status, output, error = _run_cli(
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
                    "privacy",
                ]
            )

            config = load_config(config_path)

        self.assertEqual(0, status, error)
        self.assertIn("AMPG_INIT_SITE status=written", output)
        self.assertIn("AMPG_INIT_PROFILE name=tor-i2p", output)
        self.assertIn("AMPG_INIT_TOGGLE protocol=clearnet enabled=false", output)
        self.assertIn("AMPG_INIT_TOGGLE protocol=tor enabled=true", output)
        self.assertEqual("example", config.sites[0].id)
        self.assertTrue(config.sites[0].protocols["tor"].enabled)
        self.assertTrue(config.sites[0].protocols["i2p"].enabled)
        self.assertFalse(config.sites[0].protocols["clearnet"].enabled)
        self.assertFalse(config.sites[0].protocols["gemini"].enabled)

    def test_init_site_protocol_override_can_make_i2p_only_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config_path = root / "gateway.toml"

            status, output, error = _run_cli(
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
                    "--protocol",
                    "i2p",
                ]
            )

            config = load_config(config_path)

        self.assertEqual(0, status, error)
        self.assertIn("protocols=i2p", output)
        self.assertTrue(config.sites[0].protocols["i2p"].enabled)
        self.assertFalse(config.sites[0].protocols["tor"].enabled)
        self.assertIn("mobile-i2p", config.profiles)

    def test_init_site_full_preset_uses_auto_clearnet_for_new_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
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
                    "full",
                ]
            )
            config = load_config(config_path)

        self.assertEqual(0, status, error)
        self.assertEqual("auto", config.sites[0].protocols["clearnet"].daemon_policy)

    def test_init_site_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config_path = root / "gateway.toml"
            source = _source(root)
            args = [
                "--config",
                str(config_path),
                "init",
                "site",
                "example",
                "--domain",
                "example.test",
                "--source",
                str(source),
            ]
            self.assertEqual(0, _run_cli(args)[0])

            status, _, error = _run_cli(args)

        self.assertEqual(1, status)
        self.assertIn("config already exists", error)

    def test_init_site_output_can_build_immediately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
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
                    "--protocol",
                    "i2p",
                ]
            )
            self.assertEqual(0, status, error)

            status, output, error = _run_cli(["--config", str(config_path), "build"])

        self.assertEqual(0, status, error)
        self.assertIn("AMPG_BUILD site=example protocol=i2p", output)


if __name__ == "__main__":
    unittest.main()
