"""Versioned Synbios↔Exo integration contract helpers (stdlib + coordinator only)."""

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "prototype"))

from harness.exo_integration_adapter import (  # noqa: E402
    contract_version,
    host_grants_payload,
    swarm_references,
)
from coordinator import INTEGRATION_SURFACE  # noqa: E402


class ExoIntegrationAdapterTests(unittest.TestCase):
    def test_contract_version_matches_workspace(self):
        self.assertEqual(contract_version(), INTEGRATION_SURFACE["version"])
        refs = swarm_references()
        self.assertIn("1189", refs)
        self.assertEqual(refs["1189"], "task_contract")

    def test_host_grants_payload_roots_under_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "proj"
            ws.mkdir()
            payload = host_grants_payload(ws, ["src/x.py", "docs"])
        self.assertEqual(payload["integration_surface_version"], INTEGRATION_SURFACE["version"])
        root = str(ws.resolve())
        self.assertEqual(payload["workspace_root"], root)
        self.assertIn(f"{root}/docs", payload["write_roots"])
        self.assertIn(f"{root}/src/x.py", payload["write_roots"])


if __name__ == "__main__":
    unittest.main()
