import os
import shutil
import tempfile
import unittest

from cmdwhy.analyze import analyze
from cmdwhy.demo_data import demo_events
from cmdwhy.model import Event
from cmdwhy.report import Renderer
from cmdwhy.resolve import resolve_targets
from cmdwhy.sources import merge_events, parse_file
from cmdwhy.util import Paint

from tests.helpers import temp_config


class StableIdTest(unittest.TestCase):
    def setUp(self):
        self.cfg, self.home = temp_config()
        self.renderer = Renderer(Paint(False), home="/home/ubuntu")

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_uid_survives_inserted_event(self):
        first = analyze(merge_events(demo_events(), self.cfg), self.cfg, {"files": ["demo"]})
        target = first.event(3)
        uid = target.uid
        self.assertTrue(uid)

        extra = Event(ts=0, cmd="echo inserted-before", source="manual")
        shifted = analyze(merge_events([extra] + demo_events(), self.cfg), self.cfg, {"files": ["demo"]})
        matches = [event for event in shifted.events if event.cmd == target.cmd and event.ts == target.ts]
        self.assertEqual(len(matches), 1)
        self.assertNotEqual(matches[0].seq, target.seq)
        self.assertEqual(matches[0].uid, uid)

        seqs, notes = resolve_targets(shifted, ["e" + uid])
        self.assertEqual(seqs, [matches[0].seq])
        text = self.renderer.render_explain(shifted, seqs)
        self.assertIn("e" + uid, text)

    def test_dedupe_same_history_id_across_sources(self):
        hook = Event(ts=100, cmd="git status", hist_id=7, exit_code=0, source="hook")
        history = Event(ts=200, cmd="git status", hist_id=7, source="bash")
        merged = merge_events([hook, history], self.cfg)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].exit_code, 0)

    def test_dedupe_same_uid(self):
        one = Event(ts=100, cmd="ls", uid="abc1234567", source="hook")
        two = Event(ts=999, cmd="ls", uid="abc1234567", source="history")
        merged = merge_events([one, two], self.cfg)
        self.assertEqual(len(merged), 1)

    def test_parse_file_ids_are_reproducible(self):
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("  1  git status\n  2  ls -la\n")
            first, _fmt = parse_file(path)
            second, _fmt = parse_file(path)
            self.assertEqual([event.uid for event in first], [event.uid for event in second])
            self.assertTrue(all(event.uid for event in first))
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
