---
trigger: glob
globs: .github/workflows/*.yml
---
# Rule: GitHub Actions (Glob: .github/workflows/*.yml)

## Principles
- Keep CI separate from release/publish workflows.
- CI should not require secrets; release/publish may require secrets.
- Use explicit Python version and cache uv where appropriate.

## Python
- Use Python 3.12 consistently across CI.
- Prefer caching uv downloads if CI runs frequently.

## Safety
- Never print secrets.
- Keep permissions minimal (contents: read by default).
