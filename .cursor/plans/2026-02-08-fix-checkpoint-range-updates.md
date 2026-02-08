目标
- 校验会话/消息排序的当前处理逻辑，并确保早停时不重复处理已处理消息

计划
- 确认会话列表使用 updated_at 倒序，消息列表最终按时间正序处理
- 增加统一的“最后消息”解析逻辑，支持 int/str 时间戳
- 即使 mem0 消息为空或跳过抽取，也更新会话级 checkpoint
- 维持 last_run_at 只在非早停时更新
- 补充单元测试验证 int created_at 能写入 processed_range_end

涉及文件
- tools/extract_long_term_memory.py
- tests/unit/tools/test_extraction_async.py

