目标
- 按窗口期过滤会话，只处理 start_time/end_time 内会话
- 取消基于 last_run_at 的扫描/跳过逻辑
- 保留现有消息级 checkpoint 去重机制

计划
- 更新 scan_user_conversations_incremental 的会话过滤与计数逻辑
- 移除 last_run_at 的 idempotency/停止扫描判断
- 调整并新增单元测试覆盖新的窗口过滤行为

涉及文件
- utils/extraction.py
- tools/extract_long_term_memory.py
- tests/unit/utils/test_dify_incremental_scan.py

