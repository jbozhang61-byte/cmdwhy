# 命令历史注解报告

> 62 条命令 / 5 个会话 · 数据源：demo_history.jsonl

## 概览

- 成功 29，失败 11（确认 8 / 推测 3），未记录退出码 22
- 错误率 21.6%（已知状态的 37 条中失败 8 条）
- 修复链 11 条，已验证 9 条，平均修复耗时 2m43s
- 新增命令 25 条，环境改变 20 次，危险命令 0 条
- 高频错误：PERM ×2、MODULE:flask ×1、PIP668 ×1、CMD_NOT_FOUND:pytest ×1、CMD_NOT_FOUND:puhs ×1、PERM:dpkg-lock ×1

## 报错：错在哪，后来怎么好的

### PERM — 权限不足（2 次）

- #34 15:08:00 `nginx -t`
  - 错误：紧接着用 sudo 重跑了同一条命令，通常意味着上一条因权限不足失败
  - 修复：`sudo nginx -t`（已验证）
  - 更正：`sudo nginx -t`
- #36 15:10:00 `systemctl reload nginx`
  - 错误：紧接着用 sudo 重跑了同一条命令，通常意味着上一条因权限不足失败
  - 修复：`sudo systemctl reload nginx`（未验证）
  - 更正：`sudo systemctl reload nginx`

确认这是系统级操作后加 sudo 重试；若只是脚本不能执行，用 chmod +x <文件>。

### CMD_NOT_FOUND:puhs — 命令不存在或拼写错误（1 次）

- #14 09:32:00 `git puhs`
  - 错误：git: 'puhs' is not a git command. See 'git --help'.
  - 修复：`git push`（已验证）
  - 更正：`git push`

先确认拼写；Ubuntu 上可用 sudo apt install <包名>，或用 command-not-found 查询包名。

### CMD_NOT_FOUND:pytest — 命令不存在或拼写错误（1 次）

- #10 09:24:00 `pytest -q`
  - 错误：bash: pytest: command not found
  - 修复：`pip install pytest`（已验证）

先确认拼写；Ubuntu 上可用 sudo apt install <包名>，或用 command-not-found 查询包名。

### DOCKER — Docker 相关错误（1 次）

- #28 12:02:00 `docker ps`
  - 错误：permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock: Get "http://%2Fvar%2Frun%2Fdocker.sock/v1.45/containers/json": dial…
  - 修复：`sudo docker ps`（已验证）

systemctl status docker 看服务；权限问题参考 docker 组配置；拉不动镜像时检查 registry mirror。

### GIT_REJECT:fetch-first — 推送被拒（远端有新提交）（1 次）

- #45 18:20:00 `git push origin main`
  - 错误：紧接着 git pull/fetch，通常是远端拒绝了 push（非快进）
  - 修复：`git pull --rebase`（未验证）

git pull --rebase 后再 push；先 git log --oneline @{u}.. 看清差异。

### MODULE:flask — Python 模块缺失（1 次）

- #3 09:13:00 `python3 app.py`
  - 错误：ModuleNotFoundError: No module named 'flask'
  - 修复：`sudo apt install python3-venv -y` → `python3 -m venv .venv` → `source .venv/bin/activate`（已验证）

确认 which python / python -V，在同一个环境 pip install <包>；需要系统库时先 apt install 对应的 -dev 包。

### PERM:dpkg-lock — apt 锁文件被占用 / 缺少 root（1 次）

- #18 11:40:00 `apt install jq`
  - 错误：E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)
  - 修复：`sudo apt install jq -y`（已验证）
  - 更正：`sudo apt install jq`

包管理命令前加 sudo；若提示 lock 被占用，先 ps aux | grep -E 'apt|dpkg' 确认没有其他安装在进行。

### PERM:exec — 脚本缺少执行权限（1 次）

- #20 11:44:00 `./deploy.sh`
  - 错误：bash: ./deploy.sh: Permission denied
  - 修复：`chmod +x deploy.sh`（已验证）

chmod +x <脚本>，或显式用 bash <脚本> 运行。

### PIP668 — PEP 668：系统 Python 受保护（1 次）

- #4 09:15:00 `pip install -r requirements.txt`
  - 错误：error: externally-managed-environment
  - 修复：`sudo apt install python3-venv -y` → `python3 -m venv .venv` → `source .venv/bin/activate`（已验证）

python3 -m venv .venv && source .venv/bin/activate，然后 pip install；命令行工具用 pipx。

### PORT:3000 — 端口被占用（1 次）

- #23 11:52:00 `npm run dev`
  - 错误：Error: listen EADDRINUSE: address already in use :::3000
  - 修复：`kill 4242`（已验证）

ss -ltnp | grep <端口> 或 lsof -i :<端口> 找到 PID，kill 它，或换端口。

## 改变：环境/项目状态动了什么

- 09:17:00 安装软件包 python3-venv — `sudo apt install python3-venv -y`
- 09:18:00 创建虚拟环境 .venv — `python3 -m venv .venv`
- 09:19:00 修改 shell 环境（source .venv/bin/activate） — `source .venv/bin/activate`
- 09:20:00 安装 Python 依赖 requirements.txt — `pip install -r requirements.txt`
- 09:25:00 安装 Python 依赖 pytest — `pip install pytest`
- 09:32:30 推送远端 — `git push`
- 09:42:00 切换分支/版本 → feat/history-why — `git checkout -b feat/history-why`
- 11:41:00 安装软件包 jq — `sudo apt install jq -y`
- 11:45:00 修改权限 +x deploy.sh — `chmod +x deploy.sh`
- 11:55:00 结束进程 4242 — `kill 4242`
- 15:05:00 切换目录 /home/ubuntu/work/api/web → /home/ubuntu/infra — `cd ~/infra`
- 15:06:00 编辑文件 nginx.conf — `vim nginx.conf`
- 15:11:00 重载服务 nginx — `sudo systemctl reload nginx`
- 18:20:30 同步远端 — `git pull --rebase`
- 18:21:00 推送远端 — `git push origin main`
- 18:25:00 切换分支/版本 → fix/port-config — `git checkout -b fix/port-config`
- 18:33:00 提交改动 — `git commit -m "fix: use env port"`
- 18:34:00 推送远端 — `git push`
- 21:04:00 升级系统软件包 — `sudo apt upgrade -y`
- 21:10:00 重启服务 nginx — `sudo systemctl restart nginx`

## 添加：第一次出现的命令

- 09:12:00 `ls -la` — 查看目录内容
- 09:12:30 `git status` — 查看仓库状态
- 09:13:00 `python3 app.py` — 运行 Python 脚本
- 09:15:00 `pip install -r requirements.txt` — 安装 Python 依赖
- 09:17:00 `sudo apt install python3-venv -y` — 安装缺失的 Python 依赖
- 09:19:00 `source .venv/bin/activate` — 安装缺失的 Python 依赖
- 09:24:00 `pytest -q` — 运行测试
- 11:44:00 `./deploy.sh` — 运行 ./deploy.sh
- 11:45:00 `chmod +x deploy.sh` — 给脚本加执行权限
- 11:52:00 `npm run dev` — 运行 npm 脚本
- 11:53:00 `ss -ltnp | grep 3000` — 查看端口/连接
- 11:54:00 `lsof -i :3000` — 查看端口占用
- 11:55:00 `kill 4242` — 结束占用端口的进程
- 12:02:00 `docker ps` — 查看容器
- 12:07:00 `journalctl -u docker -n 20 --no-pager` — 查看系统日志
- 15:05:00 `cd ~/infra` — 切换工作目录
- 15:06:00 `vim nginx.conf` — 编辑文件
- 15:08:00 `nginx -t` — 运行 nginx
- 15:10:00 `systemctl reload nginx` — 重载服务配置
- 15:13:00 `curl -I localhost` — 发起 HTTP 请求
- 15:18:00 `df -h` — 查看磁盘空间
- 15:19:00 `du -sh /var/log` — 统计目录占用
- 15:23:00 `uptime` — 查看运行时长
- 21:00:00 `uname -a` — 查看系统信息
- 21:12:00 `htop` — 查看系统负载

## 随机：回看会话

### 会话 S3 · 15:05–15:23

14 条命令 · ~/infra · infra · git:main · Ubuntu 24.04
- #34 `nginx -t` — PERM
  - 修复：`sudo nginx -t`
- #36 `systemctl reload nginx` — PERM
  - 修复：`sudo systemctl reload nginx`
