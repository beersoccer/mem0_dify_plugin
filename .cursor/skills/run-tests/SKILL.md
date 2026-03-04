---
name: run-tests
description: Runs the mem0_dify_plugin test suite (unit, integration, e2e). Use when the user wants to run tests, verify changes, check coverage, or mentions unit tests, integration tests, e2e, pytest, or test gaps.
---

# mem0_dify_plugin 测试运行指南

## 项目路径

所有命令均在项目根目录执行：`/Users/beersoccer/workspace/mem0_dify_plugin`

## 测试目录结构

```
tests/
├── unit/
│   ├── tools/     # 10 个测试文件（工具函数测试）
│   └── utils/     # 16 个测试文件（工具类测试）
├── integration/   # 2 个测试文件（Dify API 集成）
└── e2e/           # 1 个测试文件（端到端会话记忆）
```

## 快速命令

```bash
# 激活虚拟环境（必须先执行）
source .venv/bin/activate

# 单元测试（全部）
pytest tests/unit/ -v

# 集成测试
pytest tests/integration/ -v

# 端到端测试
pytest tests/e2e/test_e2e_session_memory.py -v -s

# 全部非 E2E 测试（快速回归）
pytest tests/unit/ tests/integration/ -v
```

## 运行规则

### 单元测试和集成测试
直接运行，无需特殊参数：
```bash
source .venv/bin/activate
pytest tests/unit/ -v
pytest tests/integration/ -v
```

### 端到端测试（包含 dify_plugin 导入）
E2E 测试导入了 `dify_plugin`，在 macOS 上使用 `--forked` 需要设置环境变量：

```bash
# 方式1：直接运行（会有 gevent 警告，但不影响结果）
source .venv/bin/activate
pytest tests/e2e/test_e2e_session_memory.py -v -s

# 方式2：使用 fork 模式避免警告（macOS 需要设置环境变量）
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
pytest --forked tests/e2e/test_e2e_session_memory.py -v -s

# 方式3：使用统一脚本（Cursor agent 推荐）
./tests/run_tests.sh --e2e test_01_verify_dify_connectivity -v -s
```

## 常用筛选

```bash
# 按标记筛选（跳过慢测试）
pytest -m "not slow" -v

# 运行需要 dify_plugin 隔离的测试
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
pytest --forked -m dify_plugin -v -s

# 运行特定文件
pytest tests/unit/tools/test_extract_long_term_memory.py -v
pytest tests/unit/utils/test_checkpoint.py -v

# 运行特定测试函数
pytest tests/unit/tools/test_extract_long_term_memory.py::test_parse_user_ids_variants -v

# 运行特定 E2E 测试
pytest tests/e2e/test_e2e_session_memory.py::TestE2ESessionMemory::test_01_verify_dify_connectivity -v -s
```

## 测试文件速查表

### unit/tools/（10 个文件）

| 测试文件 | 对应模块 |
|---------|---------|
| `test_extract_long_term_memory.py` | 辅助函数、去重与时间比较 |
| `test_extraction_async.py` | 异步抽取、并发处理 ⚠️ 需 --forked |
| `test_extraction_parameters.py` | 参数验证、时间范围 ⚠️ 需 --forked |
| `test_token_truncation.py` | Token 截断逻辑 ⚠️ 需 --forked |
| `test_time_range_expansion.py` | 时间范围扩展 |
| `test_search_with_filters.py` | 搜索过滤器 |
| `test_check_extraction_status.py` | 任务状态展示与格式化 |
| `test_get_user_checkpoint.py` | 用户 Checkpoint 查询 |
| `test_add_memory_overload_guard.py` | 记忆添加过载保护 |
| `test_update_memory.py` | 记忆更新 |

### unit/utils/（16 个文件）

| 测试文件 | 对应模块 |
|---------|---------|
| `test_dify_incremental_scan.py` | 增量扫描逻辑、分页 |
| `test_checkpoint.py` | Checkpoint 持久化 |
| `test_distributed_lock.py` | 分布式锁 |
| `test_retry.py` | 重试机制 |
| `test_bg_task_tracking.py` | 后台任务跟踪 |
| `test_async_local_client_read_timeout.py` | 异步客户端超时 |
| `test_idempotency.py` | 幂等性 |
| `test_dify_client.py` | Dify 客户端基础行为 |
| `test_mem0_client_config_override.py` | Mem0 配置覆盖 |
| `test_mem0_client_llm_compat.py` | LLM 兼容补丁 |
| `test_mem0_extraction_logging.py` | 分类日志等级 |
| `test_message_utils.py` | 消息规范化与统计 |
| `test_prompts.py` | Prompt 约束 |
| `test_task_status_async.py` | 任务状态异步更新 |
| `test_task_status_filters.py` | 任务状态过滤器 |
| `test_overload_guard_preenqueue.py` / `test_performance_user_ids.py` 等 | 其余专项测试 |

### integration/（2 个文件）

| 测试文件 | 说明 |
|---------|------|
| `test_dify_integration.py` | Dify API 集成（20+ 个测试） |
| `test_time_range_filtering.py` | 真实 Dify 数据的时间范围过滤 |

## E2E 测试列表

| 测试方法 | 说明 | 是否需要外部服务 |
|---------|------|----------------|
| `test_01_verify_dify_connectivity` | 验证 Dify API 连接 | 是（Dify） |
| `test_02_fetch_all_conversations_and_messages` | 获取所有会话和消息统计 | 是（Dify） |
| `test_03_extract_long_term_memory_simple` | 单会话记忆抽取 | 是（Dify + Mem0） |
| `test_04_extract_memory_from_test_dataset` | 使用本地数据集验证（**离线可运行**） | 否 |

> `test_04` 使用 `tests/e2e/test_conversation_data.json` 本地数据，不依赖外部服务，推荐优先运行。

## 当前测试覆盖缺口

修改代码后，如果涉及以下模块，需要补充测试：

| 优先级 | 模块 | 缺少的测试 |
|--------|------|-----------|
| 🔴 高 | `utils/mem0_extraction.py` 会话分类 | `classify_conversation_memory_type` 未有专门单元测试 |
| 🔴 高 | 错误处理和恢复 | Dify API 超时、Mem0 添加失败、Checkpoint 保存失败 |
| 🟡 中 | 并发用户处理 | 信号量限制（5用户）、时间预算强制执行 |
| 🟡 中 | 边界条件 | 空会话、超长会话（>64K tokens）、只有未来消息的会话 |
| 🟢 低 | `utils/task_status.py` | 缺少专门单元测试 |
| 🟢 低 | `build_memory_metadata` 元数据构建 | 结构完整性验证 |

**当前覆盖率基线：**
- 核心逻辑：~75%（目标 >90%）
- 边界条件：~60%（目标 >80%）
- 错误处理：~50%（目标 >85%）
- 集成测试：~80%（目标 >90%）

## 环境配置检查

```bash
# 检查虚拟环境
./tests/run_tests.sh --check-env

# 确认 pytest 可用
source .venv/bin/activate && pytest --version

# 确认 pytest-forked 已安装
source .venv/bin/activate && pip list | grep pytest-forked
```

### tests/.env 必需变量（仅集成测试和 E2E 测试需要）

```bash
DIFY_BASE_URL=https://<your-dify-host>/v1   # 必须以 /v1 结尾
DIFY_API_KEY=<your-dify-api-key>
DIFY_USER_IDS=<user_a>,<user_b>
MEM0_LLM_CONFIG={"provider":"...","config":{...}}
MEM0_EMBEDDER_CONFIG={"provider":"...","config":{...}}
MEM0_VECTOR_DB_CONFIG={"provider":"pgvector","config":{"connection_string":"..."}}
```

## 故障排除

| 问题 | 解决方案 |
|------|---------|
| `ModuleNotFoundError: No module named 'pytest'` | `source .venv/bin/activate` 后重试 |
| `gevent MonkeyPatchWarning` | 加上 `export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES && pytest --forked ...` |
| macOS fork 崩溃 | 设置 `export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` |
| `--forked` 模式看不到输出 | 去掉 `--forked` 调试（会有警告），或用 `2>&1 \| tee tests/test_output.log` |
| `.env` 文件未找到 | 创建 `tests/.env` 并填写配置 |
| 虚拟环境不存在 | `uv venv && source .venv/bin/activate && uv sync` |

## 保存测试输出

```bash
# 保存到文件同时显示在终端
source .venv/bin/activate
pytest tests/e2e/test_e2e_session_memory.py -v -s 2>&1 | tee tests/test_output.log

# 使用统一脚本保存
./tests/run_tests.sh --e2e test_01_verify_dify_connectivity --output-file test_output.log
```

## 参考文档

- 详细测试说明：[tests/TESTING_README.md](../TESTING_README.md)
- 技术问题分析：[tests/TESTING_TECHNICAL_GUIDE.md](../TESTING_TECHNICAL_GUIDE.md)
- 测试覆盖分析：[tests/TESTING_COVERAGE.md](../TESTING_COVERAGE.md)
