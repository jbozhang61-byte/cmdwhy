# cmdwhy

**让命令历史自己解释自己。**

`history` 只记得你敲了什么。cmdwhy 补上另外四件事：

- **在什么环境**：目录、项目类型、Git 分支、虚拟环境、发行版、是否 root、容器 / SSH；
- **为什么敲**：这条命令在整段会话里的动机（装依赖、修权限、排查、重试、切换目录……）；
- **错在哪、怎么好的**：退出码 + 错误原文 → 稳定错误签名 → 修复链 → 是否被重跑验证；
- **以后怎么办**：同类错误自动检索你以前真正修好它的命令；打错字时自动给出更正建议。

Linux 优先：Debian/Ubuntu/Kali、Arch/Manjaro、Fedora/RHEL/CentOS/Rocky/Alma、openSUSE、Alpine 都能用；纯 Python 标准库，零第三方依赖，数据全部留在本机。

## 30 秒感受

```bash
python3 -m cmdwhy demo
```

它使用内置的一段 Ubuntu 日常（flask 缺失、PEP 668、拼写错误、端口占用、Docker 权限、Git 推送被拒），不读取你的真实历史。节选：

```text
── S2  11:40–12:07 · 27m00s · ~/work/api · api · git:main · venv:.venv · Ubuntu 24.04
   13 条命令 · 4 处报错 · 4 个修复动作
  #18  11:40:00  $ apt install jq
       ✗ 失败（1）  意图：安装系统包
       报错  PERM:dpkg-lock  E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)
       动机  执行失败，随后用修复动作救场
       修复链  sudo apt install jq -y  ✓ 已验证
       更正  sudo apt install jq（高）
  #19  11:41:00  $ sudo apt install jq -y
       ✓ 成功（0）  补 sudo 提权重试
       动机  修复 #18 的报错
       修复  #18 的 PERM:dpkg-lock
       改变  安装软件包 jq
```

这就是开头说的那种注释：**“用户在这里遇到权限错误，随后用 sudo 重试，意图是修复权限不足”**，只不过 cmdwhy 会自动生成，并且带证据和置信度。

## 它是怎么回答“为什么”的

| 维度 | 数据来源 | 例子 |
| --- | --- | --- |
| 工作环境 | 历史里的 cwd + 扫描项目标记 + Git + venv + /etc/os-release + hook 记录 | `~/work/api · api(python) · git:main* · venv:.venv · Ubuntu 24.04 · ubuntu@devbox` |
| 动机 | 前后命令关系 + 命令意图分类 + 修复链 | “修复 #18 的 PERM:dpkg-lock” |
| 报错 | hook 捕获的 exit code / stderr；没有则从后续动作反推 | `PERM:dpkg-lock`、`PORT:3000`、`MODULE:flask` |
| 后续 | 寻找同一条命令的重跑，检查是否成功 | “在 #19 重跑并成功 → 修复已验证” |
| 任务上下文 | 前后各 20 条命令、错误签名、项目类型、修复链 | “正在修复 Python 依赖，当前处于修复阶段” |
| 建议 | 错误签名知识库 + Ubuntu 常见处置 + 输入纠错 | `sudo apt install jq` |

## 用前后几十条命令判断“当时在干什么”

`cmdwhy explain` 默认会看这条命令**前后各 20 条**命令（限制在同一会话、同一项目内），用加权规则判断当前任务，并给出这条命令的目的：

```text
任务    Node 开发服务 · 排查（任务判断 高）
目标    让 api 的开发服务在本地跑起来
目的    尝试运行 npm 脚本；因 PORT:3000 失败，成为当前任务的卡点
上下文  #23 报 PORT:3000；#27 验证成功（窗口 #18–#30，共 13 条）
```

判断依据按权重排序：

1. 窗口内出现的**错误签名**（如 `PORT:3000`、`MODULE:flask`、`GIT_REJECT`）；
2. 命令家族与关键 token（pip/venv、npm、git、apt、docker、systemctl、ss/lsof…）；
3. 项目类型（python/node/rust…）与当前目录；
4. 修复链：这条命令是准备、排查、修复还是验证。

调整窗口：

```bash
cmdwhy explain 518 --context 40   # 前后各 40 条
cmdwhy config --set context_window 30
```

局限：这是**启发式判断**，不是读心。任务标签会标注置信度；窗口跨越不同项目或会话时会自动截断，不会把两件事混在一起。

## 自动完成与自动纠错

默认是 **suggest（只建议）**，不会动你的系统。需要时可以显式开启：

### 1. 命令打错，自动改正

```bash
cmdwhy mode autocorrect on
cw run -- git stauts
```

`cw run` 检测到 `CMD_NOT_FOUND` / 权限类错误，且修正命令可信度高、无危险时，会直接执行修正：

```text
cmdwhy: autocorrect 已开启，自动执行修正： git status
cmdwhy: 已自动改正并执行成功。
```

手动方式仍然可用：`cmdwhy fix "git stauts"`、`cw run --fix --yes -- git stauts`。

除了拼写错误，`--fix` 还会针对错误类型给出可执行修正：脚本没有执行位 → `chmod +x`；Docker 权限 → `sudo`；Git 推送被拒 → `git pull --rebase`；PEP 668 → 创建 venv；缺少 Python 模块 → `pip install`。`autocorrect` 只自动执行身份明确、无提权的一类（拼写、chmod）；sudo 修正必须显式 `cw run --fix --yes`。如果同类错误在知识库里有验证过且不含 sudo 的修法，也会按步骤自动执行。

### 2. 根据上下文推断下一步

```bash
cmdwhy do --dry-run
cmdwhy do --from 518 --dry-run    # 从指定 history 编号开始推断
```

它综合最近命令、错误签名、任务上下文、当前项目类型和历史知识库，给出最多 5 步计划：

```text
下一步计划
  基于 #23 · Node 开发服务
  目标  让 api 的开发服务在本地跑起来

  1. [低风险] ss -ltnp | grep 3000
       确认端口被哪个进程占用

  2. [低风险] lsof -i :3000
       用另一种方式确认占用进程

当前模式 suggest：只给计划；cmdwhy do --yes 执行；cmdwhy mode auto 自动。
```

### 3. 自动完成

```bash
cmdwhy mode auto
cmdwhy do
```

自动模式只自动执行**低风险**步骤；中风险写操作（创建 venv、pip/npm 安装、chmod、git pull/push）需要 `cmdwhy do --yes` 明确确认；sudo、apt/systemctl、`rm`、`dd`、`mkfs`、关机等高风险命令永远不会自动执行。每步 120 秒超时，失败即停。

```bash
cmdwhy do --yes       # suggest 模式下，确认执行计划
cmdwhy do --dry-run   # 任何时候都只看计划
cmdwhy mode off       # 关闭自动完成
cmdwhy mode suggest   # 恢复为只建议（默认）
```

安全边界：

- 默认 `suggest`，`auto` 必须手动开启；
- auto 只执行低风险；中风险必须 `--yes`；高风险永不执行；
- 不执行 `cd`、`source`、`export` 这类无法影响父 shell 的命令；
- 含 `<包名>` 等占位符的建议不会执行；
- 执行失败立刻停止，不会继续“硬猜”；
- 所有步骤都记录为普通命令事件，可以事后用 `cmdwhy explain` 复查。

## 搜索与过滤

命令多了以后，可以按关键词、错误、状态、时间、项目、会话查：

```bash
cmdwhy search flask
cmdwhy search --error PORT --since 7d
cmdwhy search --status fail --project api
cmdwhy search --session S2 --oldest
cmdwhy search --since today --until "2026-11-17 18:00"
cmdwhy search --regex 'PORT|EADDRINUSE'
cmdwhy search --any npm pnpm yarn
cmdwhy search git push --sort relevance
cmdwhy search git --json
```

搜索范围包括命令文本、意图、任务、目的、错误签名/原文、项目名和 cwd。默认多个关键词是 AND；--any 改为 OR，--regex 把查询当正则，--sort relevance 用 BM25 排序。有索引时查询直接走 SQLite FTS5；未建索引、正则或中文查询回退到 Python BM25。结果保留 history 编号与稳定 ID，可以直接：

```text
命令搜索  关键词：flask · 显示 1 / 共 62 条

  #3    h503   09:13  ✗  python3 app.py  MODULE:flask
       Python 依赖与环境 · 运行 Python 脚本 · api · ~/work/api
```

时间参数支持：

- `7d`、`24h`、`30m`、`2w`
- `today` / `yesterday`
- `2026-11-17`、`2026-11-17 09:00`

没有时间戳的旧历史在带时间过滤时会被排除，避免误判。

## 会话概要

不想看逐条时间线时，可以按会话快速回顾“这次到底做了什么”：

```bash
cmdwhy summary
cmdwhy summary --session S2
cmdwhy summary --all
cmdwhy summary --today
cmdwhy summary --week
cmdwhy summary --project api
cmdwhy summary --since 7d
cmdwhy summary --json
```

```text
── S2  11:40–12:07 · 27m00s · ~/work/api · api · git:main · venv:.venv · Ubuntu 24.04
   13 条命令 · 4 处报错 · 4 个修复动作（4 已验证）
   任务  Ubuntu 软件包管理 · 脚本执行权限 · Node 开发服务 · Docker 与容器
   错误  PERM:dpkg-lock ×1 · PERM:exec ×1 · PORT:3000 ×1 · DOCKER ×1
   修复  sudo apt install jq -y › chmod +x deploy.sh › kill 4242 › sudo docker ps
   改变  安装软件包 jq · 修改权限 +x deploy.sh · 结束进程 4242
```

每条会话会汇总：命令数、报错数、修复动作与验证数、主要任务、错误签名、修复步骤、环境改变。

--today / --week（周一开始）/ --project / --since / --until 会切换到聚合视图：

    今日概要  42 条命令 · 3 个会话 · 6 处报错 · 5 个修复（4 已验证）
       任务  Node 开发服务 · Docker 与容器
       错误  PORT:3000 ×2 · DOCKER ×1
       修复  kill 4242 › sudo docker ps
       改变  结束进程 4242

## 安装



### 方式一：直接用，不安装

```bash
git clone <你的仓库地址> cmdwhy
cd cmdwhy
python3 -m cmdwhy demo
```

要求 Python 3.8+，无第三方依赖。Debian/Ubuntu/Kali、Arch、Fedora/RHEL/CentOS、openSUSE、Alpine 的官方 Python 都够。

### 方式二：安装成 `cmdwhy` / `cw` 命令

```bash
cd cmdwhy
bash install.sh        # 自动识别 apt/pacman/dnf/zypper/apk，建 .venv
. .venv/bin/activate
cmdwhy --version
```


### 支持的发行版

| 发行版 | 包管理器 | 说明 |
| --- | --- | --- |
| Ubuntu / Debian / Kali / Mint / Pop | apt | 主要开发环境，hook 已在 Ubuntu 实测 |
| Arch / Manjaro / EndeavourOS | pacman | 用 pacman 生成安装/搜索建议 |
| Fedora / RHEL / CentOS / Rocky / Alma | dnf / yum | 用 dnf provides 查命令归属 |
| openSUSE Leap / Tumbleweed | zypper | 用 zypper 搜索包 |
| Alpine | apk | 官方 Python 即可，install.sh 会装 bash |

命令缺失时不再写死 sudo apt install，而是按当前发行版生成 pacman/dnf/zypper/apk 命令；`cmdwhy doctor` 会显示检测到的发行版和包管理器。
安装后会得到两个命令：

- `cmdwhy`：分析、报告、诊断、纠错；
- `cw`：包装执行器，运行时捕获真实错误，失败后给出或执行修正（见下文）。

## 最省事的用法

不用记完整子命令，直接用编号或短别名：

| 想做什么 | 最短写法 |
| --- | --- |
| 看某条命令为什么执行 | `cmdwhy 518` / `cmdwhy '#18'` / `cmdwhy e1a2b3c4` |
| 看最近一条 | `cmdwhy last` |
| 看时间线 | `cmdwhy tl -n 20` |
| 搜索 | `cmdwhy s flask` / `cmdwhy find PORT` |
| 会话/今天/本周总结 | `cmdwhy sum` / `cmdwhy today` / `cmdwhy week` |
| 检查上一条失败命令 | `cmdwhy fix` |
| 推断下一步 | `cmdwhy next` / `cmdwhy do` |
| 查看命令地图 | `cmdwhy guide` |

短别名：`tl`=timeline，`ex`/`why`=explain，`s`/`find`=search，`sum`=summary，`h`/`hist`=history，`next`=do，`st`=stats；`today`/`week` 直接是 summary 的快捷方式。

## 快速开始

```bash
cmdwhy init            # 建数据目录，默认 ~/.local/share/cmdwhy
cmdwhy ingest          # 读取 ~/.bash_history / ~/.zsh_history / fish 历史，沉淀知识库
cmdwhy timeline -n 30  # 按会话看逐条注解
cmdwhy timeline --page 2 --page-size 20   # 分页看历史
cmdwhy report          # 报错 / 改变 / 添加 / 随机 四段式复盘
cmdwhy hook install    # 关键：让之后的命令带上退出码和错误原文
exec bash -l           # 或新开终端，让 hook 生效
```

`hook install` 会往 `~/.bashrc` / `~/.zshrc` 追加配置，`--shell fish` 时写入 `~/.config/fish/config.fish`，并在数据目录生成 hook 脚本。bash 用 `PROMPT_COMMAND`（兼容 5.1+ 的数组形式），zsh 用 `preexec` + `precmd`，fish 用 `fish_preexec` + `fish_prompt`。它把上一条命令的**退出码、cwd、发行版和 history 编号（有则记录）**写进 `events.jsonl`；连续两次执行同一条命令也会分别记录。命令本身仍在 shell 里执行，cmdwhy 只旁路记录。

### 没有时间戳的旧历史也能分析

bash 默认不记录时间。cmdwhy 会：

1. 有 `#<epoch>` 注释就按时间解析（设置了 `HISTTIMEFORMAT` 的历史）；
2. 没有时间戳时保留原有顺序，归入“时间未知”的会话；
3. 用“随后是否出现 sudo / 改正 / 安装 / 创建目录”等动作，反推上一条大概率失败了；
4. 所有推断都标成 **推测**，置信度低，不冒充事实。


### 直接按 history 数字分析

shell 内建 `history` 会给每条命令一个编号：

```text
 512  git status
 518  apt install jq
 519  sudo apt install jq -y
```

cmdwhy 可以直接吃这份输出，并沿用同样的编号：

```bash
history > /tmp/history.txt
cmdwhy ingest --file /tmp/history.txt
cmdwhy explain 518          # 518 是 history 输出里的编号
cmdwhy explain 518-520
cmdwhy explain '#18'        # # 前缀 = cmdwhy 分析序号
cmdwhy explain h518         # 强制按 history 编号

history | cmdwhy ingest --stdin    # 不落文件，直接导入
history | cmdwhy analyze --stdin   # 只看一次，不写库
```

时间线会同时显示三套标识：

- `#18`：当前分析顺序。**新增/导入更早的历史后会漂移**，只适合当前视图；
- `h518`：shell 的 history 编号，稳定但旧历史可能没有；
- `e1a2b3c4`：cmdwhy 的稳定 ID，落盘时生成，**新增历史后仍指向同一条命令**。

修复链、后续命令、报告里的引用会显示成 `#18[e1a2b3c4]`，其中 e 开头的是稳定 ID。推荐用稳定 ID 定位：

同一 history 编号的 hook 事件和 history 输出会按同一次执行合并，保留信息更全的一条；无法确认的重复仍会保留，不强行合并。

`@bash
cmdwhy explain e1a2b3c4
cmdwhy explain uid:e1a2b3c4
`@

数字参数的解析优先级是：

1. `e...` / `uid:e...` → 稳定 ID；
2. 带 `#` 前缀（`#18`）→ 分析序号；
3. 带 `h` 前缀（`h518`）→ history 编号；
4. 纯数字（`518`）→ 先找 history 编号，找不到再当分析序号；
5. 区间：`518-520` 有 history 编号时按编号区间，否则按分析序号区间；`#18-20`、`seq:18-20`、`h518-520` 可强制指定编号体系。

`history` 输出不含 cwd，导入后环境会显示“环境未知”，不会拿你**当前**目录冒充当时目录；想要完整环境，用 hook 或带上 cwd 的 JSONL。


没有原始 `history` 输出时，也可以先让 cmdwhy 给命令编号：

```bash
cmdwhy history              # 最近 50 条，带编号
cmdwhy history -n 100
cmdwhy history --all
cmdwhy history --duplicates # 只列出重复出现的命令
cmdwhy history --grep status
```

重复命令会被分别编号，并标出是第几次出现：

```text
命令编号  共 4 条 · 显示 4 条 · 1 个命令重复出现
编号来自 history 输出；没有 history 编号的显示为 #分析序号。查看：cmdwhy explain <编号>

     501  09:00:00  ls -la
     502  09:00:30  git status  （第 1/2 次）
     503  09:01:00  git status  （第 2/2 次）
     504  09:01:30  git puhs
```

这样 `explain 502` 和 `explain 503` 就是两条不同的 `git status`，不会混淆。



## 常用命令

| 命令 | 作用 |
| --- | --- |
| `cmdwhy demo` | 用内置 Ubuntu 数据演示全部能力 |
| `cmdwhy init` | 初始化数据目录和配置 |
| `cmdwhy ingest [--file 路径] [--stdin]` | 导入历史（也支持 history 管道输入），学习错误→修复的知识库 |
| `cmdwhy analyze 文件... [--stdin]` | 只分析指定历史文件或标准输入，不改配置、不写知识库 |
| `cmdwhy timeline [-n N] [--session S2] [--page 2]` | 按会话展示；`--page/--page-size` 分页 |
| `cmdwhy explain 518` / `'#18'` / `e1a2b3c4` | 按 history 编号、当前序号或稳定 ID 解释命令；可调前后窗口 |
| `cmdwhy report [--md 文件]` | 生成“报错 / 改变 / 添加 / 随机”四段式复盘 |
| `cmdwhy export --format md -o 文件` | 导出 json / md / timeline / report |
| `cmdwhy stats` | 错误率、意图分布、修复耗时（MTTR）、sudo 比例 |
| `cmdwhy sessions` | 列出会话及每个会话的环境 |
| `cmdwhy summary [--session S2] [--today] [--week] [--project api]` | 按会话/时间段/项目总结 |
| `cmdwhy changes` | 环境/状态变化：cd、安装、分支、服务、权限…… |
| `cmdwhy additions` | 第一次出现的新命令 |
| `cmdwhy history [--duplicates] [--grep 文本]` | 像 history 一样列出编号，重复命令分别编号 |
| `cmdwhy search 关键词` / `--regex` / `--any` / `--sort relevance` | 搜索历史；有索引时走 FTS5 + BM25 |
| `cmdwhy index status/rebuild/clear` | 查看/重建 SQLite 查询索引 |
| `cmdwhy digest --random 2` | 随机回看几个会话 |
| `cmdwhy fix "git stauts"` | 输入纠错，给出可直接执行的正确命令 |
| `cmdwhy fix --last` | 检查上一条失败命令的输入 |
| `cmdwhy diagnose` / `--text "错误输出"` | 检索同类错误，给出你以前的修法和通用建议 |
| `cmdwhy repair graph / reject / accept` | 查看因果图，纠正“这条不是修复” |
| `cmdwhy kb` / `--signature PERM:dpkg-lock` / `--export` | 查看、检索、导出错误知识库 |
| `cmdwhy hook install [--shell fish]` | 管理 bash / zsh / fish hook |
| `cmdwhy run [--shell] -- 命令` | 包装执行，捕获 stderr 并即时诊断；--shell 支持管道/重定向 |
| `cmdwhy do [--dry-run] [--yes]` | 根据最近命令和环境推断下一步，可执行安全步骤 |
| `cmdwhy mode suggest/auto/off` | 自动完成开关 |
| `cmdwhy mode autocorrect on/off` | cw run 失败时自动改正输入 |
| `cmdwhy doctor` | 自检数据目录、来源、hook、Git、知识库 |
| `cmdwhy config --set idle_gap 600` | 查看/修改配置 |
| `cmdwhy completion bash --install` | 安装 bash/zsh 补全 |
| `cmdwhy guide` / `cmdwhy version` | 命令地图 / 版本信息 |
| `cw run --fix --yes -- 命令` | 失败后给出修正，自动执行安全的修正命令 |

全局参数：`--home DIR`（数据目录）、`--json`、`--no-color`。

完整命令地图：`cmdwhy guide`；每个命令的参数、JSON 结构和示例见 **[docs/COMMANDS.md](docs/COMMANDS.md)**。

## 三个真实片段

### 1. 一次权限失败 + sudo 重试

```text
#18  11:40:00  $ apt install jq
结果    ✗ 失败（1）
置信度  高（依据：退出码/错误原文）
意图    安装系统包
任务    Ubuntu 软件包管理 · 排查（任务判断 高）
目标    在 Ubuntu 上安装/升级需要的软件包
目的    尝试安装系统包；因 PERM:dpkg-lock 失败，成为当前任务的卡点
错误    PERM:dpkg-lock  E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)
环境    ~/work/api · api · git:main · venv:.venv · Ubuntu 24.04
历史编号  518（cmdwhy explain 518 可直接定位）
推断    在 api 项目里安装系统包，但执行失败了；你随后用 sudo apt install jq -y 继续处理。
建议    包管理命令前加 sudo；若提示 lock 被占用，先 ps aux | grep -E 'apt|dpkg' 确认没有其他安装在进行。
更正    sudo apt install jq
后续    #19 sudo apt install jq -y  ✓ 成功（0）
```

### 2. 一个端口占用修复链

```text
#23  11:52:00  $ npm run dev
       ✗ 失败（1）  意图：运行 npm 脚本
       报错  PORT:3000  Error: listen EADDRINUSE: address already in use :::3000
       修复链  kill 4242  ✓ 已验证
  #24  11:53:00  $ ss -ltnp | grep 3000
       ✓ 成功（0）  查看端口/连接
       动机  排查 #23 的报错
  #26  11:55:00  $ kill 4242
       ✓ 成功（0）  结束占用端口的进程
       动机  修复 #23 的报错
  #27  11:56:00  $ npm run dev
       ✓ 成功（0）  运行 npm 脚本
```

### 3. 输入错误自动纠正

```bash
$ cmdwhy fix "git stauts"

命令输入检查  git stauts

  1. git status   可信度 高
     · git status
     · git 的合法子命令
     · 字母顺序颠倒
     · 你用过 9 次

建议执行： git status
```

更主动的用法：

```bash
$ cw run --fix --yes -- git stauts
git: 'stauts' is not a git command. See 'git --help'.
...
[错误诊断] CMD_NOT_FOUND:stauts
  ...
  针对这条输入，可能是
    1. git status
最可能改成： git status
cmdwhy: 自动执行修正： git status
On branch master
...
```

完整的样例输出在 `examples/` 目录：

- `examples/sample_timeline.txt`：S2 会话逐条注解
- `examples/sample_history.txt`：带编号的命令列表（含重复命令）
- `examples/sample_plan.txt`：根据上下文推断出的下一步计划
- `examples/sample_search.txt`：关键词搜索结果的编号与上下文
- `examples/sample_summary.txt`：按会话总结的概览
- `examples/sample_explain.txt`：三条命令的完整解释
- `examples/sample_report.md`：四段式 Markdown 报告
- `examples/demo_history.jsonl`：演示数据，可以直接 `cmdwhy ingest --file examples/demo_history.jsonl`
- `examples/demo_history_output.txt`：模拟 `history` 输出的编号格式，可以直接 `cmdwhy analyze examples/demo_history_output.txt` 或 `cmdwhy ingest --file ...`

## 工作流程

```text
bash / zsh / fish 历史          hook 记录（退出码、cwd、stderr、发行版）
        \                               /
         \                             /
          +---- 解析 / 去重 / 脱敏 ----+
                         |
              会话切分（空闲 > 30 分钟）
                         |
       环境指纹   错误签名   命令角色   意图分类
                         |
             修复链：失败 → 排查/修改 → 重跑 → 是否成功
                         |
       知识库（错误签名 → 你验证过的修复步骤）
                         |
        终端报告 / Markdown / JSON / 即时诊断 / 输入纠正
```

### 错误签名

错误原文会先归一成稳定签名，去掉路径、数字、时间、引号内容，避免“同一个错换了个 PID 就认不出来”：

| 签名 | 触发 |
| --- | --- |
| `PERM:dpkg-lock` | apt/dpkg 锁文件 Permission denied |
| `PERM:exec` | `./script` 没有执行权限（126） |
| `PERM:docker` / `DOCKER` | docker.sock 权限不足 |
| `CMD_NOT_FOUND:pytest` | command not found（127） |
| `MODULE:flask` | ModuleNotFoundError |
| `PIP668` | externally-managed-environment |
| `PORT:3000` | EADDRINUSE |
| `GIT_REJECT:fetch-first` | push 被拒（non-fast-forward） |
| `LOCK:dpkg` | 包管理器锁被占用 |
| `DISK:space` / `KILLED:oom` | 磁盘满 / OOM |
| `GIT_AUTH:http` / `SSH:publickey` | 远程认证 / SSH 公钥失败 |
| `DB:postgres` / `DB:mysql` | 数据库连接、权限或库表错误 |
| `TEST_FAIL:pytest` / `DEPENDENCY:npm` | 测试失败 / 依赖冲突 |
| `YAML` / `JSON_DECODE` / `TLS:certificate` | 配置解析 / 证书校验 |
| `READONLY` / `K8S:pod` | 只读文件系统 / Pod 异常 |
| `GO:module` / `RUST:compile` / `JAVA:version` | 多语言构建失败 |

### 修复链与验证

不是“下一条命令 = 修复”。cmdwhy 会：

1. 在后续最多 8 条命令里找**同一条命令的重跑**（忽略 sudo、参数、拼写小差异）；
2. 把中间真正改变环境的命令（安装、chmod、kill、mkdir、venv、git pull…）记为修复步骤；
3. 如果重跑退出码为 0 → **已验证**；没有退出码 → 只写“重跑（未记录退出码）”，不假装验证；
4. 排查类只读命令（`ss`、`lsof`、`journalctl`、`git diff`）不算修复步骤，但会进入“动机”说明。

### 置信度

| 级别 | 依据 |
| --- | --- |
| 高 | 有真实退出码和 stderr，错误类别明确 |
| 中 | 只有退出码，或修复动作明确但无重跑确认 |
| 低 | 纯上下文推断（旧历史没有退出码） |

所有“推测失败”在时间线上都带 `?` 前缀，不混进已确认错误。

## 纠正修复链（“这条不是修复”）

修复链是启发式推断，可能把“并行做别的事”误认为修复。现在可以人工纠正：

    cmdwhy repair graph              # 失败 → 修复动作 → 验证 的因果图
    cmdwhy repair reject '#19'       # 第 19 条不是对上一条失败的修复
    cmdwhy repair accept '#19'       # 确认这条修复链成立
    cmdwhy repair list               # 列出已确认/否定的链

纠正按失败事件的稳定 ID 持久化到 repairs.json；之后 explain、报告、知识库学习都会尊重它。

## 错误知识库：下次别再踩同一个坑

每次 `ingest` 都会把“这个错误签名 → 当时真正让它变好的命令”沉淀到 `knowledge.json`。下次遇到同签名错误：

```bash
$ cmdwhy diagnose --text "error: externally-managed-environment"
错误诊断  PIP668
  这是什么  PEP 668：系统 Python 受保护
  为什么  Ubuntu 23.04+ 禁止 pip 直接装进系统 Python，避免破坏 apt 管理的包，应改用虚拟环境或 pipx。
  下一步  python3 -m venv .venv && source .venv/bin/activate，然后 pip install；命令行工具用 pipx。
  要避免  不要习惯性加 --break-system-packages。
```

如果知识库里有你验证过的修法，会优先显示：

```text
你以前这样修好过（按有效次数排序）
  1. sudo apt install python3-venv -y → python3 -m venv .venv → source .venv/bin/activate
     有效 2 次 · 最近 2026-11-17
```

- 只从**验证过**或**高/中置信度**的修复链学习；
- 同签名精确检索优先，其次按类别兜底；签名相同但路径/PID 不同的错误，会再做一次文本相似度匹配；
- `cmdwhy kb --export` 导出，`cmdwhy kb --clear` 清空。

## 输入纠错引擎

`cmdwhy fix` 和 `cw run --fix` 不是简单“编辑距离最近”：

1. 候选必须真实存在：PATH 里的可执行文件、shell 内建、合法子命令，或你**成功用过**的历史命令；
2. 距离最多 2，且通常要求首字母相同；
3. 加分项：你用过很多次、下一个词正好是候选的子命令、键盘相邻键误触、字母顺序颠倒；
4. 危险命令（`rm`、`dd`、`mkfs`、`shutdown`、`chmod -R`……）默认降权；
5. 权限不足且命令本身需要 root 时，直接建议 `sudo <原命令>`；
6. 找不到相近命令时，不硬猜，提示“可能没安装”，并给出 `command-not-found` 的用法。

```text
$ cmdwhy fix "gti status"
  1. git status   可信度 高
     · 字母顺序颠倒
     · 系统里存在这个命令
     · 后面的 status 是它的合法子命令
```

## 数据、隐私与安全

- **全部本地**：不联网、不上传、不调用外部 API。
- **落盘前脱敏**：命令里的 `--password=`、`--token=`、`export *SECRET=`、URL 里的账号密码、GitHub token、AWS key、SSH 公钥、40 位以上混合 token 会被替换成 `***`，hook 记录在写入 events.jsonl 之前就会处理。
- **存储位置**：`$CMDWHY_HOME`，默认 `~/.local/share/cmdwhy`；文件是 `events.jsonl`（追加写）、`knowledge.json`、`config.json`、`repairs.json`、`cache.db`（解析缓存）、`index.db`（FTS5 查询索引）。
- **解析缓存**：历史文件按 mtime/size + redact 配置缓存到 `cache.db`，缓存内容已脱敏；文件改动会自动失效，删掉 `cache.db` 也安全。
- **危险命令不自动执行**：`cw run --yes` 只执行通过安全检查的修正命令；含 `<包名>` 这种占位符、或命中危险规则的建议一律拒绝。
- **可卸载**：`cmdwhy hook uninstall` 移除 rc 里的配置；删掉数据目录即可清除全部记录。

自定义事件也可以直接喂给它（每行一个 JSON）：

```json
{"ts": 1763341920.0, "cmd": "sudo apt install jq -y", "exit_code": 0, "cwd": "/home/ubuntu/work/api", "shell": "bash", "distro": "Ubuntu 24.04", "source": "hook"}
```

## 配置

`cmdwhy init` 后可以在 `config.json` 里调整：

```json
{
  "sources": ["/home/ubuntu/.bash_history", "/home/ubuntu/.zsh_history"],
  "idle_gap": 1800,
  "window": 8,
  "context_window": 20,
  "redact": true,
  "color": "auto",
  "learn": true,
  "autopilot": "suggest",
  "autocorrect": false,
  "max_events": 5000,
  "ignore_prefixes": ["cmdwhy"]
}
```

- `idle_gap`：超过多少秒切分会话；
- `window`：向后找修复动作/重跑的最大条数；
- `context_window`：判断“当时在干什么”时前后各看多少条，默认 20；
- `max_events`：最多分析多少条（默认取最近 5000 条）；
- `learn`：设为 `false` 时 `ingest` 不写知识库（仍可手动 `cmdwhy kb --learn`）；
- `autopilot`：`off` / `suggest` / `auto`；auto 只跑低风险，中风险需 `--yes`；
- `autocorrect`：`cw run` 失败时是否自动执行高可信修正；
- `ignore_prefixes`：不记录/不分析的命令前缀。

## 局限（先说实话）

1. **还没在 Ubuntu 桌面图形终端里做真人输入验收**；WSL 和 VMware 的 bash/zsh/fish 已通过伪终端实测。旧 bash 历史没有退出码时，失败只能靠上下文推断，置信度是低/中。
2. **hook 覆盖 bash / zsh / fish**；其他 shell 仍可把事件按 JSON 写进 `events.jsonl`。
3. **历史里的 cwd 可能已经不存在**，这时项目类型、Git 分支、venv 只能靠 hook 当时记录或留空，不会瞎猜。
4. **不拦截命令输出**。想拿到精确 stderr，用 `cw run -- 命令` 或 `cmdwhy run -- 命令`；它会把 stderr 尾部记入事件并立即诊断。
5. **修复链是启发式**，不是因果证明。它给出的是“最可能”的解释，并明确标出置信度和验证状态。

### Ubuntu 原生环境验证

已在两种 Ubuntu 24.04 原生环境中跑通：

- **WSL2**：Ubuntu 24.04.3 LTS，Python 3.12.3，bash 5.2.21，git 2.43.0；
- **VMware Workstation**：Ubuntu 24.04.5 LTS，Python 3.12.3，bash 5.2.21，git 2.43.0。

WSL2 上 **197 个测试全部通过**；VMware 0.4.0 上最近一次 **196 个测试通过**（14.9s；197 的短命令测试还没在 VM 重跑）。WSL 里还实测了 zsh 5.9、fish 3.7 的 hook，连续两次相同的 `git status` 分别记录；5000 条历史第二次加载从 0.090s 降到 0.036s（SQLite 解析缓存）。

完整记录见 **[docs/VALIDATION.md](docs/VALIDATION.md)**。
真实历史方面：当前机器能找到的真实用户历史是 **494 条**（Windows Git Bash 94 + PowerShell 401 + VM 12），没有可用的 1000+ 条用户历史，所以没有伪造。另用 1600 条**真实执行事件**（实际运行命令并记录退出码/cwd）做了规模压测：WSL 2 秒、VM 1 秒，27 个会话、53 次失败、4 条修复链，SQLite 索引 1600 条。


仍未覆盖：Ubuntu 桌面图形终端里的真人输入、可用的**用户本人**上千条历史（当前只找到 494 条真实历史）、Ubuntu 20.04 回归。GitHub Actions 已实际跑过（Ubuntu 22.04/24.04 × Python 3.8–3.12、Debian 12、Arch、Fedora、AlmaLinux 9、Alpine + shellcheck，全部通过）。


## 开发与测试

```bash
python3 -m unittest discover -s tests -v   # 197 个测试
make demo                                  # 内置演示
python3 -m compileall -q cmdwhy tests      # 语法检查
```

CI（.github/workflows/ci.yml）：Ubuntu 22.04/24.04 × Python 3.8–3.12 矩阵，跑 coverage + unittest；另有 shellcheck 任务检查 bash hook、zsh/fish 语法和 install.sh。

目录：

```text
cmdwhy/
├── cmdwhy/
│   ├── cli.py         命令行入口、所有子命令
│   ├── analyze.py     分析引擎：会话、失败推断、修复链、动机、统计
│   ├── sources.py     bash/zsh/fish/JSONL 解析、去重、脱敏
│   ├── env.py         工作环境指纹（项目/Git/venv/发行版/容器/SSH/WSL/包管理器）
│   ├── system.py      Debian/Arch/Fedora/SUSE/Alpine 包管理器适配
│   ├── errors.py      错误分类与稳定签名
│   ├── intent.py      命令意图、角色（只读/改动/运行）、修复意图
│   ├── typo.py        纠错引擎（Damerau-Levenshtein + 真实命令 + 历史成功证据）
│   ├── knowledge.py   错误签名 → 修复步骤知识库
│   ├── hook.py        bash/zsh/fish hook 生成与安装
│   ├── runner.py      cw run：捕获执行、即时诊断、安全自动修正
│   ├── report.py      终端/Markdown/JSON 渲染
│   ├── hints.py       各错误类别的 Ubuntu 处置建议
│   ├── safety.py      危险命令识别
│   ├── redact.py      脱敏
│   ├── demo_data.py   内置演示数据
│   ├── context.py     前后窗口任务推断与单条命令目的
│   ├── planner.py     根据上下文和环境推断下一步（可自动执行）
│   ├── search.py      关键词/正则/OR/BM25/错误/时间/项目搜索
│   ├── index_db.py    SQLite + FTS5 查询索引
│   ├── causal.py      修复链 logistic 因果概率
│   ├── cache.py       SQLite 解析缓存（脱敏、按 mtime/size 失效）
│   ├── repairs.py     修复链人工确认/否定
│   ├── resolve.py     history 编号 / 分析序号 / 稳定 ID 解析
│   ├── guide.py       命令地图与 bash/zsh 补全脚本
│   └── util.py        时间/路径/距离/颜色等工具
├── docs/COMMANDS.md   完整命令参考
├── docs/VALIDATION.md Ubuntu WSL / VMware 验证记录
├── examples/          样例输出与演示数据
├── tests/             197 个单元 + 端到端 CLI 测试
├── install.sh         Ubuntu 一键安装
├── pyproject.toml
└── Makefile
```

## 常见问题

**它和 `history` / `fc` / atuin 有什么区别？**
它们解决“找到/同步/搜索历史”；cmdwhy 解决“解释历史”：环境、动机、报错、修复链、同类错误复用、输入纠错。可以一起用。

**会拖慢 shell 吗？**
hook 在每次提示符前把一条 JSON 追加到文件，命令在后台执行；正常交互感觉不到。

**会不会误判我的成功命令？**
有退出码时不会。没有退出码时才可能推测失败，且会标 `?` 和低置信度。你可以在 `config.json` 里设置 `learn: false` 禁止从推测中学习。

**为什么建议有时候是 `sudo apt install <包名>`？**
因为只凭命令名无法确定 Ubuntu 包名，硬猜一个包名更危险。可以用 `command-not-found <命令>` 或 `apt search` 确认；`cmdwhy diagnose` 也会优先给你历史里真实用过的包名。

**怎么彻底删除？**
`cmdwhy hook uninstall`，然后删除 `~/.local/share/cmdwhy` 以及 rc 文件里残留的 `# >>> cmdwhy >>>` 块。

## License

MIT
