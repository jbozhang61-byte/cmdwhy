import unittest

from cmdwhy.errors import classify_event, classify_text, normalize_error_text
from cmdwhy.model import Event


class ErrorsTest(unittest.TestCase):
    def test_permission_dpkg(self):
        info = classify_text(
            "E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)",
            cmd="apt install jq",
        )
        self.assertEqual(info.category, "PERM")
        self.assertEqual(info.signature, "PERM:dpkg-lock")

    def test_docker_before_generic_permission(self):
        info = classify_text(
            'permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock'
        )
        self.assertEqual(info.category, "DOCKER")

    def test_pip668(self):
        info = classify_text("error: externally-managed-environment\nSee PEP 668")
        self.assertEqual(info.signature, "PIP668")

    def test_command_not_found_word(self):
        info = classify_text("bash: pytest: command not found")
        self.assertEqual(info.signature, "CMD_NOT_FOUND:pytest")
        self.assertEqual(info.missing_word, "pytest")

    def test_git_subcommand(self):
        info = classify_text("git: 'puhs' is not a git command. See 'git --help'.", cmd="git puhs")
        self.assertEqual(info.missing_word, "puhs")

    def test_module(self):
        info = classify_event(
            Event(cmd="python3 app.py", exit_code=1, stderr="ModuleNotFoundError: No module named 'flask'")
        )
        self.assertEqual(info.signature, "MODULE:flask")
        self.assertEqual(info.module, "flask")

    def test_port(self):
        info = classify_text("Error: listen EADDRINUSE: address already in use :::3000", cmd="npm run dev")
        self.assertEqual(info.signature, "PORT:3000")

    def test_exit_code_only(self):
        info = classify_event(Event(cmd="pytest", exit_code=127))
        self.assertEqual(info.category, "CMD_NOT_FOUND")
        self.assertEqual(info.confidence, "medium")

    def test_exit_126(self):
        info = classify_event(Event(cmd="./deploy.sh", exit_code=126))
        self.assertEqual(info.signature, "PERM:exec")

    def test_normalize_stable(self):
        a = normalize_error_text("FileNotFoundError: /home/a/x.py line 42 at 12:30:01")
        b = normalize_error_text("FileNotFoundError: /home/b/y.py line 7 at 09:11:55")
        self.assertEqual(a, b)

    def test_no_error_on_success(self):
        self.assertIsNone(classify_event(Event(cmd="ls", exit_code=0)))
        self.assertIsNone(classify_event(Event(cmd="ls")))


if __name__ == "__main__":
    unittest.main()
