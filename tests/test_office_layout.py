"""Run the Node office-zones layout test; skip when node isn't on PATH."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST = ROOT / "tests" / "office_layout.test.js"


class OfficeLayoutTest(unittest.TestCase):
    def test_node_layout(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node not on PATH")
        r = subprocess.run([node, str(TEST)], cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, f"node test failed:\n{r.stdout}\n{r.stderr}")


if __name__ == "__main__":
    unittest.main()
