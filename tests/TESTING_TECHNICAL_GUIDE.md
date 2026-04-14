# 测试技术说明（实现机制与排障路径）

Last updated: 2026-04-14

## 文档定位

`TESTING_README.md` 讲“怎么跑”，本文件讲“为什么这样设计”。
适合以下场景：

- 你要改测试框架代码（helpers / CI / runner）
- 你要定位顽固失败（超时、网络、数据污染）
- 你要扩展新的真实环境测试层

---

## 总体设计：同一套代码，多执行策略

核心原则：

1. 测试逻辑尽量复用同一套代码。
2. 差异只体现在 profile 与 fail/skip 策略。
3. 所有真实环境测试必须具备 preflight、timeout、cleanup、artifact。

Profile 语义：

- `local`
  - 开发机调试友好；网络不可达可按策略 skip。
- `remote`
  - 手工连远端测试环境；默认要求网络可达。
- `ci`
  - CI 场景；失败优先快速暴露（fail-fast）。

补充说明：

- 针对 mem0 版本演进，当前 unit 已补充 `AsyncMemory.from_config()` 同步/异步两种初始化语义的兼容回归测试。
- provider 侧也补充了 `async_mode=true` 的凭证校验链路测试，确保仍通过 `get_async_client(...).search(...)` 做轻量验证。

---

## Preflight 机制（最关键防线）

入口在 `tests/helpers/dify_env.py`：

- `create_dify_client()`
- `preflight_chat_client()` / `preflight_workflow_client()`

执行顺序：

1. 读取并规范化 base URL（必须 `/v1`）。
2. 检查 API key 是否存在。
3. localhost 策略判断：
   - 未显式允许 localhost 时，根据 profile 决定 skip/fail。
4. 轻量探测：
   - `list_conversations(limit=1)` 验证 API 可达性。
5. 根据 `REQUIRE_DIFY_NETWORK` 最终决策 skip 或 fail。

设计目的：避免“正式用例运行到一半才发现环境不可用”。

---

## 超时治理（四层）

### 1) 请求超时

- 配置：`DIFY_HTTP_TIMEOUT`
- 作用：单次 HTTP 请求上限

### 2) 轮询总超时

- 配置：`DIFY_WORKFLOW_MAX_WAIT`
- 作用：workflow 从触发到终态的最大等待时间

### 3) 无进展超时

- 配置：`DIFY_STALL_TIMEOUT`
- 作用：状态/时间戳长时间不变判定为卡住

### 4) pytest 级超时

- 通过 `tests/run_tests.sh --timeout` 注入
- 若本地未装 `pytest-timeout`，脚本自动降级（提示但不失败）

推荐默认值：

- HTTP: 20s
- max wait: 120s
- poll interval: 2s
- stall: 30s

---

## Seed / Cleanup 生命周期（防污染核心）

### Seed

- 实现：`tests/helpers/dify_seed.py`
- 输入：`tests/fixtures/conversation_seed_cases.yaml`
- 输出：`SeedManifest`（run_id/user_ids/conversation_ids）

### Cleanup

- Dify cleanup：`tests/helpers/dify_cleanup.py`
  - `delete_conversation`
  - 可选删除后可见性验证
- Mem0 cleanup：`tests/helpers/mem0_cleanup.py`
  - `delete_all`
  - checkpoint / access_log / lock / task_status 显式清理

保障方式：

- fixture teardown 或 `try/finally` 强制执行 cleanup
- 即使断言失败/异常也能回收数据

---

## Workflow 执行状态机

实现：`tests/helpers/workflow_runner.py`

执行步骤：

1. `run_workflow_blocking(inputs, user_id)`
2. 解析 `workflow_run_id`
3. 轮询 `get_workflow_run_detail`
4. 达到终态：`succeeded|failed|stopped|completed`
5. 断言输出：status/key/contains

artifact 输出策略：

- 触发后立即写 `workflow-initial-*`
- 成功终态写 `workflow-final-*`
- 任意异常写 `workflow-failure-*`（含错误类型、消息、上下文、初始响应）

---

## Artifact 与排障流程

启用条件：

- 设置 `TEST_ARTIFACTS_DIR`

典型产物：

- seed manifest
- cleanup summary
- workflow initial/final/failure

推荐排障顺序：

1. 看 pytest 日志（先定位失败用例）
2. 看 manifest/cleanup（确认数据生命周期）
3. 看 workflow failure（确认请求参数与远端响应）

---

## 并发与进程策略

历史风险：导入 `dify_plugin` 可能触发 gevent monkey patching 冲突。

当前策略：

- `tests/run_tests.sh` 仅在显式传入 `--forked` 时启用多进程隔离
- `acceptance` 默认不加 `--forked`，以便 session 级 fixture 共享 seed 数据
- macOS 下仅在启用 `--forked` 时设置 `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`

调试建议：

- 使用 `--output-file` 保存完整输出
- 配合 artifact 做故障复盘

---

## CI 编排与触发

文件：`/.github/workflows/ci.yml`

- `push/pull_request`：默认执行 `unit`
- `workflow_dispatch` + `run_real_env_suites=true`：执行
  - `integration-dify`
  - `acceptance-workflow`

每个真实环境 job 包含：

- guard step（缺 secrets 时显式 skip）
- suite 执行
- pytest 日志上传
- `test-artifacts/<suite>` 上传

---

## 操作建议（环境初始化与命令顺序）

推荐将 conda 作为全局 Python 管理器，但本项目测试执行统一使用 `.venv`。

### 首次初始化

```bash
cd /Users/beersoccer/workspace/mem0_dify_plugin
uv venv .venv
uv sync --group dev
source .venv/bin/activate
./tests/run_tests.sh --check-env
./tests/run_tests.sh --suite unit --timeout 120
```

三条核心命令作用：

- `uv venv .venv`：创建项目本地虚拟环境。
- `uv sync --group dev`：按 `pyproject.toml` + `uv.lock` 安装依赖（含测试依赖）。
- `source .venv/bin/activate`：激活项目环境，确保 `python/pytest` 指向 `.venv`。

### 日常开发（每次新开终端）

```bash
cd /Users/beersoccer/workspace/mem0_dify_plugin
source .venv/bin/activate
./tests/run_tests.sh --suite unit --timeout 120
```

### 真实环境测试执行顺序

```bash
# 先确保 tests/.env.local 或 tests/.env.remote 已配置（本地/远程手工测试）
# CI 不使用 .env 文件，改为 secrets 注入同名环境变量
source .venv/bin/activate
./tests/run_tests.sh --suite integration --env-file tests/.env.remote --require-network --timeout 180
./tests/run_tests.sh --suite acceptance --env-file tests/.env.remote --require-network --timeout 900
```

### 依赖更新后

```bash
cd /Users/beersoccer/workspace/mem0_dify_plugin
source .venv/bin/activate
uv sync --group dev
```

---

## 扩展新真实环境测试时的约束清单

新增任何真实环境测试，请同时满足：

1. 使用 `dify_env` 做 preflight，不直接裸连客户端。
2. 全程有 timeout（请求 + 轮询 + pytest）。
3. 必须带 cleanup（Dify 或 Mem0）。
4. 失败路径写 artifact（至少包含输入和错误摘要）。
5. 在 `run_tests.sh` 可通过 `--suite` 或明确路径运行。

---

## 最近补充的 forget_memories 工具测试

对应文件：`tests/unit/tools/test_forget_memories.py`

覆盖点：

1. `dry_run=true` 时只预览，不执行 `mem.delete`，也不保存 access log。
2. 记忆删除存在失败时，仅按“实际成功删除的 memory_id”更新 access log，避免误删未成功删除条目的访问记录。
3. 真实执行下 checkpoint 清理遵循“保留最新，删除旧副本；最新未过期则不删最新”。

这组用例对应 `tools/forget_memories.py` 的关键风险路径，属于工具层回归保护，建议在改动遗忘/清理逻辑后优先执行。


