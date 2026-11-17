"""cmdwhy 命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import __version__
from . import errors as err_mod
from .analyze import analyze
from .config import Config, config_for, default_home
from .context import attach_contexts
from .demo_data import demo_events
from .env import quick_env
from .guide import COMMAND_NAMES, completion_bash, completion_zsh, guide_data, render_guide
from .hints import hint_for
from .hook import install as hook_install
from .hook import record as hook_record
from .hook import status as hook_status
from .hook import uninstall as hook_uninstall
from .knowledge import load_knowledge
from .model import Event
from .planner import build_plan
from .report import Renderer, analysis_to_dict, build_history_rows
from .resolve import resolve_targets
from .runner import cmd_run, run_command
from .safety import danger_of, safe_to_autofix
from .search import parse_time, search_events
from .sources import PARSERS, append_event, detect_format, load_events, merge_events, parse_bash
from .typo import CorpusIndex, propose_fixes
from .util import Paint, atomic_write, color_enabled, fmt_datetime, truncate, write_json


def _configure_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _extract_globals(argv):
    home = None
    flags = {"json": False, "no_color": False}
    rest = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--home" and index + 1 < len(argv):
            home = argv[index + 1]
            index += 2
            continue
        if token.startswith("--home="):
            home = token.split("=", 1)[1]
            index += 1
            continue
        if token == "--json":
            flags["json"] = True
            index += 1
            continue
        if token == "--no-color":
            flags["no_color"] = True
            index += 1
            continue
        rest.append(token)
        index += 1
    return home, rest, flags


def build_parser():
    parser = argparse.ArgumentParser(
        prog="cmdwhy",
        description="把 shell 历史还原成：在什么环境、为什么执行、哪里报错、后来怎么修好的。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "常用：\n"
            "  cmdwhy demo                        先看效果（内置 Ubuntu 数据）\n"
            "  cmdwhy ingest && cmdwhy timeline   导入历史并查看逐条注解\n"
            "  cmdwhy report                      报错 / 改变 / 添加 / 随机 四段式复盘\n"
            "  cmdwhy fix 'git stauts'            检查并纠正输入错误\n"
            "  cmdwhy hook install                让之后的命令带上退出码和错误原文\n"
            "\n所有命令：cmdwhy guide        完整参数：cmdwhy <命令> --help        文档：docs/COMMANDS.md"
        ),
    )
    parser.add_argument("--version", action="version", version="cmdwhy " + __version__)
    parser.add_argument("--home", help="数据目录（默认 ~/.local/share/cmdwhy）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("init", help="初始化数据目录与默认配置")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("demo", help="用内置 Ubuntu 示例数据演示全部能力（不读真实历史）")
    p.add_argument("--limit", type=int, default=18, help="时间线显示条数")
    p.add_argument("--random", type=int, default=1, help="随机回看的会话数")
    p.add_argument("--seed", type=int, default=None, help="随机种子（可复现）")
    p.add_argument("--sections", default="errors,changes,additions,random", help="报告分段")
    p.add_argument("--explain", default=None, help="解释指定序号（逗号分隔，如 3,18）")
    p.add_argument("--no-report", action="store_true", help="只看时间线")
    p.add_argument("--no-timeline", action="store_true", help="只看报告")
    p.add_argument("--history", action="store_true", help="按 history 样式列出编号（含重复）")
    p.add_argument("--duplicates", action="store_true", help="配合 --history，只列重复命令")
    p.add_argument("--grep", default=None, help="配合 --history，过滤命令文本")
    p.add_argument("--context", type=int, default=None, help="前后各看多少条命令，默认 20")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("ingest", help="读取历史并沉淀错误知识库")
    p.add_argument("--file", action="append", default=None, help="额外历史文件（可多次）")
    p.add_argument("--stdin", action="store_true", help="从标准输入读取 history 输出，例如 history | cmdwhy ingest --stdin")
    p.add_argument("--no-store", action="store_true", help="不读取 hook 记录")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("timeline", help="按会话展示逐条命令注解")
    p.add_argument("-n", "--limit", type=int, default=20, help="显示最近多少条")
    p.add_argument("--session", help="只看某个会话，如 S2")
    p.add_argument("-v", "--verbose", action="store_true", help="显示所有证据")
    p.set_defaults(func=cmd_timeline)

    p = sub.add_parser("explain", help="解释某条命令：为什么敲、当时环境、结果与后续")
    p.add_argument("target", nargs="*", default=["last"], help="history 编号 / #分析序号 / 区间 / last")
    p.add_argument("--context", type=int, default=None, help="前后各看多少条命令，默认 20")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("report", help="生成四段式复盘：报错 / 改变 / 添加 / 随机")
    p.add_argument("--sections", default="errors,changes,additions,random", help="逗号分隔")
    p.add_argument("--random", type=int, default=2, help="随机回看会话数")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--md", nargs="?", const="-", default=None, help="同时输出 Markdown（可给文件路径）")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("stats", help="统计错误率、意图分布、修复耗时")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("sessions", help="列出会话及每个会话的环境")
    p.set_defaults(func=cmd_sessions)

    p = sub.add_parser("summary", help="按会话总结：在做什么、错在哪、怎么修的")
    p.add_argument("--session", help="只看某个会话，如 S2")
    p.add_argument("--all", action="store_true", help="显示全部会话（默认最近 5 个）")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("changes", help="列出环境/状态变化（cd、安装、分支、服务…）")
    p.set_defaults(func=cmd_changes)

    p = sub.add_parser("additions", help="列出第一次出现的新命令")
    p.set_defaults(func=cmd_additions)

    p = sub.add_parser("history", help="像 history 一样列出带编号的命令（重复命令分别编号）")
    p.add_argument("-n", "--limit", type=int, default=50, help="显示最近多少条")
    p.add_argument("--all", action="store_true", help="显示全部")
    p.add_argument("--session", help="只看某个会话")
    p.add_argument("--grep", help="只显示包含该文本的命令")
    p.add_argument("--duplicates", action="store_true", help="只显示出现多次的命令")
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("search", help="按关键词、错误、时间、项目搜索历史")
    p.add_argument("query", nargs="*", help="关键词；多个词需要全部匹配")
    p.add_argument("--status", choices=["ok", "fail", "unknown"], help="按状态过滤")
    p.add_argument("--error", help="按错误签名/类别过滤，如 PORT:3000、PERM")
    p.add_argument("--session", help="只看某个会话，如 S2")
    p.add_argument("--project", help="按项目或 cwd 过滤")
    p.add_argument("--since", help="起始时间：7d / 24h / today / 2026-11-17")
    p.add_argument("--until", help="结束时间，格式同上")
    p.add_argument("-n", "--limit", type=int, default=30, help="最多显示多少条，0 表示全部")
    p.add_argument("--oldest", action="store_true", help="按时间正序（默认最新在前）")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("digest", help="随机回看几个会话（随机）")
    p.add_argument("--random", type=int, default=2)
    p.add_argument("--seed", type=int, default=None)
    p.set_defaults(func=cmd_digest)

    p = sub.add_parser("fix", help="检查命令输入，给出可直接执行的改正建议")
    p.add_argument("words", nargs="*", help="要检查的命令，如：git stauts")
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--last", action="store_true", help="检查上一条失败的命令")
    p.set_defaults(func=cmd_fix)

    p = sub.add_parser("diagnose", help="检索同类错误：以前怎么修好的、这次该怎么改")
    p.add_argument("--last", action="store_true", help="诊断最近一次失败")
    p.add_argument("--text", help="直接给一段错误输出")
    p.add_argument("--file", help="从文件读取错误输出")
    p.add_argument("--signature", help="按错误签名检索，如 PERM:dpkg-lock")
    p.add_argument("--fix", action="store_true", help="附带输入纠正建议")
    p.set_defaults(func=cmd_diagnose)

    p = sub.add_parser("kb", help="查看/清空/导出错误知识库")
    p.add_argument("--signature", help="只看某个签名")
    p.add_argument("--learn", action="store_true", help="重新扫描历史并学习")
    p.add_argument("--clear", action="store_true", help="清空知识库")
    p.add_argument("--export", nargs="?", const="-", help="导出 JSON（可给文件路径）")
    p.set_defaults(func=cmd_kb)

    p = sub.add_parser("hook", help="安装/卸载/查看 shell hook（记录退出码与错误）")
    p.add_argument("action", choices=["install", "uninstall", "status"])
    p.add_argument("--shell", action="append", choices=["bash", "zsh"], help="默认两个都装")
    p.add_argument("--rc", help="写入指定 rc 文件（测试用）")
    p.add_argument("--print", action="store_true", help="只打印脚本，不改文件")
    p.set_defaults(func=cmd_hook)

    p = sub.add_parser("record", help="内部命令：由 shell hook 调用，记录单条命令")
    p.add_argument("--exit", type=int, default=None)
    p.add_argument("--cmd", required=True)
    p.add_argument("--hist-id", default=None)
    p.add_argument("--cwd", default=None)
    p.add_argument("--shell", default=None)
    p.add_argument("--distro", default=None)
    p.add_argument("--stderr-file", default=None)
    p.add_argument("--stderr", default=None)
    p.add_argument("--user", default=None)
    p.add_argument("--host", default=None)
    p.add_argument("--ts", type=float, default=None)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("run", help="包装执行：捕获错误、检索同类修复、可自动改正")
    p.add_argument("--shell", action="store_true", help="经由 shell 执行，支持管道/重定向")
    p.add_argument("--fix", action="store_true", help="失败后给出改正建议")
    p.add_argument("--yes", action="store_true", help="自动执行安全的改正命令")
    p.add_argument("--retry", action="store_true", help="改正后重跑原命令")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("rest", nargs=argparse.REMAINDER, help="-- 之后的命令")
    p.set_defaults(func=cmd_run_cli)

    p = sub.add_parser("do", help="根据最近命令和环境推断下一步，可自动完成")
    p.add_argument("--yes", action="store_true", help="执行推断出的安全步骤")
    p.add_argument("--dry-run", action="store_true", help="只显示计划，不执行")
    p.add_argument("--limit", type=int, default=5, help="最多执行几步")
    p.add_argument("--from", dest="from_target", default=None, help="从指定编号开始推断（history 编号或 #分析序号）")
    p.set_defaults(func=cmd_do)

    p = sub.add_parser("mode", help="开启/关闭自动完成和自动纠错")
    p.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "off", "suggest", "auto", "autocorrect"],
    )
    p.add_argument("value", nargs="?", default=None, help="autocorrect on/off")
    p.set_defaults(func=cmd_mode)

    p = sub.add_parser("doctor", help="自检：数据目录、来源、hook、Git、命令可用性")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("guide", help="打印完整命令地图（按用途分组）")
    p.set_defaults(func=cmd_guide)

    p = sub.add_parser("version", help="显示版本、Python 和数据目录")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("analyze", help="直接分析历史文件（不改配置、不写知识库）")
    p.add_argument("files", nargs="*", help="历史文件：jsonl / bash / zsh / fish / history 输出")
    p.add_argument("--stdin", action="store_true", help="从标准输入读取，例如 history | cmdwhy analyze --stdin")
    p.add_argument("--report", action="store_true", help="输出四段式报告（默认时间线）")
    p.add_argument("--md", nargs="?", const="-", default=None, help="输出 Markdown（可给文件路径）")
    p.add_argument("-n", "--limit", type=int, default=20, help="时间线显示条数")
    p.add_argument("--sections", default="errors,changes,additions,random", help="报告分段")
    p.add_argument("--random", type=int, default=1, help="随机回看会话数")
    p.add_argument("--seed", type=int, default=None, help="随机种子")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("config", help="查看和修改配置")
    p.add_argument("--get", metavar="KEY", help="读取一个配置项")
    p.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="修改一个配置项")
    p.add_argument("--path", action="store_true", help="只打印配置文件路径")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("export", help="导出数据：json / md / timeline / report")
    p.add_argument("--format", choices=["json", "md", "timeline", "report"], default="md")
    p.add_argument("-o", "--output", default="-", help="输出文件，- 表示标准输出")
    p.add_argument("-n", "--limit", type=int, default=50, help="timeline 条数")
    p.add_argument("--sections", default="errors,changes,additions,random", help="报告分段")
    p.add_argument("--random", type=int, default=2, help="随机回看会话数")
    p.add_argument("--seed", type=int, default=None, help="随机种子")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("completion", help="生成或安装 bash/zsh 补全")
    p.add_argument("shell", choices=["bash", "zsh"])
    p.add_argument("--install", action="store_true", help="写入当前用户的补全目录")
    p.set_defaults(func=cmd_completion)

    _decorate(sub)
    return parser


HELP_DESCRIPTIONS = {
    "init": "创建默认数据目录（~/.local/share/cmdwhy）和 config.json，打印路径与下一步。",
    "demo": "使用内置的一段 Ubuntu 日常数据演示环境推断、动机、报错、修复链和输入纠错，不读取或修改你的真实历史。",
    "ingest": "解析配置里的历史文件（bash / zsh / fish / JSONL），分析修复链，并把验证过的修法写入错误知识库。",
    "analyze": "直接分析指定历史文件，不登记来源、不写知识库，适合临时查看别人的历史或导出的日志。",
    "timeline": "按会话展示每条命令：环境、意图、动机、报错、修复链、输入更正。",
    "explain": "完整解释一条或一段命令：时间、环境、结果、置信度、意图、动机、任务上下文、本条目的、依据、建议与后续。数字优先按 history 编号解析。",
    "report": "生成四段式复盘：一、报错与修复；二、环境/状态改变；三、第一次出现的命令；四、随机回看会话。",
    "stats": "统计命令数、会话数、错误率、修复链与平均修复耗时、意图分布、常用命令、高频错误。",
    "sessions": "列出所有会话的起止时间、环境、命令数、报错数和修复动作数。",
    "changes": "列出会改变环境/状态的命令：cd、安装、创建目录、改权限、切分支、重启服务、结束进程。",
    "summary": "按会话总结：任务、报错、修复动作、验证状态和环境改变。适合快速回顾“这次会话到底做了什么”。",
    "additions": "列出第一次出现的命令，适合回顾新项目/新环境里引入的工具。",
    "history": "像 shell 内建 history 一样列出带编号的命令。重复命令会显示“第 k/n 次”，每个编号对应一次具体执行，可直接 cmdwhy explain <编号>。",
    "search": "按关键词、错误签名、状态、时间、项目和会话搜索历史命令，结果保留 history 编号，可以直接 explain。",
    "digest": "随机抽取几个会话做回顾，默认输出意图、报错和修复动作。",
    "fix": "检查命令输入：在 PATH、合法子命令和你成功用过的历史里找最像的命令，给出可直接执行的修正。",
    "diagnose": "检索同类错误：按错误签名或原文相似度，给出你以前验证有效的修法，以及 Ubuntu 通用处置建议。",
    "kb": "查看、检索、导出或清空本地错误知识库（错误签名 -> 修复步骤）。",
    "hook": "安装/卸载/查看 bash、zsh hook。hook 会把退出码、cwd、发行版写入事件文件，让之后的注解置信度更高。",
    "record": "内部命令：由 shell hook 调用，记录单条命令。一般不需要手动执行。",
    "run": "包装执行命令：捕获 stdout/stderr、记录退出码；失败后即时诊断，可自动执行安全的修正。",
    "doctor": "自检：Python 版本、数据目录可写性、历史来源、hook 安装状态、Git、command-not-found、知识库。",
    "guide": "按用途分组打印全部命令，适合第一次使用或忘记命令时查看。",
    "version": "显示 cmdwhy 版本、Python 版本、数据目录、历史来源数量和知识库路径。",
    "config": "查看配置，或读取/修改单个配置项（sources、idle_gap、window、redact、learn、color、max_events、ignore_prefixes）。",
    "export": "把分析结果导出为 JSON、Markdown、时间线或报告，-o - 表示输出到标准输出。",
    "completion": "生成 bash/zsh 补全脚本；--install 会写入当前用户的补全目录。",
}

HELP_EXAMPLES = {
    "demo": "  cmdwhy demo\n  cmdwhy demo --no-timeline --sections errors\n  cmdwhy demo --explain 18",
    "ingest": "  cmdwhy ingest\n  cmdwhy ingest --file ~/.bash_history\n  history | cmdwhy ingest --stdin",
    "analyze": "  cmdwhy analyze examples/demo_history_output.txt\n  cmdwhy analyze ~/.zsh_history --report\n  history | cmdwhy analyze --stdin",
    "timeline": "  cmdwhy timeline\n  cmdwhy timeline -n 50 --verbose\n  cmdwhy timeline --session S2",
    "explain": "  cmdwhy explain last\n  cmdwhy explain 518            # history 输出里的编号\n  cmdwhy explain '#18'          # 分析序号\n  cmdwhy explain 518 --context 40",
    "report": "  cmdwhy report\n  cmdwhy report --sections errors,changes\n  cmdwhy report --md report.md",
    "stats": "  cmdwhy stats\n  cmdwhy stats --json",
    "changes": "  cmdwhy changes",
    "summary": "  cmdwhy summary\n  cmdwhy summary --session S2\n  cmdwhy summary --all",
    "additions": "  cmdwhy additions",
    "history": "  cmdwhy history\n  cmdwhy history -n 100\n  cmdwhy history --duplicates\n  cmdwhy history --grep status",
    "search": "  cmdwhy search flask\n  cmdwhy search --error PORT --since 7d\n  cmdwhy search --status fail --project api\n  cmdwhy search --json",
    "digest": "  cmdwhy digest --random 2 --seed 7",
    "fix": "  cmdwhy fix 'git stauts'\n  cmdwhy fix 'gti status'\n  cmdwhy fix --last",
    "diagnose": "  cmdwhy diagnose\n  cmdwhy diagnose --text 'error: externally-managed-environment'\n  cmdwhy diagnose --signature PERM:dpkg-lock --fix",
    "kb": "  cmdwhy kb\n  cmdwhy kb --signature PORT:3000\n  cmdwhy kb --learn\n  cmdwhy kb --export kb.json",
    "hook": "  cmdwhy hook install\n  cmdwhy hook status\n  cmdwhy hook install --print --shell bash",
    "run": "  cmdwhy run -- npm run dev\n  cmdwhy run --fix -- python3 app.py\n  cw run --fix --yes -- git stauts",
    "doctor": "  cmdwhy doctor",
    "guide": "  cmdwhy guide\n  cmdwhy guide --json",
    "config": "  cmdwhy config\n  cmdwhy config --get idle_gap\n  cmdwhy config --set idle_gap 600\n  cmdwhy config --set sources ~/.bash_history,~/.zsh_history",
    "export": "  cmdwhy export --format md -o report.md\n  cmdwhy export --format json -o history.json\n  cmdwhy export --format timeline -n 100",
    "completion": "  cmdwhy completion bash\n  cmdwhy completion bash --install\n  cmdwhy completion zsh --install",
}


def _decorate(subparsers):
    for name, child in subparsers.choices.items():
        child.formatter_class = argparse.RawDescriptionHelpFormatter
        if name in HELP_DESCRIPTIONS:
            child.description = HELP_DESCRIPTIONS[name]
        if name in HELP_EXAMPLES:
            child.epilog = "示例：\n" + HELP_EXAMPLES[name]


def _cfg(home, ensure=True):
    cfg = config_for(home) if ensure else Config(home=home or default_home())
    return cfg


def _renderer(args, cfg):
    enabled = color_enabled() and not getattr(args, "no_color", False)
    if getattr(cfg, "color", "auto") == "never":
        enabled = False
    elif getattr(cfg, "color", "auto") == "always":
        enabled = True
    return Renderer(Paint(enabled), home=os.path.expanduser("~"))


def _analysis(cfg, files=None, use_store=True, with_context=False):
    events, meta = load_events(cfg, extra_paths=files, use_store=use_store)
    return analyze(events, cfg, meta, with_context=with_context), meta


def _print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


# ------------------------------------------------------------------ 命令实现

def cmd_init(args, cfg, renderer):
    cfg.ensure()
    print("数据目录  " + cfg.home)
    print("配置文件  " + cfg.config_path)
    print("事件记录  " + cfg.store_path)
    print("知识库    " + cfg.knowledge_path)
    if cfg.sources:
        print("历史来源")
        for path in cfg.sources:
            print("  - " + path)
    else:
        print("没有自动发现历史文件；用 cmdwhy ingest --file <路径> 指定。")
    print("")
    print("下一步： cmdwhy ingest && cmdwhy timeline")
    return 0


def cmd_demo(args, cfg, renderer):
    cfg = Config(home=cfg.home)
    events = merge_events(demo_events(), cfg)
    analysis = analyze(events, cfg, {"files": ["内置示例数据"], "warnings": []})
    renderer = Renderer(renderer.p, home="/home/ubuntu")
    if args.context:
        attach_contexts(analysis, max(1, args.context))
    if args.json:
        _print_json(analysis_to_dict(analysis))
        return 0
    print(renderer.p("【演示数据】一段 Ubuntu 开发日常：flask 缺失、PEP 668、拼写错误、端口占用、Docker 权限、Git 推送被拒。", "yellow"))
    print("")
    if args.history:
        print(
            renderer.render_history_list(
                analysis,
                limit=args.limit,
                grep=args.grep,
                duplicates=args.duplicates,
                show_all=args.duplicates,
            )
        )
        return 0
    if args.explain:
        targets = [part.strip() for part in args.explain.split(",") if part.strip()]
        seqs, notes = resolve_targets(analysis, targets)
        for note in notes:
            print(renderer.p("提示：" + note, "yellow"))
        if not seqs:
            print("没有找到要解释的命令。可写 518（history 编号）或 #18（分析序号）。")
            return 1
        print(renderer.render_explain(analysis, seqs))
        return 0
    if not args.no_timeline:
        print(renderer.render_timeline(analysis, limit=args.limit))
        if not args.no_report:
            print("")
    if not args.no_report:
        print(renderer.render_report(analysis, sections=_sections(args.sections), random_n=args.random, seed=args.seed))
    return 0


def cmd_ingest(args, cfg, renderer):
    if args.stdin:
        text = sys.stdin.read()
        if not text.strip():
            print("标准输入为空。用法：history | cmdwhy ingest --stdin")
            return 1
        fmt = detect_format("stdin", text)
        parser = PARSERS.get(fmt, parse_bash)
        imported = parser(text, source="stdin")
        for event in imported:
            append_event(cfg, event)
        print("从标准输入导入 %d 条命令（%s 格式）" % (len(imported), fmt))
    if args.file:
        registered = list(cfg.sources)
        for path in cfg.expand_sources(args.file):
            absolute = os.path.abspath(path)
            if absolute not in registered:
                registered.append(absolute)
        cfg.sources = registered
        cfg.sources_configured = True
        cfg.save()
    analysis, meta = _analysis(cfg, files=args.file, use_store=not args.no_store)
    if args.json:
        _print_json(analysis_to_dict(analysis))
        return 0
    if not analysis.events:
        print("没有读到命令。先确认历史文件存在，或用 cmdwhy demo 看效果。")
        return 1
    history_ids = sum(1 for event in analysis.events if event.hist_id is not None)
    suffix = "（其中 %d 条带 history 编号）" % history_ids if history_ids else ""
    print("读取 %d 个来源 · %d 条命令%s" % (len(meta.get("files", [])), len(analysis.events), suffix))
    for path in meta.get("files", []):
        print("  - " + path)
    stats = analysis.stats
    print(
        "识别 %d 个会话 · 失败 %d 条（确认 %d / 推测 %d）· 修复链 %d 条"
        % (stats["sessions"], stats["fail"] + stats["suspected"], stats["fail"], stats["suspected"], stats["chains"])
    )
    knowledge = load_knowledge(cfg)
    if cfg.learn:
        learned = knowledge.learn(analysis)
        summary = knowledge.summary()
        print(
            "知识库：本次沉淀 %d 条修复记录 · 共 %d 个错误签名 / %d 次验证有效"
            % (learned, summary["signatures"], summary["verified_fixes"])
        )
    else:
        print("知识库：配置 learn=false，本次跳过学习。")
    print("")
    print("下一步： cmdwhy timeline   逐条看注解")
    print("        cmdwhy report     看报错/改变/添加/随机复盘")
    print("        cmdwhy hook install   让新命令带上退出码和错误原文")
    return 0


def cmd_timeline(args, cfg, renderer):
    analysis, meta = _analysis(cfg, with_context=args.verbose)
    if args.json:
        _print_json(analysis_to_dict(analysis))
        return 0
    if not analysis.events:
        print("没有命令记录。先运行 cmdwhy ingest，或 cmdwhy demo 看效果。")
        return 1
    print(renderer.render_timeline(analysis, limit=args.limit, sid=args.session, verbose=args.verbose))
    return 0


def cmd_explain(args, cfg, renderer):
    analysis, meta = _analysis(cfg)
    if not analysis.events:
        print("没有命令记录。先运行 cmdwhy ingest，或 cmdwhy demo 看效果。")
        return 1
    seqs, notes = resolve_targets(analysis, args.target or ["last"])
    if seqs:
        attach_contexts(analysis, args.context or cfg.context_window, seqs=seqs)
    if not seqs:
        print("没有找到要解释的命令。")
        for note in notes:
            print("  " + note)
        print("用法：cmdwhy explain 518（history 编号）/ #18（分析序号）/ 518-520 / last")
        return 1
    if args.json:
        payload = []
        for seq in seqs:
            item = analysis.ann(seq).to_dict()
            item["hist_id"] = analysis.event(seq).hist_id
            item["cmd"] = analysis.event(seq).cmd
            payload.append(item)
        _print_json(payload)
        return 0
    for note in notes:
        print(renderer.p("提示：" + note, "yellow"))
    print(renderer.render_explain(analysis, seqs))
    return 0


def _sections(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def cmd_report(args, cfg, renderer):
    analysis, meta = _analysis(cfg)
    if args.json:
        _print_json(analysis_to_dict(analysis))
        return 0
    if not analysis.events:
        print("没有命令记录。先运行 cmdwhy ingest，或 cmdwhy demo 看效果。")
        return 1
    sections = _sections(args.sections)
    print(renderer.render_report(analysis, sections=sections, random_n=args.random, seed=args.seed))
    if args.md:
        markdown = renderer.render_markdown(analysis, sections=sections, random_n=args.random, seed=args.seed)
        target = args.md
        if target == "-":
            print("")
            print(markdown)
        else:
            try:
                with open(target, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(markdown + "\n")
            except OSError as exc:
                print("写入失败：%s" % exc, file=sys.stderr)
                return 1
            print("")
            print("Markdown 已写入 " + target)
    return 0


def cmd_stats(args, cfg, renderer):
    analysis, meta = _analysis(cfg)
    if args.json:
        _print_json(analysis.stats)
        return 0
    if not analysis.events:
        print("没有命令记录。")
        return 1
    print(renderer.render_stats(analysis))
    return 0


def cmd_sessions(args, cfg, renderer):
    analysis, meta = _analysis(cfg)
    if args.json:
        _print_json([{"sid": s.sid, "start": s.start_ts, "end": s.end_ts, "n": s.n, "cwd": s.cwd} for s in analysis.sessions])
        return 0
    if not analysis.events:
        print("没有命令记录。")
        return 1
    print(renderer.render_sessions(analysis))
    return 0


def cmd_summary(args, cfg, renderer):
    analysis, meta = _analysis(cfg, with_context=True)
    if not analysis.events:
        print("没有命令记录。")
        return 1
    sessions = analysis.sessions
    if args.session:
        sessions = [session for session in sessions if session.sid == args.session]
        if not sessions:
            print("没有找到会话 %s。" % args.session)
            return 1
    elif not args.all:
        sessions = sessions[-5:]
    if args.json:
        payload = []
        for session in sessions:
            fails = [
                analysis.ann(event.seq)
                for event in session.events
                if analysis.ann(event.seq).status in ("fail", "suspected")
            ]
            tasks = []
            fixes = []
            for event in session.events:
                task = analysis.ann(event.seq).task
                if task and task not in tasks:
                    tasks.append(task)
                for step in analysis.ann(event.seq).steps:
                    if step not in fixes:
                        fixes.append(step)
            payload.append(
                {
                    "sid": session.sid,
                    "start_ts": session.start_ts,
                    "end_ts": session.end_ts,
                    "events": session.n,
                    "failures": len(fails),
                    "tasks": tasks,
                    "errors": [
                        ann.error.signature for ann in fails if ann.error is not None
                    ],
                    "fixes": fixes,
                    "env": session.env.to_dict() if session.env is not None else None,
                }
            )
        _print_json(payload)
        return 0
    print(renderer.render_summary(analysis, sessions))
    return 0


def cmd_changes(args, cfg, renderer):
    analysis, meta = _analysis(cfg)
    if args.json:
        _print_json([analysis.ann(ev.seq).to_dict() for ev in analysis.events if analysis.ann(ev.seq).changes])
        return 0
    print(renderer.render_changes(analysis))
    return 0


def cmd_additions(args, cfg, renderer):
    analysis, meta = _analysis(cfg)
    if args.json:
        _print_json([analysis.ann(ev.seq).to_dict() for ev in analysis.events if analysis.ann(ev.seq).novelty])
        return 0
    print(renderer.render_additions(analysis))
    return 0


def cmd_history(args, cfg, renderer):
    analysis, meta = _analysis(cfg)
    if args.json:
        rows, totals = build_history_rows(
            analysis, sid=args.session, grep=args.grep, duplicates=args.duplicates
        )
        _print_json({"total": sum(totals.values()), "rows": rows})
        return 0
    if not analysis.events:
        print("没有命令记录。先运行 cmdwhy ingest，或 cmdwhy demo 看效果。")
        return 1
    print(
        renderer.render_history_list(
            analysis,
            limit=args.limit,
            sid=args.session,
            grep=args.grep,
            duplicates=args.duplicates,
            show_all=args.all or args.duplicates,
        )
    )
    return 0


def cmd_search(args, cfg, renderer):
    analysis, meta = _analysis(cfg, with_context=True)
    try:
        since_ts = parse_time(args.since)
        until_ts = parse_time(args.until)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    query = " ".join(args.query).strip()
    results, total = search_events(
        analysis,
        query=query,
        status=args.status,
        error=args.error,
        since_ts=since_ts,
        until_ts=until_ts,
        session=args.session,
        project=args.project,
        limit=args.limit,
        oldest=args.oldest,
    )
    if args.json:
        _print_json([result.to_dict() for result in results])
        return 0
    filters = []
    if args.status:
        filters.append("状态=" + args.status)
    if args.error:
        filters.append("错误~" + args.error)
    if args.session:
        filters.append("会话=" + args.session)
    if args.project:
        filters.append("项目=" + args.project)
    if args.since:
        filters.append("从 " + args.since)
    if args.until:
        filters.append("到 " + args.until)
    print(renderer.render_search(analysis, results, total=total, query=query, filters=filters))
    return 0 if results else 1


def cmd_digest(args, cfg, renderer):
    analysis, meta = _analysis(cfg)
    if args.json:
        _print_json([{"sid": s.sid, "n": s.n} for s in analysis.sessions])
        return 0
    if not analysis.events:
        print("没有命令记录。")
        return 1
    print(renderer.render_digest(analysis, n=args.random, seed=args.seed))
    return 0


def _last_failure(analysis):
    for ann in reversed(analysis.anns):
        if ann.status in ("fail", "suspected") and ann.error is not None:
            return ann
    return None


def cmd_fix(args, cfg, renderer):
    analysis, meta = _analysis(cfg)
    if not args.words and not args.last:
        print("用法：cmdwhy fix <命令> 或 cmdwhy fix --last", file=sys.stderr)
        return 2
    cmd_text = " ".join(args.words)
    error = None
    if args.last:
        ann = _last_failure(analysis)
        if ann is None:
            print("历史里还没有失败的命令可以检查。")
            return 1
        cmd_text = analysis.event(ann.seq).cmd
        error = ann.error
    index = CorpusIndex(analysis.events)
    fixes = propose_fixes(cmd_text, index=index, error=error, limit=args.top)
    if args.json:
        _print_json({"command": cmd_text, "fixes": [fix.to_dict() for fix in fixes]})
        return 0
    print(renderer.render_fixes(cmd_text, fixes))
    return 0 if fixes else 1


def cmd_diagnose(args, cfg, renderer):
    analysis, meta = _analysis(cfg)
    knowledge = load_knowledge(cfg)
    signature = None
    category = None
    occurrences = 0
    fixes = None
    source_label = None
    text = args.text
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print("读取失败：%s" % exc, file=sys.stderr)
            return 1
    if text:
        error = err_mod.classify_text(text)
        signature = error.signature
        category = error.category
        occurrences = knowledge.occurrences(signature)
        source_label = "来自你提供的错误输出"
        if args.fix:
            fixes = propose_fixes(error.missing_word or "", CorpusIndex(analysis.events), error)
    elif args.signature:
        signature = args.signature
        category = signature.split(":", 1)[0]
        occurrences = knowledge.occurrences(signature)
        source_label = "按签名检索"
    else:
        ann = _last_failure(analysis)
        if ann is None:
            print("没有找到失败记录。用 --text 直接给一段错误输出，或用 --signature 指定签名。")
            return 1
        signature = ann.error.signature
        category = ann.error.category
        occurrences = knowledge.occurrences(signature)
        source_label = "最近一次失败 #%d %s" % (ann.seq, analysis.event(ann.seq).cmd)
        if args.fix:
            fixes = propose_fixes(analysis.event(ann.seq).cmd, CorpusIndex(analysis.events), ann.error)
    remedies = knowledge.lookup(signature, category)
    if not remedies and text:
        remedies = knowledge.lookup_text(text, category)
    if args.json:
        _print_json(
            {
                "signature": signature,
                "category": category,
                "occurrences": occurrences,
                "hint": hint_for(category),
                "remedies": [remedy.to_dict() for remedy in remedies],
                "fixes": [fix.to_dict() for fix in fixes] if fixes else [],
            }
        )
        return 0
    print(renderer.render_diagnosis(signature, category, occurrences, remedies, fixes=fixes, source=source_label))
    return 0


def cmd_kb(args, cfg, renderer):
    knowledge = load_knowledge(cfg)
    if args.clear:
        knowledge.clear()
        print("知识库已清空。")
        return 0
    if args.learn:
        analysis, meta = _analysis(cfg)
        learned = knowledge.learn(analysis)
        print("扫描 %d 条命令，沉淀 %d 条修复记录。" % (len(analysis.events), learned))
        knowledge = load_knowledge(cfg)
    if args.export:
        data = knowledge.export()
        if args.export == "-":
            _print_json(data)
        else:
            write_json(args.export, data)
            print("已导出到 " + args.export)
        return 0
    if args.signature:
        remedies = knowledge.lookup(args.signature, args.signature.split(":", 1)[0])
        if args.json:
            _print_json([remedy.to_dict() for remedy in remedies])
            return 0
        if not remedies:
            print("签名 %s 还没有沉淀修复记录。" % args.signature)
            return 1
        print(renderer.render_diagnosis(args.signature, args.signature.split(":", 1)[0], knowledge.occurrences(args.signature), remedies))
        return 0
    if args.json:
        _print_json(knowledge.export())
        return 0
    print(renderer.render_kb(knowledge))
    return 0


def cmd_hook(args, cfg, renderer):
    shells = tuple(args.shell) if args.shell else ("bash", "zsh")
    if args.action == "install":
        messages = hook_install(cfg, shells=shells, rc_override=args.rc, print_only=args.print)
        print("\n".join(messages))
        return 0
    if args.action == "uninstall":
        print("\n".join(hook_uninstall(cfg, shells=shells, rc_override=args.rc)))
        return 0
    info = hook_status(cfg, shells=shells, rc_override=args.rc)
    if args.json:
        _print_json(info)
        return 0
    print("数据目录    " + info["home"])
    print("事件记录    " + info["store"] + ("（%d 条）" % info["events"] if info["store_exists"] else "（还不存在）"))
    print("cmdwhy 路径 " + (info["cmd_in_path"] or "未在 PATH 中（会用 python -m cmdwhy）"))
    for item in info["shells"]:
        mark = "已安装" if item["installed"] else "未安装"
        print("%-9s %s → %s" % (item["shell"], mark, item["rc"]))
    print("")
    print("安装： cmdwhy hook install    只打印脚本： cmdwhy hook install --print")
    return 0


def cmd_record(args, cfg, renderer):
    try:
        hook_record(cfg, args)
    except Exception:
        return 0
    return 0


def cmd_run_cli(args, cfg, renderer):
    rest = list(args.rest)
    if rest and rest[0] == "--":
        rest = rest[1:]
    if not rest:
        print("用法：cw run [--shell] [--fix] [--yes] [--retry] -- <命令>", file=sys.stderr)
        return 2
    return cmd_run(
        cfg, rest, fix=args.fix, yes=args.yes, retry=args.retry, quiet=args.quiet, shell=args.shell
    )


def cmd_do(args, cfg, renderer):
    if cfg.autopilot == "off" and not args.dry_run:
        print("自动完成已关闭。先运行：cmdwhy mode suggest")
        return 1
    analysis, meta = _analysis(cfg, with_context=True)
    knowledge = load_knowledge(cfg)
    focus = None
    if args.from_target:
        seqs, notes = resolve_targets(analysis, [args.from_target])
        if not seqs:
            print("没有找到要作为起点的命令。")
            for note in notes:
                print("  " + note)
            return 2
        focus = seqs[0]
    plan = build_plan(analysis, knowledge, limit=max(1, min(10, args.limit)), focus_seq=focus)
    print(renderer.render_plan(analysis, plan, mode=cfg.autopilot))
    execute = not args.dry_run and (args.yes or cfg.autopilot == "auto")
    if not execute:
        return 0
    runnable = [
        action
        for action in plan.actions
        if action.executable and action.risk != "high" and safe_to_autofix(action.command)
    ]
    if not runnable:
        print("")
        print("没有可自动执行的安全步骤，请手动确认。")
        return 0
    env = quick_env(os.getcwd())
    executed = 0
    for action in runnable:
        print("")
        print(renderer.p("▶ " + action.command, "bold"))
        code, stderr, duration, started = run_command(action.command)
        event = Event(
            ts=started,
            cmd=action.command,
            exit_code=code,
            cwd=os.getcwd(),
            user=env.user,
            host=env.host,
            distro=env.distro,
            shell=env.shell,
            duration_ms=int(duration * 1000),
            stderr=stderr[-4000:] if stderr else None,
            source="autopilot",
        )
        append_event(cfg, event)
        executed += 1
        if code != 0:
            print(renderer.p("停止：这一步失败（退出码 %d）。" % code, "red"), file=sys.stderr)
            return code
    print("")
    print(renderer.p("已自动完成 %d 步，结果已记录到 cmdwhy。" % executed, "green"))
    return 0


def cmd_mode(args, cfg, renderer):
    action = args.action or "status"
    if action == "status":
        print("autopilot    " + cfg.autopilot + "  （off / suggest / auto）")
        print("autocorrect  " + ("on" if cfg.autocorrect else "off"))
        print("")
        print("自动完成： cmdwhy mode suggest | auto | off")
        print("自动纠错： cmdwhy mode autocorrect on | off")
        print("查看计划： cmdwhy do --dry-run")
        return 0
    if action == "autocorrect":
        value = (args.value or "").lower()
        if value not in ("on", "off", "true", "false", "1", "0"):
            print("用法：cmdwhy mode autocorrect on|off", file=sys.stderr)
            return 2
        cfg.autocorrect = value in ("on", "true", "1")
        cfg.save()
        print("autocorrect 已" + ("开启" if cfg.autocorrect else "关闭"))
        return 0
    if action in ("off", "suggest", "auto"):
        cfg.autopilot = action
        cfg.save()
        print("autopilot = " + action)
        if action == "auto":
            print("低/中风险步骤会被自动执行；可用 --dry-run 先看计划。")
        return 0
    print("用法：cmdwhy mode [status|off|suggest|auto|autocorrect on|off]", file=sys.stderr)
    return 2


def cmd_doctor(args, cfg, renderer):
    import shutil

    p = renderer.p
    lines = [p.bold("cmdwhy 自检")]
    lines.append("")
    lines.append("  Python      %s（需要 3.8+）" % sys.version.split()[0])
    lines.append("  数据目录    %s" % cfg.home)
    writable = os.access(cfg.home, os.W_OK)
    lines.append("  可写        %s" % ("是" if writable else p("否——请检查权限", "red")))
    if os.path.exists(cfg.store_path):
        events, meta = load_events(cfg)
        captured = meta.get("captured", 0)
        lines.append("  事件记录    %d 条（其中 %d 条带退出码/错误，注解置信度高）" % (len(events), captured))
        if events:
            lines.append("  最近事件    %s %s" % (fmt_datetime(events[-1].ts), truncate(events[-1].cmd, 50)))
    else:
        lines.append("  事件记录    还没有；安装 hook 后自动积累")
    sources = cfg.expand_sources()
    if sources:
        lines.append("  历史来源    %d 个" % len(sources))
        for path in sources:
            lines.append("              " + path)
    else:
        lines.append("  历史来源    " + p("没有找到 bash/zsh/fish 历史", "yellow"))
    info = hook_status(cfg)
    for item in info["shells"]:
        lines.append("  %-10s %s" % (item["shell"] + " hook", "已安装" if item["installed"] else "未安装"))
    lines.append("  Git         %s" % (shutil.which("git") or "未安装（无法推断分支）"))
    lines.append("  command-not-found  %s" % (shutil.which("command-not-found") or "未安装（apt 包名提示会弱一些）"))
    knowledge = load_knowledge(cfg)
    summary = knowledge.summary()
    lines.append("  知识库      %d 个签名 / %d 次验证有效" % (summary["signatures"], summary["verified_fixes"]))
    danger, why = danger_of("sudo rm -rf /")
    lines.append("  安全策略    危险命令识别 %s（示例：%s）" % ("正常" if danger else "异常", why or "-"))
    lines.append("")
    lines.append("  建议")
    if not info["shells"][0]["installed"] and not info["shells"][1]["installed"]:
        lines.append("    - 运行 cmdwhy hook install，让新命令带上退出码与工作目录")
    if not sources:
        lines.append("    - 用 cmdwhy ingest --file ~/.bash_history 指定历史文件")
    lines.append("    - 想立刻体验：cmdwhy demo")
    print("\n".join(lines))
    return 0


def main(argv=None):
    _configure_stdio()
    raw = list(sys.argv[1:] if argv is None else argv)
    home, rest, flags = _extract_globals(raw)
    parser = build_parser()
    args = parser.parse_args(rest)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    args.json = bool(flags.get("json") or getattr(args, "json", False))
    args.no_color = bool(flags.get("no_color") or getattr(args, "no_color", False))
    args.home = home or getattr(args, "home", None)
    ensure = getattr(args, "command", "") not in ("demo",)
    cfg = _cfg(args.home, ensure=ensure)
    renderer = _renderer(args, cfg)
    try:
        return args.func(args, cfg, renderer)
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 130


def cmd_guide(args, cfg, renderer):
    if args.json:
        _print_json(guide_data())
        return 0
    print(render_guide(renderer.p))
    return 0


def cmd_version(args, cfg, renderer):
    print("cmdwhy " + __version__)
    print("Python " + sys.version.split()[0])
    print("数据目录 " + cfg.home)
    print("历史来源 " + str(len(cfg.sources)) + " 个")
    print("知识库 " + cfg.knowledge_path)
    return 0


def _stdin_events(cfg, source="stdin"):
    text = sys.stdin.read()
    if not text.strip():
        return [], "空"
    fmt = detect_format("stdin", text)
    parser = PARSERS.get(fmt, parse_bash)
    events = parser(text, source=source)
    return merge_events(events, cfg), fmt


def cmd_analyze(args, cfg, renderer):
    if not args.files and not args.stdin:
        print("用法：cmdwhy analyze <文件...> 或 cmdwhy analyze --stdin", file=sys.stderr)
        return 2
    if args.stdin or args.files == ["-"]:
        events, fmt = _stdin_events(cfg)
        meta = {"files": ["stdin（%s）" % fmt], "warnings": []}
        analysis = analyze(events, cfg, meta)
    else:
        events, meta = load_events(cfg, extra_paths=args.files, use_store=False)
        analysis = analyze(events, cfg, meta, with_context=False)
    if args.json:
        _print_json(analysis_to_dict(analysis))
        return 0
    if not analysis.events:
        print("没有读到命令。支持 bash / zsh / fish 历史和 cmdwhy JSONL。")
        return 1
    if args.md is not None:
        text = renderer.render_markdown(
            analysis, sections=_sections(args.sections), random_n=args.random, seed=args.seed
        )
        if args.md == "-":
            print(text)
        else:
            atomic_write(args.md, text + "\n")
            print("Markdown 已写入 " + args.md)
        return 0
    if args.report:
        print(
            renderer.render_report(
                analysis, sections=_sections(args.sections), random_n=args.random, seed=args.seed
            )
        )
    else:
        print(renderer.render_timeline(analysis, limit=args.limit))
    return 0


CONFIG_KEYS = (
    "sources",
    "idle_gap",
    "window",
    "context_window",
    "redact",
    "learn",
    "autopilot",
    "autocorrect",
    "color",
    "max_events",
    "ignore_prefixes",
)


def _parse_config_value(key, raw):
    if key in ("idle_gap", "window", "context_window", "max_events"):
        value = int(raw)
        if value <= 0:
            raise ValueError("必须是正整数")
        return value
    if key in ("redact", "learn", "autocorrect"):
        return str(raw).lower() in ("1", "true", "yes", "on")
    if key == "autopilot":
        if raw not in ("off", "suggest", "auto"):
            raise ValueError("只能是 off / suggest / auto")
        return raw
    if key in ("sources", "ignore_prefixes"):
        return [part.strip() for part in str(raw).split(",") if part.strip()]
    if key == "color":
        if raw not in ("auto", "always", "never"):
            raise ValueError("只能是 auto / always / never")
        return raw
    raise ValueError("未知配置项")


def cmd_config(args, cfg, renderer):
    if args.path:
        print(cfg.config_path)
        return 0
    if args.get:
        key = args.get
        if key not in CONFIG_KEYS:
            print("未知配置项：%s\n可用：%s" % (key, "、".join(CONFIG_KEYS)), file=sys.stderr)
            return 2
        value = getattr(cfg, key)
        if args.json:
            _print_json({key: value})
        else:
            print(json.dumps(value, ensure_ascii=False))
        return 0
    if args.set:
        key, raw = args.set
        if key not in CONFIG_KEYS:
            print("未知配置项：%s\n可用：%s" % (key, "、".join(CONFIG_KEYS)), file=sys.stderr)
            return 2
        try:
            value = _parse_config_value(key, raw)
        except ValueError as exc:
            print("无效值：%s" % exc, file=sys.stderr)
            return 2
        setattr(cfg, key, value)
        if key == "sources":
            cfg.sources_configured = True
        cfg.save()
        print("已更新 %s = %s" % (key, json.dumps(value, ensure_ascii=False)))
        print("配置文件 " + cfg.config_path)
        return 0
    if args.json:
        _print_json(cfg.to_dict())
        return 0
    print("配置文件  " + cfg.config_path)
    print("数据目录  " + cfg.home)
    for key in CONFIG_KEYS:
        print("  %-16s %s" % (key, json.dumps(getattr(cfg, key), ensure_ascii=False)))
    print("")
    print("修改：cmdwhy config --set idle_gap 600")
    return 0


def cmd_export(args, cfg, renderer):
    analysis, meta = _analysis(cfg, with_context=args.format == "json")
    if not analysis.events:
        print("没有命令记录。先运行 cmdwhy ingest，或 cmdwhy demo 看效果。")
        return 1
    if args.format == "json":
        text = json.dumps(analysis_to_dict(analysis), ensure_ascii=False, indent=2, default=str)
    elif args.format == "timeline":
        text = renderer.render_timeline(analysis, limit=args.limit)
    elif args.format == "report":
        text = renderer.render_report(
            analysis, sections=_sections(args.sections), random_n=args.random, seed=args.seed
        )
    else:
        text = renderer.render_markdown(
            analysis, sections=_sections(args.sections), random_n=args.random, seed=args.seed
        )
    if args.output and args.output != "-":
        atomic_write(args.output, text + "\n")
        print("已导出 %s（%d 字节，格式 %s）" % (args.output, len(text.encode("utf-8")), args.format))
    else:
        print(text)
    return 0


def cmd_completion(args, cfg, renderer):
    script = completion_bash() if args.shell == "bash" else completion_zsh()
    if not args.install:
        print(script, end="" if script.endswith("\n") else "\n")
        return 0
    home = os.path.expanduser("~")
    if args.shell == "bash":
        path = os.path.join(home, ".local", "share", "bash-completion", "completions", "cmdwhy")
    else:
        path = os.path.join(home, ".zfunc", "_cmdwhy")
    atomic_write(path, script)
    print("已写入 " + path)
    if args.shell == "bash":
        print("重新打开终端即可生效（需要 bash-completion：sudo apt install bash-completion）。")
    else:
        print("确保 ~/.zshrc 里包含： fpath=(~/.zfunc $fpath)  并且已执行 compinit。")
    return 0


def cw_main(argv=None):
    """cw 包装器：cw run -- <命令>，或直接 cw -- <命令>。"""
    _configure_stdio()
    raw = list(sys.argv[1:] if argv is None else argv)
    fix = False
    yes = False
    retry = False
    quiet = False
    shell = False
    rest = []
    index = 0
    while index < len(raw):
        token = raw[index]
        if token == "run" and not rest:
            index += 1
            continue
        if token == "--fix":
            fix = True
        elif token == "--yes":
            yes = True
        elif token == "--retry":
            retry = True
        elif token == "--quiet":
            quiet = True
        elif token == "--shell":
            shell = True
        elif token in ("-h", "--help"):
            print("用法：cw run [--shell] [--fix] [--yes] [--retry] -- <命令>")
            print("示例：cw run --shell -- 'npm run dev | tee dev.log'")
            print("      cw run --fix --yes -- git stauts")
            return 0
        else:
            rest.append(token)
        index += 1
    home, rest, flags = _extract_globals(rest)
    if rest and rest[0] == "--":
        rest = rest[1:]
    if not rest:
        print("用法：cw run [--fix] [--yes] [--retry] -- <命令>", file=sys.stderr)
        return 2
    cfg = config_for(home).ensure()
    return cmd_run(cfg, rest, fix=fix, yes=yes, retry=retry, quiet=quiet, shell=shell)


if __name__ == "__main__":
    sys.exit(main())
