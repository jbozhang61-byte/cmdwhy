"""命令地图与 shell 补全：让所有命令一眼可见、可补全。"""

from __future__ import annotations

COMMAND_NAMES = [
    "init",
    "demo",
    "ingest",
    "analyze",
    "timeline",
    "explain",
    "recent",
    "block",
    "report",
    "stats",
    "sessions",
    "summary",
    "changes",
    "additions",
    "history",
    "search",
    "index",
    "digest",
    "fix",
    "diagnose",
    "repair",
    "label",
    "kb",
    "hook",
    "env",
    "run",
    "doctor",
    "do",
    "mode",
    "config",
    "export",
    "completion",
    "version",
    "guide",
]

GROUPS = [
    (
        "开始使用",
        [
            ("cmdwhy demo", "用内置 Ubuntu 示例演示全部能力（不读真实历史）"),
            ("cmdwhy init", "创建数据目录和默认配置"),
            ("cmdwhy doctor", "自检：数据目录、历史来源、hook、Git、知识库"),
            ("cmdwhy env", "查看当前完整环境：项目/工作区/分支/venv/tmux/kube/aws/conda"),
            ("cmdwhy guide", "打印这张命令地图"),
            ("cmdwhy version", "显示版本、Python、数据目录"),
            ("cmdwhy 518", "最短：等同 explain 518"),
            ("cmdwhy tl / s / sum", "timeline / search / summary 短别名"),
            ("cmdwhy today / week", "今天的汇总 / 本周汇总"),
        ],
    ),
    (
        "导入历史",
        [
            ("cmdwhy ingest", "读取配置里的历史文件，并沉淀错误知识库"),
            ("cmdwhy ingest --file 路径", "导入指定文件，并登记为长期来源"),
            ("cmdwhy analyze 路径...", "只分析指定文件，不改配置、不写知识库"),
        ],
    ),
    (
        "看注解",
        [
            ("cmdwhy timeline -n 30", "按会话展示命令、环境、动机、报错、修复链"),
            ("cmdwhy timeline --session S2", "只看某个会话"),
            ("cmdwhy block 50-60", "把 50–60 条命令当成一个阶段：任务、阶段、错误、修复、环境变化"),
            ("cmdwhy block --last 60", "直接分析最近 60 条"),
            ("cmdwhy explain 518", "按 history 编号解释：任务、目的、依据、后续"),
            ("cmdwhy explain 518 --context 40", "前后各看 40 条命令判断任务"),
            ("cmdwhy explain '#18'", "按分析序号解释（# 前缀）"),
            ("cmdwhy explain 518-520", "按编号解释一段范围"),
            ("cmdwhy explain last", "解释最近一条命令"),
            ("cmdwhy recent 3", "解释最近第 3 条；last 3 同义"),
            ("cmdwhy sessions", "列出所有会话及环境"),
            ("cmdwhy summary", "按会话总结任务、报错、修复和改变"),
            ("cmdwhy changes", "环境/状态变化：cd、安装、分支、服务、权限"),
            ("cmdwhy additions", "第一次出现的新命令"),
            ("cmdwhy history", "像 history 一样列出编号，重复命令分别编号"),
            ("cmdwhy history --duplicates", "只列出重复出现的命令"),
            ("cmdwhy search flask", "按关键词搜索命令、错误、任务"),
            ("cmdwhy search --error PORT --since 7d", "按错误和时间过滤"),
            ("cmdwhy index status", "查看 SQLite/FTS5 查询索引"),
        ],
    ),
    (
        "复盘与统计",
        [
            ("cmdwhy report", "报错 / 改变 / 添加 / 随机 四段式复盘"),
            ("cmdwhy report --md 报告.md", "同时导出 Markdown"),
            ("cmdwhy stats", "错误率、意图分布、修复耗时、sudo 比例"),
            ("cmdwhy digest --random 2", "随机回看两个会话"),
            ("cmdwhy export --format md", "导出完整报告（json/md/timeline/report）"),
        ],
    ),
    (
        "纠错与诊断",
        [
            ("cmdwhy fix 'git stauts'", "检查输入，给出可直接执行的正确命令"),
            ("cmdwhy fix --last", "检查上一条失败命令的输入"),
            ("cmdwhy diagnose", "诊断最近一次失败：以前怎么修好的"),
            ("cmdwhy diagnose --text '错误输出'", "直接给一段 stderr 做检索"),
            ("cmdwhy diagnose --signature PERM:dpkg-lock", "按错误签名检索"),
            ("cmdwhy repair graph", "看失败 → 修复动作 → 验证的因果图"),
            ("cmdwhy repair reject 19", "纠正：第 19 条不是对上一条失败的修复"),
            ("cmdwhy repair list", "列出人工确认/否定的修复链"),
            ("cmdwhy label 518 --task '...'", "人工修正任务/目标/目的"),
            ("cmdwhy run -- 命令", "包装执行，失败后即时诊断；--fix --yes 可自动修正"),
            ("cw run --fix --yes -- 命令", "同 cmdwhy run 的短别名"),
        ],
    ),
    (
        "自动完成",
        [
            ("cmdwhy do --dry-run", "根据最近命令和环境推断下一步"),
            ("cmdwhy do --yes", "执行推断出的安全步骤"),
            ("cmdwhy mode suggest", "只给建议，不自动执行"),
            ("cmdwhy mode auto", "只自动执行低风险步骤；写操作需 --yes"),
            ("cmdwhy mode autocorrect on", "cw run 失败时自动改正输入"),
        ],
    ),
    (
        "知识库与配置",
        [
            ("cmdwhy kb", "查看错误知识库"),
            ("cmdwhy kb --signature PORT:3000", "检索某个错误签名"),
            ("cmdwhy kb --learn", "重新扫描历史并学习"),
            ("cmdwhy kb --export kb.json", "导出知识库"),
            ("cmdwhy config", "查看配置"),
            ("cmdwhy config --set idle_gap 600", "修改配置项"),
            ("cmdwhy config --get sources", "读取单个配置项"),
        ],
    ),
    (
        "Shell 集成",
        [
            ("cmdwhy hook install", "安装 bash/zsh hook，记录退出码和 cwd"),
            ("cmdwhy hook status", "查看 hook 是否生效"),
            ("cmdwhy hook uninstall", "移除 hook"),
            ("cmdwhy completion bash", "输出 bash 补全脚本"),
            ("cmdwhy completion zsh --install", "安装 zsh 补全"),
        ],
    ),
]


def guide_data():
    return [{"group": group, "commands": [{"command": cmd, "description": desc} for cmd, desc in items]} for group, items in GROUPS]


def render_guide(paint=None):
    lines = []
    title = "cmdwhy 命令地图"
    if paint is not None:
        title = paint.bold(title)
    lines.append(title)
    for group, items in GROUPS:
        lines.append("")
        lines.append(("■ " + group) if paint is None else paint("■ " + group, "cyan", "bold"))
        for command, description in items:
            lines.append("  %-38s %s" % (command, description))
    lines.append("")
    footer = "完整参数：cmdwhy <命令> --help    详细文档：docs/COMMANDS.md"
    lines.append(footer if paint is None else paint(footer, "grey"))
    return "\n".join(lines)


def completion_bash():
    commands = " ".join(COMMAND_NAMES)
    return (
        "# cmdwhy bash completion\n"
        "# 安装：cmdwhy completion bash --install\n"
        "_cmdwhy_complete() {\n"
        '    local cur="$2" prev="$3"\n'
        '    local commands="' + commands + '"\n'
        '    case "$prev" in\n'
        "        hook)\n"
        '            COMPREPLY=( $(compgen -W "install uninstall status" -- "$cur") )\n'
        "            return 0\n"
        "            ;;\n"
        "        completion)\n"
        '            COMPREPLY=( $(compgen -W "bash zsh" -- "$cur") )\n'
        "            return 0\n"
        "            ;;\n"
        "        --shell)\n"
        '            COMPREPLY=( $(compgen -W "bash zsh" -- "$cur") )\n'
        "            return 0\n"
        "            ;;\n"
        "        --sections)\n"
        '            COMPREPLY=( $(compgen -W "errors changes additions random" -- "$cur") )\n'
        "            return 0\n"
        "            ;;\n"
        "        --format)\n"
        '            COMPREPLY=( $(compgen -W "json md timeline report" -- "$cur") )\n'
        "            return 0\n"
        "            ;;\n"
        "        --get|--set)\n"
        '            COMPREPLY=( $(compgen -W "sources idle_gap window redact learn color max_events ignore_prefixes" -- "$cur") )\n'
        "            return 0\n"
        "            ;;\n"
        "        --file|-o|--output|--md)\n"
        '            COMPREPLY=( $(compgen -f -- "$cur") )\n'
        "            return 0\n"
        "            ;;\n"
        "    esac\n"
        '    if [ "$COMP_CWORD" -eq 1 ]; then\n'
        '        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )\n'
        "    fi\n"
        "}\n"
        "complete -F _cmdwhy_complete cmdwhy\n"
    )


def completion_zsh():
    entries = []
    descriptions = {
        "init": "初始化数据目录",
        "demo": "内置示例演示",
        "ingest": "导入历史",
        "analyze": "分析指定文件",
        "timeline": "命令时间线",
        "explain": "解释某条命令",
        "report": "四段式复盘",
        "stats": "统计",
        "sessions": "会话列表",
        "summary": "会话概要",
        "changes": "环境变化",
        "additions": "新增命令",
        "history": "编号命令列表",
        "search": "搜索历史",
        "index": "SQLite 查询索引",
        "digest": "随机回看",
        "fix": "输入纠错",
        "diagnose": "错误诊断",
        "repair": "修复链纠正",
        "label": "人工标签",
        "kb": "错误知识库",
        "hook": "shell hook",
        "run": "包装执行",
        "doctor": "自检",
        "do": "推断并自动完成下一步",
        "mode": "自动完成/纠错开关",
        "config": "配置",
        "export": "导出",
        "completion": "补全脚本",
        "version": "版本信息",
        "guide": "命令地图",
    }
    for name in COMMAND_NAMES:
        entries.append("        '%s:%s'" % (name, descriptions.get(name, name)))
    return (
        "#compdef cmdwhy\n"
        "# cmdwhy zsh completion\n"
        "# 安装：cmdwhy completion zsh --install\n"
        "_cmdwhy() {\n"
        "    local -a commands\n"
        "    commands=(\n"
        + "\n".join(entries)
        + "\n    )\n"
        "    _arguments -C '1:命令:->command' '*::参数:->args'\n"
        "    case $state in\n"
        "        command)\n"
        "            _describe '命令' commands\n"
        "            ;;\n"
        "        args)\n"
        "            case $words[1] in\n"
        "                hook) _values '动作' install uninstall status ;;\n"
        "                completion) _values 'shell' bash zsh ;;\n"
        "                export) _values '格式' json md timeline report ;;\n"
        "                config) _values '选项' --get --set --path ;;\n"
        "            esac\n"
        "            ;;\n"
        "    esac\n"
        "}\n"
        '_cmdwhy "$@"\n'
    )
