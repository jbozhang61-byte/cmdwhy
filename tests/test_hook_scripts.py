import os
import shutil
import subprocess
import unittest

from cmdwhy.hook import hook_script

from tests.helpers import temp_config


def find_gnu_bash():
    candidates = []
    git = shutil.which("git")
    if git:
        base = os.path.dirname(os.path.dirname(git))
        candidates.extend([os.path.join(base, "bin", "bash.exe"), os.path.join(base, "usr", "bin", "bash.exe")])
    path = shutil.which("bash")
    if path:
        candidates.append(path)
    for candidate in candidates:
        if not candidate or not os.path.exists(candidate):
            continue
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0 and "GNU bash" in result.stdout:
            return candidate
    return None


BASH = find_gnu_bash()


class HookScriptTest(unittest.TestCase):
    def test_script_guards_against_duplicates(self):
        cfg, home = temp_config()
        try:
            script = hook_script("bash", cfg)
            self.assertIn("_cmdwhy_record", script)
            self.assertIn("PROMPT_COMMAND", script)
            self.assertIn("history 1", script)
            self.assertIn("--hist-id", script)
            self.assertIn("_CMDWHY_LAST_NUM", script)
            self.assertNotIn("$" + "{", script)
        finally:
            shutil.rmtree(home, ignore_errors=True)

    @unittest.skipUnless(BASH, "GNU bash not available")
    def test_bash_syntax(self):
        cfg, home = temp_config()
        try:
            script = hook_script("bash", cfg)
            result = subprocess.run(
                [BASH, "-n"],
                input=script,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            shutil.rmtree(home, ignore_errors=True)


    @unittest.skipUnless(BASH, "GNU bash not available")
    def test_bash_hook_reads_history_number(self):
        cfg, home = temp_config()
        try:
            script = hook_script("bash", cfg)
            probe = script + """
history() { printf '  512  git status\\n'; }
_cmdwhy_record
first_num=$_CMDWHY_LAST_NUM
first_cmd=$_CMDWHY_LAST
history() { printf '  513  git status\\n'; }
_cmdwhy_record
printf 'FIRST=%s|%s SECOND=%s\\n' "$first_num" "$first_cmd" "$_CMDWHY_LAST_NUM"
"""
            result = subprocess.run(
                [BASH, "-s"],
                input=probe,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("FIRST=512|git status SECOND=513", result.stdout)
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_zsh_script_shape(self):
        cfg, home = temp_config()
        try:
            script = hook_script("zsh", cfg)
            self.assertIn("precmd_functions", script)
            self.assertIn("fc -l -1", script)
            self.assertIn("--hist-id", script)
        finally:
            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
