# 测试指南

## 概述

本文档提供 mem0_dify_plugin 项目的完整测试指南，包括端到端测试、集成测试和单元测试的运行方法、环境配置和故障排除。

## 目录

- [快速开始](#快速开始)
- [环境配置](#环境配置)
- [端到端测试](#端到端测试)
- [集成测试](#集成测试)
- [单元测试](#单元测试)
- [测试数据集](#测试数据集)
- [测试覆盖](#测试覆盖)
- [故障排除](#故障排除)
- [性能基准](#性能基准)
- [验证要点](#验证要点)
- [Cursor Agent 使用说明](#cursor-agent-使用说明)
- [相关文档](#相关文档)

## 快速开始

### 手动运行测试（推荐）

**推荐方式**：手动激活虚拟环境后直接使用 pytest 命令：

```bash
# 1. 激活虚拟环境
source .venv/bin/activate

# 2. 运行测试
pytest tests/unit/ -v                                    # 所有单元测试
pytest tests/integration/ -v                            # 集成测试
pytest tests/e2e/test_e2e_session_memory.py -v -s       # 端到端测试
pytest --forked -m dify_plugin -v -s                    # dify_plugin 相关测试（需要 fork 模式）

# 运行特定测试文件
pytest tests/unit/tools/test_extract_long_term_memory.py -v

# 运行特定测试函数
pytest tests/unit/tools/test_extract_long_term_memory.py::test_parse_user_ids_variants -v

# 运行带标记的测试
pytest -m "not slow" -v
```

**为什么推荐手动方式？**
- ✅ 更灵活，可以使用所有 pytest 参数和选项
- ✅ 更直观，直接使用标准 pytest 命令
- ✅ 更高效，无需通过脚本包装
- ✅ 更符合 Python 开发习惯

### 使用辅助脚本（可选）

项目提供了统一的测试运行脚本 `run_tests.sh`，主要用于：
- 验证虚拟环境配置
- Cursor agent 自动执行测试
- 快速运行常见测试场景

```bash
# 检查虚拟环境配置
./tests/run_tests.sh --check-env

# 运行单元测试（自动激活虚拟环境）
./tests/run_tests.sh tests/unit/ -v

# 使用 fork 模式运行测试（避免 gevent monkey patching 冲突）
./tests/run_tests.sh --forked tests/e2e/ -v

# 运行端到端测试（自动使用 fork 模式）
./tests/run_tests.sh --e2e test_01_verify_dify_connectivity

# 运行测试并保存输出到文件
./tests/run_tests.sh --forked tests/e2e/ -v --output-file test_output.log

# 查看帮助信息
./tests/run_tests.sh --help
```

**脚本功能：**
- ✅ 自动检查虚拟环境是否存在
- ✅ 自动激活虚拟环境（如果未激活）
- ✅ 验证 pytest 和 pytest-forked 是否已安装
- ✅ 支持 fork 模式、E2E 模式等常见场景
- ✅ 支持输出重定向到文件

### 测试目录结构

测试文件已按类型组织到子目录：

```
tests/
├── unit/
│   ├── tools/          # 工具单元测试（7个文件）
│   └── utils/          # 工具类单元测试（9个文件）
├── integration/        # 集成测试（1个文件）
└── e2e/               # 端到端测试（1个文件）
```

## 环境配置

### 必需配置

在 `tests/.env` 文件中配置以下环境变量（不要提交到 git）：

```bash
# Dify配置
DIFY_BASE_URL=http://localhost/v1
DIFY_API_KEY=app-xxx
DIFY_USER_IDS=test_user,real_user
DIFY_APP_ID=xxx

# Mem0配置
MEM0_LLM_CONFIG={"provider":"azure_openai","config":{"model":"gpt-4","api_key":"...","base_url":"..."}}
MEM0_EMBEDDER_CONFIG={"provider":"azure_openai","config":{"model":"text-embedding-ada-002","api_key":"...","base_url":"..."}}
MEM0_VECTOR_DB_CONFIG={"provider":"pgvector","config":{"dbname":"mem0","user":"postgres","password":"...","host":"localhost","port":5432}}
```

### 可选配置

```bash
# 时间范围测试配置（可选）
TEST_START_TIME="2026-01-17T12:00:00Z"
TEST_END_TIME="2026-01-17T12:01:00Z"
```

### 环境要求

1. **Dify开发环境**
   - Dify服务已启动（通常在 `http://localhost`）
   - 包含测试用户数据：`test_user` 和 `real_user`
   - 每个用户至少有若干条会话和消息

2. **Mem0环境**
   - PostgreSQL数据库（带pgvector扩展）
   - LLM服务（Azure OpenAI / OpenAI）
   - Embedding服务

3. **Python依赖**
   - `pytest>=7.0.0`
   - `pytest-forked`（用于隔离 gevent monkey patching）
   - `pytest-asyncio`（用于异步测试）

## 端到端测试

### 测试文件

- `tests/e2e/test_e2e_session_memory.py` - 端到端会话级记忆测试（使用 fork 模式）

### 测试内容

#### 测试1: 验证Dify连接

验证能否成功连接到Dify API并获取用户数据。

```bash
# 手动方式（推荐）
source .venv/bin/activate
pytest --forked tests/e2e/test_e2e_session_memory.py::TestE2ESessionMemory::test_01_verify_dify_connectivity -v -s

# 或使用脚本
./tests/run_tests.sh --e2e test_01_verify_dify_connectivity -v -s
```

**预期输出:**
```
测试1: 验证Dify API连接
====================================
检查用户: test_user
  ✓ 成功获取会话列表
  - 会话数量: X
  - 是否有更多: True/False
  ✓ 成功获取消息列表
  - 消息数量: Y
```

#### 测试2: 获取所有会话和消息

扫描所有会话和消息，显示每个用户的统计信息。

```bash
# 手动方式（推荐）
source .venv/bin/activate
pytest --forked tests/e2e/test_e2e_session_memory.py::TestE2ESessionMemory::test_02_fetch_all_conversations_and_messages -v -s

# 或使用脚本
./tests/run_tests.sh --e2e test_02_fetch_all_conversations_and_messages -v -s
```

**预期输出:**
```
测试2: 获取所有会话和消息数据
====================================
用户: test_user
时间范围: 2026-01-18T00:00:00 到 2026-01-26T00:00:00

统计信息:
  - 扫描的会话数: X
  - 扫描的消息数: Y
  - 时间范围内的会话数: A
  - 时间范围内的消息数: B
  - 丢弃的未来消息数: 0
  - 停止原因: completed
```

#### 测试3: 简化的长期记忆抽取

测试单个会话的记忆抽取流程。

```bash
# 手动方式（推荐）
source .venv/bin/activate
pytest --forked tests/e2e/test_e2e_session_memory.py::TestE2ESessionMemory::test_03_extract_long_term_memory_simple -v -s

# 或使用脚本
./tests/run_tests.sh --e2e test_03_extract_long_term_memory_simple -v -s
```

**预期输出:**
```
测试3: 简化的长期记忆抽取测试
====================================
测试用户: test_user

会话信息:
  - 会话ID: abc123...
  - 消息数: 10
  - Token数: 1234

步骤1: 分类会话记忆类型...
  ✓ 分类结果: semantic

步骤2: 抽取 semantic 类型记忆...
  ✓ 成功抽取 3 条记忆
```

#### 测试4: 使用测试数据集验证记忆提取

使用 `test_conversation_data.json` 中的标准化测试数据验证记忆提取功能。

**测试内容:**
- 验证记忆分类准确性（分类结果应与预期类型匹配）
- 验证记忆提取成功性（应成功提取到记忆）
- 测试三类记忆类型（SEMANTIC、EPISODIC、PROCEDURAL）
- 测试中英文会话的处理能力

```bash
# 手动方式（推荐）
source .venv/bin/activate
pytest --forked tests/e2e/test_e2e_session_memory.py::TestE2ESessionMemory::test_04_extract_memory_from_test_dataset -v -s

# 或使用脚本
./tests/run_tests.sh --e2e test_04_extract_memory_from_test_dataset -v -s
```

**预期输出:**
```
测试4: 使用测试数据集验证记忆提取功能
================================================================================
加载了 6 个测试会话

============================================================
测试会话: conv_semantic_real_user_001
  用户: real_user
  预期类型: SEMANTIC
  消息数: 5
  Mem0消息数: 10

  步骤1: 分类会话记忆类型...
  ✓ 分类结果: SEMANTIC
  ✓ 分类正确！与预期类型匹配

  步骤2: 抽取 SEMANTIC 类型记忆...
  ✓ 成功抽取 5 条记忆
    [1] Prefers dark mode for applications...
    [2] Name is Alex...
    [3] Works as a software engineer...

================================================================================
测试摘要
================================================================================
总测试会话数: 6
成功处理会话数: 6
分类准确数: 6/6
成功提取记忆数: 6/6

按记忆类型统计:
  SEMANTIC:
    总数: 2
    分类准确: 2/2 (100.0%)
    成功提取: 2/2 (100.0%)
  EPISODIC:
    总数: 2
    分类准确: 2/2 (100.0%)
    成功提取: 2/2 (100.0%)
  PROCEDURAL:
    总数: 2
    分类准确: 2/2 (100.0%)
    成功提取: 2/2 (100.0%)

分类准确率: 100.0%
```

**优势:**
- 不依赖Dify API，可以离线运行
- 使用标准化测试数据，结果可复现
- 全面覆盖三类记忆类型
- 提供详细的统计信息，便于分析

### 运行所有E2E测试

```bash
# 手动方式（推荐）
source .venv/bin/activate
pytest --forked tests/e2e/test_e2e_session_memory.py -v -s

# 或使用脚本
./tests/run_tests.sh --e2e -v -s
```

## 集成测试

### 测试文件

- `tests/integration/test_dify_integration.py` - Dify API集成测试
- `tests/unit/tools/test_extraction_async.py` - 异步抽取测试（工具测试，但包含集成逻辑）

### 运行集成测试

```bash
# 手动方式（推荐）
source .venv/bin/activate
pytest tests/integration/test_dify_integration.py -v

# 异步抽取测试（需要 fork 模式）
pytest --forked tests/unit/tools/test_extraction_async.py -v

# 或使用脚本
./tests/run_tests.sh tests/integration/test_dify_integration.py -v
./tests/run_tests.sh --forked tests/unit/tools/test_extraction_async.py -v
```

### 集成测试内容

- ✅ Dify API连接和分页
- ✅ 会话和消息增量扫描
- ✅ Checkpoint持久化
- ✅ 消息格式转换
- ✅ 错误处理和重试
- ✅ 并发处理

## 单元测试

### 核心测试文件

#### 工具测试 (tests/unit/tools/)

| 测试文件 | 测试内容 | 测试数量 |
|---------|---------|---------|
| `test_extract_long_term_memory.py` | 辅助函数、消息规范化 | 19 |
| `test_extraction_async.py` | 异步抽取、并发处理 | 多组 |
| `test_extraction_parameters.py` | 参数验证、时间范围 | 多组 |
| `test_token_truncation.py` | Token截断逻辑 | 多组 |
| `test_time_range_filtering.py` | 时间范围过滤 | 多组 |
| `test_time_range_expansion.py` | 时间范围扩展 | 多组 |
| `test_search_with_filters.py` | 搜索过滤器 | 3 |

#### 工具类测试 (tests/unit/utils/)

| 测试文件 | 测试内容 | 测试数量 |
|---------|---------|---------|
| `test_dify_incremental_scan.py` | 增量扫描逻辑、分页 | 8 |
| `test_checkpoint.py` | Checkpoint持久化 | 5 |
| `test_distributed_lock.py` | 分布式锁 | 多组 |
| `test_retry.py` | 重试机制 | 多组 |
| `test_bg_task_tracking.py` | 后台任务跟踪 | 多组 |
| `test_async_local_client_read_timeout.py` | 异步客户端超时 | 多组 |
| `test_idempotency_fix.py` | 幂等性修复 | 多组 |
| `test_report_rendering.py` | 报告渲染 | 多组 |
| `test_log_analyzer.py` | 日志分析 | 多组 |

### 运行单元测试

```bash
# 手动方式（推荐）
source .venv/bin/activate
pytest tests/unit/ -v                    # 所有单元测试
pytest tests/unit/tools/ -v              # 工具测试
pytest tests/unit/utils/ -v              # 工具类测试

# 运行特定测试文件
pytest tests/unit/tools/test_extract_long_term_memory.py -v
pytest tests/unit/utils/test_dify_incremental_scan.py -v
pytest tests/unit/utils/test_checkpoint.py -v

# 或使用脚本
./tests/run_tests.sh tests/unit/ -v
./tests/run_tests.sh tests/unit/tools/test_extract_long_term_memory.py -v
```

## 测试数据集

### 测试会话数据

项目提供了标准化的测试数据集 `test_conversation_data.json`，用于测试三类会话级长期记忆功能。

#### 数据格式

- **文件位置**: `tests/test_conversation_data.json`
- **格式**: JSON，符合Dify API消息格式
- **编码**: UTF-8

#### 数据结构

每个会话包含：
- `conversation_id`: 会话唯一标识符
- `user_id`: 用户ID（`real_user` 或 `test_user`）
- `memory_type`: 记忆类型（`SEMANTIC`、`EPISODIC`、`PROCEDURAL`）
- `description`: 会话描述
- `messages`: 消息列表（3-5轮对话，围绕同一主题连贯展开）

消息格式支持Dify API的两种格式：
1. **query/answer 对格式**（当前使用）
2. **role/content 格式**（也支持）

#### 测试数据详情

**SEMANTIC（语义记忆）- 2个会话**
- `conv_semantic_real_user_001`: real_user英文会话，围绕个人偏好和身份信息（深色模式、素食、爱好、晨跑习惯）
- `conv_semantic_test_user_001`: test_user中文会话，围绕饮食习惯和个人偏好（咖啡、不吃辣、爱好、作息习惯）

**EPISODIC（情景记忆）- 2个会话**
- `conv_episodic_real_user_001`: real_user英文会话，围绕巴黎旅行经历（从计划到执行到回忆）
- `conv_episodic_test_user_001`: test_user中文会话，围绕上海出差经历（从准备到执行到总结）

**PROCEDURAL（程序记忆）- 2个会话**
- `conv_procedural_real_user_001`: real_user英文会话，围绕代码审查工作流程（深入讨论流程细节）
- `conv_procedural_test_user_001`: test_user中文会话，围绕文档写作流程（深入讨论流程细节）

#### 使用测试数据

```python
import json
from pathlib import Path

def load_test_conversations():
    """加载测试会话数据"""
    test_data_path = Path(__file__).parent / "test_conversation_data.json"
    with test_data_path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["conversations"]

# 使用示例
conversations = load_test_conversations()
for conv in conversations:
    print(f"会话ID: {conv['conversation_id']}")
    print(f"用户: {conv['user_id']}")
    print(f"记忆类型: {conv['memory_type']}")
    print(f"消息数: {len(conv['messages'])}")
```

#### 验证要点

使用测试数据时，应验证：
1. **记忆分类准确性**: 会话应被正确分类为对应的记忆类型
2. **提取准确性**: 提取的事实应与预期记忆类型匹配
3. **语言处理**: 
   - `real_user` 的英文内容应提取为英文事实
   - `test_user` 的中文内容应提取为中文事实
4. **对话连贯性**: 每个会话的对话应围绕同一主题连贯展开
5. **格式兼容性**: 消息格式应与Dify API返回的格式一致

## 测试覆盖

### 已覆盖的功能模块

1. **Dify API客户端** - 单元测试 + 集成测试
2. **增量扫描逻辑** - 完整的单元测试覆盖
3. **Checkpoint管理** - 单元测试 + 幂等性测试
4. **分布式锁** - 单元测试
5. **时间范围过滤** - 专门的测试文件
6. **Token截断** - 专门的测试文件
7. **消息格式转换** - 单元测试

### 测试覆盖度

- **核心逻辑覆盖率**: ~75%
- **边界条件覆盖率**: ~60%
- **错误处理覆盖率**: ~50%
- **集成测试覆盖率**: ~80%

### 需要补充的测试

1. **会话分类逻辑** - 需要LLM调用，建议使用mock
2. **错误处理和恢复** - 需要补充更多边界场景
3. **并发处理** - 需要更多压力测试
4. **性能测试** - 大规模数据处理场景

## 故障排除

### 问题1: Gevent Monkey Patching 冲突

**症状:**
```
MonkeyPatchWarning: Monkey-patching ssl after ssl has already been imported...
RuntimeError: cannot release un-acquired lock
```

**解决方案:**
使用 fork 模式运行测试：
```bash
pytest --forked -m dify_plugin -v -s
```

**详细说明:** 参见 [TESTING_TECHNICAL_GUIDE.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/tests/TESTING_TECHNICAL_GUIDE.md)

**⚠️ 输出捕获限制:**
- Fork 模式下，所有输出都会被捕获，测试通过时不会显示
- 这是 pytest-forked 的正常行为

**✅ 解决方案：将输出保存到文件**

1. **手动方式（推荐）**：
   ```bash
   source .venv/bin/activate
   pytest --forked tests/e2e/test_e2e_session_memory.py -v -s 2>&1 | tee test_output.log
   ```

2. **使用脚本**：
   ```bash
   ./tests/run_tests.sh --e2e test_01_verify_dify_connectivity --output-file test_output.log
   ```

**其他选项：**
- **调试时**：临时去掉 `--forked` 查看输出（会有 gevent 警告但不影响测试）
  ```bash
  source .venv/bin/activate
  pytest tests/e2e/test_e2e_session_memory.py -v -s
  ```
- **生产运行**：使用 `--forked` 确保完全隔离

### 问题2: "未找到 .env 文件"

**解决方案:**
```bash
# 创建 tests/.env 文件并填写配置
touch tests/.env
# 编辑填写配置...
```

### 问题3: "用户没有会话数据"

**解决方案:**
在Dify环境中为test_user和real_user创建测试会话和消息。

### 问题4: "Mem0连接失败"

**解决方案:**
检查以下配置：
- PostgreSQL数据库是否启动
- pgvector扩展是否安装
- LLM和Embedding服务是否可访问
- `tests/.env`中的配置是否正确

### 问题5: 测试运行很慢

**原因:**
- LLM推理需要时间（每个会话约2-5秒）
- 网络请求需要时间
- Token计数需要处理

**优化建议:**
- 减少测试用户数量
- 减少测试时间范围（使用1天而不是7天）
- 使用更快的LLM模型
- 使用并行执行：`pytest -n auto -v`

### 问题6: 导入错误 / No module named pytest

**症状:**
```
ModuleNotFoundError: No module named 'pytest'
```

**解决方案:**
手动激活虚拟环境（推荐）：
```bash
source .venv/bin/activate
pytest tests/unit/ -v
```

或直接使用虚拟环境的 pytest（无需激活）：
```bash
.venv/bin/pytest tests/unit/ -v
```

或使用脚本自动激活虚拟环境：
```bash
./tests/run_tests.sh tests/unit/ -v
```

### 问题7: 虚拟环境不存在

**解决方案:**
创建虚拟环境：
```bash
# 使用 uv（推荐）
uv venv

# 或使用 venv
python -m venv .venv
```

然后安装依赖：
```bash
source .venv/bin/activate
uv sync  # 或 pip install -r requirements.txt -r requirements-dev.txt
```

## 性能基准

基于测试数据规模的预期运行时间：

| 用户数 | 会话数 | 消息数 | 预期时间 |
|--------|--------|--------|----------|
| 2      | 10     | 100    | 1-2分钟  |
| 5      | 25     | 250    | 3-5分钟  |
| 10     | 50     | 500    | 6-10分钟 |

注意：实际时间取决于：
- LLM响应速度
- 网络延迟
- 数据库性能
- Token数量

## 验证要点

### Dify连接验证
- ✅ 能够成功连接到Dify API
- ✅ 每个测试用户至少有会话数据
- ✅ 会话至少包含消息数据

### 数据获取验证
- ✅ 正确统计会话数和消息数
- ✅ 时间范围过滤正确
- ✅ Token计数准确
- ✅ 未来消息被正确丢弃

### 记忆抽取验证
- ✅ 会话分类正确（semantic/episodic/procedural）
- ✅ 成功调用LLM进行记忆抽取
- ✅ 抽取的记忆数 > 0
- ✅ 记忆包含有意义的内容

### Checkpoint验证
- ✅ Checkpoint成功保存到Mem0
- ✅ Checkpoint包含正确的`last_run_at`时间
- ✅ 每个会话的checkpoint包含`last_processed_message_id`
- ✅ 每个会话的checkpoint包含时间范围信息

## Cursor Agent 使用说明

当 Cursor agent 需要运行测试时，可以使用统一的测试脚本：

```bash
./tests/run_tests.sh <选项> <测试路径或参数>
```

脚本功能：
1. 自动检查虚拟环境配置
2. 自动激活虚拟环境（如果未激活）
3. 验证 pytest 和依赖是否已安装
4. 支持 fork 模式、E2E 模式等常见场景

示例：
```bash
# 检查虚拟环境
./tests/run_tests.sh --check-env

# 运行所有单元测试
./tests/run_tests.sh tests/unit/ -v

# 运行特定测试文件
./tests/run_tests.sh tests/unit/tools/test_extract_long_term_memory.py -v

# 运行特定测试函数
./tests/run_tests.sh tests/unit/tools/test_extract_long_term_memory.py::test_parse_user_ids_variants -v

# 使用 fork 模式运行 e2e 测试
./tests/run_tests.sh --forked tests/e2e/ -v

# 运行端到端测试并保存输出
./tests/run_tests.sh --e2e test_01_verify_dify_connectivity --output-file test_output.log
```

**注意**：对于手动执行，推荐直接激活虚拟环境后使用 pytest 命令，更灵活高效。

## 相关文档

- [TESTING_TECHNICAL_GUIDE.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/tests/TESTING_TECHNICAL_GUIDE.md) - 技术问题分析和解决方案（Gevent Monkey Patching、Fork 模式等）
- [TESTING_COVERAGE.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/tests/TESTING_COVERAGE.md) - 详细的测试覆盖分析

## 下一步

测试通过后，可以：
1. 在生产环境中配置定时任务
2. 监控记忆抽取质量
3. 根据实际使用情况调整参数
4. 补充更多的单元测试

