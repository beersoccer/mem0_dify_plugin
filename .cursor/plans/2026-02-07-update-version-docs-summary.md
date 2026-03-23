# 计划：版本与文档同步（2026-02-07）

## 目标
- 汇总上次提交以来的优化、增强与修复点，并写入变更记录与对外说明
- 版本号 +1，并在所有根目录 Markdown 文档中同步信息
- 为 `check_extraction_status` 增补配置说明并引用截图

## 执行步骤（≤8）
1. 基于 `git diff` 提炼本次优化/增强/修复清单
2. 更新 `manifest.yaml` 与 `pyproject.toml` 版本号
3. 更新 `CHANGELOG.md` 的新版本条目
4. 更新 `README.md` 的版本与 “What’s New” 说明
5. 更新 `CONFIG.md` 中提取任务查看工具的配置说明与截图
6. 更新 `PR_TEMPLATE.md` 的版本说明与变更摘要
7. 更新 `PRIVACY.md` 的数据说明与更新时间

## 计划修改的文件
- `manifest.yaml`
- `pyproject.toml`
- `CHANGELOG.md`
- `README.md`
- `CONFIG.md`
- `PR_TEMPLATE.md`
- `PRIVACY.md`

