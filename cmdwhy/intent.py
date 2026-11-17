"""命令意图与角色分类：这条命令想干什么、它在修复链里属于哪一步。"""

from __future__ import annotations

from .model import command_head, command_tokens, core_signature, split_command

SIMPLE_INTENTS = {
    "ls": "查看目录内容",
    "ll": "查看目录内容",
    "la": "查看目录内容",
    "pwd": "确认当前路径",
    "cd": "切换工作目录",
    "cat": "阅读文件内容",
    "less": "阅读文件内容",
    "more": "阅读文件内容",
    "head": "查看文件开头",
    "tail": "查看文件末尾/日志",
    "vim": "编辑文件",
    "vi": "编辑文件",
    "nano": "编辑文件",
    "emacs": "编辑文件",
    "code": "编辑文件",
    "grep": "搜索文本",
    "rg": "搜索文本",
    "ag": "搜索文本",
    "find": "查找文件",
    "fd": "查找文件",
    "tree": "查看目录树",
    "wc": "统计文件行数",
    "which": "确认命令位置",
    "type": "确认命令类型",
    "whereis": "确认命令位置",
    "make": "构建项目",
    "cmake": "生成构建配置",
    "pytest": "运行测试",
    "tox": "运行测试",
    "mypy": "类型检查",
    "ruff": "代码检查",
    "flake8": "代码检查",
    "black": "格式化代码",
    "isort": "整理导入",
    "python": "运行 Python",
    "python3": "运行 Python 脚本",
    "node": "运行 Node 脚本",
    "bash": "执行 shell 脚本",
    "sh": "执行 shell 脚本",
    "ps": "查看进程",
    "pgrep": "查找进程",
    "top": "查看系统负载",
    "htop": "查看系统负载",
    "free": "查看内存",
    "df": "查看磁盘空间",
    "du": "统计目录占用",
    "uptime": "查看运行时长",
    "date": "查看时间",
    "kill": "结束进程",
    "killall": "结束进程",
    "pkill": "结束进程",
    "curl": "发起 HTTP 请求",
    "wget": "下载文件",
    "ping": "测试网络连通",
    "ss": "查看端口/连接",
    "netstat": "查看端口/连接",
    "lsof": "查看端口占用",
    "dig": "查询 DNS",
    "nslookup": "查询 DNS",
    "nc": "测试端口",
    "traceroute": "路由追踪",
    "ssh": "远程登录",
    "scp": "远程传输文件",
    "rsync": "同步文件",
    "chmod": "修改文件权限",
    "chown": "修改文件属主",
    "sudo": "以 root 权限执行",
    "mkdir": "创建目录",
    "rmdir": "删除目录",
    "rm": "删除文件",
    "cp": "复制文件",
    "mv": "移动/重命名文件",
    "touch": "创建空文件",
    "ln": "创建链接",
    "tar": "打包/解包",
    "zip": "压缩文件",
    "unzip": "解压文件",
    "gzip": "压缩文件",
    "mount": "挂载文件系统",
    "umount": "卸载文件系统",
    "lsblk": "查看块设备",
    "fdisk": "磁盘分区",
    "ufw": "管理防火墙",
    "iptables": "管理防火墙",
    "useradd": "添加用户",
    "usermod": "修改用户",
    "passwd": "修改密码",
    "groupadd": "添加用户组",
    "crontab": "管理定时任务",
    "export": "设置环境变量",
    "unset": "取消环境变量",
    "source": "加载环境脚本",
    ".": "加载环境脚本",
    "alias": "设置命令别名",
    "unalias": "删除命令别名",
    "env": "查看环境变量",
    "printenv": "查看环境变量",
    "uname": "查看系统信息",
    "hostnamectl": "查看主机信息",
    "lsb_release": "查看发行版信息",
    "neofetch": "查看系统信息",
    "history": "查看命令历史",
    "clear": "清屏",
    "exit": "退出会话",
    "logout": "退出会话",
    "su": "切换用户",
    "journalctl": "查看系统日志",
    "dmesg": "查看内核日志",
    "systemctl": "管理系统服务",
    "service": "管理系统服务",
    "sed": "编辑文件内容",
    "tee": "写入文件",
    "truncate": "截断文件",
    "snap": "Snap 包管理",
    "dpkg": "系统包管理",
    "apt": "系统包管理",
    "apt-get": "系统包管理",
    "pip": "Python 包管理",
    "pip3": "Python 包管理",
    "pipx": "安装 Python 工具",
    "conda": "Conda 环境管理",
    "uv": "uv 依赖管理",
    "poetry": "Poetry 依赖管理",
    "docker": "容器操作",
    "docker-compose": "容器编排",
    "podman": "容器操作",
}

GIT_INTENTS = {
    "status": "查看仓库状态",
    "diff": "查看未提交改动",
    "log": "查看提交历史",
    "show": "查看提交内容",
    "add": "暂存改动",
    "commit": "提交改动",
    "push": "推送远端",
    "pull": "拉取远端",
    "fetch": "获取远端更新",
    "checkout": "切换分支/文件",
    "switch": "切换分支",
    "branch": "管理分支",
    "merge": "合并分支",
    "rebase": "变基",
    "clone": "克隆仓库",
    "stash": "暂存工作区",
    "reset": "回退改动",
    "restore": "恢复文件",
    "remote": "管理远端",
    "tag": "管理标签",
    "init": "初始化仓库",
    "config": "配置 Git",
    "revert": "撤销提交",
    "cherry-pick": "拣选提交",
    "blame": "追溯代码作者",
    "clean": "清理未跟踪文件",
}

APT_INTENTS = {
    "install": "安装系统包",
    "remove": "卸载系统包",
    "purge": "彻底卸载软件包",
    "update": "更新包索引",
    "upgrade": "升级系统包",
    "full-upgrade": "完整升级系统",
    "search": "搜索软件包",
    "show": "查看包信息",
    "autoremove": "清理无用依赖",
    "list": "列出软件包",
}

PIP_INTENTS = {
    "install": "安装 Python 依赖",
    "uninstall": "卸载 Python 依赖",
    "list": "列出已装依赖",
    "freeze": "导出依赖清单",
    "show": "查看包信息",
}

NPM_INTENTS = {
    "install": "安装 Node 依赖",
    "ci": "安装 Node 依赖（CI 模式）",
    "run": "运行 npm 脚本",
    "start": "启动开发服务",
    "test": "运行前端测试",
    "build": "构建前端",
    "publish": "发布 npm 包",
}

DOCKER_INTENTS = {
    "ps": "查看容器",
    "run": "启动容器",
    "build": "构建镜像",
    "logs": "查看容器日志",
    "exec": "进入容器执行",
    "compose": "编排容器",
    "pull": "拉取镜像",
    "push": "推送镜像",
    "images": "查看镜像",
    "rm": "删除容器",
    "rmi": "删除镜像",
    "start": "启动容器",
    "stop": "停止容器",
}

SYSTEMCTL_INTENTS = {
    "start": "启动服务",
    "stop": "停止服务",
    "restart": "重启服务",
    "status": "查看服务状态",
    "enable": "设置开机自启",
    "disable": "取消开机自启",
    "reload": "重载服务配置",
    "daemon-reload": "重载 systemd 配置",
    "is-active": "检查服务是否在跑",
}

INSPECT_HEADS = {
    "ls", "ll", "la", "pwd", "cat", "less", "more", "head", "tail", "grep", "rg", "ag",
    "find", "fd", "tree", "stat", "file", "wc", "du", "df", "free", "ps", "pgrep",
    "top", "htop", "ss", "netstat", "lsof", "journalctl", "dmesg", "which", "type",
    "whereis", "history", "env", "printenv", "uname", "whoami", "id", "uptime", "date",
    "cal", "hostname", "lsblk", "blkid", "nvidia-smi", "curl", "wget", "ping", "dig",
    "nslookup", "nc", "traceroute", "test",
}

MUTATE_HEADS = {
    "cd", "export", "unset", "alias", "unalias", "source", ".", "mkdir", "rmdir", "rm",
    "cp", "mv", "touch", "ln", "chmod", "chown", "mount", "umount", "kill", "killall",
    "pkill", "apt", "apt-get", "dpkg", "snap", "pip", "pip3", "pipx", "conda", "brew",
    "npm", "yarn", "pnpm", "systemctl", "service", "docker", "docker-compose", "podman",
    "useradd", "usermod", "userdel", "groupadd", "passwd", "crontab", "sed", "tee",
    "truncate", "tar", "zip", "unzip", "gzip", "vim", "vi", "nano", "code", "emacs",
    "git", "uv", "poetry", "make", "cmake", "ufw", "iptables",
}

RUN_HEADS = {
    "python", "python3", "python2", "node", "bash", "sh", "zsh", "pytest", "tox", "go",
    "cargo", "java", "mvn", "gradle", "ruby", "php", "perl", "make", "cmake",
}


def _sub(tokens):
    if len(tokens) > 1 and not tokens[1].startswith("-"):
        return tokens[1]
    return ""


def classify_intent(event) -> str:
    tokens = event.tokens
    if not tokens:
        return "空命令"
    head = tokens[0]
    sub = _sub(tokens)
    if head.startswith("python") and head not in ("python", "python3", "python2"):
        head = "python3"
    if head in ("python", "python3", "python2"):
        if "-m" in tokens:
            try:
                module = tokens[tokens.index("-m") + 1]
            except IndexError:
                return "运行 Python 模块"
            if module == "venv":
                return "创建虚拟环境"
            if module in ("pip", "pip3"):
                return "Python 包管理"
            if module in ("pytest", "unittest"):
                return "运行测试"
            return "运行 Python 模块 " + module
        return "运行 Python 脚本"
    if head == "git":
        return GIT_INTENTS.get(sub, "Git 操作")
    if head in ("apt", "apt-get", "dpkg", "snap"):
        return APT_INTENTS.get(sub, "系统包管理")
    if head in ("pip", "pip3", "pipx"):
        return PIP_INTENTS.get(sub, "Python 包管理")
    if head in ("npm", "yarn", "pnpm"):
        return NPM_INTENTS.get(sub, "Node 包管理")
    if head in ("docker", "podman"):
        return DOCKER_INTENTS.get(sub, "容器操作")
    if head in ("systemctl", "service"):
        return SYSTEMCTL_INTENTS.get(sub, "管理系统服务")
    if head == "journalctl":
        return "查看系统日志"
    if head in SIMPLE_INTENTS:
        return SIMPLE_INTENTS[head]
    return "运行 " + head


def command_key(cmd: str):
    tokens = command_tokens(cmd)
    if not tokens:
        return None
    head = tokens[0]
    sub = _sub(tokens)
    if sub and head in ("git", "apt", "apt-get", "pip", "pip3", "npm", "docker", "systemctl", "cargo", "go", "kubectl"):
        return head + " " + sub
    return head


def command_role(cmd: str) -> str:
    """inspect（只读排查）/ mutate（改变环境）/ run（运行程序）/ other。"""
    tokens = command_tokens(cmd)
    if not tokens:
        return "other"
    head = tokens[0]
    sub = _sub(tokens)
    if head.startswith("python"):
        if "-m" in tokens:
            try:
                module = tokens[tokens.index("-m") + 1]
            except IndexError:
                module = ""
            if module in ("venv", "pip", "pip3", "virtualenv"):
                return "mutate"
        return "run"
    if head == "git":
        return "inspect" if sub in ("status", "log", "diff", "show", "blame", "remote", "rev-parse") else "mutate"
    if head in ("systemctl", "service"):
        return "inspect" if sub in ("status", "is-active", "is-enabled", "list-units", "show") else "mutate"
    if head in ("docker", "podman"):
        return "inspect" if sub in ("ps", "logs", "images", "inspect", "version", "info") else "mutate"
    if head in ("apt", "apt-get", "dpkg", "snap"):
        return "inspect" if sub in ("search", "show", "list", "policy") else "mutate"
    if head in ("pip", "pip3"):
        return "inspect" if sub in ("list", "show", "freeze", "check") else "mutate"
    if head in ("npm", "yarn", "pnpm"):
        if sub in ("install", "ci", "add", "remove", "uninstall"):
            return "mutate"
        if sub in ("run", "start", "test", "build"):
            return "run"
        return "mutate"
    if head in INSPECT_HEADS:
        return "inspect"
    if head in MUTATE_HEADS:
        return "mutate"
    if head in RUN_HEADS:
        return "run"
    return "other"


FIX_INTENTS = {
    "PERM": "提权/改权限后重试",
    "CMD_NOT_FOUND": "安装缺失命令",
    "NOT_FOUND": "补齐缺失路径",
    "PORT": "释放被占用的端口",
    "PIP668": "改用虚拟环境安装",
    "MODULE": "安装缺失的 Python 依赖",
    "BUILD": "补齐构建依赖",
    "DISK": "清理磁盘空间",
    "LOCK": "解除包管理锁",
    "GIT_REJECT": "同步远端后重试",
    "GIT_CONFLICT": "处理合并冲突",
    "AUTH": "修复认证凭据",
    "NET": "排查网络问题",
    "DOCKER": "修复 Docker 访问",
    "SYNTAX": "修复语法问题",
    "KILLED": "处理资源不足",
    "USAGE": "修正参数用法",
}


def fix_intent(category: str, cmd: str) -> str:
    base = (category or "GENERIC").split(":", 1)[0]
    head = command_head(cmd)
    if base == "PERM":
        if head == "chmod":
            return "给脚本加执行权限"
        if head == "chown":
            return "修改文件属主"
        if head == "usermod":
            return "把用户加入权限组"
        if (cmd or "").strip().startswith("sudo"):
            return "补 sudo 提权重试"
        return "修复权限问题"
    if base == "NOT_FOUND" and head in ("mkdir", "touch", "git"):
        return "创建缺失的路径"
    if base == "PORT" and head in ("kill", "killall", "pkill", "fuser"):
        return "结束占用端口的进程"
    if base == "PIP668" and head.startswith("python"):
        return "创建虚拟环境"
    return FIX_INTENTS.get(base, "修复报错")
