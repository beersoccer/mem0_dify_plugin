## Plan: docs + 版本号更新 + 提取任务查看工具说明

- 基于 `git diff HEAD` 归纳上次提交后的优化、增强与修复点
- 明确新版本号（在 `manifest.yaml` 与根目录文档保持一致）
- 更新 `CHANGELOG.md` 记录本次变更摘要（精简且与代码一致）
- 更新 `README.md`/`CONFIG.md`/`PR_TEMPLATE.md`/`PRIVACY.md` 的相关描述，避免冗余
- 在 `CONFIG.md` 增补 `check_extraction_status` 的配置说明并引用截图
- 复核文档对工具输出/参数/截图的引用是否与现有实现匹配

Files to touch:
- manifest.yaml
- CHANGELOG.md
- README.md
- CONFIG.md
- PR_TEMPLATE.md
- PRIVACY.md

