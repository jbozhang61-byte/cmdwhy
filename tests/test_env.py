import os
import shutil
import tempfile
import unittest

from cmdwhy.env import detect_project
from cmdwhy.model import EnvInfo


class EnvTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cmdwhy-env-")

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def project(self, name, files):
        root = os.path.join(self.home, name)
        os.makedirs(root)
        for filename in files:
            path = os.path.join(root, filename)
            if filename.endswith("/"):
                os.makedirs(path)
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("")
        return detect_project(root)

    def test_more_project_kinds(self):
        cases = {
            "go": ["go.mod"],
            "rust": ["Cargo.toml"],
            "java": ["pom.xml"],
            "php": ["composer.json"],
            "ruby": ["Gemfile"],
            "dotnet": ["app.csproj"],
            "terraform": ["main.tf"],
            "kubernetes": ["Chart.yaml"],
        }
        for kind, files in cases.items():
            found = self.project(kind, files)
            self.assertIsNotNone(found, kind)
            self.assertEqual(found[1], kind)

    def test_env_serialization_has_runtime_fields(self):
        env = EnvInfo(cwd="/tmp", wsl=True, pkg_manager="apt", container=True, ssh=True)
        data = env.to_dict()
        self.assertTrue(data["wsl"])
        self.assertEqual(data["pkg_manager"], "apt")
        self.assertTrue(data["container"])
        self.assertIn("WSL", env.full())


if __name__ == "__main__":
    unittest.main()
