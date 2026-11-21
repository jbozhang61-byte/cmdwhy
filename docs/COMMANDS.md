# cmdwhy 命令参考

版本：0.6.0（`cmdwhy version` 可查看当前安装版本）

完整的安装、工作流和排障说明见 [USAGE.md](USAGE.md)。

所有命令都支持全局参数，位置随意：

```bash
cmdwhy --json stats          # 等价于 cmdwhy stats --json
cmdwhy --home /tmp/cw demo   # 临时换数据目录
cmdwhy --no-color timeline   # 适合重定向到文件
```

## 最短写法

    cmdwhy 518              # 等同 cmdwhy explain 518
    cmdwhy last             # 最近一条
    cmdwhy e1a2b3c4         # 稳定 ID
    cmdwhy tl -n 20         # timeline
    cmdwhy s flask          # search
    cmdwhy sum / today / week
    cmdwhy fix              # 检查上一条失败
    cmdwhy next             # do

别名：tl/ex/why/s/find/sum/h/hist/next/st；today/week 直接映射到 summary。
## 全局参数

| 参数 | 说明 |
| --- | --- |
| `--home DIR` | 数据目录，默认 `$CMDWHY_HOME` 或 `~/.local/share/cmdwhy` |
| `--json` | 输出机器可读 JSON（每个命令的 JSON 结构见下文） |
| `--no-color` | 关闭 ANSI 颜色 |
| `--version` | 打印版本并退出 |
| `-h, --help` | 命令帮助；每个子命令也有独立帮助 |

## 命令总表

| 命令 | 一句话 | 典型场景 |
| --- | --- | --- |
| `demo` | 内置 Ubuntu 示例演示 | 第一次安装、验证效果 |
| `init` | 初始化数据目录 | 首次使用 |
| `ingest` | 导入历史并学习知识库 | 装好后第一次分析 |
| `analyze` | 临时分析指定文件 | 看同事的 history、看导出的日志 |
| `timeline` | 逐条注解时间线 | 回顾某次调试 |
| `explain` | 解释某条/一小段命令 | “我当时为什么敲这个” |
| `block` | 把 50–60 条当成一个阶段 | 复盘一段调试/部署 |
| `report` | 四段式复盘 | 写复盘、周报 |
| `stats` | 统计 | 看错误率、修复耗时 |
| `sessions` | 会话列表 | 先定位会话编号 |
| `summary` | 按会话/时间段/项目总结 | 快速回顾一次会话或今天/本周 |
| `changes` | 环境/状态变化 | 看安装了什么、切了什么分支 |
| `additions` | 首次出现的新命令 | 回顾新工具 |
| `history` | history 风格编号列表 | 重复命令要区分是哪一次 |
| `search` | 搜索命令/错误/时间/项目，支持正则/OR/BM25 | 查找某类操作 |
| `index` | SQLite FTS5 查询索引 | 搜索加速/排障 |
| `digest` | 随机回看会话 | 随机抽查自己的操作 |
| `fix` | 输入纠错 | 命令打错、找不到命令 |
| `diagnose` | 同类错误检索 | 又遇到熟悉的报错 |
| `repair` | 修复链因果图与人工纠正 | 这条不是修复 |
| `label` | 人工修正任务/目标/目的 | 启发式标签不准 |
| `kb` | 错误知识库 | 查看/导出修法 |
| `hook` | bash/zsh/fish hook | 让新命令带退出码 |
| `run` | 包装执行 + 即时诊断 | 想拿到精确 stderr；`--shell` 支持管道 |
| `do` | 推断下一步并执行安全步骤 | 让工具根据上下文接着做 |
| `mode` | 自动完成/自动纠错开关 | 开启或关闭 autopilot |
| `doctor` | 自检 | 排障 |
| `env` | 当前完整工作环境 | tmux/SSH/conda/kube/aws/worktree |
| `guide` | 命令地图 | 忘了命令名 |
| `version` | 版本信息 | 报 bug |
| `config` | 查看/修改配置 | 调整会话切分、来源 |
| `export` | 导出 json/md/timeline/report | 归档、分享 |
| `completion` | bash/zsh 补全 | 提升输入效率 |

---

## 开始使用

### cmdwhy demo

用内置数据演示全部能力，**不读取也不修改**你的真实历史。

```bash
cmdwhy demo
cmdwhy demo --limit 12                 # 时间线条数
cmdwhy demo --no-timeline              # 只看四段式报告
cmdwhy demo --no-report                # 只看时间线
cmdwhy demo --explain 518,523          # history 编号；也可写 18 表示分析序号
cmdwhy demo --sections errors          # 只看报告中的“报错”部分
cmdwhy demo --json                     # 完整分析 JSON
```

### cmdwhy init

```bash
cmdwhy init
```

创建 `~/.local/share/cmdwhy/`、默认 `config.json`，并打印事件文件、知识库路径和下一步提示。

### cmdwhy doctor

```bash
cmdwhy doctor
```

检查：Python 版本、发行版/包管理器、数据目录是否可写、事件条数、历史来源、hook 是否安装、Git、包文件查询工具、知识库规模、危险命令规则是否正常。

### cmdwhy env

```bash
cmdwhy env
cmdwhy env --json
```

显示目录、项目/工作区、分支、venv/conda、tmux/SSH、kube/aws/gcloud/docker 上下文、发行版、包管理器、用户/主机和 root/container/WSL 状态。

### 支持的发行版

| 家族 | 发行版 | 包管理器 |
| --- | --- | --- |
| Debian | Ubuntu / Debian / Kali / Mint / Pop | apt |
| Arch | Arch / Manjaro / EndeavourOS | pacman |
| Fedora | Fedora / RHEL / CentOS / Rocky / Alma | dnf / yum |
| SUSE | openSUSE Leap / Tumbleweed | zypper |
| Alpine | Alpine | apk |

从 `/etc/os-release` 识别家族；命令缺失、venv 安装、包搜索会生成对应包管理器的命令，不再写死 apt。

### cmdwhy guide / version

```bash
cmdwhy guide
cmdwhy guide --json
cmdwhy version
```

---

## 导入历史

### cmdwhy ingest

解析配置里的历史来源（bash / zsh / fish / JSONL），做环境推断、错误签名、修复链分析，并把**验证过**的修法写入 `knowledge.json`。历史文件的解析结果会按 mtime/size + redact 配置缓存到 `cache.db`（SQLite，内容已脱敏）；文件改动自动失效。

```bash
cmdwhy ingest
cmdwhy ingest --file ~/.bash_history
cmdwhy ingest --file examples/demo_history.jsonl
cmdwhy ingest --file a.jsonl --file b.jsonl   # 可重复
cmdwhy ingest --no-store                      # 不读取 hook 事件
history | cmdwhy ingest --stdin               # 直接导入 history 输出
```

`--file` 指定的文件会被**登记为长期来源**，后续 `timeline` / `report` 会继续读取它。

`--stdin` 从标准输入读取 `history` 的输出，解析编号并追加进事件库，所以 `explain 518` 可以直接用。`history` 输出不含 cwd，环境会显示“环境未知”，不会拿当前目录冒充当时目录。

### cmdwhy analyze

只分析，不登记、不写知识库，适合临时文件：

```bash
cmdwhy analyze examples/demo_history.jsonl
cmdwhy analyze ~/.zsh_history -n 50
cmdwhy analyze old.jsonl --report
cmdwhy analyze old.jsonl --report --sections errors,changes
cmdwhy analyze old.jsonl --md report.md     # 导出 Markdown
cmdwhy analyze old.jsonl --json
cmdwhy analyze examples/demo_history_output.txt   # history 输出（带编号）
history | cmdwhy analyze --stdin                  # 管道输入，不落盘
```

支持格式自动识别：`.bash_history`、`.zsh_history`、fish history、cmdwhy JSONL、shell 内建 `history` 的输出。

---

## 看注解

### cmdwhy history

像 shell 内建 `history` 一样列出带编号的命令。和 shell 一样，**重复命令会占不同编号**；cmdwhy 还会标出它是第几次出现。

```bash
cmdwhy history
cmdwhy history -n 100
cmdwhy history --all
cmdwhy history --duplicates
cmdwhy history --grep status
cmdwhy history --session S2
cmdwhy history --json
```

示例输出：

```text
命令编号  共 4 条 · 显示 4 条 · 1 个命令重复出现
编号来自 history 输出；没有 history 编号的显示为 #分析序号。查看：cmdwhy explain <编号>

     501  09:00:00  ls -la
     502  09:00:30  git status  （第 1/2 次）
     503  09:01:00  git status  （第 2/2 次）
     504  09:01:30  git puhs
```

- 有 history 输出编号时显示原编号（如 `502`）；没有时显示 `#分析序号`；
- `--duplicates` 只列重复命令，方便看清“同一命令的多次执行”；
- 编号可以直接交给 `cmdwhy explain`，重复命令不会混淆。

### cmdwhy search

按关键词、错误、状态、时间、项目、会话搜索，结果保留 history 编号：

`@bash
cmdwhy search flask
cmdwhy search --error PORT --since 7d
cmdwhy search --status fail --project api
cmdwhy search --session S2 --oldest
cmdwhy search --since today --until "2026-11-17 18:00"
cmdwhy search --regex 'PORT|EADDRINUSE'
cmdwhy search --any npm pnpm yarn
cmdwhy search git push --sort relevance
cmdwhy search git --json
`@

- 默认多个关键词是 AND；--any 改为 OR；--regex 把查询当正则；--sort relevance 用 BM25；
- 有索引时直接走 SQLite FTS5，未建索引、正则或中文查询回退到 Python BM25；
- 匹配命令文本、意图、任务、目的、错误签名/原文、项目名、cwd；
- `--status`：`ok` / `fail` / `unknown`（`fail` 包含疑似失败）；
- `--error`：按错误签名或类别子串匹配，如 `PORT:3000`、`PERM`；
- `--since/--until`：`7d`、`24h`、`30m`、`2w`、`today`、`yesterday`、`2026-11-17 [HH:MM]`；
- `--limit 0` 显示全部，`--oldest` 按时间正序；
- 无时间戳的旧历史在带时间过滤时排除。
### cmdwhy index

    cmdwhy index status
    cmdwhy index rebuild
    cmdwhy index clear

索引库是 `index.db`，保存事件、状态、任务、错误、项目字段，并用 FTS5 建全文索引。`ingest`/`search` 会自动更新；签名（来源 mtime/size + store + labels + 配置）不一致时会重建。损坏的 index.db/cache.db 会自动删除重建。


### cmdwhy summary

`@bash
cmdwhy summary
cmdwhy summary --session S2
cmdwhy summary --all
cmdwhy summary --today
cmdwhy summary --week
cmdwhy summary --project api
cmdwhy summary --since 7d
cmdwhy summary --json
`@

每条会话输出：命令数、报错数、修复动作与验证数、主要任务、错误签名、修复步骤、环境改变。

`@text
── S2  11:40–12:07 · 27m00s · ~/work/api · api · git:main · venv:.venv · Ubuntu 24.04
   13 条命令 · 4 处报错 · 4 个修复动作（4 已验证）
   任务  系统软件包管理 · 脚本执行权限 · Node 开发服务 · Docker 与容器
   错误  PERM:dpkg-lock ×1 · PERM:exec ×1 · PORT:3000 ×1 · DOCKER ×1
   修复  sudo apt install jq -y › chmod +x deploy.sh › kill 4242 › sudo docker ps
   改变  安装软件包 jq · 修改权限 +x deploy.sh · 结束进程 4242
`@

默认显示最近 5 个会话，`--all` 显示全部。

`--today` / `--week`（周一开始）/ `--project` / `--since` / `--until` 不按会话拆分，而是输出聚合概要：命令数、会话数、报错、修复、任务、错误签名、改变。

`--today` / `--week`（周一开始）/ `--project` / `--since` / `--until` 不按会话拆分，而是输出聚合概要：命令数、会话数、报错、修复、任务、错误签名、改变。

### cmdwhy timeline

```bash
cmdwhy timeline
cmdwhy timeline -n 50
cmdwhy timeline --session S2
cmdwhy timeline --page 2 --page-size 20   # 分页
cmdwhy timeline -v              # 显示全部证据
cmdwhy timeline --json
```

每条命令显示：会话环境、退出码/失败、错误签名与原文摘要、意图、动机、修复链、输入更正、环境改变。

### cmdwhy explain

```bash
cmdwhy explain last
cmdwhy explain 518            # history 输出里的编号（优先）
cmdwhy explain 518-520
cmdwhy explain '#18'          # 分析序号（会随新增历史漂移）
cmdwhy explain e1a2b3c4       # 稳定 ID（推荐）
cmdwhy explain h518           # 强制按 history 编号
cmdwhy explain seq:18         # 强制按分析序号
cmdwhy explain 518 --context 40   # 前后各看 40 条
cmdwhy explain 518 --json
```

数字解析规则：

| 写法 | 含义 |
| --- | --- |
| `518` | 先找 history 编号，找不到再当分析序号 |
| `e1a2b3c4` / `uid:e1a2b3c4` | 稳定 ID（新增历史后不变，推荐） |
| `#18` / `seq:18` | 分析序号（当前顺序，会漂移） |
| `h518` / `h:518` | history 编号 |
| `518-520` | 有 history 编号时按编号区间，否则按分析序号区间 |
| `#18-20` / `seq:18-20` | 强制按分析序号区间 |
| `h518-520` | 强制按 history 编号区间 |
| `last` | 最近一条 |

时间线同时显示 `#18`（当前顺序）、`h518`（history 编号）和 `e1a2b3c4`（稳定 ID）。修复链/报告引用会写成 `#18[e1a2b3c4]`，推荐用稳定 ID 复查，因为新增历史后 `#18` 可能指向别的命令。同一个 history 编号出现多次时，默认显示最近一条，并给出提示。

输出字段：

- **命令 / 结果 / 置信度**：成功、失败（退出码）、疑似失败，以及置信度依据；
- **意图 / 动机**：这条命令想做什么、在整段会话里承担什么角色；
- **错误**：签名、原文、退出码；
- **环境**：目录、项目/工作区、分支、venv/conda、tmux/SSH、kube/aws/gcloud/docker、发行版；
- **位置 / 历史编号**：会话编号、分析序号，以及 history 输出里的编号；
- **任务 / 目标 / 阶段**：用前后各 20 条命令、当时环境和每条命令的角色推断“当时在干什么”，以及当前处于准备/排查/修复/验证的哪个阶段；
- **作用 / 目的**：这条命令是只读排查、改变环境还是运行验证，以及它在当前任务里具体想达成什么；
- **目的**：这一条命令在任务中的具体作用；
- **上下文**：窗口内最关键的错误、验证和命令；
- **推断**：一句自然语言解释“为什么敲”；
- **依据**：报错、修复动作、验证记录、更正建议；
- **建议**：Ubuntu 上该怎么处理；
- **后续**：下一条命令及其状态。

任务上下文默认看前后各 20 条命令，限制在同一会话、同一项目/工作区、同一分支/venv/conda 和同一终端会话内；窗口内错误签名权重最高，其次是命令家族、当时环境（项目/cwd/分支/venv/发行版/包管理器/容器/SSH/WSL/root）、命令角色（只读排查/改变环境/运行验证）和修复链。

```bash
cmdwhy explain 518 --context 40
cmdwhy config --set context_window 30
```

这是启发式判断，不是因果证明；任务标签会标出置信度，窗口跨项目/会话时会自动截断。

### cmdwhy block

```bash
cmdwhy block 50-60
cmdwhy block '#50-60'
cmdwhy block h518-560
cmdwhy block --last 60
cmdwhy block --last 60 --json
```

`explain 50-60` 是逐条解释；`block 50-60` 把这一段当成一个阶段，输出：

- 命令段、会话数、时间范围、当前环境；
- 总体任务、阶段变化、成功/失败/修复/验证；
- 错误签名、角色分布、环境变化；
- 按任务分组；
- 每条命令的作用和目的（最多 240 条）。

默认无参数时分析最近 50 条；`--window` 可改上下文窗口。

### cmdwhy sessions / changes / additions

```bash
cmdwhy sessions
cmdwhy changes
cmdwhy additions
```

- `changes` 列出 cd、安装、创建目录、改权限、切分支、重启服务、结束进程等会改变环境的命令；
- `additions` 以**命令名**为粒度，列出第一次出现的工具。

---

## 复盘与统计

### cmdwhy report

```bash
cmdwhy report
cmdwhy report --sections errors
cmdwhy report --sections changes,additions
cmdwhy report --random 3 --seed 7
cmdwhy report --md report.md
cmdwhy report --md -            # Markdown 打到标准输出
```

四段固定结构：

1. **报错**：按错误签名分组，列出失败命令、错误原文、修复步骤、是否验证；
2. **改变**：环境/状态变化；
3. **添加**：第一次出现的命令；
4. **随机**：随机抽取会话回看。

### cmdwhy stats

```bash
cmdwhy stats
cmdwhy stats --json
```

统计命令数、会话数、错误率、修复链与验证数、平均修复耗时（MTTR）、意图分布、常用命令、高频错误、sudo 比例、危险命令数。

### cmdwhy digest

```bash
cmdwhy digest
cmdwhy digest --random 3 --seed 42
```

随机回看会话的意图分布、报错和修复动作。

### cmdwhy export

```bash
cmdwhy export --format md -o report.md
cmdwhy export --format report -o report.txt
cmdwhy export --format timeline -n 100
cmdwhy export --format json -o history.json
cmdwhy export --format json              # 标准输出
```

`json` 结构包含 `stats`、`sessions`（含每条事件）、`annotations`（每条命令的完整注解）。

---

## 纠错与诊断

### cmdwhy fix

```bash
cmdwhy fix "git stauts"
cmdwhy fix "gti status"
cmdwhy fix "apt instal jq"
cmdwhy fix --last
cmdwhy fix --last --top 5
cmdwhy fix "git stauts" --json
```

候选来源：PATH 可执行文件、shell 内建、合法子命令、你成功用过的历史命令。评分考虑 Damerau-Levenshtein 距离、键盘相邻键、首字母、历史使用次数、下一个词是否是候选子命令；危险命令降权。

除了拼写，还会按错误类型给出修正：`PERM:exec` → `chmod +x`；Docker 权限 → `sudo`；`GIT_REJECT` → `git pull --rebase`；`PIP668` → 创建 venv；`MODULE` → `pip install <模块>`；`python` → `python3`；`cd` 到不存在的目录 → 最接近的兄弟目录或 `mkdir -p`；文件父目录不存在 → `mkdir -p <父目录>`。

### cmdwhy diagnose

```bash
cmdwhy diagnose
cmdwhy diagnose --last
cmdwhy diagnose --text "error: externally-managed-environment"
cmdwhy diagnose --file err.log
cmdwhy diagnose --signature PERM:dpkg-lock
cmdwhy diagnose --signature PORT:3000 --fix
cmdwhy diagnose --text "..." --json
```

检索顺序：同签名精确匹配 → 同类别兜底 → 错误原文相似度（路径/PID 不同也能匹配）。命中后给出你以前**验证有效**的修法，再给通用建议，最后（`--fix`）给输入纠正。

### cmdwhy repair

查看失败 → 修复动作 → 验证的因果图，并允许人工纠正：

    cmdwhy repair graph
    cmdwhy repair reject '#19'    # 第 19 条不是对上一条失败的修复
    cmdwhy repair accept '#19'    # 确认这条修复链成立
    cmdwhy repair list

图里的因果概率是 logistic 评分：综合时间距离、重跑相似度、修复动作、验证状态和错误置信度；人工 reject 直接置 0，accept 置 1。纠正按失败事件的稳定 ID 持久化到 repairs.json；之后 explain、报告和知识库学习都会尊重它。


### cmdwhy label

    cmdwhy label 518 --task '部署 API' --goal '发布新版本' --purpose '发布并确认回滚点'
    cmdwhy label 518 --clear
    cmdwhy label --list

标注按稳定 ID 写入 labels.json；之后 explain、timeline、summary、search 优先使用人工标签。

### cmdwhy kb

```bash
cmdwhy kb
cmdwhy kb --signature MODULE:flask
cmdwhy kb --learn
cmdwhy kb --export kb.json
cmdwhy kb --export -            # JSON 标准输出
cmdwhy kb --clear
```

知识库只从“已验证”或“高/中置信度”的修复链学习，避免把猜测固化成经验。

### cmdwhy run / cw

```bash
cmdwhy run -- npm run dev
cmdwhy run --shell -- "npm run dev | tee dev.log"   # 管道/重定向
cmdwhy run --fix -- python3 app.py
cmdwhy run --fix --yes -- git stauts
cmdwhy run --fix --yes --retry -- python3 app.py
cw run --fix --yes -- git stauts        # 安装后等价的短命令
```

- 捕获 stdout/stderr 并实时透传；
- 失败后记录退出码、stderr 尾部、cwd、发行版；
- 立即诊断并给出修正；
- `--yes` 只自动执行通过安全检查的修正；危险命令、含 `<包名>` 占位符的建议一律不执行；`autocorrect` 只自动执行拼写/chmod 等无提权修正，并尝试知识库里验证过且不含 sudo 的修法；
- `--retry` 只在“安装类”修正成功后重跑原命令；
- `--shell` 让命令经过 shell 执行，支持管道、重定向、通配符；默认不经过 shell，参数原样传递。

### cmdwhy do / mode

默认只建议，不执行：

`@bash
cmdwhy do --dry-run       # 推断下一步，只展示计划
cmdwhy do --from 518      # 从指定编号开始推断
cmdwhy do --yes           # 执行计划里的低/中风险步骤（高风险仍不执行）
cmdwhy mode suggest       # 默认：只给建议
cmdwhy mode auto          # 只自动执行低风险步骤
cmdwhy mode off           # 关闭自动完成
cmdwhy mode autocorrect on    # cw run 失败时自动改正输入
`@

`do` 的依据：最近一条命令的退出码/错误、任务上下文、当前项目类型、历史知识库和当前目录里的项目文件。最多 5 步，失败即停。

生成的动作示例：

| 场景 | 生成的下一步 |
| --- | --- |
| 输入错误 `git stauts` | `git status` |
| `apt install` 权限不足 | `sudo apt install ...` |
| 端口占用 | `ss -ltnp` 配合 `grep 3000`，或 `lsof -i :3000` |
| Git 推送被拒 | `git pull --rebase`，然后重跑 push |
| Python 模块缺失 | `python3 -m pip install <module>` |
| PEP 668 | `python3 -m venv .venv` |
| 项目没有 venv | `python3 -m venv .venv` |
| Node 项目没有依赖 | `npm install` |

安全边界：

- 默认 `suggest`，`auto` 必须手动开启；
- auto 只执行低风险；中风险写操作需要 `--yes`；sudo/apt/systemctl 等高风险永不执行；
- 每步 120 秒超时，失败即停；
- 不执行 `cd`、`source`、`export` 这类无法影响父 shell 的命令；
- 含 `<包名>` 等占位符的建议不会执行；
- 执行结果会作为普通事件记录，可用 `cmdwhy explain` 复查。

---

## Shell 集成

### cmdwhy hook

```bash
cmdwhy hook install
cmdwhy hook install --shell bash
cmdwhy hook install --shell zsh
cmdwhy hook install --shell fish             # 写入 ~/.config/fish/config.fish
cmdwhy hook install --print --shell bash     # 只打印脚本
cmdwhy hook install --rc /tmp/bashrc          # 指定 rc（测试用）
cmdwhy hook status
cmdwhy hook uninstall
```

hook 在每次提示符出现前，把上一条命令的退出码、cwd、发行版和 history 编号（有则记录）写入 `events.jsonl`。bash 用 `PROMPT_COMMAND`（兼容数组），zsh 用 `preexec`+`precmd`，fish 用 `fish_preexec`+`fish_prompt`。连续执行同一条命令会分别记录。它不改变命令执行结果，也不拦截输出。

### cmdwhy completion

```bash
cmdwhy completion bash
cmdwhy completion bash --install
cmdwhy completion zsh
cmdwhy completion zsh --install
```

安装位置：

- bash：`~/.local/share/bash-completion/completions/cmdwhy`
- zsh：`~/.zfunc/_cmdwhy`

zsh 还需要在 `~/.zshrc` 里保证：

```zsh
fpath=(~/.zfunc $fpath)
autoload -Uz compinit && compinit
```

补全覆盖子命令、`hook` 动作、`--sections`、`--format`、配置项名和文件参数。

---

## 配置

### cmdwhy config

```bash
cmdwhy config
cmdwhy config --path
cmdwhy config --get idle_gap
cmdwhy config --set idle_gap 600
cmdwhy config --set window 12
cmdwhy config --set color never
cmdwhy config --set sources ~/.bash_history,~/.zsh_history
cmdwhy config --json
```

可配置项：

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `sources` | 字符串数组 | 历史文件路径，支持 `~` 和通配符 |
| `idle_gap` | 整数秒 | 超过多久切分会话，默认 1800 |
| `window` | 整数 | 向后找修复/重跑的最大条数，默认 8 |
| `context_window` | 整数 | 判断任务上下文时前后各看多少条，默认 20 |
| `redact` | 布尔 | 落盘前脱敏，默认 true |
| `learn` | 布尔 | 是否从分析结果学习知识库，默认 true；false 时 `ingest` 跳过学习（`kb --learn` 仍可手动执行） |
| `autopilot` | off/suggest/auto | 自动完成模式，默认 suggest |
| `autocorrect` | 布尔 | cw run 失败时自动执行高可信修正，默认 false |
| `color` | auto/always/never | 颜色策略 |
| `max_events` | 整数 | 最多分析最近多少条，默认 5000 |
| `ignore_prefixes` | 字符串数组 | 不记录/不分析的命令前缀 |

---

## 退出码与 JSON

- `0`：成功；
- `1`：没有数据、没有匹配、或用户可修正的错误；
- `2`：参数/配置错误；
- `cmdwhy run`：返回被包装命令的退出码；自动修正成功时返回修正命令的退出码。

所有 `--json` 输出都是 UTF-8、`ensure_ascii=False`、缩进 2 的 JSON，字段为中文值、英文键，便于 `jq` 处理：

```bash
cmdwhy timeline --json | jq '.stats'
cmdwhy export --format json | jq '.annotations[] | select(.status=="fail")'
```

## 环境变量

| 变量 | 作用 |
| --- | --- |
| `CMDWHY_HOME` | 覆盖数据目录 |
| `NO_COLOR` | 关闭颜色（等价 `--no-color`） |
| `PYTHONIOENCODING=utf-8` | 非 UTF-8 终端下建议设置 |

## 常见组合

```bash
# 每天收工前生成一份 Markdown 复盘
cmdwhy ingest && cmdwhy report --md report.md

# 看最常踩的坑
cmdwhy stats --json | jq '.signatures[:3]'

# 排查某个报错
cmdwhy diagnose --text "error: externally-managed-environment"

# 在 CI 里分析一段历史
cmdwhy analyze artifacts/history.jsonl --report --sections errors
```

## 另见

- [README](../README.md)：安装、原理、置信度、隐私、局限
- [示例报告](../examples/sample_report.md)
- [示例时间线](../examples/sample_timeline.txt)
- [示例解释](../examples/sample_explain.txt)
