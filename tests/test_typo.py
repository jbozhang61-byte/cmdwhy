import unittest

from cmdwhy.typo import (
    CorpusIndex,
    damerau,
    propose_fixes,
    suggest_heads,
    suggest_subs,
)


class TypoTest(unittest.TestCase):
    def test_damerau_transposition(self):
        self.assertEqual(damerau("stauts", "status"), 1)
        self.assertEqual(damerau("git", "gti"), 1)
        self.assertEqual(damerau("push", "pull"), 2)

    def test_subcommand(self):
        suggestions = suggest_subs("git", "stauts", None)
        self.assertTrue(suggestions)
        self.assertEqual(suggestions[0].word, "status")

    def test_head_with_next_subcommand(self):
        suggestions = suggest_heads("gti", None, next_token="status")
        self.assertTrue(suggestions)
        self.assertEqual(suggestions[0].word, "git")

    def test_propose_subcommand_fix(self):
        fixes = propose_fixes("git stauts")
        self.assertTrue(fixes)
        self.assertEqual(fixes[0].command, "git status")
        self.assertEqual(fixes[0].kind, "subcommand")

    def test_propose_head_fix(self):
        fixes = propose_fixes("gti status")
        self.assertTrue(fixes)
        self.assertEqual(fixes[0].command, "git status")
        self.assertEqual(fixes[0].kind, "head")

    def test_missing_command_suggests_install(self):
        fixes = propose_fixes("frobnicate -q")
        self.assertTrue(fixes)
        self.assertEqual(fixes[0].kind, "install")

    def test_never_suggest_far_word(self):
        fixes = propose_fixes("zzzzzzz")
        self.assertTrue(not fixes or fixes[0].kind == "install")


    def test_exec_permission_fix(self):
        from cmdwhy.errors import classify_text

        error = classify_text("bash: ./deploy.sh: Permission denied", cmd="./deploy.sh")
        fixes = propose_fixes("./deploy.sh", error=error)
        self.assertTrue(fixes)
        self.assertEqual(fixes[0].command, "chmod +x ./deploy.sh")
        self.assertEqual(fixes[0].kind, "chmod")

    def test_docker_permission_fix(self):
        from cmdwhy.errors import classify_text

        error = classify_text(
            "permission denied while trying to connect to the Docker daemon socket",
            cmd="docker ps",
        )
        fixes = propose_fixes("docker ps", error=error)
        self.assertTrue(fixes)
        self.assertEqual(fixes[0].command, "sudo docker ps")

    def test_git_reject_fix(self):
        from cmdwhy.errors import classify_text

        error = classify_text("! [rejected] main -> main (fetch first)", cmd="git push")
        fixes = propose_fixes("git push", error=error)
        self.assertTrue(fixes)
        self.assertEqual(fixes[0].command, "git pull --rebase")

    def test_sudo_suggestion(self):
        from cmdwhy.errors import classify_text

        error = classify_text("E: Could not open lock file (13: Permission denied)", cmd="apt install jq")
        fixes = propose_fixes("apt install jq", error=error)
        self.assertTrue(fixes)
        self.assertEqual(fixes[0].command, "sudo apt install jq")


if __name__ == "__main__":
    unittest.main()
