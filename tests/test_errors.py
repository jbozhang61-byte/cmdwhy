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


    def test_rich_error_signatures(self):
        cases = [
            ("fatal: Authentication failed for 'https://github.com/x/y.git'", "GIT_AUTH"),
            ("Permission denied (publickey).", "SSH"),
            ("npm ERR! ERESOLVE unable to resolve dependency tree", "DEPENDENCY"),
            ("yaml.scanner.ScannerError: mapping values are not allowed here", "YAML"),
            ("SSL certificate problem: certificate verify failed", "TLS"),
            ("Read-only file system", "READONLY"),
            ("go: missing go.sum entry for module", "GO"),
            ("error[E0308]: mismatched types", "RUST"),
            ("UnsupportedClassVersionError: class file version 61.0", "JAVA"),
            ("psql: error: could not connect to server", "DB"),
        ]
        for text, category in cases:
            info = classify_text(text)
            self.assertEqual(info.category, category, text)

    def test_test_failure_and_k8s(self):
        pytest_fail = classify_text("FAILED tests/test_a.py::test_x - AssertionError: 1 != 2")
        self.assertEqual(pytest_fail.category, "TEST_FAIL")
        pod = classify_text("Warning  BackOff  pod is in CrashLoopBackOff")
        self.assertEqual(pod.category, "K8S")


    def test_multilingual_errors(self):
        cases = [
            ("bash: foo: 命令未找到", "CMD_NOT_FOUND"),
            ("ls: 无法访问 'x': 没有那个文件或目录", "NOT_FOUND"),
            ("cp: 权限不够", "PERM"),
            ("bash: foo: コマンドが見つかりません", "CMD_NOT_FOUND"),
            ("Verbindung abgelehnt", "NET"),
            ("Permission non accordée", "PERM"),
            ("Module introuvable: requests", "MODULE"),
            ("Нет места на диске", "DISK"),
        ]
        for text, category in cases:
            info = classify_text(text)
            self.assertEqual(info.category, category, text)

    def test_multilingual_missing_word(self):
        info = classify_text("bash: foo: 命令未找到")
        self.assertEqual(info.missing_word, "foo")
        self.assertEqual(info.signature, "CMD_NOT_FOUND:foo")

    def test_normalize_stable(self):
        a = normalize_error_text("FileNotFoundError: /home/a/x.py line 42 at 12:30:01")
        b = normalize_error_text("FileNotFoundError: /home/b/y.py line 7 at 09:11:55")
        self.assertEqual(a, b)

    def test_no_error_on_success(self):
        self.assertIsNone(classify_event(Event(cmd="ls", exit_code=0)))
        self.assertIsNone(classify_event(Event(cmd="ls")))


if __name__ == "__main__":
    unittest.main()
