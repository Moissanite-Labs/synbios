import os
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(
    os.environ.get("SYNBIOS_RUN_DEMO_PARITY"),
    "demo parity runs in the browser CI job (SYNBIOS_RUN_DEMO_PARITY=1)",
)
class TestWebDemoParity(unittest.TestCase):
    def test_demo_store_matches_backend(self):
        root = Path(__file__).resolve().parents[1]
        web = root / "web"
        result = subprocess.run(
            ["npx", "--yes", "tsx", "demo-parity.test.ts"],
            cwd=web,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            result.stdout + result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
