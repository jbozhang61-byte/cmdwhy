# 参与 cmdwhy

感谢你愿意改进 cmdwhy。这个项目目标是：让 shell 历史自己解释自己，同时保持本地、可解释、可纠正。

## 开发环境

- Python 3.8+
- 无第三方运行时依赖
- Linux 优先；Windows/WSL 可用于分析和运行测试
- 推荐用虚拟环境：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
```

## 跑测试

```bash
python -m unittest discover -s tests -v
python -m compileall -q cmdwhy tests
```

当前测试数见 README。改代码后请至少跑完整测试；涉及 shell hook 的改动，最好在 bash/zsh/fish 里各验证一次。

## 代码风格

- 纯标准库，避免新增运行时依赖；
- Python 3.8 兼容：不用 3.9+ 的仅新语法；
- 新逻辑先写可测试的函数，再接到 CLI；
- 面向用户的文本保持简洁、可执行、明确置信度；
- 不要执行高风险命令；自动执行只允许低风险动作。

## 可以贡献什么

- 新的发行版适配：在 `system.py` / `env.py` 增加包管理器和路径；
- 新的错误签名：在 `errors.py` 增加可区分的中英文模式；
- 新的命令意图 / 角色：在 `intent.py` 增加规则；
- 上下文规则：在 `context.py` 增加环境/角色信号，不要只堆关键词；
- 搜索、分页、缓存、索引的性能改进；
- 文档、示例、CI 和测试。

## 隐私

- 不提交真实用户的历史文件、token、密码、私有仓库地址；
- 测试数据使用虚构值；
- 落盘前必须经过 `redact.py`；
- 新增字段如果要写盘，先判断是否包含敏感信息。

## 提交 PR

1. 说明要解决的问题和用户场景；
2. 给出复现步骤或测试；
3. 跑完整测试；
4. 如果改了输出格式，同步更新 README / docs/COMMANDS.md / examples。
