# 测试运行说明（零背景可上手）

## 这份文档能帮你做什么

如果你第一次接触这个仓库，按本文档一步步执行，可以完成：

1. 跑通 `unit`（本地必做，最快验证代码是否健康）。
2. 在有 Dify/Mem0 环境时跑通 `integration`、`acceptance`。
3. 在失败时拿到可排查的日志和 JSON artifact。
4. 在 GitHub Actions 手动触发完整真实环境测试。

---

## 测试分层（先理解）

- `unit`
  - 纯逻辑，不依赖网络。
  - 目标：快速发现代码回归。
- `integration`（Dify API）
  - 验证 seed 和 cleanup（会创建并删除 Dify 会话）。
  - 目标：确认 Dify API 数据面可用。
- `acceptance`（workflow）
  - 真正调用 `/workflows/run` 并轮询 run detail，检查结果与副作用。
  - 目标：确认发布后的 workflow 行为与内存生命周期符合预期。

统一入口脚本：`tests/run_tests.sh`

---

## 第 0 步：前置条件检查

### 必需软件

- Python 3.12
- 项目虚拟环境 `.venv`
- 已安装依赖（至少含 `pytest`、`pytest-forked`）

### 一键检查

```bash
source .venv/bin/activate
./tests/run_tests.sh --check-env
```

---

## 第 1 步：准备环境变量（真实环境测试才需要）

推荐拆分为两个文件（不要提交到 Git）：

- 本地开发：`tests/.env.local`（文件内 `TEST_PROFILE=local`）
- 远程/UAT：`tests/.env.remote`（文件内 `TEST_PROFILE=remote` 或 `ci`）
- CI：不使用 `.env` 文件，直接由 GitHub Actions secrets 注入同名环境变量

`run_tests.sh` 的规则：

- 不再使用 `--profile` 或外部 `TEST_PROFILE` 环境变量
- 通过 `--env-file` 指定配置文件（例如 `tests/.env.local` / `tests/.env.remote`）
- profile 由该文件内的 `TEST_PROFILE` 决定（`local|remote|ci`）

可先把下面模板写入 `tests/.env.local`：

```bash
# ---------- 执行策略 ----------
TEST_PROFILE=local
ALLOW_LOCALHOST_DIFY=1
REQUIRE_DIFY_NETWORK=0

# ---------- Dify ----------
DIFY_BASE_URL=https://<your-dify-host>/v1
DIFY_CHATFLOW_API_KEY=<chatflow-app-api-key>
DIFY_WORKFLOW_API_KEY=<workflow-app-api-key>

# ---------- 共享 ----------
DIFY_CHATFLOW_APP_ID=<chatflow-app-id>

# ---------- 超时 ----------
DIFY_HTTP_TIMEOUT=20
DIFY_POLL_INTERVAL=2
DIFY_WORKFLOW_MAX_WAIT=120
DIFY_STALL_TIMEOUT=30

# ---------- Mem0（acceptance 需要）----------
MEM0_LLM_CONFIG=...
MEM0_EMBEDDER_CONFIG=...
MEM0_VECTOR_DB_CONFIG=...
MEM0_GRAPH_DB_CONFIG=...
MEM0_RERANKER_CONFIG=...
```

`tests/.env.remote` 可复用同一套字段，建议改成：

```bash
TEST_PROFILE=remote
ALLOW_LOCALHOST_DIFY=0
REQUIRE_DIFY_NETWORK=1
```

### 常见配置错误

- `DIFY_*_BASE_URL` 没有以 `/v1` 结尾。
- 使用了 localhost，但 `ALLOW_LOCALHOST_DIFY=0`。
- 想强制失败却没有加 `--require-network` 或 `REQUIRE_DIFY_NETWORK=1`。

---

## 第 2 步：按顺序运行测试（推荐流程）

### 2.1 先跑 unit（必须）

```bash
./tests/run_tests.sh --suite unit --timeout 120
```

预期：全部通过，且不依赖 Dify/Mem0。

### 2.2 再跑 integration（可选）

```bash
./tests/run_tests.sh --suite integration --env-file tests/.env.remote --require-network --timeout 180
```

预期：

- 创建 seed 会话
- 删除会话并验证不可见
- 生成 integration 相关 artifact

### 2.3 最后跑 acceptance（可选）

```bash
./tests/run_tests.sh --suite acceptance --env-file tests/.env.remote --require-network --timeout 900
```

预期：

- workflow run 成功进入终态
- smoke 与 memory lifecycle case 按 fixture 配置运行
- 失败时产生 `workflow-failure-*` artifact

---

## 命令参数速查

`tests/run_tests.sh`：

- `--suite unit|integration|acceptance`
- `--env-file <envfile>`
- `--require-network`
- `--timeout <seconds>`
- `--output-file <logfile>`
- `--forked`
- `--e2e`（已废弃，会直接报错并提示改用 integration/acceptance）
- `--cleanup none|manifest|force-all`（测试结束后清理模式，默认 `none`）
- `--check-env`

说明：

- 若本地未安装 `pytest-timeout`，脚本会提示并继续运行（不会因 `--timeout` 失败）。
- `acceptance` 默认执行 `-m workflow_acceptance -v -s`，仅运行 workflow 验收用例。
- `acceptance` 默认超时来自环境变量 `PYTEST_TIMEOUT_ACCEPTANCE`（未设置时为 180 秒）。
- 本地开发建议在 `tests/.env.local` 设置 `PYTEST_TIMEOUT_ACCEPTANCE=900`，避免 memory lifecycle 用例频繁超时。

---

## 关键测试文件（你会经常看）

- Unit（工具与核心逻辑）
  - `tests/unit/tools/test_forget_memories.py`
  - `tests/unit/utils/test_memory_forgetting.py`
- Integration
  - `tests/integration/test_dify_seed_api.py`
  - `tests/integration/test_dify_integration.py`
  - `tests/integration/test_time_range_filtering.py`
- Acceptance
  - `tests/acceptance/test_workflow_plugin_smoke.py`
  - `tests/acceptance/test_memory_extraction_quality.py`
  - `tests/acceptance/test_workflow_memory_lifecycle.py`
- Fixtures
  - `tests/fixtures/conversation_seed_cases.yaml`
  - `tests/fixtures/workflow_cases.yaml`

---

## 如何读取 artifact（失败排查核心）

artifact 默认写入 `tests/artifacts/<profile>`（`local|remote|ci`）：

- `*-manifest-*`：seed 输入/输出范围
- `*-cleanup-summary-*`：Dify 或 Mem0 清理结果
- `workflow-initial-*`：workflow 初始响应
- `workflow-final-*`：workflow 终态结果
- `workflow-failure-*`：失败摘要（错误类型/消息/上下文）

建议：

```bash
./tests/run_tests.sh --suite acceptance --env-file tests/.env.remote --require-network --output-file acceptance.log
```

然后先看 `acceptance.log`，再看 `tests/artifacts/<profile>` 下 JSON。

---

## 清理 Dify 残留会话（网络抖动/中断后的安全回收）

如果 integration/acceptance 在 seed 之后中断，可能会留下测试会话。推荐使用：

`tests/cleanup_seed_residuals.py`

安全策略：

- 默认是 **dry-run**，只预览不删除。
- 默认仅清理 manifest 中记录的会话（测试代码写入），不需要人工指定用户。
- 仅在 `--force-all` 时，才会直连 Dify 做全量扫描清理。
- `--force-all` 的用户来源是：manifest 用户 + `DIFY_CLEANUP_USERS`（取并集）。
- 若两者都为空，脚本会提示并直接退出，不执行真实清理。
- 删除后默认 `verify=true`，会二次确认会话已不可见。

执行步骤：

```bash
cd /path/to/mem0_dify_plugin
source .venv/bin/activate

# 1) 预览待删除目标（推荐先执行）
python tests/cleanup_seed_residuals.py --env-file tests/.env.local

# 2) 执行删除并验证
python tests/cleanup_seed_residuals.py --env-file tests/.env.local --execute

# 3) 异常场景强制全量清理（直连 Dify live scan）
python tests/cleanup_seed_residuals.py --env-file tests/.env.local --force-all --execute
```

常用参数：

- `--artifacts-dir <dir>`：指定 artifact 目录（默认取 `TEST_ARTIFACTS_DIR`，否则自动使用 `tests/artifacts/<profile>`）
- `--glob "<pattern>"`：指定 manifest 匹配模式（默认 `*manifest*.json`）
- `--force-all`：全量强制清理（异常兜底）
- `--no-verify`：跳过删除后验证（不建议，除非你只想快速回收）

可选环境变量（清理专用）：

- `DIFY_CLEANUP_USERS`：`force-all` 模式追加清理用户（与 manifest 用户合并去重）。

建议将该脚本作为 integration/acceptance 跑完后的固定步骤，减少残留风险。

也可以直接在统一入口里启用自动兜底：

```bash
./tests/run_tests.sh --suite integration --env-file tests/.env.local --cleanup manifest

# 异常场景：执行强制全量清理
./tests/run_tests.sh --suite integration --env-file tests/.env.local --cleanup force-all
```

---

## GitHub Actions 手动触发完整真实环境测试

当前 `/.github/workflows/ci.yml` 策略：

- `push/pull_request`：默认只跑 `unit`
- 真实环境套件需要手动触发

操作步骤：

1. 打开 GitHub -> Actions -> CI
2. 点击 `Run workflow`
3. 勾选 `run_real_env_suites = true`
4. 运行后观察真实环境相关 job（以当前 `ci.yml` 为准）：
   - `integration-dify`
   - `acceptance-workflow`

缺少 secrets 时 job 会显式 skip，不会影响 unit 结果。

CI 建议：仅配置仓库/环境 secrets，不创建或提交任何 `tests/.env*` 文件。

---

## 故障排查（按优先级）

### 1) 连接失败 / preflight 失败

- 检查 `DIFY_*_BASE_URL` 与 API KEY
- remote/ci 场景建议始终加 `--require-network`
- local 场景不想失败可设 `REQUIRE_DIFY_NETWORK=0`

### 2) workflow 卡住

- 提高 `DIFY_WORKFLOW_MAX_WAIT`
- 检查 `DIFY_STALL_TIMEOUT`
- 查看 `workflow-failure-*` artifact 里的错误上下文

### 3) Mem0 凭据问题

- acceptance 要求至少 LLM/Embedder/Vector DB 配置
- 缺失会 skip 或失败（取决于场景）

### 4) fork 下终端输出不完整

- 使用 `--output-file` 保存完整日志
- 同时查看 artifact JSON

---

## 新人建议执行路径（最稳）

1. `--check-env`
2. 先跑 `unit`
3. 准备 `.env.local` / `.env.remote`
4. 跑 `integration`
5. 跑 `acceptance`
6. 若失败，按“日志 -> artifact -> env”顺序排查

---

## 相关文档

- `tests/TESTING_COVERAGE.md`：覆盖面与缺口
- `tests/TESTING_TECHNICAL_GUIDE.md`：技术机制与设计细节

