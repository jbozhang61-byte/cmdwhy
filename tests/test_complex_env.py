import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from cmdwhy.analyze import analyze, build_sessions
from cmdwhy.config import Config
from cmdwhy.context import infer_context
from cmdwhy.env import build_env, detect_project, runtime_profile
from cmdwhy.model import Event
from cmdwhy.sources import merge_events


class ComplexEnvironmentTest(unittest.TestCase):
    def test_runtime_profile_captures_orchestration(self):
        values = {
            "TMUX_PANE": "%7",
            "KUBE_CONTEXT": "prod-eu",
            "AWS_PROFILE": "readonly",
            "CONDA_DEFAULT_ENV": "ml",
            "TERM_PROGRAM": "tmux",
            "TF_WORKSPACE": "prod",
            "AWS_REGION": "eu-west-1",
            "GOOGLE_CLOUD_PROJECT": "data-prod",
            "COMPOSE_PROJECT_NAME": "shop",
            "IN_NIX_SHELL": "impure",
        }
        with patch.dict(os.environ, values, clear=True):
            profile = runtime_profile()
        self.assertEqual(profile["tmux"], "%7")
        self.assertEqual(profile["session"], "%7")
        self.assertEqual(profile["kube_context"], "prod-eu")
        self.assertEqual(profile["aws_profile"], "readonly")
        self.assertEqual(profile["conda_env"], "ml")
        self.assertEqual(profile["tf_workspace"], "prod")
        self.assertEqual(profile["aws_region"], "eu-west-1")
        self.assertEqual(profile["gcloud_project"], "data-prod")
        self.assertEqual(profile["compose_project"], "shop")
        self.assertEqual(profile["nix_shell"], "impure")

    def test_sessions_split_by_terminal_identity(self):
        events = [
            Event(ts=100, cmd="ls", host="devbox", runtime={"session": "tmux-a"}),
            Event(ts=101, cmd="pwd", host="devbox", runtime={"session": "tmux-a"}),
            Event(ts=102, cmd="git status", host="devbox", runtime={"session": "tmux-b"}),
        ]
        sessions = build_sessions(events, 1800, {})
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0].n, 2)
        self.assertEqual(sessions[1].n, 1)

    def test_worktree_git_file_is_a_project_root(self):
        root = tempfile.mkdtemp(prefix="cmdwhy-worktree-")
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        with open(os.path.join(root, ".git"), "w", encoding="utf-8") as fh:
            fh.write("gitdir: /tmp/worktrees/api\n")
        project = detect_project(root)
        self.assertIsNotNone(project)
        self.assertEqual(os.path.abspath(project[0]), os.path.abspath(root))
        self.assertIn("git", project[2] + [project[1]])

    def test_runtime_reaches_context_and_output(self):
        home = tempfile.mkdtemp(prefix="cmdwhy-runtime-")
        self.addCleanup(lambda: shutil.rmtree(home, ignore_errors=True))
        cfg = Config(home=home)
        cfg.sources = []
        cfg.ensure()
        rows = [
            {
                "ts": 1763341920,
                "cmd": "kubectl get pods",
                "cwd": home,
                "distro": "Ubuntu 24.04",
                "runtime": {"session": "tmux-a", "kube_context": "prod-eu", "aws_profile": "readonly"},
            }
        ]
        with open(os.path.join(home, "complex.jsonl"), "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
        events, _ = __import__("cmdwhy.sources", fromlist=["load_events"]).load_events(
            cfg, extra_paths=[os.path.join(home, "complex.jsonl")], use_store=False
        )
        analysis = analyze(merge_events(events, cfg), cfg, {}, with_context=True)
        context = analysis.contexts[1]
        self.assertIn("kube:prod-eu", context.environment)
        self.assertIn("aws:readonly", context.environment)


if __name__ == "__main__":
    unittest.main()
