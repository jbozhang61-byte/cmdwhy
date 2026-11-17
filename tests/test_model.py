import unittest

from cmdwhy.model import (
    Event,
    command_head,
    command_tokens,
    core_signature,
    similar_commands,
    split_command,
)


class ModelTest(unittest.TestCase):
    def test_split_quotes(self):
        self.assertEqual(split_command('git commit -m "fix: bug"'), ("git", "commit", "-m", "fix: bug"))

    def test_tokens_strip_sudo_and_env(self):
        self.assertEqual(command_tokens("sudo apt install -y jq"), ("apt", "install", "-y", "jq"))
        self.assertEqual(command_tokens("FOO=1 BAR=2 python3 app.py"), ("python3", "app.py"))

    def test_core_signature_drops_flags(self):
        self.assertEqual(core_signature("sudo apt install -y jq"), ("apt", "install", "jq"))
        self.assertEqual(core_signature("npm run dev -- -p 3000"), ("npm", "run", "dev", "3000"))

    def test_similar_commands(self):
        self.assertTrue(similar_commands("apt install jq", "sudo apt install jq -y"))
        self.assertFalse(similar_commands("apt install jq", "apt remove nginx"))

    def test_event_status(self):
        self.assertTrue(Event(cmd="x", exit_code=1).failed)
        self.assertFalse(Event(cmd="x", exit_code=0).failed)
        self.assertFalse(Event(cmd="x").failed)

    def test_head(self):
        self.assertEqual(command_head("sudo -u root systemctl restart nginx"), "systemctl")


if __name__ == "__main__":
    unittest.main()
