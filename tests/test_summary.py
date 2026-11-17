import shutil
import unittest

from cmdwhy.analyze import analyze
from cmdwhy.demo_data import demo_events
from cmdwhy.report import Renderer
from cmdwhy.sources import merge_events
from cmdwhy.util import Paint

from tests.helpers import temp_config


class SummaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.home = temp_config()
        cls.analysis = analyze(merge_events(demo_events(), cls.cfg), cls.cfg, {"files": ["demo"]})
        cls.renderer = Renderer(Paint(False), home="/home/ubuntu")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_summary_sessions(self):
        text = self.renderer.render_summary(self.analysis, self.analysis.sessions)
        self.assertIn("会话概要", text)
        self.assertIn("S2", text)
        self.assertIn("S4", text)
        self.assertIn("Node 开发服务", text)
        self.assertIn("PERM:dpkg-lock", text)
        self.assertIn("Git 同步与提交", text)

    def test_summary_single_session(self):
        session = [item for item in self.analysis.sessions if item.sid == "S2"]
        text = self.renderer.render_summary(self.analysis, session)
        self.assertIn("S2", text)
        self.assertIn("sudo docker ps", text)
        self.assertNotIn("S4", text)


if __name__ == "__main__":
    unittest.main()
