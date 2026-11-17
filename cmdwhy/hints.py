"""按错误类别给出 Ubuntu 上最常见、最靠谱的处置建议。"""

from __future__ import annotations

HINTS = {
    "PERM": {
        "title": "权限不足",
        "why": "该操作需要更高的文件/设备权限，当前用户没有。",
        "next": "确认这是系统级操作后加 sudo 重试；若只是脚本不能执行，用 chmod +x <文件>。",
        "avoid": "不要用 chmod -R 777 绕过，也不要长期以 root 跑日常命令。",
    },
    "PERM:dpkg-lock": {
        "title": "apt 锁文件被占用 / 缺少 root",
        "why": "dpkg 的锁文件属于 root，普通用户无法写入；也可能是另一个 apt 进程正在运行。",
        "next": "包管理命令前加 sudo；若提示 lock 被占用，先 ps aux | grep -E 'apt|dpkg' 确认没有其他安装在进行。",
        "avoid": "不要 rm /var/lib/dpkg/lock*，那会破坏 dpkg 状态。",
    },
    "PERM:exec": {
        "title": "脚本缺少执行权限",
        "why": "文件没有 x 位，内核拒绝执行。",
        "next": "chmod +x <脚本>，或显式用 bash <脚本> 运行。",
        "avoid": "不要 chmod 777，+x 就够了。",
    },
    "PERM:docker": {
        "title": "无权访问 Docker 守护进程",
        "why": "当前用户不在 docker 组，docker.sock 默认只允许 root 访问。",
        "next": "临时：sudo docker ...；长期：sudo usermod -aG docker $USER 后重新登录。",
        "avoid": "把 docker 组当普通用户组看待——它等价于 root 权限。",
    },
    "CMD_NOT_FOUND": {
        "title": "命令不存在或拼写错误",
        "why": "shell 在 PATH 里找不到这个命令，通常是没安装、拼错，或 PATH 没生效。",
        "next": "先确认拼写；Ubuntu 上可用 sudo apt install <包名>，或用 command-not-found 查询包名。",
        "avoid": "不要盲目复制网上的安装脚本；先 apt search 确认包名。",
    },
    "NOT_FOUND": {
        "title": "文件或目录不存在",
        "why": "路径写错、目录还没创建，或当前工作目录不对。",
        "next": "用 ls 确认路径，mkdir -p 创建缺失目录，或 cd 到正确项目目录。",
        "avoid": "不要用 rm -rf 处理不确定的路径。",
    },
    "PORT": {
        "title": "端口被占用",
        "why": "上一次的服务没退出，或有别的进程占用了该端口。",
        "next": "ss -ltnp | grep <端口> 或 lsof -i :<端口> 找到 PID，kill 它，或换端口。",
        "avoid": "不要直接 kill -9 不认识的进程。",
    },
    "NET": {
        "title": "网络失败",
        "why": "连接被拒、DNS 解析失败或超时，可能是服务没起、代理/镜像源问题。",
        "next": "先 curl -v 看握手到哪一步；容器内确认端口映射；apt/pip 换国内镜像前先确认公司网络策略。",
        "avoid": "不要把 curl 失败误判为代码问题。",
    },
    "AUTH": {
        "title": "认证失败",
        "why": "凭据、SSH key 或 token 无效/过期。",
        "next": "检查 ssh -T 测试连接、git config credential.helper、token 是否过期。",
        "avoid": "不要把 token 写进命令行历史，用 credential helper 或环境变量。",
    },
    "PIP668": {
        "title": "PEP 668：系统 Python 受保护",
        "why": "Ubuntu 23.04+ 禁止 pip 直接装进系统 Python，避免破坏 apt 管理的包，应改用虚拟环境或 pipx。",
        "next": "python3 -m venv .venv && source .venv/bin/activate，然后 pip install；命令行工具用 pipx。",
        "avoid": "不要习惯性加 --break-system-packages。",
    },
    "MODULE": {
        "title": "Python 模块缺失",
        "why": "当前解释器环境里没装这个包，或装到了另一个 Python/虚拟环境。",
        "next": "确认 which python / python -V，在同一个环境 pip install <包>；需要系统库时先 apt install 对应的 -dev 包。",
        "avoid": "不要 sudo pip install 到系统环境。",
    },
    "BUILD": {
        "title": "编译/构建失败",
        "why": "缺少头文件、编译器或依赖版本不匹配。",
        "next": "按报错装 -dev 包（如 libpq-dev、python3-dev、build-essential），再 make clean 重试。",
        "avoid": "不要跳过报错直接改代码。",
    },
    "DISK": {
        "title": "磁盘空间不足",
        "why": "分区写满或 inode 用尽。",
        "next": "df -h、du -xh --max-depth=1 / | sort -h 找大目录；清 journal：sudo journalctl --vacuum-size=200M。",
        "avoid": "不要删 /var/lib 下不认识的数据库文件。",
    },
    "LOCK": {
        "title": "包管理器锁被占用",
        "why": "另一个 apt/dpkg 进程正在运行，或上次异常退出留下锁。",
        "next": "ps aux | grep -E 'apt|dpkg' 确认；等它结束，或用 sudo dpkg --configure -a 修复半装状态。",
        "avoid": "不要直接删 lock 文件。",
    },
    "GIT_CONFLICT": {
        "title": "Git 合并冲突",
        "why": "本地与远端改了同一处。",
        "next": "git status 看冲突文件，编辑后 git add，再 git rebase --continue / git commit。",
        "avoid": "不要 git checkout -- . 丢掉自己的改动。",
    },
    "GIT_REJECT": {
        "title": "推送被拒（远端有新提交）",
        "why": "远端分支比你新，直接 push 会覆盖历史。",
        "next": "git pull --rebase 后再 push；先 git log --oneline @{u}.. 看清差异。",
        "avoid": "不要用 --force 解决 non-fast-forward。",
    },
    "DOCKER": {
        "title": "Docker 相关错误",
        "why": "守护进程没起、权限不足，或镜像/网络配置问题。",
        "next": "systemctl status docker 看服务；权限问题参考 docker 组配置；拉不动镜像时检查 registry mirror。",
        "avoid": "不要把 sudo 当万能药，先确认 daemon 是否在跑。",
    },
    "SYNTAX": {
        "title": "语法错误",
        "why": "命令或脚本有拼写/引号/缩进问题。",
        "next": "bash -n <脚本>、python -m py_compile <文件> 定位；检查引号是否成对。",
        "avoid": "不要整段重写，先定位第一处报错。",
    },
    "KILLED": {
        "title": "进程被系统杀死",
        "why": "多半是 OOM（内存不足）或被信号终止。",
        "next": "dmesg -T | grep -i -E 'killed|oom' 确认；减少并发/内存，或加 swap。",
        "avoid": "不要在内存不足时继续加并发。",
    },
    "INTERRUPT": {
        "title": "命令被中断",
        "why": "你按了 Ctrl-C，或进程收到 SIGINT。",
        "next": "若只是耗时太长，考虑加 timeout、后台运行（nohup ... &）或缩小范围。",
        "avoid": "不要在半途中断数据库迁移。",
    },
    "USAGE": {
        "title": "参数用法错误",
        "why": "选项名或参数个数不对。",
        "next": "<命令> --help 或 man <命令> 查正确写法。",
        "avoid": "不要凭记忆猜参数。",
    },
    "GENERIC": {
        "title": "命令返回非零退出码",
        "why": "没有捕获到错误输出，只能从退出码和上下文推断。",
        "next": "用 cw run <命令> 重跑一次以捕获 stderr；或看命令自己的日志。",
        "avoid": "不要忽略退出码继续往下跑。",
    },
}


def base_category(category: str) -> str:
    if not category:
        return ""
    if category in HINTS:
        return category
    head = category.split(":", 1)[0]
    return head


def hint_for(category: str) -> dict:
    if category and category in HINTS:
        return HINTS[category]
    base = base_category(category)
    if base in HINTS:
        return HINTS[base]
    return HINTS["GENERIC"]
