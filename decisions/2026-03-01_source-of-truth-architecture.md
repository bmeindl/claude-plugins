# Decision: Local Source of Truth + Manifest Architecture

**Date:** 2026-03-01
**Participants:** Benjamin
**Status:** Accepted

## Context

Team knowledge sharing in SynteaOS used two systems:
1. **department-context/** — GitLab subtree at `syntea-pm/department-context/`, pushed to a dedicated GitLab repo
2. **ai-collab/** — GitHub repo for per-user shared context with visibility controls, symlinks, and `/cmesh` skill

Both handled "share knowledge with the team" but with different mechanisms. Maintaining two sharing systems creates confusion and splits the workflow.

## Options Considered

### A. Move files to ai-collab (shared-repo-as-source)
Files live in ai-collab, symlinked back to workspace. Simple, but:
- Breaks multi-audience: a file can't live in 2 repos as source
- Removes files from local workspace (editing friction)
- GitLab subtree for IU team stops working

### B. Local source + copy on share (chosen)
Files stay local. A manifest (`.collab-manifest.yml`) tracks what's shared, where, when. `/cmesh share` copies to target repos. `/cmesh sync` detects drift.
- Multi-audience: same file published to ai-collab AND GitLab
- No file removal from workspace
- Manifest provides transparency and staleness detection

### C. Pointer-based (manifest only, no copy)
Manifest points to files but doesn't copy. Receivers must have access to the source.
- Too fragile: requires all collaborators to access all source repos
- No offline/snapshot capability

### D. Manifest-hybrid (manifest + on-demand pull)
Like B but receivers pull on demand rather than receiving copies.
- Adds complexity without clear benefit over B

## Decision

**Option B: Local source + manifest + deterministic sync tool.**

Key elements:
- **Source of truth:** Local workspace. Files never leave.
- **Publishing:** `/cmesh share` copies to target repo(s) with frontmatter
- **Transparency:** `.collab-manifest.yml` tracks all shares with SHA256 checksums
- **Staleness:** `collab-sync check` compares checksums, reports drift
- **Privacy:** `collab-sync` enforces `<!-- private -->` tags deterministically (cannot accidentally share)
- **Execution:** Deterministic Python tool (`collab-sync`) for file ops; LLM agent for interactive decisions

## Design Principles (The Thinking Behind It)

**Why "local source" instead of "shared repo as source"?**
The workspace IS the knowledge. Benjamin's department-context files are written, edited, and reasoned about locally. Moving them to a shared repo makes them feel like shared infrastructure — something you're careful about editing. Keeping them local preserves the feeling of "my notes, my workspace, I share what I choose." The manifest makes sharing explicit and auditable without removing ownership.

**Why deterministic tool + LLM agent (not one or the other)?**
Each does what it's best at. The LLM is great at "should this be shared? with whom? what's a good summary tag?" — that's judgment. But copying files, computing checksums, checking privacy tags, and running git commands? That's mechanical, and a mechanical process can't accidentally share a private file. The `<!-- private -->` check is a hard if-statement, not a "please don't share this" prompt instruction. This split also means the tool works without an LLM at all (cron job, CI pipeline, manual run).

**Why checksums instead of timestamps?**
A file could be `touch`ed without changing. Conversely, a file could change and have its timestamp reset. SHA256 is the only reliable way to know if content actually changed. It's also cheap to compute (16 files in <1ms).

**Why track the GitLab subtree in the manifest?**
The manifest should be the single place to answer "where does this workspace share knowledge?" Even though collab-sync doesn't operate the subtree (that's still `git subtree push`), tracking it provides complete visibility. When we eventually retire the subtree, we remove the entry.

**Why `.collabignore` in addition to `<!-- private -->`?**
In-file tags protect individual files. But some entire directories should never be scanned — `personal/`, `inbox/`, credential folders. `.collabignore` provides folder-level exclusion without touching any files.

## Consequences

- `.collab-manifest.yml` is the canonical record of what's shared from each workspace
- `department-context/` continues to exist locally (still source of truth for content)
- GitLab subtree remains a valid publication target (tracked in manifest, not operated by collab-sync)
- `/syntea-context` skill simplified: team sharing routed to `/cmesh share`
- Colleagues migrating from department-context only need to add ai-collab + manifest
- The `collab-sync` tool at `claude-plugins/plugins/cmesh/tools/collab-sync/` handles all deterministic operations

## Migration Path

**For Benjamin (done):** `.collab-manifest.yml` created, 16 files published, symlink added.

**For colleagues already on department-context (if any):** See `migration-from-department-context.md` — agent-executable guide that walks through setup, CLAUDE.md updates, and verification.

**For new colleagues:** `/cmesh setup` handles everything. No department-context knowledge needed.

**Retirement of department-context (future):** When all IU team members are on ai-collab, remove GitLab subtree remote, archive the GitLab repo, clean up the manifest entry. The local folder can stay or be reorganized. This is a Phase 2+ decision.

## Related Documents

- `claude-plugins/plugins/cmesh/tools/collab-sync/README.md` — Tool documentation and architecture
- `claude-plugins/plugins/cmesh/skills/cmesh/SKILL.md` — How the LLM agent uses the tool
- `ground-control/.collab-manifest.yml` — Benjamin's manifest (the first one)
