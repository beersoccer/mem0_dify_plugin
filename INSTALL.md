# Mem0 Dify Plugin v0.0.7 - 安装指南

## 📦 安装步骤

### 1. 获取插件包

插件已打包为 `.difypkg` 文件（版本号以实际发布为准）：
- **文件名**: `mem0-0.0.7.difypkg`
- **大小**: ~600KB
- **位置**: Releases 页面

### 2. 上传到 Dify

#### 方法 A：通过 Dify 管理界面（推荐）

1. **登录 Dify**
   - 访问你的 Dify 实例（自建或 Dify 云）
   - 例如：`https://your-dify-instance.com` 或 `https://cloud.dify.ai`

2. **进入插件管理**
   - 导航到 **Settings** → **Plugins**
   - 或直接访问 `/plugins` 路径

3. **上传插件**
   - 点击 **"Upload Plugin"** 或 **"安装插件"** 按钮
   - 选择 `mem0-0.0.7.difypkg` 文件
   - 等待上传和安装完成

4. **配置本地模式凭证**
   - 安装完成后，点击插件的配置按钮
   - 在 Provider 凭证中填写以下 JSON：
     - 必填：`local_llm_json`、`local_embedder_json`、`local_vector_db_json`
     - 可选：`local_graph_db_json`、`local_reranker_json`
   - 保存配置

#### 方法 B：使用 Dify CLI（如果可用）

```bash
# 如果你有 dify-cli 工具
dify plugin install mem0-0.0.7.difypkg
```

---

## 🔧 本地配置示例

### 示例：pgvector（推荐在 `local_vector_db_json` 中设置维度）
```json
{
  "provider": "pgvector",
  "config": {
    "connection_string": "postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require",
    "collection_name": "mem0",
    "embedding_model_dims": 1536,
    "metric": "cosine"
  }
}
```

### 示例：Azure OpenAI 向量模型（`local_embedder_json`）
```json
{
  "provider": "azure_openai",
  "config": {
    "model": "text-embedding-3-small",
    "azure_kwargs": {
      "api_version": "2024-10-21",
      "azure_deployment": "text-embedding-3-small",
      "azure_endpoint": "https://<your-endpoint>.cognitiveservices.azure.com/",
      "api_key": "<your-azure-key>"
    }
  }
}
```

---

## ✅ 验证安装

安装完成后，你应该能看到以下 8 个工具：

### 核心功能工具
1. ✅ **Add Memory** - 添加记忆（异步入队，立即返回）
2. ✅ **Search Memory** - 搜索记忆（本地模式过滤器与 top_k）
3. ✅ **Get All Memories** - 获取所有记忆
4. ✅ **Get Memory** - 获取单条记忆详情
5. ✅ **Update Memory** - 更新记忆
6. ✅ **Delete Memory** - 删除单条记忆
7. ✅ **Delete All Memories** - 批量删除记忆
8. ✅ **Get Memory History** - 查看记忆历史

---

## 🧪 快速测试

### 测试 1：添加记忆
```json
{
  "user": "I love Italian food",
  "assistant": "Great! I'll remember that.",
  "user_id": "test_user_001",
  "metadata": "{\"category\": \"food_preferences\"}"
}
```

### 测试 2：搜索记忆
```json
{
  "query": "What food does the user like?",
  "user_id": "test_user_001",
  "top_k": 5
}
```

### 测试 3：使用过滤器（本地模式）
```json
{
  "query": "user preferences",
  "filters": "{\"AND\": [{\"user_id\": \"test_user_001\"}]}"
}
```

---

## 🔧 故障排查

### 问题 1：上传失败
**原因**：文件损坏或格式不正确
**解决**：
```bash
# 重新生成插件包
cd /Users/howsun/Warp/dify/mem0-plugin-update
./build_package.sh
```

### 问题 2：工具无法使用
**原因**：本地 JSON 配置缺失或无效
**解决**：
1. 确认已填写必填项：`local_llm_json`、`local_embedder_json`、`local_vector_db_json`
2. 检查 JSON 结构是否为 `{ "provider": ..., "config": { ... } }`
3. 对于 pgvector，优先提供可用的 `connection_string`

### 问题 3：过滤器 JSON 报错
**原因**：JSON 格式错误
**解决**：
- 确保 `filters` 参数是有效的 JSON 字符串
- 使用在线 JSON 验证器检查格式
- 参考 CHANGELOG.md 中的示例

### 问题 4：HTTP 超时
**原因**：数据库/图数据库连接问题
**解决**：
- 检查向量库（如 pgvector/pinecone）或图数据库（Neo4j）连接配置
- 确认凭证、地址与端口正确

---

## 📚 更多资源

- **插件更新日志**: 查看 `CHANGELOG.md`
- **Mem0 官方文档**: https://docs.mem0.ai
- **Dify 插件文档**: https://docs.dify.ai/docs/plugins
- **问题反馈**: 联系插件开发者

---

## 🔄 更新插件

### 从旧版本升级
如果你已经安装了旧版：

1. **备份数据**（可选）
   - 导出现有的记忆数据
   - 记录当前配置

2. **卸载旧版本**
   - 在 Dify 插件管理中卸载旧版本
   - 或使用 CLI：`dify plugin uninstall mem0`

3. **安装新版本**
   - 按照上述步骤安装 v0.0.7
   - 重新配置本地 JSON 凭证（LLM/Embedder/Vector DB）

4. **验证功能**
   - 测试 8 个工具
   - 验证过滤器与 `top_k`
   - 验证 `Add Memory` 异步入队是否正常

### 说明
- 插件仅支持 **Local-only** 模式（无 SaaS/API 版本参数）
- `Add Memory` 默认非阻塞（异步入队）；紧接着的搜索可能短暂不可见（最终一致）
- 插件内部使用单进程级后台事件循环并在退出时优雅清理（atexit/SIGTERM/SIGINT）

---

## 🎉 开始使用

安装完成后，你可以：

1. **在 Workflow 中使用**
   - 拖拽 Mem0 工具到工作流
   - 配置参数
   - 连接其他节点

2. **在 Agent 中使用**
   - 为 Agent 添加 Mem0 工具
   - Agent 将自动使用记忆功能
   - 支持长期记忆和上下文

3. **通过 API 调用**
   - 使用 Dify API 调用 Mem0 工具
   - 集成到你的应用中
   - 实现自定义记忆逻辑

---

## ⚠️ 重要提示

1. **API Key 安全**
   - 不要在公共场合分享 API Key
   - 定期更换 API Key
   - 使用环境变量存储敏感信息

2. **记忆管理**
   - 定期清理不需要的记忆
   - 使用 metadata 组织记忆
   - 注意记忆存储配额

3. **性能优化**
   - 使用 `top_k/limit` 控制返回数量（默认 5）
   - 合理使用过滤器减少查询范围
   - 插件内部使用单进程级后台事件循环与信号量限制并发
   - 进程退出时会优雅停止后台 loop

---

**祝你使用愉快！** 🚀

如有问题，请查看 CHANGELOG.md 或联系支持团队。
