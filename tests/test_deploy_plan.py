import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from ampg.cli import main


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


class DeployPlanTest(unittest.TestCase):
    def test_deploy_plan_guides_fresh_i2p_only_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config_path = root / "gateway.toml"
            init_status, _, init_error = _run_cli(
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
            self.assertEqual(0, init_status, init_error)

            status, output, error = _run_cli(
                [
                    "--config",
                    str(config_path),
                    "deploy",
                    "plan",
                    "--profile",
                    "mobile-i2p",
                ]
            )

        self.assertEqual(0, status, error)
        self.assertIn("AMPG_DEPLOY_SUMMARY status=todo", output)
        self.assertIn("AMPG_DEPLOY_STEP stage=source status=ready", output)
        self.assertIn("AMPG_DEPLOY_STEP stage=build status=todo", output)
        self.assertIn("AMPG_DEPLOY_STEP stage=dns status=skipped", output)
        self.assertIn("AMPG_DEPLOY_STEP stage=artifacts status=todo", output)
        self.assertIn("AMPG_DEPLOY_NEXT step=1 stage=build", output)
        self.assertIn("build --profile mobile-i2p", output)

    def test_deploy_plan_shows_dns_review_for_clearnet_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config_path = root / "gateway.toml"
            init_status, _, init_error = _run_cli(
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
            self.assertEqual(0, init_status, init_error)

            _, output, _ = _run_cli(
                [
                    "--config",
                    str(config_path),
                    "deploy",
                    "plan",
                    "--profile",
                    "vps-full",
                ]
            )

        self.assertIn("AMPG_DEPLOY_STEP stage=dns status=review", output)
        self.assertIn("set A/AAAA records for example.test", output)

    def test_deploy_plan_after_build_moves_build_stage_to_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config_path = root / "gateway.toml"
            init_status, _, init_error = _run_cli(
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
            self.assertEqual(0, init_status, init_error)
            build_status, _, build_error = _run_cli(["--config", str(config_path), "build"])
            self.assertEqual(0, build_status, build_error)

            status, output, error = _run_cli(
                [
                    "--config",
                    str(config_path),
                    "deploy",
                    "plan",
                    "--profile",
                    "mobile-i2p",
                ]
            )

        self.assertEqual(0, status, error)
        self.assertIn("AMPG_DEPLOY_STEP stage=build status=ready", output)
        self.assertIn("AMPG_DEPLOY_STEP stage=artifacts status=todo", output)


if __name__ == "__main__":
    unittest.main()
