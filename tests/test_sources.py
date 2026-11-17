import os
import unittest

from cmdwhy.config import Config
from cmdwhy.sources import (
    detect_format,
    merge_events,
    parse_bash,
    parse_fish,
    parse_jsonl,
    parse_zsh,
)

from tests.helpers import temp_config


class SourcesTest(unittest.TestCase):
    def test_bash_timestamps(self):
        events = parse_bash("#1763341920\nls -la\n#1763341930\ngit status\n")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].cmd, "ls -la")
        self.assertEqual(events[0].ts, 1763341920.0)
        self.assertEqual(events[1].cmd, "git status")
        self.assertEqual(events[1].ts, 1763341930.0)

    def test_zsh_extended_and_multiline(self):
        text = ": 1763341920:12;echo hi\n: 1763341930:0;for i in 1 2; do\n    echo $i\ndone\n"
        events = parse_zsh(text)
        self.assertEqual(events[0].cmd, "echo hi")
        self.assertEqual(events[0].duration_ms, 12000)
        self.assertIn("for i in 1 2", events[1].cmd)
        self.assertIn("done", events[1].cmd)

    def test_fish(self):
        text = "- cmd: echo hi\n  when: 1763341920\n- cmd: ls\n  when: 1763341930\n"
        events = parse_fish(text)
        self.assertEqual([ev.cmd for ev in events], ["echo hi", "ls"])
        self.assertEqual(events[0].ts, 1763341920.0)

    def test_jsonl(self):
        text = '{"ts": 1763341920, "cmd": "ls", "exit": 0}\n{"event": {"ts": 1763341930, "command": "git status"}}\n'
        events = parse_jsonl(text)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].exit_code, 0)
        self.assertEqual(events[1].cmd, "git status")

    def test_detect(self):
        self.assertEqual(detect_format("x", ": 1763341920:0;ls\n"), "zsh")
        self.assertEqual(detect_format("x", "- cmd: ls\n"), "fish")
        self.assertEqual(detect_format("x", '{"cmd": "ls"}'), "jsonl")
        self.assertEqual(detect_format("x", "#1763341920\nls\n"), "bash")


    def test_history_output(self):
        from cmdwhy.sources import parse_history_output

        events = parse_history_output(
            "  512  git status\n"
            "  513  2026-11-17 09:12:00 ls -la\n"
            "  514  git puhs\n"
        )
        self.assertEqual([event.hist_id for event in events], [512, 513, 514])
        self.assertEqual(events[0].cmd, "git status")
        self.assertEqual(events[1].cmd, "ls -la")
        self.assertGreater(events[1].ts, 0)
        self.assertEqual(events[2].cmd, "git puhs")

    def test_history_detection(self):
        text = "  512  git status\n  513  ls -la\n  514  git puhs\n"
        self.assertEqual(detect_format("pasted.txt", text), "history")

    def test_history_ids_survive_merge(self):
        from cmdwhy.model import Event

        cfg, home = temp_config()
        try:
            event = Event(ts=100, cmd="ls", hist_id=42, source="history")
            merged = merge_events([event], cfg)
            self.assertEqual(merged[0].hist_id, 42)
        finally:
            import shutil

            shutil.rmtree(home, ignore_errors=True)

    def test_dedupe_keeps_distinct_history_entries(self):
        from cmdwhy.model import Event

        cfg, home = temp_config()
        try:
            merged = merge_events(
                [
                    Event(ts=100, cmd="ls", source="bash_history"),
                    Event(ts=100, cmd="ls", hist_id=42, exit_code=0, source="hook"),
                ],
                cfg,
            )
            # 带 history 编号的是独立的一次执行，不能被别的来源合并掉
            self.assertEqual(len(merged), 2)
            self.assertTrue(any(event.hist_id == 42 for event in merged))
        finally:
            import shutil

            shutil.rmtree(home, ignore_errors=True)

    def test_dedupe_same_history_id(self):
        from cmdwhy.model import Event

        cfg, home = temp_config()
        try:
            merged = merge_events(
                [
                    Event(ts=100, cmd="ls", hist_id=42, source="stdin"),
                    Event(ts=100, cmd="ls", hist_id=42, exit_code=0, source="hook"),
                ],
                cfg,
            )
            self.assertEqual(len(merged), 1)
            self.assertEqual(merged[0].hist_id, 42)
            self.assertEqual(merged[0].exit_code, 0)
        finally:
            import shutil

            shutil.rmtree(home, ignore_errors=True)

    def test_merge_ignores_tool_and_redacts(self):
        cfg, home = temp_config()
        try:
            from cmdwhy.model import Event

            events = [
                Event(ts=1, cmd="cmdwhy timeline"),
                Event(ts=2, cmd="mysql --password=hunter2 -u root"),
            ]
            merged = merge_events(events, cfg)
            self.assertEqual(len(merged), 1)
            self.assertNotIn("hunter2", merged[0].cmd)
            self.assertEqual(merged[0].seq, 1)
        finally:
            import shutil

            shutil.rmtree(home, ignore_errors=True)

    def test_dedupe_across_sources(self):
        cfg, home = temp_config()
        try:
            from cmdwhy.model import Event

            events = [
                Event(ts=100, cmd="ls", source="bash_history"),
                Event(ts=100, cmd="ls", source="hook", exit_code=0),
            ]
            merged = merge_events(events, cfg)
            self.assertEqual(len(merged), 1)
            self.assertEqual(merged[0].exit_code, 0)
            self.assertEqual(merged[0].source, "hook")
        finally:
            import shutil

            shutil.rmtree(home, ignore_errors=True)

    def test_append_event_redacts_store(self):
        from cmdwhy.model import Event
        from cmdwhy.sources import append_event

        cfg, home = temp_config()
        try:
            append_event(cfg, Event(cmd="mysql --password=hunter2 -u root", ts=1, source="hook"))
            with open(cfg.store_path, "r", encoding="utf-8") as fh:
                content = fh.read()
            self.assertNotIn("hunter2", content)
        finally:
            import shutil

            shutil.rmtree(home, ignore_errors=True)

    def test_same_source_duplicates_kept(self):
        cfg, home = temp_config()
        try:
            from cmdwhy.model import Event

            events = [Event(ts=100, cmd="git push", source="bash_history"), Event(ts=101, cmd="git push", source="bash_history")]
            merged = merge_events(events, cfg)
            self.assertEqual(len(merged), 2)
        finally:
            import shutil

            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
