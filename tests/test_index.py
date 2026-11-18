import shutil
import unittest

from cmdwhy import index_db
from cmdwhy.analyze import analyze
from cmdwhy.demo_data import demo_events
from cmdwhy.sources import merge_events

from tests.helpers import temp_config


class IndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.home = temp_config()
        events = merge_events(demo_events(), cls.cfg)
        cls.analysis = analyze(events, cls.cfg, {"files": ["demo"]}, with_context=True)
        index_db.update(cls.cfg, cls.analysis)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_status_current(self):
        info = index_db.status(self.cfg)
        self.assertTrue(info["current"])
        self.assertEqual(info["events"], 62)

    def test_query_and_bm25(self):
        results, total = index_db.query(self.cfg, "flask", sort="relevance")
        if results is None:
            self.skipTest("SQLite FTS5 not available")
        self.assertIsNotNone(results)
        self.assertGreaterEqual(total, 1)
        self.assertIn(3, [result.seq for result in results])
        self.assertTrue(any(result.score > 0 for result in results))

    def test_filters(self):
        results, total = index_db.query(self.cfg, "git", status="ok", limit=5)
        if results is None:
            self.skipTest("SQLite FTS5 not available")
        self.assertIsNotNone(results)
        self.assertLessEqual(total, 62)
        self.assertTrue(results)

    def test_cjk_falls_back(self):
        results, _total = index_db.query(self.cfg, "权限")
        self.assertIsNone(results)


if __name__ == "__main__":
    unittest.main()
