import unittest
from pathlib import Path

from ampg.platforms import detect_platform, platform_by_name


class PlatformsTest(unittest.TestCase):
    def test_detects_termux_before_generic_linux(self):
        provider = detect_platform(
            {
                "PREFIX": "/data/data/com.termux/files/usr",
                "HOME": "/data/data/com.termux/files/home",
            },
            system_name="Linux",
            path_exists=lambda path: path == Path("/run/systemd/system"),
        )

        self.assertEqual("android-termux", provider.name)
        self.assertTrue(provider.can_manage_daemons)
        self.assertFalse(provider.can_write_system_config)
        self.assertEqual(
            Path("/data/data/com.termux/files/usr/var/lib/ampg"),
            provider.state_root,
        )

    def test_detects_systemd_linux(self):
        provider = detect_platform(
            {"HOME": "/home/operator"},
            system_name="Linux",
            path_exists=lambda path: path == Path("/run/systemd/system"),
        )

        self.assertEqual("linux-systemd", provider.name)
        self.assertEqual("systemd", provider.process_supervisor)
        self.assertTrue(provider.can_write_system_config)

    def test_detects_user_space_linux_without_systemd(self):
        provider = detect_platform(
            {"HOME": "/home/operator"},
            system_name="Linux",
            path_exists=lambda path: False,
        )

        self.assertEqual("linux-user", provider.name)
        self.assertEqual(Path("/home/operator/.local/state/ampg"), provider.state_root)
        self.assertFalse(provider.can_write_system_config)

    def test_named_platforms_are_available_for_dry_runs(self):
        self.assertEqual("macos-launchd", platform_by_name("macos-launchd").name)
        self.assertEqual("unknown", platform_by_name("unknown").name)
        with self.assertRaisesRegex(ValueError, "unknown platform provider"):
            platform_by_name("mainframe")


if __name__ == "__main__":
    unittest.main()
