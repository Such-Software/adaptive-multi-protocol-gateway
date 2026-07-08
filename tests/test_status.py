import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ampg.cli import main
from ampg.config import load_config
from ampg.platforms import platform_by_name
from ampg.status import DaemonProbe, _process_running, doctor_gateway, gateway_status


def _probe(*, installed: bool = False, running: bool = False):
    def probe(adapter):
        executable_path = f"/usr/bin/{adapter.executable}" if installed else None
        return DaemonProbe(
            installed=installed,
            running=running,
            executable_path=executable_path,
        )

    return probe


def _write_config(root: Path, protocol_block: str, *, source_exists: bool = True) -> Path:
    source = root / "site"
    if source_exists:
        source.mkdir()
        (source / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
    config_path = root / "gateway.toml"
    config_path.write_text(
        f"""
[[site]]
id = "example"
domain = "example.test"

[site.source]
kind = "static-html"
path = "./site"

[site.outputs]
root = "./out"
plan_root = "./plan"

{protocol_block}
""",
        encoding="utf-8",
    )
    return config_path


class StatusTest(unittest.TestCase):
    def test_auto_policy_adopts_running_daemon(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_config(
                Path(tmp),
                """
[site.protocols.tor]
enabled = true
renderer = "privacy-html"
daemon = "tor"
daemon_policy = "auto"
""",
            )
            config = load_config(config_path)

            statuses = gateway_status(
                config,
                platform_provider=platform_by_name("linux-user"),
                daemon_probe=_probe(installed=True, running=True),
            )

        self.assertEqual(1, len(statuses))
        self.assertEqual("ok", statuses[0].status)
        self.assertEqual("adopt-existing", statuses[0].action)
        self.assertEqual("system-adopted", statuses[0].provider_source)
        self.assertTrue(statuses[0].adoptable)

    def test_auto_policy_manages_missing_daemon_on_manageable_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_config(
                Path(tmp),
                """
[site.protocols.i2p]
enabled = true
renderer = "privacy-html"
daemon = "i2pd"
daemon_policy = "auto"
""",
            )
            config = load_config(config_path)

            statuses = gateway_status(
                config,
                platform_provider=platform_by_name("android-termux"),
                daemon_probe=_probe(installed=False, running=False),
            )

        self.assertEqual("ok", statuses[0].status)
        self.assertEqual("manage-owned", statuses[0].action)
        self.assertEqual("platform-package", statuses[0].provider_source)
        self.assertTrue(statuses[0].manageable)

    def test_adopt_policy_errors_when_daemon_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_config(
                Path(tmp),
                """
[site.protocols.clearnet]
enabled = true
renderer = "clearnet"
daemon = "nginx"
daemon_policy = "adopt"
""",
            )
            config = load_config(config_path)

            statuses = gateway_status(
                config,
                platform_provider=platform_by_name("linux-user"),
                daemon_probe=_probe(installed=False, running=False),
            )

        self.assertEqual("error", statuses[0].status)
        self.assertEqual("unavailable", statuses[0].action)
        self.assertEqual("unavailable", statuses[0].provider_source)
        self.assertIn("nginx is not installed", statuses[0].message)

    def test_unknown_adapter_errors_unless_external(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_config(
                Path(tmp),
                """
[site.protocols.hyperweb]
enabled = true
renderer = "clearnet"
daemon = "hyperd"
daemon_policy = "auto"
""",
            )
            config = load_config(config_path)

            statuses = gateway_status(
                config,
                platform_provider=platform_by_name("linux-user"),
                daemon_probe=_probe(installed=False, running=False),
            )

        self.assertEqual("error", statuses[0].status)
        self.assertEqual("unknown", statuses[0].backend)
        self.assertIn("no registered adapter", statuses[0].message)

    def test_doctor_reports_source_renderer_and_status_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_config(
                Path(tmp),
                """
[site.protocols.tor]
enabled = true
renderer = "unbuilt-renderer"
daemon = "tor"
daemon_policy = "adopt"
""",
                source_exists=False,
            )
            config = load_config(config_path)

            issues = doctor_gateway(
                config,
                platform_provider=platform_by_name("linux-user"),
                daemon_probe=_probe(installed=False, running=False),
            )

        codes = {issue.code for issue in issues}
        self.assertIn("source-missing", codes)
        self.assertIn("unsupported-renderer", codes)
        self.assertIn("daemon-status", codes)
        self.assertGreaterEqual(sum(1 for issue in issues if issue.severity == "error"), 3)

    def test_doctor_cli_allows_warnings_without_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_config(
                Path(tmp),
                """
[site.protocols.clearnet]
enabled = true
renderer = "clearnet"
daemon = "nginx"
daemon_policy = "external"
""",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(["--config", str(config_path), "doctor", "--platform", "unknown"])

        self.assertEqual(0, status)
        output = stdout.getvalue()
        self.assertIn("AMPG_DOCTOR_SUMMARY", output)
        self.assertIn("warnings=1", output)
        self.assertIn("errors=0", output)

    def test_i2pd_probe_accepts_distro_daemon_process_name(self):
        calls: list[tuple[str, ...]] = []

        def run(command, **_kwargs):
            calls.append(tuple(command))

            class Result:
                returncode = 0 if command[-1] == "i2pd-daemon" else 1

            return Result()

        with patch("ampg.status.shutil.which", return_value="/usr/bin/pgrep"):
            with patch("ampg.status.subprocess.run", side_effect=run):
                running = _process_running("i2pd")

        self.assertTrue(running)
        self.assertEqual(
            [
                ("/usr/bin/pgrep", "-x", "i2pd"),
                ("/usr/bin/pgrep", "-x", "i2pd-daemon"),
            ],
            calls,
        )


if __name__ == "__main__":
    unittest.main()
