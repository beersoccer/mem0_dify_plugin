## Plan: Enforce /v1-only Dify base URL

- Update `DifyClient` to require `base_url` ending with `/v1`
- Remove redundant path-adjustment logic in `_get_json`
- Update unit/integration/e2e tests to use `/v1` base URL
- Adjust any test fixtures that previously accepted host-only URLs
- Run lint checks for touched files

