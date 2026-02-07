## 计划

- 更新默认 `days_back` 与 `EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT` 常量
- 为扫描超出上限时新增会话续扫的 checkpoint 字段与逻辑
- 调整扫描函数的停止原因与统计字段以支持续扫
- 更新同步/异步流程保存与清理续扫游标
- 修正单元测试与配置说明中的默认值

## 涉及文件

- `utils/constants.py`
- `tools/extract_long_term_memory.py`
- `utils/extraction.py`
- `utils/checkpoint.py`
- `tests/unit/utils/test_dify_incremental_scan.py`
- `tests/unit/tools/test_extraction_parameters.py`
- `CONFIG.md`

