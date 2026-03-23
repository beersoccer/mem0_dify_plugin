---
name: dify-workflow-acceptance-blueprint
overview: 为 `mem0_dify_plugin` 制定一套兼容本地开发环境与 GitHub CI 的自动化测试整改蓝图，覆盖 Dify 真实环境接入、数据 seed/cleanup、超时治理、分层测试与 workflow 验收。
todos:
  - id: unify-test-profiles
    content: 设计并落地 local/remote/ci profile、环境变量命名与 preflight 规则
    status: completed
  - id: build-seed-cleanup-layer
    content: 实现 Chatflow seed manifest、Dify conversation cleanup 与 Mem0 全链路 cleanup 方案
    status: completed
  - id: refactor-real-env-tests
    content: 重构 extraction e2e 并新增 workflow acceptance 测试结构与 marker
    status: completed
  - id: harden-timeouts-and-runner
    content: 补齐 HTTP/轮询/pytest/job 级超时并升级 tests/run_tests.sh
    status: completed
  - id: wire-ci-jobs
    content: 改造 GitHub CI 分层 job、secrets 策略与日志工件上传
    status: completed
isProject: false
---

# Dify 自动化验收实施蓝图

## 进度快照（更新于 2026-03-12）

已完成（代码已落地）：

- `tests/helpers/dify_env.py` 已支持 `TEST_PROFILE=local|remote|ci`、localhost 策略与 preflight（chat/workflow）。
- `utils/dify_client.py` 已扩展 workflow run/detail、conversation delete，并统一请求超时与重试。
- `tests/helpers/` 已具备 `dify_seed.py`、`dify_cleanup.py`、`mem0_cleanup.py`、`workflow_runner.py`。
- 已新增分层真实环境测试：
  - `tests/integration/test_dify_seed_api.py`
  - `tests/integration/test_dify_seed_api.py`
  - `tests/e2e/test_extract_long_term_memory_seeded.py`
  - `tests/acceptance/test_workflow_plugin_smoke.py`
  - `tests/acceptance/test_workflow_memory_lifecycle.py`
- `tests/conftest.py` 已新增 marker：`dify_api`、`extraction_e2e`、`workflow_acceptance`、`requires_remote`。
- `tests/run_tests.sh` 已支持 `--suite` / `--profile` / `--require-network` / `--timeout`，并兼容缺失 `pytest-timeout` 的本地场景。
- `.github/workflows/ci.yml` 已拆分为 `unit`、`integration-dify`、`e2e-extraction`、`acceptance-workflow`，并支持仅手动触发重型真实环境套件。

实施结论：蓝图项已全部落地，当前进入维护阶段（按需补真实用例数据与环境参数）。

## 目标

建立一套可在本地与 GitHub CI 复用的真实环境自动化测试体系，覆盖：

- Dify Chat/Chatflow API 造数与清理
- 长期记忆抽取链路 (`extract_long_term_memory`) 的真实验收
- Dify Workflow 运行 (`POST /workflows/run`) 的真实验收
- Mem0 副作用（记忆、checkpoint、access_log、task_status）的可靠清理
- 超时与环境不可达场景的明确 fail/skip 策略

## 当前基线

当前实现基线（已更新）：

- [tests/run_tests.sh](/Users/beersoccer/workspace/mem0_dify_plugin/tests/run_tests.sh)：已具备 suite/profile/timeout 入口，作为本地与 CI 的统一执行入口。
- [tests/conftest.py](/Users/beersoccer/workspace/mem0_dify_plugin/tests/conftest.py)：已统一真实环境 marker 注册，兼容 `dify_plugin` 自动标记逻辑。
- [tests/helpers/dify_env.py](/Users/beersoccer/workspace/mem0_dify_plugin/tests/helpers/dify_env.py)：已承担 profile 解析、客户端创建、preflight 与 fail/skip 策略。
- [tests/helpers/dify_seed.py](/Users/beersoccer/workspace/mem0_dify_plugin/tests/helpers/dify_seed.py) 与 [tests/helpers/dify_cleanup.py](/Users/beersoccer/workspace/mem0_dify_plugin/tests/helpers/dify_cleanup.py)：已支持 seed manifest 与 conversation cleanup。
- [tests/helpers/mem0_cleanup.py](/Users/beersoccer/workspace/mem0_dify_plugin/tests/helpers/mem0_cleanup.py)：已支持 memories/checkpoint/access_log/lock/task_status 清理。
- [tests/helpers/workflow_runner.py](/Users/beersoccer/workspace/mem0_dify_plugin/tests/helpers/workflow_runner.py)：已支持 workflow run + polling + stall detection。
- [.github/workflows/ci.yml](/Users/beersoccer/workspace/mem0_dify_plugin/.github/workflows/ci.yml)：已拆分分层 job，重型真实环境套件默认手动触发。

## 设计原则

- 同一套测试代码复用，本地与 CI 只在环境 profile、是否强制联网、失败/跳过策略上分流。
- 真实环境测试必须先 preflight，再执行正式用例。
- 所有真实环境测试都必须自动 seed 与自动 cleanup，禁止依赖手工前置。
- Workflow 验收与 conversation seed 使用不同 app/api key，避免职责混淆。
- 所有网络操作必须有单请求超时、轮询总超时、无进展超时、pytest/job 级超时。
- cleanup 必须同时覆盖 Dify 会话与 Mem0 副作用，且在失败路径也执行。

## 分层测试结构

建议将测试体系拆为 4 层：

1. `unit`

- 仅纯逻辑，不连 Dify/Mem0/网络。
- PR 必跑，本地默认必跑。

1. `integration.dify_api`

- 验证 Dify Chat/Chatflow 数据面：seed、列会话、列消息、删会话、时间范围过滤。
- 主要回答“测试基础设施是否可用”。

1. `e2e.extraction`

- 验证 `extract_long_term_memory` 链路：读取 seed conversations -> 抽取 -> 写入 Mem0 -> checkpoint 更新 -> 清理。

1. `acceptance.workflow`

- 验证发布后的 Dify Workflow：`/workflows/run` -> 轮询 run detail -> 断言 outputs -> 校验插件副作用。

## 环境 Profile 方案

统一引入测试 profile 概念，而不是继续只用一个 `DIFY_BASE_URL`：

- `TEST_PROFILE=local`
  - 本地开发使用，允许 `localhost`
  - 真实环境测试默认可 skip（除非显式要求强制）
- `TEST_PROFILE=remote`
  - 手工连接远程测试环境时使用
  - 网络不可达默认 fail
- `TEST_PROFILE=ci`
  - GitHub Actions 使用
  - 有 secrets 的真实验收 job 必须 fail-fast；无 secrets 的 job 不创建或显式 skipped

建议拆分环境变量：

- `DIFY_CHAT_BASE_URL`, `DIFY_CHAT_API_KEY`：用于通过 Chat/Chatflow API 造 conversations/messages
- `DIFY_WORKFLOW_BASE_URL`, `DIFY_WORKFLOW_API_KEY`：用于 workflow 验收
- `DIFY_APP_ID`：抽取/插件隔离 app_id
- `DIFY_TEST_USERS`：测试用户集合
- `ALLOW_LOCALHOST_DIFY`：本地允许 localhost
- `REQUIRE_DIFY_NETWORK`：是否把网络不可达视为 fail
- `DIFY_HTTP_TIMEOUT`, `DIFY_POLL_INTERVAL`, `DIFY_WORKFLOW_MAX_WAIT`, `DIFY_STALL_TIMEOUT`：统一超时参数

## Seed / Cleanup 统一方案

### Seed

将你现有“性能脚本通过 Chatflow 批量造数”的流程升级为自动化 seed 层：

- 提炼为可由 pytest fixture 调用的 helper 或脚本包装器
- 支持参数：`run_id`、`user_prefix`、`conversation_count`、`messages_per_conversation`、`timeout`
- 返回 manifest：`run_id`、`user_ids`、`conversation_ids`、`created_at_window`
- 所有 seed 数据都加统一前缀或 metadata（若 API 支持），方便排查与 cleanup

### Cleanup

清理必须拆成两段：

1. Dify conversation cleanup

- 根据 seed manifest 中的 `conversation_id` 调 Dify 官方 `DELETE /v1/conversations/{conversation_id}`
- 删除后再查询验证不可见

1. Mem0 副作用 cleanup

- 普通记忆：按 `(user_id, agent_id/app_id)` 清 `delete_all`
- checkpoint：单独清理（不能假设 `delete_all` 覆盖）
- access_log：单独清理
- task_status：若 workflow/extraction 使用到则清理

建议 cleanup 顺序：

1. 删除 Dify conversations
2. 清普通 memories
3. 清 checkpoint
4. 清 access_log
5. 清 task_status

## 超时与可达性治理

### Preflight

所有真实环境 suite 在开始前先做一层 preflight：

- base_url 格式检查
- api_key 非空检查
- 一次轻量 API 探测（例如 `list_conversations(limit=1)`）
- profile-based 策略：
  - `local` + `REQUIRE_DIFY_NETWORK=0`：失败可 skip
  - `remote/ci` 或显式要求联网：失败直接 fail

### Timeout 体系

统一补 4 层超时：

- 单请求超时：复用并扩展 [utils/dify_client.py](/Users/beersoccer/workspace/mem0_dify_plugin/utils/dify_client.py)
- 轮询总超时：workflow run detail 最多等待 `max_wait_s`
- 无进展超时：状态或时间戳长期不变则 fail (`stall_timeout_s`)
- pytest/job 级超时：避免进程长期卡死

建议默认值：

- HTTP timeout: 20s
- workflow max wait: 120s
- poll interval: 2s
- stall timeout: 30s
- pytest timeout: integration 120s / e2e 300s / acceptance 180s

## 代码与目录落位建议

### 新增/重构 helpers

- [utils/dify_client.py](/Users/beersoccer/workspace/mem0_dify_plugin/utils/dify_client.py)
  - 扩展：`run_workflow_blocking()` / `get_workflow_run_detail()` / `delete_conversation()`
- 新增测试 helpers（建议放 `tests/helpers/`）
  - `dify_env.py`：统一 profile/env 读取与 preflight
  - `dify_seed.py`：包装 Chatflow/perf seed 逻辑
  - `dify_cleanup.py`：删除 conversations
  - `mem0_cleanup.py`：清理 memories/checkpoints/access_log/task_status
  - `workflow_runner.py`：workflow run + polling + timeout/stall detection

### 新增测试目录

- `tests/integration/test_dify_seed_api.py`
- `tests/integration/test_dify_seed_api.py`
- `tests/e2e/test_extract_long_term_memory_seeded.py`
- `tests/acceptance/test_workflow_plugin_smoke.py`
- `tests/acceptance/test_workflow_memory_lifecycle.py`
- `tests/fixtures/conversation_seed_cases.yaml`
- `tests/fixtures/workflow_cases.yaml`

### 收敛现有文件职责

- [tests/e2e/test_e2e_session_memory.py](/Users/beersoccer/workspace/mem0_dify_plugin/tests/e2e/test_e2e_session_memory.py)
  - 从“大而全演示式脚本”收敛成 extraction 专用 e2e
  - 移除手工前置依赖，改为 fixture 自动 seed
- [tests/e2e/cleanup_test_memories.py](/Users/beersoccer/workspace/mem0_dify_plugin/tests/e2e/cleanup_test_memories.py)
  - 拆分或下沉到 helper 层，只保留可复用 cleanup 逻辑
- [tests/conftest.py](/Users/beersoccer/workspace/mem0_dify_plugin/tests/conftest.py)
  - 新增 marker：如 `dify_api`, `extraction_e2e`, `workflow_acceptance`, `requires_remote`
  - 统一 skip/fail 决策，不再由各测试文件各自实现
- [tests/run_tests.sh](/Users/beersoccer/workspace/mem0_dify_plugin/tests/run_tests.sh)
  - 增加 suite/profile 参数，如 `--suite unit|integration|e2e|acceptance`、`--profile local|remote|ci`
  - 增加 preflight、timeout、日志输出、失败快照支持

## 本地与 CI 执行矩阵

### 本地开发

- 默认跑：`unit`
- 手动选择：`integration` / `e2e` / `acceptance`
- 若 profile=`local` 且 `REQUIRE_DIFY_NETWORK=0`，真实环境不可达可 skip

### GitHub CI

建议改造 [.github/workflows/ci.yml](/Users/beersoccer/workspace/mem0_dify_plugin/.github/workflows/ci.yml) 为分层 job：

- `unit`
- `integration-dify`
- `e2e-extraction`
- `acceptance-workflow`

策略：

- 普通 PR / push(main)：默认跑 `unit`（快速反馈）
- 手动 `workflow_dispatch` 且勾选 `run_real_env_suites=true`：执行 `integration-dify`、`e2e-extraction`、`acceptance-workflow`
- 若缺少必需 secrets：真实环境 job 显式 skip，不影响基础 CI
- 所有真实环境 job 统一上传：pytest log + 测试 artifact（seed manifest、cleanup log、workflow 失败摘要）

## 分阶段实施顺序

### Phase 1：稳定测试基础设施（已完成）

- 引入统一 profile/env loader
- 统一 preflight 逻辑
- 引入 pytest/job 超时
- 扩展 `tests/run_tests.sh` 支持 suite/profile

### Phase 2：打通数据生命周期（已完成）

- 将性能脚本/Chatflow 造数包装成 seed helper
- 实现 conversation delete cleanup
- 实现 Mem0 全链路 cleanup（普通记忆 + checkpoint + access_log + task_status）
- 用 manifest 追踪 test run

### Phase 3：重构 extraction e2e（已完成）

- 将现有 [tests/e2e/test_e2e_session_memory.py](/Users/beersoccer/workspace/mem0_dify_plugin/tests/e2e/test_e2e_session_memory.py) 改为 seed 驱动
- 拆分 connectivity / extraction / dataset 验证职责
- 加入 teardown-after-failure 保障

### Phase 4：新增 workflow acceptance（已完成）

- 扩展 [utils/dify_client.py](/Users/beersoccer/workspace/mem0_dify_plugin/utils/dify_client.py) 的 workflow API 能力
- 新增 smoke 与 memory lifecycle 两组 acceptance tests
- 加入 workflow polling + stall detection

### Phase 5：接入 CI（已完成）

- 改造 [.github/workflows/ci.yml](/Users/beersoccer/workspace/mem0_dify_plugin/.github/workflows/ci.yml)
- 区分 PR / main 常规 CI 与 dispatch 手动重型套件触发策略
- 接入 secrets、日志工件上传、失败摘要

## 风险与注意事项

- Dify Service API 创建的 conversations 与 WebApp 会话不共享，因此必须统一使用 API seed，不能再依赖 UI 或 WebApp 历史数据。
- `delete_all_memories` 不应被假设为会清内部 checkpoint/access_log；必须显式做内部 cleanup。
- `dify_plugin` 相关测试仍需 fork 隔离；新 marker 设计必须兼容 [tests/conftest.py](/Users/beersoccer/workspace/mem0_dify_plugin/tests/conftest.py) 的现有逻辑。
- 任何真实环境测试都必须保证 cleanup 在断言失败、超时、异常时仍执行。

## 验收标准

蓝图实施完成后，应达到：

- 本地开发可一键运行指定 suite，不连网时明确 skip，不会无限等待
- CI 可基于 profile/secrets 自动区分该跑哪些真实环境测试
- extraction 测试不再依赖手工前置造数
- workflow 验收能真实调用 Dify `/workflows/run`
- 所有真实环境测试都自动删除 Dify conversation，并清理 Mem0 副作用
- 任一网络/环境异常都能在受控超时内返回明确失败原因，而不是长时间挂起

