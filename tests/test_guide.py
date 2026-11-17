import argparse
import unittest

from cmdwhy.cli import build_parser
from cmdwhy.guide import COMMAND_NAMES, GROUPS, completion_bash, completion_zsh, guide_data, render_guide


class GuideTest(unittest.TestCase):
    def test_commands_match_parser(self):
        parser = build_parser()
        sub = [action for action in parser._actions if isinstance(action, argparse._SubParsersAction)][0]
        expected = set(COMMAND_NAMES) | {"record"}
        self.assertEqual(expected, set(sub.choices))

    def test_groups_cover_commands(self):
        listed = set()
        for _group, items in GROUPS:
            for command, _desc in items:
                listed.add(command.split()[1] if command.startswith("cmdwhy ") else command.split()[0])
        missing = set(COMMAND_NAMES) - listed - {"record"}
        self.assertEqual(missing, set())

    def test_render_guide(self):
        text = render_guide(None)
        self.assertIn("命令地图", text)
        self.assertIn("cmdwhy fix", text)
        self.assertIn("cmdwhy completion", text)
        self.assertGreater(len(guide_data()), 5)

    def test_completion_scripts(self):
        bash = completion_bash()
        zsh = completion_zsh()
        self.assertIn("complete -F _cmdwhy_complete cmdwhy", bash)
        self.assertIn("#compdef cmdwhy", zsh)
        for name in COMMAND_NAMES:
            self.assertIn(name, bash)
            self.assertIn(name, zsh)


if __name__ == "__main__":
    unittest.main()
