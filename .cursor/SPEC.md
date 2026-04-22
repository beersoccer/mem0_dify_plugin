# SPEC

## Problem
为 Dify 自托管用户提供一个“**长期记忆巩固/归纳（memory consolidation）**”能力：在用户未显式要求“记住”的情况下，调用方只需传入 `run_at` + `user_ids`（可选 `app_id / max_users_per_run / budget_tokens`），插件即可**自动增量扫描**这些用户在 Dify 中的历史对话，抽取长期有用信息并写入 Mem0（semantic/episodic/procedural，以 metadata 标记 subtype）。

## Context (repo facts)
- Plugin manifest: `./manifest.yaml`
- Entry: `./main.py`
- Key modules: `./provider`, `./tools`, `./utils`
- 现状：已实现 10 个 Mem0 管理工具（8个基础工具 + 2个长期记忆工具，见 `AGENTS.md`）。基础工具以单次 user/assistant 输入为主，`extract_long_term_memory` 工具提供批量/定期从历史会话巩固长期记忆的能力（异步任务模式），`check_extraction_status` 工具用于查询异步任务状态和进度。
- Dify 会话/消息 API 能力边界（用于设计“等价增量”）：
  - 会话列表：支持 `sort_by=-updated_at` + `last_id` 分页；**不支持** `updated_at > t` 过滤。
  - 会话消息：支持 `first_id` + `limit` 倒序翻页；**不支持** `after_message_id` 或按时间区间过滤。
- Mem0 侧关键行为（用于决定 prompt/抽取实现）：
  - 在 “非 procedural（infer 抽取）”路径下，Mem0 使用 **config 级** `custom_fact_extraction_prompt` / `custom_update_memory_prompt` 控制抽取与更新；`add(..., prompt=...)` **不会**对 infer 路径生效（该 `prompt` 参数仅在 procedural memory 路径中用于替换 procedural system prompt）。
  - 因此若要分别产出 semantic/episodic/procedural 三类抽取（各自 prompt/策略不同），需要在工具内部准备 **3 组 MemoryConfig/Client**，对同一段对话分别执行三次 `add(infer=True)`，并以 `metadata.memory_subtype` 固定标记 subtype。
- 定位澄清：
  - 本能力对外叫“长期记忆巩固/抽取”，对内支持 `memory_subtype = semantic|episodic|procedural`。
  - 不强依赖 Mem0 原生 `memory_type="procedural_memory"` 路径（该路径更偏 agent 执行历史摘要），本方案以 infer 抽取 + subtype 标注为主。

## Scope
- In scope:
  - 新增 Dify 插件工具：`extract_long_term_memory`（异步任务模式）
    - 输入：`user_ids`、`app_id`、`dify_base_url`、`dify_api_key`，可选 `days_back / conversations_limit / max_tokens_per_conversation / time_budget`
    - 输出：立即返回 `task_id`，实际处理在后台异步执行
  - 新增 Dify 插件工具：`check_extraction_status`（查询异步任务状态）
    - 输入：`task_id`
    - 输出：任务状态、进度、统计信息、最终报告（如果已完成）
  - “等价增量”扫描策略（适配 Dify API 不支持服务端增量过滤的现实）
    - conversations：倒序扫描 + `conversation.updated_at <= user_checkpoint.last_run_at` 停止条件
    - messages：倒序翻页 + 遇到 `last_processed_message_id` 停止条件；丢弃 `created_at > run_at`
  - Checkpoint 存 Mem0（不依赖外部 DB）
    - 支持幂等、断点续跑、增量处理
    - checkpoint 作为 internal memory 写入，并在检索端默认过滤避免污染
  - 抽取与写入：
    - 记忆分 semantic/episodic/procedural，统一写入 Mem0（infer=True），通过 `metadata.memory_subtype` 标记 subtype
    - 具备会话分段（自动窗口），避免一次上下文过长
  - 预算与稳定性：
    - `max_users_per_run` 硬上限
    - `budget_tokens` 全局预算（优先级：semantic > episodic > procedural）
    - API 并发限制与失败隔离（单 user / 单会话失败不影响其他）
- Out of scope:
  - 插件内部常驻 cron/worker（Dify 插件容器生命周期不可控，不保证按时执行）
  - 外部筛选 user_id 的业务逻辑（由调用方决定，例如 VIP 用户）
  - 引入外部数据库/队列系统作为必须依赖（checkpoint 全存 Mem0）

## Constraints
- Backward compatibility:
  - 不改变现有 8 个工具语义与行为；仅新增工具与必要的 credentials 字段/配置项（如需要）
  - 复用现有 mem0 local 配置与 async 模式能力（write ops 可异步，read ops 同步等待）
- Security / privacy:
  - Dify API 访问凭证（`DIFY_BASE_URL` / `DIFY_API_KEY`）作为插件新增 tool 的独有配置，不放在 credentials 配置中
  - 仅处理入参 `user_ids` 指定用户；可选 `app_id` 进一步限定应用范围避免跨应用混入
  - checkpoint/internal memory 以 metadata 标识并在检索/注入上下文时默认过滤
  - 报告默认不回传原始对话内容，仅回传统计、ID 与时间范围；必要时可增加 debug 开关但默认关闭
- Performance:
  - 必须采用“倒序扫描 + checkpoint 停止条件”以降低无增量过滤情况下的扫描开销
  - 必须实现会话分段（按时间间隔/消息数/token 阈值）避免 prompt 过长
  - 必须实现 token 预算与优先级降级策略（先保 semantic，再 episodic，再 procedural）
- Reliability:
  - 幂等：同一 `run_at` 重跑不重复处理（checkpoint 保证）
  - 失败隔离：单 user / 单 conversation 失败不影响整体，返回 PARTIAL_SUCCESS 并记录错误原因
  - checkpoint 更新需避免生成多条（优先“更新同一条”），若失败需可重试且不会导致重复处理

## Design details (to be implemented)
### 1) 目标与定位
- **目标**：提供一个 Dify 插件工具，用户只需传入 `run_at` + `user_ids`（可选 `app_id / max_users_per_run / budget_tokens`），插件即可自动增量扫描这些用户在 Dify 中的历史对话，并抽取“长期有用信息”写入 Mem0 长期记忆。
- **定位**：长期记忆巩固/归纳（memory consolidation），不要求用户在对话中显式说“请记住”。

### 2) 对外接口（Dify 插件工具）
- 工具名：`consolidate_long_term_memory`

#### 入参（JSON）
- 必填：
  - `run_at`: string（ISO8601），本次抽取截止时间点；只处理 `created_at <= run_at` 的消息
  - `user_ids`: string[]，本次需要处理的用户列表（由外部业务筛选，例如 VIP）
- 可选：
  - `app_id`: string，限定只处理某个应用的会话（避免跨应用混入）
  - `max_users_per_run`: int，单次最多处理用户数（默认建议 100）
  - `budget_tokens`: int，单次运行 token 总预算（默认建议 200000）

#### 出参（JSON 报告）
- `status`: SUCCESS | PARTIAL_SUCCESS | ERROR
- `run_id`: 本次执行唯一标识（建议 `hash(run_at + sorted(user_ids) + app_id)`）
- `summary`: 用户处理数/跳过数、会话扫描数、消息扫描数、写入记忆条数（按 subtype 统计）、预算消耗
- `per_user`: 每个 user 的统计与错误原因（如有）
- `checkpoint_updates`: checkpoint 更新情况（成功/失败、失败原因）

### 3) 依赖与鉴权（自托管）
- 插件 tool 参数，非 credentials：
  - Dify API：`DIFY_BASE_URL`、`DIFY_API_KEY`（至少能调用会话列表与消息列表接口）
  - Mem0 local：沿用现有 local 配置（LLM/Embedder/Vector DB/Graph 可选等）

### 4) Dify 数据获取策略（等价增量）
- conversations：`sort_by=-updated_at` + `last_id` 分页倒序扫描
  - 停止条件：当扫描到 `conversation.updated_at <= user_checkpoint.last_run_at` 时停止继续翻页（更旧的都已处理）
  - `app_id`：若 API 不支持服务端过滤，则客户端过滤
- messages：`first_id` + `limit` 倒序翻页
  - 丢弃：`message.created_at > run_at`
  - 停止条件：`message.id == conversation_checkpoint.last_processed_message_id`（等价 after_id）
  - 收集：得到“本次新增消息集合”，按时间正序重排供抽取

### 5) Checkpoint（存 Mem0，不依赖外部 DB）
#### 5.1 存储形态
- checkpoint 作为 Mem0 内部控制 memory 写入，metadata 标识：
  - `meta.__internal = true`
  - `meta.internal_type = "checkpoint"`
  - `meta.checkpoint_key = "dify_consolidation_v1"`
  - `meta.user_id = <user_id>`
  - `meta.app_id = <app_id 或 "*">`
- 约束：internal memory 必须在检索端默认过滤（或至少注入上下文逻辑里过滤）。
- **实现状态**：当前所有读取工具（`search_memory`、`get_all_memories`、`get_memory`、`get_memory_history`）已默认过滤 `__internal=true`，确保 checkpoint 不污染用户检索结果。对于 `get_memory` 和 `get_memory_history`，如果查询的 memory_id 对应 internal memory，会直接返回 NOT_FOUND。

#### 5.2 数据结构（建议）
- `user_checkpoint`（user + app 维度）
  - `last_run_at`: string | null
  - `conversations`: dict（key=conversation_id）
    - `last_processed_message_id`: string | null
    - `last_processed_message_created_at`: string | null
    - `last_seen_updated_at`: string | null（可选）
  - `version`: "v1"

#### 5.3 读写策略
- 读取：用 Mem0 filters 精确定位（`user_id + app_id + checkpoint_key`）
- 更新：更新同一条 checkpoint memory（避免生成多条）；失败则返回 PARTIAL_SUCCESS 并记录告警信息

### 6) 核心执行流程（端到端）
对一次 `consolidate_long_term_memory(run_at, user_ids, ...)`：
1. 输入校验与预算初始化：校验 run_at、user_ids 去重、应用 max_users_per_run、初始化 remaining_budget_tokens
2. 按 user 处理（串行或小并发 + 锁，避免 checkpoint 竞争）
   - 读取 checkpoint；若 `checkpoint.last_run_at >= run_at` 则跳过（幂等）
3. 扫描会话列表（倒序）：分页拉取；遇到停止条件则结束
4. 扫描每个会话的新增消息（倒序翻页）：丢弃未来消息；遇到 last_processed_message_id 停止；得到新增消息集合
5. 会话分段（自动窗口）：按时间间隔/累计 token/消息数切段；每段生成 segment_id（可用 message_id 范围）
6. 三类长期记忆抽取（semantic / episodic / procedural）
   - 统一落库：写入普通 mem0 memory（infer=True），用 `metadata.memory_subtype` 标记 subtype
   - 实现方式：
     - 由于 infer 路径 prompt 为 config 级，工具内部准备 3 组 MemoryConfig/Client（同向量库配置，不同 prompt），对同一段分别调用三次 `add(...)`
   - 预算控制：每次抽取前估算 token；超预算跳过低优先级 subtype（procedural 最后）
7. 写入 metadata（可追溯）
   - `memory_subtype`, `source="dify_consolidation"`, `app_id`, `conversation_id`, `segment_id`, `run_at`, `extracted_at`, `message_id_range`, `schema_version`
8. 更新 checkpoint：按 conversation 写入 last_processed_*；更新 user last_run_at=run_at；写回 mem0
9. 输出报告：汇总 + per_user（含跳过原因、错误摘要、预算消耗）

### 7) 抽取 Prompt 设计（默认内置，可后续开放配置）
- 三类抽取 prompt 均输出 `{"facts": ["..."]}`，但约束不同：
  - semantic：只保留跨天仍成立的偏好/事实/约束/长期目标；排除一次性内容
  - episodic：只保留未来可能被问到/用于个性化的关键事件与结果；尽量含时间语境但避免过长
  - procedural：只保留明确可复用流程/规则/步骤；不满足则返回空
- 可选：轻量 gating（规则/关键词）决定是否执行 procedural 抽取以节省预算

### 8) 预算、限流与稳定性
- `max_users_per_run`：硬上限
- `budget_tokens`：全局预算；优先级 semantic > episodic > procedural
- API 限流：对 Dify 会话/消息 API 控制并发（N 可配置）
- 幂等：同一 run_at 重跑不重复处理（checkpoint）
- 部分失败：单 user / 单 conversation 失败不影响其他；返回 PARTIAL_SUCCESS 并在 per_user 记录失败原因

### 9) 使用方式（插件化通用）
- 在任意 Dify 应用/工作流中添加节点调用 `consolidate_long_term_memory`
- 外部业务系统按计划触发该工作流并传入：
  - `run_at`, `user_ids`
  - 可选 `app_id / max_users_per_run / budget_tokens`
- 外部触发可非常轻量（cron/CI/k8s CronJob 调用 Dify 工作流入口），外部只负责触发，不负责窗口/去重/抽取逻辑

## Acceptance criteria

### 已实现（v0.2.3）
- ✅ **正确性**：
  - ✅ 工具端到端可用：`extract_long_term_memory.py/.yaml` 和 `check_extraction_status.py/.yaml` 已实现并注册到 `provider/mem0ai.yaml`
  - ✅ 异步任务模式：工具立即返回 task_id，后台异步处理，支持并发处理多个用户（最多5个并发）
  - ✅ 智能记忆分类：每个会话只提取最相关的记忆类型，减少33%的LLM调用（从3次减少到2次：1次分类 + 1次提取）
  - ✅ Token感知处理：使用tiktoken进行精确token计数，在API分页阶段应用token限制以优化网络传输
  - ✅ 幂等性：同一 `run_at` 重跑不重复写入（checkpoint `last_run_at >= run_at` 跳过逻辑已实现）
  - ✅ 未来消息过滤：`created_at > run_at` 的消息被丢弃（`scan_new_messages_for_conversation` 已实现）
  - ✅ 三类抽取：semantic/episodic/procedural 产出并带 `memory_subtype` metadata（`build_subtype_memories` + `build_memory_metadata` 已实现）
  - ✅ Legacy checkpoint 迁移：旧 checkpoint（缺 `__internal` metadata）自动迁移为 internal memory（`load_checkpoint` 已实现）
- ✅ **可控性**：
  - ✅ `max_users_per_run` 生效：用户列表截断逻辑已实现
  - ✅ `budget_tokens` 生效：全局预算跟踪 + 优先级降级（semantic > episodic > procedural）已实现
  - ✅ 报告包含预算消耗与跳过原因
- ✅ **可观测性**：
  - ✅ 报告输出清晰：`status/run_id/summary/per_user/checkpoint_updates` 结构完整
  - ✅ 统计包含：扫描会话数、扫描消息数、写入记忆数（按 subtype）、预算消耗
- ✅ **可测试性**：
  - ✅ 测试已添加：`test_consolidate_long_term_memory.py`、`test_checkpoint.py`、`test_dify_incremental_scan.py`
  - ✅ `pytest -q tests` 本地通过（17 passed, 1 skipped）
  - ✅ CI 通过（ruff + pytest）
- ✅ **安全**：
  - ✅ checkpoint internal memory 不进入正常检索结果：所有读取工具默认过滤 `__internal=true`
  - ✅ `get_memory`/`get_memory_history` 对 internal memory 返回 NOT_FOUND

### 待优化（可选）
- ✅ **工具可见性**：`extract_long_term_memory` 和 `check_extraction_status` 已在 Dify UI 中可见
- ⚠️ **Prompt 质量**：`utils/prompts.py` 中三类抽取 prompt 字符串拼接存在多余引号字符，可能影响 LLM 抽取质量
- ⚠️ **Async 模式兼容**：工具当前直接使用 `Memory.from_config`（同步），未复用 `utils/mem0_client.py` 的 async/sync 统一封装
- ⚠️ **Procedural gating**：未实现关键词/规则 gating 以节省预算（SPEC 中标注为可选）
- ⚠️ **并发优化**：当前按 user 串行处理，未实现小并发（2~5）以提升吞吐
- ✅ **文档更新**：
  - README.md/CONFIG.md 已更新工具列表（10个工具）并补充 `extract_long_term_memory` 和 `check_extraction_status` 使用说明
  - AGENTS.md 已同步工具清单（10个工具）
  - CHANGELOG.md 和 manifest.yaml version 已更新到 v0.2.3

---

### 已实现（v0.3.0 — 2026-04-22）

- ✅ **Checkpoint 可靠性**：
  - `AsyncCheckpointManager.load()` 已恢复所有三个 resume cursor 字段（`resume_conversation_cursor`、`resume_run_at`、`resume_start_time`），修复了 async 模式下 `max_conversations_reached` 后续重跑无法续点的 P0 问题
  - Checkpoint `save()` 改为先 add 后 delete，避免 add 失败时误删旧 checkpoint；`load()` 通过取最新的记录安全处理临时重复条目
- ✅ **Distributed Lock 可靠性**：
  - `acquire_lock()` 写入后执行 read-after-write 验证，新增 `_load_all_locks(limit=5)` 方法重读所有活跃锁；最早 `acquired_at` 获胜，失败方自删（解决 Mem0 最终一致性窗口内的竞争问题）
  - `forget_memories` 新增 `_clean_expired_locks()` 清理过期分布式锁记录；返回结果增加 `locks_cleaned` 字段
- ✅ **测试隔离**：
  - `test_checkpoint.py` 中所有 async 路径改为 sync `def` + `_run_async()` 辅助函数，该函数在独立线程中通过 `asyncio.events._set_running_loop(None)` 清除继承的运行循环，彻底解决 pytest-asyncio AUTO 模式下 C 级 TSS 继承导致的 "Cannot run the event loop while another loop is running" 问题
- ✅ **Provider 兼容门控**：
  - 新增 `test_config_builder_providers.py`（117 个参数化测试）：89 个测试覆盖 LLM、Embedder、Vector DB、Reranker 的规范 provider 名称和关键配置字段；28 个测试交叉检验 mem0 工厂注册表，在 `mem0ai` 升级后新增/删除/重命名 provider 时立即失败
  - 从 `LLM_CONFIGS` 中移除无效的 `mistral` provider（该 provider 不在 mem0 `LlmFactory` 注册表中）
- ✅ **测试规模**：
  - 单元测试从 v0.2.12 的约 380 个增长到 **471 个**，全部通过（`pytest tests/unit/ -q`）
- ✅ **文档更新**：
  - AGENTS.md 同步工具清单（12个工具）、完整 utils 模块列表、测试目录结构及设计说明
  - SPEC.md 增加 v0.3.0 验收标准章节
  - CHANGELOG.md、README.md、CONFIG.md、manifest.yaml、pyproject.toml 版本更新到 v0.3.0
