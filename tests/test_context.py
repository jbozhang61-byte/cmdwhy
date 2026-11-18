import shutil
import unittest

from cmdwhy.analyze import analyze
from cmdwhy.context import infer_context
from cmdwhy.demo_data import demo_events
from cmdwhy.sources import merge_events

from tests.helpers import temp_config


class ContextDemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.home = temp_config()
        cls.analysis = analyze(merge_events(demo_events(), cls.cfg), cls.cfg, {"files": ["demo"]})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def ann(self, seq):
        return self.analysis.ann(seq)

    def test_every_command_has_context(self):
        for ann in self.analysis.anns:
            self.assertTrue(ann.task, ann.seq)
            self.assertTrue(ann.purpose, ann.seq)
            self.assertIn(ann.seq, self.analysis.contexts)

    def test_python_task(self):
        ann = self.ann(3)
        self.assertEqual(ann.task, "Python 依赖与环境")
        self.assertIn("api", ann.task_goal)
        self.assertIn("MODULE:flask", ann.purpose + ann.context_summary)
        self.assertEqual(ann.phase, "排查")

    def test_venv_fix_purpose_references_nearest_error(self):
        ann = self.ann(5)
        self.assertIn("PIP668", ann.purpose)
        self.assertIn("虚拟环境", ann.purpose + ann.intent)

    def test_system_package_task(self):
        ann = self.ann(18)
        self.assertIn("软件包", ann.task)
        self.assertIn("dpkg", ann.purpose)
        context = self.analysis.contexts[18]
        self.assertIn("#18", context.summary)
        self.assertIn("#19", context.summary)

    def test_node_task_and_port_purpose(self):
        ann = self.ann(23)
        self.assertIn("Node", ann.task)
        self.assertIn("PORT:3000", ann.purpose)
        self.assertIn("开发服务", ann.task_goal)
        self.assertIn("#27", self.analysis.contexts[23].summary)

    def test_inspect_purpose(self):
        ann = self.ann(24)
        self.assertIn("端口", ann.purpose)
        self.assertEqual(ann.phase, "排查")

    def test_retry_purpose(self):
        ann = self.ann(27)
        self.assertIn("验证", ann.purpose)
        self.assertEqual(ann.phase, "验证")

    def test_git_task(self):
        ann = self.ann(45)
        self.assertIn("Git", ann.task)
        self.assertIn("GIT_REJECT", ann.purpose)

    def test_context_window_bounds(self):
        context = self.analysis.contexts[62]
        self.assertLessEqual(context.start_seq, 62)
        self.assertEqual(context.end_seq, 62)
        self.assertGreater(context.end_seq - context.start_seq + 1, 1)

    def test_environment_and_role_fields(self):
        context = self.analysis.contexts[3]
        self.assertIn("venv", context.environment)
        self.assertIn("apt", context.environment)
        self.assertEqual(context.role, "run")
        self.assertIn(context.purpose_kind, ("排查", "执行"))
        data = context.to_dict()
        self.assertIn("environment", data)
        self.assertIn("purpose_kind", data)

    def test_small_custom_window(self):
        context = infer_context(self.analysis, 18, window=2)
        self.assertLessEqual(context.start_seq, 18)
        self.assertGreaterEqual(context.end_seq, 18)
        self.assertLessEqual(context.end_seq - context.start_seq + 1, 5)


if __name__ == "__main__":
    unittest.main()
