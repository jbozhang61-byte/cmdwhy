import shutil
import unittest

from cmdwhy.analyze import analyze
from cmdwhy.config import Config
from cmdwhy.demo_data import demo_events
from cmdwhy.planner import build_plan
from cmdwhy.safety import is_dangerous
from cmdwhy.sources import merge_events

from tests.helpers import temp_config


class PlannerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.home = temp_config()
        cls.raw = demo_events()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def analysis(self):
        cfg = Config(home=self.home)
        cfg.sources = []
        events = merge_events(self.raw, cfg)
        return analyze(events, cfg, {"files": ["demo"]}, with_context=True)

    def test_empty_history(self):
        analysis = analyze([], self.cfg, {})
        plan = build_plan(analysis, cwd=self.home)
        commands = [action.command for action in plan.actions]
        self.assertIn("ls -la", commands)
        self.assertIn("git status", commands)

    def test_typo_plan(self):
        plan = build_plan(self.analysis(), cwd=self.home, focus_seq=14)
        commands = [action.command for action in plan.actions]
        self.assertIn("git push", commands)

    def test_permission_plan(self):
        plan = build_plan(self.analysis(), cwd=self.home, focus_seq=18)
        commands = [action.command for action in plan.actions]
        self.assertTrue(any(command.startswith("sudo apt install jq") for command in commands))

    def test_port_plan(self):
        plan = build_plan(self.analysis(), cwd=self.home, focus_seq=23)
        commands = [action.command for action in plan.actions]
        self.assertIn("ss -ltnp | grep 3000", commands)
        self.assertIn("lsof -i :3000", commands)

    def test_git_reject_plan(self):
        plan = build_plan(self.analysis(), cwd=self.home, focus_seq=45)
        commands = [action.command for action in plan.actions]
        self.assertIn("git pull --rebase", commands)
        self.assertIn("git push origin main", commands)

    def test_risk_boundaries(self):
        permission = build_plan(self.analysis(), cwd=self.home, focus_seq=18)
        sudo_actions = [a for a in permission.actions if a.command.startswith("sudo ")]
        self.assertTrue(sudo_actions)
        self.assertTrue(all(a.risk == "high" for a in sudo_actions))
        git = build_plan(self.analysis(), cwd=self.home, focus_seq=45)
        pull = [a for a in git.actions if a.command == "git pull --rebase"][0]
        self.assertEqual(pull.risk, "medium")
        port = build_plan(self.analysis(), cwd=self.home, focus_seq=23)
        self.assertTrue(all(a.risk == "low" for a in port.actions))

    def test_autopilot_filter_never_allows_high(self):
        from cmdwhy.cli import _autopilot_actions

        permission = build_plan(self.analysis(), cwd=self.home, focus_seq=18)
        selected = _autopilot_actions(permission, allow_medium=True)
        self.assertFalse(any(action.command.startswith("sudo ") for action in selected))
        git = build_plan(self.analysis(), cwd=self.home, focus_seq=45)
        self.assertFalse(any(action.risk == "medium" for action in _autopilot_actions(git, False)))
        self.assertTrue(any(action.risk == "medium" for action in _autopilot_actions(git, True)))

    def test_no_dangerous_actions(self):
        analysis = self.analysis()
        for seq in (14, 18, 23, 45):
            plan = build_plan(analysis, cwd=self.home, focus_seq=seq)
            for action in plan.actions:
                self.assertFalse(is_dangerous(action.command), action.command)

    def test_limit(self):
        plan = build_plan(self.analysis(), cwd=self.home, limit=2, focus_seq=18)
        self.assertLessEqual(len(plan.actions), 2)

    def test_plan_serializable(self):
        plan = build_plan(self.analysis(), cwd=self.home, focus_seq=18)
        data = plan.to_dict()
        self.assertIn("actions", data)
        self.assertTrue(data["actions"])


if __name__ == "__main__":
    unittest.main()
