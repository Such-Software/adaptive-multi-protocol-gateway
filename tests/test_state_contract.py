import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from ampg.addresses import capture_addresses
from ampg.cli import main
from ampg.config import load_config
from ampg.state_contract import address_capture_candidates, state_contract


def _write_config(root: Path, protocol_block: str) -> Path:
    source = root / "site"
    source.mkdir()
    (source / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
    config_path = root / "gateway.toml"
    config_path.write_text(
        f"""
[gateway]
state_dir = "./state"
cache_dir = "./cache"
run_dir = "./run"

[profiles.mobile-i2p]
protocols = ["i2p"]

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


class StateContractTest(unittest.TestCase):
    def test_i2p_contract_declares_config_key_and_address_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config = load_config(
                _write_config(
                    root,
                    """
[site.protocols.i2p]
enabled = true
renderer = "privacy-html"
keys_file = "example-web.dat"
""",
                )
            )

            contracts = state_contract(config)

        by_role_path = {(contract.role, contract.path) for contract in contracts}
        self.assertIn(("daemon-config", root / "state/example/i2p/i2pd-tunnels.conf"), by_role_path)
        self.assertIn(("identity-key", root / "state/example/i2p/example-web.dat"), by_role_path)
        self.assertIn(("address-file", root / "state/example/i2p/hostname.txt"), by_role_path)
        sensitive = {contract.role for contract in contracts if contract.sensitive}
        self.assertEqual({"identity-key"}, sensitive)

    def test_address_capture_uses_contract_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config = load_config(
                _write_config(
                    root,
                    """
[site.protocols.i2p]
enabled = true
renderer = "privacy-html"
""",
                )
            )
            site = config.sites[0]
            protocol = site.protocols["i2p"]
            candidates = address_capture_candidates(config, site, protocol)
            address_file = root / "state/example/i2p/hostname.txt"
            address_file.parent.mkdir(parents=True)
            address_file.write_text("contractcapture.b32.i2p\n", encoding="utf-8")

            results = capture_addresses(config)

        self.assertEqual(address_file, candidates[0])
        self.assertEqual("captured", results[0].status)
        self.assertEqual(address_file, results[0].path)
        self.assertEqual("http://contractcapture.b32.i2p/", results[0].url)

    def test_state_contract_cli_respects_profile_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config_path = _write_config(
                root,
                """
[site.protocols.clearnet]
enabled = true
renderer = "clearnet"

[site.protocols.i2p]
enabled = true
renderer = "privacy-html"
""",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(
                    [
                        "--config",
                        str(config_path),
                        "state-contract",
                        "--profile",
                        "mobile-i2p",
                    ]
                )

        output = stdout.getvalue()
        self.assertEqual(0, status)
        self.assertIn("AMPG_STATE site=example protocol=i2p role=address-file", output)
        self.assertIn("sensitive=true", output)
        self.assertIn("AMPG_STATE_SUMMARY", output)
        self.assertNotIn("protocol=clearnet", output)


if __name__ == "__main__":
    unittest.main()
