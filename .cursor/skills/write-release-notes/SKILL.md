---
name: write-release-notes
description: Updates all release documentation for a new version: CHANGELOG.md (new version block), README.md (title, Last updated, What's New rotation), PR_TEMPLATE.md (Key Updates), manifest.yaml (version field), and CONFIG.md (Last updated, conditionally Upgrade Guide). Use when the user asks to write release notes, update the changelog, update README for a new version, bump the version, or prepare a plugin submission.
---

# Write Release Notes

**Prerequisite**: The user must explicitly provide the new version number and a description of changes. Never infer or auto-bump versions (see `05-versioning.mdc`).

## Files to Update (in order)

### 1. `CHANGELOG.md`

Insert a new version block **at the top**, immediately after the `# Mem0 Dify Plugin - Changelog` heading.

**Block format:**
```markdown
## Version X.Y.Z (YYYY-MM-DD)

### <emoji> <Category Title>
- **<Change title>**:
  - Concise description (one line preferred)

---
```

**Emoji → Category mapping** (pick the relevant ones; omit unused):

| Emoji | Category |
|-------|----------|
| 🛡️ | Stability / Security |
| ⚡ | Optimizations / Performance |
| ✨ | Enhancements / New Features |
| 🐛 | Fixes |
| 🧱 | Infrastructure / Robustness |
| 🛠️ | Reliability & Compatibility |
| 📊 | Observability / Monitoring |
| 🔧 | Configuration / Defaults |

Add a `**Note:**` paragraph after the last section if there are known limitations or important caveats.

---

### 2. `README.md`

Three locations to update:

**a) Title line (line 1):**
```markdown
# Mem0 Dify Plugin vX.Y.Z
```

**b) `Last updated:` field (line 7):**
```markdown
Last updated: YYYY-MM-DD
```

**c) `What's New` section** — keep the **three most recent versions** visible, rotate older ones:

```markdown
### What's New (vX.Y.Z) - <Short Title> ✅
- **<Change title>**:
  - One-line description (keep concise vs CHANGELOG; omit low-level details)

These changes **<impact summary>**; <known limitation if any>.

### Previous Updates (vX.Y.(Z-1)) - <Previous Title> ✅
- **<Bullet 1>**
- **<Bullet 2>**
- **<Bullet 3>**

### Previous Updates (vX.Y.(Z-2)) - <Previous Title> ✅
- **<Bullet 1>**
...

### Previous Updates (vX.Y.(Z-3)) - <Previous Title>! 🛠️

For full historical details, see [CHANGELOG.md](...).
```

When rotating:
- Current "What's New" → becomes first "Previous Updates" block.
- First "Previous Updates" → becomes second "Previous Updates" block.
- Second "Previous Updates" → becomes third "Previous Updates" block (condensed to 3 bullets max).
- Third "Previous Updates" → collapsed into the final "For full historical details" line.

---

### 3. `PR_TEMPLATE.md`

Update only the **`### Key Updates`** section under **`## 3. Description`**:

```markdown
### Key Updates

- **<Category title>**: <One-line summary>
- **<Category title>**: <One-line summary>
```

Also update `Last updated: YYYY-MM-DD` on line 3.

Keep the rest of the template unchanged (metadata, submission type checkboxes, privacy policy are static).

---

### 4. `manifest.yaml`

Update the `version:` field on line 1:

```yaml
version: X.Y.Z
```

No other fields in `manifest.yaml` change during a routine version bump.

---

### 5. `CONFIG.md`

Always update `Last updated:` on line 3:

```markdown
Last updated: YYYY-MM-DD
```

**Conditionally** update content when this release includes:

| Trigger | Section to update |
|---------|------------------|
| New or renamed config parameters | Relevant config example blocks and parameter tables |
| Changed default values (timeouts, pool sizes, concurrency) | "Runtime Behavior" / "Connection Stability" sections; update the stated default values |
| Breaking config changes (removed/renamed fields) | `## Upgrade Guide` — add a new sub-section describing the migration path |

If none of the above apply, only update `Last updated:` and leave the rest unchanged.

---

## Checklist

```
- [ ] CHANGELOG.md: new block inserted at top, correct emoji/format
- [ ] README.md: title and Last updated updated
- [ ] README.md: What's New replaced; Previous Updates rotated correctly
- [ ] PR_TEMPLATE.md: Key Updates and Last updated refreshed
- [ ] manifest.yaml: version field updated
- [ ] CONFIG.md: Last updated refreshed; content updated if config/defaults changed
- [ ] No version numbers changed anywhere except what user explicitly approved
```

## Tone & Style

- CHANGELOG: detailed, technical, developer audience.
- README What's New: concise, user-facing, omit internal implementation details.
- PR_TEMPLATE Key Updates: one-liner per category, reviewer audience.
- CONFIG.md: instructional, operational, user-facing; keep examples runnable.

## Files NOT updated at release time

- `PRIVACY.md` — privacy policy; only update if data handling practices change
- `tests/TESTING_*.md` — updated alongside test code changes, not per release
- `.cursor/plans/*.md` — historical plans, never modified after creation
- `.windsurf/`, `.cursor/rules/`, `.cursor/skills/` — tooling/AI config, not release docs
