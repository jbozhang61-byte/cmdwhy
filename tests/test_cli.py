import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CliTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cmdwhy-cli-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.home, ignore_errors=True))
        with open(os.path.join(self.home, "config.json"), "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "sources": []}, fh)

    def run_cli(self, *args, expect=None, input_text=None):
        env = os.environ.copy()
        env["CMDWHY_HOME"] = self.home
        env["PYTHONPATH"] = ROOT
        env["PYTHONIOENCODING"] = "utf-8"
        env["NO_COLOR"] = "1"
        proc = subprocess.run(
            [sys.executable, "-m", "cmdwhy"] + list(args),
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=180,
            input=input_text,
        )
        if expect is not None:
            self.assertEqual(proc.returncode, expect, proc.stdout + "\n" + proc.stderr)
        return proc

    def write_events(self):
        path = os.path.join(self.home, "fixture.jsonl")
        rows = [
            {
                "ts": 1763341920,
                "cmd": "apt install jq",
                "exit_code": 1,
                "stderr": "E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)",
                "cwd": "/home/ubuntu/work/api",
                "source": "fixture",
                "distro": "Ubuntu 24.04",
                "project": "api",
            },
            {
                "ts": 1763341980,
                "cmd": "sudo apt install jq -y",
                "exit_code": 0,
                "cwd": "/home/ubuntu/work/api",
                "source": "fixture",
                "distro": "Ubuntu 24.04",
                "project": "api",
            },
            {
                "ts": 1763342100,
                "cmd": "git puhs",
                "exit_code": 1,
                "stderr": "git: 'puhs' is not a git command. See 'git --help'.",
                "cwd": "/home/ubuntu/work/api",
                "source": "fixture",
                "distro": "Ubuntu 24.04",
                "project": "api",
            },
            {
                "ts": 1763342120,
                "cmd": "git push",
                "exit_code": 0,
                "cwd": "/home/ubuntu/work/api",
                "source": "fixture",
                "distro": "Ubuntu 24.04",
                "project": "api",
            },
            {
                "ts": 1763342200,
                "cmd": "git status",
                "exit_code": 0,
                "cwd": "/home/ubuntu/work/api",
                "source": "fixture",
                "distro": "Ubuntu 24.04",
                "project": "api",
            },
        ]
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path

    def test_demo(self):
        proc = self.run_cli("demo", "--no-report", "--limit", "5", expect=0)
        self.assertIn("命令时间线", proc.stdout)
        self.assertIn("演示数据", proc.stdout)


    def test_explain_shows_task_context(self):
        proc = self.run_cli("demo", "--explain", "518", expect=0)
        self.assertIn("任务", proc.stdout)
        self.assertIn("目的", proc.stdout)
        self.assertIn("上下文", proc.stdout)
        proc = self.run_cli("demo", "--explain", "518", "--context", "3", expect=0)
        self.assertIn("任务", proc.stdout)

    def test_demo_explain_by_history_number(self):
        proc = self.run_cli("demo", "--explain", "518", expect=0)
        self.assertIn("#18", proc.stdout)
        self.assertIn("apt install jq", proc.stdout)
        self.assertIn("历史编号  518", proc.stdout)

    def test_demo_explain(self):
        proc = self.run_cli("demo", "--explain", "18,23", expect=0)
        self.assertIn("PERM:dpkg-lock", proc.stdout)
        self.assertIn("PORT:3000", proc.stdout)
        self.assertIn("sudo apt install jq -y", proc.stdout)

    def test_demo_json(self):
        proc = self.run_cli("demo", "--json", expect=0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["stats"]["sessions"], 5)
        self.assertTrue(data["annotations"][17]["fix_of"] or data["annotations"][17]["steps"])

    def test_ingest_timeline_explain(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        timeline = self.run_cli("timeline", expect=0)
        self.assertIn("git puhs", timeline.stdout)
        explain = self.run_cli("explain", "2", expect=0)
        self.assertIn("sudo apt install jq -y", explain.stdout)
        self.assertIn("修复 #1", explain.stdout)

    def test_stats_and_report(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        stats = self.run_cli("stats", expect=0)
        self.assertIn("错误率", stats.stdout)
        md = os.path.join(self.home, "report.md")
        report = self.run_cli("report", "--md", md, expect=0)
        self.assertIn("报错", report.stdout)
        self.assertTrue(os.path.exists(md))
        with open(md, "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("# 命令历史注解报告", content)
        self.assertIn("PERM:dpkg-lock", content)

    def test_fix_last(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        proc = self.run_cli("fix", "--last", expect=0)
        self.assertIn("git push", proc.stdout)
        self.assertIn("建议执行", proc.stdout)

    def test_diagnose_text(self):
        proc = self.run_cli(
            "diagnose",
            "--text",
            "error: externally-managed-environment\nSee PEP 668",
            expect=0,
        )
        self.assertIn("PIP668", proc.stdout)
        self.assertIn("虚拟环境", proc.stdout)

    def test_kb_learn_and_lookup(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        kb = self.run_cli("kb", "--signature", "PERM:dpkg-lock", expect=0)
        self.assertIn("sudo apt install jq -y", kb.stdout)
        summary = self.run_cli("kb", expect=0)
        self.assertIn("错误知识库", summary.stdout)

    def test_hook_print(self):
        proc = self.run_cli("hook", "install", "--print", "--shell", "bash", expect=0)
        self.assertIn("_cmdwhy_record", proc.stdout)
        self.assertIn("PROMPT_COMMAND", proc.stdout)
        self.assertIn("--exit", proc.stdout)

    def test_doctor(self):
        proc = self.run_cli("doctor", expect=0)
        self.assertIn("自检", proc.stdout)
        self.assertIn("Python", proc.stdout)

    def test_run_wrapper(self):
        proc = self.run_cli(
            "run",
            "--",
            sys.executable,
            "-c",
            "import sys; print('boom', file=sys.stderr); sys.exit(3)",
            expect=3,
        )
        self.assertIn("退出码 3", proc.stderr)
        self.assertIn("错误诊断", proc.stdout)



    def write_history_output(self):
        path = os.path.join(self.home, "history.txt")
        lines = [
            "  501  2026-11-17 09:00:00 ls -la",
            "  502  2026-11-17 09:01:00 git puhs",
            "  503  2026-11-17 09:02:00 git push",
            "  504  2026-11-17 09:03:00 git status",
        ]
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        return path


    def test_ingest_stdin(self):
        history = "  601  2026-11-17 10:00:00 ls -la\n  602  2026-11-17 10:01:00 git puhs\n  603  2026-11-17 10:02:00 git push\n"
        proc = self.run_cli("ingest", "--stdin", expect=0, input_text=history)
        self.assertIn("从标准输入导入 3 条命令", proc.stdout)
        timeline = self.run_cli("timeline", expect=0).stdout
        self.assertIn("h601", timeline)
        explain = self.run_cli("explain", "602", expect=0).stdout
        self.assertIn("git puhs", explain)

    def test_analyze_stdin(self):
        history = "  701  ls -la\n  702  git status\n  703  git puhs\n"
        proc = self.run_cli("analyze", "--stdin", "--json", expect=0, input_text=history)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["stats"]["events"], 3)
        hist_ids = []
        for session in payload["sessions"]:
            for event in session["events"]:
                hist_ids.append(event["hist_id"])
        self.assertEqual(hist_ids, [701, 702, 703])



    def test_run_shell_mode(self):
        proc = self.run_cli("run", "--quiet", "--shell", "--", "echo shell-ok", expect=0)
        self.assertIn("shell-ok", proc.stdout)

    def test_learn_disabled(self):
        self.run_cli("config", "--set", "learn", "false", expect=0)
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        payload = json.loads(self.run_cli("kb", "--json", expect=0).stdout)
        self.assertEqual(payload["entries"], {})


    def test_record_history_ids(self):
        self.run_cli("record", "--cmd", "ls -la", "--hist-id", "512", "--exit", "0", expect=0)
        self.run_cli("record", "--cmd", "ls -la", "--hist-id", "513", "--exit", "0", expect=0)
        listing = self.run_cli("history", "--all", expect=0).stdout
        self.assertIn("512", listing)
        self.assertIn("513", listing)
        self.assertIn("第 1/2 次", listing)
        self.assertIn("第 2/2 次", listing)
        explain = self.run_cli("explain", "513", expect=0).stdout
        self.assertIn("历史编号  513", explain)



    def test_autocorrect_same_error_from_kb(self):
        self.run_cli("mode", "autocorrect", "on", expect=0)
        entry = {
            "version": 1,
            "entries": {
                "GENERIC": {
                    "category": "GENERIC",
                    "count": 1,
                    "norm": "exit 1",
                    "remedies": {
                        "echo fixed": {
                            "steps": ["echo fixed"],
                            "count": 1,
                            "verified": 1,
                            "last_ts": 1763341920,
                        }
                    },
                }
            },
        }
        with open(os.path.join(self.home, "knowledge.json"), "w", encoding="utf-8") as fh:
            json.dump(entry, fh)
        proc = self.run_cli(
            "run",
            "--quiet",
            "--",
            sys.executable,
            "-c",
            "import sys; sys.exit(1)",
            expect=0,
        )
        self.assertIn("找到同类错误的历史修法", proc.stderr)
        self.assertIn("fixed", proc.stdout)


    def test_diagnose_marks_unverified_remedy(self):
        entry = {
            "version": 1,
            "entries": {
                "PERM": {
                    "category": "PERM",
                    "count": 1,
                    "norm": "permission denied",
                    "remedies": {
                        "sudo apt install jq": {
                            "steps": ["sudo apt install jq"],
                            "count": 1,
                            "verified": 0,
                            "last_ts": 1763341920,
                        }
                    },
                }
            },
        }
        with open(os.path.join(self.home, "knowledge.json"), "w", encoding="utf-8") as fh:
            json.dump(entry, fh)
        proc = self.run_cli("diagnose", "--signature", "PERM", expect=0)
        self.assertIn("未验证", proc.stdout)
        self.assertNotIn("你以前这样修好过", proc.stdout)




    def test_timeline_shows_purpose(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        text = self.run_cli("timeline", "-n", "5", expect=0).stdout
        self.assertIn("目的：", text)

    def test_timeline_pagination(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        first = self.run_cli("timeline", "--page", "1", "--page-size", "2", expect=0).stdout
        second = self.run_cli("timeline", "--page", "2", "--page-size", "2", expect=0).stdout
        self.assertIn("第 1/", first)
        self.assertIn("第 2/", second)
        self.assertNotEqual(first, second)

    def test_summary_project_and_period(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        data = json.loads(self.run_cli("summary", "--project", "api", "--json", expect=0).stdout)
        self.assertGreater(data["events"], 0)
        text = self.run_cli("summary", "--since", "2000-01-01", expect=0).stdout
        self.assertIn("时间范围概要", text)

    def test_search_regex_any_relevance(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        regex = self.run_cli("search", "--regex", "git|ls", expect=0).stdout
        self.assertIn("git", regex)
        any_term = self.run_cli("search", "--any", "git", "zzz", expect=0).stdout
        self.assertIn("git", any_term)
        ordered = self.run_cli("search", "git", "push", "--sort", "relevance", expect=0).stdout
        self.assertIn("git push", ordered)
        bad = self.run_cli("search", "--regex", "[", expect=2)
        self.assertIn("正则表达式无效", bad.stderr)



    def test_index_status_and_clear(self):
        self.run_cli("ingest", "--file", "examples/demo_history.jsonl", expect=0)
        info = json.loads(self.run_cli("index", "status", "--json", expect=0).stdout)
        self.assertTrue(info["current"])
        self.assertEqual(info["events"], 62)
        self.run_cli("search", "flask", expect=0)
        self.run_cli("index", "clear", expect=0)
        cleared = json.loads(self.run_cli("index", "status", "--json", expect=0).stdout)
        self.assertEqual(cleared["events"], 0)



    def test_block_multiple_commands(self):
        self.run_cli("ingest", "--file", "examples/demo_history.jsonl", expect=0)
        text = self.run_cli("block", "#18-30", expect=0).stdout
        self.assertIn("命令段", text)
        self.assertIn("任务", text)
        self.assertIn("分组", text)
        self.assertIn("环境变化", text)
        recent = self.run_cli("block", "--last", "5", expect=0).stdout
        self.assertIn("命令段", recent)
        payload = json.loads(self.run_cli("block", "#18-30", "--json", expect=0).stdout)
        self.assertEqual(payload["count"], 13)
        self.assertEqual(len(payload["commands"]), 13)
        self.assertTrue(payload["tasks"])

    def test_label_correction(self):
        self.run_cli("ingest", "--file", "examples/demo_history.jsonl", expect=0)
        proc = self.run_cli(
            "label", "518",
            "--task", "部署 API",
            "--purpose", "发布新版本并确认回滚点",
            expect=0,
        )
        self.assertIn("已标注", proc.stdout)
        text = self.run_cli("explain", "518", expect=0).stdout
        self.assertIn("部署 API", text)
        self.assertIn("发布新版本并确认回滚点", text)
        listed = self.run_cli("label", "--list", expect=0).stdout
        self.assertIn("部署 API", listed)
        self.run_cli("label", "518", "--clear", expect=0)
        after = self.run_cli("explain", "518", expect=0).stdout
        self.assertNotIn("部署 API", after)

    def test_repair_correction(self):
        self.run_cli("ingest", "--file", "examples/demo_history.jsonl", expect=0)
        before = self.run_cli("explain", "#18", expect=0).stdout
        self.assertIn("修复", before)
        graph = self.run_cli("repair", "graph", expect=0).stdout
        self.assertIn("修复链图", graph)
        self.run_cli("repair", "reject", "#19", expect=0)
        after = self.run_cli("explain", "#18", expect=0).stdout
        self.assertIn("这不是修复", after)
        listed = self.run_cli("repair", "list", expect=0).stdout
        self.assertIn("已否定", listed)
        self.run_cli("repair", "accept", "#19", expect=0)


    def test_shorthand_commands(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        explained = self.run_cli("#3", expect=0).stdout
        self.assertIn("命令", explained)
        searched = self.run_cli("s", "git", expect=0).stdout
        self.assertIn("命令搜索", searched)
        timeline = self.run_cli("tl", "-n", "2", expect=0).stdout
        self.assertIn("命令时间线", timeline)
        fixed = self.run_cli("fix", expect=0).stdout
        self.assertIn("命令输入检查", fixed)

    def test_summary(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        text = self.run_cli("summary", "--all", expect=0).stdout
        self.assertIn("会话概要", text)
        self.assertIn("S1", text)
        payload = json.loads(self.run_cli("summary", "--json", expect=0).stdout)
        self.assertTrue(payload)
        self.assertIn("events", payload[0])


    def test_explain_by_stable_id(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        payload = json.loads(self.run_cli("history", "--json", "--all", expect=0).stdout)
        rows = payload["rows"]
        uid = rows[0]["uid"]
        self.assertTrue(uid)
        text = self.run_cli("explain", "e" + uid, expect=0).stdout
        self.assertIn("稳定 ID", text)
        self.assertIn(rows[0]["cmd"], text)

    def test_search_filters(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        proc = self.run_cli("search", "git", expect=0)
        self.assertIn("git puhs", proc.stdout)
        fails = self.run_cli("search", "--status", "fail", expect=0)
        self.assertIn("git puhs", fails.stdout)
        self.assertIn("apt install jq", fails.stdout)
        errors = self.run_cli("search", "--error", "PERM", expect=0)
        self.assertIn("apt install jq", errors.stdout)
        self.assertNotIn("git status", errors.stdout)
        rows = json.loads(self.run_cli("search", "git", "--json", expect=0).stdout)
        self.assertEqual(len(rows), 3)
        self.assertIn("hist_id", rows[0])

    def test_search_bad_time(self):
        self.write_events()
        proc = self.run_cli("search", "ls", "--since", "not-a-time", expect=2)
        self.assertIn("无法识别的时间", proc.stderr)

    def test_mode_toggles(self):
        status = self.run_cli("mode", expect=0).stdout
        self.assertIn("suggest", status)
        self.run_cli("mode", "auto", expect=0)
        self.assertEqual(json.loads(self.run_cli("config", "--get", "autopilot", expect=0).stdout), "auto")
        self.run_cli("mode", "autocorrect", "on", expect=0)
        self.assertTrue(json.loads(self.run_cli("config", "--get", "autocorrect", expect=0).stdout))
        self.run_cli("mode", "off", expect=0)
        self.assertEqual(json.loads(self.run_cli("config", "--get", "autopilot", expect=0).stdout), "off")

    def test_do_dry_run_failure_plan(self):
        path = os.path.join(self.home, "failure.jsonl")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": 1763341920,
                        "cmd": "apt install jq",
                        "exit_code": 1,
                        "stderr": "E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)",
                        "cwd": "/home/ubuntu/work/api",
                    }
                )
                + "\n"
            )
        self.run_cli("ingest", "--file", path, expect=0)
        proc = self.run_cli("do", "--dry-run", expect=0)
        self.assertIn("下一步计划", proc.stdout)
        self.assertIn("sudo apt install jq", proc.stdout)
        total = json.loads(self.run_cli("history", "--json", expect=0).stdout)["total"]
        self.assertEqual(total, 1)


    def test_do_from_chosen_command(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        proc = self.run_cli("do", "--from", "3", "--dry-run", expect=0)
        self.assertIn("基于 #3", proc.stdout)
        self.assertIn("git push", proc.stdout)

    def test_do_refuses_when_off(self):
        self.run_cli("mode", "off", expect=0)
        proc = self.run_cli("do", expect=1)
        self.assertIn("已关闭", proc.stdout)

    def test_history_list_duplicates(self):
        path = os.path.join(self.home, "dups.txt")
        lines = [
            "  501  ls -la",
            "  502  git status",
            "  503  git status",
            "  504  git puhs",
        ]
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        self.run_cli("ingest", "--file", path, expect=0)
        listing = self.run_cli("history", "--all", expect=0).stdout
        self.assertIn("501", listing)
        self.assertIn("502", listing)
        self.assertIn("503", listing)
        self.assertIn("第 1/2 次", listing)
        self.assertIn("第 2/2 次", listing)
        duplicates = self.run_cli("history", "--duplicates", "--all", expect=0).stdout
        self.assertRegex(duplicates, r"(?m)^\s+502\s")
        self.assertRegex(duplicates, r"(?m)^\s+503\s")
        self.assertNotRegex(duplicates, r"(?m)^\s+501\s")
        explain = self.run_cli("explain", "503", expect=0).stdout
        self.assertIn("git status", explain)
        self.assertIn("历史编号  503", explain)

    def test_history_grep_and_json(self):
        path = os.path.join(self.home, "grep.txt")
        lines = ["  601  ls -la", "  602  git status", "  603  git puhs"]
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        self.run_cli("ingest", "--file", path, expect=0)
        filtered = self.run_cli("history", "--grep", "puhs", expect=0).stdout
        self.assertIn("603", filtered)
        self.assertNotIn("601", filtered)
        payload = json.loads(self.run_cli("history", "--json", expect=0).stdout)
        self.assertEqual(payload["total"], 3)
        self.assertEqual([row["hist_id"] for row in payload["rows"]], [601, 602, 603])
        self.assertEqual(payload["rows"][1]["occurrence"], 1)

    def test_demo_history_view(self):
        proc = self.run_cli("demo", "--history", "--duplicates", "--limit", "30", expect=0)
        self.assertIn("命令编号", proc.stdout)
        self.assertIn("第 1/2 次", proc.stdout)
        self.assertIn("第 2/2 次", proc.stdout)

    def test_history_number_analysis(self):
        path = self.write_history_output()
        self.run_cli("ingest", "--file", path, expect=0)
        timeline = self.run_cli("timeline", expect=0).stdout
        self.assertIn("h501", timeline)
        explain = self.run_cli("explain", "502", expect=0).stdout
        self.assertIn("git puhs", explain)
        self.assertIn("历史编号  502", explain)
        by_seq = self.run_cli("explain", "#2", expect=0).stdout
        self.assertIn("git puhs", by_seq)
        missing = self.run_cli("explain", "999", expect=1)
        self.assertIn("没有找到", missing.stdout)

    def test_analyze_history_output(self):
        path = self.write_history_output()
        payload = json.loads(self.run_cli("analyze", path, "--json", expect=0).stdout)
        self.assertEqual(payload["stats"]["events"], 4)
        hist_ids = []
        for session in payload["sessions"]:
            for event in session["events"]:
                hist_ids.append(event["hist_id"])
        self.assertEqual(hist_ids, [501, 502, 503, 504])

    def test_guide(self):
        proc = self.run_cli("guide", expect=0)
        self.assertIn("命令地图", proc.stdout)
        self.assertIn("cmdwhy fix", proc.stdout)
        data = self.run_cli("guide", "--json", expect=0)
        groups = json.loads(data.stdout)
        self.assertTrue(any(group["group"] == "开始使用" for group in groups))

    def test_version(self):
        proc = self.run_cli("version", expect=0)
        self.assertIn("cmdwhy 0.6.0", proc.stdout)

    def test_analyze_demo_file(self):
        proc = self.run_cli("analyze", "examples/demo_history.jsonl", "-n", "4", expect=0)
        self.assertIn("命令时间线", proc.stdout)
        self.assertIn("共 62 条", proc.stdout)
        payload = json.loads(self.run_cli("analyze", "examples/demo_history.jsonl", "--json", expect=0).stdout)
        self.assertEqual(payload["stats"]["events"], 62)

    def test_analyze_does_not_touch_config(self):
        self.run_cli("analyze", "examples/demo_history.jsonl", "-n", "2", expect=0)
        with open(os.path.join(self.home, "config.json"), "r", encoding="utf-8") as fh:
            config = json.load(fh)
        self.assertEqual(config["sources"], [])

    def test_config(self):
        self.assertEqual(json.loads(self.run_cli("config", "--get", "idle_gap", expect=0).stdout), 1800)
        self.run_cli("config", "--set", "idle_gap", "600", expect=0)
        self.assertEqual(json.loads(self.run_cli("config", "--get", "idle_gap", expect=0).stdout), 600)
        data = json.loads(self.run_cli("config", "--json", expect=0).stdout)
        self.assertEqual(data["idle_gap"], 600)
        self.assertIn("config.json", self.run_cli("config", "--path", expect=0).stdout)
        self.run_cli("config", "--set", "context_window", "12", expect=0)
        self.assertEqual(json.loads(self.run_cli("config", "--get", "context_window", expect=0).stdout), 12)

    def test_export(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        markdown = os.path.join(self.home, "export.md")
        proc = self.run_cli("export", "--format", "md", "-o", markdown, expect=0)
        self.assertIn("已导出", proc.stdout)
        with open(markdown, "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("# 命令历史注解报告", content)
        data = json.loads(self.run_cli("export", "--format", "json", expect=0).stdout)
        self.assertEqual(data["stats"]["events"], 5)
        self.assertEqual(len(data["annotations"]), 5)

    def test_completion(self):
        bash = self.run_cli("completion", "bash", expect=0).stdout
        self.assertIn("complete -F _cmdwhy_complete cmdwhy", bash)
        self.assertIn("analyze", bash)
        zsh = self.run_cli("completion", "zsh", expect=0).stdout
        self.assertIn("#compdef cmdwhy", zsh)
        self.assertIn("_cmdwhy", zsh)

    def test_help_lists_new_commands(self):
        proc = self.run_cli("--help", expect=0)
        for name in ("analyze", "config", "export", "completion", "guide", "version", "history"):
            self.assertIn(name, proc.stdout)

    def test_sessions_changes_additions(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        sessions = self.run_cli("sessions", expect=0)
        self.assertIn("S1", sessions.stdout)
        changes = self.run_cli("changes", expect=0)
        self.assertIn("安装软件包 jq", changes.stdout)
        additions = self.run_cli("additions", expect=0)
        self.assertIn("git", additions.stdout)

    def test_json_stats(self):
        path = self.write_events()
        self.run_cli("ingest", "--file", path, expect=0)
        proc = self.run_cli("stats", "--json", expect=0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["events"], 5)


if __name__ == "__main__":
    unittest.main()
