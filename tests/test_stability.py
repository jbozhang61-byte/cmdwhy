import os
import shutil
import tempfile
import unittest

from cmdwhy import index_db
from cmdwhy.analyze import analyze
from cmdwhy.demo_data import demo_events
from cmdwhy.sources import append_event, load_events, merge_events
from cmdwhy.model import Event

from tests.helpers import temp_config


class StabilityTest(unittest.TestCase):
    def setUp(self):
        self.cfg, self.home = temp_config()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_corrupt_cache_recovers(self):
        path = os.path.join(self.home, "history.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("  1  git status\n  2  ls -la\n")
        self.cfg.sources = [path]
        first, _meta = load_events(self.cfg)
        self.assertEqual(len(first), 2)
        with open(self.cfg.cache_path, "wb") as fh:
            fh.write(b"this is not sqlite")
        second, meta = load_events(self.cfg)
        self.assertEqual(len(second), 2)
        self.assertEqual(second[0].cmd, "git status")

    def test_corrupt_index_recovers(self):
        analysis = analyze(merge_events(demo_events(), self.cfg), self.cfg, {}, with_context=True)
        index_db.update(self.cfg, analysis)
        with open(self.cfg.index_path, "wb") as fh:
            fh.write(b"broken index")
        self.assertFalse(index_db.is_current(self.cfg))
        events, _total = index_db.query(self.cfg, "git")
        self.assertIn(events, (None, []))
        index_db.update(self.cfg, analysis)
        self.assertTrue(index_db.is_current(self.cfg))
        results, total = index_db.query(self.cfg, "flask", sort="relevance")
        if results is not None:
            self.assertGreaterEqual(total, 1)

    def test_malformed_source_does_not_abort(self):
        bad = os.path.join(self.home, "bad-dir")
        good = os.path.join(self.home, "good.txt")
        os.makedirs(bad)
        with open(good, "w", encoding="utf-8") as fh:
            fh.write("  1  git status\n")
        self.cfg.sources = [bad, good]
        events, meta = load_events(self.cfg)
        self.assertGreaterEqual(len(events), 1)
        self.assertTrue(meta["warnings"])

    def test_append_is_line_atomic(self):
        event = Event(cmd="echo hi", exit_code=0)
        append_event(self.cfg, event)
        append_event(self.cfg, event)
        with open(self.cfg.store_path, encoding="utf-8") as fh:
            lines = [line for line in fh if line.strip()]
        self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
