# Agent Context Mesh (cmesh) — Dev Context

Guidance for AI assistants working on this plugin.

## What This Plugin Is

Source code for the Agent Context Mesh **tool** layer: the SKILL.md (agent brain, 10 modes) and collab-sync CLI (deterministic Python, 8 commands). No user data lives here.

## Key Files

| File | Purpose | Edit frequency |
|------|---------|----------------|
| `skills/cmesh/SKILL.md` | Agent instructions for all 10 modes | Often — new features, UX improvements |
| `tools/collab-sync/sync.py` | CLI entry point, command dispatch | Moderate — new commands, flag changes |
| `tools/collab-sync/manifest.py` | Manifest YAML handling | Rare — schema changes |
| `tools/collab-sync/safety.py` | Privacy enforcement | Rare — new safety rules |
| `tools/collab-sync/crypto.py` | age encryption, key exchange | Rare — crypto changes |
| `tools/collab-sync/changes.py` | Checksums, stale detection | Rare |
| `tools/collab-sync/operations.py` | File copy with frontmatter | Rare |

## Architecture Principles

1. **LLM handles judgment, CLI handles mechanics.** The SKILL.md decides what to share and with whom. collab-sync does the file copy, checksum, git, encryption. This prevents the LLM from accidentally sharing private content.

2. **Privacy is code, not prompt.** `<!-- private -->` is a hard `if` in `safety.py`, not an instruction to the LLM.

3. **Data repos are siblings, not nested.** ai-collab sits next to workspaces at `~/Documents/` level. This enables multi-workspace access.

4. **`$AI_COLLAB` = data, `$COLLAB_TOOL` = tool.** SKILL.md uses `$AI_COLLAB` for data access (symlinks, inbox, git pull/push) and `$COLLAB_TOOL` for the CLI path. Don't mix them.

## How to Test Changes

1. This repo should be cloned as a sibling to your workspace (at `~/Documents/claude-plugins/`)
2. Or symlinked into your workspace (e.g., `personal/projects/claude-plugins/`)
3. The SKILL.md `$COLLAB_TOOL` discovery finds it automatically
4. Edit → save → invoke `/cmesh <mode>` in your workspace → immediate effect
5. No reinstall needed (plugin-relative path works for both dev and installed)

## Release Process

Changes in this repo ARE the release — no separate copy step needed.
Bump version in `.claude-plugin/plugin.json` for significant changes.
Users get updates on next `/plugin update`.

## Maintainers

- Benjamin Meindl (@bmeindl) — PM, original author
- Quintus Stierstorfer (@DIY-Quinny) — PM, co-developer
