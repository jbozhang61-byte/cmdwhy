# cmdwhy 完整使用手册

版本：0.6.0  
适用：Debian / Ubuntu / Kali、Arch / Manjaro、Fedora / RHEL / CentOS / Rocky / Alma、openSUSE、Alpine  
数据：全部本地保存，不联网、不上传。

## 1. cmdwhy 是什么

shell 的 `history` 只记录“敲了什么”。cmdwhy 补上：

- 在什么环境：目录、项目、分支、venv、发行版、包管理器、容器、SSH、WSL、root；
- 为什么敲：任务、目标、阶段、命令角色、单条命令的目的；
- 错在哪、怎么好的：退出码、stderr、错误签名、修复链、是否验证；
- 以后怎么办：同类错误的历史修法、输入纠错、下一步计划；
- 怎么找：关键词、正则、OR、BM25、错误、时间、项目、会话；
- 怎么回顾：时间线、会话概要、今天/本周/项目汇总、报告、Markdown/JSON 导出。

## 2. 安装

### 方式一：不安装，直接跑

```bash
git clone https://github.com/jbozhang61-byte/cmdwhy
cd cmdwhy
python3 -m cmdwhy demo
```

要求 Python 3.8+，无第三方依赖。

### 方式二：安装成 cmdwhy / cw 命令

```bash
cd cmdwhy
bash install.sh
. .venv/bin/activate
cmdwhy --version
```

`install.sh` 会自动识别 apt / pacman / dnf / yum / zypper / apk，安装 Python、venv、pip、git，并建立 `.venv`。

安装后有两个命令：

- `cmdwhy`：分析、解释、搜索、报告、诊断、纠错；
- `cw`：包装执行器，例如 `cw run --fix --yes -- git stauts`。

## 3. 第一次使用

### 3.1 先看演示

```bash
cmdwhy demo
cmdwhy demo --explain 518
cmdwhy demo --limit 10 --no-report
```

演示数据不会写入你的真实历史。

### 3.2 初始化并导入旧历史

```bash
cmdwhy init
cmdwhy ingest
```

`ingest` 默认读取 `~/.bash_history`、`~/.zsh_history`、fish 历史，并学习错误→修复知识库。

也可以指定文件或管道：

```bash
history > /tmp/history.txt
cmdwhy ingest --file /tmp/history.txt

history | cmdwhy ingest --stdin
history | cmdwhy analyze --stdin
```

### 3.3 安装 hook

hook 让**新命令**带上真实退出码、cwd、stderr 和发行版。

```bash
cmdwhy hook install
# fish：
cmdwhy hook install --shell fish
# 只打印脚本，不改 rc：
cmdwhy hook install --print --shell bash

exec bash -l
```

检查：

```bash
cmdwhy hook status
cmdwhy doctor
```

### 3.4 确认能用

```bash
cmdwhy demo --explain 518
cmdwhy doctor
```

## 4. 最短命令

| 想做什么 | 最短写法 |
| --- | --- |
| 看第 518 条 | `cmdwhy 518` |
| 看最近一条 | `cmdwhy last` |
| 用稳定 ID | `cmdwhy e1a2b3c4` |
| 时间线 | `cmdwhy tl -n 20` |
| 搜索 | `cmdwhy s flask` / `cmdwhy find PORT` |
| 会话总结 | `cmdwhy sum` |
| 今天 / 本周 | `cmdwhy today` / `cmdwhy week` |
| 检查上一条失败 | `cmdwhy fix` |
| 推断下一步 | `cmdwhy next` |
| 编号列表 | `cmdwhy h -n 50` |
| 统计 | `cmdwhy st` |
| 命令地图 | `cmdwhy guide` |

完整短别名：

- `tl` = timeline
- `ex` / `why` = explain
- `s` / `find` = search
- `sum` = summary
- `h` / `hist` = history
- `next` = do
- `st` = stats
- `today` / `week` = summary --today / --week

数字目标 `518`、`#18`、`h518`、`e1a2b3c4`、`uid:e1a2b3c4`、`last` 会自动走 `explain`。

## 5. 五个核心工作流

### 5.1 回顾刚才在干什么

```bash
cmdwhy tl -n 30
cmdwhy tl --page 2 --page-size 20
cmdwhy sum --today
cmdwhy today
cmdwhy week
```

时间线每条显示：

- 命令、状态、退出码；
- 意图、目的、角色；
- 环境、项目、分支、venv；
- 报错签名、修复链、验证状态；
- 环境改变。

会话概要和今天/本周汇总适合快速复盘。

### 5.2 解释某条命令

```bash
cmdwhy 518
cmdwhy '#18'
cmdwhy last
cmdwhy e1a2b3c4
cmdwhy explain 518 --context 40
cmdwhy explain 518 --json
```

输出包括：

- 作用 / 任务 / 目标 / 阶段 / 目的；
- 环境；
- 错误 / 修复链 / 置信度 / 因果概率；
- 后续命令；
- 依据和上下文摘要。

`#18` 是当前顺序，新增历史会变；`e1a2b3c4` 是稳定 ID，推荐长期引用。

### 5.3 多条命令一起看（50–60 条）

```bash
cmdwhy block 50-60
cmdwhy block '#50-60'
cmdwhy block h518-560
cmdwhy block --last 60
cmdwhy block --last 60 --json
```

区别：

- `cmdwhy explain 518`：解释**一条**；
- `cmdwhy explain 518-520`：逐条解释**一小段**；
- `cmdwhy block 50-60`：把这一整段当成一个**阶段**，给出总体任务、阶段变化、错误/修复/验证、角色分布、环境变化，再附逐条目的。

默认没有参数时分析最近 50 条；一次最多 240 条。`--window` 可以改上下文窗口。

典型输出：

```text
命令段  #50–#60  11 条 · 2 个会话 · 09:12–09:40
环境    ~/work/api · api · git:main · venv:.venv · Ubuntu 24.04 · apt
任务    Python 依赖与环境×7 · Git 同步与提交×4
阶段    准备 → 排查 → 修复 → 验证
结果    成功 7 · 失败 3 · 修复动作 3，验证 2
错误    MODULE:flask×2 · PORT:3000×1
角色    改变环境×5 · 只读排查×4 · 运行/验证×2
环境变化 进入 venv .venv；cd ~/work/api/web
分组    [Python 依赖与环境] #50–#56 ...
命令    #50 ... 目的：...
```

### 5.4 命令打错了 / 又遇到熟悉报错

```bash
cmdwhy fix
cmdwhy fix "git stauts"
cmdwhy fix "gti status"
cmdwhy fix --last --top 5

cmdwhy diagnose
cmdwhy diagnose --text "permission denied"
cmdwhy diagnose --signature PERM:dpkg-lock
cmdwhy diagnose --file err.log
```

`fix` 会看 PATH、合法子命令、你以前成功用过的命令；`diagnose` 会优先给出你验证过的同类修法。

### 5.5 直接执行并自动修正

```bash
cw run --fix --yes --retry -- ./deploy.sh
cmdwhy run --fix --yes --retry -- git stauts
cmdwhy run --shell -- "npm run dev | tee dev.log"
```

它会捕获 stdout/stderr，失败后诊断并按需修正。

### 5.6 让工具推断下一步

```bash
cmdwhy next
cmdwhy do --dry-run
cmdwhy do --yes
cmdwhy do --from 518 --dry-run
```

安全边界：

- `auto` 只自动执行**低风险**步骤；
- 中风险写操作（venv、pip/npm 安装、chmod、git pull/push）需要 `--yes`；
- sudo、apt/systemctl、rm/dd/mkfs 等高风险永不自动执行；
- 每步 120 秒超时，失败即停。

## 6. 搜索与索引

```bash
cmdwhy s flask
cmdwhy s --error PORT --since 7d
cmdwhy s --status fail --project api
cmdwhy s --regex 'PORT|EADDRINUSE'
cmdwhy s --any npm pnpm yarn
cmdwhy s git push --sort relevance
cmdwhy s --session S2 --oldest
cmdwhy s --since today --until "2026-11-17 18:00"
```

- 默认关键词 AND；`--any` 是 OR；`--regex` 是正则；
- `--sort relevance` 用 BM25；
- 有索引时走 SQLite FTS5，未建索引/正则/中文查询回退 Python BM25；
- 结果保留 history 编号和稳定 ID。

索引：

```bash
cmdwhy index status
cmdwhy index rebuild
cmdwhy index clear
```

`ingest` / `search` 会自动更新索引。索引签名包含来源 mtime/size、store、labels 和配置；不一致会自动重建。

## 7. 人工纠正

### 7.1 纠正任务 / 目标 / 目的

```bash
cmdwhy label 518 --task "部署 API" --goal "发布新版本" --purpose "发布并确认回滚点"
cmdwhy label 518 --clear
cmdwhy label --list
```

按稳定 ID 写入 `labels.json`；之后 explain、timeline、summary、search 都优先使用人工标签。

### 7.2 纠正修复链

```bash
cmdwhy repair graph
cmdwhy repair reject '#19'
cmdwhy repair accept '#19'
cmdwhy repair list
```

`repair graph` 显示失败 → 修复动作 → 验证，以及 logistic 因果概率。人工 reject 直接置 0，accept 置 1。

## 8. 报告与导出

```bash
cmdwhy stats
cmdwhy report
cmdwhy report --sections errors,changes --random 2 --seed 7
cmdwhy report --md report.md
cmdwhy export --format json -o dump.json
cmdwhy export --format md -o report.md
cmdwhy export --format timeline -o timeline.txt
cmdwhy export --format report -o report.txt
```

`report` 是四段式：报错 / 改变 / 添加 / 随机；`stats` 包含错误率、意图分布、修复耗时、sudo 比例。

## 9. 上下文、环境、角色、目的

窗口默认前后各 20 条，限制在同一会话、同一项目内。

评分使用：

1. 窗口内错误签名；
2. 命令家族和关键 token；
3. 当时环境：cwd、项目类型、分支、venv、发行版、包管理器、容器/SSH/WSL/root；
4. 命令角色：只读排查 / 改变环境 / 运行验证；
5. 修复链：准备、排查、修复、验证。

示例：

```text
作用    改变环境 · 排查
任务    系统软件包管理 · 排查（任务判断 高）
目标    在 Ubuntu 24.04 上安装/升级/清理需要的软件包
目的    在 ~/work/api · api · git:main · venv:.venv · Ubuntu 24.04 · apt 里
        尝试安装系统包；因 PERM:dpkg-lock 失败，成为当前任务的卡点
环境    ~/work/api · api · git:main · venv:.venv · Ubuntu 24.04 · apt
上下文  #18 报 PERM:dpkg-lock；#19 验证成功；
        环境变化：cd …/work/api/web；离开 venv .venv
```

旧历史没有 cwd/发行版时环境会显示未知，不会拿当前目录冒充。

调整窗口：

```bash
cmdwhy explain 518 --context 40
cmdwhy config --set context_window 30
```

## 10. 数据、隐私与文件

数据目录：

```bash
~/.local/share/cmdwhy
# 或
echo $CMDWHY_HOME
```

| 文件 | 作用 |
| --- | --- |
| `events.jsonl` | 事件追加写 |
| `config.json` | 配置 |
| `knowledge.json` | 错误签名 → 修复步骤 |
| `repairs.json` | 修复链人工否定/确认 |
| `labels.json` | 任务/目标/目的人工标签 |
| `cache.db` | SQLite 解析缓存 |
| `index.db` | SQLite FTS5 查询索引 |

- 落盘前脱敏：`--password=`、`--token=`、`export *SECRET=`、URL 账号密码、GitHub token、AWS key、SSH 公钥等替换为 `***`；
- 缓存内容已脱敏；
- 删除数据目录即可清除全部记录；
- `CMDWHY_NO_CACHE=1` 可关闭解析缓存。

## 11. Hook 细节

支持 bash / zsh / fish：

```bash
cmdwhy hook install
cmdwhy hook install --shell bash
cmdwhy hook install --shell zsh
cmdwhy hook install --shell fish
cmdwhy hook install --rc /tmp/rc --print
cmdwhy hook status
cmdwhy hook uninstall
```

- bash 用 `PROMPT_COMMAND`（兼容 5.1+ 数组）；
- zsh 用 `preexec` + `precmd`；
- fish 用 `fish_preexec` + `fish_prompt`；
- hook 不改变命令结果，只旁路记录；
- 连续相同的命令会分别记录。

## 12. 支持的发行版

| 发行版 | 包管理器 | 说明 |
| --- | --- | --- |
| Ubuntu / Debian / Kali / Mint / Pop | apt | 主要环境，hook 实测 |
| Arch / Manjaro / EndeavourOS | pacman | 生成 pacman 安装/搜索 |
| Fedora / RHEL / CentOS / Rocky / Alma | dnf / yum | dnf provides |
| openSUSE Leap / Tumbleweed | zypper | zypper 搜索 |
| Alpine | apk | install.sh 会装 bash |

命令缺失、venv 安装、包搜索会按当前包管理器生成，不写死 apt。

## 13. 常见问题

### 没有历史 / 记录为空

```bash
cmdwhy hook status
cmdwhy ingest
cmdwhy doctor
echo $CMDWHY_HOME
```

### hook 安装了但没记录

- 需要新开终端或 `source` 对应 rc；
- 确认 `cmdwhy` 在 PATH；
- 看 `cmdwhy hook status`，必要时 `cmdwhy hook install --print` 手动 source；
- fish 需要 `--shell fish`。

### 重复事件

- hook 与 history 输出同 history 编号、同命令会合并；
- 同一命令的不同执行保留，用 `history --duplicates` 看次数；
- 稳定 ID 可以精确定位。

### cache.db / index.db 损坏

会自动删除重建；也可以：

```bash
cmdwhy index rebuild
rm -f ~/.local/share/cmdwhy/cache.db ~/.local/share/cmdwhy/index.db
```

### 标签 / 任务是错的

```bash
cmdwhy label 518 --task "..." --purpose "..."
```

### 太慢

- 大历史首次分析会慢；后续走 cache/index；
- `timeline --limit` / `--page` 分页；
- `search` 优先走索引；
- 5 万条以上建议定期清理或拆分数据目录。

## 14. 命令速查

```text
demo                    内置演示
init                    初始化
ingest                  导入历史并学习知识库
analyze                 临时分析文件/stdin
timeline / tl           时间线；--page/--page-size
explain / ex / why      解释；支持 518 / #18 / eID / last
block / blk / seg       多条命令阶段分析；50-60 / --last 60
summary / sum / today   会话/今天/本周/项目汇总
search / s / find       搜索；--regex/--any/--sort relevance
history / h             编号列表；--duplicates/--grep
fix                     输入纠错；默认查上一条失败
diagnose                同类错误检索
repair                  修复链 graph/reject/accept/list
label                   任务/目标/目的人工标注
kb                      知识库
run                     cw run 的完整写法
do / next               下一步计划
mode                    autopilot/autocorrect 开关
hook                    bash/zsh/fish hook
index                   SQLite 索引 status/rebuild/clear
doctor                  自检
stats / report / export 统计、报告、导出
config                  配置
completion              bash/zsh 补全
guide / version         命令地图 / 版本
```

## 15. 安全边界

- 默认 `suggest`，不自动执行；
- `auto` 只跑低风险；
- 中风险需 `--yes`；
- 高风险永不自动执行；
- 含 `<包名>` 占位符的建议不执行；
- `cd`、`source`、`export` 不会自动执行；
- 自动修正只做低风险且身份明确的动作；sudo 修正必须显式 `--yes`。

## 16. 开发与测试

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q cmdwhy tests
coverage run --source=cmdwhy -m unittest discover -s tests
coverage report -m
```

CI：Ubuntu 22.04/24.04 × Python 3.8–3.12，Debian 12、Arch、Fedora、AlmaLinux 9、Alpine，加 shellcheck。

## 17. 项目地址

https://github.com/jbozhang61-byte/cmdwhy

命令参考：docs/COMMANDS.md  
验证记录：docs/VALIDATION.md
