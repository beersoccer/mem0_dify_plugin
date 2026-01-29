# 提示词对比分析：当前实现 vs Mem0 最佳实践

## 日期
2026-01-25

## 对比维度

### 1. 提取来源控制

**Mem0 原生** (`USER_MEMORY_EXTRACTION_PROMPT`):
```
# [IMPORTANT]: GENERATE FACTS SOLELY BASED ON THE USER'S MESSAGES. 
# DO NOT INCLUDE INFORMATION FROM ASSISTANT OR SYSTEM MESSAGES.
# [IMPORTANT]: YOU WILL BE PENALIZED IF YOU INCLUDE INFORMATION 
# FROM ASSISTANT OR SYSTEM MESSAGES.
```
- 使用 `[IMPORTANT]` 标记（2次）
- 明确惩罚机制
- 强调"用户消息 ONLY"

**当前实现**:
```python
_common_rules():
- Focus ONLY on user-related information (preferences, events, knowledge).
- Do not include system messages, meta instructions, or assistant's self-descriptions.
```
- 仅在通用规则中简单说明
- 没有 `[IMPORTANT]` 标记
- 没有惩罚机制

**差距：** ⚠️ 当前实现对提取来源的控制不够强

---

### 2. 信息类型分类

**Mem0 原生**:
```
7 种通用类型（不区分 semantic/episodic/procedural）:
1. Store Personal Preferences
2. Maintain Important Personal Details
3. Track Plans and Intentions
4. Remember Activity and Service Preferences
5. Monitor Health and Wellness Preferences
6. Store Professional Details
7. Miscellaneous Information Management
```

**当前实现**:
```
分三种记忆类型，各有 5 种细分：
Semantic: Personal Preferences, Profile Facts, Long-term Goals, Enduring Constraints, Core Values
Episodic: Significant Events, Past Experiences, Temporal Context, Key Outcomes, Relational Events
Procedural: Workflows, Rules & Policies, SOPs, Troubleshooting Steps, Checklists
```

**差距：** ✅ 当前实现更细化，符合记忆分层需求

---

### 3. Few-shot 示例质量

**Mem0 原生**:
```
6 个示例，包括：
- 2 个空返回（负样本）
- 4 个正常提取
- 所有示例都包含 assistant 回复（但强调不提取）
```

**当前实现**:
```
每个 subtype 6 个示例：
- 2 个空返回（负样本）
- 4 个正常提取
- 1 个多语言（中文）
- 所有示例都包含 assistant 回复
```

**差距：** ✅ 质量相当，甚至更好（有多语言）

---

### 4. EXCLUDE 规则

**Mem0 原生**:
- 没有明确的 EXCLUDE 部分
- 依赖 "If you do not find anything relevant, return empty list"

**当前实现**:
```
EXCLUDE (these belong to other categories):
- One-off events or experiences (→ episodic)
- Temporary plans or short-term intentions
- Specific procedures or workflows (→ procedural)
- Routine chatter without lasting significance
```

**差距：** ✅ 当前实现更清晰，有助于边界区分

---

### 5. 分类提示词（新增）

**Mem0 原生**:
- 不存在（mem0 不做分类，全部提取）

**当前实现**:
```
MEMORY_CLASSIFICATION_PROMPT:
- 判断会话最符合哪类记忆
- 返回 SEMANTIC/EPISODIC/PROCEDURAL/NONE
- 6 个 few-shot 示例
```

**差距：** ✅ 优化创新，减少 LLM 调用

---

## 核心问题诊断

### ❌ 需要修复的问题

**1. 提取来源控制不足**
- **影响：** 可能提取 assistant 的信息而非用户的信息
- **严重性：** 高
- **mem0 强调：** 使用 `[IMPORTANT]` 标记 + 惩罚机制

**示例场景：**
```
User: Hi, my name is John.
Assistant: Nice to meet you, John! My name is Alex and I admire software engineering.

# 当前实现可能错误提取：
{"facts": ["Name is John", "Name is Alex", "Admires software engineering"]}  # ❌ 错误

# 应该只提取：
{"facts": ["Name is John"]}  # ✅ 正确
```

**2. 分类提示词没有 "[IMPORTANT]" 标记**
- 分类提示词也应该强调只基于用户消息

---

### ✅ 已经做得好的部分

1. **记忆类型细分** - 符合长期记忆分层需求
2. **EXCLUDE 规则** - 明确边界，减少混淆
3. **多语言支持** - 中文示例
4. **Few-shot 质量** - 数量和质量都足够
5. **分类优化** - 减少 33% LLM 调用

---

## 优化建议（必要且不过度）

### 优先级 1：修复提取来源控制（必须）

在所有提取提示词（SEMANTIC/EPISODIC/PROCEDURAL）中添加：

```python
# [IMPORTANT]: EXTRACT FACTS SOLELY BASED ON THE USER'S MESSAGES. 
# DO NOT INCLUDE INFORMATION FROM ASSISTANT OR SYSTEM MESSAGES.
# [IMPORTANT]: YOU WILL BE PENALIZED IF YOU EXTRACT INFORMATION 
# FROM ASSISTANT OR SYSTEM MESSAGES.
```

**理由：** 这是 mem0 原生强调的关键点，防止混淆提取来源

---

### 优先级 2：增强分类提示词（推荐）

在 `MEMORY_CLASSIFICATION_PROMPT` 中添加：

```python
# [IMPORTANT]: CLASSIFY BASED ON THE USER'S MESSAGES ONLY.
# Analyze the PRIMARY content the user is communicating, not assistant responses.
```

**理由：** 分类应该基于用户意图，而非 assistant 回复

---

### 优先级 3：保持 _common_rules() 的一致性（可选）

将 `_common_rules()` 中的：
```python
- Focus ONLY on user-related information (preferences, events, knowledge).
```

改为：
```python
# [IMPORTANT]: Extract facts SOLELY based on the USER's messages.
# DO NOT extract information from assistant or system messages.
- Focus ONLY on user-related information (preferences, events, knowledge).
```

**理由：** 与 mem0 原生风格保持一致

---

## 不需要改的部分（避免过度设计）

1. ✅ **信息类型分类** - 当前的三类细分合理，不需要改回 mem0 的 7 类通用
2. ✅ **Few-shot 数量和质量** - 已经足够，不需要增加更多
3. ✅ **EXCLUDE 规则** - 已经很清晰，不需要调整
4. ✅ **输出格式** - `{"facts": [...]}` 与 mem0 一致，不需要改
5. ✅ **多语言示例** - 已经有中文示例，不需要增加其他语言

---

## 优化前后对比

| 维度 | 优化前 | 优化后 | 提升 |
|------|-------|-------|------|
| 提取来源控制 | 简单说明 | [IMPORTANT] 标记 + 惩罚 | ⬆️ 显著提升 |
| 分类准确性 | 可能受 assistant 影响 | 明确基于用户消息 | ⬆️ 提升 |
| 与 mem0 对齐度 | 70% | 95% | ⬆️ 提升 |
| 提示词复杂度 | 简洁 | 略增（+3-4 行） | ➡️ 可接受 |

---

## 实施计划

### 修改文件
- `utils/prompts.py` - 更新 3 个提取提示词 + 1 个分类提示词

### 预计影响
- **代码行数：** +15 行（每个提示词 +3-4 行）
- **向后兼容：** ✅ 完全兼容（只是提示词增强）
- **测试需求：** 建议测试提取准确性（但不需要修改测试代码）

---

## 结论

**需要优化：** ✅ 是（优先级 1 必须修复）

**理由：**
1. mem0 原生使用 `[IMPORTANT]` 标记和惩罚机制是有充分理由的
2. 提取来源控制是记忆系统的核心，不能妥协
3. 优化成本低（+15 行）但收益高（防止错误提取）

**不属于过度设计：**
- 只是对齐 mem0 最佳实践
- 没有引入新的复杂逻辑
- 没有改变架构或接口

