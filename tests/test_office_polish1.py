"""Office polish 1: demo roster consistency (spec docs/specs/office-polish1.md)."""
import sys
import unittest
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE_ROOT / "template" / "office"))

import demo as demo_mod


class DemoConsistency(unittest.TestCase):
    """Agent ids in demo_config equal agent ids in demo_state, for every scene."""

    def test_ids_match_every_scene(self):
        cfg_ids = set(demo_mod.demo_config()["config"]["agents"])
        for scene in demo_mod.SCENES:
            with self.subTest(scene=scene):
                st_ids = {a["id"] for a in demo_mod.demo_state(scene)["agents"]}
                self.assertEqual(cfg_ids, st_ids)

    def test_accounts_paid_benched_coders(self):
        cfg = demo_mod.demo_config()["config"]
        st = demo_mod.demo_state("working")
        by_id = {a["id"]: a for a in st["agents"]}
        for aid, a in cfg["agents"].items():
            self.assertEqual(a["account"], by_id[aid]["account"], aid)
        self.assertEqual(set(cfg["paid_agents"]),
                         {a["id"] for a in st["agents"] if a.get("paid")})
        self.assertEqual(set(cfg["disabled_agents"]),
                         {a["id"] for a in st["agents"] if a.get("benched")})
        self.assertEqual(set(cfg["coders"]),
                         {a["id"] for a in st["agents"] if a.get("coder")})
        for c in cfg["coders"]:
            self.assertIn(f"{c}:*", cfg["fallback"])
            for m in cfg["fallback"][f"{c}:*"]:
                self.assertIn(m, cfg["agents"])


if __name__ == "__main__":
    unittest.main()
