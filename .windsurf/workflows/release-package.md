# Workflow: Package Dify Plugin

1) Confirm versions:
   - manifest.yaml version matches CHANGELOG.md if user-facing change
2) Package:
   - ./build_package.sh  (if present)
   - or use dify plugin CLI per repo workflow
3) Validate artifact exists:
   - *.difypkg
4) If packaging fails:
   - inspect .difyignore and packaging logs
5) If CI/release workflow exists:
   - verify it references correct branch naming and PR head
