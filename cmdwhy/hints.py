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
    "GIT_AUTH": {
        "title": "Git 远程认证失败",
        "why": "HTTPS 凭据、token 或 SSH key 失效，或远端要求新的登录方式。",
        "next": "git config --global credential.helper、gh auth login，或改用 SSH 并 ssh -T git@github.com 验证。",
        "avoid": "不要把 token 直接写进远程 URL 或命令行历史。",
    },
    "SSH": {
        "title": "SSH 连接/认证失败",
        "why": "公钥没加到远端、权限过宽、host key 变化，或网络断开。",
        "next": "ssh -v 看握手；检查 ~/.ssh 权限 700/600、ssh-add -l、known_hosts。",
        "avoid": "不要用 StrictHostKeyChecking=no 长期跳过 host key 校验。",
    },
    "K8S": {
        "title": "Kubernetes 操作失败",
        "why": "context/凭据不对、RBAC 禁止、Pod 未就绪，或集群不可达。",
        "next": "kubectl config current-context、kubectl auth can-i --list、kubectl describe pod <name> 看事件。",
        "avoid": "不要在生产集群上直接 apply 未审查的 YAML。",
    },
    "DB": {
        "title": "数据库连接/查询失败",
        "why": "服务没起、连接串/密码错、库表不存在，或连接数满。",
        "next": "确认服务端口、连接串和账号权限；psql/mysql 手动连一次，先看服务日志。",
        "avoid": "不要为省事把数据库端口暴露到公网。",
    },
    "TLS": {
        "title": "TLS/证书校验失败",
        "why": "证书过期、自签名、CA 不匹配，或系统时间不对。",
        "next": "openssl s_client -connect host:443 看证书链；确认系统时间和 CA 包。",
        "avoid": "不要用 -k / verify=False 绕过证书校验。",
    },
    "READONLY": {
        "title": "文件系统/数据库只读",
        "why": "分区以只读挂载、磁盘故障保护，或数据库进入只读模式。",
        "next": "mount | grep ' ro,'、dmesg 看文件系统错误；数据库看是否处于 recovery/read-only。",
        "avoid": "不要强行 remount rw 掩盖磁盘故障。",
    },
    "TEST_FAIL": {
        "title": "测试失败",
        "why": "断言失败、用例超时，或环境依赖没准备好。",
        "next": "先跑单个失败用例（pytest -x / npm test -- -t），看第一处断言和环境差异。",
        "avoid": "不要用跳过测试或改断言来让流水线变绿。",
    },
    "DEPENDENCY": {
        "title": "依赖解析冲突",
        "why": "lock 文件、peer dependency 或版本范围互相冲突。",
        "next": "看完整错误里的冲突包；用项目规定的包管理器，必要时删 lock 重装并审查 diff。",
        "avoid": "不要无脑 --force / --legacy-peer-deps。",
    },
    "YAML": {
        "title": "YAML 解析失败",
        "why": "缩进、冒号或列表层级不合法。",
        "next": "用 yamllint / python -c 'import yaml;yaml.safe_load(open(...))' 定位第一处。",
        "avoid": "不要用 tab 缩进 YAML。",
    },
    "JSON_DECODE": {
        "title": "JSON 解析失败",
        "why": "响应/文件不是合法 JSON，或前面混入了日志。",
        "next": "把原始输出落到文件，用 jq . 看第一处；确认接口是否返回了 HTML 错误页。",
        "avoid": "不要对非 JSON 输出硬套 jq。",
    },
    "COMPOSE": {
        "title": "Docker Compose 失败",
        "why": "服务构建失败、端口/卷冲突，或依赖服务没起来。",
        "next": "docker compose config 校验、docker compose logs <service> 看具体服务。",
        "avoid": "不要直接 down -v 清掉数据卷。",
    },
    "JAVA": {
        "title": "Java/Maven/Gradle 失败",
        "why": "JDK 版本不匹配、JAVA_HOME 错，或依赖下载失败。",
        "next": "java -version、echo $JAVA_HOME、mvn -v / gradle -v；按项目要求切 JDK。",
        "avoid": "不要全局改 JAVA_HOME 影响其他项目。",
    },
    "RUST": {
        "title": "Rust 编译失败",
        "why": "类型/借用检查错误、crate 缺失，或工具链版本不匹配。",
        "next": "cargo check 看第一处 error[E...]；rustup show 确认 toolchain。",
        "avoid": "不要为了过编译到处 clone/ unwrap。",
    },
    "GO": {
        "title": "Go 构建/模块失败",
        "why": "go.sum 缺失、模块路径错，或依赖下载失败。",
        "next": "go mod tidy、go env GOPROXY；确认在模块根目录执行。",
        "avoid": "不要关闭 GOPROXY 校验来绕过供应链问题。",
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
