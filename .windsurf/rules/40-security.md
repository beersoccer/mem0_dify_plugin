---
trigger: always_on
---
# Rule: Security & Secrets (Always On)

## Secrets
- Never commit secrets (API keys, passwords, tokens).
- .env files and private keys must be ignored by git and excluded from packaging.
- If configuration must store sensitive fields:
  - Use encrypted strings or environment-variable injection.
- For any change touching auth/credentials:
  - Add a short security note in the plan (risk + mitigation).

## Telemetry / analytics
- Do not remove or bypass telemetry disabling in main.py without a clear reason.
- If enabling telemetry for debugging:
  - gate behind explicit env var and keep default disabled
  - document in SPEC/PLAN and ensure secrets are not leaked
