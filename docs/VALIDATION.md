# Ubuntu 验证记录

日期：2026-11-17

本次在两种真实 Ubuntu 24.04 环境里跑过 cmdwhy，均为原生 Linux 用户态，不使用 Windows 兼容层。

| 环境 | WSL2 | VMware Workstation |
| --- | --- | --- |
| 发行版 | Ubuntu 24.04.3 LTS | Ubuntu 24.04.5 LTS |
| 内核 | 6.18.40.1-microsoft-standard-WSL2 | 6.8.0-147-generic |
| Python | 3.12.3 | 3.12.3 |
| bash | 5.2.21 | 5.2.21 |
| git | 2.43.0 | 2.43.0 |
| 测试 | 144 passed | 144 passed |
| 用时 | 25.8s | 7.2s |

## 验证过的功能

- python3 -m unittest discover -s tests：144 个测试全部通过；
- cmdwhy demo：时间线、任务上下文、history 编号显示正常；
- cmdwhy fix "git stauts"：干净环境下判定为高可信度，建议 git status；
- cmdwhy ingest + cmdwhy history --duplicates --all：重复的 git status 分别编号；
- cmdwhy explain 503：落到第二次 git status，历史编号正确；
- cmdwhy mode autocorrect on + cmdwhy run -- git stauts：自动执行 git status，退出码 0；
- 交互式 bash + hook（VMware 虚拟机）：
    - 共记录 6 条事件；
    - git stauts 退出码 1；
    - 连续两次 git status 分别记录为 hist=3、hist=4；
    - --duplicates 能显示“第 1/2 次、第 2/2 次”；
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

## 仍未覆盖

- Ubuntu 桌面图形终端里的真实交互（本次通过 script 伪终端验证 bash + hook）；
- zsh、fish 实机；
- 上千条真实历史、多人共用机器；
- Ubuntu 20.04 / 22.04 的兼容性回归。

## 复现方式

    python3 -m unittest discover -s tests
    python3 -m cmdwhy demo
    python3 -m cmdwhy hook install
    exec bash -l

然后在交互式 shell 里执行几条命令，查看：

    cmdwhy history --duplicates
    cmdwhy explain <编号>
