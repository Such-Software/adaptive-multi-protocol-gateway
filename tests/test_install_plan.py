import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from ampg.cli import main
from ampg.config import load_config
from ampg.install_plan import blocked_install_steps, install_plan
from ampg.platforms import platform_by_name
from ampg.status import DaemonProbe


def _probe(*, installed: bool = False, running: bool = False):
    def probe(adapter):
        executable_path = f"/usr/bin/{adapter.executable}" if installed else None
        return DaemonProbe(
            installed=installed,
            running=running,
            executable_path=executable_path,
        )

    return probe


def _write_config(root: Path, protocol_block: str) -> Path:
    source = root / "site"
    source.mkdir()
    (source / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
    config_path = root / "gateway.toml"
    config_path.write_text(
        f"""
[profiles.mobile-i2p]
protocols = ["i2p"]
platform = "android-termux"

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


class InstallPlanTest(unittest.TestCase):
    def test_android_i2p_plan_includes_transport_and_loopback_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(
                _write_config(
                    Path(tmp),
                    """
[site.protocols.i2p]
enabled = true
renderer = "privacy-html"
daemon = "i2pd"
daemon_policy = "auto"
""",
                )
            )

            steps = install_plan(
                config,
                platform_provider=platform_by_name("android-termux"),
                daemon_probe=_probe(installed=False, running=False),
            )

        self.assertEqual([], blocked_install_steps(steps))
        package_commands = {
            (step.target, step.command)
            for step in steps
            if step.stage == "package"
        }
        self.assertIn(("i2pd", "pkg install i2pd"), package_commands)
        self.assertIn(("nginx", "pkg install nginx"), package_commands)
        self.assertTrue(any(step.stage == "state" for step in steps))
        self.assertTrue(
            any(
                step.stage == "supervisor"
                and step.command == "sv-enable ampg-example-i2p"
                for step in steps
            )
        )

    def test_adopted_daemon_has_no_managed_install_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(
                _write_config(
                    Path(tmp),
                    """
[site.protocols.tor]
enabled = true
renderer = "privacy-html"
daemon = "tor"
daemon_policy = "auto"
""",
                )
            )

            steps = install_plan(
                config,
                platform_provider=platform_by_name("linux-systemd"),
                daemon_probe=_probe(installed=True, running=True),
            )

        self.assertEqual(1, len(steps))
        self.assertEqual("adopt-existing", steps[0].action)
        self.assertEqual("skipped", steps[0].status)

    def test_unknown_platform_blocks_managed_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(
                _write_config(
                    Path(tmp),
                    """
[site.protocols.i2p]
enabled = true
renderer = "privacy-html"
daemon = "i2pd"
daemon_policy = "auto"
""",
                )
            )

            steps = install_plan(
                config,
                platform_provider=platform_by_name("unknown"),
                daemon_probe=_probe(installed=False, running=False),
            )

        self.assertEqual(1, len(steps))
        self.assertEqual("blocked", steps[0].status)
        self.assertIn("cannot manage", steps[0].message)

    def test_install_plan_cli_uses_profile_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_config(
                Path(tmp),
                """
[site.protocols.clearnet]
enabled = true
renderer = "clearnet"
daemon = "nginx"
daemon_policy = "adopt"

[site.protocols.i2p]
enabled = true
renderer = "privacy-html"
daemon = "i2pd"
daemon_policy = "auto"
""",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(
                    [
                        "--config",
                        str(config_path),
                        "install-plan",
                        "--profile",
                        "mobile-i2p",
                    ]
                )

            output = stdout.getvalue()

        self.assertEqual(0, status)
        self.assertIn("protocol=i2p", output)
        self.assertIn("platform=android-termux", output)
        self.assertIn('command="pkg install i2pd"', output)
        self.assertIn("blocked=0", output)
        self.assertNotIn("protocol=clearnet", output)


if __name__ == "__main__":
    unittest.main()
