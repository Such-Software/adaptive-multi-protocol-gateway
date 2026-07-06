from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_TARGET_TERMS = (
    "wowrace",
    "wowngeon",
    "smirk-monorepo",
    "medusa-multi-tenant-platform",
    "ai-gen-bot",
)


class PublicPrivateSplitTest(unittest.TestCase):
    def test_private_target_names_do_not_appear_in_public_docs(self):
        failures = []
        for path in sorted((ROOT / "docs").rglob("*.md")):
            rel = path.relative_to(ROOT)
            if "private" in rel.parts:
                continue
            text = path.read_text(encoding="utf-8").lower()
            for term in PRIVATE_TARGET_TERMS:
                if term in text:
                    failures.append(f"{rel}: contains private target term {term!r}")
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
