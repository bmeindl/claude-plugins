# collab-sync — Deterministic Sync Tool

A focused Python CLI that reads `.collab-manifest.yml` and handles all file operations for shared context — deterministically, with no LLM involved in copy/commit/push.

## Why Deterministic?

The core insight: **privacy and file operations should never depend on LLM judgment.**

- An LLM might accidentally share a private file. A script that checks `<!-- private -->` tags **cannot** make that mistake.
- At scale (5 colleagues × 10 files = 50 files), deterministic operations are fast and reliable.
- The LLM agent handles what it's good at: deciding *what* to share, *with whom*, and generating tags. The tool handles what scripts are good at: checksums, file copies, git operations.

## Commands

```bash
# Check what's stale or missing (read-only, safe to run anytime)
python3 sync.py --workspace /path/to/workspace check

# Short summary (for /cmesh status)
python3 sync.py --workspace /path/to/workspace check --summary

# JSON output (for programmatic use)
python3 sync.py --workspace /path/to/workspace check --json

# Copy changed files to target repo, commit, push
python3 sync.py --workspace /path/to/workspace push

# Dry run — show what would happen
python3 sync.py --workspace /path/to/workspace push --dry

# Add a file to the manifest
python3 sync.py --workspace /path/to/workspace add path/to/file.md \
  --dest benjamin/outbound/iu-public/file.md \
  --visibility iu-public \
  --tag "Description of the file"

# Remove a share entry
python3 sync.py --workspace /path/to/workspace remove path/to/file.md

# Create a new manifest
python3 sync.py --workspace /path/to/workspace init --name ground-control --user benjamin
```

If `--workspace` is omitted, auto-detects by walking up from cwd to find `.collab-manifest.yml` or `.git`.

## Module Structure

| Module | LOC | Purpose |
|--------|-----|---------|
| `sync.py` | ~150 | CLI entry point (argparse), command dispatch |
| `manifest.py` | ~130 | YAML load/save/validate, schema, entry CRUD |
| `changes.py` | ~80 | SHA256 checksums, stale detection, `<!-- shared -->` tag scanning |
| `operations.py` | ~30 | Copy with frontmatter prepend, directory creation |
| `safety.py` | ~80 | `<!-- private -->` enforcement, `.collabignore` parsing |

## Safety Guarantees

These are **hard constraints** — the tool refuses to proceed, no override flag:

1. **`<!-- private -->`** — If the first line of a source file is `<!-- private -->`, the tool will not share it. Period.
2. **`.collabignore`** — Glob patterns (like .gitignore) that exclude files/folders. Placed in any directory, applies to subtree.
3. **Source missing** — If a source file no longer exists, the tool marks it `source_missing` in the manifest and warns. It **never** deletes the target copy.
4. **Dirty target** — If the target repo has uncommitted changes, the tool refuses to push.

## How It Fits Together

```
User says "share this"
        │
        ▼
┌─────────────────┐
│  /cmesh share   │  LLM agent: decides visibility, generates tag,
│  (SKILL.md)      │  confirms with user
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  collab-sync     │  Deterministic: computes checksum, checks privacy,
│  add + push      │  copies file with frontmatter, updates manifest,
└────────┬────────┘  commits and pushes
         │
         ▼
┌─────────────────┐
│  ai-collab repo  │  Published copy lives here, discoverable via
│  (GitHub)        │  symlinks by all collaborators
└─────────────────┘
```

## Dependencies

- Python 3.10+
- `pyyaml` (see `requirements.txt`)
- Git (for push operations)

## Future Considerations

- **Batch operations:** `collab-sync push` already handles all stale files in one pass. Could add `--only <source>` for selective re-publish.
- **Watch mode:** `collab-sync watch` could monitor source files and notify when shares go stale (not planned, low priority).
- **Multi-repo targets:** The manifest schema already supports multiple targets per source (e.g., ai-collab AND GitLab). The push command processes all targets.
