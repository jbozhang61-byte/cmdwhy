#!/usr/bin/env bash
# cmdwhy 一键安装（Ubuntu / Debian）
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "需要 python3：sudo apt install -y python3 python3-venv" >&2
    exit 1
fi

if ! python3 -c "import venv" >/dev/null 2>&1; then
    echo "需要 python3-venv：sudo apt install -y python3-venv" >&2
    exit 1
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
