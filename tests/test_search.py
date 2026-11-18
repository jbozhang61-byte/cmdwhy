import shutil
import unittest

from cmdwhy.analyze import analyze
from cmdwhy.demo_data import demo_events
from cmdwhy.search import parse_time, search_events
from cmdwhy.sources import merge_events

from tests.helpers import temp_config


class SearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.home = temp_config()
        cls.analysis = analyze(merge_events(demo_events(), cls.cfg), cls.cfg, {"files": ["demo"]})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_query(self):
        results, total = search_events(self.analysis, query="flask")
        self.assertGreaterEqual(total, 1)
        self.assertIn(3, [result.seq for result in results])

    def test_status(self):
        results, _total = search_events(self.analysis, status="fail", limit=0)
        seqs = [result.seq for result in results]
        self.assertIn(18, seqs)
        self.assertIn(23, seqs)
        self.assertNotIn(19, seqs)

    def test_error_filter(self):
        results, _total = search_events(self.analysis, error="PORT", limit=0)
        self.assertIn(23, [result.seq for result in results])

    def test_project_filter(self):
        results, _total = search_events(self.analysis, project="api", limit=0)
        self.assertTrue(results)
        for result in results:
            self.assertEqual(result.project, "api")

    def test_session_filter(self):
        results, total = search_events(self.analysis, session="S2", limit=0)
        self.assertEqual(total, 13)
        self.assertTrue(all(18 <= result.seq <= 30 for result in results))

    def test_time_window(self):
        start = self.analysis.events[17].ts
        results, _total = search_events(self.analysis, since_ts=start, limit=0)
        self.assertTrue(results)
        self.assertTrue(all(result.ts >= start for result in results))
        end = self.analysis.events[16].ts
        results, _total = search_events(self.analysis, until_ts=end, limit=0)
        self.assertTrue(all(result.ts <= end for result in results))

    def test_limit_and_order(self):
        results, total = search_events(self.analysis, limit=3)
        self.assertEqual(total, 62)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].seq, 62)
        oldest, _total = search_events(self.analysis, limit=3, oldest=True)
        self.assertEqual(oldest[0].seq, 1)

    def test_parse_time(self):
        self.assertAlmostEqual(parse_time("7d", now=1000000), 1000000 - 7 * 86400)
        self.assertIsNotNone(parse_time("2026-11-17"))
        with self.assertRaises(ValueError):
            parse_time("not-a-time")


    def test_regex(self):
        results, _total = search_events(self.analysis, query="flask|docker", regex=True)
        seqs = [result.seq for result in results]
        self.assertIn(3, seqs)
        self.assertIn(28, seqs)

    def test_any_term(self):
        results, _total = search_events(self.analysis, query="flask zzz-no-such-word", any_term=True)
        self.assertIn(3, [result.seq for result in results])

    def test_relevance_sort(self):
        results, _total = search_events(self.analysis, query="git push", sort="relevance", limit=5)
        self.assertTrue(results)
        self.assertGreaterEqual(results[0].score, results[-1].score)

    def test_invalid_regex(self):
        with self.assertRaises(ValueError):
            search_events(self.analysis, query="[", regex=True)

    def test_result_fields(self):
        results, _total = search_events(self.analysis, query="npm", limit=1)
        data = results[0].to_dict()
        for key in ("seq", "hist_id", "cmd", "status", "task", "error"):
            self.assertIn(key, data)


if __name__ == "__main__":
    unittest.main()
