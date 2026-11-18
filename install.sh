#!/usr/bin/env bash
# cmdwhy 一键安装：Debian/Ubuntu/Kali、Arch、Fedora/RHEL/CentOS、openSUSE、Alpine
set -euo pipefail
cd "$(dirname "$0")"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo "当前用户不是 root，且没有 sudo；请用 root 运行。" >&2
        exit 1
    fi
fi

install_packages() {
    if command -v apt-get >/dev/null 2>&1; then
        $SUDO apt-get update -qq
        $SUDO apt-get install -y python3 python3-venv python3-pip git
    elif command -v pacman >/dev/null 2>&1; then
        $SUDO pacman -Syu --noconfirm
        $SUDO pacman -S --needed --noconfirm python python-pip git
    elif command -v dnf >/dev/null 2>&1; then
        $SUDO dnf install -y python3 python3-pip git
    elif command -v yum >/dev/null 2>&1; then
        $SUDO yum install -y python3 python3-pip git
    elif command -v zypper >/dev/null 2>&1; then
        $SUDO zypper --non-interactive install python3 python3-pip git
    elif command -v apk >/dev/null 2>&1; then
        $SUDO apk add --no-cache python3 py3-pip git bash
    else
        echo "未识别的包管理器；请手动安装 python3、venv、pip、git。" >&2
        exit 1
    fi
}

if ! command -v python3 >/dev/null 2>&1; then
    echo "缺少 python3，尝试安装依赖……"
    install_packages
fi

if ! python3 -c "import venv" >/dev/null 2>&1; then
    echo "缺少 venv 模块，尝试安装依赖……"
    install_packages
fi

if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi

# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip >/dev/null 2>&1 || true
pip install -e .

echo ""
echo "安装完成。试试："
echo "  cmdwhy demo"
echo "  cmdwhy init && cmdwhy ingest"
echo "  cmdwhy hook install"
