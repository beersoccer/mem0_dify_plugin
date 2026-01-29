---
trigger: always_on
---
# Rule: Dify Plugin Constraints (Suggested: Always On)

## Source of truth files
- manifest.yaml: name/version/author/metadata
- provider/*.yaml or tools/*.yaml: tool/provider definitions
- .difyignore: packaging excludes
- build_package.sh: packaging script (if present)

## Packaging
- Do not include secrets in repository or packaged artifacts.
- If packaging fails (size/ignored files), review .difyignore first.
- Prefer using documented Dify plugin packaging commands and structure.
- Ensure .difyignore excludes:
  - .env*, keys, local caches, tests (if packaging expects runtime-only)

## Versioning discipline
- If user-facing change:
  - Update CHANGELOG.md once per release
  - Keep manifest.yaml version consistent with CHANGELOG
- If internal-only change (CI/tests/refactor):
  - Do NOT bump manifest.yaml version unless required by your release process
