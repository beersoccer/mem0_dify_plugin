# Plan: docs + version bump + config update

## Scope
- Summarize post-last-commit optimizations/enhancements/bug fixes from git diff
- Bump version by +1 (manifest + changelog + README if needed)
- Update all root Markdown docs with concise, code-aligned notes
- Add check_extraction_status configuration section + screenshot in CONFIG

## Files to touch
- CHANGELOG.md
- README.md
- CONFIG.md
- PRIVACY.md (only if changes warrant mention)
- PR_TEMPLATE.md (only if template needs alignment)
- manifest.yaml

## Steps
1. Inspect git diff for functional changes across tools/utils/tests
2. Extract user-facing changes and bug fixes for changelog & README
3. Update CONFIG with check_extraction_status config + screenshot reference
4. Bump version (+1) consistently across versioned docs
5. Review root Markdown for accuracy and remove redundant text
