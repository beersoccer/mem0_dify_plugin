# 计划：统一任务状态的 __internal 过滤兼容性

- 阅读 `utils/task_status.py` 的保存/加载流程，确认过滤路径
- 调整 `task_status_filters()` 参数化 `__internal` 条件，避免过度依赖字符串格式
- 在加载与存在性检查中增加本地二次过滤，兼容 True/"true"
- 同步处理同步与异步管理器，确保行为一致
- 更新单元测试以匹配新的过滤行为

文件清单：
- `utils/task_status.py`
- `tests/unit/utils/test_task_status_filters.py`

