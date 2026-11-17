import os
import shutil
import unittest

from cmdwhy.analyze import analyze
from cmdwhy.demo_data import demo_events
from cmdwhy.knowledge import Knowledge, load_knowledge
from cmdwhy.sources import merge_events

from tests.helpers import temp_config


class KnowledgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.home = temp_config()
        events = merge_events(demo_events(), cls.cfg)
        cls.analysis = analyze(events, cls.cfg, {"files": ["demo"]})
        cls.knowledge = Knowledge(os.path.join(cls.home, "knowledge.json"))
        cls.learned = cls.knowledge.learn(cls.analysis)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_learned(self):
        self.assertGreaterEqual(self.learned, 6)
        self.assertIn("MODULE:flask", self.knowledge.entries)
        self.assertIn("PERM:dpkg-lock", self.knowledge.entries)

    def test_lookup_exact(self):
        remedies = self.knowledge.lookup("MODULE:flask")
        self.assertTrue(remedies)
        self.assertTrue(any("venv" in step for step in remedies[0].steps))
        self.assertGreaterEqual(remedies[0].verified, 1)

    def test_lookup_category_fallback(self):
        remedies = self.knowledge.lookup("PERM:not-seen-before", "PERM")
        self.assertTrue(remedies)

    def test_same_signature_search(self):
        remedies = self.knowledge.lookup("PORT:3000")
        self.assertTrue(remedies)
        self.assertEqual(remedies[0].steps, ["kill 4242"])

    def test_persist_and_reload(self):
        path = os.path.join(self.home, "reload.json")
        self.knowledge.path = path
        self.knowledge.save()
        loaded = Knowledge(path)
        self.assertEqual(loaded.summary()["signatures"], self.knowledge.summary()["signatures"])
        self.assertGreater(loaded.summary()["verified_fixes"], 0)

    def test_load_helper(self):
        helper = load_knowledge(self.cfg)
        self.assertIsInstance(helper, Knowledge)

    def test_lookup_text_similar(self):
        import time

        path = os.path.join(self.home, "text-kb.json")
        kb = Knowledge(path)
        kb.entries["GENERIC"] = {
            "category": "GENERIC",
            "count": 1,
            "norm": "error: connection to database timed out after 30 seconds",
            "samples": ["error: connection to database timed out after 30 seconds"],
            "remedies": {"systemctl restart postgresql": {"steps": ["systemctl restart postgresql"], "count": 1, "verified": 1, "last_ts": time.time()}},
        }
        found = kb.lookup_text("error: connection to database timed out after 55 seconds", category="GENERIC")
        self.assertTrue(found)
        self.assertEqual(found[0].command, "systemctl restart postgresql")


if __name__ == "__main__":
    unittest.main()
