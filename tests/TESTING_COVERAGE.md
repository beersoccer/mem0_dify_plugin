# 测试覆盖现状（可用于评审与新人理解）

Last updated: 2026-04-16

## 如何阅读本文件

本文件回答三个问题：

1. **测了什么**：当前已经覆盖到哪些代码和场景。
2. **怎么测的**：每一层测试验证哪些行为。
3. **还缺什么**：已知风险和后续补齐建议。

---

## 覆盖模型总览

当前测试体系按三层组织：

- `unit`
  - 覆盖纯逻辑模块与边界处理。
- `integration`
  - 覆盖 Dify 数据面连通、增量扫描、时间窗口、seed 与 cleanup。
- `acceptance.workflow`
  - 覆盖真实 workflow 调用、轮询与副作用验证。

---

## 文件到能力映射

### Integration（Dify API 能力）

- `tests/integration/test_dify_seed_api.py`
  - 读取 `conversation_seed_cases.yaml`
  - 执行 seed -> cleanup 一体化流程
  - 断言 manifest 字段完整、删除后不可见
  - 写出 `integration-seed-*` 与 `integration-cleanup-summary-*` artifact
- `tests/integration/test_dify_integration.py`
  - 覆盖会话与消息列表读取、分页、鉴权异常
  - 覆盖增量扫描与 checkpoint 的核心行为
- `tests/integration/test_time_range_filtering.py`
  - 覆盖时间窗口过滤、边界条件和统计一致性

### Acceptance（workflow 验收）

- `tests/acceptance/test_workflow_plugin_smoke.py`
  - 加载 `workflow_cases.yaml:smoke`
  - 执行 workflow run
  - 轮询 run detail 到终态
  - 输出断言（key/contains/status）

- `tests/acceptance/test_workflow_memory_lifecycle.py`
  - 加载 `workflow_cases.yaml:memory_lifecycle`
  - 执行 workflow case
  - 按 case 断言最小 memory 数量
  - finally 中进行 Mem0 清理并输出 artifact

---

## Helper 能力覆盖（测试基础设施）

- `tests/helpers/dify_env.py`
  - profile 解析：`local|remote|ci`
  - preflight 探测：chat/workflow
  - skip/fail 策略：localhost 与网络策略

- `tests/helpers/dify_seed.py`
  - seed case 模板渲染
  - seed manifest 生成

- `tests/helpers/dify_cleanup.py`
  - conversation 删除
  - 删除后可见性验证

- `tests/helpers/mem0_cleanup.py`
  - memories/checkpoint/access_log/lock/task_status 清理

- `tests/helpers/workflow_runner.py`
  - workflow run + polling + timeout/stall
  - initial/final/failure artifact

---

## 单元测试覆盖摘要

`tests/unit/` 对核心逻辑保持高覆盖，重点包括：

- `utils/score_utils.py` -> `tests/unit/utils/test_score_utils.py`
- `normalize_search_results` -> `tests/unit/utils/test_normalize_search_results.py`
- `utils/memory_forgetting.py` -> `tests/unit/utils/test_memory_forgetting.py`
- `utils/dify_client.py` -> `tests/unit/utils/test_dify_client.py`
- `AsyncMem0Client.create()` mem0 兼容初始化 -> `tests/unit/utils/test_async_memory_init_compat.py`
- `provider/mem0ai.py` 异步凭证校验路由 -> `tests/unit/provider/test_mem0_provider_validation.py`
- `tools/forget_memories.py` -> `tests/unit/tools/test_forget_memories.py`
  - 覆盖 `dry_run` 行为（不执行删除/不落 access log）
  - 覆盖“部分删除失败”时仅按成功删除 ID 更新 access log
  - 覆盖真实执行下 checkpoint 去重清理逻辑
- 以及 extraction、checkpoint、retry、task_status、distributed_lock 等模块

---

## 目前已知缺口与风险

### 1) workflow fixtures 与环境配置一致性

- 当前 `tests/fixtures/workflow_cases.yaml` 中 smoke 与 memory_lifecycle 为启用状态
- 若在目标环境改为 `enabled: false` 或缺少必要环境变量，acceptance 仍会 skip

建议：在目标环境维护一份启用版 case（不要提交敏感数据）。

### 2) 真实环境稳定性依赖外部服务

- Dify/Mem0 可用性
- 网络抖动和响应时间
- 权限和数据隔离策略

建议：在 CI 使用固定测试窗口和专用测试用户。

### 3) 静态 lint 的 GitHub context 告警

- 编辑器可能提示 `vars/secrets` 相关 warning
- 这类告警通常不影响 Actions 真实执行

---

## 覆盖结论

- 蓝图要求的三层测试结构已落地。
- seed/cleanup 生命周期、preflight、超时治理已覆盖关键路径。
- artifact 机制已接入，满足失败定位与回放分析需求。

---

## 新人建议补测顺序

1. 先跑 `unit`
2. 再跑 `integration`
3. 最后 `acceptance`

如果新增功能跨层改动，至少新增：

- 1 个 unit（逻辑）
- 1 个 integration 或 acceptance（真实行为）

