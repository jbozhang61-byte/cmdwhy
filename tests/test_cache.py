import os
import shutil
import sqlite3
import tempfile
import unittest

from cmdwhy.sources import load_events

from tests.helpers import temp_config


class CacheTest(unittest.TestCase):
    def setUp(self):
        self.cfg, self.home = temp_config()
        fd, self.path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("  1  mysql --password=hunter2 -e 'select 1'\n  2  ls\n")
        self.cfg.sources = [self.path]

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_cache_hit_and_invalidation(self):
        first, _meta = load_events(self.cfg)
        self.assertEqual(len(first), 2)
        self.assertTrue(os.path.exists(self.cfg.cache_path))
        second, _meta = load_events(self.cfg)
        self.assertEqual([event.uid for event in first], [event.uid for event in second])
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("  3  git status\n")
        third, _meta = load_events(self.cfg)
        self.assertEqual(len(third), 3)

    def test_cache_is_redacted(self):
        load_events(self.cfg)
        con = sqlite3.connect(self.cfg.cache_path)
        try:
            payload = con.execute("SELECT events FROM parse_cache").fetchone()[0]
        finally:
            con.close()
        self.assertNotIn("hunter2", payload)
        self.assertIn("***", payload)


if __name__ == "__main__":
    unittest.main()
