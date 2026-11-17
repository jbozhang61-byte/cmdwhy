import shutil
import unittest

from cmdwhy.analyze import analyze
from cmdwhy.demo_data import demo_events
from cmdwhy.model import Analysis, Event
from cmdwhy.resolve import history_map, resolve_targets
from cmdwhy.sources import merge_events

from tests.helpers import temp_config


class ResolveDemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.home = temp_config()
        events = merge_events(demo_events(), cls.cfg)
        cls.analysis = analyze(events, cls.cfg, {"files": ["demo"]})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_history_map(self):
        table = history_map(self.analysis)
        self.assertIn(518, table)
        self.assertEqual(table[518][0].seq, 18)

    def test_bare_number_prefers_history(self):
        seqs, notes = resolve_targets(self.analysis, ["518"])
        self.assertEqual(seqs, [18])
        self.assertEqual(notes, [])

    def test_explicit_seq(self):
        self.assertEqual(resolve_targets(self.analysis, ["#18"])[0], [18])
        self.assertEqual(resolve_targets(self.analysis, ["seq:18"])[0], [18])

    def test_explicit_history_prefix(self):
        self.assertEqual(resolve_targets(self.analysis, ["h518"])[0], [18])
        self.assertEqual(resolve_targets(self.analysis, ["h:518"])[0], [18])

    def test_history_range(self):
        seqs, notes = resolve_targets(self.analysis, ["518-520"])
        self.assertEqual(seqs, [18, 19, 20])
        self.assertTrue(notes)

    def test_bare_number_falls_back_to_seq(self):
        seqs, notes = resolve_targets(self.analysis, ["18"])
        self.assertEqual(seqs, [18])
        self.assertEqual(notes, [])


    def test_explicit_seq_range(self):
        self.assertEqual(resolve_targets(self.analysis, ["#18-20"])[0], [18, 19, 20])
        self.assertEqual(resolve_targets(self.analysis, ["seq:18-20"])[0], [18, 19, 20])

    def test_explicit_history_range(self):
        self.assertEqual(resolve_targets(self.analysis, ["h518-520"])[0], [18, 19, 20])

    def test_out_of_range(self):
        seqs, notes = resolve_targets(self.analysis, ["#99999"])
        self.assertEqual(seqs, [])
        self.assertTrue(notes)

    def test_last(self):
        self.assertEqual(resolve_targets(self.analysis, ["last"])[0], [len(self.analysis.events)])

    def test_not_found(self):
        seqs, notes = resolve_targets(self.analysis, ["99999"])
        self.assertEqual(seqs, [])
        self.assertTrue(notes)

    def test_garbage(self):
        seqs, notes = resolve_targets(self.analysis, ["abc"])
        self.assertEqual(seqs, [])
        self.assertTrue(notes)


class ResolveAmbiguousTest(unittest.TestCase):
    def test_duplicate_history_number_chooses_latest(self):
        events = [
            Event(seq=1, ts=1, cmd="ls", hist_id=7),
            Event(seq=2, ts=2, cmd="pwd", hist_id=7),
        ]
        analysis = Analysis(events=events, anns=[], sessions=[])
        seqs, notes = resolve_targets(analysis, ["7"])
        self.assertEqual(seqs, [2])
        self.assertTrue(notes)


if __name__ == "__main__":
    unittest.main()
