计划（查看工具资源管理对齐长期记忆工具）

- 查看工具禁用 keepalive，避免额外后台线程
- 保持独立池与显式 close，确保不影响其它工具
- 更新单测，断言 enable_keepalive=False

涉及文件：
- tools/get_user_checkpoint.py
- tools/check_extraction_status.py
- tests/unit/tools/test_get_user_checkpoint.py
- tests/unit/tools/test_check_extraction_status.py

