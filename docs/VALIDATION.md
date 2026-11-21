# Ubuntu 验证记录

日期：2026-11-18

本次在两种真实 Ubuntu 24.04 环境里跑过 cmdwhy，均为原生 Linux 用户态，不使用 Windows 兼容层。

| 环境 | WSL2 | VMware Workstation |
| --- | --- | --- |
| 发行版 | Ubuntu 24.04.3 LTS | Ubuntu 24.04.5 LTS |
| 内核 | 6.18.40.1-microsoft-standard-WSL2 | 6.8.0-147-generic |
| Python | 3.12.3 | 3.12.3 |
| bash | 5.2.21 | 5.2.21 |
| git | 2.43.0 | 2.43.0 |
| zsh / fish | zsh 5.9 / fish 3.7 | 未安装 |
| 测试 | 211 passed | 210 passed |
| 用时 | 53.9s | 22.8s |

## 验证过的功能

- python3 -m unittest discover -s tests：211 个测试全部通过（VM 上最近一次 210 个）；
- cmdwhy demo：时间线、任务上下文、history 编号显示正常；
- cmdwhy fix "git stauts"：干净环境下判定为高可信度，建议 git status；
- cmdwhy ingest + cmdwhy history --duplicates --all：重复的 git status 分别编号；
- cmdwhy explain e<稳定ID>：新增历史、seq 变化后仍指向同一条命令；
- cmdwhy explain 503：落到第二次 git status，历史编号正确；
- cmdwhy mode autocorrect on + cmdwhy run -- git stauts：自动执行 git status，退出码 0；
- 交互式 bash + hook（VMware 虚拟机）：
    - 共记录 6 条事件；
    - git stauts 退出码 1；
    - 连续两次 git status 分别记录为 hist=3、hist=4；
    - --duplicates 能显示“第 1/2 次、第 2/2 次”；
- 交互式 zsh 5.9 + fish 3.7 hook（WSL）：
    - 各记录 5 条事件；
    - git stauts 退出码 1；
    - 连续两次 git status 分别记录；
- 自动执行边界：sudo/apt/systemctl 在计划里标为高风险，auto 和 --yes 都不会选中；
- bash 5.2 的 PROMPT_COMMAND 数组形式保留原有内容并追加记录函数；
- 跨来源重复：同一 history 编号的 hook 事件与 history 输出只保留信息更全的一条；
- 解析缓存：5000 条历史首次 0.090s，第二次 0.036s（SQLite，mtime/size 失效）；
- 错误识别扩展到 SSH/DB/TLS/K8S/TEST_FAIL/DEPENDENCY/YAML/JSON/GO/RUST/JAVA 等；
- 环境识别新增 PHP、.NET、Terraform、Kubernetes、WSL、包管理器；
- 本地通过 bash -n、shellcheck -S error、zsh -n、fish -n；coverage 基线约 55%。
- cmdwhy search --error PORT --since 7d / --regex / --any / --sort relevance：错误、时间、正则、OR、相关度搜索；
- cmdwhy summary --session S2 / --today / --week / --project api：会话与聚合概要；
- cmdwhy timeline --page 1 --page-size 20：时间线分页；
- cmdwhy repair graph / reject / accept：修复链因果图与人工纠正；
- cmdwhy do --from 1 --dry-run：从指定命令推断下一步；
- cmdwhy mode、cmdwhy doctor：状态与自检正常。

VMware 虚拟机里的 hook 交互式日志：

    hist=1 exit=0 cmd=cd /tmp/vm-hookrepo
    hist=2 exit=1 cmd=git stauts
    hist=3 exit=0 cmd=git status
    hist=4 exit=0 cmd=git status
    hist=5 exit=0 cmd=ls
    hist=6 exit=0 cmd=history

## 本轮验证中发现并修复的问题

1. 干净环境里合法子命令纠错只有“低”可信度。
   改为：一位编辑距离且目标为合法子命令时，判定为高可信度。
2. 未验证的知识库修法被显示成“你以前这样修好过”。
   现在只把 verified > 0 的修法放进“修好过”列表；其余明确标为“未验证，仅供参考”。
3. 命令 ID 漂移：新增稳定 ID `e...`，修复链/报告引用写成 `#seq[eUID]`，`explain` 支持稳定 ID。
4. 跨来源重复：同 history 编号、同命令的 hook 与 history 事件合并。
5. 自动执行边界：auto 只跑低风险；中风险需 `--yes`；sudo/apt/systemctl 等高风险永不自动执行。
6. shell 覆盖：bash 兼容 PROMPT_COMMAND 数组；zsh 改用 preexec/precmd；新增 fish hook（fish_preexec/fish_prompt）。

## 真实历史与规模压测

当前环境里能找到的真实用户历史：

| 来源 | 行数/事件 |
| --- | --- |
| Windows Git Bash .bash_history | 94 条（过滤掉 Function Key 噪声） |
| PowerShell ConsoleHost_history | 401 行 / 真实命令 |
| VMware Ubuntu .bash_history | 12 条 |
| 合计 | 494 个事件 |

没有可用的 1000+ 条用户历史，所以没有把合成命令伪装成真实历史。
另外生成并实际执行了 1600 条真实命令事件（临时 git 仓库、真实退出码/cwd/stderr，不是用户历史）：

- WSL 分析耗时 2 秒，VMware 1 秒；
- 1600 事件 / 27 个会话 / 53 次失败 / 4 条修复链；
- SQLite 索引 634–659 KB，search 走 FTS5/BM25；
- PowerShell `& command` 前缀已归一化，避免把 280 条命令误记成 `&`。

## 跨发行版 CI

GitHub Actions 的 distro 任务在容器里跑了完整测试：

| 发行版 | 包管理器 | 结果 |
| --- | --- | --- |
| Debian 12 | apt | success |
| Arch Linux | pacman | success |
| Fedora latest | dnf | success |
| AlmaLinux 9 | dnf | success |
| Alpine latest | apk | success |

同一 run 里还有 Ubuntu 22.04/24.04 × Python 3.8–3.12 和 shellcheck，全部通过。

## 仍未覆盖

- Ubuntu 桌面图形终端里的真实交互（本次通过 script 伪终端验证 bash + hook）；
- 用户本人的上千条真实历史：当前只找到 494 条真实历史，没有伪造；另用 1600 条真实执行事件做了规模压测；
- 多人共用机器；
- Ubuntu 20.04 兼容性回归；22.04/24.04、Debian 12、Arch、Fedora、AlmaLinux 9、Alpine 已由 GitHub Actions（run 44875760103）覆盖并通过。

## 复现方式

    python3 -m unittest discover -s tests
    python3 -m cmdwhy demo
    python3 -m cmdwhy hook install
    exec bash -l

然后在交互式 shell 里执行几条命令，查看：

    cmdwhy history --duplicates
    cmdwhy explain <编号>
