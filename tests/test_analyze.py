import shutil
import unittest

from cmdwhy.analyze import analyze
from cmdwhy.config import Config
from cmdwhy.demo_data import demo_events
from cmdwhy.sources import merge_events

from tests.helpers import temp_config


class AnalyzeDemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.home = temp_config()
        cls.events = merge_events(demo_events(), cls.cfg)
        cls.analysis = analyze(cls.events, cls.cfg, {"files": ["demo"], "warnings": []})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def ann(self, seq):
        return self.analysis.ann(seq)

    def test_counts(self):
        self.assertEqual(len(self.analysis.events), 62)
        self.assertEqual(len(self.analysis.sessions), 5)
        self.assertEqual(self.analysis.sessions[0].n, 17)

    def test_module_error_and_venv_chain(self):
        ann = self.ann(3)
        self.assertEqual(ann.error.signature, "MODULE:flask")
        self.assertTrue(ann.verified)
        self.assertEqual(ann.verified_at, 9)
        self.assertIn("python3 -m venv .venv", " ".join(ann.steps))
        self.assertNotIn("pip install -r requirements.txt", ann.steps)

    def test_repair_probability(self):
        self.assertGreater(self.ann(18).repair_probability, 0.7)
        self.assertGreater(self.ann(45).repair_probability, 0.0)
        self.assertLessEqual(self.ann(45).repair_probability, 1.0)

    def test_pip668(self):
        ann = self.ann(4)
        self.assertEqual(ann.error.signature, "PIP668")
        self.assertTrue(any("venv" in step for step in ann.steps))

    def test_sudo_retry(self):
        ann = self.ann(18)
        self.assertEqual(ann.error.signature, "PERM:dpkg-lock")
        self.assertTrue(ann.verified)
        self.assertEqual(ann.steps, ["sudo apt install jq -y"])
        self.assertTrue(self.ann(19).fix_of)
        self.assertIn("sudo", self.ann(18).correction["command"])

    def test_exec_permission(self):
        ann = self.ann(20)
        self.assertEqual(ann.error.signature, "PERM:exec")
        self.assertTrue(any(step.startswith("chmod +x") for step in ann.steps))

    def test_port_chain(self):
        ann = self.ann(23)
        self.assertEqual(ann.error.signature, "PORT:3000")
        self.assertEqual(ann.steps, ["kill 4242"])
        self.assertTrue(ann.verified)

    def test_docker(self):
        ann = self.ann(28)
        self.assertEqual(ann.error.category, "DOCKER")
        self.assertEqual(ann.steps, ["sudo docker ps"])

    def test_typo_correction(self):
        ann = self.ann(14)
        self.assertEqual(ann.error.signature, "CMD_NOT_FOUND:puhs")
        self.assertEqual(ann.correction["command"], "git push")
        self.assertEqual(self.ann(15).intent, "修正输入后重跑")

    def test_inferred_git_reject(self):
        ann = self.ann(45)
        self.assertEqual(ann.error.category, "GIT_REJECT")
        self.assertTrue(ann.error.inferred)
        self.assertFalse(ann.verified)
        self.assertEqual(ann.steps, ["git pull --rebase"])

    def test_inferred_sudo_in_plain_history(self):
        ann = self.ann(34)
        self.assertEqual(ann.error.signature, "PERM")
        self.assertTrue(ann.error.inferred)
        self.assertEqual(ann.steps, ["sudo nginx -t"])

    def test_per_event_env(self):
        env = self.analysis.envs[23]
        self.assertEqual(env.project, "api")
        self.assertEqual(env.cwd, "/home/ubuntu/work/api/web")
        self.assertTrue(env.distro.startswith("Ubuntu"))

    def test_changes(self):
        self.assertIn("安装软件包 jq", self.ann(19).changes[0])
        self.assertEqual(self.ann(18).changes, [])
        self.assertTrue(any("切换分支" in change for change in self.ann(17).changes))

    def test_novelty_head_level(self):
        self.assertEqual(self.ann(1).novelty, "new")
        self.assertEqual(self.ann(2).novelty, "new")
        self.assertIsNone(self.ann(13).novelty)

    def test_stats(self):
        stats = self.analysis.stats
        self.assertGreaterEqual(stats["fail"], 8)
        self.assertGreaterEqual(stats["verified_chains"], 6)
        self.assertGreater(stats["mttr"], 0)
        self.assertEqual(stats["danger"], 0)

    def test_motivation_not_spurious(self):
        self.assertNotIn("排查", self.ann(54).motivation)
        self.assertIn("排查", self.ann(24).motivation)

    def test_inspect_after_error(self):
        self.assertEqual(self.ann(24).motivation, "排查 #23 的报错")


class EmptyAnalysisTest(unittest.TestCase):
    def test_empty(self):
        cfg, home = temp_config()
        try:
            analysis = analyze([], cfg, {})
            self.assertEqual(analysis.stats["events"], 0)
            self.assertEqual(analysis.events, [])
        finally:
            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
