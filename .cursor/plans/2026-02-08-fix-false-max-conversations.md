目标
- 修正 max_conversations 触发条件，避免“假早停”

计划
- 在 scan_user_conversations_incremental 中仅当有更多会话时返回 max_conversations_reached
- 更新相关单元测试覆盖 has_more=false 的完成场景

涉及文件
- utils/extraction.py
- tests/unit/utils/test_dify_incremental_scan.py

